"""Stage an immutable reviewed module bundle; no runtime activation/enrollment.

Plan by default. Existing and partially installed bundles are never overwritten.
The old installed modules, lock and journal remain in place.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

from admission import digest, initialize
from private_controller import TrustedStore
from private_launch import ROOT

CONTROL = Path(ROOT)/'control'
MODULES = ('admission.py', 'authority.py', 'git_journal.py', 'private_launch.py',
           'private_controller.py', 'systemd_observer.py', 'native_session.py',
           'native_backend.py', 'artifact_verifier.py', 'resume_verifier.py', 'private_wakeup.py',
           'worker_window.py', 'private_worker.py', 'worker_units.py',
           'trusted_delivery.py', 'github_transport.py', 'delivery_artifact.py',
           'qualification_environment.py', 'qualification_plan.py',
           'qualification_probe.py', 'qualification_runner.py', 'strict_configuration.py',
           'enrollment.py', 'enrollment_operator.py', 'frozen_contract.py', 'workflow_gate.py')


def plan():
    source = Path(__file__).resolve().parent
    hashes = {name: hashlib.sha256((source/name).read_bytes()).hexdigest() for name in MODULES}
    return {'schema':1, 'control':str(CONTROL), 'modules':hashes,
            'runtime_activated':False, 'timer_installed':False, 'model_calls':0}


def apply(expected_digest):
    initialize(expected_digest)
    if os.geteuid() != 0 or sys.platform != 'linux':
        raise ValueError('Explicit root Linux promotion required')
    expected = plan()
    if digest(expected) != expected_digest:
        raise ValueError('Reviewed source bundle changed')
    source = Path(__file__).resolve().parent
    for path in (source, *source.parents):
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('Untrusted promotion source parent')
    store = TrustedStore(CONTROL)
    with store.lock():
        if any((CONTROL/name).exists() or (CONTROL/name).is_symlink()
               for name in ('active-owner.json', 'enabled-outcome.json')) or list(CONTROL.glob('*.approval.json')):
            raise ValueError('Promotion requires an unenrolled inactive pilot')
        target = CONTROL/('bundle-'+expected_digest)
        target.mkdir(mode=0o700)
        store._sync()
        for name, expected_hash in expected['modules'].items():
            source_fd = os.open(source/name, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(source_fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022 or info.st_nlink != 1:
                    raise ValueError('Untrusted promotion source file')
                data = stream.read(1024*1024+1)
            if len(data) > 1024*1024 or hashlib.sha256(data).hexdigest() != expected_hash:
                raise ValueError('Reviewed module changed')
            fd = os.open(target/name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o444)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fchmod(stream.fileno(),0o444)
                os.fsync(stream.fileno())
        bundle_store = TrustedStore(target)
        bundle_store.create('manifest.json',expected)
        for name, expected_hash in expected['modules'].items():
            if hashlib.sha256((target/name).read_bytes()).hexdigest() != expected_hash:
                raise ValueError('Installed bundle readback mismatch')
        bundle_store._sync()
        receipt = {'bundle_digest':expected_digest, 'bundle_path':str(target), 'manifest':expected}
        store.create(expected_digest+'.bundle.json',receipt)
        if store.read(expected_digest+'.bundle.json') != receipt:
            raise ValueError('Bundle receipt readback mismatch')
        return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--expected-digest')
    args = parser.parse_args()
    if args.apply:
        if not args.expected_digest:
            parser.error('--apply requires reviewed --expected-digest')
        print(json.dumps(apply(args.expected_digest),indent=2))
    else:
        manifest = plan()
        print(json.dumps({'bundle_digest':digest(manifest),'manifest':manifest},indent=2))
