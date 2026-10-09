# Deep Loop State Schema (version 4)

`state.json` is the authoritative checkpoint. `plan.md` owns the readable task contract. Phases before SHIP remain agent-maintained. `deep_loop.py complete` is the only ordinary transition to COMPLETE: it validates SHIP against an unchanged state preimage and atomically writes the terminal fields.

Required session fields created by `init`: `schemaVersion: 4`, `sessionId`, `task`, `active`, `complete`, `phase`, `startedAt`, `uiRoute`, `checks`, `delivery`.

Schema-1/2/3 sessions remain readable and retain their original validation behavior. They are not silently upgraded because endpoint authority, branch disposition, and UI-route provenance require attributable evidence.

## UI route

Schema-4 sessions start with `uiRoute: {"kind": "pending"}`. Before source edits, classify the work and run `validate --stage build`:

- `not_applicable` requires a scope-specific `reason`.
- `specified` requires `approvedTarget` and `evidence` naming the approved visual target or exact repository pattern.
- `greenfield` requires exactly three distinct `options`; a `selectedDirection` from those options; `selection: {source: "user", evidence}`; `designProvenance: {route: "product-design", evidence}`; `mobbin` with an evidenced `inspected` or `no_comparable` status; and nonempty `affectedSurfaces` and `plannedEvidence` arrays.

The helper validates record shape, not whether the cited design decision or source was genuine. The agent still inspects the evidence. An unavailable required Mobbin pass remains pending rather than being relabeled `no_comparable`.

## Checks

Each entry has `name` and `status`:
- `pending` or `failed`: blocks validation at its required stage; record failure evidence when available.
- `passed`: requires a nonempty `evidence` string describing the check, observed result, and artifact or command that supports it.
- `not_applicable`: requires a nonempty `reason` tied to the actual scope.

Checks and tasks may declare `stage: review` (default), `ship`, or `closeout`. REVIEW requires review-stage records; SHIP and ordinary completion require every stage. The internal preservation `delivery` stage requires review and ship proof, deferring only explicit closeout records to the preserved working checkpoint. Invalid stage values fail validation. BUILD checks readiness, contract identity and applicable design authority, not post-implementation passing results.

Choose the checks from the task's acceptance criteria. At least one must pass with evidence; a collection containing only not-applicable checks cannot establish acceptance. Reset affected checks and delivery to pending after relevant changes.

A passed hosted-CI check also uses `kind: "external_ci"` and `externalEvidence: {provider, url, revision, conclusion}`. `conclusion` must be `success`, `url` must identify the observed HTTP(S) run, and `revision` must equal the delivered revision. For a single-target delivery, it must equal `delivery.revision`. For a multi-target delivery, add `target` with the matching `delivery.targets[].id`; the revision must equal that target's revision. Static workflow files, job names, queued runs, and prose that a check will run later are not execution evidence.

## Delivery

`endpoint`: exact target defined in the plan.
`status`: pending, failed, or verified.
`evidence`: independent readback, its observed result, and enough target/version information to identify what was delivered.
`revision`: exact commit, artifact digest, build identifier, or other immutable revision used by delivery evidence.
`endpointDecision`: `{status, source, evidence}`. `status` is `pending` until settled; `source` is `user`, `repository`, or `contract`; `evidence` identifies the attributable instruction. Agent-authored goal wording is not an authority source.
`branchDisposition`: required for SHIP. A single-target Git task branch uses `{kind, status, revision, evidence}`, where `kind` is `pull_request`, `merged`, or `kept_local`, `status` is `verified`, and `revision` equals `delivery.revision`. `kept_local` is valid only with a user-sourced endpoint decision. For non-Git or non-branch delivery, use `{kind: "not_applicable", reason}`.

When one delivery endpoint contains multiple independently versioned targets (for example, pull requests in separate repositories), use `delivery.targets` instead of a composite `delivery.revision` or top-level `branchDisposition`. It is a nonempty array of objects with a unique `id`, that target's immutable `revision`, independent readback `evidence`, and a `branchDisposition` using the same rules above. Each passed hosted-CI check must name its target ID in `externalEvidence.target`; the helper verifies that the target exists and that its CI and branch-disposition revisions exactly match that target. Keep the aggregate endpoint, status, and evidence at the top level. The single-target fields remain supported for existing schema-3/4 checkpoints.

Review validation requires a settled endpoint decision. Ship validation additionally requires verified status, endpoint, evidence, passing review requirements, and either a single immutable delivery revision with its branch disposition or complete revision/readback/branch records for every target. Evidence strings are references and claims; the agent must inspect their truth and freshness.

## Optional records

`verificationContract`: `{path, sha256, semanticsSha256, endpoint}` written by `bind-contract`. `semanticsSha256` excludes only mutable aggregate/verifier run status and evidence fields. Bound checks use `verifierId` from that contract. At REVIEW/SHIP every due blocking verifier needs a unique passed check with evidence; `not_applicable` cannot waive it. Use `refresh-contract` only when the endpoint and semantic hash are unchanged; it updates the file hash without resetting evidence. Any requirement, invariant, verifier definition, gap, ship gate, endpoint, or legacy binding without semantic identity requires `bind-contract`, which resets check/delivery evidence. SHIP delivery must use the bound endpoint. The helper preserves legacy record-only behavior. A verifier declaring bound deterministic `proof` also requires the check's `receipt: {path, sha256}` and validates current declared invocation/input/artifact identity; see [durable receipts](verification-contract-integration.md#durable-deterministic-receipts). It does not authenticate human judgments or independently establish live endpoint truth.

`tasks`: dependency-aware local task, issue, and decision records. See [local-tracker.md](local-tracker.md) for fields and ownership. Absence preserves the small-task and existing-session workflow. When present, every record must be valid; due tasks must be done with evidence or cancelled with an authorized scope reason. REVIEW evaluates review tasks; SHIP evaluates all stages. Cancelled prerequisites never satisfy a dependency.

`uiEvidence`: optional registered UI request path/hash, current source/environment manifests, bound invocation receipts and unresolved differences. A registered substantive request requires an approved Design Contract; actual receipts, artifact hashes, coverage, native reports and preserved pixels are checked at REVIEW/SHIP through [UI design adapter](ui-ux-integration.md). Schema-4 `uiRoute` remains the independent recorded BUILD decision. Neither field authenticates human identity or host activity.

`goal`: optional native-goal linkage, containing `objective` copied from the runtime goal. It records association, not status or authority; query `get_goal` on resume. The helper neither creates goals nor validates their runtime state.

`issues`: unresolved failures with evidence and next safe action. A nonempty list blocks validation; clear resolved entries only after fresh verification.

`debt`: entries with `item` and `status`:
- `open`: blocks validation.
- `paid`: requires `evidence` of paydown.
- `accepted`: requires `acceptance` recording the user's explicit acceptance, `owner`, and `paydown` task. Acceptance must cover the current scope; it does not waive a failed requirement.

`blocker`: current impediment and recovery path when required evidence or authority is unavailable. A nonempty blocker prevents validation; keep complete false and clear it only when resolved.

## Example: local artifact

```json
{
  "schemaVersion": 4,
  "sessionId": "8405b17e",
  "task": "Add CSV export",
  "active": true,
  "complete": false,
  "phase": "SHIP",
  "startedAt": "2026-10-04T20:00:00+00:00",
  "uiRoute": {"kind": "not_applicable", "reason": "The task has no user-facing UI"},
  "checks": [
    {"name": "CSV content", "status": "passed", "evidence": "CLI fixture check: exported rows and headers match expected.csv"},
    {"name": "Production deployment", "status": "not_applicable", "reason": "Requested endpoint is a local tool"}
  ],
  "delivery": {
    "endpoint": "Saved CSV export CLI",
    "endpointDecision": {"status": "settled", "source": "user", "evidence": "User requested a local CLI artifact"},
    "revision": "sha256:53f2...",
    "status": "verified",
    "evidence": "Fresh invocation of sha256:53f2... generated the expected CSV",
    "branchDisposition": {"kind": "not_applicable", "reason": "The delivered artifact is not maintained on a task branch"}
  }
}
```

Complete only after ship validation and independent inspection of evidence; then run `deep_loop.py complete`. Do not hand-edit terminal fields.

## Archived closeout

`preserve` retains exact original files under an external archive's `snapshot/`; `archive.json` records their hashes and any restore-tested Git HEAD bundle. Its `checkpoint/` is the resumable working copy, with the bound contract relocated to preserved bytes and a pending Post-ship closeout check explicitly staged `closeout`. `retire-checkpoint` requires unchanged source bytes and removes only that checkpoint and a matching current pointer. After independent cleanup readback, `finalize-archive` records evidence, validates SHIP, and finalizes this working copy; `final.json` records hashes of final state and evidence. Original snapshot bytes remain unchanged. These records verify integrity, not the truth of supplied shipment/cleanup claims; the coordinator owns live readback and writer quiescence. Archives remain until explicitly pruned.

A preserved working checkpoint may contain `proofResolution: {path, sha256}` written by the helper. It binds the retained logical-to-physical dependency map. Archived validation locates that map in the current archive, checks integrity, and resolves only retained copies; approved contract, request, receipt and artifact bytes stay unchanged. Do not hand-author a map to substitute different evidence.

A blocking bound verifier may declare `proof.readback` for structured artifact-backed endpoint inspection. Its generated check is ship-stage and carries the existing `receipt` binding. Declared endpoint, exact single/multi-target set, observed revisions and delivered file digests must match current delivery at SHIP/preservation/complete; changing a check stage cannot waive readback. See [bound endpoint readback](verification-contract-integration.md#bound-endpoint-readback). No new completion command or schema version is introduced.
