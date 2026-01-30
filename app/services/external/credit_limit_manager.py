# -*- coding: utf-8 -*-
"""
Credit Limit Manager Service.

Automatische Verwaltung von Kreditlimits:
- Limit-Berechnung basierend auf Score
- Automatische Anpassungen
- Limit-Historie
- Ueberwachung und Alerts

Vision 2.0 Feature: Erweiterte Integrationen
Feinpoliert und durchdacht.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Dict, Any, List
from uuid import UUID
from enum import Enum

from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.services.external.credit_scoring_service import CreditScoringService, RiskLevel

logger = logging.getLogger(__name__)


class LimitChangeReason(str, Enum):
    """Gruende fuer Limit-Aenderungen."""
    INITIAL = "initial"                    # Erstmalige Festlegung
    SCORE_UPDATE = "score_update"          # Score-basierte Aktualisierung
    PAYMENT_BEHAVIOR = "payment_behavior"  # Zahlungsverhalten
    MANUAL_INCREASE = "manual_increase"    # Manuelle Erhoehung
    MANUAL_DECREASE = "manual_decrease"    # Manuelle Reduzierung
    RISK_ALERT = "risk_alert"              # Risiko-Alert
    INSOLVENCY = "insolvency"              # Insolvenz
    RELATIONSHIP_DURATION = "relationship_duration"  # Beziehungsdauer


class CreditLimitChange(BaseModel):
    """Schema fuer Limit-Aenderung."""
    entity_id: UUID
    previous_limit: Decimal
    new_limit: Decimal
    change_percent: float
    reason: str
    reason_details: Optional[str] = None
    approved_by_id: Optional[UUID] = None
    changed_at: datetime = Field(default_factory=datetime.utcnow)


class CreditLimitManager:
    """
    Service fuer automatisches Kreditlimit-Management.

    Features:
    - Automatische Limit-Berechnung
    - Regelmaessige Neuberechnung
    - Limit-Historie
    - Genehmigungsworkflow fuer grosse Aenderungen
    """

    # Schwellwerte fuer automatische Anpassungen
    AUTO_INCREASE_THRESHOLD = 0.1    # Max 10% automatische Erhoehung
    AUTO_DECREASE_THRESHOLD = 0.2    # Max 20% automatische Reduzierung
    REVIEW_THRESHOLD = 0.3           # Ab 30% manuelle Pruefung

    # Basis-Limits nach Risikostufe
    BASE_LIMITS = {
        RiskLevel.MINIMAL: Decimal("500000"),
        RiskLevel.LOW: Decimal("200000"),
        RiskLevel.MODERATE: Decimal("100000"),
        RiskLevel.ELEVATED: Decimal("50000"),
        RiskLevel.HIGH: Decimal("20000"),
        RiskLevel.CRITICAL: Decimal("0"),
    }

    def __init__(
        self,
        db: AsyncSession,
        scoring_service: Optional[CreditScoringService] = None,
    ):
        """
        Initialisiere Manager.

        Args:
            db: AsyncSession fuer Datenbankzugriff
            scoring_service: Optional Credit-Scoring-Service
        """
        self.db = db
        self.scoring_service = scoring_service

    async def get_credit_limit(
        self,
        entity_id: UUID,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """
        Hole aktuelles Kreditlimit fuer Entity.

        Args:
            entity_id: Business-Entity ID
            company_id: Mandanten-ID

        Returns:
            Limit-Informationen
        """
        from app.db.models import BusinessEntity

        result = await self.db.execute(
            select(BusinessEntity).where(
                and_(
                    BusinessEntity.id == entity_id,
                    BusinessEntity.company_id == company_id,
                )
            )
        )
        entity = result.scalar_one_or_none()

        if not entity:
            raise ValueError(f"Entity {entity_id} nicht gefunden")

        # Hole Limit aus Entity-Metadata oder berechne
        metadata = entity.metadata or {}
        credit_data = metadata.get("credit_limit", {})

        current_limit = Decimal(str(credit_data.get("amount", 0)))
        last_updated = credit_data.get("updated_at")

        # Hole aktuelle Nutzung
        utilization = await self._calculate_utilization(entity_id, company_id)

        return {
            "entity_id": str(entity_id),
            "entity_name": entity.name,
            "credit_limit": float(current_limit),
            "utilized_amount": utilization["utilized"],
            "available_amount": max(0, float(current_limit) - utilization["utilized"]),
            "utilization_percent": utilization["percent"],
            "last_updated": last_updated,
            "risk_level": credit_data.get("risk_level"),
            "next_review": credit_data.get("next_review"),
        }

    async def calculate_and_update_limit(
        self,
        entity_id: UUID,
        company_id: UUID,
        user_id: Optional[UUID] = None,
        include_external: bool = True,
    ) -> Dict[str, Any]:
        """
        Berechne und aktualisiere Kreditlimit.

        Args:
            entity_id: Business-Entity ID
            company_id: Mandanten-ID
            user_id: Optional ausfuehrender User
            include_external: Externe Daten einbeziehen

        Returns:
            Aktualisierungsergebnis
        """
        from app.db.models import BusinessEntity

        # Hole Entity
        result = await self.db.execute(
            select(BusinessEntity).where(
                and_(
                    BusinessEntity.id == entity_id,
                    BusinessEntity.company_id == company_id,
                )
            )
        )
        entity = result.scalar_one_or_none()

        if not entity:
            raise ValueError(f"Entity {entity_id} nicht gefunden")

        # Berechne Score
        if not self.scoring_service:
            self.scoring_service = CreditScoringService(self.db)

        score_result = await self.scoring_service.calculate_score(
            entity_id=entity_id,
            company_id=company_id,
            include_external=include_external,
        )

        # Bestimme neues Limit
        risk_level = RiskLevel(score_result["risk_level"])
        base_limit = self.BASE_LIMITS[risk_level]

        # Anpassung basierend auf Score
        score = score_result["total_score"]
        score_multiplier = 0.5 + (score / 100)  # 0.5-1.5
        new_limit = base_limit * Decimal(str(score_multiplier))

        # Runde auf 1000
        new_limit = (new_limit // 1000) * 1000

        # Hole altes Limit
        metadata = entity.metadata or {}
        old_credit_data = metadata.get("credit_limit", {})
        old_limit = Decimal(str(old_credit_data.get("amount", 0)))

        # Berechne Aenderung
        if old_limit > 0:
            change_percent = float((new_limit - old_limit) / old_limit)
        else:
            change_percent = 1.0  # Neues Limit

        # Bestimme ob automatisch oder Review
        requires_review = False
        reason = LimitChangeReason.SCORE_UPDATE.value

        if abs(change_percent) > self.REVIEW_THRESHOLD:
            requires_review = True
            reason = LimitChangeReason.MANUAL_INCREASE.value if change_percent > 0 else LimitChangeReason.MANUAL_DECREASE.value

        # Automatische Begrenzung
        if not requires_review:
            if change_percent > self.AUTO_INCREASE_THRESHOLD:
                new_limit = old_limit * Decimal("1.1")  # Max 10% automatisch
            elif change_percent < -self.AUTO_DECREASE_THRESHOLD:
                new_limit = old_limit * Decimal("0.8")  # Max 20% automatisch

        # Speichere neues Limit
        now = datetime.utcnow()
        new_credit_data = {
            "amount": float(new_limit),
            "risk_level": risk_level.value,
            "score": score,
            "updated_at": now.isoformat(),
            "updated_by": str(user_id) if user_id else "system",
            "next_review": (now + timedelta(days=90)).isoformat(),
            "requires_review": requires_review,
        }

        metadata["credit_limit"] = new_credit_data

        # Historie speichern
        history = metadata.get("credit_limit_history", [])
        history.append({
            "previous": float(old_limit),
            "new": float(new_limit),
            "change_percent": change_percent,
            "reason": reason,
            "changed_at": now.isoformat(),
            "changed_by": str(user_id) if user_id else "system",
        })
        # Nur letzte 20 Eintraege behalten
        metadata["credit_limit_history"] = history[-20:]

        entity.metadata = metadata
        await self.db.flush()

        logger.info(
            f"Credit limit updated for {entity_id}: {old_limit} -> {new_limit} ({change_percent:+.1%})"
        )

        return {
            "entity_id": str(entity_id),
            "previous_limit": float(old_limit),
            "new_limit": float(new_limit),
            "change_percent": change_percent,
            "risk_level": risk_level.value,
            "score": score,
            "requires_review": requires_review,
            "reason": reason,
            "updated_at": now.isoformat(),
        }

    async def manual_adjust_limit(
        self,
        entity_id: UUID,
        company_id: UUID,
        new_limit: Decimal,
        user_id: UUID,
        reason: str,
        reason_details: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Manuelle Limit-Anpassung.

        Args:
            entity_id: Business-Entity ID
            company_id: Mandanten-ID
            new_limit: Neues Limit
            user_id: Genehmigender User
            reason: Grund fuer Aenderung
            reason_details: Details

        Returns:
            Aktualisierungsergebnis
        """
        from app.db.models import BusinessEntity

        result = await self.db.execute(
            select(BusinessEntity).where(
                and_(
                    BusinessEntity.id == entity_id,
                    BusinessEntity.company_id == company_id,
                )
            )
        )
        entity = result.scalar_one_or_none()

        if not entity:
            raise ValueError(f"Entity {entity_id} nicht gefunden")

        metadata = entity.metadata or {}
        old_credit_data = metadata.get("credit_limit", {})
        old_limit = Decimal(str(old_credit_data.get("amount", 0)))

        if old_limit > 0:
            change_percent = float((new_limit - old_limit) / old_limit)
        else:
            change_percent = 1.0

        now = datetime.utcnow()
        new_credit_data = {
            "amount": float(new_limit),
            "risk_level": old_credit_data.get("risk_level", "unknown"),
            "score": old_credit_data.get("score"),
            "updated_at": now.isoformat(),
            "updated_by": str(user_id),
            "manual_adjustment": True,
            "next_review": (now + timedelta(days=90)).isoformat(),
        }

        metadata["credit_limit"] = new_credit_data

        # Historie
        history = metadata.get("credit_limit_history", [])
        history.append({
            "previous": float(old_limit),
            "new": float(new_limit),
            "change_percent": change_percent,
            "reason": reason,
            "reason_details": reason_details,
            "changed_at": now.isoformat(),
            "changed_by": str(user_id),
            "manual": True,
        })
        metadata["credit_limit_history"] = history[-20:]

        entity.metadata = metadata
        await self.db.flush()

        logger.info(
            f"Manual credit limit adjustment for {entity_id}: {old_limit} -> {new_limit} by {user_id}"
        )

        return {
            "entity_id": str(entity_id),
            "previous_limit": float(old_limit),
            "new_limit": float(new_limit),
            "change_percent": change_percent,
            "reason": reason,
            "reason_details": reason_details,
            "approved_by": str(user_id),
            "updated_at": now.isoformat(),
        }

    async def get_limit_history(
        self,
        entity_id: UUID,
        company_id: UUID,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Hole Limit-Historie.

        Args:
            entity_id: Business-Entity ID
            company_id: Mandanten-ID
            limit: Max Anzahl Eintraege

        Returns:
            Historie-Eintraege
        """
        from app.db.models import BusinessEntity

        result = await self.db.execute(
            select(BusinessEntity.metadata).where(
                and_(
                    BusinessEntity.id == entity_id,
                    BusinessEntity.company_id == company_id,
                )
            )
        )
        metadata = result.scalar()

        if not metadata:
            return []

        history = metadata.get("credit_limit_history", [])
        return history[-limit:]

    async def get_entities_for_review(
        self,
        company_id: UUID,
    ) -> List[Dict[str, Any]]:
        """
        Hole Entities die Review benoetigen.

        Args:
            company_id: Mandanten-ID

        Returns:
            Liste von Entities fuer Review
        """
        from app.db.models import BusinessEntity

        now = datetime.utcnow()

        # Hole alle Entities mit abgelaufenem Review oder requires_review
        result = await self.db.execute(
            select(BusinessEntity)
            .where(BusinessEntity.company_id == company_id)
        )
        entities = list(result.scalars().all())

        review_needed = []
        for entity in entities:
            metadata = entity.metadata or {}
            credit_data = metadata.get("credit_limit", {})

            if not credit_data:
                # Noch kein Limit gesetzt
                review_needed.append({
                    "entity_id": str(entity.id),
                    "entity_name": entity.name,
                    "reason": "initial",
                    "current_limit": 0,
                })
                continue

            # Pruefe ob Review erforderlich
            requires_review = credit_data.get("requires_review", False)
            next_review_str = credit_data.get("next_review")

            if requires_review:
                review_needed.append({
                    "entity_id": str(entity.id),
                    "entity_name": entity.name,
                    "reason": "limit_change_approval",
                    "current_limit": credit_data.get("amount", 0),
                    "risk_level": credit_data.get("risk_level"),
                })
            elif next_review_str:
                next_review = datetime.fromisoformat(next_review_str)
                if now >= next_review:
                    review_needed.append({
                        "entity_id": str(entity.id),
                        "entity_name": entity.name,
                        "reason": "scheduled_review",
                        "current_limit": credit_data.get("amount", 0),
                        "risk_level": credit_data.get("risk_level"),
                        "last_review": credit_data.get("updated_at"),
                    })

        return review_needed

    async def _calculate_utilization(
        self,
        entity_id: UUID,
        company_id: UUID,
    ) -> Dict[str, float]:
        """Berechne aktuelle Limit-Auslastung."""
        from app.db.models import InvoiceTracking

        # Summe offener Rechnungen
        result = await self.db.execute(
            select(func.sum(InvoiceTracking.amount))
            .where(
                and_(
                    InvoiceTracking.entity_id == entity_id,
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.payment_status.in_(["unpaid", "overdue"]),
                )
            )
        )
        utilized = float(result.scalar() or 0)

        # Hole aktuelles Limit
        limit_info = await self.get_credit_limit(entity_id, company_id)
        credit_limit = limit_info.get("credit_limit", 0)

        if credit_limit > 0:
            percent = (utilized / credit_limit) * 100
        else:
            percent = 100 if utilized > 0 else 0

        return {
            "utilized": utilized,
            "percent": round(percent, 2),
        }

    async def batch_update_limits(
        self,
        company_id: UUID,
        include_external: bool = False,
    ) -> Dict[str, Any]:
        """
        Batch-Aktualisierung aller Limits.

        Args:
            company_id: Mandanten-ID
            include_external: Externe Daten einbeziehen

        Returns:
            Zusammenfassung der Aktualisierungen
        """
        from app.db.models import BusinessEntity

        result = await self.db.execute(
            select(BusinessEntity.id)
            .where(BusinessEntity.company_id == company_id)
        )
        entity_ids = [row[0] for row in result.all()]

        updated = 0
        errors = 0
        changes = []

        for entity_id in entity_ids:
            try:
                change = await self.calculate_and_update_limit(
                    entity_id=entity_id,
                    company_id=company_id,
                    include_external=include_external,
                )
                changes.append(change)
                updated += 1
            except Exception as e:
                logger.error(f"Batch limit update failed for {entity_id}: {e}")
                errors += 1

        await self.db.commit()

        return {
            "total_entities": len(entity_ids),
            "updated": updated,
            "errors": errors,
            "changes": changes,
        }
