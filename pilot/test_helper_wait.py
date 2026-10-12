import errno
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import pinned_helper


class HelperWaitTests(unittest.TestCase):
    def run_child(self,code,*,timeout=2,encoded=b'bounded input'):
        with tempfile.TemporaryFile() as output,tempfile.TemporaryFile() as errors:
            result=pinned_helper._run_helper([sys.executable,'-I','-c',code],encoded,
                output,errors,{'PATH':'/usr/bin:/bin'},timeout)
            output.seek(0);errors.seek(0)
            return result,output.read(),errors.read()

    def test_legacy_wait_preserves_input_output_and_one_launch(self):
        original=subprocess.Popen
        with patch.object(pinned_helper,'_pidfd_wait_available',return_value=False),patch.object(subprocess,'Popen',wraps=original) as launched:
            result,out,err=self.run_child('import sys;sys.stdout.buffer.write(sys.stdin.buffer.read());sys.stderr.write("error stream")')
        self.assertEqual(launched.call_count,1);self.assertEqual(result.returncode,0)
        self.assertEqual(out,b'bounded input');self.assertEqual(err,b'error stream')

    def test_legacy_deadline_kills_and_reaps_owned_child(self):
        original=subprocess.Popen;children=[]
        def launch(*args,**kwargs):
            child=original(*args,**kwargs);children.append(child);return child
        with patch.object(pinned_helper,'_pidfd_wait_available',return_value=False),patch.object(subprocess,'Popen',side_effect=launch):
            with self.assertRaises(subprocess.TimeoutExpired):self.run_child('import time;time.sleep(5)',timeout=.03)
        self.assertEqual(len(children),1);self.assertIsNotNone(children[0].returncode)

    def test_oversized_input_rejects_without_launch(self):
        with patch.object(subprocess,'Popen') as launched:
            with self.assertRaisesRegex(ValueError,'Bounded helper input'):self.run_child('',encoded=b'x'*1572865)
        launched.assert_not_called()

    def test_nonzero_exit_is_preserved_for_existing_result_validator(self):
        result,_,_=self.run_child('raise SystemExit(7)');self.assertEqual(result.returncode,7)

    @unittest.skipUnless(callable(getattr(os,'pidfd_open',None)),'Linux pidfd required')
    def test_event_wait_matches_legacy_and_closes_descriptors(self):
        before=set(os.listdir('/proc/self/fd'))
        code='import sys;sys.stdout.buffer.write(sys.stdin.buffer.read())'
        with patch.object(pinned_helper,'_pidfd_wait_available',return_value=False):legacy=self.run_child(code)
        with patch.object(pinned_helper,'_pidfd_wait_available',return_value=True):current=self.run_child(code)
        self.assertEqual(current[0].returncode,legacy[0].returncode);self.assertEqual(current[1:],legacy[1:])
        self.assertEqual(set(os.listdir('/proc/self/fd')),before)

    @unittest.skipUnless(callable(getattr(os,'pidfd_open',None)),'Linux pidfd required')
    def test_capability_denial_selects_legacy_before_exactly_one_launch(self):
        original=subprocess.Popen
        with patch.object(os,'pidfd_open',side_effect=PermissionError(errno.EPERM,'denied')),patch.object(subprocess,'Popen',wraps=original) as launched:
            result,_,_=self.run_child('pass')
        self.assertEqual(result.returncode,0);self.assertEqual(launched.call_count,1)

    @unittest.skipUnless(callable(getattr(os,'pidfd_open',None)),'Linux pidfd required')
    def test_event_timeout_interrupt_and_waiter_failure_reap_without_retry(self):
        original=subprocess.Popen;select=pinned_helper.select.select
        for failure in ('timeout',KeyboardInterrupt(),ValueError('waiter failed')):
            children=[];before=set(os.listdir('/proc/self/fd'))
            def launch(*args,**kwargs):
                child=original(*args,**kwargs);children.append(child);return child
            def wait(*args):
                if failure=='timeout':return select(*args)
                raise failure
            with self.subTest(failure=failure),patch.object(pinned_helper,'_pidfd_wait_available',return_value=True),patch.object(subprocess,'Popen',side_effect=launch),patch.object(pinned_helper.select,'select',side_effect=wait):
                with self.assertRaises(subprocess.TimeoutExpired if failure=='timeout' else type(failure)):
                    self.run_child('import time;time.sleep(5)',timeout=.03)
            self.assertEqual(len(children),1);self.assertIsNotNone(children[0].returncode)
            self.assertEqual(set(os.listdir('/proc/self/fd')),before)

    @unittest.skipUnless(callable(getattr(os,'pidfd_open',None)),'Linux pidfd required')
    def test_exit_before_pidfd_acquisition_is_reaped_without_relaunch(self):
        original=subprocess.Popen;children=[]
        def launch(*args,**kwargs):
            child=original(*args,**kwargs);children.append(child);return child
        def gone(pid):
            children[0].wait();raise ProcessLookupError(errno.ESRCH,'already exited')
        with patch.object(pinned_helper,'_pidfd_wait_available',return_value=True),patch.object(subprocess,'Popen',side_effect=launch),patch.object(os,'pidfd_open',side_effect=gone):
            result,_,_=self.run_child('pass')
        self.assertEqual(result.returncode,0);self.assertEqual(len(children),1)

    @unittest.skipUnless(callable(getattr(os,'pidfd_open',None)),'Linux pidfd required')
    def test_interrupt_and_empty_readiness_keep_original_deadline(self):
        real_select=pinned_helper.select.select
        calls=[]
        def wait(*args):
            calls.append(args[3])
            if len(calls)==1:raise InterruptedError()
            if len(calls)==2:return ([],[],[])
            return real_select(*args)
        with patch.object(pinned_helper,'_pidfd_wait_available',return_value=True),patch.object(pinned_helper.select,'select',side_effect=wait):
            result,_,_=self.run_child('pass')
        self.assertEqual(result.returncode,0)
        self.assertGreaterEqual(len(calls),3)
        self.assertTrue(all(a>=b for a,b in zip(calls,calls[1:])))

    def test_missing_pidfd_capability_selects_legacy_before_launch(self):
        with patch.object(os,'pidfd_open',None,create=True):
            result,_,_=self.run_child('pass')
        self.assertEqual(result.returncode,0)
