"""
Periodischer Vault Secret Refresh Task.

Aktualisiert Secrets aus Vault regelmäßig basierend auf VAULT_SECRET_REFRESH_INTERVAL.

Feinpoliert und durchdacht - Enterprise Secrets Management.
"""

from typing import Dict, Any

import structlog
from celery import shared_task

from app.core.config import settings

logger = structlog.get_logger(__name__)


@shared_task(name="vault.refresh_secrets", bind=True, max_retries=3)
def refresh_vault_secrets(self) -> Dict[str, Any]:
    """
    Aktualisiert Secrets aus Vault (periodisch).

    Returns:
        Dict mit Status (success/failed/skipped) und optional reason

    Raises:
        self.retry: Bei Fehlern wird Task mit Countdown retried
    """
    try:
        # Vault deaktiviert - kein Refresh nötig
        if not settings.VAULT_ENABLED:
            logger.debug("vault_refresh_skipped", reason="Vault deaktiviert")
            return {"status": "skipped", "reason": "Vault deaktiviert"}

        # Vault aktiviert - prüfe ob refresh_secrets Methode existiert
        if not hasattr(settings, "refresh_secrets"):
            logger.warning(
                "vault_refresh_not_supported",
                reason="Settings hat keine refresh_secrets Methode",
            )
            return {
                "status": "skipped",
                "reason": "refresh_secrets Methode nicht verfügbar",
            }

        # Führe Refresh aus
        success = settings.refresh_secrets()

        if success:
            logger.info(
                "vault_secrets_refreshed",
                message="Secrets erfolgreich aus Vault aktualisiert",
            )
            return {"status": "success"}
        else:
            logger.warning(
                "vault_refresh_failed",
                message="Secret-Refresh fehlgeschlagen (kein Fehler geworfen)",
            )
            return {"status": "failed", "reason": "refresh_secrets returned False"}

    except Exception as e:
        logger.error(
            "vault_refresh_error",
            error=str(e),
            error_type=type(e).__name__,
            message="Unerwarteter Fehler beim Secret-Refresh",
        )
        # Retry mit 60 Sekunden Countdown
        raise self.retry(countdown=60, exc=e)
