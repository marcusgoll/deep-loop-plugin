"""Read-only Git projection of one complete, currently verified candidate.

No provider, enrollment, acceptance, or Git process is invoked. Callers must
hold account-wide quiescence and recheck their own authority/window. The explicit
projection retains all regular files; Git directories are implicit and file
modes preserve only the executable bit. Full source metadata remains bound by
the candidate snapshot. Never mix this projection with a provider base tree.
"""
import hashlib
import os
from pathlib import Path
import stat

from admission import digest
from candidate_snapshot import _mount_id, require_candidate_snapshot

RULES = {'kind': 'git_regular_files_v1', 'directories': 'implicit',
         'file_modes': 'executable_bit'}


def git_object(kind, payload):
    return hashlib.sha1(kind.encode() + b' ' + str(len(payload)).encode() + b'\0' + payload).hexdigest()


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_uid,
            info.st_gid, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


class GitCandidateExport:
    def __init__(self, policy, snapshot, rules):
        if rules != RULES:
            raise ValueError('Explicit complete Git projection required')
        # Retained snapshots grant no export truth on their own.
        require_candidate_snapshot(policy, snapshot)
        self.policy, self.snapshot = policy, snapshot

    def _read(self, entry, *, contents=False):
        """Open every component without following links; hash the actual bytes."""
        directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        try:
            for part in Path(self.policy['candidate_root']).parts[1:]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                os.close(directory); directory = child
            root = os.fstat(directory); mount = _mount_id(directory)
            if root.st_uid not in self.policy['allowed_uids']:
                raise ValueError('Foreign export root')
            for part in entry['path'].split('/')[:-1]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                os.close(directory); directory = child
                info = os.fstat(directory)
                if info.st_uid not in self.policy['allowed_uids'] or info.st_dev != root.st_dev or _mount_id(directory) != mount:
                    raise ValueError('Foreign export directory or mount')
            child = os.open(entry['path'].split('/')[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            try:
                before = os.fstat(child)
                if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or
                        before.st_dev != root.st_dev or _mount_id(child) != mount or
                        (stat.S_IMODE(before.st_mode), before.st_uid, before.st_gid, before.st_size) !=
                        (entry['mode'], entry['uid'], entry['gid'], entry['bytes'])):
                    raise ValueError('Export input identity changed')
                git = hashlib.sha1(b'blob ' + str(entry['bytes']).encode() + b'\0')
                source = hashlib.sha256(); size = 0; chunks = []
                while True:
                    chunk = os.read(child, 65536)
                    if not chunk: break
                    size += len(chunk)
                    if size > entry['bytes'] or size > self.policy['max_file_bytes']:
                        raise ValueError('Export byte limit exceeded')
                    git.update(chunk); source.update(chunk)
                    if contents: chunks.append(chunk)
                if (size != entry['bytes'] or source.hexdigest() != entry['sha256'] or
                        _identity(os.fstat(child)) != _identity(before) or _mount_id(child) != mount):
                    raise ValueError('Candidate changed during Git export')
                return git.hexdigest(), b''.join(chunks) if contents else None
            finally: os.close(child)
        finally: os.close(directory)

    def plan(self):
        require_candidate_snapshot(self.policy, self.snapshot)
        files = []; blob_identities = {}
        for entry in self.snapshot['manifest']['entries']:
            for part in entry['path'].split('/'):
                if part.rstrip(' .').casefold() == '.git':
                    raise ValueError('Git metadata cannot be candidate source')
            if entry['mode'] & 0o7000:
                raise ValueError('Special permission bits cannot be projected to Git')
            if entry['type'] != 'file': continue
            blob, _ = self._read(entry)
            identity = (entry['sha256'], entry['bytes'])
            if blob in blob_identities and blob_identities[blob] != identity:
                raise ValueError('Conflicting candidate bytes share a Git blob identity')
            blob_identities[blob] = identity
            files.append({'path':entry['path'], 'mode':'100755' if entry['mode'] & 0o111 else '100644',
                          'sha':blob, 'sha256':entry['sha256'], 'bytes':entry['bytes']})
        files.sort(key=lambda row:row['path'].encode('utf-8'))
        tree = {}
        for entry in files:
            current = tree; parts = entry['path'].split('/')
            for part in parts[:-1]: current = current.setdefault(part, {'children':{}})['children']
            current[parts[-1]] = entry
        trees = []
        def encode(children, prefix):
            rows = []
            for name, child in children.items():
                directory = 'children' in child
                mode, object_sha = ('40000', encode(child['children'], prefix + name + '/')) if directory else (child['mode'], child['sha'])
                rows.append((name, mode, object_sha, directory))
            rows.sort(key=lambda row:(row[0] + ('/' if row[3] else '')).encode('utf-8'))
            payload = b''.join(mode.encode() + b' ' + name.encode('utf-8') + b'\0' + bytes.fromhex(sha)
                               for name, mode, sha, _ in rows)
            identity = git_object('tree', payload)
            trees.append({'path':prefix.rstrip('/'), 'sha':identity,
                          'entries':[{'name':name, 'mode':mode, 'sha':sha, 'type':'tree' if directory else 'blob'}
                                     for name, mode, sha, directory in rows]})
            return identity
        tree_sha = encode(tree, '')
        require_candidate_snapshot(self.policy, self.snapshot)
        plan = {'kind':'workflow_git_export_v1','candidate_snapshot_sha256':self.snapshot['sha256'],
                'rules':RULES.copy(),'files':files,'tree_sha':tree_sha,'trees':trees}
        return {**plan, 'manifest_sha256':digest(plan)}

    def read_blob(self, plan, blob_sha):
        """Only a fresh complete matching plan may select a content-addressed blob."""
        if self.plan() != plan:
            raise ValueError('Git export manifest changed')
        matches = [row for row in plan['files'] if row['sha'] == blob_sha]
        if not matches: raise ValueError('Blob outside approved Git export')
        row = matches[0]
        entry = next(e for e in self.snapshot['manifest']['entries'] if e['path'] == row['path'])
        observed, data = self._read(entry, contents=True)
        if observed != blob_sha: raise ValueError('Export blob identity changed')
        require_candidate_snapshot(self.policy, self.snapshot)
        return data
