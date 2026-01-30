# -*- coding: utf-8 -*-
"""
Explainable Anomaly Detection Service.

Vision 2026 Q3: Erweiterte Anomalie-Erkennung mit detaillierten Erklaerungen.

Erweitert den bestehenden AnomalyDetectionService um:
- Detaillierte Erklaerungen pro Anomalie-Typ
- Kontextuelle Informationen (Vergleichswerte, Trends)
- Empfehlungen mit Priorisierung
- Historische Anomalie-Trends
- Feedback-Integration fuer Verbesserung

Feinpoliert und durchdacht - Deutsche Qualitaet.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import structlog
from prometheus_client import Counter, Histogram
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, BusinessEntity
from app.services.ai.anomaly_detection_service import (
    AnomalyDetectionService,
    AnomalyCheckResult,
    DetectedAnomaly,
    AnomalyType,
    AnomalySeverity,
    get_anomaly_detection_service,
)
from app.services.ai.extracted_data_wrapper import ExtractedData, get_extracted_data

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

EXPLAINABLE_ANOMALY_REQUESTS = Counter(
    "explainable_anomaly_requests_total",
    "Anzahl der erklaerbaren Anomalie-Analysen",
    ["anomaly_type"]
)

ANOMALY_FEEDBACK_RECEIVED = Counter(
    "anomaly_feedback_total",
    "Anzahl erhaltener Feedback-Eintraege",
    ["feedback_type"]  # confirmed, false_positive, unclear
)


# =============================================================================
# Datenstrukturen
# =============================================================================

class AnomalyExplanationLevel(str, Enum):
    """Detail-Level der Erklaerung."""
    BRIEF = "brief"      # Kurze Zusammenfassung
    DETAILED = "detailed"  # Vollstaendige Analyse
    EXPERT = "expert"    # Mit technischen Details


@dataclass
class ContextualComparison:
    """Kontextueller Vergleich fuer eine Anomalie."""
    metric_name: str
    current_value: str
    comparison_value: str
    comparison_type: str  # "average", "median", "last_month", "last_year"
    deviation_percent: float
    is_significant: bool


@dataclass
class AnomalyRecommendation:
    """Empfehlung zur Behandlung einer Anomalie."""
    priority: int  # 1=hoechste Prioritaet
    action: str
    reason: str
    expected_outcome: str
    effort_level: str  # "low", "medium", "high"


@dataclass
class AnomalyTrend:
    """Historischer Trend fuer einen Anomalie-Typ."""
    anomaly_type: AnomalyType
    occurrences_30d: int
    occurrences_90d: int
    trend_direction: str  # "increasing", "stable", "decreasing"
    typical_severity: AnomalySeverity


@dataclass
class ExplainedAnomaly:
    """Vollstaendig erklaerte Anomalie."""
    anomaly_type: AnomalyType
    severity: AnomalySeverity
    confidence: float
    title: str
    summary: str
    detailed_explanation: str
    context_comparisons: List[ContextualComparison]
    recommendations: List[AnomalyRecommendation]
    affected_fields: List[str]
    evidence: Dict[str, Any]
    historical_trend: Optional[AnomalyTrend]
    similar_cases_count: int
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExplainedAnomalyResult:
    """Ergebnis der erklaerbaren Anomalie-Analyse."""
    document_id: uuid.UUID
    anomalies: List[ExplainedAnomaly]
    overall_risk_score: float
    overall_explanation: str
    top_recommendations: List[AnomalyRecommendation]
    requires_immediate_action: bool
    processing_time_ms: int
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Anomalie-Erklaerungen Templates
# =============================================================================

ANOMALY_TEMPLATES: Dict[AnomalyType, Dict[str, str]] = {
    AnomalyType.HIGH_AMOUNT: {
        "title": "Ungewoehnlich hoher Betrag erkannt",
        "summary_template": "Der Betrag von {amount} EUR ist {factor}x hoeher als der historische Median von {median} EUR.",
        "detail_template": (
            "Bei der Analyse wurden ungewoehnlich hohe Betraege festgestellt. "
            "Der aktuelle Rechnungsbetrag liegt deutlich ueber den historischen Werten. "
            "Dies kann auf einen Preisanstieg, eine groessere Bestellung oder "
            "einen potenziellen Fehler hindeuten. "
            "Vergleichswerte: Median der letzten 12 Monate: {median} EUR, "
            "Maximum: {max} EUR, Durchschnitt: {avg} EUR."
        ),
    },
    AnomalyType.NEW_SUPPLIER_HIGH_VALUE: {
        "title": "Neuer Lieferant mit hohem Betrag",
        "summary_template": "Unbekannter Lieferant '{supplier}' mit Rechnung ueber {amount} EUR.",
        "detail_template": (
            "Eine Rechnung von einem bisher unbekannten Lieferanten wurde erkannt. "
            "Bei Erstbestellungen mit hohen Betraegen ist besondere Vorsicht geboten. "
            "Empfohlen wird die Verifizierung des Lieferanten vor Freigabe der Zahlung. "
            "Pruefen Sie: Handelsregistereintrag, Website, Referenzen."
        ),
    },
    AnomalyType.DUPLICATE_NUMBER: {
        "title": "Potenzielle Doppelrechnung erkannt",
        "summary_template": "Rechnungsnummer '{invoice_number}' existiert bereits ({count}x).",
        "detail_template": (
            "Eine Rechnung mit identischer Rechnungsnummer wurde bereits im System gefunden. "
            "Dies kann auf eine Doppelbuchung, eine korrigierte Rechnung (Storno/Gutschrift) "
            "oder einen Betrugsversuch hindeuten. "
            "Gefundene Duplikate: {duplicate_ids}. "
            "Bitte pruefen Sie die Dokumente manuell auf Unterschiede."
        ),
    },
    AnomalyType.UNUSUAL_PAYMENT_TERMS: {
        "title": "Unuebliches Zahlungsziel",
        "summary_template": "Zahlungsziel von {days} Tagen ist ungewoehnlich.",
        "detail_template": (
            "Das angegebene Zahlungsziel weicht stark von den ueblichen "
            "Geschaeftsbedingungen ab. Standard-Zahlungsziele liegen typischerweise "
            "bei 14-30 Tagen. Sehr lange Zahlungsziele koennen ein Hinweis auf "
            "besondere Vereinbarungen oder potenzielle Probleme sein. "
            "Bei sehr kurzen Fristen pruefen Sie auf Skonto-Moeglichkeiten."
        ),
    },
    AnomalyType.ROUND_AMOUNT: {
        "title": "Verdaechtig runder Betrag",
        "summary_template": "Betrag von {amount} EUR ist ungewoehnlich rund.",
        "detail_template": (
            "Exakt runde Betraege ohne Centbetraege sind bei geschaeftlichen "
            "Transaktionen selten und koennen auf Schaetzwerte, Pauschalen "
            "oder manipulierte Betraege hindeuten. "
            "Pruefen Sie ob Einzelpositionen auf der Rechnung vorhanden sind "
            "und ob diese den Gesamtbetrag rechnerisch ergeben."
        ),
    },
    AnomalyType.WEEKEND_INVOICE: {
        "title": "Rechnung am Wochenende datiert",
        "summary_template": "Rechnungsdatum liegt auf einem {day}.",
        "detail_template": (
            "Die Rechnung wurde auf ein Wochenende datiert, was bei den meisten "
            "Unternehmen unueblich ist. Dies kann auf eine manuelle Datumseingabe "
            "oder automatisierte Systeme hindeuten. "
            "Bei Kleinunternehmern oder Freiberuflern ist dies jedoch haeufiger."
        ),
    },
    AnomalyType.MISSING_VAT: {
        "title": "Fehlende USt-Identifikationsnummer",
        "summary_template": "Keine USt-ID bei Rechnung ueber {amount} EUR.",
        "detail_template": (
            "Bei dieser Rechnung fehlt die USt-Identifikationsnummer, obwohl der "
            "Betrag ueber der Pruefgrenze liegt. Fuer den Vorsteuerabzug ist eine "
            "gueltige USt-ID des Rechnungsstellers erforderlich. "
            "Pruefen Sie die Rechnung auf Vollstaendigkeit oder fordern Sie eine "
            "korrigierte Version an."
        ),
    },
    AnomalyType.AMOUNT_MISMATCH: {
        "title": "Betragsdiskrepanz erkannt",
        "summary_template": "Netto + MwSt ({calculated} EUR) != Brutto ({actual} EUR).",
        "detail_template": (
            "Die Summe aus Nettobetrag und MwSt entspricht nicht dem angegebenen "
            "Bruttobetrag. Differenz: {difference} EUR. "
            "Moegliche Ursachen: Rundungsfehler, falsche MwSt-Berechnung, "
            "Tippfehler bei der Rechnungserstellung. "
            "Eine korrekte Rechnung ist fuer den Vorsteuerabzug erforderlich."
        ),
    },
    AnomalyType.FUTURE_DATE: {
        "title": "Datum in der Zukunft",
        "summary_template": "Rechnungsdatum liegt {days} Tage in der Zukunft.",
        "detail_template": (
            "Das angegebene Rechnungsdatum liegt nach dem heutigen Datum. "
            "Dies kann auf eine Vordatierung, einen Eingabefehler oder "
            "unterschiedliche Zeitzonen hindeuten. "
            "Pruefen Sie das korrekte Datum beim Lieferanten."
        ),
    },
}


class ExplainableAnomalyService:
    """
    Erweiterte Anomalie-Erkennung mit detaillierten Erklaerungen.

    Nutzt den bestehenden AnomalyDetectionService und reichert
    die Ergebnisse mit kontextuellen Erklaerungen an.
    """

    def __init__(self) -> None:
        """Initialisiert den Service."""
        self._base_service = get_anomaly_detection_service()
        self._feedback_cache: Dict[str, List[Dict[str, Any]]] = {}

    async def analyze_document(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        company_id: Optional[uuid.UUID] = None,
        explanation_level: AnomalyExplanationLevel = AnomalyExplanationLevel.DETAILED,
    ) -> ExplainedAnomalyResult:
        """
        Analysiert ein Dokument auf Anomalien mit vollstaendiger Erklaerung.

        Args:
            db: Database Session
            document_id: Dokument-ID
            company_id: Optional Company-ID
            explanation_level: Detail-Level der Erklaerung

        Returns:
            ExplainedAnomalyResult mit erklaerten Anomalien
        """
        import time
        start_time = time.perf_counter()

        # Basis-Analyse durchfuehren
        base_result = await self._base_service.check_document(
            db, document_id, company_id
        )

        # Dokument laden fuer Kontext
        result = await db.execute(
            select(Document).where(Document.id == document_id)
        )
        doc = result.scalar_one_or_none()
        extracted_data = get_extracted_data(doc) if doc else None

        # Anomalien erweitern
        explained_anomalies: List[ExplainedAnomaly] = []

        for anomaly in base_result.anomalies:
            explained = await self._explain_anomaly(
                db, anomaly, doc, extracted_data, company_id, explanation_level
            )
            explained_anomalies.append(explained)

            EXPLAINABLE_ANOMALY_REQUESTS.labels(
                anomaly_type=anomaly.anomaly_type.value
            ).inc()

        # Top-Empfehlungen sammeln
        all_recommendations = [
            rec
            for ea in explained_anomalies
            for rec in ea.recommendations
        ]
        top_recommendations = sorted(
            all_recommendations,
            key=lambda r: r.priority
        )[:5]

        # Gesamterklaerung generieren
        overall_explanation = self._generate_overall_explanation(
            explained_anomalies, base_result.overall_risk_score
        )

        # Sofortige Aktion erforderlich?
        requires_immediate = any(
            ea.severity in (AnomalySeverity.HIGH, AnomalySeverity.CRITICAL)
            for ea in explained_anomalies
        )

        processing_time_ms = int((time.perf_counter() - start_time) * 1000)

        return ExplainedAnomalyResult(
            document_id=document_id,
            anomalies=explained_anomalies,
            overall_risk_score=base_result.overall_risk_score,
            overall_explanation=overall_explanation,
            top_recommendations=top_recommendations,
            requires_immediate_action=requires_immediate,
            processing_time_ms=processing_time_ms,
            metadata={
                "explanation_level": explanation_level.value,
                "base_anomaly_count": len(base_result.anomalies),
            },
        )

    async def submit_feedback(
        self,
        document_id: uuid.UUID,
        anomaly_type: AnomalyType,
        feedback_type: str,  # "confirmed", "false_positive", "unclear"
        user_id: uuid.UUID,
        comment: Optional[str] = None,
    ) -> bool:
        """
        Speichert Feedback zu einer Anomalie fuer zukuenftige Verbesserung.

        Args:
            document_id: Dokument-ID
            anomaly_type: Anomalie-Typ
            feedback_type: Art des Feedbacks
            user_id: User-ID
            comment: Optionaler Kommentar

        Returns:
            True wenn erfolgreich
        """
        feedback = {
            "document_id": str(document_id),
            "anomaly_type": anomaly_type.value,
            "feedback_type": feedback_type,
            "user_id": str(user_id),
            "comment": comment,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # In Cache speichern (in Produktion: Datenbank)
        key = f"{anomaly_type.value}"
        if key not in self._feedback_cache:
            self._feedback_cache[key] = []
        self._feedback_cache[key].append(feedback)

        ANOMALY_FEEDBACK_RECEIVED.labels(feedback_type=feedback_type).inc()

        logger.info(
            "anomaly_feedback_received",
            document_id=str(document_id),
            anomaly_type=anomaly_type.value,
            feedback_type=feedback_type,
        )

        return True

    async def get_anomaly_trends(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        days: int = 90,
    ) -> List[AnomalyTrend]:
        """
        Gibt historische Anomalie-Trends zurueck.

        Args:
            db: Database Session
            company_id: Company-ID
            days: Analysezeitraum in Tagen

        Returns:
            Liste von AnomalyTrend
        """
        # Vereinfachte Implementierung - in Produktion aus Datenbank
        trends = []

        for anomaly_type in AnomalyType:
            # Placeholder-Daten (in Produktion: echte Statistiken)
            trends.append(AnomalyTrend(
                anomaly_type=anomaly_type,
                occurrences_30d=5,  # Placeholder
                occurrences_90d=15,  # Placeholder
                trend_direction="stable",
                typical_severity=AnomalySeverity.MEDIUM,
            ))

        return trends

    # =========================================================================
    # PRIVATE METHODS
    # =========================================================================

    async def _explain_anomaly(
        self,
        db: AsyncSession,
        anomaly: DetectedAnomaly,
        doc: Optional[Document],
        extracted_data: Optional[ExtractedData],
        company_id: Optional[uuid.UUID],
        explanation_level: AnomalyExplanationLevel,
    ) -> ExplainedAnomaly:
        """Erstellt eine vollstaendige Erklaerung fuer eine Anomalie."""
        template = ANOMALY_TEMPLATES.get(anomaly.anomaly_type, {})

        # Titel und Summary aus Template
        title = template.get("title", anomaly.anomaly_type.value)

        # Summary mit Details fuellen
        summary = self._format_summary(
            template.get("summary_template", anomaly.description),
            anomaly.details,
        )

        # Detaillierte Erklaerung
        detailed = self._format_summary(
            template.get("detail_template", ""),
            anomaly.details,
        )

        # Kontextuelle Vergleiche erstellen
        comparisons = await self._build_comparisons(
            db, anomaly, extracted_data, company_id
        )

        # Empfehlungen erstellen
        recommendations = self._build_recommendations(anomaly)

        # Betroffene Felder
        affected_fields = self._get_affected_fields(anomaly.anomaly_type)

        # Historische Trends (vereinfacht)
        trend = AnomalyTrend(
            anomaly_type=anomaly.anomaly_type,
            occurrences_30d=3,
            occurrences_90d=10,
            trend_direction="stable",
            typical_severity=anomaly.severity,
        )

        return ExplainedAnomaly(
            anomaly_type=anomaly.anomaly_type,
            severity=anomaly.severity,
            confidence=anomaly.confidence,
            title=title,
            summary=summary,
            detailed_explanation=detailed,
            context_comparisons=comparisons,
            recommendations=recommendations,
            affected_fields=affected_fields,
            evidence=anomaly.details,
            historical_trend=trend,
            similar_cases_count=5,  # Placeholder
            metadata={
                "original_description": anomaly.description,
                "original_recommendation": anomaly.recommendation,
            },
        )

    def _format_summary(
        self,
        template: str,
        details: Dict[str, Any],
    ) -> str:
        """Formatiert ein Template mit Details."""
        try:
            # Sichere String-Formatierung
            result = template
            for key, value in details.items():
                placeholder = "{" + key + "}"
                if placeholder in result:
                    if isinstance(value, (int, float, Decimal)):
                        formatted = f"{float(value):.2f}" if isinstance(value, (Decimal, float)) else str(value)
                    else:
                        formatted = str(value)
                    result = result.replace(placeholder, formatted)
            return result
        except Exception:
            return template

    async def _build_comparisons(
        self,
        db: AsyncSession,
        anomaly: DetectedAnomaly,
        extracted_data: Optional[ExtractedData],
        company_id: Optional[uuid.UUID],
    ) -> List[ContextualComparison]:
        """Erstellt kontextuelle Vergleiche."""
        comparisons: List[ContextualComparison] = []

        if anomaly.anomaly_type == AnomalyType.HIGH_AMOUNT:
            if "amount" in anomaly.details and "median" in anomaly.details:
                amount = anomaly.details["amount"]
                median = anomaly.details["median"]
                deviation = ((amount - median) / median * 100) if median > 0 else 0

                comparisons.append(ContextualComparison(
                    metric_name="Rechnungsbetrag",
                    current_value=f"{amount:.2f} EUR",
                    comparison_value=f"{median:.2f} EUR",
                    comparison_type="median",
                    deviation_percent=round(deviation, 1),
                    is_significant=deviation > 100,
                ))

        elif anomaly.anomaly_type == AnomalyType.AMOUNT_MISMATCH:
            if "total_gross" in anomaly.details and "calculated_gross" in anomaly.details:
                actual = anomaly.details["total_gross"]
                calculated = anomaly.details["calculated_gross"]
                diff = anomaly.details.get("difference", 0)

                comparisons.append(ContextualComparison(
                    metric_name="Bruttobetrag-Berechnung",
                    current_value=f"{actual:.2f} EUR",
                    comparison_value=f"{calculated:.2f} EUR (berechnet)",
                    comparison_type="calculated",
                    deviation_percent=round((diff / actual * 100) if actual > 0 else 0, 2),
                    is_significant=diff > 1.0,
                ))

        return comparisons

    def _build_recommendations(
        self,
        anomaly: DetectedAnomaly,
    ) -> List[AnomalyRecommendation]:
        """Erstellt Empfehlungen fuer eine Anomalie."""
        recommendations: List[AnomalyRecommendation] = []

        # Primaere Empfehlung aus der Anomalie
        if anomaly.recommendation:
            recommendations.append(AnomalyRecommendation(
                priority=1,
                action=anomaly.recommendation,
                reason=f"Basierend auf {anomaly.anomaly_type.value} Erkennung",
                expected_outcome="Risikominimierung durch manuelle Pruefung",
                effort_level="low",
            ))

        # Anomalie-spezifische zusaetzliche Empfehlungen
        if anomaly.anomaly_type == AnomalyType.NEW_SUPPLIER_HIGH_VALUE:
            recommendations.extend([
                AnomalyRecommendation(
                    priority=2,
                    action="Handelsregistereintrag des Lieferanten pruefen",
                    reason="Verifizierung der Geschaeftslegitimitaet",
                    expected_outcome="Sicherstellung der Serioesitaet",
                    effort_level="medium",
                ),
                AnomalyRecommendation(
                    priority=3,
                    action="Referenzen von anderen Kunden einholen",
                    reason="Zusaetzliche Vertrauensbildung",
                    expected_outcome="Risikoreduktion bei Erstbestellung",
                    effort_level="high",
                ),
            ])

        elif anomaly.anomaly_type == AnomalyType.DUPLICATE_NUMBER:
            recommendations.extend([
                AnomalyRecommendation(
                    priority=2,
                    action="Originaldokumente vergleichen",
                    reason="Feststellung ob identisch oder unterschiedlich",
                    expected_outcome="Klaerung ob Doppelbuchung oder legitim",
                    effort_level="medium",
                ),
                AnomalyRecommendation(
                    priority=3,
                    action="Lieferanten kontaktieren bei Unklarheit",
                    reason="Direkte Klaerung mit Rechnungssteller",
                    expected_outcome="Verbindliche Aussage zur Rechnung",
                    effort_level="medium",
                ),
            ])

        elif anomaly.anomaly_type == AnomalyType.MISSING_VAT:
            recommendations.append(AnomalyRecommendation(
                priority=2,
                action="Korrigierte Rechnung mit USt-ID anfordern",
                reason="Fuer korrekten Vorsteuerabzug erforderlich",
                expected_outcome="Steuerrechtlich korrekte Dokumentation",
                effort_level="low",
            ))

        return recommendations

    def _get_affected_fields(self, anomaly_type: AnomalyType) -> List[str]:
        """Gibt die von einer Anomalie betroffenen Felder zurueck."""
        field_mapping: Dict[AnomalyType, List[str]] = {
            AnomalyType.HIGH_AMOUNT: ["total_gross", "total_net", "vat_amount"],
            AnomalyType.NEW_SUPPLIER_HIGH_VALUE: ["supplier_name", "total_gross"],
            AnomalyType.DUPLICATE_NUMBER: ["invoice_number"],
            AnomalyType.UNUSUAL_PAYMENT_TERMS: ["payment_term_days", "due_date"],
            AnomalyType.ROUND_AMOUNT: ["total_gross"],
            AnomalyType.WEEKEND_INVOICE: ["invoice_date"],
            AnomalyType.MISSING_VAT: ["supplier_vat_id", "customer_vat_id"],
            AnomalyType.AMOUNT_MISMATCH: ["total_net", "vat_amount", "total_gross"],
            AnomalyType.FUTURE_DATE: ["invoice_date"],
        }
        return field_mapping.get(anomaly_type, [])

    def _generate_overall_explanation(
        self,
        anomalies: List[ExplainedAnomaly],
        risk_score: float,
    ) -> str:
        """Generiert eine Gesamterklaerung."""
        if not anomalies:
            return "Keine Anomalien erkannt. Das Dokument erscheint unauffaellig."

        count = len(anomalies)
        critical_count = len([
            a for a in anomalies
            if a.severity in (AnomalySeverity.HIGH, AnomalySeverity.CRITICAL)
        ])

        if critical_count > 0:
            urgency = f"{critical_count} kritische Anomalie(n) erfordern sofortige Aufmerksamkeit. "
        else:
            urgency = ""

        risk_level = (
            "hoch" if risk_score > 0.6
            else "mittel" if risk_score > 0.3
            else "niedrig"
        )

        top_types = ", ".join(
            a.anomaly_type.value.replace("_", " ").title()
            for a in anomalies[:3]
        )

        return (
            f"{count} Anomalie(n) erkannt mit Gesamt-Risikoscore {risk_score:.2f} ({risk_level}). "
            f"{urgency}"
            f"Hauptbereiche: {top_types}. "
            f"Empfohlene Aktionen finden Sie in den Einzelanalysen."
        )


# =============================================================================
# Factory
# =============================================================================

_explainable_anomaly_service: Optional[ExplainableAnomalyService] = None


def get_explainable_anomaly_service() -> ExplainableAnomalyService:
    """Factory fuer ExplainableAnomalyService Singleton."""
    global _explainable_anomaly_service
    if _explainable_anomaly_service is None:
        _explainable_anomaly_service = ExplainableAnomalyService()
    return _explainable_anomaly_service
