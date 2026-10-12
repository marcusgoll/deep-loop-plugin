import unittest
from unittest.mock import Mock
import test_private_controller as fixtures


class WorkflowAutoAdvanceTests(unittest.TestCase):
    def setUp(self):
        fixtures.PrivateControllerTests.setUp(self)
        self.key=self.journal.contract_digest;self.unit='deep-loop-pilot-'+self.key+'-1-1'
        self.owner={'contract_digest':self.key,'unit':self.unit,'run_id':1,'run_attempt':1}
        self.journal.state.update(schema=2,task_credits=[],attempts=[{'run_id':1,'run_attempt':1,'status':'finished'}])
        self.store.create(self.key+'.workflow.json',{'fixture':True})
        self.store.create(self.unit+'.workflow-attempt.json',{'owner':self.owner})
        self.selection={'task_id':'selected'}
        self.gate=Mock();self.gate._read.return_value=({'task_verifiers':{'selected':['V1','V2']}},{},{})
        self.gate.verification_plan.return_value={'definitions':[{'verifier':{'id':'V1'}},{'verifier':{'id':'V2'}}]}
        self.gate.helper.prerequisite_issues.side_effect=lambda state,ids:[] if ids==['V1'] else ['pending']
        self.controller._finished_workflow_context=Mock(return_value=(self.gate,self.selection,None,None,None))
        self.controller.start_native_workflow_verification=Mock()
        self.controller.record_workflow_task_proof=Mock()
        self.controller.accept_workflow_task=Mock()

    def test_only_unproved_verifier_is_started_using_full_plan_index(self):
        self.assertEqual(self.controller.advance_finished_workflow_task(),'submitted_native_workflow_verifier')
        self.controller.start_native_workflow_verification.assert_called_once_with(self.owner,1)
        self.controller.accept_workflow_task.assert_not_called()
        self.assertEqual(self.backend.submissions,[])

    def test_previously_run_stale_or_failed_proof_is_never_replayed(self):
        self.store.create(self.unit+'.verifier-1.intent.json',{})
        self.controller._verifier_cleanup_completion=Mock(return_value={'cleanup_only':True})
        self.assertEqual(self.controller.advance_finished_workflow_task(),'blocked_stale_or_failed_verifier_proof')
        self.controller.start_native_workflow_verification.assert_not_called()

    def test_proof_recording_and_acceptance_are_separate_actions(self):
        self.gate.helper.prerequisite_issues.side_effect=None;self.gate.helper.prerequisite_issues.return_value=[]
        self.assertEqual(self.controller.advance_finished_workflow_task(),'recorded_workflow_task_proof')
        self.controller.accept_workflow_task.assert_not_called()
        self.store.create(self.unit+'.task-proof.json',{})
        self.assertEqual(self.controller.advance_finished_workflow_task(),'accepted_workflow_task')
        self.controller.start_native_workflow_verification.assert_not_called()

    def test_credited_attempt_does_not_repeat_acceptance_or_verification(self):
        self.journal.state['task_credits']=[{'run_id':1,'run_attempt':1}]
        self.assertIsNone(self.controller.advance_finished_workflow_task())
        self.controller._finished_workflow_context.assert_not_called()
        self.controller.start_native_workflow_verification.assert_not_called()

    def test_active_verifier_fence_blocks_fresh_task_advance(self):
        self.store.create('active-verifier.json',{})
        with self.assertRaisesRegex(ValueError,'unreconciled verifier'):
            self.controller.advance_finished_workflow_task()
        self.controller.start_native_workflow_verification.assert_not_called()
