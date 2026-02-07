#!/usr/bin/env node

/**
 * Deep Loop Stop Hook v4.0 - Enriched Phase Prompts
 *
 * Simple while-true mechanism:
 * 1. Check max iterations safety valve
 * 2. Check staleness (8hr threshold)
 * 3. Detect <promise>PHASE_COMPLETE</promise> tags
 * 4. Feed enriched phase prompt back to continue loop
 *
 * v4.0 changes:
 * - Structured error logging (no more silent catches)
 * - Optimized transcript reading (tail 50KB instead of full read)
 * - Enriched phase prompts (BUILD multi-agent, REVIEW skills, SHIP PR)
 * - Increased assistant message check from 5 to 10
 */

import fs from 'fs';
import path from 'path';

// Session-specific directory
let DEEP_DIR = '.deep';
let sessionId = null;

function logError(err, context = '') {
  try {
    const logPath = getDeepPath('hook-errors.log');
    const entry = `[${new Date().toISOString()}] ${context}: ${err.message || err}\n`;
    fs.appendFileSync(logPath, entry);
  } catch {
    // Last resort: stderr
    process.stderr.write(`[deep-hook] ${context}: ${err.message || err}\n`);
  }
}

function initDeepDir(sid) {
  sessionId = sid;
  if (sid && sid.length >= 8) {
    DEEP_DIR = `.deep-${sid.slice(0, 8)}`;
  }
  if (!fs.existsSync(DEEP_DIR) && fs.existsSync('.deep') && !sessionId) {
    DEEP_DIR = '.deep';
  }
  return DEEP_DIR;
}

function getDeepPath(filename) {
  return path.join(DEEP_DIR, filename);
}

// File paths
const STATE_FILE = () => getDeepPath('state.json');
const TASK_FILE = () => getDeepPath('task.md');
const PLAN_FILE = () => getDeepPath('plan.md');
const FORCE_EXIT_FILE = () => getDeepPath('FORCE_EXIT');

// Configuration
const STALE_THRESHOLD_MS = 8 * 60 * 60 * 1000; // 8 hours
const TRANSCRIPT_TAIL_BYTES = 50 * 1024; // Read last 50KB of transcript

// Phase completion promises
const PHASE_PROMISES = {
  'CHALLENGE': 'CHALLENGE_COMPLETE',
  'RLM_EXPLORE': 'RLM_COMPLETE',
  'PLAN': 'PLAN_COMPLETE',
  'BUILD': 'BUILD_COMPLETE',
  'REVIEW': 'REVIEW_COMPLETE',
  'FIX': 'FIX_COMPLETE',
  'SHIP': 'SHIP_COMPLETE'
};

// Final completion promises
const DEEP_COMPLETE = 'DEEP_COMPLETE';
const QUICK_COMPLETE = 'QUICK_COMPLETE';

// Step detection patterns for progress tracking
const STEP_PATTERNS = [
  { pattern: /git (commit|add)/i, step: 'Committing' },
  { pattern: /\.(test|spec)\.(ts|tsx|js|jsx)/i, step: 'Writing tests' },
  { pattern: /(npm test|vitest|jest|pytest|cargo test)/i, step: 'Testing' },
  { pattern: /(npm run lint|eslint|biome|prettier)/i, step: 'Linting' },
  { pattern: /(tsc|typecheck|type-check)/i, step: 'Type checking' },
  { pattern: /(npm run build|cargo build|go build)/i, step: 'Building' },
  { pattern: /Task tool|subagent/i, step: 'Running subagent' },
  { pattern: /task-agent|TASK_COMPLETE|TASK_BLOCKED/i, step: 'Task agent' },
  { pattern: /tasks-status\.json/i, step: 'Orchestrating tasks' },
  { pattern: /(Write|Edit) tool/i, step: 'Implementing' },
  { pattern: /(Read|Glob|Grep) tool/i, step: 'Exploring' }
];

function readState() {
  try {
    if (!fs.existsSync(STATE_FILE())) return null;
    return JSON.parse(fs.readFileSync(STATE_FILE(), 'utf8'));
  } catch (err) {
    logError(err, 'readState');
    return null;
  }
}

function writeState(state) {
  try {
    fs.writeFileSync(STATE_FILE(), JSON.stringify(state, null, 2));
  } catch (err) {
    logError(err, 'writeState');
  }
}

function isStale(state) {
  try {
    const started = new Date(state.startedAt || state.createdAt).getTime();
    return Date.now() - started > STALE_THRESHOLD_MS;
  } catch (err) {
    logError(err, 'isStale');
    return false;
  }
}

function shouldForceExit() {
  if (fs.existsSync(FORCE_EXIT_FILE())) {
    try { fs.unlinkSync(FORCE_EXIT_FILE()); } catch (err) {
      logError(err, 'shouldForceExit:unlink');
    }
    return true;
  }
  return false;
}

function readTask() {
  try {
    if (fs.existsSync(TASK_FILE())) {
      return fs.readFileSync(TASK_FILE(), 'utf8').trim();
    }
  } catch (err) {
    logError(err, 'readTask');
  }
  return null;
}

/**
 * Read last N bytes of transcript for efficiency.
 * For 8hr sessions the transcript can be huge - avoid reading entire file.
 */
function readTranscriptTail(transcriptPath) {
  try {
    if (!transcriptPath || !fs.existsSync(transcriptPath)) return '';

    const stat = fs.statSync(transcriptPath);
    const fileSize = stat.size;

    if (fileSize <= TRANSCRIPT_TAIL_BYTES) {
      return fs.readFileSync(transcriptPath, 'utf8');
    }

    // Read only the last TRANSCRIPT_TAIL_BYTES
    const fd = fs.openSync(transcriptPath, 'r');
    const buffer = Buffer.alloc(TRANSCRIPT_TAIL_BYTES);
    fs.readSync(fd, buffer, 0, TRANSCRIPT_TAIL_BYTES, fileSize - TRANSCRIPT_TAIL_BYTES);
    fs.closeSync(fd);

    return buffer.toString('utf8');
  } catch (err) {
    logError(err, 'readTranscriptTail');
    return '';
  }
}

function checkPromiseInTranscript(transcriptPath, promise) {
  try {
    const content = readTranscriptTail(transcriptPath);
    if (!content) return false;

    const lines = content.split('\n').filter(Boolean);

    // Check last 10 assistant messages (up from 5)
    const assistantLines = lines
      .filter(l => l.includes('"role":"assistant"'))
      .slice(-10);

    for (const line of assistantLines) {
      try {
        const msg = JSON.parse(line);
        const textParts = (msg.message?.content || [])
          .filter(c => c.type === 'text')
          .map(c => c.text)
          .join('\n');

        if (textParts.includes(`<promise>${promise}</promise>`)) {
          return true;
        }
      } catch (err) {
        logError(err, 'checkPromiseInTranscript:parseLine');
      }
    }
  } catch (err) {
    logError(err, 'checkPromiseInTranscript');
  }
  return false;
}

function detectCurrentStep(transcriptPath) {
  try {
    const content = readTranscriptTail(transcriptPath);
    if (!content) return null;

    const lines = content.split('\n').filter(Boolean);
    const recentLines = lines.slice(-10);

    for (const line of recentLines.reverse()) {
      for (const { pattern, step } of STEP_PATTERNS) {
        if (pattern.test(line)) {
          return step;
        }
      }
    }
  } catch (err) {
    logError(err, 'detectCurrentStep');
  }
  return null;
}

function isQuickMode(state) {
  return state?.mode === 'quick';
}

function isExternalMode(state) {
  return state?.mode === 'external';
}

function getMaxIterations(state) {
  if (isQuickMode(state)) return 3;
  return state?.maxIterations || 10;
}

function buildPhasePrompt(state) {
  const task = readTask() || state.task || 'See plan.md';
  const { phase, iteration, maxIterations } = state;

  const basePrompt = `
## Deep Loop - Iteration ${iteration}/${maxIterations}
**Phase:** ${phase}
**Task:** ${task}

Read state from:
- ${DEEP_DIR}/plan.md - Your implementation plan
- ${DEEP_DIR}/state.json - Current progress
- ${DEEP_DIR}/issues.json - Outstanding issues (if exists)
`;

  const phaseInstructions = {
    'CHALLENGE': `
### CHALLENGE Phase (Senior Dev Pushback)

Before building, challenge the request:

1. **Understand the WHY** - What problem are we really solving?
2. **Challenge the approach**:
   - Do we need to build this at all?
   - Is there an existing solution?
   - What's the simplest approach?
   - What are the risks?
3. **Propose alternatives** if simpler options exist
4. **Get user confirmation** via AskUserQuestion

Output your challenge assessment, then ask user how to proceed.

When done: Update state.json to phase: PLAN (or COMPLETE if cancelled)
Output: <promise>CHALLENGE_COMPLETE</promise>
`,
    'RLM_EXPLORE': `
### RLM_EXPLORE Phase

Large codebase detected. Explore and map architecture:
1. Probe codebase structure
2. Chunk by module/directory
3. Write exploration report to ${DEEP_DIR}/exploration.md

When done: Update state.json to phase: PLAN
Output: <promise>RLM_COMPLETE</promise>
`,
    'PLAN': `
### PLAN Phase

Follow the /deep-plan Mode 1 planning approach.

#### Step 1: Locked Assumptions (Auto-Approved)

Output as locked declarations, proceed immediately:

\`\`\`markdown
## Locked Assumptions (Auto-Approved)
**Task:** [specific]
**Stack:** [technology] BECAUSE [reason]
**Files:** [list]
**Scope IN:** [included]
**Scope OUT:** [excluded]
**Key Bets:** [critical decisions]
\`\`\`

#### Step 1.5: Root Cause Analysis (Mandatory)

**Question:** Are we solving ROOT PROBLEM or treating SYMPTOM?

#### Step 2: Detailed Plan

Create ${DEEP_DIR}/plan.md with:
1. Problem statement
2. Testable acceptance criteria
3. Atomic task breakdown (<=3 files per task, <=20 min each)
4. Risk assessment

Also create ${DEEP_DIR}/decisions.md with locked decisions table.

When done: Update state.json to phase: BUILD
Output: <promise>PLAN_COMPLETE</promise>
`,
    'BUILD': `
### BUILD Phase (Multi-Agent TDD)

**Test-Driven Development is MANDATORY.**
**NO PARTIAL COMPLETION - Tasks must be 100% done or not done.**

#### Build Mode

Check state.json \`buildMode\`:
- \`"multi-agent"\` (default): You are the ORCHESTRATOR. Spawn Task agents.
- \`"single"\`: Execute tasks sequentially in this session.

#### Multi-Agent Orchestration

1. **Parse tasks** from plan.md, identify dependencies
2. **Write** ${DEEP_DIR}/tasks-status.json with task list
3. **Spawn Task agents** (up to maxParallel concurrent):

\`\`\`
Task({
  subagent_type: "deep-loop:task-agent",
  description: "Build: {task_title}",
  prompt: "Task: {title}\\nCriteria: {criteria}\\nDecisions: {decisions.md content}\\n\\n1. RED: failing test\\n2. GREEN: implement\\n3. REFACTOR: cleanup\\n4. Validate: test, lint, types",
  run_in_background: false
})
\`\`\`

4. **Handle failures**: retry 2x same prompt, then new agent with error context, then escalate after 3 total
5. **Invoke skill**: \`Skill({ skill: "tdd-workflow" })\` for TDD guidance
6. **Frontend tasks**: Also invoke \`Skill({ skill: "frontend-design" })\`

#### Post-Build

After all tasks complete, invoke code-simplifier:
\`\`\`
Task({
  subagent_type: "deep-loop:code-simplifier",
  model: "haiku",
  description: "Simplify: post-build cleanup",
  prompt: "Review recently changed code. Remove unnecessary complexity."
})
\`\`\`

#### Completion Gate

Before BUILD_COMPLETE:
- [ ] ALL atomic tasks complete (not some, ALL)
- [ ] All tests pass
- [ ] No TODOs, FIXMEs, or placeholder code
- [ ] code-simplifier has run

When done: Update state.json to phase: REVIEW
Output: <promise>BUILD_COMPLETE</promise>
`,
    'REVIEW': `
### REVIEW Phase (Automated + Adversarial + Skills)

**Part 1: Automated Validation**
\`\`\`bash
npm test && npm run typecheck && npm run lint && npm run build
\`\`\`

**Part 2: Skill Invocations (MANDATORY)**
\`\`\`
Skill({ skill: "code-review" })
Skill({ skill: "security-audit" })
\`\`\`
Log any issues found by skills to ${DEEP_DIR}/issues.json.

**Part 3: Adversarial Self-Review (Senior Dev Mindset)**

Ask yourself and log concerns to issues.json:
- **Correctness**: Edge cases missed?
- **Security**: Injection, auth, data exposure risks?
- **Performance**: N+1 queries, unbounded loops, memory leaks?
- **Maintainability**: Would a new dev understand this?
- **Error handling**: What happens when things fail?
- **Over-engineering**: Built more than needed?
- **Under-engineering**: Cut corners that will bite us?

**Part 4: Smell Check**
- Functions > 50 lines
- Files > 300 lines
- Deep nesting (> 3 levels)
- Magic numbers/strings
- Commented-out code
- Copy-pasted blocks

**Part 5: Pre-Ship Root Cause Validation**
Did we solve root problem or just treat symptoms?
If symptom fix, document root in decisions.md.

Record in ${DEEP_DIR}/test-results.json.

If ALL pass AND no critical issues: Update state.json to phase: SHIP
If ANY issues: Update state.json to phase: FIX, add to issues.json

Output: <promise>REVIEW_COMPLETE</promise>
`,
    'FIX': `
### FIX Phase

**Root Cause Check (Mandatory):** For each failure, ask: symptom or root cause?
- Race condition masking timing issue?
- Flaky test revealing state leakage?
- Edge case exposing design flaw?

Use: \`Skill({ skill: "debug-investigate" })\` for root cause analysis.

Address ${DEEP_DIR}/issues.json:
1. Run root cause check for each failure
2. Fix each issue (root or symptom, documented)
3. Commit atomically: \`[deep] fix: {description}\`
4. Run validation

When all fixed: Clear issues.json, update state.json to phase: REVIEW
Output: <promise>FIX_COMPLETE</promise>
`,
    'SHIP': `
### SHIP Phase

**1. Invoke verify-app subagent:**
\`\`\`
Task({
  subagent_type: "deep-loop:verify-app",
  description: "Verify: E2E testing",
  prompt: "Detect app type (web, API, CLI, library). Run appropriate verification. Output: VERIFIED or issues list."
})
\`\`\`

**2. Invoke PR craftsman skill:**
\`\`\`
Skill({ skill: "pr-craftsman" })
\`\`\`

**3. Git finalization (if in repo):**
\`\`\`bash
git push -u origin HEAD
gh pr create --base main --fill
gh pr merge --auto --squash
\`\`\`

**4. Write lessons-learned:**
Create ${DEEP_DIR}/lessons-learned.md reflecting on:
- Wrong assumptions and when caught
- Overcomplication introduced
- Scope creep that happened
- Root cause vs symptom fixes

**Completion Checklist:**
- [ ] All acceptance criteria met
- [ ] All tests pass
- [ ] verify-app passes
- [ ] PR created and merged (or committed to main)

When ALL complete:
Update state.json: phase: COMPLETE, complete: true
Output: <promise>DEEP_COMPLETE</promise>
`
  };

  return basePrompt + (phaseInstructions[phase] || '');
}

async function main(transcriptPath) {
  // Force exit check
  if (shouldForceExit()) {
    console.log('[OK] Deep Loop - Force exit');
    process.exit(0);
  }

  const state = readState();

  // No active loop
  if (!state || !state.active) {
    process.exit(0);
  }

  // External mode: don't block - let bash script handle orchestration
  if (isExternalMode(state)) {
    if (checkPromiseInTranscript(transcriptPath, DEEP_COMPLETE)) {
      state.complete = true;
      state.phase = 'COMPLETE';
      writeState(state);
      console.log('[OK] External loop - DEEP_COMPLETE detected');
    }
    process.exit(0);
  }

  // Detect and update current step for progress tracking
  const detectedStep = detectCurrentStep(transcriptPath);
  if (detectedStep && state.current_step !== detectedStep) {
    state.current_step = detectedStep;
    writeState(state);
  }

  // Check for quick mode
  const quickMode = isQuickMode(state);
  const maxIter = getMaxIterations(state);

  // Already complete
  if (state.complete || state.phase === 'COMPLETE') {
    const modeLabel = quickMode ? 'Quick' : 'Deep';
    console.log(`
## ${modeLabel} Loop Complete

Session: ${sessionId?.slice(0, 8) || 'unknown'}
Iterations: ${state.iteration}/${maxIter}
`);
    process.exit(0);
  }

  // Staleness check
  if (isStale(state)) {
    console.log('[OK] Deep Loop - Stale (>8hrs), allowing exit');
    process.exit(0);
  }

  // Max iterations safety valve
  if (state.iteration >= maxIter) {
    const modeLabel = quickMode ? 'QUICK' : 'DEEP';
    console.log(`
## ${modeLabel} ITERATION LIMIT REACHED (${state.iteration}/${maxIter})

Options:
1. Force exit: touch ${DEEP_DIR}/FORCE_EXIT
2. Increase limit: edit ${DEEP_DIR}/state.json maxIterations
3. Mark complete: set complete: true in state.json
`);
    process.exit(0);
  }

  // Check for quick mode completion
  if (quickMode && checkPromiseInTranscript(transcriptPath, QUICK_COMPLETE)) {
    state.complete = true;
    state.result = 'success';
    state.active = false;
    writeState(state);
    console.log('[OK] Quick mode complete');
    process.exit(0);
  }

  // Check for phase completion promise
  const currentPhase = state.phase;
  const phasePromise = PHASE_PROMISES[currentPhase];

  if (phasePromise && checkPromiseInTranscript(transcriptPath, phasePromise)) {
    console.log(`[OK] Phase ${currentPhase} complete`);
    process.exit(0);
  }

  // Check for final completion
  if (checkPromiseInTranscript(transcriptPath, DEEP_COMPLETE)) {
    state.complete = true;
    state.phase = 'COMPLETE';
    writeState(state);
    console.log('[OK] Deep Loop complete');
    process.exit(0);
  }

  // Continue loop - increment iteration and feed prompt
  state.iteration = (state.iteration || 0) + 1;
  state.lastActivity = new Date().toISOString();
  writeState(state);

  // Build appropriate prompt
  let phasePrompt, systemMsg;

  if (quickMode) {
    phasePrompt = `
## Quick Mode - Iteration ${state.iteration}/${maxIter}
**Task:** ${state.task || 'See task.md'}

Execute directly:
1. Read relevant file(s)
2. Make the change
3. Validate (lint, types)
4. Commit: [quick] <description>

When done: <promise>QUICK_COMPLETE</promise>

If blocked after 3 attempts, ask user for guidance.
`;
    systemMsg = `Quick ${state.iteration}/${maxIter} | To complete: <promise>QUICK_COMPLETE</promise>`;
  } else {
    phasePrompt = buildPhasePrompt(state);
    systemMsg = `Deep ${state.iteration}/${maxIter} | Phase: ${state.phase} | Step: ${state.current_step || 'Unknown'} | Complete: <promise>${phasePromise || DEEP_COMPLETE}</promise>`;
  }

  // Output JSON to block exit and feed prompt
  const output = {
    decision: 'block',
    reason: phasePrompt,
    systemMessage: systemMsg
  };

  console.log(JSON.stringify(output));
  process.exit(2);
}

// Read hook input from stdin
let hookInput = '';
process.stdin.setEncoding('utf8');

process.stdin.on('data', (chunk) => {
  hookInput += chunk;
});

process.stdin.on('end', () => {
  try {
    const input = JSON.parse(hookInput);
    initDeepDir(input.session_id);
    main(input.transcript_path).catch(err => {
      logError(err, 'main:catch');
      process.exit(0);
    });
  } catch (err) {
    logError(err, 'stdin:parse');
    initDeepDir(null);
    main(null).catch(err => {
      logError(err, 'main:fallback');
      process.exit(0);
    });
  }
});

// Timeout for stdin
setTimeout(() => {
  if (!hookInput) {
    initDeepDir(null);
    main(null).catch(err => {
      logError(err, 'main:timeout');
      process.exit(0);
    });
  }
}, 5000);
