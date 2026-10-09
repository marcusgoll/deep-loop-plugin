import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from admission import digest, initialize, reserve
from native_backend import NativeBackend
from private_controller import TrustedStore
from private_launch import launch_plan

SESSION = '12345678-1234-4234-8234-123456789012'

class NativeBackendTests(unittest.TestCase):
    def setUp(self):
        clock=patch('native_backend.remaining',return_value=3600);clock.start();self.addCleanup(clock.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = TrustedStore(Path(self.temp.name).resolve(), owner_uid=os.getuid())
        self.contract = {'prompt':'literal $(not a shell command)\n', 'executor':{'path':'/pinned/native/codex','sha256':'b'*64}}
        self.contract_digest = digest(self.contract)
        state = reserve(initialize(self.contract_digest), self.contract_digest, run_id=1, run_attempt=1,
                        model_seconds=600, active_seconds=1200)
        self.plan = launch_plan(state, self.contract_digest, run_id=1, run_attempt=1)
        self.backend = NativeBackend(self.store, self.contract_digest)
        self.owner = {'contract_digest':self.contract_digest,'unit':self.plan['unit'],
                      'plan_digest':digest(self.plan),'session_id':None}
        self.store.create('active-owner.json', self.owner)
    def native_observation(self):
        return {'unit':self.plan['unit'],'invocation_id':'a'*32,'active_state':'inactive',
                'cgroup_empty':True,'ownership_verified':True,'execution_finished':True}
    def test_unqualified_submission_creates_no_capture(self):
        with self.assertRaises(ValueError): self.backend.submit(self.plan,self.contract)
        self.assertFalse(list(self.store.root.glob('*.jsonl')))
    def test_pinned_native_argv_and_root_capture_are_single_use(self):
        self.backend.qualified = (digest(self.plan),digest(self.contract))
        calls=[]
        def run(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args,0,stdout='a'*32+'\n')
        with patch('native_backend.subprocess.run',side_effect=run), patch('native_backend.observe_unit',return_value=self.native_observation()):
            self.assertEqual(self.backend.submit(self.plan,self.contract),'a'*32)
        argv=calls[0]
        self.assertIn('--service-type=exec',argv)
        self.assertEqual(argv[argv.index('/pinned/native/codex')+1:][:2],['--no-daemon','exec'])
        self.assertIn('--skip-git-repo-check',argv)
        self.assertNotIn(self.contract['prompt'],argv)
        self.assertEqual((self.store.root/(self.plan['unit']+'.prompt')).read_text(),self.contract['prompt'])
        self.assertEqual((self.store.root/(self.plan['unit']+'.jsonl')).stat().st_mode&0o777,0o600)
        with self.assertRaises(ValueError): self.backend.submit(self.plan,self.contract)
    def test_uncertain_submission_keeps_capture_and_consumes_qualification(self):
        self.backend.qualified=(digest(self.plan),digest(self.contract))
        with patch('native_backend.subprocess.run',side_effect=OSError('response lost')):
            with self.assertRaises(OSError): self.backend.submit(self.plan,self.contract)
        self.assertTrue((self.store.root/(self.plan['unit']+'.jsonl')).exists())
        with self.assertRaises(ValueError): self.backend.submit(self.plan,self.contract)
    def test_stopped_owned_native_capture_establishes_session(self):
        self.backend._raw(self.plan['unit']+'.jsonl', ('{"type":"thread.started","thread_id":"'+SESSION+'"}\n').encode())
        with patch('native_backend.observe_unit',return_value=self.native_observation()):
            observed,session=self.backend.observe(self.plan['unit'],'a'*32)
        self.assertEqual(session,SESSION)
        self.assertTrue(observed['cgroup_empty'])
    def test_recovery_adopts_only_matching_existing_native_unit(self):
        for suffix in ('.prompt', '.jsonl', '.stderr'):
            self.backend._raw(self.plan['unit']+suffix,b'')
        output = 'Description=Deep Loop plan '+digest(self.plan)+'\nInvocationID='+'a'*32+'\n'
        with patch('native_backend.subprocess.run',return_value=subprocess.CompletedProcess([],0,stdout=output)) as run, patch('native_backend.observe_unit',return_value=self.native_observation()):
            self.assertEqual(self.backend.recover_invocation(self.plan,self.contract,self.owner),'a'*32)
            self.assertEqual(run.call_args.args[0][0],'/usr/bin/systemctl')
        with patch('native_backend.subprocess.run',return_value=subprocess.CompletedProcess([],0,stdout=output.replace(digest(self.plan),'b'*64))):
            with self.assertRaises(ValueError): self.backend.recover_invocation(self.plan,self.contract,self.owner)
    def test_short_window_blocks_native_dispatch_after_preparation(self):
        self.backend.qualified=(digest(self.plan),digest(self.contract))
        with patch('native_backend.remaining',return_value=1199),patch('native_backend.subprocess.run') as run:
            with self.assertRaises(ValueError):self.backend.submit(self.plan,self.contract)
            run.assert_not_called()
        self.assertTrue((self.store.root/(self.plan['unit']+'.jsonl')).exists())

    def test_missing_capture_blocks_recovery_without_submission(self):
        with patch('native_backend.subprocess.run') as run:
            with self.assertRaises(FileNotFoundError): self.backend.recover_invocation(self.plan,self.contract,self.owner)
            run.assert_not_called()

    def test_active_capture_is_not_finalized(self):
        observation=dict(self.native_observation(),active_state='active',cgroup_empty=False,execution_finished=False)
        with patch('native_backend.observe_unit',return_value=observation):
            self.assertIsNone(self.backend.observe(self.plan['unit'],'a'*32)[1])

if __name__ == '__main__': unittest.main()
