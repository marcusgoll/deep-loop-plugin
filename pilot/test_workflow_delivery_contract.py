import copy
import unittest

from git_candidate_export import RULES
from workflow_delivery_contract import validate_workflow_delivery


def delivery(key):
    return {'kind':'full_workflow_draft_v1','approval_ref':'literal model-free delivery qualification',
            'repository':'marcusgoll/deep-loop-plugin','repository_id':123,'publisher':'marcusgoll','publisher_id':456,
            'base_ref':'codex/pilot-auth-recovery','base_sha':'a'*40,'branch':'deep-loop-workflow/'+key,
            'title':'Bounded workflow fixture','body':'Explicit complete candidate draft qualification',
            'commit':{'name':'Deep Loop fixture','email':'fixture@example.com','date':'2026-10-10T00:00:00Z',
                      'message':'Complete model-free workflow fixture\n'},'export_rules':RULES.copy(),
            'required_checks':[{'name':'verify','app_id':15368,'app_slug':'github-actions',
                               'workflow_path':'.github/workflows/pilot-verification.yml','event':'pull_request'}],
            'required_reviews':[{'login':'independent-reviewer','id':789}]}


class WorkflowDeliveryContractTests(unittest.TestCase):
    def setUp(self):self.key='b'*64;self.capability=delivery(self.key)
    def test_explicit_complete_capability_is_retained_without_defaults(self):
        self.assertEqual(validate_workflow_delivery(self.capability,self.key),self.capability)
        for field in self.capability:
            changed=copy.deepcopy(self.capability);del changed[field]
            with self.subTest(field=field),self.assertRaises(ValueError):validate_workflow_delivery(changed,self.key)
        with self.assertRaises(ValueError):validate_workflow_delivery({**self.capability,'merge':True},self.key)
    def test_foreign_branch_identity_and_unsupported_projection_are_rejected(self):
        for field,value in [('branch','deep-loop-workflow/'+'c'*64),('base_sha','0'*40),('repository','../other'),
                            ('publisher_id',True),('repository_id',0),('approval_ref',' '),
                            ('export_rules',{**RULES,'exclude':['private']})]:
            with self.subTest(field=field),self.assertRaises(ValueError):
                validate_workflow_delivery({**self.capability,field:value},self.key)
    def test_git_reference_injection_and_ambiguous_names_are_rejected(self):
        for name in ('a..b','a/.hidden','a//b','a/b.lock','a/','refs@{1}','a:b','a\nb','-option'):
            with self.subTest(name=name),self.assertRaises(ValueError):
                validate_workflow_delivery({**self.capability,'base_ref':name},self.key)
    def test_commit_header_injection_and_invalid_date_are_rejected(self):
        for field,value in [('name','name\nparent abc'),('email','fake@address\n'),('date','2026-02-30T00:00:00Z'),
                            ('message','no explicit terminating newline'),('date','2026-10-10T00:00:00+00:00')]:
            changed=copy.deepcopy(self.capability);changed['commit'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):validate_workflow_delivery(changed,self.key)
    def test_obligations_cannot_be_omitted_duplicated_or_lose_provenance(self):
        for field,value in [('required_checks',[]),('required_checks',self.capability['required_checks']*2),
                            ('required_reviews',self.capability['required_reviews']*2),('required_reviews',None)]:
            with self.subTest(field=field),self.assertRaises(ValueError):
                validate_workflow_delivery({**self.capability,field:value},self.key)
        for field in self.capability['required_checks'][0]:
            changed=copy.deepcopy(self.capability);del changed['required_checks'][0][field]
            with self.subTest(field=field),self.assertRaises(ValueError):validate_workflow_delivery(changed,self.key)
    def test_no_review_obligation_must_still_be_explicit(self):
        self.capability['required_reviews']=[]
        validate_workflow_delivery(self.capability,self.key)

if __name__=='__main__':unittest.main()
