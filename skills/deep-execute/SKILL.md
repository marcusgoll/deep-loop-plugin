---
name: deep-execute
description: Process queued tasks from .deep/tasks.md. Use when user asks to 'execute queue', 'process tasks', 'run queued work'. Supports multi-session claim-based coordination with git conflict handling.
version: 9.1.0
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Task
---

# Deep Execute - Task Queue Processor

Process tasks from `.deep/tasks.md` with claim-based coordination for multi-session execution.

## File Structure

```
.deep/
├── tasks.md              # Active task queue
├── completed-tasks.md    # Done tasks with commit SHA
├── claims.json           # Lock file for multi-session coordination
├── git-conflicts.json    # Tasks blocked by git conflicts (multi-session)
└── progress.json         # Current execution state (recovery)
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

## Multi-Session Git Coordination

When running multiple `/deep execute` sessions in parallel, git conflicts are inevitable if tasks touch overlapping files.

### How It Works

```
Session A: claim task-001 → implement → commit → push ✓
Session B: claim task-003 → implement → commit → push ✗ (rejected)
                                                    ↓
                                              fetch + rebase
                                                    ↓
                                        (conflict?) → git-blocked
                                        (clean?)    → push retry ✓
```

### Conflict Resolution Strategy

| Scenario | Behavior |
|----------|----------|
| **Clean rebase** | Auto-retry push (up to 3 attempts) |
| **File conflict** | Mark `git-blocked`, save to recovery branch, continue next task |
| **Same file, no conflict** | Git auto-merges, push succeeds |

### git-conflicts.json

Tracks tasks blocked by git conflicts for visibility and later resolution:

```json
{
  "task-005": {
    "blockedAt": "2026-01-20T15:30:00Z",
    "session": "abc12345",
    "conflictingFiles": ["src/utils/helpers.ts"],
    "localCommit": "def789",
    "remoteCommit": "123abc",
    "recoveryBranch": "deep-recovery/task-005-abc12345"
  }
}
```

### Recovery Branches

When git-blocked, the work is preserved:

```bash
# List recovery branches
git branch | grep deep-recovery/

# Recover work manually
git checkout deep-recovery/task-005-abc12345
# Resolve conflicts, merge to main
```

### Best Practices for Parallel Sessions

1. **Partition tasks by directory** - Minimize overlap
2. **3-4 sessions max** - Beyond this, git contention increases
3. **Use worktrees** for true isolation (different working directories)
4. **Accept some git-blocks** - They get retried after other sessions complete

### Automatic Retry After Resolution

When a session finds a `git-blocked` task with conflicts now resolved:

```bash
# Check if task can proceed
git fetch origin
if git merge-base --is-ancestor {localCommit} origin/{branch}; then
  # Remote already has our changes (another session merged)
  # Mark task complete
elif git rebase origin/{branch} --onto {localCommit} 2>/dev/null; then
  # Conflicts resolved upstream, can now push
  # Resume task at SHIP phase
fi
```

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
  "tasksGitBlocked": 0,
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

3. **Push with conflict handling** (Multi-Session Support)

   ```bash
   # Update step
   # "step": "pushing"

   PUSH_ATTEMPTS=0
   MAX_PUSH_ATTEMPTS=3
   PUSH_SUCCESS=0

   while [ $PUSH_ATTEMPTS -lt $MAX_PUSH_ATTEMPTS ] && [ $PUSH_SUCCESS -eq 0 ]; do
     PUSH_ATTEMPTS=$((PUSH_ATTEMPTS + 1))

     # Try to push
     if git push origin HEAD 2>&1; then
       PUSH_SUCCESS=1
       echo "[SHIP] Push successful"
     else
       echo "[SHIP] Push rejected (attempt $PUSH_ATTEMPTS/$MAX_PUSH_ATTEMPTS)"

       # Fetch latest from remote
       git fetch origin

       # Get current branch
       BRANCH=$(git rev-parse --abbrev-ref HEAD)

       # Check if we can rebase cleanly
       if git rebase origin/$BRANCH 2>&1; then
         echo "[SHIP] Rebase successful, retrying push..."
         # Loop continues, will retry push
       else
         # Rebase failed - check if it's a conflict
         if git diff --name-only --diff-filter=U | grep -q .; then
           echo "[SHIP] Git conflict detected - cannot auto-resolve"
           git rebase --abort
           GIT_CONFLICT=1
           break
         else
           # Other rebase error
           git rebase --abort 2>/dev/null
           echo "[SHIP] Rebase failed for unknown reason"
         fi
       fi
     fi
   done
   ```

4. **Handle push outcomes**

   | Outcome | Action |
   |---------|--------|
   | Push success | Proceed to completion |
   | Rebase + push success | Proceed to completion |
   | Git conflict | Mark task as `git-blocked`, release claim |
   | Max attempts exceeded | Mark task as `push-failed`, release claim |

   **If GIT_CONFLICT:**
   ```bash
   # Log conflict details
   echo "[SHIP] task-XXX blocked by git conflict with remote"

   # Record in task metadata for visibility
   # Task will be picked up later when conflict is resolved
   # Or another session working on different files can continue
   ```
   - **Do NOT count as task failure attempt** (not the task's fault)
   - Release claim immediately so other sessions can work
   - Task remains in queue with `git-blocked` status
   - Log conflicting files for manual resolution

5. **Record completion**
   ```bash
   COMMIT_SHA=$(git rev-parse --short HEAD)
   ```

**If push successful:**
- Task complete -> proceed to Step 5 success path

**If commit failed:**
- Task failed -> proceed to Step 5 failure path

**If git-blocked:**
- Release claim, do NOT increment attempts
- Add to `.deep/git-conflicts.json` for visibility
- Continue to next task

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
[SHIP] task-001: Pushing to remote...
✓ task-001 complete (commit: abc1234)
```

**Git conflict output:**
```
[SHIP] task-003: Pushing to remote...
[SHIP] task-003: Push rejected, fetching and rebasing...
[SHIP] task-003: Git conflict detected in src/utils/helpers.ts
[SHIP] task-003: Saving to recovery branch deep-recovery/task-003-abc12345
⚠ task-003 git-blocked (conflicts with remote, work preserved)
→ Continuing to next task...
```

### Step 5: Handle Completion

**On Git-Blocked:**

When a task cannot push due to git conflicts with another session's changes:

1. **Record conflict** in `.deep/git-conflicts.json`:
   ```json
   {
     "task-XXX": {
       "blockedAt": "2026-01-20T15:30:00Z",
       "session": "{session8}",
       "conflictingFiles": ["src/api/auth.ts", "src/models/user.ts"],
       "localCommit": "{commit_sha}",
       "remoteCommit": "{remote_sha}",
       "reason": "Conflicting changes in shared files"
     }
   }
   ```

2. **Update task in tasks.md** (add git-blocked marker):
   ```markdown
   ## [ ] task-XXX: {title}
   **Priority:** {priority}
   **Added:** {date}
   **Attempts:** {N}  <!-- NOT incremented for git conflicts -->
   **Status:** git-blocked
   **Blocked Since:** {timestamp}
   **Conflict With:** {conflicting files}
   ```

3. **Release claim** from claims.json (let other sessions work)

4. **Stash local changes** for later recovery:
   ```bash
   # Create a recovery branch with the work
   git checkout -b deep-recovery/task-XXX-{session8}
   git checkout -  # Return to main branch
   git reset --hard origin/{branch}  # Clean state for next task
   ```

5. **Continue to next task** - don't block the queue

**Resolution Options (Manual or Auto):**

| Scenario | Resolution |
|----------|------------|
| Other session finishes first | Re-run task, changes may merge cleanly |
| True conflict | Human resolves, then `/deep execute` picks up task |
| Stale task | `git branch -D deep-recovery/task-XXX-*` after manual resolution |

---

**On Success:**

1. Get commit SHA:
   ```bash
   COMMIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "no-git")
   ```

2. Remove task from tasks.md:
   - Change `## [ ] task-XXX:` to nothing (remove entire block)

3. Remove from git-conflicts.json if present

4. Append to completed-tasks.md:
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
Completed: {N} | Failed: {N} | Git-Blocked: {N} | Remaining: {N}
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

Git-Blocked: {N}
  - task-005: {title} (conflicts: src/utils/helpers.ts)
    Recovery: deep-recovery/task-005-abc12345

Skipped (max attempts): {N}
  - task-004: {title}

Queue Status: EMPTY (except {N} git-blocked)
=============================

To resolve git-blocked tasks:
  git checkout deep-recovery/task-XXX-{session}
  # Resolve conflicts with main
  git checkout main && git merge deep-recovery/task-XXX-{session}
  # Or re-run: /deep execute (may auto-resolve after other sessions finish)
```

## Configuration

| Setting | Value | Description |
|---------|-------|-------------|
| Claim timeout | 30 min | Time before claim expires |
| Max retries | 3 | Attempts per task before skipping |
| Max push attempts | 3 | Rebase+push retries before git-blocked |
| Priority order | high->medium->low | Task selection order |
| Git conflict handling | enabled | Auto-rebase on push rejection |
| Recovery branches | enabled | Preserve git-blocked work |

## NOW EXECUTE

When invoked:
1. Initialize and get session ID
2. Read tasks.md, claims.json, and git-conflicts.json
3. Find first unclaimed task (priority order, skip git-blocked unless resolved)
4. Claim the task (write to claims.json)
5. Execute task with **full Ralph loop**:
   - **PLAN**: Create mini-plan for task
   - **BUILD**: Implement + run code-simplifier
   - **REVIEW**: Run tests, lint, typecheck
   - **FIX**: Address issues (max 3 iterations)
   - **SHIP**: Commit + push with conflict handling
6. Handle outcomes:
   - **Success**: Move to completed-tasks.md with SHA
   - **Task failure**: Release claim, increment attempts
   - **Git-blocked**: Save to recovery branch, release claim, continue (no attempt increment)
7. Loop until queue empty
8. Output summary of completed/failed/git-blocked tasks

**Multi-session safe:** Git conflicts are auto-detected, work is preserved, and other tasks continue processing.

**Key difference from before:** Each task goes through PLAN->BUILD->REVIEW->FIX->SHIP phases with git conflict handling for parallel execution.
