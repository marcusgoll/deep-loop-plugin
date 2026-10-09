"""Single-use trusted enrollment transaction; no default contract or activation.

The root operator authenticates the exact human approval before calling this
adapter. It is never a worker recovery path. Durable intent makes every partial
or uncertain transaction require inspection instead of automatic re-enrollment.
"""
from frozen_contract import validate_frozen
from admission import digest, initialize, reserve
from private_launch import launch_plan
from worker_window import open_window, host_clock


class Enrollment:
    def __init__(self, store, journal, backend, preflight, activate, clock=host_clock):
        self.store, self.journal, self.backend = store, journal, backend
        self.preflight, self.activate, self.clock = preflight, activate, clock

    def apply(self, contract, *, expected_digest, approval_ref):
        validate_frozen(contract)
        initialize(expected_digest)
        if (digest(contract) != expected_digest or self.journal.contract_digest != expected_digest or
                not isinstance(approval_ref, str) or not approval_ref.strip() or len(approval_ref) > 4096):
            raise ValueError('Exact authenticated approve-and-run required')
        key = expected_digest
        with self.store.lock():
            # This dedicated pilot supports one enrollment ever. Terminal or
            # uncertain approval records remain authority, never cleanup targets.
            for pattern in ('*.approval.json', '*.enrollment-intent.json',
                            '*.activation-intent.json', '*.window.json', '*.enrollment-complete.json'):
                if list(self.store.root.glob(pattern)):
                    raise ValueError('Existing or partial enrollment requires inspection')
            for name in ('active-owner.json', 'enabled-outcome.json', key+'.window.json',
                         key+'.enrollment-intent.json', key+'.activation-intent.json'):
                try: self.store.read(name)
                except FileNotFoundError: pass
                else: raise ValueError('Existing or partial enrollment requires inspection')
            # Preflight verifies exact installed bundle/units, disabled timer,
            # empty candidate, frozen source/identity and qualification receipt.
            # It must be read-only and authentic host evidence, not model claims.
            preflight = self.preflight(contract)
            if not isinstance(preflight, dict) or preflight.get('contract_digest') != key:
                raise ValueError('Unbound trusted enrollment preflight')
            intent = {'contract_digest':key, 'approval_ref':approval_ref, 'preflight':preflight}
            self.store.create(key+'.enrollment-intent.json', intent)
            self.store.create(key+'.approval.json', {'contract':contract,'approval_ref':approval_ref})
            # Qualification runs against authenticated approval before creating
            # a journal or opening a live window. This plan is never dispatched.
            trial = reserve(initialize(key), key, run_id=1, run_attempt=1,
                            model_seconds=600, active_seconds=1200)
            plan = launch_plan(trial, key, run_id=1, run_attempt=1)
            self.backend.qualify(plan, contract)
            revision = self.journal.publish(None, initialize(key))
            observed_revision, state = self.journal.read()
            if observed_revision != revision or state != initialize(key):
                raise ValueError('Uncertain enrollment journal publication')
            open_window(self.store, key, clock=self.clock)
            self.store.create('enabled-outcome.json', {'contract_digest':key})
            activation = {'contract_digest':key, 'journal_revision':revision,
                          'approval_ref':approval_ref, 'preflight_digest':digest(preflight)}
            self.store.create(key+'.activation-intent.json', activation)
        # Release the stream lock before starting the timer: its first worker
        # must be able to acquire it. Unknown activation is not blindly replayed.
        observed = self.activate(contract)
        if observed != {'timer':'active', 'contract_digest':key}:
            raise ValueError('Uncertain private timer activation; inspect existing state')
        with self.store.lock():
            if self.store.read('enabled-outcome.json') != {'contract_digest':key}:
                raise ValueError('Worker selection drift after activation')
            self.store.create(key+'.enrollment-complete.json', {**activation,'activation':observed})
            return self.store.read(key+'.enrollment-complete.json')
