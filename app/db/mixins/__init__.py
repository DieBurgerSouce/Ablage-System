"""SQLAlchemy Model Mixins.

Wiederverwendbare Mixins fuer gemeinsame Spalten und Verhaltensweisen.
"""

from app.db.mixins.optimistic_lock import OptimisticLockMixin

__all__ = [
    "OptimisticLockMixin",
]
