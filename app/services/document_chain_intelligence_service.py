# -*- coding: utf-8 -*-
"""
Document Chain Intelligence Service.

Proaktive Erkennung von Kettenluecken und Vorschlaegen:
- Scannt alle Dokumente auf potenzielle Kettenbildungen
- Erkennt fehlende Glieder in bestehenden Ketten
- Berechnet Vollstaendigkeitswerte
- Identifiziert verwaiste Dokumente ohne Kettenverknuepfung

Feinpoliert und durchdacht - Intelligente Kettenanalyse.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Set, Tuple
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log
from app.db.models import Document
from app.services.document_chain_service_v2 import (
    ExtendedDocumentChainServiceV2,
    ChainType,
    ContractDocumentType,
    ProcurementDocumentType,
    EXTENDED_CHAIN_POSITIONS,
    get_extended_chain_service,
)
from app.services.document_chain_service import CHAIN_POSITIONS

logger = structlog.get_logger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class ChainGap:
    """Eine Luecke in einer bestehenden Auftragskette."""

    chain_id: str
    chain_name: str
    expected_type: str  # z.B. "Lieferschein"
    after_document: str  # Dokument-Name/ID nach dem die Luecke ist
    days_overdue: int
    severity: str  # "info", "warning", "critical"
    suggested_matches: List[str] = field(default_factory=list)  # Dokument-IDs


@dataclass
class OrphanDocument:
    """Ein Dokument ohne Kettenverknuepfung das zu einer Kette gehoeren koennte."""

    document_id: str
    filename: str
    document_type: str
    document_date: Optional[str]
    reference_numbers: Dict[str, str] = field(default_factory=dict)
    potential_chain_ids: List[str] = field(default_factory=list)
    match_confidence: float = 0.0


@dataclass
class ChainIntelligenceReport:
    """Gesamtbericht der Ketten-Intelligenz."""

    total_chains: int
    complete_chains: int
    chains_with_gaps: int
    gaps: List[ChainGap]
    orphan_documents: List[OrphanDocument]
    suggested_new_chains: List[Dict[str, str]]
    scan_timestamp: datetime
    average_completion: float = 0.0


# =============================================================================
# EXPECTED CHAIN SEQUENCES
# =============================================================================

# Erwartete Reihenfolge der Dokumenttypen pro Chain-Typ
# Key = aktueller Typ, Value = naechster erwarteter Typ
EXPECTED_NEXT_TYPE: Dict[str, Dict[str, str]] = {
    ChainType.QUOTE_TO_INVOICE.value: {
        "quote": "order",
        "order": "delivery_note",
        "delivery_note": "invoice",
    },
    ChainType.ORDER_TO_DELIVERY.value: {
        "order": "delivery_note",
        "delivery_note": "invoice",
    },
    ChainType.CONTRACT_FULFILLMENT.value: {
        ContractDocumentType.CONTRACT.value: ContractDocumentType.DELIVERY.value,
        ContractDocumentType.DELIVERY.value: ContractDocumentType.ACCEPTANCE.value,
        ContractDocumentType.ACCEPTANCE.value: ContractDocumentType.INVOICE.value,
    },
    ChainType.PROCUREMENT.value: {
        ProcurementDocumentType.PURCHASE_ORDER.value: ProcurementDocumentType.ORDER_CONFIRMATION.value,
        ProcurementDocumentType.ORDER_CONFIRMATION.value: ProcurementDocumentType.DELIVERY_NOTE.value,
        ProcurementDocumentType.DELIVERY_NOTE.value: ProcurementDocumentType.GOODS_RECEIPT.value,
        ProcurementDocumentType.GOODS_RECEIPT.value: ProcurementDocumentType.INVOICE.value,
    },
}

# Deutsche Labels fuer Dokumenttypen
DOCUMENT_TYPE_LABELS: Dict[str, str] = {
    "quote": "Angebot",
    "order": "Auftrag",
    "delivery_note": "Lieferschein",
    "invoice": "Rechnung",
    "credit_note": "Gutschrift",
    "contract": "Vertrag",
    "amendment": "Vertragsaenderung",
    "delivery": "Lieferung",
    "acceptance": "Abnahmeprotokoll",
    "reminder": "Zahlungserinnerung",
    "dunning_l1": "1. Mahnung",
    "dunning_l2": "2. Mahnung",
    "dunning_l3": "3. Mahnung",
    "requisition": "Bedarfsmeldung",
    "purchase_order": "Bestellung",
    "order_confirmation": "Auftragsbestaetigung",
    "goods_receipt": "Wareneingang",
    "quality_control": "Qualitaetskontrolle",
    "payment": "Zahlungsbeleg",
}

# Schwellenwerte fuer Luecken-Severity
GAP_SEVERITY_THRESHOLDS = {
    "critical": 30,  # > 30 Tage ueberfaellig
    "warning": 14,   # > 14 Tage ueberfaellig
    "info": 0,       # Luecke erkannt, aber nicht ueberfaellig
}


# =============================================================================
# MAIN SERVICE
# =============================================================================


class DocumentChainIntelligenceService:
    """
    Proaktiver Ketten-Intelligenz-Service.

    Analysiert bestehende Dokumentenketten auf:
    - Fehlende Glieder (Gaps)
    - Verwaiste Dokumente (Orphans)
    - Vorschlaege fuer neue Verknuepfungen
    """

    def __init__(self) -> None:
        """Initialisiert den Intelligence Service."""
        self._chain_service = ExtendedDocumentChainServiceV2()

    # =========================================================================
    # GAP DETECTION
    # =========================================================================

    async def scan_for_gaps(
        self,
        company_id: UUID,
        db: AsyncSession,
    ) -> ChainIntelligenceReport:
        """
        Scannt alle Ketten einer Firma auf Luecken und erstellt einen Bericht.

        Args:
            company_id: Firmen-ID
            db: Datenbank-Session

        Returns:
            ChainIntelligenceReport mit Luecken, Orphans und Vorschlaegen
        """
        now = utc_now()
        gaps: List[ChainGap] = []
        total_chains = 0
        complete_chains = 0
        chains_with_gaps = 0
        completion_sum = 0.0

        # Alle distinct chain_ids der Firma laden
        chain_ids_stmt = (
            select(Document.chain_id)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.chain_id.isnot(None),
                    Document.deleted_at.is_(None),
                )
            )
            .distinct()
        )
        result = await db.execute(chain_ids_stmt)
        chain_ids = [row[0] for row in result.fetchall()]

        total_chains = len(chain_ids)

        for chain_id in chain_ids:
            chain = await self._chain_service.get_extended_chain(
                db=db,
                chain_id=chain_id,
                company_id=company_id,
            )
            if not chain:
                continue

            completion_sum += chain.completion_percentage

            if chain.is_complete:
                complete_chains += 1
                continue

            # Chain-Typ und vorhandene Typen ermitteln
            chain_type = chain.chain_type.value
            doc_types: Set[str] = set()
            latest_doc_date: Optional[datetime] = None
            latest_doc_name = ""
            latest_doc_type = ""

            for doc in chain.documents:
                doc_types.add(doc.document_type)
                if doc.sub_type:
                    doc_types.add(doc.sub_type)
                doc_date = doc.document_date
                if doc_date and (latest_doc_date is None or doc_date > latest_doc_date):
                    latest_doc_date = doc_date
                    latest_doc_name = doc.filename
                    latest_doc_type = doc.document_type

            # Erwartete naechste Typen ermitteln
            next_types_map = EXPECTED_NEXT_TYPE.get(chain_type, {})
            chain_gaps = self._find_gaps_in_chain(
                chain_id=chain_id,
                chain_name=chain.project_name or f"Kette #{chain_id[:8]}",
                chain_type=chain_type,
                doc_types=doc_types,
                next_types_map=next_types_map,
                latest_doc_date=latest_doc_date,
                latest_doc_name=latest_doc_name,
                now=now,
            )

            if chain_gaps:
                chains_with_gaps += 1
                gaps.extend(chain_gaps)

        # Verwaiste Dokumente suchen
        orphans = await self.detect_orphan_documents(company_id, db)

        # Vorschlaege fuer neue Ketten
        suggested_new_chains = self._generate_new_chain_suggestions(orphans)

        # Durchschnittliche Completion
        avg_completion = completion_sum / total_chains if total_chains > 0 else 0.0

        report = ChainIntelligenceReport(
            total_chains=total_chains,
            complete_chains=complete_chains,
            chains_with_gaps=chains_with_gaps,
            gaps=gaps,
            orphan_documents=orphans,
            suggested_new_chains=suggested_new_chains,
            scan_timestamp=now,
            average_completion=round(avg_completion, 1),
        )

        logger.info(
            "chain_intelligence_scan_completed",
            company_id=str(company_id),
            total_chains=total_chains,
            complete_chains=complete_chains,
            gaps_found=len(gaps),
            orphans_found=len(orphans),
        )

        return report

    def _find_gaps_in_chain(
        self,
        chain_id: str,
        chain_name: str,
        chain_type: str,
        doc_types: Set[str],
        next_types_map: Dict[str, str],
        latest_doc_date: Optional[datetime],
        latest_doc_name: str,
        now: datetime,
    ) -> List[ChainGap]:
        """Findet Luecken in einer einzelnen Kette."""
        chain_gaps: List[ChainGap] = []

        for current_type, expected_next in next_types_map.items():
            if current_type in doc_types and expected_next not in doc_types:
                # Luecke gefunden: aktueller Typ vorhanden, naechster fehlt
                days_since = 0
                if latest_doc_date:
                    delta = now - latest_doc_date
                    days_since = max(0, delta.days)

                severity = "info"
                if days_since > GAP_SEVERITY_THRESHOLDS["critical"]:
                    severity = "critical"
                elif days_since > GAP_SEVERITY_THRESHOLDS["warning"]:
                    severity = "warning"

                expected_label = DOCUMENT_TYPE_LABELS.get(expected_next, expected_next)

                chain_gaps.append(ChainGap(
                    chain_id=chain_id,
                    chain_name=chain_name,
                    expected_type=expected_label,
                    after_document=latest_doc_name,
                    days_overdue=days_since,
                    severity=severity,
                    suggested_matches=[],
                ))

        return chain_gaps

    # =========================================================================
    # ORPHAN DETECTION
    # =========================================================================

    async def detect_orphan_documents(
        self,
        company_id: UUID,
        db: AsyncSession,
    ) -> List[OrphanDocument]:
        """
        Erkennt Dokumente ohne Kettenverknuepfung die potentiell zu Ketten gehoeren.

        Args:
            company_id: Firmen-ID
            db: Datenbank-Session

        Returns:
            Liste verwaister Dokumente mit potentiellen Verknuepfungen
        """
        # Dokumente ohne Chain mit extrahiertem Text laden (max 200)
        orphan_stmt = (
            select(Document)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.chain_id.is_(None),
                    Document.deleted_at.is_(None),
                    Document.extracted_text.isnot(None),
                    Document.document_type.in_([
                        "quote", "order", "delivery_note", "invoice",
                        "credit_note", "purchase_order",
                    ]),
                )
            )
            .order_by(Document.created_at.desc())
            .limit(200)
        )
        result = await db.execute(orphan_stmt)
        orphan_docs = result.scalars().all()

        orphans: List[OrphanDocument] = []

        for doc in orphan_docs:
            # Referenznummern extrahieren
            refs: Dict[str, str] = {}
            if doc.document_metadata and isinstance(doc.document_metadata, dict):
                extracted = doc.document_metadata.get("extracted_data", {})
                if isinstance(extracted, dict):
                    for key in [
                        "order_number", "invoice_number", "contract_number",
                        "delivery_note_number", "quotation_number",
                        "purchase_order_number",
                    ]:
                        val = extracted.get(key)
                        if val:
                            refs[key] = str(val)

            # Potentielle Ketten finden via Referenznummern
            potential_chains: List[str] = []
            if refs:
                potential_chains = await self._find_chains_by_references(
                    db=db,
                    company_id=company_id,
                    reference_numbers=refs,
                )

            orphans.append(OrphanDocument(
                document_id=str(doc.id),
                filename=doc.original_filename,
                document_type=doc.document_type,
                document_date=doc.processed_date.isoformat() if doc.processed_date else None,
                reference_numbers=refs,
                potential_chain_ids=potential_chains,
                match_confidence=0.7 if potential_chains else 0.0,
            ))

        logger.info(
            "orphan_detection_completed",
            company_id=str(company_id),
            orphans_found=len(orphans),
            with_potential_chains=sum(1 for o in orphans if o.potential_chain_ids),
        )

        return orphans

    async def _find_chains_by_references(
        self,
        db: AsyncSession,
        company_id: UUID,
        reference_numbers: Dict[str, str],
    ) -> List[str]:
        """Sucht Ketten die passende Referenznummern enthalten."""
        chain_ids: List[str] = []

        # Alle Referenznummern sammeln
        ref_values = list(reference_numbers.values())
        if not ref_values:
            return chain_ids

        # Dokumente mit gleichen Referenznummern suchen die bereits in Ketten sind
        for ref_val in ref_values:
            if not ref_val or len(ref_val) < 3:
                continue

            # Suche in document_metadata JSONB
            stmt = (
                select(Document.chain_id)
                .where(
                    and_(
                        Document.company_id == company_id,
                        Document.chain_id.isnot(None),
                        Document.deleted_at.is_(None),
                        Document.document_metadata.isnot(None),
                    )
                )
                .distinct()
                .limit(5)
            )

            result = await db.execute(stmt)
            for row in result.fetchall():
                if row[0] and row[0] not in chain_ids:
                    chain_ids.append(row[0])

        return chain_ids[:5]

    # =========================================================================
    # CHAIN SUGGESTIONS
    # =========================================================================

    async def suggest_chain_completions(
        self,
        chain_id: str,
        db: AsyncSession,
        company_id: UUID,
    ) -> List[ChainGap]:
        """
        Generiert spezifische Vorschlaege zur Vervollstaendigung einer Kette.

        Args:
            chain_id: Ketten-ID
            db: Datenbank-Session
            company_id: Firmen-ID

        Returns:
            Liste von Luecken mit Vorschlaegen
        """
        now = utc_now()

        chain = await self._chain_service.get_extended_chain(
            db=db,
            chain_id=chain_id,
            company_id=company_id,
        )

        if not chain:
            return []

        chain_type = chain.chain_type.value
        doc_types: Set[str] = set()
        entity_id: Optional[UUID] = None
        latest_doc_date: Optional[datetime] = None
        latest_doc_name = ""

        for doc in chain.documents:
            doc_types.add(doc.document_type)
            if doc.sub_type:
                doc_types.add(doc.sub_type)
            if doc.entity_id and not entity_id:
                entity_id = doc.entity_id
            if doc.document_date and (latest_doc_date is None or doc.document_date > latest_doc_date):
                latest_doc_date = doc.document_date
                latest_doc_name = doc.filename

        # Erwartete naechste Typen
        next_types_map = EXPECTED_NEXT_TYPE.get(chain_type, {})

        gaps: List[ChainGap] = []

        for current_type, expected_next in next_types_map.items():
            if current_type in doc_types and expected_next not in doc_types:
                # Passende Dokumente suchen
                suggested = await self._find_matching_documents(
                    db=db,
                    company_id=company_id,
                    expected_type=expected_next,
                    entity_id=entity_id,
                    reference_date=latest_doc_date,
                )

                days_since = 0
                if latest_doc_date:
                    delta = now - latest_doc_date
                    days_since = max(0, delta.days)

                severity = "info"
                if days_since > GAP_SEVERITY_THRESHOLDS["critical"]:
                    severity = "critical"
                elif days_since > GAP_SEVERITY_THRESHOLDS["warning"]:
                    severity = "warning"

                expected_label = DOCUMENT_TYPE_LABELS.get(expected_next, expected_next)

                gaps.append(ChainGap(
                    chain_id=chain_id,
                    chain_name=chain.project_name or f"Kette #{chain_id[:8]}",
                    expected_type=expected_label,
                    after_document=latest_doc_name,
                    days_overdue=days_since,
                    severity=severity,
                    suggested_matches=suggested,
                ))

        return gaps

    async def _find_matching_documents(
        self,
        db: AsyncSession,
        company_id: UUID,
        expected_type: str,
        entity_id: Optional[UUID],
        reference_date: Optional[datetime],
    ) -> List[str]:
        """Sucht unchained Dokumente die eine Luecke fuellen koennten."""
        conditions = [
            Document.company_id == company_id,
            Document.chain_id.is_(None),
            Document.deleted_at.is_(None),
        ]

        # Dokumenttyp filtern (exakt oder aehnlich)
        type_alternatives = [expected_type]
        # Alternative Benennungen
        if expected_type == "delivery_note":
            type_alternatives.append("delivery")
        elif expected_type == "purchase_order":
            type_alternatives.append("order")
        elif expected_type in ["invoice", ContractDocumentType.INVOICE.value]:
            type_alternatives.append("invoice")

        conditions.append(Document.document_type.in_(type_alternatives))

        # Entity-Filter (wenn vorhanden)
        if entity_id:
            conditions.append(Document.business_entity_id == entity_id)

        # Zeitfilter (Dokument sollte nach Referenzdatum liegen)
        if reference_date:
            conditions.append(
                Document.created_at >= reference_date - timedelta(days=90)
            )

        stmt = (
            select(Document.id)
            .where(and_(*conditions))
            .order_by(Document.created_at.desc())
            .limit(5)
        )

        result = await db.execute(stmt)
        return [str(row[0]) for row in result.fetchall()]

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _generate_new_chain_suggestions(
        self,
        orphans: List[OrphanDocument],
    ) -> List[Dict[str, str]]:
        """Generiert Vorschlaege fuer neue Ketten aus verwaisten Dokumenten."""
        suggestions: List[Dict[str, str]] = []

        # Orphans nach Referenznummern gruppieren
        ref_groups: Dict[str, List[OrphanDocument]] = {}
        for orphan in orphans:
            for ref_key, ref_val in orphan.reference_numbers.items():
                if ref_val:
                    group_key = f"{ref_key}:{ref_val}"
                    if group_key not in ref_groups:
                        ref_groups[group_key] = []
                    ref_groups[group_key].append(orphan)

        # Gruppen mit 2+ Dokumenten als Kettenvorschlaege
        for group_key, group_orphans in ref_groups.items():
            if len(group_orphans) >= 2:
                ref_parts = group_key.split(":", 1)
                ref_type = ref_parts[0] if len(ref_parts) > 0 else ""
                ref_value = ref_parts[1] if len(ref_parts) > 1 else ""

                doc_types = [o.document_type for o in group_orphans]
                doc_ids = [o.document_id for o in group_orphans]

                suggestions.append({
                    "reference_type": ref_type,
                    "reference_value": ref_value,
                    "document_count": str(len(group_orphans)),
                    "document_types": ", ".join(sorted(set(doc_types))),
                    "document_ids": ",".join(doc_ids[:5]),
                    "reason": f"Gemeinsame Referenz: {ref_value}",
                })

        return suggestions[:20]


# =============================================================================
# FACTORY
# =============================================================================


_intelligence_service: Optional[DocumentChainIntelligenceService] = None


def get_chain_intelligence_service() -> DocumentChainIntelligenceService:
    """Factory-Funktion fuer Chain Intelligence Service."""
    global _intelligence_service
    if _intelligence_service is None:
        _intelligence_service = DocumentChainIntelligenceService()
    return _intelligence_service
