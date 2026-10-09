# Disposable pilot admission prerequisite

Locally tested prerequisite, not an enrolled unattended runner. Public project: marcusgoll/deep-loop-plugin. Execution is selected for a dedicated trusted private homelab lane using ChatGPT-managed Codex Pro authentication; GitHub Actions handles verification and delivery. The public repository is not a Codex credential host. No workflow, timer, model call, remote journal branch or live enrollment is installed.

`admission.py` charges full timeout allowances before launch. Fixed approved limits: 3 attempts, 1800 cumulative model seconds, 3600 cumulative active seconds, stop after 2 consecutive attempts without verified progress. Reservations never refund after interruption; conservative charging may stop earlier than measured usage. Missing journals cannot implicitly reinitialize. Duplicate run/attempt identities and unreconciled predecessors block launch.

`git_journal.py` appends the admission journal to a dedicated Git ref keyed by contract digest, using a non-force push and independent readback. Competing sibling commits cannot both fast-forward. Stale revisions, rewritten history, missing state and uncertain publication block launch. Only explicit enrollment creates an empty journal. Existing Deep Loop checkpoints retain source, verifier, task and session state; this minimal budget journal is not a second tracker.

## Trusted caller obligations

Keep modules and credentials outside the mutable candidate. The caller must authenticate approval, provider inactivity and new source/environment/contract-bound progress evidence. A fresh digest is not evidence of progress; finish() does not authenticate evidence or prove the predecessor stopped. Before launch, read back the reservation and enforce both timeouts on the whole process tree. Never give the model journal or delivery credentials.

Tests use an actual local bare Git remote. They do not prove GitHub durability, permissions or branch protection. Remote protection must prevent journal deletion/reset; missing enrolled state must block recovery. Remaining work: protected remote storage, approval binding, predecessor reconciliation, process timeout enforcement, candidate preservation, explicit-session recovery, independent review, delivery and automatic wakeup. No A01–A11 parent gate passes from these fixtures.

## Private Codex Pro execution

The current homelab CLI reports ChatGPT login. This identifies its authentication method, not its plan tier, worker isolation, remaining quota or pilot enrollment. Use a dedicated trusted private execution lane with serialized Codex-managed credentials. Keep credentials outside source, journal and public Actions jobs; let native Codex own token refresh. Do not invent a refresh service or export the shared host credential cache to the public repository.

OpenAI documents ChatGPT subscription access and headless sign-in. Its advanced account-auth CI guide applies to trusted private automation and explicitly excludes public/open-source repositories. Native execution on private infrastructure must be reviewed and isolated before enrollment. API workload identity is no longer the selected pilot authentication; no API organization/project/service account is required for this selected route.

Public Actions jobs must not acquire the Pro credential or become a command gateway to the private host. The private host reconciles only explicitly enrolled immutable contracts. Required GitHub verification and trusted delivery remain separately scoped, with exact-head proof. Scheduling/ownership, private candidate isolation, process limits, preservation, recovery and live endpoint acceptance remain unverified.

References: [Codex authentication](https://learn.chatgpt.com/docs/auth), [private account-auth CI](https://learn.chatgpt.com/docs/auth/ci-cd-auth), [Git references](https://docs.github.com/en/rest/git/refs).

Run from the repository root: `python3 -B -m unittest discover -s pilot -p 'test_*.py' -v`.
