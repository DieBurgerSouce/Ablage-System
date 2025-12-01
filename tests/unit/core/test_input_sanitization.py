# -*- coding: utf-8 -*-
"""
Unit Tests fuer Input Sanitization Module.

Testet:
- Search Query Sanitization (XSS, ReDoS, SQL-Injection)
- Filename Sanitization (Path Traversal)
- Tag Sanitization
- PII Filtering
- Safe Highlighting
"""

import pytest
from uuid import UUID

from app.core.input_sanitization import (
    sanitize_search_query,
    sanitize_filename,
    sanitize_tag,
    sanitize_html_content,
    check_sql_injection_patterns,
    validate_uuid,
    sanitize_pagination_params,
    create_safe_highlight,
    SanitizationError,
    SanitizationConfig,
)
from app.middleware.request_logging import (
    filter_pii_from_dict,
    filter_pii_from_text,
)


class TestSearchQuerySanitization:
    """Tests fuer sanitize_search_query()."""

    def test_basic_query_unchanged(self):
        """Einfache Queries bleiben unveraendert."""
        query = "Test123"  # Einfacher Query ohne ReDoS-Trigger
        result, warnings = sanitize_search_query(query)
        assert result == query

    def test_german_umlauts_preserved(self):
        """Deutsche Umlaute bleiben erhalten."""
        query = "Rechnungsübersicht für März"
        result, warnings = sanitize_search_query(query)
        assert "ü" in result
        assert "ä" not in warnings  # Keine Warnung fuer Umlaute

    def test_xss_script_tags_removed(self):
        """XSS Script-Tags werden entfernt."""
        query = '<script>alert("xss")</script>Test'
        result, warnings = sanitize_search_query(query)
        assert "<script>" not in result
        assert "</script>" not in result
        # HTML-Tags wurden entfernt
        assert any("HTML" in w for w in warnings)

    def test_javascript_injection_blocked(self):
        """JavaScript-Injection wird blockiert."""
        query = "javascript:alert(1)"
        result, warnings = sanitize_search_query(query)
        assert "javascript:" not in result.lower()

    def test_null_byte_removed(self):
        """Null-Bytes werden entfernt."""
        query = "Rechnung\x00Test"
        result, warnings = sanitize_search_query(query)
        assert "\x00" not in result
        assert any("Null" in w for w in warnings)

    def test_max_length_enforced(self):
        """Maximale Laenge wird eingehalten."""
        # Verwende verschiedene Zeichen um ReDoS-Schutz nicht auszuloesen
        query = "Test " * 200  # 1000 Zeichen
        result, warnings = sanitize_search_query(query, max_length=100)
        assert len(result) <= 100

    def test_wildcards_preserved_by_default(self):
        """Wildcards werden standardmaessig beibehalten."""
        query = "Rech*"
        result, warnings = sanitize_search_query(query, allow_wildcards=True)
        assert "*" in result

    def test_wildcards_removed_when_disabled(self):
        """Wildcards werden entfernt wenn deaktiviert."""
        query = "Rech*nung?"
        result, warnings = sanitize_search_query(query, allow_wildcards=False)
        assert "*" not in result
        assert "?" not in result

    def test_whitespace_normalized(self):
        """Whitespace wird normalisiert."""
        query = "  Rechnung   2024  "
        result, warnings = sanitize_search_query(query)
        assert result == "Rechnung 2024"

    def test_empty_query(self):
        """Leere Query gibt leeren String zurueck."""
        result, warnings = sanitize_search_query("")
        assert result == ""
        assert not warnings

    def test_control_characters_removed(self):
        """Steuerzeichen werden entfernt."""
        query = "Rechnung\x07\x08Test"
        result, warnings = sanitize_search_query(query)
        assert "\x07" not in result
        assert "\x08" not in result

    def test_event_handler_blocked(self):
        """Event-Handler-Attribute werden blockiert."""
        query = 'onclick="alert(1)" Rechnung'
        result, warnings = sanitize_search_query(query)
        assert "onclick" not in result.lower()


class TestFilenameSanitization:
    """Tests fuer sanitize_filename()."""

    def test_basic_filename_unchanged(self):
        """Einfache Dateinamen bleiben unveraendert."""
        filename = "rechnung_2024.pdf"
        result = sanitize_filename(filename)
        assert result == filename

    def test_path_traversal_blocked(self):
        """Path-Traversal wird blockiert."""
        filename = "../../../etc/passwd"
        result = sanitize_filename(filename)
        assert ".." not in result
        assert "/" not in result
        assert "\\" not in result

    def test_null_byte_removed(self):
        """Null-Bytes werden entfernt."""
        filename = "file\x00.pdf"
        result = sanitize_filename(filename)
        assert "\x00" not in result

    def test_windows_forbidden_chars_replaced(self):
        """Windows-verbotene Zeichen werden ersetzt."""
        filename = 'file<>:"|?*.pdf'
        result = sanitize_filename(filename)
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result

    def test_extension_preserved(self):
        """Dateiendung wird beibehalten."""
        filename = "rechnung.pdf"
        result = sanitize_filename(filename, preserve_extension=True)
        assert result.endswith(".pdf")

    def test_max_length_enforced(self):
        """Maximale Laenge wird eingehalten."""
        filename = "a" * 300 + ".pdf"
        result = sanitize_filename(filename, max_length=50)
        assert len(result) <= 50
        assert result.endswith(".pdf")

    def test_empty_filename_raises_error(self):
        """Leerer Dateiname wirft Exception."""
        with pytest.raises(SanitizationError) as exc_info:
            sanitize_filename("")
        assert "dateiname" in str(exc_info.value.user_message_de).lower()

    def test_german_umlauts_allowed(self):
        """Deutsche Umlaute sind erlaubt."""
        filename = "Übersicht_März.pdf"
        result = sanitize_filename(filename)
        assert "Ü" in result or "ü" in result.lower()


class TestTagSanitization:
    """Tests fuer sanitize_tag()."""

    def test_basic_tag_unchanged(self):
        """Einfache Tags bleiben unveraendert."""
        tag = "Rechnung-2024"
        result = sanitize_tag(tag)
        assert result == tag

    def test_whitespace_trimmed(self):
        """Whitespace wird getrimmt."""
        tag = "  Rechnung  "
        result = sanitize_tag(tag)
        assert result == "Rechnung"

    def test_special_chars_replaced(self):
        """Sonderzeichen werden ersetzt."""
        tag = "Rechnung@2024#test"
        result = sanitize_tag(tag)
        assert "@" not in result
        assert "#" not in result

    def test_max_length_enforced(self):
        """Maximale Laenge wird eingehalten."""
        tag = "a" * 100
        result = sanitize_tag(tag, max_length=20)
        assert len(result) <= 20

    def test_empty_tag_raises_error(self):
        """Leerer Tag wirft Exception."""
        with pytest.raises(SanitizationError):
            sanitize_tag("")

    def test_german_umlauts_allowed(self):
        """Deutsche Umlaute sind erlaubt."""
        tag = "Überweisung"
        result = sanitize_tag(tag)
        assert "Ü" in result


class TestSQLInjectionCheck:
    """Tests fuer check_sql_injection_patterns()."""

    def test_safe_query(self):
        """Sichere Queries werden akzeptiert."""
        is_safe, pattern = check_sql_injection_patterns("Rechnung 2024")
        assert is_safe
        assert pattern is None

    def test_union_select_detected(self):
        """UNION SELECT wird erkannt."""
        is_safe, pattern = check_sql_injection_patterns("1 UNION SELECT * FROM users")
        assert not is_safe
        assert "UNION" in pattern or "SELECT" in pattern

    def test_drop_table_detected(self):
        """DROP TABLE wird erkannt."""
        is_safe, pattern = check_sql_injection_patterns("1; DROP TABLE users")
        assert not is_safe

    def test_exec_injection_detected(self):
        """SQL-EXEC-Injection wird erkannt."""
        is_safe, pattern = check_sql_injection_patterns("EXEC sp_executesql")
        assert not is_safe

    def test_case_insensitive(self):
        """Erkennung ist case-insensitive."""
        is_safe, _ = check_sql_injection_patterns("1 union select * from users")
        assert not is_safe


class TestUUIDValidation:
    """Tests fuer validate_uuid()."""

    def test_valid_uuid(self):
        """Gueltige UUID wird akzeptiert."""
        uuid_str = "550e8400-e29b-41d4-a716-446655440000"
        result = validate_uuid(uuid_str)
        assert isinstance(result, UUID)
        assert str(result) == uuid_str

    def test_invalid_uuid_raises_error(self):
        """Ungueltige UUID wirft Exception."""
        with pytest.raises(SanitizationError) as exc_info:
            validate_uuid("not-a-uuid")
        assert "UUID" in str(exc_info.value.user_message_de)

    def test_empty_uuid_raises_error(self):
        """Leere UUID wirft Exception."""
        with pytest.raises(SanitizationError):
            validate_uuid("")


class TestPaginationSanitization:
    """Tests fuer sanitize_pagination_params()."""

    def test_valid_params_unchanged(self):
        """Gueltige Parameter bleiben unveraendert."""
        page, per_page = sanitize_pagination_params(5, 20)
        assert page == 5
        assert per_page == 20

    def test_negative_page_corrected(self):
        """Negative Seitenzahl wird korrigiert."""
        page, per_page = sanitize_pagination_params(-1, 20)
        assert page == 1

    def test_zero_page_corrected(self):
        """Seitenzahl 0 wird korrigiert."""
        page, per_page = sanitize_pagination_params(0, 20)
        assert page == 1

    def test_excessive_page_capped(self):
        """Zu hohe Seitenzahl wird begrenzt."""
        page, per_page = sanitize_pagination_params(99999, 20, max_page=100)
        assert page == 100

    def test_excessive_per_page_capped(self):
        """Zu hohe per_page wird begrenzt."""
        page, per_page = sanitize_pagination_params(1, 1000, max_per_page=100)
        assert per_page == 100


class TestSafeHighlight:
    """Tests fuer create_safe_highlight()."""

    def test_basic_highlight(self):
        """Einfaches Highlighting funktioniert."""
        result = create_safe_highlight("Die Rechnung wurde bezahlt", "Rechnung")
        assert "<mark>Rechnung</mark>" in result

    def test_case_insensitive(self):
        """Highlighting ist case-insensitive."""
        result = create_safe_highlight("Die RECHNUNG wurde bezahlt", "rechnung")
        assert "<mark>" in result

    def test_max_replacements_limit(self):
        """Maximale Ersetzungen werden begrenzt (DoS-Schutz)."""
        text = "a " * 100
        result = create_safe_highlight(text, "a")
        # Sollte nicht mehr als 50 Ersetzungen haben
        assert result.count("<mark>") <= 50

    def test_regex_special_chars_escaped(self):
        """Regex-Sonderzeichen werden escaped."""
        result = create_safe_highlight("Test (value) here", "(value)")
        assert "<mark>(value)</mark>" in result

    def test_empty_inputs(self):
        """Leere Inputs werden behandelt."""
        assert create_safe_highlight("", "test") == ""
        assert create_safe_highlight("test", "") == "test"


class TestPIIFiltering:
    """Tests fuer PII-Filterung."""

    def test_password_redacted(self):
        """Passwoerter werden komplett entfernt."""
        data = {"username": "test", "password": "secret123"}
        filtered = filter_pii_from_dict(data)
        assert filtered["password"] == "[REDACTED]"

    def test_email_masked(self):
        """Emails werden maskiert."""
        data = {"email": "test@example.com"}
        filtered = filter_pii_from_dict(data)
        assert "***" in filtered["email"]
        assert ".com" in filtered["email"]

    def test_name_truncated(self):
        """Namen werden gekuerzt."""
        data = {"firstname": "Johannes"}
        filtered = filter_pii_from_dict(data)
        assert filtered["firstname"].startswith("Joh")
        assert "***" in filtered["firstname"]

    def test_nested_dict_filtered(self):
        """Verschachtelte Dicts werden gefiltert."""
        data = {
            "user": {
                "password": "secret",
                "email": "test@example.com"
            }
        }
        filtered = filter_pii_from_dict(data)
        assert filtered["user"]["password"] == "[REDACTED]"

    def test_text_email_filtered(self):
        """Emails in Freitext werden gefiltert."""
        text = "Kontakt: test@example.com oder info@test.de"
        filtered = filter_pii_from_text(text)
        assert "test@example.com" not in filtered
        assert "[EMAIL-REDACTED]" in filtered

    def test_text_iban_filtered(self):
        """IBANs in Freitext werden gefiltert."""
        text = "IBAN: DE89370400440532013000"
        filtered = filter_pii_from_text(text)
        assert "DE89370400440532013000" not in filtered

    def test_jwt_filtered(self):
        """JWT-Tokens werden gefiltert."""
        text = "Token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        filtered = filter_pii_from_text(text)
        assert "eyJ" not in filtered
        assert "[JWT-REDACTED]" in filtered


class TestHTMLSanitization:
    """Tests fuer sanitize_html_content()."""

    def test_script_tags_removed(self):
        """Script-Tags werden komplett entfernt."""
        html = "<p>Test</p><script>alert('xss')</script>"
        result = sanitize_html_content(html)
        assert "<script>" not in result
        assert "alert" not in result

    def test_allowed_tags_preserved(self):
        """Erlaubte Tags bleiben erhalten."""
        html = "<p>Test <mark>highlighted</mark> text</p>"
        result = sanitize_html_content(html, allowed_tags=["mark"])
        assert "<mark>" in result

    def test_event_handlers_removed(self):
        """Event-Handler werden entfernt."""
        html = '<div onclick="alert(1)">Test</div>'
        result = sanitize_html_content(html)
        assert "onclick" not in result

    def test_style_tags_removed(self):
        """Style-Tags werden entfernt."""
        html = "<style>body{display:none}</style><p>Test</p>"
        result = sanitize_html_content(html)
        assert "<style>" not in result
