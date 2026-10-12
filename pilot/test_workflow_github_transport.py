import copy
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode
import unittest
from unittest.mock import patch
import subprocess

from admission import digest
from github_transport import UncertainAPI
import test_workflow_delivery as fixtures
from workflow_delivery import WorkflowDelivery
from workflow_github_transport import WorkflowGitHubAPI,pagination,API_VERSION,bounded_run


class RootStoreProxy:
    """Mock root ownership only; actual fixture files retain their real owner."""
    owner_uid=0
    def __init__(self,store):self.store=store
    def __getattr__(self,name):return getattr(self.store,name)


class WorkflowGitHubTransportTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.WorkflowDeliveryTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.fixture.adapter.step()  # literal plan only; no provider I/O
        self.controller=copy.copy(self.fixture.controller);self.controller.store=RootStoreProxy(self.fixture.controller.store)
        self.transport=WorkflowGitHubAPI(self.controller);self.cap=self.transport.capability;self.prefix=self.transport.prefix
        self.output='HTTP/2 200\ncontent-type: application/json\n\n[]';self.returncode=0
        for target,value in [('workflow_github_transport.os.geteuid',0),('workflow_github_transport.sys.platform','linux')]:
            p=patch(target,return_value=value) if target.endswith('geteuid') else patch(target,value)
            p.start();self.addCleanup(p.stop)
        self.native=patch('workflow_github_transport.bounded_run',side_effect=self.response).start();self.addCleanup(patch.stopall)
    def response(self,args,**kwargs):return SimpleNamespace(stdout=self.output,stderr='never exported',returncode=self.returncode)
    def list_route(self,page=1):
        return self.prefix+'/pulls?'+urlencode({'state':'all','head':self.cap['repository'].split('/')[0]+':'+self.cap['branch'],
                       'base':self.cap['base_ref'],'per_page':100,'page':page})
    def link(self,page,relation='next',*,alias=False):
        route=self.list_route(page)
        if alias:route=route.replace(self.prefix,'repositories/'+str(self.cap['repository_id']),1)
        return '<https://api.github.com/'+route+'>; rel="'+relation+'"'
    def test_named_and_repository_id_links_preserve_complete_page_metadata(self):
        for alias in (False,True):
            self.output='HTTP/2 200\nlink: '+self.link(2,alias=alias)+'\n\n'+json.dumps([{'fixture':'one row despite next link'}])
            self.assertEqual(self.transport('GET',self.list_route()),{'items':[{'fixture':'one row despite next link'}],
                             'page':1,'per_page':100,'has_next':True})
        self.output='HTTP/2 200\nlink: '+self.link(1,'prev')+'\n\n[]'
        self.assertEqual(self.transport('GET',self.list_route(2)),{'items':[],'page':2,'per_page':100,'has_next':False})
    def test_missing_link_means_last_page_without_body_length_inference(self):
        self.output='HTTP/2 200\n\n'+json.dumps([{}]*100)
        result=self.transport('GET',self.list_route());self.assertFalse(result['has_next']);self.assertEqual(len(result['items']),100)
    def test_foreign_target_filter_changes_duplicate_relations_and_page_jumps_reject(self):
        good=self.link(2)
        for link in (good.replace('api.github.com','evil.example'),good.replace('repositories/123','repositories/999').replace(self.prefix,'repos/foreign/repo'),
                     good.replace('page=2','page=3'),good.replace('per_page=100','per_page=30'),good+', '+good,
                     good.replace('https://','http://'),good.replace('rel="next"','rel="other"'),
                     good.replace('api.github.com/','api.github.com:443/')):
            with self.subTest(link=link):
                self.output='HTTP/2 200\nlink: '+link+'\n\n[]'
                with self.assertRaises(ValueError):self.transport('GET',self.list_route())
    def test_future_last_without_next_rejects_in_helper_and_transport(self):
        link=self.link(3,'last')
        with self.assertRaisesRegex(ValueError,'Contradictory'):
            pagination(self.list_route(),{'link':link},self.cap['repository'],self.cap['repository_id'])
        self.output='HTTP/2 200\nlink: '+link+'\n\n[]'
        with self.assertRaisesRegex(ValueError,'Contradictory'):self.transport('GET',self.list_route())
    def test_route_allowlist_rejects_foreign_targets_filters_methods_and_pages(self):
        before=self.native.call_count
        for method,route in [('GET','repos/foreign/repo'),('GET',self.prefix+'/pulls?state=open'),
                             ('GET',self.list_route(17)),('PATCH',self.prefix+'/git/refs'),
                             ('POST',self.prefix+'/issues'),('GET','https://api.github.com/user')]:
            with self.subTest(method=method,route=route),self.assertRaises(ValueError):self.transport(method,route)
        self.assertEqual(self.native.call_count,before)
    def test_read_requests_cannot_carry_payloads(self):
        with self.assertRaisesRegex(ValueError,'read payload'):self.transport('GET','user',{})
        self.native.assert_not_called()
    def test_subprocess_has_fixed_publisher_hostname_version_and_no_token_export(self):
        self.output='HTTP/2 200\n\n{}';self.transport('GET','user')
        args=self.native.call_args.args[0];options=self.native.call_args.kwargs
        self.assertEqual(args[:4],['/usr/sbin/runuser','-u','orchestrator','--'])
        self.assertIn('X-GitHub-Api-Version: '+API_VERSION,args);self.assertIn('--chdir=/home/orchestrator',args)
        self.assertEqual(args[args.index('--hostname')+1],'github.com');self.assertEqual(options['timeout'],3)
        for variable in ('GH_TOKEN','GITHUB_TOKEN','GH_HOST','GH_CONFIG_DIR'):self.assertIn(variable,args)
        self.assertNotIn('--paginate',args);self.assertIsNone(options['input'])
    def test_expiry_revocation_source_and_binding_drift_block_before_io(self):
        original=self.controller.store.read(self.controller.contract_digest+'.workflow.json')
        self.controller.active=False
        with self.assertRaises(ValueError):self.transport('GET','user')
        self.controller.active=True
        name=self.controller.contract_digest+'.workflow.json';self.controller.store.remove(name)
        changed={**original,'extra':'drift'};self.controller.store.create(name,changed)
        with self.assertRaises(ValueError):self.transport('GET','user')
        self.controller.store.remove(name);self.controller.store.create(name,original)
        name=self.controller.contract_digest+'.revocation-intent.json';self.controller.store.create(name,{})
        with self.assertRaises(ValueError):self.transport('GET','user')
        self.controller.store.remove(name);(self.controller.candidate/'source.txt').write_text('drift')
        with self.assertRaises(ValueError):self.transport('GET','user')
        self.native.assert_not_called()
    def test_account_ownership_and_nonroot_block_before_io(self):
        self.controller.owned=True
        with self.assertRaises(ValueError):self.transport('GET','user')
        self.controller.owned=False
        with patch('workflow_github_transport.os.geteuid',return_value=1000):
            with self.assertRaisesRegex(ValueError,'Root private'):self.transport('GET','user')
        self.native.assert_not_called()
    def test_post_response_source_drift_cannot_return_success(self):
        def changed(*args,**kwargs):
            result=self.response(*args,**kwargs);(self.controller.candidate/'source.txt').write_text('mid-response drift');return result
        self.native.side_effect=changed
        with self.assertRaises(ValueError):self.transport('GET','user')
    def test_uncertain_malformed_duplicate_and_oversized_responses_fail_closed(self):
        for response,code,error in [('HTTP/2 503\n\n{}',1,UncertainAPI),('missing headers',0,UncertainAPI),
                                    ('HTTP/2 200\nlink: a\nLink: b\n\n[]',0,ValueError),
                                    ('HTTP/2 200\n\n'+' '*2097153,0,ValueError)]:
            self.output=response;self.returncode=code
            with self.subTest(response=response[:40]),self.assertRaises(error):self.transport('GET','user')
        self.native.side_effect=subprocess.TimeoutExpired('fixture',3)
        with self.assertRaises(UncertainAPI):self.transport('GET','user')
    def test_check_total_count_and_link_metadata_must_agree(self):
        route=self.prefix+'/commits/'+'a'*40+'/check-runs?per_page=100&page=1'
        self.output='HTTP/2 200\n\n'+json.dumps({'total_count':101,'check_runs':[{}]*100})
        with self.assertRaisesRegex(ValueError,'contradicts'):self.transport('GET',route)
        link='<https://api.github.com/'+route.replace('&page=1','&page=2')+'>; rel="next"'
        self.output='HTTP/2 200\nlink: '+link+'\n\n'+json.dumps({'total_count':101,'check_runs':[{}]*100})
        self.assertEqual(self.transport('GET',route)['total_count'],101)
    def test_mutable_writes_require_exact_protected_intents_and_never_force(self):
        plan=self.controller.store.read(self.controller.contract_digest+'.workflow-delivery-plan.json')
        ref={'ref':'refs/heads/'+self.cap['branch'],'sha':plan['commit']['sha']}
        with self.assertRaises(FileNotFoundError):self.transport('POST',self.prefix+'/git/refs',ref)
        self.controller.store.create(self.controller.contract_digest+'.workflow-delivery-ref-intent.json',{**ref,'plan_sha256':digest(plan)})
        self.output='HTTP/2 201\n\n{}';self.transport('POST',self.prefix+'/git/refs',ref)
        for data in ({**ref,'force':True},{**ref,'sha':'c'*40}):
            with self.assertRaises(ValueError):self.transport('POST',self.prefix+'/git/refs',data)
        pr={k:self.cap[k] for k in ('title','body')};pr.update(head=self.cap['branch'],base=self.cap['base_ref'],draft=True)
        with self.assertRaises(FileNotFoundError):self.transport('POST',self.prefix+'/pulls',pr)
        self.controller.store.create(self.controller.contract_digest+'.workflow-delivery-pr-intent.json',{'body':pr,'head_sha':plan['commit']['sha'],'plan_sha256':digest(plan)})
        self.transport('POST',self.prefix+'/pulls',pr)
        with self.assertRaises(ValueError):self.transport('POST',self.prefix+'/pulls',{**pr,'draft':False})
    def test_immutable_writes_cannot_upload_foreign_blob_tree_or_commit(self):
        import base64
        plan=self.controller.store.read(self.controller.contract_digest+'.workflow-delivery-plan.json')
        self.output='HTTP/2 201\n\n{}'
        source=(self.controller.candidate/'source.txt').read_bytes()
        self.transport('POST',self.prefix+'/git/blobs',{'content':base64.b64encode(source).decode(),'encoding':'base64'})
        self.transport('POST',self.prefix+'/git/commits',plan['commit']['body'])
        for suffix,data in [('git/blobs',{'content':base64.b64encode(b'foreign').decode(),'encoding':'base64'}),
                            ('git/trees',{'base_tree':'a'*40,'tree':[]}),('git/commits',{**plan['commit']['body'],'parents':['c'*40]})]:
            with self.subTest(suffix=suffix),self.assertRaises(ValueError):self.transport('POST',self.prefix+'/'+suffix,data)
    def test_adapter_and_transport_converge_through_mocked_http_only(self):
        provider=self.fixture.provider
        def native(args,**kwargs):
            index=args.index('--method');method,route=args[index+1:index+3]
            body=json.loads(kwargs['input']) if kwargs['input'] is not None else None
            result=provider.api(method,route,body)
            code=404 if result is None else 201 if method=='POST' else 200
            if isinstance(result,dict) and set(result)=={'items','page','per_page','has_next'}:
                self.assertFalse(result['has_next']);result=result['items']
            return SimpleNamespace(stdout=f'HTTP/2 {code}\n\n'+json.dumps(result),returncode=1 if code==404 else 0,stderr='')
        self.native.side_effect=native;adapter=WorkflowDelivery(self.controller,self.transport)
        for _ in range(20):
            if adapter.step()=='workflow_delivery_verified':break
        else:self.fail('Mocked HTTP adapter failed to converge')
        self.assertTrue(adapter._read('complete')['delivery_verified']);self.assertFalse(adapter._read('complete')['complete'])

if __name__=='__main__':unittest.main()


class BoundedCaptureTests(unittest.TestCase):
    def test_real_child_stdout_and_stderr_are_stopped_at_limit(self):
        import sys
        for descriptor in (1,2):
            with self.subTest(descriptor=descriptor),self.assertRaisesRegex(ValueError,'Oversized'):
                bounded_run([sys.executable,'-c',
                    'import os,time; os.write('+str(descriptor)+',b"x"*3000000); time.sleep(30)'],timeout=2)
    def test_real_child_timeout_and_normal_output(self):
        import sys
        result=bounded_run([sys.executable,'-c','print("bounded")'])
        self.assertEqual(result.stdout,'bounded\n');self.assertEqual(result.returncode,0)
        with self.assertRaises(subprocess.TimeoutExpired):
            bounded_run([sys.executable,'-c','import time; time.sleep(30)'],timeout=.1)

    def test_timeout_stops_owned_descendant_before_it_can_write(self):
        import sys,tempfile,time
        with tempfile.TemporaryDirectory() as directory:
            marker=Path(directory)/'descendant-write'
            child='import time; from pathlib import Path; time.sleep(.4); Path('+repr(str(marker))+').write_text("escaped")'
            parent='import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",'+repr(child)+']); time.sleep(30)'
            with self.assertRaises(subprocess.TimeoutExpired):
                bounded_run([sys.executable,'-c',parent],timeout=.15)
            time.sleep(.5)
            self.assertFalse(marker.exists())
