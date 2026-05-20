/**
 * Configuration Library for K6 Load Tests
 *
 * Centralized configuration management:
 * - Environment-aware settings
 * - Threshold definitions
 * - Scenario templates
 * - URL builders
 */

// ==================== Base Configuration ====================

/**
 * Base URL for the API
 * Can be overridden via BASE_URL environment variable
 */
export const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';

/**
 * API prefix for versioned endpoints
 */
export const API_PREFIX = '/api/v1';

/**
 * Test user credentials
 * Should be overridden via environment variables in CI/CD
 */
export const TEST_USER = {
  email: __ENV.TEST_EMAIL || 'loadtest@ablage-system.local',
  password: __ENV.TEST_PASSWORD || 'LoadTest123!@#',
};

/**
 * Environment name
 */
export const ENVIRONMENT = __ENV.ENVIRONMENT || 'development';

// ==================== Performance Thresholds ====================

/**
 * Performance thresholds (in milliseconds)
 * Based on CLAUDE.md performance targets:
 * - API Health Check: < 50ms (p95)
 * - Document Upload: < 500ms (p95)
 * - OCR Processing: < 2s GPU, < 10s CPU (p95)
 * - Search Query: < 500ms (p95)
 */
export const THRESHOLDS = {
  // Response time thresholds
  health_check_p95: 50,
  health_check_p99: 100,

  document_upload_p95: 500,
  document_upload_p99: 1000,

  ocr_processing_gpu_p95: 2000,
  ocr_processing_gpu_p99: 5000,
  ocr_processing_cpu_p95: 10000,
  ocr_processing_cpu_p99: 30000,

  search_query_p95: 500,
  search_query_p99: 1000,

  auth_login_p95: 200,
  auth_login_p99: 500,

  auth_refresh_p95: 150,
  auth_refresh_p99: 300,

  // Error rate thresholds
  error_rate_max: 0.01, // Max 1% error rate
  error_rate_warning: 0.05, // Warning at 5%

  // Throughput thresholds
  min_requests_per_second: 10,
  target_documents_per_hour: 500,

  // Concurrent users
  target_concurrent_users: 100,
};

// ==================== Scenario Templates ====================

/**
 * Pre-defined test scenarios
 */
export const SCENARIOS = {
  // Smoke test: Quick validation
  smoke: {
    executor: 'constant-vus',
    vus: 1,
    duration: '30s',
  },

  // Load test: Normal load
  load: {
    executor: 'ramping-vus',
    startVUs: 0,
    stages: [
      { duration: '1m', target: 10 },
      { duration: '3m', target: 10 },
      { duration: '1m', target: 20 },
      { duration: '3m', target: 20 },
      { duration: '1m', target: 0 },
    ],
  },

  // Stress test: Beyond normal load
  stress: {
    executor: 'ramping-vus',
    startVUs: 0,
    stages: [
      { duration: '2m', target: 10 },
      { duration: '2m', target: 30 },
      { duration: '2m', target: 50 },
      { duration: '2m', target: 70 },
      { duration: '2m', target: 100 },
      { duration: '5m', target: 100 },
      { duration: '2m', target: 0 },
    ],
  },

  // Spike test: Sudden traffic spike
  spike: {
    executor: 'ramping-vus',
    startVUs: 0,
    stages: [
      { duration: '30s', target: 5 },
      { duration: '10s', target: 100 },
      { duration: '1m', target: 100 },
      { duration: '10s', target: 5 },
      { duration: '30s', target: 0 },
    ],
  },

  // Soak test: Extended duration
  soak: {
    executor: 'constant-vus',
    vus: 20,
    duration: '30m',
  },

  // Concurrent users test: Target 100 users
  concurrent_100: {
    executor: 'ramping-vus',
    startVUs: 0,
    stages: [
      { duration: '1m', target: 20 },
      { duration: '2m', target: 50 },
      { duration: '3m', target: 100 },
      { duration: '5m', target: 100 },
      { duration: '2m', target: 50 },
      { duration: '1m', target: 0 },
    ],
  },

  // High throughput test
  throughput: {
    executor: 'constant-arrival-rate',
    rate: 100,
    timeUnit: '1s',
    duration: '5m',
    preAllocatedVUs: 50,
    maxVUs: 200,
  },

  // Breakpoint test: Find system limits
  breakpoint: {
    executor: 'ramping-arrival-rate',
    startRate: 1,
    timeUnit: '1s',
    preAllocatedVUs: 50,
    maxVUs: 500,
    stages: [
      { duration: '2m', target: 10 },
      { duration: '2m', target: 25 },
      { duration: '2m', target: 50 },
      { duration: '2m', target: 100 },
      { duration: '2m', target: 200 },
      { duration: '2m', target: 300 },
      { duration: '1m', target: 0 },
    ],
  },
};

// ==================== Default K6 Options ====================

/**
 * Common K6 options template
 */
export const DEFAULT_OPTIONS = {
  thresholds: {
    // HTTP request duration
    'http_req_duration': ['p(95)<500', 'p(99)<1000'],

    // Error rate
    'http_req_failed': ['rate<0.01'],

    // Custom metrics by endpoint
    'http_req_duration{endpoint:health}': ['p(95)<50'],
    'http_req_duration{endpoint:login}': ['p(95)<200'],
    'http_req_duration{endpoint:upload}': ['p(95)<500'],
    'http_req_duration{endpoint:search}': ['p(95)<500'],
    'http_req_duration{endpoint:ocr}': ['p(95)<10000'],
  },

  // Tags for grouping
  tags: {
    environment: ENVIRONMENT,
    test_type: __ENV.TEST_TYPE || 'load',
  },

  // Summaries
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
};

// ==================== URL Builders ====================

/**
 * Build full API URL
 * @param {string} path - API path (without prefix)
 * @returns {string} Full URL
 */
export function getUrl(path) {
  return `${BASE_URL}${API_PREFIX}${path}`;
}

/**
 * Build URL with query parameters
 * @param {string} path - API path
 * @param {Object} params - Query parameters
 * @returns {string} Full URL with query string
 */
export function getUrlWithParams(path, params = {}) {
  const url = getUrl(path);
  const queryString = Object.entries(params)
    .filter(([_, value]) => value !== null && value !== undefined)
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
    .join('&');

  return queryString ? `${url}?${queryString}` : url;
}

/**
 * Get base URL (without API prefix)
 * @param {string} path - Path
 * @returns {string} Full URL
 */
export function getBaseUrl(path = '') {
  return `${BASE_URL}${path}`;
}

// ==================== Header Builders ====================

/**
 * Get standard headers for JSON requests
 * @param {string} token - Optional auth token
 * @returns {Object} Headers object
 */
export function getHeaders(token = null) {
  const headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  return headers;
}

/**
 * Get headers for multipart form uploads
 * @param {string} token - Auth token
 * @param {string} boundary - Form boundary
 * @returns {Object} Headers object
 */
export function getUploadHeaders(token, boundary) {
  return {
    'Authorization': `Bearer ${token}`,
    'Content-Type': `multipart/form-data; boundary=${boundary}`,
  };
}

// ==================== Environment Helpers ====================

/**
 * Check if running in production environment
 * @returns {boolean} True if production
 */
export function isProduction() {
  return ENVIRONMENT === 'production';
}

/**
 * Check if running in CI environment
 * @returns {boolean} True if CI
 */
export function isCI() {
  return __ENV.CI === 'true' || __ENV.GITHUB_ACTIONS === 'true';
}

/**
 * Get timeout based on environment
 * @param {string} type - Timeout type (short, medium, long)
 * @returns {string} Timeout string
 */
export function getTimeout(type = 'medium') {
  const timeouts = {
    short: '5s',
    medium: '30s',
    long: '120s',
  };
  return timeouts[type] || timeouts.medium;
}

// ==================== Validation ====================

/**
 * Validate that required environment variables are set
 * @param {Array} required - Required variable names
 * @returns {boolean} True if all set
 */
export function validateEnv(required = []) {
  const missing = required.filter(name => !__ENV[name]);

  if (missing.length > 0) {
    console.warn(`Missing environment variables: ${missing.join(', ')}`);
    return false;
  }

  return true;
}

// ==================== Exports ====================

export default {
  BASE_URL,
  API_PREFIX,
  TEST_USER,
  ENVIRONMENT,
  THRESHOLDS,
  SCENARIOS,
  DEFAULT_OPTIONS,
  getUrl,
  getUrlWithParams,
  getBaseUrl,
  getHeaders,
  getUploadHeaders,
  isProduction,
  isCI,
  getTimeout,
  validateEnv,
};
