/**
 * K6 Load Test: Authentication Flow
 *
 * Tests:
 * - Login endpoint performance
 * - Token refresh
 * - Rate limiting under load
 *
 * Target: Login < 200ms (p95)
 */

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';
import { BASE_URL, API_PREFIX, TEST_USER, SCENARIOS, getHeaders, randomString } from '../config.js';

// Custom metrics
const loginDuration = new Trend('auth_login_duration', true);
const refreshDuration = new Trend('auth_refresh_duration', true);
const authErrors = new Rate('auth_errors');
const rateLimitHits = new Counter('rate_limit_hits');

// Store tokens for reuse
let authTokens = null;

// Test options
export const options = {
    scenarios: {
        auth_load: {
            ...SCENARIOS.load,
            exec: 'authFlow'
        }
    },
    thresholds: {
        'auth_login_duration': ['p(95)<200', 'p(99)<500'],
        'auth_refresh_duration': ['p(95)<150', 'p(99)<300'],
        'auth_errors': ['rate<0.05'],
        'http_req_failed': ['rate<0.05']
    },
    tags: {
        test_name: 'auth_flow'
    }
};

// Login function
function login(email, password) {
    const payload = JSON.stringify({
        email: email,
        password: password
    });

    const response = http.post(
        `${BASE_URL}${API_PREFIX}/auth/login`,
        payload,
        {
            headers: getHeaders(),
            tags: { endpoint: 'login' }
        }
    );

    loginDuration.add(response.timings.duration);

    return response;
}

// Token refresh function
function refreshToken(refreshToken) {
    const payload = JSON.stringify({
        refresh_token: refreshToken
    });

    const response = http.post(
        `${BASE_URL}${API_PREFIX}/auth/refresh`,
        payload,
        {
            headers: getHeaders(),
            tags: { endpoint: 'refresh' }
        }
    );

    refreshDuration.add(response.timings.duration);

    return response;
}

// Get current user info
function getCurrentUser(accessToken) {
    const response = http.get(
        `${BASE_URL}${API_PREFIX}/auth/me`,
        {
            headers: getHeaders(accessToken),
            tags: { endpoint: 'me' }
        }
    );

    return response;
}

// Main auth flow test
export function authFlow() {
    group('Login Flow', function() {
        // Attempt login
        const loginResponse = login(TEST_USER.email, TEST_USER.password);

        const loginSuccess = check(loginResponse, {
            'login status is 200': (r) => r.status === 200,
            'login response time < 200ms': (r) => r.timings.duration < 200,
            'login returns access_token': (r) => {
                try {
                    const body = JSON.parse(r.body);
                    return body.access_token !== undefined;
                } catch {
                    return false;
                }
            },
            'login returns refresh_token': (r) => {
                try {
                    const body = JSON.parse(r.body);
                    return body.refresh_token !== undefined;
                } catch {
                    return false;
                }
            }
        });

        if (loginResponse.status === 429) {
            rateLimitHits.add(1);
            console.log('Rate limit hit during login');
            sleep(5); // Back off
            return;
        }

        if (!loginSuccess) {
            authErrors.add(1);
            return;
        }

        authErrors.add(0);

        // Parse tokens
        try {
            const body = JSON.parse(loginResponse.body);
            authTokens = {
                access: body.access_token,
                refresh: body.refresh_token
            };
        } catch (e) {
            console.error('Failed to parse login response');
            return;
        }

        sleep(0.5);
    });

    if (!authTokens) {
        return;
    }

    group('Get Current User', function() {
        const meResponse = getCurrentUser(authTokens.access);

        check(meResponse, {
            'me status is 200': (r) => r.status === 200,
            'me returns user data': (r) => {
                try {
                    const body = JSON.parse(r.body);
                    return body.email !== undefined;
                } catch {
                    return false;
                }
            }
        });

        sleep(0.3);
    });

    group('Token Refresh', function() {
        const refreshResponse = refreshToken(authTokens.refresh);

        const refreshSuccess = check(refreshResponse, {
            'refresh status is 200': (r) => r.status === 200,
            'refresh response time < 150ms': (r) => r.timings.duration < 150,
            'refresh returns new tokens': (r) => {
                try {
                    const body = JSON.parse(r.body);
                    return body.access_token !== undefined;
                } catch {
                    return false;
                }
            }
        });

        if (refreshResponse.status === 429) {
            rateLimitHits.add(1);
        }

        if (!refreshSuccess) {
            authErrors.add(1);
        }

        sleep(0.5);
    });
}

// Rate limit attack test
export function authFlood() {
    // Rapid-fire login attempts to test rate limiting
    for (let i = 0; i < 10; i++) {
        const response = login(
            `attacker${randomString(5)}@example.com`,
            'WrongPassword123!'
        );

        if (response.status === 429) {
            rateLimitHits.add(1);
            console.log('Rate limiter working correctly');
            break;
        }

        sleep(0.1);
    }
}

// Default function
export default function() {
    authFlow();
}

// Setup
export function setup() {
    console.log(`Starting auth flow load test against ${BASE_URL}`);

    // Verify login endpoint is available
    const response = http.post(
        `${BASE_URL}${API_PREFIX}/auth/login`,
        JSON.stringify({
            email: 'test@test.com',
            password: 'test'
        }),
        { headers: getHeaders() }
    );

    // 401 is expected for wrong credentials
    if (response.status !== 401 && response.status !== 200 && response.status !== 429) {
        console.warn(`Unexpected response from login endpoint: ${response.status}`);
    }

    return { startTime: new Date().toISOString() };
}

// Teardown
export function teardown(data) {
    console.log(`Auth flow load test completed.`);
    console.log(`Started at: ${data.startTime}`);
}
