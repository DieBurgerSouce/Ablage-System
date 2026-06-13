# -*- coding: utf-8 -*-
"""
Unit Tests fuer CertificationTracker.

Testet gegen den ECHTEN Vertrag von
app.services.compliance.esg.certification_tracker:
- get_certification_types()
- add_certification()  (benoetigt category aus ESGCategory)
- get_certifications()  (gibt (List[dict], int) zurueck)
- get_certification_detail()
- get_expiring_soon()
- get_upcoming_audits()
- record_audit()
- update_status()
- check_expired_certifications()
- get_certification_summary()

Feinpoliert und durchdacht - Certification Tracker Tests.
"""

from datetime import date, timedelta
from typing import List
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.services.compliance.esg.certification_tracker import (
    CertificationTracker,
    get_certification_tracker,
    CERTIFICATION_TYPES,
)
from app.db.models_esg import CertificationStatus
from .conftest import create_mock_result


# ========================= Test Fixtures =========================


@pytest.fixture
def tracker_service(mock_db: AsyncMock) -> CertificationTracker:
    """Create CertificationTracker instance with mocked db."""
    return CertificationTracker(mock_db)


# ========================= Factory Function Tests =========================


class TestFactoryFunction:
    """Tests fuer get_certification_tracker Factory."""

    def test_get_certification_tracker_returns_instance(self, mock_db: AsyncMock):
        """Factory sollte CertificationTracker-Instanz zurueckgeben."""
        service = get_certification_tracker(mock_db)

        assert isinstance(service, CertificationTracker)
        assert service.db is mock_db


# ========================= Certification Types Tests =========================


class TestCertificationTypes:
    """Tests fuer get_certification_types()."""

    def test_get_certification_types_known(
        self, tracker_service: CertificationTracker
    ):
        """Sollte bekannte Zertifizierungstypen mit Kategorie liefern."""
        types = tracker_service.get_certification_types()

        assert "ISO_14001" in types
        assert types["ISO_14001"]["category"] == "environmental"
        assert "ISO_45001" in types
        assert types["ISO_45001"]["category"] == "social"


# ========================= Add Certification Tests =========================


class TestAddCertification:
    """Tests fuer add_certification() Methode."""

    @pytest.mark.asyncio
    async def test_add_certification_success(
        self,
        tracker_service: CertificationTracker,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte neue Zertifizierung hinzufuegen."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        cert = await tracker_service.add_certification(
            company_id=company_id,
            certification_type="ISO_14001",
            certification_name="ISO 14001:2015",
            category="environmental",
            certification_body="TUeV Rheinland",
            certificate_number="ENV-2026-12345",
            issue_date=date.today() - timedelta(days=365),
            expiry_date=date.today() + timedelta(days=730),
            scope_description="Umweltmanagementsystem fuer alle Standorte",
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        # Noch gueltig -> Status ACTIVE
        assert cert.status == CertificationStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_add_certification_expired_sets_status(
        self,
        tracker_service: CertificationTracker,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Abgelaufenes Ablaufdatum sollte Status EXPIRED setzen."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        cert = await tracker_service.add_certification(
            company_id=company_id,
            certification_type="ISO_27001",
            certification_name="ISO 27001:2022",
            category="governance",
            issue_date=date.today() - timedelta(days=800),
            expiry_date=date.today() - timedelta(days=10),  # bereits abgelaufen
        )

        assert cert.status == CertificationStatus.EXPIRED

    @pytest.mark.asyncio
    async def test_add_certification_invalid_category_raises(
        self,
        tracker_service: CertificationTracker,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Ungueltige Kategorie sollte ValueError werfen."""
        with pytest.raises(ValueError, match="Kategorie"):
            await tracker_service.add_certification(
                company_id=company_id,
                certification_type="CUSTOM",
                certification_name="Phantasie-Zert",
                category="ungueltig",
                issue_date=date.today(),
            )

    @pytest.mark.asyncio
    async def test_add_certification_with_sites(
        self,
        tracker_service: CertificationTracker,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte Standorte am Zertifikat speichern."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        sites = ["Hauptsitz Berlin", "Niederlassung Muenchen", "Lager Hamburg"]

        cert = await tracker_service.add_certification(
            company_id=company_id,
            certification_type="ISO_45001",
            certification_name="ISO 45001:2018",
            category="social",
            certification_body="DEKRA",
            issue_date=date.today(),
            expiry_date=date.today() + timedelta(days=365 * 3),
            applicable_sites=sites,
        )

        assert cert.applicable_sites == sites


# ========================= Get Certifications Tests =========================


class TestGetCertifications:
    """Tests fuer get_certifications() (gibt (List[dict], int) zurueck)."""

    @pytest.mark.asyncio
    async def test_get_certifications_success(
        self,
        tracker_service: CertificationTracker,
        mock_db: AsyncMock,
        sample_certifications: List[MagicMock],
        company_id: UUID,
    ):
        """Sollte Zertifizierungen als Dict-Liste mit Gesamtanzahl liefern."""
        for c in sample_certifications:
            c.status = "active"
        count_result = create_mock_result(scalar_value=len(sample_certifications))
        list_result = create_mock_result(scalars_list=sample_certifications)
        mock_db.execute.side_effect = [count_result, list_result]

        result, total = await tracker_service.get_certifications(company_id=company_id)

        assert total == len(sample_certifications)
        assert len(result) == len(sample_certifications)
        assert all(isinstance(c, dict) for c in result)
        assert "certification_name" in result[0]
        assert "days_until_expiry" in result[0]

    @pytest.mark.asyncio
    async def test_get_certifications_filter_by_category(
        self,
        tracker_service: CertificationTracker,
        mock_db: AsyncMock,
        sample_certifications: List[MagicMock],
        company_id: UUID,
    ):
        """Sollte nach Kategorie filtern (Service serialisiert die Treffer)."""
        env_certs = [c for c in sample_certifications if c.category == "environmental"]
        for c in env_certs:
            c.status = "active"
        count_result = create_mock_result(scalar_value=len(env_certs))
        list_result = create_mock_result(scalars_list=env_certs)
        mock_db.execute.side_effect = [count_result, list_result]

        result, total = await tracker_service.get_certifications(
            company_id=company_id,
            category="environmental",
        )

        assert total == len(env_certs)
        for c in result:
            assert c["category"] == "environmental"


# ========================= Get Certification Detail Tests =========================


class TestGetCertificationDetail:
    """Tests fuer get_certification_detail() Methode."""

    @pytest.mark.asyncio
    async def test_get_certification_detail_success(
        self,
        tracker_service: CertificationTracker,
        mock_db: AsyncMock,
        sample_certification,
        company_id: UUID,
    ):
        """Sollte Zertifizierungsdetails als Dict liefern."""
        sample_certification.status = "active"
        sample_certification.last_audit_date = None
        sample_certification.audit_findings = None
        mock_db.execute.return_value = create_mock_result(
            scalar_value=sample_certification
        )

        result = await tracker_service.get_certification_detail(
            certification_id=sample_certification.id,
            company_id=company_id,
        )

        assert result is not None
        assert isinstance(result, dict)
        assert result["id"] == str(sample_certification.id)
        assert result["certification_name"] == sample_certification.certification_name

    @pytest.mark.asyncio
    async def test_get_certification_detail_not_found(
        self,
        tracker_service: CertificationTracker,
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


class TestGetExpiringSoon:
    """Tests fuer get_expiring_soon() Methode."""

    @pytest.mark.asyncio
    async def test_get_expiring_soon_success(
        self,
        tracker_service: CertificationTracker,
        mock_db: AsyncMock,
        sample_certifications: List[MagicMock],
        company_id: UUID,
    ):
        """Sollte bald ablaufende Zertifizierungen als Dict-Liste liefern."""
        expiring = [
            c
            for c in sample_certifications
            if c.expiry_date <= date.today() + timedelta(days=90)
        ]
        mock_db.execute.return_value = create_mock_result(scalars_list=expiring)

        result = await tracker_service.get_expiring_soon(
            company_id=company_id,
            days=90,
        )

        assert len(result) == len(expiring)
        assert all(isinstance(c, dict) for c in result)
        for c in result:
            assert "days_until_expiry" in c

    @pytest.mark.asyncio
    async def test_get_expiring_soon_empty(
        self,
        tracker_service: CertificationTracker,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte leere Liste liefern wenn nichts bald ablaeuft."""
        mock_db.execute.return_value = create_mock_result(scalars_list=[])

        result = await tracker_service.get_expiring_soon(
            company_id=company_id,
            days=30,
        )

        assert result == []


# ========================= Upcoming Audits Tests =========================


class TestGetUpcomingAudits:
    """Tests fuer get_upcoming_audits() Methode."""

    @pytest.mark.asyncio
    async def test_get_upcoming_audits_success(
        self,
        tracker_service: CertificationTracker,
        mock_db: AsyncMock,
        sample_certifications: List[MagicMock],
        company_id: UUID,
    ):
        """Sollte anstehende Audits als Dict-Liste liefern."""
        mock_db.execute.return_value = create_mock_result(
            scalars_list=sample_certifications
        )

        result = await tracker_service.get_upcoming_audits(
            company_id=company_id,
            days=60,
        )

        assert len(result) == len(sample_certifications)
        for c in result:
            assert "days_until_audit" in c


# ========================= Record Audit Tests =========================


class TestRecordAudit:
    """Tests fuer record_audit() Methode."""

    @pytest.mark.asyncio
    async def test_record_audit_success(
        self,
        tracker_service: CertificationTracker,
        mock_db: AsyncMock,
        sample_certification,
        company_id: UUID,
    ):
        """Sollte Audit-Daten am Zertifikat aktualisieren."""
        mock_db.execute.return_value = create_mock_result(
            scalar_value=sample_certification
        )
        mock_db.commit = AsyncMock()

        new_audit_date = date.today() + timedelta(days=180)
        result = await tracker_service.record_audit(
            certification_id=sample_certification.id,
            company_id=company_id,
            audit_date=date.today(),
            findings=["Keine Abweichungen"],
            next_audit_date=new_audit_date,
        )

        assert result is True
        mock_db.commit.assert_called_once()
        assert sample_certification.last_audit_date == date.today()
        assert sample_certification.next_audit_date == new_audit_date

    @pytest.mark.asyncio
    async def test_record_audit_not_found(
        self,
        tracker_service: CertificationTracker,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte False zurueckgeben wenn Zertifizierung nicht existiert."""
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        result = await tracker_service.record_audit(
            certification_id=uuid4(),
            company_id=company_id,
            audit_date=date.today(),
        )

        assert result is False


# ========================= Update Status Tests =========================


class TestUpdateStatus:
    """Tests fuer update_status() Methode."""

    @pytest.mark.asyncio
    async def test_update_status_success(
        self,
        tracker_service: CertificationTracker,
        mock_db: AsyncMock,
        sample_certification,
        company_id: UUID,
    ):
        """Sollte Status auf einen gueltigen Wert setzen."""
        mock_db.execute.return_value = create_mock_result(
            scalar_value=sample_certification
        )
        mock_db.commit = AsyncMock()

        result = await tracker_service.update_status(
            certification_id=sample_certification.id,
            company_id=company_id,
            new_status="revoked",
        )

        assert result is True
        assert sample_certification.status == "revoked"
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_status_invalid_raises(
        self,
        tracker_service: CertificationTracker,
        mock_db: AsyncMock,
        sample_certification,
        company_id: UUID,
    ):
        """Ungueltiger Status sollte ValueError werfen."""
        mock_db.execute.return_value = create_mock_result(
            scalar_value=sample_certification
        )

        with pytest.raises(ValueError, match="Status"):
            await tracker_service.update_status(
                certification_id=sample_certification.id,
                company_id=company_id,
                new_status="archiviert",  # kein gueltiger CertificationStatus
            )

    @pytest.mark.asyncio
    async def test_update_status_not_found(
        self,
        tracker_service: CertificationTracker,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte False zurueckgeben wenn nicht gefunden."""
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        result = await tracker_service.update_status(
            certification_id=uuid4(),
            company_id=company_id,
            new_status="active",
        )

        assert result is False


# ========================= Check Expired Tests =========================


class TestCheckExpiredCertifications:
    """Tests fuer check_expired_certifications() Methode."""

    @pytest.mark.asyncio
    async def test_check_expired_marks_and_counts(
        self,
        tracker_service: CertificationTracker,
        mock_db: AsyncMock,
        sample_certifications: List[MagicMock],
        company_id: UUID,
    ):
        """Sollte abgelaufene ACTIVE-Zertifikate auf EXPIRED setzen und zaehlen."""
        # Service liefert (per Query) nur die als abgelaufen geltenden Zertifikate
        expired = sample_certifications[:2]
        mock_db.execute.return_value = create_mock_result(scalars_list=expired)
        mock_db.commit = AsyncMock()

        count = await tracker_service.check_expired_certifications(
            company_id=company_id
        )

        assert count == 2
        for c in expired:
            assert c.status == CertificationStatus.EXPIRED
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_expired_none(
        self,
        tracker_service: CertificationTracker,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte 0 liefern und nicht committen wenn nichts abgelaufen ist."""
        mock_db.execute.return_value = create_mock_result(scalars_list=[])
        mock_db.commit = AsyncMock()

        count = await tracker_service.check_expired_certifications(
            company_id=company_id
        )

        assert count == 0
        mock_db.commit.assert_not_called()


# ========================= Statistics Tests =========================


class TestGetCertificationSummary:
    """Tests fuer get_certification_summary() Methode."""

    @pytest.mark.asyncio
    async def test_get_certification_summary_success(
        self,
        tracker_service: CertificationTracker,
        mock_db: AsyncMock,
        sample_certifications: List[MagicMock],
        company_id: UUID,
    ):
        """Sollte aggregierte Statistik (total, by_category, by_status) liefern."""
        # Status als String-Werte setzen (Service zaehlt darueber)
        for c in sample_certifications:
            c.status = "active" if c.status != "expiring" else "active"
        mock_db.execute.return_value = create_mock_result(
            scalars_list=sample_certifications
        )

        result = await tracker_service.get_certification_summary(
            company_id=company_id
        )

        assert result is not None
        assert result["total"] == len(sample_certifications)
        assert "by_category" in result
        assert "by_status" in result
        # Summe der Kategorie-Zaehler entspricht der Gesamtzahl
        assert sum(result["by_category"].values()) == len(sample_certifications)
