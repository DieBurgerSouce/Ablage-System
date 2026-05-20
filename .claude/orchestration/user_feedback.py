#!/usr/bin/env python3
"""
User Feedback Display für Multi-Model Orchestration.

Zeigt Orchestrierungs-Entscheidungen für User an mit:
- Modell-Auswahl (Opus/Sonnet/Haiku)
- Confidence Score
- Begründung
- Qualitätsscore
- Token-Einsparungen vs Opus-only

Deutsche Sprache für alle User-Facing Messages!
"""

import sys
from enum import Enum
from typing import Optional
from dataclasses import dataclass


class DisplayMode(Enum):
    """Anzeigemodus für Feedback."""
    MINIMAL = "minimal"  # Nur Modell + Savings
    STANDARD = "standard"  # Modell + Confidence + Savings
    DETAILED = "detailed"  # Alle Informationen


@dataclass
class OrchestrationFeedback:
    """Orchestrierungs-Feedback für User."""

    model: str  # "opus", "sonnet", "haiku"
    confidence: float  # 0.0 - 1.0
    reasoning: str  # Begründung für Modell-Wahl
    quality_score: Optional[float] = None  # Nach Task-Completion
    escalated_from: Optional[str] = None  # Bei Eskalation
    cache_hit: bool = False  # Opus-Decision aus Cache
    files_affected: int = 0
    estimated_tokens: int = 0


class UserFeedback:
    """Anzeige von Orchestrierungs-Entscheidungen für User."""

    # Modell-Icons für visuelle Unterscheidung
    MODEL_ICONS = {
        "opus": "🧠",  # Brain - höchste Intelligenz
        "sonnet": "⚙️",  # Gear - Standard-Arbeitspferd
        "haiku": "✨"   # Sparkle - schnell und effizient
    }

    # Token-Kosten relativ zu Opus (1.0 = Opus baseline)
    TOKEN_COSTS = {
        "opus": 1.0,
        "sonnet": 0.2,  # 80% günstiger
        "haiku": 0.05   # 95% günstiger
    }

    def __init__(self, mode: DisplayMode = DisplayMode.DETAILED):
        """
        Initialize user feedback display.

        Args:
            mode: Anzeigemodus (minimal, standard, detailed)
        """
        self.mode = mode

    def show_routing_decision(
        self,
        model: str,
        confidence: float,
        reasoning: str,
        files: int = 0,
        estimated_tokens: int = 0,
        cache_hit: bool = False
    ) -> None:
        """
        Zeigt Routing-Entscheidung vor Task-Ausführung.

        Args:
            model: Gewähltes Modell (opus/sonnet/haiku)
            confidence: Confidence Score (0.0 - 1.0)
            reasoning: Begründung für Modell-Wahl
            files: Anzahl betroffener Dateien
            estimated_tokens: Geschätzte Token-Anzahl
            cache_hit: Wurde Opus-Decision aus Cache verwendet?
        """
        feedback = OrchestrationFeedback(
            model=model,
            confidence=confidence,
            reasoning=reasoning,
            files_affected=files,
            estimated_tokens=estimated_tokens,
            cache_hit=cache_hit
        )

        self._display_routing(feedback)

    def show_quality_result(
        self,
        model: str,
        quality_score: float,
        escalated_from: Optional[str] = None
    ) -> None:
        """
        Zeigt Quality-Gate Ergebnis nach Task-Completion.

        Args:
            model: Verwendetes Modell
            quality_score: Qualitätsscore (0.0 - 1.0)
            escalated_from: Falls eskaliert, von welchem Modell
        """
        feedback = OrchestrationFeedback(
            model=model,
            confidence=1.0,  # Quality ist final
            reasoning="Task abgeschlossen",
            quality_score=quality_score,
            escalated_from=escalated_from
        )

        self._display_quality(feedback)

    def show_escalation(
        self,
        from_model: str,
        to_model: str,
        reason: str,
        quality_score: float
    ) -> None:
        """
        Zeigt Eskalation zu höherem Modell.

        Args:
            from_model: Ursprüngliches Modell
            to_model: Ziel-Modell
            reason: Grund für Eskalation
            quality_score: Quality Score der fehlgeschlagen
        """
        print(f"\n⬆️  Quality Gate: Eskalation erforderlich", file=sys.stderr)
        print(f"   Von: {self._format_model(from_model)}", file=sys.stderr)
        print(f"   Zu: {self._format_model(to_model)}", file=sys.stderr)
        print(f"   Grund: {reason}", file=sys.stderr)
        print(f"   Quality Score: {quality_score:.2f} / 1.00", file=sys.stderr)

    def _display_routing(self, feedback: OrchestrationFeedback) -> None:
        """
        Zeigt Routing-Entscheidung basierend auf Anzeigemodus.

        Args:
            feedback: Orchestrierungs-Feedback
        """
        if self.mode == DisplayMode.MINIMAL:
            # Kompakte Anzeige: Icon + Modell + Savings
            savings = self._calculate_savings(feedback.model)
            print(
                f"\n{self.MODEL_ICONS[feedback.model]} {feedback.model.upper()} "
                f"(💰 {savings}% vs Opus)",
                file=sys.stderr
            )

        elif self.mode == DisplayMode.STANDARD:
            # Standard: Icon + Modell + Confidence + Savings
            savings = self._calculate_savings(feedback.model)
            print(f"\n⚙️ Multi-Model Orchestration:", file=sys.stderr)
            print(
                f"   Modell: {self._format_model(feedback.model)}",
                file=sys.stderr
            )
            print(f"   Confidence: {feedback.confidence:.0%}", file=sys.stderr)
            print(f"   💰 Token-Einsparung: ~{savings}% vs Opus", file=sys.stderr)

        else:  # DisplayMode.DETAILED
            # Detailliert: Alle Informationen
            savings = self._calculate_savings(feedback.model)

            print(f"\n⚙️ Multi-Model Orchestration:", file=sys.stderr)
            print(
                f"   Modell: {self._format_model(feedback.model)}",
                file=sys.stderr
            )
            print(f"   Confidence: {feedback.confidence:.0%}", file=sys.stderr)
            print(f"   Begründung: {feedback.reasoning}", file=sys.stderr)

            if feedback.files_affected > 0:
                print(
                    f"   Betroffene Dateien: {feedback.files_affected}",
                    file=sys.stderr
                )

            if feedback.estimated_tokens > 0:
                print(
                    f"   Geschätzte Tokens: {feedback.estimated_tokens:,}",
                    file=sys.stderr
                )

            if feedback.cache_hit:
                print(f"   ♻️  Cache-Hit: Opus-Decision wiederverwendet", file=sys.stderr)

            print(f"   💰 Token-Einsparung: ~{savings}% vs Opus", file=sys.stderr)

    def _display_quality(self, feedback: OrchestrationFeedback) -> None:
        """
        Zeigt Quality-Gate Ergebnis.

        Args:
            feedback: Orchestrierungs-Feedback mit Quality Score
        """
        if feedback.quality_score is None:
            return

        # Emoji basierend auf Quality Score
        if feedback.quality_score >= 0.95:
            status_emoji = "✅"
            status_text = "Exzellent"
        elif feedback.quality_score >= 0.85:
            status_emoji = "✅"
            status_text = "Gut"
        elif feedback.quality_score >= 0.70:
            status_emoji = "⚠️"
            status_text = "Akzeptabel"
        else:
            status_emoji = "❌"
            status_text = "Unzureichend"

        print(f"\n{status_emoji} Quality Gate: {status_text}", file=sys.stderr)
        print(
            f"   Quality Score: {feedback.quality_score:.2f} / 1.00",
            file=sys.stderr
        )

        if feedback.escalated_from:
            print(
                f"   ⬆️  Eskaliert von {feedback.escalated_from.upper()}",
                file=sys.stderr
            )

    def _format_model(self, model: str) -> str:
        """
        Formatiert Modell-Name mit Icon.

        Args:
            model: Modell-Name (opus/sonnet/haiku)

        Returns:
            Formatierter String mit Icon
        """
        icon = self.MODEL_ICONS.get(model, "🤖")
        return f"{icon} {model.upper()}"

    def _calculate_savings(self, model: str) -> int:
        """
        Berechnet Token-Einsparung vs Opus in Prozent.

        Args:
            model: Verwendetes Modell (opus/sonnet/haiku)

        Returns:
            Einsparung in Prozent (0-100)
        """
        if model not in self.TOKEN_COSTS:
            return 0

        cost_ratio = self.TOKEN_COSTS[model]
        savings = int((1.0 - cost_ratio) * 100)
        return savings


def create_feedback_display(mode: str = "detailed") -> UserFeedback:
    """
    Factory-Funktion für UserFeedback.

    Args:
        mode: Anzeigemodus (minimal, standard, detailed)

    Returns:
        UserFeedback-Instanz
    """
    try:
        display_mode = DisplayMode(mode)
    except ValueError:
        # Fallback zu detailed bei ungültigem Mode
        display_mode = DisplayMode.DETAILED

    return UserFeedback(mode=display_mode)


# Beispiel-Nutzung für Testing
if __name__ == "__main__":
    # Test verschiedene Anzeigemodi
    print("=== MINIMAL MODE ===")
    feedback_minimal = UserFeedback(mode=DisplayMode.MINIMAL)
    feedback_minimal.show_routing_decision(
        model="sonnet",
        confidence=0.87,
        reasoning="Feature implementation with tests",
        files=5,
        estimated_tokens=12000
    )

    print("\n=== STANDARD MODE ===")
    feedback_standard = UserFeedback(mode=DisplayMode.STANDARD)
    feedback_standard.show_routing_decision(
        model="sonnet",
        confidence=0.87,
        reasoning="Feature implementation with tests",
        files=5,
        estimated_tokens=12000
    )

    print("\n=== DETAILED MODE ===")
    feedback_detailed = UserFeedback(mode=DisplayMode.DETAILED)
    feedback_detailed.show_routing_decision(
        model="sonnet",
        confidence=0.87,
        reasoning="Feature implementation with tests",
        files=5,
        estimated_tokens=12000,
        cache_hit=True
    )

    print("\n=== QUALITY RESULT ===")
    feedback_detailed.show_quality_result(
        model="sonnet",
        quality_score=0.92
    )

    print("\n=== ESCALATION ===")
    feedback_detailed.show_escalation(
        from_model="haiku",
        to_model="sonnet",
        reason="Quality Score unter 0.95",
        quality_score=0.82
    )

    print("\n=== HAIKU (MINIMAL) ===")
    feedback_minimal.show_routing_decision(
        model="haiku",
        confidence=0.95,
        reasoning="Simple formatting task"
    )

    print("\n=== OPUS (DETAILED) ===")
    feedback_detailed.show_routing_decision(
        model="opus",
        confidence=1.0,
        reasoning="Kritischer Security-Code",
        files=12,
        estimated_tokens=25000
    )
