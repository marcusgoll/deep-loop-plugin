import copy
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from admission import digest
from private_controller import TrustedStore
from native_result import NativeResult,interval,read_regular

class NativeResultTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve();self.store=TrustedStore(self.root,owner_uid=os.getuid())
        self.key='a'*64;self.prefix='deep-loop-pilot-'+self.key+'-1-1.verifier-0'
        output=self.root/'output';output.mkdir(mode=0o700);self.artifact=output/'result.txt';self.artifact.write_text('observed');self.artifact.chmod(0o600)
        self.owned={'journal_revision':'b'*40,'plan':{'selection':{'task_id':'one'}}}
        self.plan={'contract_digest':self.key,'source_owner':{'unit':'deep-loop-pilot-'+self.key+'-1-1'},'index':0,
                   'unit':'deep-loop-pilot-'+'c'*64+'-1-1','argv':['/usr/bin/python3','verify.py'],'cwd':str(self.root),
                   'read_write_paths':[str(output)],'definition':{'base':str(self.root),'identity':{'implementation':'d'*64},
                   'verifier':{'id':'V1','proof':{'artifacts':[{'path':str(self.artifact)}]}}}}
        self.store.create(self.prefix+'.intent.json',{'plan':self.plan,'owned_plan':self.owned,'plan_digest':digest(self.plan)})
        self.store.create('active-verifier.json',{'contract_digest':self.key,'prefix':self.prefix,'plan_digest':digest(self.plan)})
        self.store.create(self.prefix+'.invocation.json',{'plan_digest':digest(self.plan),'invocation_id':'e'*32})
        for suffix in ('.stdout','.stderr'):
            path=self.root/(self.prefix+suffix);path.write_bytes(b'captured');path.chmod(0o600)
        self.journal=Mock(contract_digest=self.key);self.journal.read.return_value=('b'*40,{'attempts':[]})
        self.gate=Mock(store=self.store,contract_digest=self.key);self.gate.verification_plan.return_value=self.owned['plan']
        self.observation={'plan_digest':digest(self.plan),'invocation_id':'e'*32,'exit_code':0,'unit_result':'success',
                          'native':{'ownership_verified':True,'execution_finished':True,'cgroup_empty':True},
                          'execution_interval':{'start_wall_us':1700000000000000,'end_wall_us':1700000000000010,
                                                'start_monotonic_us':100,'end_monotonic_us':110}}
        self.backend=Mock(store=self.store,key=self.key);self.backend.adopt.return_value=self.observation
        self.gate.helper.contract_semantics_sha256.return_value='f'*64
        self.sealer=NativeResult(self.store,self.journal,self.backend,self.gate)
    def seal(self,window=100):
        with patch('native_result.require_active'),patch('native_result.remaining',return_value=window,side_effect=window if isinstance(window,list) else None),patch('pwd.getpwnam',return_value=type('Account',(),{'pw_uid':max(1,os.getuid())})()),patch('native_result.subprocess.run',return_value=type('Process',(),{'returncode':1,'stdout':''})()):
            return self.sealer.seal(self.prefix)
    def test_native_result_is_sealed_without_checkpoint_acceptance_or_fence_release(self):
        result=self.seal();self.assertEqual(self.seal(),result)
        self.assertEqual(result['artifacts'][0]['sha256'],hashlib.sha256(b'observed').hexdigest())
        self.assertTrue(result['native_result_sealed']);self.assertFalse(result['checkpoint_published']);self.assertFalse(result['parent_accepted'])
        self.assertTrue((self.root/'active-verifier.json').exists())
        self.journal.publish.assert_not_called()
    def test_failed_or_nonempty_native_does_not_create_result(self):
        for change in ({'exit_code':1},{'unit_result':'timeout'},{'native':{'ownership_verified':True,'execution_finished':False,'cgroup_empty':False}}):
            self.backend.adopt.return_value={**self.observation,**change}
            with self.assertRaisesRegex(ValueError,'Successful ended empty'):self.seal()
            self.assertFalse((self.root/(self.prefix+'.result.json')).exists())
    def test_bound_input_and_generation_drift_block_sealing(self):
        self.gate.verification_plan.side_effect=[self.owned['plan'],{'selection':{'task_id':'changed'}}]
        with self.assertRaisesRegex(ValueError,'inputs changed during'):self.seal()
        self.gate.verification_plan.side_effect=None
        self.backend.adopt.side_effect=[self.observation,{**self.observation,'invocation_id':'f'*32}]
        with self.assertRaisesRegex(ValueError,'ownership changed during'):self.seal()
    def test_symlink_and_hardlink_artifacts_are_rejected(self):
        alias=self.root/'alias';os.link(self.artifact,alias)
        with self.assertRaisesRegex(ValueError,'Untrusted regular'):self.seal()
        alias.unlink();self.artifact.unlink();self.artifact.symlink_to(self.root/(self.prefix+'.stdout'))
        with self.assertRaises(OSError):self.seal()
    def test_protected_result_cannot_be_replaced_after_output_drift(self):
        self.seal();self.artifact.write_text('changed')
        with self.assertRaisesRegex(ValueError,'Protected native result changed'):self.seal()
    def test_logs_are_bounded_and_truncation_keeps_full_digest(self):
        data=b'x'*70000;(self.root/(self.prefix+'.stdout')).write_bytes(data)
        result=self.seal();capture=result['captures']['stdout']
        self.assertTrue(capture['truncated']);self.assertEqual(len(capture['text']),65536)
        self.assertEqual(capture['sha256'],hashlib.sha256(data).hexdigest())
        (self.root/(self.prefix+'.stderr')).chmod(0o644)
        with self.assertRaisesRegex(ValueError,'Untrusted regular'):self.seal()
    def test_invalid_native_interval_is_rejected(self):
        for change in ({'start_wall_us':0},{'end_monotonic_us':99},{'end_wall_us':1}):
            observation=copy.deepcopy(self.observation);observation['execution_interval'].update(change)
            with self.assertRaisesRegex(ValueError,'interval unavailable'):interval(observation)
    def test_cleanup_and_model_ownership_prevent_sealing(self):
        self.store.create(self.prefix+'.cleanup-intent.json',{})
        with self.assertRaisesRegex(ValueError,'Cleaned verifier'):self.seal()
        self.store.remove(self.prefix+'.cleanup-intent.json');self.store.create('active-owner.json',{})
        with self.assertRaisesRegex(ValueError,'Model ownership conflicts'):self.seal()

    def test_late_window_expiry_keeps_native_result_unpublished(self):
        with self.assertRaisesRegex(ValueError,'window expired'):self.seal(window=[100,0])
        self.assertFalse((self.root/(self.prefix+'.result.json')).exists())
        self.assertTrue((self.root/'active-verifier.json').exists())
    def test_artifact_count_bound_is_enforced(self):
        self.plan['definition']['verifier']['proof']['artifacts']*=129
        self.store.remove(self.prefix+'.intent.json')
        self.store.create(self.prefix+'.intent.json',{'plan':self.plan,'owned_plan':self.owned,'plan_digest':digest(self.plan)})
        self.store.remove('active-verifier.json');self.store.create('active-verifier.json',{'contract_digest':self.key,'prefix':self.prefix,'plan_digest':digest(self.plan)})
        self.store.remove(self.prefix+'.invocation.json');self.store.create(self.prefix+'.invocation.json',{'plan_digest':digest(self.plan),'invocation_id':'e'*32})
        self.observation['plan_digest']=digest(self.plan)
        with self.assertRaisesRegex(ValueError,'Bounded native result artifacts'):self.seal()

    def test_receipt_row_preserves_real_native_provenance_without_publication(self):
        result=self.seal()
        state={'sessionId':'fixture-session','verificationContract':{'semanticsSha256':'f'*64,'path':'/fixture-contract.json'}}
        intent=self.store.read(self.prefix+'.intent.json');intent['owned_plan']['plan']['checkpoint_sha256']=digest(state)
        self.store.remove(self.prefix+'.intent.json');self.store.create(self.prefix+'.intent.json',intent)
        result['owned_plan_digest']=digest(intent['owned_plan'])
        self.gate.verification_plan.return_value=intent['owned_plan']['plan']
        self.gate._read.return_value=({'fixture':'binding'},state,{})
        with patch.object(self.sealer,'seal',return_value=result):
            row=self.sealer.receipt_row(self.prefix)
        self.assertEqual(row['goal_id'],'fixture-session')
        self.assertEqual(row['native_provenance']['invocation_id'],'e'*32)
        self.assertEqual(row['startedAt'],result['startedAt'])
        self.assertEqual(row['artifacts'],result['artifacts'])
        self.assertEqual(row['sealed_result_sha256'],digest(result))
        self.assertEqual(row['runtime']['scope'],'protected result observer')
        self.assertTrue((self.root/'active-verifier.json').exists())
        self.assertFalse((self.root/(self.prefix+'.receipt.json')).exists())

    def test_receipt_row_rejects_changed_binding(self):
        result=self.seal()
        state={'sessionId':'fixture','verificationContract':{'semanticsSha256':'f'*64,'path':'/fixture-contract.json'}}
        intent=self.store.read(self.prefix+'.intent.json');intent['owned_plan']['plan']['checkpoint_sha256']=digest(state)
        self.store.remove(self.prefix+'.intent.json');self.store.create(self.prefix+'.intent.json',intent)
        result['owned_plan_digest']=digest(intent['owned_plan'])
        self.gate.verification_plan.return_value=intent['owned_plan']['plan']
        self.gate._read.side_effect=[({},state,{}),({'changed':True},state,{})]
        with patch.object(self.sealer,'seal',return_value=result):
            with self.assertRaisesRegex(ValueError,'binding changed'):
                self.sealer.receipt_row(self.prefix)

    def test_receipt_row_rejects_stable_substituted_checkpoint_after_sealing(self):
        result=self.seal()
        self.gate._read.return_value=({},
            {'sessionId':'substituted','verificationContract':{'semanticsSha256':'f'*64,'path':'/fixture-contract.json'}}, {})
        intent=self.store.read(self.prefix+'.intent.json');intent['owned_plan']['plan']['checkpoint_sha256']='0'*64
        self.store.remove(self.prefix+'.intent.json');self.store.create(self.prefix+'.intent.json',intent)
        result['owned_plan_digest']=digest(intent['owned_plan'])
        self.gate.verification_plan.return_value=intent['owned_plan']['plan']
        with patch.object(self.sealer,'seal',return_value=result):
            with self.assertRaisesRegex(ValueError,'checkpoint changed'):
                self.sealer.receipt_row(self.prefix)

    def test_receipt_row_rejects_substituted_semantics(self):
        result=self.seal()
        state={'sessionId':'fixture','verificationContract':{'path':'/fixture.json','semanticsSha256':'0'*64}}
        intent=self.store.read(self.prefix+'.intent.json');intent['owned_plan']['plan']['checkpoint_sha256']=digest(state)
        self.store.remove(self.prefix+'.intent.json');self.store.create(self.prefix+'.intent.json',intent)
        result['owned_plan_digest']=digest(intent['owned_plan'])
        self.gate.verification_plan.return_value=intent['owned_plan']['plan'];self.gate._read.return_value=({},state,{})
        with patch.object(self.sealer,'seal',return_value=result):
            with self.assertRaisesRegex(ValueError,'semantics changed'):
                self.sealer.receipt_row(self.prefix)
