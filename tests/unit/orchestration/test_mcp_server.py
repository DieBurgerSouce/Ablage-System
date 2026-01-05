"""Unit tests for orchestration_server.py (MCP Server).

Tests für den MCP Server mit Task Routing, Quality Gates und Metrics.

Hinweis: Diese Tests sind unabhängig vom Haupt-conftest.py und importieren
direkt aus dem MCP-Server Verzeichnis.
"""

import pytest
import asyncio
import json
import re
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
import sys
from pathlib import Path
from dataclasses import asdict

# Konfigurations-Marker für pytest
pytestmark = pytest.mark.unit

# Add MCP server to path BEFORE imports
_mcp_path = str(Path(__file__).parent.parent.parent.parent / ".claude" / "mcp-server")
if _mcp_path not in sys.path:
    sys.path.insert(0, _mcp_path)

from orchestration_server import (
    TaskRouting,
    CachedDecision,
    TaskClassifier,
    DecisionCache,
    QualityGate,
    QualityResult,
    HaikuQualityGate,
    OrchestrationMetrics,
    OrchestrationMCPServer,
    ModelTier,
)


class TestTaskRouting:
    """Tests für TaskRouting dataclass."""

    def test_default_values(self):
        """TaskRouting sollte korrekte Default-Werte haben."""
        routing = TaskRouting(
            agent_name="test-agent",
            tier="sonnet",
            confidence=0.85,
            reasoning="Test reasoning"
        )

        assert routing.agent_name == "test-agent"
        assert routing.tier == "sonnet"
        assert routing.confidence == 0.85
        assert routing.specialty is None
        # KRITISCH: Dies testet den Mutable Default Fix
        assert routing.cached_decisions == []
        assert isinstance(routing.cached_decisions, list)

    def test_mutable_default_independence(self):
        """Jede TaskRouting Instanz sollte unabhängige cached_decisions haben."""
        # KRITISCH: Testet dass der Mutable Default Bug gefixt ist
        routing1 = TaskRouting("agent1", "sonnet", 0.8, "r1")
        routing2 = TaskRouting("agent2", "opus", 0.9, "r2")

        routing1.cached_decisions.append({"test": "decision1"})

        # routing2 sollte NICHT beeinflusst werden
        assert len(routing2.cached_decisions) == 0

    def test_with_specialty(self):
        """TaskRouting mit specialty sollte korrekt funktionieren."""
        routing = TaskRouting(
            agent_name="ocr-specialist",
            tier="opus",
            confidence=0.95,
            reasoning="OCR-spezifischer Task",
            specialty="OCR Pipeline Optimierung"
        )

        assert routing.specialty == "OCR Pipeline Optimierung"

    def test_with_cached_decisions(self):
        """TaskRouting mit cached_decisions sollte korrekt funktionieren."""
        routing = TaskRouting(
            agent_name="test-agent",
            tier="sonnet",
            confidence=0.85,
            reasoning="Test",
            cached_decisions=[{"decision": "test", "confidence": 0.9}]
        )

        assert len(routing.cached_decisions) == 1
        assert routing.cached_decisions[0]["decision"] == "test"


class TestCachedDecision:
    """Tests für CachedDecision dataclass."""

    def test_cached_decision_creation(self):
        """CachedDecision sollte korrekt erstellt werden."""
        now = datetime.now()
        cached = CachedDecision(
            task_description="Implement feature",
            decision="Use strategy pattern",
            reasoning="Best for extensibility",
            affected_files=["app/service.py"],
            model_used="opus",
            confidence=0.95,
            timestamp=now
        )

        assert cached.task_description == "Implement feature"
        assert cached.model_used == "opus"
        assert cached.confidence == 0.95
        assert cached.timestamp == now

    def test_to_dict(self):
        """to_dict sollte korrekte Struktur zurückgeben."""
        now = datetime.now()
        cached = CachedDecision(
            task_description="Test task",
            decision="Test decision",
            reasoning="Test reasoning",
            affected_files=["file.py"],
            model_used="sonnet",
            confidence=0.85,
            timestamp=now
        )

        d = cached.to_dict()

        assert d["task_description"] == "Test task"
        assert d["decision"] == "Test decision"
        assert d["model_used"] == "sonnet"
        assert d["confidence"] == 0.85
        assert d["timestamp"] == now.isoformat()
        assert "file.py" in d["affected_files"]


class TestQualityResult:
    """Tests für QualityResult dataclass."""

    def test_quality_result_creation(self):
        """QualityResult sollte korrekt erstellt werden."""
        result = QualityResult(
            checks_passed=["syntax", "type_hints", "german_language"],
            checks_failed=[],
            quality_score=0.92,
            should_escalate=False,
            threshold=0.85
        )

        assert "syntax" in result.checks_passed
        assert len(result.checks_failed) == 0
        assert result.quality_score == 0.92
        assert result.should_escalate is False

    def test_quality_result_with_escalation(self):
        """QualityResult mit Eskalation sollte korrekt sein."""
        result = QualityResult(
            checks_passed=["syntax"],
            checks_failed=["type_hints", "german_language"],
            quality_score=0.33,
            should_escalate=True,
            threshold=0.85
        )

        assert result.should_escalate is True
        assert len(result.checks_failed) == 2


class TestTaskClassifier:
    """Tests für TaskClassifier Klasse."""

    @pytest.fixture
    def classifier(self):
        """Provide TaskClassifier instance."""
        return TaskClassifier()

    def test_classify_haiku_safe_typo(self, classifier):
        """Typo-Fixes sollten als Haiku klassifiziert werden."""
        result = classifier.classify("fix typo in config")

        # Typo-Fixes sind Haiku-safe
        assert result.tier == "haiku"
        assert result.confidence > 0.9

    def test_classify_haiku_safe_format(self, classifier):
        """Format-Tasks sollten als Haiku klassifiziert werden."""
        result = classifier.classify("format code with black")

        assert result.tier == "haiku"

    def test_classify_sonnet_implementation(self, classifier):
        """Implementation-Tasks sollten als Sonnet klassifiziert werden."""
        result = classifier.classify("implement user authentication with JWT tokens")

        # Implementation sollte mindestens Sonnet sein
        assert result.tier in ["sonnet", "opus"]

    def test_classify_opus_architecture(self, classifier):
        """Architektur-Tasks sollten als Opus klassifiziert werden."""
        result = classifier.classify(
            "Design and implement a fault-tolerant distributed caching system",
            ["app/core/cache.py", "app/services/cache_service.py", "infrastructure/redis.py"]
        )

        # Architektur sollte Opus sein
        assert result.tier == "opus"

    def test_haiku_blacklist_prevents_haiku(self, classifier):
        """Blacklisted Keywords sollten Haiku verhindern."""
        # Security task - auf Blacklist
        result = classifier.classify("fix security vulnerability")

        # Sollte NICHT Haiku sein
        assert result.tier != "haiku"

    def test_is_haiku_safe_method(self, classifier):
        """_is_haiku_safe sollte korrekt funktionieren."""
        # Safe
        is_safe, reason = classifier._is_haiku_safe("fix typo in readme")
        assert is_safe is True

        # Not safe (blacklisted)
        is_safe, reason = classifier._is_haiku_safe("implement user auth")
        assert is_safe is False

    def test_tier_to_agent_mapping(self, classifier):
        """_tier_to_agent sollte korrekte Agenten zurückgeben."""
        assert classifier._tier_to_agent(ModelTier.HAIKU_SIMPLE) == "haiku-task"
        assert classifier._tier_to_agent(ModelTier.SONNET_CAPABLE) == "sonnet-implementation"
        assert classifier._tier_to_agent(ModelTier.OPUS_REQUIRED) == "opus-task"


class TestDecisionCache:
    """Tests für DecisionCache Klasse."""

    @pytest.fixture
    def cache(self):
        """Provide DecisionCache instance."""
        return DecisionCache(ttl_days=7)

    def test_store_and_find(self, cache):
        """Gespeicherte Entscheidungen sollten gefunden werden."""
        cache.store(
            task_description="Implement auth",
            decision="Use JWT",
            reasoning="Industry standard",
            affected_files=["app/auth.py"],
            model_used="opus",
            confidence=0.95
        )

        relevant = cache.find_relevant("Implement authentication", ["app/auth.py"])

        assert len(relevant) >= 1
        assert relevant[0].decision == "Use JWT"

    def test_ttl_expiration(self, cache):
        """Abgelaufene Einträge sollten nicht gefunden werden."""
        # Store with manipulated timestamp (expired)
        cached = CachedDecision(
            task_description="Old task",
            decision="Old decision",
            reasoning="Old reasoning",
            affected_files=["old.py"],
            model_used="opus",
            confidence=0.9,
            timestamp=datetime.now() - timedelta(days=10)  # Älter als TTL
        )
        cache.cache.append(cached)

        # Should not find expired entry
        relevant = cache.find_relevant("Old task", ["old.py"])
        assert len(relevant) == 0

    def test_clear(self, cache):
        """clear() sollte alle Einträge löschen."""
        cache.store("test", "test", "test", ["test.py"], "opus", 0.9)
        assert len(cache.cache) > 0

        cache.clear()
        assert len(cache.cache) == 0


class TestQualityGate:
    """Tests für QualityGate Klasse."""

    @pytest.fixture
    def gate(self):
        """Provide QualityGate instance."""
        return QualityGate()

    def test_valid_python_syntax(self, gate):
        """Gültiger Python-Code sollte Syntax-Check bestehen."""
        valid_code = '''
def hello() -> str:
    """Say hello."""
    return "Hallo Welt"
'''
        result = gate.validate(valid_code, "test.py", "sonnet")

        assert "syntax" in result.checks_passed

    def test_invalid_python_syntax(self, gate):
        """Ungültiger Python-Code sollte Syntax-Check nicht bestehen."""
        invalid_code = '''
def hello(
    return "broken"
'''
        result = gate.validate(invalid_code, "test.py", "sonnet")

        assert "syntax" in result.checks_failed

    def test_no_secrets_check(self, gate):
        """Code ohne Secrets sollte no_secrets Check bestehen."""
        clean_code = '''
API_KEY = os.environ.get("API_KEY")
password = get_password_from_vault()
'''
        result = gate.validate(clean_code, "test.py", "sonnet")

        assert "no_secrets" in result.checks_passed

    def test_secrets_detected(self, gate):
        """Code mit Secrets sollte no_secrets Check nicht bestehen."""
        code_with_secret = '''
api_key = "sk-1234567890123456789012345678901234567890"
'''
        result = gate.validate(code_with_secret, "test.py", "sonnet")

        assert "no_secrets" in result.checks_failed

    def test_escalation_threshold(self, gate):
        """Schlechte Qualität sollte Eskalation auslösen."""
        bad_code = '''
def hello(
    api_key = "sk-abcdefghijklmnopqrstuvwxyz123456789012"
'''
        result = gate.validate(bad_code, "test.py", "haiku")

        # Haiku hat höchsten Threshold (0.95)
        assert result.should_escalate is True


class TestHaikuQualityGate:
    """Tests für HaikuQualityGate Klasse (strikt 98%)."""

    @pytest.fixture
    def gate(self):
        """Provide HaikuQualityGate instance."""
        return HaikuQualityGate()

    def test_valid_format_change_passes(self, gate):
        """Reine Formatierungs-Änderungen sollten bestehen."""
        original = "def hello():return 'hello'"
        modified = "def hello():\n    return 'hello'"

        passed, reason, escalate_to = gate.validate(original, modified, "format")

        assert passed is True
        assert escalate_to is None

    def test_syntax_error_fails(self, gate):
        """Syntax-Fehler sollten scheitern und eskalieren."""
        original = "def hello(): return 'hello'"
        modified = "def hello( return 'hello'"  # Syntax error

        passed, reason, escalate_to = gate.validate(original, modified, "format")

        assert passed is False
        assert escalate_to == "sonnet"

    def test_function_deletion_fails(self, gate):
        """Gelöschte Funktionen sollten scheitern."""
        original = '''
def func1():
    pass

def func2():
    pass
'''
        modified = '''
def func1():
    pass
'''

        passed, reason, escalate_to = gate.validate(original, modified, "format")

        assert passed is False  # Function was deleted

    def test_threshold_is_98_percent(self, gate):
        """Threshold sollte 98% sein."""
        assert gate.HAIKU_THRESHOLD == 0.98


class TestOrchestrationMetrics:
    """Tests für OrchestrationMetrics Klasse."""

    @pytest.fixture
    def metrics(self):
        """Provide OrchestrationMetrics instance."""
        return OrchestrationMetrics()

    def test_record_task(self, metrics):
        """record_task sollte Tasks korrekt zählen."""
        metrics.record_task("haiku", 100, 0.95)
        metrics.record_task("sonnet", 500, 0.90)
        metrics.record_task("opus", 1000, 0.85)

        assert metrics.tasks_by_tier["haiku"] == 1
        assert metrics.tasks_by_tier["sonnet"] == 1
        assert metrics.tasks_by_tier["opus"] == 1
        assert metrics.get_total_tasks() == 3

    def test_record_escalation(self, metrics):
        """record_escalation sollte Eskalationen zählen."""
        metrics.record_escalation()
        metrics.record_escalation()

        assert metrics.escalations == 2

    def test_cache_hit_rate(self, metrics):
        """Cache Hit Rate sollte korrekt berechnet werden."""
        metrics.record_cache_hit()
        metrics.record_cache_hit()
        metrics.record_cache_miss()

        # 2 hits, 1 miss = 66.7% hit rate
        total = metrics.cache_hits + metrics.cache_misses
        rate = metrics.cache_hits / total
        assert rate == pytest.approx(0.667, rel=0.01)

    def test_token_savings(self, metrics):
        """Token Savings sollten korrekt berechnet werden."""
        # Record haiku tasks (cheapest)
        for _ in range(5):
            metrics.record_task("haiku", 100, 0.95)

        savings = metrics.get_token_savings_percentage()
        # Haiku ist viel billiger als Opus Baseline
        assert savings > 80  # Mindestens 80% Savings

    def test_reset(self, metrics):
        """reset() sollte alle Metriken zurücksetzen."""
        metrics.record_task("haiku", 100, 0.95)
        metrics.record_escalation()

        metrics.reset()

        assert metrics.get_total_tasks() == 0
        assert metrics.escalations == 0

    def test_get_summary(self, metrics):
        """get_summary() sollte lesbaren String zurückgeben."""
        metrics.record_task("haiku", 100, 0.95)

        summary = metrics.get_summary()

        assert "Orchestration Metrics" in summary
        assert "Haiku" in summary


class TestOrchestrationMCPServer:
    """Tests für OrchestrationMCPServer Klasse."""

    @pytest.fixture
    def server(self):
        """Provide OrchestrationMCPServer instance with mocked config."""
        with patch.object(OrchestrationMCPServer, '_load_config', return_value={
            "orchestration": {
                "specialized_agents_enabled": True,
                "cache_enabled": True
            },
            "specialized_patterns": {
                "refactoring-expert": {
                    "agent": "refactoring-expert",
                    "tier": "opus",
                    "keywords": ["refactor", "migration"],
                    "file_patterns": ["**/*.py"]
                },
                "testing-expert": {
                    "agent": "testing-expert",
                    "tier": "sonnet",
                    "keywords": ["test", "pytest"],
                    "file_patterns": ["tests/**/*"]
                }
            },
            "thresholds": {"cache_ttl_days": 7}
        }):
            return OrchestrationMCPServer()

    def test_server_initialization(self, server):
        """Server sollte korrekt initialisiert werden."""
        assert server.classifier is not None
        assert server.cache is not None
        assert server.quality_gate is not None
        assert server.metrics is not None

    def test_specialized_agent_matching(self, server):
        """Spezialisierte Agenten sollten erkannt werden."""
        # Test refactoring match
        matches = server._matches_specialty(
            "Refactor the auth module",
            ["app/auth.py"],
            server.specialized_patterns["refactoring-expert"]
        )
        assert matches is True

    def test_specialized_agent_no_match(self, server):
        """Nicht passende Tasks sollten nicht matchen."""
        matches = server._matches_specialty(
            "Update documentation",
            ["README.md"],
            server.specialized_patterns["refactoring-expert"]
        )
        # "Update documentation" sollte nicht "refactor" matchen
        assert matches is False

    @pytest.mark.asyncio
    async def test_route_task_specialized(self, server):
        """route_task sollte spezialisierte Agenten bevorzugen."""
        result = await server.route_task(
            "Refactor the authentication module",
            ["app/auth.py"]
        )

        assert result.specialty is not None
        assert result.agent_name == "refactoring-expert"

    @pytest.mark.asyncio
    async def test_route_task_standard(self, server):
        """route_task sollte Standard-Routing nutzen wenn kein Spezialist passt."""
        result = await server.route_task(
            "Update the README file",
            ["README.md"]
        )

        # Sollte Standard-Tier sein
        assert result.tier in ["haiku", "sonnet", "opus"]

    def test_regex_safe_pattern_matching(self, server):
        """Pattern-Matching sollte gegen Regex-Injection geschützt sein."""
        # Test mit potenziell gefährlichen Patterns
        spec_config = {
            "agent": "test",
            "keywords": ["test"],
            "file_patterns": ["app/*"]
        }

        # Sollte nicht crashen
        result = server._matches_specialty(
            "Test task",
            ["app/[special].py", "app/{brackets}.py"],
            spec_config
        )

        assert isinstance(result, bool)


class TestEdgeCases:
    """Tests für Grenzfälle."""

    @pytest.fixture
    def classifier(self):
        """Provide TaskClassifier instance."""
        return TaskClassifier()

    def test_empty_task_prompt(self, classifier):
        """Leerer Task-Prompt sollte behandelt werden."""
        result = classifier.classify("")

        # Sollte nicht crashen
        assert result.tier in ["haiku", "sonnet", "opus"]

    def test_very_long_task_prompt(self, classifier):
        """Sehr langer Task-Prompt sollte behandelt werden."""
        long_prompt = "Implement " * 1000

        result = classifier.classify(long_prompt)

        # Sollte nicht crashen und wegen Länge höheres Tier haben
        assert result.tier in ["sonnet", "opus"]

    def test_unicode_in_prompt(self, classifier):
        """Unicode-Zeichen in Prompts sollten behandelt werden."""
        result = classifier.classify(
            "Implementiere Dokumentverarbeitung für äöü ß"
        )

        assert result.tier in ["haiku", "sonnet", "opus"]

    def test_special_characters_in_files(self, classifier):
        """Spezielle Zeichen in Dateipfaden sollten behandelt werden."""
        result = classifier.classify(
            "Update files",
            ["path/with spaces/file.py", "path/with-dashes/file.py"]
        )

        assert result.tier in ["haiku", "sonnet", "opus"]

    def test_division_by_zero_prevention(self, classifier):
        """Division durch Null sollte verhindert werden."""
        # Empty files list
        result = classifier.classify("Task", [])
        assert result.tier in ["haiku", "sonnet", "opus"]


class TestConcurrencySafety:
    """Tests für Thread/Async-Safety."""

    @pytest.fixture
    def classifier(self):
        """Provide TaskClassifier instance."""
        return TaskClassifier()

    @pytest.mark.asyncio
    async def test_concurrent_classification(self, classifier):
        """Mehrere gleichzeitige Klassifizierungen sollten sicher sein."""
        async def classify_task(prompt: str):
            # Simuliere async context
            await asyncio.sleep(0.01)
            return classifier.classify(prompt, [])

        # 10 parallele Klassifizierungen
        tasks = [
            classify_task(f"Task {i}: Implement feature")
            for i in range(10)
        ]

        results = await asyncio.gather(*tasks)

        # Alle sollten gültige Ergebnisse haben
        assert len(results) == 10
        for r in results:
            assert r.tier in ["haiku", "sonnet", "opus"]
            assert 0 <= r.confidence <= 1


class TestModelTier:
    """Tests für ModelTier Enum."""

    def test_tier_values(self):
        """ModelTier sollte korrekte Werte haben."""
        assert ModelTier.HAIKU_SIMPLE.value == "haiku"
        assert ModelTier.SONNET_CAPABLE.value == "sonnet"
        assert ModelTier.OPUS_REQUIRED.value == "opus"

    def test_tier_from_string(self):
        """ModelTier sollte von String erstellbar sein."""
        assert ModelTier("haiku") == ModelTier.HAIKU_SIMPLE
        assert ModelTier("sonnet") == ModelTier.SONNET_CAPABLE
        assert ModelTier("opus") == ModelTier.OPUS_REQUIRED
