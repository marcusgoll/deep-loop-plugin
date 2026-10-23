import json,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class DurableTests(unittest.TestCase):
 def setUp(self):
  t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.d=Path(t.name);self.db=self.d/'state.db';self.plan=self.d/'plan.json';self.plan.write_text(json.dumps({'steps':[{'key':'read','protected':False},{'key':'write','protected':True}],'max_attempts':2}))
 def cmd(self,action,*args,ok=True):
  if action in ('complete','fail') and '--attempt' not in args:args=(*args,'--attempt',str(getattr(self,'attempt',1)))
  p=subprocess.run([sys.executable,str(ROOT/'scripts/durable_executor.py'),str(self.db),action,'--task','t',*args],capture_output=True,text=True)
  if ok:self.assertEqual(p.returncode,0,p.stderr)
  else:self.assertNotEqual(p.returncode,0)
  result=json.loads(p.stdout) if p.returncode==0 else None
  if action=='claim' and result:self.attempt=result['attempt']
  return result
 def init(self,auth='not_granted'):self.cmd('init','--plan',str(self.plan),'--authorization',auth)
 def test_checkpoint_restart(self):
  self.init('granted_for_scope');self.cmd('claim','--key','read');self.cmd('complete','--key','read','--result','sha256:a');self.assertEqual(self.cmd('recover')['state'],'ready');self.assertEqual(self.cmd('status')['step'],1)
 def test_inflight_recovery_blocks(self):
  self.init();self.cmd('claim','--key','read');self.assertEqual(self.cmd('recover')['state'],'blocked');self.cmd('claim','--key','read',ok=False)
 def test_protected_requires_authorization(self):
  self.init();self.cmd('claim','--key','read');self.cmd('complete','--key','read','--result','ok');self.cmd('claim','--key','write',ok=False)
 def test_duplicate_completion_rejected(self):
  self.init();self.cmd('claim','--key','read');self.cmd('complete','--key','read','--result','ok');self.cmd('complete','--key','read','--result','ok',ok=False)
 def test_retry_budget(self):
  self.init();self.cmd('claim','--key','read');self.assertEqual(self.cmd('fail','--key','read')['state'],'retryable');self.cmd('claim','--key','read');self.assertEqual(self.cmd('fail','--key','read')['state'],'blocked')
 def test_wrong_key(self):
  self.init();self.cmd('claim','--key','write',ok=False)
 def test_journal(self):
  self.init();self.cmd('claim','--key','read');self.assertEqual([x['event'] for x in self.cmd('journal')],['initialized','claimed'])
 def test_no_overwrite(self):
  self.init();self.cmd('init','--plan',str(self.plan),ok=False)
 def test_invalid_plan_does_not_create_database(self):
  self.plan.write_text('{"steps":[]}');self.cmd('init','--plan',str(self.plan),ok=False);self.assertFalse(self.db.exists())
 def test_status_missing_does_not_create_database(self):
  self.cmd('status',ok=False);self.assertFalse(self.db.exists())
 def test_stale_completion_rejected(self):
  self.init();self.cmd('claim','--key','read');self.cmd('fail','--key','read');self.cmd('claim','--key','read');self.cmd('complete','--key','read','--result','old','--attempt','1',ok=False)
 def test_unrelated_database_preserved(self):
  import sqlite3,hashlib
  with sqlite3.connect(self.db) as db:db.execute('CREATE TABLE private(value TEXT)')
  db.close()
  before=self.db.read_bytes();self.cmd('init','--plan',str(self.plan),ok=False);self.assertEqual(self.db.read_bytes(),before)
 def test_status_readonly(self):
  self.init();before=self.db.read_bytes();self.cmd('status');self.cmd('journal');self.assertEqual(self.db.read_bytes(),before)
 def test_duplicate_claim_race(self):
  self.init();args=[sys.executable,str(ROOT/'scripts/durable_executor.py'),str(self.db),'claim','--task','t','--key','read']
  procs=[subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(2)]
  for proc in procs:proc.communicate(timeout=15)
  self.assertEqual(sorted(proc.returncode for proc in procs),[0,1]);self.assertEqual(self.cmd('status')['steps'][0]['attempts'],1)
 def test_malformed_init_clean_error(self):
  self.plan.write_text('[]');self.cmd('init','--plan',str(self.plan),ok=False);self.assertFalse(self.db.exists())
 def test_empty_task_rejected(self):
  result=subprocess.run([sys.executable,str(ROOT/'scripts/durable_executor.py'),str(self.db),'init','--task',' ','--plan',str(self.plan)],capture_output=True,text=True)
  self.assertNotEqual(result.returncode,0);self.assertFalse(self.db.exists())
 def test_foreign_wal_preserved(self):
  code="import sqlite3,os,sys;d=sqlite3.connect(sys.argv[1]);d.execute('PRAGMA journal_mode=WAL');d.execute('CREATE TABLE private(value TEXT)');d.execute(\"INSERT INTO private VALUES('keep')\");d.commit();os._exit(0)"
  subprocess.run([sys.executable,'-c',code,str(self.db)],check=True)
  before={name:(self.d/name).read_bytes() for name in ['state.db','state.db-wal']}
  self.cmd('init','--plan',str(self.plan),ok=False)
  for name,content in before.items():self.assertTrue((self.d/name).exists());self.assertEqual((self.d/name).read_bytes(),content)
 def test_optional_contract_hash_recorded(self):
  data=json.loads(self.plan.read_text());data['contract_sha256']='a'*64;self.plan.write_text(json.dumps(data));self.init();self.assertEqual(self.cmd('journal')[0]['payload']['contract_sha256'],'a'*64)
 def test_bad_contract_hash_no_database(self):
  data=json.loads(self.plan.read_text());data['contract_sha256']='bad';self.plan.write_text(json.dumps(data));self.cmd('init','--plan',str(self.plan),ok=False);self.assertFalse(self.db.exists())
if __name__=='__main__':unittest.main()
