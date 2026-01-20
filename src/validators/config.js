/**
 * Validator Configuration
 *
 * Settings for file validation hooks.
 */

export const config = {
  // Global settings
  enabled: true,
  maxFileSizeBytes: 1024 * 1024, // 1MB - skip larger files
  timeoutMs: 5000, // 5 second timeout per validator

  // Skip patterns - directories/files to ignore
  skipPatterns: [
    'node_modules',
    '.git',
    'dist',
    'build',
    '.next',
    '__pycache__',
    'venv',
    '.venv',
    'coverage',
    '.nyc_output',
    '.turbo',
    '.vercel'
  ],

  // Individual validator settings
  validators: {
    json: {
      enabled: true,
      // Schema locations for JSON validation (future)
      schemas: {}
    },
    csv: {
      enabled: true,
      maxRowsToCheck: 100, // Don't check entire large files
      allowInconsistentColumns: false
    },
    sql: {
      enabled: true,
      dangerousKeywords: ['DROP', 'TRUNCATE', 'DELETE FROM', 'ALTER TABLE DROP'],
      warnKeywords: ['UPDATE', 'INSERT INTO']
    },
    markdown: {
      enabled: true,
      checkFrontmatter: true,
      checkLinks: true
    },
    env: {
      enabled: true,
      warnOnMissingValue: true
    },
    typescript: {
      enabled: true,
      useProjectConfig: true // Use project's tsconfig if available
    },
    python: {
      enabled: true,
      checkImports: true
    }
  }
};

// Extension to validator mapping
export const extensionMap = {
  '.json': 'json',
  '.jsonc': 'json',
  '.csv': 'csv',
  '.tsv': 'csv',
  '.sql': 'sql',
  '.md': 'markdown',
  '.markdown': 'markdown',
  '.env': 'env',
  '.env.local': 'env',
  '.env.development': 'env',
  '.env.production': 'env',
  '.ts': 'typescript',
  '.tsx': 'typescript',
  '.mts': 'typescript',
  '.cts': 'typescript',
  '.py': 'python',
  '.pyw': 'python'
};

// Check if path should be skipped
export function shouldSkipPath(filePath) {
  const normalized = filePath.replace(/\\/g, '/');
  return config.skipPatterns.some(pattern =>
    normalized.includes(`/${pattern}/`) ||
    normalized.includes(`/${pattern}`)
  );
}

// Check if file size should be skipped
export function shouldSkipSize(sizeBytes) {
  return sizeBytes > config.maxFileSizeBytes;
}

// Get validator for extension
export function getValidatorName(ext) {
  return extensionMap[ext.toLowerCase()] || null;
}

// Check if validator is enabled
export function isValidatorEnabled(validatorName) {
  if (!config.enabled) return false;
  return config.validators[validatorName]?.enabled ?? false;
}

// Get validator settings
export function getValidatorSettings(validatorName) {
  return config.validators[validatorName] || {};
}
