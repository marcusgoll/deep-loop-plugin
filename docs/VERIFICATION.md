# Package verification

Candidate: Codex Deep Loop 0.6.1, 83 files. The release manifest records the verified installed-source hashes and the published file hashes. Thirty text files receive only CRLF-to-LF normalization for repository policy.

The full package check uses scripts/verify_skill.py check. On 2026-10-23, all 26 gates passed: 354 discovered tests, 351 executed and 3 opt-in browser skips; 14 pixel comparisons; 24 fixture preflights. The check ran against the normalized repository snapshot on Windows with Python 3.11. Supporting skills and Pillow remain separate prerequisites; see [provisioning](USAGE.md). Receipts remain in the maintainer local audit packet.

The legacy archive and root license remain unchanged from the refreshed repository baseline. The skill contains no controller runtime, controller service unit or controller tests. Its integration guide requires a separately provisioned app.

Package checks do not prove live model execution, Linux controller isolation, crash recovery, remote delivery, native device delivery or an unattended workflow. Browser capability trials remain opt-in. This update does not install the skill elsewhere, publish the controller, create a tag or release, merge, deploy or activate services.
