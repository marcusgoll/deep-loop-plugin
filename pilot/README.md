# Disposable pilot admission prerequisite

Locally tested prerequisite, not an enrolled unattended runner. Public project: marcusgoll/deep-loop-plugin. Execution is selected for a dedicated trusted private homelab lane using ChatGPT-managed Codex Pro authentication; GitHub Actions handles verification and delivery. The public repository is not a Codex credential host. Read-only hosted verification and disabled private worker units are installed. No model call or live enrollment has occurred.

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

Before applying any plan, the trusted controller must authenticate the exact approved contract, read back its durable reservation, acquire a host-wide credential-stream lock, verify immutable launcher/config and canonical candidate paths, and verify the native effective policy. Reject candidate-supplied config, hooks, MCP and plugin extensions. Persist trusted session observations outside the candidate and authenticate UUID-to-contract binding before resume. Never use `--last` or reset the budget on recovery. `recovery_action()` requests reconciliation only after an exact owned execution has ended and its cgroup is empty; missing observations block. The caller must independently collect these observations. No new reservation is authorized by recovery.

Fresh device sign-in for the dedicated account has been verified privately. These plan tests do not prove managed configuration enforcement, session binding, credential serialization, durable host controller ownership, automatic wakeup or live model recovery. Those integrations and end-to-end evidence remain required before enrollment.

## Trusted controller core and native observations

`private_controller.py` connects explicit approval enrollment, the append-only journal, durable host-wide ownership, native submission and recovery. `TrustedStore` requires a canonical private directory and trusted nonwritable ancestors, validates file ownership/modes and rejects symlinks/hardlinks. Create `credential-stream.lock` once during explicit trusted setup; recovery never recreates a missing lock. Immutable JSON records are published without replacement and fsynced with their directory. Production retains root ownership; nonroot ownership is only for disposable tests.

The controller reads the exact immutable approved contract, qualifies the backend, charges and independently reads back admission, persists global launch intent, then submits once. A crash or uncertain response blocks later launches across contracts. A missing invocation receipt can be recovered only from an existing native unit with protected captures, the exact plan description and verified native ownership. Missing or unloaded units remain blocked; recovery never replays submission. A root-owned session binding is accepted only from the trusted native adapter, never candidate text. Resume requires that binding and the same contract. Reconciliation never submits: it requires the exact invocation plus ended execution and empty cgroup proof, finishes without refund, and releases global ownership only after journal persistence. Reconciliation accepts progress only from an explicitly supplied trusted verifier after native ended-execution and empty-cgroup proof. Without that verifier it credits no progress. Two no-progress outcomes stop further attempts.

`systemd_observer.py` collects native properties with bounded `systemctl show` and kernel cgroup-v2 population evidence. Missing units, changed invocation/account/cgroup ownership, unexpected restart policy and unavailable population data block recovery. A released cgroup counts as empty only with the retained exact ended native invocation. Successful units use RemainAfterExit=yes; native active/exited state with MainPID=0 and an empty cgroup proves ended execution without losing invocation identity. Running or populated units cannot reconcile. Keep units retained until reconciliation; do not use `--collect` for live attempts. These observations do not authenticate Codex session events.

These modules provide orchestration and read-only host observation, not an installed controller. Production submission, effective-policy/candidate qualification and native session-event adapters must be integrated before launch. No callable default backend, public dispatch endpoint, scheduler, model call or outcome enrollment is added. The tests exercise uncertain submissions, durable intents, same-contract session recovery, missing lock, cross-contract exclusion, invocation drift and no-progress stop. Existing Git adapter tests separately prove local bare-Git persistence; fake controller backends are explicitly fixtures, not host evidence.

`bootstrap_controller.py` is plan-only by default. Explicit reviewed root Linux `--apply` creates the fixed protected control directory, one credential-stream lock, a local bare Git journal and a separate journal workspace. It installs only the five trusted prerequisite modules, hash-verifies them, and persists the installation receipt. Existing or partial state and unsafe parents block reapplication; preserve failures for inspection. No contract approval, journal ref, submission adapter, timer or model invocation is installed. Local storage remains tied to this host: off-host backup/recovery protection is a separate acceptance obligation.

## Native submission and session capture adapter

`native_backend.py` implements private native submission behind the controller. It requires root execution, exact protected approval, a canonical root-owned binary whose SHA-256 matches the frozen contract, the dedicated account/candidate, no candidate `.git`/`.codex`/hooks/symlinks/aliased files, no unexpected system configuration and no existing private-account process. A separately produced protected qualification receipt must exactly match the executor, permission profile, candidate and no-model checks. The adapter does not produce its own qualification evidence.

Submission consumes its matching in-memory qualification once, requires the persisted launch intent, creates protected prompt/output files without replacement and invokes the pinned underlying native binary directly through systemd. Prompt text is stdin data, never an argument or shell program. The unit uses the plan's account, timeouts and cgroup policy, bounded file size, fixed system slice and retained invocation. No shared daemon or wrapper/package lookup is used. Uncertain submit is never retried. Recovery can adopt its existing exact native invocation only through protected captures, plan identity and native ownership proof. No default CLI dispatch endpoint is provided.

`native_session.py` validates bounded native JSONL captures. Only a top-level `thread.started` event with an exact canonical UUID can establish a session; nested tool output and prose are ignored. Conflicting UUIDs, unknown session schema and malformed stopped captures block binding. The backend reads captures only after exact native ended-execution/empty-cgroup proof. These parsing rules do not authenticate arbitrary input: provenance comes from the protected capture of the pinned native unit. Production native-policy and systemd I/O qualification remain pending, as do boot/crash recovery integration, automatic wakeup and trusted delivery.

No-model host probes verified protected systemd stdin/stdout, dedicated HOME/cwd/UID, retained successful invocation with MainPID=0, private direct/symlink denial, host-parent descriptor and memory denial, network denial, and effective disabled capability flags. Apps, browser/computer actions, plugins, additional agents, child goals, dependency installers and web search are disabled for this local writer lane. These probes do not establish a live model outcome, native session capture during inference, automatic wakeup or delivery. Fresh/resumed commands and cumulative reservations use the same restrictions.

The writer command also pins `forced_login_method="chatgpt"` and the OpenAI provider. Its service removes API-key, alternate Codex-home/base-URL and Node option environment inputs while retaining the dedicated login environment. Qualification verifies the private account currently reports ChatGPT authentication; Login status establishes the stored authentication method, not token freshness or subscription entitlement. Native authentication failures block execution; there is no API fallback. No API organization, key or refresh broker is provisioned.


## Disposable artifact verification

`artifact_verifier.py` independently reads the stopped candidate through bounded,
fd-relative reads. The frozen contract supplies all baseline file hashes and one
permitted artifact path with its exact expected SHA-256. Missing, additional or
changed files fail acceptance; symlinks, hardlinks, foreign ownership and private
configuration paths block verification. The verifier runs no candidate code.
A passing semantic receipt binds the contract and resulting file hashes, without
timestamps or invocation IDs. The controller persists it outside the candidate
before journal completion. Repeated identical output counts as no progress;
a crash after journal completion recovers without repeating verification or
refunding reservations. This narrowly verifies the disposable artifact, not a
general repository build, GitHub delivery or unattended end-to-end execution.


## Explicit wakeup transition

`private_wakeup.tick` reads one protected enabled-outcome selection and its exact
immutable approval. No selection means no work. It reuses controller ownership
and the append-only journal rather than creating another task tracker. A wakeup
with an owner reconciles only; a later wakeup may resume the protected previous
session with fixed 600 model seconds and 1200 active seconds charged in advance.
Two consecutive no-progress outcomes or three attempts stop dispatch. Exact
artifact acceptance stops at the trusted-delivery boundary. Missing owner or
session provenance blocks; it never silently starts a replacement task.

This transition is not an installed timer. Service deadlines, host promotion,
boot recovery and the trusted delivery adapter still require integration and
proof. An absent or unloaded native unit cannot establish ended execution.


## Protected versioned promotion

`promote_controller.py` prints a manifest by default. Explicit root Linux apply
requires its externally reviewed manifest digest and an inactive, unenrolled
pilot. It stages the nine controller/adapter/verifier/wakeup modules in a new
hash-named protected bundle, preserves the original modules and journal, and
verifies immutable files and durable receipt readback. Existing or partial
bundles block reapplication. It selects no runtime, installs no timer and creates
no approval or model call. The trusted launcher and staged source must themselves
be externally verified before invocation.

The reviewed nine-module bundle has been privately staged and hash/mode/readback
verified. A literal Python no-model native-unit probe verified adoption of the
same retained invocation after a lost submit response, without a second dispatch.
This establishes an existing-unit recovery primitive, not Codex inference,
boot recovery, an installed scheduler or GitHub delivery.


## Bounded private wakeup jobs

`private_worker.py` performs one transition per systemd invocation. Generated
units pin its immutable bundle, use 45 seconds of runtime plus 5-second startup
and shutdown limits, disable service restart, and wake every 30 seconds. The
worker authenticates its native invocation and reads back the typed native
timeout values before work. It stops its timer on faults and terminal states.
An abruptly interrupted worker can be inspected by the next wakeup, using the
same protected owner, journal and session rather than a new enrollment.

`worker_window.py` never creates missing state on recovery. Its explicit
approve-and-run importer requires the exact approved contract and a separately
stated `worker_wall_seconds=3600`. This additional conservative lifetime counts
waits and sleeps; it does not change D013 cumulative reservation accounting.
Changed boot identity, missing state or backward clock observations block.
Wakeups with 60 seconds or less remaining stop; new reservations require 1200
seconds remaining. The native adapter rechecks this after qualification and
capture preparation, immediately before dispatch, so a separate model cgroup
cannot outlive the remaining window through a delayed launch.

Host qualification found systemd 255 cannot mutate the runtime limit of an
already running service. The implementation therefore uses fixed short jobs.
A no-model native probe verified typed timeout readback and actual static timeout
termination. The reviewed twelve-module worker bundle and generated service/timer are now
installed privately. Native timeout values and immutable file hashes were
verified. The timer remains disabled and inactive, with no enabled outcome or
model call. The prior bundle is preserved.


An empty-queue timer qualification verified a native trigger followed by failed
enrollment condition, zero worker processes and no invocation identity. The timer
was stopped afterward and remains disabled. This proves refusal without an
enrolled outcome; it does not prove an enrolled execution or interruption run.

`.github/workflows/pilot-verification.yml` provides fresh GitHub-hosted Python
verification with read-only permissions, pinned actions and no retained checkout
credentials. It has no private-host command gateway or model authentication.
Repository settings currently disallow Actions-created PRs; trusted delivery
must account for this without assuming a write-capable workflow or changing
that setting. No delivery adapter is yet installed.


## Trusted delivery adapter

`trusted_delivery.py` accepts only independent artifact evidence from a stopped
writer with released ownership. It exports one bounded artifact, creates
content-addressed Git objects, and binds the draft PR to the frozen source,
repository, publisher and exact head. Protected intent records prevent blind
replay of uncertain branch or PR creation. Exact hosted check and workflow-run
readback is required before delivery completes. No merge or deployment is
provided.

`github_transport.py` uses the existing private publisher authentication through
a finite set of GitHub routes. Private read-only preflight verified the publisher
and repository identities. It does not establish write authorization or a live
publication. The final approve-and-run contract must explicitly include this
private publisher method and the additional 3600-second worker wall limit.

The source has 89 passing local tests, including uncertain-write adoption,
changed candidate rejection and exact-head delivery checks. Live Pro inference,
boot recovery and disposable delivery remain unverified.

`install_worker_units.py --previous-digest` permits a disabled, unenrolled
upgrade only from matching protected unit authority. It preserves the exact old
configuration, validates the replacement, fsyncs it and checks inactive/disabled
readback. Partial or changed installations require inspection. It never starts
or enables the timer. Other trusted root installers must respect the same
installation lock; filesystem replacement does not provide compare-and-swap.


## Contract-bound qualification preparation

`qualification_plan.py` derives sandbox and feature-inspection commands from
the exact reserved native launch plan. It binds the candidate, executor and
permission digest and permits only the fixed disposable probe path. It starts
no process and creates no qualification receipt. The producer must verify the
pinned executable and probe bytes, set the dedicated account and exact candidate
working directory, reject unexpected configuration, inspect actual results and
clean up probe files before publishing protected evidence.

A private no-model grammar preflight confirmed all thirteen generated feature
disables resolve to false. This does not prove the candidate sandbox or managed
configuration for an enrolled run. Qualification production remains pending.

The sandbox/features grammar lacks execution's ignore-config flags. Command success alone cannot prove equivalent policy loading. The
producer must establish absence of user, ancestor-project, managed and rules
configuration and validate effective configuration independently.

`qualification_environment.py` verifies the pinned executable, dedicated
identity, canonical private directories, bounded candidate objects, absence of
configuration/rules and private-process inactivity. `qualification_probe.py`
prepares literal probe scripts and validates exact observed denials, including
both a sentinel descriptor and the parent's capture descriptor. These helpers
do not start probes or publish qualification authority.

Sandbox and feature inspection reject `--strict-config`. Strict validation now
uses a separate app-server startup with empty input, restricted networking and
positive/unknown-field negative controls. Native preflight proved clean success
and explicit unknown-field rejection. The full producer subsequently passed a disposable no-model fixture on the
private host. Any successful-command diagnostic also blocks
qualification.
Probe and wrapper Python use isolated mode (`-I`) to prevent candidate module
imports before sandboxing. The root producer keeps immutable intent on an
uncertain submission and requires retained native identity and stopped-process
proof before reading results. The supported parser path and PID namespace correction passed independent
review. Protected receipt readback verified the completed no-model fixture.

The current suite passes 107 tests. Host qualification proved candidate writes,
private direct/symlink denial, isolated parent PID namespace, retained parent
targets, descriptor/capture/memory denial, network denial, strict positive and
negative configuration controls, and exact I/O. The candidate was empty after
cleanup; the protected receipt is root-owned 0600. No model request or enrollment
occurred. Qualification must be repeated for the final frozen outcome.

Parent `ENOENT` is accepted only with independently retained target existence
and a different child PID namespace. Missing paths alone remain insufficient.
Failed diagnostic fixtures and their native identities were preserved.


For an explicitly frozen `resume_verification` contract, the disposable worker
uses `ResumeVerifier`: the first stopped invocation must produce only the exact
temporary checkpoint. Its protected observation counts as no progress and keeps
the charged budget. Final acceptance requires a distinct native invocation,
explicitly requested and observed with the same canonical session UUID, the
checkpoint removed, and the exact final artifact. The protected native receipts
and acceptance are re-read before every delivery transition; completion includes
the resume-proof digest. Contracts without this field retain artifact-only
acceptance. These tests use fixture backends and do not establish live inference
or native recovery. Preparation adds no enrollment or timer activation.
