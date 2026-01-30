# -*- coding: utf-8 -*-
"""
Contract Comparison Service.

Vergleicht Vertragsversionen und identifiziert:
- Geaenderte Klauseln
- Hinzugefuegte/Entfernte Abschnitte
- Finanzielle Aenderungen
- Risiko-Impact der Aenderungen

Feinpoliert und durchdacht.
"""

import logging
from datetime import datetime
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_contract import (
    Contract,
    ContractComparison,
)

logger = logging.getLogger(__name__)


class ContractComparisonService:
    """
    Service fuer Vertragsvergleiche.

    Ermoeglicht den detaillierten Vergleich von
    Vertragsversionen oder unterschiedlichen Vertraegen.
    """

    # Felder die verglichen werden
    COMPARABLE_FIELDS = [
        "title",
        "contract_type",
        "total_value",
        "currency",
        "effective_date",
        "expiration_date",
        "notice_period_days",
        "auto_renewal",
        "renewal_period_months",
        "renewal_notice_days",
        "payment_terms",
        "clauses",
        "parties",
    ]

    # Risiko-Impact pro Feld
    FIELD_RISK_WEIGHTS = {
        "total_value": 3.0,
        "notice_period_days": 2.0,
        "expiration_date": 2.0,
        "auto_renewal": 1.5,
        "clauses": 2.0,
        "parties": 1.0,
        "payment_terms": 1.5,
    }

    def __init__(self, db: AsyncSession):
        """Initialisiere Service mit Datenbank-Session."""
        self.db = db

    async def compare_contracts(
        self,
        contract_a_id: UUID,
        contract_b_id: UUID,
        company_id: UUID,
        created_by_id: Optional[UUID] = None,
        save_comparison: bool = True,
    ) -> Dict[str, Any]:
        """
        Vergleiche zwei Vertraege.

        Args:
            contract_a_id: ID des ersten Vertrags (alt)
            contract_b_id: ID des zweiten Vertrags (neu)
            company_id: ID der Firma
            created_by_id: ID des Benutzers
            save_comparison: Ob Vergleich gespeichert werden soll

        Returns:
            Dictionary mit Vergleichsergebnis
        """
        # Lade Vertraege
        contract_a = await self.db.get(Contract, contract_a_id)
        contract_b = await self.db.get(Contract, contract_b_id)

        if not contract_a or not contract_b:
            raise ValueError("Einer oder beide Vertraege nicht gefunden")

        # Berechne Unterschiede
        differences = self._calculate_differences(contract_a, contract_b)

        # Berechne Aehnlichkeit
        similarity = self._calculate_similarity(contract_a, contract_b)

        # Analysiere Klauseln
        clause_analysis = self._analyze_clauses(
            contract_a.clauses or {},
            contract_b.clauses or {},
        )

        # Berechne Risiko-Impact
        risk_impact = self._calculate_risk_impact(differences, clause_analysis)

        # Erstelle Zusammenfassung
        summary = self._generate_summary(differences, clause_analysis, risk_impact)

        result = {
            "contract_a_id": str(contract_a_id),
            "contract_b_id": str(contract_b_id),
            "contract_a_title": contract_a.title,
            "contract_b_title": contract_b.title,
            "differences": differences,
            "similarity_score": similarity,
            "added_clauses": clause_analysis["added"],
            "removed_clauses": clause_analysis["removed"],
            "modified_clauses": clause_analysis["modified"],
            "risk_impact": risk_impact,
            "summary": summary,
            "compared_at": datetime.now().isoformat(),
        }

        # Speichere Vergleich
        if save_comparison:
            comparison = ContractComparison(
                contract_a_id=contract_a_id,
                contract_b_id=contract_b_id,
                differences=differences,
                similarity_score=Decimal(str(similarity)),
                added_clauses=clause_analysis["added"],
                removed_clauses=clause_analysis["removed"],
                modified_clauses=clause_analysis["modified"],
                risk_impact=risk_impact["total"],
                risk_summary=summary,
                company_id=company_id,
                created_by_id=created_by_id,
            )
            self.db.add(comparison)
            await self.db.commit()
            await self.db.refresh(comparison)
            result["comparison_id"] = str(comparison.id)

        logger.info(
            f"Vertragsvergleich: {contract_a_id} vs {contract_b_id}, "
            f"Aehnlichkeit: {similarity:.2%}, Risiko-Impact: {risk_impact['total']}"
        )

        return result

    async def get_comparison(
        self,
        comparison_id: UUID,
    ) -> Optional[ContractComparison]:
        """Hole gespeicherten Vergleich."""
        return await self.db.get(ContractComparison, comparison_id)

    async def get_comparisons_for_contract(
        self,
        contract_id: UUID,
    ) -> List[ContractComparison]:
        """Hole alle Vergleiche fuer einen Vertrag."""
        query = select(ContractComparison).where(
            (ContractComparison.contract_a_id == contract_id) |
            (ContractComparison.contract_b_id == contract_id)
        ).order_by(ContractComparison.created_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def compare_with_previous_version(
        self,
        contract_id: UUID,
        company_id: UUID,
        created_by_id: Optional[UUID] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Vergleiche Vertrag mit seiner Vorgaengerversion.

        Args:
            contract_id: ID des aktuellen Vertrags
            company_id: ID der Firma
            created_by_id: ID des Benutzers

        Returns:
            Vergleichsergebnis oder None wenn keine Vorgaengerversion
        """
        contract = await self.db.get(Contract, contract_id)
        if not contract or not contract.parent_contract_id:
            return None

        return await self.compare_contracts(
            contract_a_id=contract.parent_contract_id,
            contract_b_id=contract_id,
            company_id=company_id,
            created_by_id=created_by_id,
        )

    def _calculate_differences(
        self,
        contract_a: Contract,
        contract_b: Contract,
    ) -> List[Dict[str, Any]]:
        """Berechne Unterschiede zwischen Vertraegen."""
        differences = []

        for field in self.COMPARABLE_FIELDS:
            value_a = getattr(contract_a, field, None)
            value_b = getattr(contract_b, field, None)

            # Konvertiere fuer Vergleich
            value_a_str = self._normalize_value(value_a)
            value_b_str = self._normalize_value(value_b)

            if value_a_str != value_b_str:
                change_type = self._determine_change_type(value_a, value_b)
                difference = {
                    "field": field,
                    "field_label": self._get_field_label(field),
                    "old_value": value_a_str,
                    "new_value": value_b_str,
                    "change_type": change_type,
                }

                # Berechne prozentuale Aenderung fuer numerische Felder
                if field == "total_value" and value_a and value_b:
                    try:
                        old_val = float(value_a)
                        new_val = float(value_b)
                        if old_val > 0:
                            pct_change = ((new_val - old_val) / old_val) * 100
                            difference["percentage_change"] = round(pct_change, 2)
                    except (ValueError, TypeError):
                        pass

                differences.append(difference)

        return differences

    def _calculate_similarity(
        self,
        contract_a: Contract,
        contract_b: Contract,
    ) -> float:
        """Berechne Aehnlichkeit zwischen Vertraegen (0-1)."""
        # Kombiniere relevante Textfelder
        text_a_parts = []
        text_b_parts = []

        for field in ["title", "contract_type"]:
            val_a = getattr(contract_a, field, "") or ""
            val_b = getattr(contract_b, field, "") or ""
            text_a_parts.append(str(val_a))
            text_b_parts.append(str(val_b))

        # Klauseln als Text
        clauses_a = contract_a.clauses or {}
        clauses_b = contract_b.clauses or {}
        text_a_parts.append(str(clauses_a))
        text_b_parts.append(str(clauses_b))

        text_a = " ".join(text_a_parts)
        text_b = " ".join(text_b_parts)

        # Berechne Aehnlichkeit mit SequenceMatcher
        matcher = SequenceMatcher(None, text_a.lower(), text_b.lower())
        return matcher.ratio()

    def _analyze_clauses(
        self,
        clauses_a: Dict[str, Any],
        clauses_b: Dict[str, Any],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Analysiere Klausel-Aenderungen."""
        added = []
        removed = []
        modified = []

        all_keys = set(clauses_a.keys()) | set(clauses_b.keys())

        for key in all_keys:
            in_a = key in clauses_a
            in_b = key in clauses_b

            if in_b and not in_a:
                # Hinzugefuegt
                added.append({
                    "clause": key,
                    "clause_label": self._get_clause_label(key),
                    "new_value": clauses_b[key],
                })
            elif in_a and not in_b:
                # Entfernt
                removed.append({
                    "clause": key,
                    "clause_label": self._get_clause_label(key),
                    "old_value": clauses_a[key],
                })
            elif in_a and in_b:
                # Pruefen ob geaendert
                if clauses_a[key] != clauses_b[key]:
                    modified.append({
                        "clause": key,
                        "clause_label": self._get_clause_label(key),
                        "old_value": clauses_a[key],
                        "new_value": clauses_b[key],
                        "changes": self._diff_clause_values(clauses_a[key], clauses_b[key]),
                    })

        return {
            "added": added,
            "removed": removed,
            "modified": modified,
        }

    def _calculate_risk_impact(
        self,
        differences: List[Dict[str, Any]],
        clause_analysis: Dict[str, List],
    ) -> Dict[str, Any]:
        """Berechne Risiko-Impact der Aenderungen."""
        total_impact = 0
        factor_impacts = {}

        # Feld-Aenderungen
        for diff in differences:
            field = diff["field"]
            weight = self.FIELD_RISK_WEIGHTS.get(field, 1.0)
            change_type = diff["change_type"]

            # Basiswert je nach Aenderungstyp
            base_impact = {
                "added": 5,
                "removed": 10,
                "modified": 8,
                "increased": 6,
                "decreased": 4,
            }.get(change_type, 5)

            impact = int(base_impact * weight)
            factor_impacts[field] = impact
            total_impact += impact

        # Klausel-Aenderungen
        clause_impact = 0
        for _ in clause_analysis["added"]:
            clause_impact += 5
        for _ in clause_analysis["removed"]:
            clause_impact += 15  # Entfernte Klauseln sind riskanter
        for _ in clause_analysis["modified"]:
            clause_impact += 10

        factor_impacts["clauses"] = clause_impact
        total_impact += clause_impact

        # Normalisiere auf -100 bis +100
        total_impact = min(100, max(-100, total_impact))

        # Bestimme Impact-Kategorie
        if total_impact > 50:
            impact_category = "critical"
        elif total_impact > 25:
            impact_category = "high"
        elif total_impact > 10:
            impact_category = "medium"
        elif total_impact > 0:
            impact_category = "low"
        else:
            impact_category = "none"

        return {
            "total": total_impact,
            "category": impact_category,
            "by_factor": factor_impacts,
        }

    def _generate_summary(
        self,
        differences: List[Dict[str, Any]],
        clause_analysis: Dict[str, List],
        risk_impact: Dict[str, Any],
    ) -> str:
        """Generiere Zusammenfassung des Vergleichs."""
        parts = []

        # Anzahl Aenderungen
        num_changes = len(differences)
        num_clause_changes = (
            len(clause_analysis["added"]) +
            len(clause_analysis["removed"]) +
            len(clause_analysis["modified"])
        )

        parts.append(f"{num_changes} Feldaenderungen und {num_clause_changes} Klauselaenderungen gefunden.")

        # Wichtige Aenderungen hervorheben
        for diff in differences:
            if diff["field"] == "total_value":
                pct = diff.get("percentage_change")
                if pct:
                    direction = "erhoeht" if pct > 0 else "verringert"
                    parts.append(f"Vertragswert um {abs(pct):.1f}% {direction}.")

            elif diff["field"] == "notice_period_days":
                parts.append(
                    f"Kuendigungsfrist geaendert: {diff['old_value']} → {diff['new_value']} Tage."
                )

            elif diff["field"] == "auto_renewal":
                if diff["new_value"] == "True":
                    parts.append("Automatische Verlaengerung aktiviert.")
                else:
                    parts.append("Automatische Verlaengerung deaktiviert.")

        # Klausel-Zusammenfassung
        if clause_analysis["removed"]:
            clauses = ", ".join([c["clause_label"] for c in clause_analysis["removed"]])
            parts.append(f"Entfernte Klauseln: {clauses}.")

        if clause_analysis["added"]:
            clauses = ", ".join([c["clause_label"] for c in clause_analysis["added"]])
            parts.append(f"Neue Klauseln: {clauses}.")

        # Risiko-Warnung
        if risk_impact["category"] in ["critical", "high"]:
            parts.append(f"ACHTUNG: {risk_impact['category'].upper()} Risiko-Impact ({risk_impact['total']}).")

        return " ".join(parts)

    def _normalize_value(self, value: Any) -> str:
        """Normalisiere Wert fuer Vergleich."""
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return str(value)
        if isinstance(value, Decimal):
            return str(float(value))
        if hasattr(value, 'isoformat'):
            return value.isoformat()
        return str(value)

    def _determine_change_type(self, old_val: Any, new_val: Any) -> str:
        """Bestimme Art der Aenderung."""
        if old_val is None and new_val is not None:
            return "added"
        if old_val is not None and new_val is None:
            return "removed"

        # Numerischer Vergleich
        try:
            old_num = float(old_val) if old_val else 0
            new_num = float(new_val) if new_val else 0
            if new_num > old_num:
                return "increased"
            elif new_num < old_num:
                return "decreased"
        except (ValueError, TypeError):
            pass

        return "modified"

    def _diff_clause_values(
        self,
        old_val: Any,
        new_val: Any,
    ) -> List[Dict[str, Any]]:
        """Berechne Detailaenderungen in einer Klausel."""
        changes = []

        if isinstance(old_val, dict) and isinstance(new_val, dict):
            all_keys = set(old_val.keys()) | set(new_val.keys())
            for key in all_keys:
                old_sub = old_val.get(key)
                new_sub = new_val.get(key)
                if old_sub != new_sub:
                    changes.append({
                        "key": key,
                        "old": old_sub,
                        "new": new_sub,
                    })
        else:
            changes.append({
                "key": "_value",
                "old": old_val,
                "new": new_val,
            })

        return changes

    def _get_field_label(self, field: str) -> str:
        """Hole deutschen Label fuer Feld."""
        labels = {
            "title": "Titel",
            "contract_type": "Vertragstyp",
            "total_value": "Vertragswert",
            "currency": "Waehrung",
            "effective_date": "Beginn",
            "expiration_date": "Ablauf",
            "notice_period_days": "Kuendigungsfrist (Tage)",
            "auto_renewal": "Automatische Verlaengerung",
            "renewal_period_months": "Verlaengerungszeitraum (Monate)",
            "renewal_notice_days": "Verlaengerungs-Kuendigungsfrist (Tage)",
            "payment_terms": "Zahlungsbedingungen",
            "clauses": "Klauseln",
            "parties": "Vertragsparteien",
        }
        return labels.get(field, field)

    def _get_clause_label(self, clause: str) -> str:
        """Hole deutschen Label fuer Klausel."""
        labels = {
            "liability": "Haftung",
            "warranty": "Gewaehrleistung",
            "jurisdiction": "Gerichtsstand",
            "incoterms": "Lieferbedingungen",
            "price_adjustment": "Preisanpassung",
            "confidentiality": "Geheimhaltung",
        }
        return labels.get(clause, clause.replace("_", " ").title())
