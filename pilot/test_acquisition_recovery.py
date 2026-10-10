"""Real-process acquisition crashes; no native executor or model is invoked.

These tests establish safe blocking at ambiguous admission boundaries. They do
not establish automatic convergence for ownerless or never-submitted attempts.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest

from admission import digest, initialize
from git_journal import GitJournal
from private_controller import PrivateController, TrustedStore


class NoLaunchBackend:
    def __init__(self, store, crash=False):
        self.store, self.crash = store, crash

    def qualify(self, plan, contract):
        # Fixture substitution: production qualification is not exercised here.
        pass

    def submit(self, plan, contract):
        if self.crash:
            os.kill(os.getpid(), signal.SIGKILL)
        self.store.create('unexpected-submit.json', {'unit': plan['unit']})
        raise AssertionError('Acquisition replay reached submission')

    def recover_invocation(self, plan, contract, owner):
        raise FileNotFoundError('Fixture has no submitted native invocation')


def controller(root, stage=None):
    root = Path(root)

    class CrashStore(TrustedStore):
        def create(self, name, value):
            if stage == 'before-owner' and name == 'active-owner.json':
                os.kill(os.getpid(), signal.SIGKILL)
            super().create(name, value)

    class CrashJournal(GitJournal):
        def publish(self, expected, state):
            revision = super().publish(expected, state)
            if stage == 'after-admission' and state['attempts']:
                os.kill(os.getpid(), signal.SIGKILL)
            return revision

    store = CrashStore(root/'control', owner_uid=os.getuid())
    contract = json.loads((root/'contract.json').read_text())
    journal = CrashJournal(root/'work', str(root/'journal.git'), digest(contract))
    return PrivateController(store, journal, NoLaunchBackend(store, stage == 'after-owner'))


class AcquisitionProcessRecovery(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root/'control').mkdir(mode=0o700)
        self.store = TrustedStore(self.root/'control', owner_uid=os.getuid())
        self.store.create('credential-stream.lock', {})
        contract = {'kind': 'model-free-acquisition-fixture', 'prompt': 'No launch permitted'}
        self.key = digest(contract)
        (self.root/'contract.json').write_text(json.dumps(contract))
        (self.root/'unrelated.txt').write_bytes(b'preserve unrelated work\n')
        for args in (['git', 'init', '--bare', str(self.root/'journal.git')],
                     ['git', 'init', str(self.root/'work')]):
            subprocess.run(args, check=True, capture_output=True)
        self.store.create(self.key+'.approval.json',
                          {'contract': contract, 'approval_ref': 'model-free-test-only'})
        controller(self.root).journal.publish(None, initialize(self.key))

    def check_crash(self, stage, owner_expected):
        script = "from test_acquisition_recovery import controller;import sys;controller(sys.argv[1],sys.argv[2]).start(run_id=1,run_attempt=1,model_seconds=600,active_seconds=1200)"
        result = subprocess.run([sys.executable, '-c', script, str(self.root), stage],
                                cwd=Path(__file__).resolve().parent,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, -signal.SIGKILL, result.stderr)
        fresh = controller(self.root)
        revision, state = fresh.journal.read()
        self.assertEqual(len(state['attempts']), 1)
        attempt = state['attempts'][0]
        self.assertEqual((attempt['status'], attempt['model_seconds'], attempt['active_seconds']),
                         ('reserved', 600, 1200))
        if owner_expected:
            owner = self.store.read('active-owner.json')
            self.assertEqual(owner['reservation_revision'], revision)
            self.assertEqual(owner['contract_digest'], self.key)
        else:
            with self.assertRaises(FileNotFoundError):
                self.store.read('active-owner.json')
        # Restart in another process: it may inspect but cannot replay or refund.
        probe = """from test_acquisition_recovery import controller
import sys,json
c=controller(sys.argv[1]);before=c.journal.read();errors=[]
for action in (lambda:c.start(run_id=2,run_attempt=1,model_seconds=600,active_seconds=1200),c.reconcile):
 try:action();raise AssertionError('Ambiguous acquisition proceeded')
 except (ValueError,FileNotFoundError) as error:errors.append(type(error).__name__)
assert c.journal.read()==before
print(json.dumps(errors))
"""
        result = subprocess.run([sys.executable, '-c', probe, str(self.root)],
                                cwd=Path(__file__).resolve().parent,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), ['ValueError', 'FileNotFoundError'])
        self.assertEqual(fresh.journal.read(), (revision, state))
        with self.assertRaises(FileNotFoundError):
            self.store.read('unexpected-submit.json')
        self.assertEqual((self.root/'unrelated.txt').read_bytes(), b'preserve unrelated work\n')

    def test_durable_admission_before_response_blocks_replay(self):
        self.check_crash('after-admission', False)

    def test_admission_readback_before_owner_blocks_replay(self):
        self.check_crash('before-owner', False)

    def test_owner_before_native_submit_blocks_replay(self):
        self.check_crash('after-owner', True)
