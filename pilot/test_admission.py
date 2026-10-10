import json
import unittest

from admission import credit_task, digest, finish, initialize, reserve


CONTRACT = digest({"disposable": True})


class AdmissionTests(unittest.TestCase):
    def launch(self, journal, run=1, model=600, active=1200, attempt=1):
        return reserve(journal, CONTRACT, run_id=run, run_attempt=attempt,
                       model_seconds=model, active_seconds=active)

    def close(self, journal, run=1, progress=None, attempt=1):
        return finish(journal, CONTRACT, run_id=run, run_attempt=attempt,
                      progress_receipt=progress)

    def test_workflow_credit_is_append_only_unique_and_keeps_budget(self):
        state=self.close(self.launch(initialize(CONTRACT,workflow=True)))
        credit=digest({'approved_task':'one'})
        saved=credit_task(state,CONTRACT,run_id=1,run_attempt=1,progress_receipt=credit)
        self.assertEqual(state['attempts'],saved['attempts'])
        self.assertEqual(state['task_credits'],[])
        with self.assertRaises(ValueError):credit_task(saved,CONTRACT,run_id=1,run_attempt=1,progress_receipt=credit)
        second=self.close(self.launch(saved,2),2)
        with self.assertRaises(ValueError):credit_task(second,CONTRACT,run_id=2,run_attempt=1,progress_receipt=credit)
        third=self.launch(second,3)
        self.assertEqual(sum(a['model_seconds'] for a in third['attempts']),1800)
        with self.assertRaises(ValueError):self.launch(third,4)
        with self.assertRaises(ValueError):credit_task(self.close(self.launch(initialize(CONTRACT))),CONTRACT,run_id=1,run_attempt=1,progress_receipt=credit)

    def test_workflow_missing_credit_preserves_no_progress_stop(self):
        state=initialize(CONTRACT,workflow=True)
        for run in (1,2):state=self.close(self.launch(state,run),run)
        with self.assertRaises(ValueError):self.launch(state,3)
        with self.assertRaises(ValueError):credit_task(state,CONTRACT,run_id=1,run_attempt=1,progress_receipt=digest('old task'))

    def test_three_attempts_across_serialized_restarts_then_stop(self):
        state = initialize(CONTRACT)
        for run in range(1, 4):
            state = self.launch(json.loads(json.dumps(state)), run)
            state = self.close(state, run, digest({"verifier": run}))
        self.assertEqual(sum(a["model_seconds"] for a in state["attempts"]), 1800)
        self.assertEqual(sum(a["active_seconds"] for a in state["attempts"]), 3600)
        with self.assertRaises(ValueError):
            self.launch(state, 4)

    def test_crash_reservation_blocks_duplicate_and_other_writer(self):
        before = initialize(CONTRACT)
        after = self.launch(before)
        self.assertEqual(before["attempts"], [])
        for run in (1, 2):
            with self.assertRaises(ValueError):
                self.launch(json.loads(json.dumps(after)), run)

    def test_no_progress_stops_after_two(self):
        state = initialize(CONTRACT)
        for run in (1, 2):
            state = self.close(self.launch(state, run), run)
        with self.assertRaises(ValueError):
            self.launch(state, 3)

    def test_new_progress_resets_streak_not_reserved_time(self):
        state = self.close(self.launch(initialize(CONTRACT)))
        state = self.close(self.launch(state, 2), 2, digest({"new": 1}))
        self.assertEqual(len(self.launch(state, 3)["attempts"]), 3)

    def test_model_and_active_allowances_fail_independently(self):
        state = self.close(self.launch(initialize(CONTRACT), model=1700, active=1800))
        for model, active in ((101, 101), (1, 1801)):
            with self.assertRaises(ValueError):
                self.launch(state, 2, model=model, active=active)

    def test_same_run_rerun_counts_and_duplicate_identity_rejected(self):
        state = self.close(self.launch(initialize(CONTRACT)))
        with self.assertRaises(ValueError):
            self.launch(state)
        self.assertEqual(len(self.launch(state, attempt=2)["attempts"]), 2)

    def test_missing_changed_or_corrupt_state_never_resets(self):
        good = initialize(CONTRACT)
        bad_limits = json.loads(json.dumps(good)); bad_limits["limits"]["attempts"] = 4
        bad_digest = json.loads(json.dumps(good)); bad_digest["contract_digest"] = "f"*64
        for state in (None, {}, bad_limits, bad_digest):
            with self.assertRaises(ValueError):
                self.launch(state)

    def test_invalid_numbers_rejected(self):
        for n in (True, 0, -1, 1.5, "1"):
            with self.assertRaises(ValueError):
                self.launch(initialize(CONTRACT), model=n)

    def test_wrong_finish_and_reused_receipts_rejected(self):
        state = self.launch(initialize(CONTRACT))
        with self.assertRaises(ValueError):
            self.close(state, 2)
        proof = digest({"gate": 1})
        state = self.close(state, progress=proof)
        with self.assertRaises(ValueError):
            self.close(state)
        state = self.launch(state, 2)
        with self.assertRaises(ValueError):
            self.close(state, 2, proof)


if __name__ == "__main__":
    unittest.main()
