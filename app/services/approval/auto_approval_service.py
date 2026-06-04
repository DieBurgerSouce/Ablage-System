# -*- coding: utf-8 -*-
"""
AutoApprovalService - Automatische Genehmigung für Niedrig-Risiko-Dokumente.

Implementiert konfigurierbare Regeln für automatische Genehmigungen:
- Betragsschwellen (z.B. Rechnungen < 500€)
- Bekannte Lieferanten mit gutem Risiko-Score
- Dokumenttyp-basierte Regeln
- Entity-Beziehungshistorie

Human-in-the-Loop Pattern:
- Opt-out pro User/Dokumenttyp möglich
- Vollständiger Audit-Trail für Compliance
- Integration mit AIDecisionService für Erklärbarkeit
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Set

import structlog
from sqlalchemy import select, and_, or_, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.db.models import (
    Document,
    BusinessEntity,
    InvoiceTracking,
    ApprovalRequest,
    ApprovalStep,
    ApprovalStatus,
    ApprovalPriority,
    User,
    Company,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# Enums und Konstanten
# ============================================================================


class AutoApprovalReason(str, Enum):
    """Gruende für automatische Genehmigung."""

    AMOUNT_BELOW_THRESHOLD = "amount_below_threshold"
    TRUSTED_SUPPLIER = "trusted_supplier"
    LOW_RISK_SCORE = "low_risk_score"
    RECURRING_PAYMENT = "recurring_payment"
    PRE_APPROVED_CATEGORY = "pre_approved_category"
    KNOWN_DOCUMENT_CHAIN = "known_document_chain"


class AutoApprovalDecision(str, Enum):
    """Entscheidungsergebnis."""

    AUTO_APPROVED = "auto_approved"
    REQUIRES_REVIEW = "requires_review"
    ESCALATE = "escalate"
    BLOCKED = "blocked"


# ============================================================================
# Datenklassen
# ============================================================================


@dataclass
class AutoApprovalRule:
    """Konfigurierbare Regel für automatische Genehmigung."""

    id: str
    name: str
    description: str
    enabled: bool = True
    priority: int = 100  # Niedrigere Zahl = höhere Priorität

    # Bedingungen
    max_amount: Optional[Decimal] = None
    min_entity_relationship_months: Optional[int] = None
    max_risk_score: Optional[int] = None
    document_types: Optional[List[str]] = None
    categories: Optional[List[str]] = None
    entity_types: Optional[List[str]] = None  # "customer", "supplier"

    # Ausschluesse
    excluded_users: Set[str] = field(default_factory=set)
    excluded_companies: Set[str] = field(default_factory=set)
    excluded_document_types: Set[str] = field(default_factory=set)

    # Zeitliche Einschränkungen
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    business_hours_only: bool = False

    # Aktionen
    auto_approve: bool = True
    notify_approvers: bool = True
    create_audit_entry: bool = True


@dataclass
class AutoApprovalResult:
    """Ergebnis der automatischen Genehmigungsprüfung."""

    decision: AutoApprovalDecision
    reasons: List[AutoApprovalReason]
    matched_rules: List[str]
    confidence: float
    explanation: str

    # Bei Auto-Approval
    approval_id: Optional[uuid.UUID] = None
    approved_at: Optional[datetime] = None
    approved_by_rule: Optional[str] = None

    # Bei Eskalation
    escalation_reason: Optional[str] = None
    suggested_approvers: Optional[List[uuid.UUID]] = None

    # Audit
    audit_trail: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AutoApprovalConfig:
    """Globale Konfiguration für Auto-Approval."""

    # Allgemeine Schwellen
    default_max_amount: Decimal = Decimal("500.00")
    default_max_risk_score: int = 30
    default_min_relationship_months: int = 6

    # Trusted Supplier Kriterien
    trusted_supplier_min_documents: int = 5
    trusted_supplier_max_payment_delay_days: int = 7

    # Rate Limits
    max_auto_approvals_per_day: int = 100
    max_auto_approvals_per_hour: int = 20

    # Feature Flags
    enable_amount_based_approval: bool = True
    enable_trusted_supplier_approval: bool = True
    enable_risk_based_approval: bool = True
    enable_recurring_payment_approval: bool = True

    # Opt-out Defaults
    default_opt_out_document_types: Set[str] = field(
        default_factory=lambda: {"contract", "legal", "confidential"}
    )


@dataclass
class EntityTrustScore:
    """Trust-Score für eine Entity (Kunde/Lieferant)."""

    entity_id: uuid.UUID
    trust_score: float  # 0.0 - 1.0
    relationship_months: int
    total_documents: int
    total_invoices: int
    avg_payment_delay_days: float
    risk_score: int
    is_trusted: bool
    trust_factors: Dict[str, float] = field(default_factory=dict)


# ============================================================================
# AutoApprovalService
# ============================================================================


class AutoApprovalService:
    """Service für automatische Genehmigungen mit konfigurierbaren Regeln.

    Workflow:
    1. Dokument/Rechnung wird eingereicht
    2. Service prüft alle aktiven Auto-Approval-Regeln
    3. Bei Match: Automatische Genehmigung mit Audit-Trail
    4. Bei Unsicherheit: Weiterleitung an manuellen Review
    5. Bei Ausschluss: Eskalation an entsprechenden Approver

    Human-in-the-Loop:
    - User können Opt-out konfigurieren
    - Alle Auto-Approvals sind nachvollziehbar
    - Feedback verbessert zukünftige Entscheidungen
    """

    def __init__(
        self,
        db: AsyncSession,
        config: Optional[AutoApprovalConfig] = None,
    ):
        """Initialisiert den Service.

        Args:
            db: Async Database Session
            config: Optionale Konfiguration (sonst Defaults)
        """
        self.db = db
        self.config = config or AutoApprovalConfig()
        self._rules: List[AutoApprovalRule] = []
        self._init_default_rules()

    def _init_default_rules(self) -> None:
        """Initialisiert Standard-Regeln."""
        self._rules = [
            # Regel 1: Kleine Betraege von bekannten Lieferanten
            AutoApprovalRule(
                id="small_amount_known_supplier",
                name="Kleine Betraege bekannter Lieferanten",
                description="Rechnungen unter 500€ von Lieferanten mit >6 Monaten Beziehung",
                priority=10,
                max_amount=self.config.default_max_amount,
                min_entity_relationship_months=self.config.default_min_relationship_months,
                entity_types=["supplier"],
                document_types=["invoice", "recurring_invoice"],
            ),
            # Regel 2: Sehr kleine Betraege (allgemein)
            AutoApprovalRule(
                id="micro_payment",
                name="Micro-Zahlungen",
                description="Betraege unter 50€ werden automatisch genehmigt",
                priority=5,
                max_amount=Decimal("50.00"),
                document_types=["invoice", "expense", "receipt"],
            ),
            # Regel 3: Niedrig-Risiko Entities
            AutoApprovalRule(
                id="low_risk_entity",
                name="Niedrig-Risiko Geschäftspartner",
                description="Dokumente von Entities mit Risiko-Score < 20",
                priority=20,
                max_risk_score=20,
                max_amount=Decimal("1000.00"),
            ),
            # Regel 4: Wiederkehrende Zahlungen
            AutoApprovalRule(
                id="recurring_payment",
                name="Wiederkehrende Zahlungen",
                description="Erkannte wiederkehrende Zahlungen (Miete, Abos)",
                priority=15,
                categories=["recurring", "subscription", "rent", "lease"],
                max_amount=Decimal("2000.00"),
            ),
            # Regel 5: Pre-approved Kategorien
            AutoApprovalRule(
                id="pre_approved_category",
                name="Vorab genehmigte Kategorien",
                description="Bestimmte Kategorien sind vorab genehmigt",
                priority=25,
                categories=["office_supplies", "software_subscription", "utilities"],
                max_amount=Decimal("200.00"),
            ),
        ]

    # ========================================================================
    # Hauptmethoden
    # ========================================================================

    async def check_auto_approval(
        self,
        document_id: Optional[uuid.UUID] = None,
        invoice_id: Optional[uuid.UUID] = None,
        entity_id: Optional[uuid.UUID] = None,
        amount: Optional[Decimal] = None,
        document_type: Optional[str] = None,
        category: Optional[str] = None,
        company_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> AutoApprovalResult:
        """Prüft ob ein Dokument/Rechnung automatisch genehmigt werden kann.

        Args:
            document_id: Optional Dokument-ID
            invoice_id: Optional Rechnungs-ID
            entity_id: Optional Entity-ID (Kunde/Lieferant)
            amount: Betrag (falls bekannt)
            document_type: Dokumenttyp
            category: Kategorie
            company_id: Company-ID für Multi-Tenant
            user_id: User-ID für Opt-out Prüfung

        Returns:
            AutoApprovalResult mit Entscheidung und Begruendung
        """
        context = await self._build_context(
            document_id=document_id,
            invoice_id=invoice_id,
            entity_id=entity_id,
            amount=amount,
            document_type=document_type,
            category=category,
            company_id=company_id,
            user_id=user_id,
        )

        # Opt-out Prüfung
        if await self._is_opted_out(context):
            return AutoApprovalResult(
                decision=AutoApprovalDecision.REQUIRES_REVIEW,
                reasons=[],
                matched_rules=[],
                confidence=0.0,
                explanation="Auto-Approval ist für diesen Kontext deaktiviert (Opt-out)",
                audit_trail={"opted_out": True, "context": context},
            )

        # Rate Limit Prüfung
        if not await self._check_rate_limits(company_id):
            return AutoApprovalResult(
                decision=AutoApprovalDecision.REQUIRES_REVIEW,
                reasons=[],
                matched_rules=[],
                confidence=0.0,
                explanation="Rate Limit für automatische Genehmigungen erreicht",
                audit_trail={"rate_limited": True},
            )

        # Regeln evaluieren
        matched_rules: List[AutoApprovalRule] = []
        approval_reasons: List[AutoApprovalReason] = []
        total_confidence = 0.0

        for rule in sorted(self._rules, key=lambda r: r.priority):
            if not rule.enabled:
                continue

            match_result = await self._evaluate_rule(rule, context)
            if match_result["matches"]:
                matched_rules.append(rule)
                approval_reasons.extend(match_result["reasons"])
                total_confidence = max(total_confidence, match_result["confidence"])

        # Keine passende Regel gefunden
        if not matched_rules:
            return AutoApprovalResult(
                decision=AutoApprovalDecision.REQUIRES_REVIEW,
                reasons=[],
                matched_rules=[],
                confidence=0.0,
                explanation="Keine Auto-Approval-Regel zutreffend - manuelle Prüfung erforderlich",
                audit_trail={"no_matching_rules": True, "context": context},
            )

        # Blockierung prüfen (z.B. excluded document types)
        blocking_rule = await self._check_blocking_rules(context)
        if blocking_rule:
            return AutoApprovalResult(
                decision=AutoApprovalDecision.BLOCKED,
                reasons=[],
                matched_rules=[],
                confidence=0.0,
                explanation=f"Auto-Approval blockiert: {blocking_rule}",
                escalation_reason=blocking_rule,
                audit_trail={"blocked_by": blocking_rule, "context": context},
            )

        # Auto-Approval durchführen
        result = await self._execute_auto_approval(
            context=context,
            matched_rules=matched_rules,
            reasons=approval_reasons,
            confidence=total_confidence,
        )

        logger.info(
            "auto_approval_decision",
            decision=result.decision.value,
            document_id=str(document_id) if document_id else None,
            invoice_id=str(invoice_id) if invoice_id else None,
            matched_rules=[r.id for r in matched_rules],
            confidence=total_confidence,
        )

        return result

    async def apply_auto_approval(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
        company_id: uuid.UUID,
        amount: Optional[Decimal] = None,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[ApprovalRequest]:
        """Wendet Auto-Approval an und erstellt ApprovalRequest.

        Args:
            entity_type: Typ (document, invoice, etc.)
            entity_id: ID der Entität
            company_id: Company-ID
            amount: Optional Betrag
            title: Optional Titel
            metadata: Optional Metadaten

        Returns:
            ApprovalRequest wenn erstellt, sonst None
        """
        # Auto-Approval prüfen
        result = await self.check_auto_approval(
            document_id=entity_id if entity_type == "document" else None,
            invoice_id=entity_id if entity_type == "invoice" else None,
            amount=amount,
            document_type=entity_type,
            company_id=company_id,
        )

        if result.decision != AutoApprovalDecision.AUTO_APPROVED:
            return None

        # ApprovalRequest erstellen (bereits genehmigt)
        approval_request = ApprovalRequest(
            id=uuid.uuid4(),
            company_id=company_id,
            entity_type=entity_type,
            entity_id=entity_id,
            title=title or f"Auto-genehmigt: {entity_type}",
            description=f"Automatisch genehmigt durch Regel: {result.approved_by_rule}",
            amount=amount,
            status=ApprovalStatus.APPROVED,
            priority=ApprovalPriority.LOW,
            request_metadata={
                "auto_approved": True,
                "auto_approval_reasons": [r.value for r in result.reasons],
                "matched_rules": result.matched_rules,
                "confidence": result.confidence,
                **(metadata or {}),
            },
            created_at=utc_now(),
            resolved_at=utc_now(),
        )

        self.db.add(approval_request)

        # Auto-Approval Step erstellen
        approval_step = ApprovalStep(
            id=uuid.uuid4(),
            approval_request_id=approval_request.id,
            step_number=1,
            approver_type="system",
            approver_value="auto_approval_service",
            status=ApprovalStatus.APPROVED,
            is_required=True,
            decision="approved",
            decision_date=utc_now(),
            decision_notes=result.explanation,
        )

        self.db.add(approval_step)
        await self.db.commit()

        logger.info(
            "auto_approval_applied",
            approval_id=str(approval_request.id),
            entity_type=entity_type,
            entity_id=str(entity_id),
            amount=str(amount) if amount else None,
        )

        return approval_request

    # ========================================================================
    # Trust Score Berechnung
    # ========================================================================

    async def calculate_entity_trust_score(
        self,
        entity_id: uuid.UUID,
    ) -> EntityTrustScore:
        """Berechnet den Trust-Score für eine Entity.

        Args:
            entity_id: ID der Entity

        Returns:
            EntityTrustScore mit allen Faktoren
        """
        # Entity laden
        stmt = select(BusinessEntity).where(BusinessEntity.id == entity_id)
        result = await self.db.execute(stmt)
        entity = result.scalar_one_or_none()

        if not entity:
            return EntityTrustScore(
                entity_id=entity_id,
                trust_score=0.0,
                relationship_months=0,
                total_documents=0,
                total_invoices=0,
                avg_payment_delay_days=0.0,
                risk_score=100,
                is_trusted=False,
            )

        # Beziehungsdauer berechnen
        relationship_months = 0
        if entity.created_at:
            delta = utc_now() - entity.created_at
            relationship_months = delta.days // 30

        # Dokument-Count
        doc_stmt = select(func.count(Document.id)).where(
            Document.business_entity_id == entity_id
        )
        doc_result = await self.db.execute(doc_stmt)
        total_documents = doc_result.scalar() or 0

        # Invoice-Count und Payment-Delay
        invoice_stmt = select(InvoiceTracking).where(
            InvoiceTracking.entity_id == entity_id
        )
        invoice_result = await self.db.execute(invoice_stmt)
        invoices = invoice_result.scalars().all()

        total_invoices = len(invoices)
        avg_payment_delay = 0.0

        if invoices:
            paid_invoices = [i for i in invoices if i.paid_at and i.due_date]
            if paid_invoices:
                delays = [
                    (i.paid_at - i.due_date).days
                    for i in paid_invoices
                    if i.paid_at >= i.due_date
                ]
                avg_payment_delay = sum(delays) / len(delays) if delays else 0.0

        # Risk Score (aus Entity oder berechnet)
        risk_score = entity.risk_score if hasattr(entity, "risk_score") and entity.risk_score else 50

        # Trust-Faktoren berechnen
        trust_factors = {
            "relationship_duration": min(1.0, relationship_months / 12),  # Max bei 12 Monaten
            "document_volume": min(1.0, total_documents / 50),  # Max bei 50 Dokumenten
            "invoice_history": min(1.0, total_invoices / 20),  # Max bei 20 Rechnungen
            "payment_behavior": max(0.0, 1.0 - (avg_payment_delay / 30)),  # 0 bei 30+ Tagen Delay
            "risk_score_factor": max(0.0, 1.0 - (risk_score / 100)),  # Invertiert
        }

        # Gewichteter Trust-Score
        weights = {
            "relationship_duration": 0.20,
            "document_volume": 0.15,
            "invoice_history": 0.20,
            "payment_behavior": 0.25,
            "risk_score_factor": 0.20,
        }

        trust_score = sum(
            trust_factors[k] * weights[k] for k in trust_factors
        )

        # Ist trusted?
        is_trusted = (
            trust_score >= 0.7 and
            relationship_months >= self.config.default_min_relationship_months and
            total_documents >= self.config.trusted_supplier_min_documents and
            avg_payment_delay <= self.config.trusted_supplier_max_payment_delay_days
        )

        return EntityTrustScore(
            entity_id=entity_id,
            trust_score=trust_score,
            relationship_months=relationship_months,
            total_documents=total_documents,
            total_invoices=total_invoices,
            avg_payment_delay_days=avg_payment_delay,
            risk_score=risk_score,
            is_trusted=is_trusted,
            trust_factors=trust_factors,
        )

    # ========================================================================
    # Regel-Management
    # ========================================================================

    def add_rule(self, rule: AutoApprovalRule) -> None:
        """Fuegt eine neue Regel hinzu.

        Args:
            rule: Die hinzuzufuegende Regel
        """
        # Prüfen ob Regel mit ID existiert
        existing = next((r for r in self._rules if r.id == rule.id), None)
        if existing:
            self._rules.remove(existing)

        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority)

        logger.info("auto_approval_rule_added", rule_id=rule.id, rule_name=rule.name)

    def remove_rule(self, rule_id: str) -> bool:
        """Entfernt eine Regel.

        Args:
            rule_id: ID der zu entfernenden Regel

        Returns:
            True wenn entfernt, False wenn nicht gefunden
        """
        rule = next((r for r in self._rules if r.id == rule_id), None)
        if rule:
            self._rules.remove(rule)
            logger.info("auto_approval_rule_removed", rule_id=rule_id)
            return True
        return False

    def get_rules(self) -> List[AutoApprovalRule]:
        """Gibt alle konfigurierten Regeln zurück.

        Returns:
            Liste aller Regeln
        """
        return self._rules.copy()

    def enable_rule(self, rule_id: str, enabled: bool = True) -> bool:
        """Aktiviert oder deaktiviert eine Regel.

        Args:
            rule_id: ID der Regel
            enabled: True zum Aktivieren, False zum Deaktivieren

        Returns:
            True wenn erfolgreich, False wenn Regel nicht gefunden
        """
        rule = next((r for r in self._rules if r.id == rule_id), None)
        if rule:
            rule.enabled = enabled
            logger.info(
                "auto_approval_rule_toggled",
                rule_id=rule_id,
                enabled=enabled,
            )
            return True
        return False

    # ========================================================================
    # Opt-out Management
    # ========================================================================

    async def set_user_opt_out(
        self,
        user_id: uuid.UUID,
        opt_out: bool,
        document_types: Optional[List[str]] = None,
    ) -> None:
        """Setzt Opt-out für einen User.

        Args:
            user_id: User-ID
            opt_out: True für Opt-out, False zum Opt-in
            document_types: Optional spezifische Dokumenttypen
        """
        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            logger.warning("user_not_found_for_opt_out", user_id=str(user_id))
            return

        # Preferences aktualisieren
        preferences = user.preferences or {}
        preferences["auto_approval_opt_out"] = opt_out
        if document_types:
            preferences["auto_approval_opt_out_types"] = document_types

        user.preferences = preferences
        await self.db.commit()

        logger.info(
            "auto_approval_opt_out_set",
            user_id=str(user_id),
            opt_out=opt_out,
            document_types=document_types,
        )

    # ========================================================================
    # Hilfsmethoden
    # ========================================================================

    async def _build_context(
        self,
        document_id: Optional[uuid.UUID],
        invoice_id: Optional[uuid.UUID],
        entity_id: Optional[uuid.UUID],
        amount: Optional[Decimal],
        document_type: Optional[str],
        category: Optional[str],
        company_id: Optional[uuid.UUID],
        user_id: Optional[uuid.UUID],
    ) -> Dict[str, Any]:
        """Baut den Kontext für die Regelauswertung.

        Returns:
            Dict mit allen relevanten Informationen
        """
        context: Dict[str, Any] = {
            "document_id": document_id,
            "invoice_id": invoice_id,
            "entity_id": entity_id,
            "amount": amount,
            "document_type": document_type,
            "category": category,
            "company_id": company_id,
            "user_id": user_id,
            "timestamp": utc_now(),
        }

        # Dokument-Details laden
        if document_id:
            stmt = select(Document).where(Document.id == document_id)
            result = await self.db.execute(stmt)
            document = result.scalar_one_or_none()
            if document:
                context["document"] = document
                context["document_type"] = context.get("document_type") or document.document_type
                context["entity_id"] = context.get("entity_id") or document.business_entity_id

        # Invoice-Details laden
        if invoice_id:
            stmt = select(InvoiceTracking).where(InvoiceTracking.id == invoice_id)
            result = await self.db.execute(stmt)
            invoice = result.scalar_one_or_none()
            if invoice:
                context["invoice"] = invoice
                context["amount"] = context.get("amount") or invoice.amount
                context["entity_id"] = context.get("entity_id") or invoice.entity_id

        # Entity Trust Score berechnen
        if context.get("entity_id"):
            context["entity_trust"] = await self.calculate_entity_trust_score(
                context["entity_id"]
            )

        return context

    async def _is_opted_out(self, context: Dict[str, Any]) -> bool:
        """Prüft ob Auto-Approval für diesen Kontext deaktiviert ist.

        Args:
            context: Der Auswertungs-Kontext

        Returns:
            True wenn Opt-out aktiv
        """
        user_id = context.get("user_id")
        document_type = context.get("document_type")

        # Globale Opt-out Dokumenttypen
        if document_type and document_type in self.config.default_opt_out_document_types:
            return True

        # User-spezifisches Opt-out
        if user_id:
            stmt = select(User).where(User.id == user_id)
            result = await self.db.execute(stmt)
            user = result.scalar_one_or_none()

            if user and user.preferences:
                if user.preferences.get("auto_approval_opt_out"):
                    opt_out_types = user.preferences.get("auto_approval_opt_out_types", [])
                    if not opt_out_types or document_type in opt_out_types:
                        return True

        return False

    async def _check_rate_limits(
        self,
        company_id: Optional[uuid.UUID],
    ) -> bool:
        """Prüft ob Rate Limits eingehalten werden.

        Args:
            company_id: Company-ID

        Returns:
            True wenn innerhalb der Limits
        """
        if not company_id:
            return True

        now = utc_now()

        # Stündliches Limit
        hour_ago = now - timedelta(hours=1)
        hourly_stmt = select(func.count(ApprovalRequest.id)).where(
            and_(
                ApprovalRequest.company_id == company_id,
                ApprovalRequest.request_metadata["auto_approved"].as_string() == "true",
                ApprovalRequest.created_at >= hour_ago,
            )
        )
        hourly_result = await self.db.execute(hourly_stmt)
        hourly_count = hourly_result.scalar() or 0

        if hourly_count >= self.config.max_auto_approvals_per_hour:
            logger.warning(
                "auto_approval_hourly_limit_reached",
                company_id=str(company_id),
                count=hourly_count,
            )
            return False

        # Tägliches Limit
        day_ago = now - timedelta(days=1)
        daily_stmt = select(func.count(ApprovalRequest.id)).where(
            and_(
                ApprovalRequest.company_id == company_id,
                ApprovalRequest.request_metadata["auto_approved"].as_string() == "true",
                ApprovalRequest.created_at >= day_ago,
            )
        )
        daily_result = await self.db.execute(daily_stmt)
        daily_count = daily_result.scalar() or 0

        if daily_count >= self.config.max_auto_approvals_per_day:
            logger.warning(
                "auto_approval_daily_limit_reached",
                company_id=str(company_id),
                count=daily_count,
            )
            return False

        return True

    async def _evaluate_rule(
        self,
        rule: AutoApprovalRule,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Evaluiert eine einzelne Regel.

        Args:
            rule: Die zu evaluierende Regel
            context: Der Auswertungs-Kontext

        Returns:
            Dict mit matches, reasons, confidence
        """
        result = {
            "matches": False,
            "reasons": [],
            "confidence": 0.0,
        }

        # Zeitliche Gültigkeit prüfen
        now = utc_now()
        if rule.valid_from and now < rule.valid_from:
            return result
        if rule.valid_until and now > rule.valid_until:
            return result

        # Ausschluesse prüfen
        user_id = context.get("user_id")
        if user_id and str(user_id) in rule.excluded_users:
            return result

        company_id = context.get("company_id")
        if company_id and str(company_id) in rule.excluded_companies:
            return result

        document_type = context.get("document_type")
        if document_type and document_type in rule.excluded_document_types:
            return result

        # Bedingungen prüfen
        conditions_met = 0
        total_conditions = 0

        # Dokumenttyp-Bedingung
        if rule.document_types:
            total_conditions += 1
            if document_type and document_type in rule.document_types:
                conditions_met += 1
            else:
                return result  # Hard requirement

        # Kategorie-Bedingung
        if rule.categories:
            total_conditions += 1
            category = context.get("category")
            if category and category in rule.categories:
                conditions_met += 1
                result["reasons"].append(AutoApprovalReason.PRE_APPROVED_CATEGORY)

        # Betrags-Bedingung
        if rule.max_amount is not None:
            total_conditions += 1
            amount = context.get("amount")
            if amount is not None and Decimal(str(amount)) <= rule.max_amount:
                conditions_met += 1
                result["reasons"].append(AutoApprovalReason.AMOUNT_BELOW_THRESHOLD)
            elif amount is not None:
                return result  # Amount too high

        # Entity-Beziehungs-Bedingung
        if rule.min_entity_relationship_months is not None:
            total_conditions += 1
            entity_trust = context.get("entity_trust")
            if entity_trust and entity_trust.relationship_months >= rule.min_entity_relationship_months:
                conditions_met += 1
                result["reasons"].append(AutoApprovalReason.TRUSTED_SUPPLIER)
            elif entity_trust:
                return result  # Relationship too short

        # Risiko-Score Bedingung
        if rule.max_risk_score is not None:
            total_conditions += 1
            entity_trust = context.get("entity_trust")
            if entity_trust and entity_trust.risk_score <= rule.max_risk_score:
                conditions_met += 1
                result["reasons"].append(AutoApprovalReason.LOW_RISK_SCORE)
            elif entity_trust:
                return result  # Risk too high

        # Entity-Typ Bedingung
        if rule.entity_types:
            total_conditions += 1
            entity_trust = context.get("entity_trust")
            # Für jetzt immer als erfuellt betrachten wenn Entity existiert
            if entity_trust:
                conditions_met += 1

        # Ergebnis berechnen
        if total_conditions > 0 and conditions_met == total_conditions:
            result["matches"] = True
            result["confidence"] = min(0.95, 0.7 + (conditions_met * 0.05))

        return result

    async def _check_blocking_rules(
        self,
        context: Dict[str, Any],
    ) -> Optional[str]:
        """Prüft ob es blockierende Regeln gibt.

        Args:
            context: Der Auswertungs-Kontext

        Returns:
            Blocking-Grund oder None
        """
        document_type = context.get("document_type")

        # Immer manuelle Prüfung für bestimmte Typen
        if document_type in {"contract", "legal", "confidential", "personal"}:
            return f"Dokumenttyp '{document_type}' erfordert manuelle Prüfung"

        # Hoher Betrag
        amount = context.get("amount")
        if amount and Decimal(str(amount)) > Decimal("10000.00"):
            return f"Betrag {amount}€ überschreitet Maximalgrenze für Auto-Approval"

        # Hoher Risk Score
        entity_trust = context.get("entity_trust")
        if entity_trust and entity_trust.risk_score >= 80:
            return f"Entity hat hohen Risiko-Score ({entity_trust.risk_score})"

        return None

    async def _execute_auto_approval(
        self,
        context: Dict[str, Any],
        matched_rules: List[AutoApprovalRule],
        reasons: List[AutoApprovalReason],
        confidence: float,
    ) -> AutoApprovalResult:
        """Führt die Auto-Approval aus.

        Args:
            context: Der Auswertungs-Kontext
            matched_rules: Zutreffende Regeln
            reasons: Gruende für die Genehmigung
            confidence: Konfidenz-Score

        Returns:
            AutoApprovalResult
        """
        # Unique reasons
        unique_reasons = list(set(reasons))
        rule_ids = [r.id for r in matched_rules]
        primary_rule = matched_rules[0].name if matched_rules else "Unknown"

        # Erklärung generieren
        explanation_parts = []
        for reason in unique_reasons:
            if reason == AutoApprovalReason.AMOUNT_BELOW_THRESHOLD:
                amount = context.get("amount")
                explanation_parts.append(f"Betrag ({amount}€) unter Schwellenwert")
            elif reason == AutoApprovalReason.TRUSTED_SUPPLIER:
                entity_trust = context.get("entity_trust")
                if entity_trust:
                    explanation_parts.append(
                        f"Bekannter Lieferant ({entity_trust.relationship_months} Monate Beziehung)"
                    )
            elif reason == AutoApprovalReason.LOW_RISK_SCORE:
                entity_trust = context.get("entity_trust")
                if entity_trust:
                    explanation_parts.append(f"Niedriger Risiko-Score ({entity_trust.risk_score})")
            elif reason == AutoApprovalReason.PRE_APPROVED_CATEGORY:
                category = context.get("category")
                explanation_parts.append(f"Vorab genehmigte Kategorie: {category}")

        explanation = "; ".join(explanation_parts) if explanation_parts else "Automatisch genehmigt"

        return AutoApprovalResult(
            decision=AutoApprovalDecision.AUTO_APPROVED,
            reasons=unique_reasons,
            matched_rules=rule_ids,
            confidence=confidence,
            explanation=explanation,
            approved_at=utc_now(),
            approved_by_rule=primary_rule,
            audit_trail={
                "context": {
                    "document_id": str(context.get("document_id")) if context.get("document_id") else None,
                    "invoice_id": str(context.get("invoice_id")) if context.get("invoice_id") else None,
                    "amount": str(context.get("amount")) if context.get("amount") else None,
                    "document_type": context.get("document_type"),
                },
                "matched_rules": rule_ids,
                "reasons": [r.value for r in unique_reasons],
                "confidence": confidence,
                "timestamp": utc_now().isoformat(),
            },
        )


# ============================================================================
# Factory Function
# ============================================================================


def get_auto_approval_service(
    db: AsyncSession,
    config: Optional[AutoApprovalConfig] = None,
) -> AutoApprovalService:
    """Factory für AutoApprovalService.

    Args:
        db: Async Database Session
        config: Optionale Konfiguration

    Returns:
        AutoApprovalService Instanz
    """
    return AutoApprovalService(db=db, config=config)
