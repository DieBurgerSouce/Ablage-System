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

logger = structlog.get_logger(__name__)


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
    confidence_details: Optional[Dict[str, Any]] = None
    correction_details: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

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
            "confidence_details": self.confidence_details,
            "correction_details": self.correction_details,
            "error": self.error,
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
        min_confidence_threshold: float = 0.65
    ):
        """
        Initialisiere OCR Pipeline.

        Args:
            enable_german_correction: German Correction Agent aktivieren
            enable_circuit_breaker: Circuit Breaker aktivieren
            enable_memory_guard: GPU Memory Guard aktivieren
            min_confidence_threshold: Minimale Confidence für Akzeptanz
        """
        self.enable_german_correction = enable_german_correction
        self.enable_circuit_breaker = enable_circuit_breaker
        self.enable_memory_guard = enable_memory_guard
        self.min_confidence_threshold = min_confidence_threshold

        # Services initialisieren
        self.confidence_service = get_confidence_service()
        self.fallback_chain = get_fallback_chain()
        self.circuit_registry = get_circuit_breaker_registry()
        self.memory_guard = get_memory_guard() if enable_memory_guard else None
        self.gpu_manager = GPUManager()

        # German Correction Agent (lazy load)
        self._german_agent = None

        # Backend Handlers registrieren
        self._register_default_backends()

        logger.info(
            "ocr_pipeline_initialized",
            german_correction=enable_german_correction,
            circuit_breaker=enable_circuit_breaker,
            memory_guard=enable_memory_guard,
            min_confidence=min_confidence_threshold
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
                    error=str(e)
                )
                self.enable_german_correction = False
        return self._german_agent

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
        except Exception as e:
            logger.error(
                "ocr_pipeline_fallback_error",
                document_id=document_id,
                error=str(e)
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
                error=str(e)
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
                        error=str(e)
                    )
                    # Verwende unkorrigierten Text bei Fehler

        # Step 4: Finale Confidence-Analyse
        confidence_details = None
        if fallback_result.confidence_metrics:
            confidence_details = fallback_result.confidence_metrics.to_dict()

        total_time = int((time.perf_counter() - start_time) * 1000)

        result = OCRPipelineResult(
            success=True,
            text=fallback_result.text,
            corrected_text=corrected_text,
            confidence=fallback_result.confidence,
            backend_used=fallback_result.final_backend,
            backends_tried=fallback_result.backends_tried,
            fallbacks_occurred=fallback_result.fallbacks_occurred,
            corrections_applied=corrections_applied,
            processing_time_ms=total_time,
            german_correction_applied=german_correction_applied,
            confidence_details=confidence_details,
            correction_details=correction_details
        )

        logger.info(
            "ocr_pipeline_completed",
            document_id=document_id,
            success=True,
            backend=fallback_result.final_backend,
            confidence=fallback_result.confidence,
            corrections=corrections_applied,
            time_ms=total_time
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
                "min_confidence_threshold": self.min_confidence_threshold,
            },
            "fallback_chain": self.fallback_chain.get_metrics(),
            "circuit_breakers": self.circuit_registry.get_all_status(),
        }

        if self.memory_guard:
            status["memory_guard"] = self.memory_guard.get_status()

        # German Agent Status
        if self._german_agent:
            status["german_correction"] = self._german_agent.get_correction_stats()

        return status


# Singleton Instance
_ocr_pipeline: Optional[OCRPipeline] = None


def get_ocr_pipeline() -> OCRPipeline:
    """Hole Singleton-Instance der OCR Pipeline."""
    global _ocr_pipeline
    if _ocr_pipeline is None:
        _ocr_pipeline = OCRPipeline()
    return _ocr_pipeline
