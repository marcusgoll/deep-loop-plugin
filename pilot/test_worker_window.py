import os
from pathlib import Path
import tempfile
import subprocess
import sys
import json
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

    def test_separate_process_recovers_original_window_without_reset(self):
        open_window(self.store,self.key,lambda:('boot',100))
        original=(self.store.root/(self.key+'.window.json')).read_bytes()
        script = """import os,sys,json
from pathlib import Path
from private_controller import TrustedStore
from worker_window import remaining
store=TrustedStore(Path(sys.argv[1]),owner_uid=os.getuid())
print(json.dumps({'remaining':remaining(store,sys.argv[2],lambda:('boot',1100))}))
"""
        result=subprocess.run([sys.executable,'-c',script,str(self.store.root),self.key],
                              cwd=Path(__file__).resolve().parent,capture_output=True,text=True,check=True,timeout=5)
        self.assertEqual(json.loads(result.stdout),{'remaining':2600})
        self.assertEqual((self.store.root/(self.key+'.window.json')).read_bytes(),original)

    def test_killed_creator_keeps_original_deadline(self):
        script = """import os,sys,time
from pathlib import Path
from private_controller import TrustedStore
from worker_window import open_window
store=TrustedStore(Path(sys.argv[1]),owner_uid=os.getuid())
open_window(store,sys.argv[2],lambda:('boot',100))
print('persisted',flush=True)
time.sleep(30)
"""
        process=subprocess.Popen([sys.executable,'-u','-c',script,str(self.store.root),self.key],
                                 cwd=Path(__file__).resolve().parent,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            import select
            readable,_,_=select.select([process.stdout],[],[],5)
            self.assertTrue(readable,'Creator did not persist window within bound')
            self.assertEqual(process.stdout.readline().strip(),'persisted')
            process.kill()
            process.wait(timeout=5)
            self.assertLess(process.returncode,0)
            self.assertEqual(remaining(self.store,self.key,lambda:('boot',1100)),2600)
            with self.assertRaises(FileExistsError):
                open_window(self.store,self.key,lambda:('boot',1100))
        finally:
            if process.poll() is None:process.kill();process.wait(timeout=5)
            process.stdout.close();process.stderr.close()

    def test_changed_boot_or_clock_blocks_without_recreation(self):
        open_window(self.store,self.key,lambda:('first',100))
        for clock in [lambda:('new',200),lambda:('first',99),lambda:('first',float('nan'))]:
            with self.assertRaises(ValueError):remaining(self.store,self.key,clock)
        self.assertEqual(self.store.read(self.key+'.window.json')['started'],100)

if __name__=='__main__':unittest.main()
