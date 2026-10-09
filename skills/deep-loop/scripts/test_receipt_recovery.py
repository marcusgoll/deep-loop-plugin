import argparse, copy, json, shutil, sys, tempfile, unittest
from pathlib import Path
import deep_loop, ui_design
import test_ui_design as ui_fixtures
from test_ui_design import save, sha

class GenericReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.impl=self.root/'verify.py';self.impl.write_text("from pathlib import Path\nassert Path('input.txt').read_text()=='correct'\nPath('result.txt').write_text('verified')\n")
        self.source=self.root/'input.txt';self.source.write_text('correct')
        self.manifest=save(self.root/'source.json',{'files':{'input.txt':sha(self.source)}})
        self.env=save(self.root/'environment.json',{'python':sys.version})
        self.proof={'mode':'bound','implementation':{'path':str(self.impl),'sha256':sha(self.impl)},'argv':[sys.executable,str(self.impl)],'source_manifest':{'path':str(self.manifest),'sha256':sha(self.manifest)},'environment_manifest':{'path':str(self.env),'sha256':sha(self.env)},'artifacts':[{'path':str(self.root/'result.txt')}]}
        self.contract={'name':'Receipt fixture','scope':'local','status':'NOT_RUN','requirements':[{'id':'R1','outcome':'Correct','invariant':'Correct','priority':'blocking'}],'verifiers':[{'id':'V1','covers':['R1'],'class':'deterministic','status':'implemented','expected':'No failures','gate':'blocking','proof':self.proof}],'gaps':[],'ship_gate':dict.fromkeys(('require_all_blocking_verifiers_pass','require_zero_blocking_gaps','require_human_approvals_recorded','require_evidence_matches_revision'),True)}
        self.path=save(self.root/'contract.json',self.contract)
        self.state={'schemaVersion':2,'sessionId':'receipt1','checks':[{'name':'V1','verifierId':'V1','status':'passed','evidence':'claimed'}],'verificationContract':{'path':str(self.path),'sha256':sha(self.path),'endpoint':'local'},'delivery':{'endpoint':'local','status':'verified','evidence':'readback'}}
    def run_bound(self):
        batch=save(self.root/'checks.json',[{'name':'V1','verifierId':'V1','argv':self.proof['argv']}]);out=self.root/'receipt.json'
        args=argparse.Namespace(root=str(self.root),checks=str(batch),output=str(out),contract=str(self.path),goal_id='receipt1',ui_request=None,source_manifest=None,environment_manifest=None)
        self.assertEqual(deep_loop.run_checks(args),0)
        self.state['checks'][0]['receipt']={'path':str(out),'sha256':sha(out)}
        return out
    def test_claim_is_not_bound_proof(self): self.assertTrue(deep_loop.contract_issues(self.state,'review'))
    def test_actual_run_then_source_artifact_receipt_and_goal_drift(self):
        receipt=self.run_bound();self.assertEqual(deep_loop.contract_issues(self.state,'review'),[])
        for path in (self.source,self.root/'result.txt',receipt,self.env,self.impl):
            previous=path.read_bytes();path.write_bytes(previous+b'changed')
            self.assertTrue(deep_loop.contract_issues(self.state,'review'),str(path));path.write_bytes(previous)
        self.state['sessionId']='other001';self.assertTrue(deep_loop.contract_issues(self.state,'review'))
    def test_failed_execution_missing_artifact_and_input_mutation_do_not_pass(self):
        for script in ("raise SystemExit(3)", "pass", "from pathlib import Path\nPath('input.txt').write_text('drift')\nPath('result.txt').write_text('verified')"):
            self.impl.write_text(script);self.proof['implementation']['sha256']=sha(self.impl)
            save(self.path,self.contract);self.state['verificationContract']['sha256']=sha(self.path)
            batch=save(self.root/'checks.json',[{'name':'V1','verifierId':'V1','argv':self.proof['argv']}])
            out=self.root/('run-'+str(len(script))+'.json')
            args=argparse.Namespace(root=str(self.root),checks=str(batch),output=str(out),contract=str(self.path),goal_id='receipt1',ui_request=None,source_manifest=None,environment_manifest=None)
            self.assertNotEqual(deep_loop.run_checks(args),0)
            self.state['checks'][0]['receipt']={'path':str(out),'sha256':sha(out)}
            self.assertTrue(deep_loop.contract_issues(self.state,'review'))
    def test_substituted_receipt_invocation_and_contract_semantics_rejected(self):
        receipt=self.run_bound();original=receipt.read_bytes()
        for key,value in (('argv',['wrong']),('goal_id','other001'),('exitCode',7),('artifacts',[]),('contract_semantics','wrong'),('identity',{}),('runtime',{})):
            rows=json.loads(original);rows[0][key]=value;save(receipt,rows)
            self.state['checks'][0]['receipt']['sha256']=sha(receipt)
            self.assertTrue(deep_loop.contract_issues(self.state,'review'),key)
        receipt.write_bytes(original);self.state['checks'][0]['receipt']['sha256']=sha(receipt)
        self.contract['requirements'][0]['invariant']='Changed obligation';save(self.path,self.contract)
        self.state['verificationContract']['sha256']=sha(self.path)
        self.assertTrue(deep_loop.contract_issues(self.state,'review'))
    def test_bound_invocation_rejects_undeclared_command_before_output(self):
        batch=save(self.root/'checks.json',[{'name':'V1','verifierId':'V1','argv':[sys.executable,'-c','pass']}]);out=self.root/'receipt.json'
        args=argparse.Namespace(root=str(self.root),checks=str(batch),output=str(out),contract=str(self.path),goal_id='receipt1',ui_request=None,source_manifest=None,environment_manifest=None)
        with self.assertRaises(ValueError):deep_loop.run_checks(args)
        self.assertFalse(out.exists())
    def test_build_checks_definitions_not_pending_run_and_manual_requires_reason(self):
        self.assertEqual(deep_loop.contract_issues(self.state,'build'),[])
        self.contract['verifiers'][0]['proof']={'mode':'manual'};save(self.path,self.contract)
        self.state['verificationContract']['sha256']=sha(self.path)
        self.assertTrue(deep_loop.contract_issues(self.state,'build'))
    def test_pending_closeout_bound_proof_is_due_only_at_ship(self):
        self.state['checks'][0].update(stage='closeout',status='pending',evidence='')
        self.assertEqual(deep_loop.contract_issues(self.state,'review'),[])
        self.assertEqual(deep_loop.contract_issues(self.state,'delivery'),[])
        self.assertTrue(deep_loop.contract_issues(self.state,'ship'))
    def test_generic_archive_requires_resolution_binding_and_rejects_unresolved_bound_closeout(self):
        self.run_bound();self.state.update(task='Generic recovery',active=False,complete=False,phase='SHIP')
        root=self.root/'checkout';root.mkdir();checkpoint=root/'.deep-receipt1';checkpoint.mkdir()
        save(checkpoint/'state.json',self.state);(checkpoint/'plan.md').write_text('Generic recovery')
        archive=self.root/'archive';args=argparse.Namespace(root=str(root),path=str(checkpoint),session=None,destination=str(archive),include=[],checkpoint_only=True)
        deep_loop.preserve(args)
        state_path=archive/'checkpoint/state.json';working=json.loads(state_path.read_text());del working['proofResolution'];save(state_path,working)
        with self.assertRaises(ValueError):deep_loop.verify_archive(archive)
        with self.assertRaises(ValueError):deep_loop.retire_checkpoint(argparse.Namespace(root=str(root),archive=str(archive)))
        self.assertTrue(checkpoint.exists())
        shutil.rmtree(archive)
        self.state['checks'][0].update(stage='closeout',status='pending',evidence='');self.state['checks'][0].pop('receipt')
        self.state['checks'].append({'name':'Independent readback','status':'passed','evidence':'Saved artifact inspected'})
        save(checkpoint/'state.json',self.state);preimage=(checkpoint/'state.json').read_bytes()
        with self.assertRaisesRegex(ValueError,'unresolved bound closeout'):deep_loop.preserve(args)
        self.assertFalse(archive.exists());self.assertEqual((checkpoint/'state.json').read_bytes(),preimage)
        self.state['checks'][0].update(status='passed',evidence='Executed closeout',receipt={'path':str(self.root/'receipt.json'),'sha256':sha(self.root/'receipt.json')})
        save(checkpoint/'state.json',self.state);deep_loop.preserve(args)
        for path in list(self.root.iterdir()):
            if path not in (root,archive):
                shutil.rmtree(path) if path.is_dir() else path.unlink()
        deep_loop.retire_checkpoint(argparse.Namespace(root=str(root),archive=str(archive)))
        evidence=self.root/'closeout-readback.txt';evidence.write_text('Checkpoint removed')
        deep_loop.finalize_archive(argparse.Namespace(archive=str(archive),evidence=str(evidence)))
    def test_advisory_bound_declaration_does_not_require_absent_check(self):
        advisory=copy.deepcopy(self.contract['verifiers'][0]);advisory.update(id='V2',gate='advisory')
        self.contract['verifiers'].append(advisory);save(self.path,self.contract)
        self.state['verificationContract']['sha256']=sha(self.path)
        self.run_bound();self.assertEqual(deep_loop.contract_issues(self.state,'review'),[])
        self.state['checks'].append({'name':'Optional declared check','verifierId':'V2','status':'passed','evidence':'claimed'})
        self.assertTrue(deep_loop.contract_issues(self.state,'review'))
    def test_explicit_manual_and_legacy(self):
        self.contract['verifiers'][0]['proof']={'mode':'manual','reason':'Human visual judgment'}
        save(self.path,self.contract);self.state['verificationContract']['sha256']=sha(self.path)
        self.assertEqual(deep_loop.contract_issues(self.state,'review'),[])
        del self.contract['verifiers'][0]['proof'];save(self.path,self.contract);self.state['verificationContract']['sha256']=sha(self.path)
        self.assertEqual(deep_loop.contract_issues(self.state,'review'),[])

class PortableUIRecoveryTests(unittest.TestCase):
    setUp=ui_fixtures.UIContractTests.setUp;make_capture=ui_fixtures.UIContractTests.make_capture;execute_independent=ui_fixtures.UIContractTests.execute_independent;record=ui_fixtures.UIContractTests.record;pixels=ui_fixtures.UIContractTests.pixels
    def test_archive_passes_after_original_inputs_removed_and_corruption_blocks_retirement(self):
        self.pixels();self.state.update(task='Recovery',active=False,complete=False,phase='SHIP')
        root=self.root/'checkout';root.mkdir();checkpoint=root/'.deep-fixture1';checkpoint.mkdir()
        save(checkpoint/'state.json',self.state);(checkpoint/'plan.md').write_text('Recovery')
        archive=self.root/'archive'
        args=argparse.Namespace(root=str(root),path=str(checkpoint),session=None,destination=str(archive),include=[],checkpoint_only=True)
        original_contract=self.path.read_bytes();deep_loop.preserve(args)
        for p in list(self.root.iterdir()):
            if p not in (root,archive):
                shutil.rmtree(p) if p.is_dir() else p.unlink()
        relocated=self.root/'relocated-archive';archive.rename(relocated);archive=relocated
        deep_loop.verify_archive(archive)
        saved=json.loads((archive/'archive.json').read_text());mapped=saved['resolution']['files'][str(self.path.resolve())]
        resolution_path=archive/'resolution.json';resolution_bytes=resolution_path.read_bytes()
        mapping=json.loads(resolution_bytes);del mapping['files'][str(self.actual.resolve())]
        save(resolution_path,mapping)
        with self.assertRaises((ValueError,OSError)):deep_loop.retire_checkpoint(argparse.Namespace(root=str(root),archive=str(archive)))
        self.assertTrue(checkpoint.exists());resolution_path.write_bytes(resolution_bytes)
        copy_path=archive/mapped['path'];self.assertEqual(copy_path.read_bytes(),original_contract)
        preimage=copy_path.read_bytes();copy_path.write_bytes(b'corrupt')
        with self.assertRaises((ValueError,OSError)):deep_loop.retire_checkpoint(argparse.Namespace(root=str(root),archive=str(archive)))
        self.assertTrue(checkpoint.exists());copy_path.write_bytes(preimage)
        deep_loop.retire_checkpoint(argparse.Namespace(root=str(root),archive=str(archive)))
        evidence=self.root/'closeout.txt';evidence.write_text('Readback checkpoint removed')
        deep_loop.finalize_archive(argparse.Namespace(archive=str(archive),evidence=str(evidence)))
        self.assertEqual(deep_loop.validate(argparse.Namespace(root=str(archive),path=str(archive/'checkpoint'),session=None,stage='ship',mode='fail')),0)

if __name__=='__main__':unittest.main()
