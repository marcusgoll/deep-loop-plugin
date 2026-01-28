---
name: deep-quick
description: Skill from deep-loop plugin
version: 8.0.0
---

# Deep Quick - Fast Mode for Small Tasks

Skip planning ceremony for quick tasks. Straight to BUILD with 3-iteration limit.

## When to Use

| Use Quick Mode | Use Full `/deep` |
|----------------|------------------|
| Single file fix | Multi-file feature |
| Obvious bug | Architectural decisions |
| <30 lines change | >50 lines |
| "Fix typo in X" | "Implement feature Y" |

## Execution Flow

```
TRIAGE (auto) -> BUILD -> VERIFY -> COMMIT
```

No PLAN phase. No exploration. Just execute.

---

## Step 1: Initialize Quick State

Create `.deep-{session8}/` with minimal state:

```json
{
  "mode": "quick",
  "active": true,
  "sessionId": "{session8}",
  "iteration": 0,
  "maxIterations": 3,
  "startedAt": "2025-01-22T10:00:00Z",
  "task": "Brief task description"
}
```

Write task to `.deep-{session8}/task.md`.

**No plan.md needed for quick mode.**

---

## Step 2: BUILD (Direct)

Execute the task directly:

1. **Read** relevant file(s)
2. **Edit** to implement change
3. **Validate** (lint, types, test if applicable)
4. **Commit** atomically

```bash
git add -A
git commit -m "$(cat <<'EOF'
[quick] <description>

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

**If validation fails:**
- Fix immediately (iteration 2)
- If still failing at iteration 3: escalate to user

---

## Step 3: Verify (Simplified)

Run quick verification:

```bash
# If tests exist
npm test --passWithNoTests 2>/dev/null || true

# Type check if TS project
npm run typecheck 2>/dev/null || tsc --noEmit 2>/dev/null || true

# Lint
npm run lint 2>/dev/null || true
```

**For quick mode:** Warnings are acceptable. Only block on errors.

---

## Step 4: Code Simplifier (Optional)

**Only invoke if:**
- Change touched >10 lines
- Added new functions

Otherwise skip for speed.

If needed, use Task tool:
```
subagent_type: "general-purpose"
description: "Quick: simplify"
prompt: "Review the last commit. Remove unnecessary complexity. Keep changes minimal."
```

---

## Step 5: Complete

Update state:
```json
{
  "mode": "quick",
  "active": false,
  "complete": true,
  "iteration": 1,
  "result": "success"
}
```

**Output:** `<promise>QUICK_COMPLETE</promise>`

---

## Iteration Limits

| Iteration | Action |
|-----------|--------|
| 1 | Execute task |
| 2 | Fix validation errors |
| 3 | Final attempt or escalate |

**Hard limit: 3 iterations.** If not complete, ask user for guidance.

---

## State File Location

`.deep-{session8}/state.json` with `"mode": "quick"`

The stop hook recognizes quick mode and:
- Uses 3-iteration limit instead of 10/20
- Looks for `<promise>QUICK_COMPLETE</promise>`
- Allows faster exits

---

## Examples

### Example 1: Typo Fix

User: `/deep quick fix typo in README.md`

```
1. Read README.md
2. Find and fix typo
3. Commit: [quick] fix typo in README
4. <promise>QUICK_COMPLETE</promise>
```

### Example 2: Add Export

User: `/deep quick export Button from components/index.ts`

```
1. Read components/index.ts
2. Add: export { Button } from './Button'
3. Validate: tsc --noEmit
4. Commit: [quick] export Button from index
5. <promise>QUICK_COMPLETE</promise>
```

### Example 3: Quick Bug Fix

User: `/deep quick null check in validateUser`

```
1. Find validateUser function (Grep)
2. Read file
3. Add null check
4. Run tests
5. Commit: [quick] add null check to validateUser
6. <promise>QUICK_COMPLETE</promise>
```

---

## Error Handling

| Error | Action |
|-------|--------|
| Can't find file | Ask user for path |
| Validation fails (iter 1-2) | Fix and retry |
| Validation fails (iter 3) | Escalate to user |
| Task too complex | Suggest `/deep` instead |

**Complexity detection triggers:**
- Task mentions 3+ files
- Task involves "refactor", "redesign", "architecture"
- Task requires design decisions

On complexity trigger:
```
This task seems complex. Want me to use full /deep mode instead?
```

---

## NOW EXECUTE

1. Initialize quick state (`.deep-{session8}/state.json` with mode: "quick")
2. Execute task directly
3. Validate and commit
4. Output `<promise>QUICK_COMPLETE</promise>`
