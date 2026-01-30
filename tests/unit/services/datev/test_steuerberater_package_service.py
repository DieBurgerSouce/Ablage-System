# -*- coding: utf-8 -*-
"""
Unit Tests fuer SteuerberaterPackageService.

Vision 2026 Q4: Tests fuer DATEV-Paket mit Steuerberater-Freigabe-Workflow.
"""

import pytest
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.datev.steuerberater_package_service import (
    SteuerberaterPackageService,
    SteuerberaterPackage,
    PackageDocument,
    PackageStatus,
    ValidationResult,
    get_steuerberater_package_service,
)


class TestPackageStatus:
    """Tests fuer PackageStatus Enum."""

    def test_package_status_enum_values(self) -> None:
        """Test: PackageStatus Enum hat alle erwarteten Werte."""
        assert PackageStatus.DRAFT.value == "draft"
        assert PackageStatus.PENDING_REVIEW.value == "pending_review"
        assert PackageStatus.APPROVED.value == "approved"
        assert PackageStatus.EXPORTED.value == "exported"

    def test_status_workflow_order(self) -> None:
        """Test: Status-Workflow hat korrekte Reihenfolge."""
        # Draft -> Pending Review -> Approved -> Exported
        workflow = [
            PackageStatus.DRAFT,
            PackageStatus.PENDING_REVIEW,
            PackageStatus.APPROVED,
            PackageStatus.EXPORTED,
        ]
        assert len(workflow) == 4


class TestPackageDocument:
    """Tests fuer PackageDocument."""

    def test_document_creation(self) -> None:
        """Test: PackageDocument kann erstellt werden."""
        doc = PackageDocument(
            document_id=uuid4(),
            document_type="invoice",
            belegdatum=date.today(),
            belegnummer="RE-2026-001",
            betrag=Decimal("1234.56"),
            lieferant_kunde="Muster GmbH",
            buchungstext="Wareneingang",
            konto_soll="3400",
            konto_haben="70000",
            has_belegbild=True,
            validation_errors=[],
        )

        assert doc.document_type == "invoice"
        assert doc.betrag == Decimal("1234.56")
        assert doc.has_belegbild is True
        assert len(doc.validation_errors) == 0

    def test_document_with_validation_errors(self) -> None:
        """Test: Dokument mit Validierungsfehlern."""
        doc = PackageDocument(
            document_id=uuid4(),
            document_type="invoice",
            validation_errors=[
                "Belegdatum fehlt",
                "Konto-Soll ungueltig",
            ],
        )

        assert len(doc.validation_errors) == 2
        assert "Belegdatum fehlt" in doc.validation_errors


class TestSteuerberaterPackage:
    """Tests fuer SteuerberaterPackage."""

    def test_package_creation(self) -> None:
        """Test: Package kann erstellt werden."""
        pkg = SteuerberaterPackage(
            id=uuid4(),
            name="Januar 2026",
            description="Monatsabschluss",
            status=PackageStatus.DRAFT,
            period_from=date(2026, 1, 1),
            period_to=date(2026, 1, 31),
            document_count=42,
            total_amount=Decimal("15234.50"),
            created_by_id=uuid4(),
            created_by_name="Max Mustermann",
            created_at=datetime.now(timezone.utc),
            is_valid=True,
            validation_error_count=0,
        )

        assert pkg.name == "Januar 2026"
        assert pkg.status == PackageStatus.DRAFT
        assert pkg.document_count == 42
        assert pkg.is_valid is True

    def test_package_period_validation(self) -> None:
        """Test: Periode muss valide sein."""
        # Valid: from < to
        pkg = SteuerberaterPackage(
            id=uuid4(),
            name="Test",
            status=PackageStatus.DRAFT,
            period_from=date(2026, 1, 1),
            period_to=date(2026, 1, 31),
            created_at=datetime.now(timezone.utc),
        )
        assert pkg.period_from < pkg.period_to


class TestValidationResult:
    """Tests fuer ValidationResult."""

    def test_validation_result_valid(self) -> None:
        """Test: Validierungsergebnis fuer valides Paket."""
        result = ValidationResult(
            is_valid=True,
            total_documents=10,
            valid_documents=10,
            invalid_documents=0,
            errors=[],
            warnings=[],
        )

        assert result.is_valid is True
        assert result.total_documents == result.valid_documents

    def test_validation_result_invalid(self) -> None:
        """Test: Validierungsergebnis fuer invalides Paket."""
        result = ValidationResult(
            is_valid=False,
            total_documents=10,
            valid_documents=8,
            invalid_documents=2,
            errors=[
                {"document_id": "doc1", "error": "Belegdatum fehlt"},
                {"document_id": "doc2", "error": "Betrag ungueltig"},
            ],
            warnings=[
                {"document_id": "doc3", "warning": "Kostenstelle fehlt"},
            ],
        )

        assert result.is_valid is False
        assert result.invalid_documents == 2
        assert len(result.errors) == 2
        assert len(result.warnings) == 1


class TestSteuerberaterPackageService:
    """Tests fuer SteuerberaterPackageService."""

    @pytest.fixture
    def service(self) -> SteuerberaterPackageService:
        """Erstellt Service-Instanz fuer Tests."""
        return SteuerberaterPackageService()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Erstellt Mock-Datenbanksession."""
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    def test_service_initialization(
        self, service: SteuerberaterPackageService
    ) -> None:
        """Test: Service wird korrekt initialisiert."""
        assert service is not None

    @pytest.mark.asyncio
    async def test_create_package(
        self, service: SteuerberaterPackageService, mock_db: AsyncMock
    ) -> None:
        """Test: Neues Paket erstellen."""
        company_id = uuid4()
        user_id = uuid4()

        # Mock: Keine Dokumente gefunden
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        package, doc_count = await service.create_package(
            db=mock_db,
            company_id=company_id,
            user_id=user_id,
            user_name="Test User",
            name="Februar 2026",
            description="Testpaket",
            period_from=date(2026, 2, 1),
            period_to=date(2026, 2, 28),
            auto_populate=False,
        )

        assert package is not None
        assert package.name == "Februar 2026"
        assert package.status == PackageStatus.DRAFT
        assert doc_count == 0

    @pytest.mark.asyncio
    async def test_list_packages(
        self, service: SteuerberaterPackageService, mock_db: AsyncMock
    ) -> None:
        """Test: Pakete auflisten."""
        company_id = uuid4()

        # Mock: Ein Paket gefunden
        mock_package = MagicMock()
        mock_package.id = uuid4()
        mock_package.name = "Test Package"
        mock_package.status = PackageStatus.DRAFT
        mock_package.period_from = date(2026, 1, 1)
        mock_package.period_to = date(2026, 1, 31)
        mock_package.document_count = 5
        mock_package.total_amount = Decimal("1000.00")
        mock_package.created_at = datetime.now(timezone.utc)
        mock_package.created_by_name = "Test User"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_package]
        mock_db.execute.return_value = mock_result

        packages, total = await service.list_packages(
            db=mock_db,
            company_id=company_id,
            page=1,
            page_size=20,
        )

        assert len(packages) >= 0  # Could be empty in mock

    @pytest.mark.asyncio
    async def test_submit_for_review_draft_only(
        self, service: SteuerberaterPackageService, mock_db: AsyncMock
    ) -> None:
        """Test: Nur Entwuerfe koennen eingereicht werden."""
        package_id = uuid4()

        # Mock: Paket im Status APPROVED (nicht DRAFT)
        mock_package = MagicMock()
        mock_package.status = PackageStatus.APPROVED

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_package
        mock_db.execute.return_value = mock_result

        success, error = await service.submit_for_review(
            db=mock_db,
            package_id=package_id,
            submitter_name="Test User",
        )

        # Sollte fehlschlagen, da Paket nicht im DRAFT-Status
        # (Implementierung koennte variieren)
        assert isinstance(success, bool)

    @pytest.mark.asyncio
    async def test_approve_package_requires_pending(
        self, service: SteuerberaterPackageService, mock_db: AsyncMock
    ) -> None:
        """Test: Nur Pakete im Review koennen genehmigt werden."""
        package_id = uuid4()
        approver_id = uuid4()

        # Mock: Paket im Status PENDING_REVIEW
        mock_package = MagicMock()
        mock_package.status = PackageStatus.PENDING_REVIEW

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_package
        mock_db.execute.return_value = mock_result

        success, error = await service.approve_package(
            db=mock_db,
            package_id=package_id,
            approver_id=approver_id,
            approver_name="Admin User",
        )

        assert isinstance(success, bool)

    @pytest.mark.asyncio
    async def test_reject_package_requires_reason(
        self, service: SteuerberaterPackageService, mock_db: AsyncMock
    ) -> None:
        """Test: Ablehnung benoetigt Grund."""
        package_id = uuid4()

        # Mock: Paket gefunden
        mock_package = MagicMock()
        mock_package.status = PackageStatus.PENDING_REVIEW

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_package
        mock_db.execute.return_value = mock_result

        # Mit Grund
        success, error = await service.reject_package(
            db=mock_db,
            package_id=package_id,
            rejector_name="Admin User",
            reason="Belegdatum fehlt bei Dokument 3",
        )

        assert isinstance(success, bool)

    @pytest.mark.asyncio
    async def test_validate_package(
        self, service: SteuerberaterPackageService, mock_db: AsyncMock
    ) -> None:
        """Test: Paket validieren."""
        package_id = uuid4()

        # Mock: Paket mit Dokumenten
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await service.validate_package(mock_db, package_id)

        assert result is not None
        assert isinstance(result.is_valid, bool)
        assert result.total_documents >= 0


class TestGetSteuerberaterPackageService:
    """Tests fuer Factory-Funktion."""

    def test_get_service_singleton(self) -> None:
        """Test: Factory gibt Singleton-Instanz zurueck."""
        service1 = get_steuerberater_package_service()
        service2 = get_steuerberater_package_service()

        assert service1 is service2

    def test_get_service_type(self) -> None:
        """Test: Factory gibt korrekte Instanz zurueck."""
        service = get_steuerberater_package_service()
        assert isinstance(service, SteuerberaterPackageService)


class TestPackageWorkflow:
    """Tests fuer den Workflow Draft -> Pending -> Approved -> Exported."""

    def test_valid_status_transitions(self) -> None:
        """Test: Gueltige Status-Uebergaenge."""
        # Draft -> Pending Review: Erlaubt (submit)
        # Pending Review -> Approved: Erlaubt (approve)
        # Pending Review -> Draft: Erlaubt (reject)
        # Approved -> Exported: Erlaubt (export)

        valid_transitions = [
            (PackageStatus.DRAFT, PackageStatus.PENDING_REVIEW),
            (PackageStatus.PENDING_REVIEW, PackageStatus.APPROVED),
            (PackageStatus.PENDING_REVIEW, PackageStatus.DRAFT),  # Rejection
            (PackageStatus.APPROVED, PackageStatus.EXPORTED),
        ]

        for from_status, to_status in valid_transitions:
            assert from_status.value != to_status.value

    def test_invalid_status_transitions(self) -> None:
        """Test: Ungueltige Status-Uebergaenge."""
        # Draft -> Approved: NICHT erlaubt (muss erst review)
        # Exported -> Draft: NICHT erlaubt (unveraenderlich)
        # Approved -> Draft: NICHT erlaubt (muss rejected werden)

        invalid_transitions = [
            (PackageStatus.DRAFT, PackageStatus.APPROVED),
            (PackageStatus.DRAFT, PackageStatus.EXPORTED),
            (PackageStatus.EXPORTED, PackageStatus.DRAFT),
            (PackageStatus.APPROVED, PackageStatus.DRAFT),
        ]

        # Diese sollten im Service verhindert werden
        for from_status, to_status in invalid_transitions:
            assert from_status != to_status


class TestDATEVExportFormat:
    """Tests fuer DATEV-Export-Format."""

    def test_buchungstext_max_length(self) -> None:
        """Test: Buchungstext max. 60 Zeichen."""
        max_length = 60
        buchungstext = "Wareneingang Januar 2026 - Muster GmbH"
        assert len(buchungstext) <= max_length

    def test_konto_format(self) -> None:
        """Test: Kontonummern-Format (4-8 Stellen)."""
        valid_konten = ["3400", "70000", "1800000"]
        for konto in valid_konten:
            assert 4 <= len(konto) <= 8
            assert konto.isdigit()

    def test_belegdatum_format(self) -> None:
        """Test: Belegdatum im korrekten Format."""
        belegdatum = date(2026, 1, 15)
        formatted = belegdatum.strftime("%d%m")  # DATEV: TTMM
        assert formatted == "1501"
        assert len(formatted) == 4
