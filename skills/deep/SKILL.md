---
name: deep
description: Start deterministic development loop (PLAN->BUILD->REVIEW->FIX->SHIP). Use when user asks to 'deep loop', 'implement feature', 'build with TDD', or mentions multi-agent BUILD. Supports external/ralph modes.
version: 11.0.0
argument-hint: [task description] [--no-challenge] [--internal] [--external]
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Task, Skill
---

# Deep Loop v11.0.0

**[CHALLENGE] -> PLAN -> BUILD -> REVIEW -> FIX -> SHIP**

## Startup

1. Run: `echo $DEEP_LOOP_TASKS_ENABLED` to check Task Sync status
2. Output banner:

```
+---------------------------------------+
|  DEEP LOOP v11.0.0                    |
|  Skills Integration: enabled          |
|  Task Sync: {enabled|disabled}        |
+---------------------------------------+
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

---

## Skills Reference

| Phase | Skills | Purpose |
|-------|--------|---------|
| BUILD | `/tdd-workflow` | Test-first development |
| BUILD (frontend) | `/frontend-design`, `/react-best-practices` | UI quality |
| REVIEW | `/code-review`, `/security-audit` | Quality + security gates |
| FIX | `/debug-investigate` | Root cause analysis |
| SHIP | `/pr-craftsman` | Well-structured PR |

Invoke: `Skill({ skill: "code-review" })`

---

## When to Ask User (Rare)

**Default: Proceed autonomously.** User invoked /deep = implicit trust.

Score each assumption 1-3:
- **3 (Technical):** Proceed autonomously
- **2 (Minor ambiguity):** Interpret generously, proceed
- **1 (Business logic unclear):** MUST ask

**Only surface score=1 to user. Max 2 questions/task.**

---

## Phase Completion Promises

| Phase | Promise | Triggers |
|-------|---------|----------|
| CHALLENGE | `<promise>CHALLENGE_COMPLETE</promise>` | User confirmed approach |
| PLAN | `<promise>PLAN_COMPLETE</promise>` | Plan written to plan.md |
| BUILD | `<promise>BUILD_COMPLETE</promise>` | All tasks done, code-simplifier run |
| REVIEW | `<promise>REVIEW_COMPLETE</promise>` | All validation passes |
| FIX | `<promise>FIX_COMPLETE</promise>` | Issues resolved |
| SHIP | `<promise>SHIP_COMPLETE</promise>` | PR merged or committed |
| **Final** | `<promise>DEEP_COMPLETE</promise>` | All criteria met |

**CRITICAL:** Only output a promise when that phase is TRULY complete.

---

## Step 1: Triage

### Complexity

| Level | Signals | Iterations |
|-------|---------|------------|
| **QUICK** | Single file, obvious fix, <30 lines | 3 |
| **STANDARD** | 2-5 files, some design decisions | 10 |
| **DEEP** | 6+ files, architectural, high-stakes | 20 |

### Loop Mode

| Mode | When | Mechanism |
|------|------|-----------|
| **Internal** | QUICK, explicit `--internal` | Stop hook blocks, feeds prompts |
| **External** | STANDARD/DEEP, explicit `--external` | Bash script orchestrates Claude calls |

### --no-challenge Flag

If `--no-challenge` is passed OR the task description is unambiguous single-purpose (e.g., "add health check endpoint"), skip CHALLENGE phase and go directly to PLAN.

**Task Sync (if DEEP_LOOP_TASKS_ENABLED=true):**
```
TaskCreate({
  subject: "[DEEP] {brief_task_summary}",
  description: "{user_requirement}",
  activeForm: "Triaging {task}",
  metadata: { type: "deep-loop", sessionId: "{session8}", mode: "{internal|external}", complexity: "{QUICK|STANDARD|DEEP}" }
})
```

---

## Step 2: Initialize State

Extract first 8 chars of session ID. Create:

```
.deep-{session8}/
├── state.json
├── task.md       # Original task (immutable)
├── plan.md
├── issues.json
└── test-results.json
```

**state.json:**
```json
{
  "active": true,
  "sessionId": "{session8}",
  "mode": "internal",
  "buildMode": "multi-agent",
  "maxParallel": 3,
  "phase": "PLAN",
  "iteration": 0,
  "maxIterations": 10,
  "startedAt": "{ISO timestamp}",
  "task": "Brief task description",
  "parentTaskId": null,
  "atomicTaskIds": []
}
```

---

## Step 3: Execute Phases

The **stop hook** feeds detailed phase-specific prompts each iteration. Below is the phase overview for orientation.

### CHALLENGE (skippable via --no-challenge)
Challenge the request before building. Do we need this? Simpler approach? Get user confirmation.

### PLAN
Follow the planning approach from `/deep-plan` Mode 1 (single task planning).
Create plan.md with: problem statement, testable acceptance criteria, atomic task breakdown, risk assessment.

For PLAN details, the stop hook delivers the full planning prompt.

**External Mode:** After PLAN, generate loop.sh via `generate-loop-script.js` and launch in background.

### BUILD (Multi-Agent TDD)
Orchestrator spawns Task agents per atomic task. TDD mandatory (RED->GREEN->REFACTOR). Code-simplifier runs post-build.

### REVIEW
Automated validation (test, lint, types, build) + adversarial self-review + skill invocations (`/code-review`, `/security-audit`).

### FIX
Address issues.json. Root cause check mandatory. Fix -> commit -> revalidate -> back to REVIEW.

### SHIP
verify-app subagent -> git push -> PR create -> merge. Write lessons-learned.md.

---

## Task Sync Layer (Optional)

**Flag:** `DEEP_LOOP_TASKS_ENABLED=true`

Files are source of truth. Task layer adds crash recovery + visibility.

```
Files (.deep-{session}/)     <- SOURCE OF TRUTH
       <-> sync at phase boundaries
Task Management Layer        <- Recovery + Visibility
```

---

## Context Management

Each iteration starts fresh. Hook feeds phase prompt + file paths.
Read state from: task.md, plan.md, state.json, issues.json.
No conversation history accumulation. Enables 8+ hour loops.

---

## Git Operations

After each task: `git add -A && git commit -m "[deep] <phase>: <description>"`
SHIP: `gh pr create --base main --fill && gh pr merge --auto --squash`

---

## Loop Control

| Action | Method |
|--------|--------|
| Check status | Read `.deep-{session8}/state.json` |
| Cancel | `/cancel-deep` or `touch .deep-{session8}/FORCE_EXIT` |
| Force complete | Set `"complete": true` in state.json |

---

## Safety

1. **Max iterations** - Hard limit (3/10/20 by complexity)
2. **Staleness** - Auto-exits after 8 hours inactive
3. **Force exit** - `touch .deep-{session8}/FORCE_EXIT`

---

## NOW EXECUTE

1. **Triage** the task (check --no-challenge flag)
2. **Initialize** `.deep-{session8}/` with `"active": true`
3. **Run** phases in order
4. **Output promises** as phases complete
5. **Ship** when `<promise>DEEP_COMPLETE</promise>`
