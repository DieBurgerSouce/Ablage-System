# -*- coding: utf-8 -*-
"""
IP-Blocking Middleware für Ablage-System OCR.

Blockiert Anfragen von gesperrten IP-Adressen basierend auf
dem Incident Response Service.

Feinpoliert und durchdacht - Enterprise-grade Security.
"""

from datetime import datetime, timezone
from typing import Optional, Set

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import structlog

from app.core.config import settings
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


class IPBlockingMiddleware(BaseHTTPMiddleware):
    """
    Middleware zur Blockierung von gesperrten IP-Adressen.

    Prüft eingehende Requests gegen:
    1. In-Memory-Liste des IncidentResponseService
    2. Redis-basierte blockierte IPs (falls verfügbar)

    Bei Blockierung wird ein 403 Forbidden Response zurückgegeben.
    """

    def __init__(
        self,
        app,
        enabled: bool = True,
        whitelist: Optional[Set[str]] = None,
    ):
        """
        Initialisiert die IP-Blocking Middleware.

        Args:
            app: FastAPI/Starlette App
            enabled: Middleware aktivieren/deaktivieren
            whitelist: IP-Adressen die nie blockiert werden
        """
        super().__init__(app)
        self.enabled = enabled
        self.whitelist = whitelist or {"127.0.0.1", "::1", "localhost"}

    async def dispatch(self, request: Request, call_next):
        """Verarbeitet jeden Request und prüft IP-Blockierung."""
        if not self.enabled:
            return await call_next(request)

        # Extrahiere Client-IP
        client_ip = self._get_client_ip(request)

        # Whitelist prüfen
        if client_ip in self.whitelist:
            return await call_next(request)

        # Health-Endpoints immer erlauben (für Monitoring)
        if request.url.path in {"/health", "/", "/docs", "/redoc", "/openapi.json"}:
            return await call_next(request)

        # Prüfe ob IP blockiert ist
        is_blocked, reason = await self._is_ip_blocked(client_ip)

        if is_blocked:
            logger.warning(
                "ip_blocked_request_rejected",
                ip_address=client_ip,
                path=request.url.path,
                reason=reason
            )

            return JSONResponse(
                status_code=403,
                content={
                    "fehler": "Zugriff verweigert",
                    "nachricht": "Ihre IP-Adresse wurde aufgrund verdächtiger Aktivitäten temporär gesperrt. "
                                "Bei Fragen wenden Sie sich an den Administrator.",
                    "code": "IP_BLOCKED",
                    "zeitstempel": datetime.now(timezone.utc).isoformat()
                },
                headers={
                    "X-Blocked-Reason": "suspicious_activity",
                    "Cache-Control": "no-store"
                }
            )

        return await call_next(request)

    def _get_client_ip(self, request: Request) -> str:
        """
        Extrahiert die echte Client-IP unter Berücksichtigung von Proxies.

        Prüft in dieser Reihenfolge:
        1. X-Forwarded-For Header (für Reverse Proxies)
        2. X-Real-IP Header (für Nginx)
        3. Direkte Client-Adresse
        """
        # X-Forwarded-For: Die erste IP ist der ursprüngliche Client
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # Nehme die erste IP (ursprünglicher Client)
            return forwarded_for.split(",")[0].strip()

        # X-Real-IP: Wird von Nginx gesetzt
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()

        # Fallback auf direkte Verbindung
        if request.client:
            return request.client.host

        return "unknown"

    async def _is_ip_blocked(self, ip_address: str) -> tuple[bool, str]:
        """
        Prüft ob eine IP-Adresse blockiert ist.

        Prüft gegen:
        1. IncidentResponseService In-Memory-Liste
        2. Redis (falls verfügbar)

        Args:
            ip_address: Zu prüfende IP-Adresse

        Returns:
            Tuple (is_blocked, reason)
        """
        # 1. Prüfe IncidentResponseService
        try:
            from app.services.incident_response_service import get_incident_response_service

            service = get_incident_response_service()
            if service.is_ip_blocked(ip_address):
                return True, "incident_response_block"
        except Exception as e:
            logger.debug("incident_service_check_failed", **safe_error_log(e))

        # 2. Prüfe Redis (falls konfiguriert)
        try:
            from app.core.redis_state import get_redis

            manager = await get_redis()
            if manager:
                # RedisStateManager hat keine generische .get()-Methode; der
                # rohe aioredis-Client liegt unter ._redis. Verbindung
                # sicherstellen und Schlüssel direkt lesen.
                await manager._ensure_connection()
                raw_redis = manager._redis
                if raw_redis is not None:
                    blocked = await raw_redis.get(f"blocked_ip:{ip_address}")
                    if blocked:
                        return True, "redis_block"
        except Exception as e:
            logger.debug("redis_ip_check_failed", **safe_error_log(e))

        return False, ""


def create_ip_blocking_middleware(
    enabled: bool = True,
    whitelist: Optional[Set[str]] = None
) -> IPBlockingMiddleware:
    """
    Factory-Funktion für IP-Blocking Middleware.

    Args:
        enabled: Middleware aktivieren/deaktivieren
        whitelist: IP-Adressen die nie blockiert werden

    Returns:
        Konfigurierte IPBlockingMiddleware Klasse
    """
    def middleware(app):
        return IPBlockingMiddleware(
            app=app,
            enabled=enabled,
            whitelist=whitelist
        )
    return middleware
