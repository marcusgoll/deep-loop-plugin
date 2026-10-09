import os
from pathlib import Path
import tempfile
import unittest
from admission import digest
from artifact_verifier import ArtifactVerifier
from delivery_artifact import DeliveryArtifact
from trusted_delivery import ARTIFACT
import hashlib

class ArtifactReadTests(unittest.TestCase):
    def test_only_accepted_stopped_artifact_is_exported(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();target=root/ARTIFACT;target.parent.mkdir(parents=True);target.write_bytes(b'approved\n')
            contract={'verification':{'baseline':{},'artifact_path':ARTIFACT,'artifact_sha256':hashlib.sha256(b'approved\n').hexdigest()}}
            evidence=ArtifactVerifier(root,os.getuid())(contract,{'contract_digest':digest(contract)})
            reader=DeliveryArtifact(root,os.getuid())
            self.assertEqual(reader(contract,evidence),b'approved\n')
            target.write_bytes(b'changed')
            with self.assertRaises(ValueError):reader(contract,evidence)

if __name__=='__main__':unittest.main()
