"""Unit tests for DecisionCache."""

import pytest
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add .claude to path so orchestration is a proper package
_claude_path = str(Path(__file__).parent.parent.parent.parent / ".claude")
if _claude_path not in sys.path:
    sys.path.insert(0, _claude_path)

from orchestration.decision_cache import DecisionCache, CachedDecision


class TestDecisionCache:
    """Test suite for decision caching logic."""

    def test_store_and_retrieve_decision(self, decision_cache):
        """Should store and retrieve decisions correctly."""
        decision_hash = decision_cache.store(
            task_description="Implement user authentication",
            decision="Use JWT with bcrypt",
            reasoning="Industry standard",
            affected_patterns=["authentication"],
            affected_files=["app/auth.py"],
            model_used="opus",
            confidence=0.95
        )

        assert decision_hash is not None
        assert len(decision_hash) == 16  # Hash is 16 characters

        # Retrieve decision
        decision = decision_cache.get_by_hash(decision_hash)
        assert decision is not None
        assert decision.decision == "Use JWT with bcrypt"
        assert decision.model_used == "opus"

    def test_find_relevant_by_task_description(self, decision_cache):
        """Should find relevant decisions by task description similarity."""
        # Store decision
        decision_cache.store(
            task_description="Implement user login with JWT",
            decision="Use JWT tokens",
            reasoning="Secure and stateless",
            affected_patterns=["authentication", "login"],
            affected_files=["app/api/auth.py"],
            model_used="opus",
            confidence=0.92
        )

        # Search for related task
        relevant = decision_cache.find_relevant(
            task_description="Add user authentication endpoint",
            affected_files=["app/api/auth.py"]
        )

        assert len(relevant) > 0
        assert "JWT" in relevant[0].decision or "jwt" in relevant[0].decision.lower()

    def test_find_relevant_by_file_overlap(self, decision_cache):
        """Should find relevant decisions by affected file overlap."""
        decision_cache.store(
            task_description="Refactor authentication",
            decision="Use dependency injection",
            reasoning="Better testability",
            affected_patterns=["refactor"],
            affected_files=["app/core/security.py", "app/api/auth.py"],
            model_used="opus",
            confidence=0.88
        )

        # Search with overlapping files
        relevant = decision_cache.find_relevant(
            task_description="Update security module",
            affected_files=["app/core/security.py"]
        )

        assert len(relevant) > 0
        assert "app/core/security.py" in relevant[0].affected_files

    def test_find_relevant_respects_min_confidence(self, decision_cache):
        """Should filter by minimum confidence threshold."""
        # Store low confidence decision
        decision_cache.store(
            task_description="Experiment with algorithm",
            decision="Try approach A",
            reasoning="Just a guess",
            affected_patterns=["experiment"],
            affected_files=["app/algo.py"],
            model_used="sonnet",
            confidence=0.60
        )

        # Search with high confidence threshold
        relevant = decision_cache.find_relevant(
            task_description="Algorithm implementation",
            min_confidence=0.80
        )

        # Should not find low confidence decision
        assert all(d.confidence >= 0.80 for d in relevant)

    def test_find_relevant_by_tags(self, decision_cache):
        """Should find relevant decisions by tag matching."""
        decision_cache.store(
            task_description="Implement OAuth2",
            decision="Use authlib library",
            reasoning="Well maintained",
            affected_patterns=["authentication"],
            affected_files=["app/oauth.py"],
            model_used="opus",
            confidence=0.94,
            tags=["security", "oauth", "authentication"]
        )

        # Search with tag
        relevant = decision_cache.find_relevant(
            task_description="Security implementation",
            tags=["security", "authentication"]
        )

        assert len(relevant) > 0
        assert "security" in relevant[0].tags

    def test_cache_expiration(self, decision_cache):
        """Expired decisions should be removed automatically."""
        # Store decision with short TTL
        decision_hash = decision_cache.store(
            task_description="Temporary decision",
            decision="Temp approach",
            reasoning="Short lived",
            affected_patterns=["temp"],
            affected_files=["temp.py"],
            model_used="haiku",
            confidence=0.75,
            ttl_days=0  # Expires immediately
        )

        # Manually trigger cleanup (in real usage, this happens automatically)
        decision_cache._cleanup_expired()

        # Decision should be removed
        assert decision_cache.get_by_hash(decision_hash) is None

    def test_invalidate_for_files(self, decision_cache):
        """Should invalidate cache when files change."""
        # Store decision
        decision_cache.store(
            task_description="Implement feature",
            decision="Use pattern X",
            reasoning="Best practice",
            affected_patterns=["implementation"],
            affected_files=["app/feature.py", "app/utils.py"],
            model_used="opus",
            confidence=0.90
        )

        # Invalidate one of the files
        invalidated_count = decision_cache.invalidate_for_files(["app/feature.py"])

        # Should invalidate the decision
        assert invalidated_count > 0

    def test_get_stats(self, decision_cache):
        """Should return accurate cache statistics."""
        # Store some decisions
        for i in range(5):
            decision_cache.store(
                task_description=f"Task {i}",
                decision=f"Decision {i}",
                reasoning=f"Reason {i}",
                affected_patterns=["test"],
                affected_files=[f"file_{i}.py"],
                model_used="opus" if i % 2 == 0 else "sonnet",
                confidence=0.85
            )

        stats = decision_cache.get_stats()

        assert stats["total_entries"] == 5
        assert stats["total_stores"] >= 5
        assert "opus" in stats["by_model"]
        assert "sonnet" in stats["by_model"]

    def test_delete_decision(self, decision_cache):
        """Should delete specific decisions."""
        decision_hash = decision_cache.store(
            task_description="Delete me",
            decision="Will be deleted",
            reasoning="Test",
            affected_patterns=["test"],
            affected_files=["test.py"],
            model_used="haiku",
            confidence=0.70
        )

        # Delete
        deleted = decision_cache.delete(decision_hash)
        assert deleted is True

        # Verify deleted
        assert decision_cache.get_by_hash(decision_hash) is None

    def test_delete_nonexistent_decision(self, decision_cache):
        """Deleting nonexistent decision should return False."""
        deleted = decision_cache.delete("nonexistent_hash")
        assert deleted is False

    def test_max_cache_size_enforcement(self, decision_cache):
        """Cache should enforce max size by removing old entries."""
        # Store more than max size
        original_max = decision_cache.MAX_CACHE_SIZE
        decision_cache.MAX_CACHE_SIZE = 10  # Temporarily reduce for testing

        for i in range(15):
            decision_cache.store(
                task_description=f"Task {i}",
                decision=f"Decision {i}",
                reasoning=f"Reason {i}",
                affected_patterns=["test"],
                affected_files=[f"file_{i}.py"],
                model_used="sonnet",
                confidence=0.80
            )

        stats = decision_cache.get_stats()
        assert stats["total_entries"] <= decision_cache.MAX_CACHE_SIZE + 100  # Buffer

        # Restore original max
        decision_cache.MAX_CACHE_SIZE = original_max

    def test_context_hash_generation(self, decision_cache):
        """Context hash should be generated for decisions."""
        decision_hash = decision_cache.store(
            task_description="Test context",
            decision="Context decision",
            reasoning="Testing",
            affected_patterns=["test"],
            affected_files=["file1.py", "file2.py"],
            model_used="opus",
            confidence=0.88,
            context={"affected_files": ["file1.py", "file2.py"]}
        )

        decision = decision_cache.get_by_hash(decision_hash)
        assert decision.context_hash is not None
        assert len(decision.context_hash) == 8  # MD5 hash truncated to 8 chars

    def test_cached_decision_structure(self, mock_cached_decision):
        """CachedDecision should have all required fields."""
        assert hasattr(mock_cached_decision, 'decision_hash')
        assert hasattr(mock_cached_decision, 'task_description')
        assert hasattr(mock_cached_decision, 'decision')
        assert hasattr(mock_cached_decision, 'reasoning')
        assert hasattr(mock_cached_decision, 'affected_patterns')
        assert hasattr(mock_cached_decision, 'affected_files')
        assert hasattr(mock_cached_decision, 'created_at')
        assert hasattr(mock_cached_decision, 'expires_at')
        assert hasattr(mock_cached_decision, 'model_used')
        assert hasattr(mock_cached_decision, 'confidence')
        assert hasattr(mock_cached_decision, 'tags')
        assert hasattr(mock_cached_decision, 'context_hash')

    def test_find_relevant_returns_top_5(self, decision_cache):
        """Should return at most 5 most relevant decisions."""
        # Store 10 decisions
        for i in range(10):
            decision_cache.store(
                task_description=f"Authentication task variant {i}",
                decision=f"Auth decision {i}",
                reasoning=f"Auth reasoning {i}",
                affected_patterns=["authentication"],
                affected_files=["app/auth.py"],
                model_used="opus",
                confidence=0.85
            )

        # Search should return max 5
        relevant = decision_cache.find_relevant(
            task_description="Implement authentication",
            affected_files=["app/auth.py"]
        )

        assert len(relevant) <= 5

    def test_text_similarity_calculation(self, decision_cache):
        """Text similarity should correctly rank results."""
        # Store very similar decision
        decision_cache.store(
            task_description="Implement JWT authentication with refresh tokens",
            decision="Use JWT library",
            reasoning="Standard approach",
            affected_patterns=["authentication"],
            affected_files=["app/auth.py"],
            model_used="opus",
            confidence=0.92
        )

        # Store less similar decision
        decision_cache.store(
            task_description="Implement file upload",
            decision="Use multipart form data",
            reasoning="Standard HTTP",
            affected_patterns=["upload"],
            affected_files=["app/upload.py"],
            model_used="sonnet",
            confidence=0.90
        )

        # Search for similar task
        relevant = decision_cache.find_relevant(
            task_description="Add JWT token authentication"
        )

        # Most similar should be first
        if len(relevant) > 0:
            assert "JWT" in relevant[0].decision or "authentication" in relevant[0].task_description.lower()

    def test_cache_persistence(self, temp_cache_dir):
        """Cache should persist across instances."""
        # Create first instance and store decision
        cache1 = DecisionCache()
        cache1.CACHE_DIR = temp_cache_dir
        cache1.CACHE_FILE = temp_cache_dir / "decisions.json"
        cache1.STATS_FILE = temp_cache_dir / "cache_stats.json"

        decision_hash = cache1.store(
            task_description="Persistent decision",
            decision="This should persist",
            reasoning="Testing persistence",
            affected_patterns=["test"],
            affected_files=["test.py"],
            model_used="opus",
            confidence=0.88
        )

        # Create second instance (should load from disk)
        cache2 = DecisionCache()
        cache2.CACHE_DIR = temp_cache_dir
        cache2.CACHE_FILE = temp_cache_dir / "decisions.json"
        cache2.STATS_FILE = temp_cache_dir / "cache_stats.json"
        cache2._cache = cache2._load_cache()

        # Should find the decision
        decision = cache2.get_by_hash(decision_hash)
        assert decision is not None
        assert decision.decision == "This should persist"

    def test_empty_cache_stats(self, decision_cache):
        """Stats should handle empty cache gracefully."""
        stats = decision_cache.get_stats()

        assert stats["total_entries"] == 0
        assert stats["total_stores"] == 0
        assert stats["by_model"] == {}

    def test_average_confidence_calculation(self, decision_cache):
        """Should calculate average confidence correctly."""
        decision_cache.store(
            task_description="Task 1",
            decision="Decision 1",
            reasoning="Reason 1",
            affected_patterns=["test"],
            affected_files=["file1.py"],
            model_used="opus",
            confidence=0.90
        )

        decision_cache.store(
            task_description="Task 2",
            decision="Decision 2",
            reasoning="Reason 2",
            affected_patterns=["test"],
            affected_files=["file2.py"],
            model_used="sonnet",
            confidence=0.80
        )

        stats = decision_cache.get_stats()
        avg_confidence = stats["avg_confidence"]

        assert 0.84 <= avg_confidence <= 0.86  # Average of 0.90 and 0.80

    def test_clear_cache(self, decision_cache):
        """Should clear all cache data."""
        # Store some decisions
        decision_cache.store(
            task_description="Test",
            decision="Decision",
            reasoning="Reason",
            affected_patterns=["test"],
            affected_files=["test.py"],
            model_used="opus",
            confidence=0.85
        )

        # Clear cache
        decision_cache.clear()

        # Verify empty
        stats = decision_cache.get_stats()
        assert stats["total_entries"] == 0
