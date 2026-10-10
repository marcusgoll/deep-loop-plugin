"""Trusted controller orchestration; adapters supply authenticated host evidence.

There is no default enrollment, model dispatch, timer, or adapter. Production
state must be root-owned and outside the candidate. Do not import this module
from model-controlled code or accept its calls through a public workflow.
"""
import contextlib
import fcntl
import json
import os
from pathlib import Path
import stat
import tempfile

from admission import digest, finish, initialize, reserve
from authority import require_active
from private_launch import launch_plan, recovery_action


class TrustedStore:
    """Private files and a host-wide advisory lock, with fsync before return.

    The owner_uid argument supports unprivileged disposable fixtures only.
    Production callers must retain its root default and protect all ancestors.
    """
    def __init__(self, root, owner_uid=0):
        self.root = Path(root)
        self.owner_uid = owner_uid
        if not self.root.is_absolute() or self.root.resolve() != self.root:
            raise ValueError('Canonical absolute state path required')
        for path in (self.root, *self.root.parents):
            info = path.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid not in {0, owner_uid}:
                raise ValueError('Untrusted state parent')
            # /tmp is permitted only in nonroot disposable fixtures.
            if info.st_mode & 0o022 and not (owner_uid != 0 and path == Path('/tmp')):
                raise ValueError('Writable state parent')
        info = self.root.lstat()
        if info.st_uid != owner_uid or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError('Private state directory required')

    def _path(self, name):
        if not isinstance(name, str) or not name or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-.' for c in name):
            raise ValueError('Invalid state filename')
        if name in {'.', '..'}:
            raise ValueError('Invalid state filename')
        return self.root/name

    def _open(self, name, flags):
        fd = os.open(self._path(name), flags | os.O_NOFOLLOW, 0o600)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != self.owner_uid or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1:
            os.close(fd)
            raise ValueError('Untrusted state file')
        return fd

    def _sync(self):
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    @contextlib.contextmanager
    def lock(self):
        fd = self._open('credential-stream.lock', os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
        finally:
            os.close(fd)

    def read(self, name):
        fd = self._open(name, os.O_RDONLY)
        with os.fdopen(fd) as stream:
            return json.load(stream)

    def create(self, name, value):
        data = json.dumps(value, sort_keys=True, allow_nan=False).encode() + b'\n'
        fd, temporary = tempfile.mkstemp(prefix='pending-', dir=self.root)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            # link is an atomic no-overwrite publication; never replace authority.
            os.link(temporary, self._path(name), follow_symlinks=False)
            os.unlink(temporary)
            self._sync()
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def remove(self, name):
        # Validate existing authority before unlinking it.
        self.read(name)
        self._path(name).unlink()
        self._sync()


class PrivateController:
    """One host-wide credential stream; an uncertain submit is never replayed.

    backend qualifies effective policy/candidate/config, submits a native unit,
    observes its exact invocation/cgroup, and authenticates a session observation.
    Journal and backend are trusted implementations, not candidate callbacks.
    """
    def __init__(self, store, journal, backend, verifier=None, workflow_gate=None):
        self.store, self.journal, self.backend = store, journal, backend
        self.verifier = verifier
        self.workflow_gate = workflow_gate
        self.contract_digest = journal.contract_digest

    def _historical_contract(self):
        record = self.store.read(self.contract_digest + '.approval.json')
        if (set(record) != {'contract', 'approval_ref'} or
                digest(record['contract']) != self.contract_digest or
                not isinstance(record['approval_ref'], str) or not record['approval_ref']):
            raise ValueError('Missing or changed authenticated enrollment')
        return record['contract']

    def _contract(self):
        require_active(self.store, self.contract_digest)
        return self._historical_contract()

    def revoke(self, *, approval_ref, reason):
        """Trusted root stop/cleanup request; no acceptance, replay or refund.

        Intent itself revokes new authority. Resume only this immutable request
        after an interruption; ambiguous native ownership remains blocked.
        """
        if os.geteuid() != 0 or any(not isinstance(v, str) or not v.strip() or len(v) > 4096
                                  for v in (approval_ref, reason)):
            raise ValueError('Explicit trusted root revocation required')
        key = self.contract_digest
        with self.store.lock():
            contract = self._historical_contract()
            revision, journal = self.journal.read()
            try:
                current = self.store.read('active-owner.json')
            except FileNotFoundError:
                current = None
            selected = current if current and current['contract_digest'] == key else None
            intent_name = key + '.revocation-intent.json'
            try:
                intent = self.store.read(intent_name)
            except FileNotFoundError:
                intent = {'contract_digest': key, 'approval_ref': approval_ref,
                          'reason': reason, 'owner': selected}
                self.store.create(intent_name, intent)
            if (set(intent) != {'contract_digest', 'approval_ref', 'reason', 'owner'} or
                    intent['contract_digest'] != key or intent['approval_ref'] != approval_ref or
                    intent['reason'] != reason):
                raise ValueError('Immutable revocation request changed')
            revoked = {'contract_digest': key, 'intent_digest': digest(intent)}
            try:
                self.store.create(key + '.revoked.json', revoked)
            except FileExistsError:
                if self.store.read(key + '.revoked.json') != revoked:
                    raise ValueError('Protected revocation changed')
            complete_name = key + '.revocation-complete.json'
            try:
                complete = self.store.read(complete_name)
            except FileNotFoundError:
                complete = None
            if complete is not None:
                if (set(complete) != {'contract_digest', 'intent_digest', 'journal_revision'} or
                        complete['contract_digest'] != key or
                        complete['intent_digest'] != digest(intent) or
                        complete['journal_revision'] != revision or selected is not None or
                        journal['attempts'] and journal['attempts'][-1]['status'] != 'finished'):
                    raise ValueError('Completed revocation state changed')
                if intent['owner'] is not None:
                    owner = intent['owner'];last = journal['attempts'][-1]
                    original = {**journal, 'attempts': journal['attempts'][:-1] + [{**last, 'status':'reserved','progress_receipt':None}]}
                    plan = launch_plan(original,key,run_id=owner['run_id'],run_attempt=owner['run_attempt'],session_id=owner['session_id'])
                    proof = self.store.read(key+'.revocation-stop.json')
                    if (proof['intent_digest'] != digest(intent) or proof['owner'] != owner or
                            plan['unit'] != owner['unit'] or digest(plan) != owner['plan_digest']):
                        raise ValueError('Completed revocation stop proof changed')
                    observation = self.backend.observe_owned(plan,contract,owner,proof['invocation_id'])
                    if not (observation['ownership_verified'] and observation['execution_finished'] and observation['cgroup_empty']):
                        raise ValueError('Completed revocation predecessor reappeared')
                return complete
            owner = intent['owner']
            if owner is not None:
                if not journal['attempts']:
                    raise ValueError('Revoked owner lacks charged reservation')
                last = journal['attempts'][-1]
                original = {**journal, 'attempts': journal['attempts'][:-1] +
                            [{**last, 'status': 'reserved', 'progress_receipt': None}]}
                plan = launch_plan(original, key, run_id=owner['run_id'],
                                   run_attempt=owner['run_attempt'], session_id=owner['session_id'])
                if (plan['unit'] != owner['unit'] or digest(plan) != owner['plan_digest'] or
                        last['status'] == 'reserved' and revision != owner['reservation_revision']):
                    raise ValueError('Revoked ownership history changed')
                if selected is not None and selected != owner:
                    raise ValueError('Revoked owner replaced')
                proof_name = key + '.revocation-stop.json'
                try:
                    proof = self.store.read(proof_name)
                except FileNotFoundError:
                    if selected != owner:
                        raise ValueError('Lost revoked owner requires inspection')
                    try:
                        native = self.store.read(owner['unit'] + '.invocation.json')
                    except FileNotFoundError:
                        invocation = self.backend.recover_invocation(plan, contract, owner)
                        self._invocation(invocation)
                        native = {'invocation_id': invocation, 'owner': owner}
                        self.store.create(owner['unit'] + '.invocation.json', native)
                    if native['owner'] != owner:
                        raise ValueError('Revocation native owner changed')
                    self._invocation(native['invocation_id'])
                    observation = self.backend.stop_owned(plan, contract, owner, native['invocation_id'])
                    proof = {'intent_digest': digest(intent), 'invocation_id': native['invocation_id'],
                             'owner': owner, 'observation': observation}
                    self.store.create(proof_name, proof)
                observation = proof['observation']
                if (proof['intent_digest'] != digest(intent) or proof['owner'] != owner or
                        observation.get('unit') != owner['unit'] or
                        observation.get('invocation_id') != proof['invocation_id'] or
                        observation.get('ownership_verified') is not True or
                        observation.get('execution_finished') is not True or
                        observation.get('cgroup_empty') is not True):
                    raise ValueError('Revocation lacks ended empty native ownership proof')
                fresh = self.backend.observe_owned(plan, contract, owner, proof['invocation_id'])
                if not (fresh['ownership_verified'] and fresh['execution_finished'] and fresh['cgroup_empty']):
                    raise ValueError('Revocation predecessor no longer ended and empty')
                if selected is None and last['status'] != 'finished':
                    raise ValueError('Revocation lost owner before charged finish')
                if last['status'] == 'reserved':
                    closed = finish(journal, key, run_id=owner['run_id'],
                                    run_attempt=owner['run_attempt'], progress_receipt=None)
                    revision = self.journal.publish(revision, closed)
                    if self.journal.read() != (revision, closed):
                        raise ValueError('Uncertain revocation reconciliation')
                if selected is not None:
                    self.store.remove('active-owner.json')
                elif last['status'] != 'finished':
                    raise ValueError('Revocation lost owner before charged finish')
            if owner is None and journal['attempts'] and journal['attempts'][-1]['status'] == 'reserved':
                raise ValueError('Revoked reservation lacks authenticated ownership; inspection required')
            complete = {'contract_digest': key, 'intent_digest': digest(intent),
                        'journal_revision': revision}
            self.store.create(complete_name, complete)
            if self.store.read(complete_name) != complete:
                raise ValueError('Revocation completion readback changed')
            return complete

    def enroll(self, contract, approval_ref):
        """Trusted human-approval importer only, never automatic recovery."""
        initialize(self.contract_digest)
        if digest(contract) != self.contract_digest or not isinstance(approval_ref, str) or not approval_ref:
            raise ValueError('Exact authenticated approval required')
        with self.store.lock():
            # Approval is immutable. A crash before journal initialization requires
            # inspection, not an automatic re-enrollment and history reset.
            self.store.create(self.contract_digest + '.approval.json',
                              {'contract': contract, 'approval_ref': approval_ref})
            return self.journal.publish(None, initialize(self.contract_digest))

    def _unowned(self):
        try:
            self.store.read('active-owner.json')
        except FileNotFoundError:
            return
        raise ValueError('Private credential stream has an unreconciled owner')

    def _workflow_selection(self, task_id):
        try:
            self.store.read(self.contract_digest + '.workflow.json')
        except FileNotFoundError:
            if list(self.store.root.glob('deep-loop-pilot-' + self.contract_digest + '-*.workflow-attempt.json')):
                raise ValueError('Prior workflow attempt lost its protected enrollment')
            if task_id is not None:
                raise ValueError('Task dispatch requires protected workflow enrollment')
            return None
        gate = self.workflow_gate
        if (gate is None or gate.store is not self.store or
                gate.contract_digest != self.contract_digest or
                not isinstance(task_id, str) or not task_id):
            raise ValueError('Trusted workflow gate and explicit task required')
        selection = gate.selection()
        if task_id not in selection['ready']:
            raise ValueError('Task prerequisites unavailable: ' + task_id)
        return {'task_id': task_id, 'binding_digest': selection['binding_digest'],
                'session_id': selection['session_id']}

    def _workflow_receipt(self, owner):
        try:
            binding = self.store.read(self.contract_digest + '.workflow.json')
        except FileNotFoundError:
            try:
                self.store.read(owner['unit'] + '.workflow-attempt.json')
            except FileNotFoundError:
                return None
            raise ValueError('Workflow attempt lost its protected enrollment')
        receipt = self.store.read(owner['unit'] + '.workflow-attempt.json')
        selection = receipt.get('selection', {})
        if (set(receipt) != {'owner', 'selection'} or receipt['owner'] != owner or
                set(selection) != {'task_id', 'binding_digest', 'session_id'} or
                selection['binding_digest'] != digest(binding) or
                selection['session_id'] != binding['session_id'] or
                selection['task_id'] not in binding['task_verifiers']):
            raise ValueError('Protected workflow attempt identity drift')
        return selection

    def start(self, *, run_id, run_attempt, model_seconds, active_seconds, session_id=None, task_id=None):
        with self.store.lock():
            contract = self._contract()
            self._unowned()
            selection = self._workflow_selection(task_id)
            revision, journal = self.journal.read()
            reserved = reserve(journal, self.contract_digest, run_id=run_id, run_attempt=run_attempt,
                               model_seconds=model_seconds, active_seconds=active_seconds)
            plan = launch_plan(reserved, self.contract_digest, run_id=run_id,
                               run_attempt=run_attempt, session_id=session_id)
            if session_id is not None:
                binding = self.store.read(session_id + '.session.json')
                if binding['contract_digest'] != self.contract_digest or binding['session_id'] != session_id:
                    raise ValueError('Session does not belong to approved contract')
                if selection is not None:
                    prior = self.store.read(binding['unit'] + '.workflow-attempt.json')
                    if (prior['owner']['unit'] != binding['unit'] or
                            self._workflow_receipt(prior['owner']) != selection):
                        raise ValueError('Session does not belong to selected workflow task')
            # No model work is permitted by qualification. It must also prove no
            # unit for this dedicated identity is active outside the owner record.
            self.backend.qualify(plan, contract)
            if self._workflow_selection(task_id) != selection:
                raise ValueError('Workflow selection changed during qualification')
            persisted = self.journal.publish(revision, reserved)
            observed, saved = self.journal.read()
            if observed != persisted or saved != reserved:
                raise ValueError('Uncertain durable admission readback')
            owner = {'contract_digest': self.contract_digest, 'unit': plan['unit'],
                     'plan_digest': digest(plan), 'reservation_revision': persisted,
                     'run_id': run_id, 'run_attempt': run_attempt, 'session_id': session_id}
            self.store.create('active-owner.json', owner)
            if selection is not None:
                self.store.create(plan['unit'] + '.workflow-attempt.json',
                                  {'owner': owner, 'selection': selection})
            if self._workflow_selection(task_id) != selection:
                raise ValueError('Workflow selection changed before native submission')
            # The immutable intent precedes submission. Any crash or uncertainty
            # after this point blocks a second launch, including another contract.
            invocation = self.backend.submit(plan, contract)
            self._invocation(invocation)
            self.store.create(plan['unit'] + '.invocation.json',
                              {'invocation_id': invocation, 'owner': owner})
            return owner

    @staticmethod
    def _invocation(value):
        if not isinstance(value, str) or len(value) != 32 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('Invalid native invocation identity')

    def reconcile(self):
        """Wakeup/restart path: inspect and finish only, never submit or refund."""
        with self.store.lock():
            contract = self._contract()
            owner = self.store.read('active-owner.json')
            if owner['contract_digest'] != self.contract_digest:
                raise ValueError('Credential stream owned by another contract')
            workflow = self._workflow_receipt(owner)
            revision, journal = self.journal.read()
            if not journal['attempts']:
                raise ValueError('Missing reserved ownership history')
            last = journal['attempts'][-1]
            if set(owner) != {'contract_digest', 'unit', 'plan_digest', 'reservation_revision', 'run_id', 'run_attempt', 'session_id'}:
                raise ValueError('Malformed launch ownership')
            if (last['run_id'], last['run_attempt']) != (owner['run_id'], owner['run_attempt']):
                raise ValueError('Reservation ownership drift')
            # Reconstruct the original reservation even after a finish-before-
            # owner-release crash; neither command nor identity may drift.
            original = {**journal, 'attempts': journal['attempts'][:-1] +
                        [{**last, 'status': 'reserved', 'progress_receipt': None}]}
            plan = launch_plan(original, self.contract_digest, run_id=owner['run_id'],
                               run_attempt=owner['run_attempt'], session_id=owner['session_id'])
            if plan['unit'] != owner['unit'] or digest(plan) != owner['plan_digest']:
                raise ValueError('Persisted launch plan changed')
            if last['status'] == 'reserved' and revision != owner['reservation_revision']:
                raise ValueError('Reserved journal revision changed')
            try:
                receipt = self.store.read(owner['unit'] + '.invocation.json')
            except FileNotFoundError:
                # Only the trusted adapter can adopt an exact existing native
                # unit. No unit or insufficient provenance blocks; never retry.
                recover = getattr(self.backend, 'recover_invocation', None)
                if recover is None:
                    raise
                invocation = recover(plan, contract, owner)
                self._invocation(invocation)
                receipt = {'invocation_id': invocation, 'owner': owner}
                self.store.create(owner['unit'] + '.invocation.json', receipt)
            if receipt['owner'] != owner:
                raise ValueError('Changed invocation ownership')
            invocation = receipt['invocation_id']
            self._invocation(invocation)
            observation, session_id = self.backend.observe(owner['unit'], invocation)
            if observation.get('invocation_id') != invocation:
                raise ValueError('Native invocation changed or unavailable')
            proof = {k: observation.get(k) for k in ('unit', 'active_state', 'cgroup_empty', 'ownership_verified')}
            if 'execution_finished' in observation:
                proof['execution_finished'] = observation['execution_finished']
            if last['status'] == 'reserved':
                action = recovery_action(journal, self.contract_digest, proof)
            else:
                action = ('reconcile_without_refund' if proof['unit'] == owner['unit'] and
                          (proof['active_state'] in {'inactive', 'failed'} or
                           proof['active_state'] == 'active' and proof.get('execution_finished') is True) and
                          proof['cgroup_empty'] is True and proof['ownership_verified'] is True
                          else 'blocked_missing_ownership_proof')
            if action != 'reconcile_without_refund':
                return action
            if session_id is not None:
                # Canonical UUID validation is shared with launch plans.
                launch_plan({**journal, 'attempts': journal['attempts'][:-1] +
                             [{**last, 'status': 'reserved', 'progress_receipt': None}]},
                            self.contract_digest, run_id=owner['run_id'],
                            run_attempt=owner['run_attempt'], session_id=session_id)
                binding = {'contract_digest': self.contract_digest, 'session_id': session_id,
                           'unit': owner['unit'], 'invocation_id': invocation}
                try:
                    self.store.create(session_id + '.session.json', binding)
                except FileExistsError:
                    previous = self.store.read(session_id + '.session.json')
                    if (previous.get('contract_digest'), previous.get('session_id')) != (self.contract_digest, session_id):
                        raise ValueError('Conflicting session binding')
            session_receipt = {'contract_digest': self.contract_digest, 'unit': owner['unit'],
                               'invocation_id': invocation, 'session_id': session_id}
            try:
                self.store.create(owner['unit'] + '.session.json', session_receipt)
            except FileExistsError:
                if self.store.read(owner['unit'] + '.session.json') != session_receipt:
                    raise ValueError('Changed native attempt session observation')
            if last['status'] == 'reserved':
                # A trusted verifier reads the stopped candidate independently.
                # Semantic receipts omit invocation IDs/time so identical output
                # cannot repeatedly reset the no-progress counter.
                # Frozen single-artifact proof cannot accept a graph parent.
                # Workflow acceptance will use its enrolled task/parent contract.
                evidence = self.verifier(contract, owner) if self.verifier is not None and workflow is None else None
                if evidence is not None and (not isinstance(evidence, dict) or
                        evidence.get('contract_digest') != self.contract_digest):
                    raise ValueError('Verification evidence contract drift')
                progress = digest(evidence) if evidence is not None else None
                if progress in {a['progress_receipt'] for a in journal['attempts']}:
                    progress = None
                if progress is not None:
                    name = progress + '.progress.json'
                    try:
                        self.store.create(name, evidence)
                    except FileExistsError:
                        if self.store.read(name) != evidence:
                            raise ValueError('Conflicting progress evidence')
                finished = finish(journal, self.contract_digest, run_id=owner['run_id'],
                                  run_attempt=owner['run_attempt'], progress_receipt=progress)
                self.journal.publish(revision, finished)
            completed = finished if last['status'] == 'reserved' else journal
            progress = completed['attempts'][-1]['progress_receipt']
            if progress is not None:
                evidence = self.store.read(progress + '.progress.json')
                if digest(evidence) != progress or evidence.get('contract_digest') != self.contract_digest:
                    raise ValueError('Missing or changed protected progress evidence')
            self.store.remove('active-owner.json')
            return ('finished_with_verified_progress' if progress is not None
                    else 'finished_without_verified_progress')
