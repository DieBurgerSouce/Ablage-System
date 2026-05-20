"""
Decision Cache für Multi-Model Orchestration.

Cached Opus-Entscheidungen zur Wiederverwendung durch Sonnet/Haiku:
- Speichert Architekturentscheidungen persistent
- Ermöglicht Suche nach relevanten Entscheidungen
- Automatische Expiration und Invalidierung
"""

import json
import hashlib
import os
import tempfile
import logging
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any

# Cross-platform file locking - support both package and direct imports
try:
    from .file_lock import file_lock
except ImportError:
    from file_lock import file_lock

# Setup Logging
logger = logging.getLogger("orchestration.decision_cache")


@dataclass
class CachedDecision:
    """Eine gecachte Architekturentscheidung."""
    decision_hash: str
    task_description: str
    decision: str
    reasoning: str
    affected_patterns: List[str]
    affected_files: List[str]
    created_at: str
    expires_at: str
    model_used: str
    confidence: float
    tags: List[str]
    context_hash: str


class DecisionCache:
    """Cache für Opus-Entscheidungen zur Wiederverwendung durch Sonnet."""

    # Use absolute path to prevent directory duplication
    CACHE_DIR = Path(__file__).parent.parent / "cache"
    CACHE_FILE = CACHE_DIR / "decisions.json"
    STATS_FILE = CACHE_DIR / "cache_stats.json"
    DEFAULT_TTL_DAYS = 7
    MAX_CACHE_SIZE = 1000  # Maximale Anzahl Einträge

    def __init__(self):
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, CachedDecision] = self._load_cache()
        self._stats = self._load_stats()

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

    def _load_cache(self) -> Dict[str, CachedDecision]:
        """
        Lädt Cache von Disk with file locking.

        Returns:
            Dictionary mit gecachten Entscheidungen
        """
        if not self.CACHE_FILE.exists():
            return {}

        try:
            with self._file_lock(self.CACHE_FILE, 'r'):
                with open(self.CACHE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {
                        k: CachedDecision(**v)
                        for k, v in data.items()
                    }
        except Exception as e:
            logger.warning("cache_load_failed", error=str(e))
            return {}

    def _save_cache(self) -> None:
        """
        Speichert Cache auf Disk with atomic write and file locking.

        Uses temp file + os.replace to ensure atomicity.
        """
        try:
            # Prepare data
            data = {k: asdict(v) for k, v in self._cache.items()}

            with self._file_lock(self.CACHE_FILE, 'w'):
                # Write to temporary file first (atomic write pattern)
                temp_fd, temp_path = tempfile.mkstemp(
                    dir=self.CACHE_DIR,
                    prefix='.decisions_',
                    suffix='.tmp'
                )
                try:
                    with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)

                    # Atomic replace (POSIX guarantees atomicity)
                    os.replace(temp_path, self.CACHE_FILE)
                except Exception:
                    # Clean up temp file on error
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                    raise
        except Exception as e:
            logger.error("cache_save_failed", error=str(e))

    def _load_stats(self) -> Dict[str, Any]:
        """Lädt Cache-Statistiken with file locking."""
        if not self.STATS_FILE.exists():
            return {
                "total_stores": 0,
                "total_hits": 0,
                "total_misses": 0,
                "last_cleanup": datetime.utcnow().isoformat(),
            }

        try:
            with self._file_lock(self.STATS_FILE, 'r'):
                with open(self.STATS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            return {
                "total_stores": 0,
                "total_hits": 0,
                "total_misses": 0,
                "last_cleanup": datetime.utcnow().isoformat(),
            }

    def _save_stats(self) -> None:
        """Speichert Cache-Statistiken with atomic write and file locking."""
        try:
            with self._file_lock(self.STATS_FILE, 'w'):
                # Atomic write pattern
                temp_fd, temp_path = tempfile.mkstemp(
                    dir=self.CACHE_DIR,
                    prefix='.stats_',
                    suffix='.tmp'
                )
                try:
                    with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                        json.dump(self._stats, f, indent=2, ensure_ascii=False)
                    os.replace(temp_path, self.STATS_FILE)
                except Exception:
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                    raise
        except Exception as e:
            logger.error("stats_save_failed", error=str(e))

    def _generate_hash(self, task: str, patterns: List[str]) -> str:
        """
        Generiert Hash für Duplikat-Erkennung.

        Args:
            task: Task-Beschreibung
            patterns: Betroffene Patterns

        Returns:
            16-stelliger Hash
        """
        content = f"{task}:{':'.join(sorted(patterns))}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _generate_context_hash(self, context: Dict[str, Any]) -> str:
        """Generiert Hash für Kontext-Änderungen."""
        # Vereinfachter Context-Hash basierend auf betroffenen Dateien
        files = context.get("affected_files", [])
        return hashlib.md5(":".join(sorted(files)).encode()).hexdigest()[:8]

    def store(
        self,
        task_description: str,
        decision: str,
        reasoning: str,
        affected_patterns: List[str],
        affected_files: List[str],
        model_used: str = "opus",
        confidence: float = 1.0,
        ttl_days: int = None,
        tags: List[str] = None,
        context: Dict[str, Any] = None
    ) -> str:
        """
        Speichert eine neue Entscheidung.

        Args:
            task_description: Beschreibung der Aufgabe
            decision: Getroffene Entscheidung
            reasoning: Begründung
            affected_patterns: Betroffene Code-Patterns
            affected_files: Betroffene Dateien
            model_used: Verwendetes Modell
            confidence: Confidence-Score
            ttl_days: Time-to-Live in Tagen
            tags: Tags für Kategorisierung
            context: Zusätzlicher Kontext

        Returns:
            Hash der gespeicherten Entscheidung
        """

        ttl = ttl_days if ttl_days is not None else self.DEFAULT_TTL_DAYS
        now = datetime.utcnow()
        tags = tags or []
        context = context or {}

        decision_hash = self._generate_hash(task_description, affected_patterns)
        context_hash = self._generate_context_hash(context)

        cached = CachedDecision(
            decision_hash=decision_hash,
            task_description=task_description,
            decision=decision,
            reasoning=reasoning,
            affected_patterns=affected_patterns,
            affected_files=affected_files,
            created_at=now.isoformat(),
            expires_at=(now + timedelta(days=ttl)).isoformat(),
            model_used=model_used,
            confidence=confidence,
            tags=tags,
            context_hash=context_hash
        )

        self._cache[decision_hash] = cached
        self._stats["total_stores"] += 1

        # Cleanup bei zu vielen Einträgen
        if len(self._cache) > self.MAX_CACHE_SIZE:
            self._cleanup_old_entries()

        self._save_cache()
        self._save_stats()

        return decision_hash

    def find_relevant(
        self,
        task_description: str,
        affected_files: List[str] = None,
        min_confidence: float = 0.7,
        tags: List[str] = None
    ) -> List[CachedDecision]:
        """
        Findet relevante gecachte Entscheidungen.

        Args:
            task_description: Beschreibung der aktuellen Aufgabe
            affected_files: Betroffene Dateien
            min_confidence: Minimale Confidence
            tags: Zu suchende Tags

        Returns:
            Liste relevanter Entscheidungen
        """

        self._cleanup_expired()
        relevant = []

        task_lower = task_description.lower()
        affected_files = affected_files or []
        tags = tags or []

        for decision in self._cache.values():
            # Prüfe Confidence
            if decision.confidence < min_confidence:
                continue

            relevance_score = 0

            # 1. Pattern-Übereinstimmung
            pattern_matches = sum(
                1 for pattern in decision.affected_patterns
                if pattern.lower() in task_lower
            )
            relevance_score += pattern_matches * 2

            # 2. Datei-Übereinstimmung
            file_matches = sum(
                1 for af in affected_files
                for df in decision.affected_files
                if af in df or df in af
            )
            relevance_score += file_matches * 3

            # 3. Tag-Übereinstimmung
            tag_matches = len(set(tags) & set(decision.tags))
            relevance_score += tag_matches * 1

            # 4. Textuelle Ähnlichkeit (einfach)
            text_similarity = self._calculate_text_similarity(
                task_lower,
                decision.task_description.lower()
            )
            relevance_score += text_similarity

            if relevance_score > 0:
                relevant.append((decision, relevance_score))

        # Sortiere nach Relevanz-Score
        relevant.sort(key=lambda x: x[1], reverse=True)

        # Update Stats
        if relevant:
            self._stats["total_hits"] += 1
        else:
            self._stats["total_misses"] += 1

        self._save_stats()

        return [decision for decision, _ in relevant[:5]]  # Top 5

    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """Berechnet einfache Textähnlichkeit."""
        words1 = set(text1.split())
        words2 = set(text2.split())

        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    def _cleanup_expired(self) -> None:
        """Entfernt abgelaufene Einträge."""
        now = datetime.utcnow()
        expired = [
            k for k, v in self._cache.items()
            if datetime.fromisoformat(v.expires_at) < now
        ]

        for k in expired:
            del self._cache[k]

        if expired:
            self._save_cache()
            logger.info(f"cache_expired_entries_removed: count={len(expired)}")

    def _cleanup_old_entries(self) -> None:
        """Entfernt älteste Einträge bei Überlauf."""
        if len(self._cache) <= self.MAX_CACHE_SIZE:
            return

        # Sortiere nach Erstellungsdatum
        sorted_entries = sorted(
            self._cache.items(),
            key=lambda x: x[1].created_at
        )

        # Entferne älteste Einträge
        to_remove = len(self._cache) - self.MAX_CACHE_SIZE + 100  # Puffer
        for i in range(to_remove):
            if i < len(sorted_entries):
                del self._cache[sorted_entries[i][0]]

        logger.info(f"cache_old_entries_removed: count={to_remove}, reason=size_limit")

    def invalidate_for_files(self, changed_files: List[str]) -> int:
        """
        Invalidiert Cache für geänderte Dateien.

        Args:
            changed_files: Liste geänderter Dateien

        Returns:
            Anzahl invalidierter Einträge
        """
        invalidated = 0

        for decision_hash, decision in list(self._cache.items()):
            should_invalidate = any(
                any(cf in af for af in decision.affected_files)
                for cf in changed_files
            )

            if should_invalidate:
                del self._cache[decision_hash]
                invalidated += 1

        if invalidated:
            self._save_cache()
            logger.info(f"cache_entries_invalidated: count={invalidated}, reason=files_changed")

        return invalidated

    def get_by_hash(self, decision_hash: str) -> Optional[CachedDecision]:
        """Holt Entscheidung per Hash."""
        return self._cache.get(decision_hash)

    def delete(self, decision_hash: str) -> bool:
        """
        Löscht eine Entscheidung.

        Args:
            decision_hash: Hash der zu löschenden Entscheidung

        Returns:
            True wenn gelöscht, False wenn nicht gefunden
        """
        if decision_hash in self._cache:
            del self._cache[decision_hash]
            self._save_cache()
            return True
        return False

    def get_stats(self) -> Dict[str, Any]:
        """
        Gibt Cache-Statistiken zurück.

        Returns:
            Dictionary mit Statistiken
        """
        self._cleanup_expired()

        hit_rate = 0.0
        total_requests = self._stats["total_hits"] + self._stats["total_misses"]
        if total_requests > 0:
            hit_rate = self._stats["total_hits"] / total_requests

        return {
            "total_entries": len(self._cache),
            "total_stores": self._stats["total_stores"],
            "total_hits": self._stats["total_hits"],
            "total_misses": self._stats["total_misses"],
            "hit_rate": f"{hit_rate:.1%}",
            "by_model": self._count_by_model(),
            "avg_confidence": self._avg_confidence(),
            "oldest_entry": self._get_oldest_entry(),
            "cache_size_mb": self._get_cache_size_mb(),
        }

    def _count_by_model(self) -> Dict[str, int]:
        """Zählt Einträge pro Modell."""
        counts = {}
        for decision in self._cache.values():
            counts[decision.model_used] = counts.get(decision.model_used, 0) + 1
        return counts

    def _avg_confidence(self) -> float:
        """Berechnet durchschnittliche Confidence."""
        if not self._cache:
            return 0.0
        return sum(d.confidence for d in self._cache.values()) / len(self._cache)

    def _get_oldest_entry(self) -> Optional[str]:
        """Findet ältesten Eintrag."""
        if not self._cache:
            return None

        oldest = min(self._cache.values(), key=lambda d: d.created_at)
        return oldest.created_at

    def _get_cache_size_mb(self) -> float:
        """Berechnet Cache-Größe in MB."""
        try:
            if self.CACHE_FILE.exists():
                return self.CACHE_FILE.stat().st_size / (1024 * 1024)
        except Exception:
            pass
        return 0.0

    def clear(self) -> None:
        """Leert den kompletten Cache."""
        self._cache.clear()
        self._stats = {
            "total_stores": 0,
            "total_hits": 0,
            "total_misses": 0,
            "last_cleanup": datetime.utcnow().isoformat(),
        }
        self._save_cache()
        self._save_stats()
        print("Cache komplett geleert")
