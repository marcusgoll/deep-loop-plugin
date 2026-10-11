"""Real checkpoint writer/process faults with synthetic history/helper authority.

The full helper/controller integration is separately exercised in the helper
suite. These disposable tests never authenticate or contact a GitHub provider.
"""
import copy,json,os
from pathlib import Path
import unittest
from unittest.mock import patch
import test_workflow_delivery as fixtures
from admission import digest
from workflow_delivery import WorkflowDelivery
from workflow_checkpoint import WorkflowCheckpoint, WorkflowTerminal
from workflow_gate import WorkflowGate


class LiteralHelper:
    def verified_delivery_state(self,state,revision,evidence,archive=None):
        if state['delivery']['status']!='pending':raise ValueError('Pending fixture required')
        result=copy.deepcopy(state)
        result['delivery'].update(status='verified',revision=revision,evidence=evidence,
            branchDisposition={'status':'verified','kind':'pull_request','revision':revision,'evidence':evidence})
        return result
    def completed_state(self,state,archive=None):
        if state.get("complete") or state["delivery"]["status"]!="verified":raise ValueError("Delivered open fixture required")
        if state.get("blocked_ship"):raise ValueError("SHIP fixture blocked")
        return {**copy.deepcopy(state),"active":False,"complete":True,"phase":"COMPLETE"}
    def validation_issues(self,*args):return []


class CheckpointGate:
    """Use production exact-image admission and atomic writer, literal helper."""
    accepted_parent_image=WorkflowGate.accepted_parent_image
    _publish_checkpoint=WorkflowGate._publish_checkpoint
    def __init__(self,controller,path):
        self.c=controller;self.path=path;self.store=controller.store;self.contract_digest=controller.contract_digest
        self.helper=LiteralHelper()
    def _read(self):
        binding=self.store.read(self.contract_digest+'.workflow.json');state=json.loads(self.path.read_text())
        self.accepted_parent_image(binding,state)
        return binding,state,{}
    def final_review_proof(self):
        _,state,_=self._read()
        return self.c._parent_proof_at_checkpoint(self.c.proof,digest(state))


def late_history_mutation(case,terminal):
    for mutation in ('checkpoint','window'):
        with case.subTest(mutation=mutation):
            case.setUp();intent=case.terminal() if terminal else case.intent()
            provider_guard=case.wrapper._provider_guard;history_guard=case.adapter._locked_history_guard
            in_provider=False;triggered=[]
            def provider(receipt):
                nonlocal in_provider
                in_provider=True
                try:return provider_guard(receipt)
                finally:in_provider=False
            def history():
                history_guard()
                state=json.loads(case.path.read_text())
                if not in_provider and state==intent['after']:
                    triggered.append(mutation)
                    if mutation=='checkpoint':case.path.write_text(json.dumps(intent['before']))
                    else:case.c.active=False
            with patch.object(case.wrapper,'_provider_guard',side_effect=provider),patch.object(case.adapter,'_locked_history_guard',side_effect=history):
                with case.assertRaises(ValueError):case.wrapper.step()
            case.assertTrue(triggered)
            suffix='.workflow-terminal-complete.json' if terminal else '.workflow-delivery-checkpoint.json'
            case.assertFalse((case.c.store.root/(case.key+suffix)).exists())


class WorkflowCheckpointTests(unittest.TestCase):
    def setUp(self):
        f=fixtures.WorkflowDeliveryTests();f.setUp();self.addCleanup(f.doCleanups)
        self.c=f.controller;self.provider=f.provider;self.key=self.c.contract_digest
        window=patch('worker_window.remaining',return_value=1000);window.start();self.addCleanup(window.stop)
        self.path=self.c.store.root/'checkpoint.json'
        self.c.state.update(active=True,verificationContract={'endpoint':'github_draft_pr'})
        self.c.state['delivery'].update(endpoint='github_draft_pr',repository=self.c.cap['repository'],
            baseRef=self.c.cap['base_ref'],headRef=self.c.cap['branch'],
            endpointDecision={'status':'settled','source':'contract','evidence':self.c.cap['approval_ref']})
        self.path.write_text(json.dumps(self.c.state));self.path.chmod(0o600)
        self.c.binding['checkpoint_path']=str(self.path)
        self.c.proof=self.c._parent_proof_at_checkpoint(self.c.proof,digest(self.c.state))
        self.c.cut['binding_sha256']=digest(self.c.binding)
        self.c.cut['parent_receipt'].update(checkpoint_sha256=digest(self.c.state),postimage_review_proof=self.c.proof)
        self.c.cut['parent_receipt_sha256']=digest(self.c.cut['parent_receipt'])
        for suffix,value in (('.workflow.json',self.c.binding),('.parent-acceptance.json',self.c.cut['parent_receipt'])):
            self.c.store.remove(self.key+suffix);self.c.store.create(self.key+suffix,value)
        self.c.workflow_gate=CheckpointGate(self.c,self.path)
        self.adapter=WorkflowDelivery(self.c,self.provider.api);self.wrapper=WorkflowCheckpoint(self.c,self.adapter)
        for _ in range(20):
            if self.adapter.step()=='workflow_delivery_verified':break
        else:self.fail('Emulator preparation did not converge')
        self.before=self.path.read_bytes();self.parent=self.c.store.read(self.key+'.parent-acceptance.json')
    def intent(self):
        self.assertEqual(self.wrapper.step(),'prepared_workflow_delivery_checkpoint')
        return self.c.store.read(self.key+'.workflow-delivery-checkpoint-intent.json')
    def completion_exists(self):return (self.c.store.root/(self.key+'.workflow-delivery-checkpoint.json')).exists()
    def test_history_guard_cannot_change_final_checkpoint_or_extend_window(self):
        late_history_mutation(self,False)

    def test_exact_writer_and_repeat_recovery_preserve_history_and_never_provider_write(self):
        saved=self.intent();self.provider.calls.clear()
        self.assertEqual(self.wrapper.step(),'recovered_workflow_delivery_checkpoint')
        self.assertEqual(json.loads(self.path.read_text()),saved['after'])
        after=self.path.read_bytes();self.assertEqual(self.wrapper.step(),'workflow_delivery_checkpoint_verified')
        self.assertEqual(self.path.read_bytes(),after);self.assertEqual(self.c.store.read(self.key+'.parent-acceptance.json'),self.parent)
        self.assertFalse(saved['after']['complete']);self.assertTrue(saved['after']['active'])
        self.assertTrue(all(method=='GET' for method,_,_ in self.provider.calls))
    def test_provider_drift_and_missing_endpoint_never_recreate_or_publish_checkpoint(self):
        self.intent();self.provider.calls.clear();pr=copy.deepcopy(self.provider.pr)
        for mutation in ('head','base','checks','missing PR','missing ref'):
            self.provider.pr=copy.deepcopy(pr);self.provider.ref={'object':{'sha':pr['head']['sha']}};self.provider.check_status='success'
            if mutation=='head':self.provider.pr['head']['sha']='f'*40
            elif mutation=='base':self.provider.pr['base']['sha']='f'*40
            elif mutation=='checks':self.provider.check_status='failure'
            elif mutation=='missing PR':self.provider.pr=None
            else:self.provider.ref=None
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):self.wrapper.step()
            self.assertEqual(self.path.read_bytes(),self.before);self.assertFalse(self.completion_exists())
        self.assertTrue(all(method=='GET' for method,_,_ in self.provider.calls))
    def test_substituted_intent_receipt_and_checkpoint_are_rejected(self):
        intent=self.intent();name=self.key+'.workflow-delivery-checkpoint-intent.json'
        for image in ({**intent,'after':{**intent['after'],'complete':True}},
                      {**intent,'binding_sha256':'f'*64},{**intent,'unexpected':'field'}):
            self.c.store.remove(name);self.c.store.create(name,image)
            with self.assertRaises(ValueError):self.wrapper.step()
            self.assertEqual(self.path.read_bytes(),self.before)
        self.c.store.remove(name);self.c.store.create(name,intent)
        self.path.write_text(json.dumps({**intent['after'],'extra':'unapproved'}))
        with self.assertRaises(ValueError):self.c.workflow_gate._read()
        self.assertFalse(self.completion_exists())
    def test_competing_checkpoint_writer_lock_blocks_publication(self):
        import fcntl
        self.intent();lock=self.path.parent/'.deep-task-acceptance.lock'
        fd=os.open(lock,os.O_CREAT|os.O_RDWR,0o600)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):self.wrapper.step()
        finally:os.close(fd)
        self.assertEqual(self.path.read_bytes(),self.before);self.assertFalse(self.completion_exists())

    def test_revocation_and_expired_original_window_stop_recovery_before_io(self):
        self.intent();self.provider.calls.clear();self.c.active=False
        with self.assertRaisesRegex(ValueError,'expired'):self.wrapper.step()
        self.assertEqual(self.path.read_bytes(),self.before);self.assertFalse(self.completion_exists())
        self.c.active=True;self.c.store.create(self.key+'.revocation-intent.json',{'fixture':'revoked'})
        with self.assertRaisesRegex(ValueError,'revoked'):self.wrapper.step()
        self.assertFalse(self.provider.calls)
    def test_source_and_protected_receipt_drift_cannot_publish(self):
        self.intent();name=self.key+'.workflow-delivery-complete.json';receipt=self.c.store.read(name)
        self.c.store.remove(name);self.c.store.create(name,{**receipt,'head_sha':'f'*40})
        with self.assertRaises(ValueError):self.wrapper.step()
        self.c.store.remove(name);self.c.store.create(name,receipt)
        (self.c.candidate/'extra.txt').write_text('unapproved source')
        with self.assertRaises(ValueError):self.wrapper.step()
        self.assertEqual(self.path.read_bytes(),self.before);self.assertFalse(self.completion_exists())

    def test_late_window_expiry_during_final_readback_blocks_completion_receipt(self):
        intent=self.intent();original=self.c.workflow_gate._read
        publication=self.c.workflow_gate._publish_checkpoint;provider_guard=self.wrapper._provider_guard
        published=False
        def publish(*args,**kwargs):
            nonlocal published
            result=publication(*args,**kwargs);published=True;return result
        def guard_then_arm_expiry(receipt):
            provider_guard(receipt)
            if published:
                # Expire in the exact state read AFTER the final provider guard,
                # where the old code could create a completion without a check.
                def read_then_expire():
                    result=original();self.c.active=False;return result
                self.c.workflow_gate._read=read_then_expire
        with patch.object(self.c.workflow_gate,'_publish_checkpoint',side_effect=publish),                patch.object(self.wrapper,'_provider_guard',side_effect=guard_then_arm_expiry):
            with self.assertRaisesRegex(ValueError,'expired'):self.wrapper.step()
        self.assertEqual(json.loads(self.path.read_text()),intent['after']);self.assertFalse(self.completion_exists())
    def test_late_checkpoint_drift_in_source_guard_blocks_completion(self):
        intent=self.intent();guard=self.c._workflow_source_guard
        def changed(proof,**kwargs):
            guard(proof,**kwargs)
            state=json.loads(self.path.read_text())
            if state['delivery']['status']=='verified':
                state['extra']='late drift';self.path.write_text(json.dumps(state))
        with patch.object(self.c,'_workflow_source_guard',side_effect=changed):
            with self.assertRaises(ValueError):self.wrapper.step()
        self.assertFalse(self.completion_exists())
    def test_process_crash_at_intent_checkpoint_and_completion_recovers_exact_images(self):
        if not hasattr(os,'fork'):self.skipTest('Requires POSIX')
        for boundary in ('intent','checkpoint','completion'):
            child=os.fork()
            if child==0:
                create=self.c.store.create;publish=self.c.workflow_gate._publish_checkpoint
                def crash_create(name,value):
                    create(name,value)
                    if (boundary=='intent' and name.endswith('-checkpoint-intent.json') or
                            boundary=='completion' and name.endswith('-checkpoint.json')):os.kill(os.getpid(),9)
                def crash_publish(*args,**kwargs):
                    result=publish(*args,**kwargs)
                    if boundary=='checkpoint':os.kill(os.getpid(),9)
                    return result
                self.c.store.create=crash_create;self.c.workflow_gate._publish_checkpoint=crash_publish
                try:self.wrapper.step()
                finally:os._exit(3)
            _,status=os.waitpid(child,0);self.assertTrue(os.WIFSIGNALED(status));self.assertEqual(os.WTERMSIG(status),9)
        self.assertEqual(self.wrapper.step(),'workflow_delivery_checkpoint_verified')
        self.assertEqual(self.c.store.read(self.key+'.parent-acceptance.json'),self.parent)


class WorkflowTerminalTests(unittest.TestCase):
    def test_history_guard_cannot_change_terminal_checkpoint_or_extend_window(self):
        late_history_mutation(self,True)

    setUp=WorkflowCheckpointTests.setUp
    intent=WorkflowCheckpointTests.intent
    def terminal(self):
        self.intent()
        self.assertEqual(self.wrapper.step(),'recovered_workflow_delivery_checkpoint')
        self.wrapper=WorkflowTerminal(self.c,self.adapter)
        self.assertEqual(self.wrapper.step(),'prepared_workflow_terminal_checkpoint')
        return self.c.store.read(self.key+'.workflow-terminal-intent.json')
    def test_terminal_exact_recovery_and_immutable_parent(self):
        intent=self.terminal();self.provider.calls.clear()
        self.assertEqual(self.wrapper.step(),'recovered_workflow_terminal_checkpoint')
        self.assertEqual(json.loads(self.path.read_text()),intent['after'])
        self.assertEqual(self.wrapper.step(),'workflow_complete_verified')
        self.assertEqual(self.c.store.read(self.key+'.parent-acceptance.json'),self.parent)
        self.assertEqual(self.c.workflow_gate.accepted_parent_image(self.c.binding,intent['after']),json.loads(self.before))
        self.assertTrue(all(method=='GET' for method,_,_ in self.provider.calls))
    def test_terminal_forgery_and_receipt_drift(self):
        intent=self.terminal();before=self.path.read_bytes()
        name=self.key+'.workflow-terminal-intent.json'
        for forged in ({**intent,'unexpected':True},{**intent,'after':{**intent['after'],'extra':True}},
                       {**intent,'delivery_checkpoint_sha256':'f'*64}):
            self.c.store.remove(name);self.c.store.create(name,forged)
            with self.assertRaises(ValueError):self.wrapper.step()
            self.assertEqual(self.path.read_bytes(),before)
        self.c.store.remove(name);self.c.store.create(name,intent)
        checkpoint=self.key+'.workflow-delivery-checkpoint.json'
        self.c.store.remove(checkpoint)
        with self.assertRaises(FileNotFoundError):self.wrapper.step()
        self.assertEqual(self.path.read_bytes(),before)
    def test_terminal_provider_drift_never_closes(self):
        self.terminal();before=self.path.read_bytes();self.provider.check_status='failure'
        with self.assertRaises(ValueError):self.wrapper.step()
        self.assertEqual(self.path.read_bytes(),before)
        self.assertFalse((self.c.store.root/(self.key+'.workflow-terminal-complete.json')).exists())
    def test_terminal_competing_writer_blocks(self):
        import fcntl
        self.terminal();before=self.path.read_bytes()
        fd=os.open(self.path.parent/'.deep-task-acceptance.lock',os.O_RDWR|os.O_CREAT,0o600)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):self.wrapper.step()
        finally:os.close(fd)
        self.assertEqual(self.path.read_bytes(),before)
    def test_terminal_late_expiry_blocks_receipt(self):
        intent=self.terminal();publish=self.c.workflow_gate._publish_checkpoint;source=self.c._workflow_source_guard
        published=False
        def published_call(*args,**kwargs):
            nonlocal published
            result=publish(*args,**kwargs);published=True;return result
        def expire(proof,**kwargs):
            source(proof,**kwargs)
            if published:self.c.active=False
        with patch.object(self.c.workflow_gate,'_publish_checkpoint',side_effect=published_call),patch.object(self.c,'_workflow_source_guard',side_effect=expire):
            with self.assertRaisesRegex(ValueError,'expired'):self.wrapper.step()
        self.assertEqual(json.loads(self.path.read_text()),intent['after'])
        self.assertFalse((self.c.store.root/(self.key+'.workflow-terminal-complete.json')).exists())
    def test_terminal_revocation_and_source_drift(self):
        self.terminal();before=self.path.read_bytes();self.provider.calls.clear()
        self.c.store.create(self.key+'.revocation-intent.json',{'fixture':'revoked'})
        with self.assertRaisesRegex(ValueError,'revoked'):self.wrapper.step()
        self.assertFalse(self.provider.calls);self.assertEqual(self.path.read_bytes(),before)
        self.c.store.remove(self.key+'.revocation-intent.json')
        (self.c.candidate/'extra.txt').write_text('unapproved source')
        with self.assertRaises(ValueError):self.wrapper.step()
        self.assertEqual(self.path.read_bytes(),before)
    def test_terminal_process_crash_at_each_protected_boundary(self):
        if not hasattr(os,'fork'):self.skipTest('Requires POSIX')
        self.intent();self.wrapper.step();self.wrapper=WorkflowTerminal(self.c,self.adapter)
        for boundary in ('intent','checkpoint','completion'):
            child=os.fork()
            if child==0:
                create=self.c.store.create;publish=self.c.workflow_gate._publish_checkpoint
                def crash_create(name,value):
                    create(name,value)
                    if (boundary=='intent' and name.endswith('.workflow-terminal-intent.json') or
                            boundary=='completion' and name.endswith('.workflow-terminal-complete.json')):os.kill(os.getpid(),9)
                def crash_publish(*args,**kwargs):
                    result=publish(*args,**kwargs)
                    if boundary=='checkpoint':os.kill(os.getpid(),9)
                    return result
                self.c.store.create=crash_create;self.c.workflow_gate._publish_checkpoint=crash_publish
                try:self.wrapper.step()
                finally:os._exit(3)
            _,status=os.waitpid(child,0)
            self.assertTrue(os.WIFSIGNALED(status));self.assertEqual(os.WTERMSIG(status),9)
        self.assertEqual(self.wrapper.step(),'workflow_complete_verified')
        self.assertEqual(self.c.store.read(self.key+'.parent-acceptance.json'),self.parent)
