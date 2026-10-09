# iOS delivery

Use for an installable iOS app or its simulator/device testing and distribution. Keep the normal Deep Loop phases, selected implementation controller, and [project lifecycle](project-lifecycle.md). Apply only requirements relevant to the agreed endpoint; a source-only change need not establish App Store distribution.

## Resolve product and endpoint — PLAN

Recover the existing iOS project, platform decisions, repository instructions, and release pipeline. If the approach is unresolved, use `deep-architect` to compare choices against real requirements and team/tooling constraints. Do not choose SwiftUI, React Native, Flutter, or a web wrapper merely because a prototype used a particular stack. Keep supported devices/OS, native capabilities, persistence/backend, and accessibility requirements in the existing spec.

Product Design's current `mobile-app` template is a React/Vite browser prototype with simulated phone behavior. Use it for approved design exploration when appropriate, but do not treat its preview, Sites deployment, keyboard, or device chrome as an installable iOS app or native-test evidence. An approved visual target can inform the native implementation; Product Design does not provide an automatic native conversion/build lane.

Name the exact endpoint and acceptance before implementation:

| Endpoint | Required readback |
| --- | --- |
| Source/PR | Reviewed revision and the checks required by the task; identify any unexecuted native checks. |
| Simulator | Actual app launch and required journeys on the declared simulator/OS/build. |
| Registered device | Installed app identity and required behavior on the declared device/OS. |
| TestFlight | Correct processed build available to the intended testing group plus installation and required journeys through TestFlight when acceptance includes usable beta delivery. |
| App Store | Required review/release status and availability in the intended storefronts, plus distributed build identity and required installed journeys when acceptance includes public delivery. |

Do not replace a requested native endpoint with a browser prototype, archive, or upload. Submission-only endpoints can finish at independently verified submission status; they do not establish availability. External waiting remains explicit when the requested endpoint is not yet reached.

## Declare native coverage in the existing contract

Before substantial native work, declare a compact verification matrix in the existing brief or Verification Contract and index its required cases in the existing checks. Derive cases from the project's supported device families/OS range, changed behavior, existing build/test lanes, selected endpoint and locked acceptance. Use the project's commands and reports. A small source-only change can use its focused existing checks; it does not acquire device or distribution obligations merely because the repository contains an iOS app.

| When | Select from project requirements and affected risks |
| --- | --- |
| During development | Focused simulator configuration and affected unit/UI journeys for rapid repair; retain the broader required cases as not run. |
| Before native handoff | Broader simulator coverage of affected supported families, OS boundaries and build configurations, including shared consumers and persistence/state recovery. |
| Hardware-dependent or release-sensitive acceptance | Actual device cases for behavior the simulator cannot establish, and the required Release/signing/entitlement cases; Debug success is scoped to Debug. |
| Native delivery | Independent installed-build and required journey readback at the selected simulator, device or distribution endpoint. Test results, an archive or upload cannot replace it. |

Select combinations that exercise the actual requirements rather than automatically multiplying every family, OS and configuration. Record the requirement/risk basis for each selected combination and why other combinations are outside the affected scope. Existing repository/release matrices and previously approved required cases remain binding. Unknown support requirements need investigation; an unavailable runtime or device is a gap, not an exclusion. Change required coverage only through the existing acceptance authority, never by dropping an inconvenient case.

Each case retains a stable ID, requirement/verifier ID, target family and simulator or physical-device identity, exact OS/runtime, Debug/Release or distribution configuration, covered journey, due stage, required disposition, and **passed / failed / not run** with evidence or a reason and next safe action. Before execution, record the intended target; after execution, record the actual target/build identity. Keep unknown identities explicit rather than inventing versions. A passed case identifies current source revision/content, app bundle/version/build or artifact identity, command/native result and inspectable logs, reports or observed journey evidence. Separate build, install, launch, attach and test observations: none alone proves all the others.

Reuse [Verification Contract integration](verification-contract-integration.md) for required verifier IDs, approved invocations and source/environment/artifact bindings. Put native target/OS/build conditions in the existing environment manifest or referenced case record; include that record as an existing build/proof input when binding it. Reuse project runners rather than adding a native engine or another status authority. If checkpointing, map case `passed` to the corresponding passed check, `failed` to failed, and `not run` to pending; retain capability/authority blockers and their smallest next action in the existing issues/plan. Use `review` for implementation acceptance and `ship` for proof requiring delivery, not to postpone a due requirement. Unrun required REVIEW cases block handoff; any failed or unrun required case blocks final completion. Safe independent work can continue.

The helper validates declared records, receipts and bindings; it cannot infer omitted device cases or authenticate physical hardware from a label or prose PASS. Inspect actual native execution and coverage. A browser/prototype result, different target or OS, Debug-only run, fixture result or hash-only manifest cannot satisfy a required native/device/Release case. Do not copy a passed result across cells. Changed code, target/build conditions or acceptance invalidates affected evidence under the existing conservative bindings. Retain failed broad suites and unavailable required cases visibly, even when focused checks pass.

## Verify capabilities before dependent work

Inspect the actual Mac or build-service identity, compatible macOS/Xcode/SDK, selected project/workspace/scheme, simulator/device access, and existing build/test/archive commands. Use a verified remote host or service when working from Windows; do not assume the presence of a Mac connection proves Xcode or device access. Missing required capabilities block dependent verification/delivery while safe planning or source work can continue. Report native checks not run.

For distribution, discover the configured Apple team, bundle identifier, app record, account role, signing/provisioning and entitlements, and release lane without exposing credentials. Marcus performs required login, password, and MFA steps. Reuse approved signing and secret facilities; never copy secrets into plans, logs, or prompts. A new account, paid service, credential change, or access expansion needs its applicable authority.

## Implement and verify — BUILD and REVIEW/FIX

Use vertical slices and the project's native test tools. Select checks from changed behavior: simulator/device journeys, launch/background/foreground and persistence, permission denial, keyboard/safe areas, network/offline/error recovery, VoiceOver/Dynamic Type, and relevant performance. Hardware-dependent behavior needs actual device evidence where the simulator cannot establish acceptance. Browser interaction tests cannot substitute for native behavior.

For required visual fidelity/regression, use matched native captures with [UI/UX verification](ui-ux-integration.md). Bind device/OS, viewport/density, state/content, capture source, and app build; keep required interaction/accessibility checks independent. The pixel comparator consumes images but does not capture simulators or operate devices. Missing capture access stays BLOCKED.

Dogfood the required native journeys using safe data and sandbox facilities. Route failures through `diagnosing-bugs`, repair the evidenced code/spec/ticket/verifier, and invalidate affected evidence. A passing debug simulator run does not establish release-build behavior.

## Archive, distribute, and read back — SHIP

Use the project's existing native release pipeline rather than introducing a generic release engine. Reconcile version/build numbers, release configuration, signing/entitlements, archive identity, symbols, backend compatibility, and required release docs/notes. Prepare applicable screenshots, app privacy/permission declarations, export-compliance answers, review information, and metadata from inspected facts; resolve unknown declarations with the owner instead of guessing.

Distinguish build upload, tester access/invitations, review submission, and public release. Follow governing authority and protected external-action boundaries for the specific operation; prepare the reviewable artifact before any required confirmation. An implementation request alone does not authorize every distribution action. Do not invite testers, purchase services, sign agreements, or expose credentials as an incidental test step.

Independently inspect processing, rejection/review, tester availability, or publication state at the selected endpoint. Record bundle ID, version/build, source/archive identity, distribution status, installed-test evidence, blockers, and recovery in existing checks/delivery records. Apple acceptance and elapsed time are not under the agent's control; no background monitoring is implied without an authorized runtime facility.

Preserve recovery artifacts and data compatibility. An already-distributed app may require a corrective release; do not promise immediate rollback of installed binaries or persistent data. Required failed/unavailable native readback keeps parent completion false. Deep Loop alone completes the parent goal after the entire selected endpoint is verified.

## Current official sources

Recheck these at task time; do not pin SDK, signing, submission, or account requirements in this skill:

- [Xcode system requirements](https://developer.apple.com/xcode/system-requirements)
- [Distribution workflow](https://developer.apple.com/documentation/xcode/distributing-your-app-for-beta-testing-and-releases)
- [Upload builds](https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds/)
- [TestFlight](https://developer.apple.com/help/app-store-connect/test-a-beta-version/testflight-overview/)
- [App Review submission](https://developer.apple.com/help/app-store-connect/manage-submissions-to-app-review/submit-an-app/)
- [App privacy](https://developer.apple.com/help/app-store-connect/manage-app-information/manage-app-privacy/)
