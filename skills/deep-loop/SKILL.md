---
name: deep-loop
description: Use when intent needs clarification, decisions span sessions, or development needs resumable delivery or coordinated parent acceptance.
metadata:
  skill_version: "0.6.1"
---


# Deep Loop

- Own agreed acceptance through verified delivery in one proportional workflow; use specialists when needed. The helper stores checkpoints and validates fields; the agent performs work and verifies actual, current evidence.
- Save checkpoints when interruption or handoff warrants them; after every compaction, recover records and verify current state.

## Start within the user's authority

- State the outcome and start authorized work. Recover scope/authority from the request, settled decisions, plan or checkpoint; reuse it on resume while scope remains unchanged. Investigate facts; ask only about material unresolved outcome, scope, acceptance or approach choices. Pending required answers block dependent work only. Resolve changed outcomes before acting; preserve design approvals, irreversible-action boundaries and repository gates.
- Use the host's question tool within runtime restrictions (`request_user_input_async` in Codex), or chat if unavailable. Recommendations, preselection, silence and timeouts are not answers. Except in Design Grill, group independent questions with choices/tradeoffs; defer dependent questions.
- Use supplied paths/current catalog; discover exact paths once and reuse them. Read required files fully in bounded chunks without truncated combined files/logs; retain full logs in task scratch and summarize results. Inspect other chats through compact status/wait tools and cursors; fetch history only for a specific evidence gap.
- Read installed skill sources with `skill-optimization/scripts/update_package.py read`, contiguous offsets and returned hash for bounded, drift-checked retrieval. Before thread-tool calls, read [safe thread calls](references/thread-tools.md); local guards supplement runtime schemas without closing platform-owned gaps.

## Weigh UX, DX, and AX

- For material tradeoffs, weigh relevant UX (user ease), DX (ease of future changes) and AX (agent ability to understand records, verify state and continue). AX means agent experience; accessibility requires its own checks. Choose the simplest approach meeting acceptance and record consequential choices/reasons in the existing plan or decision record.
- Preserve authorized scope, working behavior and supported contracts: inspect affected flows, retain recovery points and run appropriate checks. Record unrelated findings without bundling fixes, cleanup or refactors.

## Establish intent before implementation

- Clear authorized tasks go directly to PLAN without repeating agreed intake. Before implementation or native-goal creation, recover the delivery endpoint from attributable user, repository or contract authority. A goal/implementation request does not choose local commit, PR, merge, release or deployment; self-authored goal exclusions cannot choose it. If unresolved, ask the smallest endpoint question and continue independent preparation only; otherwise recover why the outcome matters and clarify remaining intent through the tree below.
- For unresolved visual, interaction, product, print or other design intent, use `design-grill` and read [Design Grill integration](references/design-grill-integration.md) before design questions or new creation. Its interview overrides grouped intake. Reuse approved briefs/locked decisions; sufficient approved targets need no new interview. Explicit `$design-grill` retains its full interview/approval contract.

For other unclear intent, adapt `grilling`:

- Map decisions/dependencies; ask independent frontier questions together, deferring dependent questions until prerequisites settle.
- Give each a short number/title, useful choices, recommendation and main tradeoff; follow question-tool rules without treating proposals as answers.
- Research discoverable facts; delegate only when available/authorized and continue independent research while awaiting choices.
- After answers, recap settled decisions/unknowns, challenge material contradictions or unsupported assumptions, record answers/evidence in the existing plan/map and recompute the frontier.
- When material branches settle, recap outcome, constraints, exclusions and endpoint; record delegated choices and attributable answers. Required unanswered questions block dependent work only.
- For "make notifications less distracting," inspect settings and use native intake: settle priorities/channels before email batching, only if email is selected.
- Native intake does not invoke standalone Grilling; explicit `$grilling` retains its full interview/confirmation contract. Use decision mapping for durable trees. Planning-only work ends with verified plan/handoff; published specs/tickets and user-only specialists retain their selection/authority gates. Local behavior recording follows PLAN.

## Establish readiness to build

- PLAN reuses agreed behavior, decisions and authoritative brief/spec or Build Contract; a supplied contract is acceptance input, not repeated intake. Inspect affected flows for facts and ask about material choices. Start the smallest end-to-end slice with its acceptance check. Add ordered slices only for material dependencies, migration/rollout order, shared ownership, governance or user request; link each to dependency, interface and proof.
- Before installed-skill edits, read `writing-skills` and `skill-optimization`, begin its guarded packet, then edit/verify the candidate; its updater owns preservation, drift checks and apply.
- When a portable outcome contract is needed and no adequate brief or Build Contract exists, read [outcome contracts](references/outcome-contract.md). This optional authoring format supplements existing acceptance, proof and delivery gates; small settled work keeps direct checks.
- During PLAN, read [Verification Contract integration](references/verification-contract-integration.md) for supplied Build Contracts, multiple requirements, quantitative thresholds, invariants, missing proof or requested contracts; otherwise use direct acceptance-to-check mapping.
- During PLAN/proof design, read [Codebase architecture integration](references/codebase-architecture-integration.md) for new/materially changed modules, interfaces, seams or adapters, domain rules spread across callers, or proof beyond current interfaces. Apply Codebase Design locally; surveys and consequential alternative-interface exploration require deliberate selection. Small settled tasks proceed directly.
- For behavior spanning sessions/handoffs, reuse project authority; if no adequate brief/spec or Build Contract exists, save compact scope, constraints, decisions, unresolved choices and observable outcomes in the existing artifact location. Small work may stay in context. Local recording neither invokes To Spec nor publishes issues.
- When checkpointing, `plan.md` indexes authority, proof, owner, endpoint/readback, recovery and next actions. Link settled content; combine compatible records and add artifacts only for missing information. Reopen decisions affected by implementation evidence and continue independent work.

## Choose the work needed

- Choose the smallest sufficient path; record it in `plan.md` when checkpointing:
- **Defined task:** use delivery below; small feature/UI edits need no map, separate design ceremony or controller.
- **Explicit controller app selection:** read [controller app use](references/controller-execution.md). Deep Loop guides the separate Deep Loop Controller app; it does not contain or install that runtime. Verify the selected app/version and current capabilities. Preserve scoped authority and live-proof gates; ordinary tasks retain the existing path.
- **Unclear destination or major cross-session decisions:** read [decision mapping](references/decision-mapping.md), resolve one shared map, then return to delivery. Planning-only endpoints require independent inspection of decisions/handoff, then stop.
- **Coordinated parent delivery:** before assignments/implementation, read [coordinated delivery](references/coordinated-delivery.md) when explicitly requested or separately assigned slices need combined parent acceptance/release; retain coverage, applicable design approvals, executable baselines, independent review and verified host coordination. Complexity within one assigned task alone does not select it.
- Decision mapping feeds either path; one coordinator owns the parent. Reuse maps/contracts and link tracker/external evidence without duplicating ticket state.
- Governing instructions and scope/authority apply; this skill grants no permission. Current shared router supersedes historical blanket approvals, preserving specific design, irreversible-action, commit/review and recovery gates. Read [merge provenance](references/merge-provenance.md) only to trace adaptations.
- Before delegation, read [worker selection, models and concurrency](references/mattpocock-integration.md#worker-selection-models-and-concurrency); inspect requested guarantees, live ownership, isolation, review and applicable controller capabilities, then state the supported path. Inherit models by default; justified supported exceptions preserve user choices. Missing required guarantees block dispatch; narrower paths need user selection. Keep trivial work direct; this shared rule does not select Matt's user-only workflows or waive selected execution/handoff contracts.
- Under governing JEV policy, read installed `jev-codex-routing` for eligible low-risk intake with multiple plausible profiles or repair after a concrete failed objective check. Named skills/user overrides and protected/uncertain work bypass JEV. Sanitized selection remains advisory (`applied=false`), granting no execution/model authority; retain repair limits and ordinary authorized work on abstention/unavailability. Passing checks need no call.
- Before design/implementation, read [UI/UX integration](references/ui-ux-integration.md) for new user-facing screens/flows without approved targets, UI/UX exploration/audits, source matching or Mobbin research; retain greenfield gates, Product Design ownership, provenance and rendered proof.
- For explicitly selected local job leasing or signed local evidence checks, read [local coordination](references/orchestration.md) and [verification boundary](references/trusted-execution.md). These optional helpers do not supply agent dispatch, authenticated process identity, sandboxing, workspace isolation or delivery proof; required coordinated-delivery guarantees remain in force.
- For an already gathered offline GitHub PR snapshot, read [GitHub normalization](references/github-integration.md). For recorded fixture summaries, read [evaluation](references/evaluation.md). These tools neither fetch live state nor authorize mutations or establish acceptance from recorded flags.
- For explicitly selected fixture-only replay or paired recorded reports, read [fixture workflow](references/workflow.md) or [fixture comparison](references/benchmark.md). They do not implement the task or establish empirical model performance; ordinary work keeps its existing execution and proof path.
- For full roadmaps, architecture/spec handoffs, realistic dogfooding, branch integration/closeout or release maintenance, read applicable [project lifecycle](references/project-lifecycle.md) sections; small tasks remain direct, without added controllers/schema.
- For installable iOS creation/testing/distribution, read [iOS delivery](references/ios-delivery.md). For substantial work, declare project-derived device/OS/build coverage with passed/failed/not-run cases and verify the actual endpoint. Browser prototypes prove no native result; this grants no build-service/distribution authority.
- Before offering/creating/resuming/updating goals, read [native goals](references/native-goals.md) for explicit goal requests, substantial implementation, cross-session work or coordinated delivery benefiting from runtime continuation. Small fixes, explanations and planning-only work need no recommendation.

## Start or resume

- Small tasks keep one build/review path; checkpoint when interruption, multiple components or delivery steps warrant it.
- For shared projects/sessions/maps, read [multiple sessions and maps](references/local-tracker.md#multiple-sessions-and-maps): one canonical map per outcome, linked bounded sessions and explicit concurrent session locators. Discovery authorizes no reconciliation, takeover or cleanup.
- `$deep-loop continue`/resume continues the authorized objective, not new sessions/backlog. Resolve it from chat or explicit locator; inspect `.deep-current.json` and matching plan/state if present. Pointers/newest timestamps prove neither scope nor ownership. Ask which equally plausible task, or request a missing locator instead of searching unrelated projects.
- After every compaction/handoff, reread governing and relevant skill/reference guidance. Recover scope, endpoint, decisions, pending questions, ownership, blockers and next action from authority; inspect actual code/branch/worktree, workers and applicable tracker/delivery state. Recheck stale/changed evidence and blockers, then continue safe in-scope work without repeated intake. Continue grants no answers, approvals, takeover or completed-objective expansion; report verified completion and await direction before new work.
- Before applying to a known writer's target, wait for compact status showing inactivity, then recheck exact preimages. Inspection/waiting needs no message; request messaging authority only if necessary. Unknown ownership, changed preimages, lock refusal or failed preservation stops dependent work.
- Checkpoint meaningful decisions, completed slices, failures and impending handoffs/interruptions; retain its locator. Persistence is agent-owned, not a compaction hook. For inspection outside an active workspace, use [active handoff](references/checkpoint-operations.md#recoverable-active-handoff) to retain selected references without retirement/authority transfer. Small uncheckpointed tasks recover from context/live readback; ask if scope/next action cannot be established.
- For explicitly selected serialized local step claims and attempt history, read [durable journal](references/durable-execution.md). It is optional bookkeeping, separate from acceptance checkpoints, and supplies no scheduling, dispatch, execution authority or coordinated-delivery guarantee.
- Before checkpoint creation/recovery/filling/validation, read [checkpoint operations](references/checkpoint-operations.md) for initialization, sibling discovery, state/schema and helper limits. Use its [read-only recovery report](references/checkpoint-operations.md#read-only-recovery-report) for selected evidence/blockers; confirm scope and actual ownership before acting on suggestions.
- For dependent slices, recurring issues or interruptible tracked work, read [tracked tasks](references/checkpoint-operations.md#local-tasks-and-goal-continuation). Small plans retain record order; selected ready-queue policies may rank explained user priorities, correctness/unblocking and declared aging, without overriding readiness, authority or ownership. External ticket state stays at source; checkpoints link bounded execution authority.

## Work to acceptance

- **PLAN:** Establish readiness; reuse acceptance/proof and fill only gaps. Name endpoint (local artifact, PR, release or live deployment), attributable authority and independent readback. Retain required verifiers as pending checks in `state.json` or task context, including applicable cleanup/security checks. Start the smallest slice once prerequisites settle.
- Checks/tasks default to `stage: review`; `ship` proves delivery and `closeout` actual post-delivery retirement. REVIEW requires due acceptance; final SHIP requires all stages. Pending implementation acceptance does not block BUILD after prerequisites/design authority settle. Archive preservation requires review/delivery proof before deferring explicit closeout records to its preserved working checkpoint.
- For substantive UI, register actual scope with `--ui-request` and select exploration/proof through the [UI adapter](references/ui-ux-integration.md) from approved acceptance. Reuse clear targets/patterns; owners select meaningful alternatives for unresolved direction. Exact fidelity retains approved Design Contract and current execution/capture/case evidence at REVIEW/SHIP. Established-component behavior changes need risk-based rendered, interaction, accessibility and responsive proof; existing bound gates remain.
- New schema-4 checkpoints set `uiRoute` to `not_applicable`, `specified` or `greenfield`, record [applicable evidence](references/ui-ux-integration.md), and pass `validate --stage build` before source edits. Non-UI stays lightweight; specified work needs a precise approved target. Greenfield requires Product Design, two or three meaningful options (three for broad exploration/stricter specialists), explicit selection and Mobbin provenance or evidenced no-comparable disposition. Schema-1/2/3 retain recorded contracts.
- Coordinated parents retain full coverage-index checks through REVIEW/SHIP. Closed decisions, finished children and empty frontiers do not complete parents; never switch paths to bypass required capability/approval.
- Build robust behavior with the minimum code that preserves supported contracts. Reuse existing implementations; remove duplication, speculative abstractions and redundant branches introduced by the change. Fail clearly on broken invariants. Use assertions for internal invariants and explicit checks at external boundaries; required production checks must remain active with assertions disabled. Verify valid and expected failure behavior.
- **BUILD:** Implement/validate a slice, then expand; use applicable debugging/design/review specialists. Retain failures, evidence and next safe action in task records or `state.json.issues`. Changes affecting passed checks reset them to pending and invalidate affected delivery proof.
- **REVIEW/FIX:** Execute/inspect acceptance checks against current work; preserve each command's exit before the next command. Batch native checks with `scripts/deep_loop.py --root <project> run-checks --checks <checks.json> --output <new-results.json>` and `[{"name":"<check>","argv":["<executable>","<argument>"]}]`; it retains output and stops at first failure. For finite explicitly safe batches, add `--collect-independent` with unique `id`, boolean `safe` and `dependsOn` IDs after reading [collection rules](references/checkpoint-operations.md#collect-safe-independent-checks). Inspect shell checks separately with explicit chain-failure handling. Runner neither marks checks nor interprets suite reports.
- When optional outcome contracts need local command receipts beyond existing project evidence, read [local proof](references/verification.md). Its reviewed-plan runner and manifest checker supplement evidence inspection; existing bound-proof and delivery gates still apply.
- For substantial, risky, resumed, delegated or external-delivery work, use [Verification Contract integration](references/verification-contract-integration.md) to bind deterministic proof to approved invocation, current source/environment and declared artifacts. Keep human judgment explicit and inspect outcomes independently; successful exit proves no undeclared outcome. Tiny reversible work may use inspected direct proof.
- Keep failed broad suites failed, including pre-existing failures; record scoped passes/coverage and baseline defect/disposition separately. Baseline findings waive no required check. `passed` requires concrete evidence; `not_applicable` requires scope-specific reason. Hosted CI needs observed success for exact delivery revision, with provider, run URL, revision and conclusion; workflow wiring/future runs prove no execution. Fix/rerun affected checks. Pay actual new debt now or retain explicit user acceptance, owner and paydown task; unresolved failures are not accepted debt.
- Agent rules/approval mechanisms, security-sensitive work, destructive migrations and governing review obligations require a distinct read-only review context. For other substantial work, name the independent-review risk; small reversible tasks may self-review with executed checks. Self-review is not independent; unavailable required review blocks. Follow [worker review selection](references/mattpocock-integration.md#worker-selection-models-and-concurrency); review replaces neither human approval nor endpoint proof.

Checkpointed work must pass review validation before SHIP:


```powershell
py -3 "C:/Users/Marcus Gollahon/.codex/skills/deep-loop/scripts/deep_loop.py" validate --stage review
```

- Failures remain in REVIEW/FIX. Re-scope only when evidence shows acceptance cannot be met within authority/runtime limits; budgets and retry controls belong to the harness.
- Small uncheckpointed tasks directly execute/inspect acceptance with the same failure, debt and delivery gates; no helper/state ceremony. Checkpoint if durable recovery or task growth warrants it.

## Ship and verify

- When writing or updating a PR body, use [PR body writing](references/mattpocock-integration.md#pr-body-writing) in ordinary and specialist-led delivery. Preserve required repository templates and explicit user formats.
- **SHIP:** Follow authority, delivery procedure, reviews and commit gates; deliver, then independently read back the named endpoint. Record observations/location; checkpoint `delivery.status: verified` only on acceptance. Git branches require verified PR, merged or explicitly user-selected kept-local disposition; non-Git/non-branch artifacts record why branch disposition is not applicable. Local commits cannot replace agreed PR/merge/release/deployment endpoints.
- For declared structured artifact readback, follow [bound endpoint readback](references/verification-contract-integration.md#bound-endpoint-readback): separately inspect the saved artifact through approved readback, retain bound observations and compare exact endpoint/target/revision at SHIP. Acceptance results do not replace readback.
- For risks beyond immediate readback, declare probes/observation conditions before delivery and retain required SHIP results under [delayed proof](references/outcome-measurements.md#delayed-proof), including authorized observation, unavailable-proof recovery and completion limits. Immediate readback suffices when it proves acceptance.
- Verify production version/behavior at the live target; tests, merge or deployment-job success do not suffice. Inspect/execute local saved artifacts through intended interfaces. Preserve failed acceptance and repair/roll back within scope; unavailable required readback blocks.

Checkpointed work must pass SHIP validation before completion:


```powershell
py -3 "C:/Users/Marcus Gollahon/.codex/skills/deep-loop/scripts/deep_loop.py" validate --stage ship
```

- Record retained locally excluded checkpoints without a separate retention check; actual retirement requires recoverable preservation and independent readback.
- After validation, actual evidence inspection and verified selected closeout, run `deep_loop.py complete`; it revalidates SHIP against unchanged state and atomically sets `phase: COMPLETE`, `complete: true`, `active: false`. Never hand-edit terminal fields. Archived `finalize-archive` transitions only after supplied cleanup readback. Uncheckpointed completion still requires acceptance, independent endpoint readback and selected cleanup; checkpoints add no ceremony. Report result/evidence and accepted debt or blockers; retain incomplete records, failed evidence and next safe action when blocked.
- Before optimization comparisons/improvement claims or selected substantial tasks, read [outcome measurements](references/outcome-measurements.md). Derive metrics from actual local records, leave unavailable values unknown and obtain threshold approval after baseline research. Tiny tasks need no telemetry.
- After verified SHIP, offer user-selected `retro` for repeated mistakes, costly navigation/tools or missing guardrails; if selected, read [retrospective handoff](references/mattpocock-integration.md#optional-retrospective) for evidence-linked candidates. Routine tasks need none.
- Finish with delivered result, checks and material limitations/blockers; explain consequential tradeoffs, link useful evidence and match requested depth.
