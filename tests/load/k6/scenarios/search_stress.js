/**
 * K6 Load Test: Search Endpoint Stress Test
 *
 * Target: < 500ms (p95)
 * Purpose: Test search performance under various load conditions
 */

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';
import { BASE_URL, API_PREFIX, TEST_USER, SCENARIOS, getHeaders, randomGermanText, randomDocumentType } from '../config.js';

// Custom metrics
const searchDuration = new Trend('search_duration', true);
const searchErrors = new Rate('search_errors');
const searchQueries = new Counter('search_queries');

// Auth token
let accessToken = null;

// Test options
export const options = {
    scenarios: {
        search_stress: {
            ...SCENARIOS.stress,
            exec: 'searchStressTest'
        }
    },
    thresholds: {
        'search_duration': ['p(95)<500', 'p(99)<1000'],
        'search_errors': ['rate<0.05'],
        'http_req_failed': ['rate<0.05']
    },
    tags: {
        test_name: 'search_stress',
        endpoint: 'search'
    }
};

// Sample search queries (German)
const SEARCH_QUERIES = [
    'Rechnung',
    'Vertrag',
    'Angebot',
    'Lieferschein',
    'Mahnung',
    'Gutschrift',
    'Bestellung',
    'Auftragsbestätigung',
    'Müller GmbH',
    'IBAN DE89',
    '2024',
    'EUR 1.234',
    'Unterschrift',
    'Steuernummer',
    'Zahlungsziel'
];

// Login helper
function login() {
    const response = http.post(
        `${BASE_URL}${API_PREFIX}/auth/login`,
        JSON.stringify({
            email: TEST_USER.email,
            password: TEST_USER.password
        }),
        { headers: getHeaders() }
    );

    if (response.status === 200) {
        const body = JSON.parse(response.body);
        return body.access_token;
    }
    return null;
}

// Basic search
function search(token, query, filters = {}) {
    const params = new URLSearchParams();
    params.append('q', query);

    if (filters.document_type) {
        params.append('document_type', filters.document_type);
    }
    if (filters.language) {
        params.append('language', filters.language);
    }
    if (filters.limit) {
        params.append('limit', filters.limit);
    }

    const response = http.get(
        `${BASE_URL}${API_PREFIX}/documents/search?${params.toString()}`,
        {
            headers: getHeaders(token),
            tags: { endpoint: 'search' }
        }
    );

    searchDuration.add(response.timings.duration);
    searchQueries.add(1);

    return response;
}

// Advanced search with filters
function advancedSearch(token, options) {
    const payload = JSON.stringify({
        query: options.query,
        filters: {
            document_type: options.document_type,
            language: options.language || 'de',
            min_confidence: options.min_confidence || 0.5,
            date_from: options.date_from,
            date_to: options.date_to
        },
        sort_by: options.sort_by || 'relevance',
        limit: options.limit || 20,
        offset: options.offset || 0
    });

    const response = http.post(
        `${BASE_URL}${API_PREFIX}/documents/search/advanced`,
        payload,
        {
            headers: getHeaders(token),
            tags: { endpoint: 'search_advanced' }
        }
    );

    searchDuration.add(response.timings.duration);
    searchQueries.add(1);

    return response;
}

// Main search stress test
export function searchStressTest() {
    // Ensure we have a token
    if (!accessToken) {
        accessToken = login();
        if (!accessToken) {
            console.error('Failed to login');
            searchErrors.add(1);
            return;
        }
    }

    group('Basic Search', function() {
        // Random query from list
        const query = SEARCH_QUERIES[Math.floor(Math.random() * SEARCH_QUERIES.length)];

        const response = search(accessToken, query);

        const success = check(response, {
            'search status is 200': (r) => r.status === 200,
            'search response time < 500ms': (r) => r.timings.duration < 500,
            'search returns results array': (r) => {
                try {
                    const body = JSON.parse(r.body);
                    return Array.isArray(body.results) || Array.isArray(body.documents) || Array.isArray(body);
                } catch {
                    return false;
                }
            }
        });

        if (response.status === 401) {
            accessToken = login();
            searchErrors.add(1);
            return;
        }

        if (success) {
            searchErrors.add(0);
        } else {
            searchErrors.add(1);
        }

        sleep(0.2);
    });

    group('Filtered Search', function() {
        const query = SEARCH_QUERIES[Math.floor(Math.random() * SEARCH_QUERIES.length)];
        const docType = randomDocumentType();

        const response = search(accessToken, query, {
            document_type: docType,
            language: 'de',
            limit: 10
        });

        check(response, {
            'filtered search status is 200': (r) => r.status === 200,
            'filtered search response time < 500ms': (r) => r.timings.duration < 500
        });

        sleep(0.2);
    });

    group('Pagination Test', function() {
        const query = 'Rechnung';

        // First page
        let response = search(accessToken, query, { limit: 10 });
        check(response, {
            'pagination page 1 status is 200': (r) => r.status === 200
        });

        // Second page (if exists)
        response = search(accessToken, query, { limit: 10 });
        check(response, {
            'pagination page 2 status is 200': (r) => r.status === 200
        });

        sleep(0.3);
    });
}

// Concurrent search test
export function concurrentSearchTest() {
    if (!accessToken) {
        accessToken = login();
        if (!accessToken) {
            return;
        }
    }

    // Fire multiple searches rapidly
    const queries = SEARCH_QUERIES.slice(0, 5);
    const responses = [];

    for (const query of queries) {
        responses.push(search(accessToken, query));
        sleep(0.05); // Small delay
    }

    let successCount = 0;
    for (const response of responses) {
        if (response.status === 200) {
            successCount++;
        }
    }

    check(null, {
        'concurrent search success rate >= 80%': () => successCount / responses.length >= 0.8
    });
}

// Empty result handling
export function emptyResultTest() {
    if (!accessToken) {
        accessToken = login();
    }

    group('Empty Result Handling', function() {
        // Query that should return no results
        const response = search(accessToken, 'xyznonexistent123456789');

        check(response, {
            'empty result status is 200': (r) => r.status === 200,
            'empty result response time < 500ms': (r) => r.timings.duration < 500,
            'empty result returns empty array': (r) => {
                try {
                    const body = JSON.parse(r.body);
                    const results = body.results || body.documents || body;
                    return Array.isArray(results) && results.length === 0;
                } catch {
                    return false;
                }
            }
        });
    });
}

// Default function
export default function() {
    searchStressTest();
}

// Setup
export function setup() {
    console.log(`Starting search stress test against ${BASE_URL}`);

    const token = login();
    if (!token) {
        console.warn('Could not login for setup');
    }

    return {
        startTime: new Date().toISOString(),
        hasAuth: token !== null
    };
}

// Teardown
export function teardown(data) {
    console.log(`Search stress test completed.`);
    console.log(`Started at: ${data.startTime}`);
}
