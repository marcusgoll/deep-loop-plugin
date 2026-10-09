"""Execute the published orchestration snippet against isolated tool responses."""
from pathlib import Path
import json
import re
import subprocess
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'references/thread-tools.md'
TEST = r'''
let calls = 0;
let response;
const tools = { mcp__codex_app__list_threads: async () => { calls++; return response; } };
function assert(value) { if (!value) throw new Error('thread guard failed'); }
(async () => {
  for (const limit of [100, 0, -1, 1.5, '50']) assert(!(await listThreads(limit)).ok);
  assert(calls === 0);
  response = {isError:true, content:[{type:'text', text:'limit invalid'}]};
  assert((await listThreads()).error === 'limit invalid');
  let independentCalls = 0;
  const independentTool = async () => { independentCalls++; return 'independent result'; };
  const failedInventory = await listThreads();
  const independentResult = await independentTool();
  assert(!failedInventory.ok && independentResult === 'independent result' && independentCalls === 1);
  response = {content:[{type:'text',text:'not json'}]};
  assert(!(await listThreads()).ok);
  response = {content:[{type:'text',text:'{"threads":[]}'}]};
  assert((await listThreads(1)).ok);
  response = {structuredContent:{threads:[]}, content:[]};
  assert((await listThreads(50)).ok);
  response = {content:[{type:'text',text:'{"other":[]}'}]};
  assert(!(await listThreads()).ok);
  console.log('PASS: exposed snippet validates limits before dispatch, handles MCP errors and malformed data, preserves independent continuation');
})().catch(error => {console.error(error); process.exitCode=1;});
'''


class ThreadToolSnippetTests(unittest.TestCase):
    def test_published_snippet_handles_bounds_and_tool_failures(self):
        snippet = re.search(
            r'```javascript\n(.*?)\n```',
            SOURCE.read_text(encoding='utf-8'),
            re.S,
        )[1]
        result = subprocess.run(
            ['node', '-e', snippet + '\n' + TEST],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('PASS: exposed snippet validates limits', result.stdout)


if __name__ == '__main__':
    unittest.main()
