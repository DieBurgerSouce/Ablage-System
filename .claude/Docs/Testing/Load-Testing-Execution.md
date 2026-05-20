# Load-Testing Ausführungshandbuch

> **Ablage-System - Performance & Lasttests**
> Version: 1.0 | Stand: Januar 2025

---

## Übersicht

Dieses Dokument beschreibt die Load-Testing-Strategie des Ablage-Systems. Ziel ist die Validierung von Performance, Skalierbarkeit und Stabilität unter realistischer und extremer Last.

**Tools:** k6, Locust, Grafana k6 Cloud
**Ziel-Hardware:** RTX 4080 (16GB VRAM)
**Baseline:** 100 gleichzeitige Benutzer, 500 Dokumente/Stunde

---

## Inhaltsverzeichnis

1. [Test-Strategie](#test-strategie)
2. [Test-Szenarien](#test-szenarien)
3. [k6-Testskripte](#k6-testskripte)
4. [Locust-Testskripte](#locust-testskripte)
5. [Durchführung](#durchführung)
6. [Metriken & Thresholds](#metriken--thresholds)
7. [GPU-spezifische Tests](#gpu-spezifische-tests)
8. [Reporting](#reporting)
9. [CI/CD-Integration](#cicd-integration)

---

## Test-Strategie

### Test-Typen

| Test-Typ | Zweck | Dauer | Last |
|----------|-------|-------|------|
| **Smoke Test** | Basis-Funktionalität prüfen | 1 Min | 1-5 VUs |
| **Load Test** | Normale Last validieren | 10-30 Min | 50-100 VUs |
| **Stress Test** | Grenzen finden | 30-60 Min | 100-500 VUs |
| **Spike Test** | Plötzliche Last-Spitzen | 15 Min | 0→200→0 VUs |
| **Soak Test** | Langzeit-Stabilität | 4-24 Std | 50 VUs konstant |
| **OCR Capacity Test** | GPU-Kapazität | 30 Min | Dokumenten-Fokus |

### Last-Profil

```
Benutzer
  ▲
500│            ╭───╮       Stress
   │           ╱     ╲
200│       ╭──╯       ╲     Spike
   │      ╱             ╲
100│  ╭──╯               ╰──╮ Load
   │ ╱                       ╲
 50│╱                         ╰── Soak
   └────────────────────────────▶ Zeit
   0   5   15  30  45  60  Min
```

---

## Test-Szenarien

### Szenario 1: Normale Büroanwendung

**Beschreibung:** Typischer Arbeitstag mit Dokumenten-Upload und Suche

```javascript
// Benutzerverhalten
{
  "actions": [
    { "type": "login", "weight": 0.05 },
    { "type": "browse_documents", "weight": 0.30 },
    { "type": "search", "weight": 0.25 },
    { "type": "upload_document", "weight": 0.15 },
    { "type": "view_document", "weight": 0.20 },
    { "type": "download_document", "weight": 0.05 }
  ],
  "think_time": "3-10s",
  "session_duration": "5-30min"
}
```

### Szenario 2: Batch-Import

**Beschreibung:** Massiver Dokumenten-Import (z.B. Migration)

```javascript
{
  "actions": [
    { "type": "batch_upload", "count": 100, "parallel": 10 }
  ],
  "total_documents": 10000,
  "target_rate": "200 docs/min"
}
```

### Szenario 3: Intensive Suche

**Beschreibung:** Viele gleichzeitige Suchanfragen

```javascript
{
  "actions": [
    { "type": "full_text_search", "weight": 0.40 },
    { "type": "semantic_search", "weight": 0.30 },
    { "type": "filtered_search", "weight": 0.30 }
  ],
  "queries_per_second": 50
}
```

---

## k6-Testskripte

### Basis-Setup

```javascript
// tests/load/k6/config.js
export const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
export const API_URL = `${BASE_URL}/api/v1`;

export const defaultHeaders = {
  'Content-Type': 'application/json',
};

export function getAuthHeaders(token) {
  return {
    ...defaultHeaders,
    'Authorization': `Bearer ${token}`,
  };
}
```

### Smoke Test

```javascript
// tests/load/k6/smoke-test.js
import http from 'k6/http';
import { check, sleep } from 'k6';
import { API_URL, getAuthHeaders } from './config.js';

export const options = {
  vus: 1,
  duration: '1m',
  thresholds: {
    http_req_duration: ['p(95)<500'],
    http_req_failed: ['rate<0.01'],
  },
};

export function setup() {
  // Login und Token holen
  const loginRes = http.post(`${API_URL}/auth/login`, JSON.stringify({
    email: __ENV.TEST_USER_EMAIL,
    password: __ENV.TEST_USER_PASSWORD,
  }), { headers: { 'Content-Type': 'application/json' } });

  return { token: loginRes.json('access_token') };
}

export default function(data) {
  const headers = getAuthHeaders(data.token);

  // Health-Check
  const healthRes = http.get(`${API_URL}/health`, { headers });
  check(healthRes, {
    'health check passed': (r) => r.status === 200,
    'all services healthy': (r) => r.json('status') === 'healthy',
  });

  // Dokumente auflisten
  const docsRes = http.get(`${API_URL}/documents`, { headers });
  check(docsRes, {
    'documents listed': (r) => r.status === 200,
    'documents array exists': (r) => Array.isArray(r.json('items')),
  });

  sleep(1);
}
```

### Load Test

```javascript
// tests/load/k6/load-test.js
import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend } from 'k6/metrics';
import { API_URL, getAuthHeaders } from './config.js';

// Custom Metrics
const documentUploadDuration = new Trend('document_upload_duration');
const ocrProcessingDuration = new Trend('ocr_processing_duration');
const searchDuration = new Trend('search_duration');
const errorRate = new Rate('errors');

export const options = {
  stages: [
    { duration: '2m', target: 20 },   // Ramp-up
    { duration: '5m', target: 50 },   // Hold at 50
    { duration: '5m', target: 100 },  // Increase to 100
    { duration: '10m', target: 100 }, // Hold at 100
    { duration: '3m', target: 0 },    // Ramp-down
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000', 'p(99)<5000'],
    http_req_failed: ['rate<0.05'],
    errors: ['rate<0.05'],
    document_upload_duration: ['p(95)<5000'],
    search_duration: ['p(95)<500'],
  },
};

const testFile = open('./fixtures/test-invoice.pdf', 'b');

export function setup() {
  const loginRes = http.post(`${API_URL}/auth/login`, JSON.stringify({
    email: __ENV.TEST_USER_EMAIL,
    password: __ENV.TEST_USER_PASSWORD,
  }), { headers: { 'Content-Type': 'application/json' } });

  return { token: loginRes.json('access_token') };
}

export default function(data) {
  const headers = getAuthHeaders(data.token);

  // Gewichtete Aktionen simulieren
  const rand = Math.random();

  if (rand < 0.30) {
    // 30%: Dokumente durchsuchen
    group('browse_documents', () => {
      const res = http.get(`${API_URL}/documents?page=1&limit=20`, { headers });
      check(res, { 'documents fetched': (r) => r.status === 200 });
      errorRate.add(res.status !== 200);
    });
  } else if (rand < 0.55) {
    // 25%: Suche
    group('search', () => {
      const start = Date.now();
      const res = http.get(`${API_URL}/documents/search?q=rechnung`, { headers });
      searchDuration.add(Date.now() - start);
      check(res, { 'search successful': (r) => r.status === 200 });
      errorRate.add(res.status !== 200);
    });
  } else if (rand < 0.70) {
    // 15%: Dokument hochladen
    group('upload_document', () => {
      const start = Date.now();
      const res = http.post(`${API_URL}/documents`, {
        file: http.file(testFile, 'test-invoice.pdf', 'application/pdf'),
      }, { headers: { ...headers, 'Content-Type': undefined } });
      documentUploadDuration.add(Date.now() - start);
      check(res, { 'upload successful': (r) => r.status === 201 });
      errorRate.add(res.status !== 201);
    });
  } else if (rand < 0.90) {
    // 20%: Dokument anzeigen
    group('view_document', () => {
      // Zuerst Liste holen, dann erstes Dokument laden
      const listRes = http.get(`${API_URL}/documents?limit=1`, { headers });
      if (listRes.status === 200 && listRes.json('items').length > 0) {
        const docId = listRes.json('items')[0].id;
        const docRes = http.get(`${API_URL}/documents/${docId}`, { headers });
        check(docRes, { 'document fetched': (r) => r.status === 200 });
        errorRate.add(docRes.status !== 200);
      }
    });
  } else {
    // 10%: Dokument herunterladen
    group('download_document', () => {
      const listRes = http.get(`${API_URL}/documents?limit=1`, { headers });
      if (listRes.status === 200 && listRes.json('items').length > 0) {
        const docId = listRes.json('items')[0].id;
        const downloadRes = http.get(`${API_URL}/documents/${docId}/download`, { headers });
        check(downloadRes, { 'download successful': (r) => r.status === 200 });
      }
    });
  }

  // Think-Time: 3-10 Sekunden
  sleep(3 + Math.random() * 7);
}

export function teardown(data) {
  // Optional: Test-Daten aufräumen
  console.log('Load test completed');
}
```

### Stress Test

```javascript
// tests/load/k6/stress-test.js
import http from 'k6/http';
import { check, sleep } from 'k6';
import { API_URL, getAuthHeaders } from './config.js';

export const options = {
  stages: [
    { duration: '2m', target: 100 },
    { duration: '5m', target: 100 },
    { duration: '2m', target: 200 },
    { duration: '5m', target: 200 },
    { duration: '2m', target: 300 },
    { duration: '5m', target: 300 },
    { duration: '2m', target: 500 },
    { duration: '5m', target: 500 },
    { duration: '5m', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<5000'],
    http_req_failed: ['rate<0.10'],
  },
};

// ... ähnlicher Code wie Load-Test
```

### Spike Test

```javascript
// tests/load/k6/spike-test.js
import http from 'k6/http';
import { check, sleep } from 'k6';
import { API_URL, getAuthHeaders } from './config.js';

export const options = {
  stages: [
    { duration: '1m', target: 10 },   // Normallast
    { duration: '10s', target: 200 }, // Spike!
    { duration: '2m', target: 200 },  // Hold
    { duration: '10s', target: 10 },  // Recovery
    { duration: '3m', target: 10 },   // Stabilisierung
    { duration: '1m', target: 0 },    // Ramp-down
  ],
  thresholds: {
    http_req_duration: ['p(95)<10000'], // Höhere Toleranz bei Spike
    http_req_failed: ['rate<0.15'],
  },
};

// ... Test-Implementierung
```

### OCR Capacity Test

```javascript
// tests/load/k6/ocr-capacity-test.js
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Counter } from 'k6/metrics';
import { API_URL, getAuthHeaders } from './config.js';

const ocrDuration = new Trend('ocr_processing_time');
const documentsProcessed = new Counter('documents_processed');
const gpuUtilization = new Trend('gpu_utilization');

export const options = {
  scenarios: {
    constant_upload: {
      executor: 'constant-arrival-rate',
      rate: 10,                    // 10 Dokumente pro Sekunde
      timeUnit: '1s',
      duration: '30m',
      preAllocatedVUs: 50,
      maxVUs: 100,
    },
  },
  thresholds: {
    ocrProcessingTime: ['p(95)<30000'], // 30s für OCR
    http_req_failed: ['rate<0.05'],
    documents_processed: ['count>1000'], // Mindestens 1000 Dokumente
  },
};

const testFiles = [
  open('./fixtures/invoice-1page.pdf', 'b'),
  open('./fixtures/invoice-3pages.pdf', 'b'),
  open('./fixtures/contract-10pages.pdf', 'b'),
];

export function setup() {
  const loginRes = http.post(`${API_URL}/auth/login`, JSON.stringify({
    email: __ENV.TEST_USER_EMAIL,
    password: __ENV.TEST_USER_PASSWORD,
  }), { headers: { 'Content-Type': 'application/json' } });

  return { token: loginRes.json('access_token') };
}

export default function(data) {
  const headers = getAuthHeaders(data.token);

  // Zufälliges Test-Dokument wählen
  const testFile = testFiles[Math.floor(Math.random() * testFiles.length)];

  // Dokument hochladen
  const uploadStart = Date.now();
  const uploadRes = http.post(`${API_URL}/documents`, {
    file: http.file(testFile, 'test.pdf', 'application/pdf'),
  }, { headers: { ...headers, 'Content-Type': undefined } });

  if (uploadRes.status !== 201) {
    console.error(`Upload failed: ${uploadRes.status}`);
    return;
  }

  const docId = uploadRes.json('id');

  // Auf OCR-Verarbeitung warten (Polling)
  let processed = false;
  let attempts = 0;
  const maxAttempts = 60; // 60 * 1s = 60s Timeout

  while (!processed && attempts < maxAttempts) {
    sleep(1);
    attempts++;

    const statusRes = http.get(`${API_URL}/documents/${docId}`, { headers });
    if (statusRes.status === 200) {
      const status = statusRes.json('status');
      if (status === 'completed') {
        processed = true;
        ocrDuration.add(Date.now() - uploadStart);
        documentsProcessed.add(1);
      } else if (status === 'failed') {
        console.error(`OCR failed for ${docId}`);
        break;
      }
    }
  }

  // GPU-Metriken abrufen (wenn verfügbar)
  const metricsRes = http.get(`${API_URL}/metrics/gpu`, { headers });
  if (metricsRes.status === 200) {
    gpuUtilization.add(metricsRes.json('utilization_percent'));
  }

  check({ processed }, {
    'document processed successfully': (p) => p.processed === true,
  });
}
```

---

## Locust-Testskripte

### Python-basierte Lasttests

```python
# tests/load/locust/locustfile.py
from locust import HttpUser, task, between, events
from locust.env import Environment
import os
import random

class AblageUser(HttpUser):
    wait_time = between(3, 10)
    host = os.getenv("BASE_URL", "http://localhost:8000")

    def on_start(self):
        """Login beim Start"""
        response = self.client.post("/api/v1/auth/login", json={
            "email": os.getenv("TEST_USER_EMAIL"),
            "password": os.getenv("TEST_USER_PASSWORD"),
        })
        if response.status_code == 200:
            self.token = response.json()["access_token"]
            self.client.headers.update({
                "Authorization": f"Bearer {self.token}"
            })
        else:
            raise Exception("Login failed")

    @task(30)
    def browse_documents(self):
        """Dokumente durchsuchen"""
        with self.client.get(
            "/api/v1/documents",
            params={"page": 1, "limit": 20},
            name="/api/v1/documents [GET]"
        ) as response:
            if response.status_code != 200:
                response.failure(f"Got {response.status_code}")

    @task(25)
    def search_documents(self):
        """Dokumente suchen"""
        queries = ["rechnung", "vertrag", "2024", "lieferung"]
        query = random.choice(queries)
        with self.client.get(
            f"/api/v1/documents/search",
            params={"q": query},
            name="/api/v1/documents/search [GET]"
        ) as response:
            if response.status_code != 200:
                response.failure(f"Search failed: {response.status_code}")

    @task(15)
    def upload_document(self):
        """Dokument hochladen"""
        with open("fixtures/test-invoice.pdf", "rb") as f:
            files = {"file": ("test.pdf", f, "application/pdf")}
            with self.client.post(
                "/api/v1/documents",
                files=files,
                name="/api/v1/documents [POST]"
            ) as response:
                if response.status_code != 201:
                    response.failure(f"Upload failed: {response.status_code}")

    @task(20)
    def view_document(self):
        """Dokument anzeigen"""
        # Erst Liste holen
        list_response = self.client.get(
            "/api/v1/documents",
            params={"limit": 10}
        )
        if list_response.status_code == 200:
            items = list_response.json().get("items", [])
            if items:
                doc_id = random.choice(items)["id"]
                with self.client.get(
                    f"/api/v1/documents/{doc_id}",
                    name="/api/v1/documents/{id} [GET]"
                ) as response:
                    if response.status_code != 200:
                        response.failure(f"View failed: {response.status_code}")

    @task(10)
    def download_document(self):
        """Dokument herunterladen"""
        list_response = self.client.get(
            "/api/v1/documents",
            params={"limit": 1}
        )
        if list_response.status_code == 200:
            items = list_response.json().get("items", [])
            if items:
                doc_id = items[0]["id"]
                with self.client.get(
                    f"/api/v1/documents/{doc_id}/download",
                    name="/api/v1/documents/{id}/download [GET]"
                ) as response:
                    if response.status_code != 200:
                        response.failure(f"Download failed: {response.status_code}")


class AdminUser(HttpUser):
    """Admin-Benutzer mit speziellen Aktionen"""
    weight = 1  # Weniger Admin-Benutzer
    wait_time = between(5, 15)

    def on_start(self):
        response = self.client.post("/api/v1/auth/login", json={
            "email": os.getenv("ADMIN_EMAIL"),
            "password": os.getenv("ADMIN_PASSWORD"),
        })
        if response.status_code == 200:
            self.token = response.json()["access_token"]
            self.client.headers.update({
                "Authorization": f"Bearer {self.token}"
            })

    @task(50)
    def view_dashboard(self):
        self.client.get("/api/v1/admin/dashboard", name="/admin/dashboard [GET]")

    @task(30)
    def view_users(self):
        self.client.get("/api/v1/admin/users", name="/admin/users [GET]")

    @task(20)
    def view_system_stats(self):
        self.client.get("/api/v1/admin/stats", name="/admin/stats [GET]")
```

### Locust ausführen

```bash
# Interaktive Web-UI
locust -f tests/load/locust/locustfile.py

# Headless mit bestimmter Last
locust -f tests/load/locust/locustfile.py \
  --headless \
  --users 100 \
  --spawn-rate 10 \
  --run-time 30m \
  --html report.html
```

---

## Durchführung

### Pre-Test-Checkliste

```markdown
□ 1. Umgebung vorbereiten
  □ Produktionsnahe Test-Umgebung verfügbar
  □ Datenbank mit realistischen Daten gefüllt
  □ GPU verfügbar und korrekt konfiguriert
  □ Monitoring aktiv (Grafana, Prometheus)

□ 2. Baseline erfassen
  □ Aktuelle Performance-Metriken notieren
  □ GPU-Auslastung im Leerlauf prüfen
  □ Speicherverbrauch dokumentieren

□ 3. Test-Daten vorbereiten
  □ Test-Dokumente verfügbar
  □ Test-Benutzer angelegt
  □ API-Keys generiert

□ 4. Monitoring starten
  □ Grafana-Dashboard öffnen
  □ Log-Aggregation aktiv
  □ Alerting konfiguriert
```

### Ausführungsreihenfolge

```bash
# 1. Smoke Test (Basis-Validierung)
k6 run tests/load/k6/smoke-test.js

# 2. Load Test (normale Last)
k6 run tests/load/k6/load-test.js

# 3. Stress Test (Grenzen finden)
k6 run tests/load/k6/stress-test.js

# 4. OCR Capacity Test (GPU-spezifisch)
k6 run tests/load/k6/ocr-capacity-test.js

# 5. Soak Test (Langzeit, optional)
k6 run --duration 4h tests/load/k6/soak-test.js
```

### Während des Tests überwachen

```bash
# Terminal 1: k6-Ausgabe
k6 run --out json=results.json tests/load/k6/load-test.js

# Terminal 2: GPU-Monitoring
watch -n 1 nvidia-smi

# Terminal 3: Docker-Stats
docker stats

# Terminal 4: API-Logs
docker-compose logs -f backend worker
```

---

## Metriken & Thresholds

### Performance-Ziele (SLOs)

| Metrik | Ziel | Kritisch |
|--------|------|----------|
| API Response Time (P95) | < 500ms | < 2000ms |
| API Response Time (P99) | < 2000ms | < 5000ms |
| OCR Processing (P95) | < 10s | < 30s |
| Error Rate | < 1% | < 5% |
| GPU Utilization | < 85% | < 95% |
| Memory Usage | < 80% | < 95% |

### k6 Thresholds

```javascript
export const options = {
  thresholds: {
    // HTTP-Metriken
    http_req_duration: [
      'p(95)<500',   // 95% unter 500ms
      'p(99)<2000',  // 99% unter 2s
      'avg<200',     // Durchschnitt unter 200ms
    ],
    http_req_failed: ['rate<0.01'], // Weniger als 1% Fehler

    // Custom Metriken
    'ocr_processing_time': ['p(95)<10000'],
    'search_duration': ['p(95)<300'],
    'document_upload_duration': ['p(95)<3000'],

    // Gruppen-spezifisch
    'group_duration{group:::browse_documents}': ['p(95)<500'],
    'group_duration{group:::search}': ['p(95)<300'],
    'group_duration{group:::upload_document}': ['p(95)<5000'],

    // Checks
    'checks': ['rate>0.95'], // 95% aller Checks bestanden
  },
};
```

---

## GPU-spezifische Tests

### VRAM-Monitoring

```javascript
// tests/load/k6/gpu-stress.js
import http from 'k6/http';
import { Trend, Gauge } from 'k6/metrics';

const vramUsage = new Gauge('gpu_vram_usage_gb');
const gpuTemp = new Gauge('gpu_temperature_celsius');
const gpuUtil = new Gauge('gpu_utilization_percent');

export const options = {
  scenarios: {
    gpu_stress: {
      executor: 'ramping-arrival-rate',
      startRate: 1,
      timeUnit: '1s',
      stages: [
        { target: 5, duration: '2m' },
        { target: 10, duration: '5m' },
        { target: 20, duration: '5m' },
        { target: 10, duration: '2m' },
      ],
      preAllocatedVUs: 50,
    },
  },
  thresholds: {
    'gpu_vram_usage_gb': ['value<13.6'], // 85% von 16GB
    'gpu_temperature_celsius': ['value<85'],
    'gpu_utilization_percent': ['value<95'],
  },
};

export default function(data) {
  // Großes Dokument verarbeiten
  const testFile = open('./fixtures/large-document-50pages.pdf', 'b');

  const uploadRes = http.post(`${API_URL}/documents`, {
    file: http.file(testFile, 'large.pdf', 'application/pdf'),
    ocr_backend: 'deepseek',
  }, { headers });

  // GPU-Metriken abrufen
  const metricsRes = http.get(`${API_URL}/metrics/gpu`);
  if (metricsRes.status === 200) {
    const metrics = metricsRes.json();
    vramUsage.add(metrics.memory_used_gb);
    gpuTemp.add(metrics.temperature);
    gpuUtil.add(metrics.utilization);
  }
}
```

### GPU OOM-Recovery-Test

```javascript
// tests/load/k6/gpu-oom-test.js
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter } from 'k6/metrics';

const oomEvents = new Counter('gpu_oom_events');
const fallbackEvents = new Counter('cpu_fallback_events');

export const options = {
  scenarios: {
    oom_trigger: {
      executor: 'constant-arrival-rate',
      rate: 50,  // Sehr hohe Rate
      timeUnit: '1s',
      duration: '10m',
      preAllocatedVUs: 100,
    },
  },
};

export default function(data) {
  // Große Dokumente hochladen um OOM zu provozieren
  const largeFile = open('./fixtures/document-100pages.pdf', 'b');

  const res = http.post(`${API_URL}/documents`, {
    file: http.file(largeFile, 'large.pdf', 'application/pdf'),
  }, { headers });

  // Auf OOM-Fallback prüfen
  if (res.status === 200 || res.status === 201) {
    const result = res.json();
    if (result.processing_backend === 'surya_cpu') {
      fallbackEvents.add(1);
    }
  } else if (res.status === 503) {
    oomEvents.add(1);
  }
}
```

---

## Reporting

### k6-Report generieren

```bash
# JSON-Output
k6 run --out json=results.json load-test.js

# InfluxDB (für Grafana)
k6 run --out influxdb=http://localhost:8086/k6 load-test.js

# HTML-Report
k6 run load-test.js --out json=results.json
# Dann mit k6-reporter konvertieren
```

### Grafana-Dashboard

```json
{
  "title": "Load Test Results",
  "panels": [
    {
      "title": "Requests per Second",
      "targets": [
        {
          "expr": "rate(http_reqs[1m])"
        }
      ]
    },
    {
      "title": "Response Time (P95)",
      "targets": [
        {
          "expr": "histogram_quantile(0.95, rate(http_req_duration_bucket[1m]))"
        }
      ]
    },
    {
      "title": "Error Rate",
      "targets": [
        {
          "expr": "rate(http_req_failed[1m])"
        }
      ]
    },
    {
      "title": "GPU Utilization",
      "targets": [
        {
          "expr": "gpu_utilization_percent"
        }
      ]
    }
  ]
}
```

---

## CI/CD-Integration

### GitHub Actions

```yaml
# .github/workflows/load-tests.yml
name: Load Tests

on:
  schedule:
    - cron: '0 2 * * 0'  # Sonntag 2:00 Uhr
  workflow_dispatch:
    inputs:
      test_type:
        description: 'Test type'
        required: true
        default: 'load'
        type: choice
        options:
          - smoke
          - load
          - stress

jobs:
  load-test:
    runs-on: self-hosted  # Eigener Runner mit GPU
    timeout-minutes: 120

    steps:
      - uses: actions/checkout@v4

      - name: Setup k6
        run: |
          sudo apt-get update
          sudo apt-get install -y gnupg software-properties-common
          sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg \
            --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
          echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | \
            sudo tee /etc/apt/sources.list.d/k6.list
          sudo apt-get update
          sudo apt-get install -y k6

      - name: Run Load Test
        run: |
          k6 run tests/load/k6/${{ inputs.test_type }}-test.js \
            --out json=results.json
        env:
          BASE_URL: ${{ secrets.STAGING_URL }}
          TEST_USER_EMAIL: ${{ secrets.TEST_USER_EMAIL }}
          TEST_USER_PASSWORD: ${{ secrets.TEST_USER_PASSWORD }}

      - name: Upload Results
        uses: actions/upload-artifact@v4
        with:
          name: load-test-results
          path: results.json

      - name: Check Thresholds
        run: |
          # Prüfen ob Thresholds eingehalten wurden
          if grep -q '"thresholds":{".*":false}' results.json; then
            echo "::error::Load test thresholds failed!"
            exit 1
          fi
```

---

*Letzte Aktualisierung: Januar 2025*
