# -*- coding: utf-8 -*-
"""
Backend Quality Report Service für Ablage-System OCR.

Generiert detaillierte Qualitätsberichte pro OCR-Backend mit:
- Per-Backend Fehleranalyse und Schwachstellen-Erkennung
- Dokumenttyp-spezifische Performance-Metriken
- Umlaut-Genauigkeits-Tracking
- Retraining-Empfehlungen basierend auf Fehlermustern
- Vergleichsanalyse zwischen Backends

Feinpoliert und durchdacht - Enterprise-grade Quality Reporting.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum
from uuid import UUID
import statistics

from sqlalchemy import select, and_, func, case, desc
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.models import (
    OCRTrainingSample,
    OCRBackendBenchmark,
    OCRCorrection,
    OCRDocumentOutput,
    TrainingSampleStatus,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Types und Enums
# =============================================================================

class WeaknessCategory(str, Enum):
    """Kategorie der Backend-Schwaeche."""
    UMLAUT = "umlaut"
    FRAKTUR = "fraktur"
    TABLES = "tables"
    HANDWRITING = "handwriting"
    LOW_QUALITY = "low_quality"
    COMPLEX_LAYOUT = "complex_layout"
    SPECIAL_CHARS = "special_chars"
    NUMBERS = "numbers"
    DATES = "dates"
    CURRENCY = "currency"


class RetrainingPriority(str, Enum):
    """Priorität für Retraining."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class ErrorPattern:
    """Ein erkanntes Fehlermuster."""
    pattern_type: str
    description: str
    occurrence_count: int
    affected_samples: int
    example_errors: List[Dict[str, str]] = field(default_factory=list)
    severity: float = 0.0  # 0-1


@dataclass
class WeaknessPattern:
    """Erkannte Schwaeche eines Backends."""
    category: WeaknessCategory
    description: str
    severity: float  # 0-1
    affected_sample_count: int
    affected_sample_percentage: float
    example_sample_ids: List[str] = field(default_factory=list)
    recommended_action: str = ""


@dataclass
class PerformanceMetrics:
    """Performance-Metriken eines Backends."""
    avg_cer: float
    avg_wer: float
    avg_umlaut_accuracy: float
    avg_processing_time_ms: float
    p50_cer: float
    p90_cer: float
    p95_cer: float
    p99_cer: float
    total_samples: int
    verified_samples: int
    failed_samples: int


@dataclass
class DocumentTypePerformance:
    """Performance pro Dokumenttyp."""
    document_type: str
    sample_count: int
    avg_cer: float
    avg_wer: float
    avg_umlaut_accuracy: float
    is_weakness: bool = False


@dataclass
class RetrainingRecommendation:
    """Empfehlung für Retraining."""
    priority: RetrainingPriority
    focus_area: str
    description: str
    estimated_improvement: str
    sample_ids_for_training: List[str] = field(default_factory=list)
    required_samples: int = 0


@dataclass
class BackendQualityReport:
    """Vollständiger Qualitätsbericht für ein Backend."""
    backend_name: str
    report_date: datetime
    performance: PerformanceMetrics
    weaknesses: List[WeaknessPattern]
    error_patterns: List[ErrorPattern]
    document_type_performance: List[DocumentTypePerformance]
    retraining_recommendations: List[RetrainingRecommendation]
    overall_quality_score: float  # 0-100
    trend_direction: str  # "improving", "stable", "degrading"
    comparison_to_best: Dict[str, float] = field(default_factory=dict)


@dataclass
class BackendComparisonReport:
    """Vergleichsbericht zwischen allen Backends."""
    report_date: datetime
    backends: List[str]
    best_overall: str
    best_for_umlauts: str
    best_for_tables: str
    best_for_speed: str
    per_backend_scores: Dict[str, float] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)


# =============================================================================
# Service-Klasse
# =============================================================================

class BackendQualityReportService:
    """
    Service für Backend-Qualitätsberichte.

    Features:
    - Per-Backend Qualitätsanalyse
    - Schwachstellen-Erkennung
    - Retraining-Empfehlungen
    - Backend-Vergleich
    """

    def __init__(self, db: AsyncSession):
        """Initialisiere mit Datenbank-Session."""
        self.db = db
        logger.info("backend_quality_report_service_initialized")

    # =========================================================================
    # REPORT GENERATION
    # =========================================================================

    async def generate_backend_report(
        self,
        backend_name: str,
        days: int = 30,
    ) -> BackendQualityReport:
        """
        Generiert einen vollständigen Qualitätsbericht für ein Backend.

        Args:
            backend_name: Name des Backends
            days: Zeitraum in Tagen

        Returns:
            Vollständiger Qualitätsbericht
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)

        # Performance-Metriken
        performance = await self._calculate_performance_metrics(backend_name, since)

        # Schwachstellen
        weaknesses = await self._identify_weaknesses(backend_name, since)

        # Fehlermuster
        error_patterns = await self._analyze_error_patterns(backend_name, since)

        # Dokumenttyp-Performance
        doc_type_perf = await self._analyze_document_type_performance(backend_name, since)

        # Retraining-Empfehlungen
        recommendations = await self._generate_retraining_recommendations(
            backend_name, weaknesses, error_patterns
        )

        # Gesamt-Score berechnen
        quality_score = self._calculate_quality_score(performance, weaknesses)

        # Trend ermitteln
        trend = await self._determine_trend(backend_name, days)

        # Vergleich mit bestem Backend
        comparison = await self._compare_to_best(backend_name)

        report = BackendQualityReport(
            backend_name=backend_name,
            report_date=datetime.now(timezone.utc),
            performance=performance,
            weaknesses=weaknesses,
            error_patterns=error_patterns,
            document_type_performance=doc_type_perf,
            retraining_recommendations=recommendations,
            overall_quality_score=quality_score,
            trend_direction=trend,
            comparison_to_best=comparison,
        )

        logger.info(
            "backend_report_generated",
            backend=backend_name,
            quality_score=quality_score,
            weaknesses=len(weaknesses),
        )

        return report

    async def generate_comparison_report(self) -> BackendComparisonReport:
        """
        Generiert einen Vergleichsbericht aller Backends.

        Returns:
            Vergleichsbericht
        """
        backends = ["deepseek-janus-pro", "got-ocr-2.0", "surya-gpu", "surya"]
        scores: Dict[str, float] = {}
        umlaut_scores: Dict[str, float] = {}
        speed_scores: Dict[str, float] = {}

        for backend in backends:
            try:
                report = await self.generate_backend_report(backend, days=30)
                scores[backend] = report.overall_quality_score
                umlaut_scores[backend] = report.performance.avg_umlaut_accuracy * 100
                speed_scores[backend] = 1000 / max(report.performance.avg_processing_time_ms, 1)
            except Exception as e:
                logger.warning(f"Could not generate report for {backend}: {e}")
                scores[backend] = 0
                umlaut_scores[backend] = 0
                speed_scores[backend] = 0

        # Beste Backends ermitteln
        best_overall = max(scores, key=scores.get) if scores else backends[0]
        best_umlauts = max(umlaut_scores, key=umlaut_scores.get) if umlaut_scores else backends[0]
        best_speed = max(speed_scores, key=speed_scores.get) if speed_scores else backends[0]

        # Empfehlungen generieren
        recommendations = self._generate_comparison_recommendations(
            scores, umlaut_scores, speed_scores
        )

        # Bestimme besten Backend für Tabellen (falls Daten vorhanden)
        best_for_tables = await self._get_best_backend_for_tables(backends, since)
        if not best_for_tables:
            best_for_tables = best_overall  # Fallback auf Overall

        return BackendComparisonReport(
            report_date=datetime.now(timezone.utc),
            backends=backends,
            best_overall=best_overall,
            best_for_umlauts=best_umlauts,
            best_for_tables=best_for_tables,
            best_for_speed=best_speed,
            per_backend_scores=scores,
            recommendations=recommendations,
        )

    async def _get_best_backend_for_tables(
        self,
        backends: List[str],
        since: datetime,
    ) -> Optional[str]:
        """Ermittelt das beste Backend für Tabellen-Erkennung."""
        best_backend = None
        best_score = -1.0

        for backend in backends:
            # Suche nach Tabellen-spezifischen Benchmarks
            table_query = select(
                func.avg(OCRBackendBenchmark.table_accuracy).label("avg_table"),
                func.count(OCRBackendBenchmark.id).label("count"),
            ).where(
                and_(
                    OCRBackendBenchmark.backend_name == backend,
                    OCRBackendBenchmark.processed_at >= since,
                    OCRBackendBenchmark.table_accuracy.isnot(None),
                )
            )
            result = await self.db.execute(table_query)
            row = result.first()

            if row and row.count and row.count > 0 and row.avg_table:
                avg_score = float(row.avg_table)
                if avg_score > best_score:
                    best_score = avg_score
                    best_backend = backend

        return best_backend

    # =========================================================================
    # PERFORMANCE METRICS
    # =========================================================================

    async def _calculate_performance_metrics(
        self,
        backend_name: str,
        since: datetime,
    ) -> PerformanceMetrics:
        """Berechnet Performance-Metriken für ein Backend."""
        # Aggregierte Statistiken
        stats_query = select(
            func.count(OCRBackendBenchmark.id).label("total"),
            func.avg(OCRBackendBenchmark.cer).label("avg_cer"),
            func.avg(OCRBackendBenchmark.wer).label("avg_wer"),
            func.avg(OCRBackendBenchmark.umlaut_accuracy).label("avg_umlaut"),
            func.avg(OCRBackendBenchmark.processing_time_ms).label("avg_time"),
        ).where(
            and_(
                OCRBackendBenchmark.backend_name == backend_name,
                OCRBackendBenchmark.processed_at >= since,
            )
        )

        result = await self.db.execute(stats_query)
        stats = result.first()

        # Percentiles berechnen
        cer_query = select(OCRBackendBenchmark.cer).where(
            and_(
                OCRBackendBenchmark.backend_name == backend_name,
                OCRBackendBenchmark.processed_at >= since,
                OCRBackendBenchmark.cer.isnot(None),
            )
        ).order_by(OCRBackendBenchmark.cer)

        cer_result = await self.db.execute(cer_query)
        cer_values = [r[0] for r in cer_result.fetchall()]

        p50 = p90 = p95 = p99 = 0.0
        if cer_values:
            n = len(cer_values)
            p50 = cer_values[int(n * 0.50)] if n > 0 else 0
            p90 = cer_values[int(n * 0.90)] if n > 0 else 0
            p95 = cer_values[int(n * 0.95)] if n > 0 else 0
            p99 = cer_values[int(n * 0.99)] if n > 0 else 0

        # Verifizierte Samples zaehlen
        verified_query = select(func.count(OCRBackendBenchmark.id)).where(
            and_(
                OCRBackendBenchmark.backend_name == backend_name,
                OCRBackendBenchmark.processed_at >= since,
                OCRBackendBenchmark.cer < 0.05,  # "Gut" = CER < 5%
            )
        )
        verified_result = await self.db.execute(verified_query)
        verified = verified_result.scalar() or 0

        # Failed Samples
        failed_query = select(func.count(OCRBackendBenchmark.id)).where(
            and_(
                OCRBackendBenchmark.backend_name == backend_name,
                OCRBackendBenchmark.processed_at >= since,
                OCRBackendBenchmark.cer >= 0.20,  # "Schlecht" = CER >= 20%
            )
        )
        failed_result = await self.db.execute(failed_query)
        failed = failed_result.scalar() or 0

        return PerformanceMetrics(
            avg_cer=float(stats.avg_cer or 0),
            avg_wer=float(stats.avg_wer or 0),
            avg_umlaut_accuracy=float(stats.avg_umlaut or 0),
            avg_processing_time_ms=float(stats.avg_time or 0),
            p50_cer=p50,
            p90_cer=p90,
            p95_cer=p95,
            p99_cer=p99,
            total_samples=stats.total or 0,
            verified_samples=verified,
            failed_samples=failed,
        )

    # =========================================================================
    # WEAKNESS IDENTIFICATION
    # =========================================================================

    async def _identify_weaknesses(
        self,
        backend_name: str,
        since: datetime,
    ) -> List[WeaknessPattern]:
        """Identifiziert Schwaechen eines Backends."""
        weaknesses: List[WeaknessPattern] = []

        # 1. Umlaut-Schwaeche prüfen
        umlaut_weakness = await self._check_umlaut_weakness(backend_name, since)
        if umlaut_weakness:
            weaknesses.append(umlaut_weakness)

        # 2. Fraktur-Schwaeche prüfen
        fraktur_weakness = await self._check_feature_weakness(
            backend_name, since, "has_fraktur", WeaknessCategory.FRAKTUR
        )
        if fraktur_weakness:
            weaknesses.append(fraktur_weakness)

        # 3. Tabellen-Schwaeche prüfen
        table_weakness = await self._check_feature_weakness(
            backend_name, since, "has_tables", WeaknessCategory.TABLES
        )
        if table_weakness:
            weaknesses.append(table_weakness)

        # 4. Handschrift-Schwaeche prüfen
        hw_weakness = await self._check_feature_weakness(
            backend_name, since, "has_handwriting", WeaknessCategory.HANDWRITING
        )
        if hw_weakness:
            weaknesses.append(hw_weakness)

        return sorted(weaknesses, key=lambda w: w.severity, reverse=True)

    async def _check_umlaut_weakness(
        self,
        backend_name: str,
        since: datetime,
    ) -> Optional[WeaknessPattern]:
        """Prüft auf Umlaut-Schwaeche."""
        # Samples mit Umlauten
        query = select(
            func.count(OCRBackendBenchmark.id).label("total"),
            func.avg(OCRBackendBenchmark.umlaut_accuracy).label("avg_acc"),
            func.count(case((OCRBackendBenchmark.umlaut_accuracy < 0.95, 1))).label("low_acc"),
        ).join(
            OCRTrainingSample,
            OCRBackendBenchmark.training_sample_id == OCRTrainingSample.id
        ).where(
            and_(
                OCRBackendBenchmark.backend_name == backend_name,
                OCRBackendBenchmark.processed_at >= since,
                OCRTrainingSample.has_umlauts == True,  # noqa: E712
            )
        )

        result = await self.db.execute(query)
        stats = result.first()

        if not stats or stats.total == 0:
            return None

        avg_acc = float(stats.avg_acc or 0)
        low_acc_count = stats.low_acc or 0
        low_acc_pct = low_acc_count / stats.total * 100

        # Schwaeche wenn Umlaut-Accuracy < 95% oder > 10% Low-Accuracy Samples
        if avg_acc < 0.95 or low_acc_pct > 10:
            severity = 1.0 - avg_acc  # Je niedriger Accuracy, desto höher Severity

            return WeaknessPattern(
                category=WeaknessCategory.UMLAUT,
                description=f"Umlaut-Genauigkeit bei {avg_acc*100:.1f}% (Ziel: 100%)",
                severity=severity,
                affected_sample_count=low_acc_count,
                affected_sample_percentage=low_acc_pct,
                recommended_action="Fokussiertes Retraining mit deutschen Umlaut-Woertern",
            )

        return None

    async def _check_feature_weakness(
        self,
        backend_name: str,
        since: datetime,
        feature_column: str,
        category: WeaknessCategory,
    ) -> Optional[WeaknessPattern]:
        """Prüft auf Feature-spezifische Schwaeche."""
        # Dynamischer Spaltenname
        feature_attr = getattr(OCRTrainingSample, feature_column, None)
        if feature_attr is None:
            return None

        # Vergleiche CER mit/ohne Feature
        with_feature_query = select(
            func.avg(OCRBackendBenchmark.cer).label("avg_cer"),
            func.count(OCRBackendBenchmark.id).label("count"),
        ).join(
            OCRTrainingSample,
            OCRBackendBenchmark.training_sample_id == OCRTrainingSample.id
        ).where(
            and_(
                OCRBackendBenchmark.backend_name == backend_name,
                OCRBackendBenchmark.processed_at >= since,
                feature_attr == True,  # noqa: E712
            )
        )

        without_feature_query = select(
            func.avg(OCRBackendBenchmark.cer).label("avg_cer"),
        ).join(
            OCRTrainingSample,
            OCRBackendBenchmark.training_sample_id == OCRTrainingSample.id
        ).where(
            and_(
                OCRBackendBenchmark.backend_name == backend_name,
                OCRBackendBenchmark.processed_at >= since,
                feature_attr == False,  # noqa: E712
            )
        )

        with_result = await self.db.execute(with_feature_query)
        without_result = await self.db.execute(without_feature_query)

        with_stats = with_result.first()
        without_stats = without_result.first()

        if not with_stats or not with_stats.count:
            return None

        with_cer = float(with_stats.avg_cer or 0)
        without_cer = float(without_stats.avg_cer or 0) if without_stats else 0

        # Schwaeche wenn CER mit Feature >50% höher als ohne
        if without_cer > 0 and with_cer > without_cer * 1.5:
            severity = min(1.0, (with_cer - without_cer) / without_cer)

            descriptions = {
                WeaknessCategory.FRAKTUR: "Frakturschrift-Erkennung",
                WeaknessCategory.TABLES: "Tabellen-Erkennung",
                WeaknessCategory.HANDWRITING: "Handschrift-Erkennung",
            }

            # Berechne Prozentsatz der betroffenen Samples
            total_query = select(func.count(OCRBackendBenchmark.id)).where(
                and_(
                    OCRBackendBenchmark.backend_name == backend_name,
                    OCRBackendBenchmark.processed_at >= since,
                )
            )
            total_result = await self.db.execute(total_query)
            total_count = total_result.scalar() or 1

            affected_percentage = round(with_stats.count / total_count * 100, 1)

            return WeaknessPattern(
                category=category,
                description=f"{descriptions.get(category, category.value)}: "
                           f"CER {with_cer*100:.1f}% vs {without_cer*100:.1f}% ohne",
                severity=severity,
                affected_sample_count=with_stats.count,
                affected_sample_percentage=affected_percentage,
                recommended_action=f"Training mit mehr {category.value}-Samples",
            )

        return None

    # =========================================================================
    # ERROR PATTERN ANALYSIS
    # =========================================================================

    async def _analyze_error_patterns(
        self,
        backend_name: str,
        since: datetime,
    ) -> List[ErrorPattern]:
        """Analysiert Fehlermuster aus Korrekturen."""
        patterns: List[ErrorPattern] = []

        # Lade Korrekturen für dieses Backend
        correction_query = select(OCRCorrection).where(
            and_(
                OCRCorrection.backend_used == backend_name,
                OCRCorrection.created_at >= since,
            )
        ).limit(1000)

        result = await self.db.execute(correction_query)
        corrections = result.scalars().all()

        if not corrections:
            return patterns

        # Gruppiere nach Korrekturtyp
        type_counts: Dict[str, int] = {}
        type_examples: Dict[str, List[Dict[str, str]]] = {}

        for corr in corrections:
            corr_type = corr.correction_type or "general"
            type_counts[corr_type] = type_counts.get(corr_type, 0) + 1

            if corr_type not in type_examples:
                type_examples[corr_type] = []

            if len(type_examples[corr_type]) < 3:
                type_examples[corr_type].append({
                    "original": corr.original_text[:50] if corr.original_text else "",
                    "corrected": corr.corrected_text[:50] if corr.corrected_text else "",
                })

        # Erstelle Pattern-Objekte
        total_corrections = len(corrections)
        for corr_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
            severity = count / total_corrections if total_corrections > 0 else 0

            patterns.append(ErrorPattern(
                pattern_type=corr_type,
                description=f"{corr_type.capitalize()}-Fehler",
                occurrence_count=count,
                affected_samples=count,  # Vereinfacht
                example_errors=type_examples.get(corr_type, []),
                severity=severity,
            ))

        return patterns[:10]  # Top 10 Patterns

    # =========================================================================
    # DOCUMENT TYPE ANALYSIS
    # =========================================================================

    async def _analyze_document_type_performance(
        self,
        backend_name: str,
        since: datetime,
    ) -> List[DocumentTypePerformance]:
        """Analysiert Performance pro Dokumenttyp."""
        query = select(
            OCRTrainingSample.document_type,
            func.count(OCRBackendBenchmark.id).label("count"),
            func.avg(OCRBackendBenchmark.cer).label("avg_cer"),
            func.avg(OCRBackendBenchmark.wer).label("avg_wer"),
            func.avg(OCRBackendBenchmark.umlaut_accuracy).label("avg_umlaut"),
        ).join(
            OCRTrainingSample,
            OCRBackendBenchmark.training_sample_id == OCRTrainingSample.id
        ).where(
            and_(
                OCRBackendBenchmark.backend_name == backend_name,
                OCRBackendBenchmark.processed_at >= since,
            )
        ).group_by(OCRTrainingSample.document_type)

        result = await self.db.execute(query)
        rows = result.fetchall()

        performances = []
        overall_cer = None

        for row in rows:
            doc_type = row.document_type or "unknown"
            avg_cer = float(row.avg_cer or 0)

            if overall_cer is None:
                overall_cer = avg_cer

            performances.append(DocumentTypePerformance(
                document_type=doc_type,
                sample_count=row.count,
                avg_cer=avg_cer,
                avg_wer=float(row.avg_wer or 0),
                avg_umlaut_accuracy=float(row.avg_umlaut or 0),
                is_weakness=avg_cer > (overall_cer * 1.5) if overall_cer else False,
            ))

        return sorted(performances, key=lambda p: p.avg_cer, reverse=True)

    # =========================================================================
    # RETRAINING RECOMMENDATIONS
    # =========================================================================

    async def _generate_retraining_recommendations(
        self,
        backend_name: str,
        weaknesses: List[WeaknessPattern],
        error_patterns: List[ErrorPattern],
    ) -> List[RetrainingRecommendation]:
        """Generiert Retraining-Empfehlungen."""
        recommendations: List[RetrainingRecommendation] = []

        # Basierend auf Schwaechen
        for weakness in weaknesses:
            priority = RetrainingPriority.HIGH if weakness.severity > 0.3 else RetrainingPriority.MEDIUM

            if weakness.category == WeaknessCategory.UMLAUT:
                recommendations.append(RetrainingRecommendation(
                    priority=RetrainingPriority.CRITICAL,
                    focus_area="Umlaut-Genauigkeit",
                    description="Training mit deutschen Umlaut-Woertern (ae, oe, ue, ss)",
                    estimated_improvement="Erwartete Verbesserung: +10-20% Umlaut-Accuracy",
                    required_samples=500,
                ))
            elif weakness.category == WeaknessCategory.FRAKTUR:
                recommendations.append(RetrainingRecommendation(
                    priority=priority,
                    focus_area="Frakturschrift",
                    description="Training mit historischen deutschen Dokumenten",
                    estimated_improvement="Erwartete Verbesserung: -5% CER bei Fraktur",
                    required_samples=200,
                ))
            elif weakness.category == WeaknessCategory.TABLES:
                recommendations.append(RetrainingRecommendation(
                    priority=priority,
                    focus_area="Tabellen-Erkennung",
                    description="Training mit tabellarischen Dokumenten",
                    estimated_improvement="Erwartete Verbesserung: Bessere Strukturerkennung",
                    required_samples=300,
                ))

        # Basierend auf Fehlermustern
        for pattern in error_patterns[:3]:
            if pattern.severity > 0.2:
                recommendations.append(RetrainingRecommendation(
                    priority=RetrainingPriority.MEDIUM,
                    focus_area=f"{pattern.pattern_type.capitalize()}-Fehler",
                    description=f"Reduzierung von {pattern.pattern_type}-Fehlern",
                    estimated_improvement=f"Reduzierung um {pattern.severity*50:.0f}%",
                    required_samples=100,
                ))

        return sorted(recommendations, key=lambda r: {
            RetrainingPriority.CRITICAL: 0,
            RetrainingPriority.HIGH: 1,
            RetrainingPriority.MEDIUM: 2,
            RetrainingPriority.LOW: 3,
        }.get(r.priority, 4))

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _calculate_quality_score(
        self,
        performance: PerformanceMetrics,
        weaknesses: List[WeaknessPattern],
    ) -> float:
        """Berechnet einen Gesamt-Qualitätsscore (0-100)."""
        # Basis-Score aus CER (invertiert)
        cer_score = max(0, 100 - performance.avg_cer * 200)

        # Umlaut-Bonus
        umlaut_bonus = performance.avg_umlaut_accuracy * 20

        # Schwaechen-Abzug
        weakness_penalty = sum(w.severity * 10 for w in weaknesses)

        score = cer_score + umlaut_bonus - weakness_penalty
        return max(0, min(100, score))

    async def _determine_trend(
        self,
        backend_name: str,
        days: int,
    ) -> str:
        """Ermittelt den Qualitätstrend."""
        # Vergleiche aktuelle Woche mit vorheriger
        now = datetime.now(timezone.utc)
        current_week_start = now - timedelta(days=7)
        previous_week_start = now - timedelta(days=14)

        current_query = select(func.avg(OCRBackendBenchmark.cer)).where(
            and_(
                OCRBackendBenchmark.backend_name == backend_name,
                OCRBackendBenchmark.processed_at >= current_week_start,
            )
        )

        previous_query = select(func.avg(OCRBackendBenchmark.cer)).where(
            and_(
                OCRBackendBenchmark.backend_name == backend_name,
                OCRBackendBenchmark.processed_at >= previous_week_start,
                OCRBackendBenchmark.processed_at < current_week_start,
            )
        )

        current_result = await self.db.execute(current_query)
        previous_result = await self.db.execute(previous_query)

        current_cer = current_result.scalar() or 0
        previous_cer = previous_result.scalar() or 0

        if previous_cer == 0:
            return "stable"

        change = (current_cer - previous_cer) / previous_cer

        if change < -0.05:
            return "improving"
        elif change > 0.05:
            return "degrading"
        return "stable"

    async def _compare_to_best(
        self,
        backend_name: str,
    ) -> Dict[str, float]:
        """Vergleicht mit dem besten Backend."""
        backends = ["deepseek-janus-pro", "got-ocr-2.0", "surya-gpu", "surya"]
        comparison: Dict[str, float] = {}

        # Lade CER für alle Backends
        for backend in backends:
            query = select(func.avg(OCRBackendBenchmark.cer)).where(
                OCRBackendBenchmark.backend_name == backend
            )
            result = await self.db.execute(query)
            cer = result.scalar() or 0
            comparison[backend] = float(cer)

        return comparison

    def _generate_comparison_recommendations(
        self,
        scores: Dict[str, float],
        umlaut_scores: Dict[str, float],
        speed_scores: Dict[str, float],
    ) -> List[str]:
        """Generiert Empfehlungen basierend auf Vergleich."""
        recommendations = []

        best_overall = max(scores, key=scores.get) if scores else None
        best_umlauts = max(umlaut_scores, key=umlaut_scores.get) if umlaut_scores else None

        if best_overall:
            recommendations.append(
                f"Verwenden Sie {best_overall} als Standard-Backend für beste Gesamtqualität"
            )

        if best_umlauts and best_umlauts != best_overall:
            recommendations.append(
                f"Für deutsche Dokumente mit Umlauten: {best_umlauts} bevorzugen"
            )

        # Check for significant gaps
        if scores:
            avg_score = sum(scores.values()) / len(scores)
            for backend, score in scores.items():
                if score < avg_score * 0.7:
                    recommendations.append(
                        f"{backend}: Retraining empfohlen (Score {score:.0f} unter Durchschnitt)"
                    )

        return recommendations


# =============================================================================
# Factory-Funktion
# =============================================================================

async def get_backend_quality_report_service(db: AsyncSession) -> BackendQualityReportService:
    """Factory-Funktion für den Service."""
    return BackendQualityReportService(db)
