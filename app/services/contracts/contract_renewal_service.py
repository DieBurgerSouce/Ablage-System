# -*- coding: utf-8 -*-
"""
Contract Renewal Service for Ablage-System.

Phase 1.1: Vertragsverlaengerungs-Warnung (Contract Renewal Warning)

Features:
- Automatische Erkennung von Kuendigungsfristen aus OCR-Text
- Benachrichtigungen 30/60/90 Tage vor Fristablauf
- Integration mit Alert Center
- Erinnerungs-Scheduling

Feinpoliert und durchdacht - Enterprise Contract Management.
"""

import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional, List, Dict, Tuple
from uuid import UUID

import structlog
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models_contract import (
    Contract,
    ContractDeadline,
    ContractStatus,
)
from app.db.models_alert import AlertCategory, AlertSeverity, AlertStatus
from app.services.alert_center_service import (
    AlertCenterService,
    AlertCodes,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Standard reminder days (before deadline)
DEFAULT_REMINDER_DAYS: List[int] = [90, 60, 30, 14, 7, 1]

# German date patterns for OCR extraction
DATE_PATTERNS: List[str] = [
    r"(\d{1,2})\.(\d{1,2})\.(\d{4})",  # DD.MM.YYYY
    r"(\d{1,2})\.(\d{1,2})\.(\d{2})",  # DD.MM.YY
    r"(\d{4})-(\d{2})-(\d{2})",        # YYYY-MM-DD
]

# German keywords indicating termination deadlines
TERMINATION_KEYWORDS: List[str] = [
    "kuendigungsfrist",
    "kuendigung",
    "kuendigbar",
    "vertragsende",
    "laufzeit",
    "beendet",
    "endet am",
    "laeuft ab",
    "ablauf",
    "ablaufdatum",
    "mindestlaufzeit",
    "vertragslaufzeit",
    "ordentliche kuendigung",
    "ausserordentliche kuendigung",
    "fristgerecht",
    "befristet bis",
    "gueltig bis",
    "zum",  # "zum 31.12.2026"
]

# Duration keywords
DURATION_PATTERNS: Dict[str, int] = {
    r"(\d+)\s*tag": 1,
    r"(\d+)\s*tage": 1,
    r"(\d+)\s*woch": 7,
    r"(\d+)\s*wochen": 7,
    r"(\d+)\s*monat": 30,
    r"(\d+)\s*monate": 30,
    r"(\d+)\s*jahr": 365,
    r"(\d+)\s*jahre": 365,
}


# =============================================================================
# Alert Codes Extension for Contract Renewal
# =============================================================================

class ContractAlertCodes:
    """Extended alert codes for contract renewal warnings."""

    # Renewal warnings
    RENEWAL_90_DAYS = "DEAD_CONTRACT_90"
    RENEWAL_60_DAYS = "DEAD_CONTRACT_60"
    RENEWAL_30_DAYS = "DEAD_CONTRACT_30"
    RENEWAL_14_DAYS = "DEAD_CONTRACT_14"
    RENEWAL_7_DAYS = "DEAD_CONTRACT_7"
    RENEWAL_1_DAY = "DEAD_CONTRACT_1"

    # Critical deadlines
    NOTICE_DEADLINE_CRITICAL = "DEAD_NOTICE_CRITICAL"
    CONTRACT_EXPIRED = "DEAD_CONTRACT_EXPIRED"
    AUTO_RENEWAL_WARNING = "DEAD_AUTO_RENEWAL"


# =============================================================================
# Contract Renewal Service
# =============================================================================

class ContractRenewalService:
    """
    Service for managing contract renewal warnings.

    Integrates with:
    - Alert Center for notifications
    - Contract Deadline Service for scheduling
    - OCR text for automatic date extraction
    """

    def __init__(self, db: AsyncSession):
        """Initialize with database session."""
        self.db = db
        self._alert_service: Optional[AlertCenterService] = None

    @property
    def alert_service(self) -> AlertCenterService:
        """Lazy-load alert center service."""
        if self._alert_service is None:
            self._alert_service = AlertCenterService(self.db)
        return self._alert_service

    # =========================================================================
    # OCR Date Extraction
    # =========================================================================

    async def extract_contract_dates_from_document(
        self,
        document_id: UUID,
        company_id: UUID,
    ) -> Dict[str, Optional[date]]:
        """
        Extract termination/renewal dates from OCR text of a document.

        Args:
            document_id: ID of the document with OCR text
            company_id: Company ID for access control

        Returns:
            Dictionary with extracted dates:
            - effective_date: Contract start date
            - expiration_date: Contract end date
            - notice_deadline: Termination notice deadline
            - notice_period_days: Notice period in days
        """
        from app.db.models import Document

        # Get document with OCR text
        doc = await self.db.get(Document, document_id)
        if not doc or not doc.extracted_text:
            logger.debug(
                "contract_date_extraction_skipped",
                document_id=str(document_id),
                reason="no_ocr_text",
            )
            return {
                "effective_date": None,
                "expiration_date": None,
                "notice_deadline": None,
                "notice_period_days": None,
            }

        text = doc.extracted_text.lower()
        result = self._extract_dates_from_text(text)

        logger.info(
            "contract_dates_extracted",
            document_id=str(document_id),
            found_dates=sum(1 for v in result.values() if v is not None),
        )

        return result

    def _extract_dates_from_text(
        self,
        text: str,
    ) -> Dict[str, Optional[date]]:
        """
        Extract contract-relevant dates from text.

        Uses German date patterns and context keywords to identify:
        - Contract end dates
        - Termination notice deadlines
        - Notice periods
        """
        result: Dict[str, Optional[date]] = {
            "effective_date": None,
            "expiration_date": None,
            "notice_deadline": None,
            "notice_period_days": None,
        }

        # Find all dates in text
        found_dates: List[Tuple[date, str, int]] = []

        for pattern in DATE_PATTERNS:
            for match in re.finditer(pattern, text):
                try:
                    date_obj = self._parse_date_match(match)
                    if date_obj:
                        # Get context around the date (100 chars before)
                        start_pos = max(0, match.start() - 100)
                        context = text[start_pos:match.end()]
                        found_dates.append((date_obj, context, match.start()))
                except (ValueError, IndexError):
                    continue

        # Analyze context to determine date types
        for date_obj, context, pos in found_dates:
            context_lower = context.lower()

            # Check for termination/expiration keywords
            is_termination = any(kw in context_lower for kw in [
                "kuendig", "ablauf", "endet", "beendet", "laufzeit", "gueltig bis"
            ])

            # Check for start date keywords
            is_start = any(kw in context_lower for kw in [
                "beginn", "start", "ab dem", "gueltig ab", "wirksam ab"
            ])

            if is_termination and date_obj > date.today():
                if result["expiration_date"] is None or date_obj < result["expiration_date"]:
                    result["expiration_date"] = date_obj
            elif is_start:
                if result["effective_date"] is None or date_obj < result["effective_date"]:
                    result["effective_date"] = date_obj

        # Extract notice period
        notice_period = self._extract_notice_period(text)
        if notice_period:
            result["notice_period_days"] = notice_period

            # Calculate notice deadline if we have expiration date and notice period
            if result["expiration_date"] and notice_period:
                result["notice_deadline"] = result["expiration_date"] - timedelta(days=notice_period)

        return result

    def _parse_date_match(self, match: re.Match) -> Optional[date]:
        """Parse a regex date match into a date object."""
        groups = match.groups()

        if len(groups) == 3:
            if len(groups[0]) == 4:
                # YYYY-MM-DD format
                year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
            elif len(groups[2]) == 4:
                # DD.MM.YYYY format
                day, month, year = int(groups[0]), int(groups[1]), int(groups[2])
            else:
                # DD.MM.YY format
                day, month, year = int(groups[0]), int(groups[1]), int(groups[2])
                year = 2000 + year if year < 50 else 1900 + year

            try:
                return date(year, month, day)
            except ValueError:
                return None

        return None

    def _extract_notice_period(self, text: str) -> Optional[int]:
        """
        Extract notice period in days from text.

        Looks for patterns like:
        - "Kuendigungsfrist von 3 Monaten"
        - "30 Tage Kuendigungsfrist"
        - "4 Wochen vor Vertragsende"
        """
        text_lower = text.lower()

        # Look for notice period patterns
        notice_patterns = [
            r"kuendigungsfrist\s+(?:von\s+)?(\d+)\s+(tage?|wochen?|monate?|jahre?)",
            r"(\d+)\s+(tage?|wochen?|monate?|jahre?)\s+(?:vor\s+)?kuendig",
            r"frist\s+(?:von\s+)?(\d+)\s+(tage?|wochen?|monate?|jahre?)",
            r"(\d+)\s+(tage?|wochen?|monate?|jahre?)\s+frist",
        ]

        for pattern in notice_patterns:
            match = re.search(pattern, text_lower)
            if match:
                value = int(match.group(1))
                unit = match.group(2)

                # Convert to days
                if "tag" in unit:
                    return value
                elif "woch" in unit:
                    return value * 7
                elif "monat" in unit:
                    return value * 30
                elif "jahr" in unit:
                    return value * 365

        return None

    # =========================================================================
    # Reminder Scheduling
    # =========================================================================

    async def schedule_reminders(
        self,
        contract_id: UUID,
        deadline: date,
        deadline_type: str = "termination_notice",
        reminder_days: Optional[List[int]] = None,
    ) -> List[ContractDeadline]:
        """
        Schedule reminder deadlines for a contract.

        Creates ContractDeadline entries for 30/60/90 days before the deadline.

        Args:
            contract_id: Contract ID
            deadline: The main deadline date
            deadline_type: Type of deadline
            reminder_days: Days before deadline for reminders (default: [90, 60, 30])

        Returns:
            List of created ContractDeadline objects
        """
        contract = await self.db.get(Contract, contract_id)
        if not contract:
            raise ValueError(f"Vertrag {contract_id} nicht gefunden")

        if reminder_days is None:
            reminder_days = [90, 60, 30]

        today = date.today()
        created_deadlines: List[ContractDeadline] = []

        for days_before in reminder_days:
            reminder_date = deadline - timedelta(days=days_before)

            # Skip if date is in the past
            if reminder_date <= today:
                continue

            # Check if deadline already exists
            existing = await self._get_existing_deadline(
                contract_id=contract_id,
                deadline_date=reminder_date,
                deadline_type=deadline_type,
            )

            if existing:
                continue

            # Create new deadline
            title = self._get_reminder_title(deadline_type, days_before, contract.title)
            description = self._get_reminder_description(
                deadline_type, days_before, deadline, contract.title
            )
            priority = self._get_priority_for_days(days_before)

            new_deadline = ContractDeadline(
                contract_id=contract_id,
                deadline_type=deadline_type,
                title=title,
                description=description,
                deadline_date=reminder_date,
                priority=priority,
                is_completed=False,
                reminder_days_before=[7, 3, 1],  # Reminder for the reminder
                company_id=contract.company_id,
            )

            self.db.add(new_deadline)
            created_deadlines.append(new_deadline)

        if created_deadlines:
            await self.db.commit()
            logger.info(
                "contract_reminders_scheduled",
                contract_id=str(contract_id),
                count=len(created_deadlines),
            )

        return created_deadlines

    async def _get_existing_deadline(
        self,
        contract_id: UUID,
        deadline_date: date,
        deadline_type: str,
    ) -> Optional[ContractDeadline]:
        """Check if a deadline already exists."""
        result = await self.db.execute(
            select(ContractDeadline).where(
                and_(
                    ContractDeadline.contract_id == contract_id,
                    ContractDeadline.deadline_date == deadline_date,
                    ContractDeadline.deadline_type == deadline_type,
                )
            )
        )
        return result.scalar_one_or_none()

    def _get_reminder_title(
        self,
        deadline_type: str,
        days_before: int,
        contract_title: str,
    ) -> str:
        """Generate reminder title in German."""
        type_names = {
            "termination_notice": "Kuendigungsfrist",
            "contract_expiry": "Vertragsablauf",
            "renewal_decision": "Verlaengerungsentscheidung",
        }
        type_name = type_names.get(deadline_type, "Frist")

        return f"{type_name} in {days_before} Tagen"

    def _get_reminder_description(
        self,
        deadline_type: str,
        days_before: int,
        deadline: date,
        contract_title: str,
    ) -> str:
        """Generate reminder description in German."""
        type_descriptions = {
            "termination_notice": "Die Kuendigungsfrist fuer diesen Vertrag",
            "contract_expiry": "Dieser Vertrag",
            "renewal_decision": "Die Entscheidung zur Vertragsverlaengerung",
        }
        desc = type_descriptions.get(deadline_type, "Diese Frist")

        return (
            f"{desc} laeuft am {deadline.strftime('%d.%m.%Y')} ab. "
            f"Bitte pruefen Sie rechtzeitig, ob eine Kuendigung oder "
            f"Verlaengerung erforderlich ist."
        )

    def _get_priority_for_days(self, days_before: int) -> str:
        """Determine priority based on days before deadline."""
        if days_before <= 7:
            return "critical"
        elif days_before <= 30:
            return "high"
        elif days_before <= 60:
            return "medium"
        return "low"

    # =========================================================================
    # Deadline Check and Alerts
    # =========================================================================

    async def check_upcoming_deadlines(
        self,
        company_id: Optional[UUID] = None,
    ) -> Dict[str, int]:
        """
        Check all contracts for upcoming deadlines and create alerts.

        This is the main daily task that:
        1. Finds contracts with upcoming deadlines
        2. Creates Alert Center entries for critical deadlines
        3. Updates contract status if needed

        Args:
            company_id: Optional - check only for specific company

        Returns:
            Statistics about processed contracts
        """
        today = date.today()
        stats = {
            "contracts_checked": 0,
            "alerts_created": 0,
            "deadlines_found": 0,
            "errors": 0,
        }

        # Query for active contracts with upcoming deadlines
        query = select(Contract).where(
            and_(
                Contract.status.in_([
                    ContractStatus.ACTIVE.value,
                    ContractStatus.RENEWED.value,
                ]),
                or_(
                    # Expiration within 90 days
                    and_(
                        Contract.expiration_date.isnot(None),
                        Contract.expiration_date <= today + timedelta(days=90),
                        Contract.expiration_date >= today,
                    ),
                    # Auto-renewal with notice period upcoming
                    and_(
                        Contract.auto_renewal == True,
                        Contract.expiration_date.isnot(None),
                        Contract.renewal_notice_days.isnot(None),
                    ),
                ),
            )
        )

        if company_id:
            query = query.where(Contract.company_id == company_id)

        result = await self.db.execute(query)
        contracts = result.scalars().all()

        for contract in contracts:
            stats["contracts_checked"] += 1

            try:
                await self._process_contract_deadlines(contract, today, stats)
            except Exception as e:
                stats["errors"] += 1
                logger.warning(
                    "contract_deadline_check_failed",
                    contract_id=str(contract.id),
                    error_type=type(e).__name__,
                )

        logger.info(
            "contract_deadline_check_completed",
            contracts_checked=stats["contracts_checked"],
            alerts_created=stats["alerts_created"],
            deadlines_found=stats["deadlines_found"],
            errors=stats["errors"],
        )

        return stats

    async def _process_contract_deadlines(
        self,
        contract: Contract,
        today: date,
        stats: Dict[str, int],
    ) -> None:
        """Process deadlines for a single contract."""

        # Check expiration date
        if contract.expiration_date:
            days_until_expiry = (contract.expiration_date - today).days

            if days_until_expiry >= 0:
                stats["deadlines_found"] += 1

                # Create alert based on urgency
                if days_until_expiry in DEFAULT_REMINDER_DAYS:
                    alert_created = await self._create_renewal_alert(
                        contract=contract,
                        days_remaining=days_until_expiry,
                        deadline_type="expiration",
                    )
                    if alert_created:
                        stats["alerts_created"] += 1

        # Check notice deadline for auto-renewal contracts
        if contract.auto_renewal and contract.renewal_notice_days:
            notice_deadline = contract.expiration_date - timedelta(days=contract.renewal_notice_days)
            days_until_notice = (notice_deadline - today).days

            if 0 <= days_until_notice <= 90:
                stats["deadlines_found"] += 1

                if days_until_notice in [30, 14, 7, 3, 1]:
                    alert_created = await self._create_renewal_alert(
                        contract=contract,
                        days_remaining=days_until_notice,
                        deadline_type="notice",
                    )
                    if alert_created:
                        stats["alerts_created"] += 1

    async def _create_renewal_alert(
        self,
        contract: Contract,
        days_remaining: int,
        deadline_type: str,
    ) -> bool:
        """
        Create an alert in Alert Center for contract renewal.

        Args:
            contract: The contract
            days_remaining: Days until deadline
            deadline_type: "expiration" or "notice"

        Returns:
            True if alert was created, False if deduplicated
        """
        # Determine alert code and severity
        if days_remaining <= 7:
            alert_code = ContractAlertCodes.RENEWAL_7_DAYS
            severity = AlertSeverity.CRITICAL
        elif days_remaining <= 14:
            alert_code = ContractAlertCodes.RENEWAL_14_DAYS
            severity = AlertSeverity.HIGH
        elif days_remaining <= 30:
            alert_code = ContractAlertCodes.RENEWAL_30_DAYS
            severity = AlertSeverity.HIGH
        elif days_remaining <= 60:
            alert_code = ContractAlertCodes.RENEWAL_60_DAYS
            severity = AlertSeverity.MEDIUM
        else:
            alert_code = ContractAlertCodes.RENEWAL_90_DAYS
            severity = AlertSeverity.LOW

        # Build title and message (German)
        if deadline_type == "notice":
            title = f"Kuendigungsfrist in {days_remaining} Tagen"
            message = (
                f"Die Kuendigungsfrist fuer den Vertrag '{contract.title}' "
                f"laeuft in {days_remaining} Tagen ab. "
                f"Nach Ablauf verlaengert sich der Vertrag automatisch."
            )
        else:
            title = f"Vertragsablauf in {days_remaining} Tagen"
            message = (
                f"Der Vertrag '{contract.title}' laeuft in {days_remaining} Tagen ab. "
                f"Bitte pruefen Sie, ob eine Verlaengerung oder Kuendigung erforderlich ist."
            )

        # Create recurrence key for deduplication
        recurrence_key = f"contract_renewal_{contract.id}_{days_remaining}d"

        try:
            alert = await self.alert_service.create_alert(
                company_id=contract.company_id,
                alert_code=alert_code,
                category=AlertCategory.DEADLINE,
                severity=severity,
                title=title,
                message=message,
                source_type="contract_renewal_service",
                source_id=str(contract.id),
                entity_id=contract.counterparty_entity_id,
                metadata={
                    "contract_id": str(contract.id),
                    "contract_title": contract.title,
                    "days_remaining": days_remaining,
                    "deadline_type": deadline_type,
                    "expiration_date": contract.expiration_date.isoformat() if contract.expiration_date else None,
                    "auto_renewal": contract.auto_renewal,
                },
                context={
                    "link": f"/contracts/{contract.id}",
                    "link_text": "Vertrag oeffnen",
                },
                available_actions=["acknowledge", "dismiss", "view_contract"],
                recurrence_key=recurrence_key,
                auto_dismiss_hours=24 * days_remaining if days_remaining > 0 else None,
            )

            # Check if this was a new alert or deduplicated
            return alert.status == AlertStatus.NEW.value

        except Exception as e:
            logger.error(
                "renewal_alert_creation_failed",
                contract_id=str(contract.id),
                error_type=type(e).__name__,
            )
            return False

    # =========================================================================
    # Contract-specific Operations
    # =========================================================================

    async def get_upcoming_renewals(
        self,
        company_id: UUID,
        days_ahead: int = 90,
        include_auto_renewal: bool = True,
    ) -> List[Dict]:
        """
        Get list of contracts with upcoming renewal/expiration.

        Args:
            company_id: Company ID
            days_ahead: Days to look ahead
            include_auto_renewal: Include auto-renewing contracts

        Returns:
            List of contract renewal info
        """
        today = date.today()
        cutoff = today + timedelta(days=days_ahead)

        query = select(Contract).where(
            and_(
                Contract.company_id == company_id,
                Contract.status.in_([
                    ContractStatus.ACTIVE.value,
                    ContractStatus.RENEWED.value,
                ]),
                Contract.expiration_date.isnot(None),
                Contract.expiration_date >= today,
                Contract.expiration_date <= cutoff,
            )
        ).options(
            selectinload(Contract.counterparty)
        ).order_by(
            Contract.expiration_date.asc()
        )

        if not include_auto_renewal:
            query = query.where(Contract.auto_renewal == False)

        result = await self.db.execute(query)
        contracts = result.scalars().all()

        renewals = []
        for contract in contracts:
            days_until = (contract.expiration_date - today).days

            # Calculate notice deadline
            notice_deadline = None
            notice_days_remaining = None
            if contract.notice_period_days:
                notice_deadline = contract.expiration_date - timedelta(days=contract.notice_period_days)
                if notice_deadline >= today:
                    notice_days_remaining = (notice_deadline - today).days

            renewals.append({
                "contract_id": str(contract.id),
                "title": contract.title,
                "contract_type": contract.contract_type,
                "expiration_date": contract.expiration_date.isoformat(),
                "days_until_expiry": days_until,
                "auto_renewal": contract.auto_renewal,
                "renewal_period_months": contract.renewal_period_months,
                "notice_deadline": notice_deadline.isoformat() if notice_deadline else None,
                "notice_days_remaining": notice_days_remaining,
                "notice_period_days": contract.notice_period_days,
                "total_value": float(contract.total_value) if contract.total_value else None,
                "currency": contract.currency,
                "counterparty_name": contract.counterparty.name if contract.counterparty else None,
                "urgency": self._calculate_urgency(days_until, notice_days_remaining),
            })

        return renewals

    def _calculate_urgency(
        self,
        days_until_expiry: int,
        notice_days_remaining: Optional[int],
    ) -> str:
        """Calculate urgency level for a contract renewal."""
        # Notice deadline is more urgent than expiry
        if notice_days_remaining is not None:
            if notice_days_remaining <= 7:
                return "critical"
            elif notice_days_remaining <= 30:
                return "high"

        if days_until_expiry <= 7:
            return "critical"
        elif days_until_expiry <= 30:
            return "high"
        elif days_until_expiry <= 60:
            return "medium"
        return "low"

    async def set_manual_deadline(
        self,
        contract_id: UUID,
        deadline_date: date,
        deadline_type: str,
        user_id: UUID,
        description: Optional[str] = None,
    ) -> ContractDeadline:
        """
        Manually set or override a contract deadline.

        Args:
            contract_id: Contract ID
            deadline_date: The deadline date
            deadline_type: Type of deadline
            user_id: User making the change
            description: Optional description

        Returns:
            Created or updated ContractDeadline
        """
        contract = await self.db.get(Contract, contract_id)
        if not contract:
            raise ValueError(f"Vertrag {contract_id} nicht gefunden")

        # Check for existing deadline of same type
        existing = await self.db.execute(
            select(ContractDeadline).where(
                and_(
                    ContractDeadline.contract_id == contract_id,
                    ContractDeadline.deadline_type == deadline_type,
                    ContractDeadline.is_completed == False,
                )
            )
        )
        deadline = existing.scalar_one_or_none()

        if deadline:
            # Update existing
            deadline.deadline_date = deadline_date
            deadline.description = description
            deadline.updated_at = datetime.now(timezone.utc)
        else:
            # Create new
            title = self._get_reminder_title(deadline_type, 0, contract.title)
            deadline = ContractDeadline(
                contract_id=contract_id,
                deadline_type=deadline_type,
                title=title,
                description=description or self._get_reminder_description(
                    deadline_type, 0, deadline_date, contract.title
                ),
                deadline_date=deadline_date,
                priority=self._get_priority_for_days(
                    (deadline_date - date.today()).days
                ),
                is_completed=False,
                company_id=contract.company_id,
            )
            self.db.add(deadline)

        await self.db.commit()
        await self.db.refresh(deadline)

        # Schedule reminders for this deadline
        await self.schedule_reminders(
            contract_id=contract_id,
            deadline=deadline_date,
            deadline_type=deadline_type,
        )

        logger.info(
            "manual_deadline_set",
            contract_id=str(contract_id),
            deadline_type=deadline_type,
            deadline_date=deadline_date.isoformat(),
        )

        return deadline

    async def get_reminder_schedule(
        self,
        contract_id: UUID,
    ) -> List[Dict]:
        """
        Get the reminder schedule for a contract.

        Args:
            contract_id: Contract ID

        Returns:
            List of scheduled reminders
        """
        result = await self.db.execute(
            select(ContractDeadline).where(
                and_(
                    ContractDeadline.contract_id == contract_id,
                    ContractDeadline.is_completed == False,
                )
            ).order_by(
                ContractDeadline.deadline_date.asc()
            )
        )
        deadlines = result.scalars().all()

        today = date.today()
        reminders = []

        for deadline in deadlines:
            days_until = (deadline.deadline_date - today).days
            reminders.append({
                "id": str(deadline.id),
                "deadline_type": deadline.deadline_type,
                "title": deadline.title,
                "deadline_date": deadline.deadline_date.isoformat(),
                "days_until": days_until,
                "priority": deadline.priority,
                "reminder_days": deadline.reminder_days_before or [],
                "last_reminder_sent": deadline.last_reminder_sent.isoformat() if deadline.last_reminder_sent else None,
                "is_overdue": days_until < 0,
            })

        return reminders


# =============================================================================
# Factory Function
# =============================================================================

def get_contract_renewal_service(db: AsyncSession) -> ContractRenewalService:
    """Factory function to create ContractRenewalService instance."""
    return ContractRenewalService(db)
