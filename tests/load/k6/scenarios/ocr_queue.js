/**
 * K6 Load Test: OCR Queue Management
 *
 * Tests OCR queue behavior under various load conditions:
 * - Queue depth monitoring
 * - Job prioritization
 * - Recovery time after load spikes
 * - Graceful degradation
 *
 * Performance Targets (from CLAUDE.md):
 * - Documents/Hour: 500+ (GPU)
 * - Queue wait time: < 5s (p95)
 * - Submit latency: < 500ms (p95)
 *
 * Execution:
 *   k6 run tests/load/k6/scenarios/ocr_queue.js
 *   k6 run tests/load/k6/scenarios/ocr_queue.js --env SCENARIO=spike
 */

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend, Counter, Gauge } from 'k6/metrics';
import { SharedArray } from 'k6/data';
import { FormData } from 'https://jslib.k6.io/formdata/0.0.2/index.js';
import { BASE_URL, API_PREFIX, TEST_USER, getHeaders, randomString } from '../config.js';

// ==================== Custom Metrics ====================

// Queue metrics
const queueDepthGauge = new Gauge('ocr_queue_depth');
const queueWaitTime = new Trend('ocr_queue_wait_time', true);
const queueThroughput = new Counter('ocr_queue_throughput');

// Job metrics
const jobSubmitDuration = new Trend('ocr_job_submit_duration', true);
const jobProcessingDuration = new Trend('ocr_job_processing_duration', true);
const jobTotalDuration = new Trend('ocr_job_total_duration', true);

// Error and rate metrics
const submitErrors = new Rate('ocr_queue_submit_errors');
const processingErrors = new Rate('ocr_queue_processing_errors');
const rateLimitRate = new Rate('ocr_queue_rate_limits');
const timeoutRate = new Rate('ocr_queue_timeouts');

// Recovery metrics
const recoveryTime = new Trend('ocr_queue_recovery_time', true);

// Counters
const jobsSubmitted = new Counter('ocr_jobs_submitted');
const jobsCompleted = new Counter('ocr_jobs_completed');
const jobsFailed = new Counter('ocr_jobs_failed');

// ==================== Test Configuration ====================

// Select scenario based on environment variable
const SCENARIO_TYPE = __ENV.SCENARIO || 'sustained';

const scenarioConfigs = {
  // Sustained load: Target 500 docs/hour = ~8.3 docs/min = ~0.14 docs/sec
  sustained: {
    scenarios: {
      sustained_load: {
        executor: 'constant-arrival-rate',
        rate: 10,
        timeUnit: '1m',
        duration: '10m',
        preAllocatedVUs: 10,
        maxVUs: 50,
        exec: 'submitAndTrackJob',
      },
      queue_monitor: {
        executor: 'constant-vus',
        vus: 1,
        duration: '10m',
        exec: 'monitorQueue',
      },
    },
    thresholds: {
      'ocr_queue_wait_time': ['p(95)<5000', 'avg<2000'],
      'ocr_job_submit_duration': ['p(95)<500'],
      'ocr_queue_submit_errors': ['rate<0.05'],
      'ocr_jobs_submitted': ['count>80'],
    },
  },

  // Spike test: Sudden burst of jobs
  spike: {
    scenarios: {
      spike_load: {
        executor: 'ramping-arrival-rate',
        startRate: 5,
        timeUnit: '1m',
        preAllocatedVUs: 20,
        maxVUs: 100,
        stages: [
          { duration: '1m', target: 10 },
          { duration: '30s', target: 100 },
          { duration: '2m', target: 100 },
          { duration: '30s', target: 10 },
          { duration: '2m', target: 10 },
          { duration: '1m', target: 0 },
        ],
        exec: 'submitAndTrackJob',
      },
      queue_monitor: {
        executor: 'constant-vus',
        vus: 1,
        duration: '7m',
        exec: 'monitorQueue',
      },
      recovery_check: {
        executor: 'constant-vus',
        vus: 1,
        duration: '3m',
        startTime: '4m',
        exec: 'checkRecovery',
      },
    },
    thresholds: {
      'ocr_queue_wait_time': ['p(95)<30000'],
      'ocr_queue_recovery_time': ['avg<60000'],
      'ocr_queue_submit_errors': ['rate<0.10'],
    },
  },

  // Stress test: Push beyond capacity
  stress: {
    scenarios: {
      stress_load: {
        executor: 'ramping-arrival-rate',
        startRate: 10,
        timeUnit: '1m',
        preAllocatedVUs: 30,
        maxVUs: 200,
        stages: [
          { duration: '1m', target: 20 },
          { duration: '2m', target: 50 },
          { duration: '2m', target: 100 },
          { duration: '2m', target: 200 },
          { duration: '3m', target: 200 },
          { duration: '2m', target: 0 },
        ],
        exec: 'submitAndTrackJob',
      },
      queue_monitor: {
        executor: 'constant-vus',
        vus: 1,
        duration: '12m',
        exec: 'monitorQueue',
      },
    },
    thresholds: {
      'ocr_queue_submit_errors': ['rate<0.20'],
      'ocr_queue_rate_limits': ['rate<0.50'],
    },
  },

  // Quick smoke test
  smoke: {
    scenarios: {
      smoke_test: {
        executor: 'shared-iterations',
        vus: 2,
        iterations: 10,
        maxDuration: '2m',
        exec: 'submitAndTrackJob',
      },
    },
    thresholds: {
      'ocr_job_submit_duration': ['p(95)<1000'],
      'ocr_queue_submit_errors': ['rate<0.10'],
    },
  },
};

// Export options based on selected scenario
export const options = {
  ...scenarioConfigs[SCENARIO_TYPE],
  tags: {
    test_name: 'ocr_queue',
    scenario: SCENARIO_TYPE,
  },
};

// ==================== Test Data ====================

// Job tracking for completion monitoring
const pendingJobs = new Map();
const MAX_TRACKING = 500;

// ==================== Helper Functions ====================

let accessToken = null;
let lastQueueDepth = 0;
let spikeDetectedTime = null;
let recoveryDetectedTime = null;

/**
 * Authenticate and get access token
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
      console.error('Auth parse error');
    }
  }

  return accessToken;
}

/**
 * Generate minimal test PDF
 */
function generateTestPDF(pageCount = 1) {
  const pages = [];
  let objCount = 5;

  for (let i = 0; i < pageCount; i++) {
    const pageObj = objCount++;
    const contentObj = objCount++;
    const content = `Queue Test Page ${i + 1} - ${randomString(15)} - ${Date.now()}`;

    pages.push({
      pageRef: `${pageObj} 0 R`,
      pageObj: `${pageObj} 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents ${contentObj} 0 R >> endobj`,
      contentObj: `${contentObj} 0 obj << /Length ${44 + content.length} >>
stream
BT /F1 12 Tf 100 700 Td (${content}) Tj ET
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
 * Submit document to OCR queue
 */
function submitOcrJob(token) {
  const pageCount = Math.random() > 0.8 ? 2 : 1;
  const pdfContent = generateTestPDF(pageCount);
  const filename = `queue_test_${randomString(8)}.pdf`;

  const fd = new FormData();
  fd.append('file', http.file(pdfContent, filename, 'application/pdf'));
  fd.append('language', 'de');

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

  const duration = Date.now() - startTime;
  jobSubmitDuration.add(duration);

  return { response, startTime, pageCount };
}

/**
 * Check job status
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

// ==================== Main Test Scenarios ====================

/**
 * Submit job and track completion
 */
export function submitAndTrackJob() {
  const token = ensureAuth();
  if (!token) {
    submitErrors.add(1);
    return;
  }

  group('Submit OCR Job', function () {
    const { response, startTime, pageCount } = submitOcrJob(token);

    // Handle rate limiting
    if (response.status === 429) {
      rateLimitRate.add(1);
      submitErrors.add(0);
      sleep(2 + Math.random() * 3);
      return;
    }

    rateLimitRate.add(0);

    // Validate submission
    const success = check(response, {
      'submit returns 200 or 201': (r) => r.status === 200 || r.status === 201,
      'submit has document id': (r) => {
        try {
          const body = JSON.parse(r.body);
          return body.id || body.document_id;
        } catch {
          return false;
        }
      },
    });

    if (success) {
      submitErrors.add(0);
      jobsSubmitted.add(1);

      // Track job for completion monitoring
      try {
        const body = JSON.parse(response.body);
        const docId = body.id || body.document_id;

        if (docId && pendingJobs.size < MAX_TRACKING) {
          pendingJobs.set(docId, {
            submittedAt: startTime,
            pageCount: pageCount,
          });
        }
      } catch (e) {
        // Continue without tracking
      }
    } else {
      submitErrors.add(1);
      console.error(`Submit failed: ${response.status}`);
    }
  });

  // Check status of random pending jobs
  if (pendingJobs.size > 0 && Math.random() > 0.5) {
    group('Check Job Status', function () {
      const jobIds = Array.from(pendingJobs.keys());
      const jobId = jobIds[Math.floor(Math.random() * Math.min(jobIds.length, 20))];
      const jobInfo = pendingJobs.get(jobId);

      if (!jobInfo) return;

      const response = checkJobStatus(token, jobId);

      if (response.status === 200) {
        try {
          const body = JSON.parse(response.body);
          const status = body.status || body.ocr_status;

          if (status === 'completed' || status === 'processed') {
            const totalTime = Date.now() - jobInfo.submittedAt;
            const processingTime = body.processing_time_ms || totalTime;
            const waitTime = totalTime - processingTime;

            jobTotalDuration.add(totalTime);
            jobProcessingDuration.add(processingTime);
            queueWaitTime.add(Math.max(0, waitTime));

            jobsCompleted.add(1);
            queueThroughput.add(1);
            processingErrors.add(0);

            pendingJobs.delete(jobId);
          } else if (status === 'failed' || status === 'error') {
            jobsFailed.add(1);
            processingErrors.add(1);
            pendingJobs.delete(jobId);
          } else if (status === 'queued' || status === 'pending') {
            // Still waiting - track queue time
            const currentWait = Date.now() - jobInfo.submittedAt;
            queueWaitTime.add(currentWait);
          }
        } catch (e) {
          // Ignore parse errors
        }
      }
    });
  }

  sleep(0.1 + Math.random() * 0.2);
}

/**
 * Monitor queue status
 */
export function monitorQueue() {
  const token = ensureAuth();
  if (!token) return;

  group('Monitor Queue', function () {
    const response = getQueueStats(token);

    if (response.status === 200) {
      try {
        const stats = JSON.parse(response.body);

        const depth = stats.pending || stats.queue_depth || 0;
        queueDepthGauge.add(depth);

        // Detect spike (queue depth > 50)
        if (depth > 50 && !spikeDetectedTime) {
          spikeDetectedTime = Date.now();
          console.log(`Queue spike detected: depth=${depth}`);
        }

        // Detect recovery (queue depth back to < 10 after spike)
        if (spikeDetectedTime && depth < 10 && !recoveryDetectedTime) {
          recoveryDetectedTime = Date.now();
          const recTime = recoveryDetectedTime - spikeDetectedTime;
          recoveryTime.add(recTime);
          console.log(`Queue recovered in ${recTime}ms`);

          // Reset for next spike
          spikeDetectedTime = null;
          recoveryDetectedTime = null;
        }

        lastQueueDepth = depth;

        // Log periodically
        if (Math.random() > 0.9) {
          console.log(`Queue status: pending=${depth}, active=${stats.active || 0}`);
        }
      } catch (e) {
        // Queue stats endpoint may not exist
      }
    }
  });

  sleep(5);
}

/**
 * Check recovery after spike
 */
export function checkRecovery() {
  const token = ensureAuth();
  if (!token) return;

  group('Check Recovery', function () {
    // Submit a single job and measure total time
    const { response, startTime } = submitOcrJob(token);

    if (response.status === 200 || response.status === 201) {
      try {
        const body = JSON.parse(response.body);
        const docId = body.id || body.document_id;

        // Poll until complete (max 60 seconds)
        const maxWait = 60000;
        const pollInterval = 2000;
        let elapsed = 0;

        while (elapsed < maxWait) {
          sleep(pollInterval / 1000);
          elapsed += pollInterval;

          const statusResponse = checkJobStatus(token, docId);
          if (statusResponse.status === 200) {
            const statusBody = JSON.parse(statusResponse.body);
            const status = statusBody.status || statusBody.ocr_status;

            if (status === 'completed' || status === 'processed') {
              const totalTime = Date.now() - startTime;
              recoveryTime.add(totalTime);
              console.log(`Recovery test job completed in ${totalTime}ms`);
              return;
            } else if (status === 'failed' || status === 'error') {
              console.log('Recovery test job failed');
              return;
            }
          }
        }

        console.log('Recovery test job timed out');
        timeoutRate.add(1);
      } catch (e) {
        console.error('Recovery check error');
      }
    }
  });

  sleep(10);
}

// ==================== Lifecycle Hooks ====================

export function setup() {
  console.log('='.repeat(60));
  console.log('Starting OCR Queue Load Test');
  console.log(`Scenario: ${SCENARIO_TYPE}`);
  console.log(`Target: ${BASE_URL}`);
  console.log('='.repeat(60));

  // Verify API health
  const healthResponse = http.get(`${BASE_URL}${API_PREFIX}/health`);
  if (healthResponse.status !== 200) {
    console.error(`API health check failed: ${healthResponse.status}`);
    return { healthy: false };
  }

  // Verify auth
  const token = ensureAuth();
  if (!token) {
    console.error('Authentication failed');
    return { healthy: false };
  }

  console.log('Setup complete - starting test');

  return {
    startTime: new Date().toISOString(),
    healthy: true,
    scenario: SCENARIO_TYPE,
  };
}

export function teardown(data) {
  console.log('='.repeat(60));
  console.log('OCR Queue Load Test Completed');
  console.log(`Scenario: ${data.scenario}`);
  console.log(`Started: ${data.startTime}`);
  console.log(`Completed: ${new Date().toISOString()}`);
  console.log(`Pending jobs at end: ${pendingJobs.size}`);
  console.log('='.repeat(60));
}

// ==================== Default Export ====================

export default function () {
  submitAndTrackJob();
}
