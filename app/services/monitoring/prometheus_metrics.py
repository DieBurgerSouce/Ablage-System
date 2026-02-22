# -*- coding: utf-8 -*-
"""
Prometheus Metriken fuer OCR Self-Learning Pipeline.

Exponiert Metriken fuer das Self-Learning Feedback-Loop Monitoring:
- Korrektur-Zaehler (nach Feld, Backend, Entity)
- Template-Erstellung und -Updates
- Template-Deaktivierung bei hoher Korrekturrate
- Backend-Auswahl-Gewichte
- Korrektur-Queue-Laenge
- Genauigkeit Vorher/Nachher

Feinpoliert und durchdacht - Enterprise OCR Self-Learning Monitoring.
"""

from prometheus_client import Counter, Gauge, Histogram


# =============================================================================
# OCR KORREKTUR METRIKEN
# =============================================================================

ocr_corrections_total = Counter(
    "ocr_corrections_total",
    "Gesamtzahl OCR-Korrekturen",
    ["field_name", "backend", "company_id"],
)

ocr_correction_queue_length = Gauge(
    "ocr_correction_queue_length",
    "Aktuelle Laenge der Korrektur-Queue",
    [],
)

ocr_feedback_processing_duration_seconds = Histogram(
    "ocr_feedback_processing_duration_seconds",
    "Dauer der Feedback-Verarbeitung in Sekunden",
    ["task_name"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
)


# =============================================================================
# TEMPLATE METRIKEN
# =============================================================================

ocr_templates_created_total = Counter(
    "ocr_templates_created_total",
    "Gesamtzahl auto-generierter Templates",
    ["company_id"],
)

ocr_templates_updated_total = Counter(
    "ocr_templates_updated_total",
    "Template-Updates aus Korrekturen",
    ["entity_id"],
)

ocr_templates_deactivated_total = Counter(
    "ocr_templates_deactivated_total",
    "Deaktivierte Templates wegen hoher Korrekturrate",
    [],
)

ocr_template_correction_rate = Gauge(
    "ocr_template_correction_rate",
    "Korrekturrate pro Template",
    ["template_id", "entity_id"],
)


# =============================================================================
# BACKEND-GEWICHTE METRIKEN
# =============================================================================

ocr_backend_weight = Gauge(
    "ocr_backend_weight",
    "Backend-Auswahl-Gewicht (1.0=perfekt, 0.1=schlecht)",
    ["backend", "field_name"],
)


# =============================================================================
# GENAUIGKEITS-METRIKEN (VORHER/NACHHER)
# =============================================================================

ocr_learning_accuracy_before = Gauge(
    "ocr_learning_accuracy_before",
    "OCR-Genauigkeit vor Korrekturen (Baseline)",
    ["backend", "field_type"],
)

ocr_learning_accuracy_after = Gauge(
    "ocr_learning_accuracy_after",
    "OCR-Genauigkeit nach Self-Learning Verbesserungen",
    ["backend", "field_type"],
)
