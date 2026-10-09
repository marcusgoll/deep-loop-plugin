"""Recoverable closeout checks against disposable files and real Git history."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HELPER = Path(__file__).with_name('deep_loop.py')


class CloseoutChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'repo'
        self.root.mkdir()
        self.session = self.root / '.deep-archive1'
        self.archive = self.base / 'archive'
        self.cli('init', '--session', 'archive1', '--task', 'Saved export')
        self.state = {'schemaVersion': 2, 'sessionId': 'archive1', 'task': 'Saved export',
                      'active': False, 'complete': False, 'phase': 'SHIP',
                      'checks': [{'name': 'Export', 'status': 'passed', 'evidence': 'Fixture matches'}],
                      'delivery': {'endpoint': 'Saved export', 'status': 'verified', 'evidence': 'Read back'}}
        self.save_state()
        (self.session / 'evidence.txt').write_text('ignored evidence', encoding='utf-8')

    def save_state(self):
        (self.session / 'state.json').write_text(json.dumps(self.state), encoding='utf-8')

    def cli(self, *args, ok=True):
        result = subprocess.run([sys.executable, str(HELPER), '--root', str(self.root), *args],
                                capture_output=True, text=True)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def git(self, *args):
        result = subprocess.run(['git', '-C', str(self.root), *args], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def preserve(self):
        return self.cli('preserve', '--session', 'archive1', '--destination', str(self.archive))

    def test_preserve_retire_finalize_and_repeat(self):
        original = (self.session / 'state.json').read_bytes()
        self.preserve()
        self.assertEqual((self.archive / 'snapshot/state.json').read_bytes(), original)
        self.assertTrue(self.session.exists())
        self.cli('validate', '--path', str(self.archive / 'checkpoint'), '--stage', 'ship', ok=False)
        self.cli('retire-checkpoint', '--archive', str(self.archive))
        self.cli('retire-checkpoint', '--archive', str(self.archive))
        self.assertFalse(self.session.exists())
        self.assertFalse((self.root / '.deep-current.json').exists())
        evidence = self.base / 'readback.txt'
        evidence.write_text('Fixture checkpoint removed; refs/worktree not applicable', encoding='utf-8')
        self.cli('finalize-archive', '--archive', str(self.archive), '--evidence', str(evidence))
        self.cli('finalize-archive', '--archive', str(self.archive), '--evidence', str(evidence))
        state = json.loads((self.archive / 'checkpoint/state.json').read_text())
        self.assertTrue(state['complete'])
        self.cli('validate', '--path', str(self.archive / 'checkpoint'), '--stage', 'ship')
        self.cli('verify-archive', '--archive', str(self.archive))
        self.assertEqual((self.archive / 'snapshot/state.json').read_bytes(), original)
        (self.archive / 'final.json').unlink()
        self.cli('verify-archive', '--archive', str(self.archive), ok=False)
        self.cli('finalize-archive', '--archive', str(self.archive), '--evidence', str(evidence))
        (self.archive / 'closeout-evidence').write_text('corrupt')
        self.cli('verify-archive', '--archive', str(self.archive), ok=False)

    def test_planned_closeout_waits_until_preserved_delivery(self):
        contract_path = self.base / 'contract.json'
        contract = {'name': 'Archive recovery', 'scope': 'Saved export', 'status': 'NOT_RUN',
                    'requirements': [{'id': 'R1', 'outcome': 'Archive recovers', 'invariant': 'Bytes match', 'priority': 'blocking'}],
                    'verifiers': [{'id': 'V1', 'covers': ['R1'], 'class': 'deterministic', 'status': 'implemented',
                                   'expected': 'Archive bytes match', 'gate': 'blocking'}], 'gaps': [],
                    'ship_gate': dict.fromkeys(('require_all_blocking_verifiers_pass', 'require_zero_blocking_gaps',
                                               'require_human_approvals_recorded', 'require_evidence_matches_revision'), True)}
        contract_path.write_text(json.dumps(contract), encoding='utf-8')
        self.cli('bind-contract', '--session', 'archive1', '--contract', str(contract_path), '--endpoint', 'Saved export')
        self.state = json.loads((self.session / 'state.json').read_text())
        self.state.update(active=False, complete=False, phase='SHIP')
        self.state['checks'] = [{'name': 'Export', 'status': 'passed', 'evidence': 'Fixture matches'},
                                {'name': 'Endpoint', 'stage': 'ship', 'status': 'pending'},
                                {'name': 'Recovery', 'verifierId': 'V1', 'stage': 'closeout', 'status': 'pending'}]
        self.state['tasks'] = [{'id': 'retire', 'title': 'Retirement readback', 'kind': 'task',
                                'stage': 'closeout', 'status': 'pending', 'acceptance': 'Source retired, archive intact'}]
        self.state['delivery'].update(status='verified', evidence='Read back')
        self.save_state()
        self.cli('validate', '--session', 'archive1', '--stage', 'review')
        self.cli('preserve', '--session', 'archive1', '--destination', str(self.archive), ok=False)
        self.assertFalse(self.archive.exists())
        self.state['checks'][1].update(status='passed', evidence='Current endpoint')
        self.save_state()
        # Endpoint substitution must still block preservation's private delivery gate.
        self.state['delivery']['endpoint'] = 'Another endpoint'
        self.save_state()
        self.cli('preserve', '--session', 'archive1', '--destination', str(self.archive), ok=False)
        self.state['delivery']['endpoint'] = 'Saved export'
        self.save_state()
        self.preserve()
        preserved = json.loads((self.archive / 'checkpoint/state.json').read_text())
        self.assertEqual(preserved['checks'][-1]['stage'], 'closeout')
        self.cli('validate', '--path', str(self.archive / 'checkpoint'), '--stage', 'review')
        self.cli('validate', '--path', str(self.archive / 'checkpoint'), '--stage', 'ship', ok=False)
        self.cli('retire-checkpoint', '--archive', str(self.archive))
        evidence = self.base / 'readback.txt'
        evidence.write_text('Source absent; preserved archive bytes verified', encoding='utf-8')
        self.cli('verify-archive', '--archive', str(self.archive))
        self.assertFalse(self.session.exists())
        self.cli('finalize-archive', '--archive', str(self.archive), '--evidence', str(evidence), ok=False)
        path = self.archive / 'checkpoint/state.json'
        working = json.loads(path.read_text())
        self.assertFalse(working['complete'])
        working['checks'][2].update(status='passed', evidence=str(evidence))
        working['tasks'][0].update(status='done', evidence=str(evidence))
        path.write_text(json.dumps(working), encoding='utf-8')
        self.cli('finalize-archive', '--archive', str(self.archive), '--evidence', str(evidence))
        self.cli('validate', '--path', str(self.archive / 'checkpoint'), '--stage', 'ship')

    def test_existing_ui_archive_cannot_authorize_retirement(self):
        self.preserve()
        working = self.archive / 'checkpoint/state.json'
        state = json.loads(working.read_text())
        state['uiEvidence'] = {'request': {'path': str(self.session / 'request.json'), 'sha256': 'a' * 64}}
        working.write_text(json.dumps(state))
        before = (self.session / 'state.json').read_bytes()
        result = self.cli('verify-archive', '--archive', str(self.archive), ok=False)
        self.assertIn('portable UI bindings', result.stderr)
        self.cli('retire-checkpoint', '--archive', str(self.archive), ok=False)
        self.assertTrue(self.session.exists())
        self.assertEqual((self.session / 'state.json').read_bytes(), before)
        self.assertTrue((self.root / '.deep-current.json').exists())

    def test_drift_corruption_and_switched_pointer_preserve_work(self):
        self.preserve()
        (self.session / 'new.txt').write_text('another writer', encoding='utf-8')
        self.cli('retire-checkpoint', '--archive', str(self.archive), ok=False)
        self.assertTrue(self.session.exists())
        (self.session / 'new.txt').unlink()
        other = self.root / '.deep-other123'
        other.mkdir()
        pointer = {'sessionId': 'other123', 'path': str(other)}
        (self.root / '.deep-current.json').write_text(json.dumps(pointer))
        self.cli('retire-checkpoint', '--archive', str(self.archive))
        self.assertEqual(json.loads((self.root / '.deep-current.json').read_text()), pointer)
        (self.archive / 'snapshot/evidence.txt').write_text('corrupt')
        self.cli('verify-archive', '--archive', str(self.archive), ok=False)

    def test_unshipped_active_and_inside_destination_rejected(self):
        self.state['active'] = True
        self.save_state()
        self.cli('preserve', '--session', 'archive1', '--destination', str(self.archive), ok=False)
        self.state['active'] = False
        self.state['delivery']['status'] = 'pending'
        self.save_state()
        self.cli('preserve', '--session', 'archive1', '--destination', str(self.archive), ok=False)
        self.state['delivery']['status'] = 'verified'
        self.save_state()
        self.cli('preserve', '--session', 'archive1', '--destination', str(self.root / 'archive'), ok=False)
        self.assertFalse(self.archive.exists())

    def test_interruption_lock_and_manifest_identity(self):
        self.preserve()
        (self.root / '.deep-current.lock').write_text('another writer')
        self.cli('retire-checkpoint', '--archive', str(self.archive), ok=False)
        self.assertTrue(self.session.exists())
        (self.root / '.deep-current.lock').unlink()
        manifest_path = self.archive / 'archive.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['sessionId'] = '../escape'
        manifest_path.write_text(json.dumps(manifest))
        self.cli('retire-checkpoint', '--archive', str(self.archive), ok=False)
        self.assertTrue(self.session.exists())

    def test_partial_archive_and_repeat_evidence_drift(self):
        evidence = self.base / 'evidence.txt'
        evidence.write_text('original')
        args = ('preserve', '--session', 'archive1', '--destination', str(self.archive), '--include', str(evidence))
        self.cli(*args)
        self.cli(*args)
        evidence.write_text('changed')
        self.cli(*args, ok=False)
        (self.archive / 'checkpoint/state.json').unlink()
        self.cli('retire-checkpoint', '--archive', str(self.archive), ok=False)
        self.assertTrue(self.session.exists())

    def test_recursive_include_rejected(self):
        self.cli('preserve', '--session', 'archive1', '--destination', str(self.archive),
                 '--include', str(self.base), ok=False)
        self.assertFalse(self.archive.exists())

    def test_bound_contract_survives_original_removal(self):
        contract_path = self.base / 'contract.json'
        contract = {'name': 'Export', 'scope': 'Saved export', 'status': 'NOT_RUN',
                    'requirements': [{'id': 'R1', 'outcome': 'Exports rows', 'invariant': 'Rows match', 'priority': 'blocking'}],
                    'verifiers': [{'id': 'V1', 'covers': ['R1'], 'class': 'deterministic', 'status': 'implemented',
                                   'expected': 'Rows equal fixture', 'gate': 'blocking'}], 'gaps': [],
                    'ship_gate': dict.fromkeys(('require_all_blocking_verifiers_pass', 'require_zero_blocking_gaps',
                                               'require_human_approvals_recorded', 'require_evidence_matches_revision'), True)}
        contract_path.write_text(json.dumps(contract))
        self.cli('bind-contract', '--session', 'archive1', '--contract', str(contract_path), '--endpoint', 'Saved export')
        self.state = json.loads((self.session / 'state.json').read_text())
        self.state.update(active=False, complete=False, phase='SHIP')
        self.state['checks'] = [{'name': 'Rows', 'verifierId': 'V1', 'status': 'passed', 'evidence': 'Rows match fixture'}]
        self.state['delivery'].update(status='verified', evidence='Read back')
        self.save_state()
        self.preserve()
        self.cli('retire-checkpoint', '--archive', str(self.archive))
        contract_path.unlink()
        evidence = self.base / 'readback.txt'
        evidence.write_text('Selected checkpoint retired')
        self.cli('finalize-archive', '--archive', str(self.archive), '--evidence', str(evidence))
        self.cli('validate', '--path', str(self.archive / 'checkpoint'), '--stage', 'ship')

    def test_junction_evidence_rejected(self):
        if sys.platform != 'win32':
            self.skipTest('Windows junction safety')
        linked = self.session / 'linked'
        outside = self.base / 'outside'
        outside.mkdir()
        result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(linked), str(outside)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        try:
            self.cli('preserve', '--session', 'archive1', '--destination', str(self.archive), ok=False)
            self.assertFalse(self.archive.exists())
        finally:
            linked.rmdir()

    def test_dirty_shared_checkout_checkpoint_only(self):
        self.git('init', '-b', 'main')
        (self.root / 'another-writer.txt').write_text('retain')
        self.cli('preserve', '--session', 'archive1', '--destination', str(self.archive), ok=False)
        self.cli('preserve', '--session', 'archive1', '--destination', str(self.archive), '--checkpoint-only')
        self.assertIn('no Git history preserved', self.cli('verify-archive', '--archive', str(self.archive)).stdout)
        self.cli('retire-checkpoint', '--archive', str(self.archive))
        self.assertEqual((self.root / 'another-writer.txt').read_text(), 'retain')
        self.assertIsNone(json.loads((self.archive / 'archive.json').read_text())['gitHead'])

    def test_real_squash_history_restore_and_extra_evidence(self):
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        (self.root / 'product.txt').write_text('base')
        self.git('add', 'product.txt')
        self.git('commit', '-m', 'base')
        self.git('switch', '-c', 'task')
        (self.root / 'product.txt').write_text('shipped')
        self.git('commit', '-am', 'task')
        head = self.git('rev-parse', 'HEAD')
        self.git('switch', 'main')
        self.git('merge', '--squash', 'task')
        self.git('commit', '-m', 'squashed shipment')
        self.git('switch', 'task')
        self.cli('exclude')
        extra = self.root / 'ignored-output.bin'
        extra.write_bytes(b'recovery proof')
        with (self.root / '.git/info/exclude').open('a') as stream:
            stream.write('\nignored-output.bin\n')
        self.cli('preserve', '--session', 'archive1', '--destination', str(self.archive),
                 '--include', str(extra))
        self.git('commit', '--allow-empty', '-m', 'new source history')
        self.cli('preserve', '--session', 'archive1', '--destination', str(self.archive),
                 '--include', str(extra), ok=False)
        mismatch = subprocess.run(['git', '-C', str(self.root), 'update-ref', '-d', 'refs/heads/task', head],
                                  capture_output=True, text=True)
        self.assertNotEqual(mismatch.returncode, 0)
        self.git('reset', '--hard', head)
        self.cli('retire-checkpoint', '--archive', str(self.archive))
        self.git('switch', 'main')
        self.git('update-ref', '-d', 'refs/heads/task', head)
        self.cli('verify-archive', '--archive', str(self.archive))
        manifest = json.loads((self.archive / 'archive.json').read_text())
        self.assertEqual(manifest['gitHead'], head)
        self.assertEqual((self.archive / 'includes/0/ignored-output.bin').read_bytes(), b'recovery proof')


if __name__ == '__main__':
    unittest.main()
