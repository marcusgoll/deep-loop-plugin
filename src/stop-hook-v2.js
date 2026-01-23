#!/usr/bin/env node

/**
 * Deep Loop Stop Hook v3.0 - Ralph-Style Simple Loop
 *
 * Simple while-true mechanism:
 * 1. Check max iterations safety valve
 * 2. Check staleness (8hr threshold)
 * 3. Detect <promise>PHASE_COMPLETE</promise> tags
 * 4. Feed phase prompt back to continue loop
 *
 * Verification logic moved to phases - trust the prompts.
 */

import fs from 'fs';
import path from 'path';

// Session-specific directory
let DEEP_DIR = '.deep';
let sessionId = null;

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
  { pattern: /(Write|Edit) tool/i, step: 'Implementing' },
  { pattern: /(Read|Glob|Grep) tool/i, step: 'Exploring' }
];

function readState() {
  try {
    if (!fs.existsSync(STATE_FILE())) return null;
    return JSON.parse(fs.readFileSync(STATE_FILE(), 'utf8'));
  } catch {
    return null;
  }
}

function writeState(state) {
  try {
    fs.writeFileSync(STATE_FILE(), JSON.stringify(state, null, 2));
  } catch {}
}

function isStale(state) {
  try {
    const started = new Date(state.startedAt || state.createdAt).getTime();
    return Date.now() - started > STALE_THRESHOLD_MS;
  } catch {
    return false;
  }
}

function shouldForceExit() {
  if (fs.existsSync(FORCE_EXIT_FILE())) {
    try { fs.unlinkSync(FORCE_EXIT_FILE()); } catch {}
    return true;
  }
  return false;
}

function readTask() {
  try {
    if (fs.existsSync(TASK_FILE())) {
      return fs.readFileSync(TASK_FILE(), 'utf8').trim();
    }
  } catch {}
  return null;
}

function checkPromiseInTranscript(transcriptPath, promise) {
  try {
    if (!transcriptPath || !fs.existsSync(transcriptPath)) return false;

    // Read last few lines for efficiency
    const content = fs.readFileSync(transcriptPath, 'utf8');
    const lines = content.split('\n').filter(Boolean);

    // Check last 5 assistant messages
    const assistantLines = lines
      .filter(l => l.includes('"role":"assistant"'))
      .slice(-5);

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
      } catch {}
    }
  } catch {}
  return false;
}

function detectCurrentStep(transcriptPath) {
  try {
    if (!transcriptPath || !fs.existsSync(transcriptPath)) return null;

    const content = fs.readFileSync(transcriptPath, 'utf8');
    const lines = content.split('\n').filter(Boolean);

    // Check last 3 messages for step patterns
    const recentLines = lines.slice(-10);

    for (const line of recentLines.reverse()) {
      for (const { pattern, step } of STEP_PATTERNS) {
        if (pattern.test(line)) {
          return step;
        }
      }
    }
  } catch {}
  return null;
}

function isQuickMode(state) {
  return state?.mode === 'quick';
}

function isExternalMode(state) {
  return state?.mode === 'external';
}

function getMaxIterations(state) {
  // Quick mode: 3 iterations max
  // Standard: 10, Deep: 20
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

Create ${DEEP_DIR}/plan.md with:
1. Problem statement
2. Testable acceptance criteria
3. Atomic task breakdown
4. Risk assessment

When done: Update state.json to phase: BUILD
Output: <promise>PLAN_COMPLETE</promise>
`,
    'BUILD': `
### BUILD Phase (TDD)

**Test-Driven Development is MANDATORY.**
**NO PARTIAL COMPLETION - Tasks must be 100% done or not done.**

For each task from plan.md:

1. **RED** - Write failing test first
   - Commit: [deep] test: add failing test for <feature>

2. **GREEN** - Write minimal code to pass
   - Commit: [deep] implement: <feature>

3. **REFACTOR** - Clean up (optional)

4. **Validate** - Run full suite (test, lint, types)

**CRITICAL: Before marking task complete:**
- ALL acceptance criteria met (not some, ALL)
- No TODOs, FIXMEs, or placeholder code
- Feature works end-to-end

**If blocked:** Log to issues.json, retry 3x, then escalate.
**NEVER "partially complete" - either DONE or BLOCKED.**

After all tasks complete, run code-simplifier subagent.

When done: Update state.json to phase: REVIEW
Output: <promise>BUILD_COMPLETE</promise>
`,
    'REVIEW': `
### REVIEW Phase (with Adversarial Self-Review)

**Part 1: Automated Validation**
1. npm test (or equivalent)
2. npm run typecheck
3. npm run lint
4. npm run build

**Part 2: Adversarial Self-Review (Senior Dev Mindset)**
Ask yourself these questions and log concerns to issues.json:

- **Correctness**: What edge cases might I have missed?
- **Security**: Any injection, auth, or data exposure risks?
- **Performance**: Any N+1 queries, unbounded loops, or memory leaks?
- **Maintainability**: Would a new dev understand this code?
- **Error handling**: What happens when things fail?
- **Over-engineering**: Did I build more than needed?
- **Under-engineering**: Did I cut corners that will bite us?

**Part 3: Smell Check**
Look for these code smells:
- Functions > 50 lines
- Files > 300 lines
- Deep nesting (> 3 levels)
- Magic numbers/strings
- Commented-out code
- TODO/FIXME without tickets
- Copy-pasted code blocks

Record findings in ${DEEP_DIR}/test-results.json

If ALL pass AND no critical smells: Update state.json to phase: SHIP
If ANY issues: Update state.json to phase: FIX, add to issues.json

Output: <promise>REVIEW_COMPLETE</promise>
`,
    'FIX': `
### FIX Phase

Address ${DEEP_DIR}/issues.json:
1. Fix each issue
2. Commit atomically
3. Run validation

When all fixed: Clear issues.json, update state.json to phase: REVIEW
Output: <promise>FIX_COMPLETE</promise>
`,
    'SHIP': `
### SHIP Phase

1. Invoke verify-app subagent for E2E testing
2. Push branch, create PR, wait for CI
3. Merge when CI passes

Completion Checklist:
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
  // The stop hook should not interfere with external loop mode
  if (isExternalMode(state)) {
    // Check for completion to update state
    if (checkPromiseInTranscript(transcriptPath, DEEP_COMPLETE)) {
      state.complete = true;
      state.phase = 'COMPLETE';
      writeState(state);
      console.log('[OK] External loop - DEEP_COMPLETE detected');
    }
    // Always allow exit in external mode - bash script orchestrates
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

  // Max iterations safety valve (respects quick mode limit)
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

  // Check for phase completion promise (standard/deep mode)
  const currentPhase = state.phase;
  const phasePromise = PHASE_PROMISES[currentPhase];

  if (phasePromise && checkPromiseInTranscript(transcriptPath, phasePromise)) {
    // Phase complete - allow natural phase transition
    console.log(`[OK] Phase ${currentPhase} complete`);
    process.exit(0);
  }

  // Check for final completion (standard/deep mode)
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
    // Quick mode: simplified prompt
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
    // Standard/deep mode
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
      console.error('Deep loop hook error:', err.message);
      process.exit(0);
    });
  } catch {
    initDeepDir(null);
    main(null).catch(err => {
      console.error('Deep loop hook error:', err.message);
      process.exit(0);
    });
  }
});

// Timeout for stdin
setTimeout(() => {
  if (!hookInput) {
    initDeepDir(null);
    main(null).catch(err => {
      console.error('Deep loop hook error:', err.message);
      process.exit(0);
    });
  }
}, 5000);
