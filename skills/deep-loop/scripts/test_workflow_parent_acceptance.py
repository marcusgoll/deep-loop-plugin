import hashlib,json,os,copy
from pathlib import Path
import unittest
import test_workflow_dispatch as fixtures
from admission import digest
from unittest.mock import patch

class WorkflowParentAcceptanceTests(unittest.TestCase):
    def setUp(self):
        fixtures.WorkflowDispatchTests.setUp(self)
        window=patch("worker_window.remaining",side_effect=lambda *args,**kwargs:self.remaining(*args,**kwargs))
        window.start();self.addCleanup(window.stop)
    completed_outcome_fixture=fixtures.TaskExecutionTests.completed_outcome_fixture
    def prepared(self, *, delivery_capability=False):
        g=self.graph;candidate,_=g.modern_binding()
        g.binding.update(schema=3,parent_acceptance={'kind':'review_to_ship','approval_ref':'explicit model-free fixture'})
        if delivery_capability:
            from test_workflow_delivery_contract import delivery
            c=delivery(g.key)
            g.f.state['verificationContract']['endpoint']='github_draft_pr'
            g.binding['verification_contract']=g.f.state['verificationContract']
            g.binding.update(schema=4,workflow_delivery=c)
            g.f.state['delivery']={'status':'pending','endpoint':'github_draft_pr','repository':c['repository'],
                                  'baseRef':c['base_ref'],'headRef':c['branch'],
                                  'endpointDecision':{'status':'settled','source':'contract','evidence':c['approval_ref']}}
        g.store.remove(g.key+'.workflow.json');g.store.create(g.key+'.workflow.json',g.binding)
        g.f.state.update(active=True,complete=False,phase='REVIEW')
        original=g.outcome_ready
        def outcome():
            original();source=g.gate.candidate_snapshot(g.binding)
            rows=json.loads(Path(g.f.state['checks'][0]['receipt']['path']).read_text())
            for row in rows:row['candidate_source']=source
            name='parent-fixture-receipts.json';g.store.create(name,rows);p=g.store.root/name
            for check in g.f.state['checks']:check['receipt']={'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
            g.select()
        g.outcome_ready=outcome;self.completed_outcome_fixture();return candidate
    def test_schema_four_requires_contract_endpoint_to_match_delivery_authority(self):
        self.prepared(delivery_capability=True)
        state=json.loads(self.graph.checkpoint.read_text())
        state['verificationContract']['endpoint']='local'
        self.graph.checkpoint.write_text(json.dumps(state))
        with self.assertRaisesRegex(ValueError,'contract endpoint'):
            self.graph.gate._read()

    def test_phase_only_acceptance_and_idempotent_delivery_pending(self):
        self.prepared();before=self.journal.read();state=json.loads(self.graph.checkpoint.read_text())
        self.assertEqual(self.controller.advance_workflow_parent_acceptance(),'prepared_workflow_parent_acceptance')
        self.assertEqual(json.loads(self.graph.checkpoint.read_text()),state)
        self.assertEqual(self.controller.advance_workflow_parent_acceptance(),'recovered_workflow_parent_acceptance')
        self.assertEqual(json.loads(self.graph.checkpoint.read_text()),{**state,'phase':'SHIP'})
        self.assertEqual(self.controller.advance_workflow_parent_acceptance(),'workflow_delivery_pending')
        receipt=self.graph.store.read(self.graph.key+'.parent-acceptance.json')
        self.assertTrue(receipt['parent_accepted']);self.assertFalse(receipt['complete']);self.assertFalse(receipt['delivery_verified'])
        self.assertEqual(self.journal.read(),before);self.assertEqual(len(self.backend.submissions),3)
    def test_old_enrollment_never_infers_parent_authority(self):
        self.completed_outcome_fixture();self.assertIsNone(self.controller.advance_workflow_parent_acceptance())
        with self.assertRaisesRegex(ValueError,'enrollment required'):self.controller.prepare_workflow_parent_acceptance()
    def test_pending_intent_fences_other_mutations(self):
        self.prepared();self.controller.prepare_workflow_parent_acceptance()
        owner=self.graph.store.read('deep-loop-pilot-'+self.graph.key+'-3-1.task-credit.json')['owner']
        for call in (self.controller.ready_workflow_tasks,lambda:self.controller.workflow_verification_plan(owner),lambda:self.controller.start_native_workflow_verification(owner,0),lambda:self.controller.record_workflow_task_proof(owner),lambda:self.controller.credit_workflow_task(owner),lambda:self.controller.start(run_id=4,run_attempt=1,model_seconds=600,active_seconds=1200,task_id='portable')):
            with self.assertRaisesRegex(ValueError,'Pending parent'):call()
    def test_mutated_candidate_blocks_saved_parent_intent(self):
        candidate=self.prepared();self.controller.prepare_workflow_parent_acceptance();before=self.graph.checkpoint.read_bytes()
        (candidate/'project.py').write_text('source drift')
        with self.assertRaises(ValueError):self.controller.recover_workflow_parent_acceptance()
        self.assertEqual(self.graph.checkpoint.read_bytes(),before)
    def test_expired_authority_blocks_checkpoint_write(self):
        self.prepared();self.controller.prepare_workflow_parent_acceptance();before=self.graph.checkpoint.read_bytes();self.remaining.return_value=0
        with self.assertRaisesRegex(ValueError,'window expired'):self.controller.recover_workflow_parent_acceptance()
        self.assertEqual(self.graph.checkpoint.read_bytes(),before)
    def test_substituted_postimage_rejected(self):
        self.prepared();intent=self.controller.prepare_workflow_parent_acceptance();before=self.graph.checkpoint.read_bytes()
        name=self.graph.key+'.parent-acceptance-intent.json';self.graph.store.remove(name)
        intent['transition']['after']['complete']=True;self.graph.store.create(name,intent)
        with self.assertRaisesRegex(ValueError,'Substituted'):self.controller.recover_workflow_parent_acceptance()
        self.assertEqual(self.graph.checkpoint.read_bytes(),before)
    def test_full_review_pending_obligation_blocks_intent(self):
        self.prepared();state=json.loads(self.graph.checkpoint.read_text());state['checks'].append({'name':'required independent review','status':'pending'})
        self.graph.checkpoint.write_text(json.dumps(state))
        with self.assertRaisesRegex(ValueError,'Full workflow review blocked'):self.controller.prepare_workflow_parent_acceptance()
        self.assertFalse((self.graph.store.root/(self.graph.key+'.parent-acceptance-intent.json')).exists())
    def test_revoked_saved_authority_preserves_review_checkpoint(self):
        self.prepared();self.controller.prepare_workflow_parent_acceptance();before=self.graph.checkpoint.read_bytes()
        self.graph.store.create(self.graph.key+'.revocation-intent.json',{'fixture':'revoked'})
        with self.assertRaisesRegex(ValueError,'revoked'):self.controller.recover_workflow_parent_acceptance()
        self.assertEqual(self.graph.checkpoint.read_bytes(),before)
    def test_changed_journal_blocks_parent_recovery(self):
        self.prepared();self.controller.prepare_workflow_parent_acceptance();before=self.graph.checkpoint.read_bytes()
        self.journal.state['attempts'][0]['model_seconds']+=1
        with self.assertRaises(ValueError):self.controller.recover_workflow_parent_acceptance()
        self.assertEqual(self.graph.checkpoint.read_bytes(),before)
    def test_accepted_parent_seals_native_dispatch(self):
        self.prepared();self.controller.prepare_workflow_parent_acceptance();self.controller.recover_workflow_parent_acceptance()
        owner=self.graph.store.read('deep-loop-pilot-'+self.graph.key+'-3-1.task-credit.json')['owner']
        before=list(self.graph.store.root.iterdir())
        with self.assertRaisesRegex(ValueError,'Accepted parent'):self.controller.start_native_workflow_verification(owner,0)
        self.assertEqual(list(self.graph.store.root.iterdir()),before);self.assertEqual(len(self.backend.submissions),3)
    def test_delivery_parent_reader_is_fresh_and_read_only(self):
        self.prepared();self.controller.prepare_workflow_parent_acceptance();self.controller.recover_workflow_parent_acceptance()
        before={p.name:p.read_bytes() for p in self.graph.store.root.iterdir() if p.is_file()}
        checkpoint=self.graph.checkpoint.read_bytes();journal=self.journal.read()
        cut=self.controller.authenticate_workflow_parent_acceptance()
        self.assertEqual(cut['parent_receipt_sha256'],digest(cut['parent_receipt']))
        self.assertTrue(cut['parent_receipt']['parent_accepted']);self.assertFalse(cut['parent_receipt']['delivery_verified'])
        self.assertEqual(self.controller.authenticate_workflow_parent_acceptance(),cut)
        self.assertEqual({p.name:p.read_bytes() for p in self.graph.store.root.iterdir() if p.is_file()},before)
        self.assertEqual(self.graph.checkpoint.read_bytes(),checkpoint);self.assertEqual(self.journal.read(),journal)
    def test_schema_four_dispatch_acceptance_and_fresh_parent_reader_preserve_delivery(self):
        self.prepared(delivery_capability=True);before=self.journal.read()
        self.assertEqual(self.controller.advance_workflow_parent_acceptance(),'prepared_workflow_parent_acceptance')
        self.assertEqual(self.controller.advance_workflow_parent_acceptance(),'recovered_workflow_parent_acceptance')
        cut=self.controller.authenticate_workflow_parent_acceptance()
        self.assertTrue(cut['parent_receipt']['parent_accepted']);self.assertFalse(cut['parent_receipt']['delivery_verified'])
        self.assertEqual(self.controller.advance_workflow_parent_acceptance(),'workflow_delivery_pending')
        self.assertEqual(self.journal.read(),before);self.assertEqual(len(self.backend.submissions),3)
    def test_model_free_worker_delivery_uses_actual_parent_authentication(self):
        import sys
        from workflow_delivery import WorkflowDelivery,WAIT
        from workflow_checkpoint import WorkflowTerminal
        from test_workflow_delivery import Provider
        if sys.platform!='linux':
            mount=patch('git_candidate_export._mount_id',return_value=1);mount.start();self.addCleanup(mount.stop)
        self.prepared(delivery_capability=True)
        self.controller.prepare_workflow_parent_acceptance();self.controller.recover_workflow_parent_acceptance()
        before=self.journal.read();checkpoint=self.graph.checkpoint.read_bytes()
        accepted_cut=self.controller.authenticate_workflow_parent_acceptance()
        from private_worker import run
        self.graph.store.create('enabled-outcome.json',{'contract_digest':self.graph.key})
        provider=Provider(self.graph.binding['workflow_delivery'])
        def factory(key):
            self.assertEqual(key,self.graph.key)
            return WorkflowTerminal(self.controller,WorkflowDelivery(self.controller,provider.api))
        for _ in range(20):
            result=run(self.graph.store,lambda key:self.controller,window=lambda *args:3600,
                       workflow_delivery_factory=factory)
            if result=='workflow_complete_verified':break
            self.assertIn(result,(WAIT,'prepared_workflow_delivery_checkpoint','recovered_workflow_delivery_checkpoint',
                                      'prepared_workflow_terminal_checkpoint','recovered_workflow_terminal_checkpoint'))
        else:self.fail('Model-free provider adapter did not converge')
        receipt=factory(self.graph.key).adapter._read('complete');parent=self.controller.authenticate_workflow_parent_acceptance()
        self.assertEqual(receipt['parent_receipt_sha256'],parent['parent_receipt_sha256'])
        self.assertEqual(parent,accepted_cut)
        self.assertTrue(receipt['delivery_verified']);self.assertFalse(receipt['complete'])
        import deep_loop
        preimage=json.loads(checkpoint)
        delivered=deep_loop.verified_delivery_state(preimage,receipt['head_sha'],receipt['pull_request'])
        expected=copy.deepcopy(preimage)
        expected['delivery'].update(status='verified',revision=receipt['head_sha'],evidence=receipt['pull_request'],
            branchDisposition={'status':'verified','kind':'pull_request','revision':receipt['head_sha'],'evidence':receipt['pull_request']})
        self.assertEqual(delivered,expected)
        self.assertEqual(deep_loop.completed_state(delivered),{**delivered,'active':False,'complete':True,'phase':'COMPLETE'})
        for revision,evidence in [('0'*40,receipt['pull_request']),('f'*39,receipt['pull_request']),
                                  (receipt['head_sha'],'')]:
            with self.assertRaises(ValueError):deep_loop.verified_delivery_state(preimage,revision,evidence)
        for mutation in ('failed check','pending ship check','unresolved debt'):
            changed=copy.deepcopy(preimage)
            if mutation=='failed check':changed['checks'][0]['status']='failed'
            elif mutation=='pending ship check':changed['checks'].append({'name':'required ship','stage':'ship','status':'pending','evidence':''})
            else:changed['debt']=[{'item':'unresolved','status':'pending'}]
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                deep_loop.verified_delivery_state(changed,receipt['head_sha'],receipt['pull_request'])
        with self.assertRaises(ValueError):
            deep_loop.verified_delivery_state(delivered,receipt['head_sha'],receipt['pull_request'])
        self.assertEqual(self.journal.read(),before);self.assertEqual(json.loads(self.graph.checkpoint.read_bytes()),deep_loop.completed_state(delivered))
        completed=self.graph.store.read(self.graph.key+'.workflow-delivery-checkpoint.json')
        self.assertTrue(completed['delivery_verified']);self.assertFalse(completed['complete'])
        terminal=self.graph.store.read(self.graph.key+'.workflow-terminal-complete.json')
        self.assertTrue(terminal['complete']);self.assertTrue(terminal['delivery_verified'])
        self.assertEqual(len(self.backend.submissions),3)
    def test_locked_delivery_guard_rechecks_authenticated_enrollment(self):
        import sys
        from workflow_delivery import WorkflowDelivery,WAIT
        from test_workflow_delivery import Provider
        if sys.platform!='linux':
            mount=patch('git_candidate_export._mount_id',return_value=1);mount.start();self.addCleanup(mount.stop)
        self.prepared(delivery_capability=True)
        self.controller.prepare_workflow_parent_acceptance();self.controller.recover_workflow_parent_acceptance()
        before=self.graph.checkpoint.read_bytes();journal=self.journal.read()
        provider=Provider(self.graph.binding['workflow_delivery']);adapter=WorkflowDelivery(self.controller,provider.api)
        self.assertEqual(adapter.step(),WAIT)
        def changed(method,route,body,result):
            if route=='user':
                name=self.graph.key+'.approval.json';approval=self.graph.store.read(name)
                self.graph.store.remove(name)
                self.graph.store.create(name,{**approval,'contract':{**approval['contract'],'unexpected':'drift'}})
        provider.hook=changed
        with self.assertRaisesRegex(ValueError,'changed authenticated enrollment'):adapter.step()
        self.assertEqual(self.graph.checkpoint.read_bytes(),before);self.assertEqual(self.journal.read(),journal)
        self.assertEqual([method for method,_,_ in provider.calls],['GET'])

    def test_delivery_reader_cannot_finish_pending_parent(self):
        self.prepared();self.controller.prepare_workflow_parent_acceptance();before=self.graph.checkpoint.read_bytes()
        with self.assertRaises(FileNotFoundError):self.controller.authenticate_workflow_parent_acceptance()
        self.assertEqual(self.graph.checkpoint.read_bytes(),before)
        self.assertFalse((self.graph.store.root/(self.graph.key+'.parent-acceptance.json')).exists())
    def test_delivery_reader_rejects_tampered_completion(self):
        self.prepared();self.controller.prepare_workflow_parent_acceptance();self.controller.recover_workflow_parent_acceptance()
        name=self.graph.key+'.parent-acceptance.json';receipt=self.graph.store.read(name)
        receipt['delivery_verified']=True;self.graph.store.remove(name);self.graph.store.create(name,receipt)
        with self.assertRaisesRegex(ValueError,'completion proof'):self.controller.authenticate_workflow_parent_acceptance()
    def test_delivery_reader_requires_original_live_window(self):
        self.prepared();self.controller.prepare_workflow_parent_acceptance();self.controller.recover_workflow_parent_acceptance()
        before=self.graph.checkpoint.read_bytes();self.remaining.return_value=0
        with self.assertRaisesRegex(ValueError,'window expired'):self.controller.authenticate_workflow_parent_acceptance()
        self.assertEqual(self.graph.checkpoint.read_bytes(),before)
    def test_delivery_reader_rejects_source_drift(self):
        candidate=self.prepared();self.controller.prepare_workflow_parent_acceptance();self.controller.recover_workflow_parent_acceptance()
        (candidate/'project.py').write_text('changed after parent acceptance')
        with self.assertRaises(ValueError):self.controller.authenticate_workflow_parent_acceptance()
    def test_delivery_reader_rejects_revocation(self):
        self.prepared();self.controller.prepare_workflow_parent_acceptance();self.controller.recover_workflow_parent_acceptance()
        self.graph.store.create(self.graph.key+'.revocation-intent.json',{'fixture':'revoked'})
        with self.assertRaisesRegex(ValueError,'revoked'):self.controller.authenticate_workflow_parent_acceptance()
    def test_delivery_reader_rejects_checkpoint_change_at_last_guard(self):
        self.prepared();self.controller.prepare_workflow_parent_acceptance();self.controller.recover_workflow_parent_acceptance()
        original=self.controller._workflow_source_guard
        def changed(observation,**kwargs):
            original(observation,**kwargs)
            state=json.loads(self.graph.checkpoint.read_text());state['blocker']='late delivery obligation'
            self.graph.checkpoint.write_text(json.dumps(state))
        with patch.object(self.controller,'_workflow_source_guard',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'during delivery inspection'):
                self.controller.authenticate_workflow_parent_acceptance()
    def test_worker_advances_parent_without_additional_dispatch(self):
        from private_worker import run
        self.prepared();self.graph.store.create('enabled-outcome.json',{'contract_digest':self.graph.key})
        wake=lambda:run(self.graph.store,lambda key:self.controller,window=lambda *args:3600)
        self.assertEqual(wake(),'prepared_workflow_parent_acceptance')
        self.assertEqual(wake(),'recovered_workflow_parent_acceptance')
        self.assertEqual(wake(),'workflow_delivery_pending');self.assertEqual(len(self.backend.submissions),3)
    def test_checkpoint_drift_during_completion_guard_blocks_receipt(self):
        self.prepared();self.controller.prepare_workflow_parent_acceptance()
        original=self.controller._workflow_source_guard
        def changed(observation,**kwargs):
            original(observation,**kwargs)
            state=json.loads(self.graph.checkpoint.read_text())
            if state['phase']=='SHIP':
                state['blocker']='late obligation';self.graph.checkpoint.write_text(json.dumps(state))
        with patch.object(self.controller,'_workflow_source_guard',side_effect=changed):
            with self.assertRaises(ValueError):self.controller.recover_workflow_parent_acceptance()
        self.assertFalse((self.graph.store.root/(self.graph.key+'.parent-acceptance.json')).exists())
    def test_real_process_crash_after_each_publication_boundary(self):
        if not hasattr(os,'fork'):self.skipTest('Requires POSIX')
        self.prepared();before=self.journal.read()
        for boundary in ('intent','checkpoint','completion'):
            child=os.fork()
            if child==0:
                create=self.graph.store.create;publish=self.graph.gate.publish_parent_accepted_state
                def crash_create(name,value):
                    create(name,value)
                    if (boundary=='intent' and name.endswith('.parent-acceptance-intent.json') or boundary=='completion' and name.endswith('.parent-acceptance.json')):os.kill(os.getpid(),9)
                def crash_publish(*args,**kwargs):
                    result=publish(*args,**kwargs)
                    if boundary=='checkpoint':os.kill(os.getpid(),9)
                    return result
                self.graph.store.create=crash_create;self.graph.gate.publish_parent_accepted_state=crash_publish
                try:
                    if boundary=='intent':self.controller.prepare_workflow_parent_acceptance()
                    else:self.controller.recover_workflow_parent_acceptance()
                finally:os._exit(3)
            _,status=os.waitpid(child,0);self.assertTrue(os.WIFSIGNALED(status));self.assertEqual(os.WTERMSIG(status),9)
        self.assertEqual(self.controller.advance_workflow_parent_acceptance(),'workflow_delivery_pending')
        self.assertEqual(self.journal.read(),before);self.assertEqual(len(self.backend.submissions),3)

if __name__=='__main__':unittest.main()
