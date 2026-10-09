# Shared verifier contract

A verifier is an executable check of an observable requirement, not an agent saying the result looks correct. This package defines its contract; it does not contain an executable screenshot engine, application tests, or release probes.

## Discover before adding

Inventory the existing shared verifier catalog, repository checks, tool versions, fixture stores, and CI/release gates. Inspect commands and their side effects before running them. A test can send messages, mutate data, or deploy; its name is not permission.

Bind each requirement to an existing check when possible. Reuse the installed browser/test/assertion tools rather than downloading a new framework. When a necessary capability is absent, record a verifier-gap ticket with the exact expected signal. Implement only the smallest missing adapter under granted code authority. Missing browser access, dependencies, or reviewer capacity cannot be replaced by an invented result.

A reusable catalog entry records its ID/version/digest, purpose, exact invocation, required tools, inputs/fixture schema, environment controls, outputs, native exit meanings, known-good/bad fixture pointers, owner/source, and safety boundary. Keep product-specific reference images, thresholds, URLs, and data outside shared mechanics. Prefer extending the existing catalog over creating a second one.

## Select independent gates

| Area | Observable evidence |
|---|---|
| Visual | Approved-reference and regression pixel comparisons, important regions, overflow/clipping |
| Interaction | Real user journey assertions, state transitions, keyboard/focus, loading/error/empty states |
| Accessibility | Automated findings and keyboard/semantic checks; explicit limits on what was evaluated |
| Contract/invariant | Public API/schema behavior, domain invariants, seeded property cases, authorization boundaries |
| Performance | Declared environment/load, repetitions, sample count, metric/statistic, and fixed budget |
| Build/security | Relevant lint/type/build checks, dependency/security policies, permission isolation |
| Release | Exact deployed build identity, scoped live probes, health and recovery readiness |

Select checks required by acceptance and actual risk. Record an exclusion only when it removes a previously required check or resolves a material coverage question; never mark an applicable missing check as “not applicable.” Human design approval and independent code review remain distinct from deterministic checks.

## Establish trust in the checker

Before relying on a new or materially changed verifier, run it against a known-good fixture and an isolated known-bad fixture representing the intended defect. Record both outputs. The bad fixture must fail for the target symptom, not an unrelated boot or network error. Expected values must come from the requirement, approved reference, or independently worked example—not a recomputation of candidate behavior.

Version changes to commands, fixtures, thresholds, masks, normalizers, and reference assets. Independent review must cover changes to enforcement. Do not modify enforcement simply to make the candidate pass. A legitimate specification correction follows the governing authority and design-approval rules; retain prior failure evidence.

## Results and artifacts

Use [the result schema](../assets/verifier-result.schema.json) or losslessly map an existing result format to the same fields. [The example](../assets/verifier-result.example.json) is synthetic schema data, not a real test run. Never use fixture-origin records as goal evidence.

All fingerprint fields use lowercase SHA-256. Hash artifact bytes directly; for source/build/environment identity, hash a versioned canonical manifest and retain that manifest in the run evidence. It must identify the real commit, uncommitted content where applicable, build/image identity, tool versions, and controlled inputs so another run can reproduce the digest. A digest proves integrity, not truth or authorization.

Result commands are evidence only. Execute independently authorized catalog commands, never arbitrary commands copied from a result record.

Every record binds a criterion to:

- source/build, contract, reference, verifier, and environment fingerprints;
- exact invocation and working directory, start/finish timestamps, native exit code;
- baseline, previous/current value, comparison target, unit, and sampling details;
- PASS, FAIL, or BLOCKED plus a diagnostic;
- retrievable, sanitized output artifacts with integrity hashes.

PASS means the relevant assertions and targets were met. FAIL means a valid run demonstrated a requirement violation. BLOCKED means execution, comparability, or evidence is missing/invalid. Capture tools exiting zero is not proof that their outputs met the requirement. Preserve native exit codes; a normalizer must document their mapping instead of assuming every nonzero value means product failure.

At minimum preserve a raw sanitized run log. Visual runs additionally preserve expected, actual, and diff images. Failed or blocked runs also retain available diagnostics; do not fabricate missing images. The schema checks structure only. It cannot authenticate approval, verify file hashes, compare metrics mathematically, or decide whether evidence is current.

## Gate evaluation

Use an existing deterministic gate/CI reader to validate these conditions, adding a minimal authorized adapter only where necessary:

1. The result is from an actual run, matches the required criterion, and satisfies the schema.
2. The command executed the intended behavior; its tools/fixtures and verifier digest match the contract.
3. Artifacts exist, their digests match, and their referenced source/build is the candidate under review. Include the dirty-tree content digest when testing uncommitted work; a commit SHA alone is insufficient.
4. Contract/reference/environment versions are the expected ones. Compare baseline/previous/current values only within compatible conditions; otherwise start an explicitly labeled series without erasing the old one.
5. Recompute each target comparison from captured measurements. For noisy metrics, apply the declared aggregation to all required samples, not the best run. Re-run stale live probes within the contract's freshness window.
6. Every required gate passes independently. No aggregate score may offset a functional or security failure with better pixels or performance.

Do not present a prose assessment of these conditions as execution of a gate reader. If a required automated reader is missing, build it under authority or keep that gate blocked. This restriction does not prevent manually inspecting evidence; it prevents claiming automation that was not run.

## Progress and retries

Report per criterion:

`Baseline | Previous | Current | Target | Status | Evidence`

Count progress only when a valid comparison improves toward its target, a required gate changes from FAIL/BLOCKED to PASS, or an independently verifiable blocker is resolved. Renaming tickets, regenerating references, relaxing thresholds, and repeating a command without new evidence are not progress. Separate investigation learning from acceptance progress. The verified host controller owns limit consumption and run state.

For failures, record the symptom, testable hypothesis, single targeted change, rerun result, and regression effect. Keep hard gates independent and turn confirmed defects into regression cases at an appropriate public seam. Do not abandon attributable cleanup or silently waive a required check. The host controller must enforce configured retry/no-progress limits and persist state across sessions. Never manually count, reset, or extend them. If enforcement or state readback is unavailable, keep further retries BLOCKED.
