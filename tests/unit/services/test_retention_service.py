# -*- coding: utf-8 -*-
"""Tests fuer RetentionService (GoBD-Aufbewahrungsfristen).

Unit-Tests mit gemockter Datenbankschicht.
"""

import pytest
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


class TestRetentionServiceImport:
    """Stellt sicher, dass der Retention-Service importiert werden kann."""

    def test_import_modul(self):
        """retention_service-Modul laesst sich importieren."""
        import app.services.compliance.retention_service as module
        assert module is not None

    def test_import_service_klasse(self):
        """RetentionService kann importiert werden."""
        from app.services.compliance.retention_service import RetentionService
        assert RetentionService is not None

    def test_import_dataclasses(self):
        """RetentionAlert und RetentionStats koennen importiert werden."""
        from app.services.compliance.retention_service import (
            RetentionAlert,
            RetentionStats,
        )
        assert RetentionAlert is not None
        assert RetentionStats is not None

    def test_import_alert_level(self):
        """RetentionAlertLevel-Enum kann importiert werden."""
        from app.services.compliance.retention_service import RetentionAlertLevel
        assert RetentionAlertLevel.EXPIRED is not None
        assert RetentionAlertLevel.CRITICAL is not None
        assert RetentionAlertLevel.WARNING is not None
        assert RetentionAlertLevel.INFO is not None

    def test_import_default_perioden(self):
        """DEFAULT_RETENTION_PERIODS enthaelt bekannte Kategorien."""
        from app.services.compliance.retention_service import DEFAULT_RETENTION_PERIODS
        assert "invoice" in DEFAULT_RETENTION_PERIODS
        assert "contract" in DEFAULT_RETENTION_PERIODS
        assert DEFAULT_RETENTION_PERIODS["invoice"]["years"] == 10

    def test_import_singleton(self):
        """retention_service Singleton kann importiert werden."""
        from app.services.compliance.retention_service import (
            retention_service,
            RetentionService,
        )
        assert isinstance(retention_service, RetentionService)


class TestRetentionServiceInit:
    """Tests fuer RetentionService Initialisierung."""

    def test_instanz_erstellen(self):
        """RetentionService kann ohne Parameter instanziiert werden."""
        from app.services.compliance.retention_service import RetentionService
        service = RetentionService()
        assert service is not None

    def test_default_perioden_geladen(self):
        """Service laedt DEFAULT_RETENTION_PERIODS korrekt."""
        from app.services.compliance.retention_service import (
            RetentionService,
            DEFAULT_RETENTION_PERIODS,
        )
        service = RetentionService()
        assert service.default_periods is DEFAULT_RETENTION_PERIODS


class TestGetRetentionYears:
    """Tests fuer get_retention_years() (synchron)."""

    def test_rechnung_hat_10_jahre(self):
        """Kategorie 'invoice' hat 10 Jahre Aufbewahrungsfrist."""
        from app.services.compliance.retention_service import RetentionService
        service = RetentionService()
        assert service.get_retention_years("invoice") == 10

    def test_vertrag_hat_10_jahre(self):
        """Kategorie 'contract' hat 10 Jahre Aufbewahrungsfrist."""
        from app.services.compliance.retention_service import RetentionService
        service = RetentionService()
        assert service.get_retention_years("contract") == 10

    def test_geschaeftsbrief_hat_6_jahre(self):
        """Kategorie 'correspondence' hat 6 Jahre Aufbewahrungsfrist."""
        from app.services.compliance.retention_service import RetentionService
        service = RetentionService()
        assert service.get_retention_years("correspondence") == 6

    def test_unbekannte_kategorie_hat_10_jahre_default(self):
        """Unbekannte Kategorie faellt auf 10 Jahre (§147 AO) zurueck."""
        from app.services.compliance.retention_service import RetentionService
        service = RetentionService()
        assert service.get_retention_years("unbekannte_kategorie") == 10

    def test_grossschreibung_wird_ignoriert(self):
        """get_retention_years ist nicht case-sensitiv."""
        from app.services.compliance.retention_service import RetentionService
        service = RetentionService()
        assert service.get_retention_years("INVOICE") == service.get_retention_years("invoice")


class TestCalculateExpiryDate:
    """Tests fuer calculate_expiry_date() (synchrone Berechnung)."""

    def test_rechnung_ablaufdatum_10_jahre_nach_jahresende(self):
        """Rechnung vom 15.03.2024 laeuft am 31.12.2034 ab."""
        from app.services.compliance.retention_service import RetentionService
        service = RetentionService()
        doc_date = date(2024, 3, 15)
        expiry = service.calculate_expiry_date("invoice", doc_date)
        assert expiry == date(2034, 12, 31)

    def test_ablaufdatum_beginnt_am_jahresende(self):
        """Frist beginnt am 31.12. des Dokumentjahres, unabhaengig vom Monat."""
        from app.services.compliance.retention_service import RetentionService
        service = RetentionService()
        # Sowohl Januar als auch Dezember desselben Jahres muessen gleich enden
        expiry_jan = service.calculate_expiry_date("invoice", date(2024, 1, 1))
        expiry_dec = service.calculate_expiry_date("invoice", date(2024, 12, 31))
        assert expiry_jan == expiry_dec

    def test_custom_years_ueberschreibt_kategorie(self):
        """custom_years ueberschreibt die kategorie-basierten Standardwerte."""
        from app.services.compliance.retention_service import RetentionService
        service = RetentionService()
        doc_date = date(2024, 6, 1)
        expiry_standard = service.calculate_expiry_date("invoice", doc_date)
        expiry_custom = service.calculate_expiry_date("invoice", doc_date, custom_years=5)
        # 10 Jahre Standard vs. 5 Jahre Custom: Standard liegt 5 Jahre spaeter
        assert expiry_standard > expiry_custom

    def test_lieferschein_ablaufdatum_6_jahre(self):
        """Lieferschein vom 01.01.2024 laeuft am 31.12.2030 ab."""
        from app.services.compliance.retention_service import RetentionService
        service = RetentionService()
        expiry = service.calculate_expiry_date("delivery_note", date(2024, 1, 1))
        assert expiry == date(2030, 12, 31)


class TestGetExpiredArchives:
    """Tests fuer get_expired_archives() (async)."""

    @pytest.mark.asyncio
    async def test_gibt_leere_liste_wenn_keine_abgelaufenen(self):
        """get_expired_archives gibt leere Liste zurueck wenn nichts abgelaufen."""
        from app.services.compliance.retention_service import RetentionService
        service = RetentionService()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.get_expired_archives(mock_db, uuid4())
        assert result == []

    @pytest.mark.asyncio
    async def test_gibt_abgelaufene_archive_zurueck(self):
        """get_expired_archives gibt abgelaufene Archive zurueck."""
        from app.services.compliance.retention_service import RetentionService
        service = RetentionService()

        mock_archive = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_archive]
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.get_expired_archives(mock_db, uuid4())
        assert len(result) == 1
        assert result[0] is mock_archive


class TestRequestDeletion:
    """Tests fuer request_deletion() (async)."""

    @pytest.mark.asyncio
    async def test_archiv_nicht_gefunden_wirft_fehler(self):
        """request_deletion wirft ValueError wenn Archiv nicht existiert."""
        from app.services.compliance.retention_service import RetentionService
        service = RetentionService()

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="Archiv nicht gefunden"):
            await service.request_deletion(
                mock_db, uuid4(), uuid4(), "Frist abgelaufen", uuid4()
            )

    @pytest.mark.asyncio
    async def test_nicht_abgelaufenes_archiv_wirft_fehler(self):
        """request_deletion wirft ValueError wenn Frist noch nicht abgelaufen."""
        from app.services.compliance.retention_service import RetentionService
        service = RetentionService()

        company_id = uuid4()
        mock_archive = MagicMock()
        mock_archive.company_id = company_id
        # Ablaufdatum in der Zukunft
        mock_archive.retention_expires_at = date.today() + timedelta(days=365)

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=mock_archive)

        with pytest.raises(ValueError, match="Aufbewahrungsfrist ist noch nicht abgelaufen"):
            await service.request_deletion(
                mock_db, company_id, uuid4(), "Test", uuid4()
            )
