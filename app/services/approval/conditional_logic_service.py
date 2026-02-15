# -*- coding: utf-8 -*-
"""
ConditionalLogicService - Bedingte Genehmigungslogik.

Feature #3: Approval Workflow Depth
Evaluiert bedingte Regeln und fuegt bei Bedarf zusaetzliche
Genehmiger zum Approval-Workflow hinzu.

Bedingungstypen:
- Betragsschwellen (amount gt/lt/gte/lte)
- Risiko-Score-Schwellen (supplier_risk_score gt)
- Dokumenttyp-Filter (document_type eq/in)
- Kategorie-Filter (category eq/in)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Sequence
from uuid import UUID

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ApprovalRequest, BusinessEntity
from app.db.models_approval_extended import ConditionalApprovalRule

logger = structlog.get_logger(__name__)


# ============================================================================
# Datenklassen
# ============================================================================


@dataclass
class ConditionEvaluation:
    """Ergebnis einer Bedingungsauswertung."""

    rule_id: UUID
    rule_name: str
    all_conditions_met: bool
    matched_conditions: List[str] = field(default_factory=list)
    failed_conditions: List[str] = field(default_factory=list)
    additional_approvers: List[Dict[str, str]] = field(default_factory=list)
    priority_override: Optional[str] = None


@dataclass
class ConditionalResult:
    """Gesamtergebnis der bedingten Logik-Auswertung."""

    evaluated_rules: int
    matched_rules: int
    additional_approvers: List[Dict[str, str]] = field(default_factory=list)
    priority_override: Optional[str] = None
    evaluations: List[ConditionEvaluation] = field(default_factory=list)


# ============================================================================
# Operatoren
# ============================================================================

OPERATORS = {
    "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
    "eq": lambda a, b: a == b,
    "neq": lambda a, b: a != b,
    "in": lambda a, b: a in b if isinstance(b, (list, tuple, set)) else False,
    "not_in": lambda a, b: a not in b if isinstance(b, (list, tuple, set)) else True,
}


# ============================================================================
# Service
# ============================================================================


class ConditionalLogicService:
    """Service fuer bedingte Genehmigungslogik.

    Evaluiert bedingte Regeln gegen Approval-Anfragen und bestimmt
    ob zusaetzliche Genehmiger erforderlich sind.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def evaluate_conditions(
        self,
        approval_request: ApprovalRequest,
        rules: Sequence[ConditionalApprovalRule],
    ) -> ConditionalResult:
        """Evaluiert alle bedingten Regeln gegen eine Anfrage.

        Args:
            approval_request: Die zu pruefende Genehmigungsanfrage
            rules: Liste der zu pruefenden Regeln

        Returns:
            ConditionalResult mit allen Auswertungsergebnissen
        """
        result = ConditionalResult(
            evaluated_rules=len(rules),
            matched_rules=0,
        )

        # Kontext aus der Anfrage aufbauen
        context = self._build_context(approval_request)

        for rule in rules:
            if not rule.is_active:
                continue

            evaluation = await self._evaluate_single_rule(rule, context)
            result.evaluations.append(evaluation)

            if evaluation.all_conditions_met:
                result.matched_rules += 1
                result.additional_approvers.extend(evaluation.additional_approvers)
                if evaluation.priority_override and not result.priority_override:
                    result.priority_override = evaluation.priority_override

        # Duplikate bei Genehmigern entfernen
        seen_approvers: List[str] = []
        unique_approvers: List[Dict[str, str]] = []
        for approver in result.additional_approvers:
            key = f"{approver.get('type', '')}:{approver.get('value', '')}"
            if key not in seen_approvers:
                seen_approvers.append(key)
                unique_approvers.append(approver)
        result.additional_approvers = unique_approvers

        logger.info(
            "conditional_rules_evaluated",
            approval_request_id=str(approval_request.id),
            evaluated=result.evaluated_rules,
            matched=result.matched_rules,
            additional_approvers=len(result.additional_approvers),
        )

        return result

    async def get_additional_approvers(
        self,
        approval_request: ApprovalRequest,
    ) -> List[Dict[str, str]]:
        """Ermittelt zusaetzliche Genehmiger basierend auf bedingten Regeln.

        Args:
            approval_request: Die Genehmigungsanfrage

        Returns:
            Liste zusaetzlicher Genehmiger
        """
        rules = await self._get_active_rules(approval_request.company_id)
        if not rules:
            return []

        result = await self.evaluate_conditions(approval_request, rules)
        return result.additional_approvers

    def check_amount_threshold(
        self,
        amount: Optional[Decimal],
        conditions: List[Dict[str, object]],
    ) -> bool:
        """Prueft ob Betrag eine Bedingung erfuellt.

        Args:
            amount: Der zu pruefende Betrag
            conditions: Liste der Bedingungen

        Returns:
            True wenn alle Betragsbedingungen erfuellt sind
        """
        if amount is None:
            return False

        for condition in conditions:
            if condition.get("field") != "amount":
                continue

            operator = str(condition.get("operator", "gt"))
            try:
                threshold = Decimal(str(condition.get("value", 0)))
            except (InvalidOperation, ValueError):
                logger.warning(
                    "invalid_amount_threshold",
                    value=condition.get("value"),
                )
                continue

            op_func = OPERATORS.get(operator)
            if op_func and not op_func(amount, threshold):
                return False

        return True

    async def check_risk_threshold(
        self,
        entity_id: Optional[UUID],
        conditions: List[Dict[str, object]],
    ) -> bool:
        """Prueft ob Entity-Risiko-Score eine Bedingung erfuellt.

        Args:
            entity_id: ID der Business-Entity
            conditions: Liste der Bedingungen

        Returns:
            True wenn alle Risiko-Bedingungen erfuellt sind
        """
        if entity_id is None:
            return False

        # Entity laden fuer Risiko-Score
        stmt = select(BusinessEntity.risk_score).where(
            BusinessEntity.id == entity_id
        )
        result = await self.db.execute(stmt)
        risk_score = result.scalar_one_or_none()

        if risk_score is None:
            return False

        for condition in conditions:
            if condition.get("field") != "supplier_risk_score":
                continue

            operator = str(condition.get("operator", "gt"))
            try:
                threshold = float(str(condition.get("value", 0)))
            except (ValueError, TypeError):
                continue

            op_func = OPERATORS.get(operator)
            if op_func and not op_func(float(risk_score), threshold):
                return False

        return True

    async def apply_conditional_rules(
        self,
        db: AsyncSession,
        company_id: UUID,
        approval_request: ApprovalRequest,
    ) -> ConditionalResult:
        """Haupteinstiegspunkt: Evaluiert und wendet bedingte Regeln an.

        Args:
            db: Database Session
            company_id: ID der Firma
            approval_request: Die Genehmigungsanfrage

        Returns:
            ConditionalResult mit Ergebnissen
        """
        rules = await self._get_active_rules(company_id)
        if not rules:
            return ConditionalResult(evaluated_rules=0, matched_rules=0)

        return await self.evaluate_conditions(approval_request, rules)

    # ========================================================================
    # Private Hilfsmethoden
    # ========================================================================

    async def _get_active_rules(
        self,
        company_id: UUID,
    ) -> Sequence[ConditionalApprovalRule]:
        """Holt alle aktiven bedingten Regeln fuer eine Firma."""
        stmt = (
            select(ConditionalApprovalRule)
            .where(
                and_(
                    ConditionalApprovalRule.company_id == company_id,
                    ConditionalApprovalRule.is_active.is_(True),
                )
            )
            .order_by(ConditionalApprovalRule.created_at)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    def _build_context(
        self,
        approval_request: ApprovalRequest,
    ) -> Dict[str, object]:
        """Baut Kontext-Dict aus der Approval-Anfrage."""
        context: Dict[str, object] = {
            "amount": approval_request.amount,
            "currency": approval_request.currency,
            "entity_type": approval_request.entity_type,
            "entity_id": approval_request.entity_id,
            "priority": (
                approval_request.priority.value
                if approval_request.priority
                else "normal"
            ),
        }

        # Metadaten hinzufuegen falls vorhanden
        metadata = approval_request.request_metadata
        if metadata and isinstance(metadata, dict):
            for key, value in metadata.items():
                if key not in context:
                    context[key] = value

        return context

    async def _evaluate_single_rule(
        self,
        rule: ConditionalApprovalRule,
        context: Dict[str, object],
    ) -> ConditionEvaluation:
        """Evaluiert eine einzelne bedingte Regel."""
        evaluation = ConditionEvaluation(
            rule_id=rule.id,
            rule_name=rule.name,
            all_conditions_met=True,
            additional_approvers=rule.additional_approvers or [],
            priority_override=rule.priority_override,
        )

        conditions = rule.conditions or []

        for condition in conditions:
            field_name = str(condition.get("field", ""))
            operator = str(condition.get("operator", "eq"))
            expected_value = condition.get("value")

            # Sonderbehandlung fuer Risiko-Score (erfordert DB-Abfrage)
            if field_name == "supplier_risk_score":
                entity_id = context.get("entity_id")
                if entity_id and isinstance(entity_id, UUID):
                    met = await self.check_risk_threshold(
                        entity_id, [condition]
                    )
                else:
                    met = False
            else:
                actual_value = context.get(field_name)
                met = self._evaluate_condition(
                    actual_value, operator, expected_value
                )

            condition_desc = f"{field_name} {operator} {expected_value}"
            if met:
                evaluation.matched_conditions.append(condition_desc)
            else:
                evaluation.failed_conditions.append(condition_desc)
                evaluation.all_conditions_met = False

        return evaluation

    def _evaluate_condition(
        self,
        actual_value: object,
        operator: str,
        expected_value: object,
    ) -> bool:
        """Evaluiert eine einzelne Bedingung."""
        if actual_value is None:
            return False

        op_func = OPERATORS.get(operator)
        if not op_func:
            logger.warning("unknown_operator", operator=operator)
            return False

        try:
            # Numerische Vergleiche
            if operator in ("gt", "gte", "lt", "lte"):
                actual_decimal = Decimal(str(actual_value))
                expected_decimal = Decimal(str(expected_value))
                return op_func(actual_decimal, expected_decimal)
            else:
                return op_func(actual_value, expected_value)
        except (InvalidOperation, ValueError, TypeError):
            # Fallback: String-Vergleich
            try:
                return op_func(str(actual_value), str(expected_value))
            except (TypeError, ValueError):
                return False
