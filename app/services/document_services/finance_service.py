"""Finance Service - Jahr-basierte Finanz-Dokumentenverwaltung.

Enthaelt:
- get_finance_years: Alle Jahre mit Dokument-Aggregationen
- get_year_details: Details fuer ein Jahr
- get_overall_aggregations: Gesamt-Aggregationen
- get_year_aggregations: Aggregationen fuer ein Jahr
- get_category_documents: Dokumente einer Kategorie
- get_category_aggregations: Aggregationen fuer eine Kategorie

Finanz-Kategorien (18 in 4 Paketen):
- Steuern: Grundabgabenbescheid, Steuerbescheide, Vorauszahlungen, etc.
- Personal: Lohn/Gehalt, Sozialversicherung, etc.
- Versicherung: Betriebshaftpflicht, KFZ, etc.
- Bank: Kontoauszuege, Kreditvertraege, etc.
"""

import math
from datetime import datetime, timezone, date
from typing import Any, Dict, List, Optional, Set
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_, or_, extract, case, text, Float, literal_column
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql.expression import cast as sql_cast


import re

# DD.2 SECURITY FIX: Whitelist of allowed JSONB column and key names
_ALLOWED_JSONB_COLUMNS = frozenset({"extracted_data", "metadata", "validation_results"})
_ALLOWED_JSONB_KEYS = frozenset({
    "total_amount", "nachzahlung", "erstattung", "invoice_number",
    "invoice_date", "vendor_name", "tax_amount", "net_amount"
})
_SAFE_IDENTIFIER_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')


def jsonb_text(column_name: str, key: str) -> literal_column:
    """Helper: Extrahiert Text aus JSONB mit PostgreSQL ->> Operator.

    Umgeht das Problem mit CrossDBJSON TypeDecorator und .astext.

    DD.2 SECURITY FIX: Validates column_name and key against whitelist.
    """
    # Validate column_name
    if column_name not in _ALLOWED_JSONB_COLUMNS:
        if not _SAFE_IDENTIFIER_PATTERN.match(column_name):
            raise ValueError(f"Invalid JSONB column name: {column_name}")

    # Validate key - must be alphanumeric/underscore only
    if key not in _ALLOWED_JSONB_KEYS:
        if not _SAFE_IDENTIFIER_PATTERN.match(key):
            raise ValueError(f"Invalid JSONB key: {key}")

    return literal_column(f"{column_name}->>'{key}'")

from app.db.models import Document, Tag
from app.db.schemas import (
    DocumentType,
    ProcessingStatus,
    TaxType,
    FinanceDocumentCategory,
    FinanceYearResponse,
    FinanceYearListResponse,
    FinanceAggregationsResponse,
    FinanceCategoryFilter,
    FinanceCategoryDocumentResponse,
    FinanceCategoryDocumentListResponse,
    FinanceCategoryAggregations,
)
from app.services.document_services.base import DocumentServiceBase

logger = structlog.get_logger(__name__)


# Mapping von Finanz-Kategorie-Slugs zu DocumentType-Enums
FINANCE_CATEGORY_TO_DOCTYPE: Dict[str, DocumentType] = {
    # Steuern-Paket
    "grundabgabenbescheid": DocumentType.TAX_ASSESSMENT,
    "steuerbescheide": DocumentType.TAX_NOTICE,
    "vorauszahlungen": DocumentType.TAX_PREPAYMENT,
    "steuererklaerungen": DocumentType.TAX_RETURN,
    "finanzamt_korrespondenz": DocumentType.TAX_CORRESPONDENCE,
    # Personal-Paket
    "lohn_gehalt": DocumentType.PAYROLL,
    "sozialversicherung": DocumentType.SOCIAL_SECURITY,
    "berufsgenossenschaft": DocumentType.TRADE_ASSOCIATION,
    "arbeitsvertraege": DocumentType.CONTRACT,
    # Versicherungs-Paket
    "betriebshaftpflicht": DocumentType.CONTRACT,
    "sachversicherungen": DocumentType.CONTRACT,
    "kfz_versicherung": DocumentType.CONTRACT,
    "rechtsschutz": DocumentType.CONTRACT,
    # Bank-Paket
    "kontoauszuege": DocumentType.BANK_STATEMENT,
    "kreditvertraege": DocumentType.CONTRACT,
    "buergschaften": DocumentType.CONTRACT,
    "darlehen": DocumentType.CONTRACT,
}

# Kategorien die Fristen haben
CATEGORIES_WITH_DEADLINES: Set[str] = {
    "grundabgabenbescheid",
    "steuerbescheide",
    "vorauszahlungen",
}

# Kategorien die Betraege (Nachzahlung/Erstattung) haben
CATEGORIES_WITH_AMOUNTS: Set[str] = {
    "grundabgabenbescheid",
    "steuerbescheide",
    "vorauszahlungen",
}

# Paket-Mapping
CATEGORY_TO_PACKAGE: Dict[str, str] = {
    "grundabgabenbescheid": "steuern",
    "steuerbescheide": "steuern",
    "vorauszahlungen": "steuern",
    "steuererklaerungen": "steuern",
    "finanzamt_korrespondenz": "steuern",
    "lohn_gehalt": "personal",
    "sozialversicherung": "personal",
    "berufsgenossenschaft": "personal",
    "arbeitsvertraege": "personal",
    "betriebshaftpflicht": "versicherung",
    "sachversicherungen": "versicherung",
    "kfz_versicherung": "versicherung",
    "rechtsschutz": "versicherung",
    "kontoauszuege": "bank",
    "kreditvertraege": "bank",
    "buergschaften": "bank",
    "darlehen": "bank",
}

# Alle Finanz-DocumentTypes
FINANCE_DOCUMENT_TYPES: Set[str] = {
    DocumentType.TAX_ASSESSMENT.value,
    DocumentType.TAX_NOTICE.value,
    DocumentType.TAX_PREPAYMENT.value,
    DocumentType.TAX_RETURN.value,
    DocumentType.TAX_CORRESPONDENCE.value,
    DocumentType.PAYROLL.value,
    DocumentType.SOCIAL_SECURITY.value,
    DocumentType.TRADE_ASSOCIATION.value,
    DocumentType.BANK_STATEMENT.value,
}


# =============================================================================
# HISTORY LOGGING HELPER
# =============================================================================


async def log_finance_history(
    db: AsyncSession,
    document_id: UUID,
    user_id: Optional[UUID],
    action: str,
    old_values: Optional[Dict[str, Any]] = None,
    new_values: Optional[Dict[str, Any]] = None,
    changed_fields: Optional[List[str]] = None,
    description: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Loggt eine Aenderung an einem Finanz-Dokument.

    Args:
        db: Datenbank-Session
        document_id: ID des betroffenen Dokuments
        user_id: ID des Benutzers (kann None sein fuer System-Aktionen)
        action: Aktionstyp (created, updated, deleted, etc.)
        old_values: Vorherige Werte (bei Updates)
        new_values: Neue Werte (bei Updates)
        changed_fields: Liste der geaenderten Felder
        description: Menschenlesbare Beschreibung (auf Deutsch)
        ip_address: IP-Adresse des Benutzers
        user_agent: Browser/Client Info
        metadata: Zusaetzliche Kontext-Informationen
    """
    from app.db.models import FinanceDocumentHistory

    try:
        history_entry = FinanceDocumentHistory(
            document_id=document_id,
            user_id=user_id,
            action=action,
            old_values=old_values or {},
            new_values=new_values or {},
            changed_fields=changed_fields or [],
            description=description,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata=metadata or {},
        )
        db.add(history_entry)
        await db.flush()

        logger.info(
            "finance_history_logged",
            document_id=str(document_id),
            user_id=str(user_id) if user_id else None,
            action=action,
        )
    except Exception as e:
        # History-Logging sollte nie den Hauptprozess blockieren
        logger.warning(
            "finance_history_log_failed",
            document_id=str(document_id),
            action=action,
            error=str(e),
        )


class FinanceService(DocumentServiceBase):
    """Service fuer Jahr-basierte Finanz-Dokumentenverwaltung.

    Ermoeglicht gefilterte Dokumentenlisten und Aggregationen
    fuer die Finanzen-Ansicht im Frontend.
    """

    def __init__(self) -> None:
        """Initialisiere Finance-Service."""
        pass

    # =========================================================================
    # Year Overview Methods
    # =========================================================================

    async def get_finance_years(
        self,
        db: AsyncSession,
        user_id: UUID,
    ) -> FinanceYearListResponse:
        """Alle Finanz-Jahre mit Dokument-Counts abrufen.

        Args:
            db: Datenbank-Session
            user_id: ID des Benutzers (fuer Zugriffskontrolle)

        Returns:
            FinanceYearListResponse mit allen Jahren
        """
        # Query: Gruppiere nach Jahr und zaehle Dokumente
        query = (
            select(
                extract("year", Document.created_at).label("year"),
                func.count(Document.id).label("total_docs"),
                func.max(Document.created_at).label("last_doc_date"),
            )
            .where(Document.owner_id == user_id)
            .where(Document.is_deleted == False)
            .where(Document.document_type.in_(list(FINANCE_DOCUMENT_TYPES)))
            .group_by(extract("year", Document.created_at))
            .order_by(extract("year", Document.created_at).desc())
        )

        result = await db.execute(query)
        rows = result.all()

        current_year = datetime.now().year
        years: List[FinanceYearResponse] = []

        for row in rows:
            year_int = int(row.year)

            # Hole Kategorie-Counts fuer dieses Jahr
            category_counts = await self._get_year_category_counts(db, user_id, year_int)

            # Berechne Aggregationen
            aggregations = await self._calculate_year_aggregations(db, user_id, year_int)

            years.append(
                FinanceYearResponse(
                    id=str(year_int),
                    year=year_int,
                    is_active=(year_int == current_year),
                    last_document_date=row.last_doc_date,
                    document_counts=category_counts,
                    total_documents=row.total_docs,
                    total_nachzahlung=aggregations.get("nachzahlung", 0.0),
                    total_erstattung=aggregations.get("erstattung", 0.0),
                    pending_deadlines=aggregations.get("pending_deadlines", 0),
                )
            )

        return FinanceYearListResponse(items=years, total=len(years))

    async def get_year_details(
        self,
        db: AsyncSession,
        user_id: UUID,
        year: int,
    ) -> Optional[FinanceYearResponse]:
        """Details fuer ein spezifisches Jahr abrufen.

        Args:
            db: Datenbank-Session
            user_id: ID des Benutzers
            year: Das Jahr

        Returns:
            FinanceYearResponse oder None wenn keine Dokumente
        """
        # Pruefe ob Dokumente fuer dieses Jahr existieren
        count_query = (
            select(func.count(Document.id))
            .where(Document.owner_id == user_id)
            .where(Document.is_deleted == False)
            .where(Document.document_type.in_(list(FINANCE_DOCUMENT_TYPES)))
            .where(extract("year", Document.created_at) == year)
        )

        result = await db.execute(count_query)
        total_docs = result.scalar() or 0

        if total_docs == 0:
            return None

        # Hole letztes Dokumentdatum
        last_date_query = (
            select(func.max(Document.created_at))
            .where(Document.owner_id == user_id)
            .where(Document.is_deleted == False)
            .where(Document.document_type.in_(list(FINANCE_DOCUMENT_TYPES)))
            .where(extract("year", Document.created_at) == year)
        )

        result = await db.execute(last_date_query)
        last_doc_date = result.scalar()

        # Hole Kategorie-Counts
        category_counts = await self._get_year_category_counts(db, user_id, year)

        # Berechne Aggregationen
        aggregations = await self._calculate_year_aggregations(db, user_id, year)

        current_year = datetime.now().year

        return FinanceYearResponse(
            id=str(year),
            year=year,
            is_active=(year == current_year),
            last_document_date=last_doc_date,
            document_counts=category_counts,
            total_documents=total_docs,
            total_nachzahlung=aggregations.get("nachzahlung", 0.0),
            total_erstattung=aggregations.get("erstattung", 0.0),
            pending_deadlines=aggregations.get("pending_deadlines", 0),
        )

    # =========================================================================
    # Aggregation Methods
    # =========================================================================

    async def get_overall_aggregations(
        self,
        db: AsyncSession,
        user_id: UUID,
    ) -> FinanceAggregationsResponse:
        """Gesamt-Aggregationen ueber alle Jahre.

        Args:
            db: Datenbank-Session
            user_id: ID des Benutzers

        Returns:
            FinanceAggregationsResponse mit Gesamt-Statistiken
        """
        # Basis-Query fuer Finanz-Dokumente
        base_query = (
            select(Document)
            .where(Document.owner_id == user_id)
            .where(Document.is_deleted == False)
            .where(Document.document_type.in_(list(FINANCE_DOCUMENT_TYPES)))
        )

        # Gesamt-Anzahl
        count_result = await db.execute(
            select(func.count(Document.id))
            .where(Document.owner_id == user_id)
            .where(Document.is_deleted == False)
            .where(Document.document_type.in_(list(FINANCE_DOCUMENT_TYPES)))
        )
        total_documents = count_result.scalar() or 0

        # Nachzahlung/Erstattung aus JSONB
        amounts = await self._calculate_amounts(db, user_id, year=None)

        # Fristen
        deadlines = await self._calculate_deadlines(db, user_id, year=None)

        # Dokumente nach Kategorie
        docs_by_category = await self._get_documents_by_category(db, user_id, year=None)

        # Dokumente nach Paket
        docs_by_package = self._aggregate_by_package(docs_by_category)

        return FinanceAggregationsResponse(
            total_documents=total_documents,
            total_nachzahlung=amounts.get("nachzahlung", 0.0),
            total_erstattung=amounts.get("erstattung", 0.0),
            saldo=amounts.get("erstattung", 0.0) - amounts.get("nachzahlung", 0.0),
            pending_deadlines=deadlines.get("pending", 0),
            overdue_deadlines=deadlines.get("overdue", 0),
            documents_by_category=docs_by_category,
            documents_by_package=docs_by_package,
        )

    async def get_year_aggregations(
        self,
        db: AsyncSession,
        user_id: UUID,
        year: int,
    ) -> FinanceAggregationsResponse:
        """Aggregationen fuer ein spezifisches Jahr.

        Args:
            db: Datenbank-Session
            user_id: ID des Benutzers
            year: Das Jahr

        Returns:
            FinanceAggregationsResponse mit Jahr-Statistiken
        """
        # Gesamt-Anzahl fuer Jahr
        count_result = await db.execute(
            select(func.count(Document.id))
            .where(Document.owner_id == user_id)
            .where(Document.is_deleted == False)
            .where(Document.document_type.in_(list(FINANCE_DOCUMENT_TYPES)))
            .where(extract("year", Document.created_at) == year)
        )
        total_documents = count_result.scalar() or 0

        # Nachzahlung/Erstattung
        amounts = await self._calculate_amounts(db, user_id, year=year)

        # Fristen
        deadlines = await self._calculate_deadlines(db, user_id, year=year)

        # Dokumente nach Kategorie
        docs_by_category = await self._get_documents_by_category(db, user_id, year=year)

        # Dokumente nach Paket
        docs_by_package = self._aggregate_by_package(docs_by_category)

        return FinanceAggregationsResponse(
            total_documents=total_documents,
            total_nachzahlung=amounts.get("nachzahlung", 0.0),
            total_erstattung=amounts.get("erstattung", 0.0),
            saldo=amounts.get("erstattung", 0.0) - amounts.get("nachzahlung", 0.0),
            pending_deadlines=deadlines.get("pending", 0),
            overdue_deadlines=deadlines.get("overdue", 0),
            documents_by_category=docs_by_category,
            documents_by_package=docs_by_package,
        )

    # =========================================================================
    # Category Document Methods
    # =========================================================================

    async def get_category_documents(
        self,
        db: AsyncSession,
        user_id: UUID,
        filter_params: FinanceCategoryFilter,
    ) -> FinanceCategoryDocumentListResponse:
        """Dokumente fuer eine Finanz-Kategorie abrufen.

        Args:
            db: Datenbank-Session
            user_id: ID des Benutzers
            filter_params: Filter mit Jahr, Kategorie, etc.

        Returns:
            FinanceCategoryDocumentListResponse mit paginierten Ergebnissen
        """
        # Basis-Query
        conditions = [
            Document.owner_id == user_id,
            Document.is_deleted == False,
            extract("year", Document.created_at) == filter_params.year,
        ]

        # Kategorie-Filter
        if filter_params.category in FINANCE_CATEGORY_TO_DOCTYPE:
            doc_type = FINANCE_CATEGORY_TO_DOCTYPE[filter_params.category]
            conditions.append(Document.document_type == doc_type.value)

        # Textsuche
        if filter_params.search:
            search_pattern = f"%{filter_params.search}%"
            conditions.append(
                or_(
                    Document.filename.ilike(search_pattern),
                    Document.original_filename.ilike(search_pattern),
                )
            )

        # Datumsfilter
        if filter_params.date_from:
            conditions.append(Document.created_at >= filter_params.date_from)
        if filter_params.date_to:
            conditions.append(Document.created_at <= filter_params.date_to)

        # Betragsfilter (aus extracted_data) - PostgreSQL JSONB ->> fuer Text-Extraktion
        if filter_params.amount_min is not None:
            conditions.append(
                sql_cast(jsonb_text("extracted_data", "total_amount"), Float) >= filter_params.amount_min
            )
        if filter_params.amount_max is not None:
            conditions.append(
                sql_cast(jsonb_text("extracted_data", "total_amount"), Float) <= filter_params.amount_max
            )

        # Gesamt-Anzahl
        count_query = select(func.count(Document.id)).where(and_(*conditions))
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        # Sortierung
        sort_column = self._get_sort_column(filter_params.sort_by)
        if filter_params.sort_order == "desc":
            query = (
                select(Document)
                .where(and_(*conditions))
                .order_by(sort_column.desc().nulls_last())
            )
        else:
            query = (
                select(Document)
                .where(and_(*conditions))
                .order_by(sort_column.asc().nulls_first())
            )

        # Pagination
        offset = filter_params.page * filter_params.page_size
        query = query.offset(offset).limit(filter_params.page_size)

        # Tags eager-loaden
        query = query.options(selectinload(Document.tags))

        # Ausfuehren
        result = await db.execute(query)
        documents = result.scalars().all()

        total_pages = math.ceil(total / filter_params.page_size) if total > 0 else 0

        return FinanceCategoryDocumentListResponse(
            items=[self._to_finance_document_response(doc, filter_params.category) for doc in documents],
            total=total,
            page=filter_params.page,
            page_size=filter_params.page_size,
            total_pages=total_pages,
        )

    async def get_category_aggregations(
        self,
        db: AsyncSession,
        user_id: UUID,
        year: int,
        category: str,
    ) -> FinanceCategoryAggregations:
        """Aggregationen fuer eine Finanz-Kategorie.

        Args:
            db: Datenbank-Session
            user_id: ID des Benutzers
            year: Das Jahr
            category: Kategorie-Slug

        Returns:
            FinanceCategoryAggregations
        """
        conditions = [
            Document.owner_id == user_id,
            Document.is_deleted == False,
            extract("year", Document.created_at) == year,
        ]

        if category in FINANCE_CATEGORY_TO_DOCTYPE:
            doc_type = FINANCE_CATEGORY_TO_DOCTYPE[category]
            conditions.append(Document.document_type == doc_type.value)

        # Gesamt-Anzahl
        count_result = await db.execute(
            select(func.count(Document.id)).where(and_(*conditions))
        )
        total_documents = count_result.scalar() or 0

        # Datum-Bereich
        date_result = await db.execute(
            select(
                func.min(Document.created_at).label("earliest"),
                func.max(Document.created_at).label("latest"),
            ).where(and_(*conditions))
        )
        date_row = date_result.first()
        earliest_date = date_row.earliest if date_row else None
        latest_date = date_row.latest if date_row else None

        # Nachzahlung/Erstattung
        amounts = await self._calculate_amounts_for_category(db, user_id, year, category)

        # Fristen
        deadlines = await self._calculate_deadlines_for_category(db, user_id, year, category)

        return FinanceCategoryAggregations(
            category=category,
            year=year,
            total_documents=total_documents,
            total_nachzahlung=amounts.get("nachzahlung", 0.0),
            total_erstattung=amounts.get("erstattung", 0.0),
            pending_deadlines=deadlines.get("pending", 0),
            overdue_deadlines=deadlines.get("overdue", 0),
            earliest_date=earliest_date,
            latest_date=latest_date,
        )

    # =========================================================================
    # Private Helper Methods
    # =========================================================================

    async def _get_year_category_counts(
        self,
        db: AsyncSession,
        user_id: UUID,
        year: int,
    ) -> Dict[str, int]:
        """Hole Dokument-Counts pro Kategorie fuer ein Jahr."""
        query = (
            select(
                Document.document_type,
                func.count(Document.id).label("count"),
            )
            .where(Document.owner_id == user_id)
            .where(Document.is_deleted == False)
            .where(Document.document_type.in_(list(FINANCE_DOCUMENT_TYPES)))
            .where(extract("year", Document.created_at) == year)
            .group_by(Document.document_type)
        )

        result = await db.execute(query)
        rows = result.all()

        # Konvertiere DocumentType zurueck zu Kategorie-Slug
        counts: Dict[str, int] = {}
        doctype_to_category = {v.value: k for k, v in FINANCE_CATEGORY_TO_DOCTYPE.items()}

        for row in rows:
            category = doctype_to_category.get(row.document_type)
            if category:
                counts[category] = row.count

        return counts

    async def _calculate_year_aggregations(
        self,
        db: AsyncSession,
        user_id: UUID,
        year: int,
    ) -> Dict[str, Any]:
        """Berechne Aggregationen fuer ein Jahr."""
        amounts = await self._calculate_amounts(db, user_id, year)
        deadlines = await self._calculate_deadlines(db, user_id, year)

        return {
            "nachzahlung": amounts.get("nachzahlung", 0.0),
            "erstattung": amounts.get("erstattung", 0.0),
            "pending_deadlines": deadlines.get("pending", 0),
        }

    async def _calculate_amounts(
        self,
        db: AsyncSession,
        user_id: UUID,
        year: Optional[int],
    ) -> Dict[str, float]:
        """Berechne Nachzahlung/Erstattung-Summen aus JSONB.

        Nutzt SQL-Aggregation fuer Performance statt Python-Loop.
        PostgreSQL JSONB ->> Operator fuer Text-Extraktion.
        """
        # T.1 SECURITY FIX: Parameterisierte Query statt f-string fuer year
        # Baue IN-Clause als String (PostgreSQL-kompatibel) - doc_types sind Konstanten
        doc_types_str = ", ".join(f"'{dt}'" for dt in FINANCE_DOCUMENT_TYPES)

        # Build query with optional year parameter
        year_clause = "AND EXTRACT(YEAR FROM created_at) = :year" if year is not None else ""

        # Aggregiere Nachzahlung und Erstattung in einer Query
        # COALESCE fuer NULL-Handling, NULLIF fuer leere Strings
        query = text(f"""
            SELECT
                COALESCE(SUM(
                    CASE
                        WHEN extracted_data->>'nachzahlung' IS NOT NULL
                             AND extracted_data->>'nachzahlung' != ''
                        THEN (extracted_data->>'nachzahlung')::FLOAT
                        ELSE 0
                    END
                ), 0) as nachzahlung,
                COALESCE(SUM(
                    CASE
                        WHEN extracted_data->>'erstattung' IS NOT NULL
                             AND extracted_data->>'erstattung' != ''
                        THEN (extracted_data->>'erstattung')::FLOAT
                        ELSE 0
                    END
                ), 0) as erstattung
            FROM documents
            WHERE owner_id = :user_id
              AND is_deleted = FALSE
              AND document_type IN ({doc_types_str})
              {year_clause}
        """)

        # T.1 SECURITY FIX: year als Parameter statt String-Interpolation
        params: Dict[str, Any] = {"user_id": str(user_id)}
        if year is not None:
            params["year"] = year

        result = await db.execute(query, params)
        row = result.fetchone()

        return {
            "nachzahlung": float(row.nachzahlung) if row and row.nachzahlung else 0.0,
            "erstattung": float(row.erstattung) if row and row.erstattung else 0.0,
        }

    async def _calculate_deadlines(
        self,
        db: AsyncSession,
        user_id: UUID,
        year: Optional[int],
    ) -> Dict[str, int]:
        """Berechne Fristen-Counts direkt in SQL (Performance-optimiert).

        Nutzt PostgreSQL JSONB ->> Operator fuer Datum-Vergleich.
        """
        # T.1 SECURITY FIX: Parameterisierte Query statt f-string fuer year
        # Baue IN-Clause als String (PostgreSQL-kompatibel) - doc_types sind Konstanten
        doc_types_str = ", ".join(f"'{dt}'" for dt in FINANCE_DOCUMENT_TYPES)

        # Build query with optional year parameter
        year_clause = "AND EXTRACT(YEAR FROM created_at) = :year" if year is not None else ""

        today_str = date.today().isoformat()

        # SQL-basierte Zaehlung: Pending = Frist >= heute, Overdue = Frist < heute
        query = text(f"""
            SELECT
                COUNT(CASE
                    WHEN extracted_data->>'einspruchsfrist' IS NOT NULL
                         AND extracted_data->>'einspruchsfrist' >= :today
                    THEN 1
                END) as pending,
                COUNT(CASE
                    WHEN extracted_data->>'einspruchsfrist' IS NOT NULL
                         AND extracted_data->>'einspruchsfrist' < :today
                    THEN 1
                END) as overdue
            FROM documents
            WHERE owner_id = :user_id
              AND is_deleted = FALSE
              AND document_type IN ({doc_types_str})
              AND extracted_data->>'einspruchsfrist' IS NOT NULL
              {year_clause}
        """)

        # T.1 SECURITY FIX: year als Parameter statt String-Interpolation
        params: Dict[str, Any] = {
            "user_id": str(user_id),
            "today": today_str,
        }
        if year is not None:
            params["year"] = year

        result = await db.execute(query, params)
        row = result.fetchone()

        return {
            "pending": int(row.pending) if row and row.pending else 0,
            "overdue": int(row.overdue) if row and row.overdue else 0,
        }

    async def _get_documents_by_category(
        self,
        db: AsyncSession,
        user_id: UUID,
        year: Optional[int],
    ) -> Dict[str, int]:
        """Hole Dokument-Counts pro Kategorie."""
        conditions = [
            Document.owner_id == user_id,
            Document.is_deleted == False,
            Document.document_type.in_(list(FINANCE_DOCUMENT_TYPES)),
        ]

        if year is not None:
            conditions.append(extract("year", Document.created_at) == year)

        query = (
            select(
                Document.document_type,
                func.count(Document.id).label("count"),
            )
            .where(and_(*conditions))
            .group_by(Document.document_type)
        )

        result = await db.execute(query)
        rows = result.all()

        counts: Dict[str, int] = {}
        doctype_to_category = {v.value: k for k, v in FINANCE_CATEGORY_TO_DOCTYPE.items()}

        for row in rows:
            category = doctype_to_category.get(row.document_type)
            if category:
                counts[category] = row.count

        return counts

    def _aggregate_by_package(self, docs_by_category: Dict[str, int]) -> Dict[str, int]:
        """Aggregiere Kategorie-Counts nach Paket."""
        package_counts: Dict[str, int] = {
            "steuern": 0,
            "personal": 0,
            "versicherung": 0,
            "bank": 0,
        }

        for category, count in docs_by_category.items():
            package = CATEGORY_TO_PACKAGE.get(category)
            if package:
                package_counts[package] += count

        return package_counts

    async def _calculate_amounts_for_category(
        self,
        db: AsyncSession,
        user_id: UUID,
        year: int,
        category: str,
    ) -> Dict[str, float]:
        """Berechne Nachzahlung/Erstattung fuer eine Kategorie."""
        if category not in CATEGORIES_WITH_AMOUNTS:
            return {"nachzahlung": 0.0, "erstattung": 0.0}

        conditions = [
            Document.owner_id == user_id,
            Document.is_deleted == False,
            extract("year", Document.created_at) == year,
        ]

        if category in FINANCE_CATEGORY_TO_DOCTYPE:
            doc_type = FINANCE_CATEGORY_TO_DOCTYPE[category]
            conditions.append(Document.document_type == doc_type.value)

        # Query fuer Nachzahlung/Erstattung mit PostgreSQL JSONB ->> Operator
        nachzahlung_query = (
            select(
                func.coalesce(
                    func.sum(
                        func.cast(jsonb_text("extracted_data", "nachzahlung"), Float)
                    ),
                    0.0,
                )
            ).where(and_(*conditions))
        )

        erstattung_query = (
            select(
                func.coalesce(
                    func.sum(
                        func.cast(jsonb_text("extracted_data", "erstattung"), Float)
                    ),
                    0.0,
                )
            ).where(and_(*conditions))
        )

        nachzahlung_result = await db.execute(nachzahlung_query)
        erstattung_result = await db.execute(erstattung_query)

        nachzahlung = nachzahlung_result.scalar() or 0.0
        erstattung = erstattung_result.scalar() or 0.0

        return {
            "nachzahlung": float(nachzahlung) if nachzahlung else 0.0,
            "erstattung": float(erstattung) if erstattung else 0.0,
        }

    async def _calculate_deadlines_for_category(
        self,
        db: AsyncSession,
        user_id: UUID,
        year: int,
        category: str,
    ) -> Dict[str, int]:
        """Berechne Fristen fuer eine Kategorie (SQL-optimiert).

        Nutzt PostgreSQL JSONB ->> Operator fuer Datum-Vergleich.
        """
        if category not in CATEGORIES_WITH_DEADLINES:
            return {"pending": 0, "overdue": 0}

        # Bestimme document_type Filter
        doc_type_filter = ""
        if category in FINANCE_CATEGORY_TO_DOCTYPE:
            doc_type = FINANCE_CATEGORY_TO_DOCTYPE[category]
            doc_type_filter = f"AND document_type = '{doc_type.value}'"

        today_str = date.today().isoformat()

        # SQL-basierte Zaehlung mit CASE WHEN und JSONB ->>
        query = text(f"""
            SELECT
                COUNT(CASE
                    WHEN extracted_data->>'einspruchsfrist' >= :today THEN 1
                END) as pending,
                COUNT(CASE
                    WHEN extracted_data->>'einspruchsfrist' < :today THEN 1
                END) as overdue
            FROM documents
            WHERE owner_id = :user_id
              AND is_deleted = FALSE
              AND EXTRACT(YEAR FROM created_at) = :year
              AND extracted_data->>'einspruchsfrist' IS NOT NULL
              {doc_type_filter}
        """)

        result = await db.execute(
            query,
            {
                "user_id": str(user_id),
                "year": year,
                "today": today_str,
            }
        )
        row = result.fetchone()

        return {
            "pending": int(row.pending) if row and row.pending else 0,
            "overdue": int(row.overdue) if row and row.overdue else 0,
        }

    def _get_sort_column(self, sort_by: str) -> Any:
        """Hole Sortier-Spalte."""
        sort_map = {
            "document_date": Document.created_at,
            "created_at": Document.created_at,
            "updated_at": Document.updated_at,
            "filename": Document.filename,
            "file_size": Document.file_size,
        }
        return sort_map.get(sort_by, Document.created_at)

    def _to_finance_document_response(
        self,
        doc: Document,
        category: str,
    ) -> FinanceCategoryDocumentResponse:
        """Konvertiere Document zu FinanceCategoryDocumentResponse."""
        extracted_data = doc.extracted_data or {}

        # Finanz-spezifische Felder aus extracted_data
        einspruchsfrist = None
        if extracted_data.get("einspruchsfrist"):
            try:
                einspruchsfrist = datetime.fromisoformat(
                    extracted_data["einspruchsfrist"].replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                pass

        # Steuerart parsen
        steuerart = None
        if extracted_data.get("steuerart"):
            try:
                steuerart = TaxType(extracted_data["steuerart"])
            except ValueError:
                pass

        return FinanceCategoryDocumentResponse(
            id=doc.id,
            filename=doc.filename,
            original_filename=doc.original_filename or doc.filename,
            document_type=DocumentType(doc.document_type) if doc.document_type else DocumentType.OTHER,
            processing_status=ProcessingStatus(doc.status) if doc.status else ProcessingStatus.PENDING,
            file_size=doc.file_size or 0,
            page_count=doc.page_count or 0,
            mime_type=doc.mime_type,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            document_date=extracted_data.get("document_date"),
            ocr_confidence=doc.ocr_confidence,
            document_number=extracted_data.get("document_number"),
            total_amount=extracted_data.get("total_amount"),
            currency=extracted_data.get("currency", "EUR"),
            # Finanz-spezifische Felder
            einspruchsfrist=einspruchsfrist,
            aktenzeichen=extracted_data.get("aktenzeichen"),
            steuernummer=extracted_data.get("steuernummer"),
            finanzamt=extracted_data.get("finanzamt"),
            steuerart=steuerart,
            zeitraum=extracted_data.get("zeitraum"),
            nachzahlung=extracted_data.get("nachzahlung"),
            erstattung=extracted_data.get("erstattung"),
            versicherungsnummer=extracted_data.get("versicherungsnummer"),
            vertragsnummer=extracted_data.get("vertragsnummer"),
            tags=[tag.name for tag in doc.tags] if doc.tags else [],
            thumbnail_url=None,  # TODO: Generate if needed
            preview_url=None,  # TODO: Generate if needed
        )

    # =========================================================================
    # CRUD Methods
    # =========================================================================

    async def update_finance_document(
        self,
        db: AsyncSession,
        user_id: UUID,
        document_id: UUID,
        update_data: Dict[str, Any],
    ) -> Optional[Document]:
        """Aktualisiert Finanz-spezifische Felder eines Dokuments.

        Args:
            db: Datenbank-Session
            user_id: ID des Benutzers (fuer Zugriffskontrolle)
            document_id: ID des Dokuments
            update_data: Dictionary mit zu aktualisierenden Feldern

        Returns:
            Aktualisiertes Document oder None wenn nicht gefunden
        """
        # Hole Dokument
        query = (
            select(Document)
            .where(Document.id == document_id)
            .where(Document.owner_id == user_id)
            .where(Document.is_deleted == False)
        )
        result = await db.execute(query)
        document = result.scalar_one_or_none()

        if not document:
            return None

        # Extrahiere Kategorie-Aenderung
        new_category = update_data.pop("category", None)
        if new_category and new_category in FINANCE_CATEGORY_TO_DOCTYPE:
            document.document_type = FINANCE_CATEGORY_TO_DOCTYPE[new_category].value

        # Aktualisiere extracted_data
        if document.extracted_data is None:
            document.extracted_data = {}

        # Mappe Felder zu extracted_data
        field_mapping = {
            "einspruchsfrist": "einspruchsfrist",
            "aktenzeichen": "aktenzeichen",
            "steuernummer": "steuernummer",
            "finanzamt": "finanzamt",
            "steuerart": "steuerart",
            "zeitraum": "zeitraum",
            "nachzahlung": "nachzahlung",
            "erstattung": "erstattung",
            "versicherungsnummer": "versicherungsnummer",
            "vertragsnummer": "vertragsnummer",
            "document_date": "document_date",
            "document_number": "document_number",
            "total_amount": "total_amount",
        }

        for field, json_key in field_mapping.items():
            if field in update_data and update_data[field] is not None:
                value = update_data[field]
                # Datetime zu ISO-String konvertieren
                if isinstance(value, datetime):
                    value = value.isoformat()
                # Enum zu String
                elif hasattr(value, "value"):
                    value = value.value
                document.extracted_data[json_key] = value

        # Markiere extracted_data als geaendert (JSONB)
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(document, "extracted_data")

        document.updated_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(document)

        logger.info(
            "finance_document_updated",
            document_id=str(document_id),
            user_id=str(user_id),
            updated_fields=list(update_data.keys()),
        )

        return document

    async def delete_finance_document(
        self,
        db: AsyncSession,
        user_id: UUID,
        document_id: UUID,
    ) -> Optional[Document]:
        """Loescht ein Finanz-Dokument (Soft-Delete).

        Args:
            db: Datenbank-Session
            user_id: ID des Benutzers
            document_id: ID des Dokuments

        Returns:
            Geloeschtes Document oder None wenn nicht gefunden
        """
        query = (
            select(Document)
            .where(Document.id == document_id)
            .where(Document.owner_id == user_id)
            .where(Document.is_deleted == False)
        )
        result = await db.execute(query)
        document = result.scalar_one_or_none()

        if not document:
            return None

        # Soft-Delete
        document.is_deleted = True
        document.deleted_at = datetime.now(timezone.utc)
        document.updated_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(document)

        logger.info(
            "finance_document_deleted",
            document_id=str(document_id),
            user_id=str(user_id),
        )

        return document

    async def get_finance_document(
        self,
        db: AsyncSession,
        user_id: UUID,
        document_id: UUID,
    ) -> Optional[Document]:
        """Holt ein einzelnes Finanz-Dokument.

        Args:
            db: Datenbank-Session
            user_id: ID des Benutzers
            document_id: ID des Dokuments

        Returns:
            Document oder None
        """
        query = (
            select(Document)
            .where(Document.id == document_id)
            .where(Document.owner_id == user_id)
            .where(Document.is_deleted == False)
            .options(selectinload(Document.tags))
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()


# Singleton-Pattern
_finance_service: Optional[FinanceService] = None


def get_finance_service() -> FinanceService:
    """Hole oder erstelle Singleton-Instanz des FinanceService."""
    global _finance_service
    if _finance_service is None:
        _finance_service = FinanceService()
    return _finance_service
