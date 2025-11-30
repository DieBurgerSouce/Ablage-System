"""
Vault Health Check und Status API.

Stellt Endpunkte bereit um den Vault-Status zu prüfen
und die Integration zu verifizieren.

Art. 32 DSGVO - Sicherheit der Verarbeitung:
Überwachung der Geheimnismanagement-Infrastruktur.
"""

from typing import Dict, Any, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel

import structlog

from app.core.config import settings, VaultClient
from app.core.security import get_current_admin_user
from app.db.models import User

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/vault", tags=["vault"])


class VaultStatusResponse(BaseModel):
    """Vault Status Response Schema."""

    enabled: bool
    connected: bool
    authenticated: bool
    sealed: Optional[bool] = None
    version: Optional[str] = None
    cluster_name: Optional[str] = None
    address: Optional[str] = None
    last_check: str
    error: Optional[str] = None


class VaultHealthResponse(BaseModel):
    """Vault Health Response Schema."""

    status: str  # "healthy", "degraded", "unhealthy"
    vault_enabled: bool
    vault_connected: bool
    secrets_engine_status: str
    transit_engine_status: str
    last_rotation: Optional[str] = None
    message: str


class SecretMetadataResponse(BaseModel):
    """Secret Metadata Response (ohne sensible Daten)."""

    path: str
    version: int
    created_time: Optional[str] = None
    last_updated: Optional[str] = None
    keys: list[str]  # Nur Schlüsselnamen, keine Werte


@router.get(
    "/status",
    response_model=VaultStatusResponse,
    summary="Vault Status abrufen",
    description="Zeigt den aktuellen Vault-Verbindungsstatus an.",
)
async def get_vault_status(
    current_user: User = Depends(get_current_admin_user),
) -> VaultStatusResponse:
    """
    Ruft den aktuellen Vault-Status ab.

    Nur für Administratoren verfügbar.
    """
    if not settings.VAULT_ENABLED:
        return VaultStatusResponse(
            enabled=False,
            connected=False,
            authenticated=False,
            last_check=datetime.utcnow().isoformat(),
            message="Vault-Integration ist deaktiviert",
        )

    try:
        vault = VaultClient(
            vault_addr=settings.VAULT_ADDR,
            vault_token=settings.VAULT_TOKEN,
            vault_role_id=settings.VAULT_ROLE_ID,
            vault_secret_id=settings.VAULT_SECRET_ID,
            vault_namespace=settings.VAULT_NAMESPACE,
            verify_ssl=settings.VAULT_VERIFY_SSL,
        )

        connected = vault.connect()

        if connected and vault._client:
            # Hole Vault-Status
            try:
                health = vault._client.sys.read_health_status(method="GET")
                seal_status = vault._client.sys.read_seal_status()

                return VaultStatusResponse(
                    enabled=True,
                    connected=True,
                    authenticated=vault._authenticated,
                    sealed=seal_status.get("sealed", None),
                    version=health.get("version", None) if isinstance(health, dict) else None,
                    cluster_name=health.get("cluster_name", None) if isinstance(health, dict) else None,
                    address=settings.VAULT_ADDR,
                    last_check=datetime.utcnow().isoformat(),
                )
            except Exception as e:
                logger.warning("vault_health_check_partial", error=str(e))
                return VaultStatusResponse(
                    enabled=True,
                    connected=True,
                    authenticated=vault._authenticated,
                    address=settings.VAULT_ADDR,
                    last_check=datetime.utcnow().isoformat(),
                    error=f"Teilweise Statusabfrage fehlgeschlagen: {str(e)}",
                )
        else:
            return VaultStatusResponse(
                enabled=True,
                connected=False,
                authenticated=False,
                address=settings.VAULT_ADDR,
                last_check=datetime.utcnow().isoformat(),
                error="Verbindung zu Vault fehlgeschlagen",
            )

    except Exception as e:
        logger.error("vault_status_check_failed", error=str(e))
        return VaultStatusResponse(
            enabled=True,
            connected=False,
            authenticated=False,
            address=settings.VAULT_ADDR,
            last_check=datetime.utcnow().isoformat(),
            error=str(e),
        )


@router.get(
    "/health",
    response_model=VaultHealthResponse,
    summary="Vault Health Check",
    description="Führt einen umfassenden Health-Check der Vault-Integration durch.",
)
async def vault_health_check() -> VaultHealthResponse:
    """
    Führt einen Health-Check der Vault-Integration durch.

    Öffentlich verfügbar für Monitoring-Systeme.
    """
    if not settings.VAULT_ENABLED:
        return VaultHealthResponse(
            status="disabled",
            vault_enabled=False,
            vault_connected=False,
            secrets_engine_status="n/a",
            transit_engine_status="n/a",
            message="Vault-Integration ist deaktiviert",
        )

    try:
        vault = VaultClient(
            vault_addr=settings.VAULT_ADDR,
            vault_token=settings.VAULT_TOKEN,
            vault_role_id=settings.VAULT_ROLE_ID,
            vault_secret_id=settings.VAULT_SECRET_ID,
            vault_namespace=settings.VAULT_NAMESPACE,
            verify_ssl=settings.VAULT_VERIFY_SSL,
        )

        if not vault.connect():
            return VaultHealthResponse(
                status="unhealthy",
                vault_enabled=True,
                vault_connected=False,
                secrets_engine_status="unknown",
                transit_engine_status="unknown",
                message="Verbindung zu Vault fehlgeschlagen",
            )

        # Prüfe KV-Engine
        secrets_status = "unknown"
        try:
            vault._client.secrets.kv.v2.list_secrets(
                path="",
                mount_point=settings.VAULT_MOUNT_POINT,
            )
            secrets_status = "healthy"
        except Exception:
            secrets_status = "unhealthy"

        # Prüfe Transit-Engine
        transit_status = "unknown"
        try:
            vault._client.secrets.transit.list_keys()
            transit_status = "healthy"
        except Exception:
            transit_status = "not_configured"

        # Bestimme Gesamtstatus
        if secrets_status == "healthy":
            overall_status = "healthy"
            message = "Vault ist vollständig funktionsfähig"
        elif secrets_status == "unhealthy":
            overall_status = "degraded"
            message = "Vault ist verbunden, aber KV-Engine ist nicht verfügbar"
        else:
            overall_status = "degraded"
            message = "Vault-Status unbekannt"

        return VaultHealthResponse(
            status=overall_status,
            vault_enabled=True,
            vault_connected=True,
            secrets_engine_status=secrets_status,
            transit_engine_status=transit_status,
            message=message,
        )

    except Exception as e:
        logger.error("vault_health_check_failed", error=str(e))
        return VaultHealthResponse(
            status="unhealthy",
            vault_enabled=True,
            vault_connected=False,
            secrets_engine_status="unknown",
            transit_engine_status="unknown",
            message=f"Health-Check fehlgeschlagen: {str(e)}",
        )


@router.get(
    "/secrets/metadata/{path:path}",
    response_model=SecretMetadataResponse,
    summary="Secret Metadaten abrufen",
    description="Ruft Metadaten eines Secrets ab (keine sensiblen Werte).",
)
async def get_secret_metadata(
    path: str,
    current_user: User = Depends(get_current_admin_user),
) -> SecretMetadataResponse:
    """
    Ruft Metadaten eines Secrets ab.

    Zeigt nur Metadaten an, keine sensiblen Werte.
    Nur für Administratoren verfügbar.
    """
    if not settings.VAULT_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vault-Integration ist deaktiviert",
        )

    try:
        vault = VaultClient(
            vault_addr=settings.VAULT_ADDR,
            vault_token=settings.VAULT_TOKEN,
            vault_role_id=settings.VAULT_ROLE_ID,
            vault_secret_id=settings.VAULT_SECRET_ID,
            vault_namespace=settings.VAULT_NAMESPACE,
            verify_ssl=settings.VAULT_VERIFY_SSL,
        )

        if not vault.connect():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Verbindung zu Vault fehlgeschlagen",
            )

        # Hole Secret-Daten (nur für Metadaten)
        secret_data = vault.get_secret(
            path=path,
            mount_point=settings.VAULT_MOUNT_POINT,
        )

        if secret_data is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Secret nicht gefunden: {path}",
            )

        # Hole Metadaten separat
        try:
            metadata = vault._client.secrets.kv.v2.read_secret_metadata(
                path=path,
                mount_point=settings.VAULT_MOUNT_POINT,
            )
            current_version = metadata.get("data", {}).get("current_version", 1)
            created_time = metadata.get("data", {}).get("created_time")
            updated_time = metadata.get("data", {}).get("updated_time")
        except Exception:
            current_version = 1
            created_time = None
            updated_time = None

        # Nur Schlüsselnamen zurückgeben, keine Werte!
        keys = list(secret_data.keys()) if isinstance(secret_data, dict) else []

        logger.info(
            "vault_secret_metadata_accessed",
            path=path,
            user_id=str(current_user.id),
            keys_count=len(keys),
        )

        return SecretMetadataResponse(
            path=path,
            version=current_version,
            created_time=created_time,
            last_updated=updated_time,
            keys=keys,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("vault_metadata_fetch_failed", path=path, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Abrufen der Metadaten: {str(e)}",
        )


@router.post(
    "/refresh",
    summary="Secrets aktualisieren",
    description="Lädt Secrets aus Vault neu (für Runtime-Rotation).",
)
async def refresh_secrets(
    current_user: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """
    Lädt Secrets aus Vault neu.

    Nur für Administratoren verfügbar.
    Nützlich nach Secret-Rotation in Vault.
    """
    if not settings.VAULT_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vault-Integration ist deaktiviert",
        )

    try:
        success = settings.refresh_secrets()

        if success:
            logger.info(
                "vault_secrets_refreshed",
                user_id=str(current_user.id),
            )
            return {
                "status": "success",
                "message": "Secrets wurden erfolgreich aktualisiert",
                "timestamp": datetime.utcnow().isoformat(),
            }
        else:
            return {
                "status": "no_change",
                "message": "Keine neuen Secrets geladen",
                "timestamp": datetime.utcnow().isoformat(),
            }

    except Exception as e:
        logger.error("vault_secrets_refresh_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Aktualisieren der Secrets: {str(e)}",
        )
