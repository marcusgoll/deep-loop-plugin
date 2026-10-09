#!/usr/bin/env node

/**
 * PostToolUse Validator Hook
 *
 * Runs after Edit/Write operations to validate file content.
 * Provides immediate feedback for syntax errors and warnings.
 *
 * Triggers on:
 * - Edit tool
 * - Write tool
 *
 * Validators:
 * - JSON: syntax, trailing commas, comments
 * - CSV: column consistency, encoding
 * - SQL: syntax, dangerous operations
 * - Markdown: frontmatter, links
 * - ENV: KEY=value format, duplicates
 * - TypeScript: tsc --noEmit (if available)
 * - Python: py_compile (if available)
 */

import fs from 'fs';
import path from 'path';
import { validate, formatResult } from './validators/index.js';

// State file for tracking validation across session
const STATE_DIR = '.deep';
const VALIDATION_STATE_FILE = path.join(STATE_DIR, 'validation-state.json');

// Read hook input from stdin
let hookInput = '';
process.stdin.setEncoding('utf8');

process.stdin.on('data', (chunk) => {
  hookInput += chunk;
});

process.stdin.on('end', async () => {
  try {
    await main(JSON.parse(hookInput));
  } catch (e) {
    // Silent fail - don't break the workflow
    process.exit(0);
  }
});

// Timeout - don't hang indefinitely
setTimeout(() => {
  process.exit(0);
}, 8000);

/**
 * Load validation state
 */
function loadValidationState() {
  try {
    if (fs.existsSync(VALIDATION_STATE_FILE)) {
      return JSON.parse(fs.readFileSync(VALIDATION_STATE_FILE, 'utf8'));
    }
  } catch {
    // Ignore
  }
  return {
    errors: [],
    warnings: [],
    lastValidated: null,
    filesValidated: 0
  };
}

/**
 * Save validation state
 */
function saveValidationState(state) {
  try {
    // Ensure directory exists
    if (!fs.existsSync(STATE_DIR)) {
      fs.mkdirSync(STATE_DIR, { recursive: true });
    }
    fs.writeFileSync(VALIDATION_STATE_FILE, JSON.stringify(state, null, 2));
  } catch {
    // Ignore
  }
}

/**
 * Add error to validation state
 */
function trackError(state, filePath, error) {
  const entry = {
    file: path.basename(filePath),
    fullPath: filePath,
    ...error,
    timestamp: new Date().toISOString()
  };

  // Avoid duplicates
  const existing = state.errors.findIndex(e =>
    e.fullPath === filePath && e.message === error.message
  );

  if (existing >= 0) {
    state.errors[existing] = entry; // Update timestamp
  } else {
    state.errors.push(entry);
  }

  // Keep only last 50 errors
  if (state.errors.length > 50) {
    state.errors = state.errors.slice(-50);
  }
}

/**
 * Clear errors for a file (when validation passes)
 */
function clearFileErrors(state, filePath) {
  state.errors = state.errors.filter(e => e.fullPath !== filePath);
}

/**
 * Main hook logic
 */
async function main(input) {
  // Check if this is an Edit or Write tool
  const toolName = input?.tool_name || '';

  if (toolName !== 'Edit' && toolName !== 'Write') {
    process.exit(0);
  }

  // Get the file path from tool input
  const filePath = input?.tool_input?.file_path;

  if (!filePath) {
    process.exit(0);
  }

  // Check if tool succeeded
  if (input?.tool_result?.is_error) {
    process.exit(0);
  }

  // Check if file exists
  if (!fs.existsSync(filePath)) {
    process.exit(0);
  }

  // Load validation state
  const state = loadValidationState();

  // Run validation
  const result = await validate(filePath);

  // Update state
  state.filesValidated++;
  state.lastValidated = new Date().toISOString();

  if (result.skipped) {
    // No output for skipped files
    process.exit(0);
  }

  // Track or clear errors
  if (result.errors.length > 0) {
    for (const error of result.errors) {
      trackError(state, filePath, error);
    }
  } else {
    clearFileErrors(state, filePath);
  }

  // Save state
  saveValidationState(state);

  // Format and output results
  const output = formatResult(filePath, result);

  if (output) {
    console.log(output);
  }

  // Exit with appropriate code
  // 0 = success (continue)
  // Note: We don't block on validation errors, just report them
  process.exit(0);
}
