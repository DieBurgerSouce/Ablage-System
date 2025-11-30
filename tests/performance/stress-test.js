// k6 Stress Test - Ablage-System OCR API
// Testet System-Grenzen und Verhalten unter extremer Last
//
// Ausfuehrung:
//   k6 run tests/performance/stress-test.js

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

const errorRate = new Rate('errors');

// Stress Test Configuration - Pushing limits
export const options = {
  stages: [
    { duration: '2m', target: 50 },    // Ramp up
    { duration: '5m', target: 50 },    // Stay
    { duration: '2m', target: 100 },   // Increase
    { duration: '5m', target: 100 },   // Stay
    { duration: '2m', target: 150 },   // Push harder
    { duration: '5m', target: 150 },   // Stay at stress level
    { duration: '2m', target: 200 },   // Breaking point test
    { duration: '3m', target: 200 },   // Stay at breaking point
    { duration: '5m', target: 0 },     // Recovery
  ],

  thresholds: {
    http_req_duration: ['p(95)<5000'],    // Relaxed for stress test
    http_req_failed: ['rate<0.15'],       // Allow more errors
    errors: ['rate<0.2'],
  },

  tags: {
    testType: 'stress',
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';

export default function() {
  // Rapid health checks
  const healthRes = http.get(`${BASE_URL}/health`);
  check(healthRes, {
    'status is 200': (r) => r.status === 200,
  }) || errorRate.add(1);

  // API root
  const rootRes = http.get(`${BASE_URL}/`);
  check(rootRes, {
    'root is 200': (r) => r.status === 200,
  }) || errorRate.add(1);

  // Metrics endpoint (can be slow under load)
  const metricsRes = http.get(`${BASE_URL}/api/v1/metrics`);
  check(metricsRes, {
    'metrics accessible': (r) => r.status === 200 || r.status === 503,
  }) || errorRate.add(1);

  // Minimal sleep for maximum stress
  sleep(0.1);
}
