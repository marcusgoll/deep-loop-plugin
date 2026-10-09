import copy
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
                       'prompt':'Exact disposable fixture',
                       'executor':{'path':'/pinned/native','sha256':'a'*64},
                       'runtime':{'bundle_digest':'b'*64,'unit_plan_digest':'c'*64},
                       'verification':{'baseline':{},'artifact_path':'pilot/fixtures/private-lane-smoke.txt','artifact_sha256':'d'*64},
                       'resume_verification':{'checkpoint_path':'pilot/fixtures/private-lane-checkpoint.txt','checkpoint_sha256':'e'*64},
                       'delivery':{'repository':'marcusgoll/deep-loop-plugin','repository_id':2,'publisher_id':1,'base_ref':'codex/pilot-admission','source_sha':'f'*40,'commit_date':'2026-10-09T20:00:00Z','title':'Pilot','body':'Exact fixture'}}
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

    def test_malformed_frozen_contract_never_preflights_or_writes(self):
        cases=[('verification','artifact_path','unapproved.txt'),
               ('verification','artifact_sha256','bad'),
               ('resume_verification','checkpoint_sha256','bad'),
               ('resume_verification','checkpoint_path','../escape'),
               ('delivery','commit_date','2026-99-09T20:00:00Z'),
               ('delivery','title',''),('delivery','source_sha','bad')]
        self.importer.preflight=lambda contract:self.fail('Invalid contract must fail before host preflight')
        for section,field,value in cases:
            with self.subTest(field=field):
                contract=copy.deepcopy(self.contract);contract[section][field]=value
                key=digest(contract);self.journal.contract_digest=key
                with self.assertRaises(ValueError):
                    self.importer.apply(contract,expected_digest=key,approval_ref='human')
        self.assertEqual(list(self.store.root.glob('*.approval.json')),[])
        self.assertEqual(list(self.store.root.glob('*.enrollment-intent.json')),[])
        self.assertEqual(self.activations,[])

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
