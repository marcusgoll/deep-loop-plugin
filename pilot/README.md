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

## Private account qualification

`bootstrap_private_account.py` prints its plan by default. Explicit root `--apply` on Linux creates only the fixed locked `deep-loop-pilot` system account and private home/candidate directories. Existing account/group/state, symlinks, writable parents or POSIX ACLs block application. Partial failures preserve state for inspection; never blindly rerun or delete it. No credential, model invocation or recurring scheduler is created by bootstrap.

A separately authorized qualification applied this reviewed bootstrap on the private host. Independent readback verified locked password, no supplementary groups and private 0700 directories. Disposable native Codex sandbox tests under that account passed candidate writes, private direct/symlink deny-read and disabled-network controls. A transient systemd cgroup stopped a SIGTERM-resistant child. Reapplication was rejected. Raw receipts stay in the private audit packet.

These controls are qualification primitives, not an installed workflow or managed execution policy. Fresh ChatGPT device sign-in requires the account owner's consent; the shared Codex session is not copied or modified. After authentication, a reviewed immutable launch configuration must enforce these controls on every invocation. Durable ownership, cumulative runtime accounting, automatic wakeup, source/session recovery and trusted delivery still need implementation and end-to-end proof. No A01–A11 gate is complete.

## Launch and recovery plan

`private_launch.py` is a pure plan builder, not a controller or installed service. It rejects missing reservations, changed contracts, invalid identities, and allowances too small to include shutdown. Fresh and explicitly UUID-resumed executions use the same fixed permission profile, ignore user config/rules, disable hooks and keep model-command networking off. The selected profile follows the [native permission configuration](https://learn.chatgpt.com/docs/permissions).

The systemd plan selects the dedicated account, its login environment and the exact contract candidate. It disables automatic restart, kills the entire cgroup and reserves 5 seconds for shutdown plus 10 seconds for controller overhead inside the charged allowance. A controller must enforce that overhead deadline; the plan alone cannot bound a hung controller. Resume runs require the service working directory because the resume subcommand has no `--cd` option.

Before applying any plan, the trusted controller must authenticate the exact approved contract, read back its durable reservation, acquire a host-wide credential-stream lock, verify immutable launcher/config and canonical candidate paths, and verify the native effective policy. Reject candidate-supplied config, hooks, MCP and plugin extensions. Persist trusted session observations outside the candidate and authenticate UUID-to-contract binding before resume. Never use `--last` or reset the budget on recovery. `recovery_action()` requests reconciliation only after an exact owned unit is inactive/failed and its cgroup is empty; missing observations block. The caller must independently collect these observations. No new reservation is authorized by recovery.

Fresh device sign-in for the dedicated account has been verified privately. These plan tests do not prove managed configuration enforcement, session binding, credential serialization, durable host controller ownership, automatic wakeup or live model recovery. Those integrations and end-to-end evidence remain required before enrollment.

## Trusted controller core and native observations

`private_controller.py` connects explicit approval enrollment, the append-only journal, durable host-wide ownership, native submission and recovery. `TrustedStore` requires a canonical private directory and trusted nonwritable ancestors, validates file ownership/modes and rejects symlinks/hardlinks. Create `credential-stream.lock` once during explicit trusted setup; recovery never recreates a missing lock. Immutable JSON records are published without replacement and fsynced with their directory. Production retains root ownership; nonroot ownership is only for disposable tests.

The controller reads the exact immutable approved contract, qualifies the backend, charges and independently reads back admission, persists global launch intent, then submits once. A crash or uncertain response blocks later launches across contracts. A missing native invocation receipt requires explicit inspection; it never replays submission. A root-owned session binding is accepted only from the trusted native adapter, never candidate text. Resume requires that binding and the same contract. Reconciliation never submits: it requires the exact invocation plus inactive/failed and empty cgroup proof, finishes without refund, and releases global ownership only after journal persistence. Current reconciliation credits no progress; independent progress verification remains a delivery integration requirement. Two no-progress outcomes stop further attempts.

`systemd_observer.py` collects native properties with bounded `systemctl show` and kernel cgroup-v2 population evidence. Missing units, changed invocation/account/cgroup ownership, unexpected restart policy and unavailable population data block recovery. A released cgroup counts as empty only with the retained exact inactive/failed native invocation. Keep units retained until reconciliation; do not use `--collect` for live attempts. These observations do not authenticate Codex session events.

These modules provide orchestration and read-only host observation, not an installed controller. Production submission, effective-policy/candidate qualification and native session-event adapters must be integrated before launch. No callable default backend, public dispatch endpoint, scheduler, model call or outcome enrollment is added. The tests exercise uncertain submissions, durable intents, same-contract session recovery, missing lock, cross-contract exclusion, invocation drift and no-progress stop. Existing Git adapter tests separately prove local bare-Git persistence; fake controller backends are explicitly fixtures, not host evidence.
