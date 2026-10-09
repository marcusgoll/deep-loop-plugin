/**
 * JSON Validator
 *
 * Validates JSON syntax and common issues.
 */

/**
 * @param {string} filePath
 * @param {string} content
 * @param {object} settings
 * @returns {Promise<{valid: boolean, errors: Array, warnings: Array, suggestions: Array}>}
 */
export async function validateJson(filePath, content, settings) {
  const result = {
    valid: true,
    errors: [],
    warnings: [],
    suggestions: []
  };

  // Empty file check
  if (!content.trim()) {
    result.errors.push({ message: 'Empty JSON file' });
    return result;
  }

  // Try to parse
  try {
    JSON.parse(content);
  } catch (err) {
    // Extract line number from error if available
    const lineMatch = err.message.match(/position (\d+)/);
    let line = null;

    if (lineMatch) {
      const pos = parseInt(lineMatch[1], 10);
      line = content.substring(0, pos).split('\n').length;
    }

    result.errors.push({
      line,
      message: err.message
    });

    // Check for common issues
    const issues = detectCommonJsonIssues(content);
    result.suggestions.push(...issues);

    return result;
  }

  // Additional checks for valid JSON
  const warnings = checkJsonWarnings(content, filePath);
  result.warnings.push(...warnings);

  return result;
}

/**
 * Detect common JSON syntax issues
 */
function detectCommonJsonIssues(content) {
  const suggestions = [];
  const lines = content.split('\n');

  // Trailing commas
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    // Match trailing comma before ] or }
    if (/,\s*$/.test(line)) {
      const nextLine = lines[i + 1]?.trim() || '';
      if (nextLine.startsWith(']') || nextLine.startsWith('}')) {
        suggestions.push(`Line ${i + 1}: Trailing comma before closing bracket`);
      }
    }
  }

  // Single quotes instead of double
  if (/'[^']*'\s*:/.test(content)) {
    suggestions.push('Use double quotes for keys, not single quotes');
  }

  // Comments
  if (/\/\/|\/\*/.test(content)) {
    suggestions.push('JSON does not support comments - use JSONC or remove');
  }

  // Unquoted keys
  if (/^\s*[a-zA-Z_][a-zA-Z0-9_]*\s*:/m.test(content)) {
    suggestions.push('Keys must be quoted in JSON');
  }

  return suggestions;
}

/**
 * Check for warnings in valid JSON
 */
function checkJsonWarnings(content, filePath) {
  const warnings = [];

  // Check for potential secrets in certain files
  const sensitivePatterns = [
    /password/i,
    /api_?key/i,
    /secret/i,
    /token/i,
    /private_?key/i
  ];

  // Only warn for non-schema, non-config files
  const isSafeFile = /schema|config\.example|template/i.test(filePath);

  if (!isSafeFile) {
    for (const pattern of sensitivePatterns) {
      if (pattern.test(content)) {
        // Check if it's a placeholder value
        const match = content.match(new RegExp(`"[^"]*${pattern.source}[^"]*"\\s*:\\s*"([^"]*)"`, 'i'));
        if (match && match[1] && !/^\s*$|your_|<|placeholder|example|\*+/i.test(match[1])) {
          warnings.push({
            message: `Possible sensitive data: key matching "${pattern.source}"`
          });
          break;
        }
      }
    }
  }

  // Very large arrays (performance warning)
  const arrayMatches = content.match(/\[[\s\S]*?\]/g) || [];
  for (const arr of arrayMatches) {
    const itemCount = (arr.match(/,/g) || []).length + 1;
    if (itemCount > 1000) {
      warnings.push({ message: `Large array detected (${itemCount}+ items) - consider pagination` });
      break;
    }
  }

  return warnings;
}
