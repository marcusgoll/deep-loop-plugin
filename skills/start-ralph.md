# Start Ralph Mode

Create a PRD backlog and enter ralph mode for autonomous long-running task processing.

## What This Does

1. Creates `.deep/prd.json` with a task backlog from user's description
2. Sets up the orchestration state
3. Begins processing tasks using internal Task agents (uses Max subscription, no API key)

## PRD Format

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

## Usage

When user runs `/start-ralph [description]`:

1. **Parse the description** into discrete tasks
2. **Create PRD file** at `.deep/prd.json`
3. **Begin internal ralph loop** - process each task with Task agent

### Creating the PRD

Break down the user's request into atomic tasks. Each task should:
- Be completable in one session
- Have clear acceptance criteria
- Be independently testable

### Processing Tasks

For each task where `passes: false`:

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

### After Each Task

- If TASK_PASSED: Update prd.json with `passes: true`, `completedAt: [timestamp]`
- If TASK_FAILED: Increment `attempts`, log error to `lastError`, retry or move on

### Completion

When all tasks have `passes: true`:
- Output `PROMISE_COMPLETE`
- Append summary to `progress.txt`

## Example

User: `/start-ralph Build a user authentication system with login, logout, and session management`

Creates PRD:
```json
[
  {
    "id": "auth-001",
    "story": "Create user login endpoint with email/password",
    "acceptance_criteria": [
      "POST /api/auth/login accepts email and password",
      "Returns JWT token on success",
      "Returns 401 on invalid credentials"
    ],
    "priority": "high",
    "passes": false
  },
  {
    "id": "auth-002",
    "story": "Create user logout endpoint",
    "acceptance_criteria": [
      "POST /api/auth/logout invalidates session",
      "Requires valid JWT token"
    ],
    "priority": "high",
    "passes": false
  },
  {
    "id": "auth-003",
    "story": "Add session management middleware",
    "acceptance_criteria": [
      "Protected routes require valid JWT",
      "Expired tokens return 401",
      "Token refresh mechanism works"
    ],
    "priority": "high",
    "passes": false
  }
]
```

Then spawns Task agents to implement each.
