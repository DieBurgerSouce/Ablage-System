"""Aktualisiert die OpenAPI-Baseline fuer Contract-Tests.

Dieses Script generiert das aktuelle OpenAPI-Schema und speichert es als
Baseline fuer zukuenftige Kompatibilitaetstests.

Usage:
    python scripts/update_openapi_baseline.py

Created: 2026-02-07
Author: Claude Code (Feature 1.5)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def main() -> int:
    """Hauptfunktion zum Aktualisieren der OpenAPI-Baseline.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    try:
        # Import FastAPI app
        from app.main import app
        from fastapi.testclient import TestClient

        print("Generiere OpenAPI-Schema...")

        # Create test client
        client = TestClient(app)

        # Fetch OpenAPI schema
        response = client.get("/openapi.json")

        if response.status_code != 200:
            print(f"FEHLER: Konnte Schema nicht laden (Status {response.status_code})")
            return 1

        schema = response.json()

        # Add metadata
        schema["_baseline_metadata"] = {
            "created_at": datetime.now().isoformat(),
            "version": schema.get("info", {}).get("version", "unknown"),
            "endpoint_count": len(schema.get("paths", {})),
            "schema_count": len(schema.get("components", {}).get("schemas", {}))
        }

        # Save to baseline file
        baseline_path = Path(__file__).parent.parent / "tests" / "contract" / "baseline_openapi_schema.json"

        # Create backup if exists
        if baseline_path.exists():
            backup_path = baseline_path.with_suffix(
                f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            print(f"Erstelle Backup: {backup_path.name}")
            baseline_path.rename(backup_path)

        # Write new baseline
        with open(baseline_path, "w", encoding="utf-8") as f:
            json.dump(schema, f, indent=2, ensure_ascii=False)

        print(f"\n✅ Baseline erfolgreich aktualisiert: {baseline_path}")
        print(f"\nStatistik:")
        print(f"  Endpoints: {schema['_baseline_metadata']['endpoint_count']}")
        print(f"  Schemas:   {schema['_baseline_metadata']['schema_count']}")
        print(f"  Version:   {schema['_baseline_metadata']['version']}")

        return 0

    except ImportError as e:
        print(f"FEHLER: Konnte App nicht importieren: {e}")
        print("\nStelle sicher, dass die Anwendung korrekt installiert ist:")
        print("  pip install -e .")
        return 1

    except Exception as e:
        print(f"FEHLER: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
