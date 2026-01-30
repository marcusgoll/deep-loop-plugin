---
name: deep-triage
description: Classify task complexity as QUICK/STANDARD/DEEP. Use when assessing challenge difficulty, triaging work, deciding implementation approach, or when user asks "how complex" or "how hard" something is.
version: 9.0.0
---

# Deep Triage - Complexity Classification

When invoked, systematically assess the challenge's complexity level.

## Classification Framework

### QUICK (Skip to implementation)
- Bug fix with obvious cause
- Single-file change
- Clear, unambiguous requirements
- Existing pattern to follow
- < 30 minutes of work

**Action:** Skip planning, deliver concisely. Simple branch if git needed.

### STANDARD (Full process, standard depth)
- Meaningful feature with some design decisions
- 2-5 files affected
- Some architectural considerations
- Tests needed
- 1-4 hours of work

**Action:** Full Deep process. Consider worktree for isolation.

### DEEP (Full process with user checkpoints)
- Architectural or system-wide changes
- Ambiguous requirements needing clarification
- High-stakes (affects critical paths)
- Multiple valid approaches with significant tradeoffs
- Cross-cutting concerns
- > 4 hours of work

**Action:** Full process with user validation at each phase transition. Worktree isolation required.

## Triage Checklist

Answer these questions to classify:

1. **Scope:** How many files will change?
   - 1 file = QUICK
   - 2-5 files = STANDARD
   - 6+ files = DEEP

2. **Ambiguity:** Are requirements crystal clear?
   - Yes, obvious = QUICK
   - Mostly clear = STANDARD
   - Needs clarification = DEEP

3. **Risk:** What breaks if this goes wrong?
   - Nothing critical = QUICK
   - Feature degradation = STANDARD
   - System instability = DEEP

4. **Approaches:** How many valid solutions exist?
   - One obvious way = QUICK
   - 2-3 reasonable options = STANDARD
   - Many approaches with tradeoffs = DEEP

5. **Patterns:** Does existing code show the way?
   - Copy existing pattern = QUICK
   - Adapt existing pattern = STANDARD
   - Create new pattern = DEEP

## Output Format

```
COMPLEXITY: [QUICK | STANDARD | DEEP]

Reasoning:
- Scope: [assessment]
- Ambiguity: [assessment]
- Risk: [assessment]
- Approaches: [assessment]
- Patterns: [assessment]

Recommended workflow:
- [Specific guidance based on classification]
```

## When to Re-triage

If during implementation you discover:
- More files affected than expected → escalate
- Hidden complexity → escalate
- Simpler than thought → can de-escalate (but don't skip verification)
