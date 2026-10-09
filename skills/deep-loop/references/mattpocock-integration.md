# Matt Pocock workflow integration

The worker-selection section also applies to ordinary Deep Loop delegation. The other sections apply when the user chooses Matt's workflows alongside deep-loop. Read the selected installed skill before execution; its current instructions and the task's authority govern its work. Resolve named skills from the current catalog. When an instruction names a Skill tool unavailable in this runtime, read and apply the installed source after its invocation requirements are satisfied.

## Choose the execution owner

| Work | Skill boundary |
| --- | --- |
| Unresolved requirements or major decisions | Deep Loop's native decision mapping, or user-selected `grill-with-docs`/`wayfinder`; their output informs PLAN. |
| Specification and dependency tickets | User-selected `to-spec` and `to-tickets`; link their outputs in plan.md. |
| Small bounded implementation | User-selected `implement`, or ordinary direct BUILD. |
| Dependency graph with independent tickets | User-selected `implement-spec` owns worker dispatch and integration. |
| Existing Superpowers execution plan | Selected `subagent-driven-development` owns its worker/reviewer loop. |

Select one implementation controller for an effort. Deep-loop owns the overall acceptance/delivery checkpoint; the selected controller owns execution progress. Small tasks keep one build/review path without a ticket graph.

Native decision mapping and coordinated delivery are part of Deep Loop and do not invoke Matt's user-only entry points. When the coordinated path applies, its verified host-controller, approval, and evidence requirements remain in force with any selected implementation owner.

Matt's user-invoked entry points use `disable-model-invocation: true`. Deep-loop may suggest them; the user selects/invokes them. Naming deep-loop alone does not invoke those entry points, and one user-invoked skill does not automatically fire another. Once selected, use its model-invoked disciplines (`tdd`, `codebase-design`, `diagnosing-bugs`, `code-review`, `pr`) when applicable. Missing setup or unresolved test seams are handoff gaps to resolve under the selected skill, rather than inventing tracker configuration or test authority.

## Handoff and return

In plan.md, record the selected controller and the user's selection, then provide pointers to:

- authoritative spec/tickets and their dependency graph;
- repository instructions, interfaces, and resolved decisions;
- integration base, declared write scopes, acceptance checks, and applicable delivery/rollback contract.

Reuse existing artifacts. Tickets remain authoritative for their status and dependencies. Deep-loop records overall checks, blockers and evidence links; only the coordinator updates its state.json. Workers write their scoped code and reports. On resume, reconcile tracker/branch state and saved evidence before dispatching unfinished work.

The controller returns the integration revision/diff, resolved and unresolved tickets, check commands/results, review findings and dispositions, accepted debt, and artifact/report paths. The coordinator inspects those artifacts and runs integration checks covering the combined changes. A worker's passing tests establish only its scoped result.

If new evidence changes an interface, dependency or acceptance decision, pause affected tickets, resolve the decision in its existing authority, and refresh the handoff. Ordinary defects remain in REVIEW/FIX.

## Worker selection, models and concurrency

Keep trivial work direct. When delegation is available and authorized, select separable research, an independent review, or a verifiable implementation slice only when the returned result advances acceptance. Read-only research or review within one task does not by itself select coordinated parent delivery; separately assigned implementation slices with combined parent acceptance/release retain that path's required host capabilities and gates.

Give each worker the bounded task, relevant authority and artifact pointers, permitted write scope, acceptance check, and required return evidence. Only the coordinator updates parent checkpoints and integrates the combined result. Inspect worker outputs and verify parent acceptance; a worker report alone is not completion.

Before dispatch, establish the requested guarantees and inspect current facilities. Retain a compact preflight in the existing task record: selected path, authority, assignment and write owner, isolation/preimages, review obligation and distinct context availability, applicable controller capability, model/fork restrictions, verified facts, unknowns/blockers and next safe action. Tool availability is not evidence of ownership, enforced limits or durable recovery. Inspect live state where that guarantee depends on it; refresh after interruption or changed ownership/capability. Do not create a separate tracker or capability service.

| Requested path | Required capability before dependent dispatch |
| --- | --- |
| Bounded read-only research/review | Authorized facility and inputs, separate output scope, actual distinct context when independent review is required; no write takeover. |
| Bounded delegated implementation | Settled requirements/authority, verified write ownership and isolation for the assigned scope, applicable review and parent acceptance; no implied unattended continuation. |
| Durable/concurrent/cross-session coordination, or an already-required coordinated contract | Verified host enforcement and attributable controller/configuration/run-state readback under [coordinated delivery](coordinated-delivery.md), including ownership/isolation, persistence, limits and integration/release exclusivity. Ephemeral workers alone are insufficient. |

State the supported path before dispatch. Required unavailable or unknown ownership, isolation, review or controller guarantees block only dependent assignments/actions; continue safe independent work. Report the exact gap and offer a narrower path for user selection rather than silently downgrading the requested guarantees or installing infrastructure. Preserve a governing coordinated contract even if another path is available.

Select acceptance review by risk. Agent rules or approval mechanisms, security-sensitive changes, destructive migrations, and governing review obligations require a distinct read-only review context. Other substantial work uses independent review for a named uncertainty or risk; small reversible work may use executed checks and self-review unless governing instructions require more. A separate context must inspect the exact change and authority; an implementer's second look is self-review. If required independence is unavailable, retain the review blocker. Independent review replaces neither human approval nor delivery proof.

**Inherit the current model by default.** Inspect the facility's documented inheritance behavior; omit overrides where omission inherits. A role label alone does not require another model. A permitted, supported exception may use a lighter model for clearly bounded mechanical work with strong checks, or stronger reasoning for a named difficult judgment. Record the task-specific reason and requested model/effort/fork in the existing assignment. Existing tier suggestions are optional heuristics for an exception, not default role assignments or measured cost guarantees. Honor explicit user model choices; never change parent/global settings to implement a worker exception.

Use current tool metadata for supported dispatch IDs, reasoning and fork restrictions. In this Codex collaboration runtime, a full-history fork inherits and cannot take overrides; a justified exception needs a supported fresh or bounded-context fork. If an optional heuristic override is unavailable, use the permitted inherited path and report the limitation. An explicit required model or required fork that cannot be honored blocks dependent dispatch; offer compatible alternatives for user selection, without substituting a different model or dropping required context. Requested dispatch configuration and observed execution identity are separate: when the runtime does not expose identity or resource/cost data, retain unknown and make no unsupported savings claim.

Diagnose a failed objective check before escalating. More reasoning or another supported model can address evidenced missing judgment or unresolved complexity; tool, input or environment failures require their own repair. Runtime budgets and retry limits remain in the harness.

When supported by the current runtime and selected controller, async dispatch lets the coordinator continue independent work while a worker runs; parallel dispatch runs independent ready tickets concurrently. Follow the selected controller's concurrency rules: `implement-spec` uses per-ticket worktrees and an integration branch; `subagent-driven-development` has conflicting parallel-write instructions, so default to its sequential implementation path. Explicit user instructions take precedence; parallel implementation still requires the dependency and write-ownership checks below. Record the override instead of silently rewriting the installed skill.

Prove dependency readiness and separate write ownership before parallel implementation. Overlapping or uncertain writes run sequentially; isolated branches still require conflict and semantic integration review. Serialize integration-branch mutations through its owner. Workers do not reset or overwrite another writer's work. Runtime concurrency, retry limits and budgets stay in the harness.

## Return to delivery

Implementation completion means the reviewed code is ready at the agreed implementation endpoint. A resolved ticket, ready PR or integration branch does not establish a requested production deployment. Carry returned evidence into deep-loop REVIEW, then use its SHIP contract for the actual requested endpoint and independent readback. When the endpoint is the local artifact or integration branch itself, verify that endpoint directly. Required unavailable evidence keeps the checkpoint incomplete with its blocker and recovery path.

This reference describes agent handoffs. It does not add a scheduler, automatically launch workers, change models/settings, or broaden the task's execution authority. Repository commit/review gates and recovery rules remain applicable to every worker and merger.

## Optional retrospective

After verified SHIP, the user may select `retro` to improve future agent runs. It remains a user-invoked specialist, separate from acceptance review and delivery. Read the installed `retro` and its `writing-for-agents` dependency; apply the runtime's supported source-reading equivalent if its Skill tool is unavailable. Use the user's selected session, or the current session by default, and inspect primary session evidence and repository check/CI configuration.

Return candidates in severity order with the observed problem, evidence, proposed improvement, and expected benefit. Reuse existing navigation, checks, review standards, and lessons authorities. Mechanical violations belong in deterministic checks; judgment calls belong in review guidance. A clean-no-op is a valid result. Link useful findings from the existing checkpoint when present, and promote durable lessons only under the shared router's persistence rules.

Retro recommendations are separately scoped work, not permission to edit skills, global instructions, CI, or access settings. Implement them only within explicit task authority and applicable preservation/review gates. Unresolved acceptance failures stay in REVIEW/FIX; a retro neither substitutes for delivery evidence nor adds a phase, schema, or completion gate.
