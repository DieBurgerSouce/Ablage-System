"""
OpenTelemetry und Observability für Ablage-System.

Umfassende Telemetrie-Integration:
- Distributed Tracing mit OpenTelemetry
- Prometheus Metriken
- Strukturiertes Logging
- SLO/SLI Tracking

Feinpoliert und durchdacht - Enterprise-grade Observability.
"""

import time
import functools
from contextlib import contextmanager
from typing import Any, Callable, Dict, Optional, TypeVar
import structlog

# Prometheus imports
from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    Summary,
    Info,
    REGISTRY,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

logger = structlog.get_logger(__name__)

# Type variable for generic decorator
F = TypeVar('F', bound=Callable[..., Any])

# =============================================================================
# OpenTelemetry Setup (optional - graceful degradation if not installed)
# =============================================================================

OPENTELEMETRY_AVAILABLE = False
tracer = None

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME
    from opentelemetry.trace import Status, StatusCode
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    # OTLP Exporter (optional)
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        OTLP_AVAILABLE = True
    except ImportError:
        OTLP_AVAILABLE = False
        OTLPSpanExporter = None

    OPENTELEMETRY_AVAILABLE = True
    logger.info("opentelemetry_available", otlp_exporter=OTLP_AVAILABLE)

except ImportError:
    logger.info("opentelemetry_not_installed", message="Tracing deaktiviert")
    trace = None
    Status = None
    StatusCode = None


def init_telemetry(
    service_name: str = "ablage-system-ocr",
    otlp_endpoint: Optional[str] = None
) -> None:
    """
    Initialisiere OpenTelemetry Tracing.

    Args:
        service_name: Name des Services für Traces
        otlp_endpoint: Optional OTLP Collector Endpoint
    """
    global tracer

    if not OPENTELEMETRY_AVAILABLE:
        logger.warning("telemetry_init_skipped", reason="OpenTelemetry nicht installiert")
        return

    try:
        # Create resource with service name
        resource = Resource(attributes={
            SERVICE_NAME: service_name,
            "service.version": "1.0.0",
            "deployment.environment": "production",
        })

        # Create tracer provider
        provider = TracerProvider(resource=resource)

        # Add OTLP exporter if endpoint provided and available
        if otlp_endpoint and OTLP_AVAILABLE:
            otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
            provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            logger.info("otlp_exporter_configured", endpoint=otlp_endpoint)

        # Set global tracer provider
        trace.set_tracer_provider(provider)

        # Get tracer
        tracer = trace.get_tracer(__name__)

        logger.info(
            "telemetry_initialized",
            service_name=service_name,
            otlp_enabled=otlp_endpoint is not None
        )

    except Exception as e:
        logger.error("telemetry_init_failed", error=str(e))


# =============================================================================
# PROMETHEUS METRIKEN - OCR SPEZIFISCH
# =============================================================================

# OCR Request Metriken
ocr_requests_total = Counter(
    "ablage_ocr_requests_total",
    "Gesamtzahl OCR Anfragen",
    ["backend", "status", "document_type"]
)

ocr_request_duration_seconds = Histogram(
    "ablage_ocr_request_duration_seconds",
    "OCR Verarbeitungszeit in Sekunden",
    ["backend"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0]
)

ocr_confidence_score = Histogram(
    "ablage_ocr_confidence_score",
    "OCR Confidence Score Distribution",
    ["backend"],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0]
)

# Fallback Metriken
ocr_fallbacks_total = Counter(
    "ablage_ocr_fallbacks_total",
    "Anzahl Backend Fallbacks",
    ["from_backend", "to_backend", "reason"]
)

# German Correction Metriken
german_corrections_total = Counter(
    "ablage_german_corrections_total",
    "Anzahl deutscher Textkorrekturen",
    ["correction_type"]
)

german_umlauts_restored = Counter(
    "ablage_german_umlauts_restored_total",
    "Anzahl wiederhergestellter Umlaute"
)

# GPU Metriken
gpu_memory_usage_bytes = Gauge(
    "ablage_gpu_memory_usage_bytes",
    "Aktuelle GPU Speichernutzung in Bytes"
)

gpu_memory_limit_bytes = Gauge(
    "ablage_gpu_memory_limit_bytes",
    "GPU Speicherlimit in Bytes"
)

gpu_oom_events_total = Counter(
    "ablage_gpu_oom_events_total",
    "Anzahl GPU Out-of-Memory Events",
    ["backend"]
)

gpu_memory_cleanups_total = Counter(
    "ablage_gpu_memory_cleanups_total",
    "Anzahl GPU Cache Cleanups"
)

# Circuit Breaker Metriken
circuit_breaker_state = Gauge(
    "ablage_circuit_breaker_state",
    "Circuit Breaker Zustand (0=closed, 1=half_open, 2=open)",
    ["backend"]
)

circuit_breaker_failures_total = Counter(
    "ablage_circuit_breaker_failures_total",
    "Anzahl Circuit Breaker Failures",
    ["backend"]
)

# Dokument Metriken
documents_processed_total = Counter(
    "ablage_documents_processed_total",
    "Gesamtzahl verarbeiteter Dokumente",
    ["status", "backend"]
)

document_size_bytes = Histogram(
    "ablage_document_size_bytes",
    "Dokumentgröße in Bytes",
    buckets=[10000, 100000, 500000, 1000000, 5000000, 10000000, 50000000]
)

# Queue Metriken
ocr_queue_length = Gauge(
    "ablage_ocr_queue_length",
    "Aktuelle OCR Queue Länge"
)

ocr_queue_wait_seconds = Histogram(
    "ablage_ocr_queue_wait_seconds",
    "Wartezeit in der OCR Queue",
    buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0]
)

# System Info
system_info = Info(
    "ablage_system",
    "Ablage-System Informationen"
)


# =============================================================================
# SLO/SLI TRACKING
# =============================================================================

class SLOTracker:
    """
    Service Level Objective Tracker.

    Trackt SLIs und berechnet SLO Compliance:
    - Availability: System verfügbar
    - Latency: Request-Latenz unter Schwelle
    - Error Rate: Fehlerrate unter Schwelle
    - Quality: Confidence Score über Schwelle
    """

    # SLO Definitionen
    SLOS = {
        "availability": {
            "target": 0.999,  # 99.9% Verfügbarkeit
            "description": "System Verfügbarkeit"
        },
        "latency_p95": {
            "target_seconds": 10.0,  # 95% der Requests unter 10s
            "percentile": 95,
            "description": "95. Perzentil Latenz"
        },
        "latency_p99": {
            "target_seconds": 30.0,  # 99% der Requests unter 30s
            "percentile": 99,
            "description": "99. Perzentil Latenz"
        },
        "error_rate": {
            "target": 0.01,  # Maximal 1% Fehler
            "description": "Fehlerrate"
        },
        "ocr_quality": {
            "target_confidence": 0.85,  # 85% Mindest-Confidence
            "target_rate": 0.95,  # 95% der Dokumente erreichen dies
            "description": "OCR Qualität"
        }
    }

    def __init__(self):
        self._total_requests = 0
        self._successful_requests = 0
        self._failed_requests = 0
        self._latencies: list = []
        self._confidences: list = []
        self._window_size = 10000  # Rolling window

        # Prometheus SLO Gauges
        self._slo_compliance = Gauge(
            "ablage_slo_compliance_ratio",
            "SLO Compliance Ratio (0-1)",
            ["slo_name"]
        )

        self._sli_value = Gauge(
            "ablage_sli_value",
            "Aktuelle SLI Werte",
            ["sli_name"]
        )

    def record_request(
        self,
        success: bool,
        latency_seconds: float,
        confidence: Optional[float] = None
    ) -> None:
        """
        Zeichne einen Request für SLO Tracking auf.

        Args:
            success: Request erfolgreich
            latency_seconds: Latenz in Sekunden
            confidence: Optional OCR Confidence Score
        """
        self._total_requests += 1

        if success:
            self._successful_requests += 1
        else:
            self._failed_requests += 1

        # Latenz tracken (rolling window)
        self._latencies.append(latency_seconds)
        if len(self._latencies) > self._window_size:
            self._latencies = self._latencies[-self._window_size:]

        # Confidence tracken
        if confidence is not None:
            self._confidences.append(confidence)
            if len(self._confidences) > self._window_size:
                self._confidences = self._confidences[-self._window_size:]

        # Update Prometheus Metriken
        self._update_prometheus_metrics()

    def _update_prometheus_metrics(self) -> None:
        """Aktualisiere Prometheus SLO Metriken."""
        compliance = self.get_slo_compliance()

        for slo_name, is_compliant in compliance.items():
            self._slo_compliance.labels(slo_name=slo_name).set(
                1.0 if is_compliant else 0.0
            )

        # SLI Werte
        slis = self.get_sli_values()
        for sli_name, value in slis.items():
            self._sli_value.labels(sli_name=sli_name).set(value)

    def get_sli_values(self) -> Dict[str, float]:
        """Hole aktuelle SLI Werte."""
        slis = {}

        # Availability
        if self._total_requests > 0:
            slis["availability"] = self._successful_requests / self._total_requests
        else:
            slis["availability"] = 1.0

        # Error Rate
        if self._total_requests > 0:
            slis["error_rate"] = self._failed_requests / self._total_requests
        else:
            slis["error_rate"] = 0.0

        # Latenz Perzentile
        if self._latencies:
            sorted_latencies = sorted(self._latencies)
            p95_idx = int(len(sorted_latencies) * 0.95)
            p99_idx = int(len(sorted_latencies) * 0.99)
            slis["latency_p95"] = sorted_latencies[min(p95_idx, len(sorted_latencies) - 1)]
            slis["latency_p99"] = sorted_latencies[min(p99_idx, len(sorted_latencies) - 1)]
        else:
            slis["latency_p95"] = 0.0
            slis["latency_p99"] = 0.0

        # OCR Quality
        if self._confidences:
            target_conf = self.SLOS["ocr_quality"]["target_confidence"]
            above_threshold = sum(1 for c in self._confidences if c >= target_conf)
            slis["ocr_quality_rate"] = above_threshold / len(self._confidences)
            slis["ocr_confidence_avg"] = sum(self._confidences) / len(self._confidences)
        else:
            slis["ocr_quality_rate"] = 1.0
            slis["ocr_confidence_avg"] = 0.0

        return slis

    def get_slo_compliance(self) -> Dict[str, bool]:
        """Prüfe SLO Compliance."""
        slis = self.get_sli_values()
        compliance = {}

        # Availability SLO
        compliance["availability"] = slis["availability"] >= self.SLOS["availability"]["target"]

        # Error Rate SLO
        compliance["error_rate"] = slis["error_rate"] <= self.SLOS["error_rate"]["target"]

        # Latency SLOs
        compliance["latency_p95"] = slis["latency_p95"] <= self.SLOS["latency_p95"]["target_seconds"]
        compliance["latency_p99"] = slis["latency_p99"] <= self.SLOS["latency_p99"]["target_seconds"]

        # OCR Quality SLO
        compliance["ocr_quality"] = (
            slis["ocr_quality_rate"] >= self.SLOS["ocr_quality"]["target_rate"]
        )

        return compliance

    def get_summary(self) -> Dict[str, Any]:
        """Hole vollständige SLO Zusammenfassung."""
        slis = self.get_sli_values()
        compliance = self.get_slo_compliance()

        all_compliant = all(compliance.values())

        return {
            "status": "healthy" if all_compliant else "degraded",
            "overall_compliance": all_compliant,
            "slos": {
                name: {
                    "target": config,
                    "compliant": compliance[name],
                    "current_value": slis.get(name, slis.get(f"{name}_rate", 0))
                }
                for name, config in self.SLOS.items()
            },
            "slis": slis,
            "sample_size": {
                "total_requests": self._total_requests,
                "latency_samples": len(self._latencies),
                "confidence_samples": len(self._confidences),
            }
        }


# Singleton SLO Tracker
_slo_tracker: Optional[SLOTracker] = None


def get_slo_tracker() -> SLOTracker:
    """Hole Singleton SLO Tracker."""
    global _slo_tracker
    if _slo_tracker is None:
        _slo_tracker = SLOTracker()
    return _slo_tracker


# =============================================================================
# TRACING DECORATORS UND CONTEXT MANAGERS
# =============================================================================

def traced(
    span_name: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None
):
    """
    Decorator für OpenTelemetry Tracing.

    Args:
        span_name: Name des Spans (default: Funktionsname)
        attributes: Zusätzliche Span Attribute

    Usage:
        @traced("ocr.process")
        async def process_document(...):
            ...
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            name = span_name or f"{func.__module__}.{func.__name__}"

            if tracer and OPENTELEMETRY_AVAILABLE:
                with tracer.start_as_current_span(name) as span:
                    if attributes:
                        for key, value in attributes.items():
                            span.set_attribute(key, value)

                    try:
                        result = await func(*args, **kwargs)
                        span.set_status(Status(StatusCode.OK))
                        return result
                    except Exception as e:
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                        span.record_exception(e)
                        raise
            else:
                return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            name = span_name or f"{func.__module__}.{func.__name__}"

            if tracer and OPENTELEMETRY_AVAILABLE:
                with tracer.start_as_current_span(name) as span:
                    if attributes:
                        for key, value in attributes.items():
                            span.set_attribute(key, value)

                    try:
                        result = func(*args, **kwargs)
                        span.set_status(Status(StatusCode.OK))
                        return result
                    except Exception as e:
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                        span.record_exception(e)
                        raise
            else:
                return func(*args, **kwargs)

        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


@contextmanager
def trace_span(name: str, attributes: Optional[Dict[str, Any]] = None):
    """
    Context Manager für OpenTelemetry Spans.

    Usage:
        with trace_span("process_image", {"image_size": 1024}):
            # ... processing
    """
    if tracer and OPENTELEMETRY_AVAILABLE:
        with tracer.start_as_current_span(name) as span:
            if attributes:
                for key, value in attributes.items():
                    span.set_attribute(key, value)
            try:
                yield span
                span.set_status(Status(StatusCode.OK))
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
    else:
        yield None


# =============================================================================
# METRIKEN HELPER FUNKTIONEN
# =============================================================================

def record_ocr_request(
    backend: str,
    status: str,
    document_type: str,
    duration_seconds: float,
    confidence: Optional[float] = None
) -> None:
    """
    Zeichne OCR Request Metriken auf.

    Args:
        backend: Verwendetes Backend
        status: success/failure
        document_type: Dokumenttyp
        duration_seconds: Verarbeitungszeit
        confidence: Optional Confidence Score
    """
    ocr_requests_total.labels(
        backend=backend,
        status=status,
        document_type=document_type
    ).inc()

    ocr_request_duration_seconds.labels(backend=backend).observe(duration_seconds)

    if confidence is not None:
        ocr_confidence_score.labels(backend=backend).observe(confidence)

    # SLO Tracking
    slo_tracker = get_slo_tracker()
    slo_tracker.record_request(
        success=(status == "success"),
        latency_seconds=duration_seconds,
        confidence=confidence
    )


def record_fallback(
    from_backend: str,
    to_backend: str,
    reason: str
) -> None:
    """Zeichne Backend Fallback auf."""
    ocr_fallbacks_total.labels(
        from_backend=from_backend,
        to_backend=to_backend,
        reason=reason
    ).inc()


def record_german_correction(
    correction_type: str,
    count: int = 1
) -> None:
    """Zeichne German Correction auf."""
    german_corrections_total.labels(correction_type=correction_type).inc(count)


def record_umlaut_restoration(count: int = 1) -> None:
    """Zeichne Umlaut-Wiederherstellung auf."""
    german_umlauts_restored.inc(count)


def update_gpu_metrics(
    usage_bytes: int,
    limit_bytes: int
) -> None:
    """Aktualisiere GPU Metriken."""
    gpu_memory_usage_bytes.set(usage_bytes)
    gpu_memory_limit_bytes.set(limit_bytes)


def record_gpu_oom(backend: str) -> None:
    """Zeichne GPU OOM Event auf."""
    gpu_oom_events_total.labels(backend=backend).inc()


def record_gpu_cleanup() -> None:
    """Zeichne GPU Cleanup auf."""
    gpu_memory_cleanups_total.inc()


def update_circuit_breaker_state(backend: str, state: int) -> None:
    """
    Aktualisiere Circuit Breaker Status.

    Args:
        backend: Backend Name
        state: 0=closed, 1=half_open, 2=open
    """
    circuit_breaker_state.labels(backend=backend).set(state)


def set_system_info(version: str, environment: str) -> None:
    """Setze System Info Metrik."""
    system_info.info({
        "version": version,
        "environment": environment,
        "service": "ablage-system-ocr"
    })
