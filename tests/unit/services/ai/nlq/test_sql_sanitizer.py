"""Unit tests for SQLSanitizer - SECURITY CRITICAL."""

import pytest
from uuid import uuid4

from app.services.ai.nlq.sql_sanitizer import SQLSanitizer, SanitizationResult


class TestSQLSanitizer:
    """Test suite for SQL sanitizer security features."""

    @pytest.fixture
    def sanitizer(self) -> SQLSanitizer:
        """Create sanitizer instance."""
        return SQLSanitizer()

    @pytest.fixture
    def company_id(self):
        """Test company ID."""
        return uuid4()

    # =========================================================================
    # SELECT-Only Enforcement
    # =========================================================================

    def test_allows_select_query(
        self, sanitizer: SQLSanitizer, company_id
    ):
        """Valid SELECT query should pass."""
        sql = "SELECT * FROM documents"
        result = sanitizer.sanitize(sql, company_id)

        assert result.safe is True
        assert result.sanitized_sql
        assert "SELECT" in result.sanitized_sql

    @pytest.mark.parametrize(
        "malicious_sql",
        [
            "DROP TABLE users",
            "DELETE FROM documents",
            "INSERT INTO users VALUES ('hacker')",
            "UPDATE documents SET status = 'deleted'",
            "ALTER TABLE documents ADD COLUMN hacked TEXT",
            "TRUNCATE TABLE users",
            "GRANT ALL ON documents TO hacker",
        ],
    )
    def test_blocks_non_select_operations(
        self, sanitizer: SQLSanitizer, company_id, malicious_sql
    ):
        """Non-SELECT operations should be blocked."""
        result = sanitizer.sanitize(malicious_sql, company_id)

        assert result.safe is False
        assert len(result.violations) > 0
        assert "SELECT" in result.violations[0]

    # =========================================================================
    # Table Whitelist
    # =========================================================================

    def test_allows_whitelisted_tables(
        self, sanitizer: SQLSanitizer, company_id
    ):
        """Whitelisted tables should be allowed."""
        allowed_tables = [
            "documents",
            "business_entities",
            "invoice_tracking",
            "alerts",
        ]

        for table in allowed_tables:
            sql = f"SELECT * FROM {table}"
            result = sanitizer.sanitize(sql, company_id)
            assert result.safe is True, f"Table {table} should be allowed"

    def test_blocks_non_whitelisted_tables(
        self, sanitizer: SQLSanitizer, company_id
    ):
        """Non-whitelisted tables should be blocked."""
        sql = "SELECT * FROM malicious_table"
        result = sanitizer.sanitize(sql, company_id)

        assert result.safe is False
        assert any("nicht erlaubt" in v for v in result.violations)

    # =========================================================================
    # PII Column Protection
    # =========================================================================

    @pytest.mark.parametrize(
        "pii_column",
        [
            "password_hash",
            "totp_secret",
            "backup_codes",
            "iban",
            "vat_id",
            "api_key",
        ],
    )
    def test_blocks_pii_columns(
        self, sanitizer: SQLSanitizer, company_id, pii_column
    ):
        """PII columns should be blocked."""
        sql = f"SELECT {pii_column} FROM users"
        result = sanitizer.sanitize(sql, company_id)

        assert result.safe is False
        assert any(
            "geschuetzte Spalte" in v for v in result.violations
        )

    # =========================================================================
    # SQL Injection Pattern Detection
    # =========================================================================

    @pytest.mark.parametrize(
        "injection_attempt",
        [
            "SELECT * FROM users; DROP TABLE documents; --",
            "SELECT * FROM users -- comment",
            "SELECT * FROM users /* block comment */",
            "SELECT * INTO OUTFILE '/tmp/hack.txt' FROM users",
            "EXEC xp_cmdshell 'rm -rf /'",
        ],
    )
    def test_blocks_sql_injection_patterns(
        self, sanitizer: SQLSanitizer, company_id, injection_attempt
    ):
        """SQL injection patterns should be detected."""
        result = sanitizer.sanitize(injection_attempt, company_id)

        assert result.safe is False
        assert len(result.violations) > 0

    # =========================================================================
    # Company ID Injection
    # =========================================================================

    def test_injects_company_id_no_where(
        self, sanitizer: SQLSanitizer, company_id
    ):
        """Should inject company_id when no WHERE clause."""
        sql = "SELECT * FROM documents"
        result = sanitizer.sanitize(sql, company_id)

        assert result.safe is True
        assert result.company_id_injected is True
        assert f"company_id = '{company_id}'" in result.sanitized_sql

    def test_injects_company_id_with_existing_where(
        self, sanitizer: SQLSanitizer, company_id
    ):
        """Should inject company_id before existing WHERE clause."""
        sql = "SELECT * FROM documents WHERE status = 'processed'"
        result = sanitizer.sanitize(sql, company_id)

        assert result.safe is True
        assert result.company_id_injected is True
        assert f"company_id = '{company_id}'" in result.sanitized_sql
        assert "AND" in result.sanitized_sql

    def test_injects_company_id_before_order_by(
        self, sanitizer: SQLSanitizer, company_id
    ):
        """Should inject company_id before ORDER BY."""
        sql = "SELECT * FROM documents ORDER BY created_at DESC"
        result = sanitizer.sanitize(sql, company_id)

        assert result.safe is True
        assert result.company_id_injected is True
        # company_id WHERE should come before ORDER BY
        where_pos = result.sanitized_sql.find("WHERE")
        order_pos = result.sanitized_sql.upper().find("ORDER BY")
        assert where_pos < order_pos

    # =========================================================================
    # Result Row Limit
    # =========================================================================

    def test_adds_limit_when_missing(
        self, sanitizer: SQLSanitizer, company_id
    ):
        """Should add LIMIT when not present."""
        sql = "SELECT * FROM documents"
        result = sanitizer.sanitize(sql, company_id)

        assert result.safe is True
        assert "LIMIT" in result.sanitized_sql.upper()
        assert str(sanitizer.MAX_RESULT_ROWS) in result.sanitized_sql

    def test_preserves_existing_limit(
        self, sanitizer: SQLSanitizer, company_id
    ):
        """Should preserve user's LIMIT if present."""
        sql = "SELECT * FROM documents LIMIT 10"
        result = sanitizer.sanitize(sql, company_id)

        assert result.safe is True
        assert result.sanitized_sql.count("LIMIT") == 1

    # =========================================================================
    # Table Extraction
    # =========================================================================

    def test_extracts_tables_from_query(
        self, sanitizer: SQLSanitizer, company_id
    ):
        """Should extract all table names."""
        sql = """
            SELECT d.*, b.name
            FROM documents d
            JOIN business_entities b ON d.entity_id = b.id
        """
        result = sanitizer.sanitize(sql, company_id)

        assert "documents" in result.tables_used
        assert "business_entities" in result.tables_used

    # =========================================================================
    # Complex Query Scenarios
    # =========================================================================

    def test_complex_valid_query(
        self, sanitizer: SQLSanitizer, company_id
    ):
        """Complex but valid query should pass."""
        sql = """
            SELECT
                COUNT(*) as total,
                status
            FROM documents
            WHERE created_at > NOW() - INTERVAL '7 days'
            GROUP BY status
            ORDER BY total DESC
        """
        result = sanitizer.sanitize(sql, company_id)

        assert result.safe is True
        assert result.company_id_injected is True
        assert "LIMIT" in result.sanitized_sql.upper()

    def test_join_with_aggregation(
        self, sanitizer: SQLSanitizer, company_id
    ):
        """JOIN with aggregation should pass."""
        sql = """
            SELECT
                b.name,
                SUM(i.amount) as total_amount
            FROM invoice_tracking i
            JOIN business_entities b ON i.entity_id = b.id
            GROUP BY b.name
            ORDER BY total_amount DESC
        """
        result = sanitizer.sanitize(sql, company_id)

        assert result.safe is True
        assert len(result.tables_used) == 2

    # =========================================================================
    # Edge Cases
    # =========================================================================

    def test_empty_query(self, sanitizer: SQLSanitizer, company_id):
        """Empty query should be rejected."""
        result = sanitizer.sanitize("", company_id)

        assert result.safe is False

    def test_whitespace_only_query(
        self, sanitizer: SQLSanitizer, company_id
    ):
        """Whitespace-only query should be rejected."""
        result = sanitizer.sanitize("   \n\t  ", company_id)

        assert result.safe is False

    def test_case_insensitive_select(
        self, sanitizer: SQLSanitizer, company_id
    ):
        """SELECT in any case should pass."""
        for sql in ["select * from documents", "SeLeCt * FrOm documents"]:
            result = sanitizer.sanitize(sql, company_id)
            assert result.safe is True

    # =========================================================================
    # Security Regression Tests
    # =========================================================================

    def test_advanced_sql_injection_union(
        self, sanitizer: SQLSanitizer, company_id
    ):
        """UNION-based SQL injection should be blocked."""
        sql = "SELECT * FROM documents UNION SELECT password_hash FROM users"
        result = sanitizer.sanitize(sql, company_id)

        assert result.safe is False
        # Should block due to password_hash PII column

    def test_sql_injection_with_comments(
        self, sanitizer: SQLSanitizer, company_id
    ):
        """SQL injection with comment evasion should be blocked."""
        sql = "SELECT * FROM documents/**/WHERE/**/1=1--"
        result = sanitizer.sanitize(sql, company_id)

        assert result.safe is False
        # Should block due to /* comment pattern

    def test_stacked_queries(
        self, sanitizer: SQLSanitizer, company_id
    ):
        """Stacked queries should be blocked."""
        sql = "SELECT * FROM documents; SELECT * FROM users"
        result = sanitizer.sanitize(sql, company_id)

        assert result.safe is False
        # Should block due to semicolon pattern
