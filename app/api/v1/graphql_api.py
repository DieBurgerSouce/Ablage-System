"""GraphQL-ähnliche API - Flexible Query-Schnittstelle mit Field Selection."""

import structlog
import re
from typing import List, Optional, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc, asc

from app.core.deps import get_db, get_current_user
from app.db.models import User

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/graphql", tags=["graphql"])


# ============================================================================
# Pydantic Models
# ============================================================================


class GraphQLQueryRequest(BaseModel):
    """GraphQL-ähnliche Query-Anfrage."""

    entity_type: str = Field(..., description="Entitätstyp (document, entity, invoice, alert)")
    fields: List[str] = Field(..., description="Auszuwählende Felder")
    filters: Dict[str, Any] = Field(default_factory=dict, description="Filter-Bedingungen")
    limit: int = Field(20, ge=1, le=100, description="Max. Ergebnisse")
    offset: int = Field(0, ge=0, description="Offset für Paginierung")
    order_by: Optional[str] = Field(None, description="Sortierfeld")
    order_desc: bool = Field(False, description="Absteigend sortieren")

    @validator("entity_type")
    def validate_entity_type(cls, v: str) -> str:
        """Validiert Entity-Type gegen Whitelist."""
        allowed = {"document", "entity", "invoice", "alert", "workflow", "payment"}
        if v not in allowed:
            raise ValueError(f"Ungueltiger Entity-Typ. Erlaubt: {allowed}")
        return v

    @validator("fields")
    def validate_fields(cls, v: List[str]) -> List[str]:
        """Validiert Feldnamen."""
        pattern = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{0,63}$")
        for field in v:
            if not pattern.match(field):
                raise ValueError(f"Ungueltiger Feldname: {field}")
        return v

    @validator("order_by")
    def validate_order_by(cls, v: Optional[str]) -> Optional[str]:
        """Validiert Order-By Feld."""
        if v is None:
            return v
        pattern = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{0,63}$")
        if not pattern.match(v):
            raise ValueError(f"Ungueltiges Sortierfeld: {v}")
        return v


class GraphQLQueryResponse(BaseModel):
    """GraphQL-ähnliche Query-Antwort."""

    entity_type: str
    total_count: int
    items: List[Dict[str, Any]]
    has_more: bool
    offset: int
    limit: int


class GraphQLSchemaField(BaseModel):
    """Schema-Feld-Definition."""

    name: str
    type: str
    nullable: bool
    description: str


class GraphQLSchemaType(BaseModel):
    """Schema-Typ-Definition."""

    type_name: str
    fields: List[GraphQLSchemaField]
    description: str


class GraphQLSchemaResponse(BaseModel):
    """GraphQL-Schema-Antwort."""

    types: List[GraphQLSchemaType]


# ============================================================================
# Schema Definitionen
# ============================================================================


GRAPHQL_SCHEMAS = {
    "document": GraphQLSchemaType(
        type_name="Document",
        description="Dokument mit OCR-Daten",
        fields=[
            GraphQLSchemaField(name="id", type="UUID", nullable=False, description="Dokument-ID"),
            GraphQLSchemaField(name="filename", type="String", nullable=False, description="Dateiname"),
            GraphQLSchemaField(name="status", type="String", nullable=False, description="Verarbeitungsstatus"),
            GraphQLSchemaField(name="ocr_text", type="String", nullable=True, description="OCR-Text"),
            GraphQLSchemaField(name="ocr_confidence", type="Float", nullable=True, description="OCR-Confidence"),
            GraphQLSchemaField(name="created_at", type="DateTime", nullable=False, description="Erstellungsdatum"),
            GraphQLSchemaField(name="updated_at", type="DateTime", nullable=False, description="Änderungsdatum"),
            GraphQLSchemaField(name="folder_id", type="UUID", nullable=True, description="Ordner-ID"),
            GraphQLSchemaField(name="tags", type="List[String]", nullable=True, description="Tags"),
        ]
    ),
    "entity": GraphQLSchemaType(
        type_name="BusinessEntity",
        description="Geschäftspartner (Kunde/Lieferant)",
        fields=[
            GraphQLSchemaField(name="id", type="UUID", nullable=False, description="Entity-ID"),
            GraphQLSchemaField(name="name", type="String", nullable=False, description="Name"),
            GraphQLSchemaField(name="entity_type", type="String", nullable=False, description="Typ (customer/supplier)"),
            GraphQLSchemaField(name="risk_score", type="Float", nullable=True, description="Risiko-Score"),
            GraphQLSchemaField(name="payment_delay_days", type="Float", nullable=True, description="Zahlungsverzögerung"),
            GraphQLSchemaField(name="default_rate", type="Float", nullable=True, description="Ausfallrate"),
            GraphQLSchemaField(name="created_at", type="DateTime", nullable=False, description="Erstellungsdatum"),
        ]
    ),
    "invoice": GraphQLSchemaType(
        type_name="InvoiceTracking",
        description="Rechnungsverfolgung",
        fields=[
            GraphQLSchemaField(name="id", type="UUID", nullable=False, description="Rechnung-ID"),
            GraphQLSchemaField(name="invoice_number", type="String", nullable=False, description="Rechnungsnummer"),
            GraphQLSchemaField(name="amount", type="Decimal", nullable=False, description="Betrag"),
            GraphQLSchemaField(name="status", type="String", nullable=False, description="Status"),
            GraphQLSchemaField(name="due_date", type="Date", nullable=True, description="Fälligkeitsdatum"),
            GraphQLSchemaField(name="paid_date", type="Date", nullable=True, description="Zahlungsdatum"),
            GraphQLSchemaField(name="dunning_level", type="Integer", nullable=True, description="Mahnstufe"),
            GraphQLSchemaField(name="entity_id", type="UUID", nullable=True, description="Geschäftspartner-ID"),
        ]
    ),
    "alert": GraphQLSchemaType(
        type_name="Alert",
        description="System-Alert",
        fields=[
            GraphQLSchemaField(name="id", type="UUID", nullable=False, description="Alert-ID"),
            GraphQLSchemaField(name="alert_code", type="String", nullable=False, description="Alert-Code"),
            GraphQLSchemaField(name="title", type="String", nullable=False, description="Titel"),
            GraphQLSchemaField(name="category", type="String", nullable=False, description="Kategorie"),
            GraphQLSchemaField(name="severity", type="String", nullable=False, description="Schweregrad"),
            GraphQLSchemaField(name="status", type="String", nullable=False, description="Status"),
            GraphQLSchemaField(name="created_at", type="DateTime", nullable=False, description="Erstellungsdatum"),
        ]
    ),
}


# ============================================================================
# Query Builder
# ============================================================================


class QueryBuilder:
    """Baut sichere SQL-Queries aus GraphQL-ähnlichen Anfragen."""

    @staticmethod
    async def build_query(
        request: GraphQLQueryRequest,
        company_id: UUID,
        db: AsyncSession,
    ) -> tuple[Any, int]:
        """Baut Query und führt sie aus.

        Args:
            request: Query-Anfrage
            company_id: Mandanten-ID
            db: Datenbank-Session

        Returns:
            Tuple aus (Ergebnisse, Gesamt-Anzahl)
        """
        # Model ermitteln
        model_class = QueryBuilder._get_model_class(request.entity_type)

        # Verfügbare Felder prüfen
        available_fields = QueryBuilder._get_available_fields(model_class)
        for field in request.fields:
            if field not in available_fields:
                raise ValueError(f"Feld nicht verfügbar: {field}")

        # Base Query mit company_id Filter
        stmt = select(model_class).where(model_class.company_id == company_id)

        # Filter anwenden
        stmt = QueryBuilder._apply_filters(stmt, model_class, request.filters)

        # Gesamt-Anzahl ermitteln (vor Limit/Offset)
        from sqlalchemy import func
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await db.execute(count_stmt)
        total_count = count_result.scalar() or 0

        # Sortierung
        if request.order_by:
            order_field = getattr(model_class, request.order_by, None)
            if order_field is not None:
                stmt = stmt.order_by(desc(order_field) if request.order_desc else asc(order_field))
        else:
            # Standard: Nach created_at absteigend
            if hasattr(model_class, "created_at"):
                stmt = stmt.order_by(desc(model_class.created_at))

        # Paginierung
        stmt = stmt.limit(request.limit).offset(request.offset)

        # Query ausführen
        result = await db.execute(stmt)
        items = result.scalars().all()

        return items, total_count

    @staticmethod
    def _get_model_class(entity_type: str) -> Any:
        """Gibt Model-Klasse für Entity-Typ zurück."""
        from app.db.models import Document, BusinessEntity, InvoiceTracking
        from app.db.models_alert import Alert

        mapping = {
            "document": Document,
            "entity": BusinessEntity,
            "invoice": InvoiceTracking,
            "alert": Alert,
        }

        return mapping[entity_type]

    @staticmethod
    def _get_available_fields(model_class: Any) -> set[str]:
        """Gibt verfügbare Felder für Model zurück."""
        from sqlalchemy.inspection import inspect

        mapper = inspect(model_class)
        return {col.key for col in mapper.columns}

    @staticmethod
    def _apply_filters(stmt: Any, model_class: Any, filters: Dict[str, Any]) -> Any:
        """Wendet Filter auf Query an."""
        for field_name, field_value in filters.items():
            field = getattr(model_class, field_name, None)
            if field is None:
                continue

            # String-Filter
            if isinstance(field_value, str):
                if field_value.startswith("%") or field_value.endswith("%"):
                    # LIKE-Filter
                    stmt = stmt.where(field.ilike(field_value))
                else:
                    # Exakte Übereinstimmung
                    stmt = stmt.where(field == field_value)

            # Listen-Filter (IN)
            elif isinstance(field_value, list):
                stmt = stmt.where(field.in_(field_value))

            # Bereichs-Filter
            elif isinstance(field_value, dict):
                if "gte" in field_value:
                    stmt = stmt.where(field >= field_value["gte"])
                if "lte" in field_value:
                    stmt = stmt.where(field <= field_value["lte"])
                if "gt" in field_value:
                    stmt = stmt.where(field > field_value["gt"])
                if "lt" in field_value:
                    stmt = stmt.where(field < field_value["lt"])

            # Direkte Werte
            else:
                stmt = stmt.where(field == field_value)

        return stmt

    @staticmethod
    def _project_fields(item: Any, fields: List[str]) -> Dict[str, Any]:
        """Projiziert nur angeforderte Felder."""
        result = {}
        for field in fields:
            value = getattr(item, field, None)
            # UUID zu String konvertieren
            if isinstance(value, UUID):
                value = str(value)
            result[field] = value
        return result


# ============================================================================
# API Endpoints
# ============================================================================


@router.post(
    "/query",
    response_model=GraphQLQueryResponse,
    summary="GraphQL-ähnliche Query",
    description="Flexible Query mit Field Selection und Filterung."
)
async def execute_query(
    request: GraphQLQueryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GraphQLQueryResponse:
    """Führt GraphQL-ähnliche Query aus."""
    try:
        # Query ausführen
        items, total_count = await QueryBuilder.build_query(
            request=request,
            company_id=current_user.company_id,
            db=db,
        )

        # Felder projizieren
        projected_items = [
            QueryBuilder._project_fields(item, request.fields)
            for item in items
        ]

        has_more = (request.offset + request.limit) < total_count

        logger.info(
            "graphql_query_executed",
            entity_type=request.entity_type,
            fields=len(request.fields),
            results=len(projected_items),
            total=total_count,
        )

        return GraphQLQueryResponse(
            entity_type=request.entity_type,
            total_count=total_count,
            items=projected_items,
            has_more=has_more,
            offset=request.offset,
            limit=request.limit,
        )

    except ValueError as e:
        logger.warning("graphql_query_fehler", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("graphql_query_fehler", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Fehler bei der Query-Ausführung")


@router.get(
    "/schema",
    response_model=GraphQLSchemaResponse,
    summary="GraphQL-Schema",
    description="Holt verfügbare Typen und Felder."
)
async def get_schema(
    entity_type: Optional[str] = Query(None, description="Spezifischer Entity-Typ"),
    current_user: User = Depends(get_current_user),
) -> GraphQLSchemaResponse:
    """Holt GraphQL-Schema."""
    try:
        if entity_type:
            # Validierung
            if entity_type not in GRAPHQL_SCHEMAS:
                raise HTTPException(
                    status_code=404,
                    detail=f"Schema für Typ '{entity_type}' nicht gefunden"
                )
            types = [GRAPHQL_SCHEMAS[entity_type]]
        else:
            types = list(GRAPHQL_SCHEMAS.values())

        return GraphQLSchemaResponse(types=types)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("schema_abruf_fehler", error=str(e))
        raise HTTPException(status_code=500, detail="Fehler beim Schema-Abruf")
