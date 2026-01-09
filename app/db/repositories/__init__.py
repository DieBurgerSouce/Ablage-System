"""
Repository Pattern für Datenbankabstraktion.

Bietet eine saubere Trennung zwischen Datenbankoperationen und Business-Logik.
"""

from app.db.repositories.base import BaseRepository
from app.db.repositories.document_repository import DocumentRepository
from app.db.repositories.user_repository import UserRepository
from app.db.repositories.personalized_thresholds_repository import (
    PrivatUserProfileRepository,
    PrivatUserThresholdRepository,
    PrivatThresholdAdjustmentRepository,
    PrivatThresholdRecommendationRepository,
)

__all__ = [
    "BaseRepository",
    "DocumentRepository",
    "UserRepository",
    # Personalized Thresholds (Privat-Modul)
    "PrivatUserProfileRepository",
    "PrivatUserThresholdRepository",
    "PrivatThresholdAdjustmentRepository",
    "PrivatThresholdRecommendationRepository",
]
