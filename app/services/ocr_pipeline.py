"""
OCR Pipeline Service für Ablage-System.

Integriert alle OCR-Komponenten zu einer einheitlichen Pipeline:
- Fallback Chain für Backend-Auswahl
- Confidence-basierte Qualitätsprüfung
- Circuit Breaker für Fehlertoleranz
- GPU Memory Guard für Ressourcenkontrolle
- German Correction Agent für Textkorrektur

Feinpoliert und durchdacht - Enterprise-grade OCR Pipeline.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional
from pathlib import Path
import structlog
import torch

from app.services.confidence_service import (
    ConfidenceService,
    ConfidenceMetrics,
    get_confidence_service
)
from app.services.fallback_chain import (
    FallbackChain,
    FallbackResult,
    get_fallback_chain
)
from app.services.circuit_breaker import (
    CircuitBreakerRegistry,
    CircuitBreakerError,
    get_circuit_breaker_registry
)
from app.gpu_manager import (
    GPUManager,
    GPUMemoryGuard,
    get_memory_guard,
    gpu_memory_guard
)
from app.services.historical_german_normalizer import (
    HistoricalGermanNormalizer,
    NormalizationResult,
    get_historical_normalizer,
    normalize_historical
)
from app.core.config import settings
from app.core.safe_errors import safe_error_log

# Lazy import for entity extraction to avoid circular imports
EntityExtractionService = None
EntityExtractionResult = None

logger = structlog.get_logger(__name__)


@dataclass
class ConfidenceThresholds:
    """Confidence-Schwellenwerte für Qualitätskontrolle."""
    low: float = 0.70       # Unter diesem Wert: Fallback zu anderem Backend
    medium: float = 0.85    # Unter diesem Wert: needs_review Flag setzen
    high: float = 0.95      # Über diesem Wert: Hohe Qualität, direkt akzeptieren


@dataclass
class OCRPipelineResult:
    """Vollständiges Ergebnis der OCR Pipeline."""
    success: bool
    text: str
    corrected_text: str
    confidence: float
    backend_used: str
    backends_tried: List[str]
    fallbacks_occurred: int
    corrections_applied: int
    processing_time_ms: int
    german_correction_applied: bool
    historical_normalization_applied: bool = False
    historical_changes_count: int = 0
    confidence_details: Optional[Dict[str, Any]] = None
    correction_details: Optional[Dict[str, Any]] = None
    historical_normalization_details: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    needs_review: bool = False  # True wenn Confidence zwischen low und medium
    confidence_fallback_triggered: bool = False  # True wenn Fallback wegen niedriger Confidence
    # Entity Extraction (Document Intelligence)
    entity_extraction_applied: bool = False
    extracted_entities: Optional[Dict[str, Any]] = None
    # Structured Extraction (Invoice, Order, Contract data)
    structured_extraction_applied: bool = False
    structured_data: Optional[Dict[str, Any]] = None
    document_type: Optional[str] = None  # Klassifizierter Dokumenttyp

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "text": self.corrected_text,  # Korrigierter Text als Hauptergebnis
            "original_text": self.text,
            "confidence": round(self.confidence, 4),
            "backend_used": self.backend_used,
            "backends_tried": self.backends_tried,
            "fallbacks_occurred": self.fallbacks_occurred,
            "corrections_applied": self.corrections_applied,
            "processing_time_ms": self.processing_time_ms,
            "german_correction_applied": self.german_correction_applied,
            "historical_normalization_applied": self.historical_normalization_applied,
            "historical_changes_count": self.historical_changes_count,
            "confidence_details": self.confidence_details,
            "correction_details": self.correction_details,
            "historical_normalization_details": self.historical_normalization_details,
            "error": self.error,
            "needs_review": self.needs_review,
            "confidence_fallback_triggered": self.confidence_fallback_triggered,
            "entity_extraction_applied": self.entity_extraction_applied,
            "extracted_entities": self.extracted_entities,
            "structured_extraction_applied": self.structured_extraction_applied,
            "structured_data": self.structured_data,
            "document_type": self.document_type,
        }


class OCRPipeline:
    """
    Zentrale OCR Pipeline mit allen Integrationen.

    Verarbeitet Dokumente durch:
    1. GPU Memory Check
    2. Backend-Auswahl via Fallback Chain
    3. OCR-Verarbeitung mit Circuit Breaker
    4. Confidence-Analyse
    5. German Correction Agent
    6. Qualitätsvalidierung
    """

    def __init__(
        self,
        enable_german_correction: bool = True,
        enable_circuit_breaker: bool = True,
        enable_memory_guard: bool = True,
        enable_historical_normalization: bool = True,
        enable_entity_extraction: bool = True,
        enable_structured_extraction: bool = True,
        min_confidence_threshold: float = 0.65,
        confidence_thresholds: Optional[ConfidenceThresholds] = None,
        enable_confidence_fallback: bool = True
    ):
        """
        Initialisiere OCR Pipeline.

        Args:
            enable_german_correction: German Correction Agent aktivieren
            enable_circuit_breaker: Circuit Breaker aktivieren
            enable_memory_guard: GPU Memory Guard aktivieren
            enable_historical_normalization: Historical German Normalizer aktivieren
            enable_entity_extraction: Entity Extraction (Business Partner) aktivieren
            enable_structured_extraction: Strukturierte Extraktion (Invoice, Order, Contract) aktivieren
            min_confidence_threshold: Minimale Confidence für Akzeptanz (legacy)
            confidence_thresholds: Konfigurierbare Schwellenwerte für Confidence
            enable_confidence_fallback: Fallback bei niedriger Confidence aktivieren
        """
        self.enable_german_correction = enable_german_correction
        self.enable_circuit_breaker = enable_circuit_breaker
        self.enable_memory_guard = enable_memory_guard
        self.enable_historical_normalization = (
            enable_historical_normalization and
            settings.HISTORICAL_NORMALIZATION_ENABLED
        )
        self.enable_entity_extraction = enable_entity_extraction
        self.enable_structured_extraction = enable_structured_extraction
        self.min_confidence_threshold = min_confidence_threshold
        self.confidence_thresholds = confidence_thresholds or ConfidenceThresholds()
        self.enable_confidence_fallback = enable_confidence_fallback

        # Services initialisieren
        self.confidence_service = get_confidence_service()
        self.fallback_chain = get_fallback_chain()
        self.circuit_registry = get_circuit_breaker_registry()
        self.memory_guard = get_memory_guard() if enable_memory_guard else None
        self.gpu_manager = GPUManager()

        # German Correction Agent (lazy load)
        self._german_agent = None

        # Historical German Normalizer (lazy load)
        self._historical_normalizer: Optional[HistoricalGermanNormalizer] = None

        # Entity Extraction Service (lazy load)
        self._entity_extraction_service = None

        # Structured Extraction Service (lazy load)
        self._structured_extraction_service = None

        # Backend Handlers registrieren
        self._register_default_backends()

        logger.info(
            "ocr_pipeline_initialized",
            german_correction=enable_german_correction,
            circuit_breaker=enable_circuit_breaker,
            memory_guard=enable_memory_guard,
            historical_normalization=self.enable_historical_normalization,
            entity_extraction=enable_entity_extraction,
            structured_extraction=enable_structured_extraction,
            min_confidence=min_confidence_threshold,
            confidence_thresholds={
                "low": self.confidence_thresholds.low,
                "medium": self.confidence_thresholds.medium,
                "high": self.confidence_thresholds.high,
            },
            confidence_fallback=enable_confidence_fallback
        )

    def _register_default_backends(self) -> None:
        """Registriere Standard OCR Backends."""
        # Diese werden bei Bedarf dynamisch geladen
        pass

    def register_backend_handler(
        self,
        backend_name: str,
        handler: Callable
    ) -> None:
        """
        Registriere einen Backend Handler.

        Args:
            backend_name: Name des Backends
            handler: Async Handler Funktion
        """
        self.fallback_chain.register_backend_handler(backend_name, handler)

        # Circuit Breaker für Backend erstellen
        if self.enable_circuit_breaker:
            self.circuit_registry.get_or_create(backend_name)

        logger.debug("backend_registered", backend=backend_name)

    def _get_german_agent(self):
        """Lazy-load German Correction Agent."""
        if self._german_agent is None and self.enable_german_correction:
            try:
                from app.agents.postprocessing.german_correction_agent import GermanCorrectionAgent
                self._german_agent = GermanCorrectionAgent()
                logger.info("german_correction_agent_loaded")
            except ImportError as e:
                logger.warning(
                    "german_correction_agent_unavailable",
                    **safe_error_log(e)
                )
                self.enable_german_correction = False
        return self._german_agent

    def _get_historical_normalizer(self) -> Optional[HistoricalGermanNormalizer]:
        """Lazy-load Historical German Normalizer."""
        if self._historical_normalizer is None and self.enable_historical_normalization:
            try:
                self._historical_normalizer = HistoricalGermanNormalizer(
                    enable_pre_1996=settings.HISTORICAL_NORM_PRE_1996,
                    enable_th_normalization=settings.HISTORICAL_NORM_TH,
                    enable_c_normalization=settings.HISTORICAL_NORM_C,
                    enable_ph_normalization=settings.HISTORICAL_NORM_PH,
                    enable_fraktur=settings.HISTORICAL_NORM_FRAKTUR,
                )
                logger.info(
                    "historical_normalizer_loaded",
                    pre_1996=settings.HISTORICAL_NORM_PRE_1996,
                    th=settings.HISTORICAL_NORM_TH,
                    c=settings.HISTORICAL_NORM_C,
                    ph=settings.HISTORICAL_NORM_PH,
                    fraktur=settings.HISTORICAL_NORM_FRAKTUR,
                )
            except Exception as e:
                logger.warning(
                    "historical_normalizer_unavailable",
                    **safe_error_log(e)
                )
                self.enable_historical_normalization = False
        return self._historical_normalizer

    def _get_entity_extraction_service(self):
        """Lazy-load Entity Extraction Service."""
        global EntityExtractionService, EntityExtractionResult
        if self._entity_extraction_service is None and self.enable_entity_extraction:
            try:
                # Import on first use to avoid circular imports
                from app.services.entity_extraction_service import (
                    EntityExtractionService as EES,
                    EntityExtractionResult as EER
                )
                EntityExtractionService = EES
                EntityExtractionResult = EER

                # Create service without DB (just extraction, no matching)
                self._entity_extraction_service = EntityExtractionService(db=None)
                logger.info("entity_extraction_service_loaded")
            except ImportError as e:
                logger.warning(
                    "entity_extraction_service_unavailable",
                    **safe_error_log(e)
                )
                self.enable_entity_extraction = False
            except Exception as e:
                logger.warning(
                    "entity_extraction_service_init_error",
                    **safe_error_log(e)
                )
                self.enable_entity_extraction = False
        return self._entity_extraction_service

    def _get_structured_extraction_service(self):
        """Lazy-load Structured Extraction Service."""
        if self._structured_extraction_service is None and self.enable_structured_extraction:
            try:
                from app.services.structured_extraction_service import (

                    StructuredExtractionService,
                    get_structured_extraction_service,
                )
                self._structured_extraction_service = get_structured_extraction_service()
                logger.info("structured_extraction_service_loaded")
            except ImportError as e:
                logger.warning(
                    "structured_extraction_service_unavailable",
                    **safe_error_log(e)
                )
                self.enable_structured_extraction = False
            except Exception as e:
                logger.warning(
                    "structured_extraction_service_init_error",
                    **safe_error_log(e)
                )
                self.enable_structured_extraction = False
        return self._structured_extraction_service

    async def process(
        self,
        document_id: str,
        image_path: str,
        language: str = "de",
        options: Optional[Dict[str, Any]] = None,
        preferred_backend: Optional[str] = None,
        document_type: Optional[str] = None,
        skip_german_correction: bool = False
    ) -> OCRPipelineResult:
        """
        Verarbeite ein Dokument durch die vollständige Pipeline.

        Args:
            document_id: Dokument-ID
            image_path: Pfad zum Bild
            language: Sprache (default: "de")
            options: Zusätzliche Optionen
            preferred_backend: Bevorzugtes Backend
            document_type: Dokumenttyp für optimierte Verarbeitung
            skip_german_correction: German Correction überspringen

        Returns:
            OCRPipelineResult mit vollständigem Ergebnis
        """
        start_time = time.perf_counter()
        options = options or {}

        logger.info(
            "ocr_pipeline_started",
            document_id=document_id,
            language=language,
            preferred_backend=preferred_backend,
            document_type=document_type
        )

        # Step 1: GPU Memory Check
        gpu_available = True
        available_vram_gb = 16.0

        if self.enable_memory_guard and self.memory_guard:
            memory_status = self.memory_guard.check_memory_status()
            gpu_available = memory_status.get("available", False)
            if gpu_available:
                available_vram_gb = memory_status.get("remaining_gb", 0)

            if memory_status.get("is_critical"):
                logger.warning(
                    "ocr_pipeline_memory_critical",
                    document_id=document_id,
                    usage_percent=memory_status.get("usage_percent")
                )
                # Versuche Cleanup
                self.memory_guard.cleanup_cache()

        # Step 2: OCR via Fallback Chain
        try:
            fallback_result = await self.fallback_chain.execute(
                document_id=document_id,
                image_path=image_path,
                language=language,
                options=options,
                preferred_backend=preferred_backend,
                document_type=document_type,
                gpu_available=gpu_available,
                available_vram_gb=available_vram_gb
            )
        except torch.cuda.OutOfMemoryError as e:
            # GPU OOM - don't retry, need manual intervention
            logger.error(
                "ocr_pipeline_gpu_oom",
                document_id=document_id,
                **safe_error_log(e),
                recoverable=False
            )
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            return OCRPipelineResult(
                success=False,
                text="",
                corrected_text="",
                confidence=0.0,
                backend_used="none",
                backends_tried=[],
                fallbacks_occurred=0,
                corrections_applied=0,
                processing_time_ms=int((time.perf_counter() - start_time) * 1000),
                german_correction_applied=False,
                error=f"GPU out of memory: {e}"
            )
        except asyncio.TimeoutError as e:
            # Timeout - could retry with extended timeout
            logger.warning(
                "ocr_pipeline_timeout",
                document_id=document_id,
                **safe_error_log(e),
                recoverable=True
            )
            return OCRPipelineResult(
                success=False,
                text="",
                corrected_text="",
                confidence=0.0,
                backend_used="none",
                backends_tried=[],
                fallbacks_occurred=0,
                corrections_applied=0,
                processing_time_ms=int((time.perf_counter() - start_time) * 1000),
                german_correction_applied=False,
                error=f"Processing timeout: {e}"
            )
        except (ValueError, IOError, RuntimeError) as e:
            # Known error types - log and return
            logger.error(
                "ocr_pipeline_processing_error",
                document_id=document_id,
                error_type=type(e).__name__,
                **safe_error_log(e)
            )
            return OCRPipelineResult(
                success=False,
                text="",
                corrected_text="",
                confidence=0.0,
                backend_used="none",
                backends_tried=[],
                fallbacks_occurred=0,
                corrections_applied=0,
                processing_time_ms=int((time.perf_counter() - start_time) * 1000),
                german_correction_applied=False,
                **safe_error_log(e)
            )
        except Exception as e:
            # Unexpected error - log with full context
            logger.error(
                "ocr_pipeline_unexpected_error",
                document_id=document_id,
                error_type=type(e).__name__,
                **safe_error_log(e),
                exc_info=True
            )
            return OCRPipelineResult(
                success=False,
                text="",
                corrected_text="",
                confidence=0.0,
                backend_used="none",
                backends_tried=[],
                fallbacks_occurred=0,
                corrections_applied=0,
                processing_time_ms=int((time.perf_counter() - start_time) * 1000),
                german_correction_applied=False,
                **safe_error_log(e)
            )

        if not fallback_result.success:
            return OCRPipelineResult(
                success=False,
                text=fallback_result.text,
                corrected_text=fallback_result.text,
                confidence=fallback_result.confidence,
                backend_used=fallback_result.final_backend,
                backends_tried=fallback_result.backends_tried,
                fallbacks_occurred=fallback_result.fallbacks_occurred,
                corrections_applied=0,
                processing_time_ms=int((time.perf_counter() - start_time) * 1000),
                german_correction_applied=False,
                error=fallback_result.error
            )

        # Step 2.5: Confidence Thresholding
        needs_review = False
        confidence_fallback_triggered = False
        current_confidence = fallback_result.confidence

        if current_confidence < self.confidence_thresholds.low:
            # Niedrige Confidence: Versuche Fallback zu anderem Backend
            logger.warning(
                "ocr_pipeline_low_confidence",
                document_id=document_id,
                confidence=current_confidence,
                threshold=self.confidence_thresholds.low,
                backend=fallback_result.final_backend
            )

            if self.enable_confidence_fallback:
                # Versuche ein anderes Backend (wenn noch nicht alle probiert)
                available_for_retry = [
                    b for b in ["deepseek", "got_ocr", "surya", "surya_gpu"]
                    if b not in fallback_result.backends_tried
                ]

                if available_for_retry:
                    retry_backend = available_for_retry[0]
                    logger.info(
                        "ocr_pipeline_confidence_fallback",
                        document_id=document_id,
                        retry_backend=retry_backend,
                        original_confidence=current_confidence
                    )

                    try:
                        retry_result = await self.fallback_chain.execute(
                            document_id=document_id,
                            image_path=image_path,
                            language=language,
                            options=options,
                            preferred_backend=retry_backend,
                            document_type=document_type,
                            gpu_available=gpu_available,
                            available_vram_gb=available_vram_gb
                        )

                        if retry_result.success and retry_result.confidence > current_confidence:
                            # Besseres Ergebnis gefunden
                            logger.info(
                                "ocr_pipeline_confidence_fallback_success",
                                document_id=document_id,
                                old_confidence=current_confidence,
                                new_confidence=retry_result.confidence,
                                new_backend=retry_result.final_backend
                            )
                            fallback_result = retry_result
                            current_confidence = retry_result.confidence
                            confidence_fallback_triggered = True
                        else:
                            logger.debug(
                                "ocr_pipeline_confidence_fallback_no_improvement",
                                document_id=document_id,
                                retry_confidence=retry_result.confidence if retry_result.success else 0.0
                            )
                    except Exception as e:
                        logger.warning(
                            "ocr_pipeline_confidence_fallback_error",
                            document_id=document_id,
                            **safe_error_log(e)
                        )

            # Setze needs_review wenn Confidence immer noch niedrig
            if current_confidence < self.confidence_thresholds.medium:
                needs_review = True

        elif current_confidence < self.confidence_thresholds.medium:
            # Mittlere Confidence: Akzeptieren aber markieren
            needs_review = True
            logger.info(
                "ocr_pipeline_medium_confidence_review_needed",
                document_id=document_id,
                confidence=current_confidence,
                threshold=self.confidence_thresholds.medium,
                backend=fallback_result.final_backend
            )
        else:
            # Hohe Confidence: Direkt akzeptieren
            logger.debug(
                "ocr_pipeline_high_confidence",
                document_id=document_id,
                confidence=current_confidence,
                backend=fallback_result.final_backend
            )

        # Step 3: German Correction (wenn aktiviert und Sprache = de)
        corrected_text = fallback_result.text
        corrections_applied = 0
        correction_details = None
        german_correction_applied = False

        if (self.enable_german_correction and
            language == "de" and
            not skip_german_correction and
            fallback_result.text):

            german_agent = self._get_german_agent()
            if german_agent:
                try:
                    correction_result = await german_agent.process({
                        "text": fallback_result.text,
                        "domain": document_type,
                        "options": options.get("german_correction_options", {})
                    })

                    corrected_text = correction_result.get("text", fallback_result.text)
                    corrections_applied = correction_result.get("corrections_applied", 0)
                    correction_details = {
                        "corrections_applied": corrections_applied,
                        "umlauts_restored": correction_result.get("umlauts_restored", 0),
                        "validation_score": correction_result.get("validation_score", 0),
                        "domain_detected": correction_result.get("domain_detected"),
                    }
                    german_correction_applied = True

                    logger.info(
                        "ocr_pipeline_german_correction_applied",
                        document_id=document_id,
                        corrections=corrections_applied,
                        umlauts_restored=correction_result.get("umlauts_restored", 0)
                    )

                except Exception as e:
                    logger.warning(
                        "ocr_pipeline_german_correction_error",
                        document_id=document_id,
                        **safe_error_log(e)
                    )
                    # Verwende unkorrigierten Text bei Fehler

        # Step 4: Historical German Normalization (nach German Correction)
        historical_normalization_applied = False
        historical_changes_count = 0
        historical_normalization_details = None

        if (self.enable_historical_normalization and
            language == "de" and
            corrected_text):

            historical_normalizer = self._get_historical_normalizer()
            if historical_normalizer:
                try:
                    norm_result: NormalizationResult = historical_normalizer.normalize(
                        corrected_text
                    )

                    if norm_result.was_changed:
                        corrected_text = norm_result.normalized
                        historical_changes_count = norm_result.change_count
                        historical_normalization_applied = True

                        historical_normalization_details = {
                            "changes_count": norm_result.change_count,
                            "era_detected": norm_result.era_detected.value if norm_result.era_detected else None,
                            "confidence": norm_result.confidence,
                            "sample_changes": norm_result.changes[:5],  # Erste 5 Änderungen
                        }

                        logger.info(
                            "ocr_pipeline_historical_normalization_applied",
                            document_id=document_id,
                            changes_count=historical_changes_count,
                            era_detected=norm_result.era_detected.value if norm_result.era_detected else None,
                        )

                except Exception as e:
                    logger.warning(
                        "ocr_pipeline_historical_normalization_error",
                        document_id=document_id,
                        **safe_error_log(e)
                    )
                    # Verwende Text ohne Historical Normalization bei Fehler

        # Step 5: Entity Extraction (Geschaeftspartner-Erkennung)
        entity_extraction_applied = False
        extracted_entities = None

        if (self.enable_entity_extraction and
            language == "de" and
            corrected_text):

            entity_service = self._get_entity_extraction_service()
            if entity_service:
                try:
                    extraction_result = await entity_service.extract_entities(corrected_text)

                    if extraction_result and extraction_result.overall_confidence > 0:
                        entity_extraction_applied = True
                        extracted_entities = {
                            "identifiers": [
                                {
                                    "type": ident.identifier_type,
                                    "value": ident.value,
                                    "normalized": ident.normalized_value,
                                    "confidence": ident.confidence,
                                }
                                for ident in extraction_result.identifiers
                            ],
                            "addresses": [
                                {
                                    "street": addr.street,
                                    "postal_code": addr.postal_code,
                                    "city": addr.city,
                                    "confidence": addr.confidence,
                                }
                                for addr in extraction_result.addresses
                            ],
                            "company_names": [
                                {
                                    "name": company.name,
                                    "legal_form": company.legal_form,
                                    "confidence": company.confidence,
                                }
                                for company in extraction_result.company_names
                            ],
                            "emails": extraction_result.emails,
                            "overall_confidence": extraction_result.overall_confidence,
                        }

                        logger.info(
                            "ocr_pipeline_entity_extraction_applied",
                            document_id=document_id,
                            identifiers_found=len(extraction_result.identifiers),
                            addresses_found=len(extraction_result.addresses),
                            companies_found=len(extraction_result.company_names),
                            overall_confidence=extraction_result.overall_confidence,
                        )

                except Exception as e:
                    logger.warning(
                        "ocr_pipeline_entity_extraction_error",
                        document_id=document_id,
                        **safe_error_log(e)
                    )
                    # Fortfahren ohne Entity Extraction bei Fehler

        # Step 6: Structured Extraction (Rechnungen, Bestellungen, Vertraege)
        # NEU: Unterstuetzt jetzt ALLE Sprachen durch automatische Uebersetzung nach Deutsch
        structured_extraction_applied = False
        structured_data = None
        classified_document_type = None

        if (self.enable_structured_extraction and
            corrected_text):  # Sprachfilter entfernt - Uebersetzung erfolgt im Service

            structured_service = self._get_structured_extraction_service()
            if structured_service:
                try:
                    # Tabellen aus OCR-Ergebnis (Docling/Surya) fuer Line-Item-Extraktion
                    ocr_tables = getattr(fallback_result, 'tables', None)

                    extraction_result = await structured_service.extract(
                        corrected_text,
                        document_id=document_id,
                        tables=ocr_tables,
                        detected_language=language,  # NEU: Sprache fuer Uebersetzung uebergeben
                    )

                    if extraction_result and extraction_result.classification:
                        structured_extraction_applied = True
                        classified_document_type = extraction_result.classification.document_type.value

                        # Zu Dict konvertieren fuer Speicherung
                        structured_data = {
                            "classification": {
                                "document_type": extraction_result.classification.document_type.value,
                                "confidence": extraction_result.classification.confidence,
                                "matched_keywords": extraction_result.classification.matched_keywords[:10],
                            },
                            "overall_confidence": extraction_result.overall_confidence,
                            "extraction_version": extraction_result.extraction_version,
                            "extracted_at": extraction_result.extracted_at,
                            # Uebersetzungs-Metadaten (NEU fuer Mehrsprachigkeit)
                            "original_language": extraction_result.original_language,
                            "was_translated": extraction_result.was_translated,
                            "translation_confidence": extraction_result.translation_confidence,
                        }

                        # Typspezifische Daten hinzufuegen
                        if extraction_result.invoice:
                            structured_data["invoice"] = extraction_result.invoice.model_dump(
                                mode="json", exclude_none=True
                            )
                        if extraction_result.order:
                            structured_data["order"] = extraction_result.order.model_dump(
                                mode="json", exclude_none=True
                            )
                        if extraction_result.contract:
                            structured_data["contract"] = extraction_result.contract.model_dump(
                                mode="json", exclude_none=True
                            )

                        # Allgemeine Entities
                        if extraction_result.vat_ids:
                            structured_data["vat_ids"] = extraction_result.vat_ids
                        if extraction_result.ibans:
                            structured_data["ibans"] = extraction_result.ibans
                        if extraction_result.companies:
                            structured_data["companies"] = extraction_result.companies

                        logger.info(
                            "ocr_pipeline_structured_extraction_applied",
                            document_id=document_id,
                            document_type=classified_document_type,
                            classification_confidence=extraction_result.classification.confidence,
                            overall_confidence=extraction_result.overall_confidence,
                            original_language=extraction_result.original_language,
                            was_translated=extraction_result.was_translated,
                        )

                except Exception as e:
                    logger.warning(
                        "ocr_pipeline_structured_extraction_error",
                        document_id=document_id,
                        **safe_error_log(e)
                    )
                    # Fortfahren ohne Structured Extraction bei Fehler

        # Step 7: Finale Confidence-Analyse
        confidence_details = None
        if fallback_result.confidence_metrics:
            confidence_details = fallback_result.confidence_metrics.to_dict()

        total_time = int((time.perf_counter() - start_time) * 1000)

        result = OCRPipelineResult(
            success=True,
            text=fallback_result.text,
            corrected_text=corrected_text,
            confidence=current_confidence,  # Aktualisierte Confidence nach ggf. Fallback
            backend_used=fallback_result.final_backend,
            backends_tried=fallback_result.backends_tried,
            fallbacks_occurred=fallback_result.fallbacks_occurred,
            corrections_applied=corrections_applied,
            processing_time_ms=total_time,
            german_correction_applied=german_correction_applied,
            historical_normalization_applied=historical_normalization_applied,
            historical_changes_count=historical_changes_count,
            confidence_details=confidence_details,
            correction_details=correction_details,
            historical_normalization_details=historical_normalization_details,
            needs_review=needs_review,
            confidence_fallback_triggered=confidence_fallback_triggered,
            entity_extraction_applied=entity_extraction_applied,
            extracted_entities=extracted_entities,
            structured_extraction_applied=structured_extraction_applied,
            structured_data=structured_data,
            document_type=classified_document_type,
        )

        logger.info(
            "ocr_pipeline_completed",
            document_id=document_id,
            success=True,
            backend=fallback_result.final_backend,
            confidence=current_confidence,
            corrections=corrections_applied,
            historical_changes=historical_changes_count,
            entity_extraction=entity_extraction_applied,
            entities_found=len(extracted_entities.get("identifiers", [])) if extracted_entities else 0,
            structured_extraction=structured_extraction_applied,
            document_type=classified_document_type,
            time_ms=total_time,
            needs_review=needs_review,
            confidence_fallback_triggered=confidence_fallback_triggered
        )

        return result

    async def process_batch(
        self,
        documents: List[Dict[str, Any]],
        concurrency: int = 2
    ) -> List[OCRPipelineResult]:
        """
        Verarbeite mehrere Dokumente parallel.

        Args:
            documents: Liste von Dokumenten mit document_id, image_path, etc.
            concurrency: Maximale parallele Verarbeitungen

        Returns:
            Liste von OCRPipelineResult
        """
        semaphore = asyncio.Semaphore(concurrency)

        async def process_with_semaphore(doc: Dict[str, Any]) -> OCRPipelineResult:
            async with semaphore:
                return await self.process(
                    document_id=doc["document_id"],
                    image_path=doc["image_path"],
                    language=doc.get("language", "de"),
                    options=doc.get("options"),
                    preferred_backend=doc.get("preferred_backend"),
                    document_type=doc.get("document_type")
                )

        results = await asyncio.gather(
            *[process_with_semaphore(doc) for doc in documents],
            return_exceptions=True
        )

        # Konvertiere Exceptions zu Fehler-Results
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(OCRPipelineResult(
                    success=False,
                    text="",
                    corrected_text="",
                    confidence=0.0,
                    backend_used="error",
                    backends_tried=[],
                    fallbacks_occurred=0,
                    corrections_applied=0,
                    processing_time_ms=0,
                    german_correction_applied=False,
                    error=str(result)
                ))
            else:
                processed_results.append(result)

        return processed_results

    def get_status(self) -> Dict[str, Any]:
        """Hole vollständigen Pipeline-Status."""
        status = {
            "pipeline": {
                "german_correction_enabled": self.enable_german_correction,
                "circuit_breaker_enabled": self.enable_circuit_breaker,
                "memory_guard_enabled": self.enable_memory_guard,
                "historical_normalization_enabled": self.enable_historical_normalization,
                "entity_extraction_enabled": self.enable_entity_extraction,
                "structured_extraction_enabled": self.enable_structured_extraction,
                "min_confidence_threshold": self.min_confidence_threshold,
                "confidence_thresholds": {
                    "low": self.confidence_thresholds.low,
                    "medium": self.confidence_thresholds.medium,
                    "high": self.confidence_thresholds.high,
                },
                "confidence_fallback_enabled": self.enable_confidence_fallback,
            },
            "fallback_chain": self.fallback_chain.get_metrics(),
            "circuit_breakers": self.circuit_registry.get_all_status(),
        }

        # Historical Normalizer Status
        if self._historical_normalizer:
            status["historical_normalizer"] = {
                "loaded": True,
                "pre_1996_enabled": settings.HISTORICAL_NORM_PRE_1996,
                "th_enabled": settings.HISTORICAL_NORM_TH,
                "c_enabled": settings.HISTORICAL_NORM_C,
                "ph_enabled": settings.HISTORICAL_NORM_PH,
                "fraktur_enabled": settings.HISTORICAL_NORM_FRAKTUR,
            }
        else:
            status["historical_normalizer"] = {"loaded": False}

        if self.memory_guard:
            status["memory_guard"] = self.memory_guard.get_status()

        # German Agent Status
        if self._german_agent:
            status["german_correction"] = self._german_agent.get_correction_stats()

        # Entity Extraction Status
        if self._entity_extraction_service:
            status["entity_extraction"] = {
                "loaded": True,
                "stats": self._entity_extraction_service.get_extraction_stats(),
            }
        else:
            status["entity_extraction"] = {"loaded": False}

        # Structured Extraction Status
        if self._structured_extraction_service:
            status["structured_extraction"] = {
                "loaded": True,
                "classification_stats": (
                    self._structured_extraction_service.classification_service.get_stats()
                    if hasattr(self._structured_extraction_service, 'classification_service')
                    else {}
                ),
            }
        else:
            status["structured_extraction"] = {"loaded": False}

        return status


# Singleton Instance
_ocr_pipeline: Optional[OCRPipeline] = None


def get_ocr_pipeline() -> OCRPipeline:
    """Hole Singleton-Instance der OCR Pipeline."""
    global _ocr_pipeline
    if _ocr_pipeline is None:
        _ocr_pipeline = OCRPipeline()
    return _ocr_pipeline
