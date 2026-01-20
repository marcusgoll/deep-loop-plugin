/**
 * SQL Validator
 *
 * Basic SQL syntax checking and dangerous operation warnings.
 */

/**
 * @param {string} filePath
 * @param {string} content
 * @param {object} settings
 * @returns {Promise<{valid: boolean, errors: Array, warnings: Array, suggestions: Array}>}
 */
export async function validateSql(filePath, content, settings) {
  const result = {
    valid: true,
    errors: [],
    warnings: [],
    suggestions: []
  };

  // Empty file check
  if (!content.trim()) {
    result.warnings.push({ message: 'Empty SQL file' });
    return result;
  }

  // Normalize content for analysis
  const normalized = content.toUpperCase();
  const lines = content.split('\n');

  // Check for dangerous operations
  const dangerousKeywords = settings.dangerousKeywords || [
    'DROP',
    'TRUNCATE',
    'DELETE FROM',
    'ALTER TABLE DROP'
  ];

  for (const keyword of dangerousKeywords) {
    const regex = new RegExp(`\\b${keyword}\\b`, 'gi');
    let match;

    while ((match = regex.exec(content)) !== null) {
      const pos = match.index;
      const line = content.substring(0, pos).split('\n').length;

      // Check if it's in a comment
      const lineContent = lines[line - 1] || '';
      if (isInComment(lineContent, match.index - content.lastIndexOf('\n', pos) - 1)) {
        continue;
      }

      result.warnings.push({
        line,
        message: `Dangerous operation: ${keyword}`
      });
    }
  }

  // Check for potential SQL injection vectors
  checkInjectionRisks(content, result);

  // Basic syntax checks
  checkSqlSyntax(content, result);

  // Check for missing WHERE on UPDATE/DELETE
  checkMissingWhere(content, result);

  return result;
}

/**
 * Check if position is inside a SQL comment
 */
function isInComment(line, pos) {
  // Single line comment
  const dashComment = line.indexOf('--');
  if (dashComment !== -1 && dashComment < pos) return true;

  // Could extend to check /* */ but that's more complex
  return false;
}

/**
 * Check for SQL injection risks
 */
function checkInjectionRisks(content, result) {
  // String concatenation patterns that might indicate injection risk
  const riskPatterns = [
    { pattern: /\+\s*['"].*['"].*\+/g, msg: 'String concatenation in query - use parameterized queries' },
    { pattern: /\$\{[^}]+\}/g, msg: 'Template literal in SQL - ensure proper escaping' },
    { pattern: /%s|%d/g, msg: 'Format string in SQL - use parameterized queries' }
  ];

  for (const { pattern, msg } of riskPatterns) {
    if (pattern.test(content)) {
      result.suggestions.push(msg);
    }
  }
}

/**
 * Basic SQL syntax validation
 */
function checkSqlSyntax(content, result) {
  const lines = content.split('\n');

  // Track parentheses balance
  let parenDepth = 0;
  let quoteChar = null;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Skip comment-only lines
    if (line.trim().startsWith('--')) continue;

    for (let j = 0; j < line.length; j++) {
      const char = line[j];

      // Handle quotes
      if ((char === "'" || char === '"') && (j === 0 || line[j - 1] !== '\\')) {
        if (quoteChar === null) {
          quoteChar = char;
        } else if (quoteChar === char) {
          quoteChar = null;
        }
        continue;
      }

      // Skip if in string
      if (quoteChar !== null) continue;

      // Track parentheses
      if (char === '(') parenDepth++;
      if (char === ')') parenDepth--;

      if (parenDepth < 0) {
        result.errors.push({
          line: i + 1,
          message: 'Unmatched closing parenthesis'
        });
        parenDepth = 0; // Reset to continue checking
      }
    }
  }

  if (parenDepth > 0) {
    result.errors.push({ message: `Unclosed parentheses: ${parenDepth} open` });
  }

  if (quoteChar !== null) {
    result.errors.push({ message: `Unclosed string literal (${quoteChar})` });
  }
}

/**
 * Check for UPDATE/DELETE without WHERE
 */
function checkMissingWhere(content, result) {
  // Split into statements
  const statements = content.split(/;/);

  for (const stmt of statements) {
    const normalized = stmt.toUpperCase().trim();

    // Check UPDATE without WHERE
    if (/^\s*UPDATE\b/i.test(stmt) && !/\bWHERE\b/i.test(stmt)) {
      result.warnings.push({
        message: 'UPDATE without WHERE clause - will affect all rows'
      });
    }

    // Check DELETE without WHERE
    if (/^\s*DELETE\s+FROM\b/i.test(stmt) && !/\bWHERE\b/i.test(stmt)) {
      result.warnings.push({
        message: 'DELETE without WHERE clause - will delete all rows'
      });
    }
  }
}
