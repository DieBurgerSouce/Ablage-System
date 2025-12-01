"""
OCR Backend Fallback Chain für Ablage-System.

Implementiert intelligente Fallback-Logik:
- Confidence-basierte Backend-Auswahl
- Automatischer Wechsel bei niedriger Confidence
- Circuit Breaker Integration
- Metriken und Logging

Feinpoliert und durchdacht - Enterprise-grade Fallback Management.
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
import structlog

from app.services.confidence_service import (
    ConfidenceService,
    ConfidenceMetrics,
    ConfidenceLevel,
    QualityDecision,
    get_confidence_service
)
from app.services.circuit_breaker import (
    CircuitBreakerRegistry,
    CircuitBreakerError,
    CircuitState,
    get_circuit_breaker_registry
)

logger = structlog.get_logger(__name__)


class FallbackReason(Enum):
    """Gründe für Fallback."""
    LOW_CONFIDENCE = "low_confidence"
    BACKEND_ERROR = "backend_error"
    TIMEOUT = "timeout"
    GPU_OOM = "gpu_oom"
    MODEL_UNAVAILABLE = "model_unavailable"
    CIRCUIT_OPEN = "circuit_open"
    MANUAL = "manual"


@dataclass
class FallbackResult:
    """Ergebnis einer Fallback Chain Ausführung."""
    success: bool
    text: str
    confidence: float
    final_backend: str
    backends_tried: List[str]
    fallbacks_occurred: int
    fallback_reasons: List[Dict[str, str]]
    total_time_ms: int
    confidence_metrics: Optional[ConfidenceMetrics] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "text": self.text,
            "confidence": round(self.confidence, 4),
            "final_backend": self.final_backend,
            "backends_tried": self.backends_tried,
            "fallbacks_occurred": self.fallbacks_occurred,
            "fallback_reasons": self.fallback_reasons,
            "total_time_ms": self.total_time_ms,
            "confidence_metrics": self.confidence_metrics.to_dict() if self.confidence_metrics else None,
            "error": self.error,
        }


@dataclass
class BackendConfig:
    """Konfiguration für ein OCR Backend."""
    name: str
    priority: int  # Niedrigere Werte = höhere Priorität
    requires_gpu: bool
    vram_gb: float
    min_confidence_threshold: float = 0.65
    timeout_seconds: float = 120.0
    enabled: bool = True
    strengths: List[str] = field(default_factory=list)


class FallbackChain:
    """
    Implementiert eine Fallback Chain für OCR Backends.

    Die Chain versucht Backends in Prioritätsreihenfolge und
    fällt automatisch auf das nächste Backend zurück wenn:
    - Die Confidence zu niedrig ist
    - Ein Fehler auftritt
    - Ein Timeout erreicht wird
    """

    # Vorkonfigurierte Backends
    DEFAULT_BACKENDS = [
        BackendConfig(
            name="deepseek-janus-pro",
            priority=1,
            requires_gpu=True,
            vram_gb=12.0,
            min_confidence_threshold=0.70,
            timeout_seconds=120.0,
            strengths=["complex", "handwriting", "fraktur", "tables", "german"]
        ),
        BackendConfig(
            name="got-ocr-2.0",
            priority=2,
            requires_gpu=True,
            vram_gb=10.0,
            min_confidence_threshold=0.65,
            timeout_seconds=90.0,
            strengths=["formulas", "tables", "markdown", "fast"]
        ),
        BackendConfig(
            name="donut",
            priority=3,
            requires_gpu=True,
            vram_gb=8.0,
            min_confidence_threshold=0.60,
            timeout_seconds=90.0,
            strengths=["multilingual", "100_languages", "cyrillic", "polish", "russian"]
        ),
        BackendConfig(
            name="surya-gpu",
            priority=4,
            requires_gpu=True,
            vram_gb=4.0,
            min_confidence_threshold=0.60,
            timeout_seconds=60.0,
            strengths=["fast", "general", "german"]
        ),
        BackendConfig(
            name="surya",
            priority=5,
            requires_gpu=False,
            vram_gb=0.0,
            min_confidence_threshold=0.50,
            timeout_seconds=180.0,
            strengths=["cpu_fallback", "general"]
        ),
    ]

    def __init__(
        self,
        backends: Optional[List[BackendConfig]] = None,
        confidence_service: Optional[ConfidenceService] = None,
        circuit_breaker_registry: Optional[CircuitBreakerRegistry] = None,
        max_fallbacks: int = 3,
        aggregate_results: bool = False,
        enable_circuit_breaker: bool = True
    ):
        """
        Initialisiere Fallback Chain.

        Args:
            backends: Liste von Backend-Konfigurationen
            confidence_service: ConfidenceService Instance
            circuit_breaker_registry: CircuitBreakerRegistry für Backend-Schutz
            max_fallbacks: Maximale Anzahl Fallback-Versuche
            aggregate_results: Ob mehrere Ergebnisse aggregiert werden sollen
            enable_circuit_breaker: Circuit Breaker für Backends aktivieren
        """
        self.backends = sorted(
            backends or self.DEFAULT_BACKENDS,
            key=lambda b: b.priority
        )
        self.confidence_service = confidence_service or get_confidence_service()
        self.circuit_registry = circuit_breaker_registry or get_circuit_breaker_registry()
        self.max_fallbacks = max_fallbacks
        self.aggregate_results = aggregate_results
        self.enable_circuit_breaker = enable_circuit_breaker

        # Backend Handler Registry
        self._backend_handlers: Dict[str, Callable] = {}

        # Metriken
        self._fallback_counts: Dict[str, int] = {b.name: 0 for b in self.backends}
        self._success_counts: Dict[str, int] = {b.name: 0 for b in self.backends}
        self._total_calls: Dict[str, int] = {b.name: 0 for b in self.backends}

        # Circuit Breakers für alle Backends initialisieren
        if self.enable_circuit_breaker:
            for backend in self.backends:
                self.circuit_registry.get_or_create(backend.name)

        logger.info(
            "fallback_chain_initialized",
            backends=[b.name for b in self.backends],
            max_fallbacks=max_fallbacks,
            circuit_breaker_enabled=enable_circuit_breaker
        )

    def register_backend_handler(
        self,
        backend_name: str,
        handler: Callable
    ) -> None:
        """
        Registriere einen Handler für ein Backend.

        Args:
            backend_name: Name des Backends
            handler: Async Callable das OCR ausführt
        """
        self._backend_handlers[backend_name] = handler
        logger.debug("backend_handler_registered", backend=backend_name)

    def get_enabled_backends(
        self,
        gpu_available: bool = True,
        available_vram_gb: float = 16.0
    ) -> List[BackendConfig]:
        """
        Hole Liste der verfügbaren Backends.

        Args:
            gpu_available: Ob GPU verfügbar ist
            available_vram_gb: Verfügbarer VRAM in GB

        Returns:
            Liste der verfügbaren Backends in Prioritätsreihenfolge
        """
        available = []
        for backend in self.backends:
            if not backend.enabled:
                continue

            if backend.requires_gpu:
                if not gpu_available:
                    continue
                if backend.vram_gb > available_vram_gb:
                    continue

            available.append(backend)

        return available

    async def execute(
        self,
        document_id: str,
        image_path: str,
        language: str = "de",
        options: Optional[Dict[str, Any]] = None,
        preferred_backend: Optional[str] = None,
        document_type: Optional[str] = None,
        gpu_available: bool = True,
        available_vram_gb: float = 16.0
    ) -> FallbackResult:
        """
        Führe OCR mit Fallback Chain aus.

        Args:
            document_id: Dokument-ID
            image_path: Pfad zum Bild
            language: Sprache (default: "de")
            options: Zusätzliche Optionen
            preferred_backend: Bevorzugtes Backend (optional)
            document_type: Dokumenttyp für optimierte Backend-Auswahl
            gpu_available: Ob GPU verfügbar ist
            available_vram_gb: Verfügbarer VRAM

        Returns:
            FallbackResult mit Ergebnis oder Fehler
        """
        start_time = time.perf_counter()
        options = options or {}

        # Hole verfügbare Backends
        available_backends = self.get_enabled_backends(gpu_available, available_vram_gb)

        if not available_backends:
            return FallbackResult(
                success=False,
                text="",
                confidence=0.0,
                final_backend="none",
                backends_tried=[],
                fallbacks_occurred=0,
                fallback_reasons=[],
                total_time_ms=int((time.perf_counter() - start_time) * 1000),
                error="Keine Backends verfügbar"
            )

        # Ordne Backends basierend auf Präferenz
        if preferred_backend:
            available_backends = self._reorder_by_preference(
                available_backends, preferred_backend
            )

        # Track Fallback-Versuche
        backends_tried = []
        fallback_reasons = []
        last_result = None
        last_metrics = None

        # Versuche Backends in Reihenfolge
        for i, backend in enumerate(available_backends):
            if i >= self.max_fallbacks + 1:  # +1 für initialen Versuch
                break

            backend_name = backend.name
            backends_tried.append(backend_name)
            self._total_calls[backend_name] = self._total_calls.get(backend_name, 0) + 1

            logger.info(
                "fallback_chain_trying_backend",
                document_id=document_id,
                backend=backend_name,
                attempt=i + 1,
                max_attempts=min(len(available_backends), self.max_fallbacks + 1)
            )

            try:
                # Führe OCR aus
                result = await self._execute_backend(
                    backend=backend,
                    document_id=document_id,
                    image_path=image_path,
                    language=language,
                    options=options
                )

                if not result or not result.get("success", False):
                    error_msg = result.get("error", "Unbekannter Fehler") if result else "Kein Ergebnis"
                    fallback_reasons.append({
                        "backend": backend_name,
                        "reason": FallbackReason.BACKEND_ERROR.value,
                        "details": error_msg
                    })
                    self._fallback_counts[backend_name] = self._fallback_counts.get(backend_name, 0) + 1
                    continue

                # Analysiere Confidence
                confidence = result.get("confidence", 0.0)
                confidence_details = result.get("confidence_details")

                metrics = self.confidence_service.analyze_ocr_result(
                    confidence=confidence,
                    confidence_details=confidence_details,
                    backend=backend_name
                )

                last_result = result
                last_metrics = metrics

                # Prüfe ob Fallback nötig
                should_fallback, fallback_reason = self.confidence_service.should_trigger_fallback(
                    metrics=metrics,
                    document_type=document_type
                )

                if should_fallback and i < len(available_backends) - 1:
                    fallback_reasons.append({
                        "backend": backend_name,
                        "reason": FallbackReason.LOW_CONFIDENCE.value,
                        "details": fallback_reason,
                        "confidence": confidence
                    })
                    self._fallback_counts[backend_name] = self._fallback_counts.get(backend_name, 0) + 1
                    logger.warning(
                        "fallback_chain_low_confidence",
                        document_id=document_id,
                        backend=backend_name,
                        confidence=confidence,
                        reason=fallback_reason
                    )
                    continue

                # Erfolg!
                self._success_counts[backend_name] = self._success_counts.get(backend_name, 0) + 1

                total_time = int((time.perf_counter() - start_time) * 1000)
                return FallbackResult(
                    success=True,
                    text=result.get("text", ""),
                    confidence=confidence,
                    final_backend=backend_name,
                    backends_tried=backends_tried,
                    fallbacks_occurred=len(fallback_reasons),
                    fallback_reasons=fallback_reasons,
                    total_time_ms=total_time,
                    confidence_metrics=metrics
                )

            except asyncio.TimeoutError:
                fallback_reasons.append({
                    "backend": backend_name,
                    "reason": FallbackReason.TIMEOUT.value,
                    "details": f"Timeout nach {backend.timeout_seconds}s"
                })
                self._fallback_counts[backend_name] = self._fallback_counts.get(backend_name, 0) + 1
                logger.error(
                    "fallback_chain_timeout",
                    document_id=document_id,
                    backend=backend_name,
                    timeout=backend.timeout_seconds
                )

            except CircuitBreakerError as e:
                # Circuit Breaker hat Backend blockiert
                fallback_reasons.append({
                    "backend": backend_name,
                    "reason": FallbackReason.CIRCUIT_OPEN.value,
                    "details": f"Circuit offen, retry in {e.retry_after:.1f}s"
                })
                self._fallback_counts[backend_name] = self._fallback_counts.get(backend_name, 0) + 1
                logger.warning(
                    "fallback_chain_circuit_breaker_skip",
                    document_id=document_id,
                    backend=backend_name,
                    retry_after=e.retry_after
                )

            except Exception as e:
                error_type = type(e).__name__

                # Spezifische Fehlerbehandlung
                if "OutOfMemoryError" in error_type or "OOM" in str(e):
                    reason = FallbackReason.GPU_OOM
                elif "not found" in str(e).lower() or "unavailable" in str(e).lower():
                    reason = FallbackReason.MODEL_UNAVAILABLE
                else:
                    reason = FallbackReason.BACKEND_ERROR

                fallback_reasons.append({
                    "backend": backend_name,
                    "reason": reason.value,
                    "details": str(e)
                })
                self._fallback_counts[backend_name] = self._fallback_counts.get(backend_name, 0) + 1
                logger.error(
                    "fallback_chain_error",
                    document_id=document_id,
                    backend=backend_name,
                    error=str(e),
                    error_type=error_type
                )

        # Alle Backends fehlgeschlagen - verwende letztes Ergebnis wenn vorhanden
        total_time = int((time.perf_counter() - start_time) * 1000)

        if last_result:
            logger.warning(
                "fallback_chain_using_best_available",
                document_id=document_id,
                backends_tried=backends_tried,
                confidence=last_result.get("confidence", 0.0)
            )
            return FallbackResult(
                success=True,  # Teilweise erfolgreich
                text=last_result.get("text", ""),
                confidence=last_result.get("confidence", 0.0),
                final_backend=backends_tried[-1] if backends_tried else "unknown",
                backends_tried=backends_tried,
                fallbacks_occurred=len(fallback_reasons),
                fallback_reasons=fallback_reasons,
                total_time_ms=total_time,
                confidence_metrics=last_metrics,
                error="Alle primären Backends fehlgeschlagen, verwende bestes verfügbares Ergebnis"
            )

        # Komplett fehlgeschlagen
        logger.error(
            "fallback_chain_all_failed",
            document_id=document_id,
            backends_tried=backends_tried
        )
        return FallbackResult(
            success=False,
            text="",
            confidence=0.0,
            final_backend="none",
            backends_tried=backends_tried,
            fallbacks_occurred=len(fallback_reasons),
            fallback_reasons=fallback_reasons,
            total_time_ms=total_time,
            error="Alle Backends fehlgeschlagen"
        )

    async def _execute_backend(
        self,
        backend: BackendConfig,
        document_id: str,
        image_path: str,
        language: str,
        options: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Führe ein einzelnes Backend mit Circuit Breaker Schutz aus.

        Args:
            backend: Backend-Konfiguration
            document_id: Dokument-ID
            image_path: Bildpfad
            language: Sprache
            options: Optionen

        Returns:
            OCR-Ergebnis oder None bei Fehler

        Raises:
            CircuitBreakerError: Wenn Circuit offen ist
            asyncio.TimeoutError: Bei Timeout
        """
        handler = self._backend_handlers.get(backend.name)

        if not handler:
            logger.warning(
                "fallback_chain_no_handler",
                backend=backend.name
            )
            return None

        # Circuit Breaker Check (wenn aktiviert)
        circuit = None
        if self.enable_circuit_breaker:
            circuit = self.circuit_registry.get_or_create(backend.name)

            # Prüfe ob Circuit offen ist
            if circuit.state == CircuitState.OPEN:
                retry_after = circuit.get_retry_after()
                logger.warning(
                    "fallback_chain_circuit_open",
                    backend=backend.name,
                    retry_after=retry_after
                )
                raise CircuitBreakerError(
                    backend=backend.name,
                    state=circuit.state,
                    retry_after=retry_after
                )

        # Führe mit Timeout aus
        try:
            result = await asyncio.wait_for(
                handler(
                    document_id=document_id,
                    image_path=image_path,
                    language=language,
                    options=options
                ),
                timeout=backend.timeout_seconds
            )

            # Erfolg dem Circuit Breaker melden
            if circuit:
                await circuit.record_success()

            return result

        except asyncio.TimeoutError:
            # Timeout dem Circuit Breaker als Fehler melden
            if circuit:
                await circuit.record_failure()
            raise

        except CircuitBreakerError:
            # Weiterleiten ohne erneutes Recording
            raise

        except Exception as e:
            # Fehler dem Circuit Breaker melden
            if circuit:
                await circuit.record_failure()
            raise

    def _reorder_by_preference(
        self,
        backends: List[BackendConfig],
        preferred: str
    ) -> List[BackendConfig]:
        """Ordne Backends neu mit bevorzugtem Backend zuerst."""
        preferred_backend = None
        other_backends = []

        for backend in backends:
            if backend.name == preferred:
                preferred_backend = backend
            else:
                other_backends.append(backend)

        if preferred_backend:
            return [preferred_backend] + other_backends
        return backends

    def get_metrics(self) -> Dict[str, Any]:
        """Hole aktuelle Fallback-Metriken inkl. Circuit Breaker Status."""
        metrics = {
            "backends": {},
            "total_fallbacks": sum(self._fallback_counts.values()),
            "total_calls": sum(self._total_calls.values()),
            "circuit_breaker_enabled": self.enable_circuit_breaker
        }

        for backend in self.backends:
            name = backend.name
            total = self._total_calls.get(name, 0)
            success = self._success_counts.get(name, 0)
            fallbacks = self._fallback_counts.get(name, 0)

            backend_metrics = {
                "total_calls": total,
                "successes": success,
                "fallbacks": fallbacks,
                "success_rate": success / total if total > 0 else 0.0,
                "fallback_rate": fallbacks / total if total > 0 else 0.0,
            }

            # Circuit Breaker Status hinzufügen wenn aktiviert
            if self.enable_circuit_breaker:
                circuit = self.circuit_registry.get(name)
                if circuit:
                    backend_metrics["circuit_breaker"] = {
                        "state": circuit.state.value,
                        "consecutive_failures": circuit.stats.consecutive_failures,
                        "times_opened": circuit.stats.times_opened,
                    }

            metrics["backends"][name] = backend_metrics

        return metrics


# Singleton Instance
_fallback_chain: Optional[FallbackChain] = None


def get_fallback_chain() -> FallbackChain:
    """
    Hole Singleton-Instance der FallbackChain.

    Returns:
        FallbackChain Instance
    """
    global _fallback_chain
    if _fallback_chain is None:
        _fallback_chain = FallbackChain()
    return _fallback_chain
