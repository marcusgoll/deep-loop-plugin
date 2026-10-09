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


class RegisteredUIExecutionTests(unittest.TestCase):
    def test_registered_ui_requires_binding_but_small_edit_keeps_manual_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);request=root/'request.json'
            request.write_text(json.dumps({'surface':'ui','changes':['hierarchy'],'mode':'EVOLVE','platform':'web'}))
            def run(*args):
                return subprocess.run([sys.executable,str(HELPER),'--root',temp,*args],capture_output=True,text=True)
            result=run('init','--task','UI acceptance','--session','uicase01','--ui-request',str(request))
            self.assertEqual(result.returncode,0,result.stderr)
            folder=root/'.deep-uicase01';path=folder/'state.json';state=json.loads(path.read_text())
            # Preserve the installed schema-2 manual path; schema-4 gates have separate controls.
            state['schemaVersion']=2
            state['checks']=[{'name':'mechanism suite','status':'passed','evidence':'68 package tests passed'}]
            state['delivery']={'endpoint':'local UI','status':'verified','evidence':'claimed'}
            path.write_text(json.dumps(state))
            for stage in ('review','ship'):
                result=run('validate','--stage',stage)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('requires an approved',result.stdout)
            request.write_text(json.dumps({'surface':'ui','changes':['spacing'],'visually_specified':True,'mode':'PATCH'}))
            state['uiEvidence']['request']['sha256']=__import__('hashlib').sha256(request.read_bytes()).hexdigest()
            path.write_text(json.dumps(state))
            self.assertEqual(run('validate','--stage','ship').returncode,0)
            request.write_text('{}')
            self.assertNotEqual(run('validate','--stage','review').returncode,0)

    def test_bound_ui_arguments_are_not_optional_receipt_labels(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);checks=root/'checks.json';out=root/'out.json'
            checks.write_text(json.dumps([{'name':'ordinary','argv':[sys.executable,'-c','pass']}]))
            result=subprocess.run([sys.executable,str(HELPER),'--root',temp,'run-checks','--checks',str(checks),
                                   '--output',str(out),'--goal-id','claimed-task'],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse(out.exists())

if __name__ == '__main__': unittest.main()
