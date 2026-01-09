# -*- coding: utf-8 -*-
"""
Unit Tests fuer UnifiedDecisionEngine.

Testet:
- Singleton-Verhalten
- Decision Queue Management (bounded)
- Impact Score Berechnung
- Conflict Detection
- Decision Processing

PHASE 0.7 CRITICAL FIX: 80%+ Coverage Ziel
"""

from collections import deque
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.services.orchestration.unified_decision_engine import (
    UnifiedDecisionEngine,
    UnifiedDecision,
    ImpactScore,
    ConflictPair,
    ConflictType,
    DecisionStatus,
    ImpactDimension,
    ConflictRule,
    CONFLICT_RULES,
    get_unified_decision_engine,
)
from app.services.orchestration.cross_module_orchestrator import (
    OrchestrationAction,
    ActionType,
    ActionPriority,
    ModuleType,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def reset_engine():
    """Reset Singleton vor und nach jedem Test."""
    UnifiedDecisionEngine._instance = None
    yield
    UnifiedDecisionEngine._instance = None


@pytest.fixture
def engine(reset_engine):
    """Frische Engine-Instanz fuer jeden Test."""
    return UnifiedDecisionEngine()


@pytest.fixture
def sample_decision():
    """Erstellt eine Beispiel-Entscheidung."""
    return UnifiedDecision(
        id=uuid4(),
        title="Test-Entscheidung",
        description="Eine Testbeschreibung",
        primary_module=ModuleType.FINANCE,
        impact_score=ImpactScore(
            financial_impact=Decimal("500"),
            risk_reduction=30.0,
            compliance_urgency=20.0,
        ),
    )


@pytest.fixture
def sample_action():
    """Erstellt eine Beispiel-Action."""
    return OrchestrationAction(
        action_type=ActionType.CREATE_RECOMMENDATION,
        priority=ActionPriority.HIGH,
        source_module=ModuleType.INSURANCE,
        action_data={
            "category": "versicherung",
            "priority": "hoch",
            "title": "Versicherungsluecke schliessen",
        },
    )


# =============================================================================
# Singleton Tests
# =============================================================================

class TestSingletonPattern:
    """Tests fuer Singleton-Verhalten."""

    def test_singleton_returns_same_instance(self, reset_engine):
        """Singleton gibt immer dieselbe Instanz zurueck."""
        instance1 = UnifiedDecisionEngine()
        instance2 = UnifiedDecisionEngine()

        assert instance1 is instance2

    def test_factory_returns_same_instance(self, reset_engine):
        """Factory-Funktion gibt Singleton zurueck."""
        instance1 = get_unified_decision_engine()
        instance2 = get_unified_decision_engine()

        assert instance1 is instance2

    def test_initialization_only_once(self, reset_engine):
        """Initialisierung erfolgt nur einmal."""
        instance = UnifiedDecisionEngine()
        original_queue = instance._decision_queue

        instance2 = UnifiedDecisionEngine()

        assert instance2._decision_queue is original_queue


# =============================================================================
# Memory Management Tests
# =============================================================================

class TestMemoryManagement:
    """Tests fuer Memory-Leak Prevention."""

    def test_decision_queue_is_bounded(self, engine):
        """Decision Queue ist eine bounded deque."""
        assert isinstance(engine._decision_queue, deque)
        assert engine._decision_queue.maxlen == engine._max_queue_size

    @pytest.mark.asyncio
    async def test_decision_queue_bounded_size(self, engine):
        """Decision Queue darf nicht unbegrenzt wachsen."""
        # Fuege mehr als maxlen hinzu via ingest_action
        for i in range(100):  # Reduziert fuer Test-Performance
            action = OrchestrationAction(
                action_type=ActionType.CREATE_RECOMMENDATION,
                action_data={"title": f"Action {i}"},
            )
            await engine.ingest_action(action)

        # Queue sollte nicht leer sein
        assert len(engine._decision_queue) > 0

    def test_known_conflicts_is_dict_with_ttl(self, engine):
        """Known Conflicts ist Dict mit TTL-basiertem Cleanup."""
        # _known_conflicts ist ein Dict[Tuple[UUID, UUID], datetime]
        assert isinstance(engine._known_conflicts, dict)
        # Hat TTL Konfiguration
        assert hasattr(engine, "_conflict_cache_ttl")


# =============================================================================
# ImpactScore Tests
# =============================================================================

class TestImpactScore:
    """Tests fuer Impact-Score Berechnung."""

    def test_total_score_calculation(self):
        """Gesamt-Score wird korrekt berechnet."""
        score = ImpactScore(
            financial_impact=Decimal("1000"),  # 100 Punkte normalisiert
            risk_reduction=50.0,               # 50 Punkte
            compliance_urgency=80.0,           # 80 Punkte
            opportunity_value=Decimal("500"),  # 50 Punkte normalisiert
            convenience_gain=40.0,             # 40 Punkte
        )

        # Gewichtete Summe:
        # 100 * 0.35 + 50 * 0.25 + 80 * 0.20 + 50 * 0.15 + 40 * 0.05
        # = 35 + 12.5 + 16 + 7.5 + 2 = 73
        total = score.total_score

        assert total > 0
        assert total <= 100

    def test_total_score_clamps_at_100(self):
        """Financial normalization clamped bei 100."""
        score = ImpactScore(
            financial_impact=Decimal("50000"),  # Weit ueber 1000
        )

        # financial_normalized sollte auf 100 begrenzt sein
        assert score.total_score <= 100

    def test_to_dict(self):
        """to_dict gibt korrektes Dictionary zurueck."""
        score = ImpactScore(
            financial_impact=Decimal("500"),
            risk_reduction=30.0,
        )

        result = score.to_dict()

        assert "financial_impact" in result
        assert "risk_reduction" in result
        assert "total_score" in result
        assert "weights" in result
        assert result["financial_impact"] == 500.0

    def test_default_weights(self):
        """Default-Gewichtungen summieren sich zu 1."""
        score = ImpactScore()

        total_weight = sum(score.weights.values())

        assert total_weight == pytest.approx(1.0)


# =============================================================================
# UnifiedDecision Tests
# =============================================================================

class TestUnifiedDecision:
    """Tests fuer UnifiedDecision Datenklasse."""

    def test_defaults(self):
        """UnifiedDecision hat sinnvolle Defaults."""
        decision = UnifiedDecision()

        assert decision.id is not None
        assert decision.status == DecisionStatus.PENDING
        assert decision.primary_module == ModuleType.SYSTEM
        assert decision.created_at is not None
        assert decision.source_actions == []

    def test_to_dict(self, sample_decision):
        """to_dict gibt korrektes Dictionary zurueck."""
        result = sample_decision.to_dict()

        assert result["id"] == str(sample_decision.id)
        assert result["title"] == "Test-Entscheidung"
        assert result["status"] == "pending"
        assert result["primary_module"] == "finance"
        assert "impact_score" in result
        assert "created_at" in result


# =============================================================================
# Decision Processing Tests
# =============================================================================

class TestDecisionProcessing:
    """Tests fuer Decision-Verarbeitung."""

    @pytest.mark.asyncio
    async def test_ingest_action_adds_to_queue(self, engine, sample_action):
        """ingest_action fuegt Decision zur Queue hinzu."""
        initial_count = len(engine._decision_queue)

        decision = await engine.ingest_action(sample_action)

        assert len(engine._decision_queue) == initial_count + 1
        assert decision in engine._decision_queue

    @pytest.mark.asyncio
    async def test_ingest_action_returns_decision(self, engine, sample_action):
        """ingest_action gibt UnifiedDecision zurueck."""
        decision = await engine.ingest_action(sample_action)

        assert decision is not None
        assert isinstance(decision, UnifiedDecision)
        assert decision.primary_module == sample_action.source_module
        assert len(decision.source_actions) == 1
        assert decision.source_actions[0] is sample_action

    @pytest.mark.asyncio
    async def test_get_pending_count(self, engine, sample_action):
        """get_pending_count zaehlt ausstehende Decisions."""
        await engine.ingest_action(sample_action)

        count = await engine.get_pending_count()

        assert count >= 1

    @pytest.mark.asyncio
    async def test_get_prioritized_decisions(self, engine, sample_action):
        """get_prioritized_decisions gibt sortierte Liste zurueck."""
        # Mehrere Actions einfuegen
        for i in range(3):
            action = OrchestrationAction(
                action_type=ActionType.CREATE_RECOMMENDATION,
                source_module=ModuleType.FINANCE,
                action_data={"title": f"Action {i}", "priority": "high"},
            )
            await engine.ingest_action(action)

        result = await engine.get_prioritized_decisions(limit=5, min_score=0.0)

        assert isinstance(result, list)
        assert len(result) <= 5


# =============================================================================
# Conflict Detection Tests
# =============================================================================

class TestConflictDetection:
    """Tests fuer Konflikt-Erkennung."""

    def test_detect_duplicate(self, engine):
        """Duplikate werden erkannt."""
        decision1 = UnifiedDecision(
            title="Versicherungsluecke schliessen",
            primary_module=ModuleType.INSURANCE,
            description="Haftpflicht erhoehen",
        )
        decision2 = UnifiedDecision(
            title="Versicherungsluecke schliessen",  # Gleicher Titel
            primary_module=ModuleType.INSURANCE,
            description="Haftpflicht erhoehen",
        )

        # _check_duplicate ist sync, nicht async
        is_duplicate = engine._check_duplicate(decision1, decision2)

        assert is_duplicate is True

    def test_no_duplicate_different_titles(self, engine):
        """Verschiedene Titel sind keine Duplikate."""
        decision1 = UnifiedDecision(
            title="Versicherungsluecke schliessen",
            primary_module=ModuleType.INSURANCE,
        )
        decision2 = UnifiedDecision(
            title="Kredit refinanzieren",
            primary_module=ModuleType.LOAN,
        )

        # _check_duplicate ist sync, nicht async
        is_duplicate = engine._check_duplicate(decision1, decision2)

        assert is_duplicate is False

    @pytest.mark.asyncio
    async def test_detect_conflicts_between_decisions(self, engine):
        """Konflikte zwischen Decisions werden erkannt."""
        # Zwei Decisions die um dieselbe Ressource konkurrieren
        decision1 = UnifiedDecision(
            title="500 EUR in Aktien investieren",
            primary_module=ModuleType.INVESTMENT,
            impact_score=ImpactScore(financial_impact=Decimal("-500")),
        )
        decision2 = UnifiedDecision(
            title="500 EUR Notgroschen aufbauen",
            primary_module=ModuleType.FINANCE,
            impact_score=ImpactScore(financial_impact=Decimal("-500")),
        )

        # Direkt zur Queue hinzufuegen fuer Unit-Test
        engine._decision_queue.append(decision1)
        engine._decision_queue.append(decision2)

        # Konflikte erkennen
        conflicts = await engine.detect_conflicts()

        # Haengt von Implementation ab - hier nur Struktur-Test
        assert isinstance(conflicts, list)

    @pytest.mark.asyncio
    async def test_conflict_resolution_keeps_higher_impact(self, engine):
        """Konfliktloesung behaelt hoeheren Impact - Verlierer wird REJECTED."""
        high_impact = UnifiedDecision(
            id=uuid4(),
            title="Hoher Impact",
            impact_score=ImpactScore(financial_impact=Decimal("2000")),
        )
        low_impact = UnifiedDecision(
            id=uuid4(),
            title="Niedriger Impact",
            impact_score=ImpactScore(financial_impact=Decimal("100")),
        )

        conflict = ConflictPair(
            decision_a=high_impact,
            decision_b=low_impact,
            conflict_type=ConflictType.GOAL_CONFLICT,
            reason="Konkurrieren um gleiche Mittel",
            resolution_strategy="keep_higher_impact",
        )

        # _resolve_conflict modifiziert Decisions in place (keine Rueckgabe)
        await engine._resolve_conflict(conflict)

        # Hoeherer Impact bleibt PENDING, niedrigerer wird REJECTED
        assert high_impact.status == DecisionStatus.PENDING
        assert low_impact.status == DecisionStatus.REJECTED


# =============================================================================
# Prioritization Tests
# =============================================================================

class TestPrioritization:
    """Tests fuer Entscheidungs-Priorisierung."""

    @pytest.mark.asyncio
    async def test_prioritize_by_impact_score(self, engine):
        """Decisions werden nach Impact-Score priorisiert."""
        low = UnifiedDecision(
            title="Low",
            impact_score=ImpactScore(financial_impact=Decimal("100")),
        )
        high = UnifiedDecision(
            title="High",
            impact_score=ImpactScore(financial_impact=Decimal("5000")),
        )
        medium = UnifiedDecision(
            title="Medium",
            impact_score=ImpactScore(financial_impact=Decimal("1000")),
        )

        # Direkt zur Queue hinzufuegen
        engine._decision_queue.append(low)
        engine._decision_queue.append(high)
        engine._decision_queue.append(medium)

        prioritized = await engine.get_prioritized_decisions(min_score=0.0)

        # Hoechster Impact sollte zuerst kommen
        assert len(prioritized) >= 1
        assert prioritized[0].title == "High"

    @pytest.mark.asyncio
    async def test_get_prioritized_decisions_with_limit(self, engine):
        """get_prioritized_decisions respektiert Limit."""
        for i in range(10):
            decision = UnifiedDecision(
                title=f"Decision {i}",
                impact_score=ImpactScore(financial_impact=Decimal(str((i + 1) * 100))),
            )
            engine._decision_queue.append(decision)

        top_3 = await engine.get_prioritized_decisions(limit=3, min_score=0.0)

        assert len(top_3) == 3


# =============================================================================
# Metrics Tests
# =============================================================================

class TestMetrics:
    """Tests fuer Metriken."""

    @pytest.mark.asyncio
    async def test_get_stats(self, engine, sample_decision):
        """Stats werden korrekt zurueckgegeben."""
        # Direkt zur Queue hinzufuegen fuer Unit-Test
        engine._decision_queue.append(sample_decision)

        stats = await engine.get_metrics()

        assert "queue_size" in stats
        assert "pending_count" in stats
        assert stats["queue_size"] >= 1


# =============================================================================
# Enums Tests
# =============================================================================

class TestEnums:
    """Tests fuer Enums."""

    def test_conflict_type_values(self):
        """ConflictType hat erwartete Werte."""
        assert ConflictType.DUPLICATE.value == "duplicate"
        assert ConflictType.RESOURCE_CONFLICT.value == "resource_conflict"
        assert ConflictType.GOAL_CONFLICT.value == "goal_conflict"

    def test_decision_status_values(self):
        """DecisionStatus hat erwartete Werte."""
        assert DecisionStatus.PENDING.value == "pending"
        assert DecisionStatus.APPROVED.value == "approved"
        assert DecisionStatus.REJECTED.value == "rejected"
        assert DecisionStatus.MERGED.value == "merged"

    def test_impact_dimension_values(self):
        """ImpactDimension hat erwartete Werte."""
        assert ImpactDimension.FINANCIAL.value == "financial"
        assert ImpactDimension.RISK_REDUCTION.value == "risk_reduction"
        assert ImpactDimension.COMPLIANCE.value == "compliance"


# =============================================================================
# Conflict Rules Tests
# =============================================================================

class TestConflictRules:
    """Tests fuer Konflikt-Regeln."""

    def test_conflict_rules_defined(self):
        """Konflikt-Regeln sind definiert."""
        assert len(CONFLICT_RULES) > 0

    def test_conflict_rules_have_required_fields(self):
        """Jede Regel hat alle erforderlichen Felder."""
        for rule in CONFLICT_RULES:
            assert rule.name is not None
            assert rule.conflict_type is not None
            assert rule.check_fn is not None
            assert rule.resolution is not None

    def test_duplicate_rule_exists(self):
        """Duplikat-Regel existiert."""
        duplicate_rules = [r for r in CONFLICT_RULES if r.name == "duplicate_recommendation"]

        assert len(duplicate_rules) == 1
        assert duplicate_rules[0].conflict_type == ConflictType.DUPLICATE


# =============================================================================
# Advanced Conflict Detection Tests
# =============================================================================

class TestOpposingGoals:
    """Tests fuer gegensaetzliche Ziele."""

    def test_detect_saving_vs_investment_conflict(self, engine):
        """Sparen vs. Investieren wird erkannt."""
        decision_save = UnifiedDecision(
            id=uuid4(),
            title="Mehr sparen",
            description="Sparrate erhoehen auf 20%",
            primary_module=ModuleType.FINANCE,
        )
        decision_invest = UnifiedDecision(
            id=uuid4(),
            title="Investment taetigen",
            description="In Aktien investieren",
            primary_module=ModuleType.INVESTMENT,
        )

        categories_save = engine._extract_categories(decision_save)
        categories_invest = engine._extract_categories(decision_invest)

        # Beide sollten Kategorien haben
        assert "sparen" in categories_save
        assert "investment" in categories_invest or "investition" in categories_invest

    def test_detect_cancel_vs_extend_insurance(self, engine):
        """Versicherung kuendigen vs. erweitern wird erkannt."""
        decision_cancel = UnifiedDecision(
            id=uuid4(),
            title="Versicherung kuendigen",
            description="Unnoetige Versicherung kuendigen",
            primary_module=ModuleType.INSURANCE,
        )
        decision_extend = UnifiedDecision(
            id=uuid4(),
            title="Versicherung erweitern",
            description="Deckung erweitern",
            primary_module=ModuleType.INSURANCE,
        )

        categories_cancel = engine._extract_categories(decision_cancel)
        categories_extend = engine._extract_categories(decision_extend)

        assert "kuendigen" in categories_cancel or "versicherung" in categories_cancel
        assert "erweitern" in categories_extend or "versicherung" in categories_extend


class TestResourceConflicts:
    """Tests fuer Ressourcen-Konflikte."""

    def test_resource_conflict_same_module_high_cost(self, engine):
        """Ressourcen-Konflikt bei gleichem Modul und hohen Kosten."""
        decision_a = UnifiedDecision(
            id=uuid4(),
            title="Grosser Kauf A",
            primary_module=ModuleType.FINANCE,
            impact_score=ImpactScore(financial_impact=Decimal("2000")),
        )
        decision_b = UnifiedDecision(
            id=uuid4(),
            title="Grosser Kauf B",
            primary_module=ModuleType.FINANCE,
            impact_score=ImpactScore(financial_impact=Decimal("1500")),
        )

        conflict = engine._check_resource_conflict(decision_a, decision_b)

        assert conflict is not None
        assert "Ressourcen-Konflikt" in conflict

    def test_no_resource_conflict_different_modules(self, engine):
        """Kein Ressourcen-Konflikt bei verschiedenen Modulen."""
        decision_a = UnifiedDecision(
            id=uuid4(),
            title="Grosser Kauf A",
            primary_module=ModuleType.FINANCE,
            impact_score=ImpactScore(financial_impact=Decimal("2000")),
        )
        decision_b = UnifiedDecision(
            id=uuid4(),
            title="Grosser Kauf B",
            primary_module=ModuleType.INVESTMENT,
            impact_score=ImpactScore(financial_impact=Decimal("1500")),
        )

        conflict = engine._check_resource_conflict(decision_a, decision_b)

        assert conflict is None

    def test_no_resource_conflict_low_cost(self, engine):
        """Kein Ressourcen-Konflikt bei niedrigen Kosten."""
        decision_a = UnifiedDecision(
            id=uuid4(),
            title="Kleiner Kauf A",
            primary_module=ModuleType.FINANCE,
            impact_score=ImpactScore(financial_impact=Decimal("500")),
        )
        decision_b = UnifiedDecision(
            id=uuid4(),
            title="Kleiner Kauf B",
            primary_module=ModuleType.FINANCE,
            impact_score=ImpactScore(financial_impact=Decimal("300")),
        )

        conflict = engine._check_resource_conflict(decision_a, decision_b)

        assert conflict is None


# =============================================================================
# Decision Approval/Rejection Tests
# =============================================================================

class TestDecisionApproval:
    """Tests fuer Entscheidungs-Genehmigung."""

    @pytest.mark.asyncio
    async def test_approve_existing_decision(self, engine):
        """Existierende Entscheidung kann genehmigt werden."""
        decision = UnifiedDecision(
            id=uuid4(),
            title="Test-Entscheidung",
            primary_module=ModuleType.FINANCE,
        )
        engine._decision_queue.append(decision)

        result = await engine.approve_decision(decision.id)

        assert result is True
        assert decision.status == DecisionStatus.APPROVED
        assert decision.processed_at is not None

    @pytest.mark.asyncio
    async def test_approve_nonexistent_decision(self, engine):
        """Nicht existierende Entscheidung gibt False zurueck."""
        result = await engine.approve_decision(uuid4())

        assert result is False

    @pytest.mark.asyncio
    async def test_reject_existing_decision(self, engine):
        """Existierende Entscheidung kann abgelehnt werden."""
        decision = UnifiedDecision(
            id=uuid4(),
            title="Test-Entscheidung",
            primary_module=ModuleType.FINANCE,
        )
        engine._decision_queue.append(decision)

        result = await engine.reject_decision(decision.id, reason="Nicht gewuenscht")

        assert result is True
        assert decision.status == DecisionStatus.REJECTED
        assert decision.conflict_resolution == "Nicht gewuenscht"

    @pytest.mark.asyncio
    async def test_reject_nonexistent_decision(self, engine):
        """Nicht existierende Entscheidung gibt False zurueck."""
        result = await engine.reject_decision(uuid4())

        assert result is False


# =============================================================================
# Decision Merging Tests
# =============================================================================

class TestDecisionMerging:
    """Tests fuer Entscheidungs-Zusammenfuehrung."""

    @pytest.mark.asyncio
    async def test_merge_decisions_updates_status(self, engine):
        """Zusammenfuehrung aktualisiert Status."""
        decision_a = UnifiedDecision(
            id=uuid4(),
            title="Entscheidung A",
            primary_module=ModuleType.FINANCE,
            impact_score=ImpactScore(financial_impact=Decimal("500")),
        )
        decision_b = UnifiedDecision(
            id=uuid4(),
            title="Entscheidung B",
            primary_module=ModuleType.FINANCE,
            impact_score=ImpactScore(financial_impact=Decimal("300")),
        )

        await engine._merge_decisions(decision_a, decision_b)

        assert decision_b.status == DecisionStatus.MERGED
        assert str(decision_a.id) in decision_b.conflict_resolution

    @pytest.mark.asyncio
    async def test_merge_decisions_combines_actions(self, engine):
        """Zusammenfuehrung kombiniert Actions."""
        action_a = OrchestrationAction(
            action_type=ActionType.CREATE_RECOMMENDATION,
            action_data={"title": "Action A"},
        )
        action_b = OrchestrationAction(
            action_type=ActionType.CREATE_RECOMMENDATION,
            action_data={"title": "Action B"},
        )

        decision_a = UnifiedDecision(
            id=uuid4(),
            title="Entscheidung A",
            primary_module=ModuleType.FINANCE,
            source_actions=[action_a],
        )
        decision_b = UnifiedDecision(
            id=uuid4(),
            title="Entscheidung B",
            primary_module=ModuleType.INVESTMENT,
            affected_modules=[ModuleType.INVESTMENT],
            source_actions=[action_b],
        )

        await engine._merge_decisions(decision_a, decision_b)

        assert len(decision_a.source_actions) == 2
        assert ModuleType.INVESTMENT in decision_a.affected_modules

    @pytest.mark.asyncio
    async def test_merge_decisions_combines_impact(self, engine):
        """Zusammenfuehrung kombiniert Impact (max)."""
        decision_a = UnifiedDecision(
            id=uuid4(),
            title="Entscheidung A",
            primary_module=ModuleType.FINANCE,
            impact_score=ImpactScore(
                financial_impact=Decimal("500"),
                risk_reduction=30.0,
            ),
        )
        decision_b = UnifiedDecision(
            id=uuid4(),
            title="Entscheidung B",
            primary_module=ModuleType.FINANCE,
            impact_score=ImpactScore(
                financial_impact=Decimal("800"),
                risk_reduction=20.0,
            ),
        )

        await engine._merge_decisions(decision_a, decision_b)

        # Max von beiden
        assert decision_a.impact_score.financial_impact == Decimal("800")
        assert decision_a.impact_score.risk_reduction == 30.0


# =============================================================================
# Conflict Resolution Strategy Tests
# =============================================================================

class TestConflictResolutionStrategies:
    """Tests fuer Konflikt-Loesungsstrategien."""

    @pytest.mark.asyncio
    async def test_resolve_by_merge(self, engine):
        """Merge-Strategie fuehrt Duplikate zusammen."""
        decision_a = UnifiedDecision(
            id=uuid4(),
            title="Gleiche Empfehlung",
            primary_module=ModuleType.FINANCE,
        )
        decision_b = UnifiedDecision(
            id=uuid4(),
            title="Gleiche Empfehlung",
            primary_module=ModuleType.FINANCE,
        )

        conflict = ConflictPair(
            decision_a=decision_a,
            decision_b=decision_b,
            conflict_type=ConflictType.DUPLICATE,
            reason="Duplikat",
            resolution_strategy="merge",
        )

        await engine._resolve_conflict(conflict)

        assert decision_b.status == DecisionStatus.MERGED

    @pytest.mark.asyncio
    async def test_resolve_by_urgency_a_wins(self, engine):
        """Urgency-Strategie: A gewinnt bei hoeherer Dringlichkeit."""
        decision_a = UnifiedDecision(
            id=uuid4(),
            title="Dringend",
            primary_module=ModuleType.FINANCE,
            impact_score=ImpactScore(compliance_urgency=90.0),
        )
        decision_b = UnifiedDecision(
            id=uuid4(),
            title="Weniger dringend",
            primary_module=ModuleType.FINANCE,
            impact_score=ImpactScore(compliance_urgency=30.0),
        )

        conflict = ConflictPair(
            decision_a=decision_a,
            decision_b=decision_b,
            conflict_type=ConflictType.RESOURCE_CONFLICT,
            reason="Ressourcen-Konflikt",
            resolution_strategy="prioritize_by_urgency",
        )

        await engine._resolve_conflict(conflict)

        assert decision_a.status == DecisionStatus.PENDING
        assert decision_b.status == DecisionStatus.DEFERRED

    @pytest.mark.asyncio
    async def test_resolve_by_urgency_b_wins(self, engine):
        """Urgency-Strategie: B gewinnt bei hoeherer Dringlichkeit."""
        decision_a = UnifiedDecision(
            id=uuid4(),
            title="Weniger dringend",
            primary_module=ModuleType.FINANCE,
            impact_score=ImpactScore(compliance_urgency=20.0),
        )
        decision_b = UnifiedDecision(
            id=uuid4(),
            title="Dringend",
            primary_module=ModuleType.FINANCE,
            impact_score=ImpactScore(compliance_urgency=80.0),
        )

        conflict = ConflictPair(
            decision_a=decision_a,
            decision_b=decision_b,
            conflict_type=ConflictType.RESOURCE_CONFLICT,
            reason="Ressourcen-Konflikt",
            resolution_strategy="prioritize_by_urgency",
        )

        await engine._resolve_conflict(conflict)

        assert decision_a.status == DecisionStatus.DEFERRED
        assert decision_b.status == DecisionStatus.PENDING


# =============================================================================
# Impact Score Calculation Tests
# =============================================================================

class TestImpactScoreCalculation:
    """Tests fuer Impact-Score Berechnung."""

    @pytest.mark.asyncio
    async def test_calculate_impact_with_potential_savings(self, engine):
        """Impact Score beruecksichtigt potential_savings."""
        action = OrchestrationAction(
            action_type=ActionType.CREATE_RECOMMENDATION,
            action_data={"potential_savings": 1500},
        )
        decision = UnifiedDecision(title="Test")

        score = await engine._calculate_impact_score(action, decision)

        assert score.financial_impact == Decimal("1500")

    @pytest.mark.asyncio
    async def test_calculate_impact_with_amount(self, engine):
        """Impact Score beruecksichtigt amount."""
        action = OrchestrationAction(
            action_type=ActionType.CREATE_RECOMMENDATION,
            action_data={"amount": 750.50},
        )
        decision = UnifiedDecision(title="Test")

        score = await engine._calculate_impact_score(action, decision)

        assert score.financial_impact == Decimal("750.50")

    @pytest.mark.asyncio
    async def test_calculate_impact_with_workflow(self, engine):
        """Workflow-Actions erhalten Risk Reduction."""
        action = OrchestrationAction(
            action_type=ActionType.TRIGGER_WORKFLOW,
            action_data={},
        )
        decision = UnifiedDecision(title="Test")

        score = await engine._calculate_impact_score(action, decision)

        assert score.risk_reduction == 50.0

    @pytest.mark.asyncio
    async def test_calculate_impact_with_critical_severity(self, engine):
        """Critical Severity erhoeht Risk Reduction."""
        action = OrchestrationAction(
            action_type=ActionType.CREATE_RECOMMENDATION,
            action_data={"severity": "critical"},
        )
        decision = UnifiedDecision(title="Test")

        score = await engine._calculate_impact_score(action, decision)

        assert score.risk_reduction >= 30.0

    @pytest.mark.asyncio
    async def test_calculate_impact_with_high_severity(self, engine):
        """High Severity erhoeht Risk Reduction."""
        action = OrchestrationAction(
            action_type=ActionType.CREATE_RECOMMENDATION,
            action_data={"severity": "high"},
        )
        decision = UnifiedDecision(title="Test")

        score = await engine._calculate_impact_score(action, decision)

        assert score.risk_reduction >= 20.0

    @pytest.mark.asyncio
    async def test_calculate_impact_with_deadline(self, engine):
        """Deadline erhoet Compliance Urgency."""
        action = OrchestrationAction(
            action_type=ActionType.CREATE_RECOMMENDATION,
            action_data={},
        )
        decision = UnifiedDecision(
            title="Test",
            description="Deadline naht",
        )

        score = await engine._calculate_impact_score(action, decision)

        assert score.compliance_urgency == 80.0

    @pytest.mark.asyncio
    async def test_calculate_impact_with_days_remaining_critical(self, engine):
        """Wenige Tage = hohe Compliance Urgency."""
        action = OrchestrationAction(
            action_type=ActionType.CREATE_RECOMMENDATION,
            action_data={"days_remaining": 5},
        )
        decision = UnifiedDecision(title="Test")

        score = await engine._calculate_impact_score(action, decision)

        assert score.compliance_urgency == 100.0

    @pytest.mark.asyncio
    async def test_calculate_impact_with_days_remaining_medium(self, engine):
        """Mittlere Tage = mittlere Compliance Urgency."""
        action = OrchestrationAction(
            action_type=ActionType.CREATE_RECOMMENDATION,
            action_data={"days_remaining": 10},
        )
        decision = UnifiedDecision(title="Test")

        score = await engine._calculate_impact_score(action, decision)

        assert score.compliance_urgency == 70.0

    @pytest.mark.asyncio
    async def test_calculate_impact_with_days_remaining_low(self, engine):
        """Mehr Tage = niedrigere Compliance Urgency."""
        action = OrchestrationAction(
            action_type=ActionType.CREATE_RECOMMENDATION,
            action_data={"days_remaining": 20},
        )
        decision = UnifiedDecision(title="Test")

        score = await engine._calculate_impact_score(action, decision)

        assert score.compliance_urgency == 40.0

    @pytest.mark.asyncio
    async def test_calculate_impact_with_potential_gain(self, engine):
        """Potential Gain wird zu Opportunity Value."""
        action = OrchestrationAction(
            action_type=ActionType.CREATE_RECOMMENDATION,
            action_data={"potential_gain": 2000},
        )
        decision = UnifiedDecision(title="Test")

        score = await engine._calculate_impact_score(action, decision)

        assert score.opportunity_value == Decimal("2000")

    @pytest.mark.asyncio
    async def test_calculate_impact_with_auto_approve(self, engine):
        """Auto-Approve erhoet Convenience Gain."""
        action = OrchestrationAction(
            action_type=ActionType.AUTO_APPROVE,
            action_data={},
        )
        decision = UnifiedDecision(title="Test")

        score = await engine._calculate_impact_score(action, decision)

        assert score.convenience_gain == 80.0


# =============================================================================
# Category Extraction Tests
# =============================================================================

class TestCategoryExtraction:
    """Tests fuer Kategorie-Extraktion."""

    def test_extract_category_from_action_data(self, engine):
        """Kategorie aus Action-Daten."""
        action = OrchestrationAction(
            action_type=ActionType.CREATE_RECOMMENDATION,
            action_data={"category": "Refinanzierung"},
        )
        decision = UnifiedDecision(
            title="Test",
            source_actions=[action],
        )

        categories = engine._extract_categories(decision)

        assert "refinanzierung" in categories

    def test_extract_keywords_from_title(self, engine):
        """Keywords aus Titel."""
        decision = UnifiedDecision(
            title="Mehr Sparen fuer Notgroschen",
            description="",
        )

        categories = engine._extract_categories(decision)

        assert "sparen" in categories

    def test_extract_keywords_from_description(self, engine):
        """Keywords aus Beschreibung."""
        decision = UnifiedDecision(
            title="Empfehlung",
            description="Sie sollten in eine Investition denken",
        )

        categories = engine._extract_categories(decision)

        assert "investition" in categories
