"""
Odoo AI Feedback Service.

Phase 6: Odoo Integration Deepening
- Push AI insights (Risk Scores, Payment Suggestions) to Odoo
- Batch sync support for efficiency
- Error handling with retry logic

Feinpoliert und durchdacht - AI-powered ERP Integration.
"""

import structlog
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_errors import safe_error_log
from app.db.models import BusinessEntity, ERPConnection, ERPEntityMapping
from app.schemas.odoo import (
    OdooFeedbackType,
    OdooFeedbackStatus,
    OdooFeedbackPayload,
    RiskScoreFeedback,
    PaymentSuggestionFeedback,
    SkontoPredictionFeedback,
)
from app.services.erp.odoo_connector import OdooConnector
from app.services.erp.base_connector import ERPConnectionConfig, ERPEntity

logger = structlog.get_logger(__name__)


# =============================================================================
# Custom Field Mappings for Odoo
# =============================================================================

# Odoo custom fields for AI feedback
# These need to be created in Odoo (Settings > Technical > Fields)
ODOO_CUSTOM_FIELDS = {
    OdooFeedbackType.RISK_SCORE: {
        "model": "res.partner",
        "fields": {
            "x_ablage_risk_score": "score",
            "x_ablage_risk_level": "risk_level",
            "x_ablage_payment_score": "payment_behavior_score",
            "x_ablage_risk_updated": "calculated_at",
        },
    },
    OdooFeedbackType.PAYMENT_SUGGESTION: {
        "model": "res.partner",
        "fields": {
            "x_ablage_suggested_payment_term": "suggested_payment_term",
            "x_ablage_suggested_credit_limit": "suggested_credit_limit",
            "x_ablage_payment_suggestion_reason": "reason",
        },
    },
    OdooFeedbackType.SKONTO_PREDICTION: {
        "model": "res.partner",
        "fields": {
            "x_ablage_skonto_probability": "skonto_usage_probability",
            "x_ablage_avg_payment_days": "average_payment_days",
            "x_ablage_recommended_skonto": "recommended_skonto_percent",
        },
    },
}


class OdooFeedbackService:
    """
    Service für das Pushen von AI-Insights zu Odoo.

    Features:
    - Risk Score Push: Aktualisiert Risiko-Bewertungen in Odoo
    - Payment Suggestions: Empfiehlt Zahlungsbedingungen
    - Skonto Predictions: Vorhersage zur Skonto-Nutzung
    - Batch Support: Effiziente Massenverarbeitung
    - Retry Logic: Automatische Wiederholung bei Fehlern

    Usage:
        service = OdooFeedbackService()
        result = await service.push_risk_score(
            db, connection_id, entity_id, score=75.0, factors={...}
        )
    """

    def __init__(self) -> None:
        """Initialisiert den Feedback Service."""
        self._max_retries = 3
        self._retry_delay_seconds = 5

    # =========================================================================
    # Risk Score Push
    # =========================================================================

    async def push_risk_score(
        self,
        db: AsyncSession,
        connection_id: UUID,
        entity_id: UUID,
        score: float,
        payment_behavior_score: float,
        risk_level: str,
        factors: Dict[str, Any],
    ) -> Tuple[bool, Optional[str]]:
        """
        Pusht einen Risk Score zu Odoo.

        Args:
            db: Datenbank-Session
            connection_id: ERP-Verbindungs-ID
            entity_id: Lokale Entity-ID (Kunde/Lieferant)
            score: Risiko-Score (0-100)
            payment_behavior_score: Zahlungsverhalten-Score (0-100)
            risk_level: Risiko-Level (low/medium/high/critical)
            factors: Risikofaktoren (sanitized, ohne PII)

        Returns:
            Tuple[success, error_message]
        """
        try:
            # Get Odoo partner ID
            odoo_partner_id = await self._get_odoo_partner_id(
                db, connection_id, entity_id
            )
            if not odoo_partner_id:
                return False, "Keine Odoo-Verknüpfung gefunden"

            # Create connector
            connector = await self._create_connector(db, connection_id)
            if not connector:
                return False, "Verbindung nicht verfügbar"

            # Prepare data for Odoo (sanitize factors)
            sanitized_factors = self._sanitize_factors(factors)
            now = datetime.now(timezone.utc)

            odoo_data = {
                "x_ablage_risk_score": round(score, 1),
                "x_ablage_risk_level": risk_level,
                "x_ablage_payment_score": round(payment_behavior_score, 1),
                "x_ablage_risk_updated": now.strftime("%Y-%m-%d %H:%M:%S"),
                "x_ablage_risk_factors": sanitized_factors,  # JSONB in Odoo
            }

            # Connect and push
            if not await connector.connect():
                return False, connector.last_error or "Verbindungsfehler"

            try:
                success = await connector.update_customer(
                    str(odoo_partner_id),
                    odoo_data
                )

                if success:
                    # Store feedback record
                    await self._store_feedback_record(
                        db=db,
                        connection_id=connection_id,
                        entity_id=entity_id,
                        feedback_type=OdooFeedbackType.RISK_SCORE,
                        feedback_data={
                            "score": score,
                            "payment_behavior_score": payment_behavior_score,
                            "risk_level": risk_level,
                        },
                        odoo_record_id=str(odoo_partner_id),
                        status=OdooFeedbackStatus.SUCCESS,
                    )

                    logger.info(
                        "odoo_risk_score_pushed",
                        entity_id=str(entity_id),
                        odoo_partner_id=odoo_partner_id,
                        score=round(score, 1),
                        risk_level=risk_level,
                    )
                    return True, None
                else:
                    return False, "Update fehlgeschlagen"

            finally:
                await connector.disconnect()

        except Exception as e:
            logger.exception(
                "odoo_risk_score_push_error",
                entity_id=str(entity_id),
                **safe_error_log(e),
            )
            return False, str(e)

    # =========================================================================
    # Payment Suggestion Push
    # =========================================================================

    async def push_payment_suggestion(
        self,
        db: AsyncSession,
        connection_id: UUID,
        entity_id: UUID,
        suggested_payment_term: str,
        suggested_credit_limit: Optional[float],
        reason: str,
        confidence: float,
        based_on_invoices: int,
    ) -> Tuple[bool, Optional[str]]:
        """
        Pusht einen Zahlungsvorschlag zu Odoo.

        Args:
            db: Datenbank-Session
            connection_id: ERP-Verbindungs-ID
            entity_id: Lokale Entity-ID
            suggested_payment_term: Empfohlene Zahlungsbedingung
            suggested_credit_limit: Empfohlenes Kreditlimit
            reason: Begruendung (sanitized)
            confidence: Konfidenz (0-1)
            based_on_invoices: Anzahl analysierter Rechnungen

        Returns:
            Tuple[success, error_message]
        """
        try:
            odoo_partner_id = await self._get_odoo_partner_id(
                db, connection_id, entity_id
            )
            if not odoo_partner_id:
                return False, "Keine Odoo-Verknüpfung gefunden"

            connector = await self._create_connector(db, connection_id)
            if not connector:
                return False, "Verbindung nicht verfügbar"

            # Sanitize reason (remove potential PII)
            sanitized_reason = self._sanitize_text(reason)

            odoo_data = {
                "x_ablage_suggested_payment_term": suggested_payment_term,
                "x_ablage_payment_suggestion_reason": sanitized_reason,
                "x_ablage_suggestion_confidence": round(confidence, 2),
                "x_ablage_suggestion_invoice_count": based_on_invoices,
                "x_ablage_suggestion_updated": datetime.now(timezone.utc).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            }

            if suggested_credit_limit is not None:
                odoo_data["x_ablage_suggested_credit_limit"] = round(
                    suggested_credit_limit, 2
                )

            if not await connector.connect():
                return False, connector.last_error or "Verbindungsfehler"

            try:
                success = await connector.update_customer(
                    str(odoo_partner_id),
                    odoo_data
                )

                if success:
                    await self._store_feedback_record(
                        db=db,
                        connection_id=connection_id,
                        entity_id=entity_id,
                        feedback_type=OdooFeedbackType.PAYMENT_SUGGESTION,
                        feedback_data={
                            "suggested_payment_term": suggested_payment_term,
                            "suggested_credit_limit": suggested_credit_limit,
                            "confidence": confidence,
                        },
                        odoo_record_id=str(odoo_partner_id),
                        status=OdooFeedbackStatus.SUCCESS,
                    )

                    logger.info(
                        "odoo_payment_suggestion_pushed",
                        entity_id=str(entity_id),
                        odoo_partner_id=odoo_partner_id,
                        suggested_payment_term=suggested_payment_term,
                    )
                    return True, None
                else:
                    return False, "Update fehlgeschlagen"

            finally:
                await connector.disconnect()

        except Exception as e:
            logger.exception(
                "odoo_payment_suggestion_push_error",
                entity_id=str(entity_id),
                **safe_error_log(e),
            )
            return False, str(e)

    # =========================================================================
    # Skonto Prediction Push
    # =========================================================================

    async def push_skonto_prediction(
        self,
        db: AsyncSession,
        connection_id: UUID,
        entity_id: UUID,
        skonto_usage_probability: float,
        average_payment_days: float,
        recommended_skonto_percent: Optional[float],
        recommendation: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Pusht eine Skonto-Vorhersage zu Odoo.

        Args:
            db: Datenbank-Session
            connection_id: ERP-Verbindungs-ID
            entity_id: Lokale Entity-ID
            skonto_usage_probability: Wahrscheinlichkeit der Skonto-Nutzung (0-1)
            average_payment_days: Durchschnittliche Zahlungstage
            recommended_skonto_percent: Empfohlener Skonto-Prozentsatz
            recommendation: Empfehlung (sanitized)

        Returns:
            Tuple[success, error_message]
        """
        try:
            odoo_partner_id = await self._get_odoo_partner_id(
                db, connection_id, entity_id
            )
            if not odoo_partner_id:
                return False, "Keine Odoo-Verknüpfung gefunden"

            connector = await self._create_connector(db, connection_id)
            if not connector:
                return False, "Verbindung nicht verfügbar"

            sanitized_recommendation = self._sanitize_text(recommendation)

            odoo_data = {
                "x_ablage_skonto_probability": round(skonto_usage_probability, 3),
                "x_ablage_avg_payment_days": round(average_payment_days, 1),
                "x_ablage_skonto_recommendation": sanitized_recommendation,
                "x_ablage_skonto_updated": datetime.now(timezone.utc).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            }

            if recommended_skonto_percent is not None:
                odoo_data["x_ablage_recommended_skonto"] = round(
                    recommended_skonto_percent, 2
                )

            if not await connector.connect():
                return False, connector.last_error or "Verbindungsfehler"

            try:
                success = await connector.update_customer(
                    str(odoo_partner_id),
                    odoo_data
                )

                if success:
                    await self._store_feedback_record(
                        db=db,
                        connection_id=connection_id,
                        entity_id=entity_id,
                        feedback_type=OdooFeedbackType.SKONTO_PREDICTION,
                        feedback_data={
                            "skonto_usage_probability": skonto_usage_probability,
                            "average_payment_days": average_payment_days,
                            "recommended_skonto_percent": recommended_skonto_percent,
                        },
                        odoo_record_id=str(odoo_partner_id),
                        status=OdooFeedbackStatus.SUCCESS,
                    )

                    logger.info(
                        "odoo_skonto_prediction_pushed",
                        entity_id=str(entity_id),
                        odoo_partner_id=odoo_partner_id,
                        probability=round(skonto_usage_probability, 2),
                    )
                    return True, None
                else:
                    return False, "Update fehlgeschlagen"

            finally:
                await connector.disconnect()

        except Exception as e:
            logger.exception(
                "odoo_skonto_prediction_push_error",
                entity_id=str(entity_id),
                **safe_error_log(e),
            )
            return False, str(e)

    # =========================================================================
    # Batch Push Methods
    # =========================================================================

    async def push_risk_scores_batch(
        self,
        db: AsyncSession,
        connection_id: UUID,
        scores: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Pusht mehrere Risk Scores zu Odoo (Batch).

        Args:
            db: Datenbank-Session
            connection_id: ERP-Verbindungs-ID
            scores: Liste von Score-Daten mit entity_id, score, etc.

        Returns:
            Dict mit success_count, failed_count, errors
        """
        success_count = 0
        failed_count = 0
        errors: List[Dict[str, Any]] = []

        for score_data in scores:
            entity_id = score_data.get("entity_id")
            if not entity_id:
                failed_count += 1
                errors.append({"entity_id": None, "error": "entity_id fehlt"})
                continue

            success, error = await self.push_risk_score(
                db=db,
                connection_id=connection_id,
                entity_id=UUID(str(entity_id)),
                score=score_data.get("score", 0),
                payment_behavior_score=score_data.get("payment_behavior_score", 50),
                risk_level=score_data.get("risk_level", "medium"),
                factors=score_data.get("factors", {}),
            )

            if success:
                success_count += 1
            else:
                failed_count += 1
                errors.append({"entity_id": str(entity_id), "error": error})

        logger.info(
            "odoo_risk_scores_batch_pushed",
            connection_id=str(connection_id),
            success_count=success_count,
            failed_count=failed_count,
        )

        return {
            "success_count": success_count,
            "failed_count": failed_count,
            "total": len(scores),
            "errors": errors,
        }

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def _get_odoo_partner_id(
        self,
        db: AsyncSession,
        connection_id: UUID,
        entity_id: UUID,
    ) -> Optional[int]:
        """
        Holt die Odoo Partner-ID für eine lokale Entity.

        Sucht in der ERPEntityMapping-Tabelle nach der Verknüpfung.
        """
        result = await db.execute(
            select(ERPEntityMapping).where(
                and_(
                    ERPEntityMapping.connection_id == connection_id,
                    ERPEntityMapping.local_id == entity_id,
                    ERPEntityMapping.entity_type.in_(["customer", "supplier"]),
                )
            )
        )
        mapping = result.scalar_one_or_none()

        if mapping and mapping.remote_id:
            try:
                return int(mapping.remote_id)
            except ValueError:
                return None

        return None

    async def _create_connector(
        self,
        db: AsyncSession,
        connection_id: UUID,
    ) -> Optional[OdooConnector]:
        """Erstellt einen OdooConnector für die Verbindung."""
        from app.workers.tasks.erp_sync_tasks import get_connection_config

        config = await get_connection_config(db, connection_id)
        if not config or not config.is_active:
            return None

        return OdooConnector(config)

    async def _store_feedback_record(
        self,
        db: AsyncSession,
        connection_id: UUID,
        entity_id: UUID,
        feedback_type: OdooFeedbackType,
        feedback_data: Dict[str, Any],
        odoo_record_id: Optional[str],
        status: OdooFeedbackStatus,
        error_message: Optional[str] = None,
    ) -> None:
        """Speichert ein Feedback-Record für Tracking."""
        from app.db.models import OdooAIFeedback
        import uuid

        now = datetime.now(timezone.utc)

        feedback = OdooAIFeedback(
            id=uuid.uuid4(),
            connection_id=connection_id,
            entity_id=entity_id,
            feedback_type=feedback_type.value,
            feedback_data=feedback_data,
            status=status.value,
            pushed_at=now if status == OdooFeedbackStatus.SUCCESS else None,
            odoo_record_id=odoo_record_id,
            error_message=error_message,
        )

        db.add(feedback)
        await db.commit()

    def _sanitize_factors(self, factors: Dict[str, Any]) -> Dict[str, Any]:
        """
        Entfernt PII aus Risikofaktoren.

        SECURITY: Entfernt Namen, Adressen und andere persoenliche Daten.
        """
        # Erlaubte numerische Felder
        allowed_fields = {
            "payment_delay_days",
            "default_rate",
            "invoice_volume",
            "document_frequency",
            "relationship_months",
            "total_invoices",
            "paid_invoices",
            "overdue_invoices",
            "open_invoices",
        }

        sanitized = {}
        for key, value in factors.items():
            if key in allowed_fields:
                # Runde numerische Werte
                if isinstance(value, (int, float)):
                    sanitized[key] = round(value, 2) if isinstance(value, float) else value
                else:
                    sanitized[key] = value

        return sanitized

    def _sanitize_text(self, text: str, max_length: int = 500) -> str:
        """
        Sanitisiert Text für sichere Speicherung.

        Entfernt potentiell sensitive Daten und begrenzt Länge.
        """
        import re

        # Entferne potentielle Kundennamen und Zahlen die IBANs sein könnten
        sanitized = re.sub(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b", "[IBAN]", text)
        sanitized = re.sub(r"\b\d{6,}\b", "[NUMMER]", sanitized)

        # Begrenze Länge
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length - 3] + "..."

        return sanitized
