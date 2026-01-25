# -*- coding: utf-8 -*-
"""
Team & Collaboration Models fuer Ablage-System.

Matrix-Team-Struktur mit:
- Departments (permanente Abteilungen)
- Project Teams (temporaere Projektteams)
- Hierarchische Struktur (Parent-Child)
- Flexible Mitgliedschaften mit Rollen
- Zeitlich begrenzte Zuordnungen

Phase 3.1 der Strategischen Roadmap (Januar 2026).
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List
import uuid

from sqlalchemy import (
    Column,
    String,
    Integer,
    Boolean,
    Text,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
    CheckConstraint,
    Enum as SQLAlchemyEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


# ============================================================================
# Enums
# ============================================================================


class TeamType(str, Enum):
    """Team-Typ fuer Matrix-Struktur."""
    DEPARTMENT = "department"     # Permanente Abteilung
    PROJECT = "project"           # Temporaeres Projektteam
    WORKING_GROUP = "working_group"  # Arbeitsgruppe
    COMMITTEE = "committee"       # Ausschuss/Gremium
    VIRTUAL = "virtual"           # Virtuelles Team (standortuebergreifend)


class TeamMemberRole(str, Enum):
    """Rolle eines Teammitglieds."""
    MEMBER = "member"     # Normales Mitglied
    LEAD = "lead"         # Teamleiter
    ADMIN = "admin"       # Administrator (kann Mitglieder verwalten)
    DEPUTY = "deputy"     # Stellvertreter des Leiters
    OBSERVER = "observer" # Beobachter (nur Lesezugriff)


class TeamStatus(str, Enum):
    """Status eines Teams."""
    ACTIVE = "active"         # Aktiv
    INACTIVE = "inactive"     # Inaktiv (temporaer pausiert)
    ARCHIVED = "archived"     # Archiviert
    PENDING = "pending"       # Genehmigung ausstehend


class TeamVisibility(str, Enum):
    """Sichtbarkeit eines Teams."""
    PUBLIC = "public"       # Fuer alle sichtbar
    PRIVATE = "private"     # Nur fuer Mitglieder sichtbar
    COMPANY = "company"     # Fuer die gesamte Company sichtbar


# ============================================================================
# Team Model
# ============================================================================


class Team(Base):
    """Team fuer Kollaboration und Zugriffssteuerung.

    Unterstuetzt Matrix-Struktur:
    - Departments: Permanente organisatorische Einheiten
    - Projects: Temporaere Teams mit Enddatum
    - Hierarchie: Parent-Child Beziehungen

    Features:
    - Mitglieder mit verschiedenen Rollen
    - Temporaere Mitgliedschaften
    - Team-spezifische Berechtigungen
    - Aktivitaets-Tracking
    """
    __tablename__ = "teams"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identifikation
    name = Column(String(255), nullable=False)
    code = Column(String(50), nullable=True, index=True)  # Kurzcode (z.B. "DEV", "SALES")
    description = Column(Text, nullable=True)

    # Team-Typ
    team_type = Column(
        SQLAlchemyEnum(TeamType, name="team_type"),
        nullable=False,
        default=TeamType.DEPARTMENT
    )

    # Hierarchie
    parent_team_id = Column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    level = Column(Integer, default=0)  # Hierarchie-Ebene (0 = Root)
    path = Column(String(500), nullable=True)  # Materialized Path: "uuid1/uuid2/uuid3"

    # Company (Multi-Tenant)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Status & Sichtbarkeit
    status = Column(
        SQLAlchemyEnum(TeamStatus, name="team_status"),
        nullable=False,
        default=TeamStatus.ACTIVE
    )
    visibility = Column(
        SQLAlchemyEnum(TeamVisibility, name="team_visibility"),
        nullable=False,
        default=TeamVisibility.COMPANY
    )

    # Zeitliche Begrenzung (fuer Projektteams)
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)

    # Team-Einstellungen
    settings = Column(CrossDBJSON, default=dict)
    # Format: {
    #   "allow_self_join": false,
    #   "require_approval": true,
    #   "max_members": 50,
    #   "default_role": "member",
    #   "notification_preferences": {...}
    # }

    # Berechtigungen (Team-weite Defaults)
    default_permissions = Column(CrossDBJSON, default=list)
    # Format: ["documents:read", "documents:comment", ...]

    # Tags fuer Filterung
    tags = Column(CrossDBJSON, default=list)

    # Kontaktinformationen
    email = Column(String(255), nullable=True)  # Team-Email
    slack_channel = Column(String(100), nullable=True)  # Slack-Kanal
    external_id = Column(String(100), nullable=True)  # ID in externem System

    # Statistiken (cached)
    member_count = Column(Integer, default=0)
    active_member_count = Column(Integer, default=0)

    # Verantwortung
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Metadata
    metadata_json = Column(CrossDBJSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    archived_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    parent_team = relationship(
        "Team",
        remote_side="Team.id",
        backref="child_teams"
    )
    company = relationship("Company", backref="teams")
    created_by = relationship("User", foreign_keys=[created_by_id], backref="created_teams")
    memberships = relationship(
        "TeamMembership",
        back_populates="team",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_team_company_code"),
        Index("ix_team_company_status", "company_id", "status"),
        Index("ix_team_company_type", "company_id", "team_type"),
        Index("ix_team_parent", "parent_team_id"),
        Index("ix_team_path", "path"),
        CheckConstraint(
            "(end_date IS NULL) OR (start_date IS NULL) OR (end_date > start_date)",
            name="ck_team_date_range"
        ),
    )

    @property
    def is_active(self) -> bool:
        """Prueft ob Team aktiv ist."""
        if self.status != TeamStatus.ACTIVE:
            return False
        now = datetime.utcnow()
        if self.start_date and now < self.start_date:
            return False
        if self.end_date and now > self.end_date:
            return False
        return True

    @property
    def is_project(self) -> bool:
        """Prueft ob es ein Projektteam ist."""
        return self.team_type == TeamType.PROJECT

    @property
    def is_department(self) -> bool:
        """Prueft ob es eine Abteilung ist."""
        return self.team_type == TeamType.DEPARTMENT


# ============================================================================
# TeamMembership Model
# ============================================================================


class TeamMembership(Base):
    """Mitgliedschaft eines Users in einem Team.

    Features:
    - Verschiedene Rollen (Member, Lead, Admin)
    - Zeitlich begrenzte Mitgliedschaften
    - Mehrfache Mitgliedschaften moeglich (Matrix)
    - Audit-Trail fuer Aenderungen
    """
    __tablename__ = "team_memberships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Zuordnung
    team_id = Column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Rolle
    role = Column(
        SQLAlchemyEnum(TeamMemberRole, name="team_member_role"),
        nullable=False,
        default=TeamMemberRole.MEMBER
    )

    # Zeitliche Begrenzung
    valid_from = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    valid_until = Column(DateTime(timezone=True), nullable=True)  # NULL = unbegrenzt

    # Status
    is_active = Column(Boolean, default=True)
    is_primary = Column(Boolean, default=False)  # Hauptteam des Users

    # Zusaetzliche Berechtigungen (ueber Rolle hinaus)
    additional_permissions = Column(CrossDBJSON, default=list)

    # Mitgliedschafts-Details
    title = Column(String(100), nullable=True)  # Funktion/Titel im Team
    department = Column(String(100), nullable=True)  # Wenn in Projektteam: Herkunfts-Abteilung
    allocation_percent = Column(Integer, default=100)  # Anteil Zuordnung (z.B. 50% fuer Projekt)

    # Einladung/Beitritt
    invited_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    invitation_status = Column(String(20), default="accepted")  # pending, accepted, declined
    invitation_sent_at = Column(DateTime(timezone=True), nullable=True)
    joined_at = Column(DateTime(timezone=True), server_default=func.now())

    # Benachrichtigungen
    notification_preferences = Column(CrossDBJSON, default=dict)
    # Format: {
    #   "email_digest": "daily",
    #   "activity_notifications": true,
    #   "mention_notifications": true
    # }

    # Grund fuer Mitgliedschaft (Audit)
    reason = Column(Text, nullable=True)  # z.B. "Projektzuordnung Q1"

    # Metadata
    metadata_json = Column(CrossDBJSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    left_at = Column(DateTime(timezone=True), nullable=True)  # Wann Team verlassen

    # Relationships
    team = relationship("Team", back_populates="memberships")
    user = relationship("User", foreign_keys=[user_id], backref="team_memberships")
    invited_by = relationship("User", foreign_keys=[invited_by_id])

    __table_args__ = (
        # Ein User kann nur einmal pro Team Mitglied sein
        UniqueConstraint(
            "team_id", "user_id",
            name="uq_membership_team_user"
        ),
        Index("ix_membership_user_active", "user_id", "is_active"),
        Index("ix_membership_team_role", "team_id", "role"),
        Index("ix_membership_valid", "valid_from", "valid_until"),
        CheckConstraint(
            "(valid_until IS NULL) OR (valid_until > valid_from)",
            name="ck_membership_validity"
        ),
        CheckConstraint(
            "allocation_percent >= 0 AND allocation_percent <= 100",
            name="ck_membership_allocation"
        ),
    )

    @property
    def is_currently_valid(self) -> bool:
        """Prueft ob Mitgliedschaft aktuell gueltig ist."""
        if not self.is_active:
            return False
        now = datetime.utcnow()
        if now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        return True

    @property
    def is_leader(self) -> bool:
        """Prueft ob Mitglied ein Leader ist."""
        return self.role in (TeamMemberRole.LEAD, TeamMemberRole.ADMIN)

    @property
    def can_manage_members(self) -> bool:
        """Prueft ob Mitglied andere verwalten kann."""
        return self.role == TeamMemberRole.ADMIN


# ============================================================================
# TeamActivity Model (Aktivitaets-Tracking)
# ============================================================================


class TeamActivityType(str, Enum):
    """Typ einer Team-Aktivitaet."""
    MEMBER_JOINED = "member_joined"
    MEMBER_LEFT = "member_left"
    MEMBER_ROLE_CHANGED = "member_role_changed"
    TEAM_CREATED = "team_created"
    TEAM_UPDATED = "team_updated"
    TEAM_ARCHIVED = "team_archived"
    DOCUMENT_SHARED = "document_shared"
    TASK_ASSIGNED = "task_assigned"
    COMMENT_ADDED = "comment_added"
    MENTION = "mention"
    MILESTONE_REACHED = "milestone_reached"


class TeamActivity(Base):
    """Aktivitaets-Log fuer ein Team.

    Trackt alle relevanten Ereignisse innerhalb eines Teams
    fuer Activity Feed und Audit.
    """
    __tablename__ = "team_activities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Team-Zuordnung
    team_id = Column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Aktivitaets-Typ
    activity_type = Column(
        SQLAlchemyEnum(TeamActivityType, name="team_activity_type"),
        nullable=False
    )

    # Actor (wer hat die Aktion ausgefuehrt)
    actor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # Target (auf wen/was bezieht sich die Aktion)
    target_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    target_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True
    )
    target_entity_type = Column(String(50), nullable=True)  # z.B. "task", "comment"
    target_entity_id = Column(UUID(as_uuid=True), nullable=True)

    # Beschreibung
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Details (strukturiert)
    details = Column(CrossDBJSON, default=dict)
    # Format: {
    #   "old_role": "member",
    #   "new_role": "lead",
    #   "document_name": "Rechnung.pdf",
    #   ...
    # }

    # Sichtbarkeit
    is_public = Column(Boolean, default=True)  # Im Activity Feed anzeigen
    visibility = Column(
        SQLAlchemyEnum(TeamVisibility, name="activity_visibility"),
        nullable=False,
        default=TeamVisibility.COMPANY
    )

    # Mentions
    mentioned_user_ids = Column(CrossDBJSON, default=list)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    ip_address = Column(String(45), nullable=True)  # IPv6-kompatibel
    user_agent = Column(String(500), nullable=True)

    # Relationships
    team = relationship("Team", backref="activities")
    actor = relationship("User", foreign_keys=[actor_id], backref="team_activities")
    target_user = relationship("User", foreign_keys=[target_user_id])
    target_document = relationship("Document", backref="team_activities")

    __table_args__ = (
        Index("ix_activity_team_created", "team_id", "created_at"),
        Index("ix_activity_actor_created", "actor_id", "created_at"),
        Index("ix_activity_type_created", "activity_type", "created_at"),
    )


# ============================================================================
# TeamInvitation Model
# ============================================================================


class InvitationStatus(str, Enum):
    """Status einer Team-Einladung."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class TeamInvitation(Base):
    """Einladung zu einem Team.

    Ermoeglicht:
    - Einladung per Email (auch externe User)
    - Zeitlich begrenzte Einladungen
    - Tracking von Einladungs-Status
    """
    __tablename__ = "team_invitations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Team-Zuordnung
    team_id = Column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Einladender
    invited_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Eingeladener (entweder user_id oder email)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    email = Column(String(255), nullable=True)  # Fuer externe Einladungen

    # Geplante Rolle
    role = Column(
        SQLAlchemyEnum(TeamMemberRole, name="invitation_role"),
        nullable=False,
        default=TeamMemberRole.MEMBER
    )

    # Status
    status = Column(
        SQLAlchemyEnum(InvitationStatus, name="invitation_status"),
        nullable=False,
        default=InvitationStatus.PENDING
    )

    # Token fuer Einladungs-Link
    token = Column(String(100), unique=True, nullable=False)

    # Zeitliche Begrenzung
    expires_at = Column(DateTime(timezone=True), nullable=False)

    # Nachricht
    personal_message = Column(Text, nullable=True)

    # Response
    responded_at = Column(DateTime(timezone=True), nullable=True)
    decline_reason = Column(Text, nullable=True)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    team = relationship("Team", backref="invitations")
    invited_by = relationship("User", foreign_keys=[invited_by_id])
    user = relationship("User", foreign_keys=[user_id], backref="team_invitations")

    __table_args__ = (
        Index("ix_invitation_team_status", "team_id", "status"),
        Index("ix_invitation_email", "email"),
        Index("ix_invitation_token", "token"),
        CheckConstraint(
            "user_id IS NOT NULL OR email IS NOT NULL",
            name="ck_invitation_target"
        ),
    )

    @property
    def is_expired(self) -> bool:
        """Prueft ob Einladung abgelaufen ist."""
        return datetime.utcnow() > self.expires_at


# ============================================================================
# TeamDocument Model (Team-Dokument-Verknuepfung)
# ============================================================================


class TeamDocumentPermission(str, Enum):
    """Berechtigung fuer Team-Dokument."""
    READ = "read"
    COMMENT = "comment"
    EDIT = "edit"
    FULL = "full"


class TeamDocument(Base):
    """Verknuepfung zwischen Team und Dokument.

    Ermoeglicht:
    - Team-weite Dokument-Freigaben
    - Differenzierte Berechtigungen
    - Tracking von geteilten Dokumenten
    """
    __tablename__ = "team_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Zuordnung
    team_id = Column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Wer hat geteilt
    shared_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Berechtigung
    permission = Column(
        SQLAlchemyEnum(TeamDocumentPermission, name="team_document_permission"),
        nullable=False,
        default=TeamDocumentPermission.READ
    )

    # Zeitliche Begrenzung (optional)
    valid_until = Column(DateTime(timezone=True), nullable=True)

    # Notiz
    note = Column(Text, nullable=True)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    team = relationship("Team", backref="team_documents")
    document = relationship("Document", backref="team_shares")
    shared_by = relationship("User", backref="shared_team_documents")

    __table_args__ = (
        UniqueConstraint("team_id", "document_id", name="uq_team_document"),
        Index("ix_team_doc_document", "document_id"),
    )
