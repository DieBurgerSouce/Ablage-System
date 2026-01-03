# -*- coding: utf-8 -*-
"""
ExtractedData Wrapper.

Wrapper-Klasse fuer Document.extracted_data JSONB-Feld,
um einheitlichen Zugriff auf extrahierte Daten zu ermoeglichen.

Die Daten werden im Document-Model als JSONB gespeichert:
Document.extracted_data = {
    "invoice_number": "RE-12345",
    "invoice_date": "2026-01-15",
    "total_net": 1000.00,
    "total_gross": 1190.00,
    "vat_amount": 190.00,
    "supplier_name": "Firma GmbH",
    "supplier_vat_id": "DE123456789",
    ...
}
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, Optional
from uuid import UUID

# TYPE SAFETY FIX: Proper typing ohne circular imports
if TYPE_CHECKING:
    from app.db.models import Document


@dataclass
class ExtractedData:
    """
    Wrapper fuer extrahierte Dokumentdaten.

    Bietet typisierten Zugriff auf JSONB-Daten.
    """
    document_id: UUID
    raw_data: Dict[str, Any]

    # Rechnungsdaten
    @property
    def invoice_number(self) -> Optional[str]:
        return self.raw_data.get("invoice_number")

    @property
    def order_number(self) -> Optional[str]:
        """Bestellnummer / Auftragsnummer."""
        return self.raw_data.get("order_number") or self.raw_data.get("purchase_order")

    @property
    def invoice_date(self) -> Optional[date]:
        val = self.raw_data.get("invoice_date")
        if val is None:
            return None
        if isinstance(val, date):
            return val
        if isinstance(val, datetime):
            return val.date()
        if isinstance(val, str):
            try:
                return datetime.fromisoformat(val).date()
            except ValueError:
                return None
        return None

    @property
    def due_date(self) -> Optional[date]:
        val = self.raw_data.get("due_date")
        if val is None:
            return None
        if isinstance(val, date):
            return val
        if isinstance(val, datetime):
            return val.date()
        if isinstance(val, str):
            try:
                return datetime.fromisoformat(val).date()
            except ValueError:
                return None
        return None

    @property
    def payment_term_days(self) -> Optional[int]:
        val = self.raw_data.get("payment_term_days")
        if val is None:
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    # Betraege
    @property
    def total_net(self) -> Optional[Decimal]:
        val = self.raw_data.get("total_net") or self.raw_data.get("net_amount")
        if val is None:
            return None
        try:
            return Decimal(str(val))
        except Exception:
            return None

    @property
    def total_gross(self) -> Optional[Decimal]:
        val = self.raw_data.get("total_gross") or self.raw_data.get("gross_amount") or self.raw_data.get("total_amount")
        if val is None:
            return None
        try:
            return Decimal(str(val))
        except Exception:
            return None

    @property
    def vat_amount(self) -> Optional[Decimal]:
        val = self.raw_data.get("vat_amount") or self.raw_data.get("tax_amount")
        if val is None:
            return None
        try:
            return Decimal(str(val))
        except Exception:
            return None

    # Geschaeftspartner
    @property
    def supplier_name(self) -> Optional[str]:
        return self.raw_data.get("supplier_name") or self.raw_data.get("vendor_name")

    @property
    def supplier_vat_id(self) -> Optional[str]:
        return self.raw_data.get("supplier_vat_id") or self.raw_data.get("vendor_vat_id")

    @property
    def supplier_id(self) -> Optional[UUID]:
        val = self.raw_data.get("supplier_id") or self.raw_data.get("vendor_id")
        if val is None:
            return None
        if isinstance(val, UUID):
            return val
        try:
            return UUID(str(val))
        except ValueError:
            return None

    @property
    def customer_name(self) -> Optional[str]:
        return self.raw_data.get("customer_name") or self.raw_data.get("recipient_name")

    @property
    def customer_vat_id(self) -> Optional[str]:
        return self.raw_data.get("customer_vat_id") or self.raw_data.get("recipient_vat_id")

    @property
    def customer_id(self) -> Optional[UUID]:
        val = self.raw_data.get("customer_id") or self.raw_data.get("recipient_id")
        if val is None:
            return None
        if isinstance(val, UUID):
            return val
        try:
            return UUID(str(val))
        except ValueError:
            return None

    # Timestamps
    @property
    def created_at(self) -> Optional[datetime]:
        val = self.raw_data.get("created_at")
        if val is None:
            return None
        if isinstance(val, datetime):
            return val
        if isinstance(val, str):
            try:
                return datetime.fromisoformat(val)
            except ValueError:
                return None
        return None

    @classmethod
    def from_document(cls, document: Optional[Document]) -> Optional["ExtractedData"]:
        """Erstellt ExtractedData aus einem Document-Model."""
        if document is None:
            return None

        # Lade extracted_data JSONB
        raw_data = document.extracted_data or {}

        if not raw_data and not isinstance(raw_data, dict):
            return None

        return cls(
            document_id=document.id,
            raw_data=raw_data,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "document_id": str(self.document_id),
            "invoice_number": self.invoice_number,
            "invoice_date": self.invoice_date.isoformat() if self.invoice_date else None,
            "total_net": float(self.total_net) if self.total_net else None,
            "total_gross": float(self.total_gross) if self.total_gross else None,
            "vat_amount": float(self.vat_amount) if self.vat_amount else None,
            "supplier_name": self.supplier_name,
            "supplier_vat_id": self.supplier_vat_id,
            "customer_name": self.customer_name,
            "customer_vat_id": self.customer_vat_id,
        }


def get_extracted_data(document: Optional[Document]) -> Optional[ExtractedData]:
    """Helper-Funktion zum Erstellen von ExtractedData aus einem Document."""
    return ExtractedData.from_document(document)
