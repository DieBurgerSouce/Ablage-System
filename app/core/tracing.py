"""OpenTelemetry Distributed Tracing.

Implementiert End-to-End Tracing für das Ablage-System:
- Request Tracing über alle Services
- Span Context Propagation
- Custom Attributes für OCR-Operationen
- Integration mit Jaeger/OTLP Collector

Usage:
    from app.core.tracing import TracingService, trace_span


    # In app startup
    tracing = TracingService()
    tracing.setup()

    # In routes/services
    @trace_span("ocr_processing")
    async def process_document(...):
        ...
"""

import functools
import os
from contextlib import contextmanager
from typing import Callable, Dict, Optional, TypeVar, Union

import structlog

from app.core.safe_errors import safe_error_log

# Lazy imports für OpenTelemetry (optional dependency)
try:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.instrumentation.redis import RedisInstrumentor
    from opentelemetry.instrumentation.celery import CeleryInstrumentor
    from opentelemetry.propagate import set_global_textmap
    from opentelemetry.propagators.b3 import B3MultiFormat
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.trace.sampling import (
        ParentBasedTraceIdRatio,
        ALWAYS_ON,
    )
    from opentelemetry.trace import SpanKind, Status, StatusCode
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    OPENTELEMETRY_AVAILABLE = False

logger = structlog.get_logger(__name__)

F = TypeVar('F', bound=Callable[..., object])


class TracingService:
    """OpenTelemetry Tracing Service.

    Konfiguriert und verwaltet Distributed Tracing für das gesamte System.

    Features:
    - OTLP Export zu Jaeger/Collector
    - Auto-Instrumentierung für FastAPI, SQLAlchemy, Redis, Celery
    - Custom Span Attributes für OCR-Metriken
    - B3 und W3C Trace Context Propagation
    """

    def __init__(
        self,
        service_name: str = "ablage-system",
        service_version: str = "1.0.0",
        otlp_endpoint: Optional[str] = None,
        console_export: bool = False,
        enabled: bool = True
    ):
        """Initialisiert den Tracing Service.

        Args:
            service_name: Name des Services für Traces
            service_version: Version des Services
            otlp_endpoint: OTLP Collector Endpoint (z.B. localhost:4317)
            console_export: Zusätzlich auf Console ausgeben (Debug)
            enabled: Tracing aktivieren/deaktivieren
        """
        self.service_name = service_name
        self.service_version = service_version
        self.otlp_endpoint = otlp_endpoint or os.environ.get(
            "OTLP_ENDPOINT",
            "localhost:4317"
        )
        self.console_export = console_export or os.environ.get(
            "TRACING_CONSOLE_EXPORT",
            "false"
        ).lower() == "true"
        self.enabled = enabled and os.environ.get(
            "TRACING_ENABLED",
            "true"
        ).lower() == "true"

        # Sampling-Konfiguration
        self.sample_rate = float(os.environ.get("TRACE_SAMPLE_RATE", "1.0"))
        self.always_sample_errors = os.environ.get(
            "TRACE_ALWAYS_SAMPLE_ERRORS", "true"
        ).lower() == "true"
        self.slow_threshold = float(os.environ.get(
            "TRACE_SLOW_THRESHOLD_SECONDS", "1.0"
        ))

        self._tracer: Optional[object] = None
        self._provider: Optional[object] = None
        self._initialized = False

    def setup(self, app: Optional[object] = None) -> bool:
        """Initialisiert OpenTelemetry Tracing.

        Args:
            app: Optional FastAPI App für Auto-Instrumentierung

        Returns:
            True wenn erfolgreich initialisiert
        """
        if not self.enabled:
            logger.info("tracing_disabled")
            return False

        if not OPENTELEMETRY_AVAILABLE:
            logger.warning(
                "opentelemetry_not_available",
                hint="pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp"
            )
            return False

        if self._initialized:
            return True

        try:
            # Resource mit Service-Informationen
            resource = Resource.create({
                SERVICE_NAME: self.service_name,
                SERVICE_VERSION: self.service_version,
                "deployment.environment": os.environ.get("ENVIRONMENT", "development"),
                "host.name": os.environ.get("HOSTNAME", "unknown"),
            })

            # Sampling-Konfiguration
            if self.sample_rate < 1.0:
                sampler = ParentBasedTraceIdRatio(self.sample_rate)
                logger.info("trace_sampling_configured", rate=self.sample_rate)
            else:
                sampler = ALWAYS_ON
                logger.info("trace_sampling_full", rate=1.0)

            # Tracer Provider erstellen
            self._provider = TracerProvider(
                resource=resource,
                sampler=sampler,
            )

            # OTLP Exporter
            try:
                otlp_exporter = OTLPSpanExporter(
                    endpoint=self.otlp_endpoint,
                    insecure=True  # Für lokale Entwicklung
                )
                self._provider.add_span_processor(
                    BatchSpanProcessor(otlp_exporter)
                )
                logger.info(
                    "otlp_exporter_configured",
                    endpoint=self.otlp_endpoint
                )
            except Exception as e:
                logger.warning(
                    "otlp_exporter_failed",
                    **safe_error_log(e),
                    hint="Jaeger/Collector nicht erreichbar?"
                )

            # Console Exporter (Debug)
            if self.console_export:
                self._provider.add_span_processor(
                    BatchSpanProcessor(ConsoleSpanExporter())
                )

            # Global Tracer Provider setzen
            trace.set_tracer_provider(self._provider)

            # Propagators für Context Propagation
            set_global_textmap(TraceContextTextMapPropagator())

            # Tracer holen
            self._tracer = trace.get_tracer(
                self.service_name,
                self.service_version
            )

            # Auto-Instrumentierung
            self._setup_auto_instrumentation(app)

            self._initialized = True
            logger.info(
                "tracing_initialized",
                service=self.service_name,
                endpoint=self.otlp_endpoint
            )
            return True

        except Exception as e:
            logger.exception("tracing_setup_failed", **safe_error_log(e))
            return False

    def _setup_auto_instrumentation(self, app: Optional[object]) -> None:
        """Konfiguriert Auto-Instrumentierung für Frameworks."""
        if not OPENTELEMETRY_AVAILABLE:
            return

        # FastAPI Instrumentierung
        if app is not None:
            try:
                FastAPIInstrumentor.instrument_app(
                    app,
                    excluded_urls="health,readiness,metrics"
                )
                logger.debug("fastapi_instrumented")
            except Exception as e:
                logger.warning("fastapi_instrumentation_failed", **safe_error_log(e))

        # HTTPX (async HTTP client)
        try:
            HTTPXClientInstrumentor().instrument()
            logger.debug("httpx_instrumented")
        except Exception as e:
            logger.warning("httpx_instrumentation_failed", **safe_error_log(e))

        # Redis
        try:
            RedisInstrumentor().instrument()
            logger.debug("redis_instrumented")
        except Exception as e:
            logger.warning("redis_instrumentation_failed", **safe_error_log(e))

        # Celery
        try:
            CeleryInstrumentor().instrument()
            logger.debug("celery_instrumented")
        except Exception as e:
            logger.warning("celery_instrumentation_failed", **safe_error_log(e))

    def instrument_sqlalchemy(self, engine: object) -> None:
        """Instrumentiert SQLAlchemy Engine.

        Args:
            engine: SQLAlchemy Engine Instance
        """
        if not OPENTELEMETRY_AVAILABLE or not self.enabled:
            return

        try:
            SQLAlchemyInstrumentor().instrument(engine=engine)
            logger.debug("sqlalchemy_instrumented")
        except Exception as e:
            logger.warning("sqlalchemy_instrumentation_failed", **safe_error_log(e))

    def get_tracer(self) -> Optional[object]:
        """Hole den Tracer.

        Returns:
            OpenTelemetry Tracer oder None
        """
        if not self._initialized or not OPENTELEMETRY_AVAILABLE:
            return None
        return self._tracer

    @contextmanager
    def span(
        self,
        name: str,
        kind: Optional[object] = None,
        attributes: Optional[Dict[str, Union[str, int, float, bool]]] = None
    ):
        """Context Manager für manuelles Span-Tracing.

        Args:
            name: Span Name
            kind: SpanKind (CLIENT, SERVER, INTERNAL, etc.)
            attributes: Zusätzliche Span-Attribute

        Yields:
            Span Instance
        """
        if not self._initialized or not OPENTELEMETRY_AVAILABLE or self._tracer is None:
            yield None
            return

        span_kind = kind or SpanKind.INTERNAL
        with self._tracer.start_as_current_span(
            name,
            kind=span_kind,
            attributes=attributes or {}
        ) as span:
            try:
                yield span
            except Exception as e:
                if span:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                raise

    def shutdown(self) -> None:
        """Beendet den Tracing Service."""
        if self._provider is not None:
            try:
                self._provider.shutdown()
                logger.info("tracing_shutdown")
            except Exception as e:
                logger.warning("tracing_shutdown_error", **safe_error_log(e))


# Globale Tracing Service Instance
_tracing_service: Optional[TracingService] = None


def get_tracing_service() -> TracingService:
    """Hole oder erstelle globale Tracing Service Instance."""
    global _tracing_service
    if _tracing_service is None:
        _tracing_service = TracingService()
    return _tracing_service


def trace_span(
    name: Optional[str] = None,
    kind: str = "internal",
    attributes: Optional[Dict[str, Union[str, int, float, bool]]] = None
) -> Callable[[F], F]:
    """Decorator für automatisches Span-Tracing.

    Args:
        name: Span Name (default: Funktionsname)
        kind: SpanKind (internal, client, server, producer, consumer)
        attributes: Statische Span-Attribute

    Returns:
        Decorated function

    Usage:
        @trace_span("process_ocr", kind="internal")
        async def process_document(doc_id: str):
            ...
    """
    def decorator(func: F) -> F:
        span_name = name or func.__name__

        # Kind mapping
        kind_map = {
            "internal": SpanKind.INTERNAL if OPENTELEMETRY_AVAILABLE else None,
            "client": SpanKind.CLIENT if OPENTELEMETRY_AVAILABLE else None,
            "server": SpanKind.SERVER if OPENTELEMETRY_AVAILABLE else None,
            "producer": SpanKind.PRODUCER if OPENTELEMETRY_AVAILABLE else None,
            "consumer": SpanKind.CONSUMER if OPENTELEMETRY_AVAILABLE else None,
        }
        span_kind = kind_map.get(kind)

        @functools.wraps(func)
        async def async_wrapper(*args: object, **kwargs: object) -> object:
            tracing = get_tracing_service()
            with tracing.span(span_name, kind=span_kind, attributes=attributes):
                return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args: object, **kwargs: object) -> object:
            tracing = get_tracing_service()
            with tracing.span(span_name, kind=span_kind, attributes=attributes):
                return func(*args, **kwargs)

        # Prüfe ob async
        if asyncio_iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    return decorator


def asyncio_iscoroutinefunction(func: Callable[..., object]) -> bool:
    """Prüft ob Funktion async ist (ohne asyncio Import)."""
    import asyncio
    return asyncio.iscoroutinefunction(func)


# OCR-spezifische Tracing Helfer
def set_ocr_span_attributes(
    span: Optional[object],
    document_id: str,
    backend: str,
    page_count: Optional[int] = None,
    confidence: Optional[float] = None,
    vram_used_gb: Optional[float] = None
) -> None:
    """Setzt OCR-spezifische Span Attribute.

    Args:
        span: OpenTelemetry Span
        document_id: Dokument ID
        backend: OCR Backend Name
        page_count: Anzahl Seiten
        confidence: OCR Confidence Score
        vram_used_gb: VRAM-Verbrauch in GB
    """
    if span is None:
        return

    try:
        span.set_attribute("ocr.document_id", document_id)
        span.set_attribute("ocr.backend", backend)

        if page_count is not None:
            span.set_attribute("ocr.page_count", page_count)
        if confidence is not None:
            span.set_attribute("ocr.confidence", confidence)
        if vram_used_gb is not None:
            span.set_attribute("gpu.vram_used_gb", vram_used_gb)
    except Exception:
        pass  # Tracing-Fehler bewusst ignorieren (Telemetrie darf die App nie stoeren)
