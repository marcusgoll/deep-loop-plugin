import unittest
from unittest.mock import patch
import test_private_controller as fixtures
from private_worker import run,qualify_service
from worker_units import units

class WorkerTests(unittest.TestCase):
    stop=fixtures.PrivateControllerTests.stop
    def setUp(self):
        fixtures.PrivateControllerTests.setUp(self)
        self.store.create('enabled-outcome.json',{'contract_digest':self.journal.contract_digest})
    def test_owner_wait_is_one_bounded_transition(self):
        self.controller.start(run_id=1,run_attempt=1,model_seconds=600,active_seconds=1200)
        with patch('private_worker.tick',return_value='wait_for_predecessor') as tick:
            self.assertEqual(run(self.store,lambda key:self.controller,window=lambda *a:2000),'wait_for_predecessor')
        self.assertEqual(tick.call_count,1)
    def test_short_remaining_window_never_dispatches(self):
        with patch('private_worker.tick',return_value='stopped_insufficient_execution_window') as tick:
            self.assertEqual(run(self.store,lambda key:self.controller,window=lambda *a:1199),'stopped_insufficient_execution_window')
            self.assertEqual(tick.call_args.kwargs['active_window_remaining'],1199)
            self.assertEqual(tick.call_args.kwargs['expected_contract_digest'],self.journal.contract_digest)
    def test_short_window_stops_even_reconciliation_without_new_tick(self):
        with patch('private_worker.tick') as tick:
            self.assertEqual(run(self.store,lambda key:self.controller,window=lambda *a:60),'stopped_execution_window')
            tick.assert_not_called()
    def test_requires_native_service_identity(self):
        with patch.dict('os.environ',{},clear=True),patch('private_worker.subprocess.run') as process:
            with self.assertRaises(ValueError):qualify_service()
            process.assert_not_called()
    def test_unit_generation_pins_bundle_and_disables_service_restart(self):
        configuration=units('a'*64)
        service=configuration['deep-loop-private-worker.service']
        self.assertIn('bundle-'+('a'*64)+'/private_worker.py',service)
        self.assertIn('RuntimeMaxSec=45',service);self.assertIn('Restart=no',service)
        self.assertIn('ConditionPathExists=',service)

if __name__=='__main__':unittest.main()
