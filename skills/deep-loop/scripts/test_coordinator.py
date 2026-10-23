import json,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class CoordinatorTests(unittest.TestCase):
 def setUp(self):
  t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.d=Path(t.name);self.db=self.d/'db.sqlite';self.plan=self.d/'plan.json'
  self.jobs=[dict(id='a',deps=[],workspace='work/a',protected=False,authorized=False),dict(id='b',deps=['a'],workspace='work/b',protected=False,authorized=False)]
 def cmd(self,action,*args,ok=True):
  if action=='verify' and '--token' not in args:args=(*args,'--token',str(getattr(self,'token',1)))
  env=None
  if action=='verify' and ok:
   from test_trust import proof_fixture
   import os
   signed,_=proof_fixture(self.d,b'synthetic-test-key-only-0123456789');args=(*args,*signed);env=dict(os.environ,DEEP_LOOP_VERIFIER_SECRET='synthetic-test-key-only-0123456789')
  p=subprocess.run([sys.executable,str(ROOT/'scripts/coordinator.py'),str(self.db),action,*args],capture_output=True,text=True,env=env)
  self.assertEqual(p.returncode,0,p.stderr) if ok else self.assertNotEqual(p.returncode,0)
  result=json.loads(p.stdout) if p.returncode==0 else None
  if action=='lease' and result:self.token=result['token']
  return result
 def init(self):self.plan.write_text(json.dumps({'jobs':self.jobs}));self.cmd('init','--plan',str(self.plan))
 def test_dependency_and_independent_proof(self):
  self.init();a=self.cmd('lease','--worker','builder','--now','0');self.assertEqual(a['job'],'a');self.assertIsNone(self.cmd('lease','--worker','other','--now','0'))
  self.cmd('submit','--job','a','--worker','builder','--token',str(a['token']),'--result','artifact','--now','1')
  self.cmd('verify','--job','a','--worker','builder','--result','verified:manifest',ok=False)
  self.cmd('verify','--job','a','--worker','reviewer','--result','verified:manifest')
  self.assertEqual(self.cmd('lease','--worker','builder','--now','2')['job'],'b')
 def test_stale_worker(self):
  self.init();a=self.cmd('lease','--worker','one','--now','0','--ttl','2');self.assertEqual(self.cmd('expire','--now','3')['blocked'],['a']);self.cmd('submit','--job','a','--worker','one','--token',str(a['token']),'--result','x','--now','3',ok=False)
 def test_double_claim(self):
  self.init();self.cmd('lease','--worker','one','--now','0');self.assertIsNone(self.cmd('lease','--worker','two','--now','0'))
 def test_protected(self):
  self.jobs[0]['protected']=True;self.init();self.assertIsNone(self.cmd('lease','--worker','one'))
 def test_duplicate_workspace(self):
  self.jobs[1]['workspace']='work/a';self.plan.write_text(json.dumps({'jobs':self.jobs}));self.cmd('init','--plan',str(self.plan),ok=False)
 def test_cycle(self):
  self.jobs[0]['deps']=['b'];self.plan.write_text(json.dumps({'jobs':self.jobs}));self.cmd('init','--plan',str(self.plan),ok=False)
 def test_unverified_rejected(self):
  self.init();a=self.cmd('lease','--worker','one');self.cmd('submit','--job','a','--worker','one','--token',str(a['token']),'--result','x');self.cmd('verify','--job','a','--worker','two','--result','manifest',ok=False)
 def test_journal(self):
  self.init();self.cmd('lease','--worker','one');self.assertEqual(self.cmd('events')[-1]['kind'],'leased')
 def test_bad_plan_creates_no_database(self):
  self.plan.write_text('{"jobs":[]}');self.cmd('init','--plan',str(self.plan),ok=False);self.assertFalse(self.db.exists())
 def test_missing_status_creates_no_database(self):
  self.cmd('status',ok=False);self.assertFalse(self.db.exists())
 def test_nan_ttl_rejected(self):
  self.init();self.cmd('lease','--worker','one','--ttl','nan',ok=False)
 def test_nan_now_rejected(self):
  self.init();self.cmd('lease','--worker','one','--now','nan',ok=False);self.assertEqual(self.cmd('status')[0]['state'],'ready')
 def test_stale_review_token_rejected(self):
  self.init();a=self.cmd('lease','--worker','one');self.cmd('submit','--job','a','--worker','one','--token',str(a['token']),'--result','x');self.cmd('verify','--job','a','--worker','two','--token',str(a['token']+1),'--result','verified:manifest',ok=False)
 def test_empty_verified_reference_rejected(self):
  self.init();a=self.cmd('lease','--worker','one');self.cmd('submit','--job','a','--worker','one','--token',str(a['token']),'--result','x');self.cmd('verify','--job','a','--worker','two','--result','verified:',ok=False)
 def test_foreign_wal_preserved(self):
  code="import sqlite3,os,sys;d=sqlite3.connect(sys.argv[1]);d.execute('PRAGMA journal_mode=WAL');d.execute('CREATE TABLE private(value TEXT)');d.execute(\"INSERT INTO private VALUES('keep')\");d.commit();os._exit(0)"
  subprocess.run([sys.executable,'-c',code,str(self.db)],check=True);before={name:(self.d/name).read_bytes() for name in ['db.sqlite','db.sqlite-wal']}
  self.plan.write_text(json.dumps({'jobs':self.jobs}));self.cmd('init','--plan',str(self.plan),ok=False)
  for name,value in before.items():self.assertTrue((self.d/name).exists());self.assertEqual((self.d/name).read_bytes(),value)
 def test_status_readonly(self):
  self.init();before=self.db.read_bytes();self.cmd('status');self.cmd('events');self.assertEqual(self.db.read_bytes(),before)
 def test_concurrent_claims(self):
  self.init();args=[sys.executable,str(ROOT/'scripts/coordinator.py'),str(self.db),'lease','--worker','one']
  procs=[subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)];results=[]
  for proc in procs:
   out,err=proc.communicate(timeout=15);self.assertEqual(proc.returncode,0,err);results.append(json.loads(out))
  self.assertEqual(sum(result is not None for result in results),1);self.assertEqual(self.cmd('status')[0]['generation'],1)
 def test_real_lease_clock_sampled_after_lock(self):
  from unittest.mock import patch
  from contextlib import redirect_stdout
  import coordinator,io
  self.init();out=io.StringIO()
  argv=['coordinator',str(self.db),'lease','--worker','one','--ttl','1']
  with patch.object(sys,'argv',argv),patch.object(coordinator.time,'time',side_effect=[100,200]),redirect_stdout(out):
   self.assertEqual(coordinator.main(),0)
  self.assertEqual(json.loads(out.getvalue())['deadline'],201)
 def test_submit_expired_while_waiting_for_lock(self):
  from unittest.mock import patch
  from contextlib import redirect_stderr
  import coordinator,io
  self.init();a=self.cmd('lease','--worker','one','--now','100','--ttl','1')
  argv=['coordinator',str(self.db),'submit','--job','a','--worker','one','--token',str(a['token']),'--result','late']
  with patch.object(sys,'argv',argv),patch.object(coordinator.time,'time',side_effect=[100,200]),redirect_stderr(io.StringIO()):
   self.assertEqual(coordinator.main(),1)
  self.assertEqual(self.cmd('status')[0]['state'],'leased')
 def test_graph_reinitialization_rejected(self):
  self.init();before=self.cmd('status');self.jobs=[dict(id='other',deps=[],workspace='work/other',protected=False,authorized=False)];self.plan.write_text(json.dumps({'jobs':self.jobs}));self.cmd('init','--plan',str(self.plan),ok=False);self.assertEqual(self.cmd('status'),before)
 def test_malformed_job_rejected_cleanly(self):
  self.plan.write_text('{"jobs":[null]}');self.cmd('init','--plan',str(self.plan),ok=False);self.assertFalse(self.db.exists())
if __name__=='__main__':unittest.main()
