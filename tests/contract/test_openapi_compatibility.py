"""OpenAPI Contract Tests - API-Kompatibilitaetspruefung.

Stellt sicher, dass:
- OpenAPI-Schema sich nicht unbeabsichtigt aendert
- Breaking Changes erkannt werden
- Neue Endpoints dokumentiert sind
- Response-Schemas gueltig sind

Created: 2026-02-07
Author: Claude Code (Feature 1.5)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Any, List, Set, Optional

import pytest
from fastapi.testclient import TestClient

from tests.contract.schema_diff import diff_schemas, is_breaking_change, SchemaDiff


# Test markers
pytestmark = pytest.mark.contract


class TestOpenAPISchemaValidity:
    """Tests fuer OpenAPI-Schema-Validitaet."""

    def test_openapi_schema_is_valid(
        self,
        openapi_schema: Dict[str, Any]
    ) -> None:
        """Prueft, dass das OpenAPI-Schema gueltige Struktur hat."""
        # Check required top-level fields
        required_fields = ["openapi", "info", "paths"]

        for field in required_fields:
            assert field in openapi_schema, (
                f"OpenAPI-Schema fehlt erforderliches Feld: {field}"
            )

        # Check OpenAPI version
        openapi_version = openapi_schema.get("openapi", "")
        assert openapi_version.startswith("3."), (
            f"Unerwartete OpenAPI-Version: {openapi_version} (erwartet 3.x)"
        )

        # Check info section
        info = openapi_schema.get("info", {})
        assert "title" in info, "OpenAPI info fehlt 'title'"
        assert "version" in info, "OpenAPI info fehlt 'version'"

    def test_openapi_schema_has_paths(
        self,
        openapi_schema: Dict[str, Any]
    ) -> None:
        """Prueft, dass das Schema mindestens einen Endpoint definiert."""
        paths = openapi_schema.get("paths", {})

        assert len(paths) > 0, "OpenAPI-Schema hat keine Endpoints definiert"

        # Check that paths are strings starting with /
        for path in paths.keys():
            assert path.startswith("/"), (
                f"Endpoint-Pfad '{path}' startet nicht mit '/'"
            )


class TestEndpointDocumentation:
    """Tests fuer Endpoint-Dokumentation."""

    def test_all_endpoints_have_descriptions(
        self,
        openapi_schema: Dict[str, Any]
    ) -> None:
        """Prueft, dass alle Endpoints eine Beschreibung haben."""
        paths = openapi_schema.get("paths", {})
        missing_descriptions = []

        for path, methods in paths.items():
            for method, definition in methods.items():
                if method in ['get', 'post', 'put', 'patch', 'delete']:
                    if "summary" not in definition and "description" not in definition:
                        missing_descriptions.append(f"{method.upper()} {path}")

        # Allow some endpoints without description (e.g., auto-generated)
        max_allowed = 10
        assert len(missing_descriptions) <= max_allowed, (
            f"Zu viele Endpoints ohne Beschreibung ({len(missing_descriptions)}): "
            f"{missing_descriptions[:10]}"
        )

    def test_all_endpoints_have_response_models(
        self,
        openapi_schema: Dict[str, Any]
    ) -> None:
        """Prueft, dass alle Endpoints Response-Schemas definieren."""
        paths = openapi_schema.get("paths", {})
        missing_responses = []

        for path, methods in paths.items():
            for method, definition in methods.items():
                if method in ['get', 'post', 'put', 'patch', 'delete']:
                    responses = definition.get("responses", {})

                    # Check for success responses (2xx)
                    has_success_response = any(
                        code.startswith("2") for code in responses.keys()
                    )

                    if not has_success_response:
                        missing_responses.append(f"{method.upper()} {path}")

        # Allow some endpoints without explicit responses
        max_allowed = 5
        assert len(missing_responses) <= max_allowed, (
            f"Zu viele Endpoints ohne Success-Response ({len(missing_responses)}): "
            f"{missing_responses[:10]}"
        )

    def test_all_error_responses_documented(
        self,
        openapi_schema: Dict[str, Any]
    ) -> None:
        """Prueft, dass Error-Responses dokumentiert sind.

        Erwartet mindestens 422 (Validation Error) fuer POST/PUT/PATCH
        und 404 fuer GET mit ID-Parameter.
        """
        paths = openapi_schema.get("paths", {})
        missing_validation_errors = []
        missing_not_found_errors = []

        for path, methods in paths.items():
            for method, definition in methods.items():
                responses = definition.get("responses", {})

                # POST/PUT/PATCH should have 422 (validation error)
                if method in ['post', 'put', 'patch']:
                    if "422" not in responses:
                        missing_validation_errors.append(f"{method.upper()} {path}")

                # GET with {id} parameter should have 404
                if method == 'get' and '{' in path:
                    if "404" not in responses:
                        missing_not_found_errors.append(f"{method.upper()} {path}")

        # These are recommendations, not strict requirements
        if missing_validation_errors:
            print(
                f"\nINFO: {len(missing_validation_errors)} Endpoints ohne 422-Response: "
                f"{missing_validation_errors[:5]}"
            )

        if missing_not_found_errors:
            print(
                f"\nINFO: {len(missing_not_found_errors)} GET-Endpoints ohne 404-Response: "
                f"{missing_not_found_errors[:5]}"
            )

    def test_german_descriptions(
        self,
        openapi_schema: Dict[str, Any]
    ) -> None:
        """Prueft, dass Endpoint-Beschreibungen weitgehend auf Deutsch sind.

        Hinweis: Dies ist ein Hinweis-Test, keine strikte Anforderung.
        """
        paths = openapi_schema.get("paths", {})
        non_german_count = 0
        total_with_description = 0

        # Simple heuristic: German uses "ä", "ö", "ü", "ß" or specific words
        german_indicators = ["dokument", "benutzer", "erstell", "aender", "loesc"]

        for path, methods in paths.items():
            for method, definition in methods.items():
                if method in ['get', 'post', 'put', 'patch', 'delete']:
                    summary = definition.get("summary", "")
                    description = definition.get("description", "")
                    combined = (summary + " " + description).lower()

                    if combined.strip():
                        total_with_description += 1

                        # Check for German indicators
                        has_german = any(
                            indicator in combined
                            for indicator in german_indicators
                        ) or any(
                            char in combined
                            for char in ["ä", "ö", "ü", "ß"]
                        )

                        if not has_german:
                            # Might be English
                            english_words = ["create", "update", "delete", "get", "list"]
                            has_english = any(word in combined for word in english_words)

                            if has_english:
                                non_german_count += 1

        if total_with_description > 0:
            german_percentage = (
                (total_with_description - non_german_count) / total_with_description * 100
            )
            print(
                f"\nINFO: Geschaetzte deutsche Beschreibungen: "
                f"{german_percentage:.1f}% ({total_with_description - non_german_count}/{total_with_description})"
            )


class TestSchemaCompatibility:
    """Tests fuer Schema-Kompatibilitaet (Breaking Changes)."""

    def test_no_breaking_changes(
        self,
        openapi_schema: Dict[str, Any],
        baseline_schema: Optional[Dict[str, Any]]
    ) -> None:
        """Prueft, dass keine Breaking Changes im Vergleich zur Baseline existieren."""
        if baseline_schema is None:
            pytest.skip(
                "Keine Baseline vorhanden - erstelle Baseline mit "
                "scripts/update_openapi_baseline.py"
            )

        diff = diff_schemas(baseline_schema, openapi_schema)

        if diff.has_breaking_changes:
            breaking_summary = "\n".join(
                f"  - {change.details if hasattr(change, 'details') else str(change)}"
                for change in diff.breaking_changes[:10]
            )

            pytest.fail(
                f"Breaking Changes gefunden ({len(diff.breaking_changes)} gesamt):\n"
                f"{breaking_summary}\n\n"
                f"Falls diese Aenderungen beabsichtigt sind, aktualisiere die Baseline mit:\n"
                f"python scripts/update_openapi_baseline.py"
            )

    def test_schema_change_report(
        self,
        openapi_schema: Dict[str, Any],
        baseline_schema: Optional[Dict[str, Any]]
    ) -> None:
        """Erstellt einen Bericht aller Schema-Aenderungen."""
        if baseline_schema is None:
            pytest.skip("Keine Baseline vorhanden")

        diff = diff_schemas(baseline_schema, openapi_schema)

        print("\n" + "="*60)
        print("SCHEMA-AENDERUNGEN BERICHT")
        print("="*60)

        summary = diff.change_summary
        print(f"\nZusammenfassung:")
        print(f"  Breaking Changes:     {summary['breaking']}")
        print(f"  Non-Breaking Changes: {summary['non_breaking']}")
        print(f"  Warnings:             {summary['warnings']}")

        if diff.breaking_changes:
            print(f"\nBreaking Changes ({len(diff.breaking_changes)}):")
            for change in diff.breaking_changes[:10]:
                print(f"  - {change.details if hasattr(change, 'details') else str(change)}")

        if diff.non_breaking_changes:
            print(f"\nNon-Breaking Changes ({len(diff.non_breaking_changes)}):")
            for change in diff.non_breaking_changes[:10]:
                print(f"  - {change.details if hasattr(change, 'details') else str(change)}")

        if diff.warnings:
            print(f"\nWarnungen ({len(diff.warnings)}):")
            for warning in diff.warnings[:10]:
                print(f"  - {warning}")


class TestSchemaSnapshots:
    """Tests fuer Schema-Snapshot-Vergleiche."""

    def test_schema_snapshot_matches(
        self,
        openapi_schema: Dict[str, Any],
        schema_snapshot_path: Path
    ) -> None:
        """Snapshot-Test fuer Schema-Stabilitaet.

        Vergleicht das aktuelle Schema mit einem gespeicherten Snapshot.
        """
        snapshot_file = schema_snapshot_path / "current_schema.json"

        if not snapshot_file.exists():
            # Create initial snapshot
            with open(snapshot_file, "w", encoding="utf-8") as f:
                json.dump(openapi_schema, f, indent=2, ensure_ascii=False)

            pytest.skip(
                "Initialer Snapshot erstellt. Fuehre Test erneut aus."
            )

        # Load snapshot
        with open(snapshot_file, "r", encoding="utf-8") as f:
            snapshot = json.load(f)

        # Compare schemas
        diff = diff_schemas(snapshot, openapi_schema)

        # Allow non-breaking changes
        if diff.has_breaking_changes:
            pytest.fail(
                f"Schema weicht vom Snapshot ab ({len(diff.breaking_changes)} Breaking Changes). "
                f"Aktualisiere Snapshot wenn beabsichtigt."
            )

    def test_endpoint_count_stability(
        self,
        openapi_schema: Dict[str, Any],
        baseline_schema: Optional[Dict[str, Any]]
    ) -> None:
        """Prueft, dass die Anzahl der Endpoints nicht drastisch abnimmt."""
        if baseline_schema is None:
            pytest.skip("Keine Baseline vorhanden")

        old_paths = baseline_schema.get("paths", {})
        new_paths = openapi_schema.get("paths", {})

        old_endpoint_count = sum(
            1 for methods in old_paths.values()
            for method in methods.keys()
            if method in ['get', 'post', 'put', 'patch', 'delete']
        )

        new_endpoint_count = sum(
            1 for methods in new_paths.values()
            for method in methods.keys()
            if method in ['get', 'post', 'put', 'patch', 'delete']
        )

        # Allow removal of up to 10% of endpoints
        threshold = old_endpoint_count * 0.9

        assert new_endpoint_count >= threshold, (
            f"Zu viele Endpoints entfernt: {old_endpoint_count} -> {new_endpoint_count} "
            f"(Threshold: {threshold:.0f})"
        )

        print(
            f"\nINFO: Endpoint-Count: {old_endpoint_count} -> {new_endpoint_count} "
            f"({'+' if new_endpoint_count >= old_endpoint_count else ''}"
            f"{new_endpoint_count - old_endpoint_count})"
        )


class TestSchemaComponents:
    """Tests fuer Schema-Komponenten (Models)."""

    def test_all_schemas_have_descriptions(
        self,
        openapi_schema: Dict[str, Any]
    ) -> None:
        """Prueft, dass Schema-Definitionen Beschreibungen haben."""
        schemas = openapi_schema.get("components", {}).get("schemas", {})

        missing_descriptions = []

        for schema_name, schema_def in schemas.items():
            if "description" not in schema_def and "title" not in schema_def:
                missing_descriptions.append(schema_name)

        # Allow some schemas without description
        max_allowed = 20
        assert len(missing_descriptions) <= max_allowed, (
            f"Zu viele Schemas ohne Beschreibung ({len(missing_descriptions)}): "
            f"{missing_descriptions[:10]}"
        )

    def test_no_empty_schemas(
        self,
        openapi_schema: Dict[str, Any]
    ) -> None:
        """Prueft, dass keine leeren Schema-Definitionen existieren."""
        schemas = openapi_schema.get("components", {}).get("schemas", {})

        empty_schemas = []

        for schema_name, schema_def in schemas.items():
            # Check if schema has properties or is just a wrapper
            if "properties" not in schema_def and "allOf" not in schema_def:
                if "type" not in schema_def or schema_def.get("type") == "object":
                    empty_schemas.append(schema_name)

        assert len(empty_schemas) == 0, (
            f"Leere Schema-Definitionen gefunden: {empty_schemas}"
        )


class TestResponseSchemas:
    """Tests fuer Response-Schema-Definitionen."""

    def test_all_responses_reference_schemas(
        self,
        openapi_schema: Dict[str, Any]
    ) -> None:
        """Prueft, dass Response-Schemas auf definierte Schemas verweisen."""
        paths = openapi_schema.get("paths", {})
        schemas = openapi_schema.get("components", {}).get("schemas", {})
        schema_names = set(schemas.keys())

        undefined_references = []

        for path, methods in paths.items():
            for method, definition in methods.items():
                if method not in ['get', 'post', 'put', 'patch', 'delete']:
                    continue

                responses = definition.get("responses", {})

                for status_code, response_def in responses.items():
                    content = response_def.get("content", {})

                    for media_type, media_def in content.items():
                        schema = media_def.get("schema", {})

                        # Check $ref
                        ref = schema.get("$ref", "")
                        if ref:
                            # Extract schema name from #/components/schemas/SchemaName
                            match = re.search(r'#/components/schemas/(\w+)', ref)
                            if match:
                                schema_name = match.group(1)
                                if schema_name not in schema_names:
                                    undefined_references.append(
                                        f"{method.upper()} {path} -> {schema_name}"
                                    )

        assert len(undefined_references) == 0, (
            f"Undefinierte Schema-Referenzen gefunden: {undefined_references[:10]}"
        )


# Performance test
@pytest.mark.slow
class TestSchemaPerformance:
    """Performance-Tests fuer Schema-Generierung."""

    def test_openapi_schema_generation_performance(
        self,
        app_client: TestClient
    ) -> None:
        """Prueft, dass Schema-Generierung performant ist (<1s)."""
        import time

        start = time.time()
        response = app_client.get("/openapi.json")
        duration = time.time() - start

        assert response.status_code == 200, "Schema konnte nicht geladen werden"
        assert duration < 1.0, (
            f"Schema-Generierung zu langsam: {duration:.3f}s (Limit: 1.0s)"
        )

        print(f"\nINFO: Schema-Generierung dauerte {duration:.3f}s")
