/**
 * Validator Registry & Router
 *
 * Routes files to appropriate validators based on extension.
 */

import path from 'path';
import fs from 'fs';
import {
  config,
  shouldSkipPath,
  shouldSkipSize,
  getValidatorName,
  isValidatorEnabled,
  getValidatorSettings
} from './config.js';

// Import validators
import { validateJson } from './json-validator.js';
import { validateCsv } from './csv-validator.js';
import { validateSql } from './sql-validator.js';
import { validateMarkdown } from './markdown-validator.js';
import { validateEnv } from './env-validator.js';
import { validateTypescript } from './typescript-validator.js';
import { validatePython } from './python-validator.js';

// Validator registry
const validators = {
  json: validateJson,
  csv: validateCsv,
  sql: validateSql,
  markdown: validateMarkdown,
  env: validateEnv,
  typescript: validateTypescript,
  python: validatePython
};

/**
 * Validation result structure
 * @typedef {Object} ValidationResult
 * @property {boolean} valid - Overall pass/fail
 * @property {boolean} skipped - Whether validation was skipped
 * @property {string} [skipReason] - Why validation was skipped
 * @property {Array<{line?: number, message: string}>} errors - Critical issues
 * @property {Array<{line?: number, message: string}>} warnings - Non-blocking issues
 * @property {Array<string>} suggestions - Improvement hints
 */

/**
 * Validate a file
 * @param {string} filePath - Absolute path to file
 * @param {string} [content] - File content (optional, will read if not provided)
 * @returns {Promise<ValidationResult>}
 */
export async function validate(filePath, content = null) {
  const result = {
    valid: true,
    skipped: false,
    errors: [],
    warnings: [],
    suggestions: []
  };

  // Check if globally enabled
  if (!config.enabled) {
    result.skipped = true;
    result.skipReason = 'Validation disabled';
    return result;
  }

  // Check skip patterns
  if (shouldSkipPath(filePath)) {
    result.skipped = true;
    result.skipReason = 'Path matches skip pattern';
    return result;
  }

  // Get extension and validator
  const ext = path.extname(filePath);
  const basename = path.basename(filePath);

  // Handle dotfiles like .env, .env.local, etc.
  let validatorName;
  if (ext) {
    validatorName = getValidatorName(ext);
  } else if (basename.startsWith('.')) {
    // Dotfiles without extension (e.g., .env)
    validatorName = getValidatorName(basename);
  } else {
    validatorName = null;
  }

  // Also check for compound extensions like .env.local
  if (!validatorName && basename.includes('.env')) {
    validatorName = 'env';
  }

  if (!validatorName) {
    result.skipped = true;
    result.skipReason = 'No validator for extension';
    return result;
  }

  // Check if validator enabled
  if (!isValidatorEnabled(validatorName)) {
    result.skipped = true;
    result.skipReason = `${validatorName} validator disabled`;
    return result;
  }

  // Read content if not provided
  if (content === null) {
    try {
      const stats = fs.statSync(filePath);

      // Check file size
      if (shouldSkipSize(stats.size)) {
        result.skipped = true;
        result.skipReason = `File too large (${Math.round(stats.size / 1024)}KB)`;
        result.warnings.push({ message: 'File exceeds 1MB, validation skipped' });
        return result;
      }

      content = fs.readFileSync(filePath, 'utf8');
    } catch (err) {
      result.valid = false;
      result.errors.push({ message: `Cannot read file: ${err.message}` });
      return result;
    }
  }

  // Get validator
  const validator = validators[validatorName];
  if (!validator) {
    result.skipped = true;
    result.skipReason = 'Validator not implemented';
    return result;
  }

  // Run validator with timeout
  const settings = getValidatorSettings(validatorName);

  try {
    const timeoutPromise = new Promise((_, reject) =>
      setTimeout(() => reject(new Error('Validation timeout')), config.timeoutMs)
    );

    const validationPromise = validator(filePath, content, settings);

    const validatorResult = await Promise.race([validationPromise, timeoutPromise]);

    // Merge results
    result.valid = validatorResult.valid ?? true;
    result.errors = validatorResult.errors || [];
    result.warnings = validatorResult.warnings || [];
    result.suggestions = validatorResult.suggestions || [];

    // valid is false if there are errors
    if (result.errors.length > 0) {
      result.valid = false;
    }

  } catch (err) {
    result.warnings.push({ message: `Validator error: ${err.message}` });
  }

  return result;
}

/**
 * Format validation result for output
 * @param {string} filePath
 * @param {ValidationResult} result
 * @returns {string}
 */
export function formatResult(filePath, result) {
  if (result.skipped) {
    return ''; // Silent for skipped files
  }

  const lines = [];
  const relativePath = path.basename(filePath);

  if (result.errors.length > 0 || result.warnings.length > 0) {
    lines.push(`### Validation Issues: ${relativePath}`);
    lines.push('');

    for (const err of result.errors) {
      const loc = err.line ? `L${err.line}: ` : '';
      lines.push(`- ERROR ${loc}${err.message}`);
    }

    for (const warn of result.warnings) {
      const loc = warn.line ? `L${warn.line}: ` : '';
      lines.push(`- WARN ${loc}${warn.message}`);
    }

    if (result.suggestions.length > 0) {
      lines.push('');
      lines.push('**Suggestions:**');
      for (const sug of result.suggestions) {
        lines.push(`- ${sug}`);
      }
    }

    lines.push('');
  }

  return lines.join('\n');
}
