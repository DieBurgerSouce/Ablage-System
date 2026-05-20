# -*- coding: utf-8 -*-
"""
Unit-Tests für Security API Endpoints.

Testet:
- Security Audit Endpoint
- Security Score Endpoint
- Critical Findings Endpoint
- Security Checklist Endpoint
- Security Recommendations Endpoint
- Superuser-Authentifizierung
- Deutsche Response-Texte

Feinpoliert und durchdacht - Umfassende Security-API-Tests.
"""

import pytest
from datetime import datetime
from typing import Dict, Any, List
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4
from pathlib import Path
import sys

from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

# Import actual enum for proper comparison
from app.services.security_audit_service import AuditSeverity, AuditCategory


# ========================= Mock Classes =========================


class MockAuditSeverity:
    """Mock für AuditSeverity Enum."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

    @property
    def value(self):
        return self


class MockAuditCategory:
    """Mock für AuditCategory Enum."""
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    ENCRYPTION = "encryption"
    CONFIGURATION = "configuration"
    LOGGING = "logging"

    @property
    def value(self):
        return self


class MockAuditFinding:
    """Mock für AuditFinding - verwendet echte Enum-Werte."""

    def __init__(
        self,
        id: str,
        category: AuditCategory,
        severity: AuditSeverity,
        title: str,
        description: str,
        recommendation: str,
        affected_component: str,
        passed: bool,
        details: Dict[str, Any] = None
    ):
        self.id = id
        self.category = category
        self.severity = severity
        self.title = title
        self.description = description
        self.recommendation = recommendation
        self.affected_component = affected_component
        self.passed = passed
        self.details = details or {}

    def to_dict(self):
        return {
            "id": self.id,
            "category": self.category.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "recommendation": self.recommendation,
            "affected_component": self.affected_component,
            "passed": self.passed,
            "details": self.details
        }


class MockAuditReport:
    """Mock für AuditReport."""

    def __init__(
        self,
        timestamp: datetime,
        score: float,
        passed: bool,
        findings: List[MockAuditFinding],
        summary: Dict[str, int]
    ):
        self.timestamp = timestamp
        self.score = score
        self.passed = passed
        self.findings = findings
        self.summary = summary


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_superuser():
    """Mock Superuser für Authentifizierung."""
    user = Mock()
    user.id = uuid4()
    user.email = "admin@example.com"
    user.is_superuser = True
    user.is_active = True
    return user


@pytest.fixture
def mock_regular_user():
    """Mock regulärer Benutzer (kein Superuser)."""
    user = Mock()
    user.id = uuid4()
    user.email = "user@example.com"
    user.is_superuser = False
    user.is_active = True
    return user


@pytest.fixture
def mock_findings():
    """Mock Security Findings für Tests - verwendet echte Enum-Werte."""
    return [
        MockAuditFinding(
            id="SEC-001",
            category=AuditCategory.AUTHENTICATION,
            severity=AuditSeverity.CRITICAL,
            title="Schwaches Passwort-Hashing",
            description="bcrypt Rounds zu niedrig",
            recommendation="Erhöhe bcrypt Rounds auf mindestens 12",
            affected_component="app.core.security",
            passed=False,
            details={"current_rounds": 8, "recommended": 12}
        ),
        MockAuditFinding(
            id="SEC-002",
            category=AuditCategory.ENCRYPTION,
            severity=AuditSeverity.HIGH,
            title="SSL nicht erzwungen",
            description="Datenbank-Verbindung ohne SSL",
            recommendation="Aktiviere sslmode=require",
            affected_component="app.core.config",
            passed=False,
            details={"current_mode": "prefer"}
        ),
        MockAuditFinding(
            id="SEC-003",
            category=AuditCategory.CONFIGURATION,
            severity=AuditSeverity.MEDIUM,
            title="Debug-Modus aktiv",
            description="DEBUG sollte in Produktion deaktiviert sein",
            recommendation="Setze DEBUG=false",
            affected_component="app.core.config",
            passed=True,
            details={"debug": False}
        ),
        MockAuditFinding(
            id="SEC-004",
            category=AuditCategory.LOGGING,
            severity=AuditSeverity.LOW,
            title="Logging Level zu verbose",
            description="DEBUG Level kann sensible Daten exponieren",
            recommendation="Setze LOG_LEVEL auf INFO",
            affected_component="app.core.logging",
            passed=True,
            details={"level": "INFO"}
        ),
        MockAuditFinding(
            id="SEC-005",
            category=AuditCategory.AUTHORIZATION,
            severity=AuditSeverity.INFO,
            title="Rate Limiting konfiguriert",
            description="Rate Limiting ist aktiviert",
            recommendation="Keine Aktion erforderlich",
            affected_component="app.core.rate_limiting",
            passed=True,
            details={"enabled": True}
        ),
    ]


@pytest.fixture
def mock_audit_report(mock_findings):
    """Mock Audit Report."""
    return MockAuditReport(
        timestamp=datetime(2025, 1, 15, 10, 30, 0),
        score=75.5,
        passed=False,
        findings=mock_findings,
        summary={
            "total": 5,
            "passed": 3,
            "failed": 2,
            "critical": 1,
            "high": 1,
            "medium": 1,
            "low": 1,
            "info": 1
        }
    )


@pytest.fixture
def mock_audit_service(mock_audit_report):
    """Mock Security Audit Service."""
    service = Mock()
    service.run_audit = Mock(return_value=mock_audit_report)
    return service


@pytest.fixture
def mock_passing_audit_report(mock_findings):
    """Mock Audit Report mit bestandenem Audit (Score 95)."""
    # Alle Findings bestanden
    for finding in mock_findings:
        finding.passed = True

    return MockAuditReport(
        timestamp=datetime(2025, 1, 15, 10, 30, 0),
        score=95.0,
        passed=True,
        findings=mock_findings,
        summary={
            "total": 5,
            "passed": 5,
            "failed": 0,
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "info": 1
        }
    )


# ========================= Test App Factory =========================


def create_test_app(mock_superuser, mock_audit_service):
    """Create test app with mocked dependencies."""
    from fastapi import FastAPI
    from app.api.v1.security import router

    app = FastAPI()

    # Override dependencies
    async def override_get_current_superuser():
        return mock_superuser

    def override_get_security_audit_service():
        return mock_audit_service

    app.dependency_overrides = {}

    from app.api.dependencies import get_current_superuser
    app.dependency_overrides[get_current_superuser] = override_get_current_superuser

    # Patch the service getter at module level
    with patch("app.api.v1.security.get_security_audit_service", return_value=mock_audit_service):
        app.include_router(router)

    return app


# ========================= Security Audit Endpoint Tests =========================


class TestSecurityAuditEndpoint:
    """Tests für /security/audit Endpoint."""

    @pytest.mark.asyncio
    async def test_run_audit_success(self, mock_superuser, mock_audit_service, mock_audit_report):
        """Test erfolgreicher Security Audit."""
        with patch("app.api.v1.security.get_security_audit_service", return_value=mock_audit_service):
            from app.api.v1.security import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_superuser():
                return mock_superuser

            from app.api.dependencies import get_current_superuser
            app.dependency_overrides[get_current_superuser] = override_superuser
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/security/audit")

            assert response.status_code == 200
            data = response.json()

            assert data["score"] == 75.5
            assert data["passed"] is False
            assert data["total_findings"] == 5
            assert data["critical_count"] == 1
            assert data["high_count"] == 1
            assert len(data["findings"]) == 5

    @pytest.mark.asyncio
    async def test_audit_findings_structure(self, mock_superuser, mock_audit_service):
        """Test Struktur der Audit Findings."""
        with patch("app.api.v1.security.get_security_audit_service", return_value=mock_audit_service):
            from app.api.v1.security import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_superuser():
                return mock_superuser

            from app.api.dependencies import get_current_superuser
            app.dependency_overrides[get_current_superuser] = override_superuser
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/security/audit")

            data = response.json()
            finding = data["findings"][0]

            # Verify finding structure
            assert "id" in finding
            assert "category" in finding
            assert "severity" in finding
            assert "title" in finding
            assert "description" in finding
            assert "recommendation" in finding
            assert "affected_component" in finding
            assert "passed" in finding
            assert "details" in finding


# ========================= Security Score Endpoint Tests =========================


class TestSecurityScoreEndpoint:
    """Tests für /security/score Endpoint."""

    @pytest.mark.asyncio
    async def test_get_score_grade_c(self, mock_superuser, mock_audit_service):
        """Test Score mit Note C (70-79)."""
        with patch("app.api.v1.security.get_security_audit_service", return_value=mock_audit_service):
            from app.api.v1.security import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_superuser():
                return mock_superuser

            from app.api.dependencies import get_current_superuser
            app.dependency_overrides[get_current_superuser] = override_superuser
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/security/score")

            assert response.status_code == 200
            data = response.json()

            assert data["score"] == 75.5
            assert data["grade"] == "C"  # 70-79 = C
            assert data["passed"] is False
            assert "Akzeptable Sicherheit" in data["recommendation"]

    @pytest.mark.asyncio
    async def test_get_score_grade_a(self, mock_superuser, mock_passing_audit_report):
        """Test Score mit Note A (90+)."""
        mock_service = Mock()
        mock_service.run_audit = Mock(return_value=mock_passing_audit_report)

        with patch("app.api.v1.security.get_security_audit_service", return_value=mock_service):
            from app.api.v1.security import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_superuser():
                return mock_superuser

            from app.api.dependencies import get_current_superuser
            app.dependency_overrides[get_current_superuser] = override_superuser
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/security/score")

            data = response.json()

            assert data["grade"] == "A"
            assert data["passed"] is True
            assert "Ausgezeichnete" in data["recommendation"]

    @pytest.mark.asyncio
    async def test_get_score_grade_f_critical(self, mock_superuser, mock_findings):
        """Test Score mit Note F (unter 60)."""
        # Create report with low score
        low_score_report = MockAuditReport(
            timestamp=datetime.now(),
            score=45.0,
            passed=False,
            findings=mock_findings,
            summary={"total": 5, "passed": 1, "failed": 4}
        )
        mock_service = Mock()
        mock_service.run_audit = Mock(return_value=low_score_report)

        with patch("app.api.v1.security.get_security_audit_service", return_value=mock_service):
            from app.api.v1.security import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_superuser():
                return mock_superuser

            from app.api.dependencies import get_current_superuser
            app.dependency_overrides[get_current_superuser] = override_superuser
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/security/score")

            data = response.json()

            assert data["grade"] == "F"
            assert "Kritische Sicherheitsprobleme" in data["recommendation"]


# ========================= Critical Findings Endpoint Tests =========================


class TestCriticalFindingsEndpoint:
    """Tests für /security/findings/critical Endpoint."""

    @pytest.mark.asyncio
    async def test_get_critical_findings(self, mock_superuser, mock_audit_service):
        """Test Abruf kritischer Findings."""
        with patch("app.api.v1.security.get_security_audit_service", return_value=mock_audit_service):
            from app.api.v1.security import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_superuser():
                return mock_superuser

            from app.api.dependencies import get_current_superuser
            app.dependency_overrides[get_current_superuser] = override_superuser
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/security/findings/critical")

            assert response.status_code == 200
            data = response.json()

            # Should have 2 critical/high failed findings
            assert data["total_critical_high"] == 2
            assert data["action_required"] is True
            assert len(data["findings"]) == 2

    @pytest.mark.asyncio
    async def test_no_critical_findings(self, mock_superuser, mock_passing_audit_report):
        """Test wenn keine kritischen Findings vorhanden."""
        mock_service = Mock()
        mock_service.run_audit = Mock(return_value=mock_passing_audit_report)

        with patch("app.api.v1.security.get_security_audit_service", return_value=mock_service):
            from app.api.v1.security import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_superuser():
                return mock_superuser

            from app.api.dependencies import get_current_superuser
            app.dependency_overrides[get_current_superuser] = override_superuser
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/security/findings/critical")

            data = response.json()

            assert data["total_critical_high"] == 0
            assert data["action_required"] is False
            assert len(data["findings"]) == 0


# ========================= Security Checklist Endpoint Tests =========================


class TestSecurityChecklistEndpoint:
    """Tests für /security/checklist Endpoint."""

    @pytest.mark.asyncio
    async def test_get_checklist(self, mock_superuser, mock_audit_service):
        """Test Abruf der Security Checklist."""
        with patch("app.api.v1.security.get_security_audit_service", return_value=mock_audit_service):
            from app.api.v1.security import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_superuser():
                return mock_superuser

            from app.api.dependencies import get_current_superuser
            app.dependency_overrides[get_current_superuser] = override_superuser
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/security/checklist")

            assert response.status_code == 200
            data = response.json()

            assert "checklist" in data
            assert "passed_count" in data
            assert "failed_count" in data
            assert "total" in data

            assert data["total"] == 5
            assert data["passed_count"] == 3
            assert data["failed_count"] == 2

    @pytest.mark.asyncio
    async def test_checklist_item_structure(self, mock_superuser, mock_audit_service):
        """Test Struktur der Checklist Items."""
        with patch("app.api.v1.security.get_security_audit_service", return_value=mock_audit_service):
            from app.api.v1.security import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_superuser():
                return mock_superuser

            from app.api.dependencies import get_current_superuser
            app.dependency_overrides[get_current_superuser] = override_superuser
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/security/checklist")

            data = response.json()
            item = data["checklist"][0]

            assert "id" in item
            assert "title" in item
            assert "status" in item
            assert item["status"] in ["bestanden", "nicht_bestanden"]
            assert "severity" in item
            assert "category" in item

    @pytest.mark.asyncio
    async def test_checklist_sorted_by_severity(self, mock_superuser, mock_audit_service):
        """Test Checklist ist nach Severity sortiert."""
        with patch("app.api.v1.security.get_security_audit_service", return_value=mock_audit_service):
            from app.api.v1.security import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_superuser():
                return mock_superuser

            from app.api.dependencies import get_current_superuser
            app.dependency_overrides[get_current_superuser] = override_superuser
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/security/checklist")

            data = response.json()
            checklist = data["checklist"]

            # Failed items should come first
            failed_items = [c for c in checklist if c["status"] == "nicht_bestanden"]
            passed_items = [c for c in checklist if c["status"] == "bestanden"]

            # Verify failed items are before passed items
            if failed_items and passed_items:
                first_failed_idx = checklist.index(failed_items[0])
                last_failed_idx = checklist.index(failed_items[-1])
                first_passed_idx = checklist.index(passed_items[0])

                assert last_failed_idx < first_passed_idx


# ========================= Security Recommendations Endpoint Tests =========================


class TestSecurityRecommendationsEndpoint:
    """Tests für /security/recommendations Endpoint."""

    @pytest.mark.asyncio
    async def test_get_recommendations(self, mock_superuser, mock_audit_service):
        """Test Abruf der Sicherheitsempfehlungen."""
        with patch("app.api.v1.security.get_security_audit_service", return_value=mock_audit_service):
            from app.api.v1.security import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_superuser():
                return mock_superuser

            from app.api.dependencies import get_current_superuser
            app.dependency_overrides[get_current_superuser] = override_superuser
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/security/recommendations")

            assert response.status_code == 200
            data = response.json()

            assert "total_empfehlungen" in data
            assert "empfehlungen" in data
            assert "naechste_aktion" in data

            # Should have 2 recommendations (2 failed findings)
            assert data["total_empfehlungen"] == 2

    @pytest.mark.asyncio
    async def test_recommendations_structure(self, mock_superuser, mock_audit_service):
        """Test Struktur der Empfehlungen."""
        with patch("app.api.v1.security.get_security_audit_service", return_value=mock_audit_service):
            from app.api.v1.security import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_superuser():
                return mock_superuser

            from app.api.dependencies import get_current_superuser
            app.dependency_overrides[get_current_superuser] = override_superuser
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/security/recommendations")

            data = response.json()
            rec = data["empfehlungen"][0]

            # Verify German field names
            assert "prioritaet" in rec
            assert "id" in rec
            assert "titel" in rec
            assert "schweregrad" in rec
            assert "empfehlung" in rec
            assert "betroffene_komponente" in rec

    @pytest.mark.asyncio
    async def test_recommendations_sorted_by_priority(self, mock_superuser, mock_audit_service):
        """Test Empfehlungen sind nach Priorität sortiert (Critical zuerst)."""
        with patch("app.api.v1.security.get_security_audit_service", return_value=mock_audit_service):
            from app.api.v1.security import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_superuser():
                return mock_superuser

            from app.api.dependencies import get_current_superuser
            app.dependency_overrides[get_current_superuser] = override_superuser
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/security/recommendations")

            data = response.json()
            recommendations = data["empfehlungen"]

            if len(recommendations) >= 2:
                # Critical should come before High
                first_severity = recommendations[0]["schweregrad"]
                second_severity = recommendations[1]["schweregrad"]

                severity_order = ["critical", "high", "medium", "low", "info"]
                assert severity_order.index(first_severity) <= severity_order.index(second_severity)

    @pytest.mark.asyncio
    async def test_no_recommendations_when_all_passed(self, mock_superuser, mock_passing_audit_report):
        """Test keine Empfehlungen wenn alle Prüfungen bestanden."""
        mock_service = Mock()
        mock_service.run_audit = Mock(return_value=mock_passing_audit_report)

        with patch("app.api.v1.security.get_security_audit_service", return_value=mock_service):
            from app.api.v1.security import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_superuser():
                return mock_superuser

            from app.api.dependencies import get_current_superuser
            app.dependency_overrides[get_current_superuser] = override_superuser
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/security/recommendations")

            data = response.json()

            assert data["total_empfehlungen"] == 0
            assert data["naechste_aktion"] is None


# ========================= Authentication Tests =========================


class TestSecurityAPIAuthentication:
    """Tests für Authentifizierung der Security API."""

    @pytest.mark.asyncio
    async def test_audit_requires_superuser(self):
        """Test Audit Endpoint erfordert Superuser."""
        from app.api.v1.security import router
        from fastapi import FastAPI

        app = FastAPI()

        # No authentication override - should fail
        # Note: Without proper auth, FastAPI will return 401 or 422
        app.include_router(router)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/security/audit")

        # Should fail due to missing authentication
        assert response.status_code in [401, 403, 422]

    @pytest.mark.asyncio
    async def test_non_superuser_denied(self, mock_regular_user, mock_audit_service):
        """Test regulärer Benutzer wird abgelehnt."""
        with patch("app.api.v1.security.get_security_audit_service", return_value=mock_audit_service):
            from app.api.v1.security import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_non_superuser():
                # Simulate the get_current_superuser dependency raising HTTPException
                from fastapi import HTTPException, status
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Superuser-Berechtigung erforderlich"
                )

            from app.api.dependencies import get_current_superuser
            app.dependency_overrides[get_current_superuser] = override_non_superuser
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/security/audit")

            assert response.status_code == 403
            assert "Superuser" in response.json()["detail"]


# ========================= German Response Tests =========================


class TestGermanResponses:
    """Tests für deutsche Antwort-Texte."""

    @pytest.mark.asyncio
    async def test_checklist_status_german(self, mock_superuser, mock_audit_service):
        """Test Checklist Status auf Deutsch."""
        with patch("app.api.v1.security.get_security_audit_service", return_value=mock_audit_service):
            from app.api.v1.security import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_superuser():
                return mock_superuser

            from app.api.dependencies import get_current_superuser
            app.dependency_overrides[get_current_superuser] = override_superuser
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/security/checklist")

            data = response.json()

            for item in data["checklist"]:
                # Status should be in German
                assert item["status"] in ["bestanden", "nicht_bestanden"]

    @pytest.mark.asyncio
    async def test_recommendations_german_fields(self, mock_superuser, mock_audit_service):
        """Test Empfehlungen haben deutsche Feldnamen."""
        with patch("app.api.v1.security.get_security_audit_service", return_value=mock_audit_service):
            from app.api.v1.security import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_superuser():
                return mock_superuser

            from app.api.dependencies import get_current_superuser
            app.dependency_overrides[get_current_superuser] = override_superuser
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/security/recommendations")

            data = response.json()

            # Check German field names
            assert "total_empfehlungen" in data
            assert "naechste_aktion" in data

            if data["empfehlungen"]:
                rec = data["empfehlungen"][0]
                assert "prioritaet" in rec
                assert "titel" in rec
                assert "schweregrad" in rec
                assert "empfehlung" in rec
                assert "betroffene_komponente" in rec

    @pytest.mark.asyncio
    async def test_score_recommendation_german(self, mock_superuser, mock_audit_service):
        """Test Score Empfehlungen auf Deutsch."""
        with patch("app.api.v1.security.get_security_audit_service", return_value=mock_audit_service):
            from app.api.v1.security import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_superuser():
                return mock_superuser

            from app.api.dependencies import get_current_superuser
            app.dependency_overrides[get_current_superuser] = override_superuser
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/security/score")

            data = response.json()

            # Recommendation should be in German
            recommendation = data["recommendation"]
            # Check for German words
            german_words = ["Sicherheit", "Verbesserung", "Ausgezeichnet", "Akzeptable", "Kritische"]
            assert any(word in recommendation for word in german_words)


# ========================= Edge Cases =========================


class TestSecurityAPIEdgeCases:
    """Tests für Grenzfälle."""

    @pytest.mark.asyncio
    async def test_empty_findings_list(self, mock_superuser):
        """Test mit leerer Findings-Liste."""
        empty_report = MockAuditReport(
            timestamp=datetime.now(),
            score=100.0,
            passed=True,
            findings=[],
            summary={"total": 0, "passed": 0, "failed": 0}
        )
        mock_service = Mock()
        mock_service.run_audit = Mock(return_value=empty_report)

        with patch("app.api.v1.security.get_security_audit_service", return_value=mock_service):
            from app.api.v1.security import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_superuser():
                return mock_superuser

            from app.api.dependencies import get_current_superuser
            app.dependency_overrides[get_current_superuser] = override_superuser
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/security/audit")

            assert response.status_code == 200
            data = response.json()

            assert data["total_findings"] == 0
            assert len(data["findings"]) == 0

    @pytest.mark.asyncio
    async def test_all_severities_present(self, mock_superuser, mock_audit_service):
        """Test mit allen Severity-Stufen."""
        with patch("app.api.v1.security.get_security_audit_service", return_value=mock_audit_service):
            from app.api.v1.security import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_superuser():
                return mock_superuser

            from app.api.dependencies import get_current_superuser
            app.dependency_overrides[get_current_superuser] = override_superuser
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/security/audit")

            data = response.json()
            severities = {f["severity"] for f in data["findings"]}

            # All severity levels should be present in our mock data
            expected = {"critical", "high", "medium", "low", "info"}
            assert severities == expected


# ========================= Response Model Validation =========================


class TestResponseModelValidation:
    """Tests für Response Model Validierung."""

    @pytest.mark.asyncio
    async def test_audit_response_model(self, mock_superuser, mock_audit_service):
        """Test AuditReportResponse Model."""
        with patch("app.api.v1.security.get_security_audit_service", return_value=mock_audit_service):
            from app.api.v1.security import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_superuser():
                return mock_superuser

            from app.api.dependencies import get_current_superuser
            app.dependency_overrides[get_current_superuser] = override_superuser
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/security/audit")

            data = response.json()

            # Verify all required fields are present
            required_fields = [
                "timestamp", "score", "passed", "total_findings",
                "critical_count", "high_count", "summary", "findings"
            ]
            for field in required_fields:
                assert field in data, f"Missing field: {field}"

            # Verify data types
            assert isinstance(data["score"], (int, float))
            assert isinstance(data["passed"], bool)
            assert isinstance(data["total_findings"], int)
            assert isinstance(data["findings"], list)

    @pytest.mark.asyncio
    async def test_score_response_model(self, mock_superuser, mock_audit_service):
        """Test SecurityScoreResponse Model."""
        with patch("app.api.v1.security.get_security_audit_service", return_value=mock_audit_service):
            from app.api.v1.security import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_superuser():
                return mock_superuser

            from app.api.dependencies import get_current_superuser
            app.dependency_overrides[get_current_superuser] = override_superuser
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/security/score")

            data = response.json()

            # Verify all required fields
            required_fields = [
                "score", "grade", "passed", "critical_issues",
                "high_issues", "recommendation"
            ]
            for field in required_fields:
                assert field in data, f"Missing field: {field}"

            # Verify grade is valid
            assert data["grade"] in ["A", "B", "C", "D", "F"]
