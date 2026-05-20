"""Optimistic Locking Mixin fuer SQLAlchemy Models.

Verhindert Race Conditions bei gleichzeitiger Bearbeitung durch
automatische Versionspruefung (HTTP 409 bei Konflikten).

Verwendung fuer NEUE Models:
    class MyModel(Base, OptimisticLockMixin):
        __tablename__ = "my_table"
        ...

SQLAlchemy's version_id_col wird automatisch verwendet:
- Bei UPDATE wird row_version automatisch inkrementiert
- Bei Konflikt wird StaleDataError geworfen

HINWEIS: Fuer bestehende Models (Document, BusinessEntity, InvoiceTracking,
Company) wird row_version direkt in der Migration 239 hinzugefuegt.
Updates verwenden den OptimisticLockService aus
app/services/optimistic_lock_service.py.
"""

from sqlalchemy import Column, Integer, text


class OptimisticLockMixin:
    """Mixin fuer Optimistic Locking via row_version.

    Fuegt eine row_version-Spalte hinzu und konfiguriert SQLAlchemy's
    version_id_col fuer automatische Versionspruefung bei UPDATEs.

    Bei einem Konflikt (anderer Nutzer hat zwischenzeitlich geaendert)
    wirft SQLAlchemy einen StaleDataError, der vom Exception-Handler
    in HTTP 409 Conflict umgewandelt wird.

    Beispiel:
        class Vertrag(Base, OptimisticLockMixin):
            __tablename__ = "vertraege"
            id = Column(UUID(as_uuid=True), primary_key=True)
            titel = Column(String(255))
    """

    row_version: int = Column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
        comment="Optimistic Locking: Wird bei jedem UPDATE inkrementiert",
    )

    __mapper_args__ = {
        "version_id_col": row_version,
    }
