#!/usr/bin/env python3
"""
Metrics Collection für Multi-Model Orchestration.

Trackt Performance-Metriken über Zeit:
- Total tasks processed
- Tier-Distribution (Opus/Sonnet/Haiku)
- Escalation rate
- Average quality score
- Cache hit rate
- Token savings vs Opus-only baseline

Speichert in: .claude/cache/orchestration_metrics.json
"""

import json
import os
import tempfile
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Union
from datetime import datetime
from collections import defaultdict

# Cross-platform file locking - support both package and direct imports
try:
    from .file_lock import file_lock
except ImportError:
    from file_lock import file_lock


@dataclass
class MetricsSnapshot:
    """Snapshot der Metriken zu einem Zeitpunkt."""

    timestamp: str
    total_tasks: int
    tasks_by_tier: Dict[str, int]  # opus/sonnet/haiku → count
    escalations_total: int
    escalations_by_tier: Dict[str, int]  # haiku→sonnet, sonnet→opus
    avg_quality_score: float
    cache_hits: int
    cache_misses: int
    total_tokens_used: int  # Geschätzte Token-Anzahl
    tokens_saved_vs_opus: int  # Einsparung vs Opus-only
    # Extended fields for tests compatibility
    tokens_by_tier: Optional[Dict[str, int]] = None  # Per-tier token tracking
    quality_by_tier: Optional[Dict[str, float]] = None  # Per-tier quality scores
    cache_hit_rate: float = 0.0  # Calculated cache hit rate
    token_savings_pct: float = 0.0  # Token savings percentage


class OrchestrationMetrics:
    """Sammelt und verwaltet Orchestrierungs-Metriken."""

    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize metrics collector.

        Args:
            cache_dir: Directory für Cache-Dateien (default: absolute path to .claude/cache)
        """
        if cache_dir is None:
            # Use absolute path to prevent directory duplication
            cache_dir = Path(__file__).parent.parent / "cache"

        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.metrics_file = self.cache_dir / "orchestration_metrics.json"

        # Current session metrics
        self.total_tasks = 0
        self.tasks_by_tier: Dict[str, int] = defaultdict(int)
        self.escalations_total = 0
        self.escalations_by_tier: Dict[str, int] = defaultdict(int)
        self.quality_scores: List[float] = []
        self.cache_hits = 0
        self.cache_misses = 0

        # Token tracking
        self.total_tokens_used = 0
        self.tokens_saved_vs_opus = 0
        self.tokens_by_tier: Dict[str, int] = defaultdict(int)

        # Quality tracking per tier
        self.quality_scores_by_tier: Dict[str, List[float]] = defaultdict(list)

        # Historical snapshots
        self.snapshots: List[MetricsSnapshot] = []

        self._load_metrics()

    def _file_lock(self, file_path: Path, mode: str = 'r'):
        """
        Context manager for file locking (thread-safe file access).

        Args:
            file_path: Path to file to lock
            mode: File open mode ('r' or 'w')

        Returns:
            Context manager from file_lock utility
        """
        # Use cross-platform file_lock utility
        return file_lock(file_path, mode)

    def _load_metrics(self) -> None:
        """Load metrics from disk with file locking."""
        if self.metrics_file.exists():
            try:
                with self._file_lock(self.metrics_file, 'r'):
                    data = json.loads(self.metrics_file.read_text(encoding='utf-8'))

                    self.total_tasks = data.get("total_tasks", 0)
                    self.tasks_by_tier = defaultdict(int, data.get("tasks_by_tier", {}))
                    self.escalations_total = data.get("escalations_total", 0)
                    self.escalations_by_tier = defaultdict(int, data.get("escalations_by_tier", {}))
                    self.quality_scores = data.get("quality_scores", [])
                    self.cache_hits = data.get("cache_hits", 0)
                    self.cache_misses = data.get("cache_misses", 0)
                    self.total_tokens_used = data.get("total_tokens_used", 0)
                    self.tokens_saved_vs_opus = data.get("tokens_saved_vs_opus", 0)

                    # Load historical snapshots
                    self.snapshots = [
                        MetricsSnapshot(**snap) for snap in data.get("snapshots", [])
                    ]

            except Exception as e:
                print(f"Warning: Could not load metrics: {e}")

    def _save_metrics(self) -> None:
        """
        Save metrics to disk with atomic write and file locking.

        Uses temp file + os.replace to ensure atomicity.
        """
        try:
            data = {
                "total_tasks": self.total_tasks,
                "tasks_by_tier": dict(self.tasks_by_tier),
                "escalations_total": self.escalations_total,
                "escalations_by_tier": dict(self.escalations_by_tier),
                "quality_scores": self.quality_scores,
                "cache_hits": self.cache_hits,
                "cache_misses": self.cache_misses,
                "total_tokens_used": self.total_tokens_used,
                "tokens_saved_vs_opus": self.tokens_saved_vs_opus,
                "snapshots": [asdict(snap) for snap in self.snapshots],
                "last_updated": datetime.now().isoformat()
            }

            with self._file_lock(self.metrics_file, 'w'):
                # Write to temporary file first (atomic write pattern)
                temp_fd, temp_path = tempfile.mkstemp(
                    dir=self.cache_dir,
                    prefix='.metrics_',
                    suffix='.tmp'
                )
                try:
                    with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)

                    # Atomic replace (POSIX guarantees atomicity)
                    os.replace(temp_path, self.metrics_file)
                except Exception:
                    # Clean up temp file on error
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                    raise
        except Exception as e:
            print(f"Warning: Could not save metrics: {e}")

    def record_task(
        self,
        tier: str,
        tokens_used: int,
        quality_score: float,
        escalated: bool = False,
        escalation_path: Optional[str] = None,
        cache_hit: bool = False
    ) -> None:
        """
        Record a task execution.

        Args:
            tier: Used tier (opus/sonnet/haiku)
            tokens_used: Estimated token count
            quality_score: Final quality score (0-1)
            escalated: Whether task was escalated
            escalation_path: If escalated, path (e.g., "haiku->sonnet")
            cache_hit: Whether cache was used
        """
        # Increment counters
        self.total_tasks += 1
        self.tasks_by_tier[tier] += 1
        self.quality_scores.append(quality_score)
        self.quality_scores_by_tier[tier].append(quality_score)
        self.tokens_by_tier[tier] += tokens_used

        # Track escalations
        if escalated:
            self.escalations_total += 1
            if escalation_path:
                self.escalations_by_tier[escalation_path] += 1

        # Track cache
        if cache_hit:
            self.cache_hits += 1
        else:
            self.cache_misses += 1

        # Track tokens
        self.total_tokens_used += tokens_used

        # Calculate savings vs Opus baseline
        # Opus baseline = if all tasks used Opus (tokens_used / tier_cost * 1.0)
        tier_costs = {"opus": 1.0, "sonnet": 0.2, "haiku": 0.05}
        tier_cost = tier_costs.get(tier, 1.0)

        # Opus-equivalent tokens = tokens that would have been used if Opus
        opus_equivalent = int(tokens_used / tier_cost)
        savings = opus_equivalent - tokens_used
        self.tokens_saved_vs_opus += savings

        # Save to disk
        self._save_metrics()

        # Create snapshot every 10 tasks
        if self.total_tasks % 10 == 0:
            self._create_snapshot()

    def record_cache_hit(self) -> None:
        """Record a cache hit."""
        self.cache_hits += 1
        self._save_metrics()

    def record_cache_miss(self) -> None:
        """Record a cache miss."""
        self.cache_misses += 1
        self._save_metrics()

    def reset(self) -> None:
        """Reset all metrics to zero (alias for reset_metrics)."""
        self.reset_metrics()

    def _create_snapshot(self) -> None:
        """Create and save a metrics snapshot."""
        snapshot = MetricsSnapshot(
            timestamp=datetime.now().isoformat(),
            total_tasks=self.total_tasks,
            tasks_by_tier=dict(self.tasks_by_tier),
            escalations_total=self.escalations_total,
            escalations_by_tier=dict(self.escalations_by_tier),
            avg_quality_score=self.get_avg_quality_score(),
            cache_hits=self.cache_hits,
            cache_misses=self.cache_misses,
            total_tokens_used=self.total_tokens_used,
            tokens_saved_vs_opus=self.tokens_saved_vs_opus
        )

        self.snapshots.append(snapshot)

        # Keep only last 100 snapshots (for performance)
        if len(self.snapshots) > 100:
            self.snapshots = self.snapshots[-100:]

        self._save_metrics()

    def get_snapshot(self) -> MetricsSnapshot:
        """Get current metrics as a snapshot object.

        Returns:
            MetricsSnapshot with current metric values
        """
        # Calculate quality by tier
        quality_by_tier = {}
        for tier, scores in self.quality_scores_by_tier.items():
            if scores:
                quality_by_tier[tier] = sum(scores) / len(scores)

        return MetricsSnapshot(
            timestamp=datetime.now().isoformat(),
            total_tasks=self.total_tasks,
            tasks_by_tier=dict(self.tasks_by_tier),
            escalations_total=self.escalations_total,
            escalations_by_tier=dict(self.escalations_by_tier),
            avg_quality_score=self.get_avg_quality_score(),
            cache_hits=self.cache_hits,
            cache_misses=self.cache_misses,
            total_tokens_used=self.total_tokens_used,
            tokens_saved_vs_opus=self.tokens_saved_vs_opus,
            tokens_by_tier=dict(self.tokens_by_tier),
            quality_by_tier=quality_by_tier,
            cache_hit_rate=self.get_cache_hit_rate(),
            token_savings_pct=self.get_token_savings_percentage()
        )

    def get_avg_quality_score(self) -> float:
        """
        Get average quality score across all tasks.

        Returns:
            Average quality score (0-1), or 0.0 if no tasks
        """
        if not self.quality_scores:
            return 0.0
        return sum(self.quality_scores) / len(self.quality_scores)

    def get_escalation_rate(self) -> float:
        """
        Get escalation rate (percentage of tasks escalated).

        Returns:
            Escalation rate (0.0 - 1.0)
        """
        if self.total_tasks == 0:
            return 0.0
        return self.escalations_total / self.total_tasks

    def get_cache_hit_rate(self) -> float:
        """
        Get cache hit rate.

        Returns:
            Cache hit rate (0.0 - 1.0)
        """
        total_cache_requests = self.cache_hits + self.cache_misses
        if total_cache_requests == 0:
            return 0.0
        return self.cache_hits / total_cache_requests

    def get_tier_distribution(self) -> Dict[str, float]:
        """
        Get tier distribution as percentages.

        Returns:
            Dictionary with tier → percentage (0.0 - 1.0)
        """
        if self.total_tasks == 0:
            return {"opus": 0.0, "sonnet": 0.0, "haiku": 0.0}

        return {
            tier: count / self.total_tasks
            for tier, count in self.tasks_by_tier.items()
        }

    def get_token_savings_percentage(self) -> float:
        """
        Get token savings vs Opus-only baseline.

        Returns:
            Savings percentage (0.0 - 1.0)
        """
        if self.total_tokens_used == 0:
            return 0.0

        # Opus-equivalent = total_tokens_used + tokens_saved_vs_opus
        opus_equivalent = self.total_tokens_used + self.tokens_saved_vs_opus

        if opus_equivalent == 0:
            return 0.0

        return self.tokens_saved_vs_opus / opus_equivalent

    def get_summary(self) -> Dict[str, Union[int, float, str, Dict[str, float], Dict[str, str]]]:
        """
        Get comprehensive metrics summary.

        Returns:
            Dictionary with all key metrics
        """
        tier_dist = self.get_tier_distribution()

        return {
            "total_tasks": self.total_tasks,
            "tier_distribution": {
                tier: f"{pct:.1%}" for tier, pct in tier_dist.items()
            },
            "tier_distribution_raw": tier_dist,
            "escalation_rate": f"{self.get_escalation_rate():.1%}",
            "escalation_rate_raw": self.get_escalation_rate(),
            "avg_quality_score": f"{self.get_avg_quality_score():.2f}",
            "avg_quality_score_raw": self.get_avg_quality_score(),
            "cache_hit_rate": f"{self.get_cache_hit_rate():.1%}",
            "cache_hit_rate_raw": self.get_cache_hit_rate(),
            "total_tokens_used": f"{self.total_tokens_used:,}",
            "total_tokens_used_raw": self.total_tokens_used,
            "tokens_saved": f"{self.tokens_saved_vs_opus:,}",
            "tokens_saved_raw": self.tokens_saved_vs_opus,
            "token_savings_percentage": f"{self.get_token_savings_percentage():.1%}",
            "token_savings_percentage_raw": self.get_token_savings_percentage()
        }

    def print_summary(self) -> None:
        """Print formatted metrics summary to console."""
        summary = self.get_summary()

        print("\n" + "=" * 60)
        print("🎯 MULTI-MODEL ORCHESTRATION - METRIKEN ÜBERSICHT")
        print("=" * 60)

        print(f"\n📊 TASKS:")
        print(f"   Gesamt verarbeitet: {summary['total_tasks']}")
        print(f"   Tier-Verteilung:")
        for tier, pct in summary['tier_distribution'].items():
            icon = {"opus": "🧠", "sonnet": "⚙️", "haiku": "✨"}.get(tier, "🤖")
            print(f"     {icon} {tier.upper()}: {pct}")

        print(f"\n⬆️  ESKALATIONEN:")
        print(f"   Rate: {summary['escalation_rate']}")
        print(f"   Total: {self.escalations_total} von {self.total_tasks}")

        print(f"\n✅ QUALITÄT:")
        print(f"   Durchschnitt: {summary['avg_quality_score']}")

        print(f"\n♻️  CACHE:")
        print(f"   Hit Rate: {summary['cache_hit_rate']}")
        print(f"   Hits: {self.cache_hits}, Misses: {self.cache_misses}")

        print(f"\n💰 TOKEN-EINSPARUNGEN:")
        print(f"   Total verwendet: {summary['total_tokens_used']}")
        print(f"   Gespart vs Opus: {summary['tokens_saved']}")
        print(f"   Einsparung: {summary['token_savings_percentage']}")

        print("=" * 60 + "\n")

    def get_historical_trends(self, last_n: int = 10) -> List[MetricsSnapshot]:
        """
        Get historical snapshots.

        Args:
            last_n: Number of recent snapshots to return

        Returns:
            List of recent snapshots
        """
        return self.snapshots[-last_n:]

    def reset_metrics(self) -> None:
        """
        Reset all metrics (use with caution!).

        Keeps historical snapshots for analysis.
        """
        # Create final snapshot before reset
        if self.total_tasks > 0:
            self._create_snapshot()

        # Reset counters
        self.total_tasks = 0
        self.tasks_by_tier = defaultdict(int)
        self.escalations_total = 0
        self.escalations_by_tier = defaultdict(int)
        self.quality_scores = []
        self.quality_scores_by_tier = defaultdict(list)
        self.cache_hits = 0
        self.cache_misses = 0
        self.total_tokens_used = 0
        self.tokens_saved_vs_opus = 0
        self.tokens_by_tier = defaultdict(int)

        self._save_metrics()


# Beispiel-Nutzung für Testing
if __name__ == "__main__":
    # Create test metrics
    metrics = OrchestrationMetrics()

    print("=== SIMULATING TASK EXECUTIONS ===\n")

    # Simulate 50 tasks with realistic distribution
    import random

    for i in range(50):
        # Realistic tier distribution: 30% Opus, 50% Sonnet, 20% Haiku
        rand = random.random()
        if rand < 0.20:
            tier = "haiku"
            tokens = random.randint(1000, 3000)
            quality = random.uniform(0.92, 0.98)
            escalated = random.random() < 0.05  # 5% escalation
        elif rand < 0.70:
            tier = "sonnet"
            tokens = random.randint(3000, 8000)
            quality = random.uniform(0.88, 0.95)
            escalated = random.random() < 0.08  # 8% escalation
        else:
            tier = "opus"
            tokens = random.randint(8000, 20000)
            quality = random.uniform(0.95, 1.0)
            escalated = False  # Opus never escalates

        # Simulate cache hits (30% for Sonnet/Haiku)
        cache_hit = tier in ["sonnet", "haiku"] and random.random() < 0.30

        # Escalation path
        escalation_path = None
        if escalated:
            if tier == "haiku":
                escalation_path = "haiku->sonnet"
            elif tier == "sonnet":
                escalation_path = "sonnet->opus"

        metrics.record_task(
            tier=tier,
            tokens_used=tokens,
            quality_score=quality,
            escalated=escalated,
            escalation_path=escalation_path,
            cache_hit=cache_hit
        )

    # Print summary
    metrics.print_summary()

    # Show historical trends
    print("=== HISTORICAL TRENDS (Last 5 Snapshots) ===")
    trends = metrics.get_historical_trends(last_n=5)
    for i, snap in enumerate(trends, 1):
        print(f"\nSnapshot {i}:")
        print(f"  Time: {snap.timestamp}")
        print(f"  Tasks: {snap.total_tasks}")
        print(f"  Avg Quality: {snap.avg_quality_score:.2f}")
        print(f"  Savings: {snap.tokens_saved_vs_opus / (snap.total_tokens_used + snap.tokens_saved_vs_opus):.1%}")
