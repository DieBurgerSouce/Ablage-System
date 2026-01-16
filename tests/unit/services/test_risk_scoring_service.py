# -*- coding: utf-8 -*-
"""
Unit-Tests für Risk Scoring Service.

Testet:
- Risk Factor Berechnung (Payment Delay, Default Rate, etc.)
- Score-Berechnung (0-100 Skala)
- Gewichtete Aggregation
- Edge Cases (keine Daten, Grenzwerte)
- Entity Risk Update

Feinpoliert und durchdacht - Risk Scoring Tests.
"""

import pytest
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4, UUID

from app.services.risk_scoring_service import (
    RiskScoringService,
    RiskFactors,
    RISK_WEIGHTS,
    get_risk_scoring_service,
)


# ========================= Test Fixtures =========================


@pytest.fixture
def risk_service() -> RiskScoringService:
    """Create RiskScoringService instance."""
    return RiskScoringService()


@pytest.fixture
def sample_entity_id() -> UUID:
    """Provide sample entity UUID."""
    return uuid4()


@pytest.fixture
def empty_factors() -> RiskFactors:
    """Provide empty RiskFactors instance."""
    return RiskFactors()


@pytest.fixture
def high_risk_factors() -> RiskFactors:
    """Provide high-risk RiskFactors instance."""
    factors = RiskFactors()
    factors.payment_delay_days = 45.0  # Stark ueberfaellig
    factors.default_rate = 0.25  # 25% Ausfallrate
    factors.invoice_volume = 1000.0  # Niedriges Volumen
    factors.document_frequency = 0.5  # Selten
    factors.relationship_months = 3.0  # Kurze Beziehung
    factors.total_invoices = 20
    factors.paid_invoices = 10
    factors.overdue_invoices = 5
    factors.open_invoices = 5
    return factors


@pytest.fixture
def low_risk_factors() -> RiskFactors:
    """Provide low-risk RiskFactors instance."""
    factors = RiskFactors()
    factors.payment_delay_days = 0.0  # Keine Verzoegerung
    factors.default_rate = 0.0  # Keine Ausfaelle
    factors.invoice_volume = 150000.0  # Hohes Volumen
    factors.document_frequency = 15.0  # Regelmaessig
    factors.relationship_months = 36.0  # Lange Beziehung
    factors.total_invoices = 100
    factors.paid_invoices = 100
    factors.overdue_invoices = 0
    factors.open_invoices = 0
    return factors


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Create mock async database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


# ========================= RiskFactors Tests =========================


class TestRiskFactors:
    """Tests for RiskFactors data class."""

    def test_default_values(self):
        """Default-Werte sollten 0 sein."""
        factors = RiskFactors()

        assert factors.payment_delay_days == 0.0
        assert factors.default_rate == 0.0
        assert factors.invoice_volume == 0.0
        assert factors.document_frequency == 0.0
        assert factors.relationship_months == 0.0
        assert factors.total_invoices == 0
        assert factors.paid_invoices == 0
        assert factors.overdue_invoices == 0
        assert factors.open_invoices == 0

    def test_to_dict(self, high_risk_factors: RiskFactors):
        """to_dict() sollte korrekte Struktur liefern."""
        result = high_risk_factors.to_dict()

        assert "payment_delay_days" in result
        assert "default_rate" in result
        assert "invoice_volume" in result
        assert "document_frequency" in result
        assert "relationship_months" in result
        assert "total_invoices" in result
        assert "paid_invoices" in result
        assert "overdue_invoices" in result
        assert "open_invoices" in result

    def test_to_dict_rounded_values(self):
        """to_dict() sollte Werte korrekt runden."""
        factors = RiskFactors()
        factors.payment_delay_days = 12.3456
        factors.default_rate = 0.156789
        factors.invoice_volume = 12345.6789
        factors.document_frequency = 5.789
        factors.relationship_months = 8.888

        result = factors.to_dict()

        assert result["payment_delay_days"] == 12.3  # 1 Dezimalstelle
        assert result["default_rate"] == 15.7  # Als Prozent, 1 Dezimalstelle
        assert result["invoice_volume"] == 12345.68  # 2 Dezimalstellen
        assert result["document_frequency"] == 5.79  # 2 Dezimalstellen
        assert result["relationship_months"] == 8.9  # 1 Dezimalstelle


# ========================= Score Calculation Tests =========================


class TestPaymentDelayScoring:
    """Tests for payment delay scoring."""

    def test_no_delay_returns_zero(self, risk_service: RiskScoringService):
        """Keine Verzoegerung sollte Score 0 ergeben."""
        assert risk_service._score_payment_delay(0.0) == 0.0
        assert risk_service._score_payment_delay(-5.0) == 0.0

    def test_max_delay_returns_hundred(self, risk_service: RiskScoringService):
        """30+ Tage sollte Score 100 ergeben."""
        assert risk_service._score_payment_delay(30.0) == 100.0
        assert risk_service._score_payment_delay(60.0) == 100.0
        assert risk_service._score_payment_delay(90.0) == 100.0

    def test_linear_scaling(self, risk_service: RiskScoringService):
        """Score sollte linear skalieren zwischen 0 und 30 Tagen."""
        assert risk_service._score_payment_delay(15.0) == 50.0
        assert abs(risk_service._score_payment_delay(10.0) - 33.33) < 0.1
        assert abs(risk_service._score_payment_delay(20.0) - 66.67) < 0.1


class TestDefaultRateScoring:
    """Tests for default rate scoring."""

    def test_no_defaults_returns_zero(self, risk_service: RiskScoringService):
        """Keine Ausfaelle sollte Score 0 ergeben."""
        assert risk_service._score_default_rate(0.0) == 0.0
        assert risk_service._score_default_rate(-0.05) == 0.0

    def test_high_default_rate_returns_hundred(self, risk_service: RiskScoringService):
        """20%+ Ausfallrate sollte Score 100 ergeben."""
        assert risk_service._score_default_rate(0.20) == 100.0
        assert risk_service._score_default_rate(0.50) == 100.0
        assert risk_service._score_default_rate(1.0) == 100.0

    def test_linear_scaling(self, risk_service: RiskScoringService):
        """Score sollte linear skalieren zwischen 0% und 20%."""
        assert risk_service._score_default_rate(0.10) == pytest.approx(50.0)
        assert risk_service._score_default_rate(0.05) == pytest.approx(25.0)
        assert risk_service._score_default_rate(0.15) == pytest.approx(75.0)


class TestInvoiceVolumeScoring:
    """Tests for invoice volume scoring."""

    def test_no_volume_returns_high_score(self, risk_service: RiskScoringService):
        """Kein Volumen sollte hohen Score (80) ergeben."""
        assert risk_service._score_invoice_volume(0.0) == 80.0
        assert risk_service._score_invoice_volume(-1000.0) == 80.0

    def test_high_volume_returns_zero(self, risk_service: RiskScoringService):
        """100k+ EUR sollte Score 0 ergeben."""
        assert risk_service._score_invoice_volume(100000.0) == 0.0
        assert risk_service._score_invoice_volume(500000.0) == 0.0

    def test_linear_scaling(self, risk_service: RiskScoringService):
        """Score sollte linear abnehmen mit steigendem Volumen."""
        assert risk_service._score_invoice_volume(50000.0) == 40.0
        assert risk_service._score_invoice_volume(25000.0) == 60.0


class TestDocumentFrequencyScoring:
    """Tests for document frequency scoring."""

    def test_no_frequency_returns_high_score(self, risk_service: RiskScoringService):
        """Keine Dokumente sollte Score 60 ergeben."""
        assert risk_service._score_document_frequency(0.0) == 60.0
        assert risk_service._score_document_frequency(-1.0) == 60.0

    def test_high_frequency_returns_zero(self, risk_service: RiskScoringService):
        """10+ Dokumente/Monat sollte Score 0 ergeben."""
        assert risk_service._score_document_frequency(10.0) == 0.0
        assert risk_service._score_document_frequency(20.0) == 0.0

    def test_linear_scaling(self, risk_service: RiskScoringService):
        """Score sollte linear abnehmen mit steigender Frequenz."""
        assert risk_service._score_document_frequency(5.0) == 30.0
        assert risk_service._score_document_frequency(2.5) == 45.0


class TestRelationshipAgeScoring:
    """Tests for relationship age scoring."""

    def test_new_relationship_returns_high_score(self, risk_service: RiskScoringService):
        """Neue Beziehung sollte Score 70 ergeben."""
        assert risk_service._score_relationship_age(0.0) == 70.0
        assert risk_service._score_relationship_age(-1.0) == 70.0

    def test_long_relationship_returns_zero(self, risk_service: RiskScoringService):
        """24+ Monate sollte Score 0 ergeben."""
        assert risk_service._score_relationship_age(24.0) == 0.0
        assert risk_service._score_relationship_age(48.0) == 0.0

    def test_linear_scaling(self, risk_service: RiskScoringService):
        """Score sollte linear abnehmen mit zunehmender Beziehungsdauer."""
        assert risk_service._score_relationship_age(12.0) == 35.0
        assert risk_service._score_relationship_age(6.0) == 52.5


# ========================= RISK_WEIGHTS Tests =========================


class TestRiskWeights:
    """Tests for risk weight configuration."""

    def test_weights_sum_to_one(self):
        """Gewichte sollten sich zu 1.0 summieren."""
        total = sum(RISK_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_required_weights_present(self):
        """Alle erforderlichen Gewichte sollten vorhanden sein."""
        required_keys = [
            "payment_delay",
            "default_rate",
            "invoice_volume",
            "document_frequency",
            "relationship_age",
        ]
        for key in required_keys:
            assert key in RISK_WEIGHTS

    def test_payment_factors_have_higher_weight(self):
        """Zahlungsfaktoren sollten hoehere Gewichtung haben."""
        payment_weight = RISK_WEIGHTS["payment_delay"] + RISK_WEIGHTS["default_rate"]
        other_weight = (
            RISK_WEIGHTS["invoice_volume"]
            + RISK_WEIGHTS["document_frequency"]
            + RISK_WEIGHTS["relationship_age"]
        )

        assert payment_weight > other_weight


# ========================= Integration Tests =========================


class TestRiskScoreCalculation:
    """Integration tests for full risk score calculation."""

    def test_high_risk_entity(self, risk_service: RiskScoringService):
        """Hohes Risiko sollte hohen Score ergeben."""
        # Simuliere Score-Berechnung mit Einzelwerten
        delay_score = risk_service._score_payment_delay(45.0)  # 100
        default_score = risk_service._score_default_rate(0.25)  # 100
        volume_score = risk_service._score_invoice_volume(1000.0)  # ~79.2
        freq_score = risk_service._score_document_frequency(0.5)  # ~57
        age_score = risk_service._score_relationship_age(3.0)  # ~61.25

        # Gewichteter Score
        weighted_score = (
            delay_score * RISK_WEIGHTS["payment_delay"]
            + default_score * RISK_WEIGHTS["default_rate"]
            + volume_score * RISK_WEIGHTS["invoice_volume"]
            + freq_score * RISK_WEIGHTS["document_frequency"]
            + age_score * RISK_WEIGHTS["relationship_age"]
        )

        assert weighted_score > 75.0  # Hohes Risiko

    def test_low_risk_entity(self, risk_service: RiskScoringService):
        """Niedriges Risiko sollte niedrigen Score ergeben."""
        delay_score = risk_service._score_payment_delay(0.0)  # 0
        default_score = risk_service._score_default_rate(0.0)  # 0
        volume_score = risk_service._score_invoice_volume(150000.0)  # 0
        freq_score = risk_service._score_document_frequency(15.0)  # 0
        age_score = risk_service._score_relationship_age(36.0)  # 0

        weighted_score = (
            delay_score * RISK_WEIGHTS["payment_delay"]
            + default_score * RISK_WEIGHTS["default_rate"]
            + volume_score * RISK_WEIGHTS["invoice_volume"]
            + freq_score * RISK_WEIGHTS["document_frequency"]
            + age_score * RISK_WEIGHTS["relationship_age"]
        )

        assert weighted_score < 25.0  # Niedriges Risiko

    def test_payment_behavior_score_inverse(self, risk_service: RiskScoringService):
        """Payment Behavior Score sollte inverse Beziehung zu Risk Score haben."""
        # Guter Zahler
        delay_score_good = risk_service._score_payment_delay(0.0)  # 0
        default_score_good = risk_service._score_default_rate(0.0)  # 0
        payment_behavior_good = 100 - (delay_score_good * 0.6 + default_score_good * 0.4)

        # Schlechter Zahler
        delay_score_bad = risk_service._score_payment_delay(30.0)  # 100
        default_score_bad = risk_service._score_default_rate(0.20)  # 100
        payment_behavior_bad = 100 - (delay_score_bad * 0.6 + default_score_bad * 0.4)

        assert payment_behavior_good == 100.0
        assert payment_behavior_bad == 0.0


# ========================= Singleton Tests =========================


class TestServiceSingleton:
    """Tests for singleton service instance."""

    def test_get_risk_scoring_service_returns_instance(self):
        """get_risk_scoring_service sollte Service-Instanz liefern."""
        service = get_risk_scoring_service()
        assert isinstance(service, RiskScoringService)

    def test_singleton_returns_same_instance(self):
        """Wiederholte Aufrufe sollten dieselbe Instanz liefern."""
        service1 = get_risk_scoring_service()
        service2 = get_risk_scoring_service()
        assert service1 is service2


# ========================= Edge Cases =========================


class TestEdgeCases:
    """Tests for edge cases and boundary values."""

    def test_score_clamping_upper_bound(self, risk_service: RiskScoringService):
        """Score sollte bei 100 gedeckelt sein."""
        # Extreme Werte
        delay_score = risk_service._score_payment_delay(1000.0)
        assert delay_score == 100.0

    def test_score_clamping_lower_bound(self, risk_service: RiskScoringService):
        """Score sollte bei 0 nicht negativ werden."""
        delay_score = risk_service._score_payment_delay(-100.0)
        assert delay_score == 0.0

    def test_factors_with_zero_invoices(self, empty_factors: RiskFactors):
        """Faktoren mit null Rechnungen sollten keine Division by Zero verursachen."""
        result = empty_factors.to_dict()

        # Sollte keine Exception werfen und valide Werte liefern
        assert result["total_invoices"] == 0
        assert result["default_rate"] == 0.0

    def test_boundary_value_30_days(self, risk_service: RiskScoringService):
        """Grenzwert 30 Tage sollte exakt 100 ergeben."""
        assert risk_service._score_payment_delay(29.99) < 100.0
        assert risk_service._score_payment_delay(30.0) == 100.0
        assert risk_service._score_payment_delay(30.01) == 100.0

    def test_boundary_value_20_percent_default(self, risk_service: RiskScoringService):
        """Grenzwert 20% Ausfallrate sollte exakt 100 ergeben."""
        assert risk_service._score_default_rate(0.199) < 100.0
        assert risk_service._score_default_rate(0.20) == 100.0
        assert risk_service._score_default_rate(0.201) == 100.0


# ========================= Async Tests (Mocked) =========================


@pytest.mark.asyncio
class TestAsyncMethods:
    """Tests for async service methods with mocked database."""

    async def test_calculate_risk_score_entity_not_found(
        self,
        risk_service: RiskScoringService,
        mock_db_session: AsyncMock,
        sample_entity_id: UUID,
    ):
        """Bei nicht gefundener Entity sollte leere Faktoren zurueckgegeben werden."""
        # Mock: Entity nicht gefunden
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        result = await risk_service._collect_factors(mock_db_session, sample_entity_id)

        assert isinstance(result, RiskFactors)
        assert result.payment_delay_days == 0.0
        assert result.total_invoices == 0

    async def test_update_entity_risk_score_entity_not_found(
        self,
        risk_service: RiskScoringService,
        mock_db_session: AsyncMock,
        sample_entity_id: UUID,
    ):
        """Update bei nicht gefundener Entity sollte None zurueckgeben."""
        # Mock: Entity nicht gefunden in beiden Abfragen
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        result = await risk_service.update_entity_risk_score(
            mock_db_session, sample_entity_id
        )

        assert result is None

    async def test_update_all_risk_scores_with_limit(
        self,
        risk_service: RiskScoringService,
        mock_db_session: AsyncMock,
    ):
        """Batch-Update sollte Limit respektieren."""
        # Mock: 3 Entities zurueckgeben
        entity_ids = [uuid4(), uuid4(), uuid4()]
        mock_fetch_result = Mock()
        mock_fetch_result.fetchall.return_value = [(eid,) for eid in entity_ids]

        # Mock fuer update_entity_risk_score - erste Abfrage liefert Entity-IDs
        mock_db_session.execute.return_value = mock_fetch_result

        # Patchen von update_entity_risk_score, da wir nicht vollstaendig mocken koennen
        with patch.object(
            risk_service,
            "update_entity_risk_score",
            new_callable=AsyncMock,
        ) as mock_update:
            mock_update.return_value = Mock()  # Erfolgreiches Update

            updated_count = await risk_service.update_all_risk_scores(
                mock_db_session, limit=10
            )

            # Sollte fuer jede Entity aufgerufen werden
            assert mock_update.call_count == 3
            assert updated_count == 3
