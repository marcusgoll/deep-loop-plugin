import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from admission import digest
from native_publication import NativePublication
from private_controller import TrustedStore


class NativePublicationTests(unittest.TestCase):
    def setUp(self):
        authority=patch('native_publication.require_active');authority.start();self.addCleanup(authority.stop)
        window=patch('native_publication.remaining',return_value=100);self.remaining=window.start();self.addCleanup(window.stop)
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
        self.gate=Mock()
        def transition(verifier,receipt,evidence):
            return {'before':self.before,'after':{'checks':[{'status':'passed'}]},
                    'observation':{'verifier_id':verifier,'receipt':receipt,'evidence':evidence,'parent_accepted':False}}
        self.gate.verified_state.side_effect=transition
        self.gate.publish_verified_state.side_effect=lambda transition,**kwargs:transition['after']
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
        self.gate.verified_state.side_effect=lambda verifier,receipt,evidence:{'before':self.before,'after':{},'observation':{}}
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

    def test_publication_adopts_saved_transition_and_completion_exactly(self):
        intent=self.pub.prepare(self.prefix)
        complete=self.pub.publish(self.prefix)
        self.assertEqual(self.pub.publish(self.prefix),complete)
        self.assertEqual(complete['checkpoint_sha256'],digest(intent['transition']['after']))
        self.assertTrue(complete['checkpoint_published']);self.assertFalse(complete['parent_accepted'])
        self.pub.backend.submit.assert_not_called();self.journal.publish.assert_not_called()

    def test_checkpoint_written_before_completion_failure_is_recoverable(self):
        self.pub.prepare(self.prefix)
        original=self.store.create
        def interrupted(name,value):
            if name.endswith('.publication-complete.json'):raise OSError('fixture completion interruption')
            return original(name,value)
        self.store.create=interrupted
        with self.assertRaisesRegex(OSError,'interruption'):self.pub.publish(self.prefix)
        self.gate.publish_verified_state.assert_called_once()
        self.store.create=original
        self.assertTrue(self.pub.publish(self.prefix)['checkpoint_published'])
        self.pub.backend.submit.assert_not_called()

    def test_stale_journal_blocks_checkpoint_publication(self):
        self.pub.prepare(self.prefix)
        self.journal.read.return_value=('d'*40,{})
        with self.assertRaisesRegex(ValueError,'intent authority changed'):self.pub.publish(self.prefix)
        self.gate.publish_verified_state.assert_not_called()

    def test_expiry_before_checkpoint_write_preserves_intent_without_completion(self):
        self.pub.prepare(self.prefix);self.remaining.return_value=0
        with self.assertRaisesRegex(ValueError,'window expired'):self.pub.publish(self.prefix)
        self.gate.publish_verified_state.assert_not_called()
        self.assertFalse((self.store.root/(self.prefix+'.publication-complete.json')).exists())

    def test_expiry_after_checkpoint_write_blocks_completion(self):
        self.pub.prepare(self.prefix);self.remaining.side_effect=[100,0]
        with self.assertRaisesRegex(ValueError,'window expired'):self.pub.publish(self.prefix)
        self.gate.publish_verified_state.assert_called_once()
        self.assertFalse((self.store.root/(self.prefix+'.publication-complete.json')).exists())
