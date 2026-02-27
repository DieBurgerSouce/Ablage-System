# -*- coding: utf-8 -*-
"""
Contract Risk Scorer Service.

Bewertet Vertragsrisiken basierend auf:
- Finanzielle Exposition
- Kündigungsfristen und Flexibilitaet
- Haftungsklauseln
- Laufzeiten
- Gegenpartei-Risiko
- Vertragskomplexität

Feinpoliert und durchdacht.
"""

import structlog
from datetime import date
from decimal import Decimal
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_contract import (
    Contract,
    ContractType,
    ContractStatus,
)

logger = structlog.get_logger(__name__)


class ContractRiskScorer:
    """
    Service für die Risikobewertung von Verträgen.

    Berechnet einen Score von 0-100 basierend auf
    gewichteten Risikofaktoren.
    """

    # Risikofaktoren mit Gewichtungen
    RISK_FACTORS = {
        "financial_exposure": 0.25,      # Finanzielles Risiko
        "termination_flexibility": 0.15,  # Kündigungsflexibilitaet
        "liability_coverage": 0.15,       # Haftungsabdeckung
        "contract_duration": 0.10,        # Vertragslaufzeit
        "counterparty_risk": 0.15,        # Gegenpartei-Risiko
        "clause_complexity": 0.10,        # Klausel-Komplexität
        "renewal_risk": 0.10,             # Verlängerungsrisiko
    }

    # Schwellenwerte für Risikokategorien
    RISK_THRESHOLDS = {
        "low": 30,
        "medium": 60,
        "high": 80,
        "critical": 100,
    }

    def __init__(self, db: AsyncSession):
        """Initialisiere Service mit Datenbank-Session."""
        self.db = db

    async def calculate_risk_score(
        self,
        contract: Contract,
        include_factors: bool = True,
    ) -> Dict[str, Any]:
        """
        Berechne Risiko-Score für einen Vertrag.

        Args:
            contract: Der zu bewertende Vertrag
            include_factors: Ob Detailfaktoren einbezogen werden

        Returns:
            Dictionary mit Score und Faktoren
        """
        factors = {}
        weighted_score = 0.0

        # 1. Finanzielles Risiko
        financial_score, financial_detail = self._assess_financial_exposure(contract)
        factors["financial_exposure"] = financial_detail
        weighted_score += financial_score * self.RISK_FACTORS["financial_exposure"]

        # 2. Kündigungsflexibilitaet
        termination_score, termination_detail = self._assess_termination_flexibility(contract)
        factors["termination_flexibility"] = termination_detail
        weighted_score += termination_score * self.RISK_FACTORS["termination_flexibility"]

        # 3. Haftungsabdeckung
        liability_score, liability_detail = self._assess_liability_coverage(contract)
        factors["liability_coverage"] = liability_detail
        weighted_score += liability_score * self.RISK_FACTORS["liability_coverage"]

        # 4. Vertragslaufzeit
        duration_score, duration_detail = self._assess_contract_duration(contract)
        factors["contract_duration"] = duration_detail
        weighted_score += duration_score * self.RISK_FACTORS["contract_duration"]

        # 5. Gegenpartei-Risiko (vereinfacht, ohne externe Daten)
        counterparty_score, counterparty_detail = await self._assess_counterparty_risk(contract)
        factors["counterparty_risk"] = counterparty_detail
        weighted_score += counterparty_score * self.RISK_FACTORS["counterparty_risk"]

        # 6. Klausel-Komplexität
        complexity_score, complexity_detail = self._assess_clause_complexity(contract)
        factors["clause_complexity"] = complexity_detail
        weighted_score += complexity_score * self.RISK_FACTORS["clause_complexity"]

        # 7. Verlängerungsrisiko
        renewal_score, renewal_detail = self._assess_renewal_risk(contract)
        factors["renewal_risk"] = renewal_detail
        weighted_score += renewal_score * self.RISK_FACTORS["renewal_risk"]

        # Normalisiere auf 0-100
        final_score = min(100, max(0, int(weighted_score)))

        # Bestimme Risikokategorie
        risk_category = self._get_risk_category(final_score)

        result = {
            "score": final_score,
            "category": risk_category,
            "factors": factors if include_factors else {},
            "recommendations": self._generate_recommendations(factors, final_score),
        }

        logger.info(
            "contract_risk_score_calculated",
            score=final_score,
            category=risk_category,
            contract_id=str(contract.id),
        )

        return result

    async def update_contract_risk_score(
        self,
        contract_id: UUID,
    ) -> Contract:
        """
        Aktualisiere Risiko-Score eines Vertrags.

        Args:
            contract_id: ID des Vertrags

        Returns:
            Aktualisierter Vertrag
        """
        contract = await self.db.get(Contract, contract_id)
        if not contract:
            raise ValueError(f"Vertrag {contract_id} nicht gefunden")

        result = await self.calculate_risk_score(contract, include_factors=True)

        contract.risk_score = result["score"]
        contract.risk_factors = [
            {
                "factor": factor,
                "score": details.get("score", 0),
                "impact": int(details.get("score", 0) * self.RISK_FACTORS.get(factor, 0.1)),
                "description": details.get("description", ""),
            }
            for factor, details in result["factors"].items()
        ]

        await self.db.commit()
        await self.db.refresh(contract)

        return contract

    async def get_high_risk_contracts(
        self,
        company_id: UUID,
        threshold: int = 70,
    ) -> List[Contract]:
        """
        Hole Verträge mit hohem Risiko.

        Args:
            company_id: ID der Firma
            threshold: Risiko-Schwellenwert

        Returns:
            Liste von Verträgen
        """
        query = select(Contract).where(
            Contract.company_id == company_id,
            Contract.status == ContractStatus.ACTIVE.value,
            Contract.risk_score >= threshold,
        ).order_by(Contract.risk_score.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_risk_distribution(
        self,
        company_id: UUID,
    ) -> Dict[str, int]:
        """
        Hole Risiko-Verteilung für eine Firma.

        Args:
            company_id: ID der Firma

        Returns:
            Dictionary mit Anzahl pro Kategorie
        """
        distribution = {
            "low": 0,
            "medium": 0,
            "high": 0,
            "critical": 0,
            "unscored": 0,
        }

        query = select(Contract).where(
            Contract.company_id == company_id,
            Contract.status == ContractStatus.ACTIVE.value,
        )

        result = await self.db.execute(query)
        contracts = list(result.scalars().all())

        for contract in contracts:
            if contract.risk_score is None:
                distribution["unscored"] += 1
            else:
                category = self._get_risk_category(contract.risk_score)
                distribution[category] += 1

        return distribution

    async def get_aggregate_risk_metrics(
        self,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """
        Berechne aggregierte Risiko-Metriken.

        Args:
            company_id: ID der Firma

        Returns:
            Dictionary mit Metriken
        """
        # Durchschnittlicher Score
        avg_query = select(func.avg(Contract.risk_score)).where(
            Contract.company_id == company_id,
            Contract.status == ContractStatus.ACTIVE.value,
            Contract.risk_score.isnot(None),
        )
        avg_result = await self.db.execute(avg_query)
        avg_score = avg_result.scalar() or 0

        # Maximaler Score
        max_query = select(func.max(Contract.risk_score)).where(
            Contract.company_id == company_id,
            Contract.status == ContractStatus.ACTIVE.value,
        )
        max_result = await self.db.execute(max_query)
        max_score = max_result.scalar() or 0

        # Gesamtexposition (Summe der Vertragswerte von High-Risk)
        exposure_query = select(func.sum(Contract.total_value)).where(
            Contract.company_id == company_id,
            Contract.status == ContractStatus.ACTIVE.value,
            Contract.risk_score >= 70,
        )
        exposure_result = await self.db.execute(exposure_query)
        high_risk_exposure = exposure_result.scalar() or 0

        # Verteilung
        distribution = await self.get_risk_distribution(company_id)

        return {
            "average_score": round(float(avg_score), 1),
            "max_score": max_score,
            "high_risk_exposure": float(high_risk_exposure),
            "distribution": distribution,
            "total_contracts": sum(distribution.values()),
            "high_risk_count": distribution.get("high", 0) + distribution.get("critical", 0),
        }

    def _assess_financial_exposure(self, contract: Contract) -> tuple[int, Dict[str, Any]]:
        """Bewerte finanzielles Risiko."""
        score = 50  # Basis
        details = {"score": score, "description": ""}

        if contract.total_value:
            value = float(contract.total_value)

            # Hoher Wert = hoheres Risiko
            if value > 1000000:
                score = 100
                details["description"] = "Sehr hoher Vertragswert (>1 Mio EUR)"
            elif value > 500000:
                score = 80
                details["description"] = "Hoher Vertragswert (>500k EUR)"
            elif value > 100000:
                score = 60
                details["description"] = "Mittlerer Vertragswert (>100k EUR)"
            elif value > 10000:
                score = 40
                details["description"] = "Moderater Vertragswert"
            else:
                score = 20
                details["description"] = "Niedriger Vertragswert"
        else:
            score = 50
            details["description"] = "Kein Vertragswert angegeben"

        details["score"] = score
        return score, details

    def _assess_termination_flexibility(self, contract: Contract) -> tuple[int, Dict[str, Any]]:
        """Bewerte Kündigungsflexibilitaet."""
        score = 50
        details = {"score": score, "description": ""}

        if contract.notice_period_days:
            days = contract.notice_period_days

            # Kurze Frist = weniger Risiko (mehr Flexibilitaet)
            if days > 180:
                score = 90
                details["description"] = f"Lange Kündigungsfrist ({days} Tage)"
            elif days > 90:
                score = 70
                details["description"] = f"Mittlere Kündigungsfrist ({days} Tage)"
            elif days > 30:
                score = 50
                details["description"] = f"Normale Kündigungsfrist ({days} Tage)"
            elif days > 14:
                score = 30
                details["description"] = f"Kurze Kündigungsfrist ({days} Tage)"
            else:
                score = 20
                details["description"] = f"Sehr kurze Kündigungsfrist ({days} Tage)"
        else:
            score = 60
            details["description"] = "Keine Kündigungsfrist definiert"

        details["score"] = score
        return score, details

    def _assess_liability_coverage(self, contract: Contract) -> tuple[int, Dict[str, Any]]:
        """Bewerte Haftungsabdeckung."""
        score = 50
        details = {"score": score, "description": ""}

        clauses = contract.clauses or {}
        liability = clauses.get("liability", {})

        if liability:
            limit = liability.get("limit")
            exclusions = liability.get("exclusions", [])

            if limit:
                # Haftungslimit vorhanden
                if limit < 10000:
                    score = 80
                    details["description"] = "Niedriges Haftungslimit"
                elif limit < 100000:
                    score = 50
                    details["description"] = "Moderates Haftungslimit"
                else:
                    score = 30
                    details["description"] = "Hohes Haftungslimit"

                # Ausschluesse erhöhen Risiko
                if exclusions:
                    score += len(exclusions) * 5
                    details["description"] += f", {len(exclusions)} Ausschluesse"
            else:
                score = 70
                details["description"] = "Kein Haftungslimit definiert"
        else:
            score = 70
            details["description"] = "Keine Haftungsklausel gefunden"

        details["score"] = min(100, score)
        return min(100, score), details

    def _assess_contract_duration(self, contract: Contract) -> tuple[int, Dict[str, Any]]:
        """Bewerte Vertragslaufzeit."""
        score = 50
        details = {"score": score, "description": ""}

        if contract.effective_date and contract.expiration_date:
            duration = (contract.expiration_date - contract.effective_date).days

            # Lange Laufzeit = hoheres Risiko (weniger Flexibilitaet)
            if duration > 1825:  # > 5 Jahre
                score = 90
                details["description"] = "Sehr lange Laufzeit (>5 Jahre)"
            elif duration > 1095:  # > 3 Jahre
                score = 70
                details["description"] = "Lange Laufzeit (>3 Jahre)"
            elif duration > 365:  # > 1 Jahr
                score = 50
                details["description"] = "Mittlere Laufzeit (1-3 Jahre)"
            elif duration > 90:
                score = 30
                details["description"] = "Kurze Laufzeit (<1 Jahr)"
            else:
                score = 20
                details["description"] = "Sehr kurze Laufzeit"
        elif contract.expiration_date is None:
            score = 40
            details["description"] = "Unbefristeter Vertrag"
        else:
            score = 50
            details["description"] = "Laufzeit nicht bestimmbar"

        details["score"] = score
        return score, details

    async def _assess_counterparty_risk(self, contract: Contract) -> tuple[int, Dict[str, Any]]:
        """Bewerte Gegenpartei-Risiko."""
        score = 50
        details = {"score": score, "description": ""}

        # Bewertung basierend auf Entity-Daten und optional Creditreform
        if contract.counterparty_entity_id:
            entity = await self.db.get(BusinessEntity, contract.counterparty_entity_id)
            if entity:
                # Nutze Entity Risk-Score wenn verfügbar
                entity_risk = getattr(entity, "risk_score", None)
                if entity_risk is not None:
                    # Invertiere: Niedriger Risk Score = niedrigeres Risiko
                    score = int(entity_risk * 0.8)  # 0-80 Skala
                    details["description"] = f"Entity Risk Score: {entity_risk}"
                    details["entity_name"] = entity.name
                else:
                    score = 40
                    details["description"] = "Gegenpartei bekannt, kein Risk-Score"
            else:
                score = 50
                details["description"] = "Gegenpartei-ID vorhanden, Entity nicht gefunden"
        else:
            score = 60
            details["description"] = "Keine Gegenpartei-Informationen"

        # Vertragshistorie prüfen
        if contract.parent_contract_id:
            # Verlängerung = bessere Beziehung
            score -= 10
            details["description"] += ", Vertragsverlängerung"

        details["score"] = max(0, score)
        return max(0, score), details

    def _assess_clause_complexity(self, contract: Contract) -> tuple[int, Dict[str, Any]]:
        """Bewerte Klausel-Komplexität."""
        score = 50
        details = {"score": score, "description": ""}

        clauses = contract.clauses or {}
        num_clauses = len(clauses)

        # Mehr Klauseln = komplexer = höher Risiko
        if num_clauses > 10:
            score = 80
            details["description"] = f"Hohe Komplexität ({num_clauses} Klauseln)"
        elif num_clauses > 5:
            score = 60
            details["description"] = f"Mittlere Komplexität ({num_clauses} Klauseln)"
        elif num_clauses > 0:
            score = 40
            details["description"] = f"Geringe Komplexität ({num_clauses} Klauseln)"
        else:
            score = 70
            details["description"] = "Keine Klauseln extrahiert"

        # Spezielle Klauseln prüfen
        if clauses.get("price_adjustment"):
            score += 10
            details["description"] += ", Preisanpassung"

        if clauses.get("confidentiality"):
            score += 5
            details["description"] += ", NDA"

        details["score"] = min(100, score)
        return min(100, score), details

    def _assess_renewal_risk(self, contract: Contract) -> tuple[int, Dict[str, Any]]:
        """Bewerte Verlängerungsrisiko."""
        score = 50
        details = {"score": score, "description": ""}

        if contract.auto_renewal:
            score = 70
            details["description"] = "Automatische Verlängerung aktiv"

            if contract.renewal_notice_days:
                if contract.renewal_notice_days < 30:
                    score += 20
                    details["description"] += f", kurze Widerrufsfrist ({contract.renewal_notice_days} Tage)"
        else:
            score = 30
            details["description"] = "Keine automatische Verlängerung"

        # Naehe zum Ablaufdatum
        if contract.expiration_date:
            days_until = (contract.expiration_date - date.today()).days
            if 0 < days_until < 30:
                score += 20
                details["description"] += ", laeuft bald ab"

        details["score"] = min(100, score)
        return min(100, score), details

    def _get_risk_category(self, score: int) -> str:
        """Bestimme Risikokategorie basierend auf Score."""
        if score < self.RISK_THRESHOLDS["low"]:
            return "low"
        elif score < self.RISK_THRESHOLDS["medium"]:
            return "medium"
        elif score < self.RISK_THRESHOLDS["high"]:
            return "high"
        else:
            return "critical"

    def _generate_recommendations(
        self,
        factors: Dict[str, Any],
        score: int,
    ) -> List[str]:
        """Generiere Handlungsempfehlungen."""
        recommendations = []

        # Finanzielle Empfehlungen
        financial = factors.get("financial_exposure", {})
        if financial.get("score", 0) > 70:
            recommendations.append("Risikobegrenzung durch Teilzahlungen oder Meilensteine prüfen")

        # Kündigungsfrist
        termination = factors.get("termination_flexibility", {})
        if termination.get("score", 0) > 70:
            recommendations.append("Kürzere Kündigungsfristen bei Verlängerung verhandeln")

        # Haftung
        liability = factors.get("liability_coverage", {})
        if liability.get("score", 0) > 70:
            recommendations.append("Haftungsbegrenzung oder Versicherung prüfen")

        # Auto-Renewal
        renewal = factors.get("renewal_risk", {})
        if renewal.get("score", 0) > 70:
            recommendations.append("Automatische Verlängerung überprüfen, Erinnerung setzen")

        # Allgemeine Empfehlung bei hohem Risiko
        if score >= 80:
            recommendations.insert(0, "ACHTUNG: Hoher Risiko-Score - Vertrag priorisiert prüfen")

        return recommendations[:5]  # Max 5 Empfehlungen
