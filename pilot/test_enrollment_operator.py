import copy
import hashlib
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from admission import digest, initialize, reserve
from native_backend import permission_digest
from private_launch import launch_plan
import enrollment_operator as operator
from worker_units import units


class OperatorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.control=self.root/'control';self.control.mkdir()
        self.module=b'reviewed module'
        names=['private_worker.py','enrollment.py','enrollment_operator.py','resume_verifier.py']
        self.manifest={'control':str(self.control),'modules':dict.fromkeys(names,hashlib.sha256(self.module).hexdigest())}
        self.bundle=digest(self.manifest)
        self.installed={'bundle_digest':self.bundle,'units':units(self.bundle)}
        self.unit_digest=digest(self.installed)
        self.contract={'prompt':'Exact fixture','worker_wall_seconds':3600,'wakeup':{'model_seconds':600,'active_seconds':1200},
                       'verification':{'baseline':{},'artifact_path':'pilot/fixtures/private-lane-smoke.txt','artifact_sha256':'d'*64},
                       'resume_verification':{'checkpoint_path':'pilot/fixtures/private-lane-checkpoint.txt','checkpoint_sha256':'e'*64},
                       'runtime':{'bundle_digest':self.bundle,'unit_plan_digest':self.unit_digest},
                       'executor':{'path':'/pinned/native','sha256':'a'*64},
                       'delivery':{'repository':'marcusgoll/deep-loop-plugin','base_ref':'codex/pilot-admission',
                                   'source_sha':'b'*40,'publisher_id':1,'repository_id':2,'commit_date':'2026-10-09T20:00:00Z','title':'Pilot','body':'Exact fixture'}}
        self.key=digest(self.contract)
        self.candidate=self.root/'candidate'/self.key;self.candidate.mkdir(parents=True,mode=0o700)
        plan=launch_plan(reserve(initialize(self.key),self.key,run_id=1,run_attempt=1,model_seconds=600,active_seconds=1200),
                         self.key,run_id=1,run_attempt=1)
        checks={'candidate_write','private_direct_read_denied','private_symlink_read_denied','network_denied',
                'native_config_validated','systemd_io_validated','host_parent_descriptor_read_denied',
                'host_parent_memory_read_denied','external_capabilities_disabled'}
        self.qualification={'contract_digest':self.key,'executor':self.contract['executor'],
                            'permission_digest':permission_digest(plan),'candidate':str(self.candidate),
                            'checks':dict.fromkeys(checks,True)}
        self.records={self.unit_digest+'.units.json':self.installed,self.key+'.qualification.json':self.qualification}
        self.store=SimpleNamespace(read=lambda name:self.records[name])
        self.calls=[]
        def api(method,route,data):
            self.calls.append((method,route,data))
            return {'user':{'login':'marcusgoll','id':1},
                    'repos/marcusgoll/deep-loop-plugin':{'id':2,'permissions':{'push':True}},
                    'repos/marcusgoll/deep-loop-plugin/git/ref/heads/codex/pilot-admission':{'object':{'sha':'b'*40}}}[route]
        self.api=api
        def installed_bytes(path,mode):
            if mode==0o444:return self.module
            return self.installed['units'][path.name].encode()
        def process(argv,**kwargs):
            if argv[0]=='git':return SimpleNamespace(stdout='',returncode=0)
            return SimpleNamespace(stdout='disabled\n',returncode=1)
        for mock in [patch.object(operator,'CONTROL',self.control),patch.object(operator,'ROOT',str(self.root)),
                     patch.object(operator,'__file__',str(self.control/('bundle-'+self.bundle)/'enrollment_operator.py')),
                     patch.object(operator,'TrustedStore',return_value=SimpleNamespace(read=lambda name:self.manifest)),
                     patch.object(operator,'protected_bytes',side_effect=installed_bytes),
                     patch.object(operator.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=os.getuid(),pw_gid=os.getgid())),
                     patch.object(operator,'native',side_effect=lambda *args:'loaded' if '--property=LoadState' in args else 'inactive'),
                     patch.object(operator.subprocess,'run',side_effect=process)]:
            mock.start();self.addCleanup(mock.stop)

    def test_malformed_contract_rejected_before_installed_source_reads(self):
        cases=[('resume_verification','checkpoint_sha256','bad'),
               ('verification','artifact_path','unapproved.txt'),
               ('delivery','body',''),('delivery','commit_date','2026-02-31T20:00:00Z')]
        with patch.object(operator,'TrustedStore',side_effect=AssertionError('Must not inspect host')):
            for section,field,value in cases:
                with self.subTest(field=field):
                    contract=copy.deepcopy(self.contract);contract[section][field]=value
                    with self.assertRaises(ValueError):operator.preflight(self.store,contract,self.api)
        self.assertEqual(self.calls,[])

    def test_preflight_reads_exact_provider_identity_without_writes(self):
        result=operator.preflight(self.store,self.contract,self.api)
        self.assertEqual(result['contract_digest'],self.key)
        self.assertEqual(len(self.calls),3)
        self.assertTrue(all(call[0]=='GET' for call in self.calls))

    def test_candidate_extra_file_rejects_before_provider_calls(self):
        (self.candidate/'unexpected').write_text('partial')
        with self.assertRaises(ValueError):operator.preflight(self.store,self.contract,self.api)
        self.assertEqual(self.calls,[])

    def test_missing_qualification_check_blocks_before_provider_calls(self):
        self.qualification['checks'].pop('network_denied')
        with self.assertRaises(ValueError):operator.preflight(self.store,self.contract,self.api)
        self.assertEqual(self.calls,[])

    def test_module_drift_blocks_before_provider_calls(self):
        with patch.object(operator,'protected_bytes',return_value=b'changed'):
            with self.assertRaises(ValueError):operator.preflight(self.store,self.contract,self.api)
        self.assertEqual(self.calls,[])

    def test_moved_source_blocks_preflight(self):
        def changed(method,route,data):
            value=self.api(method,route,data)
            if '/git/ref/' in route:value['object']['sha']='c'*40
            return value
        with self.assertRaises(ValueError):operator.preflight(self.store,self.contract,changed)

    def test_activation_starts_timer_once_and_readbacks_without_enable(self):
        with patch.object(operator,'native',side_effect=['','active']) as native:
            self.assertEqual(operator.activate(self.contract),{'timer':'active','contract_digest':self.key})
        self.assertEqual(native.call_args_list[0].args,('start',operator.TIMER))
        self.assertEqual(native.call_count,2)

    def test_activation_unknown_state_raises_without_retry(self):
        with patch.object(operator,'native',side_effect=['','inactive']) as native:
            with self.assertRaises(ValueError):operator.activate(self.contract)
        self.assertEqual(native.call_count,2)


if __name__=='__main__':unittest.main()
