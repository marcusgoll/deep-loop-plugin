# Checkpoint operations

- [Initialize and discover](#initialize-and-discover)
- [Local tasks and goal continuation](#local-tasks-and-goal-continuation)
- [Helper boundaries and existing sessions](#helper-boundaries-and-existing-sessions)
- [Collect safe independent checks](#collect-safe-independent-checks)
- [Read-only recovery report](#read-only-recovery-report)
- [Recoverable active handoff](#recoverable-active-handoff)

Read when creating or recovering a checkpoint, using tracked tasks, validating state, or protecting and closing local sessions. The main skill owns acceptance and delivery; this reference owns their optional local records.

## Initialize and discover

When checkpointing a new task, initialize from the project root; reuse the matching session on resume:

```powershell
py -3 "C:/Users/Marcus Gollahon/.codex/skills/deep-loop/scripts/deep_loop.py" init --task "<task>"
```

For substantive UI, add `--ui-request <request.json>` to `init` or `bind-contract`; follow the [UI adapter](ui-ux-integration.md) for approved binding and current task-level receipts. This registers scope and does not replace schema-4 `uiRoute` or its BUILD gate.

Read `.deep-current.json` to locate a checkpointed session. New sessions contain only:
- `plan.md`: acceptance criteria, delivery endpoint/readback, tasks, risks and recovery.
- `state.json`: current phase, checks and evidence, delivery status; add issues or debt only when they exist.

Read [state-schema.md](state-schema.md) when filling or validating a checkpoint. New sessions use schema 4, which records endpoint authority, hosted-CI run identity when applicable, branch disposition, and the UI route BUILD gate. On resume, read both records and inspect the current workspace and delivery target. Re-run checks affected by changes since their recorded evidence.

When recovering checkpointed work or resolving relevant shared-work ownership, run `scan` from the project root to discover unfinished sibling sessions. A small settled task with no recovery or ownership question needs no scan. Treat results as recovery candidates, not new authority or proof of interruption; inspect relevant plans, current facts, and actual chat/worker ownership before resuming. Preserve completed exclusions and unrelated work.

## Local tasks and goal continuation

For dependent implementation slices, recurring issues, or work that may be interrupted, read [local tracker](local-tracker.md). Store task, issue, and decision records once in `state.json.tasks`; `plan.md` links their IDs and owns scope. Existing external trackers remain authoritative when configured: use local records for bounded execution slices with source links, without copying externally owned ticket status. Small single-step work still needs no tracker.

Use `next` to inspect dependency-ready, unclaimed tasks in record order. The agent confirms scope and ownership, records its claim under a single coordinator, executes the next safe action, verifies acceptance, and checkpoints evidence. Continue through ready work without routine human approval within existing authority. Runtime goal tools own continuation and status; task-selection commands neither execute work nor create goals. `run-checks` runs only an explicitly supplied authorized verifier argv batch.

Record implementation failures as issue tasks with acceptance and a repair action. Link any existing unresolved issue ledger entry until the original failure is verified resolved. Reset affected task evidence, dependent completed tasks, checks, and delivery after changes. Use `graph` only when a derived dependency diagram helps explain the work; it has no separate status authority.

An empty ready queue requires inspection: tasks may be claimed, running, blocked, cancelled prerequisites, or absent from the tracker. `terminal` means only that recorded tasks are done or cancelled; it does not prove scope coverage, acceptance, delivery, or native goal completion. Missing dependencies, cycles, and malformed records prevent validation. Unfinished review-stage records block REVIEW; SHIP requires review, ship and closeout records. Archive preservation requires review/delivery acceptance while deferring explicit closeout until actual retirement can be read back. Inspect coverage against the plan and perform the full SHIP readback before completing a goal.

Continue a discovered session automatically only when it matches the current authorized objective, current facts support recovery, and no other writer owns it. Preserve a linked recovery candidate otherwise; do not silently widen the goal, invent a user decision, or take over an unknown owner. Recheck blocked conditions when relevant facts change and continue independent tasks that remain safe. Human choices and irreversible-action boundaries retain their existing gates.

### Keep checkpoints local

`.deep-<id>/` folders and `.deep-current.json` are local resume evidence. When Git is available, `init` adds `.deep-*/` and `.deep-current.json` to the repository's local `info/exclude`, including for linked worktrees. It preserves existing rules and does not change tracked `.gitignore` files or stage anything. Outside Git, initialization still works.

Protect existing sessions from the project root without creating another session:

```powershell
py -3 "C:/Users/Marcus Gollahon/.codex/skills/deep-loop/scripts/deep_loop.py" exclude
git ls-files '.deep-*'
```

Ignore rules do not untrack files already committed and can be bypassed by forced staging. Check staged paths before every commit; never stage checkpoints, including with `git add -f`. If checkpoints are already tracked, preserve a recovery copy and remove only their exact paths from the index with `git rm --cached` under the repository's authority and review gates. Keep local files intact. Teams that want a shared rule can put the same patterns in the tracked `.gitignore` through their normal review workflow.

Keep active or blocked sessions for resume. After verified shipment, retaining a locally excluded checkpoint is valid when no retirement is needed. For selected actual retirement, perform authorized recoverable closeout using [project lifecycle](project-lifecycle.md#recoverable-post-ship-closeout): preserve the exact checkpoint and required ignored evidence outside the checkout before retiring eligible task state. Retain archives until explicitly pruned; SHIP alone never authorizes blind deletion. Cancelled sessions remain intact unless separately dispositioned. Promote only useful durable decisions or evidence to the existing project/vault authority.

## Helper boundaries and existing sessions

`status`, `list`, and `use --session <session8>` read or select sessions. Place `--root <project>` before the command to work outside the current directory. To cancel, set `active: false`; leave `complete: false`.

Without an explicit locator, the helper uses a valid current pointer or the sole checkpoint. A missing pointer target or multiple unselected checkpoints fails; select `--session` or `--path` after confirming task identity. Helper JSON writes replace a flushed temporary file atomically. This prevents partial replacement, not concurrent-writer conflicts or a transaction across plan, state, and pointer; retain single-writer ownership and recovery readback.

Validation defaults to a failing exit status for unmet recorded requirements. `--mode warn` is diagnostic only. Legacy generic checks validate recorded evidence fields. Explicit bound deterministic checks inspect captured execution and current declared input/artifact identity; see [Verification Contract integration](verification-contract-integration.md#durable-deterministic-receipts). Bound UI checks additionally inspect current hashes, native invocation/report receipts, case/metric coverage and preserved pixels through the UI adapter. Validation does not execute delivery or authenticate human decisions. Schema-4 `validate --stage build` enforces UI-route classification and greenfield provenance before source edits. The `complete` command is the only ordinary checkpoint transition to COMPLETE: it validates SHIP, rejects state drift, and writes the three terminal fields atomically.

Existing schema-1, schema-2, and schema-3 sessions remain untouched and readable. Schema 2 retains its original validation behavior; schema 3 retains its endpoint/delivery contract without gaining the schema-4 BUILD gate by implication. Schema-1 `validate --stage review` preserves recorded-flag/debt validation, while `--stage ship` fails because it lacks the delivery contract. Continue legacy sessions under their recorded contract or start a new schema-4 session and carry forward relevant acceptance and evidence. The stage-aware review/ship/closeout semantics also preserve existing installed schema-2 records. The old `map`, `--level`, and overwrite options are retired; existing maps and records remain available.

For registered UI and bound deterministic proof, preservation retains the original approved file bytes and logical paths, then records an integrity-bound resolution map to archive-relative copies of every dependency actually read by validation. Archived reads use those copies without falling back to original files. Verification rechecks bound acceptance before retirement or finalization; missing, changed, escaping or unsupported dependencies block closeout. Moving an intact archive changes its physical location, not its approved identities. This verifies retained acceptance evidence rather than executing a new verifier or proving live delivery. Keep originals until preservation and recovery checks pass.

A pending bound deterministic closeout check cannot yet be carried into this immutable archive. Preservation fails before mutation; retain live state until that workflow has a supported proof path. Already captured bound proof and explicit manual closeout retain their respective gates.

## Collect safe independent checks

Default `run-checks` preserves record order and stops at the first failure. Use `--collect-independent` only for a finite, already authorized batch whose commands you have inspected. The flag and a `safe: true` declaration do not grant authority to execute a command. Runtime limits, retries and concurrency remain with the host harness; this helper runs commands sequentially.

Every collection entry declares `name`, exact `argv`, unique nonempty `id`, boolean `safe`, and `dependsOn` as a list of IDs in the same batch. Optional `required` defaults to `true`. With a bound contract, also supply `verifierId`; a blocking contract obligation cannot be downgraded using `required: false`. The runner validates the entire declared graph before starting commands or creating the results file, rejects unknown dependencies and cycles, and uses stable dependency order only in collection mode.

For example, two independent checks may both run even if the first fails:

```json
[
  {"id":"format","name":"format","argv":["checker","format"],"safe":true,"dependsOn":[]},
  {"id":"tests","name":"tests","argv":["checker","test"],"safe":true,"dependsOn":[]}
]
```

An unsafe entry is skipped. An entry whose prerequisite failed or was skipped is also skipped; independent safe entries continue. Each skipped row records a reason and null exit code, with no execution receipt. An optional failed prerequisite still blocks its dependents. Every executed failure and every required skip produces a failing aggregate exit. Optional skips remain visible even when they do not fail the aggregate; never use the aggregate alone as proof that every check passed.

Executed rows retain native exit code, stdout and stderr separately from the effective result. Failure to launch records `launchError` and a null native exit code because no process returned. Bound-input drift remains an effective failure even if the native command returned zero. Read every row, including skips and launch failures, before recording checkpoint evidence. A skipped, failed or stale bound verifier cannot satisfy acceptance or endpoint readback. Collection does not change checkpoint status, rerun commands, or interpret arbitrary suite output.

## Read-only recovery report

Use `deep_loop.py --root <project> recovery-report --path <checkpoint> --json` when recovering a selected checkpoint or inspecting its current blockers. An explicit `--session` is also supported; without a locator the existing current-pointer/sole-checkpoint rules apply. Ambiguous sessions or a broken pointer require an explicit confirmed selection. The report goes to stdout; save it outside checkpoint files if durable inspection evidence is needed. Existing `status` remains a compact recorded-state view. Exit zero and top-level blockers describe the current stage only; inspect delivery/ship issues and `localShipRequirementsSatisfied` before judging readiness to complete.

Read the report alongside the authoritative task and plan. It separates recorded phase, completion, checks and delivery from inspected local proof, stage-specific gate issues, and missing or stale evidence. Bound generic, UI and endpoint-readback evidence uses the existing validation paths and archive resolution. Manual and legacy evidence remains record-only: recorded passing fields cannot establish an independently inspected outcome. Local retained proof does not establish current live deployment, worker liveness, or human authorization.

The report leaves checkpoint state, plan and pointer unchanged, creates no checkpoint folders, runs no declared verifier command, and claims no writer ownership. Retained pixel metrics may be checked in process with the trusted bundled comparator; inspection creates no new evidence or output artifacts. Ownership remains unknown until inspected through the actual host and task authority. A changed checkpoint preimage during inspection prevents a stable snapshot claim. Missing or unavailable required inspection remains a blocker; a recorded COMPLETE label does not override current evidence failures.

Use the proposed next action as a conservative inspection or repair suggestion within the selected task, not permission to execute, take over another writer, complete a goal, or select backlog work. Resolve the named uncertainty, then perform the ordinary authorized action and its verification. Generating the report neither resets stale checks nor resumes execution.

## Recoverable active handoff

Use an active handoff when a selected task needs portable inspection before delivery. It requires neither SHIP nor retirement. Save current checkpoint records first under their existing authority, then capture a new packet outside the source checkpoint:

```text
deep_loop.py --root <project> handoff --path <checkpoint> --references <references.json> --output <new-packet>
deep_loop.py inspect-handoff --packet <packet>
```

The reference list explicitly selects local files or external URLs. Each entry has unique `id`, `kind` (`decision`, `contract`, `evidence`, or `ownership`), boolean `required`, nonempty `provenance`, and exactly one absolute local `path` or HTTP(S) `url`:

```json
[{"id":"decision","kind":"decision","path":"/absolute/task/decision.md","required":true,"provenance":"Existing approved task decision record"}]
```

Inspect the selected paths and their authority before capture; the declaration grants no permission. Checkpoint state and plan are included. Other local dependencies, including bound contracts, receipts, verifier/source/environment files and artifacts, must be explicitly listed; the helper does not search directories or automatically copy unrelated files. URLs are indexed without network access. Missing, inaccessible or unlisted dependencies remain explicit unavailable evidence. Do not list secret material for copying into a handoff.

Capture retains exact source bytes and logical identities with an integrity-bound map to packet copies. A changed source preimage or existing output blocks publication; retain failure evidence and inspect any unpublished staging before retrying to a fresh destination. An incomplete staging directory is diagnostic material, not a published handoff. Keep one writer for the destination: helper reservation coordinates cooperative writers, while outside filesystem changes still require ownership and preimage checks. Creating a packet successfully proves its saved structure and readback, not task acceptance or delivery.

An intact packet can be moved and inspected using retained copies without reading original files. Inspection verifies integrity and reports reference availability separately from the existing recovery report’s stage-specific proof and blockers. Its exit fails for required unavailable references or applicable recovery blockers; manual and legacy records retain record-only truth. A required URL is still an uninspected external dependency. No declared verifier command, writer claim, checkpoint reset, goal continuation or approval authentication occurs.

A checkpoint already carrying `proofResolution` is unsupported for active handoff and is refused before capture. Preserve its original archive/binding and use the existing archive inspection workflow; do not remove the binding to bypass this limit. This is an immutable active snapshot, not a retirement archive. Archive verification, retirement and finalization refuse it. It carries no Git history, checkout restore or transferred execution permission. The receiving agent reads the named authorities and actual ownership before continuing within the existing authorized objective; the packet alone cannot authorize takeover or new scope. Retain source records until the packet has been read back.
