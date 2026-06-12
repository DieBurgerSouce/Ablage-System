"""Ableitung der Rechnungsrichtung über BusinessEntity.entity_type.

Hintergrund (Manifest w2-api, 2026-06-11): ``InvoiceTracking`` hat KEINE
Spalte ``invoice_type`` — weder im Modell noch in einer Alembic-Migration.
Alle ``invoice_type``-Filter auf InvoiceTracking liefen zur Laufzeit in
``AttributeError`` (HTTP 500).

Entscheidung (bindend, 2026-06-11): KEINE neue Spalte/Migration. Die
Richtung wird über den verknüpften Geschäftspartner abgeleitet:

- ``entity_type == 'customer'``  -> Ausgangsrechnung (Forderung, "outgoing")
- ``entity_type == 'supplier'``  -> Eingangsrechnung (Verbindlichkeit, "incoming")

Bewusste Einschränkungen (dokumentiert, kein Bug):

- Rechnungen mit ``entity_id IS NULL`` haben keine ableitbare Richtung und
  werden von beiden Filtern AUSGESCHLOSSEN.
- Entities vom Typ ``'both'`` oder ``'internal'`` sind nicht eindeutig
  zuordenbar und werden ebenfalls ausgeschlossen, bis eine fachliche
  Einzelfall-Zuordnung existiert.
- Soft-Delete der Entity wird NICHT gefiltert: die Richtungsinformation
  einer Rechnung bleibt auch bei gelöschtem Geschäftspartner gültig.
"""

from typing import Tuple

from sqlalchemy import select
from sqlalchemy.sql.elements import ColumnElement

from app.db.models_entity_business import (
    BusinessEntity,
    EntityType,
    InvoiceStatus,
    InvoiceTracking,
)

# Status-Semantik (gleiche Drift-Klasse, Sweep 2026-06-12): InvoiceTracking
# hat auch KEINE Spalten ``is_paid``/``paid_date`` — reale Spalten sind
# ``status`` (InvoiceStatus) und ``paid_at``. "Offen" = explizite
# Status-Allowlist (weder bezahlt noch storniert).
OFFENE_STATUS: Tuple[str, ...] = (
    InvoiceStatus.OPEN.value,
    InvoiceStatus.SENT.value,
    InvoiceStatus.OVERDUE.value,
    InvoiceStatus.DUNNING.value,
    InvoiceStatus.PARTIAL.value,
)


def is_open_invoice() -> ColumnElement[bool]:
    """Filter für offene Rechnungen (Ersatz für ``is_paid == False``)."""
    return InvoiceTracking.status.in_(OFFENE_STATUS)


def is_paid_invoice() -> ColumnElement[bool]:
    """Filter für bezahlte Rechnungen (Ersatz für ``is_paid == True``)."""
    return InvoiceTracking.status == InvoiceStatus.PAID.value


def _direction_filter(entity_type: str) -> ColumnElement[bool]:
    """Semi-Join: InvoiceTracking.entity_id zeigt auf Entity mit gegebenem Typ."""
    return InvoiceTracking.entity_id.in_(
        select(BusinessEntity.id).where(BusinessEntity.entity_type == entity_type)
    )


def is_outgoing_invoice() -> ColumnElement[bool]:
    """Filter für Ausgangsrechnungen (Forderungen): Entity ist Kunde."""
    return _direction_filter(EntityType.CUSTOMER.value)


def is_incoming_invoice() -> ColumnElement[bool]:
    """Filter für Eingangsrechnungen (Verbindlichkeiten): Entity ist Lieferant."""
    return _direction_filter(EntityType.SUPPLIER.value)
