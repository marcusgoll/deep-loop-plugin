#!/usr/bin/env node

/**
 * PostToolUse Hook - Auto-format code after Edit/Write operations
 *
 * Handles the "last 10%" of code formatting that Claude sometimes misses.
 * Runs formatters on files after they're written to avoid CI formatting errors.
 *
 * Triggers on:
 * - Edit tool
 * - Write tool
 *
 * Formatters (in order of preference):
 * - prettier (JS/TS/JSON/MD/CSS/HTML)
 * - biome (JS/TS)
 * - eslint --fix (JS/TS)
 * - ruff format (Python)
 * - gofmt (Go)
 * - rustfmt (Rust)
 */

import fs from 'fs';
import path from 'path';
import { execSync, spawnSync } from 'child_process';

// Read hook input from stdin
let hookInput = '';
process.stdin.setEncoding('utf8');

process.stdin.on('data', (chunk) => {
  hookInput += chunk;
});

process.stdin.on('end', () => {
  try {
    main(JSON.parse(hookInput));
  } catch (e) {
    // Silent fail - don't break the workflow
    process.exit(0);
  }
});

// Timeout - don't hang indefinitely
setTimeout(() => {
  process.exit(0);
}, 5000);

/**
 * Check if a command exists
 */
function commandExists(cmd) {
  try {
    const result = spawnSync(process.platform === 'win32' ? 'where' : 'which', [cmd], {
      stdio: ['ignore', 'pipe', 'ignore'],
      timeout: 2000
    });
    return result.status === 0;
  } catch {
    return false;
  }
}

/**
 * Run a formatter command
 */
function runFormatter(cmd, args, cwd) {
  try {
    execSync(`${cmd} ${args.join(' ')}`, {
      cwd,
      stdio: 'ignore',
      timeout: 10000
    });
    return true;
  } catch {
    return false;
  }
}

/**
 * Check if prettier is configured for a project
 */
function hasPrettierConfig(dir) {
  const configs = [
    '.prettierrc',
    '.prettierrc.js',
    '.prettierrc.json',
    '.prettierrc.yaml',
    '.prettierrc.yml',
    'prettier.config.js',
    'prettier.config.mjs'
  ];

  for (const config of configs) {
    if (fs.existsSync(path.join(dir, config))) {
      return true;
    }
  }

  // Check package.json for prettier config
  try {
    const pkg = JSON.parse(fs.readFileSync(path.join(dir, 'package.json'), 'utf8'));
    if (pkg.prettier) return true;
  } catch {
    // No package.json or no prettier field
  }

  return false;
}

/**
 * Check if biome is configured for a project
 */
function hasBiomeConfig(dir) {
  return fs.existsSync(path.join(dir, 'biome.json')) ||
         fs.existsSync(path.join(dir, 'biome.jsonc'));
}

/**
 * Get project root (look for package.json, go.mod, Cargo.toml, etc.)
 */
function findProjectRoot(filePath) {
  let dir = path.dirname(filePath);
  const root = path.parse(dir).root;

  while (dir !== root) {
    if (fs.existsSync(path.join(dir, 'package.json')) ||
        fs.existsSync(path.join(dir, 'go.mod')) ||
        fs.existsSync(path.join(dir, 'Cargo.toml')) ||
        fs.existsSync(path.join(dir, 'pyproject.toml')) ||
        fs.existsSync(path.join(dir, '.git'))) {
      return dir;
    }
    dir = path.dirname(dir);
  }

  return path.dirname(filePath);
}

/**
 * Format a file based on its extension
 */
function formatFile(filePath) {
  if (!fs.existsSync(filePath)) return;

  const ext = path.extname(filePath).toLowerCase();
  const projectRoot = findProjectRoot(filePath);
  const relativePath = path.relative(projectRoot, filePath);

  // JavaScript/TypeScript files
  if (['.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs'].includes(ext)) {
    // Try prettier first (most common)
    if (hasPrettierConfig(projectRoot) && commandExists('npx')) {
      if (runFormatter('npx', ['prettier', '--write', relativePath], projectRoot)) {
        return;
      }
    }

    // Try biome
    if (hasBiomeConfig(projectRoot) && commandExists('npx')) {
      if (runFormatter('npx', ['biome', 'format', '--write', relativePath], projectRoot)) {
        return;
      }
    }

    // Try eslint --fix as fallback
    if (fs.existsSync(path.join(projectRoot, '.eslintrc.js')) ||
        fs.existsSync(path.join(projectRoot, '.eslintrc.json')) ||
        fs.existsSync(path.join(projectRoot, 'eslint.config.js'))) {
      if (commandExists('npx')) {
        runFormatter('npx', ['eslint', '--fix', relativePath], projectRoot);
      }
    }
    return;
  }

  // JSON files
  if (ext === '.json') {
    if (hasPrettierConfig(projectRoot) && commandExists('npx')) {
      runFormatter('npx', ['prettier', '--write', relativePath], projectRoot);
    }
    return;
  }

  // Markdown files
  if (ext === '.md') {
    if (hasPrettierConfig(projectRoot) && commandExists('npx')) {
      runFormatter('npx', ['prettier', '--write', relativePath], projectRoot);
    }
    return;
  }

  // CSS/SCSS/Less
  if (['.css', '.scss', '.less', '.sass'].includes(ext)) {
    if (hasPrettierConfig(projectRoot) && commandExists('npx')) {
      runFormatter('npx', ['prettier', '--write', relativePath], projectRoot);
    }
    return;
  }

  // Python files
  if (ext === '.py') {
    // Try ruff first (fast)
    if (commandExists('ruff')) {
      if (runFormatter('ruff', ['format', filePath], projectRoot)) {
        return;
      }
    }
    // Try black as fallback
    if (commandExists('black')) {
      runFormatter('black', [filePath], projectRoot);
    }
    return;
  }

  // Go files
  if (ext === '.go') {
    if (commandExists('gofmt')) {
      runFormatter('gofmt', ['-w', filePath], projectRoot);
    }
    return;
  }

  // Rust files
  if (ext === '.rs') {
    if (commandExists('rustfmt')) {
      runFormatter('rustfmt', [filePath], projectRoot);
    }
    return;
  }
}

/**
 * Main hook logic
 */
function main(input) {
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

  // Skip formatting for certain directories
  const skipDirs = ['node_modules', '.git', 'dist', 'build', '.next', '__pycache__', 'venv'];
  if (skipDirs.some(dir => filePath.includes(path.sep + dir + path.sep))) {
    process.exit(0);
  }

  // Skip non-code files
  const codeExtensions = ['.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs', '.json', '.md',
                          '.css', '.scss', '.less', '.py', '.go', '.rs', '.html'];
  const ext = path.extname(filePath).toLowerCase();
  if (!codeExtensions.includes(ext)) {
    process.exit(0);
  }

  // Format the file
  formatFile(filePath);

  process.exit(0);
}
