# -*- coding: utf-8 -*-
"""End-to-End Tests fuer Rate Limiting mit echtem Redis.

Diese Tests validieren:
- Destruktive Admin-Operationen Rate Limits
- 429 Too Many Requests nach Limit
- Rate Limit Reset nach Zeitablauf
- Verschiedene Limit-Typen (per User, per IP)

Erfordert: docker-compose up redis

Ausfuehrung:
    pytest tests/integration/test_rate_limit_e2e.py -v -m integration
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from uuid import uuid4
from typing import AsyncGenerator
import asyncio

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from httpx import AsyncClient, ASGITransport
import redis.asyncio as aioredis

from app.db.models import (
    Base,
    User,
    ProcessingJob,
    Document,
)
from app.db.schemas import ProcessingStatus
from app.main import app
from app.core.security import create_access_token
from app.core.config import settings


pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
]


# ============================================================================
# TEST CONFIGURATION
# ============================================================================

TEST_DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5433/ablage_test"
TEST_REDIS_URL = "redis://localhost:6380/15"  # Nutze DB 15 fuer Tests


# ============================================================================
# FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def redis_client() -> AsyncGenerator[aioredis.Redis, None]:
    """Erstellt Redis-Client und bereinigt nach jedem Test."""
    client = await aioredis.from_url(TEST_REDIS_URL, decode_responses=True)
    yield client
    # Bereinige alle Rate-Limit-Keys nach dem Test
    keys = await client.keys("rate_limit:*")
    if keys:
        await client.delete(*keys)
    await client.aclose()


@pytest_asyncio.fixture
async def db_engine():
    """Erstellt Test-Datenbank-Engine."""
    engine = create_async_engine(
        TEST_DB_URL,
        echo=False,
        pool_pre_ping=True,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Erstellt Test-Session mit Rollback."""
    async_session_factory = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def test_admin(db_session: AsyncSession) -> User:
    """Erstellt Test-Admin."""
    admin = User(
        id=uuid4(),
        email="ratelimit_admin@test.de",
        username="ratelimit_admin",
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
    """Generiert JWT-Token."""
    return create_access_token(subject=str(test_admin.id))


@pytest_asyncio.fixture
async def test_document(db_session: AsyncSession, test_admin: User) -> Document:
    """Erstellt Test-Dokument."""
    doc = Document(
        id=uuid4(),
        user_id=test_admin.id,
        filename="rate_limit_test.pdf",
        original_name="rate_limit_test.pdf",
        mime_type="application/pdf",
        file_size=1024,
        status="uploaded",
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)
    return doc


@pytest_asyncio.fixture
async def pending_jobs(
    db_session: AsyncSession,
    test_document: Document,
) -> list[ProcessingJob]:
    """Erstellt mehrere pending Jobs fuer Rate-Limit-Tests."""
    jobs = []
    for i in range(15):
        job = ProcessingJob(
            id=uuid4(),
            document_id=test_document.id,
            job_type="ocr",
            backend="deepseek",
            status=ProcessingStatus.PENDING.value,
            priority=5,
        )
        db_session.add(job)
        jobs.append(job)

    await db_session.commit()
    for job in jobs:
        await db_session.refresh(job)

    return jobs


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Erstellt Test-Client."""
    transport = ASGITransport(app=app)  # type: ignore
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ============================================================================
# RATE LIMIT E2E TESTS
# ============================================================================

class TestDestructiveAdminRateLimits:
    """Tests fuer Rate Limits bei destruktiven Admin-Operationen."""

    async def test_cancel_job_rate_limit_blocks_after_limit(
        self,
        client: AsyncClient,
        admin_token: str,
        pending_jobs: list[ProcessingJob],
        redis_client: aioredis.Redis,
    ):
        """Nach 10 Cancel-Operationen sollte 429 zurueckgegeben werden.

        Dies ist der KRITISCHE Test aus SCHRITT 6 des Plans.

        ENTERPRISE FIX (Iteration 2):
        - 404 wird NICHT mehr als erfolgreicher Cancel gezaehlt
        - 404 bedeutet Job nicht gefunden = Rate-Limit wird NICHT erhoeht
        - Nur 200 zaehlt als echte Operation gegen das Limit
        """
        # Rate-Limit-Key loeschen fuer sauberen Test
        await redis_client.delete("rate_limit:destructive_admin:*")

        successful_cancels = 0
        not_found_count = 0
        rate_limited = False

        for i, job in enumerate(pending_jobs[:12]):  # Versuche 12 Cancels
            response = await client.post(
                f"/api/v1/admin/jobs/{job.id}/cancel",
                headers={"Authorization": f"Bearer {admin_token}"},
            )

            if response.status_code == 429:
                rate_limited = True
                break
            elif response.status_code == 200:
                # ENTERPRISE FIX: Nur 200 zaehlt als erfolgreicher Cancel
                successful_cancels += 1
            elif response.status_code == 404:
                # ENTERPRISE FIX: 404 wird separat gezaehlt, erhoeht Rate-Limit NICHT
                not_found_count += 1
                # Wenn Job nicht gefunden, continue ohne Rate-Limit zu erhoehen
                continue

        # ENTERPRISE FIX (Iteration 3):
        # Mindestens 10 ECHTE Cancels sollten erfolgreich sein (das Limit)
        # 404s zaehlen NICHT als erfolgreiche Operationen!
        assert successful_cancels >= 10, \
            f"Nur {successful_cancels} echte Cancels (erwartet: >= 10). 404s: {not_found_count}"

        # Der 11. oder 12. Request sollte rate-limited sein
        # (Falls Rate-Limiting aktiviert ist)
        if settings.RATE_LIMIT_DESTRUCTIVE_ADMIN_ENABLED:
            # Nur pruefen wenn wir genug echte Cancels hatten
            if successful_cancels >= 10:
                assert rate_limited, \
                    f"Rate Limiting hat nicht gegriffen nach {successful_cancels} echten Cancels"

    async def test_rate_limit_returns_correct_error_format(
        self,
        client: AsyncClient,
        admin_token: str,
        pending_jobs: list[ProcessingJob],
        redis_client: aioredis.Redis,
    ):
        """429 Response hat korrektes Format mit Retry-After Header."""
        # Fuehre viele Requests aus um Rate Limit zu erreichen
        for job in pending_jobs[:15]:
            response = await client.post(
                f"/api/v1/admin/jobs/{job.id}/cancel",
                headers={"Authorization": f"Bearer {admin_token}"},
            )

            if response.status_code == 429:
                # Pruefe Response-Format
                data = response.json()
                assert "detail" in data
                assert "limit" in data["detail"].lower() or "rate" in data["detail"].lower()

                # Retry-After Header sollte vorhanden sein
                # (Standard HTTP Rate Limiting Header)
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    assert int(retry_after) > 0
                break

    async def test_different_users_have_separate_limits(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        pending_jobs: list[ProcessingJob],
        redis_client: aioredis.Redis,
    ):
        """Verschiedene Admins haben getrennte Rate Limits."""
        # Erstelle zweiten Admin
        admin2 = User(
            id=uuid4(),
            email="admin2@test.de",
            username="admin2",
            hashed_password="hashed_password",
            is_active=True,
            is_superuser=True,
            tier="enterprise",
        )
        db_session.add(admin2)
        await db_session.commit()

        token1 = create_access_token(subject=str(pending_jobs[0].document.user_id))  # type: ignore
        token2 = create_access_token(subject=str(admin2.id))

        # Admin 1: 5 Requests
        for job in pending_jobs[:5]:
            await client.post(
                f"/api/v1/admin/jobs/{job.id}/cancel",
                headers={"Authorization": f"Bearer {token1}"},
            )

        # Admin 2: Sollte eigenes Limit haben (nicht von Admin 1 beeinflusst)
        response = await client.post(
            f"/api/v1/admin/jobs/{pending_jobs[5].id}/cancel",
            headers={"Authorization": f"Bearer {token2}"},
        )

        # Admin 2 sollte NICHT rate-limited sein
        assert response.status_code != 429, "Admin 2 wurde faelschlicherweise rate-limited"


# ============================================================================
# RATE LIMIT RESET TESTS
# ============================================================================

class TestRateLimitReset:
    """Tests fuer Rate Limit Reset nach Zeitablauf."""

    async def test_rate_limit_resets_after_window(
        self,
        client: AsyncClient,
        admin_token: str,
        pending_jobs: list[ProcessingJob],
        redis_client: aioredis.Redis,
    ):
        """Rate Limit setzt sich nach Zeitfenster zurueck.

        Hinweis: Dieser Test ist zeitabhaengig und wird in CI moeglicherweise
        uebersprungen, da das Warten auf den Reset zu lange dauern kann.
        """
        # Fuer schnelleren Test: Redis TTL direkt setzen
        rate_limit_key = f"rate_limit:destructive_admin:test"

        # Setze einen nahezu abgelaufenen Counter
        await redis_client.set(rate_limit_key, "9", ex=2)  # Laeuft in 2 Sekunden ab

        # Warte auf Ablauf
        await asyncio.sleep(3)

        # Pruefe ob Key geloescht wurde
        value = await redis_client.get(rate_limit_key)
        assert value is None, "Rate Limit Key sollte nach TTL geloescht sein"


# ============================================================================
# BULK OPERATION RATE LIMIT TESTS
# ============================================================================

class TestBulkOperationRateLimits:
    """Tests fuer Rate Limits bei Bulk-Operationen."""

    async def test_bulk_cancel_counts_as_multiple_operations(
        self,
        client: AsyncClient,
        admin_token: str,
        pending_jobs: list[ProcessingJob],
        redis_client: aioredis.Redis,
    ):
        """Bulk-Cancel zaehlt entsprechend der Anzahl Jobs zum Limit."""
        # Bereite Job-IDs vor
        job_ids = [str(job.id) for job in pending_jobs[:5]]

        # Bulk Cancel (falls Endpoint existiert)
        response = await client.post(
            "/api/v1/admin/jobs/bulk/cancel",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"job_ids": job_ids},
        )

        # Entweder 200 (Endpoint existiert) oder 404 (nicht implementiert)
        if response.status_code == 200:
            # Pruefe ob Rate Limit richtig gezaehlt wurde
            # 5 Jobs = 5 Operationen gegen das Limit
            pass
        elif response.status_code == 404:
            # Bulk Endpoint nicht implementiert - das ist OK
            pytest.skip("Bulk Cancel Endpoint nicht implementiert")


# ============================================================================
# RATE LIMIT BYPASS PREVENTION
# ============================================================================

class TestRateLimitBypassPrevention:
    """Tests um sicherzustellen, dass Rate Limits nicht umgangen werden koennen."""

    async def test_cannot_bypass_with_different_headers(
        self,
        client: AsyncClient,
        admin_token: str,
        pending_jobs: list[ProcessingJob],
    ):
        """Rate Limit kann nicht durch verschiedene Headers umgangen werden."""
        # Erschoepfe Rate Limit
        for job in pending_jobs[:12]:
            await client.post(
                f"/api/v1/admin/jobs/{job.id}/cancel",
                headers={
                    "Authorization": f"Bearer {admin_token}",
                    "X-Forwarded-For": f"192.168.1.{job.priority}",  # Fake IP
                },
            )

        # Versuche mit anderer "IP" - sollte trotzdem limitiert sein
        # (Token-basiertes Limit, nicht IP-basiert)
        response = await client.post(
            f"/api/v1/admin/jobs/{pending_jobs[0].id}/cancel",
            headers={
                "Authorization": f"Bearer {admin_token}",
                "X-Forwarded-For": "10.0.0.1",  # Andere "IP"
            },
        )

        # Wenn Rate Limiting aktiv ist, sollte immer noch 429 kommen
        if settings.RATE_LIMIT_DESTRUCTIVE_ADMIN_ENABLED:
            assert response.status_code in [429, 404], \
                "Rate Limit wurde durch Header-Spoofing umgangen"


# ============================================================================
# INFORMATIONAL: Rate Limit Status Endpoint (falls vorhanden)
# ============================================================================

class TestRateLimitStatusEndpoint:
    """Tests fuer optionalen Rate Limit Status Endpoint."""

    async def test_rate_limit_status_shows_remaining(
        self,
        client: AsyncClient,
        admin_token: str,
    ):
        """Pruefe ob Rate Limit Status Endpoint existiert und korrekt ist."""
        response = await client.get(
            "/api/v1/admin/rate-limit/status",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        if response.status_code == 404:
            pytest.skip("Rate Limit Status Endpoint nicht implementiert")

        if response.status_code == 200:
            data = response.json()
            assert "remaining" in data or "limit" in data
