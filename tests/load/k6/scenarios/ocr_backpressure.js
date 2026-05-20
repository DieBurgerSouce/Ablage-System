/**
 * K6 Load Test: OCR Queue Backpressure
 *
 * Testet OCR-Queue-Handling unter Last:
 * - Queue-Fuellstand
 * - GPU-Ressourcen-Monitoring
 * - Backpressure-Handling
 * - Graceful Degradation
 *
 * Performance-Ziele (aus CLAUDE.md):
 * - OCR (GPU): < 2s pro Seite
 * - OCR (CPU Fallback): < 10s pro Seite
 * - VRAM Usage: < 85%
 * - Documents/Hour: 500+ (GPU)
 *
 * Ausfuehrung:
 *   k6 run tests/load/k6/scenarios/ocr_backpressure.js
 */

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend, Counter, Gauge } from 'k6/metrics';
import { FormData } from 'https://jslib.k6.io/formdata/0.0.2/index.js';
import { BASE_URL, API_PREFIX, TEST_USER, getHeaders, randomString } from '../config.js';

// ==================== Custom Metrics ====================

// OCR processing metrics
const ocrSubmitDuration = new Trend('ocr_submit_duration', true);
const ocrProcessingDuration = new Trend('ocr_processing_duration', true);
const ocrQueueWaitTime = new Trend('ocr_queue_wait_time', true);

// Queue metrics
const queueDepth = new Gauge('queue_depth');
const queueBackpressure = new Gauge('queue_backpressure');
const activeOcrJobs = new Gauge('active_ocr_jobs');

// Error rates
const ocrSubmitErrors = new Rate('ocr_submit_errors');
const ocrProcessingErrors = new Rate('ocr_processing_errors');
const rateLimitHits = new Rate('rate_limit_hits');

// Counters
const documentsSubmitted = new Counter('documents_submitted');
const documentsProcessed = new Counter('documents_processed');
const gpuFallbacks = new Counter('gpu_fallbacks');

// Backend usage tracking
const backendUsage = {
  deepseek: new Counter('backend_deepseek'),
  got_ocr: new Counter('backend_got_ocr'),
  surya: new Counter('backend_surya'),
  surya_gpu: new Counter('backend_surya_gpu'),
  cpu_fallback: new Counter('backend_cpu_fallback'),
};

// ==================== Test Configuration ====================

export const options = {
  scenarios: {
    // Gradual ramp-up to test queue capacity
    queue_fill: {
      executor: 'ramping-arrival-rate',
      startRate: 1,
      timeUnit: '1s',
      preAllocatedVUs: 10,
      maxVUs: 50,
      stages: [
        { duration: '1m', target: 5 },    // Warm-up: 5 docs/sec
        { duration: '2m', target: 10 },   // Normal: 10 docs/sec
        { duration: '3m', target: 20 },   // High: 20 docs/sec (720/hour)
        { duration: '2m', target: 30 },   // Stress: 30 docs/sec (1080/hour)
        { duration: '2m', target: 10 },   // Recover: 10 docs/sec
        { duration: '1m', target: 0 },    // Drain
      ],
      exec: 'submitOcrJob',
    },

    // Concurrent polling for status checks
    status_polling: {
      executor: 'constant-vus',
      vus: 5,
      duration: '11m',
      exec: 'checkOcrStatus',
      startTime: '30s', // Start after some jobs are submitted
    },

    // Monitor queue health
    queue_monitor: {
      executor: 'constant-vus',
      vus: 1,
      duration: '12m',
      exec: 'monitorQueueHealth',
    },
  },

  thresholds: {
    // Submit latency
    'ocr_submit_duration': ['p(95)<500', 'p(99)<1000'],

    // Processing time (accounts for queue wait)
    'ocr_processing_duration': ['p(95)<10000', 'p(99)<30000'], // 10s p95, 30s p99

    // Queue wait time
    'ocr_queue_wait_time': ['p(95)<5000', 'avg<2000'], // 5s p95, 2s avg

    // Error rates
    'ocr_submit_errors': ['rate<0.05'],      // Max 5% submit failures
    'ocr_processing_errors': ['rate<0.10'],  // Max 10% processing failures
    'rate_limit_hits': ['rate<0.20'],        // Max 20% rate limits

    // Throughput
    'documents_submitted': ['count>100'],     // At least 100 docs submitted
  },

  tags: {
    test_name: 'ocr_backpressure',
  },
};

// ==================== Test Data ====================

// Pending job IDs for status tracking
const pendingJobs = [];
const MAX_PENDING_JOBS = 1000;

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
 * Generate minimal test PDF
 */
function generateTestPDF(pageCount = 1) {
  // Minimal valid PDF structure
  const pages = [];
  let objCount = 5;

  for (let i = 0; i < pageCount; i++) {
    const pageObj = objCount++;
    const contentObj = objCount++;
    pages.push({
      pageRef: `${pageObj} 0 R`,
      pageObj: `${pageObj} 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents ${contentObj} 0 R >> endobj`,
      contentObj: `${contentObj} 0 obj << /Length 60 >>
stream
BT /F1 12 Tf 100 700 Td (Test Page ${i + 1} - ${randomString(10)}) Tj ET
endstream
endobj`,
    });
  }

  const pdfContent = `%PDF-1.4
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

  return pdfContent;
}

/**
 * Submit document for OCR processing
 */
function submitForOcr(token, pdfContent, options = {}) {
  const fd = new FormData();
  const filename = options.filename || `ocr_test_${randomString(8)}.pdf`;

  fd.append('file', http.file(pdfContent, filename, 'application/pdf'));
  fd.append('language', options.language || 'de');

  if (options.backend) {
    fd.append('backend', options.backend);
  }

  const startTime = Date.now();

  const response = http.post(
    `${BASE_URL}${API_PREFIX}/documents/`,
    fd.body(),
    {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': `multipart/form-data; boundary=${fd.boundary}`,
      },
      tags: { endpoint: 'ocr_submit' },
      timeout: '30s',
    }
  );

  const submitDuration = Date.now() - startTime;
  ocrSubmitDuration.add(submitDuration);

  return { response, submitDuration, startTime };
}

/**
 * Check OCR job status
 */
function checkJobStatus(token, documentId) {
  const response = http.get(
    `${BASE_URL}${API_PREFIX}/documents/${documentId}/status`,
    {
      headers: getHeaders(token),
      tags: { endpoint: 'ocr_status' },
    }
  );

  return response;
}

/**
 * Get queue statistics
 */
function getQueueStats(token) {
  const response = http.get(
    `${BASE_URL}${API_PREFIX}/ocr/queue/stats`,
    {
      headers: getHeaders(token),
      tags: { endpoint: 'queue_stats' },
    }
  );

  return response;
}

/**
 * Get GPU utilization
 */
function getGpuStats(token) {
  const response = http.get(
    `${BASE_URL}${API_PREFIX}/monitoring/gpu`,
    {
      headers: getHeaders(token),
      tags: { endpoint: 'gpu_stats' },
    }
  );

  return response;
}

// ==================== Main Test Scenarios ====================

/**
 * Submit OCR job
 */
export function submitOcrJob() {
  const token = ensureAuth();

  if (!token) {
    ocrSubmitErrors.add(1);
    return;
  }

  group('Submit OCR Job', function () {
    // Random page count (1-3 pages)
    const pageCount = 1 + Math.floor(Math.random() * 3);
    const pdfContent = generateTestPDF(pageCount);

    const { response, submitDuration, startTime } = submitForOcr(token, pdfContent);

    // Check for rate limiting
    if (response.status === 429) {
      rateLimitHits.add(1);
      console.log('Rate limit hit, backing off...');
      sleep(5 + Math.random() * 5);
      return;
    }

    rateLimitHits.add(0);

    const success = check(response, {
      'submit status is 201 or 200': (r) => r.status === 201 || r.status === 200,
      'submit response time < 500ms': (r) => r.timings.duration < 500,
      'submit returns document_id': (r) => {
        try {
          const body = JSON.parse(r.body);
          return body.id !== undefined || body.document_id !== undefined;
        } catch {
          return false;
        }
      },
    });

    if (success) {
      ocrSubmitErrors.add(0);
      documentsSubmitted.add(1);

      // Track job for status polling
      try {
        const body = JSON.parse(response.body);
        const documentId = body.id || body.document_id;

        if (documentId && pendingJobs.length < MAX_PENDING_JOBS) {
          pendingJobs.push({
            id: documentId,
            submittedAt: startTime,
            pageCount: pageCount,
          });
        }
      } catch (e) {
        // Ignore parse errors
      }
    } else {
      ocrSubmitErrors.add(1);
      console.error(`Submit failed: ${response.status}`);
    }
  });

  // Small delay between submissions
  sleep(0.1);
}

/**
 * Check OCR status for pending jobs
 */
export function checkOcrStatus() {
  const token = ensureAuth();
  if (!token) return;

  // Get a pending job to check
  if (pendingJobs.length === 0) {
    sleep(1);
    return;
  }

  const job = pendingJobs[Math.floor(Math.random() * Math.min(pendingJobs.length, 100))];

  group('Check OCR Status', function () {
    const response = checkJobStatus(token, job.id);

    if (response.status === 200) {
      try {
        const body = JSON.parse(response.body);
        const status = body.status || body.ocr_status;

        // Track processing completion
        if (status === 'completed' || status === 'processed') {
          const processingTime = Date.now() - job.submittedAt;
          ocrProcessingDuration.add(processingTime);
          documentsProcessed.add(1);

          // Track backend used
          const backend = body.backend || body.ocr_backend;
          if (backend && backendUsage[backend]) {
            backendUsage[backend].add(1);
          }

          // Track GPU fallback
          if (backend === 'surya' || backend === 'cpu') {
            gpuFallbacks.add(1);
          }

          // Remove from pending
          const index = pendingJobs.findIndex(j => j.id === job.id);
          if (index > -1) {
            pendingJobs.splice(index, 1);
          }

          ocrProcessingErrors.add(0);
        } else if (status === 'failed' || status === 'error') {
          ocrProcessingErrors.add(1);

          // Remove failed job
          const index = pendingJobs.findIndex(j => j.id === job.id);
          if (index > -1) {
            pendingJobs.splice(index, 1);
          }
        } else if (status === 'queued' || status === 'pending') {
          // Track queue wait time
          const waitTime = Date.now() - job.submittedAt;
          ocrQueueWaitTime.add(waitTime);
        }
      } catch (e) {
        // Ignore parse errors
      }
    }
  });

  sleep(0.5 + Math.random() * 0.5);
}

/**
 * Monitor queue health
 */
export function monitorQueueHealth() {
  const token = ensureAuth();
  if (!token) return;

  group('Monitor Queue Health', function () {
    // Get queue stats
    const queueResponse = getQueueStats(token);

    if (queueResponse.status === 200) {
      try {
        const stats = JSON.parse(queueResponse.body);

        // Update gauges
        if (stats.pending !== undefined) {
          queueDepth.add(stats.pending);
        }
        if (stats.active !== undefined) {
          activeOcrJobs.add(stats.active);
        }
        if (stats.backpressure !== undefined) {
          queueBackpressure.add(stats.backpressure ? 1 : 0);
        }

        // Log high queue depth
        if (stats.pending > 50) {
          console.log(`Queue depth: ${stats.pending} (backpressure: ${stats.backpressure})`);
        }
      } catch (e) {
        // Endpoint may not exist in all environments
      }
    }

    // Get GPU stats
    const gpuResponse = getGpuStats(token);

    if (gpuResponse.status === 200) {
      try {
        const gpuStats = JSON.parse(gpuResponse.body);

        // Log VRAM usage if high
        if (gpuStats.vram_used_percent > 80) {
          console.warn(`High VRAM usage: ${gpuStats.vram_used_percent}%`);
        }
      } catch (e) {
        // Endpoint may not exist in all environments
      }
    }
  });

  sleep(5); // Poll every 5 seconds
}

// ==================== Lifecycle Hooks ====================

export function setup() {
  console.log('='.repeat(60));
  console.log('Starting OCR Backpressure Test');
  console.log(`Target: ${BASE_URL}`);
  console.log('Performance Goals:');
  console.log('  - OCR Submit: < 500ms');
  console.log('  - OCR Processing: < 10s (p95)');
  console.log('  - Queue Wait: < 5s (p95)');
  console.log('  - Target Throughput: 500+ docs/hour');
  console.log('='.repeat(60));

  // Verify API health
  const healthResponse = http.get(`${BASE_URL}${API_PREFIX}/health`);

  if (healthResponse.status !== 200) {
    console.error(`API health check failed: ${healthResponse.status}`);
    return { healthy: false };
  }

  // Verify auth works
  const token = ensureAuth();
  if (!token) {
    console.error('Authentication failed');
    return { healthy: false };
  }

  console.log('API health check passed');

  return {
    startTime: new Date().toISOString(),
    healthy: true,
  };
}

export function teardown(data) {
  console.log('='.repeat(60));
  console.log('OCR Backpressure Test Completed');
  console.log(`Started at: ${data.startTime}`);
  console.log(`Completed at: ${new Date().toISOString()}`);
  console.log(`Pending jobs remaining: ${pendingJobs.length}`);
  console.log('='.repeat(60));
}

// ==================== Default Export ====================

export default function () {
  submitOcrJob();
}
