"""
Change Summary Service.

Fasst Diff-Ergebnisse in menschenlesbare Zusammenfassungen.
"""

from dataclasses import dataclass
from typing import List

import structlog

from app.services.diff.text_diff_engine import TextDiffResult

logger = structlog.get_logger(__name__)


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class ChangeSummary:
    """Zusammenfassung von Änderungen."""

    summary_text: str  # Deutsche Beschreibung
    change_count: int
    similarity_percent: float
    key_changes: List[str]  # Top 5 wichtigste Änderungen


# ============================================================================
# CHANGE SUMMARY SERVICE
# ============================================================================


class ChangeSummaryService:
    """Service für Änderungs-Zusammenfassungen."""

    def summarize(self, diff: TextDiffResult) -> ChangeSummary:
        """
        Erstellt Zusammenfassung aus Diff.

        Args:
            diff: TextDiffResult

        Returns:
            ChangeSummary
        """
        logger.info("change_summary_started", hunks_count=len(diff.hunks))

        # Summary-Text generieren
        if diff.similarity >= 0.95:
            summary_text = "Minimale Änderungen (>95% identisch)"
        elif diff.similarity >= 0.80:
            summary_text = "Moderate Änderungen (80-95% identisch)"
        elif diff.similarity >= 0.50:
            summary_text = "Signifikante Änderungen (50-80% identisch)"
        else:
            summary_text = "Umfangreiche Änderungen (<50% identisch)"

        # Key Changes extrahieren (Top 5 größte Hunks)
        sorted_hunks = sorted(
            diff.hunks,
            key=lambda h: len(h.content_a) + len(h.content_b),
            reverse=True,
        )

        key_changes: List[str] = []
        for hunk in sorted_hunks[:5]:
            if hunk.change_type == "added":
                preview = hunk.content_b[:100]
                key_changes.append(f"Hinzugefügt: {preview}...")
            elif hunk.change_type == "deleted":
                preview = hunk.content_a[:100]
                key_changes.append(f"Gelöscht: {preview}...")
            else:
                key_changes.append("Textänderung")

        change_count = diff.additions + diff.deletions + diff.modifications

        summary = ChangeSummary(
            summary_text=summary_text,
            change_count=change_count,
            similarity_percent=round(diff.similarity * 100, 2),
            key_changes=key_changes,
        )

        logger.info(
            "change_summary_completed",
            change_count=change_count,
            similarity_percent=summary.similarity_percent,
        )

        return summary
