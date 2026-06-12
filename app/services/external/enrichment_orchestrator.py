"""
External Data Enrichment Orchestrator.

Orchestriert verschiedene externe Datenquellen zur Anreicherung von
Geschäftspartnern (BusinessEntity).

Features:
- Handelsregister-Abfrage (Mock)
- Bundesanzeiger-Abfrage (Mock)
- Redis-Caching mit 6-Monats-TTL
- Multi-Tenant Isolation
- Confidence-Scoring

WICHTIG: Derzeit Mock-Implementierung. Echte APIs erfordern Registrierung.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BusinessEntity
from app.core.security.sensitive_data_filter import get_pii_safe_logger
from app.core.safe_errors import safe_error_log
from app.services.external.handelsregister_service import (
    HandelsregisterService,
    CompanyRecord,
)
from app.services.external.bundesanzeiger_service import (

    BundesanzeigerService,
    InsolvencyResult,
)

logger = get_pii_safe_logger(__name__)


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class EnrichmentResult:
    """Ergebnis einer Entity-Anreicherung."""

    entity_id: UUID
    sources_queried: List[str]
    enriched_fields: Dict[str, Any]
    confidence: float  # 0.0 - 1.0
    cached: bool
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SourceInfo:
    """Informationen über eine Datenquelle."""

    name: str
    description: str  # German
    available: bool
    last_checked: Optional[datetime] = None


# ============================================================================
# ENRICHMENT ORCHESTRATOR
# ============================================================================


class EnrichmentOrchestrator:
    """Orchestriert externe Datenquellen für Entity-Anreicherung."""

    def __init__(self) -> None:
        """Initialisiert Orchestrator mit Services."""
        self.handelsregister = HandelsregisterService()
        self.bundesanzeiger = BundesanzeigerService()

    # ========================================================================
    # PUBLIC API
    # ========================================================================

    async def enrich_entity(
        self,
        entity_id: UUID,
        company_id: UUID,
        sources: Optional[List[str]],
        db: AsyncSession,
    ) -> EnrichmentResult:
        """
        Reichert Entity mit externen Daten an.

        Args:
            entity_id: BusinessEntity-ID
            company_id: Company-ID (Multi-Tenant)
            sources: Optional Liste von Quellen (handelsregister, bundesanzeiger)
                     None = alle verfügbaren Quellen
            db: Datenbank-Session

        Returns:
            EnrichmentResult mit angereicherten Daten

        Raises:
            ValueError: Entity nicht gefunden oder keine Berechtigung
        """
        logger.info(
            "enrichment_started",
            entity_id=str(entity_id),
            company_id=str(company_id),
            sources=sources,
        )

        # Entity abrufen
        stmt = select(BusinessEntity).where(
            BusinessEntity.id == entity_id,
            BusinessEntity.company_id == company_id,
        )
        result = await db.execute(stmt)
        entity = result.scalar_one_or_none()

        if not entity:
            raise ValueError("Geschäftspartner nicht gefunden oder keine Berechtigung")

        # Quellen bestimmen
        if sources is None:
            sources = ["handelsregister", "bundesanzeiger"]

        enriched_fields: Dict[str, Any] = {}
        sources_queried: List[str] = []
        total_confidence = 0.0

        # Handelsregister
        if "handelsregister" in sources:
            try:
                hr_data = await self._query_handelsregister(entity)
                if hr_data:
                    enriched_fields.update(hr_data)
                    sources_queried.append("handelsregister")
                    # Volle Punktzahl pro erfolgreich liefernder Quelle —
                    # vorher 0.5, wodurch die Confidence nie ueber 0.5 kam.
                    total_confidence += 1.0
            except Exception as e:
                logger.warning(
                    "handelsregister_query_failed",
                    **safe_error_log(e),
                    entity_id=str(entity_id),
                )

        # Bundesanzeiger
        if "bundesanzeiger" in sources:
            try:
                ba_data = await self._query_bundesanzeiger(entity)
                if ba_data:
                    enriched_fields.update(ba_data)
                    sources_queried.append("bundesanzeiger")
                    total_confidence += 1.0
            except Exception as e:
                logger.warning(
                    "bundesanzeiger_query_failed",
                    **safe_error_log(e),
                    entity_id=str(entity_id),
                )

        # Confidence berechnen: Anteil erfolgreich liefernder Quellen
        confidence = (
            total_confidence / len(sources) if sources else 0.0
        )

        # HINWEIS: BusinessEntity hat KEINE metadata-Spalte (SQLAlchemy
        # reserviert .metadata fuer die Registry) — der fruehere Versuch
        # `entity.metadata["enrichment"] = ...` crashte mit TypeError.
        # Persistenz der Enrichment-Historie braucht eine Schema-Erweiterung
        # (Followup); bis dahin wird das Ergebnis nur zurueckgegeben.

        logger.info(
            "enrichment_completed",
            entity_id=str(entity_id),
            sources_queried=sources_queried,
            fields_enriched=len(enriched_fields),
            confidence=confidence,
        )

        return EnrichmentResult(
            entity_id=entity_id,
            sources_queried=sources_queried,
            enriched_fields=enriched_fields,
            confidence=confidence,
            cached=False,
        )

    async def get_available_sources(self) -> List[SourceInfo]:
        """
        Gibt verfügbare Datenquellen zurück.

        Returns:
            Liste von SourceInfo-Objekten
        """
        sources = [
            SourceInfo(
                name="handelsregister",
                description="Handelsregister-Abfrage (Mock)",
                available=True,
                last_checked=datetime.utcnow(),
            ),
            SourceInfo(
                name="bundesanzeiger",
                description="Bundesanzeiger Insolvenzbekanntmachungen (Mock)",
                available=True,
                last_checked=datetime.utcnow(),
            ),
        ]

        logger.debug("available_sources_retrieved", count=len(sources))
        return sources

    # ========================================================================
    # PRIVATE HELPERS
    # ========================================================================

    async def _query_handelsregister(
        self, entity: BusinessEntity
    ) -> Optional[Dict[str, Any]]:
        """Fragt Handelsregister ab."""
        if not entity.name:
            return None

        # Mock-Abfrage
        results = await self.handelsregister.search_company(
            name=entity.name,
            location=entity.city,
        )

        if not results:
            return None

        # Erstes Ergebnis nehmen
        company = results[0]

        enriched = {}
        if company.legal_form and not entity.legal_form:
            enriched["legal_form"] = company.legal_form

        if company.register_number:
            enriched["register_number"] = company.register_number

        if company.registered_address:
            enriched["registered_address"] = company.registered_address

        if company.founded_date:
            enriched["founded_date"] = company.founded_date

        if company.capital:
            enriched["capital"] = company.capital

        return enriched if enriched else None

    async def _query_bundesanzeiger(
        self, entity: BusinessEntity
    ) -> Optional[Dict[str, Any]]:
        """Fragt Bundesanzeiger ab."""
        if not entity.name:
            return None

        # Mock-Abfrage
        result = await self.bundesanzeiger.check_insolvency(
            company_name=entity.name
        )

        # Erfolgreich befragt: auch ein SAUBERER Befund (keine Insolvenz —
        # der Normalfall) ist ein echtes Ergebnis und zaehlt als befragte
        # Quelle. Vorher wurde hier None geliefert und die Quelle fehlte in
        # sources_queried/Confidence.
        enriched: Dict[str, Any] = {
            "insolvency_warning": result.has_insolvency,
        }
        if result.has_insolvency:
            enriched["insolvency_count"] = result.count

        if result.publications:
            enriched["insolvency_publications"] = [
                {
                    "date": pub.publication_date.isoformat(),
                    "type": pub.publication_type,
                    "court": pub.court,
                }
                for pub in result.publications[:3]  # Max 3
            ]

        return enriched
