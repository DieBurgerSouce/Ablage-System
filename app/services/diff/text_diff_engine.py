"""
Text Diff Engine.

Vergleicht zwei Texte und generiert strukturierte Diff-Ergebnisse.

Features:
- difflib-basierter Textvergleich
- Line-by-Line Diff
- Similarity-Score (0-1)
- Hunks mit Kontext
"""

import difflib
from dataclasses import dataclass
from typing import List

import structlog

logger = structlog.get_logger(__name__)


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class DiffHunk:
    """Einzelner Diff-Abschnitt."""

    line_start_a: int
    line_start_b: int
    content_a: str
    content_b: str
    change_type: str  # added, deleted, modified


@dataclass
class TextDiffResult:
    """Text-Diff-Ergebnis."""

    additions: int
    deletions: int
    modifications: int
    hunks: List[DiffHunk]
    similarity: float  # 0-1


# ============================================================================
# TEXT DIFF ENGINE
# ============================================================================


class TextDiffEngine:
    """Engine für Text-basierte Diffs."""

    def diff_texts(self, text_a: str, text_b: str) -> TextDiffResult:
        """
        Vergleicht zwei Texte.

        Args:
            text_a: Erster Text
            text_b: Zweiter Text

        Returns:
            TextDiffResult mit Änderungen
        """
        logger.info(
            "text_diff_started",
            len_a=len(text_a),
            len_b=len(text_b),
        )

        lines_a = text_a.splitlines()
        lines_b = text_b.splitlines()

        # SequenceMatcher für Similarity
        matcher = difflib.SequenceMatcher(None, text_a, text_b)
        similarity = matcher.ratio()

        # Unified Diff
        diff = list(
            difflib.unified_diff(
                lines_a,
                lines_b,
                lineterm="",
                n=3,  # 3 Zeilen Kontext
            )
        )

        # Hunks parsen
        hunks: List[DiffHunk] = []
        additions = 0
        deletions = 0
        modifications = 0

        i = 0
        while i < len(diff):
            line = diff[i]

            if line.startswith("@@"):
                # Hunk-Header parsen: @@ -start_a,count_a +start_b,count_b @@
                line_start_a, line_start_b = self._parse_hunk_header(line)
                i += 1
                hunk_lines_a: List[str] = []
                hunk_lines_b: List[str] = []

                while i < len(diff) and not diff[i].startswith("@@"):
                    line = diff[i]
                    if line.startswith("-"):
                        hunk_lines_a.append(line[1:])
                        deletions += 1
                    elif line.startswith("+"):
                        hunk_lines_b.append(line[1:])
                        additions += 1
                    elif line.startswith(" "):
                        # Context (unverändert)
                        hunk_lines_a.append(line[1:])
                        hunk_lines_b.append(line[1:])
                    i += 1

                # Hunk erstellen
                if hunk_lines_a or hunk_lines_b:
                    change_type = "modified"
                    if not hunk_lines_a:
                        change_type = "added"
                    elif not hunk_lines_b:
                        change_type = "deleted"
                    else:
                        modifications += 1

                    hunks.append(
                        DiffHunk(
                            line_start_a=line_start_a,
                            line_start_b=line_start_b,
                            content_a="\n".join(hunk_lines_a),
                            content_b="\n".join(hunk_lines_b),
                            change_type=change_type,
                        )
                    )
            else:
                i += 1

        result = TextDiffResult(
            additions=additions,
            deletions=deletions,
            modifications=modifications,
            hunks=hunks,
            similarity=similarity,
        )

        logger.info(
            "text_diff_completed",
            additions=additions,
            deletions=deletions,
            similarity=similarity,
        )

        return result

    def _parse_hunk_header(self, header: str) -> tuple[int, int]:
        """Parst Hunk-Header und extrahiert Zeilennummern.

        Format: @@ -start_a,count_a +start_b,count_b @@

        Args:
            header: Hunk-Header-Zeile

        Returns:
            Tuple (line_start_a, line_start_b)
        """
        import re

        # Pattern: @@ -start_a[,count_a] +start_b[,count_b] @@
        pattern = r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@"
        match = re.search(pattern, header)

        if match:
            return int(match.group(1)), int(match.group(2))

        return 0, 0
