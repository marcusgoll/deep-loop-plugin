import unittest
import deep_loop
import test_workflow_gate as graph_fixtures
import test_private_controller as controller_fixtures
from admission import initialize
from private_controller import PrivateController


class WorkflowDispatchTests(unittest.TestCase):
    def setUp(self):
        self.graph=graph_fixtures.WorkflowGateTests()
        self.graph.setUp();self.addCleanup(self.graph.doCleanups)
        g=self.graph
        g.store.create('credential-stream.lock',{})
        self.journal=controller_fixtures.FixtureJournal(g.contract)
        self.journal.publish(None,initialize(g.key))
        self.backend=controller_fixtures.FixtureBackend()
        self.controller=PrivateController(g.store,self.journal,self.backend,workflow_gate=g.gate)
    def start(self,task_id='dependent'):
        return self.controller.start(run_id=1,run_attempt=1,model_seconds=600,active_seconds=1200,task_id=task_id)
    def test_native_submission_has_protected_task_and_charge(self):
        owner=self.start()
        record=self.graph.store.read(owner['unit']+'.workflow-attempt.json')
        self.assertEqual(record['owner'],owner)
        self.assertEqual(record['selection']['task_id'],'dependent')
        self.assertEqual(len(self.backend.submissions),1)
        self.assertEqual(self.journal.state['attempts'][0]['model_seconds'],600)
        with self.assertRaises(ValueError):self.start('portable')
    def test_stale_prerequisite_blocks_before_charge_but_portable_dispatches(self):
        self.graph.f.source.write_text('drift')
        with self.assertRaises(ValueError):self.start()
        self.assertEqual(self.journal.state['attempts'],[])
        self.start('portable');self.assertEqual(len(self.backend.submissions),1)
    def test_gate_is_mandatory_when_binding_exists(self):
        self.controller.workflow_gate=None
        with self.assertRaises(ValueError):self.start()
        self.assertEqual(self.backend.submissions,[])
        self.assertEqual(self.journal.state['attempts'],[])
    def test_proof_drift_during_qualification_never_charges_or_submits(self):
        self.backend.qualify=lambda *args:self.graph.f.source.write_text('drift')
        with self.assertRaises(ValueError):self.start()
        self.assertEqual(self.journal.state['attempts'],[])
        self.assertEqual(self.backend.submissions,[])
    def test_drift_after_admission_preserves_charge_and_blocks_replay(self):
        publish=self.journal.publish
        def drift(expected,state):
            result=publish(expected,state)
            self.graph.f.source.write_text('drift')
            return result
        self.journal.publish=drift
        with self.assertRaises(ValueError):self.start()
        self.assertEqual(self.journal.state['attempts'][0]['model_seconds'],600)
        self.assertEqual(self.backend.submissions,[])
        restarted=PrivateController(self.graph.store,self.journal,self.backend,workflow_gate=self.graph.gate)
        with self.assertRaises(ValueError):restarted.start(run_id=2,run_attempt=1,model_seconds=600,active_seconds=1200,task_id='portable')
    def test_missing_binding_cannot_downgrade_workflow_acceptance(self):
        owner=self.start();calls=[]
        self.controller.verifier=lambda *args:calls.append(args) or {'contract_digest':self.graph.key}
        self.backend.active=False;self.backend.empty=True
        self.graph.store.remove(self.graph.key+'.workflow.json')
        with self.assertRaisesRegex(ValueError,'lost its protected enrollment'):
            self.controller.reconcile()
        self.assertEqual(calls,[])
        self.assertEqual(self.graph.store.read('active-owner.json'),owner)
        self.assertEqual(self.journal.state['attempts'][0]['status'],'reserved')
        self.assertIsNone(self.journal.state['attempts'][0]['progress_receipt'])

    def test_missing_binding_cannot_restart_as_frozen_artifact(self):
        self.start();self.backend.active=False;self.backend.empty=True
        self.controller.reconcile()
        self.graph.store.remove(self.graph.key+'.workflow.json')
        with self.assertRaisesRegex(ValueError,'lost its protected enrollment'):
            self.controller.start(run_id=2,run_attempt=1,model_seconds=600,active_seconds=1200)
        self.assertEqual(len(self.journal.state['attempts']),1)
        self.assertEqual(len(self.backend.submissions),1)

    def test_crash_before_task_receipt_retains_owned_charge_and_blocks_replay(self):
        create=self.graph.store.create
        def crash(name,value):
            if name.endswith('.workflow-attempt.json'):raise OSError('Fixture write interruption')
            return create(name,value)
        self.graph.store.create=crash
        with self.assertRaises(OSError):self.start()
        self.graph.store.create=create
        with self.assertRaises(ValueError):self.start('portable')
        with self.assertRaises(FileNotFoundError):self.controller.reconcile()
        self.assertEqual(self.backend.submissions,[])
        self.assertEqual(self.journal.state['attempts'][0]['model_seconds'],600)
        self.assertEqual(self.journal.state['attempts'][0]['status'],'reserved')

    def test_same_parent_session_cannot_resume_a_different_task(self):
        self.start();self.backend.active=False;self.backend.empty=True
        self.controller.reconcile()
        with self.assertRaisesRegex(ValueError,'selected workflow task'):
            self.controller.start(run_id=2,run_attempt=1,model_seconds=600,active_seconds=1200,
                                  task_id='portable',session_id=controller_fixtures.SESSION)
        self.assertEqual(len(self.journal.state['attempts']),1)
        self.assertEqual(len(self.backend.submissions),1)

    def test_workflow_cannot_use_single_artifact_as_parent_acceptance(self):
        self.controller.verifier=lambda *args:{'contract_digest':self.graph.key,'artifact':'fixture'}
        self.start();self.backend.active=False;self.backend.empty=True
        self.assertEqual(self.controller.reconcile(),'finished_without_verified_progress')
        self.assertIsNone(self.journal.state['attempts'][0]['progress_receipt'])
        self.assertEqual(self.graph.f.state['tasks'][1]['status'],'pending')

if __name__=='__main__':unittest.main()
