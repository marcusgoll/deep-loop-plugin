import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from pinned_helper import PinnedHelper,BoundPinnedHelper,PairedReviewWorkerError


@unittest.skipUnless(sys.platform=='linux','Production helper requires Linux runtime')
class PinnedHelperTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.files={}
        for name,text in [('skills/deep-loop/scripts/deep_loop.py',"import os\ndef task_records(state):return [state,os.environ['DEEP_LOOP_SKILLS_ROOT'],'OPENAI_API_KEY' in os.environ]\n"),
                          ('skills/deep-loop/scripts/proof_binding.py',''),
                          ('skills/verification-contract/scripts/validate_contract.py','')]:
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
            self.files[name]=hashlib.sha256(p.read_bytes()).hexdigest()
        for directory in self.root.rglob('*'):
            if directory.is_dir():directory.chmod(0o755)
            else:directory.chmod(0o644)
        python=Path('/usr/bin/python3').resolve()
        self.config={'root':str(self.root),'files':self.files,'python':{'path':str(python),'sha256':hashlib.sha256(python.read_bytes()).hexdigest()}}
        self.helper=PinnedHelper(self.config,owner_uid=os.getuid())
    def test_isolated_helper_ignores_inherited_import_and_skill_overrides(self):
        with patch.dict(os.environ,{'PYTHONPATH':'/evil','DEEP_LOOP_SKILLS_ROOT':'/evil','OPENAI_API_KEY':'fixture-never-forward'}):
            self.assertEqual(self.helper.task_records({'fixture':True}),[{'fixture':True},str(self.root/'skills'),False])
    def test_verification_methods_cross_real_isolated_proxy(self):
        p=self.root/'skills/deep-loop/scripts/deep_loop.py'
        p.write_text("def contract_semantics_sha256(contract):return contract['fixture_hash']\ndef verification_definitions(state,ids):return [state,ids]\ndef verified_check_state(state,verifier_id,receipt,evidence,expected):return [state,verifier_id,receipt,evidence,expected]\n")
        self.files[str(p.relative_to(self.root))]=hashlib.sha256(p.read_bytes()).hexdigest()
        state={'fixture':True};receipt={'path':'fixture.json','sha256':'a'*64}
        self.assertEqual(self.helper.contract_semantics_sha256({'fixture_hash':'c'*64}),'c'*64)
        self.assertEqual(self.helper.verification_definitions(state,['V1']),[state,['V1']])
        self.assertEqual(self.helper.verified_check_state(state,'V1',receipt,'fixture evidence','b'*64),
                         [state,'V1',receipt,'fixture evidence','b'*64])

    def test_full_validation_proxy_preserves_archive_path_and_missing_api_blocks(self):
        with self.assertRaisesRegex(ValueError,'unavailable or failed'):
            self.helper.validation_issues({'schemaVersion':2},'review')
        p=self.root/'skills/deep-loop/scripts/deep_loop.py'
        p.write_text("from pathlib import Path\ndef validation_issues(state,stage,archive=None):\n assert archive is None or isinstance(archive,Path)\n return [state,stage,str(archive) if archive is not None else None]\n")
        self.files[str(p.relative_to(self.root))]=hashlib.sha256(p.read_bytes()).hexdigest()
        self.assertEqual(self.helper.validation_issues({'schemaVersion':2},'ship',self.root),
                         [{'schemaVersion':2},'ship',str(self.root)])
        self.assertEqual(self.helper.validation_issues({},'review'),[{},'review',None])

    def test_terminal_derivation_proxy_keeps_archive_paths_and_missing_methods_block(self):
        for operation in (lambda:self.helper.completed_state({}),lambda:self.helper.verified_delivery_state({},'a'*40,'readback')):
            with self.assertRaisesRegex(ValueError,'unavailable or failed'):operation()
        p=self.root/'skills/deep-loop/scripts/deep_loop.py'
        p.write_text("from pathlib import Path\ndef completed_state(state,archive=None):\n assert archive is None or isinstance(archive,Path)\n return [state,str(archive) if archive is not None else None]\ndef verified_delivery_state(state,revision,evidence,archive=None):\n assert archive is None or isinstance(archive,Path)\n return [state,revision,evidence,str(archive) if archive is not None else None]\n")
        self.files[str(p.relative_to(self.root))]=hashlib.sha256(p.read_bytes()).hexdigest()
        self.assertEqual(self.helper.completed_state({'fixture':True},self.root),[{'fixture':True},str(self.root)])
        self.assertEqual(self.helper.verified_delivery_state({},'a'*40,'readback',self.root),[{},'a'*40,'readback',str(self.root)])

    def test_dependency_collector_crosses_isolated_proxy_and_rejects_drift(self):
        with self.assertRaisesRegex(ValueError,'unavailable or failed'):
            self.helper.review_dependency_cut({'verificationContract':{'path':'/missing'}},[['V1']])
        source=Path(__file__).with_name('proof_binding_source.py')
        if not source.exists():source=Path(__file__).resolve().parents[1]/'skills/deep-loop/scripts/proof_binding.py'
        module=self.root/'skills/deep-loop/scripts/proof_binding.py';module.write_bytes(source.read_bytes())
        self.files[str(module.relative_to(self.root))]=hashlib.sha256(module.read_bytes()).hexdigest()
        p=self.root/'skills/deep-loop/scripts/deep_loop.py'
        p.write_text("""from pathlib import Path
import proof_binding as proof
def task_records(state):return [[],{}]
def contract_definition_issues(state):return []
def contract_data(path,verify_files=True):return proof.read(path)
def prerequisite_issues(state,ids):proof.read(state['receipt']);return []
def validation_issues(state,stage,archive=None):
 proof.sha(state['artifact'])
 if state.get('drift'):Path(state['artifact']).write_bytes(b'late drift')
 return []
""")
        self.files[str(p.relative_to(self.root))]=hashlib.sha256(p.read_bytes()).hexdigest()
        contract=self.root/'contract.json';contract.write_text('{"verifiers":[]}')
        receipt=self.root/'receipt.json';receipt.write_text('[]')
        artifact=self.root/'artifact';artifact.write_bytes(b'passed')
        state={'verificationContract':{'path':str(contract)},'receipt':str(receipt),'artifact':str(artifact)}
        with patch.object(self.helper,'_verify',wraps=self.helper._verify) as verify:
            cut=self.helper.review_dependency_cut(state,[['V1']],self.root)
            self.assertEqual(verify.call_count,1)
        self.assertEqual(set(cut),{str(contract),str(receipt),str(artifact)})
        self.assertEqual(cut[str(artifact)]['sha256'],hashlib.sha256(b'passed').hexdigest())
        wrapped=self.helper.review_observation_with_dependencies(state,[['V1']],self.root)
        self.assertEqual(set(wrapped),{'observation','dependencies'})
        self.assertEqual(wrapped['dependencies'],cut)
        self.assertEqual(wrapped['observation'],self.helper.review_observation(state,[['V1']],self.root))
        p.write_text(p.read_text()+"\ndef verified_delivery_state(state,revision,evidence,archive=None):\n proof.sha(state['image_input']);return {'image':'derived'}\n")
        self.files[str(p.relative_to(self.root))]=hashlib.sha256(p.read_bytes()).hexdigest()
        image=self.root/'image-input';image.write_bytes(b'image-bound proof')
        derivation={'before':{'image_input':str(image)},'revision':'a'*40,'evidence':'fixture','terminal':False}
        combined=self.helper.checkpoint_observation_with_dependencies(state,'review_observation',[['V1']],self.root,derivation)
        self.assertEqual(combined['observation'],self.helper.checkpoint_observation(state,'review_observation',[['V1']],self.root,derivation))
        self.assertEqual(set(combined['dependencies']),set(cut)|{str(image)})
        with self.assertRaisesRegex(ValueError,'unavailable or failed'):
            self.helper.review_dependency_cut({**state,'drift':True},[['V1']],self.root)

    def test_fixed_definition_batch_uses_unchanged_legacy_functions_and_rechecks_pins(self):
        p=self.root/'skills/deep-loop/scripts/deep_loop.py'
        p.write_text("from pathlib import Path\ndef task_records(state):return [state['tasks'],{'task':state['tasks'][0]}]\ndef contract_definition_issues(state):return []\ndef contract_data(path,verify_files=True):\n assert isinstance(path,Path) and verify_files is False\n return {'path':str(path),'verifiers':[]}\n")
        self.files[str(p.relative_to(self.root))]=hashlib.sha256(p.read_bytes()).hexdigest()
        state={'tasks':[{'id':'task'}],'verificationContract':{'path':str(self.root/'contract.json')}}
        with patch.object(self.helper,'_verify',wraps=self.helper._verify) as verify:
            result=self.helper.definition_observation(state)
            self.assertEqual(verify.call_count,1)
        self.assertEqual(result,{'records':[[{'id':'task'}],{'task':{'id':'task'}}],
                                 'issues':[],'contract':{'path':state['verificationContract']['path'],'verifiers':[]}})
        p.write_text('source drift')
        with self.assertRaisesRegex(ValueError,'source drift'):self.helper.definition_observation(state)

    def test_fixed_review_batch_composes_legacy_readers_and_rechecks_pins(self):
        p=self.root/'skills/deep-loop/scripts/deep_loop.py'
        p.write_text("from pathlib import Path\ndef task_records(state):return [state['tasks'],{}]\ndef contract_definition_issues(state):return []\ndef contract_data(path,verify_files=True):return {'verifiers':[]}\ndef prerequisite_issues(state,ids):return ['bad'] if ids==['bad'] else []\ndef validation_issues(state,stage,archive=None):\n assert isinstance(archive,Path) and stage=='review'\n return []\n")
        self.files[str(p.relative_to(self.root))]=hashlib.sha256(p.read_bytes()).hexdigest()
        state={'tasks':[],'verificationContract':{'path':'/fixture'}}
        with patch.object(self.helper,'_verify',wraps=self.helper._verify) as verify:
            result=self.helper.review_observation(state,[['good'],['bad']],self.root)
            self.assertEqual(verify.call_count,1)
        self.assertEqual(result['prerequisites'],[[],['bad']]);self.assertEqual(result['review_issues'],[])
        p.write_text('drift')
        with self.assertRaisesRegex(ValueError,'source drift'):self.helper.review_observation(state,[['good']],self.root)

    def test_fixed_outcome_batch_uses_legacy_readers_without_validation_api(self):
        p=self.root/'skills/deep-loop/scripts/deep_loop.py'
        p.write_text("def task_records(state):return [state['tasks'],{}]\ndef contract_definition_issues(state):return []\ndef contract_data(path,verify_files=True):return {'verifiers':[]}\ndef prerequisite_issues(state,ids):return ['bad'] if ids==['bad'] else []\n")
        self.files[str(p.relative_to(self.root))]=hashlib.sha256(p.read_bytes()).hexdigest()
        state={'tasks':[],'verificationContract':{'path':'/fixture'}}
        result=self.helper.outcome_observation(state,[['good'],['bad']])
        self.assertEqual(set(result),{'records','issues','contract','prerequisites'})
        self.assertEqual(result['prerequisites'],[[],['bad']])
        for groups in ([],[['duplicate','duplicate']],[[]]):
            with self.assertRaises(ValueError):self.helper.outcome_observation(state,groups)
        p.write_text('drift')
        with self.assertRaisesRegex(ValueError,'source drift'):self.helper.outcome_observation(state,[['good']])

    def test_checkpoint_composition_keeps_existing_readers_and_exact_images(self):
        p=self.root/'skills/deep-loop/scripts/deep_loop.py'
        p.write_text("from pathlib import Path\ndef task_records(state):return [state['tasks'],{}]\ndef contract_definition_issues(state):return []\ndef contract_data(path,verify_files=True):return {'verifiers':[]}\ndef prerequisite_issues(state,ids):return []\ndef validation_issues(state,stage,archive=None):return []\ndef verified_delivery_state(state,revision,evidence,archive=None):\n assert isinstance(archive,Path)\n return {**state,'revision':revision,'evidence':evidence}\ndef completed_state(state,archive=None):return {**state,'complete':True}\n")
        self.files[str(p.relative_to(self.root))]=hashlib.sha256(p.read_bytes()).hexdigest()
        state={'tasks':[],'verificationContract':{'path':'/fixture'}}
        derivation={'before':{'pending':True},'revision':'a'*40,'evidence':'readback','terminal':False}
        for mode in ('definition_observation','outcome_observation','review_observation'):
            expected=(self.helper.definition_observation(state) if mode=='definition_observation' else
                      self.helper.outcome_observation(state,[['V1']]) if mode=='outcome_observation' else
                      self.helper.review_observation(state,[['V1']],self.root))
            with patch.object(self.helper,'_verify',wraps=self.helper._verify) as verify:
                actual=self.helper.checkpoint_observation(state,mode,[['V1']],self.root,derivation)
                self.assertEqual(verify.call_count,1)
            image=actual.pop('delivery_image');self.assertEqual(actual,expected)
            self.assertEqual(image,self.helper.verified_delivery_state(derivation['before'],'a'*40,'readback',self.root))
        terminal={**derivation,'terminal':True}
        actual=self.helper.checkpoint_observation(state,'definition_observation',None,self.root,terminal)
        self.assertEqual(actual['terminal_image'],self.helper.completed_state(actual['delivery_image'],self.root))
        large_state={**state,'payload':'s'*300000}
        large_derivation={**derivation,'before':{'payload':'b'*300000}}
        result=self.helper.checkpoint_observation(large_state,'definition_observation',None,self.root,large_derivation)
        self.assertEqual(result['delivery_image']['payload'],'b'*300000)
        oversized={**derivation,'before':{'payload':'b'*524288}}
        with self.assertRaisesRegex(ValueError,'unavailable or failed'):
            self.helper.checkpoint_observation(state,'definition_observation',None,self.root,oversized)
        for bad in ({**derivation,'terminal':1},{**derivation,'extra':True}):
            with self.assertRaises(ValueError):self.helper.checkpoint_observation(state,'definition_observation',None,self.root,bad)
        p.write_text('source drift')
        with self.assertRaisesRegex(ValueError,'source drift'):
            self.helper.checkpoint_observation(state,'definition_observation',None,self.root,derivation)

    def test_definition_batch_preserves_individual_result_capacity(self):
        p=self.root/'skills/deep-loop/scripts/deep_loop.py'
        p.write_text("def task_records(state):return 'r'*600000\ndef contract_definition_issues(state):return []\ndef contract_data(path,verify_files=True):return 'c'*600000\n")
        self.files[str(p.relative_to(self.root))]=hashlib.sha256(p.read_bytes()).hexdigest()
        result=self.helper.definition_observation({'verificationContract':{'path':'/fixture'}})
        self.assertEqual(len(result['records']),600000);self.assertEqual(len(result['contract']),600000)
        p.write_text("def task_records(state):return 'r'*1100000\ndef contract_definition_issues(state):return []\ndef contract_data(path,verify_files=True):return {}\n")
        self.files[str(p.relative_to(self.root))]=hashlib.sha256(p.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError,'unavailable or failed'):self.helper.definition_observation({'verificationContract':{'path':'/fixture'}})

    def test_drift_unpinned_dependency_and_oversize_request_fail_closed(self):
        p=self.root/'skills/deep-loop/scripts/deep_loop.py';p.write_text('drift')
        with self.assertRaisesRegex(ValueError,'source drift'):self.helper.task_queue({})
        self.files[str(p.relative_to(self.root))]=hashlib.sha256(p.read_bytes()).hexdigest()
        extra=p.with_name('extra.py');extra.write_text('')
        with self.assertRaisesRegex(ValueError,'Unpinned'):self.helper.task_queue({})
        extra.unlink()
        with self.assertRaisesRegex(ValueError,'request exceeds'):self.helper.task_records({'large':'x'*524288})

    def test_excessive_helper_output_fails_with_bounded_capture(self):
        p=self.root/'skills/deep-loop/scripts/deep_loop.py'
        p.write_text("def task_records(state):return 'x'*2097152\n")
        self.files[str(p.relative_to(self.root))]=hashlib.sha256(p.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError,'unavailable or failed'):
            self.helper.task_records({})

    def test_source_size_and_inventory_depth_are_bounded(self):
        p=self.root/'skills/deep-loop/scripts/deep_loop.py'
        original=p.read_bytes();p.write_bytes(b'x'*1048577)
        with self.assertRaisesRegex(ValueError,'file exceeds bound'):self.helper.task_records({})
        p.write_bytes(original)
        (p.parent/'a/b/c/d/e').mkdir(parents=True)
        for directory in p.parent.rglob('*'):
            if directory.is_dir():directory.chmod(0o755)
        with self.assertRaisesRegex(ValueError,'depth exceeds bound'):self.helper.task_records({})

    def test_inventory_entries_and_alternate_imports_are_bounded(self):
        folder=self.root/'skills/deep-loop/scripts'
        for extension in ('.pyc','.so','.pyd','.pth'):
            p=folder/('extra'+extension);p.write_bytes(b'')
            with self.assertRaisesRegex(ValueError,'import artifact'):self.helper.task_records({})
            p.unlink()
        p=folder/'link';p.symlink_to(folder/'deep_loop.py')
        with self.assertRaisesRegex(ValueError,'symlink'):self.helper.task_records({})
        p.unlink()
        for number in range(2049):(folder/str(number)).touch()
        with self.assertRaisesRegex(ValueError,'inventory exceeds bound'):self.helper.task_records({})

    def test_child_allocation_fails_closed(self):
        p=self.root/'skills/deep-loop/scripts/deep_loop.py'
        p.write_text("def task_records(state):return bytearray(1073741824)\n")
        self.files[str(p.relative_to(self.root))]=hashlib.sha256(p.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError,'unavailable or failed'):self.helper.task_records({})

    def bound(self):
        from admission import digest
        from private_controller import TrustedStore
        control=self.root/'control';control.mkdir(mode=0o700)
        store=TrustedStore(control,owner_uid=os.getuid())
        key=digest({'fixture':'bound helper'})
        binding={'approval_ref':'fixture binding'}
        store.create(key+'.workflow.json',binding)
        record={'contract_digest':key,'binding_digest':digest(binding),'approval_ref':binding['approval_ref'],'helper':self.config}
        intent={'contract_digest':key,'binding_digest':digest(binding),'approval_ref':binding['approval_ref'],'helper_digest':digest(record),'journal_revision':'a'*40}
        store.create(key+'.workflow-helper-intent.json',intent)
        store.create(key+'.workflow-helper-complete.json',{**intent,'activated':False})
        return BoundPinnedHelper(store,key),store,key,record

    def test_protected_binding_reloads_authority_and_source_on_each_call(self):
        helper,store,key,record=self.bound()
        store.create(key+'.workflow-helper.json',record)
        self.assertEqual(helper.task_records({})[0],{})
        store.remove(key+'.workflow-helper.json')
        store.create(key+'.workflow-helper.json',{**record,'binding_digest':'0'*64})
        with self.assertRaisesRegex(ValueError,'authority changed'):helper.task_records({})
        store.remove(key+'.workflow-helper.json');store.create(key+'.workflow-helper.json',record)
        (self.root/'skills/deep-loop/scripts/deep_loop.py').write_text('drift')
        with self.assertRaisesRegex(ValueError,'source drift'):helper.task_records({})

    def test_protected_helper_construction_is_lazy_but_use_requires_record(self):
        helper,store,key,record=self.bound()
        with self.assertRaises(FileNotFoundError):helper.task_records({})

    def test_partial_or_changed_completion_blocks_helper_use(self):
        helper,store,key,record=self.bound();store.create(key+'.workflow-helper.json',record)
        complete=store.read(key+'.workflow-helper-complete.json');store.remove(key+'.workflow-helper-complete.json')
        with self.assertRaises(FileNotFoundError):helper.task_records({})
        store.create(key+'.workflow-helper-complete.json',{**complete,'activated':True})
        with self.assertRaisesRegex(ValueError,'completion changed'):helper.task_records({})

    def paired_fixture(self):
        code="""import proof_binding
_counter=[]
def task_records(state):
 _counter.append(1)
 return {'counter':len(_counter),'clean':proof_binding._CONTEXT.get() is None}
def contract_definition_issues(state):return []
def contract_data(path,verify_files=False):return {}
def prerequisite_issues(state,ids):return []
def validation_issues(state,stage,archive=None):return []
"""
        context="""from contextlib import contextmanager
from contextvars import ContextVar
_CONTEXT=ContextVar('pair_test',default=None)
@contextmanager
def dependency_context():
 yield {}
def close_dependency_cut(records):return {'fixture':{'hash':'unchanged'}}
"""
        for name,text in [('skills/deep-loop/scripts/deep_loop.py',code),('skills/deep-loop/scripts/proof_binding.py',context)]:
            p=self.root/name;p.write_text(text);self.files[name]=hashlib.sha256(p.read_bytes()).hexdigest()
        return {'verificationContract':{'path':str(self.root/'contract.json')}}

    def test_paired_passes_have_independent_module_state_and_dependency_results(self):
        state=self.paired_fixture()
        original=self.helper.review_observation(state,[['V1']],None)
        with self.helper.review_pair():
            opening=self.helper.review_observation(state,[['V1']],None)
            closing=self.helper.review_observation_with_dependencies(state,[['V1']],None)
        self.assertEqual(opening,original);self.assertEqual(closing['observation'],original)
        self.assertEqual(opening['records'],{'counter':1,'clean':True})
        self.assertEqual(closing['dependencies'],{'fixture':{'hash':'unchanged'}})
        self.assertIsNone(self.helper._review_pair)

    def test_paired_checkpoint_review_matches_ordinary_images_and_dependencies(self):
        state=self.paired_fixture();path=self.root/'skills/deep-loop/scripts/deep_loop.py'
        path.write_text(path.read_text()+"\ndef verified_delivery_state(state,revision,evidence,archive=None):return {**state,'revision':revision,'evidence':evidence}\ndef completed_state(state,archive=None):return {**state,'complete':True}\n")
        self.files[str(path.relative_to(self.root))]=hashlib.sha256(path.read_bytes()).hexdigest()
        for terminal in (False,True):
            derivation={'before':{'pending':True,'payload':'b'*300000},'revision':'a'*40,'evidence':'fixture','terminal':terminal}
            ordinary=self.helper.checkpoint_observation(state,'review_observation',[['V1']],self.root,derivation)
            with self.helper.review_pair():
                opening=self.helper.checkpoint_observation(state,'review_observation',[['V1']],self.root,derivation)
                closing=self.helper.checkpoint_observation_with_dependencies(state,'review_observation',[['V1']],self.root,derivation)
            self.assertEqual(opening,ordinary);self.assertEqual(closing['observation'],ordinary)
            self.assertEqual(closing['dependencies'],{'fixture':{'hash':'unchanged'}})

    def test_pair_rejects_changed_closing_input_and_reaps_coordinator(self):
        state=self.paired_fixture();pair=None
        with self.assertRaises(PairedReviewWorkerError):
            with self.helper.review_pair():
                self.helper.review_observation(state,[['V1']],None);pair=self.helper._review_pair
                self.helper.review_observation({**state,'changed':True},[['V1']],None)
        self.assertIsNotNone(pair.process.returncode);self.assertIsNone(self.helper._review_pair)

    def test_pair_import_stderr_is_file_size_bounded(self):
        state=self.paired_fixture()
        path=self.root/'skills/deep-loop/scripts/deep_loop.py'
        path.write_text("import os\nwhile True: os.write(2,b'x'*65536)\n"+path.read_text())
        self.files['skills/deep-loop/scripts/deep_loop.py']=hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaises(PairedReviewWorkerError):
            with self.helper.review_pair():
                pair=self.helper._review_pair
                self.helper.review_observation(state,[['V1']],None)
        self.assertIsNotNone(pair.process.returncode)
        self.assertIsNone(self.helper._review_pair)

    def test_pair_rejects_and_reaps_detached_adopted_descendants(self):
        import time
        for mode in ('live','zombie'):
            with self.subTest(mode=mode):
                state=self.paired_fixture();marker=self.root/'descendant.json'
                path=self.root/'skills/deep-loop/scripts/deep_loop.py'
                path.write_text(path.read_text()+f"""
def task_records(state):
 import os,time,json
 from pathlib import Path
 marker=Path({str(marker)!r})
 pid=os.fork()
 if pid==0:
  os.setsid()
  grandchild=os.fork()
  if grandchild==0:
   marker.write_text(json.dumps({{'pid':os.getpid(),'stat':Path('/proc/self/stat').read_text()}}))
   if {mode!r}=='zombie':os._exit(0)
   while True:time.sleep(.01)
  os._exit(0)
 os.waitpid(pid,0)
 deadline=time.monotonic()+1
 while not marker.exists():
  assert time.monotonic()<deadline
  time.sleep(.001)
 return {{'fixture':'descendant'}}
""")
                self.files[str(path.relative_to(self.root))]=hashlib.sha256(path.read_bytes()).hexdigest()
                with self.assertRaises(PairedReviewWorkerError):
                    with self.helper.review_pair():
                        pair=self.helper._review_pair
                        self.helper.review_observation(state,[['V1']],None)
                pid=__import__('json').loads(marker.read_text())['pid']
                self.assertFalse(Path('/proc',str(pid)).exists())
                self.assertIsNotNone(pair.process.returncode)
                marker.unlink()

    def test_pair_preserves_normal_git_subprocess_and_near_reader_limit(self):
        state=self.paired_fixture();path=self.root/'skills/deep-loop/scripts/deep_loop.py'
        path.write_text(path.read_text()+"\ndef task_records(state):\n import subprocess\n return {'git':subprocess.run(['/usr/bin/git','--version'],capture_output=True,text=True,check=True).stdout,'data':'x'*1048000}\n")
        self.files[str(path.relative_to(self.root))]=hashlib.sha256(path.read_bytes()).hexdigest()
        original=self.helper.review_observation(state,[['V1']],None)
        with self.helper.review_pair():
            opening=self.helper.review_observation(state,[['V1']],None)
            closing=self.helper.review_observation_with_dependencies(state,[['V1']],None)
        self.assertEqual(opening,original);self.assertEqual(closing['observation'],original)

    def test_pair_maximum_group_count_preserves_large_result_capacity(self):
        from admission import digest
        state=self.paired_fixture();path=self.root/'skills/deep-loop/scripts/deep_loop.py'
        path.write_text(path.read_text()+"\ndef prerequisite_issues(state,ids):return 'x'*1048000\n")
        self.files[str(path.relative_to(self.root))]=hashlib.sha256(path.read_bytes()).hexdigest()
        groups=[['V'+str(index)] for index in range(129)]
        ordinary=self.helper.review_observation(state,groups,None);expected=digest(ordinary)
        del ordinary
        with self.helper.review_pair():
            opening=self.helper.review_observation(state,groups,None)
            self.assertEqual(digest(opening),expected);del opening
            closing=self.helper.review_observation_with_dependencies(state,groups,None)
            self.assertEqual(digest(closing['observation']),expected)

    def test_pair_capability_selection_requires_current_outer_containment(self):
        import pinned_helper
        self.assertFalse(self.helper.supports_review_pair())
        with patch.object(pinned_helper,'_PAIR_CONTAINMENT',(os.getpid(),'fixture','a'*32,'/system.slice/fixture.service')):
            with patch.dict(os.environ,{'INVOCATION_ID':'b'*32}):
                with self.assertRaisesRegex(RuntimeError,'invocation'):self.helper.supports_review_pair()
            with patch.dict(os.environ,{'INVOCATION_ID':'a'*32}),patch('pinned_helper.Path.read_text',return_value='0::/other'):
                with self.assertRaisesRegex(RuntimeError,'containment'):self.helper.supports_review_pair()
            with patch.dict(os.environ,{'INVOCATION_ID':'a'*32}),patch('pinned_helper.Path.read_text',return_value='0::/system.slice/fixture.service'),patch.object(pinned_helper,'_review_pair_available',return_value=False):
                self.assertFalse(self.helper.supports_review_pair())

    def test_pair_reverifies_pins_before_closing_and_reaps_after_callback_failure(self):
        state=self.paired_fixture()
        for failure in ('pins','callback'):
            with self.subTest(failure=failure):
                with self.assertRaises(PairedReviewWorkerError):
                    with self.helper.review_pair():
                        self.helper.review_observation(state,[['V1']],None);pair=self.helper._review_pair
                        if failure=='callback':raise ValueError('controller check failed')
                        path=self.root/'skills/deep-loop/scripts/deep_loop.py';original=path.read_text()
                        path.write_text(original+'\n# changed pin\n')
                        try:self.helper.review_observation(state,[['V1']],None)
                        finally:path.write_text(original)
                self.assertIsNotNone(pair.process.returncode);self.assertIsNone(self.helper._review_pair)

    def test_pair_protocol_rejects_oversized_partial_and_extra_frames(self):
        import pinned_helper
        state=self.paired_fixture()
        for mode in ('oversized','partial','extra'):
            program="""import json,os
size=int.from_bytes(os.read(0,8),'big');data=bytearray()
while len(data)<size:data.extend(os.read(0,size-len(data)))
request=json.loads(data)
"""
            if mode=='oversized':program+="os.write(1,(request['limit']+1).to_bytes(8,'big'))\n"
            elif mode=='partial':program+="os.write(1,b'bad')\n"
            else:program+="os.write(1,(2).to_bytes(8,'big')+b'{}')\nsize=int.from_bytes(os.read(0,8),'big');data=bytearray()\nwhile len(data)<size:data.extend(os.read(0,size-len(data)))\nos.write(1,(2).to_bytes(8,'big')+b'{}'+b'x')\n"
            with self.subTest(mode=mode),patch.object(pinned_helper,'PAIR_COORDINATOR',program):
                with self.assertRaises(PairedReviewWorkerError):
                    with self.helper.review_pair():
                        pair=self.helper._review_pair
                        self.helper.review_observation(state,[['V1']],None)
                        self.helper.review_observation(state,[['V1']],None)
                self.assertIsNotNone(pair.process.returncode)

    def test_pair_deadline_covers_between_pass_controller_work_without_reset(self):
        import time
        state=self.paired_fixture()
        with self.assertRaises(PairedReviewWorkerError):
            with self.helper.review_pair():
                self.helper.review_observation(state,[['V1']],None);pair=self.helper._review_pair
                pair.deadline=time.monotonic()-1
                self.helper.review_observation(state,[['V1']],None)
        self.assertIsNotNone(pair.process.returncode)

    def test_pair_context_rejects_incomplete_nested_and_nonreview_operations(self):
        state=self.paired_fixture()
        with self.assertRaises(PairedReviewWorkerError):
            with self.helper.review_pair():
                self.helper.review_observation(state,[['V1']],None);pair=self.helper._review_pair
        self.assertIsNotNone(pair.process.returncode)
        with self.assertRaisesRegex(ValueError,'Nested'):
            with self.helper.review_pair():
                with self.helper.review_pair():pass
        with self.assertRaisesRegex(ValueError,'Fixed paired full review'):
            with self.helper.review_pair():self.helper.task_records(state)

    def test_pair_reader_output_bound_is_still_enforced(self):
        state=self.paired_fixture();path=self.root/'skills/deep-loop/scripts/deep_loop.py'
        path.write_text(path.read_text().replace("return {'counter':len(_counter),'clean':proof_binding._CONTEXT.get() is None}","return 'x'*1048577"))
        self.files[str(path.relative_to(self.root))]=hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaises(PairedReviewWorkerError):
            with self.helper.review_pair():
                pair=self.helper._review_pair;self.helper.review_observation(state,[['V1']],None)
        self.assertIsNotNone(pair.process.returncode)
