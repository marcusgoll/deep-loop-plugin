# Deep Loop - Deterministic Development Protocol

A self-correcting development loop: **[RLM_EXPLORE] -> PLAN -> BUILD -> REVIEW -> FIX -> SHIP**

## Quick Start

1. **Triage** the task (complexity + execution mode)
2. **[Optional] RLM Explore** if codebase is large (>5000 files OR >10MB)
3. **Initialize** `.deep/` state directory
4. **Execute** loop with automatic subagent invocation
5. **Ship** - commit, PR, merge - only when all gates pass

**CRITICAL: Git operations are NOT optional. Every successful build MUST commit. Every completed loop MUST create PR and merge.**

## Step 1: Triage

### Complexity Level

| Level | Signals | Iterations |
|-------|---------|------------|
| **QUICK** | Single file, obvious fix, <30 lines | 3 |
| **STANDARD** | 2-5 files, some design decisions | 10 |
| **DEEP** | 6+ files, architectural, high-stakes | 20 |

**NOTE:** ALL complexity levels require full CI/CD workflow (commit, push, PR, CI, merge). QUICK does not mean "skip git" - it means fewer iterations.

### Execution Mode (Ralph vs Sequential)

| Mode | When to Use | How |
|------|-------------|-----|
| **Sequential** | Tasks depend on each other, <3 tasks | Standard loop in-session |
| **Ralph** | 3+ independent tasks, parallelizable | Spawn Task agents |

**Default behavior:**
- QUICK: Always sequential
- STANDARD: Sequential unless explicitly parallel tasks
- DEEP: Prefer Ralph if 3+ independent tasks identified in PLAN

## Step 2: Initialize State

Create `.deep/` directory and files:
- `.deep/state.json` - Loop state
- `.deep/task.md` - Original task
- `.deep/plan.md` - Start with `phase: PLAN` (or `RLM_EXPLORE` if large codebase)

## Step 2.5: RLM Explore (Optional)

**Trigger:** Codebase exceeds 5000 files OR 10MB total size

### Detection

```bash
# Count files
find . -type f \( -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.py" \) | wc -l

# Check size
du -sh . 2>/dev/null
```

### When to Use

| Codebase Size | Action |
|---------------|--------|
| <1000 files, <5MB | Skip RLM_EXPLORE, go to PLAN |
| 1000-5000 files | Optional RLM_EXPLORE |
| >5000 files OR >10MB | **Recommended** RLM_EXPLORE |

### Execution

If RLM_EXPLORE needed, invoke via Task tool:

```
Task tool with:
  subagent_type: "general-purpose"
  description: "RLM: explore codebase"
  prompt: |
    You are executing RLM_EXPLORE phase for a large codebase.
    Goal: [task description]

    Follow rlm-explore skill protocol:
    1. Probe codebase structure
    2. Chunk by module/directory
    3. Spawn haiku sub-agents per chunk
    4. Aggregate into exploration report

    Write output to .deep/exploration.md
    Track costs in .deep/rlm-context.json

    When done: <promise>EXPLORED</promise>
```

### Output

- `.deep/exploration.md` - Codebase map and architecture
- `.deep/rlm-context.json` - Cost tracking

### Transition

After RLM_EXPLORE completes:
1. Update state.json: `"phase": "PLAN"`
2. PLAN phase consumes exploration.md for better task breakdown

## Progress Monitoring

During BUILD and FIX phases, track current step via output detection. Update `.deep/state.json` with:

```json
{
  "phase": "BUILD",
  "current_step": "Implementing",
  "task_index": 2,
  "started_at": "2025-01-18T10:00:00Z"
}
```

### Step Detection Patterns

| Pattern Detected | Current Step |
|-----------------|--------------|
| `git commit`, `git add` | Committing |
| `progress.txt` | Logging |
| `PRD.md`, `prd.json` | Updating PRD |
| `lint`, `eslint`, `biome` | Linting |
| `test`, `vitest`, `jest`, `pytest` | Testing |
| `.test.`, `.spec.`, `__tests__` | Writing tests |
| Write/Edit tool calls | Implementing |
| Read/Glob/Grep tool calls | Reading code |

### Step Display (for user visibility)

When executing tasks, prefix output with current step:

```
[BUILD] Implementing → Adding user validation...
[BUILD] Testing → Running vitest...
[BUILD] Committing → Staged 3 files...
```

This helps users understand progress without needing to read full output.

---

## Step 3: Execute the Loop

### PHASE: PLAN

Create `.deep/plan.md` with:
- Problem statement
- Testable acceptance criteria
- Atomic task breakdown
- **Ralph decision**: Mark tasks `sequential` or `parallel`

**Transition:** Update state.json `phase: BUILD`

---

### PHASE: BUILD (Sequential Mode)

For each task:
1. Mark in_progress in TodoWrite
2. Implement
3. Validate (test, lint, typecheck)
4. **COMMIT IMMEDIATELY** (see Git Operations below)
5. Log issue if fail, retry (max 3x)

**MANDATORY: After BUILD completes, invoke code-simplifier subagent:**

Use Task tool with:
- subagent_type: "general-purpose"
- description: "Simplify: post-build cleanup"
- prompt: "You are a code simplification specialist. Review recently changed code. Look for unnecessary complexity. Apply simplifications. DO NOT: Add features, change public interfaces, break tests. Output: SIMPLIFIED or NO_CHANGES"

**Transition:** Update state.json `phase: REVIEW`

---

### PHASE: BUILD (Ralph Mode)

When mode=ralph:

**1. Convert plan to `.deep/prd.json`** with tasks array

**2. For each task where `passes: false`, spawn Task agent:**

Use Task tool with:
- subagent_type: "general-purpose"
- description: "Ralph: task-001"
- prompt: "You are executing a single task from a PRD backlog. Implement ONLY this task. Run validation. Commit. Output: TASK_PASSED or TASK_FAILED: [reason]"

**3. For parallel tasks, spawn multiple in ONE message**

**4. Process results:**
- TASK_PASSED: Update prd.json
- TASK_FAILED: Increment attempts, retry if < 3

**5. When all tasks pass:** Run code-simplifier, then transition to REVIEW

---

### PHASE: REVIEW

Run comprehensive validation:
1. npm test or equivalent
2. npm run typecheck
3. npm run lint
4. npm run build

Record in `.deep/test-results.json`

**For large changesets (20+ files):** Use RLM-style verification:

```
Task tool with:
  subagent_type: "general-purpose"
  description: "RLM: verify changeset"
  prompt: |
    You are executing RLM verification for a large changeset.
    Follow rlm-verify skill protocol:
    1. Chunk files by module/concern
    2. Spawn haiku reviewers per chunk
    3. Aggregate issues into .deep/issues.json
    4. Write report to .deep/verification-report.md

    When done: <promise>VERIFIED</promise>
```

**If issues found:** Add to `.deep/issues.json`, transition to FIX
**If clean:** Transition to SHIP

---

### PHASE: FIX

Address `.deep/issues.json`:
1. Fix each issue
2. **Commit atomically** (see Git Operations)
3. Run validation

**Transition:** Clear issues.json, return to REVIEW

---

### PHASE: SHIP

**CI Verification (Automatic):**

After PR creation, the hook automatically polls CI status:
- Polls every 15 seconds for up to 10 minutes
- Progress shown: `CI: 3✓ 2⏳ 0✗`
- If CI fails → transitions to FIX phase with failure details
- If CI times out → blocks with timeout message
- Results written to `.deep/git-results.json`

**MANDATORY: Before completing, invoke verify-app subagent with smart detection:**

Use Task tool with:
- subagent_type: "general-purpose"
- description: "Verify: smart E2E testing"
- prompt: |
    You are an E2E verification specialist with smart detection.

    ## Step 1: Detect App Type
    Check for: package.json scripts, src/app or src/pages, api/ routes, bin/ CLI, exports

    ## Step 2: Check Environment
    - Is dev server running? (check ports 3000, 3001, 5173, 8000)
    - Are browser tools available? (try mcp__claude-in-chrome__tabs_context_mcp)

    ## Step 3: Route to Verification Method
    | App Type | Browser Available | Method |
    |----------|-------------------|--------|
    | Web App | YES | Browser E2E (invoke browser-test) |
    | Web App | NO | HTTP curl tests |
    | API | - | Curl endpoint tests |
    | CLI | - | Command execution tests |
    | Library | - | Import and type tests |

    ## Step 4: Run Verification
    For web apps with browser: Use mcp__claude-in-chrome__* tools
    - tabs_context_mcp → tabs_create_mcp → navigate → test flows → screenshot

    ## Step 5: Report Results
    Output: VERIFIED, issues list, or SKIPPED with reason

    Follow verify-app subagent protocol for full details.

**MANDATORY: Git Finalization (if in git repo):**

Execute ALL of these steps - do NOT skip:

```bash
# 1. Check if we're in a git repo and on a feature branch
git rev-parse --git-dir && git branch --show-current

# 2. Push the branch
git push -u origin HEAD

# 3. Create PR with auto-merge enabled
gh pr create --base main --fill --body "$(cat <<'EOF'
## Summary
<auto-generated from commits>

## Test plan
- All tests pass
- Verified via deep-loop

Generated via /deep
EOF
)"

# 4. Enable auto-merge (squash)
gh pr merge --auto --squash

# 5. Record PR URL
gh pr view --json url -q .url
```

**If on main/master:** Skip PR, work is already merged via atomic commits.

**Completion Criteria:**
- [ ] All acceptance criteria met
- [ ] All tests pass
- [ ] No type errors
- [ ] No lint errors
- [ ] verify-app passes (or skipped with reason)
- [ ] **PR created AND auto-merge enabled** (if feature branch)
- [ ] Record PR URL in `.deep/git-results.json`

**When ALL pass:** Update state.json `phase: COMPLETE, complete: true`
Output: `<promise>COMPLETE</promise>`

**Completion Summary (Automatic):**

On successful exit, the hook outputs a summary:

```
## Deep Loop Complete ✓

**Session:** a7f3c2b9
**Task:** Add user validation
**Duration:** 12 minutes
**Iterations:** 5/10

### Tasks
4/4 completed

### Verification
Tests: ✓ | Types: ✓ | Lint: ✓ | Build: ✓

### Git
Commits: 4
PR: #123
CI: ✓ Passed
```

Summary is also saved to `.deep/summary.json`.

---

## Git Operations Reference

### After Each Successful Task (BUILD/FIX phases)

```bash
# Stage changes
git add -A

# Commit with deep-loop tag
git commit -m "$(cat <<'EOF'
[deep] <phase>: <what was done>

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

### Commit Message Format

| Phase | Tag | Example |
|-------|-----|---------|
| BUILD | `[deep] implement:` | `[deep] implement: add user validation` |
| FIX | `[deep] fix:` | `[deep] fix: resolve type error in auth` |
| REVIEW | `[deep] refactor:` | `[deep] refactor: simplify error handling` |

### PR Creation (SHIP phase)

```bash
# Create PR
gh pr create --base main --title "[deep] <task summary>" --body "..."

# Enable auto-merge immediately
gh pr merge --auto --squash

# If CI required, this waits for checks then merges automatically
```

### Auto-Merge Requirements

Auto-merge (`gh pr merge --auto`) requires:
1. Branch protection rules allow it
2. CI checks pass
3. No merge conflicts

If auto-merge fails, manually merge:
```bash
gh pr merge --squash
```

---

## AI Conflict Resolution

When merge conflicts occur (especially in Ralph mode with parallel branches), use AI to resolve them automatically before escalating to the user.

### When Conflicts Occur

1. **Ralph mode branch merges** - Parallel agents may touch same files
2. **Integration branch creation** - Merging completed group branches
3. **PR merge failures** - CI passes but merge conflicts exist

### Resolution Protocol

When `git merge` fails with conflicts:

```bash
# 1. Identify conflicted files
git diff --name-only --diff-filter=U
```

**2. Invoke conflict-resolver subagent:**

Use Task tool with:
- subagent_type: "general-purpose"
- model: "sonnet"
- description: "Resolve: merge conflicts"
- prompt: |
    You are resolving git merge conflicts. Conflicted files:
    [list from git diff --name-only --diff-filter=U]

    For each conflicted file:
    1. Read the file to see conflict markers (<<<<<<< HEAD, =======, >>>>>>> branch)
    2. Understand what BOTH versions are trying to do
    3. Edit the file to intelligently combine both changes
    4. Remove ALL conflict markers
    5. Ensure resulting code compiles and is valid

    After resolving all conflicts:
    1. Run `git add` on each resolved file
    2. Run `git commit --no-edit` to complete the merge

    CRITICAL: Preserve functionality from BOTH branches. The goal is integration, not picking sides.

    Output: RESOLVED or FAILED: [reason]

**3. If AI resolution fails:**

```bash
# Abort the merge
git merge --abort
```

Then escalate to user:
```
Merge conflict could not be auto-resolved.
Conflicted files: [list]
Please resolve manually: git merge <branch>
```

### Conflict Resolution in Ralph Mode

For parallel group workflows with integration branches:

```
Group 1 tasks complete → Create integration-group-1 branch
  ├── Merge agent-1 branch ✓
  ├── Merge agent-2 branch ✓
  └── Merge agent-3 branch ⚠️ CONFLICT
      └── Invoke conflict-resolver subagent
          ├── SUCCESS → Continue to Group 2
          └── FAILED → Abort, notify user, preserve branches
```

### Record Conflict Resolution

Log to `.deep/conflict-log.json`:

```json
{
  "conflicts": [
    {
      "timestamp": "2025-01-18T10:30:00Z",
      "source_branch": "ralphy/agent-3-add-validation",
      "target_branch": "integration-group-1",
      "files": ["src/auth/validate.ts", "src/types.ts"],
      "resolution": "AI_RESOLVED",
      "model": "sonnet"
    }
  ]
}
```

---

## Subagent Invocation Summary

| Phase Transition | Subagent | Required |
|-----------------|----------|----------|
| START -> PLAN (large codebase) | rlm-explorer | If >5000 files |
| BUILD -> REVIEW | code-simplifier | YES |
| REVIEW (large changeset) | rlm-verify | If >20 files changed |
| REVIEW -> SHIP | verify-app | YES (smart detection) |
| verify-app (web + browser) | browser-test | If web app + browser available |
| Merge conflict (any phase) | conflict-resolver | On conflict |

**These are NOT optional.** The loop MUST invoke these subagents via Task tool.

### Smart Verification Flow

```
verify-app invoked
    │
    ├─ Detect app type
    │   ├─ Web App? ──► Check browser tools
    │   │               ├─ Available ──► browser-test subagent
    │   │               └─ Unavailable ──► curl/HTTP fallback
    │   ├─ API? ──► curl endpoint tests
    │   ├─ CLI? ──► command execution tests
    │   └─ Library? ──► import/type tests
    │
    └─ Report: VERIFIED | issues | SKIPPED
```

---

## RLM Mode (Large Context Handling)

For tasks involving large contexts (>5000 files OR >10MB):

### Auto-Detection

The loop detects when RLM mode is beneficial:
- Codebase size check during triage
- Changeset size check during REVIEW

### How It Works

1. **Chunking** - Context split into manageable pieces (~200K chars)
2. **Sub-Calls** - Recursive LLM queries per chunk (haiku for cost)
3. **Aggregation** - Results synthesized via final LLM call

### Cost Tracking

RLM operations track costs in `.deep/rlm-context.json`:

```json
{
  "loaded_at": "2025-01-18T10:00:00Z",
  "total_chars": 5000000,
  "chunks": [
    {"path": "src/", "chars": 1200000, "processed": true}
  ],
  "sub_calls": 15,
  "model_used": "haiku",
  "cost_estimate": "$0.45"
}
```

### Limits

- **Max sub-calls:** 50 (prevents runaway costs)
- **Chunk size:** ~200K chars
- **Cost warning:** At 30 sub-calls

### Manual Trigger

User can force RLM mode: "use RLM mode for this", "chunk and process"

---

## Loop Control

**Check status:** `cat .deep/state.json`
**Cancel:** `/cancel-deep` or set `complete: true` manually
**Force complete:** Set `phase: COMPLETE, complete: true` in state.json

## Commands

| Command | Action |
|---------|--------|
| `/deep <task>` | Start deep loop on task |
| `/deep-status` | Show current phase and progress |
| `/cancel-deep` | Cancel loop, set state to CANCELLED |

---

## Edge Case Handling (v5.5)

1. **Infinite Loop Prevention** - Hard iteration limit (3/10/20)
2. **Staleness Detection** - 8-hour threshold
3. **Incomplete Work on Exit** - Verifies test-results.json + git-results.json
4. **Lost Context Recovery** - Persistent tasks preserved
5. **Over-engineering Prevention** - code-simplifier enforced
6. **Clear Definition of Done** - Completion checklist
7. **Git Chaos Prevention** - Atomic commits + PR verification
8. **Parallel Task Coordination** - Lock file mechanism
9. **Verification Blindness Fix** - verify-app enforced
10. **Stuck Approach Detection** - User escalation after 3 failures
11. **RLM Cost Tracking** - Warns at 30 sub-calls, blocks at 50
12. **Active CI Polling** - Auto-polls CI for 10 min, blocks on failure
13. **Completion Summary** - Shows session stats, tasks, commits, PR on exit
14. **Merge Conflict Resolution** - AI conflict-resolver before user escalation
15. **Progress Visibility** - Step detection for user-facing status updates
16. **Smart App Detection** - Auto-detect app type for appropriate verification
17. **Browser E2E Testing** - Chrome automation when available for web apps

---

## NOW EXECUTE

You have read the deep loop protocol. Now execute it:

1. **Triage** the task provided
2. **Initialize** `.deep/` state
3. **Run** the loop phases in order
4. **Commit after each task** - not optional
5. **Invoke subagents** at mandatory points via Task tool
6. **Create PR and enable auto-merge** in SHIP phase
7. **Ship** when all gates pass
