# -*- coding: utf-8 -*-
"""
USt-Voranmeldung Service (VAT Pre-Registration) - GL-Based.

Generiert USt-VA aus GL Journal Entry Lines (nicht aus Dokumenten).
Verwendet tax_code Mapping zu ELSTER Kennziffern.

GoBD-konform, ELSTER-kompatibel.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.db.models_gl_posting import (
    JournalEntry,
    JournalEntryLine,
    JournalEntryStatus,
    TaxPeriod,
    TaxPeriodType,
    TaxPeriodStatus,
)
from app.services.accounting.vat_service import VATReport  # Reuse existing VATReport class

logger = structlog.get_logger(__name__)


# =============================================================================
# BU-Schlüssel -> ELSTER Kennziffer Mapping (DATEV)
# =============================================================================

# Vereinfachtes Mapping (vollständige Liste siehe DATEV-Doku)
TAX_CODE_TO_KENNZIFFER = {
    # Output VAT (Umsatzsteuer)
    "20": "81",  # Umsatz 19% (Kennziffer 81)
    "21": "86",  # Umsatz 7% (Kennziffer 86)

    # Input VAT (Vorsteuer)
    "40": "66",  # Vorsteuer 19% (Kennziffer 66)
    "41": "66",  # Vorsteuer 7% (Kennziffer 66)

    # Innergemeinschaftlich
    "93": "89",  # IG-Erwerb 19% (Kennziffer 89)
    "94": "93",  # IG-Erwerb 7% (Kennziffer 93)
    "95": "61",  # Vorsteuer IG-Erwerb (Kennziffer 61)
}


@dataclass
class UStVAReport:
    """USt-Voranmeldung Report."""
    company_id: UUID
    fiscal_year: int
    period_type: str
    period_number: int
    period_start: date
    period_end: date

    # Calculated amounts
    total_output_vat: Decimal
    total_input_vat: Decimal
    vat_payable: Decimal

    # Details by Kennziffer
    kennziffer_data: Dict[str, Decimal]


class UStVoranmeldungService:
    """
    Service für USt-Voranmeldung aus GL Entries.

    Liest JournalEntryLines, gruppiert nach tax_code, mappt auf ELSTER Kennziffern.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_ust_voranmeldung(
        self,
        company_id: UUID,
        fiscal_year: int,
        period_type: str,
        period_number: int,
    ) -> UStVAReport:
        """
        Generiert USt-Voranmeldung aus gebuchten Entries.

        Args:
            company_id: Firmen-ID
            fiscal_year: Jahr
            period_type: "monthly" oder "quarterly"
            period_number: Monat 1-12 oder Quartal 1-4

        Returns:
            UStVAReport mit berechneten Beträgen
        """
        # Period-Dates berechnen
        period_start, period_end = self._calculate_period_dates(
            fiscal_year, period_type, period_number
        )

        # Query: Aggregiere tax_amount nach tax_code
        stmt = (
            select(
                JournalEntryLine.tax_code,
                func.sum(JournalEntryLine.tax_amount).label("total_tax"),
            )
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
            .where(
                and_(
                    JournalEntry.company_id == company_id,
                    JournalEntry.fiscal_year == fiscal_year,
                    JournalEntry.status == JournalEntryStatus.POSTED.value,
                    JournalEntry.posting_date >= period_start,
                    JournalEntry.posting_date <= period_end,
                    JournalEntryLine.tax_code.isnot(None),
                )
            )
            .group_by(JournalEntryLine.tax_code)
        )

        result = await self.db.execute(stmt)
        rows = result.all()

        # Mapping auf Kennziffern
        kennziffer_data: Dict[str, Decimal] = {}
        output_vat = Decimal("0")
        input_vat = Decimal("0")

        for row in rows:
            tax_code = row.tax_code
            total_tax = row.total_tax or Decimal("0")

            # Map zu Kennziffer
            kennziffer = TAX_CODE_TO_KENNZIFFER.get(tax_code)
            if not kennziffer:
                logger.warning(
                    "unknown_tax_code",
                    tax_code=tax_code,
                    company_id=str(company_id),
                )
                continue

            kennziffer_data[kennziffer] = kennziffer_data.get(kennziffer, Decimal("0")) + total_tax

            # Output vs Input
            if tax_code in ("20", "21", "93", "94"):
                output_vat += total_tax
            elif tax_code in ("40", "41", "95"):
                input_vat += total_tax

        vat_payable = output_vat - input_vat

        return UStVAReport(
            company_id=company_id,
            fiscal_year=fiscal_year,
            period_type=period_type,
            period_number=period_number,
            period_start=period_start,
            period_end=period_end,
            total_output_vat=output_vat,
            total_input_vat=input_vat,
            vat_payable=vat_payable,
            kennziffer_data=kennziffer_data,
        )

    async def file_ust_voranmeldung(
        self,
        company_id: UUID,
        report: UStVAReport,
    ) -> TaxPeriod:
        """
        Erstellt TaxPeriod Record mit berechneten Beträgen.

        Args:
            company_id: Firmen-ID
            report: Berechneter USt-VA Report

        Returns:
            TaxPeriod (status=filed)
        """
        import uuid
        from sqlalchemy.sql import func

        tax_period = TaxPeriod(
            id=uuid.uuid4(),
            company_id=company_id,
            fiscal_year=report.fiscal_year,
            period_type=report.period_type,
            period_number=report.period_number,
            period_start=report.period_start,
            period_end=report.period_end,
            status=TaxPeriodStatus.FILED.value,
            total_output_vat=report.total_output_vat,
            total_input_vat=report.total_input_vat,
            vat_payable=report.vat_payable,
            filed_at=utc_now(),
            report_data={
                "kennziffer_data": {k: str(v) for k, v in report.kennziffer_data.items()},
            },
        )

        self.db.add(tax_period)
        await self.db.flush()

        logger.info(
            "ust_va_filed",
            tax_period_id=str(tax_period.id),
            company_id=str(company_id),
            vat_payable=str(report.vat_payable),
        )

        return tax_period

    async def export_elster_xml(self, tax_period_id: UUID) -> str:
        """
        Exportiert eine gespeicherte TaxPeriod als ELSTER-XML.

        Laedt den TaxPeriod-Record, konvertiert die Daten in ein VATReport-Objekt
        und delegiert die XML-Erzeugung an VATReport.to_elster_xml().

        Args:
            tax_period_id: ID der gespeicherten Steuerperiode.

        Returns:
            ELSTER-konformes XML als String (UTF-8).

        Raises:
            ValueError: Wenn die TaxPeriod nicht gefunden wird.
        """
        from app.services.accounting.vat_service import (
            VATReportPeriod,
            VATSummary,
            VAT_KENNZIFFERN,
        )
        from app.db.models import Company

        # TaxPeriod laden
        stmt = select(TaxPeriod).where(TaxPeriod.id == tax_period_id)
        result = await self.db.execute(stmt)
        tax_period = result.scalar_one_or_none()

        if tax_period is None:
            raise ValueError(f"TaxPeriod {tax_period_id} nicht gefunden")

        # Steuernummer der Firma laden
        company_stmt = select(Company).where(Company.id == tax_period.company_id)
        company_result = await self.db.execute(company_stmt)
        company = company_result.scalar_one_or_none()
        steuernummer = company.tax_number if company else None

        # Period-Type bestimmen
        if tax_period.period_type == "monthly":
            period_type = VATReportPeriod.MONTHLY
            month_names = [
                "", "Januar", "Februar", "Maerz", "April", "Mai", "Juni",
                "Juli", "August", "September", "Oktober", "November", "Dezember",
            ]
            period_label = f"{month_names[tax_period.period_number]} {tax_period.fiscal_year}"
        elif tax_period.period_type == "quarterly":
            period_type = VATReportPeriod.QUARTERLY
            period_label = f"Q{tax_period.period_number}/{tax_period.fiscal_year}"
        else:
            period_type = VATReportPeriod.YEARLY
            period_label = str(tax_period.fiscal_year)

        # Kennziffer-Daten aus report_data extrahieren
        kz_data: Dict[str, Decimal] = {}
        if tax_period.report_data and "kennziffer_data" in tax_period.report_data:
            for kz, val in tax_period.report_data["kennziffer_data"].items():
                kz_data[kz] = Decimal(str(val))

        def _kz_summary(kz: str) -> VATSummary:
            """Erstellt VATSummary fuer eine Kennziffer."""
            label = VAT_KENNZIFFERN.get(kz, kz)
            amount = kz_data.get(kz, Decimal("0"))
            return VATSummary(kennziffer=kz, label=label, vat_amount=amount, net_amount=amount)

        # VATReport zusammenbauen
        report = VATReport(
            company_id=tax_period.company_id,
            period_type=period_type,
            period_start=tax_period.period_start,
            period_end=tax_period.period_end,
            period_label=period_label,
            generated_at=tax_period.filed_at or utc_now(),
            status=tax_period.status,
            output_vat_19=_kz_summary("81"),
            output_vat_7=_kz_summary("86"),
            inner_eu_deliveries=_kz_summary("41"),
            export_deliveries=_kz_summary("43"),
            input_vat=_kz_summary("66"),
            input_vat_inner_eu=_kz_summary("61"),
            input_vat_reverse_charge=_kz_summary("67"),
            inner_eu_acquisition_19=_kz_summary("89"),
            inner_eu_acquisition_7=_kz_summary("93"),
            total_output_vat=tax_period.total_output_vat or Decimal("0"),
            total_input_vat=tax_period.total_input_vat or Decimal("0"),
            vat_payable=tax_period.vat_payable or Decimal("0"),
        )

        logger.info(
            "elster_xml_exported",
            tax_period_id=str(tax_period_id),
            company_id=str(tax_period.company_id),
            period=period_label,
        )

        return report.to_elster_xml(steuernummer=steuernummer)

    def _calculate_period_dates(
        self,
        fiscal_year: int,
        period_type: str,
        period_number: int,
    ) -> tuple[date, date]:
        """Berechnet Start/End-Datum für Periode."""
        from datetime import date as dt_date

        if period_type == "monthly":
            start = dt_date(fiscal_year, period_number, 1)
            if period_number == 12:
                end = dt_date(fiscal_year, 12, 31)
            else:
                next_month = dt_date(fiscal_year, period_number + 1, 1)
                from datetime import timedelta
                end = next_month - timedelta(days=1)
        elif period_type == "quarterly":
            start_month = (period_number - 1) * 3 + 1
            start = dt_date(fiscal_year, start_month, 1)
            end_month = start_month + 2
            if end_month == 12:
                end = dt_date(fiscal_year, 12, 31)
            else:
                next_quarter = dt_date(fiscal_year, end_month + 1, 1)
                from datetime import timedelta
                end = next_quarter - timedelta(days=1)
        else:
            raise ValueError(f"Invalid period_type: {period_type}")

        return start, end


def get_ust_voranmeldung_service(db: AsyncSession) -> UStVoranmeldungService:
    """FastAPI Dependency."""
    return UStVoranmeldungService(db)
