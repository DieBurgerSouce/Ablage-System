# -*- coding: utf-8 -*-
"""
Log Analytics Service.

Aggregiert und analysiert Logs für Monitoring und Alerting:
- Trend-Analyse für Error Rates
- Anomalie-Erkennung bei ungewoehnlichen Mustern
- Dashboard-Metriken für Grafana
- Retention-Policy-Management

Feinpoliert und durchdacht - Enterprise Log Analytics.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# ENUMS AND DATA CLASSES
# =============================================================================


class LogLevel(str, Enum):
    """Log-Level für Klassifizierung."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class TrendDirection(str, Enum):
    """Trend-Richtung für Metriken."""

    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"
    VOLATILE = "volatile"


@dataclass
class LogEntry:
    """Einzelner Log-Eintrag für Analyse."""

    timestamp: datetime
    level: LogLevel
    source: str
    message: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LogMetrics:
    """Aggregierte Log-Metriken."""

    total_entries: int = 0
    by_level: Dict[str, int] = field(default_factory=dict)
    by_source: Dict[str, int] = field(default_factory=dict)
    error_rate_percent: float = 0.0
    warning_rate_percent: float = 0.0
    entries_per_minute: float = 0.0


@dataclass
class TrendAnalysis:
    """Trend-Analyse-Ergebnis."""

    metric_name: str
    direction: TrendDirection
    current_value: float
    previous_value: float
    change_percent: float
    is_anomaly: bool = False
    anomaly_reason: Optional[str] = None


@dataclass
class LogHealthReport:
    """Gesamt-Report zur Log-Gesundheit."""

    timestamp: datetime
    period_minutes: int
    metrics: LogMetrics
    trends: List[TrendAnalysis]
    alerts: List[Dict[str, Any]]
    recommendations: List[str]


# =============================================================================
# LOG ANALYTICS SERVICE
# =============================================================================


class LogAnalyticsService:
    """
    Service für Log-Analyse und Monitoring.

    Features:
    - In-Memory Rolling Window für schnelle Analysen
    - Trend-Erkennung für Error/Warning Rates
    - Anomalie-Erkennung bei Spikes
    - Dashboard-kompatible Metriken
    """

    def __init__(
        self,
        window_size_minutes: int = 60,
        anomaly_threshold: float = 2.0,
    ) -> None:
        """
        Initialisiere Log Analytics Service.

        Args:
            window_size_minutes: Größe des Analyse-Fensters
            anomaly_threshold: Schwellwert für Anomalie-Erkennung (Standardabweichungen)
        """
        self.window_size_minutes = window_size_minutes
        self.anomaly_threshold = anomaly_threshold

        # In-Memory Rolling Window
        self._entries: List[LogEntry] = []
        self._max_entries = 100000  # Max Einträge im Memory

        # Historische Metriken für Trend-Analyse
        self._historical_metrics: List[Tuple[datetime, LogMetrics]] = []
        self._max_history = 24 * 60  # 24h bei Minutenaufloesung

        # Alert Thresholds
        self._error_rate_warning = 5.0  # %
        self._error_rate_critical = 10.0  # %
        self._warning_rate_critical = 20.0  # %

    def record_log(
        self,
        level: LogLevel,
        source: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Zeichnet einen Log-Eintrag auf.

        Args:
            level: Log-Level
            source: Quelle (Modul/Service)
            message: Log-Nachricht
            metadata: Zusätzliche Metadaten
        """
        entry = LogEntry(
            timestamp=datetime.now(timezone.utc),
            level=level,
            source=source,
            message=message,
            metadata=metadata or {},
        )

        self._entries.append(entry)

        # Pruning wenn Max erreicht
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries // 2:]

    def get_metrics(self, last_minutes: Optional[int] = None) -> LogMetrics:
        """
        Berechnet Log-Metriken für den angegebenen Zeitraum.

        Args:
            last_minutes: Zeitfenster in Minuten (None = alles)

        Returns:
            Aggregierte Log-Metriken
        """
        entries = self._get_entries_in_window(last_minutes)

        if not entries:
            return LogMetrics()

        # Aggregate by level
        by_level: Dict[str, int] = defaultdict(int)
        for entry in entries:
            by_level[entry.level.value] += 1

        # Aggregate by source
        by_source: Dict[str, int] = defaultdict(int)
        for entry in entries:
            by_source[entry.source] += 1

        total = len(entries)
        error_count = by_level.get(LogLevel.ERROR.value, 0) + by_level.get(LogLevel.CRITICAL.value, 0)
        warning_count = by_level.get(LogLevel.WARNING.value, 0)

        # Time-based metrics
        if entries:
            time_span = (entries[-1].timestamp - entries[0].timestamp).total_seconds()
            entries_per_minute = (total / (time_span / 60)) if time_span > 0 else 0
        else:
            entries_per_minute = 0

        return LogMetrics(
            total_entries=total,
            by_level=dict(by_level),
            by_source=dict(by_source),
            error_rate_percent=round((error_count / total * 100) if total > 0 else 0, 2),
            warning_rate_percent=round((warning_count / total * 100) if total > 0 else 0, 2),
            entries_per_minute=round(entries_per_minute, 2),
        )

    def analyze_trends(self) -> List[TrendAnalysis]:
        """
        Analysiert Trends in den Log-Metriken.

        Vergleicht aktuelle Periode mit vorheriger.

        Returns:
            Liste von Trend-Analysen
        """
        current_metrics = self.get_metrics(self.window_size_minutes)
        previous_metrics = self._get_previous_period_metrics()

        trends = []

        # Error Rate Trend
        trends.append(self._analyze_metric_trend(
            metric_name="Error Rate",
            current=current_metrics.error_rate_percent,
            previous=previous_metrics.error_rate_percent if previous_metrics else 0,
            critical_threshold=self._error_rate_critical,
        ))

        # Warning Rate Trend
        trends.append(self._analyze_metric_trend(
            metric_name="Warning Rate",
            current=current_metrics.warning_rate_percent,
            previous=previous_metrics.warning_rate_percent if previous_metrics else 0,
            critical_threshold=self._warning_rate_critical,
        ))

        # Entries per Minute Trend
        trends.append(self._analyze_metric_trend(
            metric_name="Durchsatz",
            current=current_metrics.entries_per_minute,
            previous=previous_metrics.entries_per_minute if previous_metrics else 0,
            critical_threshold=None,  # Kein kritischer Schwellwert
        ))

        return trends

    def _analyze_metric_trend(
        self,
        metric_name: str,
        current: float,
        previous: float,
        critical_threshold: Optional[float] = None,
    ) -> TrendAnalysis:
        """Analysiert Trend einer einzelnen Metrik."""
        # Change berechnen
        if previous > 0:
            change_percent = ((current - previous) / previous) * 100
        elif current > 0:
            change_percent = 100.0
        else:
            change_percent = 0.0

        # Richtung bestimmen
        if abs(change_percent) < 5:
            direction = TrendDirection.STABLE
        elif abs(change_percent) > 50:
            direction = TrendDirection.VOLATILE
        elif change_percent > 0:
            direction = TrendDirection.INCREASING
        else:
            direction = TrendDirection.DECREASING

        # Anomalie prüfen
        is_anomaly = False
        anomaly_reason = None

        if critical_threshold and current > critical_threshold:
            is_anomaly = True
            anomaly_reason = f"Wert {current:.1f}% überschreitet kritischen Schwellwert {critical_threshold:.1f}%"
        elif abs(change_percent) > 100 and current > previous:
            is_anomaly = True
            anomaly_reason = f"Starker Anstieg um {change_percent:.0f}% erkannt"

        return TrendAnalysis(
            metric_name=metric_name,
            direction=direction,
            current_value=round(current, 2),
            previous_value=round(previous, 2),
            change_percent=round(change_percent, 1),
            is_anomaly=is_anomaly,
            anomaly_reason=anomaly_reason,
        )

    def get_health_report(self) -> LogHealthReport:
        """
        Erstellt vollständigen Log-Health-Report.

        Returns:
            LogHealthReport mit Metriken, Trends und Empfehlungen
        """
        metrics = self.get_metrics(self.window_size_minutes)
        trends = self.analyze_trends()

        # Alerts generieren
        alerts = []
        recommendations = []

        # Error Rate Alert
        if metrics.error_rate_percent >= self._error_rate_critical:
            alerts.append({
                "severity": "critical",
                "type": "high_error_rate",
                "message": f"Kritische Error Rate: {metrics.error_rate_percent:.1f}%",
                "threshold": self._error_rate_critical,
                "current": metrics.error_rate_percent,
            })
            recommendations.append("Untersuche die Error-Logs sofort - kritische Fehlerrate")
        elif metrics.error_rate_percent >= self._error_rate_warning:
            alerts.append({
                "severity": "warning",
                "type": "elevated_error_rate",
                "message": f"Erhöhte Error Rate: {metrics.error_rate_percent:.1f}%",
                "threshold": self._error_rate_warning,
                "current": metrics.error_rate_percent,
            })
            recommendations.append("Prüfe Error-Logs auf wiederkehrende Probleme")

        # Warning Rate Alert
        if metrics.warning_rate_percent >= self._warning_rate_critical:
            alerts.append({
                "severity": "warning",
                "type": "high_warning_rate",
                "message": f"Hohe Warning Rate: {metrics.warning_rate_percent:.1f}%",
                "threshold": self._warning_rate_critical,
                "current": metrics.warning_rate_percent,
            })
            recommendations.append("Viele Warnings deuten auf Konfigurationsprobleme hin")

        # Anomalie Alerts
        for trend in trends:
            if trend.is_anomaly:
                alerts.append({
                    "severity": "warning",
                    "type": "anomaly",
                    "metric": trend.metric_name,
                    "message": trend.anomaly_reason,
                })

        # Allgemeine Empfehlungen
        if not recommendations:
            if metrics.error_rate_percent < 1:
                recommendations.append("System-Logs zeigen gesunde Fehlerraten")
            recommendations.append("Regelmäßige Log-Überprüfung empfohlen")

        return LogHealthReport(
            timestamp=datetime.now(timezone.utc),
            period_minutes=self.window_size_minutes,
            metrics=metrics,
            trends=trends,
            alerts=alerts,
            recommendations=recommendations,
        )

    def get_top_errors(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Gibt die häufigsten Errors zurück.

        Args:
            limit: Anzahl der Top-Errors

        Returns:
            Liste der häufigsten Errors
        """
        entries = self._get_entries_in_window(self.window_size_minutes)
        error_entries = [
            e for e in entries
            if e.level in (LogLevel.ERROR, LogLevel.CRITICAL)
        ]

        # Group by message (vereinfacht)
        error_counts: Dict[str, int] = defaultdict(int)
        error_examples: Dict[str, LogEntry] = {}

        for entry in error_entries:
            # Normalisiere Message für Gruppierung
            key = f"{entry.source}:{entry.message[:100]}"
            error_counts[key] += 1
            if key not in error_examples:
                error_examples[key] = entry

        # Sortieren nach Count
        sorted_errors = sorted(
            error_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:limit]

        return [
            {
                "message": error_examples[key].message,
                "source": error_examples[key].source,
                "level": error_examples[key].level.value,
                "count": count,
                "last_occurrence": error_examples[key].timestamp.isoformat(),
            }
            for key, count in sorted_errors
        ]

    def get_log_volume_by_time(
        self,
        interval_minutes: int = 5,
        periods: int = 12,
    ) -> List[Dict[str, Any]]:
        """
        Gibt Log-Volumen nach Zeit zurück (für Charts).

        Args:
            interval_minutes: Intervall-Größe
            periods: Anzahl der Perioden

        Returns:
            Liste mit Zeitreihen-Daten
        """
        now = datetime.now(timezone.utc)
        result = []

        for i in range(periods - 1, -1, -1):
            period_end = now - timedelta(minutes=i * interval_minutes)
            period_start = period_end - timedelta(minutes=interval_minutes)

            entries = [
                e for e in self._entries
                if period_start <= e.timestamp < period_end
            ]

            by_level = defaultdict(int)
            for entry in entries:
                by_level[entry.level.value] += 1

            result.append({
                "timestamp": period_end.isoformat(),
                "total": len(entries),
                "by_level": dict(by_level),
            })

        return result

    def get_source_statistics(self) -> List[Dict[str, Any]]:
        """
        Gibt Statistiken nach Log-Quelle zurück.

        Returns:
            Liste mit Source-Statistiken
        """
        entries = self._get_entries_in_window(self.window_size_minutes)

        source_stats: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for entry in entries:
            source_stats[entry.source]["total"] += 1
            source_stats[entry.source][entry.level.value] += 1

        result = []
        for source, stats in sorted(source_stats.items(), key=lambda x: x[1]["total"], reverse=True):
            total = stats["total"]
            result.append({
                "source": source,
                "total": total,
                "error_count": stats.get(LogLevel.ERROR.value, 0) + stats.get(LogLevel.CRITICAL.value, 0),
                "warning_count": stats.get(LogLevel.WARNING.value, 0),
                "error_rate_percent": round(
                    (stats.get(LogLevel.ERROR.value, 0) + stats.get(LogLevel.CRITICAL.value, 0)) / total * 100
                    if total > 0 else 0, 1
                ),
            })

        return result

    def _get_entries_in_window(self, minutes: Optional[int] = None) -> List[LogEntry]:
        """Holt Einträge im Zeitfenster."""
        if minutes is None:
            return self._entries

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        return [e for e in self._entries if e.timestamp >= cutoff]

    def _get_previous_period_metrics(self) -> Optional[LogMetrics]:
        """Holt Metriken der vorherigen Periode aus Historie."""
        if len(self._historical_metrics) < 2:
            return None
        return self._historical_metrics[-2][1]

    def store_metrics_snapshot(self) -> None:
        """Speichert aktuellen Metriken-Snapshot für Historie."""
        metrics = self.get_metrics(self.window_size_minutes)
        self._historical_metrics.append((datetime.now(timezone.utc), metrics))

        # Pruning
        if len(self._historical_metrics) > self._max_history:
            self._historical_metrics = self._historical_metrics[-self._max_history:]

    def get_dashboard_data(self) -> Dict[str, Any]:
        """
        Gibt alle Daten für Dashboard zurück.

        Returns:
            Dictionary mit allen Dashboard-relevanten Daten
        """
        report = self.get_health_report()

        return {
            "timestamp": report.timestamp.isoformat(),
            "period_minutes": report.period_minutes,
            "summary": {
                "total_entries": report.metrics.total_entries,
                "error_rate_percent": report.metrics.error_rate_percent,
                "warning_rate_percent": report.metrics.warning_rate_percent,
                "entries_per_minute": report.metrics.entries_per_minute,
            },
            "by_level": report.metrics.by_level,
            "trends": [
                {
                    "metric": t.metric_name,
                    "direction": t.direction.value,
                    "current": t.current_value,
                    "previous": t.previous_value,
                    "change_percent": t.change_percent,
                    "is_anomaly": t.is_anomaly,
                }
                for t in report.trends
            ],
            "alerts": report.alerts,
            "recommendations": report.recommendations,
            "top_errors": self.get_top_errors(5),
            "volume_timeline": self.get_log_volume_by_time(),
            "source_stats": self.get_source_statistics()[:10],
        }


# =============================================================================
# SINGLETON ACCESS
# =============================================================================


_log_analytics_service: Optional[LogAnalyticsService] = None


def get_log_analytics_service() -> LogAnalyticsService:
    """Gibt LogAnalyticsService-Instanz zurück."""
    global _log_analytics_service
    if _log_analytics_service is None:
        _log_analytics_service = LogAnalyticsService()
    return _log_analytics_service
