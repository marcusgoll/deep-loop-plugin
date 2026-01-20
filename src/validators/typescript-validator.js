/**
 * TypeScript Validator
 *
 * Quick syntax validation using tsc --noEmit for single files.
 * Falls back to basic syntax checking if tsc unavailable.
 */

import { execSync, spawnSync } from 'child_process';
import path from 'path';
import fs from 'fs';

/**
 * @param {string} filePath
 * @param {string} content
 * @param {object} settings
 * @returns {Promise<{valid: boolean, errors: Array, warnings: Array, suggestions: Array}>}
 */
export async function validateTypescript(filePath, content, settings) {
  const result = {
    valid: true,
    errors: [],
    warnings: [],
    suggestions: []
  };

  // Empty file check
  if (!content.trim()) {
    result.warnings.push({ message: 'Empty TypeScript file' });
    return result;
  }

  // Try tsc validation first
  if (hasTsc()) {
    const tscResult = await runTscValidation(filePath, settings);
    if (tscResult.ran && (tscResult.errors.length > 0 || tscResult.warnings.length > 0)) {
      result.errors.push(...tscResult.errors);
      result.warnings.push(...tscResult.warnings);
      return result;
    }
  }

  // Always run basic syntax checking as fallback or sanity check
  basicSyntaxCheck(content, result);

  return result;
}

/**
 * Check if tsc is available
 */
function hasTsc() {
  try {
    const cmd = process.platform === 'win32' ? 'where' : 'which';
    const result = spawnSync(cmd, ['tsc'], {
      stdio: ['ignore', 'pipe', 'ignore'],
      timeout: 2000
    });
    return result.status === 0;
  } catch {
    return false;
  }
}

/**
 * Run tsc --noEmit on the file
 */
async function runTscValidation(filePath, settings) {
  const result = { ran: false, errors: [], warnings: [] };

  try {
    // Find project root with tsconfig
    const projectRoot = findTsConfig(filePath);

    const args = ['--noEmit', '--pretty', 'false'];

    if (projectRoot && settings.useProjectConfig !== false) {
      args.push('--project', `"${path.join(projectRoot, 'tsconfig.json')}"`);
      // Only check the specific file
      args.push(`"${filePath}"`);
    } else {
      // Standalone check with lenient settings
      args.push(
        '--target', 'ES2020',
        '--module', 'ESNext',
        '--moduleResolution', 'node',
        '--esModuleInterop', 'true',
        '--skipLibCheck', 'true',
        '--noImplicitAny', 'false',
        `"${filePath}"`
      );
    }

    execSync(`tsc ${args.join(' ')}`, {
      cwd: path.dirname(filePath),
      stdio: ['ignore', 'pipe', 'pipe'],
      timeout: 5000
    });

    result.ran = true;
  } catch (err) {
    result.ran = true;

    // Parse tsc output
    const output = err.stderr?.toString() || err.stdout?.toString() || '';
    const lines = output.split('\n').filter(l => l.trim());

    for (const line of lines) {
      // Format: file(line,col): error TS1234: message
      const match = line.match(/\((\d+),\d+\):\s*(error|warning)\s+TS\d+:\s*(.+)/);
      if (match) {
        const [, lineNum, type, message] = match;
        const issue = { line: parseInt(lineNum, 10), message };

        if (type === 'error') {
          result.errors.push(issue);
        } else {
          result.warnings.push(issue);
        }
      } else if (line.includes('error TS')) {
        // General error without line number
        result.errors.push({ message: line.trim() });
      }
    }

    // Limit errors to avoid noise
    if (result.errors.length > 10) {
      const count = result.errors.length;
      result.errors = result.errors.slice(0, 10);
      result.errors.push({ message: `... and ${count - 10} more errors` });
    }
  }

  return result;
}

/**
 * Find directory with tsconfig.json
 */
function findTsConfig(filePath) {
  let dir = path.dirname(filePath);
  const root = path.parse(dir).root;

  while (dir !== root) {
    if (fs.existsSync(path.join(dir, 'tsconfig.json'))) {
      return dir;
    }
    dir = path.dirname(dir);
  }

  return null;
}

/**
 * Basic syntax checking without tsc
 */
function basicSyntaxCheck(content, result) {
  const lines = content.split('\n');

  // Track brackets
  let braceDepth = 0;
  let bracketDepth = 0;
  let parenDepth = 0;
  let inString = null;
  let inTemplate = false;
  let inMultiComment = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const lineNum = i + 1;

    for (let j = 0; j < line.length; j++) {
      const char = line[j];
      const prev = line[j - 1];

      // Handle multi-line comments
      if (inMultiComment) {
        if (char === '/' && prev === '*') {
          inMultiComment = false;
        }
        continue;
      }

      if (char === '*' && prev === '/') {
        inMultiComment = true;
        continue;
      }

      // Skip single-line comments
      if (char === '/' && line[j + 1] === '/') {
        break;
      }

      // Handle strings
      if ((char === '"' || char === "'" || char === '`') && prev !== '\\') {
        if (inString === null) {
          inString = char;
          inTemplate = char === '`';
        } else if (inString === char) {
          inString = null;
          inTemplate = false;
        }
        continue;
      }

      // Skip if in string (except for template expressions)
      if (inString !== null && !(inTemplate && char === '$' && line[j + 1] === '{')) {
        continue;
      }

      // Track brackets
      if (char === '{') braceDepth++;
      if (char === '}') braceDepth--;
      if (char === '[') bracketDepth++;
      if (char === ']') bracketDepth--;
      if (char === '(') parenDepth++;
      if (char === ')') parenDepth--;

      // Check for immediate imbalance
      if (braceDepth < 0) {
        result.errors.push({ line: lineNum, message: 'Unmatched closing brace }' });
        braceDepth = 0;
      }
      if (bracketDepth < 0) {
        result.errors.push({ line: lineNum, message: 'Unmatched closing bracket ]' });
        bracketDepth = 0;
      }
      if (parenDepth < 0) {
        result.errors.push({ line: lineNum, message: 'Unmatched closing parenthesis )' });
        parenDepth = 0;
      }
    }
  }

  // Final balance check
  if (braceDepth > 0) {
    result.errors.push({ message: `Unclosed braces: ${braceDepth} open` });
  }
  if (bracketDepth > 0) {
    result.errors.push({ message: `Unclosed brackets: ${bracketDepth} open` });
  }
  if (parenDepth > 0) {
    result.errors.push({ message: `Unclosed parentheses: ${parenDepth} open` });
  }
  if (inString !== null) {
    result.errors.push({ message: `Unclosed string literal (${inString})` });
  }
  if (inMultiComment) {
    result.errors.push({ message: 'Unclosed multi-line comment' });
  }
}
