# Phase 1 outcome contracts

Use this optional format when an engineering task needs portable, machine-readable intent and no existing authority adequately carries it. Reuse an adequate brief or Build Contract; do not create a competing acceptance record. Keep the contract beside the existing plan and link it when checkpointing.

## Define and route

Record exactly one primary `question` with paired `build`, `why`, and falsifiable `prove`. Acceptance entries name an observable question, method, expected result, status and evidence references. Scope names included and excluded work; constraints retain invariants, and blockers retain unresolved dependencies. Record the attributable delivery endpoint and independent readback in the existing plan; this format has no endpoint field.

Select the smallest route that fits the affected flow:

- `small_fix`: known local behavior with narrow regression coverage.
- `bounded_feature`: new behavior across known boundaries with integration checks.
- `architecture`: consequential interface, data or deployment changes requiring the applicable architecture guidance, recovery and review.
- `investigation`: unresolved root cause or requirements; gather evidence before dependent edits.

Routes guide proportional discovery and proof, not permissions or automatic delegation. Security, persisted data, production, ownership uncertainty and locked decisions retain their governing safeguards.

## Authority and status

`authorization` is `not_granted` or `granted_for_scope`. Record the latter only from attributable user instructions or applicable standing authority, retaining that source in the existing plan. A contract value never grants permission, answers an open question, or approves an irreversible effect. Read-only investigation can proceed without mutation authority; required approvals still precede their protected action.

Use `draft`, `ready`, `in_progress`, `blocked`, or `verified` to describe actual progress. `ready` does not establish approval. Mark acceptance `pending`, `passed`, `failed`, or `blocked`; `passed` needs inspected, reproducible evidence for the actual work. Reset affected checks after source changes. `verified` requires all checks passed, no blockers, and the task's existing delivery/readback gates. Structural validity alone cannot advance status.

## Validate and execute

The shape is [contract.schema.json](../schemas/contract.schema.json). Run the standard-library authoring check:

```powershell
py -3 "C:/Users/Marcus Gollahon/.codex/skills/deep-loop/scripts/verify_contract.py" <contract.json>
```

Exit 0 checks recorded fields, unique check IDs, evidence-reference presence and completion consistency. Exit 1 rejects those rules; exit 2 reports unreadable/invalid JSON or CLI usage. The schema documents the shape; the CLI implements its own checks and additional invariants, not full JSON Schema validation. Neither executes acceptance, authenticates evidence, verifies freshness or inspects the delivered endpoint. Evidence references must omit secrets.

This Phase 1 JSON is not the Verification Contract JSON accepted by `deep_loop.py bind-contract`. For bound proof, use [Verification Contract integration](verification-contract-integration.md) to derive and link the appropriate proof contract from this acceptance authority. Preserve requirement IDs and run status in the existing checkpoint/check results rather than treating the two formats as interchangeable.

Run its regression checks with `py -3 -B scripts/test_contract.py` from this skill directory. The existing `scripts/verify_skill.py check` suite also runs these tests. Existing Deep Loop helpers, checkpoint schemas and delivery gates remain in effect.
