import argparse
import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
import deep_loop
import test_receipt_recovery as fixtures
import test_endpoint_readback as endpoint_fixtures

class RecoveryReportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.checkpoint=self.root/'.deep-recover1'; self.checkpoint.mkdir()
        self.state={'schemaVersion':2,'sessionId':'recover1','task':'Local file','phase':'SHIP',
                    'active':True,'complete':False,'checks':[{'name':'Acceptance','status':'passed','evidence':'Recorded'}],
                    'delivery':{'endpoint':'local','status':'verified','evidence':'Recorded'}}
        self.write()
    def write(self):
        (self.checkpoint/'state.json').write_text(json.dumps(self.state))
        (self.checkpoint/'plan.md').write_text('Explicit local scope')
    def persist(self):
        endpoint_fixtures.EndpointReadbackTests.persist(self)
    def report(self, path=None):
        stream=io.StringIO()
        with redirect_stdout(stream), patch.object(deep_loop.subprocess,'run',side_effect=AssertionError('No subprocess inspection')):
            result=deep_loop.recovery_report(argparse.Namespace(root=str(self.root),path=str(path or self.checkpoint),session=None,json=True))
        return result,json.loads(stream.getvalue())
    def test_readonly_record_only_and_unknown_ownership(self):
        (self.root/'.deep-current.json').write_text(json.dumps({'path':str(self.checkpoint)}))
        before=deep_loop.file_manifest(self.root)
        code,report=self.report()
        self.assertEqual(code,0); self.assertEqual(deep_loop.file_manifest(self.root),before)
        self.assertEqual(report['inspection']['ownership'],'unknown')
        self.assertEqual(report['inspection']['proofBasis'],'record_only')
        self.assertEqual(report['delivery']['liveEndpoint'],'not_inspected')
        self.assertEqual(report['completionTruth'],'not_authenticated_by_report')
    def test_stage_due_and_skipped_checks_cannot_pass(self):
        self.state['phase']='REVIEW'
        self.state['checks'].append({'name':'Closeout','stage':'closeout','status':'pending'})
        self.write(); code,report=self.report()
        self.assertEqual(code,0); self.assertEqual(report['stages']['ship']['status'],'blocked')
        self.assertEqual(report['checks'][1]['dueAt'],['ship'])
        self.state['checks'][0]['status']='skipped'; self.write()
        self.assertNotEqual(self.report()[0],0)
    def test_missing_plan_and_unavailable_contract_refuse_clear(self):
        (self.checkpoint/'plan.md').unlink(); self.assertNotEqual(self.report()[0],0)
        self.state['verificationContract']={'path':str(self.root/'missing'),'sha256':'0'*64,'endpoint':'local'}
        self.write(); code,report=self.report(); self.assertNotEqual(code,0)
        self.assertIn(report['stages']['ship']['status'],('blocked','unavailable'))
        self.assertEqual(report['inspection']['proofBasis'],'unavailable')
        self.assertFalse(report['localShipRequirementsSatisfied'])
    def test_schemas_three_four_gate_requirements_reused(self):
        for version in (3,4):
            self.state['schemaVersion']=version; self.write(); code,report=self.report()
            self.assertNotEqual(code,0); self.assertFalse(report['localShipRequirementsSatisfied'])
        self.state['uiRoute']={'kind':'not_applicable','reason':'Local text'}
        self.state['delivery'].update(endpointDecision={'status':'settled','source':'user','evidence':'Approved'},revision='r1',branchDisposition={'kind':'not_applicable','reason':'No branch'})
        self.write(); self.assertEqual(self.report()[0],0)
    def test_legacy_manual_limits_remain_explicit(self):
        self.state={'schemaVersion':1,'sessionId':'recover1','phase':'COMPLETE','complete':True,'active':False,'task':'Legacy'}
        self.write(); (self.checkpoint/'verification.json').write_text(json.dumps({'requiredGates':['review'],'gates':{'review':True}}))
        (self.checkpoint/'debt.md').write_text('## New debt\n')
        code,report=self.report(); self.assertNotEqual(code,0)
        self.assertEqual(report['inspection']['proofBasis'],'record_only')
        self.assertFalse(report['localShipRequirementsSatisfied'])
    def test_observed_drift_refuses_report(self):
        original=deep_loop.validate
        def drift(args):
            code=original(args); (self.checkpoint/'plan.md').write_text('Concurrent change'); return code
        with patch.object(deep_loop,'validate',side_effect=drift),self.assertRaisesRegex(ValueError,'changed during inspection'):
            self.report()
    def test_registered_ui_binding_and_request_drift_inspected_readonly(self):
        request=self.root/'request.json'
        fixtures.save(request,{'surface':'ui','changes':['hierarchy'],'mode':'EVOLVE','platform':'web'})
        self.state['uiEvidence']={'request':{'path':str(request),'sha256':fixtures.sha(request)}}
        self.write(); before=deep_loop.file_manifest(self.root)
        code,report=self.report(); self.assertNotEqual(code,0)
        self.assertTrue(any('requires an approved' in issue for issue in report['blockers']))
        self.assertEqual(deep_loop.file_manifest(self.root),before)
        request.write_text('{}'); code,report=self.report(); self.assertNotEqual(code,0)
        self.assertFalse(report['localShipRequirementsSatisfied'])
    def test_malformed_flags_and_schema_never_clear(self):
        for key,value in [('active','yes'),('complete','yes'),('schemaVersion',True),('phase',{})]:
            original=self.state[key]; self.state[key]=value; self.write()
            code,report=self.report(); self.assertNotEqual(code,0)
            self.assertFalse(report['localShipRequirementsSatisfied']); self.state[key]=original
    def test_absent_advisory_proof_is_not_claimed(self):
        fixtures.GenericReceiptTests.setUp(self)
        self.contract['verifiers'][0]['gate']='advisory'
        self.contract['requirements'][0]['priority']='advisory'
        fixtures.save(self.path,self.contract)
        self.state['verificationContract']['sha256']=fixtures.sha(self.path)
        self.state['checks']=[{'name':'Manual acceptance','status':'passed','evidence':'Recorded'}]
        self.checkpoint=self.root/'.deep-receipt1'; self.checkpoint.mkdir()
        self.state.update(task='Advisory',phase='SHIP',complete=False,active=True); self.write()
        code,report=self.report(); self.assertEqual(code,0)
        self.assertEqual(report['proofs'][0]['inspection'],'not_claimed')
        self.assertEqual(report['inspection']['proofFreshness'],'due_ship_gates_satisfied')
    def test_locator_ambiguity_and_missing_pointer_unchanged(self):
        other=self.root/'.deep-other001'; other.mkdir()
        args=argparse.Namespace(root=str(self.root),path=None,session=None,json=True)
        with self.assertRaisesRegex(ValueError,'Multiple checkpoints'):
            deep_loop.recovery_report(args)
        (self.root/'.deep-current.json').write_text(json.dumps({'path':str(self.root/'absent')}))
        with self.assertRaisesRegex(ValueError,'Current checkpoint is missing'):
            deep_loop.recovery_report(args)
    def test_bound_actual_current_then_source_drift_complete_is_blocked(self):
        fixtures.GenericReceiptTests.setUp(self); fixtures.GenericReceiptTests.run_bound(self)
        self.checkpoint=self.root/'.deep-receipt1'; self.checkpoint.mkdir()
        self.state.update(task='Bound local file',phase='COMPLETE',complete=True,active=False); self.write()
        code,report=self.report(); self.assertEqual(code,0)
        self.assertEqual(report['inspection']['proofFreshness'],'due_ship_gates_satisfied')
        self.assertEqual(report['proofs'][0]['inspection'],'current_for_ship')
        self.source.write_text('drift'); before=deep_loop.file_manifest(self.root)
        code,report=self.report(); self.assertNotEqual(code,0)
        self.assertTrue(report['recorded']['complete']); self.assertFalse(report['localShipRequirementsSatisfied'])
        self.assertEqual(deep_loop.file_manifest(self.root),before)
    def test_readback_current_then_delivered_drift(self):
        endpoint_fixtures.EndpointReadbackTests.setUp(self); endpoint_fixtures.EndpointReadbackTests.run_bound(self)
        self.checkpoint=self.root/'.deep-receipt1'; self.checkpoint.mkdir()
        self.state.update(task='Readback',phase='SHIP',complete=False,active=True); self.write()
        code,report=self.report(); self.assertEqual(code,0)
        self.assertEqual(report['delivery']['retainedReadback'],'current_for_ship')
        self.delivered.write_text('drift'); self.assertNotEqual(self.report()[0],0)
    def test_archive_resolution_relocated_without_external_commands(self):
        fixtures.GenericReceiptTests.setUp(self); fixtures.GenericReceiptTests.run_bound(self)
        checkout=self.root/'checkout'; checkout.mkdir(); self.checkpoint=checkout/'.deep-receipt1'; self.checkpoint.mkdir()
        self.state.update(task='Archive',phase='SHIP',complete=False,active=False); self.write()
        archive=self.root/'archive'
        deep_loop.preserve(argparse.Namespace(root=str(checkout),path=str(self.checkpoint),session=None,destination=str(archive),include=[],checkpoint_only=True))
        for path in (self.path,self.impl,self.manifest,self.env,self.source,self.root/'result.txt',self.root/'receipt.json'):
            path.unlink()
        moved=self.root/'moved'; shutil.move(archive,moved)
        before=deep_loop.file_manifest(moved); code,report=self.report(moved/'checkpoint')
        self.assertEqual(code,0); self.assertEqual(report['inspection']['proofBasis'],'bound_and_recorded')
        self.assertEqual(deep_loop.file_manifest(moved),before)

if __name__=='__main__': unittest.main()
