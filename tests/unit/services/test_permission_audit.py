# -*- coding: utf-8 -*-
"""
Tests fuer PermissionAuditService.

Testet:
- Protokollierung von Rollen- und Permission-Aenderungen
- Tenant-Isolation (company_id Filter)
- CSV- und JSON-Export
- Compliance-Zusammenfassung
- DSGVO Art. 30 Konformitaet
- Sicherheit: Cross-Tenant-Zugriff wird verhindert
"""

import csv
import io
import json
import pytest
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch, PropertyMock
from uuid import UUID, uuid4

from app.services.permission_audit_service import (
    PermissionAuditService,
    PermissionChangeType,
    PermissionChangeRecord,
    PermissionAuditExport,
)


@pytest.fixture
def mock_db() -> AsyncMock:
    """Erstellt eine Mock-Datenbank-Session."""
    return AsyncMock()


@pytest.fixture
def mock_audit_logger() -> Mock:
    """Erstellt einen Mock fuer SecurityAuditLogger."""
    logger = Mock()
    logger.log_event = AsyncMock(return_value="audit-id-test-12345")
    return logger


@pytest.fixture
def service(mock_db: AsyncMock, mock_audit_logger: Mock) -> PermissionAuditService:
    """Erstellt eine PermissionAuditService-Instanz."""
    with patch("app.services.permission_audit_service.SecurityAuditLogger") as mock_class:
        mock_class.return_value = mock_audit_logger
        svc = PermissionAuditService(mock_db)
    return svc


class TestLogRoleAssigned:
    """Tests fuer log_role_assigned()."""

    @pytest.mark.asyncio
    async def test_protokolliert_rollenzuweisung(
        self, service: PermissionAuditService, mock_audit_logger: Mock
    ):
        """Rollenzuweisung wird korrekt protokolliert."""
        result = await service.log_role_assigned(
            target_user_id="user-test-001",
            role_name="admin",
            company_id="company-test-001",
            changed_by_user_id="admin-test-001",
            ip_address="192.0.2.1",
            reason="Befoerderung",
        )

        assert result == "audit-id-test-12345"
        mock_audit_logger.log_event.assert_called_once()
        call_kwargs = mock_audit_logger.log_event.call_args
        assert call_kwargs.kwargs["resource_type"] == "permission"

    @pytest.mark.asyncio
    async def test_ohne_optionale_felder(
        self, service: PermissionAuditService, mock_audit_logger: Mock
    ):
        """Protokollierung funktioniert auch ohne optionale Felder."""
        result = await service.log_role_assigned(
            target_user_id="user-test-001",
            role_name="viewer",
            company_id="company-test-001",
        )

        assert result is not None


class TestLogRoleRemoved:
    """Tests fuer log_role_removed()."""

    @pytest.mark.asyncio
    async def test_protokolliert_rollenentfernung(
        self, service: PermissionAuditService, mock_audit_logger: Mock
    ):
        """Rollenentfernung wird protokolliert (role_removed hat keine 'revoked' -> info)."""
        await service.log_role_removed(
            target_user_id="user-test-001",
            role_name="admin",
            company_id="company-test-001",
        )

        call_kwargs = mock_audit_logger.log_event.call_args.kwargs
        # role_removed value does not contain "revoked", so severity is "info"
        assert call_kwargs["severity"] == "info"


class TestLogPermissionGranted:
    """Tests fuer log_permission_granted() und log_permission_revoked()."""

    @pytest.mark.asyncio
    async def test_permission_granted_details(
        self, service: PermissionAuditService, mock_audit_logger: Mock
    ):
        """Permission-Erteilung enthaelt korrekte Details."""
        await service.log_permission_granted(
            target_user_id="user-test-001",
            permission_name="documents:delete",
            company_id="company-test-001",
        )

        call_kwargs = mock_audit_logger.log_event.call_args.kwargs
        details = call_kwargs["details"]
        assert details["permission"] == "documents:delete"
        assert details["change_type"] == "permission_granted"

    @pytest.mark.asyncio
    async def test_permission_revoked_ist_warning(
        self, service: PermissionAuditService, mock_audit_logger: Mock
    ):
        """Entzug einer Permission hat Severity 'warning'."""
        await service.log_permission_revoked(
            target_user_id="user-test-001",
            permission_name="documents:delete",
            company_id="company-test-001",
        )

        call_kwargs = mock_audit_logger.log_event.call_args.kwargs
        assert call_kwargs["severity"] == "warning"


class TestLogGroupMembership:
    """Tests fuer log_group_membership_change()."""

    @pytest.mark.asyncio
    async def test_gruppe_hinzugefuegt(
        self, service: PermissionAuditService, mock_audit_logger: Mock
    ):
        """Gruppenmitgliedschaft wird als GROUP_ADDED protokolliert."""
        await service.log_group_membership_change(
            target_user_id="user-test-001",
            group_name="buchhaltung",
            added=True,
            company_id="company-test-001",
        )

        call_kwargs = mock_audit_logger.log_event.call_args.kwargs
        details = call_kwargs["details"]
        assert details["change_type"] == "group_added"
        assert details["group"] == "buchhaltung"

    @pytest.mark.asyncio
    async def test_gruppe_entfernt(
        self, service: PermissionAuditService, mock_audit_logger: Mock
    ):
        """Gruppenentfernung wird als GROUP_REMOVED protokolliert."""
        await service.log_group_membership_change(
            target_user_id="user-test-001",
            group_name="buchhaltung",
            added=False,
            company_id="company-test-001",
        )

        call_kwargs = mock_audit_logger.log_event.call_args.kwargs
        details = call_kwargs["details"]
        assert details["change_type"] == "group_removed"


class TestLogDelegation:
    """Tests fuer Delegation-Logging (Phase 3)."""

    @pytest.mark.asyncio
    async def test_delegation_erstellt(
        self, service: PermissionAuditService, mock_audit_logger: Mock
    ):
        """Delegation-Erstellung wird mit Metadaten protokolliert."""
        valid_until = datetime.now(timezone.utc) + timedelta(days=7)

        await service.log_delegation_created(
            delegator_id="admin-test-001",
            delegate_id="user-test-001",
            permissions=["documents:read", "documents:write"],
            valid_until=valid_until,
            company_id="company-test-001",
        )

        call_kwargs = mock_audit_logger.log_event.call_args.kwargs
        details = call_kwargs["details"]
        assert details["change_type"] == "delegation_created"
        assert "delegator_id" in details.get("metadata", {})
        assert details["metadata"]["permissions_count"] == 2


class TestGetUserPermissionHistory:
    """Tests fuer get_user_permission_history() mit Tenant-Isolation."""

    @pytest.mark.asyncio
    async def test_tenant_isolation_filtert_fremde_eintraege(
        self, service: PermissionAuditService, mock_db: AsyncMock
    ):
        """Eintraege anderer Companies werden herausgefiltert."""
        # Simuliere AuditLog-Eintraege mit verschiedenen company_ids
        entry_own = Mock()
        entry_own.id = uuid4()
        entry_own.created_at = datetime.now(timezone.utc)
        entry_own.user_id = uuid4()
        entry_own.ip_address = "192.0.2.1"
        entry_own.audit_metadata = {
            "company_id": "company-test-001",
            "change_type": "role_assigned",
        }

        entry_other = Mock()
        entry_other.id = uuid4()
        entry_other.created_at = datetime.now(timezone.utc)
        entry_other.user_id = uuid4()
        entry_other.ip_address = "192.0.2.2"
        entry_other.audit_metadata = {
            "company_id": "andere-company",
            "change_type": "role_assigned",
        }

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [entry_own, entry_other]
        mock_db.execute = AsyncMock(return_value=mock_result)

        records = await service.get_user_permission_history(
            user_id=str(entry_own.user_id),
            company_id="company-test-001",
        )

        assert len(records) == 1
        assert records[0].company_id == "company-test-001"

    @pytest.mark.asyncio
    async def test_leere_historie(
        self, service: PermissionAuditService, mock_db: AsyncMock
    ):
        """Leere Historie gibt leere Liste zurueck."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        records = await service.get_user_permission_history(
            user_id=str(uuid4()),
            company_id="company-test-001",
        )

        assert records == []


class TestExportCSV:
    """Tests fuer export_csv() - DSGVO Art. 30 konform."""

    @pytest.mark.asyncio
    async def test_csv_hat_deutsche_header(
        self, service: PermissionAuditService, mock_db: AsyncMock
    ):
        """CSV-Export hat deutschsprachige Header."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        csv_content = await service.export_csv(company_id="company-test-001")

        assert "Zeitstempel" in csv_content
        assert "Änderungstyp" in csv_content or "Aenderungstyp" in csv_content
        assert "Berechtigung" in csv_content

    @pytest.mark.asyncio
    async def test_csv_nutzt_semikolon_delimiter(
        self, service: PermissionAuditService, mock_db: AsyncMock
    ):
        """CSV nutzt Semikolon als Trennzeichen fuer deutsches Excel."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        csv_content = await service.export_csv(company_id="company-test-001")

        assert ";" in csv_content


class TestComplianceSummary:
    """Tests fuer get_compliance_summary()."""

    @pytest.mark.asyncio
    async def test_zusammenfassung_enthaelt_pflichtfelder(
        self, service: PermissionAuditService, mock_db: AsyncMock
    ):
        """Compliance-Zusammenfassung enthaelt alle Pflichtfelder."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        summary = await service.get_compliance_summary(
            company_id="company-test-001",
            period_days=30,
        )

        assert "period_start" in summary
        assert "period_end" in summary
        assert "total_changes" in summary
        assert "changes_by_type" in summary
        assert "users_affected" in summary
        assert "admins_involved" in summary
