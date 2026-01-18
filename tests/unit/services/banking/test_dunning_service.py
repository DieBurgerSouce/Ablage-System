# -*- coding: utf-8 -*-
"""
Tests fuer DunningService.

Testet:
- Mahnkonfiguration
- Ueberfaelligkeits-Erkennung
- Gebuehren-Berechnung
- Verzugszinsen
- Empfohlene Aktionen
"""

import pytest
from datetime import datetime, date, timedelta
from decimal import Decimal
from uuid import uuid4

from app.services.banking.dunning_service import (
    DunningService,
    DunningConfig,
    DunningCandidate,
    DunningAction,
)
from app.services.banking.models import DunningLevel


class TestDunningConfig:
    """Tests fuer Mahnkonfiguration."""

    def test_default_config(self):
        """Sollte Standard-Konfiguration haben."""
        config = DunningConfig()

        assert config.reminder_after_days == 7
        assert config.first_dunning_after_days == 14
        assert config.second_dunning_after_days == 28
        assert config.final_dunning_after_days == 42
        assert config.first_dunning_fee == Decimal("5.00")
        assert config.second_dunning_fee == Decimal("10.00")
        assert config.final_dunning_fee == Decimal("15.00")

    def test_custom_config(self):
        """Sollte benutzerdefinierte Konfiguration akzeptieren."""
        config = DunningConfig(
            reminder_after_days=5,
            first_dunning_after_days=10,
            first_dunning_fee=Decimal("10.00"),
        )

        assert config.reminder_after_days == 5
        assert config.first_dunning_after_days == 10
        assert config.first_dunning_fee == Decimal("10.00")


class TestRecommendedAction:
    """Tests fuer empfohlene Mahnaktion."""

    @pytest.fixture
    def service(self) -> DunningService:
        return DunningService()

    def test_reminder_for_early_overdue(self, service: DunningService):
        """Sollte Zahlungserinnerung empfehlen wenn weniger als 14 Tage."""
        action = service._get_recommended_action(
            days_overdue=5,
            current_level=DunningLevel.NOT_STARTED,
        )

        assert action == DunningAction.REMINDER

    def test_first_dunning_recommended(self, service: DunningService):
        """Sollte 1. Mahnung empfehlen ab 14 Tage."""
        action = service._get_recommended_action(
            days_overdue=15,
            current_level=DunningLevel.NOT_STARTED,
        )

        assert action == DunningAction.FIRST_DUNNING

    def test_second_dunning_recommended(self, service: DunningService):
        """Sollte 2. Mahnung empfehlen ab 28 Tage."""
        action = service._get_recommended_action(
            days_overdue=30,
            current_level=DunningLevel.FIRST_REMINDER,
        )

        assert action == DunningAction.SECOND_DUNNING

    def test_final_dunning_recommended(self, service: DunningService):
        """Sollte letzte Mahnung empfehlen ab 42 Tage."""
        action = service._get_recommended_action(
            days_overdue=45,
            current_level=DunningLevel.SECOND_REMINDER,
        )

        assert action == DunningAction.FINAL_DUNNING

    def test_collection_after_final(self, service: DunningService):
        """Sollte Inkasso empfehlen nach letzter Mahnung."""
        action = service._get_recommended_action(
            days_overdue=60,
            current_level=DunningLevel.FINAL_REMINDER,
        )

        assert action == DunningAction.COLLECTION

    def test_no_escalation_before_threshold(self, service: DunningService):
        """Sollte nicht eskalieren wenn Schwelle nicht erreicht."""
        # Erste Mahnung gesendet, aber noch nicht 28 Tage
        action = service._get_recommended_action(
            days_overdue=20,
            current_level=DunningLevel.FIRST_REMINDER,
        )

        assert action == DunningAction.FIRST_DUNNING


class TestFeeCalculation:
    """Tests fuer Gebuehren-Berechnung."""

    @pytest.fixture
    def service(self) -> DunningService:
        return DunningService()

    def test_fee_for_first_dunning(self, service: DunningService):
        """Sollte Gebuehr fuer 1. Mahnung berechnen."""
        fee = service._get_fee_for_level(DunningLevel.FIRST_REMINDER)

        assert fee == Decimal("5.00")

    def test_fee_for_second_dunning(self, service: DunningService):
        """Sollte Gebuehr fuer 2. Mahnung berechnen."""
        fee = service._get_fee_for_level(DunningLevel.SECOND_REMINDER)

        assert fee == Decimal("10.00")

    def test_fee_for_final_dunning(self, service: DunningService):
        """Sollte Gebuehr fuer letzte Mahnung berechnen."""
        fee = service._get_fee_for_level(DunningLevel.FINAL_REMINDER)

        assert fee == Decimal("15.00")

    def test_no_fee_for_not_started(self, service: DunningService):
        """Sollte keine Gebuehr fuer Level NOT_STARTED haben."""
        fee = service._get_fee_for_level(DunningLevel.NOT_STARTED)

        assert fee == Decimal("0.00")

    def test_fee_for_action(self, service: DunningService):
        """Sollte Gebuehr fuer Aktion berechnen."""
        reminder_fee = service._get_fee_for_action(DunningAction.REMINDER)
        first_fee = service._get_fee_for_action(DunningAction.FIRST_DUNNING)

        assert reminder_fee == Decimal("0.00")
        assert first_fee == Decimal("5.00")


class TestLateInterestCalculation:
    """Tests fuer Verzugszinsen-Berechnung."""

    @pytest.fixture
    def service(self) -> DunningService:
        return DunningService()

    def test_no_interest_if_not_overdue(self, service: DunningService):
        """Sollte keine Zinsen berechnen wenn nicht ueberfaellig."""
        today = date.today()
        due_date = today + timedelta(days=5)  # Noch nicht faellig

        interest = service._calculate_late_interest(
            principal=Decimal("1000.00"),
            due_date=due_date,
            as_of_date=today,
        )

        assert interest == Decimal("0.00")

    def test_interest_calculation(self, service: DunningService):
        """Sollte Verzugszinsen korrekt berechnen."""
        today = date.today()
        due_date = today - timedelta(days=30)  # 30 Tage ueberfaellig

        interest = service._calculate_late_interest(
            principal=Decimal("1000.00"),
            due_date=due_date,
            as_of_date=today,
        )

        # Basiszins + 5% = 8.62% p.a.
        # 1000 * 0.0862 / 365 * 30 = ~7.09
        assert interest > Decimal("0.00")
        assert interest < Decimal("10.00")  # Plausibilitaetspruefung

    def test_interest_scales_with_principal(self, service: DunningService):
        """Sollte Zinsen proportional zum Betrag skalieren."""
        today = date.today()
        due_date = today - timedelta(days=60)

        interest_1000 = service._calculate_late_interest(
            principal=Decimal("1000.00"),
            due_date=due_date,
            as_of_date=today,
        )

        interest_2000 = service._calculate_late_interest(
            principal=Decimal("2000.00"),
            due_date=due_date,
            as_of_date=today,
        )

        # Doppelter Betrag = doppelte Zinsen
        assert interest_2000 == interest_1000 * 2

    def test_interest_scales_with_days(self, service: DunningService):
        """Sollte Zinsen proportional zu Tagen skalieren."""
        today = date.today()

        interest_30d = service._calculate_late_interest(
            principal=Decimal("1000.00"),
            due_date=today - timedelta(days=30),
            as_of_date=today,
        )

        interest_60d = service._calculate_late_interest(
            principal=Decimal("1000.00"),
            due_date=today - timedelta(days=60),
            as_of_date=today,
        )

        # Doppelte Zeit = ungefaehr doppelte Zinsen (Rundung beachten)
        assert float(interest_60d) == pytest.approx(float(interest_30d * 2), rel=0.01)


class TestDunningCandidate:
    """Tests fuer DunningCandidate Dataclass."""

    def test_create_candidate(self):
        """Sollte Mahnkandidaten erstellen."""
        today = date.today()
        due_date = today - timedelta(days=20)

        candidate = DunningCandidate(
            document_id=uuid4(),
            invoice_number="RE-2024-001",
            creditor_name="Test GmbH",
            amount=Decimal("500.00"),
            due_date=due_date,
            days_overdue=20,
            current_level=DunningLevel.NOT_STARTED,
            recommended_action=DunningAction.FIRST_DUNNING,
            accumulated_fees=Decimal("0.00"),
            late_interest=Decimal("2.50"),
            total_due=Decimal("507.50"),
        )

        assert candidate.invoice_number == "RE-2024-001"
        assert candidate.days_overdue == 20
        assert candidate.total_due == Decimal("507.50")

    def test_total_due_calculation(self):
        """Sollte Gesamtbetrag korrekt berechnen."""
        candidate = DunningCandidate(
            document_id=uuid4(),
            invoice_number="RE-2024-002",
            creditor_name="Muster AG",
            amount=Decimal("1000.00"),
            due_date=date.today() - timedelta(days=45),
            days_overdue=45,
            current_level=DunningLevel.SECOND_REMINDER,
            recommended_action=DunningAction.FINAL_DUNNING,
            accumulated_fees=Decimal("15.00"),  # 5 + 10
            late_interest=Decimal("10.50"),
            total_due=Decimal("1025.50"),  # 1000 + 15 + 10.50
        )

        expected_total = (
            candidate.amount +
            candidate.accumulated_fees +
            candidate.late_interest
        )

        assert candidate.total_due == expected_total


class TestCustomConfig:
    """Tests mit benutzerdefinierter Konfiguration."""

    def test_custom_fee_structure(self):
        """Sollte benutzerdefinierte Gebuehrenstruktur verwenden."""
        config = DunningConfig(
            first_dunning_fee=Decimal("10.00"),
            second_dunning_fee=Decimal("20.00"),
            final_dunning_fee=Decimal("30.00"),
        )

        service = DunningService(config=config)

        assert service._get_fee_for_level(DunningLevel.FIRST_REMINDER) == Decimal("10.00")
        assert service._get_fee_for_level(DunningLevel.SECOND_REMINDER) == Decimal("20.00")
        assert service._get_fee_for_level(DunningLevel.FINAL_REMINDER) == Decimal("30.00")

    def test_custom_timing(self):
        """Sollte benutzerdefinierte Zeitraeume verwenden."""
        config = DunningConfig(
            reminder_after_days=3,
            first_dunning_after_days=7,
            second_dunning_after_days=14,
            final_dunning_after_days=21,
        )

        service = DunningService(config=config)

        # 8 Tage sollte 1. Mahnung ausloesen (statt Erinnerung)
        action = service._get_recommended_action(
            days_overdue=8,
            current_level=DunningLevel.NOT_STARTED,
        )

        assert action == DunningAction.FIRST_DUNNING

    def test_custom_interest_rate(self):
        """Sollte benutzerdefinierten Zinssatz verwenden."""
        config = DunningConfig(
            late_interest_rate=Decimal("9.00"),  # 9% ueber Basiszins
            base_interest_rate=Decimal("5.00"),  # Höherer Basiszins
        )

        service = DunningService(config=config)

        today = date.today()
        interest = service._calculate_late_interest(
            principal=Decimal("1000.00"),
            due_date=today - timedelta(days=365),
            as_of_date=today,
        )

        # 1000 * 14% = 140 (ungefaehr)
        assert interest > Decimal("100.00")
        assert interest < Decimal("200.00")


class TestMinDunningAmount:
    """Tests fuer Mindestbetrag."""

    def test_min_amount_default(self):
        """Sollte Standard-Mindestbetrag haben."""
        config = DunningConfig()

        assert config.min_dunning_amount == Decimal("5.00")

    def test_custom_min_amount(self):
        """Sollte benutzerdefinierten Mindestbetrag verwenden."""
        config = DunningConfig(min_dunning_amount=Decimal("10.00"))

        assert config.min_dunning_amount == Decimal("10.00")


# =============================================================================
# ASYNC DB TESTS
# =============================================================================

from unittest.mock import AsyncMock, MagicMock, patch
from app.services.banking.models import DunningStatus


class TestAsyncGetOverdueInvoices:
    """Tests fuer async get_overdue_invoices."""

    @pytest.fixture
    def service(self) -> DunningService:
        return DunningService()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        return db

    @pytest.fixture
    def sample_user_id(self):
        return uuid4()

    @pytest.fixture
    def sample_overdue_documents(self, sample_user_id):
        """Sample ueberfaellige Dokumente."""
        today = date.today()
        documents = []

        # Rechnung 1: 20 Tage ueberfaellig
        doc1 = MagicMock()
        doc1.id = uuid4()
        doc1.owner_id = sample_user_id
        doc1.document_type = "invoice"
        doc1.deleted_at = None
        doc1.extracted_data = {
            "invoice_number": "RE-2024-001",
            "creditor_name": "Kunde A GmbH",
            "total_amount": "1500.00",
            "due_date": (today - timedelta(days=20)).isoformat(),
        }
        documents.append(doc1)

        # Rechnung 2: 45 Tage ueberfaellig
        doc2 = MagicMock()
        doc2.id = uuid4()
        doc2.owner_id = sample_user_id
        doc2.document_type = "invoice"
        doc2.deleted_at = None
        doc2.extracted_data = {
            "invoice_number": "RE-2024-002",
            "creditor_name": "Kunde B AG",
            "total_amount": "2500.00",
            "due_date": (today - timedelta(days=45)).isoformat(),
        }
        documents.append(doc2)

        # Rechnung 3: Nicht ueberfaellig (ignorieren)
        doc3 = MagicMock()
        doc3.id = uuid4()
        doc3.owner_id = sample_user_id
        doc3.document_type = "invoice"
        doc3.deleted_at = None
        doc3.extracted_data = {
            "invoice_number": "RE-2024-003",
            "creditor_name": "Kunde C",
            "total_amount": "500.00",
            "due_date": (today + timedelta(days=10)).isoformat(),
        }
        documents.append(doc3)

        # Rechnung 4: Bereits bezahlt (ignorieren)
        doc4 = MagicMock()
        doc4.id = uuid4()
        doc4.owner_id = sample_user_id
        doc4.document_type = "invoice"
        doc4.deleted_at = None
        doc4.extracted_data = {
            "invoice_number": "RE-2024-004",
            "creditor_name": "Kunde D",
            "total_amount": "3000.00",
            "due_date": (today - timedelta(days=30)).isoformat(),
            "payment_status": "paid",
        }
        documents.append(doc4)

        return documents

    @pytest.mark.asyncio
    async def test_get_overdue_invoices(
        self, service: DunningService, mock_db, sample_user_id, sample_overdue_documents
    ):
        """Sollte ueberfaellige Rechnungen finden."""
        # Mock Document-Abfrage
        mock_doc_result = MagicMock()
        mock_doc_result.scalars.return_value.all.return_value = sample_overdue_documents

        # Mock DunningRecord-Abfrage (keine existierenden Mahnungen)
        mock_dunning_result = MagicMock()
        mock_dunning_result.scalar_one_or_none.return_value = None

        mock_db.execute = AsyncMock(side_effect=[mock_doc_result, mock_dunning_result, mock_dunning_result])

        candidates = await service.get_overdue_invoices(
            db=mock_db,
            user_id=sample_user_id,
            min_days_overdue=1,
        )

        # Nur 2 ueberfaellige (nicht bezahlte) sollten zurueckgegeben werden
        assert len(candidates) == 2

    @pytest.mark.asyncio
    async def test_get_overdue_invoices_empty(
        self, service: DunningService, mock_db, sample_user_id
    ):
        """Sollte leere Liste bei keinen ueberfaelligen zurueckgeben."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        candidates = await service.get_overdue_invoices(
            db=mock_db,
            user_id=sample_user_id,
        )

        assert candidates == []

    @pytest.mark.asyncio
    async def test_get_overdue_invoices_with_max_days(
        self, service: DunningService, mock_db, sample_user_id, sample_overdue_documents
    ):
        """Sollte max_days_overdue Filter respektieren."""
        mock_doc_result = MagicMock()
        mock_doc_result.scalars.return_value.all.return_value = sample_overdue_documents
        mock_dunning_result = MagicMock()
        mock_dunning_result.scalar_one_or_none.return_value = None

        mock_db.execute = AsyncMock(side_effect=[mock_doc_result, mock_dunning_result])

        candidates = await service.get_overdue_invoices(
            db=mock_db,
            user_id=sample_user_id,
            min_days_overdue=1,
            max_days_overdue=30,  # Nur bis 30 Tage
        )

        # Nur Rechnung mit 20 Tagen sollte zurueckgegeben werden
        assert len(candidates) == 1


class TestAsyncCreateDunning:
    """Tests fuer async create_dunning."""

    @pytest.fixture
    def service(self) -> DunningService:
        return DunningService()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @pytest.fixture
    def sample_user_id(self):
        return uuid4()

    @pytest.fixture
    def sample_document(self, sample_user_id):
        """Sample Dokument fuer Mahnung."""
        today = date.today()
        doc = MagicMock()
        doc.id = uuid4()
        doc.owner_id = sample_user_id
        doc.document_type = "invoice"
        doc.deleted_at = None
        doc.extracted_data = {
            "invoice_number": "RE-2024-100",
            "creditor_name": "Test Kunde",
            "total_amount": "1000.00",
            "due_date": (today - timedelta(days=20)).isoformat(),
        }
        return doc

    @pytest.mark.asyncio
    async def test_create_dunning_not_found(
        self, service: DunningService, mock_db, sample_user_id
    ):
        """Sollte Fehler werfen bei nicht existierendem Dokument."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError, match="Dokument nicht gefunden"):
            await service.create_dunning(
                db=mock_db,
                user_id=sample_user_id,
                document_id=uuid4(),
                level=DunningLevel.FIRST_REMINDER,
            )

    @pytest.mark.asyncio
    async def test_create_dunning_already_exists(
        self, service: DunningService, mock_db, sample_user_id, sample_document
    ):
        """Sollte Fehler werfen bei existierendem Mahnverfahren."""
        # Mock Dokument gefunden
        mock_doc_result = MagicMock()
        mock_doc_result.scalar_one_or_none.return_value = sample_document

        # Mock existierendes Mahnverfahren
        existing_dunning = MagicMock()
        existing_dunning.dunning_level = DunningLevel.FIRST_REMINDER.value
        mock_dunning_result = MagicMock()
        mock_dunning_result.scalar_one_or_none.return_value = existing_dunning

        mock_db.execute = AsyncMock(side_effect=[mock_doc_result, mock_dunning_result])

        with pytest.raises(ValueError, match="existiert bereits"):
            await service.create_dunning(
                db=mock_db,
                user_id=sample_user_id,
                document_id=sample_document.id,
                level=DunningLevel.FIRST_REMINDER,
            )


class TestAsyncEscalateDunning:
    """Tests fuer async escalate_dunning."""

    @pytest.fixture
    def service(self) -> DunningService:
        return DunningService()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @pytest.fixture
    def sample_user_id(self):
        return uuid4()

    @pytest.mark.asyncio
    async def test_escalate_dunning_not_found(
        self, service: DunningService, mock_db, sample_user_id
    ):
        """Sollte Fehler werfen bei nicht existierendem Mahnvorgang."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError, match="nicht gefunden"):
            await service.escalate_dunning(
                db=mock_db,
                user_id=sample_user_id,
                dunning_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_escalate_dunning_wrong_status(
        self, service: DunningService, mock_db, sample_user_id
    ):
        """Sollte Fehler werfen bei falschem Status."""
        # Mock abgeschlossener Mahnvorgang
        dunning = MagicMock()
        dunning.id = uuid4()
        dunning.user_id = sample_user_id
        dunning.status = DunningStatus.PAID.value
        dunning.dunning_level = DunningLevel.FIRST_REMINDER.value

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = dunning
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError, match="kann nicht eskaliert werden"):
            await service.escalate_dunning(
                db=mock_db,
                user_id=sample_user_id,
                dunning_id=dunning.id,
            )


class TestAsyncCloseDunning:
    """Tests fuer async close_dunning."""

    @pytest.fixture
    def service(self) -> DunningService:
        return DunningService()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @pytest.fixture
    def sample_user_id(self):
        return uuid4()

    @pytest.mark.asyncio
    async def test_close_dunning_invalid_status(
        self, service: DunningService, mock_db, sample_user_id
    ):
        """Sollte Fehler werfen bei ungueltigem Status."""
        with pytest.raises(ValueError, match="kann nicht auf"):
            await service.close_dunning(
                db=mock_db,
                user_id=sample_user_id,
                dunning_id=uuid4(),
                status=DunningStatus.PENDING,  # Ungueltig
            )

    @pytest.mark.asyncio
    async def test_close_dunning_not_found(
        self, service: DunningService, mock_db, sample_user_id
    ):
        """Sollte Fehler werfen bei nicht existierendem Mahnvorgang."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError, match="nicht gefunden"):
            await service.close_dunning(
                db=mock_db,
                user_id=sample_user_id,
                dunning_id=uuid4(),
                status=DunningStatus.PAID,
            )


class TestAsyncListDunnings:
    """Tests fuer async list_dunnings."""

    @pytest.fixture
    def service(self) -> DunningService:
        return DunningService()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        return db

    @pytest.fixture
    def sample_user_id(self):
        return uuid4()

    @pytest.mark.asyncio
    async def test_list_dunnings_empty(
        self, service: DunningService, mock_db, sample_user_id
    ):
        """Sollte leere Liste zurueckgeben."""
        # Mock count
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        # Mock list
        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_list_result])

        dunnings, total = await service.list_dunnings(
            db=mock_db,
            user_id=sample_user_id,
        )

        assert dunnings == []
        assert total == 0


class TestAsyncDunningStats:
    """Tests fuer async get_dunning_stats."""

    @pytest.fixture
    def service(self) -> DunningService:
        return DunningService()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        return db

    @pytest.fixture
    def sample_user_id(self):
        return uuid4()

    @pytest.mark.asyncio
    async def test_get_dunning_stats_empty(
        self, service: DunningService, mock_db, sample_user_id
    ):
        """Sollte leere Stats zurueckgeben bei keinen Daten."""
        # Mock fuer verschiedene Abfragen
        mock_empty_result = MagicMock()
        mock_empty_result.scalars.return_value.all.return_value = []
        mock_empty_result.scalar.return_value = 0
        # Service erwartet 3 Werte: count, gross_amount, reminder_fee
        mock_empty_result.one.return_value = (0, Decimal("0.00"), Decimal("0.00"))

        mock_db.execute = AsyncMock(return_value=mock_empty_result)

        stats = await service.get_dunning_stats(
            db=mock_db,
            user_id=sample_user_id,
        )

        # Service gibt Frontend-kompatibles Format zurueck (siehe get_dunning_stats docstring)
        assert "total_amount_overdue" in stats
        assert "total_active" in stats
        assert "by_level" in stats


class TestAsyncAutomaticDunning:
    """Tests fuer async process_automatic_dunning."""

    @pytest.fixture
    def service(self) -> DunningService:
        return DunningService()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        return db

    @pytest.fixture
    def sample_user_id(self):
        return uuid4()

    @pytest.mark.asyncio
    async def test_automatic_dunning_dry_run(
        self, service: DunningService, mock_db, sample_user_id
    ):
        """Sollte dry_run ohne Aenderungen durchfuehren."""
        # Mock leere Ergebnisse
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        actions = await service.process_automatic_dunning(
            db=mock_db,
            user_id=sample_user_id,
            dry_run=True,
        )

        assert isinstance(actions, list)


class TestDunningActionEnum:
    """Tests fuer DunningAction Enum."""

    def test_action_values(self):
        """Sollte korrekte Aktions-Werte haben."""
        assert DunningAction.REMINDER.value == "reminder"
        assert DunningAction.FIRST_DUNNING.value == "first"
        assert DunningAction.SECOND_DUNNING.value == "second"
        assert DunningAction.FINAL_DUNNING.value == "final"
        assert DunningAction.COLLECTION.value == "collection"
        assert DunningAction.WRITE_OFF.value == "write_off"

    def test_action_count(self):
        """Sollte 6 Aktionen haben."""
        assert len(DunningAction) == 6


class TestDunningLevelEnum:
    """Tests fuer DunningLevel Enum."""

    def test_level_values(self):
        """Sollte korrekte Level-Werte haben."""
        assert DunningLevel.NOT_STARTED.value == 0
        assert DunningLevel.FIRST_REMINDER.value == 1
        assert DunningLevel.SECOND_REMINDER.value == 2
        assert DunningLevel.FINAL_REMINDER.value == 3

    def test_level_ordering(self):
        """Sollte aufsteigende Reihenfolge haben."""
        assert DunningLevel.NOT_STARTED.value < DunningLevel.FIRST_REMINDER.value
        assert DunningLevel.FIRST_REMINDER.value < DunningLevel.SECOND_REMINDER.value
        assert DunningLevel.SECOND_REMINDER.value < DunningLevel.FINAL_REMINDER.value
