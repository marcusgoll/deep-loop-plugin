# Decision Checker Subagent

Validates BUILD implementation against locked decisions in `decisions.md`.

## Purpose

Prevents mid-build pivots from locked architectural decisions. If BUILD deviates from PLAN decisions, this subagent flags it before review.

## When to Invoke

Call after BUILD completes, before REVIEW:

```
Task tool with:
  subagent_type: "general-purpose"
  model: "haiku"
  description: "Check: decision compliance"
  prompt: |
    You are validating implementation against locked decisions.

    Read: .deep-{session8}/decisions.md
    Check: Recent git diff or changed files

    For each locked decision, verify implementation matches:
    - Correct libraries used?
    - Correct patterns followed?
    - No contradicting implementations?

    Output: COMPLIANT or DRIFT_DETECTED: [list of violations]
```

## Input

### decisions.md Format

```markdown
## Locked Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| State management | Zustand | Simple, no boilerplate |
| API pattern | REST | Team familiarity |
| Auth | Clerk | Already integrated |
| Styling | Tailwind | Existing setup |
| Database | Postgres via Prisma | Type safety |
```

### Files to Check

```bash
# Get changed files since deep loop started
git diff --name-only HEAD~$(git rev-list --count HEAD --since="<startedAt>")
```

## Validation Rules

| Decision Type | Check Method |
|---------------|--------------|
| Library choice | Check imports in changed files |
| Pattern | Check code structure matches expected pattern |
| Framework | Verify framework-specific patterns used |
| Database | Check ORM usage matches decision |
| Styling | Check class names/style approach |

## Output Format

### COMPLIANT

```
COMPLIANT

All implementations match locked decisions:
- State management: Zustand used ✓
- API pattern: REST endpoints ✓
- Auth: Clerk integration ✓
```

### DRIFT_DETECTED

```
DRIFT_DETECTED

Violations found:

1. **State Management**
   - Decision: Zustand
   - Found: Redux imports in src/store/index.ts
   - Line: import { configureStore } from '@reduxjs/toolkit'

2. **API Pattern**
   - Decision: REST
   - Found: GraphQL schema in src/graphql/schema.ts

Recommendation:
- Revert to planned approach, or
- Update decisions.md with user approval before proceeding
```

## Drift Handling

When DRIFT_DETECTED:

1. **Pause BUILD** - Do not proceed to REVIEW
2. **Ask user** via AskUserQuestion:
   ```json
   {
     "question": "Implementation drifted from plan. How to proceed?",
     "header": "Decision Drift",
     "options": [
       {"label": "Revert to plan", "description": "Undo drift, implement as originally planned"},
       {"label": "Update decisions", "description": "Lock the new approach instead"},
       {"label": "Ignore drift", "description": "Proceed anyway (not recommended)"}
     ]
   }
   ```

3. **If revert**: Undo drifted changes, re-implement
4. **If update**: Modify decisions.md, continue to REVIEW
5. **If ignore**: Log warning, proceed with risk noted

## Integration Points

### In REVIEW Phase

Before running validations:

```markdown
**Pre-REVIEW: Decision compliance check**

1. Read .deep-{session8}/decisions.md
2. Invoke decision-checker subagent
3. If DRIFT_DETECTED: Handle before continuing
4. If COMPLIANT: Proceed with validation
```

### In stop-hook-v2.js

Can be called automatically when BUILD_COMPLETE detected:

```javascript
// After BUILD_COMPLETE promise detected
if (fs.existsSync(getDeepPath('decisions.md'))) {
  // Inject decision check into next iteration
  // Or flag for manual review
}
```

## Example Session

```
[BUILD] Task 3 complete
[BUILD] All tasks complete, running code-simplifier...
[BUILD] code-simplifier: NO_CHANGES
[BUILD] Running decision compliance check...

Decision Checker Results:
- State management: Zustand ✓
- API pattern: REST ✓
- Auth: Clerk ✓
- Database: Prisma ✓

COMPLIANT - All decisions honored.

<promise>BUILD_COMPLETE</promise>
```

## Configuration

### Skip Decision Check

If decisions.md doesn't exist, skip check:

```javascript
if (!fs.existsSync(getDeepPath('decisions.md'))) {
  return 'SKIPPED - No decisions.md found';
}
```

### Strict Mode

Set in state.json to block on ANY drift:

```json
{
  "strictDecisions": true
}
```

In strict mode, DRIFT_DETECTED blocks progress without user prompt.

## NOW EXECUTE

When invoked:
1. Read decisions.md locked decisions
2. Get list of changed files
3. For each decision, check relevant files
4. Output COMPLIANT or DRIFT_DETECTED with details
