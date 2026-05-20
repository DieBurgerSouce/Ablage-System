# -*- coding: utf-8 -*-
"""
Autonomy Level System.

Enterprise Feature: Autonomie-Framework für Zero-Touch Operations.

Levels:
- CONSERVATIVE: Immer Bestätigung erforderlich
- SMART_HYBRID: 95%+ Confidence = Auto-Ausführung
- PROGRESSIVE: Routine-Aufgaben autonom
- ZERO_TOUCH: Alles automatisch
"""

from enum import IntEnum
from typing import TypedDict


class AutonomyLevel(IntEnum):
    """
    Autonomie-Level für KI-gesteuerte Aktionen.

    Die Level bestimmen, wie viel menschliche Bestätigung
    für verschiedene Aktionstypen erforderlich ist.
    """

    CONSERVATIVE = 1   # Immer Bestätigung
    SMART_HYBRID = 2   # 95%+ Confidence = Auto
    PROGRESSIVE = 3    # Routine = Auto
    ZERO_TOUCH = 4     # Alles Auto

    @property
    def description(self) -> str:
        """Deutsche Beschreibung des Levels."""
        descriptions = {
            AutonomyLevel.CONSERVATIVE: "Konservativ - Immer menschliche Bestätigung",
            AutonomyLevel.SMART_HYBRID: "Smart Hybrid - Automatisch bei 95%+ Confidence",
            AutonomyLevel.PROGRESSIVE: "Progressiv - Routine-Aufgaben automatisch",
            AutonomyLevel.ZERO_TOUCH: "Zero-Touch - Vollautomatisch",
        }
        return descriptions.get(self, "Unbekanntes Level")

    @property
    def confidence_threshold(self) -> float:
        """Confidence-Schwellenwert für automatische Ausführung."""
        thresholds = {
            AutonomyLevel.CONSERVATIVE: 1.01,  # Nie automatisch (>100%)
            AutonomyLevel.SMART_HYBRID: 0.95,
            AutonomyLevel.PROGRESSIVE: 0.85,
            AutonomyLevel.ZERO_TOUCH: 0.70,
        }
        return thresholds.get(self, 1.01)

    @property
    def auto_approve_routine(self) -> bool:
        """Ob Routine-Aufgaben automatisch genehmigt werden."""
        return self >= AutonomyLevel.PROGRESSIVE

    @property
    def requires_human_review_always(self) -> bool:
        """Ob immer menschliche Überprüfung erforderlich ist."""
        return self == AutonomyLevel.CONSERVATIVE


class ActionCategory(IntEnum):
    """
    Kategorisierung von Aktionen nach Risiko und Reversibilität.

    Bestimmt zusammen mit dem Autonomy Level, ob eine Aktion
    automatisch ausgeführt werden kann.
    """

    # Niedrig-Risiko, reversibel
    ROUTINE = 1          # Tagging, Kategorisierung
    READ_ONLY = 2        # Berichte, Analysen

    # Mittel-Risiko, teilweise reversibel
    MODIFICATION = 3     # Dokument-Metadaten ändern
    NOTIFICATION = 4     # Benachrichtigungen senden

    # Hoch-Risiko, schwer reversibel
    FINANCIAL = 5        # Zahlungen, Buchungen
    DELETION = 6         # Löschen von Daten
    EXTERNAL = 7         # Externe API-Aufrufe

    # Kritisch, nicht reversibel
    LEGAL = 8            # Rechtlich bindende Aktionen
    COMPLIANCE = 9       # Compliance-relevante Aktionen

    @property
    def risk_level(self) -> str:
        """Risiko-Level als Text."""
        if self <= ActionCategory.READ_ONLY:
            return "niedrig"
        elif self <= ActionCategory.NOTIFICATION:
            return "mittel"
        elif self <= ActionCategory.EXTERNAL:
            return "hoch"
        else:
            return "kritisch"

    @property
    def min_confidence_boost(self) -> float:
        """
        Zusätzliche Confidence-Anforderung basierend auf Risiko.

        Kritische Aktionen erfordern höhere Confidence.
        """
        boosts = {
            ActionCategory.ROUTINE: 0.0,
            ActionCategory.READ_ONLY: 0.0,
            ActionCategory.MODIFICATION: 0.02,
            ActionCategory.NOTIFICATION: 0.02,
            ActionCategory.FINANCIAL: 0.05,
            ActionCategory.DELETION: 0.05,
            ActionCategory.EXTERNAL: 0.03,
            ActionCategory.LEGAL: 0.10,
            ActionCategory.COMPLIANCE: 0.10,
        }
        return boosts.get(self, 0.0)

    @property
    def requires_explicit_approval(self) -> bool:
        """
        Ob diese Kategorie immer explizite Genehmigung erfordert.

        Kritische Kategorien können nie vollautomatisch sein.
        """
        return self >= ActionCategory.LEGAL


class AutonomyDecision(TypedDict):
    """Ergebnis einer Autonomie-Entscheidung."""

    can_auto_execute: bool
    reason: str
    required_confidence: float
    actual_confidence: float
    action_category: str
    autonomy_level: int
    requires_human_review: bool
    suggested_reviewers: list[str]


def can_auto_execute(
    autonomy_level: AutonomyLevel,
    action_category: ActionCategory,
    confidence: float,
) -> AutonomyDecision:
    """
    Entscheidet, ob eine Aktion automatisch ausgeführt werden kann.

    Args:
        autonomy_level: Aktuelles Autonomie-Level des Tenants
        action_category: Kategorie der geplanten Aktion
        confidence: Confidence-Score der KI (0.0 - 1.0)

    Returns:
        AutonomyDecision mit Begründung
    """
    # Kritische Aktionen erfordern immer Genehmigung
    if action_category.requires_explicit_approval:
        return AutonomyDecision(
            can_auto_execute=False,
            reason=f"Kategorie '{action_category.name}' erfordert immer explizite Genehmigung",
            required_confidence=1.01,
            actual_confidence=confidence,
            action_category=action_category.name,
            autonomy_level=autonomy_level,
            requires_human_review=True,
            suggested_reviewers=["admin", "compliance"],
        )

    # Conservative Level: Immer menschliche Überprüfung
    if autonomy_level.requires_human_review_always:
        return AutonomyDecision(
            can_auto_execute=False,
            reason="Konservatives Autonomie-Level: Alle Aktionen erfordern Bestätigung",
            required_confidence=1.01,
            actual_confidence=confidence,
            action_category=action_category.name,
            autonomy_level=autonomy_level,
            requires_human_review=True,
            suggested_reviewers=[],
        )

    # Berechne erforderliche Confidence
    base_threshold = autonomy_level.confidence_threshold
    risk_boost = action_category.min_confidence_boost
    required_confidence = min(base_threshold + risk_boost, 1.0)

    # Routine-Aufgaben bei Progressive+ Level
    if (
        autonomy_level.auto_approve_routine
        and action_category <= ActionCategory.READ_ONLY
    ):
        return AutonomyDecision(
            can_auto_execute=True,
            reason="Routine-Aufgabe bei progressivem Level automatisch genehmigt",
            required_confidence=required_confidence,
            actual_confidence=confidence,
            action_category=action_category.name,
            autonomy_level=autonomy_level,
            requires_human_review=False,
            suggested_reviewers=[],
        )

    # Confidence-Check
    if confidence >= required_confidence:
        return AutonomyDecision(
            can_auto_execute=True,
            reason=f"Confidence ({confidence:.1%}) >= Schwellenwert ({required_confidence:.1%})",
            required_confidence=required_confidence,
            actual_confidence=confidence,
            action_category=action_category.name,
            autonomy_level=autonomy_level,
            requires_human_review=False,
            suggested_reviewers=[],
        )

    # Confidence zu niedrig
    return AutonomyDecision(
        can_auto_execute=False,
        reason=f"Confidence ({confidence:.1%}) < Schwellenwert ({required_confidence:.1%})",
        required_confidence=required_confidence,
        actual_confidence=confidence,
        action_category=action_category.name,
        autonomy_level=autonomy_level,
        requires_human_review=True,
        suggested_reviewers=[],
    )
