"""
Auto-Filing Service.

Bestimmt automatisch den Ablageort fuer Dokumente basierend auf:
- Dokumententyp -> Standard-Ordner-Mapping
- Geschaeftspartner-Zuordnung -> Entity-Folder
- Firmenspezifische Regeln -> Custom Folder Assignments

Da im aktuellen System keine Folder-Struktur fuer normale Dokumente existiert
(nur PrivatFolder fuer Privat-Space), gibt dieser Service derzeit nur
Empfehlungen zurueck, die in Zukunft implementiert werden koennen.
"""

from dataclasses import dataclass
from typing import Optional
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BusinessEntity, Company

logger = structlog.get_logger(__name__)


@dataclass
class FilingResult:
    """Ergebnis der Auto-Filing-Bestimmung."""

    folder_id: Optional[UUID]
    folder_name: Optional[str]
    confidence: float
    reason: str  # Deutsche Erklaerung


# Standard-Ordner-Mapping fuer Dokumententypen
# Diese werden in Zukunft verwendet, sobald ein Folder-System implementiert ist
DEFAULT_FOLDER_MAPPING = {
    "invoice": "Rechnungen",
    "contract": "Vertraege",
    "delivery_note": "Lieferscheine",
    "order": "Bestellungen",
    "offer": "Angebote",
    "receipt": "Belege",
    "correspondence": "Korrespondenz",
    "other": "Sonstiges",
}


class AutoFilingService:
    """
    Service zur automatischen Bestimmung des Ablageorts.

    Aktuell gibt der Service Empfehlungen zurueck, da das Haupt-Dokumentensystem
    noch keine Folder-Struktur hat. Die Logik ist vorbereitet fuer zukuenftige
    Implementierung.
    """

    async def determine_filing(
        self,
        document_id: UUID,
        classification_type: str,
        entity_id: Optional[UUID],
        company_id: UUID,
        db: AsyncSession,
    ) -> FilingResult:
        """
        Bestimmt den Ablageort fuer ein Dokument.

        Args:
            document_id: ID des Dokuments
            classification_type: Dokumententyp (invoice, contract, etc.)
            entity_id: Optional Geschaeftspartner-ID
            company_id: Firmen-ID fuer Multi-Tenant
            db: Datenbank-Session

        Returns:
            FilingResult mit Ordner-Empfehlung und Begruendung
        """
        logger.info(
            "determining_filing_location",
            document_id=str(document_id),
            classification_type=classification_type,
            has_entity=entity_id is not None,
            company_id=str(company_id),
        )

        # 1. Pruefen ob Entity einen Standard-Ordner hat
        if entity_id is not None:
            entity_filing = await self._check_entity_folder(
                entity_id=entity_id,
                company_id=company_id,
                db=db,
            )
            if entity_filing is not None:
                logger.info(
                    "filing_determined_by_entity",
                    entity_id=str(entity_id),
                    folder_name=entity_filing.folder_name,
                )
                return entity_filing

        # 2. Pruefen ob Firma Custom-Regeln hat
        company_filing = await self._check_company_rules(
            company_id=company_id,
            classification_type=classification_type,
            db=db,
        )
        if company_filing is not None:
            logger.info(
                "filing_determined_by_company_rules",
                company_id=str(company_id),
                folder_name=company_filing.folder_name,
            )
            return company_filing

        # 3. Standard-Mapping basierend auf Dokumententyp
        default_filing = self._get_default_folder(classification_type)

        logger.info(
            "filing_determined_by_default",
            classification_type=classification_type,
            folder_name=default_filing.folder_name,
        )

        return default_filing

    async def _check_entity_folder(
        self,
        entity_id: UUID,
        company_id: UUID,
        db: AsyncSession,
    ) -> Optional[FilingResult]:
        """
        Prueft ob ein Geschaeftspartner einen Standard-Ordner hat.

        Args:
            entity_id: Geschaeftspartner-ID
            company_id: Mandanten-ID fuer Multi-Tenant Isolation
            db: Datenbank-Session

        Returns:
            FilingResult falls Ordner vorhanden, sonst None
        """
        from sqlalchemy import and_

        # SECURITY FIX: Entity abrufen mit company_id Filter
        result = await db.execute(
            select(BusinessEntity).where(
                and_(
                    BusinessEntity.id == entity_id,
                    BusinessEntity.company_id == company_id,
                )
            )
        )
        entity = result.scalar_one_or_none()

        if not entity:
            logger.warning(
                "entity_not_found_for_filing",
                entity_id=str(entity_id),
            )
            return None

        # Aktuell haben BusinessEntities noch kein default_folder_id Feld
        # Dies ist fuer zukuenftige Erweiterung vorbereitet
        # TODO: Add default_folder_id to BusinessEntity model

        # Vorschlag: Ordner nach Entity-Name erstellen
        folder_name = f"{entity.name}"

        return FilingResult(
            folder_id=None,  # Noch nicht implementiert
            folder_name=folder_name,
            confidence=0.95,
            reason=f"Dokument gehoert zu Geschaeftspartner '{entity.name}'",
        )

    async def _check_company_rules(
        self,
        company_id: UUID,
        classification_type: str,
        db: AsyncSession,
    ) -> Optional[FilingResult]:
        """
        Prueft firmenspezifische Filing-Regeln.

        Args:
            company_id: Firmen-ID
            classification_type: Dokumententyp
            db: Datenbank-Session

        Returns:
            FilingResult falls Custom-Regel vorhanden, sonst None
        """
        # Company abrufen
        result = await db.execute(
            select(Company).where(Company.id == company_id)
        )
        company = result.scalar_one_or_none()

        if not company:
            logger.warning(
                "company_not_found_for_filing",
                company_id=str(company_id),
            )
            return None

        # Custom Filing Rules sind noch nicht im Company-Model implementiert
        # Dies ist fuer zukuenftige Erweiterung vorbereitet
        # TODO: Add filing_rules JSONB field to Company model
        # Format: {"invoice": {"folder_id": "uuid", "folder_name": "Custom"}}

        # Vorlaeufig: Keine Custom-Regeln
        return None

    def _get_default_folder(
        self,
        classification_type: str,
    ) -> FilingResult:
        """
        Gibt Standard-Ordner fuer einen Dokumententyp zurueck.

        Args:
            classification_type: Dokumententyp

        Returns:
            FilingResult mit Standard-Ordner
        """
        # Ordnername aus Mapping
        folder_name = DEFAULT_FOLDER_MAPPING.get(
            classification_type,
            DEFAULT_FOLDER_MAPPING["other"],
        )

        # Begruendung
        if classification_type in DEFAULT_FOLDER_MAPPING:
            reason = f"Dokument vom Typ '{classification_type}' wird standardmaessig in '{folder_name}' abgelegt"
        else:
            reason = f"Unbekannter Dokumententyp '{classification_type}' wird in '{folder_name}' abgelegt"

        return FilingResult(
            folder_id=None,  # Noch nicht implementiert
            folder_name=folder_name,
            confidence=0.80,
            reason=reason,
        )

    async def get_available_folders(
        self,
        company_id: UUID,
        db: AsyncSession,
    ) -> list[dict[str, str]]:
        """
        Gibt verfuegbare Ordner fuer eine Firma zurueck.

        Args:
            company_id: Firmen-ID
            db: Datenbank-Session

        Returns:
            Liste von Ordnern mit {id, name}
        """
        # Aktuell keine Folder-Struktur vorhanden
        # Gibt Standard-Ordner zurueck

        folders = []
        for doc_type, folder_name in DEFAULT_FOLDER_MAPPING.items():
            folders.append({
                "id": None,  # Noch nicht implementiert
                "name": folder_name,
                "doc_type": doc_type,
            })

        logger.debug(
            "available_folders_retrieved",
            company_id=str(company_id),
            folder_count=len(folders),
        )

        return folders

    def update_default_mapping(
        self,
        new_mapping: dict[str, str],
    ) -> None:
        """
        Aktualisiert das Standard-Ordner-Mapping.

        Args:
            new_mapping: Neues Mapping von Dokumententyp zu Ordnername

        Note:
            Diese Methode ist fuer zukuenftige Erweiterung vorbereitet.
            Aktuell wird das globale Mapping verwendet.
        """
        logger.info(
            "default_folder_mapping_update_requested",
            new_mapping=new_mapping,
        )

        # TODO: Implement persistent storage of custom mappings
        # in AppConfig or Company settings

        logger.warning(
            "default_folder_mapping_update_not_yet_implemented",
            message="Custom Folder Mappings werden erst in zukuenftiger Version unterstuetzt",
        )
