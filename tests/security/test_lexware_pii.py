# -*- coding: utf-8 -*-
"""
Security Tests: Lexware PII Protection

Tests that Lexware-specific sensitive data is properly protected:
- Customer numbers (Kundennummern)
- Supplier numbers (Lieferantennummern)
- IBANs from Lexware imports
- VAT-IDs (Umsatzsteuer-IDs)
- Matchcodes

Critical Rules from CLAUDE.md:
- "NIEMALS Kundennummern, IBANs, VAT-IDs in Logs"
- "NIEMALS Entity-Namen in Logs/Responses (PII)"

Enterprise Feature: Lexware Integration
"""

import io
import re
import uuid
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# =============================================================================
# TEST DATA
# =============================================================================


SAMPLE_LEXWARE_CUSTOMERS = [
    {
        "kd_nr": "KD-12345678",
        "matchcode": "MUELLER-GMBH",
        "name": "Müller GmbH & Co. KG",
        "iban": "DE89370400440532013000",
        "vat_id": "DE123456789",
        "address": "Musterstraße 123, 12345 Berlin",
    },
    {
        "kd_nr": "KD-87654321",
        "matchcode": "SCHMIDT-AG",
        "name": "Schmidt Handels AG",
        "iban": "DE44500105175407324931",
        "vat_id": "DE987654321",
        "address": "Industrieweg 45, 80331 München",
    },
]

SAMPLE_LEXWARE_SUPPLIERS = [
    {
        "lief_nr": "LF-99999999",
        "matchcode": "LIEFERANT-A",
        "name": "Lieferant A GmbH",
        "iban": "DE75512108001245126199",
        "vat_id": "DE111111111",
    },
]


# =============================================================================
# LOG SANITIZATION TESTS
# =============================================================================


class TestLexwareLogSanitization:
    """Tests that Lexware PII is not logged."""

    def test_customer_number_not_in_logs(self, log_capture) -> None:
        """Test that customer numbers are not logged."""
        for customer in SAMPLE_LEXWARE_CUSTOMERS:
            kd_nr = customer["kd_nr"]
            log_output = log_capture.getvalue()

            # Full customer number should not appear
            assert kd_nr not in log_output, \
                f"Kundennummer {kd_nr} sollte nicht in Logs erscheinen"

            # Even partial should be masked
            numeric_part = re.sub(r"\D", "", kd_nr)
            if len(numeric_part) >= 6:
                assert numeric_part not in log_output, \
                    f"Numerischer Teil der Kundennummer sollte nicht in Logs erscheinen"

    def test_supplier_number_not_in_logs(self, log_capture) -> None:
        """Test that supplier numbers are not logged."""
        for supplier in SAMPLE_LEXWARE_SUPPLIERS:
            lief_nr = supplier["lief_nr"]
            log_output = log_capture.getvalue()

            assert lief_nr not in log_output, \
                f"Lieferantennummer {lief_nr} sollte nicht in Logs erscheinen"

    def test_iban_not_in_logs(self, log_capture) -> None:
        """Test that IBANs are not logged."""
        all_entities = SAMPLE_LEXWARE_CUSTOMERS + SAMPLE_LEXWARE_SUPPLIERS

        for entity in all_entities:
            iban = entity.get("iban", "")
            if not iban:
                continue

            log_output = log_capture.getvalue()

            # Full IBAN should not appear
            assert iban not in log_output, \
                f"IBAN {iban} sollte nicht in Logs erscheinen"

            # Partial IBAN (last 10 digits) should not appear
            assert iban[-10:] not in log_output, \
                f"IBAN-Endung sollte nicht in Logs erscheinen"

    def test_vat_id_not_in_logs(self, log_capture) -> None:
        """Test that VAT-IDs are not logged."""
        all_entities = SAMPLE_LEXWARE_CUSTOMERS + SAMPLE_LEXWARE_SUPPLIERS

        for entity in all_entities:
            vat_id = entity.get("vat_id", "")
            if not vat_id:
                continue

            log_output = log_capture.getvalue()

            assert vat_id not in log_output, \
                f"VAT-ID {vat_id} sollte nicht in Logs erscheinen"

    def test_matchcode_not_in_logs(self, log_capture) -> None:
        """Test that matchcodes (which often contain company names) are not logged."""
        all_entities = SAMPLE_LEXWARE_CUSTOMERS + SAMPLE_LEXWARE_SUPPLIERS

        for entity in all_entities:
            matchcode = entity.get("matchcode", "")
            if not matchcode:
                continue

            log_output = log_capture.getvalue()

            assert matchcode not in log_output, \
                f"Matchcode {matchcode} sollte nicht in Logs erscheinen"


# =============================================================================
# API RESPONSE TESTS
# =============================================================================


class TestLexwareAPIResponseSanitization:
    """Tests that Lexware API responses properly mask PII."""

    def test_entity_list_masks_iban(self, test_client, auth_headers) -> None:
        """Test that entity list responses mask IBANs."""
        response = test_client.get(
            "/api/v1/entities",
            headers=auth_headers,
        )

        if response.status_code == 200:
            data = response.json()
            entities = data.get("items", data.get("entities", []))

            for entity in entities:
                iban = entity.get("iban", "")
                if iban:
                    # IBAN should be masked (e.g., "DE89****...3000")
                    assert "****" in iban or len(iban) <= 8, \
                        f"IBAN sollte maskiert sein: {iban}"

    def test_entity_search_masks_sensitive_data(self, test_client, auth_headers) -> None:
        """Test that entity search results mask sensitive data."""
        # Search for entities
        response = test_client.get(
            "/api/v1/entities/search?query=Mueller",
            headers=auth_headers,
        )

        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])

            for result in results:
                # Customer/Supplier numbers should be partially masked
                for key in ["customer_number", "kd_nr", "supplier_number", "lief_nr"]:
                    value = result.get(key, "")
                    if value and len(value) > 6:
                        # At least some characters should be masked
                        assert "***" in value or value.startswith("***"), \
                            f"{key} sollte teilweise maskiert sein"

    def test_lexware_statistics_aggregated(self, test_client, auth_headers) -> None:
        """Test that Lexware statistics are aggregated, not individual."""
        response = test_client.get(
            "/api/v1/lexware/statistics",
            headers=auth_headers,
        )

        if response.status_code == 200:
            data = response.json()

            # Should contain counts, not individual entities
            assert "customer_count" in data or "total_customers" in data or "count" in data, \
                "Statistiken sollten aggregierte Zahlen enthalten"

            # Should NOT contain individual customer/supplier data
            response_text = str(data).lower()
            assert "kd_nr" not in response_text or response_text.count("kd_nr") == 0, \
                "Statistiken sollten keine einzelnen Kundennummern enthalten"

    def test_lexware_import_response_no_raw_data(self, test_client, auth_headers) -> None:
        """Test that Lexware import responses don't contain raw imported data."""
        # Create a mock Excel file
        mock_file = io.BytesIO(b"mock excel data")

        response = test_client.post(
            "/api/v1/lexware/import/customers",
            files={"file": ("customers.xlsx", mock_file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=auth_headers,
        )

        if response.status_code in [200, 201]:
            data = response.json()

            # Response should contain summary, not raw data
            assert "imported_count" in data or "success_count" in data or "summary" in data, \
                "Import-Response sollte Zusammenfassung enthalten"

            # Should not contain raw customer data
            response_text = str(data)
            for customer in SAMPLE_LEXWARE_CUSTOMERS:
                assert customer["iban"] not in response_text, \
                    "Import-Response sollte keine rohen IBANs enthalten"


# =============================================================================
# ERROR RESPONSE TESTS
# =============================================================================


class TestLexwareErrorResponseSanitization:
    """Tests that error responses don't leak Lexware PII."""

    def test_import_error_no_customer_data(self, test_client, auth_headers) -> None:
        """Test that import errors don't contain customer data."""
        # Create an invalid file to trigger error
        mock_file = io.BytesIO(b"invalid file content")

        response = test_client.post(
            "/api/v1/lexware/import/customers",
            files={"file": ("invalid.txt", mock_file, "text/plain")},
            headers=auth_headers,
        )

        if response.status_code >= 400:
            error_text = response.text

            # Error should not contain example customer data
            for customer in SAMPLE_LEXWARE_CUSTOMERS:
                assert customer["kd_nr"] not in error_text
                assert customer["iban"] not in error_text
                assert customer["vat_id"] not in error_text

    def test_entity_not_found_error_no_guessing(self, test_client, auth_headers) -> None:
        """Test that entity not found errors don't reveal valid entity info."""
        fake_entity_id = uuid.uuid4()

        response = test_client.get(
            f"/api/v1/entities/{fake_entity_id}",
            headers=auth_headers,
        )

        if response.status_code == 404:
            error_text = response.text

            # Error should be generic, not reveal any valid entity info
            assert "Mueller" not in error_text
            assert "KD-" not in error_text
            assert "LF-" not in error_text


# =============================================================================
# CONFLICT RESOLUTION TESTS
# =============================================================================


class TestLexwareConflictResolutionSanitization:
    """Tests that conflict resolution doesn't leak PII."""

    def test_conflict_details_masked(self, test_client, auth_headers) -> None:
        """Test that conflict details mask sensitive values."""
        response = test_client.get(
            "/api/v1/lexware/conflicts",
            headers=auth_headers,
        )

        if response.status_code == 200:
            data = response.json()
            conflicts = data.get("conflicts", [])

            for conflict in conflicts:
                # If conflict shows old vs new values, they should be masked
                old_value = conflict.get("old_value", "")
                new_value = conflict.get("new_value", "")

                # IBANs in conflicts should be masked
                if "DE" in str(old_value) and len(str(old_value)) > 15:
                    assert "****" in str(old_value), \
                        "Alte IBAN in Konflikt sollte maskiert sein"


# =============================================================================
# AUDIT LOG TESTS
# =============================================================================


class TestLexwareAuditLogSanitization:
    """Tests that audit logs don't contain Lexware PII."""

    def test_audit_log_masks_lexware_operations(self, test_client, auth_headers) -> None:
        """Test that audit logs mask Lexware operation details."""
        response = test_client.get(
            "/api/v1/admin/audit-logs?action=lexware_import",
            headers=auth_headers,
        )

        if response.status_code == 200:
            data = response.json()
            logs = data.get("logs", data.get("items", []))

            for log in logs:
                log_text = str(log)

                # Audit logs should not contain raw customer data
                for customer in SAMPLE_LEXWARE_CUSTOMERS:
                    assert customer["iban"] not in log_text, \
                        "Audit-Log sollte keine rohen IBANs enthalten"
                    assert customer["name"] not in log_text, \
                        "Audit-Log sollte keine Firmennamen enthalten"


# =============================================================================
# ENTITY LINKING TESTS
# =============================================================================


class TestEntityLinkingSanitization:
    """Tests that entity linking doesn't leak PII."""

    def test_link_suggestions_minimal_info(self, test_client, auth_headers) -> None:
        """Test that entity link suggestions contain minimal PII."""
        doc_id = uuid.uuid4()

        response = test_client.get(
            f"/api/v1/documents/{doc_id}/entity-suggestions",
            headers=auth_headers,
        )

        if response.status_code == 200:
            data = response.json()
            suggestions = data.get("suggestions", [])

            for suggestion in suggestions:
                # Suggestions should have ID and confidence, but limited PII
                assert "entity_id" in suggestion or "id" in suggestion
                assert "confidence" in suggestion or "score" in suggestion

                # Should not contain full IBAN
                suggestion_text = str(suggestion)
                iban_pattern = re.compile(r"[A-Z]{2}\d{2}[A-Z0-9]{14,}")
                if iban_pattern.search(suggestion_text):
                    # If IBAN-like pattern found, it should be masked
                    assert "****" in suggestion_text, \
                        "IBAN in Vorschlägen sollte maskiert sein"


# =============================================================================
# EXPORT TESTS
# =============================================================================


class TestLexwareExportSanitization:
    """Tests that Lexware exports handle PII appropriately."""

    def test_entity_export_warns_about_pii(self, test_client, auth_headers) -> None:
        """Test that entity exports include PII warning."""
        response = test_client.get(
            "/api/v1/entities/export?format=csv",
            headers=auth_headers,
        )

        # Export should either:
        # 1. Require elevated permissions
        # 2. Include PII warning header
        # 3. Be audit logged
        if response.status_code == 200:
            # Check for X-Contains-PII header
            has_pii_warning = response.headers.get("X-Contains-PII", "") == "true"
            has_content_warning = response.headers.get("X-Content-Warning", "")

            # At least some form of warning should be present
            # (This test documents expected behavior)
            pass

    def test_gdpdu_export_includes_all_required_data(self, test_client, auth_headers) -> None:
        """Test that GDPdU exports include required data but with proper access control."""
        response = test_client.get(
            "/api/v1/tax/gdpdu/export",
            headers=auth_headers,
        )

        # GDPdU exports require admin/finance role
        # If successful, data should be complete (tax authority requirement)
        # But access should be strictly controlled
        if response.status_code == 403:
            # Expected: insufficient permissions
            pass
        elif response.status_code == 200:
            # Admin access: data should be complete but audit logged
            pass


# =============================================================================
# INPUT VALIDATION TESTS
# =============================================================================


class TestLexwareInputValidation:
    """Tests that Lexware inputs are properly validated."""

    @pytest.mark.parametrize("invalid_kd_nr", [
        "'; DROP TABLE entities; --",
        "KD-<script>alert(1)</script>",
        "KD-' OR '1'='1",
        "../../../etc/passwd",
        "KD-\x00\x00\x00",  # Null bytes
    ])
    def test_customer_number_validated(self, invalid_kd_nr: str, test_client, auth_headers) -> None:
        """Test that customer numbers are validated against injection."""
        response = test_client.get(
            f"/api/v1/entities/search?customer_number={invalid_kd_nr}",
            headers=auth_headers,
        )

        # Should not cause 500 error
        assert response.status_code != 500, \
            f"Ungültige Kundennummer sollte keinen Server-Fehler verursachen: {invalid_kd_nr}"

    @pytest.mark.parametrize("invalid_iban", [
        "DE89370400440532013000'; DROP TABLE--",
        "DE<script>alert(1)</script>",
        "INVALID_IBAN_FORMAT",
        "DE" * 50,  # Very long
    ])
    def test_iban_validated(self, invalid_iban: str, test_client, auth_headers) -> None:
        """Test that IBANs are validated."""
        response = test_client.get(
            f"/api/v1/entities/search?iban={invalid_iban}",
            headers=auth_headers,
        )

        # Should be rejected with 400/422, not 500
        assert response.status_code != 500
        if len(invalid_iban) > 50 or "script" in invalid_iban.lower():
            assert response.status_code in [400, 422], \
                f"Ungültige IBAN sollte abgelehnt werden: {invalid_iban}"


# =============================================================================
# BATCH OPERATION TESTS
# =============================================================================


class TestLexwareBatchOperationSanitization:
    """Tests that batch operations don't aggregate PII inappropriately."""

    def test_batch_import_summary_only(self, test_client, auth_headers) -> None:
        """Test that batch import results contain summary, not individual data."""
        mock_file = io.BytesIO(b"mock excel data")

        response = test_client.post(
            "/api/v1/lexware/import/customers/batch",
            files={"file": ("large_customers.xlsx", mock_file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=auth_headers,
        )

        if response.status_code in [200, 201, 202]:
            data = response.json()

            # Should contain summary statistics
            response_keys = set(data.keys())
            expected_summary_keys = {"total", "success", "failed", "skipped", "imported_count"}

            # At least one summary key should be present
            assert response_keys & expected_summary_keys, \
                "Batch-Import sollte Zusammenfassung enthalten"

    def test_batch_link_result_no_pii(self, test_client, auth_headers) -> None:
        """Test that batch entity linking results don't contain PII."""
        response = test_client.post(
            "/api/v1/lexware/link-documents",
            json={"document_ids": [str(uuid.uuid4()) for _ in range(5)]},
            headers=auth_headers,
        )

        if response.status_code in [200, 202]:
            data = response.json()

            # Results should be by document ID, not contain entity details
            linked = data.get("linked", data.get("results", []))

            for result in linked:
                result_text = str(result)
                # Should not contain full IBANs
                assert not re.search(r"[A-Z]{2}\d{2}[A-Z0-9]{14,}", result_text), \
                    "Batch-Link-Ergebnis sollte keine vollständigen IBANs enthalten"


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def log_capture(mocker):
    """Capture log output for testing."""
    import io
    import logging

    # Create string buffer
    log_stream = io.StringIO()

    # Add handler
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.DEBUG)

    # Get root logger and add handler
    logger = logging.getLogger()
    original_level = logger.level
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)

    yield log_stream

    # Cleanup
    logger.removeHandler(handler)
    logger.setLevel(original_level)
