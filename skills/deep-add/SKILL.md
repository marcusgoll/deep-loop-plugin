---
name: deep-add
description: Add tasks to the shared deep loop task queue. Use when user wants to add tasks for later execution by /deep execute.
version: 9.0.0
---

# Deep Add - Interactive Task Queue Management

Add tasks to `.deep/tasks.md` for later execution by multiple Claude sessions.

## Task Format

Tasks are stored in `.deep/tasks.md`:

```markdown
# Task Queue

## [ ] task-001: Short title
**Priority:** high | medium | low
**Added:** YYYY-MM-DD by session-XXXXXXXX
**Attempts:** 0

Description of what needs to be done.

- [ ] Acceptance criterion 1
- [ ] Acceptance criterion 2

---
```

## Execution Flow

### Step 1: Initialize

```bash
# Ensure .deep directory exists
mkdir -p .deep

# Check for existing tasks.md
if [ -f .deep/tasks.md ]; then
  cat .deep/tasks.md
else
  echo "No existing tasks.md"
fi
```

### Step 2: Get Next Task ID

Count existing tasks to generate unique ID:

```bash
# Count task headers
grep -c "^## \[ \] task-" .deep/tasks.md 2>/dev/null || echo "0"
```

Format: `task-XXX` where XXX is zero-padded (001, 002, etc.)

### Step 3: Gather Task Details via AskUserQuestion

Use AskUserQuestion to interactively gather:

**Question 1: Task Title**
```
What task do you want to add to the queue?
```
- Free text response expected

**Question 2: Acceptance Criteria**
```
What are the acceptance criteria? (one per line)
```
- Free text response expected

**Question 3: Priority**
```json
{
  "question": "What priority level?",
  "header": "Priority",
  "options": [
    {"label": "High", "description": "Critical path, do first"},
    {"label": "Medium (Recommended)", "description": "Normal priority"},
    {"label": "Low", "description": "Nice to have, do last"}
  ],
  "multiSelect": false
}
```

### Step 4: Format and Append

Get session ID from transcript path (first 8 chars of UUID) or generate random.

Format the task:

```markdown
## [ ] task-XXX: {title}
**Priority:** {priority}
**Added:** {YYYY-MM-DD} by session-{session8}
**Attempts:** 0

{description from title/context}

- [ ] {criterion 1}
- [ ] {criterion 2}

---
```

Append to `.deep/tasks.md` (create file with header if missing).

### Step 5: Confirm and Loop

After adding:
1. Show confirmation: "Added task-XXX: {title}"
2. Ask: "Add another task?"

If yes, loop back to Step 3.
If no, show summary of task queue.

## File Structure

```
.deep/
├── tasks.md              # Shared task queue
├── completed-tasks.md    # Done tasks with evidence
├── claims.json           # Lock file for multi-session
└── {session8}/           # Session-specific state (existing)
```

## Creating tasks.md

If `.deep/tasks.md` doesn't exist, create with header:

```markdown
# Task Queue

Tasks for `/deep execute` to process. Add tasks with `/deep add`.

---

```

## Example Session

```
User: /deep add

Claude: [Uses AskUserQuestion]
  "What task do you want to add?"

User: Add email validation to signup form

Claude: [Uses AskUserQuestion]
  "What are the acceptance criteria?"

User:
- Email format validates correctly
- Shows inline error message
- Blocks form submission if invalid

Claude: [Uses AskUserQuestion with priority options]

User: Medium

Claude: Added task-003: Add email validation to signup form
  Priority: medium
  Criteria: 3

Add another task? [Uses AskUserQuestion: Yes/No]

User: No

Claude: Task queue summary:
  - task-001: [high] User authentication
  - task-002: [low] Update README
  - task-003: [medium] Add email validation to signup form
```

## NOW EXECUTE

When invoked:
1. Initialize .deep directory
2. Count existing tasks for next ID
3. Use AskUserQuestion to gather task details
4. Append formatted task to tasks.md
5. Ask if user wants to add more
6. Show summary when done
