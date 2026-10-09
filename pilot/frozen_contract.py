"""Pure validation before private enrollment and trusted delivery."""
from datetime import datetime
from pathlib import PurePosixPath
import re

from admission import LIMITS, initialize
from artifact_verifier import _path

REPOSITORY = 'marcusgoll/deep-loop-plugin'
ARTIFACT = 'pilot/fixtures/private-lane-smoke.txt'
CHECKPOINT = 'pilot/fixtures/private-lane-checkpoint.txt'


def validate_delivery(delivery):
    if (not isinstance(delivery, dict) or
            set(delivery) != {'repository','repository_id','publisher_id','base_ref','source_sha','commit_date','title','body'} or
            delivery['repository'] != REPOSITORY or delivery['base_ref'] != 'codex/pilot-admission' or
            any(type(delivery[k]) != int or delivery[k] < 1 for k in ('repository_id','publisher_id')) or
            not isinstance(delivery['source_sha'], str) or
            not re.fullmatch('[0-9a-f]{40}', delivery['source_sha']) or delivery['source_sha'] == '0'*40 or
            not isinstance(delivery['commit_date'], str) or
            not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', delivery['commit_date']) or
            any(not isinstance(delivery[k], str) or not delivery[k] or len(delivery[k]) > 4096 for k in ('title','body'))):
        raise ValueError('Unsupported frozen delivery endpoint')
    datetime.strptime(delivery['commit_date'], '%Y-%m-%dT%H:%M:%SZ')


def validate_frozen(contract):
    if not isinstance(contract, dict):
        raise ValueError('Frozen contract must be an object')
    if (type(contract.get('worker_wall_seconds')) != int or
            contract['worker_wall_seconds'] != LIMITS['active_seconds'] or
            contract.get('wakeup') != {'model_seconds':600,'active_seconds':1200} or
            any(type(value) != int for value in contract['wakeup'].values()) or
            not isinstance(contract.get('prompt'), str) or not contract['prompt'] or len(contract['prompt']) > 65536):
        raise ValueError('Unsupported frozen execution allowances or prompt')
    executor = contract.get('executor')
    if not isinstance(executor, dict) or set(executor) != {'path','sha256'}:
        raise ValueError('Pinned native executor required')
    path = executor['path']
    if (not isinstance(path, str) or not path.startswith('/') or len(path) > 4096 or
            str(PurePosixPath(path)) != path or '..' in path.split('/')):
        raise ValueError('Canonical absolute native executor required')
    initialize(executor['sha256'])
    runtime = contract.get('runtime')
    if not isinstance(runtime, dict) or set(runtime) != {'bundle_digest','unit_plan_digest'}:
        raise ValueError('Pinned installed runtime required')
    for value in runtime.values(): initialize(value)
    verification = contract.get('verification')
    if (not isinstance(verification, dict) or
            set(verification) != {'baseline','artifact_path','artifact_sha256'} or
            not isinstance(verification['baseline'], dict) or verification['baseline'] != {} or
            _path(verification['artifact_path']) != ARTIFACT):
        raise ValueError('Exact disposable artifact contract required')
    initialize(verification['artifact_sha256'])
    resume = contract.get('resume_verification')
    if (not isinstance(resume, dict) or set(resume) != {'checkpoint_path','checkpoint_sha256'} or
            _path(resume['checkpoint_path']) != CHECKPOINT):
        raise ValueError('Exact temporary checkpoint contract required')
    initialize(resume['checkpoint_sha256'])
    validate_delivery(contract.get('delivery'))
