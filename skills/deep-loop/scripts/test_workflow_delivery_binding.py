import copy
import json
import unittest

import test_workflow_gate as fixtures
from test_workflow_delivery_contract import delivery


class WorkflowDeliveryBindingTests(unittest.TestCase):
    def setUp(self):
        self.g=fixtures.WorkflowGateTests();self.g.setUp();self.addCleanup(self.g.doCleanups)
        g=self.g;g.modern_binding()
        g.binding.update(schema=4,parent_acceptance={'kind':'review_to_ship','approval_ref':'literal parent authority'},
                         workflow_delivery=delivery(g.key))
        c=g.binding['workflow_delivery']
        g.f.state['delivery']={'status':'pending','endpoint':'github_draft_pr','repository':c['repository'],
                              'baseRef':c['base_ref'],'headRef':c['branch'],
                              'endpointDecision':{'status':'settled','source':'contract','evidence':c['approval_ref']}}
        g.checkpoint.write_text(json.dumps(g.f.state))
    def test_fresh_schema_four_binds_full_source_and_explicit_delivery(self):
        binding,state,_=self.g.gate.validate_binding(self.g.binding)
        self.assertEqual(binding,self.g.binding);self.assertEqual(state,self.g.f.state)
        self.assertEqual(self.g.gate.candidate_snapshot(binding)['policy']['scope'],'entire_candidate')
    def test_old_frozen_bindings_cannot_gain_delivery_fields(self):
        for version in (2,3):
            binding=copy.deepcopy(self.g.binding);binding['schema']=version
            if version==2:del binding['parent_acceptance']
            with self.subTest(version=version),self.assertRaises(ValueError):self.g.gate.validate_binding(binding)
    def test_delivery_endpoint_and_authority_must_match_checkpoint(self):
        for field,value in [('repository','foreign/repository'),('baseRef','other'),('headRef','other'),
                            ('endpoint','local'),('endpointDecision',{'status':'settled','source':'agent','evidence':'inferred'})]:
            state=copy.deepcopy(self.g.f.state);state['delivery'][field]=value
            self.g.checkpoint.write_text(json.dumps(state))
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'delivery endpoint'):
                self.g.gate.validate_binding(self.g.binding)
    def test_missing_parent_or_delivery_capability_cannot_select_schema_four(self):
        for field in ('parent_acceptance','workflow_delivery'):
            binding=copy.deepcopy(self.g.binding);del binding[field]
            with self.subTest(field=field),self.assertRaises(ValueError):self.g.gate.validate_binding(binding)

if __name__=='__main__':unittest.main()
