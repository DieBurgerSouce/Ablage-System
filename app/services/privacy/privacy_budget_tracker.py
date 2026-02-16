# -*- coding: utf-8 -*-
"""
Privacy Budget Tracker.

Verwaltet das Epsilon-Budget pro Tenant pro Tag.
Stellt sicher, dass Privacy-Garantien nicht durch viele Queries untergraben werden.

Vision 2.0 Feature: Anonymized Analytics (Phase 5)
Feinpoliert und durchdacht.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Union
from typing_extensions import TypedDict
from uuid import UUID

import redis.asyncio as redis
from pydantic import BaseModel

from app.core.config import settings
from app.core.safe_errors import safe_error_log

logger = logging.getLogger(__name__)

# Type definitions for mypy strict mode
MetadataValue = Union[str, int, float, bool, None]
MetadataDict = Dict[str, MetadataValue]


class BudgetStatusDict(TypedDict):
    """Typed dictionary for BudgetStatus serialization."""
    company_id: str
    date: str
    total_budget: float
    consumed: float
    remaining: float
    is_exhausted: bool
    queries_count: int
    reset_at: str


class BudgetExhaustedError(Exception):
    """Wird geworfen wenn Privacy-Budget erschoepft ist."""
    pass


@dataclass
class BudgetStatus:
    """Status des Privacy-Budgets."""
    company_id: UUID
    date: date
    total_budget: float
    consumed: float
    remaining: float
    is_exhausted: bool
    queries_count: int
    reset_at: datetime

    def to_dict(self) -> BudgetStatusDict:
        """Konvertiert zu Dictionary."""
        return BudgetStatusDict(
            company_id=str(self.company_id),
            date=self.date.isoformat(),
            total_budget=self.total_budget,
            consumed=round(self.consumed, 4),
            remaining=round(self.remaining, 4),
            is_exhausted=self.is_exhausted,
            queries_count=self.queries_count,
            reset_at=self.reset_at.isoformat(),
        )


class BudgetConsumption(BaseModel):
    """Einzelne Budget-Verbrauchung."""
    epsilon: float
    query_type: str
    timestamp: datetime
    endpoint: Optional[str] = None
    metadata: MetadataDict = {}


@dataclass
class BudgetConfig:
    """Konfiguration für Privacy Budget."""
    daily_budget: float = 10.0
    min_remaining_warning: float = 2.0
    budget_reset_hour: int = 0  # Mitternacht
    allow_overdraft: bool = False
    overdraft_limit: float = 0.0
    track_history: bool = True
    history_retention_days: int = 30


class PrivacyBudgetTracker:
    """
    Verwaltet Privacy-Budget pro Tenant.

    Implementiert Differential Privacy Composition Theorem:
    Mehrere Queries addieren ihre Epsilons auf.
    """

    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None,
        config: Optional[BudgetConfig] = None
    ) -> None:
        """
        Initialisiert den Budget Tracker.

        Args:
            redis_client: Redis-Client für persistenten Storage
            config: Budget-Konfiguration
        """
        self.redis = redis_client
        self.config = config or BudgetConfig()
        self._local_cache: Dict[str, float] = {}  # Fallback ohne Redis

        logger.info(
            "privacy_budget_tracker_initialized",
            daily_budget=self.config.daily_budget,
            redis_available=redis_client is not None
        )

    def _get_budget_key(self, company_id: UUID) -> str:
        """Generiert Redis-Key für Budget."""
        today = date.today().isoformat()
        return f"privacy_budget:{company_id}:{today}"

    def _get_history_key(self, company_id: UUID) -> str:
        """Generiert Redis-Key für History."""
        today = date.today().isoformat()
        return f"privacy_budget_history:{company_id}:{today}"

    def _get_query_count_key(self, company_id: UUID) -> str:
        """Generiert Redis-Key für Query Count."""
        today = date.today().isoformat()
        return f"privacy_budget_queries:{company_id}:{today}"

    async def get_remaining_budget(self, company_id: UUID) -> float:
        """
        Gibt verbleibendes Budget für heute zurück.

        Args:
            company_id: Tenant-ID

        Returns:
            Verbleibendes Epsilon-Budget
        """
        consumed = await self._get_consumed(company_id)
        remaining = self.config.daily_budget - consumed
        return max(0, remaining)

    async def _get_consumed(self, company_id: UUID) -> float:
        """Liest verbrauchtes Budget."""
        key = self._get_budget_key(company_id)

        if self.redis:
            try:
                value = await self.redis.get(key)
                return float(value) if value else 0.0
            except Exception as e:
                logger.warning("redis_get_failed", key=key, **safe_error_log(e))

        # Fallback zu Local Cache
        return self._local_cache.get(key, 0.0)

    async def _set_consumed(self, company_id: UUID, value: float) -> None:
        """Setzt verbrauchtes Budget."""
        key = self._get_budget_key(company_id)

        if self.redis:
            try:
                # TTL: 24 Stunden + Puffer
                await self.redis.set(key, str(value), ex=90000)
            except Exception as e:
                logger.warning("redis_set_failed", key=key, **safe_error_log(e))

        # Immer auch Local Cache updaten
        self._local_cache[key] = value

    async def consume_budget(
        self,
        company_id: UUID,
        epsilon: float,
        query_type: str = "unknown",
        endpoint: Optional[str] = None
    ) -> bool:
        """
        Verbraucht Budget für eine Query.

        Args:
            company_id: Tenant-ID
            epsilon: Zu verbrauchendes Epsilon
            query_type: Typ der Query (für Logging)
            endpoint: API-Endpoint (optional)

        Returns:
            True wenn Budget verfügbar und verbraucht wurde

        Raises:
            BudgetExhaustedError: Wenn Budget erschoepft
        """
        if epsilon <= 0:
            raise ValueError("Epsilon muss positiv sein")

        remaining = await self.get_remaining_budget(company_id)

        # Prüfe ob genug Budget
        if epsilon > remaining:
            if not self.config.allow_overdraft:
                # SECURITY: Keine Epsilon-Werte in Logs (Geschäftsgeheimnis)
                logger.warning(
                    "privacy_budget_exhausted",
                    company_id=str(company_id),
                )
                # SECURITY: Keine konkreten Werte in Error Messages exponieren
                raise BudgetExhaustedError(
                    "Privacy-Budget erschoepft. "
                    "Budget wird um Mitternacht zurückgesetzt."
                )

            # Prüfe Overdraft-Limit
            overdraft_needed = epsilon - remaining
            if overdraft_needed > self.config.overdraft_limit:
                # SECURITY: Keine konkreten Werte exponieren
                raise BudgetExhaustedError(
                    "Overdraft-Limit überschritten. "
                    "Bitte warten Sie bis zum Budget-Reset."
                )

        # Verbrauche Budget
        consumed = await self._get_consumed(company_id)
        new_consumed = consumed + epsilon
        await self._set_consumed(company_id, new_consumed)

        # Inkrementiere Query-Count
        await self._increment_query_count(company_id)

        # Logge History
        if self.config.track_history:
            await self._log_consumption(
                company_id, epsilon, query_type, endpoint
            )

        logger.info(
            "privacy_budget_consumed",
            company_id=str(company_id),
            epsilon=epsilon,
            total_consumed=new_consumed,
            remaining=self.config.daily_budget - new_consumed
        )

        return True

    async def _increment_query_count(self, company_id: UUID) -> None:
        """Inkrementiert Query-Zähler."""
        key = self._get_query_count_key(company_id)

        if self.redis:
            try:
                await self.redis.incr(key)
                await self.redis.expire(key, 90000)
            except Exception as e:
                logger.warning("redis_incr_failed", key=key, **safe_error_log(e))

    async def _get_query_count(self, company_id: UUID) -> int:
        """Liest Query-Zähler."""
        key = self._get_query_count_key(company_id)

        if self.redis:
            try:
                value = await self.redis.get(key)
                return int(value) if value else 0
            except Exception as e:
                logger.warning("redis_get_failed", key=key, **safe_error_log(e))

        return 0

    async def _log_consumption(
        self,
        company_id: UUID,
        epsilon: float,
        query_type: str,
        endpoint: Optional[str]
    ) -> None:
        """Loggt Verbrauch in History."""
        if not self.redis:
            return

        key = self._get_history_key(company_id)
        entry = {
            "epsilon": epsilon,
            "query_type": query_type,
            "endpoint": endpoint or "",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        try:
            import json
            await self.redis.rpush(key, json.dumps(entry))
            await self.redis.expire(key, self.config.history_retention_days * 86400)
        except Exception as e:
            logger.warning("redis_history_log_failed", **safe_error_log(e))

    async def get_status(self, company_id: UUID) -> BudgetStatus:
        """
        Gibt vollständigen Budget-Status zurück.

        Args:
            company_id: Tenant-ID

        Returns:
            BudgetStatus mit allen Details
        """
        consumed = await self._get_consumed(company_id)
        remaining = max(0, self.config.daily_budget - consumed)
        queries = await self._get_query_count(company_id)

        # Berechne nächsten Reset
        today = date.today()
        reset_time = datetime.combine(
            today + timedelta(days=1),
            datetime.min.time()
        ).replace(hour=self.config.budget_reset_hour)

        return BudgetStatus(
            company_id=company_id,
            date=today,
            total_budget=self.config.daily_budget,
            consumed=consumed,
            remaining=remaining,
            is_exhausted=remaining <= 0,
            queries_count=queries,
            reset_at=reset_time
        )

    async def check_budget_available(
        self,
        company_id: UUID,
        epsilon: float
    ) -> bool:
        """
        Prüft ob genug Budget für Query verfügbar ist.

        Args:
            company_id: Tenant-ID
            epsilon: Benötigtes Epsilon

        Returns:
            True wenn Budget ausreicht
        """
        remaining = await self.get_remaining_budget(company_id)
        return epsilon <= remaining

    async def get_history(
        self,
        company_id: UUID,
        limit: int = 100
    ) -> List[BudgetConsumption]:
        """
        Gibt Query-History zurück.

        Args:
            company_id: Tenant-ID
            limit: Max Anzahl Einträge

        Returns:
            Liste von BudgetConsumption
        """
        if not self.redis:
            return []

        key = self._get_history_key(company_id)

        try:
            import json
            entries = await self.redis.lrange(key, -limit, -1)
            return [
                BudgetConsumption(**json.loads(entry))
                for entry in entries
            ]
        except Exception as e:
            logger.warning("redis_history_read_failed", **safe_error_log(e))
            return []

    async def reset_budget(self, company_id: UUID) -> None:
        """
        Setzt Budget manuell zurück (Admin-Funktion).

        Args:
            company_id: Tenant-ID
        """
        await self._set_consumed(company_id, 0.0)

        if self.redis:
            key = self._get_query_count_key(company_id)
            try:
                await self.redis.delete(key)
            except Exception as e:
                logger.warning("redis_delete_failed", key=key, **safe_error_log(e))

        logger.info(
            "privacy_budget_reset",
            company_id=str(company_id),
            reset_by="admin"
        )


# Singleton-Instanz
_budget_tracker: Optional[PrivacyBudgetTracker] = None


async def get_budget_tracker() -> PrivacyBudgetTracker:
    """Gibt Singleton-Instanz des Budget Trackers zurück."""
    global _budget_tracker
    if _budget_tracker is None:
        # Versuche Redis-Verbindung
        redis_client = None
        try:
            redis_url = getattr(settings, "REDIS_URL", None)
            if redis_url:
                redis_client = redis.from_url(redis_url)
        except Exception as e:
            logger.warning("redis_connection_failed", **safe_error_log(e))

        _budget_tracker = PrivacyBudgetTracker(redis_client=redis_client)

    return _budget_tracker
