import copy
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'pilot'))
import deep_loop
import test_receipt_recovery
from test_ui_design import save, sha
from admission import digest
from private_controller import TrustedStore
from workflow_gate import WorkflowGate, graph_identity, task_progress_identity


class WorkflowGateTests(unittest.TestCase):
    def setUp(self):
        self.f = f = test_receipt_recovery.GenericReceiptTests()
        f.setUp();self.addCleanup(f.doCleanups)
        f.state['tasks'] = [dict(id=i,title=i,acceptance='Verified',kind='task',
                                status='done' if i=='prerequisite' else 'pending',
                                evidence='Receipt' if i=='prerequisite' else '',
                                dependsOn=['prerequisite'] if i=='dependent' else [])
                            for i in ['prerequisite','dependent','portable']]
        for i in ['V2','V3']:
            verifier=copy.deepcopy(f.contract['verifiers'][0]);verifier['id']=i
            f.contract['verifiers'].append(verifier)
            f.state['checks'].append(dict(name=i,verifierId=i,status='pending',evidence=''))
        save(f.path,f.contract);f.state['verificationContract']['sha256']=sha(f.path)
        f.run_bound()
        self.checkpoint=save(f.root/'state.json',f.state).resolve()
        control=f.root.resolve()/'control';control.mkdir(mode=0o700)
        self.store=TrustedStore(control,owner_uid=os.getuid())
        self.contract={'fixture':'model-free parent','prompt':'Bounded parent scope',
                       'wakeup':{'model_seconds':600,'active_seconds':1200},
                       'executor':{'path':'/pinned/native/codex','sha256':'b'*64}};self.key=digest(self.contract)
        self.store.create(self.key+'.approval.json',dict(contract=self.contract,approval_ref='fixture approval'))
        self.binding=dict(contract_digest=self.key,approval_ref='fixture graph approval',
                          checkpoint_path=str(self.checkpoint),session_id=f.state['sessionId'],
                          verification_contract=f.state['verificationContract'],
                          graph=graph_identity(f.state['tasks']),
                          task_verifiers={'prerequisite':['V1'],'dependent':['V2'],'portable':['V3']},
                          task_prompts={i:'Literal approved '+i for i in ['prerequisite','dependent','portable']},
                          boundary='integrated_candidate')
        self.store.create(self.key+'.workflow.json',self.binding)
        self.gate=WorkflowGate(self.store,self.key,deep_loop)
    def modern_binding(self):
        from unittest.mock import patch
        if sys.platform != 'linux':
            mount=patch('candidate_snapshot._mount_id',return_value=1)
            mount.start();self.addCleanup(mount.stop)
        candidate=(self.f.root/'mutable-project').resolve();candidate.mkdir()
        (candidate/'project.py').write_text('first candidate')
        output=(self.f.root/'verifier-output').resolve();output.mkdir()
        self.binding.update(schema=2,candidate_source_policy={
            'schema':1,'candidate_root':str(candidate.resolve()),'scope':'entire_candidate',
            'allowed_uids':[os.getuid()],'max_entries':100,'max_file_bytes':4096,
            'max_total_bytes':16384,'max_depth':5},artifact_output_root=str(output.resolve()))
        for verifier in self.f.contract['verifiers']:
            verifier['proof']['artifacts']=[{'path':str(output/'result.txt')}]
        (output/'result.txt').write_text('verified')
        self.replace_contract()
        return candidate,output

    def test_version_two_plan_binds_mutable_candidate_without_repinning_manifest(self):
        candidate,_=self.modern_binding()
        selection=self.accepted_selection('portable')
        first=self.gate.verification_plan(selection)
        (candidate/'project.py').write_text('second candidate')
        second=self.gate.verification_plan(selection)
        self.assertNotEqual(first['candidate_source'],second['candidate_source'])
        self.assertEqual(first['definitions'],second['definitions'])
        self.assertEqual(first['selection'],second['selection'])
        self.assertFalse(second['execution_authorized'])

    def test_version_two_policy_and_output_overlap_fail_closed(self):
        candidate,_=self.modern_binding()
        for mutation in ('schema','scope','output'):
            binding=copy.deepcopy(self.binding)
            if mutation=='schema':binding['schema']=True
            elif mutation=='scope':binding['candidate_source_policy']['scope']='subset'
            else:binding['artifact_output_root']=str(candidate/'output')
            with self.assertRaises(ValueError):self.gate.validate_binding(binding)

    def test_version_two_immutable_candidate_inputs_and_wrong_artifacts_block_plan(self):
        candidate,output=self.modern_binding()
        from unittest.mock import patch
        original=self.gate.helper.verification_definitions
        def candidate_input(state,ids):
            rows=original(state,ids);rows[0]['input_paths'].append(str(candidate/'project.py'))
            return rows
        with patch.object(self.gate.helper,'verification_definitions',side_effect=candidate_input):
            with self.assertRaisesRegex(ValueError,'Immutable verifier inputs'):
                self.gate.verification_plan(self.accepted_selection('portable'))
        self.f.contract['verifiers'][2]['proof']['artifacts']=[{'path':str(candidate/'unapproved')}]
        self.replace_contract()
        with self.assertRaisesRegex(ValueError,'approved output'):
            self.gate.verification_plan(self.accepted_selection('portable'))

    def test_version_two_receipts_require_protected_exact_fresh_snapshot(self):
        candidate,_=self.modern_binding()
        source=self.gate.candidate_snapshot(self.binding)
        self.store.create('candidate-receipt.json',[{'verifier_id':'V3','candidate_source':source}])
        path=self.store.root/'candidate-receipt.json'
        state=copy.deepcopy(self.f.state)
        check=next(row for row in state['checks'] if row['verifierId']=='V3')
        check['receipt']={'path':str(path),'sha256':sha(path)}
        self.assertEqual(self.gate._candidate_receipts(self.binding,state,['V3']),source)
        (candidate/'project.py').write_text('new final candidate')
        with self.assertRaisesRegex(ValueError,'stale'):
            self.gate._candidate_receipts(self.binding,state,['V3'])
        check['receipt']['path']=str(self.f.root/'receipt.json')
        with self.assertRaisesRegex(ValueError,'Protected'):
            self.gate._candidate_receipts(self.binding,state,['V3'])

    def test_dependent_edit_refreshes_ancestor_verifiers_without_reopening_task(self):
        from unittest.mock import patch
        candidate,_=self.modern_binding()
        original_task=copy.deepcopy(self.f.state['tasks'][0])
        source=self.gate.candidate_snapshot(self.binding)
        def receipt(identifier,source):
            name=identifier.lower()+'.candidate-receipt.json'
            try:self.store.remove(name)
            except FileNotFoundError:pass
            self.store.create(name,[{'verifier_id':identifier,'candidate_source':source}])
            path=self.store.root/name
            next(c for c in self.f.state['checks'] if c['verifierId']==identifier).update(
                status='passed',receipt={'path':str(path),'sha256':sha(path)})
            save(self.checkpoint,self.f.state)
        receipt('V1',source);receipt('V2',source)
        (candidate/'project.py').write_text('edited by dependent task')
        selected=self.accepted_selection('dependent')
        with patch.object(self.gate.helper,'prerequisite_issues',return_value=[]):
            plan=self.gate.verification_plan(selected)
            self.assertEqual(plan['verifier_ids'],['V1','V2'])
            self.assertEqual(self.gate.unresolved_verifiers(self.binding,self.f.state,plan['verifier_ids']),['V1','V2'])
            with self.assertRaisesRegex(ValueError,'stale'):self.gate.task_acceptance(selected)
            fresh=self.gate.candidate_snapshot(self.binding)
            receipt('V1',fresh);receipt('V2',fresh)
            self.assertEqual(self.gate.unresolved_verifiers(self.binding,self.f.state,plan['verifier_ids']),[])
            self.assertEqual(self.gate.task_acceptance(selected)['candidate_source'],fresh)
        self.assertEqual(self.f.state['tasks'][0],original_task)
        self.assertEqual(self.f.state['tasks'][1]['status'],'pending')

    def test_final_task_verifies_all_blocking_checks_without_new_task_selection(self):
        self.modern_binding()
        self.f.state['tasks'][1].update(status='done',evidence='retained history')
        save(self.checkpoint,self.f.state)
        plan=self.gate.verification_plan(self.accepted_selection('portable'))
        self.assertEqual(plan['verifier_ids'],['V1','V2','V3'])
        self.assertEqual(plan['selection']['task_id'],'portable')
        self.assertFalse(plan['parent_accepted'])

    def test_version_two_writer_rejects_expiry_or_mutation_after_callback(self):
        from unittest.mock import patch
        candidate,_=self.modern_binding()
        source=self.gate.candidate_snapshot(self.binding)
        before=copy.deepcopy(self.f.state)
        after=copy.deepcopy(before);after['task']='postimage'
        transition={'before':before,'after':after,'observation':{'candidate_source':source}}
        original=self.checkpoint.read_bytes()
        with patch('worker_window.remaining',return_value=0):
            with self.assertRaisesRegex(ValueError,'window expired'):
                self.gate._publish_checkpoint(transition,lambda _:transition,lambda:None)
        self.assertEqual(self.checkpoint.read_bytes(),original)
        with patch('worker_window.remaining',return_value=100):
            with self.assertRaisesRegex(ValueError,'snapshot changed'):
                self.gate._publish_checkpoint(transition,lambda _:transition,lambda:None,
                    before_write=lambda:(candidate/'project.py').write_text('late mutation'))
        self.assertEqual(self.checkpoint.read_bytes(),original)

    def test_owned_binding_metadata_remains_readable_with_invalid_mutable_source(self):
        candidate,_=self.modern_binding()
        (candidate/'forbidden-alias').symlink_to('/etc/passwd')
        self.assertEqual(self.gate._read()[0],self.binding)
        with self.assertRaisesRegex(ValueError,'unsupported'):
            self.gate.verification_plan(self.accepted_selection('portable'))

    def select(self):
        save(self.checkpoint,self.f.state)
        return self.gate.selection()
    def test_verification_plan_resolves_pending_selected_inputs_without_acceptance(self):
        before=copy.deepcopy(self.f.state)
        plan=self.gate.verification_plan(self.accepted_selection('portable'))
        self.assertEqual(plan['verifier_ids'],['V3'])
        self.assertEqual(plan['definitions'][0]['verifier']['proof']['argv'],self.f.proof['argv'])
        self.assertFalse(plan['execution_authorized']);self.assertFalse(plan['parent_accepted'])
        self.assertEqual(self.f.state,before)
        self.f.source.write_text('drift')
        with self.assertRaises(ValueError):self.gate.verification_plan(self.accepted_selection('portable'))
    def replace_contract(self):
        save(self.f.path,self.f.contract)
        self.f.state['verificationContract']['sha256']=sha(self.f.path)
        self.binding['verification_contract']=self.f.state['verificationContract']
        self.store.remove(self.key+'.workflow.json');self.store.create(self.key+'.workflow.json',self.binding)
        self.select()
    def test_verification_plan_ignores_unrelated_missing_source_but_rejects_manual_selected(self):
        self.f.contract['verifiers'][1]['proof']['implementation']['path']=str(self.f.root/'unavailable-native.py')
        self.replace_contract()
        plan=self.gate.verification_plan(self.accepted_selection('portable'))
        self.assertEqual(plan['verifier_ids'],['V3'])
        self.f.contract['verifiers'][2]['proof']={'mode':'manual','reason':'Owner inspection required'}
        self.replace_contract()
        with self.assertRaisesRegex(ValueError,'requires bound blocking'):
            self.gate.verification_plan(self.accepted_selection('portable'))
    def test_native_receipt_semantics_ignore_future_input_with_real_helper(self):
        from unittest.mock import Mock,patch
        from native_result import NativeResult
        self.f.contract['verifiers'][1]['proof']['implementation']['path']=str(self.f.root/'absent-future.py')
        self.f.state['verificationContract']['semanticsSha256']=deep_loop.contract_semantics_sha256(self.f.contract)
        self.replace_contract()
        selection=self.accepted_selection('portable')
        plan=self.gate.verification_plan(selection)
        owned={'plan':plan}
        prefix='fixture-verifier'
        self.store.create(prefix+'.intent.json',{'owned_plan':owned})
        result={'owned_plan_digest':digest(owned),'verifier_id':'V3','argv':[],
                'cwd':str(self.f.root),'identity':{},'artifacts':[], 'exitCode':0,
                'startedAt':'fixture','finishedAt':'fixture','runtime':{},
                'unit':'fixture','invocation_id':'fixture','plan_digest':'fixture',
                'execution_interval':{},'unit_result':'success','captures':{}}
        sealer=NativeResult(self.store,Mock(),Mock(),self.gate)
        with patch.object(sealer,'seal',return_value=result):
            row=sealer.receipt_row(prefix)
        self.assertEqual(row['contract_semantics'],self.f.state['verificationContract']['semanticsSha256'])
        self.f.source.write_text('selected source drift')
        with patch.object(sealer,'seal',return_value=result):
            with self.assertRaises(ValueError):sealer.receipt_row(prefix)

    def test_verification_plan_preserves_human_judgment_as_unresolved(self):
        self.f.contract['verifiers'][2]['class']='human'
        self.replace_contract()
        with self.assertRaisesRegex(ValueError,'requires bound blocking'):
            self.gate.verification_plan(self.accepted_selection('portable'))

    def test_verification_plan_rejects_changed_selection_and_checkpoint(self):
        selection=self.accepted_selection('portable')
        with self.assertRaisesRegex(ValueError,'selection changed'):
            self.gate.verification_plan({**selection,'prompt_sha256':'0'*64})
        from unittest.mock import patch
        original=self.gate.helper.verification_definitions
        def change(state,ids):
            result=original(state,ids);self.f.state['task']='changed';save(self.checkpoint,self.f.state);return result
        with patch.object(self.gate.helper,'verification_definitions',side_effect=change):
            with self.assertRaisesRegex(ValueError,'checkpoint changed'):
                self.gate.verification_plan(selection)

    def test_helper_task_transition_preserves_parent_and_requires_proof(self):
        self.f.state['tasks'][0].update(status='pending',evidence='')
        before=copy.deepcopy(self.f.state)
        result=deep_loop.accepted_task_state(before,'prerequisite',['V1'],'protected task receipt',digest(before))
        self.assertEqual(before,self.f.state)
        self.assertEqual(result['tasks'][0]['status'],'done')
        self.assertEqual(result['checks'],before['checks'])
        self.assertEqual(result.get('complete'),before.get('complete'))
        self.assertEqual(result.get('delivery'),before.get('delivery'))
        self.assertEqual(result,deep_loop.accepted_task_state(result,'prerequisite',['V1'],'protected task receipt',digest(result)))
        with self.assertRaisesRegex(ValueError,'preimage'):
            deep_loop.accepted_task_state(before,'prerequisite',['V1'],'proof','0'*64)
        with self.assertRaisesRegex(ValueError,'proof blocked'):
            deep_loop.accepted_task_state(before,'portable',['V3'],'proof',digest(before))
        with self.assertRaisesRegex(ValueError,'completed prerequisites'):
            deep_loop.accepted_task_state(before,'dependent',['V2'],'proof',digest(before))

    def test_helper_transition_rejects_closed_blocked_and_not_due_sessions(self):
        self.f.state['tasks'][0].update(status='pending',evidence='')
        for change in ({'active':False},{'complete':True},{'blocker':'External decision'}):
            state=copy.deepcopy(self.f.state);state.update(change)
            with self.assertRaisesRegex(ValueError,'session or stage'):
                deep_loop.accepted_task_state(state,'prerequisite',['V1'],'proof',digest(state))
        state=copy.deepcopy(self.f.state);state['tasks'][0]['stage']='ship'
        with self.assertRaisesRegex(ValueError,'session or stage'):
            deep_loop.accepted_task_state(state,'prerequisite',['V1'],'proof',digest(state))

    def test_explicit_workflow_binding_requires_empty_private_approved_state(self):
        from workflow_enrollment import WorkflowBindingEnrollment
        from test_private_controller import FixtureJournal
        from admission import initialize
        self.store.create('credential-stream.lock',{})
        self.store.remove(self.key+'.workflow.json')
        journal=FixtureJournal(self.contract);journal.publish(None,initialize(self.key,workflow=True))
        with self.assertRaisesRegex(ValueError,'protected controller store'):
            WorkflowBindingEnrollment(self.store,journal,deep_loop).apply(self.binding,expected_binding_digest=digest(self.binding),approval_ref=self.binding['approval_ref'])
        self.checkpoint=save(self.store.root/'state.json',self.f.state)
        self.binding['checkpoint_path']=str(self.checkpoint)
        operator=WorkflowBindingEnrollment(self.store,journal,deep_loop)
        with self.assertRaisesRegex(ValueError,'Exact authenticated'):
            operator.apply(self.binding,expected_binding_digest='0'*64,approval_ref=self.binding['approval_ref'])
        journal.state=initialize(self.key)
        with self.assertRaisesRegex(ValueError,'Empty explicitly'):
            operator.apply(self.binding,expected_binding_digest=digest(self.binding),approval_ref=self.binding['approval_ref'])
        journal.state=initialize(self.key,workflow=True)
        self.checkpoint.chmod(0o666)
        with self.assertRaisesRegex(ValueError,'Protected private'):
            operator.apply(self.binding,expected_binding_digest=digest(self.binding),approval_ref=self.binding['approval_ref'])
        self.checkpoint.chmod(0o600)
        result=operator.apply(self.binding,expected_binding_digest=digest(self.binding),approval_ref=self.binding['approval_ref'])
        self.assertFalse(result['activated'])
        self.assertEqual(self.gate.selection()['ready'],['dependent','portable'])
        completion=self.store.read(self.key+'.workflow-binding-complete.json')
        self.store.remove(self.key+'.workflow-binding-complete.json')
        with self.assertRaises(FileNotFoundError):self.gate.selection()
        self.store.create(self.key+'.workflow-binding-complete.json',completion)
        with self.assertRaises(FileNotFoundError):self.store.read('enabled-outcome.json')
        with self.assertRaisesRegex(ValueError,'partial workflow'):
            operator.apply(self.binding,expected_binding_digest=digest(self.binding),approval_ref=self.binding['approval_ref'])

    def accepted_selection(self, task_id='prerequisite'):
        import hashlib
        return dict(task_id=task_id,binding_digest=digest(self.binding),
                    session_id=self.f.state['sessionId'],
                    prompt_sha256=hashlib.sha256(self.binding['task_prompts'][task_id].encode()).hexdigest())

    def transition(self):
        self.f.state['tasks'][0].update(status='pending',evidence='')
        self.select()
        return self.gate.accepted_state(self.accepted_selection(),'protected receipt')

    def test_acceptance_publication_and_after_write_retry(self):
        transition=self.transition()
        saved=self.gate.publish_accepted_state(transition)
        self.assertEqual(saved,transition['after'])
        from unittest.mock import patch
        import stat
        sync=os.fsync;directories=[]
        def inspected_sync(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):directories.append(fd)
            sync(fd)
        with patch('workflow_gate.os.fsync',side_effect=inspected_sync):
            self.assertEqual(saved,self.gate.publish_accepted_state(transition))
        self.assertTrue(directories)
        self.assertTrue((self.checkpoint.parent/'.deep-task-acceptance.lock').is_file())

    @unittest.skipUnless(hasattr(os,'fork'),'Requires POSIX process interruption')
    def test_acceptance_sigkill_before_and_after_replace_recovers(self):
        import signal
        for after in (False,True):
            transition=self.transition()
            child=os.fork()
            if child==0:
                replace=os.replace
                def crash(*args,**kwargs):
                    if after:replace(*args,**kwargs)
                    os.kill(os.getpid(),signal.SIGKILL)
                os.replace=crash
                try:self.gate.publish_accepted_state(transition)
                finally:os._exit(3)
            _,status=os.waitpid(child,0)
            self.assertTrue(os.WIFSIGNALED(status))
            self.assertEqual(os.WTERMSIG(status),signal.SIGKILL)
            self.assertEqual(self.gate.publish_accepted_state(transition),transition['after'])

    def test_acceptance_write_response_fault_recovers_without_repeating_transition(self):
        from unittest.mock import patch
        transition=self.transition();replace=os.replace
        def response_fault(*args,**kwargs):
            replace(*args,**kwargs)
            raise OSError('Fixture response lost after atomic replace')
        with patch('workflow_gate.os.replace',side_effect=response_fault):
            with self.assertRaises(OSError):self.gate.publish_accepted_state(transition)
        self.assertEqual(self.gate.publish_accepted_state(transition),transition['after'])
        self.assertFalse(list(self.checkpoint.parent.glob('.deep-task-acceptance-*.tmp')))

    def test_oversized_acceptance_output_preserves_readable_checkpoint(self):
        self.f.state['tasks'][0].update(status='pending',evidence='')
        self.select();before=self.checkpoint.read_bytes()
        transition=self.gate.accepted_state(self.accepted_selection(),'x'*(1024*1024))
        with self.assertRaisesRegex(ValueError,'bounded writer limit'):
            self.gate.publish_accepted_state(transition)
        self.assertEqual(self.checkpoint.read_bytes(),before)

    def test_acceptance_stale_proof_cannot_publish_done_status(self):
        transition=self.transition();before=self.checkpoint.read_bytes()
        self.f.source.write_text('drift')
        with self.assertRaisesRegex(ValueError,'proof blocked'):
            self.gate.publish_accepted_state(transition)
        self.assertEqual(self.checkpoint.read_bytes(),before)

    def test_acceptance_publication_rejects_stale_lock_and_unprotected_file(self):
        transition=self.transition()
        self.f.state['tasks'][2]['evidence']='unrelated edit'
        save(self.checkpoint,self.f.state)
        with self.assertRaisesRegex(ValueError,'Stale'):
            self.gate.publish_accepted_state(transition)
        save(self.checkpoint,transition['before'])
        import fcntl
        lock=self.checkpoint.parent/'.deep-task-acceptance.lock'
        with lock.open('r+') as stream:
            fcntl.flock(stream.fileno(),fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):self.gate.publish_accepted_state(transition)
        self.checkpoint.chmod(0o666)
        with self.assertRaisesRegex(ValueError,'Protected checkpoint file'):
            self.gate.publish_accepted_state(transition)

    def test_protected_transition_uses_own_mapping_and_does_not_write(self):
        self.f.state['tasks'][0].update(status='pending',evidence='')
        self.select();before=self.checkpoint.read_bytes()
        transition=self.gate.accepted_state(self.accepted_selection(),'protected receipt')
        self.assertEqual(transition['after']['tasks'][0]['status'],'done')
        self.assertEqual(self.checkpoint.read_bytes(),before)
        with self.assertRaisesRegex(ValueError,'proof blocked'):
            self.gate.accepted_state(self.accepted_selection('portable'),'unrelated passed proof')

    def test_task_acceptance_requires_own_current_proof(self):
        before=copy.deepcopy(self.f.state)
        receipt=self.gate.task_acceptance(self.accepted_selection())
        self.assertFalse(receipt['parent_accepted'])
        self.assertEqual(receipt['verifier_ids'],['V1'])
        self.assertEqual(before,self.f.state)
        with self.assertRaisesRegex(ValueError,'proof blocked'):
            self.gate.task_acceptance(self.accepted_selection('portable'))
        self.f.source.write_text('drift')
        with self.assertRaisesRegex(ValueError,'proof blocked'):
            self.gate.task_acceptance(self.accepted_selection())

    def test_progress_identity_does_not_reward_receipt_or_checkpoint_churn(self):
        observation=self.gate.task_acceptance(self.accepted_selection())
        identity=task_progress_identity(observation)
        changed=copy.deepcopy(observation)
        changed.update(checkpoint_sha256='unrelated state changed',proof_receipts={'V1':{'path':'new receipt','sha256':'new run'}})
        self.assertEqual(task_progress_identity(changed),identity)
        changed['selection']['task_id']='other approved task'
        self.assertNotEqual(task_progress_identity(changed),identity)
        changed['parent_accepted']=True
        with self.assertRaises(ValueError):task_progress_identity(changed)

    def test_task_acceptance_rejects_cancelled_or_blocked_task(self):
        for status in ('cancelled','blocked'):
            self.f.state['tasks'][0].update(status=status,reason='Revoked task',evidence='Existing receipt',blocker='Revoked',nextAction='Resolve authority')
            save(self.checkpoint,self.f.state)
            with self.assertRaisesRegex(ValueError,'cancelled or blocked'):
                self.gate.task_acceptance(self.accepted_selection())

    def test_task_acceptance_rejects_identity_and_concurrent_drift(self):
        selected=self.accepted_selection();selected['prompt_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'prompt identity'):
            self.gate.task_acceptance(selected)
        original=self.gate._read;calls=[]
        def changing_read():
            result=original();calls.append(1)
            if len(calls)==2:result[1]['tasks'][0]['evidence']='changed'
            return result
        self.gate._read=changing_read
        with self.assertRaisesRegex(ValueError,'changed during inspection'):
            self.gate.task_acceptance(self.accepted_selection())

    def test_fifo_and_linked_checkpoint_rejected_without_blocking(self):
        self.checkpoint.unlink();os.mkfifo(self.checkpoint)
        with self.assertRaisesRegex(ValueError,'Regular checkpoint'):self.gate.selection()
        self.checkpoint.unlink();self.checkpoint.symlink_to(self.f.path)
        with self.assertRaisesRegex(ValueError,'Canonical checkpoint'):self.gate.selection()

    def test_oversized_checkpoint_rejected(self):
        self.checkpoint.write_bytes(b' '*(1024*1024+1))
        with self.assertRaisesRegex(ValueError,'bounded reader'):self.gate.selection()

    def test_revoked_parent_cannot_select_any_task(self):
        self.store.create(self.key+'.revocation-intent.json',{'fixture':'revoked'})
        with self.assertRaises(ValueError):self.gate.selection()

    def test_current_proof_and_independent_pending_verifier(self):
        before=copy.deepcopy(self.f.state)
        self.assertEqual(self.select()['ready'],['dependent','portable'])
        self.assertEqual(before,self.f.state)
        self.assertTrue(deep_loop.contract_issues(self.f.state,'review'))
    def test_stale_or_missing_proof_only_blocks_dependent(self):
        self.f.source.write_text('drift')
        result=self.select();self.assertEqual(result['ready'],['portable'])
        self.assertIn('dependent',result['blocked'])
    def test_missing_failed_or_manual_prerequisite_keeps_portable_ready(self):
        original=copy.deepcopy(self.f.state)
        for change in ({'status':'failed'}, {'receipt':{'path':str(self.f.root/'missing.json'),'sha256':'0'*64}}):
            self.f.state=copy.deepcopy(original);self.f.state['checks'][0].update(change)
            self.assertEqual(self.select()['ready'],['portable'])
        self.f.state=original
        self.f.contract['verifiers'][0]['proof']={'mode':'manual','reason':'Required native inspection'}
        save(self.f.path,self.f.contract)
        self.f.state['verificationContract']['sha256']=sha(self.f.path)
        self.binding['verification_contract']=copy.deepcopy(self.f.state['verificationContract'])
        self.store.remove(self.key+'.workflow.json');self.store.create(self.key+'.workflow.json',self.binding)
        self.assertEqual(self.select()['ready'],['portable'])

    def test_mapping_cannot_omit_parent_obligation(self):
        self.binding['task_verifiers']['portable']=['V2']
        self.store.remove(self.key+'.workflow.json');self.store.create(self.key+'.workflow.json',self.binding)
        with self.assertRaisesRegex(ValueError,'every parent blocking'):self.select()
    def test_graph_and_parent_identity_drift_rejected(self):
        self.f.state['tasks'][1]['dependsOn']=[]
        with self.assertRaisesRegex(ValueError,'graph drift'):self.select()
        self.f.state['tasks'][1]['dependsOn']=['prerequisite']
        self.f.state['sessionId']='substituted'
        with self.assertRaisesRegex(ValueError,'identity drift'):self.select()
    def test_cancelled_prerequisite_cannot_be_promoted(self):
        self.f.state['tasks'][0].update(status='cancelled',reason='fixture cancellation')
        self.assertEqual(self.select()['ready'],['portable'])
    def test_unsupported_merge_boundary_cannot_silently_pass(self):
        self.binding['boundary']='merge_required'
        self.store.remove(self.key+'.workflow.json');self.store.create(self.key+'.workflow.json',self.binding)
        with self.assertRaisesRegex(ValueError,'Unsupported'):self.select()


    def verification_transition(self):
        import json
        rows=json.loads((self.f.root/'receipt.json').read_text())
        rows[0]['verifier_id']='V3';rows[0]['name']='V3'
        path=save(self.f.root/'native-receipt.json',rows).resolve()
        reference={'path':str(path),'sha256':sha(path)}
        return self.gate.verified_state('V3',reference,'Native verifier evidence')

    def test_verification_publication_changes_only_selected_check_and_exact_retry(self):
        before=copy.deepcopy(self.f.state)
        transition=self.verification_transition()
        self.assertEqual(transition['before'],before)
        expected=copy.deepcopy(before);expected['checks'][2]=transition['after']['checks'][2]
        self.assertEqual(transition['after'],expected)
        saved=self.gate.publish_verified_state(transition)
        self.assertEqual(saved,expected)
        self.assertEqual(self.gate.publish_verified_state(transition),saved)
        self.assertEqual(saved['tasks'],before['tasks']);self.assertEqual(saved['delivery'],before['delivery'])

    def test_verification_publication_rejects_changed_receipt_or_stale_checkpoint(self):
        transition=self.verification_transition()
        path=Path(transition['observation']['receipt']['path']);path.write_text('[]')
        with self.assertRaises(ValueError):self.gate.publish_verified_state(transition)
        self.assertEqual(__import__('json').loads(self.checkpoint.read_text()),transition['before'])

    def test_verification_transition_requires_exact_preimage(self):
        transition=self.verification_transition()
        with self.assertRaisesRegex(ValueError,'preimage'):
            deep_loop.verified_check_state(transition['before'],'V3',transition['observation']['receipt'],'Evidence','0'*64)

    def test_late_publication_authority_guard_blocks_actual_atomic_replace(self):
        transition=self.verification_transition()
        def expired():raise ValueError('fixture publication window expired')
        with self.assertRaisesRegex(ValueError,'window expired'):
            self.gate.publish_verified_state(transition,before_write=expired)
        self.assertEqual(__import__('json').loads(self.checkpoint.read_text()),transition['before'])
        self.assertFalse(list(self.checkpoint.parent.glob('.deep-task-acceptance-*.tmp')))



    def test_final_review_inspects_full_helper_obligations_without_mutation(self):
        self.outcome_ready();before=self.checkpoint.read_bytes()
        proof=self.gate.final_review_proof()
        self.assertEqual(proof['kind'],'workflow_final_review_proof')
        self.assertFalse(proof['parent_accepted']);self.assertFalse(proof['delivery_verified'])
        self.assertEqual(self.checkpoint.read_bytes(),before)
        for field,value in [('debt',[{'item':'unaccepted debt','status':'accepted'}]),
                            ('blocker','unavailable required review'),
                            ('checks',self.f.state['checks']+[{'name':'independent review','status':'pending'}])]:
            previous=self.f.state.get(field)
            self.f.state[field]=value;self.select()
            with self.assertRaisesRegex(ValueError,'Full workflow review blocked'):self.gate.final_review_proof()
            if previous is None:self.f.state.pop(field)
            else:self.f.state[field]=previous
            self.select()

    def test_final_review_rejects_checkpoint_drift_during_full_validation(self):
        from unittest.mock import patch
        self.outcome_ready();original=self.gate.helper.validation_issues
        def changed(*args):
            issues=original(*args)
            self.f.state['blocker']='concurrent blocker';self.select()
            return issues
        with patch.object(self.gate.helper,'validation_issues',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'cut changed'):self.gate.final_review_proof()

    def outcome_ready(self):
        import argparse
        f=self.f
        batch=save(f.root/'outcome-checks.json',[{'name':v['id'],'verifierId':v['id'],'argv':v['proof']['argv']} for v in f.contract['verifiers']])
        output=f.root/'outcome-receipt.json'
        args=argparse.Namespace(root=str(f.root),checks=str(batch),output=str(output),contract=str(f.path),goal_id=f.state['sessionId'],ui_request=None,source_manifest=None,environment_manifest=None)
        self.assertEqual(deep_loop.run_checks(args),0)
        for check in f.state['checks']:check.update(status='passed',evidence='Actual integrated fixture checks',receipt={'path':str(output),'sha256':sha(output)})
        for task in f.state['tasks']:task.update(status='done',evidence='Controller must authenticate this claim')
        self.select()

    def test_outcome_observer_requires_all_tasks_and_current_real_proof(self):
        with self.assertRaisesRegex(ValueError,'unfinished'):self.gate.outcome_proof()
        self.outcome_ready();before=self.checkpoint.read_bytes()
        observed=self.gate.outcome_proof()
        self.assertEqual(observed['verifier_ids'],['V1','V2','V3'])
        self.assertEqual(set(observed['tasks']),{'prerequisite','dependent','portable'})
        self.assertFalse(observed['parent_accepted']);self.assertFalse(observed['delivery_verified'])
        self.assertEqual(self.checkpoint.read_bytes(),before)
        self.f.source.write_text('drift')
        with self.assertRaisesRegex(ValueError,'proof blocked'):self.gate.outcome_proof()

    def test_outcome_done_claim_without_all_verifier_receipts_is_blocked(self):
        for task in self.f.state['tasks']:task.update(status='done',evidence='Untrusted completion claim')
        self.select()
        with self.assertRaisesRegex(ValueError,'proof blocked'):self.gate.outcome_proof()

    def test_outcome_observer_rejects_checkpoint_change_during_task_inspection(self):
        from unittest.mock import patch
        self.outcome_ready();original=self.gate.task_acceptance
        def change(selection):
            observation=original(selection);self.f.state['tasks'][0]['evidence']='Concurrent drift';self.select();return observation
        with patch.object(self.gate,'task_acceptance',side_effect=change):
            with self.assertRaisesRegex(ValueError,'changed'):self.gate.outcome_proof()

if __name__=='__main__':unittest.main()
