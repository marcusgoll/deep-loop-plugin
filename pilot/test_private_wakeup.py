import unittest
import test_private_controller as fixtures
from private_wakeup import tick


class WakeupTests(unittest.TestCase):
    stop = fixtures.PrivateControllerTests.stop
    def setUp(self):
        fixtures.PrivateControllerTests.setUp(self)
        self.contract['wakeup'] = {'model_seconds':600,'active_seconds':1200}
        # Rebuild explicit enrollment fixture for this distinct frozen contract.
        from test_private_controller import FixtureJournal
        from private_controller import PrivateController
        self.journal = FixtureJournal(self.contract)
        self.controller = PrivateController(self.store,self.journal,self.backend)
        self.controller.enroll(self.contract,'explicit-wakeup-fixture')
    def enable(self):
        self.store.create('enabled-outcome.json',{'contract_digest':self.journal.contract_digest})
    def tick(self):
        return tick(self.store,lambda contract_digest:self.controller)
    def test_disabled_never_enrolls_or_launches(self):
        self.assertEqual(self.tick(),'disabled')
        self.assertEqual(self.backend.submissions,[])
    def test_wakeup_submits_once_reconciles_then_resumes_exact_session(self):
        self.enable()
        self.assertEqual(self.tick(),'submitted_once')
        self.assertEqual(self.tick(),'wait_for_predecessor')
        self.stop()
        self.assertEqual(self.tick(),'finished_without_verified_progress')
        self.assertEqual(len(self.backend.submissions),1)
        self.assertEqual(self.tick(),'submitted_once')
        self.assertEqual(self.backend.submissions[-1]['session_id'],self.backend.session_id)
        self.assertEqual(self.tick(),'finished_without_verified_progress')
        self.assertEqual(self.tick(),'stopped_limits')
        self.assertEqual(len(self.backend.submissions),2)
    def test_acceptance_stops_dispatch_at_trusted_delivery_boundary(self):
        self.enable()
        self.controller.verifier = lambda contract, owner:{'contract_digest':self.journal.contract_digest,'artifact':'exact'}
        self.tick()
        self.stop()
        self.assertEqual(self.tick(),'finished_with_verified_progress')
        self.assertEqual(self.tick(),'ready_for_trusted_delivery')
        self.assertEqual(len(self.backend.submissions),1)
    def test_selected_contract_drift_rejected_before_dispatch(self):
        self.enable()
        with self.assertRaises(ValueError):tick(self.store,lambda key:self.controller,expected_contract_digest='a'*64)
        self.assertEqual(self.backend.submissions,[])
    def test_short_window_blocks_dispatch_but_preserves_terminal_acceptance(self):
        self.enable()
        self.assertEqual(tick(self.store,lambda key:self.controller,active_window_remaining=1199),'stopped_insufficient_execution_window')
        self.controller.verifier=lambda contract,owner:{'contract_digest':self.journal.contract_digest}
        self.tick();self.stop();self.tick()
        self.assertEqual(tick(self.store,lambda key:self.controller,active_window_remaining=1),'ready_for_trusted_delivery')

    def test_missing_session_blocks_fresh_replacement(self):
        self.enable()
        self.backend.session_id = None
        self.tick()
        self.stop()
        self.tick()
        self.assertEqual(self.tick(),'blocked_missing_session')
        self.assertEqual(len(self.backend.submissions),1)

if __name__ == '__main__': unittest.main()
