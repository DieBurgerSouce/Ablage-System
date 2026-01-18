"""Approval Rule Service fuer Enterprise Genehmigungsregeln.

Enterprise Feature: Verwaltet Regeln fuer automatisches Approval-Routing mit:
- Betragsschwellen
- Kategoriebasiertes Routing
- Lieferanten-Risikobewertung
- Multi-Level Genehmiger-Ketten
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Optional, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    ApprovalRule,
    ApprovalRuleType,
)

logger = logging.getLogger(__name__)


@dataclass
class ApprovalChainStep:
    """Einzelner Schritt in der Genehmiger-Kette."""

    step: int
    type: str  # "user", "role", "group"
    value: str  # User-ID, Rollenname, etc.
    required: bool = True
    threshold: Optional[Decimal] = None  # Optional: Betragsschwelle fuer diesen Schritt


@dataclass
class MatchedRule:
    """Ergebnis einer Regel-Ueberpruefung."""

    rule: ApprovalRule
    match_score: float  # 0.0 - 1.0, hoeher = bessere Uebereinstimmung
    matched_conditions: list[str]


class ApprovalRuleService:
    """Service fuer Approval-Regeln.

    Ermoeglicht das Erstellen, Verwalten und Evaluieren von
    Genehmigungsregeln fuer verschiedene Entitaeten.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Approval Rule Service.

        Args:
            db: Async Database Session
        """
        self.db = db

    async def create_rule(
        self,
        company_id: UUID,
        name: str,
        rule_type: ApprovalRuleType,
        entity_types: list[str],
        conditions: dict[str, Any],
        approval_chain: list[dict[str, Any]],
        created_by_id: Optional[UUID] = None,
        description: Optional[str] = None,
        escalation_after_hours: Optional[int] = None,
        escalation_to_role: Optional[str] = None,
        sla_hours: int = 48,
        priority: int = 100,
    ) -> ApprovalRule:
        """Erstellt eine neue Genehmigungsregel.

        Args:
            company_id: ID der Firma
            name: Name der Regel
            rule_type: Typ der Regel
            entity_types: Entitaeten auf die die Regel angewendet wird
            conditions: Bedingungen als Dict
            approval_chain: Genehmiger-Kette
            created_by_id: ID des Erstellers
            description: Beschreibung
            escalation_after_hours: Eskalation nach X Stunden
            escalation_to_role: Eskalation an Rolle
            sla_hours: Max. Bearbeitungszeit
            priority: Prioritaet (niedriger = hoeher)

        Returns:
            Erstellte ApprovalRule
        """
        rule = ApprovalRule(
            company_id=company_id,
            name=name,
            description=description,
            rule_type=rule_type,
            entity_types=entity_types,
            conditions=conditions,
            approval_chain=approval_chain,
            escalation_after_hours=escalation_after_hours,
            escalation_to_role=escalation_to_role,
            sla_hours=sla_hours,
            priority=priority,
            created_by_id=created_by_id,
        )

        self.db.add(rule)
        await self.db.commit()
        await self.db.refresh(rule)

        logger.info(
            f"Approval-Regel erstellt: {name} (ID: {rule.id}) "
            f"fuer Company {company_id}"
        )

        return rule

    async def get_rule(
        self,
        rule_id: UUID,
        company_id: UUID,
    ) -> Optional[ApprovalRule]:
        """Holt eine Regel anhand der ID.

        SECURITY: company_id MUSS fuer Multi-Tenant Isolation uebergeben werden.

        Args:
            rule_id: ID der Regel
            company_id: ID der Firma (REQUIRED fuer Multi-Tenant Isolation)

        Returns:
            ApprovalRule oder None
        """
        result = await self.db.execute(
            select(ApprovalRule).where(
                ApprovalRule.id == rule_id,
                ApprovalRule.company_id == company_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_rules_for_company(
        self,
        company_id: UUID,
        active_only: bool = True,
    ) -> Sequence[ApprovalRule]:
        """Holt alle Regeln einer Firma.

        Args:
            company_id: ID der Firma
            active_only: Nur aktive Regeln

        Returns:
            Liste von ApprovalRules
        """
        query = select(ApprovalRule).where(ApprovalRule.company_id == company_id)

        if active_only:
            query = query.where(ApprovalRule.is_active.is_(True))

        query = query.order_by(ApprovalRule.priority)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def update_rule(
        self,
        rule_id: UUID,
        company_id: UUID,
        **updates: Any,
    ) -> Optional[ApprovalRule]:
        """Aktualisiert eine Regel.

        SECURITY: company_id MUSS fuer Multi-Tenant Isolation uebergeben werden.

        Args:
            rule_id: ID der Regel
            company_id: ID der Firma (REQUIRED fuer Multi-Tenant Isolation)
            **updates: Felder zum Aktualisieren

        Returns:
            Aktualisierte ApprovalRule oder None
        """
        rule = await self.get_rule(rule_id, company_id=company_id)
        if not rule:
            return None

        allowed_fields = {
            "name", "description", "rule_type", "entity_types",
            "conditions", "approval_chain", "escalation_after_hours",
            "escalation_to_role", "sla_hours", "priority", "is_active",
        }

        for field, value in updates.items():
            if field in allowed_fields:
                setattr(rule, field, value)

        await self.db.commit()
        await self.db.refresh(rule)

        logger.info(f"Approval-Regel aktualisiert: {rule.name} (ID: {rule_id})")

        return rule

    async def delete_rule(
        self,
        rule_id: UUID,
        company_id: UUID,
    ) -> bool:
        """Loescht eine Regel.

        SECURITY: company_id MUSS fuer Multi-Tenant Isolation uebergeben werden.

        Args:
            rule_id: ID der Regel
            company_id: ID der Firma (REQUIRED fuer Multi-Tenant Isolation)

        Returns:
            True wenn erfolgreich geloescht
        """
        rule = await self.get_rule(rule_id, company_id=company_id)
        if not rule:
            logger.warning(
                "approval_rule_delete_failed",
                rule_id=str(rule_id),
                company_id=str(company_id),
                reason="not_found_or_wrong_company",
            )
            return False

        await self.db.delete(rule)
        await self.db.commit()

        logger.info(f"Approval-Regel geloescht: {rule.name} (ID: {rule_id})")

        return True

    async def find_matching_rules(
        self,
        company_id: UUID,
        entity_type: str,
        entity_data: dict[str, Any],
    ) -> list[MatchedRule]:
        """Findet alle passenden Regeln fuer eine Entitaet.

        Args:
            company_id: ID der Firma
            entity_type: Typ der Entitaet (invoice, expense, etc.)
            entity_data: Daten der Entitaet zur Bedingungspruefung

        Returns:
            Liste von MatchedRule, sortiert nach Prioritaet
        """
        rules = await self.get_rules_for_company(company_id, active_only=True)

        matched_rules: list[MatchedRule] = []

        for rule in rules:
            # Pruefen ob Entity-Typ passt
            if entity_type not in rule.entity_types:
                continue

            # Bedingungen pruefen
            match_result = self._evaluate_conditions(rule.conditions, entity_data)

            if match_result["matches"]:
                matched_rules.append(
                    MatchedRule(
                        rule=rule,
                        match_score=match_result["score"],
                        matched_conditions=match_result["matched"],
                    )
                )

        # Sortieren nach Prioritaet (niedrig = hoch)
        matched_rules.sort(key=lambda x: x.rule.priority)

        return matched_rules

    def _evaluate_conditions(
        self,
        conditions: dict[str, Any],
        entity_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Evaluiert Bedingungen gegen Entitaetsdaten.

        Args:
            conditions: Bedingungen aus der Regel
            entity_data: Daten der Entitaet

        Returns:
            Dict mit matches (bool), score (float), matched (list)
        """
        if not conditions:
            return {"matches": True, "score": 1.0, "matched": []}

        matched_conditions: list[str] = []
        total_conditions = len(conditions)

        for condition_key, condition_value in conditions.items():
            # WICHTIG: _not_in muss VOR _in ersetzt werden, da sonst
            # "category_not_in" zu "category_not" wird statt "category"
            entity_value = entity_data.get(condition_key.replace("_greater_than", "")
                                           .replace("_less_than", "")
                                           .replace("_equals", "")
                                           .replace("_not_in", "")
                                           .replace("_in", ""))

            if entity_value is None:
                continue

            if "_greater_than" in condition_key:
                if self._compare_values(entity_value, condition_value, ">"):
                    matched_conditions.append(condition_key)
            elif "_less_than" in condition_key:
                if self._compare_values(entity_value, condition_value, "<"):
                    matched_conditions.append(condition_key)
            elif "_equals" in condition_key:
                if entity_value == condition_value:
                    matched_conditions.append(condition_key)
            elif "_not_in" in condition_key:
                # WICHTIG: _not_in muss VOR _in geprueft werden,
                # da "category_not_in" auch "_in" enthaelt
                if entity_value not in condition_value:
                    matched_conditions.append(condition_key)
            elif "_in" in condition_key:
                if entity_value in condition_value:
                    matched_conditions.append(condition_key)
            else:
                # Exakte Uebereinstimmung
                if entity_value == condition_value:
                    matched_conditions.append(condition_key)

        matches = len(matched_conditions) == total_conditions
        score = len(matched_conditions) / total_conditions if total_conditions > 0 else 1.0

        return {
            "matches": matches,
            "score": score,
            "matched": matched_conditions,
        }

    def _compare_values(
        self,
        entity_value: Any,
        condition_value: Any,
        operator: str,
    ) -> bool:
        """Vergleicht zwei Werte.

        Args:
            entity_value: Wert der Entitaet
            condition_value: Wert aus der Bedingung
            operator: Vergleichsoperator (>, <, ==)

        Returns:
            True wenn Vergleich erfolgreich
        """
        try:
            # Konvertiere zu Decimal fuer numerische Vergleiche
            if isinstance(entity_value, (int, float, str)):
                entity_value = Decimal(str(entity_value))
            if isinstance(condition_value, (int, float, str)):
                condition_value = Decimal(str(condition_value))

            if operator == ">":
                return entity_value > condition_value
            elif operator == "<":
                return entity_value < condition_value
            elif operator == "==":
                return entity_value == condition_value
        except (ValueError, TypeError, InvalidOperation):
            return False

        return False

    async def create_default_rules(self, company_id: UUID, created_by_id: UUID) -> list[ApprovalRule]:
        """Erstellt Standard-Genehmigungsregeln fuer eine Firma.

        Args:
            company_id: ID der Firma
            created_by_id: ID des Erstellers

        Returns:
            Liste der erstellten Regeln
        """
        default_rules = [
            {
                "name": "Rechnungen ueber 5.000 EUR",
                "description": "Alle Rechnungen ueber 5.000 EUR benoetigen Manager-Genehmigung",
                "rule_type": ApprovalRuleType.AMOUNT_THRESHOLD,
                "entity_types": ["invoice"],
                "conditions": {"amount_greater_than": 5000},
                "approval_chain": [
                    {"step": 1, "type": "role", "value": "manager", "required": True},
                ],
                "priority": 100,
            },
            {
                "name": "Rechnungen ueber 25.000 EUR",
                "description": "Alle Rechnungen ueber 25.000 EUR benoetigen CFO-Genehmigung",
                "rule_type": ApprovalRuleType.AMOUNT_THRESHOLD,
                "entity_types": ["invoice"],
                "conditions": {"amount_greater_than": 25000},
                "approval_chain": [
                    {"step": 1, "type": "role", "value": "manager", "required": True},
                    {"step": 2, "type": "role", "value": "cfo", "required": True},
                ],
                "priority": 50,  # Hoehere Prioritaet
            },
            {
                "name": "Reisekosten ueber 1.000 EUR",
                "description": "Reisekosten ueber 1.000 EUR benoetigen Genehmigung",
                "rule_type": ApprovalRuleType.CATEGORY,
                "entity_types": ["expense"],
                "conditions": {
                    "category_in": ["travel", "reise", "dienstreise"],
                    "amount_greater_than": 1000,
                },
                "approval_chain": [
                    {"step": 1, "type": "role", "value": "manager", "required": True},
                ],
                "priority": 100,
            },
            {
                "name": "Neue Vertraege",
                "description": "Alle neuen Vertraege benoetigen Rechtsabteilung und Management",
                "rule_type": ApprovalRuleType.DOCUMENT_TYPE,
                "entity_types": ["contract", "document"],
                "conditions": {"document_type_in": ["contract", "vertrag"]},
                "approval_chain": [
                    {"step": 1, "type": "role", "value": "legal", "required": True},
                    {"step": 2, "type": "role", "value": "manager", "required": True},
                ],
                "priority": 80,
                "sla_hours": 72,
            },
        ]

        created_rules: list[ApprovalRule] = []

        for rule_data in default_rules:
            rule = await self.create_rule(
                company_id=company_id,
                created_by_id=created_by_id,
                **rule_data,
            )
            created_rules.append(rule)

        logger.info(
            f"Standard-Genehmigungsregeln erstellt fuer Company {company_id}: "
            f"{len(created_rules)} Regeln"
        )

        return created_rules

    async def evaluate_rule_conditions(
        self,
        rule: ApprovalRule,
        entity_data: dict[str, Any],
    ) -> bool:
        """Evaluiert ob eine Regel auf Entity-Daten zutrifft (fuer API Preview).

        Args:
            rule: Die zu pruefende Regel
            entity_data: Testdaten der Entitaet

        Returns:
            True wenn die Regel zutrifft
        """
        result = self._evaluate_conditions(rule.conditions or {}, entity_data)
        return result["matches"]
