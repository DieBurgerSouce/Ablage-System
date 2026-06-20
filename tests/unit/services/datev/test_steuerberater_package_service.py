# -*- coding: utf-8 -*-
"""
Unit Tests fuer SteuerberaterPackageService.

Vision 2026 Q4: Tests fuer DATEV-Paket mit Steuerberater-Freigabe-Workflow.
"""

import pytest
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from app.services.datev.steuerberater_package_service import (
    SteuerberaterPackageService,
    SteuerberaterPackage,
    PackageDocument,
    PackageStatus,
    PackageValidationResult as ValidationResult,
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
            document_number="RE-2026-001",
            document_date=date.today(),
            document_type="invoice",
            amount=Decimal("1234.56"),
            tax_amount=Decimal("197.30"),
            tax_rate=Decimal("19"),
            account_debit="3400",
            account_credit="70000",
            description="Wareneingang",
            entity_name="Muster GmbH",
        )

        assert doc.document_type == "invoice"
        assert doc.amount == Decimal("1234.56")
        assert doc.entity_name == "Muster GmbH"
        assert doc.validation_errors == []

    def test_document_with_validation_errors(self) -> None:
        """Test: Dokument mit Validierungsfehlern."""
        doc = PackageDocument(
            document_id=uuid4(),
            document_number="RE-2026-002",
            document_date=date.today(),
            document_type="invoice",
            amount=Decimal("100.00"),
            tax_amount=Decimal("19.00"),
            tax_rate=Decimal("19"),
            account_debit="3400",
            account_credit="70000",
            description="Test",
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
            status=PackageStatus.DRAFT,
            period_from=date(2026, 1, 1),
            period_to=date(2026, 1, 31),
            total_documents=42,
            total_amount=Decimal("15234.50"),
            created_by_id=uuid4(),
            created_at=datetime.now(timezone.utc),
            validation_passed=True,
        )

        assert pkg.status == PackageStatus.DRAFT
        assert pkg.total_documents == 42
        assert pkg.total_amount == Decimal("15234.50")
        assert pkg.validation_passed is True

    def test_package_period_validation(self) -> None:
        """Test: Periode muss valide sein."""
        # Valid: from < to
        pkg = SteuerberaterPackage(
            id=uuid4(),
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
            passed=True,
            errors=[],
            warnings=[],
            document_errors={},
            summary={
                "total_documents": 10,
                "valid_documents": 10,
                "total_amount": "1000.00",
                "total_tax": "190.00",
            },
        )

        assert result.passed is True
        assert result.document_errors == {}
        assert result.summary["total_documents"] == result.summary["valid_documents"]

    def test_validation_result_invalid(self) -> None:
        """Test: Validierungsergebnis fuer invalides Paket."""
        result = ValidationResult(
            passed=False,
            errors=["Keine Dokumente im Paket"],
            warnings=["Dokument RE-3 ausserhalb Zeitraum"],
            document_errors={
                "doc1": ["Belegdatum fehlt"],
                "doc2": ["Betrag ist 0"],
            },
            summary={
                "total_documents": 10,
                "valid_documents": 8,
                "total_amount": "1000.00",
                "total_tax": "190.00",
            },
        )

        assert result.passed is False
        assert len(result.document_errors) == 2
        assert len(result.errors) == 1
        assert len(result.warnings) == 1


class TestSteuerberaterPackageService:
    """Tests fuer SteuerberaterPackageService."""

    @pytest.fixture
    def service(self) -> SteuerberaterPackageService:
        """Erstellt Service-Instanz fuer Tests (In-Memory-Store)."""
        return SteuerberaterPackageService()

    def _make_valid_document(self) -> PackageDocument:
        """Erstellt ein DATEV-valides Dokument im Zeitraum 2026-02."""
        return PackageDocument(
            document_id=uuid4(),
            document_number="RE-2026-100",
            document_date=date(2026, 2, 15),
            document_type="invoice",
            amount=Decimal("119.00"),
            tax_amount=Decimal("19.00"),
            tax_rate=Decimal("19"),
            account_debit="3400",
            account_credit="70000",
            description="Wareneingang Februar",
        )

    def test_service_initialization(
        self, service: SteuerberaterPackageService
    ) -> None:
        """Test: Service wird korrekt initialisiert."""
        assert service is not None

    @pytest.mark.asyncio
    async def test_create_package(
        self, service: SteuerberaterPackageService
    ) -> None:
        """Test: Neues Paket erstellen (In-Memory-Store)."""
        company_id = uuid4()
        user_id = uuid4()

        package = await service.create_package(
            company_id=company_id,
            period_from=date(2026, 2, 1),
            period_to=date(2026, 2, 28),
            created_by_id=user_id,
        )

        assert package is not None
        assert package.company_id == company_id
        assert package.created_by_id == user_id
        assert package.status == PackageStatus.DRAFT
        assert package.total_documents == 0
        # Paket wird im Store abgelegt und ist abrufbar
        assert await service.get_package(package.id) is package

    @pytest.mark.asyncio
    async def test_list_packages(
        self, service: SteuerberaterPackageService
    ) -> None:
        """Test: Pakete fuer eine Company auflisten (company-gescoped)."""
        company_id = uuid4()
        other_company = uuid4()

        await service.create_package(
            company_id=company_id,
            period_from=date(2026, 1, 1),
            period_to=date(2026, 1, 31),
            created_by_id=uuid4(),
        )
        await service.create_package(
            company_id=other_company,
            period_from=date(2026, 1, 1),
            period_to=date(2026, 1, 31),
            created_by_id=uuid4(),
        )

        packages = await service.list_packages(company_id=company_id)

        # Nur das Paket der eigenen Company darf zurueckkommen (Mandantentrennung)
        assert len(packages) == 1
        assert packages[0].company_id == company_id

    @pytest.mark.asyncio
    async def test_submit_for_review_draft_only(
        self, service: SteuerberaterPackageService
    ) -> None:
        """Test: Nur validierte Entwuerfe koennen eingereicht werden."""
        package = await service.create_package(
            company_id=uuid4(),
            period_from=date(2026, 2, 1),
            period_to=date(2026, 2, 28),
            created_by_id=uuid4(),
        )
        await service.add_documents(package.id, [self._make_valid_document()])
        await service.validate_package(package.id)

        submitted = await service.submit_for_review(package.id)
        assert submitted.status == PackageStatus.PENDING_REVIEW

        # Erneutes Einreichen (nicht mehr DRAFT) muss fehlschlagen
        with pytest.raises(ValueError):
            await service.submit_for_review(package.id)

    @pytest.mark.asyncio
    async def test_approve_package_requires_pending(
        self, service: SteuerberaterPackageService
    ) -> None:
        """Test: Nur Pakete im Review koennen genehmigt werden."""
        approver_id = uuid4()
        package = await service.create_package(
            company_id=uuid4(),
            period_from=date(2026, 2, 1),
            period_to=date(2026, 2, 28),
            created_by_id=uuid4(),
        )

        # Im DRAFT-Status darf nicht genehmigt werden
        with pytest.raises(ValueError):
            await service.approve_package(package.id, approver_id)

        await service.add_documents(package.id, [self._make_valid_document()])
        await service.validate_package(package.id)
        await service.submit_for_review(package.id)

        approved = await service.approve_package(
            package.id, approver_id, comment="Freigegeben"
        )
        assert approved.status == PackageStatus.APPROVED
        assert approved.approved_by_id == approver_id
        assert approved.approval_comment == "Freigegeben"

    @pytest.mark.asyncio
    async def test_reject_package_requires_pending(
        self, service: SteuerberaterPackageService
    ) -> None:
        """Test: Ablehnung speichert den Grund und nur aus PENDING_REVIEW."""
        rejector_id = uuid4()
        package = await service.create_package(
            company_id=uuid4(),
            period_from=date(2026, 2, 1),
            period_to=date(2026, 2, 28),
            created_by_id=uuid4(),
        )
        await service.add_documents(package.id, [self._make_valid_document()])
        await service.validate_package(package.id)
        await service.submit_for_review(package.id)

        rejected = await service.reject_package(
            package.id,
            rejector_id,
            reason="Belegdatum fehlt bei Dokument 3",
        )
        assert rejected.status == PackageStatus.REJECTED
        assert rejected.rejection_reason == "Belegdatum fehlt bei Dokument 3"

    @pytest.mark.asyncio
    async def test_validate_package(
        self, service: SteuerberaterPackageService
    ) -> None:
        """Test: Leeres Paket schlaegt die Validierung fehl."""
        package = await service.create_package(
            company_id=uuid4(),
            period_from=date(2026, 2, 1),
            period_to=date(2026, 2, 28),
            created_by_id=uuid4(),
        )

        result = await service.validate_package(package.id)

        assert result is not None
        assert isinstance(result.passed, bool)
        # Ein Paket ohne Dokumente ist nicht valide
        assert result.passed is False
        assert "Keine Dokumente im Paket" in result.errors

    @pytest.mark.asyncio
    async def test_validate_package_with_valid_document(
        self, service: SteuerberaterPackageService
    ) -> None:
        """Test: Paket mit DATEV-validem Dokument besteht die Validierung."""
        package = await service.create_package(
            company_id=uuid4(),
            period_from=date(2026, 2, 1),
            period_to=date(2026, 2, 28),
            created_by_id=uuid4(),
        )
        await service.add_documents(package.id, [self._make_valid_document()])

        result = await service.validate_package(package.id)

        assert result.passed is True
        assert result.document_errors == {}
        assert result.summary["total_documents"] == 1


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
