import unittest
from admission import initialize, reserve
from private_launch import launch_plan, recovery_action

D = 'a' * 64

class PrivateLaunchTests(unittest.TestCase):
    def setUp(self):
        self.journal = reserve(initialize(D), D, run_id=1, run_attempt=1,
                               model_seconds=600, active_seconds=1200)
    def plan(self, **kwargs):
        return launch_plan(self.journal, D, run_id=1, run_attempt=1, **kwargs)
    def test_shutdown_is_inside_allowance(self):
        plan = self.plan()
        self.assertEqual(plan['properties']['RuntimeMaxSec'] + plan['properties']['TimeoutStopSec'] + plan['controller_overhead_seconds'], 600)
        self.assertEqual(plan['properties']['KillMode'], 'control-group')
        self.assertEqual(plan['properties']['Restart'], 'no')
    def test_recovery_uses_explicit_uuid_and_same_policy(self):
        session = '12345678-1234-4234-8234-123456789012'
        fresh, resumed = self.plan(), self.plan(session_id=session)
        self.assertEqual(resumed['command'][-3:], ['resume', session, '-'])
        self.assertEqual(resumed['command'][:-3], fresh['command'][:-3])
        self.assertIn('--ignore-user-config', resumed['command'])
        self.assertIn('permissions.deep_loop_private.network.enabled=false', resumed['command'])
        for invalid in ('--last', 'thread-name', '', 1, '00000000-0000-0000-0000-000000000000'):
            with self.assertRaises(ValueError): self.plan(session_id=invalid)
    def test_no_unreserved_launch_or_identity_drift(self):
        with self.assertRaises(ValueError):
            launch_plan(initialize(D), D, run_id=1, run_attempt=1)
        with self.assertRaises(ValueError):
            launch_plan(self.journal, D, run_id=True, run_attempt=1)
        with self.assertRaises(ValueError):
            launch_plan(self.journal, 'b'*64, run_id=1, run_attempt=1)
    def test_no_launch_when_shutdown_cannot_fit(self):
        journal = reserve(initialize(D), D, run_id=1, run_attempt=1, model_seconds=15, active_seconds=15)
        with self.assertRaises(ValueError):
            launch_plan(journal, D, run_id=1, run_attempt=1)
    def test_recovery_requires_inactive_empty_owned_cgroup(self):
        observation = {'unit': self.plan()['unit'], 'active_state': 'failed', 'cgroup_empty': True, 'ownership_verified': True}
        self.assertEqual(recovery_action(self.journal, D, observation), 'reconcile_without_refund')
        for key, value in [('active_state', 'active'), ('cgroup_empty', False)]:
            self.assertEqual(recovery_action(self.journal, D, dict(observation, **{key: value})), 'wait_for_predecessor')
        for value in (None, {}, dict(observation, ownership_verified=False), dict(observation, unit='other')):
            self.assertEqual(recovery_action(self.journal, D, value), 'blocked_missing_ownership_proof')

if __name__ == '__main__': unittest.main()
