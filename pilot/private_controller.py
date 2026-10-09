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
import uuid

from admission import digest, finish, initialize, reserve
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
    def __init__(self, store, journal, backend):
        self.store, self.journal, self.backend = store, journal, backend
        self.contract_digest = journal.contract_digest

    def _contract(self):
        record = self.store.read(self.contract_digest + '.approval.json')
        if (set(record) != {'contract', 'approval_ref'} or
                digest(record['contract']) != self.contract_digest or
                not isinstance(record['approval_ref'], str) or not record['approval_ref']):
            raise ValueError('Missing or changed authenticated enrollment')
        return record['contract']

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

    def start(self, *, run_id, run_attempt, model_seconds, active_seconds, session_id=None):
        with self.store.lock():
            contract = self._contract()
            self._unowned()
            revision, journal = self.journal.read()
            reserved = reserve(journal, self.contract_digest, run_id=run_id, run_attempt=run_attempt,
                               model_seconds=model_seconds, active_seconds=active_seconds)
            plan = launch_plan(reserved, self.contract_digest, run_id=run_id,
                               run_attempt=run_attempt, session_id=session_id)
            if session_id is not None:
                binding = self.store.read(session_id + '.session.json')
                if binding['contract_digest'] != self.contract_digest or binding['session_id'] != session_id:
                    raise ValueError('Session does not belong to approved contract')
            # No model work is permitted by qualification. It must also prove no
            # unit for this dedicated identity is active outside the owner record.
            self.backend.qualify(plan, contract)
            persisted = self.journal.publish(revision, reserved)
            observed, saved = self.journal.read()
            if observed != persisted or saved != reserved:
                raise ValueError('Uncertain durable admission readback')
            owner = {'contract_digest': self.contract_digest, 'unit': plan['unit'],
                     'plan_digest': digest(plan), 'reservation_revision': persisted,
                     'run_id': run_id, 'run_attempt': run_attempt}
            self.store.create('active-owner.json', owner)
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
            self._contract()
            owner = self.store.read('active-owner.json')
            if owner['contract_digest'] != self.contract_digest:
                raise ValueError('Credential stream owned by another contract')
            receipt = self.store.read(owner['unit'] + '.invocation.json')
            if receipt['owner'] != owner:
                raise ValueError('Changed invocation ownership')
            invocation = receipt['invocation_id']
            self._invocation(invocation)
            observation, session_id = self.backend.observe(owner['unit'], invocation)
            if observation.get('invocation_id') != invocation:
                raise ValueError('Native invocation changed or unavailable')
            revision, journal = self.journal.read()
            last = journal['attempts'][-1]
            if (last['run_id'], last['run_attempt']) != (owner['run_id'], owner['run_attempt']):
                raise ValueError('Reservation ownership drift')
            proof = {k: observation.get(k) for k in ('unit', 'active_state', 'cgroup_empty', 'ownership_verified')}
            if last['status'] == 'reserved':
                action = recovery_action(journal, self.contract_digest, proof)
            else:
                action = ('reconcile_without_refund' if proof['unit'] == owner['unit'] and
                          proof['active_state'] in {'inactive', 'failed'} and
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
            if last['status'] == 'reserved':
                # No adapter-generated or model-reported progress is accepted.
                # Independent verification can be integrated separately; until
                # then every completed invocation consumes a no-progress attempt.
                finished = finish(journal, self.contract_digest, run_id=owner['run_id'], run_attempt=owner['run_attempt'])
                self.journal.publish(revision, finished)
            self.store.remove('active-owner.json')
            return 'finished_without_verified_progress'
