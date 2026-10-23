"""Record-only ready-work ranking; no scheduler or permission claim."""
import copy
import datetime
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import deep_loop


def task(id, **fields):
    value = dict(id=id, title=id, kind='task', status='pending', acceptance='Observed result')
    value.update(fields)
    return value


def selection(**fields):
    if 'readyAge' in fields:
        age=fields.pop('readyAge')
        if type(age) is int and age >= 0:
            fields['readySince']=(datetime.datetime(2026,10,9,12,1,tzinfo=datetime.timezone.utc)-datetime.timedelta(seconds=age)).isoformat()
        else:
            fields['readySince']=age
    return dict(evidence='Coordinator inspected approved priority/requirement and eligible-round age', **fields)


def state(*tasks, **fields):
    value = dict(schemaVersion=4, active=True, complete=False, phase='BUILD', tasks=list(tasks))
    value.update(fields)
    return value


def policy_state(*tasks, **fields):
    return state(*tasks, queuePolicy=dict(kind='outcome', agingAfterSeconds=3, asOf='2026-10-09T12:01:00Z', evidence='Approved bounded queue policy'), **fields)


class WorkPriorities(unittest.TestCase):
    def ids(self, result):
        return [t['id'] for t in result['ready']]

    def test_legacy_exact_order_and_shape(self):
        result = deep_loop.task_queue(state(task('z'), task('a')))
        self.assertEqual(self.ids(result), ['z', 'a'])
        self.assertEqual(set(result), {'queueState', 'ready', 'waiting'})

    def test_user_priority_precedes_correctness_and_age(self):
        result = deep_loop.task_queue(policy_state(
            task('old', selection=selection(readyAge=100, blockingCorrectness=True)),
            task('chosen', selection=selection(userPriority=2))))
        self.assertEqual(self.ids(result), ['chosen', 'old'])
        self.assertEqual(result['selection']['basis'], 'record_only')

    def test_correctness_then_required_transitive_unlocks(self):
        result = deep_loop.task_queue(policy_state(task('plain'),
            task('unlock'), task('middle', dependsOn=['unlock']),
            task('required', dependsOn=['middle'], selection=selection(required=True)),
            task('fix', selection=selection(blockingCorrectness=True))))
        self.assertEqual(self.ids(result), ['fix', 'unlock', 'plain'])
        scores = {row['id']: row for row in result['selection']['ranking']}
        self.assertEqual(scores['unlock']['potentialRequiredDescendants'], ['required'])

    def test_aging_promotes_within_priority_without_mutation(self):
        value = policy_state(task('fix', selection=selection(blockingCorrectness=True)),
            task('old', selection=selection(readyAge=3)))
        before = copy.deepcopy(value)
        with patch('deep_loop.subprocess.run', side_effect=AssertionError('No producer')):
            result = deep_loop.task_queue(value)
        self.assertEqual(self.ids(result), ['old', 'fix'])
        self.assertEqual(value, before)
        self.assertTrue(result['selection']['ranking'][0]['aged'])

    def test_age_then_stable_id_breaks_ties(self):
        result = deep_loop.task_queue(policy_state(task('z'), task('b', selection=selection(readyAge=2)), task('a')))
        self.assertEqual(self.ids(result), ['b', 'a', 'z'])

    def test_oldest_aged_task_precedes_fresh_correctness(self):
        result = deep_loop.task_queue(policy_state(task('fix', selection=selection(blockingCorrectness=True)),
            task('age3', selection=selection(readyAge=3)), task('age5', selection=selection(readyAge=5))))
        self.assertEqual(self.ids(result), ['age5', 'age3', 'fix'])

    def test_hard_filters_before_ranking(self):
        result = deep_loop.task_queue(policy_state(task('ready'),
            task('claimed', owner='live-writer', selection=selection(userPriority=999)),
            task('blocked', status='blocked', blocker='Wait', nextAction='Observe', selection=selection(readyAge=999)),
            task('dep', dependsOn=['blocked'], selection=selection(userPriority=999)),
            task('running', status='running', owner='worker'),
            task('ship', stage='ship', selection=selection(userPriority=999))))
        self.assertEqual(self.ids(result), ['ready'])
        self.assertEqual({r['task']['id'] for r in result['waiting']}, {'claimed', 'blocked', 'dep', 'running', 'ship'})

    def test_session_closed_and_blocker_cannot_be_waived(self):
        for field in ({'active':False}, {'complete':True}, {'blocker':'Authority unavailable'}):
            with self.subTest(field=field):
                result = deep_loop.task_queue(policy_state(task('high', selection=selection(userPriority=999)), **field))
                self.assertEqual(result['ready'], [])

    def test_done_cancelled_descendants_do_not_boost(self):
        result = deep_loop.task_queue(policy_state(task('z'), task('a'),
            task('cancelled', status='cancelled', reason='Authorized scope exclusion', dependsOn=['z'], selection=selection(required=True))))
        self.assertEqual(self.ids(result), ['a','z'])
        self.assertEqual(result['selection']['ranking'][1]['potentialRequiredDescendants'], [])

    def test_missing_age_unavailable_and_no_live_clock(self):
        value=policy_state(task('a'))
        parser=datetime.datetime.fromisoformat
        with patch('deep_loop.datetime.datetime') as clock:
            clock.fromisoformat.side_effect=parser
            result=deep_loop.task_queue(value)
            clock.now.assert_not_called()
        row=result['selection']['ranking'][0]
        self.assertIsNone(row['ageSeconds'])
        self.assertFalse(row['aged'])
        self.assertEqual(result['selection']['asOf'],value['queuePolicy']['asOf'])

    def test_cancelled_chain_never_boosts_or_satisfies_readiness(self):
        result=deep_loop.task_queue(policy_state(task('z'),task('a'),
            task('cancelled',status='cancelled',reason='Authorized exclusion',dependsOn=['z']),
            task('required',dependsOn=['cancelled'],selection=selection(required=True,userPriority=999))))
        self.assertEqual(self.ids(result),['a','z'])
        self.assertEqual(result['selection']['ranking'][1]['potentialRequiredDescendants'],[])
        self.assertEqual(result['waiting'][0]['task']['id'],'required')
        self.assertTrue(any('Unfinished prerequisites: cancelled' in reason for reason in result['waiting'][0]['reasons']))

    def test_invalid_policy_rejected(self):
        for policy in (None, {}, {'kind':'automatic'},
                {'kind':'outcome','agingAfterSeconds':True,'evidence':'x','asOf':'2026-10-09T12:01:00Z'},
                {'kind':'outcome','agingAfterSeconds':0,'evidence':'x','asOf':'2026-10-09T12:01:00Z'},
                {'kind':'outcome','agingAfterSeconds':1,'evidence':'','asOf':'2026-10-09T12:01:00Z'},
                {'kind':'outcome','agingAfterSeconds':1,'evidence':'x','asOf':'2026-10-09T12:01:00Z','clock':'now'}):
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                deep_loop.task_queue(state(task('a'), queuePolicy=policy))

    def test_invalid_selection_rejected(self):
        for selected in (None, {}, selection(userPriority=True), selection(userPriority=-1),
                selection(readyAge=-1), selection(readyAge=0.1), selection(blockingCorrectness='yes'),
                selection(required=1), selection(unknown='x')):
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                deep_loop.task_queue(policy_state(task('a', selection=selected)))

    def test_invalid_times_rejected(self):
        for date in ('2026-10-09T12:02:00Z','2026-10-09T12:00:00','2026-10-09T12:00:00+01:00','not-a-date'):
            with self.subTest(date=date), self.assertRaises(ValueError):
                deep_loop.task_queue(policy_state(task('a',selection=selection(readySince=date))))
        value=policy_state(task('a')); value['queuePolicy']['asOf']='not-a-date'
        with self.assertRaises(ValueError): deep_loop.task_queue(value)

    def test_only_canonical_utc_timestamp_grammar(self):
        for date in ('2026-10-09 12:00:00Z', '20261009T120000Z', '2026-10-09X12:00:00Z',
                     '2026-10-09🦉12:00:00Z', '2026-10-09T12:00Z', '2026-10-09T12:00:00+0000',
                     '2026-10-09T12:00:00z', '2026-10-09T12:00:00,5Z'):
            with self.subTest(date=date), self.assertRaises(ValueError):
                deep_loop.task_queue(policy_state(task('a',selection=selection(readySince=date))))
        for date in ('2026-10-09T12:00:00.125Z', '2026-10-09T12:00:00+00:00',
                     '2026-10-09T12:00:00.125+00:00'):
            with self.subTest(date=date):
                row=deep_loop.task_queue(policy_state(task('a',selection=selection(readySince=date))))['selection']['ranking'][0]
                self.assertGreater(row['ageSeconds'],0)
        value=policy_state(task('a'));value['queuePolicy']['asOf']='2026-10-09 12:01:00Z'
        with self.assertRaises(ValueError): deep_loop.task_queue(value)

    def test_bad_graph_still_rejected(self):
        with self.assertRaises(ValueError):
            deep_loop.task_queue(policy_state(task('a', dependsOn=['missing'], selection=selection(userPriority=999))))
        with self.assertRaises(ValueError):
            deep_loop.task_queue(policy_state(task('a', dependsOn=['b']), task('b', dependsOn=['a'])))

    def test_no_policy_does_not_interpret_selection(self):
        self.assertEqual(self.ids(deep_loop.task_queue(state(task('z', selection={'userPriority':999}),task('a')))), ['z','a'])

    def test_cli_read_only_current_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary); checkpoint=path/'.deep-12345678'; checkpoint.mkdir()
            value=policy_state(task('z'), task('a', selection=selection(userPriority=2)))
            (checkpoint/'state.json').write_text(json.dumps(value)); (checkpoint/'plan.md').write_text('Approved bounded scope')
            (path/'.deep-current.json').write_text(json.dumps({'path':str(checkpoint)}))
            before={str(p.relative_to(path)):p.read_bytes() for p in path.rglob('*') if p.is_file()}
            result=subprocess.run([sys.executable,str(Path(deep_loop.__file__)), 'next','--path',str(checkpoint)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(self.ids(json.loads(result.stdout)),['a','z'])
            after={str(p.relative_to(path)):p.read_bytes() for p in path.rglob('*') if p.is_file()}
            self.assertEqual(before,after)


if __name__ == '__main__':
    unittest.main()
