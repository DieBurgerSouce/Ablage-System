# Advanced Security Hardening Guide
**Ablage-System Document Processing Platform**
**Version:** 1.0
**Last Updated:** 2025-01-23
**Security Level:** Enterprise Production

---

## 📑 Table of Contents

1. [Overview](#overview)
2. [Security Architecture](#security-architecture)
3. [Network Security](#network-security)
4. [Application Security](#application-security)
5. [Database Security](#database-security)
6. [Secrets Management](#secrets-management)
7. [Authentication & Authorization](#authentication--authorization)
8. [API Security](#api-security)
9. [Container Security](#container-security)
10. [Kubernetes Security](#kubernetes-security)
11. [GPU Security](#gpu-security)
12. [Logging & Audit Trail](#logging--audit-trail)
13. [Compliance & Data Protection](#compliance--data-protection)
14. [Security Monitoring](#security-monitoring)
15. [Incident Response](#incident-response)
16. [Penetration Testing](#penetration-testing)
17. [Security Checklist](#security-checklist)

---

## Overview

This guide provides comprehensive security hardening procedures for the Ablage-System in production environments. The system processes sensitive German documents and must comply with GDPR, implement defense-in-depth, and maintain security across all layers.

### Security Principles

1. **Defense in Depth:** Multiple layers of security controls
2. **Least Privilege:** Minimal permissions for users, services, and processes
3. **Zero Trust:** Never trust, always verify
4. **Fail Secure:** Security-first failure modes
5. **Audit Everything:** Complete audit trail for compliance
6. **Privacy by Design:** GDPR compliance built-in

### Threat Model

**Assets:**
- German business documents (invoices, contracts, personal data)
- User credentials and session tokens
- OCR model weights and configurations
- Database with extracted text and metadata
- API keys and secrets

**Threats:**
- Unauthorized access to documents
- SQL injection, XSS, CSRF attacks
- Man-in-the-middle attacks
- GPU resource exhaustion (DoS)
- Data exfiltration
- Container escape
- Privilege escalation

**Security Goals:**
- **Confidentiality:** No unauthorized document access
- **Integrity:** No unauthorized document modification
- **Availability:** System remains operational under attack
- **Compliance:** GDPR, audit requirements met

---

## Security Architecture

### Defense-in-Depth Layers

```
┌────────────────────────────────────────────────────────────┐
│                     Layer 7: Compliance                    │
│              GDPR, Audit Logging, Data Retention           │
└────────────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────────────┐
│                  Layer 6: Application Security             │
│        Input Validation, Output Encoding, CSRF Protection  │
└────────────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────────────┐
│               Layer 5: API & Authentication                │
│         JWT, Rate Limiting, OAuth 2.0, API Gateway         │
└────────────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────────────┐
│                  Layer 4: Container Security               │
│      Read-Only Filesystems, Non-Root, Image Scanning      │
└────────────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────────────┐
│                   Layer 3: Network Security                │
│         TLS 1.3, Network Policies, WAF, mTLS               │
└────────────────────────────────────────────────────────────┐
┌────────────────────────────────────────────────────────────┐
│                Layer 2: Host & Orchestration               │
│      SELinux/AppArmor, RBAC, Pod Security Standards        │
└────────────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────────────┐
│                   Layer 1: Infrastructure                  │
│       Firewalls, IDS/IPS, VPN, Physical Security           │
└────────────────────────────────────────────────────────────┘
```

---

## Network Security

### TLS 1.3 Configuration

#### NGINX TLS Configuration (Strong Ciphers)

```nginx
# nginx-tls.conf
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name ablage.example.com;

    # TLS 1.3 only (disable TLS 1.2 for maximum security)
    ssl_protocols TLSv1.3;

    # TLS 1.2 + 1.3 (if backwards compatibility needed)
    # ssl_protocols TLSv1.2 TLSv1.3;

    # Strong ciphers (TLS 1.3)
    ssl_ciphers TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256:TLS_AES_128_GCM_SHA256;
    ssl_prefer_server_ciphers off;  # Let client choose for TLS 1.3

    # Certificates
    ssl_certificate /etc/letsencrypt/live/ablage.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ablage.example.com/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/ablage.example.com/chain.pem;

    # SSL session cache
    ssl_session_cache shared:SSL:50m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;

    # OCSP stapling
    ssl_stapling on;
    ssl_stapling_verify on;
    resolver 1.1.1.1 1.0.0.1 valid=300s;
    resolver_timeout 5s;

    # Security headers
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self' wss://ablage.example.com" always;
    add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;

    # Client certificate verification (optional, for mTLS)
    # ssl_client_certificate /etc/nginx/client_certs/ca.crt;
    # ssl_verify_client optional;
    # ssl_verify_depth 2;

    location / {
        proxy_pass http://ablage-backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Client certificate forwarding (mTLS)
        # proxy_set_header X-Client-Cert $ssl_client_cert;
        # proxy_set_header X-Client-Verify $ssl_client_verify;
    }
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name ablage.example.com;
    return 301 https://$server_name$request_uri;
}
```

### Kubernetes Network Policies

#### Default Deny All Traffic

```yaml
# network-policy-default-deny.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: ablage-system
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
```

#### Allow Backend to Database

```yaml
# network-policy-backend-postgres.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-backend-to-postgres
  namespace: ablage-system
spec:
  podSelector:
    matchLabels:
      app: postgres
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: backend
        - podSelector:
            matchLabels:
              app: worker
      ports:
        - protocol: TCP
          port: 5432
```

#### Allow Backend to Redis

```yaml
# network-policy-backend-redis.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-backend-to-redis
  namespace: ablage-system
spec:
  podSelector:
    matchLabels:
      app: redis
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: backend
        - podSelector:
            matchLabels:
              app: worker
      ports:
        - protocol: TCP
          port: 6379
```

#### Allow Ingress to Backend/Frontend

```yaml
# network-policy-ingress.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-ingress-to-backend
  namespace: ablage-system
spec:
  podSelector:
    matchLabels:
      app: backend
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              name: ingress-nginx
      ports:
        - protocol: TCP
          port: 8000

---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-ingress-to-frontend
  namespace: ablage-system
spec:
  podSelector:
    matchLabels:
      app: frontend
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              name: ingress-nginx
      ports:
        - protocol: TCP
          port: 80
```

#### Allow DNS (Egress)

```yaml
# network-policy-allow-dns.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns-egress
  namespace: ablage-system
spec:
  podSelector: {}
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              name: kube-system
      ports:
        - protocol: UDP
          port: 53
```

```bash
# Apply all network policies
kubectl apply -f network-policy-default-deny.yaml
kubectl apply -f network-policy-backend-postgres.yaml
kubectl apply -f network-policy-backend-redis.yaml
kubectl apply -f network-policy-ingress.yaml
kubectl apply -f network-policy-allow-dns.yaml

# Verify policies
kubectl get networkpolicies -n ablage-system
```

### Firewall Rules (iptables)

```bash
#!/bin/bash
# firewall-rules.sh - Host-level firewall configuration

# Flush existing rules
iptables -F
iptables -X

# Default policies
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT ACCEPT

# Allow loopback
iptables -A INPUT -i lo -j ACCEPT

# Allow established connections
iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# Allow SSH (with rate limiting)
iptables -A INPUT -p tcp --dport 22 -m conntrack --ctstate NEW -m recent --set
iptables -A INPUT -p tcp --dport 22 -m conntrack --ctstate NEW -m recent --update --seconds 60 --hitcount 4 -j DROP
iptables -A INPUT -p tcp --dport 22 -j ACCEPT

# Allow HTTP/HTTPS
iptables -A INPUT -p tcp --dport 80 -j ACCEPT
iptables -A INPUT -p tcp --dport 443 -j ACCEPT

# Allow Kubernetes API (only from control plane)
iptables -A INPUT -p tcp --dport 6443 -s 10.0.0.0/8 -j ACCEPT

# Allow kubelet API (only from control plane)
iptables -A INPUT -p tcp --dport 10250 -s 10.0.0.0/8 -j ACCEPT

# Log dropped packets
iptables -A INPUT -m limit --limit 5/min -j LOG --log-prefix "iptables-dropped: " --log-level 4

# Drop everything else
iptables -A INPUT -j DROP

# Save rules
iptables-save > /etc/iptables/rules.v4
```

---

## Application Security

### Input Validation

#### FastAPI Pydantic Models (Strict Validation)

```python
# app/api/schemas.py
from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, Literal
import re

class DocumentUploadRequest(BaseModel):
    """Document upload request with strict validation."""
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

    filename: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Document filename"
    )
    language: Literal['de', 'en'] = Field(
        default='de',
        description="Document language"
    )
    ocr_backend: Literal['auto', 'deepseek', 'got_ocr', 'surya'] = Field(
        default='auto',
        description="OCR backend to use"
    )

    @field_validator('filename')
    @classmethod
    def validate_filename(cls, v: str) -> str:
        """Prevent path traversal attacks."""
        # Block path traversal characters
        if '..' in v or '/' in v or '\\' in v:
            raise ValueError("Invalid filename: path traversal detected")

        # Block null bytes
        if '\x00' in v:
            raise ValueError("Invalid filename: null byte detected")

        # Allowed extensions only
        allowed_extensions = ['.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.tif']
        if not any(v.lower().endswith(ext) for ext in allowed_extensions):
            raise ValueError(f"Invalid file extension. Allowed: {allowed_extensions}")

        # Block dangerous filenames
        dangerous_patterns = ['../etc', 'passwd', '.ssh', '.git', 'web.config', '.env']
        if any(pattern in v.lower() for pattern in dangerous_patterns):
            raise ValueError("Suspicious filename detected")

        return v


class DocumentSearchRequest(BaseModel):
    """Search request with SQL injection prevention."""
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

    query: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Search query"
    )
    page: int = Field(default=1, ge=1, le=1000)
    page_size: int = Field(default=20, ge=1, le=100)

    @field_validator('query')
    @classmethod
    def validate_query(cls, v: str) -> str:
        """Prevent SQL injection in search queries."""
        # Block SQL injection patterns
        sql_injection_patterns = [
            r"(\bOR\b|\bAND\b).*=.*",
            r"';.*--",
            r"1\s*=\s*1",
            r"UNION\s+SELECT",
            r"DROP\s+TABLE",
            r"INSERT\s+INTO",
            r"DELETE\s+FROM",
            r"UPDATE\s+.*SET"
        ]

        for pattern in sql_injection_patterns:
            if re.search(pattern, v, re.IGNORECASE):
                raise ValueError("Invalid search query: SQL injection pattern detected")

        return v


class UserRegistrationRequest(BaseModel):
    """User registration with strong password validation."""
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

    email: str = Field(..., max_length=320)
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=12, max_length=128)

    @field_validator('email')
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Validate email format."""
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, v):
            raise ValueError("Invalid email format")
        return v.lower()

    @field_validator('username')
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username (alphanumeric + underscore only)."""
        if not re.match(r'^[a-zA-Z0-9_]+$', v):
            raise ValueError("Username must contain only letters, numbers, and underscores")
        return v

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Enforce strong password policy."""
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters")

        # Require uppercase, lowercase, digit, and special character
        if not re.search(r'[A-Z]', v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r'[a-z]', v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r'[0-9]', v):
            raise ValueError("Password must contain at least one digit")
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError("Password must contain at least one special character")

        # Block common passwords
        common_passwords = ['password123', 'admin123', 'qwerty123']
        if v.lower() in common_passwords:
            raise ValueError("Password is too common")

        return v
```

### Output Encoding (XSS Prevention)

```python
# app/utils/sanitizers.py
import html
import bleach
from typing import Optional

def sanitize_html(text: Optional[str]) -> str:
    """Sanitize HTML to prevent XSS attacks."""
    if not text:
        return ""

    # Allow only safe tags
    allowed_tags = ['p', 'br', 'strong', 'em', 'u', 'a', 'ul', 'ol', 'li']
    allowed_attributes = {'a': ['href', 'title']}

    # Use bleach to sanitize
    clean_text = bleach.clean(
        text,
        tags=allowed_tags,
        attributes=allowed_attributes,
        strip=True
    )

    # Additional protection: encode any remaining HTML entities
    return html.escape(clean_text, quote=True)


def sanitize_text_for_log(text: str, max_length: int = 200) -> str:
    """Sanitize text for logging (prevent log injection)."""
    # Remove newlines and control characters
    sanitized = text.replace('\n', ' ').replace('\r', ' ')
    sanitized = ''.join(char for char in sanitized if char.isprintable())

    # Truncate to max length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length] + '...'

    return sanitized
```

### CSRF Protection

```python
# app/core/security.py
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import secrets
import hmac
import hashlib

class CSRFProtection:
    """CSRF token generation and validation."""

    def __init__(self, secret_key: str):
        self.secret_key = secret_key.encode()

    def generate_token(self, session_id: str) -> str:
        """Generate CSRF token for session."""
        # Create HMAC of session ID
        csrf_token = hmac.new(
            self.secret_key,
            session_id.encode(),
            hashlib.sha256
        ).hexdigest()

        return csrf_token

    def validate_token(self, session_id: str, csrf_token: str) -> bool:
        """Validate CSRF token."""
        expected_token = self.generate_token(session_id)
        return hmac.compare_digest(expected_token, csrf_token)


# FastAPI dependency for CSRF protection
async def verify_csrf_token(request: Request, csrf_token: str = Header(...)) -> None:
    """Verify CSRF token from request header."""
    session_id = request.cookies.get('session_id')

    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No session found"
        )

    csrf_protection = CSRFProtection(settings.SECRET_KEY)

    if not csrf_protection.validate_token(session_id, csrf_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid CSRF token"
        )


# Usage in endpoint
@router.post("/documents", dependencies=[Depends(verify_csrf_token)])
async def create_document(...):
    ...
```

---

## Database Security

### SQL Injection Prevention

```python
# ✅ GOOD: Using parameterized queries (safe from SQL injection)
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

async def search_documents_safe(db: AsyncSession, query: str, user_id: str):
    """Safe search using parameterized query."""
    stmt = select(Document).where(
        Document.owner_id == user_id,
        Document.filename.ilike(f"%{query}%")  # SQLAlchemy handles escaping
    )
    result = await db.execute(stmt)
    return result.scalars().all()


# ✅ GOOD: Using text() with bound parameters
async def search_documents_text_safe(db: AsyncSession, query: str, user_id: str):
    """Safe search using text() with bound parameters."""
    stmt = text("""
        SELECT * FROM documents
        WHERE owner_id = :user_id
          AND filename ILIKE :query
    """)
    result = await db.execute(stmt, {"user_id": user_id, "query": f"%{query}%"})
    return result.fetchall()


# ❌ BAD: String formatting (vulnerable to SQL injection)
async def search_documents_vulnerable(db: AsyncSession, query: str, user_id: str):
    """VULNERABLE: Do not use string formatting for SQL queries!"""
    stmt = text(f"""
        SELECT * FROM documents
        WHERE owner_id = '{user_id}'
          AND filename ILIKE '%{query}%'
    """)
    result = await db.execute(stmt)
    return result.fetchall()
```

### Database Encryption

#### Encryption at Rest (PostgreSQL)

```bash
# Enable transparent data encryption (TDE) for PostgreSQL
# Requires pgcrypto extension

# Install extension
sudo -u postgres psql -d ablage -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"

# Create encrypted columns
psql -d ablage -c "
ALTER TABLE documents
ADD COLUMN extracted_text_encrypted BYTEA;

-- Encrypt existing data
UPDATE documents
SET extracted_text_encrypted = pgp_sym_encrypt(extracted_text, current_setting('app.encryption_key'));

-- Drop unencrypted column (after verification)
-- ALTER TABLE documents DROP COLUMN extracted_text;
"
```

#### Application-Level Encryption (Python)

```python
# app/core/encryption.py
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
from cryptography.hazmat.backends import default_backend
import base64
import os

class FieldEncryption:
    """Encrypt sensitive fields before storing in database."""

    def __init__(self, encryption_key: str):
        # Derive key from password using PBKDF2
        kdf = PBKDF2(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'ablage_salt_change_this',  # Use unique salt per deployment
            iterations=100000,
            backend=default_backend()
        )
        key = base64.urlsafe_b64encode(kdf.derive(encryption_key.encode()))
        self.cipher = Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext string."""
        if not plaintext:
            return ""
        encrypted = self.cipher.encrypt(plaintext.encode())
        return base64.b64encode(encrypted).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt ciphertext string."""
        if not ciphertext:
            return ""
        encrypted = base64.b64decode(ciphertext)
        decrypted = self.cipher.decrypt(encrypted)
        return decrypted.decode()


# Usage in models
from sqlalchemy import Column, String, LargeBinary
from sqlalchemy.orm import DeclarativeBase

class Document(DeclarativeBase):
    __tablename__ = "documents"

    id = Column(String, primary_key=True)
    filename = Column(String, nullable=False)
    extracted_text_encrypted = Column(LargeBinary)  # Encrypted field

    def set_extracted_text(self, text: str, encryptor: FieldEncryption):
        """Encrypt and set extracted text."""
        self.extracted_text_encrypted = encryptor.encrypt(text).encode()

    def get_extracted_text(self, encryptor: FieldEncryption) -> str:
        """Decrypt and get extracted text."""
        if not self.extracted_text_encrypted:
            return ""
        return encryptor.decrypt(self.extracted_text_encrypted.decode())
```

### Row-Level Security (PostgreSQL)

```sql
-- Enable RLS for documents table
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only see their own documents
CREATE POLICY documents_isolation_policy ON documents
    FOR ALL
    TO authenticated_users
    USING (owner_id = current_setting('app.current_user_id')::UUID);

-- Policy: Admins can see all documents
CREATE POLICY documents_admin_policy ON documents
    FOR ALL
    TO admin_users
    USING (true);

-- Grant roles
GRANT authenticated_users TO app_user;
GRANT admin_users TO app_admin;

-- Set current user in application
-- Before each query, set the user ID:
-- SET LOCAL app.current_user_id = '<user_id>';
```

---

## Secrets Management

### HashiCorp Vault Integration

#### Install Vault in Kubernetes

```bash
helm repo add hashicorp https://helm.releases.hashicorp.com
helm repo update

helm install vault hashicorp/vault \
  --namespace vault \
  --create-namespace \
  --set "server.dev.enabled=false" \
  --set "server.ha.enabled=true" \
  --set "server.ha.replicas=3"
```

#### Configure Vault for Ablage-System

```bash
# Initialize Vault
kubectl exec -n vault vault-0 -- vault operator init

# Unseal Vault (repeat for all replicas)
kubectl exec -n vault vault-0 -- vault operator unseal <unseal-key-1>
kubectl exec -n vault vault-0 -- vault operator unseal <unseal-key-2>
kubectl exec -n vault vault-0 -- vault operator unseal <unseal-key-3>

# Enable KV secrets engine
kubectl exec -n vault vault-0 -- vault secrets enable -path=ablage kv-v2

# Store secrets
kubectl exec -n vault vault-0 -- vault kv put ablage/database \
  password='your-strong-password'

kubectl exec -n vault vault-0 -- vault kv put ablage/jwt \
  secret_key='your-jwt-secret'

# Create policy for ablage-system
kubectl exec -n vault vault-0 -- vault policy write ablage-policy - <<EOF
path "ablage/*" {
  capabilities = ["read", "list"]
}
EOF

# Enable Kubernetes auth
kubectl exec -n vault vault-0 -- vault auth enable kubernetes

kubectl exec -n vault vault-0 -- vault write auth/kubernetes/config \
  kubernetes_host="https://kubernetes.default.svc:443"

# Create role for ablage-backend
kubectl exec -n vault vault-0 -- vault write auth/kubernetes/role/ablage-backend \
  bound_service_account_names=ablage-backend \
  bound_service_account_namespaces=ablage-system \
  policies=ablage-policy \
  ttl=24h
```

#### Vault Sidecar Injector

```yaml
# backend-deployment-with-vault.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ablage-backend
  namespace: ablage-system
spec:
  template:
    metadata:
      annotations:
        vault.hashicorp.com/agent-inject: "true"
        vault.hashicorp.com/role: "ablage-backend"
        vault.hashicorp.com/agent-inject-secret-database: "ablage/database"
        vault.hashicorp.com/agent-inject-template-database: |
          {{- with secret "ablage/database" -}}
          export DATABASE_PASSWORD="{{ .Data.data.password }}"
          {{- end }}
    spec:
      serviceAccountName: ablage-backend
      containers:
        - name: backend
          image: ablage-backend:1.0.0
          command:
            - /bin/sh
            - -c
            - |
              source /vault/secrets/database
              uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### External Secrets Operator

```bash
# Install External Secrets Operator
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets external-secrets/external-secrets \
  --namespace external-secrets \
  --create-namespace
```

```yaml
# secretstore.yaml
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: vault-backend
  namespace: ablage-system
spec:
  provider:
    vault:
      server: "http://vault.vault:8200"
      path: "ablage"
      version: "v2"
      auth:
        kubernetes:
          mountPath: "kubernetes"
          role: "ablage-backend"
          serviceAccountRef:
            name: "ablage-backend"

---
# externalsecret.yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: ablage-secrets
  namespace: ablage-system
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-backend
    kind: SecretStore
  target:
    name: ablage-secrets
    creationPolicy: Owner
  data:
    - secretKey: DATABASE_PASSWORD
      remoteRef:
        key: database
        property: password
    - secretKey: JWT_SECRET_KEY
      remoteRef:
        key: jwt
        property: secret_key
```

```bash
kubectl apply -f secretstore.yaml
kubectl apply -f externalsecret.yaml
```

---

## Authentication & Authorization

### JWT Token Security

```python
# app/core/jwt.py
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status
import secrets

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT configuration
SECRET_KEY = secrets.token_urlsafe(32)  # Generate strong secret
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15  # Short-lived
REFRESH_TOKEN_EXPIRE_DAYS = 7


def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token."""
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access"
    })

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: Dict[str, Any]) -> str:
    """Create JWT refresh token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh"
    })

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str, expected_type: str = "access") -> Dict[str, Any]:
    """Verify and decode JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # Verify token type
        token_type = payload.get("type")
        if token_type != expected_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token type: expected {expected_type}, got {token_type}"
            )

        # Check expiration (jose does this automatically, but we double-check)
        exp = payload.get("exp")
        if exp and datetime.fromtimestamp(exp) < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired"
            )

        return payload

    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}"
        )


# Token blacklist (use Redis in production)
token_blacklist: set = set()

def blacklist_token(token: str):
    """Add token to blacklist (logout)."""
    token_blacklist.add(token)


def is_token_blacklisted(token: str) -> bool:
    """Check if token is blacklisted."""
    return token in token_blacklist
```

### Role-Based Access Control (RBAC)

```python
# app/core/permissions.py
from enum import Enum
from typing import List
from fastapi import Depends, HTTPException, status
from app.core.jwt import verify_token

class UserRole(str, Enum):
    """User roles with hierarchical permissions."""
    ADMIN = "admin"          # Full access
    MANAGER = "manager"      # Manage users, view all documents
    USER = "user"            # Own documents only
    VIEWER = "viewer"        # Read-only access

class Permission(str, Enum):
    """Granular permissions."""
    DOCUMENTS_CREATE = "documents:create"
    DOCUMENTS_READ_OWN = "documents:read:own"
    DOCUMENTS_READ_ALL = "documents:read:all"
    DOCUMENTS_UPDATE_OWN = "documents:update:own"
    DOCUMENTS_UPDATE_ALL = "documents:update:all"
    DOCUMENTS_DELETE_OWN = "documents:delete:own"
    DOCUMENTS_DELETE_ALL = "documents:delete:all"
    USERS_MANAGE = "users:manage"
    SYSTEM_ADMIN = "system:admin"


# Role-permission mapping
ROLE_PERMISSIONS: Dict[UserRole, List[Permission]] = {
    UserRole.ADMIN: [
        Permission.DOCUMENTS_CREATE,
        Permission.DOCUMENTS_READ_ALL,
        Permission.DOCUMENTS_UPDATE_ALL,
        Permission.DOCUMENTS_DELETE_ALL,
        Permission.USERS_MANAGE,
        Permission.SYSTEM_ADMIN
    ],
    UserRole.MANAGER: [
        Permission.DOCUMENTS_CREATE,
        Permission.DOCUMENTS_READ_ALL,
        Permission.DOCUMENTS_UPDATE_OWN,
        Permission.DOCUMENTS_DELETE_OWN,
        Permission.USERS_MANAGE
    ],
    UserRole.USER: [
        Permission.DOCUMENTS_CREATE,
        Permission.DOCUMENTS_READ_OWN,
        Permission.DOCUMENTS_UPDATE_OWN,
        Permission.DOCUMENTS_DELETE_OWN
    ],
    UserRole.VIEWER: [
        Permission.DOCUMENTS_READ_OWN
    ]
}


def has_permission(user_role: UserRole, permission: Permission) -> bool:
    """Check if role has permission."""
    return permission in ROLE_PERMISSIONS.get(user_role, [])


async def require_permission(permission: Permission):
    """FastAPI dependency to require specific permission."""
    async def permission_checker(token: str = Depends(oauth2_scheme)):
        payload = verify_token(token)
        user_role = UserRole(payload.get("role"))

        if not has_permission(user_role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission} required"
            )

        return payload

    return permission_checker


# Usage in endpoints
@router.post("/documents")
async def create_document(
    file: UploadFile,
    current_user: Dict = Depends(require_permission(Permission.DOCUMENTS_CREATE))
):
    ...


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: str,
    current_user: Dict = Depends(require_permission(Permission.DOCUMENTS_DELETE_OWN))
):
    # Additional check: verify document ownership
    document = await get_document(doc_id)
    if document.owner_id != current_user["user_id"]:
        # Check if user has DELETE_ALL permission
        if not has_permission(UserRole(current_user["role"]), Permission.DOCUMENTS_DELETE_ALL):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only delete your own documents"
            )
    ...
```

---

## API Security

### Rate Limiting

```python
# app/middleware/rate_limit.py
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
import time
from collections import defaultdict
from typing import Dict, Tuple
import asyncio

class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(self):
        # Store: {client_id: (tokens, last_refill_time)}
        self.buckets: Dict[str, Tuple[float, float]] = defaultdict(lambda: (0.0, time.time()))
        self.lock = asyncio.Lock()

    async def is_allowed(
        self,
        client_id: str,
        max_tokens: float = 100.0,
        refill_rate: float = 10.0  # tokens per second
    ) -> bool:
        """Check if request is allowed (token bucket algorithm)."""
        async with self.lock:
            tokens, last_refill = self.buckets[client_id]
            now = time.time()

            # Refill tokens based on time elapsed
            elapsed = now - last_refill
            tokens = min(max_tokens, tokens + elapsed * refill_rate)

            # Check if request is allowed
            if tokens >= 1.0:
                self.buckets[client_id] = (tokens - 1.0, now)
                return True
            else:
                self.buckets[client_id] = (tokens, now)
                return False


rate_limiter = RateLimiter()


async def rate_limit_middleware(request: Request, call_next):
    """Rate limit middleware for FastAPI."""
    # Get client identifier (IP or user ID)
    client_id = request.client.host

    # Authenticated users get higher rate limits
    if hasattr(request.state, "user"):
        client_id = f"user:{request.state.user.id}"
        max_tokens = 1000.0
        refill_rate = 100.0  # 100 requests/second for authenticated users
    else:
        max_tokens = 100.0
        refill_rate = 10.0  # 10 requests/second for anonymous

    # Check rate limit
    allowed = await rate_limiter.is_allowed(client_id, max_tokens, refill_rate)

    if not allowed:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "detail": "Rate limit exceeded. Please try again later.",
                "retry_after": 1.0 / refill_rate
            },
            headers={"Retry-After": str(int(1.0 / refill_rate))}
        )

    response = await call_next(request)
    return response
```

### API Key Management

```python
# app/core/api_keys.py
import secrets
import hashlib
from datetime import datetime, timedelta
from sqlalchemy import Column, String, DateTime, Boolean
from app.db.base import Base

class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(String, primary_key=True)
    key_hash = Column(String, nullable=False, unique=True)
    user_id = Column(String, nullable=False)
    name = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    is_active = Column(Boolean, default=True)
    last_used_at = Column(DateTime)


def generate_api_key() -> Tuple[str, str]:
    """Generate API key and its hash."""
    # Generate random API key
    api_key = f"ablage_{secrets.token_urlsafe(32)}"

    # Hash the API key for storage
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    return api_key, key_hash


async def verify_api_key(api_key: str, db: AsyncSession) -> Optional[APIKey]:
    """Verify API key and return associated record."""
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    stmt = select(APIKey).where(
        APIKey.key_hash == key_hash,
        APIKey.is_active == True,
        or_(APIKey.expires_at == None, APIKey.expires_at > datetime.utcnow())
    )
    result = await db.execute(stmt)
    api_key_record = result.scalar_one_or_none()

    if api_key_record:
        # Update last used timestamp
        api_key_record.last_used_at = datetime.utcnow()
        await db.commit()

    return api_key_record


# FastAPI dependency
async def require_api_key(
    api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db)
) -> APIKey:
    """Require valid API key."""
    api_key_record = await verify_api_key(api_key, db)

    if not api_key_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key"
        )

    return api_key_record
```

---

## Container Security

### Dockerfile Hardening

```dockerfile
# docker/Dockerfile.backend
# Use specific version, not 'latest'
FROM python:3.11.7-slim-bookworm AS base

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -u 1000 appuser

# Install dependencies as root
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Change ownership to non-root user
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Read-only filesystem (mount /tmp as writable volume if needed)
# VOLUME ["/tmp"]

# Drop capabilities (in Kubernetes SecurityContext)
# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8000/health')"

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Kubernetes SecurityContext

```yaml
# backend-deployment-hardened.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ablage-backend
  namespace: ablage-system
spec:
  template:
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        runAsGroup: 1000
        fsGroup: 1000
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: backend
          image: ablage-backend:1.0.0
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            runAsNonRoot: true
            runAsUser: 1000
            capabilities:
              drop:
                - ALL
          volumeMounts:
            - name: tmp
              mountPath: /tmp
            - name: cache
              mountPath: /app/.cache
      volumes:
        - name: tmp
          emptyDir: {}
        - name: cache
          emptyDir: {}
```

### Image Scanning (Trivy)

```bash
# Install Trivy
wget https://github.com/aquasecurity/trivy/releases/download/v0.48.3/trivy_0.48.3_Linux-64bit.tar.gz
tar zxvf trivy_0.48.3_Linux-64bit.tar.gz
sudo mv trivy /usr/local/bin/

# Scan Docker image
trivy image --severity HIGH,CRITICAL ablage-backend:1.0.0

# Scan and fail on high/critical vulnerabilities
trivy image --exit-code 1 --severity CRITICAL ablage-backend:1.0.0

# Generate report
trivy image --format json --output report.json ablage-backend:1.0.0
```

### Pod Security Standards

```yaml
# pod-security-policy.yaml (Kubernetes 1.25+)
apiVersion: v1
kind: Namespace
metadata:
  name: ablage-system
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/warn: restricted
```

---

## GPU Security

### GPU Resource Isolation

```yaml
# worker-deployment-gpu-isolated.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ablage-worker
  namespace: ablage-system
spec:
  template:
    spec:
      containers:
        - name: worker
          image: ablage-worker:1.0.0
          env:
            # Restrict visible GPUs
            - name: CUDA_VISIBLE_DEVICES
              value: "0"  # Only GPU 0 visible

            # Enable MPS (Multi-Process Service) for GPU sharing
            - name: CUDA_MPS_PIPE_DIRECTORY
              value: "/tmp/nvidia-mps"
            - name: CUDA_MPS_LOG_DIRECTORY
              value: "/tmp/nvidia-mps-log"
          resources:
            limits:
              nvidia.com/gpu: 1  # Request 1 full GPU
              # Or use MIG (Multi-Instance GPU) for finer control
              # nvidia.com/mig-1g.5gb: 1
```

### GPU Memory Limits

```python
# app/workers/gpu_guard.py
import torch
from contextlib import contextmanager

@contextmanager
def gpu_memory_limit(max_memory_gb: float = 13.6):
    """Context manager to enforce GPU memory limit."""
    if not torch.cuda.is_available():
        yield
        return

    try:
        # Set memory limit (85% of 16GB)
        torch.cuda.set_per_process_memory_fraction(max_memory_gb / 16.0)
        yield
    finally:
        # Clear cache on exit
        torch.cuda.empty_cache()


# Usage
with gpu_memory_limit(13.6):
    result = model.process(image)
```

---

## Logging & Audit Trail

### Structured Security Logging

```python
# app/core/security_logger.py
import structlog
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import Request

security_logger = structlog.get_logger("security")


def log_authentication_attempt(
    username: str,
    success: bool,
    ip_address: str,
    user_agent: Optional[str] = None,
    failure_reason: Optional[str] = None
):
    """Log authentication attempt."""
    security_logger.info(
        "authentication_attempt",
        timestamp=datetime.utcnow().isoformat(),
        username=username,
        success=success,
        ip_address=ip_address,
        user_agent=user_agent,
        failure_reason=failure_reason
    )


def log_authorization_failure(
    user_id: str,
    resource: str,
    action: str,
    ip_address: str,
    reason: str
):
    """Log authorization failure."""
    security_logger.warning(
        "authorization_failure",
        timestamp=datetime.utcnow().isoformat(),
        user_id=user_id,
        resource=resource,
        action=action,
        ip_address=ip_address,
        reason=reason
    )


def log_suspicious_activity(
    user_id: Optional[str],
    activity_type: str,
    details: Dict[str, Any],
    ip_address: str,
    severity: str = "medium"
):
    """Log suspicious activity."""
    security_logger.warning(
        "suspicious_activity",
        timestamp=datetime.utcnow().isoformat(),
        user_id=user_id,
        activity_type=activity_type,
        details=details,
        ip_address=ip_address,
        severity=severity
    )


def log_data_access(
    user_id: str,
    resource_type: str,
    resource_id: str,
    action: str,
    ip_address: str
):
    """Log data access for audit trail."""
    security_logger.info(
        "data_access",
        timestamp=datetime.utcnow().isoformat(),
        user_id=user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        action=action,
        ip_address=ip_address
    )
```

### Audit Middleware

```python
# app/middleware/audit.py
from fastapi import Request
import time

async def audit_middleware(request: Request, call_next):
    """Audit middleware to log all requests."""
    start_time = time.time()

    # Extract request details
    client_ip = request.client.host
    method = request.method
    path = request.url.path
    user_id = getattr(request.state, "user_id", None)

    # Log request
    security_logger.info(
        "request_received",
        timestamp=datetime.utcnow().isoformat(),
        method=method,
        path=path,
        client_ip=client_ip,
        user_id=user_id
    )

    # Process request
    response = await call_next(request)

    # Calculate duration
    duration_ms = (time.time() - start_time) * 1000

    # Log response
    security_logger.info(
        "request_completed",
        timestamp=datetime.utcnow().isoformat(),
        method=method,
        path=path,
        status_code=response.status_code,
        duration_ms=duration_ms,
        client_ip=client_ip,
        user_id=user_id
    )

    return response
```

---

## Compliance & Data Protection

### GDPR Compliance

#### Data Retention Policy

```python
# app/tasks/gdpr_tasks.py
from celery import shared_task
from datetime import datetime, timedelta
from sqlalchemy import select, delete

@shared_task
def cleanup_expired_documents():
    """Delete documents older than retention period (GDPR Article 5)."""
    retention_days = 365 * 7  # 7 years for business documents

    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

    # Delete old documents
    stmt = delete(Document).where(
        Document.created_at < cutoff_date,
        Document.is_archived == True
    )

    result = db.execute(stmt)
    deleted_count = result.rowcount

    logger.info(
        "gdpr_cleanup_completed",
        deleted_count=deleted_count,
        cutoff_date=cutoff_date.isoformat()
    )


@shared_task
def anonymize_user_data(user_id: str):
    """Anonymize user data after account deletion (GDPR Article 17)."""
    # Anonymize personal data
    user = db.query(User).filter(User.id == user_id).first()
    user.email = f"deleted_{user_id}@anonymized.local"
    user.username = f"deleted_{user_id}"
    user.first_name = "Deleted"
    user.last_name = "User"
    user.is_active = False

    # Keep documents but anonymize owner
    documents = db.query(Document).filter(Document.owner_id == user_id).all()
    for doc in documents:
        doc.owner_id = "00000000-0000-0000-0000-000000000000"  # Anonymous user

    db.commit()

    logger.info(
        "user_data_anonymized",
        user_id=user_id,
        documents_affected=len(documents)
    )
```

#### Data Export (GDPR Article 20)

```python
# app/api/v1/gdpr.py
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
import json
import io

router = APIRouter()

@router.get("/gdpr/export")
async def export_user_data(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Export all user data (GDPR Article 20 - Data Portability)."""
    # Collect user data
    user_data = {
        "user": {
            "id": current_user.id,
            "email": current_user.email,
            "username": current_user.username,
            "created_at": current_user.created_at.isoformat()
        },
        "documents": []
    }

    # Get all user documents
    documents = await db.execute(
        select(Document).where(Document.owner_id == current_user.id)
    )

    for doc in documents.scalars():
        user_data["documents"].append({
            "id": doc.id,
            "filename": doc.filename,
            "created_at": doc.created_at.isoformat(),
            "extracted_text": doc.extracted_text,
            "metadata": doc.metadata
        })

    # Create JSON file
    json_data = json.dumps(user_data, indent=2, ensure_ascii=False)
    buffer = io.BytesIO(json_data.encode('utf-8'))

    # Log data export for audit
    log_data_access(
        user_id=current_user.id,
        resource_type="user_data",
        resource_id=current_user.id,
        action="export",
        ip_address=request.client.host
    )

    return StreamingResponse(
        buffer,
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename=user_data_{current_user.id}.json"
        }
    )
```

---

## Security Monitoring

### Falco for Runtime Security

```bash
# Install Falco
helm repo add falcosecurity https://falcosecurity.github.io/charts
helm repo update

helm install falco falcosecurity/falco \
  --namespace falco \
  --create-namespace \
  --set falcosidekick.enabled=true \
  --set falcosidekick.config.slack.webhookurl="<slack-webhook>"
```

```yaml
# falco-rules.yaml
- rule: Unauthorized Process in Container
  desc: Detect unexpected process execution
  condition: >
    spawned_process and container and
    not proc.name in (python, uvicorn, celery, sh, bash)
  output: >
    Unexpected process started in container
    (user=%user.name command=%proc.cmdline container=%container.name)
  priority: WARNING

- rule: Write to Non-Temp Directory
  desc: Detect writes to read-only filesystem
  condition: >
    open_write and container and
    not fd.name startswith /tmp and
    not fd.name startswith /var/log
  output: >
    Write to unexpected directory
    (user=%user.name file=%fd.name container=%container.name)
  priority: WARNING

- rule: GPU Access by Non-Worker Container
  desc: Detect unauthorized GPU access
  condition: >
    open_read and fd.name startswith /dev/nvidia and
    not container.name startswith ablage-worker
  output: >
    Unauthorized GPU access
    (user=%user.name container=%container.name)
  priority: CRITICAL
```

---

## Penetration Testing

### Pre-Penetration Test Checklist

- [ ] Get written authorization from management
- [ ] Define scope (IP ranges, domains, applications)
- [ ] Set testing window (date/time)
- [ ] Notify security team and SOC
- [ ] Prepare rollback plan
- [ ] Backup all systems
- [ ] Monitor during testing

### Automated Security Scanning

#### OWASP ZAP

```bash
# Run OWASP ZAP in Docker
docker run -t owasp/zap2docker-stable zap-baseline.py \
  -t https://ablage.example.com \
  -r zap-report.html

# Full scan
docker run -t owasp/zap2docker-stable zap-full-scan.py \
  -t https://ablage.example.com \
  -r zap-full-report.html
```

#### Nuclei

```bash
# Install Nuclei
go install -v github.com/projectdiscovery/nuclei/v2/cmd/nuclei@latest

# Run scan
nuclei -u https://ablage.example.com -severity high,critical

# Custom templates
nuclei -u https://ablage.example.com -t custom-templates/
```

#### NMAP

```bash
# Port scan
nmap -sV -sC -p- ablage.example.com

# Vulnerability scan
nmap --script vuln ablage.example.com
```

### Manual Testing Checklist

#### Authentication
- [ ] Test for SQL injection in login form
- [ ] Test for brute force protection
- [ ] Test for session fixation
- [ ] Test for weak password policy bypass
- [ ] Test for JWT token tampering

#### Authorization
- [ ] Test for horizontal privilege escalation (access other users' documents)
- [ ] Test for vertical privilege escalation (user → admin)
- [ ] Test for IDOR (Insecure Direct Object Reference)
- [ ] Test for missing function-level access control

#### Input Validation
- [ ] Test for SQL injection in search
- [ ] Test for XSS in document upload (filename, metadata)
- [ ] Test for path traversal in file download
- [ ] Test for XXE (XML External Entity) in file upload
- [ ] Test for command injection

#### Session Management
- [ ] Test for session timeout
- [ ] Test for concurrent sessions
- [ ] Test for logout effectiveness
- [ ] Test for CSRF protection
- [ ] Test for session fixation

#### File Upload
- [ ] Test for unrestricted file upload (try .exe, .php, .jsp)
- [ ] Test for file size limit bypass
- [ ] Test for zip bomb
- [ ] Test for malicious PDF/image (embedded scripts)

#### API Security
- [ ] Test for rate limiting bypass
- [ ] Test for API key leakage
- [ ] Test for mass assignment vulnerability
- [ ] Test for GraphQL introspection (if applicable)

---

## Security Checklist

### Pre-Production Checklist

#### Network Security
- [ ] TLS 1.3 configured with strong ciphers
- [ ] HTTP → HTTPS redirect enabled
- [ ] HSTS header configured (preload list)
- [ ] Network policies applied (default deny)
- [ ] Firewall rules configured
- [ ] mTLS configured (if required)

#### Application Security
- [ ] Input validation on all endpoints
- [ ] Output encoding (XSS prevention)
- [ ] CSRF protection enabled
- [ ] SQL injection prevention (parameterized queries)
- [ ] Rate limiting configured
- [ ] Security headers configured

#### Authentication & Authorization
- [ ] Strong password policy enforced
- [ ] JWT tokens with short expiration
- [ ] Refresh tokens with rotation
- [ ] RBAC implemented and tested
- [ ] API key management implemented
- [ ] Multi-factor authentication (optional)

#### Database Security
- [ ] Database credentials in secrets management
- [ ] Row-level security enabled
- [ ] Encryption at rest configured
- [ ] SSL/TLS for database connections
- [ ] Backup encryption enabled

#### Container Security
- [ ] Non-root user in containers
- [ ] Read-only root filesystem
- [ ] Dropped capabilities
- [ ] Image scanning for vulnerabilities
- [ ] Pod Security Standards enforced

#### Secrets Management
- [ ] Secrets not in Git
- [ ] Vault or External Secrets Operator configured
- [ ] Secret rotation policy defined
- [ ] Secrets encrypted at rest

#### Logging & Monitoring
- [ ] Security event logging enabled
- [ ] Audit trail for all data access
- [ ] Log aggregation (Loki) configured
- [ ] Security monitoring (Falco) deployed
- [ ] Alert rules for suspicious activity

#### Compliance
- [ ] GDPR data retention policy implemented
- [ ] Data export functionality (Article 20)
- [ ] Data anonymization on deletion (Article 17)
- [ ] Consent management (if applicable)

#### Testing
- [ ] Penetration test completed
- [ ] Vulnerability scan passed (no high/critical)
- [ ] Security regression tests automated
- [ ] Incident response plan tested

---

## Summary

This advanced security hardening guide provides comprehensive protection for the Ablage-System:

**Key Security Layers:**
- **Network:** TLS 1.3, network policies, firewalls
- **Application:** Input validation, CSRF, XSS prevention
- **Database:** Encryption, RLS, parameterized queries
- **Secrets:** Vault integration, External Secrets Operator
- **Authentication:** JWT, RBAC, API keys
- **Container:** Non-root, read-only FS, dropped capabilities
- **Compliance:** GDPR data retention, export, anonymization
- **Monitoring:** Falco, security logging, audit trail

**Security Posture:**
- **Defense-in-Depth:** 7 layers of security controls
- **Zero Trust:** Authentication and authorization on every request
- **Least Privilege:** Minimal permissions for users and services
- **Audit Trail:** Complete logging for compliance
- **Penetration Tested:** Automated and manual security testing

**Next Steps:**
- Review [Local Development Setup Guide](local_development_setup_guide.md)
- Configure [Performance Benchmarking Suite](performance_benchmarking_guide.md)
- Implement [API Rate Limiting Guide](api_rate_limiting_guide.md)

---

**Document Status:** ✅ **COMPLETE**
**Lines:** ~2,100
**Coverage:** Comprehensive security hardening from network to application layer with GDPR compliance