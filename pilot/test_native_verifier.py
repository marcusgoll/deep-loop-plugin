import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from admission import digest
from native_verifier import NativeVerifier,launch_plan,NETWORK_SYSCALLS


class VerifierPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.candidate=self.root/'candidate';self.candidate.mkdir()
        self.output=self.candidate/'output';self.output.mkdir()
        self.implementation=self.candidate/'verify.py';self.implementation.write_text('pass')
        self.key='a'*64
        self.owner={'contract_digest':self.key,'unit':'deep-loop-pilot-'+self.key+'-1-1','plan_digest':'b'*64}
        verifier={'id':'V1','gate':'blocking','class':'deterministic','proof':{
            'mode':'bound','argv':['/usr/bin/python3','verify.py'],'working_directory':str(self.candidate),
            'artifacts':[{'path':str(self.output/'result.txt')}]}}
        self.owned={'owner':self.owner,'invocation_id':'c'*32,'journal_revision':'d'*40,
                    'plan':{'contract_digest':self.key,'execution_authorized':False,'parent_accepted':False,
                            'verifier_ids':['V1'],'definitions':[{'verifier':verifier,'identity':{},
                            'input_paths':[str(self.implementation)],'base':str(self.candidate)}]}}
        self.plan=launch_plan(self.owned,self.candidate,0)
    def test_plan_freezes_command_and_readonly_candidate_with_separate_outputs(self):
        self.assertEqual(self.plan['argv'],self.owned['plan']['definitions'][0]['verifier']['proof']['argv'])
        self.assertEqual(self.plan['command'][:4],['/usr/bin/env','-i','PATH=/usr/bin:/bin','HOME=/nonexistent'])
        self.assertEqual(self.plan['read_write_paths'],[str(self.output)])
        self.assertEqual(self.plan['runtime_seconds'],15)
        self.assertNotEqual(self.plan['unit'],self.owner['unit'])
    def test_output_cannot_expose_candidate_root_or_input_tree(self):
        for artifact in (self.candidate/'result.txt',self.implementation.parent/'nested/result.txt'):
            owned=copy.deepcopy(self.owned)
            owned['plan']['definitions'][0]['verifier']['proof']['artifacts']=[{'path':str(artifact)}]
            if artifact.parent.name=='nested':
                owned['plan']['definitions'][0]['input_paths']=[str(artifact.parent/'source.py')]
            with self.assertRaisesRegex(ValueError,'output must not contain'):launch_plan(owned,self.candidate,0)
    def test_human_readback_outside_cwd_and_nul_are_rejected(self):
        for mutation in ('human','readback','cwd','nul'):
            owned=copy.deepcopy(self.owned);row=owned['plan']['definitions'][0]
            if mutation=='human':row['verifier']['class']='human'
            elif mutation=='readback':row['verifier']['proof']['readback']={}
            elif mutation=='cwd':row['verifier']['proof']['working_directory']=str(self.root)
            else:row['verifier']['proof']['argv'].append('x\0y')
            with self.assertRaises(ValueError):launch_plan(owned,self.candidate,0)
    def test_properties_deny_network_privilege_and_control_access(self):
        backend=NativeVerifier(type('Store',(),{'root':self.root/'control'})(),self.key)
        properties=backend._properties(self.plan,'fixture')
        self.assertEqual(properties['User'],'deep-loop-pilot')
        self.assertEqual(properties['ReadOnlyPaths'],str(self.candidate))
        self.assertEqual(properties['ReadWritePaths'],str(self.output))
        self.assertEqual(properties['CapabilityBoundingSet'],'')
        self.assertEqual(properties['NoNewPrivileges'],'yes')
        self.assertEqual(properties['PrivateNetwork'],'yes')
        for syscall in ('io_uring_enter','io_uring_register','io_uring_setup'):
            self.assertIn(syscall,properties['SystemCallFilter'].split())
        self.assertIn(str(backend.store.root),properties['InaccessiblePaths'])
    def backend_fixture(self):
        from unittest.mock import Mock
        backend=NativeVerifier(Mock(root=self.root/'control'),self.key)
        backend._intent=Mock(return_value='fixture')
        backend.store.read.return_value={'plan_digest':digest(self.plan)}
        properties=backend._properties(self.plan,'fixture')
        def run(argv,**kwargs):
            if argv[0]=='/usr/bin/busctl':
                if argv[-1]=='SystemCallFilter':return type('Result',(),{'stdout':json.dumps({'type':'(bas)','data':[False,list(NETWORK_SYSCALLS)]})})()
                if argv[-1]=='SystemCallArchitectures':return type('Result',(),{'stdout':json.dumps({'type':'as','data':['native']})})()
                row=[self.plan['command'][0],self.plan['command'],False,0,0,1,1,999,1,0]
                return type('Result',(),{'stdout':json.dumps({'type':'a(sasbttttuii)','data':[row]})})()
            name=next(a.removeprefix('--property=') for a in argv if a.startswith('--property='))
            value={'InvocationID':'e'*32,'RuntimeMaxUSec':'15s','TimeoutStartUSec':'5s','TimeoutStopUSec':'5s','SystemCallErrorNumber':'1'}.get(name,properties.get(name))
            return type('Result',(),{'stdout':str(value)})()
        native={'execution_finished':True,'cgroup_empty':True,'ownership_verified':True}
        return backend,run,native
    def test_adoption_checks_exact_argv_and_native_limits_without_resubmission(self):
        backend,run,native=self.backend_fixture()
        with patch('native_verifier.subprocess.run',side_effect=run) as process,patch('native_verifier.observe_unit',return_value=native):
            observation=backend.adopt(self.plan)
        self.assertEqual(observation['exit_code'],0)
        self.assertFalse(any(c.args[0][0]=='/usr/bin/systemd-run' for c in process.call_args_list))
        def changed(argv,**kwargs):
            result=run(argv,**kwargs)
            if '--property=RuntimeMaxUSec' in argv:result.stdout='infinity'
            return result
        with patch('native_verifier.subprocess.run',side_effect=changed),patch('native_verifier.observe_unit',return_value=native):
            with self.assertRaisesRegex(ValueError,'deadline drift'):backend.adopt(self.plan)
    def test_substituted_argv_is_rejected_and_changed_generation_is_not_stopped(self):
        backend,run,native=self.backend_fixture()
        def changed(argv,**kwargs):
            result=run(argv,**kwargs)
            if argv[0]=='/usr/bin/busctl' and argv[-1]=='ExecStart':
                data=json.loads(result.stdout);data['data'][0][1]=['/evil'];result.stdout=json.dumps(data)
            return result
        with patch('native_verifier.subprocess.run',side_effect=changed),patch('native_verifier.observe_unit',return_value=native):
            with self.assertRaisesRegex(ValueError,'argv changed'):backend.adopt(self.plan)
        with patch.object(backend,'adopt',return_value={'invocation_id':'f'*32}),patch('native_verifier.subprocess.run') as process:
            with self.assertRaisesRegex(ValueError,'generation changed'):backend.stop(self.plan,'e'*32)
            process.assert_not_called()

    def test_submission_response_loss_is_never_replayed(self):
        from private_controller import TrustedStore
        import os
        control=self.root/'control';control.mkdir(mode=0o700)
        store=TrustedStore(control,owner_uid=os.getuid())
        backend=NativeVerifier(store,self.key)
        with patch.object(backend,'_intent',return_value='fixture'),patch.object(backend,'_qualify'),patch.object(backend,'_dispatch_window'),\
                patch('native_verifier.subprocess.run',side_effect=OSError('lost response')) as process:
            with self.assertRaises(OSError):backend.submit(self.plan)
            with self.assertRaises(FileExistsError):backend.submit(self.plan)
        self.assertEqual(process.call_count,1)
        self.assertEqual(store.read('fixture.submit-intent.json'),{'plan_digest':digest(self.plan)})
    def test_preflight_change_after_intent_prevents_native_submission(self):
        from private_controller import TrustedStore
        import os
        control=self.root/'control';control.mkdir(mode=0o700)
        store=TrustedStore(control,owner_uid=os.getuid());backend=NativeVerifier(store,self.key)
        with patch.object(backend,'_intent',return_value='fixture'),\
                patch.object(backend,'_qualify',side_effect=[None,ValueError('inputs changed')]),\
                patch('native_verifier.subprocess.run') as process:
            with self.assertRaisesRegex(ValueError,'inputs changed'):backend.submit(self.plan)
            process.assert_not_called()
        self.assertEqual(store.read('fixture.submit-intent.json'),{'plan_digest':digest(self.plan)})

    def test_hard_linked_bound_input_is_rejected(self):
        import os
        account=type('Account',(),{'pw_uid':os.getuid(),'pw_gid':os.getgid()})()
        self.implementation.chmod(0o600)
        backend=NativeVerifier(None,self.key)
        backend._candidate_input(self.implementation,account)
        os.link(self.implementation,self.output/'writable-alias.py')
        with self.assertRaisesRegex(ValueError,'single-link'):
            backend._candidate_input(self.implementation,account)

    def test_late_window_expiry_preserves_intent_without_dispatch(self):
        from private_controller import TrustedStore
        import os
        control=self.root/'control';control.mkdir(mode=0o700)
        store=TrustedStore(control,owner_uid=os.getuid());backend=NativeVerifier(store,self.key)
        with patch.object(backend,'_intent',return_value='fixture'),patch.object(backend,'_qualify'), \
                patch('native_verifier.require_active'),patch('native_verifier.remaining',return_value=29), \
                patch('native_verifier.subprocess.run') as process:
            with self.assertRaisesRegex(ValueError,'immutable verification window'):backend.submit(self.plan)
            process.assert_not_called()
        self.assertEqual(store.read('fixture.submit-intent.json'),{'plan_digest':digest(self.plan)})

    def test_syscall_filter_drift_blocks_adoption(self):
        backend,run,native=self.backend_fixture()
        def changed(argv,**kwargs):
            result=run(argv,**kwargs)
            if argv[-1]=='SystemCallFilter':result.stdout=json.dumps({'type':'(bas)','data':[False,['socket']]})
            return result
        with patch('native_verifier.subprocess.run',side_effect=changed),patch('native_verifier.observe_unit',return_value=native):
            with self.assertRaisesRegex(ValueError,'syscall isolation drift'):backend.adopt(self.plan)

    def test_unsubmitted_cleanup_requires_missing_dispatch_and_empty_account(self):
        import os
        from private_controller import TrustedStore
        control=self.root/'control';control.mkdir(mode=0o700)
        store=TrustedStore(control,owner_uid=os.getuid());backend=NativeVerifier(store,self.key)
        empty=type('Result',(),{'returncode':1,'stdout':''})()
        with patch.object(backend,'_intent',return_value='fixture'),patch('native_verifier.pwd.getpwnam',return_value=type('Account',(),{'pw_uid':123})()),patch('native_verifier.subprocess.run',return_value=empty) as process:
            result=backend.unsubmitted(self.plan)
            self.assertFalse(result['native_dispatched'])
            store.create('fixture.submit-intent.json',{'plan_digest':digest(self.plan)})
            with self.assertRaisesRegex(ValueError,'requires native ownership'):backend.unsubmitted(self.plan)
            self.assertEqual(process.call_count,1)
    def test_cleanup_intent_prevents_later_submit(self):
        import os
        from private_controller import TrustedStore
        control=self.root/'control';control.mkdir(mode=0o700)
        store=TrustedStore(control,owner_uid=os.getuid());backend=NativeVerifier(store,self.key)
        store.create('fixture.cleanup-intent.json',{})
        with patch.object(backend,'_intent',return_value='fixture'),patch('native_verifier.subprocess.run') as process:
            with self.assertRaisesRegex(ValueError,'cleanup prevents'):backend.submit(self.plan)
            process.assert_not_called()
