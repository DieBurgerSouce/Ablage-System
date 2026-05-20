# -*- coding: utf-8 -*-
"""Unit tests for Onboarding API.

Tests:
- Onboarding-Status abrufen
- Schritte abschliessen
- Onboarding ueberspringen/zuruecksetzen
- Checkliste
"""

import pytest
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.v1.onboarding import (
    ONBOARDING_STEPS,
    POST_SETUP_CHECKLIST,
    _get_onboarding_status_from_preferences,
    _build_onboarding_status,
    _build_checklist_status,
)


class TestOnboardingStepsDefinition:
    """Tests fuer Onboarding-Schritt-Definitionen."""

    def test_steps_not_empty(self):
        """Es sollte Schritte geben."""
        assert len(ONBOARDING_STEPS) > 0

    def test_steps_have_required_fields(self):
        """Alle Schritte sollten erforderliche Felder haben."""
        required = ["id", "order", "title", "description", "icon", "required"]

        for step in ONBOARDING_STEPS:
            for field in required:
                assert field in step, f"Schritt {step.get('id')} fehlt Feld: {field}"

    def test_steps_unique_ids(self):
        """Schritt-IDs sollten eindeutig sein."""
        ids = [s["id"] for s in ONBOARDING_STEPS]
        assert len(ids) == len(set(ids))

    def test_steps_ordered(self):
        """Schritte sollten aufsteigend geordnet sein."""
        orders = [s["order"] for s in ONBOARDING_STEPS]
        assert orders == sorted(orders)

    def test_steps_german_content(self):
        """Schritte sollten deutschen Content haben."""
        for step in ONBOARDING_STEPS:
            assert len(step["title"]) > 0
            assert len(step["description"]) > 0

    def test_has_seven_steps(self):
        """Es sollte 7 Schritte geben."""
        assert len(ONBOARDING_STEPS) == 7


class TestPostSetupChecklist:
    """Tests fuer Post-Setup Checkliste."""

    def test_checklist_not_empty(self):
        """Checkliste sollte nicht leer sein."""
        assert len(POST_SETUP_CHECKLIST) > 0

    def test_checklist_has_required_fields(self):
        """Checklisten-Eintraege sollten Felder haben."""
        required = ["id", "title", "description", "category"]

        for item in POST_SETUP_CHECKLIST:
            for field in required:
                assert field in item, f"Item {item.get('id')} fehlt Feld: {field}"

    def test_checklist_unique_ids(self):
        """Item-IDs sollten eindeutig sein."""
        ids = [i["id"] for i in POST_SETUP_CHECKLIST]
        assert len(ids) == len(set(ids))

    def test_checklist_categories(self):
        """Kategorien sollten gueltig sein."""
        valid_categories = ["documents", "ocr", "entities", "invoices", "banking", "workflows"]

        for item in POST_SETUP_CHECKLIST:
            assert item["category"] in valid_categories


class TestOnboardingStatusBuilder:
    """Tests fuer _build_onboarding_status."""

    def test_build_empty_status(self):
        """Leerer Status sollte Defaults haben."""
        status = _build_onboarding_status({})

        assert status.current_step == 1
        assert status.total_steps == 7
        assert len(status.completed_steps) == 0
        assert status.progress_percent == 0
        assert status.is_complete is False
        assert status.skipped is False

    def test_build_partial_status(self):
        """Teilweise abgeschlossener Status."""
        status = _build_onboarding_status({
            "completed_steps": ["company", "industry"],
            "step_completed_at": {
                "company": "2026-01-01T10:00:00Z",
                "industry": "2026-01-01T10:05:00Z",
            },
        })

        assert len(status.completed_steps) == 2
        assert "company" in status.completed_steps
        assert "industry" in status.completed_steps
        assert status.current_step == 3  # Naechster nicht-abgeschlossener
        assert status.progress_percent > 0

    def test_build_complete_status(self):
        """Vollstaendig abgeschlossener Status."""
        all_step_ids = [s["id"] for s in ONBOARDING_STEPS]

        status = _build_onboarding_status({
            "completed_steps": all_step_ids,
            "completed_at": "2026-01-01T12:00:00Z",
        })

        assert status.is_complete is True
        assert status.progress_percent == 100
        assert len(status.completed_steps) == 7

    def test_build_skipped_status(self):
        """Uebersprungener Status."""
        status = _build_onboarding_status({
            "skipped": True,
            "completed_at": "2026-01-01T10:00:00Z",
        })

        assert status.skipped is True
        assert status.is_complete is True

    def test_build_status_includes_steps(self):
        """Status sollte alle Schritte enthalten."""
        status = _build_onboarding_status({})

        assert len(status.steps) == 7

        # Alle Schritte sollten da sein
        step_ids = [s.id for s in status.steps]
        expected_ids = [s["id"] for s in ONBOARDING_STEPS]
        assert step_ids == expected_ids


class TestChecklistStatusBuilder:
    """Tests fuer _build_checklist_status."""

    def test_build_empty_checklist(self):
        """Leere Checkliste."""
        status = _build_checklist_status({})

        assert len(status.items) == len(POST_SETUP_CHECKLIST)
        assert status.completed_count == 0
        assert status.progress_percent == 0

    def test_build_partial_checklist(self):
        """Teilweise abgeschlossene Checkliste."""
        status = _build_checklist_status({
            "completed_items": {
                "first_document": "2026-01-01T10:00:00Z",
                "first_ocr": "2026-01-01T10:05:00Z",
            },
        })

        assert status.completed_count == 2
        assert status.progress_percent > 0

        # Pruefen dass Items korrekt markiert sind
        completed_item = next(i for i in status.items if i.id == "first_document")
        assert completed_item.completed is True
        assert completed_item.completed_at is not None

    def test_build_complete_checklist(self):
        """Vollstaendige Checkliste."""
        all_item_ids = {i["id"]: "2026-01-01T12:00:00Z" for i in POST_SETUP_CHECKLIST}

        status = _build_checklist_status({
            "completed_items": all_item_ids,
        })

        assert status.completed_count == len(POST_SETUP_CHECKLIST)
        assert status.progress_percent == 100


class TestOnboardingAPISchemas:
    """Tests fuer API-Schemas."""

    def test_onboarding_status_fields(self):
        """OnboardingStatus sollte alle Felder haben."""
        from app.api.v1.onboarding import OnboardingStatus

        status = OnboardingStatus(
            started_at="2026-01-01T10:00:00Z",
            completed_at=None,
            skipped=False,
            current_step=1,
            total_steps=7,
            completed_steps=[],
            progress_percent=0,
            is_complete=False,
            steps=[],
        )

        assert status.current_step == 1
        assert status.total_steps == 7

    def test_checklist_item_fields(self):
        """ChecklistItem sollte alle Felder haben."""
        from app.api.v1.onboarding import ChecklistItem

        item = ChecklistItem(
            id="first_document",
            title="Erstes Dokument",
            description="Laden Sie ein Dokument hoch",
            category="documents",
            completed=False,
            completed_at=None,
        )

        assert item.id == "first_document"
        assert item.completed is False


class TestOnboardingAPIEndpoints:
    """Tests fuer API-Endpoints (ohne tatsaechliche HTTP-Aufrufe)."""

    def test_valid_step_ids(self):
        """Gueltige Schritt-IDs."""
        valid_ids = [s["id"] for s in ONBOARDING_STEPS]

        assert "company" in valid_ids
        assert "users" in valid_ids
        assert "complete" in valid_ids

    def test_invalid_step_id_detection(self):
        """Ungueltige Schritt-IDs sollten erkannt werden."""
        valid_ids = [s["id"] for s in ONBOARDING_STEPS]

        assert "invalid_step" not in valid_ids
        assert "admin" not in valid_ids


class TestOnboardingPreferencesExtraction:
    """Tests fuer _get_onboarding_status_from_preferences."""

    def test_extract_from_empty(self):
        """Extraktion aus leeren Preferences."""
        result = _get_onboarding_status_from_preferences({})
        assert result == {}

    def test_extract_from_valid(self):
        """Extraktion aus gueltigen Preferences."""
        prefs = {
            "onboarding": {
                "started_at": "2026-01-01T10:00:00Z",
                "completed_steps": ["company"],
            },
            "other_setting": "value",
        }

        result = _get_onboarding_status_from_preferences(prefs)

        assert "started_at" in result
        assert "completed_steps" in result
        assert len(result["completed_steps"]) == 1

    def test_extract_ignores_other_keys(self):
        """Andere Keys sollten ignoriert werden."""
        prefs = {
            "theme": "dark",
            "language": "de",
        }

        result = _get_onboarding_status_from_preferences(prefs)
        assert result == {}


class TestOnboardingProgressCalculation:
    """Tests fuer Fortschrittsberechnung."""

    def test_progress_zero(self):
        """0% bei keinen abgeschlossenen Schritten."""
        status = _build_onboarding_status({})
        assert status.progress_percent == 0

    def test_progress_partial(self):
        """Korrekter Prozentsatz bei teilweisem Fortschritt."""
        status = _build_onboarding_status({
            "completed_steps": ["company", "industry", "users"],  # 3 von 7
        })

        expected = int((3 / 7) * 100)  # 42%
        assert status.progress_percent == expected

    def test_progress_complete(self):
        """100% bei allen abgeschlossenen Schritten."""
        all_steps = [s["id"] for s in ONBOARDING_STEPS]

        status = _build_onboarding_status({
            "completed_steps": all_steps,
        })

        assert status.progress_percent == 100


class TestChecklistProgressCalculation:
    """Tests fuer Checklisten-Fortschritt."""

    def test_checklist_progress_zero(self):
        """0% bei keinen erledigten Items."""
        status = _build_checklist_status({})
        assert status.progress_percent == 0

    def test_checklist_progress_partial(self):
        """Korrekter Prozentsatz bei teilweisem Fortschritt."""
        status = _build_checklist_status({
            "completed_items": {
                "first_document": "2026-01-01T10:00:00Z",
            },
        })

        expected = int((1 / len(POST_SETUP_CHECKLIST)) * 100)
        assert status.progress_percent == expected

    def test_checklist_progress_complete(self):
        """100% bei allen erledigten Items."""
        all_items = {i["id"]: "2026-01-01T12:00:00Z" for i in POST_SETUP_CHECKLIST}

        status = _build_checklist_status({
            "completed_items": all_items,
        })

        assert status.progress_percent == 100
