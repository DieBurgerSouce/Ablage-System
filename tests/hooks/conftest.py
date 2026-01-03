#!/usr/bin/env python3
"""
Pytest Fixtures fuer Hook-Tests.

Bietet gemeinsame Test-Fixtures fuer:
- Temporaere Verzeichnisse
- Mock-Config
- Sample-Plan-Dateien
"""

import json
import tempfile
from pathlib import Path
from typing import Dict, Any

import pytest


@pytest.fixture
def temp_plans_dir(tmp_path: Path) -> Path:
    """Erstelle temporaeres .claude/plans Verzeichnis."""
    plans_dir = tmp_path / ".claude/plans"
    plans_dir.mkdir(parents=True)
    return plans_dir


@pytest.fixture
def sample_plan_content() -> str:
    """Sample Plan mit mehreren Features."""
    return """# Projekt-Roadmap 2026

## Feature 1: User Authentication
JWT-basierte Authentifizierung mit refresh tokens.

## Feature 2: Dashboard
Admin-Dashboard mit Metriken und Charts.

## Feature 3: API v2
REST API mit OpenAPI 3.1 Spezifikation.

## Feature 4: Reporting
Export-Funktionalitaet fuer Berichte.
"""


@pytest.fixture
def sample_progress_json() -> Dict[str, Any]:
    """Sample PROGRESS.json Struktur."""
    return {
        "version": "4.0",
        "status": "in_progress",
        "total_features": 4,
        "completed_features": 2,
        "current_feature": "FEATURE_03",
        "features": [
            {
                "id": "FEATURE_01",
                "name": "User Authentication",
                "status": "completed",
                "spec_file": "FEATURE_01_user_auth.md"
            },
            {
                "id": "FEATURE_02",
                "name": "Dashboard",
                "status": "completed",
                "spec_file": "FEATURE_02_dashboard.md"
            },
            {
                "id": "FEATURE_03",
                "name": "API v2",
                "status": "in_progress",
                "spec_file": None
            },
            {
                "id": "FEATURE_04",
                "name": "Reporting",
                "status": "pending",
                "spec_file": None
            }
        ],
        "metadata": {
            "plan_file": "test-plan.md",
            "plan_mtime": 1735902000.0,
            "plan_content_hash": "abc123",
            "output_dir": ".claude/plans/test-plan/"
        }
    }


@pytest.fixture
def sample_config() -> Dict[str, Any]:
    """Sample config.json."""
    return {
        "settings": {
            "plan_freshness_minutes": 5,
            "feature_count_threshold": 3,
            "phase_count_threshold": 2,
            "task_count_threshold": 1,
            "max_spec_lines": 500,
            "enable_logging": True,
            "log_level": "WARNING"
        },
        "feature_detection": {
            "keywords": {
                "api": ["endpoint", "api", "rest"],
                "ui": ["component", "page", "display"],
                "db": ["schema", "migration", "model"]
            },
            "default_type": "service"
        }
    }


@pytest.fixture
def create_plan_file(temp_plans_dir: Path):
    """Factory Fixture fuer Plan-Dateien."""
    def _create(name: str, content: str) -> Path:
        plan_file = temp_plans_dir / name
        plan_file.write_text(content, encoding="utf-8")
        return plan_file
    return _create


@pytest.fixture
def create_progress_file(temp_plans_dir: Path):
    """Factory Fixture fuer PROGRESS.json."""
    def _create(data: Dict[str, Any]) -> Path:
        progress_file = temp_plans_dir / "PROGRESS.json"
        progress_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return progress_file
    return _create


# Markers fuer Test-Kategorien
def pytest_configure(config):
    """Registriere Custom Markers."""
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")
    config.addinivalue_line("markers", "integration: marks integration tests")
    config.addinivalue_line("markers", "unit: marks unit tests")
