# -*- coding: utf-8 -*-
"""
Tests fuer PaymentService.

Testet:
- Zahlungserstellung
- IBAN/BIC-Validierung
- Workflow (Draft -> Approved -> Submitted -> Confirmed)
- Stornierung
- Skonto-Erkennung
"""

import pytest
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from uuid import uuid4, UUID
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.banking.payment_service import (
    PaymentService,
    PaymentValidationResult,
)
from app.services.banking.models import (
    PaymentStatus,
    PaymentType,
    PaymentOrderCreate,
)


def create_mock_payment(
    payment_id: UUID = None,
    user_id: UUID = None,
    status: str = PaymentStatus.DRAFT.value,
    **overrides
) -> MagicMock:
    """Erstelle vollstaendiges Mock-PaymentOrder Objekt.

    Alle Felder die PaymentOrderResponse benoetigt werden gesetzt.
    """
    now = datetime.now(timezone.utc)
    mock = MagicMock()
    mock.id = payment_id or uuid4()
    mock.user_id = user_id or uuid4()
    mock.bank_account_id = overrides.get("bank_account_id", uuid4())
    mock.document_id = overrides.get("document_id", None)
    mock.invoice_number = overrides.get("invoice_number", None)
    mock.payment_type = overrides.get("payment_type", PaymentType.TRANSFER.value)
    mock.sepa_type = overrides.get("sepa_type", None)
    mock.status = status
    mock.beneficiary_name = overrides.get("beneficiary_name", "Test GmbH")
    mock.beneficiary_iban = overrides.get("beneficiary_iban", "DE89370400440532013000")
    mock.beneficiary_bic = overrides.get("beneficiary_bic", None)
    mock.amount = overrides.get("amount", Decimal("100.00"))
    mock.currency = overrides.get("currency", "EUR")
    mock.reference = overrides.get("reference", "Test-Zahlung")
    mock.execution_date = overrides.get("execution_date", None)
    mock.tan_required = overrides.get("tan_required", False)
    mock.tan_attempts = overrides.get("tan_attempts", 0)
    mock.uses_skonto = overrides.get("uses_skonto", False)
    mock.skonto_amount = overrides.get("skonto_amount", None)
    mock.original_amount = overrides.get("original_amount", None)
    mock.skonto_deadline = overrides.get("skonto_deadline", None)
    mock.bank_reference = overrides.get("bank_reference", None)
    mock.approved_at = overrides.get("approved_at", None)
    mock.submitted_at = overrides.get("submitted_at", None)
    mock.created_at = overrides.get("created_at", now)
    mock.updated_at = overrides.get("updated_at", now)
    return mock


class TestIBANValidation:
    """Tests fuer IBAN-Validierung."""

    @pytest.fixture
    def service(self) -> PaymentService:
        return PaymentService()

    def test_normalize_iban(self, service: PaymentService):
        """Sollte IBAN normalisieren."""
        assert service._normalize_iban("DE89 3704 0044 0532 0130 00") == "DE89370400440532013000"
        assert service._normalize_iban("de89370400440532013000") == "DE89370400440532013000"

    def test_validate_iban_checksum_valid(self, service: PaymentService):
        """Sollte gueltige IBAN akzeptieren."""
        # Bekannte gueltige IBANs
        valid_ibans = [
            "DE89370400440532013000",
            "AT611904300234573201",
            "CH9300762011623852957",
        ]
        for iban in valid_ibans:
            assert service._validate_iban_checksum(iban), f"IBAN sollte gueltig sein: {iban}"

    def test_validate_iban_checksum_invalid(self, service: PaymentService):
        """Sollte ungueltige IBAN ablehnen."""
        invalid_ibans = [
            "DE89370400440532013001",  # Falsche Pruefziffer
            "DE00370400440532013000",  # Pruefziffer 00
            "INVALID",
        ]
        for iban in invalid_ibans:
            assert not service._validate_iban_checksum(iban), f"IBAN sollte ungueltig sein: {iban}"


class TestPaymentValidation:
    """Tests fuer Zahlungsvalidierung."""

    @pytest.fixture
    def service(self) -> PaymentService:
        return PaymentService()

    def test_validate_payment_success(self, service: PaymentService):
        """Sollte gueltige Zahlung akzeptieren."""
        data = PaymentOrderCreate(
            bank_account_id=uuid4(),
            beneficiary_name="Test GmbH",
            beneficiary_iban="DE89370400440532013000",
            amount=Decimal("100.00"),
            reference="Rechnung 2024-001",
        )

        result = service._validate_payment(data)

        assert result.valid
        assert len(result.errors) == 0

    def test_validate_payment_invalid_iban_checksum(self, service: PaymentService):
        """Sollte IBAN mit falscher Pruefziffer ablehnen."""
        # Diese IBAN hat eine falsche Pruefziffer (endet auf 01 statt 00)
        data = PaymentOrderCreate(
            bank_account_id=uuid4(),
            beneficiary_name="Test GmbH",
            beneficiary_iban="DE89370400440532013001",  # Falsche Pruefziffer
            amount=Decimal("100.00"),
        )

        result = service._validate_payment(data)

        assert not result.valid
        assert any("Pruefziffer" in e for e in result.errors)

    def test_validate_payment_large_amount_warning(self, service: PaymentService):
        """Sollte Warnung bei grossem Betrag ausgeben."""
        data = PaymentOrderCreate(
            bank_account_id=uuid4(),
            beneficiary_name="Test GmbH",
            beneficiary_iban="DE89370400440532013000",
            amount=Decimal("60000.00"),  # Ueber MAX_SINGLE_PAYMENT
            reference="Grosser Transfer",
        )

        result = service._validate_payment(data)

        # Sollte valide sein, aber mit Warnung
        assert result.valid
        assert len(result.warnings) > 0

    def test_validate_payment_past_date(self, service: PaymentService):
        """Sollte vergangenes Datum ablehnen."""
        data = PaymentOrderCreate(
            bank_account_id=uuid4(),
            beneficiary_name="Test GmbH",
            beneficiary_iban="DE89370400440532013000",
            amount=Decimal("100.00"),
            reference="Test",
            execution_date=date.today() - timedelta(days=1),
        )

        result = service._validate_payment(data)

        assert not result.valid
        assert any("Vergangenheit" in e for e in result.errors)


class TestEndToEndIDGeneration:
    """Tests fuer End-to-End-ID-Generierung."""

    @pytest.fixture
    def service(self) -> PaymentService:
        return PaymentService()

    def test_generate_end_to_end_id_format(self, service: PaymentService):
        """Sollte korrektes Format haben."""
        e2e_id = service._generate_end_to_end_id()

        assert e2e_id.startswith("E2E")
        assert len(e2e_id) > 10

    def test_generate_end_to_end_id_unique(self, service: PaymentService):
        """Sollte eindeutige IDs generieren."""
        ids = [service._generate_end_to_end_id() for _ in range(100)]
        assert len(ids) == len(set(ids))


class TestBankReferenceGeneration:
    """Tests fuer Bank-Referenznummer-Generierung."""

    @pytest.fixture
    def service(self) -> PaymentService:
        return PaymentService()

    def test_generate_bank_reference_format(self, service: PaymentService):
        """Sollte korrektes Format haben."""
        ref = service._generate_bank_reference()

        assert ref.startswith("REF")
        assert len(ref) > 10


class TestTANValidation:
    """Tests fuer TAN-Validierung."""

    @pytest.fixture
    def service(self) -> PaymentService:
        return PaymentService()

    def test_validate_tan_valid(self, service: PaymentService):
        """Sollte gueltige TAN akzeptieren."""
        assert service._validate_tan("123456")

    def test_validate_tan_too_short(self, service: PaymentService):
        """Sollte zu kurze TAN ablehnen."""
        assert not service._validate_tan("12345")

    def test_validate_tan_too_long(self, service: PaymentService):
        """Sollte zu lange TAN ablehnen."""
        assert not service._validate_tan("1234567")

    def test_validate_tan_non_numeric(self, service: PaymentService):
        """Sollte nicht-numerische TAN ablehnen."""
        assert not service._validate_tan("12345a")

    def test_validate_tan_empty(self, service: PaymentService):
        """Sollte leere TAN ablehnen."""
        assert not service._validate_tan("")
        assert not service._validate_tan(None)


class TestPaymentServiceWithMockedDB:
    """Tests mit gemockter Datenbank."""

    @pytest.fixture
    def service(self) -> PaymentService:
        return PaymentService()

    @pytest.fixture
    def mock_db(self):
        """Mockt AsyncSession."""
        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()
        return db

    @pytest.mark.asyncio
    async def test_get_payment_not_found(
        self, service: PaymentService, mock_db
    ):
        """Sollte None zurueckgeben wenn Zahlung nicht gefunden."""
        user_id = uuid4()
        payment_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.get_payment(mock_db, user_id, payment_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_approve_payment_wrong_status(
        self, service: PaymentService, mock_db
    ):
        """Sollte Fehler werfen wenn Status nicht 'draft' ist."""
        user_id = uuid4()
        payment_id = uuid4()

        mock_payment = MagicMock()
        mock_payment.status = PaymentStatus.APPROVED.value

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_payment
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="kann nicht genehmigt"):
            await service.approve_payment(mock_db, user_id, payment_id)

    @pytest.mark.asyncio
    async def test_cancel_payment_wrong_status(
        self, service: PaymentService, mock_db
    ):
        """Sollte Fehler werfen wenn Status nicht stornierbar ist."""
        user_id = uuid4()
        payment_id = uuid4()

        mock_payment = MagicMock()
        mock_payment.status = PaymentStatus.CONFIRMED.value

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_payment
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="kann nicht storniert"):
            await service.cancel_payment(mock_db, user_id, payment_id)

    @pytest.mark.asyncio
    async def test_submit_payment_not_approved(
        self, service: PaymentService, mock_db
    ):
        """Sollte Fehler werfen wenn Zahlung nicht genehmigt ist."""
        user_id = uuid4()
        payment_id = uuid4()

        mock_payment = MagicMock()
        mock_payment.status = PaymentStatus.DRAFT.value

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_payment
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="muss genehmigt"):
            await service.submit_payment(mock_db, user_id, payment_id)


class TestPaymentServiceThresholds:
    """Tests fuer Schwellenwerte."""

    @pytest.fixture
    def service(self) -> PaymentService:
        return PaymentService()

    def test_max_single_payment(self, service: PaymentService):
        """Sollte korrekten Max-Einzelbetrag haben."""
        assert service.MAX_SINGLE_PAYMENT == Decimal("50000.00")

    def test_max_batch_total(self, service: PaymentService):
        """Sollte korrekten Max-Batch-Betrag haben."""
        assert service.MAX_BATCH_TOTAL == Decimal("100000.00")


class TestTANWorkflow:
    """Tests fuer TAN-Workflow (Submit → TAN → Confirm)."""

    @pytest.fixture
    def service(self) -> PaymentService:
        return PaymentService()

    @pytest.fixture
    def mock_db(self):
        """Mockt AsyncSession."""
        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @pytest.fixture
    def sample_user_id(self):
        return uuid4()

    @pytest.fixture
    def sample_payment_id(self):
        return uuid4()

    @pytest.mark.asyncio
    async def test_submit_payment_success(
        self, service: PaymentService, mock_db, sample_user_id, sample_payment_id
    ):
        """Sollte Zahlung erfolgreich zur Bank senden."""
        mock_payment = MagicMock()
        mock_payment.id = sample_payment_id
        mock_payment.status = PaymentStatus.APPROVED.value
        mock_payment.amount = Decimal("100.00")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_payment
        mock_db.execute.return_value = mock_result

        result = await service.submit_payment(mock_db, sample_user_id, sample_payment_id)

        assert "payment_id" in result
        assert result["tan_required"] is True
        assert "expires_at" in result
        assert mock_payment.status == PaymentStatus.PENDING_TAN.value
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_payment_not_found(
        self, service: PaymentService, mock_db, sample_user_id, sample_payment_id
    ):
        """Sollte Fehler werfen wenn Zahlung nicht gefunden."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="nicht gefunden"):
            await service.submit_payment(mock_db, sample_user_id, sample_payment_id)

    @pytest.mark.asyncio
    async def test_confirm_with_tan_success(
        self, service: PaymentService, mock_db, sample_user_id, sample_payment_id
    ):
        """Sollte Zahlung mit gueltiger TAN bestaetigen."""
        mock_payment = create_mock_payment(
            payment_id=sample_payment_id,
            user_id=sample_user_id,
            status=PaymentStatus.PENDING_TAN.value,
            tan_attempts=0,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_payment
        mock_db.execute.return_value = mock_result

        result = await service.confirm_with_tan(
            mock_db, sample_user_id, sample_payment_id, "123456"
        )

        assert mock_payment.status == PaymentStatus.CONFIRMED.value
        assert mock_payment.bank_reference is not None
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_confirm_with_tan_invalid_tan(
        self, service: PaymentService, mock_db, sample_user_id, sample_payment_id
    ):
        """Sollte Fehler bei ungueltiger TAN werfen."""
        mock_payment = MagicMock()
        mock_payment.id = sample_payment_id
        mock_payment.status = PaymentStatus.PENDING_TAN.value
        mock_payment.tan_attempts = 0

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_payment
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="Ungueltige TAN"):
            await service.confirm_with_tan(
                mock_db, sample_user_id, sample_payment_id, "12345"  # Zu kurz
            )

        assert mock_payment.tan_attempts == 1

    @pytest.mark.asyncio
    async def test_confirm_with_tan_max_attempts_exceeded(
        self, service: PaymentService, mock_db, sample_user_id, sample_payment_id
    ):
        """Sollte Zahlung nach 3 TAN-Versuchen ablehnen."""
        mock_payment = MagicMock()
        mock_payment.id = sample_payment_id
        mock_payment.status = PaymentStatus.PENDING_TAN.value
        mock_payment.tan_attempts = 2  # Bereits 2 Versuche

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_payment
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="Maximale TAN-Versuche"):
            await service.confirm_with_tan(
                mock_db, sample_user_id, sample_payment_id, "wrong1"  # 3. Versuch
            )

        assert mock_payment.status == PaymentStatus.REJECTED.value

    @pytest.mark.asyncio
    async def test_confirm_with_tan_wrong_status(
        self, service: PaymentService, mock_db, sample_user_id, sample_payment_id
    ):
        """Sollte Fehler werfen wenn Status nicht PENDING_TAN ist."""
        mock_payment = MagicMock()
        mock_payment.id = sample_payment_id
        mock_payment.status = PaymentStatus.DRAFT.value

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_payment
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="wartet nicht auf TAN"):
            await service.confirm_with_tan(
                mock_db, sample_user_id, sample_payment_id, "123456"
            )


class TestBatchPayments:
    """Tests fuer Sammelzahlungen (Batches)."""

    @pytest.fixture
    def service(self) -> PaymentService:
        return PaymentService()

    @pytest.fixture
    def mock_db(self):
        """Mockt AsyncSession."""
        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()
        return db

    @pytest.fixture
    def sample_user_id(self):
        return uuid4()

    @pytest.fixture
    def sample_account_id(self):
        return uuid4()

    @pytest.fixture
    def sample_payments(self):
        """Erstelle Beispiel-Zahlungen fuer Batch."""
        return [
            PaymentOrderCreate(
                bank_account_id=uuid4(),
                beneficiary_name="Lieferant A",
                beneficiary_iban="DE89370400440532013000",
                amount=Decimal("1000.00"),
                reference="Rechnung A-001",
            ),
            PaymentOrderCreate(
                bank_account_id=uuid4(),
                beneficiary_name="Lieferant B",
                beneficiary_iban="AT611904300234573201",
                amount=Decimal("500.00"),
                reference="Rechnung B-002",
            ),
        ]

    @pytest.mark.asyncio
    async def test_create_batch_success(
        self,
        service: PaymentService,
        mock_db,
        sample_user_id,
        sample_account_id,
        sample_payments,
    ):
        """Sollte Batch erfolgreich erstellen."""
        mock_account = MagicMock()
        mock_account.id = sample_account_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_account
        mock_db.execute.return_value = mock_result

        result = await service.create_batch(
            mock_db,
            sample_user_id,
            sample_account_id,
            "Dezember Rechnungen",
            sample_payments,
        )

        assert result["payment_count"] == 2
        assert result["total_amount"] == 1500.00
        assert result["status"] == PaymentStatus.DRAFT.value
        assert "batch_id" in result
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_batch_account_not_found(
        self,
        service: PaymentService,
        mock_db,
        sample_user_id,
        sample_account_id,
        sample_payments,
    ):
        """Sollte Fehler werfen wenn Bankkonto nicht gefunden."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="Bankkonto nicht gefunden"):
            await service.create_batch(
                mock_db,
                sample_user_id,
                sample_account_id,
                "Test Batch",
                sample_payments,
            )

    @pytest.mark.asyncio
    async def test_create_batch_exceeds_max_total(
        self,
        service: PaymentService,
        mock_db,
        sample_user_id,
        sample_account_id,
    ):
        """Sollte Fehler werfen wenn Batch-Gesamtbetrag zu hoch."""
        mock_account = MagicMock()
        mock_account.id = sample_account_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_account
        mock_db.execute.return_value = mock_result

        large_payments = [
            PaymentOrderCreate(
                bank_account_id=uuid4(),
                beneficiary_name=f"Lieferant {i}",
                beneficiary_iban="DE89370400440532013000",
                amount=Decimal("40000.00"),  # 3 * 40000 = 120000 > 100000
                reference=f"Rechnung {i}",
            )
            for i in range(3)
        ]

        with pytest.raises(ValueError, match="ueberschreitet Maximum"):
            await service.create_batch(
                mock_db,
                sample_user_id,
                sample_account_id,
                "Grosser Batch",
                large_payments,
            )

    @pytest.mark.asyncio
    async def test_create_batch_validation_errors(
        self,
        service: PaymentService,
        mock_db,
        sample_user_id,
        sample_account_id,
    ):
        """Sollte Validierungsfehler sammeln."""
        mock_account = MagicMock()
        mock_account.id = sample_account_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_account
        mock_db.execute.return_value = mock_result

        invalid_payments = [
            PaymentOrderCreate(
                bank_account_id=uuid4(),
                beneficiary_name="Test",
                beneficiary_iban="DE00000000000000000",  # Ungueltig (falsche Pruefziffer)
                amount=Decimal("100.00"),
            ),
        ]

        with pytest.raises(ValueError, match="Validierungsfehler"):
            await service.create_batch(
                mock_db,
                sample_user_id,
                sample_account_id,
                "Fehlerhafter Batch",
                invalid_payments,
            )


class TestSkontoOpportunities:
    """Tests fuer Skonto-Erkennung."""

    @pytest.fixture
    def service(self) -> PaymentService:
        return PaymentService()

    @pytest.fixture
    def mock_db(self):
        """Mockt AsyncSession."""
        db = AsyncMock()
        db.execute = AsyncMock()
        return db

    @pytest.fixture
    def sample_user_id(self):
        return uuid4()

    @pytest.mark.asyncio
    async def test_get_skonto_opportunities_with_valid_documents(
        self, service: PaymentService, mock_db, sample_user_id
    ):
        """Sollte Skonto-Moeglichkeiten finden."""
        today = date.today()
        skonto_date = today + timedelta(days=5)

        mock_doc = MagicMock()
        mock_doc.id = uuid4()
        mock_doc.extracted_data = {
            "invoice_number": "RE-2024-001",
            "sender": {"name": "Test GmbH"},
            "amounts": {"gross": 1000.00},
            "payment_terms": {
                "skonto": {
                    "date": skonto_date.isoformat(),
                    "percent": 2.0,
                }
            },
        }

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_doc]
        mock_db.execute.return_value = mock_result

        opportunities = await service.get_skonto_opportunities(
            mock_db, sample_user_id, days_ahead=14
        )

        assert len(opportunities) == 1
        assert opportunities[0]["skonto_percent"] == 2.0
        assert opportunities[0]["potential_savings"] == 20.0
        assert opportunities[0]["days_remaining"] == 5

    @pytest.mark.asyncio
    async def test_get_skonto_opportunities_expired(
        self, service: PaymentService, mock_db, sample_user_id
    ):
        """Sollte abgelaufenes Skonto nicht anzeigen."""
        yesterday = date.today() - timedelta(days=1)

        mock_doc = MagicMock()
        mock_doc.id = uuid4()
        mock_doc.extracted_data = {
            "invoice_number": "RE-2024-001",
            "amounts": {"gross": 1000.00},
            "payment_terms": {
                "skonto": {
                    "date": yesterday.isoformat(),
                    "percent": 2.0,
                }
            },
        }

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_doc]
        mock_db.execute.return_value = mock_result

        opportunities = await service.get_skonto_opportunities(
            mock_db, sample_user_id, days_ahead=14
        )

        assert len(opportunities) == 0

    @pytest.mark.asyncio
    async def test_get_skonto_opportunities_no_skonto(
        self, service: PaymentService, mock_db, sample_user_id
    ):
        """Sollte Dokumente ohne Skonto ignorieren."""
        mock_doc = MagicMock()
        mock_doc.id = uuid4()
        mock_doc.extracted_data = {
            "invoice_number": "RE-2024-001",
            "amounts": {"gross": 1000.00},
            "payment_terms": {},  # Kein Skonto
        }

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_doc]
        mock_db.execute.return_value = mock_result

        opportunities = await service.get_skonto_opportunities(
            mock_db, sample_user_id, days_ahead=14
        )

        assert len(opportunities) == 0


class TestPendingPayments:
    """Tests fuer ausstehende Zahlungen."""

    @pytest.fixture
    def service(self) -> PaymentService:
        return PaymentService()

    @pytest.fixture
    def mock_db(self):
        """Mockt AsyncSession."""
        db = AsyncMock()
        db.execute = AsyncMock()
        return db

    @pytest.fixture
    def sample_user_id(self):
        return uuid4()

    @pytest.mark.asyncio
    async def test_get_pending_payments_multiple_statuses(
        self, service: PaymentService, mock_db, sample_user_id
    ):
        """Sollte Zahlungen mit verschiedenen ausstehenden Status zurueckgeben."""
        mock_payments = []
        for i, status in enumerate([
            PaymentStatus.DRAFT.value,
            PaymentStatus.APPROVED.value,
            PaymentStatus.PENDING_TAN.value,
        ]):
            mock_payment = create_mock_payment(
                user_id=sample_user_id,
                status=status,
                beneficiary_name=f"Test {i}",
                reference=f"Test {i}",
            )
            mock_payments.append(mock_payment)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_payments
        mock_db.execute.return_value = mock_result

        results = await service.get_pending_payments(mock_db, sample_user_id)

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_get_pending_payments_empty(
        self, service: PaymentService, mock_db, sample_user_id
    ):
        """Sollte leere Liste zurueckgeben wenn keine ausstehenden Zahlungen."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        results = await service.get_pending_payments(mock_db, sample_user_id)

        assert len(results) == 0


class TestPaymentApproval:
    """Tests fuer Zahlungsgenehmigung."""

    @pytest.fixture
    def service(self) -> PaymentService:
        return PaymentService()

    @pytest.fixture
    def mock_db(self):
        """Mockt AsyncSession."""
        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        return db

    @pytest.fixture
    def sample_user_id(self):
        return uuid4()

    @pytest.fixture
    def sample_payment_id(self):
        return uuid4()

    @pytest.mark.asyncio
    async def test_approve_payment_success(
        self, service: PaymentService, mock_db, sample_user_id, sample_payment_id
    ):
        """Sollte Zahlung erfolgreich genehmigen."""
        mock_payment = create_mock_payment(
            payment_id=sample_payment_id,
            user_id=sample_user_id,
            status=PaymentStatus.DRAFT.value,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_payment
        mock_db.execute.return_value = mock_result

        result = await service.approve_payment(mock_db, sample_user_id, sample_payment_id)

        assert mock_payment.status == PaymentStatus.APPROVED.value
        assert mock_payment.approved_at is not None
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_approve_payment_not_found(
        self, service: PaymentService, mock_db, sample_user_id, sample_payment_id
    ):
        """Sollte Fehler werfen wenn Zahlung nicht gefunden."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="nicht gefunden"):
            await service.approve_payment(mock_db, sample_user_id, sample_payment_id)


class TestPaymentCancellation:
    """Tests fuer Zahlungsstornierung."""

    @pytest.fixture
    def service(self) -> PaymentService:
        return PaymentService()

    @pytest.fixture
    def mock_db(self):
        """Mockt AsyncSession."""
        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        return db

    @pytest.fixture
    def sample_user_id(self):
        return uuid4()

    @pytest.fixture
    def sample_payment_id(self):
        return uuid4()

    @pytest.mark.asyncio
    async def test_cancel_payment_from_draft(
        self, service: PaymentService, mock_db, sample_user_id, sample_payment_id
    ):
        """Sollte Draft-Zahlung stornieren koennen."""
        mock_payment = create_mock_payment(
            payment_id=sample_payment_id,
            user_id=sample_user_id,
            status=PaymentStatus.DRAFT.value,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_payment
        mock_db.execute.return_value = mock_result

        result = await service.cancel_payment(
            mock_db, sample_user_id, sample_payment_id, "Nicht mehr benoetigt"
        )

        assert mock_payment.status == PaymentStatus.CANCELLED.value
        assert mock_payment.error_message == "Nicht mehr benoetigt"
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_payment_from_pending_tan(
        self, service: PaymentService, mock_db, sample_user_id, sample_payment_id
    ):
        """Sollte PENDING_TAN-Zahlung stornieren koennen."""
        mock_payment = create_mock_payment(
            payment_id=sample_payment_id,
            user_id=sample_user_id,
            status=PaymentStatus.PENDING_TAN.value,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_payment
        mock_db.execute.return_value = mock_result

        result = await service.cancel_payment(mock_db, sample_user_id, sample_payment_id)

        assert mock_payment.status == PaymentStatus.CANCELLED.value


class TestListPayments:
    """Tests fuer Zahlungslisten."""

    @pytest.fixture
    def service(self) -> PaymentService:
        return PaymentService()

    @pytest.fixture
    def mock_db(self):
        """Mockt AsyncSession."""
        db = AsyncMock()
        db.execute = AsyncMock()
        return db

    @pytest.fixture
    def sample_user_id(self):
        return uuid4()

    @pytest.mark.asyncio
    async def test_list_payments_with_pagination(
        self, service: PaymentService, mock_db, sample_user_id
    ):
        """Sollte Zahlungen mit Pagination zurueckgeben."""
        mock_payments = [create_mock_payment(user_id=sample_user_id) for _ in range(5)]

        # Mock count query
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 10  # Gesamtanzahl

        # Mock data query
        mock_data_result = MagicMock()
        mock_data_result.scalars.return_value.all.return_value = mock_payments

        mock_db.execute.side_effect = [mock_count_result, mock_data_result]

        payments, total = await service.list_payments(
            mock_db, sample_user_id, offset=0, limit=5
        )

        assert len(payments) == 5
        assert total == 10

    @pytest.mark.asyncio
    async def test_list_payments_filter_by_status(
        self, service: PaymentService, mock_db, sample_user_id
    ):
        """Sollte Zahlungen nach Status filtern."""
        mock_payments = [
            create_mock_payment(user_id=sample_user_id, status=PaymentStatus.CONFIRMED.value)
            for _ in range(2)
        ]

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 2

        mock_data_result = MagicMock()
        mock_data_result.scalars.return_value.all.return_value = mock_payments

        mock_db.execute.side_effect = [mock_count_result, mock_data_result]

        payments, total = await service.list_payments(
            mock_db, sample_user_id, status=PaymentStatus.CONFIRMED
        )

        assert len(payments) == 2
        assert total == 2

    @pytest.mark.asyncio
    async def test_list_payments_empty(
        self, service: PaymentService, mock_db, sample_user_id
    ):
        """Sollte leere Liste zurueckgeben wenn keine Zahlungen."""
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        mock_data_result = MagicMock()
        mock_data_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [mock_count_result, mock_data_result]

        payments, total = await service.list_payments(mock_db, sample_user_id)

        assert len(payments) == 0
        assert total == 0
