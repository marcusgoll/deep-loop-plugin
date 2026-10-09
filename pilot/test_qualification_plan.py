import copy
import unittest
from admission import digest,initialize,reserve
from private_launch import launch_plan,ROOT
from qualification_plan import qualification_plan

class QualificationPlanTests(unittest.TestCase):
    def setUp(self):
        self.contract={'prompt':'disposable','executor':{'path':'/usr/bin/pinned-codex','sha256':'a'*64}}
        self.key=digest(self.contract)
        journal=reserve(initialize(self.key),self.key,run_id=1,run_attempt=1,model_seconds=600,active_seconds=1200)
        self.plan=launch_plan(journal,self.key,run_id=1,run_attempt=1)
        self.script=self.plan['candidate']+'/.deep-loop-qualification.py'
    def test_no_model_commands_bind_policy_and_candidate(self):
        result=qualification_plan(self.plan,self.contract,self.script)
        self.assertEqual(result['model_calls'],0)
        self.assertIn('--strict-config',result['strict_command'])
        self.assertNotIn('--strict-config',result['features_command'])
        self.assertNotIn('--strict-config',result['sandbox_command'])
        self.assertIn('no_user_config',result['configuration_preconditions'])
        self.assertIn('effective_configuration_validated',result['configuration_preconditions'])
        self.assertEqual(result['sandbox_command'][-4:],['--','/usr/bin/python3','-I',self.script])
        self.assertNotIn('exec',result['sandbox_command'])
        self.assertNotIn('resume',result['sandbox_command'])
        self.assertEqual(result['candidate'],ROOT+'/candidate/'+self.key)
        self.assertIn('forced_login_method="chatgpt"',result['features_command'])
    def test_malformed_executor_digest_rejected(self):
        contract=copy.deepcopy(self.contract);contract['executor']['sha256']='a'*61
        plan=copy.deepcopy(self.plan);plan['contract_digest']=digest(contract)
        plan['candidate']=ROOT+'/candidate/'+digest(contract)
        with self.assertRaises(ValueError):qualification_plan(plan,contract,plan['candidate']+'/.deep-loop-qualification.py')

    def test_changed_candidate_script_or_capabilities_rejected(self):
        for field,value in [('candidate','/tmp/other'),('contract_digest','b'*64)]:
            plan=copy.deepcopy(self.plan);plan[field]=value
            with self.assertRaises(ValueError):qualification_plan(plan,self.contract,self.script)
        with self.assertRaises(ValueError):qualification_plan(self.plan,self.contract,'/tmp/arbitrary.py')
        plan=copy.deepcopy(self.plan);plan['command'].remove('--ignore-user-config')
        with self.assertRaises(ValueError):qualification_plan(plan,self.contract,self.script)

if __name__=='__main__':unittest.main()
