"""Root-only explicit frozen approve-and-run operator; plan/readback by default.

The operator must authenticate the human approval outside this CLI. An approval
reference is provenance, not a signature. Never invoke --apply from a worker or
public workflow. It starts the timer once without enabling it across host boots.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import sys

from frozen_contract import validate_frozen
from admission import digest, initialize, reserve
from enrollment import Enrollment
from git_journal import GitJournal
from github_transport import GitHubAPI
from native_backend import NativeBackend, permission_digest
from private_controller import TrustedStore
from private_launch import ACCOUNT, ROOT, launch_plan
from worker_units import units

CONTROL = Path(ROOT)/'control'
SYSTEM_UNITS = Path('/etc/systemd/system')
TIMER = 'deep-loop-private-worker.timer'
SERVICE = 'deep-loop-private-worker.service'


def native(*args):
    return subprocess.run(['/usr/bin/systemctl', *args], capture_output=True,
                          text=True, check=True, timeout=5).stdout.strip()


def protected_bytes(path, mode):
    for parent in path.parents:
        info = parent.lstat()
        if parent.resolve() != parent or not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('Untrusted installed source parent')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or
                stat.S_IMODE(info.st_mode) != mode or info.st_nlink != 1):
            raise ValueError('Untrusted installed source file')
        data = stream.read(1024*1024+1)
        if len(data) > 1024*1024:
            raise ValueError('Oversized installed source')
        return data


def preflight(store, contract, api):
    validate_frozen(contract)
    key = digest(contract)
    runtime = contract['runtime']
    if set(runtime) != {'bundle_digest', 'unit_plan_digest'}:
        raise ValueError('Unsupported frozen runtime')
    for value in runtime.values(): initialize(value)
    bundle = CONTROL/('bundle-'+runtime['bundle_digest'])
    manifest = TrustedStore(bundle).read('manifest.json')
    if digest(manifest) != runtime['bundle_digest']:
        raise ValueError('Frozen bundle manifest drift')
    required = {'private_worker.py', 'enrollment.py', 'enrollment_operator.py', 'resume_verifier.py'}
    if (not required <= set(manifest['modules']) or len(manifest['modules']) > 64 or
            manifest.get('control') != str(CONTROL)):
        raise ValueError('Frozen bundle missing required execution modules')
    for name, expected in manifest['modules'].items():
        if Path(name).name != name or not name.endswith('.py'):
            raise ValueError('Unsafe bundle module path')
        initialize(expected)
        if hashlib.sha256(protected_bytes(bundle/name, 0o444)).hexdigest() != expected:
            raise ValueError('Frozen installed module drift')
    # The operator itself must be running from the frozen reviewed bundle.
    if Path(__file__).resolve().parent != bundle:
        raise ValueError('Operator must execute from frozen installed bundle')
    installed = store.read(runtime['unit_plan_digest']+'.units.json')
    expected_units = units(runtime['bundle_digest'])
    if (digest(installed) != runtime['unit_plan_digest'] or installed['units'] != expected_units or
            installed['bundle_digest'] != runtime['bundle_digest']):
        raise ValueError('Frozen worker unit authority drift')
    for name, text in expected_units.items():
        if protected_bytes(SYSTEM_UNITS/name, 0o644) != text.encode():
            raise ValueError('Installed worker unit drift')
        if native('show',name,'--property=LoadState','--value') != 'loaded' or native('show',name,'--property=ActiveState','--value') != 'inactive':
            raise ValueError('Worker must be loaded and inactive before enrollment')
    timer = subprocess.run(['/usr/bin/systemctl','is-enabled',TIMER],capture_output=True,text=True,timeout=5)
    if timer.returncode != 1 or timer.stdout.strip() != 'disabled':
        raise ValueError('Enrollment requires disabled private timer')
    candidate = Path(ROOT)/'candidate'/key
    info = candidate.lstat()
    account = pwd.getpwnam(ACCOUNT)
    if (candidate.resolve() != candidate or not stat.S_ISDIR(info.st_mode) or
            info.st_uid != account.pw_uid or info.st_gid != account.pw_gid or stat.S_IMODE(info.st_mode) != 0o700):
        raise ValueError('Frozen private candidate drift')
    with os.scandir(candidate) as entries:
        if next(entries, None) is not None:
            raise ValueError('Disposable enrollment requires an empty candidate')
    trial = reserve(initialize(key),key,run_id=1,run_attempt=1,model_seconds=600,active_seconds=1200)
    plan = launch_plan(trial,key,run_id=1,run_attempt=1)
    qualification = store.read(key+'.qualification.json')
    checks = {'candidate_write','private_direct_read_denied','private_symlink_read_denied','network_denied',
              'native_config_validated','systemd_io_validated','host_parent_descriptor_read_denied',
              'host_parent_memory_read_denied','external_capabilities_disabled'}
    if qualification != {'contract_digest':key,'executor':contract['executor'],
                         'permission_digest':permission_digest(plan),'candidate':str(candidate),
                         'checks':dict.fromkeys(checks,True)}:
        raise ValueError('Exact independent qualification unavailable')
    # No existing journal ref, even without corresponding local approval files.
    refs = subprocess.run(['git','--git-dir='+str(CONTROL/'journal.git'),'for-each-ref',
                           '--format=%(refname)','refs/heads/deep-loop-journal/'],
                          capture_output=True,text=True,check=True,timeout=5).stdout.strip()
    if refs: raise ValueError('Existing journal enrollment requires inspection')
    delivery = contract['delivery']
    if delivery['repository'] != 'marcusgoll/deep-loop-plugin' or delivery['base_ref'] != 'codex/pilot-admission':
        raise ValueError('Unsupported frozen pilot destination')
    publisher = api('GET','user',None)
    repository = api('GET','repos/'+delivery['repository'],None)
    reference = api('GET','repos/'+delivery['repository']+'/git/ref/heads/'+delivery['base_ref'],None)
    if (publisher.get('login') != 'marcusgoll' or publisher.get('id') != delivery['publisher_id'] or
            repository.get('id') != delivery['repository_id'] or repository.get('permissions',{}).get('push') is not True or
            reference is None or reference.get('object',{}).get('sha') != delivery['source_sha']):
        raise ValueError('Frozen private publisher/source identity drift')
    return {'contract_digest':key,'runtime':runtime,'qualification_digest':digest(qualification),
            'source_sha':delivery['source_sha'],'candidate':str(candidate)}


def activate(contract):
    native('start',TIMER)
    if native('show',TIMER,'--property=ActiveState','--value') != 'active':
        raise ValueError('Private timer activation readback unavailable')
    return {'timer':'active','contract_digest':digest(contract)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('contract_digest')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--approval-ref')
    args = parser.parse_args()
    if os.geteuid() != 0 or sys.platform != 'linux':
        raise ValueError('Trusted root Linux operator required')
    initialize(args.contract_digest)
    store = TrustedStore(CONTROL)
    frozen = store.read(args.contract_digest+'.frozen.json')
    if set(frozen) != {'contract'} or digest(frozen['contract']) != args.contract_digest:
        raise ValueError('Protected frozen contract changed')
    contract = frozen['contract']
    if not args.apply:
        with store.lock(): result = preflight(store,contract,GitHubAPI())
    else:
        if not args.approval_ref: parser.error('--apply requires authenticated --approval-ref')
        journal = GitJournal(CONTROL/'journal-work',str(CONTROL/'journal.git'),args.contract_digest)
        importer = Enrollment(store,journal,NativeBackend(store,args.contract_digest),
                              lambda value:preflight(store,value,GitHubAPI()),activate)
        result = importer.apply(contract,expected_digest=args.contract_digest,approval_ref=args.approval_ref)
    print(json.dumps(result,indent=2))


if __name__ == '__main__': main()
