import os
from pathlib import Path
import tempfile
import unittest
from admission import digest
from enrollment import Enrollment
from private_controller import TrustedStore
from test_private_controller import FixtureBackend, FixtureJournal


class EnrollmentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=TrustedStore(Path(self.temp.name).resolve(),owner_uid=os.getuid())
        self.store.create('credential-stream.lock',{})
        self.contract={'worker_wall_seconds':3600,'wakeup':{'model_seconds':600,'active_seconds':1200},
                       'verification':{'baseline':{}},'resume_verification':{},'delivery':{}}
        self.key=digest(self.contract);self.journal=FixtureJournal(self.contract);self.backend=FixtureBackend()
        self.activations=[]
        def activate(contract):
            # A worker can obtain the lock immediately on activation.
            with self.store.lock():
                self.assertEqual(self.store.read('enabled-outcome.json'),{'contract_digest':self.key})
                self.assertEqual(self.journal.state['attempts'],[])
            self.activations.append(contract)
            return {'timer':'active','contract_digest':self.key}
        self.importer=Enrollment(self.store,self.journal,self.backend,
            lambda contract:{'contract_digest':digest(contract)},activate,
            clock=lambda:('11111111-1111-4111-8111-111111111111',100))

    def apply(self):
        return self.importer.apply(self.contract,expected_digest=self.key,approval_ref='human-exact-fixture')

    def test_single_use_persists_before_activation_without_model_dispatch(self):
        result=self.apply()
        self.assertEqual(result['contract_digest'],self.key)
        self.assertEqual(len(self.activations),1)
        self.assertEqual(self.backend.submissions,[])
        self.assertEqual(self.store.read(self.key+'.window.json')['started'],100)
        with self.assertRaises(ValueError):self.apply()
        self.assertEqual(len(self.activations),1)

    def test_failed_qualification_preserves_intent_and_blocks_reinitialization(self):
        self.backend.qualified=False
        with self.assertRaises(ValueError):self.apply()
        self.assertIsNone(self.journal.state)
        self.assertEqual(self.activations,[])
        self.assertEqual(self.store.read(self.key+'.enrollment-intent.json')['approval_ref'],'human-exact-fixture')
        self.backend.qualified=True
        with self.assertRaises(ValueError):self.apply()

    def test_unknown_journal_publication_never_opens_window_or_activates(self):
        self.journal.uncertain=True
        with self.assertRaises(OSError):self.apply()
        with self.assertRaises(FileNotFoundError):self.store.read(self.key+'.window.json')
        self.assertEqual(self.activations,[])
        self.journal.uncertain=False
        with self.assertRaises(ValueError):self.apply()

    def test_unknown_activation_keeps_original_window_and_never_replays(self):
        calls=[]
        def unknown(contract):
            calls.append(contract);raise OSError('Lost activation response')
        self.importer.activate=unknown
        with self.assertRaises(OSError):self.apply()
        with self.assertRaises(ValueError):self.apply()
        self.assertEqual(len(calls),1)
        self.assertEqual(self.store.read(self.key+'.window.json')['started'],100)
        self.assertEqual(self.journal.state['attempts'],[])

    def test_foreign_contract_partial_intent_blocks_new_enrollment(self):
        self.store.create('a'*64+'.enrollment-intent.json',{'contract_digest':'a'*64})
        self.importer.preflight=lambda contract:self.fail('Must not preflight after partial enrollment')
        with self.assertRaises(ValueError):self.apply()
        self.assertEqual(self.activations,[])
        self.assertIsNone(self.journal.state)

    def test_changed_contract_or_unbound_preflight_never_writes_authority(self):
        with self.assertRaises(ValueError):
            self.importer.apply(self.contract,expected_digest='a'*64,approval_ref='human')
        self.importer.preflight=lambda contract:{'contract_digest':'a'*64}
        with self.assertRaises(ValueError):self.apply()
        self.assertEqual(list(self.store.root.glob('*.approval.json')),[])


if __name__=='__main__':unittest.main()
