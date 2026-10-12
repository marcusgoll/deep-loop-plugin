"""Real process-kill recovery with a durable model-free provider emulator."""
import copy
import json
import os
from pathlib import Path
import signal
import unittest

from test_workflow_delivery import Provider
import test_workflow_delivery as fixtures
from workflow_delivery import WorkflowDelivery,WAIT


class DurableProvider(Provider):
    def __init__(self,capability,path,*,crash=None,apply=True):
        super().__init__(capability);self.path=Path(path);self.crash=crash;self.apply_crash=apply
        if not self.path.exists():self.save()
        self.load()
    def load(self):
        for name,value in json.loads(self.path.read_text()).items():setattr(self,name,value)
    def save(self):
        state={name:getattr(self,name) for name in ('blobs','trees','commits','ref','pr','calls')}
        temporary=self.path.with_suffix('.pending')
        with temporary.open('w') as stream:json.dump(state,stream);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,self.path)
        directory=os.open(self.path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(directory)
        finally:os.close(directory)
    def api(self,method,route,body):
        self.load();self.calls.append([method,route,copy.deepcopy(body)])
        result=self.request(method,route,body)
        kill=method=='POST' and route.endswith('/'+str(self.crash))
        if kill and not self.apply_crash:
            if self.crash=='git/refs':self.ref=None
            elif self.crash=='pulls':self.pr=None
            elif self.crash=='git/blobs':self.blobs.pop(result['sha'],None)
        self.save()
        if kill:os.kill(os.getpid(),signal.SIGKILL)
        return copy.deepcopy(result)


class WorkflowDeliveryCrashTests(unittest.TestCase):
    def setUp(self):fixtures.WorkflowDeliveryTests.setUp(self)
    def killed(self,operation,apply):
        path=self.controller.store.root.parent/'provider.json'
        provider=DurableProvider(self.controller.cap,path,crash=operation,apply=apply)
        child=os.fork()
        if child==0:
            try:
                adapter=WorkflowDelivery(self.controller,provider.api)
                for _ in range(20):adapter.step()
            except BaseException:os._exit(88)
            os._exit(89)
        _,status=os.waitpid(child,0)
        self.assertTrue(os.WIFSIGNALED(status));self.assertEqual(os.WTERMSIG(status),signal.SIGKILL)
        self.provider=DurableProvider(self.controller.cap,path)
        self.adapter=WorkflowDelivery(self.controller,self.provider.api)
    complete=fixtures.WorkflowDeliveryTests.complete
    def test_killed_mutable_writes_reconcile_without_replay(self):
        if not hasattr(os,'fork'):self.skipTest('Requires POSIX process-kill qualification')
        for operation in ('git/refs','pulls'):
            for apply in (True,False):
                with self.subTest(operation=operation,apply=apply):
                    self.setUp();self.killed(operation,apply)
                    if apply:self.assertTrue(self.complete()['delivery_verified'])
                    else:
                        for _ in range(3):self.assertEqual(self.adapter.step(),WAIT)
                        self.assertIsNone(self.adapter._read('complete'))
                    self.provider.load()
                    self.assertEqual(len([c for c in self.provider.calls if c[0]=='POST' and c[1].endswith('/'+operation)]),1)
    def test_killed_immutable_writes_reconcile_actual_content_identity(self):
        if not hasattr(os,'fork'):self.skipTest('Requires POSIX process-kill qualification')
        for apply in (True,False):
            with self.subTest(apply=apply):
                self.setUp();self.killed('git/blobs',apply);self.complete();self.provider.load()
                self.assertEqual(len([c for c in self.provider.calls if c[0]=='POST' and c[1].endswith('/git/blobs')]),2 if apply else 3)

if __name__=='__main__':unittest.main()
