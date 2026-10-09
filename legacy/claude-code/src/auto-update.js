#!/usr/bin/env node

/**
 * Deep Loop Auto-Update Hook
 *
 * Runs on session start to check for plugin updates.
 * Only updates if a git remote is configured.
 */

import { execSync } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PLUGIN_ROOT = path.resolve(__dirname, '..');

function exec(cmd) {
  try {
    return execSync(cmd, {
      cwd: PLUGIN_ROOT,
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe']
    }).trim();
  } catch (e) {
    return null;
  }
}

function checkForUpdates() {
  // Check if git repo
  const isGitRepo = exec('git rev-parse --git-dir');
  if (!isGitRepo) {
    return { status: 'not_git', message: null };
  }

  // Check if remote configured
  const remote = exec('git remote');
  if (!remote) {
    return { status: 'no_remote', message: null };
  }

  // Fetch latest
  const fetchResult = exec('git fetch --quiet');
  if (fetchResult === null) {
    return { status: 'fetch_failed', message: 'Could not fetch updates' };
  }

  // Check if behind
  const localHead = exec('git rev-parse HEAD');
  const remoteHead = exec(`git rev-parse ${remote}/master 2>/dev/null || git rev-parse ${remote}/main 2>/dev/null`);

  if (!remoteHead) {
    return { status: 'no_remote_branch', message: null };
  }

  if (localHead === remoteHead) {
    return { status: 'up_to_date', message: null };
  }

  // Check if we're behind (remote has commits we don't have)
  const behind = exec(`git rev-list --count HEAD..${remote}/master 2>/dev/null || git rev-list --count HEAD..${remote}/main 2>/dev/null`);

  if (behind && parseInt(behind) > 0) {
    // Pull updates
    const pullResult = exec('git pull --ff-only --quiet');
    if (pullResult !== null) {
      // Get new version
      const newVersion = exec('grep -o \'"version": *"[^"]*"\' plugin.json | cut -d\'"\' -f4') || 'unknown';
      return {
        status: 'updated',
        message: `Deep Loop updated to v${newVersion}`
      };
    } else {
      return {
        status: 'pull_failed',
        message: 'Updates available but pull failed (local changes?)'
      };
    }
  }

  return { status: 'up_to_date', message: null };
}

// Run update check
const result = checkForUpdates();

if (result.message) {
  console.log(`[deep-loop] ${result.message}`);
}

// Always exit cleanly - don't block session start
process.exit(0);
