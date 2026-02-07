---
name: deep-cleanup
description: Clean up stale deep loop files. Use when user asks to 'clean up', 'remove .deep directories'. Removes old session artifacts.
version: 11.0.0
allowed-tools: Bash
---

# Deep Cleanup

Manually clean up stale files from deep loop sessions.

## What This Does

1. Removes stale `.deep/` directories older than 7 days
2. Removes stale plan files from `~/.claude/plans/`
3. Cleans up orphaned lock files
4. Resets stuck escalation files

## Usage

```bash
# Remove .deep directories older than 7 days
find . -maxdepth 1 -name ".deep*" -type d -mtime +7 -exec rm -rf {} \;

# Remove stale plans
find ~/.claude/plans -name "*.md" -mtime +7 -delete

# Remove lock files
rm -f .deep/agent.lock

# Remove escalation files
rm -f .deep/NEEDS_USER
```

## When to Use

- After abandoned deep loops
- When session-start hook reports stale directories
- Before starting a fresh project
- To clear accumulated temp files

## Manual Cleanup Commands

### Reset Everything
```bash
rm -rf .deep
```

### Keep State but Clear Issues
```bash
echo '[]' > .deep/issues.json
```

### Force Exit Stuck Loop
```bash
touch .deep/FORCE_EXIT
```

### Skip Verification
```bash
echo "Manual cleanup" > .deep/FORCE_COMPLETE
```
