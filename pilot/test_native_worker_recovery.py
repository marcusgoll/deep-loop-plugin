import unittest
from unittest.mock import Mock,patch
import test_private_controller as fixtures


class NativeWorkerRecoveryTests(unittest.TestCase):
    def setUp(self):
        fixtures.PrivateControllerTests.setUp(self)
        self.prefix='fixture-owned-verifier'
        self.store.create('active-verifier.json',{'contract_digest':self.journal.contract_digest,'prefix':self.prefix})
        self.observed={'exit_code':0,'unit_result':'success','native':{'execution_finished':True,'cgroup_empty':True}}
        self.controller.recover_native_workflow_verification=Mock(return_value=self.observed)
        self.controller.prepare_native_workflow_publication=Mock()
        self.controller.publish_native_workflow_result=Mock()
        self.controller.cleanup_native_workflow_verification=Mock()

    def test_prepare_publish_cleanup_are_separate_wakeups_without_dispatch(self):
        self.assertEqual(self.controller.recover_pending_native_publication(),'prepared_native_verifier_publication')
        self.controller.publish_native_workflow_result.assert_not_called()
        self.store.create(self.prefix+'.publication-intent.json',{})
        self.assertEqual(self.controller.recover_pending_native_publication(),'recovered_native_verifier_publication')
        self.controller.cleanup_native_workflow_verification.assert_not_called()
        self.store.create(self.prefix+'.publication-complete.json',{})
        self.assertEqual(self.controller.recover_pending_native_publication(),'recovered_native_verifier_cleanup')
        self.assertEqual(self.backend.submissions,[])

    def test_running_verifier_waits_and_failed_verifier_cleans_without_publication(self):
        self.observed['native']['execution_finished']=False
        self.assertEqual(self.controller.recover_pending_native_publication(),'wait_for_native_verifier')
        self.controller.prepare_native_workflow_publication.assert_not_called()
        self.observed['native']['execution_finished']=True;self.observed['unit_result']='timeout'
        self.assertEqual(self.controller.recover_pending_native_publication(),'blocked_failed_native_verifier')
        self.controller.cleanup_native_workflow_verification.assert_called_once_with(self.prefix)
        self.controller.publish_native_workflow_result.assert_not_called()

    def test_existing_cleanup_intent_has_priority(self):
        self.store.create(self.prefix+'.cleanup-intent.json',{})
        self.assertEqual(self.controller.recover_pending_native_publication(),'recovered_native_verifier_cleanup')
        self.controller.recover_native_workflow_verification.assert_not_called()
        self.controller.prepare_native_workflow_publication.assert_not_called()

    def test_other_owner_and_absent_stream_do_not_take_over(self):
        self.store.remove('active-verifier.json')
        self.assertIsNone(self.controller.recover_pending_native_publication())
        self.store.create('active-verifier.json',{'contract_digest':'0'*64,'prefix':self.prefix})
        self.assertEqual(self.controller.recover_pending_native_publication(),'blocked_other_verifier_owner')
        self.controller.recover_native_workflow_verification.assert_not_called()

    def test_wakeup_returns_recovery_without_selection_or_submission(self):
        # Existing wakeup fixture supplies a separately approved schedule.
        import test_private_wakeup
        fixture=test_private_wakeup.WakeupTests('test_disabled_never_enrolls_or_launches')
        fixture.setUp();self.addCleanup(fixture.doCleanups);fixture.enable()
        fixture.controller.recover_pending_native_publication=Mock(return_value='wait_for_native_verifier')
        with patch.object(fixture.controller,'ready_workflow_tasks',side_effect=AssertionError('selected during recovery')):
            self.assertEqual(fixture.tick(),'wait_for_native_verifier')
        self.assertEqual(fixture.backend.submissions,[])
