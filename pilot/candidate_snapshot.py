"""Read-only complete candidate inventory; not enrollment or acceptance.

Call only while the candidate writer is quiescent. A stable inventory is not
proof of historical immutability; native execution must expose it read-only.
Version one deliberately supports no exclusions or source-scope subsets.
"""
import hashlib
import os
from pathlib import Path
import stat

from admission import digest


def _mount_id(fd):
    # st_dev alone cannot identify same-filesystem bind mounts. Linux fdinfo
    # supplies the mount identity of the actual opened object. Other hosts fail
    # closed; this primitive is for the private Linux execution lane.
    try:
        with open('/proc/self/fdinfo/' + str(fd), 'rb') as stream:
            payload = stream.read(4097)
        rows = [line.split(b':', 1)[1].strip() for line in payload.splitlines()
                if line.startswith(b'mnt_id:')]
        if len(payload) > 4096 or len(rows) != 1 or not rows[0].isdigit():
            raise ValueError('Candidate mount identity unavailable')
        return int(rows[0])
    except OSError as exc:
        raise ValueError('Candidate mount identity unavailable') from exc


def capture_candidate(policy):
    if (not isinstance(policy, dict) or set(policy) != {
            'schema', 'candidate_root', 'scope', 'max_entries',
            'max_file_bytes', 'max_total_bytes', 'max_depth', 'allowed_uids'} or
            type(policy['schema']) is not int or policy['schema'] != 1 or
            policy['scope'] != 'entire_candidate'):
        raise ValueError('Unsupported complete candidate policy')
    limits = {'max_entries': 100000, 'max_file_bytes': 67108864,
              'max_total_bytes': 1073741824, 'max_depth': 128}
    if any(type(policy[k]) is not int or not 0 < policy[k] <= cap
           for k, cap in limits.items()):
        raise ValueError('Bounded candidate limits required')
    owners = policy['allowed_uids']
    if (not isinstance(owners, list) or not 1 <= len(owners) <= 4 or
            any(type(uid) is not int or not 0 <= uid < 2 ** 31 for uid in owners) or
            owners != sorted(set(owners))):
        raise ValueError('Explicit bounded candidate owners required')
    root = policy['candidate_root']
    if (not isinstance(root, str) or not root or
            not Path(root).is_absolute() or str(Path(root)) != root or
            '..' in Path(root).parts or Path(root).resolve() != Path(root)):
        raise ValueError('Canonical candidate root required')
    directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in Path(root).parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=directory)
            os.close(directory)
            directory = child
        root_stat = os.fstat(directory)
        root_mount = _mount_id(directory)
        def identity(info):
            return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
                    info.st_uid, info.st_gid, info.st_size,
                    info.st_mtime_ns, info.st_ctime_ns)
        def inventory():
            entries, observed, total = [], [], 0
            def walk(fd, prefix, depth):
                nonlocal total
                if depth > policy['max_depth']:
                    raise ValueError('Candidate depth exceeded')
                before = os.fstat(fd)
                if before.st_uid not in owners:
                    raise ValueError('Unsupported candidate owner')
                if (_mount_id(fd) != root_mount or before.st_dev != root_stat.st_dev):
                    raise ValueError('Candidate mount boundary')
                observed.append((prefix, identity(before)))
                entries.append({'path': prefix, 'type': 'directory',
                                'mode': stat.S_IMODE(before.st_mode),
                                'uid': before.st_uid, 'gid': before.st_gid})
                if len(entries) > policy['max_entries']:
                    raise ValueError('Candidate entry limit exceeded')
                # Listing must itself remain bounded before sorting/materializing.
                names = []
                with os.scandir(fd) as listing:
                    for item in listing:
                        names.append(item.name)
                        if len(names) + len(entries) > policy['max_entries']:
                            raise ValueError('Candidate entry limit exceeded')
                for name in sorted(names):
                    path = prefix + '/' + name if prefix else name
                    info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                    if info.st_uid not in owners:
                        raise ValueError('Unsupported candidate owner')
                    if info.st_dev != root_stat.st_dev:
                        raise ValueError('Candidate mount boundary')
                    if stat.S_ISDIR(info.st_mode):
                        child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                        dir_fd=fd)
                        try:
                            if _mount_id(child) != root_mount:
                                raise ValueError('Candidate mount boundary')
                            if identity(os.fstat(child)) != identity(info):
                                raise ValueError('Candidate directory changed')
                            walk(child, path, depth + 1)
                        finally:
                            os.close(child)
                    elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                        child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                        dir_fd=fd)
                        try:
                            if _mount_id(child) != root_mount:
                                raise ValueError('Candidate mount boundary')
                            if identity(os.fstat(child)) != identity(info):
                                raise ValueError('Candidate file changed')
                            hashed, size = hashlib.sha256(), 0
                            while True:
                                data = os.read(child, 65536)
                                if not data:
                                    break
                                size += len(data)
                                total += len(data)
                                if (size > policy['max_file_bytes'] or
                                        total > policy['max_total_bytes']):
                                    raise ValueError('Candidate byte limit exceeded')
                                hashed.update(data)
                            if _mount_id(child) != root_mount:
                                raise ValueError('Candidate mount boundary')
                            if identity(os.fstat(child)) != identity(info):
                                raise ValueError('Candidate file changed during capture')
                        finally:
                            os.close(child)
                        observed.append((path, identity(info)))
                        entries.append({'path': path, 'type': 'file',
                                        'mode': stat.S_IMODE(info.st_mode),
                                        'uid': info.st_uid, 'gid': info.st_gid,
                                        'bytes': size, 'sha256': hashed.hexdigest()})
                        if len(entries) > policy['max_entries']:
                            raise ValueError('Candidate entry limit exceeded')
                    else:
                        raise ValueError('Candidate link or special file unsupported')
                if identity(os.fstat(fd)) != identity(before):
                    raise ValueError('Candidate directory changed during capture')
            walk(directory, '', 0)
            return entries, observed
        first = inventory()
        if inventory() != first:
            raise ValueError('Candidate changed between inventory passes')
        # Detect replacement of the named root or any ancestor as well.
        if (Path(root).resolve() != Path(root) or
                identity(os.stat(root, follow_symlinks=False)) != identity(root_stat)):
            raise ValueError('Candidate root changed')
        manifest = {'schema': 1, 'policy_sha256': digest(policy), 'entries': first[0]}
        return {'manifest': manifest, 'sha256': digest(manifest)}
    finally:
        os.close(directory)


def require_candidate_snapshot(policy, snapshot):
    if (not isinstance(snapshot, dict) or set(snapshot) != {'manifest', 'sha256'} or
            snapshot['sha256'] != digest(snapshot['manifest']) or
            capture_candidate(policy) != snapshot):
        raise ValueError('Candidate snapshot changed or substituted')
    return snapshot
