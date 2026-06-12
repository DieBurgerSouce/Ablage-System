# -*- coding: utf-8 -*-
"""
Tests for JSONB Column/Key Whitelist Validation.

Tests the SQL injection prevention via whitelist validation in entity_search_service.py.
Covers CWE-89: Improper Neutralization of Special Elements used in an SQL Command.
"""

import pytest

from app.services.entity_search_service import (
    VALID_COMPANIES,
    VALID_LEXWARE_FIELDS,
    InvalidCompanyError,
    InvalidLexwareFieldError,
    _validate_company,
    _validate_lexware_field,
)


class TestValidCompaniesWhitelist:
    """Tests for VALID_COMPANIES whitelist."""

    def test_valid_companies_is_frozenset(self) -> None:
        """VALID_COMPANIES should be immutable."""
        assert isinstance(VALID_COMPANIES, frozenset)

    def test_valid_companies_contains_folie(self) -> None:
        """VALID_COMPANIES should contain 'folie'."""
        assert "folie" in VALID_COMPANIES

    def test_valid_companies_contains_messer(self) -> None:
        """VALID_COMPANIES should contain 'messer'."""
        assert "messer" in VALID_COMPANIES

    def test_valid_companies_limited_set(self) -> None:
        """VALID_COMPANIES should only contain known companies."""
        # Ensure no unexpected entries
        assert len(VALID_COMPANIES) == 2
        assert VALID_COMPANIES == frozenset({"folie", "messer"})


class TestValidLexwareFieldsWhitelist:
    """Tests for VALID_LEXWARE_FIELDS whitelist."""

    def test_valid_lexware_fields_is_frozenset(self) -> None:
        """VALID_LEXWARE_FIELDS should be immutable."""
        assert isinstance(VALID_LEXWARE_FIELDS, frozenset)

    def test_valid_lexware_fields_contains_expected(self) -> None:
        """VALID_LEXWARE_FIELDS should contain expected fields."""
        expected_fields = {"kd_nr", "lief_nr", "matchcode", "debitor_konto", "kreditor_konto"}
        for field in expected_fields:
            assert field in VALID_LEXWARE_FIELDS

    def test_valid_lexware_fields_no_dangerous_names(self) -> None:
        """VALID_LEXWARE_FIELDS should not contain dangerous names."""
        dangerous_names = {
            "password", "secret", "token", "api_key",
            "__", "...", "DROP", "DELETE", "INSERT",
        }
        for dangerous in dangerous_names:
            assert dangerous.lower() not in VALID_LEXWARE_FIELDS


class TestValidateCompany:
    """Tests for _validate_company() function."""

    def test_validate_company_folie_lowercase(self) -> None:
        """'folie' should be valid."""
        result = _validate_company("folie")
        assert result == "folie"

    def test_validate_company_messer_lowercase(self) -> None:
        """'messer' should be valid."""
        result = _validate_company("messer")
        assert result == "messer"

    def test_validate_company_case_insensitive(self) -> None:
        """Company validation should be case-insensitive."""
        assert _validate_company("FOLIE") == "folie"
        assert _validate_company("Folie") == "folie"
        assert _validate_company("MESSER") == "messer"
        assert _validate_company("Messer") == "messer"

    def test_validate_company_none(self) -> None:
        """None company should return None."""
        result = _validate_company(None)
        assert result is None

    def test_validate_company_empty_string(self) -> None:
        """Empty string is rejected (fail-closed, CWE-89).

        W3 (2026-06-12): Echter Vertrag — nur ``None`` bedeutet "kein
        Firmen-Filter"; ein Leerstring ist kein gueltiger JSONB-Key.
        """
        with pytest.raises(InvalidCompanyError):
            _validate_company("")

    def test_validate_company_invalid_raises(self) -> None:
        """Invalid company should raise InvalidCompanyError."""
        with pytest.raises(InvalidCompanyError) as exc_info:
            _validate_company("evil_company")
        assert "Ungültige Firma" in str(exc_info.value) or "ungueltig" in str(exc_info.value).lower()

    def test_validate_company_sql_injection_attempt(self) -> None:
        """SQL injection attempts should be rejected."""
        sql_injections = [
            "folie'; DROP TABLE business_entities; --",
            "messer OR 1=1",
            "folie UNION SELECT * FROM users",
            "' OR ''='",
            "1; DELETE FROM documents",
        ]
        for injection in sql_injections:
            with pytest.raises(InvalidCompanyError):
                _validate_company(injection)

    def test_validate_company_path_traversal(self) -> None:
        """Path traversal attempts should be rejected."""
        path_traversals = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32",
            "folie/../../../secret",
        ]
        for traversal in path_traversals:
            with pytest.raises(InvalidCompanyError):
                _validate_company(traversal)

    def test_validate_company_unicode_attacks(self) -> None:
        """Unicode-based attacks should be rejected."""
        unicode_attacks = [
            "folie\x00",  # Null byte
            "messer\u0000",  # Unicode null
            "folie\u202e",  # Right-to-left override
        ]
        for attack in unicode_attacks:
            with pytest.raises(InvalidCompanyError):
                _validate_company(attack)


class TestValidateLexwareField:
    """Tests for _validate_lexware_field() function."""

    def test_validate_field_kd_nr(self) -> None:
        """'kd_nr' should be valid."""
        result = _validate_lexware_field("kd_nr")
        assert result == "kd_nr"

    def test_validate_field_lief_nr(self) -> None:
        """'lief_nr' should be valid."""
        result = _validate_lexware_field("lief_nr")
        assert result == "lief_nr"

    def test_validate_field_matchcode(self) -> None:
        """'matchcode' should be valid."""
        result = _validate_lexware_field("matchcode")
        assert result == "matchcode"

    def test_validate_field_debitor_konto(self) -> None:
        """'debitor_konto' should be valid."""
        result = _validate_lexware_field("debitor_konto")
        assert result == "debitor_konto"

    def test_validate_field_kreditor_konto(self) -> None:
        """'kreditor_konto' should be valid."""
        result = _validate_lexware_field("kreditor_konto")
        assert result == "kreditor_konto"

    def test_validate_field_invalid_raises(self) -> None:
        """Invalid field should raise InvalidLexwareFieldError."""
        with pytest.raises(InvalidLexwareFieldError) as exc_info:
            _validate_lexware_field("evil_field")
        assert "Ungültiges" in str(exc_info.value) or "ungueltig" in str(exc_info.value).lower()

    def test_validate_field_sql_injection_attempt(self) -> None:
        """SQL injection in field names should be rejected."""
        sql_injections = [
            "kd_nr'; DROP TABLE business_entities; --",
            "lief_nr OR 1=1",
            "matchcode UNION SELECT * FROM users",
            "' OR ''='",
            "1; DELETE FROM documents",
        ]
        for injection in sql_injections:
            with pytest.raises(InvalidLexwareFieldError):
                _validate_lexware_field(injection)

    def test_validate_field_jsonb_injection(self) -> None:
        """JSONB-specific injection attempts should be rejected."""
        jsonb_injections = [
            "kd_nr->>'password'",
            "kd_nr #>> '{}'",
            "matchcode @> '{}'",
            "lief_nr ?| array['a']",
        ]
        for injection in jsonb_injections:
            with pytest.raises(InvalidLexwareFieldError):
                _validate_lexware_field(injection)

    def test_validate_field_empty_string_raises(self) -> None:
        """Empty field name should raise."""
        with pytest.raises(InvalidLexwareFieldError):
            _validate_lexware_field("")

    def test_validate_field_whitespace_raises(self) -> None:
        """Whitespace-only field should raise."""
        with pytest.raises(InvalidLexwareFieldError):
            _validate_lexware_field("   ")


class TestSecurityScenarios:
    """Security-focused test scenarios."""

    def test_combination_attack_company_and_field(self) -> None:
        """Combined attacks on company and field should fail."""
        # Both should fail independently
        with pytest.raises(InvalidCompanyError):
            _validate_company("folie'; --")

        with pytest.raises(InvalidLexwareFieldError):
            _validate_lexware_field("kd_nr'; --")

    def test_case_sensitivity_not_exploitable(self) -> None:
        """Case differences should not bypass validation.

        W3 (2026-06-12): Beide Validatoren NORMALISIEREN auf lowercase und
        pruefen erst danach gegen die Whitelist. Grossschreibung ist damit
        kein Bypass: zurueckgegeben (und downstream verwendet) wird immer
        der normalisierte, gewhitelistete Wert.
        """
        result_field = _validate_lexware_field("KD_NR")
        assert result_field == "kd_nr"
        assert result_field in VALID_LEXWARE_FIELDS

        # Nicht-whitelisted Feld bleibt auch case-insensitiv verboten
        with pytest.raises(InvalidLexwareFieldError):
            _validate_lexware_field("EVIL_FIELD")

        # Company validation is case-insensitive (normalized)
        result = _validate_company("FOLIE")
        assert result == "folie"

    def test_whitelist_immutability(self) -> None:
        """Whitelists should not be modifiable."""
        # frozenset is immutable, so this should raise
        with pytest.raises(AttributeError):
            VALID_COMPANIES.add("evil")  # type: ignore

        with pytest.raises(AttributeError):
            VALID_LEXWARE_FIELDS.add("evil")  # type: ignore


class TestEdgeCases:
    """Edge case tests."""

    def test_very_long_company_name(self) -> None:
        """Very long company names should be rejected."""
        long_name = "a" * 10000
        with pytest.raises(InvalidCompanyError):
            _validate_company(long_name)

    def test_very_long_field_name(self) -> None:
        """Very long field names should be rejected."""
        long_field = "a" * 10000
        with pytest.raises(InvalidLexwareFieldError):
            _validate_lexware_field(long_field)

    def test_special_characters_in_company(self) -> None:
        """Special characters in company names should be rejected."""
        special_chars = ["folie!", "messer@", "test#", "test$", "test%"]
        for name in special_chars:
            with pytest.raises(InvalidCompanyError):
                _validate_company(name)

    def test_special_characters_in_field(self) -> None:
        """Special characters in field names should be rejected."""
        special_chars = ["kd_nr!", "lief_nr@", "test#", "test$", "test%"]
        for field in special_chars:
            with pytest.raises(InvalidLexwareFieldError):
                _validate_lexware_field(field)

    def test_newlines_in_company(self) -> None:
        """Newlines in company names should be rejected."""
        with pytest.raises(InvalidCompanyError):
            _validate_company("folie\nmesser")

    def test_newlines_in_field(self) -> None:
        """Newlines in field names should be rejected."""
        with pytest.raises(InvalidLexwareFieldError):
            _validate_lexware_field("kd_nr\nlief_nr")


class TestErrorMessages:
    """Tests for German error messages."""

    def test_invalid_company_german_message(self) -> None:
        """InvalidCompanyError should have German message."""
        with pytest.raises(InvalidCompanyError) as exc_info:
            _validate_company("evil")
        error_message = str(exc_info.value)
        # Should contain German text
        assert "Firma" in error_message or "firma" in error_message.lower()

    def test_invalid_field_german_message(self) -> None:
        """InvalidLexwareFieldError should have German message."""
        with pytest.raises(InvalidLexwareFieldError) as exc_info:
            _validate_lexware_field("evil")
        error_message = str(exc_info.value)
        # Should contain German text
        assert "Feld" in error_message or "feld" in error_message.lower()
