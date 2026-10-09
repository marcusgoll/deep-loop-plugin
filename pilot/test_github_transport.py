import json
import subprocess
import unittest
from unittest.mock import patch
from github_transport import GitHubAPI,UncertainAPI

class TransportTests(unittest.TestCase):
    def setUp(self):
        patcher=patch('github_transport.os.geteuid',return_value=0);patcher.start();self.addCleanup(patcher.stop)
    def test_private_identity_fixed_host_and_cleared_environment(self):
        response=subprocess.CompletedProcess([],0,stdout='HTTP/2.0 200 OK\nHeader: value\n\n'+json.dumps({'login':'marcusgoll'}),stderr='')
        with patch('github_transport.subprocess.run',return_value=response) as run:
            self.assertEqual(GitHubAPI()('GET','user'),{'login':'marcusgoll'})
        args=run.call_args.args[0]
        self.assertIn('orchestrator',args);self.assertIn('github.com',args);self.assertIn('GH_CONFIG_DIR',args)
        self.assertEqual(run.call_args.kwargs['timeout'],3)
    def test_unapproved_endpoint_and_wrong_owner_never_invoke_publisher(self):
        for method,route in [('POST','user'),('PUT','repos/marcusgoll/deep-loop-plugin/pulls/1/merge'),('POST','repos/marcusgoll/deep-loop-plugin-other/pulls')]:
            with patch('github_transport.subprocess.run') as run:
                with self.assertRaises(ValueError):GitHubAPI()(method,route)
                run.assert_not_called()
    def test_read_404_is_absent_but_write_uncertainty_is_not_success(self):
        response=subprocess.CompletedProcess([],1,stdout='HTTP/2.0 404 Not Found\n\n{}',stderr='')
        with patch('github_transport.subprocess.run',return_value=response):
            self.assertIsNone(GitHubAPI()('GET','repos/marcusgoll/deep-loop-plugin/git/ref/heads/codex/pilot-admission'))
            with self.assertRaises(UncertainAPI):GitHubAPI()('POST','repos/marcusgoll/deep-loop-plugin/git/refs',{})
    def test_timeout_reports_uncertainty_without_replay(self):
        with patch('github_transport.subprocess.run',side_effect=subprocess.TimeoutExpired('gh',3)) as run:
            with self.assertRaises(UncertainAPI):GitHubAPI()('POST','repos/marcusgoll/deep-loop-plugin/pulls',{})
            self.assertEqual(run.call_count,1)

if __name__=='__main__':unittest.main()
