# -*- coding: utf-8 -*-
"""
Data Quality History database models.

Speichert historische Datenqualitaets-Berichte fuer Trend-Tracking:
- Gesamt-Score pro Zeitpunkt
- Issue-Zaehler pro Kategorie
- Detail-Informationen fuer Drill-Down

Feinpoliert und durchdacht - Enterprise Data Quality History.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


class DataQualityHistory(Base):
    """
    Historische Datenqualitaets-Eintraege.

    Speichert periodische Snapshots des Datenqualitaets-Scores
    und der Issues pro Company fuer Trend-Analyse.
    """

    __tablename__ = "data_quality_history"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    overall_score = Column(Float, nullable=False)
    issue_counts = Column(
        CrossDBJSON,
        default=dict,
        nullable=False,
        comment="Issue-Zaehler pro Kategorie: {'uncategorized': 5, 'duplicates': 3, ...}",
    )
    issue_details = Column(
        CrossDBJSON,
        default=list,
        nullable=False,
        comment="Vollstaendige Issue-Liste fuer Drill-Down",
    )
    checked_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        Index(
            "ix_dq_history_company_checked",
            "company_id",
            "checked_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<DataQualityHistory(company_id={self.company_id}, "
            f"score={self.overall_score}, checked_at={self.checked_at})>"
        )
