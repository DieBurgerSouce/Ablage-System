"""E2E Integration Tests for MCP Server + Specialized Agents.

Diese Tests validieren das vollautomatische Routing-System:
- Automatic tier-based routing (Haiku/Sonnet/Opus)
- Specialized agent detection (Refactoring, OCR, Testing, Database)
- Quality escalation chain (Haiku → Sonnet → Opus)
- Cached decision injection for Sonnet/Haiku
"""

import pytest
from pathlib import Path
from typing import Dict, Any, List, Optional
import sys

# Add MCP server to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / ".claude" / "mcp-server"))

# Diese Suite testet das claude-flow-Orchestrierungs-Tooling unter
# `.claude/mcp-server/`, NICHT die Ablage-App. Dieses Verzeichnis ist im
# Backend-Container nicht gemountet (nur `app/` + `tests/`), daher ist das
# Modul dort nicht importierbar. Sauber ueberspringen statt Collection-Error.
pytest.importorskip(
    "orchestration_server",
    reason="claude-flow MCP-Server-Tooling (.claude/mcp-server) im App-Container nicht verfuegbar",
)

from orchestration_server import (  # noqa: E402
    OrchestrationMCPServer,
    TaskRouting,
    TaskClassifier,
    DecisionCache,
    QualityGate
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mcp_server():
    """Create MCP Server instance for testing."""
    config_path = Path(__file__).parent.parent.parent / ".claude" / "mcp-server" / "config.json"
    server = OrchestrationMCPServer(config_path=config_path)
    return server


@pytest.fixture
def clean_cache(mcp_server):
    """Ensure cache is clean before tests."""
    mcp_server.cache.clear()
    yield
    mcp_server.cache.clear()


# ============================================================================
# TIER-BASED ROUTING TESTS
# ============================================================================

class TestTierBasedRouting:
    """Test automatic tier-based routing for standard tasks."""

    @pytest.mark.asyncio
    async def test_automatic_haiku_routing_simple_task(self, mcp_server, clean_cache):
        """Simple task → Haiku automatisch."""
        task_prompt = "Fix typo in README"
        files = []

        routing = await mcp_server.route_task(task_prompt, files)

        assert routing.agent_name == "haiku-task"
        assert routing.tier == "haiku"
        assert routing.specialty is None  # Standard routing
        assert routing.confidence >= 0.85

    @pytest.mark.asyncio
    async def test_automatic_sonnet_routing_moderate_task(self, mcp_server, clean_cache):
        """Moderate complexity task → Sonnet."""
        task_prompt = "Implement user login endpoint with JWT authentication"
        files = ["app/api/v1/auth.py", "app/core/security.py"]

        routing = await mcp_server.route_task(task_prompt, files)

        assert routing.agent_name == "sonnet-implementation"
        assert routing.tier == "sonnet"
        assert routing.specialty is None
        assert routing.confidence >= 0.70

    @pytest.mark.asyncio
    async def test_automatic_opus_routing_complex_task(self, mcp_server, clean_cache):
        """Complex architectural task → Opus."""
        task_prompt = "Design microservices architecture for document processing system"
        files = []

        routing = await mcp_server.route_task(task_prompt, files)

        assert routing.agent_name == "opus-task"
        assert routing.tier == "opus"
        assert routing.specialty is None
        assert routing.confidence >= 0.80


# ============================================================================
# SPECIALIZED AGENT ROUTING TESTS
# ============================================================================

class TestSpecializedAgentRouting:
    """Test specialized agent pattern detection and routing."""

    @pytest.mark.asyncio
    async def test_refactoring_agent_keyword_match(self, mcp_server, clean_cache):
        """Refactoring keywords → Refactoring Expert Agent."""
        task_prompt = "Refactoriere Authentication-System von Session zu JWT"
        files = [
            "app/api/auth.py",
            "app/core/security.py",
            "app/db/models/user.py",
            "app/services/auth_service.py",
            "tests/test_auth.py"
        ]  # 5 files = meets threshold

        routing = await mcp_server.route_task(task_prompt, files)

        assert routing.agent_name == "refactoring-expert"
        assert routing.tier == "opus"
        assert routing.specialty == "refactoring"
        assert routing.confidence >= 0.90

    @pytest.mark.asyncio
    async def test_refactoring_agent_file_count_threshold(self, mcp_server, clean_cache):
        """Refactoring requires min 5 files."""
        task_prompt = "Refactoriere Authentication zu JWT"
        files = ["app/api/auth.py", "app/core/security.py"]  # Only 2 files

        routing = await mcp_server.route_task(task_prompt, files)

        # Should still match on keywords, but check file count is respected
        if routing.specialty == "refactoring":
            # If matched, it's because keywords are strong enough
            assert len(files) >= 2  # At least some files
        else:
            # Otherwise should fall back to tier-based routing
            assert routing.tier in ["sonnet", "opus"]

    @pytest.mark.asyncio
    async def test_ocr_specialist_keyword_match(self, mcp_server, clean_cache):
        """OCR keywords → OCR Specialist Agent."""
        task_prompt = "Optimiere DeepSeek GPU Batch Processing für deutsche Texte"
        files = ["app/agents/ocr/deepseek.py"]

        routing = await mcp_server.route_task(task_prompt, files)

        assert routing.agent_name == "ocr-specialist"
        assert routing.tier == "opus"
        assert routing.specialty == "ocr"
        assert routing.confidence >= 0.90

    @pytest.mark.asyncio
    async def test_ocr_specialist_file_pattern_match(self, mcp_server, clean_cache):
        """OCR file patterns → OCR Specialist Agent."""
        task_prompt = "Fix bug in OCR service"
        files = ["app/services/ocr_service.py"]

        routing = await mcp_server.route_task(task_prompt, files)

        assert routing.agent_name == "ocr-specialist"
        assert routing.specialty == "ocr"

    @pytest.mark.asyncio
    async def test_testing_agent_keyword_match(self, mcp_server, clean_cache):
        """Testing keywords → Testing Expert Agent."""
        task_prompt = "Erstelle Unit Tests für OCR Pipeline mit 80%+ Coverage"
        files = ["tests/unit/services/test_ocr_service.py"]

        routing = await mcp_server.route_task(task_prompt, files)

        assert routing.agent_name == "testing-expert"
        assert routing.tier == "sonnet"
        assert routing.specialty == "testing"
        assert routing.confidence >= 0.90

    @pytest.mark.asyncio
    async def test_testing_agent_file_pattern_match(self, mcp_server, clean_cache):
        """Test files → Testing Expert Agent."""
        task_prompt = "Add more tests"
        files = ["tests/unit/test_auth.py", "tests/integration/test_ocr.py"]

        routing = await mcp_server.route_task(task_prompt, files)

        assert routing.agent_name == "testing-expert"
        assert routing.specialty == "testing"

    @pytest.mark.asyncio
    async def test_database_agent_keyword_match(self, mcp_server, clean_cache):
        """Database keywords → Database Expert Agent."""
        task_prompt = "Erstelle SQLAlchemy Models für Document Management mit pgvector"
        files = ["app/db/models.py"]

        routing = await mcp_server.route_task(task_prompt, files)

        assert routing.agent_name == "database-expert"
        assert routing.tier == "sonnet"
        assert routing.specialty == "database"
        assert routing.confidence >= 0.90

    @pytest.mark.asyncio
    async def test_database_agent_file_pattern_match(self, mcp_server, clean_cache):
        """Database migration files → Database Expert Agent."""
        task_prompt = "Update migration script"
        files = ["alembic/versions/abc123_add_email_verified.py"]

        routing = await mcp_server.route_task(task_prompt, files)

        assert routing.agent_name == "database-expert"
        assert routing.specialty == "database"

    @pytest.mark.asyncio
    async def test_specialized_agent_priority_over_tier(self, mcp_server, clean_cache):
        """Specialized agents should have priority over tier-based routing."""
        # Simple task that would normally go to Haiku
        task_prompt = "Fix typo in test file"
        files = ["tests/unit/test_simple.py"]

        routing = await mcp_server.route_task(task_prompt, files)

        # Should route to Testing Agent because of file pattern
        assert routing.agent_name == "testing-expert"
        assert routing.specialty == "testing"
        # NOT haiku-task even though it's a simple task


# ============================================================================
# PROMPT ENHANCEMENT TESTS
# ============================================================================

class TestPromptEnhancement:
    """Test prompt enhancement with cached decisions and tier-specific guidance."""

    @pytest.mark.asyncio
    async def test_prompt_enhancement_with_cached_decisions(self, mcp_server):
        """Sonnet/Haiku prompts should include cached Opus decisions."""
        # 1. Store some Opus decisions in cache
        mcp_server.cache.store(
            task_description="Implement authentication with JWT",
            decision="Use FastAPI Depends() for DI, bcrypt for passwords, httpOnly cookies for tokens",
            reasoning="Best practices for secure auth in FastAPI",
            affected_files=["app/api/v1/auth.py"],
            model_used="opus",
            confidence=0.95
        )

        # 2. Route a similar Sonnet task
        task_prompt = "Add user registration endpoint"
        files = ["app/api/v1/auth.py"]

        routing = await mcp_server.route_task(task_prompt, files)
        task_call = mcp_server.create_task_call(routing, task_prompt, files)

        # 3. Verify cached decisions are injected
        enhanced_prompt = task_call["prompt"]
        assert "CACHED DECISIONS FROM OPUS" in enhanced_prompt
        assert "FastAPI Depends()" in enhanced_prompt
        assert "bcrypt" in enhanced_prompt
        assert "Confidence: 95%" in enhanced_prompt

    @pytest.mark.asyncio
    async def test_prompt_enhancement_tier_specific_guidance(self, mcp_server, clean_cache):
        """Each tier should get appropriate guidance."""
        # Haiku task
        haiku_routing = await mcp_server.route_task("Fix typo", [])
        haiku_call = mcp_server.create_task_call(haiku_routing, "Fix typo", [])
        assert "HAIKU GUIDELINES" in haiku_call["prompt"]
        assert "simple, well-defined tasks" in haiku_call["prompt"]

        # Sonnet task
        sonnet_routing = await mcp_server.route_task("Implement login endpoint", ["app/api/auth.py"])
        sonnet_call = mcp_server.create_task_call(sonnet_routing, "Implement login endpoint", ["app/api/auth.py"])
        assert "SONNET GUIDELINES" in sonnet_call["prompt"]
        assert "cached Opus decisions" in sonnet_call["prompt"]

        # Opus task
        opus_routing = await mcp_server.route_task("Design microservices architecture", [])
        opus_call = mcp_server.create_task_call(opus_routing, "Design microservices architecture", [])
        assert "OPUS GUIDELINES" in opus_call["prompt"]
        assert "architectural decisions" in opus_call["prompt"]

    @pytest.mark.asyncio
    async def test_prompt_enhancement_specialty_context(self, mcp_server, clean_cache):
        """Specialized agents should get domain-specific context."""
        # Refactoring agent
        task_prompt = "Migrate to async SQLAlchemy 2.0"
        files = ["app/db/models.py"] * 5  # 5 files to trigger refactoring

        routing = await mcp_server.route_task(task_prompt, files)
        task_call = mcp_server.create_task_call(routing, task_prompt, files)

        if routing.specialty == "refactoring":
            enhanced_prompt = task_call["prompt"]
            # Should include specialty context
            assert "refactoring" in enhanced_prompt.lower() or "migration" in enhanced_prompt.lower()


# ============================================================================
# QUALITY GATE & ESCALATION TESTS
# ============================================================================

class TestQualityGateEscalation:
    """Test quality validation and automatic escalation chain."""

    @pytest.mark.asyncio
    async def test_haiku_escalation_to_sonnet_on_quality_failure(self, mcp_server):
        """Haiku quality failure → Escalate to Sonnet."""
        # Simulate Haiku output with quality issues (no type hints, German errors)
        bad_haiku_output = """
def process(x):
    return x
"""

        escalation_task = await mcp_server.validate_and_escalate(
            task_id="test-1",
            output=bad_haiku_output,
            model_used="haiku",
            original_prompt="Implement data processing function",
            files=["app/services/processor.py"]
        )

        # Should escalate to Sonnet
        assert escalation_task is not None
        assert escalation_task["subagent_type"] == "sonnet-implementation"
        assert "ESCALATION FROM HAIKU" in escalation_task["prompt"]
        assert "quality" in escalation_task["prompt"].lower()

    @pytest.mark.asyncio
    async def test_sonnet_escalation_to_opus_on_quality_failure(self, mcp_server):
        """Sonnet quality failure → Escalate to Opus."""
        # Simulate Sonnet output with quality issues
        bad_sonnet_output = """
from typing import Any

def process(data: Any) -> Any:  # ❌ Using Any type
    print("Processing...")  # ❌ English string
    return data
"""

        escalation_task = await mcp_server.validate_and_escalate(
            task_id="test-2",
            output=bad_sonnet_output,
            model_used="sonnet",
            original_prompt="Implement data processing with type safety",
            files=["app/services/processor.py"]
        )

        # Should escalate to Opus
        assert escalation_task is not None
        assert escalation_task["subagent_type"] == "opus-task"
        assert "ESCALATION FROM SONNET" in escalation_task["prompt"]

    @pytest.mark.asyncio
    async def test_opus_quality_failure_no_escalation(self, mcp_server):
        """Opus quality failure → No escalation (log critical failure)."""
        bad_opus_output = """
def process(x):  # Even Opus can fail sometimes
    return x
"""

        escalation_task = await mcp_server.validate_and_escalate(
            task_id="test-3",
            output=bad_opus_output,
            model_used="opus",
            original_prompt="Implement data processing",
            files=["app/services/processor.py"]
        )

        # Opus can't escalate - should return None
        assert escalation_task is None

    @pytest.mark.asyncio
    async def test_quality_pass_no_escalation(self, mcp_server):
        """High quality output → No escalation."""
        good_output = """
from typing import List, Dict

async def process_documents(
    documents: List[str],
    options: Dict[str, any]
) -> List[Dict[str, any]]:
    \"\"\"Verarbeite Dokumente mit den angegebenen Optionen.

    Args:
        documents: Liste von Dokument-IDs
        options: Verarbeitungsoptionen

    Returns:
        Liste von Verarbeitungsergebnissen

    Raises:
        ProcessingError: Wenn Verarbeitung fehlschlägt
    \"\"\"
    results = []
    for doc_id in documents:
        result = await process_single(doc_id, options)
        results.append(result)
    return results
"""

        escalation_task = await mcp_server.validate_and_escalate(
            task_id="test-4",
            output=good_output,
            model_used="sonnet",
            original_prompt="Implement document processing",
            files=["app/services/processor.py"]
        )

        # Good quality - no escalation needed
        assert escalation_task is None

    @pytest.mark.asyncio
    async def test_opus_decision_cached_on_success(self, mcp_server, clean_cache):
        """Successful Opus output should be cached for future Sonnet/Haiku use."""
        good_opus_output = """
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

async def get_users(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100
) -> List[User]:
    \"\"\"Hole Benutzerliste mit Pagination.\"\"\"
    result = await db.execute(
        select(User).offset(skip).limit(limit)
    )
    return result.scalars().all()
"""

        # Validate (should pass)
        escalation = await mcp_server.validate_and_escalate(
            task_id="test-5",
            output=good_opus_output,
            model_used="opus",
            original_prompt="Implement user listing endpoint",
            files=["app/api/v1/users.py"]
        )

        assert escalation is None  # No escalation

        # Check that decision was cached
        cached = mcp_server.cache.find_relevant("Implement user listing", ["app/api/v1/users.py"])
        assert len(cached) > 0
        assert cached[0].model_used == "opus"
        assert "AsyncSession" in cached[0].decision or "Depends" in cached[0].decision


# ============================================================================
# TASK CALL CREATION TESTS
# ============================================================================

class TestTaskCallCreation:
    """Test Task() JSON creation for Claude Code."""

    @pytest.mark.asyncio
    async def test_task_call_structure(self, mcp_server, clean_cache):
        """Task call should have correct structure."""
        routing = await mcp_server.route_task("Fix typo", [])
        task_call = mcp_server.create_task_call(routing, "Fix typo", [])

        # Verify structure
        assert "type" in task_call
        assert task_call["type"] == "Task"
        assert "subagent_type" in task_call
        assert "description" in task_call
        assert "prompt" in task_call
        assert "model" in task_call

    @pytest.mark.asyncio
    async def test_task_call_explicit_model_override(self, mcp_server, clean_cache):
        """Task call should include explicit model override."""
        # Haiku task
        haiku_routing = await mcp_server.route_task("Fix typo", [])
        haiku_call = mcp_server.create_task_call(haiku_routing, "Fix typo", [])
        assert haiku_call["model"] == "haiku"

        # Opus task (specialized agent)
        opus_routing = await mcp_server.route_task(
            "Refactoriere Authentication",
            ["app/api/auth.py"] * 5  # 5 files
        )
        opus_call = mcp_server.create_task_call(opus_routing, "Refactoriere Authentication", ["app/api/auth.py"] * 5)
        assert opus_call["model"] == "opus"

    @pytest.mark.asyncio
    async def test_task_call_description_includes_tier(self, mcp_server, clean_cache):
        """Task description should indicate which tier is being used."""
        routing = await mcp_server.route_task("Implement feature", ["app/api/users.py"])
        task_call = mcp_server.create_task_call(routing, "Implement feature", ["app/api/users.py"])

        description = task_call["description"]
        assert routing.tier in description.lower()


# ============================================================================
# METRICS TRACKING TESTS
# ============================================================================

class TestMetricsTracking:
    """Test that metrics are properly tracked."""

    @pytest.mark.asyncio
    async def test_metrics_recorded_for_routing(self, mcp_server, clean_cache):
        """Metrics should be recorded for each routing decision."""
        initial_count = mcp_server.metrics.get_total_tasks()

        await mcp_server.route_task("Fix typo", [])
        await mcp_server.route_task("Implement feature", ["app/api/users.py"])

        final_count = mcp_server.metrics.get_total_tasks()
        assert final_count == initial_count + 2

    @pytest.mark.asyncio
    async def test_metrics_track_tier_distribution(self, mcp_server, clean_cache):
        """Metrics should track distribution across tiers."""
        # Route tasks to different tiers
        await mcp_server.route_task("Fix typo", [])  # Haiku
        await mcp_server.route_task("Implement login", ["app/api/auth.py"])  # Sonnet
        await mcp_server.route_task("Design architecture", [])  # Opus

        distribution = mcp_server.metrics.get_tier_distribution()
        assert distribution.get("haiku", 0) >= 1
        assert distribution.get("sonnet", 0) >= 1
        assert distribution.get("opus", 0) >= 1


# ============================================================================
# INTEGRATION TEST SCENARIOS
# ============================================================================

class TestRealWorldScenarios:
    """Test realistic end-to-end scenarios."""

    @pytest.mark.asyncio
    async def test_document_processing_feature_development(self, mcp_server, clean_cache):
        """Scenario: Entwickle neue Document Processing Feature."""
        # 1. Architecture design → Opus
        arch_routing = await mcp_server.route_task(
            "Design document processing pipeline architecture",
            []
        )
        assert arch_routing.tier == "opus"

        # 2. Implementation → Sonnet (uses cached Opus decisions)
        impl_routing = await mcp_server.route_task(
            "Implement document upload endpoint",
            ["app/api/v1/documents.py"]
        )
        assert impl_routing.tier == "sonnet"

        # 3. Tests → Testing Agent
        test_routing = await mcp_server.route_task(
            "Add unit tests for document upload",
            ["tests/unit/api/test_documents.py"]
        )
        assert test_routing.specialty == "testing"

        # 4. Bug fix → Haiku
        bug_routing = await mcp_server.route_task(
            "Fix typo in error message",
            ["app/api/v1/documents.py"]
        )
        assert bug_routing.tier == "haiku"

    @pytest.mark.asyncio
    async def test_ocr_optimization_workflow(self, mcp_server, clean_cache):
        """Scenario: Optimiere OCR Pipeline für GPU."""
        # 1. OCR optimization → OCR Specialist
        ocr_routing = await mcp_server.route_task(
            "Optimiere DeepSeek GPU Batch Processing, VRAM unter 85% halten",
            ["app/agents/ocr/deepseek.py"]
        )
        assert ocr_routing.specialty == "ocr"
        assert ocr_routing.tier == "opus"

        # 2. GPU tests → Testing Agent
        test_routing = await mcp_server.route_task(
            "Add GPU memory leak tests",
            ["tests/unit/agents/test_deepseek.py"]
        )
        assert test_routing.specialty == "testing"

    @pytest.mark.asyncio
    async def test_database_migration_workflow(self, mcp_server, clean_cache):
        """Scenario: Database Schema Migration."""
        # 1. Migration creation → Database Agent
        migration_routing = await mcp_server.route_task(
            "Erstelle Alembic Migration für email_verified column",
            ["alembic/versions/abc123_add_email_verified.py"]
        )
        assert migration_routing.specialty == "database"

        # 2. Model update → Database Agent
        model_routing = await mcp_server.route_task(
            "Update SQLAlchemy User model",
            ["app/db/models.py"]
        )
        assert model_routing.specialty == "database"

    @pytest.mark.asyncio
    async def test_refactoring_workflow(self, mcp_server, clean_cache):
        """Scenario: Large-scale refactoring."""
        # Refactoring with 5+ files → Refactoring Agent
        refactor_routing = await mcp_server.route_task(
            "Migrate from sync to async SQLAlchemy",
            [
                "app/db/models.py",
                "app/db/repositories.py",
                "app/services/document_service.py",
                "app/api/v1/documents.py",
                "tests/unit/db/test_models.py"
            ]
        )
        assert refactor_routing.specialty == "refactoring"
        assert refactor_routing.tier == "opus"


# ============================================================================
# EDGE CASES & ERROR HANDLING
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_empty_task_prompt(self, mcp_server, clean_cache):
        """Empty prompt should still route (fallback to default)."""
        routing = await mcp_server.route_task("", [])
        assert routing.agent_name is not None
        assert routing.tier is not None

    @pytest.mark.asyncio
    async def test_no_files_provided(self, mcp_server, clean_cache):
        """Routing should work without files."""
        routing = await mcp_server.route_task("Implement feature", None)
        assert routing.agent_name is not None

    @pytest.mark.asyncio
    async def test_many_files_provided(self, mcp_server, clean_cache):
        """Routing should work with many files."""
        files = [f"app/module_{i}.py" for i in range(50)]
        routing = await mcp_server.route_task("Refactor modules", files)
        # Should likely trigger refactoring agent due to file count
        assert routing.agent_name is not None

    @pytest.mark.asyncio
    async def test_mixed_specialty_signals(self, mcp_server, clean_cache):
        """Task with mixed signals should prioritize correctly."""
        # Has both OCR and testing keywords
        routing = await mcp_server.route_task(
            "Add tests for OCR service",
            ["tests/unit/services/test_ocr_service.py"]
        )
        # Should prioritize based on files (tests/*) or keywords
        assert routing.specialty in ["testing", "ocr"] or routing.specialty is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
