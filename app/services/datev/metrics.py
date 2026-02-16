# -*- coding: utf-8 -*-
"""
DATEV Prometheus Metriken Service.

Stellt Prometheus-kompatible Metriken für DATEV-Operationen bereit:
- datev_exports_total: Anzahl der Exports nach Status
- datev_export_duration_seconds: Export-Dauer
- datev_export_documents_total: Exportierte Dokumente
- datev_config_count: Anzahl aktiver Konfigurationen

Feinpoliert und durchdacht - Enterprise Monitoring.
"""

import time
from contextlib import contextmanager
from typing import Generator, Optional

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)


# =============================================================================
# DATEV METRICS REGISTRY
# =============================================================================

# Separate Registry für DATEV-Metriken (optional: kann auch default Registry nutzen)
# Wir nutzen die globale Default-Registry für Integration mit /metrics Endpoint

# Export Counter
datev_exports_total = Counter(
    "datev_exports_total",
    "Anzahl DATEV-Buchungsstapel-Exporte",
    labelnames=["status", "kontenrahmen"],
)

# Export Duration Histogram
# Buckets: 1s, 2.5s, 5s, 10s, 25s, 50s, 100s, 250s, 500s
datev_export_duration_seconds = Histogram(
    "datev_export_duration_seconds",
    "Dauer der DATEV-Export-Verarbeitung in Sekunden",
    labelnames=["kontenrahmen"],
    buckets=(1.0, 2.5, 5.0, 10.0, 25.0, 50.0, 100.0, 250.0, 500.0),
)

# Documents per Export Counter
datev_export_documents_total = Counter(
    "datev_export_documents_total",
    "Anzahl exportierter Dokumente",
    labelnames=["status", "kontenrahmen"],
)

# Configuration Gauge
datev_config_count = Gauge(
    "datev_config_count",
    "Anzahl aktiver DATEV-Konfigurationen",
    labelnames=["kontenrahmen"],
)

# Vendor Mappings Gauge
datev_vendor_mappings_count = Gauge(
    "datev_vendor_mappings_count",
    "Anzahl aktiver Vendor-Mappings",
)

# Export Errors Counter
datev_export_errors_total = Counter(
    "datev_export_errors_total",
    "Anzahl fehlgeschlagener DATEV-Exporte",
    labelnames=["error_type"],
)

# Rate Limit Counter
datev_rate_limit_hits_total = Counter(
    "datev_rate_limit_hits_total",
    "Anzahl Rate-Limit-Überschreitungen für DATEV-Exporte",
)


# =============================================================================
# METRICS SERVICE CLASS
# =============================================================================

class DATEVMetricsService:
    """
    Service für DATEV-spezifische Prometheus-Metriken.

    Singleton-Pattern für thread-safe globalen Zugriff.
    """

    _instance: Optional["DATEVMetricsService"] = None

    def __new__(cls) -> "DATEVMetricsService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def record_export(
        self,
        status: str,
        kontenrahmen: str,
        document_count: int,
        duration_seconds: float,
    ) -> None:
        """
        Zeichnet einen abgeschlossenen Export auf.

        Args:
            status: "success", "partial", "failed"
            kontenrahmen: "SKR03" oder "SKR04"
            document_count: Anzahl exportierter Dokumente
            duration_seconds: Dauer der Export-Verarbeitung
        """
        # Export zaehlen
        datev_exports_total.labels(
            status=status,
            kontenrahmen=kontenrahmen,
        ).inc()

        # Dokumente zaehlen
        datev_export_documents_total.labels(
            status=status,
            kontenrahmen=kontenrahmen,
        ).inc(document_count)

        # Dauer aufzeichnen
        datev_export_duration_seconds.labels(
            kontenrahmen=kontenrahmen,
        ).observe(duration_seconds)

    def record_export_error(self, error_type: str) -> None:
        """
        Zeichnet einen Export-Fehler auf.

        Args:
            error_type: Fehlertyp (z.B. "validation", "io", "database", "timeout")
        """
        datev_export_errors_total.labels(error_type=error_type).inc()

    def record_rate_limit_hit(self) -> None:
        """Zeichnet eine Rate-Limit-Überschreitung auf."""
        datev_rate_limit_hits_total.inc()

    def update_config_count(self, skr03_count: int, skr04_count: int) -> None:
        """
        Aktualisiert die Anzahl aktiver Konfigurationen.

        Args:
            skr03_count: Anzahl SKR03-Konfigurationen
            skr04_count: Anzahl SKR04-Konfigurationen
        """
        datev_config_count.labels(kontenrahmen="SKR03").set(skr03_count)
        datev_config_count.labels(kontenrahmen="SKR04").set(skr04_count)

    def update_vendor_mappings_count(self, count: int) -> None:
        """
        Aktualisiert die Anzahl aktiver Vendor-Mappings.

        Args:
            count: Anzahl der Vendor-Mappings
        """
        datev_vendor_mappings_count.set(count)

    @contextmanager
    def track_export_duration(self, kontenrahmen: str) -> Generator[None, None, None]:
        """
        Context Manager zum Tracken der Export-Dauer.

        Usage:
            with metrics.track_export_duration("SKR03"):
                # Export-Logik
                pass

        Args:
            kontenrahmen: "SKR03" oder "SKR04"
        """
        start_time = time.perf_counter()
        try:
            yield
        finally:
            duration = time.perf_counter() - start_time
            datev_export_duration_seconds.labels(
                kontenrahmen=kontenrahmen,
            ).observe(duration)

    def get_metrics(self) -> bytes:
        """
        Gibt alle DATEV-Metriken im Prometheus-Format zurück.

        Returns:
            Prometheus-formatierte Metriken als Bytes
        """
        return generate_latest()

    def get_content_type(self) -> str:
        """
        Gibt den Content-Type für Prometheus-Metriken zurück.

        Returns:
            Content-Type String
        """
        return CONTENT_TYPE_LATEST

    def get_summary(self) -> dict:
        """
        Gibt eine JSON-Zusammenfassung der DATEV-Metriken zurück.

        Returns:
            Dictionary mit Metriken-Zusammenfassung
        """
        from datetime import datetime, timezone

        # Sammle aktuelle Werte aus den Metriken
        # Hinweis: Dies ist eine vereinfachte Darstellung
        # Die echten Werte kommen aus dem Prometheus Registry

        return {
            "zeitstempel": datetime.now(timezone.utc).isoformat(),
            "metriken": {
                "datev_exports_total": "Counter - Anzahl Exports nach Status/Kontenrahmen",
                "datev_export_duration_seconds": "Histogram - Export-Dauer",
                "datev_export_documents_total": "Counter - Exportierte Dokumente",
                "datev_config_count": "Gauge - Aktive Konfigurationen",
                "datev_vendor_mappings_count": "Gauge - Vendor-Mappings",
                "datev_export_errors_total": "Counter - Export-Fehler nach Typ",
                "datev_rate_limit_hits_total": "Counter - Rate-Limit-Treffer",
            },
            "prometheus_endpoint": "/api/v1/metrics/datev",
            "hinweis": "Nutze Prometheus-Endpoint für aktuelle Werte",
        }


# =============================================================================
# SINGLETON ACCESSOR
# =============================================================================

_metrics_service: Optional[DATEVMetricsService] = None


def get_datev_metrics_service() -> DATEVMetricsService:
    """
    Gibt die Singleton-Instanz des DATEV Metrics Service zurück.

    Returns:
        DATEVMetricsService Instanz
    """
    global _metrics_service
    if _metrics_service is None:
        _metrics_service = DATEVMetricsService()
    return _metrics_service
