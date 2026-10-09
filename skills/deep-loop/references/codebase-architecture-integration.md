# Codebase architecture integration

Deep Loop owns execution. Codebase Design supplies design vocabulary; Improve Codebase Architecture discovers candidates. This is guidance inside PLAN and verification design, not a new phase, controller, or mandatory artifact.

## Local design discipline

For the triggers in the main skill, read the installed `codebase-design/SKILL.md` (currently `C:/Users/Marcus Gollahon/.agents/skills/codebase-design/SKILL.md`). Apply its module, interface, depth, seam, adapter, leverage, and locality concepts to the affected flow. This reference does not replace that source.

Trace callers and existing ownership first. Prefer a meaningful existing interface that hides shared complexity. Include caller obligations such as ordering, errors, configuration, and performance, not only signatures. Apply the deletion test: does removing the module spread complexity into callers, or merely remove a pass-through? Respect the area's glossary and ADRs. Choose the smallest design that meets acceptance; do not invent adapters for hypothetical variation.

For deepening or dependency-driven proof, read that package's `DEEPENING.md` and classify each relevant dependency:

| Dependency | Interface proof and seam |
| --- | --- |
| In-process | Exercise real behavior through the module interface; no adapter needed. |
| Local-substitutable | Use the existing local stand-in; the seam can stay internal. |
| Remote but owned | Inject the transport port with production and in-memory adapters. |
| True external | Inject a port with a mock adapter; add required integration evidence. |

Bind observable outcomes through the meaningful interface to Verification Contract requirement IDs and existing checks. Stand-ins, mocks, and in-memory adapters do not prove a real remote endpoint. Keep required integration and independent endpoint readback explicit. Replace shallow internal tests only after equivalent behavioral coverage exists; preserve supported regressions.

When verification exposes a poor seam, first distinguish an interface problem from missing environment or endpoint evidence. Apply local Codebase Design analysis and propose a bounded repair. Unavailable proof remains a named gap; it does not license a broad refactor or a success claim.

For consequential, hard-to-reverse choices with competing plausible interfaces, recommend targeted Design It Twice. When selected or explicitly delegated, read the package's `DESIGN-IT-TWICE.md` and use its independent comparison method before settling the interface. Simple reversible choices do not need it. Report unavailable agent/runtime capabilities rather than claiming an unperformed comparison.

## Selected architecture survey

Use Improve Codebase Architecture only for an explicit architecture objective or a user-selected survey before a large build. If local analysis shows structure blocks sound verification, present that evidence and recommend a focused survey; wait for selection before broad exploration. An unclear architecture alone does not authorize a survey.

After selection, read the installed `improve-codebase-architecture/SKILL.md` (currently `C:/Users/Marcus Gollahon/.agents/skills/improve-codebase-architecture/SKILL.md`), even if it is absent from the discoverable catalog. Follow its scope, exploration, candidate, and owner-selection gates. If the source or required capability is unavailable, report the gap. Survey product code remains unchanged; any glossary/ADR edits must be within the granted scope and preserved independently.

For this integrated path, the user's requested format is Markdown candidate records with useful before/after diagrams. Include affected files, observed friction/evidence, proposed direction, locality/leverage or testing benefit, recommendation strength, and top recommendation. Defer concrete interfaces until candidate selection. HTML is optional when requested or useful; this task-scoped format adaptation does not change the standalone skill's HTML requirement.

The survey ends with candidates and owner selection, not implementation. After a candidate is selected, use the survey's Grilling loop and preserve its shared-understanding confirmation. Offer `grill-to-checklist` as the follow-on; once selected, reuse the settled discussion to produce its Build Contract without repeating the interview. Bind its requirements to Verification Contract proof and hand the bounded work to Deep Loop only when implementation is authorized. Neither recommendation nor contract creation supplies a missing owner reply or implementation grant.

Record unrelated architecture findings with reason, evidence, and affected area. Continue the current task when possible; do not silently refactor those findings. Link the chosen design, contract, proof, and gaps from the existing PLAN authority rather than creating a competing backlog.
