# -*- coding: utf-8 -*-
"""
Explanation Collector - Sammelt KI-Erklaerungen fuer Dokumente und Entities.

Aggregiert Erklaerungen aus allen AI-Services, die ein Dokument
oder eine Entity verarbeitet haben:
- Klassifikation (Auto-Kategorisierung)
- OCR-Backend-Auswahl
- Risikobewertung
- Buchungsvorschlaege
- Entity-Linking
- Anomalieerkennung
- Betrugserkennung

Feinpoliert und durchdacht - Enterprise-grade XAI Aggregation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AIDecision, Document, BusinessEntity
from app.services.ai.explainability_protocol import (
    DecisionType,
    ExplanationFactor,
    ExplanationResult,
)
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# ============================================================================
# Decision Type Mapping
# ============================================================================

# Maps AIDecision.decision_type strings to DecisionType enum values
_DECISION_TYPE_MAP: Dict[str, DecisionType] = {
    "categorization": DecisionType.CLASSIFICATION,
    "classification": DecisionType.CLASSIFICATION,
    "risk_assessment": DecisionType.RISK_ASSESSMENT,
    "risk": DecisionType.RISK_ASSESSMENT,
    "ocr": DecisionType.OCR_EXTRACTION,
    "ocr_extraction": DecisionType.OCR_EXTRACTION,
    "accounting": DecisionType.BOOKING_SUGGESTION,
    "booking_suggestion": DecisionType.BOOKING_SUGGESTION,
    "booking": DecisionType.BOOKING_SUGGESTION,
    "dunning": DecisionType.DUNNING_RECOMMENDATION,
    "dunning_recommendation": DecisionType.DUNNING_RECOMMENDATION,
    "anomaly": DecisionType.ANOMALY_DETECTION,
    "anomaly_detection": DecisionType.ANOMALY_DETECTION,
    "matching": DecisionType.ENTITY_LINKING,
    "entity_linking": DecisionType.ENTITY_LINKING,
    "duplicate": DecisionType.DUPLICATE_DETECTION,
    "duplicate_detection": DecisionType.DUPLICATE_DETECTION,
    "fraud": DecisionType.FRAUD_DETECTION,
    "fraud_detection": DecisionType.FRAUD_DETECTION,
    "prediction": DecisionType.CASHFLOW_PREDICTION,
    "cashflow_prediction": DecisionType.CASHFLOW_PREDICTION,
}

# German summaries for decision types
_DECISION_SUMMARIES: Dict[DecisionType, str] = {
    DecisionType.CLASSIFICATION: "Dokument automatisch klassifiziert",
    DecisionType.RISK_ASSESSMENT: "Risikobewertung durchgefuehrt",
    DecisionType.OCR_EXTRACTION: "OCR-Texterkennung abgeschlossen",
    DecisionType.BOOKING_SUGGESTION: "Buchungsvorschlag erstellt",
    DecisionType.DUNNING_RECOMMENDATION: "Mahnempfehlung generiert",
    DecisionType.ANOMALY_DETECTION: "Anomalie erkannt",
    DecisionType.ENTITY_LINKING: "Geschaeftspartner-Zuordnung vorgenommen",
    DecisionType.DUPLICATE_DETECTION: "Duplikatpruefung durchgefuehrt",
    DecisionType.FRAUD_DETECTION: "Betrugspruefung abgeschlossen",
    DecisionType.CASHFLOW_PREDICTION: "Cashflow-Vorhersage erstellt",
}

# German service names
_SERVICE_NAMES: Dict[DecisionType, str] = {
    DecisionType.CLASSIFICATION: "Auto-Kategorisierung",
    DecisionType.RISK_ASSESSMENT: "Risiko-Scoring",
    DecisionType.OCR_EXTRACTION: "OCR-Texterkennung",
    DecisionType.BOOKING_SUGGESTION: "Buchungsassistent",
    DecisionType.DUNNING_RECOMMENDATION: "Mahnwesen-KI",
    DecisionType.ANOMALY_DETECTION: "Anomalie-Erkennung",
    DecisionType.ENTITY_LINKING: "Entity-Linking",
    DecisionType.DUPLICATE_DETECTION: "Duplikat-Erkennung",
    DecisionType.FRAUD_DETECTION: "Betrugserkennung",
    DecisionType.CASHFLOW_PREDICTION: "Cashflow-Prognose",
}


class ExplanationCollector:
    """Sammelt Erklaerungen aus allen AI-Services fuer Dokumente und Entities."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Collector mit einer Datenbank-Session."""
        self.db = db

    async def collect_for_document(
        self,
        document_id: UUID,
        company_id: UUID,
    ) -> List[ExplanationResult]:
        """
        Sammelt alle KI-Erklaerungen fuer ein Dokument.

        Durchsucht die ai_decisions-Tabelle nach allen Entscheidungen,
        die fuer dieses Dokument getroffen wurden, und konvertiert sie
        in das einheitliche ExplanationResult-Format.

        Args:
            document_id: ID des Dokuments
            company_id: ID des Mandanten (Multi-Tenancy)

        Returns:
            Liste von ExplanationResult-Objekten
        """
        explanations: List[ExplanationResult] = []

        try:
            # Alle AI-Entscheidungen fuer dieses Dokument abrufen
            stmt = (
                select(AIDecision)
                .where(
                    and_(
                        AIDecision.document_id == document_id,
                        AIDecision.company_id == company_id,
                    )
                )
                .order_by(desc(AIDecision.created_at))
            )
            result = await self.db.execute(stmt)
            decisions = result.scalars().all()

            for decision in decisions:
                explanation = self._convert_decision(decision)
                if explanation is not None:
                    explanations.append(explanation)

            # Zusaetzlich: OCR-Erklaerung aus Dokument-Metadaten
            ocr_explanation = await self._collect_ocr_explanation(
                document_id, company_id
            )
            if ocr_explanation is not None:
                # Nur hinzufuegen, wenn nicht schon eine OCR-Entscheidung existiert
                has_ocr = any(
                    e.decision_type == DecisionType.OCR_EXTRACTION
                    for e in explanations
                )
                if not has_ocr:
                    explanations.append(ocr_explanation)

            logger.info(
                "explanations_collected_for_document",
                document_id=str(document_id),
                count=len(explanations),
            )

        except Exception as e:
            logger.error(
                "explanation_collection_failed",
                document_id=str(document_id),
                **safe_error_log(e),
            )

        return explanations

    async def collect_for_entity(
        self,
        entity_id: UUID,
        company_id: UUID,
    ) -> List[ExplanationResult]:
        """
        Sammelt alle KI-Erklaerungen fuer eine Entity (Geschaeftspartner).

        Sucht nach Risikobewertungen, Mahnempfehlungen und
        Anomalie-Erkennungen fuer die Entity.

        Args:
            entity_id: ID der Entity
            company_id: ID des Mandanten (Multi-Tenancy)

        Returns:
            Liste von ExplanationResult-Objekten
        """
        explanations: List[ExplanationResult] = []

        try:
            # AI-Entscheidungen mit Bezug zu Dokumenten dieser Entity
            stmt = (
                select(AIDecision)
                .join(Document, AIDecision.document_id == Document.id)
                .where(
                    and_(
                        Document.business_entity_id == entity_id,
                        AIDecision.company_id == company_id,
                    )
                )
                .order_by(desc(AIDecision.created_at))
                .limit(50)  # Begrenzung fuer Performance
            )
            result = await self.db.execute(stmt)
            decisions = result.scalars().all()

            for decision in decisions:
                explanation = self._convert_decision(decision)
                if explanation is not None:
                    explanations.append(explanation)

            logger.info(
                "explanations_collected_for_entity",
                entity_id=str(entity_id),
                count=len(explanations),
            )

        except Exception as e:
            logger.error(
                "explanation_collection_for_entity_failed",
                entity_id=str(entity_id),
                **safe_error_log(e),
            )

        return explanations

    def _convert_decision(self, decision: AIDecision) -> Optional[ExplanationResult]:
        """
        Konvertiert eine AIDecision in ein ExplanationResult.

        Args:
            decision: AIDecision-Datenbankentrag

        Returns:
            ExplanationResult oder None bei unbekanntem Typ
        """
        decision_type = _DECISION_TYPE_MAP.get(decision.decision_type)
        if decision_type is None:
            logger.warning(
                "unknown_decision_type",
                decision_type=decision.decision_type,
                decision_id=str(decision.id),
            )
            return None

        # Faktoren aus der Explanation extrahieren
        factors = self._extract_factors(decision)

        # Entscheidungszusammenfassung generieren
        summary = self._build_summary(decision_type, decision)

        # Modellinfo
        model_used = None
        if decision.features_used and isinstance(decision.features_used, dict):
            model_used = decision.features_used.get("model")

        # Alternative Entscheidungen
        alternatives = self._extract_alternatives(decision)

        return ExplanationResult(
            decision_type=decision_type,
            service_name=_SERVICE_NAMES.get(
                decision_type, decision.decision_type
            ),
            decision_summary=summary,
            confidence=decision.confidence or 0.0,
            factors=factors,
            model_used=model_used,
            alternative_decisions=alternatives,
            created_at=(
                decision.created_at.isoformat()
                if decision.created_at
                else datetime.now(timezone.utc).isoformat()
            ),
        )

    def _extract_factors(
        self, decision: AIDecision
    ) -> List[ExplanationFactor]:
        """Extrahiert Erklaerungsfaktoren aus einer AI-Entscheidung."""
        factors: List[ExplanationFactor] = []

        explanation_data = decision.explanation
        if not explanation_data or not isinstance(explanation_data, dict):
            return factors

        # Reasons extrahieren (einfaches String-Array)
        reasons = explanation_data.get("reasons", [])
        if isinstance(reasons, list):
            for i, reason in enumerate(reasons):
                if isinstance(reason, str):
                    factors.append(
                        ExplanationFactor(
                            name=f"Grund {i + 1}",
                            value=reason,
                            importance=max(0.3, 1.0 - (i * 0.15)),
                            description=reason,
                        )
                    )

        # Features extrahieren (Dict mit Gewichtungen)
        features = explanation_data.get("features", {})
        if isinstance(features, dict):
            for name, value in features.items():
                importance = 0.5
                if isinstance(value, dict):
                    importance = float(value.get("importance", 0.5))
                    display_value = str(value.get("value", value))
                else:
                    display_value = str(value)

                factors.append(
                    ExplanationFactor(
                        name=name,
                        value=display_value,
                        importance=importance,
                        description=f"{name}: {display_value}",
                    )
                )

        # Factors extrahieren (falls direkt vorhanden)
        raw_factors = explanation_data.get("factors", [])
        if isinstance(raw_factors, list):
            for f in raw_factors:
                if isinstance(f, dict):
                    factors.append(
                        ExplanationFactor(
                            name=str(f.get("name", "Faktor")),
                            value=str(f.get("value", "")),
                            importance=float(f.get("importance", 0.5)),
                            description=str(
                                f.get("description", f.get("name", ""))
                            ),
                        )
                    )

        return factors

    def _build_summary(
        self, decision_type: DecisionType, decision: AIDecision
    ) -> str:
        """Erstellt eine deutschsprachige Zusammenfassung der Entscheidung."""
        base_summary = _DECISION_SUMMARIES.get(
            decision_type, "KI-Entscheidung getroffen"
        )

        # Detail-Informationen aus decision_value extrahieren
        decision_value = decision.decision_value
        if not isinstance(decision_value, dict):
            return base_summary

        if decision_type == DecisionType.CLASSIFICATION:
            category = decision_value.get("category", "")
            if category:
                return f"Dokument als '{category}' klassifiziert"

        elif decision_type == DecisionType.BOOKING_SUGGESTION:
            debit = decision_value.get("debit_account", "")
            credit = decision_value.get("credit_account", "")
            if debit and credit:
                return f"Buchung vorgeschlagen: Soll {debit} / Haben {credit}"

        elif decision_type == DecisionType.RISK_ASSESSMENT:
            score = decision_value.get("score")
            if score is not None:
                return f"Risikobewertung: Score {score}/100"

        elif decision_type == DecisionType.ENTITY_LINKING:
            match_type = decision_value.get("match_type", "")
            if match_type:
                return f"Entity-Zuordnung: {match_type}"

        return base_summary

    def _extract_alternatives(
        self, decision: AIDecision
    ) -> List[Dict[str, Optional[str]]]:
        """Extrahiert alternative Entscheidungen aus den Metadaten."""
        alternatives: List[Dict[str, Optional[str]]] = []

        explanation_data = decision.explanation
        if not explanation_data or not isinstance(explanation_data, dict):
            return alternatives

        raw_alternatives = explanation_data.get("alternatives", [])
        if isinstance(raw_alternatives, list):
            for alt in raw_alternatives:
                if isinstance(alt, dict):
                    alternatives.append({
                        "label": str(alt.get("label", "")),
                        "confidence": str(alt.get("confidence", "")),
                        "reason": alt.get("reason"),
                    })

        return alternatives

    async def _collect_ocr_explanation(
        self,
        document_id: UUID,
        company_id: UUID,
    ) -> Optional[ExplanationResult]:
        """
        Erstellt eine OCR-Erklaerung aus den Dokument-Metadaten.

        Liest das verwendete OCR-Backend und die Konfidenz
        direkt aus der documents-Tabelle.
        """
        try:
            stmt = select(Document).where(
                and_(
                    Document.id == document_id,
                    Document.company_id == company_id,
                )
            )
            result = await self.db.execute(stmt)
            document = result.scalar_one_or_none()

            if document is None or document.ocr_backend_used is None:
                return None

            factors: List[ExplanationFactor] = []

            # Backend-Faktor
            factors.append(
                ExplanationFactor(
                    name="OCR-Backend",
                    value=document.ocr_backend_used,
                    importance=0.9,
                    description=(
                        f"Backend '{document.ocr_backend_used}' fuer die "
                        f"Texterkennung verwendet"
                    ),
                )
            )

            # Konfidenz-Faktor
            if document.ocr_confidence is not None:
                factors.append(
                    ExplanationFactor(
                        name="OCR-Konfidenz",
                        value=f"{document.ocr_confidence:.1%}",
                        importance=0.8,
                        description=(
                            f"Texterkennung mit {document.ocr_confidence:.1%} "
                            f"Konfidenz"
                        ),
                    )
                )

            # Verarbeitungszeit-Faktor
            if document.processing_duration_ms is not None:
                duration_s = document.processing_duration_ms / 1000.0
                factors.append(
                    ExplanationFactor(
                        name="Verarbeitungszeit",
                        value=f"{duration_s:.1f}s",
                        importance=0.4,
                        description=(
                            f"Texterkennung dauerte {duration_s:.1f} Sekunden"
                        ),
                    )
                )

            # Sprache-Faktor
            if document.detected_language:
                factors.append(
                    ExplanationFactor(
                        name="Erkannte Sprache",
                        value=document.detected_language,
                        importance=0.5,
                        description=(
                            f"Sprache als '{document.detected_language}' erkannt"
                        ),
                    )
                )

            return ExplanationResult(
                decision_type=DecisionType.OCR_EXTRACTION,
                service_name="OCR-Texterkennung",
                decision_summary=(
                    f"Texterkennung mit {document.ocr_backend_used} "
                    f"abgeschlossen"
                ),
                confidence=document.ocr_confidence or 0.0,
                factors=factors,
                model_used=document.ocr_backend_used,
                created_at=(
                    document.processed_date.isoformat()
                    if document.processed_date
                    else None
                ),
            )

        except Exception as e:
            logger.error(
                "ocr_explanation_collection_failed",
                document_id=str(document_id),
                **safe_error_log(e),
            )
            return None
