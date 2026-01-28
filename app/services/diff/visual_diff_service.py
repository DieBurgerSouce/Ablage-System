"""Visual Version Diff Service.

Seite-an-Seite Vergleich mit Hervorhebungen fuer Vertraege und Dokumente.
"""
from __future__ import annotations

import difflib
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence
from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)


class DiffType(str, Enum):
    """Typ der Aenderung."""
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"


@dataclass
class DiffBlock:
    """Ein Block von Aenderungen."""
    diff_type: DiffType
    old_text: str = ""
    new_text: str = ""
    old_line_start: int = 0
    old_line_end: int = 0
    new_line_start: int = 0
    new_line_end: int = 0
    page_number: int = 1


@dataclass
class DiffResult:
    """Ergebnis eines Dokumentvergleichs."""
    document_a_id: str
    document_b_id: str
    total_changes: int = 0
    additions: int = 0
    deletions: int = 0
    modifications: int = 0
    similarity_ratio: float = 0.0
    blocks: list[DiffBlock] = field(default_factory=list)
    summary: str = ""
    pages_affected: list[int] = field(default_factory=list)


@dataclass
class ChangeSummary:
    """Zusammenfassung der Aenderungen."""
    total_changes: int
    additions: int
    deletions: int
    modifications: int
    similarity_percentage: float
    key_changes: list[str]
    risk_level: str  # low, medium, high


class VisualDiffService:
    """Service fuer visuellen Dokumentenvergleich."""

    def compare_texts(
        self,
        text_a: str,
        text_b: str,
        document_a_id: str = "",
        document_b_id: str = "",
        context_lines: int = 3,
    ) -> DiffResult:
        """Vergleicht zwei Texte und erzeugt ein Diff-Ergebnis.

        Args:
            text_a: Originaltext
            text_b: Neuer Text
            document_a_id: ID des Originaldokuments
            document_b_id: ID des neuen Dokuments
            context_lines: Kontextzeilen um Aenderungen

        Returns:
            DiffResult mit allen Aenderungen
        """
        lines_a = text_a.splitlines(keepends=True)
        lines_b = text_b.splitlines(keepends=True)

        matcher = difflib.SequenceMatcher(None, lines_a, lines_b)
        ratio = matcher.ratio()

        blocks: list[DiffBlock] = []
        additions = 0
        deletions = 0
        modifications = 0

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                blocks.append(DiffBlock(
                    diff_type=DiffType.UNCHANGED,
                    old_text="".join(lines_a[i1:i2]),
                    new_text="".join(lines_b[j1:j2]),
                    old_line_start=i1 + 1,
                    old_line_end=i2,
                    new_line_start=j1 + 1,
                    new_line_end=j2,
                ))
            elif tag == "replace":
                modifications += 1
                blocks.append(DiffBlock(
                    diff_type=DiffType.MODIFIED,
                    old_text="".join(lines_a[i1:i2]),
                    new_text="".join(lines_b[j1:j2]),
                    old_line_start=i1 + 1,
                    old_line_end=i2,
                    new_line_start=j1 + 1,
                    new_line_end=j2,
                ))
            elif tag == "insert":
                additions += 1
                blocks.append(DiffBlock(
                    diff_type=DiffType.ADDED,
                    new_text="".join(lines_b[j1:j2]),
                    new_line_start=j1 + 1,
                    new_line_end=j2,
                ))
            elif tag == "delete":
                deletions += 1
                blocks.append(DiffBlock(
                    diff_type=DiffType.REMOVED,
                    old_text="".join(lines_a[i1:i2]),
                    old_line_start=i1 + 1,
                    old_line_end=i2,
                ))

        total_changes = additions + deletions + modifications

        result = DiffResult(
            document_a_id=document_a_id,
            document_b_id=document_b_id,
            total_changes=total_changes,
            additions=additions,
            deletions=deletions,
            modifications=modifications,
            similarity_ratio=ratio,
            blocks=blocks,
            summary=self._generate_summary_text(total_changes, additions, deletions, modifications, ratio),
        )

        logger.info(
            "diff_completed",
            total_changes=total_changes,
            similarity=f"{ratio:.2%}",
        )
        return result

    def generate_change_summary(self, diff_result: DiffResult) -> ChangeSummary:
        """Erzeugt eine strukturierte Zusammenfassung der Aenderungen.

        Args:
            diff_result: Ergebnis des Vergleichs

        Returns:
            ChangeSummary mit Risikobewertung
        """
        key_changes: list[str] = []

        for block in diff_result.blocks:
            if block.diff_type == DiffType.MODIFIED:
                old_preview = block.old_text[:100].strip()
                new_preview = block.new_text[:100].strip()
                key_changes.append(
                    f"Zeile {block.old_line_start}: '{old_preview}' -> '{new_preview}'"
                )
            elif block.diff_type == DiffType.ADDED:
                preview = block.new_text[:100].strip()
                key_changes.append(f"Hinzugefuegt (Zeile {block.new_line_start}): '{preview}'")
            elif block.diff_type == DiffType.REMOVED:
                preview = block.old_text[:100].strip()
                key_changes.append(f"Entfernt (Zeile {block.old_line_start}): '{preview}'")

        # Risikobewertung
        similarity = diff_result.similarity_ratio
        if similarity >= 0.95:
            risk_level = "low"
        elif similarity >= 0.80:
            risk_level = "medium"
        else:
            risk_level = "high"

        return ChangeSummary(
            total_changes=diff_result.total_changes,
            additions=diff_result.additions,
            deletions=diff_result.deletions,
            modifications=diff_result.modifications,
            similarity_percentage=round(similarity * 100, 2),
            key_changes=key_changes[:20],  # Max 20 Aenderungen
            risk_level=risk_level,
        )

    def compute_text_hash(self, text: str) -> str:
        """Berechnet SHA-256 Hash eines Textes."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _generate_summary_text(
        self,
        total: int,
        additions: int,
        deletions: int,
        modifications: int,
        ratio: float,
    ) -> str:
        """Erzeugt einen lesbaren Zusammenfassungstext."""
        parts: list[str] = []
        if additions > 0:
            parts.append(f"{additions} Hinzufuegung(en)")
        if deletions > 0:
            parts.append(f"{deletions} Loeschung(en)")
        if modifications > 0:
            parts.append(f"{modifications} Aenderung(en)")

        if not parts:
            return "Keine Aenderungen gefunden."

        changes_text = ", ".join(parts)
        return (
            f"{total} Aenderungen insgesamt: {changes_text}. "
            f"Aehnlichkeit: {ratio:.1%}"
        )
