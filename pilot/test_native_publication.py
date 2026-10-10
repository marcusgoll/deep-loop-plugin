import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from admission import digest
from native_publication import NativePublication
from private_controller import TrustedStore


class NativePublicationTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.store=TrustedStore(Path(temp.name).resolve(),owner_uid=os.getuid())
        self.prefix='fixture-native';self.before={'checks':[{'status':'pending'}]}
        self.owned={'journal_revision':'a'*40,'plan':{'checkpoint_sha256':digest(self.before)}}
        result={'owned_plan_digest':digest(self.owned),'native_result_sealed':True}
        self.store.create(self.prefix+'.intent.json',{'owned_plan':self.owned})
        self.store.create(self.prefix+'.result.json',result)
        self.row={'verifier_id':'V1','sealed_result_sha256':digest(result),
                  'native_provenance':{'invocation_id':'b'*32}}
        self.journal=Mock(contract_digest='c'*64);self.journal.read.return_value=('a'*40,{'attempts':['charged']})
        self.gate=Mock();self.gate.verified_state.return_value={'before':self.before,'after':{'checks':[{'status':'passed'}]},'observation':{'fixture':True}}
        self.pub=NativePublication(self.store,self.journal,Mock(),self.gate)
        self.pub.results=Mock();self.pub.results.receipt_row.return_value=self.row

    def test_receipt_hash_is_saved_bytes_and_intent_retry_is_exact(self):
        intent=self.pub.prepare(self.prefix)
        self.assertEqual(self.pub.prepare(self.prefix),intent)
        path=Path(intent['receipt']['path'])
        self.assertEqual(intent['receipt']['sha256'],hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(json.loads(path.read_bytes()),[self.row])
        self.assertFalse(intent['parent_accepted'])
        self.gate.publish_verified_state.assert_not_called()
        self.journal.publish.assert_not_called()

    def test_interruption_after_receipt_is_adopted_without_execution(self):
        self.gate.verified_state.side_effect=ValueError('fixture interrupted')
        with self.assertRaisesRegex(ValueError,'interrupted'):self.pub.prepare(self.prefix)
        self.assertTrue((self.store.root/(self.prefix+'.receipt.json')).exists())
        self.assertFalse((self.store.root/(self.prefix+'.publication-intent.json')).exists())
        self.gate.verified_state.side_effect=None
        self.pub.prepare(self.prefix)
        self.pub.backend.submit.assert_not_called()

    def test_changed_receipt_and_stale_journal_block(self):
        self.store.create(self.prefix+'.receipt.json',[{'substituted':True}])
        with self.assertRaisesRegex(ValueError,'record changed'):self.pub.prepare(self.prefix)
        self.store.remove(self.prefix+'.receipt.json')
        self.journal.read.return_value=('d'*40,{'attempts':['charged']})
        with self.assertRaisesRegex(ValueError,'authority changed'):self.pub.prepare(self.prefix)
        self.assertFalse((self.store.root/(self.prefix+'.publication-intent.json')).exists())

    def test_late_result_change_blocks_intent(self):
        self.pub.results.receipt_row.side_effect=[self.row,{**self.row,'changed':True}]
        with self.assertRaisesRegex(ValueError,'inputs changed'):self.pub.prepare(self.prefix)
        self.assertFalse((self.store.root/(self.prefix+'.publication-intent.json')).exists())
