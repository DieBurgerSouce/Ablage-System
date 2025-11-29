/**
 * K6 Load Test: Document Upload
 *
 * Target: < 500ms (p95)
 * Purpose: Test document upload performance under load
 */

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';
import { FormData } from 'https://jslib.k6.io/formdata/0.0.2/index.js';
import { BASE_URL, API_PREFIX, TEST_USER, SCENARIOS, getHeaders, randomString, randomDocumentType } from '../config.js';

// Custom metrics
const uploadDuration = new Trend('document_upload_duration', true);
const uploadErrors = new Rate('document_upload_errors');
const documentsUploaded = new Counter('documents_uploaded');

// Auth token
let accessToken = null;

// Test options
export const options = {
    scenarios: {
        upload_load: {
            ...SCENARIOS.load,
            exec: 'documentUploadFlow'
        }
    },
    thresholds: {
        'document_upload_duration': ['p(95)<500', 'p(99)<1000'],
        'document_upload_errors': ['rate<0.05'],
        'http_req_failed': ['rate<0.05']
    },
    tags: {
        test_name: 'document_upload',
        endpoint: 'upload'
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

// Generate a simple test PDF content
function generateTestPDF() {
    // Minimal PDF structure
    const pdfContent = `%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >> endobj
4 0 obj << /Length 44 >>
stream
BT /F1 12 Tf 100 700 Td (Test ${randomString(8)}) Tj ET
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
300
%%EOF`;
    return pdfContent;
}

// Generate test image (1x1 white PNG)
function generateTestImage() {
    // Minimal valid PNG (1x1 white pixel)
    const pngBase64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==';
    return pngBase64;
}

// Upload document
function uploadDocument(token, filename, content, contentType) {
    const fd = new FormData();
    fd.append('file', http.file(content, filename, contentType));
    fd.append('language', 'de');
    fd.append('document_type', randomDocumentType());

    const response = http.post(
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

    uploadDuration.add(response.timings.duration);

    return response;
}

// Main upload flow
export function documentUploadFlow() {
    // Ensure we have a token
    if (!accessToken) {
        accessToken = login();
        if (!accessToken) {
            console.error('Failed to login');
            uploadErrors.add(1);
            return;
        }
    }

    group('Document Upload', function() {
        // Generate test document
        const filename = `test_document_${randomString(8)}.pdf`;
        const content = generateTestPDF();

        // Upload
        const response = uploadDocument(accessToken, filename, content, 'application/pdf');

        const success = check(response, {
            'upload status is 201 or 200': (r) => r.status === 201 || r.status === 200,
            'upload response time < 500ms': (r) => r.timings.duration < 500,
            'upload returns document_id': (r) => {
                try {
                    const body = JSON.parse(r.body);
                    return body.id !== undefined || body.document_id !== undefined;
                } catch {
                    return false;
                }
            }
        });

        if (response.status === 401) {
            // Token expired, refresh
            accessToken = login();
            uploadErrors.add(1);
            return;
        }

        if (response.status === 429) {
            console.log('Rate limit hit during upload');
            sleep(5);
            return;
        }

        if (success) {
            documentsUploaded.add(1);
            uploadErrors.add(0);
        } else {
            uploadErrors.add(1);
            console.error(`Upload failed: ${response.status} - ${response.body}`);
        }

        sleep(1);
    });
}

// Batch upload test
export function batchUploadFlow() {
    if (!accessToken) {
        accessToken = login();
        if (!accessToken) {
            console.error('Failed to login');
            return;
        }
    }

    group('Batch Upload', function() {
        const documents = [];

        // Prepare batch
        for (let i = 0; i < 5; i++) {
            documents.push({
                filename: `batch_doc_${randomString(8)}.pdf`,
                content: generateTestPDF()
            });
        }

        // Upload sequentially (batch endpoint if available, else sequential)
        let successCount = 0;
        for (const doc of documents) {
            const response = uploadDocument(
                accessToken,
                doc.filename,
                doc.content,
                'application/pdf'
            );

            if (response.status === 201 || response.status === 200) {
                successCount++;
            }

            sleep(0.5);
        }

        check(null, {
            'batch upload success rate >= 80%': () => successCount / documents.length >= 0.8
        });

        documentsUploaded.add(successCount);
    });
}

// Default function
export default function() {
    documentUploadFlow();
}

// Setup
export function setup() {
    console.log(`Starting document upload load test against ${BASE_URL}`);

    // Try to login
    const token = login();
    if (!token) {
        console.warn('Could not login for setup. Test user may need to be created.');
    } else {
        console.log('Successfully authenticated for load test');
    }

    return {
        startTime: new Date().toISOString(),
        hasAuth: token !== null
    };
}

// Teardown
export function teardown(data) {
    console.log(`Document upload load test completed.`);
    console.log(`Started at: ${data.startTime}`);
    console.log(`Auth available: ${data.hasAuth}`);
}
