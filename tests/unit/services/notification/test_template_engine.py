# -*- coding: utf-8 -*-
"""
Unit-Tests fuer Notification Template Engine.

Testet:
- Template-Rendering mit Jinja2-Sandbox
- Variablenvalidierung
- Vorschau-Funktionen
- Template-CRUD-Operationen
- Sicherheitsmassnahmen (Sandbox-Schutz)
- Preset-Templates

Feinpoliert und durchdacht - Notification Template Engine Tests.
"""

import pytest
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import UUID, uuid4
from jinja2 import TemplateSyntaxError

from app.services.notification.template_engine import (
    NotificationTemplateEngine,
    PRESET_TEMPLATES,
    get_template_engine,
)
from app.db.models_notification_template import NotificationTemplate


# Test-Konstanten fuer gueltige UUIDs
TEST_USER_UUID = UUID("00000000-0000-0000-0000-000000000001")
TEST_TEMPLATE_UUID = UUID("00000000-0000-0000-0000-000000000002")


# ========================= Test Fixtures =========================


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
    """Erstelle Beispiel-Template-Objekt."""
    return NotificationTemplate(
        id=TEST_TEMPLATE_UUID,
        name="test_template",
        category="document",
        subject_template="Dokument verarbeitet: {{ document_title }}",
        body_template="""Hallo {{ user_name }},

das Dokument "{{ document_title }}" wurde erfolgreich verarbeitet.

Status: {{ status }}

Mit freundlichen Gruessen,
Ablage-System
""",
        variables={
            "required": ["user_name", "document_title", "status"],
            "optional": ["ocr_confidence"],
        },
        channels=["email", "in_app"],
        is_active=True,
        created_by_id=TEST_USER_UUID,
    )


@pytest.fixture
def sample_variables():
    """Erstelle Beispiel-Variablen-Dict."""
    return {
        "user_name": "Max Mustermann",
        "document_title": "Rechnung-2024.pdf",
        "status": "Erfolgreich",
    }


# ========================= Render Tests =========================


@pytest.mark.asyncio
async def test_render_notification_success(
    template_engine,
    mock_db,
    sample_template,
    sample_variables,
):
    """Test: Erfolgreiches Rendering mit allen erforderlichen Variablen."""
    # Mock DB response
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = AsyncMock(return_value=sample_template)
    mock_db.execute.return_value = mock_result

    # Render template
    result = await template_engine.render_notification(
        template_id=TEST_TEMPLATE_UUID,
        variables=sample_variables,
    )

    # Assertions
    assert isinstance(result, dict)
    assert "subject" in result
    assert "body" in result
    assert "Rechnung-2024.pdf" in result["subject"]
    assert "Max Mustermann" in result["body"]
    assert "Erfolgreich" in result["body"]


@pytest.mark.asyncio
async def test_render_notification_missing_variable(
    template_engine,
    mock_db,
    sample_template,
):
    """Test: Fehler bei fehlenden erforderlichen Variablen."""
    # Mock DB response
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = AsyncMock(return_value=sample_template)
    mock_db.execute.return_value = mock_result

    # Unvollstaendige Variablen (fehlt 'status')
    incomplete_vars = {
        "user_name": "Max Mustermann",
        "document_title": "Rechnung-2024.pdf",
    }

    # Should raise ValueError
    with pytest.raises(ValueError) as exc_info:
        await template_engine.render_notification(
            template_id=TEST_TEMPLATE_UUID,
            variables=incomplete_vars,
        )

    assert "Fehlende Variablen" in str(exc_info.value)
    assert "status" in str(exc_info.value)


@pytest.mark.asyncio
async def test_render_notification_template_not_found(
    template_engine,
    mock_db,
):
    """Test: Fehler bei nicht existierender Vorlage."""
    # Mock DB response - keine Vorlage gefunden
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = AsyncMock(return_value=None)
    mock_db.execute.return_value = mock_result

    with pytest.raises(ValueError) as exc_info:
        await template_engine.render_notification(
            template_id=TEST_TEMPLATE_UUID,
            variables={"key": "value"},
        )

    assert "nicht gefunden" in str(exc_info.value)


@pytest.mark.asyncio
async def test_render_notification_inactive_template(
    template_engine,
    mock_db,
    sample_template,
):
    """Test: Fehler bei deaktivierter Vorlage."""
    # Deaktiviere Template
    sample_template.is_active = False

    # Mock DB response
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = AsyncMock(return_value=sample_template)
    mock_db.execute.return_value = mock_result

    with pytest.raises(ValueError) as exc_info:
        await template_engine.render_notification(
            template_id=TEST_TEMPLATE_UUID,
            variables={"key": "value"},
        )

    assert "deaktiviert" in str(exc_info.value)


# ========================= Validation Tests =========================


@pytest.mark.asyncio
async def test_validate_variables_all_present(
    template_engine,
    mock_db,
    sample_template,
    sample_variables,
):
    """Test: Validierung mit allen erforderlichen Variablen."""
    # Mock DB response
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = AsyncMock(return_value=sample_template)
    mock_db.execute.return_value = mock_result

    # Validate
    validation = await template_engine.validate_variables(
        template_id=TEST_TEMPLATE_UUID,
        variables=sample_variables,
    )

    # Assertions
    assert validation["valid"] is True
    assert validation["missing"] == []


@pytest.mark.asyncio
async def test_validate_variables_missing(
    template_engine,
    mock_db,
    sample_template,
):
    """Test: Validierung meldet fehlende Variablen."""
    # Mock DB response
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = AsyncMock(return_value=sample_template)
    mock_db.execute.return_value = mock_result

    # Unvollstaendige Variablen
    incomplete_vars = {
        "user_name": "Max Mustermann",
        # Fehlen: document_title, status
    }

    # Validate
    validation = await template_engine.validate_variables(
        template_id=TEST_TEMPLATE_UUID,
        variables=incomplete_vars,
    )

    # Assertions
    assert validation["valid"] is False
    assert "document_title" in validation["missing"]
    assert "status" in validation["missing"]
    assert len(validation["missing"]) == 2


@pytest.mark.asyncio
async def test_validate_variables_template_not_found(
    template_engine,
    mock_db,
):
    """Test: Validierung bei nicht existierender Vorlage."""
    # Mock DB response - keine Vorlage
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = AsyncMock(return_value=None)
    mock_db.execute.return_value = mock_result

    # Validate
    validation = await template_engine.validate_variables(
        template_id=TEST_TEMPLATE_UUID,
        variables={"key": "value"},
    )

    # Assertions
    assert validation["valid"] is False
    assert "template_not_found" in validation["missing"]


# ========================= Preview Tests =========================


@pytest.mark.asyncio
async def test_preview_template_with_sample_data(
    template_engine,
    mock_db,
    sample_template,
    sample_variables,
):
    """Test: Vorschau mit benutzerdefinierten Beispieldaten."""
    # Mock DB response
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = AsyncMock(return_value=sample_template)
    mock_db.execute.return_value = mock_result

    # Preview with sample data
    preview = await template_engine.preview_template(
        template_id=TEST_TEMPLATE_UUID,
        sample_data=sample_variables,
    )

    # Assertions
    assert isinstance(preview, dict)
    assert "subject" in preview
    assert "body" in preview
    assert "Rechnung-2024.pdf" in preview["subject"]
    assert "Max Mustermann" in preview["body"]


@pytest.mark.asyncio
async def test_preview_template_default_data(
    template_engine,
    mock_db,
    sample_template,
):
    """Test: Vorschau mit Standard-Platzhaltern."""
    # Mock DB response
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = AsyncMock(return_value=sample_template)
    mock_db.execute.return_value = mock_result

    # Preview without sample data (uses placeholders)
    preview = await template_engine.preview_template(
        template_id=TEST_TEMPLATE_UUID,
    )

    # Assertions
    assert isinstance(preview, dict)
    assert "subject" in preview
    assert "body" in preview
    # Should contain uppercase placeholders
    assert "[DOCUMENT_TITLE]" in preview["subject"]
    assert "[USER_NAME]" in preview["body"]
    assert "[STATUS]" in preview["body"]


# ========================= CRUD Tests =========================


@pytest.mark.asyncio
async def test_create_template(
    template_engine,
    mock_db,
):
    """Test: Erstellen einer neuen Vorlage."""
    # Create template
    template = await template_engine.create_template(
        name="test_new_template",
        category="document",
        subject_template="Test: {{ title }}",
        body_template="Body: {{ message }}",
        variables={"required": ["title", "message"], "optional": []},
        channels=["email"],
        created_by_id=TEST_USER_UUID,
    )

    # Assertions
    assert mock_db.add.called
    assert mock_db.commit.called
    assert mock_db.refresh.called


@pytest.mark.asyncio
async def test_create_template_invalid_syntax(
    template_engine,
    mock_db,
):
    """Test: Fehler bei ungueltigem Jinja2-Template."""
    with pytest.raises(ValueError) as exc_info:
        await template_engine.create_template(
            name="test_invalid",
            category="document",
            subject_template="Test: {{ title }",  # Missing closing brace
            body_template="Body",
            variables=None,
            channels=None,
            created_by_id=TEST_USER_UUID,
        )

    assert "Template-Syntax-Fehler" in str(exc_info.value)


@pytest.mark.asyncio
async def test_update_template(
    template_engine,
    mock_db,
    sample_template,
):
    """Test: Aktualisieren einer bestehenden Vorlage."""
    # Mock DB response
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = AsyncMock(return_value=sample_template)
    mock_db.execute.return_value = mock_result

    # Update template
    updated = await template_engine.update_template(
        template_id=TEST_TEMPLATE_UUID,
        name="updated_name",
        category="system",
    )

    # Assertions
    assert updated is not None
    assert mock_db.commit.called
    assert mock_db.refresh.called
    assert sample_template.name == "updated_name"
    assert sample_template.category == "system"


@pytest.mark.asyncio
async def test_update_template_not_found(
    template_engine,
    mock_db,
):
    """Test: Update bei nicht existierender Vorlage."""
    # Mock DB response - keine Vorlage
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = AsyncMock(return_value=None)
    mock_db.execute.return_value = mock_result

    # Update should return None
    updated = await template_engine.update_template(
        template_id=TEST_TEMPLATE_UUID,
        name="updated",
    )

    assert updated is None


@pytest.mark.asyncio
async def test_delete_template_soft_delete(
    template_engine,
    mock_db,
    sample_template,
):
    """Test: Soft-Delete setzt is_active=False."""
    # Mock DB response
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = AsyncMock(return_value=sample_template)
    mock_db.execute.return_value = mock_result

    # Delete template
    success = await template_engine.delete_template(TEST_TEMPLATE_UUID)

    # Assertions
    assert success is True
    assert sample_template.is_active is False
    assert mock_db.commit.called


@pytest.mark.asyncio
async def test_delete_template_not_found(
    template_engine,
    mock_db,
):
    """Test: Delete bei nicht existierender Vorlage."""
    # Mock DB response - keine Vorlage
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = AsyncMock(return_value=None)
    mock_db.execute.return_value = mock_result

    # Delete should return False
    success = await template_engine.delete_template(TEST_TEMPLATE_UUID)

    assert success is False


# ========================= List Tests =========================


@pytest.mark.asyncio
async def test_list_templates_by_category(
    template_engine,
    mock_db,
    sample_template,
):
    """Test: Filtern nach Kategorie."""
    # Mock DB response
    mock_result = AsyncMock()
    mock_result.scalars = Mock(return_value=Mock(all=Mock(return_value=[sample_template])))
    mock_db.execute.return_value = mock_result

    # List templates
    templates = await template_engine.list_templates(category="document")

    # Assertions
    assert len(templates) == 1
    assert templates[0].category == "document"


@pytest.mark.asyncio
async def test_list_templates_active_only(
    template_engine,
    mock_db,
    sample_template,
):
    """Test: Nur aktive Vorlagen."""
    # Create inactive template
    inactive_template = NotificationTemplate(
        id=uuid4(),
        name="inactive",
        category="system",
        subject_template="Test",
        body_template="Test",
        is_active=False,
    )

    # Mock DB response - nur aktive Vorlagen
    mock_result = AsyncMock()
    mock_result.scalars = Mock(return_value=Mock(all=Mock(return_value=[sample_template])))
    mock_db.execute.return_value = mock_result

    # List templates (active_only=True by default)
    templates = await template_engine.list_templates(active_only=True)

    # Assertions
    assert len(templates) == 1
    assert templates[0].is_active is True


# ========================= Security Tests =========================


@pytest.mark.asyncio
async def test_sandboxed_environment_blocks_unsafe(
    template_engine,
    mock_db,
):
    """Test: Jinja2-Sandbox blockiert gefaehrliche Operationen."""
    # Create template with unsafe operation attempt
    unsafe_template = NotificationTemplate(
        id=TEST_TEMPLATE_UUID,
        name="unsafe",
        category="document",
        subject_template="Test",
        body_template="{{ ''.__class__.__bases__[0].__subclasses__() }}",  # Attempt to access internals
        variables={"required": [], "optional": []},
        is_active=True,
    )

    # Mock DB response
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = AsyncMock(return_value=unsafe_template)
    mock_db.execute.return_value = mock_result

    # Should raise SecurityError or similar
    with pytest.raises((Exception, TemplateSyntaxError)):
        await template_engine.render_notification(
            template_id=TEST_TEMPLATE_UUID,
            variables={},
        )


# ========================= Preset Tests =========================


def test_preset_templates_available():
    """Test: Preset-Templates haben erwartete Keys."""
    # Check that preset templates exist
    assert "APPROVAL_REQUESTED" in PRESET_TEMPLATES
    assert "DOCUMENT_PROCESSED" in PRESET_TEMPLATES
    assert "ESCALATION_ALERT" in PRESET_TEMPLATES
    assert "PAYMENT_REMINDER" in PRESET_TEMPLATES
    assert "SYSTEM_ALERT" in PRESET_TEMPLATES

    # Check structure of one preset
    approval_preset = PRESET_TEMPLATES["APPROVAL_REQUESTED"]
    assert "name" in approval_preset
    assert "category" in approval_preset
    assert "subject" in approval_preset
    assert "body" in approval_preset
    assert "variables" in approval_preset
    assert "channels" in approval_preset

    # Check variables structure
    assert "required" in approval_preset["variables"]
    assert "optional" in approval_preset["variables"]
    assert isinstance(approval_preset["variables"]["required"], list)
    assert isinstance(approval_preset["variables"]["optional"], list)


# ========================= Factory Tests =========================


@pytest.mark.asyncio
async def test_get_template_engine_factory():
    """Test: Factory-Funktion erstellt Engine."""
    mock_db = AsyncMock()
    engine = get_template_engine(mock_db)

    assert isinstance(engine, NotificationTemplateEngine)
    assert engine.db == mock_db


# ========================= Custom Filter Tests =========================


def test_currency_filter():
    """Test: Waehrungsformatierung."""
    engine = NotificationTemplateEngine(AsyncMock())

    # Test currency filter
    result = engine._currency_filter(1234.56)
    assert result == "1.234,56 EUR"

    result = engine._currency_filter(0.99)
    assert result == "0,99 EUR"


def test_date_filter():
    """Test: Datumsformatierung."""
    engine = NotificationTemplateEngine(AsyncMock())

    # Test date filter with ISO format
    result = engine._date_filter("2024-12-25T10:30:00")
    assert result == "25.12.2024"

    # Test with invalid date
    result = engine._date_filter("invalid")
    assert result == "invalid"
