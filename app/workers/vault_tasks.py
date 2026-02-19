"""Vault secret rotation tasks for Celery Beat.

Periodische Secret-Rotation ueber HashiCorp Vault.
Phase 1.2 - Security Haertung.
"""

import structlog
from celery import shared_task

from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


@shared_task(
    name="vault.refresh_secrets",
    bind=True,
    soft_time_limit=30,
    time_limit=60,
    max_retries=0,
    acks_late=True,
    queue="maintenance",
)
def refresh_vault_secrets(self) -> dict:
    """Refresh secrets from HashiCorp Vault.

    Ruft settings.refresh_secrets() auf, um gecachte Vault-Secrets
    zu erneuern. Non-critical: Fehler werden geloggt aber nicht geworfen.

    Returns:
        dict with status and details
    """
    from app.core.config import settings

    if not settings.VAULT_ENABLED:
        logger.debug("vault_refresh_skipped", reason="VAULT_ENABLED=False")
        return {"status": "skipped", "reason": "vault_disabled"}

    try:
        success = settings.refresh_secrets()
        if success:
            logger.info(
                "vault_secrets_refreshed",
                message="Vault-Secrets erfolgreich aktualisiert",
            )
            return {"status": "success", "refreshed": True}
        else:
            logger.warning(
                "vault_secrets_refresh_fehlgeschlagen",
                message="Vault-Secrets konnten nicht aktualisiert werden",
            )
            return {"status": "warning", "refreshed": False}

    except Exception as e:
        logger.error(
            "vault_secrets_refresh_fehler",
            **safe_error_log(e),
            message="Fehler bei Vault-Secret-Rotation",
        )
        # Non-critical: don't raise, just return error status
        return {"status": "error", "error": str(type(e).__name__)}
