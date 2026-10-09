import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HELPER = Path(__file__).with_name('deep_loop.py')
class IndependentChecks(unittest.TestCase):
    def run_batch(self, rows, collect=True, existing=False):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        root=Path(temp.name); (root/'checks.json').write_text(json.dumps(rows))
        if existing: (root/'out.json').write_text('retained')
        cmd=[sys.executable,str(HELPER),'--root',str(root),'run-checks','--checks',str(root/'checks.json'),'--output',str(root/'out.json')]
        if collect: cmd.append('--collect-independent')
        result=subprocess.run(cmd,capture_output=True,text=True)
        return root,result
    def check(self,id,exit=0,deps=None,safe=True,required=True):
        return dict(id=id,name=id,argv=[sys.executable,'-c',f'import sys; print("out"); print("err",file=sys.stderr); sys.exit({exit})'],safe=safe,dependsOn=deps or [],required=required)
    def test_collect_and_skip(self):
        root,r=self.run_batch([self.check('bad',7),self.check('child',deps=['bad']),self.check('unsafe',safe=False),self.check('good')])
        self.assertNotEqual(r.returncode,0); rows=json.loads((root/'out.json').read_text())
        self.assertEqual([x['status'] for x in rows],['failed','skipped','skipped','passed'])
        self.assertEqual(rows[0]['nativeExitCode'],7); self.assertEqual(rows[0]['nativeStdout'],'out\n');self.assertEqual(rows[0]['nativeStderr'],'err\n')
        self.assertIsNone(rows[1]['exitCode']);self.assertIn('bad',rows[1]['reason'])
    def test_default_stop_first(self):
        root,r=self.run_batch([self.check('bad',7),self.check('good')],False)
        self.assertEqual(r.returncode,7);self.assertEqual(len(json.loads((root/'out.json').read_text())),1)
    def test_optional_failure_still_blocks(self):
        root,r=self.run_batch([self.check('bad',7,required=False),self.check('good')]);self.assertNotEqual(r.returncode,0)
    def test_optional_unsafe_skip(self):
        root,r=self.run_batch([self.check('unsafe',safe=False,required=False),self.check('good')]);self.assertEqual(r.returncode,0)
    def test_forward_dependency(self):
        root,r=self.run_batch([self.check('child',deps=['parent']),self.check('parent')]);self.assertEqual(r.returncode,0)
        self.assertEqual([x['id'] for x in json.loads((root/'out.json').read_text())],['parent','child'])
    def test_invalid_no_output(self):
        invalid=[]
        for patch in [{'id':''},{'safe':'yes'},{'dependsOn':['missing']},{'required':'yes'},{'dependsOn':['a','a']}]:
            row=self.check('a');row.update(patch);invalid.append([row])
        invalid += [[self.check('a'),self.check('a')],[self.check('a',deps=['b']),self.check('b',deps=['a'])]]
        for rows in invalid:
            with self.subTest(rows=rows):
                root,r=self.run_batch(rows);self.assertNotEqual(r.returncode,0);self.assertFalse((root/'out.json').exists())
    def test_launch_failure_is_not_native_exit(self):
        row=self.check("missing");row["argv"]=["/nonexistent/deep-loop-test-command"]
        root,r=self.run_batch([row,self.check("good")]);self.assertNotEqual(r.returncode,0)
        rows=json.loads((root/"out.json").read_text());self.assertIsNone(rows[0]["nativeExitCode"]);self.assertIn("launchError",rows[0]);self.assertEqual(rows[1]["status"],"passed")
    def test_prior_output_preserved(self):
        root,r=self.run_batch([self.check('a')],existing=True);self.assertNotEqual(r.returncode,0);self.assertEqual((root/'out.json').read_text(),'retained')
import argparse
import deep_loop
import test_receipt_recovery as fixtures
from test_ui_design import save, sha
class BoundCollection(unittest.TestCase):
    def setUp(self): fixtures.GenericReceiptTests.setUp(self)
    def args(self, safe=True, required=None):
        row=dict(id='a',name='V1',verifierId='V1',argv=self.proof['argv'],safe=safe,dependsOn=[])
        if required is not None: row['required']=required
        batch=save(self.root/'checks.json',[row]);self.out=self.root/'receipt.json'
        return argparse.Namespace(root=str(self.root),checks=str(batch),output=str(self.out),contract=str(self.path),goal_id='receipt1',ui_request=None,source_manifest=None,environment_manifest=None,collect_independent=True)
    def test_bound_required_cannot_downgrade(self):
        with self.assertRaises(ValueError): deep_loop.run_checks(self.args(required=False))
        self.assertFalse(self.out.exists());self.assertFalse((self.root/'result.txt').exists())
    def test_skip_cannot_supply_receipt(self):
        self.assertNotEqual(deep_loop.run_checks(self.args(safe=False)),0)
        self.state['checks'][0]['receipt']={'path':str(self.out),'sha256':sha(self.out)}
        self.assertTrue(deep_loop.contract_issues(self.state,'review'))
        self.assertNotIn('proof_mode',json.loads(self.out.read_text())[0])
    def test_bound_pass_and_drift_native_preserved(self):
        self.impl.write_text("from pathlib import Path\nPath('input.txt').write_text('drift')\nPath('result.txt').write_text('verified')")
        self.proof['implementation']['sha256']=sha(self.impl);save(self.path,self.contract)
        self.assertNotEqual(deep_loop.run_checks(self.args()),0)
        row=json.loads(self.out.read_text())[0];self.assertEqual(row['nativeExitCode'],0);self.assertEqual(row['status'],'failed')
        self.state['verificationContract']['sha256']=sha(self.path);self.state['checks'][0]['receipt']={'path':str(self.out),'sha256':sha(self.out)}
        self.assertTrue(deep_loop.contract_issues(self.state,'review'))
    def test_bound_success_is_compatible(self):
        self.assertEqual(deep_loop.run_checks(self.args()),0)
        self.state['checks'][0]['receipt']={'path':str(self.out),'sha256':sha(self.out)}
        self.assertEqual(deep_loop.contract_issues(self.state,'review'),[])
import test_endpoint_readback as readback_fixture
class ReadbackCollection(BoundCollection):
    def test_skip_cannot_supply_receipt(self):
        self.assertNotEqual(deep_loop.run_checks(self.args(safe=False)),0)
        self.state['checks'][0]['receipt']={'path':str(self.out),'sha256':sha(self.out)}
        self.assertTrue(deep_loop.contract_issues(self.state,'ship'))
    def persist(self): readback_fixture.EndpointReadbackTests.persist(self)
    def setUp(self): readback_fixture.EndpointReadbackTests.setUp(self)
    def test_bound_success_is_compatible(self):
        self.assertEqual(deep_loop.run_checks(self.args()),0)
        self.state['checks'][0]['receipt']={'path':str(self.out),'sha256':sha(self.out)}
        self.assertEqual(deep_loop.contract_issues(self.state,'ship'),[])
        self.delivered.write_text('drift');self.assertTrue(deep_loop.contract_issues(self.state,'ship'))
    def test_bound_pass_and_drift_native_preserved(self):
        self.impl.write_text("from pathlib import Path\nPath('delivered.csv').write_text('modified')\n"+self.impl.read_text())
        self.proof['implementation']['sha256']=sha(self.impl);self.persist()
        self.assertNotEqual(deep_loop.run_checks(self.args()),0)
        row=json.loads(self.out.read_text())[0];self.assertEqual(row['nativeExitCode'],0);self.assertEqual(row['status'],'failed')
import test_ui_design as ui_fixture
class UICollection(unittest.TestCase):
    def test_ui_skip_not_accepted(self):
        f=ui_fixture.UIContractTests();self.addCleanup(f.doCleanups);f.setUp()
        batch=save(f.root/'collect.json',[dict(id=v['id'],name=v['id'],verifierId=v['id'],argv=v['argv'],safe=False,dependsOn=[]) for v in f.contract['verifiers'] if 'max_diff_ratio' not in v['threshold']])
        out=f.root/'collected.json'
        args=argparse.Namespace(root=str(f.root),checks=str(batch),output=str(out),ui_request=str(f.request),contract=str(f.path),goal_id='fixture1',source_manifest=str(f.manifest),environment_manifest=str(f.environment),collect_independent=True)
        self.assertNotEqual(deep_loop.run_checks(args),0)
        f.state['uiEvidence']['invocations']={'path':str(out),'sha256':sha(out)}
        self.assertTrue(deep_loop.contract_issues(f.state,'review'))
        self.assertTrue(all(r['status']=='skipped' and 'verifier_id' not in r for r in json.loads(out.read_text())))
if __name__=='__main__': unittest.main()
