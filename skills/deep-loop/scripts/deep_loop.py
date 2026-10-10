#!/usr/bin/env python
"""Manual development checkpoints; validation checks records, not their truth."""
import argparse
import proof_binding
from contextlib import contextmanager, redirect_stdout, nullcontext
import io
import datetime
import graphlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid


def write_json(path, data):
    payload = json.dumps(data, indent=2) + '\n'
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix=path.name + '.', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def read_json(path):
    return proof_binding.read(path)


def sessions(root):
    return sorted((p for p in root.glob('.deep-*') if p.is_dir()),
                  key=lambda p: p.stat().st_mtime, reverse=True)


def resolve(args):
    root = Path(args.root).resolve()
    if args.path:
        return Path(args.path).resolve()
    if args.session:
        return root / f'.deep-{args.session}'
    pointer = root / '.deep-current.json'
    if pointer.exists():
        path = Path(read_json(pointer)['path'])
        if path.is_dir():
            return path
        raise ValueError('Current checkpoint is missing. Select --session or --path explicitly.')
    found = sessions(root)
    if not found:
        raise ValueError('No deep loop sessions found.')
    if len(found) != 1:
        raise ValueError('Multiple checkpoints found. Select --session or --path explicitly.')
    return found[0]


@contextmanager
def checkpoint_lock(root):
    lock = root / '.deep-current.lock'
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        yield
    finally:
        os.close(descriptor)
        lock.unlink()


def set_current(root, path):
    with checkpoint_lock(root):
        write_json(root / '.deep-current.json', {'sessionId': path.name.removeprefix('.deep-'), 'path': str(path)})


def exclude_checkpoints(root):
    """Keep resumable local evidence out of ordinary Git staging."""
    if shutil.which('git') is None:
        return
    result = subprocess.run(['git', '-C', str(root), 'rev-parse', '--git-path', 'info/exclude'],
                            capture_output=True, text=True)
    if result.returncode:
        if 'not a git repository' in result.stderr:
            return
        raise ValueError(result.stderr.strip())
    path = root / result.stdout.strip()
    existing = path.read_bytes() if path.exists() else b''
    missing = [p for p in (b'.deep-*/', b'.deep-current.json') if p not in existing.splitlines()]
    if missing:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('ab') as stream:
            if existing and not existing.endswith(b'\n'):
                stream.write(b'\n')
            stream.write(b'\n'.join(missing) + b'\n')


def init(args):
    root = Path(args.root).resolve()
    session_id = args.session or uuid.uuid4().hex[:8]
    if len(session_id) != 8 or not session_id.isalnum():
        raise ValueError('Session ID must be eight letters or digits.')
    exclude_checkpoints(root)
    path = root / f'.deep-{session_id}'
    path.mkdir()  # Never overwrite an existing checkpoint.
    write_json(path / 'state.json', {
        'schemaVersion': 4, 'sessionId': session_id, 'task': args.task,
        'active': True, 'complete': False, 'phase': 'PLAN',
        'startedAt': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'uiRoute': {'kind': 'pending'},
        'checks': [], 'delivery': {
            'endpoint': '',
            'endpointDecision': {'status': 'pending', 'source': '', 'evidence': ''},
            'branchDisposition': {'status': 'pending', 'kind': '', 'evidence': ''},
            'revision': '',
            'status': 'pending',
            'evidence': '',
        },
    })
    if getattr(args, 'ui_request', None):
        state = read_json(path / 'state.json')
        state['uiEvidence'] = {'request': ui_request(args.ui_request)}
        write_json(path / 'state.json', state)
    (path / 'plan.md').write_text(
        f'# {args.task}\n\n## Acceptance criteria\n\n## Delivery endpoint and readback\n\n'
        '## Tasks\n\n## Risks and recovery\n', encoding='utf-8')
    set_current(root, path)
    print(f'Deep loop initialized: {path}')
    return 0


def legacy_issues(path):
    """Preserve review validation for existing sessions without rewriting them."""
    verification = read_json(path / 'verification.json')
    issues = [f'Gate not passed: {name}' for name in verification.get('requiredGates', [])
              if verification.get('gates', {}).get(name) is not True]
    if verification.get('round', 1) > verification.get('maxRounds', 3):
        issues.append('Legacy review-round limit exceeded.')
    in_debt = False
    for line in (path / 'debt.md').read_text(encoding='utf-8-sig').splitlines():
        if line.strip().lower().startswith('## new debt'):
            in_debt = True
        elif line.strip().startswith('## '):
            in_debt = False
        elif in_debt and line.strip().startswith('- [ ]') and line.strip() != '- [ ] [area] [file] [impact] [paydown plan]':
            issues.append('Outstanding legacy debt entry.')
    return issues


def present(record, *fields):
    return all(isinstance(record.get(field), str) and record[field].strip() for field in fields)


def required_at(record, stage):
    gate = record.get('stage', 'review')
    if gate not in ('review', 'ship', 'closeout'):
        raise ValueError('Record stage must be review, ship or closeout.')
    return gate == 'review' or stage == 'ship' or stage == 'delivery' and gate == 'ship'


def ui_request(path):
    from ui_design import route
    source = Path(path).resolve()
    decision = route(read_json(source))
    if decision['route'] == 'blocked':
        raise ValueError(decision['diagnostic'])
    return {'path': str(source), 'sha256': proof_binding.sha(source)}


def ui_binding_required(state):
    proof = state.get('uiEvidence')
    if proof is None:
        return False
    from ui_design import bound_file, read, route, SUBSTANTIVE
    if not isinstance(proof, dict) or 'request' not in proof:
        raise ValueError('UI evidence requires a registered request')
    request = read(bound_file(proof['request'], Path.cwd()))
    decision = route(request)
    if decision['route'] == 'blocked':
        raise ValueError(decision['diagnostic'])
    return (request.get('surface') == 'ui' and (request.get('mode') in ('GREENFIELD', 'REDESIGN')
            or bool(set(request['changes']) & SUBSTANTIVE) or 'source_manifest' in proof))


def skill_dependency(relative):
    """Resolve installed dependencies without copying them into candidate packets."""
    explicit = os.environ.get('DEEP_LOOP_SKILLS_ROOT')
    local = Path(__file__).resolve().parents[2]
    installed = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex')) / 'skills'
    roots = [Path(explicit)] if explicit else [local, installed]
    for root in roots:
        target = root / relative
        if target.is_file():
            return target.resolve()
    raise ValueError(f'Missing skill dependency: {relative}; set DEEP_LOOP_SKILLS_ROOT to its installed skills directory.')


def contract_data(path, verify_files=True):
    data = read_json(path)
    validator = skill_dependency('verification-contract/scripts/validate_contract.py')
    spec = importlib.util.spec_from_file_location('contract_validator', validator)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    errors = module.validate(data)
    if errors:
        raise ValueError('Invalid verification contract: ' + '; '.join(errors))
    for verifier in data['verifiers']:
        proof_binding.definition(verifier, proof_binding.logical(path).parent, verify_files=verify_files)
    return data


def contract_semantics_sha256(contract):
    """Hash acceptance semantics while excluding mutable execution status."""
    semantic = json.loads(json.dumps(contract))
    semantic.pop('status', None)
    semantic.pop('evidence', None)
    for verifier in semantic.get('verifiers', []):
        if isinstance(verifier, dict):
            verifier.pop('status', None)
            verifier.pop('evidence', None)
    payload = json.dumps(semantic, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def bind_contract(args):
    path = resolve(args)
    state = read_json(path / 'state.json')
    if state.get('schemaVersion') not in (2, 3, 4) or not args.endpoint.strip():
        raise ValueError('Binding requires a schema-2/3/4 checkpoint and declared endpoint.')
    source = Path(args.contract).resolve()
    contract = contract_data(source)
    if getattr(args, 'ui_request', None):
        state.setdefault('uiEvidence', {})['request'] = ui_request(args.ui_request)
    if ui_binding_required(state) and 'design' not in contract:
        raise ValueError('Registered substantive UI requires an approved Design Contract')
    if 'design' in contract:
        from ui_design import design_data
        design_data(contract, source.parent)
    checks = state.setdefault('checks', [])
    if not isinstance(checks, list) or any(not isinstance(c, dict) for c in checks):
        raise ValueError('Checks must contain records.')
    for verifier in contract['verifiers']:
        if verifier['gate'] == 'blocking' and not any(c.get('verifierId') == verifier['id'] for c in checks):
            checks.append({'name': verifier['id'], 'verifierId': verifier['id'], **({'stage':'ship'} if verifier.get('proof',{}).get('readback') is not None else {})})
    for check in checks:
        check.update(status='pending', evidence='')
        if any(v['id']==check.get('verifierId') and v.get('proof',{}).get('readback') is not None for v in contract['verifiers']):
            check['stage']='ship'
    delivery = {'endpoint': args.endpoint, 'status': 'pending', 'evidence': ''}
    if state['schemaVersion'] in (3, 4):
        prior = state.get('delivery', {})
        if not isinstance(prior, dict):
            raise ValueError('Delivery must be an object before binding.')
        delivery = json.loads(json.dumps(prior))
        delivery.update(endpoint=args.endpoint, status='pending', evidence='')
        if prior.get('endpoint') != args.endpoint:
            delivery['endpointDecision'] = {'status': 'pending', 'source': '', 'evidence': ''}
        else:
            delivery.setdefault('endpointDecision', {'status': 'pending', 'source': '', 'evidence': ''})
        subjects = delivery.get('targets')
        if subjects is None:
            delivery.setdefault('revision', '')
            subjects = [delivery]
        elif not isinstance(subjects, list) or any(not isinstance(item, dict) for item in subjects):
            raise ValueError('Delivery targets must contain records before binding.')
        for subject in subjects:
            if subject is not delivery:
                subject.update(status='pending', evidence='')
            disposition = subject.setdefault('branchDisposition', {'status': 'pending', 'kind': '', 'evidence': ''})
            if not isinstance(disposition, dict):
                raise ValueError('Branch disposition must be an object before binding.')
            if disposition.get('kind') != 'not_applicable':
                disposition.update(status='pending', evidence='')
    state.update(verificationContract={'path': str(source), 'sha256': proof_binding.sha(source),
                                       'semanticsSha256': contract_semantics_sha256(contract),
                                       'endpoint': args.endpoint}, complete=False, phase='PLAN', delivery=delivery)
    write_json(path / 'state.json', state)
    print('Contract bound; prior check and delivery evidence invalidated.')
    return 0


def refresh_contract(args):
    """Refresh mutable contract run status without invalidating unchanged acceptance evidence."""
    path = resolve(args)
    state_path = path / 'state.json'
    state = read_json(state_path)
    binding = state.get('verificationContract')
    if not isinstance(binding, dict) or not present(binding, 'path', 'sha256', 'semanticsSha256', 'endpoint'):
        raise ValueError('Refresh requires a current binding with semantic identity; use bind-contract and rerun evidence.')
    if args.endpoint.strip() != binding['endpoint']:
        raise ValueError('Refresh endpoint differs from the bound endpoint; use bind-contract and rerun evidence.')
    source = Path(args.contract).resolve()
    contract = contract_data(source)
    semantics = contract_semantics_sha256(contract)
    if semantics != binding['semanticsSha256']:
        raise ValueError('Contract acceptance semantics changed; use bind-contract and rerun evidence.')
    binding.update(path=str(source), sha256=proof_binding.sha(source),
                   semanticsSha256=semantics)
    write_json(state_path, state)
    print('Contract status refreshed; check and delivery evidence preserved because acceptance semantics are unchanged.')
    return 0


def resolution_context(state, archive=None):
    # Explicit handoff maps remain restrictive through nested gate inspection.
    if proof_binding.mapped_context():
        return nullcontext()
    binding = state.get('proofResolution')
    if binding is None:
        return proof_binding.files_context()
    path = (Path(archive)/'resolution.json').resolve() if archive else Path(binding['path']).resolve()
    if hashlib.sha256(path.read_bytes()).hexdigest() != binding['sha256']:
        raise ValueError('Preserved resolution map changed')
    mapping = json.loads(path.read_text(encoding='utf-8'))
    if mapping.get('schemaVersion') != 1 or not isinstance(mapping.get('files'), dict):
        raise ValueError('Invalid preserved resolution map')
    return proof_binding.files_context(path.parent, mapping['files'])


def contract_issues(state, stage, archive=None):
    try:
        with resolution_context(state, archive):
            return _contract_issues(state, stage)
    except (OSError, ValueError, KeyError, TypeError) as error:
        return ['Preserved proof BLOCKED: ' + str(error)]




def contract_definition_issues(state):
    """Validate parent definitions and coverage, without execution acceptance."""
    try:
        if not isinstance(state.get('verificationContract'), dict):
            raise ValueError('Bound parent verification contract required')
        with resolution_context(state, None):
            return _contract_issues(state, 'build', verify_files=False)
    except (OSError, ValueError, KeyError, TypeError) as error:
        return ['Contract definitions BLOCKED: ' + str(error)]


def prerequisite_issues(state, verifier_ids):
    """Inspect selected current proof without changing parent acceptance.

    IDs must come from the coordinator's protected task coverage map. This
    reader cannot authenticate that mapping or authorize native dispatch.
    """
    try:
        if (not isinstance(verifier_ids, list) or not verifier_ids or
                any(not isinstance(v, str) or not v for v in verifier_ids) or
                len(set(verifier_ids)) != len(verifier_ids)):
            raise ValueError('Explicit unique prerequisite verifier IDs required')
        if not isinstance(state.get('verificationContract'), dict):
            raise ValueError('Bound parent verification contract required')
        with resolution_context(state, None):
            failures = _contract_issues(state, 'build', verify_files=False)
            if failures:
                return failures
            path = Path(state['verificationContract']['path'])
            contract = contract_data(path, verify_files=False)
            verifiers = {v['id']: v for v in contract['verifiers']}
            checks = {c.get('verifierId'): c for c in state.get('checks', []) if isinstance(c, dict)}
            for identifier in verifier_ids:
                if identifier not in verifiers:
                    raise ValueError('Unknown prerequisite verifier: ' + identifier)
                verifier = verifiers[identifier]
                proof = proof_binding.definition(verifier, proof_binding.logical(path).parent)
                check = checks.get(identifier)
                if (verifier['gate'] != 'blocking' or not proof or proof['mode'] != 'bound' or
                        'readback' in proof or not isinstance(check, dict) or
                        check.get('stage', 'review') != 'review' or
                        check.get('status') != 'passed' or not present(check, 'evidence')):
                    raise ValueError('Current blocking review proof required: ' + identifier)
            if 'design' in contract:
                from ui_design import evidence_issues
                failures.extend(evidence_issues(contract, path, state))
            failures.extend(proof_binding.issues(contract, path, state, 'review',
                            contract_semantics_sha256(contract), set(verifier_ids)))
            # Completion gaps remain parent obligations at prerequisite review.
            failures.extend('Unresolved contract gap: ' + g['id'] for g in contract['gaps']
                            if g['blocks'] == 'completion')
            return failures
    except (OSError, ValueError, KeyError, TypeError) as error:
        return ['Prerequisite proof BLOCKED: ' + str(error)]


def _contract_issues(state, stage, verify_files=True):
    binding = state.get('verificationContract')
    try:
        ui_required = ui_binding_required(state)
    except (OSError, ValueError, KeyError, TypeError) as error:
        return ['UI binding BLOCKED: ' + str(error)]
    if binding is None:
        return ['Registered substantive UI requires an approved verifier/contract binding.'] if ui_required else []
    if not isinstance(binding, dict) or not present(binding, 'path', 'sha256', 'endpoint'):
        return ['Verification contract binding requires path, sha256 and endpoint.']
    source = Path(binding['path'])
    if proof_binding.sha(source) != binding['sha256']:
        return ['Verification contract changed; rebind explicitly and rerun evidence.']
    contract = contract_data(source, verify_files=verify_files)
    issues = (proof_binding.issues(contract, source, state, stage, contract_semantics_sha256(contract))
              if verify_files else [])
    if ui_required and 'design' not in contract:
        issues.append('Registered substantive UI requires an approved Design Contract.')
    checks = [c for c in state.get('checks', []) if isinstance(c, dict)]
    verifiers = {v['id']: v for v in contract['verifiers']}
    ids = [c['verifierId'] for c in checks if 'verifierId' in c]
    if any(not isinstance(i, str) or i not in verifiers for i in ids) or len(ids) != len(set(ids)):
        issues.append('Check verifier IDs must be unique and belong to the bound contract.')
    for verifier in verifiers.values():
        if stage != 'build' and verifier['gate'] == 'blocking' and not any(c.get('verifierId') == verifier['id'] and (
                not required_at(c, stage) or c.get('status') == 'passed' and present(c, 'evidence')) for c in checks):
            issues.append('Blocking verifier lacks passing evidence: ' + verifier['id'])
    for requirement in contract['requirements']:
        covered = any(v['gate'] == 'blocking' and requirement['id'] in v['covers'] for v in verifiers.values())
        if requirement['priority'] == 'blocking' and not covered and not any(g['requirement'] == requirement['id'] and g['blocks'] in ('implementation', 'completion', 'shipping') for g in contract['gaps']):
            issues.append('Blocking requirement lacks blocking coverage: ' + requirement['id'])
    for gap in contract['gaps']:
        if gap['blocks'] not in ('implementation', 'completion', 'shipping', 'none'):
            issues.append('Invalid gap gate: ' + gap['id'])
        elif (gap['blocks'] == 'implementation' or stage != 'build' and gap['blocks'] == 'completion'
              or stage in ('delivery', 'ship') and gap['blocks'] == 'shipping'):
            issues.append('Unresolved contract gap: ' + gap['id'])
    if stage in ('delivery', 'ship') and state.get('delivery', {}).get('endpoint') != binding['endpoint']:
        issues.append('Delivery endpoint differs from the declared contract endpoint.')
    if 'design' in contract:
        if stage == 'build':
            from ui_design import design_data
            design_data(contract, source.parent)
        else:
            from ui_design import evidence_issues
            issues.extend(evidence_issues(contract, source, state))
    return issues


def schema_three_issues(state, stage):
    """Require attributable endpoints and evidence-shaped external delivery claims."""
    issues = []
    delivery = state.get('delivery')
    if not isinstance(delivery, dict):
        return ['Schema-3 delivery must be an object.']

    multi_target = 'targets' in delivery
    targets_by_id = {}
    if multi_target:
        targets = delivery.get('targets')
        if not isinstance(targets, list) or not targets:
            issues.append('Multi-target delivery requires a nonempty targets list.')
            targets = []
        for index, target in enumerate(targets, start=1):
            if not isinstance(target, dict):
                issues.append(f'Multi-target delivery target {index} must be an object.')
                continue
            target_id = target.get('id')
            if not present(target, 'id', 'revision'):
                issues.append(f'Multi-target delivery target {index} requires a nonempty id and immutable revision.')
                continue
            if target_id in targets_by_id:
                issues.append(f'Multi-target delivery target IDs must be unique: {target_id}')
                continue
            targets_by_id[target_id] = target
        if present(delivery, 'revision') or 'branchDisposition' in delivery:
            issues.append('Multi-target delivery must not declare a singular revision or branch disposition.')

    decision = delivery.get('endpointDecision')
    if not isinstance(decision, dict) or decision.get('status') != 'settled' or not present(decision, 'source', 'evidence'):
        issues.append('Delivery endpoint requires a settled authority source and evidence.')
        decision = {}
    elif decision['source'] not in ('user', 'repository', 'contract'):
        issues.append('Delivery endpoint authority source must be user, repository, or contract.')

    for check in state.get('checks', []):
        if not isinstance(check, dict) or check.get('kind') != 'external_ci' or check.get('status') != 'passed':
            continue
        external = check.get('externalEvidence')
        required_external_fields = (
            ('provider', 'url', 'revision', 'conclusion', 'target')
            if multi_target else ('provider', 'url', 'revision', 'conclusion')
        )
        if not isinstance(external, dict) or not present(external, *required_external_fields):
            issues.append(f"Hosted CI check requires structured external evidence: {check.get('name', '<unnamed>')}")
            continue
        if external['conclusion'] != 'success':
            issues.append(f"Hosted CI conclusion is not success: {check.get('name', '<unnamed>')}")
        if not external['url'].startswith(('https://', 'http://')):
            issues.append(f"Hosted CI evidence requires a run URL: {check.get('name', '<unnamed>')}")
        if multi_target:
            target = targets_by_id.get(external['target'])
            if target is None:
                issues.append(f"Hosted CI target is not declared in delivery targets: {check.get('name', '<unnamed>')}")
            elif external['revision'] != target['revision']:
                issues.append(f"Hosted CI revision differs from delivery target revision: {check.get('name', '<unnamed>')}")
        elif not present(delivery, 'revision') or external['revision'] != delivery['revision']:
            issues.append(f"Hosted CI revision differs from delivery revision: {check.get('name', '<unnamed>')}")

    if stage not in ('ship', 'delivery'):
        return issues

    if multi_target:
        for target_id, target in targets_by_id.items():
            if not present(target, 'evidence'):
                issues.append(f'Multi-target delivery target requires independent readback evidence: {target_id}')
            disposition = target.get('branchDisposition')
            if not isinstance(disposition, dict) or not present(disposition, 'kind'):
                issues.append(f'Multi-target delivery target requires an explicit branch disposition: {target_id}')
                continue
            if disposition['kind'] == 'not_applicable':
                if not present(disposition, 'reason'):
                    issues.append(f'A not-applicable branch disposition requires a reason: {target_id}')
                continue
            if disposition['kind'] not in ('pull_request', 'merged', 'kept_local'):
                issues.append(f'Branch disposition must be pull_request, merged, kept_local, or not_applicable: {target_id}')
                continue
            if disposition.get('status') != 'verified' or not present(disposition, 'evidence', 'revision'):
                issues.append(f'Branch disposition requires verified status, revision, and evidence: {target_id}')
            elif disposition['revision'] != target['revision']:
                issues.append(f'Branch disposition revision differs from its delivery target revision: {target_id}')
            if disposition['kind'] == 'kept_local' and decision.get('source') != 'user':
                issues.append(f'Keeping a task branch local requires user-sourced endpoint authority: {target_id}')
        return issues

    if not present(delivery, 'revision'):
        issues.append('SHIP requires an immutable delivery revision.')

    disposition = delivery.get('branchDisposition')
    if not isinstance(disposition, dict) or not present(disposition, 'kind'):
        issues.append('SHIP requires an explicit branch disposition.')
        return issues
    if disposition['kind'] == 'not_applicable':
        if not present(disposition, 'reason'):
            issues.append('A not-applicable branch disposition requires a reason.')
        return issues
    if disposition['kind'] not in ('pull_request', 'merged', 'kept_local'):
        issues.append('Branch disposition must be pull_request, merged, kept_local, or not_applicable.')
        return issues
    if disposition.get('status') != 'verified' or not present(disposition, 'evidence', 'revision'):
        issues.append('Branch disposition requires verified status, revision, and evidence.')
    elif not present(delivery, 'revision') or disposition['revision'] != delivery['revision']:
        issues.append('Branch disposition revision differs from delivery revision.')
    if disposition['kind'] == 'kept_local' and decision.get('source') != 'user':
        issues.append('Keeping a task branch local requires user-sourced endpoint authority.')
    return issues


def schema_four_issues(state):
    """Require every new session to classify UI work before BUILD."""
    route = state.get('uiRoute')
    if not isinstance(route, dict):
        return ['Schema-4 uiRoute must be an object.']
    kind = route.get('kind')
    if kind == 'pending':
        return ['Classify uiRoute before BUILD: not_applicable, specified, or greenfield.']
    if kind == 'not_applicable':
        return [] if present(route, 'reason') else ['A not-applicable uiRoute requires a scope-specific reason.']
    if kind == 'specified':
        return [] if present(route, 'approvedTarget', 'evidence') else [
            'A specified uiRoute requires an approved target or exact repository pattern and evidence.'
        ]
    if kind != 'greenfield':
        return ['uiRoute kind must be pending, not_applicable, specified, or greenfield.']

    issues = []
    exploration = route.get('exploration', 'broad')
    if not isinstance(exploration, str) or exploration not in ('broad', 'material_choice'):
        issues.append('A greenfield uiRoute exploration must be broad or material_choice.')
    counts = (2, 3) if exploration == 'material_choice' else (3,)
    options = route.get('options')
    if (not isinstance(options, list) or len(options) not in counts or
            any(not isinstance(option, str) or not option.strip() for option in options) or
            len({option.strip() for option in options}) != len(options)):
        issues.append('A greenfield uiRoute requires two or three distinct named visual options for material_choice; broad exploration requires exactly three distinct named visual options.')
        options = []
    if not present(route, 'selectedDirection') or route.get('selectedDirection') not in options:
        issues.append('A greenfield uiRoute requires a selectedDirection from the declared visual options.')
    selection = route.get('selection')
    if (not isinstance(selection, dict) or selection.get('source') != 'user' or
            not present(selection, 'evidence')):
        issues.append('A greenfield uiRoute requires explicit user selection evidence.')
    provenance = route.get('designProvenance')
    if (not isinstance(provenance, dict) or provenance.get('route') != 'product-design' or
            not present(provenance, 'evidence')):
        issues.append('A greenfield uiRoute requires Product Design provenance evidence.')
    mobbin = route.get('mobbin')
    if (not isinstance(mobbin, dict) or mobbin.get('status') not in ('inspected', 'no_comparable') or
            not present(mobbin, 'evidence')):
        issues.append('A greenfield uiRoute requires an inspected Mobbin packet or an evidenced no-comparable disposition.')
    for field in ('affectedSurfaces', 'plannedEvidence'):
        values = route.get(field)
        if not isinstance(values, list) or not values or any(not isinstance(value, str) or not value.strip() for value in values):
            issues.append(f'A greenfield uiRoute requires nonempty {field}.')
    return issues


def task_records(state):
    """Validate the graph once for selection, rendering, scanning, and completion."""
    if not isinstance(state, dict) or state.get('schemaVersion', 1) not in (1, 2, 3, 4):
        raise ValueError('Unsupported or malformed session state.')
    tasks = state.get('tasks', [])
    if not isinstance(tasks, list):
        raise ValueError('Tasks must be a list.')
    by_id = {}
    for task in tasks:
        if not isinstance(task, dict) or not present(task, 'id', 'title', 'acceptance'):
            raise ValueError('Each task requires id, title, and acceptance.')
        if task['id'] in by_id:
            raise ValueError(f"Duplicate task ID: {task['id']}")
        if task.get('kind') not in ('task', 'issue', 'decision'):
            raise ValueError(f"Invalid task kind: {task['id']}")
        if task.get('status') not in ('pending', 'running', 'blocked', 'done', 'cancelled'):
            raise ValueError(f"Invalid task status: {task['id']}")
        required_at(task, 'ship')  # Validate even stages whose acceptance is not yet due.
        deps = task.get('dependsOn', [])
        if not isinstance(deps, list) or any(not isinstance(d, str) or not d.strip() for d in deps):
            raise ValueError(f"dependsOn must contain task IDs: {task['id']}")
        if not isinstance(task.get('owner', ''), str):
            raise ValueError(f"Task owner must be a string: {task['id']}")
        if task['status'] == 'running' and not present(task, 'owner'):
            raise ValueError(f"Running task requires an owner: {task['id']}")
        if task['status'] == 'blocked' and not present(task, 'blocker', 'nextAction'):
            raise ValueError(f"Blocked task requires blocker and nextAction: {task['id']}")
        if task['status'] == 'done' and not present(task, 'evidence'):
            raise ValueError(f"Done task requires evidence: {task['id']}")
        if task['status'] == 'cancelled' and not present(task, 'reason'):
            raise ValueError(f"Cancelled task requires a scope/authority reason: {task['id']}")
        by_id[task['id']] = task
    for task in tasks:
        for dep in task.get('dependsOn', []):
            if dep not in by_id:
                raise ValueError(f"Missing dependency {dep} for {task['id']}")
            if task['status'] == 'done' and by_id[dep]['status'] != 'done':
                raise ValueError(f"Done task has unfinished dependency: {task['id']} -> {dep}")
    try:
        graphlib.TopologicalSorter({t['id']: t.get('dependsOn', []) for t in tasks}).prepare()
    except graphlib.CycleError as error:
        raise ValueError(f'Dependency cycle: {error.args[1]}') from error
    return tasks, by_id


def task_queue(state):
    tasks, by_id = task_records(state)
    ready, waiting = [], []
    for task in tasks:
        if task['status'] in ('done', 'cancelled'):
            continue
        reasons = []
        if not required_at(task, 'ship' if state.get('phase') == 'SHIP' else 'review'):
            reasons.append('Task waits for SHIP.')
        if state.get('complete') is True or state.get('active') is False:
            reasons.append('Session is closed or inactive; inspect its scope before resuming.')
        if state.get('blocker'):
            reasons.append('Session blocker: ' + str(state['blocker']))
        if task['status'] != 'pending':
            reasons.append('Task status: ' + task['status'])
        if task.get('owner', '').strip():
            reasons.append('Claimed by: ' + task['owner'])
        unfinished = [d for d in task.get('dependsOn', []) if by_id[d]['status'] != 'done']
        if unfinished:
            reasons.append('Unfinished prerequisites: ' + ', '.join(unfinished))
        if reasons:
            waiting.append({'task': task, 'reasons': reasons})
        else:
            ready.append(task)
    return {'queueState': ('untracked' if not tasks else 'ready' if ready else 'waiting' if waiting else 'terminal'),
            'ready': ready, 'waiting': waiting}


def scan(root):
    report = []
    invalid = False
    for path in sessions(root):
        record = {'path': str(path)}
        try:
            state = read_json(path / 'state.json')
            queue = task_queue(state)
            if not present(state, 'task') or not isinstance(state.get('complete'), bool):
                raise ValueError('Session requires a task and boolean complete flag.')
            if state['complete'] and not queue['waiting'] and not state.get('issues') and not state.get('blocker'):
                continue
            record.update(task=state['task'], phase=state.get('phase'), active=state.get('active'),
                          complete=state['complete'], blocker=state.get('blocker', ''),
                          issues=state.get('issues', []), lastActivity=state.get('lastActivity', state.get('startedAt')),
                          **queue)
            if state['complete']:
                record['warning'] = 'Recorded complete with unresolved work; inspect without reopening automatically.'
        except (OSError, ValueError, TypeError, KeyError) as error:
            record['error'] = str(error)
            invalid = True
        report.append(record)
    print(json.dumps(report, indent=2))
    return int(invalid)


def graph(state):
    tasks, _ = task_records(state)
    nodes = {t['id']: f'n{i}' for i, t in enumerate(tasks)}
    lines = ['flowchart TD']
    for task in tasks:
        label = f"{task['id']}: {task['title']} ({task['status']})"
        label = ''.join(f'#{ord(c)};' if not c.isascii() or c in '#&"<>[]{}\\\n\r' else c for c in label)
        lines.append(f'  {nodes[task["id"]]}["{label}"]')
        lines.extend(f'  {nodes[dep]} --> {nodes[task["id"]]}' for dep in task.get('dependsOn', []))
    print('\n'.join(lines))
    return 0


def validate(args):
    path = resolve(args)
    state = read_json(path / 'state.json')
    version = state.get('schemaVersion', 1)
    if version == 1:
        issues = legacy_issues(path)
        print('Legacy validation checks recorded flags only; it is not evidence validation.')
        if args.stage == 'ship':
            issues.append('Legacy session has no delivery evidence contract. Continue its manual workflow; do not treat this helper as shipment proof.')
    elif version in (2, 3, 4):
        issues = contract_issues(state, args.stage, path.parent if 'proofResolution' in state else None)
        if version in (3, 4):
            issues.extend(schema_three_issues(state, args.stage))
        if version == 4:
            issues.extend(schema_four_issues(state))
        if state.get('issues'):
            issues.append('Resolve recorded issues before validation.')
        if state.get('blocker'):
            issues.append('Required work is blocked; preserve the incomplete checkpoint.')
        if args.stage == 'build':
            print('\n'.join(f'- {issue}' for issue in issues) if issues else '[OK] BUILD prerequisites recorded; verify the cited evidence independently.')
            return 1 if issues and args.mode == 'fail' else 0
        checks = state.get('checks')
        if not isinstance(checks, list) or not checks:
            issues.append('Record the required acceptance checks before validation.')
        else:
            for check in checks:
                if not isinstance(check, dict) or not present(check, 'name'):
                    issues.append('Check requires a name.')
                elif check.get('status') not in ('pending', 'failed', 'passed', 'not_applicable'):
                    issues.append('Invalid check status: ' + check['name'])
                elif not required_at(check, args.stage):
                    continue
                elif check.get('status') == 'passed' and present(check, 'evidence'):
                    continue
                elif check.get('status') == 'not_applicable' and present(check, 'reason'):
                    continue
                else:
                    issues.append(f"Check lacks passing evidence or a not-applicable reason: {check['name']}")
            if not any(isinstance(c, dict) and required_at(c, args.stage) and c.get('status') == 'passed' and present(c, 'evidence') for c in checks):
                issues.append('At least one acceptance check must have passing evidence.')
        debt = state.get('debt', [])
        if not isinstance(debt, list):
            issues.append('Debt must be a list.')
        else:
            for item in debt:
                if not isinstance(item, dict) or not present(item, 'item'):
                    issues.append('Debt entry requires an item.')
                elif item.get('status') == 'paid' and present(item, 'evidence'):
                    continue
                elif item.get('status') == 'accepted' and present(item, 'acceptance', 'owner', 'paydown'):
                    continue
                else:
                    issues.append(f"Debt is unresolved or acceptance is incomplete: {item['item']}")
        if args.stage in ('delivery', 'ship'):
            delivery = state.get('delivery')
            if not isinstance(delivery, dict) or delivery.get('status') != 'verified' or not present(delivery, 'endpoint', 'evidence'):
                issues.append('Delivery requires a named endpoint and independent readback evidence.')
        elif state.get('complete') is True:
            issues.append('A completed session must be validated with --stage ship.')
    else:
        raise ValueError(f'Unsupported session schema: {version}')
    tasks, _ = task_records(state)
    issues.extend(f"Unfinished {t['kind']}: {t['id']} ({t['status']})"
                  for t in tasks if required_at(t, args.stage) and t['status'] not in ('done', 'cancelled'))
    print('\n'.join(f'- {issue}' for issue in issues) if issues else '[OK] Recorded requirements satisfied; verify the cited evidence independently.')
    return 1 if issues and args.mode == 'fail' else 0


def recovery_report(args):
    from ui_design import inspection_only
    with inspection_only():
        return _recovery_report(args)


def _recovery_report(args):
    """Inspect selected local evidence without claiming ownership or live endpoint truth."""
    path = resolve(args)
    root = Path(args.root).resolve()
    observed = [path / 'state.json', path / 'plan.md', root / '.deep-current.json']

    def fingerprint():
        return {str(item): hashlib.sha256(item.read_bytes()).hexdigest()
                if item.is_file() else None for item in observed}

    before = fingerprint()
    state = read_json(path / 'state.json')
    if not isinstance(state, dict):
        raise ValueError('Checkpoint state must be an object.')
    version = state.get('schemaVersion', 1)
    phase = state.get('phase')
    stage = {'PLAN': 'build', 'BUILD': 'build', 'REVIEW': 'review',
             'SHIP': 'delivery', 'COMPLETE': 'ship'}.get(phase) if isinstance(phase, str) else None
    problems = []
    if type(version) is not int or version not in (1, 2, 3, 4):
        problems.append('Unsupported or malformed schema version.')
    for flag in ('active', 'complete'):
        if flag in state and type(state[flag]) is not bool:
            problems.append('Recorded ' + flag + ' must be boolean.')
    if before[str(path / 'plan.md')] is None:
        problems.append('Checkpoint plan is unavailable; inspect selected checkpoint files.')
    if stage is None:
        problems.append('Recorded phase has no supported stage; inspect checkpoint scope.')
    gates = {}
    for name in ('build', 'review', 'delivery', 'ship'):
        captured = io.StringIO()
        try:
            with redirect_stdout(captured):
                code = validate(argparse.Namespace(root=str(root), path=str(path),
                             session=None, stage=name, mode='fail'))
            diagnostics = [line[2:] for line in captured.getvalue().splitlines() if line.startswith('- ')]
            gates[name] = {'status': 'blocked' if code else 'recorded_satisfied',
                           'issues': diagnostics}
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            gates[name] = {'status': 'unavailable', 'issues': [str(error)]}
    binding = state.get('verificationContract')
    proofs = []
    proof_unavailable = False
    if binding is not None:
        try:
            with resolution_context(state, path.parent if 'proofResolution' in state else None):
                contract = contract_data(Path(binding['path']))
                binding_current = proof_binding.sha(Path(binding['path'])) == binding.get('sha256')
                for verifier in contract['verifiers']:
                    proof = verifier.get('proof') or {}
                    check = next((c for c in state.get('checks', []) if isinstance(c, dict)
                                  and c.get('verifierId') == verifier['id']), None)
                    inspected = 'record_only'
                    diagnostics = []
                    if proof.get('mode') == 'bound':
                        if check is None and verifier['gate'] == 'advisory':
                            inspected = 'not_claimed'
                        elif not binding_current:
                            inspected = 'blocked'
                            diagnostics = ['Verification contract binding changed.']
                        else:
                            diagnostics = proof_binding.issues({'verifiers': [verifier]}, Path(binding['path']),
                                state, 'ship', contract_semantics_sha256(contract))
                            inspected = 'blocked' if diagnostics else 'current_for_ship'
                    proofs.append({'verifierId': verifier['id'], 'gate': verifier['gate'],
                                   'mode': proof.get('mode', 'record_only'),
                                   'readbackDeclared': proof.get('readback') is not None,
                                   'inspection': inspected, 'issues': diagnostics})
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            proof_unavailable = True
            problems.append('Bound proof inspection unavailable: ' + str(error))
    checks = []
    for check in state.get('checks', []) if isinstance(state.get('checks'), list) else []:
        if not isinstance(check, dict):
            continue  # Existing gate validation reports malformed entries.
        try:
            due = [name for name in ('review', 'delivery', 'ship') if required_at(check, name)]
        except (ValueError, TypeError):
            due = []
        checks.append({'name': check.get('name'), 'verifierId': check.get('verifierId'),
                       'recordedStatus': check.get('status', 'pending'),
                       'stage': check.get('stage', 'review'), 'dueAt': due,
                       'receiptRecorded': isinstance(check.get('receipt'), dict),
                       'evidenceRecorded': present(check, 'evidence'),
                       'reason': check.get('reason')})
    bound = any(p['mode'] == 'bound' for p in proofs)
    blockers = list(problems)
    if stage:
        blockers.extend(gates[stage]['issues'])
    if state.get('complete') is True:
        blockers.extend(gates['ship']['issues'])
    blockers = list(dict.fromkeys(blockers))
    local_ship = not problems and gates['ship']['status'] == 'recorded_satisfied'
    report = {
        'schemaVersion': 1, 'checkpoint': str(path), 'sessionId': state.get('sessionId'),
        'recorded': {'schemaVersion': version, 'phase': phase, 'active': state.get('active'),
                     'complete': state.get('complete'), 'task': state.get('task')},
        'inspection': {'scope': 'local retained evidence only', 'checkpointIdentity': before,
                       'stable': True, 'ownership': 'unknown', 'ownerLiveness': 'not_inspected',
                       'authorityAuthenticity': 'not_authenticated',
                       'proofBasis': 'unavailable' if proof_unavailable else 'bound_and_recorded' if bound else 'record_only',
                       'proofFreshness': 'due_ship_gates_satisfied' if bound and local_ship else 'not_established',
                       'liveEndpoint': 'not_inspected'},
        'currentStage': stage, 'stages': gates, 'checks': checks, 'proofs': proofs,
        'delivery': {'recorded': state.get('delivery'),
                     'retainedReadback': 'current_for_ship' if local_ship and any(
                         p['readbackDeclared'] and p['inspection'] == 'current_for_ship' for p in proofs) else 'not_established',
                     'liveEndpoint': 'not_inspected'},
        'localShipRequirementsSatisfied': local_ship,
        'completionTruth': 'not_authenticated_by_report', 'blockers': blockers,
        'nextSafeAction': ('Inspect the listed blockers and current authority before changing or resuming this checkpoint.'
                           if blockers else 'Inspect cited evidence, endpoint truth, and ownership before any authorized next action.'),
    }
    if fingerprint() != before:
        raise ValueError('Checkpoint or locator changed during inspection; discard this report and inspect again.')
    if getattr(args, 'json', False):
        print(json.dumps(report, indent=2))
    else:
        print(f"Session: {path}\nRecorded phase: {phase}\nRecorded complete: {state.get('complete')}\n"
              f"Current stage: {stage}\nProof basis: {report['inspection']['proofBasis']}\n"
              f"Proof freshness: {report['inspection']['proofFreshness']}\nOwnership: unknown\n"
              "Live endpoint: not inspected\nCompletion truth: not authenticated by report")
        for name, gate in gates.items():
            print(f"{name}: {gate['status']}")
        for issue in blockers:
            print('- ' + issue)
        print('Next safe action: ' + report['nextSafeAction'])
    return int(bool(blockers))


def complete_session(args):
    """Validate SHIP against one preimage, then atomically close that checkpoint."""
    root = Path(args.root).resolve()
    path = resolve(args)
    state_path = path / 'state.json'
    preimage = state_path.read_bytes()
    state = json.loads(preimage.decode('utf-8-sig'))
    if state.get('complete') is True and state.get('active') is False and state.get('phase') == 'COMPLETE':
        if validate(argparse.Namespace(root=str(root), path=str(path), session=None, stage='ship', mode='fail')):
            return 1
        print(f'Session already complete: {path}')
        return 0
    if state.get('phase') != 'SHIP' or state.get('active') is not True or state.get('complete') is not False:
        print('- Completion requires an active, incomplete checkpoint in SHIP.', file=sys.stderr)
        return 1
    if validate(argparse.Namespace(root=str(root), path=str(path), session=None, stage='ship', mode='fail')):
        return 1
    with checkpoint_lock(root):
        if state_path.read_bytes() != preimage:
            raise ValueError('Checkpoint changed after SHIP validation; revalidate before completion.')
        state.update(active=False, complete=True, phase='COMPLETE')
        write_json(state_path, state)
    closed = read_json(state_path)
    if closed.get('active') is not False or closed.get('complete') is not True or closed.get('phase') != 'COMPLETE':
        raise ValueError('Completed checkpoint readback failed.')
    print(f'Session completed after SHIP validation: {path}')
    return 0


def file_manifest(path):
    """Exact regular files/directories only; refuse links and Windows junctions."""
    def check(item):
        info = item.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError(f'Linked/reparse paths cannot be archived: {item}')
        if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise ValueError(f'Unsupported archive path: {item}')
    check(path)
    if path.is_file():
        return {'.': hashlib.sha256(path.read_bytes()).hexdigest()}
    result = {}
    for directory, dirs, files in os.walk(path, followlinks=False):
        for name in dirs + files:
            item = Path(directory) / name
            check(item)
            result[item.relative_to(path).as_posix()] = (
                None if item.is_dir() else hashlib.sha256(item.read_bytes()).hexdigest())
    return result


def git_command(root, *arguments):
    result = subprocess.run(['git', '-C', str(root), *arguments], capture_output=True, text=True)
    if result.returncode:
        raise ValueError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def verify_archive(archive, allow_unfinalized=False):
    if (archive / 'handoff.json').exists():
        raise ValueError('Active handoff packets cannot authorize archive retirement or finalization.')
    manifest = read_json(archive / 'archive.json')
    session_id = manifest['sessionId']
    root = Path(manifest['sourceRoot'])
    if not isinstance(session_id, str) or len(session_id) != 8 or not session_id.isalnum():
        raise ValueError('Invalid preserved session identity.')
    if not root.is_absolute() or str(root / f'.deep-{session_id}') != manifest['sourcePath']:
        raise ValueError('Preserved checkpoint identity is inconsistent.')
    if archive.resolve().is_relative_to(root.resolve()):
        raise ValueError('Archive must remain outside its source checkout.')
    if manifest['files'].get('snapshot') != manifest['sourceFiles']:
        raise ValueError('Original snapshot manifest is missing or inconsistent.')
    if manifest.get('gitHead') and 'source.bundle' not in manifest['files']:
        raise ValueError('Source history manifest is missing.')
    for relative, expected in manifest['files'].items():
        target = archive / relative
        if Path(relative).is_absolute() or not target.resolve().is_relative_to(archive.resolve()):
            raise ValueError('Archive manifest path escapes its archive.')
        if file_manifest(target) != expected:
            raise ValueError(f'Archive bytes changed: {relative}')
    original = read_json(archive / 'snapshot/state.json')
    if original.get('sessionId') != session_id or original.get('active') is not False:
        raise ValueError('Original checkpoint identity or quiescence changed.')
    checkpoint = archive / 'checkpoint'
    file_manifest(checkpoint)
    working = read_json(checkpoint / 'state.json')
    if working.get('sessionId') != session_id or not (checkpoint / 'plan.md').is_file():
        raise ValueError('Working archive checkpoint identity differs.')
    if ('uiEvidence' in original or 'uiEvidence' in working or 'proofResolution' in working
            or manifest.get('resolutionBinding') is not None or manifest.get('resolution') is not None):
        resolution_file = archive/'resolution.json'
        if not resolution_file.is_file():
            raise ValueError('Archive lacks portable UI bindings or proof resolution')
        expected_binding = manifest.get('resolutionBinding')
        if not isinstance(expected_binding, dict) or expected_binding.get('sha256') != file_manifest(resolution_file)['.']:
            raise ValueError('Archive resolution digest differs')
        if working.get('proofResolution') != expected_binding or manifest.get('resolution') != read_json(resolution_file):
            raise ValueError('Archive resolution identity differs from preserved map')
        for key in ('verificationContract', 'uiEvidence'):
            if working.get(key) != original.get(key):
                raise ValueError('Approved archived proof identity changed: ' + key)
        problems = contract_issues(working, 'delivery', archive)
        if problems:
            raise ValueError('Archived acceptance proof failed: ' + '; '.join(problems))
    receipt = archive / 'final.json'
    if receipt.exists():
        final = read_json(receipt)
        if file_manifest(checkpoint / 'state.json') != final['state'] or file_manifest(archive / 'closeout-evidence') != final['evidence']:
            raise ValueError('Final checkpoint or closeout evidence changed.')
    elif working.get('complete') is True and not allow_unfinalized:
        raise ValueError('Finalization was interrupted; resume finalize-archive with the same evidence.')
    if manifest.get('gitHead'):
        # A real fetch into an empty repository proves this bundle is self-contained.
        with tempfile.TemporaryDirectory() as temporary:
            restored = Path(temporary)
            git_command(restored, 'init', '--bare')
            git_command(restored, 'fetch', '--no-tags', str(archive / 'source.bundle'), 'HEAD')
            if git_command(restored, 'rev-parse', 'FETCH_HEAD') != manifest['gitHead']:
                raise ValueError('Restored source tip differs from the preserved tip.')
    return manifest


def preserve(args):
    root, source = Path(args.root).resolve(), resolve(args)
    destination = Path(args.destination).absolute()
    state = read_json(source / 'state.json')
    session_id = state['sessionId']
    if len(session_id) != 8 or not session_id.isalnum() or source != root / f'.deep-{session_id}':
        raise ValueError('Preserve requires the exact direct checkpoint under --root.')
    if state.get('schemaVersion') not in (2, 3, 4) or state.get('active') is not False or state.get('phase') not in ('SHIP', 'COMPLETE'):
        raise ValueError('Preserve requires a quiesced schema-2/3/4 SHIP/COMPLETE checkpoint.')
    if validate(argparse.Namespace(root=str(root), path=str(source), session=None, stage='delivery', mode='fail')):
        raise ValueError('Acceptance and delivery checks must pass before preservation.')
    closeout_verifiers = []
    binding_for_closeout = state.get('verificationContract')
    if binding_for_closeout:
        contract_for_closeout = contract_data(Path(binding_for_closeout['path']))
        checks_by_id = {c.get('verifierId'): c for c in state.get('checks', []) if isinstance(c, dict)}
        for verifier in contract_for_closeout['verifiers']:
            check = checks_by_id.get(verifier['id'], {})
            if verifier.get('proof', {}).get('mode') == 'bound' and check.get('stage') == 'closeout':
                closeout_verifiers.append(verifier)
                problems = proof_binding.issues(
                    {'verifiers': [verifier]}, Path(binding_for_closeout['path']), state,
                    'ship', contract_semantics_sha256(contract_for_closeout))
                if problems:
                    raise ValueError('Preserve cannot archive unresolved bound closeout proof; '
                                     'complete it while its declared inputs remain available or retain the checkpoint.')
    dependencies = set()
    with proof_binding.files_context(trace=dependencies):
        issues = _contract_issues(state, 'delivery')
        if closeout_verifiers:
            issues.extend(proof_binding.issues({'verifiers': closeout_verifiers},
                Path(binding_for_closeout['path']), state, 'ship', contract_semantics_sha256(contract_for_closeout)))
    if issues:
        raise ValueError('Preservation proof is incomplete: ' + '; '.join(issues))
    portable = bool('uiEvidence' in state or dependencies and any(v.get('proof', {}).get('mode') == 'bound'
                    for v in contract_data(Path(state['verificationContract']['path']))['verifiers']))
    source_files = file_manifest(source)
    if destination.resolve().is_relative_to(root):
        raise ValueError('Archive must be outside the checkout.')
    repository = subprocess.run(['git', '-C', str(root), 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
    git_root = Path(repository.stdout.strip()).resolve() if repository.returncode == 0 else None
    if git_root and destination.resolve().is_relative_to(git_root):
        raise ValueError('Archive must be outside the repository.')
    save_history = git_root and not args.checkpoint_only
    if save_history and git_command(root, 'status', '--porcelain', '--untracked-files=all'):
        raise ValueError('Preserve source history only from a clean checkout; resolve dirty paths first.')
    includes = [Path(p).absolute() for p in args.include]
    binding = state.get('verificationContract')
    if binding:
        includes.append(Path(binding['path']).absolute())
    if portable:
        includes.extend(Path(name) for name in sorted(dependencies))
    inputs = [(p, file_manifest(p)) for p in dict.fromkeys(includes)]
    if any(destination.resolve().is_relative_to(p.resolve()) for p, _ in inputs):
        raise ValueError('Included evidence cannot contain its destination archive.')
    if destination.exists():
        saved = verify_archive(destination)
        if saved['sourcePath'] != str(source) or saved['sourceFiles'] != source_files:
            raise ValueError('Existing archive belongs to different or changed source.')
        if saved.get('gitHead') != (git_command(root, 'rev-parse', 'HEAD') if save_history else None):
            raise ValueError('Source history differs from existing preservation.')
        if set(saved['locations']) != {str(p) for p, _ in inputs}:
            raise ValueError('Requested evidence differs from existing preservation.')
        for original, expected in inputs:
            if file_manifest(Path(saved['locations'][str(original)])) != expected:
                raise ValueError('Included evidence differs from existing preservation.')
        print(f'Existing preservation verified: {destination}')
        return 0
    destination.mkdir(parents=True, exist_ok=False)
    shutil.copytree(source, destination / 'snapshot')
    files = {'snapshot': source_files}
    locations = {}
    for index, (original, expected) in enumerate(inputs):
        relative = f'includes/{index}/{original.name}'
        target = destination / relative
        target.parent.mkdir(parents=True)
        if original.is_dir():
            shutil.copytree(original, target)
        else:
            shutil.copy2(original, target)
        if file_manifest(original) != expected:
            raise ValueError('Included evidence changed during preservation; source retained.')
        files[relative] = expected
        locations[str(original)] = str(target)
    head = None
    if save_history:
        head = git_command(root, 'rev-parse', 'HEAD')
        git_command(root, 'bundle', 'create', str(destination / 'source.bundle'), 'HEAD')
        if git_command(root, 'rev-parse', 'HEAD') != head or git_command(root, 'status', '--porcelain', '--untracked-files=all'):
            raise ValueError('Source tip changed during preservation.')
        files['source.bundle'] = file_manifest(destination / 'source.bundle')
    if file_manifest(source) != source_files:
        raise ValueError('Checkpoint changed during preservation; source retained.')
    resolution = None
    if portable:
        mapping = {}
        for original, expected in inputs:
            target = Path(locations[str(original)])
            if original.is_file():
                mapping[str(original.resolve())] = {'path': target.relative_to(destination).as_posix(), 'sha256': expected['.']}
            else:
                for name, digest in expected.items():
                    if digest is not None:
                        mapping[str((original/name).resolve())] = {'path': (target/name).relative_to(destination).as_posix(), 'sha256': digest}
        write_json(destination/'resolution.json', {'schemaVersion': 1, 'files': mapping})
        files['resolution.json'] = file_manifest(destination/'resolution.json')
        resolution = {'path': str((destination/'resolution.json').resolve()), 'sha256': files['resolution.json']['.']}
    manifest = {'sourceRoot': str(root), 'sourcePath': str(source), 'sessionId': session_id,
                'sourceFiles': source_files, 'files': files, 'locations': locations, 'gitHead': head, 'resolution': read_json(destination/'resolution.json') if resolution else None, 'resolutionBinding': resolution}
    write_json(destination / 'archive.json', manifest)
    checkpoint = destination / 'checkpoint'
    checkpoint.mkdir()
    shutil.copy2(source / 'plan.md', checkpoint / 'plan.md')
    if resolution:
        state['proofResolution'] = resolution
    elif binding:
        state['verificationContract']['path'] = locations[str(Path(binding['path']).absolute())]
    state.update(active=False, complete=False, phase='SHIP')
    state['checks'] = [c for c in state['checks'] if c['name'] != 'Post-ship closeout']
    state['checks'].append({'name': 'Post-ship closeout', 'stage': 'closeout', 'status': 'pending'})
    write_json(checkpoint / 'state.json', state)
    verify_archive(destination)
    print(f'Preserved and integrity-verified: {destination}; final checkpoint: {checkpoint}')
    return 0


def retire_checkpoint(args):
    archive = Path(args.archive).resolve()
    saved = verify_archive(archive)
    root = Path(args.root).resolve()
    source = root / f".deep-{saved['sessionId']}"
    if str(root) != saved['sourceRoot'] or str(source) != saved['sourcePath']:
        raise ValueError('Archive does not authorize this checkpoint/root.')
    with checkpoint_lock(root):
        if source.exists():
            if file_manifest(source) != saved['sourceFiles']:
                raise ValueError('Checkpoint changed since preservation; leave it intact.')
            shutil.rmtree(source)
        pointer = root / '.deep-current.json'
        if pointer.exists():
            current = read_json(pointer)
            if current.get('sessionId') == saved['sessionId'] and current.get('path') == str(source):
                pointer.unlink()
    print('Exact preserved checkpoint retired; unrelated pointer/session retained.')
    return 0


def finalize_archive(args):
    archive = Path(args.archive).resolve()
    saved = verify_archive(archive, allow_unfinalized=True)
    if Path(saved['sourcePath']).exists():
        raise ValueError('Retire the selected live checkpoint before finalization.')
    evidence = Path(args.evidence).absolute()
    expected = file_manifest(evidence)
    if not evidence.is_file():
        raise ValueError('Closeout evidence must be a saved file inspected by the coordinator.')
    target = archive / 'closeout-evidence'
    if target.exists():
        if file_manifest(target) != expected:
            raise ValueError('Existing final evidence differs; retain it and resolve drift.')
    else:
        shutil.copy2(evidence, target)
    if file_manifest(target) != expected or file_manifest(evidence) != expected:
        raise ValueError('Final evidence changed during copying; keep incomplete.')
    checkpoint = archive / 'checkpoint'
    state = read_json(checkpoint / 'state.json')
    checks = [c for c in state['checks'] if c['name'] == 'Post-ship closeout']
    if len(checks) != 1:
        raise ValueError('Archived checkpoint must retain its closeout gate.')
    checks[0].update(status='passed', evidence=f'{target}; SHA256 {expected["."]}')
    write_json(checkpoint / 'state.json', state)
    if validate(argparse.Namespace(root=str(archive), path=str(checkpoint), session=None, stage='ship', mode='fail')):
        raise ValueError('Archived SHIP requirements are not satisfied; keep incomplete.')
    state.update(active=False, complete=True, phase='COMPLETE')
    write_json(checkpoint / 'state.json', state)
    write_json(archive / 'final.json', {'state': file_manifest(checkpoint / 'state.json'), 'evidence': expected})
    verify_archive(archive)
    print('Archived checkpoint COMPLETE; supplied closeout evidence is recorded, not authenticated by this helper.')
    return 0



def independent_batch(checks):
    """Validate explicit execution authority and a closed acyclic graph before effects."""
    ids = [c.get('id') for c in checks]
    if any(not isinstance(i, str) or not i.strip() for i in ids) or len(ids) != len(set(ids)):
        raise ValueError('Collection requires unique nonempty check IDs')
    known = set(ids)
    for c in checks:
        deps = c.get('dependsOn')
        if (type(c.get('safe')) is not bool or type(c.get('required', True)) is not bool
                or not isinstance(deps, list) or any(not isinstance(d, str) for d in deps)
                or len(deps) != len(set(deps)) or any(d not in known for d in deps)):
            raise ValueError('Collection requires explicit boolean safe and dependency IDs; required must be boolean')
    by_id = {c['id']: c for c in checks}
    try:
        list(graphlib.TopologicalSorter({c['id']: c['dependsOn'] for c in checks}).static_order())
        order = []
        while len(order) < len(checks):
            order.append(next(c['id'] for c in checks if c['id'] not in order and all(i in order for i in c['dependsOn'])))
    except graphlib.CycleError as error:
        raise ValueError('Collection dependency graph contains a cycle') from error
    return [by_id[i] for i in order]


def run_checks(args):
    checks = read_json(Path(args.checks))
    if not isinstance(checks, list) or not checks or any(
        not isinstance(c, dict) or not present(c, 'name') or not isinstance(c.get('argv'), list)
        or not c['argv'] or any(not isinstance(a, str) or not a for a in c['argv']) for c in checks
    ):
        raise ValueError('Checks must be a nonempty list of named argv commands; shell chains are not parsed.')
    collect = getattr(args, 'collect_independent', False)
    if collect:
        checks = independent_batch(checks)
    context = None
    if getattr(args, 'ui_request', None):
        from ui_design import design_data, route, source_identity, sha, bound_file
        if not all((args.contract, args.goal_id, args.source_manifest, args.environment_manifest)):
            raise ValueError('UI execution requires contract, goal ID, source and environment manifests')
        source_path = Path(args.contract).resolve()
        contract = contract_data(source_path)
        design = design_data(contract, source_path.parent)
        request = ui_request(args.ui_request)
        decision = route(read_json(Path(request['path'])), source_path)
        if decision['status'] == 'BLOCKED':
            raise ValueError(decision['diagnostic'])
        verifiers = {v['id']: v for v in contract['verifiers']}
        ids = [c.get('verifierId') for c in checks]
        expected = {i for group in design['verification'].values() for i in group
                    if 'max_diff_ratio' not in verifiers[i]['threshold']}
        if len(ids) != len(set(ids)) or set(ids) != expected:
            raise ValueError('UI execution batch must cover exactly the independent declared verifier IDs')
        for check in checks:
            verifier = verifiers[check['verifierId']]
            bound_file(verifier['implementation'], source_path.parent)
            if check['argv'] != verifier['argv']:
                raise ValueError('UI command differs from approved verifier declaration')
        context = {'goal_id': args.goal_id, 'subject': {
            'source_fingerprint': source_identity(Path(args.source_manifest)),
            'contract_fingerprint': sha(source_path),
            'environment_fingerprint': sha(Path(args.environment_manifest))},
            'request_sha256': request['sha256'], 'route': decision,
            'route_fingerprint': sha(Path(__file__).with_name('ui_design.py'))}
    elif getattr(args, 'contract', None):
        if not getattr(args, 'goal_id', None) or any(getattr(args, key, None) for key in ('source_manifest', 'environment_manifest')):
            raise ValueError('Generic bound execution requires contract and goal ID; manifests come from approved declarations')
        source_path = Path(args.contract).resolve()
        contract = contract_data(source_path)
        verifiers = {v['id']: v for v in contract['verifiers']}
        ids = [c.get('verifierId') for c in checks]
        if len(ids) != len(set(ids)) or any(i not in verifiers for i in ids):
            raise ValueError('Bound execution requires unique declared verifier IDs')
        generic = {}
        for check in checks:
            proof = proof_binding.definition(verifiers[check['verifierId']], source_path.parent)
            if not proof or proof['mode'] != 'bound' or check['argv'] != proof['argv']:
                raise ValueError('Generic command differs from approved bound verifier declaration')
            if str(Path(proof.get('working_directory', source_path.parent)).resolve()) != str(Path(args.root).resolve()):
                raise ValueError('Bound execution working directory differs from declaration')
            if 'readback' in proof and (source_path.parent/proof['readback']['result']).exists():
                raise ValueError('Readback result already exists; preserve it and declare a fresh output before rerun')
            generic[check['verifierId']] = (proof, proof_binding.identity(proof, source_path.parent),
                [proof_binding.sha(source_path.parent/t['artifact']) for t in proof['readback']['targets']] if 'readback' in proof else None)
        context = {'generic': generic, 'semantics': contract_semantics_sha256(contract), 'contract_hash': proof_binding.sha(source_path)}
    elif any(getattr(args, name, None) for name in ('goal_id', 'source_manifest', 'environment_manifest')):
        raise ValueError('Bound execution requires --contract')
    if collect and context:
        for check in checks:
            verifier = verifiers[check['verifierId']]
            required = verifier.get('gate') == 'blocking'
            if 'required' in check and check['required'] != required:
                raise ValueError('Collection required flag contradicts authoritative verifier gate')
            check['required'] = required
    # Exclusive result creation preserves prior evidence and refuses accidental reruns.
    with Path(args.output).open('x', encoding='utf-8') as output:
        results = []
        outcomes = {}
        aggregate = 0
        for check in checks:
            if collect:
                blocked = [i for i in check['dependsOn'] if outcomes[i] != 'passed']
                reason = ('Execution not explicitly safe' if not check['safe'] else
                          'Dependencies did not pass: ' + ', '.join(blocked) if blocked else None)
                if reason:
                    row = dict(id=check['id'], name=check['name'], argv=check['argv'],
                               required=check.get('required', True), dependsOn=check['dependsOn'],
                               status='skipped', reason=reason, exitCode=None, stdout='', stderr='')
                    results.append(row); outcomes[check['id']] = 'skipped'
                    if row['required']:
                        aggregate = aggregate or 1
                    output.seek(0); json.dump(results, output, indent=2); output.truncate(); output.flush()
                    print(f"{check['name']}: skipped: {reason}")
                    continue
            if context and 'generic' not in context:
                from ui_design import bound_file, sha
                fingerprint = sha(bound_file(verifiers[check['verifierId']]['implementation'], source_path.parent))
            started = datetime.datetime.now(datetime.timezone.utc).isoformat()
            launch_error = None
            try:
                result = subprocess.run(check['argv'], cwd=args.root, capture_output=True, text=True, encoding='utf-8', errors='replace')
                code, stdout, stderr = result.returncode, result.stdout, result.stderr
            except OSError as error:
                code, stdout, stderr = 127, '', str(error)
                launch_error = str(error)
            row = dict(name=check['name'], argv=check['argv'], startedAt=started,
                                cwd=str(Path(args.root).resolve()), exitCode=code,
                                finishedAt=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                status='passed' if code == 0 else 'failed', stdout=stdout, stderr=stderr)
            if collect:
                row.update(id=check['id'], required=check.get('required', True), dependsOn=check['dependsOn'],
                           nativeExitCode=code if launch_error is None else None, nativeStdout=stdout, nativeStderr=stderr if launch_error is None else '')
                if launch_error is not None:
                    row['launchError'] = launch_error
            if context and 'generic' in context:
                proof, preimage, subjects = context['generic'][check['verifierId']]
                try:
                    current = (proof_binding.identity(proof, source_path.parent) == preimage
                               and proof_binding.sha(source_path) == context['contract_hash'])
                    saved_artifacts = proof_binding.artifacts(proof, source_path.parent)
                    if 'readback' in proof:
                        row['readback'] = proof_binding.readback_observation(proof, source_path.parent)
                        current = current and subjects == [proof_binding.sha(source_path.parent/t['artifact']) for t in proof['readback']['targets']]
                except (OSError, ValueError, KeyError, TypeError):
                    current, saved_artifacts = False, []
                if not current:
                    code = 2
                    row.update(exitCode=code, status='failed', stderr=stderr+'\nBound inputs/artifacts drifted or missing during execution')
                row.update(proof_mode='bound', verifier_id=check['verifierId'], goal_id=args.goal_id,
                           contract_semantics=context['semantics'], identity=preimage, artifacts=saved_artifacts,
                           runtime=proof_binding.runtime_identity())
            elif context:
                from ui_design import bound_file, source_identity, sha
                verifier = verifiers[check['verifierId']]
                try:
                    current = (sha(bound_file(verifier['implementation'], source_path.parent)) == fingerprint
                               and source_identity(Path(args.source_manifest)) == context['subject']['source_fingerprint']
                               and sha(source_path) == context['subject']['contract_fingerprint']
                               and sha(Path(args.environment_manifest)) == context['subject']['environment_fingerprint']
                               and sha(Path(args.ui_request)) == context['request_sha256'])
                except (OSError, ValueError, KeyError, TypeError):
                    current = False
                if not current:
                    code = 2
                    row.update(exitCode=code, status='failed', stderr=stderr+'\nUI inputs drifted during execution')
                row.update(context, verifier_id=verifier['id'], verifier_fingerprint=fingerprint)
            results.append(row)
            output.seek(0); json.dump(results, output, indent=2); output.truncate(); output.flush()
            print(f"{check['name']}: exit {code}")
            if collect:
                outcomes[check['id']] = row['status']
                if code:
                    aggregate = aggregate or (code if code > 0 else 1)
            elif code:
                return code if code > 0 else 1
    return aggregate


def handoff(args):
    from active_handoff import create
    return create(args, sys.modules[__name__])


def inspect_handoff(args):
    from active_handoff import inspect
    return inspect(args, sys.modules[__name__])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='.', help='Project root')
    commands = parser.add_subparsers(dest='command', required=True)
    runner = commands.add_parser('run-checks', help='Run named argv verifiers, stopping at the first failure')
    runner.add_argument('--checks', required=True)
    runner.add_argument('--output', required=True)
    runner.add_argument('--collect-independent', action='store_true', help='Collect explicitly safe checks with declared IDs and dependencies')
    for option in ('ui-request', 'contract', 'goal-id', 'source-manifest', 'environment-manifest'):
        runner.add_argument('--' + option)
    create = commands.add_parser('init', help='Create a two-file session')
    create.add_argument('--task', required=True)
    create.add_argument('--session')
    create.add_argument('--ui-request')
    commands.add_parser('exclude', help='Locally ignore existing and future checkpoints in Git')
    commands.add_parser('list', help='List sessions')
    commands.add_parser('scan', help='Read-only report of unfinished or invalid sibling sessions')
    packet = commands.add_parser('handoff', help='Save an active read-only packet; no transferred authority')
    packet.add_argument('--path', required=True)
    packet.add_argument('--references', required=True)
    packet.add_argument('--output', required=True)
    reader = commands.add_parser('inspect-handoff', help='Verify retained packet bytes and inspect without live fallback')
    reader.add_argument('--packet', required=True)
    for name in ('verify-archive', 'retire-checkpoint', 'finalize-archive'):
        command = commands.add_parser(name)
        command.add_argument('--archive', required=True)
        if name == 'finalize-archive':
            command.add_argument('--evidence', required=True)
    for name in ('status', 'recovery-report', 'use', 'validate', 'complete', 'next', 'graph', 'bind-contract', 'refresh-contract', 'preserve'):
        command = commands.add_parser(name)
        command.add_argument('--session')
        command.add_argument('--path')
        if name == 'recovery-report':
            command.add_argument('--json', action='store_true', help='Emit read-only inspection as JSON on stdout')
        if name == 'preserve':
            command.add_argument('--destination', required=True)
            command.add_argument('--include', action='append', default=[])
            command.add_argument('--checkpoint-only', action='store_true', help='Preserve checkpoint/evidence only; supplies no branch-history retirement proof')
        if name in ('bind-contract', 'refresh-contract'):
            command.add_argument('--contract', required=True)
            command.add_argument('--endpoint', required=True)
        if name == 'bind-contract':
            command.add_argument('--ui-request')
        if name == 'validate':
            command.add_argument('--stage', choices=('build', 'review', 'ship'), default='review')
            command.add_argument('--mode', choices=('warn', 'fail'), default='fail')
    args = parser.parse_args()
    try:
        root = Path(args.root).resolve()
        if args.command == 'handoff':
            return handoff(args)
        if args.command == 'inspect-handoff':
            return inspect_handoff(args)
        if args.command == 'run-checks':
            return run_checks(args)
        if args.command == 'preserve':
            return preserve(args)
        if args.command == 'verify-archive':
            saved = verify_archive(Path(args.archive).resolve())
            print('Archive bytes and original Git tip restore verified; live cleanup not assessed.' if saved.get('gitHead')
                  else 'Archive checkpoint/evidence bytes verified; no Git history preserved. Live cleanup not assessed.')
            return 0
        if args.command == 'retire-checkpoint':
            return retire_checkpoint(args)
        if args.command == 'finalize-archive':
            return finalize_archive(args)
        if args.command == 'init':
            return init(args)
        if args.command == 'exclude':
            exclude_checkpoints(root)
            return 0
        if args.command == 'list':
            print('\n'.join(str(p) for p in sessions(root)))
            return 0
        if args.command == 'validate':
            return validate(args)
        if args.command == 'recovery-report':
            return recovery_report(args)
        if args.command == 'complete':
            return complete_session(args)
        if args.command == 'bind-contract':
            return bind_contract(args)
        if args.command == 'refresh-contract':
            return refresh_contract(args)
        if args.command == 'scan':
            return scan(root)
        path = resolve(args)
        state = read_json(path / 'state.json')
        if args.command == 'next':
            print(json.dumps(task_queue(state), indent=2))
            return 0
        if args.command == 'graph':
            return graph(state)
        if args.command == 'use':
            set_current(root, path)
        print(f"Session: {path}\nPhase: {state.get('phase')}\nActive: {state.get('active')}\nTask: {state.get('task', '')}")
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(f'[ERROR] {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
