# -*- coding: utf-8 -*-
"""
Unified Explainability Service - Phase 4.3 Erklaerbare AI-Entscheidungen API.

Zentraler Service fuer alle KI-Erklaerungen im Ablage-System:
- Dokument-Klassifikation (warum wurde dieses Dokument so klassifiziert?)
- Cluster-Vorschlaege (warum wird dieser Cluster vorgeschlagen?)
- Anomalie-Erklaerungen (warum wurde diese Anomalie gemeldet?)
- Entity-Linking (warum wurde diese Entitaet verknuepft?)

Feinpoliert und durchdacht - Enterprise-grade Explainable AI.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Union
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_errors import safe_error_log
from app.db.models import (
    BusinessEntity,
    Document,
    DocumentEntityLink,
)
from app.db.models_anomaly import Anomaly
from app.db.models_clustering import ClusterSuggestion

logger = structlog.get_logger(__name__)


# =============================================================================
# Typdefinitionen
# =============================================================================

ExplanationFactor = Dict[str, Union[str, float]]
AlternativeDecision = Dict[str, Union[str, float]]


# =============================================================================
# Ergebnis-Typen
# =============================================================================

ClassificationExplanation = Dict[
    str, Union[str, float, List[ExplanationFactor], List[AlternativeDecision]]
]
ClusterExplanation = Dict[
    str, Union[str, float, List[Dict[str, Union[str, float]]], List[str]]
]
AnomalyExplanation = Dict[
    str, Union[str, float, List[str], Dict[str, Union[str, float, int]]]
]
EntityLinkExplanation = Dict[
    str, Union[str, float, List[Dict[str, str]]]
]


# =============================================================================
# Hilfsfunktionen fuer Erklaerungstexte
# =============================================================================

def _confidence_label(confidence: float) -> str:
    """Liefert deutschen Beschreibungstext fuer Konfidenzwert."""
    if confidence >= 0.90:
        return "sehr hoher"
    if confidence >= 0.75:
        return "hoher"
    if confidence >= 0.55:
        return "mittlerer"
    return "niedriger"


def _doc_type_german(doc_type: str) -> str:
    """Uebersetzt internen Dokumenttyp ins Deutsche."""
    mapping: Dict[str, str] = {
        "invoice": "Rechnung",
        "order": "Bestellung",
        "delivery_note": "Lieferschein",
        "contract": "Vertrag",
        "credit_note": "Gutschrift",
        "dunning": "Mahnung",
        "bank_statement": "Kontoauszug",
        "receipt": "Quittung",
        "letter": "Brief",
        "report": "Bericht",
        "other": "Sonstiges",
    }
    return mapping.get(doc_type.lower(), doc_type)


def _severity_german(severity: str) -> str:
    """Uebersetzt Anomalie-Schweregrad ins Deutsche."""
    mapping: Dict[str, str] = {
        "info": "Information",
        "warning": "Warnung",
        "critical": "Kritisch",
        "low": "Niedrig",
        "medium": "Mittel",
        "high": "Hoch",
    }
    return mapping.get(severity.lower(), severity)


def _link_type_german(link_type: Optional[str]) -> str:
    """Uebersetzt Entity-Link-Typ ins Deutsche."""
    mapping: Dict[str, str] = {
        "invoice_sender": "Rechnungssteller",
        "invoice_recipient": "Rechnungsempfaenger",
        "mentioned": "Im Dokument erwaehnt",
        "extracted": "Per OCR extrahiert",
        "manual": "Manuell verknuepft",
    }
    if not link_type:
        return "Unbekannt"
    return mapping.get(link_type.lower(), link_type)


# =============================================================================
# ExplainabilityService
# =============================================================================

class ExplainabilityService:
    """
    Einheitlicher Service fuer KI-Entscheidungserlaeuterungen.

    Erklaert saemtliche KI-Entscheidungen des Ablage-Systems in
    natuerlichsprachlichem Deutsch. Nutzt vorhandene Datenbankinformationen
    und greift gracefully auf "Nicht gefunden"-Erklaerungen zurueck,
    wenn Daten fehlen.

    Unterstuetzte Erklaerungstypen:
    - explain_classification: Dokument-Klassifikation per OCR-Pipeline
    - explain_cluster_suggestion: Cluster-/Entity-Vorschlaege per pgvector
    - explain_anomaly: Anomalie-Erkennungen (regelbasiert + ML)
    - explain_entity_linking: Verknuepfungen zwischen Dokumenten und Entitaeten
    """

    # -------------------------------------------------------------------
    # Klassifikationserlaeuterung
    # -------------------------------------------------------------------

    async def explain_classification(
        self,
        document_id: UUID,
        company_id: UUID,
        db: AsyncSession,
    ) -> ClassificationExplanation:
        """
        Erklaert die Dokumentklassifikation der OCR-Pipeline.

        Beschreibt, anhand welcher Merkmale das Dokument einer
        Kategorie zugeordnet wurde, und listet Alternativen sowie
        die wichtigsten Einflussfaktoren auf.

        Args:
            document_id: UUID des Dokuments
            company_id: UUID des Mandanten (Zugriffsschutz)
            db: Datenbankverbindung

        Returns:
            Dictionary mit explanation_text, factors, confidence, alternatives
        """
        logger.info(
            "explainability.classification.start",
            document_id=str(document_id),
            company_id=str(company_id),
        )

        try:
            result = await db.execute(
                select(Document).where(
                    Document.id == document_id,
                    Document.company_id == company_id,
                )
            )
            document = result.scalar_one_or_none()
        except Exception as exc:
            logger.error(
                "explainability.classification.db_error",
                **safe_error_log(exc, context="explain_classification"),
            )
            document = None

        if not document:
            return self._not_found_explanation(
                "classification",
                "Dokument nicht gefunden oder kein Zugriff.",
            )

        doc_type = document.document_type or "other"
        confidence = float(document.ocr_confidence or 0.5)
        extracted_text = document.extracted_text or ""
        meta = document.document_metadata or {}

        # Einflussfaktoren aufbauen
        factors: List[ExplanationFactor] = []

        # 1. Erkannte Schluesselwoerter
        keywords = self._extract_classification_keywords(extracted_text, doc_type)
        if keywords:
            factors.append({
                "feature": "Schluesselwoerter",
                "weight": 0.40,
                "description": (
                    f"Typische Begriffe erkannt: {', '.join(keywords[:4])}"
                ),
            })

        # 2. Strukturmerkmale
        has_table_indicators = any(
            kw in extracted_text.lower()
            for kw in ["betrag", "mwst", "netto", "brutto", "gesamt", "summe"]
        )
        if has_table_indicators:
            factors.append({
                "feature": "Strukturmerkmale",
                "weight": 0.25,
                "description": "Typische Tabellenstruktur und Betragsfelder erkannt.",
            })

        # 3. OCR-Konfidenz
        ocr_label = (
            "Sehr hohe OCR-Qualitaet" if confidence > 0.90
            else "Gute OCR-Qualitaet" if confidence > 0.70
            else "Niedrige OCR-Qualitaet - Klassifikation moeglicherweise unsicher"
        )
        factors.append({
            "feature": "OCR-Konfidenz",
            "weight": 0.25,
            "description": f"{ocr_label} ({confidence * 100:.0f}%).",
        })

        # 4. Dateiname / Metadaten
        filename = meta.get("original_filename", "") or ""
        if filename:
            factors.append({
                "feature": "Dateiname",
                "weight": 0.10,
                "description": f"Dateiname '{filename}' lieferte zusaetzliche Hinweise.",
            })

        # Alternativen
        alternative_types = self._get_alternative_doc_types(doc_type)
        alternatives: List[AlternativeDecision] = [
            {"category": _doc_type_german(t), "confidence": round(0.85 - 0.15 * i, 2)}
            for i, t in enumerate(alternative_types[:3])
        ]

        german_type = _doc_type_german(doc_type)
        conf_label = _confidence_label(confidence)
        explanation_text = (
            f"Dieses Dokument wurde als '{german_type}' klassifiziert, "
            f"weil {conf_label} Konfidenz ({confidence * 100:.0f}%) vorliegt. "
        )
        if keywords:
            explanation_text += (
                f"Erkannte Schluesselwoerter wie '{keywords[0]}' "
                f"sind typisch fuer diesen Dokumenttyp. "
            )
        if has_table_indicators:
            explanation_text += "Zudem deutet die Struktur mit Betragsfeldern auf diesen Typ hin."

        logger.info(
            "explainability.classification.done",
            document_id=str(document_id),
            doc_type=doc_type,
            confidence=confidence,
        )

        return {
            "document_id": str(document_id),
            "predicted_category": german_type,
            "predicted_category_key": doc_type,
            "confidence_score": round(confidence, 3),
            "top_features": factors,
            "alternative_categories": alternatives,
            "explanation_text": explanation_text,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # -------------------------------------------------------------------
    # Cluster-Vorschlag-Erlaeuterung
    # -------------------------------------------------------------------

    async def explain_cluster_suggestion(
        self,
        suggestion_id: UUID,
        company_id: UUID,
        db: AsyncSession,
    ) -> ClusterExplanation:
        """
        Erklaert einen Cluster-Vorschlag der pgvector-Aehnlichkeitssuche.

        Beschreibt, welche Dokumente als Referenz dienten, warum sie
        aehnlich sind und welche gemeinsamen Merkmale vorliegen.

        Args:
            suggestion_id: UUID des ClusterSuggestion-Eintrags
            company_id: UUID des Mandanten (Zugriffsschutz)
            db: Datenbankverbindung

        Returns:
            Dictionary mit explanation_text, factors, confidence, alternatives
        """
        logger.info(
            "explainability.cluster.start",
            suggestion_id=str(suggestion_id),
            company_id=str(company_id),
        )

        try:
            result = await db.execute(
                select(ClusterSuggestion).where(
                    ClusterSuggestion.id == suggestion_id,
                    ClusterSuggestion.company_id == company_id,
                )
            )
            suggestion = result.scalar_one_or_none()
        except Exception as exc:
            logger.error(
                "explainability.cluster.db_error",
                **safe_error_log(exc, context="explain_cluster_suggestion"),
            )
            suggestion = None

        if not suggestion:
            return self._not_found_explanation(
                "cluster_suggestion",
                "Cluster-Vorschlag nicht gefunden oder kein Zugriff.",
            )

        similarity = float(suggestion.similarity_score or 0.0)
        suggested_category = suggestion.suggested_category or "Unbekannt"

        # Referenzdokument laden fuer Kontext
        ref_doc: Optional[Document] = None
        if suggestion.reference_document_id:
            try:
                ref_result = await db.execute(
                    select(Document).where(
                        Document.id == suggestion.reference_document_id,
                        Document.company_id == company_id,
                    )
                )
                ref_doc = ref_result.scalar_one_or_none()
            except Exception as exc:
                logger.warning(
                    "explainability.cluster.ref_doc_error",
                    **safe_error_log(exc, context="explain_cluster_ref_doc"),
                )

        # Aehnliche Dokumente zusammenstellen
        top_similar: List[Dict[str, Union[str, float]]] = []
        if ref_doc:
            top_similar.append({
                "document_id": str(ref_doc.id),
                "title": ref_doc.title or ref_doc.filename or "Unbekannt",
                "similarity": round(similarity, 3),
            })

        # Gemeinsame Merkmale ableiten
        common_features: List[str] = []
        if ref_doc and ref_doc.document_type:
            common_features.append(
                f"Gleicher Dokumenttyp: {_doc_type_german(ref_doc.document_type)}"
            )
        if suggested_category:
            common_features.append(f"Kategorie: {suggested_category}")
        if not common_features:
            common_features.append("Aehnliche Textstruktur und Inhalt (Embedding-Aehnlichkeit)")

        # Faktoren
        factors: List[ExplanationFactor] = [
            {
                "feature": "Vektoraehnlichkeit",
                "weight": 0.70,
                "description": (
                    f"Cosine-Similarity von {similarity * 100:.1f}% mit Referenzdokument "
                    f"(pgvector-Berechnung auf semantischen Embeddings)."
                ),
            },
            {
                "feature": "Dokumentkategorie",
                "weight": 0.20,
                "description": f"Vorgeschlagene Kategorie: {suggested_category}.",
            },
            {
                "feature": "Mandantenisolation",
                "weight": 0.10,
                "description": "Nur Dokumente desselben Mandanten wurden verglichen.",
            },
        ]

        # Alternativen: andere Status-Optionen
        alternatives: List[AlternativeDecision] = [
            {"category": "Keine Zuordnung", "confidence": round(1.0 - similarity, 2)},
        ]

        sim_label = _confidence_label(similarity)
        explanation_text = (
            f"Dieser Cluster-Vorschlag basiert auf {sim_label} Aehnlichkeit "
            f"({similarity * 100:.1f}%) mit bestehenden Dokumenten. "
        )
        if ref_doc:
            ref_title = ref_doc.title or ref_doc.filename or "ein aehnliches Dokument"
            explanation_text += (
                f"Das Referenzdokument '{ref_title}' weist den hoechsten "
                f"Uebereinstimmungsgrad auf. "
            )
        if common_features:
            explanation_text += f"Gemeinsame Merkmale: {'; '.join(common_features[:2])}."

        logger.info(
            "explainability.cluster.done",
            suggestion_id=str(suggestion_id),
            similarity=similarity,
        )

        return {
            "suggestion_id": str(suggestion_id),
            "suggested_cluster_name": suggested_category,
            "similarity_score": round(similarity, 3),
            "top_similar_documents": top_similar,
            "common_features": common_features,
            "explanation_text": explanation_text,
            "factors": factors,
            "confidence": round(similarity, 3),
            "alternatives": alternatives,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # -------------------------------------------------------------------
    # Anomalie-Erlaeuterung
    # -------------------------------------------------------------------

    async def explain_anomaly(
        self,
        anomaly_id: UUID,
        company_id: UUID,
        db: AsyncSession,
    ) -> AnomalyExplanation:
        """
        Erklaert eine erkannte Anomalie mit Kontext und historischer Einordnung.

        Beschreibt, welche Bedingungen die Anomalie ausgeloest haben,
        welche Regel oder welches ML-Modell verantwortlich war und wie
        sich der Befund zu normalen Werten verhaelt.

        Args:
            anomaly_id: UUID der Anomalie
            company_id: UUID des Mandanten (Zugriffsschutz)
            db: Datenbankverbindung

        Returns:
            Dictionary mit explanation_text, factors, confidence, alternatives
        """
        logger.info(
            "explainability.anomaly.start",
            anomaly_id=str(anomaly_id),
            company_id=str(company_id),
        )

        try:
            result = await db.execute(
                select(Anomaly).where(
                    Anomaly.id == anomaly_id,
                    Anomaly.company_id == company_id,
                )
            )
            anomaly = result.scalar_one_or_none()
        except Exception as exc:
            logger.error(
                "explainability.anomaly.db_error",
                **safe_error_log(exc, context="explain_anomaly"),
            )
            anomaly = None

        if not anomaly:
            return self._not_found_explanation(
                "anomaly",
                "Anomalie nicht gefunden oder kein Zugriff.",
            )

        severity = anomaly.severity or "info"
        anomaly_type = anomaly.anomaly_type or "unknown"
        description = anomaly.description or ""
        details: Dict[str, Union[str, float, int]] = anomaly.details or {}
        score = float(anomaly.score or 0.5)

        # Regelname bestimmen
        rule_name: Optional[str] = None
        if anomaly.rule_id:
            try:
                from app.db.models_anomaly import AnomalyRule
                rule_result = await db.execute(
                    select(AnomalyRule).where(AnomalyRule.id == anomaly.rule_id)
                )
                rule = rule_result.scalar_one_or_none()
                if rule:
                    rule_name = rule.title or rule.description
            except Exception as exc:
                logger.warning(
                    "explainability.anomaly.rule_lookup_error",
                    **safe_error_log(exc, context="anomaly_rule_lookup"),
                )

        # Ausloesebedingungen aus Details extrahieren
        trigger_conditions: List[str] = self._extract_trigger_conditions(
            anomaly_type, details
        )

        # Historischer Kontext
        historical_context = self._build_historical_context(anomaly_type, details, score)

        # Einflussfaktoren
        factors: List[ExplanationFactor] = [
            {
                "feature": "Anomalie-Typ",
                "weight": 0.40,
                "description": f"Erkannter Typ: {anomaly_type.replace('_', ' ').title()}",
            },
            {
                "feature": "Schweregrad",
                "weight": 0.30,
                "description": (
                    f"Schweregrad: {_severity_german(severity)} "
                    f"(Score: {score * 100:.0f}%)"
                ),
            },
            {
                "feature": "Erkennungsquelle",
                "weight": 0.20,
                "description": (
                    f"Regelbasiert: '{rule_name}'" if rule_name
                    else "ML-basierte Erkennung (statistisches Modell)"
                ),
            },
            {
                "feature": "Konfidenz",
                "weight": 0.10,
                "description": f"Erkennungskonfidenz: {score * 100:.0f}%.",
            },
        ]

        # Alternativen
        alternatives: List[AlternativeDecision] = [
            {"category": "Fehlalarm", "confidence": round(1.0 - score, 2)},
            {"category": "Beobachten ohne Aktion", "confidence": 0.30},
        ]

        severity_german = _severity_german(severity)
        explanation_text = (
            f"Diese Anomalie vom Typ '{anomaly_type.replace('_', ' ').title()}' "
            f"wurde mit Schweregrad '{severity_german}' erkannt. "
        )
        if rule_name:
            explanation_text += f"Ausgeloest durch Regel: '{rule_name}'. "
        if trigger_conditions:
            explanation_text += (
                f"Ausloesebedingungen: {'; '.join(trigger_conditions[:2])}. "
            )
        explanation_text += historical_context

        logger.info(
            "explainability.anomaly.done",
            anomaly_id=str(anomaly_id),
            anomaly_type=anomaly_type,
            severity=severity,
        )

        return {
            "anomaly_id": str(anomaly_id),
            "anomaly_type": anomaly_type,
            "severity": severity,
            "rule_name": rule_name,
            "trigger_conditions": trigger_conditions,
            "historical_context": historical_context,
            "explanation_text": explanation_text,
            "factors": factors,
            "confidence": round(score, 3),
            "alternatives": alternatives,
            "details": details,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # -------------------------------------------------------------------
    # Entity-Linking-Erlaeuterung
    # -------------------------------------------------------------------

    async def explain_entity_linking(
        self,
        document_id: UUID,
        entity_id: UUID,
        company_id: UUID,
        db: AsyncSession,
    ) -> EntityLinkExplanation:
        """
        Erklaert die Verknuepfung zwischen einem Dokument und einer Geschaeftsentitaet.

        Zeigt, welche Felder oder Muster die Zuordnung begruenden (z. B.
        Rechnungsadresse, USt-ID, Name des Absenders).

        Args:
            document_id: UUID des Dokuments
            entity_id: UUID der Geschaeftsentitaet
            company_id: UUID des Mandanten (Zugriffsschutz)
            db: Datenbankverbindung

        Returns:
            Dictionary mit explanation_text, factors, confidence, alternatives
        """
        logger.info(
            "explainability.entity_link.start",
            document_id=str(document_id),
            entity_id=str(entity_id),
            company_id=str(company_id),
        )

        # Dokument laden
        try:
            doc_result = await db.execute(
                select(Document).where(
                    Document.id == document_id,
                    Document.company_id == company_id,
                )
            )
            document = doc_result.scalar_one_or_none()
        except Exception as exc:
            logger.error(
                "explainability.entity_link.doc_error",
                **safe_error_log(exc, context="explain_entity_link_doc"),
            )
            document = None

        # Entitaet laden (BusinessEntity hat keine company_id - cross-company Entitaeten)
        try:
            entity_result = await db.execute(
                select(BusinessEntity).where(
                    BusinessEntity.id == entity_id,
                )
            )
            entity = entity_result.scalar_one_or_none()
        except Exception as exc:
            logger.error(
                "explainability.entity_link.entity_error",
                **safe_error_log(exc, context="explain_entity_link_entity"),
            )
            entity = None

        if not document or not entity:
            return self._not_found_explanation(
                "entity_linking",
                "Dokument oder Entitaet nicht gefunden oder kein Zugriff.",
            )

        # Link-Datensatz laden (falls vorhanden)
        link_type: Optional[str] = None
        link_confidence: float = 0.0
        link_metadata: Dict[str, Union[str, float, int]] = {}
        try:
            link_result = await db.execute(
                select(DocumentEntityLink).where(
                    DocumentEntityLink.document_id == document_id,
                    DocumentEntityLink.entity_id == entity_id,
                    DocumentEntityLink.company_id == company_id,
                )
            )
            link = link_result.scalar_one_or_none()
            if link:
                link_type = link.link_type
                link_confidence = float(link.confidence or 0.8)
                link_metadata = link.link_metadata or {}
        except Exception as exc:
            logger.warning(
                "explainability.entity_link.link_error",
                **safe_error_log(exc, context="explain_entity_link_link"),
            )

        if link_confidence == 0.0:
            link_confidence = 0.80  # Fallback wenn direkt verknuepft

        entity_name = entity.name or "Unbekannte Entitaet"
        link_type_german = _link_type_german(link_type)

        # Uebereinstimmungskriterien aufbauen
        matching_criteria: List[Dict[str, str]] = []
        extracted_text = document.extracted_text or ""

        # Namensuebereinstimmung pruefen
        if entity_name and entity_name.lower() in extracted_text.lower():
            matching_criteria.append({
                "field": "Firmenname",
                "pattern": entity_name,
                "description": f"Name '{entity_name}' im Dokumenttext gefunden.",
            })

        # USt-ID pruefen
        entity_vat = getattr(entity, "vat_id", None) or ""
        if entity_vat and entity_vat in extracted_text:
            matching_criteria.append({
                "field": "USt-Identifikationsnummer",
                "pattern": entity_vat,
                "description": f"USt-ID '{entity_vat}' im Dokument erkannt.",
            })

        # Adresse pruefen
        entity_city = getattr(entity, "city", None) or ""
        if entity_city and entity_city.lower() in extracted_text.lower():
            matching_criteria.append({
                "field": "Ort",
                "pattern": entity_city,
                "description": f"Ort '{entity_city}' stimmt mit Entitaets-Adresse ueberein.",
            })

        # Link-Metadaten als Kriterium
        if link_metadata:
            for key, value in list(link_metadata.items())[:2]:
                matching_criteria.append({
                    "field": key,
                    "pattern": str(value),
                    "description": f"Uebereinstimmung im Feld '{key}': {value}",
                })

        # Falls keine direkten Kriterien gefunden: generische Angabe
        if not matching_criteria:
            matching_criteria.append({
                "field": "Verknuepfungstyp",
                "pattern": link_type or "auto",
                "description": (
                    "Verknuepfung durch automatische Dokumentanalyse oder manuelle Zuordnung."
                ),
            })

        # Faktoren
        factors: List[ExplanationFactor] = [
            {
                "feature": "Entitaets-Name",
                "weight": 0.40,
                "description": f"Entitaet: {entity_name}",
            },
            {
                "feature": "Verknuepfungstyp",
                "weight": 0.30,
                "description": f"Art der Verknuepfung: {link_type_german}",
            },
            {
                "feature": "Uebereinstimmungskriterien",
                "weight": 0.20,
                "description": f"{len(matching_criteria)} Uebereinstimmung(en) gefunden.",
            },
            {
                "feature": "Konfidenz",
                "weight": 0.10,
                "description": f"Verknuepfungskonfidenz: {link_confidence * 100:.0f}%.",
            },
        ]

        # Alternativen
        alternatives: List[AlternativeDecision] = [
            {"category": "Keine Entitaet verknuepfen", "confidence": round(1.0 - link_confidence, 2)},
        ]

        conf_label = _confidence_label(link_confidence)
        criteria_count = len(matching_criteria)
        explanation_text = (
            f"Dieses Dokument wurde mit der Entitaet '{entity_name}' verknuepft "
            f"(Typ: {link_type_german}), weil {conf_label} Uebereinstimmung "
            f"({link_confidence * 100:.0f}%) festgestellt wurde. "
        )
        if criteria_count > 0:
            field_list = ", ".join(c["field"] for c in matching_criteria[:3])
            explanation_text += (
                f"{criteria_count} Kriterium/Kriterien stimmen ueberein: {field_list}."
            )

        logger.info(
            "explainability.entity_link.done",
            document_id=str(document_id),
            entity_id=str(entity_id),
            link_type=link_type,
            confidence=link_confidence,
        )

        return {
            "document_id": str(document_id),
            "entity_id": str(entity_id),
            "entity_name": entity_name,
            "match_score": round(link_confidence, 3),
            "link_type": link_type or "auto",
            "matching_criteria": matching_criteria,
            "explanation_text": explanation_text,
            "factors": factors,
            "confidence": round(link_confidence, 3),
            "alternatives": alternatives,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # -------------------------------------------------------------------
    # Private Hilfsmethoden
    # -------------------------------------------------------------------

    def _not_found_explanation(
        self,
        explanation_type: str,
        reason: str,
    ) -> Dict[str, Union[str, float, List[ExplanationFactor], List[AlternativeDecision]]]:
        """
        Liefert eine standardisierte "Nicht gefunden"-Erklaerung.

        Wirft keine Exception, sondern gibt eine erklaerende Antwort zurueck,
        die dem Frontend einen sinnvollen Hinweis gibt.

        Args:
            explanation_type: Bezeichnung des Erklaerungstyps (fuer Logging)
            reason: Deutscher Grund fuer die fehlende Erklaerung

        Returns:
            Standardisierte Erklaerungsstruktur mit confidence=0
        """
        logger.warning(
            "explainability.not_found",
            explanation_type=explanation_type,
            reason=reason,
        )
        return {
            "explanation_text": (
                f"Keine Erklaerung verfuegbar: {reason} "
                "Bitte pruefen Sie die ID und Ihre Zugriffsrechte."
            ),
            "factors": [],
            "confidence": 0.0,
            "alternatives": [],
            "error": "not_found",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _extract_classification_keywords(
        self,
        text: str,
        doc_type: str,
    ) -> List[str]:
        """
        Extrahiert typische Schluesselwoerter aus dem OCR-Text anhand des Dokumenttyps.

        Args:
            text: Extrahierter OCR-Text
            doc_type: Interner Dokumenttyp-Schluessel

        Returns:
            Liste gefundener Schluesselwoerter (deutsch)
        """
        text_lower = text.lower()
        keyword_map: Dict[str, List[str]] = {
            "invoice": [
                "rechnung", "rechnungsnummer", "betrag", "mwst", "umsatzsteuer",
                "zahlungsziel", "faellig", "lieferant", "iban",
            ],
            "order": [
                "bestellung", "auftrag", "bestellnummer", "liefertermin",
                "menge", "artikel",
            ],
            "delivery_note": [
                "lieferschein", "lieferung", "versand", "paket", "ware",
                "empfaenger",
            ],
            "contract": [
                "vertrag", "vereinbarung", "laufzeit", "kuendigung",
                "vertragspartner", "unterschrift",
            ],
            "credit_note": [
                "gutschrift", "stornierung", "erstattung", "rueckzahlung",
            ],
            "dunning": [
                "mahnung", "zahlungserinnerung", "verzug", "mahngebuehr",
                "faellig",
            ],
            "bank_statement": [
                "kontoauszug", "kontonummer", "saldo", "buchung", "iban",
                "gutschrift", "lastschrift",
            ],
        }
        keywords_to_check = keyword_map.get(doc_type, [])
        return [kw for kw in keywords_to_check if kw in text_lower]

    def _get_alternative_doc_types(self, current_type: str) -> List[str]:
        """
        Liefert plausible alternative Dokumenttypen zur aktuellen Klassifikation.

        Args:
            current_type: Aktuell zugewiesener Typ

        Returns:
            Liste alternativer Typen (ohne den aktuellen)
        """
        all_types = [
            "invoice", "order", "delivery_note", "contract",
            "credit_note", "dunning", "bank_statement", "receipt",
            "letter", "report", "other",
        ]
        return [t for t in all_types if t != current_type][:4]

    def _extract_trigger_conditions(
        self,
        anomaly_type: str,
        details: Dict[str, Union[str, float, int]],
    ) -> List[str]:
        """
        Leitet Ausloesebedingungen aus Anomalie-Details ab.

        Args:
            anomaly_type: Typ der Anomalie
            details: JSONB-Details der Anomalie

        Returns:
            Liste deutscher Bedingungsbeschreibungen
        """
        conditions: List[str] = []
        type_lower = anomaly_type.lower()

        if "high_amount" in type_lower or "amount" in type_lower:
            if "amount" in details:
                conditions.append(
                    f"Betrag von {details['amount']} EUR liegt ueber dem Schwellenwert."
                )
            if "median" in details:
                conditions.append(
                    f"Historischer Median: {details['median']} EUR."
                )

        if "duplicate" in type_lower:
            if "invoice_number" in details:
                conditions.append(
                    f"Rechnungsnummer '{details['invoice_number']}' bereits vorhanden."
                )
            if "count" in details:
                conditions.append(
                    f"Duplikat {details['count']}x gefunden."
                )

        if "date" in type_lower or "future" in type_lower or "weekend" in type_lower:
            if "invoice_date" in details:
                conditions.append(
                    f"Rechnungsdatum: {details['invoice_date']}."
                )

        if "vat" in type_lower or "mwst" in type_lower:
            conditions.append("Fehlende oder ungueltige USt-Identifikationsnummer.")

        if "supplier" in type_lower or "new_supplier" in type_lower:
            if "supplier" in details:
                conditions.append(
                    f"Erstbestellung bei unbekanntem Lieferant '{details['supplier']}'."
                )

        if not conditions and details:
            # Generische Bedingungen aus vorhandenen Details
            for key, value in list(details.items())[:2]:
                conditions.append(f"{key}: {value}")

        if not conditions:
            conditions.append("Anomalie-Erkennung basierend auf statistischem Modell.")

        return conditions

    def _build_historical_context(
        self,
        anomaly_type: str,
        details: Dict[str, Union[str, float, int]],
        score: float,
    ) -> str:
        """
        Erstellt deutschen historischen Kontexttext fuer eine Anomalie.

        Args:
            anomaly_type: Typ der Anomalie
            details: JSONB-Details
            score: Erkennungsscore (0-1)

        Returns:
            Deutscher Kontexttext
        """
        risk_level = (
            "hoch" if score > 0.7
            else "mittel" if score > 0.4
            else "niedrig"
        )
        context = (
            f"Das Risikopotenzial dieser Anomalie wird als '{risk_level}' eingeschaetzt "
            f"(Score: {score * 100:.0f}%). "
        )
        if "high_amount" in anomaly_type.lower():
            context += (
                "Aehnliche Betragsabweichungen treten bei diesem Mandanten selten auf. "
                "Eine manuelle Pruefung ist empfohlen."
            )
        elif "duplicate" in anomaly_type.lower():
            context += (
                "Doppelte Rechnungsnummern koennen auf Eingabefehler oder "
                "Betrugsversuche hinweisen."
            )
        else:
            context += (
                "Vergleich mit historischen Werten empfehlenswert, "
                "bevor eine Aktion eingeleitet wird."
            )
        return context
