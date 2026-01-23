# Deep Loop - Deterministic Development Protocol

**Version 7.1.0** | External loop + Senior Dev Mode

A self-correcting development loop with senior dev capabilities:

**[CHALLENGE] -> PLAN -> BUILD -> REVIEW -> FIX -> SHIP**

## Startup Banner

When `/deep` starts, output:
```
╔═══════════════════════════════════════╗
║  DEEP LOOP v7.1.0                     ║
║  Senior Dev Mode: ✓ enabled           ║
║  External Loop: ✓ supported           ║
╚═══════════════════════════════════════╝
```

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

**Default: External loop** for STANDARD/DEEP tasks.

| Mode | When to Use | Mechanism |
|------|-------------|-----------|
| **Internal** | QUICK tasks, interactive, user watching | Stop hook blocks, feeds prompts |
| **External** | STANDARD/DEEP, long-running, autonomous | Bash script orchestrates Claude calls |

**Use External Loop When (ANY):**
- Complexity = STANDARD or DEEP
- Task count ≥ 3
- Estimated changes > 5 files
- Ralph mode selected
- User says "overnight", "background", "daemon", "external"

**Use Internal Loop When (ALL):**
- Complexity = QUICK
- Single task
- User is actively monitoring
- User says "interactive", "watch", "internal"

**Output in Triage:**
```markdown
## Triage Results

**Complexity:** STANDARD
**Tasks:** 5
**Files affected:** ~8
**Loop mode:** EXTERNAL (recommended)

Reason: Multi-file feature with 5 tasks benefits from fresh context per iteration.
```

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
  "mode": "external",
  "phase": "PLAN",
  "iteration": 0,
  "maxIterations": 10,
  "startedAt": "2025-01-20T10:00:00Z",
  "task": "Brief task description"
}
```

The `mode` field MUST be set during TRIAGE based on complexity:
- QUICK → `"mode": "internal"`
- STANDARD/DEEP → `"mode": "external"`

This ensures the stop hook doesn't block during PLAN phase for external tasks.

---

## Step 3: Execute Phases

### PHASE: PLAN

**Two-step planning: Assumptions first, then detailed plan.**

#### Step 1: Assumptions Preview

Before detailed planning, output your assumptions to the user:

```markdown
## Planning Assumptions

**Task Understanding:**
- [What I think you're asking for]

**Technical Approach:**
- [Technology/pattern I plan to use]
- [Files I expect to modify]

**Scope Boundaries:**
- [What I WILL do]
- [What I WON'T do (out of scope)]

**Key Decisions:**
- [Decision 1]: [My planned choice]
- [Decision 2]: [My planned choice]
```

**Wait for user approval** via AskUserQuestion before proceeding.

#### Step 2: Detailed Plan

After user approves, create `.deep-{session8}/plan.md`:
- Problem statement
- Testable acceptance criteria
- Atomic task breakdown
- Risk assessment

Also create `.deep-{session8}/decisions.md`:
```markdown
## Locked Decisions
| Decision | Choice | Rationale |
|----------|--------|-----------|
| ... | ... | ... |
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

2. **Generate `.deep-{session8}/loop.sh`** (see generate-loop-script.js)

3. **Output handoff instructions:**
   ```
   External loop mode selected. Plan created and approved.

   To start the autonomous loop:
     cd {cwd}
     bash .deep-{session8}/loop.sh

   For Telegram notifications, ensure these are set:
     export TELEGRAM_BOT_TOKEN="your-bot-token"
     export TELEGRAM_CHAT_ID="your-chat-id"

   Monitor progress:
     tail -f .deep-{session8}/loop.log

   Cancel:
     touch .deep-{session8}/FORCE_EXIT

   The loop will run until complete or max iterations reached.
   ```

4. **Exit current session** - The bash script takes over orchestration.

**Note:** In external mode, assumptions are auto-approved during BUILD. The plan was already approved interactively.

---

### PHASE: BUILD (TDD)

**Test-Driven Development is MANDATORY.**
**NO PARTIAL COMPLETION - Tasks must be 100% done or not done.**

For each task from plan.md:

1. **RED** - Write failing test first
   - Define expected behavior
   - Run test → confirm it fails
   - Commit: `[deep] test: add failing test for <feature>`

2. **GREEN** - Write minimal code to pass
   - Implement just enough to pass the test
   - Run test → confirm it passes
   - Commit: `[deep] implement: <feature>`

3. **REFACTOR** - Clean up (optional)
   - Improve code without changing behavior
   - Tests must still pass
   - Commit: `[deep] refactor: <what>`

4. **Validate** - Run full suite (test, lint, types)
5. **Log failures** to issues.json if any

**CRITICAL: NO PARTIAL COMPLETION ALLOWED**

Before marking ANY task complete, verify:
- [ ] ALL acceptance criteria from plan.md are met (not some, ALL)
- [ ] Tests pass for the ENTIRE feature (not just parts)
- [ ] No TODOs, FIXMEs, or "will implement later" comments
- [ ] No placeholder code or stub implementations
- [ ] Feature works end-to-end (not just individual pieces)

**If task cannot be fully completed:**
1. DO NOT mark as complete
2. DO NOT move to next task
3. Log blocker to issues.json with specific reason
4. Attempt to resolve blocker (max 3 retries)
5. Only after 3 failed attempts: escalate to user

**NEVER output "partially complete" - either DONE or BLOCKED.**

**TDD Checklist per task:**
- [ ] Test written BEFORE implementation
- [ ] Test fails initially (proves it tests something)
- [ ] Implementation makes test pass
- [ ] No untested code paths
- [ ] 100% of acceptance criteria met

**After all tasks:** Invoke code-simplifier subagent via Task tool:
```
subagent_type: "general-purpose"
description: "Simplify: post-build cleanup"
prompt: "Review recently changed code. Remove unnecessary complexity. DO NOT add features or change interfaces."
```

**Transition:** Update state.json `"phase": "REVIEW"`
**Output:** `<promise>BUILD_COMPLETE</promise>`

---

### PHASE: REVIEW

Run comprehensive validation:
1. `npm test` (or equivalent)
2. `npm run typecheck`
3. `npm run lint`
4. `npm run build`

Record in `.deep-{session8}/test-results.json`:
```json
{
  "allPassed": true,
  "results": {
    "tests": { "ran": true, "passed": true },
    "types": { "ran": true, "passed": true },
    "lint": { "ran": true, "passed": true },
    "build": { "ran": true, "passed": true }
  }
}
```

**If ALL pass:** Update state.json `"phase": "SHIP"`
**If ANY fail:** Update state.json `"phase": "FIX"`, add to issues.json
**Output:** `<promise>REVIEW_COMPLETE</promise>`

---

### PHASE: FIX

Address `.deep-{session8}/issues.json`:
1. Fix each issue
2. Commit atomically
3. Run validation

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
- **Output:** `<promise>DEEP_COMPLETE</promise>`

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

| Transition | Subagent | Required |
|------------|----------|----------|
| BUILD -> REVIEW | code-simplifier | YES |
| REVIEW -> SHIP | verify-app | YES |

Invoke via Task tool with `subagent_type: "general-purpose"`.

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
