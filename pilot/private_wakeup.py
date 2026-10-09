"""One trusted wakeup transition for an explicitly enabled frozen outcome.

No default outcome, enrollment, reset, delivery or automatic failover. Production
service deadlines/host installation must be qualified separately. This module
reuses controller ownership and its journal; it stores no task-status replica.
"""
from admission import LIMITS, digest
from private_launch import launch_plan


def tick(store, controller_factory, *, expected_contract_digest=None, active_window_remaining=None):
    try:
        enabled = store.read('enabled-outcome.json')
    except FileNotFoundError:
        return 'disabled'
    if set(enabled) != {'contract_digest'}:
        raise ValueError('Malformed explicit wakeup selection')
    contract_digest = enabled['contract_digest']
    if expected_contract_digest is not None and contract_digest != expected_contract_digest:
        raise ValueError('Enabled outcome changed during worker execution')
    approval = store.read(contract_digest + '.approval.json')
    contract = approval['contract']
    if digest(contract) != contract_digest or not approval['approval_ref']:
        raise ValueError('Changed authenticated wakeup contract')
    # This disposable pilot divides the approved cumulative allowances across
    # the maximum three attempts. Wakeups cannot choose or increase allowances.
    schedule = contract['wakeup']
    expected = {'model_seconds': LIMITS['model_seconds']//LIMITS['attempts'],
                'active_seconds': LIMITS['active_seconds']//LIMITS['attempts']}
    if schedule != expected or any(type(v) is not int for v in schedule.values()):
        raise ValueError('Changed frozen wakeup allowances')
    controller = controller_factory(contract_digest)
    if controller.contract_digest != contract_digest:
        raise ValueError('Wakeup controller contract drift')
    try:
        owner = store.read('active-owner.json')
    except FileNotFoundError:
        owner = None
    if owner is not None:
        if owner['contract_digest'] != contract_digest:
            return 'blocked_other_owner'
        # Even successful reconciliation never dispatches in the same wakeup.
        return controller.reconcile()
    _, journal = controller.journal.read()
    attempts = journal['attempts']
    if attempts and attempts[-1]['status'] == 'reserved':
        return 'blocked_missing_owner'
    if attempts and attempts[-1]['progress_receipt'] is not None:
        evidence = store.read(attempts[-1]['progress_receipt']+'.progress.json')
        if digest(evidence) != attempts[-1]['progress_receipt'] or evidence.get('contract_digest') != contract_digest:
            raise ValueError('Unavailable protected acceptance evidence')
        return 'ready_for_trusted_delivery'
    no_progress = 0
    for attempt in reversed(attempts):
        if attempt['progress_receipt'] is not None:
            break
        no_progress += 1
    if len(attempts) >= LIMITS['attempts'] or no_progress >= LIMITS['no_progress']:
        return 'stopped_limits'
    session = None
    if attempts:
        last = attempts[-1]
        original = {**journal, 'attempts': attempts[:-1] +
                    [{**last, 'status': 'reserved', 'progress_receipt': None}]}
        plan = launch_plan(original, contract_digest, run_id=last['run_id'], run_attempt=last['run_attempt'])
        receipt = store.read(plan['unit']+'.session.json')
        invocation = store.read(plan['unit']+'.invocation.json')
        if (set(receipt) != {'contract_digest', 'unit', 'invocation_id', 'session_id'} or
                receipt['contract_digest'] != contract_digest or receipt['unit'] != plan['unit'] or
                receipt['invocation_id'] != invocation['invocation_id']):
            raise ValueError('Unverified attempt session provenance')
        session = receipt['session_id']
        if session is None:
            # A missing session does not justify silently starting a fresh task.
            return 'blocked_missing_session'
    if active_window_remaining is not None and active_window_remaining < schedule['active_seconds']:
        return 'stopped_insufficient_execution_window'
    controller.start(run_id=len(attempts)+1, run_attempt=1, session_id=session, **schedule)
    return 'submitted_once'
