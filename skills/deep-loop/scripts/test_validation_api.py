import argparse
import contextlib
import copy
import io
import unittest
from unittest.mock import patch

import deep_loop
import test_receipt_recovery


class FullValidationApiTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_receipt_recovery.GenericReceiptTests()
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.fixture.run_bound()

    def compare(self,state,stage):
        before=copy.deepcopy(state)
        files={str(p):p.read_bytes() for p in self.fixture.root.rglob('*') if p.is_file()}
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            issues=deep_loop.validation_issues(state,stage)
        self.assertEqual(output.getvalue(),'')
        self.assertEqual(state,before)
        self.assertEqual(files,{str(p):p.read_bytes() for p in self.fixture.root.rglob('*') if p.is_file()})
        args=argparse.Namespace(stage=stage,mode='fail')
        reader=deep_loop.read_json
        def selected(path):
            return state if path==self.fixture.root/'state.json' else reader(path)
        with patch.object(deep_loop,'resolve',return_value=self.fixture.root),patch.object(deep_loop,'read_json',side_effect=selected),contextlib.redirect_stdout(io.StringIO()) as cli:
            code=deep_loop.validate(args)
        self.assertEqual(code,1 if issues else 0)
        if issues:self.assertEqual(cli.getvalue(),''.join('- '+issue+'\n' for issue in issues))
        return issues

    def test_full_review_delivery_ship_and_build_preserve_cli_evidence_gates(self):
        for stage in ('build','review','delivery','ship'):
            with self.subTest(stage=stage):self.assertEqual(self.compare(self.fixture.state,stage),[])
        cases=[({'debt':[{'item':'debt','status':'accepted','owner':'owner','paydown':'later'}]},'Debt is unresolved'),
               ({'blocker':'missing required review'},'Required work is blocked'),
               ({'issues':['unresolved failure']},'Resolve recorded issues'),
               ({'checks':self.fixture.state['checks']+[{'name':'extra integration review','status':'pending'}]},'extra integration review'),
               ({'tasks':[{'id':'unfinished','title':'unfinished','kind':'task','status':'pending','acceptance':'required','dependsOn':[]}]},'Unfinished task'),
               ({'complete':True},'completed session'),
               ({'schemaVersion':4,'uiRoute':{'kind':'pending'}},'UI'),
               ({'schemaVersion':3},'Delivery')]
        for change,expected in cases:
            with self.subTest(change=change):
                issues=self.compare({**self.fixture.state,**change},'review')
                self.assertIn(expected,'; '.join(issues))
        self.assertIn('Delivery requires', '; '.join(self.compare({**self.fixture.state,'delivery':{'status':'pending'}},'ship')))

    def test_bound_source_drift_still_rejects_full_review(self):
        self.fixture.source.write_text('changed candidate')
        self.assertTrue(self.compare(self.fixture.state,'review'))

    def test_legacy_unknown_schemas_and_stages_cannot_use_workflow_api(self):
        for state in ({},{'schemaVersion':1},{'schemaVersion':True},{'schemaVersion':5}):
            with self.assertRaises(ValueError):deep_loop.validation_issues(state,'review')
        with self.assertRaises(ValueError):deep_loop.validation_issues(self.fixture.state,'unknown')
