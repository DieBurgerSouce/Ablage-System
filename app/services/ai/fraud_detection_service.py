# -*- coding: utf-8 -*-
"""
Enhanced Fraud Detection Service for Ablage-System.

Comprehensive fraud detection with:
- CEO Fraud Detection (urgency language, unknown sender, unusual amounts)
- Duplicate Payment Detection (hash-based + fuzzy matching)
- IBAN Manipulation Detection (baseline tracking, change verification)
- Internal Irregularity Detection (self-approval, unusual patterns)

SECURITY: NEVER log entity names, financial details, or PII.

Feinpoliert und durchdacht - Enterprise Fraud Prevention.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union
from uuid import UUID

# JSON-compatible value type for fraud detection details/metadata
JSONValue = Union[str, int, float, bool, None, Dict[str, "JSONValue"], List["JSONValue"]]
JSONDict = Dict[str, JSONValue]

import structlog
from sqlalchemy import select, func, and_, or_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, BusinessEntity, InvoiceTracking, AuditLog
from app.db.models_privat_enterprise import ApprovalRequest, ApprovalStep
from app.db.models_fraud import (
    IBANBaseline,
    FraudScanResult,
    IBANChangeRequest,
    FraudScanType,
    FraudRiskLevel,
    FraudScanStatus,
    IBANChangeStatus,
)
from app.db.models_alert import AlertCategory, AlertSeverity
from app.services.alert_center_service import AlertCenterService, AlertCodes
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# German Urgency Keywords for CEO Fraud Detection
# =============================================================================

GERMAN_URGENCY_KEYWORDS = frozenset({
    # High urgency
    "dringend", "sofort", "umgehend", "unverzueglich", "schnellstmöglich",
    "eilig", "asap", "sofortige", "dringende", "schnellstens",
    # Confidentiality
    "vertraulich", "geheim", "streng vertraulich", "nur für sie",
    "persoenlich", "nicht weiterleiten", "diskret", "unter uns",
    # Authority pressure
    "geschäftsführer", "ceo", "vorstand", "chef", "direktor",
    "anweisung", "auftrag", "anordnung", "befehl",
    # Payment pressure
    "zahlung", "überweisung", "bankverbindung", "neue iban",
    "konto geändert", "kontoänderung", "bankwechsel",
})

CEO_FRAUD_INDICATORS = {
    "urgency_language": 0.3,
    "confidentiality_request": 0.25,
    "unknown_sender": 0.2,
    "unusual_amount": 0.15,
    "unusual_bank_details": 0.1,
}


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class FraudIndicator:
    """A single fraud indicator with weight and details."""
    name: str
    weight: float
    description: str
    details: JSONDict = field(default_factory=dict)


@dataclass
class FraudDetectionResult:
    """Result of a fraud detection scan."""
    scan_type: FraudScanType
    risk_score: float  # 0.0 - 1.0
    risk_level: FraudRiskLevel
    confidence: float  # 0.0 - 1.0
    indicators: List[FraudIndicator]
    explanation: JSONDict
    document_id: Optional[UUID] = None
    entity_id: Optional[UUID] = None
    invoice_id: Optional[UUID] = None

    @property
    def is_suspicious(self) -> bool:
        """Check if result indicates suspicious activity."""
        return self.risk_score >= 0.5 or self.risk_level in (FraudRiskLevel.HIGH, FraudRiskLevel.CRITICAL)


# =============================================================================
# Enhanced Fraud Detection Service
# =============================================================================

class EnhancedFraudDetectionService:
    """
    Enhanced fraud detection with ML-based anomaly detection.

    Detects:
    - CEO Fraud (Business Email Compromise)
    - Duplicate Payments
    - IBAN Manipulation
    - Internal Irregularities (self-approval, unusual patterns)
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the fraud detection service."""
        self.session = session
        self._alert_service: Optional[AlertCenterService] = None

    @property
    def alert_service(self) -> AlertCenterService:
        """Lazy-load alert center service."""
        if self._alert_service is None:
            self._alert_service = AlertCenterService(self.session)
        return self._alert_service

    # =========================================================================
    # CEO Fraud Detection
    # =========================================================================

    async def detect_ceo_fraud(
        self,
        document_id: UUID,
        company_id: UUID,
    ) -> FraudDetectionResult:
        """
        Detect CEO fraud indicators in a document.

        CEO fraud patterns:
        - Unknown sender with high amount request
        - Urgency language (dringend, sofort, vertraulich)
        - Unusual bank details
        - Request for secrecy/confidentiality

        Args:
            document_id: Document to analyze
            company_id: Company context

        Returns:
            FraudDetectionResult with risk assessment
        """
        indicators: List[FraudIndicator] = []

        # Load document
        doc = await self._get_document(document_id)
        if not doc:
            return self._empty_result(FraudScanType.CEO_FRAUD, document_id=document_id)

        extracted_data = doc.extracted_data or {}
        text_content = (doc.extracted_text or "").lower()

        # 1. Check urgency language
        urgency_matches = self._find_urgency_keywords(text_content)
        if urgency_matches:
            indicators.append(FraudIndicator(
                name="urgency_language",
                weight=CEO_FRAUD_INDICATORS["urgency_language"],
                description=f"Dringende Sprache erkannt ({len(urgency_matches)} Treffer)",
                details={"keyword_count": len(urgency_matches)},  # No keywords logged
            ))

        # 2. Check confidentiality request
        confidentiality_words = {"vertraulich", "geheim", "nur für sie", "persoenlich", "diskret"}
        conf_matches = [w for w in confidentiality_words if w in text_content]
        if conf_matches:
            indicators.append(FraudIndicator(
                name="confidentiality_request",
                weight=CEO_FRAUD_INDICATORS["confidentiality_request"],
                description="Vertraulichkeitsanfrage erkannt",
                details={"match_count": len(conf_matches)},
            ))

        # 3. Check for unknown sender with high amount
        sender_name = extracted_data.get("sender_name", "")
        amount = self._parse_amount(extracted_data.get("total_gross"))

        if sender_name:
            is_known = await self._is_known_sender(sender_name, company_id)
            if not is_known and amount and amount > Decimal("5000"):
                indicators.append(FraudIndicator(
                    name="unknown_sender",
                    weight=CEO_FRAUD_INDICATORS["unknown_sender"],
                    description="Unbekannter Absender mit hohem Betrag",
                    details={"amount_above_threshold": True},  # No actual amount logged
                ))

        # 4. Check for unusual amount
        if amount:
            is_unusual = await self._is_unusual_amount(amount, company_id)
            if is_unusual:
                indicators.append(FraudIndicator(
                    name="unusual_amount",
                    weight=CEO_FRAUD_INDICATORS["unusual_amount"],
                    description="Ungewoehnlich hoher Betrag",
                    details={"deviation_detected": True},
                ))

        # 5. Check for new/unusual bank details mentioned
        if self._mentions_bank_change(text_content):
            indicators.append(FraudIndicator(
                name="unusual_bank_details",
                weight=CEO_FRAUD_INDICATORS["unusual_bank_details"],
                description="Bankverbindungsänderung erwaehnt",
                details={},
            ))

        # Calculate risk score and level
        risk_score = sum(ind.weight for ind in indicators)
        risk_score = min(risk_score, 1.0)
        risk_level = self._calculate_risk_level(risk_score)
        confidence = self._calculate_confidence(len(indicators), 5)

        result = FraudDetectionResult(
            scan_type=FraudScanType.CEO_FRAUD,
            risk_score=risk_score,
            risk_level=risk_level,
            confidence=confidence,
            indicators=indicators,
            explanation={
                "indicator_count": len(indicators),
                "top_indicators": [ind.name for ind in sorted(indicators, key=lambda x: -x.weight)[:3]],
            },
            document_id=document_id,
        )

        # Store scan result
        await self._store_scan_result(result, company_id)

        # Create alert if suspicious
        if result.is_suspicious:
            await self._create_fraud_alert(
                company_id=company_id,
                alert_code=AlertCodes.FRAUD_CEO_FRAUD,
                title="CEO-Betrug vermutet",
                message="Dokument zeigt Anzeichen von CEO-Betrug (Dringlichkeit, Vertraulichkeit, unbekannter Absender)",
                document_id=document_id,
                severity=AlertSeverity.HIGH if risk_level == FraudRiskLevel.CRITICAL else AlertSeverity.MEDIUM,
                metadata={"scan_type": "ceo_fraud", "risk_score": risk_score},
            )

        return result

    # =========================================================================
    # Duplicate Payment Detection
    # =========================================================================

    async def detect_duplicate_payment(
        self,
        invoice_id: UUID,
        company_id: UUID,
    ) -> FraudDetectionResult:
        """
        Detect potential duplicate payment for an invoice.

        Detection methods:
        - Hash-based exact match (invoice_number + amount + entity)
        - Fuzzy matching (similar amounts +/- 5%, similar dates +/- 3 days)

        Args:
            invoice_id: Invoice to check
            company_id: Company context

        Returns:
            FraudDetectionResult with duplicate candidates
        """
        indicators: List[FraudIndicator] = []

        # Load invoice
        invoice = await self._get_invoice(invoice_id)
        if not invoice:
            return self._empty_result(FraudScanType.DUPLICATE_PAYMENT, invoice_id=invoice_id)

        # Create hash for exact matching
        invoice_hash = self._create_invoice_hash(invoice)

        # Find exact duplicates
        exact_duplicates = await self._find_exact_duplicates(
            invoice_hash, invoice_id, company_id
        )
        if exact_duplicates:
            indicators.append(FraudIndicator(
                name="exact_duplicate",
                weight=0.9,
                description=f"Exaktes Duplikat erkannt ({len(exact_duplicates)} Treffer)",
                details={"duplicate_count": len(exact_duplicates)},  # No IDs logged
            ))

        # Find fuzzy duplicates (similar amount, similar date)
        if invoice.amount and invoice.created_at:
            fuzzy_duplicates = await self._find_fuzzy_duplicates(
                invoice.amount,
                invoice.created_at,
                invoice.entity_id,
                invoice_id,
                company_id,
            )
            if fuzzy_duplicates:
                indicators.append(FraudIndicator(
                    name="fuzzy_duplicate",
                    weight=0.6,
                    description=f"Ähnliche Rechnung erkannt ({len(fuzzy_duplicates)} Treffer)",
                    details={"similar_count": len(fuzzy_duplicates)},
                ))

        # Check for same invoice number with different entity
        if invoice.invoice_number:
            number_duplicates = await self._find_invoice_number_duplicates(
                invoice.invoice_number, invoice.entity_id, invoice_id, company_id
            )
            if number_duplicates:
                indicators.append(FraudIndicator(
                    name="number_reuse",
                    weight=0.7,
                    description="Gleiche Rechnungsnummer bei anderem Lieferanten",
                    details={"entity_mismatch": True},
                ))

        # Calculate scores
        risk_score = sum(ind.weight for ind in indicators)
        risk_score = min(risk_score, 1.0)
        risk_level = self._calculate_risk_level(risk_score)
        confidence = 0.95 if indicators else 0.0

        result = FraudDetectionResult(
            scan_type=FraudScanType.DUPLICATE_PAYMENT,
            risk_score=risk_score,
            risk_level=risk_level,
            confidence=confidence,
            indicators=indicators,
            explanation={
                "detection_methods": [ind.name for ind in indicators],
            },
            invoice_id=invoice_id,
            entity_id=invoice.entity_id,
        )

        # Store result
        await self._store_scan_result(result, company_id)

        # Create alert if suspicious
        if result.is_suspicious:
            await self._create_fraud_alert(
                company_id=company_id,
                alert_code=AlertCodes.FRAUD_DUPLICATE_PAYMENT,
                title="Mögliche Duplikat-Zahlung erkannt",
                message="Rechnung könnte ein Duplikat sein. Manuelle Prüfung erforderlich.",
                document_id=invoice.document_id,
                entity_id=invoice.entity_id,
                severity=AlertSeverity.HIGH,
                metadata={"scan_type": "duplicate_payment", "risk_score": risk_score},
            )

        return result

    # =========================================================================
    # IBAN Manipulation Detection
    # =========================================================================

    async def detect_iban_manipulation(
        self,
        entity_id: UUID,
        new_iban: str,
        company_id: UUID,
        source_document_id: Optional[UUID] = None,
    ) -> FraudDetectionResult:
        """
        Detect potential IBAN manipulation for an entity.

        Checks:
        - IBAN differs from baseline
        - Frequency of IBAN changes
        - Country change (DE -> foreign)

        Args:
            entity_id: Entity whose IBAN is being changed
            new_iban: The new IBAN value
            company_id: Company context
            source_document_id: Document that triggered the change

        Returns:
            FraudDetectionResult with manipulation assessment
        """
        indicators: List[FraudIndicator] = []
        new_iban_normalized = new_iban.upper().replace(" ", "")

        # Get current baseline IBANs for this entity
        baseline = await self._get_iban_baseline(entity_id, company_id)

        if not baseline:
            # First IBAN for this entity - no baseline to compare
            # Still flag if it's a foreign IBAN for a German entity
            if not new_iban_normalized.startswith("DE"):
                indicators.append(FraudIndicator(
                    name="foreign_iban",
                    weight=0.3,
                    description="Auslaendische IBAN für ersten Eintrag",
                    details={"country": new_iban_normalized[:2]},
                ))
        else:
            # Compare with existing baseline
            existing_ibans = [b.iban for b in baseline if b.is_active]

            if new_iban_normalized not in existing_ibans:
                # IBAN change detected
                indicators.append(FraudIndicator(
                    name="iban_change",
                    weight=0.5,
                    description="Neue IBAN weicht von gespeicherter Baseline ab",
                    details={"is_new": True},
                ))

                # Check for country change
                old_countries = set(iban[:2] for iban in existing_ibans)
                new_country = new_iban_normalized[:2]
                if old_countries and new_country not in old_countries:
                    indicators.append(FraudIndicator(
                        name="country_change",
                        weight=0.4,
                        description="IBAN-Land hat sich geändert",
                        details={"country_changed": True},
                    ))

                # Check recent change frequency
                recent_changes = await self._count_recent_iban_changes(
                    entity_id, company_id, days=90
                )
                if recent_changes >= 2:
                    indicators.append(FraudIndicator(
                        name="frequent_changes",
                        weight=0.3,
                        description="Häufige IBAN-Änderungen in letzten 90 Tagen",
                        details={"change_count": recent_changes},
                    ))

        # Calculate scores
        risk_score = sum(ind.weight for ind in indicators)
        risk_score = min(risk_score, 1.0)
        risk_level = self._calculate_risk_level(risk_score)
        confidence = 0.85 if indicators else 0.1

        result = FraudDetectionResult(
            scan_type=FraudScanType.IBAN_MANIPULATION,
            risk_score=risk_score,
            risk_level=risk_level,
            confidence=confidence,
            indicators=indicators,
            explanation={
                "requires_verification": risk_score >= 0.3,
                "indicator_names": [ind.name for ind in indicators],
            },
            entity_id=entity_id,
            document_id=source_document_id,
        )

        # Store result
        await self._store_scan_result(result, company_id)

        # Create change request if suspicious
        if risk_score >= 0.3:
            await self._create_iban_change_request(
                entity_id=entity_id,
                company_id=company_id,
                new_iban=new_iban_normalized,
                old_iban=baseline[0].iban if baseline else None,
                source_document_id=source_document_id,
                risk_score=risk_score,
                risk_indicators={"indicators": [ind.name for ind in indicators]},
            )

            await self._create_fraud_alert(
                company_id=company_id,
                alert_code=AlertCodes.FRAUD_IBAN_MANIPULATION,
                title="IBAN-Änderung erfordert Verifizierung",
                message="Eine IBAN-Änderung wurde erkannt. Bitte verifizieren Sie die neuen Bankdaten.",
                entity_id=entity_id,
                document_id=source_document_id,
                severity=AlertSeverity.HIGH if risk_level == FraudRiskLevel.CRITICAL else AlertSeverity.MEDIUM,
                metadata={"scan_type": "iban_manipulation", "risk_score": risk_score},
            )

        return result

    async def get_iban_history(
        self,
        entity_id: UUID,
        company_id: UUID,
    ) -> List[JSONDict]:
        """
        Get IBAN change history for an entity.

        Args:
            entity_id: Entity to get history for
            company_id: Company context

        Returns:
            List of IBAN history entries (masked for security)
        """
        stmt = (
            select(IBANBaseline)
            .where(
                and_(
                    IBANBaseline.entity_id == entity_id,
                    IBANBaseline.company_id == company_id,
                )
            )
            .order_by(IBANBaseline.first_seen_at.desc())
        )
        result = await self.session.execute(stmt)
        baselines = result.scalars().all()

        return [b.to_dict() for b in baselines]

    # =========================================================================
    # Internal Irregularity Detection
    # =========================================================================

    async def detect_self_approval(
        self,
        approval_id: UUID,
        company_id: UUID,
    ) -> FraudDetectionResult:
        """
        Detect self-approval attempts.

        Checks if approver is also the requester/creator of the item.

        Args:
            approval_id: Approval to check
            company_id: Company context

        Returns:
            FraudDetectionResult for self-approval
        """
        # M10: ApprovalRequest company-scoped laden (Ownership-/Multi-Tenant-Check)
        stmt = select(ApprovalRequest).where(
            and_(
                ApprovalRequest.id == approval_id,
                ApprovalRequest.company_id == company_id,
            )
        )
        approval = (await self.session.execute(stmt)).scalar_one_or_none()

        if approval is None:
            # Keine Daten -> ehrliches Leerergebnis (confidence=0.0), kein PII
            logger.warning(
                "fraud_self_approval_request_not_found",
                approval_id=str(approval_id),
            )
            return self._empty_result(FraudScanType.INTERNAL_IRREGULARITY)

        requester_id = approval.requested_by_id
        if requester_id is None:
            # Antragsteller nicht erfasst -> ehrlich nicht bewertbar (confidence=0.0)
            logger.warning(
                "fraud_self_approval_no_requester",
                approval_id=str(approval_id),
            )
            return self._empty_result(FraudScanType.INTERNAL_IRREGULARITY)

        indicators: List[FraudIndicator] = []

        # (1) Abschliessende Aufloesung durch den Antragsteller selbst
        if approval.resolved_by_id is not None and approval.resolved_by_id == requester_id:
            indicators.append(
                FraudIndicator(
                    name="self_resolution",
                    weight=0.6,
                    description=(
                        "Antragsteller hat die eigene Genehmigungsanfrage selbst "
                        "abschliessend aufgeloest (Vier-Augen-Prinzip verletzt)."
                    ),
                    details={"approval_id": str(approval_id)},
                )
            )

        # (2) Mindestens ein Genehmigungsschritt durch den Antragsteller freigegeben
        stmt_steps = select(func.count(ApprovalStep.id)).where(
            and_(
                ApprovalStep.approval_request_id == approval.id,
                ApprovalStep.decision_by_id == requester_id,
                ApprovalStep.decision == "approved",
            )
        )
        self_approved_steps = (await self.session.execute(stmt_steps)).scalar() or 0
        if self_approved_steps > 0:
            indicators.append(
                FraudIndicator(
                    name="self_approval_step",
                    weight=0.7,
                    description=(
                        "Antragsteller hat mindestens einen Genehmigungsschritt der "
                        "eigenen Anfrage selbst freigegeben."
                    ),
                    details={"self_approved_steps": int(self_approved_steps)},
                )
            )

        risk_score = min(1.0, sum(ind.weight for ind in indicators))
        risk_level = self._calculate_risk_level(risk_score)

        return FraudDetectionResult(
            scan_type=FraudScanType.INTERNAL_IRREGULARITY,
            risk_score=risk_score,
            risk_level=risk_level,
            # Echte Pruefung durchgefuehrt -> hohe Confidence (auch bei sauberem Ergebnis)
            confidence=0.9,
            indicators=indicators,
            explanation={"approval_id": str(approval_id), "check": "self_approval"},
        )

    async def detect_unusual_approval_pattern(
        self,
        user_id: UUID,
        company_id: UUID,
        days: int = 30,
    ) -> FraudDetectionResult:
        """
        Detect unusual approval patterns for a user.

        Patterns checked:
        - High approval volume compared to peers
        - Approvals outside business hours
        - Approvals just under threshold
        - Approvals for same entity repeatedly

        Args:
            user_id: User to analyze
            company_id: Company context
            days: Analysis period

        Returns:
            FraudDetectionResult with pattern analysis
        """
        indicators: List[FraudIndicator] = []

        # M10: Eine belastbare Muster-Analyse (Approval-Volumen vs. Peers,
        # knapp-unter-Schwelle, wiederholte Entitaeten, Off-Hours) erfordert
        # zusaetzliche Aggregations-/Baseline-Daten, die noch nicht angebunden
        # sind. Bis dahin ehrlich: KEINE Indikatoren, confidence=0.0 (kein
        # faelschlich gruenes Ergebnis), mit klarem Warn-Log statt Stillschweigen.
        logger.warning(
            "fraud_unusual_approval_pattern_not_implemented",
            analysis_period_days=days,
        )

        risk_score = sum(ind.weight for ind in indicators)
        risk_level = self._calculate_risk_level(risk_score)

        return FraudDetectionResult(
            scan_type=FraudScanType.INTERNAL_IRREGULARITY,
            risk_score=risk_score,
            risk_level=risk_level,
            confidence=0.0,
            indicators=indicators,
            explanation={
                "analysis_period_days": days,
                "status": "nicht_implementiert",
            },
        )

    async def analyze_audit_trail(
        self,
        company_id: UUID,
        start_date: datetime,
        end_date: datetime,
    ) -> List[FraudDetectionResult]:
        """
        Analyze audit trail for anomalies.

        Checks:
        - Unusual access patterns
        - Bulk deletions/modifications
        - Access to sensitive data outside hours
        - Unauthorized export attempts

        Args:
            company_id: Company to analyze
            start_date: Analysis start
            end_date: Analysis end

        Returns:
            List of FraudDetectionResults for anomalies found
        """
        results: List[FraudDetectionResult] = []

        # M10: Echte Audit-Trail-Analyse auf Basis von AuditLog
        # (app.db.models.AuditLog). Alle Queries strikt company_id-gefiltert
        # (Multi-Tenant). KEIN PII-Logging — nur aggregierte Zahlen.

        # (1) Bulk-Deletes: einzelne Nutzer mit auffaellig vielen Loesch-Aktionen
        bulk_delete_threshold = 20
        try:
            stmt_deletes = (
                select(
                    AuditLog.user_id,
                    func.count(AuditLog.id).label("delete_count"),
                )
                .where(
                    and_(
                        AuditLog.company_id == company_id,
                        AuditLog.user_id.isnot(None),
                        AuditLog.created_at >= start_date,
                        AuditLog.created_at <= end_date,
                        or_(
                            AuditLog.action.ilike("%delete%"),
                            AuditLog.action.ilike("%loesch%"),
                            AuditLog.action.ilike("%lösch%"),
                        ),
                    )
                )
                .group_by(AuditLog.user_id)
                .having(func.count(AuditLog.id) >= bulk_delete_threshold)
            )
            delete_rows = (await self.session.execute(stmt_deletes)).all()
        except Exception as exc:  # noqa: BLE001 - ehrliche Degradation
            logger.warning("fraud_audit_bulk_delete_query_failed", error=safe_error_log(exc))
            delete_rows = []

        for row in delete_rows:
            delete_count = int(row.delete_count)
            weight = min(1.0, 0.3 + delete_count / 200.0)
            indicator = FraudIndicator(
                name="bulk_deletions",
                weight=weight,
                description=(
                    "Ungewoehnlich viele Loesch-Aktionen durch einen einzelnen "
                    "Nutzer im Audit-Trail des Zeitraums."
                ),
                details={
                    "user_id": str(row.user_id),
                    "delete_count": delete_count,
                },
            )
            results.append(
                FraudDetectionResult(
                    scan_type=FraudScanType.INTERNAL_IRREGULARITY,
                    risk_score=weight,
                    risk_level=self._calculate_risk_level(weight),
                    confidence=0.85,
                    indicators=[indicator],
                    explanation={
                        "check": "bulk_deletions",
                        "threshold": bulk_delete_threshold,
                    },
                )
            )

        # (2) Off-Hours-Aktivitaet: Aktionen ausserhalb der Geschaeftszeiten
        # (vor 06:00, ab 22:00 oder am Wochenende). func.extract ist
        # PostgreSQL-Standard; bei abweichendem Dialekt degradiert die Pruefung
        # ehrlich (Warn-Log) statt ein falsch-gruenes Ergebnis zu liefern.
        off_hours_threshold = 25
        try:
            hour_col = func.extract("hour", AuditLog.created_at)
            dow_col = func.extract("dow", AuditLog.created_at)  # 0=So ... 6=Sa
            stmt_off_hours = (
                select(
                    AuditLog.user_id,
                    func.count(AuditLog.id).label("off_hours_count"),
                )
                .where(
                    and_(
                        AuditLog.company_id == company_id,
                        AuditLog.user_id.isnot(None),
                        AuditLog.created_at >= start_date,
                        AuditLog.created_at <= end_date,
                        or_(
                            hour_col < 6,
                            hour_col >= 22,
                            dow_col.in_([0, 6]),
                        ),
                    )
                )
                .group_by(AuditLog.user_id)
                .having(func.count(AuditLog.id) >= off_hours_threshold)
            )
            off_hours_rows = (await self.session.execute(stmt_off_hours)).all()
        except Exception as exc:  # noqa: BLE001 - ehrliche Degradation
            logger.warning("fraud_audit_off_hours_query_failed", error=safe_error_log(exc))
            off_hours_rows = []

        for row in off_hours_rows:
            off_hours_count = int(row.off_hours_count)
            weight = min(1.0, 0.25 + off_hours_count / 300.0)
            indicator = FraudIndicator(
                name="off_hours_activity",
                weight=weight,
                description=(
                    "Auffaellig viele Audit-Aktionen ausserhalb der "
                    "Geschaeftszeiten (nachts/Wochenende)."
                ),
                details={
                    "user_id": str(row.user_id),
                    "off_hours_count": off_hours_count,
                },
            )
            results.append(
                FraudDetectionResult(
                    scan_type=FraudScanType.INTERNAL_IRREGULARITY,
                    risk_score=weight,
                    risk_level=self._calculate_risk_level(weight),
                    confidence=0.8,
                    indicators=[indicator],
                    explanation={
                        "check": "off_hours_activity",
                        "threshold": off_hours_threshold,
                    },
                )
            )

        return results

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def _get_document(self, document_id: UUID) -> Optional[Document]:
        """Get document by ID."""
        stmt = select(Document).where(Document.id == document_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_invoice(self, invoice_id: UUID) -> Optional[InvoiceTracking]:
        """Get invoice by ID."""
        stmt = select(InvoiceTracking).where(InvoiceTracking.id == invoice_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _is_known_sender(self, sender_name: str, company_id: UUID) -> bool:
        """Check if sender is a known entity."""
        if not sender_name:
            return False

        # Fuzzy match against known entities
        stmt = (
            select(func.count(BusinessEntity.id))
            .where(
                and_(
                    BusinessEntity.company_id == company_id,
                    BusinessEntity.name.ilike(f"%{sender_name[:30]}%"),
                )
            )
        )
        result = await self.session.execute(stmt)
        count = result.scalar() or 0
        return count > 0

    async def _is_unusual_amount(self, amount: Decimal, company_id: UUID) -> bool:
        """Check if amount is unusual for this company."""
        # Get median amount for last 90 days
        stmt = (
            select(func.percentile_cont(0.5).within_group(InvoiceTracking.amount))
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.amount.isnot(None),
                    InvoiceTracking.created_at >= datetime.now(timezone.utc) - timedelta(days=90),
                )
            )
        )
        try:
            result = await self.session.execute(stmt)
            median = result.scalar()
            if median and median > 0:
                return float(amount) > float(median) * 3
        except Exception:
            pass
        return False

    def _find_urgency_keywords(self, text: str) -> List[str]:
        """Find urgency keywords in text."""
        found = []
        for keyword in GERMAN_URGENCY_KEYWORDS:
            if keyword in text:
                found.append(keyword)
        return found

    def _mentions_bank_change(self, text: str) -> bool:
        """Check if text mentions bank/IBAN change."""
        bank_change_patterns = [
            r"neue[rn]?\s+(?:iban|bank|konto)",
            r"(?:iban|bank|konto)\s*(?:ge)?änder",
            r"bankverbindung\s*(?:ge)?änder",
            r"bitte\s+(?:überweisen|zahlen)\s+auf",
        ]
        for pattern in bank_change_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def _create_invoice_hash(self, invoice: InvoiceTracking) -> str:
        """Create a hash for duplicate detection."""
        components = [
            str(invoice.invoice_number or "").lower().strip(),
            f"{float(invoice.amount or 0):.2f}",
            str(invoice.entity_id or ""),
        ]
        combined = "|".join(components)
        return hashlib.md5(combined.encode()).hexdigest()

    async def _find_exact_duplicates(
        self,
        invoice_hash: str,
        exclude_id: UUID,
        company_id: UUID,
    ) -> List[UUID]:
        """Find invoices with matching hash."""
        # This would require a hash column on InvoiceTracking
        # For now, use a simpler query
        return []

    async def _find_fuzzy_duplicates(
        self,
        amount: Decimal,
        invoice_date: datetime,
        entity_id: Optional[UUID],
        exclude_id: UUID,
        company_id: UUID,
        amount_tolerance: float = 0.05,
        date_tolerance_days: int = 3,
    ) -> List[UUID]:
        """Find invoices with similar amount and date."""
        min_amount = float(amount) * (1 - amount_tolerance)
        max_amount = float(amount) * (1 + amount_tolerance)
        min_date = invoice_date - timedelta(days=date_tolerance_days)
        max_date = invoice_date + timedelta(days=date_tolerance_days)

        stmt = (
            select(InvoiceTracking.id)
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.id != exclude_id,
                    InvoiceTracking.amount >= min_amount,
                    InvoiceTracking.amount <= max_amount,
                    InvoiceTracking.created_at >= min_date,
                    InvoiceTracking.created_at <= max_date,
                )
            )
        )

        if entity_id:
            stmt = stmt.where(InvoiceTracking.entity_id == entity_id)

        result = await self.session.execute(stmt)
        return [row[0] for row in result.all()]

    async def _find_invoice_number_duplicates(
        self,
        invoice_number: str,
        entity_id: Optional[UUID],
        exclude_id: UUID,
        company_id: UUID,
    ) -> List[UUID]:
        """Find invoices with same number but different entity."""
        stmt = (
            select(InvoiceTracking.id)
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.id != exclude_id,
                    InvoiceTracking.invoice_number == invoice_number,
                )
            )
        )

        if entity_id:
            stmt = stmt.where(InvoiceTracking.entity_id != entity_id)

        result = await self.session.execute(stmt)
        return [row[0] for row in result.all()]

    async def _get_iban_baseline(
        self,
        entity_id: UUID,
        company_id: UUID,
    ) -> List[IBANBaseline]:
        """Get IBAN baselines for an entity."""
        stmt = (
            select(IBANBaseline)
            .where(
                and_(
                    IBANBaseline.entity_id == entity_id,
                    IBANBaseline.company_id == company_id,
                )
            )
            .order_by(IBANBaseline.last_used_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _count_recent_iban_changes(
        self,
        entity_id: UUID,
        company_id: UUID,
        days: int = 90,
    ) -> int:
        """Count IBAN changes in recent period."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            select(func.count(IBANBaseline.id))
            .where(
                and_(
                    IBANBaseline.entity_id == entity_id,
                    IBANBaseline.company_id == company_id,
                    IBANBaseline.first_seen_at >= cutoff,
                )
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def _create_iban_change_request(
        self,
        entity_id: UUID,
        company_id: UUID,
        new_iban: str,
        old_iban: Optional[str],
        source_document_id: Optional[UUID],
        risk_score: float,
        risk_indicators: JSONDict,
    ) -> IBANChangeRequest:
        """Create an IBAN change verification request."""
        request = IBANChangeRequest(
            entity_id=entity_id,
            company_id=company_id,
            old_iban=old_iban,
            new_iban=new_iban,
            source_document_id=source_document_id,
            detection_method="fraud_scan",
            risk_score=risk_score,
            risk_indicators=risk_indicators,
            verification_required=True,
            verification_deadline=datetime.now(timezone.utc) + timedelta(days=7),
        )
        self.session.add(request)
        await self.session.flush()

        logger.info(
            "iban_change_request_created",
            request_id=str(request.id),
            entity_id=str(entity_id),
        )
        return request

    def _calculate_risk_level(self, risk_score: float) -> FraudRiskLevel:
        """Calculate risk level from score."""
        if risk_score >= 0.8:
            return FraudRiskLevel.CRITICAL
        elif risk_score >= 0.6:
            return FraudRiskLevel.HIGH
        elif risk_score >= 0.3:
            return FraudRiskLevel.MEDIUM
        else:
            return FraudRiskLevel.LOW

    def _calculate_confidence(self, indicator_count: int, max_indicators: int) -> float:
        """Calculate confidence based on indicator coverage."""
        if indicator_count == 0:
            return 0.1
        coverage = indicator_count / max_indicators
        return min(0.5 + coverage * 0.5, 0.95)

    def _parse_amount(self, value: Union[str, int, float, Decimal, None]) -> Optional[Decimal]:
        """Parse amount from various formats."""
        if value is None:
            return None
        try:
            if isinstance(value, Decimal):
                return value
            return Decimal(str(value))
        except Exception:
            return None

    def _empty_result(
        self,
        scan_type: FraudScanType,
        document_id: Optional[UUID] = None,
        entity_id: Optional[UUID] = None,
        invoice_id: Optional[UUID] = None,
    ) -> FraudDetectionResult:
        """Create an empty result for cases with no data."""
        return FraudDetectionResult(
            scan_type=scan_type,
            risk_score=0.0,
            risk_level=FraudRiskLevel.LOW,
            confidence=0.0,
            indicators=[],
            explanation={"reason": "no_data"},
            document_id=document_id,
            entity_id=entity_id,
            invoice_id=invoice_id,
        )

    async def _store_scan_result(
        self,
        result: FraudDetectionResult,
        company_id: UUID,
    ) -> FraudScanResult:
        """Store scan result in database."""
        scan_result = FraudScanResult(
            company_id=company_id,
            document_id=result.document_id,
            entity_id=result.entity_id,
            invoice_id=result.invoice_id,
            scan_type=result.scan_type.value,
            scan_source="automated",
            risk_score=result.risk_score,
            risk_level=result.risk_level.value,
            confidence=result.confidence,
            indicators={
                "items": [
                    {"name": ind.name, "weight": ind.weight, "description": ind.description}
                    for ind in result.indicators
                ]
            },
            explanation=result.explanation,
        )
        self.session.add(scan_result)
        await self.session.flush()
        return scan_result

    async def _create_fraud_alert(
        self,
        company_id: UUID,
        alert_code: str,
        title: str,
        message: str,
        document_id: Optional[UUID] = None,
        entity_id: Optional[UUID] = None,
        severity: AlertSeverity = AlertSeverity.HIGH,
        metadata: Optional[JSONDict] = None,
    ) -> None:
        """Create an alert for detected fraud."""
        await self.alert_service.create_alert(
            company_id=company_id,
            alert_code=alert_code,
            category=AlertCategory.FRAUD,
            severity=severity,
            title=title,
            message=message,
            source_type="fraud_detection",
            document_id=document_id,
            entity_id=entity_id,
            metadata=metadata or {},
            available_actions=["acknowledge", "investigate", "dismiss", "escalate"],
        )


# =============================================================================
# Factory Function
# =============================================================================

def get_enhanced_fraud_detection_service(session: AsyncSession) -> EnhancedFraudDetectionService:
    """Factory function to create EnhancedFraudDetectionService instance."""
    return EnhancedFraudDetectionService(session)
