import json,tempfile,unittest,sys,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from workflow import execute
class WorkflowTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.d=Path(self.tmp.name)
  self.contract=self.d/'contract.json';self.contract.write_text(json.dumps({'id':'x','question':'Does it work?','build':'fixture','why':'reliability','prove':'replay','route':'small_fix','scope':{'included':['x'],'excluded':[]},'constraints':[],'authorization':'granted_for_scope','status':'ready','acceptance':[{'id':'a','question':'works?','method':'fixture','expected':'pass','status':'pending','evidence':[]}],'blockers':[]}))
  self.spec={'contract':str(self.contract),'database':str(self.d/'state.sqlite'),'task':'t','authorization':'granted_for_scope','steps':[{'key':'one','protected':False,'result':'pass'}]}
 def test_complete(self):self.assertEqual(execute(self.spec)['state'],'completed')
 def test_resume_completed(self):execute(self.spec);self.assertEqual(execute(self.spec)['state'],'completed')
 def test_fail_retryable(self):self.spec['steps'][0]['result']='fail';self.assertEqual(execute(self.spec)['state'],'retryable')
 def test_protected_blocked(self):self.spec['authorization']='not_granted';self.spec['steps'][0]['protected']=True;self.assertEqual(execute(self.spec)['state'],'blocked')
 def test_plan_mismatch(self):execute(self.spec);self.spec['steps'][0]['key']='changed';self.assertRaises(ValueError,execute,self.spec)
 def test_bad_contract(self):self.contract.write_text('{}');self.assertRaises(ValueError,execute,self.spec)
 def test_duplicate_keys(self):self.spec['steps']*=2;self.assertRaises(ValueError,execute,self.spec)
 def test_running_recovery(self):
  from workflow import call
  execute(self.spec);self.spec['task']='u';self.spec['database']=str(self.d/'other.sqlite');self.spec['steps'][0]['result']='fail';execute(self.spec)
  call('durable_executor.py',self.spec['database'],'claim','--task','u','--key','one')
  self.assertEqual(execute(self.spec)['state'],'blocked')
 def test_contract_drift_rejected(self):
  execute(self.spec);self.contract.write_text(self.contract.read_text()+' ');self.assertRaises(ValueError,execute,self.spec)
 def test_protection_drift_rejected(self):
  execute(self.spec);self.spec['steps'][0]['protected']=True;self.assertRaises(ValueError,execute,self.spec)
 def test_authority_drift_rejected(self):
  execute(self.spec);self.spec['authorization']='not_granted';self.assertRaises(ValueError,execute,self.spec)
 def test_invalid_result_no_database(self):
  self.spec['steps'][0]['result']='anything';self.assertRaises(ValueError,execute,self.spec);self.assertFalse(Path(self.spec['database']).exists())
 def test_invalid_step_shape(self):
  self.spec['steps']=[None];self.assertRaises(ValueError,execute,self.spec);self.assertFalse(Path(self.spec['database']).exists())
 def test_cli_output_collision_no_journal(self):
  source=self.d/'spec.json';source.write_text(json.dumps(self.spec));out=self.d/'out.json';out.write_text('keep')
  r=subprocess.run([sys.executable,str(ROOT/'scripts/workflow.py'),str(source),str(out)],capture_output=True);self.assertEqual(r.returncode,2);self.assertEqual(out.read_text(),'keep');self.assertFalse(Path(self.spec['database']).exists())
 def test_output_database_alias_rejected(self):
  source=self.d/'spec.json';source.write_text(json.dumps(self.spec))
  for suffix in ('','-wal','-shm','-journal'):
   out=Path(self.spec['database']+suffix);r=subprocess.run([sys.executable,str(ROOT/'scripts/workflow.py'),str(source),str(out)],capture_output=True);self.assertEqual(r.returncode,2);self.assertFalse(out.exists())
 def test_running_owner_not_recovered(self):
  from workflow import call
  self.spec['steps'][0]['result']='fail';execute(self.spec);claim=call('durable_executor.py',self.spec['database'],'claim','--task','t','--key','one')
  self.assertEqual(execute(self.spec)['state'],'blocked');self.assertEqual(call('durable_executor.py',self.spec['database'],'status','--task','t')['state'],'running')
  self.assertEqual(call('durable_executor.py',self.spec['database'],'complete','--task','t','--key','one','--attempt',claim['attempt'],'--result','original owner')['state'],'completed')
if __name__=='__main__':unittest.main()
