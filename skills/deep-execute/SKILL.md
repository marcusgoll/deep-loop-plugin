---
name: deep-execute
description: Execute tasks from the shared deep loop task queue. Processes tasks with claim-based coordination for multi-session support.
version: 9.0.0
---

# Deep Execute - Task Queue Processor

Process tasks from `.deep/tasks.md` with claim-based coordination for multi-session execution.

## File Structure

```
.deep/
├── tasks.md              # Active task queue
├── completed-tasks.md    # Done tasks with commit SHA
└── claims.json           # Lock file for multi-session coordination
```

## Claims System

### claims.json Format

```json
{
  "task-001": {
    "claimedBy": "abc12345",
    "claimedAt": "2026-01-20T15:00:00Z",
    "expiresAt": "2026-01-20T15:30:00Z"
  }
}
```

### Claim Rules

- **Timeout:** 30 minutes (configurable)
- **Before claiming:** Check if task already claimed
- **On completion:** Remove claim, move task to completed
- **On failure:** Release claim for retry
- **Stale claims:** Claims older than 30 min can be stolen

## Compaction Recovery

**CRITICAL:** Context compaction can happen mid-execution. All state MUST be recoverable from files.

### Recovery Check (Run First)

Before initializing, check if we're resuming from compaction:

```bash
if [ -f .deep/progress.json ]; then
  PHASE=$(cat .deep/progress.json | grep -o '"phase": *"[^"]*"' | cut -d'"' -f4)
  CURRENT=$(cat .deep/progress.json | grep -o '"currentTask": *"[^"]*"' | cut -d'"' -f4)

  if [ "$PHASE" != "COMPLETE" ] && [ -n "$CURRENT" ] && [ "$CURRENT" != "null" ]; then
    echo "RESUMING: Found in-progress execution"
    echo "  Task: $CURRENT"
    echo "  Phase: $PHASE"
    # Skip to Step 2 with existing claim
  fi
fi
```

### Resume Logic

| State Found | Action |
|-------------|--------|
| No progress.json | Fresh start -> Step 0 |
| phase=COMPLETE | Fresh start -> Step 0 |
| phase=PLAN + currentTask | Resume -> Skip to Step 4a |
| phase=BUILD + currentTask | Resume -> Skip to Step 4b |
| phase=REVIEW + currentTask | Resume -> Skip to Step 4c |
| phase=FIX + currentTask | Resume -> Skip to Step 4d |
| phase=SHIP + currentTask | Resume -> Skip to Step 4e |
| phase=INIT + currentTask | Resume -> Skip to Step 2 |

### State Persistence Points

Update progress.json at EVERY transition:
1. After claiming task (currentTask set, phase=PLAN)
2. Before implementation (phase=BUILD, step=implementing)
3. After simplifier runs (step=simplifying)
4. Before validation (phase=REVIEW, step=validating)
5. If issues found (phase=FIX, step=fixing)
6. Before commit (phase=SHIP, step=committing)
7. After completion (tasksCompleted++, currentTask=null)

## Execution Flow

### Step 0: Initialize Progress File

Before starting execution, create/update `.deep/progress.json`:

```bash
mkdir -p .deep

# Get session ID
SESSION_ID=$(echo $RANDOM | md5sum | head -c 8)

# Count pending tasks
PENDING=$(grep -c "^## \[ \] task-" .deep/tasks.md 2>/dev/null || echo "0")
COMPLETED=$(grep -c "^## \[x\] task-" .deep/completed-tasks.md 2>/dev/null || echo "0")

# Create progress file
cat > .deep/progress.json << EOF
{
  "currentTask": null,
  "session": "$SESSION_ID",
  "phase": "INIT",
  "step": null,
  "startedAt": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "lastUpdate": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "tasksCompleted": $COMPLETED,
  "tasksFailed": 0,
  "tasksRemaining": $PENDING,
  "tasksSkipped": 0
}
EOF
```

### Phase/Step Values

| Phase | Steps | Description |
|-------|-------|-------------|
| INIT | - | Starting up, finding tasks |
| PLAN | planning | Creating mini-plan for task |
| BUILD | implementing, simplifying | Executing task + code-simplifier |
| REVIEW | validating | Running tests, lint, typecheck |
| FIX | fixing | Addressing validation issues |
| SHIP | committing | Creating git commit |
| COMPLETE | - | Queue empty |

Update progress.json after each phase/step transition.

### Step 1: Initialize

```bash
# Get session ID (first 8 chars of transcript UUID or generate)
SESSION_ID=$(echo $RANDOM | md5sum | head -c 8)

# Ensure files exist
mkdir -p .deep
touch .deep/claims.json
[ -f .deep/claims.json ] || echo '{}' > .deep/claims.json
```

### Step 2: Find Next Unclaimed Task

Read `.deep/tasks.md` and `.deep/claims.json`.

Parse tasks: Look for `## [ ] task-XXX:` headers.

For each task:
1. Check if claimed in claims.json
2. If claimed, check if expired (>30 min old)
3. If unclaimed or expired, this is our target

Priority order:
1. High priority unclaimed tasks first
2. Medium priority unclaimed tasks
3. Low priority unclaimed tasks

### Step 3: Claim Task

Atomic claim process:

```bash
# Read current claims
CLAIMS=$(cat .deep/claims.json)

# Add our claim (using session timestamp)
NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
EXPIRES=$(date -u -d "+30 minutes" +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || \
          date -u -v+30M +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || \
          echo "2026-01-20T23:59:59Z")
```

Update claims.json:
```json
{
  "task-XXX": {
    "claimedBy": "{session8}",
    "claimedAt": "{NOW}",
    "expiresAt": "{EXPIRES}"
  }
}
```

### Step 4: Execute Task (Full Ralph Loop)

For the claimed task, run the complete PLAN -> BUILD -> REVIEW -> FIX -> SHIP loop:

1. **Extract task details** from tasks.md
   - Title
   - Description
   - Acceptance criteria (checkboxes)

2. **Initialize session state**
   ```bash
   mkdir -p .deep/{session8}
   ```

   Write `.deep/{session8}/state.json`:
   ```json
   {
     "sessionId": "{session8}",
     "taskId": "task-XXX",
     "phase": "PLAN",
     "iteration": 0,
     "maxIterations": 3,
     "startedAt": "{timestamp}"
   }
   ```

#### 4a. PLAN Phase

Create mini-plan for this specific task:

```bash
# Update progress
cat > .deep/progress.json << EOF
{
  "currentTask": "task-XXX",
  "session": "{session8}",
  "phase": "PLAN",
  "step": "planning",
  ...
}
EOF
```

Write `.deep/{session8}/task-{id}-plan.md`:
```markdown
# Task Plan: {task title}

## Objective
{From task description}

## Files to Modify
- {file1} - {what to change}
- {file2} - {what to change}

## Implementation Steps
1. {Step 1}
2. {Step 2}
3. {Step 3}

## Acceptance Criteria
{Copied from task}

## Risks
- {Potential issue and mitigation}
```

**Transition:** Update state.json `"phase": "BUILD"`

#### 4b. BUILD Phase

```bash
# Update progress
cat > .deep/progress.json << EOF
{
  "currentTask": "task-XXX",
  "phase": "BUILD",
  "step": "implementing",
  ...
}
EOF
```

1. **Implement the task** following the mini-plan
   - Follow acceptance criteria
   - Write tests if applicable

2. **Run code-simplifier** (MANDATORY after implementation)

   ```bash
   # Update step
   # "step": "simplifying"
   ```

   Invoke via Task tool:
   ```
   Task tool with:
     subagent_type: "deep-loop:code-simplifier"
     model: "haiku"
     description: "Simplify: task-{id}"
     prompt: |
       Review code just written for task-{id}.
       Look for unnecessary complexity.
       Apply simplifications.
       DO NOT: Add features, change interfaces, break tests.
       Output: SIMPLIFIED or NO_CHANGES
   ```

**Transition:** Update state.json `"phase": "REVIEW"`

#### 4c. REVIEW Phase

```bash
# Update progress
cat > .deep/progress.json << EOF
{
  "currentTask": "task-XXX",
  "phase": "REVIEW",
  "step": "validating",
  ...
}
EOF
```

Run validation gate:

```bash
# 1. Tests
if [ -f package.json ]; then
  npm test 2>&1 || TEST_FAIL=1
elif [ -f pytest.ini ] || [ -f pyproject.toml ]; then
  pytest 2>&1 || TEST_FAIL=1
fi

# 2. Lint
if [ -f package.json ]; then
  npm run lint 2>&1 || LINT_FAIL=1
fi

# 3. Typecheck
if [ -f tsconfig.json ]; then
  npx tsc --noEmit 2>&1 || TYPE_FAIL=1
fi
```

**If issues found:**
- Write issues to `.deep/{session8}/issues.json`
- Transition to FIX phase

**If clean:**
- Transition to SHIP phase

#### 4d. FIX Phase (if needed)

```bash
# Update progress
cat > .deep/progress.json << EOF
{
  "currentTask": "task-XXX",
  "phase": "FIX",
  "step": "fixing",
  "iteration": {N},
  ...
}
EOF
```

1. Read `.deep/{session8}/issues.json`
2. Address each issue
3. Increment iteration counter
4. **If iteration > maxIterations (3):**
   - Mark task as FAILED
   - Go to Step 5 failure path
5. **Else:**
   - Clear issues.json
   - Return to REVIEW phase

#### 4e. SHIP Phase

```bash
# Update progress
cat > .deep/progress.json << EOF
{
  "currentTask": "task-XXX",
  "phase": "SHIP",
  "step": "committing",
  ...
}
EOF
```

1. **Stage and commit**
   ```bash
   git add -A
   git commit -m "$(cat <<'EOF'
   [deep] implement: {task title}

   - {brief summary of changes}

   Co-Authored-By: Claude <noreply@anthropic.com>
   EOF
   )"
   ```

2. **Verify commit exists**
   ```bash
   git log -1 --oneline | grep -q "\[deep\]" || COMMIT_FAIL=1
   ```

3. **Record completion**
   ```bash
   COMMIT_SHA=$(git rev-parse --short HEAD)
   ```

**If commit successful:**
- Task complete -> proceed to Step 5 success path

**If commit failed:**
- Task failed -> proceed to Step 5 failure path

---

### Phase Transition Summary

```
PLAN -> BUILD -> REVIEW -> SHIP
                 |
              (issues?)
                 | yes
                FIX ------> (iteration > 3?)
                 ^              | yes
                 └------------- FAIL
```

### Progress Display

Output phase transitions for visibility:

```
[PLAN] task-001: Creating implementation plan...
[BUILD] task-001: Implementing changes...
[BUILD] task-001: Running code-simplifier...
[REVIEW] task-001: Running validation gate...
[SHIP] task-001: Committing changes...
✓ task-001 complete (commit: abc1234)
```

### Step 5: Handle Completion

**On Success:**

1. Get commit SHA:
   ```bash
   COMMIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "no-git")
   ```

2. Remove task from tasks.md:
   - Change `## [ ] task-XXX:` to nothing (remove entire block)

3. Append to completed-tasks.md:
   ```markdown
   ## [x] task-XXX: {title}
   **Completed:** {YYYY-MM-DD HH:MM:SS}
   **Session:** {session8}
   **Commit:** {COMMIT_SHA}

   ### Evidence
   - Tests pass: `{test command}`
   - Files changed: `{file list}`

   ---
   ```

4. Remove claim from claims.json

5. Clean up session directory (optional)

**On Failure:**

1. Log error to task in tasks.md:
   ```markdown
   ## [ ] task-XXX: {title}
   **Priority:** {priority}
   **Added:** {date}
   **Attempts:** {N+1}
   **Last Attempt:** {date} by {session8} - FAILED: {reason}
   ```

2. Remove claim from claims.json (release for retry)

3. Increment `Attempts` counter in task

4. Update progress.json: `tasksFailed++`

5. **Skip check:** If Attempts >= 3:
   - Move task to completed-tasks.md with status SKIPPED
   - Update progress.json: `tasksSkipped++`
   - Log: "Task {task-XXX} skipped after 3 failed attempts"

### Step 6: Auto-Loop (MANDATORY)

**When `/deep execute` is invoked, it MUST run until queue is empty.**

After completing/failing a task:

```
while true:
  1. Update progress.json:
     - currentTask: null (between tasks)
     - tasksCompleted++ (if success)
     - tasksRemaining--

  2. Read tasks.md for unclaimed tasks

  3. Filter out tasks with Attempts >= 3

  4. If no eligible tasks remain:
     - Update progress.json: phase = "COMPLETE"
     - Output final summary (see below)
     - Exit with success

  5. Else:
     - Go to Step 2 (find next task)
     - Continue loop
```

**NEVER exit after single task.** The loop runs until:
- Queue empty (all tasks completed or skipped)
- All remaining tasks at max attempts (3)
- User interrupt (Ctrl+C)
- Session timeout (4 hours)
- Catastrophic error (file system, git broken)

### Running Summary

Output every 3 tasks:

```
=== Deep Execute Progress ===
Session: {session8}
Completed: {N} | Failed: {N} | Skipped: {N} | Remaining: {N}
Current: task-XXX - {title}
Runtime: {elapsed}
=============================
```

### Final Summary

When queue empty:

```
=== Deep Execute Complete ===
Session: {session8}
Duration: {elapsed}

Completed: {N}
  - task-001: {title} (commit: abc1234)
  - task-002: {title} (commit: def5678)

Failed: {N}
  - task-003: {title} (reason: tests failed)

Skipped (max attempts): {N}
  - task-004: {title}

Queue Status: EMPTY
=============================
```

## Configuration

| Setting | Value | Description |
|---------|-------|-------------|
| Claim timeout | 30 min | Time before claim expires |
| Max retries | 3 | Attempts per task before skipping |
| Priority order | high->medium->low | Task selection order |

## NOW EXECUTE

When invoked:
1. Initialize and get session ID
2. Read tasks.md and claims.json
3. Find first unclaimed task (priority order)
4. Claim the task (write to claims.json)
5. Execute task with **full Ralph loop**:
   - **PLAN**: Create mini-plan for task
   - **BUILD**: Implement + run code-simplifier
   - **REVIEW**: Run tests, lint, typecheck
   - **FIX**: Address issues (max 3 iterations)
   - **SHIP**: Commit with [deep] tag
6. On success: move to completed-tasks.md with SHA
7. On failure: release claim, increment attempts
8. Loop until queue empty
9. Output summary of completed/failed tasks

**Key difference from before:** Each task goes through PLAN->BUILD->REVIEW->FIX->SHIP phases, not just implement+validate.
