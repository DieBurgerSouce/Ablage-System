# Ablage-System Authentication Documentation

## Overview

The Ablage-System OCR platform includes a complete JWT-based authentication and authorization system with the following features:

- **JWT Token Authentication** (Access + Refresh tokens)
- **Password Hashing** with bcrypt (cost factor 12)
- **Token Blacklisting** for logout functionality
- **Role-Based Access Control** (User, Superuser)
- **German Language Support** for all user-facing messages
- **Password Strength Validation**

## Architecture

### Components

1. **app/core/security.py** - Core security functions (JWT, password hashing)
2. **app/services/user_service.py** - User management service layer
3. **app/api/dependencies.py** - FastAPI dependencies for auth
4. **app/api/v1/auth.py** - Authentication API endpoints
5. **app/db/models.py** - User database model
6. **app/db/schemas.py** - Pydantic validation schemas

## API Endpoints

All authentication endpoints are under `/api/v1/auth`:

### 1. User Registration

**POST** `/api/v1/auth/register`

Register a new user account.

**Request Body:**
```json
{
  "email": "user@example.com",
  "username": "username",
  "password": "SecurePassword123!",
  "full_name": "Full Name",
  "preferred_language": "de"
}
```

**Password Requirements:**
- Minimum 8 characters
- At least one uppercase letter
- At least one lowercase letter
- At least one digit
- At least one special character (!@#$%^&*()_+-=[]{}|;:,.<>?)

**Response (201 Created):**
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "username": "username",
  "full_name": "Full Name",
  "preferred_language": "de",
  "is_active": true,
  "is_superuser": false,
  "preferred_ocr_backend": "auto",
  "daily_quota": 100,
  "created_at": "2025-11-26T10:00:00Z",
  "last_login": null
}
```

**Error Responses:**
- `400` - User already exists, weak password, or invalid data
- `422` - Validation error

### 2. User Login

**POST** `/api/v1/auth/login`

Authenticate user and receive JWT tokens.

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "SecurePassword123!"
}
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Token Expiration:**
- Access Token: 15 minutes
- Refresh Token: 7 days

**Error Responses:**
- `401` - Invalid email or password
- `403` - User account is deactivated

### 3. Token Refresh

**POST** `/api/v1/auth/refresh`

Get a new access token using a valid refresh token.

**Request Body:**
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Error Responses:**
- `401` - Invalid or expired refresh token

### 4. Logout

**POST** `/api/v1/auth/logout`

Logout user and blacklist refresh token.

**Headers:**
```
Authorization: Bearer <access_token>
```

**Request Body (Optional):**
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response (200 OK):**
```json
{
  "message": "Erfolgreich abgemeldet",
  "detail": "Bitte melden Sie sich erneut an, um auf geschützte Ressourcen zuzugreifen",
  "timestamp": "2025-11-26T10:00:00Z"
}
```

### 5. Get Current User

**GET** `/api/v1/auth/me`

Get information about the currently authenticated user.

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response (200 OK):**
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "username": "username",
  "full_name": "Full Name",
  "preferred_language": "de",
  "is_active": true,
  "is_superuser": false,
  "preferred_ocr_backend": "auto",
  "daily_quota": 100,
  "created_at": "2025-11-26T10:00:00Z",
  "last_login": "2025-11-26T10:30:00Z"
}
```

**Error Responses:**
- `401` - Invalid or expired token
- `403` - Missing authorization header

### 6. List Users (Admin Only)

**GET** `/api/v1/auth/users?skip=0&limit=100`

List all users in the system (superuser only).

**Headers:**
```
Authorization: Bearer <access_token>
```

**Query Parameters:**
- `skip` - Number of records to skip (default: 0)
- `limit` - Maximum records to return (default: 100)

**Response (200 OK):**
```json
[
  {
    "id": "uuid",
    "email": "user@example.com",
    "username": "username",
    ...
  }
]
```

**Error Responses:**
- `403` - Not a superuser

## Using Authentication in Your Code

### Protecting Endpoints

Use FastAPI dependencies to protect endpoints:

```python
from fastapi import APIRouter, Depends
from app.api.dependencies import get_current_active_user, get_current_superuser
from app.db.models import User

router = APIRouter()

@router.get("/protected")
async def protected_endpoint(
    current_user: User = Depends(get_current_active_user)
):
    """Requires authenticated user."""
    return {"message": f"Hello {current_user.username}"}

@router.delete("/admin/delete-user/{user_id}")
async def delete_user(
    user_id: str,
    admin: User = Depends(get_current_superuser)
):
    """Requires superuser (admin) privileges."""
    # Only admins can access this
    pass
```

### Optional Authentication

For endpoints that work with or without authentication:

```python
from app.api.dependencies import get_current_user_optional

@router.get("/public-or-private")
async def mixed_endpoint(
    user: Optional[User] = Depends(get_current_user_optional)
):
    if user:
        return {"message": f"Authenticated as {user.username}"}
    else:
        return {"message": "Anonymous access"}
```

## Client Implementation Examples

### Python (httpx)

```python
import httpx

BASE_URL = "http://localhost:8000"

# Register
async with httpx.AsyncClient() as client:
    response = await client.post(
        f"{BASE_URL}/api/v1/auth/register",
        json={
            "email": "user@example.com",
            "username": "user",
            "password": "SecurePass123!"
        }
    )
    print(response.json())

# Login
async with httpx.AsyncClient() as client:
    response = await client.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={
            "email": "user@example.com",
            "password": "SecurePass123!"
        }
    )
    tokens = response.json()
    access_token = tokens["access_token"]

# Access protected endpoint
async with httpx.AsyncClient() as client:
    response = await client.get(
        f"{BASE_URL}/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    print(response.json())
```

### JavaScript (fetch)

```javascript
const BASE_URL = "http://localhost:8000";

// Register
const register = async () => {
  const response = await fetch(`${BASE_URL}/api/v1/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: "user@example.com",
      username: "user",
      password: "SecurePass123!"
    })
  });
  return response.json();
};

// Login
const login = async () => {
  const response = await fetch(`${BASE_URL}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: "user@example.com",
      password: "SecurePass123!"
    })
  });
  const tokens = await response.json();
  localStorage.setItem("access_token", tokens.access_token);
  localStorage.setItem("refresh_token", tokens.refresh_token);
  return tokens;
};

// Get current user
const getCurrentUser = async () => {
  const accessToken = localStorage.getItem("access_token");
  const response = await fetch(`${BASE_URL}/api/v1/auth/me`, {
    headers: { "Authorization": `Bearer ${accessToken}` }
  });
  return response.json();
};

// Refresh token
const refreshToken = async () => {
  const refreshToken = localStorage.getItem("refresh_token");
  const response = await fetch(`${BASE_URL}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken })
  });
  const tokens = await response.json();
  localStorage.setItem("access_token", tokens.access_token);
  localStorage.setItem("refresh_token", tokens.refresh_token);
  return tokens;
};
```

### cURL

```bash
# Register
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "username": "user",
    "password": "SecurePass123!"
  }'

# Login
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePass123!"
  }'

# Get current user (replace TOKEN with actual access token)
curl -X GET "http://localhost:8000/api/v1/auth/me" \
  -H "Authorization: Bearer TOKEN"
```

## Security Features

### Password Security

- **Hashing Algorithm**: bcrypt with cost factor 12
- **Strength Validation**: Enforces strong passwords
- **No Plain Text Storage**: Passwords are never stored in plain text

### Token Security

- **Short-lived Access Tokens**: 15-minute expiration reduces attack window
- **Refresh Token Rotation**: New refresh token issued on each refresh
- **Token Blacklisting**: Prevents use of logged-out tokens
- **JTI (JWT ID)**: Unique identifier for each token enables blacklisting

### Database Security

- **Async Sessions**: Non-blocking database operations
- **Connection Pooling**: Efficient resource management
- **SQL Injection Protection**: SQLAlchemy ORM prevents SQL injection
- **Unique Constraints**: Email and username uniqueness enforced at DB level

## Configuration

Environment variables in `.env`:

```env
# Security - JWT Authentication
SECRET_KEY=your-secret-key-change-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5433/ablage_system
```

**IMPORTANT**: Generate a secure secret key for production:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Testing

Run authentication tests:

```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run tests
pytest tests/test_auth.py -v

# Run with coverage
pytest tests/test_auth.py --cov=app/api/v1/auth --cov=app/core/security
```

## Migration from Session-Based Auth

If migrating from session-based authentication:

1. **Token Storage**: Clients must store JWT tokens (localStorage/cookies)
2. **CORS Configuration**: Update CORS settings for token-based auth
3. **Authorization Header**: Use `Authorization: Bearer <token>` instead of cookies
4. **Token Refresh Logic**: Implement automatic token refresh before expiration
5. **Logout Flow**: Call logout endpoint and clear stored tokens

## Production Deployment Checklist

- [ ] Generate secure `SECRET_KEY` (32+ bytes)
- [ ] Set appropriate token expiration times
- [ ] Configure HTTPS/TLS for all endpoints
- [ ] Implement Redis-based token blacklist (replace in-memory)
- [ ] Enable rate limiting on auth endpoints
- [ ] Configure secure CORS origins (not `["*"]`)
- [ ] Set up monitoring for failed login attempts
- [ ] Implement account lockout after multiple failed attempts
- [ ] Add email verification for new registrations
- [ ] Set up password reset functionality
- [ ] Enable audit logging for authentication events
- [ ] Configure session timeout and auto-logout

## Troubleshooting

### Common Issues

**401 Unauthorized - Token Invalid**
- Token expired (access token: 15 min, refresh token: 7 days)
- Token blacklisted (after logout)
- Invalid SECRET_KEY or ALGORITHM

**403 Forbidden - Account Deactivated**
- User account `is_active = False`
- Contact admin to reactivate

**400 Bad Request - Password Validation**
- Password doesn't meet strength requirements
- Check error message for specific requirement

**Database Connection Errors**
- Verify DATABASE_URL is correct
- Ensure PostgreSQL is running
- Check database credentials

## German Error Messages

All error messages are in German for user-facing responses:

- `"Benutzer mit dieser E-Mail existiert bereits"` - User with this email already exists
- `"Benutzername ist bereits vergeben"` - Username is already taken
- `"Ungültige E-Mail-Adresse oder Passwort"` - Invalid email or password
- `"Benutzerkonto ist deaktiviert"` - User account is deactivated
- `"Token ungültig oder abgelaufen"` - Token invalid or expired
- `"Passwort muss mindestens 8 Zeichen lang sein"` - Password must be at least 8 characters
- And more...

## Support

For issues or questions:
1. Check this documentation
2. Review error messages (in German)
3. Check logs for detailed error information
4. Consult API documentation at `/docs`

---

**Version**: 1.0.0
**Last Updated**: 2025-11-26
**Author**: Ablage-System Development Team
