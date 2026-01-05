#!/usr/bin/env python3
"""
Learning Feedback System für Multi-Model Orchestration.

Tracks task executions and learns from outcomes to optimize routing patterns.

FUNKTIONSWEISE:
1. Record jedes Task-Result (tier, quality, escalated, etc.)
2. Analyse von Patterns: Welche Task-Typen funktionieren gut mit welchem Tier?
3. Optimierungsvorschläge für TaskClassifier-Patterns
4. Kontinuierliches Lernen über Zeit

STORAGE:
- .claude/cache/learning_feedback.json - Task execution history
- .claude/cache/pattern_optimizations.json - Learned optimizations
"""

import json
import hashlib
import logging
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime
from collections import defaultdict

# Support both package and direct imports
try:
    from .task_classifier import ModelTier
except ImportError:
    from task_classifier import ModelTier

# Setup Logging
logger = logging.getLogger("orchestration.learning_feedback")


@dataclass
class TaskExecution:
    """Record of a single task execution."""

    task_hash: str  # Hash of task prompt for deduplication
    task_pattern: str  # Primary pattern matched (e.g., "implementation", "refactor")
    initial_tier: str  # Tier originally selected
    final_tier: str  # Tier that completed successfully
    escalated: bool  # Whether escalation occurred
    quality_score: float  # Final quality score (0-1)
    execution_time_ms: int  # Time taken in milliseconds
    timestamp: str  # ISO timestamp
    success: bool  # Whether task completed successfully


@dataclass
class PatternStatistics:
    """Statistics for a specific task pattern."""

    pattern: str
    total_executions: int
    tier_success_rates: Dict[str, float]  # opus/sonnet/haiku → success rate
    avg_quality_scores: Dict[str, float]  # opus/sonnet/haiku → avg quality
    escalation_rate: Dict[str, float]  # tier → escalation %
    recommended_tier: str  # Current recommendation
    confidence: float  # Confidence in recommendation (0-1)


class LearningFeedback:
    """Learning system that optimizes routing based on execution history."""

    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize learning feedback system.

        Args:
            cache_dir: Directory for cache files (default: .claude/cache)
        """
        if cache_dir is None:
            cache_dir = Path(".claude/cache")

        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.feedback_file = self.cache_dir / "learning_feedback.json"
        self.optimizations_file = self.cache_dir / "pattern_optimizations.json"

        self.feedback_history: List[TaskExecution] = []
        self.pattern_stats: Dict[str, PatternStatistics] = {}

        self._load_feedback()

    def _load_feedback(self):
        """Load feedback history from disk."""
        if self.feedback_file.exists():
            try:
                data = json.loads(self.feedback_file.read_text(encoding='utf-8'))
                self.feedback_history = [
                    TaskExecution(**item) for item in data.get("executions", [])
                ]
            except Exception as e:
                logger.warning("feedback_history_load_failed", error=str(e))

        if self.optimizations_file.exists():
            try:
                data = json.loads(self.optimizations_file.read_text(encoding='utf-8'))
                self.pattern_stats = {
                    k: PatternStatistics(**v) for k, v in data.items()
                }
            except Exception as e:
                logger.warning("pattern_statistics_load_failed", error=str(e))

    def _save_feedback(self):
        """Save feedback history to disk."""
        try:
            data = {
                "executions": [asdict(exec) for exec in self.feedback_history],
                "last_updated": datetime.now().isoformat()
            }
            self.feedback_file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
        except Exception as e:
            logger.warning("feedback_history_save_failed", error=str(e))

    def _save_optimizations(self):
        """Save pattern statistics to disk."""
        try:
            data = {
                k: asdict(v) for k, v in self.pattern_stats.items()
            }
            self.optimizations_file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
        except Exception as e:
            logger.warning("pattern_statistics_save_failed", error=str(e))

    def record_task(
        self,
        task_prompt: str,
        task_pattern: str,
        initial_tier: str,
        final_tier: str,
        escalated: bool,
        quality_score: float,
        execution_time_ms: int,
        success: bool = True
    ):
        """
        Record a task execution for learning.

        Args:
            task_prompt: The task prompt
            task_pattern: Primary pattern matched
            initial_tier: Tier originally selected
            final_tier: Tier that completed successfully
            escalated: Whether escalation occurred
            quality_score: Final quality score (0-1)
            execution_time_ms: Time taken in milliseconds
            success: Whether task completed successfully
        """
        # Create task hash (for deduplication)
        task_hash = hashlib.md5(task_prompt.encode('utf-8')).hexdigest()[:16]

        # Create execution record
        execution = TaskExecution(
            task_hash=task_hash,
            task_pattern=task_pattern,
            initial_tier=initial_tier,
            final_tier=final_tier,
            escalated=escalated,
            quality_score=quality_score,
            execution_time_ms=execution_time_ms,
            timestamp=datetime.now().isoformat(),
            success=success
        )

        # Add to history
        self.feedback_history.append(execution)

        # Save to disk
        self._save_feedback()

        # Trigger optimization every 10 tasks
        if len(self.feedback_history) % 10 == 0:
            self._update_pattern_statistics()

    def _update_pattern_statistics(self):
        """Update pattern statistics based on feedback history."""
        # Group executions by pattern
        pattern_executions = defaultdict(list)
        for exec in self.feedback_history:
            pattern_executions[exec.task_pattern].append(exec)

        # Calculate statistics for each pattern
        for pattern, executions in pattern_executions.items():
            stats = self._calculate_pattern_stats(pattern, executions)
            self.pattern_stats[pattern] = stats

        # Save optimizations
        self._save_optimizations()

    def _calculate_pattern_stats(
        self,
        pattern: str,
        executions: List[TaskExecution]
    ) -> PatternStatistics:
        """
        Calculate statistics for a specific pattern.

        Args:
            pattern: Pattern name
            executions: List of executions for this pattern

        Returns:
            PatternStatistics
        """
        tier_executions = defaultdict(list)
        tier_escalations = defaultdict(int)
        tier_totals = defaultdict(int)

        for exec in executions:
            tier_executions[exec.initial_tier].append(exec)
            tier_totals[exec.initial_tier] += 1
            if exec.escalated:
                tier_escalations[exec.initial_tier] += 1

        # Calculate success rates
        tier_success_rates = {}
        avg_quality_scores = {}
        escalation_rates = {}

        for tier in ["opus", "sonnet", "haiku"]:
            execs = tier_executions.get(tier, [])
            if execs:
                successful = [e for e in execs if e.success and not e.escalated]
                tier_success_rates[tier] = len(successful) / len(execs)
                avg_quality_scores[tier] = sum(e.quality_score for e in execs) / len(execs)
                escalation_rates[tier] = tier_escalations[tier] / tier_totals[tier]
            else:
                tier_success_rates[tier] = 0.0
                avg_quality_scores[tier] = 0.0
                escalation_rates[tier] = 0.0

        # Determine recommended tier
        # Prefer lower-cost tiers if success rate is good
        recommended_tier = "opus"  # Default
        confidence = 0.5

        if tier_success_rates.get("haiku", 0) > 0.85 and avg_quality_scores.get("haiku", 0) > 0.90:
            recommended_tier = "haiku"
            confidence = tier_success_rates["haiku"]
        elif tier_success_rates.get("sonnet", 0) > 0.75 and avg_quality_scores.get("sonnet", 0) > 0.85:
            recommended_tier = "sonnet"
            confidence = tier_success_rates["sonnet"]

        return PatternStatistics(
            pattern=pattern,
            total_executions=len(executions),
            tier_success_rates=tier_success_rates,
            avg_quality_scores=avg_quality_scores,
            escalation_rate=escalation_rates,
            recommended_tier=recommended_tier,
            confidence=confidence
        )

    def get_pattern_recommendation(self, pattern: str) -> Optional[PatternStatistics]:
        """
        Get routing recommendation for a pattern.

        Args:
            pattern: Task pattern

        Returns:
            PatternStatistics if available, else None
        """
        return self.pattern_stats.get(pattern)

    def optimize_classifier_patterns(self) -> List[Dict[str, Any]]:
        """
        Generate optimization suggestions for TaskClassifier.

        Returns:
            List of suggested pattern adjustments
        """
        suggestions = []

        for pattern, stats in self.pattern_stats.items():
            # Only suggest if we have enough data (>20 executions)
            if stats.total_executions < 20:
                continue

            # Suggest downgrade if lower tier performs well
            current_tier = stats.recommended_tier

            if current_tier == "haiku" and stats.tier_success_rates.get("haiku", 0) > 0.90:
                suggestions.append({
                    "pattern": pattern,
                    "action": "keep_haiku",
                    "reasoning": f"Haiku performs excellently ({stats.tier_success_rates['haiku']:.0%} success)",
                    "confidence": stats.confidence
                })
            elif current_tier == "sonnet" and stats.tier_success_rates.get("haiku", 0) > 0.85:
                suggestions.append({
                    "pattern": pattern,
                    "action": "downgrade_to_haiku",
                    "reasoning": f"Haiku could handle this ({stats.tier_success_rates['haiku']:.0%} success)",
                    "confidence": stats.confidence
                })
            elif current_tier == "opus" and stats.tier_success_rates.get("sonnet", 0) > 0.80:
                suggestions.append({
                    "pattern": pattern,
                    "action": "downgrade_to_sonnet",
                    "reasoning": f"Sonnet could handle this ({stats.tier_success_rates['sonnet']:.0%} success)",
                    "confidence": stats.confidence
                })

            # Suggest upgrade if high escalation rate
            if stats.escalation_rate.get(current_tier, 0) > 0.20:
                suggestions.append({
                    "pattern": pattern,
                    "action": "upgrade_tier",
                    "reasoning": f"High escalation rate ({stats.escalation_rate[current_tier]:.0%})",
                    "confidence": 0.8
                })

        return suggestions

    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary of learning feedback.

        Returns:
            Summary statistics
        """
        total_executions = len(self.feedback_history)

        if total_executions == 0:
            return {"total_executions": 0}

        escalated = sum(1 for e in self.feedback_history if e.escalated)
        avg_quality = sum(e.quality_score for e in self.feedback_history) / total_executions

        tier_distribution = defaultdict(int)
        for exec in self.feedback_history:
            tier_distribution[exec.initial_tier] += 1

        return {
            "total_executions": total_executions,
            "escalation_rate": escalated / total_executions,
            "avg_quality_score": avg_quality,
            "tier_distribution": dict(tier_distribution),
            "patterns_tracked": len(self.pattern_stats)
        }
