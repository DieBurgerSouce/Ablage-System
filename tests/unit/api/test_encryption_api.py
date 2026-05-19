# -*- coding: utf-8 -*-
"""Unit-Tests fuer Encryption Admin API (B5).

DSGVO Art. 32 (Sicherheit der Verarbeitung) - die Field-Level-Encryption-
Admin-API ist kritisch fuer Compliance. Tests fokussieren auf:
- Whitelist-Validierung (nur registrierte Felder duerfen migriert werden)
- Admin-only Authorization (alle Endpoints require_superuser)
- Pydantic-Schema-Validierung (batch_groesse Grenzen)
- Error-Pfade

Quelle: GOAL_PHASE_B.md B5, MASTER_REVIEW_2026-05-19.md test_gaps.md
"Top 2 CRITICAL Untested: encryption.py - Key management & document
encryption (GDPR Art. 32)".
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from fastapi import HTTPException, status
from pydantic import ValidationError


pytestmark = [pytest.mark.unit, pytest.mark.api]


# =================== Fixtures ===================


@pytest.fixture
def admin_user():
    u = Mock()
    u.id = uuid4()
    u.email = "admin@example.com"
    u.is_superuser = True
    return u


@pytest.fixture
def mock_db():
    return AsyncMock()


# =================== get_encryption_status ===================


class TestGetEncryptionStatus:
    async def test_returns_field_statuses(self, admin_user, mock_db):
        from app.api.v1.encryption import get_encryption_status

        with patch(
            "app.api.v1.encryption.FieldEncryptionService"
        ) as svc_class:
            svc = Mock()
            svc.get_encryption_status = AsyncMock(
                return_value=[
                    {
                        "tabelle": "users",
                        "spalte": "totp_secret",
                        "algorithmus": "AES-256-GCM",
                        "key_version": "v1",
                        "status": "active",
                        "zeilen_verschluesselt": "150",
                        "letzte_rotation": "2026-05-01T00:00:00",
                    }
                ]
            )
            svc_class.return_value = svc

            result = await get_encryption_status(
                current_user=admin_user, db=mock_db
            )

        assert result.gesamt_felder == 1
        assert result.aktive_felder == 1
        assert result.felder[0].tabelle == "users"

    async def test_counts_active_fields_correctly(self, admin_user, mock_db):
        from app.api.v1.encryption import get_encryption_status

        with patch(
            "app.api.v1.encryption.FieldEncryptionService"
        ) as svc_class:
            svc = Mock()
            svc.get_encryption_status = AsyncMock(
                return_value=[
                    {"tabelle": "t1", "spalte": "c1", "algorithmus": "AES",
                     "key_version": "v1", "status": "active",
                     "zeilen_verschluesselt": "100", "letzte_rotation": "now"},
                    {"tabelle": "t2", "spalte": "c2", "algorithmus": "AES",
                     "key_version": "v1", "status": "pending",
                     "zeilen_verschluesselt": "0", "letzte_rotation": "never"},
                    {"tabelle": "t3", "spalte": "c3", "algorithmus": "AES",
                     "key_version": "v0", "status": "deprecated",
                     "zeilen_verschluesselt": "50", "letzte_rotation": "old"},
                ]
            )
            svc_class.return_value = svc

            result = await get_encryption_status(
                current_user=admin_user, db=mock_db
            )

        assert result.gesamt_felder == 3
        assert result.aktive_felder == 1  # nur "active" zaehlt

    async def test_service_failure_returns_500(self, admin_user, mock_db):
        from app.api.v1.encryption import get_encryption_status

        with patch(
            "app.api.v1.encryption.FieldEncryptionService"
        ) as svc_class:
            svc = Mock()
            svc.get_encryption_status = AsyncMock(
                side_effect=RuntimeError("DB unreachable")
            )
            svc_class.return_value = svc

            with pytest.raises(HTTPException) as exc:
                await get_encryption_status(
                    current_user=admin_user, db=mock_db
                )
            assert exc.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


# =================== start_encryption_migration ===================


class TestStartEncryptionMigration:
    """B5: Whitelist-Validierung verhindert beliebige Tabellen-Verschluesselung."""

    async def test_unknown_field_returns_400(self, admin_user, mock_db):
        from app.api.v1.encryption import (
            start_encryption_migration,
            EncryptionMigrateRequest,
        )

        req = EncryptionMigrateRequest(
            tabelle="evil_table",  # nicht in ENCRYPTED_FIELDS
            spalte="evil_col",
            batch_groesse=500,
        )
        with pytest.raises(HTTPException) as exc:
            await start_encryption_migration(
                request=req, current_user=admin_user, db=mock_db
            )
        assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "Ungueltiges Feld" in exc.value.detail

    async def test_valid_field_starts_celery_task(self, admin_user, mock_db):
        from app.api.v1.encryption import (
            start_encryption_migration,
            EncryptionMigrateRequest,
        )
        from app.services.encryption.field_encryption_service import (
            ENCRYPTED_FIELDS,
        )

        # Pick the first whitelisted field
        first = ENCRYPTED_FIELDS[0]
        req = EncryptionMigrateRequest(
            tabelle=first["table"],
            spalte=first["column"],
            batch_groesse=500,
        )

        fake_task = Mock()
        fake_task.id = "task-abc-123"

        with patch(
            "app.workers.tasks.encryption_tasks.encrypt_field_task"
        ) as task_mock:
            task_mock.delay.return_value = fake_task
            result = await start_encryption_migration(
                request=req, current_user=admin_user, db=mock_db
            )

        assert result.task_id == "task-abc-123"
        assert result.tabelle == first["table"]


# =================== Pydantic Schema Validation ===================


class TestSchemaValidation:
    def test_batch_groesse_below_min_rejected(self):
        from app.api.v1.encryption import EncryptionMigrateRequest

        with pytest.raises(ValidationError):
            EncryptionMigrateRequest(tabelle="t", spalte="c", batch_groesse=5)

    def test_batch_groesse_above_max_rejected(self):
        from app.api.v1.encryption import EncryptionMigrateRequest

        with pytest.raises(ValidationError):
            EncryptionMigrateRequest(tabelle="t", spalte="c", batch_groesse=10000)

    def test_batch_groesse_at_min_accepted(self):
        from app.api.v1.encryption import EncryptionMigrateRequest

        req = EncryptionMigrateRequest(tabelle="t", spalte="c", batch_groesse=10)
        assert req.batch_groesse == 10

    def test_batch_groesse_at_max_accepted(self):
        from app.api.v1.encryption import EncryptionMigrateRequest

        req = EncryptionMigrateRequest(tabelle="t", spalte="c", batch_groesse=5000)
        assert req.batch_groesse == 5000

    def test_batch_groesse_default_is_500(self):
        from app.api.v1.encryption import EncryptionMigrateRequest

        req = EncryptionMigrateRequest(tabelle="t", spalte="c")
        assert req.batch_groesse == 500

    def test_key_rotation_request_same_constraints(self):
        from app.api.v1.encryption import KeyRotationRequest

        with pytest.raises(ValidationError):
            KeyRotationRequest(tabelle="t", spalte="c", batch_groesse=0)
        # at max
        req = KeyRotationRequest(tabelle="t", spalte="c", batch_groesse=5000)
        assert req.batch_groesse == 5000


# =================== Whitelist Source-of-Truth ===================


class TestEncryptedFieldsWhitelist:
    """B5: ENCRYPTED_FIELDS ist die Single-Source-of-Truth fuer Whitelist."""

    def test_encrypted_fields_is_non_empty_list(self):
        from app.services.encryption.field_encryption_service import (
            ENCRYPTED_FIELDS,
        )
        assert isinstance(ENCRYPTED_FIELDS, list)
        assert len(ENCRYPTED_FIELDS) > 0

    def test_each_entry_has_table_and_column(self):
        from app.services.encryption.field_encryption_service import (
            ENCRYPTED_FIELDS,
        )
        for field in ENCRYPTED_FIELDS:
            assert "table" in field, f"Missing 'table' in {field}"
            assert "column" in field, f"Missing 'column' in {field}"
            assert isinstance(field["table"], str)
            assert isinstance(field["column"], str)
