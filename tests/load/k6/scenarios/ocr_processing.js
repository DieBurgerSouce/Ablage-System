/**
 * K6 Load Test: OCR Processing Performance
 *
 * Target: < 2s GPU (p95), < 10s CPU (p95)
 * Purpose: Test OCR processing throughput and response times
 */

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';
import { FormData } from 'https://jslib.k6.io/formdata/0.0.2/index.js';
import { BASE_URL, API_PREFIX, TEST_USER, SCENARIOS, getHeaders, randomString } from '../config.js';

// Custom metrics
const ocrDuration = new Trend('ocr_processing_duration', true);
const ocrGpuDuration = new Trend('ocr_gpu_duration', true);
const ocrCpuDuration = new Trend('ocr_cpu_duration', true);
const ocrErrors = new Rate('ocr_errors');
const ocrJobsStarted = new Counter('ocr_jobs_started');
const ocrJobsCompleted = new Counter('ocr_jobs_completed');

// Auth token
let accessToken = null;

// Test options
export const options = {
    scenarios: {
        ocr_load: {
            executor: 'constant-vus',
            vus: 5,
            duration: '5m',
            exec: 'ocrProcessingTest'
        }
    },
    thresholds: {
        'ocr_processing_duration': ['p(95)<10000'],
        'ocr_gpu_duration': ['p(95)<2000'],
        'ocr_cpu_duration': ['p(95)<10000'],
        'ocr_errors': ['rate<0.1'],
        'http_req_failed': ['rate<0.1']
    },
    tags: {
        test_name: 'ocr_processing',
        endpoint: 'ocr'
    }
};

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

// Generate test document
function generateTestDocument() {
    // Minimal PDF with German text
    const germanText = 'Rechnung Nr. ' + randomString(6);
    return `%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >> endobj
4 0 obj << /Length 100 >>
stream
BT /F1 12 Tf 100 700 Td (${germanText}) Tj 100 680 Td (IBAN: DE89 3704 0044 0532 0130 00) Tj ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000206 00000 n
trailer << /Size 5 /Root 1 0 R >>
startxref
350
%%EOF`;
}

// Upload and start OCR
function uploadAndProcessDocument(token, backend = 'auto') {
    const fd = new FormData();
    const content = generateTestDocument();
    const filename = `ocr_test_${randomString(8)}.pdf`;

    fd.append('file', http.file(content, filename, 'application/pdf'));
    fd.append('language', 'de');
    fd.append('backend', backend);

    const uploadResponse = http.post(
        `${BASE_URL}${API_PREFIX}/documents/`,
        fd.body(),
        {
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': `multipart/form-data; boundary=${fd.boundary}`
            },
            tags: { endpoint: 'upload' }
        }
    );

    if (uploadResponse.status !== 200 && uploadResponse.status !== 201) {
        return { error: 'upload_failed', status: uploadResponse.status };
    }

    let documentId;
    try {
        const body = JSON.parse(uploadResponse.body);
        documentId = body.id || body.document_id;
    } catch {
        return { error: 'parse_failed' };
    }

    ocrJobsStarted.add(1);

    // Start OCR processing
    const ocrResponse = http.post(
        `${BASE_URL}${API_PREFIX}/ocr/process`,
        JSON.stringify({
            document_id: documentId,
            backend: backend,
            language: 'de'
        }),
        {
            headers: getHeaders(token),
            tags: { endpoint: 'ocr' }
        }
    );

    return {
        uploadResponse,
        ocrResponse,
        documentId,
        backend
    };
}

// Poll for OCR completion
function waitForOcrCompletion(token, documentId, maxWaitMs = 30000) {
    const startTime = Date.now();
    const pollInterval = 1000; // 1 second

    while (Date.now() - startTime < maxWaitMs) {
        const response = http.get(
            `${BASE_URL}${API_PREFIX}/documents/${documentId}`,
            {
                headers: getHeaders(token),
                tags: { endpoint: 'document_status' }
            }
        );

        if (response.status === 200) {
            try {
                const body = JSON.parse(response.body);
                const status = body.status || body.ocr_status;

                if (status === 'completed' || status === 'success') {
                    return {
                        success: true,
                        duration: Date.now() - startTime,
                        result: body
                    };
                }

                if (status === 'failed' || status === 'error') {
                    return {
                        success: false,
                        duration: Date.now() - startTime,
                        error: 'ocr_failed'
                    };
                }
            } catch {
                // Continue polling
            }
        }

        sleep(pollInterval / 1000);
    }

    return {
        success: false,
        duration: maxWaitMs,
        error: 'timeout'
    };
}

// Main OCR processing test
export function ocrProcessingTest() {
    if (!accessToken) {
        accessToken = login();
        if (!accessToken) {
            console.error('Failed to login');
            ocrErrors.add(1);
            return;
        }
    }

    group('OCR Processing - Auto Backend', function() {
        const result = uploadAndProcessDocument(accessToken, 'auto');

        if (result.error) {
            ocrErrors.add(1);
            console.error(`Upload failed: ${result.error}`);
            return;
        }

        const ocrSuccess = check(result.ocrResponse, {
            'OCR start status is 200 or 202': (r) => r.status === 200 || r.status === 202,
            'OCR response has task_id or document_id': (r) => {
                try {
                    const body = JSON.parse(r.body);
                    return body.task_id || body.document_id || body.id;
                } catch {
                    return false;
                }
            }
        });

        if (!ocrSuccess) {
            ocrErrors.add(1);
            return;
        }

        // Wait for completion and measure time
        const completion = waitForOcrCompletion(accessToken, result.documentId, 30000);

        ocrDuration.add(completion.duration);

        if (completion.success) {
            ocrJobsCompleted.add(1);
            ocrErrors.add(0);

            check(completion, {
                'OCR completed within 10s': (c) => c.duration < 10000,
                'OCR has extracted text': (c) => {
                    return c.result && (c.result.extracted_text || c.result.text);
                }
            });
        } else {
            ocrErrors.add(1);
            console.error(`OCR failed: ${completion.error}`);
        }

        sleep(2);
    });
}

// GPU-specific test
export function ocrGpuTest() {
    if (!accessToken) {
        accessToken = login();
        if (!accessToken) {
            return;
        }
    }

    group('OCR Processing - GPU (DeepSeek)', function() {
        const result = uploadAndProcessDocument(accessToken, 'deepseek');

        if (result.error) {
            ocrErrors.add(1);
            return;
        }

        const completion = waitForOcrCompletion(accessToken, result.documentId, 15000);

        if (completion.success) {
            ocrGpuDuration.add(completion.duration);
            ocrJobsCompleted.add(1);

            check(completion, {
                'GPU OCR completed within 2s': (c) => c.duration < 2000
            });
        }

        sleep(3);
    });
}

// CPU-specific test
export function ocrCpuTest() {
    if (!accessToken) {
        accessToken = login();
        if (!accessToken) {
            return;
        }
    }

    group('OCR Processing - CPU (Surya)', function() {
        const result = uploadAndProcessDocument(accessToken, 'surya');

        if (result.error) {
            ocrErrors.add(1);
            return;
        }

        const completion = waitForOcrCompletion(accessToken, result.documentId, 30000);

        if (completion.success) {
            ocrCpuDuration.add(completion.duration);
            ocrJobsCompleted.add(1);

            check(completion, {
                'CPU OCR completed within 10s': (c) => c.duration < 10000
            });
        }

        sleep(3);
    });
}

// GPU status check
export function checkGpuStatus() {
    const response = http.get(
        `${BASE_URL}/gpu/status`,
        {
            headers: getHeaders(),
            tags: { endpoint: 'gpu_status' }
        }
    );

    check(response, {
        'GPU status is 200': (r) => r.status === 200,
        'GPU is available': (r) => {
            try {
                const body = JSON.parse(r.body);
                return body.available === true || body.gpu_available === true;
            } catch {
                return false;
            }
        }
    });

    return response;
}

// Default function
export default function() {
    ocrProcessingTest();
}

// Setup
export function setup() {
    console.log(`Starting OCR processing load test against ${BASE_URL}`);

    // Check GPU status
    const gpuStatus = http.get(`${BASE_URL}/gpu/status`);
    let gpuAvailable = false;

    try {
        const body = JSON.parse(gpuStatus.body);
        gpuAvailable = body.available || body.gpu_available || false;
    } catch {
        // Ignore
    }

    console.log(`GPU Available: ${gpuAvailable}`);

    const token = login();

    return {
        startTime: new Date().toISOString(),
        hasAuth: token !== null,
        gpuAvailable: gpuAvailable
    };
}

// Teardown
export function teardown(data) {
    console.log(`OCR processing load test completed.`);
    console.log(`Started at: ${data.startTime}`);
    console.log(`GPU was available: ${data.gpuAvailable}`);
}
