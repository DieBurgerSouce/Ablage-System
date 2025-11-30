// k6 Load Test - Ablage-System OCR API
// Performance und Lasttest fuer die API-Endpoints
//
// Ausfuehrung:
//   k6 run tests/performance/load-test.js
//   k6 run --vus 50 --duration 5m tests/performance/load-test.js

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

// Custom Metrics
const errorRate = new Rate('errors');
const successfulLogins = new Counter('successful_logins');
const documentUploads = new Counter('document_uploads');
const ocrProcessingTime = new Trend('ocr_processing_time');

// Test Configuration
export const options = {
  // Stages define load ramp-up/down pattern
  stages: [
    { duration: '1m', target: 10 },   // Ramp up to 10 users
    { duration: '3m', target: 10 },   // Stay at 10 users
    { duration: '1m', target: 25 },   // Ramp up to 25 users
    { duration: '3m', target: 25 },   // Stay at 25 users
    { duration: '1m', target: 50 },   // Spike to 50 users
    { duration: '2m', target: 50 },   // Stay at 50 users
    { duration: '1m', target: 0 },    // Ramp down
  ],

  // Thresholds define pass/fail criteria
  thresholds: {
    http_req_duration: ['p(95)<2000'],        // 95% of requests < 2s
    http_req_failed: ['rate<0.05'],           // Error rate < 5%
    errors: ['rate<0.1'],                     // Custom error rate < 10%
    'http_req_duration{endpoint:health}': ['p(99)<500'],  // Health check < 500ms
    'http_req_duration{endpoint:login}': ['p(95)<1000'],  // Login < 1s
    'http_req_duration{endpoint:documents}': ['p(95)<3000'], // Documents < 3s
  },

  // Tags for better metrics grouping
  tags: {
    testType: 'load',
  },
};

// Environment Variables
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const TEST_USER = __ENV.TEST_USER || 'loadtest@example.com';
const TEST_PASSWORD = __ENV.TEST_PASSWORD || 'LoadTest123!';

// Shared state
let authToken = null;

// Setup - runs once before all VUs start
export function setup() {
  console.log(`Starting load test against ${BASE_URL}`);

  // Register test user if needed
  const registerRes = http.post(`${BASE_URL}/api/v1/auth/register`, JSON.stringify({
    email: TEST_USER,
    password: TEST_PASSWORD,
    name: 'Load Test User',
  }), {
    headers: { 'Content-Type': 'application/json' },
  });

  // Login to get token
  const loginRes = http.post(`${BASE_URL}/api/v1/auth/login`, JSON.stringify({
    email: TEST_USER,
    password: TEST_PASSWORD,
  }), {
    headers: { 'Content-Type': 'application/json' },
  });

  if (loginRes.status === 200) {
    const body = JSON.parse(loginRes.body);
    return { token: body.access_token };
  }

  console.error('Setup failed: Could not authenticate');
  return { token: null };
}

// Main test scenario
export default function(data) {
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': data.token ? `Bearer ${data.token}` : '',
  };

  // Group 1: Health Checks (unauthenticated)
  group('Health Checks', function() {
    const healthRes = http.get(`${BASE_URL}/health`, {
      tags: { endpoint: 'health' },
    });

    check(healthRes, {
      'health check returns 200': (r) => r.status === 200,
      'health check has status': (r) => JSON.parse(r.body).status !== undefined,
    }) || errorRate.add(1);

    sleep(0.5);
  });

  // Group 2: Authentication
  group('Authentication', function() {
    // Login
    const loginRes = http.post(`${BASE_URL}/api/v1/auth/login`, JSON.stringify({
      email: TEST_USER,
      password: TEST_PASSWORD,
    }), {
      headers: { 'Content-Type': 'application/json' },
      tags: { endpoint: 'login' },
    });

    const loginSuccess = check(loginRes, {
      'login returns 200': (r) => r.status === 200,
      'login returns token': (r) => {
        try {
          return JSON.parse(r.body).access_token !== undefined;
        } catch {
          return false;
        }
      },
    });

    if (loginSuccess) {
      successfulLogins.add(1);
    } else {
      errorRate.add(1);
    }

    sleep(1);
  });

  // Skip authenticated tests if no token
  if (!data.token) {
    return;
  }

  // Group 3: Document Operations
  group('Document Operations', function() {
    // List documents
    const listRes = http.get(`${BASE_URL}/api/v1/documents`, {
      headers: headers,
      tags: { endpoint: 'documents' },
    });

    check(listRes, {
      'list documents returns 200': (r) => r.status === 200,
      'list documents returns array': (r) => {
        try {
          const body = JSON.parse(r.body);
          return Array.isArray(body.documents || body);
        } catch {
          return false;
        }
      },
    }) || errorRate.add(1);

    sleep(0.5);

    // Get document stats
    const statsRes = http.get(`${BASE_URL}/api/v1/documents/stats`, {
      headers: headers,
      tags: { endpoint: 'stats' },
    });

    check(statsRes, {
      'stats returns 200 or 404': (r) => r.status === 200 || r.status === 404,
    }) || errorRate.add(1);

    sleep(0.5);
  });

  // Group 4: Search Operations
  group('Search Operations', function() {
    const searchRes = http.get(`${BASE_URL}/api/v1/search?q=test&limit=10`, {
      headers: headers,
      tags: { endpoint: 'search' },
    });

    check(searchRes, {
      'search returns 200': (r) => r.status === 200 || r.status === 404,
    }) || errorRate.add(1);

    sleep(0.5);
  });

  // Group 5: Batch Jobs (if any exist)
  group('Batch Jobs', function() {
    const batchRes = http.get(`${BASE_URL}/api/v1/batch-jobs`, {
      headers: headers,
      tags: { endpoint: 'batch-jobs' },
    });

    check(batchRes, {
      'batch jobs returns 200': (r) => r.status === 200,
    }) || errorRate.add(1);

    sleep(0.5);
  });

  // Group 6: Metrics Endpoints
  group('Metrics', function() {
    const metricsRes = http.get(`${BASE_URL}/api/v1/metrics/business`, {
      headers: headers,
      tags: { endpoint: 'metrics' },
    });

    check(metricsRes, {
      'metrics returns 200': (r) => r.status === 200,
    }) || errorRate.add(1);

    sleep(0.5);
  });

  // Random sleep between iterations (1-3 seconds)
  sleep(Math.random() * 2 + 1);
}

// Teardown - runs once after all VUs finish
export function teardown(data) {
  console.log('Load test completed');
}
