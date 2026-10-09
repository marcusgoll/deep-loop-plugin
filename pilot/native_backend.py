"""Private native executor adapter. No CLI entrypoint or default enrollment.

Only the trusted controller may call it after importing exact human approval.
Qualification receipts are produced by independently reviewed no-model host
probes, outside this adapter; their absence blocks submission.
"""
import hashlib
import os
from pathlib import Path
import pwd
import stat
import subprocess

from admission import digest
from native_session import MAX_CAPTURE_BYTES, session_from_capture
from private_launch import ACCOUNT, ROOT
from systemd_observer import observe_unit


def permission_digest(plan):
    command = plan['command']
    overrides = [command[i+1] for i, value in enumerate(command[:-1]) if value == '-c']
    return digest({'overrides': overrides, 'ignore_user_config': '--ignore-user-config' in command,
                   'ignore_rules': '--ignore-rules' in command, 'hooks_disabled': ['--disable', 'hooks'] == command[command.index('--disable'):command.index('--disable')+2]})


class NativeBackend:
    def __init__(self, store, contract_digest):
        self.store, self.contract_digest = store, contract_digest
        self.qualified = None

    def qualify(self, plan, contract):
        self.qualified = None
        if os.geteuid() != 0 or digest(contract) != self.contract_digest or plan['contract_digest'] != self.contract_digest:
            raise ValueError('Trusted root exact-contract execution required')
        approval = self.store.read(self.contract_digest + '.approval.json')
        if approval['contract'] != contract or not approval['approval_ref']:
            raise ValueError('Exact authenticated approval required')
        executor = contract['executor']
        if set(executor) != {'path', 'sha256'} or not isinstance(contract['prompt'], str) or not contract['prompt']:
            raise ValueError('Pinned native executor and exact prompt required')
        binary = Path(executor['path'])
        if not binary.is_absolute() or binary.resolve() != binary:
            raise ValueError('Canonical native executor required')
        for path in (binary, *binary.parents):
            info = path.lstat()
            if info.st_uid != 0 or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode):
                raise ValueError('Untrusted native executable path')
        if not stat.S_ISREG(binary.stat().st_mode) or not os.access(binary, os.X_OK) or hashlib.sha256(binary.read_bytes()).hexdigest() != executor['sha256']:
            raise ValueError('Native executable drift')
        account = pwd.getpwnam(ACCOUNT)
        if account.pw_dir != ROOT+'/home' or os.getgrouplist(ACCOUNT, account.pw_gid) != [account.pw_gid]:
            raise ValueError('Private execution identity drift')
        candidate = Path(plan['candidate'])
        if str(candidate) != ROOT+'/candidate/'+self.contract_digest or candidate.resolve() != candidate:
            raise ValueError('Candidate path drift')
        for path in (Path(account.pw_dir), candidate):
            info = path.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != account.pw_uid or info.st_gid != account.pw_gid or stat.S_IMODE(info.st_mode) != 0o700:
                raise ValueError('Private account directory ownership drift')
        for path in candidate.rglob('*'):
            info = path.lstat()
            if path.name in {'.codex', '.git', 'hooks.json'} or stat.S_ISLNK(info.st_mode) or not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)) or info.st_uid != account.pw_uid:
                raise ValueError('Candidate contains unqualified execution configuration or filesystem object')
            if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
                raise ValueError('Candidate contains an aliased file')
        for path in ('/etc/codex/config.toml', '/etc/codex/requirements.toml'):
            if Path(path).exists() or Path(path).is_symlink():
                raise ValueError('Unexpected managed system configuration requires requalification')
        # No other process may own this private credential stream outside the
        # controller. The no-model preflight must run before a model unit starts.
        processes = subprocess.run(['/usr/bin/pgrep', '-u', str(account.pw_uid)], capture_output=True, text=True, timeout=5)
        if processes.returncode != 1:
            raise ValueError('Private identity has another process or unavailable ownership evidence')
        receipt = self.store.read(self.contract_digest + '.qualification.json')
        expected = {'contract_digest': self.contract_digest, 'executor': executor,
                    'permission_digest': permission_digest(plan), 'candidate': str(candidate),
                    'checks': {'candidate_write': True, 'private_direct_read_denied': True,
                               'private_symlink_read_denied': True, 'network_denied': True,
                               'native_config_validated': True, 'systemd_io_validated': True}}
        if receipt != expected:
            raise ValueError('Missing or incompatible independent native qualification')
        self.qualified = (digest(plan), digest(contract))

    def _raw(self, name, data):
        fd = os.open(self.store._path(name), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        self.store._sync()
        return str(self.store._path(name))

    def submit(self, plan, contract):
        if self.qualified != (digest(plan), digest(contract)):
            raise ValueError('Native submission has no matching qualification')
        self.qualified = None
        owner = self.store.read('active-owner.json')
        if owner['contract_digest'] != self.contract_digest or owner['unit'] != plan['unit'] or owner['plan_digest'] != digest(plan):
            raise ValueError('Native submission has no matching durable intent')
        unit = plan['unit']
        prompt = self._raw(unit+'.prompt', contract['prompt'].encode())
        capture = self._raw(unit+'.jsonl', b'')
        errors = self._raw(unit+'.stderr', b'')
        properties = dict(plan['properties'], StandardInput='file:'+prompt,
                          StandardOutput='append:'+capture, StandardError='append:'+errors,
                          LimitFSIZE=str(MAX_CAPTURE_BYTES), Slice='system.slice')
        args = ['/usr/bin/systemd-run', '--unit='+unit, '--service-type=exec']
        args += ['--property='+key+'='+str(value) for key, value in properties.items()]
        # Invoke the pinned native binary directly, avoiding Node wrapper and
        # package-resolution changes. No shared app-server daemon is used.
        command = [contract['executor']['path'], '--no-daemon', *plan['command'][1:]]
        command.insert(command.index('exec')+1, '--skip-git-repo-check')
        subprocess.run(args + command, capture_output=True, text=True, check=True, timeout=5)
        invocation = subprocess.run(['/usr/bin/systemctl', 'show', unit+'.service', '--property=InvocationID', '--value'],
                                    capture_output=True, text=True, check=True, timeout=5).stdout.strip()
        # Exact native ownership readback is required before returning identity.
        observe_unit(unit, invocation)
        return invocation

    def observe(self, unit, invocation):
        owner = self.store.read('active-owner.json')
        if owner['contract_digest'] != self.contract_digest or owner['unit'] != unit:
            raise ValueError('Capture has no matching protected ownership')
        observed = observe_unit(unit, invocation)
        if observed['active_state'] not in {'inactive', 'failed'} or not observed['cgroup_empty']:
            return observed, None
        fd = self.store._open(unit+'.jsonl', os.O_RDONLY)
        with os.fdopen(fd, 'rb') as stream:
            data = stream.read(MAX_CAPTURE_BYTES+1)
        session = session_from_capture(data, owner['session_id'])
        return observed, session
