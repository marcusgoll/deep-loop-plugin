# Merge provenance

Deep Loop 0.3.0 consolidates planning and coordinated-delivery capabilities into one conditional entry point. The installed Wayfinder and Wayfinder Delivery packages remain intact; this merge does not migrate existing callers or automations.

Sources inspected: installed Deep Loop 0.2.2 and its state, Matt Pocock, and UI/UX references; installed Wayfinder SKILL.md; Wayfinder Delivery 0.1.1 SKILL.md, coordination, design approval, verifier contract, evidence schema/example, and provenance/evaluation scenarios.

Wayfinder Delivery records its upstream source as Matt Pocock's `mattpocock/skills` at commit `c55ee46073ed923f86ce59a5eb3b6d895095d1b7`, Wayfinder blob `812805b760baf328db0ebdef6f3807e381f97016`. These identifiers are recorded provenance from the local package, not a new upstream verification. The copied MIT notice is retained at [LICENSE-wayfinder](../LICENSE-wayfinder). No upstream endorsement is claimed.

Retained: canonical map/index, decision detail in tickets, dependencies/frontier, in-scope uncertainty versus exclusions, real human decisions; parent coverage and exact design approvals; executable baselines/sensitivity checks; independent review; host-enforced coordination/limits; integrated release identity/live verification and compatible recovery.

Adapted: mapping is a Deep Loop PLAN capability; planning-only requests have a planning endpoint; coordinated delivery feeds the existing checkpoint schema. Direct tasks remain lightweight. Upstream one-ticket/session rules, mandatory research branches/grilling, and automatic research dispatch are not inherited. User-only upstream orchestrators are not silently invoked. Skill instructions do not implement a controller or prove evidence authenticity.

Authority: the current governing shared router wins historical general approval/scoped-autonomy wording. Specific design approvals and safety, verification, ownership, irreversible-action, and commit/review requirements remain. No permission/configuration change is bundled with consolidation.

Local installed package has no owning Git repository. Preserve preimages and record content hashes and validation under runs; no canonical shared-library or other-runtime publication is implied. Package validation and scenario exercises do not establish a successful live coordinated-delivery pilot.
