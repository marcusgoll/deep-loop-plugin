# Migration verification

Candidate: Codex Deep Loop 0.5.9, 44 files. The passing independent source review binds its exact file manifest. This public copy preserves those bytes without formatting adjustments; release-manifest.json records their hashes.

All 16 declared package gates passed against the reviewed source: 187 discovered tests, 183 executed, 4 skipped; 14 pixel comparisons; 24 fixture preflights. Public-copy checks must also pass before PR publication. Runtime: Python 3.11.3 and Pillow 10.2.0 on macOS. Full source/environment-bound receipts remain in the local audit packet.

The four skips are one Windows-junction safety case on non-Windows and three explicitly opt-in browser capability cases. No browser trial, Windows junction execution, physical device proof, remote model invocation, new PR or installed-runtime validation occurred in these package checks. Synthetic UI fixtures do not establish product/device delivery.

The full package-check entrypoint is scripts/verify_skill.py check. Its metadata gate requires the installed skill-creator quick validator; contract-related checks use verification-contract. A selected specialist fixture needs to-spec. Pixel checks require Pillow. The required installed-skill source-reading procedure also uses the separate skill-optimization reader. See [portable usage and provisioning](USAGE.md) for configured roots, exact required files and the current public-provisioning limitation. The dependencies used by the local check were separately hash-bound in its receipts; they are not vendored by this migration.

Every one of the 53 tracked legacy files from d68b8ff6cc7f231f7eab12751a88dcd78f36dac9 is preserved byte-for-byte under legacy/claude-code. Root license remains. Root legacy plugin metadata and hooks are absent; Git history is retained. Python syntax, JSON parsing, relative Markdown links and staged diff checks pass.

This proves the migration package under the recorded environment and scope. It does not prove the complete unattended outcome workflow, exclusive host ownership, cumulative resource accounting, restart reconciliation, authentication against forged receipts, native delivery or real-project applicability. The broader optimization task has no final completion result; its passing independent source review is the reviewed snapshot basis here. The original migration was merged in PR #2. This v0.5.9 update requires its own PR review; no tag, release or unattended pilot execution is implied.
