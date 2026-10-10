"""Root private publisher transport bound to an enrolled workflow delivery plan.

Uses existing private publisher authentication without exporting credentials.
Caller is the trusted adapter holding its credential lock. No auth changes,
enrollment, arbitrary URLs, force updates or pagination URL following occur.
Link semantics: https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api
"""
import base64
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import selectors
import signal
import tempfile
import time
from urllib.parse import parse_qs, urlencode, urlsplit

from admission import digest
from github_transport import UncertainAPI
from git_candidate_export import GitCandidateExport, git_object
from workflow_delivery import WorkflowDelivery, commit_object
from workflow_delivery_contract import validate_workflow_delivery

API_VERSION = '2026-03-10'


def pagination(route, headers, repository, repository_id):
    path, separator, query = route.partition('?')
    params=parse_qs(query,keep_blank_values=True,strict_parsing=True,max_num_fields=12)
    if (not separator or params.get('per_page')!=['100'] or len(params.get('page',[]))!=1 or
            re.fullmatch(r'[1-9][0-9]*',params['page'][0]) is None or
            any(len(values)!=1 for values in params.values())):
        raise ValueError('Exact workflow pagination request required')
    page=int(params['page'][0]);links={}
    value=headers.get('link')
    if value is not None:
        if not value or len(value)>8192:raise ValueError('Malformed workflow pagination header')
        for entry in value.split(','):
            match=re.fullmatch(r'\s*<([^<>\s]+)>;\s*rel="(next|prev|first|last)"\s*',entry)
            if match is None or match[2] in links:raise ValueError('Malformed or duplicate workflow page relation')
            target=urlsplit(match[1]);relation=match[2]
            suffix=path.removeprefix('repos/'+repository)
            allowed_paths={'/'+path,'/repositories/'+str(repository_id)+suffix}
            if (target.scheme!='https' or target.netloc!='api.github.com' or target.fragment or
                    target.path not in allowed_paths):
                raise ValueError('Foreign workflow pagination target')
            linked=parse_qs(target.query,keep_blank_values=True,strict_parsing=True,max_num_fields=12)
            if (set(linked)!=set(params) or any(len(v)!=1 for v in linked.values()) or
                    re.fullmatch(r'[1-9][0-9]*',linked.get('page',[''])[0]) is None or
                    any(linked[k]!=v for k,v in params.items() if k!='page')):
                raise ValueError('Workflow pagination filters changed')
            number=int(linked['page'][0])
            if (relation=='next' and number!=page+1 or relation=='prev' and number!=page-1 or
                    relation=='first' and number!=1 or relation=='last' and number<page):
                raise ValueError('Workflow pagination sequence changed')
            links[relation]=number
        if ('next' in links and 'last' in links and links['last']<links['next'] or
                'last' in links and links['last']>page and 'next' not in links):
            raise ValueError('Contradictory workflow page relations')
    return {'page':page,'per_page':100,'has_next':'next' in links}


def bounded_run(args, *, input=None, timeout=3):
    """Drain both pipes incrementally; kill the child before retaining excess output."""
    limit=2*1024*1024
    with tempfile.TemporaryFile() as request:
        if input is not None:request.write(input.encode())
        request.seek(0)
        with subprocess.Popen(args,stdin=request,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True) as process:
            buffers={process.stdout:bytearray(),process.stderr:bytearray()}
            deadline=time.monotonic()+timeout
            try:
                with selectors.DefaultSelector() as selector:
                    for pipe in buffers:
                        os.set_blocking(pipe.fileno(),False);selector.register(pipe,selectors.EVENT_READ)
                    while selector.get_map():
                        remaining=deadline-time.monotonic()
                        if remaining<=0:raise subprocess.TimeoutExpired(args,timeout)
                        for key,_ in selector.select(remaining):
                            chunk=os.read(key.fileobj.fileno(),65536)
                            if not chunk:selector.unregister(key.fileobj);continue
                            if len(buffers[key.fileobj])+len(chunk)>limit:
                                raise ValueError('Oversized workflow GitHub output')
                            buffers[key.fileobj].extend(chunk)
                remaining=deadline-time.monotonic()
                if remaining<=0:raise subprocess.TimeoutExpired(args,timeout)
                process.wait(timeout=remaining)
            except BaseException:
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                process.wait();raise
            return subprocess.CompletedProcess(args,process.returncode,
                buffers[process.stdout].decode(),buffers[process.stderr].decode())


class WorkflowGitHubAPI:
    def __init__(self, controller):
        self.controller=controller;self.store=controller.store;self.key=controller.contract_digest
        binding=self.store.read(self.key+'.workflow.json')
        if binding.get('schema')!=4:raise ValueError('Explicit full workflow transport enrollment required')
        self.binding_digest=digest(binding)
        self.capability=copy.deepcopy(validate_workflow_delivery(binding['workflow_delivery'],self.key))
        self.prefix='repos/'+self.capability['repository']

    def _authority(self):
        if os.geteuid()!=0 or sys.platform!='linux' or self.store.owner_uid!=0:
            raise ValueError('Root private Linux workflow transport required')
        binding=self.store.read(self.key+'.workflow.json')
        plan=self.store.read(self.key+'.workflow-delivery-plan.json')
        if (digest(binding)!=self.binding_digest or binding.get('schema')!=4 or
                validate_workflow_delivery(binding['workflow_delivery'],self.key)!=self.capability or
                plan['capability']!=self.capability or plan['cut']['binding_sha256']!=self.binding_digest):
            raise ValueError('Enrolled workflow transport authority drift')
        guard=WorkflowDelivery(self.controller,None);guard.cut=plan['cut'];guard._locked_guard()
        source=plan['cut']['parent_receipt']['postimage_review_proof']['candidate_source']
        export=GitCandidateExport(source['policy'],source['snapshot'],self.capability['export_rules']).plan()
        if plan!={'cut':plan['cut'],'capability':self.capability,'export':export,
                  'commit':commit_object(self.capability,export['tree_sha'])}:
            raise ValueError('Workflow transport export plan drift')
        return plan

    def _route(self,method,route,data,plan):
        p=re.escape(self.prefix);cap=self.capability
        reads=[r'user',p,p+r'/git/ref/heads/'+re.escape(cap['base_ref']),
               p+r'/git/ref/heads/'+re.escape(cap['branch']),p+r'/git/(?:blobs|trees|commits)/[0-9a-f]{40}',
               p+r'/actions/runs/[1-9][0-9]*',p+r'/pulls/[1-9][0-9]*']
        paged=[]
        for page in range(1,17):
            params={'state':'all','head':cap['repository'].split('/')[0]+':'+cap['branch'],
                    'base':cap['base_ref'],'per_page':100,'page':page}
            paged.append(re.escape(self.prefix+'/pulls?'+urlencode(params)))
        paged.extend([p+r'/pulls/[1-9][0-9]*/reviews\?per_page=100&page=(?:[1-9]|1[0-6])',
                      p+r'/commits/[0-9a-f]{40}/check-runs\?per_page=100&page=(?:[1-9]|1[0-6])'])
        if method=='GET':
            if data is not None:raise ValueError('Unexpected workflow read payload')
            if any(re.fullmatch(pattern,route) for pattern in paged):return True
            if any(re.fullmatch(pattern,route) for pattern in reads):return False
            raise ValueError('Unapproved workflow publisher read')
        if method!='POST' or not isinstance(data,dict):raise ValueError('Unapproved workflow publisher write')
        suffix=route.removeprefix(self.prefix+'/')
        if route!=self.prefix+'/'+suffix:raise ValueError('Foreign workflow publisher write')
        if suffix=='git/blobs' and set(data)=={'content','encoding'} and data['encoding']=='base64' and isinstance(data['content'],str):
            maximum=max((row['bytes'] for row in plan['export']['files']),default=0)
            if len(data['content'])>maximum*2+1024:raise ValueError('Oversized workflow blob request')
            payload=base64.b64decode(data['content'],validate=True);identity=git_object('blob',payload)
            if not any(row['sha']==identity and row['bytes']==len(payload) and row['sha256']==hashlib.sha256(payload).hexdigest()
                       for row in plan['export']['files']):raise ValueError('Blob outside exact workflow export')
        elif suffix=='git/trees':
            expected=[{'tree':[{'path':r['name'],'mode':'040000' if r['mode']=='40000' else r['mode'],
                               'type':r['type'],'sha':r['sha']} for r in tree['entries']]} for tree in plan['export']['trees']]
            if data not in expected:raise ValueError('Tree outside exact workflow export')
        elif suffix=='git/commits':
            if data!=plan['commit']['body']:raise ValueError('Commit outside exact workflow export')
        elif suffix=='git/refs':
            expected={'ref':'refs/heads/'+cap['branch'],'sha':plan['commit']['sha']}
            intent=self.store.read(self.key+'.workflow-delivery-ref-intent.json')
            if data!=expected or intent!={**expected,'plan_sha256':digest(plan)}:
                raise ValueError('Exact protected workflow ref intent required')
        elif suffix=='pulls':
            expected={k:cap[k] for k in ('title','body')};expected.update(head=cap['branch'],base=cap['base_ref'],draft=True)
            intent=self.store.read(self.key+'.workflow-delivery-pr-intent.json')
            if data!=expected or intent!={'body':expected,'head_sha':plan['commit']['sha'],'plan_sha256':digest(plan)}:
                raise ValueError('Exact protected workflow PR intent required')
        else:raise ValueError('Unapproved workflow publisher write')
        return False

    def __call__(self,method,route,data=None):
        plan=self._authority();paged=self._route(method,route,data,plan)
        args=['/usr/sbin/runuser','-u','orchestrator','--','/usr/bin/env',
              '-u','GH_TOKEN','-u','GITHUB_TOKEN','-u','GH_ENTERPRISE_TOKEN','-u','GITHUB_ENTERPRISE_TOKEN',
              '-u','GH_HOST','-u','GH_CONFIG_DIR','--chdir=/home/orchestrator','/usr/bin/gh','api',
              '--hostname','github.com','--include','--header','X-GitHub-Api-Version: '+API_VERSION,'--method',method,route]
        payload=None
        if method=='POST':args+=['--input','-'];payload=json.dumps(data,allow_nan=False)
        self._authority()
        try:result=bounded_run(args,input=payload,timeout=3)
        except (subprocess.TimeoutExpired,OSError) as exc:raise UncertainAPI('Workflow GitHub response unavailable') from exc
        if len(result.stdout.encode())>2*1024*1024:raise ValueError('Oversized workflow GitHub response')
        header,separator,body=result.stdout.replace('\r\n','\n').partition('\n\n')
        lines=header.split('\n');status=re.fullmatch(r'HTTP/\S+ (\d{3})(?: [^\r\n]*)?',lines[0])
        if not separator or status is None:raise UncertainAPI('Workflow GitHub response headers unavailable')
        headers={}
        for line in lines[1:]:
            name,colon,value=line.partition(':')
            if not colon or re.fullmatch(r'[A-Za-z0-9-]+',name) is None or name.lower() in headers:
                raise ValueError('Malformed or duplicated workflow GitHub header')
            headers[name.lower()]=value.strip()
        code=int(status[1]);self._authority()
        if method=='GET' and code==404:return None
        if result.returncode!=0 or not 200<=code<300:raise UncertainAPI('Workflow GitHub operation did not confirm success')
        observed=json.loads(body)
        if paged:
            metadata=pagination(route,headers,self.capability['repository'],self.capability['repository_id'])
            if '/check-runs?' in route:
                if (not isinstance(observed,dict) or type(observed.get('total_count')) is not int or
                        not isinstance(observed.get('check_runs'),list) or not 0<=observed['total_count']<=1600 or
                        len(observed['check_runs'])!=min(100,max(0,observed['total_count']-(metadata['page']-1)*100)) or
                        metadata['has_next']!=(observed['total_count']>metadata['page']*100)):
                    raise ValueError('Workflow check listing contradicts pagination headers')
                return observed
            if not isinstance(observed,list) or len(observed)>100 or metadata['has_next'] and not observed:
                raise ValueError('Malformed workflow paginated response')
            return {'items':observed,**metadata}
        if 'link' in headers:raise ValueError('Unexpected pagination on bounded workflow object read')
        return observed
