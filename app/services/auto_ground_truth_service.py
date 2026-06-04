# -*- coding: utf-8 -*-
"""
Auto Ground-Truth Service für Ablage-System OCR.

Automatische Ground-Truth-Generierung aus High-Confidence OCR für Enterprise-Scale.

Bei 500+ Dokumenten/Tag ist manuelle Annotation unrealistisch.
Dieser Service implementiert die "Smart Ground-Truth Pipeline":

1. OCR-Ergebnisse mit Confidence >= 95% werden automatisch als Ground-Truth akzeptiert
2. Umlaut-Validierung vor Auto-Accept (keine "ae" statt "ae" durchlassen)
3. Strukturelle Validierung für Rechnungen (Betrag, Datum, Rechnungsnummer)
4. 10% Stichproben-Review für Qualitätssicherung
5. Business-Priorität basierend auf Dokumenttyp

Feinpoliert und durchdacht - Enterprise-grade Auto-Annotation.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
import hashlib
import re

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.models import (
    OCRTrainingSample,
    BusinessDocumentProfile,
    Document,
    TrainingSampleStatus,
)
from app.services.umlaut_validation_service import (

    UmlautValidationService,
    UmlautValidationResult,
)
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class AutoAcceptResult:
    """Ergebnis der Auto-Accept-Entscheidung."""
    should_accept: bool
    reasons: List[str]
    confidence: float
    validation_details: Dict[str, Any]
    business_priority: float = 1.0


@dataclass
class StructuralValidationResult:
    """Ergebnis der strukturellen Validierung."""
    is_valid: bool
    missing_fields: List[str]
    found_fields: Dict[str, str]
    validation_score: float


@dataclass
class ProcessingResult:
    """Ergebnis der Ground-Truth-Verarbeitung."""
    success: bool
    sample_id: Optional[UUID] = None
    auto_accepted: bool = False
    needs_manual_review: bool = False
    reasons: List[str] = None

    def __post_init__(self):
        if self.reasons is None:
            self.reasons = []


# =============================================================================
# Auto Ground-Truth Service
# =============================================================================

class AutoGroundTruthService:
    """
    Service für automatische Ground-Truth-Generierung aus High-Confidence OCR.

    Bei 500+ Docs/Tag: OCR-Ergebnisse mit Confidence > 95% werden
    automatisch als Ground-Truth akzeptiert (mit Flagging für Stichproben-Review).
    """

    # Stichproben-Rate für Auto-Accepted Samples (10%)
    SPOT_CHECK_RATE = 0.10

    # Minimale Textlänge für valide Ground-Truth
    MIN_TEXT_LENGTH = 50

    # Default Auto-Accept Confidence (wird von Profile überschrieben)
    DEFAULT_CONFIDENCE_THRESHOLD = 0.95

    # Strukturelle Validierung: Pflichtfelder pro Dokumenttyp
    REQUIRED_FIELDS = {
        "invoice": ["invoice_number", "date", "amount"],
        "contract": ["date"],
        "letter": [],
        "delivery_note": ["date"],
        "order_confirmation": ["date", "order_number"],
    }

    # Regex-Pattern für Feld-Erkennung
    FIELD_PATTERNS = {
        "invoice_number": [
            r"Rechnungs?-?Nr\.?\s*:?\s*([\w\-/]+)",
            r"Rechnung\s+Nr\.?\s*:?\s*([\w\-/]+)",
            r"Invoice\s*#?\s*:?\s*([\w\-/]+)",
            r"RE-\d{4,}",
        ],
        "date": [
            r"(\d{2}[.\-/]\d{2}[.\-/]\d{4})",
            r"(\d{2}[.\-/]\d{2}[.\-/]\d{2})",
            r"(\d{4}[.\-/]\d{2}[.\-/]\d{2})",
        ],
        "amount": [
            r"Gesamt\s*:?\s*([\d.,]+)\s*(?:EUR|€)?",
            r"Summe\s*:?\s*([\d.,]+)\s*(?:EUR|€)?",
            r"Betrag\s*:?\s*([\d.,]+)\s*(?:EUR|€)?",
            r"Total\s*:?\s*([\d.,]+)\s*(?:EUR|€)?",
            r"([\d.,]+)\s*€",
        ],
        "order_number": [
            r"Bestell-?Nr\.?\s*:?\s*([\w\-/]+)",
            r"Auftrags-?Nr\.?\s*:?\s*([\w\-/]+)",
            r"Order\s*#?\s*:?\s*([\w\-/]+)",
        ],
    }

    def __init__(self):
        """Initialisiere Auto Ground-Truth Service."""
        self.umlaut_validator = UmlautValidationService()

    # =========================================================================
    # MAIN API
    # =========================================================================

    async def process_document_for_training(
        self,
        db: AsyncSession,
        document_id: UUID,
        ocr_text: str,
        ocr_confidence: float,
        document_type: Optional[str] = None,
        file_path: Optional[str] = None,
        file_hash: Optional[str] = None,
        extracted_fields: Optional[Dict[str, Any]] = None,
    ) -> ProcessingResult:
        """
        Entscheidet ob OCR-Ergebnis als Ground-Truth akzeptiert wird.

        Kriterien:
        1. Confidence >= profile.auto_accept_confidence (default 95%)
        2. Umlaut-Validierung bestanden
        3. Strukturelle Validierung (bei Rechnungen: Betrag, Datum vorhanden)

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            ocr_text: OCR-extrahierter Text
            ocr_confidence: Confidence-Score des OCR-Backends (0-1)
            document_type: Dokumenttyp (invoice, contract, etc.)
            file_path: Pfad zur Datei
            file_hash: SHA-256 Hash der Datei
            extracted_fields: Bereits extrahierte Felder

        Returns:
            ProcessingResult mit Entscheidung und ggf. erstelltem Sample
        """
        logger.info(
            "auto_ground_truth_processing",
            document_id=str(document_id),
            document_type=document_type,
            ocr_confidence=ocr_confidence,
            text_length=len(ocr_text) if ocr_text else 0,
        )

        # Hole Business-Profil für Dokumenttyp
        profile = await self._get_document_profile(db, document_type)

        # Validiere für Auto-Accept
        accept_result = await self.validate_for_auto_accept(
            text=ocr_text,
            document_type=document_type,
            confidence=ocr_confidence,
            profile=profile,
            extracted_fields=extracted_fields,
        )

        if accept_result.should_accept:
            # Erstelle Auto-Accepted Training Sample
            sample = await self._create_auto_accepted_sample(
                db=db,
                document_id=document_id,
                ocr_text=ocr_text,
                ocr_confidence=ocr_confidence,
                document_type=document_type,
                file_path=file_path,
                file_hash=file_hash,
                business_priority=accept_result.business_priority,
                extracted_fields=extracted_fields,
            )

            logger.info(
                "auto_ground_truth_accepted",
                document_id=str(document_id),
                sample_id=str(sample.id),
                confidence=ocr_confidence,
                needs_spot_check=sample.needs_spot_check,
            )

            return ProcessingResult(
                success=True,
                sample_id=sample.id,
                auto_accepted=True,
                needs_manual_review=sample.needs_spot_check,
                reasons=accept_result.reasons,
            )
        else:
            # Sample geht in manuelle Verifikations-Queue
            logger.info(
                "auto_ground_truth_rejected",
                document_id=str(document_id),
                reasons=accept_result.reasons,
                confidence=ocr_confidence,
            )

            return ProcessingResult(
                success=False,
                auto_accepted=False,
                needs_manual_review=True,
                reasons=accept_result.reasons,
            )

    async def validate_for_auto_accept(
        self,
        text: str,
        document_type: Optional[str],
        confidence: float,
        profile: Optional[BusinessDocumentProfile] = None,
        extracted_fields: Optional[Dict[str, Any]] = None,
    ) -> AutoAcceptResult:
        """
        Validiert ob Text für Auto-Accept geeignet.

        Prüft:
        - Confidence >= Schwellenwert
        - Umlaut-Konsistenz (keine "ae" statt "ae")
        - Strukturelle Felder (Rechnungsnummer, Datum bei Invoices)
        - Keine offensichtlichen OCR-Artefakte

        Args:
            text: OCR-Text
            document_type: Dokumenttyp
            confidence: OCR Confidence (0-1)
            profile: Business Document Profile (optional)
            extracted_fields: Bereits extrahierte Felder

        Returns:
            AutoAcceptResult mit Entscheidung und Gruenden
        """
        reasons = []
        validation_details = {}
        should_accept = True

        # Bestimme Schwellenwerte
        confidence_threshold = (
            profile.auto_accept_confidence
            if profile
            else self.DEFAULT_CONFIDENCE_THRESHOLD
        )
        min_text_length = (
            profile.min_text_length
            if profile
            else self.MIN_TEXT_LENGTH
        )
        require_umlaut_validation = (
            profile.require_umlaut_validation
            if profile
            else True
        )
        business_priority = (
            profile.training_weight
            if profile
            else 1.0
        )

        # 1. Text-Länge prüfen
        if not text or len(text) < min_text_length:
            reasons.append(f"Text zu kurz ({len(text) if text else 0} < {min_text_length})")
            should_accept = False
            validation_details["text_length_valid"] = False
        else:
            validation_details["text_length_valid"] = True

        # 2. Confidence prüfen
        if confidence < confidence_threshold:
            reasons.append(f"Confidence zu niedrig ({confidence:.2%} < {confidence_threshold:.2%})")
            should_accept = False
            validation_details["confidence_valid"] = False
        else:
            validation_details["confidence_valid"] = True
            reasons.append(f"Confidence OK ({confidence:.2%})")

        # 3. Umlaut-Validierung
        if require_umlaut_validation and text:
            umlaut_result = self._validate_umlauts(text)
            validation_details["umlaut_validation"] = {
                "accuracy": umlaut_result.umlaut_accuracy,
                "suggestions_count": len(umlaut_result.suggestions),
            }

            # Ablehnen wenn zu viele Umlaut-Fehler
            if umlaut_result.umlaut_accuracy < 0.95:
                reasons.append(f"Umlaut-Accuracy zu niedrig ({umlaut_result.umlaut_accuracy:.2%})")
                should_accept = False
            elif umlaut_result.suggestions:
                reasons.append(f"{len(umlaut_result.suggestions)} potentielle Umlaut-Fehler gefunden")
                # Bei wenigen Fehlern nur Warnung, kein Ablehnen
                if len(umlaut_result.suggestions) > 5:
                    should_accept = False

        # 4. OCR-Artefakt-Prüfung
        artifact_check = self._check_ocr_artifacts(text)
        validation_details["artifacts"] = artifact_check
        if artifact_check["has_artifacts"]:
            reasons.append(f"OCR-Artefakte gefunden: {', '.join(artifact_check['artifact_types'])}")
            should_accept = False

        # 5. Strukturelle Validierung (typ-spezifisch)
        if document_type and text:
            structural_result = self._validate_structure(
                text=text,
                document_type=document_type,
                extracted_fields=extracted_fields,
            )
            validation_details["structural"] = {
                "is_valid": structural_result.is_valid,
                "score": structural_result.validation_score,
                "missing_fields": structural_result.missing_fields,
                "found_fields": structural_result.found_fields,
            }

            if not structural_result.is_valid:
                reasons.append(f"Fehlende Pflichtfelder: {', '.join(structural_result.missing_fields)}")
                should_accept = False
            else:
                reasons.append(f"Strukturelle Validierung OK (Score: {structural_result.validation_score:.2f})")

        return AutoAcceptResult(
            should_accept=should_accept,
            reasons=reasons,
            confidence=confidence,
            validation_details=validation_details,
            business_priority=business_priority,
        )

    async def process_batch(
        self,
        db: AsyncSession,
        document_ids: List[UUID],
        max_documents: int = 100,
    ) -> Dict[str, Any]:
        """
        Verarbeitet einen Batch von Dokumenten für Auto-Ground-Truth.

        Args:
            db: Datenbank-Session
            document_ids: Liste von Dokument-IDs
            max_documents: Maximale Anzahl zu verarbeitender Dokumente

        Returns:
            Dict mit Batch-Statistiken
        """
        results = {
            "processed": 0,
            "auto_accepted": 0,
            "rejected": 0,
            "spot_check_flagged": 0,
            "errors": 0,
            "details": [],
        }

        for doc_id in document_ids[:max_documents]:
            try:
                # Hole Dokument mit OCR-Daten
                doc = await self._get_document_with_ocr(db, doc_id)
                if not doc:
                    continue

                result = await self.process_document_for_training(
                    db=db,
                    document_id=doc_id,
                    ocr_text=doc.get("ocr_text", ""),
                    ocr_confidence=doc.get("confidence", 0.0),
                    document_type=doc.get("document_type"),
                    file_path=doc.get("file_path"),
                    file_hash=doc.get("file_hash"),
                )

                results["processed"] += 1
                if result.auto_accepted:
                    results["auto_accepted"] += 1
                    if result.needs_manual_review:
                        results["spot_check_flagged"] += 1
                else:
                    results["rejected"] += 1

            except Exception as e:
                logger.error(
                    "auto_ground_truth_batch_error",
                    document_id=str(doc_id),
                    **safe_error_log(e),
                )
                results["errors"] += 1

        await db.commit()
        return results

    # =========================================================================
    # INTERNAL HELPERS
    # =========================================================================

    async def _get_document_profile(
        self,
        db: AsyncSession,
        document_type: Optional[str],
    ) -> Optional[BusinessDocumentProfile]:
        """Holt Business-Profil für Dokumenttyp."""
        if not document_type:
            return None

        result = await db.execute(
            select(BusinessDocumentProfile)
            .where(BusinessDocumentProfile.document_type == document_type)
            .where(BusinessDocumentProfile.is_active == True)
        )
        return result.scalar_one_or_none()

    async def _get_document_with_ocr(
        self,
        db: AsyncSession,
        document_id: UUID,
    ) -> Optional[Dict[str, Any]]:
        """Holt Dokument mit OCR-Daten."""
        result = await db.execute(
            select(Document).where(Document.id == document_id)
        )
        doc = result.scalar_one_or_none()

        if not doc:
            return None

        return {
            "ocr_text": doc.extracted_text if hasattr(doc, "extracted_text") else "",
            "confidence": doc.ocr_confidence if hasattr(doc, "ocr_confidence") else 0.0,
            "document_type": doc.document_type if hasattr(doc, "document_type") else None,
            "file_path": doc.file_path if hasattr(doc, "file_path") else None,
            "file_hash": doc.file_hash if hasattr(doc, "file_hash") else None,
        }

    async def _create_auto_accepted_sample(
        self,
        db: AsyncSession,
        document_id: UUID,
        ocr_text: str,
        ocr_confidence: float,
        document_type: Optional[str],
        file_path: Optional[str],
        file_hash: Optional[str],
        business_priority: float,
        extracted_fields: Optional[Dict[str, Any]],
    ) -> OCRTrainingSample:
        """Erstellt ein Auto-Accepted Training Sample."""

        # Berechne File-Hash falls nicht vorhanden
        if not file_hash and file_path:
            file_hash = hashlib.sha256(file_path.encode()).hexdigest()

        # Entscheide ob Stichprobe - DETERMINISTIC: Hash-basiert für Reproduzierbarkeit
        # Verwende file_hash oder document_id für deterministische Entscheidung
        spot_check_seed = file_hash or str(document_id) or ""
        spot_check_hash = int(hashlib.md5(spot_check_seed.encode()).hexdigest()[:8], 16)
        needs_spot_check = (spot_check_hash % 100) < (self.SPOT_CHECK_RATE * 100)

        # Erkenne Umlaute im Text
        has_umlauts = self._detect_umlauts(ocr_text)
        umlaut_words = self._extract_umlaut_words(ocr_text)

        sample = OCRTrainingSample(
            # Dokumentreferenz
            file_path=file_path or f"document:{document_id}",
            file_hash=file_hash or hashlib.sha256(str(document_id).encode()).hexdigest(),

            # Ground Truth (vom OCR)
            ground_truth_text=ocr_text,

            # Dokumentklassifikation
            language="de",
            document_type=document_type,
            difficulty="medium",

            # Dokumenteigenschaften
            has_umlauts=has_umlauts,
            umlaut_words=umlaut_words,
            extracted_fields=extracted_fields or {},

            # Workflow Status - Auto-Verified
            status=TrainingSampleStatus.VERIFIED.value,

            # Auto-Accept Pipeline Felder
            business_priority=business_priority,
            auto_accepted=True,
            auto_acceptance_confidence=ocr_confidence,
            source="auto_accepted",
            needs_spot_check=needs_spot_check,

            # Timestamps
            verified_at=datetime.now(timezone.utc),
        )

        db.add(sample)
        await db.flush()

        # Update Profile Statistics
        await self._update_profile_statistics(db, document_type)

        return sample

    async def _update_profile_statistics(
        self,
        db: AsyncSession,
        document_type: Optional[str],
    ) -> None:
        """Aktualisiert Statistiken im Business-Profil."""
        if not document_type:
            return

        profile = await self._get_document_profile(db, document_type)
        if not profile:
            return

        # Zaehle Samples
        count_result = await db.execute(
            select(func.count(OCRTrainingSample.id))
            .where(OCRTrainingSample.document_type == document_type)
            .where(OCRTrainingSample.deleted_at.is_(None))
        )
        total_count = count_result.scalar() or 0

        verified_result = await db.execute(
            select(func.count(OCRTrainingSample.id))
            .where(OCRTrainingSample.document_type == document_type)
            .where(OCRTrainingSample.status == TrainingSampleStatus.VERIFIED.value)
            .where(OCRTrainingSample.deleted_at.is_(None))
        )
        verified_count = verified_result.scalar() or 0

        auto_accepted_result = await db.execute(
            select(func.count(OCRTrainingSample.id))
            .where(OCRTrainingSample.document_type == document_type)
            .where(OCRTrainingSample.auto_accepted == True)
            .where(OCRTrainingSample.deleted_at.is_(None))
        )
        auto_accepted_count = auto_accepted_result.scalar() or 0

        # Berechne Coverage
        target_samples = int(profile.estimated_daily_volume * profile.target_coverage * 0.1)
        coverage = verified_count / target_samples if target_samples > 0 else 0.0

        # Update Profile
        profile.current_sample_count = total_count
        profile.verified_sample_count = verified_count
        profile.auto_accepted_count = auto_accepted_count
        profile.coverage_percentage = min(coverage, 1.0)

    def _validate_umlauts(self, text: str) -> UmlautValidationResult:
        """Validiert Umlaute im Text."""
        return self.umlaut_validator.validate_text(text)

    def _check_ocr_artifacts(self, text: str) -> Dict[str, Any]:
        """Prüft auf typische OCR-Artefakte."""
        artifact_types = []

        # Zu viele Sonderzeichen in Folge
        if re.search(r'[^\w\s]{5,}', text):
            artifact_types.append("sonderzeichen_cluster")

        # Zu viele Zahlen-Buchstaben-Wechsel (typisches OCR-Problem)
        if re.search(r'(\d[a-zA-Z]){4,}|([a-zA-Z]\d){4,}', text):
            artifact_types.append("digit_letter_confusion")

        # Ungewoehnliche Zeichen
        unusual_chars = re.findall(r'[^\w\s\-\.,;:!?()"\'\u00C0-\u017F€$%&/=+*#@]', text)
        if len(unusual_chars) > 10:
            artifact_types.append("unusual_characters")

        # Zu viele Grossbuchstaben in Reihe (ausser Akronyme)
        if re.search(r'[A-Z]{10,}', text):
            artifact_types.append("excessive_caps")

        return {
            "has_artifacts": len(artifact_types) > 0,
            "artifact_types": artifact_types,
        }

    def _validate_structure(
        self,
        text: str,
        document_type: str,
        extracted_fields: Optional[Dict[str, Any]] = None,
    ) -> StructuralValidationResult:
        """Validiert strukturelle Anforderungen für Dokumenttyp."""
        required_fields = self.REQUIRED_FIELDS.get(document_type, [])
        found_fields = {}
        missing_fields = []

        # Prüfe bereits extrahierte Felder
        if extracted_fields:
            for field in required_fields:
                if field in extracted_fields and extracted_fields[field]:
                    found_fields[field] = str(extracted_fields[field])

        # Versuche fehlende Felder im Text zu finden
        for field in required_fields:
            if field in found_fields:
                continue

            patterns = self.FIELD_PATTERNS.get(field, [])
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    found_fields[field] = match.group(1) if match.groups() else match.group(0)
                    break

            if field not in found_fields:
                missing_fields.append(field)

        # Berechne Validierungs-Score
        if not required_fields:
            score = 1.0
        else:
            score = len(found_fields) / len(required_fields)

        return StructuralValidationResult(
            is_valid=len(missing_fields) == 0,
            missing_fields=missing_fields,
            found_fields=found_fields,
            validation_score=score,
        )

    def _detect_umlauts(self, text: str) -> bool:
        """Erkennt ob Text deutsche Umlaute enthält."""
        umlaut_pattern = r'[äöüÄÖÜß]'
        return bool(re.search(umlaut_pattern, text))

    def _extract_umlaut_words(self, text: str) -> List[str]:
        """Extrahiert Woerter mit Umlauten."""
        umlaut_pattern = r'\b\w*[äöüÄÖÜß]\w*\b'
        matches = re.findall(umlaut_pattern, text)
        # Deduplizieren und limitieren
        unique_words = list(set(matches))
        return unique_words[:100]  # Max 100 Woerter speichern


# =============================================================================
# Singleton Instance
# =============================================================================

_auto_ground_truth_service: Optional[AutoGroundTruthService] = None


def get_auto_ground_truth_service() -> AutoGroundTruthService:
    """Holt oder erstellt Singleton-Instanz des AutoGroundTruthService."""
    global _auto_ground_truth_service
    if _auto_ground_truth_service is None:
        _auto_ground_truth_service = AutoGroundTruthService()
    return _auto_ground_truth_service
