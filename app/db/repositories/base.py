"""
Basis-Repository mit generischen CRUD-Operationen.

Stellt abstrakte Basisklasse für alle Repositories bereit.
Alle Operationen sind async und verwenden SQLAlchemy 2.0 Syntax.
"""

from abc import ABC
from typing import TypeVar, Generic, Optional, List, Type, Any, Dict
from uuid import UUID

from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase
import structlog

logger = structlog.get_logger(__name__)

# Type variable für Model-Klassen
ModelType = TypeVar("ModelType", bound=DeclarativeBase)


class BaseRepository(Generic[ModelType], ABC):
    """
    Generisches Basis-Repository für CRUD-Operationen.

    Bietet:
    - get_by_id: Einzelnes Objekt nach ID laden
    - get_all: Alle Objekte mit Pagination
    - create: Neues Objekt erstellen
    - update: Objekt aktualisieren
    - delete: Objekt löschen
    - count: Anzahl der Objekte zählen
    - exists: Prüfen ob Objekt existiert

    Verwendung:
        class DocumentRepository(BaseRepository[Document]):
            def __init__(self, db: AsyncSession):
                super().__init__(db, Document)
    """

    def __init__(self, db: AsyncSession, model: Type[ModelType]):
        """
        Initialisiert das Repository.

        Args:
            db: Async-Datenbank-Session
            model: SQLAlchemy Model-Klasse
        """
        self.db = db
        self.model = model
        self._model_name = model.__name__

    async def get_by_id(self, id: UUID) -> Optional[ModelType]:
        """
        Lädt ein Objekt nach ID.

        Args:
            id: UUID des Objekts

        Returns:
            Objekt oder None wenn nicht gefunden
        """
        result = await self.db.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        order_by: Optional[str] = None,
        order_desc: bool = False
    ) -> List[ModelType]:
        """
        Lädt alle Objekte mit optionaler Pagination.

        Args:
            skip: Anzahl zu überspringender Objekte
            limit: Maximale Anzahl (default: 100)
            order_by: Optionales Sortierfeld
            order_desc: Absteigende Sortierung (default: False)

        Returns:
            Liste von Objekten
        """
        query = select(self.model)

        if order_by and hasattr(self.model, order_by):
            order_column = getattr(self.model, order_by)
            if order_desc:
                query = query.order_by(order_column.desc())
            else:
                query = query.order_by(order_column.asc())

        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create(self, obj_data: Dict[str, Any]) -> ModelType:
        """
        Erstellt ein neues Objekt.

        Args:
            obj_data: Dictionary mit Objektdaten

        Returns:
            Erstelltes Objekt
        """
        db_obj = self.model(**obj_data)
        self.db.add(db_obj)
        await self.db.commit()
        await self.db.refresh(db_obj)

        logger.info(
            "repository_create",
            model=self._model_name,
            id=str(getattr(db_obj, "id", "unknown"))
        )

        return db_obj

    async def update(
        self,
        id: UUID,
        obj_data: Dict[str, Any]
    ) -> Optional[ModelType]:
        """
        Aktualisiert ein Objekt.

        Args:
            id: UUID des Objekts
            obj_data: Dictionary mit zu aktualisierenden Feldern

        Returns:
            Aktualisiertes Objekt oder None wenn nicht gefunden
        """
        db_obj = await self.get_by_id(id)
        if not db_obj:
            return None

        for field, value in obj_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)

        await self.db.commit()
        await self.db.refresh(db_obj)

        logger.info(
            "repository_update",
            model=self._model_name,
            id=str(id)
        )

        return db_obj

    async def delete(self, id: UUID) -> bool:
        """
        Löscht ein Objekt.

        Args:
            id: UUID des Objekts

        Returns:
            True wenn gelöscht, False wenn nicht gefunden
        """
        db_obj = await self.get_by_id(id)
        if not db_obj:
            return False

        await self.db.delete(db_obj)
        await self.db.commit()

        logger.info(
            "repository_delete",
            model=self._model_name,
            id=str(id)
        )

        return True

    async def count(self, **filters: object) -> int:
        """
        Zählt Objekte mit optionalen Filtern.

        Args:
            **filters: Optionale Filterkriterien (field=value)

        Returns:
            Anzahl der Objekte
        """
        query = select(func.count()).select_from(self.model)

        for field, value in filters.items():
            if hasattr(self.model, field):
                query = query.where(getattr(self.model, field) == value)

        result = await self.db.execute(query)
        return result.scalar() or 0

    async def exists(self, id: UUID) -> bool:
        """
        Prüft ob ein Objekt existiert.

        Args:
            id: UUID des Objekts

        Returns:
            True wenn vorhanden
        """
        query = select(func.count()).select_from(self.model).where(
            self.model.id == id
        )
        result = await self.db.execute(query)
        return (result.scalar() or 0) > 0

    async def bulk_create(self, objects_data: List[Dict[str, Any]]) -> List[ModelType]:
        """
        Erstellt mehrere Objekte in einer Transaktion.

        Args:
            objects_data: Liste von Dictionaries mit Objektdaten

        Returns:
            Liste erstellter Objekte
        """
        db_objs = [self.model(**data) for data in objects_data]
        self.db.add_all(db_objs)
        await self.db.commit()

        for obj in db_objs:
            await self.db.refresh(obj)

        logger.info(
            "repository_bulk_create",
            model=self._model_name,
            count=len(db_objs)
        )

        return db_objs

    async def bulk_delete(self, ids: List[UUID]) -> int:
        """
        Löscht mehrere Objekte.

        Args:
            ids: Liste von UUIDs

        Returns:
            Anzahl gelöschter Objekte
        """
        if not ids:
            return 0

        result = await self.db.execute(
            delete(self.model).where(self.model.id.in_(ids))
        )
        await self.db.commit()

        deleted_count = result.rowcount
        logger.info(
            "repository_bulk_delete",
            model=self._model_name,
            count=deleted_count
        )

        return deleted_count
