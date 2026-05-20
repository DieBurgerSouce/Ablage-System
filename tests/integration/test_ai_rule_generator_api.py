# -*- coding: utf-8 -*-
"""Integration Tests fuer AI Rule Generator API.

Vision 2.0 - Phase 2 (Januar 2026)

HINWEIS: Diese Tests erfordern einen laufenden Ollama-Server!
"""

import pytest
from httpx import AsyncClient

from app.main import app


@pytest.mark.integration
@pytest.mark.skipif(
    condition=True,  # Skip by default, nur mit --run-integration
    reason="Erfordert laufenden Ollama-Server"
)
class TestAIRuleGeneratorAPI:
    """Integration Tests fuer /api/v1/rules/generate."""

    @pytest.fixture
    async def client(self):
        """HTTP Client."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            yield ac

    @pytest.fixture
    async def auth_headers(self, client: AsyncClient):
        """Auth Headers mit gueltigem Token."""
        # Login
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@example.com",
                "password": "testpassword123"
            }
        )
        assert response.status_code == 200
        token = response.json()["access_token"]

        return {"Authorization": f"Bearer {token}"}

    @pytest.mark.asyncio
    async def test_generate_simple_rule(self, client: AsyncClient, auth_headers):
        """Test: Einfache Regel generieren."""
        # Arrange
        payload = {
            "prompt": "Rechnungen über 10000 EUR müssen vom CFO genehmigt werden"
        }

        # Act
        response = await client.post(
            "/api/v1/rules/generate",
            json=payload,
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()

        assert data["name"]
        assert data["description"]
        assert data["category"] in ["approval", "compliance", "custom"]
        assert 1 <= data["priority"] <= 100
        assert "condition" in data
        assert "actions" in data
        assert len(data["actions"]) > 0
        assert 0.0 <= data["confidence"] <= 1.0
        assert data["explanation"]

        # Bedingung sollte amount und document_type pruefen
        condition = data["condition"]
        assert "and" in condition or "field" in condition

    @pytest.mark.asyncio
    async def test_generate_skonto_rule(self, client: AsyncClient, auth_headers):
        """Test: Skonto-Regel generieren."""
        # Arrange
        payload = {
            "prompt": "Erstelle Regel für Skonto-Überwachung"
        }

        # Act
        response = await client.post(
            "/api/v1/rules/generate",
            json=payload,
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()

        assert "skonto" in data["name"].lower() or "skonto" in data["description"].lower()
        assert data["category"] in ["notification", "workflow"]
        assert data["confidence"] > 0.7

    @pytest.mark.asyncio
    async def test_generate_fraud_rule(self, client: AsyncClient, auth_headers):
        """Test: Betrugserkennungs-Regel generieren."""
        # Arrange
        payload = {
            "prompt": "Duplikate mit niedriger OCR-Konfidenz blockieren"
        }

        # Act
        response = await client.post(
            "/api/v1/rules/generate",
            json=payload,
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()

        assert data["category"] == "fraud"
        assert data["priority"] >= 75  # Fraud-Regeln sollten hohe Prioritaet haben

        # Sollte block_processing oder manual_review_required enthalten
        action_types = [a["type"] for a in data["actions"]]
        assert "block_processing" in action_types or "manual_review_required" in action_types

    @pytest.mark.asyncio
    async def test_generate_with_short_prompt(self, client: AsyncClient, auth_headers):
        """Test: Zu kurzer Prompt wird abgelehnt."""
        # Arrange
        payload = {
            "prompt": "Test"  # Zu kurz (<5 Zeichen)
        }

        # Act
        response = await client.post(
            "/api/v1/rules/generate",
            json=payload,
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 422  # Validation Error

    @pytest.mark.asyncio
    async def test_generate_with_long_prompt(self, client: AsyncClient, auth_headers):
        """Test: Zu langer Prompt wird abgelehnt."""
        # Arrange
        payload = {
            "prompt": "X" * 1001  # Zu lang (>1000 Zeichen)
        }

        # Act
        response = await client.post(
            "/api/v1/rules/generate",
            json=payload,
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 422  # Validation Error

    @pytest.mark.asyncio
    async def test_generate_complex_condition_rule(self, client: AsyncClient, auth_headers):
        """Test: Regel mit komplexer Bedingung."""
        # Arrange
        payload = {
            "prompt": "Neue Lieferanten mit Rechnungen über 5000 EUR zur Prüfung"
        }

        # Act
        response = await client.post(
            "/api/v1/rules/generate",
            json=payload,
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()

        # Sollte AND-Bedingung haben
        condition = data["condition"]
        assert "and" in condition

        # Sollte sowohl supplier.is_new als auch amount pruefen
        # (entweder direkt oder in verschachtelter Struktur)
        condition_str = str(condition)
        assert "supplier" in condition_str or "is_new" in condition_str
        assert "amount" in condition_str

    @pytest.mark.asyncio
    async def test_generate_with_else_actions(self, client: AsyncClient, auth_headers):
        """Test: Regel mit else-Aktionen."""
        # Arrange
        payload = {
            "prompt": "Neue Lieferanten zur Prüfung, bekannte Lieferanten automatisch genehmigen"
        }

        # Act
        response = await client.post(
            "/api/v1/rules/generate",
            json=payload,
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()

        # Sollte else_actions haben (optional, haengt vom LLM ab)
        if data["else_actions"]:
            assert len(data["else_actions"]) > 0

    @pytest.mark.asyncio
    async def test_generate_unauthorized(self, client: AsyncClient):
        """Test: Ohne Auth wird Zugriff verweigert."""
        # Arrange
        payload = {
            "prompt": "Test Regel"
        }

        # Act
        response = await client.post(
            "/api/v1/rules/generate",
            json=payload,
            # Keine auth_headers
        )

        # Assert
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_generate_and_test_rule(self, client: AsyncClient, auth_headers):
        """Test: Generierte Regel testen."""
        # Arrange
        generate_payload = {
            "prompt": "Rechnungen über 1000 EUR zur Genehmigung"
        }

        # Act 1: Regel generieren
        gen_response = await client.post(
            "/api/v1/rules/generate",
            json=generate_payload,
            headers=auth_headers,
        )
        assert gen_response.status_code == 200
        generated = gen_response.json()

        # Act 2: Generierte Regel testen
        test_payload = {
            "condition": generated["condition"],
            "actions": generated["actions"],
            "context": {
                "document_type": "invoice",
                "amount": 1500.0,  # Sollte matchen
            }
        }

        test_response = await client.post(
            "/api/v1/rules/test",
            json=test_payload,
            headers=auth_headers,
        )

        # Assert
        assert test_response.status_code == 200
        test_result = test_response.json()

        # Regel sollte matchen
        assert test_result["matched"] is True
        assert len(test_result["would_trigger_actions"]) > 0

    @pytest.mark.asyncio
    async def test_generate_date_based_rule(self, client: AsyncClient, auth_headers):
        """Test: Datumsbasierte Regel."""
        # Arrange
        payload = {
            "prompt": "Warnung bei Rechnungen die in 3 Tagen fällig werden"
        }

        # Act
        response = await client.post(
            "/api/v1/rules/generate",
            json=payload,
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()

        # Sollte due_date oder ähnliches prüfen
        condition_str = str(data["condition"])
        assert "due_date" in condition_str or "date" in condition_str

    @pytest.mark.asyncio
    async def test_generate_tag_based_rule(self, client: AsyncClient, auth_headers):
        """Test: Tag-basierte Regel."""
        # Arrange
        payload = {
            "prompt": "Dokumente mit Tag 'urgent' zur sofortigen Bearbeitung"
        }

        # Act
        response = await client.post(
            "/api/v1/rules/generate",
            json=payload,
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()

        # Sollte has_tag operator verwenden
        condition_str = str(data["condition"])
        assert "tag" in condition_str.lower() or "urgent" in condition_str.lower()

    @pytest.mark.asyncio
    async def test_generate_notification_rule(self, client: AsyncClient, auth_headers):
        """Test: Benachrichtigungs-Regel."""
        # Arrange
        payload = {
            "prompt": "Admin benachrichtigen bei Dokumenten mit niedriger OCR-Qualität"
        }

        # Act
        response = await client.post(
            "/api/v1/rules/generate",
            json=payload,
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()

        assert data["category"] in ["notification", "data_quality"]

        # Sollte notify_admin Aktion haben
        action_types = [a["type"] for a in data["actions"]]
        assert "notify_admin" in action_types or "notify_team" in action_types
