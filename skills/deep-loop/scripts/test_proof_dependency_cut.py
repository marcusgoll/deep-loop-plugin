import hashlib
from pathlib import Path
import tempfile
import unittest
import proof_binding as proof

class ProofDependencyCutTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.file=self.root/'input.json';self.file.write_text('{"value":1}')
    def test_nested_resolution_keeps_independent_exact_read_cut(self):
        with proof.dependency_context() as records:
            with proof.files_context():proof.read(self.file)
            with proof.files_context(trace=set()):proof.sha(self.file)
            cut=proof.close_dependency_cut(records)
        self.assertEqual(cut[str(self.file)]['sha256'],hashlib.sha256(self.file.read_bytes()).hexdigest())
        self.assertEqual(cut[str(self.file)]['physical_path'],str(self.file))
    def test_conflicting_read_and_post_read_mutation_reject(self):
        for close in (False,True):
            with self.subTest(close=close),proof.dependency_context() as records:
                proof.read(self.file);self.file.write_text('{"value":2}')
                with self.assertRaises(ValueError):
                    proof.close_dependency_cut(records) if close else proof.read(self.file)
            self.file.write_text('{"value":1}')
    def test_alias_retarget_and_missing_file_reject(self):
        alias=self.root/'alias';alias.symlink_to(self.file)
        other=self.root/'other';other.write_bytes(self.file.read_bytes())
        with proof.dependency_context() as records:
            proof.read(alias);alias.unlink();alias.symlink_to(other)
            with self.assertRaises(ValueError):proof.close_dependency_cut(records)
        with proof.dependency_context() as records:
            proof.read(self.file);self.file.unlink()
            with self.assertRaises(FileNotFoundError):proof.close_dependency_cut(records)
    def test_preserved_map_uses_physical_file_in_nested_context(self):
        logical=self.root/'unavailable.json';digest=hashlib.sha256(self.file.read_bytes()).hexdigest()
        mapping={str(logical):{'path':self.file.name,'sha256':digest}}
        with proof.dependency_context() as records:
            with proof.files_context(self.root,mapping):self.assertEqual(proof.read(logical),{'value':1})
            cut=proof.close_dependency_cut(records)
        self.assertIn(str(self.file),cut);self.assertNotIn(str(logical),cut)

    def test_ui_bound_alias_keeps_original_mapping_until_closure(self):
        from ui_design import bound_file
        alias=self.root/'ui-alias';alias.symlink_to(self.file)
        other=self.root/'other-ui';other.write_bytes(self.file.read_bytes())
        record={'path':alias.name,'sha256':hashlib.sha256(self.file.read_bytes()).hexdigest()}
        with proof.dependency_context() as records:
            self.assertEqual(bound_file(record,self.root),self.file)
            alias.unlink();alias.symlink_to(other)
            with self.assertRaises(ValueError):proof.close_dependency_cut(records)

    def test_resolution_map_alias_is_closed_independently_of_nested_context(self):
        import json
        from deep_loop import resolution_context
        mapping=self.root/'resolution.json';mapping.write_text(json.dumps({'schemaVersion':1,'files':{}}))
        other=self.root/'other-resolution.json';other.write_bytes(mapping.read_bytes())
        alias=self.root/'map-alias';alias.symlink_to(mapping)
        state={'proofResolution':{'path':str(alias),'sha256':hashlib.sha256(mapping.read_bytes()).hexdigest()}}
        with proof.dependency_context() as records:
            with resolution_context(state):pass
            alias.unlink();alias.symlink_to(other)
            with self.assertRaises(ValueError):proof.close_dependency_cut(records)
