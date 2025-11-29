/**
 * K6 Load Testing Configuration for Ablage-System
 *
 * Performance Targets (from CLAUDE.md):
 * - API Health Check: < 50ms (p95)
 * - Document Upload: < 500ms (p95)
 * - OCR Processing: < 2s GPU, < 10s CPU (p95)
 * - Search Query: < 500ms (p95)
 */

// Base URL for API
export const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
export const API_PREFIX = '/api/v1';

// Test user credentials
export const TEST_USER = {
    email: __ENV.TEST_EMAIL || 'loadtest@ablage-system.local',
    password: __ENV.TEST_PASSWORD || 'LoadTest123!@#'
};

// Performance thresholds (in milliseconds)
export const THRESHOLDS = {
    // Response time thresholds
    health_check_p95: 50,
    document_upload_p95: 500,
    ocr_processing_gpu_p95: 2000,
    ocr_processing_cpu_p95: 10000,
    search_query_p95: 500,
    auth_login_p95: 200,

    // Error rate thresholds
    error_rate: 0.01,  // Max 1% error rate

    // Throughput thresholds
    min_requests_per_second: 10
};

// Load test scenarios
export const SCENARIOS = {
    // Smoke test: Quick validation
    smoke: {
        executor: 'constant-vus',
        vus: 1,
        duration: '30s'
    },

    // Load test: Normal load
    load: {
        executor: 'ramping-vus',
        startVUs: 0,
        stages: [
            { duration: '1m', target: 10 },   // Ramp up
            { duration: '3m', target: 10 },   // Stay at 10
            { duration: '1m', target: 20 },   // Ramp up more
            { duration: '3m', target: 20 },   // Stay at 20
            { duration: '1m', target: 0 }     // Ramp down
        ]
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
            { duration: '5m', target: 100 },  // Stay at peak
            { duration: '2m', target: 0 }
        ]
    },

    // Spike test: Sudden traffic spike
    spike: {
        executor: 'ramping-vus',
        startVUs: 0,
        stages: [
            { duration: '30s', target: 5 },
            { duration: '10s', target: 100 },  // Spike!
            { duration: '1m', target: 100 },
            { duration: '10s', target: 5 },
            { duration: '30s', target: 0 }
        ]
    },

    // Soak test: Extended duration
    soak: {
        executor: 'constant-vus',
        vus: 20,
        duration: '30m'
    }
};

// Common K6 options
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
        'http_req_duration{endpoint:ocr}': ['p(95)<10000']
    },

    // Tags for grouping
    tags: {
        environment: __ENV.ENVIRONMENT || 'development',
        test_type: __ENV.TEST_TYPE || 'load'
    }
};

// Helper functions
export function getUrl(path) {
    return `${BASE_URL}${API_PREFIX}${path}`;
}

export function getHeaders(token = null) {
    const headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    };

    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    return headers;
}

// Random data generators
export function randomString(length = 10) {
    const chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
    let result = '';
    for (let i = 0; i < length; i++) {
        result += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return result;
}

export function randomGermanText() {
    const texts = [
        'Dies ist ein Testdokument mit Umlauten: äöüß',
        'Rechnung Nr. 2024-001 über 1.234,56 EUR',
        'Sehr geehrte Damen und Herren',
        'Mit freundlichen Grüßen, Müller GmbH',
        'Lieferadresse: Hauptstraße 123, 12345 Berlin'
    ];
    return texts[Math.floor(Math.random() * texts.length)];
}

export function randomDocumentType() {
    const types = ['invoice', 'contract', 'letter', 'report', 'other'];
    return types[Math.floor(Math.random() * types.length)];
}
