"""
Goods Receipt Service - Wareneingang aus Lieferscheinen

Verknüpft Lieferschein-Dokumente mit Bestandsbuchungen.
"""

import uuid
from datetime import datetime
from decimal import Decimal
import re
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Document, DocumentType
from app.db.models_inventory import (
    GoodsReceipt,
    GoodsReceiptLine,
    InventoryMovement,
    MovementType,
    Warehouse,
)
from app.services.inventory.inventory_item_service import InventoryItemService
from app.services.inventory.stock_service import StockService


class GoodsReceiptService:
    """Service für Wareneingang"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.item_service = InventoryItemService(session)
        self.stock_service = StockService(session)

    async def create_from_delivery_note(
        self,
        document_id: uuid.UUID,
        company_id: uuid.UUID,
        warehouse_id: uuid.UUID,
        receipt_date: Optional[datetime] = None,
        notes: Optional[str] = None,
        created_by: Optional[uuid.UUID] = None,
    ) -> GoodsReceipt:
        """
        Erstellt Wareneingang aus einem Lieferschein-Dokument.

        Args:
            document_id: ID des Lieferschein-Dokuments
            company_id: Unternehmen
            warehouse_id: Ziellager
            receipt_date: Eingangsdatum (Standard: jetzt)
            notes: Bemerkungen
            created_by: Erstellt durch User

        Returns:
            Erstellter GoodsReceipt
        """
        # Dokument prüfen
        doc_query = select(Document).where(
            and_(
                Document.id == document_id,
                Document.company_id == company_id,
            )
        )
        result = await self.session.execute(doc_query)
        document = result.scalar_one_or_none()

        if not document:
            raise ValueError("Dokument nicht gefunden")

        if document.document_type != DocumentType.DELIVERY_NOTE:
            raise ValueError("Dokument ist kein Lieferschein")

        # Prüfen ob bereits Wareneingang existiert
        existing_query = select(GoodsReceipt).where(
            GoodsReceipt.delivery_note_id == document_id
        )
        existing = await self.session.execute(existing_query)
        if existing.scalar_one_or_none():
            raise ValueError("Wareneingang für diesen Lieferschein bereits vorhanden")

        # Wareneingang erstellen
        goods_receipt = GoodsReceipt(
            company_id=company_id,
            delivery_note_id=document_id,
            warehouse_id=warehouse_id,
            supplier_id=document.entity_id,
            delivery_note_number=self._extract_delivery_note_number(document),
            receipt_date=receipt_date or datetime.utcnow(),
            is_processed=False,
            notes=notes,
            created_by=created_by,
        )
        self.session.add(goods_receipt)
        await self.session.flush()

        # Zeilen aus extrahierten Daten erstellen
        await self._create_lines_from_document(goods_receipt, document)

        return goods_receipt

    async def _create_lines_from_document(
        self,
        goods_receipt: GoodsReceipt,
        document: Document,
    ) -> None:
        """Erstellt Wareneingangszeilen aus Dokumentdaten"""
        extracted_data = document.extracted_data or {}
        line_items = extracted_data.get("line_items", [])

        for idx, item_data in enumerate(line_items, start=1):
            line = GoodsReceiptLine(
                goods_receipt_id=goods_receipt.id,
                line_number=idx,
                item_number_extracted=item_data.get("article_number"),
                description=item_data.get("description"),
                quantity_expected=self._parse_quantity(item_data.get("quantity")),
                quantity_received=self._parse_quantity(item_data.get("quantity")) or Decimal("0"),
                unit=item_data.get("unit", "Stück"),
                is_matched=False,
            )
            self.session.add(line)

        await self.session.flush()

    def _extract_delivery_note_number(self, document: Document) -> Optional[str]:
        """Extrahiert Lieferscheinnummer aus Dokumentdaten"""
        extracted_data = document.extracted_data or {}

        # Verschiedene Felder prüfen
        for field in ["delivery_note_number", "lieferschein_nr", "delivery_number", "reference"]:
            if field in extracted_data and extracted_data[field]:
                return str(extracted_data[field])

        return None

    def _parse_quantity(self, value) -> Optional[Decimal]:
        """Parst Menge aus verschiedenen Formaten"""
        if value is None:
            return None

        if isinstance(value, (int, float)):
            return Decimal(str(value))

        if isinstance(value, str):
            # Komma durch Punkt ersetzen
            cleaned = value.replace(",", ".").strip()
            # Nur Zahlen und Punkt
            match = re.search(r"[\d.]+", cleaned)
            if match:
                try:
                    return Decimal(match.group())
                except Exception:
                    return None

        return None

    async def get_by_id(
        self,
        receipt_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> Optional[GoodsReceipt]:
        """Wareneingang mit Zeilen abrufen"""
        query = (
            select(GoodsReceipt)
            .options(selectinload(GoodsReceipt.lines))
            .where(
                and_(
                    GoodsReceipt.id == receipt_id,
                    GoodsReceipt.company_id == company_id,
                )
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_delivery_note(
        self,
        document_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> Optional[GoodsReceipt]:
        """Wareneingang für Lieferschein abrufen"""
        query = (
            select(GoodsReceipt)
            .options(selectinload(GoodsReceipt.lines))
            .where(
                and_(
                    GoodsReceipt.delivery_note_id == document_id,
                    GoodsReceipt.company_id == company_id,
                )
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_pending(
        self,
        company_id: uuid.UUID,
        warehouse_id: Optional[uuid.UUID] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[GoodsReceipt]:
        """Offene Wareneingaenge auflisten"""
        conditions = [
            GoodsReceipt.company_id == company_id,
            GoodsReceipt.is_processed == False,  # noqa: E712
        ]
        if warehouse_id:
            conditions.append(GoodsReceipt.warehouse_id == warehouse_id)

        query = (
            select(GoodsReceipt)
            .options(selectinload(GoodsReceipt.lines))
            .where(and_(*conditions))
            .order_by(GoodsReceipt.receipt_date.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def match_line_to_item(
        self,
        line_id: uuid.UUID,
        item_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> GoodsReceiptLine:
        """Ordnet eine Wareneingangszeile einem Artikel zu"""
        # Zeile laden
        line_query = (
            select(GoodsReceiptLine)
            .join(GoodsReceipt)
            .where(
                and_(
                    GoodsReceiptLine.id == line_id,
                    GoodsReceipt.company_id == company_id,
                )
            )
        )
        result = await self.session.execute(line_query)
        line = result.scalar_one_or_none()

        if not line:
            raise ValueError("Wareneingangszeile nicht gefunden")

        # Artikel prüfen
        item = await self.item_service.get_by_id(item_id, company_id)
        if not item:
            raise ValueError("Artikel nicht gefunden")

        line.item_id = item_id
        line.is_matched = True
        line.match_confidence = Decimal("1.0")  # Manuell = 100%

        await self.session.flush()
        return line

    async def auto_match_lines(
        self,
        receipt_id: uuid.UUID,
        company_id: uuid.UUID,
        min_confidence: float = 0.8,
    ) -> dict:
        """
        Versucht, Zeilen automatisch Artikeln zuzuordnen.

        Args:
            receipt_id: Wareneingangs-ID
            company_id: Unternehmen
            min_confidence: Mindest-Confidence für automatisches Matching

        Returns:
            Dict mit matched, unmatched, total
        """
        receipt = await self.get_by_id(receipt_id, company_id)
        if not receipt:
            raise ValueError("Wareneingang nicht gefunden")

        matched = 0
        unmatched = 0

        for line in receipt.lines:
            if line.is_matched:
                matched += 1
                continue

            # Versuche Matching anhand Artikelnummer
            search_text = line.item_number_extracted or line.description or ""
            if not search_text:
                unmatched += 1
                continue

            matches = await self.item_service.match_from_text(search_text, company_id)

            if matches and matches[0][1] >= min_confidence:
                best_match, confidence = matches[0]
                line.item_id = best_match.id
                line.is_matched = True
                line.match_confidence = Decimal(str(confidence))
                matched += 1
            else:
                unmatched += 1

        await self.session.flush()

        return {
            "matched": matched,
            "unmatched": unmatched,
            "total": len(receipt.lines),
        }

    async def update_line_quantity(
        self,
        line_id: uuid.UUID,
        company_id: uuid.UUID,
        quantity_received: Decimal,
    ) -> GoodsReceiptLine:
        """Aktualisiert die empfangene Menge einer Zeile"""
        line_query = (
            select(GoodsReceiptLine)
            .join(GoodsReceipt)
            .where(
                and_(
                    GoodsReceiptLine.id == line_id,
                    GoodsReceipt.company_id == company_id,
                )
            )
        )
        result = await self.session.execute(line_query)
        line = result.scalar_one_or_none()

        if not line:
            raise ValueError("Wareneingangszeile nicht gefunden")

        line.quantity_received = quantity_received
        await self.session.flush()
        return line

    async def process_receipt(
        self,
        receipt_id: uuid.UUID,
        company_id: uuid.UUID,
        created_by: Optional[uuid.UUID] = None,
    ) -> dict:
        """
        Verarbeitet Wareneingang und bucht Bestände.

        Alle gematchten Zeilen werden als Bestandszugaenge gebucht.

        Args:
            receipt_id: Wareneingangs-ID
            company_id: Unternehmen
            created_by: User ID

        Returns:
            Dict mit booked, skipped, movements
        """
        receipt = await self.get_by_id(receipt_id, company_id)
        if not receipt:
            raise ValueError("Wareneingang nicht gefunden")

        if receipt.is_processed:
            raise ValueError("Wareneingang bereits verarbeitet")

        booked = 0
        skipped = 0
        movements: list[uuid.UUID] = []

        for line in receipt.lines:
            if not line.is_matched or not line.item_id:
                skipped += 1
                continue

            # Warenbewegung buchen
            movement = await self.stock_service.book_movement(
                company_id=company_id,
                item_id=line.item_id,
                warehouse_id=receipt.warehouse_id,
                movement_type=MovementType.GOODS_RECEIPT,
                quantity=line.quantity_received,
                document_id=receipt.delivery_note_id,
                reference_number=receipt.delivery_note_number,
                entity_id=receipt.supplier_id,
                notes=line.description,
                created_by=created_by,
            )

            line.movement_id = movement.id
            movements.append(movement.id)
            booked += 1

        # Wareneingang als verarbeitet markieren
        receipt.is_processed = True
        receipt.processed_at = datetime.utcnow()

        await self.session.flush()

        return {
            "booked": booked,
            "skipped": skipped,
            "movements": movements,
        }

    async def get_unprocessed_delivery_notes(
        self,
        company_id: uuid.UUID,
        limit: int = 50,
    ) -> list[Document]:
        """Lieferscheine ohne Wareneingang finden"""
        # Subquery für bereits verarbeitete
        processed_subq = select(GoodsReceipt.delivery_note_id).where(
            GoodsReceipt.company_id == company_id
        )

        query = (
            select(Document)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.document_type == DocumentType.DELIVERY_NOTE,
                    Document.id.notin_(processed_subq),
                )
            )
            .order_by(Document.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_statistics(
        self,
        company_id: uuid.UUID,
        warehouse_id: Optional[uuid.UUID] = None,
    ) -> dict:
        """Statistiken zu Wareneingaengen"""
        from sqlalchemy import func as sqla_func

        conditions = [GoodsReceipt.company_id == company_id]
        if warehouse_id:
            conditions.append(GoodsReceipt.warehouse_id == warehouse_id)

        # Gesamt
        total_query = select(sqla_func.count()).select_from(GoodsReceipt).where(and_(*conditions))
        total_result = await self.session.execute(total_query)
        total = total_result.scalar_one()

        # Offen
        pending_query = (
            select(sqla_func.count())
            .select_from(GoodsReceipt)
            .where(and_(*conditions, GoodsReceipt.is_processed == False))  # noqa: E712
        )
        pending_result = await self.session.execute(pending_query)
        pending = pending_result.scalar_one()

        # Verarbeitet
        processed = total - pending

        return {
            "total": total,
            "pending": pending,
            "processed": processed,
        }
