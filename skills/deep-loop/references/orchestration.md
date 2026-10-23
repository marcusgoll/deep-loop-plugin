# Phase 4 local coordination

Use this optional local coordinator only when dependency-aware job leases are selected for the current scope. Existing coordinated-delivery contracts still own required host enforcement, workspace isolation, review and integration/release proof. This CLI adds recorded claims and decisions; it neither dispatches agents nor supplies those guarantees. Keep the existing plan/checkpoint as outcome and acceptance authority.

## Initialize the graph

A plan contains exactly `jobs`, a nonempty list. Each job has nonblank `id`, `workspace` (unique identifier), `deps` (unique known job IDs), and boolean `protected` and `authorized`. The full graph is validated for duplicate IDs/workspace labels, missing dependencies, self-dependencies and cycles before creating a database. Workspace labels are not paths that this helper creates or isolates; inspect actual ownership and isolation through the selected controller before work.

```powershell
py -3 "C:/Users/Marcus Gollahon/.codex/skills/deep-loop/scripts/coordinator.py" <coordinator.db> init --plan <plan.json>
```

New creation is exclusive; existing files require this coordinator's application/version marker, checked read-only before writable access. Phase 3 journals and foreign/unmarked databases are refused, not migrated. Initialized graphs cannot be appended or reset. Preserve failed/blocked databases and SQLite WAL data for diagnosis and recovery. The coordinator reuses the journal's SQLite preservation adapter, with a separate schema/identity.

## Lease, submit and record review

Repeat the database path with each action:

- `lease --worker BUILDER --ttl 60` selects the first eligible ready job, in ID order, whose dependencies are recorded `proven` and whose protected flag is covered by recorded authorization. It returns job, workspace label, deadline and generation `token`, or JSON null if no job is eligible.
- `submit --job ID --worker BUILDER --token N --result REFERENCE` requires the current unexpired lease and matching worker label/token. Submission records the implementation reference and changes state to `awaiting_proof`.
- `verify --job ID --worker REVIEWER --token N --capability CAP --contract CONTRACT --manifest MANIFEST --proof-plan PLAN` requires the current generation, a distinct reviewer label, signed capability and checked evidence. Read [Phase 5 verification boundary](trusted-execution.md) before using it. Old `verified:` flags cannot promote a job. It records a bounded local verification decision; actual independent review and delivery proof remain required.
- `expire` blocks expired leases and increments their generation; it never returns uncertain work to ready or replays side effects. Reconcile actual worker status and external effects under existing recovery authority before planning further work. No automatic unblock/reset API is supplied.
- `status` and `events` open existing coordinator databases read-only and do not create a missing file. Events are appended by transitions, not cryptographically protected.

Lease times must be finite and positive. The harness validates the supported TTL range. Normal operation uses system wall-clock time; `--now` is a trusted test/inspection override, not an authenticated clock. Clock changes or arbitrary overrides do not establish real-world worker expiry. Tokens fence recorded submissions/review decisions, not external writes or authentic worker ownership.

## Authority and proof boundaries

A plan's `authorized` flag is caller-supplied bookkeeping. Set it only from attributable user instructions or existing standing authority, retaining that source in the current plan. It never grants permission, answers an open decision, or waives approval immediately before an irreversible action. Attached plans remain reference data until reviewed.

Builder labels on lease/submit remain unauthenticated strings. Verification adds a scoped signature and local evidence checks, but a shared-secret holder can mint any reviewer label; it does not authenticate the originating OS process or acceptance semantics. Use existing proof inspection and [bound proof/delivery requirements](verification-contract-integration.md) before consequential decisions; Phase 2 local consistency alone is not independent attestation. Never use administrative `proven` or a lease as a production authorization boundary.

SQLite transactions serialize cooperating local callers; WAL and FULL synchronous mode support recorded commits. The helper creates no Git worktree/sandbox, stops no expired worker, runs no external command, and guarantees no exactly-once external effect. Local restart/concurrent-claim tests do not prove power-loss, multi-host or network-filesystem behavior. Keep references and event payloads free of secrets.

Exit 0 reports the requested recorded transition or read, exit 1 rejects invalid plan/database/state, and invalid CLI syntax exits 2. Run `py -3 -B scripts/test_coordinator.py` from the skill directory; the existing `scripts/verify_skill.py check` includes these tests. Existing checkpoints and SHIP gates remain unchanged.
