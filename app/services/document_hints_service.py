# -*- coding: utf-8 -*-
"""
Document Hints Service for Ablage-System.

Aggregiert proaktive, kontextbezogene Hinweise für Dokumente:
- Fehlende Dokumente in Auftragsketten
- Ablaufende Skonto-Fristen
- Risiko-Scores von Geschäftspartnern
- Überfällige Zahlungen
- OCR-Qualitätswarnungen
- Duplikatsverdacht
- Compliance-Hinweise
- Erforderliche Freigaben

Feinpoliert und durchdacht - Enterprise-grade Document Hints.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import List, Optional, Dict, Any
from uuid import UUID
from decimal import Decimal

import structlog
from sqlalchemy import select, and_, or_, func, cast
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Document,
    BusinessEntity,
    InvoiceTracking,
    DocumentType,
    InvoiceStatus,
)
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums
# =============================================================================

class HintCategory(str, Enum):
    """Kategorien von Document Hints."""
    MISSING_DOCUMENT = "missing_document"
    SKONTO_DEADLINE = "skonto_deadline"
    ENTITY_RISK = "entity_risk"
    PAYMENT_OVERDUE = "payment_overdue"
    OCR_QUALITY = "ocr_quality"
    DUPLICATE_SUSPECT = "duplicate_suspect"
    COMPLIANCE = "compliance"
    ACTION_REQUIRED = "action_required"


class HintSeverity(str, Enum):
    """Schweregrad von Hints."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class DocumentHint:
    """Einzelner proaktiver Hinweis für ein Dokument."""
    category: HintCategory
    severity: HintSeverity
    title: str  # German, kurz
    message: str  # German, beschreibend
    action_label: Optional[str] = None  # z.B. "Lieferschein zuordnen"
    action_type: Optional[str] = None  # z.B. "link_document", "approve_payment"
    action_data: Optional[Dict[str, str]] = None  # z.B. {"document_id": "...", "entity_id": "..."}
    confidence: float = 1.0  # 0-1
    expires_at: Optional[datetime] = None  # Für zeitkritische Hints

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary für JSON-Serialisierung."""
        result: Dict[str, Any] = {
            "category": self.category.value,
            "severity": self.severity.value,
            "title": self.title,
            "message": self.message,
            "confidence": self.confidence,
        }
        if self.action_label:
            result["action_label"] = self.action_label
        if self.action_type:
            result["action_type"] = self.action_type
        if self.action_data:
            result["action_data"] = self.action_data
        if self.expires_at:
            result["expires_at"] = self.expires_at.isoformat()
        return result


@dataclass
class HintSummary:
    """Zusammenfassung aller Hints (Dashboard)."""
    by_category: Dict[str, int] = field(default_factory=dict)
    by_severity: Dict[str, int] = field(default_factory=dict)
    total: int = 0
    critical_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "by_category": self.by_category,
            "by_severity": self.by_severity,
            "total": self.total,
            "critical_count": self.critical_count,
        }


# =============================================================================
# Document Hints Service
# =============================================================================

class DocumentHintsService:
    """
    Service zur Aggregation proaktiver Dokument-Hinweise.

    Koordiniert verschiedene Datenquellen um kontextbezogene Hinweise
    zu generieren die dem Benutzer helfen, Probleme zu erkennen
    bevor sie kritisch werden.
    """

    # Confidence thresholds
    DUPLICATE_SIMILARITY_THRESHOLD = 0.85
    OCR_CONFIDENCE_THRESHOLD = 0.70

    def __init__(self, session: AsyncSession) -> None:
        """Initialize document hints service."""
        self.session = session

    async def get_hints_for_document(
        self,
        document_id: UUID,
        company_id: UUID,
    ) -> List[DocumentHint]:
        """
        Holt alle Hints für ein einzelnes Dokument.

        Args:
            document_id: Dokument-ID
            company_id: Firmen-ID (REQUIRED für Multi-Tenant)

        Returns:
            Liste von DocumentHints
        """
        # Dokument laden
        stmt = select(Document).where(
            and_(
                Document.id == document_id,
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
            )
        )
        result = await self.session.execute(stmt)
        document = result.scalar_one_or_none()

        if not document:
            logger.warning(
                "document_not_found_for_hints",
                document_id=str(document_id),
                company_id=str(company_id),
            )
            return []

        hints: List[DocumentHint] = []

        # Verschiedene Hint-Quellen prüfen
        try:
            hints.extend(await self._check_missing_documents(document))
            hints.extend(await self._check_skonto_deadline(document))
            hints.extend(await self._check_entity_risk(document))
            hints.extend(await self._check_payment_overdue(document))
            hints.extend(await self._check_ocr_quality(document))
            hints.extend(await self._check_duplicate_suspect(document, company_id))
            hints.extend(await self._check_compliance(document))
            hints.extend(await self._check_action_required(document))
        except Exception as e:
            logger.error(
                "hint_generation_error",
                document_id=str(document_id),
                **safe_error_log(e),
            )

        return hints

    async def get_hints_batch(
        self,
        document_ids: List[UUID],
        company_id: UUID,
    ) -> Dict[UUID, List[DocumentHint]]:
        """
        Holt Hints für mehrere Dokumente (Batch-Operation).

        Args:
            document_ids: Liste von Dokument-IDs
            company_id: Firmen-ID

        Returns:
            Dictionary: document_id -> Liste von Hints
        """
        results: Dict[UUID, List[DocumentHint]] = {}

        for doc_id in document_ids:
            try:
                hints = await self.get_hints_for_document(doc_id, company_id)
                results[doc_id] = hints
            except Exception as e:
                logger.error(
                    "batch_hint_error",
                    document_id=str(doc_id),
                    **safe_error_log(e),
                )
                results[doc_id] = []

        return results

    async def get_hint_summary(
        self,
        company_id: UUID,
    ) -> HintSummary:
        """
        Erstellt eine Zusammenfassung aller Hints für das Dashboard.

        Args:
            company_id: Firmen-ID

        Returns:
            HintSummary mit Statistiken
        """
        summary = HintSummary()

        # Alle Dokumente der Firma laden
        stmt = select(Document).where(
            and_(
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
            )
        ).limit(1000)  # Limit zur Performance-Optimierung

        result = await self.session.execute(stmt)
        documents = result.scalars().all()

        # Hints für alle Dokumente sammeln
        for doc in documents:
            try:
                hints = await self.get_hints_for_document(doc.id, company_id)

                for hint in hints:
                    # Kategorie zaehlen
                    cat_key = hint.category.value
                    summary.by_category[cat_key] = summary.by_category.get(cat_key, 0) + 1

                    # Severity zaehlen
                    sev_key = hint.severity.value
                    summary.by_severity[sev_key] = summary.by_severity.get(sev_key, 0) + 1

                    # Total
                    summary.total += 1

                    # Critical zaehlen
                    if hint.severity == HintSeverity.CRITICAL:
                        summary.critical_count += 1
            except Exception as e:
                logger.error(
                    "summary_document_error",
                    document_id=str(doc.id),
                    **safe_error_log(e),
                )

        return summary

    # =========================================================================
    # Internal Hint Checkers
    # =========================================================================

    async def _check_missing_documents(
        self,
        document: Document,
    ) -> List[DocumentHint]:
        """Prüfen ob zugehoerige Dokumente in Kette fehlen."""
        hints: List[DocumentHint] = []

        # Nur für Rechnungen relevant
        if document.document_type != DocumentType.INVOICE.value:
            return hints

        # Prüfe ob Lieferschein vorhanden (via chain_id oder business_entity)
        if document.chain_id:
            # Prüfe ob Lieferschein in Kette vorhanden
            stmt = select(func.count()).where(
                and_(
                    Document.chain_id == document.chain_id,
                    Document.document_type == DocumentType.DELIVERY_NOTE.value,
                    Document.deleted_at.is_(None),
                )
            )
            count = await self.session.scalar(stmt)

            if count == 0:
                hints.append(
                    DocumentHint(
                        category=HintCategory.MISSING_DOCUMENT,
                        severity=HintSeverity.WARNING,
                        title="Lieferschein fehlt",
                        message="Diese Rechnung hat keinen zugehoerigen Lieferschein in der Auftragskette",
                        action_label="Lieferschein zuordnen",
                        action_type="link_document",
                        action_data={
                            "document_id": str(document.id),
                            "chain_id": document.chain_id,
                        },
                        confidence=0.85,
                    )
                )

        return hints

    async def _check_skonto_deadline(
        self,
        document: Document,
    ) -> List[DocumentHint]:
        """Prüfen ob Skonto-Frist bald ablaeuft."""
        hints: List[DocumentHint] = []

        # Invoice Tracking laden
        stmt = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.document_id == document.id,
                InvoiceTracking.deleted_at.is_(None),
            )
        )
        result = await self.session.execute(stmt)
        invoice = result.scalar_one_or_none()

        if not invoice or not invoice.skonto_deadline:
            return hints

        # Skonto bereits genutzt?
        if invoice.skonto_used:
            return hints

        now = datetime.now(timezone.utc)
        deadline = invoice.skonto_deadline

        # Zeitzone normalisieren
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)

        days_remaining = (deadline - now).days

        # Nur wenn Frist noch nicht abgelaufen
        if days_remaining >= 0 and days_remaining <= 7:
            # Berechne Ersparnis
            savings = Decimal(str(invoice.amount)) * Decimal(str(invoice.skonto_percentage or 0)) / Decimal("100")
            savings = savings.quantize(Decimal("0.01"))

            severity = HintSeverity.CRITICAL if days_remaining <= 2 else HintSeverity.WARNING

            hints.append(
                DocumentHint(
                    category=HintCategory.SKONTO_DEADLINE,
                    severity=severity,
                    title=f"Skonto-Frist laeuft in {days_remaining} Tagen ab",
                    message=f"Skonto-Frist laeuft am {deadline.strftime('%d.%m.%Y')} ab. Ersparnis: {savings} EUR",
                    action_label="Skonto nutzen",
                    action_type="apply_skonto",
                    action_data={
                        "document_id": str(document.id),
                        "invoice_id": str(invoice.id),
                        "savings": str(savings),
                    },
                    confidence=1.0,
                    expires_at=deadline,
                )
            )

        return hints

    async def _check_entity_risk(
        self,
        document: Document,
    ) -> List[DocumentHint]:
        """Prüfen ob Geschäftspartner hohen Risiko-Score hat."""
        hints: List[DocumentHint] = []

        if not document.business_entity_id:
            return hints

        # Entity laden
        stmt = select(BusinessEntity).where(BusinessEntity.id == document.business_entity_id)
        result = await self.session.execute(stmt)
        entity = result.scalar_one_or_none()

        if not entity:
            return hints

        # Risk Score prüfen
        risk_score = entity.risk_score or 0.0

        if risk_score >= 75:
            severity = HintSeverity.CRITICAL
            title = "Kritischer Risiko-Score"
        elif risk_score >= 50:
            severity = HintSeverity.WARNING
            title = "Erhöhter Risiko-Score"
        else:
            return hints  # Kein Hint bei niedrigem Risiko

        # Anzahl unbezahlter Rechnungen
        stmt_overdue = select(func.count()).select_from(InvoiceTracking).join(
            Document, InvoiceTracking.document_id == Document.id
        ).where(
            and_(
                Document.business_entity_id == entity.id,
                InvoiceTracking.status.in_([InvoiceStatus.OVERDUE.value, InvoiceStatus.DUNNING.value]),
                InvoiceTracking.deleted_at.is_(None),
            )
        )
        overdue_count = await self.session.scalar(stmt_overdue) or 0

        message = f"Risiko-Score: {int(risk_score)}/100"
        if overdue_count > 0:
            message += f" - {overdue_count} unbezahlte Rechnung(en)"

        hints.append(
            DocumentHint(
                category=HintCategory.ENTITY_RISK,
                severity=severity,
                title=title,
                message=message,
                action_label="Risikoprofil anzeigen",
                action_type="view_risk_profile",
                action_data={
                    "entity_id": str(entity.id),
                    "risk_score": str(int(risk_score)),
                },
                confidence=0.95,
            )
        )

        return hints

    async def _check_payment_overdue(
        self,
        document: Document,
    ) -> List[DocumentHint]:
        """Prüfen ob Zahlung überfällig ist."""
        hints: List[DocumentHint] = []

        # Invoice Tracking laden
        stmt = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.document_id == document.id,
                InvoiceTracking.deleted_at.is_(None),
            )
        )
        result = await self.session.execute(stmt)
        invoice = result.scalar_one_or_none()

        if not invoice or not invoice.due_date:
            return hints

        # Bereits bezahlt?
        if invoice.status == InvoiceStatus.PAID.value:
            return hints

        now = datetime.now(timezone.utc)
        due_date = invoice.due_date

        # Zeitzone normalisieren
        if due_date.tzinfo is None:
            due_date = due_date.replace(tzinfo=timezone.utc)

        days_overdue = (now - due_date).days

        if days_overdue > 0:
            severity = HintSeverity.CRITICAL if days_overdue > 30 else HintSeverity.WARNING

            hints.append(
                DocumentHint(
                    category=HintCategory.PAYMENT_OVERDUE,
                    severity=severity,
                    title=f"Rechnung seit {days_overdue} Tagen überfällig",
                    message=f"Diese Rechnung ist seit {days_overdue} Tagen überfällig. Betrag: {invoice.amount:.2f} EUR",
                    action_label="Mahnung senden",
                    action_type="send_dunning",
                    action_data={
                        "document_id": str(document.id),
                        "invoice_id": str(invoice.id),
                        "days_overdue": str(days_overdue),
                    },
                    confidence=1.0,
                )
            )

        return hints

    async def _check_ocr_quality(
        self,
        document: Document,
    ) -> List[DocumentHint]:
        """Prüfen ob OCR-Qualität niedrig ist."""
        hints: List[DocumentHint] = []

        confidence = document.ocr_confidence or 1.0

        if confidence < self.OCR_CONFIDENCE_THRESHOLD:
            severity = HintSeverity.CRITICAL if confidence < 0.5 else HintSeverity.WARNING

            hints.append(
                DocumentHint(
                    category=HintCategory.OCR_QUALITY,
                    severity=severity,
                    title="Niedrige OCR-Qualität",
                    message=f"OCR-Erkennung unsicher ({confidence * 100:.0f}% Konfidenz) - Manuelle Prüfung empfohlen",
                    action_label="Dokument prüfen",
                    action_type="review_ocr",
                    action_data={
                        "document_id": str(document.id),
                        "confidence": str(confidence),
                    },
                    confidence=confidence,
                )
            )

        return hints

    async def _check_duplicate_suspect(
        self,
        document: Document,
        company_id: UUID,
    ) -> List[DocumentHint]:
        """Prüfen ob Dokument möglicherweise Duplikat ist."""
        hints: List[DocumentHint] = []

        # Nur für Rechnungen mit extracted_data
        if document.document_type != DocumentType.INVOICE.value:
            return hints

        if not document.extracted_data:
            return hints

        # Rechnungsnummer aus extracted_data holen
        invoice_number = document.extracted_data.get("invoice_number")
        if not invoice_number:
            return hints

        # Nach anderen Dokumenten mit gleicher Rechnungsnummer suchen
        stmt = select(Document).where(
            and_(
                Document.company_id == company_id,
                Document.id != document.id,
                Document.document_type == DocumentType.INVOICE.value,
                Document.deleted_at.is_(None),
                cast(Document.extracted_data, JSONB)["invoice_number"].astext == str(invoice_number),
            )
        ).limit(1)

        result = await self.session.execute(stmt)
        duplicate = result.scalar_one_or_none()

        if duplicate:
            hints.append(
                DocumentHint(
                    category=HintCategory.DUPLICATE_SUSPECT,
                    severity=HintSeverity.WARNING,
                    title="Mögliches Duplikat",
                    message=f"Ein Dokument mit Rechnungsnummer {invoice_number} existiert bereits",
                    action_label="Dokumente vergleichen",
                    action_type="compare_documents",
                    action_data={
                        "document_id": str(document.id),
                        "duplicate_id": str(duplicate.id),
                    },
                    confidence=0.80,
                )
            )

        return hints

    async def _check_compliance(
        self,
        document: Document,
    ) -> List[DocumentHint]:
        """Prüfen ob Pflichtfelder fehlen (GoBD-Compliance)."""
        hints: List[DocumentHint] = []

        # Nur für Rechnungen relevant
        if document.document_type != DocumentType.INVOICE.value:
            return hints

        if not document.extracted_data:
            return hints

        # GoBD Pflichtfelder für Rechnungen
        required_fields = ["invoice_number", "invoice_date", "total_amount"]
        missing_fields: List[str] = []

        for field in required_fields:
            if not document.extracted_data.get(field):
                missing_fields.append(field)

        if missing_fields:
            field_names = {
                "invoice_number": "Rechnungsnummer",
                "invoice_date": "Rechnungsdatum",
                "total_amount": "Gesamtbetrag",
            }

            missing_labels = [field_names.get(f, f) for f in missing_fields]

            hints.append(
                DocumentHint(
                    category=HintCategory.COMPLIANCE,
                    severity=HintSeverity.WARNING,
                    title="GoBD-Pflichtfelder fehlen",
                    message=f"Dokument fehlt GoBD-Pflichtfelder: {', '.join(missing_labels)}",
                    action_label="Felder ergaenzen",
                    action_type="edit_extracted_data",
                    action_data={
                        "document_id": str(document.id),
                        "missing_fields": missing_fields,
                    },
                    confidence=0.90,
                )
            )

        return hints

    async def _check_action_required(
        self,
        document: Document,
    ) -> List[DocumentHint]:
        """Prüfen ob Freigabe oder Aktion erforderlich ist."""
        hints: List[DocumentHint] = []

        # Beispiel: Rechnung über 10.000 EUR erfordert Freigabe
        if document.document_type == DocumentType.INVOICE.value and document.extracted_data:
            total_amount = document.extracted_data.get("total_amount")

            if total_amount:
                try:
                    amount = float(total_amount)
                    if amount >= 10000:
                        hints.append(
                            DocumentHint(
                                category=HintCategory.ACTION_REQUIRED,
                                severity=HintSeverity.WARNING,
                                title="Freigabe erforderlich",
                                message=f"Rechnung über {amount:.2f} EUR erfordert Freigabe",
                                action_label="Freigabe anfordern",
                                action_type="request_approval",
                                action_data={
                                    "document_id": str(document.id),
                                    "amount": str(amount),
                                },
                                confidence=1.0,
                            )
                        )
                except (ValueError, TypeError) as e:
                    logger.debug("amount_parse_error", error_type=type(e).__name__, amount=total_amount)

        return hints


# =============================================================================
# Factory Function
# =============================================================================

def get_document_hints_service(session: AsyncSession) -> DocumentHintsService:
    """Factory-Funktion für Dependency Injection."""
    return DocumentHintsService(session)
