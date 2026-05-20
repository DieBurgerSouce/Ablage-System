# CI/CD Test Integration Guide

> **Stand**: Januar 2026
> **Status**: Enterprise-Ready
> **Coverage-Ziel**: 90% (Critical Paths: 95%+)

## Inhaltsverzeichnis

1. [Übersicht](#übersicht)
2. [GitHub Actions Workflows](#github-actions-workflows)
3. [Pipeline-Architektur](#pipeline-architektur)
4. [Test-Kategorien und Marker](#test-kategorien-und-marker)
5. [Test-Konfiguration](#test-konfiguration)
6. [Coverage-Management](#coverage-management)
7. [Flaky Test Handling](#flaky-test-handling)
8. [Test Artifact Management](#test-artifact-management)
9. [GPU Test Runner](#gpu-test-runner)
10. [Pre-Commit Hooks](#pre-commit-hooks)
11. [Security Scanning](#security-scanning)
12. [Performance Testing](#performance-testing)
13. [Best Practices](#best-practices)
14. [Troubleshooting](#troubleshooting)

---

## Übersicht

Das Ablage-System nutzt ein Enterprise-Grade CI/CD-System basierend auf **GitHub Actions** mit:

- **8+ spezialisierte Workflows** für unterschiedliche Test-Szenarien
- **Parallele Ausführung** für schnelles Feedback
- **Matrix-Builds** für Multi-Browser E2E-Tests
- **Scheduled Runs** für tägliche Security-Scans
- **Pre-Commit Hooks** für lokale Qualitätskontrolle

### Workflow-Matrix

| Workflow | Trigger | Zweck | Dauer |
|----------|---------|-------|-------|
| `ci.yml` | Push/PR | Haupt-CI (Tests, Linting, Build) | ~10-15 min |
| `coverage.yml` | Push/PR | Coverage-Report + Badge | ~8 min |
| `e2e.yml` | Push/PR (frontend/**) | Playwright E2E-Tests | ~15-30 min |
| `security-scan.yml` | Push/PR/Schedule (03:00 UTC) | Trivy, SBOM, IaC Scan | ~10 min |
| `pr-security.yml` | PR | PR-spezifische Security-Checks | ~5 min |
| `smoke-tests.yml` | Manual/Workflow-Call | Post-Deployment Validierung | ~2 min |
| `performance.yml` | Schedule (So 02:00)/Manual | k6 Load/Stress Tests | ~15-30 min |
| `backup-restore-test.yml` | Schedule | Backup-Integrität | ~10 min |

---

## GitHub Actions Workflows

### Haupt-CI Pipeline (`ci.yml`)

Die zentrale Pipeline mit 8 Jobs in paralleler und sequentieller Ausführung:

```yaml
# Workflow-Struktur
jobs:
  pre-commit     # Job 0: Pre-commit Hooks (MUST pass)
    │
    ▼
  code-quality   # Job 1: Ruff + MyPy
    │
    ├── security    # Job 2: Bandit + Safety (parallel)
    ├── test-unit   # Job 3: Unit Tests (parallel)
    ├── test-integration  # Job 4: Integration Tests (parallel)
    ├── build       # Job 5: Docker Build Verification (parallel)
    └── docs        # Job 6: Documentation Build (parallel)
          │
          ▼
      ci-summary   # Job 8: Aggregierter Status
```

#### Job-Details

**Pre-Commit (Job 0)**
```yaml
pre-commit:
  name: Pre-commit Hooks
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: "3.11"
        cache: pip
    - run: |
        pip install pre-commit
        pre-commit run --all-files --show-diff-on-failure
```

**Unit Tests (Job 3)**
```yaml
test-unit:
  name: Unit Tests
  services:
    postgres:
      image: postgres:16-alpine
      env:
        POSTGRES_USER: postgres
        POSTGRES_PASSWORD: postgres
        POSTGRES_DB: ablage_test
      options: >-
        --health-cmd pg_isready
        --health-interval 10s
        --health-timeout 5s
        --health-retries 5
      ports:
        - 5432:5432
    redis:
      image: redis:7-alpine
      ports:
        - 6379:6379
  steps:
    - run: |
        pytest tests/unit/ -v --tb=short \
          --cov=app --cov-report=xml --cov-report=term
    - uses: codecov/codecov-action@v4
      with:
        files: ./coverage.xml
        flags: unittests
```

### E2E Pipeline (`e2e.yml`)

Multi-Browser Matrix für Frontend-Tests:

```yaml
e2e-tests:
  name: E2E Tests (${{ matrix.browser }})
  timeout-minutes: 30
  strategy:
    fail-fast: false
    matrix:
      browser: [chromium, firefox, webkit]  # Bei workflow_dispatch: all

  steps:
    # Backend starten
    - run: |
        uvicorn app.main:app --host 0.0.0.0 --port 8000 &
        sleep 10
        curl -f http://localhost:8000/health || exit 1

    # Playwright Tests
    - run: npx playwright test --project=${{ matrix.browser }}

    # Screenshots bei Fehlern
    - uses: actions/upload-artifact@v4
      if: failure()
      with:
        name: playwright-screenshots-${{ matrix.browser }}
        path: frontend/test-results/
```

### Security Scan Pipeline (`security-scan.yml`)

Täglicher Security-Scan um 03:00 UTC:

```yaml
# Container Image Scan mit Trivy
container-scan:
  strategy:
    matrix:
      image:
        - name: backend
          dockerfile: ./Dockerfile
        - name: worker
          dockerfile: ./docker/Dockerfile.worker
        - name: frontend
          dockerfile: ./frontend/Dockerfile

  steps:
    - name: Run Trivy Vulnerability Scanner
      uses: aquasecurity/trivy-action@master
      with:
        image-ref: 'scan-target:${{ matrix.image.name }}'
        format: 'sarif'
        severity: 'CRITICAL,HIGH'
        ignore-unfixed: true

    - name: Generate SBOM
      uses: aquasecurity/trivy-action@master
      with:
        format: 'cyclonedx'
        output: 'sbom-${{ matrix.image.name }}.json'
```

---

## Pipeline-Architektur

### Concurrency Control

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

- **Automatisches Abbrechen**: Alte Runs werden bei neuem Push abgebrochen
- **Branch-Isolation**: Jeder Branch hat eigene Concurrency-Group
- **Ressourcen-Effizienz**: Verhindert parallele Runs für denselben Branch

### Path-Filtering

```yaml
on:
  push:
    paths-ignore:
      - '**.md'
      - 'docs/**'
      - '.github/ISSUE_TEMPLATE/**'
  pull_request:
    paths:
      - 'frontend/**'  # Nur für E2E-Tests
```

### Service Container

Alle Test-Jobs nutzen konsistente Service-Container:

| Service | Image | Port | Health Check |
|---------|-------|------|--------------|
| PostgreSQL | `postgres:16-alpine` | 5432 | `pg_isready` |
| Redis | `redis:7-alpine` | 6379 | `redis-cli ping` |
| MinIO | `minio/minio:latest` | 9000 | `curl /minio/health/live` |

---

## Test-Kategorien und Marker

### Pytest Marker

Definiert in `pyproject.toml`:

```ini
[tool.pytest.ini_options]
markers = [
    "unit: Unit tests",
    "integration: Integration tests",
    "e2e: End-to-end tests",
    "gpu: Tests requiring GPU",
    "gpu_required: Tests that require GPU (will skip if not available)",
    "gpu_optional: GPU tests (skip if no GPU available)",
    "slow: Slow running tests",
    "asyncio: Async tests",
    "database: Tests requiring database",
    "redis: Tests requiring Redis",
    "minio: Tests requiring MinIO",
    "metrics: Backend metrics tests",
    "fallback: GPU fallback scenario tests",
    "windows: Windows-specific tests",
    "experimental: Experimental features under evaluation",
    "docker: Docker container health tests",
    "critical: Critical service tests (must pass)",
    "connectivity: Service connectivity tests",
    "prometheus: Prometheus target tests",
    "logs: Container log scanning tests",
]
```

### Marker-Verwendung

```python
# Unit Test
@pytest.mark.unit
def test_password_validation():
    ...

# Integration Test mit Datenbank
@pytest.mark.integration
@pytest.mark.database
async def test_document_crud():
    ...

# GPU-Test mit Skip wenn nicht verfügbar
@pytest.mark.gpu_optional
@pytest.mark.skipif(not torch.cuda.is_available(), reason="GPU not available")
def test_ocr_gpu_processing():
    ...

# Kritischer Test (muss immer bestehen)
@pytest.mark.critical
def test_authentication_flow():
    ...

# Langsamer Test (separat ausführbar)
@pytest.mark.slow
def test_large_batch_processing():
    ...
```

### Test-Ausführung nach Kategorie

```bash
# Nur Unit-Tests
pytest -m unit

# Nur Integration-Tests
pytest -m integration

# GPU-Tests
pytest -m gpu

# Kritische Tests
pytest -m critical

# Schnelle Tests (ohne slow)
pytest -m "not slow"

# Kombination
pytest -m "unit and not slow"
```

---

## Test-Konfiguration

### pytest.ini Options

```ini
[tool.pytest.ini_options]
minversion = "7.0"
pythonpath = ["."]
testpaths = ["tests"]
python_files = ["test_*.py", "*_test.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]

# Standard-Optionen
addopts = [
    "-ra",              # Report all (except passed)
    "--strict-markers", # Unbekannte Marker = Fehler
    "--strict-config",  # Konfig-Fehler = Fehler
    "--maxfail=5",      # Nach 5 Fehlern abbrechen
    "--tb=short",       # Kurze Tracebacks
    "-v",               # Verbose
]

# Async-Modus
asyncio_mode = "auto"
```

### conftest.py Fixtures

**Hauptfixtures** (`tests/conftest.py`):

```python
# Test-Settings Override
@pytest.fixture(scope="session")
def test_settings():
    return Settings(
        TESTING=True,
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        REDIS_URL="redis://localhost:6379/15",
        CELERY_TASK_ALWAYS_EAGER=True,
        RATE_LIMIT_ENABLED=False,
    )

# Async Test-Client
@pytest_asyncio.fixture
async def async_client(test_settings):
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

# Auth-Headers
@pytest_asyncio.fixture
async def auth_headers(test_user):
    access_token = create_access_token(data={"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {access_token}"}

# Mock GPU Manager
@pytest.fixture
def mock_gpu_manager():
    gpu_manager = Mock()
    gpu_manager.get_detailed_status.return_value = {
        "available": True,
        "device_name": "NVIDIA GeForce RTX 4080",
        "memory_used_mb": 1024,
        "memory_total_mb": 16384,
    }
    return gpu_manager

# Sample German Text
@pytest.fixture
def sample_german_text():
    return """
    Sehr geehrte Damen und Herren,
    hiermit übersenden wir Ihnen die Rechnung.
    Rechnungsnummer: RE-2024-001
    Betrag: 1.234,56 €
    """
```

---

## Coverage-Management

### Coverage-Konfiguration

```ini
[tool.coverage.run]
source = ["app"]
omit = [
    "*/tests/*",
    "*/migrations/*",
    "*/__pycache__/*",
]
branch = true
parallel = true

[tool.coverage.report]
precision = 2
show_missing = true
fail_under = 90  # Enterprise-Standard: 90%
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
]
```

### Coverage Workflow (`coverage.yml`)

```yaml
- name: Run Tests with Coverage
  run: |
    pytest tests/ \
      --cov=app \
      --cov-report=xml \
      --cov-report=html \
      --cov-report=term-missing \
      --cov-branch \
      --cov-fail-under=80

- name: Upload Coverage to Codecov
  uses: codecov/codecov-action@v4
  with:
    files: ./coverage.xml
    fail_ci_if_error: true

- name: Comment Coverage on PR
  if: github.event_name == 'pull_request'
  uses: actions/github-script@v7
  with:
    script: |
      const coverage = '${{ env.COVERAGE_PERCENT }}';
      const comment = `## 📊 Coverage: ${coverage}%
      ${coverage >= 80 ? '✅ Meets threshold!' : '⚠️ Below 80%'}`;
      await github.rest.issues.createComment({...});
```

### Coverage-Thresholds

| Bereich | Minimum | Empfohlen |
|---------|---------|-----------|
| Gesamt | 80% | 90% |
| Critical Paths | 90% | 95% |
| Neue Dateien | 80% | 100% |

---

## Flaky Test Handling

### Retry-Strategien

**Celery Task Retry**
```python
@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    acks_late=True,
)
async def process_document_task(self, document_id: str):
    try:
        ...
    except TransientError as e:
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
```

**Test-Level Retry mit pytest-rerunfailures**
```bash
# Installation
pip install pytest-rerunfailures

# Verwendung
pytest --reruns 3 --reruns-delay 1

# Nur für bestimmte Marker
pytest -m "flaky" --reruns 3
```

### Flaky Test Marker

```python
import pytest

@pytest.mark.flaky(reruns=3, reruns_delay=2)
def test_network_dependent_operation():
    """Test der von Netzwerk-Timing abhängt."""
    ...

@pytest.mark.flaky(reruns=2, condition=sys.platform == "win32")
def test_windows_specific():
    """Windows-spezifischer flaky Test."""
    ...
```

### Flaky Test Identifikation

```yaml
# In CI: Flaky Tests separat tracken
- name: Run Tests with Flaky Detection
  run: |
    pytest tests/ \
      --json-report \
      --json-report-file=test-results.json

    # Analysiere Flaky-Pattern
    python scripts/analyze_flaky_tests.py test-results.json
```

---

## Test Artifact Management

### Artifact-Upload Strategien

```yaml
# Coverage HTML Report
- uses: actions/upload-artifact@v4
  with:
    name: coverage-html-report
    path: htmlcov/
    retention-days: 30

# Playwright Screenshots (nur bei Fehlern)
- uses: actions/upload-artifact@v4
  if: failure()
  with:
    name: playwright-screenshots-${{ matrix.browser }}
    path: frontend/test-results/
    retention-days: 7

# Security SBOM (90 Tage für Compliance)
- uses: actions/upload-artifact@v4
  with:
    name: sbom-${{ matrix.image.name }}
    path: sbom-${{ matrix.image.name }}.json
    retention-days: 90

# Performance Test Results
- uses: actions/upload-artifact@v4
  with:
    name: load-test-results
    path: results.json
    retention-days: 30
```

### Artifact-Retention Policy

| Artifact-Typ | Retention | Begründung |
|--------------|-----------|------------|
| Coverage Reports | 30 Tage | Historische Analyse |
| Test Screenshots | 7 Tage | Debugging |
| Security SBOM | 90 Tage | Compliance |
| Performance Results | 30 Tage | Trend-Analyse |
| Build Logs | 14 Tage | Standard |

---

## GPU Test Runner

### GPU-Verfügbarkeit prüfen

```python
# tests/gpu/conftest.py
import pytest
import torch

def pytest_configure(config):
    """GPU-Status bei Teststart prüfen."""
    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        print(f"GPU verfügbar: {gpu_name}")
    else:
        print("Keine GPU verfügbar - GPU-Tests werden übersprungen")

@pytest.fixture(scope="session")
def gpu_available():
    return torch.cuda.is_available()

@pytest.fixture
def skip_without_gpu(gpu_available):
    if not gpu_available:
        pytest.skip("GPU nicht verfügbar")
```

### GPU Test Patterns

```python
@pytest.mark.gpu_required
@pytest.mark.skipif(not torch.cuda.is_available(), reason="GPU required")
def test_deepseek_ocr_processing():
    """DeepSeek OCR benötigt GPU."""
    from app.agents.ocr import DeepSeekOCR

    ocr = DeepSeekOCR()
    result = ocr.process(test_image)

    assert result.confidence > 0.9
    assert "ä" in result.text or "ö" in result.text

@pytest.mark.gpu_optional
def test_ocr_with_fallback():
    """OCR mit automatischem CPU-Fallback."""
    from app.services.ocr_orchestrator import OCROrchestrator

    orchestrator = OCROrchestrator()
    result = orchestrator.process(test_image, allow_cpu_fallback=True)

    # Sollte immer funktionieren
    assert result.success
    assert result.backend_used in ["deepseek", "surya", "surya_cpu"]
```

### VRAM-Monitoring in Tests

```python
@pytest.mark.gpu
def test_gpu_memory_under_threshold():
    """GPU-Speicher sollte unter 85% bleiben."""
    import torch

    torch.cuda.reset_peak_memory_stats()

    # OCR-Batch verarbeiten
    results = ocr.process_batch(large_batch)

    peak_memory = torch.cuda.max_memory_allocated() / 1024**3
    total_memory = torch.cuda.get_device_properties(0).total_memory / 1024**3

    assert peak_memory < total_memory * 0.85, \
        f"VRAM {peak_memory:.2f}GB überschreitet 85% von {total_memory:.2f}GB"
```

---

## Pre-Commit Hooks

### Konfiguration (`.pre-commit-config.yaml`)

```yaml
repos:
  # Allgemeine Checks
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
      - id: check-added-large-files
        args: [--maxkb=1024]
      - id: detect-private-key
      - id: debug-statements

  # Python Formatting - Ruff
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.9
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format

  # Type Checking - MyPy
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.8.0
    hooks:
      - id: mypy
        args: [--ignore-missing-imports, --show-error-codes]
        files: ^app/

  # Security - Bandit
  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.6
    hooks:
      - id: bandit
        args: [-c, pyproject.toml]
        files: ^app/

  # Secrets - detect-secrets
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.4.0
    hooks:
      - id: detect-secrets
        args: [--baseline, .secrets.baseline]

  # Docker - Hadolint
  - repo: https://github.com/hadolint/hadolint
    rev: v2.12.0
    hooks:
      - id: hadolint-docker
        args: [--ignore, DL3008, --ignore, DL3013]

  # Commit Messages - Conventional Commits
  - repo: https://github.com/compilerla/conventional-pre-commit
    rev: v3.0.0
    hooks:
      - id: conventional-pre-commit
        stages: [commit-msg]
        args: [--force-scope]
```

### Installation und Verwendung

```bash
# Installation
pip install pre-commit
pre-commit install

# Alle Hooks manuell ausführen
pre-commit run --all-files

# Spezifischen Hook ausführen
pre-commit run ruff --all-files

# Commit-Message Hook installieren
pre-commit install --hook-type commit-msg

# Baseline für Secrets aktualisieren
detect-secrets scan > .secrets.baseline
```

---

## Security Scanning

### Trivy Integration

**Container Scan:**
```yaml
- name: Run Trivy Vulnerability Scanner
  uses: aquasecurity/trivy-action@master
  with:
    image-ref: 'scan-target:${{ matrix.image.name }}'
    format: 'sarif'
    output: 'trivy.sarif'
    severity: 'CRITICAL,HIGH'
    ignore-unfixed: true

- name: Upload to GitHub Security
  uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: 'trivy.sarif'
```

**Filesystem Scan:**
```yaml
- name: Trivy Filesystem Scan
  uses: aquasecurity/trivy-action@master
  with:
    scan-type: 'fs'
    scan-ref: '.'
    format: 'sarif'
    severity: 'CRITICAL,HIGH'
```

**IaC Scan (Terraform, Docker):**
```yaml
- name: Trivy IaC Scan
  uses: aquasecurity/trivy-action@master
  with:
    scan-type: 'config'
    scan-ref: '.'
    format: 'sarif'
```

### SBOM Generation

```yaml
- name: Generate SBOM
  uses: aquasecurity/trivy-action@master
  with:
    format: 'cyclonedx'
    output: 'sbom.json'

- name: Upload SBOM
  uses: actions/upload-artifact@v4
  with:
    name: sbom
    path: sbom.json
    retention-days: 90
```

### Secret Detection

```yaml
# TruffleHog
- name: TruffleHog Secret Scan
  uses: trufflesecurity/trufflehog@main
  with:
    extra_args: --only-verified --fail

# Gitleaks (Alternative)
- name: Gitleaks Scan
  uses: gitleaks/gitleaks-action@v2
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

---

## Performance Testing

### k6 Load Testing

**Smoke Test (Quick Verification):**
```javascript
// tests/performance/smoke-test.js
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 1,
  duration: '30s',
};

export default function () {
  const res = http.get(`${__ENV.BASE_URL}/health`);
  check(res, {
    'status is 200': (r) => r.status === 200,
    'response time < 500ms': (r) => r.timings.duration < 500,
  });
  sleep(1);
}
```

**Load Test:**
```javascript
// tests/performance/load-test.js
export const options = {
  stages: [
    { duration: '2m', target: 10 },   // Ramp up
    { duration: '5m', target: 10 },   // Steady state
    { duration: '2m', target: 50 },   // Spike
    { duration: '2m', target: 0 },    // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'],  // 95% < 500ms
    http_req_failed: ['rate<0.01'],    // < 1% Fehler
  },
};
```

**Stress Test:**
```javascript
// tests/performance/stress-test.js
export const options = {
  stages: [
    { duration: '2m', target: 100 },
    { duration: '5m', target: 100 },
    { duration: '2m', target: 200 },
    { duration: '5m', target: 200 },
    { duration: '2m', target: 0 },
  ],
};
```

### Performance Thresholds

| Endpoint | p95 Target | p99 Target |
|----------|------------|------------|
| `/health` | < 50ms | < 100ms |
| `/api/v1/documents` | < 300ms | < 500ms |
| Document Upload | < 500ms | < 1000ms |
| OCR Processing (GPU) | < 2000ms | < 5000ms |
| OCR Processing (CPU) | < 10000ms | < 15000ms |

---

## Best Practices

### 1. Test-Isolation

```python
# Gute Isolation - eigene Fixtures
@pytest.fixture
async def isolated_db_session():
    """Isolierte DB-Session mit automatischem Rollback."""
    async with engine.begin() as conn:
        await conn.begin_nested()  # SAVEPOINT
        yield conn
        await conn.rollback()  # Automatischer Rollback
```

### 2. Deterministische Tests

```python
# Seed für Reproduzierbarkeit
@pytest.fixture
def seeded_random():
    import random
    random.seed(42)
    yield random
    random.seed()  # Reset
```

### 3. Test-Parallelisierung

```bash
# pytest-xdist für parallele Ausführung
pytest -n auto  # Automatische Worker-Anzahl
pytest -n 4     # 4 Worker
```

### 4. CI-Spezifische Anpassungen

```python
import os

@pytest.fixture
def ci_timeout():
    """Längere Timeouts in CI."""
    return 30 if os.environ.get("CI") else 10
```

### 5. Saubere Artifact-Struktur

```
test-artifacts/
├── coverage/
│   ├── coverage.xml
│   └── htmlcov/
├── screenshots/
│   └── failure-*.png
├── performance/
│   ├── load-results.json
│   └── stress-results.json
└── security/
    ├── trivy.sarif
    └── sbom.json
```

---

## Troubleshooting

### Häufige CI-Fehler

**1. Timeout bei Service-Containern**
```yaml
# Lösung: Health-Check Retries erhöhen
services:
  postgres:
    options: >-
      --health-retries 10
      --health-interval 15s
```

**2. Flaky Tests durch Timing**
```python
# Lösung: Explizites Warten statt sleep
from tenacity import retry, stop_after_attempt, wait_fixed

@retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
async def wait_for_condition():
    assert condition_met()
```

**3. Coverage unter Threshold**
```bash
# Debug: Welche Zeilen fehlen?
pytest --cov=app --cov-report=term-missing

# Bestimmte Bereiche ausschließen
[tool.coverage.run]
omit = ["app/experimental/*"]
```

**4. Pre-Commit schlägt fehl**
```bash
# Cache leeren
pre-commit clean
pre-commit install --install-hooks

# Bestimmten Hook debuggen
pre-commit run mypy --verbose
```

**5. Docker Build Cache fehlt**
```yaml
# GitHub Actions Cache aktivieren
- uses: docker/build-push-action@v5
  with:
    cache-from: type=gha
    cache-to: type=gha,mode=max
```

### Debug-Tipps

```bash
# Lokale CI-Simulation
act -j test-unit  # Mit act (Docker-based)

# Verbose pytest Output
pytest -vvv --tb=long

# Nur fehlgeschlagene Tests wiederholen
pytest --lf  # Last failed

# Test mit pdb Debugger
pytest --pdb --pdb-first
```

---

## CI/CD Checkliste

### Vor jedem PR

- [ ] `pre-commit run --all-files` lokal ausführen
- [ ] `pytest tests/unit/` erfolgreich
- [ ] Coverage >= 80%
- [ ] Keine Secrets im Code (detect-secrets)
- [ ] Conventional Commit Message

### Vor Release

- [ ] Alle CI-Workflows grün
- [ ] Security Scan ohne CRITICAL
- [ ] E2E-Tests bestanden
- [ ] Performance-Tests im Threshold
- [ ] SBOM generiert
- [ ] Changelog aktualisiert

---

## Referenzen

- **GitHub Actions Docs**: https://docs.github.com/en/actions
- **pytest Dokumentation**: https://docs.pytest.org
- **Trivy**: https://aquasecurity.github.io/trivy
- **k6**: https://k6.io/docs
- **Pre-commit**: https://pre-commit.com
