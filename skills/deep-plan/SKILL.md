---
name: deep-plan
description: Create implementation plans with acceptance criteria. Use when user asks to 'plan this', 'create PRD', 'break down task'. Supports PRD-to-task-queue conversion.
version: 9.2.0
argument-hint: [task] or --prd [file] or --generate [description]
---

# Deep Plan - Strategic Planning & PRD Conversion

Three modes:
1. **Single Task Planning** - Deep dive into one task (original behavior)
2. **PRD -> Task Queue** - Convert PRD/spec into tasks.md for deep-execute
3. **Generate PRD** - Create PRD from feature description, then convert to tasks

## Mode Detection

On invocation, determine mode:

```
/deep plan              -> Ask which mode
/deep plan <task>       -> Single task planning
/deep plan --prd        -> PRD conversion mode (existing PRD)
/deep plan --prd <file> -> PRD conversion with specific file
/deep plan --generate   -> Generate PRD from description
```

Use AskUserQuestion if ambiguous:

```json
{
  "question": "What type of planning?",
  "header": "Plan Mode",
  "options": [
    {"label": "Plan a single task", "description": "Deep dive planning for one feature/task"},
    {"label": "Convert PRD to tasks", "description": "Parse existing PRD/spec into task queue"},
    {"label": "Generate PRD first", "description": "Create PRD from feature description, then convert"}
  ],
  "multiSelect": false
}
```

---

# MODE 1: Single Task Planning

When invoked, create a comprehensive implementation plan that enables deterministic execution.

## The Planning Mindset

1. **Understand before planning** - Explore the codebase first
2. **Testable criteria** - Every acceptance criterion must be verifiable
3. **Atomic tasks** - Each task should be completable in one focused session
4. **Risk awareness** - Identify what could go wrong upfront

## Phase 0: RLM Exploration Check

**Before Phase 1, assess if RLM exploration is needed.**

### Detection

```bash
# Count source files
find . -type f \( -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.py" -o -name "*.go" \) 2>/dev/null | wc -l

# Check total size
du -sh . 2>/dev/null
```

### Decision Matrix

| Files | Size | Action |
|-------|------|--------|
| <1000 | <5MB | Proceed to Phase 1 (standard exploration) |
| 1000-5000 | 5-10MB | Consider RLM exploration |
| >5000 | >10MB | **Invoke RLM exploration** |

### RLM Exploration Invocation

If large codebase detected:

```
Task tool with:
  subagent_type: "deep-loop:rlm-explorer"
  model: "haiku"
  description: "RLM: explore before planning"
  prompt: |
    Large codebase detected. Execute RLM exploration:

    1. Chunk by top-level directories
    2. For each chunk, identify:
       - Purpose/responsibility
       - Key exports
       - Dependencies
    3. Aggregate into architecture map

    Write to .deep/exploration.md
    Track costs in .deep/rlm-context.json

    Return summary for PLAN phase consumption.
```

Then proceed to Phase 1 with exploration.md as context.

## Phase 1: Discovery

### Explore the Context
```bash
# Understand project structure
ls -la
cat package.json 2>/dev/null || cat Cargo.toml 2>/dev/null || cat requirements.txt 2>/dev/null

# Find related code
grep -r "relevant_keyword" --include="*.ts" --include="*.py" -l

# Check for ADRs
ls docs/adr/ 2>/dev/null || ls docs/adrs/ 2>/dev/null || ls adr/ 2>/dev/null
```

### Questions to Answer
- What existing code relates to this task?
- What patterns does the codebase use?
- What dependencies are involved?
- Are there tests we can learn from?
- **Do any ADRs constrain the implementation approach?**

## Phase 2: Problem Definition

### Write the Problem Statement
```markdown
## Problem Statement

**Current State**: [What exists now / what's broken / what's missing]

**Desired State**: [What we want to achieve]

**Why It Matters**: [Business/user impact]

**Constraints**: [Technical, time, or resource limitations]
```

## Phase 3: Acceptance Criteria

### Write TESTABLE Criteria

Each criterion must be verifiable by:
- An automated test
- A specific command
- A measurable outcome

**Good Examples:**
```markdown
## Acceptance Criteria

- [ ] `npm test` passes with 0 failures
- [ ] API endpoint `/users` returns 200 with valid JSON
- [ ] Build size < 500KB (verified by `npm run build`)
- [ ] No TypeScript errors (`tsc --noEmit` exits 0)
- [ ] User can complete checkout flow in < 3 clicks
```

**Bad Examples:**
- "Code is clean" (not measurable)
- "Works well" (not specific)
- "Users are happy" (not testable in code)

## Phase 4: Task Breakdown

### Create Atomic Tasks

Each task should:
- Be completable in one focused session
- Have clear start and end states
- Be independently testable
- Build on previous tasks

```markdown
## Task Breakdown

### Phase 1: Foundation
1. [ ] Create database migration for `users` table
   - Input: Migration file
   - Output: `npm run migrate` succeeds
   - Verify: Table exists in DB

2. [ ] Implement User model with validation
   - Input: Model file
   - Output: Unit tests pass
   - Verify: `npm test -- --grep User`

### Phase 2: API Layer
3. [ ] Create POST /users endpoint
   - Input: Route handler
   - Output: Integration test passes
   - Verify: `curl -X POST localhost:3000/users`

4. [ ] Create GET /users/:id endpoint
   - Input: Route handler
   - Output: Returns user JSON
   - Verify: `curl localhost:3000/users/1`

### Phase 3: Frontend
5. [ ] Create UserForm component
   - Input: React component
   - Output: Component renders
   - Verify: Storybook story works

6. [ ] Wire form to API
   - Input: API integration
   - Output: E2E test passes
   - Verify: Playwright test
```

## Phase 5: Technical Approach

### Document the How
```markdown
## Technical Approach

### Architecture
[Diagram or description of component relationships]

### Key Decisions
1. **[Decision]**: [Why this approach vs alternatives]
2. **[Decision]**: [Why this approach vs alternatives]

### ADR Constraints
[List any ADRs from docs/adr/ that constrain this task's implementation]
- ADR-XXXX: [Constraint summary and how it affects this task]

### Dependencies
- [Package/library]: [Version] - [Purpose]

### API Contracts
[If applicable, document request/response shapes]
```

## Phase 6: Risk Assessment

### Identify and Mitigate
```markdown
## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| [Risk 1] | High/Med/Low | High/Med/Low | [How to prevent/handle] |
| [Risk 2] | High/Med/Low | High/Med/Low | [How to prevent/handle] |

### Rollback Plan
If the implementation fails:
1. [Step to revert]
2. [Step to restore previous state]
```

## Phase 7: Validation Strategy

### Define How to Verify
```markdown
## Validation Strategy

### Automated Tests
- Unit: [What to test at unit level]
- Integration: [What to test at integration level]
- E2E: [Critical user flows to verify]

### Manual Verification
- [ ] [Manual check 1]
- [ ] [Manual check 2]

### Performance Criteria
- [Metric]: [Threshold]
```

## Output Format

The final plan should be written to `.deep/plan.md` (if in a deep loop) or presented to the user.

```markdown
# Plan: [Task Title]

## Problem Statement
[From Phase 2]

## Acceptance Criteria
[From Phase 3]

## Task Breakdown
[From Phase 4]

## Technical Approach
[From Phase 5]

## Risk Assessment
[From Phase 6]

## Validation Strategy
[From Phase 7]

---
*Plan created: [timestamp]*
*Estimated tasks: [N]*
*Risk level: [Low/Medium/High]*
```

## Integration with Deep Loop

When used within `/deep-loop`:
1. Write plan to `.deep/plan.md`
2. Update `.deep/state.json` with plan summary
3. If `noPause` is false and level is `deep`, ask for user approval
4. Transition to BUILD phase on approval

---

# MODE 2: PRD -> Task Queue Conversion

Convert PRDs, specs, or feature documents into atomic tasks for `/deep execute`.

## Step 1: Find PRD Source

```bash
# Check common locations
for f in PRD.md prd.md SPEC.md spec.md requirements.md REQUIREMENTS.md \
         docs/PRD.md docs/prd.md docs/requirements.md .github/PRD.md; do
  [ -f "$f" ] && echo "Found: $f"
done
```

If not found, use AskUserQuestion:

```json
{
  "question": "Where is your PRD or spec?",
  "header": "PRD Source",
  "options": [
    {"label": "Paste it here", "description": "I'll type/paste the requirements"},
    {"label": "File path", "description": "I'll provide the path"},
    {"label": "GitHub issue", "description": "Link to issue with requirements"},
    {"label": "Create PRD template", "description": "Help me write a PRD first"}
  ],
  "multiSelect": false
}
```

## Step 1.5: Discover ADR Constraints

**Before parsing the PRD, scan for Architecture Decision Records.**

```bash
# Check common ADR locations
for d in docs/adr docs/adrs adr adrs doc/adr .github/adr; do
  [ -d "$d" ] && echo "ADR directory found: $d"
done

# Also check for inline decisions files
for f in decisions.md DECISIONS.md docs/decisions.md .deep/decisions.md; do
  [ -f "$f" ] && echo "Decisions file found: $f"
done
```

### If ADRs Found

1. **Read each ADR file** in the directory
2. **Extract constraints** — look for:
   - `## Decision`: The chosen approach
   - `## Status`: Only apply `accepted` ADRs (skip `proposed`, `deprecated`, `superseded`)
   - `## Consequences`: Constraints that affect implementation
3. **Build constraint map** — key/value pairs:

```
ADR Constraints:
  ADR-0003 (Auth): Use Clerk, JWT in cookies (not headers)
  ADR-0004 (Database): SQLAlchemy ORM only, no raw SQL, bidirectional relationships
  ADR-0006 (Design): CSS variables for colors, no hardcoded hex, no dark: prefix
  ADR-0009 (Error): RFC7807 error format
  ADR-0011 (Rate): All endpoints require @limiter decorator
```

4. **Carry constraints forward** — inject into task generation (Step 3) so each task includes relevant ADR constraints as acceptance criteria

### If No ADRs Found

Proceed without — the decision-checker agent will still validate during REVIEW.

## Step 2: Parse PRD Structure

Extract these sections:

| Section | Markers | Maps To |
|---------|---------|---------|
| Goal | `## Goal`, `## Objective`, `## Overview` | Context for all tasks |
| User Stories | `## User Stories`, `As a...` | Task groups |
| Features | `## Features`, `### Feature:` | Individual tasks |
| Acceptance Criteria | `- [ ]`, `## Acceptance` | Task criteria |
| Technical | `## Technical`, `## Constraints` | Task constraints |
| Out of Scope | `## Out of Scope`, `## Non-goals` | Exclusions |

### Parsing Logic

```
For each User Story / Feature:
  1. Extract title
  2. Extract description
  3. Find acceptance criteria (checkboxes or bullet points)
  4. Identify dependencies (mentions of other features)
  5. Assess priority (explicit or inferred from order)
  6. Match relevant ADR constraints (from Step 1.5) to this feature
```

## Step 3: Generate Atomic Tasks

**Atomicity Rules:**
- One task = completable in <2 hours
- Single responsibility
- Testable acceptance criteria
- Clear done state

**Breakdown Patterns:**

| PRD Pattern | Generated Tasks |
|-------------|-----------------|
| "User can register" | 1. Add registration form UI<br>2. Add registration API endpoint<br>3. Add email validation<br>4. Add tests |
| "Dashboard shows metrics" | 1. Create dashboard layout<br>2. Add metrics API<br>3. Add chart components<br>4. Wire data to charts |
| "Integrate with Stripe" | 1. Add Stripe SDK<br>2. Create payment service<br>3. Add webhook handler<br>4. Add checkout flow |

**Task Format:**

```markdown
## [ ] task-XXX: {verb} {component} {outcome}
**Priority:** high|medium|low
**Added:** {date} by deep-plan
**Attempts:** 0
**Depends:** task-YYY (optional)
**Source:** PRD section "{section name}"
**ADR Constraints:** ADR-XXXX (if applicable)

{Description from PRD}

- [ ] {Acceptance criterion 1}
- [ ] {Acceptance criterion 2}
- [ ] {ADR constraint as criterion, e.g., "No raw SQL - use ORM (ADR-0004)"}
- [ ] Tests pass

---
```

**ADR Integration Rules:**
- Only add ADR constraints relevant to the specific task
- Database tasks → include ADR-0004 constraints
- Auth tasks → include ADR-0003 constraints
- UI tasks → include ADR-0006 constraints
- API endpoint tasks → include ADR-0009, ADR-0011 constraints
- Format: `{constraint description} (ADR-XXXX)`

## Step 4: Determine Dependencies

Build dependency graph:

```
Foundation tasks (no deps)     -> high priority
  |
Core feature tasks (deps: foundation) -> high priority
  |
Supporting tasks (deps: core)  -> medium priority
  |
Polish/enhancement tasks       -> low priority
```

**Dependency Detection:**
- Explicit: PRD says "after X is done" or "requires Y"
- Implicit: Data model before API, API before UI
- Technical: Database before backend, backend before frontend

**Priority Rules:**

| Task Type | Default Priority |
|-----------|-----------------|
| Setup/infrastructure | high |
| Data models/schema | high |
| Core API endpoints | high |
| Core UI components | medium |
| Secondary features | medium |
| Enhancements | low |
| Documentation | low |

## Step 5: User Review

Present summary before writing:

```
+---------------------------------------------------+
|           PRD -> TASK CONVERSION SUMMARY           |
+---------------------------------------------------+

Source: docs/PRD.md
Feature: User Authentication System

ADR Constraints Applied:
  ADR-0003: Auth via Clerk, JWT in cookies
  ADR-0004: SQLAlchemy ORM, bidirectional relationships
  (none found = "No ADRs found in project")

Tasks Generated: 12
  +- High Priority: 5
  +- Medium Priority: 5
  +- Low Priority: 2

Dependency Groups:
  Group 1 (parallel):  task-001, task-002
  Group 2 (after G1):  task-003, task-004, task-005
  Group 3 (after G2):  task-006, task-007, task-008
  Group 4 (after G3):  task-009, task-010, task-011, task-012

Estimated Complexity: STANDARD (10 iterations)

===================================================
```

```json
{
  "question": "How to proceed?",
  "header": "Confirm",
  "options": [
    {"label": "Write all to tasks.md", "description": "Add all 12 tasks to queue"},
    {"label": "Show task details", "description": "Review each task first"},
    {"label": "Adjust scope", "description": "Include/exclude specific features"},
    {"label": "MVP only", "description": "Just high priority tasks"}
  ],
  "multiSelect": false
}
```

## Step 6: Write to tasks.md

```bash
mkdir -p .deep

# Get next task ID
if [ -f .deep/tasks.md ]; then
  LAST=$(grep -o "task-[0-9]*" .deep/tasks.md | sort -t- -k2 -n | tail -1 | cut -d- -f2)
  NEXT=$((10#${LAST:-0} + 1))
else
  NEXT=1
  # Create header
  cat > .deep/tasks.md << 'EOF'
# Task Queue

Tasks for `/deep execute` to process.

---
EOF
fi

# Append tasks with zero-padded IDs (task-001, task-002, etc.)
```

## Step 7: Output Summary

```
+---------------------------------------------------+
|              TASKS CREATED                        |
+---------------------------------------------------+

Added 12 tasks to .deep/tasks.md

High Priority:
  task-001: Setup database schema [high]
  task-002: Create User model [high]
  task-003: Add auth middleware [high]
  task-004: Create login endpoint [high]
  task-005: Create register endpoint [high]

Medium Priority:
  task-006: Add login form UI [medium]
  task-007: Add register form UI [medium]
  task-008: Add session management [medium]
  task-009: Add password reset flow [medium]
  task-010: Add email verification [medium]

Low Priority:
  task-011: Add remember me feature [low]
  task-012: Add OAuth providers [low]

Next Steps:
  /deep execute  -> Start processing queue
  /deep status   -> View full task list
  /deep add      -> Add more tasks manually

===================================================
```

---

# MODE 3: Generate PRD from Feature Description

When user provides a feature description without an existing PRD, generate one first.

## Step 1: Gather Requirements via AskUserQuestion

```json
{
  "question": "Describe the feature you want to build",
  "header": "Feature",
  "options": [
    {"label": "I'll describe it now", "description": "Type your feature description"},
    {"label": "From GitHub issue", "description": "Provide issue URL"},
    {"label": "From conversation", "description": "Use what we discussed above"}
  ],
  "multiSelect": false
}
```

Follow-up questions (skip if obvious from description):

```json
{
  "question": "Who are the target users?",
  "header": "Users",
  "options": [
    {"label": "Developers", "description": "Building/integrating with API"},
    {"label": "End users", "description": "Using the app directly"},
    {"label": "Admins", "description": "Managing/configuring the system"},
    {"label": "All of the above", "description": "Multiple user types"}
  ],
  "multiSelect": true
}
```

```json
{
  "question": "Key constraints?",
  "header": "Constraints",
  "options": [
    {"label": "Existing tech stack", "description": "Must use current framework/tools"},
    {"label": "Backward compatible", "description": "Cannot break existing APIs"},
    {"label": "Performance critical", "description": "Must be fast/scalable"},
    {"label": "Security sensitive", "description": "Auth/data protection required"}
  ],
  "multiSelect": true
}
```

## Step 2: Generate PRD Structure

Write to `.deep/PRD.md`:

```markdown
# PRD: {Feature Name}

## Goal
{One sentence from user description - what and why}

## User Stories
{Inferred from feature description and user type}
- As a {user type}, I want to {action} so that {benefit}
- As a {user type}, I want to {action} so that {benefit}

## Features

### {Feature 1}
{Description}

**Acceptance Criteria:**
- [ ] {Testable criterion}
- [ ] {Testable criterion}

### {Feature 2}
{Description}

**Acceptance Criteria:**
- [ ] {Testable criterion}
- [ ] {Testable criterion}

## Technical Constraints
{From user input or inferred from codebase}
- {Constraint 1}
- {Constraint 2}

## Out of Scope
{Boundaries inferred from description}
- {What we're NOT building}
- {What's deferred to future}

## Success Metrics
{How we'll know it works}
- {Metric 1}
- {Metric 2}
```

## Step 3: User Review

Present PRD summary and ask for approval:

```
+---------------------------------------------------+
|           GENERATED PRD SUMMARY                   |
+---------------------------------------------------+

Feature: {Feature Name}
Goal: {One-liner}

User Stories: {N}
Features: {N}
Acceptance Criteria: {N total}

Estimated Tasks: ~{N} (after conversion)
Complexity: {QUICK|STANDARD|DEEP}

PRD Location: .deep/PRD.md

===================================================
```

```json
{
  "question": "How to proceed?",
  "header": "PRD Review",
  "options": [
    {"label": "Looks good, convert to tasks", "description": "Generate task queue from this PRD"},
    {"label": "Show full PRD", "description": "Let me review the details"},
    {"label": "Edit first", "description": "I want to modify the PRD"},
    {"label": "Start over", "description": "Regenerate with different inputs"}
  ],
  "multiSelect": false
}
```

## Step 4: Convert to Tasks

Once approved, automatically run Mode 2 (PRD -> tasks.md):

1. Parse the generated PRD
2. Create atomic tasks with acceptance criteria
3. Determine dependencies
4. Write to `.deep/tasks.md`
5. Output summary

---

## NOW EXECUTE

When `/deep plan` is invoked:

1. **Detect mode** - single task vs PRD conversion vs PRD generation
2. **If PRD generation mode:**
   - Gather requirements via AskUserQuestion
   - Generate PRD structure
   - Write to .deep/PRD.md
   - User review and approval
   - Run Mode 2 (PRD -> tasks) automatically
3. **If PRD conversion mode:**
   - Find/request PRD source
   - **Discover ADR constraints** (scan docs/adr/, decisions.md)
   - Parse structure (with ADR constraint matching)
   - Generate atomic tasks (embed relevant ADR constraints as acceptance criteria)
   - Determine dependencies
   - Review with user
   - Write to .deep/tasks.md
   - Output summary
4. **If single task mode:**
   - Follow original Phase 1-7 planning flow
