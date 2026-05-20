# -*- coding: utf-8 -*-
"""
Clause Recognition Service for Contract Management V2.

Erkennt und extrahiert Vertragsklauseln aus OCR-Text:
- Preisanpassungsklauseln (Indexierung, Prozentual)
- Mindestlaufzeiten
- Automatische Verlängerungsklauseln
- Vertragsstrafen (Penalty)
- Kündigungsbedingungen
- Haftungsbegrenzungen
- Gewährleistungsklauseln

SECURITY:
- NIEMALS Vertragstext in Logs speichern (Geschäftsgeheimnisse)
- Multi-Tenant via company_id Filter

Feinpoliert und durchdacht - Enterprise Contract Management V2.
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Pattern, Tuple
from uuid import UUID

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_contract import Contract, ContractClause, ClauseType

logger = structlog.get_logger(__name__)


# =============================================================================
# Constants and Patterns
# =============================================================================


@dataclass
class ClausePattern:
    """Pattern definition for clause extraction."""
    clause_type: str
    patterns: List[Pattern]
    extractor: Optional[str] = None  # Name of extraction function
    risk_keywords: List[str] = field(default_factory=list)
    confidence_base: float = 0.7


# German clause patterns
CLAUSE_PATTERNS: Dict[str, ClausePattern] = {
    # Preisanpassungsklauseln
    ClauseType.PRICE_ADJUSTMENT.value: ClausePattern(
        clause_type=ClauseType.PRICE_ADJUSTMENT.value,
        patterns=[
            re.compile(
                r"(?:preis(?:anpassung|erhöhung|änderung)|indexierung)[^.]*"
                r"(?:verbraucherpreisindex|vpi|index|prozent|%)[^.]*\.?",
                re.IGNORECASE | re.DOTALL
            ),
            re.compile(
                r"(?:die\s+preise|der\s+preis)[^.]*(?:angepasst|erhöh|geänder)[^.]*"
                r"(?:jährlich|jährlich|index|prozent)[^.]*\.?",
                re.IGNORECASE | re.DOTALL
            ),
            re.compile(
                r"preisgleitklausel[^.]*\.?",
                re.IGNORECASE | re.DOTALL
            ),
        ],
        extractor="extract_price_adjustment",
        risk_keywords=["unbegrenzt", "einseitig", "ohne zustimmung"],
        confidence_base=0.75,
    ),

    # Mindestlaufzeit
    ClauseType.MINIMUM_TERM.value: ClausePattern(
        clause_type=ClauseType.MINIMUM_TERM.value,
        patterns=[
            re.compile(
                r"(?:mindestlaufzeit|mindestvertragslaufzeit|erstlaufzeit)"
                r"[^.]*(?:\d+)[^.]*(?:monat|jahr)[^.]*\.?",
                re.IGNORECASE | re.DOTALL
            ),
            re.compile(
                r"(?:der\s+vertrag|dieser\s+vertrag)[^.]*"
                r"(?:mindestens|wenigstens)[^.]*"
                r"(?:\d+)[^.]*(?:monat|jahr)[^.]*\.?",
                re.IGNORECASE | re.DOTALL
            ),
            re.compile(
                r"(?:feste\s+laufzeit|unkuendbar)[^.]*(?:\d+)[^.]*(?:monat|jahr)[^.]*\.?",
                re.IGNORECASE | re.DOTALL
            ),
        ],
        extractor="extract_minimum_term",
        risk_keywords=["unkuendbar", "bindend", "keine kündigung"],
        confidence_base=0.8,
    ),

    # Automatische Verlängerung
    ClauseType.AUTO_RENEWAL.value: ClausePattern(
        clause_type=ClauseType.AUTO_RENEWAL.value,
        patterns=[
            re.compile(
                r"(?:verlängert\s+sich|verlängerung)[^.]*"
                r"(?:automatisch|stillschweigend)[^.]*\.?",
                re.IGNORECASE | re.DOTALL
            ),
            re.compile(
                r"(?:sofern|wenn)[^.]*(?:nicht|keine)[^.]*(?:kuendi)[^.]*"
                r"verlänger[^.]*\.?",
                re.IGNORECASE | re.DOTALL
            ),
            re.compile(
                r"(?:tacit|automatic)\s*renewal[^.]*\.?",
                re.IGNORECASE | re.DOTALL
            ),
        ],
        extractor="extract_auto_renewal",
        risk_keywords=["unbegrenzt", "ohne limit", "endlos"],
        confidence_base=0.85,
    ),

    # Vertragsstrafe / Penalty
    ClauseType.PENALTY.value: ClausePattern(
        clause_type=ClauseType.PENALTY.value,
        patterns=[
            re.compile(
                r"(?:vertragsstrafe|poenale|konventionalstrafe)[^.]*\.?",
                re.IGNORECASE | re.DOTALL
            ),
            re.compile(
                r"(?:verzug|verspätung)[^.]*"
                r"(?:\d+)[^.]*(?:prozent|%|euro|eur)[^.]*(?:pro\s+tag|täglich)?[^.]*\.?",
                re.IGNORECASE | re.DOTALL
            ),
            re.compile(
                r"(?:schadensersatz|pauschaliert)[^.]*(?:\d+)[^.]*\.?",
                re.IGNORECASE | re.DOTALL
            ),
        ],
        extractor="extract_penalty",
        risk_keywords=["unbeschraenkt", "ohne begrenzung", "schadensersatz"],
        confidence_base=0.75,
    ),

    # Kündigungsbedingungen
    ClauseType.TERMINATION_CONDITION.value: ClausePattern(
        clause_type=ClauseType.TERMINATION_CONDITION.value,
        patterns=[
            re.compile(
                r"(?:kündigung|kündigungsrecht)[^.]*"
                r"(?:frist|termin|form|schriftlich)[^.]*\.?",
                re.IGNORECASE | re.DOTALL
            ),
            re.compile(
                r"(?:ausserordentliche\s+kündigung|fristlose\s+kündigung)[^.]*\.?",
                re.IGNORECASE | re.DOTALL
            ),
            re.compile(
                r"(?:der\s+vertrag)[^.]*(?:gekündigt|beendet)[^.]*"
                r"(?:wenn|falls|sofern)[^.]*\.?",
                re.IGNORECASE | re.DOTALL
            ),
        ],
        extractor="extract_termination",
        risk_keywords=["nur schriftlich", "einschreiben", "ausschluss"],
        confidence_base=0.8,
    ),

    # Haftungsbegrenzung
    ClauseType.LIABILITY.value: ClausePattern(
        clause_type=ClauseType.LIABILITY.value,
        patterns=[
            re.compile(
                r"(?:haftung|haftungsbegrenzung|haftungsausschluss)[^.]*\.?",
                re.IGNORECASE | re.DOTALL
            ),
            re.compile(
                r"(?:die\s+haftung|unsere\s+haftung)[^.]*"
                r"(?:begrenzt|beschraenkt|ausgeschlossen)[^.]*\.?",
                re.IGNORECASE | re.DOTALL
            ),
            re.compile(
                r"(?:hoechstbetrag|maximalhaftung)[^.]*(?:\d+)[^.]*(?:euro|eur|%)[^.]*\.?",
                re.IGNORECASE | re.DOTALL
            ),
        ],
        extractor="extract_liability",
        risk_keywords=["ausgeschlossen", "keinerlei", "vollständig"],
        confidence_base=0.75,
    ),

    # Gewährleistung
    ClauseType.WARRANTY.value: ClausePattern(
        clause_type=ClauseType.WARRANTY.value,
        patterns=[
            re.compile(
                r"(?:gewährleistung|garantie|maengelanspruch)[^.]*"
                r"(?:\d+)[^.]*(?:monat|jahr)[^.]*\.?",
                re.IGNORECASE | re.DOTALL
            ),
            re.compile(
                r"(?:gewährleistungsfrist|garantiezeit)[^.]*\.?",
                re.IGNORECASE | re.DOTALL
            ),
            re.compile(
                r"(?:maengel|fehler)[^.]*(?:beheben|beseitigen|nachbesser)[^.]*\.?",
                re.IGNORECASE | re.DOTALL
            ),
        ],
        extractor="extract_warranty",
        risk_keywords=["ausgeschlossen", "verkürzt", "eingeschraenkt"],
        confidence_base=0.8,
    ),

    # Gerichtsstand
    ClauseType.JURISDICTION.value: ClausePattern(
        clause_type=ClauseType.JURISDICTION.value,
        patterns=[
            re.compile(
                r"(?:gerichtsstand|zuständiges\s+gericht)[^.]*"
                r"(?:ist|sind|liegt)[^.]*(?:[A-Z][a-z]+)[^.]*\.?",
                re.IGNORECASE | re.DOTALL
            ),
            re.compile(
                r"(?:es\s+gilt)[^.]*(?:deutsches\s+recht|recht\s+der)[^.]*\.?",
                re.IGNORECASE | re.DOTALL
            ),
            re.compile(
                r"(?:schiedsgericht|arbitration)[^.]*\.?",
                re.IGNORECASE | re.DOTALL
            ),
        ],
        extractor="extract_jurisdiction",
        risk_keywords=["ausland", "foreign", "schiedsgericht"],
        confidence_base=0.85,
    ),

    # Zahlungsbedingungen
    ClauseType.PAYMENT_TERMS.value: ClausePattern(
        clause_type=ClauseType.PAYMENT_TERMS.value,
        patterns=[
            re.compile(
                r"(?:zahlung|zahlungsbedingung|zahlungsziel)[^.]*"
                r"(?:\d+)[^.]*(?:tag|woche)[^.]*\.?",
                re.IGNORECASE | re.DOTALL
            ),
            re.compile(
                r"(?:skonto|rabatt)[^.]*(?:\d+)[^.]*(?:prozent|%)[^.]*"
                r"(?:\d+)[^.]*(?:tag)[^.]*\.?",
                re.IGNORECASE | re.DOTALL
            ),
            re.compile(
                r"(?:fällig|zahlbar)[^.]*(?:sofort|innerhalb|nach)[^.]*\.?",
                re.IGNORECASE | re.DOTALL
            ),
        ],
        extractor="extract_payment_terms",
        risk_keywords=["sofort", "vorkasse", "ohne abzug"],
        confidence_base=0.8,
    ),

    # Datenschutz
    ClauseType.DATA_PROTECTION.value: ClausePattern(
        clause_type=ClauseType.DATA_PROTECTION.value,
        patterns=[
            re.compile(
                r"(?:datenschutz|dsgvo|personenbezogene\s+daten)[^.]*\.?",
                re.IGNORECASE | re.DOTALL
            ),
            re.compile(
                r"(?:auftragsverarbeitung|avv)[^.]*\.?",
                re.IGNORECASE | re.DOTALL
            ),
            re.compile(
                r"(?:datenverarbeitung|datennutzung)[^.]*(?:zustimmung|einwilligung)[^.]*\.?",
                re.IGNORECASE | re.DOTALL
            ),
        ],
        extractor="extract_data_protection",
        risk_keywords=["weitergabe", "dritte", "transfer"],
        confidence_base=0.75,
    ),

    # Vertraulichkeit / Geheimhaltung
    ClauseType.CONFIDENTIALITY.value: ClausePattern(
        clause_type=ClauseType.CONFIDENTIALITY.value,
        patterns=[
            re.compile(
                r"(?:vertraulich|geheimhaltung|verschwiegenheit)[^.]*\.?",
                re.IGNORECASE | re.DOTALL
            ),
            re.compile(
                r"(?:geschäftsgeheimnisse?|betriebsgeheimnisse?)[^.]*\.?",
                re.IGNORECASE | re.DOTALL
            ),
            re.compile(
                r"(?:nda|non[- ]?disclosure)[^.]*\.?",
                re.IGNORECASE | re.DOTALL
            ),
        ],
        extractor="extract_confidentiality",
        risk_keywords=["unbefristet", "strafen", "vertragsstrafe"],
        confidence_base=0.8,
    ),
}


# Number extraction patterns
NUMBER_PATTERNS = {
    "integer": re.compile(r"(\d+)"),
    "decimal": re.compile(r"(\d+[.,]\d+)"),
    "percent": re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:prozent|%|v\.h\.)", re.IGNORECASE),
    "euro": re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:euro|eur|\u20ac)", re.IGNORECASE),
    "months": re.compile(r"(\d+)\s*(?:monat|monate)", re.IGNORECASE),
    "years": re.compile(r"(\d+)\s*(?:jahr|jahre)", re.IGNORECASE),
    "days": re.compile(r"(\d+)\s*(?:tag|tage)", re.IGNORECASE),
    "weeks": re.compile(r"(\d+)\s*(?:woche|wochen)", re.IGNORECASE),
}


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class ExtractedClause:
    """Result of clause extraction."""
    clause_type: str
    clause_text: str
    confidence: float
    extracted_value: Dict[str, Any]
    source_position: Optional[Dict[str, int]] = None
    source_page: Optional[int] = None
    risk_level: Optional[str] = None
    risk_notes: Optional[str] = None
    extraction_method: str = "regex"


@dataclass
class ClauseExtractionResult:
    """Complete result of clause extraction for a document."""
    clauses: List[ExtractedClause]
    document_id: Optional[UUID] = None
    contract_id: Optional[UUID] = None
    total_clauses: int = 0
    extraction_confidence: float = 0.0
    processing_time_ms: int = 0
    warnings: List[str] = field(default_factory=list)


# =============================================================================
# Clause Recognition Service
# =============================================================================


class ClauseRecognitionService:
    """
    Service for recognizing and extracting contract clauses.

    Features:
    - German legal text pattern recognition
    - Structured value extraction
    - Risk level assessment
    - Clause verification workflow

    SECURITY:
    - Never log clause text (business secrets)
    - Multi-tenant via company_id
    """

    def __init__(self, db: AsyncSession):
        """Initialize with database session."""
        self.db = db

    # =========================================================================
    # Main Extraction Methods
    # =========================================================================

    async def extract_clauses_from_text(
        self,
        text: str,
        contract_id: Optional[UUID] = None,
        company_id: Optional[UUID] = None,
        clause_types: Optional[List[str]] = None,
    ) -> ClauseExtractionResult:
        """
        Extract all clauses from contract text.

        Args:
            text: OCR text from contract document
            contract_id: Optional contract ID
            company_id: Optional company ID for storage
            clause_types: Optional list of clause types to extract

        Returns:
            ClauseExtractionResult with all found clauses
        """
        import time
        start_time = time.time()

        result = ClauseExtractionResult(
            clauses=[],
            contract_id=contract_id,
        )

        if not text or len(text) < 100:
            result.warnings.append("Text zu kurz für Klauselextraktion")
            return result

        # Normalize text
        normalized_text = self._normalize_text(text)

        # Determine which clause types to extract
        types_to_extract = clause_types or list(CLAUSE_PATTERNS.keys())

        # Extract each clause type
        for clause_type in types_to_extract:
            if clause_type not in CLAUSE_PATTERNS:
                continue

            pattern_def = CLAUSE_PATTERNS[clause_type]
            extracted = self._extract_clause_type(
                text=normalized_text,
                pattern_def=pattern_def,
            )

            if extracted:
                result.clauses.extend(extracted)

        # Calculate overall confidence
        if result.clauses:
            result.extraction_confidence = sum(c.confidence for c in result.clauses) / len(result.clauses)
        result.total_clauses = len(result.clauses)

        # Processing time
        result.processing_time_ms = int((time.time() - start_time) * 1000)

        logger.info(
            "clauses_extracted",
            total_clauses=result.total_clauses,
            clause_types=[c.clause_type for c in result.clauses],
            confidence=round(result.extraction_confidence, 3),
            processing_ms=result.processing_time_ms,
        )

        return result

    async def extract_and_store_clauses(
        self,
        contract_id: UUID,
        company_id: UUID,
        text: Optional[str] = None,
        document_id: Optional[UUID] = None,
        replace_existing: bool = False,
    ) -> List[ContractClause]:
        """
        Extract clauses and store them in the database.

        Args:
            contract_id: Contract ID
            company_id: Company ID
            text: OCR text (if not provided, will be fetched from contract document)
            document_id: Optional document ID to fetch text from
            replace_existing: Replace existing clauses if True

        Returns:
            List of created ContractClause objects
        """
        from app.db.models import Document

        # Get text if not provided
        if not text:
            # Get from contract's document
            contract = await self.db.get(Contract, contract_id)
            if not contract:
                raise ValueError(f"Vertrag {contract_id} nicht gefunden")

            doc_id = document_id or contract.document_id
            if doc_id:
                doc = await self.db.get(Document, doc_id)
                if doc and doc.ocr_text:
                    text = doc.ocr_text

        if not text:
            logger.warning(
                "no_text_for_clause_extraction",
                contract_id=str(contract_id),
            )
            return []

        # Extract clauses
        extraction_result = await self.extract_clauses_from_text(
            text=text,
            contract_id=contract_id,
            company_id=company_id,
        )

        if not extraction_result.clauses:
            return []

        # Optionally remove existing clauses
        if replace_existing:
            existing = await self.db.execute(
                select(ContractClause).where(
                    ContractClause.contract_id == contract_id
                )
            )
            for clause in existing.scalars().all():
                await self.db.delete(clause)

        # Store new clauses
        created_clauses: List[ContractClause] = []
        for extracted in extraction_result.clauses:
            # Create hash for deduplication
            text_hash = hashlib.sha256(extracted.clause_text.encode()).hexdigest()

            # Check for duplicate
            existing = await self.db.execute(
                select(ContractClause).where(
                    and_(
                        ContractClause.contract_id == contract_id,
                        ContractClause.clause_text_hash == text_hash,
                    )
                )
            )
            if existing.scalar_one_or_none():
                continue

            clause = ContractClause(
                contract_id=contract_id,
                company_id=company_id,
                clause_type=extracted.clause_type,
                clause_text=extracted.clause_text,
                clause_text_hash=text_hash,
                confidence=Decimal(str(round(extracted.confidence, 4))),
                extraction_method=extracted.extraction_method,
                source_page=extracted.source_page,
                source_position=extracted.source_position,
                extracted_value=extracted.extracted_value,
                risk_level=extracted.risk_level,
                risk_notes=extracted.risk_notes,
            )
            self.db.add(clause)
            created_clauses.append(clause)

        if created_clauses:
            await self.db.commit()

        logger.info(
            "clauses_stored",
            contract_id=str(contract_id),
            clauses_created=len(created_clauses),
        )

        return created_clauses

    # =========================================================================
    # Clause Retrieval
    # =========================================================================

    async def get_clauses_for_contract(
        self,
        contract_id: UUID,
        company_id: UUID,
        clause_types: Optional[List[str]] = None,
        verified_only: bool = False,
    ) -> List[ContractClause]:
        """
        Get all clauses for a contract.

        Args:
            contract_id: Contract ID
            company_id: Company ID for access control
            clause_types: Optional filter by clause types
            verified_only: Only return verified clauses

        Returns:
            List of ContractClause objects
        """
        query = select(ContractClause).where(
            and_(
                ContractClause.contract_id == contract_id,
                ContractClause.company_id == company_id,
                ContractClause.is_active == True,
            )
        )

        if clause_types:
            query = query.where(ContractClause.clause_type.in_(clause_types))

        if verified_only:
            query = query.where(ContractClause.is_verified == True)

        query = query.order_by(ContractClause.clause_type, ContractClause.confidence.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_clause_by_id(
        self,
        clause_id: UUID,
        company_id: UUID,
    ) -> Optional[ContractClause]:
        """Get a specific clause by ID."""
        result = await self.db.execute(
            select(ContractClause).where(
                and_(
                    ContractClause.id == clause_id,
                    ContractClause.company_id == company_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def verify_clause(
        self,
        clause_id: UUID,
        company_id: UUID,
        user_id: UUID,
        verified: bool = True,
        updated_value: Optional[Dict[str, Any]] = None,
    ) -> Optional[ContractClause]:
        """
        Verify or update a clause.

        Args:
            clause_id: Clause ID
            company_id: Company ID
            user_id: Verifying user ID
            verified: Verification status
            updated_value: Optional updated extracted value

        Returns:
            Updated clause or None if not found
        """
        clause = await self.get_clause_by_id(clause_id, company_id)
        if not clause:
            return None

        clause.is_verified = verified
        clause.verified_by_id = user_id
        clause.verified_at = datetime.now(timezone.utc)

        if updated_value is not None:
            clause.extracted_value = updated_value
            clause.extraction_method = "manual"
            clause.confidence = Decimal("1.0")

        await self.db.commit()
        await self.db.refresh(clause)

        return clause

    # =========================================================================
    # Internal Extraction Methods
    # =========================================================================

    def _normalize_text(self, text: str) -> str:
        """Normalize text for pattern matching."""
        # Replace common OCR errors
        text = text.replace("\n", " ")
        text = re.sub(r"\s+", " ", text)

        # Normalize German umlauts
        replacements = {
            "ae": "ae", "oe": "oe", "ue": "ue",
            "AE": "AE", "OE": "OE", "UE": "UE",
            "\u00e4": "ae", "\u00f6": "oe", "\u00fc": "ue",
            "\u00c4": "Ae", "\u00d6": "Oe", "\u00dc": "Ue",
            "\u00df": "ss",
        }

        # Keep original umlauts for display but normalize for matching
        return text

    def _extract_clause_type(
        self,
        text: str,
        pattern_def: ClausePattern,
    ) -> List[ExtractedClause]:
        """Extract clauses of a specific type."""
        clauses: List[ExtractedClause] = []
        seen_texts: set = set()

        for pattern in pattern_def.patterns:
            for match in pattern.finditer(text):
                clause_text = match.group(0).strip()

                # Skip if too short or already seen
                if len(clause_text) < 20:
                    continue
                text_hash = hashlib.md5(clause_text.encode()).hexdigest()
                if text_hash in seen_texts:
                    continue
                seen_texts.add(text_hash)

                # Calculate confidence
                confidence = pattern_def.confidence_base
                context = text[max(0, match.start() - 50):min(len(text), match.end() + 50)].lower()

                # Adjust confidence based on context
                if any(kw in context for kw in ["vertrag", "vereinbar", "klausel"]):
                    confidence += 0.05
                if len(clause_text) > 100:
                    confidence += 0.05

                # Extract structured value
                extracted_value = self._extract_structured_value(
                    clause_text=clause_text,
                    clause_type=pattern_def.clause_type,
                )

                # Assess risk
                risk_level, risk_notes = self._assess_clause_risk(
                    clause_text=clause_text,
                    clause_type=pattern_def.clause_type,
                    risk_keywords=pattern_def.risk_keywords,
                )

                clause = ExtractedClause(
                    clause_type=pattern_def.clause_type,
                    clause_text=clause_text,
                    confidence=min(1.0, confidence),
                    extracted_value=extracted_value,
                    source_position={"start": match.start(), "end": match.end()},
                    risk_level=risk_level,
                    risk_notes=risk_notes,
                )
                clauses.append(clause)

        return clauses

    def _extract_structured_value(
        self,
        clause_text: str,
        clause_type: str,
    ) -> Dict[str, Any]:
        """Extract structured values from clause text."""
        text_lower = clause_text.lower()
        value: Dict[str, Any] = {"raw_text": clause_text[:200]}

        if clause_type == ClauseType.PRICE_ADJUSTMENT.value:
            return self._extract_price_adjustment_value(text_lower)

        elif clause_type == ClauseType.MINIMUM_TERM.value:
            return self._extract_minimum_term_value(text_lower)

        elif clause_type == ClauseType.AUTO_RENEWAL.value:
            return self._extract_auto_renewal_value(text_lower)

        elif clause_type == ClauseType.PENALTY.value:
            return self._extract_penalty_value(text_lower)

        elif clause_type == ClauseType.WARRANTY.value:
            return self._extract_warranty_value(text_lower)

        elif clause_type == ClauseType.PAYMENT_TERMS.value:
            return self._extract_payment_terms_value(text_lower)

        elif clause_type == ClauseType.LIABILITY.value:
            return self._extract_liability_value(text_lower)

        return value

    def _extract_price_adjustment_value(self, text: str) -> Dict[str, Any]:
        """Extract price adjustment details."""
        value: Dict[str, Any] = {"type": "unknown"}

        # Check for index-based adjustment
        if "verbraucherpreisindex" in text or "vpi" in text:
            value["type"] = "index"
            value["index_name"] = "VPI"
        elif "index" in text:
            value["type"] = "index"

        # Check for percentage
        percent_match = NUMBER_PATTERNS["percent"].search(text)
        if percent_match:
            value["percent"] = float(percent_match.group(1).replace(",", "."))

        # Check for cap
        if "maximal" in text or "hoechstens" in text:
            cap_match = NUMBER_PATTERNS["percent"].search(text)
            if cap_match:
                value["cap_percent"] = float(cap_match.group(1).replace(",", "."))

        # Check for interval
        if "jährlich" in text or "jahr" in text:
            value["interval"] = "annual"
        elif "quartalsweise" in text or "quartal" in text:
            value["interval"] = "quarterly"

        return value

    def _extract_minimum_term_value(self, text: str) -> Dict[str, Any]:
        """Extract minimum term details."""
        value: Dict[str, Any] = {}

        # Extract months
        months_match = NUMBER_PATTERNS["months"].search(text)
        if months_match:
            value["months"] = int(months_match.group(1))

        # Extract years
        years_match = NUMBER_PATTERNS["years"].search(text)
        if years_match:
            years = int(years_match.group(1))
            value["months"] = value.get("months", 0) + (years * 12)

        # Check for binding
        value["binding"] = "unkuendbar" in text or "bindend" in text

        return value

    def _extract_auto_renewal_value(self, text: str) -> Dict[str, Any]:
        """Extract auto renewal details."""
        value: Dict[str, Any] = {"enabled": True}

        # Extract renewal period
        months_match = NUMBER_PATTERNS["months"].search(text)
        if months_match:
            value["period_months"] = int(months_match.group(1))

        years_match = NUMBER_PATTERNS["years"].search(text)
        if years_match:
            value["period_months"] = int(years_match.group(1)) * 12

        # Extract notice period
        if "kündig" in text:
            days_match = NUMBER_PATTERNS["days"].search(text)
            if days_match:
                value["notice_days"] = int(days_match.group(1))
            weeks_match = NUMBER_PATTERNS["weeks"].search(text)
            if weeks_match:
                value["notice_days"] = int(weeks_match.group(1)) * 7
            months_match2 = NUMBER_PATTERNS["months"].search(text[text.find("kündig"):])
            if months_match2:
                value["notice_days"] = int(months_match2.group(1)) * 30

        return value

    def _extract_penalty_value(self, text: str) -> Dict[str, Any]:
        """Extract penalty details."""
        value: Dict[str, Any] = {}

        # Extract penalty percentage
        percent_match = NUMBER_PATTERNS["percent"].search(text)
        if percent_match:
            value["percent"] = float(percent_match.group(1).replace(",", "."))

        # Extract euro amount
        euro_match = NUMBER_PATTERNS["euro"].search(text)
        if euro_match:
            value["amount_eur"] = float(euro_match.group(1).replace(",", "."))

        # Check for type
        if "verzug" in text or "verspätung" in text:
            value["type"] = "late_delivery"
        elif "mangel" in text or "fehler" in text:
            value["type"] = "defect"
        else:
            value["type"] = "general"

        # Check for cap
        if "maximal" in text or "hoechstens" in text or "begrenzt" in text:
            cap_match = NUMBER_PATTERNS["percent"].search(text[text.find("maximal"):] if "maximal" in text else text)
            if cap_match:
                value["max_percent"] = float(cap_match.group(1).replace(",", "."))

        return value

    def _extract_warranty_value(self, text: str) -> Dict[str, Any]:
        """Extract warranty details."""
        value: Dict[str, Any] = {}

        # Extract warranty period
        months_match = NUMBER_PATTERNS["months"].search(text)
        if months_match:
            value["period_months"] = int(months_match.group(1))

        years_match = NUMBER_PATTERNS["years"].search(text)
        if years_match:
            years = int(years_match.group(1))
            value["period_months"] = value.get("period_months", 0) + (years * 12)

        # Check warranty type
        if "nachbesser" in text or "beseitigung" in text:
            value["type"] = "repair"
        elif "ersatz" in text or "neuliefer" in text:
            value["type"] = "replacement"
        elif "minderung" in text or "preisnachlass" in text:
            value["type"] = "price_reduction"

        return value

    def _extract_payment_terms_value(self, text: str) -> Dict[str, Any]:
        """Extract payment terms details."""
        value: Dict[str, Any] = {}

        # Extract payment deadline
        days_match = NUMBER_PATTERNS["days"].search(text)
        if days_match:
            value["due_days"] = int(days_match.group(1))

        # Extract skonto
        if "skonto" in text:
            percent_match = NUMBER_PATTERNS["percent"].search(text[text.find("skonto"):])
            if percent_match:
                value["skonto_percent"] = float(percent_match.group(1).replace(",", "."))
            days_match2 = NUMBER_PATTERNS["days"].search(text[text.find("skonto"):])
            if days_match2:
                value["skonto_days"] = int(days_match2.group(1))

        # Check payment type
        if "vorkasse" in text or "vorauszahlung" in text:
            value["type"] = "prepayment"
        elif "nachnahme" in text:
            value["type"] = "cod"
        elif "überweisung" in text:
            value["type"] = "bank_transfer"

        return value

    def _extract_liability_value(self, text: str) -> Dict[str, Any]:
        """Extract liability details."""
        value: Dict[str, Any] = {}

        # Extract liability limit
        euro_match = NUMBER_PATTERNS["euro"].search(text)
        if euro_match:
            value["limit_eur"] = float(euro_match.group(1).replace(",", "."))

        percent_match = NUMBER_PATTERNS["percent"].search(text)
        if percent_match:
            value["limit_percent"] = float(percent_match.group(1).replace(",", "."))

        # Check for exclusions
        if "ausgeschlossen" in text:
            value["excluded"] = True
        if "vorsatz" in text or "grobe fahrl" in text:
            value["except_gross_negligence"] = True
        if "personenschaden" in text or "koerper" in text:
            value["except_personal_injury"] = True

        return value

    def _assess_clause_risk(
        self,
        clause_text: str,
        clause_type: str,
        risk_keywords: List[str],
    ) -> Tuple[Optional[str], Optional[str]]:
        """Assess risk level of a clause."""
        text_lower = clause_text.lower()
        risk_factors: List[str] = []

        # Check risk keywords
        for keyword in risk_keywords:
            if keyword in text_lower:
                risk_factors.append(f"Risiko-Keyword: {keyword}")

        # Type-specific risk assessment
        if clause_type == ClauseType.PRICE_ADJUSTMENT.value:
            if "unbegrenzt" in text_lower or "ohne limit" in text_lower:
                risk_factors.append("Unbegrenzte Preisanpassung möglich")
            if "einseitig" in text_lower:
                risk_factors.append("Einseitige Anpassung durch Vertragspartner")

        elif clause_type == ClauseType.MINIMUM_TERM.value:
            months_match = NUMBER_PATTERNS["months"].search(text_lower)
            years_match = NUMBER_PATTERNS["years"].search(text_lower)
            total_months = 0
            if months_match:
                total_months += int(months_match.group(1))
            if years_match:
                total_months += int(years_match.group(1)) * 12
            if total_months > 24:
                risk_factors.append(f"Lange Mindestlaufzeit: {total_months} Monate")

        elif clause_type == ClauseType.LIABILITY.value:
            if "ausgeschlossen" in text_lower and "vorsatz" not in text_lower:
                risk_factors.append("Weitgehender Haftungsausschluss")

        elif clause_type == ClauseType.PENALTY.value:
            percent_match = NUMBER_PATTERNS["percent"].search(text_lower)
            if percent_match and float(percent_match.group(1).replace(",", ".")) > 10:
                risk_factors.append("Hohe Vertragsstrafe")

        # Determine risk level
        if len(risk_factors) >= 3:
            return "critical", "; ".join(risk_factors)
        elif len(risk_factors) >= 2:
            return "high", "; ".join(risk_factors)
        elif len(risk_factors) >= 1:
            return "medium", "; ".join(risk_factors)

        return "low", None


# =============================================================================
# Factory Function
# =============================================================================


def get_clause_recognition_service(db: AsyncSession) -> ClauseRecognitionService:
    """Factory function to create ClauseRecognitionService instance."""
    return ClauseRecognitionService(db)
