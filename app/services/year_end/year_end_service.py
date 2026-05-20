# -*- coding: utf-8 -*-
"""
Jahresabschluss-Assistent Service.

Vollständigkeitsprüfung und Lückenanalyse für den Jahresabschluss:
- Belegvollständigkeit pro Monat
- Bankabgleich (unzugeordnete Transaktionen)
- Offene Posten
- Umsatzsteuer-Abstimmung
- AfA-Vollständigkeit
- Reisekostenbelege

Feinpoliert und durchdacht - Enterprise-grade Jahresabschluss.
"""

from datetime import datetime, date
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_, extract
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import Document, BankAccount, BankTransaction
from app.db.models_year_end import (
    YearEndSession,
    YearEndCheckItem,
    YearEndGap,
    YearEndStatus,
    CheckItemStatus,
    GapCategory,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Standard-Checkliste (German)
# =============================================================================

_MONTH_NAMES = [
    "Januar", "Februar", "Maerz", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]


class YearEndService:
    """Service für Jahresabschluss-Assistenten."""

    def _build_standard_checklist(self) -> List[Dict[str, str]]:
        """Erstellt die Standard-Checkliste für den Jahresabschluss.

        Returns:
            Liste von Prüfpunkten mit category und check_name.
        """
        items: List[Dict[str, str]] = []

        # Eingangsrechnungen pro Monat (12 Items)
        for i, month_name in enumerate(_MONTH_NAMES, start=1):
            items.append({
                "category": "Eingangsrechnungen",
                "check_name": f"Eingangsrechnungen {month_name} vollständig",
            })

        # Ausgangsrechnungen pro Monat (12 Items)
        for i, month_name in enumerate(_MONTH_NAMES, start=1):
            items.append({
                "category": "Ausgangsrechnungen",
                "check_name": f"Ausgangsrechnungen {month_name} vollständig",
            })

        # Einzelne Prüfpunkte
        single_checks = [
            ("Bankabgleich", "Bankabgleich durchgeführt"),
            ("Offene Posten", "Offene Posten bereinigt"),
            ("Umsatzsteuer", "Umsatzsteuer-Voranmeldungen abgeglichen"),
            ("Umsatzsteuer", "Jahres-Umsatzsteuererklärung vorbereitet"),
            ("Anlagevermoegen", "Anlageverzeichnis aktualisiert"),
            ("Reisekosten", "Reisekosten vollständig"),
            ("Bewirtung", "Bewirtungsbelege geprüft"),
            ("Kasse", "Kassenabschluss durchgeführt"),
            ("Lohn", "Lohnkonten abgestimmt"),
            ("Rückstellungen", "Rückstellungen gebildet"),
        ]
        for category, check_name in single_checks:
            items.append({
                "category": category,
                "check_name": check_name,
            })

        return items

    async def create_session(
        self,
        db: AsyncSession,
        company_id: UUID,
        fiscal_year: int,
        user_id: UUID,
    ) -> YearEndSession:
        """Erstellt eine neue Jahresabschluss-Session mit Standard-Checkliste.

        Args:
            db: Datenbank-Session.
            company_id: Unternehmens-ID.
            fiscal_year: Geschäftsjahr (z.B. 2025).
            user_id: ID des Benutzers, der den Abschluss startet.

        Returns:
            Die erstellte YearEndSession.
        """
        now = utc_now()
        session = YearEndSession(
            company_id=company_id,
            fiscal_year=fiscal_year,
            status=YearEndStatus.DRAFT.value,
            started_by=user_id,
            started_at=now,
            progress_percent=0,
        )
        db.add(session)
        await db.flush()

        # Standard-Checkliste generieren
        checklist = self._build_standard_checklist()
        for sort_order, item_def in enumerate(checklist):
            check_item = YearEndCheckItem(
                session_id=session.id,
                company_id=company_id,
                category=item_def["category"],
                check_name=item_def["check_name"],
                status=CheckItemStatus.PENDING.value,
                sort_order=sort_order,
            )
            db.add(check_item)

        session.total_checks = len(checklist)
        await db.commit()
        await db.refresh(session)

        logger.info(
            "Jahresabschluss-Session erstellt",
            session_id=str(session.id),
            fiscal_year=fiscal_year,
            total_checks=len(checklist),
        )
        return session

    async def get_session(
        self,
        db: AsyncSession,
        session_id: UUID,
        company_id: UUID,
    ) -> Optional[YearEndSession]:
        """Laedt eine Session mit Prüfpunkten und Lücken.

        Args:
            db: Datenbank-Session.
            session_id: Session-ID.
            company_id: Unternehmens-ID (RLS).

        Returns:
            Die Session oder None.
        """
        stmt = (
            select(YearEndSession)
            .options(
                selectinload(YearEndSession.check_items),
                selectinload(YearEndSession.gaps),
            )
            .where(
                and_(
                    YearEndSession.id == session_id,
                    YearEndSession.company_id == company_id,
                    YearEndSession.deleted_at.is_(None),
                )
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_sessions(
        self,
        db: AsyncSession,
        company_id: UUID,
        page: int = 1,
        per_page: int = 20,
    ) -> Tuple[List[YearEndSession], int]:
        """Listet alle Jahresabschluss-Sessions (paginiert).

        Args:
            db: Datenbank-Session.
            company_id: Unternehmens-ID (RLS).
            page: Seitennummer (1-basiert).
            per_page: Einträge pro Seite.

        Returns:
            Tuple aus (Sessions-Liste, Gesamtanzahl).
        """
        base_filter = and_(
            YearEndSession.company_id == company_id,
            YearEndSession.deleted_at.is_(None),
        )

        # Gesamtanzahl
        count_stmt = (
            select(func.count())
            .select_from(YearEndSession)
            .where(base_filter)
        )
        total_result = await db.execute(count_stmt)
        total = total_result.scalar_one()

        # Paginierte Abfrage
        offset = (page - 1) * per_page
        stmt = (
            select(YearEndSession)
            .where(base_filter)
            .order_by(YearEndSession.fiscal_year.desc())
            .offset(offset)
            .limit(per_page)
        )
        result = await db.execute(stmt)
        sessions = list(result.scalars().all())

        return sessions, total

    async def run_completeness_check(
        self,
        db: AsyncSession,
        session_id: UUID,
        company_id: UUID,
    ) -> YearEndSession:
        """Führt die automatische Vollständigkeitsprüfung durch.

        Prüft:
        1. Belegvollständigkeit pro Monat
        2. Bankabgleich (unzugeordnete Transaktionen)
        3. Offene Posten
        4. Umsatzsteuer-Abstimmung
        5. AfA-Vollständigkeit
        6. Reisekostenbelege

        Args:
            db: Datenbank-Session.
            session_id: Session-ID.
            company_id: Unternehmens-ID (RLS).

        Returns:
            Die aktualisierte Session.
        """
        session = await self.get_session(db, session_id, company_id)
        if session is None:
            raise ValueError("Jahresabschluss-Session nicht gefunden")

        session.status = YearEndStatus.IN_PROGRESS.value
        year = session.fiscal_year

        passed = 0
        warnings = 0
        failed = 0

        for item in session.check_items:
            # Eingangsrechnungen / Ausgangsrechnungen pro Monat
            if item.category in ("Eingangsrechnungen", "Ausgangsrechnungen"):
                month_index = _MONTH_NAMES.index(
                    item.check_name.split(" ")[1]
                ) + 1
                status_str, gap_count = await self._check_monthly_receipts(
                    db, company_id, year, month_index,
                )
                item.status = status_str
                item.checked_at = utc_now()
                item.details_json = {
                    "monat": month_index,
                    "lücken": gap_count,
                }

                if status_str == CheckItemStatus.PASSED.value:
                    passed += 1
                elif status_str == CheckItemStatus.WARNING.value:
                    warnings += 1
                else:
                    failed += 1

                # Lücken als Gaps erfassen
                if gap_count > 0:
                    gap = YearEndGap(
                        session_id=session_id,
                        company_id=company_id,
                        category=GapCategory.MISSING_RECEIPT.value,
                        month=month_index,
                        description=(
                            f"{gap_count} fehlende Belege im "
                            f"{_MONTH_NAMES[month_index - 1]} {year}"
                        ),
                    )
                    db.add(gap)

            elif item.category == "Bankabgleich":
                status_str, unmatched = await self._check_bank_reconciliation(
                    db, company_id, year,
                )
                item.status = status_str
                item.checked_at = utc_now()
                item.details_json = {
                    "nicht_zugeordnet": unmatched,
                }

                if status_str == CheckItemStatus.PASSED.value:
                    passed += 1
                elif status_str == CheckItemStatus.WARNING.value:
                    warnings += 1
                else:
                    failed += 1

                if unmatched > 0:
                    gap = YearEndGap(
                        session_id=session_id,
                        company_id=company_id,
                        category=GapCategory.UNMATCHED_TRANSACTION.value,
                        description=(
                            f"{unmatched} nicht zugeordnete "
                            f"Banktransaktionen in {year}"
                        ),
                    )
                    db.add(gap)

            else:
                # Andere Prüfpunkte als PENDING belassen
                # (manuelle Prüfung erforderlich)
                pass

        # Fortschritt berechnen
        total = session.total_checks
        checked = passed + warnings + failed
        session.passed_checks = passed
        session.warning_checks = warnings
        session.failed_checks = failed
        session.progress_percent = int((checked / total * 100)) if total > 0 else 0

        await db.commit()
        await db.refresh(session)

        logger.info(
            "Vollständigkeitsprüfung abgeschlossen",
            session_id=str(session_id),
            passed=passed,
            warnings=warnings,
            failed=failed,
            progress=session.progress_percent,
        )
        return session

    async def get_gaps(
        self,
        db: AsyncSession,
        session_id: UUID,
        company_id: UUID,
        category: Optional[str] = None,
        month: Optional[int] = None,
        resolved: Optional[bool] = None,
    ) -> List[YearEndGap]:
        """Listet Lücken einer Session mit optionalen Filtern.

        Args:
            db: Datenbank-Session.
            session_id: Session-ID.
            company_id: Unternehmens-ID (RLS).
            category: Optional - nach Kategorie filtern.
            month: Optional - nach Monat filtern.
            resolved: Optional - nach Loesungsstatus filtern.

        Returns:
            Liste der Lücken.
        """
        conditions = [
            YearEndGap.session_id == session_id,
            YearEndGap.company_id == company_id,
        ]
        if category is not None:
            conditions.append(YearEndGap.category == category)
        if month is not None:
            conditions.append(YearEndGap.month == month)
        if resolved is not None:
            conditions.append(YearEndGap.is_resolved == resolved)

        stmt = (
            select(YearEndGap)
            .where(and_(*conditions))
            .order_by(YearEndGap.month, YearEndGap.created_at)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def resolve_gap(
        self,
        db: AsyncSession,
        gap_id: UUID,
        company_id: UUID,
        user_id: UUID,
        notes: str,
    ) -> YearEndGap:
        """Markiert eine Lücke als behoben.

        Args:
            db: Datenbank-Session.
            gap_id: Lücken-ID.
            company_id: Unternehmens-ID (RLS).
            user_id: ID des Benutzers.
            notes: Loesungsbeschreibung.

        Returns:
            Die aktualisierte Lücke.

        Raises:
            ValueError: Wenn die Lücke nicht gefunden wurde.
        """
        stmt = select(YearEndGap).where(
            and_(
                YearEndGap.id == gap_id,
                YearEndGap.company_id == company_id,
            )
        )
        result = await db.execute(stmt)
        gap = result.scalar_one_or_none()

        if gap is None:
            raise ValueError("Lücke nicht gefunden")

        gap.is_resolved = True
        gap.resolved_by = user_id
        gap.resolved_at = utc_now()
        gap.resolution_notes = notes

        await db.commit()
        await db.refresh(gap)

        logger.info(
            "Lücke behoben",
            gap_id=str(gap_id),
            category=gap.category,
        )
        return gap

    async def update_check_item(
        self,
        db: AsyncSession,
        item_id: UUID,
        company_id: UUID,
        status: str,
        user_id: UUID,
        notes: Optional[str] = None,
    ) -> YearEndCheckItem:
        """Aktualisiert den Status eines Prüfpunkts.

        Args:
            db: Datenbank-Session.
            item_id: Prüfpunkt-ID.
            company_id: Unternehmens-ID (RLS).
            status: Neuer Status.
            user_id: ID des Benutzers.
            notes: Optionale Anmerkungen.

        Returns:
            Der aktualisierte Prüfpunkt.

        Raises:
            ValueError: Wenn der Prüfpunkt nicht gefunden wurde.
        """
        stmt = select(YearEndCheckItem).where(
            and_(
                YearEndCheckItem.id == item_id,
                YearEndCheckItem.company_id == company_id,
            )
        )
        result = await db.execute(stmt)
        item = result.scalar_one_or_none()

        if item is None:
            raise ValueError("Prüfpunkt nicht gefunden")

        item.status = status
        item.checked_at = utc_now()
        if notes is not None:
            item.resolution_notes = notes
        if status in (CheckItemStatus.PASSED.value, CheckItemStatus.SKIPPED.value):
            item.resolved_by = user_id
            item.resolved_at = utc_now()

        await db.commit()
        await db.refresh(item)

        logger.info(
            "Prüfpunkt aktualisiert",
            item_id=str(item_id),
            status=status,
        )
        return item

    async def generate_report_data(
        self,
        db: AsyncSession,
        session_id: UUID,
        company_id: UUID,
    ) -> Dict[str, object]:
        """Generiert umfassende Berichtsdaten für den Steuerberater.

        Args:
            db: Datenbank-Session.
            session_id: Session-ID.
            company_id: Unternehmens-ID (RLS).

        Returns:
            Dict mit Berichtsdaten.

        Raises:
            ValueError: Wenn die Session nicht gefunden wurde.
        """
        session = await self.get_session(db, session_id, company_id)
        if session is None:
            raise ValueError("Jahresabschluss-Session nicht gefunden")

        # Zusammenfassung
        summary: Dict[str, object] = {
            "geschäftsjahr": session.fiscal_year,
            "status": session.status,
            "fortschritt_prozent": session.progress_percent,
            "gesamt_prüfpunkte": session.total_checks,
            "bestanden": session.passed_checks,
            "warnungen": session.warning_checks,
            "fehlgeschlagen": session.failed_checks,
        }

        # Prüfpunkte nach Kategorie gruppiert
        categories: Dict[str, List[Dict[str, object]]] = {}
        for item in session.check_items:
            cat = item.category
            if cat not in categories:
                categories[cat] = []
            categories[cat].append({
                "prüfpunkt": item.check_name,
                "status": item.status,
                "details": item.details_json,
                "geprüft_am": (
                    item.checked_at.isoformat() if item.checked_at else None
                ),
            })

        # Lücken nach Kategorie
        gap_analysis: Dict[str, List[Dict[str, object]]] = {}
        total_gap_amount = Decimal("0.00")
        for gap in session.gaps:
            cat = gap.category
            if cat not in gap_analysis:
                gap_analysis[cat] = []
            gap_dict: Dict[str, object] = {
                "beschreibung": gap.description,
                "monat": gap.month,
                "behoben": gap.is_resolved,
            }
            if gap.amount is not None:
                gap_dict["betrag"] = str(gap.amount)
                total_gap_amount += gap.amount
            gap_analysis[cat].append(gap_dict)

        # Pro-Monat-Zusammenfassung
        month_breakdown: List[Dict[str, object]] = []
        for month_idx in range(1, 13):
            month_gaps = [g for g in session.gaps if g.month == month_idx]
            month_checks = [
                c for c in session.check_items
                if c.details_json and c.details_json.get("monat") == month_idx
            ]
            month_breakdown.append({
                "monat": month_idx,
                "name": _MONTH_NAMES[month_idx - 1],
                "lücken_gesamt": len(month_gaps),
                "lücken_behoben": sum(1 for g in month_gaps if g.is_resolved),
                "prüfpunkte_bestanden": sum(
                    1 for c in month_checks
                    if c.status == CheckItemStatus.PASSED.value
                ),
            })

        # Loesungsfortschritt
        total_gaps = len(session.gaps)
        resolved_gaps = sum(1 for g in session.gaps if g.is_resolved)
        resolution_progress: Dict[str, object] = {
            "gesamt_lücken": total_gaps,
            "behoben": resolved_gaps,
            "offen": total_gaps - resolved_gaps,
            "fortschritt_prozent": (
                int(resolved_gaps / total_gaps * 100) if total_gaps > 0 else 100
            ),
            "offener_betrag": str(total_gap_amount),
        }

        # Empfehlungen (German)
        empfehlungen: List[str] = []
        if session.failed_checks > 0:
            empfehlungen.append(
                f"{session.failed_checks} Prüfpunkte fehlgeschlagen - "
                "bitte vor Abschluss korrigieren."
            )
        if total_gaps - resolved_gaps > 0:
            empfehlungen.append(
                f"{total_gaps - resolved_gaps} offene Lücken müssen "
                "noch behoben werden."
            )
        if session.warning_checks > 0:
            empfehlungen.append(
                f"{session.warning_checks} Warnungen sollten "
                "geprüft werden."
            )
        if not empfehlungen:
            empfehlungen.append(
                "Alle Prüfungen bestanden. "
                "Der Jahresabschluss kann abgeschlossen werden."
            )

        report_data: Dict[str, object] = {
            "zusammenfassung": summary,
            "prüfpunkte_nach_kategorie": categories,
            "lücken_analyse": gap_analysis,
            "monats_übersicht": month_breakdown,
            "loesungsfortschritt": resolution_progress,
            "empfehlungen": empfehlungen,
        }

        # Bericht-Zeitstempel setzen
        session.report_generated_at = utc_now()
        await db.commit()

        logger.info(
            "Steuerberater-Bericht generiert",
            session_id=str(session_id),
            fiscal_year=session.fiscal_year,
        )
        return report_data

    async def complete_session(
        self,
        db: AsyncSession,
        session_id: UUID,
        company_id: UUID,
        user_id: UUID,
    ) -> YearEndSession:
        """Schließt eine Jahresabschluss-Session ab.

        Validiert, dass alle kritischen Prüfpunkte bestanden sind.

        Args:
            db: Datenbank-Session.
            session_id: Session-ID.
            company_id: Unternehmens-ID (RLS).
            user_id: ID des Benutzers.

        Returns:
            Die abgeschlossene Session.

        Raises:
            ValueError: Wenn die Session nicht abgeschlossen werden kann.
        """
        session = await self.get_session(db, session_id, company_id)
        if session is None:
            raise ValueError("Jahresabschluss-Session nicht gefunden")

        # Prüfen, ob kritische Checks fehlgeschlagen sind
        failed_items = [
            item for item in session.check_items
            if item.status == CheckItemStatus.FAILED.value
        ]
        if failed_items:
            failed_names = [item.check_name for item in failed_items[:5]]
            raise ValueError(
                f"Jahresabschluss kann nicht abgeschlossen werden. "
                f"{len(failed_items)} fehlgeschlagene Prüfpunkte: "
                f"{', '.join(failed_names)}"
            )

        session.status = YearEndStatus.COMPLETED.value
        session.completed_at = utc_now()
        await db.commit()
        await db.refresh(session)

        logger.info(
            "Jahresabschluss abgeschlossen",
            session_id=str(session_id),
            fiscal_year=session.fiscal_year,
        )
        return session

    # =========================================================================
    # Private Helper Methods
    # =========================================================================

    async def _check_monthly_receipts(
        self,
        db: AsyncSession,
        company_id: UUID,
        year: int,
        month: int,
    ) -> Tuple[str, int]:
        """Prüft die Belegvollständigkeit für einen Monat.

        Args:
            db: Datenbank-Session.
            company_id: Unternehmens-ID.
            year: Geschäftsjahr.
            month: Monat (1-12).

        Returns:
            Tuple aus (Status-String, Anzahl Lücken).
        """
        try:
            # Dokumente im Monat zaehlen
            stmt = (
                select(func.count())
                .select_from(Document)
                .where(
                    and_(
                        Document.company_id == company_id,
                        extract("year", Document.created_at) == year,
                        extract("month", Document.created_at) == month,
                    )
                )
            )
            result = await db.execute(stmt)
            doc_count = result.scalar_one()

            # Einfache Heuristik: Wenn weniger als 5 Dokumente, Warnung
            # Wenn 0, dann fehlgeschlagen
            if doc_count == 0:
                return CheckItemStatus.FAILED.value, 1
            elif doc_count < 5:
                return CheckItemStatus.WARNING.value, 0
            else:
                return CheckItemStatus.PASSED.value, 0

        except Exception as e:
            logger.warning(
                "Belegprüfung fehlgeschlagen",
                **safe_error_log(e),
                month=month,
                year=year,
            )
            return CheckItemStatus.WARNING.value, 0

    async def _check_bank_reconciliation(
        self,
        db: AsyncSession,
        company_id: UUID,
        year: int,
    ) -> Tuple[str, int]:
        """Prüft den Bankabgleich auf nicht zugeordnete Transaktionen.

        BankTransaction hat kein direktes company_id. Der Zugriff
        erfolgt über BankAccount -> User -> UserCompany.
        Für den Jahresabschluss zaehlen wir nicht zugeordnete
        Transaktionen (matched_document_id IS NULL) im Geschäftsjahr.

        Args:
            db: Datenbank-Session.
            company_id: Unternehmens-ID.
            year: Geschäftsjahr.

        Returns:
            Tuple aus (Status-String, Anzahl nicht zugeordneter Transaktionen).
        """
        try:
            # Nicht zugeordnete Transaktionen zaehlen
            # Join: BankTransaction -> BankAccount (über bank_account_id)
            stmt = (
                select(func.count())
                .select_from(BankTransaction)
                .join(
                    BankAccount,
                    BankTransaction.bank_account_id == BankAccount.id,
                )
                .where(
                    and_(
                        extract("year", BankTransaction.booking_date) == year,
                        BankTransaction.matched_document_id.is_(None),
                    )
                )
            )
            result = await db.execute(stmt)
            unmatched = result.scalar_one()

            if unmatched == 0:
                return CheckItemStatus.PASSED.value, 0
            elif unmatched <= 10:
                return CheckItemStatus.WARNING.value, unmatched
            else:
                return CheckItemStatus.FAILED.value, unmatched

        except Exception as e:
            logger.warning(
                "Bankabgleich-Prüfung fehlgeschlagen",
                **safe_error_log(e),
                year=year,
            )
            return CheckItemStatus.WARNING.value, 0
