"""Trusted, bounded verifier for the disposable single-artifact outcome.

Only call after native ownership proves the candidate cgroup empty. The frozen
contract supplies every baseline hash and the exact permitted output bytes hash.
Candidate text, logs and timestamps never provide progress authority.
"""
import hashlib
import os
from pathlib import Path, PurePosixPath
import stat

from admission import digest, initialize
from qualification_environment import empty_runtime_guard

MAX_BYTES = 16 * 1024 * 1024
MAX_FILES = 4096


def _path(value):
    if (not isinstance(value, str) or not value or len(value) > 512 or
            str(PurePosixPath(value)) != value or value.startswith('/') or
            any(part in {'.', '..', '.git', '.codex'} for part in value.split('/'))):
        raise ValueError('Invalid frozen artifact path')
    return value


class ArtifactVerifier:
    def __init__(self, candidate, owner_uid, *, allow_runtime_guards=False):
        self.candidate = Path(candidate)
        self.owner_uid = owner_uid
        self.allow_runtime_guards = allow_runtime_guards

    def __call__(self, contract, owner):
        contract_digest = digest(contract)
        if owner['contract_digest'] != contract_digest:
            raise ValueError('Verification contract drift')
        specification = contract['verification']
        if set(specification) != {'baseline', 'artifact_path', 'artifact_sha256'}:
            raise ValueError('Unsupported verification contract')
        baseline = specification['baseline']
        if not isinstance(baseline, dict) or len(baseline) > MAX_FILES:
            raise ValueError('Invalid frozen baseline')
        for name, value in baseline.items():
            _path(name)
            initialize(value)
        artifact = _path(specification['artifact_path'])
        initialize(specification['artifact_sha256'])
        if self.candidate.resolve() != self.candidate or not self.candidate.is_absolute():
            raise ValueError('Noncanonical candidate')
        files = {}
        consumed = 0
        directories = 0
        entries = 0

        def bounded_names(fd):
            nonlocal entries
            with os.scandir(fd) as iterator:
                for entry in iterator:
                    entries += 1
                    if entries > MAX_FILES:
                        raise ValueError('Candidate exceeds entry bound')
                    yield entry.name

        def walk(fd, prefix=''):
            nonlocal consumed, directories, entries
            directories += 1
            if directories > MAX_FILES:
                raise ValueError('Candidate exceeds directory bound')
            info = os.fstat(fd)
            if info.st_uid != self.owner_uid or not stat.S_ISDIR(info.st_mode):
                raise ValueError('Foreign candidate directory')
            for name in bounded_names(fd):
                if self.allow_runtime_guards and not prefix and empty_runtime_guard(fd, name, self.owner_uid):
                    continue
                path = _path(prefix + name)
                before = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISDIR(before.st_mode):
                    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    try:
                        walk(child, path + '/')
                    finally:
                        os.close(child)
                    continue
                if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_uid != self.owner_uid:
                    raise ValueError('Unsafe candidate object')
                child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                try:
                    opened = os.fstat(child)
                    if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                        raise ValueError('Candidate changed during verification')
                    data = bytearray()
                    while True:
                        chunk = os.read(child, min(65536, MAX_BYTES - consumed + 1))
                        if not chunk:
                            break
                        consumed += len(chunk)
                        if consumed > MAX_BYTES:
                            raise ValueError('Candidate exceeds verification bound')
                        data.extend(chunk)
                    after = os.fstat(child)
                    if (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                        raise ValueError('Candidate changed during verification')
                    files[path] = hashlib.sha256(data).hexdigest()
                    if len(files) > MAX_FILES:
                        raise ValueError('Candidate exceeds file bound')
                finally:
                    os.close(child)

        root = os.open(self.candidate, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            walk(root)
        finally:
            os.close(root)
        expected = {**baseline, artifact: specification['artifact_sha256']}
        # Unexpected changes are a failed acceptance check, never new progress.
        if files != expected or baseline.get(artifact) == expected[artifact]:
            return None
        return {'contract_digest': contract_digest, 'verifier': 'exact-artifact-v1',
                'files_digest': digest(files), 'artifact_path': artifact,
                'artifact_sha256': expected[artifact]}
