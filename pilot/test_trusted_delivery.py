import copy
import hashlib
import os
from pathlib import Path
import tempfile
import unittest

from admission import digest,initialize,reserve,finish
from private_controller import TrustedStore
from trusted_delivery import TrustedDelivery,ARTIFACT,WORKFLOW

class Journal:
    def __init__(self,contract,evidence):
        self.contract_digest=digest(contract)
        state=reserve(initialize(self.contract_digest),self.contract_digest,run_id=1,run_attempt=1,model_seconds=600,active_seconds=1200)
        self.state=finish(state,self.contract_digest,run_id=1,run_attempt=1,progress_receipt=digest(evidence))
    def read(self):return 'fixture',copy.deepcopy(self.state)

class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=TrustedStore(Path(self.temp.name).resolve(),owner_uid=os.getuid());self.store.create('credential-stream.lock',{})
        self.data=b'approved disposable outcome\n'
        self.contract={'verification':{'baseline':{},'artifact_path':ARTIFACT,'artifact_sha256':hashlib.sha256(self.data).hexdigest()},
                       'delivery':{'repository':'marcusgoll/deep-loop-plugin','repository_id':2,'publisher_id':1,'base_ref':'codex/pilot-admission','source_sha':'a'*40,'commit_date':'2026-10-09T20:00:00Z','title':'Disposable pilot','body':'Exact approved artifact only.'}}
        self.key=digest(self.contract)
        self.evidence={'contract_digest':self.key,'verifier':'exact-artifact-v1','artifact_path':ARTIFACT,'artifact_sha256':self.contract['verification']['artifact_sha256'],
                       'files_digest':digest({ARTIFACT:self.contract['verification']['artifact_sha256']})}
        self.store.create(self.key+'.approval.json',{'contract':self.contract,'approval_ref':'human-fixture'})
        self.store.create(digest(self.evidence)+'.progress.json',self.evidence)
        self.journal=Journal(self.contract,self.evidence)
        self.calls=[];self.branch=None;self.pr=None;self.lost=None;self.create_before_loss=True
        self.delivery=TrustedDelivery(self.store,self.journal,self.api,lambda *a:self.data)
    def api(self,method,route,data):
        self.calls.append((method,route,data))
        suffix=route.removeprefix('repos/marcusgoll/deep-loop-plugin/')
        if route=='user':return {'login':'marcusgoll','id':1}
        if route=='repos/marcusgoll/deep-loop-plugin':return {'id':2}
        if suffix=='git/ref/heads/codex/pilot-admission':return {'object':{'sha':'a'*40}}
        if suffix=='git/commits/'+'a'*40:return {'tree':{'sha':'b'*40}}
        if method=='POST' and suffix=='git/blobs':return {'sha':hashlib.sha1(b'blob '+str(len(self.data)).encode()+b'\0'+self.data).hexdigest()}
        if method=='POST' and suffix=='git/trees':
            self.assertEqual(data['base_tree'],'b'*40);self.assertEqual(data['tree'][0]['path'],ARTIFACT);return {'sha':'c'*40}
        if method=='POST' and suffix=='git/commits':
            self.assertEqual(data['parents'],['a'*40]);self.assertEqual(data['author'],data['committer']);return {'sha':'d'*40}
        if suffix.startswith('git/ref/heads/deep-loop-pilot/'):return self.branch
        if method=='POST' and suffix=='git/refs':
            if self.create_before_loss:self.branch={'object':{'sha':data['sha']}}
            if self.lost=='ref':raise OSError('Lost write response')
            return self.branch
        if suffix.startswith('compare/'):
            return {'status':'ahead','ahead_by':1,'behind_by':0,'base_commit':{'sha':'a'*40},'merge_base_commit':{'sha':'a'*40},
                    'commits':[{'sha':'d'*40}],'files':[{'filename':ARTIFACT,'status':'added','sha':hashlib.sha1(b'blob '+str(len(self.data)).encode()+b'\0'+self.data).hexdigest()}]}
        if suffix.startswith('pulls?'):return [] if self.pr is None else [self.pr]
        if method=='POST' and suffix=='pulls':
            if self.create_before_loss:
                self.pr={'number':17,'state':'open','draft':True,'user':{'login':'marcusgoll'},'html_url':'https://github.com/marcusgoll/deep-loop-plugin/pull/17',
                         'head':{'sha':'d'*40,'ref':data['head'],'repo':{'full_name':'marcusgoll/deep-loop-plugin'}},
                         'base':{'sha':'a'*40,'ref':data['base'],'repo':{'full_name':'marcusgoll/deep-loop-plugin'}}}
            if self.lost=='pr':raise OSError('Lost PR response')
            return self.pr
        if suffix.startswith('commits/'):
            return {'check_runs':[{'name':'verify','app':{'slug':'github-actions'},'head_sha':'d'*40,'status':'completed','conclusion':'success','details_url':'https://github.com/marcusgoll/deep-loop-plugin/actions/runs/12/job/13'}]}
        if suffix=='actions/runs/12':return {'head_sha':'d'*40,'path':WORKFLOW,'event':'pull_request','status':'completed','conclusion':'success'}
        if suffix=='pulls/17':return self.pr
        self.fail('Unexpected endpoint '+route)
    def advance(self,count):
        for _ in range(count):self.assertEqual(self.delivery.step(),'wait_for_trusted_delivery')
    def test_incremental_exact_draft_delivery_and_current_readback(self):
        self.advance(6)
        self.assertEqual(self.delivery.step(),'delivered_verified_draft')
        self.assertEqual(self.delivery.step(),'delivered_verified_draft')
        writes=[r for m,r,d in self.calls if m=='POST']
        self.assertEqual(sum(r.endswith('/pulls') for r in writes),1)
        self.assertEqual(sum(r.endswith('/git/refs') for r in writes),1)
        self.assertFalse(any('merge' in r or 'delete' in r for r in writes))
    def test_lost_ref_response_adopts_without_second_write(self):
        self.advance(4);self.lost='ref'
        with self.assertRaises(OSError):self.delivery.step()
        self.lost=None;self.delivery.step()
        self.assertEqual(sum(m=='POST' and r.endswith('/git/refs') for m,r,d in self.calls),1)
    def test_lost_pr_response_adopts_without_duplicate(self):
        self.advance(5);self.lost='pr'
        with self.assertRaises(OSError):self.delivery.step()
        self.lost=None;self.assertEqual(self.delivery.step(),'delivered_verified_draft')
        self.assertEqual(sum(m=='POST' and r.endswith('/pulls') for m,r,d in self.calls),1)
    def test_uncertain_missing_pr_never_replays(self):
        self.advance(5);self.lost='pr';self.create_before_loss=False
        with self.assertRaises(OSError):self.delivery.step()
        self.lost=None
        self.assertEqual(self.delivery.step(),'wait_for_trusted_delivery')
        self.assertEqual(self.delivery.step(),'wait_for_trusted_delivery')
        self.assertEqual(sum(m=='POST' and r.endswith('/pulls') for m,r,d in self.calls),1)
    def test_no_progress_or_active_owner_never_writes(self):
        self.journal.state['attempts'][-1]['progress_receipt']=None
        with self.assertRaises(ValueError):self.delivery.step()
        self.assertEqual(self.calls,[])
        self.journal.state['attempts'][-1]['progress_receipt']=digest(self.evidence)
        self.store.create('active-owner.json',{})
        with self.assertRaises(ValueError):self.delivery.step()
        self.assertEqual(self.calls,[])
    def test_provider_diff_mismatch_blocks_pr_creation(self):
        self.advance(5)
        original=self.api
        def changed(method,route,data):
            result=original(method,route,data)
            if '/compare/' in route:result['files'][0]['filename']='unapproved.txt'
            return result
        self.delivery.api=changed
        with self.assertRaises(ValueError):self.delivery.step()
        self.assertIsNone(self.pr)

    def test_changed_branch_or_non_draft_pr_blocks(self):
        self.advance(5);self.branch={'object':{'sha':'e'*40}}
        with self.assertRaises(ValueError):self.delivery.step()
        self.branch={'object':{'sha':'d'*40}};self.delivery.step();self.pr['draft']=False
        with self.assertRaises(ValueError):self.delivery.step()

if __name__=='__main__':unittest.main()
