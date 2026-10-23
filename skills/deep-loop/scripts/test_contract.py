import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = {
    "id": "DL-001", "question": "Can imports be idempotent?", "build": "Use source keys and upserts.",
    "why": "Avoid duplicate flight records.", "prove": "Import the same fixture twice and compare stable record IDs.",
    "route": "bounded_feature", "scope": {"included": ["completed imports"], "excluded": ["predictions"]},
    "constraints": ["never invent times"], "authorization": "not_granted", "status": "ready",
    "acceptance": [{"id": "A1", "question": "Are duplicates prevented?", "method": "fixture replay", "expected": "one record per flight", "status": "pending", "evidence": []}],
    "blockers": []
}

class ContractTests(unittest.TestCase):
    def run_cli(self, obj):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "contract.json"
            p.write_text(json.dumps(obj), encoding="utf-8")
            return subprocess.run([sys.executable, str(ROOT / "scripts/verify_contract.py"), str(p)], capture_output=True, text=True)

    def test_valid_pending(self):
        self.assertEqual(self.run_cli(BASE).returncode, 0)

    def test_missing_question_rejected(self):
        x = copy.deepcopy(BASE); x.pop("question")
        self.assertNotEqual(self.run_cli(x).returncode, 0)

    def test_unproven_verified_rejected(self):
        x = copy.deepcopy(BASE); x["status"] = "verified"
        self.assertNotEqual(self.run_cli(x).returncode, 0)

    def test_passed_without_evidence_rejected(self):
        x = copy.deepcopy(BASE); x["acceptance"][0]["status"] = "passed"
        self.assertNotEqual(self.run_cli(x).returncode, 0)

    def test_verified_with_blocker_rejected(self):
        x = copy.deepcopy(BASE); x["status"] = "verified"; x["acceptance"][0]["status"] = "passed"
        x["acceptance"][0]["evidence"] = ["ci/run-123"]; x["blockers"] = ["deployment blocked"]
        self.assertNotEqual(self.run_cli(x).returncode, 0)

    def test_duplicate_ids_rejected(self):
        x = copy.deepcopy(BASE); x["acceptance"].append(copy.deepcopy(x["acceptance"][0]))
        self.assertNotEqual(self.run_cli(x).returncode, 0)

    def test_unknown_field_rejected(self):
        x = copy.deepcopy(BASE); x["extra"] = "unexpected"
        self.assertNotEqual(self.run_cli(x).returncode, 0)

    def test_valid_verified_structure(self):
        x = copy.deepcopy(BASE); x["status"] = "verified"; x["acceptance"][0]["status"] = "passed"
        x["acceptance"][0]["evidence"] = ["ci/run-123"]
        self.assertEqual(self.run_cli(x).returncode, 0)

if __name__ == "__main__":
    unittest.main()
