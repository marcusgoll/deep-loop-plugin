# Safe thread-tool calls

Read before composing thread-tool calls in `functions.exec`. The installed app owns its schema; the evidenced `list_threads` limit is 1..50. Keep error results as data so an independent operation can still run. Inspect `isError` before decoding text; use structured content when available. Recheck live definitions if the app changes.

Use this guarded call in the orchestration cell:

```javascript
async function listThreads(limit = 50) {
  if (!Number.isInteger(limit) || limit < 1 || limit > 50) {
    return { ok: false, error: "list_threads limit must be an integer from 1 to 50" };
  }
  const response = await tools.mcp__codex_app__list_threads({ limit });
  const content = response.content?.find(item => item.type === "text")?.text;
  if (response.isError) return { ok: false, error: content || "list_threads failed" };
  try {
    const value = response.structuredContent ?? JSON.parse(content);
    if (!value || !Array.isArray(value.threads)) throw new Error("thread inventory missing");
    return { ok: true, value };
  } catch (error) {
    return { ok: false, error: "Invalid thread response: " + error.message };
  }
}
```

Then call `listThreads()` and inspect `ok` before selecting a chat; print only the relevant inventory fields. This local caller guard does not change the platform's exposed schema or establish that an error response is a successful inventory.
