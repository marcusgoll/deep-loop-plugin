# Deep Loop - Deterministic Development Protocol

A self-correcting development loop: **PLAN → BUILD → REVIEW → FIX → COMPLETE**

## Quick Start

1. **Triage** the task (complexity + execution mode)
2. **Initialize** `.deep/` state directory
3. **Execute** loop OR spawn Ralph agents
4. **Complete** only when all gates pass

## Step 1: Triage

### Complexity Level

| Level | Signals | Iterations |
|-------|---------|------------|
| **QUICK** | Single file, obvious fix, <30 lines | 3 |
| **STANDARD** | 2-5 files, some design decisions | 10 |
| **DEEP** | 6+ files, architectural, high-stakes | 20 |

### Execution Mode (Ralph vs Sequential)

After determining complexity, decide execution mode:

| Mode | When to Use | How |
|------|-------------|-----|
| **Sequential** | Tasks depend on each other, <3 tasks | Standard loop in-session |
| **Ralph** | 3+ independent tasks, parallelizable | Spawn Task agents |

**Ralph Triage Questions:**
1. Can tasks run independently? (no shared state between tasks)
2. Are there 3+ discrete tasks after planning?
3. Would fresh context per task help? (complex codebase)

**Default behavior:**
- QUICK → Always sequential
- STANDARD → Sequential unless explicitly parallel tasks
- DEEP → Prefer Ralph if 3+ independent tasks identified in PLAN

## Step 2: Initialize State

Create `.deep/` directory:

```bash
mkdir -p .deep
```

**Required files:**
- `.deep/state.json` - Loop state
- `.deep/task.md` - Original task
- `.deep/issues.json` - Start with `[]`

**State template:**
```json
{
  "phase": "PLAN",
  "level": "standard",
  "mode": "sequential",
  "iteration": 0,
  "maxIterations": 10,
  "complete": false,
  "task": "[summary]",
  "startedAt": "[ISO timestamp]"
}
```

## Step 3: Execute by Mode

### Sequential Mode

**QUICK**: Skip PLAN, implement directly, run basic validation
**STANDARD**: Full PLAN → BUILD → REVIEW → FIX loop
**DEEP**: Full loop + self-verification + user checkpoints

### Ralph Mode (Internal v4.0)

Uses Task tool with `subagent_type=general-purpose` to spawn agents.
**No API credits** - uses Max subscription.

#### Ralph Execution Flow

**1. Complete PLAN phase first** - identify all tasks

**2. Create PRD** - write `.deep/prd.json`:

```json
[
  {
    "id": "task-001",
    "story": "What to build",
    "acceptance_criteria": ["Criterion 1", "Criterion 2"],
    "priority": "high",
    "passes": false,
    "attempts": 0
  }
]
```

**3. Update state** - set `"mode": "ralph"` in state.json

**4. Spawn agent for each task** where `passes: false`:

```
Task tool:
  subagent_type: "general-purpose"
  description: "Ralph: [task-id]"
  prompt: |
    You are executing a single task from a PRD backlog.

    ## Task
    ID: [task-id]
    Story: [story]

    ## Acceptance Criteria
    [criteria list]

    ## Instructions
    1. Implement ONLY this task
    2. Run validation (test, lint, typecheck)
    3. Commit: "ralph: [task-id] - [summary]"
    4. Output EXACTLY one of:
       - TASK_PASSED - all criteria met, validation passes
       - TASK_FAILED: [reason] - blocked or failing

    ## Context
    Working directory: [cwd]
    [relevant file paths]
```

**5. Process results:**
- `TASK_PASSED` → Update prd.json: `passes: true`
- `TASK_FAILED` → Increment attempts, log issue, retry (max 3)

**6. Parallel execution** (for truly independent tasks):

Spawn multiple agents in single message:
```
[Task call 1: task-001]
[Task call 2: task-002]
[Task call 3: task-003]
```

**7. Completion:**

When all prd.json tasks have `passes: true`:
- Run final validation
- Output: `<promise>COMPLETE</promise>`

## The Loop Phases

### PLAN Phase
Create `.deep/plan.md` with:
- Problem statement
- Testable acceptance criteria
- Atomic task breakdown
- **Ralph decision**: Mark tasks `[PARALLEL]` or `[SEQUENTIAL]`

### BUILD Phase (Sequential)
For each task:
1. Mark in_progress
2. **Update heartbeat**: Write `lastActivity` to `.deep/state.json` before starting
3. Implement
4. Validate (test, lint, typecheck)
5. **Update heartbeat again** after validation completes
6. Commit if pass
7. Log issue if fail, retry (max 3x)

**Heartbeat**: For long-running tasks, update `.deep/state.json.lastActivity` every 30min to prevent staleness timeout (8hr limit).

### BUILD Phase (Ralph)
1. Convert plan to `.deep/prd.json`
2. Spawn Task agents
3. Collect results
4. Update prd.json

### REVIEW Phase
- Build, tests, types, lint
- Code review patterns
- Create PR if git repo

### FIX Phase
Address `.deep/issues.json`:
1. Fix issue
2. Commit
3. Return to REVIEW

### COMPLETE Phase
All gates pass:
- Tests passing
- No type errors
- No lint errors
- No blocking issues

Output: `<promise>COMPLETE</promise>`

## State Management

Update `.deep/state.json` at transitions:
```json
{ "phase": "BUILD", "mode": "ralph" }
{ "phase": "REVIEW" }
{ "phase": "COMPLETE", "complete": true }
```

## Loop Control

**Check status:** `cat .deep/state.json`
**Cancel:** `/cancel-deep` or create `.deep/FORCE_EXIT`
**Force complete:** Create `.deep/FORCE_COMPLETE` with reason

## Validation Gates

Before COMPLETE, all must pass:
- `npm test` or equivalent
- `npm run typecheck` or `tsc --noEmit`
- `npm run lint`
- `npm run build`

Record in `.deep/test-results.json`:
```json
{
  "results": {
    "tests": { "ran": true, "passed": true },
    "types": { "ran": true, "passed": true },
    "lint": { "ran": true, "passed": true },
    "build": { "ran": true, "passed": true }
  },
  "allPassed": true
}
```

## Git Integration

When in git repo:
1. Create feature branch
2. Atomic commits per task
3. Create PR when BUILD complete
4. Wait for CI to pass
5. Merge to main/master

Record in `.deep/git-results.json` for verification.

## Success Criteria

Complete ONLY when:
- [ ] All acceptance criteria met
- [ ] All tests pass
- [ ] No type errors
- [ ] No lint errors
- [ ] No blocking issues
- [ ] PR merged (if git repo)

## Commands

| Command | Action |
|---------|--------|
| `/deep [task]` | Start deep loop on task |
| `/deep status` | Show current phase and progress |
| `/deep tasks` | List pending persistent tasks |
| `/deep clear-tasks` | Clear all persistent tasks |
| `/deep cleanup` | Remove stale .deep/ directories |
| `/cancel-deep` | Cancel loop, set state to CANCELLED |

### `/deep tasks`
```bash
cat .deep/persistent-tasks.json | jq '.tasks[] | select(.status != "completed")'
```

### `/deep clear-tasks`
```bash
rm .deep/persistent-tasks.json
```

### `/deep cleanup`
```bash
# Remove .deep directories older than 7 days
find . -maxdepth 1 -name ".deep*" -type d -mtime +7 -exec rm -rf {} \;
```

## Subagent Auto-Invocation

Subagents run automatically at specific points:

| Subagent | Trigger | Purpose |
|----------|---------|---------|
| **code-simplifier** | After BUILD completes | Remove complexity, dead code |
| **verify-app** | Before COMPLETE | E2E testing via browser or CLI |

### After BUILD Phase
Automatically spawn code-simplifier:
```
Task tool:
  subagent_type: "general-purpose"
  description: "Simplify code"
  prompt: [contents of src/subagents/code-simplifier.md]
```

### Before COMPLETE Phase
If browser available, spawn verify-app:
```
Task tool:
  subagent_type: "general-purpose"
  description: "Verify app"
  prompt: [contents of src/subagents/verify-app.md]
```

Skip verify-app if:
- No UI to test (library/CLI without visual)
- Tests already cover functionality
- User explicitly skips with `--no-verify`

## Edge Case Handling (v5.0)

The stop hook handles 10 critical edge cases:

### 1. Infinite Loop Prevention
- Hard iteration limit based on complexity (3/10/20)
- BLOCKS exit when limit reached (not just warns)
- Escape: `FORCE_EXIT` or `FORCE_COMPLETE`

### 2. Staleness Detection
- 8-hour threshold for state.json
- Auto-cleanup on session start
- Heartbeat mechanism for long tasks

### 3. Incomplete Work on Exit
- Verifies test-results.json before completion
- Verifies git-results.json (PR created, CI passed, merged)
- Resets to REVIEW if verification fails

### 4. Lost Context Recovery
- Persistent tasks in `.deep/persistent-tasks.json`
- Session start shows resumption context
- Task history preserved across sessions

### 5. Over-engineering Prevention
- code-simplifier subagent prompt after BUILD
- Explicit reminders to avoid abstraction
- Keep solutions minimal

### 6. Clear Definition of Done
- Completion checklist in REVIEW phase
- All criteria must be checked
- `<promise>COMPLETE</promise>` only when verified

### 7. Git Chaos Prevention
- Atomic commit protocol in BUILD
- Branch naming convention
- PR + CI verification before completion

### 8. Parallel Task Coordination
- Lock file mechanism (`.deep/agent.lock`)
- 5-minute timeout for stale locks
- Prevents race conditions on PRD

### 9. Verification Blindness Fix
- E2E verification reminder in REVIEW
- Browser testing via mcp__claude-in-chrome
- Real HTTP requests for APIs

### 10. Stuck Approach Detection
- Track consecutive failures per task
- User escalation after 3 failures
- Creates `.deep/NEEDS_USER` file
- Loop blocked until user responds

## CI/CD Integration

For git repos with `gh` CLI:

### Automatic PR Flow
1. Push branch: `git push -u origin HEAD`
2. Create PR: `gh pr create --title "..." --body "..."`
3. Wait for CI: `gh pr checks --watch`
4. Merge: `gh pr merge --squash --delete-branch`

### git-results.json Template
```json
{
  "repository": {
    "isGitRepo": true,
    "hasGhCli": true,
    "branch": "feature/..."
  },
  "pr": {
    "created": true,
    "number": 123,
    "url": "https://github.com/..."
  },
  "ci": {
    "checked": true,
    "passed": true,
    "status": "success"
  },
  "merge": {
    "merged": true,
    "mergedAt": "ISO timestamp"
  },
  "enforcement": {
    "requirePR": true,
    "requireCIPass": true,
    "requireMerge": true
  },
  "allPassed": true
}
```

### Skip Git Verification
If not using git or gh:
```bash
echo "No git/gh available" > .deep/FORCE_COMPLETE
```
