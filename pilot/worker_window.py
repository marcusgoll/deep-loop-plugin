"""Immutable host-boot execution window; restarting never extends its deadline."""
import math
from pathlib import Path
import time
import uuid

from admission import LIMITS, initialize


def host_clock():
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if str(uuid.UUID(boot)) != boot:
        raise ValueError('Unavailable host boot identity')
    return boot, time.clock_gettime(time.CLOCK_BOOTTIME)


def open_window(store, contract_digest, clock=host_clock):
    """Explicit approve-and-run importer only; existing state blocks."""
    initialize(contract_digest)
    approval = store.read(contract_digest+'.approval.json')
    from admission import digest
    if (digest(approval['contract']) != contract_digest or not approval['approval_ref'] or
            approval['contract'].get('worker_wall_seconds') != LIMITS['active_seconds']):
        raise ValueError('Exact authenticated approval required')
    boot, now = clock()
    if type(now) not in (int,float) or not math.isfinite(now) or now < 0:
        raise ValueError('Invalid trusted host clock')
    store.create(contract_digest+'.window.json',
                 {'contract_digest':contract_digest,'boot_id':boot,'started':now,
                  'seconds':LIMITS['active_seconds']})


def remaining(store, contract_digest, clock=host_clock):
    initialize(contract_digest)
    boot, now = clock()
    if not isinstance(now, (int, float)) or isinstance(now, bool) or not math.isfinite(now) or now < 0:
        raise ValueError('Invalid trusted host clock')
    name = contract_digest+'.window.json'
    record = store.read(name)
    if (set(record) != {'contract_digest','boot_id','started','seconds'} or
            record['contract_digest'] != contract_digest or record['boot_id'] != boot or
            record['seconds'] != LIMITS['active_seconds'] or
            type(record['started']) not in (int,float) or not math.isfinite(record['started']) or
            record['started'] < 0 or now < record['started']):
        raise ValueError('Execution window unavailable or host boot changed; never reset')
    return max(0,record['seconds']-(now-record['started']))
