/**
 * K6 Load Test: Search Latency
 *
 * Testet Such-Latenz mit Ziel: < 200ms P99
 * - Volltextsuche
 * - Entity-Suche (Kunden, Lieferanten)
 * - Filterbasierte Suche
 *
 * Performance-Ziele:
 * - Search Latency: < 200ms (p99)
 * - Search Latency: < 100ms (p95)
 *
 * Ausfuehrung:
 *   k6 run tests/load/k6/scenarios/search_latency.js
 */

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend, Counter, Gauge } from 'k6/metrics';
import { SharedArray } from 'k6/data';
import { BASE_URL, API_PREFIX, TEST_USER, getHeaders, randomGermanText } from '../config.js';

// ==================== Custom Metrics ====================

// Search-specific metrics
const fulltextSearchDuration = new Trend('fulltext_search_duration', true);
const entitySearchDuration = new Trend('entity_search_duration', true);
const filterSearchDuration = new Trend('filter_search_duration', true);
const advancedSearchDuration = new Trend('advanced_search_duration', true);

// Aggregated search metric
const allSearchDuration = new Trend('all_search_duration', true);

// Error rates
const searchErrors = new Rate('search_errors');
const emptyResultRate = new Rate('empty_result_rate');

// Counters
const totalSearches = new Counter('total_searches');
const searchResultsFound = new Counter('search_results_found');

// ==================== Test Configuration ====================

export const options = {
  scenarios: {
    // Constant rate search test
    search_latency: {
      executor: 'constant-arrival-rate',
      rate: 50,              // 50 searches per second
      timeUnit: '1s',
      duration: '5m',
      preAllocatedVUs: 20,   // Pre-allocate 20 VUs
      maxVUs: 100,           // Allow up to 100 VUs
      exec: 'searchTest',
    },

    // Ramping rate for stress testing
    search_stress: {
      executor: 'ramping-arrival-rate',
      startRate: 10,
      timeUnit: '1s',
      preAllocatedVUs: 20,
      maxVUs: 200,
      stages: [
        { duration: '1m', target: 20 },   // Warm-up
        { duration: '2m', target: 50 },   // Normal load
        { duration: '2m', target: 100 },  // High load
        { duration: '1m', target: 50 },   // Cool-down
        { duration: '30s', target: 10 },  // Wind-down
      ],
      exec: 'searchTest',
      startTime: '6m', // Start after latency test
    },
  },

  thresholds: {
    // Primary search latency targets
    'all_search_duration': ['p(99)<200', 'p(95)<100', 'avg<80'],

    // Search type specific
    'fulltext_search_duration': ['p(99)<200', 'p(95)<100'],
    'entity_search_duration': ['p(99)<200', 'p(95)<100'],
    'filter_search_duration': ['p(99)<150', 'p(95)<80'],
    'advanced_search_duration': ['p(99)<300', 'p(95)<150'],

    // Error thresholds
    'search_errors': ['rate<0.02'],      // Max 2% search errors
    'http_req_failed': ['rate<0.05'],

    // Empty results (informational, not failure)
    'empty_result_rate': ['rate<0.5'],   // Warning if >50% empty
  },

  tags: {
    test_name: 'search_latency',
  },
};

// ==================== Test Data ====================

// German search terms organized by category
const searchTerms = new SharedArray('searchTerms', function () {
  return {
    // Document content searches
    fulltext: [
      'Rechnung',
      'Vertrag',
      'Angebot',
      'Lieferschein',
      'Mahnung',
      'Gutschrift',
      'Bestellung',
      'Auftragsbestaetigung',
      'Steuernummer',
      'Unterschrift',
      'Zahlungsziel',
      'Skonto',
      'Nettobetrag',
      'Bruttobetrag',
      'MwSt',
      'USt-IdNr',
    ],

    // Entity names
    entities: [
      'GmbH',
      'AG',
      'KG',
      'Mueller',
      'Schmidt',
      'Berlin',
      'Muenchen',
      'Hamburg',
      'Frankfurt',
    ],

    // Financial terms
    financial: [
      'EUR',
      '1000',
      '5000',
      '10000',
      'IBAN',
      'DE89',
      'BIC',
      'COBADEFF',
    ],

    // Date patterns
    dates: [
      '2024',
      '2025',
      '01.2024',
      '12.2024',
      'Januar',
      'Februar',
      'Maerz',
    ],

    // Customer/Supplier numbers
    numbers: [
      'K-',
      'L-',
      'RE-',
      'AN-',
      'AU-',
      'LS-',
    ],
  };
});

// Document types for filtered search
const documentTypes = ['invoice', 'contract', 'letter', 'report', 'other'];

// ==================== Helper Functions ====================

let accessToken = null;

/**
 * Ensure authenticated
 */
function ensureAuth() {
  if (accessToken) return accessToken;

  const response = http.post(
    `${BASE_URL}${API_PREFIX}/auth/login`,
    JSON.stringify({
      email: TEST_USER.email,
      password: TEST_USER.password,
    }),
    { headers: getHeaders() }
  );

  if (response.status === 200) {
    try {
      accessToken = JSON.parse(response.body).access_token;
    } catch (e) {
      console.error('Failed to parse auth response');
    }
  }

  return accessToken;
}

/**
 * Get random search term from category
 */
function getRandomTerm(category) {
  const terms = searchTerms[category];
  return terms[Math.floor(Math.random() * terms.length)];
}

/**
 * Fulltext search
 */
function fulltextSearch(token, query) {
  const response = http.get(
    `${BASE_URL}${API_PREFIX}/documents/search?q=${encodeURIComponent(query)}&limit=20`,
    {
      headers: getHeaders(token),
      tags: { endpoint: 'search_fulltext', search_type: 'fulltext' },
    }
  );

  fulltextSearchDuration.add(response.timings.duration);
  allSearchDuration.add(response.timings.duration);
  totalSearches.add(1);

  const success = check(response, {
    'fulltext search status 200': (r) => r.status === 200,
    'fulltext search < 200ms': (r) => r.timings.duration < 200,
  });

  if (!success) {
    searchErrors.add(1);
  } else {
    searchErrors.add(0);
    trackResults(response);
  }

  return response;
}

/**
 * Entity search (customers/suppliers)
 */
function entitySearch(token, query, entityType = 'customer') {
  const endpoint = entityType === 'customer' ? 'entities/customers' : 'entities/suppliers';

  const response = http.get(
    `${BASE_URL}${API_PREFIX}/${endpoint}?search=${encodeURIComponent(query)}&limit=20`,
    {
      headers: getHeaders(token),
      tags: { endpoint: 'search_entity', search_type: 'entity', entity_type: entityType },
    }
  );

  entitySearchDuration.add(response.timings.duration);
  allSearchDuration.add(response.timings.duration);
  totalSearches.add(1);

  const success = check(response, {
    'entity search status 200': (r) => r.status === 200,
    'entity search < 200ms': (r) => r.timings.duration < 200,
  });

  if (!success) {
    searchErrors.add(1);
  } else {
    searchErrors.add(0);
    trackResults(response);
  }

  return response;
}

/**
 * Filter-based search
 */
function filterSearch(token, filters) {
  const params = new URLSearchParams();

  if (filters.document_type) params.append('document_type', filters.document_type);
  if (filters.language) params.append('language', filters.language);
  if (filters.date_from) params.append('date_from', filters.date_from);
  if (filters.date_to) params.append('date_to', filters.date_to);
  if (filters.min_confidence) params.append('min_confidence', filters.min_confidence);
  params.append('limit', '20');

  const response = http.get(
    `${BASE_URL}${API_PREFIX}/documents/?${params.toString()}`,
    {
      headers: getHeaders(token),
      tags: { endpoint: 'search_filter', search_type: 'filter' },
    }
  );

  filterSearchDuration.add(response.timings.duration);
  allSearchDuration.add(response.timings.duration);
  totalSearches.add(1);

  const success = check(response, {
    'filter search status 200': (r) => r.status === 200,
    'filter search < 150ms': (r) => r.timings.duration < 150,
  });

  if (!success) {
    searchErrors.add(1);
  } else {
    searchErrors.add(0);
    trackResults(response);
  }

  return response;
}

/**
 * Advanced search with multiple criteria
 */
function advancedSearch(token, searchOptions) {
  const payload = JSON.stringify({
    query: searchOptions.query,
    filters: {
      document_type: searchOptions.document_type,
      language: searchOptions.language || 'de',
      min_confidence: searchOptions.min_confidence || 0.5,
      date_from: searchOptions.date_from,
      date_to: searchOptions.date_to,
    },
    sort_by: searchOptions.sort_by || 'relevance',
    limit: searchOptions.limit || 20,
    offset: searchOptions.offset || 0,
  });

  const response = http.post(
    `${BASE_URL}${API_PREFIX}/documents/search/advanced`,
    payload,
    {
      headers: getHeaders(token),
      tags: { endpoint: 'search_advanced', search_type: 'advanced' },
    }
  );

  advancedSearchDuration.add(response.timings.duration);
  allSearchDuration.add(response.timings.duration);
  totalSearches.add(1);

  const success = check(response, {
    'advanced search status 200': (r) => r.status === 200,
    'advanced search < 300ms': (r) => r.timings.duration < 300,
  });

  if (!success) {
    searchErrors.add(1);
  } else {
    searchErrors.add(0);
    trackResults(response);
  }

  return response;
}

/**
 * Track search results for metrics
 */
function trackResults(response) {
  try {
    const body = JSON.parse(response.body);
    const results = body.results || body.items || body;

    if (Array.isArray(results)) {
      if (results.length === 0) {
        emptyResultRate.add(1);
      } else {
        emptyResultRate.add(0);
        searchResultsFound.add(results.length);
      }
    }
  } catch (e) {
    // Ignore parse errors
  }
}

// ==================== Main Test Scenarios ====================

/**
 * Main search test - randomly selects search type
 */
export function searchTest() {
  const token = ensureAuth();

  if (!token) {
    console.error('Authentication failed');
    searchErrors.add(1);
    return;
  }

  // Randomly select search type
  const searchType = Math.random();

  if (searchType < 0.4) {
    // 40% fulltext search
    group('Fulltext Search', function () {
      const query = getRandomTerm('fulltext');
      fulltextSearch(token, query);
    });
  } else if (searchType < 0.6) {
    // 20% entity search
    group('Entity Search', function () {
      const query = getRandomTerm('entities');
      const entityType = Math.random() > 0.5 ? 'customer' : 'supplier';
      entitySearch(token, query, entityType);
    });
  } else if (searchType < 0.8) {
    // 20% filter search
    group('Filter Search', function () {
      const docType = documentTypes[Math.floor(Math.random() * documentTypes.length)];
      filterSearch(token, {
        document_type: docType,
        language: 'de',
      });
    });
  } else {
    // 20% advanced search
    group('Advanced Search', function () {
      const query = getRandomTerm('fulltext');
      const docType = documentTypes[Math.floor(Math.random() * documentTypes.length)];
      advancedSearch(token, {
        query: query,
        document_type: docType,
        min_confidence: 0.5,
      });
    });
  }

  // Small think time between searches
  sleep(0.1 + Math.random() * 0.2);
}

/**
 * Focused fulltext search test
 */
export function fulltextOnly() {
  const token = ensureAuth();
  if (!token) return;

  const categories = ['fulltext', 'financial', 'dates', 'numbers'];
  const category = categories[Math.floor(Math.random() * categories.length)];
  const query = getRandomTerm(category);

  fulltextSearch(token, query);
  sleep(0.1);
}

/**
 * Focused entity search test
 */
export function entityOnly() {
  const token = ensureAuth();
  if (!token) return;

  const query = getRandomTerm('entities');
  entitySearch(token, query, Math.random() > 0.5 ? 'customer' : 'supplier');
  sleep(0.1);
}

// ==================== Lifecycle Hooks ====================

export function setup() {
  console.log('='.repeat(60));
  console.log('Starting Search Latency Test');
  console.log(`Target: ${BASE_URL}`);
  console.log('Performance Goals:');
  console.log('  - P99 Latency: < 200ms');
  console.log('  - P95 Latency: < 100ms');
  console.log('='.repeat(60));

  // Verify API is accessible
  const healthResponse = http.get(`${BASE_URL}${API_PREFIX}/health`);

  if (healthResponse.status !== 200) {
    console.error(`API health check failed: ${healthResponse.status}`);
    return { healthy: false };
  }

  // Verify search endpoint works
  const token = ensureAuth();
  if (token) {
    const searchResponse = http.get(
      `${BASE_URL}${API_PREFIX}/documents/search?q=test&limit=1`,
      { headers: getHeaders(token) }
    );

    if (searchResponse.status === 200) {
      console.log('Search endpoint verified');
    } else {
      console.warn(`Search endpoint returned: ${searchResponse.status}`);
    }
  }

  return {
    startTime: new Date().toISOString(),
    healthy: true,
  };
}

export function teardown(data) {
  console.log('='.repeat(60));
  console.log('Search Latency Test Completed');
  console.log(`Started at: ${data.startTime}`);
  console.log(`Completed at: ${new Date().toISOString()}`);
  console.log('='.repeat(60));
}

// ==================== Default Export ====================

export default function () {
  searchTest();
}
