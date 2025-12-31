"""
Streckengeschäft Detection - Service Layer

Core business logic for Drop Shipment / Triangular Transaction Detection.
Implements the detection cascade, classification, and DATEV integration.

Rechtliche Grundlagen:
- §3 Abs. 6a UStG: Reihengeschäft - Zuordnung der bewegten Lieferung
- §25b UStG: Innergemeinschaftliches Dreiecksgeschäft - Vereinfachungsregelung
- BMF-Schreiben 25.04.2023: Nachweispflichten
"""

import asyncio
import csv
import io
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from uuid import UUID, uuid4

import structlog
from sqlalchemy import and_, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.services.streckengeschaeft.exceptions import (
    ClassificationNotFoundError,
    DatevExportError,
    DocumentNotFoundError,
    ProofDocumentError,
    ValidationConflictError,
)

logger = structlog.get_logger(__name__)

from app.db.models import (
    ClassificationAuditLog,
    ClassificationIndicator,
    ConfidenceLevel,
    DatevStreckengeschaeftAccount,
    Document,
    DropShipmentClassification,
    DropShipmentPosition,
    ProofDocument,
    TransactionParty,
    VatIdRegistry,
)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ClassificationIndicatorMatch:
    """A matched indicator during classification."""
    code: str
    name: str
    weight: int
    is_definitive: bool
    matched_value: Optional[str] = None
    source_field: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ClassificationResult:
    """Complete classification result."""
    classification: DropShipmentClassification
    positions: list = field(default_factory=list)
    parties: list = field(default_factory=list)
    proof_documents: list = field(default_factory=list)
    suggested_actions: list = field(default_factory=list)


@dataclass
class BulkClassifyResult:
    """Result of bulk classification."""
    successful: list = field(default_factory=list)
    failed: list = field(default_factory=list)
    manual_required_count: int = 0


@dataclass
class EUAnalysisResult:
    """Result of EU country analysis."""
    countries: set = field(default_factory=set)
    is_triangular_candidate: bool = False
    indicators: list = field(default_factory=list)


@dataclass
class ZmRecord:
    """Single record for Zusammenfassende Meldung."""
    vat_id: str
    country_code: str
    amount: Decimal
    is_triangular: bool
    classification_id: UUID


@dataclass
class ZmCountryAggregation:
    """Aggregation per country for ZM reporting."""
    country_code: str
    amount: Decimal
    record_count: int


@dataclass
class ZmSummary:
    """Summary for Zusammenfassende Meldung period."""
    period: str  # YYYY-MM
    total_amount: Decimal
    triangular_count: int
    record_count: int
    deadline: date
    records: list = field(default_factory=list)
    by_country: list = field(default_factory=list)  # ZmCountryAggregation list


@dataclass
class DatevExportResult:
    """Result of DATEV export creation."""
    export_id: str
    filename: str
    download_url: Optional[str]
    record_count: int
    zm_record_count: int
    warnings: list = field(default_factory=list)
    content: str = ""


# =============================================================================
# DETECTION SERVICE
# =============================================================================

class DropShipmentDetectionService:
    """
    Service for detecting and classifying Streckengeschäft transactions.

    Implements the detection cascade:
    1. Definitive indicators (ERP markers, legal references)
    2. Party analysis (addresses, VAT IDs)
    3. EU country analysis (triangular detection)
    4. Position-level analysis (mixed invoices)
    5. Document chain validation
    """

    EU_COUNTRY_CODES = {
        'AT', 'BE', 'BG', 'CY', 'CZ', 'DE', 'DK', 'EE', 'ES', 'FI',
        'FR', 'GR', 'HR', 'HU', 'IE', 'IT', 'LT', 'LU', 'LV', 'MT',
        'NL', 'PL', 'PT', 'RO', 'SE', 'SI', 'SK'
    }

    VAT_ID_PATTERNS = {
        'AT': r'^ATU\d{8}$',
        'BE': r'^BE[01]\d{9}$',
        'DE': r'^DE\d{9}$',
        'FR': r'^FR[A-Z0-9]{2}\d{9}$',
        'NL': r'^NL\d{9}B\d{2}$',
        'IT': r'^IT\d{11}$',
        'ES': r'^ES[A-Z0-9]\d{7}[A-Z0-9]$',
        'PL': r'^PL\d{10}$',
        'CZ': r'^CZ\d{8,10}$',
    }

    # Definitive text patterns for §25b detection
    LEGAL_PATTERNS = [
        r'§\s*25\s*b\s*UStG',
        r'Dreiecksgeschäft',
        r'innergemeinschaftliches\s+Dreiecksgeschäft',
        r'triangular\s+transaction',
        r'Reihengeschäft',
    ]

    def __init__(self, session: AsyncSession):
        self.session = session
        self._indicator_config: Optional[list] = None

    async def classify_document(
        self,
        document_id: UUID,
        force_reclassify: bool = False,
        user_id: Optional[UUID] = None,
    ) -> ClassificationResult:
        """Main classification entry point."""
        logger.info(
            "classify_document_started",
            document_id=str(document_id),
            force_reclassify=force_reclassify,
            user_id=str(user_id) if user_id else None,
        )

        document = await self._load_document(document_id)
        if not document:
            logger.warning("classify_document_not_found", document_id=str(document_id))
            raise DocumentNotFoundError(str(document_id))

        if not force_reclassify:
            existing = await self._get_existing_classification(document_id)
            if existing:
                return existing

        indicators = await self._load_indicator_config()
        matched_indicators: list[ClassificationIndicatorMatch] = []
        conflicts: list[dict] = []

        # Step 1: Definitive indicators
        definitive_match = await self._check_definitive_indicators(document, indicators)
        if definitive_match:
            matched_indicators.extend(definitive_match)

        # Step 2: Party analysis
        parties = await self._extract_parties(document)
        party_indicators = self._analyze_parties(parties)
        matched_indicators.extend(party_indicators)

        # Step 3: EU country analysis
        vat_ids = self._extract_vat_ids(document)
        eu_analysis = self._analyze_eu_countries(vat_ids)
        if eu_analysis.indicators:
            matched_indicators.extend(eu_analysis.indicators)

        # Step 4: Position analysis
        positions = await self._analyze_positions(document)

        # Step 5: Determine classification
        classification_data = self._determine_classification(
            matched_indicators=matched_indicators,
            eu_analysis=eu_analysis,
            positions=positions,
            conflicts=conflicts,
        )

        # Step 6: Proof documents
        proof_docs = await self._identify_proof_documents(document_id, classification_data)

        # Step 7: Suggested actions
        suggested_actions = self._generate_suggested_actions(classification_data, proof_docs)

        # Save
        saved = await self._save_classification(
            document_id, classification_data, positions, parties,
            proof_docs, matched_indicators, conflicts, user_id
        )

        logger.info(
            "classify_document_completed",
            document_id=str(document_id),
            classification_id=str(saved.id),
            transaction_type=saved.transaction_type,
            confidence_level=saved.confidence_level,
            confidence_score=saved.confidence_score,
            indicator_count=len(matched_indicators),
            user_id=str(user_id) if user_id else None,
        )

        return ClassificationResult(
            classification=saved,
            positions=positions,
            parties=parties,
            proof_documents=proof_docs,
            suggested_actions=suggested_actions,
        )

    async def bulk_classify(
        self,
        document_ids: list[UUID],
        force_reclassify: bool = False,
        skip_low_confidence: bool = False,
        user_id: Optional[UUID] = None,
    ) -> BulkClassifyResult:
        """Classify multiple documents in parallel.

        Uses asyncio.gather for concurrent processing with error handling.
        """
        logger.info(
            "bulk_classify_started",
            document_count=len(document_ids),
            force_reclassify=force_reclassify,
            skip_low_confidence=skip_low_confidence,
            user_id=str(user_id) if user_id else None,
        )

        result = BulkClassifyResult()

        async def classify_single(doc_id: UUID) -> tuple[UUID, Optional[ClassificationResult], Optional[str]]:
            """Classify single document, returning (id, result, error)."""
            try:
                classification = await self.classify_document(
                    doc_id, force_reclassify, user_id
                )
                return (doc_id, classification, None)
            except Exception as e:
                return (doc_id, None, str(e))

        # Process all documents in parallel
        tasks = [classify_single(doc_id) for doc_id in document_ids]
        classifications = await asyncio.gather(*tasks, return_exceptions=False)

        # Aggregate results
        for doc_id, classification, error in classifications:
            if error:
                logger.warning(
                    "bulk_classify_single_failed",
                    document_id=str(doc_id),
                    error=error,
                )
                result.failed.append({
                    'document_id': str(doc_id),
                    'error': error,
                })
            elif classification:
                if skip_low_confidence and classification.classification.confidence_level in ('low', 'manual_required'):
                    result.manual_required_count += 1
                else:
                    result.successful.append(classification)

        logger.info(
            "bulk_classify_completed",
            total=len(document_ids),
            successful=len(result.successful),
            failed=len(result.failed),
            manual_required=result.manual_required_count,
            user_id=str(user_id) if user_id else None,
        )

        return result

    async def _check_definitive_indicators(
        self,
        document: Document,
        indicators: list,
    ) -> list[ClassificationIndicatorMatch]:
        """Check for 100% definitive indicators."""
        matches = []

        extracted_data = document.extracted_data or {}
        full_text = document.ocr_text or ''

        # Check ERP position type
        position_type = extracted_data.get('position_type', '')
        if position_type.upper() == 'TAS':
            matches.append(ClassificationIndicatorMatch(
                code='ERP_TAS',
                name='SAP Positionstyp TAS',
                weight=100,
                is_definitive=True,
                matched_value='TAS',
                source_field='erp_position_type',
            ))

        # Check for legal references in text
        for pattern in self.LEGAL_PATTERNS:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                matches.append(ClassificationIndicatorMatch(
                    code='LEGAL_25B',
                    name='§25b UStG Hinweis',
                    weight=100,
                    is_definitive=True,
                    matched_value=match.group(),
                    source_field='full_text',
                ))
                break

        # Check procurement type field
        procurement_type = extracted_data.get('procurement_type', '')
        if re.search(r'strecken|drop.?ship', procurement_type, re.IGNORECASE):
            matches.append(ClassificationIndicatorMatch(
                code='ERP_DROPSHIP',
                name='ERP Streckengeschäft-Flag',
                weight=100,
                is_definitive=True,
                matched_value=procurement_type,
                source_field='procurement_type',
            ))

        return matches

    def _extract_vat_ids(self, document: Document) -> list[dict]:
        """Extract all VAT IDs from document."""
        vat_ids = []
        extracted_data = document.extracted_data or {}

        for field_name in ['seller_vat_id', 'buyer_vat_id', 'ship_to_vat_id', 'vat_id']:
            vat_id = extracted_data.get(field_name)
            if vat_id:
                country = self._extract_country_from_vat_id(vat_id)
                if country and not any(v['vat_id'] == vat_id for v in vat_ids):
                    vat_ids.append({
                        'vat_id': vat_id,
                        'country_code': country,
                        'source_field': field_name,
                    })

        # Scan full text
        full_text = document.ocr_text or ''
        for country, pattern in self.VAT_ID_PATTERNS.items():
            for match in re.finditer(pattern, full_text):
                vat_id = match.group()
                if not any(v['vat_id'] == vat_id for v in vat_ids):
                    vat_ids.append({
                        'vat_id': vat_id,
                        'country_code': country,
                        'source_field': 'ocr_text',
                    })

        return vat_ids

    def _extract_country_from_vat_id(self, vat_id: str) -> Optional[str]:
        """Extract ISO country code from VAT ID prefix."""
        if len(vat_id) >= 2:
            prefix = vat_id[:2].upper()
            if prefix in self.EU_COUNTRY_CODES:
                return prefix
        return None

    def _analyze_eu_countries(self, vat_ids: list[dict]) -> EUAnalysisResult:
        """Analyze EU countries from VAT IDs for triangular detection."""
        countries = set()
        for vat in vat_ids:
            if vat['country_code']:
                countries.add(vat['country_code'])

        indicators = []
        is_triangular = len(countries) >= 3

        if is_triangular:
            indicators.append(ClassificationIndicatorMatch(
                code='THREE_EU_VATID',
                name='Drei EU-USt-IdNrn.',
                weight=95,
                is_definitive=False,
                matched_value=', '.join(sorted(countries)),
                source_field='vat_id_analysis',
            ))

        return EUAnalysisResult(
            countries=countries,
            is_triangular_candidate=is_triangular,
            indicators=indicators,
        )

    def _analyze_parties(self, parties: list) -> list[ClassificationIndicatorMatch]:
        """Analyze party addresses for drop shipment indicators."""
        indicators = []

        if len(parties) < 2:
            return indicators

        invoice_party = next((p for p in parties if p.get('party_role') == 'bill_to'), None)
        ship_to_party = next((p for p in parties if p.get('party_role') == 'ship_to'), None)

        if invoice_party and ship_to_party:
            if self._are_different_companies(invoice_party, ship_to_party):
                indicators.append(ClassificationIndicatorMatch(
                    code='ADDR_MISMATCH',
                    name='Abweichende Liefer-/Rechnungsadresse',
                    weight=90,
                    is_definitive=False,
                    matched_value=f"{ship_to_party.get('company_name')} ≠ {invoice_party.get('company_name')}",
                    source_field='address_comparison',
                ))

        return indicators

    def _are_different_companies(self, party1: dict, party2: dict) -> bool:
        """Check if two parties represent different companies."""
        name1 = party1.get('company_name', '')
        name2 = party2.get('company_name', '')

        if not name1 or not name2:
            return False

        name1_norm = self._normalize_company_name(name1)
        name2_norm = self._normalize_company_name(name2)

        from difflib import SequenceMatcher
        similarity = SequenceMatcher(None, name1_norm, name2_norm).ratio()

        return similarity < 0.8

    def _normalize_company_name(self, name: str) -> str:
        """Normalize company name for comparison."""
        name = name.lower()
        for suffix in ['gmbh', 'ag', 'kg', 'ohg', 'e.k.', 'gbr', 'ltd', 'inc', 'co.', '& co']:
            name = name.replace(suffix, '')
        name = re.sub(r'[^\w\s]', '', name)
        return ' '.join(name.split())

    def _determine_classification(
        self,
        matched_indicators: list[ClassificationIndicatorMatch],
        eu_analysis: EUAnalysisResult,
        positions: list,
        conflicts: list[dict],
    ) -> dict:
        """Determine final classification based on all indicators."""
        total_weight = sum(i.weight for i in matched_indicators)
        has_definitive = any(i.is_definitive for i in matched_indicators)

        if has_definitive:
            confidence_level = 'definitive'
            confidence_score = 100
        elif total_weight >= 180:
            confidence_level = 'high'
            confidence_score = min(99, total_weight // 2)
        elif total_weight >= 120:
            confidence_level = 'medium'
            confidence_score = 70 + (total_weight - 120) // 6
        elif total_weight >= 70:
            confidence_level = 'low'
            confidence_score = 50 + (total_weight - 70) // 4
        else:
            confidence_level = 'manual_required'
            confidence_score = max(10, total_weight)

        if conflicts:
            confidence_score = max(10, confidence_score - 20)
            if confidence_level in ('definitive', 'high'):
                confidence_level = 'medium'

        transaction_type = 'standard'
        if has_definitive or total_weight >= 90:
            transaction_type = 'triangular_eu' if eu_analysis.is_triangular_candidate else 'drop_shipment'
        elif total_weight >= 50:
            transaction_type = 'unknown'

        company_role = 'intermediate' if transaction_type in ('triangular_eu', 'drop_shipment') else 'not_applicable'

        vat_category = 'standard_de'
        if transaction_type == 'triangular_eu':
            vat_category = 'triangular_middle'
        elif transaction_type == 'drop_shipment':
            vat_category = 'intra_community'

        zm_relevant = transaction_type in ('triangular_eu', 'drop_shipment')
        zm_marker = '1' if transaction_type == 'triangular_eu' else None

        return {
            'transaction_type': transaction_type,
            'company_role': company_role,
            'vat_category': vat_category,
            'confidence_level': confidence_level,
            'confidence_score': confidence_score,
            'party_count': len(eu_analysis.countries) or 2,
            'eu_countries_involved': list(eu_analysis.countries),
            'zm_relevant': zm_relevant,
            'zm_marker': zm_marker,
        }

    def _generate_suggested_actions(
        self,
        classification: dict,
        proof_documents: list,
    ) -> list[dict]:
        """Generate suggested actions based on classification."""
        actions = []

        missing_proofs = [p for p in proof_documents if not p.get('is_present', True)]
        if missing_proofs:
            actions.append({
                'action_type': 'warning',
                'priority': 'high',
                'title_de': 'Fehlende Belegnachweise',
                'description_de': f"Folgende Belege fehlen: {', '.join(p.get('proof_type', '') for p in missing_proofs)}",
            })

        if classification.get('zm_relevant'):
            actions.append({
                'action_type': 'zm_check',
                'priority': 'medium',
                'title_de': 'ZM-Meldepflicht',
                'description_de': 'Diese Transaktion ist für die Zusammenfassende Meldung relevant. Frist: 25. des Folgemonats.',
            })

        if classification.get('confidence_level') in ('low', 'manual_required'):
            actions.append({
                'action_type': 'create_task',
                'priority': 'high',
                'title_de': 'Manuelle Prüfung erforderlich',
                'description_de': 'Die automatische Klassifikation ist unsicher. Bitte manuell prüfen.',
            })

        return actions

    async def _load_document(self, document_id: UUID) -> Optional[Document]:
        """Load document from database."""
        result = await self.session.execute(
            select(Document).where(Document.id == document_id)
        )
        return result.scalar_one_or_none()

    async def _load_indicator_config(self) -> list[dict]:
        """Load indicator configuration from database."""
        result = await self.session.execute(
            select(ClassificationIndicator).where(ClassificationIndicator.is_active == True)
        )
        indicators = result.scalars().all()
        return [
            {
                'code': ind.indicator_code,
                'name_de': ind.indicator_name_de,
                'weight': ind.weight,
                'is_definitive': ind.is_definitive,
                'detection_pattern': ind.detection_pattern,
                'detection_field': ind.detection_field,
            }
            for ind in indicators
        ]

    async def _get_existing_classification(self, document_id: UUID) -> Optional[ClassificationResult]:
        """Check for existing classification."""
        result = await self.session.execute(
            select(DropShipmentClassification)
            .options(
                selectinload(DropShipmentClassification.positions),
                selectinload(DropShipmentClassification.parties),
                selectinload(DropShipmentClassification.proof_documents),
            )
            .where(DropShipmentClassification.document_id == document_id)
        )
        classification = result.scalar_one_or_none()

        if not classification:
            return None

        return ClassificationResult(
            classification=classification,
            positions=[p for p in classification.positions],
            parties=[p for p in classification.parties],
            proof_documents=[p for p in classification.proof_documents],
            suggested_actions=self._generate_suggested_actions(
                {'zm_relevant': classification.zm_relevant, 'confidence_level': classification.confidence_level},
                [{'is_present': p.is_present, 'proof_type': p.proof_type} for p in classification.proof_documents]
            ),
        )

    async def _extract_parties(self, document: Document) -> list[dict]:
        """Extract party information from document."""
        parties = []
        extracted_data = document.extracted_data or {}

        # Seller
        if extracted_data.get('seller_name'):
            parties.append({
                'party_role': 'seller',
                'sequence_number': 1,
                'company_name': extracted_data.get('seller_name'),
                'vat_id': extracted_data.get('seller_vat_id'),
                'country_code': self._extract_country_from_vat_id(extracted_data.get('seller_vat_id', '')),
                'street': extracted_data.get('seller_street'),
                'city': extracted_data.get('seller_city'),
                'postal_code': extracted_data.get('seller_postal_code'),
                'country': extracted_data.get('seller_country'),
                'source_field': 'seller_address',
            })

        # Buyer / Bill-to
        if extracted_data.get('buyer_name'):
            parties.append({
                'party_role': 'bill_to',
                'sequence_number': 2,
                'company_name': extracted_data.get('buyer_name'),
                'vat_id': extracted_data.get('buyer_vat_id'),
                'country_code': self._extract_country_from_vat_id(extracted_data.get('buyer_vat_id', '')),
                'street': extracted_data.get('buyer_street'),
                'city': extracted_data.get('buyer_city'),
                'postal_code': extracted_data.get('buyer_postal_code'),
                'country': extracted_data.get('buyer_country'),
                'source_field': 'buyer_address',
            })

        # Ship-to (if different from buyer)
        if extracted_data.get('ship_to_name'):
            parties.append({
                'party_role': 'ship_to',
                'sequence_number': 3,
                'company_name': extracted_data.get('ship_to_name'),
                'vat_id': extracted_data.get('ship_to_vat_id'),
                'country_code': self._extract_country_from_vat_id(extracted_data.get('ship_to_vat_id', '')),
                'street': extracted_data.get('ship_to_street'),
                'city': extracted_data.get('ship_to_city'),
                'postal_code': extracted_data.get('ship_to_postal_code'),
                'country': extracted_data.get('ship_to_country'),
                'source_field': 'ship_to_address',
            })

        return parties

    async def _analyze_positions(self, document: Document) -> list[dict]:
        """Analyze line items for position-level classification."""
        positions = []
        extracted_data = document.extracted_data or {}
        line_items = extracted_data.get('line_items', [])

        for idx, item in enumerate(line_items, start=1):
            warehouse_code = item.get('warehouse_code') or item.get('lagerort')
            erp_type = item.get('position_type') or item.get('positionstyp')

            is_drop_shipment = False
            if erp_type and erp_type.upper() == 'TAS':
                is_drop_shipment = True
            elif warehouse_code is None or warehouse_code == '':
                # Empty warehouse code indicates drop shipment
                is_drop_shipment = True

            positions.append({
                'position_number': idx,
                'article_number': item.get('article_number') or item.get('artikelnummer'),
                'article_description': item.get('description') or item.get('bezeichnung'),
                'quantity': item.get('quantity') or item.get('menge'),
                'unit_price': item.get('unit_price') or item.get('einzelpreis'),
                'line_total': item.get('total') or item.get('gesamtpreis'),
                'is_drop_shipment': is_drop_shipment,
                'warehouse_code': warehouse_code,
                'erp_position_type': erp_type,
                'vat_rate': item.get('vat_rate') or item.get('steuersatz'),
            })

        return positions

    async def _identify_proof_documents(self, document_id: UUID, classification: dict) -> list[dict]:
        """Identify required proof documents based on classification."""
        required_proofs = []
        transaction_type = classification.get('transaction_type', 'standard')

        if transaction_type in ('drop_shipment', 'triangular_eu'):
            # Required proofs for drop shipment / triangular
            required_proofs = [
                {'proof_type': 'invoice', 'is_present': True, 'is_complete': True},  # The document itself
                {'proof_type': 'delivery_note', 'is_present': False, 'is_complete': False},
                {'proof_type': 'cmr', 'is_present': False, 'is_complete': False},
                {'proof_type': 'gelangensbestaetigung', 'is_present': False, 'is_complete': False},
            ]

        if transaction_type == 'triangular_eu':
            required_proofs.append({
                'proof_type': 'vat_id_proof',
                'is_present': False,
                'is_complete': False,
            })

        return required_proofs

    async def _save_classification(
        self,
        document_id: UUID,
        classification_data: dict,
        positions: list[dict],
        parties: list[dict],
        proof_documents: list[dict],
        matched_indicators: list[ClassificationIndicatorMatch],
        conflicts: list[dict],
        user_id: Optional[UUID],
    ) -> DropShipmentClassification:
        """Save classification to database."""
        logger.debug(
            "save_classification_started",
            document_id=str(document_id),
            transaction_type=classification_data.get('transaction_type'),
            position_count=len(positions),
            party_count=len(parties),
        )

        # Create main classification
        classification = DropShipmentClassification(
            document_id=document_id,
            transaction_type=classification_data['transaction_type'],
            company_role=classification_data['company_role'],
            vat_category=classification_data['vat_category'],
            confidence_level=classification_data['confidence_level'],
            confidence_score=classification_data['confidence_score'],
            party_count=classification_data['party_count'],
            eu_countries_involved=classification_data['eu_countries_involved'],
            zm_relevant=classification_data['zm_relevant'],
            zm_marker=classification_data.get('zm_marker'),
            indicators=[i.to_dict() for i in matched_indicators],
            conflicts=conflicts if conflicts else None,
        )
        self.session.add(classification)
        await self.session.flush()  # Get the ID

        # Create positions
        for pos_data in positions:
            position = DropShipmentPosition(
                classification_id=classification.id,
                document_id=document_id,
                position_number=pos_data['position_number'],
                article_number=pos_data.get('article_number'),
                article_description=pos_data.get('article_description'),
                quantity=pos_data.get('quantity'),
                unit_price=pos_data.get('unit_price'),
                line_total=pos_data.get('line_total'),
                is_drop_shipment=pos_data['is_drop_shipment'],
                warehouse_code=pos_data.get('warehouse_code'),
                erp_position_type=pos_data.get('erp_position_type'),
                vat_rate=pos_data.get('vat_rate'),
            )
            self.session.add(position)

        # Create parties
        for party_data in parties:
            party = TransactionParty(
                classification_id=classification.id,
                party_role=party_data['party_role'],
                sequence_number=party_data['sequence_number'],
                company_name=party_data.get('company_name'),
                vat_id=party_data.get('vat_id'),
                country_code=party_data.get('country_code'),
                street=party_data.get('street'),
                city=party_data.get('city'),
                postal_code=party_data.get('postal_code'),
                country=party_data.get('country'),
                source_field=party_data.get('source_field'),
            )
            self.session.add(party)

        # Create proof documents
        for proof_data in proof_documents:
            proof = ProofDocument(
                classification_id=classification.id,
                proof_type=proof_data['proof_type'],
                is_present=proof_data['is_present'],
                is_complete=proof_data['is_complete'],
            )
            self.session.add(proof)

        # Create audit log entry
        audit_log = ClassificationAuditLog(
            classification_id=classification.id,
            action='created',
            new_value=classification_data,
            performed_by=user_id,
        )
        self.session.add(audit_log)

        await self.session.commit()
        return classification

    async def get_indicator_config(self) -> list[dict]:
        """Get all indicator configurations."""
        return await self._load_indicator_config()

    async def update_indicator(
        self,
        indicator_id: UUID,
        weight: Optional[int] = None,
        is_active: Optional[bool] = None,
        detection_pattern: Optional[str] = None,
        updated_by: Optional[UUID] = None,
    ) -> ClassificationIndicator:
        """Update indicator configuration."""
        result = await self.session.execute(
            select(ClassificationIndicator).where(ClassificationIndicator.id == indicator_id)
        )
        indicator = result.scalar_one_or_none()

        if not indicator:
            raise ClassificationNotFoundError(str(indicator_id))

        if weight is not None:
            indicator.weight = weight
        if is_active is not None:
            indicator.is_active = is_active
        if detection_pattern is not None:
            indicator.detection_pattern = detection_pattern

        await self.session.commit()
        return indicator


# =============================================================================
# CLASSIFICATION SERVICE
# =============================================================================

class DropShipmentClassificationService:
    """Service for managing classifications."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_classifications(
        self,
        filters: Optional[dict] = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = 'created_at',
        sort_order: str = 'desc',
        include_deleted: bool = False,
        user_id: Optional[UUID] = None,  # Security: Filter by user ownership
    ) -> dict:
        """List classifications with filtering and pagination.

        Args:
            filters: Filter dict or Pydantic model with filter attributes
            user_id: If provided, only return classifications where the
                     associated document is owned by this user.
        """
        # Convert Pydantic model to dict if needed, otherwise use empty dict
        if filters is None:
            filter_dict = {}
        elif hasattr(filters, 'model_dump'):
            filter_dict = filters.model_dump(exclude_none=True)
        elif hasattr(filters, 'dict'):
            filter_dict = filters.dict(exclude_none=True)
        elif isinstance(filters, dict):
            filter_dict = filters
        else:
            filter_dict = {}

        query = select(DropShipmentClassification).options(
            joinedload(DropShipmentClassification.document)
        )

        # Security: Filter by user ownership via document
        if user_id is not None:
            query = query.join(
                Document,
                DropShipmentClassification.document_id == Document.id
            ).where(Document.owner_id == user_id)

        # Soft-delete filter (default: exclude deleted)
        if not include_deleted:
            query = query.where(DropShipmentClassification.is_deleted == False)

        # Apply filters - support both singular and plural field names
        transaction_types = filter_dict.get('transaction_types') or filter_dict.get('transaction_type')
        if transaction_types:
            if isinstance(transaction_types, list) and len(transaction_types) > 0:
                query = query.where(DropShipmentClassification.transaction_type.in_(transaction_types))
            elif isinstance(transaction_types, str):
                query = query.where(DropShipmentClassification.transaction_type == transaction_types)

        confidence_levels = filter_dict.get('confidence_levels') or filter_dict.get('confidence_level')
        if confidence_levels:
            if isinstance(confidence_levels, list) and len(confidence_levels) > 0:
                query = query.where(DropShipmentClassification.confidence_level.in_(confidence_levels))
            elif isinstance(confidence_levels, str):
                query = query.where(DropShipmentClassification.confidence_level == confidence_levels)

        if filter_dict.get('zm_relevant') is not None:
            query = query.where(DropShipmentClassification.zm_relevant == filter_dict['zm_relevant'])
        if filter_dict.get('is_validated') is not None:
            query = query.where(DropShipmentClassification.is_validated == filter_dict['is_validated'])
        if filter_dict.get('date_from'):
            query = query.where(DropShipmentClassification.created_at >= filter_dict['date_from'])
        if filter_dict.get('date_to'):
            query = query.where(DropShipmentClassification.created_at <= filter_dict['date_to'])

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar()

        # Apply sorting
        if sort_order == 'desc':
            query = query.order_by(desc(getattr(DropShipmentClassification, sort_by)))
        else:
            query = query.order_by(getattr(DropShipmentClassification, sort_by))

        # Apply pagination
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        classifications = result.unique().scalars().all()

        return {
            'items': classifications,
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': (total + page_size - 1) // page_size,
        }

    async def get_classification_detail(
        self,
        classification_id: UUID,
        include_audit_log: bool = True,
        include_deleted: bool = False,
    ) -> Optional[DropShipmentClassification]:
        """Get detailed classification with all related data."""
        query = select(DropShipmentClassification).options(
            selectinload(DropShipmentClassification.document),
            selectinload(DropShipmentClassification.positions),
            selectinload(DropShipmentClassification.parties),
            selectinload(DropShipmentClassification.proof_documents),
        )

        if include_audit_log:
            query = query.options(selectinload(DropShipmentClassification.audit_logs))

        query = query.where(DropShipmentClassification.id == classification_id)

        # Soft-delete filter
        if not include_deleted:
            query = query.where(DropShipmentClassification.is_deleted == False)

        result = await self.session.execute(query)
        return result.unique().scalar_one_or_none()

    async def soft_delete_classification(
        self,
        classification_id: UUID,
        deleted_by: Optional[UUID] = None,
        reason: str = "",
    ) -> bool:
        """Soft-delete a classification (GDPR/GoBD compliant)."""
        classification = await self.get_classification_detail(
            classification_id, include_audit_log=False
        )

        if not classification:
            return False

        # Mark as deleted
        classification.is_deleted = True
        classification.deleted_at = datetime.utcnow()
        classification.deleted_by = deleted_by

        # Create audit log entry
        audit_log = ClassificationAuditLog(
            classification_id=classification_id,
            action='soft_deleted',
            performed_by=deleted_by,
            reason=reason or "Klassifikation gelöscht",
            previous_value={
                'is_deleted': False,
            },
            new_value={
                'is_deleted': True,
                'deleted_at': classification.deleted_at.isoformat(),
            },
        )
        self.session.add(audit_log)

        await self.session.commit()
        return True

    async def restore_classification(
        self,
        classification_id: UUID,
        restored_by: Optional[UUID] = None,
        reason: str = "",
    ) -> Optional[DropShipmentClassification]:
        """Restore a soft-deleted classification."""
        classification = await self.get_classification_detail(
            classification_id, include_audit_log=False, include_deleted=True
        )

        if not classification or not classification.is_deleted:
            return None

        # Restore
        classification.is_deleted = False
        classification.deleted_at = None
        classification.deleted_by = None

        # Create audit log entry
        audit_log = ClassificationAuditLog(
            classification_id=classification_id,
            action='restored',
            performed_by=restored_by,
            reason=reason or "Klassifikation wiederhergestellt",
            previous_value={'is_deleted': True},
            new_value={'is_deleted': False},
        )
        self.session.add(audit_log)

        await self.session.commit()
        return classification

    async def validate_classification(
        self,
        classification_id: UUID,
        transaction_type: Optional[str] = None,
        company_role: Optional[str] = None,
        vat_category: Optional[str] = None,
        reason: str = "",
        validated_by: Optional[UUID] = None,
    ) -> DropShipmentClassification:
        """Validate or override a classification with optimistic locking."""
        logger.info(
            "validate_classification_started",
            classification_id=str(classification_id),
            transaction_type=transaction_type,
            company_role=company_role,
            validated_by=str(validated_by) if validated_by else None,
        )

        classification = await self.get_classification_detail(classification_id, include_audit_log=False)

        if not classification:
            logger.warning("validate_classification_not_found", classification_id=str(classification_id))
            raise ClassificationNotFoundError(str(classification_id))

        # Store original updated_at for optimistic locking
        original_updated_at = classification.updated_at

        previous_value = {
            'transaction_type': classification.transaction_type,
            'company_role': classification.company_role,
            'vat_category': classification.vat_category,
            'is_validated': classification.is_validated,
        }

        # Prepare new values
        new_transaction_type = transaction_type or classification.transaction_type
        new_company_role = company_role or classification.company_role
        new_vat_category = vat_category or classification.vat_category
        now = datetime.utcnow()

        # Optimistic locking: Only update if updated_at hasn't changed
        result = await self.session.execute(
            update(DropShipmentClassification)
            .where(
                and_(
                    DropShipmentClassification.id == classification_id,
                    DropShipmentClassification.updated_at == original_updated_at,
                )
            )
            .values(
                transaction_type=new_transaction_type,
                company_role=new_company_role,
                vat_category=new_vat_category,
                is_validated=True,
                validated_by=validated_by,
                validated_at=now,
                updated_at=now,
            )
        )

        if result.rowcount == 0:
            logger.warning(
                "validate_classification_conflict",
                classification_id=str(classification_id),
                original_updated_at=str(original_updated_at),
            )
            raise ValidationConflictError(str(classification_id))

        new_value = {
            'transaction_type': new_transaction_type,
            'company_role': new_company_role,
            'vat_category': new_vat_category,
            'is_validated': True,
        }

        # Create audit log
        audit_log = ClassificationAuditLog(
            classification_id=classification_id,
            action='manually_validated',
            previous_value=previous_value,
            new_value=new_value,
            reason=reason,
            performed_by=validated_by,
        )
        self.session.add(audit_log)

        await self.session.commit()

        logger.info(
            "validate_classification_completed",
            classification_id=str(classification_id),
            new_transaction_type=new_transaction_type,
            new_company_role=new_company_role,
            validated_by=str(validated_by) if validated_by else None,
        )

        # Refresh classification to return updated data
        await self.session.refresh(classification)
        return classification

    async def get_positions(self, classification_id: UUID) -> list[DropShipmentPosition]:
        """Get all positions for a classification."""
        result = await self.session.execute(
            select(DropShipmentPosition)
            .where(DropShipmentPosition.classification_id == classification_id)
            .order_by(DropShipmentPosition.position_number)
        )
        return result.scalars().all()

    async def update_position(
        self,
        position_id: UUID,
        is_drop_shipment: Optional[bool] = None,
        vat_category: Optional[str] = None,
        updated_by: Optional[UUID] = None,
    ) -> DropShipmentPosition:
        """Update a position classification."""
        result = await self.session.execute(
            select(DropShipmentPosition).where(DropShipmentPosition.id == position_id)
        )
        position = result.scalar_one_or_none()

        if not position:
            raise ClassificationNotFoundError(str(position_id))

        if is_drop_shipment is not None:
            position.is_drop_shipment = is_drop_shipment
        if vat_category is not None:
            position.vat_category = vat_category

        await self.session.commit()
        return position

    async def get_proof_documents(self, classification_id: UUID) -> list[ProofDocument]:
        """Get all proof documents for a classification."""
        result = await self.session.execute(
            select(ProofDocument)
            .where(ProofDocument.classification_id == classification_id)
        )
        return result.scalars().all()

    async def link_proof_document(
        self,
        classification_id: UUID,
        document_id: UUID,
        proof_type: str,
        linked_by: Optional[UUID] = None,
    ) -> ProofDocument:
        """Link a proof document to a classification."""
        # Check if proof entry exists
        result = await self.session.execute(
            select(ProofDocument)
            .where(
                and_(
                    ProofDocument.classification_id == classification_id,
                    ProofDocument.proof_type == proof_type,
                )
            )
        )
        proof = result.scalar_one_or_none()

        if proof:
            proof.document_id = document_id
            proof.is_present = True
        else:
            proof = ProofDocument(
                classification_id=classification_id,
                document_id=document_id,
                proof_type=proof_type,
                is_present=True,
            )
            self.session.add(proof)

        # Create audit log
        audit_log = ClassificationAuditLog(
            classification_id=classification_id,
            action='proof_linked',
            new_value={'proof_type': proof_type, 'document_id': str(document_id)},
            performed_by=linked_by,
        )
        self.session.add(audit_log)

        await self.session.commit()
        return proof

    async def get_zm_summary(
        self,
        period: str,
        user_id: Optional[UUID] = None,  # Security: Filter by user ownership
    ) -> ZmSummary:
        """Get ZM summary for a period (YYYY-MM format).

        Args:
            user_id: If provided, only return ZM data for classifications where
                     the associated document is owned by this user.
        """
        year, month = map(int, period.split('-'))
        start_date = date(year, month, 1)

        if month == 12:
            end_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(year, month + 1, 1) - timedelta(days=1)

        # Deadline is 25th of following month
        if month == 12:
            deadline = date(year + 1, 1, 25)
        else:
            deadline = date(year, month + 1, 25)

        # Build base query
        query = (
            select(DropShipmentClassification)
            .options(
                selectinload(DropShipmentClassification.parties),
                joinedload(DropShipmentClassification.document),
            )
        )

        # Security: Filter by user ownership via document
        if user_id is not None:
            query = query.join(
                Document,
                DropShipmentClassification.document_id == Document.id
            ).where(Document.owner_id == user_id)

        # Query ZM-relevant classifications with document data (exclude soft-deleted)
        result = await self.session.execute(
            query.where(
                and_(
                    DropShipmentClassification.zm_relevant == True,
                    DropShipmentClassification.is_deleted == False,
                    DropShipmentClassification.created_at >= start_date,
                    DropShipmentClassification.created_at <= end_date,
                )
            )
        )
        classifications = result.unique().scalars().all()

        # Aggregiere nach VAT-ID (ZM erfordert Gruppierung pro Käufer-USt-IdNr.)
        # Key: (vat_id, is_triangular) -> aggregierte Werte
        vat_aggregation: dict[tuple[str, bool], dict] = {}

        for cl in classifications:
            # Find buyer VAT ID
            buyer = next((p for p in cl.parties if p.party_role == 'bill_to'), None)
            if buyer and buyer.vat_id:
                is_triangular = cl.transaction_type == 'triangular_eu'
                vat_id = buyer.vat_id.upper().replace(' ', '')  # Normalize VAT ID
                country_code = buyer.country_code or vat_id[:2]

                # Extract amount from document's extracted_data
                amount = Decimal('0')
                if cl.document and cl.document.extracted_data:
                    extracted = cl.document.extracted_data
                    # Try multiple common field names for invoice amount
                    for field in ['total_amount', 'invoice_total', 'gross_amount',
                                  'net_amount', 'betrag', 'gesamtbetrag', 'rechnungsbetrag']:
                        raw_amount = extracted.get(field)
                        if raw_amount:
                            try:
                                # Handle string amounts with comma/dot
                                if isinstance(raw_amount, str):
                                    raw_amount = raw_amount.replace('.', '').replace(',', '.')
                                amount = Decimal(str(raw_amount))
                                break
                            except (ValueError, TypeError):
                                continue

                # Aggregiere pro VAT-ID und Triangular-Status
                # (Dreiecksgeschäfte müssen getrennt gemeldet werden mit Kz. 1)
                key = (vat_id, is_triangular)
                if key not in vat_aggregation:
                    vat_aggregation[key] = {
                        'vat_id': vat_id,
                        'country_code': country_code,
                        'amount': Decimal('0'),
                        'is_triangular': is_triangular,
                        'classification_ids': [],
                    }
                vat_aggregation[key]['amount'] += amount
                vat_aggregation[key]['classification_ids'].append(cl.id)

        # Konvertiere aggregierte Daten zu ZmRecords
        records = []
        total_amount = Decimal('0')
        triangular_count = 0

        for (vat_id, is_triangular), data in vat_aggregation.items():
            records.append(ZmRecord(
                vat_id=data['vat_id'],
                country_code=data['country_code'],
                amount=data['amount'],
                is_triangular=data['is_triangular'],
                classification_id=data['classification_ids'][0],  # Erste ID als Referenz
            ))
            total_amount += data['amount']
            if is_triangular:
                triangular_count += 1

        # Sortiere nach Land, dann VAT-ID
        records.sort(key=lambda r: (r.country_code, r.vat_id))

        # Aggregiere nach Land für Frontend CountryBreakdown Component
        country_aggregation: dict[str, dict] = {}
        for record in records:
            if record.country_code not in country_aggregation:
                country_aggregation[record.country_code] = {
                    'amount': Decimal('0'),
                    'record_count': 0,
                }
            country_aggregation[record.country_code]['amount'] += record.amount
            country_aggregation[record.country_code]['record_count'] += 1

        by_country = [
            ZmCountryAggregation(
                country_code=cc,
                amount=data['amount'],
                record_count=data['record_count'],
            )
            for cc, data in sorted(country_aggregation.items())
        ]

        return ZmSummary(
            period=period,
            total_amount=total_amount,
            triangular_count=triangular_count,
            record_count=len(records),
            deadline=deadline,
            records=records,
            by_country=by_country,
        )

    async def get_zm_records(
        self,
        period: str,
        include_triangular_only: bool = False,
    ) -> list[ZmRecord]:
        """Get ZM records for export."""
        summary = await self.get_zm_summary(period)

        if include_triangular_only:
            return [r for r in summary.records if r.is_triangular]

        return summary.records

    async def get_statistics(
        self,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        user_id: Optional[UUID] = None,  # Security: Filter by user ownership
    ) -> dict:
        """Get classification statistics.

        Args:
            user_id: If provided, only return statistics for classifications
                     where the associated document is owned by this user.
        """
        # Build base query with optional user filter
        base_conditions = [DropShipmentClassification.is_deleted == False]

        if date_from:
            base_conditions.append(DropShipmentClassification.created_at >= date_from)
        if date_to:
            base_conditions.append(DropShipmentClassification.created_at <= date_to)

        # Security: Filter by user ownership via document
        if user_id is not None:
            query = (
                select(
                    DropShipmentClassification.transaction_type,
                    DropShipmentClassification.confidence_level,
                    func.count(DropShipmentClassification.id).label('count'),
                )
                .join(Document, DropShipmentClassification.document_id == Document.id)
                .where(Document.owner_id == user_id)
                .where(and_(*base_conditions))
                .group_by(
                    DropShipmentClassification.transaction_type,
                    DropShipmentClassification.confidence_level,
                )
            )
        else:
            query = (
                select(
                    DropShipmentClassification.transaction_type,
                    DropShipmentClassification.confidence_level,
                    func.count(DropShipmentClassification.id).label('count'),
                )
                .where(and_(*base_conditions))
                .group_by(
                    DropShipmentClassification.transaction_type,
                    DropShipmentClassification.confidence_level,
                )
            )

        result = await self.session.execute(query)
        rows = result.all()

        # Initialize with default values for all known types
        by_type = {
            'drop_shipment': 0,
            'triangular_eu': 0,
            'chain_transaction': 0,
            'consignment': 0,
            'standard_purchase': 0,
            'standard_sale': 0,
        }
        by_confidence = {
            'high': 0,
            'medium': 0,
            'low': 0,
            'manual_required': 0,
        }
        total = 0

        for row in rows:
            t_type, conf, count = row
            if t_type in by_type:
                by_type[t_type] += count
            else:
                by_type[t_type] = count
            if conf in by_confidence:
                by_confidence[conf] += count
            else:
                by_confidence[conf] = count
            total += count

        # Get ZM stats (with user filter)
        zm_query = select(func.count(DropShipmentClassification.id)).where(
            DropShipmentClassification.zm_relevant == True
        )
        if user_id is not None:
            zm_query = zm_query.join(
                Document, DropShipmentClassification.document_id == Document.id
            ).where(Document.owner_id == user_id)
        zm_result = await self.session.execute(zm_query)
        zm_count = zm_result.scalar()

        # Get manual review count (with user filter)
        # Cast to text because PostgreSQL column is native ENUM type
        from sqlalchemy import cast, String as SAString
        manual_query = select(func.count(DropShipmentClassification.id)).where(
            cast(DropShipmentClassification.confidence_level, SAString) == ConfidenceLevel.MANUAL_REQUIRED.value
        )
        if user_id is not None:
            manual_query = manual_query.join(
                Document, DropShipmentClassification.document_id == Document.id
            ).where(Document.owner_id == user_id)
        manual_result = await self.session.execute(manual_query)
        manual_count = manual_result.scalar()

        # Calculate time-based statistics for dashboard
        from datetime import datetime, timedelta

        today = datetime.now().date()
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)

        # Base conditions for time-based queries
        time_base_conditions = [DropShipmentClassification.is_deleted == False]

        # Classified today
        today_query = select(func.count(DropShipmentClassification.id)).where(
            and_(
                *time_base_conditions,
                func.date(DropShipmentClassification.created_at) == today
            )
        )
        if user_id is not None:
            today_query = today_query.join(
                Document, DropShipmentClassification.document_id == Document.id
            ).where(Document.owner_id == user_id)
        today_result = await self.session.execute(today_query)
        classified_today = today_result.scalar() or 0

        # Classified this week
        week_query = select(func.count(DropShipmentClassification.id)).where(
            and_(
                *time_base_conditions,
                func.date(DropShipmentClassification.created_at) >= week_start
            )
        )
        if user_id is not None:
            week_query = week_query.join(
                Document, DropShipmentClassification.document_id == Document.id
            ).where(Document.owner_id == user_id)
        week_result = await self.session.execute(week_query)
        classified_this_week = week_result.scalar() or 0

        # Classified this month
        month_query = select(func.count(DropShipmentClassification.id)).where(
            and_(
                *time_base_conditions,
                func.date(DropShipmentClassification.created_at) >= month_start
            )
        )
        if user_id is not None:
            month_query = month_query.join(
                Document, DropShipmentClassification.document_id == Document.id
            ).where(Document.owner_id == user_id)
        month_result = await self.session.execute(month_query)
        classified_this_month = month_result.scalar() or 0

        return {
            'total': total,
            'by_transaction_type': by_type,
            'by_confidence_level': by_confidence,
            'zm_relevant_count': zm_count,
            'manual_review_count': manual_count,
            'classified_today': classified_today,
            'classified_this_week': classified_this_week,
            'classified_this_month': classified_this_month,
        }

    async def get_accuracy_metrics(
        self,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> dict:
        """Get classification accuracy metrics."""
        query = select(
            func.count(DropShipmentClassification.id).label('total'),
            func.count(DropShipmentClassification.id).filter(
                DropShipmentClassification.is_validated == True
            ).label('validated'),
        )

        if date_from:
            query = query.where(DropShipmentClassification.created_at >= date_from)
        if date_to:
            query = query.where(DropShipmentClassification.created_at <= date_to)

        result = await self.session.execute(query)
        row = result.one()

        total = row.total or 0
        validated = row.validated or 0

        return {
            'total_classifications': total,
            'validated_count': validated,
            'validation_rate': (validated / total * 100) if total > 0 else 0,
        }

    async def unlink_proof_document(
        self,
        classification_id: UUID,
        proof_id: UUID,
        user_id: Optional[UUID] = None,
    ) -> None:
        """Unlink a proof document from a classification."""
        # Find and delete the proof document link
        result = await self.session.execute(
            select(ProofDocument).where(
                and_(
                    ProofDocument.classification_id == classification_id,
                    ProofDocument.id == proof_id,
                )
            )
        )
        proof = result.scalar_one_or_none()

        if not proof:
            raise ProofDocumentError(
                message="Proof document not found",
                proof_id=str(proof_id),
                classification_id=str(classification_id),
            )

        await self.session.delete(proof)

        # Create audit log entry
        audit_log = ClassificationAuditLog(
            classification_id=classification_id,
            action='proof_unlinked',
            previous_value={'proof_id': str(proof_id), 'proof_type': proof.proof_type},
            new_value=None,
            performed_by=user_id,
            reason='Belegnachweis entfernt',
        )
        self.session.add(audit_log)

        await self.session.commit()

    async def delete_classification(
        self,
        classification_id: UUID,
        user_id: Optional[UUID] = None,
        reason: str = "",
    ) -> None:
        """Soft-delete a classification (GDPR/GoBD compliant)."""
        logger.info(
            "delete_classification_started",
            classification_id=str(classification_id),
            user_id=str(user_id) if user_id else None,
        )

        result = await self.session.execute(
            select(DropShipmentClassification).where(
                and_(
                    DropShipmentClassification.id == classification_id,
                    DropShipmentClassification.is_deleted == False,
                )
            )
        )
        classification = result.scalar_one_or_none()

        if not classification:
            logger.warning("delete_classification_not_found", classification_id=str(classification_id))
            raise ClassificationNotFoundError(str(classification_id))

        # Soft-delete: Set is_deleted flag and timestamp
        classification.is_deleted = True
        classification.deleted_at = datetime.utcnow()
        classification.deleted_by = user_id

        # Create audit log entry
        audit_log = ClassificationAuditLog(
            classification_id=classification_id,
            action='soft_deleted',
            previous_value={
                'transaction_type': classification.transaction_type,
                'confidence_score': classification.confidence_score,
                'is_deleted': False,
            },
            new_value={
                'is_deleted': True,
                'deleted_at': classification.deleted_at.isoformat(),
            },
            performed_by=user_id,
            reason=reason or 'Klassifikation gelöscht',
        )
        self.session.add(audit_log)

        await self.session.commit()

        logger.info(
            "delete_classification_completed",
            classification_id=str(classification_id),
            user_id=str(user_id) if user_id else None,
        )


# =============================================================================
# DATEV EXPORT SERVICE
# =============================================================================

class DatevExportService:
    """Service for DATEV export."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_export(
        self,
        classification_ids: list[UUID],
        kontenrahmen: str = 'SKR03',
        include_zm_data: bool = True,
        export_format: str = 'extf',
        created_by: Optional[UUID] = None,
    ) -> DatevExportResult:
        """Create DATEV export file."""
        logger.info(
            "datev_export_started",
            classification_count=len(classification_ids),
            kontenrahmen=kontenrahmen,
            export_format=export_format,
            include_zm_data=include_zm_data,
            created_by=str(created_by) if created_by else None,
        )

        warnings: list[str] = []

        # Get classifications
        result = await self.session.execute(
            select(DropShipmentClassification)
            .options(
                selectinload(DropShipmentClassification.parties),
                selectinload(DropShipmentClassification.positions),
            )
            .where(DropShipmentClassification.id.in_(classification_ids))
        )
        classifications = result.unique().scalars().all()

        if not classifications:
            logger.warning(
                "datev_export_no_classifications",
                classification_ids=[str(cid) for cid in classification_ids],
            )
            raise DatevExportError(
                message="No classifications found for export",
                details={"classification_ids": [str(cid) for cid in classification_ids]},
            )

        # Check for missing data and collect warnings
        for cl in classifications:
            if not cl.is_validated:
                warnings.append(f"Klassifikation {cl.id} ist nicht validiert")
            if not cl.parties:
                warnings.append(f"Klassifikation {cl.id} hat keine Parteien")

        # Get account mappings
        account_mappings = await self.get_account_mappings(kontenrahmen)

        # Generate export
        if export_format == 'extf':
            content = self._generate_extf(classifications, account_mappings, include_zm_data)
        else:
            content = self._generate_csv(classifications, account_mappings)

        # Count ZM-relevant records (triangular or intra-EU)
        zm_record_count = sum(
            1 for cl in classifications
            if cl.transaction_type in ('triangular_eu', 'drop_shipment') and cl.zm_relevant
        )

        # Log export
        for cl in classifications:
            audit_log = ClassificationAuditLog(
                classification_id=cl.id,
                action='exported_datev',
                new_value={'format': export_format, 'kontenrahmen': kontenrahmen},
                performed_by=created_by,
            )
            self.session.add(audit_log)

        await self.session.commit()

        # Generate unique export ID
        export_id = str(uuid4())
        filename = f"datev_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        logger.info(
            "datev_export_completed",
            export_id=export_id,
            filename=filename,
            record_count=len(classifications),
            zm_record_count=zm_record_count,
            warning_count=len(warnings),
            created_by=str(created_by) if created_by else None,
        )

        return DatevExportResult(
            export_id=export_id,
            filename=filename,
            download_url=None,  # Will be set by storage service if file is persisted
            record_count=len(classifications),
            zm_record_count=zm_record_count,
            warnings=warnings,
            content=content,
        )

    def _generate_extf(
        self,
        classifications: list[DropShipmentClassification],
        account_mappings: dict,
        include_zm_data: bool,
    ) -> str:
        """Generate DATEV EXTF format (Buchungsstapel).

        Das EXTF-Format ist das offizielle DATEV-Austauschformat für
        Buchungsstapel. Es besteht aus:
        1. Kopfzeile (Metadaten)
        2. Spaltenüberschriften
        3. Buchungssätze
        """
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_MINIMAL)

        # DATEV EXTF Kopfzeile (Zeile 1 - Metadaten)
        # Format: "EXTF";Versionsnummer;Formatversion;...
        # WICHTIG: EXTF wird ohne extra Anführungszeichen geschrieben,
        # da csv.writer mit QUOTE_MINIMAL das Quoting automatisch macht
        now = datetime.now()
        writer.writerow([
            'EXTF',                            # Kennzeichen EXTF (csv.writer quotet automatisch)
            700,                               # Versionsnummer
            21,                                # Formatversion (Buchungsstapel)
            'Buchungsstapel',                  # Formatkategorie
            '',                                # Formatname
            '',                                # Formatversion (leer)
            now.strftime('%Y%m%d%H%M%S') + '000',  # Erstellungsdatum + Millisekunden
            '',                                # Importiert (leer)
            'ST',                              # Herkunftskennzeichen (Steuerberater)
            '',                                # Exportiert von (leer)
            '',                                # Importiert durch (leer)
            '',                                # Berater-Nr.
            '',                                # Mandanten-Nr.
            now.year,                          # WJ-Beginn
            4,                                 # Sachkontenlänge
            now.strftime('%Y%m%d'),            # Datum von
            now.strftime('%Y%m%d'),            # Datum bis
            '',                                # Bezeichnung
            '',                                # Diktatzeichen
            1,                                 # Buchungstyp (1 = Soll)
            0,                                 # Rechnungslegungszweck
            '',                                # Festschreibung
            'EUR',                             # WKZ
            '',                                # Derivatskennzeichen
            '',                                # Kost1
            '',                                # Kost2
        ])

        # DATEV EXTF Spaltenüberschriften (Zeile 2)
        writer.writerow([
            'Umsatz (ohne Soll/Haben-Kz)',     # 1: Betrag
            'Soll/Haben-Kennzeichen',          # 2: S oder H
            'WKZ Umsatz',                      # 3: Währungskennzeichen
            'Kurs',                            # 4: Wechselkurs
            'Basis-Umsatz',                    # 5: Basiswährungsbetrag
            'WKZ Basis-Umsatz',                # 6: Basiswährung
            'Konto',                           # 7: Sachkonto
            'Gegenkonto (ohne BU-Schlüssel)',  # 8: Gegenkonto
            'BU-Schlüssel',                    # 9: Buchungsschlüssel
            'Belegdatum',                      # 10: TTMM
            'Belegfeld 1',                     # 11: Rechnungsnummer
            'Belegfeld 2',                     # 12: Zusatzinfo
            'Skonto',                          # 13: Skontobetrag
            'Buchungstext',                    # 14: Buchungstext
            'Postensperre',                    # 15: 0 oder 1
            'Diverse Adressnummer',            # 16: Adressnummer
            'Geschäftspartnerbank',            # 17: Bankverbindung
            'Sachverhalt',                     # 18: L+L-Sachverhalt
            'Zinssperre',                      # 19: 0 oder 1
            'Beleglink',                       # 20: Link zum Beleg
            'Beleginfo - Art 1',               # 21: Beleginfo-Typ
            'Beleginfo - Inhalt 1',            # 22: Beleginfo-Wert
            'EU-Land',                         # 23: Ländercode
            'EU-UStID',                        # 24: USt-IdNr.
            'EU-Steuersatz',                   # 25: Steuersatz
            'Abw. Versteuerungsart',           # 26: Versteuerungsart
            'Sachverhalt L+L',                 # 27: Sachverhalt
            'Funktionsergänzung L+L',          # 28: Funktionsergänzung
            'BU 49 Hauptfunktionstyp',         # 29: Hauptfunktionstyp
            'BU 49 Hauptfunktionsnummer',      # 30: Hauptfunktionsnummer
            'BU 49 Funktionsergänzung',        # 31: Funktionsergänzung
            'Zusatzinformation - Art 1',       # 32: Zusatzinfo-Typ
            'Zusatzinformation - Inhalt 1',    # 33: Zusatzinfo-Wert
            'Stück',                           # 34: Mengenangabe
            'Gewicht',                         # 35: Gewicht
            'Zahlweise',                       # 36: Zahlweise
            'Forderungsart',                   # 37: Forderungsart
            'Veranlagungsjahr',                # 38: Jahr
            'Zugeordnete Fälligkeit',          # 39: Fälligkeitsdatum
            'Skontotyp',                       # 40: Skontotyp
            'Auftragsnummer',                  # 41: Auftragsnummer
        ])

        for cl in classifications:
            mapping = account_mappings.get(
                (cl.company_role, cl.transaction_type),
                {}
            )

            # Find VAT ID for ZM
            buyer = next((p for p in cl.parties if p.party_role == 'bill_to'), None)
            vat_id = buyer.vat_id if buyer else ''
            country = buyer.country_code if buyer else ''

            # Calculate amount from positions with safe parsing
            amount = Decimal('0')
            for p in cl.positions:
                if p.is_drop_shipment:
                    try:
                        amount += Decimal(str(p.line_total or 0))
                    except (ValueError, TypeError, InvalidOperation):
                        # Skip invalid amounts, log for debugging
                        pass

            # DATEV erwartet Beträge mit Komma als Dezimaltrennzeichen
            amount_str = f"{amount:.2f}".replace('.', ',')

            # Buchungssatz im EXTF-Format (41 Spalten)
            writer.writerow([
                amount_str,                            # 1: Umsatz
                'S',                                   # 2: Soll/Haben-Kz
                'EUR',                                 # 3: WKZ Umsatz
                '',                                    # 4: Kurs
                '',                                    # 5: Basis-Umsatz
                '',                                    # 6: WKZ Basis-Umsatz
                mapping.get('revenue_account', '8400'),  # 7: Konto
                mapping.get('expense_account', ''),      # 8: Gegenkonto
                mapping.get('tax_code', ''),             # 9: BU-Schlüssel
                cl.created_at.strftime('%d%m'),          # 10: Belegdatum (TTMM)
                '',                                      # 11: Belegfeld 1
                '',                                      # 12: Belegfeld 2
                '',                                      # 13: Skonto
                'Streckengeschäft',                      # 14: Buchungstext
                0,                                       # 15: Postensperre
                '',                                      # 16: Diverse Adressnummer
                '',                                      # 17: Geschäftspartnerbank
                '',                                      # 18: Sachverhalt
                0,                                       # 19: Zinssperre
                '',                                      # 20: Beleglink
                '',                                      # 21: Beleginfo - Art 1
                '',                                      # 22: Beleginfo - Inhalt 1
                country if include_zm_data else '',      # 23: EU-Land
                vat_id if include_zm_data else '',       # 24: EU-UStID
                '',                                      # 25: EU-Steuersatz
                '',                                      # 26: Abw. Versteuerungsart
                '',                                      # 27: Sachverhalt L+L
                '',                                      # 28: Funktionsergänzung L+L
                '',                                      # 29: BU 49 Hauptfunktionstyp
                '',                                      # 30: BU 49 Hauptfunktionsnummer
                '',                                      # 31: BU 49 Funktionsergänzung
                '',                                      # 32: Zusatzinformation - Art 1
                '',                                      # 33: Zusatzinformation - Inhalt 1
                '',                                      # 34: Stück
                '',                                      # 35: Gewicht
                '',                                      # 36: Zahlweise
                '',                                      # 37: Forderungsart
                '',                                      # 38: Veranlagungsjahr
                '',                                      # 39: Zugeordnete Fälligkeit
                '',                                      # 40: Skontotyp
                '',                                      # 41: Auftragsnummer
            ])

        return output.getvalue()

    def _generate_csv(
        self,
        classifications: list[DropShipmentClassification],
        account_mappings: dict,
    ) -> str:
        """Generate simple CSV export."""
        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow([
            'Klassifikations-ID', 'Transaktionstyp', 'Unternehmerrolle',
            'Konfidenz', 'ZM-relevant', 'Erlöskonto', 'Aufwandskonto',
            'Steuerschlüssel', 'USt-IdNr.'
        ])

        for cl in classifications:
            mapping = account_mappings.get(
                (cl.company_role, cl.transaction_type),
                {}
            )

            buyer = next((p for p in cl.parties if p.party_role == 'bill_to'), None)

            writer.writerow([
                str(cl.id),
                cl.transaction_type,
                cl.company_role,
                f"{cl.confidence_score}%",
                'Ja' if cl.zm_relevant else 'Nein',
                mapping.get('revenue_account', ''),
                mapping.get('expense_account', ''),
                mapping.get('tax_code', ''),
                buyer.vat_id if buyer else '',
            ])

        return output.getvalue()

    async def get_account_mappings(self, kontenrahmen: str = 'SKR03') -> dict:
        """Get DATEV account mappings."""
        result = await self.session.execute(
            select(DatevStreckengeschaeftAccount)
            .where(
                and_(
                    DatevStreckengeschaeftAccount.kontenrahmen == kontenrahmen,
                    DatevStreckengeschaeftAccount.is_active == True,
                )
            )
        )
        accounts = result.scalars().all()

        mappings = {}
        for acc in accounts:
            key = (acc.company_role, acc.transaction_type)
            mappings[key] = {
                'revenue_account': acc.revenue_account,
                'expense_account': acc.expense_account,
                'tax_code': acc.tax_code,
                'ustva_kennzahl': acc.ustva_kennzahl,
                'zm_kennzeichen': acc.zm_kennzeichen,
            }

        return mappings

    async def get_export(self, export_id: UUID) -> Optional[dict]:
        """Get a previous export by ID (would need export history table)."""
        # This would require an export history table
        return None

    async def log_export(
        self,
        export_id: UUID,
        classification_ids: list[UUID],
        user_id: Optional[UUID] = None,
    ) -> None:
        """Log an export operation."""
        for cl_id in classification_ids:
            audit_log = ClassificationAuditLog(
                classification_id=cl_id,
                action='exported_datev',
                new_value={'export_id': str(export_id)},
                performed_by=user_id,
            )
            self.session.add(audit_log)

        await self.session.commit()


# =============================================================================
# VAT ID VALIDATION SERVICE
# =============================================================================

class VatIdValidationService:
    """Service for VAT ID validation via EU VIES."""

    VIES_WSDL = "https://ec.europa.eu/taxation_customs/vies/checkVatService.wsdl"

    def __init__(self, session: AsyncSession):
        self.session = session

    async def validate_vat_id(
        self,
        vat_id: str,
        requester_vat_id: Optional[str] = None,
    ) -> dict:
        """Validate a VAT ID via EU VIES service."""
        # Check cache first
        result = await self.session.execute(
            select(VatIdRegistry).where(VatIdRegistry.vat_id == vat_id)
        )
        cached = result.scalar_one_or_none()

        if cached and cached.last_validated:
            # Use cache if validated within last 24 hours
            if datetime.utcnow() - cached.last_validated.replace(tzinfo=None) < timedelta(hours=24):
                return {
                    'vat_id': cached.vat_id,
                    'is_valid': cached.is_valid,
                    'company_name': cached.company_name,
                    'country_code': cached.country_code,
                    'from_cache': True,
                }

        # Extract country code and number
        country_code = vat_id[:2].upper()
        vat_number = vat_id[2:]

        # In production, this would call the actual VIES SOAP service
        # For now, we simulate a successful validation
        is_valid = len(vat_number) >= 8
        company_name = None

        # Save to registry
        if cached:
            cached.is_valid = is_valid
            cached.last_validated = datetime.utcnow()
            cached.validation_response = {'simulated': True}
        else:
            new_entry = VatIdRegistry(
                vat_id=vat_id,
                country_code=country_code,
                is_valid=is_valid,
                last_validated=datetime.utcnow(),
                validation_response={'simulated': True},
            )
            self.session.add(new_entry)

        await self.session.commit()

        return {
            'vat_id': vat_id,
            'is_valid': is_valid,
            'company_name': company_name,
            'country_code': country_code,
            'from_cache': False,
        }

    async def list_vat_ids(
        self,
        country_code: Optional[str] = None,
        is_valid: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """List VAT IDs from registry."""
        query = select(VatIdRegistry)

        if country_code:
            query = query.where(VatIdRegistry.country_code == country_code)
        if is_valid is not None:
            query = query.where(VatIdRegistry.is_valid == is_valid)

        # Count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar()

        # Paginate
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        vat_ids = result.scalars().all()

        return {
            'items': vat_ids,
            'total': total,
            'page': page,
            'page_size': page_size,
        }
