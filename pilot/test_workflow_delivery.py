import base64
import copy
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs

from admission import digest
from authority import require_active
from candidate_snapshot import capture_candidate,require_candidate_snapshot
from private_controller import TrustedStore,PrivateController
from test_workflow_delivery_contract import delivery
from workflow_delivery import WorkflowDelivery,WAIT,commit_object


def object_sha(kind,payload):return hashlib.sha1(kind.encode()+b' '+str(len(payload)).encode()+b'\0'+payload).hexdigest()


class Provider:
    """In-memory GitHub-shaped emulator, never an authenticated publisher."""
    def __init__(self,capability):
        self.cap=capability;self.blobs={};self.trees={};self.commits={};self.ref=None;self.pr=None
        self.calls=[];self.lost=None;self.apply=True;self.hook=None;self.check_status='success'
        self.check_total=1;self.review_state='APPROVED';self.review_head=None;self.list_override=None;self.pagination_metadata=True
    def page(self,suffix,rows):
        if not self.pagination_metadata:return rows
        number=int(parse_qs(suffix.split('?',1)[1])['page'][0])
        return {'items':rows,'page':number,'per_page':100,'has_next':len(rows)==100}
    def api(self,method,route,body):
        self.calls.append((method,route,copy.deepcopy(body)))
        result=self.request(method,route,body)
        if self.hook:self.hook(method,route,body,result)
        if method=='POST' and route.endswith('/'+str(self.lost)):
            if not self.apply:
                if self.lost=='git/refs':self.ref=None
                if self.lost=='pulls':self.pr=None
                if self.lost=='git/blobs':self.blobs.pop(result['sha'],None)
            raise OSError('Emulated unavailable provider response')
        return copy.deepcopy(result)
    def request(self,method,route,body):
        c=self.cap;suffix=route.removeprefix('repos/'+c['repository']+'/')
        if route=='user':return {'login':c['publisher'],'id':c['publisher_id']}
        repo={'full_name':c['repository'],'id':c['repository_id']}
        if route=='repos/'+c['repository']:return repo
        if suffix=='git/ref/heads/'+c['base_ref']:return {'object':{'sha':c['base_sha']}}
        if method=='GET' and suffix.startswith('git/blobs/'):return self.blobs.get(suffix.split('/')[-1])
        if method=='POST' and suffix=='git/blobs':
            data=base64.b64decode(body['content']);sha=object_sha('blob',data)
            result={'sha':sha,'size':len(data),'encoding':'base64','content':body['content']};self.blobs[sha]=result;return result
        if method=='GET' and suffix.startswith('git/trees/'):return self.trees.get(suffix.split('/')[-1])
        if method=='POST' and suffix=='git/trees':
            if 'base_tree' in body:raise AssertionError('Complete tree must never overlay provider base')
            rows=sorted(body['tree'],key=lambda r:(r['path']+('/' if r['type']=='tree' else '')).encode())
            payload=b''.join(r['mode'].lstrip('0').encode()+b' '+r['path'].encode()+b'\0'+bytes.fromhex(r['sha']) for r in rows)
            sha=object_sha('tree',payload);result={'sha':sha,'truncated':False,'tree':rows};self.trees[sha]=result;return result
        if method=='GET' and suffix.startswith('git/commits/'):return self.commits.get(suffix.split('/')[-1])
        if method=='POST' and suffix=='git/commits':
            def ident(role):
                r=body[role];stamp=int(datetime.fromisoformat(r['date'].replace('Z','+00:00')).timestamp())
                return f"{r['name']} <{r['email']}> {stamp} +0000"
            raw=(f"tree {body['tree']}\n"+''.join('parent '+p+'\n' for p in body['parents'])+
                 'author '+ident('author')+'\ncommitter '+ident('committer')+'\n\n'+body['message']).encode()
            sha=object_sha('commit',raw);result={**body,'sha':sha,'tree':{'sha':body['tree']},'parents':[{'sha':p} for p in body['parents']]}
            self.commits[sha]=result;return result
        if suffix=='git/ref/heads/'+c['branch']:return self.ref
        if method=='POST' and suffix=='git/refs':self.ref={'object':{'sha':body['sha']}};return self.ref
        if suffix.startswith('pulls?'):return self.page(suffix,self.list_override if self.list_override is not None else ([] if self.pr is None else [self.pr]))
        if method=='POST' and suffix=='pulls':
            self.pr={**body,'number':17,'state':'open','user':{'login':c['publisher'],'id':c['publisher_id']},
                     'html_url':'https://github.com/'+c['repository']+'/pull/17',
                     'head':{'sha':self.ref['object']['sha'],'ref':c['branch'],'repo':repo.copy()},
                     'base':{'sha':c['base_sha'],'ref':c['base_ref'],'repo':repo.copy()}}
            return self.pr
        if suffix=='pulls/17':return self.pr
        head=self.ref['object']['sha'] if self.ref else None
        if suffix.startswith('commits/'):
            required=c['required_checks'][0]
            return {'total_count':self.check_total,'check_runs':[{'id':101,'name':required['name'],'app':{'id':required['app_id'],'slug':required['app_slug']},
                    'head_sha':head,'status':'completed','conclusion':self.check_status,
                    'details_url':'https://github.com/'+c['repository']+'/actions/runs/12/job/13'}]}
        if suffix=='actions/runs/12':
            required=c['required_checks'][0]
            return {'head_sha':head,'head_branch':c['branch'],'path':required['workflow_path'],'event':'pull_request',
                    'status':'completed','conclusion':'success','repository':repo.copy(),'head_repository':repo.copy(),
                    'pull_requests':[{'number':17,'head':{'sha':head},'base':{'sha':c['base_sha']}}]}
        if suffix.startswith('pulls/17/reviews?'):
            return self.page(suffix,[{'id':102,'user':r,'state':self.review_state,'commit_id':self.review_head or head} for r in c['required_reviews']])
        raise AssertionError((method,route,body))


class FixtureController:
    def __init__(self,root):
        from types import SimpleNamespace
        self.contract_digest='b'*64;self.store=TrustedStore(root/'control',owner_uid=os.getuid())
        self.store.create('credential-stream.lock',{})
        self.candidate=root/'candidate';self.candidate.mkdir();(self.candidate/'source.txt').write_bytes(b'accepted source\n')
        (self.candidate/'nested').mkdir();(self.candidate/'nested'/'run').write_bytes(b'#!/bin/sh\n');(self.candidate/'nested'/'run').chmod(0o700)
        self.policy={'schema':1,'candidate_root':str(self.candidate),'scope':'entire_candidate','allowed_uids':[os.getuid()],
                     'max_entries':100,'max_file_bytes':4096,'max_total_bytes':16384,'max_depth':6}
        self.snapshot=capture_candidate(self.policy);self.cap=delivery(self.contract_digest)
        self.binding={'schema':4,'workflow_delivery':self.cap};self.state={'phase':'SHIP','delivery':{'status':'pending'},'complete':False}
        self.proof={'checkpoint_sha256':digest(self.state),'outcome_proof':{'checkpoint_sha256':digest(self.state),'tasks':{}},'candidate_source':{'policy':self.policy,'snapshot':self.snapshot}}
        intent={'fixture':'already qualified real parent-reader prerequisite'}
        receipt={'intent_digest':digest(intent),'postimage_review_proof':self.proof}
        self.quiescence={'account':'fixture','empty':True};self.journal=SimpleNamespace(read=lambda:('journal-fixture',{}))
        self.cut={'binding_sha256':digest(self.binding),'parent_receipt':receipt,'parent_receipt_sha256':digest(receipt),
                  'outcome':{'journal_revision':'journal-fixture','quiescence':self.quiescence,'task_histories':{}}}
        self.store.create(self.contract_digest+'.workflow.json',self.binding)
        self.store.create(self.contract_digest+'.parent-acceptance.json',receipt)
        self.store.create(self.contract_digest+'.parent-acceptance-intent.json',intent)
        self.active=True;self.owned=False
        self.workflow_gate=SimpleNamespace(_read=lambda:(self.store.read(self.contract_digest+'.workflow.json'),self.state,{}),
                                           final_review_proof=lambda:copy.deepcopy(self.proof),
                                           accepted_parent_image=lambda binding,state:state)
    _parent_proof_at_checkpoint=staticmethod(PrivateController._parent_proof_at_checkpoint)
    def authenticate_workflow_parent_acceptance(self):
        self._workflow_mutation_authority();self._unowned();require_candidate_snapshot(self.policy,self.snapshot)
        return copy.deepcopy(self.cut)
    def _contract(self):require_active(self.store,self.contract_digest)
    def _workflow_mutation_authority(self,**kwargs):
        require_active(self.store,self.contract_digest)
        if not self.active:raise ValueError('Original fixture window expired')
    def _unowned(self):
        if self.owned:raise ValueError('Fixture account not quiescent')
    def _require_no_pending_task_acceptance(self):pass
    def _require_no_pending_task_credit(self):pass
    def _workflow_quiescence(self):return self.quiescence
    def _workflow_source_guard(self,proof,**kwargs):self._workflow_mutation_authority();require_candidate_snapshot(self.policy,self.snapshot)


class WorkflowDeliveryTests(unittest.TestCase):
    def setUp(self):
        if sys.platform!='linux':
            mount=patch('candidate_snapshot._mount_id',return_value=1);mount.start();self.addCleanup(mount.stop)
            mount=patch('git_candidate_export._mount_id',return_value=1);mount.start();self.addCleanup(mount.stop)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);root=Path(self.temp.name).resolve();(root/'control').mkdir(mode=0o700)
        self.controller=FixtureController(root);self.provider=Provider(self.controller.cap)
        self.adapter=WorkflowDelivery(self.controller,self.provider.api)
    def complete(self):
        for _ in range(20):
            result=self.adapter.step()
            if result=='workflow_delivery_verified':return self.adapter._read('complete')
            self.assertEqual(result,WAIT)
        self.fail('Delivery failed to converge within bounded emulator steps')
    def ready_pr(self):
        for _ in range(20):
            self.adapter.step()
            if self.provider.pr is not None:return
        self.fail('PR preparation failed')
    def ready_commit(self):
        for _ in range(20):
            self.assertEqual(self.adapter.step(),WAIT)
            if self.adapter._read('commit') is not None:return
        self.fail('Commit publication failed')

    def test_review_cut_guard_still_rejects_drift_during_get(self):
        c=self.controller
        c.workflow_gate.final_review_cut=lambda:(c.store.read(c.contract_digest+'.workflow.json'),copy.deepcopy(c.state),copy.deepcopy(c.proof))
        self.adapter._initialize()
        original=self.adapter.api
        def changed(method,route,body):
            result=original(method,route,body)
            c.state['new_required_obligation']='unverified'
            return result
        self.adapter.api=changed
        with self.assertRaises(ValueError):self.adapter._api('GET','user')
        self.assertEqual(len(self.provider.calls),1)
        self.assertIsNone(self.adapter._read('complete'))

    def test_review_cut_path_and_legacy_path_produce_same_delivery(self):
        c=self.controller
        c.workflow_gate.final_review_cut=lambda:(c.store.read(c.contract_digest+'.workflow.json'),copy.deepcopy(c.state),copy.deepcopy(c.proof))
        receipt=self.complete()
        self.assertTrue(receipt['delivery_verified'])
        self.assertFalse(receipt['complete'])
        c.workflow_gate.final_review_cut=lambda:None
        self.assertEqual(self.adapter.authenticate_delivery(),receipt)

    def test_commit_seal_stops_before_ref_and_requires_fresh_remote_commit(self):
        self.ready_commit()
        self.assertIsNone(self.provider.ref)
        self.assertIsNone(self.adapter._read('ref-intent'))
        sealed=self.adapter._read('commit')
        self.assertEqual(sealed,self.adapter.plan['commit'])
        self.provider.commits[sealed['sha']]['message']='substituted remote commit'
        with self.assertRaisesRegex(ValueError,'commit differs'):self.adapter.step()
        self.assertIsNone(self.adapter._read('ref-intent'))

    def test_substituted_commit_seal_blocks_ref_publication(self):
        self.ready_commit();name=self.controller.contract_digest+'.workflow-delivery-commit.json'
        original=self.adapter._read('commit');self.controller.store.remove(name)
        self.controller.store.create(name,{**original,'sha':'0'*40})
        with self.assertRaisesRegex(ValueError,'commit record drift'):self.adapter.step()
        self.assertIsNone(self.provider.ref)

    def test_uncertain_commit_response_reconciles_once_without_ref_in_same_wake(self):
        self.provider.lost='git/commits'
        with self.assertRaises(OSError):self.complete()
        self.assertIsNone(self.adapter._read('commit'))
        self.provider.lost=None
        self.assertEqual(self.adapter.step(),WAIT)
        self.assertIsNotNone(self.adapter._read('commit'));self.assertIsNone(self.adapter._read('ref-intent'))
        writes=[c for c in self.provider.calls if c[0]=='POST' and c[1].endswith('/git/commits')]
        self.assertEqual(len(writes),1)
        self.assertTrue(self.complete()['delivery_verified'])

    def test_complete_tree_and_verified_draft_preserve_checkpoint_and_source(self):
        before=copy.deepcopy(self.controller.state);receipt=self.complete()
        self.assertTrue(receipt['delivery_verified']);self.assertFalse(receipt['complete'])
        self.assertEqual(self.controller.state,before);require_candidate_snapshot(self.controller.policy,self.controller.snapshot)
        root=self.provider.trees[self.provider.commits[receipt['head_sha']]['tree']['sha']]
        self.assertEqual({r['path'] for r in root['tree']},{'source.txt','nested'})
        self.assertNotIn('deleted-baseline-file.txt',{r['path'] for r in root['tree']})
        nested=next(r for r in root['tree'] if r['path']=='nested');self.assertEqual(self.provider.trees[nested['sha']]['tree'][0]['mode'],'100755')
        before=len([c for c in self.provider.calls if c[0]=='POST']);self.assertEqual(self.complete(),receipt)
        self.assertEqual(len([c for c in self.provider.calls if c[0]=='POST']),before)
    def test_commit_identity_matches_independent_git_commit_tree(self):
        if not shutil.which('git'):self.skipTest('Requires independent Git oracle')
        with tempfile.TemporaryDirectory() as temporary:
            env={'PATH':os.defpath,'HOME':'/nonexistent','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'}
            subprocess.run(['git','init','--bare',temporary],env=env,capture_output=True,check=True)
            tree=subprocess.run(['git','--git-dir='+temporary,'mktree'],input=b'',env=env,capture_output=True,check=True).stdout.decode().strip()
            meta=self.controller.cap['commit']
            for role in ('AUTHOR','COMMITTER'):
                env.update({'GIT_'+role+'_NAME':meta['name'],'GIT_'+role+'_EMAIL':meta['email'],'GIT_'+role+'_DATE':meta['date']})
            parent=subprocess.run(['git','--git-dir='+temporary,'commit-tree',tree],input=b'base\n',env=env,capture_output=True,check=True).stdout.decode().strip()
            cap={**self.controller.cap,'base_sha':parent}
            actual=subprocess.run(['git','--git-dir='+temporary,'commit-tree',tree,'-p',parent],input=meta['message'].encode(),env=env,capture_output=True,check=True).stdout.decode().strip()
            self.assertEqual(commit_object(cap,tree)['sha'],actual)
    def test_expiry_revocation_and_source_drift_block_provider_calls(self):
        self.adapter.step();before=len(self.provider.calls)
        for problem in ('expiry','revocation','source'):
            with self.subTest(problem=problem):
                if problem=='expiry':self.controller.active=False
                elif problem=='revocation':self.controller.store.create(self.controller.contract_digest+'.revocation-intent.json',{})
                else:(self.controller.candidate/'source.txt').write_text('drift')
                with self.assertRaises(ValueError):self.adapter.step()
                self.assertEqual(len(self.provider.calls),before)
                self.controller.active=True
                if problem=='revocation':self.controller.store.remove(self.controller.contract_digest+'.revocation-intent.json')
    def test_mutation_during_provider_response_cannot_seal_delivery(self):
        self.ready_pr()
        def mutate(method,route,body,result):
            (self.controller.candidate/'source.txt').write_text('changed during readback')
        self.provider.hook=mutate
        with self.assertRaises(ValueError):self.adapter.step()
        self.assertIsNone(self.adapter._read('complete'))
    def test_get_response_rechecks_current_authority_and_proof(self):
        for drift in ('journal','parent','checkpoint','native','revocation','window','proof','source'):
            with self.subTest(drift=drift):
                self.setUp();self.adapter.cut=self.controller.authenticate_workflow_parent_acceptance()
                def changed(method,route,body,result):
                    c=self.controller
                    if drift=='journal':c.journal.read=lambda:('changed-journal',{})
                    elif drift=='parent':
                        name=c.contract_digest+'.parent-acceptance.json';value=c.store.read(name)
                        c.store.remove(name);c.store.create(name,{**value,'unexpected':'changed'})
                    elif drift=='checkpoint':c.state['blocker']='late requirement'
                    elif drift=='native':c.owned=True
                    elif drift=='revocation':c.store.create(c.contract_digest+'.revocation-intent.json',{})
                    elif drift=='window':c.active=False
                    elif drift=='proof':c.proof['outcome_proof']['tasks']={'substituted':{'observation':{'checkpoint_sha256':digest(c.state)}}}
                    else:(c.candidate/'source.txt').write_text('changed during GET')
                self.provider.hook=changed
                with self.assertRaises(ValueError):self.adapter._api('GET','user')
                self.assertEqual([c[0] for c in self.provider.calls],['GET'])
                self.assertIsNone(self.adapter._read('complete'))

    def test_applied_and_unapplied_uncertain_mutable_writes_never_replay(self):
        for operation in ('git/refs','pulls'):
            for apply in (True,False):
                with self.subTest(operation=operation,apply=apply):
                    self.setUp();self.provider.lost=operation;self.provider.apply=apply
                    with self.assertRaises(OSError):self.complete()
                    self.provider.lost=None
                    for _ in range(3):self.adapter.step()
                    writes=[c for c in self.provider.calls if c[0]=='POST' and c[1].endswith('/'+operation)]
                    self.assertEqual(len(writes),1)
                    if apply:self.assertTrue(self.complete()['delivery_verified'])
                    else:self.assertIsNone(self.adapter._read('complete'))
    def test_uncertain_immutable_object_reconciles_content_identity(self):
        self.provider.lost='git/blobs'
        with self.assertRaises(OSError):self.complete()
        self.provider.lost=None;self.complete()
        first=self.provider.calls[0:]
        blobs=[c for c in first if c[0]=='POST' and c[1].endswith('/git/blobs')]
        self.assertEqual(len(blobs),2)  # exactly two distinct candidate blobs
    def test_required_checks_fail_or_wait_and_incomplete_listing_blocks(self):
        self.ready_pr();self.provider.check_status='failure'
        with self.assertRaisesRegex(ValueError,'check failed'):self.adapter.step()
        self.provider.check_status='success';self.provider.check_total=2
        with self.assertRaisesRegex(ValueError,'Truncated'):self.adapter.step()
        self.assertIsNone(self.adapter._read('complete'))
    def test_stale_or_dismissed_reviews_do_not_verify_delivery(self):
        self.ready_pr();self.provider.review_head='c'*40
        self.assertEqual(self.adapter.step(),WAIT)
        self.provider.review_head=None;self.provider.review_state='DISMISSED'
        self.assertEqual(self.adapter.step(),WAIT);self.assertIsNone(self.adapter._read('complete'))
    def test_foreign_head_base_or_publisher_cannot_complete(self):
        self.ready_pr();original=copy.deepcopy(self.provider.pr)
        for side in ('head','base','user'):
            self.provider.pr=copy.deepcopy(original)
            if side=='user':self.provider.pr['user']['id']=999
            else:self.provider.pr[side]['sha']='c'*40
            with self.subTest(side=side),self.assertRaises(ValueError):self.adapter.step()
            self.assertIsNone(self.adapter._read('complete'))
    def test_ambiguous_or_unbounded_pr_listings_cannot_create_another_pr(self):
        self.ready_pr();self.provider.list_override=[self.provider.pr]*2
        with self.assertRaisesRegex(ValueError,'Ambiguous'):self.adapter.step()
        self.provider.list_override=[self.provider.pr]*100
        with self.assertRaisesRegex(ValueError,'exceeds complete'):self.adapter.step()
        self.assertEqual(len([c for c in self.provider.calls if c[0]=='POST' and c[1].endswith('/pulls')]),1)
    def test_provider_tree_extra_file_or_truncation_cannot_complete(self):
        self.ready_pr();root=self.provider.trees[next(iter(self.provider.commits.values()))['tree']['sha']]
        root['truncated']=True
        with self.assertRaisesRegex(ValueError,'Incomplete workflow tree'):self.adapter.step()
        root['truncated']=False;root['tree'].append({'path':'foreign','mode':'100644','type':'blob','sha':'a'*40})
        with self.assertRaisesRegex(ValueError,'complete accepted inventory'):self.adapter.step()
    def test_final_acceptance_provider_calls_cannot_leave_stale_endpoint(self):
        for drift in ('head','base','draft','branch'):
            with self.subTest(drift=drift):
                self.setUp();self.ready_pr();rounds=0
                def change(method,route,body,result):
                    nonlocal rounds
                    if '/check-runs?' in route:
                        rounds+=1
                        if rounds==2:
                            if drift=='branch':self.provider.ref['object']['sha']='c'*40
                            elif drift=='draft':self.provider.pr['draft']=False
                            else:self.provider.pr[drift]['sha']='c'*40
                self.provider.hook=change
                with self.assertRaises(ValueError):self.adapter.step()
                self.assertIsNone(self.adapter._read('complete'))
    def test_bare_short_page_without_pagination_proof_cannot_verify(self):
        self.ready_pr();self.provider.pagination_metadata=False
        with self.assertRaisesRegex(ValueError,'pagination metadata'):self.adapter.step()
        self.assertIsNone(self.adapter._read('complete'))

if __name__=='__main__':unittest.main()
