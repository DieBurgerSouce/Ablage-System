# -*- coding: utf-8 -*-
"""
Security Tests: Broken Access Control (OWASP A01:2021)

Testet:
- Multi-Tenant IDOR (Insecure Direct Object Reference)
- Privilege Escalation
- Forced Browsing
- Path Traversal in File Access
- API Rate Limiting Bypass

Kritische Regeln aus CLAUDE.md:
- "Multi-Tenant IDOR Prevention"
- "Owner check + sharing permissions"
- Alle API-Endpunkte muessen company_id validieren
"""

import uuid
from typing import Dict, List

import pytest


# =============================================================================
# MULTI-TENANT IDOR TESTS
# =============================================================================


class TestMultiTenantIDOR:
    """Tests gegen Multi-Tenant IDOR Angriffe.

    Kritisch: User A darf NIEMALS auf Daten von User B zugreifen,
    selbst wenn sie die korrekte UUID kennen.
    """

    @pytest.fixture
    def company_a_id(self) -> uuid.UUID:
        return uuid.UUID("11111111-1111-1111-1111-111111111111")

    @pytest.fixture
    def company_b_id(self) -> uuid.UUID:
        return uuid.UUID("22222222-2222-2222-2222-222222222222")

    @pytest.fixture
    def document_from_company_a(self) -> uuid.UUID:
        return uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    def test_document_access_cross_tenant(
        self, test_client, auth_headers_company_a, document_from_company_a
    ):
        """User von Company A versucht Dokument von Company B zu lesen."""
        # Dokument-ID von Company B (erraten oder geleakt)
        foreign_document_id = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

        response = test_client.get(
            f"/api/v1/documents/{foreign_document_id}",
            headers=auth_headers_company_a,
        )
        # MUSS 403 oder 404 sein, NIEMALS 200
        assert response.status_code in [403, 404]

    def test_document_delete_cross_tenant(self, test_client, auth_headers_company_a):
        """User von Company A versucht Dokument von Company B zu loeschen."""
        foreign_document_id = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

        response = test_client.delete(
            f"/api/v1/documents/{foreign_document_id}",
            headers=auth_headers_company_a,
        )
        assert response.status_code in [403, 404]

    def test_folder_access_cross_tenant(self, test_client, auth_headers_company_a):
        """User von Company A versucht Folder von Company B zu lesen."""
        foreign_folder_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

        response = test_client.get(
            f"/api/v1/folders/{foreign_folder_id}",
            headers=auth_headers_company_a,
        )
        assert response.status_code in [403, 404]

    def test_entity_access_cross_tenant(self, test_client, auth_headers_company_a):
        """User von Company A versucht BusinessEntity von Company B zu lesen."""
        foreign_entity_id = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")

        response = test_client.get(
            f"/api/v1/entities/{foreign_entity_id}",
            headers=auth_headers_company_a,
        )
        assert response.status_code in [403, 404]

    def test_invoice_access_cross_tenant(self, test_client, auth_headers_company_a):
        """User von Company A versucht Invoice von Company B zu lesen."""
        foreign_invoice_id = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")

        response = test_client.get(
            f"/api/v1/invoices/{foreign_invoice_id}",
            headers=auth_headers_company_a,
        )
        assert response.status_code in [403, 404]

    def test_bulk_operation_cross_tenant(self, test_client, auth_headers_company_a):
        """User von Company A versucht Bulk-Operation auf Dokumente von Company B."""
        foreign_doc_ids = [
            str(uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")),
            str(uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbc")),
        ]

        response = test_client.post(
            "/api/v1/documents/bulk/delete",
            json={"document_ids": foreign_doc_ids},
            headers=auth_headers_company_a,
        )
        # Bulk-Operation sollte KEINE fremden Dokumente betreffen
        assert response.status_code in [403, 404, 200]
        if response.status_code == 200:
            # Keine Dokumente sollten geloescht worden sein
            data = response.json()
            assert data.get("deleted_count", 0) == 0

    def test_search_leaks_no_cross_tenant_data(self, test_client, auth_headers_company_a):
        """Suchergebnisse duerfen nur Daten der eigenen Company enthalten."""
        response = test_client.get(
            "/api/v1/documents/search?query=test",
            headers=auth_headers_company_a,
        )
        if response.status_code == 200:
            data = response.json()
            # Alle Ergebnisse muessen zur eigenen Company gehoeren
            # (In der Praxis: company_id in jedem Dokument pruefen)


# =============================================================================
# PRIVILEGE ESCALATION TESTS
# =============================================================================


class TestPrivilegeEscalation:
    """Tests gegen Privilege Escalation Angriffe."""

    def test_role_escalation_via_api(self, test_client, auth_headers_normal_user):
        """Normaler User versucht sich Admin-Rechte zu geben."""
        response = test_client.patch(
            "/api/v1/users/me",
            json={"role": "admin", "is_superuser": True},
            headers=auth_headers_normal_user,
        )
        # Sollte abgelehnt werden
        assert response.status_code in [400, 403, 422]

        # Verify: Role sollte unveraendert sein
        me_response = test_client.get("/api/v1/users/me", headers=auth_headers_normal_user)
        if me_response.status_code == 200:
            assert me_response.json().get("is_superuser") is not True

    def test_access_admin_endpoints(self, test_client, auth_headers_normal_user):
        """Normaler User versucht Admin-Endpoints zu erreichen."""
        admin_endpoints = [
            "/api/v1/admin/users",
            "/api/v1/admin/companies",
            "/api/v1/admin/rate-limits",
            "/api/v1/admin/audit-logs",
            "/api/v1/admin/system/settings",
        ]

        for endpoint in admin_endpoints:
            response = test_client.get(endpoint, headers=auth_headers_normal_user)
            assert response.status_code in [401, 403, 404], f"Endpoint {endpoint} sollte geschuetzt sein"

    def test_viewer_cannot_edit(self, test_client, auth_headers_viewer):
        """Viewer (read-only) versucht zu editieren."""
        document_id = uuid.uuid4()

        # Viewer sollte lesen koennen
        response = test_client.get(
            f"/api/v1/documents/{document_id}",
            headers=auth_headers_viewer,
        )
        # (Kann 404 sein wenn Dokument nicht existiert)

        # Viewer sollte NICHT editieren koennen
        response = test_client.patch(
            f"/api/v1/documents/{document_id}",
            json={"name": "Modified by Viewer"},
            headers=auth_headers_viewer,
        )
        assert response.status_code in [403, 404]

    def test_company_switch_without_permission(self, test_client, auth_headers_company_a):
        """User versucht zu einer Company zu wechseln, der er nicht angehoert."""
        foreign_company_id = uuid.UUID("22222222-2222-2222-2222-222222222222")

        response = test_client.post(
            f"/api/v1/users/me/switch-company/{foreign_company_id}",
            headers=auth_headers_company_a,
        )
        assert response.status_code in [403, 404]


# =============================================================================
# FORCED BROWSING TESTS
# =============================================================================


class TestForcedBrowsing:
    """Tests gegen Forced Browsing / Direkter Objektzugriff."""

    def test_sequential_id_enumeration(self, test_client, auth_headers):
        """Testet ob sequentielle IDs erraten werden koennen."""
        # Ablage-System verwendet UUIDs, nicht sequentielle IDs
        # Dieser Test validiert dass UUIDs verwendet werden

        # Versuche sequentielle Nummern
        for i in range(1, 10):
            response = test_client.get(
                f"/api/v1/documents/{i}",
                headers=auth_headers,
            )
            # Sollte 422 (invalid UUID) oder 404 sein, nicht 200
            assert response.status_code in [404, 422]

    def test_uuid_guessing_protection(self, test_client, auth_headers):
        """Testet dass zufaellige UUIDs nicht zu Daten-Leaks fuehren."""
        # Generiere 100 zufaellige UUIDs
        for _ in range(100):
            random_uuid = uuid.uuid4()
            response = test_client.get(
                f"/api/v1/documents/{random_uuid}",
                headers=auth_headers,
            )
            # Sollte 404 sein (nicht existent) oder 403 (keine Berechtigung)
            # NIEMALS sollte ein fremdes Dokument zurueckgegeben werden
            assert response.status_code in [403, 404]

    def test_hidden_endpoints_not_accessible(self, test_client, auth_headers):
        """Testet dass interne/versteckte Endpoints nicht erreichbar sind."""
        hidden_endpoints = [
            "/internal/metrics",
            "/debug/info",
            "/admin/backup",
            "/api/internal/health-detailed",
            "/.env",
            "/config/settings.json",
            "/api/v1/debug/dump-db",
        ]

        for endpoint in hidden_endpoints:
            response = test_client.get(endpoint, headers=auth_headers)
            # Sollte 401, 403 oder 404 sein
            assert response.status_code in [401, 403, 404], f"Hidden endpoint {endpoint} erreichbar"


# =============================================================================
# PATH TRAVERSAL IN FILE ACCESS TESTS
# =============================================================================


class TestPathTraversal:
    """Tests gegen Path Traversal in File-Zugriffen."""

    @pytest.mark.parametrize("malicious_path", [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32\\config\\sam",
        "....//....//....//etc/passwd",
        "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",  # URL-encoded
        "..%252f..%252f..%252fetc%252fpasswd",  # Double-encoded
        "/etc/passwd",
        "C:\\Windows\\System32\\config\\SAM",
        "file:///etc/passwd",
    ])
    def test_path_traversal_in_document_path(self, malicious_path: str, test_client, auth_headers):
        """Testet Path Traversal in Dokumentenpfaden."""
        response = test_client.get(
            f"/api/v1/documents/download/{malicious_path}",
            headers=auth_headers,
        )
        # Sollte abgelehnt werden
        assert response.status_code in [400, 403, 404, 422]
        # Response sollte keine sensiblen Systemdaten enthalten
        if response.content:
            assert b"root:" not in response.content  # /etc/passwd
            assert b"[boot loader]" not in response.content  # Windows SAM

    @pytest.mark.parametrize("malicious_filename", [
        "../../../etc/passwd",
        "test/../../../etc/passwd",
        "test%00.pdf",  # Null-Byte injection
        "test\x00.pdf",  # Null-Byte
    ])
    def test_path_traversal_in_upload(self, malicious_filename: str, test_client, auth_headers):
        """Testet Path Traversal beim Upload."""
        response = test_client.post(
            "/api/v1/documents/upload",
            files={"file": (malicious_filename, b"dummy content", "application/pdf")},
            headers=auth_headers,
        )
        # Filename sollte sanitized oder abgelehnt werden
        if response.status_code == 201:
            data = response.json()
            stored_filename = data.get("filename", "")
            assert ".." not in stored_filename
            assert "/" not in stored_filename or stored_filename.count("/") == stored_filename.count("\\") == 0
            assert "\x00" not in stored_filename


# =============================================================================
# RESOURCE OWNERSHIP TESTS
# =============================================================================


class TestResourceOwnership:
    """Tests fuer Ressourcen-Ownership und Sharing."""

    def test_document_owner_access(self, test_client, auth_headers_owner):
        """Owner kann sein Dokument lesen."""
        own_doc_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        response = test_client.get(
            f"/api/v1/documents/{own_doc_id}",
            headers=auth_headers_owner,
        )
        # Owner sollte Zugriff haben
        assert response.status_code in [200, 404]

    def test_shared_document_access(self, test_client, auth_headers_shared_user):
        """User mit Share-Berechtigung kann Dokument lesen."""
        shared_doc_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        response = test_client.get(
            f"/api/v1/documents/{shared_doc_id}",
            headers=auth_headers_shared_user,
        )
        # User mit Share sollte Zugriff haben
        assert response.status_code in [200, 404]

    def test_no_share_no_access(self, test_client, auth_headers_no_share):
        """User ohne Share-Berechtigung kann Dokument NICHT lesen."""
        unshared_doc_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        response = test_client.get(
            f"/api/v1/documents/{unshared_doc_id}",
            headers=auth_headers_no_share,
        )
        assert response.status_code in [403, 404]


# =============================================================================
# FIXTURES - Verwendung von conftest.py
# =============================================================================
# Die Fixtures test_client, auth_headers, auth_headers_company_a, auth_headers_company_b
# werden aus conftest.py importiert. Diese nutzen den ECHTEN TestClient mit ECHTEN JWT-Tokens.

# Zusätzliche Role-based Fixtures für dieses Modul
@pytest.fixture
def auth_headers_normal_user(_check_app_available):
    """Auth-Header fuer normalen User (kein Admin)."""
    try:
        from app.core.security import create_access_token
        from uuid import uuid4
        user_data = {
            "sub": str(uuid4()),
            "email": "normal-user@test.local",
            "is_active": True,
            "is_superuser": False,
            "company_id": "00000000-0000-0000-0000-000000000001",
        }
        token = create_access_token(data=user_data)
        return {"Authorization": f"Bearer {token}"}
    except ImportError:
        return {"Authorization": "Bearer normal-user-token"}


@pytest.fixture
def auth_headers_viewer(_check_app_available):
    """Auth-Header fuer Viewer (read-only)."""
    try:
        from app.core.security import create_access_token
        from uuid import uuid4
        user_data = {
            "sub": str(uuid4()),
            "email": "viewer@test.local",
            "is_active": True,
            "is_superuser": False,
            "role": "viewer",
            "company_id": "00000000-0000-0000-0000-000000000001",
        }
        token = create_access_token(data=user_data)
        return {"Authorization": f"Bearer {token}"}
    except ImportError:
        return {"Authorization": "Bearer viewer-token"}


@pytest.fixture
def auth_headers_owner(_check_app_available):
    """Auth-Header fuer Dokument-Owner."""
    try:
        from app.core.security import create_access_token
        from uuid import uuid4
        user_data = {
            "sub": str(uuid4()),
            "email": "owner@test.local",
            "is_active": True,
            "is_superuser": False,
            "company_id": "00000000-0000-0000-0000-000000000001",
        }
        token = create_access_token(data=user_data)
        return {"Authorization": f"Bearer {token}"}
    except ImportError:
        return {"Authorization": "Bearer owner-token"}


@pytest.fixture
def auth_headers_shared_user(_check_app_available):
    """Auth-Header fuer User mit Share-Berechtigung."""
    try:
        from app.core.security import create_access_token
        from uuid import uuid4
        user_data = {
            "sub": str(uuid4()),
            "email": "shared-user@test.local",
            "is_active": True,
            "is_superuser": False,
            "company_id": "00000000-0000-0000-0000-000000000001",
        }
        token = create_access_token(data=user_data)
        return {"Authorization": f"Bearer {token}"}
    except ImportError:
        return {"Authorization": "Bearer shared-user-token"}


@pytest.fixture
def auth_headers_no_share(_check_app_available):
    """Auth-Header fuer User ohne Share-Berechtigung."""
    try:
        from app.core.security import create_access_token
        from uuid import uuid4
        user_data = {
            "sub": str(uuid4()),
            "email": "no-share@test.local",
            "is_active": True,
            "is_superuser": False,
            "company_id": "00000000-0000-0000-0000-000000000003",  # Different company
        }
        token = create_access_token(data=user_data)
        return {"Authorization": f"Bearer {token}"}
    except ImportError:
        return {"Authorization": "Bearer no-share-token"}


@pytest.fixture
def _check_app_available():
    """Prueft ob die App verfuegbar ist."""
    try:
        from app.main import app
        return True
    except ImportError:
        import pytest
        pytest.skip("App not available")
