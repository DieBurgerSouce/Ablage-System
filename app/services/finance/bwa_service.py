# -*- coding: utf-8 -*-
"""
BWA Service - Betriebswirtschaftliche Auswertung.

Standard-BWA nach SKR03/SKR04.
Monatlich, quartalsweise, jaehrlich.
Vergleich mit Vorjahr/Vormonat.

Feinpoliert und durchdacht - Enterprise-grade Finanzberichterstattung.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from uuid import UUID
import uuid as uuid_mod

import structlog
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.db.models_german_finance import (
    BWAReport,
    BWAPeriod,
    SKRSchema,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# SKR03 Kontenmapping
# =============================================================================

SKR03_RANGES: Dict[str, List[str]] = {
    "erloese": ["8000-8999"],
    "materialaufwand": ["3000-3999"],
    "personalaufwand": ["4000-4199"],
    "abschreibungen": ["4800-4855"],
    "sonstige_aufwendungen": ["4200-4799", "4856-4999"],
    "zinsertraege": ["7000-7099"],
    "zinsaufwand": ["7300-7399"],
}

SKR04_RANGES: Dict[str, List[str]] = {
    "erloese": ["4000-4999"],
    "materialaufwand": ["5000-5999"],
    "personalaufwand": ["6000-6199"],
    "abschreibungen": ["6200-6255"],
    "sonstige_aufwendungen": ["6256-6999"],
    "zinsertraege": ["7000-7099"],
    "zinsaufwand": ["7300-7399"],
}


class BWAService:
    """Betriebswirtschaftliche Auswertung (BWA).

    Standard-BWA nach SKR03/SKR04 mit Vorjahresvergleich.
    """

    async def generate_bwa(
        self,
        db: AsyncSession,
        company_id: UUID,
        skr_schema: SKRSchema,
        period_type: BWAPeriod,
        year: int,
        month: Optional[int] = None,
        quarter: Optional[int] = None,
    ) -> BWAReport:
        """BWA generieren fuer einen Zeitraum.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            skr_schema: Kontenrahmen (SKR03/SKR04)
            period_type: monthly, quarterly, yearly
            year: Berichtsjahr
            month: Berichtsmonat (1-12)
            quarter: Berichtsquartal (1-4)

        Returns:
            BWAReport mit allen berechneten Positionen
        """
        period_start, period_end = self._calculate_period_range(
            period_type, year, month, quarter
        )

        # GL-Daten aggregieren
        positionen = await self._aggregate_gl_entries(
            db, company_id, skr_schema, period_start, period_end
        )

        # Ergebnisrechnung
        erloese_total = self._sum_position(positionen.get("erloese"))
        material_total = self._sum_position(positionen.get("materialaufwand"))
        personal_total = self._sum_position(positionen.get("personalaufwand"))
        afa_total = self._sum_position(positionen.get("abschreibungen"))
        sonstige_total = self._sum_position(positionen.get("sonstige_aufwendungen"))

        betriebsergebnis = erloese_total - material_total - personal_total - afa_total - sonstige_total

        zinsertraege = self._sum_position(positionen.get("zinsertraege"))
        zinsaufwand = self._sum_position(positionen.get("zinsaufwand"))
        finanzergebnis = zinsertraege - zinsaufwand

        ergebnis_vor_steuern = betriebsergebnis + finanzergebnis

        # Vereinfachte Steuer (ca. 30%)
        steuern = max(0.0, ergebnis_vor_steuern * 0.30)
        jahresueberschuss = ergebnis_vor_steuern - steuern

        # Vorjahresvergleich
        vorjahresvergleich = await self._load_previous_year(
            db, company_id, skr_schema, period_start, period_end
        )

        # Vorhandene BWA pruefen oder neu erstellen
        existing = await self._find_existing(db, company_id, period_start, period_end)

        if existing:
            report = existing
        else:
            report = BWAReport(
                id=uuid_mod.uuid4(),
                company_id=company_id,
            )
            db.add(report)

        report.period_start = period_start
        report.period_end = period_end
        report.period_type = period_type.value
        report.skr_schema = skr_schema.value
        report.erloese = positionen.get("erloese")
        report.materialaufwand = positionen.get("materialaufwand")
        report.personalaufwand = positionen.get("personalaufwand")
        report.abschreibungen = positionen.get("abschreibungen")
        report.sonstige_aufwendungen = positionen.get("sonstige_aufwendungen")
        report.betriebsergebnis = betriebsergebnis
        report.finanzergebnis = finanzergebnis
        report.ergebnis_vor_steuern = ergebnis_vor_steuern
        report.steuern = steuern
        report.jahresueberschuss = jahresueberschuss
        report.vorjahresvergleich = vorjahresvergleich
        report.status = "freigegeben"

        await db.flush()

        logger.info(
            "bwa_generiert",
            company_id=str(company_id),
            schema=skr_schema.value,
            period=f"{period_start} - {period_end}",
            jahresueberschuss=jahresueberschuss,
        )

        return report

    async def get_bwa(
        self,
        db: AsyncSession,
        report_id: UUID,
    ) -> Optional[BWAReport]:
        """Hole einen BWA-Report."""
        stmt = select(BWAReport).where(BWAReport.id == report_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_bwa_reports(
        self,
        db: AsyncSession,
        company_id: UUID,
        year: int,
    ) -> List[BWAReport]:
        """Liste BWA-Reports fuer ein Jahr."""
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)

        stmt = (
            select(BWAReport)
            .where(
                and_(
                    BWAReport.company_id == company_id,
                    BWAReport.period_start >= year_start,
                    BWAReport.period_end <= year_end,
                )
            )
            .order_by(BWAReport.period_start.asc())
        )

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def export_pdf(
        self,
        db: AsyncSession,
        report_id: UUID,
    ) -> Dict[str, object]:
        """Generiere PDF-ready Datenstruktur fuer einen BWA-Report.

        Returns:
            Dict mit allen BWA-Daten fuer PDF-Rendering
        """
        report = await self.get_bwa(db, report_id)
        if report is None:
            raise ValueError(f"BWA-Report {report_id} nicht gefunden")

        return {
            "titel": "Betriebswirtschaftliche Auswertung",
            "untertitel": f"Zeitraum: {report.period_start} bis {report.period_end}",
            "schema": report.skr_schema,
            "positionen": [
                {
                    "gruppe": "I. Erloese",
                    "details": report.erloese or {},
                    "summe": self._sum_position(report.erloese),
                },
                {
                    "gruppe": "II. Materialaufwand",
                    "details": report.materialaufwand or {},
                    "summe": self._sum_position(report.materialaufwand),
                },
                {
                    "gruppe": "III. Personalaufwand",
                    "details": report.personalaufwand or {},
                    "summe": self._sum_position(report.personalaufwand),
                },
                {
                    "gruppe": "IV. Sonstige Aufwendungen",
                    "details": report.sonstige_aufwendungen or {},
                    "summe": self._sum_position(report.sonstige_aufwendungen),
                },
                {
                    "gruppe": "V. Abschreibungen",
                    "details": report.abschreibungen or {},
                    "summe": self._sum_position(report.abschreibungen),
                },
            ],
            "ergebnisse": {
                "betriebsergebnis": report.betriebsergebnis,
                "finanzergebnis": report.finanzergebnis,
                "ergebnis_vor_steuern": report.ergebnis_vor_steuern,
                "steuern": report.steuern,
                "jahresueberschuss": report.jahresueberschuss,
            },
            "vorjahresvergleich": report.vorjahresvergleich,
            "generiert_am": utc_now().isoformat(),
        }

    async def compare_periods(
        self,
        db: AsyncSession,
        company_id: UUID,
        period_a_start: date,
        period_a_end: date,
        period_b_start: date,
        period_b_end: date,
    ) -> Dict[str, object]:
        """Vergleiche zwei BWA-Perioden side-by-side.

        Returns:
            Dict mit Vergleich und Abweichungen
        """
        reports_a = await self._find_reports_in_range(
            db, company_id, period_a_start, period_a_end
        )
        reports_b = await self._find_reports_in_range(
            db, company_id, period_b_start, period_b_end
        )

        def _agg(reports: List[BWAReport]) -> Dict[str, float]:
            return {
                "betriebsergebnis": sum(r.betriebsergebnis for r in reports),
                "finanzergebnis": sum(r.finanzergebnis for r in reports),
                "ergebnis_vor_steuern": sum(r.ergebnis_vor_steuern for r in reports),
                "steuern": sum(r.steuern for r in reports),
                "jahresueberschuss": sum(r.jahresueberschuss for r in reports),
            }

        data_a = _agg(reports_a)
        data_b = _agg(reports_b)

        abweichungen: Dict[str, Dict[str, float]] = {}
        for key in data_a:
            val_a = data_a[key]
            val_b = data_b[key]
            diff = val_b - val_a
            pct = (diff / val_a * 100) if val_a != 0 else 0.0
            abweichungen[key] = {
                "periode_a": round(val_a, 2),
                "periode_b": round(val_b, 2),
                "differenz": round(diff, 2),
                "veraenderung_prozent": round(pct, 1),
            }

        return {
            "periode_a": {
                "start": period_a_start.isoformat(),
                "end": period_a_end.isoformat(),
                "daten": data_a,
            },
            "periode_b": {
                "start": period_b_start.isoformat(),
                "end": period_b_end.isoformat(),
                "daten": data_b,
            },
            "abweichungen": abweichungen,
            "verglichen_am": utc_now().isoformat(),
        }

    async def generate_comparison(
        self,
        db: AsyncSession,
        company_id: UUID,
        bwa_id: UUID,
    ) -> Dict[str, object]:
        """Vergleich mit Vorjahr/Vormonat.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            bwa_id: ID der aktuellen BWA

        Returns:
            Dict mit Vergleichsdaten
        """
        stmt = select(BWAReport).where(
            and_(BWAReport.id == bwa_id, BWAReport.company_id == company_id)
        )
        result = await db.execute(stmt)
        current_bwa = result.scalar_one_or_none()

        if current_bwa is None:
            raise ValueError(f"BWA {bwa_id} nicht gefunden")

        current_data = {
            "betriebsergebnis": current_bwa.betriebsergebnis,
            "finanzergebnis": current_bwa.finanzergebnis,
            "ergebnis_vor_steuern": current_bwa.ergebnis_vor_steuern,
            "jahresueberschuss": current_bwa.jahresueberschuss,
        }

        previous_data = current_bwa.vorjahresvergleich or {}
        diffs: Dict[str, object] = {}

        for key, current_val in current_data.items():
            prev_val = previous_data.get(key, 0.0)
            absolute_diff = (current_val or 0.0) - (prev_val or 0.0)
            pct_diff = None
            if prev_val and prev_val != 0:
                pct_diff = round(absolute_diff / abs(prev_val) * 100, 2)

            diffs[key] = {
                "aktuell": current_val,
                "vorjahr": prev_val,
                "differenz": round(absolute_diff, 2),
                "differenz_prozent": pct_diff,
            }

        return diffs

    async def get_yearly_overview(
        self,
        db: AsyncSession,
        company_id: UUID,
        year: int,
        skr_schema: SKRSchema,
    ) -> List[BWAReport]:
        """Alle BWAs eines Jahres abrufen."""
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)

        stmt = (
            select(BWAReport)
            .where(
                and_(
                    BWAReport.company_id == company_id,
                    BWAReport.period_start >= year_start,
                    BWAReport.period_end <= year_end,
                    BWAReport.skr_schema == skr_schema.value,
                )
            )
            .order_by(BWAReport.period_start.asc())
        )

        result = await db.execute(stmt)
        return list(result.scalars().all())

    # =========================================================================
    # Private Methoden
    # =========================================================================

    async def _aggregate_gl_entries(
        self,
        db: AsyncSession,
        company_id: UUID,
        skr_schema: SKRSchema,
        period_start: date,
        period_end: date,
    ) -> Dict[str, object]:
        """Aggregiert GL-Eintraege nach BWA-Positionen."""
        from app.db.models_gl_posting import (
            JournalEntry, JournalEntryLine, JournalEntryStatus,
        )

        ranges = SKR03_RANGES if skr_schema == SKRSchema.SKR03 else SKR04_RANGES

        stmt = (
            select(
                JournalEntryLine.account_number,
                func.sum(JournalEntryLine.debit_amount).label("total_debit"),
                func.sum(JournalEntryLine.credit_amount).label("total_credit"),
            )
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
            .where(
                and_(
                    JournalEntry.company_id == company_id,
                    JournalEntry.status == JournalEntryStatus.POSTED.value,
                    JournalEntry.posting_date >= period_start,
                    JournalEntry.posting_date <= period_end,
                )
            )
            .group_by(JournalEntryLine.account_number)
        )

        query_result = await db.execute(stmt)
        rows = query_result.all()

        result_dict: Dict[str, object] = {}

        for position, account_ranges in ranges.items():
            konten: List[Dict[str, object]] = []
            total = 0.0

            for row in rows:
                acct = row.account_number or ""
                debit = float(row.total_debit or 0)
                credit = float(row.total_credit or 0)

                for acct_range in account_ranges:
                    if self._account_in_range(acct, acct_range):
                        # Erloese: Credit-Seite; Aufwand: Debit-Seite
                        if position in ("erloese", "zinsertraege"):
                            betrag = credit - debit
                        else:
                            betrag = debit - credit

                        konten.append({
                            "konto": acct,
                            "betrag": round(betrag, 2),
                        })
                        total += betrag
                        break

            result_dict[position] = {
                "total": round(total, 2),
                "konten": konten,
            }

        return result_dict

    def _sum_position(self, position_data: Optional[Dict[str, object]]) -> float:
        """Summiert eine BWA-Position."""
        if not position_data:
            return 0.0
        if isinstance(position_data, dict):
            return float(position_data.get("total", 0.0))
        return 0.0

    async def _load_previous_year(
        self,
        db: AsyncSession,
        company_id: UUID,
        skr_schema: SKRSchema,
        period_start: date,
        period_end: date,
    ) -> Optional[Dict[str, object]]:
        """Laedt Vorjahresdaten fuer Vergleich."""
        prev_start = date(period_start.year - 1, period_start.month, period_start.day)
        try:
            prev_end = date(period_end.year - 1, period_end.month, period_end.day)
        except ValueError:
            # 29. Februar -> 28. Februar
            prev_end = date(period_end.year - 1, period_end.month, 28)

        prev_bwa = await self._find_existing(db, company_id, prev_start, prev_end)

        if prev_bwa is None:
            return None

        return {
            "betriebsergebnis": prev_bwa.betriebsergebnis,
            "finanzergebnis": prev_bwa.finanzergebnis,
            "ergebnis_vor_steuern": prev_bwa.ergebnis_vor_steuern,
            "steuern": prev_bwa.steuern,
            "jahresueberschuss": prev_bwa.jahresueberschuss,
            "period_start": prev_start.isoformat(),
            "period_end": prev_end.isoformat(),
        }

    async def _find_existing(
        self,
        db: AsyncSession,
        company_id: UUID,
        period_start: date,
        period_end: date,
    ) -> Optional[BWAReport]:
        """Sucht vorhandene BWA."""
        stmt = select(BWAReport).where(
            and_(
                BWAReport.company_id == company_id,
                BWAReport.period_start == period_start,
                BWAReport.period_end == period_end,
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _find_reports_in_range(
        self,
        db: AsyncSession,
        company_id: UUID,
        range_start: date,
        range_end: date,
    ) -> List[BWAReport]:
        """Sucht alle BWA-Reports in einem Zeitraum."""
        stmt = (
            select(BWAReport)
            .where(
                and_(
                    BWAReport.company_id == company_id,
                    BWAReport.period_start >= range_start,
                    BWAReport.period_end <= range_end,
                )
            )
            .order_by(BWAReport.period_start.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    def _account_in_range(self, account_number: str, account_range: str) -> bool:
        """Prueft ob ein Konto im angegebenen Bereich liegt."""
        if "-" not in account_range:
            return account_number == account_range
        try:
            parts = account_range.split("-")
            return int(parts[0]) <= int(account_number) <= int(parts[1])
        except (ValueError, IndexError):
            return False

    def _calculate_period_range(
        self,
        period_type: BWAPeriod,
        year: int,
        month: Optional[int],
        quarter: Optional[int],
    ) -> Tuple[date, date]:
        """Berechnet Start/Ende eines Zeitraums."""
        if period_type == BWAPeriod.MONTHLY and month:
            start = date(year, month, 1)
            if month == 12:
                end = date(year, 12, 31)
            else:
                end = date(year, month + 1, 1) - timedelta(days=1)
        elif period_type == BWAPeriod.QUARTERLY and quarter:
            start_month = (quarter - 1) * 3 + 1
            start = date(year, start_month, 1)
            end_month = start_month + 2
            if end_month == 12:
                end = date(year, 12, 31)
            else:
                end = date(year, end_month + 1, 1) - timedelta(days=1)
        else:
            start = date(year, 1, 1)
            end = date(year, 12, 31)
        return start, end


def get_bwa_service() -> BWAService:
    """FastAPI Dependency."""
    return BWAService()
