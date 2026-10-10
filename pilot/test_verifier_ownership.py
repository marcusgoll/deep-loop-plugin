import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from admission import digest
from private_controller import PrivateController,TrustedStore
from test_private_controller import FixtureBackend,FixtureJournal

class VerifierOwnershipTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.store=TrustedStore(Path(temp.name).resolve(),owner_uid=os.getuid())
        self.store.create('credential-stream.lock',{})
        self.contract={'prompt':'fixture','source':'frozen'}
        self.journal=FixtureJournal(self.contract);self.backend=FixtureBackend();self.native=Mock()
        self.controller=PrivateController(self.store,self.journal,self.backend,native_verifier=self.native)
        self.controller.enroll(self.contract,'fixture-approval');self.key=self.journal.contract_digest
        self.owner={'contract_digest':self.key,'unit':'deep-loop-pilot-'+self.key+'-1-1'}
        self.plan={'contract_digest':self.key,'source_owner':self.owner,'index':0,'unit':'deep-loop-pilot-'+'e'*64+'-1-1'}
        self.observation={'plan_digest':digest(self.plan),'invocation_id':'a'*32,
            'native':{'ownership_verified':True,'execution_finished':True,'cgroup_empty':True}}
        self.native.adopt.return_value=self.observation
        def submit(plan):
            self.store.create(self.owner['unit']+'.verifier-0.submit-intent.json',{'plan_digest':digest(plan)})
            return self.observation
        self.native.submit.side_effect=submit
        self.native.unsubmitted.return_value={'plan_digest':digest(self.plan),'submission_intent_absent':True,'account_empty':True,'native_dispatched':False}
        self.native.stop.return_value=self.observation
        self.gate=Mock();self.gate.verification_plan.return_value={'selection':{}}
    def dispatch(self):
        revision,state=self.journal.read()
        with patch.object(self.controller,'_finished_workflow_context',return_value=(self.gate,{},revision,state,{'invocation_id':'b'*32})),patch('native_verifier.launch_plan',return_value=self.plan):
            return self.controller.start_native_workflow_verification(self.owner,0)
    def test_response_loss_fences_other_dispatch_and_recovers_without_replay(self):
        original=self.native.submit.side_effect
        def lost(plan):
            original(plan)
            raise OSError('response lost')
        self.native.submit.side_effect=lost
        with self.assertRaises(OSError):self.dispatch()
        self.assertEqual(self.store.read('active-verifier.json')['plan_digest'],digest(self.plan))
        with self.assertRaisesRegex(ValueError,'unreconciled verifier'):self.dispatch()
        with self.assertRaisesRegex(ValueError,'unreconciled verifier'):
            self.controller.start(run_id=1,run_attempt=1,model_seconds=600,active_seconds=1200)
        self.assertEqual(self.journal.state['attempts'],[])
        self.assertEqual(self.controller.recover_native_workflow_verification(),self.observation)
        self.assertEqual(self.native.submit.call_count,1)
        self.assertTrue((self.store.root/'active-verifier.json').exists())
    def test_missing_stream_marker_still_fences_interrupted_preparation(self):
        self.dispatch();self.store.remove('active-verifier.json')
        with self.assertRaisesRegex(ValueError,'Pending native verifier'):self.controller._unowned()
    def test_changed_invocation_does_not_replace_protected_identity(self):
        self.dispatch();self.native.adopt.return_value={**self.observation,'invocation_id':'c'*32}
        with self.assertRaisesRegex(ValueError,'invocation changed'):self.controller.recover_native_workflow_verification()
    def test_revocation_stops_exact_verifier_and_preserves_stream_fence(self):
        self.dispatch()
        with patch('private_controller.os.geteuid',return_value=0):
            result=self.controller.revoke(approval_ref='fixture-revoke',reason='stop fixture')
        self.native.stop.assert_called_once_with(self.plan,'a'*32)
        self.assertEqual(self.journal.state['attempts'],[])
        self.assertTrue((self.store.root/'active-verifier.json').exists())
        self.assertEqual(result['contract_digest'],self.key)

    def test_pending_verifier_fences_proof_acceptance_credit_and_other_outcome(self):
        self.dispatch()
        for operation in (self.controller.record_workflow_task_proof,self.controller.accept_workflow_task,
                          self.controller.credit_workflow_task,self.controller.workflow_verification_plan):
            with self.subTest(operation=operation.__name__):
                with self.assertRaisesRegex(ValueError,'unreconciled verifier'):operation(self.owner)
        other_contract={'prompt':'another outcome','source':'frozen'}
        other_journal=FixtureJournal(other_contract)
        other=PrivateController(self.store,other_journal,self.backend)
        other.enroll(other_contract,'another-fixture-approval')
        with self.assertRaisesRegex(ValueError,'unreconciled verifier'):
            other.start(run_id=1,run_attempt=1,model_seconds=600,active_seconds=1200)
        self.assertEqual(other_journal.state['attempts'],[])

    def test_cleanup_releases_only_after_durable_completion_without_acceptance(self):
        self.dispatch();prefix=self.owner['unit']+'.verifier-0'
        result=self.controller.cleanup_native_workflow_verification(prefix)
        self.assertTrue(result['cleanup_only']);self.assertFalse(result['parent_accepted'])
        self.assertFalse((self.store.root/'active-verifier.json').exists())
        self.controller._verifier_unowned()
        self.assertEqual(self.controller.cleanup_native_workflow_verification(prefix),result)
        self.assertEqual(self.journal.state['attempts'],[])
        self.native.submit.assert_called_once()
    def test_cleanup_completion_failure_keeps_fence_and_exact_retry_recovers(self):
        self.dispatch();prefix=self.owner['unit']+'.verifier-0';original=self.store.create
        def fail(name,value):
            if name.endswith('.cleanup-complete.json'):raise OSError('completion failed')
            return original(name,value)
        with patch.object(self.store,'create',side_effect=fail):
            with self.assertRaises(OSError):self.controller.cleanup_native_workflow_verification(prefix)
        self.assertTrue((self.store.root/'active-verifier.json').exists())
        self.controller.cleanup_native_workflow_verification(prefix)
        self.controller._verifier_unowned()
        self.native.submit.assert_called_once()
    def test_nonempty_native_cleanup_keeps_fence(self):
        self.dispatch();prefix=self.owner['unit']+'.verifier-0'
        self.native.adopt.return_value={**self.observation,'native':{'ownership_verified':True,'execution_finished':False,'cgroup_empty':False}}
        with self.assertRaisesRegex(ValueError,'fresh ended empty'):self.controller.cleanup_native_workflow_verification(prefix)
        self.assertTrue((self.store.root/'active-verifier.json').exists())
    def test_completed_cleanup_retry_does_not_remove_another_stream(self):
        self.dispatch();prefix=self.owner['unit']+'.verifier-0'
        self.controller.cleanup_native_workflow_verification(prefix)
        another={'contract_digest':'f'*64,'prefix':'another','plan_digest':'e'*64}
        self.store.create('active-verifier.json',another)
        self.controller.cleanup_native_workflow_verification(prefix)
        self.assertEqual(self.store.read('active-verifier.json'),another)

    def test_interrupted_preparation_before_stream_marker_recovers_without_native_action(self):
        original=self.store.create
        def fail(name,value):
            if name=='active-verifier.json':raise OSError('marker interrupted')
            return original(name,value)
        with patch.object(self.store,'create',side_effect=fail):
            with self.assertRaises(OSError):self.dispatch()
        prefix=self.owner['unit']+'.verifier-0'
        completion=self.controller.cleanup_native_workflow_verification(prefix)
        self.assertTrue(completion['preparation_only'])
        self.assertIsNone(completion['invocation_id'])
        self.native.submit.assert_not_called();self.native.adopt.assert_not_called();self.native.stop.assert_not_called()
        self.controller._verifier_unowned()
        self.assertEqual(self.controller.cleanup_native_workflow_verification(prefix),completion)
    def test_preparation_cleanup_failure_retains_orphan_fence(self):
        original=self.store.create
        def fail_marker(name,value):
            if name=='active-verifier.json':raise OSError('marker interrupted')
            return original(name,value)
        with patch.object(self.store,'create',side_effect=fail_marker):
            with self.assertRaises(OSError):self.dispatch()
        prefix=self.owner['unit']+'.verifier-0'
        def fail_completion(name,value):
            if name.endswith('.cleanup-complete.json'):raise OSError('completion interrupted')
            return original(name,value)
        with patch.object(self.store,'create',side_effect=fail_completion):
            with self.assertRaises(OSError):self.controller.cleanup_native_workflow_verification(prefix)
        with self.assertRaisesRegex(ValueError,'Pending native verifier'):self.controller._verifier_unowned()
        self.controller.cleanup_native_workflow_verification(prefix)
        self.controller._verifier_unowned()
    def test_preparation_closed_then_dispatch_record_appears_blocks(self):
        self.native.submit.side_effect=OSError('before submission intent')
        with self.assertRaises(OSError):self.dispatch()
        prefix=self.owner['unit']+'.verifier-0'
        self.controller.cleanup_native_workflow_verification(prefix)
        self.store.create(prefix+'.submit-intent.json',{'plan_digest':digest(self.plan)})
        with self.assertRaisesRegex(ValueError,'acquired dispatch history'):self.controller._verifier_unowned()

    def make_orphan(self):
        original=self.store.create
        def fail(name,value):
            if name=='active-verifier.json':raise OSError('marker interrupted')
            return original(name,value)
        with patch.object(self.store,'create',side_effect=fail):
            with self.assertRaises(OSError):self.dispatch()
        return self.owner['unit']+'.verifier-0'

    def test_worker_closes_unsubmitted_orphan_once_without_replaying(self):
        self.make_orphan();before=self.journal.read()
        self.assertEqual(self.controller.recover_pending_native_publication(),'recovered_native_verifier_preparation_cleanup')
        self.assertIsNone(self.controller.recover_pending_native_publication())
        self.assertEqual(self.journal.read(),before)
        self.native.submit.assert_not_called();self.native.adopt.assert_not_called();self.native.stop.assert_not_called()
        self.controller._verifier_unowned()

    def test_missing_stream_with_submission_history_stays_fenced(self):
        prefix=self.make_orphan();self.store.create(prefix+'.submit-intent.json',{})
        self.assertEqual(self.controller.recover_pending_native_publication(),'blocked_missing_verifier_stream')
        self.native.unsubmitted.assert_not_called()
        with self.assertRaisesRegex(ValueError,'Pending native verifier'):self.controller._verifier_unowned()

    def test_ambiguous_orphan_preparations_are_not_cleaned(self):
        prefix=self.make_orphan();intent=self.store.read(prefix+'.intent.json')
        self.store.create(prefix[:-1]+'1.intent.json',intent)
        self.assertEqual(self.controller.recover_pending_native_publication(),'blocked_ambiguous_verifier_preparation')
        self.native.unsubmitted.assert_not_called()

    def test_orphan_plan_drift_blocks_before_cleanup_writes(self):
        prefix=self.make_orphan();intent=self.store.read(prefix+'.intent.json');intent['plan_digest']='0'*64
        self.store.remove(prefix+'.intent.json');self.store.create(prefix+'.intent.json',intent)
        with self.assertRaisesRegex(ValueError,'identity drift'):self.controller.recover_pending_native_publication()
        self.native.unsubmitted.assert_not_called()
        self.assertFalse((self.store.root/(prefix+'.cleanup-intent.json')).exists())
