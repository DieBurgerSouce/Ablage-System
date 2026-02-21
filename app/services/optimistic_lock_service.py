"""Optimistic Locking Service.

Bietet Hilfsfunktionen fuer optimistic locking bei Updates.
Prueft row_version und wirft OptimisticLockError bei Konflikten.

Verwendung in Endpoints:
    from app.services.optimistic_lock_service import update_with_optimistic_lock

    await update_with_optimistic_lock(
        session=db,
        model_class=Document,
        entity_id=document_id,
        expected_version=request.row_version,
        update_values={"filename": "neu.pdf"},
    )

Fuer neue Models mit OptimisticLockMixin ist dieser Service nicht
zwingend noetig, da SQLAlchemy's version_id_col den Check automatisch
uebernimmt. Fuer bestehende Models (Document, BusinessEntity, etc.)
ohne Mixin wird dieser Service empfohlen.
"""

from typing import TypeVar
from uuid import UUID

from sqlalchemy import update, select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")

# Tabellen die Optimistic Locking unterstuetzen
OPTIMISTIC_LOCK_TABLES = frozenset({
    "documents",
    "business_entities",
    "invoice_tracking",
    "companies",
})


class OptimisticLockError(Exception):
    """Wird geworfen wenn row_version nicht uebereinstimmt.

    Attributes:
        entity_type: Tabellenname des betroffenen Objekts.
        entity_id: ID des betroffenen Objekts.
        expected_version: Vom Client gesendete (veraltete) Version.
    """

    def __init__(
        self,
        entity_type: str,
        entity_id: UUID,
        expected_version: int,
    ) -> None:
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.expected_version = expected_version
        super().__init__(
            f"Optimistic lock conflict on {entity_type} {entity_id} "
            f"(expected version {expected_version})"
        )


async def update_with_optimistic_lock(
    session: AsyncSession,
    model_class: type,
    entity_id: UUID,
    expected_version: int,
    update_values: dict,
) -> bool:
    """Fuehrt ein UPDATE mit Optimistic Locking durch.

    Setzt row_version in der WHERE-Clause, sodass das UPDATE nur
    erfolgreich ist, wenn kein anderer Nutzer zwischenzeitlich
    geaendert hat.

    Args:
        session: Async DB Session.
        model_class: SQLAlchemy Model-Klasse (muss row_version haben).
        entity_id: ID des zu aktualisierenden Objekts.
        expected_version: Erwartete row_version (vom Client).
        update_values: Dict mit zu aktualisierenden Feldern.
            row_version wird automatisch inkrementiert und darf
            NICHT in update_values enthalten sein.

    Returns:
        True wenn Update erfolgreich.

    Raises:
        OptimisticLockError: Wenn row_version nicht uebereinstimmt.
        ValueError: Wenn das Objekt nicht existiert.
    """
    # row_version automatisch inkrementieren
    values = dict(update_values)
    values["row_version"] = expected_version + 1

    stmt = (
        update(model_class)
        .where(model_class.id == entity_id)
        .where(model_class.row_version == expected_version)
        .values(**values)
    )

    result = await session.execute(stmt)

    if result.rowcount == 0:
        # Pruefen ob Objekt ueberhaupt existiert
        check_stmt = select(model_class.row_version).where(
            model_class.id == entity_id
        )
        check_result = await session.execute(check_stmt)
        current_version = check_result.scalar_one_or_none()

        if current_version is None:
            table_name = getattr(model_class, "__tablename__", "unbekannt")
            raise ValueError(
                f"{table_name} {entity_id} nicht gefunden"
            )

        logger.warning(
            "optimistic_lock_version_mismatch",
            entity_type=model_class.__tablename__,
            entity_id=str(entity_id),
            expected_version=expected_version,
            current_version=current_version,
        )

        raise OptimisticLockError(
            entity_type=model_class.__tablename__,
            entity_id=entity_id,
            expected_version=expected_version,
        )

    logger.debug(
        "optimistic_lock_update_success",
        entity_type=model_class.__tablename__,
        entity_id=str(entity_id),
        new_version=expected_version + 1,
    )

    return True
