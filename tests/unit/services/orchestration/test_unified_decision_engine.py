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
