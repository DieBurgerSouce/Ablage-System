# -*- coding: utf-8 -*-
"""
Business Metriken fuer Ablage-System OCR.

Erweiterte Prometheus-Metriken fuer:
- OCR-Verarbeitung (Zeichen, Konfidenz, Backend-Nutzung)
- Dokumenten-Workflow (Upload, Status, Typen)
- Backpressure und Queue-Status
- Model-Loading und GPU-Effizienz
- Fraktur-Erkennung und Spezialverarbeitung

Feinpoliert und durchdacht - Enterprise-grade Business Metriken.
"""

import time
from typing import Any, Dict, Optional
from contextlib import contextmanager

import structlog
from prometheus_client import Counter, Histogram, Gauge, Summary, Info

logger = structlog.get_logger(__name__)


# =============================================================================
# OCR METRIKEN
# =============================================================================

# OCR Verarbeitungen gesamt
ocr_processing_total = Counter(
    "ablage_ocr_processing_total",
    "Gesamtzahl OCR-Verarbeitungen",
    ["backend", "status", "document_type"]
)

# OCR Verarbeitungsdauer
ocr_processing_duration_seconds = Histogram(
    "ablage_ocr_processing_duration_seconds",
    "OCR-Verarbeitungsdauer in Sekunden",
    ["backend", "document_type"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0]
)

# Extrahierte Zeichen pro Dokument
ocr_characters_extracted = Histogram(
    "ablage_ocr_characters_extracted",
    "Anzahl extrahierter Zeichen pro Dokument",
    ["backend"],
    buckets=[100, 500, 1000, 5000, 10000, 50000, 100000, 500000]
)

# OCR Konfidenz-Score
ocr_confidence_score = Histogram(
    "ablage_ocr_confidence_score",
    "OCR Konfidenz-Score (0-1)",
    ["backend"],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99, 1.0]
)

# Backend-Auswahl
ocr_backend_selection_total = Counter(
    "ablage_ocr_backend_selection_total",
    "OCR Backend Auswahl nach Grund",
    ["backend", "selection_reason"]
)

# Zeichen pro Sekunde (Durchsatz)
ocr_characters_per_second = Gauge(
    "ablage_ocr_characters_per_second",
    "OCR Durchsatz: Zeichen pro Sekunde",
    ["backend"]
)

# Seiten verarbeitet
ocr_pages_processed_total = Counter(
    "ablage_ocr_pages_processed_total",
    "Gesamtzahl verarbeiteter Seiten",
    ["backend"]
)


# =============================================================================
# FRAKTUR / SPEZIALVERARBEITUNG
# =============================================================================

# Fraktur-Erkennung
ocr_fraktur_detected_total = Counter(
    "ablage_ocr_fraktur_detected_total",
    "Anzahl erkannter Fraktur-Dokumente",
    ["confidence_level"]  # high, medium, low
)

# Deutsche Umlaute Genauigkeit
ocr_umlaut_accuracy = Histogram(
    "ablage_ocr_umlaut_accuracy",
    "Umlaut-Erkennungsgenauigkeit (0-1)",
    ["backend"],
    buckets=[0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 0.99, 1.0]
)

# Postprocessing-Korrekturen
ocr_postprocessing_corrections = Counter(
    "ablage_ocr_postprocessing_corrections_total",
    "Anzahl Postprocessing-Korrekturen",
    ["correction_type"]  # umlaut, ligature, spelling, whitespace
)


# =============================================================================
# DOKUMENT-METRIKEN
# =============================================================================

# Dokumenten-Upload
documents_uploaded_total = Counter(
    "ablage_documents_uploaded_total",
    "Gesamtzahl hochgeladener Dokumente",
    ["file_type", "source"]  # source: api, web, batch
)

# Dokumenten-Groesse
document_size_bytes = Histogram(
    "ablage_document_size_bytes",
    "Dokumentengroesse in Bytes",
    ["file_type"],
    buckets=[10000, 100000, 1000000, 5000000, 10000000, 50000000, 100000000]
)

# Dokumenten-Seitenanzahl
document_page_count = Histogram(
    "ablage_document_page_count",
    "Seitenanzahl pro Dokument",
    ["file_type"],
    buckets=[1, 2, 5, 10, 20, 50, 100, 200, 500]
)

# Dokumenten-Status-Uebergaenge
document_status_transitions_total = Counter(
    "ablage_document_status_transitions_total",
    "Dokumenten-Status-Uebergaenge",
    ["from_status", "to_status"]
)

# Aktive Dokumente pro Status
documents_by_status = Gauge(
    "ablage_documents_by_status",
    "Anzahl Dokumente pro Status",
    ["status"]
)


# =============================================================================
# BACKPRESSURE METRIKEN
# =============================================================================

# Backpressure-Status
backpressure_status = Gauge(
    "ablage_backpressure_status",
    "Backpressure-Status (0=normal, 1=warning, 2=critical, 3=overloaded)"
)

# Queue-Laenge gesamt
backpressure_queue_length = Gauge(
    "ablage_backpressure_queue_length_total",
    "Gesamte Queue-Laenge ueber alle Queues"
)

# Abgelehnte Anfragen
backpressure_rejected_total = Counter(
    "ablage_backpressure_rejected_total",
    "Abgelehnte Anfragen wegen Ueberlast",
    ["priority", "reason"]
)

# Degradierte Anfragen (auf CPU-Backend)
backpressure_degraded_total = Counter(
    "ablage_backpressure_degraded_total",
    "Auf CPU-Backend degradierte Anfragen",
    ["original_backend", "fallback_backend"]
)


# =============================================================================
# MODEL-LOADING METRIKEN
# =============================================================================

# Model-Loading-Dauer
model_loading_duration_seconds = Histogram(
    "ablage_model_loading_duration_seconds",
    "Model-Ladedauer in Sekunden",
    ["model_name"],
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0]
)

# Model-Loading-Status
model_loading_status = Gauge(
    "ablage_model_loading_status",
    "Model-Loading-Status (0=pending, 1=loading, 2=loaded, 3=failed)",
    ["model_name"]
)

# Preloaded Models
models_preloaded_total = Gauge(
    "ablage_models_preloaded_total",
    "Anzahl vorgeladener Modelle"
)


# =============================================================================
# GPU-EFFIZIENZ METRIKEN
# =============================================================================

# GPU Batch Groesse
gpu_batch_size = Histogram(
    "ablage_gpu_batch_size",
    "GPU Batch-Groesse bei Verarbeitung",
    ["task_type"],
    buckets=[1, 2, 4, 8, 16, 32, 64]
)

# GPU Speicher-Effizienz
gpu_memory_efficiency = Gauge(
    "ablage_gpu_memory_efficiency",
    "GPU Speicher-Effizienz (genutzter/reservierter Speicher)"
)

# GPU Idle-Zeit
gpu_idle_seconds_total = Counter(
    "ablage_gpu_idle_seconds_total",
    "Kumulative GPU Idle-Zeit in Sekunden"
)


# =============================================================================
# HELPER FUNKTIONEN
# =============================================================================

def record_ocr_processing(
    backend: str,
    status: str,
    document_type: str,
    duration_seconds: float,
    characters_count: int,
    confidence: float,
    pages: int = 1
) -> None:
    """
    Zeichne OCR-Verarbeitung auf.

    Args:
        backend: OCR-Backend (deepseek, got_ocr, surya)
        status: Verarbeitungsstatus (success, failed, partial)
        document_type: Dokumenttyp (pdf, image, tiff)
        duration_seconds: Verarbeitungsdauer
        characters_count: Anzahl extrahierter Zeichen
        confidence: Konfidenz-Score (0-1)
        pages: Anzahl verarbeiteter Seiten
    """
    ocr_processing_total.labels(
        backend=backend,
        status=status,
        document_type=document_type
    ).inc()

    ocr_processing_duration_seconds.labels(
        backend=backend,
        document_type=document_type
    ).observe(duration_seconds)

    if characters_count > 0:
        ocr_characters_extracted.labels(backend=backend).observe(characters_count)

    if 0 <= confidence <= 1:
        ocr_confidence_score.labels(backend=backend).observe(confidence)

    if duration_seconds > 0:
        chars_per_sec = characters_count / duration_seconds
        ocr_characters_per_second.labels(backend=backend).set(chars_per_sec)

    ocr_pages_processed_total.labels(backend=backend).inc(pages)


def record_backend_selection(backend: str, reason: str) -> None:
    """
    Zeichne Backend-Auswahl auf.

    Args:
        backend: Ausgewaehltes Backend
        reason: Auswahlgrund (user_preference, auto_select, degraded, etc.)
    """
    ocr_backend_selection_total.labels(backend=backend, selection_reason=reason).inc()


def record_fraktur_detection(confidence_level: str) -> None:
    """
    Zeichne Fraktur-Erkennung auf.

    Args:
        confidence_level: Konfidenz-Level (high, medium, low)
    """
    ocr_fraktur_detected_total.labels(confidence_level=confidence_level).inc()


def record_postprocessing_correction(correction_type: str, count: int = 1) -> None:
    """
    Zeichne Postprocessing-Korrektur auf.

    Args:
        correction_type: Art der Korrektur
        count: Anzahl Korrekturen
    """
    ocr_postprocessing_corrections.labels(correction_type=correction_type).inc(count)


def record_document_upload(
    file_type: str,
    source: str,
    size_bytes: int,
    page_count: int = 1
) -> None:
    """
    Zeichne Dokumenten-Upload auf.

    Args:
        file_type: Dateityp (pdf, png, jpg, tiff)
        source: Upload-Quelle (api, web, batch)
        size_bytes: Dateigroesse
        page_count: Seitenanzahl
    """
    documents_uploaded_total.labels(file_type=file_type, source=source).inc()
    document_size_bytes.labels(file_type=file_type).observe(size_bytes)
    document_page_count.labels(file_type=file_type).observe(page_count)


def record_status_transition(from_status: str, to_status: str) -> None:
    """
    Zeichne Status-Uebergang auf.

    Args:
        from_status: Alter Status
        to_status: Neuer Status
    """
    document_status_transitions_total.labels(
        from_status=from_status,
        to_status=to_status
    ).inc()


def update_documents_by_status(status_counts: Dict[str, int]) -> None:
    """
    Aktualisiere Dokumenten-Zaehler pro Status.

    Args:
        status_counts: Dict mit Status -> Anzahl
    """
    for status, count in status_counts.items():
        documents_by_status.labels(status=status).set(count)


def update_backpressure_metrics(
    status_value: int,
    queue_length: int,
    rejected_count: int = 0,
    degraded_count: int = 0
) -> None:
    """
    Aktualisiere Backpressure-Metriken.

    Args:
        status_value: Status (0=normal, 1=warning, 2=critical, 3=overloaded)
        queue_length: Aktuelle Queue-Laenge
        rejected_count: Abgelehnte Anfragen (falls vorhanden)
        degraded_count: Degradierte Anfragen (falls vorhanden)
    """
    backpressure_status.set(status_value)
    backpressure_queue_length.set(queue_length)


def record_backpressure_rejection(priority: str, reason: str) -> None:
    """Zeichne abgelehnte Anfrage auf."""
    backpressure_rejected_total.labels(priority=priority, reason=reason).inc()


def record_backpressure_degradation(original: str, fallback: str) -> None:
    """Zeichne Backend-Degradierung auf."""
    backpressure_degraded_total.labels(
        original_backend=original,
        fallback_backend=fallback
    ).inc()


def record_model_loading(model_name: str, duration_seconds: float, success: bool) -> None:
    """
    Zeichne Model-Loading auf.

    Args:
        model_name: Name des Models
        duration_seconds: Ladedauer
        success: Ob Loading erfolgreich war
    """
    model_loading_duration_seconds.labels(model_name=model_name).observe(duration_seconds)
    # 2=loaded, 3=failed
    model_loading_status.labels(model_name=model_name).set(2 if success else 3)


def update_preloaded_models_count(count: int) -> None:
    """Aktualisiere Anzahl vorgeladener Modelle."""
    models_preloaded_total.set(count)


@contextmanager
def track_ocr_processing(
    backend: str,
    document_type: str = "unknown"
):
    """
    Context Manager zum Tracken von OCR-Verarbeitung.

    Usage:
        with track_ocr_processing("deepseek", "pdf") as tracker:
            result = process_document(doc)
            tracker.set_result(
                characters=len(result.text),
                confidence=result.confidence,
                pages=result.pages
            )

    Args:
        backend: OCR-Backend
        document_type: Dokumenttyp

    Yields:
        Tracker-Objekt mit set_result() Methode
    """
    class OCRTracker:
        def __init__(self):
            self.start_time = time.perf_counter()
            self.characters = 0
            self.confidence = 0.0
            self.pages = 1
            self.status = "success"

        def set_result(
            self,
            characters: int,
            confidence: float = 0.0,
            pages: int = 1
        ):
            self.characters = characters
            self.confidence = confidence
            self.pages = pages

        def set_failed(self):
            self.status = "failed"

    tracker = OCRTracker()

    try:
        yield tracker
    except Exception:
        tracker.set_failed()
        raise
    finally:
        duration = time.perf_counter() - tracker.start_time
        record_ocr_processing(
            backend=backend,
            status=tracker.status,
            document_type=document_type,
            duration_seconds=duration,
            characters_count=tracker.characters,
            confidence=tracker.confidence,
            pages=tracker.pages
        )


def get_metrics_summary() -> Dict[str, Any]:
    """
    Hole Zusammenfassung aller Business-Metriken.

    Returns:
        Dict mit Metriken-Uebersicht
    """
    return {
        "ocr": {
            "metrics_defined": 7,
            "includes": ["processing_total", "duration", "characters", "confidence", "backend_selection", "throughput", "pages"]
        },
        "fraktur": {
            "metrics_defined": 3,
            "includes": ["detection", "umlaut_accuracy", "postprocessing"]
        },
        "documents": {
            "metrics_defined": 5,
            "includes": ["uploads", "size", "pages", "status_transitions", "by_status"]
        },
        "backpressure": {
            "metrics_defined": 4,
            "includes": ["status", "queue_length", "rejected", "degraded"]
        },
        "model_loading": {
            "metrics_defined": 3,
            "includes": ["duration", "status", "preloaded_count"]
        },
        "gpu": {
            "metrics_defined": 3,
            "includes": ["batch_size", "memory_efficiency", "idle_time"]
        }
    }
