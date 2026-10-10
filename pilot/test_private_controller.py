import copy
import os
from pathlib import Path
import tempfile
import subprocess
import unittest

from admission import digest, initialize
from private_controller import PrivateController, TrustedStore
from git_journal import GitJournal

SESSION = '12345678-1234-4234-8234-123456789012'

class FixtureJournal:
    def __init__(self, contract):
        self.contract_digest = digest(contract)
        self.state = None
        self.revision = None
        self.uncertain = False
    def read(self):
        if self.state is None: raise FileNotFoundError('No enrolled journal')
        return self.revision, copy.deepcopy(self.state)
    def publish(self, expected, state, *, before_publish=None):
        if expected != self.revision: raise ValueError('Stale journal')
        if before_publish is not None:before_publish()
        self.state = copy.deepcopy(state)
        self.revision = digest({'state': state, 'parent': expected})
        if not hasattr(self,'history'):self.history={}
        self.history[self.revision]=copy.deepcopy(self.state)
        if self.uncertain: raise OSError('Uncertain publication')
        return self.revision

    def verify_history(self, revision, expected):
        if getattr(self,'history',{}).get(revision) != expected:
            raise ValueError('Journal historical revision differs')
        if (self.state['attempts'][:len(expected['attempts'])] != expected['attempts'] or
                self.state.get('task_credits',[])[:len(expected.get('task_credits',[]))] != expected.get('task_credits',[])):
            raise ValueError('Journal credited history missing or rewritten')
        return self.read()

class FixtureBackend:
    def __init__(self):
        self.submissions = []
        self.failure = False
        self.active = True
        self.empty = False
        self.invocation = 'a' * 32
        self.qualified = True
        self.session_id = SESSION
    def qualify(self, plan, contract):
        if not self.qualified: raise ValueError('Unqualified effective policy')
    def submit(self, plan, contract):
        self.submissions.append(plan)
        if self.failure: raise OSError('Submission response lost')
        return self.invocation
    def observe(self, unit, invocation):
        return {'unit': unit, 'invocation_id': self.invocation,
                'active_state': 'active' if self.active else 'inactive',
                'cgroup_empty': self.empty, 'ownership_verified': True}, self.session_id

class PrivateControllerTests(unittest.TestCase):
    def setUp(self):
        # macOS canonical /private/tmp and Linux /tmp are disposable fixtures.
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        self.store = TrustedStore(root, owner_uid=os.getuid())
        self.store.create('credential-stream.lock', {})
        self.contract = {'prompt': 'Disposable fixture only', 'source': 'frozen'}
        self.journal = FixtureJournal(self.contract)
        self.backend = FixtureBackend()
        self.controller = PrivateController(self.store, self.journal, self.backend)
        self.controller.enroll(self.contract, 'human-fixture-approval')
    def start(self, **kwargs):
        return self.controller.start(run_id=1, run_attempt=1, model_seconds=600, active_seconds=1200, **kwargs)
    def stop(self):
        self.backend.active = False
        self.backend.empty = True
    def test_missing_approval_and_qualification_never_submit_or_charge(self):
        self.backend.qualified = False
        with self.assertRaises(ValueError): self.start()
        self.assertEqual(self.journal.state['attempts'], [])
        self.store.remove(self.journal.contract_digest + '.approval.json')
        with self.assertRaises(FileNotFoundError): self.start()
        self.assertEqual(self.backend.submissions, [])
    def test_reservation_and_intent_precede_submit(self):
        original = self.backend.submit
        def inspect(plan, contract):
            owner = self.store.read('active-owner.json')
            self.assertEqual(owner['reservation_revision'], self.journal.revision)
            self.assertEqual(self.journal.state['attempts'][-1]['status'], 'reserved')
            return original(plan, contract)
        self.backend.submit = inspect
        self.start()
        with self.assertRaises(ValueError): self.start()
        self.assertEqual(len(self.backend.submissions), 1)
    def test_uncertain_submit_blocks_restart_and_other_contract(self):
        self.backend.failure = True
        with self.assertRaises(OSError): self.start()
        restarted = PrivateController(self.store, self.journal, self.backend)
        with self.assertRaises(ValueError):
            restarted.start(run_id=2, run_attempt=1, model_seconds=600, active_seconds=1200)
        with self.assertRaises(FileNotFoundError): restarted.reconcile()
        other = FixtureJournal({'prompt': 'different'})
        self.store.create(other.contract_digest + '.approval.json', {'contract': {'prompt': 'different'}, 'approval_ref': 'other-fixture'})
        other.publish(None, initialize(other.contract_digest))
        with self.assertRaises(ValueError):
            PrivateController(self.store, other, self.backend).start(run_id=1, run_attempt=1, model_seconds=600, active_seconds=1200)
        self.assertEqual(len(self.backend.submissions), 1)
    def test_uncertain_admission_blocks_launch_after_restart(self):
        self.journal.uncertain = True
        with self.assertRaises(OSError): self.start()
        self.journal.uncertain = False
        with self.assertRaises(ValueError): self.start()
        self.assertEqual(self.backend.submissions, [])
    def test_recovery_binds_session_and_preserves_charge(self):
        self.start()
        self.assertEqual(self.controller.reconcile(), 'wait_for_predecessor')
        self.stop()
        self.backend.empty = False
        self.assertEqual(self.controller.reconcile(), 'wait_for_predecessor')
        self.backend.empty = True
        self.assertEqual(self.controller.reconcile(), 'finished_without_verified_progress')
        self.assertEqual(self.journal.state['attempts'][0]['model_seconds'], 600)
        self.assertEqual(self.journal.state['attempts'][0]['status'], 'finished')
        self.controller.start(run_id=2, run_attempt=1, model_seconds=600, active_seconds=1200, session_id=SESSION)
        self.assertEqual(self.backend.submissions[-1]['command'][-3:], ['resume', SESSION, '-'])
        self.assertEqual(self.controller.reconcile(), 'finished_without_verified_progress')
    def test_changed_invocation_and_unbound_session_block(self):
        with self.assertRaises(FileNotFoundError): self.start(session_id=SESSION)
        self.start()
        self.stop()
        self.backend.invocation = 'b'*32
        with self.assertRaises(ValueError): self.controller.reconcile()
        self.assertEqual(self.journal.state['attempts'][0]['status'], 'reserved')
    def test_no_progress_limit_survives_controller_restart(self):
        for run in (1, 2):
            self.backend.session_id = None
            self.backend.active = True
            self.backend.empty = False
            self.controller.start(run_id=run, run_attempt=1, model_seconds=600, active_seconds=1200)
            self.stop()
            self.controller.reconcile()
            self.controller = PrivateController(self.store, self.journal, self.backend)
        with self.assertRaises(ValueError):
            self.controller.start(run_id=3, run_attempt=1, model_seconds=600, active_seconds=1200)
        self.assertEqual(len(self.backend.submissions), 2)
    def test_lock_and_immutable_authority(self):
        with self.store.lock():
            with self.assertRaises(BlockingIOError):
                with self.store.lock(): pass
        with self.assertRaises(FileExistsError):
            self.controller.enroll(self.contract, 'replacement')
        self.assertEqual(self.journal.state['attempts'], [])
    def test_changed_persisted_plan_blocks_reconciliation(self):
        self.start()
        self.stop()
        owner = self.store.read('active-owner.json')
        self.store.remove('active-owner.json')
        owner['plan_digest'] = 'f'*64
        self.store.create('active-owner.json', owner)
        with self.assertRaises(ValueError): self.controller.reconcile()
        self.assertEqual(self.journal.state['attempts'][0]['status'], 'reserved')
    def test_finish_before_owner_release_is_recoverable(self):
        self.backend.session_id = None
        self.start()
        self.stop()
        remove = self.store.remove
        def interrupted(name):
            if name == 'active-owner.json': raise OSError('Crash before release')
            return remove(name)
        self.store.remove = interrupted
        with self.assertRaises(OSError): self.controller.reconcile()
        revision = self.journal.revision
        self.store.remove = remove
        restarted = PrivateController(self.store, self.journal, self.backend)
        self.assertEqual(restarted.reconcile(), 'finished_without_verified_progress')
        self.assertEqual(self.journal.revision, revision)
        with self.assertRaises(FileNotFoundError): self.store.read('active-owner.json')
    def test_real_git_journal_reconciles_from_new_controller_workspace(self):
        remote = self.store.root/'journal.git'
        first = self.store.root/'first'
        restarted = self.store.root/'restarted'
        for args in (['git', 'init', '--bare', str(remote)], ['git', 'init', str(first)],
                     ['git', 'init', str(restarted)]):
            subprocess.run(args, check=True, capture_output=True)
        journal = GitJournal(first, str(remote), self.journal.contract_digest)
        journal.publish(None, initialize(journal.contract_digest))
        controller = PrivateController(self.store, journal, self.backend)
        controller.start(run_id=1, run_attempt=1, model_seconds=600, active_seconds=1200)
        self.stop()
        recovered = GitJournal(restarted, str(remote), journal.contract_digest)
        controller = PrivateController(self.store, recovered, self.backend)
        self.assertEqual(controller.reconcile(), 'finished_without_verified_progress')
        _, state = recovered.read()
        self.assertEqual(state['attempts'][0]['model_seconds'], 600)
        self.assertEqual(state['attempts'][0]['status'], 'finished')
    def test_verified_progress_is_stable_and_never_reused(self):
        evidence = {'contract_digest': self.journal.contract_digest, 'artifact': 'fixed-hash'}
        self.controller.verifier = lambda contract, owner: evidence
        self.start()
        self.assertEqual(self.controller.reconcile(), 'wait_for_predecessor')
        self.stop()
        self.assertEqual(self.controller.reconcile(), 'finished_with_verified_progress')
        receipt = self.journal.state['attempts'][0]['progress_receipt']
        self.assertEqual(self.store.read(receipt + '.progress.json'), evidence)
        self.controller.start(run_id=2, run_attempt=1, model_seconds=600, active_seconds=1200)
        self.assertEqual(self.controller.reconcile(), 'finished_without_verified_progress')
        self.assertIsNone(self.journal.state['attempts'][1]['progress_receipt'])
    def test_verified_finish_before_owner_release_recovers_without_verification_repeat(self):
        self.controller.verifier = lambda contract, owner: {'contract_digest': self.journal.contract_digest, 'artifact': 'fixed-hash'}
        self.start()
        self.stop()
        remove = self.store.remove
        self.store.remove = lambda name: (_ for _ in ()).throw(OSError('Crash'))
        with self.assertRaises(OSError): self.controller.reconcile()
        self.store.remove = remove
        restarted = PrivateController(self.store, self.journal, self.backend,
                                      verifier=lambda *args: self.fail('Repeated verification'))
        self.assertEqual(restarted.reconcile(), 'finished_with_verified_progress')

    def test_missing_progress_evidence_blocks_finished_owner_release(self):
        self.controller.verifier = lambda contract, owner: {'contract_digest': self.journal.contract_digest}
        self.start()
        self.stop()
        remove = self.store.remove
        self.store.remove = lambda name: (_ for _ in ()).throw(OSError('Crash'))
        with self.assertRaises(OSError): self.controller.reconcile()
        self.store.remove = remove
        progress = self.journal.state['attempts'][-1]['progress_receipt']
        remove(progress + '.progress.json')
        with self.assertRaises(FileNotFoundError): self.controller.reconcile()
        self.assertEqual(self.store.read('active-owner.json')['run_id'], 1)

    def test_uncertain_native_submit_is_adopted_without_replay(self):
        self.backend.failure = True
        with self.assertRaises(OSError): self.start()
        self.backend.recover_invocation = lambda plan, contract, owner: self.backend.invocation
        self.stop()
        self.assertEqual(self.controller.reconcile(), 'finished_without_verified_progress')
        self.assertEqual(len(self.backend.submissions), 1)
        self.assertEqual(self.journal.state['attempts'][0]['model_seconds'], 600)

    def test_missing_lock_never_recreates_ownership(self):
        self.store.remove('credential-stream.lock')
        with self.assertRaises(FileNotFoundError): self.start()
        self.assertEqual(self.backend.submissions, [])
    def test_symlink_and_hardlink_state_rejected(self):
        target = self.store.root/'target.json'
        target.write_text('{}')
        target.chmod(0o600)
        (self.store.root/'symlink.json').symlink_to(target)
        with self.assertRaises(OSError): self.store.read('symlink.json')
        os.link(target, self.store.root/'hardlink.json')
        with self.assertRaises(ValueError): self.store.read('hardlink.json')

if __name__ == '__main__': unittest.main()
