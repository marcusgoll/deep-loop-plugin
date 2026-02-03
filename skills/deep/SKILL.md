---
name: deep
description: Skill from deep-loop plugin
version: 9.0.0
---

# Deep Loop - Deterministic Development Protocol

**Version 8.0.0** | Multi-Agent + External loop + Senior Dev Mode + Task Sync

A self-correcting development loop with senior dev capabilities:

**[CHALLENGE] -> PLAN -> BUILD -> REVIEW -> FIX -> SHIP**

## Startup Banner

When `/deep` starts:

1. **First**, run: `echo $DEEP_LOOP_TASKS_ENABLED` to check Task Sync status
2. **Then** output banner with correct status:

```
╔═══════════════════════════════════════╗
║  DEEP LOOP v8.0.0                     ║
║  Multi-Agent Build: ✓ enabled         ║
║  Senior Dev Mode: ✓ enabled           ║
║  External Loop: ✓ supported           ║
║  Task Sync: ✓ enabled                 ║
╚═══════════════════════════════════════╝
```

Show `✓ enabled` if `DEEP_LOOP_TASKS_ENABLED=true`, else `○ disabled`.

## Key Mechanism

**While-true loop until `<promise>DEEP_COMPLETE</promise>`**

Each iteration:
1. Hook feeds phase prompt (fresh context)
2. You read state from files
3. Execute phase work
4. Output phase completion promise
5. Hook detects promise, allows phase transition
6. Repeat until DEEP_COMPLETE

**State lives in files, not context.** Each iteration reads fresh state.

---

## Philosophy

> **This codebase will outlive you.**

Every shortcut becomes someone else's burden. Every hack compounds into technical debt that slows the whole team down.

You are not just writing code. You are shaping the future of this project.

- The patterns you establish will be copied
- The corners you cut will be cut again
- Fight entropy
- Leave the codebase better than you found it

---

## When to Ask User (Rare)

**Default: Proceed autonomously.** User invoked /deep = implicit trust.

Score each assumption 1-3:
- **3 (Technical):** Proceed autonomously (stack, patterns, performance tradeoffs)
- **2 (Minor ambiguity):** Interpret generously, proceed
- **1 (Business logic unclear):** MUST ask

**Only surface score=1 to user. Max 2 questions/task.**

### Always Autonomous
- Tech stack choices (analyze codebase, decide)
- Code patterns (follow existing conventions)
- Minor scope clarifications (interpret generously)
- Performance tradeoffs <10% (engineering judgment)
- Test strategy (TDD mandatory per protocol)

### Ask Only When
- Ambiguous business logic (e.g., "edit posts" = edit others' posts?)
- Destructive ops (delete prod data, breaking API changes requiring user awareness)
- Budget blowout (task estimated 3x longer than triaged, user should know)

**Example:**

✅ "Add caching" → Autonomously choose Redis (matches existing infra)
❌ "Delete inactive users" → Ask: "Delete = soft delete or hard delete? Threshold = 90 days?"

See `.claude/rules/hedging.md` for prescriptive tone guidance.

---

## Task Sync Layer (Optional)

**Feature flag:** `DEEP_LOOP_TASKS_ENABLED=true` (default: false)

When enabled, Claude Code Task Management tools sync with file state for:
- **Crash recovery:** Tasks persist across context clears
- **Visibility:** `TaskList` shows progress without reading files
- **Ralph mode:** Multiple sessions claim tasks via metadata

### Architecture

```
Files (.deep-{session}/)     ← SOURCE OF TRUTH
       ↕ sync at phase boundaries
Task Management Layer        ← Recovery + Visibility
```

**Files win conflicts.** Task layer is optional enhancement.

### Metadata Schema

**Parent task:**
```json
{ "type": "deep-loop", "sessionId": "8405b17e", "mode": "sequential", "complexity": "STANDARD", "phase": "BUILD" }
```

**Atomic subtask:**
```json
{ "type": "deep-loop-atomic", "parentTaskId": "1", "sessionId": "8405b17e", "atomicIndex": 0, "commitSHA": null }
```

---

## Multi-Agent Build Architecture

**NEW in v8.0.0:** BUILD phase uses Task agents for fresh context per atomic task.

### Architecture

```
┌─────────────────────────────────────────────────┐
│  ORCHESTRATOR (main Claude session)             │
│  - Manages state.json                           │
│  - Analyzes task dependencies                   │
│  - Spawns task agents (parallel if independent) │
│  - Handles retries with error context           │
│  - Outputs BUILD_COMPLETE when all done         │
└─────────────────────────────────────────────────┘
         │ spawn (up to 3 parallel)    ▲ promise
         ▼                             │
┌─────────────────────────────────────────────────┐
│  TASK AGENT (fresh context per task)            │
│  - Receives: task, criteria, relevant files     │
│  - Executes TDD: RED → GREEN → REFACTOR         │
│  - Commits atomically                           │
│  - Returns: TASK_COMPLETE or TASK_BLOCKED       │
└─────────────────────────────────────────────────┘
```

### Benefits

| Aspect | Single Session | Multi-Agent |
|--------|----------------|-------------|
| Context | Accumulates, degrades | Fresh per task |
| Parallelism | None | Up to 3 concurrent |
| Failure isolation | Whole loop affected | Per-task isolation |
| Retry quality | Same polluted context | New agent + error context |

### Configuration (state.json)

```json
{
  "buildMode": "multi-agent",
  "maxParallel": 3,
  "retryStrategy": "new-agent-with-context"
}
```

Set `"buildMode": "single"` to use legacy single-session BUILD.

---

## Atlas MCP Integration (Optional)

If Atlas MCP is configured, use it during deep loop:

### PLAN Phase
```
atlas_pack(task: "{task_description}", budget: 50)
```
Gather relevant context before planning. Output goes to `pack.json`.

### BUILD Phase (Before Creating New Code)
```
atlas_find_duplicates(intent: "{what_you_want_to_create}")
```
Check for existing utilities/helpers before writing new ones.

### REVIEW Phase
```
atlas check
```
Verify no API drift. If fails, fix before proceeding.

**Note:** Atlas tools are optional. Deep loop works without them.

---

## Phase Completion Promises

| Phase | Completion Promise | Triggers |
|-------|-------------------|----------|
| RLM_EXPLORE | `<promise>RLM_COMPLETE</promise>` | Exploration report written |
| PLAN | `<promise>PLAN_COMPLETE</promise>` | Plan written to plan.md |
| BUILD | `<promise>BUILD_COMPLETE</promise>` | Implementation done, code-simplifier run |
| REVIEW | `<promise>REVIEW_COMPLETE</promise>` | All validation passes |
| FIX | `<promise>FIX_COMPLETE</promise>` | Issues resolved |
| SHIP | `<promise>SHIP_COMPLETE</promise>` | PR merged or committed |
| **Final** | `<promise>DEEP_COMPLETE</promise>` | All criteria met |

**CRITICAL:** Only output a promise when that phase is TRULY complete. The loop trusts your promises.

---

## Quick Start

1. **Triage** task complexity (QUICK/STANDARD/DEEP)
2. **Initialize** `.deep-{session8}/` state directory
3. **Execute** loop phases in order
4. **Output promises** as each phase completes
5. **Ship** when all gates pass

---

## Step 1: Triage

### Complexity Level

| Level | Signals | Iterations |
|-------|---------|------------|
| **QUICK** | Single file, obvious fix, <30 lines | 3 |
| **STANDARD** | 2-5 files, some design decisions | 10 |
| **DEEP** | 6+ files, architectural, high-stakes | 20 |

### Loop Mode Selection

**Default: Internal loop** (interactive, user watching).

| Mode | When to Use | Mechanism |
|------|-------------|-----------|
| **Internal** | Default for all tasks, interactive | Stop hook blocks, feeds prompts |
| **External** | Long-running, autonomous, overnight | Bash script orchestrates Claude calls |

**Use Internal Loop (Default):**
- User is present and watching
- Interactive development session
- Any complexity level

**Use External Loop When (ANY):**
- User says "overnight", "background", "daemon", "external"
- Ralph mode selected
- User explicitly requests autonomous execution

**Output in Triage:**
```markdown
## Triage Results

**Complexity:** STANDARD
**Tasks:** 5
**Files affected:** ~8
**Loop mode:** INTERNAL (default)

Reason: Interactive session with user present.
```

**Task Sync (if DEEP_LOOP_TASKS_ENABLED=true):**
```
TaskCreate({
  subject: "[DEEP] {brief_task_summary}",
  description: "{user_requirement}",
  activeForm: "Triaging {task}",
  metadata: { type: "deep-loop", sessionId: "{session8}", mode: "{internal|external}", complexity: "{QUICK|STANDARD|DEEP}" }
})
```
Save returned task ID to `state.json` as `parentTaskId`.

---

## Step 2: Initialize State

**Use session-specific directory naming.**

Extract first 8 characters of session ID from transcript path and create:

```
.deep-{session8}/
├── state.json    # Loop state (active, phase, iteration)
├── task.md       # Original task (immutable)
├── plan.md       # Implementation plan
├── issues.json   # Current issues (if any)
└── test-results.json  # Latest validation
```

**CRITICAL: Set mode IMMEDIATELY during TRIAGE, not after PLAN.**

**state.json format (set during TRIAGE):**
```json
{
  "active": true,
  "sessionId": "8405b17e",
  "mode": "internal",
  "buildMode": "multi-agent",
  "maxParallel": 3,
  "phase": "PLAN",
  "iteration": 0,
  "maxIterations": 10,
  "startedAt": "2025-01-20T10:00:00Z",
  "task": "Brief task description",
  "parentTaskId": null,
  "atomicTaskIds": []
}
```

**mode options:**
- `"internal"` (default): Interactive, stop hook controls iteration
- `"external"`: Autonomous, bash script orchestrates Claude calls

**buildMode options:**
- `"multi-agent"` (default): Orchestrator spawns Task agents per atomic task
- `"single"`: Legacy single-session BUILD phase

`parentTaskId` and `atomicTaskIds` populated when Task Sync enabled.

---

## Step 3: Execute Phases

### PHASE: PLAN

**Two-step planning: Assumptions first, then detailed plan.**

#### Step 0: Gather Context (if Atlas available)
```
atlas_pack(task: "{task_description}", budget: 50)
```
Read `pack.json` for relevant files/symbols before planning.

#### Step 1: Locked Assumptions (Auto-Approved)

Output assumptions as locked declarations, proceed immediately:

```markdown
## Locked Assumptions (Auto-Approved)

**Task:** [What you're building - specific, not vague]
**Stack:** [Technology] BECAUSE [reason - codebase patterns, requirements, etc.]
**Files:** [List of files to modify]
**Scope IN:** [Included features/behavior]
**Scope OUT:** [Explicitly excluded - prevents scope creep]
**Key Bets:** [Critical decisions] - no alternatives considered

These are LOCKED. Proceeding to detailed plan immediately.
```

**Rationale:** User invoked /deep = implicit trust. Faster time-to-first-commit, less decision fatigue. See `.claude/rules/hedging.md` for prescriptive tone guidance.

#### Step 1.5: Root Cause Analysis (Mandatory Gate)

Before detailed planning, force re-evaluation with existing context:

**Question:** Are we solving the ROOT PROBLEM or treating a SYMPTOM?

```markdown
## Root Cause Analysis

**Surface request:** [Stated task from user]
**Underlying need:** [Inferred root problem]
**Architectural issue:** [Is there deeper design flaw? YES/NO + explanation]

**Classification:**
- [ ] SYMPTOM: Treating immediate pain point (root out of scope)
- [ ] ROOT: Addressing underlying design/architecture issue (preferred)

**If SYMPTOM chosen:**
Root problem documented in decisions.md under "Known Technical Debt"
Continuing with symptom fix (root logged for future)

**If ROOT chosen:**
Expanded scope to address root cause
Decision locked to prevent symptom-only implementation
```

See `.claude/rules/root-cause.md` for classification guidance.

**This gate ensures durable solutions, not fragile patches.**

#### Step 2: Detailed Plan

Create `.deep-{session8}/plan.md`:
- Problem statement
- Testable acceptance criteria
- Atomic task breakdown (see atomicity rules below)
- Risk assessment

**Task Atomicity Rules (MANDATORY):**

Each atomic task MUST:
- Touch ≤3 files (if >3, split further)
- Complete in ≤20 minutes
- Have 1-3 acceptance criteria (specific, testable)
- Produce ≤1 primary commit (RED+GREEN+REFACTOR = 1 logical change)

**Examples:**

❌ BAD: "Implement user authentication" (too coarse, 10+ files, 2+ hours)

✅ GOOD:
- "Add User model with email/password" (15 min, 2 files)
- "Implement JWT signing endpoint" (20 min, 1 file)
- "Add auth middleware" (10 min, 1 file)

**Anti-pattern:** Tasks that span multiple subsystems or require hours of work.

Also create `.deep-{session8}/decisions.md`:
```markdown
## Locked Decisions
| Decision | Choice | Rationale |
|----------|--------|-----------|
| ... | ... | ... |
```

**Task Sync (if DEEP_LOOP_TASKS_ENABLED=true):**

After plan approval, create atomic subtasks:
```
For each atomic task in plan.md:
  taskId = TaskCreate({
    subject: "task-{index}: {task_title}",
    description: "{acceptance_criteria}",
    activeForm: "Building {task_title}",
    metadata: { type: "deep-loop-atomic", parentTaskId: "{parentTaskId}", sessionId: "{session8}", atomicIndex: {index} }
  })
  Append taskId to state.json atomicTaskIds[]

If sequential mode (not Ralph):
  TaskUpdate(taskId, { addBlockedBy: [prevTaskId] })
```

**Transition (Internal Mode):** Update state.json `"phase": "BUILD"`
**Output:** `<promise>PLAN_COMPLETE</promise>`

**Transition (External Mode):** Generate loop.sh and hand off to user.

---

### External Mode Handoff

When `mode: "external"` in state.json, after PLAN phase:

1. **Update state for external execution:**
   ```json
   {
     "active": true,
     "mode": "external",
     "phase": "BUILD",
     "assumptions_approved": true,
     "loopScript": ".deep-{session8}/loop.sh"
   }
   ```

2. **Generate `.deep-{session8}/loop.sh`** via generate-loop-script.js:
   ```bash
   node "{plugins}/deep-loop/src/generate-loop-script.js" "{session8}" "{task}" {maxIterations}
   ```

3. **Auto-launch loop in background:**
   ```bash
   # Use Bash tool with run_in_background: true
   bash .deep-{session8}/loop.sh
   ```

   Record the Task ID returned by the background Bash call.

4. **Output status to user:**
   ```
   External loop launched in background.

   Session: {session8}
   Task ID: {task_id}
   Log: .deep-{session8}/loop.log

   Monitor: tail -f .deep-{session8}/loop.log
   Cancel: touch .deep-{session8}/FORCE_EXIT

   Loop running autonomously. You can continue other work.
   ```

5. **Stay available** - Don't exit. User may have follow-up questions or want to monitor.

**External Mode: Fully Autonomous Execution**

When `mode="external"`, the loop operates with zero mid-stream user interaction:

**Auto-approved:**
- PLAN assumptions (logged, not prompted)
- Decision drift (auto-resolved via decision-checker, logged)
- Task failures (auto-retry 3x → escalate to log, not user)

**User reviews `.deep-{session8}/loop.log` AFTER completion.**

**Zero interruptions** - defeats "overnight mode" if user must approve mid-stream.

**Max autonomous time:** ≤8 hours
- If not DEEP_COMPLETE after 8h → pause, log, notify user

**Guardrails:**
- Commit frequency monitoring (no commits >45 min → stuck, escalate)
- Test passage trends (declining → bad direction, escalate)
- Drift classifier (safe auto-accept, dangerous auto-revert)

---

### PHASE: BUILD (Multi-Agent TDD)

**Test-Driven Development is MANDATORY.**
**Multi-Agent mode spawns fresh Task agents per atomic task.**

#### Build Mode Selection

Check `state.json.buildMode`:
- `"multi-agent"` (default): Orchestrator spawns Task agents
- `"single"`: Legacy single-session BUILD

**Task Sync (if DEEP_LOOP_TASKS_ENABLED=true):**
```
TaskUpdate(parentTaskId, { status: "in_progress", metadata: { phase: "BUILD" } })
```

---

#### Multi-Agent BUILD (Default)

**You are the ORCHESTRATOR.** Your job:
1. Parse atomic tasks from plan.md
2. Analyze dependencies between tasks
3. Spawn Task agents (parallel if independent)
4. Handle results and retries
5. Output BUILD_COMPLETE when all tasks done

##### Step 1: Parse Tasks and Dependencies

Read plan.md and identify:
- Atomic tasks with acceptance criteria
- Dependencies (task B needs task A's output)
- Independent tasks (can run in parallel)

Write to `.deep-{session8}/tasks-status.json`:
```json
{
  "tasks": [
    { "id": 0, "title": "...", "status": "pending", "dependsOn": [], "attempts": 0 },
    { "id": 1, "title": "...", "status": "pending", "dependsOn": [0], "attempts": 0 },
    { "id": 2, "title": "...", "status": "pending", "dependsOn": [], "attempts": 0 }
  ]
}
```

##### Step 2: Orchestrator Algorithm (Deterministic)

**No "what should I do?" moments. Algorithm decides.**

**1. Select next batch:**
```javascript
// Filter ready tasks (pending + dependencies complete)
readyTasks = tasks.filter(t => t.status === 'pending' && allDepsComplete(t))

// Take first N (up to maxParallel), no prioritization debate
batch = readyTasks.slice(0, maxParallel)  // maxParallel = 3
```

**2. Spawn agents (parallel, no waiting):**
```javascript
for task in batch:
  Task({
    subagent_type: "general-purpose",
    description: `Build: ${task.title}`,
    prompt: buildTaskAgentPrompt(task),
    run_in_background: false  // Wait for completion to handle results
  }) &  // Parallel spawn
```

**3. Handle failures (prescriptive retry):**
```javascript
if attempts < 2:
  // Retry same prompt (transient error)
  task.status = "pending"
  task.attempts += 1
else if attempts < 3:
  // New agent + error context (learn from failure)
  Task({ prompt: `Previous error: ${lastError}\n\nTry different approach.\n\n${originalPrompt}` })
  task.attempts += 1
else:
  // Log escalation, continue other tasks (don't block)
  task.status = "escalated"
  log(`Task ${task.id} blocked after 3 attempts: ${lastError}`)
  // DO NOT prompt user - continue with remaining tasks
```

**No manual orchestration. Deterministic scheduling.**

**Task agent prompt template:**
```markdown
# Task Agent - Atomic Task Executor

## Your Task
**Title:** {task.title}
**Acceptance Criteria:**
{task.criteria}

## Relevant Context
{atlas_pack output OR explicit file list}

## Locked Decisions (DO NOT DEVIATE)
{contents of decisions.md}

## Instructions
1. RED: Write failing test, commit
2. GREEN: Implement to pass, commit
3. REFACTOR: Clean up (optional), commit
4. Validate: test, lint, types

## Output
- Success: <promise>TASK_COMPLETE</promise>
- Blocked: <promise>TASK_BLOCKED:reason</promise>
```

##### Step 3: Handle Results

**On TASK_COMPLETE:**
```json
Update tasks-status.json: task.status = "complete"
Update tasks-status.json: task.commitSHA = git rev-parse HEAD
```

**On TASK_BLOCKED:**
```json
task.attempts += 1
task.lastError = "blocked reason"

if task.attempts < 2:
  // Retry same task
  task.status = "pending"
else:
  // Spawn NEW agent with error context (learning from failure)
  Task({
    prompt: `
      ## Retry with Error Context

      Previous attempts failed with:
      ${task.lastError}

      [previous agent learnings if any]

      Try a different approach. ${originalPrompt}
    `
  })

if task.attempts >= 3:
  task.status = "escalated"
  // Ask user for help
  AskUserQuestion({ question: "Task blocked after 3 attempts: {reason}. How to proceed?" })
```

##### Step 4: Continue Until All Complete

Loop:
1. Check tasks-status.json for pending tasks with met dependencies
2. Spawn batch of up to 3 independent task agents
3. Process results
4. Repeat until all tasks complete or escalated

##### Step 5: Post-Build

After all tasks complete, invoke code-simplifier:
```
Task({
  subagent_type: "general-purpose",
  description: "Simplify: post-build cleanup",
  prompt: "Review recently changed code. Remove unnecessary complexity."
})
```

---

#### Legacy Single-Session BUILD (buildMode: "single")

For each task from plan.md:

**Before creating new utilities/helpers (if Atlas available):**
```
atlas_find_duplicates(intent: "{what_you_want_to_create}")
```

**For frontend/UI tasks:** Invoke `frontend-design` skill.

1. **RED** - Write failing test first
   - Commit: `[deep] test: add failing test for <feature>`

2. **GREEN** - Write minimal code to pass
   - Commit: `[deep] implement: <feature>`

3. **REFACTOR** - Clean up (optional)
   - Commit: `[deep] refactor: <what>`

4. **Validate** - Run full suite (test, lint, types)
5. **Log failures** to issues.json

---

#### Completion Requirements (Both Modes)

**CRITICAL: NO PARTIAL COMPLETION ALLOWED**

Before BUILD_COMPLETE:
- [ ] ALL atomic tasks complete (not some, ALL)
- [ ] All tests pass
- [ ] No TODOs, FIXMEs, or placeholder code
- [ ] code-simplifier has run

**Transition:** Update state.json `"phase": "REVIEW"`
**Output:** `<promise>BUILD_COMPLETE</promise>`

---

### PHASE: REVIEW

**Binary Completion Gate (Zero Exceptions)**

ALL checks MUST pass with 0 failures:

1. **Tests:** 100% pass (no "flaky test" excuses)
2. **Lint:** 0 warnings (fix or disable rule explicitly, no //ignore)
3. **Types:** 0 errors (any `any` = instant fail)
4. **Build:** Success (no "works on my machine")
5. **Atlas check:** (if available) No API drift

**No "mostly working" states. Binary: PASS→SHIP or FAIL→FIX.**

Run validation:
```bash
npm test && npm run typecheck && npm run lint && npm run build && atlas check
```

Record in `.deep-{session8}/test-results.json`:
```json
{
  "allPassed": true,
  "results": {
    "tests": { "ran": true, "passed": true, "failures": 0 },
    "types": { "ran": true, "passed": true, "errors": 0 },
    "lint": { "ran": true, "passed": true, "warnings": 0 },
    "build": { "ran": true, "passed": true }
  }
}
```

**If ALL pass (100%):** Update state.json `"phase": "SHIP"`
**If ANY fail (even 1):** Update state.json `"phase": "FIX"`, add to issues.json (automatic, no discussion)
**Output:** `<promise>REVIEW_COMPLETE</promise>`

**Pre-SHIP Root Cause Validation:**

Before proceeding to SHIP, validate:

```markdown
## Pre-Ship Root Cause Check

**Did we solve root problem or just treat symptoms?**

Review completed work:
- Changes made: [List]
- Problem addressed: [Surface vs root]
- Technical debt introduced: [Any shortcuts?]
- Follow-up needed: [Root issues deferred?]

**Pass criteria:**
- SYMPTOM fixed: Root documented in decisions.md as known debt ✓
- ROOT fixed: No shortcuts, design is sound ✓

**Fail criteria:**
- Symptom fixed but root NOT documented → Revisit FIX
- Hack/workaround without justification → Refactor or document

Only SHIP when confident solution is durable, not fragile.
```

See `.claude/rules/root-cause.md` for classification.

---

### PHASE: FIX

**Failure Root Cause Check (Mandatory)**

When test fails or bug found, STOP and ask:

**Is this test failure a symptom of a deeper issue?**

Check for:
- Race condition masking timing issue
- Flaky test revealing state leakage
- Edge case exposing design flaw
- Error message hiding real problem

**Decision:**
- **SYMPTOM:** Note in test comment, fix locally
- **ROOT:** Expand FIX scope to address underlying issue

**Examples:**

❌ "Test fails randomly" → Add retry logic (SYMPTOM)
✅ "Test fails randomly" → Fix shared state pollution (ROOT)

❌ "API timeout" → Add retry (SYMPTOM)
✅ "API timeout" → Fix N+1 query causing timeouts (ROOT)

See `.claude/rules/root-cause.md` for classification.

**Don't patch over problems - solve them.**

---

Address `.deep-{session8}/issues.json`:
1. **Run root cause check** for each failure
2. Fix each issue (root or symptom, documented)
3. Commit atomically
4. Run validation

**When all fixed:** Clear issues.json, update state.json `"phase": "REVIEW"`
**Output:** `<promise>FIX_COMPLETE</promise>`

---

### PHASE: SHIP

**1. Invoke verify-app subagent:**
```
subagent_type: "general-purpose"
description: "Verify: E2E testing"
prompt: |
  Detect app type (web, API, CLI, library).
  Run appropriate verification.
  Output: VERIFIED or issues list.
```

**2. Git finalization (if in repo):**
```bash
git push -u origin HEAD
gh pr create --base main --fill
gh pr merge --auto --squash
```

**Completion Checklist:**
- [ ] All acceptance criteria met
- [ ] All tests pass
- [ ] verify-app passes
- [ ] PR created and merged (or committed to main)

**When ALL complete:**
- Update state.json: `"phase": "COMPLETE", "complete": true`

**Task Sync (if DEEP_LOOP_TASKS_ENABLED=true):**
```
finalCommitSHA = git rev-parse HEAD
TaskUpdate(parentTaskId, {
  status: "completed",
  metadata: { phase: "COMPLETE", commitSHA: "{finalCommitSHA}", completedAt: "{timestamp}" }
})
```

- **Output:** `<promise>DEEP_COMPLETE</promise>`

---

### PHASE: LESSONS_LEARNED (Post-Completion Self-Review)

**Before exiting /deep loop, reflect on what went wrong and create prevention rules.**

Every correction should add a rule so it never happens again. This is continuous improvement.

**Reflection Prompts:**

1. **Wrong assumptions:** What did I assume incorrectly? When discovered? How to catch earlier?
2. **Unescalated confusion:** What ambiguity did I guess on instead of escalating?
3. **Overcomplication:** What code is more complex than needed? Why?
4. **Scope creep:** What out-of-scope changes did I make? Why?
5. **Missed root cause:** Did I solve symptom instead of root? What's the underlying issue?

**Output to `.deep-{session8}/lessons-learned.md`:**

```markdown
# Lessons Learned - {timestamp}

## Issue 1: [Title]
**What happened:** [Description of mistake/issue]
**Caught:** [Which phase/when discovered]
**Prevention:** [Rule to prevent recurrence]

## Issue 2: [Title]
**What happened:** [Description]
**Caught:** [When]
**Prevention:** [Rule]
```

**Examples:**

```markdown
## Issue 1: Assumed JWT in headers, actually in cookies
**What happened:** Implemented JWT extraction from Authorization header, failed in tests
**Caught:** BUILD phase test failures
**Prevention:** In PLAN phase, grep for existing auth patterns before assuming: `grep -r "jwt\|token" middleware/`

## Issue 2: Created abstraction class for 2 use cases
**What happened:** Built ConfigManager class, only used in 2 places
**Caught:** Self-review flagged premature abstraction
**Prevention:** Task-agent blocks abstractions with <3 uses (add to simplicity.md)

## Issue 3: Added cache, didn't fix N+1 query (symptom fix)
**What happened:** Slow API → added Redis cache, performance still degraded after cache expired
**Caught:** Performance monitoring showed spikes at cache TTL
**Prevention:** FIX phase checks query patterns before adding cache (root vs symptom)
```

**User Promotion Workflow:**

After /deep completes, user reviews `.deep-{session8}/lessons-learned.md`.

For valuable rules, promote to plugin files:
```bash
# Add to task-agent.md
echo "Check existing auth patterns before assuming: grep -r 'auth' ." >> agents/task-agent.md

# Or update rules files
echo "Abstractions require 3+ uses (not 2)" >> .claude/rules/simplicity.md
```

**Metrics to Track:**
- Lessons per session (track over time)
- Rule promotion rate (how many become permanent)
- Repeat mistakes (same lesson twice = enforcement failure)

This builds institutional knowledge - don't repeat mistakes.

---

## Context Management

**Each iteration starts fresh.** Hook feeds:
1. Phase prompt with instructions
2. File paths to read state from

**You** read state from files:
- `task.md` - What to build
- `plan.md` - How to build it
- `state.json` - Current phase/iteration
- `issues.json` - What's broken

**No conversation history accumulation.** This enables 8+ hour loops without context rot.

---

## Git Operations

### After Each Task (BUILD/FIX)

```bash
git add -A
git commit -m "[deep] <phase>: <description>"
```

### PR Creation (SHIP)

```bash
gh pr create --base main --title "[deep] <task>" --fill
gh pr merge --auto --squash
```

---

## Subagent Summary

| Context | Subagent | Required |
|---------|----------|----------|
| BUILD (multi-agent) | task-agent | Per atomic task |
| BUILD -> REVIEW | code-simplifier | YES |
| REVIEW -> SHIP | verify-app | YES |

**Invoke via Task tool:**
```javascript
Task({
  subagent_type: "general-purpose",
  description: "Build: {task_title}",
  prompt: "..." // See task-agent.md template
})
```

---

## Loop Control

| Action | Method |
|--------|--------|
| Check status | `cat .deep-{session8}/state.json` |
| Cancel | `/cancel-deep` or `touch .deep-{session8}/FORCE_EXIT` |
| Force complete | Set `"complete": true` in state.json |

---

## Safety Features

1. **Max iterations** - Hard limit (3/10/20 by complexity)
2. **Staleness** - Auto-exits after 8 hours inactive
3. **Force exit** - `touch .deep-{session8}/FORCE_EXIT`

---

## NOW EXECUTE

1. **Triage** the task
2. **Initialize** `.deep-{session8}/` with `"active": true`
3. **Run** phases in order
4. **Output promises** as phases complete
5. **Ship** when `<promise>DEEP_COMPLETE</promise>`
