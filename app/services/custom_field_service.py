# -*- coding: utf-8 -*-
"""
Custom Field Service fuer benutzerdefinierte Felder.

Verwaltet Felddefinitionen (CRUD) und Feldwerte auf Dokumenten.
Validiert Werte gegen Felddefinitionen und schuetzt vor SQL-Injection
bei JSONB-Abfragen (CWE-89).
"""

import re
from datetime import datetime, date
from typing import Dict, List, Optional, Sequence, Union
from uuid import UUID

import structlog
from sqlalchemy import select, update, and_, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document
from app.db.models_custom_fields import CustomFieldDefinition, FieldType
from app.api.schemas.custom_fields import FIELD_NAME_PATTERN, validate_field_name
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

# Erlaubte Lookup-Entitaeten (Whitelist)
ALLOWED_LOOKUP_ENTITIES = frozenset({
    "business_entity",
    "document",
    "user",
    "company",
    "tag",
})


class CustomFieldValidationError(Exception):
    """Fehler bei der Validierung eines benutzerdefinierten Feldwerts."""

    def __init__(self, field_name: str, message: str) -> None:
        self.field_name = field_name
        self.message = message
        super().__init__(f"Feld '{field_name}': {message}")


class CustomFieldService:
    """Service fuer benutzerdefinierte Felder."""

    # ------------------------------------------------------------------
    # Definition CRUD
    # ------------------------------------------------------------------

    async def create_definition(
        self,
        db: AsyncSession,
        *,
        name: str,
        label: str,
        field_type: str,
        company_id: UUID,
        user_id: UUID,
        description: Optional[str] = None,
        document_type: Optional[str] = None,
        required: bool = False,
        default_value: Optional[str] = None,
        validation_rules: Optional[Dict[str, Union[float, int, str, None]]] = None,
        dropdown_options: Optional[List[Dict[str, str]]] = None,
        lookup_entity: Optional[str] = None,
        sort_order: int = 0,
        is_searchable: bool = True,
        is_filterable: bool = True,
    ) -> CustomFieldDefinition:
        """Erstellt eine neue Felddefinition.

        Args:
            db: Datenbank-Session
            name: Interner Feldname (snake_case)
            label: Anzeige-Label (deutsch)
            field_type: Feldtyp
            company_id: Mandanten-ID
            user_id: Ersteller-ID
            description: Optionale Beschreibung
            document_type: Dokumenttyp-Filter
            required: Pflichtfeld
            default_value: Standardwert
            validation_rules: Validierungsregeln
            dropdown_options: Dropdown-Optionen
            lookup_entity: Lookup-Zielentitaet
            sort_order: Sortierreihenfolge
            is_searchable: In Suche einschliessen
            is_filterable: Als Filter anbieten

        Returns:
            Erstellte Felddefinition

        Raises:
            ValueError: Bei ungueltigem Feldnamen oder doppeltem Namen
        """
        # Feldnamen validieren (CWE-89)
        validate_field_name(name)

        # Feldtyp validieren
        try:
            FieldType(field_type)
        except ValueError:
            raise ValueError(
                f"Ungueltiger Feldtyp '{field_type}'. "
                f"Erlaubt: {', '.join(ft.value for ft in FieldType)}"
            )

        # Dropdown-Felder muessen Optionen haben
        if field_type in (FieldType.DROPDOWN.value, FieldType.MULTI_SELECT.value):
            if not dropdown_options or len(dropdown_options) == 0:
                raise ValueError(
                    f"Feldtyp '{field_type}' erfordert mindestens eine Option "
                    "in dropdown_options."
                )

        # Lookup-Entitaet validieren
        if field_type == FieldType.LOOKUP.value:
            if not lookup_entity:
                raise ValueError("Feldtyp 'lookup' erfordert lookup_entity.")
            if lookup_entity not in ALLOWED_LOOKUP_ENTITIES:
                raise ValueError(
                    f"Ungueltige Lookup-Entitaet '{lookup_entity}'. "
                    f"Erlaubt: {', '.join(sorted(ALLOWED_LOOKUP_ENTITIES))}"
                )

        # Pruefen ob Name bereits existiert (pro Mandant + Dokumenttyp)
        existing = await self._get_definition_by_name(
            db, company_id=company_id, name=name, document_type=document_type
        )
        if existing is not None:
            raise ValueError(
                f"Feld '{name}' existiert bereits fuer "
                f"Dokumenttyp '{document_type or 'alle'}'."
            )

        definition = CustomFieldDefinition(
            name=name,
            label=label,
            description=description,
            field_type=field_type,
            document_type=document_type,
            required=required,
            default_value=default_value,
            validation_rules=validation_rules,
            dropdown_options=dropdown_options,
            lookup_entity=lookup_entity,
            sort_order=sort_order,
            is_searchable=is_searchable,
            is_filterable=is_filterable,
            company_id=company_id,
            created_by=user_id,
        )
        db.add(definition)
        await db.flush()

        logger.info(
            "custom_field_definition_created",
            field_id=str(definition.id),
            name=name,
            field_type=field_type,
            company_id=str(company_id),
        )
        return definition

    async def update_definition(
        self,
        db: AsyncSession,
        *,
        field_id: UUID,
        company_id: UUID,
        updates: Dict[str, object],
    ) -> Optional[CustomFieldDefinition]:
        """Aktualisiert eine Felddefinition.

        Args:
            db: Datenbank-Session
            field_id: Feld-ID
            company_id: Mandanten-ID (Sicherheitspruefung)
            updates: Zu aktualisierende Felder

        Returns:
            Aktualisierte Felddefinition oder None
        """
        definition = await self._get_definition_by_id(db, field_id, company_id)
        if definition is None:
            return None

        allowed_fields = {
            "label", "description", "required", "default_value",
            "validation_rules", "dropdown_options", "sort_order",
            "is_searchable", "is_filterable", "is_active",
        }

        for key, value in updates.items():
            if key in allowed_fields:
                setattr(definition, key, value)

        await db.flush()

        logger.info(
            "custom_field_definition_updated",
            field_id=str(field_id),
            updated_fields=list(updates.keys()),
        )
        return definition

    async def delete_definition(
        self,
        db: AsyncSession,
        *,
        field_id: UUID,
        company_id: UUID,
    ) -> bool:
        """Soft-Delete einer Felddefinition (setzt is_active=False).

        Args:
            db: Datenbank-Session
            field_id: Feld-ID
            company_id: Mandanten-ID

        Returns:
            True wenn erfolgreich, False wenn nicht gefunden
        """
        definition = await self._get_definition_by_id(db, field_id, company_id)
        if definition is None:
            return False

        definition.is_active = False
        await db.flush()

        logger.info(
            "custom_field_definition_deleted",
            field_id=str(field_id),
        )
        return True

    async def list_definitions(
        self,
        db: AsyncSession,
        *,
        company_id: UUID,
        document_type: Optional[str] = None,
        include_inactive: bool = False,
    ) -> Sequence[CustomFieldDefinition]:
        """Listet Felddefinitionen fuer einen Mandanten.

        Args:
            db: Datenbank-Session
            company_id: Mandanten-ID
            document_type: Optional: nur fuer diesen Dokumenttyp
            include_inactive: Auch deaktivierte Felder anzeigen

        Returns:
            Liste von Felddefinitionen
        """
        conditions = [CustomFieldDefinition.company_id == company_id]

        if not include_inactive:
            conditions.append(CustomFieldDefinition.is_active.is_(True))

        if document_type is not None:
            # Felder die fuer diesen Typ oder alle Typen gelten
            conditions.append(
                (CustomFieldDefinition.document_type == document_type)
                | (CustomFieldDefinition.document_type.is_(None))
            )

        stmt = (
            select(CustomFieldDefinition)
            .where(and_(*conditions))
            .order_by(CustomFieldDefinition.sort_order, CustomFieldDefinition.name)
        )
        result = await db.execute(stmt)
        return result.scalars().all()

    async def get_definition(
        self,
        db: AsyncSession,
        *,
        field_id: UUID,
        company_id: UUID,
    ) -> Optional[CustomFieldDefinition]:
        """Holt eine einzelne Felddefinition.

        Args:
            db: Datenbank-Session
            field_id: Feld-ID
            company_id: Mandanten-ID

        Returns:
            Felddefinition oder None
        """
        return await self._get_definition_by_id(db, field_id, company_id)

    # ------------------------------------------------------------------
    # Field Values (auf Dokumenten)
    # ------------------------------------------------------------------

    async def set_field_values(
        self,
        db: AsyncSession,
        *,
        document_id: UUID,
        company_id: UUID,
        values: Dict[str, Union[str, int, float, bool, List[str], None]],
    ) -> Dict[str, Union[str, int, float, bool, List[str], None]]:
        """Setzt benutzerdefinierte Feldwerte auf einem Dokument.

        Validiert alle Werte gegen die Felddefinitionen.
        Bestehende Werte die nicht im Dict enthalten sind bleiben erhalten.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            company_id: Mandanten-ID
            values: Dict von Feldname -> Wert

        Returns:
            Aktualisiertes Werte-Dict

        Raises:
            CustomFieldValidationError: Bei ungueltigem Wert
            ValueError: Bei unbekanntem Feldnamen
        """
        # Dokument laden
        stmt = select(Document).where(
            and_(Document.id == document_id, Document.company_id == company_id)
        )
        result = await db.execute(stmt)
        document = result.scalar_one_or_none()
        if document is None:
            raise ValueError("Dokument nicht gefunden.")

        # Definitionen fuer diesen Mandanten laden
        definitions = await self.list_definitions(
            db, company_id=company_id, document_type=document.document_type
        )
        definitions_by_name: Dict[str, CustomFieldDefinition] = {
            d.name: d for d in definitions
        }

        # Alle Feldnamen validieren (CWE-89)
        for field_name in values:
            validate_field_name(field_name)
            if field_name not in definitions_by_name:
                raise ValueError(
                    f"Unbekanntes Feld '{field_name}' fuer Dokumenttyp "
                    f"'{document.document_type or 'alle'}'."
                )

        # Werte validieren
        for field_name, value in values.items():
            definition = definitions_by_name[field_name]
            self._validate_field_value(definition, field_name, value)

        # Bestehende Werte laden und mergen
        current_values: Dict[str, object] = dict(
            document.custom_field_values or {}
        )
        for field_name, value in values.items():
            if value is None:
                current_values.pop(field_name, None)
            else:
                current_values[field_name] = value

        # Update via SQL (vermeidet ORM-Tracking-Probleme bei JSONB)
        await db.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(custom_field_values=current_values)
        )

        logger.info(
            "custom_field_values_set",
            document_id=str(document_id),
            field_count=len(values),
        )
        return current_values

    async def get_field_values(
        self,
        db: AsyncSession,
        *,
        document_id: UUID,
        company_id: UUID,
    ) -> Dict[str, Union[str, int, float, bool, List[str], None]]:
        """Liest benutzerdefinierte Feldwerte eines Dokuments.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            company_id: Mandanten-ID

        Returns:
            Dict von Feldname -> Wert
        """
        stmt = select(Document.custom_field_values).where(
            and_(Document.id == document_id, Document.company_id == company_id)
        )
        result = await db.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return {}
        return dict(row) if row else {}

    async def search_by_custom_field(
        self,
        db: AsyncSession,
        *,
        field_name: str,
        value: Union[str, int, float, bool],
        company_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Document]:
        """Sucht Dokumente anhand eines benutzerdefinierten Feldwerts.

        Verwendet JSONB-Operatoren fuer effiziente Suche mit GIN-Index.

        SECURITY: Feldname wird gegen Whitelist validiert (CWE-89).

        Args:
            db: Datenbank-Session
            field_name: Feldname (wird validiert)
            value: Gesuchter Wert
            company_id: Mandanten-ID
            limit: Max. Ergebnisse
            offset: Offset fuer Pagination

        Returns:
            Liste von Dokumenten
        """
        # CWE-89: Feldnamen validieren bevor JSONB-Abfrage
        validate_field_name(field_name)

        # SQLAlchemy JSONB-Operator fuer sichere Abfrage
        # Verwendet den @> Operator (contains) mit parametrisierten Werten
        stmt = (
            select(Document)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                    Document.custom_field_values[field_name].as_string()
                    == str(value),
                )
            )
            .order_by(Document.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await db.execute(stmt)
        return result.scalars().all()

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_field_value(
        self,
        definition: CustomFieldDefinition,
        field_name: str,
        value: Union[str, int, float, bool, List[str], None],
    ) -> None:
        """Validiert einen einzelnen Feldwert gegen die Definition.

        Args:
            definition: Felddefinition
            field_name: Feldname (fuer Fehlermeldungen)
            value: Zu pruefender Wert

        Raises:
            CustomFieldValidationError: Bei ungueltigem Wert
        """
        field_type = definition.field_type

        # None = Feld loeschen (erlaubt wenn nicht Pflicht)
        if value is None:
            if definition.required:
                raise CustomFieldValidationError(
                    field_name, "Pflichtfeld darf nicht leer sein."
                )
            return

        # Typ-spezifische Validierung
        if field_type == FieldType.TEXT.value:
            self._validate_text(definition, field_name, value)
        elif field_type == FieldType.NUMBER.value:
            self._validate_number(definition, field_name, value)
        elif field_type == FieldType.DATE.value:
            self._validate_date(field_name, value)
        elif field_type == FieldType.BOOLEAN.value:
            self._validate_boolean(field_name, value)
        elif field_type == FieldType.DROPDOWN.value:
            self._validate_dropdown(definition, field_name, value)
        elif field_type == FieldType.MULTI_SELECT.value:
            self._validate_multi_select(definition, field_name, value)
        elif field_type == FieldType.LOOKUP.value:
            self._validate_lookup(field_name, value)

    def _validate_text(
        self,
        definition: CustomFieldDefinition,
        field_name: str,
        value: object,
    ) -> None:
        if not isinstance(value, str):
            raise CustomFieldValidationError(
                field_name, "Wert muss ein Text sein."
            )
        rules = definition.validation_rules or {}
        min_len = rules.get("min_length")
        max_len = rules.get("max_length")
        pattern = rules.get("pattern")

        if min_len is not None and len(value) < int(min_len):
            raise CustomFieldValidationError(
                field_name,
                f"Text muss mindestens {min_len} Zeichen lang sein.",
            )
        if max_len is not None and len(value) > int(max_len):
            raise CustomFieldValidationError(
                field_name,
                f"Text darf maximal {max_len} Zeichen lang sein.",
            )
        if pattern is not None:
            try:
                if not re.match(str(pattern), value):
                    raise CustomFieldValidationError(
                        field_name,
                        f"Text entspricht nicht dem Muster '{pattern}'.",
                    )
            except re.error:
                raise CustomFieldValidationError(
                    field_name,
                    "Ungueltiges Validierungsmuster in Felddefinition.",
                )

    def _validate_number(
        self,
        definition: CustomFieldDefinition,
        field_name: str,
        value: object,
    ) -> None:
        if not isinstance(value, (int, float)):
            raise CustomFieldValidationError(
                field_name, "Wert muss eine Zahl sein."
            )
        rules = definition.validation_rules or {}
        min_val = rules.get("min_value")
        max_val = rules.get("max_value")

        if min_val is not None and value < float(min_val):
            raise CustomFieldValidationError(
                field_name,
                f"Wert muss mindestens {min_val} sein.",
            )
        if max_val is not None and value > float(max_val):
            raise CustomFieldValidationError(
                field_name,
                f"Wert darf maximal {max_val} sein.",
            )

    def _validate_date(self, field_name: str, value: object) -> None:
        if not isinstance(value, str):
            raise CustomFieldValidationError(
                field_name, "Datum muss als Text im Format YYYY-MM-DD angegeben werden."
            )
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            raise CustomFieldValidationError(
                field_name,
                f"Ungueltiges Datum '{value}'. Format: YYYY-MM-DD",
            )

    def _validate_boolean(self, field_name: str, value: object) -> None:
        if not isinstance(value, bool):
            raise CustomFieldValidationError(
                field_name, "Wert muss true oder false sein."
            )

    def _validate_dropdown(
        self,
        definition: CustomFieldDefinition,
        field_name: str,
        value: object,
    ) -> None:
        if not isinstance(value, str):
            raise CustomFieldValidationError(
                field_name, "Wert muss ein Text sein."
            )
        options = definition.dropdown_options or []
        allowed = {opt.get("value", opt) if isinstance(opt, dict) else str(opt) for opt in options}
        if value not in allowed:
            raise CustomFieldValidationError(
                field_name,
                f"Wert '{value}' ist keine gueltige Option. "
                f"Erlaubt: {', '.join(sorted(allowed))}",
            )

    def _validate_multi_select(
        self,
        definition: CustomFieldDefinition,
        field_name: str,
        value: object,
    ) -> None:
        if not isinstance(value, list):
            raise CustomFieldValidationError(
                field_name, "Wert muss eine Liste sein."
            )
        options = definition.dropdown_options or []
        allowed = {opt.get("value", opt) if isinstance(opt, dict) else str(opt) for opt in options}
        for item in value:
            if not isinstance(item, str):
                raise CustomFieldValidationError(
                    field_name, "Jeder Wert in der Liste muss ein Text sein."
                )
            if item not in allowed:
                raise CustomFieldValidationError(
                    field_name,
                    f"Wert '{item}' ist keine gueltige Option. "
                    f"Erlaubt: {', '.join(sorted(allowed))}",
                )

    def _validate_lookup(self, field_name: str, value: object) -> None:
        """Lookup-Werte muessen gueltige UUIDs sein."""
        if not isinstance(value, str):
            raise CustomFieldValidationError(
                field_name, "Lookup-Wert muss eine UUID als Text sein."
            )
        uuid_pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            re.IGNORECASE,
        )
        if not uuid_pattern.match(value):
            raise CustomFieldValidationError(
                field_name,
                f"Ungueltiges UUID-Format: '{value}'.",
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _get_definition_by_id(
        self,
        db: AsyncSession,
        field_id: UUID,
        company_id: UUID,
    ) -> Optional[CustomFieldDefinition]:
        """Holt eine Felddefinition per ID mit Mandanten-Check."""
        stmt = select(CustomFieldDefinition).where(
            and_(
                CustomFieldDefinition.id == field_id,
                CustomFieldDefinition.company_id == company_id,
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_definition_by_name(
        self,
        db: AsyncSession,
        *,
        company_id: UUID,
        name: str,
        document_type: Optional[str],
    ) -> Optional[CustomFieldDefinition]:
        """Holt eine Felddefinition per Name (Eindeutigkeit pruefen)."""
        conditions = [
            CustomFieldDefinition.company_id == company_id,
            CustomFieldDefinition.name == name,
        ]
        if document_type is not None:
            conditions.append(CustomFieldDefinition.document_type == document_type)
        else:
            conditions.append(CustomFieldDefinition.document_type.is_(None))

        stmt = select(CustomFieldDefinition).where(and_(*conditions))
        result = await db.execute(stmt)
        return result.scalar_one_or_none()


# Singleton-Instanz
_custom_field_service: Optional[CustomFieldService] = None


def get_custom_field_service() -> CustomFieldService:
    """Liefert die Singleton-Instanz des CustomFieldService."""
    global _custom_field_service
    if _custom_field_service is None:
        _custom_field_service = CustomFieldService()
    return _custom_field_service
