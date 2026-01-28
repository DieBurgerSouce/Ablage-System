"""
Zero-Touch OCR Prometheus Metrics.

Metriken fuer Monitoring und Observability des Zero-Touch Processing Systems.
"""

from prometheus_client import Counter, Histogram, Gauge


# =============================================================================
# Counters
# =============================================================================

ZERO_TOUCH_PROCESSED = Counter(
    "zero_touch_processed_total",
    "Total number of documents processed by zero-touch system",
    ["result", "type"],
)
"""
Counter fuer verarbeitete Dokumente.

Labels:
- result: success, failed, manual_review_required
- type: invoice, contract, delivery_note, order, offer, other
"""


# =============================================================================
# Gauges
# =============================================================================

ZERO_TOUCH_AUTO_RATE = Gauge(
    "zero_touch_auto_rate",
    "Percentage of documents auto-processed without manual intervention",
)
"""
Gauge fuer Auto-Processing-Rate (0.0 - 1.0).
Wird regelmaessig aktualisiert basierend auf letzten N Dokumenten.
"""


# =============================================================================
# Histograms
# =============================================================================

ZERO_TOUCH_CONFIDENCE = Histogram(
    "zero_touch_confidence",
    "Distribution of overall confidence scores",
    buckets=[0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 1.0],
)
"""
Histogram fuer Confidence-Score-Verteilung.
Buckets optimiert fuer Schwellwert-Analyse (typischer Threshold: 0.90).
"""

ZERO_TOUCH_DURATION = Histogram(
    "zero_touch_duration_ms",
    "Processing duration in milliseconds",
    buckets=[100, 500, 1000, 2000, 5000, 10000],
)
"""
Histogram fuer Verarbeitungsdauer in Millisekunden.
Umfasst gesamte Zero-Touch-Pipeline von OCR-Completion bis Business-Object-Creation.
"""


# =============================================================================
# Helper Functions
# =============================================================================

def record_processing(
    result: str,
    doc_type: str,
    confidence: float,
    duration_ms: int,
) -> None:
    """
    Erfasst Metriken fuer eine abgeschlossene Verarbeitung.

    Args:
        result: Ergebnis (success, failed, manual_review_required)
        doc_type: Dokumententyp (invoice, contract, etc.)
        confidence: Overall Confidence Score (0.0 - 1.0)
        duration_ms: Verarbeitungsdauer in Millisekunden
    """
    ZERO_TOUCH_PROCESSED.labels(result=result, type=doc_type).inc()
    ZERO_TOUCH_CONFIDENCE.observe(confidence)
    ZERO_TOUCH_DURATION.observe(duration_ms)


def update_auto_rate(auto_rate: float) -> None:
    """
    Aktualisiert die Auto-Processing-Rate.

    Args:
        auto_rate: Rate zwischen 0.0 und 1.0
    """
    ZERO_TOUCH_AUTO_RATE.set(auto_rate)
