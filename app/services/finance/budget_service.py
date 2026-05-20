# -*- coding: utf-8 -*-
"""
BudgetService - Budgetierung & Controlling für Ablage-System.

Implementiert:
- CRUD für Budgets, Budget-Positionen, Kostenstellen
- Automatische Kategorisierung aus OCR-extrahierten Daten
- Soll/Ist-Vergleiche mit Abweichungsanalysen
- Alert-System bei Budget-Überschreitung
- Drill-Down Berichte

Phase 2.1 der Feature-Roadmap (Januar 2026).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

import structlog
from sqlalchemy import select, and_, or_, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from app.core.datetime_utils import utc_now
from app.db.models_budget import (
    Budget,
    BudgetLine,
    BudgetAllocation,
    BudgetAlert,
    BudgetCategory,
    BudgetReport,
    Kostenstelle,
    BudgetPeriodType,
    BudgetStatus,
    BudgetLineStatus,
    AllocationSource,
    AlertSeverity,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# Request/Response Dataclasses
# ============================================================================


@dataclass
class KostenstelleCreateRequest:
    """Request für Kostenstellen-Erstellung."""
    code: str
    name: str
    company_id: uuid.UUID
    description: Optional[str] = None
    parent_id: Optional[uuid.UUID] = None
    responsible_user_id: Optional[uuid.UUID] = None
    category: Optional[str] = None
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None
    tags: List[str] = field(default_factory=list)


@dataclass
class BudgetCreateRequest:
    """Request für Budget-Erstellung."""
    name: str
    company_id: uuid.UUID
    period_type: BudgetPeriodType
    year: int
    start_date: date
    end_date: date
    description: Optional[str] = None
    quarter: Optional[int] = None
    month: Optional[int] = None
    owner_id: Optional[uuid.UUID] = None
    total_planned: Decimal = Decimal("0.00")
    currency: str = "EUR"
    warning_threshold: float = 80.0
    critical_threshold: float = 95.0
    allow_overspend: bool = False
    previous_budget_id: Optional[uuid.UUID] = None


@dataclass
class BudgetLineCreateRequest:
    """Request für Budget-Position-Erstellung."""
    budget_id: uuid.UUID
    name: str
    category: str
    planned_amount: Decimal
    kostenstelle_id: Optional[uuid.UUID] = None
    subcategory: Optional[str] = None
    account_number: Optional[str] = None
    description: Optional[str] = None
    monthly_distribution: Optional[Dict[str, float]] = None
    auto_assign_rules: Optional[List[Dict[str, Any]]] = None


@dataclass
class AllocationCreateRequest:
    """Request für Budget-Zuordnung."""
    budget_id: uuid.UUID
    budget_line_id: uuid.UUID
    amount: Decimal
    booking_date: date
    source: AllocationSource = AllocationSource.MANUAL
    document_id: Optional[uuid.UUID] = None
    invoice_tracking_id: Optional[uuid.UUID] = None
    bank_transaction_id: Optional[uuid.UUID] = None
    kostenstelle_id: Optional[uuid.UUID] = None
    description: Optional[str] = None
    reference: Optional[str] = None
    vendor_name: Optional[str] = None
    tax_amount: Decimal = Decimal("0.00")
    is_committed: bool = False
    created_by_id: Optional[uuid.UUID] = None


@dataclass
class BudgetFilter:
    """Filter für Budget-Abfragen."""
    company_id: uuid.UUID
    year: Optional[int] = None
    quarter: Optional[int] = None
    month: Optional[int] = None
    period_type: Optional[BudgetPeriodType] = None
    status: Optional[BudgetStatus] = None
    kostenstelle_id: Optional[uuid.UUID] = None
    category: Optional[str] = None


@dataclass
class BudgetSummary:
    """Zusammenfassung eines Budgets."""
    budget_id: uuid.UUID
    name: str
    period_type: BudgetPeriodType
    year: int
    quarter: Optional[int]
    month: Optional[int]
    status: BudgetStatus
    total_planned: Decimal
    total_actual: Decimal
    total_committed: Decimal
    total_remaining: Decimal
    utilization_percent: float
    lines_count: int
    lines_over_budget: int
    lines_warning: int
    alerts_count: int
    unacknowledged_alerts: int


@dataclass
class BudgetVarianceReport:
    """Abweichungsbericht."""
    budget_id: uuid.UUID
    period_start: date
    period_end: date
    lines: List[Dict[str, Any]]
    total_variance: Decimal
    total_variance_percent: float
    by_category: Dict[str, Dict[str, Any]]
    by_kostenstelle: Dict[str, Dict[str, Any]]
    recommendations: List[str]
    generated_at: datetime


@dataclass
class CategoryMatchResult:
    """Ergebnis der Kategorie-Erkennung."""
    category: str
    subcategory: Optional[str]
    kostenstelle_code: Optional[str]
    confidence: float
    matched_keywords: List[str]
    matched_patterns: List[str]
    suggested_budget_line_id: Optional[uuid.UUID]


# ============================================================================
# BudgetService Implementation
# ============================================================================


class BudgetService:
    """Service für Budget-Verwaltung und Controlling."""

    def __init__(self):
        self._category_cache: Dict[str, BudgetCategory] = {}
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl = timedelta(minutes=15)

    # ========================================================================
    # Kostenstellen CRUD
    # ========================================================================

    async def create_kostenstelle(
        self,
        db: AsyncSession,
        request: KostenstelleCreateRequest,
    ) -> Kostenstelle:
        """Erstellt eine neue Kostenstelle."""
        # Prüfe auf doppelten Code
        existing = await db.execute(
            select(Kostenstelle).where(
                and_(
                    Kostenstelle.company_id == request.company_id,
                    Kostenstelle.code == request.code,
                )
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Kostenstelle mit Code '{request.code}' existiert bereits")

        # Bestimme Level und Path
        level = 0
        path = request.code
        if request.parent_id:
            parent = await db.get(Kostenstelle, request.parent_id)
            if parent:
                level = parent.level + 1
                path = f"{parent.path}/{request.code}" if parent.path else request.code

        kostenstelle = Kostenstelle(
            code=request.code,
            name=request.name,
            description=request.description,
            company_id=request.company_id,
            parent_id=request.parent_id,
            level=level,
            path=path,
            responsible_user_id=request.responsible_user_id,
            category=request.category,
            valid_from=request.valid_from,
            valid_until=request.valid_until,
            tags=request.tags,
        )

        db.add(kostenstelle)
        await db.commit()
        await db.refresh(kostenstelle)

        logger.info(
            "kostenstelle_created",
            kostenstelle_id=str(kostenstelle.id),
            code=request.code,
            company_id=str(request.company_id),
        )

        return kostenstelle

    async def list_kostenstellen(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        include_inactive: bool = False,
        parent_id: Optional[uuid.UUID] = None,
    ) -> List[Kostenstelle]:
        """Listet alle Kostenstellen einer Firma."""
        query = select(Kostenstelle).where(
            Kostenstelle.company_id == company_id
        )

        if not include_inactive:
            query = query.where(Kostenstelle.is_active == True)

        if parent_id is not None:
            query = query.where(Kostenstelle.parent_id == parent_id)
        else:
            # Nur Root-Kostenstellen
            query = query.where(Kostenstelle.parent_id.is_(None))

        query = query.order_by(Kostenstelle.code)

        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_kostenstelle_tree(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> List[Dict[str, Any]]:
        """Gibt hierarchische Kostenstellenstruktur zurück."""
        kostenstellen = await db.execute(
            select(Kostenstelle)
            .where(
                and_(
                    Kostenstelle.company_id == company_id,
                    Kostenstelle.is_active == True,
                )
            )
            .order_by(Kostenstelle.level, Kostenstelle.code)
        )

        all_ks = list(kostenstellen.scalars().all())
        ks_by_id = {ks.id: ks for ks in all_ks}

        def build_tree(parent_id: Optional[uuid.UUID]) -> List[Dict[str, Any]]:
            children = [
                ks for ks in all_ks
                if ks.parent_id == parent_id
            ]
            return [
                {
                    "id": str(ks.id),
                    "code": ks.code,
                    "name": ks.name,
                    "level": ks.level,
                    "category": ks.category,
                    "children": build_tree(ks.id),
                }
                for ks in children
            ]

        return build_tree(None)

    # ========================================================================
    # Budget CRUD
    # ========================================================================

    async def create_budget(
        self,
        db: AsyncSession,
        request: BudgetCreateRequest,
    ) -> Budget:
        """Erstellt ein neues Budget."""
        budget = Budget(
            name=request.name,
            description=request.description,
            company_id=request.company_id,
            period_type=request.period_type,
            year=request.year,
            quarter=request.quarter,
            month=request.month,
            start_date=request.start_date,
            end_date=request.end_date,
            owner_id=request.owner_id,
            total_planned=request.total_planned,
            total_remaining=request.total_planned,
            currency=request.currency,
            warning_threshold=request.warning_threshold,
            critical_threshold=request.critical_threshold,
            allow_overspend=request.allow_overspend,
            previous_budget_id=request.previous_budget_id,
            status=BudgetStatus.DRAFT,
        )

        db.add(budget)
        await db.commit()
        await db.refresh(budget)

        logger.info(
            "budget_created",
            budget_id=str(budget.id),
            name=request.name,
            year=request.year,
            company_id=str(request.company_id),
        )

        return budget

    async def get_budget(
        self,
        db: AsyncSession,
        budget_id: uuid.UUID,
        include_lines: bool = True,
    ) -> Optional[Budget]:
        """Ruft ein Budget ab."""
        query = select(Budget).where(Budget.id == budget_id)

        if include_lines:
            query = query.options(
                selectinload(Budget.lines).selectinload(BudgetLine.kostenstelle),
                selectinload(Budget.alerts),
            )

        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def list_budgets(
        self,
        db: AsyncSession,
        filter: BudgetFilter,
        page: int = 0,
        page_size: int = 25,
    ) -> Tuple[List[Budget], int]:
        """Listet Budgets mit Filtern."""
        query = select(Budget).where(Budget.company_id == filter.company_id)

        if filter.year:
            query = query.where(Budget.year == filter.year)
        if filter.quarter:
            query = query.where(Budget.quarter == filter.quarter)
        if filter.month:
            query = query.where(Budget.month == filter.month)
        if filter.period_type:
            query = query.where(Budget.period_type == filter.period_type)
        if filter.status:
            query = query.where(Budget.status == filter.status)

        # Count
        count_query = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_query)).scalar() or 0

        # Paginate
        query = (
            query
            .order_by(Budget.year.desc(), Budget.quarter, Budget.month)
            .offset(page * page_size)
            .limit(page_size)
        )

        result = await db.execute(query)
        return list(result.scalars().all()), total

    async def get_budget_summary(
        self,
        db: AsyncSession,
        budget_id: uuid.UUID,
    ) -> Optional[BudgetSummary]:
        """Gibt Zusammenfassung eines Budgets zurück."""
        budget = await self.get_budget(db, budget_id, include_lines=True)
        if not budget:
            return None

        # Zaehle Lines nach Status
        lines_over = sum(1 for l in budget.lines if l.status == BudgetLineStatus.OVER_BUDGET)
        lines_warning = sum(1 for l in budget.lines if l.status == BudgetLineStatus.WARNING)

        # Zaehle Alerts
        alerts_total = len(budget.alerts)
        alerts_unack = sum(1 for a in budget.alerts if not a.is_acknowledged)

        return BudgetSummary(
            budget_id=budget.id,
            name=budget.name,
            period_type=budget.period_type,
            year=budget.year,
            quarter=budget.quarter,
            month=budget.month,
            status=budget.status,
            total_planned=budget.total_planned,
            total_actual=budget.total_actual,
            total_committed=budget.total_committed,
            total_remaining=budget.total_remaining,
            utilization_percent=budget.utilization_percent,
            lines_count=len(budget.lines),
            lines_over_budget=lines_over,
            lines_warning=lines_warning,
            alerts_count=alerts_total,
            unacknowledged_alerts=alerts_unack,
        )

    async def activate_budget(
        self,
        db: AsyncSession,
        budget_id: uuid.UUID,
        approved_by_id: uuid.UUID,
    ) -> Budget:
        """Aktiviert ein Budget (von DRAFT zu ACTIVE)."""
        budget = await db.get(Budget, budget_id)
        if not budget:
            raise ValueError(f"Budget {budget_id} nicht gefunden")

        if budget.status != BudgetStatus.DRAFT:
            raise ValueError(f"Budget kann nur aus Status DRAFT aktiviert werden (aktuell: {budget.status})")

        budget.status = BudgetStatus.ACTIVE
        budget.approved_at = utc_now()
        budget.approved_by_id = approved_by_id

        await db.commit()
        await db.refresh(budget)

        logger.info(
            "budget_activated",
            budget_id=str(budget_id),
            approved_by=str(approved_by_id),
        )

        return budget

    async def close_budget(
        self,
        db: AsyncSession,
        budget_id: uuid.UUID,
    ) -> Budget:
        """Schließt ein Budget ab."""
        budget = await db.get(Budget, budget_id)
        if not budget:
            raise ValueError(f"Budget {budget_id} nicht gefunden")

        budget.status = BudgetStatus.CLOSED

        await db.commit()
        await db.refresh(budget)

        logger.info("budget_closed", budget_id=str(budget_id))

        return budget

    # ========================================================================
    # Budget Lines CRUD
    # ========================================================================

    async def create_budget_line(
        self,
        db: AsyncSession,
        request: BudgetLineCreateRequest,
    ) -> BudgetLine:
        """Erstellt eine neue Budget-Position."""
        budget = await db.get(Budget, request.budget_id)
        if not budget:
            raise ValueError(f"Budget {request.budget_id} nicht gefunden")

        line = BudgetLine(
            budget_id=request.budget_id,
            kostenstelle_id=request.kostenstelle_id,
            name=request.name,
            category=request.category,
            subcategory=request.subcategory,
            account_number=request.account_number,
            description=request.description,
            planned_amount=request.planned_amount,
            monthly_distribution=request.monthly_distribution or {},
            auto_assign_rules=request.auto_assign_rules or [],
            status=BudgetLineStatus.UNDER_BUDGET,
        )

        db.add(line)

        # Update Budget total
        budget.total_planned = (budget.total_planned or Decimal("0")) + request.planned_amount
        budget.total_remaining = (budget.total_remaining or Decimal("0")) + request.planned_amount

        await db.commit()
        await db.refresh(line)

        logger.info(
            "budget_line_created",
            line_id=str(line.id),
            budget_id=str(request.budget_id),
            category=request.category,
            planned_amount=str(request.planned_amount),
        )

        return line

    async def list_budget_lines(
        self,
        db: AsyncSession,
        budget_id: uuid.UUID,
        category: Optional[str] = None,
        kostenstelle_id: Optional[uuid.UUID] = None,
    ) -> List[BudgetLine]:
        """Listet Budget-Positionen."""
        query = (
            select(BudgetLine)
            .where(BudgetLine.budget_id == budget_id)
            .options(selectinload(BudgetLine.kostenstelle))
        )

        if category:
            query = query.where(BudgetLine.category == category)
        if kostenstelle_id:
            query = query.where(BudgetLine.kostenstelle_id == kostenstelle_id)

        query = query.order_by(BudgetLine.category, BudgetLine.name)

        result = await db.execute(query)
        return list(result.scalars().all())

    # ========================================================================
    # Allocations CRUD
    # ========================================================================

    async def create_allocation(
        self,
        db: AsyncSession,
        request: AllocationCreateRequest,
    ) -> BudgetAllocation:
        """Erstellt eine neue Budget-Zuordnung."""
        # Validiere Budget und Line
        budget = await db.get(Budget, request.budget_id)
        if not budget:
            raise ValueError(f"Budget {request.budget_id} nicht gefunden")

        if budget.status != BudgetStatus.ACTIVE:
            raise ValueError(f"Budget ist nicht aktiv (Status: {budget.status})")

        line = await db.get(BudgetLine, request.budget_line_id)
        if not line:
            raise ValueError(f"Budget-Position {request.budget_line_id} nicht gefunden")

        if line.budget_id != request.budget_id:
            raise ValueError("Budget-Position gehoert nicht zu diesem Budget")

        # Erstelle Allocation
        allocation = BudgetAllocation(
            budget_id=request.budget_id,
            budget_line_id=request.budget_line_id,
            kostenstelle_id=request.kostenstelle_id or line.kostenstelle_id,
            document_id=request.document_id,
            invoice_tracking_id=request.invoice_tracking_id,
            bank_transaction_id=request.bank_transaction_id,
            amount=request.amount,
            tax_amount=request.tax_amount,
            net_amount=request.amount - request.tax_amount,
            booking_date=request.booking_date,
            source=request.source,
            description=request.description,
            reference=request.reference,
            vendor_name=request.vendor_name,
            is_committed=request.is_committed,
            is_processed=not request.is_committed,
            created_by_id=request.created_by_id,
        )

        db.add(allocation)

        # Update Line und Budget
        if request.is_committed:
            line.committed_amount = (line.committed_amount or Decimal("0")) + request.amount
            budget.total_committed = (budget.total_committed or Decimal("0")) + request.amount
        else:
            line.actual_amount = (line.actual_amount or Decimal("0")) + request.amount
            budget.total_actual = (budget.total_actual or Decimal("0")) + request.amount

        budget.total_remaining = budget.total_planned - budget.total_actual - budget.total_committed

        # Update Line Status
        await self._update_line_status(line, budget)

        # Check for Alerts
        await self._check_and_create_alerts(db, budget, line)

        await db.commit()
        await db.refresh(allocation)

        logger.info(
            "allocation_created",
            allocation_id=str(allocation.id),
            budget_id=str(request.budget_id),
            line_id=str(request.budget_line_id),
            amount=str(request.amount),
            source=request.source.value,
        )

        return allocation

    async def list_allocations(
        self,
        db: AsyncSession,
        budget_id: uuid.UUID,
        budget_line_id: Optional[uuid.UUID] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        page: int = 0,
        page_size: int = 50,
    ) -> Tuple[List[BudgetAllocation], int]:
        """Listet Budget-Zuordnungen."""
        query = select(BudgetAllocation).where(BudgetAllocation.budget_id == budget_id)

        if budget_line_id:
            query = query.where(BudgetAllocation.budget_line_id == budget_line_id)
        if date_from:
            query = query.where(BudgetAllocation.booking_date >= date_from)
        if date_to:
            query = query.where(BudgetAllocation.booking_date <= date_to)

        # Count
        count_query = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_query)).scalar() or 0

        # Paginate
        query = (
            query
            .order_by(BudgetAllocation.booking_date.desc())
            .offset(page * page_size)
            .limit(page_size)
        )

        result = await db.execute(query)
        return list(result.scalars().all()), total

    # ========================================================================
    # Auto-Kategorisierung aus OCR
    # ========================================================================

    async def detect_category_from_ocr(
        self,
        db: AsyncSession,
        extracted_text: str,
        vendor_name: Optional[str] = None,
        amount: Optional[Decimal] = None,
        company_id: Optional[uuid.UUID] = None,
    ) -> Optional[CategoryMatchResult]:
        """Erkennt Budget-Kategorie aus OCR-extrahierten Daten."""
        # Lade Kategorien aus Cache oder DB
        await self._ensure_category_cache(db)

        best_match: Optional[CategoryMatchResult] = None
        best_score = 0.0

        text_lower = extracted_text.lower()

        for code, category in self._category_cache.items():
            if not category.is_active:
                continue

            matched_keywords = []
            matched_patterns = []

            # Keyword-Matching
            for keyword in (category.keywords or []):
                if keyword.lower() in text_lower:
                    matched_keywords.append(keyword)

            # Vendor-Pattern-Matching
            if vendor_name:
                vendor_lower = vendor_name.lower()
                for pattern in (category.vendor_patterns or []):
                    if pattern.lower() in vendor_lower:
                        matched_patterns.append(pattern)

            # Score berechnen
            score = len(matched_keywords) * 0.3 + len(matched_patterns) * 0.5

            if score > best_score:
                best_score = score
                best_match = CategoryMatchResult(
                    category=category.code,
                    subcategory=None,
                    kostenstelle_code=category.default_kostenstelle_code,
                    confidence=min(score, 1.0),
                    matched_keywords=matched_keywords,
                    matched_patterns=matched_patterns,
                    suggested_budget_line_id=None,
                )

        if best_match and best_match.confidence < 0.3:
            return None  # Nicht sicher genug

        return best_match

    async def auto_allocate_document(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        company_id: uuid.UUID,
        extracted_data: Dict[str, Any],
        user_id: Optional[uuid.UUID] = None,
    ) -> Optional[BudgetAllocation]:
        """Ordnet ein Dokument automatisch einem Budget zu."""
        # Finde aktives Budget für die Periode
        doc_date = extracted_data.get("document_date") or date.today()
        if isinstance(doc_date, str):
            doc_date = datetime.fromisoformat(doc_date).date()

        budget = await self._find_active_budget_for_date(db, company_id, doc_date)
        if not budget:
            logger.debug("auto_allocate_no_budget", document_id=str(document_id))
            return None

        # Erkenne Kategorie
        extracted_text = extracted_data.get("full_text", "")
        vendor_name = extracted_data.get("vendor_name") or extracted_data.get("sender_name")
        amount = Decimal(str(extracted_data.get("total_amount", "0")))

        match = await self.detect_category_from_ocr(
            db, extracted_text, vendor_name, amount, company_id
        )

        if not match or match.confidence < 0.5:
            logger.debug(
                "auto_allocate_low_confidence",
                document_id=str(document_id),
                confidence=match.confidence if match else 0,
            )
            return None

        # Finde passende Budget-Line
        line = await self._find_matching_budget_line(
            db, budget.id, match.category, match.kostenstelle_code
        )

        if not line:
            logger.debug(
                "auto_allocate_no_line",
                document_id=str(document_id),
                category=match.category,
            )
            return None

        # Erstelle Allocation
        allocation = await self.create_allocation(
            db,
            AllocationCreateRequest(
                budget_id=budget.id,
                budget_line_id=line.id,
                amount=amount,
                booking_date=doc_date,
                source=AllocationSource.OCR_AUTO,
                document_id=document_id,
                vendor_name=vendor_name,
                description=f"Auto-Zuordnung: {match.category}",
                created_by_id=user_id,
            )
        )

        # Update Allocation mit OCR-Details
        allocation.ocr_confidence = match.confidence
        allocation.ocr_extracted_category = match.category
        allocation.ocr_matched_rule = ", ".join(match.matched_keywords[:3])
        await db.commit()

        logger.info(
            "auto_allocation_created",
            document_id=str(document_id),
            allocation_id=str(allocation.id),
            category=match.category,
            confidence=match.confidence,
        )

        return allocation

    # ========================================================================
    # Variance Reports (Abweichungsanalysen)
    # ========================================================================

    async def generate_variance_report(
        self,
        db: AsyncSession,
        budget_id: uuid.UUID,
    ) -> BudgetVarianceReport:
        """Generiert Abweichungsbericht für ein Budget."""
        budget = await self.get_budget(db, budget_id, include_lines=True)
        if not budget:
            raise ValueError(f"Budget {budget_id} nicht gefunden")

        lines_data = []
        by_category: Dict[str, Dict[str, Any]] = {}
        by_kostenstelle: Dict[str, Dict[str, Any]] = {}
        total_variance = Decimal("0")
        recommendations = []

        for line in budget.lines:
            variance = line.actual_amount - line.planned_amount
            variance_percent = (
                float((variance / line.planned_amount) * 100)
                if line.planned_amount > 0 else 0.0
            )

            total_variance += variance

            line_data = {
                "line_id": str(line.id),
                "name": line.name,
                "category": line.category,
                "subcategory": line.subcategory,
                "kostenstelle_id": str(line.kostenstelle_id) if line.kostenstelle_id else None,
                "kostenstelle_code": line.kostenstelle.code if line.kostenstelle else None,
                "planned": float(line.planned_amount),
                "actual": float(line.actual_amount),
                "committed": float(line.committed_amount or 0),
                "variance": float(variance),
                "variance_percent": variance_percent,
                "status": line.status.value,
            }
            lines_data.append(line_data)

            # Aggregiere nach Kategorie
            if line.category not in by_category:
                by_category[line.category] = {
                    "planned": Decimal("0"),
                    "actual": Decimal("0"),
                    "variance": Decimal("0"),
                }
            by_category[line.category]["planned"] += line.planned_amount
            by_category[line.category]["actual"] += line.actual_amount
            by_category[line.category]["variance"] += variance

            # Aggregiere nach Kostenstelle
            ks_key = str(line.kostenstelle_id) if line.kostenstelle_id else "none"
            if ks_key not in by_kostenstelle:
                by_kostenstelle[ks_key] = {
                    "name": line.kostenstelle.name if line.kostenstelle else "Ohne Zuordnung",
                    "planned": Decimal("0"),
                    "actual": Decimal("0"),
                    "variance": Decimal("0"),
                }
            by_kostenstelle[ks_key]["planned"] += line.planned_amount
            by_kostenstelle[ks_key]["actual"] += line.actual_amount
            by_kostenstelle[ks_key]["variance"] += variance

            # Generiere Empfehlungen
            if variance_percent > 20:
                recommendations.append(
                    f"Position '{line.name}' liegt {variance_percent:.1f}% über Budget. "
                    f"Prüfung empfohlen."
                )
            elif variance_percent < -30 and budget.status == BudgetStatus.ACTIVE:
                recommendations.append(
                    f"Position '{line.name}' ist nur zu {100 + variance_percent:.1f}% ausgeschoepft. "
                    f"Budget-Umverteilung möglich."
                )

        # Konvertiere Decimals zu floats für JSON
        for cat_data in by_category.values():
            cat_data["planned"] = float(cat_data["planned"])
            cat_data["actual"] = float(cat_data["actual"])
            cat_data["variance"] = float(cat_data["variance"])

        for ks_data in by_kostenstelle.values():
            ks_data["planned"] = float(ks_data["planned"])
            ks_data["actual"] = float(ks_data["actual"])
            ks_data["variance"] = float(ks_data["variance"])

        total_variance_percent = (
            float((total_variance / budget.total_planned) * 100)
            if budget.total_planned > 0 else 0.0
        )

        return BudgetVarianceReport(
            budget_id=budget.id,
            period_start=budget.start_date,
            period_end=budget.end_date,
            lines=lines_data,
            total_variance=total_variance,
            total_variance_percent=total_variance_percent,
            by_category=by_category,
            by_kostenstelle=by_kostenstelle,
            recommendations=recommendations,
            generated_at=utc_now(),
        )

    # ========================================================================
    # Alert System
    # ========================================================================

    async def _check_and_create_alerts(
        self,
        db: AsyncSession,
        budget: Budget,
        line: BudgetLine,
    ) -> Optional[BudgetAlert]:
        """Prüft auf Budget-Überschreitungen und erstellt Alerts."""
        utilization = line.utilization_percent

        # Bestimme Severity
        severity: Optional[AlertSeverity] = None
        threshold = 0.0

        if utilization > 100:
            severity = AlertSeverity.EXCEEDED
            threshold = 100.0
        elif utilization >= budget.critical_threshold:
            severity = AlertSeverity.CRITICAL
            threshold = budget.critical_threshold
        elif utilization >= budget.warning_threshold:
            severity = AlertSeverity.WARNING
            threshold = budget.warning_threshold

        if not severity:
            return None

        # Prüfe ob Alert bereits existiert
        existing = await db.execute(
            select(BudgetAlert).where(
                and_(
                    BudgetAlert.budget_line_id == line.id,
                    BudgetAlert.severity == severity,
                    BudgetAlert.is_acknowledged == False,
                )
            )
        )

        if existing.scalar_one_or_none():
            return None  # Alert existiert bereits

        # Erstelle neuen Alert
        amount_exceeded = None
        if utilization > 100:
            amount_exceeded = line.actual_amount - line.planned_amount

        alert = BudgetAlert(
            budget_id=budget.id,
            budget_line_id=line.id,
            kostenstelle_id=line.kostenstelle_id,
            severity=severity,
            title=f"Budget-{severity.value.capitalize()}: {line.name}",
            message=self._generate_alert_message(line, utilization, severity),
            threshold_percent=threshold,
            actual_percent=utilization,
            amount_exceeded=amount_exceeded,
        )

        db.add(alert)

        logger.warning(
            "budget_alert_created",
            budget_id=str(budget.id),
            line_id=str(line.id),
            severity=severity.value,
            utilization=utilization,
        )

        return alert

    def _generate_alert_message(
        self,
        line: BudgetLine,
        utilization: float,
        severity: AlertSeverity,
    ) -> str:
        """Generiert Alert-Nachricht."""
        if severity == AlertSeverity.EXCEEDED:
            return (
                f"Budget für '{line.name}' wurde überschritten. "
                f"Ist: {line.actual_amount:.2f} EUR, "
                f"Soll: {line.planned_amount:.2f} EUR "
                f"({utilization:.1f}% Auslastung)"
            )
        elif severity == AlertSeverity.CRITICAL:
            return (
                f"Budget für '{line.name}' ist kritisch. "
                f"Aktuelle Auslastung: {utilization:.1f}%. "
                f"Verbleibend: {line.remaining_amount:.2f} EUR"
            )
        else:
            return (
                f"Budget für '{line.name}' naehert sich der Grenze. "
                f"Aktuelle Auslastung: {utilization:.1f}%. "
                f"Verbleibend: {line.remaining_amount:.2f} EUR"
            )

    async def acknowledge_alert(
        self,
        db: AsyncSession,
        alert_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> BudgetAlert:
        """Bestätigt einen Budget-Alert."""
        alert = await db.get(BudgetAlert, alert_id)
        if not alert:
            raise ValueError(f"Alert {alert_id} nicht gefunden")

        alert.is_acknowledged = True
        alert.acknowledged_at = utc_now()
        alert.acknowledged_by_id = user_id

        await db.commit()
        await db.refresh(alert)

        logger.info(
            "alert_acknowledged",
            alert_id=str(alert_id),
            user_id=str(user_id),
        )

        return alert

    async def list_unacknowledged_alerts(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        severity: Optional[AlertSeverity] = None,
    ) -> List[BudgetAlert]:
        """Listet unbestätigte Alerts."""
        query = (
            select(BudgetAlert)
            .join(Budget)
            .where(
                and_(
                    Budget.company_id == company_id,
                    BudgetAlert.is_acknowledged == False,
                )
            )
            .options(
                joinedload(BudgetAlert.budget),
                joinedload(BudgetAlert.budget_line),
            )
        )

        if severity:
            query = query.where(BudgetAlert.severity == severity)

        query = query.order_by(
            BudgetAlert.severity.desc(),
            BudgetAlert.created_at.desc(),
        )

        result = await db.execute(query)
        return list(result.scalars().all())

    # ========================================================================
    # Helper Methods
    # ========================================================================

    async def _update_line_status(self, line: BudgetLine, budget: Budget) -> None:
        """Aktualisiert den Status einer Budget-Position."""
        utilization = line.utilization_percent

        if utilization > 100:
            line.status = BudgetLineStatus.OVER_BUDGET
        elif utilization >= budget.warning_threshold:
            line.status = BudgetLineStatus.WARNING
        elif utilization >= 50:
            line.status = BudgetLineStatus.ON_TRACK
        else:
            line.status = BudgetLineStatus.UNDER_BUDGET

    async def _find_active_budget_for_date(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        target_date: date,
    ) -> Optional[Budget]:
        """Findet aktives Budget für ein Datum."""
        result = await db.execute(
            select(Budget).where(
                and_(
                    Budget.company_id == company_id,
                    Budget.status == BudgetStatus.ACTIVE,
                    Budget.start_date <= target_date,
                    Budget.end_date >= target_date,
                )
            ).order_by(
                # Bevorzuge spezifischere Budgets (Monat > Quartal > Jahr)
                Budget.period_type.desc()
            ).limit(1)
        )
        return result.scalar_one_or_none()

    async def _find_matching_budget_line(
        self,
        db: AsyncSession,
        budget_id: uuid.UUID,
        category: str,
        kostenstelle_code: Optional[str] = None,
    ) -> Optional[BudgetLine]:
        """Findet passende Budget-Position."""
        query = select(BudgetLine).where(
            and_(
                BudgetLine.budget_id == budget_id,
                BudgetLine.category == category,
            )
        )

        if kostenstelle_code:
            query = query.join(Kostenstelle).where(
                Kostenstelle.code == kostenstelle_code
            )

        result = await db.execute(query.limit(1))
        return result.scalar_one_or_none()

    async def _ensure_category_cache(self, db: AsyncSession) -> None:
        """Stellt sicher dass Kategorie-Cache aktuell ist."""
        now = utc_now()
        if (
            self._cache_timestamp is None
            or now - self._cache_timestamp > self._cache_ttl
        ):
            result = await db.execute(
                select(BudgetCategory).where(BudgetCategory.is_active == True)
            )
            categories = result.scalars().all()
            self._category_cache = {c.code: c for c in categories}
            self._cache_timestamp = now


# ============================================================================
# Singleton
# ============================================================================


_budget_service: Optional[BudgetService] = None


def get_budget_service() -> BudgetService:
    """Returns singleton BudgetService instance."""
    global _budget_service
    if _budget_service is None:
        _budget_service = BudgetService()
    return _budget_service
