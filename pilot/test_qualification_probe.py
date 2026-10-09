import json
import tempfile
import subprocess
import sys
from pathlib import Path
import unittest
from qualification_probe import CHECKS,PROBE,validate_output,wrapper_source,parent_denial
import errno

class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.output={'observations':{name:True for name in CHECKS},'stdin':'literal','uid':978,'cwd':'/candidate','home':'/private'}
    def check(self):return validate_output(json.dumps(self.output),978,'/candidate','/private','literal')
    def test_requires_every_observed_denial_and_identity(self):
        self.assertEqual(self.check(),self.output['observations'])
        for name in CHECKS:
            self.output['observations'][name]=False
            with self.assertRaises(ValueError):self.check()
            self.output['observations'][name]=True
        self.output['observations']['network_denied']=1
        with self.assertRaises(ValueError):self.check()
    def test_wrong_identity_and_missing_checks_block(self):
        self.output['cwd']='/other'
        with self.assertRaises(ValueError):self.check()
        self.output['cwd']='/candidate';del self.output['observations']['network_denied']
        with self.assertRaises(ValueError):self.check()
    def test_isolated_wrapper_rejects_candidate_import_injection(self):
        with tempfile.TemporaryDirectory() as temporary:
            candidate=Path(temporary)
            (candidate/'json.py').write_text("raise RuntimeError('candidate import executed')")
            (candidate/'subprocess.py').write_text("raise RuntimeError('candidate import executed')")
            sentinel=candidate/'sentinel';sentinel.write_text('disposable qualification sentinel')
            wrapper=candidate/'wrapper.py'
            source=wrapper_source([sys.executable,'-I','-c',"print('{}')"],str(sentinel),'escape','proof')
            # This portable test covers import isolation, not Linux proc mechanics.
            if not Path('/proc/self/mem').exists():
                source=source.replace("os.stat('/proc/self/mem')","os.stat(__file__)").replace("os.readlink('/proc/self/ns/pid')","'fixture namespace'")
            wrapper.write_text(source)
            result=subprocess.run([sys.executable,'-I',str(wrapper)],input='literal',cwd=candidate,
                                  capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)['stdin'],'literal')

    def test_missing_parent_path_requires_proven_namespace_and_known_target(self):
        self.assertFalse(parent_denial(errno.ENOENT,False,True))
        self.assertFalse(parent_denial(errno.ENOENT,True,False))
        self.assertTrue(parent_denial(errno.ENOENT,True,True))
        self.assertTrue(parent_denial(errno.EACCES,False,True))
        self.assertFalse(parent_denial(errno.EIO,True,True))

    def test_scripts_compile_without_model_command(self):
        compile(PROBE,'probe','exec')
        compile(wrapper_source(['/pinned','sandbox','--','python','probe'],'/dummy','/escape','/proof'),'wrapper','exec')
        self.assertNotIn('codex exec',PROBE)

if __name__=='__main__':unittest.main()
