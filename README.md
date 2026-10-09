# Deep Loop

Deep Loop carries authorized work through Understand → Contract → Execute → Prove → Deliver, with observable acceptance and resumable checkpoints.

This repository is being prepared as the public home of the new Codex skill. The old Claude Code plugin is preserved under [legacy/claude-code](legacy/claude-code/README.md); its original Git history is retained. Its version numbers and runtime hooks belong to that earlier implementation.

## Migration preview

This branch is a local preparation preview. The exact independently reviewed v0.5.6 skill bundle has been inserted. All 15 local package gates pass. The source snapshot has a passing independent review; the broader optimization task was interrupted without a final completion result. This is a verified migration candidate, not a released or installed skill. Publication and release approval remain pending.

The current-skill location is [`skills/deep-loop/`](skills/deep-loop/SKILL.md), containing `SKILL.md`, references, schemas, helper scripts and behavioral tests. The package version and SHA-256 file manifest are recorded in [`release-manifest.json`](release-manifest.json). This manifest identifies bytes; it does not establish unattended runtime acceptance.

## Package verification

Local verification passed 15 gates with 179 executed tests, 4 explicit skips, 14 pixel comparisons and 24 fixture preflights. See [verification details](docs/VERIFICATION.md), including dependencies and untested boundaries.

The helper suite uses Python. Pixel verification needs Pillow. The complete package check also resolves the installed skill-creator validator and verification-contract validator; a selected specialist fixture requires to-spec. These supporting skills are not bundled here. Optional specialists are not unconditional execution dependencies.

## Automation boundary

Deep Loop defines the execution and acceptance workflow. Scheduling, exclusive ownership, durable recovery and cumulative limits must be established by the execution host. A checkpoint validator or successful model response alone does not prove completed delivery.

The proposed unattended pilot uses GitHub Actions for execution ownership, native Codex for implementation, and Deep Loop for acceptance. This migration does not install or enroll that pilot, prove crash recovery, or authorize merge/deployment.

## Legacy compatibility

The legacy plugin files are preserved for inspection and a separately selected legacy release. Its SessionStart and Stop hooks are not activated by this new repository layout. Existing Claude installations should remain pinned to their known legacy revision until a separately verified compatibility path is provided.

## Licensing

The original repository [license](LICENSE) is retained. The current skill's bundled attribution/license files must be preserved when its reviewed package is inserted.
