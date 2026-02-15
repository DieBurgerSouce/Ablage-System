"""
Invoice Pipeline Service.

Vollautomatischer Rechnungsworkflow (Feature #3):
1. OCR-Qualitaet pruefen
2. Entity-Linking durchfuehren
3. Dokument kategorisieren
4. Auto-Approval pruefen
5. Bei Genehmigung: Als zahlungsbereit markieren
6. Bei Ablehnung: Eskalation mit Details

Pipeline-Status wird fuer Audit-Trail protokolliert.
Nutzt bestehende Services:
- auto_approval_service.py
- document_entity_linker_service.py
- autonomous_actions_service.py
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import select, and_, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log
from app.db.models import (
    Document,
    BusinessEntity,
    InvoiceTracking,
    AIDecision,
    User,
    Company,
)
from app.services.approval.auto_approval_service import (
    AutoApprovalService,
    AutoApprovalConfig,
    AutoApprovalDecision,
)
from app.services.document_entity_linker_service import (
    DocumentEntityLinkerService,
    LinkingResult,
)
from app.services.ai.autonomous_actions_service import (
    AutonomousActionsService,
    AutonomyConfig,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# Enums und Konstanten
# ============================================================================


class PipelineStage(str, Enum):
    """Pipeline-Stufen."""

    OCR_COMPLETE = "ocr_complete"
    ENTITY_LINKED = "entity_linked"
    CATEGORIZED = "categorized"
    APPROVED = "approved"
    PAYMENT_READY = "payment_ready"
    ESCALATED = "escalated"


class PipelineStatus(str, Enum):
    """Pipeline-Ergebnis-Status."""

    SUCCESS = "success"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"
    ESCALATED = "escalated"


# OCR-Konfidenz-Schwelle fuer automatische Verarbeitung
DEFAULT_OCR_CONFIDENCE_THRESHOLD = 0.85


# ============================================================================
# Datenklassen
# ============================================================================


@dataclass
class PipelineResult:
    """Ergebnis einer Pipeline-Ausfuehrung."""

    document_id: uuid.UUID
    stage: PipelineStage
    status: PipelineStatus
    confidence: float  # 0-1
    actions_taken: List[str]  # Deutsche Beschreibungen
    next_action: Optional[str] = None  # Was als naechstes passieren muss
    processing_time_ms: int = 0
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineStats:
    """Statistiken fuer die Pipeline."""

    total_processed: int
    successful: int
    needs_review: int
    failed: int
    escalated: int
    avg_processing_time_ms: float
    auto_approval_rate: float  # %
    entity_linking_rate: float  # %
    avg_confidence: float


# ============================================================================
# Invoice Pipeline Service
# ============================================================================


class InvoicePipelineService:
    """Vollautomatischer Rechnungsworkflow.

    Orchestriert alle Schritte von OCR bis Zahlungsfreigabe:
    1. OCR-Qualitaet validieren
    2. Entity automatisch verknuepfen
    3. Dokument kategorisieren
    4. Auto-Approval pruefen
    5. Status setzen (zahlungsbereit oder Review)

    Alle Schritte werden fuer Audit-Trail protokolliert.
    """

    def __init__(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        auto_approval_config: Optional[AutoApprovalConfig] = None,
        autonomy_config: Optional[AutonomyConfig] = None,
    ):
        """Initialisiert den Pipeline-Service.

        Args:
            db: Async Database Session
            company_id: Mandanten-ID fuer Multi-Tenancy
            auto_approval_config: Optionale Auto-Approval-Konfiguration
            autonomy_config: Optionale Autonomie-Konfiguration
        """
        self.db = db
        self.company_id = company_id

        # Services initialisieren
        self.auto_approval_service = AutoApprovalService(
            db=db,
            config=auto_approval_config,
        )
        self.entity_linker = DocumentEntityLinkerService(db=db)
        self.autonomous_actions = AutonomousActionsService(
            db=db,
            config=autonomy_config,
        )

    async def process_invoice(
        self,
        document_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
    ) -> PipelineResult:
        """Fuehrt die vollstaendige Pipeline fuer eine Rechnung aus.

        Args:
            document_id: ID des zu verarbeitenden Dokuments
            user_id: Optionale User-ID fuer Audit-Trail

        Returns:
            PipelineResult mit Status und Details
        """
        start_time = datetime.now()
        actions_taken: List[str] = []

        try:
            # 1. Dokument laden und validieren
            doc = await self._load_document(document_id)
            if not doc:
                return PipelineResult(
                    document_id=document_id,
                    stage=PipelineStage.OCR_COMPLETE,
                    status=PipelineStatus.FAILED,
                    confidence=0.0,
                    actions_taken=actions_taken,
                    error_message="Dokument nicht gefunden",
                )

            # Multi-Tenancy: Company-ID pruefen
            if doc.company_id != self.company_id:
                return PipelineResult(
                    document_id=document_id,
                    stage=PipelineStage.OCR_COMPLETE,
                    status=PipelineStatus.FAILED,
                    confidence=0.0,
                    actions_taken=actions_taken,
                    error_message="Keine Berechtigung fuer dieses Dokument",
                )

            # 2. OCR-Qualitaet pruefen
            ocr_confidence = await self._check_ocr_quality(doc)
            if ocr_confidence < DEFAULT_OCR_CONFIDENCE_THRESHOLD:
                actions_taken.append(
                    f"OCR-Qualitaet zu niedrig ({ocr_confidence:.1%})"
                )
                return PipelineResult(
                    document_id=document_id,
                    stage=PipelineStage.OCR_COMPLETE,
                    status=PipelineStatus.NEEDS_REVIEW,
                    confidence=ocr_confidence,
                    actions_taken=actions_taken,
                    next_action="Manuelle OCR-Korrektur erforderlich",
                )

            actions_taken.append(f"OCR-Qualitaet validiert ({ocr_confidence:.1%})")

            # 3. Entity-Linking durchfuehren (falls noch nicht verknuepft)
            if not doc.entity_id:
                linking_result = await self._perform_entity_linking(doc)
                if linking_result and linking_result.linked_count > 0:
                    actions_taken.append(
                        f"Entity automatisch verknuepft (Confidence: {linking_result.details[0].get('confidence', 0):.1%})"
                    )
                    # Dokument neu laden nach Linking
                    doc = await self._load_document(document_id)
                else:
                    actions_taken.append("Keine passende Entity gefunden")

            # 4. Dokument kategorisieren (falls noch nicht kategorisiert)
            if not doc.category or doc.category == "uncategorized":
                category_result = await self._categorize_document(doc)
                if category_result:
                    actions_taken.append(
                        f"Dokument kategorisiert als '{category_result}'"
                    )
                else:
                    actions_taken.append("Automatische Kategorisierung fehlgeschlagen")

            # 5. Auto-Approval pruefen
            approval_result = await self._check_auto_approval(doc)

            if approval_result.decision == AutoApprovalDecision.AUTO_APPROVED:
                # Dokument als genehmigt markieren
                await self._mark_as_approved(doc, approval_result, user_id)
                actions_taken.append(
                    f"Automatisch genehmigt: {approval_result.explanation}"
                )

                # Status auf PAYMENT_READY setzen
                await self._mark_payment_ready(doc)
                actions_taken.append("Als zahlungsbereit markiert")

                # Erfolgreiche Pipeline
                processing_time = int(
                    (datetime.now() - start_time).total_seconds() * 1000
                )

                return PipelineResult(
                    document_id=document_id,
                    stage=PipelineStage.PAYMENT_READY,
                    status=PipelineStatus.SUCCESS,
                    confidence=approval_result.confidence,
                    actions_taken=actions_taken,
                    next_action="Zahlung kann durchgefuehrt werden",
                    processing_time_ms=processing_time,
                    metadata={
                        "approval_reasons": approval_result.reasons,
                        "matched_rules": approval_result.matched_rules,
                    },
                )

            elif approval_result.decision == AutoApprovalDecision.REQUIRES_REVIEW:
                # Manueller Review erforderlich
                actions_taken.append(
                    f"Manuelle Pruefung erforderlich: {approval_result.explanation}"
                )

                processing_time = int(
                    (datetime.now() - start_time).total_seconds() * 1000
                )

                return PipelineResult(
                    document_id=document_id,
                    stage=PipelineStage.APPROVED,
                    status=PipelineStatus.NEEDS_REVIEW,
                    confidence=approval_result.confidence,
                    actions_taken=actions_taken,
                    next_action="Manuelle Genehmigung durch Approver erforderlich",
                    processing_time_ms=processing_time,
                    metadata={
                        "suggested_approvers": approval_result.suggested_approvers or [],
                    },
                )

            else:
                # Eskalation
                await self._escalate_document(doc, approval_result)
                actions_taken.append(
                    f"Eskaliert: {approval_result.escalation_reason or 'Unbekannter Grund'}"
                )

                processing_time = int(
                    (datetime.now() - start_time).total_seconds() * 1000
                )

                return PipelineResult(
                    document_id=document_id,
                    stage=PipelineStage.ESCALATED,
                    status=PipelineStatus.ESCALATED,
                    confidence=approval_result.confidence,
                    actions_taken=actions_taken,
                    next_action="Admin-Review erforderlich",
                    processing_time_ms=processing_time,
                    metadata={
                        "escalation_reason": approval_result.escalation_reason,
                    },
                )

        except Exception as e:
            logger.error(
                "invoice_pipeline_error",
                document_id=str(document_id),
                **safe_error_log(e),
            )

            processing_time = int((datetime.now() - start_time).total_seconds() * 1000)

            return PipelineResult(
                document_id=document_id,
                stage=PipelineStage.OCR_COMPLETE,
                status=PipelineStatus.FAILED,
                confidence=0.0,
                actions_taken=actions_taken,
                error_message=f"Pipeline-Fehler: {str(e)}",
                processing_time_ms=processing_time,
            )

    async def get_pipeline_status(
        self,
        document_id: uuid.UUID,
    ) -> PipelineResult:
        """Ruft den aktuellen Pipeline-Status ab.

        Args:
            document_id: ID des Dokuments

        Returns:
            Aktueller PipelineResult
        """
        doc = await self._load_document(document_id)

        if not doc:
            return PipelineResult(
                document_id=document_id,
                stage=PipelineStage.OCR_COMPLETE,
                status=PipelineStatus.FAILED,
                confidence=0.0,
                actions_taken=["Dokument nicht gefunden"],
            )

        # Status aus Dokument ableiten
        actions_taken: List[str] = []

        # OCR Status
        ocr_confidence = await self._check_ocr_quality(doc)
        stage = PipelineStage.OCR_COMPLETE
        actions_taken.append(f"OCR abgeschlossen ({ocr_confidence:.1%})")

        # Entity Status
        if doc.entity_id:
            stage = PipelineStage.ENTITY_LINKED
            actions_taken.append("Entity verknuepft")

        # Kategorie Status
        if doc.category and doc.category != "uncategorized":
            stage = PipelineStage.CATEGORIZED
            actions_taken.append(f"Kategorisiert als '{doc.category}'")

        # Genehmigungsstatus aus InvoiceTracking
        invoice = await self._get_invoice_tracking(document_id)
        if invoice:
            if invoice.approval_status == "approved":
                stage = PipelineStage.APPROVED
                actions_taken.append("Genehmigt")

                if invoice.payment_status == "ready" or invoice.is_payment_ready:
                    stage = PipelineStage.PAYMENT_READY
                    actions_taken.append("Zahlungsbereit")

        # Status bestimmen
        if stage == PipelineStage.PAYMENT_READY:
            status = PipelineStatus.SUCCESS
            next_action = "Zahlung kann durchgefuehrt werden"
        elif stage in (PipelineStage.APPROVED, PipelineStage.CATEGORIZED):
            status = PipelineStatus.NEEDS_REVIEW
            next_action = "Manuelle Genehmigung erforderlich"
        else:
            status = PipelineStatus.NEEDS_REVIEW
            next_action = "Pipeline weiterfuehren"

        return PipelineResult(
            document_id=document_id,
            stage=stage,
            status=status,
            confidence=ocr_confidence,
            actions_taken=actions_taken,
            next_action=next_action,
        )

    async def approve_and_continue(
        self,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> PipelineResult:
        """Manuell genehmigen und Pipeline fortsetzen.

        Args:
            document_id: ID des Dokuments
            user_id: ID des genehmigenden Users

        Returns:
            PipelineResult nach Genehmigung
        """
        start_time = datetime.now()
        actions_taken: List[str] = ["Manuelle Genehmigung durch User"]

        try:
            doc = await self._load_document(document_id)
            if not doc:
                return PipelineResult(
                    document_id=document_id,
                    stage=PipelineStage.OCR_COMPLETE,
                    status=PipelineStatus.FAILED,
                    confidence=0.0,
                    actions_taken=actions_taken,
                    error_message="Dokument nicht gefunden",
                )

            # Multi-Tenancy pruefen
            if doc.company_id != self.company_id:
                return PipelineResult(
                    document_id=document_id,
                    stage=PipelineStage.OCR_COMPLETE,
                    status=PipelineStatus.FAILED,
                    confidence=0.0,
                    actions_taken=actions_taken,
                    error_message="Keine Berechtigung fuer dieses Dokument",
                )

            # Genehmigung durchfuehren
            approval_result = await self._manual_approval(doc, user_id)
            actions_taken.append("Dokument genehmigt")

            # Als zahlungsbereit markieren
            await self._mark_payment_ready(doc)
            actions_taken.append("Als zahlungsbereit markiert")

            processing_time = int((datetime.now() - start_time).total_seconds() * 1000)

            return PipelineResult(
                document_id=document_id,
                stage=PipelineStage.PAYMENT_READY,
                status=PipelineStatus.SUCCESS,
                confidence=1.0,  # Manuelle Genehmigung = volle Confidence
                actions_taken=actions_taken,
                next_action="Zahlung kann durchgefuehrt werden",
                processing_time_ms=processing_time,
            )

        except Exception as e:
            logger.error(
                "manual_approval_error",
                document_id=str(document_id),
                user_id=str(user_id),
                **safe_error_log(e),
            )

            processing_time = int((datetime.now() - start_time).total_seconds() * 1000)

            return PipelineResult(
                document_id=document_id,
                stage=PipelineStage.APPROVED,
                status=PipelineStatus.FAILED,
                confidence=0.0,
                actions_taken=actions_taken,
                error_message=f"Genehmigung fehlgeschlagen: {str(e)}",
                processing_time_ms=processing_time,
            )

    async def get_pipeline_stats(
        self,
        days: int = 30,
    ) -> PipelineStats:
        """Ruft Pipeline-Statistiken ab.

        Args:
            days: Anzahl Tage fuer Statistik-Zeitraum

        Returns:
            PipelineStats mit Metriken
        """
        start_date = utc_now() - timedelta(days=days)

        # Dokumente aus dem Zeitraum
        query = select(Document).where(
            and_(
                Document.company_id == self.company_id,
                Document.created_at >= start_date,
                Document.document_type.in_(["invoice", "recurring_invoice", "receipt"]),
            )
        )
        result = await self.db.execute(query)
        documents = result.scalars().all()

        if not documents:
            return PipelineStats(
                total_processed=0,
                successful=0,
                needs_review=0,
                failed=0,
                escalated=0,
                avg_processing_time_ms=0.0,
                auto_approval_rate=0.0,
                entity_linking_rate=0.0,
                avg_confidence=0.0,
            )

        # Statistiken berechnen
        total = len(documents)
        successful = 0
        needs_review = 0
        failed = 0
        escalated = 0
        auto_approved = 0
        entity_linked = 0
        total_confidence = 0.0
        total_processing_time_ms = 0
        processing_time_count = 0

        for doc in documents:
            # OCR-Confidence
            if hasattr(doc, "ocr_confidence") and doc.ocr_confidence:
                total_confidence += doc.ocr_confidence

            # Processing time
            if doc.processing_duration_ms is not None:
                total_processing_time_ms += doc.processing_duration_ms
                processing_time_count += 1

            # Entity-Linking
            if doc.entity_id:
                entity_linked += 1

            # Invoice-Tracking fuer Status
            invoice = await self._get_invoice_tracking(doc.id)
            if invoice:
                if invoice.approval_status == "approved":
                    if invoice.is_payment_ready or invoice.payment_status == "ready":
                        successful += 1
                        if invoice.auto_approved:
                            auto_approved += 1
                    else:
                        needs_review += 1
                elif invoice.approval_status == "rejected":
                    failed += 1
                elif invoice.approval_status == "escalated":
                    escalated += 1
                else:
                    needs_review += 1

        avg_confidence = total_confidence / total if total > 0 else 0.0
        auto_approval_rate = (auto_approved / total * 100) if total > 0 else 0.0
        entity_linking_rate = (entity_linked / total * 100) if total > 0 else 0.0

        return PipelineStats(
            total_processed=total,
            successful=successful,
            needs_review=needs_review,
            failed=failed,
            escalated=escalated,
            avg_processing_time_ms=(
                total_processing_time_ms / processing_time_count
                if processing_time_count > 0
                else 0.0
            ),
            auto_approval_rate=auto_approval_rate,
            entity_linking_rate=entity_linking_rate,
            avg_confidence=avg_confidence,
        )

    # =========================================================================
    # Private Helper Methods
    # =========================================================================

    async def _load_document(self, document_id: uuid.UUID) -> Optional[Document]:
        """Laedt ein Dokument aus der Datenbank."""
        query = select(Document).where(Document.id == document_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _get_invoice_tracking(
        self, document_id: uuid.UUID
    ) -> Optional[InvoiceTracking]:
        """Laedt InvoiceTracking fuer ein Dokument."""
        query = select(InvoiceTracking).where(InvoiceTracking.document_id == document_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _check_ocr_quality(self, doc: Document) -> float:
        """Prueft die OCR-Qualitaet eines Dokuments.

        Returns:
            Confidence-Score (0.0 - 1.0)
        """
        # Aus Document-Metadaten oder OCR-Confidence-Feld
        if hasattr(doc, "ocr_confidence") and doc.ocr_confidence:
            return doc.ocr_confidence

        # Fallback: Aus extracted_data
        if doc.extracted_data and isinstance(doc.extracted_data, dict):
            confidence = doc.extracted_data.get("ocr_confidence")
            if confidence is not None:
                return float(confidence)

        # Default: Moderate Confidence
        return 0.80

    async def _perform_entity_linking(self, doc: Document) -> Optional[LinkingResult]:
        """Fuehrt Entity-Linking durch.

        Returns:
            LinkingResult oder None bei Fehler
        """
        try:
            result = await self.entity_linker.link_single_document(doc.id)
            return result
        except Exception as e:
            logger.warning(
                "entity_linking_failed",
                document_id=str(doc.id),
                **safe_error_log(e),
            )
            return None

    async def _categorize_document(self, doc: Document) -> Optional[str]:
        """Kategorisiert ein Dokument automatisch.

        Returns:
            Kategorie-Name oder None
        """
        # Nutzt autonomous_actions_service fuer Kategorisierung
        try:
            # Vereinfachte Logik - in Praxis: KI-basiert
            extracted = doc.extracted_data or {}

            # Rechnung-Keywords
            if any(
                keyword in str(extracted).lower()
                for keyword in ["rechnung", "invoice", "betrag", "total"]
            ):
                # Kategorie setzen
                doc.category = "invoice"
                await self.db.commit()
                await self.db.refresh(doc)
                return "invoice"

            # Beleg-Keywords
            if any(
                keyword in str(extracted).lower()
                for keyword in ["quittung", "receipt", "kassenbon"]
            ):
                doc.category = "receipt"
                await self.db.commit()
                await self.db.refresh(doc)
                return "receipt"

            return None

        except Exception as e:
            logger.warning(
                "categorization_failed",
                document_id=str(doc.id),
                **safe_error_log(e),
            )
            return None

    async def _check_auto_approval(self, doc: Document) -> Any:
        """Prueft Auto-Approval fuer ein Dokument.

        Returns:
            AutoApprovalResult
        """
        # Nutzt auto_approval_service
        return await self.auto_approval_service.evaluate_document(doc)

    async def _mark_as_approved(
        self,
        doc: Document,
        approval_result: Any,
        user_id: Optional[uuid.UUID],
    ) -> None:
        """Markiert ein Dokument als genehmigt."""
        # InvoiceTracking erstellen/aktualisieren
        invoice = await self._get_invoice_tracking(doc.id)

        if not invoice:
            # Neues InvoiceTracking erstellen
            invoice = InvoiceTracking(
                id=uuid.uuid4(),
                document_id=doc.id,
                company_id=doc.company_id,
                approval_status="approved",
                auto_approved=True,
                approved_at=utc_now(),
                approved_by=user_id,
                approval_metadata={
                    "rules": approval_result.matched_rules,
                    "confidence": approval_result.confidence,
                    "reasons": [r.value for r in approval_result.reasons],
                },
            )
            self.db.add(invoice)
        else:
            # Bestehendes InvoiceTracking aktualisieren
            invoice.approval_status = "approved"
            invoice.auto_approved = True
            invoice.approved_at = utc_now()
            invoice.approved_by = user_id

        await self.db.commit()

    async def _manual_approval(self, doc: Document, user_id: uuid.UUID) -> None:
        """Fuehrt manuelle Genehmigung durch."""
        invoice = await self._get_invoice_tracking(doc.id)

        if not invoice:
            # Neues InvoiceTracking
            invoice = InvoiceTracking(
                id=uuid.uuid4(),
                document_id=doc.id,
                company_id=doc.company_id,
                approval_status="approved",
                auto_approved=False,
                approved_at=utc_now(),
                approved_by=user_id,
            )
            self.db.add(invoice)
        else:
            invoice.approval_status = "approved"
            invoice.auto_approved = False
            invoice.approved_at = utc_now()
            invoice.approved_by = user_id

        await self.db.commit()

    async def _mark_payment_ready(self, doc: Document) -> None:
        """Markiert ein Dokument als zahlungsbereit."""
        invoice = await self._get_invoice_tracking(doc.id)

        if invoice:
            invoice.is_payment_ready = True
            invoice.payment_status = "ready"
            await self.db.commit()

    async def _escalate_document(self, doc: Document, approval_result: Any) -> None:
        """Eskaliert ein Dokument."""
        invoice = await self._get_invoice_tracking(doc.id)

        if not invoice:
            invoice = InvoiceTracking(
                id=uuid.uuid4(),
                document_id=doc.id,
                company_id=doc.company_id,
                approval_status="escalated",
                escalation_reason=approval_result.escalation_reason,
                escalated_at=utc_now(),
            )
            self.db.add(invoice)
        else:
            invoice.approval_status = "escalated"
            invoice.escalation_reason = approval_result.escalation_reason
            invoice.escalated_at = utc_now()

        await self.db.commit()


# ============================================================================
# Service Factory
# ============================================================================


def get_invoice_pipeline_service(
    db: AsyncSession,
    company_id: uuid.UUID,
) -> InvoicePipelineService:
    """Factory-Funktion fuer InvoicePipelineService.

    Args:
        db: Async Database Session
        company_id: Mandanten-ID

    Returns:
        InvoicePipelineService-Instanz
    """
    return InvoicePipelineService(db=db, company_id=company_id)
