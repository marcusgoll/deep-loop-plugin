from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import copy
import os
import subprocess
import tempfile
import threading
import unittest

from admission import credit_task, digest, finish, initialize, reserve
from git_journal import GitJournal
from private_controller import PrivateController, TrustedStore


class GitJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.remote = root/"durable.git"
        subprocess.run(["git", "init", "--bare", str(self.remote)],
                       check=True, capture_output=True)
        self.clients = []
        self.contract = digest({"fixture": True})
        for name in ("first", "restarted"):
            work = root/name
            subprocess.run(["git", "init", str(work)], check=True, capture_output=True)
            self.clients.append(GitJournal(work, str(self.remote), self.contract))

    def reserved(self, state):
        return reserve(state, self.contract, run_id=1, run_attempt=1,
                       model_seconds=600, active_seconds=1200)

    def test_batch_authenticates_saved_states_against_current_remote(self):
        first, restarted = self.clients
        original = initialize(self.contract, workflow=True)
        initial = first.publish(None, original)
        reserved = self.reserved(original)
        reservation = first.publish(initial, reserved)
        finished = finish(reserved, self.contract, run_id=1, run_attempt=1)
        stopped = first.publish(reservation, finished)
        credited = credit_task(finished, self.contract, run_id=1, run_attempt=1,
                               progress_receipt=digest('verified batch task'))
        current = first.publish(stopped, credited)
        self.assertEqual(restarted.verify_histories([
            (initial, original), (stopped, finished), (current, credited)
        ]), (current, credited))

    def credited_controller(self, count=3):
        control = Path(self.temp.name).resolve()/'control'
        control.mkdir(mode=0o700)
        store = TrustedStore(control, owner_uid=os.getuid())
        store.create('credential-stream.lock', {})
        journal = self.clients[0]
        state = initialize(self.contract, workflow=True)
        revision = journal.publish(None, state)
        histories = []
        for run_id in range(1, count+1):
            state = reserve(state, self.contract, run_id=run_id, run_attempt=1,
                            model_seconds=600, active_seconds=1200)
            revision = journal.publish(revision, state)
            state = finish(state, self.contract, run_id=run_id, run_attempt=1)
            revision = journal.publish(revision, state)
            progress = digest({'verified task': run_id})
            state = credit_task(state, self.contract, run_id=run_id, run_attempt=1,
                                progress_receipt=progress)
            revision = journal.publish(revision, state)
            unit = f'deep-loop-pilot-{self.contract}-{run_id}-1'
            owner = {'contract_digest': self.contract, 'unit': unit}
            intent = {'owner': owner, 'after': state, 'progress_identity': progress}
            store.create(unit+'.task-credit-intent.json', intent)
            store.create(unit+'.task-credit.json', {
                'owner': owner, 'intent_digest': digest(intent),
                'journal_revision': revision, 'progress_identity': progress,
                'progress_credit_assigned': True, 'parent_accepted': False})
            histories.append((revision, copy.deepcopy(state)))
        controller = PrivateController.__new__(PrivateController)
        controller.store, controller.journal = store, journal
        controller.contract_digest = self.contract
        return controller, histories

    def test_credit_guard_rejects_record_changed_after_history_authentication(self):
        controller, histories = self.credited_controller()
        latest = histories[-1][0]
        original = controller.journal._git
        triggered = []
        def late_record_change(*args, **kwargs):
            result = original(*args, **kwargs)
            if args == ('merge-base', '--is-ancestor', latest, latest):
                name = f'deep-loop-pilot-{self.contract}-3-1.task-credit.json'
                changed = controller.store.read(name)
                changed['parent_accepted'] = True
                controller.store.remove(name)
                controller.store.create(name, changed)
                triggered.append(True)
            return result
        controller.journal._git = late_record_change
        with controller.store.lock():
            with self.assertRaisesRegex(ValueError, 'credit.*changed'):
                controller._require_no_pending_task_credit()
        self.assertEqual(triggered, [True])

    def test_batch_rejects_remote_advance_before_closing_read(self):
        controller, histories = self.credited_controller(count=1)
        restarted = self.clients[1]
        original = restarted._git
        triggered = []
        def remote_advance(*args, **kwargs):
            result = original(*args, **kwargs)
            if args[0] == 'merge-base' and not triggered:
                triggered.append(True)
                revision, state = controller.journal.read()
                next_state = reserve(state, self.contract, run_id=2, run_attempt=1,
                                     model_seconds=600, active_seconds=1200)
                controller.journal.publish(revision, next_state)
            return result
        restarted._git = remote_advance
        with self.assertRaisesRegex(ValueError, 'changed during batch'):
            restarted.verify_histories(histories)
        self.assertEqual(triggered, [True])

    def test_batch_reads_a_fresh_remote_on_each_call(self):
        controller, histories = self.credited_controller(count=1)
        restarted = self.clients[1]
        self.assertEqual(restarted.verify_histories(histories), histories[-1])
        revision, state = controller.journal.read()
        next_state = reserve(state, self.contract, run_id=2, run_attempt=1,
                             model_seconds=600, active_seconds=1200)
        current = controller.journal.publish(revision, next_state)
        self.assertEqual(restarted.verify_histories(histories), (current, next_state))

    def test_batch_rejects_substituted_saved_state(self):
        _, histories = self.credited_controller()
        changed = copy.deepcopy(histories)
        changed[1][1]['attempts'][0]['model_seconds'] = 599
        with self.assertRaisesRegex(ValueError, 'historical revision differs'):
            self.clients[1].verify_histories(changed)

    def test_batch_rejects_sibling_history_with_identical_state(self):
        controller, histories = self.credited_controller(count=1)
        restarted = self.clients[1]
        current, state = restarted.read()
        journal = controller.journal
        initial = journal._git('rev-list', '--max-parents=0', current)
        sibling = journal._git('commit-tree', current+'^{tree}', '-p', initial,
                               data='Injected sibling with identical journal bytes\n')
        journal._git('push', '--force', '--', str(self.remote), sibling+':'+journal.ref)
        self.assertEqual(restarted.read(), (sibling, state))
        with self.assertRaises(subprocess.CalledProcessError):
            restarted.verify_histories(histories)

    def test_batch_rejects_removed_remote_credit_history(self):
        controller, histories = self.credited_controller()
        restarted = self.clients[1]
        restarted.read()  # Retain the formerly published object locally.
        subprocess.run(['git', '--git-dir='+str(self.remote), 'update-ref',
                        controller.journal.ref, histories[-2][0]],
                       check=True, capture_output=True)
        with self.assertRaises(subprocess.CalledProcessError):
            restarted.verify_histories(histories)

    def test_batch_rejects_invalid_group_before_remote_access(self):
        journal = self.clients[0]  # No journal has been enrolled.
        valid = ('a'*40, initialize(self.contract))
        for group in ([], [valid]*4, [None], [('bad revision', valid[1])],
                      [('a'*40, {})]):
            with self.subTest(group=group), self.assertRaises(ValueError):
                journal.verify_histories(group)

    def test_credit_guard_rejects_new_intent_during_history_authentication(self):
        controller, histories = self.credited_controller()
        original = controller.journal._git
        triggered = []
        def new_pending_intent(*args, **kwargs):
            result = original(*args, **kwargs)
            if args == ('merge-base', '--is-ancestor', histories[-1][0], histories[-1][0]):
                controller.store.create(f'deep-loop-pilot-{self.contract}-4-1.task-credit-intent.json', {})
                triggered.append(True)
            return result
        controller.journal._git = new_pending_intent
        with controller.store.lock(), self.assertRaisesRegex(ValueError, 'credit.*changed'):
            controller._require_no_pending_task_credit()
        self.assertEqual(triggered, [True])

    def test_credit_guard_blocks_missing_completion_receipt(self):
        controller, _ = self.credited_controller()
        controller.store.remove(f'deep-loop-pilot-{self.contract}-3-1.task-credit.json')
        with controller.store.lock(), self.assertRaisesRegex(ValueError, 'Pending task credit'):
            controller._require_no_pending_task_credit()

    def test_credit_guard_accepts_batch_and_legacy_journal(self):
        controller, histories = self.credited_controller()
        with controller.store.lock():
            controller._require_no_pending_task_credit()
            controller.journal.verify_histories = None
            controller._require_no_pending_task_credit()
        self.assertEqual(controller.journal.read(), histories[-1])

    def test_late_authority_expiry_blocks_actual_remote_push(self):
        first,restarted=self.clients
        original=initialize(self.contract)
        revision=first.publish(None,original)
        def expired():raise ValueError('fixture publication window expired')
        with self.assertRaisesRegex(ValueError,'window expired'):
            first.publish(revision,self.reserved(original),before_publish=expired)
        self.assertEqual(restarted.read(),(revision,original))

    def test_workflow_credit_appends_event_without_attempt_rewrite(self):
        first,restarted=self.clients
        revision=first.publish(None,initialize(self.contract,workflow=True))
        _,state=first.read();state=self.reserved(state);revision=first.publish(revision,state)
        state=finish(state,self.contract,run_id=1,run_attempt=1);revision=first.publish(revision,state)
        credited=credit_task(state,self.contract,run_id=1,run_attempt=1,progress_receipt=digest('approved task'))
        saved_revision=first.publish(revision,credited)
        self.assertEqual(restarted.read(),(saved_revision,credited))
        self.assertEqual(credited['attempts'],state['attempts'])
        self.assertEqual(restarted.verify_history(saved_revision,credited),(saved_revision,credited))
        with self.assertRaises(ValueError):restarted.verify_history(revision,credited)
        next_state=reserve(credited,self.contract,run_id=2,run_attempt=1,model_seconds=600,active_seconds=1200)
        next_revision=first.publish(saved_revision,next_state)
        self.assertEqual(restarted.verify_history(saved_revision,credited),(next_revision,next_state))
        with self.assertRaises(ValueError):first.publish(revision,credited)
        altered={**credited,'task_credits':[]}
        with self.assertRaises(ValueError):first.publish(saved_revision,altered)

    def test_durable_prelaunch_charge_survives_workspace_loss(self):
        first, restarted = self.clients
        old = first.publish(None, initialize(self.contract))
        _, state = first.read()
        new = first.publish(old, self.reserved(state))
        observed, saved = restarted.read()
        self.assertEqual(observed, new)
        self.assertEqual(saved["attempts"][0]["model_seconds"], 600)
        with self.assertRaises(ValueError):
            self.reserved(saved)

    def test_stale_writer_and_history_reset_rejected(self):
        first, second = self.clients
        old = first.publish(None, initialize(self.contract))
        _, state = second.read()
        first.publish(old, self.reserved(state))
        with self.assertRaises(ValueError):
            second.publish(old, self.reserved(state))
        current, saved = second.read()
        with self.assertRaises(ValueError):
            second.publish(current, initialize(self.contract))
        with self.assertRaises(subprocess.CalledProcessError):
            second.publish(None, initialize(self.contract))

    def test_finish_preserves_reservation_and_missing_state_blocks(self):
        first, second = self.clients
        with self.assertRaises(subprocess.CalledProcessError):
            second.read()
        old = first.publish(None, initialize(self.contract))
        _, state = first.read()
        head = first.publish(old, self.reserved(state))
        _, state = second.read()
        done = finish(state, self.contract, run_id=1, run_attempt=1)
        second.publish(head, done)
        _, saved = first.read()
        self.assertEqual(saved, done)
        self.assertEqual(saved["attempts"][0]["active_seconds"], 1200)

    def test_competing_sibling_pushes_have_one_winner(self):
        self.race(False)

    def test_duplicate_identical_dispatches_have_one_winner(self):
        self.race(True)

    def race(self, identical):
        first, second = self.clients
        old = first.publish(None, initialize(self.contract))
        barrier = threading.Barrier(2)

        class RacingJournal(GitJournal):
            def _git(self, *args, data=None):
                if args[0] == "push":
                    barrier.wait(timeout=10)
                return super()._git(*args, data=data)

        clients = [RacingJournal(c.workspace, c.remote, c.contract_digest)
                   for c in (first, second)]
        def compete(pair):
            index, client = pair
            _, state = client.read()
            update = reserve(state, self.contract, run_id=1 if identical else index+1, run_attempt=1,
                             model_seconds=600, active_seconds=1200)
            try:
                return client.publish(old, update)
            except subprocess.CalledProcessError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(compete, enumerate(clients)))
        self.assertEqual(sum(result is not None for result in results), 1)
        _, saved = first.read()
        self.assertEqual(len(saved["attempts"]), 1)


if __name__ == "__main__":
    unittest.main()
