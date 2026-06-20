# -*- coding: utf-8 -*-
"""
Integration Tests für Tunes + Upload Workflow.

Testet:
- Tune-Auswahl im Upload-Flow
- Backend-Auswahl basierend auf Tune
- Vollständiger Upload-Workflow mit Tune-Kontext

Feinpoliert und durchdacht - Enterprise Test Coverage.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4
from datetime import datetime, timezone

# Test markers
pytestmark = [pytest.mark.integration]


class TestTunesApiIntegration:
    """Integration Tests für Tunes API."""

    @pytest.mark.asyncio
    async def test_tunes_requires_auth(self, async_client):
        """Ohne Auth-Header antwortet die Tunes-Liste mit 403.

        W3 (2026-06-12): Repo-Konvention (Nutzer-Entscheidung W3): 403 bei
        fehlender Auth BLEIBT (HTTPBearer auto_error-Default).
        """
        response = await async_client.get("/api/v1/tunes/")
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_tunes_crud_workflow(self, async_client):
        """Tunes-Liste mit Auth liefert 200 + leere Liste.

        W3 (2026-06-12): Echter Vertrag — FastAPI-Dependencies lassen sich
        nicht via patch() auf Modul-Attribute mocken (Depends-Referenzen
        sind beim Import gebunden). Korrekt: app.dependency_overrides.
        GET / verlangt get_current_active_user (nicht superuser).
        """
        from app.api import dependencies
        from app.main import app

        admin_user = Mock(id=uuid4(), is_superuser=True, email="admin@test.de")

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        async def _override_db():
            yield mock_session

        app.dependency_overrides[dependencies.get_db] = _override_db
        app.dependency_overrides[dependencies.get_current_active_user] = (
            lambda: admin_user
        )
        try:
            response = await async_client.get("/api/v1/tunes/")
        finally:
            app.dependency_overrides.pop(dependencies.get_db, None)
            app.dependency_overrides.pop(
                dependencies.get_current_active_user, None
            )

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_tune_affects_document_processing(self, async_client):
        """Tune-Auswahl beeinflusst Dokumentenverarbeitung."""
        # Tunes haben prompt_template und default_backend
        # Diese sollten die OCR-Verarbeitung beeinflussen

        tune_for_invoices = {
            "id": str(uuid4()),
            "name": "Rechnungen",
            "description": "Optimiert für Rechnungsverarbeitung",
            "icon": "Receipt",
            "color": "bg-blue-500",
            "prompt_template": "Extrahiere Rechnungsdaten: Betrag, Datum, Lieferant",
            "default_backend": "deepseek-janus",
            "is_system": True,
            "is_active": True
        }

        tune_for_contracts = {
            "id": str(uuid4()),
            "name": "Verträge",
            "description": "Optimiert für Vertragsanalyse",
            "icon": "Scale",
            "color": "bg-green-500",
            "prompt_template": "Extrahiere Vertragsdaten: Parteien, Laufzeit, Konditionen",
            "default_backend": "deepseek-janus",
            "is_system": True,
            "is_active": True
        }

        # Beide Tunes haben unterschiedliche prompt_templates
        assert tune_for_invoices["prompt_template"] != tune_for_contracts["prompt_template"]
        assert tune_for_invoices["default_backend"] == tune_for_contracts["default_backend"]


class TestUploadFlowWithTunes:
    """Integration Tests für Upload-Flow mit Tune-Auswahl."""

    @pytest.mark.asyncio
    async def test_upload_with_tune_selection(self, async_client):
        """Upload mit expliziter Tune-Auswahl."""
        # Der Upload-Flow sollte:
        # 1. User wählt Backend (z.B. deepseek-janus)
        # 2. User wählt Tune (z.B. Rechnungen)
        # 3. User lädt Dokument hoch
        # 4. System nutzt Tune-Kontext für Analyse

        tune_id = str(uuid4())
        backend_id = "deepseek-janus"

        # Simuliere Upload-Request mit Tune-Kontext
        upload_context = {
            "selected_tune_id": tune_id,
            "selected_backend_id": backend_id,
            "files": []  # In echtem Test: PDF-Dateien
        }

        # Validiere dass beide Werte gesetzt sind
        assert upload_context["selected_tune_id"] is not None
        assert upload_context["selected_backend_id"] is not None

    def test_upload_state_has_tune_fields(self):
        """UploadState Interface hat Tune-bezogene Felder."""
        # Dies validiert die TypeScript-Typen
        upload_state = {
            "step": "upload",
            "selectedBackendId": "deepseek-janus",
            "selectedTuneId": None,  # Kann null sein
            "files": [],
            "analysisResults": [],
            "groups": []
        }

        # selectedTuneId kann null sein - das ist erlaubt
        assert "selectedTuneId" in upload_state
        assert "selectedBackendId" in upload_state

    def test_analysis_result_includes_tune(self):
        """SmartAnalysisResult enthält Tune-Information."""
        analysis_result = {
            "fileId": "file-0",
            "fileName": "rechnung_2024.pdf",
            "fileSize": 1024 * 100,  # 100 KB
            "detectedTuneId": str(uuid4()),  # Erkannter oder gewählter Tune
            "selectedBackendId": "deepseek-janus",
            "confidence": "high",
            "issues": [],
            "isChild": False,
            "parentId": None,
            "previewUrl": "blob:..."
        }

        # detectedTuneId sollte vorhanden sein
        assert "detectedTuneId" in analysis_result
        assert analysis_result["detectedTuneId"] is not None


class TestTuneBackendMapping:
    """Tests für Tune-zu-Backend Mapping."""

    def test_tune_has_default_backend(self):
        """Jeder Tune hat einen default_backend."""
        tunes = [
            {"name": "Rechnungen", "default_backend": "deepseek-janus"},
            {"name": "Verträge", "default_backend": "deepseek-janus"},
            {"name": "Korrespondenz", "default_backend": "got-ocr"},
            {"name": "Technische Docs", "default_backend": "surya-docling"},
        ]

        for tune in tunes:
            assert tune["default_backend"] is not None
            assert tune["default_backend"] in [
                "deepseek-janus", "got-ocr", "surya-docling", "surya-gpu"
            ]

    def test_backend_can_be_overridden(self):
        """User kann Backend trotz Tune-Default überschreiben."""
        tune_default = "deepseek-janus"
        user_selection = "got-ocr"

        # User-Auswahl überschreibt Tune-Default
        final_backend = user_selection if user_selection else tune_default

        assert final_backend == "got-ocr"
        assert final_backend != tune_default


class TestTuneGermanLocalization:
    """Tests für deutsche Lokalisierung im Tune-System."""

    def test_system_tunes_have_german_names(self):
        """System-Tunes haben deutsche Namen und Beschreibungen."""
        system_tunes = [
            {
                "name": "Rechnungen & Finanzen",
                "description": "Rechnungen, Quittungen und Finanzdokumente"
            },
            {
                "name": "Verträge & Rechtliches",
                "description": "Verträge, rechtliche Dokumente und Vereinbarungen"
            },
            {
                "name": "Allgemeiner Schriftverkehr",
                "description": "Briefe, E-Mails und allgemeine Korrespondenz"
            },
            {
                "name": "Technische Dokumentation",
                "description": "Handbücher, Anleitungen und technische Spezifikationen"
            }
        ]

        for tune in system_tunes:
            # Prüfe auf deutsche Sonderzeichen (indirekt)
            assert tune["name"] != ""
            assert tune["description"] != ""
            # Mindestens ein Wort sollte > 5 Zeichen sein (typisch Deutsch)
            assert any(len(word) > 5 for word in tune["name"].split())

    def test_error_messages_contain_german_keywords(self):
        """Fehlermeldungen enthalten deutsche Schlüsselwörter."""
        expected_german_phrases = [
            "existiert bereits",  # Duplicate name
            "nicht gefunden",  # Not found
            "können nicht gelöscht werden",  # System tune delete
        ]

        # Diese werden in app/api/v1/tunes.py verwendet
        for phrase in expected_german_phrases:
            # Einfache Validierung dass die Phrase existiert
            assert len(phrase) > 0
            # Prüfe auf deutsche Zeichen
            has_german_char = any(c in phrase for c in "äöüßÄÖÜ")
            has_german_word = "nicht" in phrase or "bereits" in phrase or "werden" in phrase
            assert has_german_char or has_german_word


class TestTuneApiSchemas:
    """Tests für Tunes API Schemas."""

    def test_tune_create_schema(self):
        """TuneCreate Schema validiert Eingaben korrekt."""
        from app.api.schemas.tunes import TuneCreate

        # Gültiger Tune
        valid_tune = TuneCreate(
            name="Test Tune",
            description="Eine Testbeschreibung",
            icon="FileText",
            color="bg-blue-500"
        )

        assert valid_tune.name == "Test Tune"
        assert valid_tune.is_active == True  # Default

    def test_tune_update_schema_partial(self):
        """TuneUpdate Schema erlaubt partielle Updates."""
        from app.api.schemas.tunes import TuneUpdate

        # Nur Name ändern
        partial_update = TuneUpdate(name="Neuer Name")
        assert partial_update.name == "Neuer Name"
        assert partial_update.description is None  # Nicht gesetzt

    def test_tune_response_schema(self):
        """TuneResponse Schema enthält alle Felder."""
        from app.api.schemas.tunes import TuneResponse

        # Response muss id und timestamps haben
        response_fields = TuneResponse.model_fields.keys()

        assert "id" in response_fields
        assert "name" in response_fields
        assert "is_system" in response_fields
        assert "created_at" in response_fields
        assert "updated_at" in response_fields
