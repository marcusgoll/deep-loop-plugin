# Portable helper usage and provisioning

The current package is a draft migration snapshot. The portable commands below replace the author-specific Windows installation paths in SKILL.md and its references. They invoke the same helper with the same acceptance and authority requirements; they do not waive prerequisites or approve execution.

From the repository root, inspect commands without installing:

```sh
python3 skills/deep-loop/scripts/deep_loop.py --help
```

For an existing, explicitly selected checkpoint:

```sh
python3 skills/deep-loop/scripts/deep_loop.py validate --path /path/to/checkpoint --stage review
python3 skills/deep-loop/scripts/deep_loop.py validate --path /path/to/checkpoint --stage ship
```

On Windows use `py -3` and an actual checkpoint path. For an installed skill, replace `skills/deep-loop/scripts/deep_loop.py` with its discovered installation path. Other documented helper commands use this same substitution; preserve their arguments and approval requirements. Do not assume the example author's account, drive or home directory exists.

## Supporting skills

This repository distributes the Deep Loop snapshot, not the separately maintained supporting skills. The public migration does not provide an installation source for those supporting skills. Full provisioning is currently limited to environments where the maintainer has supplied them; a public, self-contained dependency release is a separate follow-up. Do not copy credentials or private runtime/session directories to obtain them.

| Capability | Required separately supplied file | When needed |
|---|---|---|
| Bounded, hash-guarded installed-skill source reads | skill-optimization/scripts/update_package.py | The current SKILL.md requires this source-reading procedure |
| Package metadata check | .system/skill-creator/scripts/quick_validate.py | Full package verification |
| Bound contract validation | verification-contract/scripts/validate_contract.py | Contract binding/validation and full package verification |
| Selected specialist fixture | to-spec/SKILL.md | The package harness's selected specialist preflight |
| Pixel checks | Pillow Python package | Pixel/UI evidence and its test suites |

Deep Loop's helper resolves validator dependencies from DEEP_LOOP_SKILLS_ROOT when explicitly set; otherwise it tries the adjacent skills directory and the skills directory under CODEX_HOME (default ~/.codex). The harness's to-spec fixture separately looks under ~/.agents/skills/to-spec. The source-reader procedure uses the discovered skill-optimization installation path. Obtain these skills through your existing approved provisioning, not from an assumed path in this repo.

If a required dependency is unavailable, the affected source-reading, bound-contract or full-package-verification step is blocked. The maintainer's passing receipts establish checks in the recorded provisioned environment, not a successful clean-install experience for an unprovisioned public checkout. Do not report partial checks as the full 15-gate pass.

In a provisioned environment, the existing full-check entrypoint is:

```sh
python3 skills/deep-loop/scripts/verify_skill.py check --output /path/to/new-check-receipts
python3 skills/deep-loop/scripts/verify_skill.py check-summary --output /path/to/new-check-receipts
```

Keep receipts outside skills/deep-loop to avoid changing the package being checked. Review the recorded skips and environment limits. Running these fixture checks does not enroll an unattended worker, install the skill, or authorize delivery.
