"""
Tenant Rate Limit Service.

Multi-Tenant Rate Limiting mit Subscription-Tier-basierter Konfiguration.
Ermöglicht individuelle Rate-Limits pro Company/Mandant.

Features:
- Tenant-spezifische Rate Limits (pro Endpoint-Pattern)
- Subscription-Tier-Defaults (Free, Basic, Professional, Enterprise)
- Usage-Metriken für Dashboard
- Rate-Limit-Violation-Logging für Security

Created: 2026-01-19
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from uuid import UUID
import fnmatch
import structlog

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.db.models import (
    Company,
    TenantRateLimit,
    TenantUsageMetrics,
    RateLimitViolation,
    SubscriptionTierDefaults,
    SubscriptionTier,
    User,
)
from app.core.config import settings
from app.core.safe_errors import safe_error_log
from app.core.rate_limiting import (

    get_redis_storage,
    RateLimitStorageError,
)

logger = structlog.get_logger(__name__)


# ==================== Default Tier Configuration ====================

DEFAULT_TIER_CONFIG: Dict[str, Dict[str, Any]] = {
    SubscriptionTier.FREE.value: {
        "requests_per_minute": 30,
        "requests_per_hour": 300,
        "requests_per_day": 1000,
        "ocr_requests_per_hour": 10,
        "batch_requests_per_hour": 2,
        "burst_limit": 10,
        "max_users": 3,
        "max_documents_per_month": 50,
        "max_storage_gb": 1,
        "features": ["ocr", "search", "export_csv"],
    },
    SubscriptionTier.BASIC.value: {
        "requests_per_minute": 60,
        "requests_per_hour": 600,
        "requests_per_day": 5000,
        "ocr_requests_per_hour": 50,
        "batch_requests_per_hour": 10,
        "burst_limit": 20,
        "max_users": 10,
        "max_documents_per_month": 500,
        "max_storage_gb": 10,
        "features": ["ocr", "search", "export_csv", "export_pdf", "api_access"],
    },
    SubscriptionTier.PROFESSIONAL.value: {
        "requests_per_minute": 120,
        "requests_per_hour": 1200,
        "requests_per_day": 20000,
        "ocr_requests_per_hour": 200,
        "batch_requests_per_hour": 50,
        "burst_limit": 50,
        "max_users": 50,
        "max_documents_per_month": 5000,
        "max_storage_gb": 100,
        "features": [
            "ocr", "search", "export_csv", "export_pdf", "api_access",
            "advanced_analytics", "workflow", "integrations"
        ],
    },
    SubscriptionTier.ENTERPRISE.value: {
        "requests_per_minute": 1000,
        "requests_per_hour": 10000,
        "requests_per_day": 100000,
        "ocr_requests_per_hour": 1000,
        "batch_requests_per_hour": 500,
        "burst_limit": 200,
        "max_users": 999,
        "max_documents_per_month": 999999,
        "max_storage_gb": 9999,
        "features": [
            "ocr", "search", "export_csv", "export_pdf", "api_access",
            "advanced_analytics", "workflow", "integrations", "sso",
            "audit_log", "custom_branding", "priority_support", "dedicated_resources"
        ],
    },
}


class TenantRateLimitService:
    """Service für Tenant-spezifisches Rate Limiting."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== Rate Limit Checking ====================

    async def check_rate_limit(
        self,
        company_id: UUID,
        user_id: Optional[UUID],
        endpoint: str,
        method: str,
        ip_address: str,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Prüfe Rate Limit für einen Request.

        Args:
            company_id: Mandanten-ID
            user_id: User-ID (optional)
            endpoint: API-Endpoint
            method: HTTP-Method
            ip_address: Client-IP
            user_agent: User-Agent Header

        Returns:
            Dict mit:
            - allowed: bool - Request erlaubt
            - remaining: int - Verbleibende Requests
            - limit: int - Aktuelles Limit
            - reset_at: str - Zeitpunkt des Resets
            - limit_type: str - Art des Limits (minute, hour, day)
        """
        # 1. Hole Rate Limit Konfiguration für Company
        rate_config = await self._get_rate_limit_config(company_id, endpoint)

        # 2. Hole Redis Storage
        storage = await get_redis_storage()
        if not storage or not storage.is_available:
            if settings.RATE_LIMIT_FAIL_CLOSED:
                logger.error(
                    "tenant_rate_limit_redis_unavailable_fail_closed",
                    company_id=str(company_id),
                    endpoint=endpoint
                )
                raise RateLimitStorageError(
                    "Rate-Limiting-Service vorübergehend nicht verfügbar."
                )
            # Fail-open: Erlaube Request
            return {
                "allowed": True,
                "reason": "redis_unavailable",
                "remaining": -1,
                "limit": -1,
            }

        # 3. Prüfe Limits (Minute -> Hour -> Day)
        for limit_type, window_seconds, limit_key_suffix in [
            ("minute", 60, self._get_minute_key()),
            ("hour", 3600, self._get_hour_key()),
            ("day", 86400, self._get_day_key()),
        ]:
            limit_field = f"requests_per_{limit_type}"
            limit_value = rate_config.get(limit_field, 100)

            redis_key = f"tenant_ratelimit:{company_id}:{endpoint}:{limit_key_suffix}"

            try:
                current_count = await storage._redis.get(redis_key)
                current_count = int(current_count) if current_count else 0

                if current_count >= limit_value:
                    # Rate Limit überschritten - logge Violation
                    await self._log_violation(
                        company_id=company_id,
                        user_id=user_id,
                        endpoint=endpoint,
                        method=method,
                        ip_address=ip_address,
                        user_agent=user_agent,
                        limit_type=limit_type,
                        limit_value=limit_value,
                        current_count=current_count,
                    )

                    return {
                        "allowed": False,
                        "remaining": 0,
                        "limit": limit_value,
                        "reset_at": self._get_reset_time(limit_type).isoformat(),
                        "limit_type": limit_type,
                        "retry_after": self._get_retry_after(limit_type),
                    }

            except Exception as e:
                logger.error(
                    "tenant_rate_limit_check_failed",
                    company_id=str(company_id),
                    **safe_error_log(e)
                )
                if settings.RATE_LIMIT_FAIL_CLOSED:
                    raise RateLimitStorageError("Rate-Limit-Prüfung fehlgeschlagen.") from e

        # Request erlaubt - berechne remaining
        remaining = rate_config.get("requests_per_minute", 100) - current_count

        return {
            "allowed": True,
            "remaining": max(0, remaining - 1),
            "limit": rate_config.get("requests_per_minute", 100),
            "reset_at": self._get_reset_time("minute").isoformat(),
            "limit_type": "minute",
        }

    async def increment_usage(
        self,
        company_id: UUID,
        endpoint: str,
    ) -> bool:
        """
        Inkrementiere Rate-Limit-Zähler nach erfolgreichem Request.

        Args:
            company_id: Mandanten-ID
            endpoint: API-Endpoint

        Returns:
            True bei Erfolg
        """
        storage = await get_redis_storage()
        if not storage or not storage.is_available:
            return False

        try:
            # Inkrementiere alle Zeitfenster
            for window_seconds, key_suffix in [
                (60, self._get_minute_key()),
                (3600, self._get_hour_key()),
                (86400, self._get_day_key()),
            ]:
                redis_key = f"tenant_ratelimit:{company_id}:{endpoint}:{key_suffix}"
                await storage.increment(redis_key, window_seconds)

            logger.debug(
                "tenant_rate_limit_incremented",
                company_id=str(company_id),
                endpoint=endpoint
            )
            return True

        except Exception as e:
            logger.error(
                "tenant_rate_limit_increment_failed",
                company_id=str(company_id),
                **safe_error_log(e)
            )
            return False

    # ==================== Configuration Management ====================

    async def get_company_limits(
        self,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """
        Hole alle Rate Limit Konfigurationen für eine Company.

        Args:
            company_id: Mandanten-ID

        Returns:
            Dict mit allen Limits und Subscription-Info
        """
        # Company mit Subscription-Info laden
        result = await self.db.execute(
            select(Company).where(Company.id == company_id)
        )
        company = result.scalar_one_or_none()

        if not company:
            raise ValueError(f"Company {company_id} nicht gefunden")

        # Custom Limits laden
        limits_result = await self.db.execute(
            select(TenantRateLimit).where(
                and_(
                    TenantRateLimit.company_id == company_id,
                    TenantRateLimit.is_active == True
                )
            )
        )
        custom_limits = limits_result.scalars().all()

        # Tier-Defaults holen
        tier = getattr(company, 'subscription_tier', 'free') or 'free'
        tier_defaults = DEFAULT_TIER_CONFIG.get(tier, DEFAULT_TIER_CONFIG["free"])

        return {
            "company_id": str(company_id),
            "company_name": company.name,
            "subscription_tier": tier,
            "subscription_expires_at": getattr(company, 'subscription_expires_at', None),
            "tier_defaults": tier_defaults,
            "custom_limits": [
                {
                    "id": str(limit.id),
                    "endpoint_pattern": limit.endpoint_pattern,
                    "requests_per_minute": limit.requests_per_minute,
                    "requests_per_hour": limit.requests_per_hour,
                    "requests_per_day": limit.requests_per_day,
                    "burst_limit": limit.burst_limit,
                    "is_custom": limit.is_custom,
                }
                for limit in custom_limits
            ],
            "max_users": getattr(company, 'max_users', tier_defaults["max_users"]),
            "max_documents_per_month": getattr(
                company, 'max_documents_per_month',
                tier_defaults["max_documents_per_month"]
            ),
            "max_storage_gb": getattr(company, 'max_storage_gb', tier_defaults["max_storage_gb"]),
            "features_enabled": getattr(company, 'features_enabled', tier_defaults["features"]),
        }

    async def update_company_limit(
        self,
        company_id: UUID,
        endpoint_pattern: str,
        requests_per_minute: Optional[int] = None,
        requests_per_hour: Optional[int] = None,
        requests_per_day: Optional[int] = None,
        burst_limit: Optional[int] = None,
        created_by_id: Optional[UUID] = None,
    ) -> TenantRateLimit:
        """
        Erstelle oder aktualisiere Custom Rate Limit für Company.

        Args:
            company_id: Mandanten-ID
            endpoint_pattern: Endpoint-Pattern (z.B. /api/v1/documents/*)
            requests_per_minute: Limit pro Minute
            requests_per_hour: Limit pro Stunde
            requests_per_day: Limit pro Tag
            burst_limit: Burst-Limit
            created_by_id: User der die Änderung macht

        Returns:
            TenantRateLimit Model
        """
        # Existierenden Eintrag suchen
        result = await self.db.execute(
            select(TenantRateLimit).where(
                and_(
                    TenantRateLimit.company_id == company_id,
                    TenantRateLimit.endpoint_pattern == endpoint_pattern
                )
            )
        )
        existing = result.scalar_one_or_none()

        # Tier-Defaults als Fallback
        company_result = await self.db.execute(
            select(Company).where(Company.id == company_id)
        )
        company = company_result.scalar_one_or_none()
        tier = getattr(company, 'subscription_tier', 'free') or 'free'
        tier_config = DEFAULT_TIER_CONFIG.get(tier, DEFAULT_TIER_CONFIG["free"])

        if existing:
            # Update
            if requests_per_minute is not None:
                existing.requests_per_minute = requests_per_minute
            if requests_per_hour is not None:
                existing.requests_per_hour = requests_per_hour
            if requests_per_day is not None:
                existing.requests_per_day = requests_per_day
            if burst_limit is not None:
                existing.burst_limit = burst_limit
            existing.is_custom = True
            existing.updated_at = datetime.now(timezone.utc)

            logger.info(
                "tenant_rate_limit_updated",
                company_id=str(company_id),
                endpoint_pattern=endpoint_pattern
            )
            return existing
        else:
            # Create
            new_limit = TenantRateLimit(
                company_id=company_id,
                endpoint_pattern=endpoint_pattern,
                requests_per_minute=requests_per_minute or tier_config["requests_per_minute"],
                requests_per_hour=requests_per_hour or tier_config["requests_per_hour"],
                requests_per_day=requests_per_day or tier_config["requests_per_day"],
                burst_limit=burst_limit or tier_config["burst_limit"],
                is_custom=True,
                created_by_id=created_by_id,
            )
            self.db.add(new_limit)

            logger.info(
                "tenant_rate_limit_created",
                company_id=str(company_id),
                endpoint_pattern=endpoint_pattern
            )
            return new_limit

    async def reset_to_tier_defaults(
        self,
        company_id: UUID,
    ) -> int:
        """
        Setze alle Custom Limits auf Tier-Defaults zurück.

        Args:
            company_id: Mandanten-ID

        Returns:
            Anzahl gelöschter Custom-Limits
        """
        result = await self.db.execute(
            select(TenantRateLimit).where(
                and_(
                    TenantRateLimit.company_id == company_id,
                    TenantRateLimit.is_custom == True
                )
            )
        )
        custom_limits = result.scalars().all()

        count = len(custom_limits)
        for limit in custom_limits:
            await self.db.delete(limit)

        logger.info(
            "tenant_rate_limits_reset",
            company_id=str(company_id),
            deleted_count=count
        )
        return count

    # ==================== Usage Metrics ====================

    async def get_usage_summary(
        self,
        company_id: UUID,
        period_type: str = "daily",
        days_back: int = 30,
    ) -> Dict[str, Any]:
        """
        Hole Nutzungs-Summary für eine Company.

        Args:
            company_id: Mandanten-ID
            period_type: hourly, daily, monthly
            days_back: Anzahl Tage zurück

        Returns:
            Usage-Summary mit Metriken
        """
        start_date = datetime.now(timezone.utc) - timedelta(days=days_back)

        result = await self.db.execute(
            select(TenantUsageMetrics).where(
                and_(
                    TenantUsageMetrics.company_id == company_id,
                    TenantUsageMetrics.period_type == period_type,
                    TenantUsageMetrics.period_start >= start_date
                )
            ).order_by(TenantUsageMetrics.period_start.desc())
        )
        metrics = result.scalars().all()

        if not metrics:
            return {
                "company_id": str(company_id),
                "period_type": period_type,
                "data_points": 0,
                "total_requests": 0,
                "rate_limited_requests": 0,
                "avg_response_time_ms": None,
            }

        total_requests = sum(m.total_requests for m in metrics)
        rate_limited = sum(m.rate_limited_requests for m in metrics)
        avg_response_times = [m.avg_response_time_ms for m in metrics if m.avg_response_time_ms]

        return {
            "company_id": str(company_id),
            "period_type": period_type,
            "data_points": len(metrics),
            "total_requests": total_requests,
            "rate_limited_requests": rate_limited,
            "rate_limit_percentage": (rate_limited / total_requests * 100) if total_requests > 0 else 0,
            "avg_response_time_ms": sum(avg_response_times) / len(avg_response_times) if avg_response_times else None,
            "documents_processed": sum(m.documents_processed for m in metrics),
            "pages_processed": sum(m.pages_processed for m in metrics),
            "storage_used_bytes": metrics[0].storage_used_bytes if metrics else 0,
            "active_users": max(m.active_users for m in metrics) if metrics else 0,
            "timeline": [
                {
                    "period_start": m.period_start.isoformat(),
                    "total_requests": m.total_requests,
                    "rate_limited": m.rate_limited_requests,
                    "documents_processed": m.documents_processed,
                }
                for m in metrics[:30]  # Letzte 30 Datenpunkte
            ],
        }

    async def get_violation_history(
        self,
        company_id: UUID,
        hours_back: int = 24,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Hole Rate-Limit-Violations für eine Company.

        Args:
            company_id: Mandanten-ID
            hours_back: Stunden zurück
            limit: Max Anzahl Ergebnisse

        Returns:
            Liste von Violations
        """
        start_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)

        result = await self.db.execute(
            select(RateLimitViolation).where(
                and_(
                    RateLimitViolation.company_id == company_id,
                    RateLimitViolation.occurred_at >= start_time
                )
            ).order_by(RateLimitViolation.occurred_at.desc()).limit(limit)
        )
        violations = result.scalars().all()

        return [
            {
                "id": str(v.id),
                "endpoint": v.endpoint,
                "method": v.method,
                "ip_address": v.ip_address,
                "limit_type": v.limit_type,
                "limit_value": v.limit_value,
                "current_count": v.current_count,
                "occurred_at": v.occurred_at.isoformat(),
            }
            for v in violations
        ]

    # ==================== Private Helpers ====================

    async def _get_rate_limit_config(
        self,
        company_id: UUID,
        endpoint: str,
    ) -> Dict[str, int]:
        """Hole Rate Limit Config für Company + Endpoint."""
        # Custom Limit suchen (Pattern-Match)
        result = await self.db.execute(
            select(TenantRateLimit).where(
                and_(
                    TenantRateLimit.company_id == company_id,
                    TenantRateLimit.is_active == True
                )
            )
        )
        custom_limits = result.scalars().all()

        # Finde passenden Pattern
        for limit in custom_limits:
            if fnmatch.fnmatch(endpoint, limit.endpoint_pattern):
                return {
                    "requests_per_minute": limit.requests_per_minute,
                    "requests_per_hour": limit.requests_per_hour,
                    "requests_per_day": limit.requests_per_day,
                    "burst_limit": limit.burst_limit,
                }

        # Fallback: Tier-Defaults
        company_result = await self.db.execute(
            select(Company).where(Company.id == company_id)
        )
        company = company_result.scalar_one_or_none()

        if company:
            tier = getattr(company, 'subscription_tier', 'free') or 'free'
            return DEFAULT_TIER_CONFIG.get(tier, DEFAULT_TIER_CONFIG["free"])

        return DEFAULT_TIER_CONFIG["free"]

    async def _log_violation(
        self,
        company_id: UUID,
        user_id: Optional[UUID],
        endpoint: str,
        method: str,
        ip_address: str,
        user_agent: Optional[str],
        limit_type: str,
        limit_value: int,
        current_count: int,
    ) -> None:
        """Logge Rate-Limit-Violation."""
        violation = RateLimitViolation(
            company_id=company_id,
            user_id=user_id,
            endpoint=endpoint,
            method=method,
            ip_address=ip_address,
            user_agent=user_agent,
            limit_type=limit_type,
            limit_value=limit_value,
            current_count=current_count,
            retry_after_seconds=self._get_retry_after(limit_type),
        )
        self.db.add(violation)

        logger.warning(
            "tenant_rate_limit_violation",
            company_id=str(company_id),
            endpoint=endpoint,
            limit_type=limit_type,
            limit_value=limit_value,
            current_count=current_count
        )

    def _get_minute_key(self) -> str:
        """Get current minute key."""
        return datetime.now(timezone.utc).strftime("%Y%m%d%H%M")

    def _get_hour_key(self) -> str:
        """Get current hour key."""
        return datetime.now(timezone.utc).strftime("%Y%m%d%H")

    def _get_day_key(self) -> str:
        """Get current day key."""
        return datetime.now(timezone.utc).strftime("%Y%m%d")

    def _get_reset_time(self, limit_type: str) -> datetime:
        """Get next reset time for limit type."""
        now = datetime.now(timezone.utc)
        if limit_type == "minute":
            return now.replace(second=0, microsecond=0) + timedelta(minutes=1)
        elif limit_type == "hour":
            return now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        else:  # day
            return now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)

    def _get_retry_after(self, limit_type: str) -> int:
        """Get retry-after in seconds."""
        now = datetime.now(timezone.utc)
        reset = self._get_reset_time(limit_type)
        return max(1, int((reset - now).total_seconds()))


# ==================== Dependency Injection ====================

async def get_tenant_rate_limit_service(
    db: AsyncSession,
) -> TenantRateLimitService:
    """FastAPI Dependency für TenantRateLimitService."""
    return TenantRateLimitService(db)
