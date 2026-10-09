# Local task tracker

Use optional `state.json.tasks` for bounded execution work. Keep one source of task status; the plan owns the objective, scope, exclusions, and delivery contract. Decision records may link the existing decision map without duplicating its answers. External authoritative tickets stay in their tracker; optional `source` links provenance or another session, not an automatic cross-session dependency or permission grant.

## Multiple sessions and maps

Multiple `.deep-*` sessions may coexist in one project. Reuse the matching session on resume; create another only for distinct authorized work or a justified handoff that preserves its predecessor. Link the [canonical map for the outcome](decision-mapping.md#one-canonical-map) from each relevant `plan.md`. Maps own decisions and relationships, plans own bounded scope and acceptance, and state owns session progress and evidence. Generated `graph.mmd` is a view of task records, never another status authority.

`.deep-current.json` is a shared convenience selector, not task identity, ownership, or a lock. With multiple chats in the same root, use `--session` or `--path` on session commands so another chat's `init` or `use` cannot redirect your work. Avoid switching the shared pointer during concurrent work when an explicit locator suffices. One coordinator writes each session; verify live ownership before takeover. Atomic file replacement and a pointer-write lock do not provide exclusive ownership of a session's plan/state.

`dependsOn` resolves IDs within the selected session only. Record cross-session prerequisites and combined acceptance in the existing parent map/contract or authoritative tracker, and inspect their current evidence before dependent work. A `source` link to another session records provenance; it neither enforces the prerequisite nor grants permission. Only the parent coordinator updates parent checkpoints, and a completed child cannot establish parent completion.

For an authorized reconciliation, use the following acceptance checklist. Keep checks pending until the corresponding proof is inspected; unresolved conflicts or unknown ownership block dependent changes.

| Requirement | Acceptance and proof |
|---|---|
| One map per outcome | Inspect relevant plans and map destinations: sessions sharing an outcome link to the same authority; separate maps have distinct completion boundaries. |
| Detail stored once | Inspect links and records: decisions and externally owned ticket status have one authoritative home; conflicting copies remain explicitly unresolved. |
| Explicit resume | Inspect the selected plan/state, live workspace, endpoint, ownership and blockers; session-specific commands use an explicit locator during concurrent work. |
| One writer per session | Verify actual coordinator/worker status before writes or takeover; owner fields alone are insufficient proof. |
| Cross-session dependencies | Inspect parent relationships and current prerequisite evidence; session-local dependency IDs and links cannot substitute for that proof. |
| Legacy preservation | Retain unique decisions, exclusions and evidence; identify each record's role and successor without silent merging or deletion. |
| Safe archival | Keep active/blocked sessions resumable. When cleanup is authorized, preserve completed/cancelled sessions outside the repository, retain or repair evidence links, and independently verify recovery and links. |

Retain the inspected inventory, source paths, conflicts, ownership observations and link/readback results in the existing reconciliation evidence. `list` and `scan` discover candidates; explicitly inspect additional project roots or worktrees when they are in scope because discovery is not recursive. Helper validation checks recorded fields, not live ownership, map uniqueness, evidence truth, or link integrity. Keep checkpoints locally excluded from Git and promote durable decisions to the existing project authority. Do not reconcile or auto-delete records merely to adopt this policy.

## Records

Each record requires nonempty `id`, `title`, and `acceptance`, plus `kind` (`task`, `issue`, `decision`) and `status` (`pending`, `running`, `blocked`, `done`, `cancelled`). IDs are unique within the session. Optional `stage` is `review` (default), `ship`, or `closeout`; invalid values fail. Use ship for delivery proof and closeout only for actual post-delivery retirement. REVIEW evaluates review tasks; SHIP evaluates all stages. `next` holds ship/closeout tasks until phase SHIP without changing ownership/dependency rules.

- `dependsOn`: optional list of prerequisite IDs in this same session. Missing IDs and cycles are invalid. Only done prerequisites satisfy dependencies.
- `owner`: optional chat/worker identity; empty means unclaimed. Running work requires an owner. Pending work with an owner is not offered by `next`.
- `evidence`: required when done, identifying the current observed acceptance result and its saved artifact/command. The agent inspects evidence; the helper checks its presence.
- `blocker` and `nextAction`: required when blocked. Distinguish waiting for a user, external condition, or repairable defect. Clear the blocker only after fresh verification; a task blocker is distinct from native goal status.
- `reason`: required when cancelled, linking the authorized exclusion or scope change. Cancelling work cannot waive required acceptance. A done task cannot depend on cancelled or unfinished work.
- `nextAction` may also identify the next repair or research step on pending issues/decisions.

```json
"tasks": [
  {"id": "build", "title": "Implement export", "kind": "task", "status": "done",
   "acceptance": "CSV headers and rows match the contract", "dependsOn": [],
   "evidence": "Fresh CLI invocation matched expected.csv"},
  {"id": "verify", "title": "Verify saved export", "kind": "task", "status": "pending",
   "acceptance": "Saved CLI passes an independent invocation", "dependsOn": ["build"], "owner": ""}
]
```

For a defect, add an issue record with its failing evidence and repair acceptance; make affected delivery work depend on it. Before changing a previously verified prerequisite, reopen affected done descendants and invalidate stale checks/delivery. Do not remove unfinished records to make validation pass.

## Read-only commands

Run from the project root; use the global `--root <project>` before the command when needed.

```powershell
py -3 "C:/Users/Marcus Gollahon/.codex/skills/deep-loop/scripts/deep_loop.py" next --session <session8>
py -3 "C:/Users/Marcus Gollahon/.codex/skills/deep-loop/scripts/deep_loop.py" scan
py -3 "C:/Users/Marcus Gollahon/.codex/skills/deep-loop/scripts/deep_loop.py" graph --session <session8>
```

`next` emits JSON with `queueState`, `ready`, and `waiting`. Ready records are pending, unclaimed, have done prerequisites, and belong to an active, unblocked session. Waiting records include reasons and their stored next actions. Record order is the tie-breaker. Invalid task structure/graphs exit nonzero. `untracked` means no task records; `terminal` means all recorded work is done/cancelled. Neither is a completion claim.

`scan` reads only direct `.deep-*` child folders in this project. It reports unfinished sessions, invalid records, and completed sessions with unresolved tasks/issues/blockers. Complete records with no such inconsistencies are omitted; historical exclusions stay closed. A corrupt sibling is reported without hiding other sessions; any invalid record gives a nonzero exit. It never changes state, the current-session pointer, ownership, or scope, and does not test live blocker conditions. Legacy plans/issue files still require inspection; an untracked session is not evidence that no tasks remain. It does not search unrelated repositories or worktrees automatically.

`graph` emits Mermaid source from the same tasks and dependencies; redirect it to the selected `.deep-<id>/graph.mmd` when a saved map helps. Regenerate it after changes; never edit its status as a separate tracker. All commands are inspections, not claims or executors.

## Ownership and recovery

One coordinator writes a session. Record its actual chat identity in optional `state.json.coordinator`; verify that writer's current status through the host before taking over. Use governing preimage, drift, and write rules when editing state. Task owners are bookkeeping, not atomic locks or proof of a dead worker. This first version does not support concurrent tracker writers: use an authoritative tracker with atomic claims before enabling that pattern.

Before acting on `next`, inspect the current plan and actual workspace, confirm authority, and recheck ownership. Record owner/running status, perform one acceptance slice, save evidence, and continue. On resume, inspect waiting records and continue your own running task after verifying partial changes; `next` never acquires or reoffers claims. Other chats must not adopt the same task merely because `next` listed it earlier. Recover another owner's running task only after confirming that owner is no longer working and verifying partial changes; preserve its history and source link.

When recovering checkpointed work or resolving shared-work ownership, scan sibling sessions and inspect relevant candidates. In-scope, unowned work can continue under the already authorized objective. Unrelated objectives, unknown ownership, missing authority, and explicit exclusions remain linked candidates; discovery does not grant execution permission. No goal creation, external scheduling, agent launch, or automatic deletion is implied.

When nothing is ready, inspect waiting reasons and plan coverage. Recheck relevant external conditions without changing policy to force progress; continue independent safe work. Finish only when task records, acceptance checks, delivery readback, and the entire authorized goal agree. Native runtime tools own budget limits, turn continuation, pause, and blocked-goal status.
