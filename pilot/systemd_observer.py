"""Read-only native ownership/cgroup observation. Never starts or stops a unit."""
import re
from pathlib import Path
import subprocess

from private_launch import ACCOUNT

UNIT = re.compile(r'deep-loop-pilot-[0-9a-f]{64}-[1-9][0-9]*-[1-9][0-9]*\Z')
PROPERTIES = ('LoadState', 'ActiveState', 'InvocationID', 'User', 'Group',
              'KillMode', 'Restart', 'Slice', 'ControlGroup', 'SubState', 'MainPID', 'RemainAfterExit')


def _native_state(unit, invocation_id, run):
    result = run(['/usr/bin/systemctl', 'show', unit + '.service',
                  '--property=' + ','.join(PROPERTIES)], capture_output=True,
                 text=True, check=True, timeout=5)
    values = {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition('=')
        if not separator or key not in PROPERTIES or key in values:
            raise ValueError('Malformed native property readback')
        values[key] = value
    expected_cgroup = '/system.slice/' + unit + '.service'
    if (set(values) != set(PROPERTIES) or values['LoadState'] != 'loaded' or
            values['InvocationID'] != invocation_id or values['User'] != ACCOUNT or
            values['Group'] != ACCOUNT or values['KillMode'] != 'control-group' or
            values['Restart'] != 'no' or values['Slice'] != 'system.slice'):
        raise ValueError('Native ownership or invocation unavailable/changed')
    retained_exit = (values['ActiveState'] == 'active' and values['SubState'] == 'exited'
                     and values['MainPID'] == '0' and values['RemainAfterExit'] == 'yes')
    inactive = values['ActiveState'] in {'inactive', 'failed'} or retained_exit
    if values['ControlGroup'] != expected_cgroup and not (inactive and values['ControlGroup'] == ''):
        raise ValueError('Unexpected native control group')
    return values, inactive


def observe_unit(unit, invocation_id, *, run=subprocess.run, cgroup_root=Path('/sys/fs/cgroup')):
    """Require a retained exact invocation and fixed system.slice ownership.

    Inactive units may have released their cgroup. A missing expected cgroup is
    empty only when the retained native invocation is inactive/failed. A missing
    native unit never constitutes proof. Missing cgroups require a fresh second
    manager snapshot for that same invocation. Production uses the kernel tree.
    """
    if not isinstance(unit, str) or not UNIT.fullmatch(unit) or len(unit + '.service') > 255:
        raise ValueError('Invalid private native unit')
    if not isinstance(invocation_id, str) or not re.fullmatch(r'[0-9a-f]{32}', invocation_id):
        raise ValueError('Invalid invocation identity')
    expected_cgroup = '/system.slice/' + unit + '.service'
    values, inactive = _native_state(unit, invocation_id, run)
    path = cgroup_root / expected_cgroup.lstrip('/')
    if path.resolve() != path:
        raise ValueError('Noncanonical cgroup path')
    try:
        events = dict(line.split() for line in (path/'cgroup.events').read_text().splitlines())
        if events.get('populated') not in {'0', '1'}:
            raise ValueError('Missing kernel cgroup population evidence')
        empty = events['populated'] == '0'
    except FileNotFoundError:
        if path.exists():
            raise ValueError('Missing kernel population evidence')
        # The manager snapshot may precede the kernel releasing a just-ended
        # cgroup. Re-read the same retained invocation once, with every ownership
        # field revalidated; no retry can launch or stop a process.
        values, inactive = _native_state(unit, invocation_id, run)
        if path.resolve() != path or path.exists() or not inactive:
            raise ValueError('Missing kernel population evidence')
        empty = True
    return {'unit': unit, 'invocation_id': invocation_id, 'active_state': values['ActiveState'],
            'cgroup_empty': empty, 'ownership_verified': True, 'execution_finished': inactive and empty}
