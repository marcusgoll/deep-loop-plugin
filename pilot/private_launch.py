"""Build a private launch plan; never enroll, start a process, or infer approval.

Only the trusted controller may apply the plan after durable admission readback
and ownership checks. Model event streams are observations, never approval.
"""
import json
import uuid

from admission import _validate

ROOT = '/var/lib/deep-loop-private-pilot'
ACCOUNT = 'deep-loop-pilot'
STOP_SECONDS = 5
OVERHEAD_SECONDS = 10
DISABLED_FEATURES = ('hooks', 'apps', 'plugins', 'remote_plugin', 'browser_use',
                     'computer_use', 'image_generation', 'in_app_browser',
                     'in_app_local_automation', 'multi_agent', 'goals',
                     'skill_mcp_dependency_install', 'shell_snapshot')


def launch_plan(journal, contract_digest, *, run_id, run_attempt, session_id=None):
    _validate(journal, contract_digest)
    for value in (run_id, run_attempt):
        if type(value) is not int or value < 1:
            raise ValueError('Invalid launch identity')
    if not journal['attempts']:
        raise ValueError('No durable reservation')
    item = journal['attempts'][-1]
    if (item['run_id'], item['run_attempt'], item['status']) != (run_id, run_attempt, 'reserved'):
        raise ValueError('Wrong reservation')
    if session_id is not None:
        if not isinstance(session_id, str):
            raise ValueError('Explicit session UUID required')
        try:
            parsed = uuid.UUID(session_id)
        except ValueError as exc:
            raise ValueError('Explicit session UUID required') from exc
        if str(parsed) != session_id or parsed.int == 0:
            raise ValueError('Canonical nonzero session UUID required')
    # Reserve process shutdown and controller overhead, rather than treating
    # RuntimeMaxSec alone as the whole charged execution window.
    runtime = min(item['model_seconds'], item['active_seconds']) - STOP_SECONDS - OVERHEAD_SECONDS
    if runtime < 1:
        raise ValueError('Allowance cannot cover runtime, shutdown and overhead')
    candidate = f'{ROOT}/candidate/{contract_digest}'
    filesystem = {':minimal': 'read', candidate: 'write', f'{ROOT}/home': 'deny',
                  '/home': 'deny', '/run': 'deny'}
    inline = '{ ' + ', '.join(json.dumps(k) + '=' + json.dumps(v) for k, v in filesystem.items()) + ' }'
    command = ['/usr/bin/codex', 'exec', '--ignore-user-config', '--ignore-rules',
               '--strict-config', '--json']
    for feature in DISABLED_FEATURES:
        command += ['--disable', feature]
    command += ['-c', 'web_search="disabled"', '-c', 'apps._default.enabled=false',
               '-c', 'approval_policy="never"',
               '-c', 'default_permissions="deep_loop_private"',
               '-c', 'permissions.deep_loop_private.filesystem=' + inline,
               '-c', 'permissions.deep_loop_private.network.enabled=false']
    if session_id is None:
        command += ['-C', candidate, '-']
    else:
        command += ['resume', session_id, '-']
    unit = f'deep-loop-pilot-{contract_digest}-{run_id}-{run_attempt}'
    if len(unit + '.service') > 255:
        raise ValueError('Launch identity exceeds systemd unit length')
    return {'schema': 1, 'contract_digest': contract_digest, 'unit': unit,
            'candidate': candidate, 'command': command,
            'properties': {'User': ACCOUNT, 'Group': ACCOUNT,
                           'WorkingDirectory': candidate, 'SetLoginEnvironment': 'yes',
                           'RuntimeMaxSec': runtime, 'TimeoutStopSec': STOP_SECONDS,
                           'KillMode': 'control-group', 'SendSIGKILL': 'yes',
                           'Restart': 'no', 'RemainAfterExit': 'yes', 'NoNewPrivileges': 'yes', 'UMask': '0077'},
            'charged_model_seconds': item['model_seconds'],
            'charged_active_seconds': item['active_seconds'],
            'controller_overhead_seconds': OVERHEAD_SECONDS,
            'session_id': session_id}


def recovery_action(journal, contract_digest, observation):
    """A trusted systemd observation can request reconciliation, never relaunch.

    Callers must authenticate observation origin and exact unit identity. Missing
    unit state alone cannot prove no process remains after a controller restart.
    """
    _validate(journal, contract_digest)
    if not journal['attempts'] or journal['attempts'][-1]['status'] != 'reserved':
        return 'no_reserved_attempt'
    item = journal['attempts'][-1]
    plan = launch_plan(journal, contract_digest, run_id=item['run_id'], run_attempt=item['run_attempt'])
    fields = {'unit', 'active_state', 'cgroup_empty', 'ownership_verified'}
    if not isinstance(observation, dict) or set(observation) not in (fields, fields | {'execution_finished'}):
        return 'blocked_missing_ownership_proof'
    if observation['unit'] != plan['unit'] or observation['ownership_verified'] is not True:
        return 'blocked_missing_ownership_proof'
    stopped = observation['active_state'] in {'inactive', 'failed'} or (
        observation['active_state'] == 'active' and observation.get('execution_finished') is True)
    if not stopped or observation['cgroup_empty'] is not True:
        return 'wait_for_predecessor'
    return 'reconcile_without_refund'
