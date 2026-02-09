# -*- coding: utf-8 -*-
"""
Unit-Tests fuer NotificationTemplateEngine.send_with_template().

Testet:
- Erfolgreichen Versand ueber alle Channels
- Template nicht gefunden
- Rendering-Fehler (fehlende Variablen)
- Einzelner Channel-Fehler (hub.send Exception)
- Teilerfolg (gemischte Channel-Ergebnisse)
- Standard-Channels aus Template
- Ungueltiger Severity-Wert
- Ungueltige Template-Kategorie
- severity=None (TypeError-Pfad)
- Deaktivierte Vorlage (is_active=False)
- Leere Delivery-Ergebnisse
- Delivery mit success=False

Feinpoliert und durchdacht - send_with_template Tests.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import UUID

from app.services.notification.template_engine import NotificationTemplateEngine
from app.db.models_notification_template import NotificationMessageTemplate as NotificationTemplate


# Test-Konstanten
TEST_USER_UUID = UUID("00000000-0000-0000-0000-000000000001")
TEST_TEMPLATE_UUID = UUID("00000000-0000-0000-0000-000000000002")


@pytest.fixture
def mock_db():
    """Erstelle Mock AsyncSession."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def template_engine(mock_db):
    """Erstelle NotificationTemplateEngine-Instanz."""
    return NotificationTemplateEngine(mock_db)


@pytest.fixture
def sample_template():
    """Erstelle Beispiel-Template mit Channels."""
    return NotificationTemplate(
        id=TEST_TEMPLATE_UUID,
        name="test_send",
        category="document",
        subject_template="Test: {{ title }}",
        body_template="Nachricht: {{ message }}",
        variables={
            "required": ["title", "message"],
            "optional": [],
        },
        channels=["email", "in_app"],
        is_active=True,
        created_by_id=TEST_USER_UUID,
    )


@pytest.fixture
def sample_variables():
    """Standard-Variablen fuer Tests."""
    return {
        "title": "Rechnung-2024.pdf",
        "message": "Dokument verarbeitet",
    }


def _make_delivery_result(success: bool = True) -> MagicMock:
    """Erstelle Mock NotificationDeliveryResult."""
    result = MagicMock()
    result.success = success
    return result


# ========================= Success Tests =========================


@pytest.mark.asyncio
async def test_send_with_template_success(
    template_engine, mock_db, sample_template, sample_variables
):
    """Test: Erfolgreicher Versand ueber alle Channels."""
    # Mock get_template
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = AsyncMock(return_value=sample_template)
    mock_db.execute.return_value = mock_result

    with patch(
        "app.services.notification.template_engine.UnifiedNotificationHub"
    ) as MockHub:
        mock_hub_instance = AsyncMock()
        mock_hub_instance.send = AsyncMock(
            return_value=[_make_delivery_result(success=True)]
        )
        MockHub.return_value = mock_hub_instance

        result = await template_engine.send_with_template(
            template_id=TEST_TEMPLATE_UUID,
            variables=sample_variables,
            recipient_id=TEST_USER_UUID,
            channels=["email", "in_app"],
            severity="info",
        )

    assert result["success"] is True
    assert "2/2" in result["message"]
    assert result["results"]["email"] is True
    assert result["results"]["in_app"] is True
    assert mock_hub_instance.send.call_count == 2


# ========================= Not Found Tests =========================


@pytest.mark.asyncio
async def test_send_with_template_not_found(
    template_engine, mock_db, sample_variables
):
    """Test: Template nicht gefunden gibt Fehler zurueck."""
    # Mock get_template returning None
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = AsyncMock(return_value=None)
    mock_db.execute.return_value = mock_result

    result = await template_engine.send_with_template(
        template_id=TEST_TEMPLATE_UUID,
        variables=sample_variables,
        recipient_id=TEST_USER_UUID,
    )

    assert result["success"] is False
    assert result["message"] == "Vorlage nicht gefunden"
    assert result["results"] == {}


# ========================= Render Failure Tests =========================


@pytest.mark.asyncio
async def test_send_with_template_render_failure(
    template_engine, mock_db
):
    """Test: Rendering-Fehler gibt Fehlermeldung zurueck."""
    # Template mit erforderlichen Variablen
    template = NotificationTemplate(
        id=TEST_TEMPLATE_UUID,
        name="test_render_fail",
        category="document",
        subject_template="Test: {{ title }}",
        body_template="Body: {{ message }}",
        variables={
            "required": ["title", "message"],
            "optional": [],
        },
        channels=["email"],
        is_active=True,
        created_by_id=TEST_USER_UUID,
    )

    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = AsyncMock(return_value=template)
    mock_db.execute.return_value = mock_result

    # Sende mit fehlenden Variablen -> Rendering schlaegt fehl
    result = await template_engine.send_with_template(
        template_id=TEST_TEMPLATE_UUID,
        variables={},  # Fehlende Pflicht-Variablen
        recipient_id=TEST_USER_UUID,
    )

    assert result["success"] is False
    assert "Fehlende Variablen" in result["message"]
    assert result["results"] == {}


# ========================= Channel Failure Tests =========================


@pytest.mark.asyncio
async def test_send_with_template_channel_failure(
    template_engine, mock_db, sample_template, sample_variables
):
    """Test: hub.send() wirft Exception -> Channel ergibt False."""
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = AsyncMock(return_value=sample_template)
    mock_db.execute.return_value = mock_result

    with patch(
        "app.services.notification.template_engine.UnifiedNotificationHub"
    ) as MockHub:
        mock_hub_instance = AsyncMock()
        mock_hub_instance.send = AsyncMock(
            side_effect=Exception("Connection refused")
        )
        MockHub.return_value = mock_hub_instance

        result = await template_engine.send_with_template(
            template_id=TEST_TEMPLATE_UUID,
            variables=sample_variables,
            recipient_id=TEST_USER_UUID,
            channels=["email"],
            severity="info",
        )

    assert result["success"] is False
    assert "0/1" in result["message"]
    assert result["results"]["email"] is False


# ========================= Partial Success Tests =========================


@pytest.mark.asyncio
async def test_send_with_template_partial_success(
    template_engine, mock_db, sample_template, sample_variables
):
    """Test: 2 Channels, 1 erfolgreich, 1 fehlgeschlagen."""
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = AsyncMock(return_value=sample_template)
    mock_db.execute.return_value = mock_result

    with patch(
        "app.services.notification.template_engine.UnifiedNotificationHub"
    ) as MockHub:
        mock_hub_instance = AsyncMock()
        mock_hub_instance.send = AsyncMock(side_effect=[
            [_make_delivery_result(success=True)],
            Exception("Channel unavailable"),
        ])
        MockHub.return_value = mock_hub_instance

        result = await template_engine.send_with_template(
            template_id=TEST_TEMPLATE_UUID,
            variables=sample_variables,
            recipient_id=TEST_USER_UUID,
            channels=["email", "in_app"],
            severity="info",
        )

    assert result["success"] is True
    assert "1/2" in result["message"]
    assert result["results"]["email"] is True
    assert result["results"]["in_app"] is False


# ========================= Default Channels Tests =========================


@pytest.mark.asyncio
async def test_send_with_template_default_channels(
    template_engine, mock_db, sample_variables
):
    """Test: Verwendet template.channels wenn keine uebergeben."""
    template = NotificationTemplate(
        id=TEST_TEMPLATE_UUID,
        name="test_defaults",
        category="system",
        subject_template="Test: {{ title }}",
        body_template="Body: {{ message }}",
        variables={
            "required": ["title", "message"],
            "optional": [],
        },
        channels=["slack"],  # Nur Slack als Template-Default
        is_active=True,
        created_by_id=TEST_USER_UUID,
    )

    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = AsyncMock(return_value=template)
    mock_db.execute.return_value = mock_result

    with patch(
        "app.services.notification.template_engine.UnifiedNotificationHub"
    ) as MockHub:
        mock_hub_instance = AsyncMock()
        mock_hub_instance.send = AsyncMock(
            return_value=[_make_delivery_result(success=True)]
        )
        MockHub.return_value = mock_hub_instance

        result = await template_engine.send_with_template(
            template_id=TEST_TEMPLATE_UUID,
            variables=sample_variables,
            recipient_id=TEST_USER_UUID,
            # channels=None -> nutzt template.channels
            severity="low",
        )

    assert result["success"] is True
    assert "1/1" in result["message"]
    assert result["results"]["slack"] is True
    assert mock_hub_instance.send.call_count == 1


# ========================= Invalid Severity/Category Tests =========================


@pytest.mark.asyncio
async def test_send_with_template_invalid_severity(
    template_engine, mock_db, sample_template, sample_variables
):
    """Test: Ungueltiger Severity-Wert gibt Fehler zurueck."""
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = AsyncMock(return_value=sample_template)
    mock_db.execute.return_value = mock_result

    with patch(
        "app.services.notification.template_engine.UnifiedNotificationHub"
    ) as MockHub:
        mock_hub_instance = AsyncMock()
        MockHub.return_value = mock_hub_instance

        result = await template_engine.send_with_template(
            template_id=TEST_TEMPLATE_UUID,
            variables=sample_variables,
            recipient_id=TEST_USER_UUID,
            channels=["email"],
            severity="nonexistent",
        )

    assert result["success"] is False
    assert result["message"] == "Ungueltiger Severity- oder Kategorie-Wert"
    assert result["results"] == {}
    mock_hub_instance.send.assert_not_called()


@pytest.mark.asyncio
async def test_send_with_template_invalid_category(
    template_engine, mock_db, sample_variables
):
    """Test: Ungueltige Template-Kategorie gibt Fehler zurueck."""
    template = NotificationTemplate(
        id=TEST_TEMPLATE_UUID,
        name="test_bad_category",
        category="bogus",  # Nicht in NotificationCategory enum
        subject_template="Test: {{ title }}",
        body_template="Body: {{ message }}",
        variables={
            "required": ["title", "message"],
            "optional": [],
        },
        channels=["email"],
        is_active=True,
        created_by_id=TEST_USER_UUID,
    )

    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = AsyncMock(return_value=template)
    mock_db.execute.return_value = mock_result

    with patch(
        "app.services.notification.template_engine.UnifiedNotificationHub"
    ) as MockHub:
        mock_hub_instance = AsyncMock()
        MockHub.return_value = mock_hub_instance

        result = await template_engine.send_with_template(
            template_id=TEST_TEMPLATE_UUID,
            variables=sample_variables,
            recipient_id=TEST_USER_UUID,
            channels=["email"],
            severity="info",
        )

    assert result["success"] is False
    assert result["message"] == "Ungueltiger Severity- oder Kategorie-Wert"
    assert result["results"] == {}
    mock_hub_instance.send.assert_not_called()


@pytest.mark.asyncio
async def test_send_with_template_none_severity(
    template_engine, mock_db, sample_template, sample_variables
):
    """Test: severity=None loest TypeError aus -> Fehler zurueck."""
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = AsyncMock(return_value=sample_template)
    mock_db.execute.return_value = mock_result

    with patch(
        "app.services.notification.template_engine.UnifiedNotificationHub"
    ) as MockHub:
        mock_hub_instance = AsyncMock()
        MockHub.return_value = mock_hub_instance

        result = await template_engine.send_with_template(
            template_id=TEST_TEMPLATE_UUID,
            variables=sample_variables,
            recipient_id=TEST_USER_UUID,
            channels=["email"],
            severity=None,  # type: ignore[arg-type]  # Defensive: testen TypeError-Pfad
        )

    assert result["success"] is False
    assert result["message"] == "Ungueltiger Severity- oder Kategorie-Wert"
    assert result["results"] == {}
    mock_hub_instance.send.assert_not_called()


# ========================= Inactive Template Tests =========================


@pytest.mark.asyncio
async def test_send_with_template_inactive_template(
    template_engine, mock_db, sample_variables
):
    """Test: Deaktivierte Vorlage gibt Rendering-Fehler zurueck."""
    template = NotificationTemplate(
        id=TEST_TEMPLATE_UUID,
        name="test_inactive",
        category="document",
        subject_template="Test: {{ title }}",
        body_template="Body: {{ message }}",
        variables={
            "required": ["title", "message"],
            "optional": [],
        },
        channels=["email"],
        is_active=False,
        created_by_id=TEST_USER_UUID,
    )

    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = AsyncMock(return_value=template)
    mock_db.execute.return_value = mock_result

    result = await template_engine.send_with_template(
        template_id=TEST_TEMPLATE_UUID,
        variables=sample_variables,
        recipient_id=TEST_USER_UUID,
    )

    assert result["success"] is False
    assert "deaktiviert" in result["message"]
    assert result["results"] == {}


# ========================= Empty Delivery Results Tests =========================


@pytest.mark.asyncio
async def test_send_with_template_empty_delivery(
    template_engine, mock_db, sample_template, sample_variables
):
    """Test: hub.send() gibt leere Liste zurueck -> Channel False."""
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = AsyncMock(return_value=sample_template)
    mock_db.execute.return_value = mock_result

    with patch(
        "app.services.notification.template_engine.UnifiedNotificationHub"
    ) as MockHub:
        mock_hub_instance = AsyncMock()
        mock_hub_instance.send = AsyncMock(return_value=[])
        MockHub.return_value = mock_hub_instance

        result = await template_engine.send_with_template(
            template_id=TEST_TEMPLATE_UUID,
            variables=sample_variables,
            recipient_id=TEST_USER_UUID,
            channels=["email"],
            severity="info",
        )

    assert result["success"] is False
    assert "0/1" in result["message"]
    assert result["results"]["email"] is False


# ========================= Delivery Failure Tests =========================


@pytest.mark.asyncio
async def test_send_with_template_delivery_failure(
    template_engine, mock_db, sample_template, sample_variables
):
    """Test: hub.send() gibt result mit success=False zurueck."""
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = AsyncMock(return_value=sample_template)
    mock_db.execute.return_value = mock_result

    with patch(
        "app.services.notification.template_engine.UnifiedNotificationHub"
    ) as MockHub:
        mock_hub_instance = AsyncMock()
        mock_hub_instance.send = AsyncMock(
            return_value=[_make_delivery_result(success=False)]
        )
        MockHub.return_value = mock_hub_instance

        result = await template_engine.send_with_template(
            template_id=TEST_TEMPLATE_UUID,
            variables=sample_variables,
            recipient_id=TEST_USER_UUID,
            channels=["email"],
            severity="info",
        )

    assert result["success"] is False
    assert "0/1" in result["message"]
    assert result["results"]["email"] is False
