# Coordinated parent delivery

Read before implementation when the selected path coordinates separately assigned slices into one parent outcome. This is a stricter Deep Loop path, adapted from Wayfinder Delivery. The ordinary PLAN → BUILD → REVIEW/FIX → SHIP phases and existing checkpoint schema remain authoritative for overall completion.

## Parent contract and coverage

Reuse the existing parent contract, map, specifications, approvals, and release procedure. Link them from `plan.md`. Record the included requirements, exclusions, repositories/environments, authority source, execution controller/configuration and attributable run-state readback, acceptance gates, evidence locations, and recovery procedure. An unsigned template, agent-generated contract, or ticket cannot authorize itself. Governing standing authority applies without manufacturing a new scoped exception.

Inventory all required behaviors, screens, states, responsive variants, journeys, and dependencies. Map each requirement to its assigned slice, approved reference where applicable, required checks/review, and current evidence. Keep details in their existing authority. Missing fields block dependent work while safe discovery may continue. Do not select unrelated backlog work or reduce parent scope to manufacture completion.

Use [decision mapping](decision-mapping.md) for unresolved questions. Implementation slices must be independently verifiable and distinguished from decisions. Closing an excluded dependency requires re-evaluating still-required behavior and edges.

## Experience approval

For UI work, read [delivery design](delivery-design.md) before mockups/prototypes. Explore alternatives, present a coherent mockup batch for explicit human approval, then build and obtain approval of an isolated interactive prototype. Reuse valid existing approvals and covered patterns. Backend-only work needs no visual gate.

Bind approval to exact artifact revision/hashes, screen/state/viewport/journey coverage, and permitted adaptations. Appearance or behavior outside that coverage returns to the relevant gate. Do not infer approval from silence or approve for the user. Construct approval artifacts before asking; ask one exact approval question and end the turn. Refresh approval evidence on resumption.

Product Design can own exploration under [UI/UX integration](ui-ux-integration.md); it does not replace this path's required approval and verification evidence. Reuse equivalent approved artifacts rather than duplicate design workflows. Do not automatically invoke upstream user-only orchestrators.

## Executable acceptance before implementation

Read [delivery verifiers](delivery-verifiers.md) before establishing acceptance. For each required criterion, define the independent expected result, actual command/tool, controlled inputs/environment, threshold or invariant, and evidence bindings. Select by scope and risk; unit tests alone cannot cover visual, behavioral, performance, security, or release requirements.

Run baseline checks before implementation. Missing required capability is BLOCKED. Reuse existing checks and verifier catalog; add only a demonstrated missing adapter under existing source authority. Prove a new/changed verifier accepts a known-good fixture and rejects the intended defect in an isolated known-bad fixture.

Required image-driven fidelity uses approved-reference pixel comparisons at matched viewport/state, with important-region checks and expected/actual/diff artifacts. Run interactions independently. Never relax thresholds, mask defects, or generate expected results from the candidate to turn a failure into a pass.

## Discover and verify host coordination

This package supplies instructions and evidence schemas, not a scheduler, lease service, verifier engine, or release runner. Discover actual worker/reviewer facilities, claims, artifact store, gate reader, and release lane. Do not install infrastructure or change runtime settings merely to satisfy this path.

Describe this path as operational only after verifying those host capabilities for the selected task. Instructions and available subagent tools alone do not prove controller enforcement. An ordinary single-writer task can use the defined-task path from intake; a parent already requiring coordinated delivery retains its blocked requirements.

The host controller enforces assignment, configured writer concurrency, verifier/repair/no-progress/resource limits, persisted run state, and integration/release exclusivity. Record controller identity, configuration revision/source, and attributable run/state readback. Limits do not grant authority. Do not invent numeric defaults or manually count, reconstruct, reset, or extend cross-session counters. Missing enforcement/readback blocks dependent assignments/retries/releases; safe discovery can continue. Do not downgrade the path to evade this requirement.

The coordinator selects eligible work. Workers receive bounded assignments and cannot select further backlog work. Only the coordinator updates parent Deep Loop checkpoints; tickets remain authoritative for child state.

Before writes, verify existing claims, sessions/processes, branch/worktree/PR activity, and ownership. A claim binds parent/ticket, owner/session, branch/worktree/PR, paths/risk zones, acquisition/expiry, heartbeat, and predecessor evidence. Expiry alone is not authority to reclaim. Recheck ownership before edits, Git/tracker mutations, and child completion.

Require verified exclusive single-writer ownership or actual atomic leases plus disjoint paths/risk zones for concurrent writers. Uncertain or overlapping writes block concurrent execution. Use supported worktrees when appropriate; preserve existing dirty work and recovery points. No new dispatcher is required for a small pilot.

Use a separate read-only review context for the exact diff, specification, and standards. Findings return to the assigned writer. Required independent review is BLOCKED when the host cannot provide it; self-review cannot be relabeled independent. Optional implementation skills may own dispatch under [Matt Pocock integration](mattpocock-integration.md), but do not replace this path's verified controller requirements.

## BUILD and REVIEW/FIX

Refresh live parent/dependencies, approvals, claims, source, CI, and release state before choosing work. Select the smallest authorized action advancing a required criterion or resolving an evidenced blocker. For a defect, reproduce the exact symptom and test a falsifiable cause.

Run affected verifiers; record baseline, previous/current measurement, target, status, commands/results, and artifact pointers against exact source/build, reference, verifier, and environment identities. On failure, diagnose from the last failure, repair, and rerun affected checks within host-enforced limits. On pass, obtain independent review of the exact diff, resolve findings, and rerun affected checks. All hard gates remain independent.

Persist evidence and reconcile coverage/dependencies after each meaningful unit or handoff. An empty frontier requires examining cycles, uncovered states, human waits, and ownership conflicts. A finished child is not a finished parent. Continue independent eligible work while a clarification is pending through a supported asynchronous question tool. Required design approval and protected-action questions follow their governing stop/end-turn rule; pending answers never authorize dependent work.

## Integrated SHIP and parent completion

Use the host-designated integration/release lane; workers do not merge/promote/deploy independently. Verify lane ownership and authority, review the exact combined change, and run full required gates on the release candidate. Reconcile post-merge CI and build identity before release.

Follow the existing permitted release process. Verify delivered artifact identity, required live journeys/probes, health, freshness, and recovery readiness. Failed live verification retains the failure evidence and uses only the compatible authorized repair/rollback procedure. Code rollback does not imply data/schema reversal; never retry production blindly.

Checkpoint pointers include contract/approval revisions, source/build/branch/worktree/PR, claims, verifier/review artifacts, controller/configuration/run state, active processes requiring reconciliation, unresolved blockers, and next safe action. Follow governing vault persistence rules where applicable; no competing issue database or secrets. Required failed persistence blocks dependent completion/release and retains a recoverable payload.

When the requested output is only a discovery packet or checkpoint, verify and report that local artifact separately from the parent delivery. Its acceptance can pass while parent requirements remain pending; retain the incomplete parent checkpoint. Do not frame unavailable production evidence as an attempted release or failure to deliver the authorized local artifact. Record only execution details needed for the selected path and next safe action.

Create named parent checks in `state.json.checks` for coverage, applicable approvals, independent review, integrated acceptance, controller/ownership evidence, delivery identity/live behavior, and required cleanup/persistence. Those checks link actual detailed evidence; the helper validates recorded fields only. Missing required evidence remains pending/failed with a blocker, not not-applicable. Keep complete false while design, capability, runtime-limit, or release evidence is missing.

Only the coordinator declares COMPLETE after every included requirement is accounted for, required approvals remain valid, checks/reviews pass on the delivered artifact, independent endpoint readback meets acceptance, and required cleanup/persistence is verified. Report the actual wait/blocker/limit condition and next authorized action otherwise. No background continuation is promised without a verified authorized host runner.
