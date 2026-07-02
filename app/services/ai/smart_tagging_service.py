# -*- coding: utf-8 -*-
"""
SmartTaggingService - Intelligente automatische Dokumenten-Tags.

Analysiert OCR-Text und Dokument-Kontext um automatisch relevante Tags zuzuweisen.
Kategorien:
- Urgency: Dringend (Frist <7 Tage)
- Financial: Enthält Skonto, Hoher Betrag
- Quality: OCR unsicher, Duplikat möglich
- Action: Mahnung fällig, Genehmigung erforderlich
- Trust: Neuer Lieferant, Bekannter Partner

Vision 2026+ Feature #5: Smart Auto-Tagging
"""

from __future__ import annotations

import re
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple

import structlog
from prometheus_client import Counter, Histogram
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, Tag, BusinessEntity, InvoiceTracking

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

SMART_TAGGING_REQUESTS = Counter(
    "smart_tagging_requests_total",
    "Anzahl der Smart-Tagging-Anfragen",
    ["tag_category", "applied"]
)

SMART_TAGGING_DURATION = Histogram(
    "smart_tagging_duration_seconds",
    "Dauer der Smart-Tagging-Analyse in Sekunden",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0]
)


# =============================================================================
# Tag-Kategorien und Konfiguration
# =============================================================================

class TagCategory:
    """Tag-Kategorien für Smart Tagging."""
    URGENCY = "urgency"
    FINANCIAL = "financial"
    QUALITY = "quality"
    ACTION = "action"
    TRUST = "trust"


@dataclass
class SmartTag:
    """Ein Smart-Tag mit Metadaten."""
    name: str
    display_name: str  # Deutscher Name
    category: str
    confidence: float
    reason: str  # Deutscher Erklärungstext
    icon: str = "Tag"  # Lucide icon name
    color: str = "gray"  # Tailwind color class (ohne Praefix)
    priority: int = 0  # Höher = wichtiger für Anzeige


@dataclass
class SmartTaggingResult:
    """Ergebnis der Smart-Tagging-Analyse."""
    document_id: uuid.UUID
    suggested_tags: List[SmartTag] = field(default_factory=list)
    applied_tags: List[str] = field(default_factory=list)
    skipped_tags: List[str] = field(default_factory=list)
    analysis_metadata: Dict[str, Any] = field(default_factory=dict)


# System-definierte Smart Tags
SMART_TAG_DEFINITIONS: List[Dict[str, Any]] = [
    # Urgency Tags
    {
        "name": "dringend",
        "display_name": "Dringend",
        "category": TagCategory.URGENCY,
        "icon": "AlertTriangle",
        "color": "red",
        "priority": 100,
    },
    {
        "name": "frist-diese-woche",
        "display_name": "Frist diese Woche",
        "category": TagCategory.URGENCY,
        "icon": "Clock",
        "color": "orange",
        "priority": 90,
    },
    {
        "name": "überfällig",
        "display_name": "Überfällig",
        "category": TagCategory.URGENCY,
        "icon": "AlertOctagon",
        "color": "red",
        "priority": 110,
    },
    # Financial Tags
    {
        "name": "skonto-möglich",
        "display_name": "Skonto möglich",
        "category": TagCategory.FINANCIAL,
        "icon": "Percent",
        "color": "green",
        "priority": 80,
    },
    {
        "name": "hoher-betrag",
        "display_name": "Hoher Betrag",
        "category": TagCategory.FINANCIAL,
        "icon": "DollarSign",
        "color": "amber",
        "priority": 70,
    },
    {
        "name": "zahlungsziel-lang",
        "display_name": "Langes Zahlungsziel",
        "category": TagCategory.FINANCIAL,
        "icon": "Calendar",
        "color": "blue",
        "priority": 40,
    },
    # Quality Tags
    {
        "name": "ocr-unsicher",
        "display_name": "OCR unsicher",
        "category": TagCategory.QUALITY,
        "icon": "AlertCircle",
        "color": "yellow",
        "priority": 85,
    },
    {
        "name": "duplikat-möglich",
        "display_name": "Duplikat möglich",
        "category": TagCategory.QUALITY,
        "icon": "Copy",
        "color": "yellow",
        "priority": 75,
    },
    {
        "name": "unvollständig",
        "display_name": "Unvollständig",
        "category": TagCategory.QUALITY,
        "icon": "FileQuestion",
        "color": "yellow",
        "priority": 65,
    },
    # Action Tags
    {
        "name": "genehmigung-erforderlich",
        "display_name": "Genehmigung erforderlich",
        "category": TagCategory.ACTION,
        "icon": "CheckSquare",
        "color": "purple",
        "priority": 95,
    },
    {
        "name": "mahnung-fällig",
        "display_name": "Mahnung fällig",
        "category": TagCategory.ACTION,
        "icon": "Mail",
        "color": "red",
        "priority": 88,
    },
    {
        "name": "rückfrage-noetig",
        "display_name": "Rückfrage nötig",
        "category": TagCategory.ACTION,
        "icon": "HelpCircle",
        "color": "blue",
        "priority": 60,
    },
    # Trust Tags
    {
        "name": "neuer-lieferant",
        "display_name": "Neuer Lieferant",
        "category": TagCategory.TRUST,
        "icon": "UserPlus",
        "color": "cyan",
        "priority": 50,
    },
    {
        "name": "bekannter-partner",
        "display_name": "Bekannter Partner",
        "category": TagCategory.TRUST,
        "icon": "UserCheck",
        "color": "green",
        "priority": 30,
    },
    {
        "name": "risiko-partner",
        "display_name": "Risiko-Partner",
        "category": TagCategory.TRUST,
        "icon": "ShieldAlert",
        "color": "red",
        "priority": 92,
    },
]


class SmartTaggingService:
    """
    Intelligenter Auto-Tagging Service.

    Analysiert Dokumente auf verschiedene Kriterien und schlaegt
    passende Tags vor oder wendet sie automatisch an.
    """

    # Konfigurations-Schwellwerte
    HIGH_AMOUNT_THRESHOLD = Decimal("5000.00")  # Ab diesem Betrag: hoher-betrag
    URGENT_DAYS_THRESHOLD = 7  # Tage bis Frist für: dringend
    OCR_CONFIDENCE_THRESHOLD = 0.75  # Unter diesem Wert: ocr-unsicher
    HIGH_RISK_THRESHOLD = 75  # Entity Risk Score ab dem: risiko-partner
    NEW_ENTITY_DAYS = 90  # Tage seit erstem Dokument für: neuer-lieferant
    AUTO_APPLY_CONFIDENCE = 0.85  # Ab dieser Konfidenz: Auto-Apply

    def __init__(self) -> None:
        """Initialisiert den Service."""
        self._tag_definitions = {t["name"]: t for t in SMART_TAG_DEFINITIONS}

    async def analyze_document(
        self,
        db: AsyncSession,
        document: Document,
        text: Optional[str] = None,
        auto_apply: bool = True,
        min_confidence: float = 0.5,
    ) -> SmartTaggingResult:
        """
        Analysiert ein Dokument und schlaegt Smart Tags vor.

        Args:
            db: Database Session
            document: Das zu analysierende Dokument
            text: OCR-Text (optional, wird aus Dokument gelesen wenn nicht angegeben)
            auto_apply: Ob Tags automatisch angewendet werden sollen
            min_confidence: Minimale Konfidenz für Vorschläge

        Returns:
            SmartTaggingResult mit allen vorgeschlagenen und angewendeten Tags
        """
        import time
        start_time = time.perf_counter()

        result = SmartTaggingResult(document_id=document.id)
        text = text or document.extracted_text or ""

        # Lade Entity wenn vorhanden
        entity: Optional[BusinessEntity] = None
        if document.business_entity_id:
            entity_result = await db.execute(
                select(BusinessEntity).where(
                    BusinessEntity.id == document.business_entity_id
                )
            )
            entity = entity_result.scalar_one_or_none()

        # Lade Invoice-Tracking wenn vorhanden
        invoice_tracking: Optional[InvoiceTracking] = None
        if document.id:
            invoice_result = await db.execute(
                select(InvoiceTracking).where(
                    InvoiceTracking.document_id == document.id
                )
            )
            invoice_tracking = invoice_result.scalar_one_or_none()

        # Sammle alle erkannten Tags
        detected_tags: List[SmartTag] = []

        # 1. Urgency-Analyse
        urgency_tags = await self._analyze_urgency(
            db, document, text, invoice_tracking
        )
        detected_tags.extend(urgency_tags)

        # 2. Financial-Analyse
        financial_tags = await self._analyze_financial(
            db, document, text, invoice_tracking
        )
        detected_tags.extend(financial_tags)

        # 3. Quality-Analyse
        quality_tags = await self._analyze_quality(
            db, document, text
        )
        detected_tags.extend(quality_tags)

        # 4. Action-Analyse
        action_tags = await self._analyze_actions(
            db, document, text, invoice_tracking
        )
        detected_tags.extend(action_tags)

        # 5. Trust-Analyse (Entity-basiert)
        trust_tags = await self._analyze_trust(
            db, document, entity
        )
        detected_tags.extend(trust_tags)

        # Filtere nach Konfidenz
        result.suggested_tags = [
            t for t in detected_tags if t.confidence >= min_confidence
        ]

        # Sortiere nach Priorität
        result.suggested_tags.sort(key=lambda t: t.priority, reverse=True)

        # Auto-Apply wenn aktiviert
        if auto_apply:
            applied, skipped = await self._apply_tags(
                db, document, result.suggested_tags
            )
            result.applied_tags = applied
            result.skipped_tags = skipped

        # Analyse-Metadaten
        duration = time.perf_counter() - start_time
        SMART_TAGGING_DURATION.observe(duration)

        result.analysis_metadata = {
            "duration_ms": round(duration * 1000, 2),
            "text_length": len(text),
            "has_entity": entity is not None,
            "has_invoice_tracking": invoice_tracking is not None,
            "tags_suggested": len(result.suggested_tags),
            "tags_applied": len(result.applied_tags),
        }

        logger.info(
            "smart_tagging_complete",
            document_id=str(document.id),
            tags_suggested=len(result.suggested_tags),
            tags_applied=len(result.applied_tags),
            duration_ms=result.analysis_metadata["duration_ms"],
        )

        return result

    async def _analyze_urgency(
        self,
        db: AsyncSession,
        document: Document,
        text: str,
        invoice_tracking: Optional[InvoiceTracking],
    ) -> List[SmartTag]:
        """Analysiert Dringlichkeit basierend auf Fristen."""
        tags: List[SmartTag] = []
        now = datetime.now(timezone.utc)

        # Prüfe auf explizite Dringlichkeits-Keywords
        urgency_keywords = [
            "dringend", "urgent", "sofort", "umgehend", "eilig",
            "fristablauf", "letzte mahnung", "zahlungsaufforderung",
        ]
        text_lower = text.lower()
        matched_keywords = [kw for kw in urgency_keywords if kw in text_lower]

        if matched_keywords:
            tags.append(SmartTag(
                name="dringend",
                display_name="Dringend",
                category=TagCategory.URGENCY,
                confidence=min(0.7 + len(matched_keywords) * 0.1, 0.95),
                reason=f"Dringlichkeits-Begriffe erkannt: {', '.join(matched_keywords[:3])}",
                icon="AlertTriangle",
                color="red",
                priority=100,
            ))

        # Prüfe Invoice-Tracking Fristen
        if invoice_tracking:
            # Überfällig?
            if invoice_tracking.due_date:
                days_overdue = (now.date() - invoice_tracking.due_date).days

                if days_overdue > 0:
                    tags.append(SmartTag(
                        name="überfällig",
                        display_name="Überfällig",
                        category=TagCategory.URGENCY,
                        confidence=0.95,
                        reason=f"Rechnung ist {days_overdue} Tage überfällig",
                        icon="AlertOctagon",
                        color="red",
                        priority=110,
                    ))
                elif days_overdue >= -self.URGENT_DAYS_THRESHOLD:
                    tags.append(SmartTag(
                        name="frist-diese-woche",
                        display_name="Frist diese Woche",
                        category=TagCategory.URGENCY,
                        confidence=0.90,
                        reason=f"Zahlungsfrist in {abs(days_overdue)} Tagen",
                        icon="Clock",
                        color="orange",
                        priority=90,
                    ))

            # Skonto-Frist prufen
            if invoice_tracking.skonto_deadline and not invoice_tracking.skonto_used:
                skonto_days = (invoice_tracking.skonto_deadline.date() - now.date()).days
                if 0 < skonto_days <= 3:
                    tags.append(SmartTag(
                        name="dringend",
                        display_name="Dringend",
                        category=TagCategory.URGENCY,
                        confidence=0.85,
                        reason=f"Skonto-Frist endet in {skonto_days} Tagen",
                        icon="AlertTriangle",
                        color="red",
                        priority=100,
                    ))

        # Erkenne Frist-Patterns im Text
        deadline_patterns = [
            r"(?:bis|spätestens|frist)\s*(?:zum|:\s*)?\s*(\d{1,2})[.\s/](\d{1,2})[.\s/](\d{2,4})",
            r"zahlungsziel[:\s]*(\d+)\s*tage",
        ]

        for pattern in deadline_patterns:
            matches = re.findall(pattern, text_lower)
            if matches:
                tags.append(SmartTag(
                    name="frist-diese-woche",
                    display_name="Frist diese Woche",
                    category=TagCategory.URGENCY,
                    confidence=0.65,
                    reason="Frist-Angabe im Dokument erkannt",
                    icon="Clock",
                    color="orange",
                    priority=90,
                ))
                break

        return tags

    async def _analyze_financial(
        self,
        db: AsyncSession,
        document: Document,
        text: str,
        invoice_tracking: Optional[InvoiceTracking],
    ) -> List[SmartTag]:
        """Analysiert finanzielle Aspekte."""
        tags: List[SmartTag] = []
        text_lower = text.lower()

        # Skonto-Erkennung
        skonto_patterns = [
            r"(\d+)\s*%?\s*skonto",
            r"skonto\s*:?\s*(\d+)\s*%",
            r"bei\s+zahlung\s+binnen\s+\d+\s+tagen?\s+(\d+)\s*%",
            r"(\d+)\s*%\s+(?:bei|innerhalb)",
        ]

        for pattern in skonto_patterns:
            if re.search(pattern, text_lower):
                # Prüfe ob Skonto noch nicht genutzt
                if not invoice_tracking or not invoice_tracking.skonto_used:
                    tags.append(SmartTag(
                        name="skonto-möglich",
                        display_name="Skonto möglich",
                        category=TagCategory.FINANCIAL,
                        confidence=0.88,
                        reason="Skonto-Bedingungen im Dokument erkannt",
                        icon="Percent",
                        color="green",
                        priority=80,
                    ))
                break

        # Hoher Betrag aus Invoice-Tracking
        if invoice_tracking and invoice_tracking.amount:
            if invoice_tracking.amount >= self.HIGH_AMOUNT_THRESHOLD:
                tags.append(SmartTag(
                    name="hoher-betrag",
                    display_name="Hoher Betrag",
                    category=TagCategory.FINANCIAL,
                    confidence=0.95,
                    reason=f"Rechnungsbetrag {invoice_tracking.amount:,.2f} EUR übersteigt Schwellwert",
                    icon="DollarSign",
                    color="amber",
                    priority=70,
                ))
        else:
            # Versuche Betrag aus Text zu extrahieren
            amount_patterns = [
                r"(?:gesamt|summe|total|brutto|netto)[:\s]*[\d\.,]+\s*(?:€|eur)",
                r"(?:€|eur)\s*[\d\.,]+",
            ]
            for pattern in amount_patterns:
                match = re.search(pattern, text_lower)
                if match:
                    # Extrahiere Zahl
                    amount_str = re.sub(r"[^\d,.]", "", match.group())
                    try:
                        # Deutsches Format: 1.234,56
                        amount_str = amount_str.replace(".", "").replace(",", ".")
                        amount = Decimal(amount_str)
                        if amount >= self.HIGH_AMOUNT_THRESHOLD:
                            tags.append(SmartTag(
                                name="hoher-betrag",
                                display_name="Hoher Betrag",
                                category=TagCategory.FINANCIAL,
                                confidence=0.75,
                                reason=f"Erkannter Betrag übersteigt {self.HIGH_AMOUNT_THRESHOLD:,.0f} EUR",
                                icon="DollarSign",
                                color="amber",
                                priority=70,
                            ))
                            break
                    except (ValueError, TypeError) as e:
                        logger.debug(
                            "smart_tagging_amount_parse_skipped",
                            error_type=type(e).__name__,
                        )

        # Langes Zahlungsziel
        if invoice_tracking:
            if invoice_tracking.due_date and invoice_tracking.invoice_date:
                payment_days = (invoice_tracking.due_date - invoice_tracking.invoice_date).days
                if payment_days >= 45:
                    tags.append(SmartTag(
                        name="zahlungsziel-lang",
                        display_name="Langes Zahlungsziel",
                        category=TagCategory.FINANCIAL,
                        confidence=0.90,
                        reason=f"Zahlungsziel: {payment_days} Tage",
                        icon="Calendar",
                        color="blue",
                        priority=40,
                    ))

        return tags

    async def _analyze_quality(
        self,
        db: AsyncSession,
        document: Document,
        text: str,
    ) -> List[SmartTag]:
        """Analysiert Qualitäts-Aspekte des Dokuments."""
        tags: List[SmartTag] = []

        # OCR-Konfidenz prüfen
        ocr_confidence = document.ocr_confidence
        if ocr_confidence is not None and ocr_confidence < self.OCR_CONFIDENCE_THRESHOLD:
            tags.append(SmartTag(
                name="ocr-unsicher",
                display_name="OCR unsicher",
                category=TagCategory.QUALITY,
                confidence=0.90,
                reason=f"OCR-Konfidenz nur {ocr_confidence:.0%} (Schwellwert: {self.OCR_CONFIDENCE_THRESHOLD:.0%})",
                icon="AlertCircle",
                color="yellow",
                priority=85,
            ))

        # Duplikat-Prüfung basierend auf Checksum
        if document.checksum:
            dup_result = await db.execute(
                select(func.count(Document.id))
                .where(
                    Document.checksum == document.checksum,
                    Document.id != document.id,
                    Document.deleted_at.is_(None),
                )
            )
            dup_count = dup_result.scalar() or 0

            if dup_count > 0:
                tags.append(SmartTag(
                    name="duplikat-möglich",
                    display_name="Duplikat möglich",
                    category=TagCategory.QUALITY,
                    confidence=0.95,
                    reason=f"{dup_count} Dokument(e) mit identischem Inhalt gefunden",
                    icon="Copy",
                    color="yellow",
                    priority=75,
                ))

        # Unvollständigkeit prüfen
        if text:
            text_lower = text.lower()

            # Prüfe auf typische Pflichtfelder bei Rechnungen
            missing_fields: List[str] = []

            if "rechnung" in text_lower or "invoice" in text_lower:
                if not re.search(r"(?:ust[\-\.]?id|vat|steuer[\-\.]?nr)", text_lower):
                    missing_fields.append("USt-IdNr")
                if not re.search(r"iban|bankverbindung|konto", text_lower):
                    missing_fields.append("Bankverbindung")
                if not re.search(r"rechnung(?:s)?[\-\.]?(?:nr|nummer)", text_lower):
                    missing_fields.append("Rechnungsnummer")

            if missing_fields:
                tags.append(SmartTag(
                    name="unvollständig",
                    display_name="Unvollständig",
                    category=TagCategory.QUALITY,
                    confidence=0.70,
                    reason=f"Möglicherweise fehlend: {', '.join(missing_fields)}",
                    icon="FileQuestion",
                    color="yellow",
                    priority=65,
                ))

        return tags

    async def _analyze_actions(
        self,
        db: AsyncSession,
        document: Document,
        text: str,
        invoice_tracking: Optional[InvoiceTracking],
    ) -> List[SmartTag]:
        """Analysiert erforderliche Aktionen."""
        tags: List[SmartTag] = []
        text_lower = text.lower()
        now = datetime.now(timezone.utc)

        # Genehmigung erforderlich (hohe Betraege)
        if invoice_tracking and invoice_tracking.amount:
            if invoice_tracking.amount >= Decimal("2500.00"):
                tags.append(SmartTag(
                    name="genehmigung-erforderlich",
                    display_name="Genehmigung erforderlich",
                    category=TagCategory.ACTION,
                    confidence=0.85,
                    reason=f"Betrag {invoice_tracking.amount:,.2f} EUR erfordert Freigabe",
                    icon="CheckSquare",
                    color="purple",
                    priority=95,
                ))

        # Mahnung fällig
        if invoice_tracking:
            if invoice_tracking.status == "overdue" and invoice_tracking.dunning_level < 3:
                days_overdue = 0
                if invoice_tracking.due_date:
                    days_overdue = (now.date() - invoice_tracking.due_date).days

                if days_overdue > 14:
                    tags.append(SmartTag(
                        name="mahnung-fällig",
                        display_name="Mahnung fällig",
                        category=TagCategory.ACTION,
                        confidence=0.90,
                        reason=f"Rechnung {days_overdue} Tage überfällig, Mahnstufe {invoice_tracking.dunning_level}",
                        icon="Mail",
                        color="red",
                        priority=88,
                    ))

        # Rückfrage noetig (erkannt an Qualitäts-Problemen)
        question_indicators = [
            "unleserlich", "unvollständig", "fehlt", "unklar",
            "bitte prüfen", "zur kenntnisnahme", "klärung",
        ]
        matched_questions = [q for q in question_indicators if q in text_lower]

        if matched_questions:
            tags.append(SmartTag(
                name="rückfrage-noetig",
                display_name="Rückfrage nötig",
                category=TagCategory.ACTION,
                confidence=0.70,
                reason=f"Klärungs-Hinweise erkannt: {', '.join(matched_questions[:2])}",
                icon="HelpCircle",
                color="blue",
                priority=60,
            ))

        return tags

    async def _analyze_trust(
        self,
        db: AsyncSession,
        document: Document,
        entity: Optional[BusinessEntity],
    ) -> List[SmartTag]:
        """Analysiert Vertrauens-Aspekte basierend auf Entity."""
        tags: List[SmartTag] = []
        now = datetime.now(timezone.utc)

        if not entity:
            return tags

        # Risiko-Partner
        if entity.risk_score and entity.risk_score >= self.HIGH_RISK_THRESHOLD:
            tags.append(SmartTag(
                name="risiko-partner",
                display_name="Risiko-Partner",
                category=TagCategory.TRUST,
                confidence=0.92,
                reason=f"Entity Risk Score: {entity.risk_score}/100",
                icon="ShieldAlert",
                color="red",
                priority=92,
            ))

        # Neuer Lieferant (erstes Dokument innerhalb 90 Tagen)
        if entity.first_document_date:
            days_since_first = (now.date() - entity.first_document_date).days
            if days_since_first <= self.NEW_ENTITY_DAYS:
                tags.append(SmartTag(
                    name="neuer-lieferant",
                    display_name="Neuer Lieferant",
                    category=TagCategory.TRUST,
                    confidence=0.88,
                    reason=f"Geschäftsbeziehung besteht seit {days_since_first} Tagen",
                    icon="UserPlus",
                    color="cyan",
                    priority=50,
                ))

        # Bekannter Partner (verifiziert und viele Dokumente)
        if entity.verified and entity.document_count and entity.document_count >= 10:
            tags.append(SmartTag(
                name="bekannter-partner",
                display_name="Bekannter Partner",
                category=TagCategory.TRUST,
                confidence=0.85,
                reason=f"Verifiziert, {entity.document_count} Dokumente, "
                       f"Beziehung seit {entity.first_document_date}",
                icon="UserCheck",
                color="green",
                priority=30,
            ))

        return tags

    async def _apply_tags(
        self,
        db: AsyncSession,
        document: Document,
        suggested_tags: List[SmartTag],
    ) -> Tuple[List[str], List[str]]:
        """
        Wendet Tags auf Dokument an.

        Args:
            db: Database Session
            document: Ziel-Dokument
            suggested_tags: Vorgeschlagene Tags

        Returns:
            Tuple (applied_tags, skipped_tags)
        """
        applied: List[str] = []
        skipped: List[str] = []

        # Lade existierende Tag-Namen des Dokuments
        existing_tag_names: Set[str] = set()
        if document.tags:
            existing_tag_names = {tag.name for tag in document.tags}

        for smart_tag in suggested_tags:
            # Skip wenn bereits vorhanden
            if smart_tag.name in existing_tag_names:
                skipped.append(smart_tag.name)
                continue

            # Skip wenn Konfidenz zu niedrig für Auto-Apply
            if smart_tag.confidence < self.AUTO_APPLY_CONFIDENCE:
                skipped.append(smart_tag.name)
                continue

            # Finde oder erstelle Tag in DB
            tag_result = await db.execute(
                select(Tag).where(Tag.name == smart_tag.name)
            )
            tag = tag_result.scalar_one_or_none()

            if not tag:
                # Erstelle neuen Tag
                tag_def = self._tag_definitions.get(smart_tag.name, {})
                tag = Tag(
                    name=smart_tag.name,
                    description=smart_tag.display_name,
                    icon=tag_def.get("icon", smart_tag.icon),
                    color=f"bg-{tag_def.get('color', smart_tag.color)}-500",
                    is_system=True,
                    is_active=True,
                )
                db.add(tag)
                await db.flush()  # Um ID zu erhalten

            # Tag zum Dokument hinzufuegen
            if tag not in document.tags:
                document.tags.append(tag)
                applied.append(smart_tag.name)

                SMART_TAGGING_REQUESTS.labels(
                    tag_category=smart_tag.category,
                    applied="true",
                ).inc()

        if applied:
            await db.commit()
            logger.info(
                "smart_tags_applied",
                document_id=str(document.id),
                tags=applied,
            )

        return applied, skipped

    async def get_tag_suggestions(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        min_confidence: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """
        Gibt Tag-Vorschläge für ein Dokument zurück ohne sie anzuwenden.

        Args:
            db: Database Session
            document_id: Dokument-ID
            min_confidence: Minimale Konfidenz

        Returns:
            Liste von Tag-Vorschlägen
        """
        # Lade Dokument
        doc_result = await db.execute(
            select(Document).where(Document.id == document_id)
        )
        document = doc_result.scalar_one_or_none()

        if not document:
            return []

        # Analysiere ohne Auto-Apply
        result = await self.analyze_document(
            db=db,
            document=document,
            auto_apply=False,
            min_confidence=min_confidence,
        )

        return [
            {
                "name": tag.name,
                "display_name": tag.display_name,
                "category": tag.category,
                "confidence": round(tag.confidence, 3),
                "reason": tag.reason,
                "icon": tag.icon,
                "color": tag.color,
                "priority": tag.priority,
            }
            for tag in result.suggested_tags
        ]

    def get_available_smart_tags(self) -> List[Dict[str, Any]]:
        """Gibt alle verfügbaren Smart Tag-Definitionen zurück."""
        return SMART_TAG_DEFINITIONS


# =============================================================================
# Singleton
# =============================================================================

_smart_tagging_service: Optional[SmartTaggingService] = None
_service_lock = threading.Lock()


def get_smart_tagging_service() -> SmartTaggingService:
    """Factory für SmartTaggingService Singleton (Thread-safe)."""
    global _smart_tagging_service
    if _smart_tagging_service is None:
        with _service_lock:
            if _smart_tagging_service is None:
                _smart_tagging_service = SmartTaggingService()
    return _smart_tagging_service
