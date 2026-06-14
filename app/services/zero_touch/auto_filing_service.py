"""
Auto-Filing Service.

Bestimmt automatisch den Ablageort für Dokumente basierend auf:
- Dokumententyp -> Standard-Ordner-Mapping
- Geschäftspartner-Zuordnung -> Entity-Folder
- Firmenspezifische Regeln -> Custom Folder Assignments

Da im aktuellen System keine Folder-Struktur für normale Dokumente existiert
(nur PrivatFolder für Privat-Space), gibt dieser Service derzeit nur
Empfehlungen zurück, die in Zukunft implementiert werden können.
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
    reason: str  # Deutsche Erklärung


# Standard-Ordner-Mapping für Dokumententypen
# Diese werden in Zukunft verwendet, sobald ein Folder-System implementiert ist
DEFAULT_FOLDER_MAPPING = {
    "invoice": "Rechnungen",
    "contract": "Verträge",
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

    Aktuell gibt der Service Empfehlungen zurück, da das Haupt-Dokumentensystem
    noch keine Folder-Struktur hat. Die Logik ist vorbereitet für zukünftige
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
        Bestimmt den Ablageort für ein Dokument.

        Args:
            document_id: ID des Dokuments
            classification_type: Dokumententyp (invoice, contract, etc.)
            entity_id: Optional Geschäftspartner-ID
            company_id: Firmen-ID für Multi-Tenant
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

        # 1. Prüfen ob Entity einen Standard-Ordner hat
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

        # 2. Prüfen ob Firma Custom-Regeln hat
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
        Prüft ob ein Geschäftspartner einen Standard-Ordner hat.

        Args:
            entity_id: Geschäftspartner-ID
            company_id: Mandanten-ID für Multi-Tenant Isolation
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

        # Phase 11.1: Nutze default_folder_id wenn vorhanden
        if entity.default_folder_id:
            # Lade zugehoerigen Ordner für den Namen
            # Folder lebt in models_folder (nicht in models) -> sonst ImportError
            from app.db.models_folder import Folder

            folder = await db.get(Folder, entity.default_folder_id)
            if folder:
                logger.info(
                    "entity_default_folder_found",
                    entity_id=str(entity_id),
                    folder_id=str(folder.id),
                )
                return FilingResult(
                    folder_id=folder.id,
                    folder_name=folder.name,
                    confidence=0.98,
                    reason=f"Dokument wird im Standard-Ordner '{folder.name}' von '{entity.name}' abgelegt",
                )

        # Fallback: Ordner nach Entity-Name
        folder_name = f"{entity.name}"

        return FilingResult(
            folder_id=None,
            folder_name=folder_name,
            confidence=0.95,
            reason=f"Dokument gehoert zu Geschäftspartner '{entity.name}'",
        )

    async def _check_company_rules(
        self,
        company_id: UUID,
        classification_type: str,
        db: AsyncSession,
    ) -> Optional[FilingResult]:
        """
        Prüft firmenspezifische Filing-Regeln.

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

        # Phase 11.2: Nutze filing_rules JSONB wenn vorhanden
        if company.filing_rules and isinstance(company.filing_rules, dict):
            rule = company.filing_rules.get(classification_type.lower())

            if rule and isinstance(rule, dict):
                folder_id = rule.get("folder_id")
                folder_name = rule.get("folder_name")
                confidence = rule.get("confidence", 0.95)

                if folder_id or folder_name:
                    # Validiere folder_id wenn vorhanden
                    valid_folder_id = None
                    if folder_id:
                        try:
                            valid_folder_id = UUID(folder_id) if isinstance(folder_id, str) else folder_id
                        except ValueError:
                            logger.warning(
                                "invalid_folder_id_in_rule",
                                company_id=str(company_id),
                                folder_id=str(folder_id),
                            )

                    logger.info(
                        "company_filing_rule_matched",
                        company_id=str(company_id),
                        classification_type=classification_type,
                        folder_name=folder_name,
                    )

                    return FilingResult(
                        folder_id=valid_folder_id,
                        folder_name=folder_name or f"Custom-{classification_type}",
                        confidence=float(confidence),
                        reason=f"Firmenspezifische Regel: '{classification_type}' -> '{folder_name}'",
                    )

        # Keine Custom-Regel gefunden
        return None

    def _get_default_folder(
        self,
        classification_type: str,
    ) -> FilingResult:
        """
        Gibt Standard-Ordner für einen Dokumententyp zurück.

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
        Gibt verfügbare Ordner für eine Firma zurück.

        Args:
            company_id: Firmen-ID
            db: Datenbank-Session

        Returns:
            Liste von Ordnern mit {id, name}
        """
        # Aktuell keine Folder-Struktur vorhanden
        # Gibt Standard-Ordner zurück

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
            Diese Methode ist für zukünftige Erweiterung vorbereitet.
            Aktuell wird das globale Mapping verwendet.
        """
        logger.info(
            "default_folder_mapping_update_requested",
            new_mapping=new_mapping,
        )

        # Update global mapping (in-memory)
        global DEFAULT_FOLDER_MAPPING
        DEFAULT_FOLDER_MAPPING.update(new_mapping)

        logger.info(
            "default_folder_mapping_updated",
            updated_keys=list(new_mapping.keys()),
        )

    async def save_company_filing_rules(
        self,
        company_id: UUID,
        rules: dict[str, dict[str, any]],
        db: AsyncSession,
    ) -> bool:
        """
        Speichert firmenspezifische Filing-Regeln persistent.

        Args:
            company_id: Firmen-ID
            rules: Dict von Dokumententyp zu Regel {folder_id, folder_name, confidence}
            db: Datenbank-Session

        Returns:
            True bei Erfolg

        Example rules:
            {
                "invoice": {"folder_id": "uuid...", "folder_name": "Rechnungen/2026", "confidence": 0.95},
                "contract": {"folder_name": "Verträge/Aktiv", "confidence": 0.90}
            }
        """
        result = await db.execute(
            select(Company).where(Company.id == company_id)
        )
        company = result.scalar_one_or_none()

        if not company:
            logger.warning(
                "company_not_found_for_filing_rules",
                company_id=str(company_id),
            )
            return False

        # Merge mit bestehenden Regeln
        existing_rules = company.filing_rules or {}
        if isinstance(existing_rules, dict):
            existing_rules.update(rules)
        else:
            existing_rules = rules

        # Speichern in JSONB-Feld
        company.filing_rules = existing_rules
        await db.commit()

        logger.info(
            "company_filing_rules_saved",
            company_id=str(company_id),
            rule_count=len(rules),
        )

        return True

    async def get_company_filing_rules(
        self,
        company_id: UUID,
        db: AsyncSession,
    ) -> dict[str, dict[str, any]]:
        """
        Laedt firmenspezifische Filing-Regeln.

        Args:
            company_id: Firmen-ID
            db: Datenbank-Session

        Returns:
            Dict von Dokumententyp zu Regel
        """
        result = await db.execute(
            select(Company).where(Company.id == company_id)
        )
        company = result.scalar_one_or_none()

        if not company or not company.filing_rules:
            return {}

        return company.filing_rules if isinstance(company.filing_rules, dict) else {}

    async def delete_company_filing_rule(
        self,
        company_id: UUID,
        document_type: str,
        db: AsyncSession,
    ) -> bool:
        """
        Löscht eine firmenspezifische Filing-Regel.

        Args:
            company_id: Firmen-ID
            document_type: Dokumententyp (z.B. 'invoice')
            db: Datenbank-Session

        Returns:
            True bei Erfolg
        """
        result = await db.execute(
            select(Company).where(Company.id == company_id)
        )
        company = result.scalar_one_or_none()

        if not company or not company.filing_rules:
            return False

        if isinstance(company.filing_rules, dict) and document_type in company.filing_rules:
            del company.filing_rules[document_type]
            await db.commit()

            logger.info(
                "company_filing_rule_deleted",
                company_id=str(company_id),
                document_type=document_type,
            )
            return True

        return False
