"""Offline pilot admission core. No execution, authentication, or remote writes.

The trusted host must persist the returned journal atomically, read it back,
authenticate approval/provider observations, and enforce timeouts before launch.
An absent journal is never implicitly re-created by reserve().
"""

import copy
import hashlib
import json


LIMITS = {"attempts": 3, "model_seconds": 1800, "active_seconds": 3600,
          "no_progress": 2}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                   allow_nan=False).encode()).hexdigest()


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"Invalid {name}")


def initialize(contract_digest):
    """Explicit enrollment only; caller must authenticate the frozen contract."""
    if (not isinstance(contract_digest, str) or len(contract_digest) != 64
            or any(c not in "0123456789abcdef" for c in contract_digest)):
        raise ValueError("Invalid contract digest")
    return {"schema": 1, "contract_digest": contract_digest,
            "limits": dict(LIMITS), "attempts": []}


def _validate(journal, contract_digest):
    if not isinstance(journal, dict) or set(journal) != {
            "schema", "contract_digest", "limits", "attempts"}:
        raise ValueError("Missing or incompatible journal")
    if type(journal["schema"]) is not int or journal["schema"] != 1 or journal["limits"] != LIMITS:
        raise ValueError("Changed schema or approved limits")
    initialize(contract_digest)
    if journal["contract_digest"] != contract_digest:
        raise ValueError("Contract drift")
    attempts = journal["attempts"]
    if not isinstance(attempts, list) or len(attempts) > LIMITS["attempts"]:
        raise ValueError("Invalid attempt history")
    identities = set()
    receipts = set()
    streak = 0
    for index, item in enumerate(attempts):
        if streak >= LIMITS["no_progress"]:
            raise ValueError("History continued after no-progress stop")
        if not isinstance(item, dict) or set(item) != {
                "run_id", "run_attempt", "model_seconds", "active_seconds",
                "status", "progress_receipt"}:
            raise ValueError("Invalid attempt record")
        for name in ("run_id", "run_attempt", "model_seconds", "active_seconds"):
            _integer(item[name], name, 1)
        identity = (item["run_id"], item["run_attempt"])
        if identity in identities or item["model_seconds"] > item["active_seconds"]:
            raise ValueError("Duplicate identity or invalid reservation")
        identities.add(identity)
        if item["status"] not in {"reserved", "finished"}:
            raise ValueError("Invalid status")
        if item["status"] == "reserved":
            if index != len(attempts)-1 or item["progress_receipt"] is not None:
                raise ValueError("Unreconciled predecessor")
        elif item["progress_receipt"] is not None:
            initialize(item["progress_receipt"])
            if item["progress_receipt"] in receipts:
                raise ValueError("Repeated progress receipt")
            receipts.add(item["progress_receipt"])
        if item["status"] == "finished":
            streak = 0 if item["progress_receipt"] is not None else streak+1
    for key in ("model_seconds", "active_seconds"):
        if sum(a[key] for a in attempts) > LIMITS[key]:
            raise ValueError("Budget exceeded")


def reserve(journal, contract_digest, *, run_id, run_attempt,
            model_seconds, active_seconds):
    """Charge full timeout allowances before launch; reservations never refund.

    Repeated run identities are rejected, including after an uncertain response.
    Caller must reconcile the durable record instead of launching again.
    """
    _validate(journal, contract_digest)
    for name, value in (("run_id", run_id), ("run_attempt", run_attempt),
                        ("model_seconds", model_seconds),
                        ("active_seconds", active_seconds)):
        _integer(value, name, 1)
    attempts = journal["attempts"]
    if model_seconds > active_seconds:
        raise ValueError("Model allowance exceeds active allowance")
    if any(a["status"] == "reserved" for a in attempts):
        raise ValueError("Predecessor requires reconciliation")
    if any((a["run_id"], a["run_attempt"]) == (run_id, run_attempt) for a in attempts):
        raise ValueError("Duplicate launch identity")
    no_progress = 0
    for a in reversed(attempts):
        if a["progress_receipt"] is not None:
            break
        no_progress += 1
    if len(attempts) >= LIMITS["attempts"] or no_progress >= LIMITS["no_progress"]:
        raise ValueError("Attempt or no-progress limit reached")
    for key, allowance in (("model_seconds", model_seconds),
                           ("active_seconds", active_seconds)):
        if sum(a[key] for a in attempts) + allowance > LIMITS[key]:
            raise ValueError("Insufficient remaining allowance")
    result = copy.deepcopy(journal)
    result["attempts"].append({"run_id": run_id, "run_attempt": run_attempt,
                               "model_seconds": model_seconds,
                               "active_seconds": active_seconds,
                               "status": "reserved", "progress_receipt": None})
    return result


def finish(journal, contract_digest, *, run_id, run_attempt,
           progress_receipt=None):
    """Trusted caller only, after provider inactivity and evidence reconciliation.

    A receipt digest identifies independently verified new progress; this module
    does not authenticate or validate that evidence. Missing evidence counts as
    no progress. Reusing an old progress digest cannot reset the stop counter.
    """
    _validate(journal, contract_digest)
    if not journal["attempts"]:
        raise ValueError("No reservation")
    if progress_receipt is not None:
        initialize(progress_receipt)
        if any(a["progress_receipt"] == progress_receipt for a in journal["attempts"]):
            raise ValueError("Reused progress receipt")
    last = journal["attempts"][-1]
    if (last["run_id"], last["run_attempt"], last["status"]) != (
            run_id, run_attempt, "reserved"):
        raise ValueError("Wrong or already reconciled reservation")
    result = copy.deepcopy(journal)
    result["attempts"][-1].update(status="finished", progress_receipt=progress_receipt)
    return result
