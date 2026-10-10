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
from workflow_gate import WorkflowGate, graph_identity


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
        self.contract={'fixture':'model-free parent'};self.key=digest(self.contract)
        self.store.create(self.key+'.approval.json',dict(contract=self.contract,approval_ref='fixture approval'))
        self.binding=dict(contract_digest=self.key,approval_ref='fixture graph approval',
                          checkpoint_path=str(self.checkpoint),session_id=f.state['sessionId'],
                          verification_contract=f.state['verificationContract'],
                          graph=graph_identity(f.state['tasks']),
                          task_verifiers={'prerequisite':['V1'],'dependent':['V2'],'portable':['V3']},
                          boundary='integrated_candidate')
        self.store.create(self.key+'.workflow.json',self.binding)
        self.gate=WorkflowGate(self.store,self.key,deep_loop)
    def select(self):
        save(self.checkpoint,self.f.state)
        return self.gate.selection()
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
