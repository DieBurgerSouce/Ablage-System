"""Unit tests for Help System API.

Tests für:
- Hilfe-Artikel abrufen
- Onboarding-Status und Fortschritt
- Tooltips
- Video-Tutorials
- Benutzer-Präferenzen
- Such-Funktionalität
"""

import pytest
from datetime import datetime, timezone
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


@pytest.mark.asyncio
class TestHelpArticles:
    """Tests für Hilfe-Artikel Endpoints."""

    async def test_get_all_help_articles(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """Alle Hilfe-Artikel abrufen."""
        response = await client.get(
            "/api/v1/help/articles",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "articles" in data
        assert "total" in data
        assert data["total"] > 0
        assert len(data["articles"]) == data["total"]

        # Prüfe Artikel-Struktur
        article = data["articles"][0]
        assert "id" in article
        assert "title" in article
        assert "content" in article
        assert "category" in article
        assert "tags" in article

    async def test_filter_articles_by_category(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """Artikel nach Kategorie filtern."""
        response = await client.get(
            "/api/v1/help/articles?category=getting-started",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "getting-started"
        assert all(
            a["category"] == "getting-started"
            for a in data["articles"]
        )

    async def test_filter_articles_by_context(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """Artikel nach Kontext filtern."""
        response = await client.get(
            "/api/v1/help/articles?context=documents",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert all(
            a.get("context") == "documents"
            for a in data["articles"]
        )

    async def test_get_single_article(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """Einzelnen Artikel abrufen."""
        response = await client.get(
            "/api/v1/help/articles/getting-started-overview",
            headers=auth_headers
        )

        assert response.status_code == 200
        article = response.json()
        assert article["id"] == "getting-started-overview"
        assert article["title"] == "Erste Schritte"
        assert "content" in article
        assert article["category"] == "getting-started"

    async def test_get_nonexistent_article(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """Nicht-existierenden Artikel abrufen."""
        response = await client.get(
            "/api/v1/help/articles/nonexistent-id",
            headers=auth_headers
        )

        assert response.status_code == 404
        assert "nicht gefunden" in response.json()["detail"]

    async def test_get_articles_by_context_endpoint(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """Artikel via Context-Endpoint abrufen."""
        response = await client.get(
            "/api/v1/help/articles/context/ocr-settings",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert all(
            a.get("context") == "ocr-settings"
            for a in data["articles"]
        )


@pytest.mark.asyncio
class TestHelpSearch:
    """Tests für Hilfe-Suche."""

    async def test_search_articles(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """Artikel durchsuchen."""
        response = await client.get(
            "/api/v1/help/search?q=ocr",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "total" in data
        assert "query" in data
        assert data["query"] == "ocr"
        assert data["total"] > 0

        # Prüfe Ergebnis-Struktur
        result = data["results"][0]
        assert "article" in result
        assert "score" in result
        assert 0.0 <= result["score"] <= 1.0

    async def test_search_title_match(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """Suche mit Titel-Match hat höchsten Score."""
        response = await client.get(
            "/api/v1/help/search?q=erste schritte",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] > 0

        # Erstes Ergebnis sollte höchsten Score haben
        results = data["results"]
        assert results[0]["score"] == 1.0  # Titel-Match

    async def test_search_min_length(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """Suche mit zu kurzem Query."""
        response = await client.get(
            "/api/v1/help/search?q=x",
            headers=auth_headers
        )

        assert response.status_code == 422  # Validation error

    async def test_search_no_results(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """Suche ohne Ergebnisse."""
        response = await client.get(
            "/api/v1/help/search?q=xyznonexistent",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["results"] == []


@pytest.mark.asyncio
class TestTooltips:
    """Tests für Tooltip Endpoints."""

    async def test_get_tooltip(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """Tooltip abrufen."""
        response = await client.get(
            "/api/v1/help/tooltips/upload-button",
            headers=auth_headers
        )

        assert response.status_code == 200
        tooltip = response.json()
        assert tooltip["feature_id"] == "upload-button"
        assert "title" in tooltip
        assert "content" in tooltip
        assert "position" in tooltip

    async def test_get_nonexistent_tooltip(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """Nicht-existierenden Tooltip abrufen."""
        response = await client.get(
            "/api/v1/help/tooltips/nonexistent-feature",
            headers=auth_headers
        )

        assert response.status_code == 404

    async def test_dismissed_tooltip_returns_404(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """Ausgeblendeter Tooltip gibt 404 zurück."""
        # 1. Tooltip ausblenden
        await client.patch(
            "/api/v1/help/preferences",
            json={"dismiss_tooltip": "upload-button-tooltip"},
            headers=auth_headers
        )

        # 2. Tooltip abrufen sollte 404 geben
        response = await client.get(
            "/api/v1/help/tooltips/upload-button",
            headers=auth_headers
        )

        assert response.status_code == 404
        assert "ausgeblendet" in response.json()["detail"]


@pytest.mark.asyncio
class TestOnboarding:
    """Tests für Onboarding Endpoints."""

    async def test_get_onboarding_status_new_user(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """Onboarding-Status für neuen User."""
        response = await client.get(
            "/api/v1/help/onboarding",
            headers=auth_headers
        )

        assert response.status_code == 200
        status = response.json()
        assert status["steps_completed"] == 0
        assert status["total_steps"] == 5
        assert status["completed"] is False
        assert status["skipped"] is False
        assert len(status["steps"]) == 5
        assert status["current_step"] == "welcome"

        # Alle Schritte sollten uncompleted sein
        assert all(not s["completed"] for s in status["steps"])

    async def test_complete_onboarding_step(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """Onboarding-Schritt erledigen."""
        response = await client.patch(
            "/api/v1/help/onboarding/step/welcome",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "Schritt 'welcome' als erledigt markiert" in data["message"]
        assert data["steps_completed"] == 1
        assert data["total_steps"] == 5

        # Status prüfen
        status_response = await client.get(
            "/api/v1/help/onboarding",
            headers=auth_headers
        )
        status = status_response.json()
        assert status["steps_completed"] == 1
        assert status["current_step"] == "upload-document"

        # Welcome-Schritt sollte completed sein
        welcome_step = next(s for s in status["steps"] if s["id"] == "welcome")
        assert welcome_step["completed"] is True

    async def test_complete_invalid_step(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """Ungültigen Schritt erledigen."""
        response = await client.patch(
            "/api/v1/help/onboarding/step/invalid-step",
            headers=auth_headers
        )

        assert response.status_code == 404

    async def test_complete_all_steps(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """Alle Onboarding-Schritte erledigen."""
        steps = ["welcome", "upload-document", "ocr-processing", "search-documents", "organize-tags"]

        for step in steps:
            await client.patch(
                f"/api/v1/help/onboarding/step/{step}",
                headers=auth_headers
            )

        # Status prüfen
        response = await client.get(
            "/api/v1/help/onboarding",
            headers=auth_headers
        )
        status = response.json()
        assert status["steps_completed"] == 5
        assert status["completed"] is True
        assert status["current_step"] is None

    async def test_skip_onboarding(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """Onboarding überspringen."""
        response = await client.post(
            "/api/v1/help/onboarding/skip",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "übersprungen" in data["message"]
        assert data["onboarding_completed"] is True

        # Preferences prüfen
        prefs_response = await client.get(
            "/api/v1/help/preferences",
            headers=auth_headers
        )
        prefs = prefs_response.json()
        assert prefs["onboarding_completed"] is True
        assert prefs["show_onboarding"] is False

    async def test_reset_onboarding(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """Onboarding zurücksetzen."""
        # 1. Schritt erledigen
        await client.patch(
            "/api/v1/help/onboarding/step/welcome",
            headers=auth_headers
        )

        # 2. Zurücksetzen
        response = await client.post(
            "/api/v1/help/onboarding/reset",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "zurückgesetzt" in data["message"]
        assert data["onboarding_completed"] is False
        assert data["steps_completed"] == 0

        # Status prüfen
        status_response = await client.get(
            "/api/v1/help/onboarding",
            headers=auth_headers
        )
        status = status_response.json()
        assert status["steps_completed"] == 0
        assert all(not s["completed"] for s in status["steps"])


@pytest.mark.asyncio
class TestVideoTutorials:
    """Tests für Video-Tutorial Endpoints."""

    async def test_get_all_videos(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """Alle Videos abrufen."""
        response = await client.get(
            "/api/v1/help/videos",
            headers=auth_headers
        )

        assert response.status_code == 200
        videos = response.json()
        assert len(videos) > 0

        # Prüfe Video-Struktur
        video = videos[0]
        assert "id" in video
        assert "title" in video
        assert "description" in video
        assert "url" in video
        assert "category" in video
        assert "duration" in video

    async def test_filter_videos_by_category(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """Videos nach Kategorie filtern."""
        response = await client.get(
            "/api/v1/help/videos?category=getting-started",
            headers=auth_headers
        )

        assert response.status_code == 200
        videos = response.json()
        assert all(v["category"] == "getting-started" for v in videos)


@pytest.mark.asyncio
class TestHelpPreferences:
    """Tests für Hilfe-Präferenzen."""

    async def test_get_default_preferences(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """Default-Präferenzen abrufen."""
        response = await client.get(
            "/api/v1/help/preferences",
            headers=auth_headers
        )

        assert response.status_code == 200
        prefs = response.json()
        assert prefs["show_hints"] is True
        assert prefs["show_onboarding"] is True
        assert prefs["onboarding_completed"] is False
        assert prefs["dismissed_tooltips"] == []
        assert prefs["completed_steps"] == []
        assert "last_updated" in prefs

    async def test_update_preferences(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """Präferenzen aktualisieren."""
        response = await client.patch(
            "/api/v1/help/preferences",
            json={
                "show_hints": False,
                "show_onboarding": False
            },
            headers=auth_headers
        )

        assert response.status_code == 200
        prefs = response.json()
        assert prefs["show_hints"] is False
        assert prefs["show_onboarding"] is False

    async def test_dismiss_tooltip(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """Tooltip ausblenden."""
        response = await client.patch(
            "/api/v1/help/preferences",
            json={"dismiss_tooltip": "upload-button-tooltip"},
            headers=auth_headers
        )

        assert response.status_code == 200
        prefs = response.json()
        assert "upload-button-tooltip" in prefs["dismissed_tooltips"]

    async def test_restore_tooltip(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """Tooltip wiederherstellen."""
        # 1. Ausblenden
        await client.patch(
            "/api/v1/help/preferences",
            json={"dismiss_tooltip": "upload-button-tooltip"},
            headers=auth_headers
        )

        # 2. Wiederherstellen
        response = await client.patch(
            "/api/v1/help/preferences",
            json={"restore_tooltip": "upload-button-tooltip"},
            headers=auth_headers
        )

        assert response.status_code == 200
        prefs = response.json()
        assert "upload-button-tooltip" not in prefs["dismissed_tooltips"]

    async def test_dismiss_multiple_tooltips(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """Mehrere Tooltips ausblenden."""
        # Tooltip 1
        await client.patch(
            "/api/v1/help/preferences",
            json={"dismiss_tooltip": "upload-button-tooltip"},
            headers=auth_headers
        )

        # Tooltip 2
        await client.patch(
            "/api/v1/help/preferences",
            json={"dismiss_tooltip": "search-tooltip"},
            headers=auth_headers
        )

        # Prüfen
        response = await client.get(
            "/api/v1/help/preferences",
            headers=auth_headers
        )
        prefs = response.json()
        assert len(prefs["dismissed_tooltips"]) == 2
        assert "upload-button-tooltip" in prefs["dismissed_tooltips"]
        assert "search-tooltip" in prefs["dismissed_tooltips"]


@pytest.mark.asyncio
class TestHelpIntegration:
    """Integrations-Tests für komplette Workflows."""

    async def test_complete_onboarding_workflow(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """Kompletter Onboarding-Workflow."""
        # 1. Initial-Status
        response = await client.get("/api/v1/help/onboarding", headers=auth_headers)
        status = response.json()
        assert status["steps_completed"] == 0

        # 2. Ersten Schritt erledigen
        await client.patch(
            "/api/v1/help/onboarding/step/welcome",
            headers=auth_headers
        )

        # 3. Zweiten Schritt erledigen
        await client.patch(
            "/api/v1/help/onboarding/step/upload-document",
            headers=auth_headers
        )

        # 4. Status prüfen
        response = await client.get("/api/v1/help/onboarding", headers=auth_headers)
        status = response.json()
        assert status["steps_completed"] == 2
        assert status["current_step"] == "ocr-processing"

        # 5. Onboarding überspringen
        await client.post("/api/v1/help/onboarding/skip", headers=auth_headers)

        # 6. Final-Status
        response = await client.get("/api/v1/help/onboarding", headers=auth_headers)
        status = response.json()
        assert status["skipped"] is True
        assert status["completed"] is True

    async def test_contextual_help_workflow(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """Kontextuelle Hilfe abrufen."""
        # 1. Artikel für Dokumente-Seite
        response = await client.get(
            "/api/v1/help/articles/context/documents",
            headers=auth_headers
        )
        assert response.status_code == 200
        articles = response.json()["articles"]
        assert len(articles) > 0

        # 2. Spezifischen Artikel lesen
        article_id = articles[0]["id"]
        response = await client.get(
            f"/api/v1/help/articles/{article_id}",
            headers=auth_headers
        )
        assert response.status_code == 200

        # 3. Tooltip für Upload-Button
        response = await client.get(
            "/api/v1/help/tooltips/upload-button",
            headers=auth_headers
        )
        assert response.status_code == 200

        # 4. Tooltip ausblenden
        await client.patch(
            "/api/v1/help/preferences",
            json={"dismiss_tooltip": "upload-button-tooltip"},
            headers=auth_headers
        )

        # 5. Tooltip sollte jetzt 404 geben
        response = await client.get(
            "/api/v1/help/tooltips/upload-button",
            headers=auth_headers
        )
        assert response.status_code == 404

    async def test_search_and_read_workflow(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """Suche und Artikel lesen."""
        # 1. Nach OCR suchen
        response = await client.get(
            "/api/v1/help/search?q=ocr",
            headers=auth_headers
        )
        assert response.status_code == 200
        results = response.json()["results"]
        assert len(results) > 0

        # 2. Ersten Artikel lesen
        article_id = results[0]["article"]["id"]
        response = await client.get(
            f"/api/v1/help/articles/{article_id}",
            headers=auth_headers
        )
        assert response.status_code == 200

        # 3. Verwandte Videos suchen
        category = response.json()["category"]
        response = await client.get(
            f"/api/v1/help/videos?category={category}",
            headers=auth_headers
        )
        assert response.status_code == 200


@pytest.mark.asyncio
class TestHelpAuthentication:
    """Tests für Authentifizierung."""

    async def test_requires_authentication(self, client: AsyncClient):
        """Alle Endpoints erfordern Authentifizierung."""
        endpoints = [
            "/api/v1/help/articles",
            "/api/v1/help/articles/getting-started-overview",
            "/api/v1/help/search?q=test",
            "/api/v1/help/tooltips/upload-button",
            "/api/v1/help/onboarding",
            "/api/v1/help/videos",
            "/api/v1/help/preferences"
        ]

        for endpoint in endpoints:
            response = await client.get(endpoint)
            assert response.status_code == 401
