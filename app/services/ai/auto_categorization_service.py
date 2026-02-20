# -*- coding: utf-8 -*-
"""
AutoCategorizationService - Automatische Dokument-Kategorisierung.

Erkennt Dokumenttypen (Rechnung, Vertrag, Lieferschein, etc.) mit
Confidence-basierter Autonomie.

Ziel-Konfidenz: 95%+ für Auto-Apply.

Feinpoliert und durchdacht - nutzt bestehende QuickClassificationService Patterns.
"""

from __future__ import annotations

import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Union

import structlog
from prometheus_client import Counter, Histogram
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, Tag, CompanySettings
from app.services.ai.decision_service import (
    AIDecisionService,
    AIDecisionResult,
    DecisionType,
    get_ai_decision_service,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

CATEGORIZATION_REQUESTS = Counter(
    "auto_categorization_requests_total",
    "Anzahl der Auto-Kategorisierungs-Anfragen",
    ["category", "confidence_level"]
)

CATEGORIZATION_DURATION = Histogram(
    "auto_categorization_duration_seconds",
    "Dauer der Auto-Kategorisierung in Sekunden",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0]
)


# =============================================================================
# Kategorien und Keywords
# =============================================================================

class DocumentCategory:
    """Standard Dokumentkategorien."""
    INVOICE_INCOMING = "invoice_incoming"  # Eingangsrechnung
    INVOICE_OUTGOING = "invoice_outgoing"  # Ausgangsrechnung
    DELIVERY_NOTE = "delivery_note"  # Lieferschein
    ORDER = "order"  # Bestellung
    CONTRACT = "contract"  # Vertrag
    OFFER = "offer"  # Angebot
    REMINDER = "reminder"  # Mahnung
    CREDIT_NOTE = "credit_note"  # Gutschrift
    RECEIPT = "receipt"  # Quittung/Beleg
    BANK_STATEMENT = "bank_statement"  # Kontoauszug
    TAX_DOCUMENT = "tax_document"  # Steuerdokument
    CORRESPONDENCE = "correspondence"  # Korrespondenz
    OTHER = "other"  # Sonstiges


@dataclass
class CategoryPattern:
    """Pattern für Kategorie-Erkennung."""
    category: str
    display_name: str  # Deutscher Name
    keywords: List[str]
    regex_patterns: List[str] = field(default_factory=list)
    weight: float = 1.0
    priority: int = 0  # Höher = wichtiger bei Konflikten


# Kategorie-Patterns mit deutschen Keywords
CATEGORY_PATTERNS: List[CategoryPattern] = [
    CategoryPattern(
        category=DocumentCategory.INVOICE_INCOMING,
        display_name="Eingangsrechnung",
        keywords=[
            "rechnung", "invoice", "rechnungsnummer", "rg-nr", "re-nr",
            "rechnungsdatum", "zahlungsziel", "fällig am", "fällig am",
            "überweisen", "überweisen", "bankverbindung", "iban",
            "nettobetrag", "bruttobetrag", "mwst", "ust-id",
        ],
        regex_patterns=[
            r"rechnung\s*(nr\.?|nummer):?\s*\d+",
            r"rg[\-\.]?nr\.?\s*:?\s*\d+",
            r"invoice\s*(no\.?|number):?\s*\d+",
            r"(betrag|summe|total):\s*[\d\.,]+\s*€",
        ],
        weight=1.0,
        priority=5,
    ),
    CategoryPattern(
        category=DocumentCategory.INVOICE_OUTGOING,
        display_name="Ausgangsrechnung",
        keywords=[
            "rechnung", "wir berechnen", "wir stellen", "unsere rechnung",
            "lieferung vom", "leistung vom", "sehr geehrte",
        ],
        regex_patterns=[
            r"wir\s+(?:berechnen|stellen)",
            r"unsere\s+rechnung",
            r"leistungszeitraum:\s*\d",
        ],
        weight=0.9,
        priority=4,
    ),
    CategoryPattern(
        category=DocumentCategory.DELIVERY_NOTE,
        display_name="Lieferschein",
        keywords=[
            "lieferschein", "lieferung", "warenausgang", "versand",
            "lieferadresse", "empfänger", "empfänger", "lieferdatum",
            "delivery note", "packing slip", "artikelnummer",
        ],
        regex_patterns=[
            r"lieferschein\s*(nr\.?|nummer):?\s*\d+",
            r"ls[\-\.]?nr\.?\s*:?\s*\d+",
        ],
        weight=1.0,
        priority=6,
    ),
    CategoryPattern(
        category=DocumentCategory.ORDER,
        display_name="Bestellung",
        keywords=[
            "bestellung", "order", "auftrag", "bestellnummer",
            "auftragsbestätigung", "auftragsbestätigung", "po number",
            "purchase order", "wir bestellen", "hiermit bestellen",
        ],
        regex_patterns=[
            r"bestell(ung)?[\-\.]?(nr\.?|nummer):?\s*\d+",
            r"order\s*(no\.?|number):?\s*\d+",
            r"po[\-\.]?(nr\.?|number)?:?\s*\d+",
        ],
        weight=1.0,
        priority=5,
    ),
    CategoryPattern(
        category=DocumentCategory.CONTRACT,
        display_name="Vertrag",
        keywords=[
            "vertrag", "vereinbarung", "contract", "agreement",
            "vertragspartner", "vertragsgegenstand", "laufzeit",
            "kündigungsfrist", "kündigungsfrist", "unterzeichnet",
            "geschäftsführer", "geschäftsführer", "prokurist",
        ],
        regex_patterns=[
            r"vertrag\s*(nr\.?|nummer):?\s*\d+",
            r"§\s*\d+",  # Paragraphen
            r"zwischen\s+.+\s+und\s+.+\s+wird",
        ],
        weight=1.2,
        priority=7,
    ),
    CategoryPattern(
        category=DocumentCategory.OFFER,
        display_name="Angebot",
        keywords=[
            "angebot", "offer", "quotation", "kostenvoranschlag",
            "angebotsnummer", "gültig bis", "gültig bis",
            "wir bieten", "wir unterbreiten", "freibleibend",
        ],
        regex_patterns=[
            r"angebot\s*(nr\.?|nummer):?\s*\d+",
            r"gültig\s+bis:?\s*\d",
            r"gültig\s+bis:?\s*\d",
        ],
        weight=1.0,
        priority=5,
    ),
    CategoryPattern(
        category=DocumentCategory.REMINDER,
        display_name="Mahnung",
        keywords=[
            "mahnung", "zahlungserinnerung", "payment reminder",
            "überfällig", "überfällig", "verzug", "mahngebühr",
            "mahngebühr", "inkasso", "letzte mahnung", "zahlungsaufforderung",
        ],
        regex_patterns=[
            r"(erste|zweite|dritte|letzte)?\s*mahnung",
            r"\d+\s*tage\s+überfällig",
            r"zahlungsziel\s+überschritten",
        ],
        weight=1.2,
        priority=8,
    ),
    CategoryPattern(
        category=DocumentCategory.CREDIT_NOTE,
        display_name="Gutschrift",
        keywords=[
            "gutschrift", "stornorechnung", "credit note", "korrektur",
            "rechnungskorrektur", "erstattung", "rückerstattung",
        ],
        regex_patterns=[
            r"gutschrift\s*(nr\.?|nummer):?\s*\d+",
            r"zu\s+rechnung\s*(nr\.?|nummer)?:?\s*\d+",
        ],
        weight=1.1,
        priority=6,
    ),
    CategoryPattern(
        category=DocumentCategory.RECEIPT,
        display_name="Quittung/Beleg",
        keywords=[
            "quittung", "beleg", "kassenbon", "receipt",
            "bar bezahlt", "zahlungsbeleg", "tankquittung",
            "ec-beleg", "kartenzahlung",
        ],
        regex_patterns=[
            r"bar\s*:?\s*[\d\.,]+\s*€",
            r"(kasse|kassen)[\-\.]?nr",
        ],
        weight=0.9,
        priority=4,
    ),
    CategoryPattern(
        category=DocumentCategory.BANK_STATEMENT,
        display_name="Kontoauszug",
        keywords=[
            "kontoauszug", "bank statement", "kontoumsätze",
            "habenumsatz", "sollumsatz", "kontostand", "buchungstag",
            "wertstellung", "verwendungszweck",
        ],
        regex_patterns=[
            r"kontoauszug\s*(nr\.?|nummer)?:?\s*\d+",
            r"(soll|haben):\s*[\d\.,]+",
            r"kontostand\s+neu",
        ],
        weight=1.0,
        priority=6,
    ),
    CategoryPattern(
        category=DocumentCategory.TAX_DOCUMENT,
        display_name="Steuerdokument",
        keywords=[
            "steuerbescheid", "umsatzsteuer-voranmeldung", "elster",
            "finanzamt", "steuernummer", "steuer-id", "steuererklärung",
            "steuererklärung", "einkommenssteuer", "gewerbesteuer",
        ],
        regex_patterns=[
            r"finanzamt\s+\w+",
            r"steuer[\-\.]?(id|nummer):\s*\d+",
        ],
        weight=1.2,
        priority=7,
    ),
    CategoryPattern(
        category=DocumentCategory.CORRESPONDENCE,
        display_name="Korrespondenz",
        keywords=[
            "sehr geehrte", "mit freundlichen", "betreff",
            "bezugnehmend auf", "in bezug auf", "ihr schreiben",
        ],
        regex_patterns=[],
        weight=0.5,  # Niedriger Score da oft generisch
        priority=1,
    ),
]


@dataclass
class CategorizationResult:
    """Ergebnis der Kategorisierung."""
    category: str
    display_name: str
    confidence: float
    matched_keywords: List[str] = field(default_factory=list)
    matched_patterns: List[str] = field(default_factory=list)
    secondary_categories: List[Tuple[str, float]] = field(default_factory=list)


class AutoCategorizationService:
    """
    Automatische Dokument-Kategorisierung mit KI-Autonomie.

    Analysiert OCR-Text und weist Kategorien basierend auf
    Pattern-Matching und Keyword-Erkennung zu.
    """

    def __init__(self) -> None:
        """Initialisiert den Service."""
        self._decision_service = get_ai_decision_service()

    def _normalize_text(self, text: str) -> str:
        """Normalisiert Text für Pattern-Matching."""
        # Lowercase, mehrfache Leerzeichen entfernen
        text = text.lower()
        text = re.sub(r'\s+', ' ', text)
        return text

    def _calculate_category_score(
        self,
        text: str,
        pattern: CategoryPattern,
    ) -> Tuple[float, List[str], List[str]]:
        """
        Berechnet Score für eine Kategorie.

        Returns:
            Tuple (score, matched_keywords, matched_patterns)
        """
        normalized_text = self._normalize_text(text)
        matched_keywords: List[str] = []
        matched_patterns: List[str] = []

        # Keyword-Matching
        keyword_score = 0.0
        for keyword in pattern.keywords:
            if keyword.lower() in normalized_text:
                matched_keywords.append(keyword)
                # Gewichtung nach Position (früh im Text = wichtiger)
                pos = normalized_text.find(keyword.lower())
                position_weight = 1.0 - (pos / len(normalized_text)) * 0.3
                keyword_score += position_weight

        # Regex-Matching (höhere Gewichtung)
        regex_score = 0.0
        for regex in pattern.regex_patterns:
            try:
                if re.search(regex, normalized_text, re.IGNORECASE):
                    matched_patterns.append(regex)
                    regex_score += 2.0  # Regex-Matches zaehlen doppelt
            except re.error:
                logger.warning(
                    "invalid_regex_pattern",
                    pattern=regex,
                    category=pattern.category,
                )

        # Gesamt-Score normalisieren
        max_keyword_score = len(pattern.keywords) * 1.0
        max_regex_score = len(pattern.regex_patterns) * 2.0
        max_total = max_keyword_score + max_regex_score

        if max_total == 0:
            return 0.0, matched_keywords, matched_patterns

        raw_score = (keyword_score + regex_score) / max_total
        weighted_score = raw_score * pattern.weight

        # Confidence-Mapping (0.0-1.0)
        # Mindestens 3 Keywords oder 1 Regex für brauchbaren Score
        if len(matched_keywords) < 2 and len(matched_patterns) == 0:
            weighted_score *= 0.5  # Unsicher

        # Auf 0.0-1.0 clippen
        confidence = min(max(weighted_score, 0.0), 1.0)

        return confidence, matched_keywords, matched_patterns

    def categorize_text(
        self,
        text: str,
        min_confidence: float = 0.3,
    ) -> CategorizationResult:
        """
        Kategorisiert einen Text.

        Args:
            text: OCR-Text des Dokuments
            min_confidence: Minimale Konfidenz für Ergebnis

        Returns:
            CategorizationResult
        """
        start_time = time.perf_counter()

        # Limitiere Text-Länge
        if len(text) > 50000:
            text = text[:50000]

        best_result: Optional[CategorizationResult] = None
        all_results: List[Tuple[str, float]] = []

        for pattern in CATEGORY_PATTERNS:
            score, keywords, regexes = self._calculate_category_score(text, pattern)

            if score >= min_confidence:
                all_results.append((pattern.category, score))

                if best_result is None or score > best_result.confidence:
                    best_result = CategorizationResult(
                        category=pattern.category,
                        display_name=pattern.display_name,
                        confidence=score,
                        matched_keywords=keywords,
                        matched_patterns=regexes,
                    )
                elif score == best_result.confidence:
                    # Bei Gleichstand: Priorität entscheidet
                    current_pattern = next(
                        (p for p in CATEGORY_PATTERNS if p.category == best_result.category),
                        None,
                    )
                    if current_pattern and pattern.priority > current_pattern.priority:
                        best_result = CategorizationResult(
                            category=pattern.category,
                            display_name=pattern.display_name,
                            confidence=score,
                            matched_keywords=keywords,
                            matched_patterns=regexes,
                        )

        # Fallback auf OTHER
        if best_result is None:
            best_result = CategorizationResult(
                category=DocumentCategory.OTHER,
                display_name="Sonstiges",
                confidence=0.5,  # Niedrige Konfidenz für unbekannt
            )

        # Sekundaere Kategorien hinzufuegen
        all_results.sort(key=lambda x: x[1], reverse=True)
        best_result.secondary_categories = [
            (cat, conf) for cat, conf in all_results
            if cat != best_result.category
        ][:3]  # Top 3 Alternativen

        duration = time.perf_counter() - start_time
        CATEGORIZATION_DURATION.observe(duration)

        return best_result

    async def categorize_document(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        text: str,
        company_id: Optional[uuid.UUID] = None,
        auto_apply_tags: bool = True,
    ) -> AIDecisionResult:
        """
        Kategorisiert ein Dokument mit AI-Autonomie.

        Args:
            db: Database Session
            document_id: Dokument-ID
            text: OCR-Text
            company_id: Optional Company-ID
            auto_apply_tags: Ob Tags automatisch zugewiesen werden sollen

        Returns:
            AIDecisionResult
        """
        # Kategorisierung durchführen
        result = self.categorize_text(text)

        # Explanation erstellen
        explanation = {
            "reasons": [],
            "matched_keywords": result.matched_keywords[:10],
            "matched_patterns": result.matched_patterns[:5],
            "secondary_categories": [
                {"category": cat, "confidence": round(conf, 3)}
                for cat, conf in result.secondary_categories
            ],
        }

        if result.matched_keywords:
            explanation["reasons"].append(
                f"Gefundene Keywords: {', '.join(result.matched_keywords[:5])}"
            )
        if result.matched_patterns:
            explanation["reasons"].append(
                f"Erkannte Muster: {len(result.matched_patterns)} Pattern-Matches"
            )

        # Decision Value
        decision_value = {
            "category": result.category,
            "display_name": result.display_name,
            "secondary_categories": [
                {"category": cat, "confidence": round(conf, 3)}
                for cat, conf in result.secondary_categories
            ],
        }

        # Callback für Auto-Apply
        async def apply_category(value: Dict[str, Union[str, List[Dict[str, Union[str, float]]]]]) -> None:
            """Wendet Kategorie auf Dokument an."""
            if not auto_apply_tags:
                return

            # Lade Document und setze Kategorie
            doc_result = await db.execute(
                select(Document).where(Document.id == document_id)
            )
            doc = doc_result.scalar_one_or_none()
            if doc:
                doc.document_category = value["category"]
                await db.commit()
                logger.info(
                    "category_auto_applied",
                    document_id=str(document_id),
                    category=value["category"],
                )

        # Entscheidung erstellen
        ai_result = await self._decision_service.make_decision(
            db=db,
            decision_type=DecisionType.CATEGORIZATION,
            decision_value=decision_value,
            confidence=result.confidence,
            document_id=document_id,
            company_id=company_id,
            explanation=explanation,
            features_used={
                "text_length": len(text),
                "keyword_count": len(result.matched_keywords),
                "pattern_count": len(result.matched_patterns),
            },
            apply_callback=apply_category if auto_apply_tags else None,
        )

        # Metriken
        CATEGORIZATION_REQUESTS.labels(
            category=result.category,
            confidence_level=ai_result.confidence_level.value,
        ).inc()

        return ai_result

    async def get_category_suggestions(
        self,
        text: str,
        limit: int = 5,
    ) -> List[Dict[str, Union[str, float, bool]]]:
        """
        Gibt Kategorie-Vorschläge ohne Persistenz zurück.

        Args:
            text: OCR-Text
            limit: Max Anzahl Vorschläge

        Returns:
            Liste von Vorschlägen mit Kategorie und Konfidenz
        """
        result = self.categorize_text(text)

        suggestions = [
            {
                "category": result.category,
                "display_name": result.display_name,
                "confidence": round(result.confidence, 3),
                "is_primary": True,
            }
        ]

        for cat, conf in result.secondary_categories[:limit - 1]:
            pattern = next(
                (p for p in CATEGORY_PATTERNS if p.category == cat),
                None,
            )
            suggestions.append({
                "category": cat,
                "display_name": pattern.display_name if pattern else cat,
                "confidence": round(conf, 3),
                "is_primary": False,
            })

        return suggestions


# Singleton-Instanz mit Thread-Safety
_auto_categorization_service: Optional[AutoCategorizationService] = None
_service_lock = threading.Lock()


def get_auto_categorization_service() -> AutoCategorizationService:
    """Factory für AutoCategorizationService Singleton (Thread-safe)."""
    global _auto_categorization_service
    if _auto_categorization_service is None:
        with _service_lock:
            # Double-check locking pattern
            if _auto_categorization_service is None:
                _auto_categorization_service = AutoCategorizationService()
    return _auto_categorization_service
