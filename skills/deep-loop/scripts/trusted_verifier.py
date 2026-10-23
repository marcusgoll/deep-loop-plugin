"""Reuse reviewed-plan evidence validation; this does not authenticate command execution."""
import hashlib
import json
from pathlib import Path
from verify_evidence import verify


def validate(contract_path, manifest_path, plan_path=None):
    if plan_path is None:raise ValueError("reviewed proof plan required")
    paths=[Path(contract_path).resolve(),Path(manifest_path).resolve(),Path(plan_path).resolve()]
    raw=[path.read_bytes() for path in paths]
    hashes=[hashlib.sha256(data).hexdigest() for data in raw]
    verify(json.loads(raw[0]),json.loads(raw[1]),paths[1].parent,json.loads(raw[2]),hashes[2])
    if any(path.read_bytes()!=data for path,data in zip(paths,raw)):
        raise ValueError("proof input drift during validation")
    return dict(zip(("contract_sha256","manifest_sha256","plan_sha256"),hashes))
