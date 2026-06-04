# -*- coding: utf-8 -*-
"""
Dashboard Sharing Models für Ablage-System.

Persistente Dashboard-Freigaben mit Audit-Trail:
- Benutzer-basiertes Sharing mit Berechtigungen
- Ablaufdatum-Unterstützung
- Vollständiger Audit-Trail aller Freigabe-Aktionen
- Eindeutigkeit pro Dashboard-Benutzer-Paar

Feinpoliert und durchdacht - Enterprise-grade Dashboard Sharing.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    String,
    Boolean,
    Integer,
    Text,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


class UserDashboard(Base):
    """Benutzer-Dashboard (Tabelle ``user_dashboards``).

    Modell fuer die zuvor verwaiste Tabelle ``user_dashboards`` (FK-Ziel von
    ``DashboardShare.dashboard_id``). Ohne dieses Modell scheiterte
    ``Base.metadata.create_all`` (NoReferencedTableError). Spalten reverse-engineered
    aus dem realen Schema.
    """

    __tablename__ = "user_dashboards"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(String(500), nullable=True)
    is_default = Column(Boolean, nullable=False, default=False)
    columns = Column(Integer, nullable=False, default=12)
    row_height = Column(Integer, nullable=False, default=80)
    compact_type = Column(String(20), nullable=True)
    default_date_range = Column(String(50), nullable=True)
    default_company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True)
    is_shared = Column(Boolean, nullable=False, default=False)
    shared_with_roles = Column(CrossDBJSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    is_favorite = Column(Boolean, nullable=False, default=False)


class DashboardShare(Base):
    """
    Persistente Dashboard-Freigaben.

    Erlaubt Sharing von Dashboards mit anderen Benutzern:
    - View-Berechtigung (nur ansehen)
    - Edit-Berechtigung (bearbeiten)
    - Optionales Ablaufdatum
    - Soft-Delete via is_active Flag
    """
    __tablename__ = "dashboard_shares"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Eindeutige ID der Freigabe"
    )
    dashboard_id = Column(
        UUID(as_uuid=True),
        ForeignKey("user_dashboards.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="ID des geteilten Dashboards (user_dashboards.id)"
    )
    shared_with_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Benutzer mit dem das Dashboard geteilt wurde"
    )
    shared_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        comment="Benutzer der das Dashboard geteilt hat"
    )
    permission = Column(
        String(10),
        nullable=False,
        default="view",
        comment="Berechtigungsstufe: view oder edit"
    )
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Ist die Freigabe aktiv? (Soft Delete)"
    )
    expires_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Optional: Ablaufdatum der Freigabe"
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Zeitpunkt der Freigabe"
    )

    # Relationships
    shared_with_user = relationship(
        "User",
        foreign_keys=[shared_with_user_id],
        backref="received_dashboard_shares"
    )
    shared_by_user = relationship(
        "User",
        foreign_keys=[shared_by_user_id],
        backref="created_dashboard_shares"
    )

    # Constraints und Indexes
    __table_args__ = (
        UniqueConstraint(
            "dashboard_id",
            "shared_with_user_id",
            name="uq_dashboard_share_user"
        ),
        Index("ix_dashboard_shares_active", "dashboard_id", "is_active"),
        Index("ix_dashboard_shares_expires", "expires_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<DashboardShare(id={self.id}, dashboard_id={self.dashboard_id}, "
            f"shared_with={self.shared_with_user_id}, permission={self.permission})>"
        )


class DashboardShareAudit(Base):
    """
    Audit-Trail für Dashboard-Freigabe-Aktionen.

    Protokolliert alle Änderungen an Freigaben:
    - Neue Freigabe erstellt
    - Freigabe entfernt
    - Berechtigung geändert
    - Zusätzliche Details in JSONB
    """
    __tablename__ = "dashboard_share_audits"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Eindeutige Audit-ID"
    )
    dashboard_share_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dashboard_shares.id", ondelete="SET NULL"),
        nullable=True,
        comment="Referenz zur Freigabe (kann NULL sein bei Löschung)"
    )
    dashboard_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Dashboard-ID (immer gesetzt)"
    )
    action = Column(
        String(30),
        nullable=False,
        comment="Aktion: shared, unshared, permission_changed"
    )
    performed_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        comment="Benutzer der die Aktion durchgeführt hat"
    )
    details = Column(
        CrossDBJSON,
        nullable=True,
        comment="Zusätzliche Details zur Aktion (alte/neue Werte, etc.)"
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Zeitpunkt der Aktion"
    )

    # Relationships
    dashboard_share = relationship("DashboardShare", backref="audit_entries")
    performed_by = relationship("User", backref="dashboard_share_audit_actions")

    # Indexes
    __table_args__ = (
        Index("ix_dashboard_share_audits_dashboard", "dashboard_id"),
        Index("ix_dashboard_share_audits_action", "action"),
        Index("ix_dashboard_share_audits_created", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<DashboardShareAudit(id={self.id}, action={self.action}, "
            f"dashboard_id={self.dashboard_id})>"
        )
