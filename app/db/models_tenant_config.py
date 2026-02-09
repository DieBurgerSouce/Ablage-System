"""
Tenant-Konfigurations-Modell fuer Multi-Tenancy.

Verwaltet Feature-Flags, Kontingente und Branding pro Mandant.
"""

import uuid
from datetime import datetime
from typing import Dict, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    func,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.models import Base, CrossDBJSON


class TenantConfig(Base):
    """
    Mandanten-Konfiguration fuer Feature-Flags und Kontingente.

    Jeder Mandant (Company) kann eigene Konfigurationen haben:
    - Feature-Flags (z.B. OCR aktiviert, DATEV-Integration)
    - Kontingente (z.B. max. Dokumente pro Monat, Speicherplatz)
    - Branding (z.B. Logo-URL, Farben)

    RLS: Diese Tabelle selbst benoetigt keine RLS, da sie nur von
    System-Admins verwaltet wird. Der Zugriff erfolgt ueber die
    Admin-API mit Superuser-Berechtigung.
    """

    __tablename__ = "tenant_configs"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    features = Column(
        CrossDBJSON,
        nullable=True,
        default=dict,
        comment="Feature-Flags (z.B. {'ocr_enabled': true, 'max_users': 50})",
    )

    quotas = Column(
        CrossDBJSON,
        nullable=True,
        default=dict,
        comment="Kontingente (z.B. {'documents_per_month': 10000, 'storage_gb': 100})",
    )

    branding = Column(
        CrossDBJSON,
        nullable=True,
        default=dict,
        comment="Branding-Konfiguration (z.B. {'logo_url': '...', 'primary_color': '#...'})",
    )

    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="Mandant aktiv (false = deaktiviert, keine Zugriffe)",
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("ix_tenant_configs_company_id", "company_id"),
        Index("ix_tenant_configs_is_active", "is_active"),
    )

    def __repr__(self) -> str:
        """String-Repraesentation."""
        return (
            f"<TenantConfig(id={self.id}, company_id={self.company_id}, "
            f"is_active={self.is_active})>"
        )
