# -*- coding: utf-8 -*-
"""Document Context Aggregator Service.

Aggregiert Cross-Module Kontext (Risk, Chains, Payments, Skonto, Pending Actions)
für ein einzelnes Dokument in einer Response.
"""

import asyncio
import structlog
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.models import Document, BusinessEntity, InvoiceTracking
from app.services.risk_scoring_service import RiskScoringService
from app.services.document_chain_service import DocumentChainService
from app.services.banking.skonto_service import SkontoService
from app.services.orchestration.cross_module_orchestrator import (
    CrossModuleOrchestrator,
    OrchestrationAction,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# Response Dataclasses
# ============================================================================

@dataclass
class EntityContext:
    """Entitäts-Kontext mit Risk-Scoring."""
    id: str
    name: str
    entity_type: str  # "customer" oder "supplier"
    risk_score: Optional[float] = None
    risk_level: Optional[str] = None  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    risk_trend: Optional[str] = None  # "IMPROVING", "STABLE", "WORSENING"


@dataclass
class ChainContext:
    """Auftragsketten-Kontext."""
    chain_id: Optional[str] = None
    position: Optional[int] = None
    total_docs: int = 0
    is_complete: bool = False
    open_discrepancies: int = 0
    has_quote: bool = False
    has_order: bool = False
    has_delivery_note: bool = False
    has_invoice: bool = False
    has_credit_note: bool = False


@dataclass
class PaymentContext:
    """Zahlungs-Kontext mit Skonto-Informationen."""
    status: str = "unknown"  # "paid", "partial", "open", "overdue"
    paid_amount: Optional[Decimal] = None
    total_amount: Optional[Decimal] = None
    skonto_available: bool = False
    skonto_deadline: Optional[date] = None
    skonto_amount: Optional[Decimal] = None
    skonto_percent: Optional[float] = None
    days_overdue: int = 0


@dataclass
class PendingAction:
    """Ausstehende Orchestrierungs-Aktion."""
    id: str
    action_type: str
    priority: str
    reason: str
    impact_description: str


@dataclass
class RelatedDocument:
    """Verwandtes Dokument."""
    id: str
    filename: str
    document_type: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class DocumentContext:
    """Aggregierter Cross-Module Kontext für ein Dokument."""
    entity: Optional[EntityContext] = None
    chain: Optional[ChainContext] = None
    payment: Optional[PaymentContext] = None
    related_documents: List[RelatedDocument] = field(default_factory=list)
    pending_actions: List[PendingAction] = field(default_factory=list)


# ============================================================================
# Service
# ============================================================================

class DocumentContextAggregatorService:
    """Aggregiert Cross-Module Kontext für ein Dokument."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_context(self, document_id: UUID, company_id: UUID) -> DocumentContext:
        """
        Aggregiert Kontext für ein Dokument.

        Alle Sub-Queries laufen parallel für optimale Performance.

        Args:
            document_id: Dokument-ID
            company_id: Company-ID des aktuellen Benutzers

        Returns:
            DocumentContext mit allen verfügbaren Kontextinformationen
        """
        # Zuerst Dokument laden um Entity-Referenz zu erhalten
        doc = await self._load_document(document_id, company_id)
        if not doc:
            logger.warning("document_not_found", document_id=str(document_id))
            return DocumentContext()

        # Alle Kontext-Sammlungen parallel ausführen
        entity_ctx, chain_ctx, payment_ctx, related, actions = await asyncio.gather(
            self._get_entity_context(doc),
            self._get_chain_context(document_id, company_id),
            self._get_payment_context(doc),
            self._get_related_documents(doc, company_id),
            self._get_pending_actions(doc),
            return_exceptions=True,
        )

        # Exceptions gracefully behandeln - loggen und None/empty zurückgeben
        result = DocumentContext()

        if isinstance(entity_ctx, EntityContext):
            result.entity = entity_ctx
        elif isinstance(entity_ctx, Exception):
            logger.warning("entity_context_failed", error=str(entity_ctx))

        if isinstance(chain_ctx, ChainContext):
            result.chain = chain_ctx
        elif isinstance(chain_ctx, Exception):
            logger.warning("chain_context_failed", error=str(chain_ctx))

        if isinstance(payment_ctx, PaymentContext):
            result.payment = payment_ctx
        elif isinstance(payment_ctx, Exception):
            logger.warning("payment_context_failed", error=str(payment_ctx))

        if isinstance(related, list):
            result.related_documents = related
        elif isinstance(related, Exception):
            logger.warning("related_docs_failed", error=str(related))

        if isinstance(actions, list):
            result.pending_actions = actions
        elif isinstance(actions, Exception):
            logger.warning("pending_actions_failed", error=str(actions))

        return result

    async def _load_document(
        self, document_id: UUID, company_id: UUID
    ) -> Optional[Document]:
        """Laedt Dokument mit Company-Filter."""
        try:
            stmt = (
                select(Document)
                .where(Document.id == document_id)
                .where(Document.company_id == company_id)
            )
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error("load_document_failed", error=str(e))
            return None

    async def _get_entity_context(self, doc: Document) -> Optional[EntityContext]:
        """
        Laedt Entitäts-Kontext mit Risk-Scoring.

        Risk-Score wird aus dem JSONB-Feld der BusinessEntity gelesen.
        Risk-Level wird basierend auf Schwellenwerten berechnet:
        - <25: LOW
        - <50: MEDIUM
        - <75: HIGH
        - >=75: CRITICAL
        """
        if not doc.business_entity_id:
            return None

        try:
            stmt = select(BusinessEntity).where(
                BusinessEntity.id == doc.business_entity_id
            )
            result = await self.db.execute(stmt)
            entity = result.scalar_one_or_none()

            if not entity:
                return None

            # Risk-Score aus JSONB-Feld extrahieren
            risk_data = entity.risk_score or {}
            risk_score = risk_data.get("score")
            risk_trend = risk_data.get("trend")

            # Risk-Level basierend auf Score berechnen
            risk_level = None
            if risk_score is not None:
                if risk_score < 25:
                    risk_level = "LOW"
                elif risk_score < 50:
                    risk_level = "MEDIUM"
                elif risk_score < 75:
                    risk_level = "HIGH"
                else:
                    risk_level = "CRITICAL"

            return EntityContext(
                id=str(entity.id),
                name=entity.name,
                entity_type=entity.entity_type,
                risk_score=risk_score,
                risk_level=risk_level,
                risk_trend=risk_trend,
            )

        except Exception as e:
            logger.error("get_entity_context_failed", error=str(e))
            raise

    async def _get_chain_context(
        self, document_id: UUID, company_id: UUID
    ) -> ChainContext:
        """
        Laedt Auftragsketten-Kontext.

        Versucht eine Kette über den DocumentChainService zu finden.
        Falls keine Kette gefunden wird, werden Default-Werte zurückgegeben.
        """
        try:
            chain_service = DocumentChainService(self.db)

            # Versuche Kette für dieses Dokument zu finden
            chain = await chain_service.get_chain_for_document(
                document_id=document_id,
                company_id=company_id
            )

            if not chain:
                return ChainContext()

            # Position des aktuellen Dokuments in der Kette finden
            position = None
            for doc in chain.documents:
                if doc.id == document_id:
                    position = doc.chain_position
                    break

            return ChainContext(
                chain_id=chain.chain_id,
                position=position,
                total_docs=chain.document_count,
                is_complete=chain.is_complete,
                open_discrepancies=chain.open_discrepancies,
                has_quote=chain.has_quote,
                has_order=chain.has_order,
                has_delivery_note=chain.has_delivery_note,
                has_invoice=chain.has_invoice,
                has_credit_note=chain.has_credit_note,
            )

        except Exception as e:
            logger.error("get_chain_context_failed", error=str(e))
            raise

    async def _get_payment_context(self, doc: Document) -> PaymentContext:
        """
        Laedt Zahlungs-Kontext mit Skonto-Informationen.

        Prüft InvoiceTracking für Zahlungsinformationen und
        SkontoService für Skonto-Daten.
        """
        try:
            # InvoiceTracking laden
            stmt = select(InvoiceTracking).where(
                InvoiceTracking.document_id == doc.id
            )
            result = await self.db.execute(stmt)
            tracking = result.scalar_one_or_none()

            if not tracking:
                return PaymentContext()

            # Zahlungsstatus bestimmen
            status = "unknown"
            paid_amount = None
            total_amount = Decimal(str(tracking.amount)) if tracking.amount else None
            days_overdue = 0

            if tracking.status:
                status_mapping = {
                    "paid": "paid",
                    "partial": "partial",
                    "open": "open",
                    "overdue": "overdue",
                }
                status = status_mapping.get(tracking.status, "unknown")

            if tracking.paid_amount is not None:
                paid_amount = Decimal(str(tracking.paid_amount))

            # Überfälligkeitstage berechnen
            if tracking.due_date and status in ["open", "overdue"]:
                from app.core.datetime_utils import utc_now
                now = utc_now()
                if now > tracking.due_date:
                    days_overdue = (now - tracking.due_date).days

            # Skonto-Informationen laden
            skonto_available = False
            skonto_deadline = None
            skonto_amount = None
            skonto_percent = None

            if total_amount and tracking.invoice_date:
                try:
                    skonto_service = SkontoService(self.db)
                    skonto_calc = await skonto_service.calculate_skonto(
                        invoice_amount=total_amount,
                        invoice_date=tracking.invoice_date,
                        skonto_percentage=2.0,  # Standard-Konditionen
                        skonto_days=10,
                        net_days=30,
                    )

                    if skonto_calc and not skonto_calc.is_expired:
                        skonto_available = True
                        skonto_deadline = skonto_calc.skonto_deadline.date()
                        skonto_amount = skonto_calc.skonto_amount
                        skonto_percent = skonto_calc.skonto_percentage

                except Exception as e:
                    logger.warning("skonto_calculation_failed", error=str(e))

            return PaymentContext(
                status=status,
                paid_amount=paid_amount,
                total_amount=total_amount,
                skonto_available=skonto_available,
                skonto_deadline=skonto_deadline,
                skonto_amount=skonto_amount,
                skonto_percent=skonto_percent,
                days_overdue=days_overdue,
            )

        except Exception as e:
            logger.error("get_payment_context_failed", error=str(e))
            raise

    async def _get_related_documents(
        self, doc: Document, company_id: UUID
    ) -> List[RelatedDocument]:
        """
        Laedt verwandte Dokumente.

        Findet andere Dokumente mit derselben business_entity_id,
        limitiert auf 10, sortiert nach created_at desc.
        """
        if not doc.business_entity_id:
            return []

        try:
            stmt = (
                select(Document)
                .where(Document.business_entity_id == doc.business_entity_id)
                .where(Document.company_id == company_id)
                .where(Document.id != doc.id)  # Aktuelles Dokument ausschließen
                .order_by(Document.created_at.desc())
                .limit(10)
            )
            result = await self.db.execute(stmt)
            documents = result.scalars().all()

            return [
                RelatedDocument(
                    id=str(d.id),
                    filename=d.filename,
                    document_type=d.document_type,
                    created_at=d.created_at.isoformat() if d.created_at else None,
                )
                for d in documents
            ]

        except Exception as e:
            logger.error("get_related_documents_failed", error=str(e))
            raise

    async def _get_pending_actions(self, doc: Document) -> List[PendingAction]:
        """
        Laedt ausstehende Orchestrierungs-Aktionen.

        Wenn der Orchestrator verfügbar ist, werden ausstehende Aktionen
        für die Entität des Dokuments abgerufen.
        """
        if not doc.business_entity_id:
            return []

        try:
            orchestrator = CrossModuleOrchestrator.get_instance()

            # Hole ausstehende Aktionen für diese Entität
            all_pending = orchestrator.get_pending_actions()

            # Filtere nach target_entity_id
            entity_actions = [
                action
                for action in all_pending
                if action.target_entity_id == doc.business_entity_id
                and action.status == "pending"
            ]

            return [
                PendingAction(
                    id=str(action.id),
                    action_type=action.action_type.value,
                    priority=action.priority.value,
                    reason=action.reason,
                    impact_description=action.impact_description,
                )
                for action in entity_actions
            ]

        except Exception as e:
            # Orchestrator könnte nicht initialisiert sein
            logger.info("pending_actions_unavailable", error=str(e))
            return []
