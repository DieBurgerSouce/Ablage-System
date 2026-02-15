# -*- coding: utf-8 -*-
"""
ConditionalLogicEngine - Bedingte Logik fuer Genehmigungsworkflows.

Feature #3: Approval Workflow Depth
Evaluiert bedingte Regeln und fuegt bei Bedarf zusaetzliche
Genehmiger zur Approval-Chain hinzu.

Regeln wie:
- Betrag > 5.000 EUR -> zusaetzlicher Genehmiger (Geschaeftsfuehrung)
- Risiko-Score > 70 -> Compliance-Pruefung erforderlich
- Dokumenttyp = 'Vertrag' -> Rechtsabteilung muss pruefen

Nutzt models_approval_extended fuer ConditionalApprovalRule.
"""

from __future__ import annotations

import json
import structlog
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.db.models import ApprovalRequest, ApprovalStep, ApprovalStatus, ApprovalPriority
from app.db.models_approval_extended import ConditionalApprovalRule

logger = structlog.get_logger(__name__)


class ConditionalLogicEngine:
    """Bedingte Logik fuer Genehmigungsworkflows.

    Evaluiert ConditionalApprovalRules gegen Dokumentdaten
    und fuegt bei Match zusaetzliche Genehmiger hinzu.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert die Conditional Logic Engine.

        Args:
            db: Async Database Session
        """
        self.db = db

    async def evaluate_conditions(
        self,
        db: AsyncSession,
        company_id: UUID,
        document_data: Dict[str, object],
    ) -> List[ConditionalApprovalRule]:
        """Prueft alle aktiven bedingten Regeln und gibt zutreffende zurueck.

        Args:
            db: Async Database Session
            company_id: ID der Firma
            document_data: Dokumentdaten fuer Bedingungspruefung
                z.B. {"amount": 7500, "supplier_risk_score": 80, "document_type": "invoice"}

        Returns:
            Liste der zutreffenden ConditionalApprovalRules
        """
        stmt = select(ConditionalApprovalRule).where(
            and_(
                ConditionalApprovalRule.company_id == company_id,
                ConditionalApprovalRule.is_active.is_(True),
            )
        )
        result = await db.execute(stmt)
        rules = result.scalars().all()

        matching: List[ConditionalApprovalRule] = []

        for rule in rules:
            conditions = rule.conditions or []
            if not conditions:
                continue

            all_match = True
            for condition in conditions:
                if not isinstance(condition, dict):
                    all_match = False
                    break

                field_name = condition.get("field", "")
                operator = condition.get("operator", "")
                threshold = condition.get("value")

                field_value = document_data.get(field_name)
                if field_value is None:
                    all_match = False
                    break

                if not self._evaluate_single_condition(
                    operator, str(field_value), threshold
                ):
                    all_match = False
                    break

            if all_match:
                matching.append(rule)
                logger.info(
                    "conditional_rule_matched",
                    rule_id=str(rule.id),
                    rule_name=rule.name,
                    conditions_count=len(conditions),
                )

        return matching

    async def apply_conditional_approvers(
        self,
        db: AsyncSession,
        request_id: UUID,
        matching_rules: List[ConditionalApprovalRule],
    ) -> int:
        """Fuegt zusaetzliche Genehmiger basierend auf zutreffenden Regeln hinzu.

        Args:
            db: Async Database Session
            request_id: ID der Genehmigungsanfrage
            matching_rules: Zutreffende bedingte Regeln

        Returns:
            Anzahl hinzugefuegter Schritte
        """
        request_stmt = select(ApprovalRequest).where(
            ApprovalRequest.id == request_id
        )
        request_result = await db.execute(request_stmt)
        request = request_result.scalar_one_or_none()

        if not request:
            logger.warning(
                "request_not_found_for_conditional_approvers",
                request_id=str(request_id),
            )
            return 0

        added_count = 0

        for rule in matching_rules:
            additional_approvers = rule.additional_approvers or []

            for approver in additional_approvers:
                if not isinstance(approver, dict):
                    continue

                approver_type = approver.get("type", "role")
                approver_value = approver.get("value", "")

                if not approver_value:
                    continue

                # Neuen Step am Ende der Chain einfuegen
                new_step_number = request.total_steps + 1

                step = ApprovalStep(
                    approval_request_id=request_id,
                    step_number=new_step_number,
                    approver_type=approver_type,
                    approver_value=approver_value,
                    is_required=True,
                    status=ApprovalStatus.PENDING,
                )

                if approver_type == "user":
                    try:
                        step.assigned_user_id = UUID(approver_value)
                    except ValueError:
                        pass

                db.add(step)
                request.total_steps = new_step_number
                added_count += 1

            # Prioritaet ueberschreiben falls definiert
            if rule.priority_override:
                try:
                    request.priority = ApprovalPriority(rule.priority_override)
                except ValueError:
                    logger.warning(
                        "invalid_priority_override",
                        value=rule.priority_override,
                        rule_id=str(rule.id),
                    )

        if added_count > 0:
            await db.flush()
            logger.info(
                "conditional_approvers_added",
                request_id=str(request_id),
                count=added_count,
                total_steps=request.total_steps,
            )

        return added_count

    def _evaluate_single_condition(
        self,
        operator: str,
        field_value: str,
        threshold: object,
    ) -> bool:
        """Einzelne Bedingung gegen einen Feldwert auswerten.

        Unterstuetzte Operatoren: gt, lt, eq, neq, in, not_in, between, contains

        Args:
            operator: Vergleichsoperator
            field_value: Aktueller Feldwert als String
            threshold: Schwellenwert aus der Bedingung

        Returns:
            True wenn Bedingung erfuellt
        """
        try:
            if operator == "gt":
                return Decimal(field_value) > Decimal(str(threshold))

            elif operator == "lt":
                return Decimal(field_value) < Decimal(str(threshold))

            elif operator == "gte":
                return Decimal(field_value) >= Decimal(str(threshold))

            elif operator == "lte":
                return Decimal(field_value) <= Decimal(str(threshold))

            elif operator == "eq":
                try:
                    return Decimal(field_value) == Decimal(str(threshold))
                except InvalidOperation:
                    return field_value.strip().lower() == str(threshold).strip().lower()

            elif operator == "neq":
                try:
                    return Decimal(field_value) != Decimal(str(threshold))
                except InvalidOperation:
                    return field_value.strip().lower() != str(threshold).strip().lower()

            elif operator == "in":
                if isinstance(threshold, list):
                    values = threshold
                else:
                    values = json.loads(str(threshold))
                return field_value.strip().lower() in [
                    str(v).strip().lower() for v in values
                ]

            elif operator == "not_in":
                if isinstance(threshold, list):
                    values = threshold
                else:
                    values = json.loads(str(threshold))
                return field_value.strip().lower() not in [
                    str(v).strip().lower() for v in values
                ]

            elif operator == "between":
                if isinstance(threshold, list) and len(threshold) == 2:
                    val = Decimal(field_value)
                    low = Decimal(str(threshold[0]))
                    high = Decimal(str(threshold[1]))
                    return low <= val <= high
                return False

            elif operator == "contains":
                return str(threshold).lower() in field_value.lower()

            else:
                logger.warning("unknown_condition_operator", operator=operator)
                return False

        except (ValueError, InvalidOperation, json.JSONDecodeError, TypeError) as exc:
            logger.debug(
                "condition_evaluation_error",
                operator=operator,
                field_value=field_value,
                threshold=str(threshold),
                error_type=type(exc).__name__,
            )
            return False
