# -*- coding: utf-8 -*-
"""
Proaktive Aktions-Prioritäts-Engine.

Berechnet Prioritäts-Scores für Aufgaben im täglichen Action-Queue.

Formel: score = deadline_proximity * financial_impact * urgency_factor

- deadline_proximity: Nähe zur Frist (0-1, höher = näher an Frist)
- financial_impact:   Monetärer Einfluss (normalisiert 0-1)
- urgency_factor:     Basiert auf Aufgabentyp

Feinpoliert und durchdacht - Enterprise-grade Priority Engine.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# ACTION TYPES & URGENCY FACTORS
# =============================================================================


class ProactiveActionType(str, Enum):
    """Typen proaktiver Aufgaben."""

    OVERDUE_INVOICE = "overdue_invoice"          # Fällige Rechnung
    PENDING_APPROVAL = "pending_approval"        # Offene Genehmigung
    SKONTO_DEADLINE = "skonto_deadline"          # Skonto-Frist läuft ab
    UNCATEGORIZED_DOC = "uncategorized_doc"      # Unkategorisiertes Dokument
    ANOMALY = "anomaly"                          # Erkannte Anomalie
    CONTRACT_EXPIRY = "contract_expiry"          # Vertragsfrist-Warnung


# Dringlichkeitsfaktoren pro Aufgabentyp (0.0 - 1.0)
URGENCY_FACTORS: dict = {
    ProactiveActionType.OVERDUE_INVOICE: 0.95,
    ProactiveActionType.PENDING_APPROVAL: 0.90,
    ProactiveActionType.SKONTO_DEADLINE: 0.85,
    ProactiveActionType.ANOMALY: 0.75,
    ProactiveActionType.CONTRACT_EXPIRY: 0.70,
    ProactiveActionType.UNCATEGORIZED_DOC: 0.30,
}

# Referenzwerte für finanzielle Normalisierung (EUR)
_FINANCIAL_REFERENCE_AMOUNTS: list = [
    100.0,       # Kleiner Betrag
    1_000.0,     # Mittlerer Betrag
    10_000.0,    # Größerer Betrag
    100_000.0,   # Hoher Betrag (100%)
]
_MAX_FINANCIAL_REFERENCE = 100_000.0

# Maximale Fristen-Horizonte in Tagen pro Aufgabentyp
# (darüber hinaus = 0 deadline_proximity)
_DEADLINE_HORIZONS_DAYS: dict = {
    ProactiveActionType.OVERDUE_INVOICE: 90,
    ProactiveActionType.PENDING_APPROVAL: 7,
    ProactiveActionType.SKONTO_DEADLINE: 14,
    ProactiveActionType.ANOMALY: 30,
    ProactiveActionType.CONTRACT_EXPIRY: 90,
    ProactiveActionType.UNCATEGORIZED_DOC: 30,
}


# =============================================================================
# PRIORITY ENGINE
# =============================================================================


class ActionPriorityEngine:
    """
    Berechnet Prioritäts-Scores für proaktive Aufgaben.

    Formel: score = deadline_proximity * financial_impact * urgency_factor

    Alle Faktoren sind im Bereich [0.0, 1.0].
    Score-Ergebnis liegt ebenfalls in [0.0, 1.0].
    Höherer Score = höhere Priorität.
    """

    def calculate_score(
        self,
        action_type: ProactiveActionType,
        deadline: Optional[datetime] = None,
        financial_amount: Optional[float] = None,
    ) -> float:
        """
        Berechnet den Prioritäts-Score für eine Aufgabe.

        Args:
            action_type:      Typ der proaktiven Aufgabe
            deadline:         Optionale Frist (timezone-aware UTC)
            financial_amount: Optionaler Geldbetrag in EUR

        Returns:
            Prioritäts-Score [0.0, 1.0]
        """
        urgency = self._urgency_factor(action_type)
        proximity = self._deadline_proximity(action_type, deadline)
        impact = self._financial_impact(financial_amount)

        score = urgency * proximity * impact

        logger.debug(
            "priority_score_calculated",
            action_type=action_type.value,
            urgency=urgency,
            proximity=proximity,
            impact=impact,
            score=score,
        )

        return round(min(1.0, max(0.0, score)), 4)

    def _urgency_factor(self, action_type: ProactiveActionType) -> float:
        """
        Gibt den Dringlichkeitsfaktor für einen Aufgabentyp zurück.

        Args:
            action_type: Aufgabentyp

        Returns:
            Dringlichkeitsfaktor [0.0, 1.0]
        """
        return URGENCY_FACTORS.get(action_type, 0.50)

    def _deadline_proximity(
        self,
        action_type: ProactiveActionType,
        deadline: Optional[datetime],
    ) -> float:
        """
        Berechnet die Nähe zur Frist als normalisierten Wert.

        Überfällige Aufgaben erhalten den Maximalwert 1.0.
        Aufgaben ohne Frist erhalten einen mittleren Wert 0.5.

        Args:
            action_type: Aufgabentyp (für Horizont-Referenz)
            deadline:    Optionale Frist (timezone-aware UTC)

        Returns:
            Fristen-Nähe [0.0, 1.0]
        """
        if deadline is None:
            return 0.50

        now = datetime.now(tz=timezone.utc)

        # Sicherstellen dass deadline timezone-aware ist
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)

        days_remaining = (deadline - now).total_seconds() / 86400.0

        # Überfällig: maximale Priorität
        if days_remaining <= 0:
            return 1.0

        horizon = float(_DEADLINE_HORIZONS_DAYS.get(action_type, 30))

        # Jenseits des Horizonts: keine Priorität
        if days_remaining >= horizon:
            return 0.0

        # Lineare Interpolation: näher = höher
        # Bei 0 Tagen -> 1.0, bei horizon Tagen -> 0.0
        proximity = 1.0 - (days_remaining / horizon)
        return round(max(0.0, min(1.0, proximity)), 4)

    def _financial_impact(self, amount: Optional[float]) -> float:
        """
        Normalisiert einen Geldbetrag auf [0.0, 1.0].

        Verwendet logarithmische Skalierung für bessere Spreizung.
        Aufgaben ohne Geldbetrag erhalten 0.5 (neutraler Einfluss).

        Args:
            amount: Geldbetrag in EUR (darf None sein)

        Returns:
            Normalisierter Einfluss [0.0, 1.0]
        """
        if amount is None:
            return 0.50

        if amount <= 0.0:
            return 0.10

        # Logarithmische Normalisierung
        import math
        log_amount = math.log10(max(1.0, amount))
        log_max = math.log10(_MAX_FINANCIAL_REFERENCE)
        impact = log_amount / log_max
        return round(max(0.0, min(1.0, impact)), 4)

    def rank_actions(self, actions: list) -> list:
        """
        Sortiert eine Liste von Aufgaben nach Prioritäts-Score (absteigend).

        Erwartet, dass jedes Element ein 'priority_score'-Attribut hat.

        Args:
            actions: Liste von Aufgaben-Objekten oder Dicts mit 'priority_score'

        Returns:
            Sortierte Liste (höchste Priorität zuerst)
        """
        def _get_score(item: object) -> float:
            if isinstance(item, dict):
                return float(item.get("priority_score", 0.0))
            return float(getattr(item, "priority_score", 0.0))

        return sorted(actions, key=_get_score, reverse=True)


# =============================================================================
# SINGLETON
# =============================================================================


_priority_engine: Optional[ActionPriorityEngine] = None


def get_priority_engine() -> ActionPriorityEngine:
    """Gibt die Singleton-Instanz der ActionPriorityEngine zurück."""
    global _priority_engine
    if _priority_engine is None:
        _priority_engine = ActionPriorityEngine()
    return _priority_engine
