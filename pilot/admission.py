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


def initialize(contract_digest, *, workflow=False):
    """Explicit enrollment only; caller must authenticate the frozen contract."""
    if (not isinstance(contract_digest, str) or len(contract_digest) != 64
            or any(c not in "0123456789abcdef" for c in contract_digest)):
        raise ValueError("Invalid contract digest")
    result = {"schema": 2 if workflow else 1, "contract_digest": contract_digest,
              "limits": dict(LIMITS), "attempts": []}
    if workflow: result["task_credits"] = []
    return result


def _validate(journal, contract_digest):
    if not isinstance(journal, dict) or set(journal) != ({
            "schema", "contract_digest", "limits", "attempts"} |
            ({"task_credits"} if journal.get("schema") == 2 else set())):
        raise ValueError("Missing or incompatible journal")
    if type(journal["schema"]) is not int or journal["schema"] not in (1, 2) or journal["limits"] != LIMITS:
        raise ValueError("Changed schema or approved limits")
    initialize(contract_digest)
    if journal["contract_digest"] != contract_digest:
        raise ValueError("Contract drift")
    attempts = journal["attempts"]
    if not isinstance(attempts, list) or len(attempts) > LIMITS["attempts"]:
        raise ValueError("Invalid attempt history")
    credit_map = {}
    credit_receipts = set()
    credits = journal.get("task_credits", [])
    if not isinstance(credits, list) or len(credits) > len(attempts):
        raise ValueError("Invalid task credit history")
    previous_index = -1
    for credit in credits:
        if not isinstance(credit, dict) or set(credit) != {"run_id", "run_attempt", "progress_receipt"}:
            raise ValueError("Invalid task credit record")
        for key in ("run_id", "run_attempt"):_integer(credit[key], key, 1)
        initialize(credit["progress_receipt"])
        matches = [i for i,a in enumerate(attempts) if isinstance(a,dict) and
                   (a.get("run_id"),a.get("run_attempt")) == (credit["run_id"],credit["run_attempt"])]
        if (len(matches) != 1 or matches[0] <= previous_index or
                attempts[matches[0]].get("status") != "finished" or
                attempts[matches[0]].get("progress_receipt") is not None or
                credit["progress_receipt"] in credit_receipts):
            raise ValueError("Repeated or unbound task credit")
        previous_index = matches[0]
        credit_map[(credit["run_id"],credit["run_attempt"])] = credit["progress_receipt"]
        credit_receipts.add(credit["progress_receipt"])
    identities = set()
    receipts = set(credit_receipts)
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
            streak = 0 if item["progress_receipt"] is not None or identity in credit_map else streak+1
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
        if a["progress_receipt"] is not None or any(
                (c["run_id"],c["run_attempt"]) == (a["run_id"],a["run_attempt"])
                for c in journal.get("task_credits", [])):
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
        if (any(a["progress_receipt"] == progress_receipt for a in journal["attempts"]) or
                any(c["progress_receipt"] == progress_receipt for c in journal.get("task_credits", []))):
            raise ValueError("Reused progress receipt")
    last = journal["attempts"][-1]
    if (last["run_id"], last["run_attempt"], last["status"]) != (
            run_id, run_attempt, "reserved"):
        raise ValueError("Wrong or already reconciled reservation")
    result = copy.deepcopy(journal)
    result["attempts"][-1].update(status="finished", progress_receipt=progress_receipt)
    return result


def credit_task(journal, contract_digest, *, run_id, run_attempt, progress_receipt):
    """Append one authenticated task credit; retain all charged attempt bytes.

    Trusted coordinator only, after durable owned task acceptance. Schema 1
    pilot histories cannot be upgraded implicitly or credited by this function.
    """
    _validate(journal, contract_digest)
    if journal['schema'] != 2 or not journal['attempts']:
        raise ValueError('Explicit workflow journal required')
    initialize(progress_receipt)
    last = journal['attempts'][-1]
    if (last['run_id'],last['run_attempt'],last['status']) != (run_id,run_attempt,'finished'):
        raise ValueError('Latest finished attempt required for task credit')
    if last['progress_receipt'] is not None or any(
            (c['run_id'],c['run_attempt']) == (run_id,run_attempt) or
            c['progress_receipt'] == progress_receipt for c in journal['task_credits']):
        raise ValueError('Repeated task progress credit')
    result = copy.deepcopy(journal)
    result['task_credits'].append(dict(run_id=run_id,run_attempt=run_attempt,progress_receipt=progress_receipt))
    _validate(result, contract_digest)
    return result
