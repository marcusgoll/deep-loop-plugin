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

    def test_history_corruption_during_get_cannot_publish_or_seal(self):
        from workflow_delivery import WorkflowDelivery
        from test_workflow_delivery import Provider
        self.prepared(delivery_capability=True)
        self.controller.prepare_workflow_parent_acceptance();self.controller.recover_workflow_parent_acceptance()
        provider=Provider(self.graph.binding['workflow_delivery']);adapter=WorkflowDelivery(self.controller,provider.api)
        adapter.cut=self.controller.authenticate_workflow_parent_acceptance()
        name='deep-loop-pilot-'+self.graph.key+'-1-1.invocation.json'
        original=self.graph.store.read(name)
        checkpoint=self.graph.checkpoint.read_bytes();journal=self.journal.read()
        for corruption in ('deleted','substituted'):
            with self.subTest(corruption=corruption):
                def changed(method,route,body,result):
                    self.graph.store.remove(name)
                    if corruption=='substituted':
                        altered=copy.deepcopy(original);altered['owner']['plan_digest']='0'*64
                        self.graph.store.create(name,altered)
                provider.hook=changed
                # This GET is read-only. Current proof remains valid; retained
                # ownership is inspected again before any durable mutation.
                self.assertEqual(adapter._api('GET','user')['id'],provider.cap['publisher_id'])
                provider.hook=None;calls=len(provider.calls)
                for mutation in (lambda:adapter._api('POST','repos/'+provider.cap['repository']+'/git/refs',{}),
                                 lambda:adapter._save('complete',{'delivery_verified':True})):
                    with self.assertRaises((ValueError,FileNotFoundError)):mutation()
                self.assertEqual(len(provider.calls),calls)
                self.assertIsNone(adapter._read('complete'));self.assertIsNone(provider.ref)
                self.assertEqual(self.graph.checkpoint.read_bytes(),checkpoint);self.assertEqual(self.journal.read(),journal)
                if corruption=='substituted':self.graph.store.remove(name)
                self.graph.store.create(name,original)

    def test_later_history_read_cannot_replace_an_earlier_native_invocation(self):
        from workflow_delivery import WorkflowDelivery
        self.prepared(delivery_capability=True)
        self.controller.prepare_workflow_parent_acceptance();self.controller.recover_workflow_parent_acceptance()
        adapter=WorkflowDelivery(self.controller,lambda *args:self.fail('History guard cannot call provider'))
        adapter.cut=self.controller.authenticate_workflow_parent_acceptance()
        owners=[row['owner'] for row in adapter.cut['outcome']['task_histories'].values()]
        self.assertGreater(len(owners),1)
        history=self.controller._workflow_task_provenance_locked
        before=self.graph.checkpoint.read_bytes();journal=self.journal.read()
        for suffix in ('.workflow-attempt.json','.invocation.json','.task-proof.json',
                       '.task-acceptance-intent.json','.task-acceptance.json',
                       '.task-credit-intent.json','.task-credit.json'):
            with self.subTest(suffix=suffix):
                name=owners[0]['unit']+suffix;original=self.graph.store.read(name);called=[]
                def changed(owner):
                    actual=history(owner);called.append(owner)
                    if owner==owners[-1]:self.graph.store.remove(name)
                    return actual
                try:
                    with patch.object(self.controller,'_workflow_task_provenance_locked',side_effect=changed):
                        with self.assertRaises((ValueError,FileNotFoundError)):adapter._locked_history_guard()
                    self.assertEqual(len(called),len(owners))
                    self.assertEqual(self.graph.checkpoint.read_bytes(),before);self.assertEqual(self.journal.read(),journal)
                finally:
                    try:self.graph.store.read(name)
                    except FileNotFoundError:self.graph.store.create(name,original)

    def test_history_closure_reobserves_native_generation_and_post_guard_records(self):
        from workflow_delivery import WorkflowDelivery
        self.prepared(delivery_capability=True)
        self.controller.prepare_workflow_parent_acceptance();self.controller.recover_workflow_parent_acceptance()
        adapter=WorkflowDelivery(self.controller,lambda *args:self.fail('History guard cannot call provider'))
        adapter.cut=self.controller.authenticate_workflow_parent_acceptance()
        owners=[row['owner'] for row in adapter.cut['outcome']['task_histories'].values()]
        history=self.controller._workflow_task_provenance_locked;observe=self.backend.observe_owned
        for mutation in ('generation','populated','restarted'):
            with self.subTest(mutation=mutation):
                changed=False
                def historical(owner):
                    nonlocal changed
                    result=history(owner)
                    if owner==owners[-1]:changed=True
                    return result
                def native(plan,contract,owner,invocation):
                    result=observe(plan,contract,owner,invocation)
                    if changed and owner==owners[0]:
                        if mutation=='generation':result={**result,'invocation_id':'b'*32}
                        elif mutation=='populated':result={**result,'cgroup_empty':False}
                        else:result={**result,'active_state':'active','execution_finished':False}
                    return result
                with patch.object(self.controller,'_workflow_task_provenance_locked',side_effect=historical),patch.object(self.backend,'observe_owned',side_effect=native):
                    with self.assertRaisesRegex(ValueError,'native generation changed'):adapter._locked_history_guard()
        name=owners[0]['unit']+'.invocation.json';original=self.graph.store.read(name)
        source=self.controller._workflow_source_guard
        def late(*args,**kwargs):
            source(*args,**kwargs)
            # Only alter during the closing current-proof/source guard.
            if len(seen)==len(owners):self.graph.store.remove(name)
        seen=[]
        def inspected(owner):
            value=history(owner);seen.append(owner);return value
        try:
            with patch.object(self.controller,'_workflow_task_provenance_locked',side_effect=inspected),patch.object(self.controller,'_workflow_source_guard',side_effect=late):
                with self.assertRaises((ValueError,FileNotFoundError)):adapter._locked_history_guard()
        finally:
            self.graph.store.create(name,original)

    def test_final_native_observation_cannot_invalidate_current_outcome_cut(self):
        from workflow_delivery import WorkflowDelivery
        self.prepared(delivery_capability=True)
        self.controller.prepare_workflow_parent_acceptance();self.controller.recover_workflow_parent_acceptance()
        adapter=WorkflowDelivery(self.controller,lambda *args:self.fail('No provider calls permitted'))
        adapter.cut=self.controller.authenticate_workflow_parent_acceptance()
        owners=[row['owner'] for row in adapter.cut['outcome']['task_histories'].values()]
        observe=self.backend.observe_owned;read=self.controller.journal.read
        for reader in (self.controller.observe_workflow_outcome,adapter._locked_history_guard):
            with self.subTest(reader=reader.__name__):
                counts={};changed=False
                def native(plan,contract,owner,invocation):
                    nonlocal changed
                    result=observe(plan,contract,owner,invocation)
                    counts[owner['unit']]=counts.get(owner['unit'],0)+1
                    # Each owner's second native observation is the final pass.
                    if owner==owners[-1] and counts[owner['unit']]==2:changed=True
                    return result
                def journal():
                    result=read()
                    return ('f'*40,result[1]) if changed else result
                with patch.object(self.backend,'observe_owned',side_effect=native),patch.object(self.controller.journal,'read',side_effect=journal):
                    with self.assertRaises(ValueError):reader()
                self.assertTrue(changed)

    def test_last_native_pass_closes_helper_generation_and_current_input_drift(self):
        from workflow_delivery import WorkflowDelivery
        self.prepared(delivery_capability=True)
        self.controller.prepare_workflow_parent_acceptance();self.controller.recover_workflow_parent_acceptance()
        adapter=WorkflowDelivery(self.controller,lambda *args:self.fail('No provider calls permitted'))
        adapter.cut=self.controller.authenticate_workflow_parent_acceptance()
        owners=[row['owner'] for row in adapter.cut['outcome']['task_histories'].values()]
        observe=self.backend.observe_owned;read=self.controller.journal.read
        proof=self.controller.workflow_gate.outcome_proof;source=self.controller._workflow_source_guard
        terminal_name=self.graph.key+'.workflow-terminal-complete.json'
        self.graph.store.create(terminal_name,{'fixture':'exact optional completion record'})
        for mode in ('generation','journal','terminal'):
            for reader in (self.controller.observe_workflow_outcome,adapter._locked_history_guard):
                with self.subTest(mode=mode,reader=reader.__name__):
                    counts={};changed=False
                    def native(plan,contract,owner,invocation):
                        nonlocal changed
                        result=observe(plan,contract,owner,invocation)
                        counts[owner['unit']]=counts.get(owner['unit'],0)+1
                        if mode=='generation' and changed and owner==owners[0]:
                            return {**result,'invocation_id':'c'*32}
                        if mode in ('journal','terminal') and owner==owners[-1] and counts[owner['unit']]==3:
                            changed=True
                            if mode=='terminal':self.graph.store.remove(terminal_name)
                        return result
                    def after_helper(value):
                        nonlocal changed
                        if mode=='generation' and counts.get(owners[-1]['unit'],0)>=2:changed=True
                        return value
                    def outcome():return after_helper(proof())
                    def source_guard(*args,**kwargs):return after_helper(source(*args,**kwargs))
                    def journal():
                        result=read()
                        return ('e'*40,result[1]) if mode=='journal' and changed else result
                    with patch.object(self.backend,'observe_owned',side_effect=native),patch.object(self.controller.journal,'read',side_effect=journal),patch.object(self.controller.workflow_gate,'outcome_proof',side_effect=outcome),patch.object(self.controller,'_workflow_source_guard',side_effect=source_guard):
                        with self.assertRaises(ValueError):reader()
                    self.assertTrue(changed)
                    if mode=='terminal':self.graph.store.create(terminal_name,{'fixture':'exact optional completion record'})

    def test_last_native_pass_cannot_drift_external_proof_files(self):
        from workflow_delivery import WorkflowDelivery
        self.prepared(delivery_capability=True)
        self.controller.prepare_workflow_parent_acceptance();self.controller.recover_workflow_parent_acceptance()
        adapter=WorkflowDelivery(self.controller,lambda *args:self.fail('No provider calls permitted'))
        adapter.cut=self.controller.authenticate_workflow_parent_acceptance()
        owners=[row['owner'] for row in adapter.cut['outcome']['task_histories'].values()]
        state=json.loads(self.graph.checkpoint.read_text())
        contract=Path(state['verificationContract']['path'])
        spec=json.loads(contract.read_text())
        verifier=next(v for v in spec['verifiers'] if v.get('proof',{}).get('mode')=='bound')
        artifact=(contract.parent/verifier['proof']['artifacts'][0]['path']).resolve()
        receipt=Path(state['checks'][0]['receipt']['path'])
        observe=self.backend.observe_owned
        for path in (contract,receipt,artifact):
            original=path.read_bytes()
            for reader in (self.controller.observe_workflow_outcome,adapter._locked_history_guard):
                with self.subTest(path=str(path),reader=reader.__name__):
                    counts={};changed=False
                    def native(plan,enrollment,owner,invocation):
                        nonlocal changed
                        result=observe(plan,enrollment,owner,invocation)
                        counts[owner['unit']]=counts.get(owner['unit'],0)+1
                        if owner==owners[-1] and counts[owner['unit']]==3:
                            path.write_bytes(original+b'\n');changed=True
                        return result
                    try:
                        with patch.object(self.backend,'observe_owned',side_effect=native):
                            with self.assertRaises(ValueError):reader()
                        self.assertTrue(changed)
                    finally:path.write_bytes(original)

    def test_private_review_dependency_wrapper_matches_existing_observation(self):
        self.prepared(delivery_capability=True)
        binding,state,_=self.graph.gate._read()
        ids=sorted({identifier for group in binding['task_verifiers'].values() for identifier in group})
        helper=self.graph.gate.helper
        wrapped=helper.review_observation_with_dependencies(state,[ids])
        self.assertEqual(set(wrapped),{'observation','dependencies'})
        self.assertEqual(wrapped['observation'],helper.review_observation(state,[ids]))
        self.assertEqual(wrapped['dependencies'],helper.review_dependency_cut(state,[ids]))
        self.assertTrue(wrapped['dependencies'])

    def test_private_gate_returns_only_closing_review_dependency_cut(self):
        self.prepared(delivery_capability=True)
        gate=self.graph.gate;helper=gate.helper
        expected=gate.final_review_authority_cut()
        original=helper.review_observation_with_dependencies
        with patch.object(helper,'review_observation',wraps=helper.review_observation) as ordinary,patch.object(helper,'review_observation_with_dependencies',wraps=original) as closing:
            result=gate.final_review_authority_dependency_cut()
            self.assertEqual(result[:4],expected)
            self.assertEqual(closing.call_count,1)
            # Module-level wrapper also invokes the ordinary readers internally.
            self.assertGreaterEqual(ordinary.call_count,1)
        self.assertTrue(result[4])
        for bad in ({},None,{'observation':{},'dependencies':{}},
                    {'observation':{},'dependencies':{'/fixture':{}}}):
            with self.subTest(bad=bad),patch.object(helper,'review_observation_with_dependencies',return_value=bad):
                with self.assertRaisesRegex(ValueError,'Malformed'):gate.final_review_authority_dependency_cut()
        with patch.object(helper,'review_observation_with_dependencies',None):
            self.assertIsNone(gate.final_review_authority_dependency_cut())

    def test_expected_source_cut_preserves_full_reviews_and_checks_source_between_them(self):
        import workflow_gate
        self.prepared(delivery_capability=True)
        gate=self.graph.gate;expected=gate.final_review_authority_cut()
        source=expected[2]['candidate_source'];events=[];inside=[False]
        read=gate._read;require=workflow_gate.require_candidate_snapshot
        def reviewed(**kwargs):
            events.append('review');inside[0]=True
            try:return read(**kwargs)
            finally:inside[0]=False
        def checked(*args):
            if not inside[0]:events.append('source')
            return require(*args)
        with patch.object(gate,'_read',side_effect=reviewed),patch.object(workflow_gate,'require_candidate_snapshot',side_effect=checked):
            actual=gate.final_review_expected_source_cut(source)
        self.assertEqual(actual,expected)
        wrapped=gate.final_review_expected_source_cut(source,dependencies=True)
        self.assertEqual(wrapped[:4],expected);self.assertTrue(wrapped[4])
        with patch.object(gate.helper,'review_observation_with_dependencies',None):
            self.assertIsNone(gate.final_review_expected_source_cut(source,dependencies=True))
        with self.assertRaisesRegex(ValueError,'accepted candidate source'):
            gate.final_review_expected_source_cut(None)
        # Candidate inspection is fixed between independent full reviews.
        self.assertEqual(events.count('review'),2)
        closing=events.index('review',1)
        self.assertIn('source',events[1:closing])
        with self.assertRaisesRegex(ValueError,'accepted candidate source'):
            gate.final_review_expected_source_cut({**source,'unexpected':'foreign'})

    def test_expected_source_check_drift_is_rejected_by_closing_review(self):
        import workflow_gate
        candidate=self.prepared(delivery_capability=True)
        gate=self.graph.gate;source=gate.final_review_authority_cut()[2]['candidate_source']
        require=workflow_gate.require_candidate_snapshot;read=gate._read;inside=[False]
        def reviewed(**kwargs):
            inside[0]=True
            try:return read(**kwargs)
            finally:inside[0]=False
        def drift(*args):
            require(*args)
            if not inside[0]:(candidate/'project.py').write_text('late source drift')
        with patch.object(gate,'_read',side_effect=reviewed),patch.object(workflow_gate,'require_candidate_snapshot',side_effect=drift):
            with self.assertRaises(ValueError):gate.final_review_expected_source_cut(source)

    def test_expected_source_check_checkpoint_drift_is_rejected(self):
        import workflow_gate
        self.prepared(delivery_capability=True)
        gate=self.graph.gate;source=gate.final_review_authority_cut()[2]['candidate_source']
        require=workflow_gate.require_candidate_snapshot;read=gate._read;inside=[False]
        def reviewed(**kwargs):
            inside[0]=True
            try:return read(**kwargs)
            finally:inside[0]=False
        def drift(*args):
            require(*args)
            if inside[0]:return
            state=json.loads(self.graph.checkpoint.read_text());state['phase']='BUILD'
            self.graph.checkpoint.write_text(json.dumps(state))
        with patch.object(gate,'_read',side_effect=reviewed),patch.object(workflow_gate,'require_candidate_snapshot',side_effect=drift):
            with self.assertRaises(ValueError):gate.final_review_expected_source_cut(source)

    def test_history_guard_uses_closing_call_files_and_keeps_legacy_collector(self):
        from workflow_delivery import WorkflowDelivery
        self.prepared(delivery_capability=True)
        self.controller.prepare_workflow_parent_acceptance();self.controller.recover_workflow_parent_acceptance()
        adapter=WorkflowDelivery(self.controller,lambda *args:self.fail('No provider calls permitted'))
        adapter.cut=self.controller.authenticate_workflow_parent_acceptance()
        helper=self.graph.gate.helper
        with patch.object(helper,'review_dependency_cut',side_effect=AssertionError('No separate collector in modern history guard')):
            adapter._locked_history_guard()
        with patch.object(self.graph.gate,'final_review_authority_dependency_cut',None),patch.object(helper,'review_dependency_cut',wraps=helper.review_dependency_cut) as collector:
            adapter._locked_history_guard();self.assertEqual(collector.call_count,1)
        self.assertNotIn('dependencies',vars(adapter))

    def test_ordered_delivery_guard_retains_two_reviews_and_legacy_final_read(self):
        from workflow_delivery import WorkflowDelivery
        self.prepared(delivery_capability=True)
        self.controller.prepare_workflow_parent_acceptance();self.controller.recover_workflow_parent_acceptance()
        gate=self.graph.gate;adapter=WorkflowDelivery(self.controller,lambda *args:self.fail('No provider calls'))
        adapter.cut=self.controller.authenticate_workflow_parent_acceptance()
        with patch.object(gate.helper,'_verify',return_value=None,create=True),patch.object(gate,'_read',wraps=gate._read) as reads:
            adapter._locked_guard()
            self.assertEqual(reads.call_count,2)
            self.assertTrue(all(call.kwargs.get('review') for call in reads.call_args_list))
        with patch.object(gate,'final_review_expected_source_cut',None),patch.object(gate,'_read',wraps=gate._read) as reads:
            adapter._locked_guard();self.assertEqual(reads.call_count,3)

    def test_ordered_delivery_guard_closes_late_source_and_protected_record_drift(self):
        from workflow_delivery import WorkflowDelivery
        candidate=self.prepared(delivery_capability=True)
        self.controller.prepare_workflow_parent_acceptance();self.controller.recover_workflow_parent_acceptance()
        gate=self.graph.gate;adapter=WorkflowDelivery(self.controller,lambda *args:self.fail('No provider calls'))
        adapter.cut=self.controller.authenticate_workflow_parent_acceptance()
        source=candidate/'project.py';original=source.read_bytes()
        name=self.graph.key+'.parent-acceptance.json';record=self.graph.store.read(name)
        for kind in ('source','parent','helper_pin'):
            def drift():
                if kind=='source':source.write_text('late candidate drift')
                elif kind=='parent':
                    self.graph.store.remove(name);self.graph.store.create(name,{**record,'unexpected':'late'})
                else:raise ValueError('Pinned helper source drift')
            try:
                with self.subTest(kind=kind),patch.object(gate.helper,'_verify',side_effect=drift,create=True):
                    with self.assertRaises(ValueError):adapter._locked_guard()
            finally:
                source.write_bytes(original)
                if self.graph.store.read(name)!=record:
                    self.graph.store.remove(name);self.graph.store.create(name,record)

    def test_ordered_guard_rejects_external_contract_drift_after_closing_review(self):
        from workflow_delivery import WorkflowDelivery
        self.prepared(delivery_capability=True)
        self.controller.prepare_workflow_parent_acceptance();self.controller.recover_workflow_parent_acceptance()
        gate=self.graph.gate;calls=[]
        adapter=WorkflowDelivery(self.controller,lambda *args:calls.append(args))
        adapter.cut=self.controller.authenticate_workflow_parent_acceptance();adapter._publication_lock=True
        contract=Path(gate._read()[1]['verificationContract']['path']);original=contract.read_bytes()
        quiescence=self.controller._workflow_quiescence;observations=[]
        def late():
            result=quiescence();observations.append(True)
            if len(observations)==2:contract.write_bytes(original+b'\n')
            return result
        try:
            with patch.object(gate.helper,'_verify',return_value=None,create=True),patch.object(self.controller,'_workflow_quiescence',side_effect=late):
                with self.assertRaisesRegex(ValueError,'proof dependency changed'):
                    adapter._api('GET','fixture')
            self.assertEqual(calls,[])
        finally:contract.write_bytes(original)

    def test_ordered_guard_verifies_helper_pin_after_final_quiescence(self):
        from workflow_delivery import WorkflowDelivery
        self.prepared(delivery_capability=True)
        self.controller.prepare_workflow_parent_acceptance();self.controller.recover_workflow_parent_acceptance()
        gate=self.graph.gate;calls=[]
        adapter=WorkflowDelivery(self.controller,lambda *args:calls.append(args))
        adapter.cut=self.controller.authenticate_workflow_parent_acceptance();adapter._publication_lock=True
        pin=self.graph.store.root/'helper-pin-fixture.py';pin.write_bytes(b'original helper')
        expected=hashlib.sha256(pin.read_bytes()).hexdigest()
        quiescence=self.controller._workflow_quiescence;observations=[];verified=[]
        def late():
            result=quiescence();observations.append(True)
            if len(observations)==2:pin.write_bytes(b'substituted helper')
            return result
        def verify():
            verified.append(len(observations))
            if hashlib.sha256(pin.read_bytes()).hexdigest()!=expected:
                raise ValueError('Pinned helper source drift')
        with patch.object(gate.helper,'_verify',side_effect=verify,create=True),patch.object(self.controller,'_workflow_quiescence',side_effect=late):
            with self.assertRaisesRegex(ValueError,'Pinned helper source drift'):adapter._api('GET','fixture')
        self.assertEqual(verified,[2]);self.assertEqual(calls,[])

    def test_large_mapping_selects_legacy_before_closing_review(self):
        from workflow_delivery import WorkflowDelivery
        self.prepared(delivery_capability=True)
        gate=self.graph.gate;name=self.graph.key+'.workflow.json';original=self.graph.store.read(name)
        large={**original,'task_verifiers':{'task-'+str(i):['V1'] for i in range(129)}}
        self.graph.store.remove(name);self.graph.store.create(name,large)
        try:
            self.assertFalse(gate.supports_review_authority_dependencies())
            self.assertIsNone(gate.final_review_authority_dependency_cut())
        finally:
            self.graph.store.remove(name);self.graph.store.create(name,original)
        self.controller.prepare_workflow_parent_acceptance();self.controller.recover_workflow_parent_acceptance()
        adapter=WorkflowDelivery(self.controller,lambda *args:self.fail('No provider calls permitted'))
        adapter.cut=self.controller.authenticate_workflow_parent_acceptance()
        with patch.object(gate,'supports_review_authority_dependencies',return_value=False),patch.object(gate,'final_review_authority_dependency_cut',side_effect=AssertionError('Ineligible mapping must select legacy before guard')),patch.object(gate.helper,'review_dependency_cut',wraps=gate.helper.review_dependency_cut) as collector:
            adapter._locked_history_guard();self.assertEqual(collector.call_count,1)

    def test_missing_dependency_collector_cannot_authorize_history_closure(self):
        self.prepared(delivery_capability=True)
        with patch.object(self.controller.workflow_gate.helper,'review_dependency_cut',None):
            with self.assertRaisesRegex(ValueError,'lacks required proof dependency collection'):
                self.controller._workflow_inspection_cut()

    def test_public_and_aggregate_history_readers_close_retained_records(self):
        self.prepared(delivery_capability=True)
        self.controller.prepare_workflow_parent_acceptance();self.controller.recover_workflow_parent_acceptance()
        outcome=self.controller.observe_workflow_outcome()
        owners=[row['owner'] for row in outcome['task_histories'].values()]
        name=owners[0]['unit']+'.invocation.json';original=self.graph.store.read(name)
        observe=self.backend.observe_owned
        def native(*args):
            result=observe(*args);self.graph.store.remove(name);return result
        try:
            with patch.object(self.backend,'observe_owned',side_effect=native):
                with self.assertRaises(FileNotFoundError):self.controller.authenticate_workflow_task_provenance(owners[0])
        finally:self.graph.store.create(name,original)
        provenance=self.controller.authenticate_workflow_task_provenance
        def later(owner):
            result=provenance(owner)
            if owner==owners[-1]:self.graph.store.remove(name)
            return result
        try:
            with patch.object(self.controller,'authenticate_workflow_task_provenance',side_effect=later):
                with self.assertRaises(FileNotFoundError):self.controller.observe_workflow_outcome()
        finally:self.graph.store.create(name,original)

    def test_direct_checkpoint_and_terminal_writers_reject_mid_get_history_corruption(self):
        import sys
        from workflow_delivery import WorkflowDelivery
        from workflow_checkpoint import WorkflowCheckpoint,WorkflowTerminal
        from test_workflow_delivery import Provider
        if sys.platform!='linux':
            mount=patch('git_candidate_export._mount_id',return_value=1);mount.start();self.addCleanup(mount.stop)
        self.prepared(delivery_capability=True)
        self.controller.prepare_workflow_parent_acceptance();self.controller.recover_workflow_parent_acceptance()
        provider=Provider(self.graph.binding['workflow_delivery']);adapter=WorkflowDelivery(self.controller,provider.api)
        for _ in range(20):
            if adapter.step()=='workflow_delivery_verified':break
        else:self.fail('Provider fixture did not converge')
        checkpoint=WorkflowCheckpoint(self.controller,adapter)
        self.assertEqual(checkpoint.step(),'prepared_workflow_delivery_checkpoint')
        name='deep-loop-pilot-'+self.graph.key+'-1-1.invocation.json';original=self.graph.store.read(name)
        for endpoint in ('delivery','terminal'):
            with self.subTest(endpoint=endpoint):
                if endpoint=='terminal':
                    self.assertEqual(checkpoint.step(),'wait_for_workflow_delivery')
                    self.assertEqual(checkpoint.step(),'recovered_workflow_delivery_checkpoint')
                    writer=WorkflowTerminal(self.controller,adapter)
                    self.assertEqual(writer.step(),'prepared_workflow_terminal_checkpoint')
                else:writer=checkpoint
                before=self.graph.checkpoint.read_bytes();journal=self.journal.read();triggered=[]
                def changed(method,route,body,result):
                    if adapter._publication_lock and route.endswith('/pulls/17') and not triggered:
                        triggered.append(route);self.graph.store.remove(name)
                        if endpoint=='terminal':
                            altered=copy.deepcopy(original);altered['owner']['plan_digest']='0'*64
                            self.graph.store.create(name,altered)
                provider.hook=changed;provider.calls.clear()
                with self.assertRaises((ValueError,FileNotFoundError)):writer.step()
                self.assertTrue(triggered);self.assertTrue(all(row[0]=='GET' for row in provider.calls))
                self.assertEqual(self.graph.checkpoint.read_bytes(),before);self.assertEqual(self.journal.read(),journal)
                suffix='.workflow-'+('delivery-checkpoint' if endpoint=='delivery' else 'terminal-complete')+'.json'
                self.assertFalse((self.graph.store.root/(self.graph.key+suffix)).exists())
                provider.hook=None
                if endpoint=='terminal':self.graph.store.remove(name)
                self.graph.store.create(name,original)

    def test_completion_final_history_rejects_corruption_after_provider_or_source(self):
        import sys
        from workflow_delivery import WorkflowDelivery,WAIT
        from workflow_checkpoint import WorkflowCheckpoint,WorkflowTerminal
        from test_workflow_delivery import Provider
        if sys.platform!='linux':
            mount=patch('git_candidate_export._mount_id',return_value=1);mount.start();self.addCleanup(mount.stop)
        self.prepared(delivery_capability=True)
        self.controller.prepare_workflow_parent_acceptance();self.controller.recover_workflow_parent_acceptance()
        provider=Provider(self.graph.binding['workflow_delivery']);adapter=WorkflowDelivery(self.controller,provider.api)
        for _ in range(20):
            if adapter.step()=='workflow_delivery_verified':break
        else:self.fail('Provider fixture did not converge')
        writer=WorkflowCheckpoint(self.controller,adapter)
        name='deep-loop-pilot-'+self.graph.key+'-1-1.invocation.json';original=self.graph.store.read(name)
        for endpoint in ('delivery','terminal'):
            if endpoint=='terminal':writer=WorkflowTerminal(self.controller,adapter)
            writer.step();self.assertEqual(writer.step(),WAIT)
            for boundary in ('provider','source'):
                with self.subTest(endpoint=endpoint,boundary=boundary):
                    before=self.graph.checkpoint.read_bytes();journal=self.journal.read();triggered=[]
                    def corrupt():
                        triggered.append(boundary);self.graph.store.remove(name)
                        altered=copy.deepcopy(original);altered['owner']['plan_digest']='0'*64
                        self.graph.store.create(name,altered)
                    def changed(method,route,body,result):
                        if adapter._publication_lock and route.endswith('/pulls/17') and not triggered:corrupt()
                    source=self.controller._workflow_source_guard;provider_done=[]
                    readback=writer._provider_readback_guard
                    def readback_then_arm(receipt):
                        result=readback(receipt);provider_done.append(True);return result
                    def source_then_corrupt(*args,**kwargs):
                        source(*args,**kwargs)
                        if provider_done and not triggered:corrupt()
                    provider.calls.clear();provider.hook=changed if boundary=='provider' else None
                    with patch.object(writer,'_provider_readback_guard',side_effect=readback_then_arm),patch.object(self.controller,'_workflow_source_guard',side_effect=source_then_corrupt if boundary=='source' else source):
                        with self.assertRaises((ValueError,FileNotFoundError)):writer.step()
                    self.assertTrue(triggered);self.assertTrue(all(row[0]=='GET' for row in provider.calls))
                    self.assertEqual(self.graph.checkpoint.read_bytes(),before);self.assertEqual(self.journal.read(),journal)
                    suffix='.workflow-'+('delivery-checkpoint' if endpoint=='delivery' else 'terminal-complete')+'.json'
                    self.assertFalse((self.graph.store.root/(self.graph.key+suffix)).exists())
                    provider.hook=None;self.graph.store.remove(name);self.graph.store.create(name,original)
            writer.step()

    def test_history_drift_between_wakes_blocks_completion_and_worker_recovers_exact_stage(self):
        import sys
        from workflow_delivery import WorkflowDelivery,WAIT
        from workflow_checkpoint import WorkflowCheckpoint,WorkflowTerminal
        from test_workflow_delivery import Provider
        from private_worker import run
        if sys.platform!='linux':
            mount=patch('git_candidate_export._mount_id',return_value=1);mount.start();self.addCleanup(mount.stop)
        self.prepared(delivery_capability=True)
        self.controller.prepare_workflow_parent_acceptance();self.controller.recover_workflow_parent_acceptance()
        provider=Provider(self.graph.binding['workflow_delivery']);adapter=WorkflowDelivery(self.controller,provider.api)
        for _ in range(20):
            if adapter.step()=='workflow_delivery_verified':break
        else:self.fail('Provider fixture did not converge')
        checkpoint=WorkflowCheckpoint(self.controller,adapter)
        self.assertEqual(checkpoint.step(),'prepared_workflow_delivery_checkpoint')
        self.assertEqual(checkpoint.step(),WAIT)
        name='deep-loop-pilot-'+self.graph.key+'-1-1.invocation.json';original=self.graph.store.read(name)
        self.graph.store.remove(name)
        with self.assertRaises(FileNotFoundError):checkpoint.step()
        self.assertFalse((self.graph.store.root/(self.graph.key+'.workflow-delivery-checkpoint.json')).exists())
        self.graph.store.create(name,original)
        self.assertEqual(checkpoint.step(),'recovered_workflow_delivery_checkpoint')
        terminal=WorkflowTerminal(self.controller,adapter)
        self.assertEqual(terminal.step(),'prepared_workflow_terminal_checkpoint')
        self.assertEqual(terminal.step(),WAIT)
        self.assertTrue(json.loads(self.graph.checkpoint.read_text())['complete'])
        receipt=self.graph.key+'.workflow-terminal-complete.json'
        self.assertFalse((self.graph.store.root/receipt).exists())
        self.graph.store.create('enabled-outcome.json',{'contract_digest':self.graph.key})
        self.graph.store.remove(name)
        wake=lambda:run(self.graph.store,lambda key:self.controller,window=lambda *args:3600,
            workflow_delivery_factory=lambda key:WorkflowTerminal(self.controller,WorkflowDelivery(self.controller,provider.api)))
        with self.assertRaises(FileNotFoundError):wake()
        self.assertFalse((self.graph.store.root/receipt).exists())
        self.graph.store.create(name,original)
        self.assertEqual(wake(),'recovered_workflow_terminal_checkpoint')
        self.assertEqual(wake(),'workflow_complete_verified')
        self.assertTrue(self.graph.store.read(receipt)['complete'])

    def test_composed_checkpoint_images_reject_substitution_and_midread_drift(self):
        import sys,deep_loop
        from workflow_delivery import WorkflowDelivery,WAIT
        from workflow_checkpoint import WorkflowCheckpoint,WorkflowTerminal
        from test_workflow_delivery import Provider
        if sys.platform!='linux':
            mount=patch('git_candidate_export._mount_id',return_value=1);mount.start();self.addCleanup(mount.stop)
        self.prepared(delivery_capability=True)
        self.controller.prepare_workflow_parent_acceptance();self.controller.recover_workflow_parent_acceptance()
        provider=Provider(self.graph.binding['workflow_delivery']);adapter=WorkflowDelivery(self.controller,provider.api)
        for _ in range(20):
            if adapter.step()=='workflow_delivery_verified':break
        else:self.fail('Provider fixture did not converge')
        writer=WorkflowCheckpoint(self.controller,adapter)
        self.assertEqual(writer.step(),'prepared_workflow_delivery_checkpoint')
        self.assertEqual(writer.step(),WAIT)
        gate=self.graph.gate;checkpoint=self.graph.checkpoint;baseline=checkpoint.read_bytes()
        cut=gate.final_review_authority_cut()
        self.assertEqual(cut[:3],gate.final_review_cut())
        self.assertEqual(cut[3],gate.accepted_parent_image(cut[0],cut[1]))
        read=gate._read;reads=[]
        def differing_origin(**kwargs):
            value=read(**kwargs);reads.append(True)
            return value if len(reads)==1 else (*value[:4],{**value[4],'unexpected':'origin drift'})
        with patch.object(gate,'_read',side_effect=differing_origin):
            with self.assertRaisesRegex(ValueError,'review cut changed'):gate.final_review_authority_cut()
        method=deep_loop.checkpoint_observation
        protected=self.graph.key+'.workflow-delivery-complete.json';receipt=self.graph.store.read(protected)
        for mode in ('definition_observation','outcome_observation','review_observation'):
            call=lambda:gate._read(review=mode=='review_observation',outcome=mode=='outcome_observation',authority=mode=='review_observation')
            expected=call()
            with patch.object(deep_loop,'checkpoint_observation',None):
                self.assertEqual(call(),expected)
            for mutation in ('image','malformed','receipt','checkpoint'):
                with self.subTest(mode=mode,mutation=mutation):
                    def changed(*args):
                        result=method(*args)
                        if mutation=='image':result['delivery_image']['complete']=True
                        elif mutation=='malformed':result.pop('delivery_image')
                        elif mutation=='receipt':
                            altered=copy.deepcopy(receipt);altered['head_sha']='0'*40
                            self.graph.store.remove(protected);self.graph.store.create(protected,altered)
                        else:
                            altered=json.loads(baseline);altered['blocker']='late drift';checkpoint.write_text(json.dumps(altered))
                        return result
                    with patch.object(deep_loop,'checkpoint_observation',side_effect=changed):
                        with self.assertRaises(ValueError):call()
                    if mutation=='receipt':
                        self.graph.store.remove(protected);self.graph.store.create(protected,receipt)
                    checkpoint.write_bytes(baseline)
                    self.assertEqual(call()[:2],(self.graph.binding,json.loads(baseline)))
        self.assertEqual(writer.step(),'recovered_workflow_delivery_checkpoint')
        terminal=WorkflowTerminal(self.controller,adapter)
        self.assertEqual(terminal.step(),'prepared_workflow_terminal_checkpoint');self.assertEqual(terminal.step(),WAIT)
        terminal_baseline=checkpoint.read_bytes()
        cut=gate.final_review_authority_cut()
        self.assertEqual(cut[:3],gate.final_review_cut())
        self.assertEqual(cut[3],gate.accepted_parent_image(cut[0],cut[1]))
        def forged(*args):
            result=method(*args);result['terminal_image']['complete']=False;return result
        with patch.object(deep_loop,'checkpoint_observation',side_effect=forged):
            with self.assertRaisesRegex(ValueError,'terminal checkpoint postimage'):gate._read()
        self.assertEqual(checkpoint.read_bytes(),terminal_baseline)
        with patch.object(deep_loop,'completed_state',side_effect=ValueError('completion blocked')):
            with self.assertRaisesRegex(ValueError,'completion blocked'):gate._read()
        self.assertEqual(terminal.step(),'recovered_workflow_terminal_checkpoint')
        self.assertEqual(len(self.backend.submissions),3)

    def test_native_history_drift_during_intent_derivation_rejects_before_write(self):
        import sys
        from workflow_delivery import WorkflowDelivery,WAIT
        from workflow_checkpoint import WorkflowCheckpoint,WorkflowTerminal
        from test_workflow_delivery import Provider
        if sys.platform!='linux':
            mount=patch('git_candidate_export._mount_id',return_value=1);mount.start();self.addCleanup(mount.stop)
        self.prepared(delivery_capability=True)
        self.controller.prepare_workflow_parent_acceptance();self.controller.recover_workflow_parent_acceptance()
        provider=Provider(self.graph.binding['workflow_delivery']);adapter=WorkflowDelivery(self.controller,provider.api)
        for _ in range(20):
            if adapter.step()=='workflow_delivery_verified':break
        else:self.fail('Provider fixture did not converge')
        name='deep-loop-pilot-'+self.graph.key+'-1-1.invocation.json'
        original=self.graph.store.read(name);journal=self.journal.read()
        wrapper=WorkflowCheckpoint(self.controller,adapter)
        for terminal in (False,True):
            if terminal:
                self.assertEqual(wrapper.step(),'prepared_workflow_delivery_checkpoint')
                self.assertEqual(wrapper.step(),WAIT)
                self.assertEqual(wrapper.step(),'recovered_workflow_delivery_checkpoint')
                wrapper=WorkflowTerminal(self.controller,adapter)
            helper=self.graph.gate.helper
            method='completed_state' if terminal else 'verified_delivery_state'
            derive=getattr(helper,method);before=self.graph.checkpoint.read_bytes()
            posts=len([row for row in provider.calls if row[0]=='POST'])
            def changed(*args,**kwargs):
                result=derive(*args,**kwargs)
                self.graph.store.remove(name)
                return result
            with patch.object(helper,method,side_effect=changed):
                with self.assertRaises(FileNotFoundError):wrapper.step()
            suffix='.workflow-terminal-intent.json' if terminal else '.workflow-delivery-checkpoint-intent.json'
            self.assertFalse((self.graph.store.root/(self.graph.key+suffix)).exists())
            self.assertEqual(self.graph.checkpoint.read_bytes(),before)
            self.assertEqual(self.journal.read(),journal)
            self.assertEqual(len([row for row in provider.calls if row[0]=='POST']),posts)
            self.graph.store.create(name,original)

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
