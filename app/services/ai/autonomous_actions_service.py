# -*- coding: utf-8 -*-
"""
AutonomousActionsService - Konkrete autonome KI-Aktionen.

Baut auf AIDecisionService auf und implementiert spezifische autonome Aktionen:
1. Ablageort automatisch bestimmen
2. Kleine Zahlungsfreigaben (<Schwelle)
3. Mahnungen automatisch versenden
4. Offensichtliche Stammdaten-Korrekturen

Human-in-the-Loop Pattern:
- Confidence-basierte Eskalation
- One-Click Bestätigung bei Unsicherheit
- Lernschleife: Bestätigte Entscheidungen trainieren KI
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Awaitable

import structlog
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log
from app.db.models import (
    Document,
    BusinessEntity,
    InvoiceTracking,
    AIDecision,
)

# NOTE: Folder model does not exist in the current schema.
# Document filing functionality is disabled until a proper folder structure is implemented.
# The service will work for entity-based and invoice-related autonomous actions.
Folder = None  # Placeholder - Folder-based filing is disabled
from app.services.ai.decision_service import (
    AIDecisionService,
    DecisionType,
    ConfidenceLevel,
    AIDecisionResult,
    get_ai_decision_service,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# Data Classes
# ============================================================================


class AutonomousAction(str, Enum):
    """Typen von autonomen Aktionen."""

    FILE_DOCUMENT = "file_document"  # Dokument ablegen
    APPROVE_PAYMENT = "approve_payment"  # Zahlung freigeben
    SEND_DUNNING = "send_dunning"  # Mahnung senden
    UPDATE_MASTER_DATA = "update_master_data"  # Stammdaten korrigieren
    ASSIGN_ENTITY = "assign_entity"  # Entity zuweisen
    CLASSIFY_DOCUMENT = "classify_document"  # Dokumenttyp bestimmen


@dataclass
class ActionProposal:
    """Vorschlag für eine autonome Aktion."""

    action_type: AutonomousAction
    target_id: uuid.UUID  # Document-ID, Invoice-ID, etc.
    proposed_value: Dict[str, Any]
    confidence: float
    reasoning: str
    requires_confirmation: bool
    auto_approved: bool = False
    decision_id: Optional[uuid.UUID] = None


@dataclass
class ActionResult:
    """Ergebnis einer ausgeführten Aktion."""

    success: bool
    action_type: AutonomousAction
    target_id: uuid.UUID
    applied_value: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    was_autonomous: bool = False
    decision_id: Optional[uuid.UUID] = None


@dataclass
class AutonomyConfig:
    """Konfiguration für autonome Aktionen.

    Nutzt Settings aus app.core.config für alle Thresholds.
    Kann per create_autonomy_config() mit aktuellen Settings erstellt werden.
    """

    # Confidence Thresholds (aus Settings)
    document_classification_threshold: float = 0.95
    entity_linking_threshold: float = 0.90
    invoice_approval_threshold: float = 0.95
    payment_matching_threshold: float = 0.95
    ocr_correction_threshold: float = 0.90

    # Zahlungsfreigabe
    payment_auto_approve_limit: Decimal = Decimal("5000.00")  # Max EUR
    payment_suggest_limit: Decimal = Decimal("10000.00")  # Vorschlag bis
    auto_approval_enabled: bool = True

    # Mahnungen
    dunning_auto_send_level: int = 1  # Bis Level 1 automatisch
    dunning_min_overdue_days: int = 14  # Min Tage überfällig

    # Stammdaten
    master_data_auto_update_confidence: float = 0.95
    master_data_fields_auto_update: List[str] = None  # None = alle

    # Ablage (filing)
    filing_auto_confidence: float = 0.95
    filing_suggest_confidence: float = 0.80

    # Routing Intelligence
    routing_enabled: bool = True
    routing_min_confidence: float = 0.85

    # Anomalie-Erkennung
    anomaly_detection_enabled: bool = True
    anomaly_alert_threshold: float = 0.75

    # Smart Suggestions
    suggestions_enabled: bool = True
    max_suggestions_per_document: int = 5

    # NLQ (Natural Language Queries)
    nlq_enabled: bool = True
    nlq_max_results: int = 100

    # Audit Logging
    audit_logging_enabled: bool = True

    def __post_init__(self):
        if self.master_data_fields_auto_update is None:
            self.master_data_fields_auto_update = [
                "email",
                "phone",
                "website",
            ]


def create_autonomy_config() -> AutonomyConfig:
    """Erstellt AutonomyConfig aus aktuellen Settings.

    Laedt alle Thresholds und Einstellungen aus app.core.config.
    Fallback auf Defaults wenn Settings nicht verfügbar.

    Returns:
        AutonomyConfig mit aktuellen Settings
    """
    try:
        from app.core.config import settings


        return AutonomyConfig(
            # Confidence Thresholds
            document_classification_threshold=settings.AUTONOMY_DOCUMENT_CLASSIFICATION_THRESHOLD,
            entity_linking_threshold=settings.AUTONOMY_ENTITY_LINKING_THRESHOLD,
            invoice_approval_threshold=settings.AUTONOMY_INVOICE_APPROVAL_THRESHOLD,
            payment_matching_threshold=settings.AUTONOMY_PAYMENT_MATCHING_THRESHOLD,
            ocr_correction_threshold=settings.AUTONOMY_OCR_CORRECTION_THRESHOLD,
            # Zahlungsfreigabe
            payment_auto_approve_limit=Decimal(str(settings.AUTONOMY_AUTO_APPROVAL_MAX_AMOUNT)),
            auto_approval_enabled=settings.AUTONOMY_AUTO_APPROVAL_ENABLED,
            # Routing
            routing_enabled=settings.AUTONOMY_ROUTING_ENABLED,
            routing_min_confidence=settings.AUTONOMY_ROUTING_MIN_CONFIDENCE,
            # Anomalie
            anomaly_detection_enabled=settings.AUTONOMY_ANOMALY_DETECTION_ENABLED,
            anomaly_alert_threshold=settings.AUTONOMY_ANOMALY_ALERT_THRESHOLD,
            # Suggestions
            suggestions_enabled=settings.AUTONOMY_SUGGESTIONS_ENABLED,
            max_suggestions_per_document=settings.AUTONOMY_MAX_SUGGESTIONS_PER_DOCUMENT,
            # NLQ
            nlq_enabled=settings.AUTONOMY_NLQ_ENABLED,
            nlq_max_results=settings.AUTONOMY_NLQ_MAX_RESULTS,
            # Audit
            audit_logging_enabled=settings.AUTONOMY_AUDIT_LOGGING_ENABLED,
            # Filing thresholds (mapped from classification)
            filing_auto_confidence=settings.AUTONOMY_DOCUMENT_CLASSIFICATION_THRESHOLD,
            filing_suggest_confidence=0.80,  # Suggest bei 80%+
        )
    except Exception as e:
        logger.warning(
            "autonomy_config_fallback",
            **safe_error_log(e),
            message="Konnte Settings nicht laden, nutze Defaults",
        )
        return AutonomyConfig()


# ============================================================================
# Autonomous Actions Service
# ============================================================================


class AutonomousActionsService:
    """Service für autonome KI-Aktionen mit Human-in-the-Loop.

    Koordiniert spezifische autonome Aktionen und integriert sie
    mit dem AIDecisionService für Audit-Trail und Self-Learning.

    Die Thresholds werden aus app.core.config.settings geladen.

    Phase 2.1: Integriert Multi-Level Trust System:
    - Level 1 (ASSISTANCE): Alle Aktionen erfordern Bestätigung
    - Level 2 (AUTO_ACCEPT): >90% Confidence, 24h Auto-Accept
    - Level 3 (CONFIDENCE): >95% sofort, 80-95% verzögert (4h)
    - Level 4 (AUTONOMOUS): Volle Autonomie, nur Exceptions
    """

    def __init__(
        self,
        db: AsyncSession,
        config: Optional[AutonomyConfig] = None,
    ):
        """Initialisiert den Service.

        Args:
            db: Async Database Session
            config: Autonomie-Konfiguration (oder aus Settings via create_autonomy_config())
        """
        self.db = db
        # Nutze übergebene Config oder lade aus Settings
        self.config = config or create_autonomy_config()
        self.decision_service = get_ai_decision_service()

        # Trust-Level Service (lazy init)
        self._trust_service = None
        self._delayed_service = None

        logger.debug(
            "autonomous_actions_service_initialized",
            classification_threshold=self.config.document_classification_threshold,
            entity_linking_threshold=self.config.entity_linking_threshold,
            invoice_approval_threshold=self.config.invoice_approval_threshold,
            payment_matching_threshold=self.config.payment_matching_threshold,
            auto_approval_max=float(self.config.payment_auto_approve_limit),
        )

    @property
    def trust_service(self):
        """Lazy-init Trust-Level Service."""
        if self._trust_service is None:
            from app.services.ai.trust_level_service import TrustLevelService
            self._trust_service = TrustLevelService(self.db)
        return self._trust_service

    @property
    def delayed_service(self):
        """Lazy-init Delayed Acceptance Service."""
        if self._delayed_service is None:
            from app.services.ai.delayed_acceptance_service import DelayedAcceptanceService
            self._delayed_service = DelayedAcceptanceService(self.db)
        return self._delayed_service

    async def _notify_autonomous_action(
        self,
        action_type: AutonomousAction,
        target_id: uuid.UUID,
        details: Dict[str, Any],
        company_id: Optional[uuid.UUID] = None,
    ) -> None:
        """Sendet Benachrichtigung nach autonomer Aktion.

        Args:
            action_type: Typ der ausgeführten Aktion
            target_id: Ziel-ID (Invoice, Entity, etc.)
            details: Zusätzliche Details
            company_id: Mandanten-ID
        """
        try:
            from app.services.notification.unified_hub import send_notification
            from app.services.notification.unified_hub import (
                NotificationCategory,
                NotificationSeverity,
            )

            action_labels = {
                AutonomousAction.APPROVE_PAYMENT: "Zahlungsfreigabe",
                AutonomousAction.SEND_DUNNING: "Mahnung",
                AutonomousAction.UPDATE_MASTER_DATA: "Stammdaten-Korrektur",
                AutonomousAction.ASSIGN_ENTITY: "Entity-Zuweisung",
                AutonomousAction.CLASSIFY_DOCUMENT: "Dokument-Klassifikation",
            }
            label = action_labels.get(action_type, str(action_type.value))

            # Lade Admin für Benachrichtigung
            from app.db.models import User
            stmt = (
                select(User)
                .where(User.is_active == True)
                .where(User.is_superuser == True)
                .limit(1)
            )
            result = await self.db.execute(stmt)
            admin = result.scalar_one_or_none()

            if not admin:
                logger.debug(
                    "no_admin_for_notification",
                    action_type=action_type.value,
                    company_id=str(company_id) if company_id else None,
                )
                return

            await send_notification(
                recipient_user_id=admin.id,
                recipient_email=admin.email or "",
                notification_type="autonomous_action",
                title=f"KI-Aktion: {label}",
                message=(
                    f"Das System hat automatisch eine {label} durchgeführt. "
                    f"Details: {details.get('summary', str(target_id))}"
                ),
                category=NotificationCategory.SYSTEM,
                severity=NotificationSeverity.MEDIUM,
                company_id=company_id,
                reference_type=action_type.value,
                reference_id=str(target_id),
                session=self.db,
            )
            logger.info(
                "autonomous_action_notification_sent",
                action_type=action_type.value,
                target_id=str(target_id),
                admin_id=str(admin.id),
            )
        except Exception:
            logger.warning(
                "autonomous_action_notification_failed",
                action_type=action_type.value,
                target_id=str(target_id),
                exc_info=True,
            )

    async def evaluate_action_mode(
        self,
        company_id: uuid.UUID,
        confidence: float,
        action_type: AutonomousAction,
        document_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Evaluiert den Aktions-Modus basierend auf Trust-Level und Confidence.

        Args:
            company_id: Company-ID
            confidence: Confidence-Score der Aktion
            action_type: Typ der Aktion
            document_type: Optional Dokumenttyp

        Returns:
            Dict mit mode, delay_hours, requires_confirmation
        """
        try:
            from app.services.ai.trust_level_service import TrustLevel

            trust_config = await self.trust_service.get_trust_config(
                company_id, document_type
            )

            # Level 1: Immer Bestätigung
            if trust_config.level == TrustLevel.LEVEL_1_ASSISTANCE:
                return {
                    "mode": "confirmation_required",
                    "delay_hours": 0,
                    "requires_confirmation": True,
                    "auto_apply": False,
                    "reason": "Trust-Level erfordert manuelle Bestätigung",
                }

            # Level 2-4: Prüfen ob Confidence ausreicht
            if confidence >= trust_config.immediate_threshold:
                # Sofortige Ausführung
                return {
                    "mode": "immediate",
                    "delay_hours": 0,
                    "requires_confirmation": False,
                    "auto_apply": True,
                    "reason": f"Confidence {confidence:.1%} >= {trust_config.immediate_threshold:.1%}",
                }
            elif confidence >= trust_config.delayed_threshold:
                # Verzögerte Ausführung
                return {
                    "mode": "delayed",
                    "delay_hours": trust_config.delay_hours,
                    "requires_confirmation": False,
                    "auto_apply": True,
                    "reason": f"Confidence {confidence:.1%} in verzoegetrem Bereich, {trust_config.delay_hours}h Wartezeit",
                }
            else:
                # Manuelle Bestätigung
                return {
                    "mode": "confirmation_required",
                    "delay_hours": 0,
                    "requires_confirmation": True,
                    "auto_apply": False,
                    "reason": f"Confidence {confidence:.1%} unter Schwelle {trust_config.delayed_threshold:.1%}",
                }

        except Exception as e:
            logger.warning(
                "evaluate_action_mode_error",
                **safe_error_log(e),
            )
            # Fallback: Bestätigung erfordern
            return {
                "mode": "confirmation_required",
                "delay_hours": 0,
                "requires_confirmation": True,
                "auto_apply": False,
                "reason": "Fallback wegen Fehler",
            }

    async def create_delayed_proposal(
        self,
        company_id: uuid.UUID,
        action_type: AutonomousAction,
        target_id: uuid.UUID,
        proposed_value: Dict[str, Any],
        confidence: float,
        delay_hours: int,
        ai_decision_id: Optional[uuid.UUID] = None,
        reasoning: str = "",
    ) -> uuid.UUID:
        """Erstellt einen verzögerten Vorschlag in der Queue.

        Args:
            company_id: Company-ID
            action_type: Typ der Aktion
            target_id: Ziel-ID
            proposed_value: Vorgeschlagener Wert
            confidence: Confidence-Score
            delay_hours: Verzögerung
            ai_decision_id: Optional AI-Decision Referenz
            reasoning: Begruendung

        Returns:
            Proposal-ID
        """
        from app.services.ai.delayed_acceptance_service import ProposalType

        # Map AutonomousAction to ProposalType
        proposal_type_map = {
            AutonomousAction.FILE_DOCUMENT: ProposalType.FILE_DOCUMENT,
            AutonomousAction.APPROVE_PAYMENT: ProposalType.APPROVE_PAYMENT,
            AutonomousAction.SEND_DUNNING: ProposalType.SEND_DUNNING,
            AutonomousAction.UPDATE_MASTER_DATA: ProposalType.UPDATE_MASTER_DATA,
            AutonomousAction.ASSIGN_ENTITY: ProposalType.ASSIGN_ENTITY,
            AutonomousAction.CLASSIFY_DOCUMENT: ProposalType.CLASSIFY_DOCUMENT,
        }

        proposal_type = proposal_type_map.get(action_type, ProposalType.CLASSIFY_DOCUMENT)

        proposal = await self.delayed_service.create_proposal(
            company_id=company_id,
            proposal_type=proposal_type,
            target_id=target_id,
            proposed_value=proposed_value,
            confidence=confidence,
            delay_hours=delay_hours,
            ai_decision_id=ai_decision_id,
            reasoning=reasoning,
        )

        logger.info(
            "delayed_proposal_created",
            proposal_id=str(proposal.id),
            action_type=action_type.value,
            delay_hours=delay_hours,
            confidence=confidence,
        )

        return proposal.id

    # ========================================================================
    # 1. Ablageort automatisch bestimmen
    # ========================================================================

    async def propose_filing_location(
        self,
        document_id: uuid.UUID,
        company_id: Optional[uuid.UUID] = None,
    ) -> ActionProposal:
        """Schlaegt Ablageort für ein Dokument vor.

        NOTE: Diese Funktion ist deaktiviert, da das Folder-Model nicht existiert.
        Das Feature wird in einer zukünftigen Version implementiert.

        Args:
            document_id: ID des Dokuments
            company_id: Optional Company-ID

        Returns:
            ActionProposal mit "Feature nicht verfügbar" Status
        """
        # Folder-basierte Ablage ist nicht implementiert
        logger.info(
            "propose_filing_location_disabled",
            document_id=str(document_id),
            reason="Folder model not implemented",
        )
        return ActionProposal(
            action_type=AutonomousAction.FILE_DOCUMENT,
            target_id=document_id,
            proposed_value={},
            confidence=0.0,
            reasoning="Automatische Ablage ist derzeit nicht verfügbar (Folder-System nicht implementiert)",
            requires_confirmation=True,
        )

    async def execute_filing(
        self,
        document_id: uuid.UUID,
        folder_id: uuid.UUID,
        decision_id: Optional[uuid.UUID] = None,
        company_id: Optional[uuid.UUID] = None,
    ) -> ActionResult:
        """Führt die Ablage eines Dokuments aus.

        NOTE: Diese Funktion ist deaktiviert, da das Folder-Model nicht existiert.

        Args:
            document_id: ID des Dokuments
            folder_id: Ziel-Folder-ID
            decision_id: Optional AIDecision-ID für Tracking
            company_id: Optional Company-ID für Multi-Tenant Filter

        Returns:
            ActionResult mit Fehler (Feature nicht verfügbar)
        """
        # Folder-basierte Ablage ist nicht implementiert
        logger.info(
            "execute_filing_disabled",
            document_id=str(document_id),
            folder_id=str(folder_id),
            reason="Folder model not implemented",
        )
        return ActionResult(
            success=False,
            action_type=AutonomousAction.FILE_DOCUMENT,
            target_id=document_id,
            error_message="Automatische Ablage ist derzeit nicht verfügbar (Folder-System nicht implementiert)",
        )

    # ========================================================================
    # 2. Kleine Zahlungsfreigaben
    # ========================================================================

    async def propose_payment_approval(
        self,
        invoice_id: uuid.UUID,
        company_id: Optional[uuid.UUID] = None,
    ) -> ActionProposal:
        """Schlaegt Zahlungsfreigabe vor.

        Automatisch genehmigt wenn:
        - Betrag unter Schwelle
        - Lieferant bekannt und vertrauenswuerdig
        - Keine Anomalien erkannt

        Args:
            invoice_id: ID der Rechnung
            company_id: Optional Company-ID

        Returns:
            ActionProposal
        """
        # Multi-Tenant Filter
        stmt = select(InvoiceTracking).where(InvoiceTracking.id == invoice_id)
        if company_id:
            stmt = stmt.where(InvoiceTracking.company_id == company_id)
        result = await self.db.execute(stmt)
        invoice = result.scalar_one_or_none()

        if not invoice:
            return ActionProposal(
                action_type=AutonomousAction.APPROVE_PAYMENT,
                target_id=invoice_id,
                proposed_value={},
                confidence=0.0,
                reasoning="Rechnung nicht gefunden oder kein Zugriff",
                requires_confirmation=True,
            )

        confidence = 0.5  # Basis-Confidence
        reasoning_parts: List[str] = []

        # 1. Betrag prüfen
        amount = Decimal(str(invoice.amount)) if invoice.amount else Decimal("0")

        if amount <= self.config.payment_auto_approve_limit:
            confidence += 0.3
            reasoning_parts.append(f"Betrag {amount} EUR unter Auto-Limit")
        elif amount <= self.config.payment_suggest_limit:
            confidence += 0.15
            reasoning_parts.append(f"Betrag {amount} EUR im Suggest-Bereich")
        else:
            reasoning_parts.append(f"Betrag {amount} EUR über Limit")

        # 2. Entity prüfen
        if invoice.entity_id:
            stmt = select(BusinessEntity).where(
                BusinessEntity.id == invoice.entity_id
            )
            result = await self.db.execute(stmt)
            entity = result.scalar_one_or_none()

            if entity:
                # Prüfen ob Geschäftsbeziehung etabliert
                # (vereinfacht: Entity existiert und hat Dokumente)
                stmt = select(func.count(Document.id)).where(
                    Document.business_entity_id == entity.id
                )
                result = await self.db.execute(stmt)
                doc_count = result.scalar() or 0

                if doc_count >= 5:
                    confidence += 0.2
                    reasoning_parts.append(f"Etablierter Lieferant ({doc_count} Dokumente)")
                elif doc_count >= 1:
                    confidence += 0.1
                    reasoning_parts.append("Bekannter Lieferant")
        else:
            reasoning_parts.append("Unbekannter Lieferant")

        # Auto-Approve Entscheidung
        auto_approved = (
            confidence >= 0.95
            and amount <= self.config.payment_auto_approve_limit
        )
        requires_confirmation = not auto_approved

        # AI Decision erstellen
        decision_result = await self.decision_service.make_decision(
            db=self.db,
            decision_type=DecisionType.ACCOUNTING,
            decision_value={
                "action": AutonomousAction.APPROVE_PAYMENT.value,
                "invoice_id": str(invoice_id),
                "amount": float(amount),
            },
            confidence=confidence,
            document_id=invoice.document_id,
            company_id=company_id,
            explanation={"reasoning": reasoning_parts},
        )

        return ActionProposal(
            action_type=AutonomousAction.APPROVE_PAYMENT,
            target_id=invoice_id,
            proposed_value={"approved": True, "amount": float(amount)},
            confidence=confidence,
            reasoning="; ".join(reasoning_parts),
            requires_confirmation=requires_confirmation,
            auto_approved=auto_approved,
            decision_id=decision_result.decision_id,
        )

    async def execute_payment_approval(
        self,
        invoice_id: uuid.UUID,
        decision_id: Optional[uuid.UUID] = None,
        company_id: Optional[uuid.UUID] = None,
    ) -> ActionResult:
        """Führt Zahlungsfreigabe aus.

        Args:
            invoice_id: ID der Rechnung
            decision_id: Optional AIDecision-ID
            company_id: Optional Company-ID für Multi-Tenant Filter

        Returns:
            ActionResult
        """
        # Multi-Tenant Filter
        stmt = select(InvoiceTracking).where(InvoiceTracking.id == invoice_id)
        if company_id:
            stmt = stmt.where(InvoiceTracking.company_id == company_id)
        result = await self.db.execute(stmt)
        invoice = result.scalar_one_or_none()

        if not invoice:
            return ActionResult(
                success=False,
                action_type=AutonomousAction.APPROVE_PAYMENT,
                target_id=invoice_id,
                error_message="Rechnung nicht gefunden oder kein Zugriff",
            )

        invoice.status = "approved"
        invoice.updated_at = utc_now()
        await self.db.commit()

        amount_str = f"{float(invoice.amount):.2f} EUR" if invoice.amount else "unbekannt"

        logger.info(
            "payment_approved_autonomously",
            invoice_id=str(invoice_id),
            amount=float(invoice.amount) if invoice.amount else 0,
            decision_id=str(decision_id) if decision_id else None,
        )

        # Benachrichtigung senden
        await self._notify_autonomous_action(
            action_type=AutonomousAction.APPROVE_PAYMENT,
            target_id=invoice_id,
            details={"summary": f"Rechnung {invoice_id} ({amount_str}) freigegeben"},
            company_id=company_id,
        )

        return ActionResult(
            success=True,
            action_type=AutonomousAction.APPROVE_PAYMENT,
            target_id=invoice_id,
            applied_value={"status": "approved"},
            was_autonomous=True,
            decision_id=decision_id,
        )

    # ========================================================================
    # 3. Mahnungen automatisch versenden
    # ========================================================================

    async def get_dunning_candidates(
        self,
        company_id: Optional[uuid.UUID] = None,
        limit: int = 50,
    ) -> List[ActionProposal]:
        """Findet Kandidaten für automatische Mahnungen.

        Kriterien:
        - Rechnung überfällig > min_overdue_days
        - Dunning-Level <= auto_send_level
        - Keine kürzliche Zahlung

        Args:
            company_id: Optional Company-ID
            limit: Maximale Anzahl

        Returns:
            Liste von ActionProposals
        """
        today = utc_now().date()
        min_due_date = today - timedelta(days=self.config.dunning_min_overdue_days)

        # KRITISCH: Multi-Tenant Filter - company_id MUSS vorhanden sein!
        if not company_id:
            logger.warning(
                "get_dunning_candidates_missing_company_id",
                message="company_id ist Pflicht für Multi-Tenant Isolation",
            )
            return []

        stmt = (
            select(InvoiceTracking)
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,  # Multi-Tenant!
                    InvoiceTracking.status == "overdue",
                    InvoiceTracking.due_date <= min_due_date,
                    InvoiceTracking.dunning_level <= self.config.dunning_auto_send_level,
                )
            )
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        invoices = result.scalars().all()

        proposals: List[ActionProposal] = []

        for invoice in invoices:
            days_overdue = (today - invoice.due_date).days
            confidence = min(0.95, 0.70 + (days_overdue / 100))  # Mehr Tage = höhere Confidence

            auto_approved = (
                confidence >= 0.90
                and invoice.dunning_level < self.config.dunning_auto_send_level
            )

            proposals.append(
                ActionProposal(
                    action_type=AutonomousAction.SEND_DUNNING,
                    target_id=invoice.id,
                    proposed_value={
                        "current_level": invoice.dunning_level,
                        "new_level": invoice.dunning_level + 1,
                        "days_overdue": days_overdue,
                    },
                    confidence=confidence,
                    reasoning=f"{days_overdue} Tage überfällig, Mahnstufe {invoice.dunning_level}",
                    requires_confirmation=not auto_approved,
                    auto_approved=auto_approved,
                )
            )

        return proposals

    async def execute_dunning(
        self,
        invoice_id: uuid.UUID,
        decision_id: Optional[uuid.UUID] = None,
        company_id: Optional[uuid.UUID] = None,
    ) -> ActionResult:
        """Führt Mahnungsstufen-Erhöhung aus.

        Args:
            invoice_id: ID der Rechnung
            decision_id: Optional AIDecision-ID
            company_id: Optional Company-ID für Multi-Tenant Filter

        Returns:
            ActionResult
        """
        # Multi-Tenant Filter
        stmt = select(InvoiceTracking).where(InvoiceTracking.id == invoice_id)
        if company_id:
            stmt = stmt.where(InvoiceTracking.company_id == company_id)
        result = await self.db.execute(stmt)
        invoice = result.scalar_one_or_none()

        if not invoice:
            return ActionResult(
                success=False,
                action_type=AutonomousAction.SEND_DUNNING,
                target_id=invoice_id,
                error_message="Rechnung nicht gefunden oder kein Zugriff",
            )

        old_level = invoice.dunning_level or 0
        new_level = min(old_level + 1, 4)  # Max Level 4

        invoice.dunning_level = new_level
        invoice.last_dunning_date = utc_now().date()
        invoice.updated_at = utc_now()
        await self.db.commit()

        logger.info(
            "dunning_sent_autonomously",
            invoice_id=str(invoice_id),
            old_level=old_level,
            new_level=new_level,
            decision_id=str(decision_id) if decision_id else None,
        )

        # Mahnbrief generieren wenn DunningRecord vorhanden
        try:
            from app.db.models import DunningRecord
            from app.services.banking.dunning_letter_service import DunningLetterService

            dr_stmt = select(DunningRecord).where(
                DunningRecord.document_id == invoice.document_id
            )
            dr_result = await self.db.execute(dr_stmt)
            dunning_record = dr_result.scalar_one_or_none()

            if dunning_record:
                dunning_record.dunning_level = new_level
                dunning_record.status = "active"
                await self.db.commit()

                letter_service = DunningLetterService()
                letter_bytes = await letter_service.generate_letter(
                    db=self.db,
                    dunning_record_id=dunning_record.id,
                    dunning_level=new_level,
                    is_b2b=getattr(dunning_record, "is_b2b", True),
                )
                logger.info(
                    "dunning_letter_generated",
                    invoice_id=str(invoice_id),
                    dunning_record_id=str(dunning_record.id),
                    level=new_level,
                    size_bytes=len(letter_bytes),
                )
        except Exception:
            logger.warning(
                "dunning_letter_generation_skipped",
                invoice_id=str(invoice_id),
                exc_info=True,
            )

        # Benachrichtigung senden
        await self._notify_autonomous_action(
            action_type=AutonomousAction.SEND_DUNNING,
            target_id=invoice_id,
            details={
                "summary": f"Mahnstufe {old_level} -> {new_level} für Rechnung {invoice_id}",
            },
            company_id=company_id,
        )

        return ActionResult(
            success=True,
            action_type=AutonomousAction.SEND_DUNNING,
            target_id=invoice_id,
            applied_value={
                "old_level": old_level,
                "new_level": new_level,
            },
            was_autonomous=True,
            decision_id=decision_id,
        )

    # ========================================================================
    # 4. Stammdaten-Korrekturen
    # ========================================================================

    async def propose_master_data_update(
        self,
        entity_id: uuid.UUID,
        field: str,
        new_value: str,
        source: str,
        confidence: float,
        company_id: Optional[uuid.UUID] = None,
    ) -> ActionProposal:
        """Schlaegt Stammdaten-Korrektur vor.

        Args:
            entity_id: ID der Entity
            field: Feldname (z.B. "email", "phone")
            new_value: Neuer Wert
            source: Quelle der Änderung (z.B. "document_ocr")
            confidence: Confidence des neuen Werts
            company_id: Optional Company-ID

        Returns:
            ActionProposal
        """
        stmt = select(BusinessEntity).where(BusinessEntity.id == entity_id)
        result = await self.db.execute(stmt)
        entity = result.scalar_one_or_none()

        if not entity:
            return ActionProposal(
                action_type=AutonomousAction.UPDATE_MASTER_DATA,
                target_id=entity_id,
                proposed_value={},
                confidence=0.0,
                reasoning="Entity nicht gefunden",
                requires_confirmation=True,
            )

        current_value = getattr(entity, field, None)

        # Prüfen ob Änderung sinnvoll
        if current_value == new_value:
            return ActionProposal(
                action_type=AutonomousAction.UPDATE_MASTER_DATA,
                target_id=entity_id,
                proposed_value={},
                confidence=0.0,
                reasoning="Wert ist bereits aktuell",
                requires_confirmation=False,
            )

        reasoning_parts = [f"Neuer Wert '{new_value}' aus {source}"]

        if current_value:
            reasoning_parts.append(f"Aktueller Wert: '{current_value}'")

        # Auto-Update wenn:
        # - Feld in Auto-Update-Liste
        # - Confidence hoch genug
        # - Aktueller Wert leer
        auto_approved = (
            field in self.config.master_data_fields_auto_update
            and confidence >= self.config.master_data_auto_update_confidence
            and not current_value
        )

        # AI Decision erstellen
        decision_result = await self.decision_service.make_decision(
            db=self.db,
            decision_type=DecisionType.MATCHING,
            decision_value={
                "action": AutonomousAction.UPDATE_MASTER_DATA.value,
                "entity_id": str(entity_id),
                "field": field,
                "old_value": current_value,
                "new_value": new_value,
            },
            confidence=confidence,
            company_id=company_id,
            explanation={
                "source": source,
                "reasoning": reasoning_parts,
            },
        )

        return ActionProposal(
            action_type=AutonomousAction.UPDATE_MASTER_DATA,
            target_id=entity_id,
            proposed_value={
                "field": field,
                "old_value": current_value,
                "new_value": new_value,
            },
            confidence=confidence,
            reasoning="; ".join(reasoning_parts),
            requires_confirmation=not auto_approved,
            auto_approved=auto_approved,
            decision_id=decision_result.decision_id,
        )

    async def execute_master_data_update(
        self,
        entity_id: uuid.UUID,
        field: str,
        new_value: str,
        decision_id: Optional[uuid.UUID] = None,
        company_id: Optional[uuid.UUID] = None,
    ) -> ActionResult:
        """Führt Stammdaten-Update aus.

        Args:
            entity_id: ID der Entity
            field: Feldname
            new_value: Neuer Wert
            decision_id: Optional AIDecision-ID
            company_id: Optional Company-ID für Multi-Tenant Filter

        Returns:
            ActionResult
        """
        # Multi-Tenant Filter
        stmt = select(BusinessEntity).where(BusinessEntity.id == entity_id)
        if company_id:
            stmt = stmt.where(BusinessEntity.company_id == company_id)
        result = await self.db.execute(stmt)
        entity = result.scalar_one_or_none()

        if not entity:
            return ActionResult(
                success=False,
                action_type=AutonomousAction.UPDATE_MASTER_DATA,
                target_id=entity_id,
                error_message="Entity nicht gefunden oder kein Zugriff",
            )

        # Nur erlaubte Felder updaten
        allowed_fields = ["email", "phone", "website", "address", "city", "postal_code"]
        if field not in allowed_fields:
            return ActionResult(
                success=False,
                action_type=AutonomousAction.UPDATE_MASTER_DATA,
                target_id=entity_id,
                error_message=f"Feld '{field}' nicht für Auto-Update erlaubt",
            )

        old_value = getattr(entity, field, None)
        setattr(entity, field, new_value)
        entity.updated_at = utc_now()
        await self.db.commit()

        logger.info(
            "master_data_updated_autonomously",
            entity_id=str(entity_id),
            field=field,
            had_old_value=old_value is not None,
            decision_id=str(decision_id) if decision_id else None,
            # SECURITY: old_value und new_value nicht loggen (PII)
        )

        return ActionResult(
            success=True,
            action_type=AutonomousAction.UPDATE_MASTER_DATA,
            target_id=entity_id,
            applied_value={
                "field": field,
                "updated": True,
            },
            was_autonomous=True,
            decision_id=decision_id,
        )

    # ========================================================================
    # Private Helpers
    # ========================================================================

    async def _find_folder_by_document_type(
        self,
        document_type: str,
        company_id: Optional[uuid.UUID],
    ) -> None:
        """Findet Standard-Folder für Dokumenttyp.

        NOTE: Deaktiviert - Folder-Model nicht implementiert.
        """
        # Folder-System nicht verfügbar
        return None

    async def _find_folder_by_history(
        self,
        document: Document,
        company_id: Optional[uuid.UUID],
    ) -> tuple[None, float]:
        """Findet Folder basierend auf historischer Ablage.

        NOTE: Deaktiviert - Folder-Model nicht implementiert.
        """
        # Folder-System nicht verfügbar
        return None, 0.0


# ============================================================================
# Factory Function
# ============================================================================


async def get_autonomous_actions_service(
    db: AsyncSession,
    config: Optional[AutonomyConfig] = None,
) -> AutonomousActionsService:
    """Factory-Funktion für AutonomousActionsService.

    Args:
        db: Async Database Session
        config: Optional Autonomie-Konfiguration

    Returns:
        Konfigurierter AutonomousActionsService
    """
    return AutonomousActionsService(db=db, config=config)
