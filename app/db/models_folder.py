"""
Folder hierarchy satellite model.

Separates Ordner-Modell fuer die geschaeftliche Dokumentenablage.
Unterstuetzt hierarchische Ordnerstrukturen mit Materialized Path,
Berechtigungsvererbung und Drag-Drop Reorganisation.

Nicht zu verwechseln mit PrivatFolder (models.py) - dieser ist fuer
den privaten Bereich (PrivatSpace) gedacht.
"""

import uuid
from enum import Enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


# ============================================================================
# Enums
# ============================================================================


class FolderType(str, Enum):
    """Ordner-Typen fuer die geschaeftliche Ablage."""
    GESCHAEFTLICH = "geschaeftlich"
    ARCHIV = "archiv"
    PROJEKT = "projekt"
    EINGANG = "eingang"
    AUSGANG = "ausgang"
    CUSTOM = "custom"


class FolderPermissionLevel(str, Enum):
    """Berechtigungsstufen fuer Ordner."""
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


# ============================================================================
# Folder Model
# ============================================================================


class Folder(Base):
    """Geschaeftliche Ordnerstruktur mit Materialized Path.

    Bietet hierarchische Ordner fuer die Dokumentenablage mit:
    - Verschachtelung ueber parent_id (Self-Referential FK)
    - Materialized Path fuer schnelle Ancestor/Descendant Queries
    - Berechtigungsvererbung ueber FolderPermission
    - Soft Delete (deleted_at)
    - Company-Scoping fuer Multi-Tenancy
    """
    __tablename__ = "folders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        comment="Multi-Tenant Isolation",
    )
    parent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("folders.id", ondelete="CASCADE"),
        nullable=True,
        comment="NULL = Root-Ordner",
    )

    # Ordner-Info
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(50), default="Folder")
    color = Column(String(7), nullable=True, comment="Hex-Farbcode z.B. #3B82F6")

    # Materialized Path: /root-id/child-id/grandchild-id
    path = Column(
        String(4000),
        nullable=False,
        comment="Materialized Path fuer schnelle Hierarchie-Queries",
    )
    level = Column(Integer, default=0, comment="Verschachtelungstiefe (0 = Root)")

    # Sortierung
    sort_order = Column(Integer, default=0)

    # Typ und Metadaten
    folder_type = Column(
        String(50),
        default=FolderType.GESCHAEFTLICH.value,
        nullable=False,
    )
    folder_metadata = Column(CrossDBJSON, default=dict, comment="Erweiterbare Metadaten")

    # Statistiken (denormalisiert fuer Performance)
    document_count = Column(Integer, default=0)
    subfolder_count = Column(Integer, default=0)

    # Sperrung
    is_locked = Column(
        Boolean,
        default=False,
        comment="Gesperrte Ordner koennen nicht veraendert werden",
    )

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    deleted_at = Column(DateTime(timezone=True), nullable=True, comment="Soft Delete")

    # Relationships
    parent = relationship(
        "Folder",
        remote_side=[id],
        back_populates="children",
    )
    children = relationship(
        "Folder",
        back_populates="parent",
        cascade="all, delete-orphan",
        order_by="Folder.sort_order",
    )
    created_by = relationship("User", foreign_keys=[created_by_id])
    permissions = relationship(
        "FolderPermission",
        back_populates="folder",
        cascade="all, delete-orphan",
    )
    folder_documents = relationship(
        "FolderDocument",
        back_populates="folder",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_folders_company_id", "company_id"),
        Index("ix_folders_parent_id", "parent_id"),
        Index("ix_folders_path", "path"),
        Index("ix_folders_folder_type", "folder_type"),
        Index("ix_folders_deleted_at", "deleted_at"),
        Index("ix_folders_company_parent", "company_id", "parent_id"),
        Index("ix_folders_company_name", "company_id", "name"),
        Index("ix_folders_sort_order", "parent_id", "sort_order"),
    )

    def __repr__(self) -> str:
        return f"<Folder(id={self.id}, name='{self.name}', path='{self.path}')>"


# ============================================================================
# Folder Permission Model
# ============================================================================


class FolderPermission(Base):
    """Berechtigungen fuer Ordner-Zugriff.

    Unterstuetzt direkte und vererbte Berechtigungen:
    - Direkte: Explizit fuer diesen Ordner gesetzt
    - Vererbt: Von einem uebergeordneten Ordner geerbt
    """
    __tablename__ = "folder_permissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    folder_id = Column(
        UUID(as_uuid=True),
        ForeignKey("folders.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    permission_level = Column(
        String(20),
        default=FolderPermissionLevel.READ.value,
        nullable=False,
    )
    inherited = Column(
        Boolean,
        default=False,
        comment="True wenn von uebergeordnetem Ordner geerbt",
    )
    inherited_from_id = Column(
        UUID(as_uuid=True),
        ForeignKey("folders.id", ondelete="CASCADE"),
        nullable=True,
        comment="Quell-Ordner bei Vererbung",
    )

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    granted_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    folder = relationship("Folder", back_populates="permissions", foreign_keys=[folder_id])
    user = relationship("User", foreign_keys=[user_id])
    granted_by = relationship("User", foreign_keys=[granted_by_id])

    __table_args__ = (
        UniqueConstraint("folder_id", "user_id", name="uq_folder_user_permission"),
        Index("ix_folder_permissions_folder_id", "folder_id"),
        Index("ix_folder_permissions_user_id", "user_id"),
        Index("ix_folder_permissions_inherited", "inherited"),
    )


# ============================================================================
# Folder-Document Association Model
# ============================================================================


class FolderDocument(Base):
    """Zuordnung von Dokumenten zu Ordnern.

    Ein Dokument kann in mehreren Ordnern liegen (Referenz, nicht Kopie).
    Das primary_folder Flag zeigt den Hauptordner an.
    """
    __tablename__ = "folder_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    folder_id = Column(
        UUID(as_uuid=True),
        ForeignKey("folders.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Sortierung innerhalb des Ordners
    sort_order = Column(Integer, default=0)

    # Primaerer Ordner (ein Dokument hat genau einen Hauptordner)
    is_primary = Column(
        Boolean,
        default=True,
        comment="Primaerer Ordner fuer dieses Dokument",
    )

    # Audit
    added_at = Column(DateTime(timezone=True), server_default=func.now())
    added_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    folder = relationship("Folder", back_populates="folder_documents")
    document = relationship("Document")
    added_by = relationship("User", foreign_keys=[added_by_id])

    __table_args__ = (
        UniqueConstraint("folder_id", "document_id", name="uq_folder_document"),
        Index("ix_folder_documents_folder_id", "folder_id"),
        Index("ix_folder_documents_document_id", "document_id"),
        Index("ix_folder_documents_is_primary", "document_id", "is_primary"),
        Index("ix_folder_documents_sort_order", "folder_id", "sort_order"),
    )
