# Phase 5 local verification boundary

The optional coordinator's `verify` action now rejects old `verified:` flags. It requires the current lease generation, a distinct reviewer label, a signed verifier capability, a Phase 1 contract, a Phase 2 evidence manifest and the separately reviewed proof plan. Existing checkpoint, bound-proof, independent review and SHIP requirements still apply.

## Issue a scoped capability

`worker_identity.issue(secret, worker, role, job, generation=N, bindings=HASHES)` returns an HMAC-SHA256 capability with a finite expiry. `bindings` contains exact `contract_sha256`, `manifest_sha256`, and `plan_sha256` values. The issuer must independently inspect and approve these artifacts for the named job/generation before signing. Do not sign hashes merely because a worker supplied them.

The coordinator reads `DEEP_LOOP_VERIFIER_SECRET` from its own environment. Provision a high-entropy secret of at least 32 bytes out of band; no key is generated, installed or persisted by this skill. Keep the signing secret exclusively with the trusted issuer/coordinator. Do not expose it to builders, untrusted executables, shared workspaces, repositories, logs or handoffs. A worker holding the secret can mint any capability. Run verification through that trusted controller rather than giving every worker the signing environment. The API accepts raw bytes; the coordinator encodes its environment value as UTF-8, so issuer and verifier must use identical bytes. Synthetic test keys are not production secrets.

Capabilities are short-lived bearer credentials tied to job, role, reviewer, generation and exact proof inputs. Keep them out of durable event logs and ordinary command history; the CLI accepts one transiently but logs only hashes and the reviewer label. The helper supplies no issuer service, revocation registry or process identity. Key rotation invalidates outstanding capabilities but is owner-controlled work outside this update.

## Validate evidence and record review

```powershell
py -3 "C:/Users/Marcus Gollahon/.codex/skills/deep-loop/scripts/coordinator.py" <coordinator.db> verify --job ID --worker REVIEWER --token N --capability CAP --contract <contract.json> --manifest <manifest.json> --proof-plan <reviewed-plan.json>
```

The coordinator reuses `verify_evidence.verify`: it checks full contract shape, acceptance coverage, declared artifact hashes, exact reviewed-plan bytes and complete recorded successful command IDs/argv. `trusted_verifier.validate` hashes the contract/manifest/plan and rejects observed input drift. Capability verification must match those exact hashes, the current generation, named job, verifier role and reviewer label; the builder label cannot review its own submission. Verification uses actual wall-clock time and rejects `--now` overrides. It records manifest hash and input bindings with the review event; it never stores the capability or signing secret. Existing leased/awaiting states retain their generation; no database migration is required. Old callers must provide signed checked evidence before promotion.

This is local integrity verification, not authenticated command execution or independently attested acceptance. A matching self-reported receipt can still be fabricated. Key holders, database writers or an attacker controlling the trusted controller can forge state. File identities are observations rather than a locked snapshot; inspect current source/environment and applicable bound proof before consequential decisions. Administrative `proven` neither grants authority nor establishes live delivery. No real signing secret or live controller is provisioned or tested by installation.

## Reserve a workspace

`workspace_manager.py ROOT JOB` atomically creates a fresh job directory and refuses any existing path. Job names use ASCII letters/digits, underscore and hyphen; path escapes and Windows device names are rejected before root creation. Preserve existing directories on refusal. The selected root resolves to its actual filesystem target; verify that target/ownership before invoking the tool.

Reservation gives only an exclusive directory name. It creates no Git worktree, OS sandbox, independent account or enforced filesystem isolation. Windows inherits directory ACLs; a mode argument is not Windows permission separation. Keep actual isolation and dispatch with the selected controller. This phase adds no unattended worker launch or GitHub mutation integration.

Run `py -3 -B scripts/test_trust.py`; the existing package check suite includes these tests. Real-key provisioning, live dispatch, multi-host and production acceptance remain unverified.
