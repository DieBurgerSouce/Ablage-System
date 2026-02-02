# Ablage-System Test Suite

Umfassende Test-Suite fuer das Ablage-System mit E2E, Visual Regression und Load Tests.

## Uebersicht

| Test-Typ | Framework | Verzeichnis | Beschreibung |
|----------|-----------|-------------|--------------|
| E2E | Playwright | `tests/frontend/e2e/` | End-to-End Browser-Tests |
| Visual | Playwright | `tests/visual/` | Screenshot-basierte Regression |
| Load | k6 | `tests/load/k6/` | Performance und Last-Tests |
| Unit | pytest | `tests/unit/` | Python Unit-Tests |
| Integration | pytest | `tests/integration/` | API Integration Tests |
| GPU | pytest | `tests/gpu/` | GPU-spezifische Tests |

---

## E2E Tests (Playwright)

### Voraussetzungen

```bash
# Im Frontend-Verzeichnis
cd frontend
npm install
npx playwright install
```

### Test-Suites

| Datei | Beschreibung |
|-------|--------------|
| `test_document_workflow.spec.ts` | Upload -> OCR -> Klassifikation -> Export |
| `test_invoice_workflow.spec.ts` | Rechnung -> Skonto -> Zahlung -> Mahnung |
| `test_entity_workflow.spec.ts` | Entity -> Document Linking -> Risk Score |
| `test_workflow_builder.spec.ts` | Workflow-Erstellung und BPMN |
| `display-modes.spec.ts` | 4 Display-Modi (Dark/Light/Whitescreen/Blackscreen) |

### Ausfuehrung

```bash
# Alle E2E-Tests
npx playwright test --config=playwright.config.ts

# Einzelne Test-Suite
npx playwright test test_document_workflow.spec.ts

# Mit UI-Modus (Debug)
npx playwright test --ui

# Nur Chromium
npx playwright test --project=chromium

# Mit Trace
npx playwright test --trace on

# Report anzeigen
npx playwright show-report
```

### Umgebungsvariablen

```bash
# Test-Benutzer
export TEST_USER_EMAIL=admin@localhost.com
export TEST_USER_PASSWORD=admin123

# Basis-URL (Standard: http://localhost:80)
export BASE_URL=http://localhost:80
```

---

## Visual Regression Tests

### Konfiguration

Separate Konfiguration: `tests/visual/playwright-visual.config.ts`

### Features

- Screenshot-Vergleich mit Baseline
- Alle 4 Display-Modi
- Multiple Viewports (Desktop, Tablet, Mobile)
- Maskierung dynamischer Inhalte (Timestamps, IDs)

### Ausfuehrung

```bash
# Visual Tests ausfuehren
npx playwright test --config=tests/visual/playwright-visual.config.ts

# Baseline-Screenshots aktualisieren
UPDATE_SNAPSHOTS=true npx playwright test --config=tests/visual/playwright-visual.config.ts

# Nur spezifische Seite
npx playwright test pages.visual.spec.ts --grep "Dashboard"
```

### Screenshot-Verwaltung

```
tests/visual/
├── __snapshots__/          # Baseline Screenshots
│   ├── expected/           # Erwartete Screenshots
│   ├── actual/             # Aktuelle Screenshots
│   └── diff/               # Differenz-Bilder
├── pages.visual.spec.ts    # Test-Definitionen
└── playwright-visual.config.ts
```

### Thresholds

| Einstellung | Wert | Beschreibung |
|-------------|------|--------------|
| `maxDiffPixelRatio` | 0.05 | Max 5% Pixel-Differenz |
| `threshold` | 0.2 | Farbtoleranz (0-1) |

---

## Load Tests (k6)

### Installation

```bash
# k6 installieren (Windows)
winget install k6

# Oder mit Chocolatey
choco install k6

# Oder Download: https://k6.io/docs/getting-started/installation/
```

### Test-Szenarien

| Szenario | Datei | Beschreibung |
|----------|-------|--------------|
| Concurrent Users | `concurrent_users.js` | 100 gleichzeitige Benutzer |
| Document Upload | `document_upload.js` | 1000 Dokumente/Stunde |
| Search Latency | `search_latency.js` | < 200ms P99 Suche |
| OCR Backpressure | `ocr_backpressure.js` | Queue-Handling unter Last |

### Ausfuehrung

```bash
# Einzelnes Szenario
k6 run tests/load/k6/scenarios/concurrent_users.js

# Mit Parametern
k6 run tests/load/k6/scenarios/concurrent_users.js --vus 50 --duration 3m

# Mit Umgebungsvariablen
k6 run -e BASE_URL=http://localhost:8000 tests/load/k6/scenarios/search_latency.js

# JSON Output
k6 run tests/load/k6/scenarios/concurrent_users.js --out json=results.json

# InfluxDB Output (fuer Grafana)
k6 run tests/load/k6/scenarios/concurrent_users.js --out influxdb=http://localhost:8086/k6
```

### Performance-Ziele (aus CLAUDE.md)

| Metrik | Ziel | Szenario |
|--------|------|----------|
| API Health Check | < 50ms (p95) | health_check.js |
| Document Upload | < 500ms (p95) | document_upload.js |
| OCR (GPU) | < 2s (p95) | ocr_processing.js |
| OCR (CPU) | < 10s (p95) | ocr_processing.js |
| Search | < 200ms (p99) | search_latency.js |
| Concurrent Users | 100+ | concurrent_users.js |
| Documents/Hour | 500+ | document_upload.js |

### Konfiguration

```javascript
// tests/load/k6/config.js

// Basis-URL
export const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';

// Test-Benutzer
export const TEST_USER = {
  email: __ENV.TEST_EMAIL || 'loadtest@ablage-system.local',
  password: __ENV.TEST_PASSWORD || 'LoadTest123!@#',
};
```

---

## Test-Daten

### Fixtures (Python)

```python
# tests/fixtures/factories.py
# Test-Daten-Generierung fuer Python-Tests
```

### Test-Dokumente

```
tests/fixtures/
├── sample_invoice.pdf      # Beispiel-Rechnung
├── sample_contract.pdf     # Beispiel-Vertrag
├── sample_document.png     # Beispiel-Bild
└── sample_fraktur.pdf      # Fraktur-Schrift Test
```

---

## CI/CD Integration

### GitHub Actions Beispiel

```yaml
# .github/workflows/tests.yml
name: Tests

on: [push, pull_request]

jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - name: Install dependencies
        run: |
          cd frontend
          npm ci
          npx playwright install --with-deps
      - name: Run E2E tests
        run: npx playwright test --config=playwright.config.ts
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-report
          path: playwright-report/

  visual:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
      - name: Install dependencies
        run: |
          cd frontend
          npm ci
          npx playwright install --with-deps
      - name: Run visual tests
        run: npx playwright test --config=tests/visual/playwright-visual.config.ts
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: visual-diff
          path: tests/visual/__snapshots__/diff/

  load:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: grafana/k6-action@v0.3.1
        with:
          filename: tests/load/k6/scenarios/concurrent_users.js
          flags: --vus 10 --duration 1m
```

---

## Troubleshooting

### E2E Tests

**Problem**: Tests schlagen bei Login fehl
```bash
# Pruefe ob Frontend/Backend laufen
curl http://localhost:80/health
curl http://localhost:8000/api/v1/health

# Pruefe Test-Benutzer existiert
docker-compose exec backend python -c "from app.db.session import get_db; ..."
```

**Problem**: Screenshots stimmen nicht ueberein
```bash
# Baseline aktualisieren
UPDATE_SNAPSHOTS=true npx playwright test --config=tests/visual/playwright-visual.config.ts

# Nur fehlende Screenshots erstellen
npx playwright test --config=tests/visual/playwright-visual.config.ts --update-snapshots missing
```

### Load Tests

**Problem**: Rate Limit Errors
```javascript
// In config.js: Reduziere Rate
export const SCENARIOS = {
  load: {
    executor: 'ramping-vus',
    stages: [
      { duration: '2m', target: 5 },  // Reduziert von 10
    ]
  }
};
```

**Problem**: Authentifizierung schlaegt fehl
```bash
# Erstelle Load-Test-Benutzer
docker-compose exec backend python -c "
from app.db.session import SessionLocal
from app.core.security import get_password_hash
from app.db.models.user import User

db = SessionLocal()
user = User(
    email='loadtest@ablage-system.local',
    hashed_password=get_password_hash('LoadTest123!@#'),
    is_active=True,
)
db.add(user)
db.commit()
"
```

---

## Metriken und Reporting

### Playwright Reports

```bash
# HTML Report generieren
npx playwright test --reporter=html

# JSON Report
npx playwright test --reporter=json --output=report.json

# Mehrere Reporter
npx playwright test --reporter=list,html
```

### k6 Metriken

```bash
# Detaillierte Zusammenfassung
k6 run --summary-trend-stats="avg,min,med,max,p(90),p(95),p(99)" scenario.js

# Grafana Dashboard
# Starte InfluxDB und Grafana, dann:
k6 run --out influxdb=http://localhost:8086/k6 scenario.js
```

---

## Best Practices

1. **Isolierte Test-Daten**: Keine echten Produktionsdaten verwenden
2. **Idempotente Tests**: Tests sollten wiederholbar sein
3. **Deutsche Texte**: Alle user-facing Texte auf Deutsch pruefen
4. **GPU-Tests**: Nur auf Maschinen mit GPU ausfuehren
5. **Visual Tests**: Nach Design-Aenderungen Baselines aktualisieren
6. **Load Tests**: Nicht auf Produktionssystemen ohne Genehmigung

---

## Weitere Dokumentation

- [E2E Testing (Playwright)](/.claude/Docs/Testing/E2E-Testing-Playwright.md)
- [GPU Testing Guide](/.claude/Docs/Testing/GPU-Testing-Guide.md)
- [Testing Requirements](/.claude/Docs/Testing/Requirements.md)
