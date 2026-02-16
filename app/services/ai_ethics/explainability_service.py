"""
Explainability Service

Erklärt KI-Entscheidungen in verstaendlicher Sprache.
Zeigt Faktoren, Gewichtungen und Alternativen.

Feinpoliert und durchdacht - Enterprise AI Explainability.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Dict, Optional
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    BusinessEntity,
    Document,
    InvoiceTracking,
    RiskScoreHistory,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class ExplanationFactor:
    """Einzelner Erklärungsfaktor."""

    name: str  # Faktor-Name (German)
    weight: float  # Gewichtung (0-1)
    value: str  # Wert (formatiert)
    impact: str  # positive, negative, neutral
    description: str  # German Beschreibung

    def to_dict(self) -> Dict[str, any]:
        """Konvertiert zu Dictionary."""
        return {
            "name": self.name,
            "weight": round(self.weight, 3),
            "value": self.value,
            "impact": self.impact,
            "description": self.description,
        }


@dataclass
class Explanation:
    """Vollständige Erklärung einer KI-Entscheidung."""

    decision_type: str  # risk_score, document_classification, etc.
    summary: str  # German Zusammenfassung
    factors: List[ExplanationFactor]  # Einzelne Faktoren
    confidence: float  # 0-1
    alternatives_considered: List[str]  # German

    def to_dict(self) -> Dict[str, any]:
        """Konvertiert zu Dictionary."""
        return {
            "decision_type": self.decision_type,
            "summary": self.summary,
            "factors": [f.to_dict() for f in self.factors],
            "confidence": round(self.confidence, 3),
            "alternatives_considered": self.alternatives_considered,
        }


# =============================================================================
# Explainability Service
# =============================================================================


class ExplainabilityService:
    """
    Explainability Service für KI-Entscheidungen.

    Unterstützt:
    - Risk Score Erklärungen
    - Document Classification Erklärungen
    - Auto-Approval Erklärungen
    """

    def __init__(self) -> None:
        """Initialisiert Service."""
        pass

    async def explain_decision(
        self,
        decision_id: UUID,
        decision_type: str,
        db: AsyncSession,
    ) -> Optional[Explanation]:
        """
        Erklärt KI-Entscheidung.

        Args:
            decision_id: ID der Entscheidung (Entity, Document, etc.)
            decision_type: Typ (risk_score, classification, approval)
            db: Database session

        Returns:
            Explanation oder None
        """
        logger.info(
            "explainability.explain",
            decision_id=str(decision_id),
            decision_type=decision_type,
        )

        if decision_type == "risk_score":
            return await self._explain_risk_score(decision_id, db)
        elif decision_type == "document_classification":
            return await self._explain_classification(decision_id, db)
        elif decision_type == "auto_approval":
            return await self._explain_auto_approval(decision_id, db)
        else:
            logger.warning("explainability.unknown_type", decision_type=decision_type)
            return None

    async def _explain_risk_score(
        self,
        entity_id: UUID,
        db: AsyncSession,
    ) -> Optional[Explanation]:
        """
        Erklärt Risk Score Berechnung.

        Args:
            entity_id: Entity UUID
            db: Database session

        Returns:
            Explanation
        """
        entity = await db.get(BusinessEntity, entity_id)
        if not entity:
            return None

        risk_score = entity.risk_score or 0
        risk_factors = entity.risk_factors or {}

        # Extrahiere Faktoren aus JSONB
        payment_delay = risk_factors.get("payment_delay_days", 0)
        default_rate = risk_factors.get("default_rate", 0) * 100  # Als Prozent
        invoice_volume = risk_factors.get("invoice_volume", 0)
        relationship_months = risk_factors.get("relationship_months", 0)
        total_invoices = risk_factors.get("total_invoices", 0)

        # Erstelle Faktoren
        factors: List[ExplanationFactor] = []

        # 1. Zahlungsverzögerung (35%)
        if payment_delay > 30:
            impact = "negative"
            desc = f"Zahlungen durchschnittlich {payment_delay:.0f} Tage verspätet (kritisch)"
        elif payment_delay > 14:
            impact = "negative"
            desc = f"Zahlungen durchschnittlich {payment_delay:.0f} Tage verspätet (moderat)"
        else:
            impact = "positive"
            desc = f"Zahlungen pünktlich (Ø {payment_delay:.0f} Tage)"

        factors.append(
            ExplanationFactor(
                name="Zahlungsverhalten",
                weight=0.35,
                value=f"{payment_delay:.0f} Tage Verzögerung",
                impact=impact,
                description=desc,
            )
        )

        # 2. Ausfallrate (25%)
        if default_rate > 20:
            impact = "negative"
            desc = f"Hohe Ausfallrate: {default_rate:.1f}% der Rechnungen überfällig"
        elif default_rate > 10:
            impact = "negative"
            desc = f"Moderate Ausfallrate: {default_rate:.1f}% der Rechnungen überfällig"
        else:
            impact = "positive"
            desc = f"Niedrige Ausfallrate: {default_rate:.1f}%"

        factors.append(
            ExplanationFactor(
                name="Ausfallrate",
                weight=0.25,
                value=f"{default_rate:.1f}%",
                impact=impact,
                description=desc,
            )
        )

        # 3. Rechnungsvolumen (15%)
        if invoice_volume > 50000:
            impact = "positive"
            desc = f"Hohes Rechnungsvolumen: {invoice_volume:,.0f} EUR (reduziert Risiko)"
        elif invoice_volume > 10000:
            impact = "neutral"
            desc = f"Moderates Rechnungsvolumen: {invoice_volume:,.0f} EUR"
        else:
            impact = "negative"
            desc = f"Niedriges Rechnungsvolumen: {invoice_volume:,.0f} EUR (erhöht Risiko)"

        factors.append(
            ExplanationFactor(
                name="Rechnungsvolumen",
                weight=0.15,
                value=f"{invoice_volume:,.0f} EUR",
                impact=impact,
                description=desc,
            )
        )

        # 4. Beziehungsdauer (15%)
        if relationship_months > 24:
            impact = "positive"
            desc = f"Langjährige Beziehung: {relationship_months:.0f} Monate (reduziert Risiko)"
        elif relationship_months > 12:
            impact = "neutral"
            desc = f"Etablierte Beziehung: {relationship_months:.0f} Monate"
        else:
            impact = "negative"
            desc = f"Neue Beziehung: {relationship_months:.0f} Monate (erhöht Risiko)"

        factors.append(
            ExplanationFactor(
                name="Beziehungsdauer",
                weight=0.15,
                value=f"{relationship_months:.0f} Monate",
                impact=impact,
                description=desc,
            )
        )

        # 5. Transaktionsfrequenz (10%)
        doc_frequency = risk_factors.get("document_frequency", 0)
        if doc_frequency > 5:
            impact = "positive"
            desc = f"Regelmäßige Transaktionen: {doc_frequency:.1f} Dokumente/Monat"
        elif doc_frequency > 2:
            impact = "neutral"
            desc = f"Moderate Transaktionen: {doc_frequency:.1f} Dokumente/Monat"
        else:
            impact = "negative"
            desc = f"Seltene Transaktionen: {doc_frequency:.1f} Dokumente/Monat"

        factors.append(
            ExplanationFactor(
                name="Transaktionsfrequenz",
                weight=0.10,
                value=f"{doc_frequency:.1f}/Monat",
                impact=impact,
                description=desc,
            )
        )

        # Zusammenfassung
        if risk_score < 30:
            risk_level = "NIEDRIG"
            summary = f"Niedriges Risiko ({risk_score:.0f}/100). Entity zeigt gutes Zahlungsverhalten und stabile Beziehung."
        elif risk_score < 60:
            risk_level = "MITTEL"
            summary = f"Mittleres Risiko ({risk_score:.0f}/100). Einige Risikofaktoren vorhanden, aber überwiegend stabil."
        else:
            risk_level = "HOCH"
            summary = f"Hohes Risiko ({risk_score:.0f}/100). Mehrere kritische Faktoren - verstärkte Überwachung empfohlen."

        alternatives = [
            "Manuelle Überprüfung bei hohem Risiko",
            "Automatische Eskalation ab Risk Score 75",
            "Zahlungsbedingungen anpassen (kürzere Fristen)",
        ]

        return Explanation(
            decision_type="risk_score",
            summary=summary,
            factors=factors,
            confidence=0.85,  # Risk Scoring ist relativ zuverlaessig
            alternatives_considered=alternatives,
        )

    async def _explain_classification(
        self,
        document_id: UUID,
        db: AsyncSession,
    ) -> Optional[Explanation]:
        """
        Erklärt Document Classification.

        Args:
            document_id: Document UUID
            db: Database session

        Returns:
            Explanation
        """
        document = await db.get(Document, document_id)
        if not document:
            return None

        doc_type = document.document_type or "unknown"
        confidence = document.ocr_confidence or 0.5
        metadata = document.document_metadata or {}

        factors: List[ExplanationFactor] = []

        # 1. Schluesselwoerter
        extracted_text = document.extracted_text or ""
        keywords = self._extract_keywords(extracted_text, doc_type)

        if keywords:
            factors.append(
                ExplanationFactor(
                    name="Schlüsselwörter",
                    weight=0.40,
                    value=", ".join(keywords[:3]),
                    impact="positive",
                    description=f"Typische Begriffe für {doc_type} erkannt",
                )
            )

        # 2. Strukturelle Merkmale
        has_tables = "table" in extracted_text.lower() or "betrag" in extracted_text.lower()
        if has_tables:
            factors.append(
                ExplanationFactor(
                    name="Strukturelle Merkmale",
                    weight=0.30,
                    value="Tabellen erkannt",
                    impact="positive",
                    description="Typische Dokumentstruktur erkannt",
                )
            )

        # 3. OCR-Konfidenz
        if confidence > 0.9:
            impact = "positive"
            desc = "Sehr hohe OCR-Qualität"
        elif confidence > 0.7:
            impact = "neutral"
            desc = "Gute OCR-Qualität"
        else:
            impact = "negative"
            desc = "Niedrige OCR-Qualität - Klassifikation unsicher"

        factors.append(
            ExplanationFactor(
                name="OCR-Konfidenz",
                weight=0.30,
                value=f"{confidence*100:.0f}%",
                impact=impact,
                description=desc,
            )
        )

        summary = f"Dokument als '{doc_type}' klassifiziert mit {confidence*100:.0f}% Konfidenz."

        alternatives = [
            "Manuelle Klassifikation bei niedriger Konfidenz",
            "Multi-Model Ansatz für bessere Genauigkeit",
        ]

        return Explanation(
            decision_type="document_classification",
            summary=summary,
            factors=factors,
            confidence=confidence,
            alternatives_considered=alternatives,
        )

    async def _explain_auto_approval(
        self,
        invoice_id: UUID,
        db: AsyncSession,
    ) -> Optional[Explanation]:
        """
        Erklärt Auto-Approval Entscheidung.

        Args:
            invoice_id: Invoice UUID
            db: Database session

        Returns:
            Explanation
        """
        invoice = await db.get(InvoiceTracking, invoice_id)
        if not invoice:
            return None

        # Lade zugehoerige Daten für Erklärung
        factors: List[ExplanationFactor] = []
        total_confidence = 0.0
        positive_factors = 0
        negative_factors = 0

        # 1. Betragsschwellen-Analyse
        amount = float(invoice.amount or 0)
        if amount <= 500:
            factors.append(ExplanationFactor(
                name="Betragsschwelle",
                weight=0.35,
                value=f"{amount:.2f} EUR",
                impact="positive",
                description="Betrag im Bereich automatischer Freigabe (bis 500 EUR)",
            ))
            total_confidence += 0.35
            positive_factors += 1
        elif amount <= 1000:
            factors.append(ExplanationFactor(
                name="Betragsschwelle",
                weight=0.25,
                value=f"{amount:.2f} EUR",
                impact="positive",
                description="Betrag im erweiterten Freigabebereich (500-1000 EUR)",
            ))
            total_confidence += 0.25
            positive_factors += 1
        else:
            factors.append(ExplanationFactor(
                name="Betragsschwelle",
                weight=0.35,
                value=f"{amount:.2f} EUR",
                impact="negative",
                description=f"Betrag über automatischer Freigabegrenze ({amount:.2f} EUR > 1000 EUR)",
            ))
            negative_factors += 1

        # 2. Lieferanten-Analyse
        from app.db.models import BusinessEntity
        entity = None
        if invoice.entity_id:
            entity = await db.get(BusinessEntity, invoice.entity_id)

        if entity:
            risk_score = getattr(entity, "risk_score", 50) or 50
            is_trusted = risk_score < 40

            if is_trusted:
                factors.append(ExplanationFactor(
                    name="Lieferanten-Status",
                    weight=0.30,
                    value=f"Risiko-Score: {risk_score}/100",
                    impact="positive",
                    description="Vertrauenswuerdiger Lieferant mit niedriger Risikobewertung",
                ))
                total_confidence += 0.30
                positive_factors += 1
            else:
                factors.append(ExplanationFactor(
                    name="Lieferanten-Status",
                    weight=0.30,
                    value=f"Risiko-Score: {risk_score}/100",
                    impact="neutral" if risk_score < 60 else "negative",
                    description=f"Lieferant mit {'mittlerer' if risk_score < 60 else 'höherer'} Risikobewertung",
                ))
                if risk_score < 60:
                    total_confidence += 0.15
                else:
                    negative_factors += 1
        else:
            factors.append(ExplanationFactor(
                name="Lieferanten-Status",
                weight=0.30,
                value="Unbekannt",
                impact="neutral",
                description="Kein Lieferant zugeordnet - neutrale Bewertung",
            ))
            total_confidence += 0.10

        # 3. Dokumenten-Qualität (basierend auf Vollständigkeit)
        doc_quality_score = 0.0
        quality_details = []

        if invoice.invoice_number:
            doc_quality_score += 0.25
            quality_details.append("Rechnungsnummer erkannt")
        if invoice.due_date:
            doc_quality_score += 0.25
            quality_details.append("Fälligkeitsdatum vorhanden")
        if invoice.amount and invoice.amount > 0:
            doc_quality_score += 0.25
            quality_details.append("Betrag erkannt")
        if invoice.entity_id:
            doc_quality_score += 0.25
            quality_details.append("Lieferant zugeordnet")

        quality_value = f"{doc_quality_score * 100:.0f}%"
        if doc_quality_score >= 0.75:
            factors.append(ExplanationFactor(
                name="Dokumenten-Qualität",
                weight=0.25,
                value=quality_value,
                impact="positive",
                description=f"Hohe Dokumentqualität: {', '.join(quality_details)}",
            ))
            total_confidence += 0.25
            positive_factors += 1
        elif doc_quality_score >= 0.50:
            factors.append(ExplanationFactor(
                name="Dokumenten-Qualität",
                weight=0.25,
                value=quality_value,
                impact="neutral",
                description=f"Mittlere Dokumentqualität: {', '.join(quality_details)}",
            ))
            total_confidence += 0.15
        else:
            factors.append(ExplanationFactor(
                name="Dokumenten-Qualität",
                weight=0.25,
                value=quality_value,
                impact="negative",
                description=f"Niedrige Dokumentqualität, fehlende Felder",
            ))
            negative_factors += 1

        # 4. Zahlungshistorie (wenn verfügbar)
        if entity:
            # Zaehle bisherige bezahlte Rechnungen
            from sqlalchemy import func
            paid_count_query = select(func.count(InvoiceTracking.id)).where(
                InvoiceTracking.entity_id == entity.id,
                InvoiceTracking.status == "paid",
            )
            paid_result = await db.execute(paid_count_query)
            paid_count = paid_result.scalar() or 0

            if paid_count >= 10:
                factors.append(ExplanationFactor(
                    name="Zahlungshistorie",
                    weight=0.10,
                    value=f"{paid_count} bezahlte Rechnungen",
                    impact="positive",
                    description="Langjaehrige positive Zahlungshistorie",
                ))
                total_confidence += 0.10
                positive_factors += 1
            elif paid_count >= 3:
                factors.append(ExplanationFactor(
                    name="Zahlungshistorie",
                    weight=0.10,
                    value=f"{paid_count} bezahlte Rechnungen",
                    impact="neutral",
                    description="Aufbauende Zahlungshistorie",
                ))
                total_confidence += 0.05

        # Berechne finale Konfidenz
        final_confidence = min(total_confidence, 0.95)
        if negative_factors > 0:
            final_confidence *= (1 - negative_factors * 0.15)

        # Generiere Summary
        if final_confidence >= 0.70 and negative_factors == 0:
            summary = f"Auto-Approval empfohlen: {positive_factors} positive Faktoren, Konfidenz {final_confidence*100:.0f}%"
            alternatives = [
                "Manuelle Freigabe bei Bedenken",
                "Vier-Augen-Prinzip ab 5000 EUR",
            ]
        elif final_confidence >= 0.50:
            summary = f"Bedingte Freigabe möglich: {positive_factors} positive, {negative_factors} kritische Faktoren"
            alternatives = [
                "Manuelle Prüfung empfohlen",
                "Rückfrage beim Lieferanten",
            ]
        else:
            summary = f"Manuelle Freigabe erforderlich: {negative_factors} kritische Faktoren identifiziert"
            alternatives = [
                "Detailprüfung durch Buchhaltung",
                "Eskalation an Vorgesetzten",
            ]

        return Explanation(
            decision_type="auto_approval",
            summary=summary,
            factors=factors,
            confidence=final_confidence,
            alternatives_considered=alternatives,
        )

    def _extract_keywords(self, text: str, doc_type: str) -> List[str]:
        """
        Extrahiert Schluesselwoerter basierend auf Dokumenttyp.

        Args:
            text: Extracted Text
            doc_type: Document Type

        Returns:
            Liste von Keywords
        """
        text_lower = text.lower()

        keyword_map = {
            "invoice": ["rechnung", "betrag", "mwst", "zahlbar"],
            "order": ["bestellung", "auftrag", "lieferung"],
            "delivery_note": ["lieferschein", "lieferung", "versand"],
            "contract": ["vertrag", "vereinbarung", "laufzeit"],
        }

        keywords_to_find = keyword_map.get(doc_type, [])
        found = [kw for kw in keywords_to_find if kw in text_lower]

        return found
