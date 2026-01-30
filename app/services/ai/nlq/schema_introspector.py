"""Schema Introspector - Stellt DB-Schema-Kontext fuer LLM bereit."""

from typing import Dict, List, Set

import structlog
from sqlalchemy import MetaData, Table, inspect
from sqlalchemy.ext.asyncio import AsyncEngine

from app.services.ai.nlq.sql_sanitizer import ALLOWED_TABLES, PII_COLUMNS
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


class SchemaIntrospector:
    """Provides database schema context for LLM SQL generation.

    Security Features:
        - Only includes ALLOWED_TABLES
        - Excludes PII columns from descriptions
        - Provides human-readable schema documentation
    """

    def __init__(self, engine: AsyncEngine):
        """Initialize schema introspector.

        Args:
            engine: SQLAlchemy async engine
        """
        self.engine = engine
        self._schema_cache: str | None = None

    async def get_schema_context(self) -> str:
        """Get human-readable schema description for LLM.

        Returns:
            Formatted schema context in German

        Caching:
            Schema is cached after first retrieval for performance
        """
        if self._schema_cache is not None:
            return self._schema_cache

        try:
            schema_lines: List[str] = [
                "# Datenbank-Schema für SQL-Generierung",
                "",
                "## Verfügbare Tabellen:",
                "",
            ]

            # Get metadata
            metadata = MetaData()
            async with self.engine.connect() as conn:
                await conn.run_sync(metadata.reflect)

            # Process each allowed table
            for table_name in sorted(ALLOWED_TABLES):
                if table_name not in metadata.tables:
                    continue

                table: Table = metadata.tables[table_name]
                schema_lines.append(f"### {table_name}")
                schema_lines.append("")

                # Add column descriptions
                columns = self._get_safe_columns(table)
                if columns:
                    schema_lines.append("**Spalten:**")
                    for col_name, col_type in columns.items():
                        schema_lines.append(f"- `{col_name}`: {col_type}")
                    schema_lines.append("")

                # Add common use cases
                use_cases = self._get_table_use_cases(table_name)
                if use_cases:
                    schema_lines.append("**Typische Abfragen:**")
                    for use_case in use_cases:
                        schema_lines.append(f"- {use_case}")
                    schema_lines.append("")

            # Add relationships
            schema_lines.append("## Wichtige Beziehungen:")
            schema_lines.append("")
            schema_lines.extend(self._get_relationships())

            # Add notes
            schema_lines.append("")
            schema_lines.append("## Hinweise:")
            schema_lines.append("")
            schema_lines.append(
                "- Alle Tabellen haben `company_id` für Multi-Tenant-Isolation"
            )
            schema_lines.append(
                "- Zeitstempel sind in UTC (`created_at`, `updated_at`)"
            )
            schema_lines.append(
                "- UUIDs werden als Primärschlüssel verwendet (`id`)"
            )
            schema_lines.append(
                "- JSONB-Spalten enthalten strukturierte Metadaten"
            )

            self._schema_cache = "\n".join(schema_lines)
            logger.info(
                "schema_context_generated",
                table_count=len(ALLOWED_TABLES),
                cache_size=len(self._schema_cache),
            )

            return self._schema_cache

        except Exception as e:
            logger.error("schema_introspection_failed", **safe_error_log(e))
            # Return minimal schema on error
            return self._get_minimal_schema()

    def _get_safe_columns(self, table: Table) -> Dict[str, str]:
        """Get columns excluding PII.

        Args:
            table: SQLAlchemy Table object

        Returns:
            Dict of column_name -> type_description
        """
        columns: Dict[str, str] = {}

        for column in table.columns:
            # Skip PII columns
            if column.name.lower() in PII_COLUMNS:
                continue

            # Format type
            col_type = str(column.type)
            if column.nullable:
                col_type += " (nullable)"
            if column.primary_key:
                col_type += " (PK)"

            columns[column.name] = col_type

        return columns

    def _get_table_use_cases(self, table_name: str) -> List[str]:
        """Get typical use cases for a table.

        Args:
            table_name: Name of the table

        Returns:
            List of German use case descriptions
        """
        use_cases_map: Dict[str, List[str]] = {
            "documents": [
                "Dokumente nach Status filtern (z.B. WHERE status = 'processed')",
                "Anzahl Dokumente pro Monat (GROUP BY EXTRACT(MONTH FROM created_at))",
                "Dokumente mit hoher OCR-Confidence (WHERE metadata->>'ocr_confidence' > '0.9')",
            ],
            "business_entities": [
                "Kunden mit höchstem Umsatz (ORDER BY total_invoice_amount DESC)",
                "Entitäten mit Risiko-Score (WHERE risk_score > 75)",
                "Anzahl Kunden vs. Lieferanten (GROUP BY entity_type)",
            ],
            "invoice_tracking": [
                "Überfällige Rechnungen (WHERE status = 'overdue')",
                "Durchschnittliche Zahlungsdauer (AVG(EXTRACT(EPOCH FROM paid_at - due_date)))",
                "Rechnungen mit Skonto-Option (WHERE skonto_percentage > 0)",
            ],
            "alerts": [
                "Kritische Alerts (WHERE severity = 'critical' AND status = 'new')",
                "Alerts pro Kategorie (GROUP BY category)",
                "Alert-Trends (COUNT(*) GROUP BY DATE(created_at))",
            ],
            "bank_transactions": [
                "Transaktionen nach Betrag (ORDER BY amount DESC)",
                "Monatliche Cashflow-Summe (SUM(amount) GROUP BY EXTRACT(MONTH FROM transaction_date))",
                "Nicht zugeordnete Transaktionen (WHERE reconciliation_status = 'unmatched')",
            ],
            "contracts": [
                "Bald ablaufende Verträge (WHERE end_date < NOW() + INTERVAL '30 days')",
                "Verträge nach Wert (ORDER BY contract_value DESC)",
                "Auto-Renewal Verträge (WHERE auto_renew = true)",
            ],
            "shipping_tracking": [
                "Aktive Sendungen (WHERE status NOT IN ('delivered', 'cancelled'))",
                "Verspätete Sendungen (WHERE status = 'delayed')",
                "Sendungen pro Carrier (GROUP BY carrier)",
            ],
        }

        return use_cases_map.get(table_name, [])

    def _get_relationships(self) -> List[str]:
        """Get important table relationships.

        Returns:
            List of relationship descriptions in German
        """
        return [
            "- `documents.folder_id` → `folders.id` (Ordnerstruktur)",
            "- `documents.entity_id` → `business_entities.id` (Geschäftspartner)",
            "- `invoice_tracking.document_id` → `documents.id` (Rechnungsdokument)",
            "- `invoice_tracking.entity_id` → `business_entities.id` (Rechnungssteller)",
            "- `document_chains.related_document_id` → `documents.id` (Dokumentenkette)",
            "- `alerts.document_id` → `documents.id` (Alert-Quelle)",
            "- `alerts.entity_id` → `business_entities.id` (Betroffene Entität)",
            "- `bank_transactions.matched_invoice_id` → `invoice_tracking.id` (Zuordnung)",
            "- `shipping_tracking.document_id` → `documents.id` (Versanddokument)",
            "- `contracts.entity_id` → `business_entities.id` (Vertragspartner)",
        ]

    def _get_minimal_schema(self) -> str:
        """Get minimal schema on error.

        Returns:
            Basic schema description
        """
        return """# Datenbank-Schema (Minimal)

## Verfügbare Tabellen:

- documents (Dokumente)
- business_entities (Geschäftspartner)
- invoice_tracking (Rechnungen)
- alerts (Benachrichtigungen)
- bank_transactions (Banktransaktionen)
- contracts (Verträge)

## Hinweis:
Verwende Standard-Spalten wie id, created_at, updated_at, company_id.
Alle Tabellen haben company_id für Multi-Tenant-Isolation.
"""

    def invalidate_cache(self) -> None:
        """Invalidate schema cache.

        Call this after schema changes (migrations).
        """
        self._schema_cache = None
        logger.info("schema_cache_invalidated")
