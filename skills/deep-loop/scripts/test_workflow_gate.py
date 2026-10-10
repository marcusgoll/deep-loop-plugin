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
    def select(self):
        save(self.checkpoint,self.f.state)
        return self.gate.selection()
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

if __name__=='__main__':unittest.main()
