"""Read-only UI routing/gates and a bound adapter to the existing pixel comparator.
No design generation, approval issuance, capture engine, or transition controller.
"""
import argparse
from contextlib import contextmanager
from contextvars import ContextVar
from proof_binding import logical, resolve_file, files_context
import datetime
import hashlib
import json
import math
import operator
from pathlib import Path
import subprocess
import sys
import tempfile

PACKAGE = Path(__file__).resolve().parents[1]
PIXEL = PACKAGE / 'scripts/pixel_diff.py'
SMALL = {'typo', 'color', 'asset', 'spacing', 'accessibility', 'existing_component'}
SUBSTANTIVE = {'navigation', 'composition', 'hierarchy', 'flow', 'visual_system', 'redesign'}
_INSPECTION_ONLY = ContextVar('deep_loop_ui_inspection_only', default=False)

@contextmanager
def inspection_only():
    token = _INSPECTION_ONLY.set(True)
    try:
        yield
    finally:
        _INSPECTION_ONLY.reset(token)

OPERATORS = {'==': operator.eq, '<=': operator.le, '>=': operator.ge, '<': operator.lt, '>': operator.gt}

def read(path):
    return json.loads(resolve_file(path).read_text(encoding='utf-8-sig'))

def sha(path):
    return hashlib.sha256(resolve_file(path).read_bytes()).hexdigest()

def design_sha(design):
    body = {k: v for k, v in design.items() if k != 'approval'}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode('utf-8')).hexdigest()

def verification_sha(contract):
    ids = {i for items in contract['design']['verification'].values() for i in items}
    declarations = sorted((v for v in contract['verifiers'] if v['id'] in ids), key=lambda v: v['id'])
    return hashlib.sha256(json.dumps(declarations, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode('utf-8')).hexdigest()

def schema_check(data, name):
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError as error:
        raise ValueError('BLOCKED: installed jsonschema dependency is unavailable') from error
    errors = list(Draft202012Validator(read(PACKAGE / 'assets' / name),
                                      format_checker=FormatChecker()).iter_errors(data))
    if errors:
        raise ValueError('; '.join(e.message for e in errors))

def bound_file(record, base):
    path = (logical(base) / record['path']).resolve()
    if sha(path) != record['sha256']:
        raise ValueError('Bound file changed: ' + str(path))
    return resolve_file(path)

def case_key(case):
    keys = ('screen', 'reference', 'viewport', 'state')
    if not isinstance(case, dict) or any(not isinstance(case.get(k), str) or not case[k].strip() for k in keys):
        raise ValueError('UI case requires screen, reference, viewport and state')
    return tuple(case[k] for k in keys)


def required_cases(contract):
    design = contract['design']
    verifiers = {v['id']: v for v in contract['verifiers']}
    coverage = [verifiers[i] for i in design['verification']['responsive']
                if 'required_cases' in verifiers[i].get('fixture', {})]
    if len(coverage) != 1:
        raise ValueError('UI requires one approved coverage verifier with fixture.required_cases')
    cases = coverage[0]['fixture']['required_cases']
    if not isinstance(cases, list) or not cases or len({case_key(c) for c in cases}) != len(cases):
        raise ValueError('Required UI cases must be nonempty and unique')
    return cases


def critical_requirements(contract):
    result = []
    for invariant in contract['design']['critical_invariants']:
        matches = [r for r in contract['requirements'] if invariant in (r['id'], r['invariant'])]
        if len(matches) != 1 or matches[0]['priority'] != 'blocking':
            raise ValueError('Critical invariant requires one blocking parent requirement: ' + invariant)
        result.append(matches[0]['id'])
    if len(result) != len(set(result)):
        raise ValueError('Duplicate critical requirement mapping')
    return set(result)


def capture_data(capture, capture_path, viewport):
    from PIL import Image
    base = logical(capture_path).parent
    actual = bound_file(capture['image'], base)
    original = bound_file(capture['original'], base)
    scale = viewport['device_scale_factor']
    default = {'width': viewport['width'], 'height': viewport['height'],
               'device_scale_factor': scale, 'crop': [0, 0, viewport['width'], viewport['height']],
               'frame': [0, 0, viewport['width'], viewport['height']], 'scroll_top': 0}
    geometry = viewport['conditions'].get('capture_geometry', default)
    observed = capture['observed']
    if observed != geometry or observed['device_scale_factor'] != scale:
        raise ValueError('Measured capture geometry/density differs from the approved conditions')
    crop, frame = observed['crop'], observed['frame']
    for box in (crop, frame):
        if (not isinstance(box, list) or len(box) != 4 or any(type(n) is not int for n in box)
                or min(box[:2]) < 0 or min(box[2:]) <= 0):
            raise ValueError('Capture crop/frame requires integer X,Y,WIDTH,HEIGHT')
    if (type(observed['width']) is not int or type(observed['height']) is not int
            or min(observed['width'], observed['height']) <= 0
            or crop[2:] != [viewport['width'], viewport['height']]
            or not (frame[0] <= crop[0] and frame[1] <= crop[1]
                    and crop[0]+crop[2] <= frame[0]+frame[2] <= observed['width']
                    and crop[1]+crop[3] <= frame[1]+frame[3] <= observed['height'])):
        raise ValueError('Capture crop/frame does not fit the measured viewport')
    box = [crop[0]*scale, crop[1]*scale, (crop[0]+crop[2])*scale, (crop[1]+crop[3])*scale]
    if any(not float(n).is_integer() for n in box):
        raise ValueError('Capture density produces fractional pixel crop')
    with Image.open(original) as image, Image.open(actual) as target:
        if (image.size != (observed['width']*scale, observed['height']*scale)
                or target.size != (viewport['width']*scale, viewport['height']*scale)
                or image.crop(tuple(map(int, box))).convert('RGBA').tobytes() != target.convert('RGBA').tobytes()):
            raise ValueError('Decoded capture dimensions or crop pixels do not match provenance')
    return actual


def execution_data(contract, contract_path, state):
    proof = state['uiEvidence']
    request_path = bound_file(proof['request'], Path(contract_path).resolve().parent)
    request = read(request_path)
    decision = route(request, contract_path)
    if decision['status'] == 'BLOCKED':
        raise ValueError('UI request cannot proceed: ' + decision['diagnostic'])
    invocation_path = bound_file(proof['invocations'], Path(contract_path).resolve().parent)
    rows = read(invocation_path)
    if not isinstance(rows, list) or not rows:
        raise ValueError('Missing task-specific UI execution receipts')
    return request_path, decision, rows


def design_data(contract, base):
    design = contract['design']
    schema_check(design, 'design-contract.schema.json')
    if design['verification_sha256'] != verification_sha(contract):
        raise ValueError('UI verification declarations changed; renew owner approval')
    approval = read(bound_file(design['approval'], base))
    if (not isinstance(approval, dict) or approval.get('role') != 'owner' or approval.get('approved_by') != design['approved_by']
            or approval.get('approved_at') != design['approved_at']
            or approval.get('decision') != design['status']
            or approval.get('design_sha256') != design_sha(design)
            or not isinstance(approval.get('source'), str) or not approval['source'].strip()):
        raise ValueError('Owner approval does not bind this exact design; return to design/owner')
    references = {r['id']: r for r in design['references']}
    viewports = {v['id']: v for v in design['canonical_viewports']}
    if len(references) != len(design['references']) or len(viewports) != len(design['canonical_viewports']):
        raise ValueError('Duplicate design reference or viewport ID')
    if not any(r['role'] == 'target' for r in references.values()):
        raise ValueError('Research references are not an approved implementation target')
    for reference in references.values():
        bound_file(reference, base)
        if reference['role'] == 'research' and not reference.get('rationale', '').strip():
            raise ValueError('Research reference needs its relevant pattern/rationale')
    ids = [i for items in design['verification'].values() for i in items]
    verifiers = {v['id']: v for v in contract['verifiers']}
    if len(ids) != len(set(ids)):
        raise ValueError('Each UI dimension requires independent verifier IDs')
    for identifier in ids:
        verifier = verifiers.get(identifier, {})
        if verifier.get('gate') != 'blocking' or verifier.get('stage', 'review') != 'review':
            raise ValueError('UI verifier must be blocking at REVIEW: ' + identifier)
        if not isinstance(verifier.get('threshold'), dict):
            raise ValueError('UI verifier requires explicit thresholds: ' + identifier)
        if 'max_diff_ratio' not in verifier['threshold']:
            bound_file(verifier['implementation'], base)
        if 'max_diff_ratio' in verifier['threshold']:
            fixture = verifier['fixture']
            if (fixture['reference'] not in references or references[fixture['reference']]['role'] != 'target'
                    or fixture['viewport'] not in viewports or fixture['state'] not in design['required_states']):
                raise ValueError('Pixel fixture must select an approved target, viewport and required state')
            threshold = verifier['threshold']
            if type(threshold.get('tolerance')) is not int or not 0 <= threshold['tolerance'] <= 255:
                raise ValueError('Pixel tolerance must be an integer in 0..255')
            for key in ('max_diff_ratio', 'region_max_diff_ratio'):
                number = threshold.get(key)
                if type(number) not in (int, float) or not math.isfinite(number) or not 0 <= number <= 1:
                    raise ValueError('Pixel ratio must be finite in 0..1')
            if not isinstance(threshold.get('regions'), list):
                raise ValueError('Pixel regions must be explicit')
    critical = critical_requirements(contract)
    cases = required_cases(contract)
    required = {case_key(c) for c in cases}
    if not {(v, s) for v in viewports for s in design['required_states']} <= {(c['viewport'], c['state']) for c in cases}:
        raise ValueError('Every canonical viewport and required state needs approved coverage')
    if {r['id'] for r in references.values() if r['role'] == 'target'} != {c['reference'] for c in cases}:
        raise ValueError('Approved target reference coverage differs')
    applicable = set()
    for case in cases:
        if (case['viewport'] not in viewports or case['state'] not in design['required_states']
                or not isinstance(case.get('invariants'), list)
                or len(case['invariants']) != len(set(case['invariants']))
                or not set(case['invariants']) <= critical):
            raise ValueError('Required case has invalid viewport/state/invariants')
        applicable.update(case['invariants'])
        pixels = [verifiers[i] for i in design['verification']['visual']
                  if 'max_diff_ratio' in verifiers[i]['threshold'] and case_key(verifiers[i]['fixture']) == case_key(case)]
        if not pixels:
            raise ValueError('Required screen/reference/viewport/state lacks pixel proof')
        for identifier in case['invariants']:
            if not any(identifier in verifiers[i]['covers']
                       and case_key(verifiers[i].get('fixture', {})) == case_key(case)
                       and identifier in {m['name'] for m in verifiers[i]['threshold']['metrics']}
                       for i in design['verification']['visual'] if 'max_diff_ratio' not in verifiers[i]['threshold']):
                raise ValueError('Critical invariant lacks independent case-specific metric: ' + identifier)
    if applicable != critical:
        raise ValueError('Critical invariant has no required case')
    for dimension, identifiers in design['verification'].items():
        for identifier in identifiers:
            verifier = verifiers[identifier]
            if 'max_diff_ratio' in verifier['threshold']:
                if case_key(verifier['fixture']) not in required:
                    raise ValueError('Pixel verifier substitutes an unapproved UI case')
            else:
                argv = verifier.get('argv')
                if not isinstance(argv, list) or not argv or any(not isinstance(a, str) or not a for a in argv):
                    raise ValueError('UI verifier requires an approved executable argv: ' + identifier)
                metrics = verifier['threshold'].get('metrics')
                if (not isinstance(metrics, list) or not metrics
                        or len({m['name'] for m in metrics}) != len(metrics)
                        or any(m['operator'] not in OPERATORS or type(m['target']) not in (int, float)
                               or not math.isfinite(m['target']) for m in metrics)):
                    raise ValueError('UI verifier requires unique finite metric thresholds')
    return design

def classify(category, design):
    if category in ('typography', 'spacing', 'geometry', 'missing_element', 'wrong_asset', 'content_hierarchy'):
        return 'FIX'
    if category in ('reference_ambiguity', 'design_defect', 'approved_departure'):
        return 'PRODUCT_DESIGN'
    permissions = design.get('allowed_interpolation', {})
    if category == 'responsive_interpolation':
        return 'CHECK_CONTRACT' if permissions.get('responsive') else 'PRODUCT_DESIGN'
    if category in ('dynamic_content', 'browser_noise'):
        return 'NORMALIZE' if permissions.get(category) else 'BLOCKED'
    return 'BLOCKED'

def route(request, contract_path=None):
    def result(name, status='NOT_RUN', diagnostic=''):
        return {'route': name, 'status': status, 'diagnostic': diagnostic}
    if not isinstance(request, dict):
        return result('blocked', 'BLOCKED', 'Request must be an object')
    if request.get('surface') == 'non_ui':
        return result('deep-loop')
    mode, platform = request.get('mode'), request.get('platform', 'web')
    if (('mode' in request and (not isinstance(mode, str) or mode not in {'GREENFIELD', 'PATCH', 'EVOLVE', 'REDESIGN'}))
            or not isinstance(platform, str) or platform not in {'web', 'ios-prototype', 'ios-native'}):
        return result('blocked', 'BLOCKED', 'Unknown UI mode/platform; classify the intended endpoint')
    changes = request.get('changes')
    flags = ('visually_specified', 'established_pattern', 'greenfield_authorized')
    if (request.get('surface') != 'ui' or not isinstance(changes, list) or not changes
            or any(not isinstance(c, str) or c not in SMALL | SUBSTANTIVE for c in changes)
            or any(k in request and type(request[k]) is not bool for k in flags)):
        return result('blocked', 'BLOCKED', 'Classify observable scope; unknown inputs cannot authorize BUILD')
    if ((mode in {'PATCH', 'EVOLVE', 'REDESIGN'} and request.get('greenfield_authorized') is True)
            or (mode == 'GREENFIELD' and (request.get('established_pattern') is True or 'existing_component' in changes))
            or (mode == 'REDESIGN' and not set(changes) & SUBSTANTIVE)):
        return result('blocked', 'BLOCKED', 'Mode contradicts observable scope or exploratory authority')

    def implementation(name, diagnostic=''):
        if platform == 'ios-native':
            return result('ios-delivery', diagnostic=diagnostic + ' Use the selected scope with the native iOS adapter; browser pixels are not native proof.')
        if platform == 'ios-prototype':
            diagnostic += ' Use existing protected mobile runtime and declared capture geometry; browser prototype endpoint only.'
        return result(name, diagnostic=diagnostic)

    design = {}
    if contract_path:
        try:
            design = design_data(read(contract_path), Path(contract_path).resolve().parent)
        except (OSError, ValueError, KeyError, TypeError) as error:
            return result('product-design', 'BLOCKED', str(error))
    if request.get('difference'):
        disposition = classify(request['difference'], design)
        return result({'FIX': 'fix', 'PRODUCT_DESIGN': 'product-design',
                       'CHECK_CONTRACT': 'verify-interpolation', 'NORMALIZE': 'normalize',
                       'BLOCKED': 'blocked'}[disposition],
                      'BLOCKED' if disposition in ('PRODUCT_DESIGN', 'BLOCKED') else 'NOT_RUN')
    if mode not in {'GREENFIELD', 'REDESIGN'} and set(changes) <= SMALL and (request.get('visually_specified') is True
                                  or set(changes) == {'existing_component'} and request.get('established_pattern') is True):
        return implementation('build')
    if design:
        return implementation('image-to-code')
    if request.get('greenfield_authorized') is True:
        return implementation('greenfield-build', diagnostic='Explicit exploratory BUILD only; approve/freeze before fidelity delivery.')
    return result('product-design', 'BLOCKED', 'No sufficiently specified or owner-approved visual target')

def source_identity(path):
    manifest = read(path)
    files = manifest['files']
    if not isinstance(files, dict) or not files:
        raise ValueError('Source manifest must identify the actual nonempty candidate')
    base = logical(path).parent
    for name, digest in files.items():
        bound_file({'path': name, 'sha256': digest}, base)
    return sha(path)

def pixel_run(reference, actual, out, threshold):
    argv = [sys.executable, str(PIXEL), '--expected', str(reference), '--actual', str(actual),
            '--output', str(out), '--tolerance', str(threshold['tolerance']),
            '--max-diff-ratio', str(threshold['max_diff_ratio']),
            '--region-max-diff-ratio', str(threshold['region_max_diff_ratio'])]
    for box in threshold['regions']:
        if not isinstance(box, list) or len(box) != 4 or any(type(n) is not int for n in box):
            raise ValueError('Pixel regions require integer X,Y,WIDTH,HEIGHT')
        argv += ['--region', ','.join(map(str, box))]
    run = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if not (out / 'result.json').is_file():
        raise ValueError('Pixel comparator unavailable: ' + run.stderr)
    with files_context():
        raw = read(out / 'result.json')
    return run, raw, argv

def compare(contract_path, verifier_id, capture_path, output, goal_id):
    contract_path, capture_path, output = map(Path, (contract_path, capture_path, output))
    if output.exists():
        raise ValueError('Evidence output exists; preserve it and select a new directory')
    contract = read(contract_path)
    design = design_data(contract, contract_path.resolve().parent)
    verifier = next(v for v in contract['verifiers'] if v['id'] == verifier_id)
    if verifier_id not in design['verification']['visual'] or 'max_diff_ratio' not in verifier['threshold']:
        raise ValueError('Select a declared visual pixel verifier')
    fixture, capture = verifier['fixture'], read(capture_path)
    viewport = next(v for v in design['canonical_viewports'] if v['id'] == fixture['viewport'])
    if any(capture.get(k) != fixture[k] for k in ('viewport', 'state')) or capture['conditions'] != viewport['conditions']:
        raise ValueError('Capture viewport/state/conditions do not match the frozen design')
    if case_key(capture) != case_key(fixture):
        raise ValueError('Capture screen/reference does not match the frozen fixture')
    actual = capture_data(capture, capture_path, viewport)
    reference = next(r for r in design['references'] if r['id'] == fixture['reference'])
    expected = bound_file(reference, contract_path.resolve().parent)
    source = Path(capture['source_manifest']).resolve()
    environment = Path(capture['environment_manifest']).resolve()
    source_hash = source_identity(source)
    if read(environment) != capture['conditions']:
        raise ValueError('Capture environment differs from declared conditions')
    from PIL import Image
    with Image.open(expected) as image:
        if list(image.size) != [viewport[k] * viewport['device_scale_factor'] for k in ('width', 'height')]:
            raise ValueError('Reference pixel dimensions do not match the canonical viewport/density')
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    run, raw, argv = pixel_run(expected, actual, output, verifier['threshold'])
    (output / 'run.log').write_text(run.stdout + run.stderr, encoding='utf-8')
    (output / 'capture.json').write_text(json.dumps(capture, indent=2), encoding='utf-8')
    metrics = []
    for name, measure in [('diffRatio', raw.get('comparison', {})),
                           *[(f'region-{i}', r) for i, r in enumerate(raw.get('regions', []))]]:
        if measure:
            metrics.append({'name': name, 'unit': 'fraction', 'baseline': None, 'previous': None,
                            'current': measure['diffRatio'], 'operator': '<=', 'target': measure['maxDiffRatio'],
                            'samples': [], 'sampling': 'All declared pixels'})
    artifacts = [{'role': name, **item} for name, item in raw['artifacts'].items()]
    artifacts += [{'role': role, 'path': str((output / name).resolve()), 'sha256': sha(output / name)}
                  for role, name in [('log', 'run.log'), ('report', 'result.json'), ('other', 'capture.json')]]
    record = {'schema_version': '1.0', 'evidence_origin': 'actual_run',
              'run_id': output.name, 'goal_id': goal_id, 'criterion_id': verifier_id, 'kind': 'visual',
              'status': raw['status'], 'subject': {'source_fingerprint': source_hash, 'build_fingerprint': None,
              'contract_fingerprint': sha(contract_path), 'reference_fingerprint': reference['sha256'],
              'environment_fingerprint': sha(environment)},
              'execution': {'verifier_id': verifier_id, 'verifier_version': 'sha256:' + sha(PIXEL),
                            'verifier_fingerprint': sha(PIXEL), 'argv': argv,
                            'working_directory': str(Path.cwd()), 'started_at': started,
                            'finished_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                            'native_exit_code': run.returncode},
              'metrics': metrics, 'artifacts': artifacts, 'diagnostic': raw['diagnostic']}
    (output / 'verifier.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    return record

def evidence_issues(contract, contract_path, state):
    if 'design' not in contract:
        return []
    try:
        base = Path(contract_path).resolve().parent
        design = design_data(contract, base)
        proof = state['uiEvidence']
        request_path, decision, invocations = execution_data(contract, contract_path, state)
        source = source_identity(Path(proof['source_manifest']))
        environment = sha(proof['environment_manifest'])
        if not isinstance(proof['differences'], list):
            raise ValueError('Differences must be a list; empty means none unexplained after design QA')
        # Unresolved differences never self-waive, including allowed interpolation.
        if proof['differences']:
            raise ValueError('Unresolved visual differences: ' + ', '.join(
                classify(d['category'], design) for d in proof['differences']))
        issues = []
        checks = {c.get('verifierId'): c for c in state['checks']}
        verifiers = {v['id']: v for v in contract['verifiers']}
        for dimension, identifiers in design['verification'].items():
            for identifier in identifiers:
                check, verifier = checks[identifier], verifiers[identifier]
                if check.get('stage', 'review') != 'review':
                    raise ValueError('UI proof cannot be deferred beyond REVIEW')
                record_path = Path(check['evidence'])
                record = read(record_path)
                schema_check(record, 'verifier-result.schema.json')
                if (check['status'] != 'passed' or record['status'] != 'PASS'
                        or record['evidence_origin'] != 'actual_run'
                        or record['execution']['native_exit_code'] != 0):
                    issues.append(identifier + ': required check did not PASS')
                    continue
                expected_kind = {'visual': 'visual', 'responsive': 'invariant',
                                 'behavior': 'interaction', 'accessibility': 'accessibility'}[dimension]
                if (record['kind'] != expected_kind or record['criterion_id'] != identifier
                        or record['execution']['verifier_id'] != identifier or record['goal_id'] != state['sessionId']):
                    raise ValueError('Wrong UI criterion, dimension or goal')
                subject = record['subject']
                if (subject['source_fingerprint'] != source or subject['environment_fingerprint'] != environment
                        or subject['contract_fingerprint'] != sha(contract_path)):
                    raise ValueError('UI evidence does not match current source/contract/environment')
                for artifact in record['artifacts']:
                    bound_file(artifact, logical(record_path).parent)
                threshold = verifier['threshold']
                if 'max_diff_ratio' in threshold:
                    fixture = verifier['fixture']
                    reference = next(r for r in design['references'] if r['id'] == fixture['reference'])
                    if subject['reference_fingerprint'] != reference['sha256'] or record['execution']['verifier_fingerprint'] != sha(PIXEL):
                        raise ValueError('Pixel reference/verifier changed')
                    actual = next(a for a in record['artifacts'] if a['role'] == 'actual')
                    capture_artifact = next(a for a in record['artifacts'] if Path(a['path']).name == 'capture.json')
                    capture = read(bound_file(capture_artifact, logical(record_path).parent))
                    viewport = next(v for v in design['canonical_viewports'] if v['id'] == fixture['viewport'])
                    captured = capture_data(capture, bound_file(capture_artifact, logical(record_path).parent), viewport)
                    from PIL import Image
                    with Image.open(captured) as original, Image.open(bound_file(actual, logical(record_path).parent)) as preserved:
                        if original.size != preserved.size or original.convert('RGBA').tobytes() != preserved.convert('RGBA').tobytes():
                            raise ValueError('Preserved pixel actual differs from the bound capture')
                    if (source_identity(Path(capture['source_manifest'])) != source
                            or sha(Path(capture['environment_manifest'])) != environment):
                        raise ValueError('Capture source/environment differs from task evidence')
                    if (case_key(capture) != case_key(fixture) or capture['viewport'] != fixture['viewport'] or capture['state'] != fixture['state']
                            or capture['conditions'] != viewport['conditions']
                            or read(proof['environment_manifest']) != viewport['conditions']):
                        raise ValueError('Pixel capture provenance mismatch')
                    if _INSPECTION_ONLY.get():
                        # Trusted installed comparator math only; never load packet implementation code.
                        from pixel_diff import compare_images, region
                        if any(not isinstance(box,list) or len(box)!=4 or any(type(n) is not int for n in box) for box in threshold['regions']):
                            raise ValueError('Pixel regions require integer X,Y,WIDTH,HEIGHT')
                        try:
                            boxes = [region(','.join(map(str, box))) for box in threshold['regions']]
                        except argparse.ArgumentTypeError as error:
                            raise ValueError(str(error)) from error
                        with Image.open(bound_file(reference, base)) as expected_image, Image.open(bound_file(actual, logical(record_path).parent)) as actual_image:
                            if getattr(expected_image, 'n_frames', 1) != 1 or getattr(actual_image, 'n_frames', 1) != 1:
                                raise ValueError('Use single-frame captures')
                            _, measured_comparison, measured_regions = compare_images(
                                expected_image, actual_image, threshold['tolerance'], threshold['max_diff_ratio'],
                                boxes, threshold['region_max_diff_ratio'])
                        if not measured_comparison['passed'] or not all(item['passed'] for item in measured_regions):
                            issues.append(identifier + ': current pixel comparison FAIL')
                    else:
                        with tempfile.TemporaryDirectory() as temp:
                            run, raw, _ = pixel_run(bound_file(reference, base),
                                                    bound_file(actual, logical(record_path).parent),
                                                    Path(temp) / 'comparison', threshold)
                            if run.returncode != 0 or raw['status'] != 'PASS':
                                issues.append(identifier + ': current pixel comparison ' + raw['status'])
                else:
                    implementation = bound_file(verifier['implementation'], base)
                    if record['execution']['verifier_fingerprint'] != sha(implementation):
                        raise ValueError('Independent verifier identity differs from the contract')
                    if dimension == 'visual' and subject['reference_fingerprint'] not in {
                            r['sha256'] for r in design['references'] if r['role'] == 'target'}:
                        raise ValueError('Structural review did not use an approved target')
                    receipts = [r for r in invocations if r.get('verifier_id') == identifier]
                    if len(receipts) != 1:
                        raise ValueError('Missing or duplicate actual invocation: ' + identifier)
                    receipt = receipts[0]
                    if (receipt.get('goal_id') != state['sessionId'] or receipt.get('subject') != {
                            'source_fingerprint': source, 'contract_fingerprint': sha(contract_path),
                            'environment_fingerprint': environment}
                            or receipt.get('request_sha256') != sha(request_path)
                            or receipt.get('route') != decision
                            or receipt.get('route_fingerprint') != sha(Path(__file__))
                            or receipt['argv'] != verifier['argv'] or receipt['argv'] != record['execution']['argv']
                            or receipt['exitCode'] != record['execution']['native_exit_code']
                            or receipt['cwd'] != record['execution']['working_directory']
                            or receipt['startedAt'] != record['execution']['started_at']
                            or receipt['finishedAt'] != record['execution']['finished_at']
                            or receipt['verifier_fingerprint'] != sha(implementation)):
                        raise ValueError('Unmatched task-specific execution: ' + identifier)
                    native = json.loads(receipt['stdout'])
                    reports = [a for a in record['artifacts'] if a['role'] == 'report']
                    if len(reports) != 1 or read(bound_file(reports[0], logical(record_path).parent)) != native:
                        raise ValueError('UI report differs from actual native output')
                    declared = threshold['metrics']
                    if len({m['name'] for m in record['metrics']}) != len(record['metrics']):
                        raise ValueError('Duplicate measured UI metrics')
                    measured = {m['name']: m['current'] for m in record['metrics']}
                    if measured != native['metrics']:
                        raise ValueError('UI metrics differ from actual native output')
                    if dimension == 'visual':
                        reference = next(r for r in design['references'] if r['id'] == verifier['fixture']['reference'])
                        if (subject['reference_fingerprint'] != reference['sha256'] or len(native['cases']) != 1
                                or case_key(native['cases'][0]) != case_key(verifier['fixture'])):
                            raise ValueError('Structural evidence substitutes a UI case/reference')
                    if 'required_cases' in verifier.get('fixture', {}):
                        if (not isinstance(native['cases'], list)
                                or len(native['cases']) != len(required_cases(contract))
                                or {case_key(c) for c in native['cases']} != {case_key(c) for c in required_cases(contract)}):
                            raise ValueError('Actual required screen/reference/viewport/state coverage differs')
                    if dimension == 'visual' or 'required_cases' in verifier.get('fixture', {}):
                        for case in native['cases']:
                            capture_path = bound_file(case['capture'], logical(record_path).parent)
                            capture_record = read(capture_path)
                            if case_key(capture_record) != case_key(case):
                                raise ValueError('Observed coverage case differs from its capture')
                            vp = next(v for v in design['canonical_viewports'] if v['id'] == case['viewport'])
                            capture_data(capture_record, capture_path, vp)
                            for pixel_id in design['verification']['visual']:
                                pixel_verifier = verifiers[pixel_id]
                                if ('max_diff_ratio' not in pixel_verifier['threshold']
                                        or case_key(pixel_verifier['fixture']) != case_key(case)):
                                    continue
                                pixel_path = Path(checks[pixel_id]['evidence'])
                                pixel_record = read(pixel_path)
                                pixel_capture = next(a for a in pixel_record['artifacts'] if Path(a['path']).name == 'capture.json')
                                if capture_record != read(bound_file(pixel_capture, logical(pixel_path).parent)):
                                    raise ValueError('Structural/coverage and pixel proof must use the same capture')
                    for metric in declared:
                        value, target = measured[metric['name']], metric['target']
                        if (type(value) not in (int, float) or type(target) not in (int, float)
                                or not math.isfinite(value) or not math.isfinite(target)
                                or not OPERATORS[metric['operator']](value, target)):
                            issues.append(identifier + ': declared threshold not met')
        return issues
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
        return ['UI proof BLOCKED: ' + str(error)]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    routing = commands.add_parser('route')
    routing.add_argument('--request', type=Path, required=True)
    routing.add_argument('--contract', type=Path)
    comparison = commands.add_parser('compare')
    for name in ('contract', 'capture', 'output'):
        comparison.add_argument('--' + name, type=Path, required=True)
    for name in ('verifier', 'goal-id'):
        comparison.add_argument('--' + name, required=True)
    args = parser.parse_args()
    try:
        result = (route(read(args.request), args.contract) if args.command == 'route' else
                  compare(args.contract, args.verifier, args.capture, args.output, args.goal_id))
        print(json.dumps(result, indent=2))
        return {'PASS': 0, 'NOT_RUN': 0, 'FAIL': 1, 'BLOCKED': 2}[result['status']]
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
        print(json.dumps({'status': 'BLOCKED', 'diagnostic': str(error)}))
        return 2

if __name__ == '__main__':
    sys.exit(main())
