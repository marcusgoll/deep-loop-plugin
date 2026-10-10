from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import subprocess
import tempfile
import threading
import unittest

from admission import credit_task, digest, finish, initialize, reserve
from git_journal import GitJournal


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
