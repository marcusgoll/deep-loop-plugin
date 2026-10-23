import copy,hashlib,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from test_contract import BASE
ROOT=Path(__file__).resolve().parents[1]
class ProofTests(unittest.TestCase):
 def setUp(self):
  t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.d=Path(t.name)
 def runpy(self,script,*args):return subprocess.run([sys.executable,str(ROOT/'scripts'/script),*map(str,args),*(['--plan',str(self.d/'plan.json')] if script=='verify_evidence.py' else [])],capture_output=True,text=True)
 def setup_proof(self,cmd,timeout=3):
  p=self.d/'plan.json';p.write_text(json.dumps({'cwd':str(self.d),'allowlist':[cmd],'checks':[{'id':'A1','argv':cmd,'timeout':timeout}]}));out=self.d/'proof.json';return p,out
 def manifest(self,proof):
  c=copy.deepcopy(BASE);c['status']='verified';c['acceptance'][0].update(status='passed',evidence=['proof']);cp=self.d/'contract.json';cp.write_text(json.dumps(c))
  m={'format':'deep-loop-evidence-v1','artifacts':[{'id':'proof','path':'proof.json','sha256':hashlib.sha256(proof.read_bytes()).hexdigest()}],'acceptance':{'A1':[{'artifact':'proof','check_id':'A1'}]}};mp=self.d/'manifest.json';mp.write_text(json.dumps(m));return cp,mp
 def test_success(self):
  p,o=self.setup_proof([sys.executable,'-c','print(1)']);self.assertEqual(self.runpy('run_proof.py',p,o).returncode,0);c,m=self.manifest(o);self.assertEqual(self.runpy('verify_evidence.py',c,m).returncode,0)
 def test_tampered(self):
  p,o=self.setup_proof([sys.executable,'-c','print(1)']);self.runpy('run_proof.py',p,o);c,m=self.manifest(o);o.write_text(o.read_text()+'x');self.assertNotEqual(self.runpy('verify_evidence.py',c,m).returncode,0)
 def test_failure(self):
  p,o=self.setup_proof([sys.executable,'-c','raise SystemExit(2)']);self.assertEqual(self.runpy('run_proof.py',p,o).returncode,1);c,m=self.manifest(o);self.assertNotEqual(self.runpy('verify_evidence.py',c,m).returncode,0)
 def test_timeout(self):
  p,o=self.setup_proof([sys.executable,'-c','import time;time.sleep(2)'],.05);self.assertEqual(self.runpy('run_proof.py',p,o).returncode,1);self.assertEqual(json.loads(o.read_text())['checks'][0]['outcome'],'timeout')
 def test_unallowlisted(self):
  p,o=self.setup_proof([sys.executable,'-c','print(1)']);data=json.loads(p.read_text());data['checks'][0]['argv']=[sys.executable,'-c','print(2)'];p.write_text(json.dumps(data));self.assertNotEqual(self.runpy('run_proof.py',p,o).returncode,0);self.assertFalse(o.exists())
 def test_no_overwrite(self):
  p,o=self.setup_proof([sys.executable,'-c','print(1)']);o.write_text('keep');self.assertNotEqual(self.runpy('run_proof.py',p,o).returncode,0);self.assertEqual(o.read_text(),'keep')
 def test_missing_evidence(self):
  cp=self.d/'contract.json';cp.write_text(json.dumps(BASE));mp=self.d/'manifest.json';mp.write_text(json.dumps({'format':'deep-loop-evidence-v1','artifacts':[],'acceptance':{}}));self.assertNotEqual(self.runpy('verify_evidence.py',cp,mp).returncode,0)
 def test_unsafe_path(self):
  p,o=self.setup_proof([sys.executable,'-c','print(1)']);self.runpy('run_proof.py',p,o);c,m=self.manifest(o);data=json.loads(m.read_text());data['artifacts'][0]['path']='../escape';m.write_text(json.dumps(data));self.assertNotEqual(self.runpy('verify_evidence.py',c,m).returncode,0)
 def test_empty_acceptance_rejected(self):
  (self.d/'plan.json').write_text(json.dumps({'cwd':str(self.d),'allowlist':[[sys.executable,'-c','print(1)']],'checks':[{'id':'A1','argv':[sys.executable,'-c','print(1)'],'timeout':3}]}));c={'acceptance':[],'status':'verified','blockers':[]};cp=self.d/'contract.json';cp.write_text(json.dumps(c));mp=self.d/'manifest.json';mp.write_text(json.dumps({'format':'deep-loop-evidence-v1','artifacts':[],'acceptance':{}}));self.assertNotEqual(self.runpy('verify_evidence.py',cp,mp).returncode,0)
 def test_prevalidate_entire_plan(self):
  marker=self.d/'marker';cmd=[sys.executable,'-c',"from pathlib import Path;Path('marker').touch()"]
  p,o=self.setup_proof(cmd);data=json.loads(p.read_text());data['checks'].append({'id':'A2','argv':['not-allowed'],'timeout':1});p.write_text(json.dumps(data));self.assertNotEqual(self.runpy('run_proof.py',p,o).returncode,0);self.assertFalse(marker.exists())
 def test_plan_drift_rejected(self):
  p,o=self.setup_proof([sys.executable,'-c','print(1)']);self.runpy('run_proof.py',p,o);c,m=self.manifest(o);p.write_text(p.read_text()+' ');self.assertNotEqual(self.runpy('verify_evidence.py',c,m).returncode,0)
 def test_substituted_argv_rejected(self):
  p,o=self.setup_proof([sys.executable,'-c','print(1)']);self.runpy('run_proof.py',p,o);data=json.loads(o.read_text());data['checks'][0]['argv']=[sys.executable,'-c','print(2)'];o.write_text(json.dumps(data));c,m=self.manifest(o);self.assertNotEqual(self.runpy('verify_evidence.py',c,m).returncode,0)
 def test_duplicate_checks_preflight(self):
  p,o=self.setup_proof([sys.executable,'-c','print(1)']);data=json.loads(p.read_text());data['checks'].append(data['checks'][0]);p.write_text(json.dumps(data));self.assertNotEqual(self.runpy('run_proof.py',p,o).returncode,0);self.assertFalse(o.exists())
 def test_launch_error_recorded(self):
  p,o=self.setup_proof([str(self.d/'missing-executable')]);self.assertEqual(self.runpy('run_proof.py',p,o).returncode,1);self.assertEqual(json.loads(o.read_text())['checks'][0]['outcome'],'error')
 def test_stop_after_failure(self):
  p,o=self.setup_proof([sys.executable,'-c','raise SystemExit(2)']);data=json.loads(p.read_text());cmd=[sys.executable,'-c',"from pathlib import Path;Path('marker').touch()"]
  data['allowlist'].append(cmd);data['checks'].append({'id':'A2','argv':cmd,'timeout':3});p.write_text(json.dumps(data));self.assertEqual(self.runpy('run_proof.py',p,o).returncode,1);self.assertFalse((self.d/'marker').exists())
 def test_malformed_manifest_rejected(self):
  p,o=self.setup_proof([sys.executable,'-c','print(1)']);self.runpy('run_proof.py',p,o);c,m=self.manifest(o);m.write_text('[]');r=self.runpy('verify_evidence.py',c,m);self.assertEqual(r.returncode,1);self.assertNotIn('Traceback',r.stderr)
 def test_extreme_timeout_rejected_cleanly(self):
  p,o=self.setup_proof([sys.executable,'-c','print(1)'],10**400);r=self.runpy('run_proof.py',p,o);self.assertEqual(r.returncode,2);self.assertNotIn('Traceback',r.stderr);self.assertFalse(o.exists())
if __name__=='__main__':unittest.main()
