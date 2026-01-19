"""
Risk Intelligence Service

Erweiterte Risikoanalyse mit:
- Branchen-Benchmarks
- Trend-Analyse
- Netzwerk-Analyse
- Externe Datenquellen
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    BusinessEntity,
    Document,
    InvoiceTracking,
)

logger = logging.getLogger(__name__)


class TrendDirection(str, Enum):
    """Trend-Richtung"""
    IMPROVING = "improving"
    STABLE = "stable"
    DETERIORATING = "deteriorating"
    CRITICAL = "critical"


class ExternalDataSource(str, Enum):
    """Externe Datenquellen"""
    CREDITREFORM = "creditreform"
    SCHUFA = "schufa"
    INSOLVENCY_REGISTER = "insolvency_register"
    HANDELSREGISTER = "handelsregister"


class RiskIntelligenceService:
    """
    Erweiterte Risk Intelligence fuer Geschaeftspartner.

    Kombiniert interne Daten mit externen Quellen und
    bietet Trend- und Netzwerk-Analysen.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        # Branchen-Benchmarks (statisch, in Zukunft aus DB/API)
        self.industry_benchmarks = {
            "retail": {
                "avg_payment_delay": 15,
                "default_rate": 0.02,
                "industry_risk_factor": 1.0,
            },
            "manufacturing": {
                "avg_payment_delay": 30,
                "default_rate": 0.03,
                "industry_risk_factor": 1.1,
            },
            "services": {
                "avg_payment_delay": 21,
                "default_rate": 0.015,
                "industry_risk_factor": 0.9,
            },
            "construction": {
                "avg_payment_delay": 45,
                "default_rate": 0.05,
                "industry_risk_factor": 1.3,
            },
            "technology": {
                "avg_payment_delay": 14,
                "default_rate": 0.02,
                "industry_risk_factor": 1.0,
            },
            "default": {
                "avg_payment_delay": 25,
                "default_rate": 0.025,
                "industry_risk_factor": 1.0,
            },
        }

    async def get_comprehensive_risk_profile(
        self,
        entity_id: UUID,
        company_id: UUID,
    ) -> dict[str, Any]:
        """
        Erstellt umfassendes Risikoprofil fuer eine Entity.

        Kombiniert:
        - Interne Analyse (Zahlungsverhalten, Volumen)
        - Trend-Analyse (Verschlechterung erkennen)
        - Branchen-Benchmark-Vergleich
        - Netzwerk-Analyse (Verbindungen)
        """
        # Basis-Entity laden
        query = select(BusinessEntity).where(
            and_(
                BusinessEntity.id == entity_id,
                BusinessEntity.company_id == company_id,
            )
        )
        result = await self.db.execute(query)
        entity = result.scalar_one_or_none()

        if not entity:
            return {"error": "Entity nicht gefunden"}

        # Parallele Analysen
        internal_analysis = await self._analyze_internal_data(entity_id, company_id)
        trend_analysis = await self._analyze_trends(entity_id, company_id)
        benchmark_comparison = await self._compare_with_benchmarks(
            entity_id, company_id, entity.industry or "default"
        )
        network_analysis = await self._analyze_network(entity_id, company_id)

        # Gesamtscore berechnen
        total_score = self._calculate_composite_score(
            internal_analysis,
            trend_analysis,
            benchmark_comparison,
            network_analysis,
        )

        return {
            "entity_id": str(entity_id),
            "entity_name": entity.name,
            "entity_type": entity.entity_type,
            "industry": entity.industry or "unknown",
            "overall_risk_score": total_score["score"],
            "risk_level": total_score["level"],
            "analysis": {
                "internal": internal_analysis,
                "trend": trend_analysis,
                "benchmark": benchmark_comparison,
                "network": network_analysis,
            },
            "recommendations": self._generate_recommendations(
                total_score, trend_analysis, benchmark_comparison
            ),
            "analyzed_at": datetime.utcnow().isoformat(),
        }

    async def _analyze_internal_data(
        self,
        entity_id: UUID,
        company_id: UUID,
    ) -> dict[str, Any]:
        """Analysiert interne Zahlungs- und Geschaeftsdaten."""
        # Rechnungen der letzten 12 Monate
        one_year_ago = datetime.utcnow() - timedelta(days=365)

        query = (
            select(
                func.count(InvoiceTracking.id).label("total_invoices"),
                func.sum(InvoiceTracking.total_amount).label("total_volume"),
                func.avg(InvoiceTracking.days_until_payment).label("avg_payment_days"),
                func.count(
                    InvoiceTracking.id
                ).filter(
                    InvoiceTracking.dunning_level > 0
                ).label("dunning_count"),
                func.count(
                    InvoiceTracking.id
                ).filter(
                    InvoiceTracking.status == "paid"
                ).label("paid_count"),
            )
            .where(
                and_(
                    InvoiceTracking.entity_id == entity_id,
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.created_at >= one_year_ago,
                )
            )
        )
        result = await self.db.execute(query)
        row = result.one()

        total_invoices = row.total_invoices or 0
        paid_count = row.paid_count or 0
        dunning_count = row.dunning_count or 0

        # Kennzahlen berechnen
        payment_rate = paid_count / total_invoices if total_invoices > 0 else 1.0
        dunning_rate = dunning_count / total_invoices if total_invoices > 0 else 0.0

        # Score berechnen (0-100, niedriger = besser)
        internal_score = 0
        internal_score += min(40, max(0, (row.avg_payment_days or 0) - 14) * 1.5)  # Zahlungsverzoegerung
        internal_score += dunning_rate * 100 * 0.3  # Mahnungen
        internal_score += (1 - payment_rate) * 100 * 0.2  # Nicht bezahlt

        return {
            "total_invoices": total_invoices,
            "total_volume": float(row.total_volume or 0),
            "avg_payment_days": float(row.avg_payment_days or 0),
            "payment_rate": payment_rate,
            "dunning_rate": dunning_rate,
            "internal_score": min(100, internal_score),
        }

    async def _analyze_trends(
        self,
        entity_id: UUID,
        company_id: UUID,
    ) -> dict[str, Any]:
        """Analysiert Trends im Zahlungsverhalten ueber Zeit."""
        # Quartalsweise Analyse
        quarters = []
        now = datetime.utcnow()

        for i in range(4):  # Letzte 4 Quartale
            quarter_end = now - timedelta(days=90 * i)
            quarter_start = quarter_end - timedelta(days=90)

            query = (
                select(
                    func.avg(InvoiceTracking.days_until_payment).label("avg_days"),
                    func.count(InvoiceTracking.id).label("invoice_count"),
                    func.sum(
                        InvoiceTracking.total_amount
                    ).filter(
                        InvoiceTracking.dunning_level > 0
                    ).label("dunning_amount"),
                )
                .where(
                    and_(
                        InvoiceTracking.entity_id == entity_id,
                        InvoiceTracking.company_id == company_id,
                        InvoiceTracking.created_at >= quarter_start,
                        InvoiceTracking.created_at < quarter_end,
                    )
                )
            )
            result = await self.db.execute(query)
            row = result.one()

            quarters.append({
                "period": f"Q{4-i}",
                "start": quarter_start.isoformat(),
                "end": quarter_end.isoformat(),
                "avg_payment_days": float(row.avg_days or 0),
                "invoice_count": row.invoice_count or 0,
                "dunning_amount": float(row.dunning_amount or 0),
            })

        # Trend berechnen
        if len(quarters) >= 2:
            recent = quarters[0]["avg_payment_days"]
            previous = quarters[1]["avg_payment_days"]

            if previous > 0:
                change = (recent - previous) / previous
            else:
                change = 0

            if change > 0.2:
                trend = TrendDirection.DETERIORATING
            elif change > 0.5:
                trend = TrendDirection.CRITICAL
            elif change < -0.1:
                trend = TrendDirection.IMPROVING
            else:
                trend = TrendDirection.STABLE
        else:
            trend = TrendDirection.STABLE
            change = 0

        return {
            "direction": trend,
            "change_percentage": change * 100,
            "quarters": quarters,
            "trend_score": (
                0 if trend == TrendDirection.IMPROVING
                else 20 if trend == TrendDirection.STABLE
                else 50 if trend == TrendDirection.DETERIORATING
                else 80
            ),
        }

    async def _compare_with_benchmarks(
        self,
        entity_id: UUID,
        company_id: UUID,
        industry: str,
    ) -> dict[str, Any]:
        """Vergleicht mit Branchen-Benchmarks."""
        benchmark = self.industry_benchmarks.get(
            industry, self.industry_benchmarks["default"]
        )

        # Entity-Daten laden
        one_year_ago = datetime.utcnow() - timedelta(days=365)
        query = (
            select(
                func.avg(InvoiceTracking.days_until_payment).label("avg_days"),
                func.count(
                    InvoiceTracking.id
                ).filter(
                    InvoiceTracking.dunning_level >= 3
                ).label("serious_defaults"),
                func.count(InvoiceTracking.id).label("total"),
            )
            .where(
                and_(
                    InvoiceTracking.entity_id == entity_id,
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.created_at >= one_year_ago,
                )
            )
        )
        result = await self.db.execute(query)
        row = result.one()

        actual_delay = float(row.avg_days or 0)
        actual_default_rate = (
            row.serious_defaults / row.total if row.total > 0 else 0
        )

        # Abweichung vom Benchmark
        delay_deviation = (
            (actual_delay - benchmark["avg_payment_delay"])
            / benchmark["avg_payment_delay"]
            if benchmark["avg_payment_delay"] > 0
            else 0
        )
        default_deviation = (
            (actual_default_rate - benchmark["default_rate"])
            / benchmark["default_rate"]
            if benchmark["default_rate"] > 0
            else 0
        )

        # Benchmark-Score (0 = besser als Benchmark, 100 = viel schlechter)
        benchmark_score = max(0, min(100, (
            delay_deviation * 30 + default_deviation * 30 +
            (benchmark["industry_risk_factor"] - 1) * 40
        )))

        return {
            "industry": industry,
            "benchmark": benchmark,
            "actual_payment_delay": actual_delay,
            "actual_default_rate": actual_default_rate,
            "delay_deviation": delay_deviation * 100,
            "default_deviation": default_deviation * 100,
            "performance": (
                "above_benchmark" if delay_deviation < -0.1
                else "at_benchmark" if delay_deviation < 0.1
                else "below_benchmark"
            ),
            "benchmark_score": benchmark_score,
        }

    async def _analyze_network(
        self,
        entity_id: UUID,
        company_id: UUID,
    ) -> dict[str, Any]:
        """Analysiert Netzwerk-Verbindungen der Entity."""
        # Entitaeten mit gleicher IBAN oder Adresse finden
        entity_query = select(BusinessEntity).where(BusinessEntity.id == entity_id)
        result = await self.db.execute(entity_query)
        entity = result.scalar_one_or_none()

        if not entity:
            return {"connections": [], "risk_score": 0}

        connections = []
        network_risk = 0

        # Gleiche IBAN
        if entity.iban:
            iban_query = (
                select(BusinessEntity)
                .where(
                    and_(
                        BusinessEntity.company_id == company_id,
                        BusinessEntity.iban == entity.iban,
                        BusinessEntity.id != entity_id,
                    )
                )
            )
            result = await self.db.execute(iban_query)
            shared_iban = result.scalars().all()

            for connected in shared_iban:
                connections.append({
                    "entity_id": str(connected.id),
                    "entity_name": connected.name,
                    "connection_type": "shared_iban",
                    "risk_level": "high",
                })
                network_risk += 30

        # Gleiche Adresse
        if entity.street and entity.city:
            address_query = (
                select(BusinessEntity)
                .where(
                    and_(
                        BusinessEntity.company_id == company_id,
                        BusinessEntity.street == entity.street,
                        BusinessEntity.city == entity.city,
                        BusinessEntity.id != entity_id,
                    )
                )
            )
            result = await self.db.execute(address_query)
            shared_address = result.scalars().all()

            for connected in shared_address:
                # Nicht doppelt zaehlen wenn bereits durch IBAN verbunden
                if not any(c["entity_id"] == str(connected.id) for c in connections):
                    connections.append({
                        "entity_id": str(connected.id),
                        "entity_name": connected.name,
                        "connection_type": "shared_address",
                        "risk_level": "medium",
                    })
                    network_risk += 15

        return {
            "connections": connections,
            "connection_count": len(connections),
            "network_risk_score": min(100, network_risk),
            "has_suspicious_connections": network_risk > 30,
        }

    def _calculate_composite_score(
        self,
        internal: dict,
        trend: dict,
        benchmark: dict,
        network: dict,
    ) -> dict[str, Any]:
        """Berechnet Gesamtscore aus allen Analysen."""
        # Gewichtete Summe
        weights = {
            "internal": 0.35,
            "trend": 0.25,
            "benchmark": 0.25,
            "network": 0.15,
        }

        composite = (
            internal.get("internal_score", 0) * weights["internal"] +
            trend.get("trend_score", 0) * weights["trend"] +
            benchmark.get("benchmark_score", 0) * weights["benchmark"] +
            network.get("network_risk_score", 0) * weights["network"]
        )

        # Level bestimmen
        if composite >= 75:
            level = "critical"
        elif composite >= 50:
            level = "high"
        elif composite >= 25:
            level = "medium"
        else:
            level = "low"

        return {
            "score": round(composite, 1),
            "level": level,
            "component_scores": {
                "internal": internal.get("internal_score", 0),
                "trend": trend.get("trend_score", 0),
                "benchmark": benchmark.get("benchmark_score", 0),
                "network": network.get("network_risk_score", 0),
            },
        }

    def _generate_recommendations(
        self,
        score: dict,
        trend: dict,
        benchmark: dict,
    ) -> list[dict[str, Any]]:
        """Generiert Handlungsempfehlungen basierend auf Analyse."""
        recommendations = []

        # Trend-basierte Empfehlungen
        if trend["direction"] == TrendDirection.DETERIORATING:
            recommendations.append({
                "priority": "high",
                "category": "trend",
                "title": "Verschlechterung des Zahlungsverhaltens",
                "description": "Das Zahlungsverhalten hat sich im Vergleich zum Vorquartal verschlechtert. "
                               "Kontaktieren Sie den Geschaeftspartner proaktiv.",
                "action": "contact_partner",
            })
        elif trend["direction"] == TrendDirection.CRITICAL:
            recommendations.append({
                "priority": "critical",
                "category": "trend",
                "title": "Kritische Entwicklung",
                "description": "Starke Verschlechterung festgestellt. Reduzieren Sie Kreditlinien "
                               "und fordern Sie Vorauszahlungen.",
                "action": "reduce_credit",
            })

        # Benchmark-basierte Empfehlungen
        if benchmark["performance"] == "below_benchmark":
            recommendations.append({
                "priority": "medium",
                "category": "benchmark",
                "title": "Unter Branchendurchschnitt",
                "description": f"Zahlungsverhalten liegt unter dem Branchendurchschnitt "
                               f"({benchmark['actual_payment_delay']:.0f} vs. "
                               f"{benchmark['benchmark']['avg_payment_delay']} Tage).",
                "action": "monitor_closely",
            })

        # Score-basierte Empfehlungen
        if score["level"] == "critical":
            recommendations.append({
                "priority": "critical",
                "category": "overall",
                "title": "Kritisches Risiko",
                "description": "Sofortige Massnahmen erforderlich. Pruefen Sie alle offenen Positionen "
                               "und erwägen Sie Factoring oder Kreditversicherung.",
                "action": "immediate_review",
            })
        elif score["level"] == "high":
            recommendations.append({
                "priority": "high",
                "category": "overall",
                "title": "Hohes Risiko",
                "description": "Erhoehte Ueberwachung empfohlen. Setzen Sie Zahlungsziele und "
                               "fuehren Sie regelmaessige Reviews durch.",
                "action": "enhanced_monitoring",
            })

        # Wenn keine spezifischen Empfehlungen
        if not recommendations:
            recommendations.append({
                "priority": "low",
                "category": "overall",
                "title": "Normales Risikoprofil",
                "description": "Keine besonderen Massnahmen erforderlich. "
                               "Regelmaessige Ueberpruefung empfohlen.",
                "action": "standard_monitoring",
            })

        return recommendations

    async def get_portfolio_risk_overview(
        self,
        company_id: UUID,
        entity_type: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Liefert Portfolio-Risikouebersicht fuer alle Entities.
        """
        # Alle Entities der Firma
        query = select(BusinessEntity).where(BusinessEntity.company_id == company_id)
        if entity_type:
            query = query.where(BusinessEntity.entity_type == entity_type)

        result = await self.db.execute(query)
        entities = result.scalars().all()

        risk_distribution = {
            "low": 0,
            "medium": 0,
            "high": 0,
            "critical": 0,
        }
        high_risk_entities = []
        total_exposure = Decimal("0")

        for entity in entities:
            profile = await self.get_comprehensive_risk_profile(entity.id, company_id)
            level = profile.get("overall_risk_score", 0)

            # Einordnung
            if level >= 75:
                risk_distribution["critical"] += 1
                high_risk_entities.append({
                    "id": str(entity.id),
                    "name": entity.name,
                    "risk_score": level,
                    "risk_level": "critical",
                })
            elif level >= 50:
                risk_distribution["high"] += 1
                high_risk_entities.append({
                    "id": str(entity.id),
                    "name": entity.name,
                    "risk_score": level,
                    "risk_level": "high",
                })
            elif level >= 25:
                risk_distribution["medium"] += 1
            else:
                risk_distribution["low"] += 1

            # Exposure berechnen (offene Betraege)
            exposure_query = (
                select(func.sum(InvoiceTracking.outstanding_amount))
                .where(
                    and_(
                        InvoiceTracking.entity_id == entity.id,
                        InvoiceTracking.status != "paid",
                    )
                )
            )
            exp_result = await self.db.execute(exposure_query)
            entity_exposure = exp_result.scalar() or Decimal("0")
            total_exposure += entity_exposure

        return {
            "total_entities": len(entities),
            "risk_distribution": risk_distribution,
            "high_risk_entities": sorted(
                high_risk_entities, key=lambda x: -x["risk_score"]
            )[:10],
            "total_exposure": float(total_exposure),
            "portfolio_risk_score": self._calculate_portfolio_risk(risk_distribution, len(entities)),
            "analyzed_at": datetime.utcnow().isoformat(),
        }

    def _calculate_portfolio_risk(
        self,
        distribution: dict[str, int],
        total: int,
    ) -> float:
        """Berechnet Portfolio-Risikoscore."""
        if total == 0:
            return 0

        weighted = (
            distribution["low"] * 10 +
            distribution["medium"] * 35 +
            distribution["high"] * 65 +
            distribution["critical"] * 90
        )
        return round(weighted / total, 1)

    async def check_external_sources(
        self,
        entity_id: UUID,
        company_id: UUID,
    ) -> dict[str, Any]:
        """
        Prueft externe Datenquellen (Mock-Implementierung).

        In Produktion wuerden hier echte API-Calls zu:
        - Creditreform
        - SCHUFA
        - Insolvenzregister
        - Handelsregister
        """
        # Entity laden
        query = select(BusinessEntity).where(
            and_(
                BusinessEntity.id == entity_id,
                BusinessEntity.company_id == company_id,
            )
        )
        result = await self.db.execute(query)
        entity = result.scalar_one_or_none()

        if not entity:
            return {"error": "Entity nicht gefunden"}

        # Mock-Daten (in Produktion durch echte API-Calls ersetzen)
        external_data = {
            "entity_id": str(entity_id),
            "entity_name": entity.name,
            "sources_checked": [],
            "alerts": [],
            "last_checked": datetime.utcnow().isoformat(),
        }

        # Handelsregister (immer verfuegbar)
        external_data["sources_checked"].append({
            "source": ExternalDataSource.HANDELSREGISTER,
            "status": "available",
            "data": {
                "registered": True,
                "legal_form": entity.name.split()[-1] if entity.name else "Unknown",
                "registration_date": "2020-01-15",
            },
        })

        # Insolvenzregister (Mock - keine Insolvenz)
        external_data["sources_checked"].append({
            "source": ExternalDataSource.INSOLVENCY_REGISTER,
            "status": "available",
            "data": {
                "insolvency_proceedings": False,
                "last_checked": datetime.utcnow().isoformat(),
            },
        })

        # Creditreform (Mock - nicht implementiert)
        external_data["sources_checked"].append({
            "source": ExternalDataSource.CREDITREFORM,
            "status": "not_configured",
            "message": "API-Anbindung nicht konfiguriert",
        })

        # SCHUFA (Mock - nicht implementiert)
        external_data["sources_checked"].append({
            "source": ExternalDataSource.SCHUFA,
            "status": "not_configured",
            "message": "API-Anbindung nicht konfiguriert",
        })

        return external_data


async def get_risk_intelligence_service(db: AsyncSession) -> RiskIntelligenceService:
    """Factory fuer RiskIntelligenceService."""
    return RiskIntelligenceService(db)
