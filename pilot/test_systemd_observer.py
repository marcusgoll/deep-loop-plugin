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
                       'Restart': 'no', 'Slice': 'system.slice', 'ControlGroup': ''}
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
    def test_missing_population_file_is_not_empty(self):
        (self.group/'cgroup.events').unlink()
        with self.assertRaises(ValueError): self.observe()

if __name__ == '__main__': unittest.main()
