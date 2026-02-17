# -*- coding: utf-8 -*-
"""Unit-Tests fuer Document Lifecycle Engine.

Testet die GoBD-konforme Dokumenten-Lebenszyklus-Verwaltung:
- Scan auf ablaufende Aufbewahrungsfristen
- Vernichtungsprotokoll-Generierung
- Lifecycle-Dashboard
- Fristverlaengerung
- Retention-Summary
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.document_lifecycle_engine import DocumentLifecycleEngine


# =============================================================================
# Fixtures
# =============================================================================


def _make_archive(
    doc_id: Optional[uuid.UUID] = None,
    company_id: Optional[uuid.UUID] = None,
    expires_at: Optional[date] = None,
    category: str = "invoice",
    years: int = 10,
    is_verified: bool = True,
    reminder_sent: bool = False,
) -> MagicMock:
    """Erstellt ein Mock-DocumentArchive-Objekt."""
    archive = MagicMock()
    archive.id = uuid.uuid4()
    archive.document_id = doc_id or uuid.uuid4()
    archive.company_id = company_id or uuid.uuid4()
    archive.retention_expires_at = expires_at or (date.today() + timedelta(days=15))
    archive.retention_category = category
    archive.retention_years = years
    archive.is_verified = is_verified
    archive.retention_reminder_sent = reminder_sent
    archive.retention_reminder_at = None
    archive.archived_at = datetime.now(timezone.utc) - timedelta(days=365 * years)
    archive.content_hash = "abc123def456" * 5
    archive.hash_algorithm = "SHA-256"

    # Mock document relationship
    doc = MagicMock()
    doc.id = archive.document_id
    doc.filename = "Rechnung_2020_001.pdf"
    doc.original_filename = "Rechnung_2020_001.pdf"
    doc.company_id = archive.company_id
    doc.is_archived = True
    archive.document = doc

    return archive


def _make_retention_setting(
    category: str = "invoice",
    display_name: str = "Rechnungen",
    years: int = 10,
    legal_basis: str = "§147 AO",
) -> MagicMock:
    """Erstellt ein Mock-RetentionSetting-Objekt."""
    setting = MagicMock()
    setting.category = category
    setting.display_name = display_name
    setting.retention_years = years
    setting.legal_basis = legal_basis
    return setting


# =============================================================================
# Tests: scan_expiring_documents
# =============================================================================


class TestScanExpiringDocuments:
    """Tests fuer DocumentLifecycleEngine.scan_expiring_documents."""

    @pytest.mark.asyncio
    async def test_scan_returns_expiring_archives(self) -> None:
        """Scannt nach Dokumenten mit ablaufender Frist."""
        engine = DocumentLifecycleEngine()
        db = AsyncMock()

        expires_soon = date.today() + timedelta(days=15)
        archive = _make_archive(expires_at=expires_soon)

        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [archive]
        result_mock.scalars.return_value = scalars_mock
        db.execute.return_value = result_mock

        results = await engine.scan_expiring_documents(db, days_ahead=30)

        assert len(results) == 1
        assert results[0].document_id == archive.document_id
        db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_scan_empty_when_no_expiring(self) -> None:
        """Gibt leere Liste zurueck wenn nichts ablaeuft."""
        engine = DocumentLifecycleEngine()
        db = AsyncMock()

        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock.scalars.return_value = scalars_mock
        db.execute.return_value = result_mock

        results = await engine.scan_expiring_documents(db, days_ahead=30)

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_scan_filters_by_company(self) -> None:
        """Filtert nach Firmen-ID wenn angegeben."""
        engine = DocumentLifecycleEngine()
        db = AsyncMock()
        company_id = uuid.uuid4()

        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock.scalars.return_value = scalars_mock
        db.execute.return_value = result_mock

        await engine.scan_expiring_documents(
            db, days_ahead=30, company_id=company_id
        )

        # Verify the execute was called (company_id filter is in the query)
        db.execute.assert_called_once()


# =============================================================================
# Tests: generate_destruction_protocol
# =============================================================================


class TestGenerateDestructionProtocol:
    """Tests fuer DocumentLifecycleEngine.generate_destruction_protocol."""

    @pytest.mark.asyncio
    async def test_protocol_for_expired_documents(self) -> None:
        """Erstellt Protokoll fuer abgelaufene Dokumente."""
        engine = DocumentLifecycleEngine()
        db = AsyncMock()
        user_id = uuid.uuid4()

        expired_date = date.today() - timedelta(days=30)
        doc_id = uuid.uuid4()
        archive = _make_archive(doc_id=doc_id, expires_at=expired_date)

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = archive
        db.execute.return_value = result_mock
        db.add = MagicMock()
        db.commit = AsyncMock()

        protocol = await engine.generate_destruction_protocol(
            db, document_ids=[doc_id], user_id=user_id
        )

        assert protocol["total_documents"] == 1
        assert protocol["approved_for_destruction"] == 1
        assert protocol["rejected"] == 0
        assert len(protocol["items"]) == 1
        assert protocol["items"][0]["document_id"] == str(doc_id)

    @pytest.mark.asyncio
    async def test_protocol_rejects_not_expired(self) -> None:
        """Lehnt Dokumente mit aktiver Frist ab."""
        engine = DocumentLifecycleEngine()
        db = AsyncMock()
        user_id = uuid.uuid4()

        future_date = date.today() + timedelta(days=365)
        doc_id = uuid.uuid4()
        archive = _make_archive(doc_id=doc_id, expires_at=future_date)

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = archive
        db.execute.return_value = result_mock
        db.add = MagicMock()
        db.commit = AsyncMock()

        protocol = await engine.generate_destruction_protocol(
            db, document_ids=[doc_id], user_id=user_id
        )

        assert protocol["approved_for_destruction"] == 0
        assert protocol["rejected"] == 1
        assert len(protocol["errors"]) == 1

    @pytest.mark.asyncio
    async def test_protocol_rejects_missing_archive(self) -> None:
        """Fehler wenn kein Archiv-Eintrag existiert."""
        engine = DocumentLifecycleEngine()
        db = AsyncMock()
        user_id = uuid.uuid4()
        doc_id = uuid.uuid4()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute.return_value = result_mock
        db.add = MagicMock()
        db.commit = AsyncMock()

        protocol = await engine.generate_destruction_protocol(
            db, document_ids=[doc_id], user_id=user_id
        )

        assert protocol["approved_for_destruction"] == 0
        assert protocol["rejected"] == 1
        assert "Kein Archiv-Eintrag" in protocol["errors"][0]["error"]

    @pytest.mark.asyncio
    async def test_protocol_includes_legal_basis(self) -> None:
        """Protokoll enthaelt gesetzliche Grundlage."""
        engine = DocumentLifecycleEngine()
        db = AsyncMock()
        user_id = uuid.uuid4()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute.return_value = result_mock
        db.add = MagicMock()
        db.commit = AsyncMock()

        protocol = await engine.generate_destruction_protocol(
            db, document_ids=[uuid.uuid4()], user_id=user_id
        )

        assert "§147 AO" in protocol["legal_basis"]
        assert "§257 HGB" in protocol["legal_basis"]


# =============================================================================
# Tests: get_lifecycle_dashboard
# =============================================================================


class TestGetLifecycleDashboard:
    """Tests fuer DocumentLifecycleEngine.get_lifecycle_dashboard."""

    @pytest.mark.asyncio
    async def test_dashboard_returns_counts(self) -> None:
        """Dashboard gibt korrekte Zaehler zurueck."""
        engine = DocumentLifecycleEngine()
        db = AsyncMock()
        company_id = uuid.uuid4()

        # Mock fuer 6 separate Queries (active, archived, exp30, exp90, expired, unverified) + category
        call_count = 0

        def mock_execute_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count <= 6:
                # Count queries
                result.scalar.return_value = call_count * 10
            else:
                # Category query
                result.all.return_value = [("invoice", 30), ("contract", 20)]
            return result

        db.execute = AsyncMock(side_effect=mock_execute_side_effect)

        dashboard = await engine.get_lifecycle_dashboard(db, company_id)

        assert "counts" in dashboard
        assert "by_category" in dashboard
        assert dashboard["company_id"] == str(company_id)

    @pytest.mark.asyncio
    async def test_dashboard_includes_generated_at(self) -> None:
        """Dashboard enthaelt Generierungszeitpunkt."""
        engine = DocumentLifecycleEngine()
        db = AsyncMock()
        company_id = uuid.uuid4()

        result_mock = MagicMock()
        result_mock.scalar.return_value = 0
        result_mock.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        dashboard = await engine.get_lifecycle_dashboard(db, company_id)

        assert "generated_at" in dashboard


# =============================================================================
# Tests: extend_retention
# =============================================================================


class TestExtendRetention:
    """Tests fuer DocumentLifecycleEngine.extend_retention."""

    @pytest.mark.asyncio
    async def test_extend_updates_expiry(self) -> None:
        """Verlaengerung aktualisiert Ablaufdatum korrekt."""
        engine = DocumentLifecycleEngine()
        db = AsyncMock()
        doc_id = uuid.uuid4()
        user_id = uuid.uuid4()

        # Altes Ablaufdatum in der Zukunft (naechstes Jahr)
        old_expires = date.today() + timedelta(days=30)
        archive = _make_archive(doc_id=doc_id, expires_at=old_expires, years=10)
        # Make archive attributes writable
        archive.retention_years = 10
        archive.retention_expires_at = old_expires
        archive.retention_reminder_sent = False
        archive.retention_reminder_at = None

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = archive
        db.execute = AsyncMock(return_value=result_mock)
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        new_years = 15
        result = await engine.extend_retention(
            db,
            document_id=doc_id,
            new_years=new_years,
            reason="Betriebspruefung",
            user_id=user_id,
        )

        assert result.retention_years == new_years
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_extend_raises_for_missing_archive(self) -> None:
        """Fehler wenn kein Archiv-Eintrag existiert."""
        from app.core.exceptions import ArchiveError

        engine = DocumentLifecycleEngine()
        db = AsyncMock()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(ArchiveError, match="Kein Archiv-Eintrag"):
            await engine.extend_retention(
                db,
                document_id=uuid.uuid4(),
                new_years=15,
                reason="Test",
                user_id=uuid.uuid4(),
            )

    @pytest.mark.asyncio
    async def test_extend_raises_for_shorter_period(self) -> None:
        """Fehler wenn neue Frist kuerzer als aktuelle."""
        from app.core.exceptions import ArchiveError

        engine = DocumentLifecycleEngine()
        db = AsyncMock()
        doc_id = uuid.uuid4()

        # Frist laeuft in 20 Jahren ab
        far_future = date.today() + timedelta(days=365 * 20)
        archive = _make_archive(doc_id=doc_id, expires_at=far_future, years=20)

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = archive
        db.execute = AsyncMock(return_value=result_mock)

        # 5 Jahre waere kuerzer als 20 Jahre in der Zukunft
        with pytest.raises(ArchiveError, match="Neue Frist"):
            await engine.extend_retention(
                db,
                document_id=doc_id,
                new_years=5,
                reason="Test",
                user_id=uuid.uuid4(),
            )


# =============================================================================
# Tests: auto_archive_expired
# =============================================================================


class TestAutoArchiveExpired:
    """Tests fuer DocumentLifecycleEngine.auto_archive_expired."""

    @pytest.mark.asyncio
    async def test_auto_archive_returns_stats(self) -> None:
        """Auto-Archivierung gibt Statistiken zurueck."""
        engine = DocumentLifecycleEngine()
        db = AsyncMock()

        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)
        db.commit = AsyncMock()

        stats = await engine.auto_archive_expired(db)

        assert "total" in stats
        assert "verified" in stats
        assert "verification_failed" in stats
        assert stats["total"] == 0


# =============================================================================
# Tests: get_retention_summary
# =============================================================================


class TestGetRetentionSummary:
    """Tests fuer DocumentLifecycleEngine.get_retention_summary."""

    @pytest.mark.asyncio
    async def test_summary_includes_categories(self) -> None:
        """Zusammenfassung enthaelt Kategorien."""
        engine = DocumentLifecycleEngine()
        db = AsyncMock()

        # First call: category stats
        cat_result = MagicMock()
        cat_result.all.return_value = []

        # Second call: retention settings
        settings_result = MagicMock()
        settings_scalars = MagicMock()
        settings_scalars.all.return_value = []
        settings_result.scalars.return_value = settings_scalars

        db.execute = AsyncMock(side_effect=[cat_result, settings_result])

        summary = await engine.get_retention_summary(db)

        assert "categories" in summary
        assert "retention_settings" in summary
        assert "generated_at" in summary

    @pytest.mark.asyncio
    async def test_summary_filters_by_company(self) -> None:
        """Zusammenfassung filtert nach Firma."""
        engine = DocumentLifecycleEngine()
        db = AsyncMock()
        company_id = uuid.uuid4()

        cat_result = MagicMock()
        cat_result.all.return_value = []
        settings_result = MagicMock()
        settings_scalars = MagicMock()
        settings_scalars.all.return_value = []
        settings_result.scalars.return_value = settings_scalars

        db.execute = AsyncMock(side_effect=[cat_result, settings_result])

        summary = await engine.get_retention_summary(db, company_id=company_id)

        assert summary["company_id"] == str(company_id)


# =============================================================================
# Tests: Pydantic Schemas
# =============================================================================


class TestLifecycleSchemas:
    """Tests fuer Lifecycle Pydantic-Schemas."""

    def test_retention_extension_request_validation(self) -> None:
        """Validiert RetentionExtensionRequest."""
        from app.api.schemas.lifecycle import RetentionExtensionRequest

        req = RetentionExtensionRequest(
            new_years=15,
            reason="Laufende Betriebspruefung durch das Finanzamt",
        )
        assert req.new_years == 15
        assert "Betriebspruefung" in req.reason

    def test_retention_extension_request_rejects_zero_years(self) -> None:
        """Lehnt 0 Jahre ab."""
        from pydantic import ValidationError
        from app.api.schemas.lifecycle import RetentionExtensionRequest

        with pytest.raises(ValidationError):
            RetentionExtensionRequest(new_years=0, reason="Test-Grund")

    def test_retention_extension_request_rejects_short_reason(self) -> None:
        """Lehnt zu kurze Begruendung ab."""
        from pydantic import ValidationError
        from app.api.schemas.lifecycle import RetentionExtensionRequest

        with pytest.raises(ValidationError):
            RetentionExtensionRequest(new_years=10, reason="abc")

    def test_destruction_protocol_request_validation(self) -> None:
        """Validiert DestructionProtocolRequest."""
        from app.api.schemas.lifecycle import DestructionProtocolRequest

        req = DestructionProtocolRequest(
            document_ids=[uuid.uuid4(), uuid.uuid4()],
            reason="Aufbewahrungsfrist abgelaufen gemaess §147 AO",
        )
        assert len(req.document_ids) == 2

    def test_destruction_protocol_request_rejects_empty_list(self) -> None:
        """Lehnt leere Dokument-Liste ab."""
        from pydantic import ValidationError
        from app.api.schemas.lifecycle import DestructionProtocolRequest

        with pytest.raises(ValidationError):
            DestructionProtocolRequest(
                document_ids=[],
                reason="Test-Grund fuer Vernichtung",
            )

    def test_dashboard_counts_schema(self) -> None:
        """Validiert LifecycleDashboardCounts."""
        from app.api.schemas.lifecycle import LifecycleDashboardCounts

        counts = LifecycleDashboardCounts(
            active=100,
            archived=50,
            expiring_30_days=5,
            expiring_90_days=15,
            expired=2,
            verification_failed=0,
        )
        assert counts.active == 100
        assert counts.expired == 2

    def test_expiring_document_response(self) -> None:
        """Validiert ExpiringDocumentResponse."""
        from app.api.schemas.lifecycle import ExpiringDocumentResponse

        resp = ExpiringDocumentResponse(
            archive_id=str(uuid.uuid4()),
            document_id=str(uuid.uuid4()),
            filename="Rechnung_2020.pdf",
            retention_category="invoice",
            retention_years=10,
            retention_expires_at=date.today() + timedelta(days=15),
            days_until_expiry=15,
            is_verified=True,
            archived_at="2020-01-15T10:00:00+00:00",
        )
        assert resp.days_until_expiry == 15
        assert resp.retention_category == "invoice"
