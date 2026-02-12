"""DATEV Write-Back Service.

Schreibt Buchungsstapel zurueck an DATEV:
- Buchungssaetze als DATEV CSV (Version 700) fuer Import
- Status-Tracking pro Stapel
- Quittungs-Verarbeitung nach DATEV-Import
"""

import structlog
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict
from uuid import UUID, uuid4
from enum import Enum
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = structlog.get_logger(__name__)

class WritebackStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"         # Bereit zum Export
    EXPORTED = "exported"    # CSV generiert und heruntergeladen
    IMPORTED = "imported"    # In DATEV importiert (manuell bestaetigt)
    ERROR = "error"
    CANCELLED = "cancelled"

@dataclass
class WritebackEntry:
    """Einzelne Buchung fuer Writeback."""
    document_id: str
    soll_konto: str      # Debit account (SKR03/SKR04)
    haben_konto: str     # Credit account
    betrag: Decimal
    belegdatum: datetime
    buchungstext: str
    belegnummer: Optional[str] = None
    steuerschluessel: Optional[str] = None  # BU-Schluessel
    kostenstelle: Optional[str] = None
    kost2: Optional[str] = None

@dataclass
class WritebackBatch:
    """Batch von Buchungen fuer DATEV-Writeback."""
    id: str
    company_id: str
    created_by: str
    status: WritebackStatus = WritebackStatus.DRAFT
    entries: List[WritebackEntry] = field(default_factory=list)
    kontenrahmen: str = "SKR03"
    wirtschaftsjahr_beginn: Optional[str] = None  # "YYYYMMDD"
    berater_nummer: Optional[str] = None
    mandanten_nummer: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    exported_at: Optional[datetime] = None
    imported_at: Optional[datetime] = None
    error_message: Optional[str] = None
    csv_content: Optional[str] = None

# In-memory store
_writeback_batches: Dict[str, WritebackBatch] = {}

class DATEVWritebackService:
    """DATEV Buchungsstapel Writeback."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_batch(self, company_id: UUID, user_id: UUID,
                           kontenrahmen: str = "SKR03") -> WritebackBatch:
        """Erstellt einen neuen Writeback-Batch."""
        batch = WritebackBatch(
            id=str(uuid4()),
            company_id=str(company_id),
            created_by=str(user_id),
            kontenrahmen=kontenrahmen,
        )
        _writeback_batches[batch.id] = batch
        logger.info("datev_writeback_batch_created", batch_id=batch.id)
        return batch

    async def add_entry(self, batch_id: str, entry: WritebackEntry) -> WritebackBatch:
        """Fuegt Buchung zum Batch hinzu."""
        batch = _writeback_batches.get(batch_id)
        if not batch:
            raise ValueError("Batch nicht gefunden")
        if batch.status != WritebackStatus.DRAFT:
            raise ValueError("Batch ist nicht mehr bearbeitbar")
        batch.entries.append(entry)
        return batch

    async def generate_csv(self, batch_id: str) -> str:
        """Generiert DATEV-kompatible CSV (Version 700)."""
        batch = _writeback_batches.get(batch_id)
        if not batch:
            raise ValueError("Batch nicht gefunden")
        if not batch.entries:
            raise ValueError("Batch hat keine Buchungen")

        from app.services.datev.buchungsstapel_writer import BuchungsstapelWriter
        writer = BuchungsstapelWriter()

        # Build CSV header
        lines = []
        lines.append(self._build_header(batch))
        lines.append(self._build_column_header())

        for entry in batch.entries:
            line = self._entry_to_csv_line(entry, batch.kontenrahmen)
            lines.append(line)

        csv_content = "\r\n".join(lines)
        batch.csv_content = csv_content
        batch.status = WritebackStatus.READY
        logger.info("datev_writeback_csv_generated", batch_id=batch_id, entries=len(batch.entries))
        return csv_content

    def _build_header(self, batch: WritebackBatch) -> str:
        """DATEV CSV Header-Zeile."""
        return ";".join([
            '"EXTF"', '700', '21',  # Format, Version, Category
            '"Buchungsstapel"',
            '""',  # Version info
            f'"{batch.created_at.strftime("%Y%m%d%H%M%S")}"',
            '""',  # Reserved
            f'"{batch.berater_nummer or ""}"',
            f'"{batch.mandanten_nummer or ""}"',
            f'"{batch.wirtschaftsjahr_beginn or ""}"',
            '""',  # Sachkontenlänge
            f'"{batch.created_at.strftime("%Y%m%d")}"',  # Datum von
            f'"{batch.created_at.strftime("%Y%m%d")}"',  # Datum bis
            '""',  # Bezeichnung
            '""',  # Diktatkürzel
            '""', '""',  # Buchungstyp, Rechnungslegungszweck
            '""',  # Reserved
            '"0"',  # WKZ
        ])

    def _build_column_header(self) -> str:
        """DATEV CSV Spalten-Header."""
        return ";".join([
            '"Umsatz"', '"S/H"', '"WKZ"', '"Konto"', '"Gegenkonto"',
            '"BU-Schlüssel"', '"Belegdatum"', '"Belegfeld 1"',
            '"Buchungstext"', '"Kostenstelle"', '"Kost2"',
        ])

    def _entry_to_csv_line(self, entry: WritebackEntry, kontenrahmen: str) -> str:
        """Konvertiert Buchung in CSV-Zeile."""
        sh = "S" if entry.betrag >= 0 else "H"
        betrag_str = f'"{abs(entry.betrag):.2f}"'.replace(".", ",")
        return ";".join([
            betrag_str,
            f'"{sh}"',
            '"EUR"',
            f'"{entry.soll_konto}"',
            f'"{entry.haben_konto}"',
            f'"{entry.steuerschluessel or ""}"',
            f'"{entry.belegdatum.strftime("%d%m")}"',
            f'"{entry.belegnummer or ""}"',
            f'"{entry.buchungstext}"',
            f'"{entry.kostenstelle or ""}"',
            f'"{entry.kost2 or ""}"',
        ])

    async def mark_imported(self, batch_id: str) -> WritebackBatch:
        """Markiert Batch als in DATEV importiert."""
        batch = _writeback_batches.get(batch_id)
        if not batch:
            raise ValueError("Batch nicht gefunden")
        batch.status = WritebackStatus.IMPORTED
        batch.imported_at = datetime.now(timezone.utc)
        logger.info("datev_writeback_imported", batch_id=batch_id)
        return batch

    async def export_batch(self, batch_id: str) -> str:
        """Exportiert und markiert Batch."""
        batch = _writeback_batches.get(batch_id)
        if not batch:
            raise ValueError("Batch nicht gefunden")
        if not batch.csv_content:
            await self.generate_csv(batch_id)
        batch.status = WritebackStatus.EXPORTED
        batch.exported_at = datetime.now(timezone.utc)
        return batch.csv_content or ""

    async def list_batches(self, company_id: str, limit: int = 20) -> List[WritebackBatch]:
        """Listet Writeback-Batches einer Firma."""
        batches = [b for b in _writeback_batches.values() if b.company_id == company_id]
        batches.sort(key=lambda b: b.created_at, reverse=True)
        return batches[:limit]

    async def get_batch(self, batch_id: str) -> Optional[WritebackBatch]:
        """Liest einen Writeback-Batch."""
        return _writeback_batches.get(batch_id)
