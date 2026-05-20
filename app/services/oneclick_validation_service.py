"""
One-Click Validierungs-Service.

Schnelle Entscheidungs-Queue für mobile und Desktop-Nutzung.
Optimiert für "maximal 2 Sekunden pro Entscheidung".

Validierungstypen:
- Rechnungsfreigabe: "Betrag X an Lieferant Y - OK?"
- Ablage-Vorschlag: "Dokument -> Kunde X, Kategorie Y - stimmt?"
- Duplikat-Erkennung: "Zusammenführen?"
- Stammdaten-Korrektur: "Adresse aktualisieren?"

UI-Patterns:
- Swipe-fähig auf Mobile (links=ablehnen, rechts=genehmigen)
- Keyboard-Shortcuts am Desktop (Y/N, Enter, 1-9)
- Batch-Verarbeitung in Queue
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple
from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log

import structlog
from sqlalchemy import select, func, and_, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (

    ValidationQueueItem,
    Document,
    BusinessEntity,
    InvoiceTracking,
    User,
    ValidationStatus,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# Enums and Data Classes
# ============================================================================


class OneClickActionType(str, Enum):
    """Typen von One-Click-Aktionen."""

    INVOICE_APPROVAL = "invoice_approval"
    FILING_SUGGESTION = "filing_suggestion"
    DUPLICATE_MERGE = "duplicate_merge"
    MASTER_DATA_UPDATE = "master_data_update"
    OCR_CORRECTION = "ocr_correction"
    ENTITY_ASSIGNMENT = "entity_assignment"


class SwipeDirection(str, Enum):
    """Swipe-Richtungen für Mobile."""

    LEFT = "left"  # Ablehnen
    RIGHT = "right"  # Genehmigen
    UP = "up"  # Überspringen
    DOWN = "down"  # Details anzeigen


@dataclass
class OneClickItem:
    """Ein Item in der One-Click-Queue."""

    id: uuid.UUID
    action_type: OneClickActionType
    priority: int
    created_at: datetime

    # Anzeige-Informationen
    title: str
    subtitle: str
    description: str

    # Haupt-Entscheidungsfrage
    question: str

    # Optionen
    primary_action_label: str  # z.B. "Freigeben"
    secondary_action_label: str  # z.B. "Ablehnen"
    skip_label: str = "Überspringen"

    # Kontext-Daten
    document_id: Optional[uuid.UUID] = None
    entity_id: Optional[uuid.UUID] = None
    invoice_id: Optional[uuid.UUID] = None

    # Zusätzliche Daten
    metadata: Optional[Dict[str, Any]] = None

    # Confidence für KI-Vorschlag
    confidence: Optional[float] = None
    confidence_reason: Optional[str] = None


@dataclass
class OneClickDecision:
    """Eine getroffene Entscheidung."""

    item_id: uuid.UUID
    decision: str  # "approve", "reject", "skip"
    notes: Optional[str] = None
    corrected_value: Optional[str] = None
    decision_time_ms: Optional[int] = None


@dataclass
class OneClickQueueStats:
    """Statistiken zur One-Click-Queue."""

    total_pending: int
    by_type: Dict[str, int]
    avg_decision_time_ms: float
    decisions_today: int
    approval_rate: float


# ============================================================================
# One-Click Validation Service
# ============================================================================


class OneClickValidationService:
    """Service für schnelle One-Click-Validierungen.

    Optimiert für:
    - Mobiles Swipe-Interface
    - Desktop Keyboard-Shortcuts
    - Batch-Verarbeitung
    - Lernende KI-Integration
    """

    def __init__(self, db: AsyncSession, user_id: uuid.UUID):
        """Initialisiert den Service.

        Args:
            db: Async Database Session
            user_id: ID des aktuellen Benutzers
        """
        self.db = db
        self.user_id = user_id

    # ========================================================================
    # Queue Methods
    # ========================================================================

    async def get_next_items(
        self,
        action_types: Optional[List[OneClickActionType]] = None,
        limit: int = 10,
    ) -> List[OneClickItem]:
        """Holt die nächsten Items zur Validierung.

        Args:
            action_types: Optional Filter für Aktionstypen
            limit: Maximale Anzahl Items

        Returns:
            Liste von OneClickItem sortiert nach Priorität
        """
        items: List[OneClickItem] = []

        # 1. Validation Queue Items laden
        validation_items = await self._get_validation_queue_items(limit)
        for item in validation_items:
            one_click_item = await self._convert_validation_item(item)
            if one_click_item:
                items.append(one_click_item)

        # 2. Pending Invoice Approvals laden
        if not action_types or OneClickActionType.INVOICE_APPROVAL in action_types:
            invoice_items = await self._get_invoice_approval_items(limit)
            items.extend(invoice_items)

        # 3. Entity Assignment Items laden
        if not action_types or OneClickActionType.ENTITY_ASSIGNMENT in action_types:
            entity_items = await self._get_entity_assignment_items(limit)
            items.extend(entity_items)

        # 4. Master Data Updates laden
        if not action_types or OneClickActionType.MASTER_DATA_UPDATE in action_types:
            master_items = await self._get_master_data_items(limit)
            items.extend(master_items)

        # Nach Priorität sortieren und limitieren
        items.sort(key=lambda x: (x.priority, x.created_at))
        return items[:limit]

    async def process_decision(
        self, decision: OneClickDecision
    ) -> Dict[str, Any]:
        """Verarbeitet eine Entscheidung.

        Args:
            decision: Die getroffene Entscheidung

        Returns:
            Ergebnis der Verarbeitung
        """
        logger.info(
            "processing_oneclick_decision",
            item_id=str(decision.item_id),
            decision=decision.decision,
            user_id=str(self.user_id),
        )

        # Item-Typ ermitteln und entsprechend verarbeiten
        # Zuerst in validation_queue_items suchen
        stmt = select(ValidationQueueItem).where(
            ValidationQueueItem.id == decision.item_id
        )
        result = await self.db.execute(stmt)
        validation_item = result.scalar_one_or_none()

        if validation_item:
            return await self._process_validation_decision(validation_item, decision)

        # In invoice_tracking suchen
        stmt = select(InvoiceTracking).where(InvoiceTracking.id == decision.item_id)
        result = await self.db.execute(stmt)
        invoice = result.scalar_one_or_none()

        if invoice:
            return await self._process_invoice_decision(invoice, decision)

        # Kein Item gefunden
        return {
            "success": False,
            "error": "Item nicht gefunden",
            "item_id": str(decision.item_id),
        }

    async def process_batch_decisions(
        self, decisions: List[OneClickDecision]
    ) -> Dict[str, Any]:
        """Verarbeitet mehrere Entscheidungen.

        Args:
            decisions: Liste von Entscheidungen

        Returns:
            Batch-Ergebnis
        """
        results = []
        success_count = 0
        error_count = 0

        for decision in decisions:
            try:
                result = await self.process_decision(decision)
                results.append(result)
                if result.get("success"):
                    success_count += 1
                else:
                    error_count += 1
            except Exception as e:
                logger.error(
                    "batch_decision_error",
                    item_id=str(decision.item_id),
                    **safe_error_log(e),
                )
                error_count += 1
                results.append({
                    "success": False,
                    "error": safe_error_detail(e, "Vorgang"),
                    "item_id": str(decision.item_id),
                })

        return {
            "success_count": success_count,
            "error_count": error_count,
            "total": len(decisions),
            "results": results,
        }

    async def get_queue_stats(self) -> OneClickQueueStats:
        """Holt Statistiken zur Queue.

        Returns:
            OneClickQueueStats
        """
        # Pending Items zaehlen
        stmt = select(func.count(ValidationQueueItem.id)).where(
            ValidationQueueItem.status == ValidationStatus.PENDING.value
        )
        result = await self.db.execute(stmt)
        pending_validation = result.scalar() or 0

        # Pending Invoices zaehlen
        stmt = select(func.count(InvoiceTracking.id)).where(
            InvoiceTracking.status == "pending"
        )
        result = await self.db.execute(stmt)
        pending_invoices = result.scalar() or 0

        total_pending = pending_validation + pending_invoices

        # Nach Typ aufschluesseln
        by_type = {
            "validation": pending_validation,
            "invoice_approval": pending_invoices,
        }

        # Durchschnittliche Entscheidungszeit (aus Validation Items)
        stmt = select(func.avg(ValidationQueueItem.validation_duration_seconds)).where(
            ValidationQueueItem.validated_at.isnot(None)
        )
        result = await self.db.execute(stmt)
        avg_duration_seconds = result.scalar() or 0
        avg_decision_time_ms = float(avg_duration_seconds * 1000)

        # Heutige Entscheidungen
        today_start = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = select(func.count(ValidationQueueItem.id)).where(
            and_(
                ValidationQueueItem.validated_at >= today_start,
                ValidationQueueItem.validated_by_id == self.user_id,
            )
        )
        result = await self.db.execute(stmt)
        decisions_today = result.scalar() or 0

        # Approval Rate
        stmt = select(func.count(ValidationQueueItem.id)).where(
            and_(
                ValidationQueueItem.status == ValidationStatus.APPROVED.value,
                ValidationQueueItem.validated_by_id == self.user_id,
            )
        )
        result = await self.db.execute(stmt)
        approved_count = result.scalar() or 0

        stmt = select(func.count(ValidationQueueItem.id)).where(
            and_(
                ValidationQueueItem.status.in_([
                    ValidationStatus.APPROVED.value,
                    ValidationStatus.REJECTED.value,
                ]),
                ValidationQueueItem.validated_by_id == self.user_id,
            )
        )
        result = await self.db.execute(stmt)
        total_decided = result.scalar() or 1  # Prevent division by zero

        approval_rate = approved_count / total_decided

        return OneClickQueueStats(
            total_pending=total_pending,
            by_type=by_type,
            avg_decision_time_ms=avg_decision_time_ms,
            decisions_today=decisions_today,
            approval_rate=approval_rate,
        )

    # ========================================================================
    # Private Methods - Item Loading
    # ========================================================================

    async def _get_validation_queue_items(self, limit: int) -> List[ValidationQueueItem]:
        """Laedt Validation Queue Items."""
        stmt = (
            select(ValidationQueueItem)
            .where(ValidationQueueItem.status == ValidationStatus.PENDING.value)
            .order_by(ValidationQueueItem.priority.asc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _convert_validation_item(
        self, item: ValidationQueueItem
    ) -> Optional[OneClickItem]:
        """Konvertiert ValidationQueueItem zu OneClickItem."""
        # Dokument laden für mehr Kontext
        stmt = select(Document).where(Document.id == item.document_id)
        result = await self.db.execute(stmt)
        document = result.scalar_one_or_none()

        if not document:
            return None

        # Aktionstyp bestimmen basierend auf Dokumenttyp
        action_type = OneClickActionType.OCR_CORRECTION
        if document.document_type == "invoice":
            action_type = OneClickActionType.INVOICE_APPROVAL
        elif document.document_type == "contract":
            action_type = OneClickActionType.FILING_SUGGESTION

        # Frage formulieren
        question = "OCR-Ergebnis prüfen?"
        if action_type == OneClickActionType.INVOICE_APPROVAL:
            question = "Rechnung freigeben?"
        elif action_type == OneClickActionType.FILING_SUGGESTION:
            question = "Ablagevorschlag akzeptieren?"

        return OneClickItem(
            id=item.id,
            action_type=action_type,
            priority=item.priority,
            created_at=item.created_at,
            title=document.original_filename or "Dokument",
            subtitle=document.document_type or "Unbekannt",
            description=f"Konfidenz: {(item.overall_confidence or 0) * 100:.0f}%",
            question=question,
            primary_action_label="Freigeben",
            secondary_action_label="Ablehnen",
            document_id=document.id,
            confidence=item.overall_confidence,
            confidence_reason=f"OCR-Konfidenz: {(item.overall_confidence or 0) * 100:.0f}%",
            metadata={
                "fields_below_threshold": item.fields_below_threshold,
                "total_fields": item.total_fields,
            },
        )

    async def _get_invoice_approval_items(self, limit: int) -> List[OneClickItem]:
        """Laedt Invoice Approval Items."""
        items: List[OneClickItem] = []

        stmt = (
            select(InvoiceTracking)
            .where(InvoiceTracking.status == "pending")
            .order_by(InvoiceTracking.due_date.asc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        invoices = result.scalars().all()

        for invoice in invoices:
            # Entity-Name laden
            entity_name = "Unbekannt"
            if invoice.entity_id:
                stmt = select(BusinessEntity.name).where(
                    BusinessEntity.id == invoice.entity_id
                )
                result = await self.db.execute(stmt)
                entity_name = result.scalar() or "Unbekannt"

            items.append(
                OneClickItem(
                    id=invoice.id,
                    action_type=OneClickActionType.INVOICE_APPROVAL,
                    priority=self._calculate_invoice_priority(invoice),
                    created_at=invoice.created_at,
                    title=f"Rechnung {invoice.invoice_number or 'N/A'}",
                    subtitle=entity_name,
                    description=f"Betrag: {invoice.amount:,.2f} EUR",
                    question=f"Rechnung über {invoice.amount:,.2f} EUR freigeben?",
                    primary_action_label="Freigeben",
                    secondary_action_label="Ablehnen",
                    invoice_id=invoice.id,
                    entity_id=invoice.entity_id,
                    document_id=invoice.document_id,
                    metadata={
                        "amount": invoice.amount,
                        "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
                        "dunning_level": invoice.dunning_level,
                    },
                )
            )

        return items

    async def _get_entity_assignment_items(self, limit: int) -> List[OneClickItem]:
        """Laedt Entity Assignment Items (Dokumente ohne Entity-Zuordnung)."""
        items: List[OneClickItem] = []

        # Dokumente ohne Entity-Zuordnung
        stmt = (
            select(Document)
            .where(
                and_(
                    Document.business_entity_id.is_(None),
                    Document.extracted_text.isnot(None),  # OCR abgeschlossen
                )
            )
            .order_by(Document.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        documents = result.scalars().all()

        for doc in documents:
            items.append(
                OneClickItem(
                    id=doc.id,
                    action_type=OneClickActionType.ENTITY_ASSIGNMENT,
                    priority=5,
                    created_at=doc.created_at,
                    title=doc.original_filename or "Dokument",
                    subtitle=doc.document_type or "Unbekannt",
                    description="Keine Geschäftspartner-Zuordnung",
                    question="Geschäftspartner zuweisen?",
                    primary_action_label="Zuweisen",
                    secondary_action_label="Überspringen",
                    document_id=doc.id,
                    metadata={
                        "document_type": doc.document_type,
                        "ocr_confidence": doc.ocr_confidence,
                    },
                )
            )

        return items

    async def _get_master_data_items(self, limit: int) -> List[OneClickItem]:
        """Laedt Master Data Update Items."""
        # Placeholder - wird bei Stammdaten-Delta-Erkennung gefuellt
        return []

    def _calculate_invoice_priority(self, invoice: InvoiceTracking) -> int:
        """Berechnet Priorität einer Rechnung.

        Faktoren:
        - Fälligkeitsdatum (überfällig = hohe Priorität)
        - Mahnstufe
        - Betrag
        """
        priority = 5  # Default

        if invoice.due_date:
            days_until_due = (invoice.due_date - utc_now().date()).days

            if days_until_due < 0:
                priority = 1  # Überfällig
            elif days_until_due < 7:
                priority = 2  # Bald fällig
            elif days_until_due < 14:
                priority = 3

        # Mahnstufe erhöhen Priorität
        if invoice.dunning_level:
            priority = min(priority, 5 - invoice.dunning_level)

        return max(1, min(10, priority))

    # ========================================================================
    # Private Methods - Decision Processing
    # ========================================================================

    async def _process_validation_decision(
        self,
        item: ValidationQueueItem,
        decision: OneClickDecision,
    ) -> Dict[str, Any]:
        """Verarbeitet Entscheidung für Validation Item."""
        now = utc_now()

        if decision.decision == "approve":
            item.status = ValidationStatus.APPROVED.value
        elif decision.decision == "reject":
            item.status = ValidationStatus.REJECTED.value
            item.rejection_reason = decision.notes
        elif decision.decision == "skip":
            item.status = ValidationStatus.SKIPPED.value
        else:
            return {"success": False, "error": f"Ungültige Entscheidung: {decision.decision}"}

        item.validated_by_id = self.user_id
        item.validated_at = now
        item.completed_at = now
        item.validation_notes = decision.notes

        if decision.decision_time_ms:
            item.validation_duration_seconds = decision.decision_time_ms // 1000

        await self.db.commit()

        logger.info(
            "validation_item_decided",
            item_id=str(item.id),
            decision=decision.decision,
            user_id=str(self.user_id),
        )

        return {
            "success": True,
            "item_id": str(item.id),
            "decision": decision.decision,
            "item_type": "validation",
        }

    async def _process_invoice_decision(
        self,
        invoice: InvoiceTracking,
        decision: OneClickDecision,
    ) -> Dict[str, Any]:
        """Verarbeitet Entscheidung für Invoice Item."""
        now = utc_now()

        if decision.decision == "approve":
            invoice.status = "approved"
        elif decision.decision == "reject":
            invoice.status = "rejected"
            invoice.notes = decision.notes
        elif decision.decision == "skip":
            # Nichts ändern, nur loggen
            pass
        else:
            return {"success": False, "error": f"Ungültige Entscheidung: {decision.decision}"}

        invoice.updated_at = now

        await self.db.commit()

        logger.info(
            "invoice_item_decided",
            item_id=str(invoice.id),
            decision=decision.decision,
            user_id=str(self.user_id),
        )

        return {
            "success": True,
            "item_id": str(invoice.id),
            "decision": decision.decision,
            "item_type": "invoice",
        }


# ============================================================================
# Keyboard Shortcuts Helper
# ============================================================================


class KeyboardShortcuts:
    """Desktop Keyboard Shortcuts für One-Click-Validierung.

    Standard-Shortcuts:
    - Y / Enter: Genehmigen
    - N / Backspace: Ablehnen
    - Space / Tab: Überspringen
    - 1-9: Quick-Select für Kategorien
    - Ctrl+Enter: Batch-Genehmigung aller sichtbaren Items
    """

    APPROVE = ["y", "Y", "Enter"]
    REJECT = ["n", "N", "Backspace"]
    SKIP = ["Space", "Tab", "s", "S"]
    BATCH_APPROVE = ["Ctrl+Enter", "Cmd+Enter"]
    BATCH_REJECT = ["Ctrl+Backspace", "Cmd+Backspace"]
    DETAILS = ["d", "D", "ArrowDown"]
    PREVIOUS = ["ArrowLeft", "k", "K"]
    NEXT = ["ArrowRight", "j", "J"]

    @classmethod
    def get_shortcut_map(cls) -> Dict[str, List[str]]:
        """Gibt alle Shortcuts als Map zurück."""
        return {
            "approve": cls.APPROVE,
            "reject": cls.REJECT,
            "skip": cls.SKIP,
            "batch_approve": cls.BATCH_APPROVE,
            "batch_reject": cls.BATCH_REJECT,
            "details": cls.DETAILS,
            "previous": cls.PREVIOUS,
            "next": cls.NEXT,
        }


# ============================================================================
# Factory Function
# ============================================================================


async def get_oneclick_validation_service(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> OneClickValidationService:
    """Factory-Funktion für OneClickValidationService.

    Args:
        db: Async Database Session
        user_id: ID des aktuellen Benutzers

    Returns:
        Konfigurierter OneClickValidationService
    """
    return OneClickValidationService(db=db, user_id=user_id)
