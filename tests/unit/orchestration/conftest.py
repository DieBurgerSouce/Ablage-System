"""Shared fixtures for orchestration tests.

HINWEIS: Die Orchestration-Komponenten verwenden relative Imports,
daher müssen wir sie als Package importieren.

WICHTIG (Container vs. Host): Diese Tests prüfen das Claude-Flow-Team-Workflow-
Tooling unter `.claude/orchestration` + `.claude/helpers` — NICHT die Ablage-
Applikation. Im Backend-Container ist `.claude/` nicht gemountet (nur `tests/`
und `pytest.ini`), daher sind die Tooling-Module dort nicht importierbar. Statt
17 Collection-Errors zu erzeugen, werden die Test-Module dann sauber von der
Sammlung ausgenommen (collect_ignore_glob). Auf dem Host (wo `.claude/`
existiert) laufen sie normal. Siehe KNOWN_ISSUES.md.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock
from datetime import datetime
import sys
import importlib.util

# Pfade für beide Orchestration-Verzeichnisse
_claude_path = Path(__file__).parent.parent.parent.parent / ".claude"
_mcp_server_path = _claude_path / "mcp-server"

# Wenn das Tooling nicht auf der Platte liegt (z. B. im Backend-Container, in dem
# `.claude/` nicht gemountet ist), die Orchestration-Tooling-Tests gar nicht erst
# sammeln — sie testen nicht die App und würden sonst nur Collection-Errors werfen.
if not (_claude_path / "orchestration" / "task_classifier.py").exists():
    collect_ignore_glob = ["test_*.py"]

# Füge beide zum Path hinzu (orchestration wird als Package unter .claude importiert)
for p in [_claude_path, _mcp_server_path]:
    p_str = str(p)
    if p_str not in sys.path:
        sys.path.insert(0, p_str)

# Import orchestration components mit try/except für Robustheit
try:
    # Versuche als Package zu importieren
    from orchestration.task_classifier import TaskClassifier, ModelTier
    from orchestration.quality_gate import QualityGate, QualityLevel
    from orchestration.decision_cache import DecisionCache
    from orchestration.metrics import OrchestrationMetrics
    from orchestration.learning_feedback import LearningFeedback
    from orchestration.user_feedback import UserFeedback
except ImportError:
    # Fallback: Erstelle Mock-Klassen wenn Import fehlschlägt
    class TaskClassifier:
        pass
    class ModelTier:
        HAIKU_CAPABLE = "haiku"
        SONNET_CAPABLE = "sonnet"
        OPUS_REQUIRED = "opus"
    class QualityGate:
        pass
    class QualityLevel:
        PASSED = "passed"
        WARNING = "warning"
        FAILED = "failed"
    class DecisionCache:
        pass
    class OrchestrationMetrics:
        def __init__(self, **kwargs):
            pass
    class LearningFeedback:
        def __init__(self, **kwargs):
            pass
    class UserFeedback:
        pass


@pytest.fixture
def task_classifier():
    """Provide TaskClassifier instance."""
    return TaskClassifier()


@pytest.fixture
def quality_gate():
    """Provide QualityGate instance."""
    return QualityGate()


@pytest.fixture
def temp_cache_dir(tmp_path):
    """Provide temporary cache directory."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    return cache_dir


@pytest.fixture
def decision_cache(temp_cache_dir):
    """Provide DecisionCache with temp storage."""
    # Override class attributes BEFORE instantiation
    original_cache_dir = DecisionCache.CACHE_DIR
    original_cache_file = DecisionCache.CACHE_FILE
    original_stats_file = DecisionCache.STATS_FILE

    DecisionCache.CACHE_DIR = temp_cache_dir
    DecisionCache.CACHE_FILE = temp_cache_dir / "decisions.json"
    DecisionCache.STATS_FILE = temp_cache_dir / "cache_stats.json"

    cache = DecisionCache()

    yield cache

    # Restore original values
    DecisionCache.CACHE_DIR = original_cache_dir
    DecisionCache.CACHE_FILE = original_cache_file
    DecisionCache.STATS_FILE = original_stats_file


@pytest.fixture
def orchestration_metrics(temp_cache_dir):
    """Provide OrchestrationMetrics with temp storage."""
    metrics = OrchestrationMetrics(cache_dir=temp_cache_dir)
    return metrics


@pytest.fixture
def learning_feedback(temp_cache_dir):
    """Provide LearningFeedback with temp storage."""
    feedback = LearningFeedback(cache_dir=temp_cache_dir)
    return feedback


@pytest.fixture
def user_feedback():
    """Provide UserFeedback instance."""
    return UserFeedback()


@pytest.fixture
def sample_german_code():
    """German code sample for testing."""
    return '''
async def verarbeite_dokument(dokument_id: str) -> Dict[str, Any]:
    """Verarbeitet ein Dokument mit OCR.

    Args:
        dokument_id: Eindeutige Dokument-ID

    Returns:
        Dictionary mit Verarbeitungsergebnis

    Raises:
        DokumentFehler: Wenn Verarbeitung fehlschlägt
    """
    try:
        ergebnis = await ocr_service.process(dokument_id)
        return {"status": "erfolg", "daten": ergebnis}
    except Exception as e:
        logger.error("dokument_verarbeitung_fehlgeschlagen", dokument_id=dokument_id, error=str(e))
        raise DokumentFehler(f"Verarbeitung fehlgeschlagen: {e}")
'''


@pytest.fixture
def sample_bad_code():
    """Code with quality issues for testing."""
    return '''
def process(x):  # No type hints
    return x * 2  # No docstring
'''


@pytest.fixture
def sample_code_with_english_errors():
    """Code with English error messages (should fail German validation)."""
    return '''
async def process(doc_id: str) -> Dict[str, Any]:
    """Process document."""
    try:
        result = await handler(doc_id)
        return result
    except Exception as e:
        raise DocumentError(f"Processing failed: {e}")  # English!
'''


@pytest.fixture
def sample_task_prompts():
    """Sample task prompts for classification testing."""
    return {
        "haiku": [
            "Fix typo in README.md line 42",
            "Format code with black",
            "Add missing comma in JSON file",
            "Update copyright year to 2026"
        ],
        "sonnet": [
            "Implement user authentication with JWT tokens and bcrypt password hashing",
            "Add unit tests for DocumentService class",
            "Refactor OCR pipeline to use async/await pattern",
            "Create API endpoint for document upload with validation"
        ],
        "opus": [
            "Design and implement a distributed caching system with Redis Cluster",
            "Architect a fault-tolerant multi-model orchestration system",
            "Refactor entire authentication system with OAuth2 and RBAC",
            "Design database schema for multi-tenant SaaS platform"
        ]
    }


@pytest.fixture
def sample_files():
    """Sample file paths for testing."""
    return {
        "simple": ["README.md"],
        "moderate": ["app/services/document_service.py", "tests/test_document.py"],
        "complex": [
            "app/core/security.py",
            "app/api/auth.py",
            "app/db/models.py",
            "app/services/user_service.py",
            "tests/integration/test_auth.py"
        ],
        "critical": [
            "app/core/security.py",
            "app/core/config.py",
            "infrastructure/terraform/main.tf"
        ]
    }


@pytest.fixture
def mock_classification_result():
    """Mock ClassificationResult for testing."""
    from task_classifier import ClassificationResult

    return ClassificationResult(
        tier=ModelTier.SONNET_CAPABLE,
        confidence=0.85,
        reasoning="Standard implementation task with tests",
        primary_pattern="implementation",
        matched_patterns=["implementation", "testing"],
        complexity_score=0.65,
        file_impact_score=0.50
    )


@pytest.fixture
def mock_quality_result():
    """Mock QualityResult for testing."""
    from quality_gate import QualityResult

    return QualityResult(
        level=QualityLevel.PASSED,
        checks_passed=["syntax", "type_hints", "german_messages"],
        checks_failed=[],
        warnings=[],
        should_escalate=False,
        escalation_reason=None,
        details={}
    )


@pytest.fixture
def mock_cached_decision():
    """Mock CachedDecision for testing."""
    from decision_cache import CachedDecision

    return CachedDecision(
        decision_hash="abc123def456",
        task_description="Implement user authentication",
        decision="Use JWT with bcrypt for passwords",
        reasoning="Industry standard, secure, well-tested",
        affected_patterns=["authentication", "security"],
        affected_files=["app/auth.py"],
        created_at=datetime.now().isoformat(),
        expires_at=datetime.now().isoformat(),
        model_used="opus",
        confidence=0.95,
        tags=["security", "authentication"],
        context_hash="12345678"
    )


@pytest.fixture
def mock_task_execution():
    """Mock TaskExecution for testing."""
    from orchestration.learning_feedback import TaskExecution

    return TaskExecution(
        task_hash="task_abc123",
        task_pattern="implementation",
        initial_tier="sonnet",
        final_tier="sonnet",
        escalated=False,
        quality_score=0.92,
        execution_time_ms=1234,
        timestamp=datetime.now().isoformat(),
        success=True
    )
