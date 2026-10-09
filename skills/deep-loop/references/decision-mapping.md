# Decision mapping

Use during PLAN when the destination contains unresolved decisions too large or dependent to settle in one session. A map finds the route; it is not an implementation backlog or a second delivery workflow.

## Establish the destination and authority

Name what reaching the end means: an agreed specification, a settled decision, a planning handoff, or a delivered change. Separate included work from exclusions. Retrieve existing specifications and locked decisions; involve the user where their preferences or choices are required. Never invent their answers.

Use the entry point's intent interview for human choices: survey the whole scope, then ask dependency-ready questions in rounds with recommendations. Keep dependent questions for later rounds and recap the settled answers before advancing. If the route is already clear, continue ordinary PLAN without creating a map. A direct delivery request does not require a separate planning approval unless an applicable decision/design gate calls for it.

## One canonical map

Keep one canonical decision map per distinct outcome, identified by its destination and completion boundary. Independent outcomes in the same project may have separate maps. Sessions contributing to the same outcome link to the existing map from their plans; a new chat, branch, worktree, or checkpoint does not create a new outcome. For coordinated delivery, use the shared parent map and link bounded child records. Small settled work still needs no map.

Reuse the configured tracker and its Wayfinding conventions. Use native parent/child and blocking relationships where supported. Without a configured tracker, use local Markdown records linked from `plan.md`; no external service or tracker setup is implied. Record identity, dependencies, and ownership explicitly in that fallback.

The parent map is an index with:

- **Destination:** the outcome and completion boundary.
- **Notes:** applicable sources, preferences, selected delivery path, and authority pointers.
- **Decisions so far:** one-line summaries linking resolved decision records.
- **Not yet specified:** in-scope questions that cannot yet be phrased precisely.
- **Out of scope:** consciously excluded work, its reason, and any linked excluded ticket.

Decision detail lives once, in its ticket/record. Refer to linked descriptive names in user-facing text rather than bare numbers. Open work comes from child records, not another manually maintained list.

When existing maps overlap, inspect their authority, ownership, decisions, exclusions, dependencies, and evidence before proposing reconciliation. Classify each as authoritative, supporting, superseded, or archived; retain unique content and explicit successor links. Conflicting decisions remain unresolved until governing authority or attributable owner input settles them. Preserve legacy maps rather than merging, replacing, or deleting them on discovery. Reconciliation and archival require their own authorized scope; a policy update does not authorize changing existing project records.

Use the project's existing index if finding outcomes becomes difficult. Add links there without copying decisions or maintaining another status ledger. See [multiple sessions](local-tracker.md#multiple-sessions-and-maps) for checkpoint selection and verification.

## Questions, dependencies, and the frontier

A decision ticket states the precise question and links necessary context. Create precise questions even when blocked; retain only genuinely unspecifiable questions in Not yet specified. Create records before wiring their dependencies. Keep implementation slices distinct from decisions.

Use these categories when helpful; they do not require new labels:

- **Research:** obtain facts from documentation or relevant sources. Delegate only through available, authorized facilities; direct research is valid when delegation is unavailable.
- **Prototype:** make an isolated artifact to resolve appearance or behavior. Link it as evidence; a decision prototype is not automatically production code or approval.
- **Human discussion:** resolve preferences or domain choices with the actual user. Optional grilling/domain-modeling skills follow their own invocation rules.
- **Prerequisite task:** perform bounded work needed to make a decision, under existing authority; link the resulting facts. This category does not license arbitrary implementation.

The frontier consists of open, dependency-ready, unclaimed work. Verify and acquire ownership before working a shared ticket using the tracker's actual claim mechanism. A basic planning assignment is not proof of an atomic implementation lease. Concurrent sessions must not take the same ticket. Apply coordinated-delivery ownership requirements before assigning implementation writers.

## Resolve and reveal

Choose the user-named question or the next eligible question advancing the destination. Load the parent once, then retrieve full relevant decision records as needed. Resolve from inspected evidence or attributable human input. Record the answer and evidence in the decision record, close it, and add its linked gist to the parent.

Graduate newly precise questions from Not yet specified into tickets and wire their dependencies. Reconcile affected decisions and edges after new evidence. Preserve rejected or superseded decisions with reasons. If a question is excluded, close it as excluded and index it under Out of scope; closure does not satisfy a still-required dependency. Never shrink the destination merely to finish.

Work may continue across eligible questions within the actual host's limits. Human-dependent questions wait for the human; do not simulate both sides. Numeric session/research caps and mandatory branch creation are not inherited from upstream Wayfinder.

## Handoff and completion

An empty frontier can mean a cycle, missing ownership, a human wait, or uncharted scope. Inspect those conditions and remaining coverage before declaring the route clear.

For a planning-only endpoint, verify that the requested decisions, unresolved constraints, specification/assets, and next execution handoff are usable through their saved records. Return that evidence to Deep Loop REVIEW/SHIP; a resolved map is evidence of planning, not delivery of a product.

For a delivery endpoint, carry the settled decisions and dependencies into the chosen Deep Loop delivery path. If implementation reveals a changed interface or acceptance decision, reopen the affected planning question in its existing authority and pause only dependent work. Ordinary defects stay in REVIEW/FIX.
