import unittest
import deep_loop
import test_workflow_gate as graph_fixtures
import test_private_controller as controller_fixtures
from admission import initialize
from private_controller import PrivateController


class WorkflowDispatchTests(unittest.TestCase):
    def setUp(self):
        from unittest.mock import patch
        window=patch('private_controller.remaining',return_value=1000)
        self.remaining=window.start();self.addCleanup(window.stop)
        self.graph=graph_fixtures.WorkflowGateTests()
        self.graph.setUp();self.addCleanup(self.graph.doCleanups)
        g=self.graph
        g.store.create('credential-stream.lock',{})
        self.journal=controller_fixtures.FixtureJournal(g.contract)
        self.journal.publish(None,initialize(g.key))
        self.backend=controller_fixtures.FixtureBackend()
        self.backend.observe_owned=lambda plan,contract,owner,invocation:self.backend.observe(owner['unit'],invocation)[0]
        self.controller=PrivateController(g.store,self.journal,self.backend,workflow_gate=g.gate)
    def start(self,task_id='dependent'):
        return self.controller.start(run_id=1,run_attempt=1,model_seconds=600,active_seconds=1200,task_id=task_id)
    def finished_proved_task(self):
        self.graph.f.state['tasks'][0].update(status='pending',evidence='')
        self.graph.select()
        owner=self.start('prerequisite')
        self.backend.active=False;self.backend.empty=True
        self.controller.reconcile()
        return owner

    def test_expired_window_blocks_durable_proof_record(self):
        owner=self.finished_proved_task();before=self.journal.read();self.remaining.return_value=0
        with self.assertRaisesRegex(ValueError,'window expired'):
            self.controller.record_workflow_task_proof(owner)
        self.assertFalse((self.graph.store.root/(owner['unit']+'.task-proof.json')).exists())
        self.assertEqual(self.journal.read(),before)

    def test_late_expiry_blocks_acceptance_checkpoint_replace(self):
        import json
        owner=self.finished_proved_task();self.controller.record_workflow_task_proof(owner)
        before=json.loads(self.graph.checkpoint.read_text());journal=self.journal.read()
        self.remaining.side_effect=[1000,0]
        with self.assertRaisesRegex(ValueError,'window expired'):
            self.controller.accept_workflow_task(owner)
        self.assertEqual(json.loads(self.graph.checkpoint.read_text()),before)
        self.assertEqual(self.journal.read(),journal)
        self.assertTrue((self.graph.store.root/(owner['unit']+'.task-acceptance-intent.json')).exists())
        self.assertFalse((self.graph.store.root/(owner['unit']+'.task-acceptance.json')).exists())

    def test_late_expiry_blocks_task_credit_git_write(self):
        owner=self.credited_task_fixture();before=self.journal.read()
        self.remaining.side_effect=[1000,0]
        with self.assertRaisesRegex(ValueError,'window expired'):
            self.controller.credit_workflow_task(owner)
        self.assertEqual(self.journal.read(),before)
        self.assertFalse((self.graph.store.root/(owner['unit']+'.task-credit.json')).exists())

    def test_verifier_plan_requires_latest_owned_stopped_attempt(self):
        owner=self.start('portable')
        with self.assertRaises(ValueError):self.controller.workflow_verification_plan(owner)
        self.backend.active=False;self.backend.empty=True;self.controller.reconcile()
        plan=self.controller.workflow_verification_plan(owner)
        self.assertEqual(plan['owner'],owner)
        self.assertEqual(plan['plan']['verifier_ids'],['V3'])
        self.assertFalse(plan['plan']['execution_authorized'])
        self.assertEqual(len(self.backend.submissions),1)
        self.backend.invocation='b'*32
        with self.assertRaises(ValueError):self.controller.workflow_verification_plan(owner)

    def test_malformed_acceptance_completion_keeps_dispatch_fenced(self):
        owner=self.finished_proved_task();self.controller.record_workflow_task_proof(owner)
        complete=self.controller.accept_workflow_task(owner)
        name=owner['unit']+'.task-acceptance.json'
        for changed in ({'intent_digest':complete['intent_digest']},
                        {**complete,'parent_accepted':True},
                        {**complete,'checkpoint_sha256':'0'*64}):
            self.graph.store.remove(name);self.graph.store.create(name,changed)
            with self.assertRaisesRegex(ValueError,'completion identity drift'):
                self.controller.ready_workflow_tasks()

    def test_acceptance_real_process_crash_reconciles_saved_intent(self):
        import os,signal
        if not hasattr(os,'fork'):self.skipTest('Requires POSIX interruption')
        owner=self.finished_proved_task();self.controller.record_workflow_task_proof(owner)
        before=self.journal.read()
        for boundary in ('intent','checkpoint'):
            child=os.fork()
            if child==0:
                if boundary=='intent':
                    create=self.graph.store.create
                    def crash(name,value):
                        create(name,value)
                        if name.endswith('.task-acceptance-intent.json'):os.kill(os.getpid(),signal.SIGKILL)
                    self.graph.store.create=crash
                else:
                    publish=self.graph.gate.publish_accepted_state
                    def crash(transition,**kwargs):
                        publish(transition,**kwargs);os.kill(os.getpid(),signal.SIGKILL)
                    self.graph.gate.publish_accepted_state=crash
                try:self.controller.accept_workflow_task(owner)
                finally:os._exit(3)
            _,status=os.waitpid(child,0)
            self.assertTrue(os.WIFSIGNALED(status));self.assertEqual(os.WTERMSIG(status),signal.SIGKILL)
            with self.assertRaisesRegex(ValueError,'Pending owned task acceptance'):
                self.controller.ready_workflow_tasks()
        accepted=self.controller.accept_workflow_task(owner)
        self.assertFalse(accepted['progress_credit_assigned'])
        self.assertEqual(before,self.journal.read());self.assertEqual(len(self.backend.submissions),1)

    def credited_task_fixture(self):
        self.journal.state=initialize(self.graph.key,workflow=True)
        owner=self.finished_proved_task()
        self.controller.record_workflow_task_proof(owner);self.controller.accept_workflow_task(owner)
        return owner

    def test_task_credit_recovers_uncertain_publication_without_rewriting_attempt(self):
        owner=self.credited_task_fixture();before=self.journal.read()
        self.journal.uncertain=True
        with self.assertRaises(OSError):self.controller.credit_workflow_task(owner)
        with self.assertRaisesRegex(ValueError,'Pending task credit'):
            self.controller.ready_workflow_tasks()
        self.journal.uncertain=False
        credited=self.controller.credit_workflow_task(owner)
        self.assertTrue(credited['progress_credit_assigned']);self.assertFalse(credited['parent_accepted'])
        self.assertEqual(self.journal.state['attempts'],before[1]['attempts'])
        self.assertEqual(len(self.journal.state['task_credits']),1)
        self.assertEqual(credited,self.controller.credit_workflow_task(owner))
        self.assertEqual(len(self.backend.submissions),1)

    def test_credit_fence_rejects_substituted_revision_and_journal_rollback(self):
        owner=self.credited_task_fixture();before=self.journal.read()
        completed=self.controller.credit_workflow_task(owner)
        name=owner['unit']+'.task-credit.json'
        self.graph.store.remove(name)
        self.graph.store.create(name,{**completed,'journal_revision':'0'*64})
        with self.assertRaisesRegex(ValueError,'historical revision'):
            self.controller.ready_workflow_tasks()
        self.graph.store.remove(name);self.graph.store.create(name,completed)
        self.journal.revision,self.journal.state=before
        with self.assertRaisesRegex(ValueError,'credited history'):
            self.controller.ready_workflow_tasks()

    def test_worker_recovers_acceptance_then_credit_without_dispatch(self):
        from private_worker import run
        self.journal.state=initialize(self.graph.key,workflow=True)
        owner=self.finished_proved_task();self.controller.record_workflow_task_proof(owner)
        self.graph.store.create('enabled-outcome.json',{'contract_digest':self.graph.key})
        create=self.graph.store.create
        def fault(name,value):
            if name.endswith('.task-acceptance.json'):raise OSError('Fixture completion fault')
            return create(name,value)
        self.graph.store.create=fault
        with self.assertRaises(OSError):self.controller.accept_workflow_task(owner)
        self.graph.store.create=create
        wake=lambda:run(self.graph.store,lambda key:self.controller,window=lambda *args:3600)
        self.assertEqual(wake(),'recovered_workflow_task_acceptance')
        self.assertEqual(wake(),'recovered_workflow_task_credit')
        self.assertEqual(len(self.backend.submissions),1)
        self.assertEqual(wake(),'submitted_once')
        self.assertEqual(len(self.backend.submissions),2)
        self.assertEqual(sum(a['model_seconds'] for a in self.journal.state['attempts']),1200)

    def test_task_credit_rejects_rolled_back_checkpoint_acceptance(self):
        owner=self.credited_task_fixture();before=self.journal.read()
        from test_ui_design import save
        save(self.graph.checkpoint,self.graph.f.state)
        with self.assertRaisesRegex(ValueError,'current accepted checkpoint'):
            self.controller.credit_workflow_task(owner)
        self.assertEqual(before,self.journal.read())

    def test_task_credit_missing_acceptance_or_stale_proof_never_publishes(self):
        owner=self.credited_task_fixture();before=self.journal.read()
        self.graph.f.source.write_text('drift')
        with self.assertRaisesRegex(ValueError,'proof blocked'):
            self.controller.credit_workflow_task(owner)
        self.assertEqual(before,self.journal.read())

    def test_owned_task_acceptance_updates_only_checkpoint_and_retries(self):
        owner=self.finished_proved_task();self.controller.record_workflow_task_proof(owner)
        before=self.journal.read()
        accepted=self.controller.accept_workflow_task(owner)
        self.assertFalse(accepted['progress_credit_assigned'])
        self.assertFalse(accepted['parent_accepted'])
        self.assertEqual(before,self.journal.read())
        self.assertEqual(accepted,self.controller.accept_workflow_task(owner))
        import json
        self.assertEqual(json.loads(self.graph.checkpoint.read_text())['tasks'][0]['status'],'done')
        self.assertEqual(len(self.backend.submissions),1)

    def test_acceptance_completion_fault_recovers_without_dispatch_or_charge(self):
        owner=self.finished_proved_task();self.controller.record_workflow_task_proof(owner)
        before=self.journal.read();create=self.graph.store.create
        def fault(name,value):
            if name.endswith('.task-acceptance.json'):raise OSError('Fixture completion write fault')
            return create(name,value)
        self.graph.store.create=fault
        with self.assertRaises(OSError):self.controller.accept_workflow_task(owner)
        self.graph.store.create=create
        with self.assertRaisesRegex(ValueError,'Pending owned task acceptance'):
            self.controller.start(run_id=2,run_attempt=1,model_seconds=600,active_seconds=1200,task_id='portable')
        with self.assertRaisesRegex(ValueError,'Pending owned task acceptance'):
            self.controller.ready_workflow_tasks()
        self.controller.accept_workflow_task(owner)
        self.assertEqual(before,self.journal.read())
        self.assertEqual(len(self.backend.submissions),1)

    def test_task_proof_is_bound_durable_and_assigns_no_credit(self):
        owner=self.finished_proved_task()
        before=self.journal.read()
        record=self.controller.record_workflow_task_proof(owner)
        self.assertEqual(record['owner'],owner)
        self.assertFalse(record['progress_credit_assigned'])
        self.assertEqual(record,self.graph.store.read(owner['unit']+'.task-proof.json'))
        self.assertEqual(record,self.controller.record_workflow_task_proof(owner))
        self.assertEqual(before,self.journal.read())
        self.assertIsNone(self.journal.state['attempts'][-1]['progress_receipt'])
        self.assertEqual(self.graph.f.state['tasks'][0]['status'],'pending')

    def test_production_historical_observer_works_after_owner_release(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from native_backend import NativeBackend
        from admission import digest
        owner=self.finished_proved_task();plan=self.backend.submissions[-1]
        observation=self.backend.observe(owner['unit'],self.backend.invocation)[0]
        self.controller.backend=NativeBackend(self.graph.store,self.graph.key)
        with patch('native_backend.os.geteuid',return_value=0), \
             patch('native_backend.subprocess.run',return_value=SimpleNamespace(stdout='Deep Loop plan '+digest(plan))) as show, \
             patch('native_backend.observe_unit',return_value=observation):
            record=self.controller.record_workflow_task_proof(owner)
        self.assertEqual(record['owner'],owner)
        self.assertIn('--property=Description',show.call_args.args[0])
        with self.assertRaises(FileNotFoundError):self.graph.store.read('active-owner.json')

    def test_task_proof_write_fault_preserves_finished_charge_and_retries_observation(self):
        owner=self.finished_proved_task();before=self.journal.read()
        create=self.graph.store.create
        def fail(name,value):
            if name.endswith('.task-proof.json'):raise OSError('Fixture observation write fault')
            return create(name,value)
        self.graph.store.create=fail
        with self.assertRaises(OSError):self.controller.record_workflow_task_proof(owner)
        self.graph.store.create=create
        self.assertEqual(before,self.journal.read())
        self.assertFalse(self.controller.record_workflow_task_proof(owner)['progress_credit_assigned'])
        self.assertEqual(len(self.backend.submissions),1)

    def test_task_proof_rejects_unfinished_or_substituted_owner(self):
        owner=self.start()
        with self.assertRaises(ValueError):self.controller.record_workflow_task_proof(owner)
        self.backend.active=False;self.backend.empty=True;self.controller.reconcile()
        changed={**owner,'plan_digest':'0'*64}
        with self.assertRaises(ValueError):self.controller.record_workflow_task_proof(changed)

    def test_task_proof_rejects_native_and_current_proof_drift(self):
        owner=self.finished_proved_task()
        self.backend.empty=False
        with self.assertRaisesRegex(ValueError,'stopped task ownership'):
            self.controller.record_workflow_task_proof(owner)
        self.backend.empty=True;self.backend.invocation='b'*32
        with self.assertRaisesRegex(ValueError,'stopped task ownership'):
            self.controller.record_workflow_task_proof(owner)
        self.backend.invocation='a'*32;self.graph.f.source.write_text('drift')
        with self.assertRaisesRegex(ValueError,'proof blocked'):
            self.controller.record_workflow_task_proof(owner)
        with self.assertRaises(FileNotFoundError):self.graph.store.read(owner['unit']+'.task-proof.json')

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

class TaskExecutionTests(WorkflowDispatchTests):
    def test_worker_dispatches_portable_task_when_prerequisite_is_stale(self):
        from private_worker import run
        self.graph.store.create('enabled-outcome.json',{'contract_digest':self.graph.key})
        self.graph.f.source.write_text('drift')
        self.assertEqual(run(self.graph.store,lambda key:self.controller,window=lambda *args:3600),'submitted_once')
        owner=self.graph.store.read('active-owner.json')
        record=self.graph.store.read(owner['unit']+'.workflow-attempt.json')
        self.assertEqual(record['selection']['task_id'],'portable')
        self.assertEqual(len(self.backend.submissions),1)

    def test_worker_same_task_resume_and_missing_session_preserve_limits(self):
        from private_worker import run
        self.graph.store.create('enabled-outcome.json',{'contract_digest':self.graph.key})
        wake=lambda:run(self.graph.store,lambda key:self.controller,window=lambda *args:3600)
        self.assertEqual(wake(),'submitted_once')
        self.backend.active=False;self.backend.empty=True
        self.assertEqual(wake(),'finished_without_verified_progress')
        self.assertEqual(wake(),'submitted_once')
        self.assertEqual(self.backend.submissions[-1]['session_id'],controller_fixtures.SESSION)
        self.assertEqual(wake(),'finished_without_verified_progress')
        self.assertEqual(wake(),'stopped_limits')
        self.assertEqual(sum(a['model_seconds'] for a in self.journal.state['attempts']),1200)

    def test_native_graph_execution_requires_trusted_reader(self):
        from unittest.mock import patch
        from admission import digest
        from native_backend import NativeBackend
        self.start();plan=self.backend.submissions[0]
        native=NativeBackend(self.graph.store,self.graph.key)
        native.qualified=(digest(plan),digest(self.graph.contract))
        with patch('native_backend.subprocess.run') as process:
            with self.assertRaisesRegex(ValueError,'trusted proof reader'):
                native.submit(plan,self.graph.contract)
            process.assert_not_called()

    def test_native_backend_reads_exact_task_prompt_and_rechecks_proof(self):
        import subprocess
        from unittest.mock import patch
        from admission import digest
        from native_backend import NativeBackend
        owner=self.start();plan=self.backend.submissions[0]
        native=NativeBackend(self.graph.store,self.graph.key,workflow_gate=self.graph.gate)
        native.qualified=(digest(plan),digest(self.graph.contract))
        observed={'unit':owner['unit'],'invocation_id':'a'*32,'active_state':'inactive',
                  'cgroup_empty':True,'ownership_verified':True,'execution_finished':True}
        calls=[]
        def run(args,**kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args,0,stdout='a'*32+'\n')
        with patch('native_backend.remaining',return_value=3600),patch('native_backend.subprocess.run',side_effect=run),patch('native_backend.observe_unit',return_value=observed):
            self.assertEqual(native.submit(plan,self.graph.contract),'a'*32)
        prompt=self.graph.store.read(owner['unit']+'.workflow-attempt.json')['selection']['task_id']
        text=(self.graph.store.root/(owner['unit']+'.prompt')).read_text()
        self.assertIn('Literal approved '+prompt,text)
        self.assertNotIn('Literal approved portable',text)
        self.assertNotIn(text,calls[0])

    def test_proof_drift_during_native_capture_writes_blocks_systemd(self):
        from unittest.mock import patch
        from admission import digest
        from native_backend import NativeBackend
        owner=self.start();plan=self.backend.submissions[0]
        native=NativeBackend(self.graph.store,self.graph.key,workflow_gate=self.graph.gate)
        native.qualified=(digest(plan),digest(self.graph.contract))
        raw=native._raw
        def drift(name,data):
            result=raw(name,data)
            if name.endswith('.stderr'):self.graph.f.source.write_text('drift')
            return result
        native._raw=drift
        with patch('native_backend.remaining',return_value=3600),patch('native_backend.subprocess.run') as process:
            with self.assertRaises(ValueError):native.submit(plan,self.graph.contract)
            process.assert_not_called()
        self.assertEqual(self.graph.store.read('active-owner.json'),owner)
        self.assertEqual(self.journal.state['attempts'][0]['model_seconds'],600)



    def historical_credited_task(self):
        owner=self.credited_task_fixture();self.controller.credit_workflow_task(owner);return owner

    def test_historical_task_acceptance_authenticates_after_later_finished_attempt(self):
        from admission import reserve,finish
        owner=self.historical_credited_task();revision,state=self.journal.read()
        reserved=reserve(state,self.graph.key,run_id=2,run_attempt=1,model_seconds=600,active_seconds=1200)
        self.journal.publish(revision,reserved)
        self.journal.publish(self.journal.revision,finish(reserved,self.graph.key,run_id=2,run_attempt=1))
        before=self.journal.read();checkpoint=self.graph.checkpoint.read_bytes()
        observed=self.controller.authenticate_workflow_task_history(owner)
        self.assertEqual(observed['task_id'],'prerequisite');self.assertFalse(observed['parent_accepted'])
        self.assertEqual(self.journal.read(),before);self.assertEqual(self.graph.checkpoint.read_bytes(),checkpoint)
        self.assertEqual(len(self.backend.submissions),1)

    def test_historical_chain_substitution_and_wrong_current_evidence_block(self):
        owner=self.historical_credited_task();store=self.graph.store
        name=owner['unit']+'.task-acceptance.json';original=store.read(name)
        store.remove(name);store.create(name,{**original,'intent_digest':'0'*64})
        with self.assertRaises(ValueError):self.controller.authenticate_workflow_task_history(owner)
        store.remove(name);store.create(name,original)
        self.graph.f.state=__import__('json').loads(self.graph.checkpoint.read_text())
        self.graph.f.state['tasks'][0]['evidence']='Substituted task evidence';self.graph.select()
        with self.assertRaisesRegex(ValueError,'evidence identity'):self.controller.authenticate_workflow_task_history(owner)

    def test_historical_task_rejects_live_owner_or_current_source_drift(self):
        owner=self.historical_credited_task();self.backend.active=True;self.backend.empty=False
        with self.assertRaisesRegex(ValueError,'stopped task'):self.controller.authenticate_workflow_task_history(owner)
        self.backend.active=False;self.backend.empty=True;self.graph.f.source.write_text('drift')
        with self.assertRaisesRegex(ValueError,'proof blocked'):self.controller.authenticate_workflow_task_history(owner)



    def test_outcome_authenticates_all_three_actual_task_acceptance_chains(self):
        self.graph.outcome_ready()
        for task in self.graph.f.state['tasks']:task.update(status='pending',evidence='')
        self.graph.select();self.journal.state=initialize(self.graph.key,workflow=True)
        for run_id,task_id in enumerate(('prerequisite','dependent','portable'),1):
            self.backend.active=True;self.backend.empty=False
            owner=self.controller.start(run_id=run_id,run_attempt=1,model_seconds=600,active_seconds=1200,task_id=task_id)
            self.backend.active=False;self.backend.empty=True;self.controller.reconcile()
            self.controller.record_workflow_task_proof(owner);self.controller.accept_workflow_task(owner);self.controller.credit_workflow_task(owner)
        before=self.journal.read();checkpoint=self.graph.checkpoint.read_bytes()
        observed=self.controller.observe_workflow_outcome()
        self.assertEqual(set(observed['task_histories']),{'prerequisite','dependent','portable'})
        self.assertFalse(observed['parent_accepted']);self.assertFalse(observed['delivery_verified'])
        self.assertEqual(self.journal.read(),before);self.assertEqual(self.graph.checkpoint.read_bytes(),checkpoint)

    def test_done_graph_without_credited_task_attribution_cannot_accept_outcome(self):
        self.graph.outcome_ready();self.journal.state=initialize(self.graph.key,workflow=True)
        from admission import reserve,finish
        self.journal.state=finish(reserve(self.journal.state,self.graph.key,run_id=1,run_attempt=1,model_seconds=600,active_seconds=1200),self.graph.key,run_id=1,run_attempt=1)
        with self.assertRaisesRegex(ValueError,'Every workflow'):self.controller.observe_workflow_outcome()

if __name__=='__main__':unittest.main()
