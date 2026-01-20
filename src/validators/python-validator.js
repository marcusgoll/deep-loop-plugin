/**
 * Python Validator
 *
 * Validates Python syntax using py_compile.
 * Falls back to basic syntax checking if Python unavailable.
 */

import { execSync, spawnSync } from 'child_process';
import path from 'path';

/**
 * @param {string} filePath
 * @param {string} content
 * @param {object} settings
 * @returns {Promise<{valid: boolean, errors: Array, warnings: Array, suggestions: Array}>}
 */
export async function validatePython(filePath, content, settings) {
  const result = {
    valid: true,
    errors: [],
    warnings: [],
    suggestions: []
  };

  // Empty file check
  if (!content.trim()) {
    result.warnings.push({ message: 'Empty Python file' });
    return result;
  }

  // Try Python validation
  const pythonCmd = getPythonCommand();
  if (pythonCmd) {
    const pyResult = await runPythonValidation(filePath, pythonCmd, settings);
    if (pyResult.ran) {
      result.errors.push(...pyResult.errors);
      result.warnings.push(...pyResult.warnings);

      // Check imports if enabled and syntax is valid
      if (settings.checkImports !== false && pyResult.errors.length === 0) {
        checkImports(content, result);
      }

      return result;
    }
  }

  // Fallback to basic checking
  basicPythonCheck(content, result);

  return result;
}

/**
 * Get available Python command
 */
function getPythonCommand() {
  const candidates = process.platform === 'win32'
    ? ['python', 'python3', 'py']
    : ['python3', 'python'];

  for (const cmd of candidates) {
    try {
      const checkCmd = process.platform === 'win32' ? 'where' : 'which';
      const result = spawnSync(checkCmd, [cmd], {
        stdio: ['ignore', 'pipe', 'ignore'],
        timeout: 2000
      });
      if (result.status === 0) {
        return cmd;
      }
    } catch {
      continue;
    }
  }

  return null;
}

/**
 * Run Python syntax validation
 */
async function runPythonValidation(filePath, pythonCmd, settings) {
  const result = { ran: false, errors: [], warnings: [] };

  try {
    // Use py_compile module for syntax check
    const code = `
import py_compile
import sys
try:
    py_compile.compile(r'${filePath.replace(/'/g, "\\'")}', doraise=True)
    sys.exit(0)
except py_compile.PyCompileError as e:
    print(str(e), file=sys.stderr)
    sys.exit(1)
`;

    execSync(`${pythonCmd} -c "${code.replace(/"/g, '\\"').replace(/\n/g, ';')}"`, {
      cwd: path.dirname(filePath),
      stdio: ['ignore', 'pipe', 'pipe'],
      timeout: 5000
    });

    result.ran = true;
  } catch (err) {
    result.ran = true;

    // Parse error output
    const output = err.stderr?.toString() || err.stdout?.toString() || '';

    // Try to extract line number
    const lineMatch = output.match(/line\s+(\d+)/i);
    const line = lineMatch ? parseInt(lineMatch[1], 10) : null;

    // Try to extract the actual error type and message
    // Look for patterns like "SyntaxError: expected ':'" or "IndentationError: ..."
    const errorMatch = output.match(/(SyntaxError|IndentationError|TabError|NameError):\s*(.+?)(?:\r?\n|$)/);

    let message;
    if (errorMatch) {
      message = `${errorMatch[1]}: ${errorMatch[2].trim()}`;
    } else {
      // Fallback: clean up and get first meaningful line
      message = output.trim()
        .replace(/^Sorry:\s*/i, '')
        .replace(/File\s+"[^"]+",\s*/g, '')
        .split('\n')
        .filter(l => l.trim() && !l.includes('Traceback') && !l.includes('py_compile'))[0];
    }

    if (message) {
      result.errors.push({ line, message });
    } else {
      result.errors.push({ message: 'Python syntax error' });
    }
  }

  return result;
}

/**
 * Check for common import issues
 */
function checkImports(content, result) {
  const lines = content.split('\n');
  const imports = new Set();

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    const lineNum = i + 1;

    // Match import statements
    let match;

    // import x
    match = line.match(/^import\s+(\w+)/);
    if (match) {
      const module = match[1];
      if (imports.has(module)) {
        result.warnings.push({ line: lineNum, message: `Duplicate import: ${module}` });
      }
      imports.add(module);
      continue;
    }

    // from x import y
    match = line.match(/^from\s+(\S+)\s+import\s+(.+)/);
    if (match) {
      const [, module, names] = match;

      // Check for star import
      if (names.trim() === '*') {
        result.warnings.push({
          line: lineNum,
          message: `Star import from ${module} - consider explicit imports`
        });
      }

      // Check for duplicate module imports
      if (imports.has(`from:${module}`)) {
        result.suggestions.push(`Line ${lineNum}: Multiple imports from ${module} - consider consolidating`);
      }
      imports.add(`from:${module}`);
    }
  }
}

/**
 * Basic Python syntax checking without interpreter
 */
function basicPythonCheck(content, result) {
  const lines = content.split('\n');

  // Track indentation
  let prevIndent = 0;
  let indentStack = [0];
  let inMultiString = null;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const lineNum = i + 1;

    // Handle multi-line strings
    const tripleDouble = (line.match(/"""/g) || []).length;
    const tripleSingle = (line.match(/'''/g) || []).length;

    if (inMultiString) {
      if ((inMultiString === '"""' && tripleDouble % 2 === 1) ||
          (inMultiString === "'''" && tripleSingle % 2 === 1)) {
        inMultiString = null;
      }
      continue;
    }

    if (tripleDouble % 2 === 1) {
      inMultiString = '"""';
      continue;
    }
    if (tripleSingle % 2 === 1) {
      inMultiString = "'''";
      continue;
    }

    // Skip empty lines and comments
    if (!line.trim() || line.trim().startsWith('#')) {
      continue;
    }

    // Check indentation
    const indent = line.match(/^(\s*)/)[1].length;

    // Check for mixed tabs and spaces
    const leadingWhitespace = line.match(/^(\s*)/)[1];
    if (leadingWhitespace.includes('\t') && leadingWhitespace.includes(' ')) {
      result.errors.push({
        line: lineNum,
        message: 'Mixed tabs and spaces in indentation'
      });
    }

    // Check for mismatched brackets on single lines
    const brackets = { '(': 0, '[': 0, '{': 0 };
    let inString = null;

    for (let j = 0; j < line.length; j++) {
      const char = line[j];
      const prev = line[j - 1];

      // Handle strings
      if ((char === '"' || char === "'") && prev !== '\\') {
        if (inString === null) {
          inString = char;
        } else if (inString === char) {
          inString = null;
        }
        continue;
      }

      if (inString) continue;

      // Track brackets
      if (char === '(') brackets['(']++;
      if (char === ')') brackets['(']--;
      if (char === '[') brackets['[']++;
      if (char === ']') brackets['[']--;
      if (char === '{') brackets['{']++;
      if (char === '}') brackets['{']--;
    }

    // Check for obvious colon issues
    const colonKeywords = ['if', 'elif', 'else', 'for', 'while', 'try', 'except',
                          'finally', 'with', 'def', 'class', 'async'];

    for (const kw of colonKeywords) {
      const kwRegex = new RegExp(`^\\s*${kw}\\b`);
      if (kwRegex.test(line) && !line.trimEnd().endsWith(':')) {
        // Check if brackets are balanced (might be multi-line)
        const allBalanced = Object.values(brackets).every(v => v === 0);
        if (allBalanced) {
          result.errors.push({
            line: lineNum,
            message: `Missing colon after '${kw}' statement`
          });
        }
      }
    }
  }

  if (inMultiString) {
    result.errors.push({ message: `Unclosed multi-line string (${inMultiString})` });
  }
}
