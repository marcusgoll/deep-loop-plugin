import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import deep_loop

HELPER = Path(__file__).with_name('deep_loop.py')


class DeliveryChecks(unittest.TestCase):
    def test_schema_three_requires_delivery_authority_and_branch_disposition(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            def run(*args):
                return subprocess.run(
                    [sys.executable, str(HELPER), '--root', temp, *args],
                    capture_output=True,
                    text=True,
                )

            self.assertEqual(run('init', '--task', 'Ship safely', '--session', 'delivery').returncode, 0)
            path = root / '.deep-delivery' / 'state.json'
            state = json.loads(path.read_text())
            self.assertEqual(state['schemaVersion'], 4)
            self.assertEqual(state['uiRoute']['kind'], 'pending')
            self.assertEqual(state['delivery']['endpointDecision']['status'], 'pending')
            self.assertEqual(state['delivery']['branchDisposition']['status'], 'pending')

            state['uiRoute'] = {'kind': 'not_applicable', 'reason': 'Delivery-only fixture'}
            state['checks'] = [{'name': 'acceptance', 'status': 'passed', 'evidence': 'current tests'}]
            state['delivery'].update(
                endpoint='Pull request with green checks',
                status='verified',
                evidence='PR readback',
                revision='abc123',
            )
            path.write_text(json.dumps(state))
            self.assertNotEqual(run('validate', '--stage', 'ship').returncode, 0)

            state['delivery']['endpointDecision'] = {
                'status': 'settled',
                'source': 'repository',
                'evidence': 'Repository policy selects a pull request',
            }
            state['delivery']['branchDisposition'] = {
                'status': 'verified',
                'kind': 'kept_local',
                'revision': 'abc123',
                'evidence': 'Local branch retained',
            }
            path.write_text(json.dumps(state))
            result = run('validate', '--stage', 'ship')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Keeping a task branch local requires user-sourced endpoint authority', result.stdout)

            state['delivery']['endpointDecision'].update(
                source='user',
                evidence='User explicitly selected local-only retention',
            )
            path.write_text(json.dumps(state))
            self.assertEqual(run('validate', '--stage', 'ship').returncode, 0)

            state['delivery']['branchDisposition'] = {
                'kind': 'not_applicable',
                'reason': 'The artifact is not maintained on a task branch',
            }
            state['delivery']['revision'] = ''
            path.write_text(json.dumps(state))
            result = run('validate', '--stage', 'ship')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('SHIP requires an immutable delivery revision', result.stdout)

    def test_schema_three_external_ci_requires_exact_revision_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            def run(*args):
                return subprocess.run(
                    [sys.executable, str(HELPER), '--root', temp, *args],
                    capture_output=True,
                    text=True,
                )

            self.assertEqual(run('init', '--task', 'Hosted checks', '--session', 'hostedci').returncode, 0)
            path = root / '.deep-hostedci' / 'state.json'
            state = json.loads(path.read_text())
            state['uiRoute'] = {'kind': 'not_applicable', 'reason': 'Hosted-CI fixture'}
            state['checks'] = [{
                'name': 'GitHub-hosted XCUI',
                'kind': 'external_ci',
                'status': 'passed',
                'evidence': 'Workflow YAML contains the job',
            }]
            state['delivery'] = {
                'endpoint': 'Pull request',
                'endpointDecision': {
                    'status': 'settled',
                    'source': 'user',
                    'evidence': 'User selected a pull request',
                },
                'branchDisposition': {
                    'status': 'verified',
                    'kind': 'pull_request',
                    'revision': 'abc123',
                    'evidence': 'PR 42 targets main',
                },
                'revision': 'abc123',
                'status': 'verified',
                'evidence': 'PR 42 read back at abc123',
            }
            path.write_text(json.dumps(state))
            result = run('validate', '--stage', 'ship')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Hosted CI check requires structured external evidence', result.stdout)

            state['checks'][0]['externalEvidence'] = {
                'provider': 'github',
                'url': 'https://github.com/example/project/actions/runs/42',
                'revision': 'wrong-sha',
                'conclusion': 'success',
            }
            path.write_text(json.dumps(state))
            result = run('validate', '--stage', 'ship')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Hosted CI revision differs from delivery revision', result.stdout)

            state['checks'][0]['externalEvidence']['revision'] = 'abc123'
            path.write_text(json.dumps(state))
            self.assertEqual(run('validate', '--stage', 'ship').returncode, 0)

    def test_schema_three_multi_target_delivery_binds_each_ci_and_branch_to_target(self):
        with tempfile.TemporaryDirectory() as temp:
            def run(*args):
                return subprocess.run(
                    [sys.executable, str(HELPER), '--root', temp, *args],
                    capture_output=True,
                    text=True,
                )

            self.assertEqual(run('init', '--task', 'Ship to two pull requests', '--session', 'multici1').returncode, 0)
            path = Path(temp) / '.deep-multici1' / 'state.json'
            state = json.loads(path.read_text())
            state['uiRoute'] = {'kind': 'not_applicable', 'reason': 'CI delivery validation fixture'}
            ios_target = 'marcusgoll/personal-logbook-ios#12'
            server_target = 'marcusgoll/logbook#203'
            ios_revision = 'f' * 40
            server_revision = '5' * 40

            def delivery_target(target_id, revision, evidence):
                return {
                    'id': target_id,
                    'revision': revision,
                    'evidence': evidence,
                    'branchDisposition': {
                        'kind': 'pull_request',
                        'status': 'verified',
                        'revision': revision,
                        'evidence': evidence,
                    },
                }

            def ci_check(name, target_id, revision, url):
                return {
                    'name': name,
                    'kind': 'external_ci',
                    'status': 'passed',
                    'evidence': f'Passed hosted CI readback for {target_id} at {revision}',
                    'externalEvidence': {
                        'provider': 'GitHub Actions',
                        'url': url,
                        'revision': revision,
                        'conclusion': 'success',
                        'target': target_id,
                    },
                }

            state['checks'] = [
                ci_check(ios_target, ios_target, ios_revision, 'https://github.com/example/ios/actions/runs/12'),
                ci_check(server_target, server_target, server_revision, 'https://github.com/example/server/actions/runs/203'),
            ]
            state['delivery'] = {
                'endpoint': 'Two pull requests',
                'endpointDecision': {
                    'status': 'settled',
                    'source': 'user',
                    'evidence': 'User selected two pull requests as the delivery endpoint',
                },
                'targets': [
                    delivery_target(ios_target, ios_revision, 'PR #12 read back at its exact head'),
                    delivery_target(server_target, server_revision, 'PR #203 read back at its exact head'),
                ],
                'status': 'verified',
                'evidence': 'Both pull requests were independently read back at their exact heads',
            }
            path.write_text(json.dumps(state))
            self.assertEqual(run('validate', '--stage', 'ship').returncode, 0)

            state['schemaVersion'] = 3
            path.write_text(json.dumps(state))
            self.assertEqual(run('validate', '--stage', 'ship').returncode, 0)
            state['schemaVersion'] = 4

            state['checks'][0]['externalEvidence']['target'] = 'unknown/repo#1'
            path.write_text(json.dumps(state))
            result = run('validate', '--stage', 'ship')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Hosted CI target is not declared in delivery targets', result.stdout)

            state['checks'][0]['externalEvidence']['target'] = ios_target
            state['checks'][0]['externalEvidence']['revision'] = server_revision
            path.write_text(json.dumps(state))
            result = run('validate', '--stage', 'ship')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Hosted CI revision differs from delivery target revision', result.stdout)

            state['checks'][0]['externalEvidence']['revision'] = ios_revision
            state['delivery']['targets'][0]['branchDisposition']['revision'] = server_revision
            path.write_text(json.dumps(state))
            result = run('validate', '--stage', 'ship')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Branch disposition revision differs from its delivery target revision', result.stdout)

            state['delivery']['targets'][0]['branchDisposition']['revision'] = ios_revision
            state['delivery']['revision'] = ios_revision + '+' + server_revision
            path.write_text(json.dumps(state))
            result = run('validate', '--stage', 'ship')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Multi-target delivery must not declare a singular revision or branch disposition', result.stdout)

    def test_schema_four_build_gate_requires_ui_classification_and_greenfield_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            def run(*args):
                return subprocess.run([sys.executable, str(HELPER), '--root', temp, *args], capture_output=True, text=True)

            self.assertEqual(run('init', '--task', 'Design a new family flow', '--session', 'uiroute1').returncode, 0)
            path = root / '.deep-uiroute1' / 'state.json'
            state = json.loads(path.read_text())
            state['delivery']['endpointDecision'] = {
                'status': 'settled', 'source': 'user', 'evidence': 'User selected a pull request'
            }
            path.write_text(json.dumps(state))
            result = run('validate', '--stage', 'build')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Classify uiRoute before BUILD', result.stdout)

            state['uiRoute'] = {'kind': 'specified', 'approvedTarget': 'Existing settings row', 'evidence': 'Repository pattern'}
            path.write_text(json.dumps(state))
            self.assertEqual(run('validate', '--stage', 'build').returncode, 0)

            state['uiRoute'] = {
                'kind': 'greenfield',
                'options': ['Timeline', 'Status card', 'Map'],
                'selectedDirection': 'Status card',
                'selection': {'source': 'user', 'evidence': 'User selected option 2'},
                'designProvenance': {'route': 'product-design', 'evidence': 'design-qa.md'},
                'mobbin': {'status': 'inspected', 'evidence': 'Mobbin flight-tracking packet'},
                'affectedSurfaces': ['Family preview'],
                'plannedEvidence': ['iPhone and iPad screenshots'],
            }
            path.write_text(json.dumps(state))
            self.assertEqual(run('validate', '--stage', 'build').returncode, 0)

            state['uiRoute']['options'] = ['Timeline', 'Status card']
            path.write_text(json.dumps(state))
            result = run('validate', '--stage', 'build')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('exactly three distinct named visual options', result.stdout)

    def test_complete_validates_ship_before_atomic_transition(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            def run(*args):
                return subprocess.run([sys.executable, str(HELPER), '--root', temp, *args], capture_output=True, text=True)

            self.assertEqual(run('init', '--task', 'Close safely', '--session', 'complete').returncode, 0)
            path = root / '.deep-complete' / 'state.json'
            state = json.loads(path.read_text())
            state.update(phase='SHIP', uiRoute={'kind': 'not_applicable', 'reason': 'No UI work'})
            state['checks'] = [{'name': 'acceptance', 'status': 'passed', 'evidence': 'fixture passed'}]
            state['delivery'] = {
                'endpoint': 'Pull request',
                'endpointDecision': {'status': 'settled', 'source': 'repository', 'evidence': 'PR workflow'},
                'branchDisposition': {'status': 'pending', 'kind': 'pull_request', 'evidence': ''},
                'revision': 'abc123',
                'status': 'verified',
                'evidence': 'PR read back at abc123',
            }
            path.write_text(json.dumps(state))
            result = run('complete')
            self.assertNotEqual(result.returncode, 0)
            unchanged = json.loads(path.read_text())
            self.assertTrue(unchanged['active'])
            self.assertFalse(unchanged['complete'])
            self.assertEqual(unchanged['phase'], 'SHIP')

            state['delivery']['branchDisposition'] = {
                'status': 'verified', 'kind': 'pull_request', 'revision': 'abc123', 'evidence': 'PR 7 head readback'
            }
            path.write_text(json.dumps(state))
            self.assertEqual(run('complete').returncode, 0)
            closed = json.loads(path.read_text())
            self.assertFalse(closed['active'])
            self.assertTrue(closed['complete'])
            self.assertEqual(closed['phase'], 'COMPLETE')
            self.assertEqual(run('complete').returncode, 0)

    def test_schema_two_delivery_behavior_remains_compatible(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / '.deep-legacyv2'
            folder.mkdir()
            (root / '.deep-current.json').write_text(json.dumps({'path': str(folder)}))
            (folder / 'state.json').write_text(json.dumps({
                'schemaVersion': 2,
                'task': 'Existing schema two task',
                'complete': False,
                'checks': [{'name': 'fixture', 'status': 'passed', 'evidence': 'observed'}],
                'delivery': {'endpoint': 'local artifact', 'status': 'verified', 'evidence': 'read back'},
            }))
            result = subprocess.run(
                [sys.executable, str(HELPER), '--root', temp, 'validate', '--stage', 'ship'],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_bound_contract_rejects_disposition_substitution_and_endpoint_drift(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def run(*args):
                return subprocess.run([sys.executable, str(HELPER), '--root', temp, *args],
                                      capture_output=True, text=True)
            self.assertEqual(run('init', '--task', 'Contract export', '--session', 'contract').returncode, 0)
            path = root / '.deep-contract' / 'state.json'
            contract_path = root / 'contract.json'
            contract = {'name': 'Export', 'scope': 'Saved CLI', 'status': 'NOT_RUN',
                        'requirements': [{'id': 'R1', 'outcome': 'Exports rows', 'invariant': 'Rows match', 'priority': 'blocking'}],
                        'verifiers': [{'id': 'V1', 'covers': ['R1'], 'class': 'deterministic', 'status': 'implemented',
                                       'expected': 'Rows equal fixture', 'gate': 'blocking'}], 'gaps': [],
                        'ship_gate': dict.fromkeys(('require_all_blocking_verifiers_pass', 'require_zero_blocking_gaps',
                                                   'require_human_approvals_recorded', 'require_evidence_matches_revision'), True)}
            def save_contract():
                contract_path.write_text(json.dumps(contract), encoding='utf-8')
            save_contract()
            def bind():
                result = run('bind-contract', '--contract', str(contract_path), '--endpoint', 'Saved CLI')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return json.loads(path.read_text())
            state = bind()
            state['schemaVersion'] = 2
            self.assertNotEqual(run('validate', '--stage', 'ship').returncode, 0)
            state['checks'] = [{'name': 'All requirements discussed', 'status': 'passed', 'evidence': 'Report written'}]
            state['delivery'] = {'endpoint': 'Saved CLI', 'status': 'verified', 'evidence': 'Current CLI invocation'}
            def save():
                path.write_text(json.dumps(state), encoding='utf-8')
            save()
            self.assertNotEqual(run('validate', '--stage', 'ship').returncode, 0)
            state['checks'] = [{'name': 'Row check', 'verifierId': 'V1', 'status': 'passed', 'evidence': 'Current rows match'}]
            save()
            self.assertEqual(run('validate', '--stage', 'ship').returncode, 0)
            good = json.loads(json.dumps(state))
            for bad in ('not_applicable', 'pending', 'failed'):
                state['checks'][0].update(status=bad, reason='Only reporting')
                save()
                self.assertNotEqual(run('validate', '--stage', 'ship').returncode, 0)
            state = json.loads(json.dumps(good))
            state['checks'].append(dict(state['checks'][0]))
            save()
            self.assertNotEqual(run('validate', '--stage', 'ship').returncode, 0)
            state = json.loads(json.dumps(good))
            state['delivery']['endpoint'] = 'Discovery report'
            save()
            self.assertNotEqual(run('validate', '--stage', 'ship').returncode, 0)
            state = json.loads(json.dumps(good))
            save()
            contract['requirements'].append({'id': 'R2', 'outcome': 'Import', 'invariant': 'Import works', 'priority': 'blocking'})
            contract['gaps'] = [{'id': 'G2', 'requirement': 'R2', 'risk': 'No import proof', 'recommended_verifier': 'Import check',
                                 'priority': 'blocking', 'blocks': 'shipping'}]
            save_contract()
            self.assertNotEqual(run('validate', '--stage', 'ship').returncode, 0)
            state = bind()
            state['schemaVersion'] = 2
            self.assertEqual(state['checks'][0]['status'], 'pending')
            state['checks'][0].update(status='passed', evidence='Current rows match')
            state['delivery'].update(status='verified', evidence='Current CLI invocation')
            save()
            self.assertEqual(run('validate', '--stage', 'review').returncode, 0)
            self.assertNotEqual(run('validate', '--stage', 'ship').returncode, 0)
            contract['gaps'][0]['blocks'] = 'none'
            save_contract()
            state = bind()
            state['schemaVersion'] = 2
            state['checks'][0].update(status='passed', evidence='Current rows match')
            state['delivery'].update(status='verified', evidence='Current CLI invocation')
            save()
            self.assertNotEqual(run('validate', '--stage', 'ship').returncode, 0)

    def test_contract_refresh_preserves_evidence_only_for_unchanged_semantics(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def run(*args):
                return subprocess.run([sys.executable, str(HELPER), '--root', temp, *args],
                                      capture_output=True, text=True)
            self.assertEqual(run('init', '--task', 'Refresh contract', '--session', 'refresh1').returncode, 0)
            state_path = root / '.deep-refresh1' / 'state.json'
            contract_path = root / 'contract.json'
            contract = {'name': 'Export', 'scope': 'Saved CLI', 'status': 'NOT_RUN',
                        'requirements': [{'id': 'R1', 'outcome': 'Exports rows', 'invariant': 'Rows match', 'priority': 'blocking'}],
                        'verifiers': [{'id': 'V1', 'covers': ['R1'], 'class': 'deterministic', 'status': 'implemented',
                                       'expected': 'Rows equal fixture', 'gate': 'blocking'}], 'gaps': [],
                        'ship_gate': dict.fromkeys(('require_all_blocking_verifiers_pass', 'require_zero_blocking_gaps',
                                                   'require_human_approvals_recorded', 'require_evidence_matches_revision'), True)}
            contract_path.write_text(json.dumps(contract), encoding='utf-8')
            self.assertEqual(run('bind-contract', '--contract', str(contract_path), '--endpoint', 'Saved CLI').returncode, 0)
            state = json.loads(state_path.read_text())
            state['phase'] = 'SHIP'
            state['checks'][0].update(status='passed', evidence='rows.json')
            state['delivery'].update(status='verified', evidence='saved export')
            state_path.write_text(json.dumps(state), encoding='utf-8')
            preserved = json.loads(state_path.read_text())

            contract['status'] = 'PASS'
            contract['verifiers'][0]['status'] = 'existing'
            contract_path.write_text(json.dumps(contract), encoding='utf-8')
            result = run('refresh-contract', '--contract', str(contract_path), '--endpoint', 'Saved CLI')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            refreshed = json.loads(state_path.read_text())
            self.assertEqual(refreshed['phase'], preserved['phase'])
            self.assertEqual(refreshed['checks'], preserved['checks'])
            self.assertEqual(refreshed['delivery'], preserved['delivery'])
            self.assertNotEqual(refreshed['verificationContract']['sha256'], preserved['verificationContract']['sha256'])
            self.assertEqual(refreshed['verificationContract']['semanticsSha256'],
                             preserved['verificationContract']['semanticsSha256'])

            before_rejection = state_path.read_bytes()
            contract['requirements'][0]['invariant'] = 'Rows and ordering match'
            contract_path.write_text(json.dumps(contract), encoding='utf-8')
            result = run('refresh-contract', '--contract', str(contract_path), '--endpoint', 'Saved CLI')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('semantics changed', result.stderr)
            self.assertEqual(state_path.read_bytes(), before_rejection)
            self.assertNotEqual(run('refresh-contract', '--contract', str(contract_path),
                                    '--endpoint', 'Different endpoint').returncode, 0)

    def test_contract_refresh_rejects_legacy_binding_without_semantic_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / '.deep-legacy1'
            folder.mkdir()
            contract_path = root / 'contract.json'
            contract = {'name': 'Export', 'scope': 'Saved CLI', 'status': 'NOT_RUN',
                        'requirements': [{'id': 'R1', 'outcome': 'Exports rows', 'invariant': 'Rows match', 'priority': 'blocking'}],
                        'verifiers': [{'id': 'V1', 'covers': ['R1'], 'class': 'deterministic', 'status': 'implemented',
                                       'expected': 'Rows equal fixture', 'gate': 'blocking'}], 'gaps': [],
                        'ship_gate': dict.fromkeys(('require_all_blocking_verifiers_pass', 'require_zero_blocking_gaps',
                                                   'require_human_approvals_recorded', 'require_evidence_matches_revision'), True)}
            contract_path.write_text(json.dumps(contract), encoding='utf-8')
            (folder / 'state.json').write_text(json.dumps({
                'schemaVersion': 2, 'task': 'Legacy', 'complete': False,
                'verificationContract': {'path': str(contract_path), 'sha256': 'a' * 64, 'endpoint': 'Saved CLI'},
            }), encoding='utf-8')
            result = subprocess.run([
                sys.executable, str(HELPER), '--root', temp, 'refresh-contract', '--path', str(folder),
                '--contract', str(contract_path), '--endpoint', 'Saved CLI',
            ], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('use bind-contract and rerun evidence', result.stderr)

    def test_selection_requires_an_unambiguous_locator(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def run(*args):
                return subprocess.run([sys.executable, str(HELPER), '--root', temp, *args], capture_output=True, text=True)
            self.assertEqual(run('init', '--task', 'First', '--session', 'first123').returncode, 0)
            pointer = root / '.deep-current.json'
            pointer.unlink()
            self.assertEqual(run('status').returncode, 0)
            self.assertEqual(run('init', '--task', 'Second', '--session', 'second12').returncode, 0)
            # A different chat's pointer selection cannot redirect an explicit locator.
            self.assertIn('Second', run('status').stdout)
            self.assertIn('First', run('status', '--session', 'first123').stdout)
            self.assertIn('First', run('status', '--path', str(root / '.deep-first123')).stdout)
            self.assertIn('second12', pointer.read_text())
            pointer.unlink()
            before = {str(p): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            self.assertNotEqual(run('status').returncode, 0)
            self.assertEqual(before, {str(p): p.read_bytes() for p in root.rglob('*') if p.is_file()})
            self.assertEqual(run('status', '--session', 'first123').returncode, 0)
            pointer.write_text(json.dumps({'path': str(root / '.deep-missing1')}))
            self.assertNotEqual(run('status').returncode, 0)
            self.assertEqual(run('use', '--session', 'first123').returncode, 0)
            self.assertIn('First', run('status').stdout)

    def test_failed_atomic_replace_preserves_checkpoint(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'state.json'
            path.write_bytes(b'{"original":true}\n')
            original = path.read_bytes()
            with patch.object(os, 'replace', side_effect=OSError('write denied')):
                with self.assertRaises(OSError):
                    deep_loop.write_json(path, {'updated': True})
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(temp).iterdir()), [path])
            deep_loop.write_json(path, {'updated': '\u2603'})
            self.assertEqual(deep_loop.read_json(path), {'updated': '\u2603'})

    def test_tracker_selection_and_completion(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def run(*args):
                return subprocess.run([sys.executable, str(HELPER), '--root', temp, *args],
                                      capture_output=True, text=True)
            self.assertEqual(run('init', '--task', 'Tracker', '--session', 'tracker1').returncode, 0)
            path = root / '.deep-tracker1' / 'state.json'
            state = json.loads(path.read_text())
            state['schemaVersion'] = 2
            state['checks'] = [{'name': 'fixture', 'status': 'passed', 'evidence': 'observed'}]
            state['delivery'] = {'endpoint': 'fixture', 'status': 'verified', 'evidence': 'readback'}
            a = {'id': 'A', 'title': 'Build "first" \u2603', 'kind': 'task', 'status': 'pending',
                 'acceptance': 'Artifact works', 'dependsOn': [], 'owner': ''}
            b = dict(a, id='B', title='Verify', dependsOn=['A'], kind='issue')
            state['tasks'] = [a, b]
            def save():
                path.write_text(json.dumps(state))
            save()
            result = run('next')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([t['id'] for t in json.loads(result.stdout)['ready']], ['A'])
            self.assertNotEqual(run('validate', '--stage', 'ship').returncode, 0)
            a.update(status='done', evidence='saved artifact executed')
            save()
            self.assertEqual([t['id'] for t in json.loads(run('next').stdout)['ready']], ['B'])
            b['owner'] = 'another-chat'
            save()
            self.assertEqual(json.loads(run('next').stdout)['ready'], [])
            b.update(status='blocked', blocker='Need login', nextAction='Owner logs in')
            save()
            self.assertEqual(json.loads(run('next').stdout)['queueState'], 'waiting')
            b.update(status='done', evidence='Fresh verification')
            save()
            self.assertEqual(run('validate', '--stage', 'ship').returncode, 0)
            self.assertEqual(json.loads(run('next').stdout)['queueState'], 'terminal')
            graph = run('graph')
            self.assertEqual(graph.returncode, 0, graph.stderr)
            self.assertIn('n0 --> n1', graph.stdout)
            self.assertIn('#34;first#34;', graph.stdout)
            self.assertIn('#9731;', graph.stdout)
            for change in ({'dependsOn': ['missing']}, {'dependsOn': ['B']},
                           {'evidence': ''}, {'owner': 42}, {'dependsOn': 'B'},
                           {'status': 'mystery'}, {'kind': 'unknown'}, {'status': 'running', 'owner': ''},
                           {'status': 'blocked'}, {'status': 'cancelled'}, {'acceptance': ''}):
                original = dict(a)
                a.update(change)
                save()
                self.assertNotEqual(run('next').returncode, 0, change)
                self.assertNotEqual(run('validate', '--stage', 'ship').returncode, 0, change)
                self.assertNotEqual(run('graph').returncode, 0, change)
                a.clear()
                a.update(original)
            for records in ([a, a], {}, [None]):
                state['tasks'] = records
                save()
                self.assertNotEqual(run('next').returncode, 0)
            state['tasks'] = [a, b]
            a.update(status='cancelled', reason='User removed this slice')
            b.update(status='pending', owner='')
            save()
            self.assertEqual(json.loads(run('next').stdout)['ready'], [])
            b.update(status='done')
            save()
            self.assertNotEqual(run('validate', '--stage', 'ship').returncode, 0)

    def test_scan_is_read_only_and_reports_each_session(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            records = {
                'old12345': {'task': 'Legacy', 'active': True, 'complete': False, 'phase': 'SHIP', 'blocker': 'Offline'},
                'done1234': {'schemaVersion': 2, 'task': 'Completed with exclusions', 'complete': True, 'active': False},
                'bad12345': {'schemaVersion': 2, 'task': 'False completion', 'complete': True, 'tasks': [
                    {'id': 'A', 'title': 'Still open', 'kind': 'task', 'status': 'pending', 'acceptance': 'works'}]},
            }
            for name, state in records.items():
                folder = root / ('.deep-' + name)
                folder.mkdir()
                (folder / 'state.json').write_text(json.dumps(state))
            corrupt = root / '.deep-corrupt1'
            corrupt.mkdir()
            (corrupt / 'state.json').write_text('{')
            (root / '.deep-current.json').write_text('{"path":"untouched"}')
            nested = root / 'another-project' / '.deep-nested12'
            nested.mkdir(parents=True)
            (nested / 'state.json').write_text(json.dumps({'task': 'Independent nested project', 'complete': False}))
            before = {str(p): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            result = subprocess.run([sys.executable, str(HELPER), '--root', temp, 'scan'], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            report = json.loads(result.stdout)
            self.assertEqual({Path(r['path']).name for r in report}, {'.deep-old12345', '.deep-bad12345', '.deep-corrupt1'})
            self.assertEqual(before, {str(p): p.read_bytes() for p in root.rglob('*') if p.is_file()})

    def test_git_exclusion_in_repo_and_worktree(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'repo'
            subprocess.run(['git', 'init', str(root)], check=True, capture_output=True)
            exclude = root / '.git' / 'info' / 'exclude'
            exclude.write_bytes(b'# Preserve me\r\nlocal-only.txt')
            original = exclude.read_bytes()
            nested = root / 'nested'
            nested.mkdir()

            def run(where, *args):
                return subprocess.run([sys.executable, str(HELPER), '--root', str(where), *args],
                                      capture_output=True, text=True)

            result = run(nested, 'init', '--task', 'Ignored checkpoint', '--session', 'abcdef12')
            self.assertEqual(result.returncode, 0, result.stderr)
            ignored = subprocess.run(['git', '-C', str(root), 'check-ignore',
                                      'nested/.deep-abcdef12/state.json', 'nested/.deep-current.json'],
                                     capture_output=True, text=True)
            self.assertEqual(ignored.returncode, 0, ignored.stdout + ignored.stderr)
            self.assertEqual(len(ignored.stdout.splitlines()), 2)
            self.assertTrue(exclude.read_bytes().startswith(original))
            protected = exclude.read_bytes()
            self.assertEqual(run(root, 'exclude').returncode, 0)
            self.assertEqual(exclude.read_bytes(), protected)
            self.assertEqual(subprocess.run(['git', '-C', str(root), 'ls-files'],
                                           capture_output=True, text=True).stdout, '')
            # Linked-worktree metadata fixture needs no commit or branch mutation.
            worktree = Path(temp) / 'worktree'
            worktree.mkdir()
            admin = root / '.git' / 'worktrees' / 'checkpoint-test'
            admin.mkdir(parents=True)
            (admin / 'commondir').write_text('../..\n')
            (admin / 'HEAD').write_text('ref: refs/heads/checkpoint-test\n')
            (admin / 'gitdir').write_text(str(worktree / '.git') + '\n')
            (worktree / '.git').write_text('gitdir: ' + str(admin) + '\n')
            result = run(worktree, 'init', '--task', 'Worktree checkpoint', '--session', '123456ab')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(subprocess.run(['git', '-C', str(worktree), 'check-ignore',
                                             '.deep-123456ab/state.json', '.deep-current.json'],
                                            capture_output=True, text=True).returncode, 0)
            self.assertEqual(exclude.read_bytes(), protected)

    def test_session_to_delivery(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            def run(*args):
                return subprocess.run([sys.executable, str(HELPER), '--root', temp, *args],
                                      capture_output=True, text=True)

            self.assertEqual(run('init', '--task', 'Local CSV export', '--session', 'abcdef12').returncode, 0)
            folder = root / '.deep-abcdef12'
            self.assertEqual({p.name for p in folder.iterdir()}, {'state.json', 'plan.md'})
            path = folder / 'state.json'
            state = json.loads(path.read_text())
            state['schemaVersion'] = 2

            def save():
                path.write_text(json.dumps(state))

            self.assertNotEqual(run('validate', '--mode', 'fail').returncode, 0)
            state['checks'] = [{'name': 'CSV acceptance', 'status': 'passed', 'evidence': 'CLI export fixture matched expected rows'},
                               {'name': 'cleanup', 'status': 'not_applicable', 'reason': 'No cleanup was planned or introduced'}]
            state['debt'] = [{'status': 'accepted', 'item': 'Large export streaming', 'acceptance': 'User accepted local-only limit',
                              'owner': 'Maintainer', 'paydown': 'Stream exports before lifting row limit'}]
            save()
            self.assertEqual(run('validate', '--mode', 'fail').returncode, 0)
            self.assertNotEqual(run('validate', '--stage', 'ship', '--mode', 'fail').returncode, 0)
            state['delivery'] = {'endpoint': 'Local CSV tool', 'status': 'verified', 'evidence': 'Fresh CLI invocation exported expected CSV'}
            save()
            self.assertEqual(run('validate', '--stage', 'ship', '--mode', 'fail').returncode, 0)
            for field, value in [('evidence', ''), ('status', 'deployed')]:
                good = dict(state['delivery'])
                state['delivery'][field] = value
                save()
                self.assertNotEqual(run('validate', '--stage', 'ship', '--mode', 'fail').returncode, 0)
                state['delivery'] = good
            state['checks'][0]['evidence'] = ''
            save()
            self.assertNotEqual(run('validate', '--mode', 'fail').returncode, 0)
            state['checks'][0]['evidence'] = 'Restored current results'
            state['checks'][1]['reason'] = ''
            save()
            self.assertNotEqual(run('validate', '--mode', 'fail').returncode, 0)
            state['checks'][1]['reason'] = 'No cleanup'
            for field, value in [('issues', [{'failure': 'CSV output mismatch'}]), ('blocker', 'Readback unavailable')]:
                state[field] = value
                save()
                self.assertNotEqual(run('validate', '--stage', 'ship', '--mode', 'fail').returncode, 0)
                del state[field]
            state['debt'][0]['owner'] = ''
            save()
            self.assertNotEqual(run('validate', '--mode', 'fail').returncode, 0)
            state['debt'][0]['owner'] = 'Maintainer'
            state['debt'][0]['status'] = 'open'
            save()
            self.assertNotEqual(run('validate', '--mode', 'fail').returncode, 0)
            self.assertEqual(run('validate', '--mode', 'warn').returncode, 0)
            self.assertNotEqual(run('init', '--task', 'Overwrite', '--session', 'abcdef12').returncode, 0)
            self.assertEqual(run('status').returncode, 0)
            self.assertEqual(run('use', '--session', 'abcdef12').returncode, 0)
            self.assertEqual(run('list').returncode, 0)

    def test_legacy_and_invalid_records(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / '.deep-old12345'
            folder.mkdir()
            (folder / 'state.json').write_text(json.dumps({'phase': 'REVIEW'}))
            (folder / 'verification.json').write_text(json.dumps({'requiredGates': ['implemented'], 'gates': {'implemented': True}}))
            (folder / 'debt.md').write_text('## New Debt\n')
            before = {p.name: p.read_bytes() for p in folder.iterdir()}
            def run(*args):
                return subprocess.run([sys.executable, str(HELPER), '--root', temp, 'validate', '--mode', 'fail', *args], capture_output=True, text=True)
            self.assertEqual(run().returncode, 0)
            self.assertNotEqual(run('--stage', 'ship').returncode, 0)
            self.assertEqual(before, {p.name: p.read_bytes() for p in folder.iterdir()})
            (folder / 'state.json').write_text('{')
            result = run()
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('Traceback', result.stderr)


class VerifierExitTests(unittest.TestCase):
    def test_failure_stops_following_check_and_records_truth(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); sentinel = root / 'later'; output = root / 'result.json'
            checks = root / 'checks.json'
            checks.write_text(json.dumps([
                {'name': 'fails', 'argv': [sys.executable, '-c', 'raise SystemExit(7)']},
                {'name': 'later', 'argv': [sys.executable, '-c', f"open({str(sentinel)!r}, 'w').write('ran')"]}
            ]))
            result = subprocess.run([sys.executable, str(HELPER), '--root', temp, 'run-checks', '--checks', str(checks), '--output', str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
            self.assertFalse(sentinel.exists())
            self.assertEqual(json.loads(output.read_text())[0]['status'], 'failed')
            checks.write_text(json.dumps([{'name': 'passes', 'argv': [sys.executable, '-c', 'pass']}]))
            result = subprocess.run([sys.executable, str(HELPER), '--root', temp, 'run-checks', '--checks', str(checks), '--output', str(root/'pass.json')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
