# -*- coding: utf-8 -*-
"""
Document Summary Service.

Deutsche Zusammenfassungen für Dokumente:
- Template-basierte Generierung
- Strukturierte Key-Facts für Dashboard
- Batch-Verarbeitung für fehlende Summaries

Format: 'Rechnung #4711 von Mueller GmbH, 3.450 EUR netto,
         Zahlungsziel 30 Tage, 2% Skonto bei 10 Tagen'

Feinpoliert und durchdacht - Klare deutsche Zusammenfassungen.
"""

import structlog
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log
from app.db.models_ki_pipeline import (
    DocumentSummary,
    ExtractionConfidence,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# TEMPLATES
# =============================================================================

SUMMARY_TEMPLATES: Dict[str, str] = {
    "invoice": (
        "Rechnung #{number} von {supplier}, {amount} EUR {tax_type}"
        ", Zahlungsziel {payment_days} Tage{skonto}"
    ),
    "delivery_note": (
        "Lieferschein #{number} von {supplier}"
        ", {item_count} Positionen, Lieferdatum {date}"
    ),
    "contract": (
        "Vertrag mit {party}, Laufzeit {start} bis {end}"
        ", {value} EUR{renewal}"
    ),
    "order": (
        "Bestellung #{number} an {supplier}"
        ", {amount} EUR, Liefertermin {delivery_date}"
    ),
    "credit_note": (
        "Gutschrift #{number} von {supplier}"
        ", {amount} EUR"
    ),
    "default": "{type} #{number} von {entity}, {date}",
}

# Dokumenttyp-Labels (deutsch)
DOCUMENT_TYPE_LABELS: Dict[str, str] = {
    "invoice": "Rechnung",
    "delivery_note": "Lieferschein",
    "order": "Bestellung",
    "contract": "Vertrag",
    "credit_note": "Gutschrift",
    "quote": "Angebot",
    "reminder": "Mahnung",
    "receipt": "Quittung",
}


def _safe_format(template: str, **kwargs: str) -> str:
    """Template sicher formatieren - fehlende Keys werden durch '?' ersetzt.

    Args:
        template: Format-String
        **kwargs: Platzhalter-Werte

    Returns:
        Formatierter String
    """
    # Ersetze fehlende Keys durch '?'
    class SafeDict(dict):
        def __missing__(self, key: str) -> str:
            return "?"

    return template.format_map(SafeDict(**kwargs))


class DocumentSummaryService:
    """Deutsche Zusammenfassungen für Dokumente.

    Format: 'Rechnung #4711 von Mueller GmbH, 3.450 EUR netto,
             Zahlungsziel 30 Tage, 2% Skonto bei 10 Tagen'
    """

    async def generate_summary(
        self,
        db: AsyncSession,
        document_id: UUID,
        company_id: UUID,
        document_type: Optional[str] = None,
        extracted_data: Optional[Dict[str, str]] = None,
    ) -> DocumentSummary:
        """Deutsche Zusammenfassung für ein Dokument generieren.

        Laedt extrahierte Daten und Confidence-Scores, bestimmt den
        Dokumenttyp und fuellt das passende Template.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            company_id: Firma-ID
            document_type: Optionaler Dokumenttyp (sonst auto-detect)
            extracted_data: Optionale vorab-extrahierte Daten

        Returns:
            DocumentSummary-Objekt
        """
        # Extrahierte Daten laden wenn nicht bereitgestellt
        if extracted_data is None:
            extracted_data = await self._load_extracted_data(db, document_id)

        # Dokumenttyp bestimmen
        if document_type is None:
            document_type = extracted_data.get("document_type", "default")

        # Template wählen
        template_key = document_type if document_type in SUMMARY_TEMPLATES else "default"
        template = SUMMARY_TEMPLATES[template_key]

        # Template-Variablen vorbereiten
        template_vars = self._prepare_template_vars(document_type, extracted_data)

        # Zusammenfassung generieren
        summary_text = _safe_format(template, **template_vars)

        # Key-Facts strukturieren
        key_facts = self._extract_key_facts(document_type, extracted_data)

        now = utc_now()

        # Bestehende Summary prüfen (upsert-artig)
        existing = await self.get_summary(db, document_id)
        if existing:
            existing.summary_text = summary_text
            existing.summary_template = template_key
            existing.key_facts = key_facts
            existing.generated_at = now
            existing.model_used = "template"
            await db.flush()

            logger.info(
                "document_summary_updated",
                document_id=str(document_id),
                template=template_key,
            )
            return existing

        # Neuen Record erstellen
        summary = DocumentSummary(
            document_id=document_id,
            company_id=company_id,
            summary_text=summary_text,
            summary_template=template_key,
            key_facts=key_facts,
            generated_at=now,
            model_used="template",
        )
        db.add(summary)
        await db.flush()

        logger.info(
            "document_summary_generated",
            document_id=str(document_id),
            template=template_key,
            summary_length=len(summary_text),
        )

        return summary

    async def get_summary(
        self,
        db: AsyncSession,
        document_id: UUID,
    ) -> Optional[DocumentSummary]:
        """Zusammenfassung abrufen.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID

        Returns:
            DocumentSummary oder None
        """
        result = await db.execute(
            select(DocumentSummary).where(
                DocumentSummary.document_id == document_id
            )
        )
        return result.scalar_one_or_none()

    async def batch_generate_summaries(
        self,
        db: AsyncSession,
        company_id: UUID,
        document_ids: List[UUID],
    ) -> List[DocumentSummary]:
        """Batch-Generierung von Zusammenfassungen.

        Generiert Zusammenfassungen für alle angegebenen Dokumente,
        überspringt bereits vorhandene.

        Args:
            db: Datenbank-Session
            company_id: Firma-ID
            document_ids: Liste der Dokument-IDs

        Returns:
            Liste der generierten DocumentSummary-Objekte
        """
        results: List[DocumentSummary] = []

        for doc_id in document_ids:
            try:
                # Prüfen ob Summary bereits existiert
                existing = await self.get_summary(db, doc_id)
                if existing:
                    results.append(existing)
                    continue

                summary = await self.generate_summary(
                    db=db,
                    document_id=doc_id,
                    company_id=company_id,
                )
                results.append(summary)
            except Exception as e:
                logger.warning(
                    "batch_summary_generation_failed",
                    document_id=str(doc_id),
                    **safe_error_log(e),
                )
                continue

        logger.info(
            "batch_summaries_generated",
            company_id=str(company_id),
            requested=len(document_ids),
            generated=len(results),
        )

        return results

    async def get_key_facts(
        self,
        db: AsyncSession,
        document_id: UUID,
    ) -> Optional[Dict[str, object]]:
        """Strukturierte Fakten für Dashboard/Listen.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID

        Returns:
            Dict mit Key-Facts oder None
        """
        summary = await self.get_summary(db, document_id)
        if summary and summary.key_facts:
            return dict(summary.key_facts)
        return None

    # =========================================================================
    # HILFSMETHODEN
    # =========================================================================

    async def _load_extracted_data(
        self,
        db: AsyncSession,
        document_id: UUID,
    ) -> Dict[str, str]:
        """Extrahierte Daten als flaches Dict laden.

        Verwendet korrigierte Werte wenn verfügbar.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID

        Returns:
            Dict {field_name: value}
        """
        result = await db.execute(
            select(ExtractionConfidence).where(
                ExtractionConfidence.document_id == document_id
            )
        )
        records = result.scalars().all()

        data: Dict[str, str] = {}
        for record in records:
            value = record.corrected_value if record.was_corrected else record.extracted_value
            data[record.field_name] = value

        return data

    def _prepare_template_vars(
        self,
        document_type: str,
        data: Dict[str, str],
    ) -> Dict[str, str]:
        """Template-Variablen aus extrahierten Daten vorbereiten.

        Args:
            document_type: Dokumenttyp
            data: Extrahierte Daten

        Returns:
            Dict mit Template-Variablen
        """
        # Grundvariablen
        vars_dict: Dict[str, str] = {
            "type": DOCUMENT_TYPE_LABELS.get(document_type, document_type),
            "number": data.get("invoice_number", data.get("order_number", "")),
            "supplier": data.get("supplier_name", ""),
            "entity": data.get("supplier_name", data.get("customer_name", "")),
            "amount": data.get("total_amount", data.get("net_amount", "")),
            "date": data.get("date", data.get("invoice_date", "")),
        }

        # Rechnungsspezifische Variablen
        if document_type == "invoice":
            tax_type = "netto"
            if data.get("vat_amount"):
                tax_type = "brutto"
            vars_dict["tax_type"] = tax_type
            vars_dict["payment_days"] = data.get("payment_days", "30")

            # Skonto-Info
            skonto_pct = data.get("skonto_percent")
            skonto_days = data.get("skonto_days")
            if skonto_pct and skonto_days:
                vars_dict["skonto"] = f", {skonto_pct}% Skonto bei {skonto_days} Tagen"
            else:
                vars_dict["skonto"] = ""

        # Lieferschein
        elif document_type == "delivery_note":
            vars_dict["item_count"] = data.get("item_count", "?")

        # Vertrag
        elif document_type == "contract":
            vars_dict["party"] = data.get("party", data.get("supplier_name", ""))
            vars_dict["start"] = data.get("contract_start", "")
            vars_dict["end"] = data.get("contract_end", "")
            vars_dict["value"] = data.get("contract_value", data.get("total_amount", ""))
            if data.get("auto_renewal") == "true":
                vars_dict["renewal"] = ", automatische Verlängerung"
            else:
                vars_dict["renewal"] = ""

        # Bestellung
        elif document_type == "order":
            vars_dict["delivery_date"] = data.get("delivery_date", "")

        return vars_dict

    def _extract_key_facts(
        self,
        document_type: str,
        data: Dict[str, str],
    ) -> Dict[str, object]:
        """Strukturierte Key-Facts aus extrahierten Daten erzeugen.

        Args:
            document_type: Dokumenttyp
            data: Extrahierte Daten

        Returns:
            Dict mit strukturierten Fakten
        """
        facts: Dict[str, object] = {
            "type": document_type,
            "type_label": DOCUMENT_TYPE_LABELS.get(document_type, document_type),
        }

        # Standard-Felder übernehmen wenn vorhanden
        standard_fields = [
            "invoice_number", "order_number", "supplier_name",
            "customer_name", "total_amount", "net_amount",
            "vat_amount", "date", "invoice_date", "due_date",
            "payment_days", "skonto_percent", "skonto_days",
            "iban", "vat_id", "item_count",
        ]

        for field in standard_fields:
            if field in data and data[field]:
                facts[field] = data[field]

        return facts


# =============================================================================
# SINGLETON
# =============================================================================

_service_instance: Optional[DocumentSummaryService] = None


def get_document_summary_service() -> DocumentSummaryService:
    """Gibt die Singleton-Instanz des DocumentSummaryService zurück."""
    global _service_instance
    if _service_instance is None:
        _service_instance = DocumentSummaryService()
    return _service_instance
