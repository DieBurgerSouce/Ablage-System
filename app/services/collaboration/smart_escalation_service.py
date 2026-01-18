# -*- coding: utf-8 -*-
"""
Smart Escalation Service for Ablage-System.

KI-gestuetzte intelligente Eskalation:
- Expertise-Score (Dokumenttyp-Historie)
- Workload-Score (offene Validation-Queue Items)
- Verfuegbarkeits-Score (Urlaub, Abwesenheit)
- Relationship-Score (vorherige Bearbeitung desselben Kunden)

Phase 2.3 der Feature-Roadmap (Januar 2026)
Feinpoliert und durchdacht - Intelligente Zuweisung auf Enterprise-Niveau.
"""

import structlog
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID
from enum import Enum

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.datetime_utils import utc_now
from app.db.models import (
    BusinessEntity,
    Company,
    Document,
    DocumentTask,
    TaskStatus,
    User,
    UserCompany,
    ValidationQueueItem,
    ValidationStatus,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums and Configuration
# =============================================================================


class AssignmentFactor(str, Enum):
    """Faktoren fuer intelligente Zuweisung."""
    EXPERTISE = "expertise"
    WORKLOAD = "workload"
    AVAILABILITY = "availability"
    RELATIONSHIP = "relationship"


class UnavailabilityReason(str, Enum):
    """Gruende fuer Nichtverfuegbarkeit."""
    VACATION = "vacation"
    SICK_LEAVE = "sick_leave"
    TRAINING = "training"
    OUT_OF_OFFICE = "out_of_office"
    OFFLINE = "offline"


@dataclass
class FactorWeights:
    """Gewichtung der Faktoren fuer Score-Berechnung."""
    expertise: float = 0.35      # 35% - Expertise ist am wichtigsten
    workload: float = 0.25       # 25% - Auslastung
    availability: float = 0.25   # 25% - Verfuegbarkeit
    relationship: float = 0.15   # 15% - Beziehung zum Kunden

    def validate(self) -> bool:
        """Validiert dass Gewichte 100% ergeben."""
        total = self.expertise + self.workload + self.availability + self.relationship
        return abs(total - 1.0) < 0.01


@dataclass
class CandidateScore:
    """Score eines Kandidaten fuer Aufgabenzuweisung."""
    user_id: UUID
    user_email: str
    user_name: str

    # Einzel-Scores (0-100)
    expertise_score: float = 0.0
    workload_score: float = 0.0
    availability_score: float = 0.0
    relationship_score: float = 0.0

    # Gewichteter Gesamtscore
    total_score: float = 0.0

    # Details fuer Erklaerbarkeit
    expertise_details: Dict[str, Any] = field(default_factory=dict)
    workload_details: Dict[str, Any] = field(default_factory=dict)
    availability_details: Dict[str, Any] = field(default_factory=dict)
    relationship_details: Dict[str, Any] = field(default_factory=dict)

    # Verfuegbarkeitsstatus
    is_available: bool = True
    unavailability_reason: Optional[str] = None


@dataclass
class AssignmentRecommendation:
    """Empfehlung fuer Aufgabenzuweisung."""
    recommended_user_id: UUID
    recommended_user_name: str
    confidence: float  # 0-100

    # Alle bewerteten Kandidaten
    candidates: List[CandidateScore]

    # Faktoren-Breakdown
    factors_used: List[AssignmentFactor]
    weights_used: FactorWeights

    # Erklaerung
    explanation: str
    explanation_details: Dict[str, Any]


# =============================================================================
# Smart Escalation Service
# =============================================================================


class SmartEscalationService:
    """Service fuer KI-gestuetzte intelligente Aufgabenzuweisung."""

    # Standardkonfiguration
    DEFAULT_WEIGHTS = FactorWeights()

    # Thresholds
    MIN_EXPERTISE_TASKS = 3       # Mindestanzahl fuer Expertise-Bewertung
    MAX_WORKLOAD_ITEMS = 20       # Max Items bevor Workload-Score = 0
    RECENT_DAYS_EXPERTISE = 90    # Tage fuer Expertise-Berechnung
    RECENT_DAYS_RELATIONSHIP = 180  # Tage fuer Relationship-Berechnung

    def __init__(self, db: AsyncSession):
        """Initialisiert den SmartEscalationService.

        Args:
            db: AsyncSession fuer Datenbankoperationen
        """
        self.db = db

    # =========================================================================
    # Main API
    # =========================================================================

    async def get_assignment_recommendation(
        self,
        company_id: UUID,
        document_id: Optional[UUID] = None,
        document_type: Optional[str] = None,
        entity_id: Optional[UUID] = None,
        task_type: Optional[str] = None,
        exclude_user_ids: Optional[List[UUID]] = None,
        weights: Optional[FactorWeights] = None,
        max_candidates: int = 10,
    ) -> Optional[AssignmentRecommendation]:
        """Ermittelt die beste Zuweisung fuer eine Aufgabe.

        SECURITY: company_id MUSS fuer Multi-Tenant Isolation uebergeben werden.

        Args:
            company_id: ID des Unternehmens (PFLICHT)
            document_id: ID des Dokuments (optional, fuer Kontext)
            document_type: Dokumenttyp (fuer Expertise-Matching)
            entity_id: ID des verknuepften Geschaeftspartners
            task_type: Typ der Aufgabe (validation, review, etc.)
            exclude_user_ids: User-IDs die ausgeschlossen werden sollen
            weights: Gewichtung der Faktoren (optional)
            max_candidates: Maximale Anzahl Kandidaten

        Returns:
            AssignmentRecommendation oder None wenn keine Kandidaten
        """
        weights = weights or self.DEFAULT_WEIGHTS
        exclude_user_ids = exclude_user_ids or []

        # 1. Hole alle aktiven Kandidaten der Company
        candidates = await self._get_eligible_candidates(
            company_id=company_id,
            exclude_user_ids=exclude_user_ids,
        )

        if not candidates:
            logger.warning(
                "smart_escalation_no_candidates",
                company_id=str(company_id),
            )
            return None

        # 2. Hole Dokumentkontext falls vorhanden
        doc_context = None
        if document_id:
            doc_context = await self._get_document_context(document_id, company_id)
            if doc_context and not document_type:
                document_type = doc_context.get("doc_type")
            if doc_context and not entity_id:
                entity_id = doc_context.get("entity_id")

        # 3. Berechne Scores fuer jeden Kandidaten
        scored_candidates: List[CandidateScore] = []

        for user in candidates:
            score = CandidateScore(
                user_id=user["id"],
                user_email=user["email"],
                user_name=user["full_name"] or user["email"],
            )

            # Expertise Score
            expertise_result = await self._calculate_expertise_score(
                user_id=user["id"],
                company_id=company_id,
                document_type=document_type,
                task_type=task_type,
            )
            score.expertise_score = expertise_result["score"]
            score.expertise_details = expertise_result["details"]

            # Workload Score
            workload_result = await self._calculate_workload_score(
                user_id=user["id"],
                company_id=company_id,
            )
            score.workload_score = workload_result["score"]
            score.workload_details = workload_result["details"]

            # Availability Score
            availability_result = await self._calculate_availability_score(
                user_id=user["id"],
            )
            score.availability_score = availability_result["score"]
            score.availability_details = availability_result["details"]
            score.is_available = availability_result["is_available"]
            score.unavailability_reason = availability_result.get("reason")

            # Relationship Score (nur wenn Entity vorhanden)
            if entity_id:
                relationship_result = await self._calculate_relationship_score(
                    user_id=user["id"],
                    entity_id=entity_id,
                    company_id=company_id,
                )
                score.relationship_score = relationship_result["score"]
                score.relationship_details = relationship_result["details"]
            else:
                # Neutral wenn keine Entity
                score.relationship_score = 50.0
                score.relationship_details = {"reason": "Keine Entity-Verknuepfung"}

            # Gewichteter Gesamtscore
            score.total_score = (
                score.expertise_score * weights.expertise +
                score.workload_score * weights.workload +
                score.availability_score * weights.availability +
                score.relationship_score * weights.relationship
            )

            scored_candidates.append(score)

        # 4. Sortiere nach Score (absteigend)
        scored_candidates.sort(key=lambda x: x.total_score, reverse=True)

        # 5. Beschraenke auf max_candidates
        scored_candidates = scored_candidates[:max_candidates]

        # 6. Erstelle Empfehlung
        if not scored_candidates:
            return None

        best_candidate = scored_candidates[0]

        # Confidence basierend auf Score-Differenz zum Zweitplatzierten
        confidence = self._calculate_recommendation_confidence(scored_candidates)

        # Erklaerung generieren
        explanation, explanation_details = self._generate_explanation(
            best_candidate=best_candidate,
            candidates=scored_candidates,
            weights=weights,
            document_type=document_type,
            entity_id=entity_id,
        )

        recommendation = AssignmentRecommendation(
            recommended_user_id=best_candidate.user_id,
            recommended_user_name=best_candidate.user_name,
            confidence=confidence,
            candidates=scored_candidates,
            factors_used=[
                AssignmentFactor.EXPERTISE,
                AssignmentFactor.WORKLOAD,
                AssignmentFactor.AVAILABILITY,
                AssignmentFactor.RELATIONSHIP,
            ],
            weights_used=weights,
            explanation=explanation,
            explanation_details=explanation_details,
        )

        logger.info(
            "smart_escalation_recommendation",
            company_id=str(company_id),
            recommended_user=str(best_candidate.user_id),
            confidence=confidence,
            total_candidates=len(scored_candidates),
            top_score=best_candidate.total_score,
        )

        return recommendation

    async def get_user_scores(
        self,
        user_id: UUID,
        company_id: UUID,
        document_type: Optional[str] = None,
        entity_id: Optional[UUID] = None,
    ) -> CandidateScore:
        """Holt die Scores eines einzelnen Users (fuer Debugging/Analyse).

        Args:
            user_id: ID des Benutzers
            company_id: ID des Unternehmens
            document_type: Dokumenttyp fuer Expertise
            entity_id: Entity fuer Relationship

        Returns:
            CandidateScore mit allen Scores
        """
        # User-Info holen
        user_result = await self.db.execute(
            select(User.id, User.email, User.full_name)
            .where(User.id == user_id)
        )
        user_row = user_result.first()

        if not user_row:
            raise ValueError(f"User {user_id} nicht gefunden")

        score = CandidateScore(
            user_id=user_row.id,
            user_email=user_row.email,
            user_name=user_row.full_name or user_row.email,
        )

        # Alle Scores berechnen
        expertise = await self._calculate_expertise_score(
            user_id, company_id, document_type, None
        )
        score.expertise_score = expertise["score"]
        score.expertise_details = expertise["details"]

        workload = await self._calculate_workload_score(user_id, company_id)
        score.workload_score = workload["score"]
        score.workload_details = workload["details"]

        availability = await self._calculate_availability_score(user_id)
        score.availability_score = availability["score"]
        score.availability_details = availability["details"]
        score.is_available = availability["is_available"]

        if entity_id:
            relationship = await self._calculate_relationship_score(
                user_id, entity_id, company_id
            )
            score.relationship_score = relationship["score"]
            score.relationship_details = relationship["details"]

        # Gesamtscore
        weights = self.DEFAULT_WEIGHTS
        score.total_score = (
            score.expertise_score * weights.expertise +
            score.workload_score * weights.workload +
            score.availability_score * weights.availability +
            score.relationship_score * weights.relationship
        )

        return score

    async def get_team_workload_overview(
        self,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """Gibt einen Ueberblick ueber die Team-Auslastung.

        Args:
            company_id: ID des Unternehmens

        Returns:
            Dict mit Team-Auslastungsstatistiken
        """
        # Alle aktiven User der Company
        candidates = await self._get_eligible_candidates(company_id, [])

        team_stats = []
        for user in candidates:
            workload = await self._calculate_workload_score(
                user["id"], company_id
            )
            availability = await self._calculate_availability_score(user["id"])

            team_stats.append({
                "user_id": str(user["id"]),
                "user_name": user["full_name"] or user["email"],
                "open_items": workload["details"].get("open_items", 0),
                "workload_score": workload["score"],
                "is_available": availability["is_available"],
                "availability_score": availability["score"],
            })

        # Sortiere nach Auslastung (niedrig zuerst = mehr Kapazitaet)
        team_stats.sort(key=lambda x: x["open_items"])

        total_open = sum(s["open_items"] for s in team_stats)
        available_count = sum(1 for s in team_stats if s["is_available"])

        return {
            "team_members": team_stats,
            "total_open_items": total_open,
            "available_members": available_count,
            "total_members": len(team_stats),
            "avg_items_per_member": total_open / len(team_stats) if team_stats else 0,
        }

    # =========================================================================
    # Score Calculation Methods
    # =========================================================================

    async def _get_eligible_candidates(
        self,
        company_id: UUID,
        exclude_user_ids: List[UUID],
    ) -> List[Dict[str, Any]]:
        """Holt alle berechtigten Kandidaten fuer Zuweisung.

        Args:
            company_id: ID des Unternehmens
            exclude_user_ids: Auszuschliessende User-IDs

        Returns:
            Liste von User-Dicts
        """
        query = (
            select(User.id, User.email, User.full_name)
            .join(UserCompany, UserCompany.user_id == User.id)
            .where(
                and_(
                    UserCompany.company_id == company_id,
                    User.is_active == True,  # noqa: E712
                    User.id.notin_(exclude_user_ids) if exclude_user_ids else True,
                    # Nur User mit relevanten Rollen
                    UserCompany.role.in_(["owner", "admin", "manager", "editor", "member"]),
                )
            )
        )

        result = await self.db.execute(query)
        rows = result.fetchall()

        return [
            {"id": row.id, "email": row.email, "full_name": row.full_name}
            for row in rows
        ]

    async def _get_document_context(
        self,
        document_id: UUID,
        company_id: UUID,
    ) -> Optional[Dict[str, Any]]:
        """Holt Dokumentkontext fuer Score-Berechnung.

        Args:
            document_id: ID des Dokuments
            company_id: ID des Unternehmens (Multi-Tenant)

        Returns:
            Dict mit Dokumentkontext oder None
        """
        result = await self.db.execute(
            select(
                Document.id,
                Document.doc_type,
                Document.entity_id,
                Document.extracted_data,
            )
            .where(
                and_(
                    Document.id == document_id,
                    Document.company_id == company_id,
                )
            )
        )
        row = result.first()

        if not row:
            return None

        return {
            "id": row.id,
            "doc_type": row.doc_type,
            "entity_id": row.entity_id,
            "extracted_data": row.extracted_data,
        }

    async def _calculate_expertise_score(
        self,
        user_id: UUID,
        company_id: UUID,
        document_type: Optional[str],
        task_type: Optional[str],
    ) -> Dict[str, Any]:
        """Berechnet Expertise-Score basierend auf Historie.

        Score basiert auf:
        - Anzahl verarbeiteter Dokumente des Typs
        - Erfolgsrate (Genehmigungen vs Ablehnungen)
        - Aktualitaet der Erfahrung

        Args:
            user_id: User-ID
            company_id: Company-ID
            document_type: Dokumenttyp
            task_type: Aufgabentyp

        Returns:
            Dict mit score und details
        """
        cutoff_date = utc_now() - timedelta(days=self.RECENT_DAYS_EXPERTISE)

        # Zaehle verarbeitete Validation Items
        validation_query = (
            select(
                func.count(ValidationQueueItem.id).label("total"),
                func.sum(
                    func.cast(
                        ValidationQueueItem.status == ValidationStatus.APPROVED.value,
                        Integer=False,
                    )
                ).label("approved"),
            )
            .join(Document, Document.id == ValidationQueueItem.document_id)
            .where(
                and_(
                    ValidationQueueItem.reviewer_id == user_id,
                    ValidationQueueItem.company_id == company_id,
                    ValidationQueueItem.reviewed_at >= cutoff_date,
                    ValidationQueueItem.status.in_([
                        ValidationStatus.APPROVED.value,
                        ValidationStatus.REJECTED.value,
                    ]),
                    # Dokumenttyp-Filter wenn vorhanden
                    Document.doc_type == document_type if document_type else True,
                )
            )
        )

        result = await self.db.execute(validation_query)
        row = result.first()

        total_processed = row.total or 0 if row else 0
        approved_count = row.approved or 0 if row else 0

        # Zaehle auch abgeschlossene Tasks
        task_query = (
            select(func.count(DocumentTask.id))
            .join(Document, Document.id == DocumentTask.document_id)
            .where(
                and_(
                    DocumentTask.assigned_to_id == user_id,
                    DocumentTask.status == TaskStatus.COMPLETED.value,
                    DocumentTask.completed_at >= cutoff_date,
                    Document.doc_type == document_type if document_type else True,
                )
            )
        )

        task_result = await self.db.execute(task_query)
        completed_tasks = task_result.scalar_one() or 0

        # Score-Berechnung
        total_experience = total_processed + completed_tasks

        if total_experience < self.MIN_EXPERTISE_TASKS:
            # Zu wenig Erfahrung - neutraler Score
            score = 50.0
            experience_level = "gering"
        elif total_experience < 10:
            score = 60.0
            experience_level = "mittel"
        elif total_experience < 25:
            score = 75.0
            experience_level = "gut"
        elif total_experience < 50:
            score = 85.0
            experience_level = "sehr_gut"
        else:
            score = 95.0
            experience_level = "experte"

        # Erfolgsrate-Bonus (max +5)
        if total_processed > 0:
            success_rate = approved_count / total_processed
            score += success_rate * 5

        score = min(100.0, score)

        return {
            "score": score,
            "details": {
                "total_processed": total_processed,
                "completed_tasks": completed_tasks,
                "total_experience": total_experience,
                "approved_count": approved_count,
                "success_rate": round(approved_count / total_processed * 100, 1) if total_processed > 0 else 0,
                "experience_level": experience_level,
                "document_type": document_type,
                "period_days": self.RECENT_DAYS_EXPERTISE,
            },
        }

    async def _calculate_workload_score(
        self,
        user_id: UUID,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """Berechnet Workload-Score basierend auf offenen Items.

        Score: 100 = keine offenen Items, 0 = MAX_WORKLOAD_ITEMS oder mehr

        Args:
            user_id: User-ID
            company_id: Company-ID

        Returns:
            Dict mit score und details
        """
        # Offene Validation Queue Items
        validation_query = (
            select(func.count(ValidationQueueItem.id))
            .where(
                and_(
                    ValidationQueueItem.reviewer_id == user_id,
                    ValidationQueueItem.company_id == company_id,
                    ValidationQueueItem.status == ValidationStatus.PENDING.value,
                )
            )
        )

        validation_result = await self.db.execute(validation_query)
        open_validations = validation_result.scalar_one() or 0

        # Offene Tasks
        task_query = (
            select(func.count(DocumentTask.id))
            .where(
                and_(
                    DocumentTask.assigned_to_id == user_id,
                    DocumentTask.status.in_([
                        TaskStatus.OPEN.value,
                        TaskStatus.IN_PROGRESS.value,
                        TaskStatus.BLOCKED.value,
                    ]),
                )
            )
        )

        task_result = await self.db.execute(task_query)
        open_tasks = task_result.scalar_one() or 0

        total_open = open_validations + open_tasks

        # Score-Berechnung: linear von 100 (0 items) bis 0 (MAX items)
        score = max(0.0, 100.0 - (total_open / self.MAX_WORKLOAD_ITEMS * 100))

        # Kapazitaetslevel
        if total_open == 0:
            capacity_level = "frei"
        elif total_open <= 5:
            capacity_level = "gering"
        elif total_open <= 10:
            capacity_level = "normal"
        elif total_open <= 15:
            capacity_level = "hoch"
        else:
            capacity_level = "ueberlastet"

        return {
            "score": score,
            "details": {
                "open_validations": open_validations,
                "open_tasks": open_tasks,
                "open_items": total_open,
                "max_items": self.MAX_WORKLOAD_ITEMS,
                "capacity_level": capacity_level,
            },
        }

    async def _calculate_availability_score(
        self,
        user_id: UUID,
    ) -> Dict[str, Any]:
        """Berechnet Verfuegbarkeits-Score.

        Prueft:
        - User.is_active Status
        - Abwesenheitseintraege (falls implementiert)
        - Letzter Login (falls getrackt)

        Args:
            user_id: User-ID

        Returns:
            Dict mit score, is_available und details
        """
        # User-Status pruefen
        result = await self.db.execute(
            select(
                User.is_active,
                User.last_login_at,
                # Hier koennten weitere Felder wie absence_until geprueft werden
            )
            .where(User.id == user_id)
        )
        row = result.first()

        if not row:
            return {
                "score": 0.0,
                "is_available": False,
                "reason": UnavailabilityReason.OFFLINE.value,
                "details": {"error": "User nicht gefunden"},
            }

        if not row.is_active:
            return {
                "score": 0.0,
                "is_available": False,
                "reason": UnavailabilityReason.OFFLINE.value,
                "details": {"is_active": False},
            }

        # Letzter Login - Score basierend auf Aktivitaet
        score = 100.0
        is_available = True
        details: Dict[str, Any] = {"is_active": True}

        if row.last_login_at:
            days_since_login = (utc_now() - row.last_login_at).days
            details["last_login_days_ago"] = days_since_login

            if days_since_login > 30:
                # Lange nicht eingeloggt - vermutlich nicht verfuegbar
                score = 20.0
                is_available = False
                details["status"] = "inaktiv"
            elif days_since_login > 7:
                score = 50.0
                details["status"] = "selten_aktiv"
            elif days_since_login > 1:
                score = 80.0
                details["status"] = "aktiv"
            else:
                score = 100.0
                details["status"] = "sehr_aktiv"
        else:
            # Kein Login-Datum - neutraler Score
            score = 70.0
            details["status"] = "unbekannt"

        # TODO: Hier koennten Abwesenheitseintraege geprueft werden
        # if user.absence_until and user.absence_until > utc_now():
        #     score = 0.0
        #     is_available = False

        return {
            "score": score,
            "is_available": is_available,
            "details": details,
        }

    async def _calculate_relationship_score(
        self,
        user_id: UUID,
        entity_id: UUID,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """Berechnet Relationship-Score basierend auf vorheriger Zusammenarbeit.

        Score basiert auf:
        - Anzahl verarbeiteter Dokumente des gleichen Kunden
        - Aktualitaet der Interaktionen

        Args:
            user_id: User-ID
            entity_id: Entity-ID (Kunde/Lieferant)
            company_id: Company-ID

        Returns:
            Dict mit score und details
        """
        cutoff_date = utc_now() - timedelta(days=self.RECENT_DAYS_RELATIONSHIP)

        # Zaehle Dokumente des gleichen Kunden die dieser User bearbeitet hat
        doc_query = (
            select(func.count(ValidationQueueItem.id))
            .join(Document, Document.id == ValidationQueueItem.document_id)
            .where(
                and_(
                    ValidationQueueItem.reviewer_id == user_id,
                    ValidationQueueItem.company_id == company_id,
                    Document.entity_id == entity_id,
                    ValidationQueueItem.reviewed_at >= cutoff_date,
                )
            )
        )

        result = await self.db.execute(doc_query)
        docs_processed = result.scalar_one() or 0

        # Score-Berechnung
        if docs_processed == 0:
            score = 50.0  # Neutral - keine vorherige Beziehung
            relationship_level = "keine"
        elif docs_processed < 3:
            score = 65.0
            relationship_level = "gering"
        elif docs_processed < 10:
            score = 80.0
            relationship_level = "mittel"
        elif docs_processed < 25:
            score = 90.0
            relationship_level = "hoch"
        else:
            score = 100.0
            relationship_level = "sehr_hoch"

        return {
            "score": score,
            "details": {
                "entity_id": str(entity_id),
                "documents_processed": docs_processed,
                "relationship_level": relationship_level,
                "period_days": self.RECENT_DAYS_RELATIONSHIP,
            },
        }

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _calculate_recommendation_confidence(
        self,
        candidates: List[CandidateScore],
    ) -> float:
        """Berechnet Konfidenz der Empfehlung.

        Basiert auf:
        - Abstand zum Zweitplatzierten
        - Absolute Hoehe des Top-Scores
        - Verfuegbarkeit des Kandidaten

        Args:
            candidates: Sortierte Kandidatenliste

        Returns:
            Konfidenz 0-100
        """
        if not candidates:
            return 0.0

        if len(candidates) == 1:
            # Nur ein Kandidat - moderate Konfidenz
            return min(70.0, candidates[0].total_score)

        best = candidates[0]
        second = candidates[1]

        # Basis: Absoluter Score
        confidence = best.total_score * 0.5

        # Bonus: Abstand zum Zweitplatzierten
        gap = best.total_score - second.total_score
        confidence += gap * 0.3

        # Bonus: Verfuegbarkeit
        if best.is_available:
            confidence += 10.0

        # Malus: Wenn Score niedrig
        if best.total_score < 50:
            confidence *= 0.7

        return min(100.0, max(0.0, confidence))

    def _generate_explanation(
        self,
        best_candidate: CandidateScore,
        candidates: List[CandidateScore],
        weights: FactorWeights,
        document_type: Optional[str],
        entity_id: Optional[UUID],
    ) -> Tuple[str, Dict[str, Any]]:
        """Generiert Erklaerung fuer die Empfehlung.

        Args:
            best_candidate: Bester Kandidat
            candidates: Alle Kandidaten
            weights: Verwendete Gewichtung
            document_type: Dokumenttyp
            entity_id: Entity-ID

        Returns:
            Tuple von (erklaerung_text, details_dict)
        """
        name = best_candidate.user_name

        # Hauptgruende sammeln
        reasons = []

        # Expertise
        if best_candidate.expertise_score >= 80:
            level = best_candidate.expertise_details.get("experience_level", "")
            if document_type:
                reasons.append(f"hohe Expertise fuer {document_type}-Dokumente ({level})")
            else:
                reasons.append(f"hohe allgemeine Expertise ({level})")

        # Workload
        if best_candidate.workload_score >= 80:
            items = best_candidate.workload_details.get("open_items", 0)
            reasons.append(f"geringe Auslastung ({items} offene Aufgaben)")

        # Relationship
        if entity_id and best_candidate.relationship_score >= 70:
            docs = best_candidate.relationship_details.get("documents_processed", 0)
            reasons.append(f"vorherige Erfahrung mit diesem Kunden ({docs} Dokumente)")

        # Verfuegbarkeit
        if best_candidate.is_available and best_candidate.availability_score >= 90:
            reasons.append("aktuell sehr aktiv im System")

        # Erklaerungstext
        if reasons:
            explanation = f"{name} empfohlen wegen: {', '.join(reasons[:3])}"
        else:
            explanation = f"{name} hat den hoechsten Gesamtscore ({best_candidate.total_score:.0f}/100)"

        # Details
        details = {
            "recommended_user": name,
            "total_score": round(best_candidate.total_score, 1),
            "score_breakdown": {
                "expertise": round(best_candidate.expertise_score, 1),
                "workload": round(best_candidate.workload_score, 1),
                "availability": round(best_candidate.availability_score, 1),
                "relationship": round(best_candidate.relationship_score, 1),
            },
            "weights_used": {
                "expertise": weights.expertise,
                "workload": weights.workload,
                "availability": weights.availability,
                "relationship": weights.relationship,
            },
            "reasons": reasons,
            "alternative_candidates": len(candidates) - 1,
        }

        return explanation, details


# =============================================================================
# Factory Function
# =============================================================================


def get_smart_escalation_service(db: AsyncSession) -> SmartEscalationService:
    """Factory-Funktion fuer SmartEscalationService.

    Args:
        db: AsyncSession fuer Datenbankoperationen

    Returns:
        SmartEscalationService Instanz
    """
    return SmartEscalationService(db)
