# Deep Loop Status - Rich Display

Display comprehensive deep loop session status with progress metrics.

## Version Header

ALWAYS output version first:
```
╔═══════════════════════════════════════╗
║  DEEP LOOP v7.2.1                     ║
║  Senior Dev Mode: ✓ enabled           ║
║  External Loop: ✓ supported           ║
║  Task Sync: {✓ enabled | ○ disabled}  ║
╚═══════════════════════════════════════╝
```

Check `DEEP_LOOP_TASKS_ENABLED` env var for Task Sync status.

## Actions

### 1. Detect Session Directory

```bash
# Find active .deep-* directories
for d in .deep-*/; do
  if [ -f "$d/state.json" ]; then
    echo "Found: $d"
  fi
done 2>/dev/null

# Fallback to legacy .deep
if [ -f .deep/state.json ]; then
  echo "Found: .deep/"
fi
```

### 2. Read State and Display Rich Status

For each session found, read state and build display:

```
echo ""
echo "  =============================================="
echo "  ||         DEEP LOOP STATUS                ||"
echo "  =============================================="
echo ""
```

**Session Info Block:**
```
  Session: {session8}
  Complexity: {complexity} (quick|standard|deep)
  Loop Mode: {mode} (internal|external)
  Started: {startedAt}
  Last Activity: {lastActivity}
```

**Loop Mode Values:**
- `internal` - Stop hook controls iteration (default for QUICK)
- `external` - Bash script controls iteration (default for STANDARD/DEEP)

**Phase Progress Block:**
```
  ┌─────────────────────────────────────────────────┐
  │ Phase: BUILD                      [===>    ] 3/10 │
  │                                                   │
  │ Step: Implementing                                │
  │ Current Task: task-003 "Add validation logic"     │
  └─────────────────────────────────────────────────┘
```

**Progress Bar Calculation:**
```javascript
const progress = iteration / maxIterations;
const filled = Math.floor(progress * 10);
const bar = '='.repeat(filled) + '>' + ' '.repeat(10 - filled - 1);
```

**Counters Block:**
```
  Completed: 5   Failed: 1   Skipped: 0   Remaining: 4
       ✓ 5        ✗ 1        ⊘ 0          ⋯ 4
```

### 3. Control Flags Check

```bash
# Check for control files
ls -la .deep-*/FORCE_EXIT .deep-*/FORCE_COMPLETE .deep-*/NEEDS_USER 2>/dev/null
```

**Display:**
```
  Control Flags:
  - FORCE_EXIT: no
  - FORCE_COMPLETE: no
  - NEEDS_USER: no
```

### 4. Task Queue Summary (if tasks.md exists)

```bash
PENDING=$(grep -c "^## \[ \] task-" .deep/tasks.md 2>/dev/null || echo "0")
DONE=$(grep -c "^## \[x\] task-" .deep/completed-tasks.md 2>/dev/null || echo "0")
```

**Display:**
```
  ┌─────────────────────────────────────────────────┐
  │ Task Queue                                       │
  ├─────────────────────────────────────────────────┤
  │ Pending: 8                                       │
  │ Completed: 5                                     │
  │                                                  │
  │ Next up:                                         │
  │   task-006: Add error handling to API           │
  │   task-007: Write tests for new endpoint        │
  └─────────────────────────────────────────────────┘
```

### 4b. Task Management View (if DEEP_LOOP_TASKS_ENABLED=true)

**If Task Sync enabled, also run:**
```
TaskList()
```

Filter results by `metadata.type === 'deep-loop' || metadata.type === 'deep-loop-atomic'`
Further filter by `metadata.sessionId === '{current_session}'` if session-specific.

**Display:**
```
  ┌─────────────────────────────────────────────────┐
  │ Task Management View (Sync Layer)                │
  ├─────────────────────────────────────────────────┤
  │ Parent: [DEEP] Implement auth feature            │
  │   Status: in_progress  Phase: BUILD             │
  │                                                  │
  │ Atomic Tasks:                                    │
  │   ✓ task-001: Add login endpoint     [abc123]   │
  │   ✓ task-002: Add JWT middleware     [def456]   │
  │   ⟳ task-003: Add session store      (blocked)  │
  │   ○ task-004: Write integration tests           │
  └─────────────────────────────────────────────────┘

Legend: ✓ completed  ⟳ in_progress  ○ pending  (blocked) = has blockedBy
```

**If Task Sync disabled:**
```
  Task Sync: ○ disabled
  Set DEEP_LOOP_TASKS_ENABLED=true to enable crash recovery + visibility
```

### 5. Recent Activity Log

Show last 3 state changes from git log or file timestamps:

```
  Recent Activity:
  - 10:45 BUILD: Implementing task-003
  - 10:42 BUILD: Committed task-002
  - 10:35 PLAN: Plan approved
```

### 6. No Active Session Display

If no state.json found:

```
  ============================================
  ||         NO ACTIVE DEEP SESSION         ||
  ============================================

  Start a new session:
  - /deep <task>        Full deep loop
  - /deep quick <task>  Quick mode (3 iterations)

  Resume from queue:
  - /deep execute       Process task queue
```

---

## Output Format Templates

### Quick Mode Status

```
  ============================================
  ||         QUICK MODE STATUS              ||
  ============================================

  Session: 8405b17e
  Task: Fix typo in README.md
  Iteration: 1/3

  Status: Executing...
```

### Standard/Deep Mode Status

```
  ============================================
  ||         DEEP LOOP STATUS               ||
  ============================================

  Session: 8405b17e           Complexity: STANDARD
  Loop Mode: EXTERNAL         Iterations: 3/10
  Started: 2025-01-22 10:00

  ┌────────────────────────────────────────┐
  │ BUILD [=====....] 50%                  │
  │                                        │
  │ Current Step: Testing                  │
  │ Current Task: Implement user auth      │
  └────────────────────────────────────────┘

  Progress:
    ✓ Completed: 2
    ✗ Failed: 0
    ⋯ Remaining: 3

  Control Flags: (none active)
```

### Stale Session Warning

If last activity > 1 hour ago:

```
  ⚠️  SESSION STALE
  Last activity: 3 hours ago

  Options:
  - Continue: /deep (will resume)
  - Cancel: /cancel-deep
  - Force complete: touch .deep-{session8}/FORCE_COMPLETE
```

---

## Step Detection (for current_step)

Update state.json `current_step` based on recent tool calls:

| Pattern Detected | Current Step |
|-----------------|--------------|
| `git commit`, `git add` | Committing |
| Write/Edit to test files | Writing tests |
| `npm test`, `vitest`, `pytest` | Testing |
| `npm run lint`, `eslint` | Linting |
| `tsc`, `typecheck` | Type checking |
| Write/Edit to source files | Implementing |
| Read/Glob/Grep | Exploring |
| Task tool (subagent) | Running subagent |

---

## NOW EXECUTE

1. Find all `.deep-*` session directories
2. Read `state.json` from each
3. Build rich status display with ASCII boxes
4. Show progress metrics and current step
5. Display task queue summary if applicable
6. Output formatted status to user
