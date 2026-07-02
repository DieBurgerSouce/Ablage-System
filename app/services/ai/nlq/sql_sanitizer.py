"""SQL Sanitizer - Verhindert SQL-Injection bei LLM-generierten Queries.

SECURITY CRITICAL: Dieser Service ist die letzte Verteidigungslinie gegen
SQL-Injection bei LLM-generierten SQL-Statements.
"""

import re
from dataclasses import dataclass, field
from typing import List, Set
from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)

# Allowed tables (whitelist)
ALLOWED_TABLES: Set[str] = {
    "documents",
    "business_entities",
    "invoice_tracking",
    "document_chains",
    "alerts",
    "smart_inbox_items",
    "zero_touch_results",
    "folders",
    "tags",
    "document_tags",
    "companies",
    "users",
    "approval_requests",
    "document_versions",
    "shipping_tracking",
    "contracts",
    "bank_transactions",
    "cash_entries",
    "expenses",
    "nlq_query_logs",
}

# Forbidden columns (PII blacklist)
PII_COLUMNS: Set[str] = {
    "password_hash",
    "totp_secret",
    "backup_codes",
    "refresh_token",
    "iban",
    "bic",
    "vat_id",
    "tax_id",
    "ssn",
    "api_key",
    "api_secret",
    "webhook_secret",
    "email_password",
    "imap_password",
}

# Forbidden SQL operations
FORBIDDEN_PATTERNS: List[str] = [
    r"\b(DROP|DELETE|INSERT|UPDATE|ALTER|CREATE|TRUNCATE|GRANT|REVOKE)\b",
    r"\b(EXEC|EXECUTE|CALL)\b",
    r"--",  # SQL comments
    r"/\*",  # Block comments
    r";\s*\w",  # Multiple statements
    r"\bINTO\s+OUTFILE\b",
    r"\bLOAD\s+DATA\b",
    r"\bINTO\s+DUMPFILE\b",
]


@dataclass
class SanitizationResult:
    """Ergebnis der SQL-Sanitization."""

    safe: bool
    sanitized_sql: str
    original_sql: str
    violations: List[str] = field(default_factory=list)
    tables_used: Set[str] = field(default_factory=set)
    company_id_injected: bool = False


class SQLSanitizer:
    """Sanitizes LLM-generated SQL to prevent injection attacks.

    SECURITY CRITICAL:
    - Only SELECT statements allowed
    - Table whitelist enforcement
    - PII column blacklist
    - Company ID injection for multi-tenant isolation
    - Pattern-based attack detection
    """

    MAX_RESULT_ROWS: int = 1000
    QUERY_TIMEOUT_SECONDS: int = 10

    def sanitize(self, sql: str, company_id: UUID) -> SanitizationResult:
        """Sanitize and validate SQL query.

        Args:
            sql: LLM-generated SQL query
            company_id: Company ID for multi-tenant isolation

        Returns:
            SanitizationResult with safe flag and sanitized SQL

        Security Features:
            - SELECT-only enforcement
            - Table whitelist validation
            - PII column blacklist
            - SQL injection pattern detection
            - Automatic company_id filter injection
            - Result row limit enforcement
        """
        violations: List[str] = []
        original_sql = sql.strip()

        # 1. Must be SELECT only
        if not re.match(r"^\s*SELECT\b", original_sql, re.IGNORECASE):
            violations.append("Nur SELECT-Abfragen sind erlaubt")
            logger.warning(
                "sql_sanitization_non_select",
                sql_prefix=original_sql[:100],
            )
            return SanitizationResult(
                safe=False,
                sanitized_sql="",
                original_sql=original_sql,
                violations=violations,
            )

        # 2. Check forbidden patterns
        for pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, original_sql, re.IGNORECASE):
                violations.append(f"Verbotenes SQL-Pattern erkannt: {pattern}")
                logger.warning(
                    "sql_sanitization_forbidden_pattern",
                    pattern=pattern,
                    sql_prefix=original_sql[:100],
                )

        # 3. Extract and validate tables
        tables_used = self._extract_tables(original_sql)
        for table in tables_used:
            if table.lower() not in ALLOWED_TABLES:
                violations.append(f"Tabelle nicht erlaubt: {table}")
                logger.warning(
                    "sql_sanitization_forbidden_table",
                    table=table,
                )

        # 4. Check PII columns
        for col in PII_COLUMNS:
            if re.search(rf"\b{re.escape(col)}\b", original_sql, re.IGNORECASE):
                violations.append(f"Zugriff auf geschuetzte Spalte: {col}")
                logger.warning(
                    "sql_sanitization_pii_column",
                    column=col,
                )

        if violations:
            logger.warning(
                "sql_sanitization_failed",
                violation_count=len(violations),
                violations=violations,
            )
            return SanitizationResult(
                safe=False,
                sanitized_sql="",
                original_sql=original_sql,
                violations=violations,
                tables_used=tables_used,
            )

        # 5. Inject company_id filter (fail-closed bei ungueltiger company_id)
        try:
            sanitized = self._inject_company_filter(original_sql, company_id)
        except ValueError as exc:
            violations.append("Ungueltige company_id - Multi-Tenant-Filter nicht moeglich")
            logger.warning(
                "sql_sanitization_invalid_company_id",
                error=str(exc),
            )
            return SanitizationResult(
                safe=False,
                sanitized_sql="",
                original_sql=original_sql,
                violations=violations,
                tables_used=tables_used,
            )

        # 6. Add LIMIT
        if not re.search(r"\bLIMIT\b", sanitized, re.IGNORECASE):
            sanitized = f"{sanitized.rstrip(';')} LIMIT {self.MAX_RESULT_ROWS}"

        logger.info(
            "sql_sanitization_success",
            tables_used=list(tables_used),
            company_id_injected=True,
        )

        return SanitizationResult(
            safe=True,
            sanitized_sql=sanitized,
            original_sql=original_sql,
            tables_used=tables_used,
            company_id_injected=True,
        )

    def _extract_tables(self, sql: str) -> Set[str]:
        """Extract table names from SQL.

        Args:
            sql: SQL query string

        Returns:
            Set of lowercase table names
        """
        tables: Set[str] = set()
        # FROM and JOIN clauses
        for match in re.finditer(
            r"\b(?:FROM|JOIN)\s+(\w+)", sql, re.IGNORECASE
        ):
            tables.add(match.group(1).lower())
        return tables

    def _inject_company_filter(self, sql: str, company_id: UUID) -> str:
        """Inject company_id WHERE filter for multi-tenant isolation.

        Args:
            sql: Original SQL query
            company_id: Company ID to filter by

        Returns:
            SQL with company_id filter injected

        Multi-Tenant Security:
            - Always injects company_id = '{company_id}' filter
            - Handles existing WHERE clauses (AND conjunction)
            - Handles missing WHERE clauses (injects before ORDER BY/LIMIT)
        """
        # SECURITY (W2-19): company_id wird in reines String-SQL interpoliert.
        # Strikt validieren, dass es eine echte UUID ist (kein injizierbarer Wert),
        # und nur die kanonische UUID-Stringform interpolieren. Fail-closed.
        validated_company_id = UUID(str(company_id))
        company_filter = f"company_id = '{validated_company_id}'"

        if re.search(r"\bWHERE\b", sql, re.IGNORECASE):
            # Add to existing WHERE clause
            sql = re.sub(
                r"\bWHERE\b",
                f"WHERE {company_filter} AND",
                sql,
                count=1,
                flags=re.IGNORECASE,
            )
        else:
            # Add WHERE before GROUP BY, ORDER BY, LIMIT, HAVING, or end
            for clause in [
                r"\bGROUP\s+BY\b",
                r"\bORDER\s+BY\b",
                r"\bLIMIT\b",
                r"\bHAVING\b",
                r"$",
            ]:
                match = re.search(clause, sql, re.IGNORECASE)
                if match:
                    pos = match.start()
                    sql = f"{sql[:pos]} WHERE {company_filter} {sql[pos:]}"
                    break

        return sql
