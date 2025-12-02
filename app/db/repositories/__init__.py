"""
Repository Pattern für Datenbankabstraktion.

Bietet eine saubere Trennung zwischen Datenbankoperationen und Business-Logik.
"""

from app.db.repositories.base import BaseRepository
from app.db.repositories.document_repository import DocumentRepository
from app.db.repositories.user_repository import UserRepository

__all__ = [
    "BaseRepository",
    "DocumentRepository",
    "UserRepository",
]
