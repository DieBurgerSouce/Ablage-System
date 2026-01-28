"""
Handelsregister Service (Mock Implementation).

Bietet Schnittstelle für Handelsregister-Abfragen.

HINWEIS: Dies ist eine Mock-Implementierung. Die echte API erfordert:
- Registrierung bei handelsregister.de oder offeneregister.de
- API-Key
- Kostenpflichtige Abfragen

Für Production: Implementiere echte API-Calls basierend auf gewähltem Provider.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class CompanyRecord:
    """Handelsregister-Eintrag einer Firma."""

    name: str
    legal_form: Optional[str] = None  # GmbH, AG, UG, etc.
    register_court: Optional[str] = None  # z.B. "Amtsgericht München"
    register_number: Optional[str] = None  # HRB 123456
    registered_address: Optional[str] = None
    founded_date: Optional[str] = None  # ISO format
    capital: Optional[str] = None  # z.B. "25.000 EUR"
    managing_directors: Optional[List[str]] = None
    status: str = "active"  # active, dissolved, in_liquidation


@dataclass
class CompanyDetails:
    """Detaillierte Firmendaten."""

    record: CompanyRecord
    shareholders: Optional[List[str]] = None
    business_purpose: Optional[str] = None
    history: Optional[List[dict]] = None  # Änderungshistorie


# ============================================================================
# HANDELSREGISTER SERVICE
# ============================================================================


class HandelsregisterService:
    """Service für Handelsregister-Abfragen (Mock)."""

    def __init__(self) -> None:
        """Initialisiert Service."""
        self.mock_enabled = True  # In Production: False

    # ========================================================================
    # PUBLIC API
    # ========================================================================

    async def search_company(
        self, name: str, location: Optional[str] = None
    ) -> List[CompanyRecord]:
        """
        Sucht Firmen im Handelsregister.

        Args:
            name: Firmenname (oder Teil davon)
            location: Optional Ort zur Einschränkung

        Returns:
            Liste von CompanyRecord-Objekten
        """
        logger.info(
            "handelsregister_search_requested",
            name=name,
            location=location,
            mock=self.mock_enabled,
        )

        if self.mock_enabled:
            return self._mock_search(name, location)

        # TODO: Echte API-Implementierung
        # try:
        #     response = await self._api_client.search(name=name, location=location)
        #     return self._parse_search_results(response)
        # except Exception as e:
        #     logger.error("handelsregister_api_error", error=str(e))
        #     return []

        return []

    async def get_company_details(self, register_id: str) -> Optional[CompanyDetails]:
        """
        Ruft detaillierte Firmendaten ab.

        Args:
            register_id: Handelsregister-ID (z.B. "HRB 123456")

        Returns:
            CompanyDetails oder None
        """
        logger.info(
            "handelsregister_details_requested",
            register_id=register_id,
            mock=self.mock_enabled,
        )

        if self.mock_enabled:
            return self._mock_details(register_id)

        # TODO: Echte API-Implementierung
        return None

    # ========================================================================
    # MOCK HELPERS
    # ========================================================================

    def _mock_search(
        self, name: str, location: Optional[str] = None
    ) -> List[CompanyRecord]:
        """Mock-Suche für Entwicklung/Tests."""
        # Simuliere verschiedene Firmentypen
        mock_results = []

        name_lower = name.lower()

        # GmbH
        if "gmbh" in name_lower or "gesellschaft" in name_lower:
            mock_results.append(
                CompanyRecord(
                    name=f"{name} GmbH",
                    legal_form="GmbH",
                    register_court="Amtsgericht München",
                    register_number="HRB 234567",
                    registered_address=f"Musterstraße 123, 80331 München",
                    founded_date="2015-03-15",
                    capital="25.000 EUR",
                    managing_directors=["Max Mustermann"],
                    status="active",
                )
            )

        # AG
        if "ag" in name_lower or len(name) > 20:
            mock_results.append(
                CompanyRecord(
                    name=f"{name} AG",
                    legal_form="AG",
                    register_court="Amtsgericht Frankfurt am Main",
                    register_number="HRB 98765",
                    registered_address=f"Börsenplatz 1, 60313 Frankfurt",
                    founded_date="2005-06-20",
                    capital="50.000.000 EUR",
                    managing_directors=["Dr. Anna Schmidt", "Thomas Weber"],
                    status="active",
                )
            )

        # UG (haftungsbeschränkt)
        if "ug" in name_lower or "startup" in name_lower:
            mock_results.append(
                CompanyRecord(
                    name=f"{name} UG (haftungsbeschränkt)",
                    legal_form="UG",
                    register_court="Amtsgericht Berlin",
                    register_number="HRB 187654",
                    registered_address=f"Startupstraße 42, 10115 Berlin",
                    founded_date="2020-01-10",
                    capital="1.000 EUR",
                    managing_directors=["Lisa Müller"],
                    status="active",
                )
            )

        # Einzelunternehmen (nicht im HRB, aber zur Demo)
        if not mock_results:
            mock_results.append(
                CompanyRecord(
                    name=name,
                    legal_form="Einzelunternehmen",
                    register_court=None,
                    register_number=None,
                    registered_address=f"{location or 'Musterstadt'}",
                    founded_date="2018-08-01",
                    capital=None,
                    managing_directors=[name],
                    status="active",
                )
            )

        logger.debug(
            "handelsregister_mock_search_completed",
            results_count=len(mock_results),
        )

        return mock_results

    def _mock_details(self, register_id: str) -> Optional[CompanyDetails]:
        """Mock-Details für Entwicklung/Tests."""
        record = CompanyRecord(
            name="Muster GmbH",
            legal_form="GmbH",
            register_court="Amtsgericht München",
            register_number=register_id,
            registered_address="Musterstraße 123, 80331 München",
            founded_date="2015-03-15",
            capital="25.000 EUR",
            managing_directors=["Max Mustermann", "Erika Musterfrau"],
            status="active",
        )

        details = CompanyDetails(
            record=record,
            shareholders=["Holding GmbH (51%)", "Privatpersonen (49%)"],
            business_purpose="Softwareentwicklung und IT-Beratung",
            history=[
                {
                    "date": "2015-03-15",
                    "type": "Gründung",
                    "description": "Eintragung ins Handelsregister",
                },
                {
                    "date": "2018-06-20",
                    "type": "Kapitalerhöhung",
                    "description": "Stammkapital von 10.000 auf 25.000 EUR erhöht",
                },
                {
                    "date": "2020-11-05",
                    "type": "Geschäftsführerwechsel",
                    "description": "Erika Musterfrau zur Geschäftsführerin bestellt",
                },
            ],
        )

        logger.debug("handelsregister_mock_details_returned", register_id=register_id)

        return details
