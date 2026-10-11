"""Incremental complete-candidate draft delivery through trusted provider I/O.

Uses the existing protected store and immutable-intent recovery discipline.
No enrollment, worker activation, checkpoint transition or merge occurs here.
The injected controller/API must be trusted host infrastructure, never candidate
callbacks. Every request checks current authority, full review and source before
and after I/O. Initialization, provider mutations and protected saves also
authenticate the complete retained parent/native history. Read-only responses
never grant durable acceptance on their own.
"""
import base64
from datetime import datetime, timezone
import hashlib
import re
from urllib.parse import urlencode

from admission import digest
from git_candidate_export import GitCandidateExport, git_object
from workflow_delivery_contract import validate_workflow_delivery

WAIT = 'wait_for_workflow_delivery'


def commit_object(capability, tree):
    metadata = capability['commit']
    timestamp = int(datetime.strptime(metadata['date'],'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp())
    identity = f"{metadata['name']} <{metadata['email']}> {timestamp} +0000"
    payload = (f"tree {tree}\nparent {capability['base_sha']}\nauthor {identity}\ncommitter {identity}\n\n" + metadata['message']).encode()
    person = {key:metadata[key] for key in ('name','email','date')}
    body = {'tree':tree,'parents':[capability['base_sha']], 'author':person,'committer':person.copy(),
            'message':metadata['message']}
    return {'sha':git_object('commit',payload),'body':body}


class WorkflowDelivery:
    def __init__(self, controller, api):
        self.controller, self.api = controller, api
        self.store, self.key = controller.store, controller.contract_digest

    def _read(self, suffix):
        try:return self.store.read(self.key+'.workflow-delivery-'+suffix+'.json')
        except FileNotFoundError:return None

    def _fresh(self):
        if self.controller.authenticate_workflow_parent_acceptance() != self.cut:
            raise ValueError('Workflow delivery accepted-parent cut changed')

    def _locked_guard(self):
        # The aggregate reader takes its own non-reentrant locks. Its fresh
        # result is checked again under the credential lock before I/O/write.
        c=self.controller;c._contract();c._workflow_mutation_authority(parent_recovery=True);c._unowned()
        c._require_no_pending_task_acceptance();c._require_no_pending_task_credit()
        authority_reader=getattr(c.workflow_gate,'final_review_authority_cut',None)
        authority_cut=authority_reader() if callable(authority_reader) else None
        if authority_cut is not None and (not isinstance(authority_cut,tuple) or len(authority_cut)!=4):
            raise ValueError('Malformed workflow review authority cut')
        reader=getattr(c.workflow_gate,'final_review_cut',None)
        reviewed=authority_cut[:3] if authority_cut is not None else reader() if callable(reader) else None
        if reviewed is None:
            binding,state,_=c.workflow_gate._read()
            current_proof=c.workflow_gate.final_review_proof()
        else:
            binding,state,current_proof=reviewed
        proof=self.cut['parent_receipt']['postimage_review_proof']
        origin=authority_cut[3] if authority_cut is not None else c.workflow_gate.accepted_parent_image(binding,state)
        current=c._parent_proof_at_checkpoint(current_proof,digest(origin))
        if (digest(binding)!=self.cut['binding_sha256'] or digest(origin)!=proof['checkpoint_sha256'] or
                c.journal.read()[0]!=self.cut['outcome']['journal_revision'] or
                self.store.read(self.key+'.parent-acceptance.json')!=self.cut['parent_receipt'] or
                digest(self.store.read(self.key+'.parent-acceptance-intent.json'))!=self.cut['parent_receipt']['intent_digest'] or
                c._workflow_quiescence()!=self.cut['outcome']['quiescence'] or
                current!=proof):
            raise ValueError('Workflow delivery authority changed before provider operation')
        c._workflow_source_guard(proof,parent_recovery=True)
        if (c.workflow_gate._read()[:2]!=(binding,state) or
                c.journal.read()[0]!=self.cut['outcome']['journal_revision'] or
                c._workflow_quiescence()!=self.cut['outcome']['quiescence']):
            raise ValueError('Workflow delivery cut changed during final source guard')
        c._workflow_mutation_authority(parent_recovery=True)

    def _locked_history_guard(self):
        """Reauthenticate retained chains before direct checkpoint mutations."""
        self._locked_guard()
        c=self.controller;checkpoint=digest(c.workflow_gate._read()[1])
        for expected in self.cut['outcome']['task_histories'].values():
            actual=c._workflow_task_provenance_locked(expected['owner'])
            if actual['checkpoint_sha256']!=checkpoint:
                raise ValueError('Workflow history checkpoint changed before publication')
            projected={k:v for k,v in expected.items() if k!='current_observation'}
            projected.update(kind='historical_workflow_task_provenance',final_proof_verified=False)
            actual={**actual,'checkpoint_sha256':expected['checkpoint_sha256']}
            if actual!=projected:
                raise ValueError('Workflow retained history changed before publication')
        self._locked_guard()

    def _save(self, suffix, value):
        self._fresh()
        with self.store.lock():
            self._locked_guard()
            try:self.store.create(self.key+'.workflow-delivery-'+suffix+'.json',value)
            except FileExistsError:
                if self._read(suffix)!=value:raise ValueError('Workflow delivery protected record drift')
                return False
            if self._read(suffix)!=value:raise ValueError('Workflow delivery record readback differs')
            return True

    def _api(self, method, route, body=None):
        if getattr(self,'_publication_lock',False):
            if method!='GET':raise ValueError('Checkpoint readback cannot mutate provider')
            self._locked_guard();response=self.api(method,route,body);self._locked_guard()
            return response
        # GET cannot publish or seal progress. Its two fresh locked guards
        # authenticate current authority/proof; full historical provenance is
        # still required at initialization and every mutation/save boundary.
        if method != 'GET':self._fresh()
        with self.store.lock():
            self._locked_guard()
            response=self.api(method,route,body)
            self._locked_guard()
            return response

    def _call(self, method, route, body=None):return self._api(method,self.prefix+route,body)

    def _identities(self):
        cap=self.capability
        user=self._api('GET','user')
        repo=self._api('GET',self.prefix.rstrip('/'))
        base=self._call('GET','git/ref/heads/'+cap['base_ref'])
        if (not isinstance(user,dict) or user.get('login')!=cap['publisher'] or user.get('id')!=cap['publisher_id'] or
                not isinstance(repo,dict) or repo.get('id')!=cap['repository_id'] or repo.get('full_name')!=cap['repository'] or
                not isinstance(base,dict) or base.get('object',{}).get('sha')!=cap['base_sha']):
            raise ValueError('Workflow delivery publisher/repository/base drift')

    def _blob(self, row, observed):
        if (not isinstance(observed,dict) or observed.get('sha')!=row['sha'] or observed.get('encoding')!='base64' or
                type(observed.get('size')) is not int or observed['size']!=row['bytes'] or
                not isinstance(observed.get('content'),str) or len(observed['content'])>row['bytes']*2+1024):
            raise ValueError('Incomplete workflow blob readback')
        data=base64.b64decode(''.join(observed['content'].split()),validate=True)
        if len(data)!=row['bytes'] or hashlib.sha256(data).hexdigest()!=row['sha256'] or git_object('blob',data)!=row['sha']:
            raise ValueError('Workflow blob differs from accepted bytes')

    def _tree(self, tree, observed):
        if (not isinstance(observed,dict) or observed.get('sha')!=tree['sha'] or observed.get('truncated') is not False or
                not isinstance(observed.get('tree'),list)):
            raise ValueError('Incomplete workflow tree readback')
        rows=[{'name':row.get('path'),'mode':'40000' if row.get('mode')=='040000' else row.get('mode'),
               'type':row.get('type'),'sha':row.get('sha')} for row in observed['tree'] if isinstance(row,dict)]
        if len(rows)!=len(observed['tree']) or rows!=tree['entries']:
            raise ValueError('Workflow tree differs from complete accepted inventory')

    def _commit(self, expected, observed):
        body=expected['body']
        if (not isinstance(observed,dict) or observed.get('sha')!=expected['sha'] or
                observed.get('tree',{}).get('sha')!=body['tree'] or
                observed.get('parents') is None or [p.get('sha') for p in observed['parents']]!=body['parents'] or
                observed.get('message')!=body['message'] or
                any({k:observed.get(role,{}).get(k) for k in ('name','email','date')}!=body[role] for role in ('author','committer')) or
                observed.get('verification',{}).get('signature') is not None):
            raise ValueError('Workflow commit differs from independently computed identity')

    def _pr(self, pr, head):
        c=self.capability
        number=pr.get('number') if isinstance(pr,dict) else None
        if (type(number) is not int or number<1 or pr.get('state')!='open' or pr.get('draft') is not True or
                pr.get('merged') is True or pr.get('user',{}).get('login')!=c['publisher'] or
                pr['user'].get('id')!=c['publisher_id'] or pr.get('title')!=c['title'] or pr.get('body')!=c['body'] or
                pr.get('html_url')!='https://github.com/'+c['repository']+'/pull/'+str(number)):
            raise ValueError('Workflow draft PR identity drift')
        for side,sha,ref in (('head',head,c['branch']),('base',c['base_sha'],c['base_ref'])):
            row=pr.get(side,{})
            if (row.get('sha')!=sha or row.get('ref')!=ref or row.get('repo',{}).get('id')!=c['repository_id'] or
                    row['repo'].get('full_name')!=c['repository']):
                raise ValueError('Workflow draft PR head/base drift')
        return number

    def _pages(self, route, params):
        rows=[]
        for page in range(1,17):
            observed=self._call('GET',route+'?'+urlencode({**params,'per_page':100,'page':page}))
            # Trusted transport must derive has_next from validated response
            # pagination metadata, never infer it from a shortened body alone.
            if (not isinstance(observed,dict) or set(observed)!={'items','page','per_page','has_next'} or
                    type(observed['page']) is not int or observed['page']!=page or
                    type(observed['per_page']) is not int or observed['per_page']!=100 or
                    type(observed['has_next']) is not bool or not isinstance(observed['items'],list)):
                raise ValueError('Workflow provider pagination metadata unavailable')
            batch=observed['items']
            if len(batch)>100 or observed['has_next'] and not batch:raise ValueError('Malformed workflow provider listing')
            rows.extend(batch)
            if not observed['has_next']:return rows
        raise ValueError('Workflow provider listing exceeds complete bounded readback')

    def _checks(self, head, number):
        rows=[];total=None
        for page in range(1,17):
            batch=self._call('GET',f'commits/{head}/check-runs?per_page=100&page={page}')
            if (not isinstance(batch,dict) or type(batch.get('total_count')) is not int or
                    not 0<=batch['total_count']<=1600 or not isinstance(batch.get('check_runs'),list) or len(batch['check_runs'])>100 or
                    total is not None and total!=batch['total_count']):
                raise ValueError('Incomplete workflow hosted-check listing')
            total=batch['total_count'];rows.extend(batch['check_runs'])
            if len(rows)>=total:break
            if len(batch['check_runs'])<100:raise ValueError('Truncated workflow hosted-check listing')
        if len(rows)!=total or any(not isinstance(row,dict) or type(row.get('id')) is not int or row['id']<1 for row in rows) or len({row['id'] for row in rows})!=len(rows):
            raise ValueError('Incomplete or duplicated workflow check identities')
        result=[];c=self.capability
        for required in c['required_checks']:
            matches=[r for r in rows if r.get('name')==required['name'] and r.get('app',{}).get('id')==required['app_id'] and
                     r['app'].get('slug')==required['app_slug'] and r.get('head_sha')==head]
            if not matches:return None
            if len(matches)!=1:raise ValueError('Ambiguous workflow required check')
            check=matches[0]
            if check.get('status')!='completed':return None
            if check.get('conclusion')!='success':raise ValueError('Workflow required hosted check failed')
            pattern=r'https://github\.com/'+re.escape(c['repository'])+r'/actions/runs/([1-9][0-9]*)/job/[1-9][0-9]*'
            match=re.fullmatch(pattern,check.get('details_url',''))
            if match is None:raise ValueError('Workflow hosted-check provenance unavailable')
            run=self._call('GET','actions/runs/'+match.group(1))
            if (not isinstance(run,dict) or run.get('head_sha')!=head or run.get('head_branch')!=c['branch'] or
                    run.get('path')!=required['workflow_path'] or run.get('event')!=required['event'] or
                    run.get('status')!='completed' or run.get('conclusion')!='success' or
                    any(run.get(field,{}).get('id')!=c['repository_id'] or run[field].get('full_name')!=c['repository']
                        for field in ('repository','head_repository')) or
                    not any(p.get('number')==number and p.get('head',{}).get('sha')==head and
                            p.get('base',{}).get('sha')==c['base_sha'] for p in run.get('pull_requests',[]))):
                raise ValueError('Workflow hosted run provenance drift')
            result.append({'required':required,'check':check,'run':run})
        return result

    def _reviews(self, head, number):
        rows=self._pages(f'pulls/{number}/reviews',{})
        if any(not isinstance(row,dict) or type(row.get('id')) is not int or row['id']<1 for row in rows) or len({r['id'] for r in rows})!=len(rows):
            raise ValueError('Malformed or duplicated workflow review listing')
        result=[]
        for required in self.capability['required_reviews']:
            decisions=[r for r in rows if r.get('user',{}).get('id')==required['id'] and
                       r['user'].get('login')==required['login'] and r.get('state') in {'APPROVED','CHANGES_REQUESTED','DISMISSED'}]
            if not decisions:return None
            latest=max(decisions,key=lambda r:r['id'])
            if latest.get('state')!='APPROVED' or latest.get('commit_id')!=head:return None
            result.append({'required':required,'review':latest})
        return result

    def _initialize(self):
        self.cut=self.controller.authenticate_workflow_parent_acceptance()
        binding=self.store.read(self.key+'.workflow.json')
        if binding.get('schema')!=4 or digest(binding)!=self.cut['binding_sha256']:
            raise ValueError('Explicit workflow delivery capability required')
        self.capability=validate_workflow_delivery(binding['workflow_delivery'],self.key)
        self.prefix='repos/'+self.capability['repository']+'/'
        source=self.cut['parent_receipt']['postimage_review_proof']['candidate_source']
        exporter=GitCandidateExport(source['policy'],source['snapshot'],self.capability['export_rules'])
        export=exporter.plan();commit=commit_object(self.capability,export['tree_sha'])
        plan={'cut':self.cut,'capability':self.capability,'export':export,'commit':commit}
        self.plan=plan;self.exporter=exporter
        return plan,export

    def step(self):
        plan,export=self._initialize();commit=plan['commit']
        saved=self._read('plan')
        if saved is None:self._save('plan',plan);return WAIT
        if saved!=plan:raise ValueError('Saved workflow delivery plan drift')
        self._identities()
        unique={row['sha']:row for row in export['files']}
        for sha,row in unique.items():
            sealed=self._read('blob-'+sha)
            if sealed is not None:
                if sealed!=row:raise ValueError('Protected workflow blob record drift')
                continue
            observed=self._call('GET','git/blobs/'+sha)
            if observed is None:
                data=self.exporter.read_blob(export,sha)
                response=self._call('POST','git/blobs',{'content':base64.b64encode(data).decode(),'encoding':'base64'})
                if response.get('sha')!=sha:raise ValueError('Published workflow blob identity drift')
                observed=self._call('GET','git/blobs/'+sha)
            self._blob(row,observed);self._save('blob-'+sha,row);return WAIT
        for tree in export['trees']:
            sealed=self._read('tree-'+tree['sha'])
            if sealed is not None:
                if sealed!=tree:raise ValueError('Protected workflow tree record drift')
                continue
            observed=self._call('GET','git/trees/'+tree['sha'])
            if observed is None:
                body={'tree':[{'path':r['name'],'mode':'040000' if r['mode']=='40000' else r['mode'],
                               'type':r['type'],'sha':r['sha']} for r in tree['entries']]}
                response=self._call('POST','git/trees',body)
                if response.get('sha')!=tree['sha']:raise ValueError('Published workflow tree identity drift')
                observed=self._call('GET','git/trees/'+tree['sha'])
            self._tree(tree,observed);self._save('tree-'+tree['sha'],tree);return WAIT
        sealed=self._read('commit')
        if sealed is not None and sealed!=commit:
            raise ValueError('Protected workflow commit record drift')
        head=commit['sha'];observed=self._call('GET','git/commits/'+head)
        if observed is None:
            response=self._call('POST','git/commits',commit['body'])
            if response.get('sha')!=head:raise ValueError('Published workflow commit identity drift')
            observed=self._call('GET','git/commits/'+head)
        self._commit(commit,observed)
        if sealed is None:
            # Finish immutable commit publication in its own durable wake.
            # Later wakes still read and authenticate the provider commit;
            # this record never substitutes for fresh remote verification.
            self._save('commit',commit);return WAIT
        branch=self.capability['branch'];ref=self._call('GET','git/ref/heads/'+branch)
        if ref is None:
            if not self._save('ref-intent',{'ref':'refs/heads/'+branch,'sha':head,'plan_sha256':digest(plan)}):return WAIT
            self._call('POST','git/refs',{'ref':'refs/heads/'+branch,'sha':head});return WAIT
        if ref.get('object',{}).get('sha')!=head:raise ValueError('Workflow branch drift; never force update')
        matches=self._pages('pulls',{'state':'all','head':self.capability['repository'].split('/')[0]+':'+branch,'base':self.capability['base_ref']})
        if not matches:
            body={k:self.capability[k] for k in ('title','body')};body.update(head=branch,base=self.capability['base_ref'],draft=True)
            if not self._save('pr-intent',{'body':body,'head_sha':head,'plan_sha256':digest(plan)}):return WAIT
            self._pr(self._call('POST','pulls',body),head);return WAIT
        if len(matches)!=1:raise ValueError('Ambiguous workflow draft PR listing')
        number=self._pr(matches[0],head)
        receipt=self._verified_receipt(plan,export,number)
        if receipt is None:return WAIT
        self._save('complete',receipt)
        return 'workflow_delivery_verified'


    def _verified_receipt(self,plan,export,number):
        unique={row['sha']:row for row in export['files']}
        head=plan['commit']['sha'];branch=self.capability['branch']
        # Reinspect every content-addressed object, including unchanged files.
        for sha,row in unique.items():self._blob(row,self._call('GET','git/blobs/'+sha))
        for tree in export['trees']:self._tree(tree,self._call('GET','git/trees/'+tree['sha']))
        checks=self._checks(head,number);reviews=self._reviews(head,number)
        if checks is None or reviews is None:return None
        self._identities();self._pr(self._call('GET','pulls/'+str(number)),head)
        ref=self._call('GET','git/ref/heads/'+branch)
        if ref is None or ref.get('object',{}).get('sha')!=head:raise ValueError('Workflow final branch drift')
        if self._checks(head,number)!=checks or self._reviews(head,number)!=reviews:
            raise ValueError('Workflow required acceptance changed during final readback')
        # Acceptance requests are provider operations too. Inspect the endpoint
        # after those requests so their side effects cannot leave a stale PR/ref
        # observation at the completion boundary.
        self._identities()
        ref=self._call('GET','git/ref/heads/'+branch)
        if ref is None or ref.get('object',{}).get('sha')!=head:raise ValueError('Workflow completion branch drift')
        self._pr(self._call('GET','pulls/'+str(number)),head)
        receipt={'contract_digest':self.key,'plan_sha256':digest(plan),'parent_receipt_sha256':self.cut['parent_receipt_sha256'],
                 'export_sha256':export['manifest_sha256'],'candidate_snapshot_sha256':export['candidate_snapshot_sha256'],
                 'journal_revision':self.cut['outcome']['journal_revision'],'head_sha':head,'base_sha':self.capability['base_sha'],
                 'pull_request':'https://github.com/'+self.capability['repository']+'/pull/'+str(number),
                 'checks':checks,'reviews':reviews,'delivery_verified':True,'complete':False}
        return receipt

    def authenticate_delivery(self, *, locked=False):
        """Fresh complete GET-only readback; never create a missing endpoint."""
        if locked:
            plan=self.plan;export=plan['export'];self._locked_guard()
        else:plan,export=self._initialize()
        if self._read('plan')!=plan:raise ValueError('Saved workflow delivery plan drift')
        previous=getattr(self,'_publication_lock',False);self._publication_lock=locked
        try:
            self._identities();head=plan['commit']['sha'];branch=self.capability['branch']
            self._commit(plan['commit'],self._call('GET','git/commits/'+head))
            ref=self._call('GET','git/ref/heads/'+branch)
            if ref is None or ref.get('object',{}).get('sha')!=head:
                raise ValueError('Workflow read-only branch unavailable or changed')
            matches=self._pages('pulls',{'state':'all','head':self.capability['repository'].split('/')[0]+':'+branch,
                                        'base':self.capability['base_ref']})
            if len(matches)!=1:raise ValueError('Workflow read-only PR unavailable or ambiguous')
            number=self._pr(matches[0],head)
            return self._verified_receipt(plan,export,number)
        finally:self._publication_lock=previous
