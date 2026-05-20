# -*- coding: utf-8 -*-
"""
TaxAssistantService - Steuer-Assistent fuer das Privat-Modul.

Erweitert den TaxOptimizationService um:
1. Auto-Kategorisierung einzelner Dokumente nach Steuer-Kategorien
2. Jahres-Zusammenfassung mit Summen pro Kategorie
3. Steuerberater-Paket ZIP-Generierung (Privat-Bereich)
4. ELSTER-Datenaufbereitung

Nutzt die bestehende TaxOptimizationService-Infrastruktur fuer
Keyword-Matching, Betragsextraktion und Abzugsberechnung.

SECURITY: NIEMALS persoenliche Finanzdaten loggen!
Enterprise Feature - KEINE externen APIs, alles lokal berechnet.
"""

from __future__ import annotations

import csv
import io
import threading
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone, date
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from prometheus_client import Counter, Histogram
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

TAX_ASSISTANT_OPS = Counter(
    "tax_assistant_operations_total",
    "Anzahl der Steuer-Assistenten Operationen",
    ["operation"],
)

TAX_ASSISTANT_DURATION = Histogram(
    "tax_assistant_duration_seconds",
    "Dauer der Steuer-Assistenten Operationen",
    buckets=[0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)


# =============================================================================
# Deutsche Steuer-Kategorien (erweitert fuer Steuer-Assistent)
# =============================================================================

TAX_CATEGORIES: Dict[str, Dict[str, object]] = {
    "werbungskosten": {
        "label": "Werbungskosten",
        "description": "Arbeitsmittel, Fortbildung, Fahrtkosten, Arbeitszimmer",
        "elster_anlage": "N",
        "keywords": [
            "buero", "arbeitsmittel", "fortbildung", "fachliteratur",
            "fahrkarte", "pendlerpauschale", "arbeitsweg", "berufskleidung",
            "bewerbung", "umzug", "arbeitszimmer", "reisekosten",
        ],
    },
    "sonderausgaben": {
        "label": "Sonderausgaben",
        "description": "Versicherungen, Spenden, Kirchensteuer",
        "elster_anlage": "Vorsorgeaufwand",
        "keywords": [
            "versicherung", "spende", "kirchensteuer", "riester",
            "ruerup", "altersvorsorge", "basisrente",
        ],
    },
    "handwerkerleistungen": {
        "label": "Handwerkerleistungen",
        "description": "Handwerker, Renovierung (20% absetzbar, max 1.200 EUR)",
        "elster_anlage": "Hauptvordruck",
        "keywords": [
            "handwerker", "renovierung", "reparatur", "sanitaer",
            "elektriker", "maler", "installation", "heizung",
            "dach", "fassade", "schornsteinfeger",
        ],
        "deductible_pct": Decimal("0.20"),
        "max_deduction": Decimal("1200"),
    },
    "haushaltsnahe": {
        "label": "Haushaltsnahe Dienstleistungen",
        "description": "Reinigung, Gartenpflege, Betreuung (20% absetzbar, max 4.000 EUR)",
        "elster_anlage": "Hauptvordruck",
        "keywords": [
            "reinigung", "garten", "betreuung", "haushaltshilfe",
            "pflege", "hausmeister", "winterdienst", "putzhilfe",
        ],
        "deductible_pct": Decimal("0.20"),
        "max_deduction": Decimal("4000"),
    },
    "aussergewoehnliche_belastungen": {
        "label": "Aussergewoehnliche Belastungen",
        "description": "Arzt, Zahnarzt, Brille, Medikamente, Kur",
        "elster_anlage": "Aussergewoehnliche Belastungen",
        "keywords": [
            "arzt", "zahnarzt", "apotheke", "brille", "medikament",
            "krankenhaus", "therapie", "kur", "rehabilitation",
            "zahnersatz", "bestattung",
        ],
    },
    "vorsorgeaufwendungen": {
        "label": "Vorsorgeaufwendungen",
        "description": "Krankenversicherung, Rentenversicherung, Haftpflicht",
        "elster_anlage": "Vorsorgeaufwand",
        "keywords": [
            "krankenversicherung", "rentenversicherung", "haftpflicht",
            "unfallversicherung", "pflegeversicherung",
        ],
    },
    "kapitalertraege": {
        "label": "Kapitalertraege",
        "description": "Zinsen, Dividenden, Aktiengewinne",
        "elster_anlage": "KAP",
        "keywords": [
            "dividende", "zins", "aktie", "depot", "kapitalertrag",
            "freistellungsauftrag", "wertpapier",
        ],
    },
    "vermietung": {
        "label": "Vermietung und Verpachtung",
        "description": "Mieteinnahmen, Instandhaltung, AfA",
        "elster_anlage": "V",
        "keywords": [
            "miete", "vermieter", "instandhaltung", "hausverwaltung",
            "nebenkosten", "mietvertrag", "pacht",
        ],
    },
}


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class TaxCategorization:
    """Ergebnis einer automatischen Steuer-Kategorisierung."""
    category: str
    label: str
    confidence: float
    matched_keywords: List[str]
    amount: Optional[Decimal]
    elster_anlage: str


@dataclass
class CategorySummary:
    """Zusammenfassung einer Steuer-Kategorie fuer ein Jahr."""
    category: str
    label: str
    document_count: int
    total_amount: Decimal
    deductible_amount: Decimal
    elster_anlage: str


@dataclass
class TaxSummary:
    """Jahres-Steuerzusammenfassung fuer den Steuer-Assistenten."""
    year: int
    categories: List[CategorySummary]
    total_amount: Decimal
    total_deductible: Decimal
    uncategorized_count: int


@dataclass
class ElsterFieldData:
    """Strukturierte Daten fuer ELSTER-Anlagen."""
    anlage: str
    field_name: str
    value: str
    description: str


@dataclass
class ElsterExportResult:
    """ELSTER-Export Ergebnis."""
    year: int
    anlagen: Dict[str, List[ElsterFieldData]]
    total_deductible: Decimal
    is_complete: bool
    missing_fields: List[str]


# =============================================================================
# Singleton Service
# =============================================================================

class TaxAssistantService:
    """
    Steuer-Assistent fuer das Privat-Modul.

    Bietet Auto-Kategorisierung, Jahres-Zusammenfassung,
    Steuerberater-Paket ZIP und ELSTER-Daten.

    SECURITY: Finanzielle Daten werden NIE geloggt!
    """

    _instance: Optional["TaxAssistantService"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "TaxAssistantService":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        logger.info("tax_assistant_service_initialized")

    # =========================================================================
    # Auto-Kategorisierung
    # =========================================================================

    async def auto_categorize(
        self,
        document_id: UUID,
        db: AsyncSession,
        space_id: UUID,
    ) -> TaxCategorization:
        """
        Kategorisiert ein Dokument automatisch nach Steuer-Kategorien.

        Analysiert Titel, Beschreibung und verknuepften OCR-Text
        und ordnet die passende Steuer-Kategorie zu.

        Args:
            document_id: ID des PrivatDocument
            db: Datenbank-Session
            space_id: Space-ID fuer Zugriffspruefung

        Returns:
            TaxCategorization mit Kategorie, Confidence und Betrag

        Raises:
            ValueError: Wenn Dokument nicht gefunden
        """
        TAX_ASSISTANT_OPS.labels(operation="auto_categorize").inc()

        from app.db.models_privat_space import PrivatDocument

        result = await db.execute(
            select(PrivatDocument).where(
                PrivatDocument.id == document_id,
                PrivatDocument.space_id == space_id,
                PrivatDocument.deleted_at.is_(None),
            )
        )
        doc = result.scalar_one_or_none()

        if not doc:
            raise ValueError("Dokument nicht gefunden")

        # Text-Inhalt zusammenstellen
        text_parts: List[str] = []
        if doc.title:
            text_parts.append(doc.title.lower())
        if doc.description:
            text_parts.append(doc.description.lower())
        if doc.file_name:
            text_parts.append(doc.file_name.lower())

        # Verknuepftes System-Dokument fuer OCR-Text laden
        if doc.document_id:
            from app.db.models import Document
            sys_doc_result = await db.execute(
                select(Document.extracted_text).where(Document.id == doc.document_id)
            )
            extracted_text = sys_doc_result.scalar_one_or_none()
            if extracted_text:
                text_parts.append(extracted_text.lower()[:2000])

        text_content = " ".join(text_parts)

        if not text_content.strip():
            return TaxCategorization(
                category="unkategorisiert",
                label="Nicht kategorisiert",
                confidence=0.0,
                matched_keywords=[],
                amount=None,
                elster_anlage="",
            )

        # Keyword-Matching gegen alle Kategorien
        best_category = ""
        best_score = 0
        best_keywords: List[str] = []

        for cat_key, cat_info in TAX_CATEGORIES.items():
            keywords = cat_info["keywords"]
            matched = [kw for kw in keywords if kw in text_content]
            score = len(matched)
            if score > best_score:
                best_score = score
                best_category = cat_key
                best_keywords = matched

        if not best_category or best_score == 0:
            return TaxCategorization(
                category="unkategorisiert",
                label="Nicht kategorisiert",
                confidence=0.0,
                matched_keywords=[],
                amount=self._extract_amount(doc),
                elster_anlage="",
            )

        confidence = min(1.0, best_score * 0.25)
        cat_info = TAX_CATEGORIES[best_category]

        return TaxCategorization(
            category=best_category,
            label=str(cat_info["label"]),
            confidence=confidence,
            matched_keywords=best_keywords,
            amount=self._extract_amount(doc),
            elster_anlage=str(cat_info["elster_anlage"]),
        )

    # =========================================================================
    # Jahres-Zusammenfassung
    # =========================================================================

    async def get_tax_summary(
        self,
        space_id: UUID,
        year: int,
        db: AsyncSession,
    ) -> TaxSummary:
        """
        Aggregiert alle kategorisierten Dokumente fuer ein Steuerjahr.

        Berechnet Summen pro Kategorie mit abzugsfaehigen Betraegen
        unter Beruecksichtigung der gesetzlichen Hoechstgrenzen.

        Args:
            space_id: ID des Privat-Space
            year: Steuerjahr
            db: Datenbank-Session

        Returns:
            TaxSummary mit Kategorien, Summen und unkategorisierten Dokumenten
        """
        TAX_ASSISTANT_OPS.labels(operation="get_tax_summary").inc()

        from app.db.models_privat_space import PrivatDocument

        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)

        # Alle Dokumente des Jahres laden
        result = await db.execute(
            select(PrivatDocument).where(
                PrivatDocument.space_id == space_id,
                PrivatDocument.deleted_at.is_(None),
                or_(
                    and_(
                        PrivatDocument.expiry_date >= year_start,
                        PrivatDocument.expiry_date <= year_end,
                    ),
                    and_(
                        PrivatDocument.created_at >= datetime(year, 1, 1, tzinfo=timezone.utc),
                        PrivatDocument.created_at < datetime(year + 1, 1, 1, tzinfo=timezone.utc),
                    ),
                ),
            )
        )
        documents = result.scalars().all()

        # Kategorisierung und Aggregation
        category_docs: Dict[str, List[Tuple[object, Decimal]]] = {}
        uncategorized_count = 0

        for doc in documents:
            cat, confidence = self._classify_document(doc)
            amount = self._extract_amount(doc) or Decimal("0")

            if cat and confidence >= 0.5:
                if cat not in category_docs:
                    category_docs[cat] = []
                category_docs[cat].append((doc, amount))
            else:
                uncategorized_count += 1

        # Zusammenfassungen erstellen
        categories: List[CategorySummary] = []
        total_amount = Decimal("0")
        total_deductible = Decimal("0")

        for cat_key, docs_amounts in category_docs.items():
            cat_info = TAX_CATEGORIES.get(cat_key, {})
            cat_total = sum(amt for _, amt in docs_amounts)
            cat_deductible = self._calculate_category_deductible(cat_key, cat_total)

            categories.append(CategorySummary(
                category=cat_key,
                label=str(cat_info.get("label", cat_key)),
                document_count=len(docs_amounts),
                total_amount=cat_total,
                deductible_amount=cat_deductible,
                elster_anlage=str(cat_info.get("elster_anlage", "")),
            ))

            total_amount += cat_total
            total_deductible += cat_deductible

        # Nach Betrag absteigend sortieren
        categories.sort(key=lambda c: c.total_amount, reverse=True)

        logger.info(
            "tax_summary_calculated",
            space_id=str(space_id),
            year=year,
            categories_found=len(categories),
            uncategorized=uncategorized_count,
        )

        return TaxSummary(
            year=year,
            categories=categories,
            total_amount=total_amount,
            total_deductible=total_deductible,
            uncategorized_count=uncategorized_count,
        )

    # =========================================================================
    # Steuerberater-Paket ZIP
    # =========================================================================

    async def generate_steuerberater_package(
        self,
        space_id: UUID,
        year: int,
        db: AsyncSession,
    ) -> Tuple[bytes, str]:
        """
        Generiert ein Steuerberater-Paket als ZIP-Datei.

        Inhalt:
        - Pro Kategorie ein Unterordner mit den zugehoerigen Dokumenten
        - Zusammenfassung.csv mit Kategorie, Anzahl, Summe, Abzugsfaehig
        - Deckblatt.txt mit Uebersicht

        Args:
            space_id: ID des Privat-Space
            year: Steuerjahr
            db: Datenbank-Session

        Returns:
            Tuple aus (ZIP-Bytes, Dateiname)
        """
        TAX_ASSISTANT_OPS.labels(operation="generate_package").inc()

        from app.db.models_privat_space import PrivatDocument

        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)

        # Alle Dokumente des Jahres laden
        result = await db.execute(
            select(PrivatDocument).where(
                PrivatDocument.space_id == space_id,
                PrivatDocument.deleted_at.is_(None),
                or_(
                    and_(
                        PrivatDocument.expiry_date >= year_start,
                        PrivatDocument.expiry_date <= year_end,
                    ),
                    and_(
                        PrivatDocument.created_at >= datetime(year, 1, 1, tzinfo=timezone.utc),
                        PrivatDocument.created_at < datetime(year + 1, 1, 1, tzinfo=timezone.utc),
                    ),
                ),
            )
        )
        documents = result.scalars().all()

        # Dokumente kategorisieren
        categorized: Dict[str, List[Tuple[object, Decimal]]] = {}
        uncategorized: List[object] = []

        for doc in documents:
            cat, confidence = self._classify_document(doc)
            amount = self._extract_amount(doc) or Decimal("0")

            if cat and confidence >= 0.5:
                if cat not in categorized:
                    categorized[cat] = []
                categorized[cat].append((doc, amount))
            else:
                uncategorized.append(doc)

        # ZIP erstellen
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            # Zusammenfassung.csv
            csv_buffer = io.StringIO()
            writer = csv.writer(csv_buffer, delimiter=";")
            writer.writerow([
                "Kategorie", "Anzahl Dokumente", "Gesamtbetrag (EUR)",
                "Abzugsfaehig (EUR)", "ELSTER-Anlage",
            ])

            total_amount = Decimal("0")
            total_deductible = Decimal("0")

            for cat_key in sorted(categorized.keys()):
                docs_amounts = categorized[cat_key]
                cat_info = TAX_CATEGORIES.get(cat_key, {})
                cat_total = sum(amt for _, amt in docs_amounts)
                cat_deductible = self._calculate_category_deductible(cat_key, cat_total)
                cat_label = str(cat_info.get("label", cat_key))
                elster = str(cat_info.get("elster_anlage", ""))

                writer.writerow([
                    cat_label,
                    len(docs_amounts),
                    str(cat_total.quantize(Decimal("0.01"))),
                    str(cat_deductible.quantize(Decimal("0.01"))),
                    elster,
                ])

                total_amount += cat_total
                total_deductible += cat_deductible

                # Dokument-Eintraege im Kategorie-Ordner
                folder_name = cat_label.replace(" ", "_")
                for idx, (doc, amount) in enumerate(docs_amounts, 1):
                    doc_title = getattr(doc, "title", None) or getattr(doc, "file_name", None) or f"Dokument_{idx}"
                    # Sicherstellen, dass Dateiname sicher ist
                    safe_name = self._sanitize_filename(doc_title)
                    entry_content = self._build_document_entry(doc, cat_label, amount)
                    zf.writestr(f"{folder_name}/{idx:03d}_{safe_name}.txt", entry_content)

            # Unkategorisierte Dokumente
            if uncategorized:
                writer.writerow([
                    "Unkategorisiert",
                    len(uncategorized),
                    "0.00",
                    "0.00",
                    "",
                ])
                for idx, doc in enumerate(uncategorized, 1):
                    doc_title = getattr(doc, "title", None) or getattr(doc, "file_name", None) or f"Dokument_{idx}"
                    safe_name = self._sanitize_filename(doc_title)
                    entry_content = self._build_document_entry(doc, "Unkategorisiert", Decimal("0"))
                    zf.writestr(f"Unkategorisiert/{idx:03d}_{safe_name}.txt", entry_content)

            zf.writestr("Zusammenfassung.csv", csv_buffer.getvalue())

            # Deckblatt
            deckblatt = self._build_deckblatt(year, categorized, total_amount, total_deductible, len(uncategorized))
            zf.writestr("Deckblatt.txt", deckblatt)

        zip_bytes = zip_buffer.getvalue()
        filename = f"Steuerberater_Paket_{year}.zip"

        logger.info(
            "steuerberater_package_generated",
            space_id=str(space_id),
            year=year,
            document_count=len(documents),
            categories=len(categorized),
        )

        return zip_bytes, filename

    # =========================================================================
    # ELSTER-Daten
    # =========================================================================

    async def get_elster_data(
        self,
        space_id: UUID,
        year: int,
        db: AsyncSession,
    ) -> ElsterExportResult:
        """
        Bereitet strukturierte Daten fuer ELSTER-Anlagen auf.

        Ordnet die Summen pro Kategorie den entsprechenden
        ELSTER-Anlage-Feldern zu.

        Args:
            space_id: ID des Privat-Space
            year: Steuerjahr
            db: Datenbank-Session

        Returns:
            ElsterExportResult mit Anlagen-Feldern und Validierung
        """
        TAX_ASSISTANT_OPS.labels(operation="get_elster_data").inc()

        summary = await self.get_tax_summary(space_id, year, db)

        anlagen: Dict[str, List[ElsterFieldData]] = {}
        missing_fields: List[str] = []

        for cat_summary in summary.categories:
            cat_info = TAX_CATEGORIES.get(cat_summary.category, {})
            anlage = str(cat_info.get("elster_anlage", "Sonstige"))

            if anlage not in anlagen:
                anlagen[anlage] = []

            anlagen[anlage].append(ElsterFieldData(
                anlage=anlage,
                field_name=cat_summary.label,
                value=str(cat_summary.total_amount.quantize(Decimal("0.01"))),
                description=str(cat_info.get("description", "")),
            ))

        # Vollstaendigkeitspruefung
        essential_anlagen = {"N", "Vorsorgeaufwand"}
        for anlage_name in essential_anlagen:
            if anlage_name not in anlagen:
                missing_fields.append(f"Anlage {anlage_name}: Keine Daten vorhanden")

        is_complete = len(missing_fields) == 0 and len(summary.categories) > 0

        logger.info(
            "elster_data_prepared",
            space_id=str(space_id),
            year=year,
            anlagen_count=len(anlagen),
            is_complete=is_complete,
        )

        return ElsterExportResult(
            year=year,
            anlagen=anlagen,
            total_deductible=summary.total_deductible,
            is_complete=is_complete,
            missing_fields=missing_fields,
        )

    # =========================================================================
    # Kategorien-Uebersicht
    # =========================================================================

    def get_available_categories(self) -> List[Dict[str, str]]:
        """
        Gibt alle verfuegbaren Steuer-Kategorien zurueck.

        Returns:
            Liste mit Kategorie-Infos (key, label, description, elster_anlage)
        """
        result: List[Dict[str, str]] = []
        for key, info in TAX_CATEGORIES.items():
            result.append({
                "key": key,
                "label": str(info["label"]),
                "description": str(info["description"]),
                "elster_anlage": str(info["elster_anlage"]),
            })
        return result

    # =========================================================================
    # Manuelle Kategorisierung
    # =========================================================================

    async def set_document_category(
        self,
        document_id: UUID,
        category: str,
        space_id: UUID,
        db: AsyncSession,
    ) -> TaxCategorization:
        """
        Setzt die Steuer-Kategorie eines Dokuments manuell.

        Speichert die Kategorie in den Dokument-Metadaten (doc_metadata).

        Args:
            document_id: ID des PrivatDocument
            category: Kategorie-Schluessel (z.B. 'werbungskosten')
            space_id: Space-ID fuer Zugriffspruefung
            db: Datenbank-Session

        Returns:
            TaxCategorization mit gesetzter Kategorie

        Raises:
            ValueError: Bei ungueltigem Dokument oder Kategorie
        """
        TAX_ASSISTANT_OPS.labels(operation="set_category").inc()

        if category not in TAX_CATEGORIES and category != "unkategorisiert":
            valid_keys = ", ".join(TAX_CATEGORIES.keys())
            raise ValueError(
                f"Ungueltige Kategorie: {category}. "
                f"Erlaubt: {valid_keys}, unkategorisiert"
            )

        from app.db.models_privat_space import PrivatDocument

        result = await db.execute(
            select(PrivatDocument).where(
                PrivatDocument.id == document_id,
                PrivatDocument.space_id == space_id,
                PrivatDocument.deleted_at.is_(None),
            )
        )
        doc = result.scalar_one_or_none()

        if not doc:
            raise ValueError("Dokument nicht gefunden")

        # Kategorie in Metadaten speichern
        metadata = dict(doc.doc_metadata) if doc.doc_metadata else {}
        metadata["tax_category"] = category
        metadata["tax_category_manual"] = True
        metadata["tax_category_updated_at"] = utc_now().isoformat()
        doc.doc_metadata = metadata

        amount = self._extract_amount(doc)

        if category == "unkategorisiert":
            return TaxCategorization(
                category="unkategorisiert",
                label="Nicht kategorisiert",
                confidence=1.0,
                matched_keywords=[],
                amount=amount,
                elster_anlage="",
            )

        cat_info = TAX_CATEGORIES[category]
        return TaxCategorization(
            category=category,
            label=str(cat_info["label"]),
            confidence=1.0,
            matched_keywords=["manuell"],
            amount=amount,
            elster_anlage=str(cat_info["elster_anlage"]),
        )

    # =========================================================================
    # Hilfsmethoden
    # =========================================================================

    def _classify_document(
        self,
        doc: object,
    ) -> Tuple[Optional[str], float]:
        """
        Klassifiziert ein Dokument nach Steuer-Kategorie.

        Prueft zuerst manuell gesetzte Kategorie, dann Keyword-Matching.

        Returns:
            Tuple aus (Kategorie-Key, Confidence 0-1)
        """
        # Manuelle Kategorie hat Vorrang
        metadata = getattr(doc, "doc_metadata", None) or {}
        if isinstance(metadata, dict) and metadata.get("tax_category"):
            manual_cat = metadata["tax_category"]
            if manual_cat in TAX_CATEGORIES:
                return manual_cat, 1.0
            if manual_cat == "unkategorisiert":
                return None, 0.0

        # Text zusammenstellen
        text_parts: List[str] = []
        for attr in ("title", "description", "file_name"):
            val = getattr(doc, attr, None)
            if val:
                text_parts.append(val.lower())

        text_content = " ".join(text_parts)
        if not text_content.strip():
            return None, 0.0

        best_cat: Optional[str] = None
        best_score = 0

        for cat_key, cat_info in TAX_CATEGORIES.items():
            keywords = cat_info["keywords"]
            score = sum(1 for kw in keywords if kw in text_content)
            if score > best_score:
                best_score = score
                best_cat = cat_key

        if best_cat and best_score > 0:
            confidence = min(1.0, best_score * 0.25)
            return best_cat, confidence

        return None, 0.0

    def _extract_amount(self, doc: object) -> Optional[Decimal]:
        """Extrahiert den Betrag aus Dokument-Metadaten."""
        metadata = getattr(doc, "doc_metadata", None) or {}
        if isinstance(metadata, dict):
            for key in ("amount", "total", "betrag", "summe", "brutto", "netto"):
                if key in metadata:
                    try:
                        return Decimal(str(metadata[key]))
                    except (ValueError, ArithmeticError):
                        continue

        return None

    def _calculate_category_deductible(
        self,
        category: str,
        total_amount: Decimal,
    ) -> Decimal:
        """Berechnet den abzugsfaehigen Betrag fuer eine Kategorie."""
        cat_info = TAX_CATEGORIES.get(category, {})

        deductible_pct = cat_info.get("deductible_pct")
        max_deduction = cat_info.get("max_deduction")

        if deductible_pct is not None and max_deduction is not None:
            return min(
                total_amount * deductible_pct,
                max_deduction,
            )

        # Voller Betrag ist abzugsfaehig (Werbungskosten, Sonderausgaben, etc.)
        return total_amount

    def _sanitize_filename(self, name: str) -> str:
        """Bereinigt einen Dateinamen fuer Verwendung im ZIP."""
        # Nur alphanumerische Zeichen, Bindestriche, Unterstriche und Punkte
        safe_chars: List[str] = []
        for ch in name:
            if ch.isalnum() or ch in "-_.":
                safe_chars.append(ch)
            elif ch in " /\\":
                safe_chars.append("_")
        result = "".join(safe_chars)
        if not result:
            result = "dokument"
        return result[:100]

    def _build_document_entry(
        self,
        doc: object,
        category_label: str,
        amount: Decimal,
    ) -> str:
        """Erstellt einen Text-Eintrag fuer ein Dokument im ZIP."""
        title = getattr(doc, "title", None) or "Ohne Titel"
        description = getattr(doc, "description", None) or ""
        file_name = getattr(doc, "file_name", None) or ""
        doc_type = getattr(doc, "document_type", None) or ""
        created = getattr(doc, "created_at", None)
        created_str = created.strftime("%d.%m.%Y") if created else ""

        lines = [
            f"Titel: {title}",
            f"Kategorie: {category_label}",
            f"Betrag: {amount.quantize(Decimal('0.01'))} EUR" if amount else "Betrag: -",
            f"Dokumenttyp: {doc_type}" if doc_type else "",
            f"Dateiname: {file_name}" if file_name else "",
            f"Erstellt: {created_str}" if created_str else "",
            f"Beschreibung: {description}" if description else "",
        ]

        return "\n".join(line for line in lines if line)

    def _build_deckblatt(
        self,
        year: int,
        categorized: Dict[str, List[Tuple[object, Decimal]]],
        total_amount: Decimal,
        total_deductible: Decimal,
        uncategorized_count: int,
    ) -> str:
        """Erstellt das Deckblatt fuer das Steuerberater-Paket."""
        now = utc_now()
        lines = [
            "=" * 60,
            f"  STEUERBERATER-PAKET {year}",
            "=" * 60,
            "",
            f"Erstellt am: {now.strftime('%d.%m.%Y %H:%M Uhr')}",
            "",
            "-" * 60,
            "  UEBERSICHT",
            "-" * 60,
            "",
        ]

        total_docs = sum(len(docs) for docs in categorized.values()) + uncategorized_count
        lines.append(f"Gesamtanzahl Dokumente: {total_docs}")
        lines.append(f"Kategorisierte Dokumente: {total_docs - uncategorized_count}")
        lines.append(f"Unkategorisierte Dokumente: {uncategorized_count}")
        lines.append("")
        lines.append(f"Gesamtbetrag: {total_amount.quantize(Decimal('0.01'))} EUR")
        lines.append(f"Davon abzugsfaehig: {total_deductible.quantize(Decimal('0.01'))} EUR")
        lines.append("")
        lines.append("-" * 60)
        lines.append("  KATEGORIEN")
        lines.append("-" * 60)
        lines.append("")

        for cat_key in sorted(categorized.keys()):
            docs_amounts = categorized[cat_key]
            cat_info = TAX_CATEGORIES.get(cat_key, {})
            cat_label = str(cat_info.get("label", cat_key))
            cat_total = sum(amt for _, amt in docs_amounts)
            cat_deductible = self._calculate_category_deductible(cat_key, cat_total)
            elster = str(cat_info.get("elster_anlage", ""))

            lines.append(f"  {cat_label}")
            lines.append(f"    Anzahl: {len(docs_amounts)}")
            lines.append(f"    Summe: {cat_total.quantize(Decimal('0.01'))} EUR")
            lines.append(f"    Abzugsfaehig: {cat_deductible.quantize(Decimal('0.01'))} EUR")
            if elster:
                lines.append(f"    ELSTER-Anlage: {elster}")
            lines.append("")

        lines.append("-" * 60)
        lines.append("  HINWEIS")
        lines.append("-" * 60)
        lines.append("")
        lines.append("Dieses Paket wurde automatisch erstellt.")
        lines.append("Bitte pruefen Sie alle Betraege und Zuordnungen.")
        lines.append("Die Kategorisierung basiert auf Keyword-Analyse")
        lines.append("und kann von der tatsaechlichen steuerlichen")
        lines.append("Einordnung abweichen.")
        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)


# =============================================================================
# Singleton Accessor
# =============================================================================

def get_tax_assistant_service() -> TaxAssistantService:
    """Gibt die Singleton-Instanz des TaxAssistantService zurueck."""
    return TaxAssistantService()
