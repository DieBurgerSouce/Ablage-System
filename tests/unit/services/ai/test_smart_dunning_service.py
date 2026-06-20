# -*- coding: utf-8 -*-
"""
Unit Tests fuer SmartDunningService.

Testet intelligentes Mahnwesen mit:
- Optimales Mahntiming
- Personalisierte Mahntexte
- A/B-Testing
- Zahlungsvorhersage
- Strategie-Tracking

Feinpoliert und durchdacht.
"""

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.services.ai.smart_dunning_service import (
    SmartDunningService,
    DunningLevel,
    DunningTone,
    DunningStrategy,
    DunningText,
    DunningTiming,
    DunningResult,
    PaymentPrediction,
    PaymentLikelihood,
    CustomerProfile,
    CustomerSegment,
    ABTest,
    ABTestVariant,
    DUNNING_LEVEL_LABELS_DE,
    TONE_DESCRIPTIONS,
    DEFAULT_WAITING_PERIODS,
    get_smart_dunning_service,
    reset_smart_dunning_service,
)
from app.services.risk_scoring_service import (
    RiskFactors,
    TrendDirection,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def service() -> SmartDunningService:
    """Erstellt frischen Service fuer jeden Test."""
    reset_smart_dunning_service()
    return SmartDunningService()


@pytest.fixture
def mock_ollama_service() -> MagicMock:
    """Mock fuer Ollama Service."""
    mock = MagicMock()
    mock.is_available = AsyncMock(return_value=True)
    mock.generate = AsyncMock(return_value='''
    {
        "subject": "Zahlungserinnerung - Rechnung RE-001",
        "greeting": "Sehr geehrte Damen und Herren,",
        "body": "wir moechten Sie freundlich an die offene Rechnung erinnern.",
        "closing": "Mit freundlichen Gruessen"
    }
    ''')
    return mock


@pytest.fixture
def mock_risk_service() -> MagicMock:
    """Mock fuer Risk Scoring Service."""
    mock = MagicMock()
    factors = RiskFactors()
    factors.payment_delay_days = 7.5
    factors.default_rate = 0.05
    factors.total_invoices = 50
    factors.open_invoices = 3
    factors.relationship_months = 24
    factors.payment_trend = TrendDirection.STABLE
    factors.industry_code = "manufacturing"

    mock.calculate_risk_score = AsyncMock(return_value=(35.0, 75.0, factors))
    return mock


@pytest.fixture
def sample_customer_profile() -> CustomerProfile:
    """Beispiel-Kundenprofil."""
    return CustomerProfile(
        entity_id=uuid.uuid4(),
        segment=CustomerSegment.GOOD,
        avg_payment_delay=7.5,
        payment_trend=TrendDirection.STABLE,
        total_invoices=50,
        open_invoices=3,
        relationship_months=24.0,
        last_payment_date=datetime.now(timezone.utc) - timedelta(days=30),
        preferred_communication=None,
        language="de",
    )


# =============================================================================
# Tests: Basis-Funktionalitaet
# =============================================================================

class TestDunningBasics:
    """Tests fuer grundlegende Mahnungs-Funktionen."""

    def test_dunning_level_labels_de_complete(self):
        """Stellt sicher, dass alle DunningLevels deutsche Labels haben."""
        for level in DunningLevel:
            assert level in DUNNING_LEVEL_LABELS_DE, f"Fehlendes Label fuer {level}"
            assert len(DUNNING_LEVEL_LABELS_DE[level]) > 0

    def test_tone_descriptions_complete(self):
        """Stellt sicher, dass alle Tones Beschreibungen haben."""
        for tone in DunningTone:
            assert tone in TONE_DESCRIPTIONS, f"Fehlende Beschreibung fuer {tone}"
            assert len(TONE_DESCRIPTIONS[tone]) > 0

    def test_default_waiting_periods_complete(self):
        """Stellt sicher, dass alle DunningLevels Wartezeiten haben."""
        for level in DunningLevel:
            assert level in DEFAULT_WAITING_PERIODS, f"Fehlende Wartezeit fuer {level}"
            assert DEFAULT_WAITING_PERIODS[level] > 0


# =============================================================================
# Tests: Kundensegment-Bestimmung
# =============================================================================

class TestCustomerSegmentation:
    """Tests fuer Kundensegmentierung."""

    def test_segment_vip(self, service: SmartDunningService):
        """VIP-Segment bei hohem Payment-Score und langer Beziehung."""
        factors = RiskFactors()
        factors.relationship_months = 36

        segment = service._determine_segment(92.0, factors)
        assert segment == CustomerSegment.VIP

    def test_segment_good(self, service: SmartDunningService):
        """Good-Segment bei gutem Payment-Score."""
        factors = RiskFactors()
        factors.relationship_months = 12

        segment = service._determine_segment(82.0, factors)
        assert segment == CustomerSegment.GOOD

    def test_segment_normal(self, service: SmartDunningService):
        """Normal-Segment bei durchschnittlichem Score."""
        factors = RiskFactors()
        factors.relationship_months = 6

        segment = service._determine_segment(65.0, factors)
        assert segment == CustomerSegment.NORMAL

    def test_segment_risky(self, service: SmartDunningService):
        """Risky-Segment bei niedrigem Score."""
        factors = RiskFactors()
        factors.relationship_months = 3

        segment = service._determine_segment(45.0, factors)
        assert segment == CustomerSegment.RISKY

    def test_segment_problematic(self, service: SmartDunningService):
        """Problematic-Segment bei sehr niedrigem Score."""
        factors = RiskFactors()
        factors.relationship_months = 1

        segment = service._determine_segment(30.0, factors)
        assert segment == CustomerSegment.PROBLEMATIC


# =============================================================================
# Tests: Tonfall-Bestimmung
# =============================================================================

class TestToneDetermination:
    """Tests fuer automatische Tonfall-Bestimmung."""

    def test_tone_reminder_level(
        self,
        service: SmartDunningService,
        sample_customer_profile: CustomerProfile,
    ):
        """Zahlungserinnerung sollte freundlich sein."""
        tone = service._determine_tone(DunningLevel.REMINDER, sample_customer_profile)
        assert tone == DunningTone.FRIENDLY

    def test_tone_first_dunning(
        self,
        service: SmartDunningService,
        sample_customer_profile: CustomerProfile,
    ):
        """1. Mahnung sollte neutral sein.

        Vertrag: Basis-Ton der 1. Mahnung ist NEUTRAL. Der GOOD/VIP-Rabatt
        mildert nur FIRM->NEUTRAL und URGENT->FIRM ab; NEUTRAL bleibt NEUTRAL
        (eine erste Erinnerung ist bereits angemessen zurueckhaltend).
        """
        tone = service._determine_tone(DunningLevel.FIRST, sample_customer_profile)
        assert tone == DunningTone.NEUTRAL

    def test_tone_second_dunning(
        self,
        service: SmartDunningService,
        sample_customer_profile: CustomerProfile,
    ):
        """2. Mahnung sollte bestimmt sein."""
        tone = service._determine_tone(DunningLevel.SECOND, sample_customer_profile)
        # GOOD-Kunde bekommt eine Stufe freundlicher -> NEUTRAL
        assert tone == DunningTone.NEUTRAL

    def test_tone_final_dunning(
        self,
        service: SmartDunningService,
        sample_customer_profile: CustomerProfile,
    ):
        """Letzte Mahnung sollte dringend sein."""
        tone = service._determine_tone(DunningLevel.FINAL, sample_customer_profile)
        # GOOD-Kunde bekommt eine Stufe freundlicher -> FIRM
        assert tone == DunningTone.FIRM

    def test_tone_problematic_customer(self, service: SmartDunningService):
        """Problematischer Kunde bekommt strengeren Ton."""
        profile = CustomerProfile(
            entity_id=uuid.uuid4(),
            segment=CustomerSegment.PROBLEMATIC,
            avg_payment_delay=45.0,
            payment_trend=TrendDirection.WORSENING,
            total_invoices=20,
            open_invoices=8,
            relationship_months=6.0,
            last_payment_date=None,
            preferred_communication=None,
            language="de",
        )

        tone = service._determine_tone(DunningLevel.REMINDER, profile)
        # PROBLEMATIC bekommt eine Stufe strenger -> NEUTRAL
        assert tone == DunningTone.NEUTRAL


# =============================================================================
# Tests: Strategie-Bestimmung
# =============================================================================

class TestStrategyDetermination:
    """Tests fuer automatische Strategie-Bestimmung."""

    def test_strategy_vip_customer(self, service: SmartDunningService):
        """VIP-Kunden sollten Beziehungsstrategie bekommen."""
        profile = CustomerProfile(
            entity_id=uuid.uuid4(),
            segment=CustomerSegment.VIP,
            avg_payment_delay=2.0,
            payment_trend=TrendDirection.STABLE,
            total_invoices=100,
            open_invoices=1,
            relationship_months=60.0,
            last_payment_date=datetime.now(timezone.utc),
            preferred_communication=None,
            language="de",
        )

        strategy = service._determine_strategy(profile)
        assert strategy == DunningStrategy.RELATIONSHIP

    def test_strategy_risky_customer(self, service: SmartDunningService):
        """Risiko-Kunden sollten Finanzdruck-Strategie bekommen."""
        profile = CustomerProfile(
            entity_id=uuid.uuid4(),
            segment=CustomerSegment.RISKY,
            avg_payment_delay=21.0,
            payment_trend=TrendDirection.WORSENING,
            total_invoices=15,
            open_invoices=5,
            relationship_months=8.0,
            last_payment_date=None,
            preferred_communication=None,
            language="de",
        )

        strategy = service._determine_strategy(profile)
        assert strategy == DunningStrategy.FINANCIAL

    def test_strategy_problematic_customer(self, service: SmartDunningService):
        """Problematische Kunden sollten Eskalations-Strategie bekommen."""
        profile = CustomerProfile(
            entity_id=uuid.uuid4(),
            segment=CustomerSegment.PROBLEMATIC,
            avg_payment_delay=45.0,
            payment_trend=TrendDirection.WORSENING,
            total_invoices=10,
            open_invoices=7,
            relationship_months=3.0,
            last_payment_date=None,
            preferred_communication=None,
            language="de",
        )

        strategy = service._determine_strategy(profile)
        assert strategy == DunningStrategy.ESCALATION

    def test_strategy_no_profile(self, service: SmartDunningService):
        """Ohne Profil sollte Standard-Strategie gewaehlt werden."""
        strategy = service._determine_strategy(None)
        assert strategy == DunningStrategy.STANDARD


# =============================================================================
# Tests: Timing-Berechnung
# =============================================================================

class TestTimingCalculation:
    """Tests fuer Mahntiming-Berechnung."""

    def test_adjust_timing_vip(
        self,
        service: SmartDunningService,
        sample_customer_profile: CustomerProfile,
    ):
        """VIP-Kunden sollten mehr Zeit bekommen."""
        sample_customer_profile.segment = CustomerSegment.VIP
        base_days = 14

        adjusted = service._adjust_timing_by_profile(
            base_days, sample_customer_profile, DunningLevel.FIRST
        )

        # VIP bekommt 30% mehr Zeit
        assert adjusted > base_days
        assert adjusted == int(base_days * 1.3)

    def test_adjust_timing_problematic(
        self,
        service: SmartDunningService,
        sample_customer_profile: CustomerProfile,
    ):
        """Problematische Kunden sollten schneller gemahnt werden."""
        sample_customer_profile.segment = CustomerSegment.PROBLEMATIC
        base_days = 14

        adjusted = service._adjust_timing_by_profile(
            base_days, sample_customer_profile, DunningLevel.FIRST
        )

        # Problematic bekommt 40% weniger Zeit
        assert adjusted < base_days
        assert adjusted == int(base_days * 0.6)

    def test_adjust_timing_worsening_trend(
        self,
        service: SmartDunningService,
        sample_customer_profile: CustomerProfile,
    ):
        """Verschlechternder Trend sollte Timing verkuerzen."""
        sample_customer_profile.payment_trend = TrendDirection.WORSENING
        base_days = 14

        adjusted = service._adjust_timing_by_profile(
            base_days, sample_customer_profile, DunningLevel.FIRST
        )

        # Worsening bekommt 20% weniger Zeit (nach Segment-Anpassung)
        assert adjusted < int(base_days * 1.1)  # GOOD segment * 1.1

    def test_adjust_timing_improving_trend(
        self,
        service: SmartDunningService,
        sample_customer_profile: CustomerProfile,
    ):
        """Verbessernder Trend sollte Timing verlaengern."""
        sample_customer_profile.payment_trend = TrendDirection.IMPROVING
        base_days = 14

        adjusted = service._adjust_timing_by_profile(
            base_days, sample_customer_profile, DunningLevel.FIRST
        )

        # Improving bekommt 20% mehr Zeit (nach Segment-Anpassung)
        # GOOD segment * 1.1 * 1.2 = 1.32
        assert adjusted > base_days

    def test_timing_bounds(
        self,
        service: SmartDunningService,
        sample_customer_profile: CustomerProfile,
    ):
        """Timing sollte innerhalb sinnvoller Grenzen bleiben."""
        sample_customer_profile.segment = CustomerSegment.VIP
        sample_customer_profile.payment_trend = TrendDirection.IMPROVING

        adjusted = service._adjust_timing_by_profile(
            30, sample_customer_profile, DunningLevel.FIRST
        )

        # Max 30 Tage
        assert adjusted <= 30

        sample_customer_profile.segment = CustomerSegment.PROBLEMATIC
        sample_customer_profile.payment_trend = TrendDirection.WORSENING

        adjusted = service._adjust_timing_by_profile(
            5, sample_customer_profile, DunningLevel.FIRST
        )

        # Min 3 Tage
        assert adjusted >= 3


# =============================================================================
# Tests: Zahlungsvorhersage
# =============================================================================

class TestPaymentPrediction:
    """Tests fuer Zahlungsvorhersage."""

    def test_probability_high_payment_score(self, service: SmartDunningService):
        """Hoher Payment-Score sollte hohe Wahrscheinlichkeit ergeben."""
        factors = {"payment_score": 90, "days_overdue": 5, "dunning_level": 0}

        prob = service._calculate_payment_probability(factors, None)

        assert prob >= 0.8

    def test_probability_low_payment_score(self, service: SmartDunningService):
        """Niedriger Payment-Score sollte niedrige Wahrscheinlichkeit ergeben."""
        factors = {"payment_score": 30, "days_overdue": 45, "dunning_level": 3}

        prob = service._calculate_payment_probability(factors, None)

        assert prob <= 0.5

    def test_probability_long_overdue_penalty(self, service: SmartDunningService):
        """Lange Ueberfaelligkeit sollte Wahrscheinlichkeit senken."""
        factors_recent = {"payment_score": 70, "days_overdue": 5, "dunning_level": 0}
        factors_old = {"payment_score": 70, "days_overdue": 60, "dunning_level": 0}

        prob_recent = service._calculate_payment_probability(factors_recent, None)
        prob_old = service._calculate_payment_probability(factors_old, None)

        assert prob_old < prob_recent

    def test_probability_to_likelihood_high(self, service: SmartDunningService):
        """Hohe Wahrscheinlichkeit -> HIGH Likelihood."""
        likelihood = service._probability_to_likelihood(0.80)
        assert likelihood == PaymentLikelihood.HIGH

    def test_probability_to_likelihood_medium(self, service: SmartDunningService):
        """Mittlere Wahrscheinlichkeit -> MEDIUM Likelihood."""
        likelihood = service._probability_to_likelihood(0.55)
        assert likelihood == PaymentLikelihood.MEDIUM

    def test_probability_to_likelihood_low(self, service: SmartDunningService):
        """Niedrige Wahrscheinlichkeit -> LOW Likelihood."""
        likelihood = service._probability_to_likelihood(0.30)
        assert likelihood == PaymentLikelihood.LOW

    def test_estimate_payment_delay(
        self,
        service: SmartDunningService,
        sample_customer_profile: CustomerProfile,
    ):
        """Erwartete Verzoegerung sollte auf Historie basieren."""
        factors = {"days_overdue": 10, "dunning_level": 1}
        sample_customer_profile.avg_payment_delay = 14.0

        delay = service._estimate_payment_delay(factors, sample_customer_profile)

        # Basierend auf avg_payment_delay + dunning_level adjustment
        assert delay >= 14


# =============================================================================
# Tests: Empfehlungs-Generierung
# =============================================================================

class TestRecommendations:
    """Tests fuer Empfehlungs-Generierung."""

    def test_recommendations_high_likelihood(
        self,
        service: SmartDunningService,
        sample_customer_profile: CustomerProfile,
    ):
        """HIGH Likelihood sollte Standard-Empfehlung geben."""
        recommendations = service._generate_payment_recommendations(
            PaymentLikelihood.HIGH,
            {"days_overdue": 5},
            sample_customer_profile,
        )

        assert any("Standard-Mahnprozess" in r for r in recommendations)

    def test_recommendations_low_likelihood(
        self,
        service: SmartDunningService,
        sample_customer_profile: CustomerProfile,
    ):
        """LOW Likelihood sollte Eskalations-Empfehlung geben."""
        recommendations = service._generate_payment_recommendations(
            PaymentLikelihood.LOW,
            {"days_overdue": 45, "dunning_level": 3},
            sample_customer_profile,
        )

        assert any("Inkasso" in r for r in recommendations)

    def test_recommendations_high_amount(
        self,
        service: SmartDunningService,
        sample_customer_profile: CustomerProfile,
    ):
        """Hoher Betrag sollte Ratenzahlungs-Hinweis geben."""
        recommendations = service._generate_payment_recommendations(
            PaymentLikelihood.MEDIUM,
            {"invoice_amount": 10000, "days_overdue": 20},
            sample_customer_profile,
        )

        assert any("Ratenzahlung" in r or "Skonto" in r for r in recommendations)


# =============================================================================
# Tests: Fallback-Texte
# =============================================================================

class TestFallbackTexts:
    """Tests fuer Fallback-Mahntexte."""

    def test_fallback_text_reminder(self, service: SmartDunningService):
        """Zahlungserinnerung Fallback-Text."""
        text = service._generate_fallback_text(
            DunningLevel.REMINDER, None, DunningTone.FRIENDLY, DunningStrategy.STANDARD
        )

        assert text.subject == "Zahlungserinnerung"
        assert "freundlich" in text.body.lower()
        assert text.dunning_level == DunningLevel.REMINDER

    def test_fallback_text_first(self, service: SmartDunningService):
        """1. Mahnung Fallback-Text."""
        text = service._generate_fallback_text(
            DunningLevel.FIRST, None, DunningTone.NEUTRAL, DunningStrategy.STANDARD
        )

        assert "1. Mahnung" in text.subject
        assert "7 Tage" in text.body

    def test_fallback_text_final(self, service: SmartDunningService):
        """Letzte Mahnung Fallback-Text."""
        text = service._generate_fallback_text(
            DunningLevel.FINAL, None, DunningTone.URGENT, DunningStrategy.STANDARD
        )

        assert "Letzte Mahnung" in text.subject
        assert "Inkasso" in text.body

    def test_fallback_text_inkasso(self, service: SmartDunningService):
        """Inkasso-Ankuendigung Fallback-Text."""
        text = service._generate_fallback_text(
            DunningLevel.INKASSO, None, DunningTone.FINAL, DunningStrategy.STANDARD
        )

        assert "Inkasso" in text.subject
        assert "Gerichtskosten" in text.body

    def test_fallback_has_full_text(self, service: SmartDunningService):
        """Fallback sollte vollstaendigen Text haben."""
        text = service._generate_fallback_text(
            DunningLevel.REMINDER, None, None, None
        )

        assert len(text.full_text) > 0
        assert text.greeting in text.full_text
        assert text.body in text.full_text
        assert text.closing in text.full_text


# =============================================================================
# Tests: A/B Testing
# =============================================================================

class TestABTesting:
    """Tests fuer A/B Testing."""

    @pytest.mark.asyncio
    async def test_create_ab_test(self, service: SmartDunningService):
        """A/B Test sollte erstellt werden koennen."""
        # Mock DB Session
        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        db.add = MagicMock()
        db.commit = AsyncMock()

        test = await service.create_ab_test(
            db=db,
            name="Test Strategy Comparison",
            description="Vergleich Standard vs Relationship",
            dunning_level=DunningLevel.FIRST,
            variants=[
                {"strategy": "standard", "tone": "neutral", "waiting_modifier": 1.0},
                {"strategy": "relationship", "tone": "friendly", "waiting_modifier": 1.2},
            ],
        )

        assert test.name == "Test Strategy Comparison"
        assert test.is_active is True
        assert len(test.variants) == 2
        assert test.variants[0].strategy == DunningStrategy.STANDARD
        assert test.variants[1].strategy == DunningStrategy.RELATIONSHIP

    @pytest.mark.asyncio
    async def test_get_ab_test_variant_consistent(self, service: SmartDunningService):
        """Varianten-Zuweisung sollte konsistent sein."""
        # Test erstellen
        test = ABTest(
            test_id="test123",
            name="Test",
            description="",
            variants=[
                ABTestVariant(
                    variant_id="test123_v0",
                    strategy=DunningStrategy.STANDARD,
                    tone=DunningTone.NEUTRAL,
                    waiting_period_modifier=1.0,
                    sample_count=0,
                    success_count=0,
                    conversion_rate=0.0,
                ),
                ABTestVariant(
                    variant_id="test123_v1",
                    strategy=DunningStrategy.RELATIONSHIP,
                    tone=DunningTone.FRIENDLY,
                    waiting_period_modifier=1.2,
                    sample_count=0,
                    success_count=0,
                    conversion_rate=0.0,
                ),
            ],
            is_active=True,
            start_date=datetime.now(timezone.utc),
            end_date=None,
            dunning_level=DunningLevel.FIRST,
            created_at=datetime.now(timezone.utc),
        )
        service._ab_tests["test123"] = test

        db = AsyncMock()
        entity_id = uuid.uuid4()

        # Mehrere Aufrufe sollten dieselbe Variante liefern
        variant1 = await service.get_ab_test_variant(db, DunningLevel.FIRST, entity_id)
        variant2 = await service.get_ab_test_variant(db, DunningLevel.FIRST, entity_id)

        assert variant1.variant_id == variant2.variant_id

    @pytest.mark.asyncio
    async def test_record_ab_test_result(self, service: SmartDunningService):
        """Ergebnisse sollten aufgezeichnet werden."""
        test = ABTest(
            test_id="test456",
            name="Test",
            description="",
            variants=[
                ABTestVariant(
                    variant_id="test456_v0",
                    strategy=DunningStrategy.STANDARD,
                    tone=DunningTone.NEUTRAL,
                    waiting_period_modifier=1.0,
                    sample_count=0,
                    success_count=0,
                    conversion_rate=0.0,
                ),
            ],
            is_active=True,
            start_date=datetime.now(timezone.utc),
            end_date=None,
            dunning_level=DunningLevel.FIRST,
            created_at=datetime.now(timezone.utc),
        )
        service._ab_tests["test456"] = test

        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        db.add = MagicMock()
        db.commit = AsyncMock()

        await service.record_ab_test_result(db, "test456_v0", success=True)
        await service.record_ab_test_result(db, "test456_v0", success=False)

        assert test.variants[0].sample_count == 2
        assert test.variants[0].success_count == 1
        assert test.variants[0].conversion_rate == 0.5


# =============================================================================
# Tests: Payment Behavior Description
# =============================================================================

class TestPaymentBehaviorDescription:
    """Tests fuer Zahlungsverhalten-Beschreibung."""

    def test_describe_punctual_payer(
        self,
        service: SmartDunningService,
        sample_customer_profile: CustomerProfile,
    ):
        """Puenktlicher Zahler sollte positiv beschrieben werden."""
        sample_customer_profile.avg_payment_delay = 0.0

        description = service._describe_payment_behavior(sample_customer_profile)

        assert "puenktlich" in description.lower()

    def test_describe_late_payer(
        self,
        service: SmartDunningService,
        sample_customer_profile: CustomerProfile,
    ):
        """Verspaeteter Zahler sollte entsprechend beschrieben werden."""
        sample_customer_profile.avg_payment_delay = 25.0

        description = service._describe_payment_behavior(sample_customer_profile)

        # Echte Beschreibung nutzt UTF-8-Umlaut: "... verspätet"
        assert "verspätet" in description.lower()

    def test_describe_with_trend(
        self,
        service: SmartDunningService,
        sample_customer_profile: CustomerProfile,
    ):
        """Trend sollte in Beschreibung einfliessen."""
        sample_customer_profile.payment_trend = TrendDirection.WORSENING

        description = service._describe_payment_behavior(sample_customer_profile)

        assert "verschlechtert" in description.lower()


# =============================================================================
# Tests: Singleton
# =============================================================================

class TestSingleton:
    """Tests fuer Singleton-Pattern."""

    def test_singleton_instance(self):
        """Sollte immer dieselbe Instanz zurueckgeben."""
        reset_smart_dunning_service()

        service1 = get_smart_dunning_service()
        service2 = get_smart_dunning_service()

        assert service1 is service2

    def test_singleton_reset(self):
        """Reset sollte neue Instanz erzeugen."""
        service1 = get_smart_dunning_service()
        reset_smart_dunning_service()
        service2 = get_smart_dunning_service()

        assert service1 is not service2
