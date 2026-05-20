"""Approval Rule Service für Enterprise Genehmigungsregeln.

Enterprise Feature: Verwaltet Regeln für automatisches Approval-Routing mit:
- Betragsschwellen
- Kategoriebasiertes Routing
- Lieferanten-Risikobewertung
- Multi-Level Genehmiger-Ketten
"""

from __future__ import annotations

import structlog
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Sequence, Union
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    ApprovalRule,
    ApprovalRuleType,
)

logger = structlog.get_logger(__name__)


@dataclass
class ApprovalChainStep:
    """Einzelner Schritt in der Genehmiger-Kette."""

    step: int
    type: str  # "user", "role", "group"
    value: str  # User-ID, Rollenname, etc.
    required: bool = True
    threshold: Optional[Decimal] = None  # Optional: Betragsschwelle für diesen Schritt


@dataclass
class MatchedRule:
    """Ergebnis einer Regel-Überprüfung."""

    rule: ApprovalRule
    match_score: float  # 0.0 - 1.0, höher = bessere Übereinstimmung
    matched_conditions: List[str]


class ApprovalRuleService:
    """Service für Approval-Regeln.

    Ermöglicht das Erstellen, Verwalten und Evaluieren von
    Genehmigungsregeln für verschiedene Entitäten.
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
        entity_types: List[str],
        conditions: Dict[str, object],
        approval_chain: List[Dict[str, object]],
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
            entity_types: Entitäten auf die die Regel angewendet wird
            conditions: Bedingungen als Dict
            approval_chain: Genehmiger-Kette
            created_by_id: ID des Erstellers
            description: Beschreibung
            escalation_after_hours: Eskalation nach X Stunden
            escalation_to_role: Eskalation an Rolle
            sla_hours: Max. Bearbeitungszeit
            priority: Priorität (niedriger = höher)

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
            "approval_rule_created",
            name=name,
            rule_id=str(rule.id),
            company_id=str(company_id),
        )

        return rule

    async def get_rule(
        self,
        rule_id: UUID,
        company_id: UUID,
    ) -> Optional[ApprovalRule]:
        """Holt eine Regel anhand der ID.

        SECURITY: company_id MUSS für Multi-Tenant Isolation übergeben werden.

        Args:
            rule_id: ID der Regel
            company_id: ID der Firma (REQUIRED für Multi-Tenant Isolation)

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
        **updates: object,
    ) -> Optional[ApprovalRule]:
        """Aktualisiert eine Regel.

        SECURITY: company_id MUSS für Multi-Tenant Isolation übergeben werden.

        Args:
            rule_id: ID der Regel
            company_id: ID der Firma (REQUIRED für Multi-Tenant Isolation)
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

        logger.info(
            "approval_rule_updated",
            rule_name=rule.name,
            rule_id=str(rule_id),
        )

        return rule

    async def delete_rule(
        self,
        rule_id: UUID,
        company_id: UUID,
    ) -> bool:
        """Löscht eine Regel.

        SECURITY: company_id MUSS für Multi-Tenant Isolation übergeben werden.

        Args:
            rule_id: ID der Regel
            company_id: ID der Firma (REQUIRED für Multi-Tenant Isolation)

        Returns:
            True wenn erfolgreich gelöscht
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

        logger.info(
            "approval_rule_deleted",
            rule_name=rule.name,
            rule_id=str(rule_id),
        )

        return True

    async def find_matching_rules(
        self,
        company_id: UUID,
        entity_type: str,
        entity_data: Dict[str, object],
    ) -> List[MatchedRule]:
        """Findet alle passenden Regeln für eine Entität.

        Args:
            company_id: ID der Firma
            entity_type: Typ der Entität (invoice, expense, etc.)
            entity_data: Daten der Entität zur Bedingungsprüfung

        Returns:
            Liste von MatchedRule, sortiert nach Priorität
        """
        rules = await self.get_rules_for_company(company_id, active_only=True)

        matched_rules: List[MatchedRule] = []

        for rule in rules:
            # Prüfen ob Entity-Typ passt
            if entity_type not in rule.entity_types:
                continue

            # Bedingungen prüfen
            match_result = self._evaluate_conditions(rule.conditions, entity_data)

            if match_result["matches"]:
                matched_rules.append(
                    MatchedRule(
                        rule=rule,
                        match_score=match_result["score"],
                        matched_conditions=match_result["matched"],
                    )
                )

        # Sortieren nach Priorität (niedrig = hoch)
        matched_rules.sort(key=lambda x: x.rule.priority)

        return matched_rules

    def _evaluate_conditions(
        self,
        conditions: Dict[str, object],
        entity_data: Dict[str, object],
    ) -> Dict[str, object]:
        """Evaluiert Bedingungen gegen Entitätsdaten.

        Args:
            conditions: Bedingungen aus der Regel
            entity_data: Daten der Entität

        Returns:
            Dict mit matches (bool), score (float), matched (list)
        """
        if not conditions:
            return {"matches": True, "score": 1.0, "matched": []}

        matched_conditions: List[str] = []
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
                # WICHTIG: _not_in muss VOR _in geprüft werden,
                # da "category_not_in" auch "_in" enthält
                if entity_value not in condition_value:
                    matched_conditions.append(condition_key)
            elif "_in" in condition_key:
                if entity_value in condition_value:
                    matched_conditions.append(condition_key)
            else:
                # Exakte Übereinstimmung
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
        entity_value: object,
        condition_value: object,
        operator: str,
    ) -> bool:
        """Vergleicht zwei Werte.

        Args:
            entity_value: Wert der Entität
            condition_value: Wert aus der Bedingung
            operator: Vergleichsoperator (>, <, ==)

        Returns:
            True wenn Vergleich erfolgreich
        """
        try:
            # Konvertiere zu Decimal für numerische Vergleiche
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

    async def create_default_rules(self, company_id: UUID, created_by_id: UUID) -> List[ApprovalRule]:
        """Erstellt Standard-Genehmigungsregeln für eine Firma.

        Args:
            company_id: ID der Firma
            created_by_id: ID des Erstellers

        Returns:
            Liste der erstellten Regeln
        """
        default_rules = [
            {
                "name": "Rechnungen über 5.000 EUR",
                "description": "Alle Rechnungen über 5.000 EUR benötigen Manager-Genehmigung",
                "rule_type": ApprovalRuleType.AMOUNT_THRESHOLD,
                "entity_types": ["invoice"],
                "conditions": {"amount_greater_than": 5000},
                "approval_chain": [
                    {"step": 1, "type": "role", "value": "manager", "required": True},
                ],
                "priority": 100,
            },
            {
                "name": "Rechnungen über 25.000 EUR",
                "description": "Alle Rechnungen über 25.000 EUR benötigen CFO-Genehmigung",
                "rule_type": ApprovalRuleType.AMOUNT_THRESHOLD,
                "entity_types": ["invoice"],
                "conditions": {"amount_greater_than": 25000},
                "approval_chain": [
                    {"step": 1, "type": "role", "value": "manager", "required": True},
                    {"step": 2, "type": "role", "value": "cfo", "required": True},
                ],
                "priority": 50,  # Höhere Priorität
            },
            {
                "name": "Reisekosten über 1.000 EUR",
                "description": "Reisekosten über 1.000 EUR benötigen Genehmigung",
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
                "name": "Neue Verträge",
                "description": "Alle neuen Verträge benötigen Rechtsabteilung und Management",
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

        created_rules: List[ApprovalRule] = []

        for rule_data in default_rules:
            rule = await self.create_rule(
                company_id=company_id,
                created_by_id=created_by_id,
                **rule_data,
            )
            created_rules.append(rule)

        logger.info(
            "default_approval_rules_created",
            company_id=str(company_id),
            count=len(created_rules),
        )

        return created_rules

    async def evaluate_rule_conditions(
        self,
        rule: ApprovalRule,
        entity_data: Dict[str, object],
    ) -> bool:
        """Evaluiert ob eine Regel auf Entity-Daten zutrifft (für API Preview).

        Args:
            rule: Die zu prüfende Regel
            entity_data: Testdaten der Entität

        Returns:
            True wenn die Regel zutrifft
        """
        result = self._evaluate_conditions(rule.conditions or {}, entity_data)
        return result["matches"]
