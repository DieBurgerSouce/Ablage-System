"""Ableitung der Rechnungsrichtung über BusinessEntity.entity_type.

Hintergrund (Manifest w2-api, 2026-06-11): ``InvoiceTracking`` hat KEINE
Spalte ``invoice_type`` — weder im Modell noch in einer Alembic-Migration.
Alle Filter auf ``InvoiceTracking.invoice_type`` liefen zur Laufzeit in
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

from sqlalchemy import select
from sqlalchemy.sql.elements import ColumnElement

from app.db.models_entity_business import BusinessEntity, EntityType, InvoiceTracking


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
