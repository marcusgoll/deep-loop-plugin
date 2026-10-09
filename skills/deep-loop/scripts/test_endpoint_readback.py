import argparse, copy, json, shutil, sys, tempfile, unittest
from pathlib import Path
import deep_loop
import test_receipt_recovery as fixtures
from test_ui_design import save, sha

class EndpointReadbackTests(unittest.TestCase):
    def setUp(self):
        fixtures.GenericReceiptTests.setUp(self)
        self.delivered=self.root/'delivered.csv';self.delivered.write_text('id,name\n1,Alpha\n')
        self.observed=self.root/'observed.json'
        self.impl.write_text("import hashlib,json\nfrom pathlib import Path\np=Path('delivered.csv').resolve()\nPath('observed.json').write_text(json.dumps({'endpoint':'local','targets':[{'id':'single','revision':'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest(),'artifact':str(p)}]}))\n")
        self.proof['implementation']['sha256']=sha(self.impl)
        self.proof['artifacts']=[{'path':str(self.observed)},{'path':str(self.delivered)}]
        self.proof['readback']={'endpoint':'local','result':str(self.observed),'targets':[{'id':'single','artifact':str(self.delivered)}]}
        self.persist();self.state['delivery']['revision']='sha256:'+sha(self.delivered)
        self.state['checks'][0]['stage']='ship'
    def persist(self):
        save(self.path,self.contract);self.state['verificationContract']['sha256']=sha(self.path)
    def run_bound(self):return fixtures.GenericReceiptTests.run_bound(self)
    def test_pending_readback_allows_review_requires_ship_even_closeout(self):
        self.state['checks'][0].update(stage='closeout',status='pending',evidence='')
        self.assertEqual(deep_loop.contract_issues(self.state,'review'),[])
        self.assertTrue(deep_loop.contract_issues(self.state,'delivery'))
    def test_current_readback_and_exact_subject_drift(self):
        self.run_bound();self.assertEqual(deep_loop.contract_issues(self.state,'ship'),[])
        original=copy.deepcopy(self.state)
        for field,value in [('endpoint','other'),('revision','sha256:'+'0'*64),('targets',[{'id':'extra','revision':'rev'}])]:
            self.state['delivery'][field]=value
            self.assertTrue(deep_loop.contract_issues(self.state,'ship'),field);self.state=copy.deepcopy(original)
        self.delivered.write_text('changed');self.assertTrue(deep_loop.contract_issues(self.state,'ship'))
    def test_substituted_observation_rejected_even_with_receipt_digest_updated(self):
        receipt=self.run_bound();rows=json.loads(receipt.read_text());rows[0]['readback']={'endpoint':'local','targets':[]};save(receipt,rows)
        self.state['checks'][0]['receipt']['sha256']=sha(receipt)
        self.assertTrue(deep_loop.contract_issues(self.state,'ship'))
    def test_malformed_observation_fails_runner(self):
        script=self.impl.read_text()
        for name,result in [('endpoint',{'endpoint':'other','targets':[]}),('duplicate',{'endpoint':'local','targets':[{'id':'single','revision':'x','artifact':str(self.delivered)}]*2}),('digest',{'endpoint':'local','targets':[{'id':'single','revision':'sha256:'+'0'*64,'artifact':str(self.delivered)}]})]:
            self.observed.unlink(missing_ok=True)
            self.impl.write_text('from pathlib import Path\nPath("observed.json").write_text('+repr(json.dumps(result))+')')
            self.proof['implementation']['sha256']=sha(self.impl);self.persist()
            out=self.root/(name+'.receipt');batch=save(self.root/'checks.json',[{'name':'V1','verifierId':'V1','argv':self.proof['argv']}])
            args=argparse.Namespace(root=str(self.root),checks=str(batch),output=str(out),contract=str(self.path),goal_id='receipt1',ui_request=None,source_manifest=None,environment_manifest=None)
            self.assertNotEqual(deep_loop.run_checks(args),0,name)
    def test_observer_must_not_modify_delivered_bytes(self):
        self.impl.write_text("from pathlib import Path\nPath('delivered.csv').write_text('modified')\n"+self.impl.read_text())
        self.proof['implementation']['sha256']=sha(self.impl);self.persist()
        with self.assertRaises(AssertionError):self.run_bound()
    def test_complete_and_repeat_complete_block_without_terminal_mutation(self):
        self.run_bound();checkpoint=self.root/'.deep-receipt1';checkpoint.mkdir();(checkpoint/'plan.md').write_text('Deliver CSV')
        self.state.update(task='Deliver CSV',active=True,complete=False,phase='SHIP');save(checkpoint/'state.json',self.state)
        args=argparse.Namespace(root=str(self.root),path=str(checkpoint),session=None)
        self.assertEqual(deep_loop.complete_session(args),0)
        state_path=checkpoint/'state.json';before=state_path.read_bytes();self.delivered.write_text('drift')
        self.assertNotEqual(deep_loop.complete_session(args),0);self.assertEqual(before,state_path.read_bytes())
    def test_archive_resolution_after_original_removal_and_relocation(self):
        self.run_bound();checkout=self.root/'checkout';checkout.mkdir();checkpoint=checkout/'.deep-receipt1';checkpoint.mkdir()
        self.state.update(task='Deliver CSV',active=False,complete=False,phase='SHIP');save(checkpoint/'state.json',self.state);(checkpoint/'plan.md').write_text('Deliver CSV')
        archive=self.root/'archive';deep_loop.preserve(argparse.Namespace(root=str(checkout),path=str(checkpoint),session=None,destination=str(archive),include=[],checkpoint_only=True))
        deep_loop.retire_checkpoint(argparse.Namespace(root=str(checkout),archive=str(archive)))
        for p in (self.path,self.impl,self.manifest,self.env,self.source,self.delivered,self.observed,self.root/'receipt.json'):p.unlink()
        moved=self.root/'relocated';shutil.move(archive,moved);deep_loop.verify_archive(moved)
        evidence=self.root/'closeout.txt';evidence.write_text('Selected checkpoint retired')
        self.assertEqual(deep_loop.finalize_archive(argparse.Namespace(root=str(checkout),archive=str(moved),evidence=str(evidence))),0)
    def test_manual_and_advisory_structured_readback_rejected(self):
        for mutation in ('manual','advisory'):
            original=copy.deepcopy(self.contract)
            if mutation=='manual':self.proof['mode']='manual';self.proof['reason']='Explicit legacy'
            else:self.contract['verifiers'][0]['gate']='advisory'
            self.persist();self.assertTrue(deep_loop.contract_issues(self.state,'build'))
            self.contract=original;self.proof=self.contract['verifiers'][0]['proof']
    def test_exact_multi_target_external_revision_requires_explicit_kind(self):
        second=self.root/'adapter.json';second.write_text('adapter observation')
        self.proof['readback']['targets'].append({'id':'remote','artifact':str(second),'revision_kind':'external'})
        self.proof['artifacts'].append({'path':str(second)})
        rows=[{'id':'single','revision':'sha256:'+sha(self.delivered),'artifact':str(self.delivered.resolve())}, {'id':'remote','revision':'commit-123','artifact':str(second.resolve())}]
        self.impl.write_text('from pathlib import Path\nPath("observed.json").write_text('+repr(json.dumps({'endpoint':'local','targets':rows}))+')')
        self.proof['implementation']['sha256']=sha(self.impl);self.persist()
        self.state['delivery']['targets']=[{'id':r['id'],'revision':r['revision']} for r in rows]
        self.run_bound();self.assertEqual(deep_loop.contract_issues(self.state,'ship'),[])
        self.state['delivery']['targets'][1]['revision']='commit-other';self.assertTrue(deep_loop.contract_issues(self.state,'ship'))
        self.proof['readback']['targets'][1].pop('revision_kind');self.persist();self.assertTrue(deep_loop.contract_issues(self.state,'ship'))
    def test_result_alias_and_missing_required_future_proof_refuse_preservation(self):
        self.proof['readback']['result']=str(self.delivered);self.persist()
        self.assertTrue(deep_loop.contract_issues(self.state,'build'))
        self.proof['readback']['result']=str(self.observed);self.persist()
        checkout=self.root/'checkout';checkout.mkdir();checkpoint=checkout/'.deep-receipt1';checkpoint.mkdir()
        self.state.update(task='Future proof',active=False,complete=False,phase='SHIP');self.state['checks'][0].update(stage='closeout',status='pending',evidence='')
        save(checkpoint/'state.json',self.state);(checkpoint/'plan.md').write_text('Future proof')
        archive=self.root/'archive'
        with self.assertRaises(ValueError):deep_loop.preserve(argparse.Namespace(root=str(checkout),path=str(checkpoint),session=None,destination=str(archive),include=[],checkpoint_only=True))
        self.assertTrue(checkpoint.exists());self.assertFalse(archive.exists())
    def test_existing_readback_output_refused_before_receipt_creation(self):
        self.observed.write_text('{}')
        batch=save(self.root/'checks.json',[{'name':'V1','verifierId':'V1','argv':self.proof['argv']}]);out=self.root/'receipt.json'
        args=argparse.Namespace(root=str(self.root),checks=str(batch),output=str(out),contract=str(self.path),goal_id='receipt1',ui_request=None,source_manifest=None,environment_manifest=None)
        with self.assertRaises(ValueError):deep_loop.run_checks(args)
        self.assertFalse(out.exists());self.assertEqual(self.observed.read_text(),'{}')
    def test_bind_defaults_readback_to_ship(self):
        checkpoint=self.root/'.deep-receipt1';checkpoint.mkdir();self.state['checks']=[];save(checkpoint/'state.json',self.state)
        deep_loop.bind_contract(argparse.Namespace(root=str(self.root),path=str(checkpoint),session=None,contract=str(self.path),endpoint='local',ui_request=None))
        self.assertEqual(json.loads((checkpoint/'state.json').read_text())['checks'][0]['stage'],'ship')
        rebound=json.loads((checkpoint/'state.json').read_text());rebound['checks'][0]['stage']='review';save(checkpoint/'state.json',rebound)
        deep_loop.bind_contract(argparse.Namespace(root=str(self.root),path=str(checkpoint),session=None,contract=str(self.path),endpoint='local',ui_request=None))
        self.assertEqual(json.loads((checkpoint/'state.json').read_text())['checks'][0]['stage'],'ship')

if __name__=='__main__':unittest.main()
