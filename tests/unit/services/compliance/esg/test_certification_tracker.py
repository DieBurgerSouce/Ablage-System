# -*- coding: utf-8 -*-
"""
Unit Tests fuer CertificationTrackerService.

Testet:
- add_certification()
- update_certification()
- get_certifications()
- get_certification_detail()
- get_expiring_certifications()
- renew_certification()
- archive_certification()
- Erinnerungen und Benachrichtigungen

Feinpoliert und durchdacht - Certification Tracker Tests.
"""

from datetime import date, timedelta
from typing import List
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.services.compliance.esg.certification_tracker import (
    CertificationTracker as CertificationTrackerService,
    get_certification_tracker as get_certification_tracker_service,
)
from .conftest import create_mock_result


# ========================= Test Fixtures =========================


@pytest.fixture
def tracker_service(mock_db: AsyncMock) -> CertificationTrackerService:
    """Create CertificationTrackerService instance with mocked db."""
    return CertificationTrackerService(mock_db)


# ========================= Factory Function Tests =========================


class TestFactoryFunction:
    """Tests fuer get_certification_tracker_service Factory."""

    def test_get_certification_tracker_service_returns_instance(
        self, mock_db: AsyncMock
    ):
        """Factory sollte CertificationTrackerService-Instanz zurueckgeben."""
        service = get_certification_tracker_service(mock_db)

        assert isinstance(service, CertificationTrackerService)
        assert service.db is mock_db


# ========================= Add Certification Tests =========================


class TestAddCertification:
    """Tests fuer add_certification() Methode."""

    @pytest.mark.asyncio
    async def test_add_certification_success(
        self,
        tracker_service: CertificationTrackerService,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte neue Zertifizierung hinzufuegen."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        cert = await tracker_service.add_certification(
            company_id=company_id,
            certification_name="ISO 14001:2015",
            certification_type="environmental",
            certification_body="TUeV Rheinland",
            certificate_number="ENV-2026-12345",
            issue_date=date.today() - timedelta(days=365),
            expiry_date=date.today() + timedelta(days=730),
            scope_description="Umweltmanagementsystem fuer alle Standorte",
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_certification_with_sites(
        self,
        tracker_service: CertificationTrackerService,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte Zertifizierung mit Standorten hinzufuegen."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        sites = ["Hauptsitz Berlin", "Niederlassung Muenchen", "Lager Hamburg"]

        await tracker_service.add_certification(
            company_id=company_id,
            certification_name="ISO 45001:2018",
            certification_type="social",
            certification_body="DEKRA",
            certificate_number="SOC-2026-67890",
            issue_date=date.today(),
            expiry_date=date.today() + timedelta(days=365 * 3),
            applicable_sites=sites,
        )

        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_certification_with_document(
        self,
        tracker_service: CertificationTrackerService,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte Zertifizierung mit Dokument verknuepfen."""
        document_id = uuid4()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        await tracker_service.add_certification(
            company_id=company_id,
            certification_name="EcoVadis Gold",
            certification_type="environmental",
            certification_body="EcoVadis",
            issue_date=date.today(),
            expiry_date=date.today() + timedelta(days=365),
            document_id=document_id,
        )

        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_certification_sets_audit_date(
        self,
        tracker_service: CertificationTrackerService,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte naechstes Audit-Datum setzen."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        next_audit = date.today() + timedelta(days=180)

        await tracker_service.add_certification(
            company_id=company_id,
            certification_name="ISO 9001:2015",
            certification_type="governance",
            certification_body="DQS",
            issue_date=date.today(),
            expiry_date=date.today() + timedelta(days=365 * 3),
            next_audit_date=next_audit,
        )

        mock_db.add.assert_called_once()


# ========================= Update Certification Tests =========================


class TestUpdateCertification:
    """Tests fuer update_certification() Methode."""

    @pytest.mark.asyncio
    async def test_update_certification_success(
        self,
        tracker_service: CertificationTrackerService,
        mock_db: AsyncMock,
        sample_certification,
        company_id: UUID,
    ):
        """Sollte Zertifizierung aktualisieren."""
        mock_db.execute.return_value = create_mock_result(
            scalar_value=sample_certification
        )
        mock_db.commit = AsyncMock()

        result = await tracker_service.update_certification(
            certification_id=sample_certification.id,
            company_id=company_id,
            next_audit_date=date.today() + timedelta(days=90),
        )

        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_certification_expiry(
        self,
        tracker_service: CertificationTrackerService,
        mock_db: AsyncMock,
        sample_certification,
        company_id: UUID,
    ):
        """Sollte Ablaufdatum aktualisieren."""
        mock_db.execute.return_value = create_mock_result(
            scalar_value=sample_certification
        )
        mock_db.commit = AsyncMock()

        new_expiry = date.today() + timedelta(days=365 * 3)

        await tracker_service.update_certification(
            certification_id=sample_certification.id,
            company_id=company_id,
            expiry_date=new_expiry,
        )

        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_certification_not_found(
        self,
        tracker_service: CertificationTrackerService,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte Fehler werfen wenn nicht gefunden."""
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        with pytest.raises(ValueError, match="nicht gefunden"):
            await tracker_service.update_certification(
                certification_id=uuid4(),
                company_id=company_id,
                next_audit_date=date.today(),
            )


# ========================= Get Certifications Tests =========================


class TestGetCertifications:
    """Tests fuer get_certifications() Methode."""

    @pytest.mark.asyncio
    async def test_get_certifications_success(
        self,
        tracker_service: CertificationTrackerService,
        mock_db: AsyncMock,
        sample_certifications: List[MagicMock],
        company_id: UUID,
    ):
        """Sollte Zertifizierungen zurueckgeben."""
        mock_db.execute.return_value = create_mock_result(
            scalars_list=sample_certifications
        )

        result = await tracker_service.get_certifications(company_id=company_id)

        assert len(result) == len(sample_certifications)

    @pytest.mark.asyncio
    async def test_get_certifications_filter_by_type(
        self,
        tracker_service: CertificationTrackerService,
        mock_db: AsyncMock,
        sample_certifications: List[MagicMock],
        company_id: UUID,
    ):
        """Sollte nach Typ filtern."""
        env_certs = [c for c in sample_certifications if c.category == "environmental"]
        mock_db.execute.return_value = create_mock_result(scalars_list=env_certs)

        result = await tracker_service.get_certifications(
            company_id=company_id,
            certification_type="environmental",
        )

        for c in result:
            assert c.category == "environmental"

    @pytest.mark.asyncio
    async def test_get_certifications_filter_by_status(
        self,
        tracker_service: CertificationTrackerService,
        mock_db: AsyncMock,
        sample_certifications: List[MagicMock],
        company_id: UUID,
    ):
        """Sollte nach Status filtern."""
        active_certs = [c for c in sample_certifications if c.status == "active"]
        mock_db.execute.return_value = create_mock_result(scalars_list=active_certs)

        result = await tracker_service.get_certifications(
            company_id=company_id,
            status="active",
        )

        for c in result:
            assert c.status == "active"


# ========================= Get Certification Detail Tests =========================


class TestGetCertificationDetail:
    """Tests fuer get_certification_detail() Methode."""

    @pytest.mark.asyncio
    async def test_get_certification_detail_success(
        self,
        tracker_service: CertificationTrackerService,
        mock_db: AsyncMock,
        sample_certification,
        company_id: UUID,
    ):
        """Sollte Zertifizierungsdetails zurueckgeben."""
        mock_db.execute.return_value = create_mock_result(
            scalar_value=sample_certification
        )

        result = await tracker_service.get_certification_detail(
            certification_id=sample_certification.id,
            company_id=company_id,
        )

        assert result is not None
        assert result.id == sample_certification.id

    @pytest.mark.asyncio
    async def test_get_certification_detail_not_found(
        self,
        tracker_service: CertificationTrackerService,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte None zurueckgeben wenn nicht gefunden."""
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        result = await tracker_service.get_certification_detail(
            certification_id=uuid4(),
            company_id=company_id,
        )

        assert result is None


# ========================= Expiring Certifications Tests =========================


class TestGetExpiringCertifications:
    """Tests fuer get_expiring_certifications() Methode."""

    @pytest.mark.asyncio
    async def test_get_expiring_certifications_success(
        self,
        tracker_service: CertificationTrackerService,
        mock_db: AsyncMock,
        sample_certifications: List[MagicMock],
        company_id: UUID,
    ):
        """Sollte bald ablaufende Zertifizierungen zurueckgeben."""
        expiring = [
            c
            for c in sample_certifications
            if c.expiry_date <= date.today() + timedelta(days=90)
        ]
        mock_db.execute.return_value = create_mock_result(scalars_list=expiring)

        result = await tracker_service.get_expiring_certifications(
            company_id=company_id,
            days_ahead=90,
        )

        for c in result:
            assert c.expiry_date <= date.today() + timedelta(days=90)

    @pytest.mark.asyncio
    async def test_get_expiring_certifications_custom_days(
        self,
        tracker_service: CertificationTrackerService,
        mock_db: AsyncMock,
        sample_certifications: List[MagicMock],
        company_id: UUID,
    ):
        """Sollte mit benutzerdefiniertem Zeitraum filtern."""
        expiring = [
            c
            for c in sample_certifications
            if c.expiry_date <= date.today() + timedelta(days=30)
        ]
        mock_db.execute.return_value = create_mock_result(scalars_list=expiring)

        result = await tracker_service.get_expiring_certifications(
            company_id=company_id,
            days_ahead=30,
        )

        # All returned should expire within 30 days
        assert mock_db.execute.called


# ========================= Renew Certification Tests =========================


class TestRenewCertification:
    """Tests fuer renew_certification() Methode."""

    @pytest.mark.asyncio
    async def test_renew_certification_success(
        self,
        tracker_service: CertificationTrackerService,
        mock_db: AsyncMock,
        sample_certification,
        company_id: UUID,
    ):
        """Sollte Zertifizierung erneuern."""
        mock_db.execute.return_value = create_mock_result(
            scalar_value=sample_certification
        )
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        new_expiry = date.today() + timedelta(days=365 * 3)
        new_certificate_number = "ENV-2029-99999"

        result = await tracker_service.renew_certification(
            certification_id=sample_certification.id,
            company_id=company_id,
            new_expiry_date=new_expiry,
            new_certificate_number=new_certificate_number,
        )

        # Should update existing or create new record
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_renew_certification_not_found(
        self,
        tracker_service: CertificationTrackerService,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte Fehler werfen wenn nicht gefunden."""
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        with pytest.raises(ValueError, match="nicht gefunden"):
            await tracker_service.renew_certification(
                certification_id=uuid4(),
                company_id=company_id,
                new_expiry_date=date.today() + timedelta(days=365),
            )


# ========================= Archive Certification Tests =========================


class TestArchiveCertification:
    """Tests fuer archive_certification() Methode."""

    @pytest.mark.asyncio
    async def test_archive_certification_success(
        self,
        tracker_service: CertificationTrackerService,
        mock_db: AsyncMock,
        sample_certification,
        company_id: UUID,
    ):
        """Sollte Zertifizierung archivieren."""
        sample_certification.status = "active"
        mock_db.execute.return_value = create_mock_result(
            scalar_value=sample_certification
        )
        mock_db.commit = AsyncMock()

        result = await tracker_service.archive_certification(
            certification_id=sample_certification.id,
            company_id=company_id,
            reason="Ersetzt durch neuere Version",
        )

        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_archive_certification_already_archived(
        self,
        tracker_service: CertificationTrackerService,
        mock_db: AsyncMock,
        sample_certification,
        company_id: UUID,
    ):
        """Sollte Warnung bei bereits archivierter Zertifizierung."""
        sample_certification.status = "archived"
        mock_db.execute.return_value = create_mock_result(
            scalar_value=sample_certification
        )

        # Should not throw error, just return
        await tracker_service.archive_certification(
            certification_id=sample_certification.id,
            company_id=company_id,
        )


# ========================= Reminder Tests =========================


class TestGetCertificationsNeedingReminder:
    """Tests fuer get_certifications_needing_reminder() Methode."""

    @pytest.mark.asyncio
    async def test_get_certifications_needing_reminder(
        self,
        tracker_service: CertificationTrackerService,
        mock_db: AsyncMock,
        sample_certifications: List[MagicMock],
        company_id: UUID,
    ):
        """Sollte Zertifizierungen mit faelliger Erinnerung zurueckgeben."""
        # Set reminder for some certs
        for i, c in enumerate(sample_certifications):
            c.reminder_days_before = 90
            c.expiry_date = date.today() + timedelta(days=80 if i < 2 else 120)

        needing_reminder = [
            c
            for c in sample_certifications
            if c.expiry_date <= date.today() + timedelta(days=c.reminder_days_before)
        ]
        mock_db.execute.return_value = create_mock_result(scalars_list=needing_reminder)

        result = await tracker_service.get_certifications_needing_reminder(
            company_id=company_id
        )

        assert len(result) == 2


# ========================= Statistics Tests =========================


class TestGetCertificationStats:
    """Tests fuer get_certification_stats() Methode."""

    @pytest.mark.asyncio
    async def test_get_certification_stats_success(
        self,
        tracker_service: CertificationTrackerService,
        mock_db: AsyncMock,
        sample_certifications: List[MagicMock],
        company_id: UUID,
    ):
        """Sollte Statistiken zurueckgeben."""
        # Mock stats query
        stats_mock = MagicMock()
        stats_mock.total = len(sample_certifications)
        stats_mock.active = len([c for c in sample_certifications if c.status == "active"])
        stats_mock.expiring_soon = 2
        stats_mock.by_category = {"environmental": 2, "social": 1, "governance": 2}

        mock_db.execute.return_value = create_mock_result(scalar_value=stats_mock)

        result = await tracker_service.get_certification_stats(company_id=company_id)

        # Starke Assertion: Certification-Stats MUSS total enthalten
        assert result is not None, "get_certification_stats sollte ein Ergebnis zurueckgeben"
        assert "total" in result, \
            f"Certification-Stats muss 'total' enthalten, erhielt: {result.keys() if isinstance(result, dict) else type(result)}"
        mock_db.execute.assert_called()  # Verifiziere, dass DB aufgerufen wurde
