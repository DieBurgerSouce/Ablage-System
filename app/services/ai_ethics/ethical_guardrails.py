"""
Ethical Guardrails

Guardrails für KI-Aktionen:
- Prüft ob Aktion ethisch vertretbar ist
- Verhindert riskante Bulk-Aktionen
- Erfordert manuelle Bestätigung bei kritischen Entscheidungen

Feinpoliert und durchdacht - Enterprise AI Safety.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BusinessEntity, Document, InvoiceTracking

logger = structlog.get_logger(__name__)


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class GuardrailResult:
    """Ergebnis einer Guardrail-Prüfung."""

    allowed: bool  # Aktion erlaubt?
    reason: str  # German Begruendung
    risk_level: str  # low, medium, high
    requires_human_review: bool  # Manuelle Prüfung erforderlich?
    metadata: Dict[str, Any]  # Zusätzliche Infos

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "risk_level": self.risk_level,
            "requires_human_review": self.requires_human_review,
            "metadata": self.metadata,
        }


# =============================================================================
# Ethical Guardrails
# =============================================================================


class EthicalGuardrails:
    """
    Ethical Guardrails für KI-Aktionen.

    Prüft:
    - Bulk-Aktionen (z.B. Massen-Löschung)
    - Kritische Entscheidungen (z.B. hohe Zahlungen)
    - Sensitive Daten-Zugriffe
    """

    def __init__(self) -> None:
        """Initialisiert Guardrails."""
        # Schwellwerte
        self.BULK_ACTION_THRESHOLD = 10  # Mehr als 10 Items = Bulk
        self.HIGH_VALUE_THRESHOLD = 10000  # EUR
        self.CRITICAL_RISK_THRESHOLD = 75  # Risk Score

    async def check_action(
        self,
        action_type: str,
        parameters: Dict,
        company_id: UUID,
        db: AsyncSession,
    ) -> GuardrailResult:
        """
        Prüft ob Aktion erlaubt ist.

        Args:
            action_type: Aktionstyp (z.B. delete_documents, approve_payment)
            parameters: Aktionsparameter
            company_id: Mandanten-ID für Multi-Tenant Isolation
            db: Database session

        Returns:
            GuardrailResult
        """
        logger.info("guardrails.check_action", action_type=action_type)

        # Route zu spezifischen Checks
        if action_type == "delete_documents":
            return await self._check_delete_documents(parameters, company_id, db)
        elif action_type == "approve_payment":
            return await self._check_approve_payment(parameters, company_id, db)
        elif action_type == "bulk_export":
            return await self._check_bulk_export(parameters, company_id, db)
        elif action_type == "auto_approve_invoices":
            return await self._check_auto_approve_invoices(parameters, company_id, db)
        elif action_type == "change_risk_score":
            return await self._check_change_risk_score(parameters, company_id, db)
        else:
            # Unbekannte Aktion - allow aber mit Review
            return GuardrailResult(
                allowed=True,
                reason=f"Aktion '{action_type}' nicht in Guardrails definiert - manuelle Prüfung empfohlen",
                risk_level="medium",
                requires_human_review=True,
                metadata={"action_type": action_type},
            )

    async def _check_delete_documents(
        self,
        parameters: Dict,
        company_id: UUID,
        db: AsyncSession,
    ) -> GuardrailResult:
        """
        Prüft Dokument-Löschung.

        Kritisch bei:
        - Mehr als 10 Dokumente (Bulk)
        - Dokumente mit verknüpften Entities
        - Dokumente mit Invoices

        Args:
            parameters: {document_ids: List[UUID]}
            company_id: Mandanten-ID für Multi-Tenant Isolation
            db: Database session

        Returns:
            GuardrailResult
        """
        document_ids = parameters.get("document_ids", [])

        if not document_ids:
            return GuardrailResult(
                allowed=False,
                reason="Keine Dokumente angegeben",
                risk_level="low",
                requires_human_review=False,
                metadata={},
            )

        # 1. Bulk-Check
        if len(document_ids) > self.BULK_ACTION_THRESHOLD:
            return GuardrailResult(
                allowed=False,
                reason=f"Bulk-Löschung von {len(document_ids)} Dokumenten erfordert manuelle Bestätigung",
                risk_level="high",
                requires_human_review=True,
                metadata={"document_count": len(document_ids)},
            )

        # 2. Prüfe auf verknüpfte Invoices
        # SECURITY FIX: company_id Filter für Multi-Tenant Isolation
        from sqlalchemy import and_
        invoices_query = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.document_id.in_(document_ids),
                InvoiceTracking.company_id == company_id,
            )
        )
        invoices_result = await db.execute(invoices_query)
        invoices = invoices_result.scalars().all()

        if invoices:
            return GuardrailResult(
                allowed=False,
                reason=f"{len(invoices)} Dokumente haben verknüpfte Rechnungen - Löschung könnte Buchführung beeinträchtigen",
                risk_level="high",
                requires_human_review=True,
                metadata={
                    "document_count": len(document_ids),
                    "linked_invoices": len(invoices),
                },
            )

        # 3. Alles OK
        return GuardrailResult(
            allowed=True,
            reason="Dokument-Löschung erlaubt",
            risk_level="low",
            requires_human_review=False,
            metadata={"document_count": len(document_ids)},
        )

    async def _check_approve_payment(
        self,
        parameters: Dict,
        company_id: UUID,
        db: AsyncSession,
    ) -> GuardrailResult:
        """
        Prüft Zahlungs-Freigabe.

        Kritisch bei:
        - Hohen Betraegen (> 10.000 EUR)
        - Neuen/unbekannten Empfängern
        - High-Risk Entities

        Args:
            parameters: {invoice_id: UUID, amount: float, entity_id: UUID}
            company_id: Mandanten-ID für Multi-Tenant Isolation
            db: Database session

        Returns:
            GuardrailResult
        """
        amount = parameters.get("amount", 0)
        entity_id = parameters.get("entity_id")

        # 1. Hoher Betrag
        if amount > self.HIGH_VALUE_THRESHOLD:
            return GuardrailResult(
                allowed=False,
                reason=f"Hoher Betrag ({amount:,.2f} EUR) erfordert manuelle Freigabe",
                risk_level="high",
                requires_human_review=True,
                metadata={"amount": amount},
            )

        # 2. Prüfe Entity Risk Score
        # SECURITY FIX: Validate entity belongs to user's company
        if entity_id:
            from sqlalchemy import and_
            entity_query = select(BusinessEntity).where(
                and_(
                    BusinessEntity.id == entity_id,
                    BusinessEntity.company_id == company_id,
                )
            )
            entity_result = await db.execute(entity_query)
            entity = entity_result.scalar_one_or_none()
            if entity and (entity.risk_score or 0) > self.CRITICAL_RISK_THRESHOLD:
                return GuardrailResult(
                    allowed=False,
                    reason=f"Empfänger hat hohen Risk Score ({entity.risk_score:.0f}) - manuelle Prüfung erforderlich",
                    risk_level="high",
                    requires_human_review=True,
                    metadata={
                        "amount": amount,
                        "risk_score": entity.risk_score,
                        "entity_name": "REDACTED",  # PII-compliant
                    },
                )

        # 3. Alles OK
        return GuardrailResult(
            allowed=True,
            reason="Zahlungs-Freigabe erlaubt",
            risk_level="low",
            requires_human_review=False,
            metadata={"amount": amount},
        )

    async def _check_bulk_export(
        self,
        parameters: Dict,
        company_id: UUID,
        db: AsyncSession,
    ) -> GuardrailResult:
        """
        Prüft Bulk-Datenexport.

        Kritisch bei:
        - Mehr als 100 Dokumente
        - Sensitive Daten-Kategorien

        Args:
            parameters: {document_count: int, include_pii: bool}
            db: Database session

        Returns:
            GuardrailResult
        """
        document_count = parameters.get("document_count", 0)
        include_pii = parameters.get("include_pii", False)

        # 1. Sehr grosse Exports
        if document_count > 100:
            return GuardrailResult(
                allowed=False,
                reason=f"Bulk-Export von {document_count} Dokumenten erfordert Admin-Berechtigung",
                risk_level="high",
                requires_human_review=True,
                metadata={"document_count": document_count},
            )

        # 2. PII-Daten
        if include_pii:
            return GuardrailResult(
                allowed=False,
                reason="Export mit personenbezogenen Daten erfordert GDPR-Bestätigung",
                risk_level="high",
                requires_human_review=True,
                metadata={
                    "document_count": document_count,
                    "includes_pii": True,
                },
            )

        # 3. Alles OK
        return GuardrailResult(
            allowed=True,
            reason="Export erlaubt",
            risk_level="low",
            requires_human_review=False,
            metadata={"document_count": document_count},
        )

    async def _check_auto_approve_invoices(
        self,
        parameters: Dict,
        company_id: UUID,
        db: AsyncSession,
    ) -> GuardrailResult:
        """
        Prüft automatische Rechnungs-Freigabe.

        Kritisch bei:
        - Vielen Rechnungen gleichzeitig
        - Hohen Gesamtbetraegen
        - High-Risk Entities

        Args:
            parameters: {invoice_ids: List[UUID], total_amount: float}
            db: Database session

        Returns:
            GuardrailResult
        """
        invoice_ids = parameters.get("invoice_ids", [])
        total_amount = parameters.get("total_amount", 0)

        # 1. Bulk-Check
        if len(invoice_ids) > self.BULK_ACTION_THRESHOLD:
            return GuardrailResult(
                allowed=False,
                reason=f"Auto-Freigabe von {len(invoice_ids)} Rechnungen erfordert manuelle Prüfung",
                risk_level="high",
                requires_human_review=True,
                metadata={
                    "invoice_count": len(invoice_ids),
                    "total_amount": total_amount,
                },
            )

        # 2. Hoher Gesamtbetrag
        if total_amount > self.HIGH_VALUE_THRESHOLD * 2:  # 20.000 EUR
            return GuardrailResult(
                allowed=False,
                reason=f"Hoher Gesamtbetrag ({total_amount:,.2f} EUR) erfordert manuelle Freigabe",
                risk_level="high",
                requires_human_review=True,
                metadata={
                    "invoice_count": len(invoice_ids),
                    "total_amount": total_amount,
                },
            )

        # 3. Alles OK
        return GuardrailResult(
            allowed=True,
            reason="Auto-Freigabe erlaubt",
            risk_level="low",
            requires_human_review=False,
            metadata={
                "invoice_count": len(invoice_ids),
                "total_amount": total_amount,
            },
        )

    async def _check_change_risk_score(
        self,
        parameters: Dict,
        company_id: UUID,
        db: AsyncSession,
    ) -> GuardrailResult:
        """
        Prüft manuelle Risk-Score-Änderung.

        Kritisch bei:
        - Grossen Spruengen (> 30 Punkte)
        - Ohne Begruendung

        Args:
            parameters: {entity_id: UUID, old_score: float, new_score: float, reason: str}
            company_id: Mandanten-ID für Multi-Tenant Isolation
            db: Database session

        Returns:
            GuardrailResult
        """
        old_score = parameters.get("old_score", 0)
        new_score = parameters.get("new_score", 0)
        reason = parameters.get("reason", "")

        score_change = abs(new_score - old_score)

        # 1. Grosser Sprung ohne Begruendung
        if score_change > 30 and not reason:
            return GuardrailResult(
                allowed=False,
                reason=f"Große Änderung ({score_change:.0f} Punkte) erfordert Begründung",
                risk_level="high",
                requires_human_review=True,
                metadata={
                    "old_score": old_score,
                    "new_score": new_score,
                    "change": score_change,
                },
            )

        # 2. Reduzierung trotz schlechtem Zahlungsverhalten
        # SECURITY FIX: Validate entity belongs to user's company
        entity_id = parameters.get("entity_id")
        if entity_id and new_score < old_score:
            from sqlalchemy import and_
            entity_query = select(BusinessEntity).where(
                and_(
                    BusinessEntity.id == entity_id,
                    BusinessEntity.company_id == company_id,
                )
            )
            entity_result = await db.execute(entity_query)
            entity = entity_result.scalar_one_or_none()
            if entity:
                risk_factors = entity.risk_factors or {}
                default_rate = risk_factors.get("default_rate", 0)

                if default_rate > 0.15:  # 15% Ausfallrate
                    return GuardrailResult(
                        allowed=False,
                        reason=f"Risk-Score-Reduzierung trotz hoher Ausfallrate ({default_rate*100:.1f}%) - manuelle Prüfung erforderlich",
                        risk_level="high",
                        requires_human_review=True,
                        metadata={
                            "old_score": old_score,
                            "new_score": new_score,
                            "default_rate": default_rate,
                        },
                    )

        # 3. Alles OK
        return GuardrailResult(
            allowed=True,
            reason="Risk-Score-Änderung erlaubt",
            risk_level="low",
            requires_human_review=False,
            metadata={
                "old_score": old_score,
                "new_score": new_score,
                "change": score_change,
            },
        )
