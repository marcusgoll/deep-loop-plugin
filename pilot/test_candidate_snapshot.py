import copy
import os
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from candidate_snapshot import capture_candidate, require_candidate_snapshot


class CandidateSnapshotTests(unittest.TestCase):
    def setUp(self):
        if sys.platform != 'linux':
            # Deterministic inventory tests only: Mac has no native fdinfo.
            mount = patch('candidate_snapshot._mount_id', return_value=1)
            mount.start()
            self.addCleanup(mount.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.policy = {'schema': 1, 'candidate_root': str(self.root),
                       'scope': 'entire_candidate', 'allowed_uids': [os.getuid()], 'max_entries': 100,
                       'max_file_bytes': 1024, 'max_total_bytes': 4096, 'max_depth': 5}
        (self.root / 'source.py').write_text('first')

    def test_complete_inventory_includes_hidden_files_and_empty_directories(self):
        (self.root / '.hidden').write_text('secret')
        (self.root / 'empty').mkdir()
        snapshot = capture_candidate(self.policy)
        self.assertEqual({e['path'] for e in snapshot['manifest']['entries']},
                         {'', '.hidden', 'empty', 'source.py'})
        self.assertEqual(require_candidate_snapshot(self.policy, snapshot), snapshot)

    def test_edit_add_delete_rename_and_mode_invalidate_snapshot(self):
        for operation in ('edit', 'add', 'delete', 'rename', 'mode'):
            with self.subTest(operation=operation):
                source = self.root / 'source.py'
                source.write_text('first')
                source.chmod(0o600)
                snapshot = capture_candidate(self.policy)
                if operation == 'edit': source.write_text('other')
                elif operation == 'add': (self.root / 'new').write_text('new')
                elif operation == 'delete': source.unlink()
                elif operation == 'rename': source.rename(self.root / 'renamed')
                else: source.chmod(0o700)
                with self.assertRaises(ValueError):
                    require_candidate_snapshot(self.policy, snapshot)
                for path in self.root.iterdir(): path.unlink()

    def test_symlink_hardlink_and_special_file_fail_closed(self):
        for kind in ('symlink', 'hardlink', 'fifo'):
            path = self.root / 'unsupported'
            if kind == 'symlink': path.symlink_to('/etc/passwd')
            elif kind == 'hardlink': os.link(self.root / 'source.py', path)
            else: os.mkfifo(path)
            with self.assertRaisesRegex(ValueError, 'unsupported'):
                capture_candidate(self.policy)
            path.unlink()

    def test_byte_entry_and_depth_bounds(self):
        for key, value in (('max_file_bytes', 1), ('max_total_bytes', 1), ('max_entries', 1)):
            with self.assertRaisesRegex(ValueError, 'limit'):
                capture_candidate({**self.policy, key: value})
        (self.root / 'a' / 'b').mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, 'depth'):
            capture_candidate({**self.policy, 'max_depth': 1})

    def test_policy_drift_and_substituted_snapshot_rejected(self):
        snapshot = capture_candidate(self.policy)
        with self.assertRaises(ValueError):
            require_candidate_snapshot({**self.policy, 'max_entries': 99}, snapshot)
        modified = copy.deepcopy(snapshot)
        modified['manifest']['entries'] = []
        with self.assertRaises(ValueError): require_candidate_snapshot(self.policy, modified)

    def test_unsupported_scope_exclusions_versions_and_limits(self):
        for changes in ({'scope': 'subset'}, {'exclude': ['.git']},
                        {'schema': True}, {'max_entries': True}, {'max_depth': 129}):
            with self.assertRaises(ValueError):
                capture_candidate({**self.policy, **changes})

    def test_mount_identity_missing_or_different_rejected(self):
        with patch('candidate_snapshot._mount_id', side_effect=ValueError('unavailable')):
            with self.assertRaises(ValueError): capture_candidate(self.policy)
        with patch('candidate_snapshot._mount_id', side_effect=[1, 1, 2]):
            with self.assertRaisesRegex(ValueError, 'mount boundary'):
                capture_candidate(self.policy)

    def test_unapproved_owner_rejected(self):
        with self.assertRaisesRegex(ValueError, 'owner'):
            capture_candidate({**self.policy, 'allowed_uids': [os.getuid() + 1]})

    def test_root_alias_rejected(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Canonical'):
            capture_candidate({**self.policy, 'candidate_root': str(alias)})

    def test_mutation_during_file_read_rejected(self):
        original = os.read
        changed = False
        def mutating_read(fd, size):
            nonlocal changed
            data = original(fd, size)
            if data and not changed:
                changed = True
                (self.root / 'source.py').write_text('different')
            return data
        with patch('candidate_snapshot.os.read', side_effect=mutating_read):
            with self.assertRaisesRegex(ValueError, 'changed'):
                capture_candidate(self.policy)


if __name__ == '__main__': unittest.main()
