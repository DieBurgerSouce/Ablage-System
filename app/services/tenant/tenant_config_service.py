"""
Service fuer Mandanten-Konfiguration und Feature-Verwaltung.

Verwaltet Feature-Flags, Kontingente und Mandanten-Status.
"""

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Optional
from uuid import UUID

from app.db.models_tenant_config import TenantConfig
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


class TenantConfigService:
    """
    Service fuer Mandanten-Konfiguration und Feature-Verwaltung.

    Verwaltet:
    - Feature-Flags pro Mandant
    - Kontingente und Quota-Pruefung
    - Branding-Einstellungen
    - Mandanten-Aktivierung/-Deaktivierung
    """

    def __init__(self, db: AsyncSession):
        """
        Initialisiert den Service.

        Args:
            db: Async Database Session
        """
        self.db = db

    async def get_tenant_config(self, company_id: UUID) -> Optional[TenantConfig]:
        """
        Holt die Konfiguration eines Mandanten.

        Args:
            company_id: UUID des Mandanten

        Returns:
            TenantConfig oder None wenn nicht gefunden
        """
        try:
            stmt = select(TenantConfig).where(TenantConfig.company_id == company_id)
            result = await self.db.execute(stmt)
            config = result.scalar_one_or_none()

            if config:
                logger.debug(
                    "tenant_config_retrieved",
                    company_id=str(company_id),
                    is_active=config.is_active,
                )

            return config

        except Exception as e:
            logger.error(
                "get_tenant_config_failed",
                **safe_error_log(e),
                company_id=str(company_id),
            )
            return None

    async def create_or_update_config(
        self,
        company_id: UUID,
        features: Optional[Dict[str, object]] = None,
        quotas: Optional[Dict[str, object]] = None,
        branding: Optional[Dict[str, object]] = None,
    ) -> TenantConfig:
        """
        Erstellt oder aktualisiert die Mandanten-Konfiguration.

        Args:
            company_id: UUID des Mandanten
            features: Feature-Flags (optional)
            quotas: Kontingente (optional)
            branding: Branding-Einstellungen (optional)

        Returns:
            Aktualisierte TenantConfig

        Raises:
            ValueError: Bei ungueltigen Eingaben
        """
        try:
            # Hole existierende Konfiguration
            config = await self.get_tenant_config(company_id)

            if config is None:
                # Erstelle neue Konfiguration
                config = TenantConfig(
                    company_id=company_id,
                    features=features or {},
                    quotas=quotas or {},
                    branding=branding or {},
                    is_active=True,
                )
                self.db.add(config)

                logger.info(
                    "tenant_config_created",
                    company_id=str(company_id),
                )
            else:
                # Aktualisiere existierende Konfiguration
                if features is not None:
                    config.features = {**(config.features or {}), **features}
                if quotas is not None:
                    config.quotas = {**(config.quotas or {}), **quotas}
                if branding is not None:
                    config.branding = {**(config.branding or {}), **branding}

                logger.info(
                    "tenant_config_updated",
                    company_id=str(company_id),
                )

            await self.db.commit()
            await self.db.refresh(config)

            return config

        except Exception as e:
            await self.db.rollback()
            logger.error(
                "create_or_update_config_failed",
                **safe_error_log(e),
                company_id=str(company_id),
            )
            raise ValueError(f"Fehler beim Speichern der Mandanten-Konfiguration: {str(e)}")

    async def get_tenant_features(self, company_id: UUID) -> Dict[str, bool]:
        """
        Gibt die Feature-Flags eines Mandanten zurueck.

        Args:
            company_id: UUID des Mandanten

        Returns:
            Dictionary mit Feature-Flags (z.B. {"ocr_enabled": true})
        """
        try:
            config = await self.get_tenant_config(company_id)

            if config is None or config.features is None:
                logger.debug(
                    "no_tenant_features",
                    company_id=str(company_id),
                )
                return {}

            # Nur boolean Features zurueckgeben
            features = config.features or {}
            return {k: bool(v) for k, v in features.items() if isinstance(v, bool)}

        except Exception as e:
            logger.error(
                "get_tenant_features_failed",
                **safe_error_log(e),
                company_id=str(company_id),
            )
            return {}

    async def check_tenant_quota(
        self,
        company_id: UUID,
        resource: str,
        current_usage: int,
    ) -> Dict[str, object]:
        """
        Prueft ob ein Mandant innerhalb seiner Kontingente liegt.

        Args:
            company_id: UUID des Mandanten
            resource: Name der Ressource (z.B. "documents_per_month")
            current_usage: Aktuelle Nutzung

        Returns:
            Dictionary mit Quota-Status:
            {
                "within_quota": bool,
                "limit": int,
                "usage": int,
                "remaining": int
            }
        """
        try:
            config = await self.get_tenant_config(company_id)

            if config is None or config.quotas is None:
                # Keine Quota-Limits definiert = unbegrenzt
                logger.debug(
                    "no_quota_limits",
                    company_id=str(company_id),
                    resource=resource,
                )
                return {
                    "within_quota": True,
                    "limit": -1,  # -1 = unbegrenzt
                    "usage": current_usage,
                    "remaining": -1,
                }

            quotas = config.quotas or {}
            limit = quotas.get(resource)

            if limit is None:
                # Ressource nicht limitiert
                return {
                    "within_quota": True,
                    "limit": -1,
                    "usage": current_usage,
                    "remaining": -1,
                }

            # Pruefe ob innerhalb des Limits
            limit_int = int(limit)
            within_quota = current_usage <= limit_int
            remaining = max(0, limit_int - current_usage)

            logger.debug(
                "quota_checked",
                company_id=str(company_id),
                resource=resource,
                within_quota=within_quota,
                usage=current_usage,
                limit=limit_int,
            )

            return {
                "within_quota": within_quota,
                "limit": limit_int,
                "usage": current_usage,
                "remaining": remaining,
            }

        except Exception as e:
            logger.error(
                "check_tenant_quota_failed",
                **safe_error_log(e),
                company_id=str(company_id),
                resource=resource,
            )
            # Bei Fehler: Quota verweigern (fail-closed fuer Enterprise Security)
            return {
                "within_quota": False,
                "limit": -1,
                "usage": current_usage,
                "remaining": -1,
            }

    async def deactivate_tenant(self, company_id: UUID) -> bool:
        """
        Deaktiviert einen Mandanten.

        Ein deaktivierter Mandant kann sich nicht mehr einloggen
        und hat keinen Zugriff auf seine Daten.

        Args:
            company_id: UUID des Mandanten

        Returns:
            True wenn erfolgreich, False bei Fehler
        """
        try:
            config = await self.get_tenant_config(company_id)

            if config is None:
                # Erstelle deaktivierte Konfiguration
                config = TenantConfig(
                    company_id=company_id,
                    features={},
                    quotas={},
                    branding={},
                    is_active=False,
                )
                self.db.add(config)
            else:
                # Deaktiviere existierende Konfiguration
                config.is_active = False

            await self.db.commit()

            logger.warning(
                "tenant_deactivated",
                company_id=str(company_id),
            )

            return True

        except Exception as e:
            await self.db.rollback()
            logger.error(
                "deactivate_tenant_failed",
                **safe_error_log(e),
                company_id=str(company_id),
            )
            return False

    async def activate_tenant(self, company_id: UUID) -> bool:
        """
        Aktiviert einen Mandanten.

        Args:
            company_id: UUID des Mandanten

        Returns:
            True wenn erfolgreich, False bei Fehler
        """
        try:
            config = await self.get_tenant_config(company_id)

            if config is None:
                # Erstelle aktivierte Konfiguration
                config = TenantConfig(
                    company_id=company_id,
                    features={},
                    quotas={},
                    branding={},
                    is_active=True,
                )
                self.db.add(config)
            else:
                # Aktiviere existierende Konfiguration
                config.is_active = True

            await self.db.commit()

            logger.info(
                "tenant_activated",
                company_id=str(company_id),
            )

            return True

        except Exception as e:
            await self.db.rollback()
            logger.error(
                "activate_tenant_failed",
                **safe_error_log(e),
                company_id=str(company_id),
            )
            return False


def get_tenant_config_service(db: AsyncSession) -> TenantConfigService:
    """
    Factory fuer TenantConfigService.

    Args:
        db: Async Database Session

    Returns:
        TenantConfigService Instanz
    """
    return TenantConfigService(db)
