"""Small known-good/bad scorer checks; no model or external side effects."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import contextlib
import io
import os
import sys
from unittest.mock import patch
import verify_skill as harness
from verify_skill import score
from verification_bridge import apply

class Acceptance(unittest.TestCase):
    def test_codex_launcher_supports_unix_and_windows_shims(self):
        with patch.object(harness.shutil,'which',side_effect=lambda name:'/opt/homebrew/bin/codex' if name=='codex' else None):
            self.assertEqual(harness.codex_command(),['/opt/homebrew/bin/codex'])
        with TemporaryDirectory() as directory:
            root=Path(directory)
            shim=root/'codex.cmd'; shim.write_text('shim')
            launcher=root/'node_modules/@openai/codex/bin/codex.js'
            launcher.parent.mkdir(parents=True); launcher.write_text('launcher')
            locations={'codex':None,'codex.cmd':str(shim),'node':'node.exe'}
            with patch.object(harness.shutil,'which',side_effect=lambda name:locations.get(name)):
                self.assertEqual(harness.codex_command(),['node.exe',str(launcher)])
        with patch.object(harness.shutil,'which',return_value=None):
            with self.assertRaisesRegex(ValueError,'Codex CLI executable'):
                harness.codex_command()

    def test_failed_close_saves_checks_before_refusing_closure(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'closure'
            failure = {'check': 'test_deep_loop.py', 'exit': 1, 'output': 'deliberate test failure'}
            arguments = ['verify_skill.py', 'close', '--contract', 'unused.json', '--selection', 'unused.json', '--output', str(out)]
            with patch.object(sys, 'argv', arguments), patch.object(harness, 'check', return_value=[failure]):
                with self.assertRaises(ValueError):
                    harness.main()
            self.assertEqual(harness.read(out / 'checks.json'), [failure])
            self.assertFalse((out / 'closure.json').exists())

    def test_preflight_exception_and_dependency_drift_invalidate_saved_proof(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            specialist = root / 'specialist.md'
            specialist.write_text('first')
            with patch.object(harness, 'SPECIALIST', specialist):
                original = harness.check_sources()
                specialist.write_text('second')
                self.assertNotEqual(harness.check_sources(), original)
                specialist.unlink()
                self.assertIsNone(harness.check_sources()['dependencies'][str(specialist)])
                identity = harness.check_sources()
                good = [{'check': name, 'exit': 0, 'sources': identity, 'tests': 0} for name in harness.CHECKS]
                harness.write_checks(root / 'results', good)
                with patch.object(harness, 'prepare', side_effect=ValueError('missing specialist')):
                    results = harness.check(['fixture preflights'])
                self.assertEqual(results[0]['exit'], 1)
                self.assertIn('missing specialist', results[0]['output'])
                harness.write_checks(root / 'results', results)
                self.assertEqual(harness.read(root / 'results/checks.json')[-1]['exit'], 1)
                summary = harness.check_summary(harness.read(root / 'results/checks.json'))
                self.assertFalse(summary['complete'])
                self.assertEqual(summary['failed'], ['fixture preflights'])

    def test_candidate_dependencies_use_an_explicit_root(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'verification-contract/scripts/validate_contract.py'
            path.parent.mkdir(parents=True)
            path.write_text('fixture validator')
            with patch.dict(os.environ, {'DEEP_LOOP_SKILLS_ROOT': str(root)}):
                self.assertEqual(harness.skill_dependency('verification-contract/scripts/validate_contract.py'), path.resolve())
                with self.assertRaises(ValueError):
                    harness.skill_dependency('missing.py')

    def test_saved_checks_derive_counts_and_refuse_stale_or_failed_proof(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            skill = root / 'skill'
            skill.mkdir()
            (skill / 'SKILL.md').write_text('version one')
            with patch.object(harness, 'SKILL', skill), patch.object(harness, 'check_sources') as sources:
                sources.side_effect = lambda: {'package': harness.inventory(skill), 'dependencies': {}}
                identity = harness.check_sources()
                rows = [{'check': name, 'exit': 0, 'tests': n, 'sources': identity}
                        for name, n in zip(harness.CHECKS, (0, 8, 2, 7) + (0,) * (len(harness.CHECKS) - 4))]
                out = root / 'results'
                harness.write_checks(out, rows)
                rerun = dict(rows[3], tests=10)
                harness.write_checks(out, [rerun])
                self.assertEqual(len(harness.read(out / 'checks.json')), len(harness.CHECKS) + 1)
                self.assertEqual(harness.check_summary(harness.read(out / 'checks.json'))['tests'], 20)
                self.assertTrue(harness.check_summary(harness.read(out / 'checks.json'))['complete'])
                harness.write_checks(out, [dict(rerun, exit=1)])
                self.assertFalse(harness.check_summary(harness.read(out / 'checks.json'))['complete'])
                (skill / 'SKILL.md').write_text('version two')
                summary = harness.check_summary(harness.read(out / 'checks.json'))
                self.assertFalse(summary['complete'])
                self.assertEqual(summary['tests'], 0)
                self.assertEqual(len(summary['stale']), len(harness.CHECKS))
                (out / '.checks.lock').write_text('another writer')
                before = (out / 'checks.json').read_bytes()
                with self.assertRaises(FileExistsError):
                    harness.write_checks(out, rows)
                self.assertEqual((out / 'checks.json').read_bytes(), before)

    def test_executed_worker_faults_cannot_be_replaced_by_action_plans(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'product.txt').write_text('partial work', encoding='utf-8')
            state = {'worker': {'id': 'w1', 'status': 'running', 'claim': True, 'status_available': True},
                     'candidate_revision': 'r2', 'child_revision': 'r1', 'required_coverage': ['export', 'import'],
                     'child_coverage': ['export'], 'checks': 'pending', 'delivery': 'pending', 'complete': False}
            with self.assertRaises(ValueError): apply(state, 'worker', {'operation': 'claim'}, root)
            with self.assertRaises(ValueError): apply(state, 'worker', {'operation': 'release'}, root)
            apply(state, 'record', {'kind': 'plan', 'value': 'interrupt then inspect then release'}, root)
            with self.assertRaises(ValueError): apply(state, 'worker', {'operation': 'release'}, root)
            apply(state, 'worker', {'operation': 'interrupt'}, root)
            with self.assertRaises(ValueError): apply(state, 'worker', {'operation': 'release'}, root)
            apply(state, 'worker', {'operation': 'status'}, root)
            apply(state, 'worker', {'operation': 'preserve'}, root)
            self.assertEqual((root/'product.recovery.txt').read_text(), 'partial work')
            apply(state, 'worker', {'operation': 'release'}, root)
            self.assertFalse(state['worker']['claim'])
            self.assertEqual((root/'product.txt').read_text(), 'partial work')
            self.assertEqual(apply(state, 'verify', {'kind': 'child'}, root)['result'], 'FAIL')
            state['child_revision'] = 'r2'
            self.assertEqual(apply(state, 'verify', {'kind': 'child'}, root)['result'], 'FAIL')
            state['child_coverage'] = ['export', 'import']
            self.assertEqual(apply(state, 'verify', {'kind': 'child'}, root)['result'], 'PASS')
            state['worker'] = {'id': 'w2', 'status': 'running', 'claim': True, 'status_available': False}
            apply(state, 'worker', {'operation': 'interrupt'}, root)
            with self.assertRaises(ValueError): apply(state, 'worker', {'operation': 'status'}, root)
            with self.assertRaises(ValueError): apply(state, 'worker', {'operation': 'release'}, root)
            self.assertTrue(state['worker']['claim'])
            self.assertEqual(apply({}, 'verify', {'kind': 'child'}, root)['result'], 'FAIL')

    def test_comparison_rejects_context_reuse_and_stale_evidence(self):
        with TemporaryDirectory() as directory:
            root=Path(directory)
            artifact=root/'output.md'; artifact.write_text('Planning only',encoding='utf-8')
            bound={'path':'output.md','sha256':harness.sha(artifact)}
            manifest={'objective':'Clear handoff','benefit':'Named follow-on is reached','purpose':'capability','planned_at':1,
                      'conditions':{role:{'actor_id':role,'fresh_context':True,'started_at':2,'guidance':None if role=='control' else bound,
                                          'output':bound,'planning_endpoint':'saved plan','runtime_endpoint':'future save/reload'} for role in ('control','incumbent','candidate')},
                      'judge':{'actor_id':'judge','fresh_context':True}}
            manifest['conditions']['control']['failure_observed']=False
            self.assertEqual(harness.comparison_ready(manifest,root)['status'],'READY_FOR_BLIND_REVIEW')
            manifest['conditions']['candidate']['actor_id']='control'
            with self.assertRaises(ValueError): harness.comparison_ready(manifest,root)
            manifest['conditions']['candidate']['actor_id']='candidate'
            manifest['judge']['actor_id']='candidate'
            with self.assertRaises(ValueError): harness.comparison_ready(manifest,root)
            manifest['judge']['actor_id']='judge'
            manifest['conditions']['candidate']['fresh_context']=False
            with self.assertRaises(ValueError): harness.comparison_ready(manifest,root)
            manifest['conditions']['candidate']['fresh_context']=True
            artifact.write_text('Changed after capture',encoding='utf-8')
            with self.assertRaises(ValueError): harness.comparison_ready(manifest,root)

    def test_comparison_retention_timing_and_cli_failure_are_explicit(self):
        with TemporaryDirectory() as directory:
            root=Path(directory)
            artifact=root/'output.md'; artifact.write_text('Planning only',encoding='utf-8')
            bound={'path':'output.md','sha256':harness.sha(artifact)}
            manifest={'objective':'Fix missing proof','benefit':'Retains missing proof','purpose':'behavior_fix','planned_at':1,
                      'conditions':{role:{'actor_id':role,'fresh_context':True,'started_at':2,'guidance':None if role=='control' else bound,
                                          'output':bound,'planning_endpoint':'saved plan','runtime_endpoint':'future save/reload'} for role in ('control','incumbent','candidate')},
                      'judge':{'actor_id':'judge','fresh_context':True}}
            manifest['conditions']['control']['failure_observed']=False
            self.assertEqual(harness.comparison_ready(manifest,root)['status'],'RETAIN_ORIGINAL')
            manifest['conditions']['control']['failure_observed']=True
            self.assertEqual(harness.comparison_ready(manifest,root)['status'],'READY_FOR_BLIND_REVIEW')
            manifest['planned_at']=3
            with self.assertRaises(ValueError): harness.comparison_ready(manifest,root)
            manifest['planned_at']=2
            with self.assertRaises(ValueError): harness.comparison_ready(manifest,root)
            manifest['planned_at']=float('nan')
            with self.assertRaises(ValueError): harness.comparison_ready(manifest,root)
            manifest['planned_at']=10**400
            with self.assertRaises(ValueError): harness.comparison_ready(manifest,root)
            manifest['planned_at']=1
            del manifest['conditions']['candidate']['runtime_endpoint']
            with self.assertRaises(ValueError): harness.comparison_ready(manifest,root)
            manifest['conditions']['candidate']['runtime_endpoint']='future save/reload'
            manifest['conditions']['candidate']['actor_id']=''
            source=root/'comparison.json'; harness.save(source,manifest)
            out=root/'result'
            with patch.object(sys,'argv',['verify_skill.py','compare','--comparison',str(source),'--output',str(out)]):
                with self.assertRaises(ValueError): harness.main()
            self.assertFalse(out.exists())

    def test_empty_and_forbidden_traces_fail(self):
        self.assertTrue(score('A1',[],{'built':False}))
        self.assertTrue(score('A3',[{'action':'publish','payload':{},'ok':False}],{'built':True,'checks':'passed'}))

    def test_stale_completion_fails(self):
        self.assertTrue(score('E1',[{'action':'finish','payload':{},'ok':True}],{'checks':'passed','complete':True}))

    def test_evidence_order_is_required(self):
        events=[{'action':'verify','payload':{'kind':kind},'ok':True,'result':{'result':'PASS'}} for kind in ('artifact','review','endpoint','ship')]+[{'action':'finish','payload':{},'ok':True}]
        self.assertEqual(score('E4',events,{'complete':True}),[])
        self.assertTrue(score('E4',list(reversed(events)),{'complete':True}))

    def test_fake_pass_and_failed_run_are_rejected(self):
        self.assertTrue(score('A1',[{'action':'build','payload':{},'ok':True}],{'built':True,'checks':'passed'}))
        events=[{'action':'verify','payload':{'kind':kind},'ok':True,'result':{'result':'FAIL'}} for kind in ('artifact','review','endpoint','ship')]+[{'action':'finish','payload':{},'ok':True}]
        self.assertTrue(score('E4',events,{'complete':True}))

    def test_changed_build_and_checkpoint_invalidate_proof(self):
        with TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'product.txt').write_text('old',encoding='utf-8')
            state={'checks':'passed','delivery':'verified','complete':True,'verifications':dict.fromkeys(('artifact','review','endpoint','ship'),'PASS')}
            apply(state,'build',{'value':'changed'},root)
            self.assertEqual((state['checks'],state['delivery']),('pending','pending'))
            self.assertFalse(state['complete'])
            self.assertFalse(state['verifications'])
            with self.assertRaises(ValueError): apply(state,'checkpoint',{'checks':[]},root)
            with self.assertRaises(ValueError): apply(state,'finish',{},root)

    def test_recovery_fields_and_recovered_verification_sequence(self):
        plan={'owner':'actor','endpoint':'local','dependencies':['copy','validate','switch'],'recovery_point':'copy','rollback':'restore copy'}
        events=[{'action':'record','payload':{'kind':'plan','value':plan},'ok':True}]+[{'action':'migration','payload':{'step':step},'ok':True} for step in ('copy','validate','switch')]
        self.assertEqual(score('P2',events,{'migration':['copy','validate','switch'],'records':{'plan':plan}}),[])
        events=[{'action':'verify','payload':{'kind':'review'},'ok':True,'result':{'result':'FAIL'}}]+[{'action':'verify','payload':{'kind':kind},'ok':True,'result':{'result':'PASS'}} for kind in ('artifact','endpoint','review','ship')]+[{'action':'finish','payload':{},'ok':True}]
        self.assertEqual(score('E4',events,{'complete':True}),[])

    def test_ui_routing_scores_greenfield_gate_and_specified_fast_path(self):
        greenfield_route={
            'route':'product-design',
            'target_status':'pending',
            'mobbin':'bounded-reference-search',
            'intended_outcome':'Family can understand current flight and expected-home status',
        }
        greenfield_events=[
            {'action':'inspect','payload':{'file':'skill/references/ui-ux-integration.md'},'ok':True},
            {'action':'record','payload':{'kind':'design_route','value':greenfield_route},'ok':True},
            {'action':'question','payload':{'text':'Choose one of the three visual directions after Product Design ideation.'},'ok':True},
        ]
        greenfield_state={'records':{'design_route':greenfield_route},'questions':['Choose one'],'built':False}
        self.assertEqual(score('U1',greenfield_events,greenfield_state),[])
        self.assertIn('greenfield UI implementation began before visual target selection',score('U1',greenfield_events,dict(greenfield_state,built=True)))

        specified_events=[
            {'action':'build','payload':{'value':'correct\n'},'ok':True},
            {'action':'verify','payload':{'kind':'artifact'},'ok':True,'result':{'result':'PASS'}},
        ]
        self.assertEqual(score('U2',specified_events,{'built':True,'checks':'passed'}),[])
        self.assertIn('specified small edit triggered redundant design ceremony',score('U2',specified_events+[{'action':'question','payload':{'text':'Choose a design'},'ok':True}],{'built':True,'checks':'passed','questions':['Choose a design']}))

    def test_fixture_preflight_rejects_broken_completed_artifact_and_checkpoint(self):
        contract={'verifiers':[{'fixture':[{'id':'S1'},{'id':'S3'}]}]}
        with TemporaryDirectory() as directory:
            out=Path(directory)/'fresh'
            harness.prepare(out,contract)
            self.assertEqual(harness.preflight(out,['S1','S3']),[])
            (out/'actors/S3/product.txt').write_text('incorrect\n',encoding='utf-8')
            self.assertTrue(harness.preflight(out,['S3']))
            (out/'actors/S1/.deep-a1000001/plan.md').unlink()
            self.assertTrue(harness.preflight(out,['S1']))
            sources=harness.read(out/'sources.json')
            sources[str(harness.SKILL/'SKILL.md')]='stale'
            harness.save(out/'sources.json',sources)
            self.assertTrue(any('installed source drift' in error for error in harness.preflight(out,[])))

    def test_unknown_contract_fails_before_creating_output(self):
        with TemporaryDirectory() as directory:
            out=Path(directory)/'fresh'
            with self.assertRaises(ValueError): harness.prepare(out,{'verifiers':[{'fixture':[{'id':'UNKNOWN'}]}]})
            self.assertFalse(out.exists())

    def test_bridge_rejects_forged_proof_and_invalidates_failed_proof(self):
        with TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'product.txt').write_text('bad',encoding='utf-8')
            state={'required_value':'correct','complete':True,'verifications':dict.fromkeys(('artifact','review','endpoint','ship'),'PASS')}
            for payload in ({'checks':'passed'},{'delivery':'verified'}):
                with self.assertRaises(ValueError): apply(state,'checkpoint',payload,root)
            self.assertEqual(apply(state,'verify',{'kind':'artifact'},root)['result'],'FAIL')
            self.assertFalse(state['complete'])
            self.assertNotIn('ship',state['verifications'])

    def test_closure_requires_complete_current_independent_review(self):
        contract={'verifiers':[{'fixture':[{'id':'A1'}]}]}
        with TemporaryDirectory() as directory:
            out=Path(directory)
            run=out/'run'; run.mkdir()
            harness.save(run/'contract.json',contract)
            harness.save(run/'sources.json',{})
            harness.save(run/'A1-execution.json',{'exit':0})
            harness.save(run/'A1-before.json',{})
            harness.save(run/'A1-after.json',{})
            raw=[{'type':'item.completed','item':{'type':'command_execution','id':'cmd1','aggregated_output':''}},{'type':'turn.completed'}]
            (run/'A1-raw.jsonl').write_text('\n'.join(json.dumps(row) for row in raw),encoding='utf-8')
            review={'A1':{'status':'PASS','raw_sha256':harness.sha(run/'A1-raw.jsonl'),'reviewed_command_ids':['cmd1'],'raw_actions_match':True,'protected_file_changes':[]}}
            review['A1'].update(source_manifest_sha256=harness.sha(run/'sources.json'),before_manifest_sha256=harness.sha(run/'A1-before.json'),after_manifest_sha256=harness.sha(run/'A1-after.json'))
            harness.save(out/'review.json',review)
            selection={'cases':{'A1':{'run':str(run),'review':str(out/'review.json')}}}
            with patch.object(harness,'evaluate',return_value={'case':'A1','status':'PENDING_REVIEW','failures':[]}) as evaluated:
                self.assertEqual(harness.close(selection,contract)['result'],'PASS')
                self.assertEqual(evaluated.call_args.kwargs,{'write':False,'source_check':False})
                harness.save(run/'sources.json',{'changed':'after review'})
                with self.assertRaises(ValueError): harness.close(selection,contract)
                harness.save(run/'sources.json',{})
                review['A1']['reviewed_command_ids']=[]
                harness.save(out/'review.json',review)
                with self.assertRaises(ValueError): harness.close(selection,contract)
                review['A1']['reviewed_command_ids']=['cmd1']
                review['A1']['raw_sha256']='stale'
                harness.save(out/'review.json',review)
                with self.assertRaises(ValueError): harness.close(selection,contract)
            with self.assertRaises(ValueError): harness.close({'cases':{}},contract)

    def test_runtime_identity_is_observed_or_explicitly_unknown(self):
        self.assertIsNone(harness.runtime_identity([])['model'])
        self.assertIsNone(harness.runtime_identity([{'type':'item.completed','model':'actor-claimed-model'}])['model'])
        self.assertEqual(harness.runtime_identity([{'type':'thread.started','model':'observed-model','model_provider':'observed-provider'}])['model'],'observed-model')

    def test_failed_pilot_stops_remaining_actor_launches(self):
        with TemporaryDirectory() as directory:
            out=Path(directory)/'fresh'
            harness.prepare(out,{'verifiers':[{'fixture':[{'id':case} for case in ('A1','A2','A3')]}]})
            with patch.object(sys,'argv',['verify_skill.py','run','--output',str(out)]), patch.object(harness,'check',return_value=[]), patch.object(harness,'run_case',side_effect=lambda out,case,timeout:(case,0)) as launched, patch.object(harness,'evaluate',side_effect=lambda out,case:{'case':case,'status':'FAIL' if case=='A1' else 'PENDING_REVIEW','failures':['deliberate pilot failure'] if case=='A1' else []}), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(harness.main(),1)
            self.assertEqual({call.args[1] for call in launched.call_args_list},{'A1','A2'})

if __name__=='__main__':
    unittest.main()
