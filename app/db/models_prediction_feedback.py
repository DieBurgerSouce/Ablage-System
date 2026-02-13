# -*- coding: utf-8 -*-
"""
Prediction Feedback Model (Satellite).

Persistiert ML-Vorhersage-Feedback fuer Retraining der
Predictive Payment AI Pipeline.

Pattern: OCRCorrectionFeedback-aehnliche Tabelle.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.db.models import Base


class PredictionFeedbackRecord(Base):
    """
    Persistiertes Feedback fuer ML-Vorhersagen.

    Speichert vorhergesagte vs. tatsaechliche Werte fuer:
    - Zahlungsverzoegerung (delay)
    - Ausfallwahrscheinlichkeit (default)
    - Zahlungsbedingungen (terms)

    Wird von der MLOps Retraining Pipeline konsumiert.
    """
    __tablename__ = "prediction_feedbacks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )

    prediction_id = Column(String(100), unique=True, nullable=False)
    prediction_type = Column(String(50), nullable=False)  # delay, default, terms
    predicted_value = Column(Float, nullable=False)
    actual_value = Column(Float, nullable=False)
    was_accurate = Column(Boolean, nullable=False)

    status = Column(String(20), nullable=False, default="pending")  # pending/processed
    processed_at = Column(DateTime(timezone=True), nullable=True)
    extra_data = Column(JSONB, nullable=True, default=dict)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index(
            "ix_prediction_feedbacks_entity_type_created",
            "entity_id", "prediction_type", "created_at",
        ),
        Index(
            "ix_prediction_feedbacks_company_status",
            "company_id", "status",
        ),
        Index("ix_prediction_feedbacks_prediction_type", "prediction_type"),
        Index("ix_prediction_feedbacks_was_accurate", "was_accurate"),
    )
