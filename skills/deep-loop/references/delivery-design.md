# Design approval and visual acceptance

## Separate exploration, intent, and proof

Exploration may be rough and disposable. Approval artifacts must be resolved enough to serve as targets. Pixel agreement proves conformity to those targets, not originality, usefulness, or artistic merit. Do not turn aesthetic taste into a fictitious numeric quality score.

Reuse an approved design system without making every screen identical. Preserve the chosen composition, typography, imagery, information hierarchy, and distinctive interaction details. When exploring a new direction, produce materially different alternatives—not the same card grid with different colors. Evaluate them within realistic surrounding navigation and content density. Do not reopen a settled direction merely to create variants.

## Two routine human gates

**Mockup approval:** Present the visual direction and a coherent batch of screens, layouts, responsive rules, defining assets, and critical states. Include any departures from supplied images. An approval covers only its explicit inventory; it is not blanket approval of unseen designs.

**Prototype approval:** Demonstrate connected journeys, navigation, keyboard/focus behavior, and relevant loading, empty, error, success, and disabled states. Show responsive behavior and meaningful motion. Identify simulated data and stubbed side effects. Approve an exact artifact revision, not a moving preview URL.

Prototypes may read realistic sanitized fixtures or permitted read-only data, but must not invoke real billing, messaging, destructive actions, or other live mutations. Build them in the already-authorized isolated lane. Prototype construction still needs source-edit authority. Do not ship throwaway prototype scaffolding as production code without implementation review and verification.

Each approval record needs:

| Field | Required content |
|---|---|
| Identity | Goal, batch, artifact revision, content hashes, preview/capture pointers |
| Coverage | Screen/state IDs, viewports, journeys, and responsive rules |
| Decision | Explicit owner approval/rejection and attributable source/timestamp |
| Adaptations | Permitted differences from supplied references; deferred design questions |
| Baselines | Approved reference assets and prototype frame hashes where applicable |

Changing any covered artifact requires impact analysis. Changes to appearance or user behavior outside the approved adaptations return to the relevant gate. Implementation-only changes preserving the approved experience need no new design approval. Never infer approval from silence, a generated note, or an unrelated “proceed.”

When asking, state one exact batch/revision and one question; then end the turn. A missing decision is WAITING_FOR_DESIGN, not rejected and not approved. The same parent resumes later.

## Two types of reference

**Design reference:** The approved image, ImageGen output, mockup, or prototype frame. Preserve the original. Record any approved crop, viewport interpretation, or responsive transformation as a derived asset with its own provenance.

**Browser regression baseline:** A browser capture traceable to the approved prototype batch, or a capture independently verified against its approved design target. Promotion requires passing fidelity evidence and independent review; the candidate screenshot cannot approve itself. This is an engineering gate, not a third routine human gate. If a visual adaptation changes the approved intent, return to design approval instead.

Existing baseline files are not approval evidence by their mere presence. Keep baseline-promotion permissions separate from implementation writes when the host supports that control.

## Pixel-diff protocol

1. Pin browser/version, OS or image digest, viewport, device-pixel ratio, zoom, installed font versions, locale, timezone, content/fixtures, seeded randomness, color scheme, and capture settings.
2. Wait for required fonts, images, data, and a defined stable UI state. Freeze time and incidental animation. Verify purposeful motion separately with controlled checkpoints and behavior assertions; do not permanently remove it just to obtain a clean screenshot.
3. Compare like-sized render regions. Record reference-to-viewport mapping before implementation. No silent resizing, stretching, warping, broad crops, or removal of meaningful content.
4. Use the existing screenshot/pixel comparator. Record pixel/color threshold, changed-pixel count/ratio limit, antialias treatment, and each region's mask policy separately. Calibrate platform noise with repeated unchanged captures and test sensitivity using known visual defects. Do not choose a permissive whole-page percentage by intuition.
5. Store expected, actual, and diff images with hashes, dimensions, viewport, state, and comparator version. Require important regions to pass individually so a small broken control cannot hide inside a large matching background.
6. If a generated reference cannot be compared directly, document the mismatch and obtain the necessary adapted design approval. A perceptual score or model's visual opinion cannot silently replace a required pixel gate.

Masks must be predeclared, narrowly scoped, justified, and shown in evidence. Never mask a required control, text, or known defect. Deterministic fixtures are preferable to masking variable product content.

No whole-page screenshot may stand in for functional DOM. Run interaction, overflow/clipping, focus order, touch/keyboard, and accessibility checks independently. Automated accessibility checks alone do not certify complete accessibility; expose any required human-only evaluation as a contract constraint rather than faking it.

## Release eligibility

All required screen/state/viewport entries need valid target provenance and current fidelity evidence. Reuse approved responsive rules where their coverage is explicit; otherwise the missing design is a blocker. No agent-generated baseline, unreviewed responsive extrapolation, or decorative similarity can close a coverage gap.
