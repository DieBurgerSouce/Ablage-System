# Security Policy

## Table of Contents

- [Supported Versions](#supported-versions)
- [Reporting a Vulnerability](#reporting-a-vulnerability)
- [Security Best Practices](#security-best-practices)
- [Security Features](#security-features)
- [Responsible Disclosure Policy](#responsible-disclosure-policy)
- [Security Updates](#security-updates)

## Supported Versions

We actively support and provide security updates for the following versions:

| Version | Supported          | End of Life    |
| ------- | ------------------ | -------------- |
| 1.0.x   | :white_check_mark: | TBD            |
| < 1.0   | :x:                | Not supported  |

**Note**: Only the latest minor and patch versions receive security updates. We strongly recommend keeping your installation up-to-date.

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security issue, please follow our responsible disclosure process:

### 🔒 Private Disclosure (Recommended)

**For security vulnerabilities, DO NOT open a public GitHub issue.**

Instead, please report vulnerabilities privately:

1. **Email**: Send details to `security@ablage-system.local`
2. **Subject Line**: `[SECURITY] Brief description of vulnerability`
3. **Include**:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if available)
   - Your contact information

### 📧 PGP Encryption (Optional)

For highly sensitive reports, you can encrypt your email using our PGP key:

```
-----BEGIN PGP PUBLIC KEY BLOCK-----
[PGP Key would be here in production]
-----END PGP PUBLIC KEY BLOCK-----
```

### ⏱️ Response Timeline

- **Initial Response**: Within 48 hours
- **Triage**: Within 5 business days
- **Fix Development**: Depends on severity (see below)
- **Disclosure**: Coordinated with reporter

### 🎯 Severity Levels

| Severity | Response Time | Example                                      |
| -------- | ------------- | -------------------------------------------- |
| Critical | 24-48 hours   | Remote code execution, authentication bypass |
| High     | 3-5 days      | SQL injection, privilege escalation          |
| Medium   | 1-2 weeks     | XSS, CSRF, information disclosure            |
| Low      | 2-4 weeks     | Minor information leakage, UI issues         |

## Security Best Practices

### Deployment Security

#### 🔐 Authentication & Authorization

```python
# Always use strong JWT secrets
JWT_SECRET = os.urandom(32).hex()  # Generate strong secret
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15  # Short-lived tokens
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Enable password requirements
PASSWORD_MIN_LENGTH = 12
PASSWORD_REQUIRE_UPPERCASE = True
PASSWORD_REQUIRE_LOWERCASE = True
PASSWORD_REQUIRE_DIGITS = True
PASSWORD_REQUIRE_SPECIAL = True
```

#### 🌐 Network Security

```yaml
# docker-compose.yml - Production settings
services:
  backend:
    environment:
      # Enable HTTPS only
      - FORCE_HTTPS=true
      - HSTS_MAX_AGE=31536000
      - HSTS_INCLUDE_SUBDOMAINS=true

      # Restrict CORS
      - CORS_ORIGINS=https://app.ablage-system.local
      - CORS_CREDENTIALS=true

      # Security headers
      - X_FRAME_OPTIONS=DENY
      - X_CONTENT_TYPE_OPTIONS=nosniff
      - X_XSS_PROTECTION=1; mode=block
      - REFERRER_POLICY=strict-origin-when-cross-origin
```

#### 🗄️ Database Security

```bash
# PostgreSQL security
export POSTGRES_PASSWORD=$(openssl rand -base64 32)
export POSTGRES_SSL_MODE=require

# Use connection pooling limits
export DB_POOL_SIZE=20
export DB_MAX_OVERFLOW=10
export DB_POOL_TIMEOUT=30
```

#### 🔑 Secret Management

**Using HashiCorp Vault** (Recommended):

```bash
# Store secrets in Vault
vault kv put secret/ablage-system/prod \
    jwt_secret="..." \
    db_password="..." \
    minio_secret_key="..." \
    redis_password="..."

# Application retrieves secrets at runtime
export VAULT_ADDR="http://localhost:8200"
export VAULT_TOKEN="your-vault-token"
```

**Environment Variables** (Minimum):

```bash
# Never commit .env to version control
# Use strong, unique secrets for each environment
JWT_SECRET=$(openssl rand -hex 32)
SECRET_KEY=$(openssl rand -hex 32)
DB_PASSWORD=$(openssl rand -base64 32)
REDIS_PASSWORD=$(openssl rand -base64 32)
MINIO_SECRET_KEY=$(openssl rand -base64 32)
```

#### 📁 File Upload Security

```python
# Restrict file types
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

# Scan uploaded files (optional but recommended)
# - Use ClamAV or similar antivirus
# - Validate file magic numbers, not just extensions
# - Strip metadata from images

# Isolate storage
UPLOAD_FOLDER = "/secure/uploads"  # Separate partition
QUARANTINE_FOLDER = "/secure/quarantine"
```

#### 🔒 TLS/SSL Configuration

```nginx
# Nginx configuration for production
server {
    listen 443 ssl http2;
    server_name app.ablage-system.local;

    # TLS 1.3 only
    ssl_protocols TLSv1.3;
    ssl_prefer_server_ciphers off;

    # Strong ciphers
    ssl_ciphers 'TLS_AES_128_GCM_SHA256:TLS_AES_256_GCM_SHA384';

    # HSTS
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;

    # Security headers
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';" always;
}
```

### Application Security

#### Input Validation

```python
# Use Pydantic for strict validation
from pydantic import BaseModel, Field, validator

class DocumentUpload(BaseModel):
    filename: str = Field(..., max_length=255)

    @validator('filename')
    def validate_filename(cls, v):
        # Prevent path traversal
        if '..' in v or '/' in v or '\\' in v:
            raise ValueError("Invalid filename")
        return v

# Sanitize user input
from bleach import clean

def sanitize_html(content: str) -> str:
    return clean(content, tags=[], strip=True)
```

#### SQL Injection Prevention

```python
# Always use parameterized queries (SQLAlchemy does this automatically)
# ✅ GOOD - Parameterized
result = await session.execute(
    select(Document).where(Document.id == doc_id)
)

# ❌ BAD - String interpolation (NEVER do this)
# result = await session.execute(f"SELECT * FROM documents WHERE id = '{doc_id}'")
```

#### XSS Prevention

```python
# Escape output in templates
from markupsafe import escape

def render_document_title(title: str) -> str:
    return escape(title)

# Set Content-Security-Policy header
CSP_HEADER = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'"
)
```

#### CSRF Protection

```python
# Enable CSRF protection for state-changing operations
from fastapi_csrf_protect import CsrfProtect

@app.post("/api/v1/documents/")
async def create_document(
    csrf_token: str = Depends(CsrfProtect.validate_csrf)
):
    # CSRF token validated automatically
    pass
```

### Operational Security

#### 🔍 Logging & Monitoring

```python
# DO NOT log sensitive data
import structlog

logger = structlog.get_logger()

# ✅ GOOD - No sensitive data
logger.info("document_uploaded", document_id=doc_id, file_size=size)

# ❌ BAD - Contains sensitive data
# logger.info(f"Document uploaded: {filename} with content: {content}")

# Log security events
logger.warning("failed_login_attempt", ip=request.client.host, username=username)
logger.error("permission_denied", user_id=user.id, resource=resource_id)
```

#### 🔄 Dependency Updates

```bash
# Regularly update dependencies
pip install --upgrade -r requirements.txt

# Check for vulnerabilities
pip install safety
safety check

# Automated dependency updates (GitHub Dependabot)
# See .github/dependabot.yml
```

#### 🗂️ Backup & Recovery

```bash
# Regular encrypted backups
# PostgreSQL
pg_dump -Fc ablage | gpg -e -r security@ablage-system.local > backup.sql.gpg

# MinIO
mc mirror --encrypt minio/documents s3://backup-bucket/

# Test restoration regularly
```

## Security Features

### Built-in Security Features

#### Authentication

- **JWT Tokens**: Short-lived access tokens (15 min), longer refresh tokens (7 days)
- **Password Hashing**: bcrypt with cost factor 12
- **Rate Limiting**:
  - Login: 5 attempts per 15 minutes per IP
  - API: 100 requests per minute per user
  - OCR: 10 documents per hour per user

#### Authorization

- **Role-Based Access Control (RBAC)**: Admin, User, Viewer roles
- **Document-Level Permissions**: Owner, shared users, organization access
- **API Key Management**: Optional API keys for programmatic access

#### Data Protection

- **Encryption at Rest**: MinIO server-side encryption (AES-256)
- **Encryption in Transit**: TLS 1.3 for all connections
- **Database Encryption**: PostgreSQL transparent data encryption (TDE) supported
- **GPU Memory Protection**: Secure memory wiping after processing

#### Audit Logging

All security-relevant events are logged:
- Authentication attempts (success/failure)
- Document access (view, download, delete)
- Permission changes
- Configuration changes
- Failed authorization attempts

### Security Scanning

#### Automated Scans

```bash
# Run security scans in CI/CD
bandit -r app/                    # Python security linter
safety check                      # Dependency vulnerabilities
trivy image ablage-backend:latest # Container image scanning
```

## Responsible Disclosure Policy

We follow a responsible disclosure policy:

1. **Report**: Securely report the vulnerability to us
2. **Acknowledge**: We acknowledge receipt within 48 hours
3. **Investigate**: We investigate and verify the issue
4. **Fix**: We develop and test a fix
5. **Coordinate**: We coordinate disclosure timing with you
6. **Disclose**: We publicly disclose after fix is deployed (typically 90 days)
7. **Credit**: We credit reporters in release notes (if desired)

### Hall of Fame

We recognize security researchers who responsibly disclose vulnerabilities:

- [Your Name Here] - [Brief description] - [Date]

## Security Updates

### How to Stay Informed

- **GitHub Security Advisories**: Watch this repository for security advisories
- **Mailing List**: Subscribe to security@ablage-system.local
- **Release Notes**: Check CHANGELOG.md for security fixes marked with 🔒

### Update Notification Process

For critical security updates:
1. Security advisory published (private)
2. Patch developed and tested
3. Advisory made public with patch
4. Email sent to security mailing list
5. 7-day grace period before exploit details disclosed

## Security Checklist

### Pre-Production Checklist

Before deploying to production, ensure:

- [ ] All secrets stored securely (Vault or encrypted environment variables)
- [ ] TLS/SSL certificates valid and properly configured
- [ ] Database passwords changed from defaults
- [ ] API rate limiting enabled
- [ ] CORS properly restricted
- [ ] Security headers configured
- [ ] Audit logging enabled and monitored
- [ ] Backups configured and tested
- [ ] Dependency vulnerabilities checked (`safety check`)
- [ ] Container images scanned (`trivy`)
- [ ] User password requirements enforced
- [ ] File upload restrictions in place
- [ ] GPU memory limits configured
- [ ] Monitoring and alerting configured

### Regular Maintenance

Monthly:
- [ ] Update all dependencies
- [ ] Review audit logs
- [ ] Test backup restoration
- [ ] Review access permissions
- [ ] Check for security advisories

Quarterly:
- [ ] Rotate secrets and API keys
- [ ] Security audit of new features
- [ ] Penetration testing (if applicable)
- [ ] Review and update security policies

## Additional Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CWE Top 25](https://cwe.mitre.org/top25/)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)
- [FastAPI Security Guide](https://fastapi.tiangolo.com/tutorial/security/)
- [Docker Security Best Practices](https://docs.docker.com/engine/security/)

## Contact

- **Security Team**: security@ablage-system.local
- **General Support**: support@ablage-system.local
- **GitHub Issues**: https://github.com/ablage-system/ablage-system-ocr/issues (non-security only)

---

**Last Updated**: 2024-11-24
**Version**: 1.0
**Maintained by**: Ablage-System Security Team
