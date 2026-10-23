#!/usr/bin/env python3
"""Standard-library Phase 1 structural contract validator. Does not execute proof."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {"id", "question", "build", "why", "prove", "route", "scope", "constraints", "authorization", "status", "acceptance", "blockers"}
CHECK = {"id", "question", "method", "expected", "status", "evidence"}

def validate(doc):
    errors = []
    if not isinstance(doc, dict):
        return ["contract must be an object"]
    errors += [f"missing: {k}" for k in sorted(REQUIRED - doc.keys())]
    errors += [f"unknown: {k}" for k in sorted(doc.keys() - REQUIRED)]
    for k in ("id", "question", "build", "why", "prove"):
        if not isinstance(doc.get(k), str) or not doc[k].strip():
            errors.append(f"{k} must be nonempty text")
    if doc.get("route") not in ("small_fix", "bounded_feature", "architecture", "investigation"):
        errors.append("invalid route")
    if doc.get("authorization") not in ("not_granted", "granted_for_scope"):
        errors.append("invalid authorization")
    if doc.get("status") not in ("draft", "ready", "in_progress", "blocked", "verified"):
        errors.append("invalid status")
    scope = doc.get("scope")
    if not isinstance(scope, dict) or set(scope) != {"included", "excluded"} or any(not isinstance(scope.get(k), list) or any(not isinstance(x, str) for x in scope[k]) for k in ("included", "excluded")):
        errors.append("scope must have included/excluded string arrays")
    for k in ("constraints", "blockers"):
        if not isinstance(doc.get(k), list) or any(not isinstance(x, str) or not x.strip() for x in doc[k]):
            errors.append(f"{k} must be an array of nonempty strings")
    checks = doc.get("acceptance")
    if not isinstance(checks, list) or not checks:
        errors.append("acceptance must be a nonempty array")
        checks = []
    ids = []
    for i, c in enumerate(checks):
        if not isinstance(c, dict):
            errors.append(f"acceptance[{i}] must be an object")
            continue
        if set(c) != CHECK:
            errors.append(f"acceptance[{i}] fields mismatch")
        for k in ("id", "question", "method", "expected"):
            if not isinstance(c.get(k), str) or not c[k].strip():
                errors.append(f"acceptance[{i}].{k} must be nonempty")
        if isinstance(c.get("id"), str):
            ids.append(c["id"])
        if c.get("status") not in ("pending", "passed", "failed", "blocked"):
            errors.append(f"acceptance[{i}] invalid status")
        ev = c.get("evidence")
        if not isinstance(ev, list) or any(not isinstance(x, str) or not x.strip() for x in ev):
            errors.append(f"acceptance[{i}] invalid evidence")
        if c.get("status") == "passed" and (not isinstance(ev, list) or not ev):
            errors.append(f"acceptance[{i}] passed without evidence")
    if len(ids) != len(set(ids)):
        errors.append("duplicate acceptance IDs")
    if doc.get("status") == "verified":
        if not checks or any(not isinstance(c, dict) or c.get("status") != "passed" for c in checks):
            errors.append("verified requires all acceptance checks passed")
        if doc.get("blockers") != []:
            errors.append("verified requires no blockers")
    return errors

def main():
    if len(sys.argv) != 2:
        print("Usage: verify_contract.py CONTRACT.json", file=sys.stderr)
        return 2
    try:
        doc = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 2
    errors = validate(doc)
    for err in errors:
        print(f"INVALID: {err}", file=sys.stderr)
    if errors:
        return 1
    print("VALID: structural checks passed; execution evidence NOT independently verified")
    return 0

if __name__ == "__main__":
    sys.exit(main())
