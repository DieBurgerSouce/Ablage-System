"""
Expense Service - Spesenabrechnung.

Verwaltet Spesenabrechnungen mit:
- CRUD fuer Reports und Items
- Workflow (Draft -> Submitted -> Approved -> Paid)
- Bewirtungskosten-Validierung
- Kilometergeld- und Verpflegungspauschalen-Berechnung
- Integration mit Kassenbuch bei Auszahlung

Alle deutschen steuerlichen Regelungen beachtet.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any
from uuid import UUID

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import structlog

from app.db.models import (
    ExpenseReport,
    ExpenseItem,
    CashEntry,
    CashRegister,
    User,
)
from app.db.schemas import (
    ExpenseReportCreate,
    ExpenseReportUpdate,
    ExpenseItemCreate,
    ExpenseItemUpdate,
    ExpenseReportStatus,
    ExpenseType,
    PerDiemCalculation,
    MileageCalculation,
)

logger = structlog.get_logger(__name__)


# ==================== Konstanten fuer deutsche Steuern ====================

# Kilometerpauschale (§ 9 Abs. 1 Nr. 4 EStG)
MILEAGE_RATE_PER_KM = Decimal("0.30")  # EUR pro km

# Verpflegungspauschalen 2024 (§ 9 Abs. 4a EStG)
# Inland
PER_DIEM_FULL_DAY_DE = Decimal("28.00")  # Ab 24 Stunden
PER_DIEM_PARTIAL_DAY_DE = Decimal("14.00")  # 8-24 Stunden
PER_DIEM_ARRIVAL_DEPARTURE_DE = Decimal("14.00")  # An-/Abreisetag

# Kuerzung bei Mahlzeitengestellung
MEAL_REDUCTION_BREAKFAST = Decimal("0.20")  # 20% des Tagessatzes
MEAL_REDUCTION_LUNCH = Decimal("0.40")  # 40%
MEAL_REDUCTION_DINNER = Decimal("0.40")  # 40%

# Bewirtungskosten
ENTERTAINMENT_DEDUCTIBLE_RATE = Decimal("0.70")  # 70% absetzbar
ENTERTAINMENT_NON_DEDUCTIBLE_RATE = Decimal("0.30")  # 30% nicht absetzbar


class ExpenseService:
    """Service fuer Spesenabrechnung."""

    # ==================== Report CRUD ====================

    async def _get_next_report_number(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> str:
        """Generiert die nächste Report-Nummer für eine Firma.

        Format: SPE-YYYY-NNNNNN (z.B. SPE-2025-000001)
        """
        year = datetime.now().year
        prefix = f"SPE-{year}-"

        # Finde die höchste bestehende Nummer für dieses Jahr
        result = await db.execute(
            select(func.max(ExpenseReport.report_number))
            .where(
                and_(
                    ExpenseReport.company_id == company_id,
                    ExpenseReport.report_number.like(f"{prefix}%")
                )
            )
        )
        max_number = result.scalar()

        if max_number:
            # Extrahiere die Nummer und inkrementiere
            try:
                current_num = int(max_number.replace(prefix, ""))
                next_num = current_num + 1
            except (ValueError, AttributeError):
                next_num = 1
        else:
            next_num = 1

        return f"{prefix}{next_num:06d}"

    async def create_report(
        self,
        db: AsyncSession,
        company_id: UUID,
        data: ExpenseReportCreate,
        user_id: UUID,
    ) -> ExpenseReport:
        """Erstellt eine neue Spesenabrechnung.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            data: Spesenabrechnung-Daten
            user_id: Ersteller-ID

        Returns:
            Erstellte Spesenabrechnung
        """
        # Generiere Report-Nummer
        report_number = await self._get_next_report_number(db, company_id)

        report = ExpenseReport(
            company_id=company_id,
            report_number=report_number,
            title=data.title,
            description=data.description,
            status="draft",
            employee_id=data.employee_id or user_id,
            submitted_by_id=user_id,
            period_start=data.period_start,
            period_end=data.period_end,
            total_amount=Decimal("0.00"),
        )
        db.add(report)
        await db.flush()
        await db.refresh(report)

        logger.info(
            "expense_report_created",
            report_id=str(report.id),
            company_id=str(company_id),
            user_id=str(user_id),
        )

        return report

    async def get_report(
        self,
        db: AsyncSession,
        report_id: UUID,
        company_id: UUID,
    ) -> Optional[ExpenseReport]:
        """Holt eine Spesenabrechnung.

        Args:
            db: Datenbank-Session
            report_id: Report-ID
            company_id: Firmen-ID

        Returns:
            Spesenabrechnung oder None
        """
        result = await db.execute(
            select(ExpenseReport)
            .options(selectinload(ExpenseReport.items))
            .where(ExpenseReport.id == report_id)
            .where(ExpenseReport.company_id == company_id)
            .where(ExpenseReport.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_reports(
        self,
        db: AsyncSession,
        company_id: UUID,
        employee_id: Optional[UUID] = None,
        status: Optional[ExpenseReportStatus] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[ExpenseReport], int]:
        """Listet Spesenabrechnungen.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            employee_id: Optional Filter nach Mitarbeiter
            status: Optional Filter nach Status
            start_date: Optional Filter nach Periode
            end_date: Optional Filter nach Periode
            skip: Offset
            limit: Limit

        Returns:
            Tuple aus Liste und Gesamtanzahl
        """
        query = (
            select(ExpenseReport)
            .options(selectinload(ExpenseReport.items))
            .where(ExpenseReport.company_id == company_id)
            .where(ExpenseReport.deleted_at.is_(None))
        )

        if employee_id:
            query = query.where(ExpenseReport.employee_id == employee_id)

        if status:
            query = query.where(ExpenseReport.status == status.value)

        if start_date:
            query = query.where(ExpenseReport.period_end >= start_date)

        if end_date:
            query = query.where(ExpenseReport.period_start <= end_date)

        # Count
        count_query = (
            select(func.count())
            .select_from(ExpenseReport)
            .where(ExpenseReport.company_id == company_id)
            .where(ExpenseReport.deleted_at.is_(None))
        )
        if employee_id:
            count_query = count_query.where(ExpenseReport.employee_id == employee_id)
        if status:
            count_query = count_query.where(ExpenseReport.status == status.value)
        if start_date:
            count_query = count_query.where(ExpenseReport.period_end >= start_date)
        if end_date:
            count_query = count_query.where(ExpenseReport.period_start <= end_date)

        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        # Fetch
        query = query.order_by(ExpenseReport.created_at.desc()).offset(skip).limit(limit)
        result = await db.execute(query)
        reports = result.scalars().all()

        return list(reports), total

    async def update_report(
        self,
        db: AsyncSession,
        report_id: UUID,
        company_id: UUID,
        data: ExpenseReportUpdate,
    ) -> Optional[ExpenseReport]:
        """Aktualisiert eine Spesenabrechnung.

        Args:
            db: Datenbank-Session
            report_id: Report-ID
            company_id: Firmen-ID
            data: Update-Daten

        Returns:
            Aktualisierte Spesenabrechnung oder None
        """
        report = await self.get_report(db, report_id, company_id)
        if not report:
            return None

        # Nur Entwuerfe koennen bearbeitet werden
        if report.status != "draft":
            raise ValueError(
                f"Nur Entwuerfe koennen bearbeitet werden. "
                f"Aktueller Status: {report.status}"
            )

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(report, field, value)

        report.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(report)

        return report

    async def delete_report(
        self,
        db: AsyncSession,
        report_id: UUID,
        company_id: UUID,
    ) -> bool:
        """Loescht eine Spesenabrechnung (Soft-Delete).

        Args:
            db: Datenbank-Session
            report_id: Report-ID
            company_id: Firmen-ID

        Returns:
            True wenn erfolgreich
        """
        report = await self.get_report(db, report_id, company_id)
        if not report:
            return False

        # Nur Entwuerfe koennen geloescht werden
        if report.status != "draft":
            raise ValueError(
                "Nur Entwuerfe koennen geloescht werden. "
                "Eingereichte Abrechnungen muessen abgelehnt werden."
            )

        report.deleted_at = datetime.utcnow()
        await db.commit()

        logger.info(
            "expense_report_deleted",
            report_id=str(report_id),
            company_id=str(company_id),
        )

        return True

    # ==================== Item CRUD ====================

    async def add_item(
        self,
        db: AsyncSession,
        report_id: UUID,
        company_id: UUID,
        data: ExpenseItemCreate,
        user_id: UUID,
    ) -> ExpenseItem:
        """Fuegt eine Position zur Spesenabrechnung hinzu.

        Args:
            db: Datenbank-Session
            report_id: Report-ID
            company_id: Firmen-ID
            data: Position-Daten
            user_id: Ersteller-ID

        Returns:
            Erstellte Position
        """
        report = await self.get_report(db, report_id, company_id)
        if not report:
            raise ValueError("Spesenabrechnung nicht gefunden.")

        if report.status != "draft":
            raise ValueError("Positionen koennen nur zu Entwuerfen hinzugefuegt werden.")

        # Validiere Bewirtungskosten
        if data.expense_type == ExpenseType.RECEIPT and data.is_entertainment:
            self._validate_entertainment_data(data.entertainment_data)

        # Berechne abzugsfaehigen Betrag
        deductible_amount = data.amount
        if data.is_entertainment:
            deductible_amount = data.amount * ENTERTAINMENT_DEDUCTIBLE_RATE

        # Berechne Kilometergeld falls applicable
        if data.expense_type == ExpenseType.MILEAGE and data.mileage_km:
            data.amount = data.mileage_km * MILEAGE_RATE_PER_KM
            deductible_amount = data.amount

        # Berechne Verpflegungspauschale
        if data.expense_type == ExpenseType.PER_DIEM:
            calculation = self.calculate_per_diem(
                travel_start=datetime.combine(data.expense_date, datetime.min.time()),
                travel_end=datetime.combine(data.expense_date, datetime.max.time()),
                meals_provided=data.per_diem_meals_provided or {},
            )
            data.amount = calculation.total_amount
            deductible_amount = data.amount

        item = ExpenseItem(
            report_id=report_id,
            expense_date=data.expense_date,
            expense_type=data.expense_type.value,
            description=data.description,
            amount=data.amount,
            currency=data.currency or "EUR",
            exchange_rate=data.exchange_rate or Decimal("1.00"),
            amount_eur=data.amount * (data.exchange_rate or Decimal("1.00")),
            tax_rate=data.tax_rate,
            net_amount=data.net_amount,
            tax_amount=data.tax_amount,
            category_id=data.category_id,
            receipt_number=data.receipt_number,
            receipt_document_id=data.receipt_document_id,
            vendor=data.vendor,
            is_entertainment=data.is_entertainment or False,
            entertainment_data=data.entertainment_data,
            mileage_km=data.mileage_km,
            mileage_from=data.mileage_from,
            mileage_to=data.mileage_to,
            mileage_purpose=data.mileage_purpose,
            per_diem_hours=data.per_diem_hours,
            per_diem_meals_provided=data.per_diem_meals_provided,
            per_diem_country=data.per_diem_country or "DE",
            notes=data.notes,
            is_approved=False,
            approved_amount=Decimal("0.00"),
            deductible_amount=deductible_amount,
        )
        db.add(item)
        await db.flush()

        # Update Report-Summen
        await self._update_report_totals(db, report)

        await db.commit()
        await db.refresh(item)

        return item

    async def update_item(
        self,
        db: AsyncSession,
        item_id: UUID,
        company_id: UUID,
        data: ExpenseItemUpdate,
        employee_id: Optional[UUID] = None,  # SECURITY FIX 26-16: IDOR Protection
    ) -> Optional[ExpenseItem]:
        """Aktualisiert eine Position.

        Args:
            db: Datenbank-Session
            item_id: Item-ID
            company_id: Firmen-ID
            data: Update-Daten
            employee_id: Optional Employee-ID fuer IDOR-Schutz

        Returns:
            Aktualisierte Position oder None
        """
        # SECURITY FIX 26-14: with_for_update() gegen TOCTOU Race Condition
        query = (
            select(ExpenseItem)
            .join(ExpenseReport)
            .where(ExpenseItem.id == item_id)
            .where(ExpenseReport.company_id == company_id)
            .where(ExpenseReport.deleted_at.is_(None))
            .with_for_update()  # SECURITY: Row Lock
        )
        # SECURITY FIX 26-16: IDOR Protection - Employee kann nur eigene Items aendern
        if employee_id:
            query = query.where(ExpenseReport.employee_id == employee_id)

        result = await db.execute(query)
        item = result.scalar_one_or_none()

        if not item:
            return None

        # Lade Report
        report = await self.get_report(db, item.report_id, company_id)
        if report and report.status != "draft":
            raise ValueError("Positionen koennen nur in Entwuerfen bearbeitet werden.")

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(item, field, value)

        # Recalc deductible
        if item.is_entertainment:
            item.deductible_amount = item.amount * ENTERTAINMENT_DEDUCTIBLE_RATE
        else:
            item.deductible_amount = item.amount

        item.updated_at = datetime.utcnow()

        # Update Report-Summen
        if report:
            await self._update_report_totals(db, report)

        await db.commit()
        await db.refresh(item)

        return item

    async def delete_item(
        self,
        db: AsyncSession,
        item_id: UUID,
        company_id: UUID,
    ) -> bool:
        """Loescht eine Position.

        Args:
            db: Datenbank-Session
            item_id: Item-ID
            company_id: Firmen-ID

        Returns:
            True wenn erfolgreich
        """
        result = await db.execute(
            select(ExpenseItem)
            .join(ExpenseReport)
            .where(ExpenseItem.id == item_id)
            .where(ExpenseReport.company_id == company_id)
            .where(ExpenseReport.deleted_at.is_(None))
        )
        item = result.scalar_one_or_none()

        if not item:
            return False

        # Lade Report
        report = await self.get_report(db, item.report_id, company_id)
        if report and report.status != "draft":
            raise ValueError("Positionen koennen nur aus Entwuerfen geloescht werden.")

        await db.delete(item)

        # Update Report-Summen
        if report:
            await self._update_report_totals(db, report)

        await db.commit()

        return True

    # ==================== Workflow ====================

    async def submit_report(
        self,
        db: AsyncSession,
        report_id: UUID,
        company_id: UUID,
        user_id: UUID,
    ) -> ExpenseReport:
        """Reicht eine Spesenabrechnung zur Pruefung ein.

        Args:
            db: Datenbank-Session
            report_id: Report-ID
            company_id: Firmen-ID
            user_id: Einreicher-ID

        Returns:
            Eingereichte Spesenabrechnung
        """
        report = await self.get_report(db, report_id, company_id)
        if not report:
            raise ValueError("Spesenabrechnung nicht gefunden.")

        if report.status != "draft":
            raise ValueError(f"Report ist nicht im Entwurf-Status: {report.status}")

        # Pruefe ob Positionen vorhanden
        if not report.items or len(report.items) == 0:
            raise ValueError("Spesenabrechnung hat keine Positionen.")

        # Validiere alle Positionen
        for item in report.items:
            if item.is_entertainment and not item.entertainment_data:
                raise ValueError(
                    f"Position '{item.description}' ist Bewirtung, "
                    "aber Bewirtungsdaten fehlen."
                )

        report.status = "submitted"
        report.submitted_at = datetime.utcnow()
        report.submitted_by_id = user_id

        await db.commit()
        await db.refresh(report)

        logger.info(
            "expense_report_submitted",
            report_id=str(report_id),
            user_id=str(user_id),
        )

        return report

    async def approve_report(
        self,
        db: AsyncSession,
        report_id: UUID,
        company_id: UUID,
        user_id: UUID,
        approved_amount: Optional[Decimal] = None,
        notes: Optional[str] = None,
    ) -> ExpenseReport:
        """Genehmigt eine Spesenabrechnung.

        Args:
            db: Datenbank-Session
            report_id: Report-ID
            company_id: Firmen-ID
            user_id: Genehmiger-ID
            approved_amount: Optional geaenderter Betrag
            notes: Optional Notizen

        Returns:
            Genehmigte Spesenabrechnung
        """
        report = await self.get_report(db, report_id, company_id)
        if not report:
            raise ValueError("Spesenabrechnung nicht gefunden.")

        if report.status not in ["submitted", "in_review"]:
            raise ValueError(f"Report kann nicht genehmigt werden: {report.status}")

        # Setze genehmigten Betrag
        if approved_amount is not None:
            report.approved_amount = approved_amount
        else:
            report.approved_amount = report.total_amount

        # Markiere alle Items als approved
        for item in report.items:
            item.is_approved = True
            item.approved_amount = item.amount

        report.status = "approved"
        report.approved_at = datetime.utcnow()
        report.approved_by_id = user_id
        if notes:
            report.rejection_reason = None  # Clear any previous rejection

        await db.commit()
        await db.refresh(report)

        logger.info(
            "expense_report_approved",
            report_id=str(report_id),
            approved_amount=str(report.approved_amount),
            user_id=str(user_id),
        )

        return report

    async def reject_report(
        self,
        db: AsyncSession,
        report_id: UUID,
        company_id: UUID,
        user_id: UUID,
        reason: str,
    ) -> ExpenseReport:
        """Lehnt eine Spesenabrechnung ab.

        Args:
            db: Datenbank-Session
            report_id: Report-ID
            company_id: Firmen-ID
            user_id: Ablehnender
            reason: Ablehnungsgrund

        Returns:
            Abgelehnte Spesenabrechnung
        """
        report = await self.get_report(db, report_id, company_id)
        if not report:
            raise ValueError("Spesenabrechnung nicht gefunden.")

        if report.status not in ["submitted", "in_review"]:
            raise ValueError(f"Report kann nicht abgelehnt werden: {report.status}")

        report.status = "rejected"
        report.rejected_at = datetime.utcnow()
        report.approved_by_id = user_id  # Wer hat entschieden
        report.rejection_reason = reason

        await db.commit()
        await db.refresh(report)

        logger.info(
            "expense_report_rejected",
            report_id=str(report_id),
            reason=reason,
            user_id=str(user_id),
        )

        return report

    async def mark_as_paid(
        self,
        db: AsyncSession,
        report_id: UUID,
        company_id: UUID,
        user_id: UUID,
        register_id: Optional[UUID] = None,
    ) -> ExpenseReport:
        """Markiert eine Spesenabrechnung als ausgezahlt.

        Args:
            db: Datenbank-Session
            report_id: Report-ID
            company_id: Firmen-ID
            user_id: Auszahlender
            register_id: Optional Kassen-ID fuer Kassenbuchung

        Returns:
            Ausgezahlte Spesenabrechnung
        """
        report = await self.get_report(db, report_id, company_id)
        if not report:
            raise ValueError("Spesenabrechnung nicht gefunden.")

        if report.status != "approved":
            raise ValueError(
                f"Nur genehmigte Abrechnungen koennen ausgezahlt werden: {report.status}"
            )

        report.status = "paid"
        report.paid_at = datetime.utcnow()
        report.paid_amount = report.approved_amount

        # Optional: Kassenbuchung erstellen
        if register_id:
            from app.services.cash_service import CashService
            from app.db.schemas import CashEntryCreate, CashEntryType as CashEntryTypeSchema

            cash_service = CashService()
            entry_data = CashEntryCreate(
                register_id=register_id,
                entry_date=date.today(),
                entry_type=CashEntryTypeSchema.EXPENSE,
                amount=report.approved_amount,
                description=f"Spesenabrechnung: {report.title}",
                counterparty=report.employee.full_name if report.employee else None,
                tax_rate=Decimal("0.00"),  # Spesen meist ohne MwSt
            )

            entry = await cash_service.create_entry(
                db=db,
                company_id=company_id,
                data=entry_data,
                user_id=user_id,
            )
            report.cash_entry_id = entry.id

        await db.commit()
        await db.refresh(report)

        logger.info(
            "expense_report_paid",
            report_id=str(report_id),
            paid_amount=str(report.paid_amount),
            user_id=str(user_id),
        )

        return report

    # ==================== Calculators ====================

    def calculate_per_diem(
        self,
        travel_start: datetime,
        travel_end: datetime,
        meals_provided: Dict[str, bool] = None,
        country: str = "DE",
    ) -> PerDiemCalculation:
        """Berechnet Verpflegungspauschale.

        Args:
            travel_start: Reisebeginn
            travel_end: Reiseende
            meals_provided: Dict mit 'breakfast', 'lunch', 'dinner' -> True/False
            country: Laendercode (nur DE implementiert)

        Returns:
            Berechnung mit Details
        """
        meals_provided = meals_provided or {}

        # Berechne Reisedauer
        duration = travel_end - travel_start
        total_hours = duration.total_seconds() / 3600

        # Bestimme Pauschale basierend auf Dauer
        if total_hours >= 24:
            base_rate = PER_DIEM_FULL_DAY_DE
            rate_type = "full_day"
        elif total_hours >= 8:
            base_rate = PER_DIEM_PARTIAL_DAY_DE
            rate_type = "partial_day"
        else:
            base_rate = Decimal("0.00")
            rate_type = "none"

        # Berechne Kuerzungen
        reduction = Decimal("0.00")
        if meals_provided.get("breakfast"):
            reduction += base_rate * MEAL_REDUCTION_BREAKFAST
        if meals_provided.get("lunch"):
            reduction += base_rate * MEAL_REDUCTION_LUNCH
        if meals_provided.get("dinner"):
            reduction += base_rate * MEAL_REDUCTION_DINNER

        total_amount = max(Decimal("0.00"), base_rate - reduction)

        return PerDiemCalculation(
            travel_start=travel_start,
            travel_end=travel_end,
            total_hours=Decimal(str(round(total_hours, 2))),
            country=country,
            base_rate=base_rate,
            rate_type=rate_type,
            meals_provided=meals_provided,
            meal_reductions=reduction,
            total_amount=total_amount,
        )

    def calculate_mileage(
        self,
        kilometers: Decimal,
        rate_per_km: Optional[Decimal] = None,
    ) -> MileageCalculation:
        """Berechnet Kilometergeld.

        Args:
            kilometers: Gefahrene Kilometer
            rate_per_km: Optional abweichender Satz

        Returns:
            Berechnung mit Details
        """
        rate = rate_per_km or MILEAGE_RATE_PER_KM
        total_amount = kilometers * rate

        return MileageCalculation(
            kilometers=kilometers,
            rate_per_km=rate,
            total_amount=total_amount,
        )

    # ==================== Private Helpers ====================

    def _validate_entertainment_data(self, data: Optional[Dict[str, Any]]) -> None:
        """Validiert Bewirtungsdaten fuer steuerliche Anforderungen.

        Args:
            data: Bewirtungsdaten

        Raises:
            ValueError: Bei ungueltigen Daten
        """
        if not data:
            raise ValueError(
                "Bewirtungskosten erfordern Angaben zu Anlass und Teilnehmern."
            )

        required_fields = ["occasion", "attendees", "business_reason"]
        missing = [f for f in required_fields if not data.get(f)]

        if missing:
            raise ValueError(
                f"Folgende Pflichtangaben fuer Bewirtung fehlen: {', '.join(missing)}"
            )

        # Pruefe Teilnehmer
        attendees = data.get("attendees", [])
        if not isinstance(attendees, list) or len(attendees) < 1:
            raise ValueError(
                "Mindestens ein Teilnehmer muss angegeben werden."
            )

        # Pruefe ob Gastgeber-Unternehmen angegeben
        if not data.get("host_company"):
            raise ValueError(
                "Das bewirtende Unternehmen muss angegeben werden."
            )

    async def _update_report_totals(
        self,
        db: AsyncSession,
        report: ExpenseReport,
    ) -> None:
        """Aktualisiert die Summen einer Spesenabrechnung.

        Args:
            db: Datenbank-Session
            report: Spesenabrechnung
        """
        # SECURITY FIX 26-15: Row Lock fuer Report vor parallelen Updates
        locked_result = await db.execute(
            select(ExpenseReport)
            .where(ExpenseReport.id == report.id)
            .with_for_update()
        )
        locked_report = locked_result.scalar_one_or_none()
        if not locked_report:
            return  # Report wurde geloescht

        # Berechne Summen aus Items
        result = await db.execute(
            select(
                func.coalesce(func.sum(ExpenseItem.amount), Decimal("0.00")),
                func.coalesce(func.sum(ExpenseItem.deductible_amount), Decimal("0.00")),
            )
            .where(ExpenseItem.report_id == report.id)
        )
        row = result.one()

        locked_report.total_amount = row[0]
        # approved_amount wird erst bei Genehmigung gesetzt

        await db.flush()
