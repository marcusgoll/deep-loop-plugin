import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from pinned_helper import PinnedHelper


@unittest.skipUnless(sys.platform=='linux','Production helper requires Linux runtime')
class PinnedHelperTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.files={}
        for name,text in [('skills/deep-loop/scripts/deep_loop.py',"import os\ndef task_records(state):return [state,os.environ['DEEP_LOOP_SKILLS_ROOT'],'OPENAI_API_KEY' in os.environ]\n"),
                          ('skills/deep-loop/scripts/proof_binding.py',''),
                          ('skills/verification-contract/scripts/validate_contract.py','')]:
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
            self.files[name]=hashlib.sha256(p.read_bytes()).hexdigest()
        for directory in self.root.rglob('*'):
            if directory.is_dir():directory.chmod(0o755)
            else:directory.chmod(0o644)
        python=Path('/usr/bin/python3').resolve()
        self.config={'root':str(self.root),'files':self.files,'python':{'path':str(python),'sha256':hashlib.sha256(python.read_bytes()).hexdigest()}}
        self.helper=PinnedHelper(self.config,owner_uid=os.getuid())
    def test_isolated_helper_ignores_inherited_import_and_skill_overrides(self):
        with patch.dict(os.environ,{'PYTHONPATH':'/evil','DEEP_LOOP_SKILLS_ROOT':'/evil','OPENAI_API_KEY':'fixture-never-forward'}):
            self.assertEqual(self.helper.task_records({'fixture':True}),[{'fixture':True},str(self.root/'skills'),False])
    def test_drift_unpinned_dependency_and_oversize_request_fail_closed(self):
        p=self.root/'skills/deep-loop/scripts/deep_loop.py';p.write_text('drift')
        with self.assertRaisesRegex(ValueError,'source drift'):self.helper.task_queue({})
        self.files[str(p.relative_to(self.root))]=hashlib.sha256(p.read_bytes()).hexdigest()
        extra=p.with_name('extra.py');extra.write_text('')
        with self.assertRaisesRegex(ValueError,'Unpinned'):self.helper.task_queue({})
        extra.unlink()
        with self.assertRaisesRegex(ValueError,'request exceeds'):self.helper.task_records({'large':'x'*524288})

    def test_excessive_helper_output_fails_with_bounded_capture(self):
        p=self.root/'skills/deep-loop/scripts/deep_loop.py'
        p.write_text("def task_records(state):return 'x'*2097152\n")
        self.files[str(p.relative_to(self.root))]=hashlib.sha256(p.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError,'unavailable or failed'):
            self.helper.task_records({})

    def test_source_size_and_inventory_depth_are_bounded(self):
        p=self.root/'skills/deep-loop/scripts/deep_loop.py'
        original=p.read_bytes();p.write_bytes(b'x'*1048577)
        with self.assertRaisesRegex(ValueError,'file exceeds bound'):self.helper.task_records({})
        p.write_bytes(original)
        (p.parent/'a/b/c/d/e').mkdir(parents=True)
        for directory in p.parent.rglob('*'):
            if directory.is_dir():directory.chmod(0o755)
        with self.assertRaisesRegex(ValueError,'depth exceeds bound'):self.helper.task_records({})

    def test_inventory_entries_and_alternate_imports_are_bounded(self):
        folder=self.root/'skills/deep-loop/scripts'
        for extension in ('.pyc','.so','.pyd','.pth'):
            p=folder/('extra'+extension);p.write_bytes(b'')
            with self.assertRaisesRegex(ValueError,'import artifact'):self.helper.task_records({})
            p.unlink()
        p=folder/'link';p.symlink_to(folder/'deep_loop.py')
        with self.assertRaisesRegex(ValueError,'symlink'):self.helper.task_records({})
        p.unlink()
        for number in range(2049):(folder/str(number)).touch()
        with self.assertRaisesRegex(ValueError,'inventory exceeds bound'):self.helper.task_records({})

    def test_child_allocation_fails_closed(self):
        p=self.root/'skills/deep-loop/scripts/deep_loop.py'
        p.write_text("def task_records(state):return bytearray(1073741824)\n")
        self.files[str(p.relative_to(self.root))]=hashlib.sha256(p.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError,'unavailable or failed'):self.helper.task_records({})
