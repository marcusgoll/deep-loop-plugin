import sys, unittest, json, subprocess, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from github_adapter import normalize
H='a'*40

def fixture():
    return {'repository':{'full_name':'owner/repo','governance':{'inspected':True},'required_checks':['CI']},'pull_request':{'number':1,'head_sha':H,'review_decision':'APPROVED','mergeable':True,'state':'open'},'checked_head_sha':H,'checks':[{'name':'CI','head_sha':H,'conclusion':'success'}]}

class GitHubTests(unittest.TestCase):
    def test_ready_is_not_authorized(self):
        r=normalize(fixture());self.assertEqual(r['readiness'],'eligible_for_further_review');self.assertEqual(r['authorization'],'not_established')
    def test_missing_check(self):
        d=fixture();d['checks']=[];self.assertEqual(normalize(d)['readiness'],'unknown')
    def test_stale_checked_head(self):
        d=fixture();d['checked_head_sha']='b'*40;self.assertEqual(normalize(d)['readiness'],'unknown')
    def test_stale_check(self):
        d=fixture();d['checks'][0]['head_sha']='b'*40;self.assertEqual(normalize(d)['readiness'],'unknown')
    def test_review_block(self):
        d=fixture();d['pull_request']['review_decision']='CHANGES_REQUESTED';self.assertEqual(normalize(d)['readiness'],'blocked')
    def test_governance_missing(self):
        d=fixture();d['repository'].pop('governance');self.assertEqual(normalize(d)['readiness'],'unknown')
    def test_missing_policy(self):
        d=fixture();d['repository'].pop('required_checks');self.assertEqual(normalize(d)['readiness'],'unknown')
    def test_duplicate_check_ambiguous(self):
        d=fixture();d['checks'].append(d['checks'][0].copy());self.assertEqual(normalize(d)['readiness'],'unknown')

    def test_missing_identity_unknown(self):
        d=fixture();d['repository'].pop('full_name');d['pull_request'].pop('number');self.assertEqual(normalize(d)['readiness'],'unknown')
    def test_invalid_identity_unknown(self):
        d=fixture();d['repository']['full_name']={};d['pull_request']['number']=True;self.assertEqual(normalize(d)['readiness'],'unknown')
    def test_bad_checked_sha_unknown(self):
        d=fixture();d['checked_head_sha']=[];r=normalize(d);self.assertEqual(r['readiness'],'unknown');self.assertIsNone(r['checked_head_sha'])
    def test_failed_required_check(self):
        d=fixture();d['checks'][0]['conclusion']='failure';self.assertEqual(normalize(d)['readiness'],'blocked')
    def test_cli_preserves_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'in.json';out=root/'out.json';source.write_text(json.dumps(fixture()));out.write_text('keep')
            r=subprocess.run([sys.executable,str(Path(__file__).with_name('github_adapter.py')),str(source),str(out)],capture_output=True,text=True);self.assertEqual(r.returncode,2);self.assertEqual(out.read_text(),'keep')
    def test_cli_invalid_no_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'in.json';out=root/'out.json';source.write_text('[]')
            r=subprocess.run([sys.executable,str(Path(__file__).with_name('github_adapter.py')),str(source),str(out)],capture_output=True,text=True);self.assertEqual(r.returncode,2);self.assertFalse(out.exists());self.assertNotIn('Traceback',r.stderr)
    def test_concurrent_output_exclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'in.json';out=root/'out.json';source.write_text(json.dumps(fixture()));args=[sys.executable,str(Path(__file__).with_name('github_adapter.py')),str(source),str(out)]
            procs=[subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(2)]
            for proc in procs:proc.communicate(timeout=10)
            self.assertEqual(sorted(proc.returncode for proc in procs),[0,2]);self.assertEqual(json.loads(out.read_text())['head_sha'],H)
if __name__=='__main__':unittest.main()
