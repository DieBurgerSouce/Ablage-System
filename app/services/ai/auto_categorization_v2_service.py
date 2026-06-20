# -*- coding: utf-8 -*-
"""
AutoCategorizationV2Service - LLM-basierte Dokument-Kategorisierung 2.0.

Erweitert die bestehende Pattern-basierte Kategorisierung um:
- Ollama-basierte kontextuelle Analyse
- Multi-Label-Klassifikation
- Erklärungen warum eine Kategorie gewaehlt wurde
- Lernen aus User-Korrekturen
- Confidence-Kalibrierung

On-Premises: Nutzt ausschließlich lokales Ollama (keine Cloud-LLMs).

Feinpoliert und durchdacht - Enterprise Document Intelligence.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Set

import structlog
from prometheus_client import Counter, Histogram, Gauge
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, AppConfig
from app.services.ai.decision_service import (
    AIDecisionService,
    AIDecisionResult,
    DecisionType,
    get_ai_decision_service,
)
from app.services.ai.ollama_service import OllamaService, get_ollama_service
from app.services.ai.auto_categorization_service import (
    AutoCategorizationService,
    CategorizationResult,
    DocumentCategory,
    CATEGORY_PATTERNS,
    CategoryPattern,
    get_auto_categorization_service,
)
from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

CATEGORIZATION_V2_REQUESTS = Counter(
    "auto_categorization_v2_requests_total",
    "Anzahl der LLM-Kategorisierungs-Anfragen",
    ["category", "confidence_level", "method"]
)

CATEGORIZATION_V2_DURATION = Histogram(
    "auto_categorization_v2_duration_seconds",
    "Dauer der LLM-Kategorisierung in Sekunden",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

LLM_FALLBACK_RATE = Counter(
    "categorization_v2_llm_fallback_total",
    "Anzahl Fallbacks auf Pattern-basierte Kategorisierung",
    ["reason"]
)

CORRECTION_LEARNING_EVENTS = Counter(
    "categorization_v2_correction_learning_total",
    "Anzahl gelernter Korrekturen",
    ["original_category", "corrected_category"]
)

CALIBRATION_ACCURACY = Gauge(
    "categorization_v2_calibration_accuracy",
    "Aktuelle Kalibrierungs-Genauigkeit",
    ["category"]
)


# =============================================================================
# Enums und Konstanten
# =============================================================================

class CategorizationMethod(str, Enum):
    """Methode der Kategorisierung."""
    PATTERN = "pattern"  # Nur Pattern-Matching (V1)
    LLM = "llm"  # Nur LLM
    HYBRID = "hybrid"  # Pattern + LLM Kombination
    CACHED = "cached"  # Aus Cache (gleicher Dokumentinhalt)


class DocumentType(str, Enum):
    """Erweiterte Dokumenttypen für Multi-Label."""
    INVOICE = "invoice"
    CONTRACT = "contract"
    DELIVERY_NOTE = "delivery_note"
    OFFER = "offer"
    ORDER = "order"
    CREDIT_NOTE = "credit_note"
    RECEIPT = "receipt"
    LETTER = "letter"
    REPORT = "report"
    REMINDER = "reminder"
    BANK_STATEMENT = "bank_statement"
    TAX_DOCUMENT = "tax_document"
    CORRESPONDENCE = "correspondence"
    OTHER = "other"


# Mapping zwischen alten und neuen Kategorien
CATEGORY_MAPPING: Dict[str, DocumentType] = {
    DocumentCategory.INVOICE_INCOMING: DocumentType.INVOICE,
    DocumentCategory.INVOICE_OUTGOING: DocumentType.INVOICE,
    DocumentCategory.DELIVERY_NOTE: DocumentType.DELIVERY_NOTE,
    DocumentCategory.ORDER: DocumentType.ORDER,
    DocumentCategory.CONTRACT: DocumentType.CONTRACT,
    DocumentCategory.OFFER: DocumentType.OFFER,
    DocumentCategory.REMINDER: DocumentType.REMINDER,
    DocumentCategory.CREDIT_NOTE: DocumentType.CREDIT_NOTE,
    DocumentCategory.RECEIPT: DocumentType.RECEIPT,
    DocumentCategory.BANK_STATEMENT: DocumentType.BANK_STATEMENT,
    DocumentCategory.TAX_DOCUMENT: DocumentType.TAX_DOCUMENT,
    DocumentCategory.CORRESPONDENCE: DocumentType.CORRESPONDENCE,
    DocumentCategory.OTHER: DocumentType.OTHER,
}

# Deutsche Namen für UI
DOCUMENT_TYPE_LABELS_DE: Dict[DocumentType, str] = {
    DocumentType.INVOICE: "Rechnung",
    DocumentType.CONTRACT: "Vertrag",
    DocumentType.DELIVERY_NOTE: "Lieferschein",
    DocumentType.OFFER: "Angebot",
    DocumentType.ORDER: "Bestellung",
    DocumentType.CREDIT_NOTE: "Gutschrift",
    DocumentType.RECEIPT: "Quittung",
    DocumentType.LETTER: "Brief",
    DocumentType.REPORT: "Bericht",
    DocumentType.REMINDER: "Mahnung",
    DocumentType.BANK_STATEMENT: "Kontoauszug",
    DocumentType.TAX_DOCUMENT: "Steuerdokument",
    DocumentType.CORRESPONDENCE: "Korrespondenz",
    DocumentType.OTHER: "Sonstiges",
}


# =============================================================================
# Dataclasses
# =============================================================================

@dataclass
class CategoryLabel:
    """Einzelnes Kategorie-Label mit Confidence."""
    document_type: DocumentType
    confidence: float
    is_primary: bool = False


@dataclass
class CategoryExplanation:
    """Erklärung für Kategorisierung."""
    summary: str  # Kurzfassung auf Deutsch
    key_indicators: List[str]  # Gefundene Schluesselbegriffe
    context_clues: List[str]  # Kontextuelle Hinweise
    reasoning: str  # Detaillierte Begruendung


@dataclass
class CategorizationV2Result:
    """Erweitertes Kategorisierungs-Ergebnis."""
    primary_type: DocumentType
    primary_confidence: float
    labels: List[CategoryLabel]  # Multi-Label mit Confidences
    explanation: CategoryExplanation
    method: CategorizationMethod
    processing_time_ms: int
    llm_model: Optional[str] = None
    pattern_result: Optional[CategorizationResult] = None  # V1 Fallback-Ergebnis
    calibrated_confidence: Optional[float] = None  # Nach Kalibrierung


@dataclass
class CorrectionEntry:
    """Einzelner Korrektur-Eintrag für Lernen."""
    document_id: uuid.UUID
    original_type: DocumentType
    corrected_type: DocumentType
    text_hash: str  # SHA-256 des Textes
    text_snippet: str  # Erste 500 Zeichen
    keywords_found: List[str]
    corrected_at: datetime
    corrected_by_id: Optional[uuid.UUID] = None


@dataclass
class CalibrationData:
    """Kalibrierungsdaten für eine Kategorie."""
    document_type: DocumentType
    total_predictions: int
    correct_predictions: int
    accuracy: float
    confidence_adjustment: float  # Wird auf Confidence addiert/subtrahiert
    last_updated: datetime


# =============================================================================
# LLM Prompt Templates
# =============================================================================

CLASSIFICATION_SYSTEM_PROMPT = """Du bist ein Dokumenten-Klassifizierungssystem für deutsche Geschäftsdokumente.

Deine Aufgabe:
1. Analysiere den Dokumententext
2. Bestimme den Dokumenttyp
3. Erkläre deine Entscheidung

Verfügbare Dokumenttypen:
- invoice: Rechnung (Eingangs- oder Ausgangsrechnung)
- contract: Vertrag (Kauf-, Miet-, Dienstleistungsvertrag)
- delivery_note: Lieferschein
- offer: Angebot/Kostenvoranschlag
- order: Bestellung/Auftrag
- credit_note: Gutschrift/Stornorechnung
- receipt: Quittung/Kassenbeleg
- letter: Brief/Schreiben
- report: Bericht
- reminder: Mahnung/Zahlungserinnerung
- bank_statement: Kontoauszug
- tax_document: Steuerdokument
- correspondence: Allgemeine Korrespondenz
- other: Sonstiges

WICHTIG:
- Antworte NUR im JSON-Format
- Alle Texte auf Deutsch
- Confidence als Zahl zwischen 0.0 und 1.0
- Bei Unsicherheit: mehrere Labels mit jeweiliger Confidence
"""

CLASSIFICATION_USER_PROMPT = """Analysiere folgendes Dokument und klassifiziere es.

Dokumententext:
---
{text}
---

Antworte im folgenden JSON-Format:
{{
    "primary_type": "invoice|contract|...",
    "primary_confidence": 0.0-1.0,
    "additional_types": [
        {{"type": "...", "confidence": 0.0-1.0}}
    ],
    "explanation": {{
        "summary": "Kurze Zusammenfassung auf Deutsch",
        "key_indicators": ["Gefundene Schluesselbegriffe"],
        "context_clues": ["Kontextuelle Hinweise"],
        "reasoning": "Detaillierte Begruendung"
    }}
}}
"""


# =============================================================================
# Service Implementation
# =============================================================================

class AutoCategorizationV2Service:
    """
    LLM-basierte Dokument-Kategorisierung 2.0.

    Features:
    - Ollama-basierte kontextuelle Analyse
    - Fallback auf Pattern-Matching bei LLM-Ausfall
    - Multi-Label-Klassifikation
    - Erklärungen für Entscheidungen
    - Lernen aus Korrekturen
    - Confidence-Kalibrierung
    """

    # Konfiguration
    MIN_TEXT_LENGTH_FOR_LLM = 50  # Mindestlänge für LLM-Analyse
    MAX_TEXT_LENGTH_FOR_LLM = 4000  # Maximum Text für LLM (Token-Limit)
    LLM_TIMEOUT_SECONDS = 30  # Timeout für LLM-Anfrage
    CACHE_TTL_SECONDS = 3600  # 1 Stunde Cache für gleiche Texte
    MIN_CORRECTIONS_FOR_LEARNING = 5  # Mindest-Korrekturen für Lernen
    CALIBRATION_WINDOW_DAYS = 30  # Zeitfenster für Kalibrierung

    # AppConfig Keys
    CORRECTIONS_KEY = "categorization_v2_corrections"
    CALIBRATION_KEY = "categorization_v2_calibration"
    CACHE_KEY_PREFIX = "categorization_v2_cache_"

    def __init__(
        self,
        ollama_service: Optional[OllamaService] = None,
        pattern_service: Optional[AutoCategorizationService] = None,
    ) -> None:
        """
        Initialisiert den V2 Kategorisierungs-Service.

        Args:
            ollama_service: Optionaler Ollama Service (Default: Singleton)
            pattern_service: Optionaler Pattern Service (Default: Singleton)
        """
        self._ollama = ollama_service
        self._pattern_service = pattern_service
        self._decision_service = get_ai_decision_service()
        self._cache: Dict[str, Tuple[CategorizationV2Result, datetime]] = {}
        self._calibration_data: Dict[DocumentType, CalibrationData] = {}

    @property
    def ollama(self) -> OllamaService:
        """Lazy-loaded Ollama Service."""
        if self._ollama is None:
            self._ollama = get_ollama_service()
        return self._ollama

    @property
    def pattern_service(self) -> AutoCategorizationService:
        """Lazy-loaded Pattern Service."""
        if self._pattern_service is None:
            self._pattern_service = get_auto_categorization_service()
        return self._pattern_service

    def _compute_text_hash(self, text: str) -> str:
        """Berechnet SHA-256 Hash für Text-Caching."""
        normalized = re.sub(r'\s+', ' ', text.lower().strip())
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:16]

    def _truncate_text(self, text: str, max_length: int = 4000) -> str:
        """Kürzt Text für LLM unter Beibehaltung der Struktur."""
        if len(text) <= max_length:
            return text

        # Versuche sinnvoll zu kürzen
        # Erste Haelfte (Header) + letzte Viertel (Footer/Summen)
        header_len = int(max_length * 0.6)
        footer_len = int(max_length * 0.35)

        header = text[:header_len]
        footer = text[-footer_len:]

        return f"{header}\n\n[...Text gekürzt...]\n\n{footer}"

    async def categorize_text(
        self,
        text: str,
        use_llm: bool = True,
        use_cache: bool = True,
        min_confidence: float = 0.3,
    ) -> CategorizationV2Result:
        """
        Kategorisiert einen Text mit LLM-Unterstützung.

        Args:
            text: OCR-Text des Dokuments
            use_llm: Ob LLM verwendet werden soll
            use_cache: Ob Cache verwendet werden soll
            min_confidence: Minimale Confidence für Ergebnis

        Returns:
            CategorizationV2Result mit Multi-Label und Erklärung
        """
        start_time = time.perf_counter()

        # Text-Hash für Cache
        text_hash = self._compute_text_hash(text)

        # Cache prüfen
        if use_cache and text_hash in self._cache:
            cached_result, cached_at = self._cache[text_hash]
            if (datetime.now(timezone.utc) - cached_at).seconds < self.CACHE_TTL_SECONDS:
                cached_result.method = CategorizationMethod.CACHED
                return cached_result

        # Pattern-basierte Analyse als Basis
        pattern_result = self.pattern_service.categorize_text(text, min_confidence)

        # Entscheide ob LLM verwendet wird
        should_use_llm = (
            use_llm
            and len(text) >= self.MIN_TEXT_LENGTH_FOR_LLM
            and pattern_result.confidence < 0.90  # LLM nur bei Unsicherheit
        )

        if should_use_llm:
            try:
                # LLM verfügbar prüfen
                llm_available = await self.ollama.is_available()
                if not llm_available:
                    LLM_FALLBACK_RATE.labels(reason="unavailable").inc()
                    should_use_llm = False
            except Exception as e:
                logger.warning(
                    "llm_availability_check_failed",
                    error=str(e),
                )
                LLM_FALLBACK_RATE.labels(reason="error").inc()
                should_use_llm = False

        if should_use_llm:
            result = await self._categorize_with_llm(
                text, pattern_result, start_time
            )
        else:
            # Fallback auf Pattern-Ergebnis
            result = self._convert_pattern_result(pattern_result, start_time)

        # Kalibrierung anwenden
        result = self._apply_calibration(result)

        # Cache aktualisieren
        if use_cache:
            self._cache[text_hash] = (result, datetime.now(timezone.utc))

        # Metriken
        CATEGORIZATION_V2_DURATION.observe(result.processing_time_ms / 1000)
        CATEGORIZATION_V2_REQUESTS.labels(
            category=result.primary_type.value,
            confidence_level=self._confidence_level(result.primary_confidence),
            method=result.method.value,
        ).inc()

        return result

    async def _categorize_with_llm(
        self,
        text: str,
        pattern_result: CategorizationResult,
        start_time: float,
    ) -> CategorizationV2Result:
        """Führt LLM-basierte Kategorisierung durch."""
        # Text für LLM vorbereiten
        truncated_text = self._truncate_text(text, self.MAX_TEXT_LENGTH_FOR_LLM)

        # LLM Prompt erstellen
        user_prompt = CLASSIFICATION_USER_PROMPT.format(text=truncated_text)

        try:
            # LLM aufrufen mit Timeout
            response = await asyncio.wait_for(
                self.ollama.generate(
                    prompt=user_prompt,
                    system_prompt=CLASSIFICATION_SYSTEM_PROMPT,
                    temperature=0.1,
                    format_json=True,
                ),
                timeout=self.LLM_TIMEOUT_SECONDS,
            )

            # JSON parsen
            llm_result = self._parse_llm_response(response)

            if llm_result:
                processing_time_ms = int((time.perf_counter() - start_time) * 1000)
                return self._build_result_from_llm(
                    llm_result, pattern_result, processing_time_ms
                )

        except asyncio.TimeoutError:
            logger.warning("llm_categorization_timeout")
            LLM_FALLBACK_RATE.labels(reason="timeout").inc()
        except json.JSONDecodeError as e:
            logger.warning("llm_response_parse_error", error=str(e))
            LLM_FALLBACK_RATE.labels(reason="parse_error").inc()
        except Exception as e:
            logger.warning("llm_categorization_error", error=str(e))
            LLM_FALLBACK_RATE.labels(reason="error").inc()

        # Fallback auf Pattern-Ergebnis
        return self._convert_pattern_result(pattern_result, start_time)

    def _parse_llm_response(self, response: str) -> Optional[Dict[str, Any]]:
        """Parst LLM-Antwort und extrahiert JSON."""
        if not response:
            return None

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # Versuche JSON aus Antwort zu extrahieren
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError as e:
                    # OPEN-46: ungültiges LLM-Kategorisierungs-JSON sichtbar machen (Fallback bleibt None)
                    logger.warning("llm_categorization_json_invalid", error_type=type(e).__name__)

        return None

    def _build_result_from_llm(
        self,
        llm_result: Dict[str, Any],
        pattern_result: CategorizationResult,
        processing_time_ms: int,
    ) -> CategorizationV2Result:
        """Baut Ergebnis aus LLM-Antwort."""
        # Primary Type extrahieren
        primary_type_str = llm_result.get("primary_type", "other")
        try:
            primary_type = DocumentType(primary_type_str)
        except ValueError:
            primary_type = DocumentType.OTHER

        primary_confidence = float(llm_result.get("primary_confidence", 0.7))
        primary_confidence = max(0.0, min(1.0, primary_confidence))

        # Labels erstellen
        labels = [
            CategoryLabel(
                document_type=primary_type,
                confidence=primary_confidence,
                is_primary=True,
            )
        ]

        # Additional Types
        for additional in llm_result.get("additional_types", []):
            try:
                add_type = DocumentType(additional.get("type", "other"))
                add_conf = float(additional.get("confidence", 0.3))
                if add_type != primary_type and add_conf >= 0.3:
                    labels.append(
                        CategoryLabel(
                            document_type=add_type,
                            confidence=max(0.0, min(1.0, add_conf)),
                            is_primary=False,
                        )
                    )
            except (ValueError, TypeError):
                continue

        # Explanation
        expl_data = llm_result.get("explanation", {})
        explanation = CategoryExplanation(
            summary=expl_data.get("summary", "LLM-basierte Klassifizierung"),
            key_indicators=expl_data.get("key_indicators", []),
            context_clues=expl_data.get("context_clues", []),
            reasoning=expl_data.get("reasoning", ""),
        )

        return CategorizationV2Result(
            primary_type=primary_type,
            primary_confidence=primary_confidence,
            labels=labels,
            explanation=explanation,
            method=CategorizationMethod.LLM,
            processing_time_ms=processing_time_ms,
            llm_model=getattr(settings, 'OLLAMA_MODEL', 'mistral'),
            pattern_result=pattern_result,
        )

    def _convert_pattern_result(
        self,
        pattern_result: CategorizationResult,
        start_time: float,
    ) -> CategorizationV2Result:
        """Konvertiert V1 Pattern-Ergebnis zu V2 Format."""
        processing_time_ms = int((time.perf_counter() - start_time) * 1000)

        # Kategorie mappen
        primary_type = CATEGORY_MAPPING.get(
            pattern_result.category, DocumentType.OTHER
        )

        # Labels erstellen
        labels = [
            CategoryLabel(
                document_type=primary_type,
                confidence=pattern_result.confidence,
                is_primary=True,
            )
        ]

        # Sekundaere Kategorien
        for cat, conf in pattern_result.secondary_categories[:3]:
            mapped_type = CATEGORY_MAPPING.get(cat, DocumentType.OTHER)
            if mapped_type != primary_type:
                labels.append(
                    CategoryLabel(
                        document_type=mapped_type,
                        confidence=conf,
                        is_primary=False,
                    )
                )

        # Explanation aus Pattern-Ergebnis
        explanation = CategoryExplanation(
            summary=f"Pattern-basierte Klassifizierung als {pattern_result.display_name}",
            key_indicators=pattern_result.matched_keywords[:10],
            context_clues=[],
            reasoning=self._build_pattern_reasoning(pattern_result),
        )

        return CategorizationV2Result(
            primary_type=primary_type,
            primary_confidence=pattern_result.confidence,
            labels=labels,
            explanation=explanation,
            method=CategorizationMethod.PATTERN,
            processing_time_ms=processing_time_ms,
            pattern_result=pattern_result,
        )

    def _build_pattern_reasoning(self, pattern_result: CategorizationResult) -> str:
        """Erstellt Begruendung aus Pattern-Ergebnis."""
        parts = []

        if pattern_result.matched_keywords:
            keywords = ", ".join(pattern_result.matched_keywords[:5])
            parts.append(f"Gefundene Schluesselbegriffe: {keywords}")

        if pattern_result.matched_patterns:
            parts.append(f"{len(pattern_result.matched_patterns)} Muster erkannt")

        if pattern_result.secondary_categories:
            alt = ", ".join(
                f"{cat} ({conf:.0%})"
                for cat, conf in pattern_result.secondary_categories[:2]
            )
            parts.append(f"Alternative Kategorien: {alt}")

        return ". ".join(parts) if parts else "Standardklassifizierung"

    def _confidence_level(self, confidence: float) -> str:
        """Mappt Confidence zu Level-String für Metriken."""
        if confidence >= 0.95:
            return "auto_apply"
        elif confidence >= 0.80:
            return "suggest"
        elif confidence >= 0.50:
            return "review"
        else:
            return "low"

    # =========================================================================
    # Kalibrierung und Lernen
    # =========================================================================

    def _apply_calibration(
        self,
        result: CategorizationV2Result,
    ) -> CategorizationV2Result:
        """Wendet Kalibrierung auf Confidence an."""
        if result.primary_type not in self._calibration_data:
            result.calibrated_confidence = result.primary_confidence
            return result

        cal = self._calibration_data[result.primary_type]
        adjusted = result.primary_confidence + cal.confidence_adjustment
        result.calibrated_confidence = max(0.0, min(1.0, adjusted))

        return result

    async def load_calibration_data(self, db: AsyncSession) -> None:
        """Laedt Kalibrierungsdaten aus der Datenbank."""
        try:
            result = await db.execute(
                select(AppConfig).where(AppConfig.key == self.CALIBRATION_KEY)
            )
            config = result.scalar_one_or_none()

            if config and config.value:
                data = config.value
                for type_str, cal_data in data.items():
                    try:
                        doc_type = DocumentType(type_str)
                        self._calibration_data[doc_type] = CalibrationData(
                            document_type=doc_type,
                            total_predictions=cal_data.get("total", 0),
                            correct_predictions=cal_data.get("correct", 0),
                            accuracy=cal_data.get("accuracy", 1.0),
                            confidence_adjustment=cal_data.get("adjustment", 0.0),
                            last_updated=datetime.fromisoformat(
                                cal_data.get("updated", datetime.now(timezone.utc).isoformat())
                            ),
                        )
                    except (ValueError, KeyError):
                        continue

                logger.info(
                    "calibration_data_loaded",
                    categories_count=len(self._calibration_data),
                )
        except Exception as e:
            logger.warning("calibration_data_load_error", error=str(e))

    async def record_correction(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        original_type: DocumentType,
        corrected_type: DocumentType,
        text: str,
        corrected_by_id: Optional[uuid.UUID] = None,
    ) -> None:
        """
        Zeichnet eine User-Korrektur für Lernen auf.

        Args:
            db: Database Session
            document_id: Dokument-ID
            original_type: Urspruengliche Kategorie
            corrected_type: Korrigierte Kategorie
            text: Dokument-Text
            corrected_by_id: User-ID des Korrigierenden
        """
        if original_type == corrected_type:
            return  # Keine Korrektur

        correction = CorrectionEntry(
            document_id=document_id,
            original_type=original_type,
            corrected_type=corrected_type,
            text_hash=self._compute_text_hash(text),
            text_snippet=text[:500] if len(text) > 500 else text,
            keywords_found=self._extract_keywords(text),
            corrected_at=datetime.now(timezone.utc),
            corrected_by_id=corrected_by_id,
        )

        # In AppConfig speichern
        try:
            result = await db.execute(
                select(AppConfig).where(AppConfig.key == self.CORRECTIONS_KEY)
            )
            config = result.scalar_one_or_none()

            corrections_list = []
            if config and config.value:
                corrections_list = config.value.get("corrections", [])

            # Neue Korrektur hinzufuegen
            corrections_list.append({
                "document_id": str(correction.document_id),
                "original_type": correction.original_type.value,
                "corrected_type": correction.corrected_type.value,
                "text_hash": correction.text_hash,
                "text_snippet": correction.text_snippet,
                "keywords_found": correction.keywords_found[:20],
                "corrected_at": correction.corrected_at.isoformat(),
                "corrected_by_id": str(correction.corrected_by_id) if correction.corrected_by_id else None,
            })

            # Auf letzte 1000 begrenzen
            corrections_list = corrections_list[-1000:]

            if config:
                config.value = {"corrections": corrections_list}
            else:
                config = AppConfig(
                    key=self.CORRECTIONS_KEY,
                    value={"corrections": corrections_list},
                )
                db.add(config)

            await db.commit()

            # Metriken
            CORRECTION_LEARNING_EVENTS.labels(
                original_category=original_type.value,
                corrected_category=corrected_type.value,
            ).inc()

            logger.info(
                "correction_recorded",
                document_id=str(document_id),
                original_type=original_type.value,
                corrected_type=corrected_type.value,
            )

        except Exception as e:
            logger.error("correction_recording_error", error=str(e))

    def _extract_keywords(self, text: str) -> List[str]:
        """Extrahiert relevante Keywords aus Text."""
        keywords = set()
        normalized = text.lower()

        for pattern in CATEGORY_PATTERNS:
            for keyword in pattern.keywords:
                if keyword.lower() in normalized:
                    keywords.add(keyword)

        return list(keywords)[:50]

    async def update_calibration(
        self,
        db: AsyncSession,
        company_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """
        Aktualisiert Kalibrierungsdaten basierend auf Korrekturen.

        Args:
            db: Database Session
            company_id: Optional Company-Filter

        Returns:
            Dict mit Kalibrierungs-Statistiken
        """
        # Korrekturen laden
        result = await db.execute(
            select(AppConfig).where(AppConfig.key == self.CORRECTIONS_KEY)
        )
        config = result.scalar_one_or_none()

        if not config or not config.value:
            return {"status": "no_corrections", "updated_categories": 0}

        corrections = config.value.get("corrections", [])

        # Nach Kategorie gruppieren
        by_original: Dict[str, List[Dict]] = {}
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.CALIBRATION_WINDOW_DAYS)

        for corr in corrections:
            corrected_at = datetime.fromisoformat(corr.get("corrected_at", ""))
            if corrected_at < cutoff:
                continue

            original = corr.get("original_type", "other")
            if original not in by_original:
                by_original[original] = []
            by_original[original].append(corr)

        # Kalibrierung berechnen
        calibration_updates = {}

        for type_str, type_corrections in by_original.items():
            if len(type_corrections) < self.MIN_CORRECTIONS_FOR_LEARNING:
                continue

            try:
                doc_type = DocumentType(type_str)
            except ValueError:
                continue

            # Berechne wie oft die Vorhersage korrekt war
            total = len(type_corrections)
            # Alle in dieser Liste sind Korrekturen, also Fehler
            # Wir brauchen auch die korrekten Vorhersagen aus AIDecision

            # Vereinfachte Heuristik: Wenn viele Korrekturen,
            # reduziere Confidence für diese Kategorie
            correction_rate = total / max(total + 10, 1)  # Annahme: 10 korrekte
            adjustment = -correction_rate * 0.1  # Max -10% Anpassung

            calibration_updates[type_str] = {
                "total": total,
                "correct": 0,  # Müsste aus AIDecision geladen werden
                "accuracy": 1.0 - correction_rate,
                "adjustment": round(adjustment, 3),
                "updated": datetime.now(timezone.utc).isoformat(),
            }

            self._calibration_data[doc_type] = CalibrationData(
                document_type=doc_type,
                total_predictions=total,
                correct_predictions=0,
                accuracy=1.0 - correction_rate,
                confidence_adjustment=adjustment,
                last_updated=datetime.now(timezone.utc),
            )

            # Prometheus Gauge
            CALIBRATION_ACCURACY.labels(category=type_str).set(1.0 - correction_rate)

        # In DB speichern
        if calibration_updates:
            try:
                cal_result = await db.execute(
                    select(AppConfig).where(AppConfig.key == self.CALIBRATION_KEY)
                )
                cal_config = cal_result.scalar_one_or_none()

                if cal_config:
                    cal_config.value = calibration_updates
                else:
                    cal_config = AppConfig(
                        key=self.CALIBRATION_KEY,
                        value=calibration_updates,
                    )
                    db.add(cal_config)

                await db.commit()
            except Exception as e:
                logger.error("calibration_save_error", error=str(e))

        logger.info(
            "calibration_updated",
            updated_categories=len(calibration_updates),
            total_corrections=sum(
                c.get("total", 0) for c in calibration_updates.values()
            ),
        )

        return {
            "status": "updated",
            "updated_categories": len(calibration_updates),
            "calibration_data": calibration_updates,
        }

    # =========================================================================
    # Document Integration
    # =========================================================================

    async def categorize_document(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        text: str,
        company_id: Optional[uuid.UUID] = None,
        auto_apply: bool = True,
        use_llm: bool = True,
    ) -> AIDecisionResult:
        """
        Kategorisiert ein Dokument mit AI-Autonomie.

        Args:
            db: Database Session
            document_id: Dokument-ID
            text: OCR-Text
            company_id: Optional Company-ID
            auto_apply: Ob Kategorie automatisch gesetzt werden soll
            use_llm: Ob LLM verwendet werden soll

        Returns:
            AIDecisionResult
        """
        # Kalibrierung laden falls nicht vorhanden
        if not self._calibration_data:
            await self.load_calibration_data(db)

        # Kategorisierung durchführen
        result = await self.categorize_text(text, use_llm=use_llm)

        # Decision Value erstellen
        decision_value = {
            "primary_type": result.primary_type.value,
            "primary_type_label": DOCUMENT_TYPE_LABELS_DE.get(
                result.primary_type, result.primary_type.value
            ),
            "labels": [
                {
                    "type": label.document_type.value,
                    "label": DOCUMENT_TYPE_LABELS_DE.get(
                        label.document_type, label.document_type.value
                    ),
                    "confidence": round(label.confidence, 3),
                    "is_primary": label.is_primary,
                }
                for label in result.labels
            ],
            "method": result.method.value,
            "llm_model": result.llm_model,
        }

        # Explanation
        explanation = {
            "summary": result.explanation.summary,
            "key_indicators": result.explanation.key_indicators[:10],
            "context_clues": result.explanation.context_clues[:5],
            "reasoning": result.explanation.reasoning[:500],
        }

        # Callback für Auto-Apply
        async def apply_category(value: Dict[str, Any]) -> None:
            """Wendet Kategorie auf Dokument an."""
            if not auto_apply:
                return

            doc_result = await db.execute(
                select(Document).where(Document.id == document_id)
            )
            doc = doc_result.scalar_one_or_none()
            if doc:
                doc.document_category = value["primary_type"]
                await db.commit()
                logger.info(
                    "category_v2_auto_applied",
                    document_id=str(document_id),
                    category=value["primary_type"],
                    method=value["method"],
                )

        # Confidence für Entscheidung
        confidence = (
            result.calibrated_confidence
            if result.calibrated_confidence is not None
            else result.primary_confidence
        )

        # AI Decision erstellen
        ai_result = await self._decision_service.make_decision(
            db=db,
            decision_type=DecisionType.CATEGORIZATION,
            decision_value=decision_value,
            confidence=confidence,
            document_id=document_id,
            company_id=company_id,
            explanation=explanation,
            features_used={
                "text_length": len(text),
                "method": result.method.value,
                "processing_time_ms": result.processing_time_ms,
                "labels_count": len(result.labels),
                "llm_used": result.method == CategorizationMethod.LLM,
            },
            apply_callback=apply_category if auto_apply else None,
        )

        return ai_result

    async def get_category_suggestions(
        self,
        text: str,
        limit: int = 5,
        use_llm: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Gibt Kategorie-Vorschläge zurück.

        Args:
            text: OCR-Text
            limit: Max Anzahl Vorschläge
            use_llm: Ob LLM verwendet werden soll

        Returns:
            Liste von Vorschlägen mit Kategorie und Konfidenz
        """
        result = await self.categorize_text(text, use_llm=use_llm)

        suggestions = []
        for label in result.labels[:limit]:
            suggestions.append({
                "type": label.document_type.value,
                "label": DOCUMENT_TYPE_LABELS_DE.get(
                    label.document_type, label.document_type.value
                ),
                "confidence": round(label.confidence, 3),
                "is_primary": label.is_primary,
            })

        # Erklärung hinzufuegen
        if suggestions:
            suggestions[0]["explanation"] = result.explanation.summary

        return suggestions

    def clear_cache(self) -> int:
        """Leert den Kategorisierungs-Cache."""
        count = len(self._cache)
        self._cache.clear()
        return count


# =============================================================================
# Singleton
# =============================================================================

_auto_categorization_v2_service: Optional[AutoCategorizationV2Service] = None
_service_lock = threading.Lock()


def get_auto_categorization_v2_service() -> AutoCategorizationV2Service:
    """Factory für AutoCategorizationV2Service Singleton (Thread-safe)."""
    global _auto_categorization_v2_service
    if _auto_categorization_v2_service is None:
        with _service_lock:
            if _auto_categorization_v2_service is None:
                _auto_categorization_v2_service = AutoCategorizationV2Service()
    return _auto_categorization_v2_service


def reset_auto_categorization_v2_service() -> None:
    """Reset für Tests."""
    global _auto_categorization_v2_service
    _auto_categorization_v2_service = None
