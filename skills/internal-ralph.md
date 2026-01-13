# Internal Ralph Mode (Max Subscription)

## Overview

Internal Ralph processes a PRD backlog using Claude Code's built-in Task tool to spawn subagents. Each task gets fresh context while using the SAME Max subscription - no API key required.

## How It Works

```
Main Session (You - Orchestrator)
    │
    ├── Read .deep/prd.json
    │
    ├── For each task where passes=false:
    │       │
    │       └── Spawn Task agent (subagent_type=general-purpose)
    │             ├── Agent implements task
    │             ├── Agent runs verification
    │             └── Agent returns result
    │
    ├── Update prd.json with result
    │
    └── Continue until all tasks pass or max iterations
```

## Why This Works

| External Ralph (broken) | Internal Ralph (works) |
|------------------------|----------------------|
| Spawns new CLI process | Uses Task tool subagents |
| `-p` flag = API mode | Subagents = same session |
| Requires API key | Uses Max subscription |
| External orchestration | Internal orchestration |

## PRD Format

Create `.deep/prd.json`:
```json
[
  {
    "id": "task-001",
    "story": "Description of what to build",
    "acceptance_criteria": [
      "Criterion 1",
      "Criterion 2"
    ],
    "priority": "high",
    "passes": false,
    "attempts": 0,
    "lastError": null
  }
]
```

## Execution Protocol

### Step 1: Read PRD
```
Read .deep/prd.json and identify next task where passes=false
```

### Step 2: Spawn Task Agent
```
Use Task tool with:
- subagent_type: "general-purpose"
- description: "[task-id]: [brief description]"
- prompt: |
    You are executing a single task from a PRD backlog.

    TASK: [task story]

    ACCEPTANCE CRITERIA:
    [list criteria]

    INSTRUCTIONS:
    1. Implement the task to meet ALL acceptance criteria
    2. Run appropriate verification (tests, lint, types)
    3. Make a git commit if successful
    4. Report: TASK_PASSED or TASK_FAILED with details

    Work autonomously. Do not ask questions - make reasonable decisions.
```

### Step 3: Process Result
- If TASK_PASSED: Update prd.json with `passes: true`
- If TASK_FAILED: Increment `attempts`, log error, try next task or retry

### Step 4: Continue or Complete
- If all tasks have `passes: true`: Output PROMISE_COMPLETE
- If tasks remain: Go to Step 1
- If max iterations reached: Output RALPH_TIMEOUT

## Progress Tracking

Append to `progress.txt` after each task:
```
## [timestamp] - [task-id]
Status: PASSED/FAILED
Summary: [what was done]
---
```

## Invocation

From Claude Code, say:
```
/internal-ralph
```

Or manually:
```
Run internal ralph mode on .deep/prd.json with max 10 iterations
```

## Advantages Over External Ralph

1. **No API key needed** - Uses Max subscription
2. **Fresh context per task** - Task agents get clean slate
3. **No TTY issues** - All internal to Claude Code
4. **Better error handling** - Main session can retry/adjust
5. **Visible progress** - See each task as it runs
6. **Can run in background** - Use `run_in_background: true`

## Parallel Execution (Advanced)

For independent tasks, spawn multiple agents simultaneously:
```
Launch Task agents for task-001, task-002, task-003 in parallel
```

This maximizes throughput while staying within Max subscription.
