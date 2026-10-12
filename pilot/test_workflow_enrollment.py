import copy
import unittest
from unittest.mock import Mock,patch

from admission import digest,initialize
import test_private_controller as fixtures
from workflow_enrollment import WorkflowHelperEnrollment


class HelperEnrollmentTests(unittest.TestCase):
    def setUp(self):
        fixtures.PrivateControllerTests.setUp(self)
        self.key=self.journal.contract_digest
        self.journal.state=initialize(self.key,workflow=True)
        self.checkpoint={'fixture':'unchanged protected checkpoint'}
        self.store.create('state.json',self.checkpoint)
        self.binding={'approval_ref':'fixture graph','checkpoint_path':str(self.store.root/'state.json')}
        intent={'contract_digest':self.key,'binding_digest':digest(self.binding),'approval_ref':'fixture graph','journal_revision':self.journal.revision,'checkpoint_sha256':digest(self.checkpoint)}
        for suffix,value in [('workflow.json',self.binding),('workflow-binding-intent.json',intent),('workflow-binding-complete.json',{**intent,'activated':False})]:
            self.store.create(self.key+'.'+suffix,value)
        self.record={'contract_digest':self.key,'binding_digest':digest(self.binding),'approval_ref':'fixture graph','helper':{'fixture':'verified snapshot'}}
        self.operator=WorkflowHelperEnrollment(self.store,self.journal)
        self.helper=Mock()
        self.addCleanup(patch.stopall)
        patch('pinned_helper.PinnedHelper',return_value=self.helper).start()
        patch('workflow_enrollment.WorkflowGate.validate_binding',return_value=(self.binding,self.checkpoint,{})).start()
    def apply(self,record=None):
        record=self.record if record is None else record
        return self.operator.apply(record,expected_helper_digest=digest(record),approval_ref='fixture graph')
    def test_nonactivating_exact_enrollment_and_retry(self):
        before=self.journal.read()
        complete=self.apply()
        self.assertFalse(complete['activated']);self.assertEqual(self.apply(),complete)
        self.assertEqual(self.journal.read(),before)
        self.assertEqual(self.store.read(self.key+'.workflow-helper.json'),self.record)
        with self.assertRaises(FileNotFoundError):self.store.read('enabled-outcome.json')
    def test_partial_publication_recovers_only_exact_identity(self):
        original=self.store.create
        def fault(name,value):
            if name.endswith('.workflow-helper-complete.json'):raise OSError('fixture completion fault')
            return original(name,value)
        with patch.object(self.store,'create',side_effect=fault):
            with self.assertRaises(OSError):self.apply()
        with self.assertRaises(FileNotFoundError):self.store.read(self.key+'.workflow-helper-complete.json')
        changed={**self.record,'helper':{'fixture':'different snapshot'}}
        with self.assertRaisesRegex(ValueError,'identity changed'):self.apply(changed)
        self.assertFalse(self.apply()['activated'])
    def test_activation_charges_or_incomplete_binding_block_enrollment(self):
        self.store.create('enabled-outcome.json',{'contract_digest':self.key})
        with self.assertRaisesRegex(ValueError,'inactive unowned'):self.apply()
        self.store.remove('enabled-outcome.json')
        self.journal.state=initialize(self.key)
        with self.assertRaisesRegex(ValueError,'Empty explicitly'):self.apply()
        self.journal.state=initialize(self.key,workflow=True)
        self.store.remove(self.key+'.workflow-binding-complete.json')
        with self.assertRaises(FileNotFoundError):self.apply()
    def test_changed_checkpoint_or_journal_cannot_complete(self):
        self.checkpoint['fixture']='drift'
        with self.assertRaisesRegex(ValueError,'checkpoint changed'):self.apply()
        with self.assertRaises(FileNotFoundError):self.store.read(self.key+'.workflow-helper-intent.json')
    def test_snapshot_drift_after_intent_keeps_enrollment_incomplete(self):
        self.helper._verify.side_effect=ValueError('source drift')
        with self.assertRaisesRegex(ValueError,'source drift'):self.apply()
        with self.assertRaises(FileNotFoundError):self.store.read(self.key+'.workflow-helper-complete.json')
        self.helper._verify.side_effect=None
        self.assertFalse(self.apply()['activated'])
    def test_human_record_digest_and_graph_reference_are_required(self):
        with self.assertRaisesRegex(ValueError,'Exact authenticated'):
            self.operator.apply(self.record,expected_helper_digest='0'*64,approval_ref='fixture graph')
        with self.assertRaisesRegex(ValueError,'Completed workflow binding'):
            self.apply({**self.record,'binding_digest':'0'*64})
