/**
 * K6 Load Test: Health Check Endpoint
 *
 * Target: < 50ms (p95)
 * Purpose: Validate API availability and basic responsiveness
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';
import { BASE_URL, SCENARIOS, getHeaders } from '../config.js';

// Custom metrics
const healthCheckDuration = new Trend('health_check_duration', true);
const healthCheckErrors = new Rate('health_check_errors');

// Test options
export const options = {
    scenarios: {
        health_smoke: {
            ...SCENARIOS.smoke,
            exec: 'healthCheck'
        }
    },
    thresholds: {
        'health_check_duration': ['p(95)<50', 'p(99)<100'],
        'health_check_errors': ['rate<0.01'],
        'http_req_failed': ['rate<0.01']
    },
    tags: {
        test_name: 'health_check',
        endpoint: 'health'
    }
};

// Health check test
export function healthCheck() {
    const response = http.get(`${BASE_URL}/health`, {
        headers: getHeaders(),
        tags: { endpoint: 'health' }
    });

    // Record custom metrics
    healthCheckDuration.add(response.timings.duration);

    // Validate response
    const success = check(response, {
        'status is 200': (r) => r.status === 200,
        'response time < 50ms': (r) => r.timings.duration < 50,
        'has status field': (r) => {
            try {
                const body = JSON.parse(r.body);
                return body.status !== undefined;
            } catch {
                return false;
            }
        },
        'status is healthy': (r) => {
            try {
                const body = JSON.parse(r.body);
                return body.status === 'healthy' || body.status === 'ok';
            } catch {
                return false;
            }
        }
    });

    if (!success) {
        healthCheckErrors.add(1);
    } else {
        healthCheckErrors.add(0);
    }

    // Small pause between requests
    sleep(0.1);
}

// Default function for running the test
export default function() {
    healthCheck();
}

// Setup function - runs once before the test
export function setup() {
    console.log(`Starting health check load test against ${BASE_URL}`);

    // Verify API is reachable
    const response = http.get(`${BASE_URL}/health`);
    if (response.status !== 200) {
        throw new Error(`API not reachable: ${response.status}`);
    }

    console.log('API is reachable. Starting load test...');
    return { startTime: new Date().toISOString() };
}

// Teardown function - runs once after the test
export function teardown(data) {
    console.log(`Health check load test completed.`);
    console.log(`Started at: ${data.startTime}`);
    console.log(`Ended at: ${new Date().toISOString()}`);
}
