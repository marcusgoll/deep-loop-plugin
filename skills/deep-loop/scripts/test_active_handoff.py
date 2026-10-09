"""Active handoff invariants: integrity is distinct from delivery or authority."""
import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import deep_loop as dl

class ActiveHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.source = self.root / '.deep-abcd1234'
        self.source.mkdir()
        self.state = {'schemaVersion':4,'sessionId':'abcd1234','task':'Export totals',
                      'phase':'BUILD','active':True,'complete':False,
                      'uiRoute':{'kind':'not_applicable','reason':'CLI only'},
                      'checks':[{'name':'acceptance','status':'pending'}],
                      'delivery':{'endpoint':'local','status':'pending'}}
        (self.source/'state.json').write_text(json.dumps(self.state))
        (self.source/'plan.md').write_text('Approved scope remains incomplete.\n')
        self.refs = self.root/'refs.json'
        self.packet = self.root/'packet'
        self.args = argparse.Namespace(root=str(self.root),path=str(self.source),session=None,
                                       references=str(self.refs),output=str(self.packet))
        self.write_refs([])
        self.original = (self.source/'state.json').read_bytes()
    def write_refs(self, rows):
        self.refs.write_text(json.dumps(rows))
    def row(self, path, required=True):
        return {'id':'decision','kind':'decision','path':str(path),'required':required,
                'provenance':'Current user approval; supplied record, not authenticated'}
    def create(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return dl.handoff(self.args)
    def inspect(self):
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream):
            code=dl.inspect_handoff(argparse.Namespace(packet=str(self.packet)))
        return code,json.loads(stream.getvalue())
    def test_active_pending_preserved_without_closeout(self):
        self.assertEqual(self.create(),0)
        self.assertEqual((self.packet/'snapshot/state.json').read_bytes(),self.original)
        self.assertEqual((self.source/'state.json').read_bytes(),self.original)
        code,report=self.inspect()
        self.assertEqual(report['packetIntegrity'],'verified')
        self.assertFalse(report['recovery']['recorded']['complete'])
        self.assertEqual(report['ownership'],'unknown')
        self.assertEqual(report['executionAuthority'],'not_transferred')
        self.assertFalse((self.packet/'archive.json').exists())
    def test_required_missing_is_saved_not_fabricated(self):
        self.write_refs([self.row(self.root/'missing')])
        self.create()
        code,report=self.inspect()
        self.assertEqual(code,1)
        self.assertEqual(report['references'][0]['status'],'unavailable')
        self.assertEqual(report['requiredReferences'],'unavailable')
    def test_optional_missing_not_required_failure(self):
        self.write_refs([self.row(self.root/'missing',False)])
        self.create()
        _,report=self.inspect()
        self.assertEqual(report['requiredReferences'],'available')
    def test_explicit_reference_bytes_and_relocation(self):
        record=self.root/'approved.md';record.write_text('yes\n')
        self.write_refs([self.row(record)])
        self.create()
        moved=self.root/'moved';self.packet.rename(moved);self.packet=moved
        record.unlink();self.refs.unlink()
        import shutil
        shutil.rmtree(self.source)
        _,report=self.inspect()
        self.assertEqual(report['references'][0]['status'],'retained')
        self.assertEqual(report['packetIntegrity'],'verified')
    def test_reference_tamper_refused(self):
        record=self.root/'approved.md';record.write_text('yes')
        self.write_refs([self.row(record)]);self.create()
        saved=json.loads((self.packet/'handoff.json').read_text())
        retained=self.packet/saved['references'][0]['retained']
        retained.write_text('no')
        with self.assertRaises(ValueError):self.inspect()
    def test_extra_unindexed_payload_refused(self):
        self.create();(self.packet/'rogue.bin').write_bytes(b'Unrelated data')
        with self.assertRaises(ValueError):self.inspect()

    def test_existing_output_unchanged(self):
        self.packet.mkdir();sentinel=self.packet/'sentinel';sentinel.write_text('keep')
        with self.assertRaises((ValueError,FileExistsError)):self.create()
        self.assertEqual(sentinel.read_text(),'keep')
        self.assertEqual((self.source/'state.json').read_bytes(),self.original)
    def test_symlink_reference_refused(self):
        target=self.root/'actual';target.write_text('value')
        link=self.root/'link';link.symlink_to(target)
        self.write_refs([self.row(link)])
        with self.assertRaises(ValueError):self.create()
        self.assertFalse(self.packet.exists())
    def test_directory_reference_refused(self):
        self.write_refs([self.row(self.source)])
        with self.assertRaises(ValueError):self.create()
    def test_duplicate_reference_ids_refused_before_output(self):
        row=self.row(self.root/'missing');self.write_refs([row,row])
        with self.assertRaises(ValueError):self.create()
        self.assertFalse(self.packet.exists())
    def test_url_index_only_without_network_or_subprocess(self):
        self.write_refs([{'id':'issue','kind':'evidence','url':'https://example.invalid/issue/7',
                         'required':True,'provenance':'Explicit external index only'}])
        with patch('subprocess.run',side_effect=AssertionError('No commands')):
            self.create();code,report=self.inspect()
        self.assertEqual(code,1)
        self.assertEqual(report['references'][0]['status'],'external_not_inspected')
    def test_packet_never_retirement_archive_even_injected_metadata(self):
        self.create();(self.packet/'archive.json').write_text('{}')
        with self.assertRaises(ValueError):dl.verify_archive(self.packet)
        self.assertEqual((self.source/'state.json').read_bytes(),self.original)
    def test_snapshot_drift_refused(self):
        self.create();(self.packet/'snapshot/state.json').write_text('{}')
        with self.assertRaises(ValueError):self.inspect()

    def test_existing_archive_resolution_binding_is_not_replaced(self):
        self.state['proofResolution']={'path':str(self.root/'old-resolution.json'),'sha256':'0'*64}
        (self.source/'state.json').write_text(json.dumps(self.state))
        preimage=(self.source/'state.json').read_bytes()
        with self.assertRaisesRegex(ValueError,'existing archive resolution binding'):self.create()
        self.assertFalse(self.packet.exists())
        self.assertEqual((self.source/'state.json').read_bytes(),preimage)

    def test_explicit_snapshot_reference_cannot_replace_preimage(self):
        import active_handoff
        self.write_refs([self.row(self.source/'state.json')])
        original_read=active_handoff.read_local
        count=0
        def drifting_read(path):
            nonlocal count
            payload=original_read(path)
            if path==self.source/'state.json':
                count+=1
                if count==2:
                    modified=json.loads(payload);modified['phase']='REVIEW'
                    return json.dumps(modified).encode()
            return payload
        with patch.object(active_handoff,'read_local',side_effect=drifting_read):
            with self.assertRaises(ValueError):self.create()
        self.assertFalse(self.packet.exists())

    def test_source_drift_prevents_publication_and_retains_staging(self):
        original_write=dl.write_json
        def drift(path,data):
            original_write(path,data)
            (self.source/'state.json').write_text('changed by another writer')
        with patch.object(dl,'write_json',side_effect=drift):
            with self.assertRaises(ValueError):self.create()
        self.assertFalse(self.packet.exists())
        self.assertTrue(list(self.root.glob('packet.staging-*')))
        self.assertFalse((self.root/'packet.handoff.lock').exists())
    def test_missing_plan_appearance_prevents_publication(self):
        (self.source/'plan.md').unlink()
        original_write=dl.write_json
        def appear(path,data):
            original_write(path,data)
            (self.source/'plan.md').write_text('New plan from another writer')
        with patch.object(dl,'write_json',side_effect=appear):
            with self.assertRaises(ValueError):self.create()
        self.assertFalse(self.packet.exists())
    def test_malformed_reference_and_escaping_map_refused(self):
        self.create()
        manifest=self.packet/'handoff.json';original=manifest.read_text();saved=json.loads(original)
        saved['references']=[None];manifest.write_text(json.dumps(saved))
        with self.assertRaises(ValueError):self.inspect()
        saved=json.loads(original);saved['resolution'][str(self.source/'state.json')]['path']='../outside'
        manifest.write_text(json.dumps(saved))
        with self.assertRaises(ValueError):self.inspect()
    def bound_fixture(self, passed=True, retain_receipt=True):
        import sys
        source=self.root/'subject.txt';source.write_text('correct')
        impl=self.root/'observe.py'
        impl.write_text("import hashlib,json\nfrom pathlib import Path\np=Path('subject.txt').resolve()\nPath('observed.json').write_text(json.dumps({'endpoint':'local','targets':[{'id':'single','revision':'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest(),'artifact':str(p)}]}))\n")
        sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        sources=self.root/'sources.json';sources.write_text(json.dumps({'files':{'subject.txt':sha(source)}}))
        env=self.root/'env.json';env.write_text(json.dumps({'python':sys.version}))
        observed=self.root/'observed.json'
        proof={'mode':'bound','implementation':{'path':str(impl),'sha256':sha(impl)},
               'source_manifest':{'path':str(sources),'sha256':sha(sources)},
               'environment_manifest':{'path':str(env),'sha256':sha(env)},
               'argv':[sys.executable,str(impl)],'artifacts':[{'path':str(source)},{'path':str(observed)}],
               'readback':{'endpoint':'local','result':str(observed),'targets':[{'id':'single','artifact':str(source)}]}}
        contract={'name':'Active packet bound fixture','scope':'local','status':'NOT_RUN',
                  'requirements':[{'id':'R1','outcome':'Correct','invariant':'Correct','priority':'blocking'}],
                  'verifiers':[{'id':'V1','covers':['R1'],'class':'deterministic','status':'implemented','expected':'No failures','gate':'blocking','proof':proof}],
                  'gaps':[],'ship_gate':dict.fromkeys(('require_all_blocking_verifiers_pass','require_zero_blocking_gaps','require_human_approvals_recorded','require_evidence_matches_revision'),True)}
        path=self.root/'contract.json';path.write_text(json.dumps(contract))
        receipt=self.root/'receipt.json'
        self.state.update(verificationContract={'path':str(path),'sha256':sha(path),'endpoint':'local'},
                          checks=[{'name':'V1','verifierId':'V1','status':'pending','stage':'ship'}])
        self.state['delivery'].update(revision='sha256:'+sha(source))
        if passed:
            batch=self.root/'batch.json';batch.write_text(json.dumps([{'name':'V1','verifierId':'V1','argv':proof['argv']}]))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(dl.run_checks(argparse.Namespace(root=str(self.root),checks=str(batch),output=str(receipt),contract=str(path),goal_id='abcd1234',ui_request=None,source_manifest=None,environment_manifest=None)),0)
            self.state['checks'][0].update(status='passed',evidence='Retained observation',receipt={'path':str(receipt),'sha256':sha(receipt)})
        (self.source/'state.json').write_text(json.dumps(self.state))
        paths=[source,impl,sources,env,path,observed]+([receipt] if retain_receipt else [])
        self.write_refs([dict(self.row(p),id='ref'+str(i),kind='contract' if p==path else 'evidence') for i,p in enumerate(paths)])
        return paths
    def test_bound_readback_survives_offline_relocation(self):
        paths=self.bound_fixture()
        self.create()
        moved=self.root/'relocated';self.packet.rename(moved);self.packet=moved
        for path in paths:path.unlink()
        import shutil
        shutil.rmtree(self.source)
        with patch('subprocess.run',side_effect=AssertionError('Do not execute retained verifier')):
            _,report=self.inspect()
        self.assertEqual(report['recovery']['proofs'][0]['inspection'],'current_for_ship')
        self.assertEqual(report['recovery']['delivery']['liveEndpoint'],'not_inspected')
    def test_undeclared_receipt_has_no_live_fallback(self):
        self.bound_fixture(retain_receipt=False)
        self.create()
        _,report=self.inspect()
        self.assertEqual(report['recovery']['proofs'][0]['inspection'],'blocked')
        self.assertIn('Unmapped preserved dependency',str(report))
        self.assertTrue((self.root/'receipt.json').is_file())
    def test_pending_bound_result_remains_missing_after_save(self):
        self.bound_fixture(passed=False)
        self.create();code,report=self.inspect()
        self.assertEqual(code,1)
        self.assertEqual(report['requiredReferences'],'unavailable')
        self.assertFalse((self.root/'observed.json').exists())
        self.assertEqual(report['recovery']['checks'][0]['recordedStatus'],'pending')

class ActiveUIHandoffTests(unittest.TestCase):
    def test_ui_report_and_offline_handoff_never_launch_or_generate(self):
        import test_ui_design as fixtures
        import proof_binding
        import ui_design
        import pixel_diff
        import shutil
        # Existing author fixture uses actual executions to establish receipt proof.
        # Canonical scratch paths avoid platform /var transport symlinks.
        original_temp = tempfile.TemporaryDirectory
        def canonical_temp(*args, **kwargs):
            kwargs.setdefault('dir',str(Path(tempfile.gettempdir()).resolve()))
            return original_temp(*args,**kwargs)
        fixture = fixtures.UIContractTests(methodName='test_substantive_without_direction_routes_to_design')
        self.addCleanup(fixture.doCleanups)
        with patch.object(fixtures.tempfile,'TemporaryDirectory',side_effect=canonical_temp), contextlib.redirect_stdout(io.StringIO()):
            fixture.setUp();fixture.pixels()
        checkpoint=fixture.root/'.deep-fixture1';checkpoint.mkdir()
        fixture.state.update(task='Retained UI inspection',active=True,complete=False,phase='REVIEW')
        fixtures.save(checkpoint/'state.json',fixture.state);(checkpoint/'plan.md').write_text('Approved fixture only')
        identity=dl.file_manifest(fixture.root)
        with patch('subprocess.run',side_effect=AssertionError('No argv during recovery')), patch('tempfile.TemporaryDirectory',side_effect=AssertionError('No generated comparison directory')),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(dl.recovery_report(argparse.Namespace(root=str(fixture.root),path=str(checkpoint),session=None,json=True)),0)
        self.assertEqual(dl.file_manifest(fixture.root),identity)
        dependencies=set()
        with proof_binding.files_context(trace=dependencies),ui_design.inspection_only():
            self.assertEqual(dl._contract_issues(fixture.state,'ship'),[])
        reference_file=fixture.root/'handoff-references.json'
        rows=[{'id':'ref'+str(i),'kind':'evidence','path':name,'required':True,'provenance':'Explicit synthetic UI dependency'} for i,name in enumerate(sorted(dependencies))]
        reference_file.write_text(json.dumps(rows))
        packet=fixture.root.parent/(fixture.root.name+'-handoff');self.addCleanup(shutil.rmtree,packet,True)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(dl.handoff(argparse.Namespace(root=str(fixture.root),path=str(checkpoint),references=str(reference_file),output=str(packet))),0)
        moved=packet.with_name(packet.name+'-moved');packet.rename(moved);self.addCleanup(shutil.rmtree,moved,True)
        shutil.rmtree(fixture.root)
        stream=io.StringIO()
        with patch('subprocess.run',side_effect=AssertionError('No argv during packet inspection')),patch('tempfile.TemporaryDirectory',side_effect=AssertionError('No output generation')),contextlib.redirect_stdout(stream):
            self.assertEqual(dl.inspect_handoff(argparse.Namespace(packet=str(moved))),0)
        report=json.loads(stream.getvalue())
        self.assertTrue(report['recovery']['localShipRequirementsSatisfied'])
        self.assertEqual(report['liveEndpoint'],'not_inspected')
        self.assertEqual(report['executionAuthority'],'not_transferred')

if __name__=='__main__':unittest.main()


