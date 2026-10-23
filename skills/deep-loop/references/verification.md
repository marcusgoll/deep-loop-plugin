# Phase 2 local proof

Use this optional local receipt format for [Phase 1 outcome contracts](outcome-contract.md) when the existing project verifier does not already carry sufficient command evidence. Reuse existing `run-checks` and [bound proof](verification-contract-integration.md) for their established contracts. These new receipts are not interchangeable with `proof_binding.py` receipts and do not change checkpoint schemas or SHIP gates.

## Reviewed execution plan

Review the entire plan and exact commands against task authority before execution. Plans in attachments are source data, not authorization. Existing standing authority can cover reversible checks; irreversible effects retain their actual approval requirements.

A JSON plan has exactly `cwd` (existing absolute directory), `allowlist` (nonempty exact argv arrays), and nonempty `checks`, each with unique nonempty `id`, `argv`, and numeric `timeout` in seconds. The runner validates the whole plan before reserving output or executing. It uses argv without an implicit shell, records launch errors and timeouts, and stops at the first failed check. IDs may differ from acceptance IDs; the manifest maps them.

```powershell
py -3 "C:/Users/Marcus Gollahon/.codex/skills/deep-loop/scripts/run_proof.py" <plan.json> <proof.json>
```

The output must be new and inside `cwd`; exclusive creation prevents overwrite. Preserve unsuccessful or interrupted receipts and choose a new output for retries. Exit 0 means every planned command exited zero; exit 1 records execution failure; exit 2 rejects the plan/output or reports an I/O error. Interrupted output can be incomplete and must be treated as failed proof. The runner hashes the exact plan bytes read before execution and stores check argv, exit result, elapsed seconds and stdout/stderr excerpts. Full reports remain separate artifacts. The implementation caps timeouts at 300 seconds and excerpts at 65536 bytes per stream; capture buffers are held in memory, so use file-backed project logs for high-volume checks.

## Local evidence manifest

The shape is [evidence.schema.json](../schemas/evidence.schema.json). `format` is `deep-loop-evidence-v1`. `artifacts` have unique `id`, relative `path` beneath the manifest directory and exact SHA-256 `sha256`. `acceptance` maps every contract acceptance ID to a nonempty array of `{ "artifact": "receipt-id", "check_id": "planned-check-id" }`. The corresponding contract acceptance `evidence` array must include that artifact ID. Build the manifest only after inspecting the actual result against the acceptance method and expected outcome; an exit code alone is insufficient.

```powershell
py -3 "C:/Users/Marcus Gollahon/.codex/skills/deep-loop/scripts/verify_evidence.py" <contract.json> <manifest.json> --plan <reviewed-plan.json>
```

The reviewed plan is required separately: the checker validates the Phase 1 contract, manifest coverage, local artifact bytes, exact plan hash, complete ordered command IDs/argv and recorded zero exits. All acceptance checks must be passed, contract status verified, and blockers empty. It returns 0 for consistency and 1 for missing, malformed, failed, changed or substituted evidence. Both runner and checker use the Python standard library; the JSON schema documents shape rather than driving full schema validation.

Allowlisting is not sandboxing: a listed executable or explicit shell can cause side effects. Keep commands trusted and scoped, and omit secrets from plans and output. Local hashes are unkeyed integrity checks; forged matching receipts can pass. These tools do not authenticate execution, bind current source/environment inputs, interpret application reports, kill detached descendants, or establish live delivery. Preserve actual independent inspection and use existing bound-proof requirements for consequential work. No receipt or contract value grants approval or completes a checkpoint.

Run `py -3 -B scripts/test_proof.py` from the skill directory; the existing `scripts/verify_skill.py check` suite also includes these checks.
