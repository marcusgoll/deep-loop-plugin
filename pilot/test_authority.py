import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from admission import digest
from authority import OutcomeRevoked, require_active
from private_controller import PrivateController, TrustedStore
from test_private_controller import FixtureJournal, FixtureBackend


class RevocationBackend(FixtureBackend):
    def __init__(self):
        super().__init__()
        self.signals=[]
        self.fail_stop=False
    def observe_owned(self,plan,contract,owner,invocation):
        if invocation!=self.invocation:raise ValueError('Changed native generation')
        return {'unit':plan['unit'],'invocation_id':invocation,'ownership_verified':True,
                'execution_finished':not self.active and self.empty,'cgroup_empty':self.empty}
    def stop_owned(self,plan,contract,owner,invocation):
        self.signals.append((plan['unit'],invocation))
        if self.fail_stop:raise OSError('Unknown stop result')
        self.active=False;self.empty=True
        return self.observe_owned(plan,contract,owner,invocation)


class RevocationTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.store=TrustedStore(Path(temp.name).resolve(),owner_uid=os.getuid())
        self.store.create('credential-stream.lock',{})
        self.contract={'prompt':'fixture only','source':'frozen'}
        self.key=digest(self.contract)
        self.journal=FixtureJournal(self.contract);self.backend=RevocationBackend()
        self.controller=PrivateController(self.store,self.journal,self.backend)
        self.controller.enroll(self.contract,'human-approval')
    def start(self):return self.controller.start(run_id=1,run_attempt=1,model_seconds=600,active_seconds=1200)
    def revoke(self):
        with patch('private_controller.os.geteuid',return_value=0):
            return self.controller.revoke(approval_ref='human-revocation',reason='stop fixture')
    def test_revocation_before_dispatch_has_no_attempt_or_signal(self):
        self.revoke()
        with self.assertRaises(OutcomeRevoked):self.start()
        self.assertEqual(self.journal.state['attempts'],[])
        self.assertEqual(self.backend.signals,[])
    def test_stop_cleanup_preserves_charges_and_never_accepts_candidate(self):
        self.start();submitted=copy.deepcopy(self.backend.submissions)
        receipt=self.revoke()
        self.assertEqual(self.journal.state['attempts'][0]['status'],'finished')
        self.assertIsNone(self.journal.state['attempts'][0]['progress_receipt'])
        self.assertEqual(self.journal.state['attempts'][0]['model_seconds'],600)
        self.assertEqual(self.journal.state['attempts'][0]['active_seconds'],1200)
        with self.assertRaises(FileNotFoundError):self.store.read('active-owner.json')
        self.assertEqual(self.revoke(),receipt)
        self.assertEqual(len(self.backend.signals),1)
        self.assertEqual(self.backend.submissions,submitted)
        with self.assertRaises(OutcomeRevoked):self.controller.reconcile()
    def test_uncertain_stop_remains_fenced_until_trusted_cleanup(self):
        self.start();self.backend.fail_stop=True
        with self.assertRaises(OSError):self.revoke()
        with self.assertRaises(OutcomeRevoked):self.start()
        self.assertEqual(self.journal.state['attempts'][0]['status'],'reserved')
        self.assertIsNotNone(self.store.read('active-owner.json'))
        self.backend.fail_stop=False;self.revoke()
        self.assertEqual(len(self.backend.submissions),1)
    def test_stale_native_generation_cannot_release_revoked_owner(self):
        self.start();self.revoke();self.backend.invocation='b'*32
        with self.assertRaises(ValueError):self.revoke()
    def test_lost_finish_response_recovers_without_refund_or_second_stop(self):
        self.start();self.journal.uncertain=True
        with self.assertRaises(OSError):self.revoke()
        self.journal.uncertain=False
        self.revoke()
        self.assertEqual(len(self.backend.signals),1)
        self.assertEqual(self.journal.state['attempts'][0]['model_seconds'],600)
    def test_partial_intent_blocks_work_even_without_complete_marker(self):
        self.store.create(self.key+'.revocation-intent.json',{'incomplete':'fixture'})
        with self.assertRaises(OutcomeRevoked):require_active(self.store,self.key)
        with self.assertRaises(ValueError):self.revoke()
    def test_changed_completion_contract_blocks_readback(self):
        receipt=self.revoke();receipt['contract_digest']='b'*64
        self.store.remove(self.key+'.revocation-complete.json')
        self.store.create(self.key+'.revocation-complete.json',receipt)
        with self.assertRaises(ValueError):self.revoke()

    def test_reserved_attempt_with_forged_completion_remains_blocked(self):
        self.start();self.store.remove('active-owner.json')
        with self.assertRaises(ValueError):self.revoke()
        intent=self.store.read(self.key+'.revocation-intent.json')
        self.store.create(self.key+'.revocation-complete.json',{'contract_digest':self.key,
            'intent_digest':digest(intent),'journal_revision':self.journal.revision})
        with self.assertRaises(ValueError):self.revoke()
        self.assertEqual(self.backend.signals,[])

    def test_changed_stop_proof_blocks_completed_cleanup_readback(self):
        self.start();self.revoke()
        proof=self.store.read(self.key+'.revocation-stop.json');proof['intent_digest']='b'*64
        self.store.remove(self.key+'.revocation-stop.json')
        self.store.create(self.key+'.revocation-stop.json',proof)
        with self.assertRaises(ValueError):self.revoke()

    def test_reserved_attempt_without_owner_stays_fenced_and_incomplete(self):
        self.start();self.store.remove('active-owner.json')
        with self.assertRaises(ValueError):self.revoke()
        with self.assertRaises(OutcomeRevoked):self.start()
        with self.assertRaises(FileNotFoundError):self.store.read(self.key+'.revocation-complete.json')
        self.assertEqual(self.journal.state['attempts'][0]['status'],'reserved')
        self.assertEqual(self.backend.signals,[])

    def test_reserved_attempt_with_foreign_owner_never_completes_or_signals(self):
        self.start();self.store.remove('active-owner.json')
        foreign={'contract_digest':'b'*64,'unit':'foreign'}
        self.store.create('active-owner.json',foreign)
        with self.assertRaises(ValueError):self.revoke()
        self.assertEqual(self.store.read('active-owner.json'),foreign)
        with self.assertRaises(FileNotFoundError):self.store.read(self.key+'.revocation-complete.json')
        self.assertEqual(self.backend.signals,[])

    def test_foreign_global_owner_is_preserved_without_signal(self):
        foreign={'contract_digest':'b'*64,'unit':'foreign'}
        self.store.create('active-owner.json',foreign)
        self.revoke()
        self.assertEqual(self.store.read('active-owner.json'),foreign)
        self.assertEqual(self.backend.signals,[])


if __name__=='__main__':unittest.main()
