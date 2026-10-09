---
name: deep-execute
description: Process queued tasks from .deep/tasks.md. Use when user asks to 'execute queue', 'process tasks', 'run queued work'. Supports multi-session claim-based coordination with git conflict handling.
version: 11.0.0
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Task, Skill
---

# Deep Execute - Concurrent Worker Orchestrator

Launch N concurrent Claude CLI workers to process `.deep/tasks.md` in parallel. Each worker claims ONE task, executes PLAN->BUILD->REVIEW->FIX->SHIP, then loops for the next.

## Architecture

```
/deep execute --workers 3
  |
  v
Orchestrator (this skill): read tasks, generate script, launch
  |
  v
.deep/execute.sh (bash master)
  |-- worker 1 → claude -p "claim+execute" → loops until QUEUE_EMPTY
  |-- worker 2 → (staggered +2s)
  |-- worker 3 → (staggered +4s)
  |
  v
Wait all, print summary, notify Telegram
```

## File Structure

```
.deep/
├── tasks.md              # Active task queue (input)
├── completed-tasks.md    # Done tasks with commit SHA (output)
├── claims.json           # Lock file for multi-worker coordination
├── git-conflicts.json    # Tasks blocked by git conflicts
├── execute.sh            # Generated worker script
├── worker-1.log          # Worker 1 output
├── worker-2.log          # Worker 2 output
├── worker-N.log          # Worker N output
└── FORCE_EXECUTE_EXIT    # Touch to stop all workers
```

## Claims System

### claims.json Format

```json
{
  "task-001": {
    "claimedBy": "w1-a3f2b1c0",
    "claimedAt": "2026-01-20T15:00:00Z",
    "expiresAt": "2026-01-20T15:30:00Z"
  }
}
```

### Claim Rules

- **Timeout:** 30 minutes
- **Before claiming:** Check if task already claimed
- **On completion:** Remove claim, move task to completed
- **On failure:** Release claim for retry
- **Stale claims:** Claims older than 30 min can be stolen

## Multi-Worker Git Coordination

```
Worker A: claim task-001 → implement → commit → push ✓
Worker B: claim task-003 → implement → commit → push ✗ (rejected)
                                                    ↓
                                              fetch + rebase
                                                    ↓
                                        (conflict?) → git-blocked + recovery branch
                                        (clean?)    → push retry ✓
```

### Conflict Resolution

| Scenario | Behavior |
|----------|----------|
| **Clean rebase** | Auto-retry push (up to 3 attempts) |
| **File conflict** | Mark git-blocked, save recovery branch, continue next task |
| **Same file, no conflict** | Git auto-merges, push succeeds |

### git-conflicts.json

```json
{
  "task-005": {
    "blockedAt": "2026-01-20T15:30:00Z",
    "session": "w2-b4e2c1d0",
    "conflictingFiles": ["src/utils/helpers.ts"],
    "localCommit": "def789",
    "remoteCommit": "123abc",
    "recoveryBranch": "deep-recovery/task-005-w2-b4e2c1d0"
  }
}
```

### Recovery

```bash
git branch | grep deep-recovery/
git checkout deep-recovery/task-005-w2-b4e2c1d0
# Resolve conflicts, merge to main
```

### Best Practices for Parallel Workers

1. **Partition tasks by directory** - Minimize file overlap
2. **3-4 workers max** - Beyond this, git contention increases
3. **Use worktrees** for true isolation (different working directories)

## Configuration

| Setting | Value | Description |
|---------|-------|-------------|
| Workers default | 3 | Concurrent claude processes |
| Workers max | 8 | Hard cap |
| Claim timeout | 30 min | Time before claim expires |
| Max retries | 3 | Attempts per task before skipping |
| Max push attempts | 3 | Rebase+push retries before git-blocked |
| Stagger delay | 2s | Delay between worker launches |

## NOW EXECUTE

When invoked:

### Step 1: Read Queue

```bash
# Count pending tasks
PENDING=$(grep -c "^## \[ \] task-" .deep/tasks.md 2>/dev/null || echo "0")
```

Show summary:
```
=== Deep Execute Queue ===
Pending tasks: {N}
{list first 10 task titles}
===========================
```

If PENDING == 0: output "No tasks in queue. Use /deep-add to add tasks." and STOP.

### Step 2: Parse Workers

Parse `--workers N` from user input (or default 3).

Rules:
- Default: 3
- Cap at task count (no idle workers)
- Max: 8
- Min: 1

```
Workers: min(requested, pending, 8)
```

### Step 3: Generate Script

Get the plugin path for generate-execute-script.js:

```bash
PLUGIN_DIR=$(find ~/.claude/plugins -path "*/deep-loop/*/src/generate-execute-script.js" -print -quit 2>/dev/null | xargs dirname)
```

Generate the execute script:

```bash
node "$PLUGIN_DIR/generate-execute-script.js" {workers} "{cwd}"
```

This creates `.deep/execute.sh`.

### Step 4: Launch

Run the script in background:

```bash
bash .deep/execute.sh
```

Use `run_in_background: true` on the Bash tool.

### Step 5: Show Monitoring

Output:
```
=== Deep Execute Launched ===
Workers: {N}
Queue: {pending} tasks

Monitor logs:
  tail -f .deep/worker-*.log

Force stop:
  touch .deep/FORCE_EXECUTE_EXIT

Check progress:
  grep -c "TASK_COMPLETE" .deep/worker-*.log
  cat .deep/completed-tasks.md
=============================
```

Done. The bash script handles all worker lifecycle, aggregation, and Telegram notification.
