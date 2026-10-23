"""Check local hashes and reviewed-plan consistency; no provenance authentication."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from run_proof import validate_plan
from verify_contract import validate


def verify(contract, manifest, base, plan, plan_hash):
    errors = validate(contract)
    if errors:
        raise ValueError("invalid contract: " + "; ".join(errors))
    validate_plan(plan)
    if contract["status"] != "verified" or contract["blockers"] or any(c["status"] != "passed" for c in contract["acceptance"]):
        raise ValueError("contract must have passed acceptance and no blockers")
    if not isinstance(manifest, dict) or set(manifest) != {"format", "artifacts", "acceptance"} or manifest["format"] != "deep-loop-evidence-v1":
        raise ValueError("invalid manifest fields or format")
    if not isinstance(manifest["artifacts"], list) or not manifest["artifacts"]:
        raise ValueError("artifacts must be nonempty")
    artifacts = {}
    for item in manifest["artifacts"]:
        if not isinstance(item, dict) or set(item) != {"id", "path", "sha256"} or not all(isinstance(v, str) and v.strip() for v in item.values()):
            raise ValueError("invalid artifact fields")
        if item["id"] in artifacts or not re.fullmatch("[a-f0-9]{64}", item["sha256"]) or Path(item["path"]).is_absolute():
            raise ValueError("duplicate artifact ID, invalid hash or absolute path")
        path = (base / item["path"]).resolve()
        if not path.is_relative_to(base) or not path.is_file():
            raise ValueError("missing or escaping artifact")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise ValueError("tampered artifact")
        artifacts[item["id"]] = raw
    mapping = manifest["acceptance"]
    if not isinstance(mapping, dict) or set(mapping) != {c["id"] for c in contract["acceptance"]}:
        raise ValueError("acceptance coverage mismatch")
    for check in contract["acceptance"]:
        refs = mapping[check["id"]]
        if not isinstance(refs, list) or not refs:
            raise ValueError("missing evidence")
        for ref in refs:
            if not isinstance(ref, dict) or set(ref) != {"artifact", "check_id"} or not all(isinstance(v, str) and v.strip() for v in ref.values()):
                raise ValueError("invalid proof reference")
            if ref["artifact"] not in artifacts or ref["artifact"] not in check["evidence"]:
                raise ValueError("evidence reference not declared by acceptance")
            proof = json.loads(artifacts[ref["artifact"]])
            if not isinstance(proof, dict) or set(proof) != {"format", "plan_sha256", "checks"} or proof["format"] != "deep-loop-proof-v1" or proof["plan_sha256"] != plan_hash:
                raise ValueError("proof does not match reviewed plan")
            rows = proof["checks"]
            if not isinstance(rows, list) or len(rows) != len(plan["checks"]):
                raise ValueError("incomplete proof checks")
            for recorded, expected in zip(rows, plan["checks"]):
                if not isinstance(recorded, dict) or recorded.get("id") != expected["id"] or recorded.get("argv") != expected["argv"] or recorded.get("outcome") != "passed" or type(recorded.get("exit_code")) is not int or recorded["exit_code"] != 0:
                    raise ValueError("missing, failed or substituted command")
            if ref["check_id"] not in {c["id"] for c in plan["checks"]}:
                raise ValueError("unknown proof check")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--plan", type=Path, required=True, help="separately reviewed execution plan")
    args = parser.parse_args()
    try:
        raw = args.plan.read_bytes()
        verify(json.loads(args.contract.read_bytes()), json.loads(args.manifest.read_bytes()), args.manifest.resolve().parent,
               json.loads(raw), hashlib.sha256(raw).hexdigest())
    except (OSError, ValueError, TypeError) as exc:
        print(f"INVALID: {exc}")
        return 1
    print("VALID: local hash and reviewed-plan consistency only; provenance NOT authenticated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
