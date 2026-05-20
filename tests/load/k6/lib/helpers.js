/**
 * Helper Functions Library for K6 Load Tests
 *
 * Provides utilities for:
 * - Random data generation (German-optimized)
 * - File generation (PDF, images)
 * - Response validation
 * - Timing utilities
 * - Statistics helpers
 */

import http from 'k6/http';
import { FormData } from 'https://jslib.k6.io/formdata/0.0.2/index.js';

// ==================== Random Data Generators ====================

/**
 * Generate random alphanumeric string
 * @param {number} length - String length
 * @returns {string} Random string
 */
export function randomString(length = 10) {
  const chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
  let result = '';
  for (let i = 0; i < length; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
}

/**
 * Generate random integer between min and max (inclusive)
 * @param {number} min - Minimum value
 * @param {number} max - Maximum value
 * @returns {number} Random integer
 */
export function randomInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

/**
 * Generate random float between min and max
 * @param {number} min - Minimum value
 * @param {number} max - Maximum value
 * @param {number} decimals - Number of decimal places
 * @returns {number} Random float
 */
export function randomFloat(min, max, decimals = 2) {
  const value = Math.random() * (max - min) + min;
  return parseFloat(value.toFixed(decimals));
}

/**
 * Pick random element from array
 * @param {Array} arr - Source array
 * @returns {*} Random element
 */
export function randomElement(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

/**
 * Generate random German text (for OCR testing)
 * @returns {string} German text
 */
export function randomGermanText() {
  const texts = [
    'Dies ist ein Testdokument mit Umlauten: aeoeuess',
    'Rechnung Nr. 2024-001 ueber 1.234,56 EUR',
    'Sehr geehrte Damen und Herren',
    'Mit freundlichen Gruessen, Mueller GmbH',
    'Lieferadresse: Hauptstrasse 123, 12345 Berlin',
    'Bestellnummer: BE-2024-12345',
    'Zahlungsziel: 14 Tage netto',
    'MwSt-Nr.: DE123456789',
    'IBAN: DE89 3704 0044 0532 0130 00',
    'Vielen Dank fuer Ihre Bestellung',
  ];
  return randomElement(texts);
}

/**
 * Generate random document type
 * @returns {string} Document type
 */
export function randomDocumentType() {
  const types = ['invoice', 'contract', 'letter', 'report', 'delivery_note', 'offer', 'order', 'other'];
  return randomElement(types);
}

/**
 * Generate random German company name
 * @returns {string} Company name
 */
export function randomGermanCompany() {
  const prefixes = ['Mueller', 'Schmidt', 'Schneider', 'Fischer', 'Weber', 'Meyer', 'Wagner', 'Becker'];
  const suffixes = ['GmbH', 'AG', 'KG', 'e.K.', 'OHG', 'GmbH & Co. KG'];
  return `${randomElement(prefixes)} ${randomElement(suffixes)}`;
}

/**
 * Generate random German address
 * @returns {Object} Address object
 */
export function randomGermanAddress() {
  const streets = ['Hauptstrasse', 'Bahnhofstrasse', 'Gartenstrasse', 'Schulstrasse', 'Kirchstrasse'];
  const cities = ['Berlin', 'Hamburg', 'Muenchen', 'Koeln', 'Frankfurt', 'Stuttgart', 'Duesseldorf'];
  const plzPrefix = randomInt(10, 99);
  const plzSuffix = randomInt(100, 999);

  return {
    street: `${randomElement(streets)} ${randomInt(1, 200)}`,
    plz: `${plzPrefix}${plzSuffix}`,
    city: randomElement(cities),
  };
}

/**
 * Generate random invoice data
 * @returns {Object} Invoice data
 */
export function randomInvoiceData() {
  const year = new Date().getFullYear();
  const month = String(randomInt(1, 12)).padStart(2, '0');
  const day = String(randomInt(1, 28)).padStart(2, '0');

  return {
    invoiceNumber: `RE-${year}-${randomInt(10000, 99999)}`,
    date: `${year}-${month}-${day}`,
    amount: randomFloat(100, 10000),
    vatRate: randomElement([7, 19]),
    currency: 'EUR',
    customer: randomGermanCompany(),
    description: randomGermanText(),
  };
}

// ==================== File Generation ====================

/**
 * Generate minimal test PDF content
 * @param {number} pageCount - Number of pages
 * @param {string} content - Text content per page
 * @returns {string} PDF content
 */
export function generateTestPDF(pageCount = 1, content = null) {
  const pages = [];
  let objCount = 5;

  for (let i = 0; i < pageCount; i++) {
    const pageObj = objCount++;
    const contentObj = objCount++;
    const pageContent = content || `Test Page ${i + 1} - ${randomString(20)}`;

    pages.push({
      pageRef: `${pageObj} 0 R`,
      pageObj: `${pageObj} 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents ${contentObj} 0 R >> endobj`,
      contentObj: `${contentObj} 0 obj << /Length ${44 + pageContent.length} >>
stream
BT /F1 12 Tf 100 700 Td (${pageContent}) Tj ET
endstream
endobj`,
    });
  }

  return `%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [${pages.map(p => p.pageRef).join(' ')}] /Count ${pageCount} >> endobj
${pages.map(p => `${p.pageObj}
${p.contentObj}`).join('\n')}
xref
0 ${objCount}
0000000000 65535 f
trailer << /Size ${objCount} /Root 1 0 R >>
startxref
999
%%EOF`;
}

/**
 * Generate test PDF with German content
 * @param {number} pageCount - Number of pages
 * @returns {string} PDF content
 */
export function generateGermanPDF(pageCount = 1) {
  const invoice = randomInvoiceData();
  const content = `${invoice.invoiceNumber} - ${invoice.customer} - ${invoice.amount} EUR`;
  return generateTestPDF(pageCount, content);
}

/**
 * Generate minimal valid PNG (1x1 white pixel)
 * @returns {ArrayBuffer} PNG data
 */
export function generateTestPNG() {
  // Minimal 1x1 white PNG in base64
  const base64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==';
  return base64;
}

/**
 * Create FormData for file upload
 * @param {string|ArrayBuffer} content - File content
 * @param {string} filename - File name
 * @param {string} contentType - MIME type
 * @param {Object} additionalFields - Additional form fields
 * @returns {FormData} Form data object
 */
export function createUploadFormData(content, filename, contentType, additionalFields = {}) {
  const fd = new FormData();
  fd.append('file', http.file(content, filename, contentType));

  for (const [key, value] of Object.entries(additionalFields)) {
    fd.append(key, value);
  }

  return fd;
}

// ==================== Response Validators ====================

/**
 * Validate JSON response structure
 * @param {Object} response - HTTP response
 * @param {Array} requiredFields - Required field names
 * @returns {boolean} True if valid
 */
export function validateJsonResponse(response, requiredFields = []) {
  if (response.status !== 200 && response.status !== 201) {
    return false;
  }

  try {
    const body = JSON.parse(response.body);

    for (const field of requiredFields) {
      if (body[field] === undefined) {
        return false;
      }
    }

    return true;
  } catch (e) {
    return false;
  }
}

/**
 * Parse JSON response safely
 * @param {Object} response - HTTP response
 * @returns {Object|null} Parsed body or null
 */
export function safeParseJson(response) {
  try {
    return JSON.parse(response.body);
  } catch (e) {
    return null;
  }
}

/**
 * Check if response indicates rate limiting
 * @param {Object} response - HTTP response
 * @returns {boolean} True if rate limited
 */
export function isRateLimited(response) {
  return response.status === 429;
}

/**
 * Check if response indicates auth failure
 * @param {Object} response - HTTP response
 * @returns {boolean} True if auth failed
 */
export function isAuthFailure(response) {
  return response.status === 401 || response.status === 403;
}

/**
 * Extract pagination info from response
 * @param {Object} response - HTTP response
 * @returns {Object|null} Pagination info
 */
export function extractPagination(response) {
  const body = safeParseJson(response);

  if (!body) {
    return null;
  }

  return {
    total: body.total || body.count || null,
    limit: body.limit || body.per_page || null,
    offset: body.offset || body.skip || null,
    page: body.page || null,
    hasMore: body.has_more || body.hasMore || (body.items && body.items.length === body.limit),
  };
}

// ==================== Timing Utilities ====================

/**
 * Generate random think time (user pause simulation)
 * @param {number} min - Minimum seconds
 * @param {number} max - Maximum seconds
 * @returns {number} Random duration in seconds
 */
export function randomThinkTime(min = 1, max = 5) {
  return min + Math.random() * (max - min);
}

/**
 * Generate exponential backoff delay
 * @param {number} attempt - Current attempt number (1-based)
 * @param {number} baseDelay - Base delay in ms
 * @param {number} maxDelay - Maximum delay in ms
 * @returns {number} Delay in ms
 */
export function exponentialBackoff(attempt, baseDelay = 1000, maxDelay = 30000) {
  const delay = Math.min(baseDelay * Math.pow(2, attempt - 1), maxDelay);
  // Add jitter (0-25% of delay)
  const jitter = delay * 0.25 * Math.random();
  return delay + jitter;
}

/**
 * Format duration in human-readable format
 * @param {number} ms - Duration in milliseconds
 * @returns {string} Formatted duration
 */
export function formatDuration(ms) {
  if (ms < 1000) {
    return `${ms.toFixed(0)}ms`;
  } else if (ms < 60000) {
    return `${(ms / 1000).toFixed(2)}s`;
  } else {
    const minutes = Math.floor(ms / 60000);
    const seconds = ((ms % 60000) / 1000).toFixed(0);
    return `${minutes}m ${seconds}s`;
  }
}

// ==================== Statistics Helpers ====================

/**
 * Calculate percentile from sorted array
 * @param {Array} sortedArray - Sorted numeric array
 * @param {number} percentile - Percentile (0-100)
 * @returns {number} Percentile value
 */
export function calculatePercentile(sortedArray, percentile) {
  if (sortedArray.length === 0) return 0;

  const index = (percentile / 100) * (sortedArray.length - 1);
  const lower = Math.floor(index);
  const upper = Math.ceil(index);

  if (lower === upper) {
    return sortedArray[lower];
  }

  const weight = index - lower;
  return sortedArray[lower] * (1 - weight) + sortedArray[upper] * weight;
}

/**
 * Calculate basic statistics from array
 * @param {Array} values - Numeric array
 * @returns {Object} Statistics object
 */
export function calculateStats(values) {
  if (values.length === 0) {
    return { count: 0, min: 0, max: 0, avg: 0, p50: 0, p90: 0, p95: 0, p99: 0 };
  }

  const sorted = [...values].sort((a, b) => a - b);
  const sum = values.reduce((a, b) => a + b, 0);

  return {
    count: values.length,
    min: sorted[0],
    max: sorted[sorted.length - 1],
    avg: sum / values.length,
    p50: calculatePercentile(sorted, 50),
    p90: calculatePercentile(sorted, 90),
    p95: calculatePercentile(sorted, 95),
    p99: calculatePercentile(sorted, 99),
  };
}

// ==================== Error Helpers ====================

/**
 * Extract error message from response
 * @param {Object} response - HTTP response
 * @returns {string} Error message
 */
export function extractErrorMessage(response) {
  const body = safeParseJson(response);

  if (body) {
    return body.detail || body.message || body.error || `HTTP ${response.status}`;
  }

  return `HTTP ${response.status}: ${response.body || 'Unknown error'}`;
}

/**
 * Log error with context
 * @param {string} context - Error context
 * @param {Object} response - HTTP response
 */
export function logError(context, response) {
  const message = extractErrorMessage(response);
  console.error(`[${context}] ${message}`);
}

// ==================== Exports ====================

export default {
  randomString,
  randomInt,
  randomFloat,
  randomElement,
  randomGermanText,
  randomDocumentType,
  randomGermanCompany,
  randomGermanAddress,
  randomInvoiceData,
  generateTestPDF,
  generateGermanPDF,
  generateTestPNG,
  createUploadFormData,
  validateJsonResponse,
  safeParseJson,
  isRateLimited,
  isAuthFailure,
  extractPagination,
  randomThinkTime,
  exponentialBackoff,
  formatDuration,
  calculatePercentile,
  calculateStats,
  extractErrorMessage,
  logError,
};
