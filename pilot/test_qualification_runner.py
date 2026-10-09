import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from admission import digest
from private_controller import TrustedStore
from private_launch import DISABLED_FEATURES
from qualification_runner import produce

class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        (self.root/'home').mkdir(mode=0o700)
        control=self.root/'control';control.mkdir(mode=0o700)
        self.store=TrustedStore(control,owner_uid=os.getuid())
        (control/'credential-stream.lock').touch(mode=0o600)
        self.contract={'fixture':'uncertain no-model probe'};self.key=digest(self.contract)
        self.candidate=self.root/'candidate';self.candidate.mkdir(mode=0o700)
        self.plan={'candidate':str(self.candidate),'properties':{}}
        self.environment={'uid':os.getuid(),'gid':os.getgid()}
        self.commands={'features_command':['pinned','features','list'],'sandbox_command':['pinned','sandbox'],'permission_digest':'a'*64,'strict_command':['pinned','app-server','--strict-config','--listen','stdio://']}
    def test_active_writer_blocks_before_probe(self):
        self.store.create('active-owner.json',{'fixture':True})
        with patch('qualification_runner.subprocess.run') as run:
            with self.assertRaises(ValueError):produce(self.store,self.plan,self.contract)
            run.assert_not_called()
    def test_dangling_owner_and_selector_block_before_probe(self):
        for name in ('active-owner.json','enabled-outcome.json'):
            path=self.store.root/name;path.symlink_to(self.root/'missing')
            try:
                with patch('qualification_runner.subprocess.run') as run:
                    with self.assertRaises(ValueError):produce(self.store,self.plan,self.contract)
                    run.assert_not_called()
            finally:path.unlink()

    def test_uncertain_submission_preserves_intent_and_never_replays(self):
        calls=[]
        def run(command,**kwargs):
            calls.append(command)
            if command[0]=='sudo':
                return SimpleNamespace(stderr='',stdout='\n'.join(name+' stable false' for name in DISABLED_FEATURES))
            raise subprocess.TimeoutExpired(command,5)
        with patch('qualification_runner.ROOT',str(self.root)), \
             patch('qualification_runner.inspect_environment',return_value=self.environment), \
             patch('qualification_runner.qualification_plan',return_value=self.commands), \
             patch('qualification_runner.subprocess.run',side_effect=run), \
             patch('qualification_runner.validate_strict',return_value=[{'fixture':'strict controls passed'}]):
            with self.assertRaises(subprocess.TimeoutExpired):produce(self.store,self.plan,self.contract)
            self.assertEqual(self.store.read(self.key+'.qualification-intent.json')['model_calls'],0)
            self.assertFalse((self.store.root/(self.key+'.qualification.json')).exists())
            before=len(calls)
            with self.assertRaises(ValueError):produce(self.store,self.plan,self.contract)
            self.assertEqual(len(calls),before)
        self.assertEqual(sum(command[0]=='/usr/bin/systemd-run' for command in calls),1)
        launch=next(command for command in calls if command[0]=='/usr/bin/systemd-run')
        self.assertEqual(launch[-3:-1],['/usr/bin/python3','-I'])

if __name__=='__main__':unittest.main()
