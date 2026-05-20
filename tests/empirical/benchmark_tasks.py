"""Benchmark-Tasks für empirische Validierung der Orchestrierung.

100+ reale Tasks verschiedener Komplexität für Token-Savings Messung.
"""

from typing import List, Dict
from dataclasses import dataclass


@dataclass
class BenchmarkTask:
    """Ein Benchmark-Task mit erwarteten Metriken."""
    id: str
    prompt: str
    files: List[str]
    expected_tier: str  # haiku, sonnet, opus
    complexity_category: str  # simple, moderate, complex
    language: str  # de, en
    estimated_tokens: int  # Grobe Schätzung


# =============================================================================
# HAIKU-TASKS (30 Tasks) - Einfache, klar definierte Aufgaben
# =============================================================================

HAIKU_TASKS = [
    # Typos und Formatierung (10 Tasks)
    BenchmarkTask(
        id="H001",
        prompt="Fix typo in README.md line 42: 'documnet' → 'document'",
        files=["README.md"],
        expected_tier="haiku",
        complexity_category="simple",
        language="en",
        estimated_tokens=100
    ),
    BenchmarkTask(
        id="H002",
        prompt="Formatiere Code in app/main.py mit Black (PEP 8 Style)",
        files=["app/main.py"],
        expected_tier="haiku",
        complexity_category="simple",
        language="de",
        estimated_tokens=120
    ),
    BenchmarkTask(
        id="H003",
        prompt="Remove trailing whitespace from all Python files in app/utils/",
        files=["app/utils/"],
        expected_tier="haiku",
        complexity_category="simple",
        language="en",
        estimated_tokens=110
    ),
    BenchmarkTask(
        id="H004",
        prompt="Korrigiere Einrückung in tests/conftest.py (4 Leerzeichen statt Tab)",
        files=["tests/conftest.py"],
        expected_tier="haiku",
        complexity_category="simple",
        language="de",
        estimated_tokens=105
    ),
    BenchmarkTask(
        id="H005",
        prompt="Update copyright year in LICENSE file from 2024 to 2025",
        files=["LICENSE"],
        expected_tier="haiku",
        complexity_category="simple",
        language="en",
        estimated_tokens=90
    ),
    BenchmarkTask(
        id="H006",
        prompt="Sortiere Imports in app/services/ocr_service.py alphabetisch",
        files=["app/services/ocr_service.py"],
        expected_tier="haiku",
        complexity_category="simple",
        language="de",
        estimated_tokens=115
    ),
    BenchmarkTask(
        id="H007",
        prompt="Add missing docstring to function process_image() in app/utils/image.py",
        files=["app/utils/image.py"],
        expected_tier="haiku",
        complexity_category="simple",
        language="en",
        estimated_tokens=130
    ),
    BenchmarkTask(
        id="H008",
        prompt="Ersetze alle print() Statements mit logger.info() in app/debug.py",
        files=["app/debug.py"],
        expected_tier="haiku",
        complexity_category="simple",
        language="de",
        estimated_tokens=125
    ),
    BenchmarkTask(
        id="H009",
        prompt="Fix inconsistent quote style in app/config.py (all double quotes)",
        files=["app/config.py"],
        expected_tier="haiku",
        complexity_category="simple",
        language="en",
        estimated_tokens=110
    ),
    BenchmarkTask(
        id="H010",
        prompt="Entferne ungenutzte Import-Statement 'from typing import Any' in app/models.py",
        files=["app/models.py"],
        expected_tier="haiku",
        complexity_category="simple",
        language="de",
        estimated_tokens=100
    ),

    # Kleine Code-Fixes (10 Tasks)
    BenchmarkTask(
        id="H011",
        prompt="Fix variable name typo: 'doc_id' → 'document_id' in app/api/documents.py",
        files=["app/api/documents.py"],
        expected_tier="haiku",
        complexity_category="simple",
        language="en",
        estimated_tokens=120
    ),
    BenchmarkTask(
        id="H012",
        prompt="Ändere Default-Wert von timeout von 30 auf 60 Sekunden in app/config.py",
        files=["app/config.py"],
        expected_tier="haiku",
        complexity_category="simple",
        language="de",
        estimated_tokens=105
    ),
    BenchmarkTask(
        id="H013",
        prompt="Add type hint to function return: def get_user() → Optional[User]",
        files=["app/users.py"],
        expected_tier="haiku",
        complexity_category="simple",
        language="en",
        estimated_tokens=115
    ),
    BenchmarkTask(
        id="H014",
        prompt="Korrigiere Fehlermeldung: 'Dokument nicht gefunden' statt 'Document not found'",
        files=["app/errors.py"],
        expected_tier="haiku",
        complexity_category="simple",
        language="de",
        estimated_tokens=110
    ),
    BenchmarkTask(
        id="H015",
        prompt="Update deprecated pytest.raises syntax to context manager in test_api.py",
        files=["tests/test_api.py"],
        expected_tier="haiku",
        complexity_category="simple",
        language="en",
        estimated_tokens=125
    ),
    BenchmarkTask(
        id="H016",
        prompt="Füge Kommentar zu komplexer Regex in app/validators.py hinzu",
        files=["app/validators.py"],
        expected_tier="haiku",
        complexity_category="simple",
        language="de",
        estimated_tokens=120
    ),
    BenchmarkTask(
        id="H017",
        prompt="Change log level from DEBUG to INFO in production config",
        files=["app/config/production.py"],
        expected_tier="haiku",
        complexity_category="simple",
        language="en",
        estimated_tokens=100
    ),
    BenchmarkTask(
        id="H018",
        prompt="Ersetze hardcoded Port 8000 mit Umgebungsvariable PORT in app/main.py",
        files=["app/main.py"],
        expected_tier="haiku",
        complexity_category="simple",
        language="de",
        estimated_tokens=130
    ),
    BenchmarkTask(
        id="H019",
        prompt="Fix SQLAlchemy warning: use select() instead of Query.filter()",
        files=["app/db/repositories.py"],
        expected_tier="haiku",
        complexity_category="simple",
        language="en",
        estimated_tokens=140
    ),
    BenchmarkTask(
        id="H020",
        prompt="Aktualisiere requirements.txt: fastapi>=0.110.0 statt >=0.109.0",
        files=["requirements.txt"],
        expected_tier="haiku",
        complexity_category="simple",
        language="de",
        estimated_tokens=95
    ),

    # Einfache Dokumentation (10 Tasks)
    BenchmarkTask(
        id="H021",
        prompt="Add usage example to README.md for /api/v1/documents endpoint",
        files=["README.md"],
        expected_tier="haiku",
        complexity_category="simple",
        language="en",
        estimated_tokens=150
    ),
    BenchmarkTask(
        id="H022",
        prompt="Ergänze Beschreibung für Parameter 'ocr_backend' in API-Dokumentation",
        files=["docs/api.md"],
        expected_tier="haiku",
        complexity_category="simple",
        language="de",
        estimated_tokens=135
    ),
    BenchmarkTask(
        id="H023",
        prompt="Fix broken link in CONTRIBUTING.md to code of conduct",
        files=["CONTRIBUTING.md"],
        expected_tier="haiku",
        complexity_category="simple",
        language="en",
        estimated_tokens=100
    ),
    BenchmarkTask(
        id="H024",
        prompt="Füge Abschnitt 'Häufige Fehler' zu docs/troubleshooting.md hinzu",
        files=["docs/troubleshooting.md"],
        expected_tier="haiku",
        complexity_category="simple",
        language="de",
        estimated_tokens=140
    ),
    BenchmarkTask(
        id="H025",
        prompt="Update version number in package.json from 1.0.0 to 1.1.0",
        files=["package.json"],
        expected_tier="haiku",
        complexity_category="simple",
        language="en",
        estimated_tokens=90
    ),
    BenchmarkTask(
        id="H026",
        prompt="Korrigiere Markdown-Formatierung in CHANGELOG.md (fehlende Leerzeichen)",
        files=["CHANGELOG.md"],
        expected_tier="haiku",
        complexity_category="simple",
        language="de",
        estimated_tokens=105
    ),
    BenchmarkTask(
        id="H027",
        prompt="Add table of contents to long documentation file docs/architecture.md",
        files=["docs/architecture.md"],
        expected_tier="haiku",
        complexity_category="simple",
        language="en",
        estimated_tokens=120
    ),
    BenchmarkTask(
        id="H028",
        prompt="Ergänze fehlende Parameterbeschreibung in Docstring von process_document()",
        files=["app/services/document_service.py"],
        expected_tier="haiku",
        complexity_category="simple",
        language="de",
        estimated_tokens=125
    ),
    BenchmarkTask(
        id="H029",
        prompt="Update outdated screenshot in docs/user-guide.md with current UI",
        files=["docs/user-guide.md", "docs/assets/screenshot.png"],
        expected_tier="haiku",
        complexity_category="simple",
        language="en",
        estimated_tokens=110
    ),
    BenchmarkTask(
        id="H030",
        prompt="Füge Beispiel für deutschen Fehlertext zu docs/i18n.md hinzu",
        files=["docs/i18n.md"],
        expected_tier="haiku",
        complexity_category="simple",
        language="de",
        estimated_tokens=130
    ),
]


# =============================================================================
# SONNET-TASKS (50 Tasks) - Standard-Implementierungen
# =============================================================================

SONNET_TASKS = [
    # API Endpoints (10 Tasks)
    BenchmarkTask(
        id="S001",
        prompt="Implement GET /api/v1/documents/{id} endpoint with authentication",
        files=["app/api/v1/documents.py", "tests/test_api_documents.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="en",
        estimated_tokens=800
    ),
    BenchmarkTask(
        id="S002",
        prompt="Implementiere POST /api/v1/ocr/process Endpoint mit Celery-Task Integration",
        files=["app/api/v1/ocr.py", "app/workers/ocr_tasks.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="de",
        estimated_tokens=850
    ),
    BenchmarkTask(
        id="S003",
        prompt="Add pagination to /api/v1/documents list endpoint (limit/offset)",
        files=["app/api/v1/documents.py", "app/db/repositories.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="en",
        estimated_tokens=750
    ),
    BenchmarkTask(
        id="S004",
        prompt="Implementiere DELETE /api/v1/documents/{id} mit Soft-Delete und Audit-Log",
        files=["app/api/v1/documents.py", "app/db/models.py", "app/services/audit.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="de",
        estimated_tokens=900
    ),
    BenchmarkTask(
        id="S005",
        prompt="Add filter parameters to documents API (date range, status, language)",
        files=["app/api/v1/documents.py", "app/db/repositories.py", "app/schemas.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="en",
        estimated_tokens=820
    ),
    BenchmarkTask(
        id="S006",
        prompt="Implementiere PATCH /api/v1/documents/{id}/metadata für Metadaten-Update",
        files=["app/api/v1/documents.py", "tests/test_api_documents.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="de",
        estimated_tokens=780
    ),
    BenchmarkTask(
        id="S007",
        prompt="Add rate limiting to OCR API endpoints (10 requests per minute per user)",
        files=["app/api/v1/ocr.py", "app/core/rate_limiter.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="en",
        estimated_tokens=850
    ),
    BenchmarkTask(
        id="S008",
        prompt="Implementiere GET /api/v1/documents/{id}/history für Versions-Historie",
        files=["app/api/v1/documents.py", "app/db/models.py", "app/db/repositories.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="de",
        estimated_tokens=880
    ),
    BenchmarkTask(
        id="S009",
        prompt="Add bulk upload endpoint POST /api/v1/documents/bulk (multiple files)",
        files=["app/api/v1/documents.py", "app/services/document_service.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="en",
        estimated_tokens=920
    ),
    BenchmarkTask(
        id="S010",
        prompt="Implementiere WebSocket Endpoint für Live-OCR-Progress Updates",
        files=["app/api/v1/websockets.py", "app/workers/ocr_tasks.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="de",
        estimated_tokens=950
    ),

    # Datenbank & Models (10 Tasks)
    BenchmarkTask(
        id="S011",
        prompt="Add User model with authentication fields and relationships to Documents",
        files=["app/db/models.py", "migrations/"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="en",
        estimated_tokens=800
    ),
    BenchmarkTask(
        id="S012",
        prompt="Implementiere DocumentVersion Model für Versions-Historie mit Diffs",
        files=["app/db/models.py", "app/db/repositories.py", "migrations/"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="de",
        estimated_tokens=870
    ),
    BenchmarkTask(
        id="S013",
        prompt="Add full-text search index on Document.extracted_text field (PostgreSQL)",
        files=["app/db/models.py", "migrations/", "app/db/repositories.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="en",
        estimated_tokens=750
    ),
    BenchmarkTask(
        id="S014",
        prompt="Implementiere Cascade Delete für User → Documents → OCRResults Beziehung",
        files=["app/db/models.py", "migrations/"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="de",
        estimated_tokens=720
    ),
    BenchmarkTask(
        id="S015",
        prompt="Add composite index on (user_id, created_at) for faster queries",
        files=["app/db/models.py", "migrations/"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="en",
        estimated_tokens=650
    ),
    BenchmarkTask(
        id="S016",
        prompt="Implementiere Repository Pattern für Document CRUD Operationen",
        files=["app/db/repositories.py", "tests/test_repositories.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="de",
        estimated_tokens=880
    ),
    BenchmarkTask(
        id="S017",
        prompt="Add database connection pooling configuration for production",
        files=["app/core/database.py", "app/config.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="en",
        estimated_tokens=700
    ),
    BenchmarkTask(
        id="S018",
        prompt="Implementiere Alembic Migration für neue Tag-Tabelle mit Many-to-Many zu Documents",
        files=["migrations/", "app/db/models.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="de",
        estimated_tokens=820
    ),
    BenchmarkTask(
        id="S019",
        prompt="Add SQLAlchemy event listeners for automatic timestamp updates",
        files=["app/db/models.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="en",
        estimated_tokens=680
    ),
    BenchmarkTask(
        id="S020",
        prompt="Implementiere Soft-Delete Mixin für alle Models mit deleted_at Feld",
        files=["app/db/models.py", "app/db/mixins.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="de",
        estimated_tokens=750
    ),

    # Business Logic & Services (15 Tasks)
    BenchmarkTask(
        id="S021",
        prompt="Implement email verification service with token generation and validation",
        files=["app/services/email_verification.py", "tests/test_email_verification.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="en",
        estimated_tokens=900
    ),
    BenchmarkTask(
        id="S022",
        prompt="Implementiere Document-Sharing Service mit Permissions (read/write/admin)",
        files=["app/services/sharing_service.py", "app/db/models.py", "tests/"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="de",
        estimated_tokens=950
    ),
    BenchmarkTask(
        id="S023",
        prompt="Add caching layer for frequently accessed documents (Redis integration)",
        files=["app/services/cache_service.py", "app/services/document_service.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="en",
        estimated_tokens=850
    ),
    BenchmarkTask(
        id="S024",
        prompt="Implementiere Thumbnail-Generierung für PDF-Dokumente (erste Seite)",
        files=["app/services/thumbnail_service.py", "app/workers/thumbnail_tasks.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="de",
        estimated_tokens=880
    ),
    BenchmarkTask(
        id="S025",
        prompt="Add audit logging service for all document operations (create/update/delete)",
        files=["app/services/audit_service.py", "app/db/models.py", "app/api/v1/documents.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="en",
        estimated_tokens=920
    ),
    BenchmarkTask(
        id="S026",
        prompt="Implementiere Notification Service für OCR-Completion Events (Email + Webhook)",
        files=["app/services/notification_service.py", "app/workers/ocr_tasks.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="de",
        estimated_tokens=870
    ),
    BenchmarkTask(
        id="S027",
        prompt="Add document export service (PDF, DOCX, TXT formats)",
        files=["app/services/export_service.py", "tests/test_export_service.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="en",
        estimated_tokens=900
    ),
    BenchmarkTask(
        id="S028",
        prompt="Implementiere Duplicate-Detection für hochgeladene Dokumente (Hash-Vergleich)",
        files=["app/services/duplicate_detection.py", "app/db/repositories.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="de",
        estimated_tokens=820
    ),
    BenchmarkTask(
        id="S029",
        prompt="Add batch processing service for multiple documents (parallel OCR)",
        files=["app/services/batch_service.py", "app/workers/batch_tasks.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="en",
        estimated_tokens=950
    ),
    BenchmarkTask(
        id="S030",
        prompt="Implementiere Search Service mit Elasticsearch-Integration und Ranking",
        files=["app/services/search_service.py", "app/core/elasticsearch.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="de",
        estimated_tokens=980
    ),
    BenchmarkTask(
        id="S031",
        prompt="Add password reset service with email tokens and expiration",
        files=["app/services/password_reset.py", "app/api/v1/auth.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="en",
        estimated_tokens=850
    ),
    BenchmarkTask(
        id="S032",
        prompt="Implementiere Quota-Management für Benutzer (max Dokumente, Speicher)",
        files=["app/services/quota_service.py", "app/db/models.py", "app/api/v1/documents.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="de",
        estimated_tokens=890
    ),
    BenchmarkTask(
        id="S033",
        prompt="Add document encryption service (AES-256) for sensitive files",
        files=["app/services/encryption_service.py", "app/services/document_service.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="en",
        estimated_tokens=920
    ),
    BenchmarkTask(
        id="S034",
        prompt="Implementiere Backup Service für automatische Dokument-Backups (täglich)",
        files=["app/services/backup_service.py", "app/workers/backup_tasks.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="de",
        estimated_tokens=880
    ),
    BenchmarkTask(
        id="S035",
        prompt="Add analytics service for document processing statistics (Prometheus metrics)",
        files=["app/services/analytics_service.py", "app/core/metrics.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="en",
        estimated_tokens=850
    ),

    # Tests (15 Tasks)
    BenchmarkTask(
        id="S036",
        prompt="Add unit tests for DocumentService with mocked database",
        files=["tests/unit/test_document_service.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="en",
        estimated_tokens=900
    ),
    BenchmarkTask(
        id="S037",
        prompt="Implementiere Integration-Tests für /api/v1/documents Endpoints (CRUD)",
        files=["tests/integration/test_api_documents.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="de",
        estimated_tokens=950
    ),
    BenchmarkTask(
        id="S038",
        prompt="Add parametrized tests for OCR backend selection logic",
        files=["tests/unit/test_ocr_orchestrator.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="en",
        estimated_tokens=820
    ),
    BenchmarkTask(
        id="S039",
        prompt="Implementiere Fixtures für Test-Dokumente (PDF, PNG, JPG)",
        files=["tests/conftest.py", "tests/fixtures/"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="de",
        estimated_tokens=750
    ),
    BenchmarkTask(
        id="S040",
        prompt="Add end-to-end test for complete document upload → OCR → retrieval workflow",
        files=["tests/e2e/test_document_workflow.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="en",
        estimated_tokens=980
    ),
    BenchmarkTask(
        id="S041",
        prompt="Implementiere Performance-Tests für API-Endpoints (response time < 500ms)",
        files=["tests/performance/test_api_performance.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="de",
        estimated_tokens=880
    ),
    BenchmarkTask(
        id="S042",
        prompt="Add security tests for authentication endpoints (SQL injection, XSS)",
        files=["tests/security/test_auth_security.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="en",
        estimated_tokens=920
    ),
    BenchmarkTask(
        id="S043",
        prompt="Implementiere Mock für Celery Worker in Unit-Tests",
        files=["tests/conftest.py", "tests/unit/test_celery_tasks.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="de",
        estimated_tokens=850
    ),
    BenchmarkTask(
        id="S044",
        prompt="Add database migration tests (rollback + upgrade scenarios)",
        files=["tests/test_migrations.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="en",
        estimated_tokens=800
    ),
    BenchmarkTask(
        id="S045",
        prompt="Implementiere Load-Tests für OCR-Pipeline (100 concurrent documents)",
        files=["tests/load/test_ocr_load.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="de",
        estimated_tokens=950
    ),
    BenchmarkTask(
        id="S046",
        prompt="Add snapshot tests for API response schemas",
        files=["tests/unit/test_api_schemas.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="en",
        estimated_tokens=780
    ),
    BenchmarkTask(
        id="S047",
        prompt="Implementiere Negative Tests für ungültige API-Requests (400 errors)",
        files=["tests/integration/test_api_validation.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="de",
        estimated_tokens=870
    ),
    BenchmarkTask(
        id="S048",
        prompt="Add test coverage reporting with pytest-cov (target: 90%)",
        files=["tests/conftest.py", ".github/workflows/test.yml"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="en",
        estimated_tokens=720
    ),
    BenchmarkTask(
        id="S049",
        prompt="Implementiere GPU-Tests mit Mock für torch.cuda (falls GPU nicht verfügbar)",
        files=["tests/unit/test_gpu_manager.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="de",
        estimated_tokens=850
    ),
    BenchmarkTask(
        id="S050",
        prompt="Add contract tests for external OCR API integrations",
        files=["tests/contract/test_ocr_apis.py"],
        expected_tier="sonnet",
        complexity_category="moderate",
        language="en",
        estimated_tokens=880
    ),
]


# =============================================================================
# OPUS-TASKS (20 Tasks) - Komplexe Architektur & große Refactorings
# =============================================================================

OPUS_TASKS = [
    # Architektur & Design (10 Tasks)
    BenchmarkTask(
        id="O001",
        prompt="Design distributed consensus algorithm for multi-datacenter deployment with Byzantine fault tolerance",
        files=["app/core/consensus.py", "app/core/distributed.py", "docs/architecture/consensus.md"],
        expected_tier="opus",
        complexity_category="complex",
        language="en",
        estimated_tokens=2000
    ),
    BenchmarkTask(
        id="O002",
        prompt="Implementiere Event-Sourcing Architecture für Document-Lifecycle mit CQRS Pattern",
        files=["app/core/events.py", "app/core/commands.py", "app/core/projections.py", "docs/architecture/event_sourcing.md"],
        expected_tier="opus",
        complexity_category="complex",
        language="de",
        estimated_tokens=2200
    ),
    BenchmarkTask(
        id="O003",
        prompt="Design plugin system for extensible OCR backends with dynamic loading and versioning",
        files=["app/core/plugins.py", "app/agents/ocr/plugin_interface.py", "docs/plugin_development.md"],
        expected_tier="opus",
        complexity_category="complex",
        language="en",
        estimated_tokens=1900
    ),
    BenchmarkTask(
        id="O004",
        prompt="Implementiere Multi-Tenancy Architecture mit tenant-isolierter Datenbank und Ressourcen",
        files=["app/core/tenancy.py", "app/db/tenant_models.py", "app/middleware/tenant_middleware.py", "docs/architecture/multi_tenancy.md"],
        expected_tier="opus",
        complexity_category="complex",
        language="de",
        estimated_tokens=2300
    ),
    BenchmarkTask(
        id="O005",
        prompt="Design real-time collaboration system for document annotation (CRDTs + WebSockets)",
        files=["app/core/collaboration.py", "app/core/crdt.py", "app/api/v1/websockets_collab.py"],
        expected_tier="opus",
        complexity_category="complex",
        language="en",
        estimated_tokens=2100
    ),
    BenchmarkTask(
        id="O006",
        prompt="Implementiere Distributed Tracing System mit OpenTelemetry für Microservices",
        files=["app/core/tracing.py", "app/middleware/tracing_middleware.py", "docker-compose.tracing.yml"],
        expected_tier="opus",
        complexity_category="complex",
        language="de",
        estimated_tokens=1850
    ),
    BenchmarkTask(
        id="O007",
        prompt="Design blue-green deployment strategy with automated rollback and health checks",
        files=["infrastructure/terraform/blue_green.tf", "infrastructure/ansible/deploy_blue_green.yml", "docs/deployment/blue_green.md"],
        expected_tier="opus",
        complexity_category="complex",
        language="en",
        estimated_tokens=2000
    ),
    BenchmarkTask(
        id="O008",
        prompt="Implementiere GraphQL API Layer mit DataLoader für N+1 Query-Optimierung",
        files=["app/api/graphql/schema.py", "app/api/graphql/resolvers.py", "app/api/graphql/dataloaders.py"],
        expected_tier="opus",
        complexity_category="complex",
        language="de",
        estimated_tokens=2150
    ),
    BenchmarkTask(
        id="O009",
        prompt="Design distributed rate limiting with Redis Cluster and sliding window algorithm",
        files=["app/core/rate_limiter_distributed.py", "app/core/sliding_window.py", "docs/architecture/rate_limiting.md"],
        expected_tier="opus",
        complexity_category="complex",
        language="en",
        estimated_tokens=1950
    ),
    BenchmarkTask(
        id="O010",
        prompt="Implementiere Circuit Breaker Pattern für alle externen Service-Calls mit Fallback-Strategie",
        files=["app/core/circuit_breaker.py", "app/services/external_service_base.py", "app/core/fallback.py"],
        expected_tier="opus",
        complexity_category="complex",
        language="de",
        estimated_tokens=2050
    ),

    # Große Refactorings (10 Tasks)
    BenchmarkTask(
        id="O011",
        prompt="Refactor entire authentication system to support OAuth2, SAML, and LDAP with unified interface",
        files=["app/core/auth/", "app/api/v1/auth.py", "app/db/models.py", "tests/integration/test_auth.py"],
        expected_tier="opus",
        complexity_category="complex",
        language="en",
        estimated_tokens=2400
    ),
    BenchmarkTask(
        id="O012",
        prompt="Migriere synchrone API zu vollständig asynchroner Architektur (async/await überall)",
        files=["app/api/", "app/services/", "app/db/", "tests/"],
        expected_tier="opus",
        complexity_category="complex",
        language="de",
        estimated_tokens=2500
    ),
    BenchmarkTask(
        id="O013",
        prompt="Refactor monolithic OCR service into microservices architecture (3 services: upload, processing, retrieval)",
        files=["services/upload/", "services/processing/", "services/retrieval/", "docker-compose.microservices.yml"],
        expected_tier="opus",
        complexity_category="complex",
        language="en",
        estimated_tokens=2600
    ),
    BenchmarkTask(
        id="O014",
        prompt="Implementiere Zero-Downtime-Migration von PostgreSQL zu multi-region setup mit Replication",
        files=["infrastructure/terraform/database_cluster.tf", "scripts/migrate_multi_region.py", "docs/migration/multi_region.md"],
        expected_tier="opus",
        complexity_category="complex",
        language="de",
        estimated_tokens=2300
    ),
    BenchmarkTask(
        id="O015",
        prompt="Refactor frontend to micro-frontends architecture with Module Federation",
        files=["frontend/shell/", "frontend/documents/", "frontend/admin/", "webpack.config.js"],
        expected_tier="opus",
        complexity_category="complex",
        language="en",
        estimated_tokens=2200
    ),
    BenchmarkTask(
        id="O016",
        prompt="Migriere gesamte Codebase zu Domain-Driven Design mit Bounded Contexts",
        files=["app/domains/documents/", "app/domains/users/", "app/domains/ocr/", "app/shared/"],
        expected_tier="opus",
        complexity_category="complex",
        language="de",
        estimated_tokens=2700
    ),
    BenchmarkTask(
        id="O017",
        prompt="Implement comprehensive observability stack (metrics, logs, traces) with correlation IDs",
        files=["app/core/observability.py", "app/middleware/observability_middleware.py", "infrastructure/monitoring/"],
        expected_tier="opus",
        complexity_category="complex",
        language="en",
        estimated_tokens=2150
    ),
    BenchmarkTask(
        id="O018",
        prompt="Refaktoriere Datenbank-Schema für horizontale Skalierung mit Sharding-Strategie",
        files=["app/db/sharding.py", "app/db/models.py", "migrations/", "docs/architecture/sharding.md"],
        expected_tier="opus",
        complexity_category="complex",
        language="de",
        estimated_tokens=2450
    ),
    BenchmarkTask(
        id="O019",
        prompt="Migrate entire test suite to behavior-driven development (BDD) with Gherkin scenarios",
        files=["tests/features/", "tests/step_definitions/", "tests/conftest.py"],
        expected_tier="opus",
        complexity_category="complex",
        language="en",
        estimated_tokens=2350
    ),
    BenchmarkTask(
        id="O020",
        prompt="Implementiere Feature-Flag-System mit A/B-Testing, Rollout-Strategie und Analytics",
        files=["app/core/feature_flags.py", "app/core/ab_testing.py", "app/services/analytics_service.py", "docs/feature_flags.md"],
        expected_tier="opus",
        complexity_category="complex",
        language="de",
        estimated_tokens=2250
    ),
]


# Kombiniere alle Tasks
ALL_BENCHMARK_TASKS = HAIKU_TASKS + SONNET_TASKS + OPUS_TASKS


def get_tasks_by_tier(tier: str) -> List[BenchmarkTask]:
    """Gibt alle Tasks eines bestimmten Tiers zurück."""
    return [task for task in ALL_BENCHMARK_TASKS if task.expected_tier == tier]


def get_tasks_by_language(language: str) -> List[BenchmarkTask]:
    """Gibt alle Tasks einer bestimmten Sprache zurück."""
    return [task for task in ALL_BENCHMARK_TASKS if task.language == language]


def get_task_statistics() -> Dict[str, int]:
    """Berechne Statistiken über die Benchmark-Suite."""
    return {
        "total_tasks": len(ALL_BENCHMARK_TASKS),
        "haiku_tasks": len(HAIKU_TASKS),
        "sonnet_tasks": len(SONNET_TASKS),
        "opus_tasks": len(OPUS_TASKS),
        "german_tasks": len([t for t in ALL_BENCHMARK_TASKS if t.language == "de"]),
        "english_tasks": len([t for t in ALL_BENCHMARK_TASKS if t.language == "en"]),
        "estimated_total_tokens": sum(t.estimated_tokens for t in ALL_BENCHMARK_TASKS),
    }
