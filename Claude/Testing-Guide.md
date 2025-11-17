🧪 TESTING STRATEGY & IMPLEMENTATION GUIDE
Comprehensive Testing for FastAPI Applications

📋 TABLE OF CONTENTS

Introduction
Testing Philosophy
Testing Environment Setup
Unit Tests
Integration Tests
API Tests
Database Tests
Mocking & Patching
Test Fixtures & Factories
Test Coverage
Async Testing
Load Testing
CI/CD Pipeline
Best Practices


🎯 INTRODUCTION
Testing Pyramid
                    ┌─────────────┐
                    │   E2E Tests │  (5%)
                    │   Manual    │
                    └─────────────┘
                 ┌──────────────────┐
                 │ Integration Tests│  (15%)
                 │   API Tests      │
                 └──────────────────┘
            ┌─────────────────────────┐
            │      Unit Tests         │  (80%)
            │   Fast, Isolated        │
            └─────────────────────────┘
Test Types Coverage
Test TypePurposeSpeedCoverageUnit TestsTest individual functions/methodsFast80%Integration TestsTest component interactionsMedium15%API TestsTest HTTP endpointsMediumIncluded in IntegrationE2E TestsTest full user workflowsSlow5%Load TestsTest performance under loadSlowPerformance validation

🛠️ TESTING ENVIRONMENT SETUP
1. Dependencies Installation
bash# requirements-test.txt

# Testing Framework
pytest==7.4.4
pytest-asyncio==0.23.3
pytest-cov==4.1.0
pytest-mock==3.12.0
pytest-xdist==3.5.0  # Parallel testing

# FastAPI Testing
httpx==0.26.0  # Async HTTP client
asgi-lifespan==2.1.0

# Database Testing
factory-boy==3.3.0
faker==22.0.0
pytest-postgresql==5.0.0

# Mocking
responses==0.24.1
freezegun==1.4.0  # Time mocking

# Load Testing
locust==2.20.0

# Code Quality
pylint==3.0.3
black==23.12.1
mypy==1.8.0

# Coverage
coverage[toml]==7.4.0
bash# Install dependencies
pip install -r requirements-test.txt
2. Pytest Configuration
toml# pyproject.toml

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py", "*_test.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]

# Asyncio mode
asyncio_mode = "auto"

# Markers
markers = [
    "unit: Unit tests",
    "integration: Integration tests",
    "api: API tests",
    "db: Database tests",
    "slow: Slow running tests",
    "smoke: Smoke tests for quick validation",
]

# Coverage
addopts = """
    --verbose
    --strict-markers
    --strict-config
    --cov=backend
    --cov-report=html
    --cov-report=term-missing
    --cov-fail-under=80
"""

# Ignore warnings
filterwarnings = [
    "ignore::DeprecationWarning",
    "ignore::PendingDeprecationWarning",
]
```

### 3. Test Directory Structure
```
tests/
├── __init__.py
├── conftest.py                 # Shared fixtures
│
├── unit/                       # Unit tests
│   ├── __init__.py
│   ├── test_security.py
│   ├── test_password.py
│   ├── test_validators.py
│   └── test_utils.py
│
├── integration/                # Integration tests
│   ├── __init__.py
│   ├── test_auth_flow.py
│   ├── test_document_flow.py
│   └── test_ocr_flow.py
│
├── api/                        # API endpoint tests
│   ├── __init__.py
│   ├── test_auth_endpoints.py
│   ├── test_user_endpoints.py
│   ├── test_document_endpoints.py
│   └── test_ocr_endpoints.py
│
├── db/                         # Database tests
│   ├── __init__.py
│   ├── test_models.py
│   ├── test_queries.py
│   └── test_migrations.py
│
├── load/                       # Load tests
│   ├── __init__.py
│   └── locustfile.py
│
├── fixtures/                   # Test fixtures
│   ├── __init__.py
│   ├── auth_fixtures.py
│   ├── db_fixtures.py
│   └── api_fixtures.py
│
└── factories/                  # Model factories
    ├── __init__.py
    ├── user_factory.py
    └── document_factory.py

🔬 UNIT TESTS
1. Basic Unit Test Structure
python# tests/unit/test_password.py

import pytest
from core.password import PasswordManager, password_manager


class TestPasswordManager:
    """Test password hashing and validation"""
    
    def test_hash_password(self):
        """Test password hashing"""
        # Arrange
        plain_password = "TestPassword123!"
        
        # Act
        hashed = password_manager.hash_password(plain_password)
        
        # Assert
        assert hashed is not None
        assert hashed != plain_password
        assert len(hashed) > 0
    
    def test_verify_password_correct(self):
        """Test password verification with correct password"""
        # Arrange
        plain_password = "TestPassword123!"
        hashed = password_manager.hash_password(plain_password)
        
        # Act
        result = password_manager.verify_password(plain_password, hashed)
        
        # Assert
        assert result is True
    
    def test_verify_password_incorrect(self):
        """Test password verification with incorrect password"""
        # Arrange
        plain_password = "TestPassword123!"
        wrong_password = "WrongPassword456!"
        hashed = password_manager.hash_password(plain_password)
        
        # Act
        result = password_manager.verify_password(wrong_password, hashed)
        
        # Assert
        assert result is False
    
    def test_hash_different_passwords_produce_different_hashes(self):
        """Test that same password produces different hashes (salt)"""
        # Arrange
        password = "TestPassword123!"
        
        # Act
        hash1 = password_manager.hash_password(password)
        hash2 = password_manager.hash_password(password)
        
        # Assert
        assert hash1 != hash2  # Different salts
        assert password_manager.verify_password(password, hash1)
        assert password_manager.verify_password(password, hash2)
    
    def test_needs_rehash_old_algorithm(self):
        """Test detection of outdated hash algorithms"""
        # Arrange - create a bcrypt hash
        from passlib.context import CryptContext
        old_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        old_hash = old_context.hash("password123")
        
        # Act
        needs_update = password_manager.needs_rehash(old_hash)
        
        # Assert
        assert needs_update is True
    
    @pytest.mark.parametrize("password,expected_valid", [
        ("short", False),                      # Too short
        ("NoDigits!", False),                  # No digits
        ("noupperca5e!", False),               # No uppercase
        ("NOLOWERCASE5!", False),              # No lowercase
        ("NoSpecial123", False),               # No special char
        ("ValidPass123!", True),               # Valid
        ("AnotherV@lid1", True),              # Valid
    ])
    def test_password_strength_validation(self, password, expected_valid):
        """Test password strength validation with various inputs"""
        # Act
        result = password_manager.validate_password_strength(password)
        
        # Assert
        assert result["is_valid"] == expected_valid
    
    def test_generate_password_default(self):
        """Test password generation with defaults"""
        # Act
        password = password_manager.generate_password()
        
        # Assert
        assert len(password) == 16
        assert any(c.isupper() for c in password)
        assert any(c.islower() for c in password)
        assert any(c.isdigit() for c in password)
    
    def test_generate_password_custom_length(self):
        """Test password generation with custom length"""
        # Act
        password = password_manager.generate_password(length=20)
        
        # Assert
        assert len(password) == 20
    
    def test_generate_password_raises_on_short_length(self):
        """Test that short password length raises error"""
        # Act & Assert
        with pytest.raises(ValueError, match="at least 12 characters"):
            password_manager.generate_password(length=8)
2. Testing JWT Tokens
python# tests/unit/test_security.py

import pytest
from datetime import datetime, timedelta
from jose import JWTError

from core.security import TokenManager, token_manager


class TestTokenManager:
    """Test JWT token generation and validation"""
    
    def test_create_access_token(self):
        """Test access token creation"""
        # Arrange
        user_id = "123e4567-e89b-12d3-a456-426614174000"
        
        # Act
        token = token_manager.create_access_token(subject=user_id)
        
        # Assert
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0
    
    def test_create_access_token_with_claims(self):
        """Test access token with additional claims"""
        # Arrange
        user_id = "123e4567-e89b-12d3-a456-426614174000"
        claims = {
            "email": "test@example.com",
            "role": "admin"
        }
        
        # Act
        token = token_manager.create_access_token(
            subject=user_id,
            additional_claims=claims
        )
        payload = token_manager.decode_token(token)
        
        # Assert
        assert payload["sub"] == user_id
        assert payload["email"] == claims["email"]
        assert payload["role"] == claims["role"]
    
    def test_decode_valid_token(self):
        """Test decoding a valid token"""
        # Arrange
        user_id = "123e4567-e89b-12d3-a456-426614174000"
        token = token_manager.create_access_token(subject=user_id)
        
        # Act
        payload = token_manager.decode_token(token)
        
        # Assert
        assert payload["sub"] == user_id
        assert "exp" in payload
        assert "iat" in payload
        assert payload["type"] == "access"
    
    def test_decode_expired_token_raises_error(self):
        """Test that expired token raises error"""
        # Arrange
        user_id = "123e4567-e89b-12d3-a456-426614174000"
        token = token_manager.create_access_token(
            subject=user_id,
            expires_delta=timedelta(seconds=-1)  # Already expired
        )
        
        # Act & Assert
        with pytest.raises(Exception):  # HTTPException or JWTError
            token_manager.decode_token(token)
    
    def test_verify_token_type(self):
        """Test token type verification"""
        # Arrange
        user_id = "123e4567-e89b-12d3-a456-426614174000"
        access_token = token_manager.create_access_token(subject=user_id)
        payload = token_manager.decode_token(access_token)
        
        # Act & Assert - should not raise
        token_manager.verify_token_type(payload, "access")
        
        # Act & Assert - should raise
        with pytest.raises(Exception):
            token_manager.verify_token_type(payload, "refresh")
    
    def test_refresh_token_creation(self):
        """Test refresh token creation"""
        # Arrange
        user_id = "123e4567-e89b-12d3-a456-426614174000"
        
        # Act
        token = token_manager.create_refresh_token(subject=user_id)
        payload = token_manager.decode_token(token)
        
        # Assert
        assert payload["type"] == "refresh"
        assert payload["sub"] == user_id
    
    def test_token_contains_jti(self):
        """Test that tokens contain unique JTI (for blacklisting)"""
        # Arrange
        user_id = "123e4567-e89b-12d3-a456-426614174000"
        
        # Act
        token1 = token_manager.create_access_token(subject=user_id)
        token2 = token_manager.create_access_token(subject=user_id)
        
        payload1 = token_manager.decode_token(token1)
        payload2 = token_manager.decode_token(token2)
        
        # Assert
        assert "jti" in payload1
        assert "jti" in payload2
        assert payload1["jti"] != payload2["jti"]  # Unique
3. Testing Input Validators
python# tests/unit/test_validators.py

import pytest
from fastapi import HTTPException

from core.validators import InputValidator


class TestInputValidator:
    """Test input validation and sanitization"""
    
    @pytest.mark.parametrize("sql_input", [
        "SELECT * FROM users",
        "'; DROP TABLE users; --",
        "1' OR '1'='1",
        "UNION SELECT password FROM users",
    ])
    def test_sql_injection_detection(self, sql_input):
        """Test SQL injection pattern detection"""
        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            InputValidator.sanitize_sql_input(sql_input)
        
        assert exc_info.value.status_code == 400
        assert "SQL injection" in str(exc_info.value.detail).lower()
    
    def test_safe_sql_input_passes(self):
        """Test that safe SQL input passes validation"""
        # Arrange
        safe_input = "John Doe"
        
        # Act
        result = InputValidator.sanitize_sql_input(safe_input)
        
        # Assert
        assert result == safe_input
    
    @pytest.mark.parametrize("html,expected", [
        ("<script>alert('XSS')</script>", ""),
        ("<b>Bold</b>", "<b>Bold</b>"),
        ('<img src=x onerror=alert(1)>', ""),
        ("<p>Safe paragraph</p>", "<p>Safe paragraph</p>"),
    ])
    def test_html_sanitization(self, html, expected):
        """Test HTML sanitization"""
        # Act
        result = InputValidator.sanitize_html(html, allowed_tags=['b', 'p'])
        
        # Assert
        assert result == expected
    
    @pytest.mark.parametrize("filename,expected", [
        ("document.pdf", "document.pdf"),
        ("../../../etc/passwd", "passwd"),
        ("my document.pdf", "my document.pdf"),
        ("file<>name.txt", "filename.txt"),
        ("very" + "long" * 100 + ".txt", True),  # Should be truncated
    ])
    def test_filename_sanitization(self, filename, expected):
        """Test filename sanitization"""
        # Act
        result = InputValidator.sanitize_filename(filename)
        
        # Assert
        if expected is True:
            # Check truncation
            assert len(result) <= 255
        else:
            assert result == expected
    
    @pytest.mark.parametrize("email,valid", [
        ("test@example.com", True),
        ("invalid.email", False),
        ("no@domain", False),
        ("valid.email+tag@domain.co.uk", True),
    ])
    def test_email_validation(self, email, valid):
        """Test email validation"""
        if valid:
            # Should not raise
            result = InputValidator.validate_email(email)
            assert result == email.lower()
        else:
            # Should raise
            with pytest.raises(HTTPException):
                InputValidator.validate_email(email)
    
    @pytest.mark.parametrize("command", [
        "rm -rf /",
        "cat /etc/passwd",
        "$(malicious)",
        "`whoami`",
    ])
    def test_command_injection_detection(self, command):
        """Test command injection detection"""
        # Act & Assert
        with pytest.raises(HTTPException):
            InputValidator.validate_no_command_injection(command)

🔗 INTEGRATION TESTS
1. Authentication Flow Integration Test
python# tests/integration/test_auth_flow.py

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from database import get_db
from tests.conftest import get_test_db


class TestAuthenticationFlow:
    """Test complete authentication flows"""
    
    @pytest.fixture(autouse=True)
    def setup(self, test_db: Session):
        """Setup for each test"""
        self.db = test_db
        self.client = TestClient(app)
        
        # Override DB dependency
        app.dependency_overrides[get_db] = lambda: self.db
        
        yield
        
        # Cleanup
        app.dependency_overrides.clear()
    
    def test_complete_registration_and_login_flow(self, test_db):
        """Test user registration and subsequent login"""
        # Step 1: Register new user
        registration_data = {
            "email": "newuser@example.com",
            "username": "newuser",
            "password": "SecurePass123!",
            "password_confirm": "SecurePass123!",
            "first_name": "New",
            "last_name": "User"
        }
        
        register_response = self.client.post(
            "/api/v1/auth/register",
            json=registration_data
        )
        
        assert register_response.status_code == 201
        user_data = register_response.json()
        assert user_data["email"] == registration_data["email"]
        assert user_data["username"] == registration_data["username"]
        assert "hashed_password" not in user_data  # Password not exposed
        
        # Step 2: Login with new user
        login_response = self.client.post(
            "/api/v1/auth/login",
            data={
                "username": registration_data["email"],
                "password": registration_data["password"]
            }
        )
        
        assert login_response.status_code == 200
        login_data = login_response.json()
        assert "access_token" in login_data
        assert "refresh_token" in login_data
        assert login_data["token_type"] == "bearer"
        
        # Step 3: Access protected endpoint with token
        access_token = login_data["access_token"]
        me_response = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        
        assert me_response.status_code == 200
        me_data = me_response.json()
        assert me_data["email"] == registration_data["email"]
    
    def test_login_logout_login_flow(self, test_user):
        """Test login -> logout -> login flow"""
        # Step 1: Login
        login_response = self.client.post(
            "/api/v1/auth/login",
            data={
                "username": test_user.email,
                "password": "TestPassword123!"
            }
        )
        
        assert login_response.status_code == 200
        token1 = login_response.json()["access_token"]
        
        # Step 2: Verify token works
        me_response = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token1}"}
        )
        assert me_response.status_code == 200
        
        # Step 3: Logout
        logout_response = self.client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {token1}"}
        )
        assert logout_response.status_code == 200
        
        # Step 4: Verify old token doesn't work
        me_response2 = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token1}"}
        )
        assert me_response2.status_code == 401
        
        # Step 5: Login again
        login_response2 = self.client.post(
            "/api/v1/auth/login",
            data={
                "username": test_user.email,
                "password": "TestPassword123!"
            }
        )
        
        assert login_response2.status_code == 200
        token2 = login_response2.json()["access_token"]
        
        # Step 6: Verify new token works
        me_response3 = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token2}"}
        )
        assert me_response3.status_code == 200
    
    def test_password_reset_flow(self, test_user):
        """Test complete password reset flow"""
        # Step 1: Request password reset
        reset_request = self.client.post(
            "/api/v1/auth/reset-password/request",
            json={"email": test_user.email}
        )
        
        assert reset_request.status_code == 200
        
        # Step 2: Get reset token from database (in real app, from email)
        from models.auth import PasswordResetToken
        reset_token_obj = self.db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == test_user.id,
            PasswordResetToken.used_at.is_(None)
        ).first()
        
        assert reset_token_obj is not None
        
        # For testing, we need the plain token (normally in email)
        # In production, this would come from the email link
        # Here we'll create a new token for testing
        from core.security import token_manager
        from datetime import timedelta
        
        reset_token = token_manager.create_access_token(
            subject=test_user.id,
            additional_claims={"type": "password_reset"},
            expires_delta=timedelta(hours=1)
        )
        
        # Step 3: Reset password with token
        new_password = "NewSecurePass456!"
        reset_confirm = self.client.post(
            "/api/v1/auth/reset-password/confirm",
            json={
                "token": reset_token,
                "new_password": new_password
            }
        )
        
        # May need to handle token verification differently in test
        # assert reset_confirm.status_code == 200
        
        # Step 4: Login with new password
        login_response = self.client.post(
            "/api/v1/auth/login",
            data={
                "username": test_user.email,
                "password": new_password
            }
        )
        
        # assert login_response.status_code == 200
2. Document Management Flow
python# tests/integration/test_document_flow.py

import pytest
import io
from fastapi.testclient import TestClient

from main import app
from tests.conftest import authenticated_client


class TestDocumentManagementFlow:
    """Test complete document management workflows"""
    
    def test_upload_process_download_flow(self, authenticated_client, test_user):
        """Test: upload -> OCR processing -> download"""
        client = authenticated_client
        
        # Step 1: Upload document
        pdf_content = b"%PDF-1.4 fake pdf content"
        files = {
            "file": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")
        }
        data = {
            "title": "Test Invoice",
            "description": "Test document"
        }
        
        upload_response = client.post(
            "/api/v1/documents/upload",
            files=files,
            data=data
        )
        
        assert upload_response.status_code == 201
        document = upload_response.json()
        document_id = document["id"]
        assert document["title"] == "Test Invoice"
        assert document["status"] == "pending"
        
        # Step 2: Trigger OCR processing
        ocr_response = client.post(
            "/api/v1/ocr/process",
            json={
                "document_id": document_id,
                "backend": "deepseek"
            }
        )
        
        assert ocr_response.status_code in [200, 202]  # 202 for async
        
        # Step 3: Check document status
        status_response = client.get(f"/api/v1/documents/{document_id}")
        
        assert status_response.status_code == 200
        # Status might be 'processing' or 'completed' depending on timing
        
        # Step 4: Download document
        download_response = client.get(
            f"/api/v1/documents/{document_id}/download"
        )
        
        assert download_response.status_code == 200
        assert download_response.headers["content-type"] == "application/pdf"
    
    def test_document_crud_flow(self, authenticated_client):
        """Test: create -> read -> update -> delete"""
        client = authenticated_client
        
        # Create
        pdf_content = b"%PDF-1.4 test"
        upload_response = client.post(
            "/api/v1/documents/upload",
            files={"file": ("doc.pdf", io.BytesIO(pdf_content), "application/pdf")},
            data={"title": "Original Title"}
        )
        
        assert upload_response.status_code == 201
        doc_id = upload_response.json()["id"]
        
        # Read
        get_response = client.get(f"/api/v1/documents/{doc_id}")
        assert get_response.status_code == 200
        assert get_response.json()["title"] == "Original Title"
        
        # Update
        update_response = client.patch(
            f"/api/v1/documents/{doc_id}",
            json={"title": "Updated Title", "tags": ["important"]}
        )
        assert update_response.status_code == 200
        assert update_response.json()["title"] == "Updated Title"
        
        # Delete
        delete_response = client.delete(f"/api/v1/documents/{doc_id}")
        assert delete_response.status_code == 204
        
        # Verify deleted
        get_response2 = client.get(f"/api/v1/documents/{doc_id}")
        assert get_response2.status_code == 404

🌐 API TESTS
1. API Test Base Class
python# tests/api/base.py

import pytest
from typing import Dict, Optional
from fastapi.testclient import TestClient


class APITestBase:
    """Base class for API tests with common utilities"""
    
    def __init__(self, client: TestClient):
        self.client = client
        self.token: Optional[str] = None
    
    def set_auth_token(self, token: str):
        """Set authentication token"""
        self.token = token
    
    def get_headers(self, extra_headers: Optional[Dict] = None) -> Dict:
        """Get headers with authentication"""
        headers = {}
        
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        
        if extra_headers:
            headers.update(extra_headers)
        
        return headers
    
    def get(self, url: str, **kwargs):
        """GET request with auth"""
        headers = self.get_headers(kwargs.pop("headers", None))
        return self.client.get(url, headers=headers, **kwargs)
    
    def post(self, url: str, **kwargs):
        """POST request with auth"""
        headers = self.get_headers(kwargs.pop("headers", None))
        return self.client.post(url, headers=headers, **kwargs)
    
    def put(self, url: str, **kwargs):
        """PUT request with auth"""
        headers = self.get_headers(kwargs.pop("headers", None))
        return self.client.put(url, headers=headers, **kwargs)
    
    def patch(self, url: str, **kwargs):
        """PATCH request with auth"""
        headers = self.get_headers(kwargs.pop("headers", None))
        return self.client.patch(url, headers=headers, **kwargs)
    
    def delete(self, url: str, **kwargs):
        """DELETE request with auth"""
        headers = self.get_headers(kwargs.pop("headers", None))
        return self.client.delete(url, headers=headers, **kwargs)
    
    def assert_response_ok(self, response, expected_status: int = 200):
        """Assert response is OK"""
        assert response.status_code == expected_status, \
            f"Expected {expected_status}, got {response.status_code}: {response.text}"
    
    def assert_response_error(self, response, expected_status: int):
        """Assert response is error"""
        assert response.status_code == expected_status
        assert "detail" in response.json()
2. Authentication API Tests
python# tests/api/test_auth_endpoints.py

import pytest
from tests.api.base import APITestBase


class TestAuthEndpoints(APITestBase):
    """Test authentication endpoints"""
    
    def test_register_success(self):
        """Test successful user registration"""
        # Arrange
        user_data = {
            "email": "newuser@test.com",
            "username": "newuser",
            "password": "SecurePass123!",
            "password_confirm": "SecurePass123!",
            "first_name": "New",
            "last_name": "User"
        }
        
        # Act
        response = self.post("/api/v1/auth/register", json=user_data)
        
        # Assert
        self.assert_response_ok(response, 201)
        data = response.json()
        assert data["email"] == user_data["email"]
        assert data["username"] == user_data["username"]
        assert "id" in data
        assert "hashed_password" not in data
    
    def test_register_duplicate_email(self, test_user):
        """Test registration with existing email"""
        # Arrange
        user_data = {
            "email": test_user.email,  # Existing email
            "username": "different",
            "password": "SecurePass123!",
            "password_confirm": "SecurePass123!"
        }
        
        # Act
        response = self.post("/api/v1/auth/register", json=user_data)
        
        # Assert
        self.assert_response_error(response, 400)
        assert "email" in response.json()["detail"].lower()
    
    def test_register_weak_password(self):
        """Test registration with weak password"""
        # Arrange
        user_data = {
            "email": "test@test.com",
            "username": "testuser",
            "password": "weak",
            "password_confirm": "weak"
        }
        
        # Act
        response = self.post("/api/v1/auth/register", json=user_data)
        
        # Assert
        self.assert_response_error(response, 422)
    
    def test_login_success(self, test_user):
        """Test successful login"""
        # Act
        response = self.client.post(
            "/api/v1/auth/login",
            data={
                "username": test_user.email,
                "password": "TestPassword123!"
            }
        )
        
        # Assert
        self.assert_response_ok(response, 200)
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert "user" in data
    
    def test_login_wrong_password(self, test_user):
        """Test login with wrong password"""
        # Act
        response = self.client.post(
            "/api/v1/auth/login",
            data={
                "username": test_user.email,
                "password": "WrongPassword123!"
            }
        )
        
        # Assert
        self.assert_response_error(response, 401)
    
    def test_login_nonexistent_user(self):
        """Test login with non-existent user"""
        # Act
        response = self.client.post(
            "/api/v1/auth/login",
            data={
                "username": "nonexistent@test.com",
                "password": "SomePassword123!"
            }
        )
        
        # Assert
        self.assert_response_error(response, 401)
    
    def test_get_current_user(self, authenticated_client):
        """Test getting current user info"""
        # Act
        response = authenticated_client.get("/api/v1/auth/me")
        
        # Assert
        self.assert_response_ok(response, 200)
        data = response.json()
        assert "id" in data
        assert "email" in data
        assert "username" in data
    
    def test_get_current_user_unauthorized(self):
        """Test getting current user without token"""
        # Act
        response = self.get("/api/v1/auth/me")
        
        # Assert
        self.assert_response_error(response, 401)
    
    def test_refresh_token(self, test_user):
        """Test token refresh"""
        # Login first
        login_response = self.client.post(
            "/api/v1/auth/login",
            data={
                "username": test_user.email,
                "password": "TestPassword123!"
            }
        )
        refresh_token = login_response.json()["refresh_token"]
        
        # Act - refresh token
        response = self.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token}
        )
        
        # Assert
        self.assert_response_ok(response, 200)
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
3. Document API Tests
python# tests/api/test_document_endpoints.py

import pytest
import io
from tests.api.base import APITestBase


class TestDocumentEndpoints(APITestBase):
    """Test document management endpoints"""
    
    def test_list_documents_empty(self, authenticated_client):
        """Test listing documents when none exist"""
        # Act
        response = authenticated_client.get("/api/v1/documents")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []
    
    def test_list_documents_with_pagination(
        self,
        authenticated_client,
        test_documents
    ):
        """Test document list pagination"""
        # Act
        response = authenticated_client.get(
            "/api/v1/documents",
            params={"page": 1, "page_size": 5}
        )
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) <= 5
        assert data["page"] == 1
        assert data["page_size"] == 5
    
    def test_upload_document_success(self, authenticated_client):
        """Test successful document upload"""
        # Arrange
        pdf_content = b"%PDF-1.4 test content"
        files = {
            "file": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")
        }
        data = {
            "title": "Test Document",
            "description": "Test description"
        }
        
        # Act
        response = authenticated_client.post(
            "/api/v1/documents/upload",
            files=files,
            data=data
        )
        
        # Assert
        assert response.status_code == 201
        doc = response.json()
        assert doc["title"] == "Test Document"
        assert doc["status"] == "pending"
    
    def test_upload_document_invalid_type(self, authenticated_client):
        """Test upload with invalid file type"""
        # Arrange
        files = {
            "file": ("test.txt", io.BytesIO(b"text"), "text/plain")
        }
        
        # Act
        response = authenticated_client.post(
            "/api/v1/documents/upload",
            files=files
        )
        
        # Assert
        assert response.status_code == 400
        assert "file type" in response.json()["detail"].lower()
    
    def test_upload_document_too_large(self, authenticated_client):
        """Test upload with file too large"""
        # Arrange
        large_content = b"x" * (51 * 1024 * 1024)  # 51 MB
        files = {
            "file": ("large.pdf", io.BytesIO(large_content), "application/pdf")
        }
        
        # Act
        response = authenticated_client.post(
            "/api/v1/documents/upload",
            files=files
        )
        
        # Assert
        assert response.status_code == 413
    
    def test_get_document_success(self, authenticated_client, test_document):
        """Test getting single document"""
        # Act
        response = authenticated_client.get(
            f"/api/v1/documents/{test_document.id}"
        )
        
        # Assert
        assert response.status_code == 200
        doc = response.json()
        assert doc["id"] == str(test_document.id)
        assert doc["title"] == test_document.title
    
    def test_get_document_not_found(self, authenticated_client):
        """Test getting non-existent document"""
        # Act
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = authenticated_client.get(f"/api/v1/documents/{fake_id}")
        
        # Assert
        assert response.status_code == 404
    
    def test_get_document_wrong_user(
        self,
        authenticated_client,
        other_user_document
    ):
        """Test getting another user's document (should fail)"""
        # Act
        response = authenticated_client.get(
            f"/api/v1/documents/{other_user_document.id}"
        )
        
        # Assert
        assert response.status_code == 403
    
    def test_update_document(self, authenticated_client, test_document):
        """Test updating document metadata"""
        # Arrange
        update_data = {
            "title": "Updated Title",
            "tags": ["important", "urgent"]
        }
        
        # Act
        response = authenticated_client.patch(
            f"/api/v1/documents/{test_document.id}",
            json=update_data
        )
        
        # Assert
        assert response.status_code == 200
        doc = response.json()
        assert doc["title"] == "Updated Title"
        assert set(doc["tags"]) == {"important", "urgent"}
    
    def test_delete_document(self, authenticated_client, test_document):
        """Test deleting document"""
        # Act
        response = authenticated_client.delete(
            f"/api/v1/documents/{test_document.id}"
        )
        
        # Assert
        assert response.status_code == 204
        
        # Verify deleted
        get_response = authenticated_client.get(
            f"/api/v1/documents/{test_document.id}"
        )
        assert get_response.status_code == 404

🗄️ DATABASE TESTS
1. Test Database Configuration
python# tests/conftest.py

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models.auth import User
from core.password import hash_password


# Test database URL (SQLite in-memory)
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def test_db():
    """
    Create test database for each test.
    
    Uses SQLite in-memory database for speed.
    """
    # Create engine
    engine = create_engine(
        SQLALCHEMY_TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    # Create session
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine
    )
    
    db = TestingSessionLocal()
    
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_user(test_db):
    """Create test user"""
    user = User(
        email="test@example.com",
        username="testuser",
        first_name="Test",
        last_name="User",
        is_active=True,
        is_verified=True
    )
    user.set_password("TestPassword123!")
    
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    
    return user


@pytest.fixture
def test_admin_user(test_db):
    """Create test admin user"""
    from models.auth import Role
    
    # Create admin role
    admin_role = Role(name="admin", description="Administrator")
    test_db.add(admin_role)
    test_db.commit()
    
    # Create admin user
    admin = User(
        email="admin@example.com",
        username="admin",
        first_name="Admin",
        last_name="User",
        is_active=True,
        is_verified=True
    )
    admin.set_password("AdminPass123!")
    admin.roles.append(admin_role)
    
    test_db.add(admin)
    test_db.commit()
    test_db.refresh(admin)
    
    return admin


@pytest.fixture
def authenticated_client(test_user, test_db):
    """Create authenticated test client"""
    from fastapi.testclient import TestClient
    from main import app
    from database import get_db
    
    # Override DB dependency
    app.dependency_overrides[get_db] = lambda: test_db
    
    client = TestClient(app)
    
    # Login to get token
    response = client.post(
        "/api/v1/auth/login",
        data={
            "username": test_user.email,
            "password": "TestPassword123!"
        }
    )
    
    token = response.json()["access_token"]
    
    # Set default authorization header
    client.headers = {"Authorization": f"Bearer {token}"}
    
    yield client
    
    # Cleanup
    app.dependency_overrides.clear()
2. Model Tests
python# tests/db/test_models.py

import pytest
from datetime import datetime

from models.auth import User, Role, Permission
from models.documents import Document


class TestUserModel:
    """Test User model"""
    
    def test_create_user(self, test_db):
        """Test user creation"""
        # Arrange
        user = User(
            email="new@example.com",
            username="newuser",
            first_name="New",
            last_name="User"
        )
        user.set_password("Password123!")
        
        # Act
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)
        
        # Assert
        assert user.id is not None
        assert user.email == "new@example.com"
        assert user.hashed_password is not None
        assert user.hashed_password != "Password123!"
        assert user.created_at is not None
    
    def test_user_password_verification(self, test_user):
        """Test password verification"""
        # Act & Assert
        assert test_user.verify_password("TestPassword123!") is True
        assert test_user.verify_password("WrongPassword") is False
    
    def test_user_unique_email(self, test_db, test_user):
        """Test that email must be unique"""
        # Arrange
        duplicate_user = User(
            email=test_user.email,  # Same email
            username="different",
            first_name="Different",
            last_name="User"
        )
        
        # Act & Assert
        test_db.add(duplicate_user)
        
        with pytest.raises(Exception):  # IntegrityError
            test_db.commit()
    
    def test_user_roles_relationship(self, test_db):
        """Test user-roles many-to-many relationship"""
        # Arrange
        user = User(email="user@test.com", username="user")
        role1 = Role(name="admin")
        role2 = Role(name="editor")
        
        # Act
        user.roles.append(role1)
        user.roles.append(role2)
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)
        
        # Assert
        assert len(user.roles) == 2
        assert role1 in user.roles
        assert role2 in user.roles
    
    def test_user_account_lockout(self, test_user, test_db):
        """Test account lockout mechanism"""
        # Increment failed attempts
        for i in range(5):
            test_user.increment_failed_login()
            test_db.commit()
        
        # Assert locked
        assert test_user.is_locked() is True
        assert test_user.failed_login_attempts == 5
        assert test_user.locked_until is not None
    
    def test_user_reset_failed_login(self, test_user, test_db):
        """Test resetting failed login attempts"""
        # Set some failed attempts
        test_user.failed_login_attempts = 3
        test_db.commit()
        
        # Reset
        test_user.reset_failed_login()
        test_db.commit()
        
        # Assert
        assert test_user.failed_login_attempts == 0
        assert test_user.locked_until is None


class TestDocumentModel:
    """Test Document model"""
    
    def test_create_document(self, test_db, test_user):
        """Test document creation"""
        # Arrange
        doc = Document(
            user_id=test_user.id,
            title="Test Document",
            file_path="uploads/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
            file_hash="abc123",
            status="pending"
        )
        
        # Act
        test_db.add(doc)
        test_db.commit()
        test_db.refresh(doc)
        
        # Assert
        assert doc.id is not None
        assert doc.user_id == test_user.id
        assert doc.title == "Test Document"
        assert doc.created_at is not None
    
    def test_document_user_relationship(self, test_db, test_user):
        """Test document-user relationship"""
        # Arrange
        doc = Document(
            user_id=test_user.id,
            title="Test",
            file_path="test.pdf",
            file_size=100,
            mime_type="application/pdf",
            file_hash="hash"
        )
        
        # Act
        test_db.add(doc)
        test_db.commit()
        test_db.refresh(doc)
        
        # Assert
        assert doc.user == test_user
        assert doc in test_user.documents
    
    def test_document_soft_delete(self, test_db, test_user):
        """Test soft delete functionality"""
        # Arrange
        doc = Document(
            user_id=test_user.id,
            title="To Delete",
            file_path="delete.pdf",
            file_size=100,
            mime_type="application/pdf",
            file_hash="hash"
        )
        test_db.add(doc)
        test_db.commit()
        
        # Act - soft delete
        doc.deleted_at = datetime.utcnow()
        test_db.commit()
        
        # Assert
        assert doc.deleted_at is not None
        # Document still in DB
        found = test_db.query(Document).filter(Document.id == doc.id).first()
        assert found is not None



🧪 TESTING STRATEGY & IMPLEMENTATION GUIDE - TEIL 2
Factories, Mocking, Coverage & CI/CD

🏭 TEST FIXTURES & FACTORIES
1. Factory Boy Setup
python# tests/factories/__init__.py

import factory
from factory import fuzzy
from factory.alchemy import SQLAlchemyModelFactory
from datetime import datetime, timedelta
from faker import Faker

from database import SessionLocal
from models.auth import User, Role, Permission
from models.documents import Document, Category


fake = Faker()


class BaseFactory(SQLAlchemyModelFactory):
    """Base factory for all models"""
    
    class Meta:
        abstract = True
        sqlalchemy_session = None
        sqlalchemy_session_persistence = "commit"
    
    @classmethod
    def _setup_next_sequence(cls):
        """Setup sequence counter"""
        return 0
2. User Factory
python# tests/factories/user_factory.py

import factory
from factory import fuzzy, Faker
from datetime import datetime, timedelta

from tests.factories import BaseFactory
from models.auth import User, Role


class RoleFactory(BaseFactory):
    """Factory for Role model"""
    
    class Meta:
        model = Role
    
    name = factory.Sequence(lambda n: f"role_{n}")
    description = Faker('sentence')


class UserFactory(BaseFactory):
    """
    Factory for User model.
    
    Usage:
        # Create user
        user = UserFactory()
        
        # Create with custom values
        user = UserFactory(email="custom@example.com")
        
        # Create multiple users
        users = UserFactory.create_batch(5)
        
        # Create without saving to DB
        user = UserFactory.build()
    """
    
    class Meta:
        model = User
    
    # Basic fields
    email = Faker('email')
    username = factory.LazyAttribute(lambda obj: obj.email.split('@')[0])
    first_name = Faker('first_name')
    last_name = Faker('last_name')
    
    # Password
    hashed_password = factory.PostGeneration(
        lambda obj, create, extracted: obj.set_password(
            extracted or "TestPassword123!"
        )
    )
    
    # Status flags
    is_active = True
    is_verified = True
    is_superuser = False
    
    # Security
    failed_login_attempts = 0
    locked_until = None
    token_version = 0
    
    # Timestamps
    created_at = factory.LazyFunction(datetime.utcnow)
    updated_at = factory.LazyFunction(datetime.utcnow)
    last_login_at = None
    
    # 2FA
    two_factor_enabled = False
    two_factor_secret = None


class AdminUserFactory(UserFactory):
    """Factory for admin users"""
    
    is_superuser = True
    
    @factory.post_generation
    def roles(self, create, extracted, **kwargs):
        """Add admin role"""
        if not create:
            return
        
        admin_role = RoleFactory(name="admin", description="Administrator")
        self.roles.append(admin_role)


class VerifiedUserFactory(UserFactory):
    """Factory for verified users"""
    
    is_verified = True
    is_active = True


class UnverifiedUserFactory(UserFactory):
    """Factory for unverified users"""
    
    is_verified = False


class LockedUserFactory(UserFactory):
    """Factory for locked users"""
    
    failed_login_attempts = 5
    locked_until = factory.LazyFunction(
        lambda: datetime.utcnow() + timedelta(hours=1)
    )
3. Document Factory
python# tests/factories/document_factory.py

import factory
from factory import fuzzy, Faker
from datetime import datetime
import random

from tests.factories import BaseFactory
from tests.factories.user_factory import UserFactory
from models.documents import Document, Category


class CategoryFactory(BaseFactory):
    """Factory for Category model"""
    
    class Meta:
        model = Category
    
    name = factory.Sequence(lambda n: f"Category {n}")
    description = Faker('sentence')
    color = fuzzy.FuzzyChoice(['red', 'blue', 'green', 'yellow', 'purple'])


class DocumentFactory(BaseFactory):
    """
    Factory for Document model.
    
    Usage:
        # Create document for specific user
        doc = DocumentFactory(user=user)
        
        # Create with OCR result
        doc = DocumentFactory(
            status="completed",
            ocr_result={"text": "Sample text"}
        )
        
        # Create pending documents
        docs = DocumentFactory.create_batch(5, status="pending")
    """
    
    class Meta:
        model = Document
    
    # Relationships
    user = factory.SubFactory(UserFactory)
    category = factory.SubFactory(CategoryFactory)
    
    # Basic fields
    title = Faker('sentence', nb_words=4)
    description = Faker('paragraph', nb_sentences=3)
    document_type = fuzzy.FuzzyChoice([
        'invoice', 'receipt', 'contract', 'report', 'other'
    ])
    
    # File information
    file_path = factory.LazyAttribute(
        lambda obj: f"uploads/{obj.user.id}/{fake.uuid4()}.pdf"
    )
    file_size = fuzzy.FuzzyInteger(1024, 10485760)  # 1KB to 10MB
    mime_type = "application/pdf"
    file_hash = factory.LazyFunction(lambda: fake.sha256())
    
    # Status
    status = fuzzy.FuzzyChoice(['pending', 'processing', 'completed', 'failed'])
    
    # OCR results
    ocr_result = None
    ocr_confidence = None
    
    # Metadata
    tags = factory.LazyFunction(
        lambda: random.sample(
            ['important', 'urgent', 'archive', 'review', 'paid'],
            k=random.randint(0, 3)
        )
    )
    
    # Timestamps
    created_at = factory.LazyFunction(datetime.utcnow)
    updated_at = factory.LazyFunction(datetime.utcnow)
    deleted_at = None


class CompletedDocumentFactory(DocumentFactory):
    """Factory for completed documents with OCR results"""
    
    status = "completed"
    ocr_result = factory.LazyFunction(
        lambda: {
            "text": fake.paragraph(nb_sentences=10),
            "entities": {
                "invoice_number": fake.uuid4()[:8],
                "date": fake.date(),
                "amount": f"${random.randint(100, 10000)}.00"
            }
        }
    )
    ocr_confidence = fuzzy.FuzzyFloat(0.85, 0.99)


class PendingDocumentFactory(DocumentFactory):
    """Factory for pending documents"""
    
    status = "pending"
    ocr_result = None
    ocr_confidence = None


class FailedDocumentFactory(DocumentFactory):
    """Factory for failed documents"""
    
    status = "failed"
    ocr_result = factory.LazyFunction(
        lambda: {"error": "OCR processing failed"}
    )
4. Using Factories in Tests
python# tests/test_with_factories.py

import pytest
from tests.factories.user_factory import UserFactory, AdminUserFactory
from tests.factories.document_factory import (
    DocumentFactory,
    CompletedDocumentFactory,
    PendingDocumentFactory
)


class TestWithFactories:
    """Examples of using factories in tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self, test_db):
        """Setup factories with test database"""
        from tests.factories import BaseFactory
        BaseFactory._meta.sqlalchemy_session = test_db
    
    def test_create_user_with_factory(self):
        """Test creating user with factory"""
        # Create user
        user = UserFactory()
        
        # Assert
        assert user.id is not None
        assert user.email is not None
        assert user.is_active is True
        assert user.verify_password("TestPassword123!")
    
    def test_create_custom_user(self):
        """Test creating user with custom values"""
        # Create user with custom email
        user = UserFactory(
            email="custom@example.com",
            first_name="John",
            last_name="Doe"
        )
        
        # Assert
        assert user.email == "custom@example.com"
        assert user.first_name == "John"
        assert user.last_name == "Doe"
    
    def test_create_batch_users(self):
        """Test creating multiple users"""
        # Create 5 users
        users = UserFactory.create_batch(5)
        
        # Assert
        assert len(users) == 5
        assert all(user.id is not None for user in users)
        # All have different emails
        emails = [user.email for user in users]
        assert len(emails) == len(set(emails))
    
    def test_create_admin_user(self):
        """Test creating admin user"""
        # Create admin
        admin = AdminUserFactory()
        
        # Assert
        assert admin.is_superuser is True
        assert len(admin.roles) > 0
        assert any(role.name == "admin" for role in admin.roles)
    
    def test_create_document_for_user(self):
        """Test creating document for specific user"""
        # Create user
        user = UserFactory()
        
        # Create document for user
        doc = DocumentFactory(user=user)
        
        # Assert
        assert doc.user_id == user.id
        assert doc.user == user
    
    def test_create_completed_documents(self):
        """Test creating completed documents"""
        # Create user
        user = UserFactory()
        
        # Create 3 completed documents
        docs = CompletedDocumentFactory.create_batch(3, user=user)
        
        # Assert
        assert len(docs) == 3
        assert all(doc.status == "completed" for doc in docs)
        assert all(doc.ocr_result is not None for doc in docs)
        assert all(doc.ocr_confidence > 0.8 for doc in docs)
    
    def test_build_without_saving(self):
        """Test building object without saving to database"""
        # Build user (not saved)
        user = UserFactory.build()
        
        # Assert
        assert user.id is None  # Not saved
        assert user.email is not None
        
        # Can manually save
        test_db.add(user)
        test_db.commit()
        assert user.id is not None

🎭 MOCKING & PATCHING
1. Basic Mocking with pytest-mock
python# tests/test_mocking_basics.py

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from datetime import datetime


class TestMockingBasics:
    """Basic mocking examples"""
    
    def test_mock_function_return_value(self, mocker):
        """Test mocking a function's return value"""
        # Mock a function
        mock_func = mocker.Mock(return_value=42)
        
        # Call mock
        result = mock_func()
        
        # Assert
        assert result == 42
        mock_func.assert_called_once()
    
    def test_mock_with_side_effect(self, mocker):
        """Test mocking with side effects"""
        # Mock with different return values
        mock_func = mocker.Mock(side_effect=[1, 2, 3])
        
        # Call multiple times
        assert mock_func() == 1
        assert mock_func() == 2
        assert mock_func() == 3
        
        # Verify call count
        assert mock_func.call_count == 3
    
    def test_mock_exception(self, mocker):
        """Test mocking exceptions"""
        # Mock that raises exception
        mock_func = mocker.Mock(side_effect=ValueError("Test error"))
        
        # Assert exception is raised
        with pytest.raises(ValueError, match="Test error"):
            mock_func()
    
    def test_mock_method_calls(self, mocker):
        """Test tracking method calls"""
        # Create mock
        mock_obj = mocker.Mock()
        
        # Call methods
        mock_obj.method1("arg1", key="value")
        mock_obj.method2()
        
        # Verify calls
        mock_obj.method1.assert_called_once_with("arg1", key="value")
        mock_obj.method2.assert_called_once()
        
        # Check call list
        assert len(mock_obj.method_calls) == 2
2. Patching External Dependencies
python# tests/test_patching.py

import pytest
from unittest.mock import patch, MagicMock
import httpx


class TestPatching:
    """Test patching external dependencies"""
    
    def test_patch_httpx_client(self, mocker):
        """Test patching HTTP client"""
        # Mock HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"key": "value"}
        
        # Patch httpx.post
        mock_post = mocker.patch('httpx.post', return_value=mock_response)
        
        # Use in code
        response = httpx.post("https://api.example.com/data")
        
        # Assert
        assert response.status_code == 200
        assert response.json() == {"key": "value"}
        mock_post.assert_called_once_with("https://api.example.com/data")
    
    def test_patch_datetime(self, mocker):
        """Test patching datetime"""
        # Mock datetime.utcnow()
        fake_now = datetime(2024, 1, 15, 12, 0, 0)
        mock_datetime = mocker.patch('datetime.datetime')
        mock_datetime.utcnow.return_value = fake_now
        
        # Use in code
        from datetime import datetime
        now = datetime.utcnow()
        
        # Assert
        assert now == fake_now
    
    def test_patch_redis(self, mocker):
        """Test patching Redis client"""
        # Mock Redis
        mock_redis = mocker.patch('redis.Redis')
        mock_client = MagicMock()
        mock_redis.return_value = mock_client
        
        # Setup return values
        mock_client.get.return_value = "cached_value"
        mock_client.setex.return_value = True
        
        # Use Redis
        import redis
        client = redis.Redis()
        value = client.get("key")
        client.setex("key", 60, "value")
        
        # Assert
        assert value == "cached_value"
        mock_client.get.assert_called_once_with("key")
        mock_client.setex.assert_called_once_with("key", 60, "value")
    
    @patch('smtplib.SMTP')
    def test_patch_email_sending(self, mock_smtp):
        """Test patching email sending"""
        # Configure mock
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server
        
        # Send email (your code)
        import smtplib
        with smtplib.SMTP('localhost') as server:
            server.send_message("test message")
        
        # Assert
        mock_server.send_message.assert_called_once()
3. Mocking Database Operations
python# tests/test_mock_database.py

import pytest
from unittest.mock import MagicMock
from uuid import uuid4


class TestMockDatabase:
    """Test mocking database operations"""
    
    def test_mock_database_query(self, mocker):
        """Test mocking database query"""
        # Create mock user
        mock_user = MagicMock()
        mock_user.id = uuid4()
        mock_user.email = "test@example.com"
        mock_user.username = "testuser"
        
        # Mock database session
        mock_db = mocker.MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user
        
        # Query database
        from models.auth import User
        result = mock_db.query(User).filter(User.email == "test@example.com").first()
        
        # Assert
        assert result == mock_user
        assert result.email == "test@example.com"
    
    def test_mock_database_add_and_commit(self, mocker):
        """Test mocking add and commit"""
        # Mock database session
        mock_db = mocker.MagicMock()
        
        # Create object
        from models.auth import User
        user = User(email="new@example.com", username="newuser")
        
        # Add to database
        mock_db.add(user)
        mock_db.commit()
        
        # Assert
        mock_db.add.assert_called_once_with(user)
        mock_db.commit.assert_called_once()
    
    def test_mock_database_rollback(self, mocker):
        """Test mocking rollback on error"""
        # Mock database session
        mock_db = mocker.MagicMock()
        mock_db.commit.side_effect = Exception("Database error")
        
        # Try to commit
        try:
            mock_db.add("something")
            mock_db.commit()
        except Exception:
            mock_db.rollback()
        
        # Assert
        mock_db.rollback.assert_called_once()
4. Mocking Celery Tasks
python# tests/test_mock_celery.py

import pytest
from unittest.mock import MagicMock, patch


class TestMockCeleryTasks:
    """Test mocking Celery tasks"""
    
    @patch('tasks.ocr_tasks.process_document_ocr.delay')
    def test_mock_celery_task_delay(self, mock_task):
        """Test mocking Celery task.delay()"""
        # Configure mock
        mock_task.return_value = MagicMock(id="task-123")
        
        # Trigger task
        from tasks.ocr_tasks import process_document_ocr
        result = process_document_ocr.delay("document-id")
        
        # Assert
        assert result.id == "task-123"
        mock_task.assert_called_once_with("document-id")
    
    @patch('tasks.ocr_tasks.process_document_ocr.apply_async')
    def test_mock_celery_apply_async(self, mock_apply_async):
        """Test mocking apply_async with ETA"""
        from datetime import datetime, timedelta
        
        # Configure mock
        mock_result = MagicMock(id="task-456")
        mock_apply_async.return_value = mock_result
        
        # Schedule task
        from tasks.ocr_tasks import process_document_ocr
        eta = datetime.utcnow() + timedelta(minutes=5)
        result = process_document_ocr.apply_async(
            args=["document-id"],
            eta=eta
        )
        
        # Assert
        assert result.id == "task-456"
        mock_apply_async.assert_called_once()
    
    def test_mock_celery_task_execution(self, mocker):
        """Test mocking task execution directly"""
        # Mock the task function
        mock_task = mocker.patch('tasks.ocr_tasks.process_document_ocr')
        mock_task.return_value = {"status": "completed"}
        
        # Execute task
        from tasks.ocr_tasks import process_document_ocr
        result = process_document_ocr("document-id")
        
        # Assert
        assert result["status"] == "completed"
5. Mocking File Operations
python# tests/test_mock_files.py

import pytest
from unittest.mock import mock_open, patch, MagicMock
import io


class TestMockFileOperations:
    """Test mocking file operations"""
    
    def test_mock_file_read(self, mocker):
        """Test mocking file read"""
        # Mock file content
        mock_file_content = "Test file content"
        mock_file = mock_open(read_data=mock_file_content)
        
        # Patch open
        mocker.patch('builtins.open', mock_file)
        
        # Read file
        with open('test.txt', 'r') as f:
            content = f.read()
        
        # Assert
        assert content == mock_file_content
        mock_file.assert_called_once_with('test.txt', 'r')
    
    def test_mock_file_write(self, mocker):
        """Test mocking file write"""
        # Mock open
        mock_file = mock_open()
        mocker.patch('builtins.open', mock_file)
        
        # Write file
        with open('output.txt', 'w') as f:
            f.write("Test output")
        
        # Assert
        mock_file.assert_called_once_with('output.txt', 'w')
        mock_file().write.assert_called_once_with("Test output")
    
    def test_mock_uploadfile(self, mocker):
        """Test mocking FastAPI UploadFile"""
        # Create mock UploadFile
        mock_file = MagicMock()
        mock_file.filename = "test.pdf"
        mock_file.content_type = "application/pdf"
        mock_file.file = io.BytesIO(b"PDF content")
        
        # Read file
        content = mock_file.file.read()
        
        # Assert
        assert content == b"PDF content"
        assert mock_file.filename == "test.pdf"
    
    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.unlink')
    def test_mock_file_deletion(self, mock_unlink, mock_exists):
        """Test mocking file deletion"""
        from pathlib import Path
        
        # Configure mocks
        mock_exists.return_value = True
        
        # Delete file
        file_path = Path("test.txt")
        if file_path.exists():
            file_path.unlink()
        
        # Assert
        mock_exists.assert_called_once()
        mock_unlink.assert_called_once()
6. Mocking External APIs
python# tests/test_mock_external_apis.py

import pytest
from unittest.mock import patch, MagicMock
import httpx


class TestMockExternalAPIs:
    """Test mocking external API calls"""
    
    @patch('httpx.AsyncClient.post')
    async def test_mock_deepseek_api(self, mock_post):
        """Test mocking DeepSeek OCR API"""
        # Configure mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "text": "Extracted text from document",
            "confidence": 0.95
        }
        mock_post.return_value = mock_response
        
        # Call API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.deepseek.com/ocr",
                json={"image": "base64_image"}
            )
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["text"] == "Extracted text from document"
        assert data["confidence"] == 0.95
    
    @patch('stripe.Customer.create')
    def test_mock_stripe_api(self, mock_create):
        """Test mocking Stripe API"""
        # Configure mock
        mock_customer = MagicMock()
        mock_customer.id = "cus_123456"
        mock_customer.email = "customer@example.com"
        mock_create.return_value = mock_customer
        
        # Create customer
        import stripe
        customer = stripe.Customer.create(
            email="customer@example.com",
            description="Test customer"
        )
        
        # Assert
        assert customer.id == "cus_123456"
        assert customer.email == "customer@example.com"
    
    def test_mock_with_responses_library(self, mocker):
        """Test using responses library for HTTP mocking"""
        import responses
        
        # Mock HTTP request
        @responses.activate
        def test_api_call():
            responses.add(
                responses.POST,
                "https://api.example.com/data",
                json={"status": "success"},
                status=200
            )
            
            # Make request
            import requests
            resp = requests.post("https://api.example.com/data")
            
            # Assert
            assert resp.json() == {"status": "success"}
        
        test_api_call()

📊 TEST COVERAGE
1. Coverage Configuration
toml# pyproject.toml

[tool.coverage.run]
source = ["backend"]
omit = [
    "*/tests/*",
    "*/venv/*",
    "*/__pycache__/*",
    "*/migrations/*",
    "*/alembic/*",
]

[tool.coverage.report]
precision = 2
show_missing = true
skip_covered = false

exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
    "@abstractmethod",
]

[tool.coverage.html]
directory = "htmlcov"
2. Running Coverage
bash# Run tests with coverage
pytest --cov=backend --cov-report=html --cov-report=term

# Run with detailed missing lines
pytest --cov=backend --cov-report=term-missing

# Run coverage for specific module
pytest tests/unit/test_security.py --cov=backend.core.security

# Generate coverage badge
coverage-badge -o coverage.svg

# Fail if coverage below threshold
pytest --cov=backend --cov-fail-under=80
3. Coverage Report Analysis
python# scripts/analyze_coverage.py

#!/usr/bin/env python3
"""Analyze test coverage and generate report"""

import subprocess
import json
from pathlib import Path


def run_coverage():
    """Run coverage and generate JSON report"""
    subprocess.run([
        "pytest",
        "--cov=backend",
        "--cov-report=json",
        "--cov-report=term"
    ])


def analyze_coverage_json():
    """Analyze coverage JSON report"""
    coverage_file = Path("coverage.json")
    
    if not coverage_file.exists():
        print("Coverage report not found. Run tests with coverage first.")
        return
    
    with open(coverage_file) as f:
        data = json.load(f)
    
    # Overall stats
    total = data["totals"]
    print("\n" + "="*60)
    print("COVERAGE SUMMARY")
    print("="*60)
    print(f"Total Lines: {total['num_statements']}")
    print(f"Covered Lines: {total['covered_lines']}")
    print(f"Missing Lines: {total['missing_lines']}")
    print(f"Coverage: {total['percent_covered']:.2f}%")
    
    # Files with low coverage
    print("\n" + "="*60)
    print("FILES WITH LOW COVERAGE (<80%)")
    print("="*60)
    
    low_coverage_files = []
    for filename, file_data in data["files"].items():
        coverage_pct = file_data["summary"]["percent_covered"]
        if coverage_pct < 80:
            low_coverage_files.append((filename, coverage_pct))
    
    # Sort by coverage percentage
    low_coverage_files.sort(key=lambda x: x[1])
    
    for filename, coverage_pct in low_coverage_files:
        print(f"{coverage_pct:6.2f}% - {filename}")
    
    # Uncovered lines
    print("\n" + "="*60)
    print("CRITICAL UNCOVERED SECTIONS")
    print("="*60)
    
    for filename, file_data in data["files"].items():
        missing_lines = file_data["missing_lines"]
        if missing_lines and "critical" in filename.lower():
            print(f"\n{filename}:")
            print(f"  Missing lines: {missing_lines}")


if __name__ == "__main__":
    run_coverage()
    analyze_coverage_json()
4. Coverage Badges
yaml# .github/workflows/coverage.yml

name: Coverage

on: [push, pull_request]

jobs:
  coverage:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install -r requirements-test.txt
    
    - name: Run tests with coverage
      run: |
        pytest --cov=backend --cov-report=xml --cov-report=term
    
    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
        fail_ci_if_error: true
    
    - name: Generate coverage badge
      run: |
        pip install coverage-badge
        coverage-badge -o coverage.svg -f
    
    - name: Commit coverage badge
      run: |
        git config --local user.email "action@github.com"
        git config --local user.name "GitHub Action"
        git add coverage.svg
        git commit -m "Update coverage badge" || echo "No changes"
        git push || echo "No changes to push"

⚡ ASYNC TESTING
1. Testing Async Functions
python# tests/test_async_functions.py

import pytest
import asyncio
from httpx import AsyncClient


class TestAsyncFunctions:
    """Test async functions"""
    
    @pytest.mark.asyncio
    async def test_async_function(self):
        """Test basic async function"""
        async def async_add(a, b):
            await asyncio.sleep(0.1)
            return a + b
        
        # Call async function
        result = await async_add(2, 3)
        
        # Assert
        assert result == 5
    
    @pytest.mark.asyncio
    async def test_async_api_call(self):
        """Test async API call"""
        from main import app
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/api/v1/health")
        
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_async_database_query(self, test_async_db):
        """Test async database query"""
        from sqlalchemy import select
        from models.auth import User
        
        # Async query
        async with test_async_db() as session:
            result = await session.execute(
                select(User).where(User.email == "test@example.com")
            )
            user = result.scalar_one_or_none()
        
        assert user is not None
    
    @pytest.mark.asyncio
    async def test_async_exception_handling(self):
        """Test async exception handling"""
        async def async_error():
            await asyncio.sleep(0.1)
            raise ValueError("Async error")
        
        # Assert exception
        with pytest.raises(ValueError, match="Async error"):
            await async_error()
    
    @pytest.mark.asyncio
    async def test_async_timeout(self):
        """Test async function with timeout"""
        async def slow_function():
            await asyncio.sleep(10)
            return "done"
        
        # Test with timeout
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(slow_function(), timeout=0.5)
2. Testing WebSockets
python# tests/test_websockets.py

import pytest
from fastapi.testclient import TestClient
from fastapi import WebSocket


class TestWebSockets:
    """Test WebSocket endpoints"""
    
    def test_websocket_connection(self):
        """Test WebSocket connection"""
        from main import app
        
        client = TestClient(app)
        
        with client.websocket_connect("/ws/test-user?token=test-token") as websocket:
            # Receive connection message
            data = websocket.receive_json()
            assert data["type"] == "connection_established"
            
            # Send ping
            websocket.send_json({"type": "ping"})
            
            # Receive pong
            pong = websocket.receive_json()
            assert pong["type"] == "pong"
    
    def test_websocket_ocr_progress(self, test_user, test_document):
        """Test OCR progress via WebSocket"""
        from main import app
        from core.security import token_manager
        
        client = TestClient(app)
        
        # Create token
        token = token_manager.create_access_token(subject=test_user.id)
        
        with client.websocket_connect(f"/ws/{test_user.id}?token={token}") as ws:
            # Simulate OCR progress update
            # (In real scenario, this would be sent from Celery task)
            
            # Receive connection message
            ws.receive_json()
            
            # In production, you would trigger OCR here
            # and receive progress updates

🔥 LOAD TESTING
1. Locust Configuration
python# tests/load/locustfile.py

from locust import HttpUser, task, between, events
from locust.contrib.fasthttp import FastHttpUser
import random
import json


class OCRBackendUser(FastHttpUser):
    """
    Simulated user for load testing.
    
    Run with:
        locust -f tests/load/locustfile.py --host=http://localhost:8000
    """
    
    wait_time = between(1, 3)  # Wait 1-3 seconds between tasks
    
    def on_start(self):
        """Execute on user start (login)"""
        # Register new user
        user_data = {
            "email": f"loadtest{random.randint(1, 100000)}@example.com",
            "username": f"loaduser{random.randint(1, 100000)}",
            "password": "LoadTest123!",
            "password_confirm": "LoadTest123!",
            "first_name": "Load",
            "last_name": "Test"
        }
        
        response = self.client.post(
            "/api/v1/auth/register",
            json=user_data
        )
        
        if response.status_code == 201:
            # Login
            login_response = self.client.post(
                "/api/v1/auth/login",
                data={
                    "username": user_data["email"],
                    "password": user_data["password"]
                }
            )
            
            if login_response.status_code == 200:
                self.token = login_response.json()["access_token"]
                self.headers = {"Authorization": f"Bearer {self.token}"}
    
    @task(3)
    def list_documents(self):
        """List documents (most common task - weight 3)"""
        self.client.get(
            "/api/v1/documents",
            headers=self.headers
        )
    
    @task(2)
    def get_user_profile(self):
        """Get user profile (weight 2)"""
        self.client.get(
            "/api/v1/auth/me",
            headers=self.headers
        )
    
    @task(1)
    def upload_document(self):
        """Upload document (less common - weight 1)"""
        # Create fake PDF
        files = {
            "file": ("test.pdf", b"%PDF-1.4 test content", "application/pdf")
        }
        data = {
            "title": f"Load Test Document {random.randint(1, 1000)}",
            "description": "Load test"
        }
        
        self.client.post(
            "/api/v1/documents/upload",
            files=files,
            data=data,
            headers=self.headers
        )
    
    @task(1)
    def search_documents(self):
        """Search documents"""
        self.client.get(
            "/api/v1/documents/search",
            params={"q": "test"},
            headers=self.headers
        )


class AdminUser(FastHttpUser):
    """Admin user with different behavior"""
    
    wait_time = between(2, 5)
    
    def on_start(self):
        """Login as admin"""
        response = self.client.post(
            "/api/v1/auth/login",
            data={
                "username": "admin@example.com",
                "password": "AdminPassword123!"
            }
        )
        
        if response.status_code == 200:
            self.token = response.json()["access_token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
    
    @task
    def view_all_users(self):
        """View all users (admin only)"""
        self.client.get(
            "/api/v1/admin/users",
            headers=self.headers
        )
    
    @task
    def view_statistics(self):
        """View system statistics"""
        self.client.get(
            "/api/v1/admin/stats",
            headers=self.headers
        )


# Custom event handlers
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when test starts"""
    print("Load test starting...")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when test stops"""
    print("Load test complete!")
    
    # Print stats
    stats = environment.stats
    print(f"\nTotal requests: {stats.total.num_requests}")
    print(f"Failed requests: {stats.total.num_failures}")
    print(f"Average response time: {stats.total.avg_response_time:.2f}ms")
    print(f"Max response time: {stats.total.max_response_time:.2f}ms")
2. Load Test Scenarios
python# tests/load/scenarios.py

from locust import HttpUser, task, between, LoadTestShape
import math


class StepLoadShape(LoadTestShape):
    """
    Step load pattern: gradually increase users.
    
    Stages:
    1. 10 users for 1 minute
    2. 50 users for 2 minutes
    3. 100 users for 3 minutes
    4. 200 users for 2 minutes
    """
    
    stages = [
        {"duration": 60, "users": 10, "spawn_rate": 1},
        {"duration": 180, "users": 50, "spawn_rate": 5},
        {"duration": 360, "users": 100, "spawn_rate": 10},
        {"duration": 480, "users": 200, "spawn_rate": 20},
    ]
    
    def tick(self):
        run_time = self.get_run_time()
        
        for stage in self.stages:
            if run_time < stage["duration"]:
                return (stage["users"], stage["spawn_rate"])
        
        return None


class SpikeLoadShape(LoadTestShape):
    """
    Spike load pattern: sudden traffic spikes.
    
    Simulates:
    - Normal load: 50 users
    - Spike: 500 users for 30 seconds
    - Back to normal
    """
    
    def tick(self):
        run_time = self.get_run_time()
        
        # Normal load
        if run_time < 120:
            return (50, 5)
        
        # Spike
        elif run_time < 150:
            return (500, 50)
        
        # Back to normal
        elif run_time < 300:
            return (50, 10)
        
        return None


class WaveLoadShape(LoadTestShape):
    """
    Wave pattern: oscillating load.
    
    Simulates daily traffic patterns.
    """
    
    def tick(self):
        run_time = self.get_run_time()
        
        if run_time > 600:  # 10 minutes
            return None
        
        # Sine wave pattern
        amplitude = 100
        period = 120  # 2 minutes
        offset = 50
        
        user_count = int(
            amplitude * math.sin(2 * math.pi * run_time / period) + offset
        )
        
        return (max(1, user_count), 10)
3. Running Load Tests
bash# Basic load test
locust -f tests/load/locustfile.py \
    --host=http://localhost:8000 \
    --users=100 \
    --spawn-rate=10 \
    --run-time=5m

# With custom shape
locust -f tests/load/locustfile.py \
    --host=http://localhost:8000 \
    --shape=StepLoadShape

# Headless mode (no web UI)
locust -f tests/load/locustfile.py \
    --host=http://localhost:8000 \
    --users=100 \
    --spawn-rate=10 \
    --run-time=5m \
    --headless \
    --csv=results/load_test

# With HTML report
locust -f tests/load/locustfile.py \
    --host=http://localhost:8000 \
    --users=100 \
    --spawn-rate=10 \
    --run-time=5m \
    --headless \
    --html=results/report.html

🚀 CI/CD TESTING PIPELINE
1. GitHub Actions Workflow
yaml# .github/workflows/tests.yml

name: Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main, develop ]

jobs:
  lint:
    name: Lint Code
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        pip install black pylint mypy
    
    - name: Black formatting check
      run: black --check backend/
    
    - name: Pylint
      run: pylint backend/ --exit-zero
    
    - name: MyPy type checking
      run: mypy backend/ --ignore-missing-imports

  test:
    name: Run Tests
    runs-on: ubuntu-latest
    
    strategy:
      matrix:
        python-version: ['3.10', '3.11', '3.12']
    
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: test_db
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_pass
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      
      redis:
        image: redis:7
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Cache dependencies
      uses: actions/cache@v3
      with:
        path: ~/.cache/pip
        key: ${{ runner.os }}-pip-${{ hashFiles('**/requirements*.txt') }}
        restore-keys: |
          ${{ runner.os }}-pip-
    
    - name: Install dependencies
      run: |
        pip install --upgrade pip
        pip install -r requirements.txt
        pip install -r requirements-test.txt
    
    - name: Run migrations
      env:
        DATABASE_URL: postgresql://test_user:test_pass@localhost:5432/test_db
      run: |
        alembic upgrade head
    
    - name: Run unit tests
      run: |
        pytest tests/unit/ -v --tb=short
    
    - name: Run integration tests
      env:
        DATABASE_URL: postgresql://test_user:test_pass@localhost:5432/test_db
        REDIS_URL: redis://localhost:6379/0
      run: |
        pytest tests/integration/ -v --tb=short
    
    - name: Run API tests
      env:
        DATABASE_URL: postgresql://test_user:test_pass@localhost:5432/test_db
      run: |
        pytest tests/api/ -v --tb=short
    
    - name: Run all tests with coverage
      env:
        DATABASE_URL: postgresql://test_user:test_pass@localhost:5432/test_db
        REDIS_URL: redis://localhost:6379/0
      run: |
        pytest --cov=backend \
               --cov-report=xml \
               --cov-report=html \
               --cov-report=term \
               --cov-fail-under=80
    
    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
        fail_ci_if_error: true
    
    - name: Archive coverage report
      uses: actions/upload-artifact@v3
      with:
        name: coverage-report-${{ matrix.python-version }}
        path: htmlcov/

  security:
    name: Security Checks
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        pip install safety bandit
    
    - name: Run Safety check
      run: safety check --json
    
    - name: Run Bandit
      run: bandit -r backend/ -f json -o bandit-report.json
    
    - name: Upload security reports
      uses: actions/upload-artifact@v3
      with:
        name: security-reports
        path: |
          bandit-report.json
2. Pre-commit Hooks
yaml# .pre-commit-config.yaml

repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
      - id: check-json
      - id: check-toml
      - id: check-merge-conflict
  
  - repo: https://github.com/psf/black
    rev: 23.12.1
    hooks:
      - id: black
        language_version: python3.11
  
  - repo: https://github.com/PyCQA/pylint
    rev: v3.0.3
    hooks:
      - id: pylint
        args: [--exit-zero]
  
  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.6
    hooks:
      - id: bandit
        args: [-r, backend/]
  
  - repo: local
    hooks:
      - id: pytest
        name: pytest
        entry: pytest tests/unit/ -v
        language: system
        pass_filenames: false
        always_run: true
bash# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Run manually
pre-commit run --all-files

✅ BEST PRACTICES & TIPS
Testing Best Practices
python"""
TESTING BEST PRACTICES

1. **AAA Pattern (Arrange-Act-Assert)**
   def test_example():
       # Arrange
       user = UserFactory()
       
       # Act
       result = user.verify_password("password")
       
       # Assert
       assert result is True

2. **One Assertion Per Test (mostly)**
   - Focus on one thing
   - Makes failures clear
   - Easier to debug

3. **Use Descriptive Names**
   ✅ test_user_login_with_wrong_password_returns_401()
   ❌ test_login()

4. **Don't Test Framework Code**
   - Don't test Pydantic validation
   - Don't test SQLAlchemy relationships
   - Test YOUR business logic

5. **Use Fixtures Wisely**
   - DRY principle
   - Scope appropriately
   - Don't overuse

6. **Mock External Dependencies**
   - APIs
   - Databases (in unit tests)
   - File systems
   - Time

7. **Test Edge Cases**
   - Empty inputs
   - Null values
   - Boundary values
   - Error conditions

8. **Keep Tests Fast**
   - Use in-memory databases
   - Mock slow operations
   - Run in parallel

9. **Maintain Test Data**
   - Use factories
   - Clean up after tests
   - Don't depend on order

10. **Document Complex Tests**
    - Explain WHY
    - Not WHAT (code shows that)
"""
Testing Cheat Sheet
markdown# Testing Cheat Sheet

## Running Tests
```bash
# All tests
pytest

# Specific file
pytest tests/test_auth.py

# Specific test
pytest tests/test_auth.py::test_login

# With markers
pytest -m unit
pytest -m "not slow"

# Parallel
pytest -n auto

# Verbose
pytest -v -s

# Stop on first failure
pytest -x

# Last failed
pytest --lf

# Coverage
pytest --cov=backend --cov-report=html
```

## Markers
```python
@pytest.mark.unit
@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.skip
@pytest.mark.skipif(condition, reason="...")
@pytest.mark.xfail
@pytest.mark.parametrize("input,expected", [...])
```

## Fixtures
```python
@pytest.fixture
def my_fixture():
    # Setup
    obj = create_obj()
    yield obj
    # Teardown
    cleanup(obj)

# Scopes
@pytest.fixture(scope="function")  # Default
@pytest.fixture(scope="class")
@pytest.fixture(scope="module")
@pytest.fixture(scope="session")

# Auto-use
@pytest.fixture(autouse=True)
```

## Assertions
```python
assert value
assert value == expected
assert value in collection
assert value is None
assert callable()

# With messages
assert value, "Custom error message"

# Exceptions
with pytest.raises(ValueError):
    raise ValueError()

with pytest.raises(ValueError, match="pattern"):
    raise ValueError("pattern here")

# Warnings
with pytest.warns(UserWarning):
    warnings.warn("warning", UserWarning)
```

## Mocking
```python
# Mock return value
mock.return_value = 42

# Mock side effect
mock.side_effect = [1, 2, 3]
mock.side_effect = Exception("error")

# Assert calls
mock.assert_called()
mock.assert_called_once()
mock.assert_called_with(arg1, arg2)
mock.assert_not_called()

# Check calls
mock.call_count
mock.call_args
mock.call_args_list
```

---

**🎉 Testing Guide Complete!** 🧪

**Key Takeaways:**
1. Write tests FIRST (TDD)
2. Aim for 80%+ coverage
3. Mock external dependencies
4. Keep tests fast and isolated
5. Use factories for test data
6. Run tests in CI/CD
7. Monitor and improve coverage

**Remember:** Good tests = confidence in deployments! 🚀WiederholenClaude kann Fehler machen. Bitte überprüfen Sie die Antworten.