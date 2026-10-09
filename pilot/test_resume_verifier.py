import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from admission import digest
from private_controller import TrustedStore
from resume_verifier import ResumeVerifier


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        root.chmod(0o700)
        self.candidate = root / 'candidate'
        self.candidate.mkdir()
        control = root / 'control'
        control.mkdir(mode=0o700)
        self.store = TrustedStore(control, owner_uid=os.getuid())
        self.contract = {'verification': {'baseline': {}, 'artifact_path': 'final.txt',
                         'artifact_sha256': sha(b'final')},
                         'resume_verification': {'checkpoint_path': 'checkpoint.txt',
                         'checkpoint_sha256': sha(b'checkpoint')}}
        self.key = digest(self.contract)
        self.sid = '11111111-1111-4111-8111-111111111111'
        self.verifier = ResumeVerifier(self.candidate, os.getuid(), self.store)

    def owner(self, unit, invocation, requested=None, observed=None):
        owner = {'contract_digest': self.key, 'unit': unit, 'session_id': requested}
        self.store.create(unit + '.invocation.json', {'owner': owner, 'invocation_id': invocation})
        self.store.create(unit + '.session.json', {'contract_digest': self.key, 'unit': unit,
                          'invocation_id': invocation, 'session_id': observed or self.sid})
        return owner

    def checkpoint(self):
        first = self.owner('first', 'a'*32)
        (self.candidate/'checkpoint.txt').write_bytes(b'checkpoint')
        self.assertIsNone(self.verifier(self.contract, first))
        (self.candidate/'checkpoint.txt').unlink()
        return first

    def test_controller_restart_resumes_without_refunding_first_attempt(self):
        from private_controller import PrivateController
        from test_private_controller import FixtureBackend, FixtureJournal, SESSION
        self.store.create('credential-stream.lock', {})
        journal = FixtureJournal(self.contract)
        backend = FixtureBackend()
        controller = PrivateController(self.store, journal, backend, self.verifier)
        controller.enroll(self.contract, 'human-fixture')
        controller.start(run_id=1, run_attempt=1, model_seconds=600, active_seconds=1200)
        (self.candidate/'checkpoint.txt').write_bytes(b'checkpoint')
        backend.active, backend.empty = False, True
        self.assertEqual(controller.reconcile(), 'finished_without_verified_progress')
        controller = PrivateController(self.store, journal, backend, self.verifier)
        backend.invocation = 'b'*32
        controller.start(run_id=2, run_attempt=1, model_seconds=600, active_seconds=1200, session_id=SESSION)
        (self.candidate/'checkpoint.txt').unlink()
        (self.candidate/'final.txt').write_bytes(b'final')
        self.assertEqual(controller.reconcile(), 'finished_with_verified_progress')
        self.assertEqual(sum(a['model_seconds'] for a in journal.state['attempts']), 1200)
        self.assertEqual(sum(a['active_seconds'] for a in journal.state['attempts']), 2400)
        self.assertIsNone(journal.state['attempts'][0]['progress_receipt'])
        self.assertIsNotNone(journal.state['attempts'][1]['progress_receipt'])

    def test_final_cannot_skip_checkpoint(self):
        first = self.owner('first', 'a'*32)
        (self.candidate/'final.txt').write_bytes(b'final')
        self.assertIsNone(self.verifier(self.contract, first))
        with self.assertRaises(FileNotFoundError): self.store.read(self.key+'.checkpoint.json')

    def test_exact_checkpoint_then_explicit_same_session_has_final_receipt(self):
        self.checkpoint()
        second = self.owner('second', 'b'*32, self.sid)
        (self.candidate/'final.txt').write_bytes(b'final')
        evidence = self.verifier(self.contract, second)
        self.assertIsNotNone(evidence)
        self.assertEqual(self.store.read(self.key+'.resume-acceptance.json')['evidence'], evidence)
        self.assertEqual(self.verifier(self.contract, second), evidence)

    def test_same_invocation_cannot_complete(self):
        first = self.checkpoint()
        (self.candidate/'final.txt').write_bytes(b'final')
        self.assertIsNone(self.verifier(self.contract, first))

    def test_different_or_unrequested_session_rejected(self):
        self.checkpoint()
        (self.candidate/'final.txt').write_bytes(b'final')
        for unit, requested, observed in [('fresh', None, self.sid),
                ('other', self.sid, '22222222-2222-4222-8222-222222222222')]:
            with self.subTest(unit=unit):
                owner = self.owner(unit, unit[0]*32, requested, observed)
                with self.assertRaises(ValueError): self.verifier(self.contract, owner)

    def test_extra_checkpoint_file_prevents_final_acceptance(self):
        self.checkpoint()
        second = self.owner('second', 'b'*32, self.sid)
        (self.candidate/'final.txt').write_bytes(b'final')
        (self.candidate/'checkpoint.txt').write_bytes(b'checkpoint')
        self.assertIsNone(self.verifier(self.contract, second))


if __name__ == '__main__': unittest.main()
