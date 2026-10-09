"""Plan-only by default; explicit root apply installs protected prerequisites.

No approval, journal ref, native executor, timer or model invocation is created.
Partial failure is preserved for inspection, never automatically reinitialized.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

from private_controller import TrustedStore
from private_launch import ROOT

CONTROL = Path(ROOT)/'control'
MODULES = ('admission.py', 'git_journal.py', 'private_launch.py',
           'private_controller.py', 'systemd_observer.py')


def plan():
    source = Path(__file__).resolve().parent
    hashes = {name: hashlib.sha256((source/name).read_bytes()).hexdigest() for name in MODULES}
    return {'schema': 1, 'control': str(CONTROL), 'owner_uid': 0, 'directory_mode': '0700',
            'modules': hashes, 'bare_journal': str(CONTROL/'journal.git'),
            'journal_workspace': str(CONTROL/'journal-work'),
            'lock': 'credential-stream.lock', 'enrolled_outcomes': 0,
            'model_calls': 0, 'timer_installed': False}


def apply(expected):
    if os.geteuid() != 0 or sys.platform != 'linux':
        raise ValueError('Explicit root Linux setup required')
    if expected != plan():
        raise ValueError('Source changed after plan')
    for parent in CONTROL.parents:
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or parent.resolve() != parent or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('Untrusted controller storage parent')
    # mkdir deliberately rejects existing state, including a partial prior setup.
    CONTROL.mkdir(mode=0o700)
    store = TrustedStore(CONTROL)
    store.create('credential-stream.lock', {})
    modules = CONTROL/'modules'
    modules.mkdir(mode=0o700)
    source = Path(__file__).resolve().parent
    for name, expected_hash in expected['modules'].items():
        data = (source/name).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected_hash:
            raise ValueError('Reviewed module changed')
        target = modules/name
        with target.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        target.chmod(0o444)
    for args in (['git', 'init', '--bare', str(CONTROL/'journal.git')],
                 ['git', 'init', str(CONTROL/'journal-work')]):
        subprocess.run(args, check=True, capture_output=True, timeout=10)
    for name, expected_hash in expected['modules'].items():
        if hashlib.sha256((modules/name).read_bytes()).hexdigest() != expected_hash:
            raise ValueError('Installed module readback mismatch')
    # Persist the immutable installation receipt after independent hash readback.
    store.create('installation.json', expected)
    return store.read('installation.json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    expected = plan()
    print(json.dumps(apply(expected) if args.apply else expected, indent=2))
