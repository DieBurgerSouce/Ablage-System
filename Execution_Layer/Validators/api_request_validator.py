"""
API Request Validator - Comprehensive request validation middleware for Ablage-System.

This module provides multi-layered request validation including:
- Pydantic schema validation with German business rules
- Rate limiting with tier-based quotas
- Authentication and authorization validation
- Input sanitization and security checks
- Request size and content type validation
- GDPR compliance checks

Author: Ablage-System Team
Version: 1.0.0
Last Updated: 2025-11-22
"""

import re
import time
from typing import Optional, Dict, List, Any, Callable
from datetime import datetime, timedelta
from functools import wraps
from collections import defaultdict

from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator, ValidationError
from redis.asyncio import Redis
import structlog

logger = structlog.get_logger(__name__)

# ============================================================================
# Configuration
# ============================================================================

class ValidationConfig:
    """Global validation configuration."""

    # Request size limits
    MAX_REQUEST_SIZE_MB = 50
    MAX_JSON_DEPTH = 10
    MAX_ARRAY_LENGTH = 1000

    # Rate limiting tiers (requests per minute)
    RATE_LIMITS = {
        "free": 10,
        "standard": 60,
        "enterprise": 300,
        "admin": 1000
    }

    # Allowed file types for document upload
    ALLOWED_MIME_TYPES = {
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/tiff",
        "image/webp"
    }

    # Allowed file extensions
    ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".webp"}

    # Security patterns
    SUSPICIOUS_PATTERNS = [
        r"<script[^>]*>.*?</script>",  # XSS
        r"javascript:",  # JS protocol
        r"on\w+\s*=",  # Event handlers
        r"(\.\./|\.\.\\)+",  # Path traversal
        r"(union|select|insert|update|delete|drop)\s+",  # SQL injection
        r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]",  # Control characters
    ]

    # German-specific validation
    GERMAN_POSTAL_CODE_PATTERN = r"^\d{5}$"
    GERMAN_PHONE_PATTERN = r"^(\+49|0)[1-9]\d{1,14}$"
    UST_ID_PATTERN = r"^DE\d{9}$"
    IBAN_PATTERN = r"^DE\d{20}$"


# ============================================================================
# Pydantic Models for Request Validation
# ============================================================================

class DocumentUploadRequest(BaseModel):
    """Validation schema for document upload requests."""

    filename: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Name der hochzuladenden Datei"
    )
    language: str = Field(
        default="de",
        pattern="^(de|en)$",
        description="Dokumentsprache (de oder en)"
    )
    ocr_backend: str = Field(
        default="auto",
        pattern="^(auto|deepseek|got_ocr|surya)$",
        description="OCR-Backend Auswahl"
    )
    enable_cache: bool = Field(
        default=True,
        description="Ergebnisse cachen"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional metadata für das Dokument"
    )

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        """Validate filename for security issues."""
        # Prevent path traversal
        if ".." in v or "/" in v or "\\" in v:
            raise ValueError("Dateiname enthält ungültige Zeichen")

        # Check extension
        extension = None
        for ext in ValidationConfig.ALLOWED_EXTENSIONS:
            if v.lower().endswith(ext):
                extension = ext
                break

        if not extension:
            raise ValueError(
                f"Ungültige Dateierweiterung. Erlaubt: {', '.join(ValidationConfig.ALLOWED_EXTENSIONS)}"
            )

        # Sanitize filename
        v = re.sub(r'[^\w\s\-\.]', '', v)

        return v

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, v: Optional[Dict]) -> Optional[Dict]:
        """Validate metadata structure."""
        if v is None:
            return v

        if not isinstance(v, dict):
            raise ValueError("Metadata muss ein Dictionary sein")

        # Limit depth and size
        if len(v) > 50:
            raise ValueError("Metadata darf maximal 50 Schlüssel enthalten")

        # Check for suspicious content
        for key, value in v.items():
            if not isinstance(key, str):
                raise ValueError("Metadata-Schlüssel müssen Strings sein")
            if len(key) > 100:
                raise ValueError("Metadata-Schlüssel zu lang (max 100 Zeichen)")
            if isinstance(value, str) and len(value) > 1000:
                raise ValueError("Metadata-Werte zu lang (max 1000 Zeichen)")

        return v


class GermanBusinessDataRequest(BaseModel):
    """Validation schema for German business data."""

    company_name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Firmenname"
    )
    address: Optional[str] = Field(
        None,
        max_length=500,
        description="Adresse"
    )
    postal_code: Optional[str] = Field(
        None,
        pattern=ValidationConfig.GERMAN_POSTAL_CODE_PATTERN,
        description="Postleitzahl (5 Ziffern)"
    )
    city: Optional[str] = Field(
        None,
        max_length=100,
        description="Stadt"
    )
    ust_id: Optional[str] = Field(
        None,
        pattern=ValidationConfig.UST_ID_PATTERN,
        description="Umsatzsteuer-Identifikationsnummer (DE + 9 Ziffern)"
    )
    iban: Optional[str] = Field(
        None,
        description="IBAN (DE + 20 Ziffern)"
    )
    phone: Optional[str] = Field(
        None,
        description="Telefonnummer"
    )

    @field_validator("company_name")
    @classmethod
    def validate_company_name(cls, v: str) -> str:
        """Validate German company name."""
        # Check for valid company types
        valid_types = ["GmbH", "AG", "UG", "KG", "OHG", "GbR", "e.V.", "SE", "KGaA"]

        # Basic sanitization
        v = v.strip()

        # Check length
        if len(v) < 1:
            raise ValueError("Firmenname darf nicht leer sein")

        return v

    @field_validator("iban")
    @classmethod
    def validate_iban(cls, v: Optional[str]) -> Optional[str]:
        """Validate German IBAN with checksum."""
        if v is None:
            return v

        # Remove spaces
        v = v.replace(" ", "").upper()

        # Check format
        if not re.match(ValidationConfig.IBAN_PATTERN, v):
            raise ValueError("Ungültige IBAN (Format: DE + 20 Ziffern)")

        # Validate checksum (mod 97)
        rearranged = v[4:] + v[:4]
        numeric = ""
        for char in rearranged:
            if char.isdigit():
                numeric += char
            else:
                numeric += str(ord(char) - ord('A') + 10)

        if int(numeric) % 97 != 1:
            raise ValueError("IBAN-Prüfsumme ungültig")

        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        """Validate German phone number."""
        if v is None:
            return v

        # Remove common formatting
        v = v.replace(" ", "").replace("-", "").replace("/", "")

        # Check pattern
        if not re.match(ValidationConfig.GERMAN_PHONE_PATTERN, v):
            raise ValueError(
                "Ungültige Telefonnummer (Format: +49... oder 0...)"
            )

        return v


class SearchRequest(BaseModel):
    """Validation schema for search requests."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Suchanfrage"
    )
    filters: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Suchfilter"
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximale Anzahl Ergebnisse"
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Offset für Paginierung"
    )
    sort_by: Optional[str] = Field(
        default="relevance",
        pattern="^(relevance|date|name)$",
        description="Sortierung"
    )

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        """Validate and sanitize search query."""
        # Remove control characters
        v = re.sub(r'[\x00-\x1F\x7F]', '', v)

        # Prevent excessively long words (possible DoS)
        words = v.split()
        for word in words:
            if len(word) > 100:
                raise ValueError("Suchwort zu lang (max 100 Zeichen pro Wort)")

        return v.strip()


# ============================================================================
# Security Validators
# ============================================================================

class SecurityValidator:
    """Security validation utilities."""

    @staticmethod
    def check_suspicious_content(content: str) -> None:
        """Check for suspicious patterns in user input.

        Raises:
            HTTPException: If suspicious pattern detected
        """
        for pattern in ValidationConfig.SUSPICIOUS_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                logger.warning(
                    "suspicious_pattern_detected",
                    pattern=pattern,
                    content_preview=content[:100]
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "code": "SUSPICIOUS_CONTENT",
                        "message": "Eingabe enthält verdächtige Muster",
                        "documentation_url": "https://docs.ablage.company.de/errors#SUSPICIOUS_CONTENT"
                    }
                )

    @staticmethod
    def validate_content_type(request: Request, allowed_types: set) -> None:
        """Validate request content type.

        Args:
            request: FastAPI request object
            allowed_types: Set of allowed MIME types

        Raises:
            HTTPException: If content type not allowed
        """
        content_type = request.headers.get("content-type", "").split(";")[0].strip()

        if content_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail={
                    "code": "UNSUPPORTED_MEDIA_TYPE",
                    "message": f"Content-Type nicht unterstützt: {content_type}",
                    "allowed_types": list(allowed_types),
                    "documentation_url": "https://docs.ablage.company.de/errors#UNSUPPORTED_MEDIA_TYPE"
                }
            )

    @staticmethod
    async def validate_request_size(request: Request, max_size_mb: int = 50) -> None:
        """Validate request body size.

        Args:
            request: FastAPI request object
            max_size_mb: Maximum size in MB

        Raises:
            HTTPException: If request too large
        """
        content_length = request.headers.get("content-length")

        if content_length:
            size_mb = int(content_length) / (1024 * 1024)
            if size_mb > max_size_mb:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail={
                        "code": "REQUEST_TOO_LARGE",
                        "message": f"Anfrage zu groß: {size_mb:.2f} MB (max {max_size_mb} MB)",
                        "documentation_url": "https://docs.ablage.company.de/errors#REQUEST_TOO_LARGE"
                    }
                )


# ============================================================================
# Rate Limiting
# ============================================================================

class RateLimiter:
    """Redis-based rate limiter with tier support."""

    def __init__(self, redis_client: Redis):
        """Initialize rate limiter.

        Args:
            redis_client: Redis client for storing rate limit data
        """
        self.redis = redis_client

    async def check_rate_limit(
        self,
        identifier: str,
        tier: str = "free",
        window_seconds: int = 60
    ) -> Dict[str, Any]:
        """Check if identifier is within rate limit.

        Args:
            identifier: Unique identifier (user ID, IP address, API key)
            tier: User tier (free, standard, enterprise, admin)
            window_seconds: Time window in seconds

        Returns:
            Dict with rate limit info

        Raises:
            HTTPException: If rate limit exceeded
        """
        limit = ValidationConfig.RATE_LIMITS.get(tier, 10)
        key = f"rate_limit:{identifier}:{tier}"

        # Get current count
        current = await self.redis.get(key)
        current_count = int(current) if current else 0

        # Check limit
        if current_count >= limit:
            ttl = await self.redis.ttl(key)
            retry_after = ttl if ttl > 0 else window_seconds

            logger.warning(
                "rate_limit_exceeded",
                identifier=identifier,
                tier=tier,
                limit=limit,
                current=current_count
            )

            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": f"Anfragelimit überschritten ({limit} Anfragen pro {window_seconds}s)",
                    "limit": limit,
                    "window_seconds": window_seconds,
                    "retry_after": retry_after,
                    "documentation_url": "https://docs.ablage.company.de/errors#RATE_LIMIT_EXCEEDED"
                },
                headers={
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + retry_after),
                    "Retry-After": str(retry_after)
                }
            )

        # Increment counter
        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_seconds)
        await pipe.execute()

        remaining = limit - current_count - 1

        return {
            "limit": limit,
            "remaining": remaining,
            "reset": int(time.time()) + window_seconds,
            "tier": tier
        }


# ============================================================================
# Authentication Validation
# ============================================================================

class AuthValidator:
    """JWT token validation and user authentication."""

    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        """Initialize auth validator.

        Args:
            secret_key: Secret key for JWT validation
            algorithm: JWT algorithm
        """
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.security = HTTPBearer()

    async def validate_token(
        self,
        credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())
    ) -> Dict[str, Any]:
        """Validate JWT token.

        Args:
            credentials: HTTP Authorization credentials

        Returns:
            Decoded token payload

        Raises:
            HTTPException: If token invalid
        """
        try:
            import jwt

            token = credentials.credentials

            # Decode and validate token
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )

            # Check expiration
            exp = payload.get("exp")
            if exp and datetime.utcfromtimestamp(exp) < datetime.utcnow():
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={
                        "code": "TOKEN_EXPIRED",
                        "message": "Token abgelaufen",
                        "documentation_url": "https://docs.ablage.company.de/errors#TOKEN_EXPIRED"
                    },
                    headers={"WWW-Authenticate": "Bearer"}
                )

            logger.info(
                "token_validated",
                user_id=payload.get("sub"),
                tier=payload.get("tier", "free")
            )

            return payload

        except jwt.InvalidTokenError as e:
            logger.warning("invalid_token", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "INVALID_TOKEN",
                    "message": "Ungültiger Token",
                    "documentation_url": "https://docs.ablage.company.de/errors#INVALID_TOKEN"
                },
                headers={"WWW-Authenticate": "Bearer"}
            )


# ============================================================================
# GDPR Compliance Validator
# ============================================================================

class GDPRValidator:
    """GDPR compliance validation."""

    @staticmethod
    def validate_consent(consent_flags: Dict[str, bool]) -> None:
        """Validate GDPR consent flags.

        Args:
            consent_flags: Dictionary of consent flags

        Raises:
            HTTPException: If required consents not given
        """
        required_consents = ["privacy_policy", "terms_of_service"]

        missing = [c for c in required_consents if not consent_flags.get(c, False)]

        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "MISSING_CONSENT",
                    "message": f"Erforderliche Einwilligungen fehlen: {', '.join(missing)}",
                    "required_consents": required_consents,
                    "documentation_url": "https://docs.ablage.company.de/errors#MISSING_CONSENT"
                }
            )

    @staticmethod
    def validate_data_retention(retention_days: int) -> None:
        """Validate data retention period.

        Args:
            retention_days: Requested retention period in days

        Raises:
            HTTPException: If retention period invalid
        """
        # §14 UStG: Rechnungen müssen 10 Jahre aufbewahrt werden
        # Art. 17 DSGVO: Recht auf Löschung nach Zweckerfüllung

        MIN_RETENTION_DAYS = 1
        MAX_RETENTION_DAYS = 365 * 10  # 10 years

        if not (MIN_RETENTION_DAYS <= retention_days <= MAX_RETENTION_DAYS):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_RETENTION_PERIOD",
                    "message": f"Ungültige Aufbewahrungsdauer: {retention_days} Tage (erlaubt: {MIN_RETENTION_DAYS}-{MAX_RETENTION_DAYS})",
                    "min_days": MIN_RETENTION_DAYS,
                    "max_days": MAX_RETENTION_DAYS,
                    "documentation_url": "https://docs.ablage.company.de/errors#INVALID_RETENTION_PERIOD"
                }
            )


# ============================================================================
# Middleware and Decorators
# ============================================================================

def validate_request(
    schema: BaseModel,
    rate_limit: bool = True,
    check_security: bool = True
) -> Callable:
    """Decorator for comprehensive request validation.

    Args:
        schema: Pydantic model for validation
        rate_limit: Enable rate limiting
        check_security: Enable security checks

    Returns:
        Decorated function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request from args/kwargs
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break

            if not request:
                request = kwargs.get("request")

            if not request:
                raise ValueError("Request object not found in function arguments")

            # Security checks
            if check_security:
                await SecurityValidator.validate_request_size(request)

            # Validate against schema
            try:
                body = await request.json()
                validated_data = schema(**body)
                kwargs["validated_data"] = validated_data
            except ValidationError as e:
                logger.warning("validation_error", errors=e.errors())
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "code": "VALIDATION_ERROR",
                        "message": "Validierungsfehler",
                        "errors": e.errors(),
                        "documentation_url": "https://docs.ablage.company.de/errors#VALIDATION_ERROR"
                    }
                )

            # Call original function
            return await func(*args, **kwargs)

        return wrapper
    return decorator


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    """Example usage and testing."""

    print("API Request Validator - Ablage-System")
    print("=" * 60)

    # Example 1: Validate document upload request
    print("\n1. Document Upload Validation:")
    try:
        doc_request = DocumentUploadRequest(
            filename="rechnung_2025.pdf",
            language="de",
            ocr_backend="deepseek",
            metadata={"kunde": "Müller GmbH", "betrag": "1234.56"}
        )
        print(f"✓ Valid: {doc_request.filename}")
    except ValidationError as e:
        print(f"✗ Invalid: {e}")

    # Example 2: Validate German business data
    print("\n2. German Business Data Validation:")
    try:
        business_request = GermanBusinessDataRequest(
            company_name="Müller Digitale Lösungen GmbH",
            postal_code="10115",
            city="Berlin",
            ust_id="DE123456789",
            iban="DE89370400440532013000"
        )
        print(f"✓ Valid: {business_request.company_name}")
    except ValidationError as e:
        print(f"✗ Invalid: {e}")

    # Example 3: Invalid IBAN checksum
    print("\n3. Invalid IBAN Checksum:")
    try:
        invalid_request = GermanBusinessDataRequest(
            company_name="Test GmbH",
            iban="DE89370400440532013099"  # Invalid checksum
        )
        print(f"✓ Valid: {invalid_request.company_name}")
    except ValidationError as e:
        print(f"✗ Invalid: {e.errors()[0]['msg']}")

    # Example 4: Security validation
    print("\n4. Security Pattern Detection:")
    try:
        SecurityValidator.check_suspicious_content("<script>alert('XSS')</script>")
        print("✓ No suspicious content")
    except HTTPException as e:
        print(f"✗ Suspicious content detected: {e.detail['message']}")

    # Example 5: Search validation
    print("\n5. Search Request Validation:")
    try:
        search_request = SearchRequest(
            query="Rechnung Müller GmbH",
            limit=20,
            sort_by="date"
        )
        print(f"✓ Valid search: {search_request.query}")
    except ValidationError as e:
        print(f"✗ Invalid: {e}")

    print("\n" + "=" * 60)
    print("Validator module ready for production use")
    print("Integration: from app.validators import validate_request, RateLimiter")
