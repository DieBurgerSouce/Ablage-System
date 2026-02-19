# -*- coding: utf-8 -*-
"""
Matching-Services für Ablage-System.

Enthält:
    - ThreeWayMatchingService: 3-Way Matching zwischen Bestellung, Lieferschein und Rechnung
    - ThreeWayMatchResult: Ergebnis-DTO eines Match-Versuchs
    - MatchCandidate: DTO für einen potentiellen Match-Partner
    - DiscrepancyInfo: DTO für eine erkannte Abweichung
"""

from app.services.matching.three_way_matching_service import (
    ThreeWayMatchingService,
    ThreeWayMatchResult,
    MatchCandidate,
    DiscrepancyInfo,
)

__all__ = [
    "ThreeWayMatchingService",
    "ThreeWayMatchResult",
    "MatchCandidate",
    "DiscrepancyInfo",
]
