# -*- coding: utf-8 -*-
"""Unit-Tests fuer GDPR-Deletion-Service (B5).

GDPR Art. 17 (Recht auf Loeschung) ist DSGVO-Pflicht - Tests verifizieren:
- Soft-Delete-Pfad (Anonymisierung mit deleted_at + Tombstone)
- Hard-Delete-Pfad (physische DB-Loeschung + MinIO-Datei)
- Stats-Tracking (documents/minio_files/api_keys/audit_logs counts)
- User-not-found -> UserNotFoundError
- MinIO-Failure-Tolerance (DB-Loeschung trotzdem fortsetzen)

Integration-Test fuer end-to-end Pipeline (request -> 30d grace -> delete ->
S3-purge -> audit -> search-leer) bleibt out-of-scope (braucht Docker-Stack).
Stattdessen: Service-Layer Contract-Tests.

Quelle: GOAL_PHASE_B.md B5, MASTER_REVIEW_2026-05-19.md test_gaps.md
"Critical Untested: gdpr_service.py Art. 17 cascade".
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4
from datetime import datetime, timezone


pytestmark = [pytest.mark.unit, pytest.mark.gdpr]


# =================== Fixtures ===================


@pytest.fixture
def mock_db():
    db = AsyncMock()
    return db


@pytest.fixture
def user():
    u = Mock()
    u.id = uuid4()
    u.email = "deleteme@example.com"
    u.full_name = "Tester"
    u.hashed_password = "$2b$12$realhash"
    return u


@pytest.fixture
def service():
    from app.services.gdpr_service import GDPRService
    return GDPRService()


# =================== execute_deletion: Service-Found vs Not-Found ===================


class TestUserResolution:
    async def test_unknown_user_raises_UserNotFoundError(self, service, mock_db):
        from app.services.gdpr_service import UserNotFoundError

        mock_db.get = AsyncMock(return_value=None)
        with pytest.raises(UserNotFoundError):
            await service.execute_deletion(db=mock_db, user_id=uuid4())

    async def test_known_user_proceeds(self, service, mock_db, user):
        mock_db.get = AsyncMock(return_value=user)
        # Mock the documents query
        docs_result = Mock()
        docs_result.scalars.return_value.all.return_value = []
        api_keys_result = Mock()
        api_keys_result.scalars.return_value.all.return_value = []
        audit_logs_result = Mock()
        audit_logs_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(
            side_effect=[docs_result, api_keys_result, audit_logs_result]
        )
        mock_db.commit = AsyncMock()

        stats = await service.execute_deletion(
            db=mock_db, user_id=user.id, hard_delete=False
        )
        assert stats["documents"] == 0
        assert "api_keys" in stats


# =================== Soft-Delete Path ===================


class TestSoftDelete:
    """Soft-Delete = Anonymisierung mit Tombstone-Werten."""

    async def test_soft_delete_sets_deleted_at_on_documents(
        self, service, mock_db, user
    ):
        doc1 = Mock()
        doc1.id = uuid4()
        doc1.file_path = "/tmp/doc1.pdf"
        doc1.deleted_at = None
        doc1.extracted_text = "Original Inhalt"
        doc1.document_metadata = {"orig": "data"}
        doc1.filename = "rechnung_123.pdf"
        doc1.original_filename = "Rechnung 123.pdf"

        mock_db.get = AsyncMock(return_value=user)
        docs_result = Mock()
        docs_result.scalars.return_value.all.return_value = [doc1]
        empty_result = Mock()
        empty_result.scalars.return_value.all.return_value = []
        api_result = Mock()
        api_result.rowcount = 0
        mock_db.execute = AsyncMock(
            side_effect=[docs_result, api_result, empty_result]
        )
        mock_db.commit = AsyncMock()

        stats = await service.execute_deletion(
            db=mock_db, user_id=user.id, hard_delete=False
        )

        # Verify Anonymisierung
        assert doc1.deleted_at is not None
        assert doc1.extracted_text == "[GELÖSCHT - GDPR Art. 17]"
        assert doc1.document_metadata == {}
        assert doc1.original_filename == "[GELÖSCHT]"
        assert stats["documents"] == 1


# =================== Hard-Delete Path ===================


class TestHardDelete:
    """Hard-Delete = physisches db.delete + MinIO file removal."""

    async def test_hard_delete_calls_db_delete_on_documents(
        self, service, mock_db, user
    ):
        doc1 = Mock()
        doc1.id = uuid4()
        doc1.file_path = "/tmp/doc1.pdf"

        mock_db.get = AsyncMock(return_value=user)
        docs_result = Mock()
        docs_result.scalars.return_value.all.return_value = [doc1]
        empty_result = Mock()
        empty_result.scalars.return_value.all.return_value = []
        api_result = Mock()
        api_result.rowcount = 0
        mock_db.execute = AsyncMock(
            side_effect=[docs_result, api_result, empty_result]
        )
        mock_db.delete = AsyncMock()
        mock_db.commit = AsyncMock()

        # Patch STORAGE_AVAILABLE to False - skip MinIO
        with patch("app.services.gdpr_service.STORAGE_AVAILABLE", False):
            await service.execute_deletion(
                db=mock_db, user_id=user.id, hard_delete=True
            )

        # Hard-Delete ruft db.delete() fuer Document UND User auf
        deleted_args = [c.args[0] for c in mock_db.delete.await_args_list]
        assert doc1 in deleted_args

    async def test_minio_failure_does_not_stop_db_deletion(
        self, service, mock_db, user
    ):
        """B5: Selbst wenn MinIO-Delete fehlschlaegt, MUSS DB-Delete weiterlaufen."""
        doc1 = Mock()
        doc1.id = uuid4()
        doc1.file_path = "/tmp/doc1.pdf"

        mock_db.get = AsyncMock(return_value=user)
        docs_result = Mock()
        docs_result.scalars.return_value.all.return_value = [doc1]
        empty_result = Mock()
        empty_result.scalars.return_value.all.return_value = []
        api_result = Mock()
        api_result.rowcount = 0
        mock_db.execute = AsyncMock(
            side_effect=[docs_result, api_result, empty_result]
        )
        mock_db.delete = AsyncMock()
        mock_db.commit = AsyncMock()

        fake_storage = Mock()
        fake_storage.delete_document = AsyncMock(
            side_effect=RuntimeError("MinIO unreachable")
        )

        with patch("app.services.gdpr_service.STORAGE_AVAILABLE", True), patch(
            "app.services.gdpr_service.get_storage_service",
            return_value=fake_storage,
        ):
            await service.execute_deletion(
                db=mock_db, user_id=user.id, hard_delete=True
            )

        # DB-Delete MUSS trotzdem aufgerufen worden sein
        # Hard-Delete ruft db.delete() fuer Document UND User auf
        deleted_args = [c.args[0] for c in mock_db.delete.await_args_list]
        assert doc1 in deleted_args


# =================== Stats-Contract ===================


class TestStatsContract:
    """B5: execute_deletion gibt Dict mit allen 4 Stats-Keys zurueck."""

    async def test_stats_contains_all_required_keys(
        self, service, mock_db, user
    ):
        mock_db.get = AsyncMock(return_value=user)
        empty = Mock()
        empty.scalars.return_value.all.return_value = []
        api_result = Mock()
        api_result.rowcount = 0  # DELETE statement
        mock_db.execute = AsyncMock(side_effect=[empty, api_result, empty])
        mock_db.commit = AsyncMock()

        stats = await service.execute_deletion(
            db=mock_db, user_id=user.id, hard_delete=False
        )
        # Documented stats keys
        for key in ("documents", "minio_files", "api_keys", "audit_logs"):
            assert key in stats, f"Stats fehlt Key: {key}"
            assert isinstance(stats[key], int)


# =================== Integration-Test Placeholder ===================


@pytest.mark.integration
@pytest.mark.skip(reason="Full GDPR Art. 17 E2E requires docker-compose stack (DB + MinIO + Celery + audit-trail)")
class TestGDPRDeletionE2E:
    """End-to-End-Test fuer GDPR Art. 17 Pipeline.

    Out-of-Scope fuer B5-Unit-Phase. Wird in Phase C aktiviert wenn Docker-
    Testumgebung verfuegbar ist. Workflow:
    request -> 30d grace period -> cascade-delete -> S3-purge -> audit-trail
    geschrieben -> search liefert 0 Dokumente fuer User
    """

    async def test_full_deletion_workflow(self):
        # 1. POST /gdpr/deletion-request
        # 2. Warte 30 Tage (Mock: shift time)
        # 3. Worker triggert execute_deletion(hard_delete=True)
        # 4. Verify: Document-Rows entfernt, MinIO-Files weg
        # 5. Verify: AuditLog enthaelt GDPR_DELETION-Eintrag
        # 6. Verify: GET /search?q=<user-data> liefert 0
        raise NotImplementedError("Implement in Phase C with docker testbed")
