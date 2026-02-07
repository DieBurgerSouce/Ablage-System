# -*- coding: utf-8 -*-
"""
Entity Health Degradation Handler.

Enterprise Feature: Automatische Aktionen bei Verschlechterung des Entity-Risk-Scores.

Automatische Massnahmen wenn der Risiko-Score steigt:
- Kreditlimit automatisch reduzieren
- Zahlungsziele verkuerzen
- Vorkasse ab Schwellenwert verlangen
- Mahnprozess beschleunigen
- Alert zur Pruefung erstellen

Feinpoliert und durchdacht - Proaktives Risikomanagement.
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

import structlog
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_errors import safe_error_log
from app.db.models import BusinessEntity, Document, InvoiceTracking
from app.db.models_alert import Alert, AlertCategory, AlertSeverity
from app.services.risk_scoring_service import (
    RiskLevel,
    RiskScoringService,
    get_risk_scoring_service,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums
# =============================================================================


class HealthAction(str, Enum):
    """Moegliche Gesundheits-Massnahmen."""
    REDUCE_CREDIT_LIMIT = "reduce_credit_limit"
    SHORTEN_PAYMENT_TERMS = "shorten_payment_terms"
    REQUIRE_PREPAYMENT = "require_prepayment"
    ACCELERATE_DUNNING = "accelerate_dunning"
    REQUIRE_APPROVAL = "require_approval"
    CREATE_REVIEW_ALERT = "create_review_alert"
    NOTIFY_ACCOUNT_MANAGER = "notify_account_manager"
    SUSPEND_ORDERS = "suspend_orders"


class ActionStatus(str, Enum):
    """Status einer Massnahme."""
    RECOMMENDED = "recommended"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    APPLIED = "applied"
    REJECTED = "rejected"
    REVERTED = "reverted"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class HealthActionRecommendation:
    """Eine empfohlene Gesundheits-Massnahme."""
    id: UUID = field(default_factory=uuid4)
    action: HealthAction = HealthAction.CREATE_REVIEW_ALERT
    status: ActionStatus = ActionStatus.RECOMMENDED

    # Kontext
    entity_id: UUID = field(default_factory=uuid4)
    company_id: UUID = field(default_factory=uuid4)
    trigger_risk_score: float = 0.0
    trigger_risk_level: RiskLevel = RiskLevel.MEDIUM

    # Details
    description: str = ""
    reason: str = ""
    impact_description: str = ""

    # Parameter
    parameters: Dict[str, Any] = field(default_factory=dict)

    # Zeitstempel
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    applied_at: Optional[datetime] = None
    applied_by_id: Optional[UUID] = None

    # Vorherige Werte (fuer Rueckgaengig-Machen)
    previous_values: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "id": str(self.id),
            "action": self.action.value,
            "status": self.status.value,
            "entity_id": str(self.entity_id),
            "company_id": str(self.company_id),
            "trigger_risk_score": self.trigger_risk_score,
            "trigger_risk_level": self.trigger_risk_level.value,
            "description": self.description,
            "reason": self.reason,
            "impact_description": self.impact_description,
            "parameters": self.parameters,
            "created_at": self.created_at.isoformat(),
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
        }


@dataclass
class HealthActionConfig:
    """Konfiguration fuer automatische Massnahmen."""
    # Schwellenwerte
    credit_limit_reduction_threshold: float = 50.0  # Risk Score
    payment_terms_reduction_threshold: float = 60.0
    prepayment_threshold: float = 75.0
    dunning_acceleration_threshold: float = 65.0
    order_suspension_threshold: float = 85.0

    # Reduktionsfaktoren
    credit_limit_reduction_percent: float = 25.0  # Um 25% reduzieren
    payment_terms_reduction_days: int = 7  # 7 Tage weniger Zahlungsziel

    # Vorkasse-Einstellungen
    prepayment_percent: float = 50.0  # 50% Vorkasse

    # Dunning-Beschleunigung
    dunning_acceleration_days: int = 3  # 3 Tage frueher mahnen


@dataclass
class HealthAssessment:
    """Bewertung des Entity-Gesundheitszustands."""
    entity_id: UUID
    company_id: UUID
    current_risk_score: float
    current_risk_level: RiskLevel
    previous_risk_score: Optional[float] = None
    score_change: float = 0.0
    is_degrading: bool = False
    recommended_actions: List[HealthActionRecommendation] = field(default_factory=list)
    assessment_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# Entity Health Handler Service
# =============================================================================


class EntityHealthHandler:
    """
    Handler fuer Entity-Gesundheitsverschlechterung.

    Ueberwacht Risiko-Score-Aenderungen und triggert
    automatische Massnahmen bei Verschlechterung.
    """

    _instance: Optional["EntityHealthHandler"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "EntityHealthHandler":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        # Konfiguration
        self._config = HealthActionConfig()

        # Aktive Empfehlungen (entity_id -> List[Recommendation])
        self._recommendations: Dict[UUID, List[HealthActionRecommendation]] = {}
        self._recommendations_lock = asyncio.Lock()

        # Risk Scoring Service
        self._risk_service: Optional[RiskScoringService] = None

        logger.info("entity_health_handler_initialized")

    @property
    def risk_service(self) -> RiskScoringService:
        """Lazy-Load Risk Scoring Service."""
        if self._risk_service is None:
            self._risk_service = get_risk_scoring_service()
        return self._risk_service

    # =========================================================================
    # Health Assessment
    # =========================================================================

    async def assess_entity_health(
        self,
        db: AsyncSession,
        entity_id: UUID,
        company_id: UUID,
    ) -> HealthAssessment:
        """
        Bewertet den Gesundheitszustand einer Entity.

        Args:
            db: Database Session
            entity_id: Entity ID
            company_id: Company ID

        Returns:
            HealthAssessment mit Empfehlungen
        """
        # Aktuellen Risk Score abrufen
        risk_score, payment_score, factors = await self.risk_service.calculate_risk_score(
            db, entity_id
        )

        risk_level = self._get_risk_level(risk_score)

        # Vorherigen Score aus Entity laden
        entity_query = select(BusinessEntity).where(BusinessEntity.id == entity_id)
        result = await db.execute(entity_query)
        entity = result.scalar_one_or_none()

        previous_score = None
        score_change = 0.0

        if entity and entity.risk_score is not None:
            previous_score = entity.risk_score
            score_change = risk_score - previous_score

        is_degrading = score_change > 5.0  # Mehr als 5 Punkte Verschlechterung

        # Empfehlungen generieren
        recommendations = await self._generate_recommendations(
            db,
            entity_id,
            company_id,
            risk_score,
            risk_level,
            score_change,
        )

        assessment = HealthAssessment(
            entity_id=entity_id,
            company_id=company_id,
            current_risk_score=risk_score,
            current_risk_level=risk_level,
            previous_risk_score=previous_score,
            score_change=score_change,
            is_degrading=is_degrading,
            recommended_actions=recommendations,
        )

        # Empfehlungen cachen
        async with self._recommendations_lock:
            self._recommendations[entity_id] = recommendations

        logger.info(
            "entity_health_assessed",
            entity_id=str(entity_id),
            risk_score=round(risk_score, 1),
            risk_level=risk_level.value,
            score_change=round(score_change, 1),
            recommendations_count=len(recommendations),
        )

        return assessment

    def _get_risk_level(self, score: float) -> RiskLevel:
        """Bestimmt das Risiko-Level."""
        if score < 25:
            return RiskLevel.LOW
        elif score < 50:
            return RiskLevel.MEDIUM
        elif score < 75:
            return RiskLevel.HIGH
        else:
            return RiskLevel.CRITICAL

    async def _generate_recommendations(
        self,
        db: AsyncSession,
        entity_id: UUID,
        company_id: UUID,
        risk_score: float,
        risk_level: RiskLevel,
        score_change: float,
    ) -> List[HealthActionRecommendation]:
        """Generiert Empfehlungen basierend auf Risiko-Score."""
        recommendations: List[HealthActionRecommendation] = []
        config = self._config

        # Entity-Daten laden fuer aktuelle Werte
        entity_query = select(BusinessEntity).where(BusinessEntity.id == entity_id)
        result = await db.execute(entity_query)
        entity = result.scalar_one_or_none()

        current_credit_limit = Decimal("0")
        current_payment_days = 30  # Default

        if entity:
            # Credit Limit aus JSONB extrahieren falls vorhanden
            if entity.risk_factors and isinstance(entity.risk_factors, dict):
                current_credit_limit = Decimal(str(
                    entity.risk_factors.get("credit_limit", 0)
                ))
                current_payment_days = int(
                    entity.risk_factors.get("payment_terms_days", 30)
                )

        # 1. Kreditlimit-Reduktion
        if risk_score >= config.credit_limit_reduction_threshold and current_credit_limit > 0:
            new_limit = current_credit_limit * Decimal(str(1 - config.credit_limit_reduction_percent / 100))
            recommendations.append(HealthActionRecommendation(
                action=HealthAction.REDUCE_CREDIT_LIMIT,
                entity_id=entity_id,
                company_id=company_id,
                trigger_risk_score=risk_score,
                trigger_risk_level=risk_level,
                description=f"Kreditlimit von {current_credit_limit:,.2f} EUR auf {new_limit:,.2f} EUR reduzieren",
                reason=f"Risk Score {risk_score:.0f} ueberschreitet Schwellenwert {config.credit_limit_reduction_threshold:.0f}",
                impact_description="Reduziert maximales Bestellvolumen ohne Genehmigung",
                parameters={
                    "current_limit": float(current_credit_limit),
                    "new_limit": float(new_limit),
                    "reduction_percent": config.credit_limit_reduction_percent,
                },
                previous_values={"credit_limit": float(current_credit_limit)},
            ))

        # 2. Zahlungsziel-Verkuerzung
        if risk_score >= config.payment_terms_reduction_threshold:
            new_days = max(7, current_payment_days - config.payment_terms_reduction_days)
            recommendations.append(HealthActionRecommendation(
                action=HealthAction.SHORTEN_PAYMENT_TERMS,
                entity_id=entity_id,
                company_id=company_id,
                trigger_risk_score=risk_score,
                trigger_risk_level=risk_level,
                description=f"Zahlungsziel von {current_payment_days} auf {new_days} Tage verkuerzen",
                reason=f"Risk Score {risk_score:.0f} ueberschreitet Schwellenwert {config.payment_terms_reduction_threshold:.0f}",
                impact_description="Verkuerzt die Zeit bis zur Faelligkeit neuer Rechnungen",
                parameters={
                    "current_days": current_payment_days,
                    "new_days": new_days,
                },
                previous_values={"payment_terms_days": current_payment_days},
            ))

        # 3. Vorkasse verlangen
        if risk_score >= config.prepayment_threshold:
            recommendations.append(HealthActionRecommendation(
                action=HealthAction.REQUIRE_PREPAYMENT,
                entity_id=entity_id,
                company_id=company_id,
                trigger_risk_score=risk_score,
                trigger_risk_level=risk_level,
                description=f"{config.prepayment_percent:.0f}% Vorkasse bei neuen Auftraegen verlangen",
                reason=f"Risk Score {risk_score:.0f} ueberschreitet Schwellenwert {config.prepayment_threshold:.0f}",
                impact_description="Reduziert Ausfallrisiko durch Vorauszahlung",
                parameters={
                    "prepayment_percent": config.prepayment_percent,
                },
                previous_values={"prepayment_required": False},
            ))

        # 4. Mahnprozess beschleunigen
        if risk_score >= config.dunning_acceleration_threshold:
            recommendations.append(HealthActionRecommendation(
                action=HealthAction.ACCELERATE_DUNNING,
                entity_id=entity_id,
                company_id=company_id,
                trigger_risk_score=risk_score,
                trigger_risk_level=risk_level,
                description=f"Mahnfristen um {config.dunning_acceleration_days} Tage verkuerzen",
                reason=f"Risk Score {risk_score:.0f} ueberschreitet Schwellenwert {config.dunning_acceleration_threshold:.0f}",
                impact_description="Beschleunigt Mahnprozess bei ueberfaelligen Rechnungen",
                parameters={
                    "acceleration_days": config.dunning_acceleration_days,
                },
            ))

        # 5. Auftraege stoppen bei kritischem Risiko
        if risk_score >= config.order_suspension_threshold:
            recommendations.append(HealthActionRecommendation(
                action=HealthAction.SUSPEND_ORDERS,
                entity_id=entity_id,
                company_id=company_id,
                trigger_risk_score=risk_score,
                trigger_risk_level=risk_level,
                description="Neue Auftraege bis zur Pruefung sperren",
                reason=f"Kritischer Risk Score {risk_score:.0f} ueberschreitet Schwellenwert {config.order_suspension_threshold:.0f}",
                impact_description="Verhindert weitere Risikoexposition",
                parameters={"suspended": True},
                previous_values={"orders_suspended": False},
            ))

        # 6. Immer: Review-Alert bei hohem Risiko
        if risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            recommendations.append(HealthActionRecommendation(
                action=HealthAction.CREATE_REVIEW_ALERT,
                entity_id=entity_id,
                company_id=company_id,
                trigger_risk_score=risk_score,
                trigger_risk_level=risk_level,
                description="Alert zur manuellen Pruefung erstellen",
                reason=f"Risk Level ist {risk_level.value}",
                impact_description="Stellt sicher, dass ein Mitarbeiter die Situation prueft",
                parameters={},
            ))

        # 7. Bei schneller Verschlechterung: Account Manager benachrichtigen
        if score_change > 15.0:  # Mehr als 15 Punkte Verschlechterung
            recommendations.append(HealthActionRecommendation(
                action=HealthAction.NOTIFY_ACCOUNT_MANAGER,
                entity_id=entity_id,
                company_id=company_id,
                trigger_risk_score=risk_score,
                trigger_risk_level=risk_level,
                description="Account Manager ueber schnelle Verschlechterung informieren",
                reason=f"Risk Score ist um {score_change:.0f} Punkte gestiegen",
                impact_description="Ermoeglicht proaktive Kundenbetreuung",
                parameters={"score_change": score_change},
            ))

        return recommendations

    # =========================================================================
    # Apply Actions
    # =========================================================================

    async def apply_recommendation(
        self,
        db: AsyncSession,
        recommendation_id: UUID,
        applied_by_id: UUID,
    ) -> Tuple[bool, str]:
        """
        Wendet eine Empfehlung an.

        Args:
            db: Database Session
            recommendation_id: ID der Empfehlung
            applied_by_id: ID des ausfuehrenden Benutzers

        Returns:
            Tuple[success, message]
        """
        # Empfehlung finden
        recommendation = None
        async with self._recommendations_lock:
            for entity_recs in self._recommendations.values():
                for rec in entity_recs:
                    if rec.id == recommendation_id:
                        recommendation = rec
                        break
                if recommendation:
                    break

        if not recommendation:
            return False, "Empfehlung nicht gefunden"

        if recommendation.status != ActionStatus.RECOMMENDED:
            return False, f"Empfehlung hat bereits Status: {recommendation.status.value}"

        # Action ausfuehren
        success = False
        message = ""

        try:
            if recommendation.action == HealthAction.REDUCE_CREDIT_LIMIT:
                success, message = await self._apply_credit_limit_reduction(
                    db, recommendation
                )
            elif recommendation.action == HealthAction.SHORTEN_PAYMENT_TERMS:
                success, message = await self._apply_payment_terms_reduction(
                    db, recommendation
                )
            elif recommendation.action == HealthAction.REQUIRE_PREPAYMENT:
                success, message = await self._apply_prepayment_requirement(
                    db, recommendation
                )
            elif recommendation.action == HealthAction.ACCELERATE_DUNNING:
                success, message = await self._apply_dunning_acceleration(
                    db, recommendation
                )
            elif recommendation.action == HealthAction.CREATE_REVIEW_ALERT:
                success, message = await self._create_review_alert(
                    db, recommendation
                )
            elif recommendation.action == HealthAction.SUSPEND_ORDERS:
                success, message = await self._apply_order_suspension(
                    db, recommendation
                )
            else:
                message = f"Aktion {recommendation.action.value} nicht implementiert"

            if success:
                recommendation.status = ActionStatus.APPLIED
                recommendation.applied_at = datetime.now(timezone.utc)
                recommendation.applied_by_id = applied_by_id

                logger.info(
                    "health_action_applied",
                    recommendation_id=str(recommendation_id),
                    action=recommendation.action.value,
                    entity_id=str(recommendation.entity_id),
                )

        except Exception as e:
            message = f"Fehler: {str(e)}"
            logger.error(
                "health_action_failed",
                recommendation_id=str(recommendation_id),
                **safe_error_log(e),
            )

        return success, message

    async def _apply_credit_limit_reduction(
        self,
        db: AsyncSession,
        recommendation: HealthActionRecommendation,
    ) -> Tuple[bool, str]:
        """Wendet Kreditlimit-Reduktion an."""
        entity_query = select(BusinessEntity).where(
            BusinessEntity.id == recommendation.entity_id
        )
        result = await db.execute(entity_query)
        entity = result.scalar_one_or_none()

        if not entity:
            return False, "Entity nicht gefunden"

        new_limit = recommendation.parameters.get("new_limit", 0)

        # Risk factors aktualisieren
        risk_factors = entity.risk_factors or {}
        risk_factors["credit_limit"] = new_limit
        risk_factors["credit_limit_reduced_at"] = datetime.now(timezone.utc).isoformat()
        risk_factors["credit_limit_reason"] = recommendation.reason
        entity.risk_factors = risk_factors

        await db.commit()

        return True, f"Kreditlimit auf {new_limit:,.2f} EUR reduziert"

    async def _apply_payment_terms_reduction(
        self,
        db: AsyncSession,
        recommendation: HealthActionRecommendation,
    ) -> Tuple[bool, str]:
        """Wendet Zahlungsziel-Verkuerzung an."""
        entity_query = select(BusinessEntity).where(
            BusinessEntity.id == recommendation.entity_id
        )
        result = await db.execute(entity_query)
        entity = result.scalar_one_or_none()

        if not entity:
            return False, "Entity nicht gefunden"

        new_days = recommendation.parameters.get("new_days", 14)

        risk_factors = entity.risk_factors or {}
        risk_factors["payment_terms_days"] = new_days
        risk_factors["payment_terms_reduced_at"] = datetime.now(timezone.utc).isoformat()
        risk_factors["payment_terms_reason"] = recommendation.reason
        entity.risk_factors = risk_factors

        await db.commit()

        return True, f"Zahlungsziel auf {new_days} Tage verkuerzt"

    async def _apply_prepayment_requirement(
        self,
        db: AsyncSession,
        recommendation: HealthActionRecommendation,
    ) -> Tuple[bool, str]:
        """Aktiviert Vorkasse-Anforderung."""
        entity_query = select(BusinessEntity).where(
            BusinessEntity.id == recommendation.entity_id
        )
        result = await db.execute(entity_query)
        entity = result.scalar_one_or_none()

        if not entity:
            return False, "Entity nicht gefunden"

        prepayment_percent = recommendation.parameters.get("prepayment_percent", 50)

        risk_factors = entity.risk_factors or {}
        risk_factors["prepayment_required"] = True
        risk_factors["prepayment_percent"] = prepayment_percent
        risk_factors["prepayment_activated_at"] = datetime.now(timezone.utc).isoformat()
        risk_factors["prepayment_reason"] = recommendation.reason
        entity.risk_factors = risk_factors

        await db.commit()

        return True, f"Vorkasse von {prepayment_percent}% aktiviert"

    async def _apply_dunning_acceleration(
        self,
        db: AsyncSession,
        recommendation: HealthActionRecommendation,
    ) -> Tuple[bool, str]:
        """Beschleunigt Mahnprozess."""
        entity_query = select(BusinessEntity).where(
            BusinessEntity.id == recommendation.entity_id
        )
        result = await db.execute(entity_query)
        entity = result.scalar_one_or_none()

        if not entity:
            return False, "Entity nicht gefunden"

        acceleration_days = recommendation.parameters.get("acceleration_days", 3)

        risk_factors = entity.risk_factors or {}
        risk_factors["dunning_acceleration_days"] = acceleration_days
        risk_factors["dunning_accelerated_at"] = datetime.now(timezone.utc).isoformat()
        entity.risk_factors = risk_factors

        await db.commit()

        return True, f"Mahnfristen um {acceleration_days} Tage beschleunigt"

    async def _apply_order_suspension(
        self,
        db: AsyncSession,
        recommendation: HealthActionRecommendation,
    ) -> Tuple[bool, str]:
        """Sperrt neue Auftraege."""
        entity_query = select(BusinessEntity).where(
            BusinessEntity.id == recommendation.entity_id
        )
        result = await db.execute(entity_query)
        entity = result.scalar_one_or_none()

        if not entity:
            return False, "Entity nicht gefunden"

        risk_factors = entity.risk_factors or {}
        risk_factors["orders_suspended"] = True
        risk_factors["orders_suspended_at"] = datetime.now(timezone.utc).isoformat()
        risk_factors["orders_suspended_reason"] = recommendation.reason
        entity.risk_factors = risk_factors

        await db.commit()

        return True, "Neue Auftraege gesperrt"

    async def _create_review_alert(
        self,
        db: AsyncSession,
        recommendation: HealthActionRecommendation,
    ) -> Tuple[bool, str]:
        """Erstellt einen Review-Alert."""
        severity = AlertSeverity.HIGH
        if recommendation.trigger_risk_level == RiskLevel.CRITICAL:
            severity = AlertSeverity.CRITICAL

        alert = Alert(
            company_id=recommendation.company_id,
            alert_code="RISK_HEALTH_DEGRADATION",
            category=AlertCategory.RISK.value,
            severity=severity.value,
            title="Risiko-Verschlechterung erkannt",
            message=(
                f"Der Risiko-Score ist auf {recommendation.trigger_risk_score:.0f} gestiegen. "
                f"Eine manuelle Pruefung wird empfohlen."
            ),
            source_type="health_handler",
            source_id=str(recommendation.id),
            entity_id=recommendation.entity_id,
            metadata={
                "risk_score": recommendation.trigger_risk_score,
                "risk_level": recommendation.trigger_risk_level.value,
                "recommendation_id": str(recommendation.id),
            },
            available_actions=["acknowledge", "dismiss", "resolve", "escalate"],
        )

        db.add(alert)
        await db.flush()

        return True, f"Review-Alert {alert.id} erstellt"

    # =========================================================================
    # Batch Processing
    # =========================================================================

    async def check_all_entities(
        self,
        db: AsyncSession,
        company_id: Optional[UUID] = None,
        limit: int = 500,
    ) -> Dict[str, Any]:
        """
        Prueft alle Entities auf Gesundheitsverschlechterung.

        Args:
            db: Database Session
            company_id: Optional: Nur fuer diese Company
            limit: Maximale Anzahl

        Returns:
            Statistiken
        """
        query = select(BusinessEntity).where(
            and_(
                BusinessEntity.is_active == True,
                BusinessEntity.deleted_at.is_(None),
                BusinessEntity.risk_score.isnot(None),
            )
        )

        if company_id:
            # Filter nach Company ueber Documents
            subquery = (
                select(Document.business_entity_id)
                .where(
                    and_(
                        Document.company_id == company_id,
                        Document.business_entity_id.isnot(None),
                    )
                )
                .distinct()
            )
            query = query.where(BusinessEntity.id.in_(subquery))

        query = query.limit(limit)

        result = await db.execute(query)
        entities = result.scalars().all()

        stats = {
            "total_checked": 0,
            "degrading": 0,
            "critical": 0,
            "recommendations_generated": 0,
        }

        for entity in entities:
            stats["total_checked"] += 1

            # Company ID ermitteln (aus erstem Dokument)
            doc_query = (
                select(Document.company_id)
                .where(Document.business_entity_id == entity.id)
                .limit(1)
            )
            doc_result = await db.execute(doc_query)
            doc_company_id = doc_result.scalar_one_or_none()

            if not doc_company_id:
                continue

            assessment = await self.assess_entity_health(
                db, entity.id, doc_company_id
            )

            if assessment.is_degrading:
                stats["degrading"] += 1

            if assessment.current_risk_level == RiskLevel.CRITICAL:
                stats["critical"] += 1

            stats["recommendations_generated"] += len(assessment.recommended_actions)

        logger.info(
            "entity_health_check_completed",
            **stats,
        )

        return stats

    # =========================================================================
    # Public API
    # =========================================================================

    async def get_recommendations(
        self,
        entity_id: UUID,
    ) -> List[HealthActionRecommendation]:
        """Gibt Empfehlungen fuer eine Entity zurueck."""
        async with self._recommendations_lock:
            return self._recommendations.get(entity_id, [])

    async def get_all_pending_recommendations(
        self,
        company_id: Optional[UUID] = None,
    ) -> List[HealthActionRecommendation]:
        """Gibt alle ausstehenden Empfehlungen zurueck."""
        pending: List[HealthActionRecommendation] = []

        async with self._recommendations_lock:
            for recs in self._recommendations.values():
                for rec in recs:
                    if rec.status == ActionStatus.RECOMMENDED:
                        if company_id is None or rec.company_id == company_id:
                            pending.append(rec)

        return pending

    def update_config(self, config: HealthActionConfig) -> None:
        """Aktualisiert die Konfiguration."""
        self._config = config
        logger.info(
            "health_handler_config_updated",
            credit_threshold=config.credit_limit_reduction_threshold,
            prepayment_threshold=config.prepayment_threshold,
        )


# =============================================================================
# Singleton Factory
# =============================================================================

_handler_instance: Optional[EntityHealthHandler] = None
_handler_lock = threading.Lock()


def get_entity_health_handler() -> EntityHealthHandler:
    """Factory-Funktion fuer EntityHealthHandler Singleton."""
    global _handler_instance
    if _handler_instance is None:
        with _handler_lock:
            if _handler_instance is None:
                _handler_instance = EntityHealthHandler()
    return _handler_instance
