# -*- coding: utf-8 -*-
"""Tests fuer SEPADirectDebitService.

Testet SEPA-Lastschrift Verwaltung, Mandats-Handling und pain.008 Generierung.
"""

import pytest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.banking.sepa_direct_debit_service import (
    SEPADirectDebitService,
    DirectDebitType,
    MandateStatus,
    SequenceType,
    DirectDebitStatus,
    SEPAMandate,
    DirectDebitEntry,
    DirectDebitBatch,
    PreNotification,
    ReturnReasonCode,
    RETURN_REASON_LABELS,
    get_sepa_direct_debit_service,
)


class TestMandateManagement:
    """Tests fuer Mandats-Verwaltung."""

    @pytest.fixture
    def service(self) -> SEPADirectDebitService:
        """Erstellt SEPADirectDebitService Instanz."""
        return SEPADirectDebitService()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Mock fuer Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_create_mandate_core(
        self, service: SEPADirectDebitService, mock_db: AsyncMock
    ) -> None:
        """Test: CORE-Mandat erstellen."""
        company_id = uuid4()
        entity_id = uuid4()

        mandate = await service.create_mandate(
            db=mock_db,
            company_id=company_id,
            entity_id=entity_id,
            debtor_name="Max Mustermann GmbH",
            debtor_iban="DE89370400440532013000",
            debtor_bic="COBADEFFXXX",
            mandate_type=DirectDebitType.CORE,
            signature_date=date.today(),
        )

        assert mandate is not None
        assert mandate.company_id == company_id
        assert mandate.entity_id == entity_id
        assert mandate.mandate_type == DirectDebitType.CORE
        assert mandate.status == MandateStatus.PENDING
        assert "MNDT-" in mandate.mandate_reference

    @pytest.mark.asyncio
    async def test_create_mandate_b2b(
        self, service: SEPADirectDebitService, mock_db: AsyncMock
    ) -> None:
        """Test: B2B-Mandat erstellen."""
        mandate = await service.create_mandate(
            db=mock_db,
            company_id=uuid4(),
            entity_id=uuid4(),
            debtor_name="Business Partner AG",
            debtor_iban="DE89370400440532013000",
            debtor_bic="COBADEFFXXX",
            mandate_type=DirectDebitType.B2B,
            signature_date=date.today(),
        )

        assert mandate.mandate_type == DirectDebitType.B2B

    @pytest.mark.asyncio
    async def test_activate_mandate(
        self, service: SEPADirectDebitService, mock_db: AsyncMock
    ) -> None:
        """Test: Mandat aktivieren."""
        # Erstelle Test-Mandat
        mandate = SEPAMandate(
            id=uuid4(),
            company_id=uuid4(),
            entity_id=uuid4(),
            mandate_reference="MNDT-TEST-001",
            debtor_name="Test GmbH",
            debtor_iban="DE89370400440532013000",
            debtor_bic="COBADEFFXXX",
            mandate_type=DirectDebitType.CORE,
            signature_date=date.today(),
            status=MandateStatus.PENDING,
        )

        result = await service.activate_mandate(
            db=mock_db,
            mandate=mandate,
        )

        # Method returns the mandate, not a boolean
        assert result is not None
        assert mandate.status == MandateStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_revoke_mandate(
        self, service: SEPADirectDebitService, mock_db: AsyncMock
    ) -> None:
        """Test: Mandat widerrufen."""
        mandate = SEPAMandate(
            id=uuid4(),
            company_id=uuid4(),
            entity_id=uuid4(),
            mandate_reference="MNDT-TEST-002",
            debtor_name="Test GmbH",
            debtor_iban="DE89370400440532013000",
            debtor_bic="COBADEFFXXX",
            mandate_type=DirectDebitType.CORE,
            signature_date=date.today(),
            status=MandateStatus.ACTIVE,
        )

        result = await service.revoke_mandate(
            db=mock_db,
            mandate=mandate,
            reason="Kunde hat widerrufen",
        )

        # Method returns the mandate, not a boolean
        assert result is not None
        assert mandate.status == MandateStatus.REVOKED

    def test_mandate_reference_format(self, service: SEPADirectDebitService) -> None:
        """Test: Mandatsreferenz hat korrektes Format."""
        company_id = uuid4()
        entity_id = uuid4()
        ref = service._generate_mandate_reference(company_id, entity_id)

        assert "MNDT-" in ref
        assert len(ref) > 10

    def test_validate_iban_valid(self, service: SEPADirectDebitService) -> None:
        """Test: Gueltige IBAN wird akzeptiert."""
        valid_ibans = [
            "DE89370400440532013000",
            "DE89 3704 0044 0532 0130 00",  # Mit Leerzeichen
            "AT611904300234573201",
            "CH9300762011623852957",
        ]

        for iban in valid_ibans:
            assert service._validate_iban(iban) is True

    def test_validate_iban_invalid(self, service: SEPADirectDebitService) -> None:
        """Test: Ungueltige IBAN wird abgelehnt."""
        invalid_ibans = [
            "XX89370400440532013000",  # Ungueltiges Land
            "DE893704",  # Zu kurz
            "",  # Leer
        ]

        for iban in invalid_ibans:
            assert service._validate_iban(iban) is False


class TestDirectDebitCreation:
    """Tests fuer Lastschrift-Erstellung."""

    @pytest.fixture
    def service(self) -> SEPADirectDebitService:
        """Erstellt SEPADirectDebitService Instanz."""
        return SEPADirectDebitService()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Mock fuer Datenbank-Session."""
        return AsyncMock()

    @pytest.fixture
    def active_mandate(self) -> SEPAMandate:
        """Erstellt aktives Test-Mandat."""
        return SEPAMandate(
            id=uuid4(),
            company_id=uuid4(),
            entity_id=uuid4(),
            mandate_reference="MNDT-ACTIVE-001",
            debtor_name="Test Kunde GmbH",
            debtor_iban="DE89370400440532013000",
            debtor_bic="COBADEFFXXX",
            mandate_type=DirectDebitType.CORE,
            signature_date=date.today() - timedelta(days=30),
            status=MandateStatus.ACTIVE,
        )

    @pytest.mark.asyncio
    async def test_create_direct_debit(
        self, service: SEPADirectDebitService, mock_db: AsyncMock, active_mandate: SEPAMandate
    ) -> None:
        """Test: Lastschrift erstellen."""
        entry = await service.create_direct_debit(
            db=mock_db,
            mandate=active_mandate,
            amount=Decimal("100.00"),
            collection_date=date.today() + timedelta(days=14),
            remittance_info="Rechnung 12345",
        )

        assert entry is not None
        assert entry.amount == Decimal("100.00")
        assert entry.status == DirectDebitStatus.DRAFT

    @pytest.mark.asyncio
    async def test_create_direct_debit_first_collection(
        self, service: SEPADirectDebitService, mock_db: AsyncMock
    ) -> None:
        """Test: Erste Lastschrift hat FRST Sequence."""
        mandate = SEPAMandate(
            id=uuid4(),
            company_id=uuid4(),
            entity_id=uuid4(),
            mandate_reference="MNDT-FIRST-001",
            debtor_name="Neuer Kunde GmbH",
            debtor_iban="DE89370400440532013000",
            debtor_bic="COBADEFFXXX",
            mandate_type=DirectDebitType.CORE,
            signature_date=date.today(),
            status=MandateStatus.ACTIVE,
            last_collection_date=None,  # Erste Lastschrift
        )

        entry = await service.create_direct_debit(
            db=mock_db,
            mandate=mandate,
            amount=Decimal("50.00"),
            collection_date=date.today() + timedelta(days=14),
            remittance_info="Ersteinzug",
        )

        assert entry.sequence_type == SequenceType.FRST

    @pytest.mark.asyncio
    async def test_create_direct_debit_recurring(
        self, service: SEPADirectDebitService, mock_db: AsyncMock
    ) -> None:
        """Test: Folge-Lastschrift hat RCUR Sequence."""
        mandate = SEPAMandate(
            id=uuid4(),
            company_id=uuid4(),
            entity_id=uuid4(),
            mandate_reference="MNDT-RECUR-001",
            debtor_name="Bestandskunde GmbH",
            debtor_iban="DE89370400440532013000",
            debtor_bic="COBADEFFXXX",
            mandate_type=DirectDebitType.CORE,
            signature_date=date.today() - timedelta(days=90),
            status=MandateStatus.ACTIVE,
            collection_count=5,  # Not first collection - needs collection_count > 0
        )

        entry = await service.create_direct_debit(
            db=mock_db,
            mandate=mandate,
            amount=Decimal("75.00"),
            collection_date=date.today() + timedelta(days=14),
            remittance_info="Folgeeinzug",
        )

        assert entry.sequence_type == SequenceType.RCUR

    @pytest.mark.asyncio
    async def test_create_direct_debit_inactive_mandate_fails(
        self, service: SEPADirectDebitService, mock_db: AsyncMock
    ) -> None:
        """Test: Lastschrift mit inaktivem Mandat schlaegt fehl."""
        mandate = SEPAMandate(
            id=uuid4(),
            company_id=uuid4(),
            entity_id=uuid4(),
            mandate_reference="MNDT-REVOKED-001",
            debtor_name="Inaktiv GmbH",
            debtor_iban="DE89370400440532013000",
            debtor_bic="COBADEFFXXX",
            mandate_type=DirectDebitType.CORE,
            signature_date=date.today() - timedelta(days=90),
            status=MandateStatus.REVOKED,  # Nicht aktiv!
        )

        with pytest.raises(ValueError, match="nicht aktiv"):
            await service.create_direct_debit(
                db=mock_db,
                mandate=mandate,
                amount=Decimal("100.00"),
                collection_date=date.today() + timedelta(days=14),
                remittance_info="Test",
            )


class TestBatchProcessing:
    """Tests fuer Batch-Verarbeitung."""

    @pytest.fixture
    def service(self) -> SEPADirectDebitService:
        """Erstellt SEPADirectDebitService Instanz."""
        return SEPADirectDebitService()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Mock fuer Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_create_batch(
        self, service: SEPADirectDebitService, mock_db: AsyncMock
    ) -> None:
        """Test: Batch erstellen."""
        company_id = uuid4()

        batch = await service.create_batch(
            db=mock_db,
            company_id=company_id,
            name="Test-Batch Januar",
            collection_date=date.today() + timedelta(days=14),
            creditor_name="Meine Firma GmbH",
            creditor_iban="DE89370400440532013999",
            creditor_id="DE98ZZZ09999999999",
            creditor_bic="COBADEFFXXX",
        )

        assert batch is not None
        assert batch.company_id == company_id
        assert batch.name == "Test-Batch Januar"

    def test_batch_dataclass(self) -> None:
        """Test: Batch-Datenstruktur ist korrekt."""
        company_id = uuid4()
        batch = DirectDebitBatch(
            id=uuid4(),
            company_id=company_id,
            name="Test-Batch",
            creation_date=date.today(),
            requested_collection_date=date.today() + timedelta(days=14),
            debit_type=DirectDebitType.CORE,
            sequence_type=SequenceType.FRST,
            entry_count=3,
            total_amount=Decimal("300.00"),
        )

        assert batch.entry_count == 3
        assert batch.total_amount == Decimal("300.00")


class TestPreNotification:
    """Tests fuer Pre-Notification (Vorabinformation)."""

    @pytest.fixture
    def service(self) -> SEPADirectDebitService:
        """Erstellt SEPADirectDebitService Instanz."""
        return SEPADirectDebitService()

    @pytest.mark.asyncio
    async def test_generate_pre_notifications(
        self, service: SEPADirectDebitService
    ) -> None:
        """Test: Vorabinformationen generieren."""
        company_id = uuid4()
        mandate_id = uuid4()

        mandate = SEPAMandate(
            id=mandate_id,
            company_id=company_id,
            entity_id=uuid4(),
            mandate_reference="MNDT-PRE-001",
            debtor_name="Vorab GmbH",
            debtor_iban="DE89370400440532013000",
            debtor_bic="COBADEFFXXX",
            mandate_type=DirectDebitType.CORE,
            signature_date=date.today() - timedelta(days=30),
            status=MandateStatus.ACTIVE,
        )

        entry = DirectDebitEntry(
            id=uuid4(),
            company_id=company_id,
            mandate_id=mandate_id,
            amount=Decimal("150.00"),
            end_to_end_id="E2E-PRE-001",
            requested_collection_date=date.today() + timedelta(days=14),
            remittance_info="Rechnung 12345",
        )

        batch = DirectDebitBatch(
            id=uuid4(),
            company_id=company_id,
            name="Pre-Test-Batch",
            creation_date=date.today(),
            requested_collection_date=date.today() + timedelta(days=14),
            debit_type=DirectDebitType.CORE,
            sequence_type=SequenceType.FRST,
            entries=[entry],
        )

        prenotifications = await service.generate_pre_notifications(
            batch=batch,
            mandates={mandate_id: mandate},
        )

        assert len(prenotifications) == 1
        assert prenotifications[0].amount == Decimal("150.00")
        assert prenotifications[0].mandate_id == mandate_id

    def test_prenotification_days_calculation(
        self, service: SEPADirectDebitService
    ) -> None:
        """Test: Pre-Notification Tage werden korrekt berechnet."""
        collection_date = date.today() + timedelta(days=14)

        # Standard: 14 Tage vor Einzug
        prenotification_date = collection_date - timedelta(
            days=service.MIN_PRENOTIFICATION_DAYS
        )

        assert prenotification_date == date.today()


class TestRTransactionHandling:
    """Tests fuer R-Transaktionen (Ruecklastschriften)."""

    @pytest.fixture
    def service(self) -> SEPADirectDebitService:
        """Erstellt SEPADirectDebitService Instanz."""
        return SEPADirectDebitService()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Mock fuer Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_process_return_ac01(
        self, service: SEPADirectDebitService
    ) -> None:
        """Test: Ruecklastschrift AC01 (Konto falsch) verarbeiten."""
        entry = DirectDebitEntry(
            id=uuid4(),
            company_id=uuid4(),
            mandate_id=uuid4(),
            amount=Decimal("100.00"),
            end_to_end_id="E2E-RETURN-001",
            requested_collection_date=date.today() - timedelta(days=5),
            status=DirectDebitStatus.SUBMITTED,
        )

        updated_entry = await service.process_return(
            entry=entry,
            reason_code=ReturnReasonCode.AC01,
            return_date=date.today(),
        )

        assert updated_entry is not None
        assert updated_entry.return_reason == ReturnReasonCode.AC01
        assert updated_entry.status == DirectDebitStatus.RETURNED

    @pytest.mark.asyncio
    async def test_process_return_md01(
        self, service: SEPADirectDebitService
    ) -> None:
        """Test: Ruecklastschrift MD01 (kein Mandat) verarbeiten."""
        entry = DirectDebitEntry(
            id=uuid4(),
            company_id=uuid4(),
            mandate_id=uuid4(),
            amount=Decimal("200.00"),
            end_to_end_id="E2E-RETURN-002",
            requested_collection_date=date.today() - timedelta(days=3),
            status=DirectDebitStatus.SUBMITTED,
        )

        updated_entry = await service.process_return(
            entry=entry,
            reason_code=ReturnReasonCode.MD01,
            return_date=date.today(),
        )

        assert updated_entry.return_reason == ReturnReasonCode.MD01

    def test_return_code_descriptions(self) -> None:
        """Test: Return-Code Beschreibungen sind vorhanden."""
        # RETURN_REASON_LABELS is a module-level dict
        assert "AC01" in RETURN_REASON_LABELS
        assert "MD01" in RETURN_REASON_LABELS
        assert "AM04" in RETURN_REASON_LABELS
        assert "MS02" in RETURN_REASON_LABELS
        assert "MS03" in RETURN_REASON_LABELS


class TestPain008Generation:
    """Tests fuer pain.008 XML-Generierung."""

    @pytest.fixture
    def service(self) -> SEPADirectDebitService:
        """Erstellt SEPADirectDebitService Instanz."""
        return SEPADirectDebitService()

    @pytest.mark.asyncio
    async def test_generate_pain008_xml_structure(
        self, service: SEPADirectDebitService
    ) -> None:
        """Test: pain.008 XML hat korrekte Struktur."""
        company_id = uuid4()

        # Erstelle Test-Batch
        mandate1 = SEPAMandate(
            id=uuid4(),
            company_id=company_id,
            entity_id=uuid4(),
            mandate_reference="MNDT-XML-001",
            debtor_name="Kunde A GmbH",
            debtor_iban="DE89370400440532013000",
            debtor_bic="COBADEFFXXX",
            mandate_type=DirectDebitType.CORE,
            signature_date=date(2026, 1, 1),
            status=MandateStatus.ACTIVE,
        )

        entry1 = DirectDebitEntry(
            id=uuid4(),
            company_id=company_id,
            mandate_id=mandate1.id,
            amount=Decimal("200.00"),
            end_to_end_id="E2E-XML-001",
            requested_collection_date=date.today() + timedelta(days=14),
            remittance_info="Rechnung 001",
            sequence_type=SequenceType.FRST,
        )

        batch = DirectDebitBatch(
            id=uuid4(),
            company_id=company_id,
            name="XML-Test-Batch",
            creation_date=date.today(),
            requested_collection_date=date.today() + timedelta(days=14),
            debit_type=DirectDebitType.CORE,
            sequence_type=SequenceType.FRST,
            entry_count=1,
            total_amount=Decimal("200.00"),
            creditor_name="Meine Firma GmbH",
            creditor_iban="DE89370400440532013999",
            creditor_bic="COBADEFFXXX",
            creditor_id="DE98ZZZ09999999999",
            entries=[entry1],
        )

        xml_content = await service.generate_pain008_xml(
            batch=batch,
            mandates={mandate1.id: mandate1},
        )

        assert xml_content is not None
        assert "<?xml" in xml_content
        assert "pain.008" in xml_content
        assert "CstmrDrctDbtInitn" in xml_content
        assert "PmtInf" in xml_content


class TestStatistics:
    """Tests fuer Statistiken."""

    @pytest.fixture
    def service(self) -> SEPADirectDebitService:
        """Erstellt SEPADirectDebitService Instanz."""
        return SEPADirectDebitService()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Mock fuer Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_get_statistics(
        self, service: SEPADirectDebitService, mock_db: AsyncMock
    ) -> None:
        """Test: Statistiken abrufen."""
        company_id = uuid4()

        # Create test entries
        entries = [
            DirectDebitEntry(
                id=uuid4(),
                company_id=company_id,
                mandate_id=uuid4(),
                amount=Decimal("100.00"),
                end_to_end_id="E2E-STAT-001",
                requested_collection_date=date.today() - timedelta(days=10),
                status=DirectDebitStatus.BOOKED,
            ),
            DirectDebitEntry(
                id=uuid4(),
                company_id=company_id,
                mandate_id=uuid4(),
                amount=Decimal("150.00"),
                end_to_end_id="E2E-STAT-002",
                requested_collection_date=date.today() - timedelta(days=5),
                status=DirectDebitStatus.BOOKED,
            ),
        ]

        stats = await service.get_statistics(
            db=mock_db,
            company_id=company_id,
            entries=entries,
            period_start=date.today() - timedelta(days=30),
            period_end=date.today(),
        )

        assert stats is not None
        assert stats.company_id == company_id
        assert stats.total_collections == 2
        assert stats.total_amount == Decimal("250.00")


class TestSingleton:
    """Tests fuer Singleton-Pattern."""

    def test_singleton_instance(self) -> None:
        """Test: Singleton gibt immer gleiche Instanz zurueck."""
        service1 = get_sepa_direct_debit_service()
        service2 = get_sepa_direct_debit_service()

        assert service1 is service2

    def test_service_has_required_methods(self) -> None:
        """Test: Service hat alle erforderlichen Methoden."""
        service = get_sepa_direct_debit_service()

        assert hasattr(service, "create_mandate")
        assert hasattr(service, "activate_mandate")
        assert hasattr(service, "create_direct_debit")
        assert hasattr(service, "create_batch")
        assert hasattr(service, "generate_pain008_xml")
        assert hasattr(service, "process_return")
        assert hasattr(service, "get_statistics")
