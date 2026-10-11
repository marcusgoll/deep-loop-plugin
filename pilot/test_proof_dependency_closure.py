import hashlib
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

class IsolatedDependencyClosureTests(unittest.TestCase):
    def test_copied_controller_bundle_closes_files_without_helper_imports(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name).resolve();bundle=root/'pilot';bundle.mkdir()
            for source in Path(__file__).parent.glob('*.py'):
                if not source.name.startswith('test_'):shutil.copy2(source,bundle/source.name)
            path=root/'proof';path.write_bytes(b'approved proof');info=path.stat()
            cut={str(path):{'physical_path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                           'size':info.st_size,'device':info.st_dev,'inode':info.st_ino,'mode':stat.S_IMODE(info.st_mode)}}
            program='''import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from private_controller import PrivateController
cut=json.loads(sys.argv[2]);controller=PrivateController.__new__(PrivateController)
assert 'proof_binding' not in sys.modules
assert controller._workflow_reobserve_proof_files(cut)==cut
Path(next(iter(cut))).write_bytes(b'changed proof')
try:controller._workflow_reobserve_proof_files(cut)
except ValueError:pass
else:raise AssertionError('Changed file accepted')
assert 'proof_binding' not in sys.modules
'''
            result=subprocess.run([sys.executable,'-I','-S','-B','-c',program,str(bundle),json.dumps(cut)],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
