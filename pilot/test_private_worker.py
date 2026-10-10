import unittest
from unittest.mock import patch
import test_private_controller as fixtures
from private_worker import run,qualify_service,build_controller
from github_transport import UncertainAPI
from worker_units import units

class WorkerTests(unittest.TestCase):
    stop=fixtures.PrivateControllerTests.stop
    def setUp(self):
        fixtures.PrivateControllerTests.setUp(self)
        self.store.create('enabled-outcome.json',{'contract_digest':self.journal.contract_digest})
    def test_owner_wait_is_one_bounded_transition(self):
        self.controller.start(run_id=1,run_attempt=1,model_seconds=600,active_seconds=1200)
        with patch('private_worker.tick',return_value='wait_for_predecessor') as tick:
            self.assertEqual(run(self.store,lambda key:self.controller,window=lambda *a:2000),'wait_for_predecessor')
        self.assertEqual(tick.call_count,1)
    def test_short_remaining_window_never_dispatches(self):
        with patch('private_worker.tick',return_value='stopped_insufficient_execution_window') as tick:
            self.assertEqual(run(self.store,lambda key:self.controller,window=lambda *a:1199),'stopped_insufficient_execution_window')
            self.assertEqual(tick.call_args.kwargs['active_window_remaining'],1199)
            self.assertEqual(tick.call_args.kwargs['expected_contract_digest'],self.journal.contract_digest)
    def test_short_window_stops_even_reconciliation_without_new_tick(self):
        with patch('private_worker.tick') as tick:
            self.assertEqual(run(self.store,lambda key:self.controller,window=lambda *a:60),'stopped_execution_window')
            tick.assert_not_called()
    def test_delivery_transition_is_invoked_only_after_acceptance(self):
        from unittest.mock import Mock
        adapter=Mock();adapter.step.return_value='wait_for_trusted_delivery'
        with patch('private_worker.tick',return_value='ready_for_trusted_delivery'):
            self.assertEqual(run(self.store,lambda key:self.controller,window=lambda *a:2000,
                                 delivery_factory=lambda key:adapter),'wait_for_trusted_delivery')
        adapter.step.assert_called_once()
    def test_uncertain_delivery_waits_without_replaying_inside_job(self):
        from unittest.mock import Mock
        adapter=Mock();adapter.step.side_effect=UncertainAPI('Unknown response')
        with patch('private_worker.tick',return_value='ready_for_trusted_delivery'):
            self.assertEqual(run(self.store,lambda key:self.controller,window=lambda *a:2000,
                                 delivery_factory=lambda key:adapter),'wait_for_trusted_delivery')
        adapter.step.assert_called_once()

    def test_requires_native_service_identity(self):
        with patch.dict('os.environ',{},clear=True),patch('private_worker.subprocess.run') as process:
            with self.assertRaises(ValueError):qualify_service()
            process.assert_not_called()
    def test_unit_generation_pins_bundle_and_disables_service_restart(self):
        configuration=units('a'*64)
        service=configuration['deep-loop-private-worker.service']
        self.assertIn('bundle-'+('a'*64)+'/private_worker.py',service)
        self.assertIn('RuntimeMaxSec=45',service);self.assertIn('Restart=no',service)
        self.assertIn('ConditionPathExists=',service)

class WorkerConstructionTests(unittest.TestCase):
    stop=fixtures.PrivateControllerTests.stop
    def setUp(self):fixtures.PrivateControllerTests.setUp(self)
    def build(self):
        from types import SimpleNamespace
        with patch('private_worker.GitJournal',return_value=self.journal),\
                patch('private_worker.NativeBackend',return_value=self.backend),\
                patch('private_worker.ResumeVerifier',return_value=None),\
                patch('private_worker.pwd.getpwnam',return_value=SimpleNamespace(pw_uid=123)):
            return build_controller(self.store,self.journal.contract_digest)
    def test_frozen_construction_needs_no_helper_and_preserves_behavior(self):
        controller=self.build()
        self.assertIs(controller.workflow_gate.store,self.store)
        self.assertIsNone(controller.ready_workflow_tasks())
    def test_native_and_controller_share_the_same_gate(self):
        from types import SimpleNamespace
        with patch('private_worker.GitJournal',return_value=self.journal),\
                patch('private_worker.ResumeVerifier',return_value=None),\
                patch('private_worker.pwd.getpwnam',return_value=SimpleNamespace(pw_uid=123)):
            controller=build_controller(self.store,self.journal.contract_digest)
        self.assertIs(controller.native_verifier.store,self.store)
        self.assertEqual(controller.native_verifier.key,self.journal.contract_digest)
        self.assertIs(controller.backend.workflow_gate,controller.workflow_gate)
        self.assertIs(controller.workflow_gate.helper.store,self.store)

    def test_workflow_cannot_use_missing_helper_configuration(self):
        controller=self.build()
        self.store.create(self.journal.contract_digest+'.workflow.json',{})
        with self.assertRaises((ValueError,FileNotFoundError)):
            controller.ready_workflow_tasks()
        self.assertEqual(self.backend.submissions,[])
    def test_owned_cleanup_does_not_resolve_helper_configuration(self):
        self.controller.start(run_id=1,run_attempt=1,model_seconds=600,active_seconds=1200)
        controller=self.build()
        with patch.object(controller.workflow_gate.helper,'_verify',side_effect=AssertionError('cleanup consulted helper')):
            self.assertEqual(controller.reconcile(),'wait_for_predecessor')
            self.stop()
            self.assertEqual(controller.reconcile(),'finished_without_verified_progress')
        self.assertEqual(len(self.backend.submissions),1)

    def test_revocation_stops_owned_attempt_without_helper_authority(self):
        from test_authority import RevocationBackend
        self.backend=RevocationBackend();self.controller.backend=self.backend
        self.controller.start(run_id=1,run_attempt=1,model_seconds=600,active_seconds=1200)
        controller=self.build()
        with patch.object(controller.workflow_gate.helper,'_verify',side_effect=AssertionError('revocation consulted helper')),\
                patch('private_controller.os.geteuid',return_value=0):
            result=controller.revoke(approval_ref='fixture revocation',reason='Stop fixture')
        self.assertIsInstance(result,dict)
        self.assertEqual(self.journal.state['attempts'][0]['status'],'finished')
        self.assertEqual(len(self.backend.submissions),1)

if __name__=='__main__':unittest.main()
