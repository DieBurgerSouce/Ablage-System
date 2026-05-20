# Authentication System - Quick Start Guide

## Installation

1. **Install dependencies:**

```bash
pip install -r requirements.txt
```

New dependencies added for authentication:
- `python-jose[cryptography]` - JWT token handling
- `passlib[bcrypt]` - Password hashing
- `bcrypt` - Bcrypt algorithm
- `python-multipart` - Form data parsing

2. **Set up environment variables:**

Copy `.env.example` to `.env` and update:

```bash
cp .env.example .env
```

Generate a secure secret key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Update `.env`:
```env
SECRET_KEY=<generated_secret_key>
DATABASE_URL=postgresql+asyncpg://ablage_admin:changeme@localhost:5433/ablage_system
```

3. **Run database migrations:**

```bash
alembic upgrade head
```

## First Steps

### 1. Start the API Server

```bash
python app/main.py
```

Or with uvicorn:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Access API Documentation

Open browser: http://localhost:8000/docs

You'll see the new authentication endpoints under the "Authentication" section.

### 3. Register Your First User

**Using cURL:**

```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "username": "admin",
    "password": "AdminPass123!",
    "full_name": "System Administrator",
    "preferred_language": "de"
  }'
```

**Using Python:**

```python
import httpx
import asyncio

async def register():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/v1/auth/register",
            json={
                "email": "admin@example.com",
                "username": "admin",
                "password": "AdminPass123!",
                "full_name": "System Administrator",
                "preferred_language": "de"
            }
        )
        print(response.json())

asyncio.run(register())
```

### 4. Login and Get Tokens

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "AdminPass123!"
  }'
```

Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

Save the `access_token` for authenticated requests.

### 5. Access Protected Endpoint

```bash
curl -X GET "http://localhost:8000/api/v1/auth/me" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

## Common Workflows

### Complete Authentication Flow

```python
import httpx
import asyncio

async def auth_flow():
    base_url = "http://localhost:8000"

    async with httpx.AsyncClient() as client:
        # 1. Register
        print("1. Registering user...")
        response = await client.post(
            f"{base_url}/api/v1/auth/register",
            json={
                "email": "user@example.com",
                "username": "user",
                "password": "UserPass123!"
            }
        )
        print(f"   Status: {response.status_code}")
        print(f"   User: {response.json()}")

        # 2. Login
        print("\n2. Logging in...")
        response = await client.post(
            f"{base_url}/api/v1/auth/login",
            json={
                "email": "user@example.com",
                "password": "UserPass123!"
            }
        )
        tokens = response.json()
        access_token = tokens["access_token"]
        refresh_token = tokens["refresh_token"]
        print(f"   Got tokens!")

        # 3. Get current user
        print("\n3. Getting current user info...")
        response = await client.get(
            f"{base_url}/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        print(f"   User: {response.json()['username']}")

        # 4. Refresh token
        print("\n4. Refreshing token...")
        response = await client.post(
            f"{base_url}/api/v1/auth/refresh",
            json={"refresh_token": refresh_token}
        )
        new_tokens = response.json()
        print(f"   Got new tokens!")

        # 5. Logout
        print("\n5. Logging out...")
        response = await client.post(
            f"{base_url}/api/v1/auth/logout",
            json={"refresh_token": new_tokens["refresh_token"]},
            headers={"Authorization": f"Bearer {new_tokens['access_token']}"}
        )
        print(f"   {response.json()['message']}")

asyncio.run(auth_flow())
```

### Protecting Your Endpoints

```python
from fastapi import APIRouter, Depends
from app.api.dependencies import get_current_active_user
from app.db.models import User

router = APIRouter()

@router.get("/my-documents")
async def get_my_documents(
    current_user: User = Depends(get_current_active_user)
):
    """
    This endpoint requires authentication.
    Only the logged-in user can access their own documents.
    """
    return {
        "user": current_user.username,
        "documents": []  # Fetch user's documents
    }
```

## Testing Authentication

Run the test suite:

```bash
# Install test dependencies if not already installed
pip install pytest pytest-asyncio httpx

# Run authentication tests
pytest tests/test_auth.py -v

# Run with verbose output
pytest tests/test_auth.py -v -s

# Run specific test
pytest tests/test_auth.py::test_login_success -v
```

## Swagger UI Testing

1. Go to http://localhost:8000/docs
2. Click on `/api/v1/auth/register` endpoint
3. Click "Try it out"
4. Fill in the request body:
   ```json
   {
     "email": "test@example.com",
     "username": "testuser",
     "password": "TestPass123!",
     "full_name": "Test User",
     "preferred_language": "de"
   }
   ```
5. Click "Execute"
6. Copy the user ID from the response
7. Try the `/api/v1/auth/login` endpoint with the same credentials
8. Copy the `access_token` from the login response
9. Click the "Authorize" button at the top of the page
10. Enter: `Bearer YOUR_ACCESS_TOKEN`
11. Click "Authorize"
12. Now you can test protected endpoints like `/api/v1/auth/me`

## Password Requirements

Passwords must meet the following criteria:

✓ At least 8 characters long
✓ Contains at least one uppercase letter (A-Z)
✓ Contains at least one lowercase letter (a-z)
✓ Contains at least one digit (0-9)
✓ Contains at least one special character (!@#$%^&*()_+-=[]{}|;:,.<>?)

**Valid Examples:**
- `SecurePass123!`
- `MyP@ssw0rd!`
- `Admin#2025`

**Invalid Examples:**
- `password` (no uppercase, digit, or special char)
- `PASSWORD123` (no lowercase or special char)
- `Pass1!` (too short)

## Token Expiration

- **Access Token**: 15 minutes (for API requests)
- **Refresh Token**: 7 days (to get new access tokens)

**Best Practice**: Implement automatic token refresh in your client:

```javascript
// JavaScript example
let accessToken = localStorage.getItem('access_token');
let refreshToken = localStorage.getItem('refresh_token');

async function apiRequest(url, options = {}) {
  // Try with current access token
  let response = await fetch(url, {
    ...options,
    headers: {
      ...options.headers,
      'Authorization': `Bearer ${accessToken}`
    }
  });

  // If token expired, refresh and retry
  if (response.status === 401) {
    const refreshResponse = await fetch('/api/v1/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken })
    });

    const tokens = await refreshResponse.json();
    accessToken = tokens.access_token;
    refreshToken = tokens.refresh_token;

    localStorage.setItem('access_token', accessToken);
    localStorage.setItem('refresh_token', refreshToken);

    // Retry original request
    response = await fetch(url, {
      ...options,
      headers: {
        ...options.headers,
        'Authorization': `Bearer ${accessToken}`
      }
    });
  }

  return response;
}
```

## Troubleshooting

### "User already exists"
- Email or username already registered
- Use different email/username or login with existing credentials

### "Invalid email or password"
- Check credentials
- Email is case-sensitive
- Password is case-sensitive

### "Token invalid or expired"
- Access token expired (15 min)
- Use refresh token to get new access token
- If refresh token also expired, login again

### "User account is deactivated"
- Account was deactivated by admin
- Contact system administrator

### Database connection errors
- Ensure PostgreSQL is running
- Check DATABASE_URL in .env
- Run `alembic upgrade head` to create tables

## Next Steps

1. **Protect your OCR endpoints**: Add authentication to document processing endpoints
2. **Implement rate limiting**: Prevent abuse with Redis-based rate limiting
3. **Add email verification**: Verify email addresses on registration
4. **Set up password reset**: Allow users to reset forgotten passwords
5. **Enable 2FA**: Add two-factor authentication for enhanced security
6. **Audit logging**: Track authentication events for security monitoring

## Resources

- Full Documentation: [AUTH_DOCUMENTATION.md](AUTH_DOCUMENTATION.md)
- API Reference: http://localhost:8000/docs
- User Model: `app/db/models.py`
- Security Functions: `app/core/security.py`
- Auth Endpoints: `app/api/v1/auth.py`

---

**Quick Reference Commands:**

```bash
# Start server
python app/main.py

# Run tests
pytest tests/test_auth.py -v

# Generate secret key
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Check API docs
open http://localhost:8000/docs
```
