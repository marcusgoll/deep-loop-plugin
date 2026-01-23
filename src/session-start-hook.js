#!/usr/bin/env node

/**
 * Session Start Hook - Persistent Task Resume + Cleanup
 *
 * Runs at the start of each Claude Code session to:
 * 1. Clean up stale temp files (plans, .deep directories)
 * 2. Check for pending persistent tasks
 * 3. Alert the user if there are unfinished tasks
 * 4. Provide context for resumption
 */

import fs from 'fs';
import path from 'path';
import os from 'os';

// Session-specific directory management
let DEEP_DIR = '.deep'; // Default, will be updated with session ID
let sessionId = null;

function initDeepDir(sid) {
  sessionId = sid;
  if (sid && sid.length >= 8) {
    // Use short session ID (first 8 chars) for readability
    DEEP_DIR = `.deep-${sid.slice(0, 8)}`;
  }
  return DEEP_DIR;
}

function getDeepPath(filename) {
  return path.join(DEEP_DIR, filename);
}

const PERSISTENT_TASKS_FILE = () => getDeepPath('persistent-tasks.json');
const DEFAULT_TASK_STALE_HOURS = 24;
const DEFAULT_CLEANUP_DAYS = 7;

// Settings file location
const CLAUDE_SETTINGS = path.join(os.homedir(), '.claude', 'settings.json');
const CLAUDE_PLANS_DIR = path.join(os.homedir(), '.claude', 'plans');

/**
 * Read Claude settings to get cleanup config
 */
function getCleanupConfig() {
  try {
    if (fs.existsSync(CLAUDE_SETTINGS)) {
      const settings = JSON.parse(fs.readFileSync(CLAUDE_SETTINGS, 'utf8'));
      return {
        cleanupPeriodDays: settings.cleanupPeriodDays ?? DEFAULT_CLEANUP_DAYS,
        enabled: settings.cleanupPeriodDays !== 0
      };
    }
  } catch (e) {
    // Ignore errors, use defaults
  }
  return { cleanupPeriodDays: DEFAULT_CLEANUP_DAYS, enabled: true };
}

/**
 * Clean up stale plan files in ~/.claude/plans/
 * Returns count of removed files
 */
function cleanupStalePlans(maxAgeDays) {
  if (maxAgeDays <= 0) return 0;

  let removed = 0;
  const maxAgeMs = maxAgeDays * 24 * 60 * 60 * 1000;
  const now = Date.now();

  try {
    if (!fs.existsSync(CLAUDE_PLANS_DIR)) return 0;

    const files = fs.readdirSync(CLAUDE_PLANS_DIR);
    for (const file of files) {
      // Only process .md files (plan files have random names like cheeky-waddling-sun.md)
      if (!file.endsWith('.md')) continue;

      // Skip prd.json and other non-plan files
      if (file === 'prd.json' || file.startsWith('.')) continue;

      const filePath = path.join(CLAUDE_PLANS_DIR, file);
      try {
        const stats = fs.statSync(filePath);
        const ageMs = now - stats.mtimeMs;

        if (ageMs > maxAgeMs) {
          fs.unlinkSync(filePath);
          removed++;
        }
      } catch (e) {
        // Ignore individual file errors
      }
    }
  } catch (e) {
    // Ignore directory errors
  }

  return removed;
}

/**
 * Clean up stale .deep directories in current working directory
 * Only removes if state.json shows complete or is very old
 */
function cleanupStaleDeepDirs(maxAgeDays) {
  if (maxAgeDays <= 0) return 0;

  let removed = 0;
  const maxAgeMs = maxAgeDays * 24 * 60 * 60 * 1000;
  const now = Date.now();
  const cwd = process.cwd();

  try {
    const entries = fs.readdirSync(cwd);

    for (const entry of entries) {
      // Match .deep or .deep-{id} directories
      if (!entry.startsWith('.deep')) continue;

      const deepPath = path.join(cwd, entry);
      const stats = fs.statSync(deepPath);

      if (!stats.isDirectory()) continue;

      const statePath = path.join(deepPath, 'state.json');
      let shouldRemove = false;

      try {
        if (fs.existsSync(statePath)) {
          const state = JSON.parse(fs.readFileSync(statePath, 'utf8'));
          const stateStats = fs.statSync(statePath);
          const ageMs = now - stateStats.mtimeMs;

          // Remove if complete or very stale
          if (state.complete === true && state.phase === 'COMPLETE') {
            shouldRemove = true;
          } else if (ageMs > maxAgeMs) {
            shouldRemove = true;
          }
        } else {
          // No state.json - check directory age
          const ageMs = now - stats.mtimeMs;
          if (ageMs > maxAgeMs) {
            shouldRemove = true;
          }
        }
      } catch (e) {
        // If we can't read state, check age
        const ageMs = now - stats.mtimeMs;
        if (ageMs > maxAgeMs) {
          shouldRemove = true;
        }
      }

      if (shouldRemove) {
        try {
          fs.rmSync(deepPath, { recursive: true, force: true });
          removed++;
        } catch (e) {
          // Ignore removal errors
        }
      }
    }
  } catch (e) {
    // Ignore directory errors
  }

  return removed;
}

function readPersistentTasks() {
  try {
    if (!fs.existsSync(PERSISTENT_TASKS_FILE())) {
      return null;
    }
    return JSON.parse(fs.readFileSync(PERSISTENT_TASKS_FILE(), 'utf8'));
  } catch (e) {
    return null;
  }
}

function getPendingTasks(tasksData) {
  if (!tasksData || !tasksData.tasks || !Array.isArray(tasksData.tasks)) {
    return [];
  }

  const staleHours = tasksData.config?.staleThresholdHours || DEFAULT_TASK_STALE_HOURS;
  const staleMs = staleHours * 60 * 60 * 1000;
  const now = Date.now();

  return tasksData.tasks.filter(task => {
    if (task.status === 'completed') return false;
    if (task.status === 'blocked') return false;

    const createdAt = new Date(task.createdAt).getTime();
    if (now - createdAt > staleMs) return false;

    return true;
  });
}

function main() {
  // 1. Run cleanup first
  const config = getCleanupConfig();
  let cleanupMessage = '';

  if (config.enabled) {
    const plansRemoved = cleanupStalePlans(config.cleanupPeriodDays);
    const deepDirsRemoved = cleanupStaleDeepDirs(config.cleanupPeriodDays);

    if (plansRemoved > 0 || deepDirsRemoved > 0) {
      const parts = [];
      if (plansRemoved > 0) parts.push(`${plansRemoved} stale plan file(s)`);
      if (deepDirsRemoved > 0) parts.push(`${deepDirsRemoved} stale .deep director(ies)`);
      cleanupMessage = `Cleaned up: ${parts.join(', ')} (>${config.cleanupPeriodDays} days old)\n`;
    }
  }

  // 2. Check for pending tasks
  const tasksData = readPersistentTasks();
  const pendingTasks = getPendingTasks(tasksData);

  if (pendingTasks.length === 0 && !cleanupMessage) {
    // Nothing to report - silent exit
    process.exit(0);
  }

  // Output any messages
  if (cleanupMessage) {
    console.log(cleanupMessage);
  }

  if (pendingTasks.length > 0) {
    // Format task list
    const taskList = pendingTasks.slice(0, 5).map((t, i) => {
      const status = t.status === 'in_progress' ? '🔄' : '⏳';
      const priority = t.priority === 'high' ? '🔴' : t.priority === 'medium' ? '🟡' : '🟢';
      return `  ${i + 1}. ${status} ${priority} ${t.content}`;
    }).join('\n');

    console.log(`
## Persistent Tasks Detected

You have **${pendingTasks.length}** pending task(s) from a previous session:

${taskList}
${pendingTasks.length > 5 ? `  ... and ${pendingTasks.length - 5} more` : ''}

**Options:**
- Continue working on these tasks (the STOP hook will enforce completion)
- Run \`/deep tasks\` to see full list
- Run \`/deep clear-tasks\` to remove all tasks
- Create \`.deep/FORCE_EXIT\` to bypass the STOP hook

The session will continue. When you try to exit, pending tasks will be enforced.
`);
  }

  // Exit 0 to allow session to continue (just a notification)
  process.exit(0);
}

// Read hook input from stdin to get session_id
let hookInput = '';
process.stdin.setEncoding('utf8');

process.stdin.on('data', (chunk) => {
  hookInput += chunk;
});

process.stdin.on('end', () => {
  try {
    const input = JSON.parse(hookInput);
    // Initialize session-specific directory
    initDeepDir(input.session_id);
  } catch (e) {
    // No valid input, use legacy .deep directory
    initDeepDir(null);
  }
  main();
});

// Timeout - don't hang indefinitely waiting for stdin
setTimeout(() => {
  if (!hookInput) {
    // No stdin received, use legacy .deep directory
    initDeepDir(null);
    main();
  }
}, 3000);
