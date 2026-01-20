# Diagnose Hook Errors

Troubleshoot Claude Code hook errors (PreToolUse, PostToolUse, etc.)

## When to Use

- See "PreToolUse:* hook error" or "PostToolUse:* hook error"
- Hooks silently failing
- Plugin not working as expected

## Diagnosis Steps

### 1. Check Python Alias (Windows)

```bash
python3 --version 2>&1
```

**If not found:**
```bash
cp "C:/Users/Marcus Gollahon/AppData/Local/Programs/Python/Python311/python.exe" \
   "C:/Users/Marcus Gollahon/AppData/Local/Programs/Python/Python311/python3.exe"
```

### 2. Find Hooks Using python3

```bash
grep -r "python3" ~/.claude/plugins/marketplaces --include="*.json" 2>/dev/null
```

### 3. Check Enabled Plugins

```bash
grep -A 20 '"enabledPlugins"' ~/.claude/settings.json
```

### 4. Test Hook Manually

For a hook command like:
```
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/security_reminder_hook.py
```

Test with:
```bash
cd ~/.claude/plugins/marketplaces/claude-plugins-official/plugins/security-guidance
echo '{"tool_name":"Write","tool_input":{"file_path":"test.txt"}}' | python3 hooks/security_reminder_hook.py
```

### 5. Common Fixes

| Error | Fix |
|-------|-----|
| `python3 not found` | Create alias (see step 1) |
| `ModuleNotFoundError` | `pip install <module>` |
| `Permission denied` | Check file permissions |
| `Hook timeout` | Increase timeout in plugin.json |

## Quick Disable

To disable a problematic plugin temporarily:

```bash
# Edit ~/.claude/settings.json
# Set the plugin to false:
"security-guidance@claude-plugins-official": false
```

Then restart Claude Code session.
