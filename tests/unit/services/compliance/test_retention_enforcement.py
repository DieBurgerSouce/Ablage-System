"""Unit Tests fuer RetentionEnforcementService.

Tests fuer:
- can_delete_document: Loeschpruefung mit aktiver/abgelaufener Frist
- resolve_gdpr_retention_conflict: GDPR vs. Retention Konflikt-Aufloesung
- enforce_retention_on_delete: Durchsetzung beim Loeschversuch
- schedule_post_retention_review: Post-Retention Review Planung
- get_compliance_dashboard: Dashboard-Daten
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import AsyncGenerator

import pytest

# Diese Integrationstests fahren ein In-Memory-SQLite ueber sqlite+aiosqlite
# hoch (create_all gegen das ORM). Ist der aiosqlite-Treiber in der Umgebung
# nicht installiert (Projekt nutzt produktiv Postgres/asyncpg), koennen die
# Tests nicht laufen -> sauberer Skip mit praezisem Grund (Infra/Dependency,
# kein Test-Drift).
pytest.importorskip(
    "aiosqlite",
    reason="aiosqlite-Treiber nicht installiert (SQLite-Integrationstest, "
    "kein Test-Drift)",
)

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, Document, DocumentArchive, Company, User, RetentionCategory, HashAlgorithm
from app.services.compliance.retention_enforcement_service import (
    retention_enforcement_service,
    EnforcementStatus,
    ConflictResolutionAction,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create test database session."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def test_company(db_session: AsyncSession) -> Company:
    """Create test company."""
    company = Company(
        id=uuid.uuid4(),
        name="Test GmbH",
        short_name="TEST",
        is_active=True,
    )
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)
    return company


@pytest.fixture
async def test_user(db_session: AsyncSession, test_company: Company) -> User:
    """Create test user."""
    user = User(
        id=uuid.uuid4(),
        username="testuser",
        email="test@example.com",
        hashed_password="hashed",
        company_id=test_company.id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_document(
    db_session: AsyncSession,
    test_company: Company,
    test_user: User
) -> Document:
    """Create test document."""
    document = Document(
        id=uuid.uuid4(),
        filename="test.pdf",
        original_filename="test.pdf",
        mime_type="application/pdf",
        file_size=1024,
        company_id=test_company.id,
        uploaded_by_id=test_user.id,
        is_archived=False,
    )
    db_session.add(document)
    await db_session.commit()
    await db_session.refresh(document)
    return document


@pytest.fixture
async def active_archive(
    db_session: AsyncSession,
    test_document: Document,
    test_company: Company,
    test_user: User
) -> DocumentArchive:
    """Create archive with active retention period."""
    # Frist laeuft in 365 Tagen ab (1 Jahr)
    retention_expires = date.today() + timedelta(days=365)

    archive = DocumentArchive(
        id=uuid.uuid4(),
        document_id=test_document.id,
        company_id=test_company.id,
        content_hash="a" * 64,
        hash_algorithm=HashAlgorithm.SHA256.value,
        signature_timestamp=datetime.now(),
        retention_category=RetentionCategory.INVOICE.value,
        retention_years=10,
        retention_expires_at=retention_expires,
        archived_by_id=test_user.id,
        is_verified=True,
    )
    db_session.add(archive)

    # Dokument als archiviert markieren
    test_document.is_archived = True
    test_document.archived_at = datetime.now()

    await db_session.commit()
    await db_session.refresh(archive)
    return archive


@pytest.fixture
async def expired_archive(
    db_session: AsyncSession,
    test_company: Company,
    test_user: User
) -> DocumentArchive:
    """Create archive with expired retention period."""
    # Erstelle neues Dokument fuer diesen Test
    document = Document(
        id=uuid.uuid4(),
        filename="expired.pdf",
        original_filename="expired.pdf",
        mime_type="application/pdf",
        file_size=1024,
        company_id=test_company.id,
        uploaded_by_id=test_user.id,
        is_archived=True,
        archived_at=datetime.now() - timedelta(days=365),
    )
    db_session.add(document)

    # Frist ist bereits abgelaufen
    retention_expires = date.today() - timedelta(days=30)

    archive = DocumentArchive(
        id=uuid.uuid4(),
        document_id=document.id,
        company_id=test_company.id,
        content_hash="b" * 64,
        hash_algorithm=HashAlgorithm.SHA256.value,
        signature_timestamp=datetime.now() - timedelta(days=365),
        retention_category=RetentionCategory.INVOICE.value,
        retention_years=10,
        retention_expires_at=retention_expires,
        archived_by_id=test_user.id,
        is_verified=True,
    )
    db_session.add(archive)

    await db_session.commit()
    await db_session.refresh(archive)
    return archive


# =============================================================================
# Tests: can_delete_document
# =============================================================================


@pytest.mark.asyncio
async def test_can_delete_non_archived_document(
    db_session: AsyncSession,
    test_document: Document
):
    """Nicht-archivierte Dokumente koennen geloescht werden."""
    result = await retention_enforcement_service.can_delete_document(
        db_session,
        test_document.id
    )

    assert result.can_delete is True
    assert "nicht archiviert" in result.reason
    assert result.enforcement_status == EnforcementStatus.EXPIRED


@pytest.mark.asyncio
async def test_cannot_delete_document_with_active_retention(
    db_session: AsyncSession,
    test_document: Document,
    active_archive: DocumentArchive
):
    """Dokumente mit aktiver Aufbewahrungsfrist duerfen nicht geloescht werden."""
    result = await retention_enforcement_service.can_delete_document(
        db_session,
        test_document.id
    )

    assert result.can_delete is False
    assert "Aufbewahrungsfrist aktiv" in result.reason
    assert result.enforcement_status == EnforcementStatus.ACTIVE
    assert result.days_remaining > 0
    assert result.legal_basis is not None
    assert "§147 AO" in result.legal_basis or "§14b UStG" in result.legal_basis


@pytest.mark.asyncio
async def test_can_delete_document_with_expired_retention(
    db_session: AsyncSession,
    expired_archive: DocumentArchive
):
    """Dokumente mit abgelaufener Aufbewahrungsfrist koennen geloescht werden."""
    result = await retention_enforcement_service.can_delete_document(
        db_session,
        expired_archive.document_id
    )

    assert result.can_delete is True
    assert "abgelaufen" in result.reason
    assert result.enforcement_status == EnforcementStatus.EXPIRED
    assert result.days_remaining < 0


@pytest.mark.asyncio
async def test_can_delete_nonexistent_document(db_session: AsyncSession):
    """Nicht-existierende Dokumente geben False zurueck."""
    fake_id = uuid.uuid4()
    result = await retention_enforcement_service.can_delete_document(
        db_session,
        fake_id
    )

    assert result.can_delete is False
    assert "nicht gefunden" in result.reason


# =============================================================================
# Tests: resolve_gdpr_retention_conflict
# =============================================================================


@pytest.mark.asyncio
async def test_gdpr_conflict_with_active_retention(
    db_session: AsyncSession,
    test_document: Document,
    active_archive: DocumentArchive
):
    """GDPR-Loeschung bei aktiver Frist: Retention hat Vorrang."""
    resolution = await retention_enforcement_service.resolve_gdpr_retention_conflict(
        db_session,
        test_document.id
    )

    assert resolution.action == ConflictResolutionAction.RETENTION_WINS
    assert "Aufbewahrungspflicht hat Vorrang" in resolution.reason
    assert resolution.can_anonymize is True
    assert resolution.scheduled_deletion_at is not None
    assert resolution.requires_admin_approval is False
    assert "§17 Abs. 3 lit. b DSGVO" in resolution.legal_justification


@pytest.mark.asyncio
async def test_gdpr_no_conflict_with_expired_retention(
    db_session: AsyncSession,
    expired_archive: DocumentArchive
):
    """GDPR-Loeschung bei abgelaufener Frist: Kein Konflikt."""
    resolution = await retention_enforcement_service.resolve_gdpr_retention_conflict(
        db_session,
        expired_archive.document_id
    )

    assert resolution.action == ConflictResolutionAction.RETENTION_WINS
    assert "abgelaufen" in resolution.reason
    assert resolution.can_anonymize is False
    assert "§17 DSGVO" in resolution.legal_justification


# =============================================================================
# Tests: enforce_retention_on_delete
# =============================================================================


@pytest.mark.asyncio
async def test_enforce_blocks_deletion_with_active_retention(
    db_session: AsyncSession,
    test_document: Document,
    active_archive: DocumentArchive,
    test_user: User
):
    """Durchsetzung blockiert Loeschung bei aktiver Frist."""
    with pytest.raises(ValueError, match="Loeschung nicht erlaubt"):
        await retention_enforcement_service.enforce_retention_on_delete(
            db_session,
            test_document.id,
            test_user.id
        )


@pytest.mark.asyncio
async def test_enforce_allows_deletion_with_expired_retention(
    db_session: AsyncSession,
    expired_archive: DocumentArchive,
    test_user: User
):
    """Durchsetzung erlaubt Loeschung bei abgelaufener Frist."""
    result = await retention_enforcement_service.enforce_retention_on_delete(
        db_session,
        expired_archive.document_id,
        test_user.id
    )

    assert result.success is True
    assert result.action_taken == "deletion_allowed"
    assert result.document_id == expired_archive.document_id


# =============================================================================
# Tests: get_compliance_dashboard
# =============================================================================


@pytest.mark.asyncio
async def test_compliance_dashboard_stats(
    db_session: AsyncSession,
    test_company: Company,
    active_archive: DocumentArchive,
    expired_archive: DocumentArchive
):
    """Dashboard liefert korrekte Statistiken."""
    dashboard = await retention_enforcement_service.get_compliance_dashboard(
        db_session,
        test_company.id
    )

    assert dashboard.total_archives == 2
    assert dashboard.active_retention >= 1
    assert dashboard.expired_retention >= 1
    assert isinstance(dashboard.by_category, dict)
    assert RetentionCategory.INVOICE.value in dashboard.by_category
    assert dashboard.last_updated is not None


@pytest.mark.asyncio
async def test_compliance_dashboard_empty_company(
    db_session: AsyncSession,
    test_company: Company
):
    """Dashboard fuer Company ohne Archive."""
    # Erstelle neue Company ohne Archive
    empty_company = Company(
        id=uuid.uuid4(),
        name="Empty GmbH",
        short_name="EMPTY",
        is_active=True,
    )
    db_session.add(empty_company)
    await db_session.commit()

    dashboard = await retention_enforcement_service.get_compliance_dashboard(
        db_session,
        empty_company.id
    )

    assert dashboard.total_archives == 0
    assert dashboard.active_retention == 0
    assert dashboard.expired_retention == 0


# =============================================================================
# Tests: schedule_post_retention_review
# =============================================================================


@pytest.mark.asyncio
async def test_schedule_post_retention_review(
    db_session: AsyncSession,
    active_archive: DocumentArchive
):
    """Post-Retention Review kann geplant werden."""
    # Sollte keine Exception werfen
    await retention_enforcement_service.schedule_post_retention_review(
        db_session,
        active_archive.id
    )

    # Nach Migration 205 wuerde hier geprueft:
    # await db_session.refresh(active_archive)
    # assert active_archive.post_retention_review_scheduled is True
    # assert active_archive.post_retention_review_at is not None


@pytest.mark.asyncio
async def test_schedule_review_for_nonexistent_archive(db_session: AsyncSession):
    """Fehler bei nicht-existierendem Archiv."""
    fake_id = uuid.uuid4()

    with pytest.raises(ValueError, match="nicht gefunden"):
        await retention_enforcement_service.schedule_post_retention_review(
            db_session,
            fake_id
        )


# =============================================================================
# Integration Tests
# =============================================================================


@pytest.mark.asyncio
async def test_full_retention_lifecycle(
    db_session: AsyncSession,
    test_company: Company,
    test_user: User
):
    """Test des kompletten Retention-Lifecycle."""
    # 1. Dokument erstellen
    document = Document(
        id=uuid.uuid4(),
        filename="lifecycle.pdf",
        original_filename="lifecycle.pdf",
        mime_type="application/pdf",
        file_size=2048,
        company_id=test_company.id,
        uploaded_by_id=test_user.id,
        is_archived=False,
    )
    db_session.add(document)
    await db_session.commit()

    # 2. Dokument kann geloescht werden (noch nicht archiviert)
    result = await retention_enforcement_service.can_delete_document(
        db_session,
        document.id
    )
    assert result.can_delete is True

    # 3. Dokument archivieren mit aktiver Frist
    archive = DocumentArchive(
        id=uuid.uuid4(),
        document_id=document.id,
        company_id=test_company.id,
        content_hash="c" * 64,
        hash_algorithm=HashAlgorithm.SHA256.value,
        signature_timestamp=datetime.now(),
        retention_category=RetentionCategory.CONTRACT.value,
        retention_years=10,
        retention_expires_at=date.today() + timedelta(days=3650),
        archived_by_id=test_user.id,
        is_verified=True,
    )
    db_session.add(archive)
    document.is_archived = True
    await db_session.commit()

    # 4. Dokument kann NICHT geloescht werden (aktive Frist)
    result = await retention_enforcement_service.can_delete_document(
        db_session,
        document.id
    )
    assert result.can_delete is False

    # 5. GDPR-Konflikt: Retention gewinnt
    resolution = await retention_enforcement_service.resolve_gdpr_retention_conflict(
        db_session,
        document.id
    )
    assert resolution.action == ConflictResolutionAction.RETENTION_WINS
    assert resolution.can_anonymize is True

    # 6. Loeschversuch wird blockiert
    with pytest.raises(ValueError):
        await retention_enforcement_service.enforce_retention_on_delete(
            db_session,
            document.id,
            test_user.id
        )

    # 7. Dashboard zeigt aktive Retention
    dashboard = await retention_enforcement_service.get_compliance_dashboard(
        db_session,
        test_company.id
    )
    assert dashboard.active_retention >= 1
