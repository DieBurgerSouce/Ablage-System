"""
Learning Autonomy satellite model.

Lernende Autonomie: Pro User + Pro Aktionstyp ein Autonomie-Level,
das mit Bestätigungen waechst.

Mechanik:
- Start: Alles auf "suggest" (Vorschlagen & Bestätigen)
- Nach N Bestätigungen desselben Musters: auto_with_undo
- User kann pro Aktion das Level manuell setzen
- Levels: manual → suggest → auto_with_undo → full_auto

Ergaenzt das bestehende Autonomy-Framework (models_autonomy.py) um
die lernende Komponente.
"""

import uuid
from enum import Enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
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

# Import canonical AutonomyDecisionLog to avoid duplicate __tablename__
from app.db.models_autonomy import AutonomyDecisionLog  # noqa: F401


# ============================================================================
# Enums
# ============================================================================


class LearningAutonomyLevel(str, Enum):
    """Autonomie-Stufen für lernende Automatisierung."""
    MANUAL = "manual"                   # User macht alles manuell
    SUGGEST = "suggest"                 # System schlaegt vor, User bestätigt
    AUTO_WITH_UNDO = "auto_with_undo"   # System führt aus, User kann zurücknehmen
    FULL_AUTO = "full_auto"             # Vollautomatisch, kein Eingriff noetig


class ActionType(str, Enum):
    """Aktionstypen für die lernende Autonomie."""
    KATEGORISIERUNG = "kategorisierung"
    ORDNER_ZUWEISUNG = "ordner_zuweisung"
    BUCHUNGSVORSCHLAG = "buchungsvorschlag"
    TAGGING = "tagging"
    MAHNSTUFE = "mahnstufe"
    OCR_BACKEND_WAHL = "ocr_backend_wahl"
    RECHNUNGSERKENNUNG = "rechnungserkennung"
    ENTITY_LINKING = "entity_linking"
    DUPLIKAT_ERKENNUNG = "duplikat_erkennung"
    ARCHIVIERUNG = "archivierung"
    EXPORT_FORMAT = "export_format"
    PRIORITAET_SETZEN = "priorität_setzen"


# ============================================================================
# User Action Autonomy (Pro User x Pro Aktionstyp)
# ============================================================================


class UserActionAutonomy(Base):
    """Autonomie-Level pro User und Aktionstyp.

    Speichert das aktuelle Level und die Lernhistorie.
    Das Level steigt automatisch mit erfolgreichen Bestätigungen
    und sinkt bei Ablehnungen/Korrekturen.
    """
    __tablename__ = "user_action_autonomy"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Aktionstyp
    action_type = Column(
        String(50),
        nullable=False,
        comment="Aktionstyp (kategorisierung, ordner_zuweisung, etc.)",
    )

    # Aktuelles Level
    current_level = Column(
        String(30),
        default=LearningAutonomyLevel.SUGGEST.value,
        nullable=False,
    )

    # Manuell gesetzt oder automatisch gelernt?
    is_manually_set = Column(
        Boolean,
        default=False,
        comment="True wenn User das Level manuell gesetzt hat",
    )

    # Lern-Metriken
    total_suggestions = Column(Integer, default=0, comment="Gesamtzahl Vorschläge")
    total_confirmations = Column(Integer, default=0, comment="Bestätigte Vorschläge")
    total_rejections = Column(Integer, default=0, comment="Abgelehnte Vorschläge")
    total_corrections = Column(Integer, default=0, comment="Korrigierte Vorschläge")
    total_auto_executed = Column(Integer, default=0, comment="Automatisch ausgeführte Aktionen")
    total_undone = Column(Integer, default=0, comment="Zurückgenommene Auto-Aktionen")

    # Streak: Aufeinanderfolgende Bestätigungen ohne Ablehnung
    current_streak = Column(Integer, default=0, comment="Aktuelle Bestätigungs-Serie")
    best_streak = Column(Integer, default=0, comment="Beste Bestätigungs-Serie")

    # Schwellenwerte für Level-Upgrade
    confirmations_for_auto_undo = Column(
        Integer,
        default=10,
        comment="Bestätigungen noetig für Upgrade zu auto_with_undo",
    )
    confirmations_for_full_auto = Column(
        Integer,
        default=50,
        comment="Bestätigungen noetig für Upgrade zu full_auto",
    )

    # Confidence-Tracking
    avg_confidence = Column(Float, default=0.0, comment="Durchschnittliche Confidence der Vorschläge")
    last_confidence = Column(Float, default=0.0, comment="Letzte Confidence")

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_interaction_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        UniqueConstraint(
            "user_id", "action_type", "company_id",
            name="uq_user_action_autonomy",
        ),
        Index("ix_user_action_autonomy_user_id", "user_id"),
        Index("ix_user_action_autonomy_company_id", "company_id"),
        Index("ix_user_action_autonomy_action_type", "action_type"),
        Index("ix_user_action_autonomy_level", "current_level"),
    )


# ============================================================================
# Autonomy Level History (Level-Änderungen)
# ============================================================================


class AutonomyLevelHistory(Base):
    """Historie der Level-Änderungen.

    Protokolliert jeden Level-Wechsel für die Vertrauenskurve.
    """
    __tablename__ = "autonomy_level_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_action_autonomy_id = Column(
        UUID(as_uuid=True),
        ForeignKey("user_action_autonomy.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Level-Wechsel
    previous_level = Column(String(30), nullable=False)
    new_level = Column(String(30), nullable=False)
    change_reason = Column(
        String(50),
        nullable=False,
        comment="streak_threshold, manual_set, rejection_downgrade, correction_downgrade",
    )

    # Metriken zum Zeitpunkt
    confirmations_at_change = Column(Integer, default=0)
    streak_at_change = Column(Integer, default=0)
    avg_confidence_at_change = Column(Float, default=0.0)

    # Audit
    changed_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_autonomy_level_history_uaa", "user_action_autonomy_id"),
        Index("ix_autonomy_level_history_time", "changed_at"),
    )
