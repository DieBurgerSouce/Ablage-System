"""
Tests for JSONB SQL Injection protection in EntitySearchService.

These tests verify that the entity search service properly validates
JSONB column and key names to prevent SQL injection (CWE-89).

Created: 2026-01-27
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.entity_search_service import (
    EntitySearchService,
    VALID_COMPANIES,
    VALID_LEXWARE_FIELDS,
    _validate_company,
    _validate_lexware_field,
)


class TestJSONBWhitelistConstants:
    """Test suite for JSONB validation whitelist constants."""

    def test_valid_companies_is_frozenset(self) -> None:
        """VALID_COMPANIES should be an immutable frozenset."""
        assert isinstance(VALID_COMPANIES, frozenset)

    def test_valid_companies_not_empty(self) -> None:
        """VALID_COMPANIES should contain at least one company."""
        assert len(VALID_COMPANIES) > 0

    def test_valid_companies_are_lowercase(self) -> None:
        """All company names should be lowercase for consistent matching."""
        for company in VALID_COMPANIES:
            assert company == company.lower(), f"Company '{company}' should be lowercase"

    def test_valid_lexware_fields_is_frozenset(self) -> None:
        """VALID_LEXWARE_FIELDS should be an immutable frozenset."""
        assert isinstance(VALID_LEXWARE_FIELDS, frozenset)

    def test_valid_lexware_fields_not_empty(self) -> None:
        """VALID_LEXWARE_FIELDS should contain expected fields."""
        assert len(VALID_LEXWARE_FIELDS) > 0

        # Common expected fields
        expected_fields = {"kd_nr", "lief_nr", "matchcode"}
        for field in expected_fields:
            assert field in VALID_LEXWARE_FIELDS, f"Expected field '{field}' not in whitelist"

    def test_whitelists_are_immutable(self) -> None:
        """Whitelists should not be modifiable."""
        with pytest.raises(AttributeError):
            VALID_COMPANIES.add("injection")  # type: ignore

        with pytest.raises(AttributeError):
            VALID_LEXWARE_FIELDS.add("injection")  # type: ignore


class TestCompanyValidation:
    """Test suite for company name validation."""

    def test_valid_company_names_accepted(self) -> None:
        """Valid company names should be accepted."""
        for company in VALID_COMPANIES:
            result = _validate_company(company)
            assert result == company

    def test_valid_company_case_insensitive(self) -> None:
        """Company validation should be case-insensitive."""
        # Get a valid company
        valid_company = next(iter(VALID_COMPANIES))

        # Test with different cases
        assert _validate_company(valid_company.upper()) == valid_company
        assert _validate_company(valid_company.title()) == valid_company
        assert _validate_company(valid_company.lower()) == valid_company

    def test_invalid_company_rejected(self) -> None:
        """Invalid company names should raise ValueError."""
        invalid_companies = [
            "malicious_company",
            "'; DROP TABLE--",
            "1=1; --",
            "../../../etc/passwd",
            "folie'; DELETE FROM--",
        ]

        for company in invalid_companies:
            with pytest.raises(ValueError) as exc_info:
                _validate_company(company)
            assert "Ungueltige Firma" in str(exc_info.value) or "ungültig" in str(exc_info.value).lower()

    def test_none_company_returns_none(self) -> None:
        """None company should return None (no filtering)."""
        result = _validate_company(None)
        assert result is None

    def test_empty_company_rejected(self) -> None:
        """Empty string company is rejected (fail-closed, CWE-89).

        W3 (2026-06-12): Echter Vertrag — nur ``None`` bedeutet "kein
        Firmen-Filter". Ein Leerstring ist KEIN gueltiger JSONB-Key und
        wird von der Whitelist-Validierung explizit abgelehnt statt
        stillschweigend durchgereicht.
        """
        with pytest.raises(ValueError):
            _validate_company("")


class TestLexwareFieldValidation:
    """Test suite for Lexware field name validation."""

    def test_valid_fields_accepted(self) -> None:
        """Valid Lexware field names should be accepted."""
        for field in VALID_LEXWARE_FIELDS:
            result = _validate_lexware_field(field)
            assert result == field

    def test_invalid_field_rejected(self) -> None:
        """Invalid field names should raise ValueError."""
        injection_attempts = [
            "'; DROP TABLE--",
            "1=1; --",
            "kd_nr'; DELETE--",
            "../../../etc/passwd",
            "field OR 1=1",
            "field UNION SELECT",
            "kd_nr)--",
            "kd_nr; TRUNCATE",
        ]

        for field in injection_attempts:
            with pytest.raises(ValueError):
                _validate_lexware_field(field)

    def test_sql_keywords_rejected(self) -> None:
        """SQL keywords should be rejected even if formatted like fields."""
        sql_keywords = [
            "SELECT",
            "DELETE",
            "UPDATE",
            "INSERT",
            "DROP",
            "TRUNCATE",
            "UNION",
            "OR",
            "AND",
        ]

        for keyword in sql_keywords:
            if keyword.lower() not in VALID_LEXWARE_FIELDS:
                with pytest.raises(ValueError):
                    _validate_lexware_field(keyword)


def _make_empty_db_mock() -> AsyncMock:
    """AsyncSession-Mock: alle Queries liefern leere Ergebnisse.

    Deckt alle vom Service genutzten Result-Pfade ab
    (scalar_one_or_none, scalars().first/all).
    """
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value.first.return_value = None
    mock_result.scalars.return_value.all.return_value = []
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    return mock_db


class TestSQLInjectionPrevention:
    """Integration tests for SQL injection prevention.

    W3 (2026-06-12): Auf den echten Service-Vertrag modernisiert.
    ``search_by_lexware_id(db=..., field=...)`` hat nie existiert; die
    realen Suchpfade sind ``find_by_customer_number``/``find_by_company``
    (db kommt in den Konstruktor, W2/W1-029). Einen frei waehlbaren
    JSONB-Feldnamen nimmt die Service-API bewusst NICHT mehr an —
    Feld-Validierung passiert in ``_validate_lexware_field``.
    """

    @pytest.mark.asyncio
    async def test_jsonb_query_with_valid_params(self) -> None:
        """Valid parameters should produce safe queries (no raise)."""
        mock_db = _make_empty_db_mock()
        service = EntitySearchService(mock_db)

        valid_company = next(iter(VALID_COMPANIES))

        result = await service.find_by_customer_number(
            "12345", company=valid_company
        )

        assert result is None  # leere DB -> kein Treffer
        assert mock_db.execute.called

    @pytest.mark.asyncio
    async def test_jsonb_query_rejects_injection_in_company(self) -> None:
        """SQL injection in company parameter should be caught."""
        mock_db = _make_empty_db_mock()
        service = EntitySearchService(mock_db)

        with pytest.raises(ValueError):
            await service.find_by_customer_number(
                "12345",
                company="'; DROP TABLE business_entities--",
            )

    @pytest.mark.asyncio
    async def test_find_by_company_rejects_injection(self) -> None:
        """find_by_company validiert die Firma ebenfalls (CWE-89)."""
        mock_db = _make_empty_db_mock()
        service = EntitySearchService(mock_db)

        with pytest.raises(ValueError):
            await service.find_by_company("folie'; DELETE FROM--")

    def test_jsonb_query_rejects_injection_in_field(self) -> None:
        """SQL injection in field names is caught by the field whitelist."""
        with pytest.raises(ValueError):
            _validate_lexware_field("kd_nr'; DELETE FROM--")

    @pytest.mark.asyncio
    async def test_value_is_parameterized(self) -> None:
        """The value parameter should be safely parameterized, not interpolated."""
        mock_db = _make_empty_db_mock()
        service = EntitySearchService(mock_db)

        valid_company = next(iter(VALID_COMPANIES))

        # This value contains SQL injection attempt
        # It should be safely parameterized, not interpolated
        dangerous_value = "12345'; DROP TABLE--"

        # Should NOT raise - value is parameterized by SQLAlchemy
        result = await service.find_by_customer_number(
            dangerous_value, company=valid_company
        )

        assert result is None
        # Verify execute was called (query was built)
        assert mock_db.execute.called


class TestValidationEdgeCases:
    """Edge case tests for validation functions."""

    def test_unicode_in_company_name(self) -> None:
        """Unicode characters should be handled correctly."""
        # Unless a unicode company is whitelisted, this should fail
        with pytest.raises(ValueError):
            _validate_company("mäller")

    def test_whitespace_handling(self) -> None:
        """Whitespace should be stripped or rejected."""
        valid_company = next(iter(VALID_COMPANIES))

        # Leading/trailing whitespace - may be stripped or cause error
        try:
            result = _validate_company(f"  {valid_company}  ")
            assert result == valid_company or result == f"  {valid_company}  "
        except ValueError:
            # Also acceptable to reject whitespace-padded input
            pass

    def test_null_byte_injection(self) -> None:
        """Null byte injection should be prevented."""
        with pytest.raises(ValueError):
            _validate_company("folie\x00malicious")

        with pytest.raises(ValueError):
            _validate_lexware_field("kd_nr\x00malicious")

    def test_newline_injection(self) -> None:
        """Newline injection should be prevented."""
        with pytest.raises(ValueError):
            _validate_company("folie\nDROP TABLE")

        with pytest.raises(ValueError):
            _validate_lexware_field("kd_nr\nDELETE")


class TestSecurityDocumentation:
    """Tests verifying security documentation and comments."""

    def test_cwe_reference_in_source(self) -> None:
        """Source code should reference CWE-89 for traceability."""
        from pathlib import Path

        source_path = (
            Path(__file__).parent.parent.parent
            / "app"
            / "services"
            / "entity_search_service.py"
        )

        with open(source_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Should reference CWE-89 (SQL Injection)
        assert "CWE-89" in content or "SQL Injection" in content or "sql injection" in content.lower()

    def test_whitelist_validation_documented(self) -> None:
        """Whitelist validation should be documented in code."""
        from pathlib import Path

        source_path = (
            Path(__file__).parent.parent.parent
            / "app"
            / "services"
            / "entity_search_service.py"
        )

        with open(source_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Should document the whitelist approach
        assert "whitelist" in content.lower() or "VALID_COMPANIES" in content
