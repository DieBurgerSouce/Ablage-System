"""OpenAPI Schema Diff Utility - Erkennung von Breaking Changes.

Vergleicht zwei OpenAPI-Schemas und identifiziert Breaking Changes.

Created: 2026-02-07
Author: Claude Code (Feature 1.5)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set, Any, Optional


@dataclass
class EndpointChange:
    """Aenderung an einem API-Endpoint."""
    path: str
    method: str
    change_type: str  # 'removed', 'added', 'modified'
    details: str


@dataclass
class SchemaChange:
    """Aenderung an einem Schema-Definition."""
    schema_name: str
    change_type: str  # 'removed', 'added', 'modified'
    field: Optional[str] = None
    details: str = ""


@dataclass
class SchemaDiff:
    """Ergebnis eines Schema-Vergleichs."""
    breaking_changes: List[EndpointChange | SchemaChange] = field(default_factory=list)
    non_breaking_changes: List[EndpointChange | SchemaChange] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def has_breaking_changes(self) -> bool:
        """Gibt True zurueck, wenn Breaking Changes existieren."""
        return len(self.breaking_changes) > 0

    @property
    def change_summary(self) -> Dict[str, int]:
        """Zusammenfassung der Aenderungen."""
        return {
            "breaking": len(self.breaking_changes),
            "non_breaking": len(self.non_breaking_changes),
            "warnings": len(self.warnings)
        }


def diff_schemas(
    old_schema: Dict[str, Any],
    new_schema: Dict[str, Any]
) -> SchemaDiff:
    """Vergleicht zwei OpenAPI-Schemas.

    Args:
        old_schema: Altes OpenAPI-Schema
        new_schema: Neues OpenAPI-Schema

    Returns:
        SchemaDiff mit allen gefundenen Aenderungen
    """
    diff = SchemaDiff()

    # Compare paths (endpoints)
    _diff_paths(old_schema, new_schema, diff)

    # Compare components/schemas
    _diff_schemas(old_schema, new_schema, diff)

    return diff


def _diff_paths(
    old_schema: Dict[str, Any],
    new_schema: Dict[str, Any],
    diff: SchemaDiff
) -> None:
    """Vergleicht API-Pfade (Endpoints)."""
    old_paths = old_schema.get("paths", {})
    new_paths = new_schema.get("paths", {})

    old_path_keys = set(old_paths.keys())
    new_path_keys = set(new_paths.keys())

    # Removed endpoints (BREAKING)
    for path in old_path_keys - new_path_keys:
        for method in old_paths[path].keys():
            if method in ['get', 'post', 'put', 'patch', 'delete']:
                diff.breaking_changes.append(
                    EndpointChange(
                        path=path,
                        method=method.upper(),
                        change_type='removed',
                        details=f"Endpoint {method.upper()} {path} wurde entfernt"
                    )
                )

    # Added endpoints (NON-BREAKING)
    for path in new_path_keys - old_path_keys:
        for method in new_paths[path].keys():
            if method in ['get', 'post', 'put', 'patch', 'delete']:
                diff.non_breaking_changes.append(
                    EndpointChange(
                        path=path,
                        method=method.upper(),
                        change_type='added',
                        details=f"Neuer Endpoint {method.upper()} {path}"
                    )
                )

    # Modified endpoints
    for path in old_path_keys & new_path_keys:
        _diff_endpoint_methods(path, old_paths[path], new_paths[path], diff)


def _diff_endpoint_methods(
    path: str,
    old_endpoint: Dict[str, Any],
    new_endpoint: Dict[str, Any],
    diff: SchemaDiff
) -> None:
    """Vergleicht HTTP-Methoden eines Endpoints."""
    http_methods = ['get', 'post', 'put', 'patch', 'delete']

    for method in http_methods:
        old_method = old_endpoint.get(method)
        new_method = new_endpoint.get(method)

        if old_method and not new_method:
            # Method removed (BREAKING)
            diff.breaking_changes.append(
                EndpointChange(
                    path=path,
                    method=method.upper(),
                    change_type='removed',
                    details=f"HTTP-Methode {method.upper()} wurde von {path} entfernt"
                )
            )
        elif not old_method and new_method:
            # Method added (NON-BREAKING)
            diff.non_breaking_changes.append(
                EndpointChange(
                    path=path,
                    method=method.upper(),
                    change_type='added',
                    details=f"Neue HTTP-Methode {method.upper()} fuer {path}"
                )
            )
        elif old_method and new_method:
            # Method modified - check parameters and responses
            _diff_method_details(path, method, old_method, new_method, diff)


def _diff_method_details(
    path: str,
    method: str,
    old_method: Dict[str, Any],
    new_method: Dict[str, Any],
    diff: SchemaDiff
) -> None:
    """Vergleicht Details einer HTTP-Methode (Parameter, Responses)."""
    # Compare parameters
    old_params = old_method.get("parameters", [])
    new_params = new_method.get("parameters", [])

    old_required_params = {
        p["name"]
        for p in old_params
        if p.get("required", False)
    }
    new_required_params = {
        p["name"]
        for p in new_params
        if p.get("required", False)
    }

    # New required parameters (BREAKING)
    for param in new_required_params - old_required_params:
        diff.breaking_changes.append(
            EndpointChange(
                path=path,
                method=method.upper(),
                change_type='modified',
                details=f"Neuer required Parameter '{param}' bei {method.upper()} {path}"
            )
        )

    # Removed required parameters (BREAKING)
    for param in old_required_params - new_required_params:
        # Check if parameter was completely removed or just made optional
        new_param_names = {p["name"] for p in new_params}
        if param not in new_param_names:
            diff.breaking_changes.append(
                EndpointChange(
                    path=path,
                    method=method.upper(),
                    change_type='modified',
                    details=f"Required Parameter '{param}' wurde von {method.upper()} {path} entfernt"
                )
            )
        else:
            # Parameter made optional (NON-BREAKING)
            diff.non_breaking_changes.append(
                EndpointChange(
                    path=path,
                    method=method.upper(),
                    change_type='modified',
                    details=f"Parameter '{param}' ist jetzt optional bei {method.upper()} {path}"
                )
            )

    # Compare response codes
    old_responses = set(old_method.get("responses", {}).keys())
    new_responses = set(new_method.get("responses", {}).keys())

    # Removed success responses (BREAKING)
    for response_code in old_responses - new_responses:
        if response_code.startswith("2"):  # 2xx success codes
            diff.breaking_changes.append(
                EndpointChange(
                    path=path,
                    method=method.upper(),
                    change_type='modified',
                    details=f"Response-Code {response_code} wurde von {method.upper()} {path} entfernt"
                )
            )


def _diff_schemas(
    old_schema: Dict[str, Any],
    new_schema: Dict[str, Any],
    diff: SchemaDiff
) -> None:
    """Vergleicht Schema-Definitionen (components/schemas)."""
    old_schemas = old_schema.get("components", {}).get("schemas", {})
    new_schemas = new_schema.get("components", {}).get("schemas", {})

    old_schema_names = set(old_schemas.keys())
    new_schema_names = set(new_schemas.keys())

    # Removed schemas (WARNING - might be breaking)
    for schema_name in old_schema_names - new_schema_names:
        diff.warnings.append(
            f"Schema '{schema_name}' wurde entfernt (pruefen, ob noch verwendet)"
        )

    # Modified schemas
    for schema_name in old_schema_names & new_schema_names:
        _diff_schema_definition(
            schema_name,
            old_schemas[schema_name],
            new_schemas[schema_name],
            diff
        )


def _diff_schema_definition(
    schema_name: str,
    old_definition: Dict[str, Any],
    new_definition: Dict[str, Any],
    diff: SchemaDiff
) -> None:
    """Vergleicht eine einzelne Schema-Definition."""
    old_props = old_definition.get("properties", {})
    new_props = new_definition.get("properties", {})

    old_required = set(old_definition.get("required", []))
    new_required = set(new_definition.get("required", []))

    # New required fields (BREAKING)
    for field in new_required - old_required:
        if field in new_props:  # Field exists
            diff.breaking_changes.append(
                SchemaChange(
                    schema_name=schema_name,
                    change_type='modified',
                    field=field,
                    details=f"Feld '{field}' ist jetzt required in Schema '{schema_name}'"
                )
            )

    # Removed required fields (BREAKING)
    for field in old_required - new_required:
        old_prop_names = set(old_props.keys())
        if field not in new_props:
            diff.breaking_changes.append(
                SchemaChange(
                    schema_name=schema_name,
                    change_type='modified',
                    field=field,
                    details=f"Required Feld '{field}' wurde von Schema '{schema_name}' entfernt"
                )
            )

    # Check field type changes
    for field in set(old_props.keys()) & set(new_props.keys()):
        old_type = old_props[field].get("type")
        new_type = new_props[field].get("type")

        if old_type != new_type:
            diff.breaking_changes.append(
                SchemaChange(
                    schema_name=schema_name,
                    change_type='modified',
                    field=field,
                    details=f"Typ von Feld '{field}' geaendert: {old_type} -> {new_type} in Schema '{schema_name}'"
                )
            )

        # Check enum changes
        old_enum = old_props[field].get("enum", [])
        new_enum = new_props[field].get("enum", [])

        if old_enum and new_enum:
            removed_values = set(old_enum) - set(new_enum)
            if removed_values:
                diff.breaking_changes.append(
                    SchemaChange(
                        schema_name=schema_name,
                        change_type='modified',
                        field=field,
                        details=f"Enum-Werte entfernt von Feld '{field}': {removed_values}"
                    )
                )


def is_breaking_change(diff: SchemaDiff) -> bool:
    """Gibt True zurueck, wenn Breaking Changes gefunden wurden.

    Args:
        diff: SchemaDiff-Objekt

    Returns:
        True wenn Breaking Changes existieren
    """
    return diff.has_breaking_changes
