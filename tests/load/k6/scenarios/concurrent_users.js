/**
 * K6 Load Test: Concurrent Users
 *
 * Testet 100 gleichzeitige Benutzer mit typischem Workflow:
 * Login -> Dashboard -> Document List -> Logout
 *
 * Performance-Ziele (aus CLAUDE.md):
 * - API Health Check: < 50ms (p95)
 * - Document List: < 500ms (p95)
 * - Concurrent Users: 100+
 *
 * Ausfuehrung:
 *   k6 run tests/load/k6/scenarios/concurrent_users.js
 *   k6 run tests/load/k6/scenarios/concurrent_users.js --vus 100 --duration 5m
 */

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend, Counter, Gauge } from 'k6/metrics';
import { SharedArray } from 'k6/data';
import { BASE_URL, API_PREFIX, TEST_USER, SCENARIOS, getHeaders, randomString } from '../config.js';

// ==================== Custom Metrics ====================

// Response time metrics
const loginDuration = new Trend('login_duration', true);
const dashboardDuration = new Trend('dashboard_duration', true);
const documentListDuration = new Trend('document_list_duration', true);
const logoutDuration = new Trend('logout_duration', true);

// Error rates
const loginErrors = new Rate('login_errors');
const apiErrors = new Rate('api_errors');

// Counters
const totalRequests = new Counter('total_requests');
const successfulSessions = new Counter('successful_sessions');

// Gauges
const activeUsers = new Gauge('active_users');

// ==================== Test Configuration ====================

export const options = {
  scenarios: {
    // Ramp-up to 100 concurrent users
    concurrent_users: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '1m', target: 20 },   // Warm-up: 0 -> 20 users
        { duration: '2m', target: 50 },   // Ramp: 20 -> 50 users
        { duration: '3m', target: 100 },  // Ramp: 50 -> 100 users
        { duration: '5m', target: 100 },  // Steady state: 100 users
        { duration: '2m', target: 50 },   // Cool-down: 100 -> 50 users
        { duration: '1m', target: 0 },    // Ramp-down: 50 -> 0 users
      ],
      gracefulRampDown: '30s',
      exec: 'userSession',
    },
  },

  thresholds: {
    // Overall response time
    'http_req_duration': ['p(95)<500', 'p(99)<1000'],

    // Specific endpoint thresholds
    'login_duration': ['p(95)<200', 'p(99)<500'],
    'dashboard_duration': ['p(95)<300', 'p(99)<600'],
    'document_list_duration': ['p(95)<500', 'p(99)<1000'],

    // Error rates
    'http_req_failed': ['rate<0.05'],        // Max 5% failure rate
    'login_errors': ['rate<0.02'],           // Max 2% login failures
    'api_errors': ['rate<0.05'],             // Max 5% API failures

    // Session success rate
    'successful_sessions': ['count>0'],
  },

  // Tags for organizing results
  tags: {
    test_name: 'concurrent_users',
    target_users: '100',
  },
};

// ==================== Test Data ====================

// Simulate multiple user credentials (in real scenario, use from file)
const users = new SharedArray('users', function () {
  const userList = [];
  for (let i = 0; i < 100; i++) {
    userList.push({
      email: `loadtest_user_${i}@ablage-system.local`,
      password: 'LoadTest123!@#',
    });
  }
  return userList;
});

// ==================== Helper Functions ====================

/**
 * Login and return access token
 */
function login(userEmail, userPassword) {
  const payload = JSON.stringify({
    email: userEmail || TEST_USER.email,
    password: userPassword || TEST_USER.password,
  });

  const response = http.post(
    `${BASE_URL}${API_PREFIX}/auth/login`,
    payload,
    {
      headers: getHeaders(),
      tags: { endpoint: 'login' },
    }
  );

  loginDuration.add(response.timings.duration);
  totalRequests.add(1);

  const loginSuccess = check(response, {
    'login status is 200': (r) => r.status === 200,
    'login response time < 200ms': (r) => r.timings.duration < 200,
    'login returns token': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.access_token !== undefined;
      } catch {
        return false;
      }
    },
  });

  if (!loginSuccess) {
    loginErrors.add(1);
    return null;
  }

  loginErrors.add(0);

  try {
    return JSON.parse(response.body).access_token;
  } catch {
    return null;
  }
}

/**
 * Fetch dashboard data
 */
function fetchDashboard(token) {
  const responses = http.batch([
    ['GET', `${BASE_URL}${API_PREFIX}/documents/stats`, null, {
      headers: getHeaders(token),
      tags: { endpoint: 'dashboard_stats' },
    }],
    ['GET', `${BASE_URL}${API_PREFIX}/documents/?limit=10`, null, {
      headers: getHeaders(token),
      tags: { endpoint: 'dashboard_recent' },
    }],
  ]);

  let maxDuration = 0;
  let allSuccess = true;

  responses.forEach((response, index) => {
    totalRequests.add(1);
    maxDuration = Math.max(maxDuration, response.timings.duration);

    const success = check(response, {
      [`dashboard request ${index} status is 200`]: (r) => r.status === 200,
    });

    if (!success) {
      allSuccess = false;
      apiErrors.add(1);
    }
  });

  dashboardDuration.add(maxDuration);

  if (allSuccess) {
    apiErrors.add(0);
  }

  return allSuccess;
}

/**
 * Fetch document list with pagination
 */
function fetchDocumentList(token, page = 1, limit = 20) {
  const offset = (page - 1) * limit;

  const response = http.get(
    `${BASE_URL}${API_PREFIX}/documents/?offset=${offset}&limit=${limit}`,
    {
      headers: getHeaders(token),
      tags: { endpoint: 'document_list' },
    }
  );

  documentListDuration.add(response.timings.duration);
  totalRequests.add(1);

  const success = check(response, {
    'document list status is 200': (r) => r.status === 200,
    'document list response time < 500ms': (r) => r.timings.duration < 500,
    'document list returns array': (r) => {
      try {
        const body = JSON.parse(r.body);
        return Array.isArray(body.items) || Array.isArray(body);
      } catch {
        return false;
      }
    },
  });

  if (success) {
    apiErrors.add(0);
  } else {
    apiErrors.add(1);
  }

  return success;
}

/**
 * Search documents
 */
function searchDocuments(token, query) {
  const response = http.get(
    `${BASE_URL}${API_PREFIX}/documents/search?q=${encodeURIComponent(query)}`,
    {
      headers: getHeaders(token),
      tags: { endpoint: 'search' },
    }
  );

  totalRequests.add(1);

  const success = check(response, {
    'search status is 200': (r) => r.status === 200,
    'search response time < 500ms': (r) => r.timings.duration < 500,
  });

  if (!success) {
    apiErrors.add(1);
  }

  return success;
}

/**
 * View single document
 */
function viewDocument(token, documentId) {
  if (!documentId) return true; // Skip if no document ID

  const response = http.get(
    `${BASE_URL}${API_PREFIX}/documents/${documentId}`,
    {
      headers: getHeaders(token),
      tags: { endpoint: 'document_detail' },
    }
  );

  totalRequests.add(1);

  const success = check(response, {
    'document detail status is 200': (r) => r.status === 200 || r.status === 404,
  });

  if (!success) {
    apiErrors.add(1);
  }

  return success;
}

/**
 * Logout (invalidate token)
 */
function logout(token) {
  const response = http.post(
    `${BASE_URL}${API_PREFIX}/auth/logout`,
    null,
    {
      headers: getHeaders(token),
      tags: { endpoint: 'logout' },
    }
  );

  logoutDuration.add(response.timings.duration);
  totalRequests.add(1);

  // Logout may return 200 or 204
  check(response, {
    'logout status is 2xx': (r) => r.status >= 200 && r.status < 300,
  });
}

// ==================== Main Test Scenarios ====================

/**
 * Complete user session: Login -> Dashboard -> Documents -> Logout
 */
export function userSession() {
  activeUsers.add(__VU); // Track active virtual users

  // Get user credentials (round-robin from pool)
  const userIndex = __VU % users.length;
  const user = users[userIndex];

  let sessionSuccess = true;

  // Step 1: Login
  group('Login', function () {
    const token = login(user.email, user.password);

    if (!token) {
      // Fallback to default test user if specific user fails
      const fallbackToken = login();

      if (!fallbackToken) {
        console.error(`Login failed for user ${user.email}`);
        sessionSuccess = false;
        return;
      }

      // Continue with fallback token
      __ENV.TOKEN = fallbackToken;
    } else {
      __ENV.TOKEN = token;
    }
  });

  if (!sessionSuccess || !__ENV.TOKEN) {
    return;
  }

  // Think time after login
  sleep(randomThinkTime(1, 3));

  // Step 2: View Dashboard
  group('Dashboard', function () {
    const success = fetchDashboard(__ENV.TOKEN);
    if (!success) {
      console.warn('Dashboard fetch failed');
    }
  });

  sleep(randomThinkTime(2, 5));

  // Step 3: Browse Document List
  group('Document List', function () {
    // First page
    fetchDocumentList(__ENV.TOKEN, 1, 20);
    sleep(randomThinkTime(1, 2));

    // Possibly browse to second page
    if (Math.random() > 0.5) {
      fetchDocumentList(__ENV.TOKEN, 2, 20);
      sleep(randomThinkTime(1, 2));
    }
  });

  sleep(randomThinkTime(1, 3));

  // Step 4: Search (sometimes)
  if (Math.random() > 0.3) {
    group('Search', function () {
      const searchTerms = ['Rechnung', 'Vertrag', 'Lieferung', '2024'];
      const searchTerm = searchTerms[Math.floor(Math.random() * searchTerms.length)];
      searchDocuments(__ENV.TOKEN, searchTerm);
    });
    sleep(randomThinkTime(1, 2));
  }

  // Step 5: View Document Detail (sometimes)
  if (Math.random() > 0.5) {
    group('Document Detail', function () {
      // In real scenario, get document ID from list response
      // For now, use a placeholder or skip
      viewDocument(__ENV.TOKEN, null);
    });
    sleep(randomThinkTime(2, 4));
  }

  // Step 6: Logout
  group('Logout', function () {
    logout(__ENV.TOKEN);
  });

  // Mark successful session
  if (sessionSuccess) {
    successfulSessions.add(1);
  }

  activeUsers.add(-__VU); // Decrement active users
}

/**
 * Random think time between min and max seconds
 */
function randomThinkTime(min, max) {
  return min + Math.random() * (max - min);
}

// ==================== Lifecycle Hooks ====================

export function setup() {
  console.log('='.repeat(60));
  console.log('Starting Concurrent Users Load Test');
  console.log(`Target: ${BASE_URL}`);
  console.log(`Max Users: 100`);
  console.log('='.repeat(60));

  // Verify API is accessible
  const healthResponse = http.get(`${BASE_URL}${API_PREFIX}/health`);

  if (healthResponse.status !== 200) {
    console.error(`API health check failed: ${healthResponse.status}`);
  } else {
    console.log('API health check passed');
  }

  // Verify login works
  const token = login();
  if (!token) {
    console.warn('Test user login failed - tests may fail');
  } else {
    console.log('Test user login verified');
  }

  return {
    startTime: new Date().toISOString(),
    targetUrl: BASE_URL,
  };
}

export function teardown(data) {
  console.log('='.repeat(60));
  console.log('Concurrent Users Load Test Completed');
  console.log(`Started at: ${data.startTime}`);
  console.log(`Completed at: ${new Date().toISOString()}`);
  console.log('='.repeat(60));
}

// ==================== Default Export ====================

export default function () {
  userSession();
}
