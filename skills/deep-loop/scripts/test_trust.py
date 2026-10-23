import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from worker_identity import issue,validate
from trusted_verifier import validate as validate_proof
from test_contract import BASE
ROOT=Path(__file__).resolve().parents[1]


def proof_fixture(directory, secret, job='a', worker='reviewer', generation=1):
    plan=directory/'proof-plan.json'
    argv=[sys.executable,'-c','print("fixture acceptance")']
    plan.write_text(json.dumps({'cwd':str(directory),'allowlist':[argv],'checks':[{'id':'A1','argv':argv,'timeout':3}]}),encoding='utf-8')
    proof=directory/'proof.json'
    subprocess.run([sys.executable,'-B',str(ROOT/'scripts/run_proof.py'),str(plan),str(proof)],check=True,capture_output=True)
    c=copy.deepcopy(BASE);c['status']='verified';c['acceptance'][0].update(status='passed',evidence=['proof'])
    contract=directory/'contract.json';contract.write_text(json.dumps(c),encoding='utf-8')
    manifest=directory/'manifest.json';manifest.write_text(json.dumps({'format':'deep-loop-evidence-v1','artifacts':[{'id':'proof','path':'proof.json','sha256':hashlib.sha256(proof.read_bytes()).hexdigest()}],'acceptance':{'A1':[{'artifact':'proof','check_id':'A1'}]}}),encoding='utf-8')
    bindings=validate_proof(contract,manifest,plan)
    token=issue(secret,worker,'verifier',job,generation=generation,bindings=bindings)
    return ['--capability',token,'--contract',str(contract),'--manifest',str(manifest),'--proof-plan',str(plan)],bindings


class TrustTests(unittest.TestCase):
 def setUp(self):
  temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.d=Path(temporary.name);self.db=self.d/'coordinator.db';self.secret=b'synthetic-test-key-only-0123456789';self.bindings={k:'a'*64 for k in ('contract_sha256','manifest_sha256','plan_sha256')}
 def cmd(self,action,*args,ok=True,secret=None):
  env=dict(os.environ,DEEP_LOOP_VERIFIER_SECRET=self.secret.decode() if secret is None else secret)
  r=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/coordinator.py'),str(self.db),action,*map(str,args)],capture_output=True,text=True,env=env)
  self.assertEqual(r.returncode,0,r.stderr) if ok else self.assertNotEqual(r.returncode,0)
  return json.loads(r.stdout) if r.returncode==0 else None
 def submitted(self):
  plan=self.d/'jobs.json';plan.write_text(json.dumps({'jobs':[{'id':'a','deps':[],'workspace':'a','protected':False,'authorized':False}]}));self.cmd('init','--plan',plan);lease=self.cmd('lease','--worker','builder');self.cmd('submit','--job','a','--worker','builder','--token',lease['token'],'--result','scoped fixture');return lease['token']
 def test_weak_secret_rejected(self):
  with self.assertRaises(ValueError):issue(b'weak','v','verifier','a',bindings=self.bindings)
 def test_capability_scope_and_expiry(self):
  token=issue(self.secret,'v','verifier','a',now=100,bindings=self.bindings)
  self.assertEqual(validate(self.secret,token,'a','verifier',now=101,bindings=self.bindings),'v')
  for job,role,now in [('b','verifier',101),('a','builder',101),('a','verifier',401)]:
   with self.assertRaises(ValueError):validate(self.secret,token,job,role,now=now,bindings=self.bindings)
 def test_issued_expiry_stays_in_clock_range(self):
  with self.assertRaises(ValueError):issue(self.secret,'v','verifier','a',now=1e15-1,ttl=2,bindings=self.bindings)
 def test_issued_token_fits_validator(self):
  for worker,job in [('v'*9000,'a'),('v','a'*9000)]:
   with self.assertRaises(ValueError):issue(self.secret,worker,'verifier',job,bindings=self.bindings)
 def test_generation_binding(self):
  token=issue(self.secret,'v','verifier','a',bindings=self.bindings)
  with self.assertRaises(ValueError):validate(self.secret,token,'a','verifier',generation=2,bindings=self.bindings)
 def test_input_binding(self):
  token=issue(self.secret,'v','verifier','a',bindings=self.bindings);changed=dict(self.bindings,contract_sha256='b'*64)
  with self.assertRaises(ValueError):validate(self.secret,token,'a','verifier',bindings=changed)
 def test_bad_signature(self):
  token=issue(self.secret,'v','verifier','a',bindings=self.bindings)
  with self.assertRaises(ValueError):validate(b'other-synthetic-test-key-0123456789',token,'a','verifier',bindings=self.bindings)
 def test_malformed_tokens(self):
  for token in [None,'not-a-token','!!!.'+'a'*64,'x'*9000]:
   with self.assertRaises(ValueError):validate(self.secret,token,'a','verifier',bindings=self.bindings)
 def test_invalid_clock(self):
  for now in [float('nan'),float('inf'),-1,10**400]:
   with self.assertRaises(ValueError):issue(self.secret,'v','verifier','a',now=now,bindings=self.bindings)
 def test_missing_evidence_arguments_rejected(self):
  self.submitted();self.cmd('verify','--job','a','--worker','reviewer','--token','1','--result','verified:fake',ok=False)
 def test_valid_evidence_promotes(self):
  self.submitted();args,_=proof_fixture(self.d,self.secret);self.assertEqual(self.cmd('verify','--job','a','--worker','reviewer','--token','1',*args)['state'],'proven')
 def test_builder_cannot_verify(self):
  self.submitted();args,_=proof_fixture(self.d,self.secret,worker='builder');self.cmd('verify','--job','a','--worker','builder','--token','1',*args,ok=False)
 def test_tampering_rejected(self):
  self.submitted();args,_=proof_fixture(self.d,self.secret);(self.d/'proof.json').write_text('tampered');self.cmd('verify','--job','a','--worker','reviewer','--token','1',*args,ok=False)
 def test_contract_substitution(self):
  self.submitted();args,_=proof_fixture(self.d,self.secret);path=self.d/'contract.json';path.write_text(path.read_text()+' ');self.cmd('verify','--job','a','--worker','reviewer','--token','1',*args,ok=False)
 def test_missing_secret(self):
  self.submitted();args,_=proof_fixture(self.d,self.secret);self.cmd('verify','--job','a','--worker','reviewer','--token','1',*args,ok=False,secret='')
 def test_wrong_identity(self):
  self.submitted();args,_=proof_fixture(self.d,self.secret,worker='other');self.cmd('verify','--job','a','--worker','reviewer','--token','1',*args,ok=False)
 def test_clock_override_rejected(self):
  self.submitted();args,_=proof_fixture(self.d,self.secret);self.cmd('verify','--job','a','--worker','reviewer','--token','1','--now','0',*args,ok=False)
 def test_missing_reviewed_plan(self):
  args,_=proof_fixture(self.d,self.secret)
  with self.assertRaises(ValueError):validate_proof(self.d/'contract.json',self.d/'manifest.json')
 def test_exclusive_workspace(self):
  command=[sys.executable,str(ROOT/'scripts/workspace_manager.py'),str(self.d/'workspaces'),'a'];self.assertEqual(subprocess.run(command,capture_output=True).returncode,0);self.assertNotEqual(subprocess.run(command,capture_output=True).returncode,0)
 def test_invalid_workspace_name(self):
  for name in ['..','CON','NUL','a/b']:
   r=subprocess.run([sys.executable,str(ROOT/'scripts/workspace_manager.py'),str(self.d/'workspaces'),name],capture_output=True);self.assertNotEqual(r.returncode,0)
  self.assertFalse((self.d/'workspaces').exists())
if __name__=='__main__':unittest.main()
