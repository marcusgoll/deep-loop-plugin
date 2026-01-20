#!/usr/bin/env node

/**
 * Deep Loop Stop Hook v2.1 - Complete Edge Case Coverage
 *
 * Handles edge cases:
 * 1. Infinite loop prevention - Hard iteration limit with blocking
 * 2. Staleness detection - 8hr threshold, auto-cleanup
 * 3. Incomplete work on exit - Test + Git verification
 * 4. Lost context recovery - Persistent tasks with resume context
 * 5. Over-engineering prevention - Triggers code-simplifier reminder
 * 6. Clear definition of done - Completion checklist
 * 7. Git chaos prevention - Atomic commit + PR verification
 * 8. Parallel task coordination - Lock file mechanism
 * 9. Verification blindness fix - E2E verification reminder
 * 10. Stuck approach detection - User escalation after N failures
 * 11. RLM cost tracking - Sub-call limits
 * 12. Active CI polling - Polls CI status for 10 min, blocks on failure
 * 13. Completion summary - Session stats on exit
 */

import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';

// File paths
const STATE_FILE = '.deep/state.json';
const SUMMARY_FILE = '.deep/summary.json';
const PLAN_FILE = '.deep/plan.md';
const ISSUES_FILE = '.deep/issues.json';
const TASK_FILE = '.deep/task.md';
const FORCE_EXIT_FILE = '.deep/FORCE_EXIT';
const FORCE_COMPLETE_FILE = '.deep/FORCE_COMPLETE';
const PERSISTENT_TASKS_FILE = '.deep/persistent-tasks.json';
const TEST_RESULTS_FILE = '.deep/test-results.json';
const GIT_RESULTS_FILE = '.deep/git-results.json';
const LOCK_FILE = '.deep/agent.lock';
const FAILURE_FILE = '.deep/failures.json';
const ESCALATION_FILE = '.deep/NEEDS_USER';
const RALPH_HANDOFF_FILE = '.deep/RALPH_HANDOFF';
const RLM_CONTEXT_FILE = '.deep/rlm-context.json';
const RLM_COSTS_FILE = '.deep/rlm-costs.json';

// Configuration
const STALE_THRESHOLD_MS = 8 * 60 * 60 * 1000; // 8 hours
const DEFAULT_TASK_STALE_HOURS = 24;
const MAX_CONSECUTIVE_FAILURES = 3;
const LOCK_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes
const RLM_SUB_CALL_WARNING = 30;
const RLM_SUB_CALL_LIMIT = 50;
const CI_POLL_INTERVAL_MS = 15 * 1000; // 15 seconds
const CI_MAX_WAIT_MS = 10 * 60 * 1000; // 10 minutes

// ============================================================================
// Edge Case 1: Infinite Loop Prevention
// ============================================================================

function checkIterationLimit(state) {
  if (!state || !state.maxIterations) return { blocked: false };

  const iteration = state.iteration || 0;
  const max = state.maxIterations;

  if (iteration >= max) {
    return {
      blocked: true,
      message: `
## ITERATION LIMIT REACHED (${iteration}/${max})

The deep loop has hit its maximum iteration limit. This prevents infinite loops.

### Options:

1. **Force exit** (abandon work):
   \`\`\`bash
   touch .deep/FORCE_EXIT
   \`\`\`

2. **Force complete** (mark as done despite limit):
   \`\`\`bash
   echo "Reached iteration limit, work is acceptable" > .deep/FORCE_COMPLETE
   \`\`\`

3. **Increase limit** (if more iterations needed):
   Edit \`.deep/state.json\` and increase \`maxIterations\`

4. **Review progress** and decide if task is actually complete
`
    };
  }

  return { blocked: false };
}

// ============================================================================
// Edge Case 2: Staleness Detection
// ============================================================================

function isStateStale() {
  try {
    const stats = fs.statSync(STATE_FILE);
    return Date.now() - stats.mtimeMs > STALE_THRESHOLD_MS;
  } catch {
    return true;
  }
}

// ============================================================================
// Edge Case 3: Incomplete Work on Exit
// ============================================================================

function verifyTestResults() {
  try {
    if (!fs.existsSync(TEST_RESULTS_FILE)) {
      return { valid: false, missing: ['test-results.json not found'], failed: [] };
    }

    const results = JSON.parse(fs.readFileSync(TEST_RESULTS_FILE, 'utf8'));
    const missing = [];
    const failed = [];

    for (const cat of ['tests', 'types', 'lint', 'build']) {
      const r = results.results?.[cat];
      if (!r) missing.push(`${cat}: no results`);
      else if (!r.ran) missing.push(`${cat}: not run`);
      else if (!r.passed) failed.push(`${cat}: failed`);
    }

    if (!results.allPassed && !missing.length && !failed.length) {
      failed.push('allPassed is false');
    }

    return { valid: !missing.length && !failed.length, missing, failed };
  } catch {
    return { valid: false, missing: ['Cannot read test results'], failed: [] };
  }
}

function verifyGitResults() {
  try {
    if (!fs.existsSync(GIT_RESULTS_FILE)) {
      return { valid: true, skip: true, skipReason: 'No git-results.json' };
    }

    const results = JSON.parse(fs.readFileSync(GIT_RESULTS_FILE, 'utf8'));

    if (!results.repository?.isGitRepo) {
      return { valid: true, skip: true, skipReason: 'Not a git repo' };
    }

    if (!results.repository?.hasGhCli) {
      return { valid: true, skip: true, skipReason: 'No gh CLI' };
    }

    const missing = [];
    const failed = [];
    const enforce = results.enforcement || {};

    if (enforce.requirePR !== false && !results.pr?.created) {
      missing.push('PR not created');
    }

    if (enforce.requireCIPass !== false) {
      if (!results.ci?.checked) missing.push('CI not checked');
      else if (!results.ci?.passed) failed.push('CI failed');
    }

    if (enforce.requireMerge !== false && !results.merge?.merged) {
      missing.push('PR not merged');
    }

    return { valid: !missing.length && !failed.length, skip: false, missing, failed };
  } catch {
    return { valid: true, skip: true, skipReason: 'Cannot read git results' };
  }
}

// ============================================================================
// Edge Case 4: Lost Context Recovery
// ============================================================================

function readPersistentTasks() {
  try {
    if (!fs.existsSync(PERSISTENT_TASKS_FILE)) return null;
    return JSON.parse(fs.readFileSync(PERSISTENT_TASKS_FILE, 'utf8'));
  } catch {
    return null;
  }
}

function getPendingTasks(tasksData) {
  if (!tasksData?.tasks?.length) return [];

  const staleMs = (tasksData.config?.staleThresholdHours || DEFAULT_TASK_STALE_HOURS) * 60 * 60 * 1000;
  const now = Date.now();

  return tasksData.tasks.filter(t => {
    if (t.status === 'completed' || t.status === 'blocked') return false;
    const created = new Date(t.createdAt).getTime();
    return now - created <= staleMs;
  });
}

// ============================================================================
// Edge Case 5: Over-engineering Prevention
// ============================================================================

function getSimplificationReminder(phase) {
  if (phase !== 'BUILD') return '';

  return `
### Code Simplification Reminder

After completing BUILD, consider running the code-simplifier:
- Remove unused imports
- Flatten unnecessary nesting
- Delete dead code
- Avoid over-abstraction
`;
}

// ============================================================================
// Edge Case 6: Clear Definition of Done
// ============================================================================

function getCompletionChecklist() {
  return `
### Completion Checklist

Before marking COMPLETE, verify:

- [ ] All acceptance criteria from plan.md are met
- [ ] All tests pass (\`npm test\`)
- [ ] No type errors (\`npm run typecheck\`)
- [ ] No lint errors (\`npm run lint\`)
- [ ] Build succeeds (\`npm run build\`)
- [ ] PR created and merged (if git repo)
- [ ] No blocking issues in issues.json

Only output \`<promise>COMPLETE</promise>\` when ALL items are checked.
`;
}

// ============================================================================
// Edge Case 7: Git Chaos Prevention
// ============================================================================

function getAtomicCommitReminder() {
  return `
### Atomic Commit Protocol

For each task completion:
1. Stage ONLY files for this task
2. Write descriptive commit message
3. Format: \`deep: [task-id] - [brief description]\`

Example:
\`\`\`bash
git add src/specific-file.ts
git commit -m "deep: task-001 - add user validation"
\`\`\`

Do NOT bundle unrelated changes in one commit.
`;
}

// ============================================================================
// Edge Case 8: Parallel Task Coordination
// ============================================================================

function acquireLock() {
  try {
    if (fs.existsSync(LOCK_FILE)) {
      const lock = JSON.parse(fs.readFileSync(LOCK_FILE, 'utf8'));
      const age = Date.now() - new Date(lock.acquiredAt).getTime();

      if (age < LOCK_TIMEOUT_MS) {
        return { acquired: false, holder: lock.agentId, age };
      }
      // Lock is stale, can acquire
    }

    const lockData = {
      agentId: process.pid.toString(),
      acquiredAt: new Date().toISOString()
    };

    fs.writeFileSync(LOCK_FILE, JSON.stringify(lockData, null, 2));
    return { acquired: true };
  } catch {
    return { acquired: true }; // Fail open
  }
}

function releaseLock() {
  try {
    if (fs.existsSync(LOCK_FILE)) {
      const lock = JSON.parse(fs.readFileSync(LOCK_FILE, 'utf8'));
      if (lock.agentId === process.pid.toString()) {
        fs.unlinkSync(LOCK_FILE);
      }
    }
  } catch {
    // Ignore
  }
}

// ============================================================================
// Edge Case 9: Verification Blindness Fix
// ============================================================================

function getVerificationReminder(state) {
  if (state?.phase !== 'REVIEW') return '';

  return `
### E2E Verification Required

Before completing REVIEW:

1. **If web app**: Use browser tools to test actual UI
   - Take screenshots
   - Click through flows
   - Check for console errors

2. **If API**: Make real HTTP requests
   - Test happy path
   - Test error cases
   - Verify response structure

3. **If CLI**: Run with sample inputs
   - Check output format
   - Test edge cases
   - Verify exit codes

Do NOT rely only on unit tests - verify real behavior.
`;
}

// ============================================================================
// Edge Case 10: Stuck Approach Detection
// ============================================================================

function trackFailure(taskId, error) {
  try {
    let failures = {};
    if (fs.existsSync(FAILURE_FILE)) {
      failures = JSON.parse(fs.readFileSync(FAILURE_FILE, 'utf8'));
    }

    if (!failures[taskId]) {
      failures[taskId] = { count: 0, errors: [] };
    }

    failures[taskId].count++;
    failures[taskId].errors.push({
      error,
      timestamp: new Date().toISOString()
    });
    failures[taskId].lastFailure = new Date().toISOString();

    fs.writeFileSync(FAILURE_FILE, JSON.stringify(failures, null, 2));

    return failures[taskId].count;
  } catch {
    return 0;
  }
}

function checkUserEscalation(taskId) {
  try {
    if (!fs.existsSync(FAILURE_FILE)) return { escalate: false };

    const failures = JSON.parse(fs.readFileSync(FAILURE_FILE, 'utf8'));
    const taskFailures = failures[taskId];

    if (taskFailures && taskFailures.count >= MAX_CONSECUTIVE_FAILURES) {
      // Create escalation file
      const escalation = {
        taskId,
        failures: taskFailures.count,
        errors: taskFailures.errors.slice(-3),
        createdAt: new Date().toISOString(),
        message: 'Task has failed multiple times. User intervention recommended.'
      };

      fs.writeFileSync(ESCALATION_FILE, JSON.stringify(escalation, null, 2));

      return {
        escalate: true,
        message: `
## USER ESCALATION REQUIRED

Task \`${taskId}\` has failed ${taskFailures.count} consecutive times.

### Recent Errors:
${taskFailures.errors.slice(-3).map(e => `- ${e.error}`).join('\n')}

### Options:

1. **Provide guidance** in the chat
2. **Skip this task**:
   Update \`.deep/persistent-tasks.json\`:
   \`"status": "blocked", "blockedReason": "User skipped"\`
3. **Abandon the loop**:
   \`touch .deep/FORCE_EXIT\`

The loop is BLOCKED until you respond.
`
      };
    }

    return { escalate: false };
  } catch {
    return { escalate: false };
  }
}

// ============================================================================
// Edge Case 11: RLM Cost Tracking
// ============================================================================

function checkRlmCosts() {
  try {
    if (!fs.existsSync(RLM_CONTEXT_FILE)) {
      return { ok: true };
    }

    const context = JSON.parse(fs.readFileSync(RLM_CONTEXT_FILE, 'utf8'));
    const subCalls = context.sub_calls || 0;

    // Track cumulative costs
    let costs = { total_sub_calls: 0, sessions: [] };
    if (fs.existsSync(RLM_COSTS_FILE)) {
      costs = JSON.parse(fs.readFileSync(RLM_COSTS_FILE, 'utf8'));
    }

    // Update costs
    costs.total_sub_calls = (costs.total_sub_calls || 0) + subCalls;
    costs.last_updated = new Date().toISOString();
    if (!costs.sessions) costs.sessions = [];
    costs.sessions.push({
      timestamp: new Date().toISOString(),
      sub_calls: subCalls,
      cost_estimate: context.cost_estimate || 'unknown'
    });

    // Keep only last 10 sessions
    if (costs.sessions.length > 10) {
      costs.sessions = costs.sessions.slice(-10);
    }

    fs.writeFileSync(RLM_COSTS_FILE, JSON.stringify(costs, null, 2));

    // Check limits
    if (subCalls >= RLM_SUB_CALL_LIMIT) {
      return {
        ok: false,
        blocked: true,
        message: `
## RLM COST LIMIT REACHED

Sub-LM calls: ${subCalls}/${RLM_SUB_CALL_LIMIT}

The RLM operation has hit the maximum sub-call limit.
This prevents runaway costs.

### Options:

1. **Continue anyway** (acknowledge cost):
   \`\`\`bash
   echo "Acknowledged: RLM costs accepted" >> .deep/rlm-context.json
   \`\`\`

2. **Abort RLM operation**:
   Delete \`.deep/rlm-context.json\` and use standard exploration

3. **Review costs**:
   See \`.deep/rlm-costs.json\` for cumulative tracking
`
      };
    }

    if (subCalls >= RLM_SUB_CALL_WARNING) {
      return {
        ok: true,
        warning: `
### RLM Cost Warning

Sub-LM calls: ${subCalls}/${RLM_SUB_CALL_LIMIT}

Approaching cost limit. Consider:
- Reducing chunk granularity
- Using more targeted filtering
- Stopping exploration early if sufficient data gathered
`
      };
    }

    return { ok: true };
  } catch {
    return { ok: true }; // Fail open
  }
}

function getRlmStatusSummary() {
  try {
    if (!fs.existsSync(RLM_CONTEXT_FILE)) {
      return '';
    }

    const context = JSON.parse(fs.readFileSync(RLM_CONTEXT_FILE, 'utf8'));

    const processedChunks = (context.chunks || []).filter(c => c.processed).length;
    const totalChunks = (context.chunks || []).length;

    return `
### RLM Status
- Chunks: ${processedChunks}/${totalChunks} processed
- Sub-calls: ${context.sub_calls || 0}
- Cost estimate: ${context.cost_estimate || 'unknown'}
`;
  } catch {
    return '';
  }
}

// ============================================================================
// Edge Case 12: CI Verification (Active Polling)
// ============================================================================

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function detectPRNumber() {
  try {
    // Try to get current PR number from gh CLI
    const result = execSync('gh pr view --json number -q .number 2>/dev/null', {
      encoding: 'utf8',
      timeout: 10000
    }).trim();
    return result ? parseInt(result, 10) : null;
  } catch {
    return null;
  }
}

async function waitForCI(prNumber) {
  const startTime = Date.now();
  let lastStatus = '';

  while (Date.now() - startTime < CI_MAX_WAIT_MS) {
    try {
      const result = execSync(`gh pr checks ${prNumber} --json name,state,conclusion 2>/dev/null`, {
        encoding: 'utf8',
        timeout: 15000
      });
      const checks = JSON.parse(result);

      if (!checks || checks.length === 0) {
        // No CI configured or checks haven't started
        return { passed: true, noCi: true };
      }

      const pending = checks.filter(c => c.state === 'PENDING' || c.state === 'IN_PROGRESS' || c.state === 'QUEUED');
      const failed = checks.filter(c => c.conclusion === 'FAILURE' || c.conclusion === 'CANCELLED' || c.conclusion === 'TIMED_OUT');
      const passed = checks.filter(c => c.conclusion === 'SUCCESS');

      // Progress update
      const status = `CI: ${passed.length}✓ ${pending.length}⏳ ${failed.length}✗`;
      if (status !== lastStatus) {
        console.log(`### ${status}`);
        lastStatus = status;
      }

      if (failed.length > 0) {
        return {
          passed: false,
          failed: failed.map(c => ({ name: c.name, conclusion: c.conclusion })),
          checks
        };
      }

      if (pending.length === 0) {
        return { passed: true, checks };
      }

      // Wait before next poll
      await sleep(CI_POLL_INTERVAL_MS);
    } catch (err) {
      // gh CLI error - might not have pr checks or no gh available
      return { passed: true, error: err.message };
    }
  }

  // Timeout
  return { passed: false, timeout: true };
}

// ============================================================================
// Edge Case 13: Completion Summary
// ============================================================================

function countCompletedTasks() {
  try {
    if (!fs.existsSync(PERSISTENT_TASKS_FILE)) return { completed: 0, total: 0 };
    const data = JSON.parse(fs.readFileSync(PERSISTENT_TASKS_FILE, 'utf8'));
    const tasks = data.tasks || [];
    const completed = tasks.filter(t => t.status === 'completed').length;
    return { completed, total: tasks.length };
  } catch {
    return { completed: 0, total: 0 };
  }
}

function getRecentCommits() {
  try {
    const result = execSync('git log --oneline -10 --since="24 hours ago" 2>/dev/null', {
      encoding: 'utf8',
      timeout: 5000
    });
    return result.trim().split('\n').filter(Boolean);
  } catch {
    return [];
  }
}

function calculateDuration(state) {
  try {
    const started = new Date(state.startedAt || state.createdAt);
    const now = new Date();
    const diffMs = now - started;
    const mins = Math.round(diffMs / 60000);
    return mins < 60 ? `${mins} minutes` : `${Math.round(mins / 60 * 10) / 10} hours`;
  } catch {
    return 'unknown';
  }
}

function generateCompletionSummary(state) {
  const taskCounts = countCompletedTasks();
  const commits = getRecentCommits();

  // Get test results
  let testSummary = { tests: '?', types: '?', lint: '?', build: '?' };
  try {
    if (fs.existsSync(TEST_RESULTS_FILE)) {
      const results = JSON.parse(fs.readFileSync(TEST_RESULTS_FILE, 'utf8'));
      const r = results.results || {};
      testSummary = {
        tests: r.tests?.passed ? '✓' : (r.tests?.ran ? '✗' : '—'),
        types: r.types?.passed ? '✓' : (r.types?.ran ? '✗' : '—'),
        lint: r.lint?.passed ? '✓' : (r.lint?.ran ? '✗' : '—'),
        build: r.build?.passed ? '✓' : (r.build?.ran ? '✗' : '—')
      };
    }
  } catch {}

  // Get git info
  let gitInfo = { pr: null, ci: null, branch: null };
  try {
    if (fs.existsSync(GIT_RESULTS_FILE)) {
      const git = JSON.parse(fs.readFileSync(GIT_RESULTS_FILE, 'utf8'));
      gitInfo = {
        pr: git.pr?.url || git.pr?.number,
        ci: git.ci?.passed ? '✓ Passed' : (git.ci?.checked ? '✗ Failed' : '—'),
        branch: git.branch
      };
    }
  } catch {}

  const summary = {
    sessionId: state.sessionId || process.pid.toString(),
    task: state.task,
    duration: calculateDuration(state),
    iterations: state.iteration,
    maxIterations: state.maxIterations,
    phases: state.phasesCompleted || [state.phase],
    tasks: taskCounts,
    commits: commits.length,
    testResults: testSummary,
    git: gitInfo,
    completedAt: new Date().toISOString()
  };

  // Write summary file
  try {
    fs.writeFileSync(SUMMARY_FILE, JSON.stringify(summary, null, 2));
  } catch {}

  // Format for console output
  return `
## Deep Loop Complete ✓

**Session:** ${summary.sessionId.slice(0, 8)}
**Task:** ${summary.task || 'See .deep/task.md'}
**Duration:** ${summary.duration}
**Iterations:** ${summary.iterations}/${summary.maxIterations}

### Tasks
${taskCounts.total > 0 ? `${taskCounts.completed}/${taskCounts.total} completed` : 'N/A'}

### Verification
Tests: ${testSummary.tests} | Types: ${testSummary.types} | Lint: ${testSummary.lint} | Build: ${testSummary.build}

### Git
${commits.length > 0 ? `Commits: ${commits.length}` : 'No commits'}
${gitInfo.pr ? `PR: ${gitInfo.pr}` : ''}
${gitInfo.ci ? `CI: ${gitInfo.ci}` : ''}
`;
}

// ============================================================================
// Main Hook Logic
// ============================================================================

function readState() {
  try {
    if (!fs.existsSync(STATE_FILE)) return null;
    return JSON.parse(fs.readFileSync(STATE_FILE, 'utf8'));
  } catch {
    return null;
  }
}

function shouldForceExit() {
  if (fs.existsSync(FORCE_EXIT_FILE)) {
    try { fs.unlinkSync(FORCE_EXIT_FILE); } catch {}
    return true;
  }
  return false;
}

function shouldForceComplete() {
  if (fs.existsSync(FORCE_COMPLETE_FILE)) {
    try {
      const reason = fs.readFileSync(FORCE_COMPLETE_FILE, 'utf8').trim();
      console.log(`## Force complete: ${reason || 'No reason given'}`);
      fs.unlinkSync(FORCE_COMPLETE_FILE);
    } catch {}
    return true;
  }
  return false;
}

function shouldRalphHandoff() {
  if (fs.existsSync(RALPH_HANDOFF_FILE)) {
    try { fs.unlinkSync(RALPH_HANDOFF_FILE); } catch {}
    return true;
  }
  return false;
}

function getPhasePrompt(state, tasksData = null) {
  const { phase, iteration, maxIterations, task } = state;

  const rlmStatus = getRlmStatusSummary();

  const header = `
## Deep Loop - Iteration ${iteration}/${maxIterations}
**Phase:** ${phase}
**Task:** ${task || 'See .deep/task.md'}
${rlmStatus}`;

  const prompts = {
    'PLAN': `${header}
### PLAN Phase

Create \`.deep/plan.md\` with:
1. Problem statement
2. Acceptance criteria (testable)
3. Task breakdown (atomic)
4. Risks

When done: Update state.json to \`"phase": "BUILD"\`
`,
    'BUILD': `${header}
### BUILD Phase

Execute tasks from plan.md:
1. Work through tasks in order
2. Run validation after each (test, lint, types)
3. Commit atomically per task
4. Log failures to issues.json
${getAtomicCommitReminder()}
${getSimplificationReminder('BUILD')}

When done: Update state.json to \`"phase": "REVIEW"\`
`,
    'REVIEW': `${header}
### REVIEW Phase

Run comprehensive review:
1. Code review patterns
2. Security audit
3. Test coverage
4. E2E verification
${getVerificationReminder(state)}
${getCompletionChecklist()}

If issues: Update to \`"phase": "FIX"\`
If clean: Update to \`"phase": "SHIP"\`, \`"complete": true\`
`,
    'FIX': `${header}
### FIX Phase

Address issues from issues.json:
1. Fix each issue
2. Commit atomically
3. Run validation

When done: Clear issues.json, update to \`"phase": "REVIEW"\`
`,
    'SHIP': `${header}
### SHIP Phase

**MANDATORY: Invoke verify-app subagent via Task tool before completing.**

Git Integration (if in repo):
1. Push branch
2. Create PR
3. Wait for CI
4. Merge

When ALL gates pass: Update state.json \`"phase": "SHIP", "complete": true\`
Output: \`<promise>COMPLETE</promise>\`
`,
    'COMPLETE': null
  };

  return prompts[phase] || null;
}

async function main() {
  // Force exit check
  if (shouldForceExit()) {
    console.log('## Deep Loop - Force exit');
    process.exit(0);
  }

  // Force complete check
  if (shouldForceComplete()) {
    process.exit(0);
  }

  // Ralph handoff check
  if (shouldRalphHandoff()) {
    console.log('## Deep Loop - Ralph handoff');
    process.exit(0);
  }

  // User escalation check
  if (fs.existsSync(ESCALATION_FILE)) {
    try {
      const esc = JSON.parse(fs.readFileSync(ESCALATION_FILE, 'utf8'));
      console.log(`
## BLOCKED - User Escalation Pending

Task \`${esc.taskId}\` needs your attention.
See \`.deep/NEEDS_USER\` for details.

To continue: Delete \`.deep/NEEDS_USER\` after addressing the issue.
`);
      console.error('[BLOCKED] User escalation pending');
      process.exit(2);
    } catch {}
  }

  const state = readState();
  const tasksData = readPersistentTasks();

  // RLM cost check (Edge Case 11)
  const rlmCheck = checkRlmCosts();
  if (rlmCheck.blocked) {
    console.log(rlmCheck.message);
    console.error('[BLOCKED] RLM cost limit reached');
    process.exit(2);
  }
  if (rlmCheck.warning) {
    console.log(rlmCheck.warning);
  }

  // Check deep loop state
  if (state && state.complete !== true && state.phase !== 'COMPLETE' && state.phase !== 'SHIP') {
    // Staleness check
    if (isStateStale()) {
      console.log('## Deep Loop - Stale state (>8hrs), allowing exit');
    }
    // Iteration limit check (Edge Case 1)
    else {
      const iterCheck = checkIterationLimit(state);
      if (iterCheck.blocked) {
        console.log(iterCheck.message);
        console.error('[BLOCKED] Iteration limit reached');
        process.exit(2);
      }

      // Active loop - block and continue
      state.iteration = (state.iteration || 0) + 1;
      state.lastActivity = new Date().toISOString();
      fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));

      const prompt = getPhasePrompt(state, tasksData);
      if (prompt) {
        console.log(prompt);
        console.error('[BLOCKED] Deep Loop phase: ' + state.phase);
        process.exit(2);
      }
    }
  }

  // Verify completion (Edge Cases 3, 7)
  if (state && (state.complete === true || state.phase === 'COMPLETE' || state.phase === 'SHIP')) {
    const testV = verifyTestResults();
    if (!testV.valid) {
      console.log(`
## BLOCKED - Tests Not Verified

${testV.missing.length ? '**Missing:** ' + testV.missing.join(', ') : ''}
${testV.failed.length ? '**Failed:** ' + testV.failed.join(', ') : ''}

Run all validations and update test-results.json.
`);
      state.phase = 'REVIEW';
      state.complete = false;
      fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));
      console.error('[BLOCKED] Test verification failed');
      process.exit(2);
    }

    const gitV = verifyGitResults();
    if (!gitV.skip && !gitV.valid) {
      // Check if CI needs active polling
      const gitResults = fs.existsSync(GIT_RESULTS_FILE)
        ? JSON.parse(fs.readFileSync(GIT_RESULTS_FILE, 'utf8'))
        : {};

      // Active CI polling if PR exists but CI not checked
      if (gitV.missing.includes('CI not checked') && gitResults.pr?.number) {
        console.log('### Polling CI status...');
        const ciResult = await waitForCI(gitResults.pr.number);

        // Update git-results.json with CI outcome
        gitResults.ci = {
          checked: true,
          passed: ciResult.passed,
          checkedAt: new Date().toISOString(),
          ...(ciResult.failed && { failed: ciResult.failed }),
          ...(ciResult.timeout && { timeout: true }),
          ...(ciResult.noCi && { noCi: true })
        };
        fs.writeFileSync(GIT_RESULTS_FILE, JSON.stringify(gitResults, null, 2));

        if (!ciResult.passed) {
          const failMsg = ciResult.timeout
            ? 'CI timed out after 10 minutes'
            : ciResult.failed?.map(f => `${f.name}: ${f.conclusion}`).join(', ');
          console.log(`
## BLOCKED - CI Failed

**Error:** ${failMsg}

Fix the CI issues and push again.
`);
          state.phase = 'FIX';
          state.complete = false;
          fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));
          console.error('[BLOCKED] CI failed');
          process.exit(2);
        }

        // CI passed - re-verify git results
        const gitV2 = verifyGitResults();
        if (!gitV2.skip && !gitV2.valid) {
          console.log(`
## BLOCKED - Git Workflow Incomplete

${gitV2.missing.length ? '**Missing:** ' + gitV2.missing.join(', ') : ''}
${gitV2.failed.length ? '**Failed:** ' + gitV2.failed.join(', ') : ''}

Complete the git workflow:
1. Create PR: \`gh pr create\`
2. Wait for CI: \`gh pr checks --watch\`
3. Merge: \`gh pr merge --squash\`
`);
          state.phase = 'REVIEW';
          state.complete = false;
          fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));
          console.error('[BLOCKED] Git verification failed');
          process.exit(2);
        }
      } else {
        console.log(`
## BLOCKED - Git Workflow Incomplete

${gitV.missing.length ? '**Missing:** ' + gitV.missing.join(', ') : ''}
${gitV.failed.length ? '**Failed:** ' + gitV.failed.join(', ') : ''}

Complete the git workflow:
1. Create PR: \`gh pr create\`
2. Wait for CI: \`gh pr checks --watch\`
3. Merge: \`gh pr merge --squash\`
`);
        state.phase = 'REVIEW';
        state.complete = false;
        fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));
        console.error('[BLOCKED] Git verification failed');
        process.exit(2);
      }
    }
  }

  // Check persistent tasks (Edge Case 4)
  const pendingTasks = getPendingTasks(tasksData);
  if (pendingTasks.length > 0) {
    const current = pendingTasks.find(t => t.status === 'in_progress') || pendingTasks[0];

    // Check for stuck task (Edge Case 10)
    const escCheck = checkUserEscalation(current.id);
    if (escCheck.escalate) {
      console.log(escCheck.message);
      console.error('[BLOCKED] User escalation required');
      process.exit(2);
    }

    console.log(`
## Persistent Tasks - ${pendingTasks.length} remaining

**Next:** ${current.content}
**ID:** ${current.id}
**Iteration:** ${current.iteration || 1}

Continue working. Update persistent-tasks.json when complete.
`);
    console.error('[BLOCKED] ' + pendingTasks.length + ' tasks remaining');
    process.exit(2);
  }

  // Cleanup on success
  releaseLock();

  // Generate completion summary if loop was active
  if (state && (state.complete === true || state.phase === 'COMPLETE' || state.phase === 'SHIP')) {
    const summary = generateCompletionSummary(state);
    console.log(summary);
  }

  console.log('[OK] Deep Loop: Exit allowed');
  process.exit(0);
}

main().catch(err => {
  console.error('Deep loop hook error:', err.message);
  process.exit(0); // Fail open - don't block on unexpected errors
});
