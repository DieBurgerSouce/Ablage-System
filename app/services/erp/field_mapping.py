"""
ERP Field Mapping Service.

Enterprise-Level Feld-Transformation:
- Bidirektionale Feld-Mappings
- Datentyp-Transformatoren
- Custom-Mapping pro Company
- Validierung und Defaults

Feinpoliert und durchdacht - Flexible Feld-Mappings.
"""

import structlog
from abc import ABC, abstractmethod
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, List, Optional, Type, Union

# Type alias for transformed values from ERP field transformations
TransformedValue = Union[str, int, float, bool, Decimal, datetime, date, Dict[str, object], None]
from uuid import UUID

logger = structlog.get_logger(__name__)


# =============================================================================
# Field Transformers
# =============================================================================


class FieldTransformer(ABC):
    """Abstrakte Basisklasse für Feld-Transformatoren."""

    @abstractmethod
    def to_erp(self, value: TransformedValue, config: Optional[Dict[str, object]] = None) -> TransformedValue:
        """Transformiert Wert für ERP-System."""
        pass

    @abstractmethod
    def from_erp(self, value: TransformedValue, config: Optional[Dict[str, object]] = None) -> TransformedValue:
        """Transformiert Wert aus ERP-System."""
        pass


class PassthroughTransformer(FieldTransformer):
    """Keine Transformation - Wert durchreichen."""

    def to_erp(self, value: TransformedValue, config: Optional[Dict[str, object]] = None) -> TransformedValue:
        return value

    def from_erp(self, value: TransformedValue, config: Optional[Dict[str, object]] = None) -> TransformedValue:
        return value


class DateTransformer(FieldTransformer):
    """Datums-Transformation (ISO <-> Odoo Format)."""

    def to_erp(self, value: TransformedValue, config: Optional[Dict[str, object]] = None) -> Optional[str]:
        """Konvertiert Python date/datetime zu Odoo-Format."""
        if value is None:
            return None

        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        elif isinstance(value, date):
            return value.strftime("%Y-%m-%d")
        elif isinstance(value, str):
            return value
        return str(value)

    def from_erp(self, value: TransformedValue, config: Optional[Dict[str, object]] = None) -> Optional[datetime]:
        """Konvertiert Odoo-Format zu Python datetime."""
        if value is None or value is False:
            return None

        if isinstance(value, (datetime, date)):
            return value if isinstance(value, datetime) else datetime.combine(value, datetime.min.time())

        if isinstance(value, str):
            try:
                # Try datetime format first
                return datetime.fromisoformat(value.replace(" ", "T").replace("Z", "+00:00"))
            except ValueError:
                try:
                    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    try:
                        return datetime.strptime(value, "%Y-%m-%d")
                    except ValueError:
                        logger.warning("date_transform_failed", value=value)
                        return None
        return None


class CurrencyTransformer(FieldTransformer):
    """Währungs-Transformation (Decimal <-> Float)."""

    def to_erp(self, value: TransformedValue, config: Optional[Dict[str, object]] = None) -> Optional[float]:
        """Konvertiert Decimal zu Float für ERP."""
        if value is None:
            return None

        if isinstance(value, Decimal):
            return float(value)
        elif isinstance(value, (int, float)):
            return float(value)
        elif isinstance(value, str):
            try:
                return float(value.replace(",", "."))
            except ValueError:
                return None
        return None

    def from_erp(self, value: TransformedValue, config: Optional[Dict[str, object]] = None) -> Optional[Decimal]:
        """Konvertiert Float zu Decimal aus ERP."""
        if value is None or value is False:
            return None

        try:
            return Decimal(str(value))
        except (ValueError, TypeError):
            return None


class BooleanTransformer(FieldTransformer):
    """Boolean-Transformation (Odoo False = None)."""

    def to_erp(self, value: TransformedValue, config: Optional[Dict[str, object]] = None) -> bool:
        """Konvertiert zu Boolean für ERP."""
        if value is None:
            return False
        return bool(value)

    def from_erp(self, value: TransformedValue, config: Optional[Dict[str, object]] = None) -> bool:
        """Konvertiert Boolean aus ERP (False = None in Odoo)."""
        if value is None or value is False:
            return False
        return bool(value)


class LookupTransformer(FieldTransformer):
    """Lookup-Transformation für Related Fields (z.B. country_id)."""

    def to_erp(self, value: TransformedValue, config: Optional[Dict[str, object]] = None) -> Optional[int]:
        """Konvertiert UUID oder ID zu ERP-ID."""
        if value is None:
            return None

        config = config or {}
        lookup_table = config.get("lookup_table", {})

        if isinstance(value, UUID):
            value = str(value)

        # Check lookup table
        if value in lookup_table:
            return lookup_table[value]

        # Try to parse as int
        if isinstance(value, (int, str)):
            try:
                return int(value)
            except ValueError:
                return None

        return None

    def from_erp(self, value: TransformedValue, config: Optional[Dict[str, object]] = None) -> Optional[str]:
        """Konvertiert ERP-ID zu lokalem Wert."""
        if value is None or value is False:
            return None

        config = config or {}
        reverse_lookup = config.get("reverse_lookup", {})

        # Odoo returns [id, name] for many2one
        if isinstance(value, (list, tuple)) and len(value) >= 1:
            erp_id = value[0]
            if erp_id in reverse_lookup:
                return reverse_lookup[erp_id]
            return str(erp_id)

        if isinstance(value, int):
            if value in reverse_lookup:
                return reverse_lookup[value]
            return str(value)

        return str(value) if value else None


class StringNormalizer(FieldTransformer):
    """String-Normalisierung (Trimmen, None-Handling)."""

    def to_erp(self, value: TransformedValue, config: Optional[Dict[str, object]] = None) -> str:
        """Normalisiert String für ERP."""
        if value is None or value is False:
            return ""

        result = str(value).strip()
        config = config or {}

        # Max length
        max_length = config.get("max_length")
        if max_length and len(result) > max_length:
            result = result[:max_length]

        return result

    def from_erp(self, value: TransformedValue, config: Optional[Dict[str, object]] = None) -> Optional[str]:
        """Normalisiert String aus ERP."""
        if value is None or value is False:
            return None

        return str(value).strip() or None


class AddressTransformer(FieldTransformer):
    """Adress-Transformation (Dict <-> einzelne Felder)."""

    def to_erp(self, value: TransformedValue, config: Optional[Dict[str, object]] = None) -> Dict[str, str]:
        """Konvertiert Address-Dict zu flachen Feldern."""
        if not isinstance(value, dict):
            return {}

        return {
            "street": value.get("street", "") or "",
            "street2": value.get("street2", "") or "",
            "city": value.get("city", "") or "",
            "zip": value.get("zip", "") or "",
            "state_id": value.get("state_id"),
            "country_id": value.get("country_id"),
        }

    def from_erp(self, value: TransformedValue, config: Optional[Dict[str, object]] = None) -> Dict[str, object]:
        """Konvertiert flache Felder zu Address-Dict."""
        if not isinstance(value, dict):
            return {}

        return {
            "street": value.get("street") or None,
            "street2": value.get("street2") or None,
            "city": value.get("city") or None,
            "zip": value.get("zip") or None,
            "state_id": value.get("state_id"),
            "country_id": value.get("country_id"),
        }


# =============================================================================
# Transformer Registry
# =============================================================================


TRANSFORMERS: Dict[str, Type[FieldTransformer]] = {
    "passthrough": PassthroughTransformer,
    "date": DateTransformer,
    "currency": CurrencyTransformer,
    "boolean": BooleanTransformer,
    "lookup": LookupTransformer,
    "string": StringNormalizer,
    "address": AddressTransformer,
}


def get_transformer(name: str) -> FieldTransformer:
    """Holt Transformer-Instanz nach Name."""
    transformer_class = TRANSFORMERS.get(name, PassthroughTransformer)
    return transformer_class()


# =============================================================================
# Field Mapping Configuration
# =============================================================================


class FieldMappingConfig:
    """Konfiguration für ein einzelnes Feld-Mapping."""

    def __init__(
        self,
        local_field: str,
        remote_field: str,
        transformer: str = "passthrough",
        transformer_config: Optional[Dict[str, object]] = None,
        direction: str = "bidirectional",
        required: bool = False,
        default_value: TransformedValue = None,
    ) -> None:
        self.local_field = local_field
        self.remote_field = remote_field
        self.transformer = get_transformer(transformer)
        self.transformer_config = transformer_config or {}
        self.direction = direction
        self.required = required
        self.default_value = default_value

    def to_erp(self, value: TransformedValue) -> TransformedValue:
        """Transformiert Wert für ERP."""
        if value is None and self.default_value is not None:
            value = self.default_value
        return self.transformer.to_erp(value, self.transformer_config)

    def from_erp(self, value: TransformedValue) -> TransformedValue:
        """Transformiert Wert aus ERP."""
        result = self.transformer.from_erp(value, self.transformer_config)
        if result is None and self.default_value is not None:
            return self.default_value
        return result


# =============================================================================
# Entity Mapping Service
# =============================================================================


class EntityMappingService:
    """Service für Entity-Feld-Mappings.

    Verwaltet Feld-Mappings pro Entity-Typ und führt
    bidirektionale Transformationen durch.
    """

    # Default Mappings pro Entity
    DEFAULT_MAPPINGS: Dict[str, List[Dict[str, object]]] = {
        "customer": [
            {"local_field": "name", "remote_field": "name", "transformer": "string", "required": True},
            {"local_field": "email", "remote_field": "email", "transformer": "string"},
            {"local_field": "phone", "remote_field": "phone", "transformer": "string"},
            {"local_field": "mobile", "remote_field": "mobile", "transformer": "string"},
            {"local_field": "vat_id", "remote_field": "vat", "transformer": "string"},
            {"local_field": "website", "remote_field": "website", "transformer": "string"},
            {"local_field": "address.street", "remote_field": "street", "transformer": "string"},
            {"local_field": "address.street2", "remote_field": "street2", "transformer": "string"},
            {"local_field": "address.city", "remote_field": "city", "transformer": "string"},
            {"local_field": "address.zip", "remote_field": "zip", "transformer": "string"},
            {"local_field": "is_company", "remote_field": "is_company", "transformer": "boolean"},
            {"local_field": "created_at", "remote_field": "create_date", "transformer": "date", "direction": "pull"},
            {"local_field": "updated_at", "remote_field": "write_date", "transformer": "date", "direction": "pull"},
        ],
        "supplier": [
            {"local_field": "name", "remote_field": "name", "transformer": "string", "required": True},
            {"local_field": "email", "remote_field": "email", "transformer": "string"},
            {"local_field": "phone", "remote_field": "phone", "transformer": "string"},
            {"local_field": "vat_id", "remote_field": "vat", "transformer": "string"},
            {"local_field": "address.street", "remote_field": "street", "transformer": "string"},
            {"local_field": "address.city", "remote_field": "city", "transformer": "string"},
            {"local_field": "address.zip", "remote_field": "zip", "transformer": "string"},
        ],
        "invoice": [
            {"local_field": "number", "remote_field": "name", "transformer": "string"},
            {"local_field": "reference", "remote_field": "ref", "transformer": "string"},
            {"local_field": "invoice_date", "remote_field": "invoice_date", "transformer": "date"},
            {"local_field": "due_date", "remote_field": "invoice_date_due", "transformer": "date"},
            {"local_field": "total_amount", "remote_field": "amount_total", "transformer": "currency"},
            {"local_field": "residual_amount", "remote_field": "amount_residual", "transformer": "currency"},
            {"local_field": "state", "remote_field": "state", "transformer": "string"},
            {"local_field": "payment_state", "remote_field": "payment_state", "transformer": "string"},
            {"local_field": "partner_id", "remote_field": "partner_id", "transformer": "lookup"},
        ],
    }

    def __init__(self, custom_mappings: Optional[Dict[str, List[Dict[str, object]]]] = None) -> None:
        """Initialisiert den Mapping-Service.

        Args:
            custom_mappings: Optionale Custom-Mappings die Default überschreiben
        """
        self._mappings: Dict[str, List[FieldMappingConfig]] = {}
        self._load_default_mappings()

        if custom_mappings:
            self._apply_custom_mappings(custom_mappings)

    def _load_default_mappings(self) -> None:
        """Laedt Default-Mappings."""
        for entity, mappings in self.DEFAULT_MAPPINGS.items():
            self._mappings[entity] = [
                FieldMappingConfig(**m) for m in mappings
            ]

    def _apply_custom_mappings(self, custom_mappings: Dict[str, List[Dict[str, object]]]) -> None:
        """Wendet Custom-Mappings an."""
        for entity, mappings in custom_mappings.items():
            if entity not in self._mappings:
                self._mappings[entity] = []

            # Add or override mappings
            existing_local_fields = {m.local_field for m in self._mappings[entity]}

            for mapping in mappings:
                local_field = mapping["local_field"]
                if local_field in existing_local_fields:
                    # Override existing
                    self._mappings[entity] = [
                        m for m in self._mappings[entity]
                        if m.local_field != local_field
                    ]
                self._mappings[entity].append(FieldMappingConfig(**mapping))

    def get_mappings(self, entity: str) -> List[FieldMappingConfig]:
        """Gibt alle Mappings für eine Entity zurück."""
        return self._mappings.get(entity, [])

    def to_erp(self, entity: str, local_data: Dict[str, object]) -> Dict[str, TransformedValue]:
        """Transformiert lokale Daten zu ERP-Format.

        Args:
            entity: Entity-Typ (customer, invoice, etc.)
            local_data: Lokale Daten

        Returns:
            Transformierte Daten im ERP-Format
        """
        result: Dict[str, TransformedValue] = {}
        mappings = self.get_mappings(entity)

        for mapping in mappings:
            if mapping.direction == "pull":
                continue  # Skip pull-only fields

            value = self._get_nested_value(local_data, mapping.local_field)
            transformed = mapping.to_erp(value)

            if transformed is not None or mapping.required:
                result[mapping.remote_field] = transformed

        return result

    def from_erp(self, entity: str, erp_data: Dict[str, object]) -> Dict[str, object]:
        """Transformiert ERP-Daten zu lokalem Format.

        Args:
            entity: Entity-Typ
            erp_data: Daten aus ERP

        Returns:
            Transformierte Daten im lokalen Format
        """
        result: Dict[str, object] = {}
        mappings = self.get_mappings(entity)

        for mapping in mappings:
            if mapping.direction == "push":
                continue  # Skip push-only fields

            value = erp_data.get(mapping.remote_field)
            transformed = mapping.from_erp(value)

            if transformed is not None:
                self._set_nested_value(result, mapping.local_field, transformed)

        return result

    def _get_nested_value(self, data: Dict[str, object], path: str) -> TransformedValue:
        """Holt verschachtelten Wert über Punkt-Notation."""
        parts = path.split(".")
        current = data

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None

        return current

    def _set_nested_value(self, data: Dict[str, object], path: str, value: TransformedValue) -> None:
        """Setzt verschachtelten Wert über Punkt-Notation."""
        parts = path.split(".")

        current = data
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]

        current[parts[-1]] = value


# =============================================================================
# Module-Level Singleton
# =============================================================================


_mapping_service: Optional[EntityMappingService] = None


def get_mapping_service(
    custom_mappings: Optional[Dict[str, List[Dict[str, object]]]] = None,
) -> EntityMappingService:
    """Gibt den Mapping-Service zurück (Singleton mit optionalen Custom-Mappings)."""
    global _mapping_service

    if _mapping_service is None or custom_mappings:
        _mapping_service = EntityMappingService(custom_mappings)

    return _mapping_service
