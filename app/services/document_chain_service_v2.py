# -*- coding: utf-8 -*-
"""
Extended Document Chain Service V2.

Erweitertes Auftragsketten-Tracking mit neuen Chain-Typen:
- Vertragserfuellung (Vertrag -> Lieferung -> Mahnung)
- Beschaffungsketten (Bestellung -> Wareneingang -> Qualitaetskontrolle)
- Projekt-basierte Dokumentengruppierung
- ML-basiertes Auto-Matching mit erweiterter Konfidenz
- Visualisierungs-API fuer Frontend

Phase 6.2: Extended Document Chains fuer Enterprise-Dokumentenmanagement.
Feinpoliert und durchdacht - Deutsche Dokumente mit hoechster Praezision.
"""

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Set, Tuple, TypedDict, Any
from uuid import UUID, uuid4
import re

import structlog
from sqlalchemy import select, func, and_, or_, update, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log
from app.services.document_chain_service import (
    DocumentChainService,
    RelationshipType,
    DiscrepancyType,
    DiscrepancySeverity,
    ChainDocument,
    DocumentChain,
    ChainMatchResult,
    ChainDiscrepancy,
    CHAIN_POSITIONS,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# EXTENDED CHAIN TYPES
# =============================================================================


class ChainType(str, Enum):
    """Erweiterte Kettentypen fuer unterschiedliche Geschaeftsprozesse."""

    # Bestehende Typen (aus v1)
    QUOTE_TO_ORDER = "quote_to_order"
    ORDER_TO_DELIVERY = "order_to_delivery"
    DELIVERY_TO_INVOICE = "delivery_to_invoice"
    QUOTE_TO_INVOICE = "quote_to_invoice"

    # NEU: Vertragserfuellung
    CONTRACT_FULFILLMENT = "contract_fulfillment"  # Vertrag -> Lieferung -> Mahnung

    # NEU: Beschaffung
    PROCUREMENT = "procurement"  # Bestellung -> Wareneingang -> QC

    # NEU: Projektbasiert
    PROJECT = "project"  # Alle Dokumente nach Projekt-ID gruppiert


class ContractDocumentType(str, Enum):
    """Dokumenttypen in einer Vertragserfuellungskette."""

    CONTRACT = "contract"  # Vertrag
    AMENDMENT = "amendment"  # Vertragsaenderung
    DELIVERY = "delivery"  # Lieferung/Leistungserbringung
    ACCEPTANCE = "acceptance"  # Abnahmeprotokoll
    INVOICE = "invoice"  # Rechnung
    REMINDER = "reminder"  # Zahlungserinnerung
    DUNNING_L1 = "dunning_l1"  # 1. Mahnung
    DUNNING_L2 = "dunning_l2"  # 2. Mahnung
    DUNNING_L3 = "dunning_l3"  # 3. Mahnung (Inkasso-Androhung)
    TERMINATION = "termination"  # Kuendigung


class ProcurementDocumentType(str, Enum):
    """Dokumenttypen in einer Beschaffungskette."""

    REQUISITION = "requisition"  # Bedarfsmeldung
    PURCHASE_ORDER = "purchase_order"  # Bestellung
    ORDER_CONFIRMATION = "order_confirmation"  # Auftragsbestaetigung
    DELIVERY_NOTE = "delivery_note"  # Lieferschein
    GOODS_RECEIPT = "goods_receipt"  # Wareneingang
    QUALITY_CONTROL = "quality_control"  # QC-Protokoll
    INVOICE = "invoice"  # Rechnung
    PAYMENT = "payment"  # Zahlungsbeleg


# Chain-Positionen fuer erweiterte Typen
EXTENDED_CHAIN_POSITIONS: Dict[str, Dict[str, int]] = {
    ChainType.CONTRACT_FULFILLMENT.value: {
        ContractDocumentType.CONTRACT.value: 1,
        ContractDocumentType.AMENDMENT.value: 2,
        ContractDocumentType.DELIVERY.value: 3,
        ContractDocumentType.ACCEPTANCE.value: 4,
        ContractDocumentType.INVOICE.value: 5,
        ContractDocumentType.REMINDER.value: 6,
        ContractDocumentType.DUNNING_L1.value: 7,
        ContractDocumentType.DUNNING_L2.value: 8,
        ContractDocumentType.DUNNING_L3.value: 9,
        ContractDocumentType.TERMINATION.value: 10,
    },
    ChainType.PROCUREMENT.value: {
        ProcurementDocumentType.REQUISITION.value: 1,
        ProcurementDocumentType.PURCHASE_ORDER.value: 2,
        ProcurementDocumentType.ORDER_CONFIRMATION.value: 3,
        ProcurementDocumentType.DELIVERY_NOTE.value: 4,
        ProcurementDocumentType.GOODS_RECEIPT.value: 5,
        ProcurementDocumentType.QUALITY_CONTROL.value: 6,
        ProcurementDocumentType.INVOICE.value: 7,
        ProcurementDocumentType.PAYMENT.value: 8,
    },
}


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class ExtendedChainDocument:
    """Ein Dokument in einer erweiterten Kette mit zusaetzlichen Metadaten."""

    id: UUID
    document_type: str
    chain_position: int
    filename: str
    document_date: Optional[datetime]
    amount: Optional[Decimal]
    reference_numbers: Dict[str, str]
    created_at: datetime
    # Erweiterte Felder
    chain_type: ChainType
    sub_type: Optional[str] = None  # z.B. ContractDocumentType, ProcurementDocumentType
    project_id: Optional[UUID] = None
    entity_id: Optional[UUID] = None
    entity_name: Optional[str] = None
    ml_confidence: Optional[float] = None  # ML-basierte Matching-Konfidenz
    ml_features: Optional[Dict[str, float]] = None  # Feature-Scores
    status: str = "active"  # active, completed, cancelled


@dataclass
class ExtendedDocumentChain:
    """Eine erweiterte Auftragskette mit zusaetzlichen Funktionen."""

    chain_id: str
    chain_type: ChainType
    company_id: UUID
    documents: List[ExtendedChainDocument]
    document_count: int
    chain_started_at: datetime
    chain_updated_at: datetime

    # Dokumenttyp-Flags (dynamisch basierend auf chain_type)
    document_type_flags: Dict[str, bool] = field(default_factory=dict)

    # Statistiken
    open_discrepancies: int = 0
    total_amount: Optional[Decimal] = None
    is_complete: bool = False
    completion_percentage: float = 0.0

    # Projekt-Integration
    project_id: Optional[UUID] = None
    project_code: Optional[str] = None
    project_name: Optional[str] = None

    # Entity-Information
    primary_entity_id: Optional[UUID] = None
    primary_entity_name: Optional[str] = None

    # Visualisierung
    visualization_data: Optional[Dict[str, Any]] = None

    # Status
    status: str = "active"  # active, completed, cancelled, disputed


@dataclass
class MLMatchResult:
    """ML-basiertes Matching-Ergebnis mit erweiterten Metriken."""

    matched: bool
    chain_id: Optional[str]
    chain_type: ChainType
    relationship_type: Optional[RelationshipType]
    confidence: float
    matched_documents: List[UUID]
    match_reason: str

    # ML-spezifische Metriken
    ml_features: Dict[str, float] = field(default_factory=dict)
    feature_contributions: Dict[str, float] = field(default_factory=dict)
    model_version: str = "v1.0"
    inference_time_ms: float = 0.0


@dataclass
class ChainVisualization:
    """Visualisierungsdaten fuer eine Dokumentenkette."""

    chain_id: str
    chain_type: ChainType
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    layout: str = "horizontal"  # horizontal, vertical, radial
    total_amount: Optional[Decimal] = None
    status: str = "active"
    completion_percentage: float = 0.0
    critical_path: List[str] = field(default_factory=list)
    bottlenecks: List[Dict[str, Any]] = field(default_factory=list)


# =============================================================================
# MAIN SERVICE
# =============================================================================


class ExtendedDocumentChainServiceV2:
    """
    Erweiterter Document Chain Service V2.

    Erweitert den bestehenden DocumentChainService um:
    - Neue Chain-Typen (Vertragserfuellung, Beschaffung, Projekt)
    - ML-basiertes Auto-Matching
    - Visualisierungs-API
    - Projekt-Integration
    - Erweiterte Metriken
    """

    # ML-Konfidenz-Schwellenwerte
    ML_CONFIDENCE_HIGH = 0.90
    ML_CONFIDENCE_MEDIUM = 0.75
    ML_CONFIDENCE_LOW = 0.60
    ML_MIN_AUTO_LINK = 0.80

    # Feature-Gewichtungen fuer ML-Matching
    ML_FEATURE_WEIGHTS = {
        "reference_match": 0.35,
        "amount_similarity": 0.20,
        "date_proximity": 0.15,
        "entity_match": 0.15,
        "document_type_sequence": 0.10,
        "text_similarity": 0.05,
    }

    def __init__(self) -> None:
        """Initialisiert den erweiterten Service."""
        # Basisservice fuer Kompatibilitaet
        self._base_service = DocumentChainService()

    # =========================================================================
    # CHAIN CREATION (Erweitert)
    # =========================================================================

    async def create_extended_chain(
        self,
        db: AsyncSession,
        documents: List[UUID],
        company_id: UUID,
        user_id: UUID,
        chain_type: ChainType,
        project_id: Optional[UUID] = None,
        chain_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Erstellt eine erweiterte Dokumentenkette.

        Args:
            db: Datenbank-Session
            documents: Liste von Dokument-IDs
            company_id: Firmen-ID
            user_id: Benutzer-ID
            chain_type: Typ der Kette
            project_id: Optionale Projekt-ID
            chain_id: Optionale Chain-ID (sonst auto-generiert)
            metadata: Zusaetzliche Metadaten

        Returns:
            Chain-ID der erstellten Kette
        """
        from app.db.models import Document

        if not documents:
            raise ValueError("Mindestens ein Dokument erforderlich")

        # Chain-ID generieren
        if not chain_id:
            prefix = self._get_chain_prefix(chain_type)
            year = utc_now().year
            stmt = select(func.count()).select_from(Document).where(
                and_(
                    Document.company_id == company_id,
                    Document.chain_id.isnot(None),
                    Document.chain_id.like(f"{prefix}-{year}-%"),
                )
            )
            result = await db.execute(stmt)
            count = result.scalar() or 0
            chain_id = f"{prefix}-{year}-{count + 1:05d}"

        # Positionsmap fuer Chain-Typ holen
        position_map = EXTENDED_CHAIN_POSITIONS.get(
            chain_type.value,
            CHAIN_POSITIONS  # Fallback auf Standard
        )

        # Dokumente laden und Chain zuweisen
        for idx, doc_id in enumerate(documents):
            doc_stmt = select(Document).where(Document.id == doc_id)
            result = await db.execute(doc_stmt)
            doc = result.scalar_one_or_none()

            if not doc:
                logger.warning(
                    "document_not_found_for_chain",
                    document_id=str(doc_id),
                    chain_id=chain_id,
                )
                continue

            # Position basierend auf Dokumenttyp oder Index
            doc_type = doc.document_type
            if isinstance(position_map, dict):
                position = position_map.get(doc_type, idx + 1)
            else:
                position = idx + 1

            doc.chain_id = chain_id
            doc.chain_position = position

            # Erstes Dokument = Root
            if idx == 0:
                doc.chain_root_document_id = None
            else:
                doc.chain_root_document_id = documents[0]

            # Chain-Metadaten in document_metadata speichern
            if doc.document_metadata is None:
                doc.document_metadata = {}
            doc.document_metadata["chain_type"] = chain_type.value
            if project_id:
                doc.document_metadata["project_id"] = str(project_id)
            if metadata:
                doc.document_metadata["chain_metadata"] = metadata

        await db.flush()

        # Projekt-Verknuepfung erstellen (falls angegeben)
        if project_id:
            await self._create_project_chain_link(
                db, chain_id, project_id, company_id, user_id
            )

        logger.info(
            "extended_chain_created",
            chain_id=chain_id,
            chain_type=chain_type.value,
            document_count=len(documents),
            project_id=str(project_id) if project_id else None,
        )

        return chain_id

    async def create_contract_chain(
        self,
        db: AsyncSession,
        contract_document_id: UUID,
        company_id: UUID,
        user_id: UUID,
        contract_number: Optional[str] = None,
    ) -> str:
        """
        Erstellt eine Vertragserfuellungskette.

        Startet mit dem Vertragsdokument und ermoeglicht
        die Verkettung von Lieferungen, Mahnungen, etc.

        Args:
            db: Datenbank-Session
            contract_document_id: ID des Vertragsdokuments
            company_id: Firmen-ID
            user_id: Benutzer-ID
            contract_number: Optionale Vertragsnummer

        Returns:
            Chain-ID
        """
        metadata: Dict[str, Any] = {}
        if contract_number:
            metadata["contract_number"] = contract_number

        return await self.create_extended_chain(
            db=db,
            documents=[contract_document_id],
            company_id=company_id,
            user_id=user_id,
            chain_type=ChainType.CONTRACT_FULFILLMENT,
            metadata=metadata,
        )

    async def create_procurement_chain(
        self,
        db: AsyncSession,
        purchase_order_id: UUID,
        company_id: UUID,
        user_id: UUID,
        order_number: Optional[str] = None,
        supplier_id: Optional[UUID] = None,
    ) -> str:
        """
        Erstellt eine Beschaffungskette.

        Startet mit der Bestellung und ermoeglicht das Tracking
        von Wareneingang, QC, Rechnung, etc.

        Args:
            db: Datenbank-Session
            purchase_order_id: ID des Bestelldokuments
            company_id: Firmen-ID
            user_id: Benutzer-ID
            order_number: Optionale Bestellnummer
            supplier_id: Optionale Lieferanten-ID

        Returns:
            Chain-ID
        """
        metadata: Dict[str, Any] = {}
        if order_number:
            metadata["order_number"] = order_number
        if supplier_id:
            metadata["supplier_id"] = str(supplier_id)

        return await self.create_extended_chain(
            db=db,
            documents=[purchase_order_id],
            company_id=company_id,
            user_id=user_id,
            chain_type=ChainType.PROCUREMENT,
            metadata=metadata,
        )

    async def create_project_chain(
        self,
        db: AsyncSession,
        project_id: UUID,
        documents: List[UUID],
        company_id: UUID,
        user_id: UUID,
    ) -> str:
        """
        Erstellt eine projektbasierte Dokumentenkette.

        Gruppiert alle Dokumente unter einer Projekt-ID.

        Args:
            db: Datenbank-Session
            project_id: Projekt-ID
            documents: Liste von Dokument-IDs
            company_id: Firmen-ID
            user_id: Benutzer-ID

        Returns:
            Chain-ID
        """
        return await self.create_extended_chain(
            db=db,
            documents=documents,
            company_id=company_id,
            user_id=user_id,
            chain_type=ChainType.PROJECT,
            project_id=project_id,
        )

    # =========================================================================
    # CHAIN RETRIEVAL (Erweitert)
    # =========================================================================

    async def get_extended_chain(
        self,
        db: AsyncSession,
        chain_id: str,
        company_id: UUID,
        include_visualization: bool = False,
    ) -> Optional[ExtendedDocumentChain]:
        """
        Holt eine erweiterte Dokumentenkette.

        Args:
            db: Datenbank-Session
            chain_id: Chain-ID
            company_id: Firmen-ID
            include_visualization: Ob Visualisierungsdaten inkludiert werden sollen

        Returns:
            ExtendedDocumentChain oder None
        """
        from app.db.models import Document, DocumentChainDiscrepancy
        from app.db.models_project import Project, ProjectDocumentChain

        # Dokumente laden
        stmt = (
            select(Document)
            .where(
                and_(
                    Document.chain_id == chain_id,
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                )
            )
            .order_by(Document.chain_position.asc(), Document.created_at.asc())
        )

        result = await db.execute(stmt)
        documents = result.scalars().all()

        if not documents:
            return None

        # Chain-Typ aus erstem Dokument ermitteln
        first_doc = documents[0]
        chain_type_value = None
        if first_doc.document_metadata:
            chain_type_value = first_doc.document_metadata.get("chain_type")

        chain_type = ChainType(chain_type_value) if chain_type_value else ChainType.QUOTE_TO_INVOICE

        # Discrepancies zaehlen
        discrepancy_stmt = select(func.count()).select_from(DocumentChainDiscrepancy).where(
            and_(
                DocumentChainDiscrepancy.chain_id == chain_id,
                DocumentChainDiscrepancy.is_resolved == False,
            )
        )
        discrepancy_result = await db.execute(discrepancy_stmt)
        open_discrepancies = discrepancy_result.scalar() or 0

        # Projekt-Info laden (falls vorhanden)
        project_id: Optional[UUID] = None
        project_code: Optional[str] = None
        project_name: Optional[str] = None

        project_chain_stmt = select(ProjectDocumentChain).where(
            and_(
                ProjectDocumentChain.chain_id == chain_id,
                ProjectDocumentChain.company_id == company_id,
            )
        )
        project_chain_result = await db.execute(project_chain_stmt)
        project_chain = project_chain_result.scalar_one_or_none()

        if project_chain:
            project_id = project_chain.project_id
            # Projekt-Details laden
            project_stmt = select(Project).where(Project.id == project_id)
            project_result = await db.execute(project_stmt)
            project = project_result.scalar_one_or_none()
            if project:
                project_code = project.code
                project_name = project.name

        # Chain-Dokumente erstellen
        chain_documents: List[ExtendedChainDocument] = []
        doc_types: Set[str] = set()
        total_amount = Decimal("0")

        for doc in documents:
            doc_types.add(doc.document_type)

            # Referenznummern und Betrag extrahieren
            refs: Dict[str, str] = {}
            amount: Optional[Decimal] = None
            entity_id: Optional[UUID] = None
            entity_name: Optional[str] = None

            if doc.document_metadata:
                extracted = doc.document_metadata.get("extracted_data", {})
                refs = {
                    k: v for k, v in {
                        "order_number": extracted.get("order_number"),
                        "invoice_number": extracted.get("invoice_number"),
                        "contract_number": extracted.get("contract_number"),
                        "delivery_note_number": extracted.get("delivery_note_number"),
                        "quotation_number": extracted.get("quotation_number"),
                        "purchase_order_number": extracted.get("purchase_order_number"),
                    }.items() if v
                }

                try:
                    amount_str = extracted.get("total_amount", extracted.get("amount"))
                    if amount_str:
                        amount = Decimal(str(amount_str))
                        total_amount += amount
                except (ValueError, TypeError):
                    pass

                # Entity-Info
                if doc.business_entity_id:
                    entity_id = doc.business_entity_id
                    if doc.business_entity:
                        entity_name = doc.business_entity.name

            # ML-Konfidenz aus Metadaten
            ml_confidence: Optional[float] = None
            ml_features: Optional[Dict[str, float]] = None
            if doc.document_metadata:
                ml_confidence = doc.document_metadata.get("ml_match_confidence")
                ml_features = doc.document_metadata.get("ml_features")

            chain_documents.append(ExtendedChainDocument(
                id=doc.id,
                document_type=doc.document_type,
                chain_position=doc.chain_position or 0,
                filename=doc.original_filename,
                document_date=doc.processed_date or doc.created_at,
                amount=amount,
                reference_numbers=refs,
                created_at=doc.created_at,
                chain_type=chain_type,
                sub_type=doc.document_type,
                project_id=project_id,
                entity_id=entity_id,
                entity_name=entity_name,
                ml_confidence=ml_confidence,
                ml_features=ml_features,
            ))

        # Dokumenttyp-Flags generieren
        doc_type_flags = self._generate_type_flags(chain_type, doc_types)

        # Completion berechnen
        completion_pct = self._calculate_completion(chain_type, doc_types)
        is_complete = completion_pct >= 100.0

        # Visualisierungsdaten
        visualization_data: Optional[Dict[str, Any]] = None
        if include_visualization:
            viz = await self.get_chain_visualization(db, chain_id, company_id)
            if viz:
                visualization_data = {
                    "nodes": viz.nodes,
                    "edges": viz.edges,
                    "layout": viz.layout,
                    "critical_path": viz.critical_path,
                }

        # Primaere Entity ermitteln
        primary_entity_id: Optional[UUID] = None
        primary_entity_name: Optional[str] = None
        for doc in chain_documents:
            if doc.entity_id:
                primary_entity_id = doc.entity_id
                primary_entity_name = doc.entity_name
                break

        return ExtendedDocumentChain(
            chain_id=chain_id,
            chain_type=chain_type,
            company_id=company_id,
            documents=chain_documents,
            document_count=len(chain_documents),
            chain_started_at=min(d.created_at for d in chain_documents),
            chain_updated_at=max(d.created_at for d in chain_documents),
            document_type_flags=doc_type_flags,
            open_discrepancies=open_discrepancies,
            total_amount=total_amount if total_amount > 0 else None,
            is_complete=is_complete,
            completion_percentage=completion_pct,
            project_id=project_id,
            project_code=project_code,
            project_name=project_name,
            primary_entity_id=primary_entity_id,
            primary_entity_name=primary_entity_name,
            visualization_data=visualization_data,
        )

    async def get_chains_by_project(
        self,
        db: AsyncSession,
        project_id: UUID,
        company_id: UUID,
    ) -> List[ExtendedDocumentChain]:
        """
        Holt alle Ketten eines Projekts.

        Args:
            db: Datenbank-Session
            project_id: Projekt-ID
            company_id: Firmen-ID

        Returns:
            Liste von ExtendedDocumentChain
        """
        from app.db.models_project import ProjectDocumentChain

        # Alle Chain-IDs fuer das Projekt holen
        stmt = select(ProjectDocumentChain.chain_id).where(
            and_(
                ProjectDocumentChain.project_id == project_id,
                ProjectDocumentChain.company_id == company_id,
            )
        )
        result = await db.execute(stmt)
        chain_ids = [row[0] for row in result.fetchall()]

        # Chains laden
        chains: List[ExtendedDocumentChain] = []
        for chain_id in chain_ids:
            chain = await self.get_extended_chain(db, chain_id, company_id)
            if chain:
                chains.append(chain)

        return chains

    # =========================================================================
    # ML-BASIERTES AUTO-MATCHING
    # =========================================================================

    async def ml_auto_match(
        self,
        db: AsyncSession,
        document_id: UUID,
        company_id: UUID,
        chain_types: Optional[List[ChainType]] = None,
    ) -> List[MLMatchResult]:
        """
        ML-basiertes Auto-Matching fuer ein Dokument.

        Verwendet mehrere Features fuer praezises Matching:
        - Referenznummern (hoechste Gewichtung)
        - Betragsaehnlichkeit
        - Datumsnaehe
        - Entity-Match
        - Dokumenttyp-Sequenz
        - Text-Aehnlichkeit

        Args:
            db: Datenbank-Session
            document_id: Zu matchendes Dokument
            company_id: Firmen-ID
            chain_types: Optionale Filter auf bestimmte Chain-Typen

        Returns:
            Liste von MLMatchResult, sortiert nach Konfidenz
        """
        import time
        from app.db.models import Document

        start_time = time.time()

        # Dokument laden
        doc = await db.get(Document, document_id)
        if not doc:
            return []

        # Features extrahieren
        doc_features = self._extract_document_features(doc)

        results: List[MLMatchResult] = []

        # Kandidaten suchen (optimierte Query)
        candidates = await self._get_matching_candidates(
            db, doc, company_id, chain_types
        )

        for candidate, existing_chain_id in candidates:
            # ML-Scoring
            feature_scores = self._calculate_feature_scores(doc_features, candidate)
            total_score = sum(
                score * self.ML_FEATURE_WEIGHTS.get(feature, 0.0)
                for feature, score in feature_scores.items()
            )

            if total_score >= self.ML_CONFIDENCE_LOW:
                # Chain-Typ ableiten
                chain_type = self._infer_chain_type(doc.document_type, candidate.document_type)
                relationship_type = self._infer_relationship_type(doc.document_type, candidate.document_type)

                # Match-Grund generieren
                match_reason = self._generate_match_reason(feature_scores, doc_features, candidate)

                inference_time = (time.time() - start_time) * 1000

                results.append(MLMatchResult(
                    matched=True,
                    chain_id=existing_chain_id,
                    chain_type=chain_type,
                    relationship_type=relationship_type,
                    confidence=total_score,
                    matched_documents=[candidate.id],
                    match_reason=match_reason,
                    ml_features=feature_scores,
                    feature_contributions={
                        feature: score * self.ML_FEATURE_WEIGHTS.get(feature, 0.0)
                        for feature, score in feature_scores.items()
                    },
                    model_version="v1.0",
                    inference_time_ms=inference_time,
                ))

        # Nach Konfidenz sortieren
        results.sort(key=lambda x: x.confidence, reverse=True)

        # Top 10 zurueckgeben
        return results[:10]

    async def ml_auto_link(
        self,
        db: AsyncSession,
        document_id: UUID,
        company_id: UUID,
        user_id: UUID,
        min_confidence: float = 0.80,
    ) -> Optional[str]:
        """
        Automatisches Linking basierend auf ML-Matching.

        Fuehrt Auto-Linking nur durch wenn Konfidenz ueber Schwellenwert.

        Args:
            db: Datenbank-Session
            document_id: Zu verknuepfendes Dokument
            company_id: Firmen-ID
            user_id: Benutzer-ID
            min_confidence: Minimale Konfidenz fuer Auto-Link

        Returns:
            Chain-ID wenn verknuepft, sonst None
        """
        matches = await self.ml_auto_match(db, document_id, company_id)

        if not matches or matches[0].confidence < min_confidence:
            return None

        best_match = matches[0]

        # In bestehende Chain eingliedern oder neue erstellen
        if best_match.chain_id:
            # Dokument zur bestehenden Chain hinzufuegen
            await self._add_document_to_chain(
                db=db,
                document_id=document_id,
                chain_id=best_match.chain_id,
                company_id=company_id,
                user_id=user_id,
                ml_confidence=best_match.confidence,
                ml_features=best_match.ml_features,
            )
            chain_id = best_match.chain_id
        else:
            # Neue Chain erstellen
            chain_id = await self.create_extended_chain(
                db=db,
                documents=[best_match.matched_documents[0], document_id],
                company_id=company_id,
                user_id=user_id,
                chain_type=best_match.chain_type,
            )

        logger.info(
            "ml_auto_link_success",
            document_id=str(document_id),
            chain_id=chain_id,
            confidence=best_match.confidence,
            match_reason=best_match.match_reason,
        )

        return chain_id

    # =========================================================================
    # VISUALIZATION API
    # =========================================================================

    async def get_chain_visualization(
        self,
        db: AsyncSession,
        chain_id: str,
        company_id: UUID,
        layout: str = "horizontal",
    ) -> Optional[ChainVisualization]:
        """
        Generiert Visualisierungsdaten fuer eine Kette.

        Args:
            db: Datenbank-Session
            chain_id: Chain-ID
            company_id: Firmen-ID
            layout: Layout-Typ (horizontal, vertical, radial)

        Returns:
            ChainVisualization oder None
        """
        from app.db.models import Document, DocumentRelationship, DocumentChainDiscrepancy

        # Dokumente laden
        stmt = (
            select(Document)
            .where(
                and_(
                    Document.chain_id == chain_id,
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                )
            )
            .order_by(Document.chain_position.asc())
        )

        result = await db.execute(stmt)
        documents = list(result.scalars().all())

        if not documents:
            return None

        # Chain-Typ ermitteln
        chain_type_value = None
        if documents[0].document_metadata:
            chain_type_value = documents[0].document_metadata.get("chain_type")
        chain_type = ChainType(chain_type_value) if chain_type_value else ChainType.QUOTE_TO_INVOICE

        # Nodes generieren
        nodes: List[Dict[str, Any]] = []
        total_amount = Decimal("0")

        for idx, doc in enumerate(documents):
            # Betrag extrahieren
            amount: Optional[Decimal] = None
            if doc.document_metadata:
                extracted = doc.document_metadata.get("extracted_data", {})
                try:
                    amount_str = extracted.get("total_amount", extracted.get("amount"))
                    if amount_str:
                        amount = Decimal(str(amount_str))
                        total_amount += amount
                except (ValueError, TypeError):
                    pass

            # Node-Status basierend auf Discrepancies
            node_status = "normal"
            disc_stmt = select(func.count()).select_from(DocumentChainDiscrepancy).where(
                and_(
                    or_(
                        DocumentChainDiscrepancy.source_document_id == doc.id,
                        DocumentChainDiscrepancy.target_document_id == doc.id,
                    ),
                    DocumentChainDiscrepancy.is_resolved == False,
                )
            )
            disc_result = await db.execute(disc_stmt)
            if (disc_result.scalar() or 0) > 0:
                node_status = "warning"

            nodes.append({
                "id": str(doc.id),
                "label": doc.original_filename[:30],
                "type": doc.document_type,
                "position": doc.chain_position or idx,
                "date": doc.processed_date.isoformat() if doc.processed_date else None,
                "amount": float(amount) if amount else None,
                "status": node_status,
                "x": idx * 200 if layout == "horizontal" else 0,
                "y": 0 if layout == "horizontal" else idx * 150,
            })

        # Edges generieren (basierend auf Relationships)
        rel_stmt = select(DocumentRelationship).where(
            DocumentRelationship.chain_id == chain_id
        )
        rel_result = await db.execute(rel_stmt)
        relationships = list(rel_result.scalars().all())

        edges: List[Dict[str, Any]] = []
        for rel in relationships:
            # Discrepancy-Status fuer Edge
            edge_status = "normal"
            disc_edge_stmt = select(func.count()).select_from(DocumentChainDiscrepancy).where(
                and_(
                    DocumentChainDiscrepancy.source_document_id == rel.source_document_id,
                    DocumentChainDiscrepancy.target_document_id == rel.target_document_id,
                    DocumentChainDiscrepancy.is_resolved == False,
                )
            )
            disc_edge_result = await db.execute(disc_edge_stmt)
            if (disc_edge_result.scalar() or 0) > 0:
                edge_status = "warning"

            edges.append({
                "id": str(rel.id),
                "source": str(rel.source_document_id),
                "target": str(rel.target_document_id),
                "type": rel.relationship_type,
                "confidence": rel.confidence_score or rel.confidence or 1.0,
                "status": edge_status,
            })

        # Falls keine expliziten Relationships: Implizite Edges basierend auf Position
        if not edges and len(nodes) > 1:
            for i in range(len(nodes) - 1):
                edges.append({
                    "id": f"implicit-{i}",
                    "source": nodes[i]["id"],
                    "target": nodes[i + 1]["id"],
                    "type": "sequence",
                    "confidence": 1.0,
                    "status": "normal",
                })

        # Critical Path (einfache Heuristik: chronologische Reihenfolge)
        critical_path = [n["id"] for n in sorted(nodes, key=lambda x: x["position"])]

        # Completion berechnen
        doc_types = {n["type"] for n in nodes}
        completion_pct = self._calculate_completion(chain_type, doc_types)

        return ChainVisualization(
            chain_id=chain_id,
            chain_type=chain_type,
            nodes=nodes,
            edges=edges,
            layout=layout,
            total_amount=total_amount if total_amount > 0 else None,
            status="active",
            completion_percentage=completion_pct,
            critical_path=critical_path,
            bottlenecks=[],  # Kann spaeter erweitert werden
        )

    # =========================================================================
    # CONTRACT FULFILLMENT SPECIFICS
    # =========================================================================

    async def add_dunning_to_contract_chain(
        self,
        db: AsyncSession,
        chain_id: str,
        dunning_document_id: UUID,
        dunning_level: int,
        company_id: UUID,
        user_id: UUID,
    ) -> bool:
        """
        Fuegt eine Mahnung zur Vertragserfuellungskette hinzu.

        Args:
            db: Datenbank-Session
            chain_id: Chain-ID
            dunning_document_id: ID des Mahnungsdokuments
            dunning_level: Mahnstufe (1-3)
            company_id: Firmen-ID
            user_id: Benutzer-ID

        Returns:
            True bei Erfolg
        """
        from app.db.models import Document

        # Chain-Typ pruefen
        chain = await self.get_extended_chain(db, chain_id, company_id)
        if not chain or chain.chain_type != ChainType.CONTRACT_FULFILLMENT:
            logger.warning(
                "add_dunning_invalid_chain",
                chain_id=chain_id,
                chain_type=chain.chain_type.value if chain else None,
            )
            return False

        # Mahndokument laden und aktualisieren
        doc = await db.get(Document, dunning_document_id)
        if not doc:
            return False

        # Dokumenttyp setzen basierend auf Mahnstufe
        dunning_type_map = {
            0: ContractDocumentType.REMINDER.value,
            1: ContractDocumentType.DUNNING_L1.value,
            2: ContractDocumentType.DUNNING_L2.value,
            3: ContractDocumentType.DUNNING_L3.value,
        }
        doc_subtype = dunning_type_map.get(dunning_level, ContractDocumentType.DUNNING_L1.value)

        # Position fuer Mahnung
        position = EXTENDED_CHAIN_POSITIONS[ChainType.CONTRACT_FULFILLMENT.value].get(
            doc_subtype, 7 + dunning_level
        )

        doc.chain_id = chain_id
        doc.chain_position = position
        doc.chain_root_document_id = chain.documents[0].id if chain.documents else None

        if doc.document_metadata is None:
            doc.document_metadata = {}
        doc.document_metadata["chain_type"] = ChainType.CONTRACT_FULFILLMENT.value
        doc.document_metadata["dunning_level"] = dunning_level

        await db.flush()

        logger.info(
            "dunning_added_to_contract_chain",
            chain_id=chain_id,
            dunning_level=dunning_level,
            document_id=str(dunning_document_id),
        )

        return True

    # =========================================================================
    # PROCUREMENT CHAIN SPECIFICS
    # =========================================================================

    async def add_quality_control_to_procurement(
        self,
        db: AsyncSession,
        chain_id: str,
        qc_document_id: UUID,
        qc_passed: bool,
        qc_notes: Optional[str],
        company_id: UUID,
        user_id: UUID,
    ) -> bool:
        """
        Fuegt ein QC-Protokoll zur Beschaffungskette hinzu.

        Args:
            db: Datenbank-Session
            chain_id: Chain-ID
            qc_document_id: ID des QC-Dokuments
            qc_passed: Ob QC bestanden
            qc_notes: Optionale QC-Notizen
            company_id: Firmen-ID
            user_id: Benutzer-ID

        Returns:
            True bei Erfolg
        """
        from app.db.models import Document

        # Chain-Typ pruefen
        chain = await self.get_extended_chain(db, chain_id, company_id)
        if not chain or chain.chain_type != ChainType.PROCUREMENT:
            logger.warning(
                "add_qc_invalid_chain",
                chain_id=chain_id,
            )
            return False

        # QC-Dokument laden und aktualisieren
        doc = await db.get(Document, qc_document_id)
        if not doc:
            return False

        position = EXTENDED_CHAIN_POSITIONS[ChainType.PROCUREMENT.value].get(
            ProcurementDocumentType.QUALITY_CONTROL.value, 6
        )

        doc.chain_id = chain_id
        doc.chain_position = position
        doc.chain_root_document_id = chain.documents[0].id if chain.documents else None

        if doc.document_metadata is None:
            doc.document_metadata = {}
        doc.document_metadata["chain_type"] = ChainType.PROCUREMENT.value
        doc.document_metadata["qc_passed"] = qc_passed
        if qc_notes:
            doc.document_metadata["qc_notes"] = qc_notes

        await db.flush()

        # Discrepancy erstellen falls QC fehlgeschlagen
        if not qc_passed:
            from app.db.models import DocumentChainDiscrepancy

            # Letzten Wareneingang finden
            goods_receipt_doc = None
            for chain_doc in chain.documents:
                if chain_doc.sub_type == ProcurementDocumentType.GOODS_RECEIPT.value:
                    goods_receipt_doc = chain_doc
                    break

            if goods_receipt_doc:
                discrepancy = DocumentChainDiscrepancy(
                    id=uuid4(),
                    chain_id=chain_id,
                    source_document_id=goods_receipt_doc.id,
                    target_document_id=qc_document_id,
                    discrepancy_type="quality_issue",
                    field_name="quality_control",
                    expected_value="passed",
                    actual_value="failed",
                    severity="error",
                    description=qc_notes or "Qualitaetskontrolle fehlgeschlagen",
                    is_resolved=False,
                    company_id=company_id,
                )
                db.add(discrepancy)
                await db.flush()

        logger.info(
            "qc_added_to_procurement_chain",
            chain_id=chain_id,
            qc_passed=qc_passed,
            document_id=str(qc_document_id),
        )

        return True

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _get_chain_prefix(self, chain_type: ChainType) -> str:
        """Gibt Prefix fuer Chain-ID basierend auf Typ zurueck."""
        prefixes = {
            ChainType.QUOTE_TO_ORDER: "CHAIN",
            ChainType.ORDER_TO_DELIVERY: "CHAIN",
            ChainType.DELIVERY_TO_INVOICE: "CHAIN",
            ChainType.QUOTE_TO_INVOICE: "CHAIN",
            ChainType.CONTRACT_FULFILLMENT: "CONTRACT",
            ChainType.PROCUREMENT: "PROC",
            ChainType.PROJECT: "PROJECT",
        }
        return prefixes.get(chain_type, "CHAIN")

    def _generate_type_flags(
        self,
        chain_type: ChainType,
        doc_types: Set[str],
    ) -> Dict[str, bool]:
        """Generiert Dokumenttyp-Flags basierend auf Chain-Typ."""
        if chain_type == ChainType.CONTRACT_FULFILLMENT:
            return {
                "has_contract": ContractDocumentType.CONTRACT.value in doc_types,
                "has_delivery": ContractDocumentType.DELIVERY.value in doc_types,
                "has_invoice": ContractDocumentType.INVOICE.value in doc_types or "invoice" in doc_types,
                "has_dunning": any(
                    d in doc_types for d in [
                        ContractDocumentType.DUNNING_L1.value,
                        ContractDocumentType.DUNNING_L2.value,
                        ContractDocumentType.DUNNING_L3.value,
                    ]
                ),
            }
        elif chain_type == ChainType.PROCUREMENT:
            return {
                "has_purchase_order": ProcurementDocumentType.PURCHASE_ORDER.value in doc_types or "purchase_order" in doc_types,
                "has_goods_receipt": ProcurementDocumentType.GOODS_RECEIPT.value in doc_types,
                "has_quality_control": ProcurementDocumentType.QUALITY_CONTROL.value in doc_types,
                "has_invoice": ProcurementDocumentType.INVOICE.value in doc_types or "invoice" in doc_types,
            }
        else:
            # Standard-Flags (aus v1)
            return {
                "has_quote": "quote" in doc_types,
                "has_order": "order" in doc_types,
                "has_delivery_note": "delivery_note" in doc_types,
                "has_invoice": "invoice" in doc_types,
                "has_credit_note": "credit_note" in doc_types,
            }

    def _calculate_completion(
        self,
        chain_type: ChainType,
        doc_types: Set[str],
    ) -> float:
        """Berechnet Completion-Prozentsatz basierend auf Chain-Typ."""
        if chain_type == ChainType.CONTRACT_FULFILLMENT:
            required = {
                ContractDocumentType.CONTRACT.value: 25,
                ContractDocumentType.DELIVERY.value: 25,
                ContractDocumentType.INVOICE.value: 25,
            }
            # Invoice kann auch als "invoice" kommen
            if "invoice" in doc_types:
                doc_types.add(ContractDocumentType.INVOICE.value)
        elif chain_type == ChainType.PROCUREMENT:
            required = {
                ProcurementDocumentType.PURCHASE_ORDER.value: 20,
                ProcurementDocumentType.ORDER_CONFIRMATION.value: 15,
                ProcurementDocumentType.DELIVERY_NOTE.value: 15,
                ProcurementDocumentType.GOODS_RECEIPT.value: 20,
                ProcurementDocumentType.INVOICE.value: 30,
            }
            # Alternative Namen mappen
            if "purchase_order" in doc_types:
                doc_types.add(ProcurementDocumentType.PURCHASE_ORDER.value)
            if "delivery_note" in doc_types:
                doc_types.add(ProcurementDocumentType.DELIVERY_NOTE.value)
            if "invoice" in doc_types:
                doc_types.add(ProcurementDocumentType.INVOICE.value)
        else:
            required = {
                "quote": 15,
                "order": 20,
                "delivery_note": 25,
                "invoice": 40,
            }

        total = sum(
            weight for doc_type, weight in required.items()
            if doc_type in doc_types
        )
        return min(100.0, total)

    def _extract_document_features(
        self,
        doc: "Document",
    ) -> Dict[str, Any]:
        """Extrahiert Features aus einem Dokument fuer ML-Matching."""
        features: Dict[str, Any] = {
            "document_type": doc.document_type,
            "date": doc.processed_date or doc.created_at,
            "entity_id": doc.business_entity_id,
        }

        if doc.document_metadata:
            extracted = doc.document_metadata.get("extracted_data", {})
            features.update({
                "amount": extracted.get("total_amount") or extracted.get("amount"),
                "order_number": extracted.get("order_number"),
                "invoice_number": extracted.get("invoice_number"),
                "contract_number": extracted.get("contract_number"),
                "customer_number": extracted.get("customer_number"),
                "purchase_order_number": extracted.get("purchase_order_number"),
            })

        return features

    async def _get_matching_candidates(
        self,
        db: AsyncSession,
        doc: "Document",
        company_id: UUID,
        chain_types: Optional[List[ChainType]] = None,
    ) -> List[Tuple["Document", Optional[str]]]:
        """Holt potentielle Matching-Kandidaten aus der DB."""
        from app.db.models import Document
        from datetime import timedelta

        # Zeitfenster: 90 Tage
        date_window = (doc.created_at or utc_now()) - timedelta(days=90)

        conditions = [
            Document.company_id == company_id,
            Document.id != doc.id,
            Document.deleted_at.is_(None),
            Document.created_at >= date_window,
        ]

        # Entity-Filter wenn vorhanden
        if doc.business_entity_id:
            conditions.append(Document.business_entity_id == doc.business_entity_id)

        stmt = (
            select(Document)
            .where(and_(*conditions))
            .order_by(Document.created_at.desc())
            .limit(100)  # Max 100 Kandidaten
        )

        result = await db.execute(stmt)
        candidates = list(result.scalars().all())

        return [(c, c.chain_id) for c in candidates]

    def _calculate_feature_scores(
        self,
        doc_features: Dict[str, Any],
        candidate: "Document",
    ) -> Dict[str, float]:
        """Berechnet Feature-Scores zwischen Dokument und Kandidat."""
        scores: Dict[str, float] = {}

        candidate_features = self._extract_document_features(candidate)

        # 1. Reference Match (0 oder 1)
        ref_match = 0.0
        for ref_type in ["order_number", "invoice_number", "contract_number", "purchase_order_number"]:
            if doc_features.get(ref_type) and candidate_features.get(ref_type):
                if doc_features[ref_type] == candidate_features[ref_type]:
                    ref_match = 1.0
                    break
        scores["reference_match"] = ref_match

        # 2. Amount Similarity (0-1)
        amount_score = 0.0
        if doc_features.get("amount") and candidate_features.get("amount"):
            try:
                d_amt = Decimal(str(doc_features["amount"]))
                c_amt = Decimal(str(candidate_features["amount"]))
                if d_amt > 0 and c_amt > 0:
                    diff_pct = abs(d_amt - c_amt) / max(d_amt, c_amt)
                    amount_score = max(0.0, 1.0 - float(diff_pct))
            except (ValueError, TypeError, ZeroDivisionError):
                pass
        scores["amount_similarity"] = amount_score

        # 3. Date Proximity (0-1, max 30 Tage)
        date_score = 0.0
        if doc_features.get("date") and candidate_features.get("date"):
            d_date = doc_features["date"]
            c_date = candidate_features["date"]
            if isinstance(d_date, datetime) and isinstance(c_date, datetime):
                days_diff = abs((d_date - c_date).days)
                date_score = max(0.0, 1.0 - (days_diff / 30.0))
        scores["date_proximity"] = date_score

        # 4. Entity Match (0 oder 1)
        entity_score = 0.0
        if doc_features.get("entity_id") and candidate_features.get("entity_id"):
            if doc_features["entity_id"] == candidate_features["entity_id"]:
                entity_score = 1.0
        scores["entity_match"] = entity_score

        # 5. Document Type Sequence (logische Abfolge)
        type_score = 0.0
        d_type = doc_features.get("document_type")
        c_type = candidate_features.get("document_type")
        valid_sequences = [
            ("quote", "order"),
            ("order", "delivery_note"),
            ("delivery_note", "invoice"),
            ("purchase_order", "order_confirmation"),
            ("order_confirmation", "delivery_note"),
            ("contract", "invoice"),
        ]
        if (c_type, d_type) in valid_sequences or (d_type, c_type) in valid_sequences:
            type_score = 1.0
        scores["document_type_sequence"] = type_score

        # 6. Text Similarity (vereinfacht: Kundennummer)
        text_score = 0.0
        if doc_features.get("customer_number") and candidate_features.get("customer_number"):
            if doc_features["customer_number"] == candidate_features["customer_number"]:
                text_score = 1.0
        scores["text_similarity"] = text_score

        return scores

    def _infer_chain_type(
        self,
        doc_type: str,
        candidate_type: str,
    ) -> ChainType:
        """Leitet Chain-Typ aus Dokumenttypen ab."""
        types = {doc_type, candidate_type}

        if "contract" in types:
            return ChainType.CONTRACT_FULFILLMENT
        if "purchase_order" in types or "goods_receipt" in types:
            return ChainType.PROCUREMENT
        if "quote" in types:
            return ChainType.QUOTE_TO_ORDER

        return ChainType.DELIVERY_TO_INVOICE

    def _infer_relationship_type(
        self,
        doc_type: str,
        candidate_type: str,
    ) -> Optional[RelationshipType]:
        """Leitet Beziehungstyp aus Dokumenttypen ab."""
        mapping = {
            ("quote", "order"): RelationshipType.QUOTE_TO_ORDER,
            ("order", "delivery_note"): RelationshipType.ORDER_TO_DELIVERY,
            ("delivery_note", "invoice"): RelationshipType.DELIVERY_TO_INVOICE,
            ("order", "invoice"): RelationshipType.ORDER_TO_INVOICE,
            ("quote", "invoice"): RelationshipType.QUOTE_TO_INVOICE,
        }

        for (t1, t2), rel in mapping.items():
            if {doc_type, candidate_type} == {t1, t2}:
                return rel

        return RelationshipType.RELATED

    def _generate_match_reason(
        self,
        feature_scores: Dict[str, float],
        doc_features: Dict[str, Any],
        candidate: "Document",
    ) -> str:
        """Generiert menschenlesbaren Match-Grund."""
        reasons = []

        if feature_scores.get("reference_match", 0) >= 0.9:
            for ref_type in ["order_number", "invoice_number", "contract_number"]:
                if doc_features.get(ref_type):
                    reasons.append(f"Gleiche {ref_type.replace('_', ' ').title()}")
                    break

        if feature_scores.get("entity_match", 0) >= 0.9:
            reasons.append("Gleicher Geschaeftspartner")

        if feature_scores.get("amount_similarity", 0) >= 0.9:
            reasons.append("Identischer Betrag")
        elif feature_scores.get("amount_similarity", 0) >= 0.7:
            reasons.append("Aehnlicher Betrag")

        if feature_scores.get("date_proximity", 0) >= 0.8:
            reasons.append("Zeitnaehe")

        if feature_scores.get("document_type_sequence", 0) >= 0.9:
            reasons.append("Logische Dokumentabfolge")

        if not reasons:
            reasons.append("ML-basierte Aehnlichkeit")

        return ", ".join(reasons)

    async def _create_project_chain_link(
        self,
        db: AsyncSession,
        chain_id: str,
        project_id: UUID,
        company_id: UUID,
        user_id: UUID,
    ) -> None:
        """Erstellt Verknuepfung zwischen Chain und Projekt."""
        from app.db.models_project import ProjectDocumentChain

        # Pruefen ob bereits verknuepft
        stmt = select(ProjectDocumentChain).where(
            and_(
                ProjectDocumentChain.chain_id == chain_id,
                ProjectDocumentChain.project_id == project_id,
            )
        )
        result = await db.execute(stmt)
        if result.scalar_one_or_none():
            return  # Bereits verknuepft

        link = ProjectDocumentChain(
            id=uuid4(),
            project_id=project_id,
            chain_id=chain_id,
            company_id=company_id,
            created_by_id=user_id,
        )
        db.add(link)
        await db.flush()

    async def _add_document_to_chain(
        self,
        db: AsyncSession,
        document_id: UUID,
        chain_id: str,
        company_id: UUID,
        user_id: UUID,
        ml_confidence: Optional[float] = None,
        ml_features: Optional[Dict[str, float]] = None,
    ) -> None:
        """Fuegt ein Dokument zu einer bestehenden Chain hinzu."""
        from app.db.models import Document

        doc = await db.get(Document, document_id)
        if not doc:
            return

        # Aktuelle Position in Chain ermitteln
        stmt = select(func.max(Document.chain_position)).where(
            Document.chain_id == chain_id
        )
        result = await db.execute(stmt)
        max_position = result.scalar() or 0

        doc.chain_id = chain_id
        doc.chain_position = max_position + 1

        # Root-Dokument finden
        root_stmt = select(Document.id).where(
            and_(
                Document.chain_id == chain_id,
                Document.chain_root_document_id.is_(None),
            )
        )
        root_result = await db.execute(root_stmt)
        root_doc_id = root_result.scalar()
        if root_doc_id and root_doc_id != document_id:
            doc.chain_root_document_id = root_doc_id

        # ML-Metadaten speichern
        if doc.document_metadata is None:
            doc.document_metadata = {}
        if ml_confidence is not None:
            doc.document_metadata["ml_match_confidence"] = ml_confidence
        if ml_features:
            doc.document_metadata["ml_features"] = ml_features

        await db.flush()


# =============================================================================
# SERVICE FACTORY
# =============================================================================


def get_extended_chain_service() -> ExtendedDocumentChainServiceV2:
    """Factory-Funktion fuer erweiterten Chain Service."""
    return ExtendedDocumentChainServiceV2()
