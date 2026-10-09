import tempfile
import os
from pathlib import Path
import unittest
from qualification_environment import configuration_paths,require_absent,inspect_candidate

class EnvironmentTests(unittest.TestCase):
    def test_dangling_configuration_symlink_and_real_config_block(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'config.toml'
            require_absent([path])
            path.symlink_to(Path(temporary)/'missing')
            with self.assertRaises(ValueError):require_absent([path])
            path.unlink();path.write_text('profile override')
            with self.assertRaises(ValueError):require_absent([path])
    def test_candidate_bound_and_unsafe_links_block(self):
        with tempfile.TemporaryDirectory() as temporary:
            candidate=Path(temporary)
            for i in range(4):(candidate/str(i)).write_text('bounded')
            with self.assertRaises(ValueError):inspect_candidate(candidate,os.getuid(),limit=3)
            inspect_candidate(candidate,os.getuid(),limit=4)
            (candidate/'escape').symlink_to('/tmp/missing')
            with self.assertRaises(ValueError):inspect_candidate(candidate,os.getuid())

    def test_parent_project_and_private_user_rules_in_scope(self):
        paths=configuration_paths('/var/lib/private/candidate/key','/var/lib/private/home')
        self.assertIn(Path('/var/lib/.codex/config.toml'),paths)
        self.assertIn(Path('/var/lib/private/home/.codex/rules'),paths)
        self.assertIn(Path('/etc/codex/requirements.toml'),paths)

if __name__=='__main__':unittest.main()
