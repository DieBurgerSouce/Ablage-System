# -*- coding: utf-8 -*-
"""
Internal Credit Scoring Service.

Kombiniert externe Bonitaetsdaten mit internen Erfahrungen:
- Multi-Faktor Scoring
- Historische Zahlungsdaten
- Risikoklassen
- Empfehlungen

Vision 2.0 Feature: Erweiterte Integrationen
Feinpoliert und durchdacht.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Dict, Any, List
from uuid import UUID
from enum import Enum

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.external.creditreform_service import CreditreformService, CreditCheckResult
from app.core.safe_errors import safe_error_detail

logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    """Risikostufen."""
    MINIMAL = "minimal"      # Score 90-100
    LOW = "low"              # Score 75-89
    MODERATE = "moderate"    # Score 60-74
    ELEVATED = "elevated"    # Score 45-59
    HIGH = "high"            # Score 30-44
    CRITICAL = "critical"    # Score 0-29


class CreditDecision(str, Enum):
    """Kreditentscheidungen."""
    APPROVE = "approve"              # Genehmigt
    APPROVE_REDUCED = "approve_reduced"  # Mit reduziertem Limit
    REVIEW = "review"                # Manuelle Prüfung
    REJECT = "reject"                # Abgelehnt


class CreditScoringService:
    """
    Service für internes Kredit-Scoring.

    Kombiniert:
    - Externe Bonitaetsdaten (Creditreform)
    - Interne Zahlungshistorie
    - Beziehungsdauer
    - Dokumentenhäufigkeit
    """

    # Faktor-Gewichtungen
    WEIGHTS = {
        "external_score": 0.35,     # Creditreform
        "payment_history": 0.30,    # Zahlungsverhalten
        "relationship": 0.15,       # Beziehungsdauer
        "volume": 0.10,             # Transaktionsvolumen
        "documents": 0.10,          # Dokumentenqualität
    }

    # Kreditlimit-Multiplikatoren nach Risikostufe
    LIMIT_MULTIPLIERS = {
        RiskLevel.MINIMAL: 1.5,
        RiskLevel.LOW: 1.2,
        RiskLevel.MODERATE: 1.0,
        RiskLevel.ELEVATED: 0.7,
        RiskLevel.HIGH: 0.4,
        RiskLevel.CRITICAL: 0.0,
    }

    def __init__(
        self,
        db: AsyncSession,
        creditreform: Optional[CreditreformService] = None,
    ):
        """
        Initialisiere Service.

        Args:
            db: AsyncSession für Datenbankzugriff
            creditreform: Optional Creditreform-Service
        """
        self.db = db
        self.creditreform = creditreform or CreditreformService()

    async def calculate_score(
        self,
        entity_id: UUID,
        company_id: UUID,
        include_external: bool = True,
    ) -> Dict[str, Any]:
        """
        Berechne Kredit-Score für eine Entity.

        Args:
            entity_id: Business-Entity ID
            company_id: Mandanten-ID
            include_external: Externe Daten einbeziehen

        Returns:
            Score-Ergebnis mit Details
        """
        from app.db.models import BusinessEntity

        # Entity laden
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

        # Faktor-Scores berechnen
        factors = {}

        # 1. Externer Score (Creditreform)
        if include_external:
            external_result = await self._get_external_score(entity)
            factors["external_score"] = external_result
        else:
            factors["external_score"] = {"score": 70, "source": "not_checked"}

        # 2. Zahlungshistorie
        factors["payment_history"] = await self._calculate_payment_score(entity_id, company_id)

        # 3. Beziehungsdauer
        factors["relationship"] = await self._calculate_relationship_score(entity_id, company_id)

        # 4. Transaktionsvolumen
        factors["volume"] = await self._calculate_volume_score(entity_id, company_id)

        # 5. Dokumentenqualität
        factors["documents"] = await self._calculate_document_score(entity_id, company_id)

        # Gewichteten Gesamt-Score berechnen
        total_score = sum(
            factors[key]["score"] * self.WEIGHTS[key]
            for key in self.WEIGHTS.keys()
        )

        # Risikostufe bestimmen
        risk_level = self._score_to_risk_level(total_score)

        # Kreditlimit berechnen
        base_limit = factors["external_score"].get("recommended_limit", 50000)
        adjusted_limit = base_limit * self.LIMIT_MULTIPLIERS[risk_level]

        # Entscheidung
        decision, decision_reason = self._make_decision(total_score, risk_level, factors)

        return {
            "entity_id": str(entity_id),
            "entity_name": entity.name,
            "total_score": round(total_score, 2),
            "risk_level": risk_level.value,
            "factors": factors,
            "recommended_credit_limit": round(adjusted_limit, 2),
            "base_credit_limit": base_limit,
            "decision": decision.value,
            "decision_reason": decision_reason,
            "calculated_at": datetime.utcnow().isoformat(),
            "warnings": self._collect_warnings(factors),
        }

    async def _get_external_score(
        self,
        entity,
    ) -> Dict[str, Any]:
        """Hole externen Bonitaets-Score."""
        try:
            result = await self.creditreform.check_credit(
                company_name=entity.name,
                vat_id=getattr(entity, "vat_id", None),
            )

            # Konvertiere Creditreform-Index zu Score (100-600 -> 100-0)
            score = 100 - ((result.credit_index - 100) / 5)
            score = max(0, min(100, score))

            return {
                "score": round(score, 2),
                "source": "creditreform",
                "credit_index": result.credit_index,
                "credit_rating": result.credit_rating,
                "probability_of_default": result.probability_of_default,
                "recommended_limit": float(result.recommended_credit_limit) if result.recommended_credit_limit else 50000,
                "warnings": result.warnings,
                "negative_features": result.negative_features,
            }

        except Exception as e:
            logger.warning(f"External credit check failed: {e}")
            return {
                "score": 50,  # Neutral bei Fehler
                "source": "error",
                "error": safe_error_detail(e, "Vorgang"),
                "recommended_limit": 25000,  # Konservatives Limit
            }

    async def _calculate_payment_score(
        self,
        entity_id: UUID,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """Berechne Score basierend auf Zahlungshistorie."""
        from app.db.models import InvoiceTracking

        # Hole Rechnungsdaten
        result = await self.db.execute(
            select(
                func.count(InvoiceTracking.id).label("total"),
                func.count(InvoiceTracking.id).filter(
                    InvoiceTracking.payment_status == "paid"
                ).label("paid"),
                func.count(InvoiceTracking.id).filter(
                    InvoiceTracking.payment_status == "overdue"
                ).label("overdue"),
                func.avg(InvoiceTracking.days_overdue).label("avg_delay"),
            )
            .where(
                and_(
                    InvoiceTracking.entity_id == entity_id,
                    InvoiceTracking.company_id == company_id,
                )
            )
        )
        stats = result.one()

        if not stats.total or stats.total == 0:
            return {
                "score": 70,  # Neutral bei fehlenden Daten
                "reason": "Keine Zahlungshistorie verfügbar",
                "invoices_total": 0,
            }

        # Berechne Scores
        payment_rate = (stats.paid or 0) / stats.total
        overdue_rate = (stats.overdue or 0) / stats.total
        avg_delay = stats.avg_delay or 0

        # Score-Berechnung
        base_score = payment_rate * 100

        # Abzuege für Verzögerungen
        if avg_delay > 30:
            base_score -= min(30, avg_delay - 30)

        # Abzuege für überfällige
        base_score -= overdue_rate * 50

        score = max(0, min(100, base_score))

        return {
            "score": round(score, 2),
            "invoices_total": stats.total,
            "invoices_paid": stats.paid or 0,
            "invoices_overdue": stats.overdue or 0,
            "payment_rate": round(payment_rate, 4),
            "overdue_rate": round(overdue_rate, 4),
            "avg_delay_days": round(avg_delay, 1) if avg_delay else 0,
        }

    async def _calculate_relationship_score(
        self,
        entity_id: UUID,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """Berechne Score basierend auf Beziehungsdauer."""
        from app.db.models import BusinessEntity

        result = await self.db.execute(
            select(BusinessEntity.created_at)
            .where(BusinessEntity.id == entity_id)
        )
        created_at = result.scalar()

        if not created_at:
            return {"score": 50, "months": 0, "reason": "Unbekannt"}

        months = (datetime.utcnow() - created_at).days / 30

        # Score steigt mit Beziehungsdauer
        if months >= 60:  # 5+ Jahre
            score = 100
        elif months >= 36:  # 3+ Jahre
            score = 90
        elif months >= 24:  # 2+ Jahre
            score = 80
        elif months >= 12:  # 1+ Jahr
            score = 70
        elif months >= 6:   # 6+ Monate
            score = 60
        else:
            score = 50

        return {
            "score": score,
            "months": round(months, 1),
            "years": round(months / 12, 1),
        }

    async def _calculate_volume_score(
        self,
        entity_id: UUID,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """Berechne Score basierend auf Transaktionsvolumen."""
        from app.db.models import InvoiceTracking

        result = await self.db.execute(
            select(
                func.sum(InvoiceTracking.amount).label("total_volume"),
                func.count(InvoiceTracking.id).label("transaction_count"),
            )
            .where(
                and_(
                    InvoiceTracking.entity_id == entity_id,
                    InvoiceTracking.company_id == company_id,
                )
            )
        )
        stats = result.one()

        total_volume = float(stats.total_volume or 0)
        transaction_count = stats.transaction_count or 0

        if transaction_count == 0:
            return {"score": 50, "volume": 0, "transactions": 0}

        # Höhere Volumen = besserer Score (bis zu einem Punkt)
        if total_volume >= 1000000:
            score = 100
        elif total_volume >= 500000:
            score = 90
        elif total_volume >= 100000:
            score = 80
        elif total_volume >= 50000:
            score = 70
        elif total_volume >= 10000:
            score = 60
        else:
            score = 50

        return {
            "score": score,
            "total_volume": total_volume,
            "transaction_count": transaction_count,
            "avg_transaction": round(total_volume / transaction_count, 2),
        }

    async def _calculate_document_score(
        self,
        entity_id: UUID,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """Berechne Score basierend auf Dokumentenqualität."""
        from app.db.models import Document

        # Prüfe Dokumente der letzten 12 Monate
        since = datetime.utcnow() - timedelta(days=365)

        result = await self.db.execute(
            select(
                func.count(Document.id).label("total"),
                func.avg(Document.ocr_confidence).label("avg_confidence"),
            )
            .where(
                and_(
                    Document.linked_entity_id == entity_id,
                    Document.company_id == company_id,
                    Document.created_at >= since,
                )
            )
        )
        stats = result.one()

        document_count = stats.total or 0
        avg_confidence = stats.avg_confidence or 0

        if document_count == 0:
            return {"score": 60, "documents": 0, "reason": "Keine Dokumente"}

        # Mehr Dokumente = bessere Datenbasis
        doc_score = min(100, 50 + (document_count * 2))

        # Hohe OCR-Confidence = bessere Qualität
        confidence_score = avg_confidence * 100

        score = (doc_score * 0.6) + (confidence_score * 0.4)

        return {
            "score": round(score, 2),
            "documents_count": document_count,
            "avg_ocr_confidence": round(avg_confidence, 4),
        }

    def _score_to_risk_level(self, score: float) -> RiskLevel:
        """Konvertiere Score zu Risikostufe."""
        if score >= 90:
            return RiskLevel.MINIMAL
        elif score >= 75:
            return RiskLevel.LOW
        elif score >= 60:
            return RiskLevel.MODERATE
        elif score >= 45:
            return RiskLevel.ELEVATED
        elif score >= 30:
            return RiskLevel.HIGH
        else:
            return RiskLevel.CRITICAL

    def _make_decision(
        self,
        score: float,
        risk_level: RiskLevel,
        factors: Dict[str, Any],
    ) -> tuple[CreditDecision, str]:
        """Treffe Kreditentscheidung."""
        # Automatische Genehmigung bei niedrigem Risiko
        if risk_level in [RiskLevel.MINIMAL, RiskLevel.LOW]:
            return CreditDecision.APPROVE, "Niedriges Risiko - automatisch genehmigt"

        # Genehmigung mit reduziertem Limit bei moderatem Risiko
        if risk_level == RiskLevel.MODERATE:
            return CreditDecision.APPROVE_REDUCED, "Moderates Risiko - reduziertes Kreditlimit"

        # Manuelle Prüfung bei erhöhtem Risiko
        if risk_level == RiskLevel.ELEVATED:
            # Prüfe ob harte Ausschlusskriterien
            external = factors.get("external_score", {})
            if external.get("negative_features"):
                return CreditDecision.REVIEW, "Negative Merkmale gefunden - manuelle Prüfung erforderlich"
            return CreditDecision.REVIEW, "Erhöhtes Risiko - manuelle Prüfung empfohlen"

        # Ablehnung bei hohem/kritischem Risiko
        if risk_level == RiskLevel.HIGH:
            return CreditDecision.REJECT, "Hohes Risiko - Kredit nicht empfohlen"

        return CreditDecision.REJECT, "Kritisches Risiko - Kredit abgelehnt"

    def _collect_warnings(self, factors: Dict[str, Any]) -> List[str]:
        """Sammle Warnungen aus allen Faktoren."""
        warnings = []

        # Externe Warnungen
        external = factors.get("external_score", {})
        if external.get("warnings"):
            warnings.extend(external["warnings"])
        if external.get("negative_features"):
            warnings.extend(external["negative_features"])

        # Zahlungsverhalten
        payment = factors.get("payment_history", {})
        if payment.get("overdue_rate", 0) > 0.1:
            warnings.append("Hohe Rate an überfälligen Rechnungen")
        if payment.get("avg_delay_days", 0) > 14:
            warnings.append(f"Durchschnittliche Zahlungsverzögerung: {payment['avg_delay_days']:.0f} Tage")

        # Beziehung
        relationship = factors.get("relationship", {})
        if relationship.get("months", 0) < 6:
            warnings.append("Kurze Geschäftsbeziehung")

        return warnings

    async def batch_calculate(
        self,
        entity_ids: List[UUID],
        company_id: UUID,
        include_external: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Batch-Berechnung für mehrere Entities.

        Args:
            entity_ids: Liste von Entity-IDs
            company_id: Mandanten-ID
            include_external: Externe Daten einbeziehen

        Returns:
            Liste von Score-Ergebnissen
        """
        results = []

        for entity_id in entity_ids:
            try:
                result = await self.calculate_score(
                    entity_id=entity_id,
                    company_id=company_id,
                    include_external=include_external,
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Score calculation failed for {entity_id}: {e}")
                results.append({
                    "entity_id": str(entity_id),
                    "error": safe_error_detail(e, "Vorgang"),
                    "total_score": 0,
                    "risk_level": RiskLevel.CRITICAL.value,
                    "decision": CreditDecision.REJECT.value,
                })

        return results
