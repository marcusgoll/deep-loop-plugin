from pathlib import Path
import subprocess
import tempfile
import unittest
from systemd_observer import observe_unit

UNIT = 'deep-loop-pilot-' + 'a'*64 + '-1-1'
INVOCATION = 'b'*32

class SystemdObserverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.group = self.root/'system.slice'/(UNIT+'.service')
        self.group.mkdir(parents=True)
        (self.group/'cgroup.events').write_text('populated 0\nfrozen 0\n')
        self.values = {'LoadState': 'loaded', 'ActiveState': 'inactive', 'InvocationID': INVOCATION,
                       'User': 'deep-loop-pilot', 'Group': 'deep-loop-pilot', 'KillMode': 'control-group',
                       'Restart': 'no', 'Slice': 'system.slice', 'ControlGroup': '',
                       'SubState': 'dead', 'MainPID': '0', 'RemainAfterExit': 'no'}
    def observe(self):
        def native(args, **kwargs):
            return subprocess.CompletedProcess(args, 0, stdout='\n'.join(k+'='+v for k,v in self.values.items()))
        return observe_unit(UNIT, INVOCATION, run=native, cgroup_root=self.root)
    def test_retained_inactive_invocation_and_empty_group(self):
        self.assertTrue(self.observe()['cgroup_empty'])
        (self.group/'cgroup.events').write_text('populated 1\n')
        self.assertFalse(self.observe()['cgroup_empty'])
    def test_absent_group_only_proves_empty_for_inactive_retained_unit(self):
        (self.group/'cgroup.events').unlink()
        self.group.rmdir()
        self.assertTrue(self.observe()['cgroup_empty'])
        self.values['ActiveState'] = 'active'
        self.values['ControlGroup'] = '/system.slice/'+UNIT+'.service'
        with self.assertRaises(ValueError): self.observe()
    def test_missing_or_changed_native_ownership_blocks(self):
        for key, value in [('LoadState','not-found'), ('InvocationID','c'*32), ('User','root'),
                           ('KillMode','process'), ('Restart','always'), ('Slice','other.slice'),
                           ('ControlGroup','/other')]:
            previous = self.values[key]
            self.values[key] = value
            with self.assertRaises(ValueError): self.observe()
            self.values[key] = previous
    def test_retained_success_requires_exited_main_process_and_empty_cgroup(self):
        self.values.update(ActiveState='active',SubState='exited',MainPID='0',RemainAfterExit='yes')
        self.assertTrue(self.observe()['execution_finished'])
        (self.group/'cgroup.events').write_text('populated 1\n')
        self.assertFalse(self.observe()['execution_finished'])
        (self.group/'cgroup.events').write_text('populated 0\n')
        self.values['MainPID']='123'
        with self.assertRaises(ValueError): self.observe()
    def test_missing_population_file_is_not_empty(self):
        (self.group/'cgroup.events').unlink()
        with self.assertRaises(ValueError): self.observe()

    def test_running_to_retained_exit_rereads_same_invocation_without_dispatch(self):
        (self.group/'cgroup.events').unlink();self.group.rmdir()
        running={**self.values,'ActiveState':'active','SubState':'running','MainPID':'123',
                 'ControlGroup':'/system.slice/'+UNIT+'.service','RemainAfterExit':'yes'}
        terminal={**running,'SubState':'exited','MainPID':'0','ControlGroup':''}
        snapshots=iter((running,terminal));calls=[]
        def native(args,**kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args,0,stdout='\n'.join(k+'='+v for k,v in next(snapshots).items()))
        observed=observe_unit(UNIT,INVOCATION,run=native,cgroup_root=self.root)
        self.assertTrue(observed['execution_finished']);self.assertTrue(observed['cgroup_empty'])
        self.assertEqual(len(calls),2)
        self.assertTrue(all(call[:2]==['/usr/bin/systemctl','show'] for call in calls))

    def test_missing_group_reread_rejects_foreign_or_still_running_native_state(self):
        (self.group/'cgroup.events').unlink();self.group.rmdir()
        running={**self.values,'ActiveState':'active','SubState':'running','MainPID':'123',
                 'ControlGroup':'/system.slice/'+UNIT+'.service','RemainAfterExit':'yes'}
        terminal={**running,'SubState':'exited','MainPID':'0','ControlGroup':''}
        for changes in ({'InvocationID':'c'*32},{'User':'root'},{'LoadState':'not-found'},running):
            snapshots=iter((running,{**terminal,**changes}))
            def native(args,**kwargs):
                return subprocess.CompletedProcess(args,0,stdout='\n'.join(k+'='+v for k,v in next(snapshots).items()))
            with self.assertRaises(ValueError):
                observe_unit(UNIT,INVOCATION,run=native,cgroup_root=self.root)

    def test_reappeared_cgroup_during_manager_reread_is_not_empty_proof(self):
        (self.group/'cgroup.events').unlink();self.group.rmdir()
        calls=0
        def native(args,**kwargs):
            nonlocal calls
            calls+=1
            if calls==2:
                self.group.mkdir();(self.group/'cgroup.events').write_text('populated 1\n')
            return subprocess.CompletedProcess(args,0,stdout='\n'.join(k+'='+v for k,v in self.values.items()))
        with self.assertRaisesRegex(ValueError,'Missing kernel'):
            observe_unit(UNIT,INVOCATION,run=native,cgroup_root=self.root)

if __name__ == '__main__': unittest.main()
