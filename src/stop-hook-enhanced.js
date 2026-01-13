#!/usr/bin/env node

/**
 * Deep Loop Stop Hook (Enhanced with Persistent Tasks + Git/PR Verification)
 *
 * Intercepts Claude's exit attempts and re-injects the appropriate prompt
 * based on the current phase OR pending persistent tasks.
 * Returns exit code 2 to block exit.
 *
 * Check Order:
 * 1. Force exit file? → Exit immediately
 * 2. Force complete file? → Exit (bypass verification with logged reason)
 * 4. Deep loop active and incomplete? → Block + re-inject phase prompt
 * 5. State says COMPLETE? → Verify tests passed
 * 6. State says COMPLETE? → Verify git/PR workflow complete (if applicable)
 * 7. Persistent tasks pending? → Block + re-inject task prompt
 * 8. All done → Allow exit
 *
 * Phases: PLAN → BUILD → REVIEW → FIX → COMPLETE
 *
 * Verification at COMPLETE:
 * - Test Results: All tests, types, lint, build must pass
 * - Git Results: PR created, CI passed, merged (if in git repo with gh CLI)
 *
 * Safety mechanisms:
 * - Staleness check: Auto-exit if state is older than STALE_THRESHOLD_MS
 * - Force exit: Create .deep/FORCE_EXIT to break out immediately
 * - Force complete: Create .deep/FORCE_COMPLETE to bypass verification

 * - Max iterations: Allows exit after hitting limit (warns but doesn't block)
 * - Task staleness: Skip tasks older than configured threshold
 */

import fs from 'fs';
import path from 'path';

const STATE_FILE = '.deep/state.json';
const PLAN_FILE = '.deep/plan.md';
const ISSUES_FILE = '.deep/issues.json';
const TASK_FILE = '.deep/task.md';
const FORCE_EXIT_FILE = '.deep/FORCE_EXIT';
const FORCE_COMPLETE_FILE = '.deep/FORCE_COMPLETE';
const PERSISTENT_TASKS_FILE = '.deep/persistent-tasks.json';
const TEST_RESULTS_FILE = '.deep/test-results.json';
const GIT_RESULTS_FILE = '.deep/git-results.json';

// State older than 8 hours is considered stale - allow exit
// Extended from 2hrs to support multi-hour deep loop runs
const STALE_THRESHOLD_MS = 8 * 60 * 60 * 1000;
// Default task staleness (24 hours)
const DEFAULT_TASK_STALE_HOURS = 24;

/**
 * Exit with both stdout and stderr output
 * Hook runners may check either stream for output
 */
function exitHook(code, message) {
  console.log(message);
  console.error(message);
  process.exit(code);
}

function readState() {
  try {
    if (!fs.existsSync(STATE_FILE)) {
      return null;
    }
    return JSON.parse(fs.readFileSync(STATE_FILE, 'utf8'));
  } catch (e) {
    return null;
  }
}

/**
 * Read persistent tasks file
 */
function readPersistentTasks() {
  try {
    if (!fs.existsSync(PERSISTENT_TASKS_FILE)) {
      return null;
    }
    return JSON.parse(fs.readFileSync(PERSISTENT_TASKS_FILE, 'utf8'));
  } catch (e) {
    return null;
  }
}

/**
 * Get pending (non-completed, non-blocked, non-stale) tasks
 * Optionally filter by phase
 */
function getPendingTasks(tasksData, phase = null) {
  if (!tasksData || !tasksData.tasks || !Array.isArray(tasksData.tasks)) {
    return [];
  }

  const staleHours = tasksData.config?.staleThresholdHours || DEFAULT_TASK_STALE_HOURS;
  const staleMs = staleHours * 60 * 60 * 1000;
  const now = Date.now();

  return tasksData.tasks.filter(task => {
    // Skip completed tasks
    if (task.status === 'completed') return false;

    // Skip blocked tasks
    if (task.status === 'blocked') return false;

    // Skip stale tasks
    const createdAt = new Date(task.createdAt).getTime();
    if (now - createdAt > staleMs) return false;

    // If phase filter specified, only include matching phase tasks
    if (phase && task.phase && task.phase !== phase) return false;

    return true;
  });
}

/**
 * Get tasks for a specific deep loop phase
 * Returns: { phaseTasks: [], buildTasks: [] }
 */
function getDeepLoopTasks(tasksData, currentPhase) {
  if (!tasksData || !tasksData.tasks || !Array.isArray(tasksData.tasks)) {
    return { phaseTasks: [], buildTasks: [] };
  }

  const allPending = getPendingTasks(tasksData);

  // Phase-level task (e.g., "Complete BUILD phase: execute all implementation tasks")
  const phaseTasks = allPending.filter(t =>
    t.phase === currentPhase &&
    t.content?.startsWith('Complete ')
  );

  // Individual build tasks (from plan breakdown)
  const buildTasks = allPending.filter(t =>
    t.phase === 'BUILD' &&
    !t.content?.startsWith('Complete ') &&
    t.context?.source === 'deep-loop'
  );

  return { phaseTasks, buildTasks };
}

/**
 * Update task status to in_progress
 */
function markTaskInProgress(taskId) {
  try {
    const tasksData = readPersistentTasks();
    if (!tasksData) return;

    const task = tasksData.tasks.find(t => t.id === taskId);
    if (task) {
      task.status = 'in_progress';
      task.iteration = (task.iteration || 0) + 1;
      task.lastActivity = new Date().toISOString();
      tasksData.updatedAt = new Date().toISOString();
      fs.writeFileSync(PERSISTENT_TASKS_FILE, JSON.stringify(tasksData, null, 2));
    }
  } catch (e) {
    // Ignore errors
  }
}

/**
 * Mark task as blocked
 */
function markTaskBlocked(taskId, reason) {
  try {
    const tasksData = readPersistentTasks();
    if (!tasksData) return;

    const task = tasksData.tasks.find(t => t.id === taskId);
    if (task) {
      task.status = 'blocked';
      task.blockedReason = reason;
      task.lastActivity = new Date().toISOString();
      tasksData.updatedAt = new Date().toISOString();
      fs.writeFileSync(PERSISTENT_TASKS_FILE, JSON.stringify(tasksData, null, 2));
    }
  } catch (e) {
    // Ignore errors
  }
}

/**
 * Check if state file is stale (older than threshold)
 */
function isStateStale() {
  try {
    const stats = fs.statSync(STATE_FILE);
    const ageMs = Date.now() - stats.mtimeMs;
    return ageMs > STALE_THRESHOLD_MS;
  } catch (e) {
    return true; // If we can't check, assume stale
  }
}

/**
 * Check for manual force exit file
 */
function shouldForceExit() {
  if (fs.existsSync(FORCE_EXIT_FILE)) {
    try {
      fs.unlinkSync(FORCE_EXIT_FILE);
    } catch (e) {
      // Ignore cleanup errors
    }
    return true;
  }
  return false;
}

/**
 * Check for Ralph handoff file (allows exit for external orchestration)
 * Create .deep/RALPH_HANDOFF when spawning external Ralph process
 */
function shouldRalphHandoff() {
  const RALPH_HANDOFF_FILE = '.deep/RALPH_HANDOFF';
  if (fs.existsSync(RALPH_HANDOFF_FILE)) {
    try {
      fs.unlinkSync(RALPH_HANDOFF_FILE);
    } catch (e) {
      // Ignore cleanup errors
    }
    return true;
  }
  return false;
}

/**
 * Check for force complete file (bypasses test verification)
 */
function shouldForceComplete() {
  if (fs.existsSync(FORCE_COMPLETE_FILE)) {
    try {
      const reason = fs.readFileSync(FORCE_COMPLETE_FILE, 'utf8').trim();
      console.log(`## Deep Loop - Force complete triggered. Reason: ${reason || 'Not specified'}`);
      fs.unlinkSync(FORCE_COMPLETE_FILE);
    } catch (e) {
      // Ignore errors
    }
    return true;
  }
  return false;
}

/**
 * Read test results file
 */
function readTestResults() {
  try {
    if (!fs.existsSync(TEST_RESULTS_FILE)) {
      return null;
    }
    return JSON.parse(fs.readFileSync(TEST_RESULTS_FILE, 'utf8'));
  } catch (e) {
    return null;
  }
}

/**
 * Read git results file
 */
function readGitResults() {
  try {
    if (!fs.existsSync(GIT_RESULTS_FILE)) {
      return null;
    }
    return JSON.parse(fs.readFileSync(GIT_RESULTS_FILE, 'utf8'));
  } catch (e) {
    return null;
  }
}

/**
 * Verify all tests have been run and passed
 * Returns: { valid: boolean, missing: string[], failed: string[] }
 */
function verifyTestResults() {
  const testResults = readTestResults();

  if (!testResults) {
    return {
      valid: false,
      missing: ['test-results.json file not found'],
      failed: []
    };
  }

  const missing = [];
  const failed = [];

  // Check each required test category
  const required = ['tests', 'types', 'lint', 'build'];

  for (const category of required) {
    const result = testResults.results?.[category];

    if (!result) {
      missing.push(`${category}: no results recorded`);
      continue;
    }

    if (!result.ran) {
      missing.push(`${category}: not run`);
    } else if (!result.passed) {
      failed.push(`${category}: failed`);
    }
  }

  // Check overall status
  if (!testResults.allPassed && missing.length === 0 && failed.length === 0) {
    failed.push('allPassed flag is false');
  }

  // Check for blockers
  if (testResults.blockers && testResults.blockers.length > 0) {
    for (const blocker of testResults.blockers) {
      failed.push(`blocker: ${blocker}`);
    }
  }

  return {
    valid: missing.length === 0 && failed.length === 0,
    missing,
    failed
  };
}

/**
 * Verify git workflow has been completed (PR created, CI passed, merged)
 * Returns: { valid: boolean, skip: boolean, missing: string[], failed: string[] }
 */
function verifyGitResults() {
  const gitResults = readGitResults();

  // No git results file - check if we should skip git verification
  if (!gitResults) {
    return {
      valid: true,
      skip: true,
      skipReason: 'No git-results.json file (project may not be in git repo)',
      missing: [],
      failed: []
    };
  }

  // Not a git repo - skip git checks
  if (!gitResults.repository?.isGitRepo) {
    return {
      valid: true,
      skip: true,
      skipReason: 'Not a git repository',
      missing: [],
      failed: []
    };
  }

  // No GitHub CLI - skip PR/CI checks but allow local git
  if (!gitResults.repository?.hasGhCli) {
    return {
      valid: true,
      skip: true,
      skipReason: 'GitHub CLI not available (local git only)',
      missing: [],
      failed: []
    };
  }

  const missing = [];
  const failed = [];
  const enforcement = gitResults.enforcement || {};

  // Check PR creation
  if (enforcement.requirePR !== false) {
    if (!gitResults.pr?.created) {
      missing.push('PR not created');
    }
  }

  // Check CI status
  if (enforcement.requireCIPass !== false) {
    if (!gitResults.ci?.checked) {
      missing.push('CI checks not run');
    } else if (!gitResults.ci?.passed) {
      failed.push(`CI failed (status: ${gitResults.ci?.status || 'unknown'})`);
    }
  }

  // Check merge status
  if (enforcement.requireMerge !== false) {
    if (!gitResults.merge?.merged) {
      missing.push('PR not merged to production');
    }
  }

  // Check overall allPassed flag
  if (!gitResults.allPassed && missing.length === 0 && failed.length === 0) {
    failed.push('Git workflow allPassed flag is false');
  }

  return {
    valid: missing.length === 0 && failed.length === 0,
    skip: false,
    missing,
    failed
  };
}

/**
 * Generate prompt for failed git verification
 */
function getGitVerificationFailedPrompt(verification) {
  const { missing, failed } = verification;

  let issues = '';
  if (missing.length > 0) {
    issues += `\n**Not Completed:**\n${missing.map(m => `- ${m}`).join('\n')}`;
  }
  if (failed.length > 0) {
    issues += `\n**Failed:**\n${failed.map(f => `- ${f}`).join('\n')}`;
  }

  return `
## COMPLETION BLOCKED - Git/PR Workflow Not Complete

The deep loop cannot complete because git/PR verification failed.
${issues}

### Required Actions

1. **Create PR (if not created):**
   \`\`\`bash
   git push -u origin HEAD
   gh pr create --title "[task description]" --body "[summary]"
   \`\`\`

2. **Wait for CI checks to pass:**
   \`\`\`bash
   gh pr checks --watch
   \`\`\`

3. **Merge PR to production:**
   \`\`\`bash
   gh pr merge --squash --delete-branch
   \`\`\`

4. **Update \`.deep/git-results.json\`** with the results:
   - Set \`pr.created: true\` with PR number and URL
   - Set \`ci.passed: true\` after CI passes
   - Set \`merge.merged: true\` after merge
   - Set \`allPassed: true\` when all complete

5. **Return to REVIEW phase** to complete verification

**DO NOT use FORCE_EXIT to bypass git workflow** - code should be merged before completion.

If you truly cannot create/merge PR (no remote, review required, etc.), create:
\`\`\`bash
echo "Reason: [explain why]" > .deep/FORCE_COMPLETE
\`\`\`
`;
}

/**
 * Generate prompt for failed test verification
 */
function getTestVerificationFailedPrompt(verification) {
  const { missing, failed } = verification;

  let issues = '';
  if (missing.length > 0) {
    issues += `\n**Not Run:**\n${missing.map(m => `- ${m}`).join('\n')}`;
  }
  if (failed.length > 0) {
    issues += `\n**Failed:**\n${failed.map(f => `- ${f}`).join('\n')}`;
  }

  return `
## COMPLETION BLOCKED - Tests Not Verified

The deep loop cannot complete because test verification failed.
${issues}

### Required Actions

1. **Run ALL validation commands:**
   \`\`\`bash
   npm run build
   npm test
   npm run typecheck
   npm run lint
   \`\`\`

2. **Update \`.deep/test-results.json\` with results:**
   - Set \`ran: true\` for each category
   - Set \`passed: true/false\` based on results
   - Set \`allPassed: true\` only if ALL passed
   - Clear \`blockers\` array if all issues resolved

3. **Return to REVIEW phase** to complete verification

**DO NOT use FORCE_EXIT to bypass tests** - this defeats the purpose of the deep loop.

If you truly cannot run tests (no framework, external issue), create:
\`\`\`bash
echo "Reason: [explain why]" > .deep/FORCE_COMPLETE
\`\`\`
`;
}

/**
 * Generate prompt for persistent task continuation
 */
function getTaskContinuationPrompt(pendingTasks) {
  const count = pendingTasks.length;
  const nextTask = pendingTasks.find(t => t.status === 'in_progress') || pendingTasks[0];

  const taskList = pendingTasks.slice(0, 5).map((t, i) => {
    const status = t.status === 'in_progress' ? '🔄' : '⏳';
    const priority = t.priority === 'high' ? '🔴' : t.priority === 'medium' ? '🟡' : '🟢';
    return `${i + 1}. ${status} ${priority} ${t.content}`;
  }).join('\n');

  return `
## Persistent Tasks - ${count} remaining

**Next Task:** ${nextTask.content}
**Task ID:** ${nextTask.id}
**Priority:** ${nextTask.priority || 'medium'}
**Iteration:** ${nextTask.iteration || 1}

### Pending Tasks:
${taskList}
${count > 5 ? `\n... and ${count - 5} more` : ''}

### Instructions

Continue working on the current task. When complete:

1. Read \`.deep/persistent-tasks.json\`
2. Find the task by ID: \`${nextTask.id}\`
3. Update: \`"status": "completed"\`, \`"completedAt": "${new Date().toISOString()}"\`
4. Write the updated file

If you encounter a blocking issue:
- Set \`"status": "blocked"\`
- Add \`"blockedReason": "description of why"\`

**To force exit:** Create empty file \`.deep/FORCE_EXIT\`

**Now continue with:** ${nextTask.content}
`;
}

function getPhasePrompt(state, tasksData = null) {
  const { phase, iteration, maxIterations, task } = state;
  const { phaseTasks, buildTasks } = tasksData ? getDeepLoopTasks(tasksData, phase) : { phaseTasks: [], buildTasks: [] };

  const header = `
## Deep Loop - Iteration ${iteration}/${maxIterations}
**Current Phase:** ${phase}
**Task:** ${task || 'See .deep/task.md'}
${buildTasks.length > 0 ? `**Pending BUILD Tasks:** ${buildTasks.length}` : ''}

`;

  const persistentTaskNote = `
### Persistent Task Tracking

Remember to update \`.deep/persistent-tasks.json\` as you work:
- Mark tasks \`"in_progress"\` when starting
- Mark tasks \`"completed"\` with \`"completedAt"\` when done
- This ensures the STOP hook tracks progress correctly
`;

  switch (phase) {
    case 'PLAN':
      return header + `
### PLAN Phase Instructions

Create a detailed plan in \`.deep/plan.md\` with:
1. **Problem Statement** - What exactly are we solving?
2. **Acceptance Criteria** - Testable success conditions
3. **Task Breakdown** - Ordered list of atomic tasks
4. **Risk Assessment** - What could go wrong?

When plan is complete:
- Validate it has all required sections
- **Generate persistent tasks from plan breakdown** (add to \`.deep/persistent-tasks.json\`)
- Update \`.deep/state.json\` with \`"phase": "BUILD"\`
- **Proceed immediately** - no user approval needed (autonomous mode)

Read the task from \`.deep/task.md\` to understand what to plan.
${persistentTaskNote}`;

    case 'BUILD':
      const buildTaskList = buildTasks.slice(0, 5).map((t, i) => {
        const status = t.status === 'in_progress' ? '🔄' : '⏳';
        return `${i + 1}. ${status} ${t.content}`;
      }).join('\n');

      return header + `
### BUILD Phase Instructions

${buildTasks.length > 0 ? `**Pending Tasks from Plan:**\n${buildTaskList}${buildTasks.length > 5 ? `\n... and ${buildTasks.length - 5} more` : ''}\n\n` : ''}

Execute the plan from \`.deep/plan.md\`:
1. Work through tasks in order
2. **Update persistent tasks as you go:**
   - Mark current task \`"in_progress"\` in \`.deep/persistent-tasks.json\`
   - After completion, set \`"completed"\` with \`"completedAt"\`
3. After each task:
   - Run tests: \`npm test\` or appropriate command
   - Check types: \`npm run typecheck\` or \`tsc --noEmit\`
   - Check lint: \`npm run lint\`
4. Log progress to \`.deep/state.json\` history
5. On failure (max 3 retries per task):
   - Log error to \`.deep/issues.json\`
   - Attempt to fix
   - If stuck after 3 attempts, document and continue

When all tasks complete with passing validation:
- **Mark BUILD phase task as completed** in persistent-tasks.json
- Update \`.deep/state.json\` with \`"phase": "REVIEW"\`

Read the plan from \`.deep/plan.md\` and check progress in \`.deep/state.json\`.
`;

    case 'REVIEW':
      return header + `
### REVIEW Phase Instructions

**First:** Mark REVIEW phase task as \`"in_progress"\` in \`.deep/persistent-tasks.json\`

Run comprehensive review:
1. **Code Review** - Use \`code-review\` skill patterns
2. **Security Audit** - Use \`security-audit\` skill patterns
3. **Frontend Tests** - If frontend code, run \`deep-frontend-test\` checks
4. **Backend Tests** - If backend code, run \`deep-backend-test\` checks
5. **Coverage Check** - Ensure test coverage meets threshold

For each issue found:
- Add to \`.deep/issues.json\` with severity and location
- Document in \`.deep/review.md\`

If issues found:
- Keep REVIEW task as \`"in_progress"\`
- Update \`.deep/state.json\` with \`"phase": "FIX"\`

If NO issues found:
- **Mark REVIEW phase task as completed** in persistent-tasks.json
- **Mark all remaining phase tasks as completed**
- Update \`.deep/state.json\` with \`"phase": "COMPLETE"\`, \`"complete": true\`
- Output: \`<promise>COMPLETE</promise>\`
`;

    case 'FIX':
      return header + `
### FIX Phase Instructions

**First:** Mark FIX phase task as \`"in_progress"\` in \`.deep/persistent-tasks.json\`

Address issues from \`.deep/issues.json\`:
1. Read each issue
2. Apply fix with atomic commit
3. Mark issue as resolved in \`.deep/issues.json\`
4. Run validation (tests, types, lint)

When all issues addressed:
- Clear \`.deep/issues.json\` (set to empty array)
- **Mark FIX phase task as completed** in persistent-tasks.json
- Update \`.deep/state.json\` with \`"phase": "REVIEW"\`

This returns to REVIEW to verify fixes didn't introduce new issues.

Read issues from \`.deep/issues.json\`.
`;

    case 'COMPLETE':
      return null; // Allow exit

    default:
      return null;
  }
}

function main() {
  // SAFETY: Manual escape hatch - create .deep/FORCE_EXIT to break out
  if (shouldForceExit()) {
    console.log('## Deep Loop - Force exit triggered. Exiting gracefully.');
    process.exit(0);
  }

  // SAFETY: Force complete - bypasses test verification with explicit reason
  if (shouldForceComplete()) {
    process.exit(0);
  }

  // SAFETY: Ralph handoff - allows exit for external orchestration
  if (shouldRalphHandoff()) {
    console.log('## Deep Loop - Ralph mode handoff. Exiting for external orchestration.');
    process.exit(0);
  }

  // CHECK 1: Deep loop state
  const state = readState();
  const tasksData = readPersistentTasks();
  let deepLoopActive = false;

  if (state && state.complete !== true && state.phase !== 'COMPLETE') {
    // SAFETY: Stale state check - if state is old, skip to persistent tasks
    if (isStateStale()) {
      console.log(`## Deep Loop - Stale state detected (>2 hours old). Checking persistent tasks...`);
    } else if (state.iteration >= state.maxIterations) {
      // SAFETY: Max iterations - warn but check persistent tasks
      console.log(`## Deep Loop - MAX ITERATIONS REACHED (${state.maxIterations}). Checking persistent tasks...`);
    } else {
      // Active deep loop - block exit
      deepLoopActive = true;
      state.iteration = (state.iteration || 0) + 1;
      state.lastActivity = new Date().toISOString();
      fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));

      // Pass tasksData to show pending build tasks in prompt
      const prompt = getPhasePrompt(state, tasksData);
      if (prompt) {
        console.log(prompt);
        console.error("[BLOCKED] Deep Loop phase: " + state.phase);
        process.exit(2);
      }
    }
  }

  // CHECK 1.5: If state says COMPLETE, verify tests actually passed
  if (state && (state.complete === true || state.phase === 'COMPLETE')) {
    const testVerification = verifyTestResults();

    if (!testVerification.valid) {
      // Tests not verified - block completion
      console.log(getTestVerificationFailedPrompt(testVerification));
      console.error("[BLOCKED] Test verification failed");

      // Reset state back to REVIEW
      state.phase = 'REVIEW';
      state.complete = false;
      state.iteration = (state.iteration || 0) + 1;
      state.lastActivity = new Date().toISOString();
      fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));

      process.exit(2);
    }

    // CHECK 1.6: Verify git/PR workflow completed (if applicable)
    const gitVerification = verifyGitResults();

    if (!gitVerification.skip && !gitVerification.valid) {
      // Git/PR workflow not complete - block completion
      console.log(getGitVerificationFailedPrompt(gitVerification));
      console.error("[BLOCKED] Git/PR verification failed");

      // Reset state back to REVIEW
      state.phase = 'REVIEW';
      state.complete = false;
      state.iteration = (state.iteration || 0) + 1;
      state.lastActivity = new Date().toISOString();
      fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));

      process.exit(2);
    }

    // Log if git verification was skipped
    if (gitVerification.skip) {
      console.log(`## Deep Loop - Git verification skipped: ${gitVerification.skipReason}`);
    }

    // All verification passed - allow exit (will continue to CHECK 3)
  }

  // CHECK 2: Persistent tasks (only if deep loop not active)
  if (!deepLoopActive) {
    // Reuse tasksData from above if already read, otherwise read it now
    const currentTasksData = tasksData || readPersistentTasks();
    const pendingTasks = getPendingTasks(currentTasksData);

    if (pendingTasks.length > 0) {
      // Check max iterations per task
      const currentTask = pendingTasks.find(t => t.status === 'in_progress') || pendingTasks[0];
      const maxIter = currentTasksData.config?.maxIterationsPerTask || 5;

      if ((currentTask.iteration || 0) >= maxIter) {
        console.log(`
## Persistent Tasks - Task iteration limit reached

Task "${currentTask.content}" has hit max iterations (${maxIter}).

Marking as blocked. Checking for remaining tasks...
`);
        // Mark as blocked
        markTaskBlocked(currentTask.id, 'Max iterations reached');

        // Re-check for remaining non-blocked tasks
        const remainingTasks = getPendingTasks(readPersistentTasks());
        if (remainingTasks.length > 0) {
          markTaskInProgress(remainingTasks[0].id);
          console.log(getTaskContinuationPrompt(remainingTasks));
          console.error("[BLOCKED] " + remainingTasks.length + " persistent tasks remaining");
          process.exit(2);
        }
      } else {
        // Block exit and continue with tasks
        markTaskInProgress(currentTask.id);
        console.log(getTaskContinuationPrompt(pendingTasks));
        console.error("[BLOCKED] " + pendingTasks.length + " persistent tasks remaining");
        process.exit(2);
      }
    }
  }

  // CHECK 3: Post-completion cleanup
  if (state && state.complete === true && state.phase === 'COMPLETE') {
    cleanupDeepDirectory();
  }

  // All done - allow exit
  const msg = '[OK] Deep Loop stop hook: No active loop or pending tasks. Exit allowed.';
  console.log(msg);
  console.error(msg);  // Also write to stderr for hook systems that expect it
  process.exit(0);
}



/**
 * Clean up .deep/ directory after successful completion
 * Only runs when state.complete === true and state.phase === 'COMPLETE'
 * Preserves .deep/ if FORCE_COMPLETE was used (for audit trail)
 */
function cleanupDeepDirectory() {
  try {
    // Check if FORCE_COMPLETE was used - preserve for audit
    if (fs.existsSync(FORCE_COMPLETE_FILE)) {
      console.log('## Deep Loop - Skipping cleanup (FORCE_COMPLETE detected - preserving for audit)');
      return;
    }

    // Check test results - only cleanup if truly complete
    const testResults = readTestResults();
    if (testResults && !testResults.allPassed) {
      console.log('## Deep Loop - Skipping cleanup (tests not all passed)');
      return;
    }

    // Check if .deep directory exists
    const deepDir = path.dirname(STATE_FILE);
    if (!fs.existsSync(deepDir)) {
      return;
    }

    // Remove the .deep directory
    fs.rmSync(deepDir, { recursive: true, force: true });
    console.log('## Deep Loop - Cleaned up .deep/ directory');
  } catch (e) {
    // Ignore cleanup errors - non-critical
  }
}

main();
