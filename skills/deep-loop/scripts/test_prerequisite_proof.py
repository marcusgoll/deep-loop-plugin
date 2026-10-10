import copy
import unittest
import deep_loop
import test_receipt_recovery
from test_ui_design import save, sha

class PrerequisiteProofTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_receipt_recovery.GenericReceiptTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        f.contract['requirements'].append({'id':'R2','outcome':'Native check','invariant':'Required','priority':'blocking'})
        second=copy.deepcopy(f.contract['verifiers'][0]);second.update(id='V2',covers=['R2'])
        f.contract['verifiers'].append(second)
        f.state['checks'].append({'name':'V2','verifierId':'V2','status':'pending','evidence':''})
        save(f.path,f.contract);f.state['verificationContract']['sha256']=sha(f.path)
        f.run_bound()
    def test_independent_proof_preserves_parent_obligations(self):
        f=self.fixture;before=copy.deepcopy(f.state)
        self.assertEqual(deep_loop.prerequisite_issues(f.state,['V1']),[])
        self.assertTrue(deep_loop.contract_issues(f.state,'review'))
        self.assertEqual(f.state,before)
        f.source.write_text('drift')
        self.assertTrue(deep_loop.prerequisite_issues(f.state,['V1']))
    def test_missing_pending_duplicate_unknown_and_unbound_rejected(self):
        f=self.fixture
        for ids in ([],['V1','V1'],['missing'],['V2'],['V1','V2'],'V1'):
            self.assertTrue(deep_loop.prerequisite_issues(f.state,ids),ids)
        del f.state['verificationContract']
        self.assertTrue(deep_loop.prerequisite_issues(f.state,['V1']))
    def test_full_parent_semantics_required(self):
        f=self.fixture;f.contract['requirements'][1]['invariant']='Changed'
        save(f.path,f.contract);f.state['verificationContract']['sha256']=sha(f.path)
        self.assertTrue(deep_loop.prerequisite_issues(f.state,['V1']))
    def test_not_due_proof_and_missing_parent_coverage_rejected(self):
        f=self.fixture;f.state['checks'][0]['stage']='ship'
        self.assertTrue(deep_loop.prerequisite_issues(f.state,['V1']))
        f.state['checks'][0].pop('stage');f.contract['verifiers'].pop()
        save(f.path,f.contract);f.state['verificationContract']['sha256']=sha(f.path)
        self.assertTrue(deep_loop.prerequisite_issues(f.state,['V1']))
    def test_manual_advisory_failed_and_substituted_receipts_rejected(self):
        f=self.fixture
        original=copy.deepcopy(f.state)
        for change in ({'status':'failed'}, {'receipt':{'path':str(f.root/'missing.json'),'sha256':'0'*64}}):
            f.state=copy.deepcopy(original);f.state['checks'][0].update(change)
            self.assertTrue(deep_loop.prerequisite_issues(f.state,['V1']))
        f.state=original
        verifier=f.contract['verifiers'][0]
        for field,value in [('gate','advisory'),('proof',{'mode':'manual','reason':'Human inspection required'})]:
            before=copy.deepcopy(verifier);verifier[field]=value
            save(f.path,f.contract);f.state['verificationContract']['sha256']=sha(f.path)
            self.assertTrue(deep_loop.prerequisite_issues(f.state,['V1']))
            verifier.clear();verifier.update(before)

if __name__=='__main__':unittest.main()
