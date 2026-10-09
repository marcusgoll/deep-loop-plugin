"""S02 compatibility controls against both preserved baselines and candidate."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HELPER = Path(os.environ.get('DL_COMPAT_HELPER', Path(__file__).with_name('deep_loop.py')))

class CompatibilityChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cli('init', '--task', 'Compatibility', '--session', 'compat01')
        self.folder = self.root / '.deep-compat01'
        self.path = self.folder / 'state.json'
        self.state = json.loads(self.path.read_text())
        self.state['uiRoute'] = {'kind': 'not_applicable', 'reason': 'Backend fixture'}
        self.state['delivery']['endpointDecision'] = {'status': 'settled', 'source': 'user', 'evidence': 'Fixture authority'}
        self.contract = {'name': 'Compatibility', 'scope': 'Fixture', 'status': 'NOT_RUN',
            'requirements': [{'id':'R1','outcome':'Saved output','invariant':'Output correct','priority':'blocking'}],
            'verifiers': [{'id':'V1','covers':['R1'],'class':'deterministic','status':'implemented','expected':'Output correct','gate':'blocking'}],
            'gaps':[], 'ship_gate':dict.fromkeys(('require_all_blocking_verifiers_pass','require_zero_blocking_gaps','require_human_approvals_recorded','require_evidence_matches_revision'),True)}
        self.contract_path = self.root / 'contract.json'
        self.save()

    def cli(self,*args):
        run = subprocess.run([sys.executable,str(HELPER),'--root',str(self.root),*args],capture_output=True,text=True)
        if args[0] == 'init': self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        return run

    def save(self):
        self.path.write_text(json.dumps(self.state))
        self.contract_path.write_text(json.dumps(self.contract))

    def bind(self):
        run=self.cli('bind-contract','--contract',str(self.contract_path),'--endpoint','Saved output')
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        self.state=json.loads(self.path.read_text())

    def test_schema4_binding_retains_attributed_delivery_fields(self):
        self.bind()
        self.assertIn('endpointDecision',self.state['delivery'])
        self.assertIn('branchDisposition',self.state['delivery'])
        self.assertIn('revision',self.state['delivery'])
        self.assertEqual(self.state['checks'][0]['status'],'pending')

    def test_rebinding_preserves_metadata_but_invalidates_nested_delivery_proof(self):
        for multi in (False, True):
            with self.subTest(multi=multi):
                self.state['schemaVersion']=4
                self.state['delivery']={'endpoint':'Saved output','status':'verified','evidence':'old readback',
                    'endpointDecision':{'status':'settled','source':'user','evidence':'Same endpoint authority'}}
                target={'id':'app','revision':'revision-A','status':'verified','evidence':'old target readback',
                        'branchDisposition':{'kind':'pull_request','revision':'revision-A','status':'verified','evidence':'old PR'}}
                if multi: self.state['delivery']['targets']=[target]
                else: self.state['delivery'].update(revision=target['revision'],branchDisposition=target['branchDisposition'])
                self.save();self.bind()
                delivery=self.state['delivery']
                self.assertEqual(delivery['endpointDecision']['status'],'settled')
                self.assertEqual(delivery['status'],'pending');self.assertEqual(delivery['evidence'],'')
                subject=delivery['targets'][0] if multi else delivery
                self.assertEqual(subject['revision'],'revision-A')
                if multi: self.assertEqual(subject['evidence'],''); self.assertEqual(subject['status'],'pending')
                self.assertEqual(subject['branchDisposition']['kind'],'pull_request')
                self.assertEqual(subject['branchDisposition']['status'],'pending')
                self.assertEqual(subject['branchDisposition']['evidence'],'')
                self.state['checks'][0].update(status='passed',evidence='new acceptance')
                self.state['delivery'].update(status='verified',evidence='new readback');self.save()
                self.assertNotEqual(self.cli('validate','--stage','ship').returncode,0)

    def test_rebinding_changed_endpoint_requires_fresh_authority(self):
        self.state['delivery'].update(endpoint='Old endpoint',endpointDecision={'status':'settled','source':'user','evidence':'Old authority'})
        self.save();self.bind()
        self.assertEqual(self.state['delivery']['endpointDecision']['status'],'pending')

    def test_build_does_not_require_review_proof(self):
        self.bind()
        self.state['delivery']['endpointDecision']={'status':'settled','source':'user','evidence':'Fixture authority'}
        self.save()
        run=self.cli('validate','--stage','build')
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        self.assertNotEqual(self.cli('validate','--stage','review').returncode,0)

    def test_build_defers_completion_gap_but_blocks_implementation_gap(self):
        self.contract['gaps']=[{'id':'G1','requirement':'R1','risk':'Readback unavailable','recommended_verifier':'Readback','priority':'blocking','blocks':'completion'}]
        self.save(); self.bind()
        self.state['delivery']['endpointDecision']={'status':'settled','source':'user','evidence':'Fixture authority'}
        self.save()
        self.assertEqual(self.cli('validate','--stage','build').returncode,0)
        self.assertNotEqual(self.cli('validate','--stage','review').returncode,0)
        self.contract['gaps'][0]['blocks']='implementation'; self.save(); self.bind()
        self.state['delivery']['endpointDecision']={'status':'settled','source':'user','evidence':'Fixture authority'};self.save()
        self.assertNotEqual(self.cli('validate','--stage','build').returncode,0)

    def test_review_defers_ship_and_closeout_without_waiving_ship(self):
        self.state['schemaVersion']=2
        self.state['checks']=[{'name':'review','status':'passed','evidence':'Observed'}, {'name':'readback','stage':'ship','status':'pending'}, {'name':'retirement','stage':'closeout','status':'pending'}]
        self.state['tasks']=[{'id':'T1','title':'retire','kind':'task','stage':'closeout','status':'pending','acceptance':'Retired'}]
        self.save()
        self.assertEqual(self.cli('validate','--stage','review').returncode,0)
        self.assertNotEqual(self.cli('validate','--stage','ship').returncode,0)

    def test_preservation_defers_only_closeout(self):
        self.state['schemaVersion']=2
        self.state.update(active=False,phase='SHIP')
        self.state['checks']=[{'name':'review','status':'passed','evidence':'Observed'}, {'name':'retirement','stage':'closeout','status':'pending'}]
        self.state['delivery']={'endpoint':'Saved output','status':'verified','evidence':'Observed readback'}
        self.save()
        outside=self.root.parent/(self.root.name+'-archive')
        self.addCleanup(lambda: __import__('shutil').rmtree(outside,ignore_errors=True))
        run=self.cli('preserve','--destination',str(outside))
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        self.assertNotEqual(self.cli('validate','--path',str(outside/'checkpoint'),'--stage','ship').returncode,0)

if __name__=='__main__': unittest.main()
