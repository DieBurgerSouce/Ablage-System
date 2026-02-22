"""Base classes and cross-database types for all SQLAlchemy models.

This module breaks circular imports by providing Base, CrossDBJSON,
CrossDBTSVector, and CrossDBVector independently of models.py.
All domain model files (models_*.py) import from here instead of models.py.
"""

from sqlalchemy import JSON, Text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import declarative_base
from sqlalchemy.types import TypeDecorator

from pgvector.sqlalchemy import Vector


class CrossDBJSON(TypeDecorator):
    """Cross-database JSON type - uses JSONB on PostgreSQL, JSON on SQLite."""
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class CrossDBTSVector(TypeDecorator):
    """Cross-database TSVector type - uses TSVECTOR on PostgreSQL, Text on SQLite."""
    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(TSVECTOR())
        return dialect.type_descriptor(Text())


class CrossDBVector(TypeDecorator):
    """Cross-database Vector type - uses pgvector on PostgreSQL, Text on SQLite."""
    impl = Text
    cache_ok = True

    def __init__(self, dim: int = 1024):
        super().__init__()
        self.dim = dim

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Vector(self.dim))
        return dialect.type_descriptor(Text())


Base = declarative_base()
