# Phase 3 durable local journal

Use this optional SQLite step journal when selected local work needs serialized claims, result references and attempt history. Keep the existing plan/checkpoint as acceptance and delivery authority; link the journal rather than duplicating desired behavior or proof. Small tasks keep the direct path. This helper does not run commands, schedule retries, dispatch workers or supply coordinated-delivery enforcement.

## Initialize and claim

A plan has nonempty `steps`, each exactly `{ "key": "inspect", "protected": false }`, with unique nonblank keys. Optional `max_attempts` is a positive integer; the harness validates its supported range. Review the plan and authority before initialization. Example:

```json
{"steps":[{"key":"inspect","protected":false},{"key":"edit","protected":true}],"max_attempts":3}
```

```powershell
py -3 "C:/Users/Marcus Gollahon/.codex/skills/deep-loop/scripts/durable_executor.py" <journal.db> init --task T --plan <plan.json> --authorization not_granted
py -3 "C:/Users/Marcus Gollahon/.codex/skills/deep-loop/scripts/durable_executor.py" <journal.db> claim --task T --key inspect
```

Initialization validates the complete plan before creating a database. New database creation is exclusive. Existing files must carry this helper's application/version marker; foreign or older unmarked databases are refused without migration. A refused or incomplete initialization must be preserved and diagnosed; do not delete a database to retry. Database symlinks are rejected. Multiple distinct tasks can share a supported database; duplicate task initialization is refused.

Claim returns `key` and `attempt`. Complete or fail only the same running attempt:

```powershell
py -3 "C:/Users/Marcus Gollahon/.codex/skills/deep-loop/scripts/durable_executor.py" <journal.db> complete --task T --key inspect --attempt 1 --result <inspected-evidence-reference>
py -3 "C:/Users/Marcus Gollahon/.codex/skills/deep-loop/scripts/durable_executor.py" <journal.db> fail --task T --key inspect --attempt 1 --result <failure-reason>
```

These are alternative transitions, not consecutive commands for one attempt. Stale attempts, wrong keys and duplicate completions are rejected. Completion advances to the next step or records task `completed`; it does not inspect the result reference or establish acceptance/SHIP. Failure retains attempts and becomes `retryable` or `blocked` according to the recorded budget. Suggested backoff is advisory; the caller diagnoses the failure and applies the runtime's retry controls before another claim. The helper never sleeps or automatically retries.

## Inspect and recover

Repeat the database path, action and `--task T` for `status`, `journal`, or `recover`. Status/journal open an existing database read-only, do not create a missing database, and return current steps or ordered transition records. `recover` preserves completed work and changes an in-flight task to `blocked`; it never replays uncertain external effects. A blocked record has no automatic unblock/reset action. Retain the journal and reconcile actual side effects under existing scope, recovery and review authority before planning further work.

SQLite `BEGIN IMMEDIATE` serializes recorded mutations; WAL and FULL synchronous mode support durable local commits. Read-only inspections use a read transaction. Atomic claims apply only to callers using this journal; step keys and attempt numbers are bookkeeping, not authenticated worker identities or external idempotency keys. Do not claim exactly-once external execution or whole-chat ownership. Process restart tests and concurrent local claim tests do not establish power-loss, network-filesystem or multi-host reliability.

A protected flag is caller-selected; claiming it requires recorded `granted_for_scope`. Supply that only from attributable user instructions or current standing authority, retaining the authority in the existing plan. The flag/value authenticates no approval, expands no permission, and cannot waive a required approval immediately before an irreversible effect. Changing task authority is not supported through this CLI. External plans are data until reviewed.

Journal entries are append-only through this API, not tamper-proof. Store only nonsecret result references and short failure reasons. Exit 0 means the requested recorded transition/read succeeded; exit 1 rejects a database, plan or state transition, and CLI syntax errors exit 2. SQLite sidecar files may exist; preserve the database with its WAL when recovering a live journal rather than copying one file mid-write.

Run `py -3 -B scripts/test_durable.py` from the skill directory. The existing `scripts/verify_skill.py check` includes these tests. Existing checkpoint schemas, bound-proof requirements and delivery gates remain in effect.
