"""Contract Test Fixtures - Shared Resources fuer API-Kompatibilitaetstests.

Created: 2026-02-07
Author: Claude Code (Feature 1.5)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, Optional

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def app_client() -> TestClient:
    """TestClient fuer FastAPI-Anwendung.

    Yields:
        TestClient fuer API-Requests
    """
    try:
        from app.main import app
        client = TestClient(app)
        return client
    except ImportError as e:
        pytest.skip(f"FastAPI app konnte nicht importiert werden: {e}")


@pytest.fixture(scope="session")
def openapi_schema(app_client: TestClient) -> Dict[str, Any]:
    """Aktuelles OpenAPI-Schema von der laufenden Anwendung.

    Args:
        app_client: TestClient fixture

    Returns:
        OpenAPI-Schema als Dictionary
    """
    response = app_client.get("/openapi.json")

    if response.status_code != 200:
        pytest.fail(
            f"OpenAPI-Schema konnte nicht geladen werden: "
            f"Status {response.status_code}"
        )

    return response.json()


@pytest.fixture(scope="session")
def baseline_schema() -> Optional[Dict[str, Any]]:
    """Baseline OpenAPI-Schema aus gespeicherter Datei.

    Returns:
        Baseline-Schema oder None, falls nicht vorhanden
    """
    baseline_path = Path(__file__).parent / "baseline_openapi_schema.json"

    if not baseline_path.exists():
        return None

    try:
        with open(baseline_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        pytest.skip(f"Baseline-Schema konnte nicht geladen werden: {e}")
        return None


@pytest.fixture(scope="session")
def baseline_schema_path() -> Path:
    """Pfad zur Baseline-Schema-Datei.

    Returns:
        Path-Objekt zur baseline_openapi_schema.json
    """
    return Path(__file__).parent / "baseline_openapi_schema.json"


@pytest.fixture(scope="function")
def schema_snapshot_path() -> Path:
    """Pfad fuer Schema-Snapshots.

    Returns:
        Path zum Snapshot-Verzeichnis
    """
    snapshot_dir = Path(__file__).parent / "snapshots"
    snapshot_dir.mkdir(exist_ok=True)
    return snapshot_dir
