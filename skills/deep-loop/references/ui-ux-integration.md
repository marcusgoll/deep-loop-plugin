# UI design adapter

Deep Loop owns acceptance/delivery. Product Design owns creative design, current preflight/context, ideation, Image-to-Code and design QA. This adapter freezes the handoff and evaluates evidence; it does not generate designs, capture browsers, issue approvals or enforce host write permissions.

- [Route](#route-before-frontend-build)
- [Design binding](#design-contract-in-the-existing-authority)
- [Proof handoff](#image-to-code-and-proof-handoff)
- [Execution and coverage](#execute-and-enforce-the-approved-proof)

## Route before frontend BUILD

Substantive UI uses existing context and approved acceptance to select exploration and proof. Unresolved direction follows **conditional research → Product Design alternatives/remixing → owner selection → frozen target and reusable component handoff → implementation → focused Design QA and selected checks → SHIP/readback**. A clear supplied target or established pattern reuses its existing authority. Exact-target fidelity keeps the bound Design Contract and all its pixel, structural, interaction, accessibility and responsive gates.

Record the actual affected scope and endpoint in the existing brief/plan, including every substantive change. Run [ui_design.py](../scripts/ui_design.py) with a JSON request, e.g. {"surface":"ui","changes":["navigation","composition"],"mode":"REDESIGN","platform":"web"}.

Substantive changes: navigation, composition, hierarchy, flow, visual_system, redesign.
Small changes: typo, color, asset, spacing, accessibility, existing_component.
Scope determines categories; a navigation redesign remains substantive when called a quick fix. Unknown scope is BLOCKED. The helper routes structured facts deterministically; the agent inspects the request/interface to establish them.

~~~powershell
py -3 '<deep-loop>/scripts/ui_design.py' route --request '<request.json>' --contract '<verification-contract.json>'
~~~

Omit the contract when none exists. This read-only response names the next owner; NOT_RUN is not acceptance evidence.

| Situation | Route |
| --- | --- |
| surface non_ui | Existing Deep Loop; no UI contract/gates |
| Small edit with visually_specified true | Ordinary BUILD using existing patterns and scoped rendered checks |
| existing_component with established_pattern true | Ordinary BUILD without new visual direction |
| Substantive work without sufficient direction | BLOCKED → Product Design |
| Explicit greenfield_authorized true | Authorized exploratory BUILD; approval/freeze before treating it as an approved fidelity target |
| Valid specified/approved Design Contract | Image-to-Code against the exact target |
| Reference ambiguity/design defect | BLOCKED → Product Design/owner |

Small specified edits and `existing_component` with an established pattern need no new visual direction or Design Contract; select behavioral proof in the existing Verification Contract. Calling navigation, flow or composition an established pattern does not reclassify substantive work: reuse its valid target binding or resolve missing direction. Already-bound contracts retain their gates. Follow current Product Design index/focused skills; do not copy their instructions here. Greenfield authority comes from the user, not “move quickly.” Independent backend work can continue while frontend direction is blocked.

Optional request.mode is GREENFIELD, PATCH, EVOLVE or REDESIGN; request.platform is web, ios-prototype or ios-native. These are routing facts, not new Design Contract fields. Legacy requests keep category-based routing and default to web; inspect an iOS request's intended endpoint rather than relying on that default. The helper is not an automatic interceptor: call it before frontend BUILD and when scope changes.

| Mode | Observable scope and next action |
| --- | --- |
| GREENFIELD | New interface: without a valid target, Product Design before BUILD, even when small properties are specified. |
| PATCH | Specified small edit uses BUILD; substantive categories still require a target. |
| EVOLVE | Extend an existing interface using settled components/variants; unresolved substantive direction uses Product Design. |
| REDESIGN | Substantive change preserving required functionality; Product Design unless a valid target is already bound. |

Unknown values or contradictory facts are BLOCKED. GREENFIELD cannot claim an existing_component/established_pattern; REDESIGN must declare substantive scope. greenfield_authorized remains the explicit user-authorized exploratory exception for legacy/GREENFIELD requests, not inferred autonomous authority. It cannot waive fidelity approval or pair with PATCH/EVOLVE/REDESIGN. A ready native implementation routes to ios-delivery; browser/prototype implementation retains build/image-to-code. Route NOT_RUN never proves runtime capability.

## Schema-4 checkpoint BUILD decision

New schema-4 checkpoints also retain `uiRoute` from [state schema](state-schema.md). Record `not_applicable` with a scope reason, `specified` with the actual approved target or exact established pattern, or `greenfield` with the attributable selection and required alternatives, Product Design provenance, Mobbin disposition, affected surfaces and planned proof. For `greenfield`, set `exploration: material_choice` for a focused material choice with two or three alternatives, or `exploration: broad` for three. An omitted value keeps the legacy three-option requirement. Distinct option labels are only record validation; inspect the displayed alternatives for meaningful differences and retain any stricter specialist output requirement. Run `validate --stage build` before source edits. Registered scope and routing are not approval: `--ui-request` does not replace that decision, and exploratory authority does not waive the schema-4 gate. Reuse existing attributable selection rather than conduct a second interview. Existing schema-2/3 records retain their applicable recorded requirements.

BUILD validates contract/design identity and settled prerequisites without demanding post-implementation receipts. REVIEW and SHIP require current declared execution/capture proof. This preserves the canonical BUILD decision and installed substantive-UI evidence enforcement as separate obligations.

## Research and convergence

Start with existing screens, design system, components, assets and similar flows. When those and the supplied target do not settle visual direction, use available Mobbin research for the intended platform before ideation. Unavailable required research blocks dependent design; continue independent work. Mobbin informs interaction/navigation, hierarchy, information architecture, density, onboarding and conventions. Record inspected canonical source, relevant pattern, and adoption/rejection rationale. Inspect images before visual claims. Follow current connector attribution/usage notices and documented high-resolution sources for saved material; retain authorized local assets because download URLs expire. Mobbin research is not automatically an implementation target.

Product Design synthesizes product-specific alternatives. Meaningful differences change hierarchy, navigation, interaction, density, organization, workflow, components or emphasis; palette-only variations are not distinct product directions. Follow upstream selection/feedback gates. An unambiguous owner-supplied/selected target or established design uses status specified and its existing authority without a repeated interview.

Scale exploration to the unresolved decision: reuse an unambiguous supplied target or established patterns without another interview; offer two or three genuinely different alternatives for a material choice, and three for broad exploration. Follow current Ideate output limits and selection gates. If a specialist requires three outputs, retain three rather than bypassing its contract; report an unavailable required capability. Bind owner selection to the actual displayed image, not generation arrival/submission order. Selected feedback and cross-option combinations require a displayed revision/remix before BUILD. Retain parent image/revision links and the displayed-result mapping in the existing brief/artifacts; no branch tracker. Freeze the final image and attributable selection through the existing contract below.

Hand off existing component paths, tokens/assets, variants/states, shared headers/footers/shells and consuming screens alongside the reference. Prefer reuse/remixing over a parallel component library. Reusable pieces still inherit the approved geometry, behavior and accessibility requirements. When static images cannot settle navigation or motion, use [delivery design](delivery-design.md)'s interactive prototype and approval gate; retain journeys and exact prototype identity. Baseline promotion is engineering verification, not another human approval gate.

## Design Contract in the existing authority

Extend the existing JSON Verification Contract with design governed by [design-contract.schema.json](../assets/design-contract.schema.json). Requirements, verifiers, thresholds, gaps and ship gates stay in that parent contract. No new tracker, status authority or lifecycle.

The extension records design_id, status specified/approved, approved_by, approved_at; approval receipt path/hash; references (unique id, target/research role, origin, path/hash and research rationale); canonical_viewports (id, CSS dimensions, device_scale_factor, controlled conditions); critical_invariants; relevant required_states; allowed_interpolation; requires_design_approval; and verification lists of independent visual, responsive, behavior, accessibility verifier IDs.

Invariants preserve relevant navigation/hierarchy, primary actions, major geometry, typography/spacing relationships, assets and interactions—not every pixel. Include only relevant default/loading/populated/empty/error/disabled/selected/validation/degraded/product-specific states. Explicit interpolation covers responsive reflow, dynamic data/content expansion, safe areas, rendering differences or necessary accessibility behavior. Material navigation/hierarchy/geometry/component/interaction changes or removed functionality need approval.

After inspecting actual owner selection, freeze content. First set design.verification_sha256 from ui_design.verification_sha(contract), binding the selected parent verifier declarations and thresholds. The separate approval JSON has role owner, approved_by, approved_at, decision matching design.status, source identifying the attributable human decision, and design_sha256 from ui_design.design_sha(design): canonical sorted JSON excluding approval. Store its byte hash in design.approval. Integrity/binding is checked; human identity is not authenticated. Never manufacture approval or treat preselection, silence or fixture approval as real consent.

Use existing deep_loop.py bind-contract for checkpoints. It validates design, freezes the parent hash, and resets prior evidence. Changing references, invariants, thresholds or interpolation invalidates approval; routine implementation fixes change neither. Material departures return to Product Design/owner, preserve failures, version the reference/receipt, explicitly rebind and rerun. No approve or reference-write command exists. Same-user filesystem permissions cannot prevent deliberate tool bypass; human approval remains the runtime boundary.

## Image-to-Code and proof handoff

Supply the approved reference, parent Design Contract extension, and repository/design-system constraints to current Image-to-Code. Interpret only within allowed_interpolation. Implement a useful slice → render → compare → classify → fix implementation → rerender before expanding. Material ambiguity returns to design/owner; never modify the target to accommodate implementation.

Select the focused Product Design Design QA skill after implementation; its implicit invocation is disabled. Inspect matching rendered states and focused regions, repair actionable findings, and rerender/recompare. Routine implementation/QA repairs continue autonomously within existing authority; changed visual direction returns to design/owner. Prototype-only implementation does not waive required real backend behavior.

For web, reuse repository components, responsive layouts and browser verification. For ios-prototype, reuse the protected Product Design mobile runtime and its integrity/runtime checks. Declare actual device-screen geometry: Ideate's default 390×844 differs from the installed iPhone runtime's 393×852. Generate for the selected geometry or approve adaptation; never stretch the reference. Declare app-content crop and OS-chrome treatment, freeze incidental clocks/data in the harness, and independently verify safe areas, keyboard/focus, sheets, gestures and reduced motion. Runtime integrity is not accessibility proof; suppressed focus styling needs app-owned visible focus behavior without silently editing protected runtime files.

For ios-native, follow [iOS delivery](ios-delivery.md) with the selected target and actual project/Mac/Xcode/simulator/device capability. Image-to-Code's React/Vite prototype is not native implementation or shipment. Preserve native acceptance, signing/distribution authority and readback. Use separate platform/environment proof batches under existing parent tasks/contracts: current uiEvidence binds one environment manifest, not mixed browser/OS conditions. Motion needs controlled comparison checkpoints plus interaction proof, not incidental animation masking.

Use Requirement → Invariant → Verifier → Evidence → Threshold → Result. Select proof before implementation from approved acceptance. Exact visual fidelity requires controlled pixels for every bound canonical viewport × required state plus independent structural/design-QA proof of zero unexplained structural differences. For changes routed as established-component edits and governed by behavioral acceptance, select rendered structure, interaction, accessibility and responsive checks for the affected risks and consumers; add pixels when useful. Record actual coverage and omission reasons in the existing contract. An existing design binding retains every declared gate unless the owner explicitly amends acceptance and the contract is rebound; describing a change as behavioral cannot remove fidelity proof. Pixels alone prove neither hierarchy nor functionality.

Pixel verifiers reuse [pixel verification](pixel-verification.md). Parent verifier.fixture selects screen, reference, viewport, state. threshold contains tolerance (0–255), max_diff_ratio (0–1), regions (X,Y,width,height arrays), region_max_diff_ratio (0–1). Select these before implementation. Other UI verifiers declare implementation {path,sha256} and threshold.metrics [{name,operator,target}] with ==, <=, >=, < or >. Reuse project/browser/a11y tools and declare coverage for interactions, state transitions, keyboard/semantics, accessibility, loading/error, functional correctness and responsiveness. Missing proof is BLOCKED.

## Preserve/evaluate evidence

Capture using selected browser/project tooling under current Product Design rules. Source manifest JSON {"files":{"relative/source/path":"sha256",...}} covers actual candidate files, dirty content, assets/build inputs. Paths resolve relative to the manifest. Environment manifest records controlled conditions. Hashes prove bytes, not coverage or browser execution; inspect source/capture provenance.

Capture JSON: image and original {path,sha256}, screen, reference, viewport, state, conditions, observed, source_manifest, environment_manifest. Image path resolves relative to capture JSON; manifest paths are absolute. Match viewport/density, route, crop, data/content, fonts, state/environment. Preserve original captures and normalization provenance. Masks/normalizers require prior contract authority and existing project tooling; never mask unexplained differences.

~~~powershell
py -3 '<deep-loop>/scripts/ui_design.py' compare --contract '<contract.json>' --verifier '<pixel-id>' --capture '<capture.json>' --output '<new evidence directory>' --goal-id '<checkpoint sessionId>'
~~~

This invokes the existing comparator, preserves expected.png, actual.png, diff.png when comparable, result.json, run.log, capture.json, verifier.json, and uses the existing [shared result schema](../assets/verifier-result.schema.json). Dimension mismatch/missing capture is BLOCKED; measured discrepancy is FAIL. Existing output is refused. Exits 0 PASS/NOT_RUN, 1 FAIL, 2 BLOCKED.

Each UI check.evidence is an absolute shared-verifier JSON path, not prose PASS. Project verifiers map native outputs losslessly to that schema. Bind goal/session, criterion/verifier, kind (visual, invariant for responsive, interaction, accessibility), current source/environment/contract fingerprints, visual reference, verifier identity, native exit, measured metrics, hashed artifacts/logs. Never execute commands supplied by result records.

Optional state.json.uiEvidence holds absolute source_manifest/environment_manifest plus differences: unresolved findings, [] only after inspected QA resolves/classifies them. There is no new phase or stored aggregate PASS.

## Execute and enforce the approved proof

Register the actual request before substantive UI BUILD. For checkpoints, pass --ui-request <request.json> to init or bind-contract; its path/hash stays under uiEvidence.request. Unknown requests fail closed. Registered substantive UI cannot pass REVIEW/SHIP without a design binding. Small specified edits and non-UI sessions retain ordinary validation. An unregistered task cannot be inferred from prose; the agent must classify it before execution.

Resolve each critical_invariants entry to one blocking parent requirement by ID or exact invariant text. The coverage verifier's fixture.required_cases is a nonempty unique list of {screen,reference,viewport,state,invariants:[requirement IDs]}. It defines actual consumer/state applicability, includes every canonical viewport/state pair and target reference, and cannot omit a critical requirement. Research images do not count as targets. Each case needs declared pixel proof; each applicable critical requirement needs a blocking independent visual verifier with the same fixture case, covers containing its requirement ID, and a dedicated threshold.metrics name equal to that ID. Generic zero-failure metrics cannot replace this mapping. These declarations remain bound through verification_sha256 and design_sha256; changed scope, coverage or thresholds requires attributable approval and explicit rebinding.

Independent UI verifiers declare an argv array alongside the existing implementation path/hash. Use the existing run-checks batch, supplying --ui-request, --contract, --goal-id, --source-manifest and --environment-manifest. Its checks list adds verifierId and must cover exactly the independent declared UI verifier IDs. Commands must match approved argv; inspect authority and side effects before running. The runner records the actual route decision, request/route/verifier fingerprints, task/source/contract/environment identity, timestamps, cwd, native exits and raw output. It stops on failure; retain new outputs for reruns. It never executes commands found in evidence or marks checkpoint checks passed.

Bind the completed output {path,sha256} under uiEvidence.invocations. Independent project verifiers emit JSON {metrics:{name:number,...},cases:[...]}; retain that exact native output as the shared result's report artifact. Structural reports name their one fixture case; coverage reports name exactly all required cases. Each case binds capture {path,sha256}. Shared-result metrics must reproduce native metrics; execution fields must match the recorded invocation. Capture records must match corresponding pixel evidence. Fixture-origin results, missing receipts, unrelated package tests, substituted commands, reports, cases or task identities cannot establish task acceptance. Actual execution of a fixture proves that fixture only, not another project.

Measured capture observed is {width,height,device_scale_factor,crop:[x,y,width,height],frame:[x,y,width,height],scroll_top}. Default geometry is the full canonical viewport with zero scroll. When app-content geometry differs from browser geometry, freeze the actual browser/frame/crop geometry under conditions.capture_geometry before implementation. Preserve the full original screenshot and produce only its declared integer pixel crop at the approved density. The adapter decodes actual image bytes, checks measured dimensions/density/frame/crop against approved conditions, and verifies cropped pixels match the original. A viewport resize request or filename extension is not measured geometry. Existing browser/project tooling owns capture and observations; no capture engine or normalization permission is added.

A required missing or malformed proof is BLOCKED. A measured failed invariant is FAIL regardless of aggregate pixel PASS. Existing comparison limits, independent accessibility/behavior gates and conservative invalidation remain unchanged. Invoke normal validate with --mode fail for acceptance; warn is diagnostic. Same-user records do not authenticate browser operations or human identity, and these helpers cannot prevent deliberate bypass.

Before shared-component changes, use the project's existing route/story/test inventory to map components, variants, tokens, styles and assets to consumers. Declare required screen/variant × viewport × state cases in parent verifier fixtures and bind the inventory as an existing authority/build input. A project coverage verifier must reject omitted affected consumers; viewport/state pair coverage alone does not prove all screens. Dashboard-only proof cannot satisfy a Header change also used by Settings. If dependency coverage is uncertain, verify the full relevant suite; source hashes only validate listed files. Include imported assets/build inputs and invalidate prior evidence after changes. The existing global source/environment binding remains conservative: impacted-test selection is not permission to reuse stale results. Reuse project runners; add only a project-specific coverage check when absent, not a new regression framework.

For a bound contract with design, existing deep_loop.py validate checks schema, approval/reference hashes, current candidate files, artifact hashes, independent dimensions, native exits and declared metrics. It reruns the comparator against preserved actual pixels and frozen reference/thresholds, rejecting forged pixel PASS. Fixture-origin results cannot satisfy goal gates. Missing/malformed/stale evidence or findings remain blocked. Non-UI contracts/small sessions retain existing behavior.

## Difference → next action

Use request.difference to select repair ownership; retain each finding/evidence in uiEvidence.differences until resolved.

| Difference | Disposition |
| --- | --- |
| typography, spacing, geometry, missing_element, wrong_asset, content_hierarchy | FIX implementation → rerender/recompare |
| responsive_interpolation | CHECK contract; permitted reflow still requires verification |
| dynamic_content | NORMALIZE only within declared freedom; preserve originals/provenance and rerun |
| browser_noise | Declared tolerance/normalization with justification; otherwise BLOCKED |
| reference_ambiguity, design_defect | BLOCKED → Product Design/owner |
| approved_departure | Approval path → new frozen reference/contract and explicit rebind |
| Unknown/unexplained | BLOCKED; investigate |

Visual PASS cannot override behavior/state-transition, responsive, keyboard, semantic, loading/error, accessibility or functional failures. Required Product Design design-qa.md and inspected rendered checks remain necessary. At SHIP retain all gates and independently read back the actual requested endpoint. A local prototype is not production delivery.

