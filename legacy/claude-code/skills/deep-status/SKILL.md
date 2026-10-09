---
name: deep-status
description: Check deep loop progress and session state. Use when user asks 'what status', 'where are we', 'deep status'. Shows phase, tasks, and iteration count.
version: 11.0.0
allowed-tools: Read, Glob, Grep
---

# Deep Loop Status

Show real session state from `.deep-*` files. No phantom data.

## Step 1: Find Session

Use Glob to find active sessions:
```
Glob({ pattern: ".deep-*/state.json" })
```

Also check legacy:
```
Glob({ pattern: ".deep/state.json" })
```

If **no state.json found**, output:

```
DEEP LOOP v11.0.0

No active session.

Start:  /deep <task>
Quick:  /deep quick <task>
Queue:  /deep execute
```

Then STOP.

## Step 2: Read State

For each session found, use Read tool on `state.json`. Extract these fields (all from actual state):

- `sessionId`
- `phase` (CHALLENGE | RLM_EXPLORE | PLAN | BUILD | REVIEW | FIX | SHIP | COMPLETE)
- `iteration` / `maxIterations`
- `mode` (internal | external | quick)
- `buildMode` (multi-agent | single)
- `startedAt`
- `lastActivity`
- `task`
- `current_step`
- `active`
- `complete`

## Step 3: Read Task Description

Read `task.md` from session dir if it exists. Use first line as task description. Fall back to `state.task` field.

## Step 4: Scan Session Files

Use Glob to find all files in the session directory:
```
Glob({ pattern: ".deep-{session8}/*" })
```

For each known file, report presence. For files with countable data, read and summarize:

- **plan.md**: Use Grep to count atomic task headers (lines matching `^## ` or `^### Task`)
- **issues.json**: Read, report array length
- **hook-errors.log**: Use Grep to count lines matching `^\[` (each error entry starts with timestamp)
- **test-results.json**: Read, report pass/fail if present
- **decisions.md**: Just report exists/missing
- **lessons-learned.md**: Just report exists/missing
- **exploration.md**: Just report exists/missing
- **FORCE_EXIT**: If exists, warn user

## Step 5: Output Status

Format output as:

```
DEEP LOOP v11.0.0

Session:    {sessionId}
Phase:      {phase}
Iteration:  {iteration}/{maxIterations}
Mode:       {mode}    Build: {buildMode}
Task:       {first line of task.md or state.task}
Step:       {current_step or "—"}
Elapsed:    {humanized duration from startedAt to now}
```

**Elapsed calculation:** Subtract `startedAt` from current time. Format as `Xh Ym` or `Xm` if under 1 hour.

**Staleness warning:** If `lastActivity` is more than 1 hour ago, append:
```
!! STALE — last activity {humanized time} ago
   Resume: /deep    Cancel: /cancel-deep    Force exit: touch .deep-{session8}/FORCE_EXIT
```

**Files section:**
```
Files:
  task.md            exists
  plan.md            exists (4 atomic tasks)
  issues.json        exists (2 issues)
  hook-errors.log    exists (3 errors)
  decisions.md       missing
  test-results.json  missing
```

Only show files that are relevant. Always show: task.md, plan.md, issues.json, hook-errors.log. Show others only if they exist.

**FORCE_EXIT warning:**
```
!! FORCE_EXIT flag is set — session will exit on next stop hook
```

## Step 6: Actionable Next Steps

Based on current phase, output one line:

| Phase | Next Step |
|-------|-----------|
| CHALLENGE | "Awaiting user confirmation on approach" |
| RLM_EXPLORE | "Exploring codebase, writing exploration.md" |
| PLAN | "Writing plan.md with atomic task breakdown" |
| BUILD | "Implementing. {N} tasks in plan." |
| REVIEW | "Validating: tests, lint, types, code-review, security-audit" |
| FIX | "{N} issues in issues.json to resolve" |
| SHIP | "Pushing, creating PR, writing lessons-learned" |
| COMPLETE | "Session finished. See lessons-learned.md" |

## NOW EXECUTE

1. Glob for `.deep-*/state.json`
2. If none found, show "no active session" and stop
3. Read state.json with Read tool
4. Read task.md with Read tool (if exists)
5. Glob session directory for all files
6. Read countable files (issues.json, hook-errors.log) for summary counts
7. Output formatted status
8. Output next steps based on phase
