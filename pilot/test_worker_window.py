import os
from pathlib import Path
import tempfile
import unittest
from private_controller import TrustedStore
from worker_window import remaining,open_window

class WindowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=TrustedStore(Path(self.temp.name).resolve(),owner_uid=os.getuid())
        from admission import digest
        self.contract={'fixture':'explicit approved window','worker_wall_seconds':3600}
        self.key=digest(self.contract)
        self.store.create(self.key+'.approval.json',{'contract':self.contract,'approval_ref':'human-fixture'})
    def test_restart_preserves_deadline_and_exhaustion(self):
        open_window(self.store,self.key,lambda:('boot',100))
        self.assertEqual(remaining(self.store,self.key,lambda:('boot',100)),3600)
        self.assertEqual(remaining(self.store,self.key,lambda:('boot',1100)),2600)
        self.assertEqual(remaining(self.store,self.key,lambda:('boot',4000)),0)
        self.assertEqual(remaining(self.store,self.key,lambda:('boot',5000)),0)
    def test_missing_window_blocks_and_explicit_open_never_overwrites(self):
        with self.assertRaises(FileNotFoundError):remaining(self.store,self.key,lambda:('boot',100))
        open_window(self.store,self.key,lambda:('boot',100))
        with self.assertRaises(FileExistsError):open_window(self.store,self.key,lambda:('boot',200))

    def test_changed_boot_or_clock_blocks_without_recreation(self):
        open_window(self.store,self.key,lambda:('first',100))
        for clock in [lambda:('new',200),lambda:('first',99),lambda:('first',float('nan'))]:
            with self.assertRaises(ValueError):remaining(self.store,self.key,clock)
        self.assertEqual(self.store.read(self.key+'.window.json')['started'],100)

if __name__=='__main__':unittest.main()
