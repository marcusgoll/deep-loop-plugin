"""Independent preconditions for no-model native policy probes.

Absence checks close configuration-loading differences between exec and sandbox.
They do not prove sandbox behavior or produce passing qualification authority.
"""
import hashlib
import os
from pathlib import Path
import pwd
import stat
import subprocess
from admission import digest,initialize
from private_launch import ACCOUNT,ROOT


def configuration_paths(candidate,home):
    candidate,home=Path(candidate),Path(home)
    paths={Path('/etc/codex/config.toml'),Path('/etc/codex/requirements.toml'),
           home/'.codex/config.toml',home/'.codex/rules'}
    for parent in (candidate,*candidate.parents):
        paths.update((parent/'.codex/config.toml',parent/'.codex/rules'))
    return sorted(paths,key=str)


def require_absent(paths):
    for path in paths:
        if path.exists() or path.is_symlink():
            raise ValueError('Unexpected policy configuration: '+str(path))


# The pinned native sandbox creates these empty root guard directories while
# preparing its filesystem boundary. They never authorize config or contents.
RUNTIME_GUARD_DIRS = frozenset({'.codex', '.git', '.agents', '.aws'})


def empty_runtime_guard(fd, name, owner_uid):
    if name not in RUNTIME_GUARD_DIRS:
        return False
    before = os.stat(name, dir_fd=fd, follow_symlinks=False)
    if not stat.S_ISDIR(before.st_mode) or before.st_uid != owner_uid:
        raise ValueError('Unsafe native runtime guard')
    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
    try:
        opened = os.fstat(child)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError('Native runtime guard changed during inspection')
        with os.scandir(child) as entries:
            if next(entries, None) is not None:
                raise ValueError('Native runtime guard contains unexpected objects')
        after = os.fstat(child)
        if (opened.st_mtime_ns, opened.st_ctime_ns) != (after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError('Native runtime guard changed during inspection')
    finally:
        os.close(child)
    return True


def inspect_candidate(candidate,owner_uid,limit=4096,*,allow_runtime_guards=False):
    count=0
    def walk(fd,depth):
        nonlocal count
        if depth>64:raise ValueError('Candidate exceeds depth bound')
        with os.scandir(fd) as iterator:
            for entry in iterator:
                count+=1
                if count>limit:raise ValueError('Candidate exceeds qualification bound')
                if allow_runtime_guards and depth == 0 and empty_runtime_guard(fd,entry.name,owner_uid):
                    continue
                info=os.stat(entry.name,dir_fd=fd,follow_symlinks=False)
                if (entry.name in {'.codex','.git','hooks.json'} or stat.S_ISLNK(info.st_mode) or
                        info.st_uid!=owner_uid or
                        not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)) or
                        (stat.S_ISREG(info.st_mode) and info.st_nlink!=1)):
                    raise ValueError('Unsafe candidate execution object')
                if stat.S_ISDIR(info.st_mode):
                    child=os.open(entry.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                    try:
                        opened=os.fstat(child)
                        if (opened.st_dev,opened.st_ino)!=(info.st_dev,info.st_ino):
                            raise ValueError('Candidate changed during inspection')
                        walk(child,depth+1)
                    finally:os.close(child)
    fd=os.open(candidate,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:walk(fd,0)
    finally:os.close(fd)


def inspect_environment(plan,contract):
    if os.geteuid()!=0 or plan['contract_digest']!=digest(contract):
        raise ValueError('Trusted root exact-contract qualification required')
    if set(contract['executor'])!={'path','sha256'}:raise ValueError('Exact pinned executor required')
    initialize(contract['executor']['sha256'])
    account=pwd.getpwnam(ACCOUNT)
    if account.pw_dir!=ROOT+'/home' or os.getgrouplist(ACCOUNT,account.pw_gid)!=[account.pw_gid]:
        raise ValueError('Private account identity drift')
    candidate=Path(plan['candidate'])
    if str(candidate)!=ROOT+'/candidate/'+digest(contract) or candidate.resolve()!=candidate:
        raise ValueError('Candidate path drift')
    for path in (candidate,Path(account.pw_dir)):
        info=path.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid!=account.pw_uid or
                info.st_gid!=account.pw_gid or stat.S_IMODE(info.st_mode)!=0o700):
            raise ValueError('Private directory identity drift')
    binary=Path(contract['executor']['path'])
    if not binary.is_absolute() or binary.resolve()!=binary:
        raise ValueError('Noncanonical executor')
    for path in (binary,*binary.parents):
        info=path.lstat()
        if info.st_uid!=0 or info.st_mode&0o022 or stat.S_ISLNK(info.st_mode):
            raise ValueError('Untrusted executor path')
    if (not stat.S_ISREG(binary.stat().st_mode) or not os.access(binary,os.X_OK) or
            hashlib.sha256(binary.read_bytes()).hexdigest()!=contract['executor']['sha256']):
        raise ValueError('Executor changed')
    paths=configuration_paths(candidate,account.pw_dir)
    require_absent(paths)
    inspect_candidate(candidate,account.pw_uid)
    processes=subprocess.run(['/usr/bin/pgrep','-u',str(account.pw_uid)],capture_output=True,text=True,timeout=5)
    if processes.returncode!=1:
        raise ValueError('Private account has another process or ownership unavailable')
    return {'contract_digest':digest(contract),'executor':contract['executor'],
            'candidate':str(candidate),'uid':account.pw_uid,'gid':account.pw_gid,
            'absent_configuration_paths':[str(path) for path in paths]}
