/**
 * ENV Validator
 *
 * Validates .env file format.
 */

/**
 * @param {string} filePath
 * @param {string} content
 * @param {object} settings
 * @returns {Promise<{valid: boolean, errors: Array, warnings: Array, suggestions: Array}>}
 */
export async function validateEnv(filePath, content, settings) {
  const result = {
    valid: true,
    errors: [],
    warnings: [],
    suggestions: []
  };

  // Empty file is OK for env
  if (!content.trim()) {
    return result;
  }

  const lines = content.split(/\r?\n/);
  const keys = new Set();

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].replace(/\r$/, '');
    const lineNum = i + 1;

    // Skip empty lines and comments
    if (!line.trim() || line.trim().startsWith('#')) {
      continue;
    }

    // Check for valid KEY=value format
    const match = line.match(/^([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$/);

    if (!match) {
      // Check for common issues
      if (line.includes('=')) {
        const keyPart = line.split('=')[0];
        if (/^\d/.test(keyPart.trim())) {
          result.errors.push({
            line: lineNum,
            message: 'Variable name cannot start with a number'
          });
        } else if (/[^A-Za-z0-9_]/.test(keyPart.trim())) {
          result.errors.push({
            line: lineNum,
            message: 'Variable name contains invalid characters (use A-Z, 0-9, _)'
          });
        } else {
          result.errors.push({
            line: lineNum,
            message: 'Invalid KEY=value format'
          });
        }
      } else {
        result.errors.push({
          line: lineNum,
          message: 'Missing = sign - expected KEY=value format'
        });
      }
      continue;
    }

    const [, key, value] = match;

    // Check for duplicate keys
    if (keys.has(key)) {
      result.warnings.push({
        line: lineNum,
        message: `Duplicate key: ${key}`
      });
    }
    keys.add(key);

    // Check for empty value (if setting enabled)
    if (settings.warnOnMissingValue !== false && !value.trim()) {
      result.warnings.push({
        line: lineNum,
        message: `Empty value for: ${key}`
      });
    }

    // Check for unquoted values with spaces
    if (value.includes(' ') && !value.startsWith('"') && !value.startsWith("'")) {
      result.warnings.push({
        line: lineNum,
        message: `Value contains spaces but is not quoted: ${key}`
      });
    }

    // Check for mismatched quotes
    if ((value.startsWith('"') && !value.endsWith('"')) ||
        (value.startsWith("'") && !value.endsWith("'"))) {
      result.errors.push({
        line: lineNum,
        message: `Mismatched quotes in value: ${key}`
      });
    }

    // Warn about sensitive-looking keys with placeholder values
    const sensitivePatterns = ['PASSWORD', 'SECRET', 'KEY', 'TOKEN', 'CREDENTIAL'];
    const isSensitive = sensitivePatterns.some(p => key.toUpperCase().includes(p));

    if (isSensitive) {
      // Check for example/placeholder values
      const placeholders = ['your_', 'xxx', 'changeme', 'example', 'placeholder', '...'];
      const isPlaceholder = placeholders.some(p => value.toLowerCase().includes(p));

      if (isPlaceholder) {
        result.suggestions.push(`Line ${lineNum}: ${key} appears to have a placeholder value`);
      }
    }
  }

  return result;
}
