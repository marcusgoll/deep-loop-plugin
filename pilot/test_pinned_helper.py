import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from pinned_helper import PinnedHelper,BoundPinnedHelper


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

    def bound(self):
        from admission import digest
        from private_controller import TrustedStore
        control=self.root/'control';control.mkdir(mode=0o700)
        store=TrustedStore(control,owner_uid=os.getuid())
        key=digest({'fixture':'bound helper'})
        binding={'approval_ref':'fixture binding'}
        store.create(key+'.workflow.json',binding)
        record={'contract_digest':key,'binding_digest':digest(binding),'approval_ref':binding['approval_ref'],'helper':self.config}
        intent={'contract_digest':key,'binding_digest':digest(binding),'approval_ref':binding['approval_ref'],'helper_digest':digest(record),'journal_revision':'a'*40}
        store.create(key+'.workflow-helper-intent.json',intent)
        store.create(key+'.workflow-helper-complete.json',{**intent,'activated':False})
        return BoundPinnedHelper(store,key),store,key,record

    def test_protected_binding_reloads_authority_and_source_on_each_call(self):
        helper,store,key,record=self.bound()
        store.create(key+'.workflow-helper.json',record)
        self.assertEqual(helper.task_records({})[0],{})
        store.remove(key+'.workflow-helper.json')
        store.create(key+'.workflow-helper.json',{**record,'binding_digest':'0'*64})
        with self.assertRaisesRegex(ValueError,'authority changed'):helper.task_records({})
        store.remove(key+'.workflow-helper.json');store.create(key+'.workflow-helper.json',record)
        (self.root/'skills/deep-loop/scripts/deep_loop.py').write_text('drift')
        with self.assertRaisesRegex(ValueError,'source drift'):helper.task_records({})

    def test_protected_helper_construction_is_lazy_but_use_requires_record(self):
        helper,store,key,record=self.bound()
        with self.assertRaises(FileNotFoundError):helper.task_records({})

    def test_partial_or_changed_completion_blocks_helper_use(self):
        helper,store,key,record=self.bound();store.create(key+'.workflow-helper.json',record)
        complete=store.read(key+'.workflow-helper-complete.json');store.remove(key+'.workflow-helper-complete.json')
        with self.assertRaises(FileNotFoundError):helper.task_records({})
        store.create(key+'.workflow-helper-complete.json',{**complete,'activated':True})
        with self.assertRaisesRegex(ValueError,'completion changed'):helper.task_records({})
