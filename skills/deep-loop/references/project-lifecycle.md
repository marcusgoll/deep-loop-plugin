# Project lifecycle

Use for full-project planning/delivery, specialist handoffs, dogfooding, or release maintenance. Keep Deep Loop's PLAN → BUILD → REVIEW/FIX → SHIP phases. This reference adds routing and acceptance guidance, not a mandatory ceremony for every task.

## Roadmap and decisions — PLAN

Reuse the project's roadmap and decision records. For a full project, connect each milestone to a usable outcome, dependencies, acceptance evidence, and material risks/recovery. Account for the requested scope; keep uncertain later milestones coarse until prerequisites settle. Separate unresolved decisions from implementation tickets. Planning-only work ends with the verified planning handoff.

Use [decision mapping](decision-mapping.md) for multi-session uncertainty. Link evidence and decisions once from plan.md; do not maintain another backlog or copy tracker status into checkpoints.

Select specialists by the question being resolved, reading their current installed instructions before use:

| Need | Owner and return |
| --- | --- |
| Consequential system choice | `deep-architect`: compare materially different approaches against actual constraints; return the recommendation, tradeoffs, and decisions to validate. |
| Module interface or testing seam | `codebase-design`: use the project's domain vocabulary, existing interfaces, depth, and locality; return caller contracts and realistic test surfaces. |
| Demonstrated friction in existing code | User-selected `improve-codebase-architecture`: return evidenced candidates; follow its candidate-selection workflow before refactoring. Skip speculative scans for a new project. |
| User journeys, screens, visual direction, accessibility | Follow [UI/UX integration](ui-ux-integration.md); return covered screens/states/viewports, selected artifacts, and interaction evidence. Preserve applicable design approvals. |

Evaluate UX, DX, and AX alongside accessibility requirements. Frontend, backend, and persistence choices support the same user journeys and contracts. Prefer the simplest approach that meets acceptance; record material tradeoffs and what evidence would justify revisiting them.

## Specification → tickets → implementation

Retain or create the local behavior record under the entrypoint's readiness rules, linking any Build Contract and its proof. This requires no duplicate spec, published issue, or ticket graph.

Use [Matt Pocock integration](mattpocock-integration.md) for invocation rules, setup, ownership, concurrency, and returned evidence. One selected implementation controller owns execution; Deep Loop owns overall acceptance/delivery. Coordinated assignments retain [coordinated delivery](coordinated-delivery.md), including verified host capabilities and independent review.

- User-selected `to-spec` synthesizes settled requirements and repository evidence; it does not replace intake. Resolve material unknowns first and preserve its testing-seam confirmation. An existing authoritative spec needs no regeneration.
- User-selected `to-tickets` turns the spec into independently verifiable vertical slices with genuine blockers. Preserve its breakdown approval and configured tracker conventions. A slice includes the frontend, backend, persistence, and checks needed for its behavior, where applicable.
- User-selected `implement-spec` executes the dependency-ready frontier and integrates per-ticket worktrees on one integration branch. Follow its worker/review workflow and the integration contract; ticket completion alone does not prove the parent outcome.

For a large roadmap, prefer cohesive milestone specs over one detailed speculative project spec. Reuse existing records. Naming Deep Loop alone does not invoke user-only specialists or authorize tracker publication, worker launches, or deployment beyond the task's governing authority.

## Evidence-driven repair — BUILD and REVIEW/FIX

For hard bugs or performance regressions, use `diagnosing-bugs`: establish an executed check that catches the exact symptom, reproduce/minimise, test falsifiable hypotheses, fix the cause, and verify the original scenario plus the regression check. Follow its current instructions rather than duplicating its diagnosis procedure here.

Repair the authority that evidence proves wrong:

| Finding | Repair target |
| --- | --- |
| Implementation violates the agreed contract | Code and a regression check at the seam that exercises the real failure. |
| Intended behavior is ambiguous or incorrectly specified | Resolve the decision; amend the existing spec and affected acceptance criteria. |
| Missing behavior or incorrect blocking relationships | Amend/split affected tickets and recompute the ready frontier. |
| Architecture prevents realistic testing or meets constraints poorly | Reopen the affected interface/architecture decision with evidence; use the appropriate specialist above. |
| Verifier misses the actual defect | Repair the verifier and invalidate evidence that relied on it. |

Preserve the reason for revisions. Pause only dependent work, refresh affected handoffs, and reset affected task/check/delivery evidence before continuing. Do not weaken acceptance to manufacture a pass. Changed scope or intended behavior needs resolution under existing authority; ordinary defects remain in REVIEW/FIX. New spec/ticket publication follows the selected specialist's invocation and approval rules.

## Dogfood — REVIEW/FIX

For user-facing product delivery, exercise the changed core journeys through the running product with realistic, safe test data. Reuse existing browser/testing facilities. Cover relevant onboarding, responsive and keyboard behavior, loading/empty/error states, and recovery; select coverage from acceptance rather than inventing a universal checklist. Do not trigger real payments, messages, destructive actions, or other protected effects merely to test a journey.

Record the artifact revision/environment, journey/input, expected and observed behavior, and evidence in the existing checks or linked report. Screenshots prove visible state; exercised interactions prove behavior. Automated checks and dogfooding complement each other. Required unavailable access remains a blocker; backend-only or planning-only work needs no invented UI dogfood gate.

Route defects through diagnosis and usability/requirement findings through their affected design/spec/tickets. Resolve required findings and rerun affected journeys before delivery. Unrelated opportunities remain out-of-scope findings.

## Release maintenance and deployment — SHIP

When verified development work needs branch integration or closeout, use `finishing-a-development-branch`. Read its installed entrypoint and workflow reference; pass the agreed endpoint, integration owner, branch/worktree identity, verification evidence, authority, and commit disposition. Reuse a finishing pass already owned by the selected implementation controller. Follow the authorized PR/merge/keep outcome without reopening settled choices; preserve its exact typed `discard` confirmation and the repository's Ponytail review/commit/push gates. A task branch needs an explicit verified disposition before parent completion. Keeping it local is valid only when the user selected that endpoint; absence of a remote or a statement that CI will run after a future push is a blocker or next action, not a completed disposition. Local-only or non-Git artifacts need no branch-finishing workflow.

The finishing skill owns only branch integration and safe closeout within this handoff. Its terminal result or `next-action-options` reconciliation returns branch/PR/merge identity, checks, preserved worktrees, cleanup disposition, and blockers to Deep Loop. Do not mark the parent native goal complete from this child stage. Deep Loop retains parent completion and continues any required release preparation, deployment, and independent endpoint verification; PR creation is sufficient only when it satisfies the agreed endpoint. Preserve any worktree still needed for active workers, feedback, remaining delivery, or recovery.

### Recoverable post-ship closeout

After independently verified shipment, apply the selected cleanup or retention disposition within authority. Retaining a locally excluded checkpoint is valid when no retirement is needed; record it without a separate retention check. For actual retirement, perform the recoverable closeout below. An open PR, green CI, or merge alone is insufficient for a deployment endpoint. First verify task ownership, exact checkout/ref identities, intended base/PR, and no remaining worker, process, feedback, release, or recovery use. Preserve active, dirty, primary, locked, shared, protected, unmerged, or uncertain targets and record their disposition. Stop on drift; no force worktree removal or automatic archive expiry.

Use an existing host-local archive location outside the entire checkout/repository, such as `$CODEX_HOME/archives/deep-loop/<repository>/<session>`. Quiesce the selected checkpoint under one coordinator; set `active: false` only after actual writers stop, retaining `complete: false` and SHIP. Product acceptance and delivery must already pass; explicit closeout-stage proof remains pending until the selected retirement is actually observed. Run the existing helper with `--root <checkout>` before each command:

```text
preserve --session <session8> --destination <external-archive> --include <required-evidence>
verify-archive --archive <external-archive>
retire-checkpoint --archive <external-archive>
```

Repeat `--include` for required ignored/generated evidence outside the checkpoint. Use absolute archive/evidence paths; relative path arguments resolve from the caller working directory. The bound Verification Contract is included automatically. The helper snapshots the exact folder, verifies copied hashes, and, in Git, creates a self-contained HEAD bundle and fetches it into an empty repository to prove recovery. Run preservation while HEAD is the source tip to be retired, or preserve that exact source history separately and prove its restore. Record source/base refs and tips, PR merge mapping (including source SHA), ownership and restore commands in existing evidence. The helper never authenticates shipment or authorizes branch deletion. Retire only the selected unchanged checkpoint and its matching pointer before removing a checkout; another session/pointer survives. The lock coordinates helper pointer writers, not arbitrary external writes: coordinator quiescence remains required. A partial archive refuses retirement; preserve it for diagnosis and use a fresh destination after inspection, never overwrite it.

When only the completed checkpoint is being retired in a shared checkout, use `preserve --checkpoint-only`. This leaves unrelated dirty work intact and archives no Git history; it supplies no proof for branch/worktree retirement. Preserve the exact source tip separately before any later branch retirement. The external archive location and checkpoint/evidence checks still apply.

Then execute the existing finishing mechanics from outside the selected checkout. For Codex-managed worktrees, use `list_artifacts` and `archive_worktree` with the exact attachment identity, preserving needed ignored files externally first; retain its returned snapshot/restore locator. Preserve primary, pinned, shared, or unsupported managed targets. For ordinary owned worktrees, recheck registration, inactivity, clean tracked/untracked state, ignored-evidence disposition, and locks, then use normal `git worktree remove` without force. A directory's location is never ownership proof.

Retire a task source branch only after no worktree uses it and its exact tip is preserved and restore-tested. Verify ancestry into the intended base, or for squash/rebase verify the merged PR's repository, source/base identities and exact source SHA plus shipped readback. An ancestry failure alone is never permission to force-delete. From an unaffected checkout, use `git update-ref -d refs/heads/<task> <preserved-tip>` for atomic expected-tip local retirement; archive and disposition any task-owned branch configuration separately. For an authorized remote retirement, read the actual remote tip, preserve its exact history, verify the same merged identity, and use an explicit lease: `git push --force-with-lease=refs/heads/<task>:<verified-tip> <remote> :refs/heads/<task>`. A refused lease preserves the newer ref. Never retire base/default/protected refs. Read back local and actual remote refs and worktree registration after each selected action.

Save the observed cleanup/retention results and recovery locators in one existing task evidence file, then:

```text
finalize-archive --archive <external-archive> --evidence <saved-readback>
verify-archive --archive <external-archive>
validate --path <external-archive>/checkpoint --stage ship
```

The archive retains an immutable original snapshot and a working checkpoint with a pending Post-ship closeout check staged `closeout`. Finalization records supplied readback and makes the working checkpoint COMPLETE only when SHIP validation passes; final hashes detect later evidence/state corruption. The agent must inspect live cleanup facts independently. Repeats accept identical inputs and refuse drift. Resume an interrupted final receipt with the same evidence. Retain archives until the user explicitly requests pruning. For a local non-Git artifact, apply checkpoint preservation when selected; skip branch/worktree mechanics. Report preserved uncertain targets and blockers honestly before completing the parent goal.

Update affected usage, configuration, interface, and operational docs alongside implementation. At release preparation, reconcile them with the combined delivered change. Follow repository conventions for version classification, manifests, changelog, migration guidance, tags, release notes, and packages. Reuse automation; do not duplicate generated release artifacts or bump versions twice. Create only artifacts required by the change and endpoint.

Deployment applies only when the agreed endpoint requires it. Use the project's existing release lane and applicable deployment specialist. Verify the target/current state, required configuration and migration implications, recovery point, and rollback procedure before mutation. Code rollback does not prove data/schema rollback. Preserve repository review/commit gates and irreversible publication boundaries.

After delivery, independently verify artifact/version identity, health, and required live journeys at the actual endpoint. For hosted CI, inspect the actual run and bind its provider, URL, successful conclusion, and tested revision to the delivered revision. Static workflow configuration proves only that a check is wired; queued, expected, or future runs do not pass the gate. A successful workflow or published tag alone is insufficient for a live deployment endpoint. Failed acceptance retains evidence and returns to repair or compatible rollback; unavailable required readback blocks completion.

Record applicable dogfood, documentation/release maintenance, and endpoint checks in existing state.json.checks with evidence or a scope-specific not-applicable reason. Reconcile ticket/milestone status only within the selected tracker's closing rules; `to-tickets` does not modify its parent issue. Report the actual endpoint, including merged/release-skipped for docs-only work when repository policy allows it. Return to Deep Loop SHIP validation; this reference adds no separate completion state or release engine.

For registered UI and bound deterministic proof, preservation retains the original approved file bytes and logical paths, then records an integrity-bound resolution map to archive-relative copies of every dependency actually read by validation. Archived reads use those copies without falling back to original files. Verification rechecks bound acceptance before retirement or finalization; missing, changed, escaping or unsupported dependencies block closeout. Moving an intact archive changes its physical location, not its approved identities. This verifies retained acceptance evidence rather than executing a new verifier or proving live delivery. Keep originals until preservation and recovery checks pass.

Preservation supports proof already produced at the delivery gate. If a bound deterministic closeout check still needs a future receipt, preservation refuses before changing source or creating an archive: its future files are not part of the immutable resolution map. Keep the live checkpoint for that workflow. Genuine human cleanup/readback judgments may remain explicitly manual; never relabel a deterministic requirement to bypass missing proof.
