import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from admission import digest
from artifact_verifier import ArtifactVerifier


def sha(value):
    return hashlib.sha256(value).hexdigest()


class ArtifactVerifierTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root/'source.txt').write_bytes(b'frozen')
        (self.root/'result.txt').write_bytes(b'approved\n')
        self.contract = {'verification': {'baseline': {'source.txt': sha(b'frozen')},
                         'artifact_path': 'result.txt', 'artifact_sha256': sha(b'approved\n')}}
        self.owner = {'contract_digest': digest(self.contract)}
        self.verifier = ArtifactVerifier(self.root, os.getuid())
    def test_exact_output_has_stable_semantic_receipt(self):
        first = self.verifier(self.contract, self.owner)
        os.utime(self.root/'result.txt', None)
        self.assertEqual(first, self.verifier(self.contract, self.owner))
        self.assertEqual(first['artifact_sha256'], sha(b'approved\n'))
    def test_wrong_output_extra_file_or_source_change_is_no_progress(self):
        for path, data in [('result.txt', b'wrong'), ('unexpected', b'new'), ('source.txt', b'changed')]:
            with self.subTest(path=path):
                (self.root/path).write_bytes(data)
                self.assertIsNone(self.verifier(self.contract, self.owner))
                if path == 'unexpected': (self.root/path).unlink()
                else: (self.root/path).write_bytes(b'frozen' if path == 'source.txt' else b'approved\n')
    def test_links_and_private_config_rejected(self):
        (self.root/'link').symlink_to(self.root/'source.txt')
        with self.assertRaises(ValueError): self.verifier(self.contract, self.owner)
        (self.root/'link').unlink()
        os.link(self.root/'source.txt', self.root/'hardlink')
        with self.assertRaises(ValueError): self.verifier(self.contract, self.owner)
        (self.root/'hardlink').unlink()
        (self.root/'.codex').mkdir()
        with self.assertRaises(ValueError): self.verifier(self.contract, self.owner)
    def test_entry_bound_applies_before_directory_materialization(self):
        for i in range(5): (self.root/str(i)).mkdir()
        with patch('artifact_verifier.MAX_FILES', 4):
            with self.assertRaises(ValueError): self.verifier(self.contract, self.owner)

    def test_unchanged_artifact_and_contract_drift_rejected(self):
        with self.assertRaises(ValueError): self.verifier(self.contract, {'contract_digest': 'a'*64})
        self.contract['verification']['baseline']['result.txt'] = sha(b'approved\n')
        self.owner['contract_digest'] = digest(self.contract)
        self.assertIsNone(self.verifier(self.contract, self.owner))

if __name__ == '__main__': unittest.main()
