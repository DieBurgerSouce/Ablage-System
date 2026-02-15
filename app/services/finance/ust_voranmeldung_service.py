# -*- coding: utf-8 -*-
"""
USt-Voranmeldung Service - Automatische Umsatzsteuer-Aggregation.

Aggregiert Vorsteuer aus Eingangsrechnungen und Umsatzsteuer aus
Ausgangsrechnungen. Erstellt ELSTER-kompatibles Format.
Quartalsweise und monatliche Zusammenstellung.

Feinpoliert und durchdacht - Enterprise-grade Steuerberichterstattung.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from uuid import UUID
import uuid as uuid_mod
import xml.etree.ElementTree as ET

import structlog
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.db.models_german_finance import (
    UStVoranmeldung,
    VATReportPeriod,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Steuersatz-Konstanten
# =============================================================================

STEUERSATZ_NORMAL = Decimal("19")
STEUERSATZ_ERMAESSIGT = Decimal("7")


class UStVoranmeldungService:
    """USt-Voranmeldung - Automatische Umsatzsteuer-Aggregation.

    Aggregiert Vorsteuer aus Eingangsrechnungen und Umsatzsteuer aus
    Ausgangsrechnungen. Erstellt ELSTER-kompatibles Format.
    """

    async def calculate_period(
        self,
        db: AsyncSession,
        company_id: UUID,
        year: int,
        month: Optional[int] = None,
        quarter: Optional[int] = None,
    ) -> UStVoranmeldung:
        """USt-Voranmeldung fuer einen Zeitraum berechnen.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            year: Steuerjahr
            month: Monat (1-12) fuer monatliche VA
            quarter: Quartal (1-4) fuer quartalsweise VA

        Returns:
            UStVoranmeldung mit berechneten Betraegen

        Raises:
            ValueError: Wenn weder Monat noch Quartal angegeben
        """
        if month is None and quarter is None:
            raise ValueError("Entweder Monat oder Quartal muss angegeben werden")

        if month is not None:
            period_type = VATReportPeriod.MONTHLY.value
            period_start, period_end = self._month_range(year, month)
        else:
            period_type = VATReportPeriod.QUARTERLY.value
            period_start, period_end = self._quarter_range(year, quarter)

        # Rechnungsdaten aggregieren
        vorsteuer_details, umsatzsteuer_details, ig_lieferungen = (
            await self._aggregate_invoices(db, company_id, period_start, period_end)
        )

        vorsteuer_summe = sum(vorsteuer_details.values())
        umsatzsteuer_summe = sum(umsatzsteuer_details.values())
        zahllast = umsatzsteuer_summe - vorsteuer_summe

        # Vorhandene VA pruefen oder neu erstellen
        existing = await self._find_existing(db, company_id, period_start, period_end)

        if existing:
            va = existing
        else:
            va = UStVoranmeldung(
                id=uuid_mod.uuid4(),
                company_id=company_id,
                period_start=period_start,
                period_end=period_end,
                period_type=period_type,
            )
            db.add(va)

        va.vorsteuer_summe = float(vorsteuer_summe)
        va.umsatzsteuer_summe = float(umsatzsteuer_summe)
        va.zahllast = float(zahllast)
        va.innergemeinschaftliche_lieferungen = float(ig_lieferungen)
        va.vorsteuer_details = {k: float(v) for k, v in vorsteuer_details.items()}
        va.umsatzsteuer_details = {k: float(v) for k, v in umsatzsteuer_details.items()}
        va.status = "geprueft"

        await db.flush()

        logger.info(
            "ust_va_berechnet",
            company_id=str(company_id),
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
            zahllast=float(zahllast),
        )

        return va

    async def generate_elster_xml(
        self,
        db: AsyncSession,
        voranmeldung_id: UUID,
    ) -> str:
        """ELSTER-kompatibles XML generieren.

        Args:
            db: Datenbank-Session
            voranmeldung_id: ID der USt-VA

        Returns:
            XML-String (UTF-8)

        Raises:
            ValueError: Wenn USt-VA nicht gefunden
        """
        from app.db.models import Company

        stmt = select(UStVoranmeldung).where(UStVoranmeldung.id == voranmeldung_id)
        result = await db.execute(stmt)
        va = result.scalar_one_or_none()

        if va is None:
            raise ValueError(f"USt-Voranmeldung {voranmeldung_id} nicht gefunden")

        # Steuernummer laden
        company_stmt = select(Company).where(Company.id == va.company_id)
        company_result = await db.execute(company_stmt)
        company = company_result.scalar_one_or_none()
        steuernummer = getattr(company, "tax_number", None) if company else None

        xml_str = self._build_elster_xml(va, steuernummer)

        va.elster_xml = xml_str
        await db.flush()

        logger.info(
            "elster_xml_generiert",
            voranmeldung_id=str(voranmeldung_id),
            company_id=str(va.company_id),
        )

        return xml_str

    async def compare_with_datev(
        self,
        db: AsyncSession,
        voranmeldung_id: UUID,
    ) -> Dict[str, object]:
        """Abgleich mit DATEV-Buchungen.

        Args:
            db: Datenbank-Session
            voranmeldung_id: ID der USt-VA

        Returns:
            Dict mit Abgleich-Ergebnis (status, abweichungen)
        """
        from app.db.models_gl_posting import (
            JournalEntry, JournalEntryLine, JournalEntryStatus,
        )

        stmt = select(UStVoranmeldung).where(UStVoranmeldung.id == voranmeldung_id)
        result = await db.execute(stmt)
        va = result.scalar_one_or_none()

        if va is None:
            raise ValueError(f"USt-Voranmeldung {voranmeldung_id} nicht gefunden")

        # DATEV-Buchungen aggregieren
        tax_stmt = (
            select(
                JournalEntryLine.tax_code,
                func.sum(JournalEntryLine.tax_amount).label("total_tax"),
            )
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
            .where(
                and_(
                    JournalEntry.company_id == va.company_id,
                    JournalEntry.status == JournalEntryStatus.POSTED.value,
                    JournalEntry.posting_date >= va.period_start,
                    JournalEntry.posting_date <= va.period_end,
                    JournalEntryLine.tax_code.isnot(None),
                )
            )
            .group_by(JournalEntryLine.tax_code)
        )

        tax_result = await db.execute(tax_stmt)
        tax_rows = tax_result.all()

        datev_vorsteuer = Decimal("0")
        datev_umsatzsteuer = Decimal("0")

        for row in tax_rows:
            total_tax = Decimal(str(row.total_tax or 0))
            if row.tax_code in ("40", "41", "95"):
                datev_vorsteuer += total_tax
            elif row.tax_code in ("20", "21", "93", "94"):
                datev_umsatzsteuer += total_tax

        va_vorsteuer = Decimal(str(va.vorsteuer_summe))
        va_umsatzsteuer = Decimal(str(va.umsatzsteuer_summe))

        abweichung_vorsteuer = abs(va_vorsteuer - datev_vorsteuer)
        abweichung_umsatzsteuer = abs(va_umsatzsteuer - datev_umsatzsteuer)

        toleranz = Decimal("0.01")
        has_discrepancy = (
            abweichung_vorsteuer > toleranz
            or abweichung_umsatzsteuer > toleranz
        )

        abgleich_details = {
            "datev_vorsteuer": float(datev_vorsteuer),
            "datev_umsatzsteuer": float(datev_umsatzsteuer),
            "va_vorsteuer": float(va_vorsteuer),
            "va_umsatzsteuer": float(va_umsatzsteuer),
            "abweichung_vorsteuer": float(abweichung_vorsteuer),
            "abweichung_umsatzsteuer": float(abweichung_umsatzsteuer),
            "abgleich_datum": utc_now().isoformat(),
            "status": "abweichung" if has_discrepancy else "uebereinstimmung",
        }

        logger.info(
            "datev_abgleich_durchgefuehrt",
            voranmeldung_id=str(voranmeldung_id),
            status="abweichung" if has_discrepancy else "uebereinstimmung",
        )

        return abgleich_details

    async def get_report(
        self,
        db: AsyncSession,
        report_id: UUID,
    ) -> Optional[UStVoranmeldung]:
        """Hole eine bestimmte USt-Voranmeldung."""
        stmt = select(UStVoranmeldung).where(UStVoranmeldung.id == report_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_reports(
        self,
        db: AsyncSession,
        company_id: UUID,
        year: int,
    ) -> List[UStVoranmeldung]:
        """Jahresuebersicht aller USt-Voranmeldungen."""
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)

        stmt = (
            select(UStVoranmeldung)
            .where(
                and_(
                    UStVoranmeldung.company_id == company_id,
                    UStVoranmeldung.period_start >= year_start,
                    UStVoranmeldung.period_end <= year_end,
                )
            )
            .order_by(UStVoranmeldung.period_start.asc())
        )

        result = await db.execute(stmt)
        return list(result.scalars().all())

    # Alias fuer Abwaertskompatibilitaet
    get_period_overview = list_reports

    async def validate_report(
        self,
        db: AsyncSession,
        report_id: UUID,
    ) -> Dict[str, object]:
        """Validiere USt-Voranmeldung gegen DATEV-Buchungen (falls vorhanden).

        Returns:
            Dict mit Validierungsergebnis und ggf. Abweichungen
        """
        report = await self.get_report(db, report_id)
        if report is None:
            raise ValueError(f"USt-Voranmeldung {report_id} nicht gefunden")

        abgleich = await self.compare_with_datev(db, report_id)
        return {
            "report_id": str(report_id),
            "status": abgleich.get("status", "unbekannt"),
            "datev_vergleich_moeglich": True,
            "abweichungen": abgleich,
            "geprueft_am": utc_now().isoformat(),
        }

    async def get_tax_rate_breakdown(
        self,
        db: AsyncSession,
        company_id: UUID,
        period_start: date,
        period_end: date,
    ) -> Dict[str, object]:
        """Detaillierte Aufschluesselung nach Steuersatz.

        Returns:
            Dict mit vorsteuer und umsatzsteuer pro Steuersatz
        """
        # Temporaer berechnen ohne zu speichern
        vorsteuer, umsatzsteuer, ig = await self._aggregate_invoices(
            db, company_id, period_start, period_end
        )

        return {
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "vorsteuer": {k: float(v) for k, v in vorsteuer.items()},
            "umsatzsteuer": {k: float(v) for k, v in umsatzsteuer.items()},
            "vorsteuer_summe": float(sum(vorsteuer.values())),
            "umsatzsteuer_summe": float(sum(umsatzsteuer.values())),
            "zahllast": float(sum(umsatzsteuer.values()) - sum(vorsteuer.values())),
            "innergemeinschaftliche_lieferungen": float(ig),
        }

    # =========================================================================
    # Private Methoden
    # =========================================================================

    async def _aggregate_invoices(
        self,
        db: AsyncSession,
        company_id: UUID,
        period_start: date,
        period_end: date,
    ) -> Tuple[Dict[str, Decimal], Dict[str, Decimal], Decimal]:
        """Aggregiert Rechnungsdaten fuer den Zeitraum.

        Returns:
            Tuple von (vorsteuer_details, umsatzsteuer_details, ig_lieferungen)
        """
        from app.db.models import InvoiceTracking

        vorsteuer: Dict[str, Decimal] = {"19": Decimal("0"), "7": Decimal("0")}
        umsatzsteuer: Dict[str, Decimal] = {"19": Decimal("0"), "7": Decimal("0")}
        ig_lieferungen = Decimal("0")

        stmt = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.invoice_date >= datetime(
                    period_start.year, period_start.month, period_start.day
                ),
                InvoiceTracking.invoice_date <= datetime(
                    period_end.year, period_end.month, period_end.day, 23, 59, 59,
                ),
                InvoiceTracking.deleted_at.is_(None),
            )
        )

        result = await db.execute(stmt)
        invoices = result.scalars().all()

        for inv in invoices:
            amount = Decimal(str(inv.amount or 0))
            tax_rate = Decimal(str(getattr(inv, "tax_rate", 19) or 19))
            inv_type = getattr(inv, "invoice_type", "incoming") or "incoming"

            # Steuer aus Bruttobetrag
            tax_amount = amount * tax_rate / (Decimal("100") + tax_rate)
            tax_amount = tax_amount.quantize(Decimal("0.01"))

            rate_key = "7" if tax_rate == STEUERSATZ_ERMAESSIGT else "19"

            if inv_type in ("incoming", "eingang"):
                vorsteuer[rate_key] += tax_amount
            else:
                umsatzsteuer[rate_key] += tax_amount

        return vorsteuer, umsatzsteuer, ig_lieferungen

    async def _find_existing(
        self,
        db: AsyncSession,
        company_id: UUID,
        period_start: date,
        period_end: date,
    ) -> Optional[UStVoranmeldung]:
        """Sucht vorhandene USt-VA fuer den Zeitraum."""
        stmt = select(UStVoranmeldung).where(
            and_(
                UStVoranmeldung.company_id == company_id,
                UStVoranmeldung.period_start == period_start,
                UStVoranmeldung.period_end == period_end,
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    def _month_range(self, year: int, month: int) -> Tuple[date, date]:
        """Berechnet Start/Ende eines Monats."""
        start = date(year, month, 1)
        if month == 12:
            end = date(year, 12, 31)
        else:
            end = date(year, month + 1, 1) - timedelta(days=1)
        return start, end

    def _quarter_range(self, year: int, quarter: int) -> Tuple[date, date]:
        """Berechnet Start/Ende eines Quartals."""
        start_month = (quarter - 1) * 3 + 1
        start = date(year, start_month, 1)
        end_month = start_month + 2
        if end_month == 12:
            end = date(year, 12, 31)
        else:
            end = date(year, end_month + 1, 1) - timedelta(days=1)
        return start, end

    def _build_elster_xml(
        self,
        va: UStVoranmeldung,
        steuernummer: Optional[str],
    ) -> str:
        """Baut ELSTER-konformes XML."""
        root = ET.Element("Elster", xmlns="http://www.elster.de/elsterxml/schema/v11")
        transfer = ET.SubElement(root, "TransferHeader", version="11")
        ET.SubElement(transfer, "Verfahren").text = "ElsterAnmeldung"
        ET.SubElement(transfer, "DatenArt").text = "UStVA"
        ET.SubElement(transfer, "Vorgang").text = "send-NoSig"

        daten_teil = ET.SubElement(root, "DatenTeil")
        nutzdatenblock = ET.SubElement(daten_teil, "Nutzdatenblock")
        nutzdaten = ET.SubElement(nutzdatenblock, "Nutzdaten")

        anmeldungssteuern = ET.SubElement(nutzdaten, "Anmeldungssteuern", art="UStVA")

        if steuernummer:
            ET.SubElement(anmeldungssteuern, "Steuernummer").text = steuernummer

        ET.SubElement(anmeldungssteuern, "Jahr").text = str(va.period_start.year)

        if va.period_type == VATReportPeriod.MONTHLY.value:
            ET.SubElement(anmeldungssteuern, "Zeitraum").text = str(
                va.period_start.month
            ).zfill(2)
        else:
            quarter = (va.period_start.month - 1) // 3 + 1
            quarter_map = {1: "41", 2: "42", 3: "43", 4: "44"}
            ET.SubElement(anmeldungssteuern, "Zeitraum").text = quarter_map.get(
                quarter, "41"
            )

        # Kennziffern
        ust_details = va.umsatzsteuer_details or {}
        vst_details = va.vorsteuer_details or {}

        kennziffern = {
            "Kz81": ust_details.get("19", 0),
            "Kz86": ust_details.get("7", 0),
            "Kz66": sum(vst_details.values()) if vst_details else 0,
            "Kz41": va.innergemeinschaftliche_lieferungen,
            "Kz83": va.zahllast,
        }

        for kz_name, kz_value in kennziffern.items():
            if kz_value and kz_value != 0:
                ET.SubElement(anmeldungssteuern, kz_name).text = f"{kz_value:.2f}"

        return ET.tostring(root, encoding="unicode", xml_declaration=True)


def get_ust_voranmeldung_service() -> UStVoranmeldungService:
    """FastAPI Dependency."""
    return UStVoranmeldungService()
