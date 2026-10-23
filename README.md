# Deep Loop

Deep Loop carries authorized work through Understand → Contract → Execute → Prove → Deliver, with observable acceptance and resumable checkpoints.

This repository is being prepared as the public home of the new Codex skill. The old Claude Code plugin is preserved under [legacy/claude-code](legacy/claude-code/README.md); its original Git history is retained. Its version numbers and runtime hooks belong to that earlier implementation.

## Current package

This repository contains the v0.6.1 Codex skill snapshot, synchronized from the verified local installation. It includes the current checkpoint, outcome-contract, local coordination, proof and fixture helpers. The separate Deep Loop Controller app is not bundled or installed by this skill.

The current-skill location is [`skills/deep-loop/`](skills/deep-loop/SKILL.md), containing `SKILL.md`, references, schemas, helper scripts and behavioral tests. The package version and SHA-256 file manifest are recorded in [`release-manifest.json`](release-manifest.json). This manifest identifies bytes; it does not establish unattended runtime acceptance.

## Package verification

See [verification details](docs/VERIFICATION.md) for current package results and untested boundaries. The release manifest records installed-source hashes and repository hashes. Packaging changes only normalize CRLF line endings to LF.

The helper suite uses Python. Pixel verification needs Pillow. Required source reading uses the separate skill-optimization reader. Full package checks also need the skill-creator validator, verification-contract validator and selected to-spec fixture. These supporting skills are not bundled or publicly distributed by this migration. See [portable usage and provisioning](docs/USAGE.md); missing prerequisites remain blocking. Optional specialists are not unconditional execution dependencies.

## Portable usage

From a checkout, inspect the helper without installing or promoting the skill:

```sh
python3 skills/deep-loop/scripts/deep_loop.py --help
```

On Windows, use `py -3` in place of `python3`. Replace personal installed-path examples in the imported skill/reference documents with the actual helper path; [portable usage](docs/USAGE.md) supplies equivalent checkpoint commands and dependency-resolution details.

## Automation boundary

Deep Loop defines the execution and acceptance workflow. Scheduling, exclusive ownership, durable recovery and cumulative limits must be established by the execution host. A checkpoint validator or successful model response alone does not prove completed delivery.

The optional controller integration points to a separate app. The current app remains local and requires separate provisioning. See [controller app use](skills/deep-loop/references/controller-execution.md). This repository does not distribute that app or activate a service. Live controller isolation, recovery and delivery need separate runtime proof.

## Legacy compatibility

The legacy plugin files are preserved for inspection and a separately selected legacy release. Its SessionStart and Stop hooks are not activated by this new repository layout. Existing Claude installations should remain pinned to their known legacy revision until a separately verified compatibility path is provided.

## Licensing

The original repository [license](LICENSE) is retained. The current skill's bundled [attribution license](skills/deep-loop/LICENSE-wayfinder) is preserved alongside its source.
