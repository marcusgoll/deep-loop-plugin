# Verification Contract in Deep Loop

Use this integration during PLAN for a supplied Build Contract, multiple requirements, quantitative thresholds, invariants, missing proof, or a requested contract. When agreed intent still needs observable technical acceptance, use the installed `grill-to-checklist` skill; reuse settled decisions and any adequate Build Contract. For proof design, use the installed `verification-contract` skill. Small tasks can keep the requirement-to-check mapping in the existing plan. Read the installed skill and its field semantics before deriving a machine-readable contract.

## Ownership and mapping

The agreed brief/spec owns desired behavior, scope, and settled decisions under governing authority; a bounded Build Contract may carry that behavior. Its technical checklist traces source decisions to requirement IDs, observable acceptance, verifier IDs, and gaps. Verification Contract owns proof design. Deep Loop owns execution and delivery status; `plan.md` indexes those authorities and records execution ownership, endpoint/readback, recovery, and next actions. Preserve existing project verifiers and evidence formats.

Reuse an existing authoritative contract; otherwise keep a checkpointed contract beside `plan.md` or in the project's existing acceptance document and link it. A settled spec and contract can replace a detailed implementation plan. Retain ordered slices when sequencing carries material risk or governance requires them, plus recovery and endpoint readback appropriate to the task.

| Contract item | Deep Loop record |
|---|---|
| Requirement ID and invariant | Link to the authoritative acceptance criterion by ID |
| Blocking verifier ID, threshold and artifacts | Required `state.json.checks` entry, initially `pending` |
| Blocking proof gap | Issue/blocker with affected requirement and next safe action |
| Actual verifier run | Inspected run artifact; a bound verifier also carries its receipt path/hash |
| Ship gate and revision identity | REVIEW acceptance plus independent SHIP endpoint readback |

Keep current run status in Deep Loop checks and existing result artifacts. The contract's availability field (`existing`, `proposed`, `implemented`) is not a run result. Generated contracts start `NOT_RUN`; if an aggregate contract status is maintained, derive it from the same inspected run evidence rather than treating it as a second authority. Never map a required missing verifier to `not_applicable`.

For checkpointed execution with an authoritative machine-readable contract, bind the linked JSON Verification Contract before execution. The Markdown Build Contract is readable acceptance input, not the JSON file passed here:

```powershell
py -3 "C:/Users/Marcus Gollahon/.codex/skills/deep-loop/scripts/deep_loop.py" bind-contract --path <checkpoint> --contract <contract.json> --endpoint "Saved CLI"
```

The helper records the contract path, content hash, semantic hash, and declared endpoint, adds blocking checks by `verifierId`, and resets prior check/delivery evidence while preserving settled schema-3/4 endpoint authority and structural delivery metadata only for the unchanged endpoint. Target/readback and branch-disposition proof is reset with affected evidence; a changed endpoint returns its authority decision to pending. Rebinding is an explicit acceptance change: retain its authority and rerun evidence. BUILD validates readiness and current contract/design identity without requiring pending post-implementation proof to pass. REVIEW requires its due blocking checks; SHIP requires all stages. Validation rejects changed contracts, missing or duplicate verifier mappings, nonpassing blocking checks, unresolved gaps at their named stage, and SHIP endpoint substitution. Unbound small-task sessions retain the existing manual mapping.

When only the contract's aggregate run status, verifier availability status, or their evidence annotations changed, refresh the binding without discarding already inspected Deep Loop evidence:

```powershell
py -3 "C:/Users/Marcus Gollahon/.codex/skills/deep-loop/scripts/deep_loop.py" refresh-contract --path <checkpoint> --contract <contract.json> --endpoint "Saved CLI"
```

The command succeeds only when the bound endpoint and semantic hash are unchanged. It preserves checks, phase, and delivery evidence while updating the exact file hash. Any requirement, invariant, verifier definition, gap, ship gate, endpoint, or older binding without a semantic hash must use `bind-contract` and rerun evidence; never edit the binding by hand.

## Execute the proof

Before BUILD, every blocking requirement has a suitable blocking verifier or explicit blocking gap. Resolve gaps that block implementation before dependent changes; completion/shipping gaps remain blocking at their named endpoint. A gap entry documents missing proof, not a waiver.

During REVIEW/FIX, execute authorized verifiers, inspect expected results and thresholds, and retain outputs tied to the actual candidate revision/content and environment. Mark the corresponding Deep Loop check passed only after that inspection. After changes, reset affected checks and delivery evidence and rerun relevant checks. Use [delivery verifiers](delivery-verifiers.md) for coordinated delivery requiring the stronger result/gate-reader contract.

At SHIP, inspect all blocking verifier results, resolve blocking gaps, verify applicable owner approvals against their artifacts, and independently read back the named endpoint. Existing authority determines whether approval is required; the contract grants no permission or additional approval gate.

## Validator boundary

The installed `scripts/validate_contract.py` accepts JSON only. Its `VALID` output checks selected fields, IDs and coverage; it is not full JSON Schema validation and does not execute verifiers, enforce thresholds, inspect artifact existence/freshness, enforce ship-gate booleans, or prove a claimed `PASS`. YAML is an authoring template; use the existing project conversion tool if needed.

Run it as an authoring check, then separately execute and inspect the required proof. Legacy generic checks validate recorded claims. Explicitly bound deterministic checks additionally validate their captured invocation, result and current declared file identities. Bound substantive UI additionally uses the existing Design Contract extension and current execution/capture/report validation in [UI adapter](ui-ux-integration.md); generic checks do not gain that evidence enforcement by implication. Neither validator substitutes for evidence inspection or the independent endpoint readback.

## Durable deterministic receipts

For consequential checkpointed work, declare each deterministic verifier's `proof` with `mode: "bound"`, approved `argv`, `implementation: {path, sha256}`, `source_manifest: {path, sha256}`, `environment_manifest: {path, sha256}`, and nonempty `artifacts: [{path}]`. Paths resolve from the contract's original directory. The source manifest is `{ "files": { "relative/source.py": "<sha256>" } }`; include all material source inputs. The environment manifest records the actual relevant environment. An optional absolute `working_directory` declares the command directory; otherwise use the contract directory. Artifact hashes are captured after execution. These declarations are part of contract semantics: changing them requires rebinding and fresh proof.

Run the existing helper with `run-checks --checks <batch.json> --output <new-results.json> --contract <contract.json> --goal-id <sessionId>`. Each batch entry has `name`, `verifierId`, and the exact approved `argv`. Set `--root` to the declared working directory. The runner keeps native exit/output and fails if declared inputs change during execution; it neither changes check status nor interprets arbitrary output as acceptance. After inspecting expected results, a passed checkpoint check uses its matching `verifierId`, explanatory `evidence`, and `receipt: {path, sha256}` for the saved results file. The receipt must match the checkpoint session, semantic contract, verifier, invocation, current declared inputs and artifacts. Missing, substituted, failed or stale bound proof blocks its due gate.

Use `proof: {mode: "manual", reason: "<why human judgment is required>"}` for an intentional manual verifier. Record its observed judgment and supporting artifacts in check evidence. Older contracts without `proof` retain their recorded-evidence behavior; they do not become bound execution proof. A required deterministic verifier must not be relabeled manual merely to bypass missing or failing proof.

The helper verifies declared file identity and captured result shape. It does not authenticate a human, prove an undeclared dependency, interpret every native test report, or establish external delivery. Inspect the verifier's expected behavior and thresholds, retain applicable specialized UI/native proof, and independently read back the actual endpoint.

Archived resolution retains existing bound proof; it does not accept a new receipt that was absent when preservation verified the dependency map. A pending bound closeout verifier therefore blocks preservation before retirement. Explicit manual closeout is available for judgments that are actually manual.

## Bound endpoint readback

For an artifact-backed delivery requiring durable independent readback, declare `proof.readback` on a blocking bound verifier:

```json
{
  "endpoint": "Saved summary file",
  "result": "readback.json",
  "targets": [{"id": "single", "artifact": "summary.txt"}]
}
```

The verifier uses the existing approved bound invocation and reads the saved artifact through its intended interface. Keep this inspection separate from producing the artifact; it must not rerun or modify the producer's output. Include the declared result and every delivered file in `proof.artifacts`. Paths resolve from the original contract directory. A single-target delivery uses ID `single`; multi-target declarations use exactly the corresponding `delivery.targets[].id` values. Each independent result is JSON with the exact declared endpoint and target entries containing `id`, observed `revision`, and the absolute original logical `artifact` path. Target declarations default to `revision_kind: "sha256"`; local file identity must be `sha256:<artifact digest>`. An adapter for a native or external endpoint may explicitly declare `revision_kind: "external"` to retain its exact build/commit revision plus a saved inspection artifact. That observation still needs the actual authorized endpoint probe; the helper checks its captured identities rather than fetching the external target. Any observed revision starting `sha256:` always has to match retained artifact bytes, including in external mode.

The declared observation file must be absent before its runner invocation. A preexisting result is retained and execution refuses before creating a new receipt, preventing a new run record from silently reusing an old report. Use fresh declared result locations when rerunning; changing their declaration requires rebinding rather than semantic refresh. Preserve prior proof and reset affected checks under the existing rerun authority. The helper never deletes an old report to make room.

Run through the existing `run-checks --contract ... --goal-id <sessionId>` interface, inspect the actual observation, then retain the results receipt in the corresponding passed checkpoint check. Binding creates this verifier's check at `stage: ship`; pending post-delivery readback does not block BUILD/REVIEW. SHIP, preservation and completion require the declared readback regardless of a later edit to the check's stage. The runner retains the observation and delivered file hashes, rejecting file changes during inspection. The gate compares current report/receipt/file bytes, authoritative endpoint, complete target set and exact delivered revisions; local SHA revisions must match actual bytes. A missing, failed, stale or mismatched observation blocks completion without terminal-state writes. Repeated `complete` rechecks current proof.

Changing readback definitions changes contract semantics and requires rebinding/fresh proof. This declaration grants no delivery, merge or deployment permission. Contracts without it preserve their existing manual or specialized readback requirements. A local downloaded report or file does not establish a server/device's live state: retain required native/live probes and human inspection under their existing contracts. The extension validates declared artifact-backed observation integrity, not human authenticity or undisclosed dependencies.

Existing archived proof retains its original readback identities through verified dependency resolution, including the observation and delivered artifacts. It records historical delivery proof rather than asserting a fresh live readback. Missing required readback blocks preservation before retirement. Future proof absent when preservation verified its immutable map remains unsupported; retain the live checkpoint for that workflow.
