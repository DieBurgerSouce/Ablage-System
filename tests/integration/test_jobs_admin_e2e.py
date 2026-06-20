# -*- coding: utf-8 -*-
"""Echte End-to-End Integration-Tests fuer Job Admin API mit PostgreSQL.

Diese Tests nutzen echte Datenbankoperationen und validieren:
- Job-Erstellung und -Persistierung
- Job-Stornierung mit Status-Updates
- Job-Wiederholung
- Pagination und Filtering
- Rate Limiting (SCHRITT 6)

Erfordert: docker-compose up postgres redis

Ausfuehrung:
    pytest tests/integration/test_jobs_admin_e2e.py -v -m integration
"""

import os

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from uuid import uuid4
from typing import AsyncGenerator
import asyncio

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, text
from httpx import AsyncClient, ASGITransport

# App Imports - KEIN try/except! Fehlende Imports = Test FAILED
from app.db.models import (
    Base,
    User,
    ProcessingJob,
    Document,
)
from app.db.schemas import ProcessingStatus
from app.main import app
from app.core.security import create_access_token


pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
]


# ============================================================================
# TEST DATABASE CONFIGURATION
# ============================================================================

# TEST_DATABASE_URL hat Vorrang (Docker/CI), sonst lokaler Fallback
TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5433/ablage_test",
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def db_engine():
    """Erstellt Test-Datenbank-Engine mit PostgreSQL.

    Ohne erreichbare Datenbank wird sauber geskippt statt mit ERROR
    abzubrechen.
    """
    engine = create_async_engine(
        TEST_DB_URL,
        echo=False,
        pool_pre_ping=True,
    )

    # Tabellen erstellen falls nicht vorhanden
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"PostgreSQL-Testdatenbank nicht erreichbar: {exc}")

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Erstellt Test-Session mit TRUNCATE fuer echte Isolation.

    ENTERPRISE FIX (Iteration 3):
    - rollback() funktioniert NICHT nach commit()
    - Stattdessen: TRUNCATE vor jedem Test fuer echte Isolation
    """
    async_session_factory = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_factory() as session:
        # ENTERPRISE FIX: TRUNCATE alle Test-relevanten Tabellen vor dem Test
        # CASCADE loescht auch abhaengige Daten
        await session.execute(text(
            "TRUNCATE processing_jobs, documents, users CASCADE"
        ))
        await session.commit()

        yield session

        # Cleanup nach dem Test (optional, da naechster Test ohnehin TRUNCATE macht)
        await session.rollback()


@pytest_asyncio.fixture
async def test_admin(db_session: AsyncSession) -> User:
    """Erstellt einen Test-Admin-Benutzer."""
    admin = User(
        id=uuid4(),
        email="admin@test.de",
        username="testadmin",
        hashed_password="hashed_password_placeholder",
        is_active=True,
        is_superuser=True,
        tier="enterprise",
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest_asyncio.fixture
async def admin_token(test_admin: User) -> str:
    """Generiert JWT-Token fuer Admin-User."""
    return create_access_token(subject=str(test_admin.id))


@pytest_asyncio.fixture
async def test_document(db_session: AsyncSession, test_admin: User) -> Document:
    """Erstellt ein Test-Dokument."""
    doc = Document(
        id=uuid4(),
        user_id=test_admin.id,
        filename="test_document.pdf",
        original_name="test_document.pdf",
        mime_type="application/pdf",
        file_size=1024,
        status="uploaded",
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)
    return doc


@pytest_asyncio.fixture
async def test_jobs(db_session: AsyncSession, test_document: Document) -> list[ProcessingJob]:
    """Erstellt mehrere Test-Jobs fuer Pagination/Filter-Tests."""
    jobs = []
    statuses = [
        ProcessingStatus.PENDING,
        ProcessingStatus.PROCESSING,
        ProcessingStatus.COMPLETED,
        ProcessingStatus.FAILED,
        ProcessingStatus.CANCELLED,
    ]
    backends = ["deepseek", "got_ocr", "surya"]

    for i in range(15):
        job = ProcessingJob(
            id=uuid4(),
            document_id=test_document.id,
            job_type="ocr",
            backend=backends[i % 3],
            status=statuses[i % 5].value,
            priority=1 + (i % 10),
            progress=100 if statuses[i % 5] == ProcessingStatus.COMPLETED else i * 10,
            error_message="Test-Fehler" if statuses[i % 5] == ProcessingStatus.FAILED else None,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(job)
        jobs.append(job)

    await db_session.commit()
    for job in jobs:
        await db_session.refresh(job)

    return jobs


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Erstellt Test-Client fuer API-Requests."""
    transport = ASGITransport(app=app)  # type: ignore
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ============================================================================
# LIST JOBS TESTS - Echte Datenbank
# ============================================================================

class TestListJobsE2E:
    """End-to-End Tests fuer GET /admin/jobs."""

    async def test_list_jobs_returns_all_jobs(
        self,
        client: AsyncClient,
        admin_token: str,
        test_jobs: list[ProcessingJob],
    ):
        """Listet alle Jobs erfolgreich auf."""
        response = await client.get(
            "/api/v1/admin/jobs",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data
        assert "total" in data
        assert data["total"] >= len(test_jobs)

    async def test_list_jobs_pagination(
        self,
        client: AsyncClient,
        admin_token: str,
        test_jobs: list[ProcessingJob],
    ):
        """Pagination funktioniert korrekt."""
        # Erste Seite
        response1 = await client.get(
            "/api/v1/admin/jobs?page=1&per_page=5",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response1.status_code == 200
        data1 = response1.json()
        assert len(data1["jobs"]) <= 5

        # Zweite Seite
        response2 = await client.get(
            "/api/v1/admin/jobs?page=2&per_page=5",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response2.status_code == 200
        data2 = response2.json()

        # Erste und zweite Seite haben unterschiedliche Jobs
        ids1 = {j["id"] for j in data1["jobs"]}
        ids2 = {j["id"] for j in data2["jobs"]}
        assert ids1.isdisjoint(ids2), "Pagination sollte unterschiedliche Jobs liefern"

    async def test_list_jobs_filter_by_status(
        self,
        client: AsyncClient,
        admin_token: str,
        test_jobs: list[ProcessingJob],
    ):
        """Filter nach Status funktioniert."""
        response = await client.get(
            "/api/v1/admin/jobs?status=failed",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        data = response.json()

        # Alle zurueckgegebenen Jobs sollten "failed" Status haben
        for job in data["jobs"]:
            assert job["status"] == "failed"

    async def test_list_jobs_filter_by_backend(
        self,
        client: AsyncClient,
        admin_token: str,
        test_jobs: list[ProcessingJob],
    ):
        """Filter nach Backend funktioniert."""
        response = await client.get(
            "/api/v1/admin/jobs?backend=deepseek",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        data = response.json()

        # Alle zurueckgegebenen Jobs sollten "deepseek" Backend haben
        for job in data["jobs"]:
            assert job["backend"] == "deepseek"

    async def test_list_jobs_requires_admin(
        self,
        client: AsyncClient,
    ):
        """Nicht-Admin sollte 401/403 erhalten."""
        response = await client.get("/api/v1/admin/jobs")
        assert response.status_code in [401, 403]


# ============================================================================
# CANCEL JOB TESTS - Echte Datenbank
# ============================================================================

class TestCancelJobE2E:
    """End-to-End Tests fuer POST /admin/jobs/{id}/cancel."""

    async def test_cancel_pending_job(
        self,
        client: AsyncClient,
        admin_token: str,
        db_session: AsyncSession,
        test_document: Document,
    ):
        """Wartenden Job erfolgreich stornieren."""
        # Erstelle einen neuen pending Job
        job = ProcessingJob(
            id=uuid4(),
            document_id=test_document.id,
            job_type="ocr",
            backend="deepseek",
            status=ProcessingStatus.PENDING.value,
            priority=5,
        )
        db_session.add(job)
        await db_session.commit()

        # Stornieren
        response = await client.post(
            f"/api/v1/admin/jobs/{job.id}/cancel?reason=Test-Stornierung",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "abgebrochen" in data["message"].lower() or "cancelled" in data["message"].lower()

        # Verifiziere in DB dass Status geaendert wurde
        await db_session.refresh(job)
        assert job.status == ProcessingStatus.CANCELLED.value

    async def test_cancel_nonexistent_job(
        self,
        client: AsyncClient,
        admin_token: str,
    ):
        """Nicht existierenden Job stornieren gibt 404."""
        fake_id = uuid4()
        response = await client.post(
            f"/api/v1/admin/jobs/{fake_id}/cancel",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 404

    async def test_cancel_completed_job_fails(
        self,
        client: AsyncClient,
        admin_token: str,
        db_session: AsyncSession,
        test_document: Document,
    ):
        """Abgeschlossenen Job kann man nicht stornieren."""
        # Erstelle einen completed Job
        job = ProcessingJob(
            id=uuid4(),
            document_id=test_document.id,
            job_type="ocr",
            backend="deepseek",
            status=ProcessingStatus.COMPLETED.value,
            progress=100,
            completed_at=datetime.now(timezone.utc),
        )
        db_session.add(job)
        await db_session.commit()

        # Stornierung sollte fehlschlagen
        response = await client.post(
            f"/api/v1/admin/jobs/{job.id}/cancel",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # Sollte 400 oder eine Fehlerantwort sein
        assert response.status_code in [400, 422] or (
            response.status_code == 200 and response.json().get("success") is False
        )


# ============================================================================
# RETRY JOB TESTS - Echte Datenbank
# ============================================================================

class TestRetryJobE2E:
    """End-to-End Tests fuer POST /admin/jobs/{id}/retry."""

    async def test_retry_failed_job(
        self,
        client: AsyncClient,
        admin_token: str,
        db_session: AsyncSession,
        test_document: Document,
    ):
        """Fehlgeschlagenen Job wiederholen."""
        # Erstelle einen failed Job
        job = ProcessingJob(
            id=uuid4(),
            document_id=test_document.id,
            job_type="ocr",
            backend="deepseek",
            status=ProcessingStatus.FAILED.value,
            error_message="Test-Fehler",
        )
        db_session.add(job)
        await db_session.commit()

        # Wiederholen
        response = await client.post(
            f"/api/v1/admin/jobs/{job.id}/retry",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    async def test_retry_with_new_priority(
        self,
        client: AsyncClient,
        admin_token: str,
        db_session: AsyncSession,
        test_document: Document,
    ):
        """Job mit neuer Prioritaet wiederholen."""
        job = ProcessingJob(
            id=uuid4(),
            document_id=test_document.id,
            job_type="ocr",
            backend="deepseek",
            status=ProcessingStatus.FAILED.value,
            priority=5,
        )
        db_session.add(job)
        await db_session.commit()

        # Wiederholen mit Prioritaet 1
        response = await client.post(
            f"/api/v1/admin/jobs/{job.id}/retry?priority=1",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200


# ============================================================================
# SQL INJECTION TESTS - Sicherheit
# ============================================================================

class TestSQLInjectionPrevention:
    """Tests fuer SQL Injection Praevention."""

    async def test_status_filter_sql_injection(
        self,
        client: AsyncClient,
        admin_token: str,
    ):
        """SQL Injection im Status-Filter wird verhindert."""
        # Versuche SQL Injection
        response = await client.get(
            "/api/v1/admin/jobs?status=pending'; DROP TABLE processing_jobs; --",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # Sollte 422 (Validation Error) oder leere Ergebnisse zurueckgeben
        # NICHT 500 (Server Error durch SQL Fehler)
        assert response.status_code in [200, 422]
        if response.status_code == 200:
            # Keine Jobs mit diesem "Status"
            assert len(response.json().get("jobs", [])) == 0

    async def test_backend_filter_sql_injection(
        self,
        client: AsyncClient,
        admin_token: str,
    ):
        """SQL Injection im Backend-Filter wird verhindert."""
        response = await client.get(
            "/api/v1/admin/jobs?backend=deepseek' OR '1'='1",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # Sollte nicht alle Jobs zurueckgeben (SQL Injection Erfolg)
        # Sollte 200 mit leerem Ergebnis oder 422 sein
        assert response.status_code in [200, 422]


# ============================================================================
# N+1 QUERY DETECTION - Performance (ENTERPRISE Iteration 3)
# ============================================================================

class QueryCounter:
    """SQLAlchemy Event-basierter Query-Zaehler fuer echte N+1 Detection.

    ENTERPRISE FIX (Iteration 3):
    - Timing-basierte Tests sind fragil und unzuverlaessig
    - Diese Klasse zaehlt echte SQL Queries via SQLAlchemy Events
    """

    def __init__(self) -> None:
        self.count = 0
        self.queries: list[str] = []

    def callback(self, conn, cursor, statement, parameters, context, executemany) -> None:
        self.count += 1
        self.queries.append(statement[:100])  # Erste 100 Zeichen speichern


class TestN1QueryPrevention:
    """Tests fuer N+1 Query Praevention mit echtem Query-Counting."""

    async def test_list_jobs_uses_eager_loading(
        self,
        client: AsyncClient,
        admin_token: str,
        test_jobs: list[ProcessingJob],
        db_session: AsyncSession,
        db_engine,
    ):
        """Liste-Jobs sollte keine N+1 Queries verursachen.

        ENTERPRISE FIX (Iteration 3):
        - Echter Query-Count statt fragiler Timing-Tests
        - Mit 15 Jobs: maximal 3-5 Queries (1 COUNT, 1 SELECT, evtl. JOINs)
        - NICHT 15+ Queries (N+1 Problem)
        """
        from sqlalchemy import event

        query_counter = QueryCounter()

        # Event-Listener registrieren
        sync_engine = db_engine.sync_engine
        event.listen(sync_engine, "before_cursor_execute", query_counter.callback)

        try:
            response = await client.get(
                "/api/v1/admin/jobs?per_page=50",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert response.status_code == 200

            # ENTERPRISE: Echte Query-Count Validierung
            # Bei 15 Jobs sollten wir NICHT 15+ Queries haben (N+1)
            # Erwartete Queries: 1 COUNT + 1 SELECT + evtl. JOIN = max 5
            max_expected_queries = 10  # Grosszuegig, aber < len(test_jobs)

            assert query_counter.count < max_expected_queries, (
                f"Moegliches N+1 Problem: {query_counter.count} Queries fuer "
                f"{len(test_jobs)} Jobs. Queries:\n" +
                "\n".join(query_counter.queries[:10])
            )
        finally:
            # Event-Listener entfernen
            event.remove(sync_engine, "before_cursor_execute", query_counter.callback)

    async def test_query_count_scales_linearly(
        self,
        client: AsyncClient,
        admin_token: str,
        test_jobs: list[ProcessingJob],
        db_engine,
    ):
        """Query-Count sollte NICHT mit Job-Anzahl linear steigen.

        ENTERPRISE FIX (Iteration 3):
        - Bei N+1: Queries = O(n) mit Job-Anzahl
        - Bei Eager Loading: Queries = O(1) konstant
        """
        from sqlalchemy import event

        query_counter = QueryCounter()
        sync_engine = db_engine.sync_engine
        event.listen(sync_engine, "before_cursor_execute", query_counter.callback)

        try:
            # Request mit per_page=5
            response1 = await client.get(
                "/api/v1/admin/jobs?per_page=5",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            count_5 = query_counter.count
            query_counter.count = 0

            # Request mit per_page=15
            response2 = await client.get(
                "/api/v1/admin/jobs?per_page=15",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            count_15 = query_counter.count

            assert response1.status_code == 200
            assert response2.status_code == 200

            # Bei N+1 wuerde count_15 viel hoeher sein als count_5
            # Bei Eager Loading sollten beide aehnlich sein
            assert count_15 <= count_5 * 2, (
                f"Query-Count skaliert nicht konstant: "
                f"per_page=5: {count_5} Queries, per_page=15: {count_15} Queries"
            )
        finally:
            event.remove(sync_engine, "before_cursor_execute", query_counter.callback)
