import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from promote_controller import MODULES, plan
from test_workflow_delivery_contract import delivery


class ControllerBundleTests(unittest.TestCase):
    def test_declared_bundle_closes_all_local_imports_including_lazy_paths(self):
        root=Path(__file__).resolve().parent
        local={p.stem for p in root.glob('*.py')}
        bundled={Path(name).stem for name in MODULES}
        for name in MODULES:
            for node in ast.walk(ast.parse((root/name).read_text())):
                modules=([node.module] if isinstance(node,ast.ImportFrom) else
                         [item.name for item in node.names] if isinstance(node,ast.Import) else [])
                for module in modules:
                    if module and module.split('.')[0] in local:
                        self.assertIn(module.split('.')[0],bundled,(name,module))
    def test_exact_planned_bundle_runs_new_capability_without_checkout_imports(self):
        root=Path(__file__).resolve().parent;manifest=plan()
        with tempfile.TemporaryDirectory() as temporary:
            target=Path(temporary)
            for name,expected in manifest['modules'].items():
                data=(root/name).read_bytes();self.assertEqual(hashlib.sha256(data).hexdigest(),expected)
                (target/name).write_bytes(data)
            code="""import json,sys
sys.path.insert(0,sys.argv[1])
from workflow_gate import WorkflowGate
from workflow_delivery_contract import validate_workflow_delivery
capability=json.load(sys.stdin)
validate_workflow_delivery(capability,'b'*64)
print('isolated-capability-pass')
"""
            result=subprocess.run([sys.executable,'-I','-B','-c',code,str(target)],
                                  input=json.dumps(delivery('b'*64)),text=True,capture_output=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout.strip(),'isolated-capability-pass')

if __name__=='__main__':unittest.main()
