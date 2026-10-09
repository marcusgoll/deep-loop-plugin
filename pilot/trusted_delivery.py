"""Trusted, incremental GitHub delivery of one frozen disposable artifact.

The injected API is authenticated private-host infrastructure, never a candidate
callback. Mutable ref/PR writes have durable intents and are never replayed.
Immutable Git objects are content-addressed and may be reconciled identically.
"""
from authority import require_active
import base64
import hashlib
import re
from urllib.parse import urlencode

from resume_verifier import validate_resume_acceptance
from admission import digest

from frozen_contract import REPOSITORY, ARTIFACT, validate_delivery
WORKFLOW = '.github/workflows/pilot-verification.yml'


def sha(value):
    if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{40}',value) or value=='0'*40:
        raise ValueError('Invalid Git object identity')
    return value


class TrustedDelivery:
    def __init__(self,store,journal,api,artifact_reader):
        self.store,self.journal,self.api,self.artifact_reader=store,journal,api,artifact_reader
        self.key=journal.contract_digest
        self.prefix='repos/'+REPOSITORY+'/'
        self.acceptance=None

    def _record(self,suffix):
        try:return self.store.read(self.key+'.delivery-'+suffix+'.json')
        except FileNotFoundError:return None

    def _save(self,suffix,value):
        self.store.create(self.key+'.delivery-'+suffix+'.json',value)
        return 'wait_for_trusted_delivery'

    def _authorized_api(self, method, route, data):
        require_active(self.store, self.key)
        self._accepted_artifact()
        return self.api(method, route, data)

    def _accepted_artifact(self):
        if self.acceptance is None:
            raise ValueError('Provider operation lacks current accepted candidate')
        contract,evidence=self.acceptance
        data=self.artifact_reader(contract,evidence)
        if not isinstance(data,bytes) or len(data)>65536 or hashlib.sha256(data).hexdigest()!=contract['verification']['artifact_sha256']:
            raise ValueError('Stopped artifact no longer matches acceptance')
        return data

    def _call(self,method,route,data=None):
        return self._authorized_api(method,self.prefix+route,data)

    def _pr(self,record,commit,base):
        number=record.get('number')
        if (type(number)!=int or number<1 or record.get('state')!='open' or record.get('draft') is not True or
                record.get('user',{}).get('login')!='marcusgoll' or
                record.get('html_url')!='https://github.com/'+REPOSITORY+'/pull/'+str(number) or
                record.get('head',{}).get('sha')!=commit or
                record['head'].get('ref')!='deep-loop-pilot/'+self.key or
                record['head'].get('repo',{}).get('full_name')!=REPOSITORY or
                record.get('base',{}).get('sha')!=base['source_sha'] or
                record['base'].get('ref')!=base['base_ref'] or
                record['base'].get('repo',{}).get('full_name')!=REPOSITORY):
            raise ValueError('PR no longer matches frozen draft delivery')
        return number

    def step(self):
        with self.store.lock():
            require_active(self.store, self.key)
            approval=self.store.read(self.key+'.approval.json');contract=approval['contract']
            if digest(contract)!=self.key or not approval['approval_ref']:
                raise ValueError('Exact authenticated delivery approval required')
            try:self.store.read('active-owner.json')
            except FileNotFoundError:pass
            else:raise ValueError('Delivery cannot overlap model ownership')
            _,journal=self.journal.read()
            if not journal['attempts'] or journal['attempts'][-1]['status']!='finished':
                raise ValueError('Missing finished accepted execution')
            progress=journal['attempts'][-1]['progress_receipt']
            if progress is None:raise ValueError('No independently verified acceptance')
            evidence=self.store.read(progress+'.progress.json')
            verification=contract['verification'];delivery=contract['delivery']
            if (digest(evidence)!=progress or evidence.get('contract_digest')!=self.key or
                    evidence.get('verifier')!='exact-artifact-v1' or evidence.get('artifact_path')!=ARTIFACT or
                    evidence.get('artifact_sha256')!=verification['artifact_sha256'] or
                    verification['artifact_path']!=ARTIFACT or
                    evidence.get('files_digest')!=digest({**verification['baseline'],ARTIFACT:verification['artifact_sha256']})):
                raise ValueError('Untrusted delivery evidence')
            validate_delivery(delivery)
            resume_proof = (validate_resume_acceptance(contract,evidence,self.store)
                            if 'resume_verification' in contract else None)
            # Re-read the stopped accepted candidate at every transition, including
            # terminal readback. A persisted blob is not current candidate proof.
            self.acceptance=(contract,evidence)
            data=self._accepted_artifact()
            base=sha(delivery['source_sha'])
            publisher=self._authorized_api('GET','user',None)
            if publisher.get('login')!='marcusgoll' or publisher.get('id')!=delivery['publisher_id']:
                raise ValueError('Private publisher identity changed')
            if self._authorized_api('GET','repos/'+REPOSITORY,None).get('id')!=delivery['repository_id']:
                raise ValueError('Frozen repository identity changed')
            reference=self._call('GET','git/ref/heads/'+delivery['base_ref'])
            if reference is None or reference.get('object',{}).get('sha')!=base:
                raise ValueError('Frozen delivery base moved')
            saved=self._record('base')
            if saved is None:
                source=self._call('GET','git/commits/'+base)
                return self._save('base',{'source_sha':base,'tree_sha':sha(source['tree']['sha'])})
            if saved['source_sha']!=base:raise ValueError('Protected source drift')
            blob=self._record('blob')
            if blob is None:
                expected=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
                response=self._call('POST','git/blobs',{'content':base64.b64encode(data).decode(),'encoding':'base64'})
                if response['sha']!=expected:raise ValueError('Published blob readback changed')
                return self._save('blob',{'sha':expected})
            tree=self._record('tree')
            if tree is None:
                response=self._call('POST','git/trees',{'base_tree':saved['tree_sha'],
                                   'tree':[{'path':ARTIFACT,'mode':'100644','type':'blob','sha':sha(blob['sha'])}]})
                return self._save('tree',{'sha':sha(response['sha'])})
            commit=self._record('commit')
            if commit is None:
                identity={'name':'Deep Loop pilot','email':'pilot@users.noreply.github.com','date':delivery['commit_date']}
                response=self._call('POST','git/commits',{'message':'Disposable Deep Loop pilot '+self.key,
                                   'tree':sha(tree['sha']),'parents':[base],'author':identity,'committer':identity})
                return self._save('commit',{'sha':sha(response['sha'])})
            head=sha(commit['sha']);branch='deep-loop-pilot/'+self.key
            observed=self._call('GET','git/ref/heads/'+branch)
            if observed is None:
                if self._record('ref-intent') is not None:return 'wait_for_trusted_delivery'
                self._save('ref-intent',{'ref':'refs/heads/'+branch,'sha':head})
                self._call('POST','git/refs',{'ref':'refs/heads/'+branch,'sha':head})
                return 'wait_for_trusted_delivery'
            if observed.get('object',{}).get('sha')!=head:raise ValueError('Delivery branch drift; never force update')
            comparison=self._call('GET','compare/'+base+'...'+head)
            if comparison is None:return 'wait_for_trusted_delivery'
            changes=comparison.get('files',[]);commits=comparison.get('commits',[])
            expected_status='modified' if ARTIFACT in verification['baseline'] else 'added'
            if (comparison.get('status')!='ahead' or comparison.get('ahead_by')!=1 or comparison.get('behind_by')!=0 or
                    comparison.get('base_commit',{}).get('sha')!=base or comparison.get('merge_base_commit',{}).get('sha')!=base or
                    len(commits)!=1 or commits[0].get('sha')!=head or len(changes)!=1 or
                    changes[0].get('filename')!=ARTIFACT or changes[0].get('status')!=expected_status or
                    changes[0].get('sha')!=blob['sha'] or changes[0].get('previous_filename') is not None):
                raise ValueError('Published diff differs from frozen single-artifact outcome')
            query=urlencode({'state':'all','head':'marcusgoll:'+branch,'base':delivery['base_ref'],'per_page':100})
            matches=self._call('GET','pulls?'+query)
            if not matches:
                if self._record('pr-intent') is not None:return 'wait_for_trusted_delivery'
                self._save('pr-intent',{'head':branch,'base':delivery['base_ref']})
                response=self._call('POST','pulls',{'head':branch,'base':delivery['base_ref'],
                                    'title':delivery['title'],'body':delivery['body'],'draft':True})
                self._pr(response,head,delivery)
                return 'wait_for_trusted_delivery'
            if len(matches)!=1:raise ValueError('Ambiguous existing pilot PR')
            number=self._pr(matches[0],head,delivery)
            checks=self._call('GET','commits/'+head+'/check-runs?per_page=100')
            qualifying=[]
            for check in checks['check_runs']:
                if check.get('name')=='verify' and check.get('app',{}).get('slug')=='github-actions' and check.get('head_sha')==head:
                    if check.get('status')!='completed':return 'wait_for_trusted_delivery'
                    if check.get('conclusion')!='success':raise ValueError('Required hosted verification failed')
                    match=re.fullmatch(r'https://github\.com/marcusgoll/deep-loop-plugin/actions/runs/(\d+)/job/\d+',check.get('details_url',''))
                    if match:qualifying.append(match.group(1))
            if len(qualifying)!=1:return 'wait_for_trusted_delivery'
            run=self._call('GET','actions/runs/'+qualifying[0])
            if (run.get('head_sha')!=head or run.get('path')!=WORKFLOW or run.get('event')!='pull_request' or
                    run.get('status')!='completed' or run.get('conclusion')!='success'):
                raise ValueError('Hosted verification provenance changed')
            final=self._call('GET','pulls/'+str(number));self._pr(final,head,delivery)
            require_active(self.store, self.key)
            self._accepted_artifact()
            receipt={'contract_digest':self.key,'progress_receipt':progress,'head_sha':head,
                     'base_sha':base,'pull_request':final['html_url'],'workflow_run':int(qualifying[0])}
            if resume_proof is not None:receipt['resume_acceptance_digest']=resume_proof
            previous=self._record('complete')
            if previous is None:self._save('complete',receipt)
            elif previous!=receipt:raise ValueError('Delivery completion drift')
            return 'delivered_verified_draft'
