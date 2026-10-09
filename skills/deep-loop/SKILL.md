---
name: deep-loop
description: Use when intent needs clarification, decisions span sessions, or development needs resumable delivery or coordinated parent acceptance.
metadata:
  skill_version: "0.5.9"
---

# Deep Loop

Own the task from agreed acceptance to verified delivery. Keep one workflow; use specialist skills for work that needs them. The helper stores checkpoints and validates their recorded fields. The agent performs the work and checks that the cited evidence is true and current.

Keep the workflow proportional to the work. Save checkpoints when interruption or handoff makes them useful. After compaction, recover from those records and verify current state before continuing; use the same recovery discipline after every subsequent compaction.

## Start within the user's authority

Briefly state the intended outcome, then begin clear authorized work. Recover scope and authority from the request and existing decisions; use the current plan or checkpoint when needed. On resume, reuse that authority while the scope is unchanged. Investigate discoverable facts yourself, and ask only about unresolved choices that materially change the outcome, scope, acceptance, or approach. Pause dependent work while a required answer is pending; continue independent work within scope. A changed outcome requires resolving its scope and authority before acting. Existing design approvals, irreversible-action boundaries, and repository review gates still apply.

Use the host's available question tool within its runtime restrictions; `request_user_input_async` supports clarification in Codex. If no suitable tool is available, ask in chat. Recommendations, preselected options, silence, and timeouts are not user answers. Group independent questions with useful choices and tradeoffs; defer dependent questions until their prerequisites are settled.

For source navigation, use the supplied skill path or current catalog first. Discover exact paths once, then reuse them. Read required files completely in bounded chunks; do not combine large files or raw logs into truncated output. Summarize check results and retain full logs in task scratch. For another chat's progress, prefer compact status/wait tools and cursors; retrieve detailed history only for a specific evidence gap.

For installed skill source reads, use `skill-optimization/scripts/update_package.py read` with contiguous offsets and the returned hash; its output bound and drift rejection protect retrieval. Before composing thread-tool calls, read [safe thread calls](references/thread-tools.md) for argument bounds and error decoding. Local guards supplement the runtime's schema; platform-owned schema gaps remain explicit.

## Weigh UX, DX, and AX

When an approach has a material tradeoff, use the relevant dimensions:

- **UX:** Is it easy for users to use?
- **DX:** Is it easy for developers to change later?
- **AX:** Can the next agent understand the records, verify the state, and keep going?

AX means agent experience. Accessibility has its own applicable acceptance checks; do not treat AX as accessibility coverage.

Choose the simplest approach that meets acceptance. Record consequential choices and their reasons in the existing plan or decision record; omit dimensions that do not affect the decision.

Stay within the authorized task. Preserve working behavior and supported contracts; inspect the affected flow, retain recovery points, and run checks appropriate to the change. Do not bundle unrelated fixes, cleanup, or refactoring. Record discovered out-of-scope problems as findings without acting on them.

## Establish intent before implementation

A clear authorized task proceeds directly to PLAN; an existing agreed brief needs no repeated interview. Before implementation or native-goal creation, settle the delivery endpoint from attributable user, repository, or contract authority. A request to "create a goal and implement" authorizes goal-backed execution but does not by itself choose between a local commit, pull request, merge, release, or deployment. Do not narrow the endpoint by writing exclusions into a self-authored goal. If the endpoint cannot be recovered, ask the smallest endpoint question and continue only independent preparation while it is pending. For other unresolved intent, recover why the outcome matters and use the decision tree below.

For unclear intent, use this adaptation of `grilling`:

- Treat the open choices as a decision tree. The question frontier contains choices whose prerequisites are settled. Ask independent frontier questions together; defer a dependent question until its prerequisite answer arrives.
- Give each question a short number/title, useful choices, and a recommended answer with its main tradeoff. Use the question-tool rules above. Recommendations are proposals, not user answers.
- Research filesystem, tools, architecture, and other discoverable facts rather than asking the user to find them. Delegate fact-finding only when available and authorized; continue independent research while human choices wait.
- After each answer round, recap settled decisions and remaining unknowns, then recompute the frontier. Challenge contradictions or unsupported assumptions that affect the outcome. Record answers and evidence in the existing plan or decision map.
- Once the material branches are resolved, recap the agreed outcome, constraints, exclusions, and endpoint, then continue within the existing authority. Record explicitly delegated choices and attributable user answers in the current plan or decision map. An unanswered required question remains open and blocks only dependent work.

Example: for "make notifications less distracting," first settle which interruptions matter and which channels are acceptable. Ask about email batching only after email is selected; inspect current notification settings yourself.

This is native Deep Loop intake, not an automatic invocation of standalone Grilling. Explicitly requested `$grilling` follows its own full interview and confirmation contract. Use decision mapping below when the unresolved tree needs durable records across sessions. Planning-only requests end with the verified plan/handoff. Published specs/tickets and user-only specialist workflows retain their selection and authority requirements; local behavior recording follows PLAN below.

## Establish readiness to build

Carry the agreed outcome and authoritative brief/spec or Build Contract into PLAN. Reuse settled behavior and decisions; a supplied Build Contract is acceptance input, not a reason to repeat intake. Resolve discoverable facts by inspecting the affected flow, and resolve remaining material choices with the user. Start with the smallest useful end-to-end slice and its acceptance check. Add an ordered implementation plan only when dependencies, migration or rollout order, shared ownership, repository governance, or the user's request makes sequencing material; link each planned slice to its dependency, affected interface, and proof.

For installed skill revisions, read `writing-skills` and `skill-optimization` before the first edit and begin the latter's guarded candidate packet. Its updater owns preservation, drift checks and apply; edit and verify the candidate before installation.

For a supplied Build Contract, acceptance spanning multiple requirements, quantitative thresholds, invariants, missing proof, or a requested contract, read [Verification Contract integration](references/verification-contract-integration.md) during PLAN. It connects technical acceptance to proof and delivery evidence; small settled tasks keep the direct acceptance-to-check path.

When work introduces or materially changes a module, interface, dependency seam, or adapter, spreads a domain rule across callers, or requires proof past the current interface, read [Codebase architecture integration](references/codebase-architecture-integration.md) during PLAN and verification design. Apply Codebase Design locally; keep architecture surveys and consequential alternative-interface exploration deliberate and selected. Small settled tasks continue directly.

When substantial behavior must survive sessions or an implementation handoff, retain it in the existing project authority. If no brief/spec or Build Contract adequately records the agreed behavior, save a compact local spec with scope, constraints, decisions, and observable outcomes in the project's existing artifact location. Record settled decisions; keep unresolved choices visible. A bounded Build Contract can itself carry the behavior, and small work can stay in task context. Local recording does not invoke To Spec or publish an issue.

When checkpointing, `plan.md` indexes those authorities, proof, owner, endpoint/readback, recovery, and next actions. Combine behavior, acceptance, and proof where their existing format and authority permit; create a separate artifact only for information the current records cannot carry. Link settled content rather than copying it. Reopen affected decisions when implementation evidence changes intent or acceptance, and continue independent work.

## Choose the work needed

Use the smallest path that meets the requested outcome; record it in `plan.md` when using checkpoints.

- **Defined task:** use the build/review/delivery path below. A small feature or UI edit needs no tracker map, separate design ceremony, or multi-worker controller.
- **Unclear destination or major decisions spanning sessions:** read [decision mapping](references/decision-mapping.md) during PLAN. Resolve uncertainty on one shared map, then return here for delivery. If the requested endpoint is planning only, independently inspect the completed decisions/handoff and stop there; do not start implementation.
- **Coordinated parent delivery:** when explicitly requested, or when a parent needs separately assigned implementation slices and combined acceptance/release, read [coordinated delivery](references/coordinated-delivery.md) before assignments or implementation. It adds coverage, design approvals where applicable, executable baselines, independent review, and verified host coordination. Complexity within a single assigned task alone does not require this path.

Decision mapping can feed either delivery path. One coordinator owns the parent outcome. Use an existing map or contract rather than create a competing record. The local checkpoint links tracker detail and external evidence; it does not duplicate ticket state.

Follow governing instructions and existing scope/authority; this skill grants no permission. The current shared router supersedes historical blanket approval language. Preserve specific design approvals, irreversible-action boundaries, commit/review gates, and recovery requirements. Read [merge provenance](references/merge-provenance.md) only when tracing these adaptations.

Before delegating work, read [worker selection, models and concurrency](references/mattpocock-integration.md#worker-selection-models-and-concurrency). Inspect the requested guarantees and current ownership, isolation, review and applicable controller capabilities; state the supported path before dispatch. Workers inherit by default; justified supported exceptions preserve user choices. Unavailable required guarantees block dependent dispatch, and a narrower path requires user selection. Trivial work stays direct. This shared section applies without selecting Matt's user-only workflows; selected workflows retain their full execution ownership and handoff contract.

For eligible low-risk intake with multiple plausible installed profiles, or repair after a concrete failed objective check, follow the governing JEV policy and read the installed `jev-codex-routing` skill. Directly named skills/user overrides, protected or uncertain work bypass JEV. Its sanitized profile selection stays advisory with `applied=false`; it grants no execution or model-selection authority. Follow its existing repair limits and continue the ordinary authorized path on abstention or unavailability; passing checks need no routing call.

For a net-new user-facing screen or flow without an approved visual target, and for UI/UX design exploration, audits, source matching, or Mobbin reference research, read [ui-ux-integration.md](references/ui-ux-integration.md) before design or implementation. It defines the greenfield design gate, Product Design ownership, reference provenance, and rendered acceptance evidence.

For a full project roadmap, architecture/specification handoffs, realistic product dogfooding, branch integration/closeout, or release maintenance, read [project lifecycle](references/project-lifecycle.md). Apply only the parts needed by the requested endpoint; small tasks retain the direct path. It connects the existing phases and specialist contracts without adding a controller or checkpoint schema.

For creating, testing, or distributing an installable iOS app, read [iOS delivery](references/ios-delivery.md). Declare native device/OS/build coverage from project requirements for substantial work, retain each required case as passed, failed or not run, and verify the actual endpoint. Browser prototypes do not establish native proof; this adds no build service or distribution authority.

For explicitly requested native goals, substantial implementation, work likely to span sessions, or coordinated delivery where runtime continuation would help, read [native goals](references/native-goals.md) before offering, creating, resuming, or updating a goal. Small fixes, explanations, and planning-only work need no goal recommendation.

## Start or resume

For a small task, keep one build/review path. Use recorded checkpoints when interruption, multiple components, or delivery steps make them useful.

When multiple sessions or maps share a project, read [multiple sessions and maps](references/local-tracker.md#multiple-sessions-and-maps). Keep one canonical decision map per distinct outcome, link bounded sessions to it, and use explicit session locators during concurrent work. Discovery alone does not authorize reconciliation, takeover, or cleanup.

Treat `$deep-loop continue` (or resume) as a request to continue the current authorized objective, not to start another session or select new backlog work. Resolve the task from the current chat or an explicit project/checkpoint pointer, then inspect `.deep-current.json` and the matching plan/state when present. A pointer or newest timestamp alone does not establish scope or ownership. If several candidates remain equally plausible, ask which task; if the task locator is missing, ask for it rather than searching unrelated projects.

Re-read governing instructions and the relevant skill/reference guidance after compaction or a handoff. Recover scope, endpoint, decisions, unresolved questions, ownership, blockers, and the next action from the saved authority; inspect actual code/branch/worktree, worker status, and applicable tracker/delivery state. Recheck changed or stale evidence, then continue the next safe in-scope action without repeating settled intake. Recheck blockers rather than assuming they persist or have cleared. Continue does not answer a pending question, grant approval, reclaim another worker's task, or expand a completed objective. If the objective is complete, report its verified endpoint and ask for direction before selecting more work.

When a known writer owns the target, wait for its compact status to show it inactive, then recheck exact source preimages before applying the bounded delta. Inspection and waiting do not require messaging the writer. Request messaging authority only when a message is necessary; do not make unnecessary messaging a prerequisite for delivery. Unknown ownership, changed preimages, lock refusal, or preservation failure still stops dependent work.

Save checkpoint updates after meaningful decisions, completed slices, failures, and before handoff or a known interruption. Keep the checkpoint locator in the handoff/retained summary. This is agent-owned persistence, not an automatic compaction hook. When active work must be inspected outside its original workspace, use the [active handoff packet](references/checkpoint-operations.md#recoverable-active-handoff) to retain explicitly selected references without retirement or transferred authority. For a small task without a saved checkpoint, recover from retained task context and live readback; if that cannot establish scope or the next action, ask rather than guess.

Before creating, recovering, filling, or validating checkpoints, read [checkpoint operations](references/checkpoint-operations.md). It owns initialization, sibling discovery, state/schema selection, and helper limits. For a selected checkpoint’s current evidence and blockers, use its [read-only recovery report](references/checkpoint-operations.md#read-only-recovery-report); confirm scope and actual ownership before taking the proposed action.

For dependent implementation slices, recurring issues, or tracked work that may be interrupted, read [tracked tasks](references/checkpoint-operations.md#local-tasks-and-goal-continuation). Keep externally owned ticket state at its source; the checkpoint records bounded execution and links its authority.

## Work to acceptance

**PLAN:** Establish readiness using the guidance above. Reuse the agreed acceptance criteria and proof design, filling only missing requirements. Name the delivery endpoint (local artifact, PR, release, or live deployment), its attributable authority, and independent readback. Map required verifiers to `state.json.checks` as `pending` when checkpointing; otherwise retain checks in task context. Include cleanup or security checks required by the actual scope or repository. Begin the smallest useful slice once its prerequisites are resolved.

Checks and tasks default to `stage: review`; use `ship` for delivery proof and `closeout` only for actual post-delivery retirement. REVIEW requires its due acceptance; final SHIP requires every stage. Pending implementation acceptance does not block BUILD once prerequisites and applicable design authority are settled. Archive preservation requires review and delivery proof before it defers explicit closeout records to the preserved working checkpoint.

For substantive UI, register the actual scope with `--ui-request` and select exploration and proof from approved acceptance through the [UI adapter](references/ui-ux-integration.md). Reuse clear targets and established patterns; unresolved material direction needs owner selection from meaningful alternatives. Exact-target fidelity retains the approved Design Contract and its current execution, capture and case evidence at REVIEW and SHIP. Established-component behavioral changes use risk-based rendered, interaction, accessibility and responsive proof; no existing bound gate is waived.

New schema-4 checkpoints classify `uiRoute` as `not_applicable`, `specified`, or `greenfield`. Record the applicable evidence described in [UI/UX integration](references/ui-ux-integration.md), then run `validate --stage build` before source edits. The gate keeps non-UI work lightweight, accepts a precise approved target for specified edits, and requires Product Design, two or three meaningful options (three for broad exploration or a specialist requirement), explicit user selection, and Mobbin provenance or an evidenced no-comparable disposition for greenfield work. Existing schema-1/2/3 checkpoints retain their recorded contract.

For a coordinated parent, select checks from the complete coverage index and retain the added requirements through REVIEW and SHIP. A closed decision, finished child, or empty frontier does not complete the parent. Do not switch to the defined-task path to bypass a missing required capability or approval.

**BUILD:** Implement the slice, validate it, then expand. Keep unresolved failures with evidence and the next safe action in the current task record, or `state.json.issues` when checkpointing. When changes affect a passed check, set it back to `pending` and invalidate affected delivery evidence. Use specialist debugging, design, or review skills when their trigger applies.

**REVIEW/FIX:** Run the selected acceptance checks, inspect the result, and record evidence against the current work. Preserve each command's exit result before running another command. For a batch of native verifiers, use `scripts/deep_loop.py --root <project> run-checks --checks <checks.json> --output <new-results.json>` with a JSON list of `{ "name": "<check>", "argv": ["<executable>", "<argument>"] }`; it stops at the first failure and retains command output. To collect a finite batch of explicitly safe checks, add `--collect-independent` and declare each entry’s unique `id`, boolean `safe`, and `dependsOn` ID list. Read [checkpoint operations](references/checkpoint-operations.md#collect-safe-independent-checks) for required-check and skip rules before selecting this mode. Run shell-specific checks separately and inspect their exit codes; explicit shell chains still require their own failure handling. The runner does not mark checkpoint checks or interpret suite reports.

For substantial, risky, resumed, delegated, or external-delivery work, bind deterministic proof to its approved invocation, current source/environment and declared artifacts using [Verification Contract integration](references/verification-contract-integration.md). Keep human judgment explicit and independently inspect the result; a captured successful exit does not prove an undeclared outcome. Tiny reversible tasks may retain inspected direct proof.

Keep a failed broad suite recorded as failed, including a pre-existing failure. Record passing scoped acceptance separately with its actual coverage; link the baseline defect and disposition without relabeling the suite. An out-of-scope baseline finding is not a waiver for a required acceptance check. A check is `passed` with concrete evidence, or `not_applicable` with a reason tied to the scope. A hosted-CI check passes only from an observed successful run for the exact delivery revision, recorded with provider, run URL, revision, and conclusion; workflow files, job names, or statements that CI will run later prove wiring, not execution. Fix failed checks, then rerun affected checks. Record new debt only when it exists: pay it down in this task, or retain explicit user acceptance, an owner, and a paydown task. Do not convert unresolved failures into accepted debt.

Require a distinct read-only review context for agent rules/approval mechanisms, security-sensitive work, destructive migrations, and governing review obligations. For other substantial work, name the risk independent review addresses; small reversible work may use self-review and executed checks. Self-review is never independent, and required review unavailability remains a blocker. Reuse [worker review selection](references/mattpocock-integration.md#worker-selection-models-and-concurrency); review does not replace human approval or endpoint proof.

For checkpointed work, before moving to SHIP:

```powershell
py -3 "C:/Users/Marcus Gollahon/.codex/skills/deep-loop/scripts/deep_loop.py" validate --stage review
```

A failure keeps the task in REVIEW/FIX. Re-scope only when evidence shows the current scope or approach cannot meet acceptance within available authority or runtime limits. Runtime budgets and retry controls belong to the harness.

For small work without a checkpoint, run and inspect the applicable acceptance checks directly; no helper invocation or state file is required. The same failure, debt, and delivery requirements still apply. Add a checkpoint if the task grows or needs durable resume evidence.

## Ship and verify

**SHIP:** Follow the task's authority and repository delivery procedure, including required reviews and commit gates. Execute the delivery, then independently read back the named endpoint. Record what was observed and where; when checkpointing, set `delivery.status` to `verified` only when it meets acceptance. For Git task work, record a verified branch disposition: pull request, merged, or explicitly user-selected kept-local. For a non-Git or non-branch artifact, record why branch disposition is not applicable. A local commit is not a substitute for an agreed pull-request, merge, release, or deployment endpoint.

For an artifact-backed endpoint with declared structured readback, follow [Verification Contract integration](references/verification-contract-integration.md#bound-endpoint-readback). Execute a separate approved inspection of the saved delivered artifact, retain its bound observation, and compare its exact endpoint, target and revision at SHIP. Acceptance results alone cannot replace that readback.

For production work, verify the intended version and behavior at the live target. Tests, a merge, or a successful deployment job alone do not establish that result. For a local artifact, inspect or execute the saved artifact through its intended interface. If acceptance fails, preserve the failure evidence and repair or roll back within scope. An unavailable required readback is a blocker.

For checkpointed work, before declaring complete:

```powershell
py -3 "C:/Users/Marcus Gollahon/.codex/skills/deep-loop/scripts/deep_loop.py" validate --stage ship
```

Retaining a locally excluded checkpoint is a valid disposition when retirement is not needed; record it without adding a separate retention check. Actual retirement requires recoverable preservation and independent readback.

Only after this passes, the agent has checked the actual evidence, and selected closeout has a verified disposition, run `deep_loop.py complete`. It revalidates SHIP against one unchanged state preimage and atomically writes `phase: COMPLETE`, `complete: true`, and `active: false`; do not hand-edit those fields. For archived sessions, `finalize-archive` performs that final transition after supplied cleanup readback. Without a checkpoint, declare completion only after actual acceptance, independent endpoint readback, and selected cleanup pass; no checkpoint is needed solely for ceremony. Close out with the delivered result and evidence, plus any accepted debt or blocker. When blocked, retain the incomplete checkpoint or current task record, failure evidence, and next safe action.

After verified SHIP, offer a user-selected `retro` when the session shows repeated mistakes, costly navigation/tool use, or missing guardrails. Read [the retrospective handoff](references/mattpocock-integration.md#optional-retrospective) when selected. It produces evidence-linked improvement candidates; routine tasks can finish without it.

Finish with the delivered result, check outcome, and any material limitation or blocker. Explain a tradeoff only when it affects the result. Link existing detailed evidence when useful; follow the user's requested report depth.
