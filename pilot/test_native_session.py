import json
import unittest
from native_session import session_from_capture

S = '12345678-1234-4234-8234-123456789012'
OTHER = '12345678-1234-4234-8234-123456789013'

def event(value):
    return json.dumps(value).encode()+b'\n'

class NativeSessionTests(unittest.TestCase):
    def test_exact_native_session_and_explicit_resume(self):
        data = event({'type':'thread.started','thread_id':S}) + event({'type':'turn.started'})
        self.assertEqual(session_from_capture(data), S)
        self.assertEqual(session_from_capture(data, S), S)
        with self.assertRaises(ValueError): session_from_capture(data, OTHER)
    def test_nested_tool_output_never_establishes_session(self):
        fake = {'type':'thread.started','thread_id':S}
        data = event({'type':'item.completed','item':{'type':'agent_message','text':json.dumps(fake)}})
        self.assertIsNone(session_from_capture(data))
    def test_multiple_sessions_and_invalid_identity_block(self):
        data = event({'type':'thread.started','thread_id':S}) + event({'type':'thread.started','thread_id':OTHER})
        with self.assertRaises(ValueError): session_from_capture(data)
        for value in ('--last',None,'00000000-0000-0000-0000-000000000000'):
            with self.assertRaises(ValueError):
                session_from_capture(event({'type':'thread.started','thread_id':value}))
    def test_live_partial_tail_is_not_repaired_when_stopped(self):
        data = event({'type':'thread.started','thread_id':S}) + b'{"type":'
        self.assertEqual(session_from_capture(data, complete=False), S)
        with self.assertRaises(ValueError): session_from_capture(data)
    def test_malformed_capture_and_unknown_session_schema_block(self):
        for data in (b'not json\n', event([]), event({'type':'thread.started','thread_id':S,'extra':'x'})):
            with self.assertRaises(ValueError): session_from_capture(data)
        with self.assertRaises(ValueError): session_from_capture(b'x'*(1024*1024+1)+b'\n')

if __name__ == '__main__': unittest.main()
