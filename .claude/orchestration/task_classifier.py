"""
Task Classifier für Multi-Model Orchestration.

Klassifiziert Aufgaben automatisch für das passende Claude-Modell:
- Opus: Architektur, Security, komplexe Entscheidungen
- Sonnet: Implementierung, Tests, Dokumentation
- Haiku: Formatierung, Boilerplate, einfache Validierung
"""

import re
from enum import Enum
from dataclasses import dataclass
from typing import List, Optional


class ModelTier(Enum):
    """Modell-Kategorien für Task-Routing."""
    OPUS_REQUIRED = "opus"
    SONNET_CAPABLE = "sonnet"
    HAIKU_SUFFICIENT = "haiku"


@dataclass
class ClassificationResult:
    """Ergebnis der Task-Klassifizierung."""
    tier: ModelTier
    confidence: float
    reasoning: str
    fallback_tier: Optional[ModelTier] = None


# Agent mapping: ModelTier → Agent name (für Claude Code Task() calls)
TIER_TO_AGENT = {
    ModelTier.OPUS_REQUIRED: "opus-task",
    ModelTier.SONNET_CAPABLE: "sonnet-implementation",
    ModelTier.HAIKU_SUFFICIENT: "haiku-task"
}


class TaskClassifier:
    """Klassifiziert Aufgaben für das passende Modell."""

    # Patterns die IMMER Opus erfordern
    OPUS_PATTERNS = [
        r"architektur",
        r"security|sicherheit",
        r"multi-?tenant",
        r"rls|row.level.security",
        r"gpu.*(management|allocation)",
        r"ocr.*(agent|backend)",
        r"refactor.*multiple|mehrere.*dateien",
        r"trade-?off",
        r"design.*(decision|entscheidung)",
        r"komplexe.*bug",
        r"neue.*feature.*architektur",
        r"sicherheitskritisch",
        r"deepseek|got-ocr|surya",
        r"multi.*backend",
        r"koordination",
    ]

    # Patterns für Sonnet
    SONNET_PATTERNS = [
        r"implement|implementier",
        r"test.*generat|erstell.*test|write.*test|unit.*test",
        r"dokumentation|docstring",
        r"api.*endpoint",
        r"crud",
        r"migration.*erstell",
        r"service.*layer",
        r"pydantic.*schema",
        r"sqlalchemy.*model",
        r"fastapi",
        r"pytest",
        r"playwright",
        r"code.*review",
        r"einzelne.*datei",
    ]

    # Patterns für Haiku - ERWEITERT für besseres Routing
    HAIKU_PATTERNS = [
        # Formatting & Style
        r"format|formatier",
        r"import.*sort|sortier.*import|sort.*import",
        r"type.?hint|typ.*annotation",
        r"lint|linting",
        r"prettify|verschöner",
        r"indent|einrück",
        r"whitespace|leerzeichen",

        # Typos & Simple Fixes
        r"typo|tippfehler",
        r"spell|rechtschreib",
        r"korrektur|correct",
        r"fix.*typo|behebe.*tippfehler",
        r"rename|umbenennen",
        r"simple.*fix|einfache.*änderung",

        # Boilerplate & Templates
        r"boilerplate",
        r"template.*ausfüll",
        r"scaffold",
        r"stub|platzhalter",
        r"skeleton|gerüst",

        # Simple Tasks
        r"validier.*einfach",
        r"regex.*transformation",
        r"einfache.*regel",
        r"mechanisch",
        r"trivial",
        r"simple|simpel",
        r"quick.*fix|schnelle.*änderung",
        r"minor.*change|kleine.*änderung",

        # Batch simple operations
        r"alle.*dateien.*format",
        r"alle.*dateien.*sort",
        r"update.*version",
        r"bump.*version",
        r"update.*copyright",
        r"update.*year|jahr.*aktualisier",

        # Comments & Docs (simple)
        r"add.*comment|kommentar.*hinzufüg",
        r"remove.*comment|kommentar.*entfern",
        r"update.*readme",
        r"fix.*link|link.*korrigier",
    ]

    # Kritische Dateipfade - IMMER Opus
    CRITICAL_PATHS = [
        "app/core/",
        "app/security/",
        "app/agents/ocr/",
        "alembic/versions/",
        ".claude/hooks/",
        "app/auth/",
        "app/permissions/",
    ]

    # GPU-relevante Pfade - IMMER Opus
    GPU_PATHS = [
        "app/agents/ocr/deepseek",
        "app/agents/ocr/got_ocr",
        "app/agents/ocr/surya",
        "app/gpu/",
        "Skills/ocr/",
    ]

    def classify(
        self,
        task_description: str,
        affected_files: List[str] = None
    ) -> ClassificationResult:
        """
        Klassifiziert eine Aufgabe für das passende Modell.

        Args:
            task_description: Beschreibung der Aufgabe
            affected_files: Liste der betroffenen Dateien

        Returns:
            ClassificationResult mit Modell-Empfehlung
        """

        task_lower = task_description.lower()
        affected_files = affected_files or []

        # 1. Check kritische Pfade zuerst
        for path in self.CRITICAL_PATHS:
            if any(path in f for f in affected_files):
                return ClassificationResult(
                    tier=ModelTier.OPUS_REQUIRED,
                    confidence=1.0,
                    reasoning=f"Kritischer Pfad betroffen: {path}"
                )

        # 2. Check GPU-Pfade
        for path in self.GPU_PATHS:
            if any(path in f for f in affected_files):
                return ClassificationResult(
                    tier=ModelTier.OPUS_REQUIRED,
                    confidence=1.0,
                    reasoning=f"GPU-kritischer Pfad betroffen: {path}"
                )

        # 3. Check Multi-File Operations
        if len(affected_files) > 5:
            return ClassificationResult(
                tier=ModelTier.OPUS_REQUIRED,
                confidence=0.9,
                reasoning=f"Multi-File Operation ({len(affected_files)} Dateien)"
            )

        # 4. Pattern Matching
        opus_score = self._match_patterns(task_lower, self.OPUS_PATTERNS)
        sonnet_score = self._match_patterns(task_lower, self.SONNET_PATTERNS)
        haiku_score = self._match_patterns(task_lower, self.HAIKU_PATTERNS)

        # 5. Entscheidungslogik
        if opus_score > 0:
            return ClassificationResult(
                tier=ModelTier.OPUS_REQUIRED,
                confidence=min(0.7 + opus_score * 0.1, 1.0),
                reasoning=f"Opus-Pattern erkannt (Score: {opus_score})"
            )

        if haiku_score > sonnet_score and haiku_score > 0:
            return ClassificationResult(
                tier=ModelTier.HAIKU_SUFFICIENT,
                confidence=min(0.6 + haiku_score * 0.1, 0.95),
                reasoning=f"Einfache Aufgabe erkannt (Score: {haiku_score})",
                fallback_tier=ModelTier.SONNET_CAPABLE
            )

        if sonnet_score > 0:
            return ClassificationResult(
                tier=ModelTier.SONNET_CAPABLE,
                confidence=min(0.6 + sonnet_score * 0.1, 0.95),
                reasoning=f"Implementierungs-Aufgabe erkannt (Score: {sonnet_score})",
                fallback_tier=ModelTier.OPUS_REQUIRED
            )

        # 6. Default: Bei Unsicherheit → Opus
        return ClassificationResult(
            tier=ModelTier.OPUS_REQUIRED,
            confidence=0.5,
            reasoning="Keine klare Klassifizierung möglich, eskaliere zu Opus"
        )

    def _match_patterns(self, text: str, patterns: List[str]) -> int:
        """
        Zählt Pattern-Matches in Text.

        Args:
            text: Text zum Durchsuchen
            patterns: Liste von Regex-Patterns

        Returns:
            Anzahl der gefundenen Patterns
        """
        return sum(1 for pattern in patterns if re.search(pattern, text, re.IGNORECASE))

    def get_classification_explanation(self, result: ClassificationResult) -> str:
        """
        Gibt eine detaillierte Erklärung der Klassifizierung zurück.

        Args:
            result: ClassificationResult

        Returns:
            Formatierte Erklärung
        """
        explanation = f"""
🤖 Model-Routing Empfehlung:

Empfohlenes Modell: {result.tier.value.upper()}
Confidence: {result.confidence:.0%}
Begründung: {result.reasoning}
"""

        if result.fallback_tier:
            explanation += f"Fallback bei Eskalation: {result.fallback_tier.value.upper()}\n"

        return explanation.strip()

    @staticmethod
    def get_agent_name(tier: ModelTier) -> str:
        """
        Get agent name for given tier.

        Args:
            tier: The model tier

        Returns:
            Agent name for Claude Code Task() calls
        """
        return TIER_TO_AGENT[tier]
