"""Satellite Model fuer Prediction-bezogene Datenbank-Entitaeten.

Enthaelt EntitySeasonalPattern fuer persistierte saisonale Zahlungsmuster.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Column, DateTime, Float, ForeignKey, Integer, String, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.models_base import Base, CrossDBJSON


class EntitySeasonalPattern(Base):
    """Persistiertes saisonales Zahlungsmuster pro Entity.

    Wird woechentlich per Celery Beat Task berechnet und
    in der Cashflow-Prognose verwendet.
    """
    __tablename__ = "entity_seasonal_patterns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Musterdaten
    pattern_type = Column(
        String(50),
        nullable=False,
        comment="z.B. holiday_slowdown, summer_slowdown, periodic_variation",
    )
    affected_months = Column(
        CrossDBJSON,
        nullable=False,
        comment="Betroffene Monate, z.B. [12, 1, 2]",
    )
    avg_delay_adjustment = Column(
        Float,
        nullable=False,
        default=1.0,
        comment="Multiplikator fuer durchschnittliche Verzoegerung",
    )
    confidence = Column(
        Float,
        nullable=False,
        default=0.0,
        comment="Konfidenz 0.0-1.0",
    )
    sample_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Anzahl zugrunde liegender Datenpunkte",
    )

    # Zeitstempel
    last_computed_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company", backref="entity_seasonal_patterns")

    def __repr__(self) -> str:
        return (
            f"<EntitySeasonalPattern entity={self.entity_id} "
            f"type={self.pattern_type} confidence={self.confidence:.2f}>"
        )
