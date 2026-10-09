/**
 * Markdown Validator
 *
 * Validates YAML frontmatter and checks for broken links.
 */

/**
 * @param {string} filePath
 * @param {string} content
 * @param {object} settings
 * @returns {Promise<{valid: boolean, errors: Array, warnings: Array, suggestions: Array}>}
 */
export async function validateMarkdown(filePath, content, settings) {
  const result = {
    valid: true,
    errors: [],
    warnings: [],
    suggestions: []
  };

  // Empty file check
  if (!content.trim()) {
    result.warnings.push({ message: 'Empty markdown file' });
    return result;
  }

  // Check frontmatter if enabled
  if (settings.checkFrontmatter !== false) {
    checkFrontmatter(content, result);
  }

  // Check links if enabled
  if (settings.checkLinks !== false) {
    checkLinks(content, result);
  }

  // Check for common markdown issues
  checkMarkdownIssues(content, result);

  return result;
}

/**
 * Validate YAML frontmatter
 */
function checkFrontmatter(content, result) {
  // Check if file starts with frontmatter
  if (!content.startsWith('---')) {
    return; // No frontmatter, that's fine
  }

  // Find closing delimiter
  const endMatch = content.substring(3).match(/\r?\n---(\r?\n|$)/);
  if (!endMatch) {
    result.errors.push({
      line: 1,
      message: 'Unclosed YAML frontmatter - missing closing ---'
    });
    return;
  }

  const frontmatter = content.substring(3, 3 + endMatch.index);
  const lines = frontmatter.split('\n');

  // Basic YAML validation
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const lineNum = i + 2; // Account for opening ---

    // Skip empty lines and comments
    if (!line.trim() || line.trim().startsWith('#')) continue;

    // Check for tabs (YAML uses spaces)
    if (line.startsWith('\t')) {
      result.errors.push({
        line: lineNum,
        message: 'YAML uses spaces for indentation, not tabs'
      });
    }

    // Check for missing colon in key-value
    if (!line.includes(':') && !line.trim().startsWith('-') && line.trim()) {
      // Might be a continuation, check indent
      const indent = line.match(/^\s*/)[0].length;
      if (indent === 0) {
        result.warnings.push({
          line: lineNum,
          message: 'Line may be missing colon for key-value pair'
        });
      }
    }

    // Check for duplicate keys (simple check)
    const keyMatch = line.match(/^(\s*)([^:\s]+)\s*:/);
    if (keyMatch && keyMatch[1] === '') {
      const key = keyMatch[2];
      const regex = new RegExp(`^${key}\\s*:`, 'm');
      const firstMatch = frontmatter.search(regex);
      const lastMatch = frontmatter.lastIndexOf(`${key}:`);
      if (firstMatch !== lastMatch) {
        result.warnings.push({
          line: lineNum,
          message: `Duplicate frontmatter key: "${key}"`
        });
      }
    }
  }
}

/**
 * Check for broken or suspicious links
 */
function checkLinks(content, result) {
  // Match markdown links: [text](url)
  const linkRegex = /\[([^\]]*)\]\(([^)]+)\)/g;
  let match;

  while ((match = linkRegex.exec(content)) !== null) {
    const [, text, url] = match;
    const line = content.substring(0, match.index).split('\n').length;

    // Check for empty URLs
    if (!url.trim()) {
      result.errors.push({ line, message: 'Empty link URL' });
      continue;
    }

    // Check for placeholder URLs
    if (/^(#|javascript:|TODO|FIXME|TBD)/i.test(url.trim())) {
      result.warnings.push({ line, message: `Placeholder link: "${url}"` });
      continue;
    }

    // Check for spaces in URL (should be encoded)
    if (url.includes(' ') && !url.startsWith('<')) {
      result.warnings.push({ line, message: 'Link URL contains spaces - should be encoded' });
    }

    // Check for relative paths that go too deep
    if (url.startsWith('../../../')) {
      result.suggestions.push(`Line ${line}: Deep relative path - consider absolute path`);
    }
  }

  // Match reference-style links: [text][ref]
  const refLinks = content.match(/\[[^\]]+\]\[[^\]]*\]/g) || [];
  const refDefs = content.match(/^\[[^\]]+\]:\s*.+$/gm) || [];

  // Check for undefined references
  for (const refLink of refLinks) {
    const refMatch = refLink.match(/\[[^\]]+\]\[([^\]]*)\]/);
    if (refMatch && refMatch[1]) {
      const ref = refMatch[1].toLowerCase();
      const isDefined = refDefs.some(def =>
        def.toLowerCase().startsWith(`[${ref}]:`)
      );
      if (!isDefined) {
        result.warnings.push({ message: `Undefined link reference: [${refMatch[1]}]` });
      }
    }
  }
}

/**
 * Check for common markdown issues
 */
function checkMarkdownIssues(content, result) {
  const lines = content.split('\n');

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const lineNum = i + 1;

    // Multiple blank lines
    if (line.trim() === '' && lines[i + 1]?.trim() === '' && lines[i + 2]?.trim() === '') {
      result.suggestions.push(`Line ${lineNum}: Multiple consecutive blank lines`);
    }

    // Trailing spaces (except for intentional line breaks)
    if (line.endsWith(' ') && !line.endsWith('  ')) {
      // Single trailing space is usually unintentional
      // Double space is intentional line break
      // Skip this as it's too noisy
    }

    // Header without space after #
    if (/^#+[^#\s]/.test(line)) {
      result.warnings.push({ line: lineNum, message: 'Header missing space after #' });
    }
  }
}
