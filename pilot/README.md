# Disposable pilot admission prerequisite

Locally tested prerequisite, not an enrolled unattended runner. Selected target: marcusgoll/deep-loop-plugin, GitHub-hosted Linux, OpenAI workload identity. No workflow, timer, model call, remote journal branch or live enrollment is installed.

`admission.py` charges full timeout allowances before launch. Fixed approved limits: 3 attempts, 1800 cumulative model seconds, 3600 cumulative active seconds, stop after 2 consecutive attempts without verified progress. Reservations never refund after interruption; conservative charging may stop earlier than measured usage. Missing journals cannot implicitly reinitialize. Duplicate run/attempt identities and unreconciled predecessors block launch.

`git_journal.py` appends the admission journal to a dedicated Git ref keyed by contract digest, using a non-force push and independent readback. Competing sibling commits cannot both fast-forward. Stale revisions, rewritten history, missing state and uncertain publication block launch. Only explicit enrollment creates an empty journal. Existing Deep Loop checkpoints retain source, verifier, task and session state; this minimal budget journal is not a second tracker.

## Trusted caller obligations

Keep modules and credentials outside the mutable candidate. The caller must authenticate approval, provider inactivity and new source/environment/contract-bound progress evidence. A fresh digest is not evidence of progress; finish() does not authenticate evidence or prove the predecessor stopped. Before launch, read back the reservation and enforce both timeouts on the whole process tree. Never give the model journal or delivery credentials.

Tests use an actual local bare Git remote. They do not prove GitHub durability, permissions or branch protection. Remote protection must prevent journal deletion/reset; missing enrolled state must block recovery. Remaining work: protected remote storage, approval binding, predecessor reconciliation, process timeout enforcement, candidate preservation, explicit-session recovery, independent review, delivery and automatic wakeup. No A01–A11 parent gate passes from these fixtures.

## Workload identity provisioning blocker

An OpenAI organization administrator must create a GitHub OIDC provider and a mapping to a selected API project/service account. None has been supplied or verified. Use issuer https://token.actions.githubusercontent.com with exact repository, ref and workflow_ref assertions; settle the reviewed execution workflow path before creating the mapping. Audience values must match exactly. Do not log raw tokens or use owner-wide wildcard trust.

The official guide documents SDK workload identity. Native Codex token/session compatibility still requires a bounded authenticated trial. No subscription credential is copied into Actions, no API-key fallback is configured and no paid call has run.

References: [OpenAI workload identity](https://developers.openai.com/api/docs/guides/workload-identity-federation/github-actions), [Git references](https://docs.github.com/en/rest/git/refs), [workflow triggers](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows).

Run from the repository root: `python3 -B -m unittest discover -s pilot -p 'test_*.py' -v`.
