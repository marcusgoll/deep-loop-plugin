"""Process-crash delivery tests with a durable local provider emulator.

The emulator is a test double, not GitHub or an authenticated publisher.
Production delivery uses the existing GitHub transport unchanged.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest

from admission import digest, finish, initialize, reserve
from artifact_verifier import ArtifactVerifier
from delivery_artifact import DeliveryArtifact
from git_journal import GitJournal
from private_controller import TrustedStore
from trusted_delivery import ARTIFACT, TrustedDelivery
import test_trusted_delivery as delivery_fixture


def save(path, value):
    temporary=path.with_suffix('.pending')
    with temporary.open('w') as stream:
        json.dump(value,stream);stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


class DurableProvider(unittest.TestCase):
    def __init__(self, root, crash=None, apply=True):
        super().__init__()
        self.root=Path(root);self.crash=crash;self.apply=apply
        self.path=self.root/'provider.json';state=json.loads(self.path.read_text())
        self.data=(self.root/'candidate'/ARTIFACT).read_bytes()
        self.branch=state['branch'];self.pr=state['pr'];self.calls=state['calls']
        self.lost=None;self.create_before_loss=True
    def api(self,method,route,data):
        result=delivery_fixture.DeliveryTests.api(self,method,route,data)
        crash=method=='POST' and route.endswith('/'+str(self.crash))
        if crash and not self.apply:
            if self.crash=='git/refs':self.branch=None
            elif self.crash=='pulls':self.pr=None
        save(self.path,{'branch':self.branch,'pr':self.pr,'calls':self.calls})
        if crash:os.kill(os.getpid(),signal.SIGKILL)
        return result


def delivery(root, provider):
    root=Path(root);store=TrustedStore(root/'control',owner_uid=os.getuid())
    contract=json.loads((root/'contract.json').read_text());key=digest(contract)
    journal=GitJournal(root/'work',str(root/'journal.git'),key)
    return TrustedDelivery(store,journal,provider.api,DeliveryArtifact(root/'candidate',os.getuid()))


class DeliveryProcessRecovery(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve()
        control=self.root/'control';control.mkdir(mode=0o700)
        self.store=TrustedStore(control,owner_uid=os.getuid());self.store.create('credential-stream.lock',{})
        self.data=b'approved disposable outcome\n'
        artifact=self.root/'candidate'/ARTIFACT;artifact.parent.mkdir(parents=True);artifact.write_bytes(self.data)
        import hashlib
        self.contract={'verification':{'baseline':{},'artifact_path':ARTIFACT,'artifact_sha256':hashlib.sha256(self.data).hexdigest()},
                       'delivery':{'repository':'marcusgoll/deep-loop-plugin','repository_id':2,'publisher_id':1,'base_ref':'codex/pilot-admission','source_sha':'a'*40,'commit_date':'2026-10-09T20:00:00Z','title':'Disposable pilot','body':'Exact approved artifact only.'}}
        self.key=digest(self.contract)
        save(self.root/'contract.json',self.contract)
        save(self.root/'provider.json',{'branch':None,'pr':None,'calls':[]})
        self.store.create(self.key+'.approval.json',{'contract':self.contract,'approval_ref':'explicit-model-free-fixture'})
        for args in (['git','init','--bare',str(self.root/'journal.git')],['git','init',str(self.root/'work')]):
            subprocess.run(args,check=True,capture_output=True)
        self.journal=GitJournal(self.root/'work',str(self.root/'journal.git'),self.key)
        revision=self.journal.publish(None,initialize(self.key))
        state=reserve(initialize(self.key),self.key,run_id=1,run_attempt=1,model_seconds=600,active_seconds=1200)
        revision=self.journal.publish(revision,state)
        self.evidence=ArtifactVerifier(self.root/'candidate',os.getuid())(self.contract,{'contract_digest':self.key})
        progress=digest(self.evidence);self.store.create(progress+'.progress.json',self.evidence)
        self.journal.publish(revision,finish(state,self.key,run_id=1,run_attempt=1,progress_receipt=progress))
    def step(self):return delivery(self.root,DurableProvider(self.root)).step()
    def advance(self,steps):
        for _ in range(steps):self.assertEqual(self.step(),'wait_for_trusted_delivery')
    def crash(self, endpoint, apply=True):
        script="import sys;from test_delivery_recovery import DurableProvider,delivery;r=sys.argv[1];delivery(r,DurableProvider(r,sys.argv[2],sys.argv[3]=='yes')).step()"
        result=subprocess.run([sys.executable,'-c',script,str(self.root),endpoint,'yes' if apply else 'no'],
            cwd=Path(__file__).resolve().parent,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,-signal.SIGKILL,result.stderr)
    def writes(self,endpoint):
        state=json.loads((self.root/'provider.json').read_text())
        return sum(method=='POST' and route.endswith('/'+endpoint) for method,route,data in state['calls'])
    def test_ref_write_before_lost_response_adopts_without_replay(self):
        self.advance(4);self.crash('git/refs');self.advance(1)
        self.assertEqual(self.step(),'delivered_verified_draft')
        self.assertEqual(self.writes('git/refs'),1);self.assertEqual(self.writes('pulls'),1)
        self.assertEqual((self.root/'candidate'/ARTIFACT).read_bytes(),self.data)
    def test_pr_write_before_lost_response_adopts_without_replay(self):
        self.advance(5);self.crash('pulls')
        self.assertEqual(self.step(),'delivered_verified_draft')
        self.assertEqual(self.writes('pulls'),1)
    def test_unapplied_uncertain_ref_never_replays_or_completes(self):
        self.advance(4);self.crash('git/refs',apply=False);self.advance(2)
        self.assertEqual(self.writes('git/refs'),1)
        with self.assertRaises(FileNotFoundError):self.store.read(self.key+'.delivery-complete.json')
    def test_unapplied_uncertain_pr_never_replays_or_completes(self):
        self.advance(5);self.crash('pulls',apply=False);self.advance(2)
        self.assertEqual(self.writes('pulls'),1)
        with self.assertRaises(FileNotFoundError):self.store.read(self.key+'.delivery-complete.json')
    def test_candidate_changed_after_export_blocks_actual_reader(self):
        self.advance(2);before=(self.root/'provider.json').read_bytes()
        (self.root/'candidate'/ARTIFACT).write_bytes(b'changed')
        with self.assertRaises(ValueError):self.step()
        self.assertEqual((self.root/'provider.json').read_bytes(),before)


if __name__=='__main__':unittest.main()
