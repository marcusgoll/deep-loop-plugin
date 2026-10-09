"""Routing and real comparator fixtures; no model, network, or owner actions."""
import argparse
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from PIL import Image
import deep_loop
import ui_design

def save(path, data):
    path.write_text(json.dumps(data, indent=2), encoding='utf-8')
    return path

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

class UIContractTests(unittest.TestCase):
    def setUp(self):
        if os.environ.get('DEEP_LOOP_TRIAL_OUTPUT') and type(self).__name__ == 'RenderedCaptionTests':
            trial_root = Path(os.environ['DEEP_LOOP_TRIAL_OUTPUT']); trial_root.mkdir(parents=True, exist_ok=True)
            self.root = Path(tempfile.mkdtemp(prefix=self._testMethodName+'-', dir=trial_root))
        else:
            self.temp = tempfile.TemporaryDirectory()
            self.addCleanup(self.temp.cleanup)
            self.root = Path(self.temp.name)
        self.reference = self.root / 'approved.png'
        Image.new('RGB', (8, 8), 'white').save(self.reference)
        self.actual = self.root / 'actual.png'
        self.actual.write_bytes(self.reference.read_bytes())
        self.owner = self.root / 'owner-selection.txt'
        self.owner.write_text('Fixture owner selected this exact design; not real owner approval.')
        self.source = self.root / 'app.html'
        self.source.write_text('<button>Continue</button>')
        self.manifest = save(self.root / 'source.json', {'files': {'app.html': sha(self.source)}})
        self.conditions = {'theme': 'light', 'content': 'fixed fixture', 'fonts': 'fixture', 'browser': 'fixture'}
        self.environment = save(self.root / 'environment.json', self.conditions)
        ids = ['pixels', 'structure', 'responsive', 'behavior', 'accessibility']
        self.contract = {
            'name': 'Fixture UI', 'scope': 'Fixture screen', 'status': 'NOT_RUN',
            'requirements': [{'id': 'R1', 'outcome': 'Matches approved UI', 'invariant': 'UI preserved', 'priority': 'blocking'}],
            'verifiers': [{'id': i, 'covers': ['R1'], 'class': 'deterministic', 'status': 'implemented',
                           'expected': 'No failures', 'gate': 'blocking',
                           'threshold': {'metrics': [{'name': 'failures', 'operator': '==', 'target': 0}]}}
                          for i in ids], 'gaps': [],
            'ship_gate': dict.fromkeys(('require_all_blocking_verifiers_pass', 'require_zero_blocking_gaps',
                                       'require_human_approvals_recorded', 'require_evidence_matches_revision'), True),
            'design': {
                'design_id': 'fixture-dashboard', 'status': 'approved', 'approved_by': 'Fixture owner',
                'approved_at': '2026-10-07T15:00:00Z',
                'approval': {'role': 'owner', 'path': str(self.owner), 'sha256': sha(self.owner)},
                'references': [{'id': 'main', 'role': 'target', 'origin': 'product-design',
                                'path': str(self.reference), 'sha256': sha(self.reference)}],
                'canonical_viewports': [{'id': 'desktop', 'width': 8, 'height': 8,
                                         'device_scale_factor': 1, 'conditions': self.conditions}],
                'critical_invariants': ['Primary action remains prominent'],
                'required_states': ['default'],
                'allowed_interpolation': {'responsive': 'Reflow preserves hierarchy'},
                'requires_design_approval': ['Navigation, hierarchy or major geometry changes'],
                'verification': {'visual': ['pixels', 'structure'], 'responsive': ['responsive'],
                                 'behavior': ['behavior'], 'accessibility': ['accessibility']}
            }
        }
        self.pixel = self.contract['verifiers'][0]
        self.pixel.update(threshold={'tolerance': 0, 'max_diff_ratio': 0, 'regions': [],
                                     'region_max_diff_ratio': 0},
                          fixture={'reference': 'main', 'viewport': 'desktop', 'state': 'default'})
        for verifier in self.contract['verifiers'][1:]:
            verifier['implementation'] = {'path': str(Path(__file__).resolve()), 'sha256': sha(Path(__file__))}
        self.case = {'screen': 'dashboard', 'reference': 'main', 'viewport': 'desktop', 'state': 'default'}
        self.pixel['fixture'].update(screen='dashboard')
        self.contract['design']['critical_invariants'] = ['R1']
        self.contract['verifiers'][1]['fixture'] = dict(self.case)
        self.contract['verifiers'][1]['threshold']['metrics'][0]['name'] = 'R1'
        self.contract['verifiers'][1]['threshold']['metrics'][0].update(operator='==', target=1)
        self.contract['verifiers'][2]['fixture'] = {'required_cases': [dict(self.case, invariants=['R1'])]}
        self.request = save(self.root / 'request.json', {'surface': 'ui', 'changes': ['hierarchy'], 'mode': 'EVOLVE', 'platform': 'web'})
        self.capture = self.make_capture('initial-capture.json')
        self.runner = self.root / 'independent.py'
        self.runner.write_text("import json,sys\nfrom pathlib import Path\n"
                               "kind=sys.argv[1]\nsource=Path(sys.argv[2]).read_text()\n"
                               "facts=json.loads(Path(sys.argv[3]).read_text())\n"
                               "metrics={'R1':int('<button>Continue</button>' in source)} if kind.startswith('structure') else {'failures':0}\n"
                               "print(json.dumps({'metrics':metrics,'cases':facts}))\n")
        self.native_cases = save(self.root / 'cases.json', [dict(self.case, capture={'path': str(self.capture), 'sha256': sha(self.capture)})])
        for verifier in self.contract['verifiers'][1:]:
            verifier['implementation'] = {'path': str(self.runner), 'sha256': sha(self.runner)}
            verifier['argv'] = [sys.executable, '-B', str(self.runner), verifier['id'], str(self.source), str(self.native_cases)]
        self.contract['design']['verification_sha256'] = ui_design.verification_sha(self.contract)
        save(self.owner, {'role': 'owner', 'approved_by': 'Fixture owner', 'approved_at': '2026-10-07T15:00:00Z',
                          'decision': 'approved', 'source': 'Synthetic fixture selection',
                          'design_sha256': ui_design.design_sha(self.contract['design'])})
        self.contract['design']['approval']['sha256'] = sha(self.owner)
        self.path = save(self.root / 'contract.json', self.contract)
        self.state = {'schemaVersion': 2, 'sessionId': 'fixture1',
                      'checks': [{'name': i, 'verifierId': i, 'status': 'passed', 'evidence': 'claimed PASS'}
                                 for i in ids],
                      'verificationContract': {'path': str(self.path), 'sha256': sha(self.path), 'endpoint': 'Fixture UI'},
                      'uiEvidence': {'request': {'path': str(self.request), 'sha256': sha(self.request)}, 'source_manifest': str(self.manifest), 'environment_manifest': str(self.environment),
                                     'differences': []},
                      'delivery': {'endpoint': 'Fixture UI', 'status': 'verified', 'evidence': 'Fixture readback'}}
        self.execute_independent()
        for check in self.state['checks'][1:]:
            record = self.record(check['verifierId'])
            result = save(self.root / (check['verifierId'] + '.json'), record)
            check['evidence'] = str(result)

    def make_capture(self, name):
        return save(self.root / name, {'image': {'path': str(self.actual), 'sha256': sha(self.actual)},
                    'original': {'path': str(self.actual), 'sha256': sha(self.actual)}, **self.case,
                    'observed': {'width': 8, 'height': 8, 'device_scale_factor': 1,
                                 'crop': [0, 0, 8, 8], 'frame': [0, 0, 8, 8], 'scroll_top': 0},
                    'conditions': self.conditions, 'source_manifest': str(self.manifest),
                    'environment_manifest': str(self.environment)})

    def execute_independent(self):
        batch = save(self.root / 'checks.json', [{'name': v['id'], 'verifierId': v['id'], 'argv': v['argv']}
                                               for v in self.contract['verifiers'] if 'max_diff_ratio' not in v['threshold']])
        self.invocations = self.root / 'invocations.json'
        args = argparse.Namespace(root=str(self.root), checks=str(batch), output=str(self.invocations),
                                  ui_request=str(self.request), contract=str(self.path), goal_id='fixture1',
                                  source_manifest=str(self.manifest), environment_manifest=str(self.environment))
        self.assertEqual(deep_loop.run_checks(args), 0)
        self.state['uiEvidence']['invocations'] = {'path': str(self.invocations), 'sha256': sha(self.invocations)}

    def record(self, verifier):
        dimension = next(d for d,ids in self.contract['design']['verification'].items() if verifier in ids)
        kind = {'visual':'visual','responsive':'invariant','behavior':'interaction','accessibility':'accessibility'}[dimension]
        receipt = next(r for r in json.loads(self.invocations.read_text()) if r['verifier_id'] == verifier)
        native = json.loads(receipt['stdout'])
        report = save(self.root / (verifier + '-native.json'), native)
        artifacts = [{'role': role, 'path': str(path), 'sha256': sha(path)} for role, path in
                     [('log', self.invocations), ('report', report), ('expected', self.reference),
                      ('actual', self.actual), ('diff', self.reference)]]
        return {'schema_version': '1.0', 'evidence_origin': 'actual_run', 'run_id': 'fixture-' + verifier,
                'goal_id': 'fixture1', 'criterion_id': verifier, 'kind': kind, 'status': 'PASS',
                'subject': {'source_fingerprint': sha(self.manifest), 'build_fingerprint': None,
                            'contract_fingerprint': sha(self.path), 'reference_fingerprint': sha(self.reference),
                            'environment_fingerprint': sha(self.environment)},
                'execution': {'verifier_id': verifier, 'verifier_version': 'executed fixture',
                              'verifier_fingerprint': sha(self.runner), 'argv': receipt['argv'],
                              'working_directory': receipt['cwd'], 'started_at': receipt['startedAt'],
                              'finished_at': receipt['finishedAt'], 'native_exit_code': receipt['exitCode']},
                'metrics': [{'name': name, 'unit': 'count', 'baseline': None, 'previous': None,
                             'current': value, 'operator': '==', 'target': value, 'samples': [],
                             'sampling': 'actual independent fixture output'} for name, value in native['metrics'].items()],
                'artifacts': artifacts, 'diagnostic': 'Executed independent mechanism fixture; not real product proof'}

    def pixels(self, name='pixel-run'):
        capture = self.make_capture(name + '-capture.json')
        result = ui_design.compare(self.path, 'pixels', capture, self.root / name, 'fixture1')
        self.state['checks'][0]['evidence'] = str(self.root / name / 'verifier.json')
        return result

    def test_ui_preservation_refuses_nonportable_bindings_before_archive_mutation(self):
        self.pixels()
        self.assertEqual(deep_loop.contract_issues(self.state, 'ship'), [])
        self.state.update(sessionId='fixture1', task='UI recovery fixture', active=False, complete=False, phase='SHIP')
        root = self.root / 'checkout'
        root.mkdir()
        checkpoint = root / '.deep-fixture1'
        checkpoint.mkdir()
        save(checkpoint / 'state.json', self.state)
        (checkpoint / 'plan.md').write_text('Fixture portable UI preservation')
        original = deep_loop.file_manifest(self.root)
        archive = self.root / 'archive'
        args = argparse.Namespace(root=str(root), path=str(checkpoint), session=None,
            destination=str(archive), include=[str(self.root)], checkpoint_only=True)
        with self.assertRaisesRegex(ValueError, 'cannot contain'):
            deep_loop.preserve(args)
        self.assertFalse(archive.exists())
        self.assertEqual(deep_loop.file_manifest(self.root), original)
        # No preserved endpoint can be claimed after removing external scratch inputs.
        self.request.unlink()
        self.assertNotEqual(deep_loop.contract_issues(self.state, 'ship'), [])
        self.assertFalse(archive.exists())
        self.assertTrue(checkpoint.exists())

    def test_ui_build_requires_approved_declarations_but_not_execution_receipts(self):
        self.state['schemaVersion'] = 4
        self.state['uiRoute'] = {'kind': 'specified', 'approvedTarget': 'Fixture target', 'evidence': str(self.owner)}
        self.state['delivery']['endpointDecision'] = {'status': 'settled', 'source': 'user', 'evidence': str(self.owner)}
        for check in self.state['checks']:
            check.update(status='pending', evidence='')
        self.state['uiEvidence'].pop('invocations', None)
        self.assertEqual(deep_loop.contract_issues(self.state, 'build'), [])
        self.assertTrue(deep_loop.contract_issues(self.state, 'review'))
        folder = self.root / '.deep-buildui1'
        folder.mkdir()
        save(folder / 'state.json', self.state)
        args = argparse.Namespace(root=str(self.root), path=str(folder), session=None, stage='build', mode='fail')
        self.assertEqual(deep_loop.validate(args), 0)
        self.contract['gaps'] = [{'id': 'G1', 'requirement': 'R1', 'risk': 'Missing prerequisite',
            'recommended_verifier': 'Prerequisite proof', 'priority': 'blocking', 'blocks': 'implementation'}]
        save(self.path, self.contract)
        self.state['verificationContract']['sha256'] = sha(self.path)
        save(folder / 'state.json', self.state)
        self.assertNotEqual(deep_loop.validate(args), 0)

    def test_substantive_without_direction_routes_to_design(self):
        self.assertEqual(ui_design.route({'surface': 'ui', 'changes': ['navigation']})['route'], 'product-design')

    def test_modes_and_platforms_require_direction_before_build(self):
        for mode in ('GREENFIELD', 'PATCH', 'EVOLVE', 'REDESIGN'):
            for platform in ('web', 'ios-prototype', 'ios-native'):
                with self.subTest(mode=mode, platform=platform):
                    request = {'surface': 'ui', 'changes': ['navigation'], 'mode': mode, 'platform': platform}
                    result = ui_design.route(request)
                    self.assertEqual((result['route'], result['status']), ('product-design', 'BLOCKED'))
                    approved = ui_design.route(request, self.path)
                    self.assertEqual(approved['route'], 'ios-delivery' if platform == 'ios-native' else 'image-to-code')
                    self.assertEqual(approved['status'], 'NOT_RUN')

    def test_greenfield_does_not_reuse_small_edit_bypass(self):
        result = ui_design.route({'surface': 'ui', 'changes': ['spacing'], 'mode': 'GREENFIELD',
                                  'visually_specified': True})
        self.assertEqual((result['route'], result['status']), ('product-design', 'BLOCKED'))

    def test_patch_and_evolve_keep_specified_small_edits_lightweight(self):
        for mode in ('PATCH', 'EVOLVE'):
            for platform in ('web', 'ios-prototype', 'ios-native'):
                with self.subTest(mode=mode, platform=platform):
                    result = ui_design.route({'surface': 'ui', 'changes': ['existing_component'],
                                              'established_pattern': True, 'mode': mode, 'platform': platform})
                    self.assertEqual(result['route'], 'ios-delivery' if platform == 'ios-native' else 'build')

    def test_mode_and_platform_inputs_fail_closed(self):
        base = {'surface': 'ui', 'changes': ['navigation'], 'visually_specified': True}
        invalid = [{'mode': x} for x in ('unknown', 'patch', None, [], {})]
        invalid += [{'platform': x} for x in ('ios', 'android', None, [], {})]
        invalid += [{'mode': 'EVOLVE', 'greenfield_authorized': True},
                    {'mode': 'PATCH', 'greenfield_authorized': True},
                    {'mode': 'REDESIGN', 'greenfield_authorized': True},
                    {'mode': 'GREENFIELD', 'established_pattern': True},
                    {'mode': 'GREENFIELD', 'changes': ['existing_component']},
                    {'mode': 'REDESIGN', 'changes': ['spacing']}]
        for fields in invalid:
            with self.subTest(fields=fields):
                result = ui_design.route(dict(base, **fields), self.path)
                self.assertEqual((result['route'], result['status']), ('blocked', 'BLOCKED'))

    def test_explicit_exploratory_override_retains_native_boundary(self):
        for mode in (None, 'GREENFIELD'):
            request = {'surface': 'ui', 'changes': ['composition'], 'greenfield_authorized': True}
            if mode: request['mode'] = mode
            self.assertEqual(ui_design.route(request)['route'], 'greenfield-build')
            request['platform'] = 'ios-native'
            result = ui_design.route(request)
            self.assertEqual(result['route'], 'ios-delivery')
            self.assertIn('exploratory', result['diagnostic'].lower())

    def test_platform_handoffs_do_not_claim_native_or_prototype_proof(self):
        request = {'surface': 'ui', 'changes': ['flow'], 'platform': 'ios-prototype'}
        self.assertIn('protected', ui_design.route(request, self.path)['diagnostic'])
        request['platform'] = 'ios-native'
        self.assertIn('native', ui_design.route(request, self.path)['diagnostic'])
        self.assertEqual(ui_design.route({'surface': 'non_ui', 'mode': [], 'platform': []})['route'], 'deep-loop')

    def test_approved_target_routes_to_image_to_code(self):
        self.assertEqual(ui_design.route({'surface': 'ui', 'changes': ['hierarchy']}, self.path)['route'],
                         'image-to-code')

    def test_trivial_specified_and_established_pattern_bypass_design(self):
        for change in ('typo', 'color', 'asset', 'spacing', 'accessibility', 'existing_component'):
            self.assertEqual(ui_design.route({'surface': 'ui', 'changes': [change], 'visually_specified': True})['route'],
                             'build')
        self.assertEqual(ui_design.route({'surface': 'ui', 'changes': ['existing_component'],
                                         'established_pattern': True})['route'], 'build')
        self.assertEqual(ui_design.route({'surface': 'ui', 'changes': ['navigation'],
                                         'visually_specified': True})['route'], 'product-design')

    def test_failed_pixel_comparison_cannot_pass_gate(self):
        Image.new('RGB', (8, 8), 'black').save(self.actual)
        self.assertEqual(self.pixels()['status'], 'FAIL')
        self.assertTrue(deep_loop.contract_issues(self.state, 'review'))
        result_path = Path(self.state['checks'][0]['evidence'])
        forged = json.loads(result_path.read_text())
        forged['status'] = 'PASS'
        forged['execution']['native_exit_code'] = 0
        for metric in forged['metrics']: metric['current'] = 0
        save(result_path, forged)
        self.assertTrue(deep_loop.contract_issues(self.state, 'ship'))

    def test_difference_taxonomy(self):
        for category in ('typography', 'spacing', 'geometry', 'missing_element', 'wrong_asset', 'content_hierarchy'):
            self.assertEqual(ui_design.classify(category, self.contract['design']), 'FIX')
        for category in ('reference_ambiguity', 'design_defect', 'approved_departure'):
            self.assertEqual(ui_design.classify(category, self.contract['design']), 'PRODUCT_DESIGN')
        self.assertEqual(ui_design.classify('responsive_interpolation', self.contract['design']), 'CHECK_CONTRACT')
        self.assertEqual(ui_design.classify('dynamic_content', self.contract['design']), 'BLOCKED')

    def test_reference_ambiguity_routes_back(self):
        self.assertEqual(ui_design.route({'surface': 'ui', 'changes': ['hierarchy'],
                                         'difference': 'reference_ambiguity'}, self.path)['route'], 'product-design')

    def test_reference_and_contract_mutation_block(self):
        self.pixels()
        self.assertEqual(deep_loop.contract_issues(self.state, 'review'), [])
        self.reference.write_bytes(b'changed by implementation')
        self.assertTrue(deep_loop.contract_issues(self.state, 'review'))

    def test_contract_mutation_requires_explicit_rebinding(self):
        self.pixels()
        changed = copy.deepcopy(self.contract)
        changed['design']['critical_invariants'] = ['Silently changed hierarchy']
        save(self.path, changed)
        self.assertTrue(deep_loop.contract_issues(self.state, 'ship'))

    def test_responsive_interpolation_does_not_self_pass_or_redesign(self):
        result = ui_design.route({'surface': 'ui', 'changes': ['hierarchy'],
                                  'difference': 'responsive_interpolation'}, self.path)
        self.assertEqual(result['route'], 'verify-interpolation')
        self.assertEqual(result['status'], 'NOT_RUN')

    def test_behavior_and_accessibility_fail_independently(self):
        self.pixels()
        for index in (2, 3, 4):
            path = Path(self.state['checks'][index]['evidence'])
            record = json.loads(path.read_text())
            record['status'] = 'FAIL'
            record['execution']['native_exit_code'] = 1
            save(path, record)
            self.assertTrue(deep_loop.contract_issues(self.state, 'review'))
            record['status'] = 'PASS'
            record['execution']['native_exit_code'] = 0
            save(path, record)

    def test_exploration_and_agent_approval_never_authoritative(self):
        for field, value in (('status', 'exploratory'), ('approval', dict(self.contract['design']['approval'], role='agent'))):
            changed = copy.deepcopy(self.contract)
            changed['design'][field] = value
            save(self.path, changed)
            self.assertEqual(ui_design.route({'surface': 'ui', 'changes': ['navigation']}, self.path)['route'], 'product-design')

    def test_mobbin_research_is_not_target(self):
        self.contract['design']['references'][0]['role'] = 'research'
        self.contract['design']['references'][0]['origin'] = 'mobbin'
        self.contract['design']['references'][0]['rationale'] = 'Study the navigation pattern'
        receipt = json.loads(self.owner.read_text())
        receipt['design_sha256'] = ui_design.design_sha(self.contract['design'])
        save(self.owner, receipt)
        self.contract['design']['approval']['sha256'] = sha(self.owner)
        save(self.path, self.contract)
        result = ui_design.route({'surface': 'ui', 'changes': ['navigation']}, self.path)
        self.assertEqual(result['route'], 'product-design')
        self.assertIn('not an approved implementation target', result['diagnostic'])

    def test_non_ui_workflows_unchanged(self):
        self.assertEqual(ui_design.route({'surface': 'non_ui'})['route'], 'deep-loop')
        state = copy.deepcopy(self.state)
        del self.contract['design']
        del state['uiEvidence']
        save(self.path, self.contract)
        state['verificationContract']['sha256'] = sha(self.path)
        self.assertEqual(deep_loop.contract_issues(state, 'ship'), [])

    def test_preserved_pixel_evidence_and_current_source(self):
        self.assertEqual(self.pixels()['status'], 'PASS')
        self.assertEqual(deep_loop.contract_issues(self.state, 'ship'), [])
        for filename in ('expected.png', 'actual.png', 'diff.png', 'result.json', 'verifier.json', 'run.log', 'capture.json'):
            self.assertTrue((self.root / 'pixel-run' / filename).is_file(), filename)
        self.source.write_text('<button>Wrong action</button>')
        self.assertTrue(deep_loop.contract_issues(self.state, 'ship'))

    def test_unexplained_differences_remain_failures(self):
        self.pixels()
        self.state['uiEvidence']['differences'] = [{'category': 'geometry', 'evidence': 'Primary action misplaced'}]
        self.assertTrue(deep_loop.contract_issues(self.state, 'review'))

    def test_threshold_failure_cannot_be_reported_pass(self):
        self.pixels()
        path = Path(self.state['checks'][3]['evidence'])
        record = json.loads(path.read_text())
        record['metrics'][0]['current'] = 1
        save(path, record)
        self.assertTrue(deep_loop.contract_issues(self.state, 'ship'))

    def test_missing_or_malformed_proof_blocks(self):
        self.pixels()
        for value in ({}, {'source_manifest': 'missing', 'environment_manifest': str(self.environment), 'differences': []}):
            self.state['uiEvidence'] = value
            self.assertTrue(deep_loop.contract_issues(self.state, 'ship'))

    def test_unknown_inputs_and_greenfield_boundary(self):
        self.assertEqual(ui_design.route({'surface': 'ui', 'changes': ['unknown']})['route'], 'blocked')
        self.assertEqual(ui_design.route({'surface': 'ui', 'changes': ['navigation'],
                                         'greenfield_authorized': True})['route'], 'greenfield-build')
        self.assertEqual(ui_design.route({'surface': 'ui', 'changes': ['navigation'],
                                         'greenfield_authorized': 'yes'})['route'], 'blocked')

    def test_rebinding_cannot_self_approve_a_departure(self):
        self.contract['design']['critical_invariants'] = ['Agent selected a different hierarchy']
        save(self.path, self.contract)
        self.state['verificationContract']['sha256'] = sha(self.path)
        self.assertTrue(deep_loop.contract_issues(self.state, 'ship'))

    def test_existing_evidence_cannot_be_overwritten(self):
        self.pixels()
        before = {p.name: p.read_bytes() for p in (self.root / 'pixel-run').iterdir()}
        with self.assertRaises(ValueError):
            self.pixels()
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.root / 'pixel-run').iterdir()})

    def test_capture_and_viewport_state_coverage_are_required(self):
        self.contract['design']['required_states'].append('error')
        receipt = json.loads(self.owner.read_text())
        receipt['design_sha256'] = ui_design.design_sha(self.contract['design'])
        save(self.owner, receipt)
        self.contract['design']['approval']['sha256'] = sha(self.owner)
        save(self.path, self.contract)
        result = ui_design.route({'surface': 'ui', 'changes': ['flow']}, self.path)
        self.assertEqual(result['route'], 'product-design')
        self.assertIn('Every canonical viewport', result['diagnostic'])

    def test_threshold_change_requires_new_approval(self):
        self.pixel['threshold']['max_diff_ratio'] = 1
        save(self.path, self.contract)
        result = ui_design.route({'surface': 'ui', 'changes': ['flow']}, self.path)
        self.assertEqual(result['route'], 'product-design')
        self.assertIn('verification declarations changed', result['diagnostic'])

class EnforcementTests(unittest.TestCase):
    setUp = UIContractTests.setUp
    make_capture = UIContractTests.make_capture
    execute_independent = UIContractTests.execute_independent
    record = UIContractTests.record
    pixels = UIContractTests.pixels

    def renew(self):
        self.contract['design']['verification_sha256'] = ui_design.verification_sha(self.contract)
        receipt = json.loads(self.owner.read_text())
        receipt['design_sha256'] = ui_design.design_sha(self.contract['design'])
        save(self.owner, receipt)
        self.contract['design']['approval']['sha256'] = sha(self.owner)
        save(self.path, self.contract)
        self.state['verificationContract']['sha256'] = sha(self.path)

    # Reuse the existing complete fixture; these assertions expose rc4 escapes.
    def test_ui_evidence_without_binding_is_rejected(self):
        self.pixels()
        del self.state['verificationContract']
        self.assertTrue(deep_loop.contract_issues(self.state, 'review'))

    def test_critical_invariant_requires_measured_mapping(self):
        self.contract['design']['critical_invariants'] = ['Unmapped caption']
        self.renew()
        with self.assertRaises(ValueError):
            ui_design.design_data(self.contract, self.root)

    def test_missing_capture_geometry_is_blocked(self):
        capture = json.loads(self.capture.read_text())
        del capture['observed']
        save(self.capture, capture)
        with self.assertRaises((ValueError, KeyError)):
            ui_design.compare(self.path, 'pixels', self.capture, self.root / 'bad-capture', 'fixture1')

    def test_mechanism_only_record_is_not_execution(self):
        self.pixels()
        del self.state['uiEvidence']['invocations']
        self.assertTrue(deep_loop.contract_issues(self.state, 'review'))

    def refresh_receipts(self):
        self.state['uiEvidence']['invocations']['sha256'] = sha(self.invocations)
        for check in self.state['checks'][1:]:
            path = Path(check['evidence']); record = json.loads(path.read_text())
            for artifact in record['artifacts']:
                if artifact['path']==str(self.invocations): artifact['sha256']=sha(self.invocations)
            save(path,record)

    def test_complete_multiscreen_state_viewport_reference_coverage(self):
        template_pixel=copy.deepcopy(self.pixel)
        template_structure=copy.deepcopy(self.contract['verifiers'][1])
        self.contract['design']['required_states']=['default','error']
        self.contract['design']['canonical_viewports'].append(dict(self.contract['design']['canonical_viewports'][0],id='phone'))
        self.contract['design']['references'].append(dict(self.contract['design']['references'][0],id='settings-target'))
        cases=[]; visual=[]
        for viewport in ('desktop','phone'):
            for state in ('default','error'):
                case=dict(screen='dashboard' if viewport=='desktop' else 'settings',
                          reference='main' if viewport=='desktop' else 'settings-target',viewport=viewport,state=state)
                name=viewport+'-'+state
                capture=json.loads(self.capture.read_text());capture.update(case)
                path=save(self.root/(name+'-capture.json'),capture)
                native_case=dict(case,capture={'path':str(path),'sha256':sha(path)})
                native_path=save(self.root/(name+'-cases.json'),[native_case])
                cases.append(native_case)
                pixel=copy.deepcopy(template_pixel);pixel.update(id='pixels-'+name,fixture=case)
                structure=copy.deepcopy(template_structure);structure.update(id='structure-'+name,fixture=case)
                structure['argv']=[sys.executable,'-B',str(self.runner),structure['id'],str(self.source),str(native_path)]
                visual.extend([pixel,structure])
        self.contract['verifiers']=visual+self.contract['verifiers'][2:]
        self.contract['design']['verification']['visual']=[v['id'] for v in visual]
        coverage=next(v for v in self.contract['verifiers'] if v['id']=='responsive')
        coverage['fixture']['required_cases']=[dict(c,invariants=['R1']) for c in cases]
        save(self.native_cases,cases)
        self.renew()
        self.state['checks']=[{'name':v['id'],'verifierId':v['id'],'status':'passed','evidence':''} for v in self.contract['verifiers']]
        self.invocations.rename(self.root/'initial-invocations.json')
        self.execute_independent()
        for check in self.state['checks']:
            verifier=next(v for v in self.contract['verifiers'] if v['id']==check['verifierId'])
            if 'max_diff_ratio' in verifier['threshold']:
                capture_path=next(c['capture']['path'] for c in cases if ui_design.case_key(c)==ui_design.case_key(verifier['fixture']))
                out=self.root/verifier['id']; result=ui_design.compare(self.path,verifier['id'],capture_path,out,'fixture1')
                self.assertEqual(result['status'],'PASS');check['evidence']=str(out/'verifier.json')
            else:
                check['evidence']=str(save(self.root/(verifier['id']+'-complete.json'),self.record(verifier['id'])))
        self.assertEqual(deep_loop.contract_issues(self.state,'ship'),[])
        coverage['fixture']['required_cases'].pop()
        self.renew()
        with self.assertRaises(ValueError): ui_design.design_data(self.contract,self.root)

    def test_deleted_execution_input_retains_failed_receipt(self):
        self.runner.write_text("from pathlib import Path\nimport sys\nPath(sys.argv[2]).unlink()\nprint('{}')\n")
        for verifier in self.contract['verifiers'][1:]:
            verifier['implementation']['sha256'] = sha(self.runner)
        self.renew()
        self.invocations.rename(self.root / 'initial-invocations.json')
        batch = save(self.root / 'drift-checks.json', [
            {'name': v['id'], 'verifierId': v['id'], 'argv': v['argv']}
            for v in self.contract['verifiers'][1:]])
        args = argparse.Namespace(root=str(self.root), checks=str(batch), output=str(self.invocations),
                                  ui_request=str(self.request), contract=str(self.path), goal_id='fixture1',
                                  source_manifest=str(self.manifest), environment_manifest=str(self.environment))
        self.assertEqual(deep_loop.run_checks(args), 2)
        rows = json.loads(self.invocations.read_text())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'failed')
        self.assertEqual(rows[0]['stdout'].strip(), '{}')
        self.assertIn('drifted', rows[0]['stderr'])

    def test_complete_current_task_passes(self):
        self.assertEqual(self.pixels()['status'], 'PASS')
        self.assertEqual(deep_loop.contract_issues(self.state, 'ship'), [])

    def test_synthetic_origin_does_not_pass(self):
        self.pixels()
        path = Path(self.state['checks'][1]['evidence'])
        record = json.loads(path.read_text()); record['evidence_origin'] = 'fixture'
        save(path, record)
        self.assertTrue(deep_loop.contract_issues(self.state, 'review'))

    def test_missing_and_substituted_cases_reject(self):
        for cases in ([], [dict(self.case, invariants=['R1'], screen='settings')],
                      [dict(self.case, invariants=['R1'], reference='unknown')],
                      [dict(self.case, invariants=['R1'], state='error')],
                      [dict(self.case, invariants=['R1'], viewport='phone')]):
            self.contract['verifiers'][2]['fixture']['required_cases'] = cases
            self.renew()
            with self.assertRaises(ValueError):
                ui_design.design_data(self.contract, self.root)

    def test_actual_coverage_report_substitution_rejects(self):
        self.pixels()
        path = Path(self.state['checks'][2]['evidence'])
        record = json.loads(path.read_text())
        report = Path(next(a['path'] for a in record['artifacts'] if a['role']=='report'))
        native = json.loads(report.read_text()); native['cases'][0]['screen'] = 'settings'
        save(report, native)
        for artifact in record['artifacts']:
            if artifact['path']==str(report): artifact['sha256']=sha(report)
        rows = json.loads(self.invocations.read_text())
        rows[1]['stdout'] = json.dumps(native)
        save(self.invocations, rows)
        self.state['uiEvidence']['invocations']['sha256'] = sha(self.invocations)
        save(path, record)
        self.refresh_receipts()
        issues=deep_loop.contract_issues(self.state,'review')
        self.assertTrue(any('Actual required' in i for i in issues),issues)

    def test_unmatched_invocation_rejects(self):
        self.pixels()
        for field,value in [('goal_id','other-goal'),('argv',['package-tests']),('exitCode',1),
                            ('request_sha256','0'*64),('route_fingerprint','0'*64)]:
            rows=json.loads(self.invocations.read_text()); old=rows[0][field]; rows[0][field]=value
            save(self.invocations,rows)
            self.refresh_receipts()
            issues=deep_loop.contract_issues(self.state,'review')
            self.assertTrue(any('Unmatched task-specific execution' in i for i in issues),(field,issues))
            rows[0][field]=old; save(self.invocations,rows)
            self.refresh_receipts()

    def test_invalid_geometry_density_and_crop_block(self):
        for mutation in ({'width':9},{'device_scale_factor':2},{'crop':[1,0,8,8]},
                         {'frame':[0,0,7,8]},{'scroll_top':339}):
            capture=json.loads(self.capture.read_text()); capture['observed'].update(mutation)
            path=save(self.root/'bad-geometry.json',capture)
            with self.assertRaises(ValueError):
                ui_design.compare(self.path,'pixels',path,self.root/'blocked','fixture1')

    def test_claimed_crop_cannot_hide_changed_original(self):
        original=self.root/'other.png'; Image.new('RGB',(8,8),'black').save(original)
        capture=json.loads(self.capture.read_text()); capture['original']={'path':str(original),'sha256':sha(original)}
        path=save(self.root/'bad-original.json',capture)
        with self.assertRaises(ValueError):
            ui_design.compare(self.path,'pixels',path,self.root/'blocked','fixture1')

    def test_missing_approval_and_stale_declaration_reject(self):
        self.pixels()
        self.owner.unlink()
        self.assertTrue(deep_loop.contract_issues(self.state,'review'))

    def test_registered_ui_cannot_drop_design_extension(self):
        del self.contract['design']; save(self.path,self.contract)
        self.state['verificationContract']['sha256']=sha(self.path)
        self.assertTrue(deep_loop.contract_issues(self.state,'review'))

def render_caption(source, image_path, capture_path, cases_path):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True, channel='chrome')
        try:
            page = browser.new_page(viewport={'width': 300, 'height': 200}, device_scale_factor=1)
            page.set_content(Path(source).read_text())
            page.evaluate('document.fonts.ready')
            caption = page.locator('#caption')
            visible = caption.count() == 1 and caption.is_visible() and caption.inner_text() == 'AT MY BALL'
            if visible:
                visible = caption.evaluate("e => {const r=e.getBoundingClientRect(); const s=getComputedStyle(e); return r.width>0 && r.height>0 && r.left>=0 && r.top>=0 && r.right<=innerWidth && r.bottom<=innerHeight && Number(s.opacity)>0}")
            observed = page.evaluate('({width:innerWidth,height:innerHeight,device_scale_factor:devicePixelRatio,crop:[0,0,300,200],frame:[0,0,300,200],scroll_top:scrollY})')
            page.screenshot(path=str(image_path))
            capture = json.loads(Path(capture_path).read_text())
            capture.update(image={'path':str(image_path),'sha256':sha(Path(image_path))},
                           original={'path':str(image_path),'sha256':sha(Path(image_path))},observed=observed)
            save(Path(capture_path),capture)
            case = {k:capture[k] for k in ('screen','reference','viewport','state')}
            case['capture'] = {'path':str(capture_path),'sha256':sha(Path(capture_path))}
            save(Path(cases_path),[case])
            return {'metrics': {'R1': int(visible)}, 'cases': [case]}
        finally:
            browser.close()


@unittest.skipUnless(os.environ.get('DEEP_LOOP_BROWSER_TRIAL') == '1', 'Explicit browser capability trial not selected')
class RenderedCaptionTests(unittest.TestCase):
    setUp = UIContractTests.setUp
    make_capture = UIContractTests.make_capture
    execute_independent = UIContractTests.execute_independent
    record = UIContractTests.record
    pixels = UIContractTests.pixels
    renew = EnforcementTests.renew

    def trial(self, seed):
        self.source.write_text('<style>body{margin:0;background:white}button{margin:70px;font:12px Arial}</style><button><span id="caption">AT MY BALL</span></button>')
        self.contract['design']['canonical_viewports'][0].update(width=300,height=200)
        self.pixel['threshold'].update(tolerance=40,max_diff_ratio=0.40,region_max_diff_ratio=0.40)
        render_caption(self.source,self.actual,self.capture,self.native_cases)
        self.reference.write_bytes(self.actual.read_bytes())
        self.contract['design']['references'][0]['sha256']=sha(self.reference)
        if seed=='removed': self.source.write_text(self.source.read_text().replace('<span id="caption">AT MY BALL</span>',''))
        if seed=='hidden': self.source.write_text(self.source.read_text()+'<style>#caption{visibility:hidden}</style>')
        save(self.manifest,{'files': {'app.html':sha(self.source)}})
        structure=self.contract['verifiers'][1]
        structure['implementation']={'path':str(Path(__file__).resolve()),'sha256':sha(Path(__file__))}
        structure['argv']=[sys.executable,'-B',str(Path(__file__).resolve()),'--render-caption',str(self.source),str(self.actual),str(self.capture),str(self.native_cases)]
        self.renew()
        # Preserve the initial fixture run. New execution gets a new receipt directory.
        self.invocations.rename(self.root/'initial-invocations.json')
        self.execute_independent()
        for check in self.state['checks'][1:]:
            record=self.record(check['verifierId'])
            if check['verifierId']=='structure': record['execution']['verifier_fingerprint']=sha(Path(__file__))
            check['evidence']=str(save(self.root/(check['verifierId']+'-rendered.json'),record))
        result=ui_design.compare(self.path,'pixels',self.capture,self.root/'rendered-pixels','fixture1')
        self.state['checks'][0]['evidence']=str(self.root/'rendered-pixels/verifier.json')
        issues=deep_loop.contract_issues(self.state,'review')
        save(self.root/'state.json',self.state)
        save(self.root/'trial-result.json',{'seed':seed,'pixel_status':result['status'],
             'critical_caption':json.loads(self.invocations.read_text())[0]['stdout'], 'gate_issues':issues,
             'scope':'Actual isolated browser fixture; no OpenRound or native application proof'})
        self.assertEqual(result['status'],'PASS')
        if seed: self.assertIn('structure: declared threshold not met',issues)
        else: self.assertEqual(issues,[])

    def test_rendered_removed_caption_fails_with_pixel_pass(self): self.trial('removed')
    def test_rendered_hidden_caption_fails_with_pixel_pass(self): self.trial('hidden')
    def test_rendered_complete_caption_passes(self): self.trial('')

if __name__ == '__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--render-caption':
        print(json.dumps(render_caption(*map(Path,sys.argv[2:]))))
    else:
        unittest.main()
