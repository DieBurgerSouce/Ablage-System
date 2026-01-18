# -*- coding: utf-8 -*-
"""
Collaboration Services Package.

Services fuer Team-Zusammenarbeit an Dokumenten:
- CommentService: Dokument-Kommentare, @Mentions, Reaktionen
- DocumentTaskService: Aufgaben-Zuweisung und -Verwaltung
- DigestService: Email-Zusammenfassungen
- EscalationService: Automatische Eskalation
- SmartEscalationService: KI-gestuetzte intelligente Zuweisung (Phase 2.3)

Feinpoliert und durchdacht - Collaboration-Suite.
"""

from app.services.collaboration.comment_service import CommentService, get_comment_service
from app.services.collaboration.document_task_service import DocumentTaskService
from app.services.collaboration.digest_service import DigestService, get_digest_service
from app.services.collaboration.escalation_service import EscalationService, get_escalation_service
from app.services.collaboration.smart_escalation_service import (
    SmartEscalationService,
    get_smart_escalation_service,
    AssignmentRecommendation,
    CandidateScore,
    FactorWeights,
    AssignmentFactor,
)

__all__ = [
    "CommentService",
    "get_comment_service",
    "DocumentTaskService",
    "DigestService",
    "get_digest_service",
    "EscalationService",
    "get_escalation_service",
    "SmartEscalationService",
    "get_smart_escalation_service",
    "AssignmentRecommendation",
    "CandidateScore",
    "FactorWeights",
    "AssignmentFactor",
]
