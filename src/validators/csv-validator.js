/**
 * CSV Validator
 *
 * Validates CSV structure and column consistency.
 */

/**
 * @param {string} filePath
 * @param {string} content
 * @param {object} settings
 * @returns {Promise<{valid: boolean, errors: Array, warnings: Array, suggestions: Array}>}
 */
export async function validateCsv(filePath, content, settings) {
  const result = {
    valid: true,
    errors: [],
    warnings: [],
    suggestions: []
  };

  // Empty file check
  if (!content.trim()) {
    result.warnings.push({ message: 'Empty CSV file' });
    return result;
  }

  // Detect delimiter
  const delimiter = detectDelimiter(content, filePath);

  // Parse rows
  const lines = content.split(/\r?\n/).filter(line => line.trim());

  if (lines.length === 0) {
    result.warnings.push({ message: 'No data rows in CSV' });
    return result;
  }

  // Get header column count
  const headerCols = parseRow(lines[0], delimiter).length;

  if (headerCols === 0) {
    result.errors.push({ line: 1, message: 'Empty header row' });
    return result;
  }

  // Check for duplicate headers
  const headers = parseRow(lines[0], delimiter);
  const headerSet = new Set();
  for (const header of headers) {
    const normalized = header.trim().toLowerCase();
    if (headerSet.has(normalized) && normalized !== '') {
      result.warnings.push({ line: 1, message: `Duplicate header: "${header}"` });
    }
    headerSet.add(normalized);
  }

  // Check data rows (limited by settings)
  const maxRows = settings.maxRowsToCheck || 100;
  const rowsToCheck = Math.min(lines.length, maxRows);

  for (let i = 1; i < rowsToCheck; i++) {
    const row = lines[i];
    const cols = parseRow(row, delimiter);

    // Empty row check
    if (cols.length === 1 && cols[0].trim() === '') {
      result.warnings.push({ line: i + 1, message: 'Empty row detected' });
      continue;
    }

    // Column count mismatch
    if (cols.length !== headerCols) {
      if (!settings.allowInconsistentColumns) {
        result.errors.push({
          line: i + 1,
          message: `Row has ${cols.length} columns, expected ${headerCols} (header)`
        });
      } else {
        result.warnings.push({
          line: i + 1,
          message: `Column count mismatch: ${cols.length} vs ${headerCols}`
        });
      }
    }

    // Check for obvious encoding issues
    if (/[^\x00-\x7F]/.test(row) && !/[\u00C0-\u024F]/.test(row)) {
      result.warnings.push({
        line: i + 1,
        message: 'Non-ASCII characters detected - verify encoding'
      });
    }
  }

  // If we only checked a subset, note that
  if (lines.length > maxRows) {
    result.suggestions.push(`Only checked first ${maxRows} of ${lines.length} rows`);
  }

  return result;
}

/**
 * Detect CSV delimiter
 */
function detectDelimiter(content, filePath) {
  // TSV files use tabs
  if (filePath.endsWith('.tsv')) {
    return '\t';
  }

  // Count occurrences in first line
  const firstLine = content.split(/\r?\n/)[0] || '';

  const commas = (firstLine.match(/,/g) || []).length;
  const tabs = (firstLine.match(/\t/g) || []).length;
  const semicolons = (firstLine.match(/;/g) || []).length;

  // Return most common
  if (tabs >= commas && tabs >= semicolons) return '\t';
  if (semicolons > commas) return ';';
  return ',';
}

/**
 * Parse a CSV row respecting quotes
 */
function parseRow(row, delimiter) {
  const cols = [];
  let current = '';
  let inQuotes = false;

  for (let i = 0; i < row.length; i++) {
    const char = row[i];

    if (char === '"') {
      if (inQuotes && row[i + 1] === '"') {
        // Escaped quote
        current += '"';
        i++;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (char === delimiter && !inQuotes) {
      cols.push(current);
      current = '';
    } else {
      current += char;
    }
  }

  cols.push(current);
  return cols;
}
