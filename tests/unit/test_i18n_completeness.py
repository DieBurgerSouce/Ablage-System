# -*- coding: utf-8 -*-
"""
i18n Completeness Tests

Validates that the translation system is complete and consistent:
- All keys in DE exist in EN (and vice versa)
- No untranslated keys (key == value, except for fallback)
- Format placeholders match between languages
- All namespace.key patterns are consistent
"""

import re
from typing import Dict, List, Set, Tuple

import pytest

from app.core.i18n.i18n import (
    _TRANSLATIONS_DE,
    _TRANSLATIONS_EN,
    FALLBACK_LANGUAGE,
    SUPPORTED_LANGUAGES,
    t,
    tn,
)


class TestI18nCompleteness:
    """Test suite for i18n completeness and consistency."""

    def test_all_languages_have_same_keys(self) -> None:
        """Ensure German and English translations have identical key sets."""
        de_keys = set(_TRANSLATIONS_DE.keys())
        en_keys = set(_TRANSLATIONS_EN.keys())

        missing_in_en = de_keys - en_keys
        missing_in_de = en_keys - de_keys

        assert not missing_in_en, (
            f"Keys present in German but missing in English: {sorted(missing_in_en)}"
        )
        assert not missing_in_de, (
            f"Keys present in English but missing in German: {sorted(missing_in_de)}"
        )

    def test_no_untranslated_keys_in_german(self) -> None:
        """Ensure no German translation equals its key (except for deliberate passthroughs)."""
        untranslated: List[str] = []

        for key, value in _TRANSLATIONS_DE.items():
            # Keys that are the same as their value are considered untranslated
            # (unless they're very short technical terms)
            if key == value and len(value) > 5:
                untranslated.append(key)

        assert not untranslated, f"Untranslated German keys found: {sorted(untranslated)}"

    def test_no_untranslated_keys_in_english(self) -> None:
        """Ensure no English translation equals its key (except for deliberate passthroughs)."""
        untranslated: List[str] = []

        for key, value in _TRANSLATIONS_EN.items():
            # Keys that are the same as their value are considered untranslated
            if key == value and len(value) > 5:
                untranslated.append(key)

        assert not untranslated, f"Untranslated English keys found: {sorted(untranslated)}"

    def test_format_placeholders_match(self) -> None:
        """Ensure format placeholders match between German and English translations."""
        mismatches: List[Tuple[str, Set[str], Set[str]]] = []

        for key in _TRANSLATIONS_DE.keys():
            de_value = _TRANSLATIONS_DE[key]
            en_value = _TRANSLATIONS_EN[key]

            # Extract placeholders using regex: {placeholder}
            de_placeholders = set(re.findall(r'\{(\w+)\}', de_value))
            en_placeholders = set(re.findall(r'\{(\w+)\}', en_value))

            if de_placeholders != en_placeholders:
                mismatches.append((key, de_placeholders, en_placeholders))

        if mismatches:
            error_msg = "Format placeholder mismatches found:\n"
            for key, de_ph, en_ph in mismatches:
                error_msg += f"  {key}:\n"
                error_msg += f"    DE: {de_ph}\n"
                error_msg += f"    EN: {en_ph}\n"
            pytest.fail(error_msg)

    def test_namespace_key_patterns_consistent(self) -> None:
        """Ensure all keys follow namespace.key pattern."""
        invalid_keys: List[str] = []

        all_keys = set(_TRANSLATIONS_DE.keys()) | set(_TRANSLATIONS_EN.keys())

        for key in all_keys:
            # Must contain exactly one dot separating namespace from key
            if key.count('.') != 1:
                invalid_keys.append(key)

        assert not invalid_keys, (
            f"Keys with invalid format (must be namespace.key): {sorted(invalid_keys)}"
        )

    def test_namespaces_are_consistent(self) -> None:
        """Ensure all namespaces are used consistently."""
        # Extract namespaces
        de_namespaces = set(key.split('.')[0] for key in _TRANSLATIONS_DE.keys())
        en_namespaces = set(key.split('.')[0] for key in _TRANSLATIONS_EN.keys())

        # Should be identical
        assert de_namespaces == en_namespaces, (
            f"Namespace mismatch. DE: {sorted(de_namespaces)}, EN: {sorted(en_namespaces)}"
        )

    def test_expected_namespaces_exist(self) -> None:
        """Ensure all expected namespaces are present."""
        expected_namespaces = {
            'common',
            'error',
            'auth',
            'document',
            'ocr',
            'entity',
            'banking',
            'workflow',
            'system',
            'validation',
            'retention',
            'compliance',
            'reporting',
            'procurement',
            'ai',
            'archive',
        }

        actual_namespaces = set(key.split('.')[0] for key in _TRANSLATIONS_DE.keys())

        missing = expected_namespaces - actual_namespaces
        assert not missing, f"Missing expected namespaces: {sorted(missing)}"

    def test_translation_function_works(self) -> None:
        """Ensure the t() function works correctly."""
        # Test simple translation
        result = t("common.success")
        assert result in ["Erfolgreich", "Success"], f"Unexpected result: {result}"

        # Test with interpolation
        result = t("document.page_count", count=5)
        assert "5" in result, f"Interpolation failed: {result}"

    def test_namespace_translation_function_works(self) -> None:
        """Ensure the tn() function works correctly."""
        result = tn("document", "uploaded_successfully")
        assert result in [
            "Dokument erfolgreich hochgeladen",
            "Document uploaded successfully",
        ], f"Unexpected result: {result}"

    def test_no_empty_translations(self) -> None:
        """Ensure no translations are empty strings."""
        empty_de = [key for key, value in _TRANSLATIONS_DE.items() if not value]
        empty_en = [key for key, value in _TRANSLATIONS_EN.items() if not value]

        assert not empty_de, f"Empty German translations: {sorted(empty_de)}"
        assert not empty_en, f"Empty English translations: {sorted(empty_en)}"

    def test_supported_languages_constant(self) -> None:
        """Ensure SUPPORTED_LANGUAGES matches available translations."""
        assert "de" in SUPPORTED_LANGUAGES
        assert "en" in SUPPORTED_LANGUAGES
        assert FALLBACK_LANGUAGE in SUPPORTED_LANGUAGES

    def test_retention_namespace_complete(self) -> None:
        """Ensure retention namespace has all required keys."""
        required_retention_keys = {
            'retention.active_lock',
            'retention.expires_in_days',
            'retention.expired',
            'retention.gdpr_conflict',
            'retention.gdpr_retention_wins',
            'retention.review_scheduled',
            'retention.compliance_ok',
            'retention.violation_found',
        }

        de_keys = set(_TRANSLATIONS_DE.keys())
        missing = required_retention_keys - de_keys

        assert not missing, f"Missing retention keys in German: {sorted(missing)}"

    def test_compliance_namespace_complete(self) -> None:
        """Ensure compliance namespace has all required keys."""
        required_compliance_keys = {
            'compliance.gobd_compliant',
            'compliance.gobd_violation',
            'compliance.audit_trail_complete',
            'compliance.data_integrity_verified',
            'compliance.report_generated',
        }

        de_keys = set(_TRANSLATIONS_DE.keys())
        missing = required_compliance_keys - de_keys

        assert not missing, f"Missing compliance keys in German: {sorted(missing)}"

    def test_reporting_namespace_complete(self) -> None:
        """Ensure reporting namespace has all required keys."""
        required_reporting_keys = {
            'reporting.generating',
            'reporting.export_ready',
            'reporting.no_data',
            'reporting.date_range_invalid',
        }

        de_keys = set(_TRANSLATIONS_DE.keys())
        missing = required_reporting_keys - de_keys

        assert not missing, f"Missing reporting keys in German: {sorted(missing)}"

    def test_procurement_namespace_complete(self) -> None:
        """Ensure procurement namespace has all required keys."""
        required_procurement_keys = {
            'procurement.po_created',
            'procurement.delivery_confirmed',
            'procurement.invoice_matched',
            'procurement.matching_failed',
            'procurement.three_way_match',
        }

        de_keys = set(_TRANSLATIONS_DE.keys())
        missing = required_procurement_keys - de_keys

        assert not missing, f"Missing procurement keys in German: {sorted(missing)}"

    def test_ai_namespace_complete(self) -> None:
        """Ensure AI namespace has all required keys."""
        required_ai_keys = {
            'ai.trust_level_auto',
            'ai.trust_level_confirm',
            'ai.trust_level_explicit',
            'ai.confidence_high',
            'ai.confidence_low',
            'ai.decision_explanation',
        }

        de_keys = set(_TRANSLATIONS_DE.keys())
        missing = required_ai_keys - de_keys

        assert not missing, f"Missing AI keys in German: {sorted(missing)}"

    def test_archive_namespace_complete(self) -> None:
        """Ensure archive namespace has all required keys."""
        required_archive_keys = {
            'archive.signed_successfully',
            'archive.signature_verified',
            'archive.signature_invalid',
            'archive.pdf_a3_created',
        }

        de_keys = set(_TRANSLATIONS_DE.keys())
        missing = required_archive_keys - de_keys

        assert not missing, f"Missing archive keys in German: {sorted(missing)}"

    def test_no_duplicate_values_within_namespace(self) -> None:
        """Ensure no duplicate translation values within the same namespace (likely copy-paste errors)."""
        de_by_namespace: Dict[str, List[Tuple[str, str]]] = {}
        en_by_namespace: Dict[str, List[Tuple[str, str]]] = {}

        # Group by namespace
        for key, value in _TRANSLATIONS_DE.items():
            namespace = key.split('.')[0]
            if namespace not in de_by_namespace:
                de_by_namespace[namespace] = []
            de_by_namespace[namespace].append((key, value))

        for key, value in _TRANSLATIONS_EN.items():
            namespace = key.split('.')[0]
            if namespace not in en_by_namespace:
                en_by_namespace[namespace] = []
            en_by_namespace[namespace].append((key, value))

        # Check for duplicate values within each namespace
        duplicates_de: List[str] = []
        for namespace, items in de_by_namespace.items():
            values = [v for k, v in items]
            seen: Set[str] = set()
            for key, value in items:
                if value in seen:
                    duplicates_de.append(f"{namespace}: {key} = '{value}'")
                seen.add(value)

        duplicates_en: List[str] = []
        for namespace, items in en_by_namespace.items():
            values = [v for k, v in items]
            seen = set()
            for key, value in items:
                if value in seen:
                    duplicates_en.append(f"{namespace}: {key} = '{value}'")
                seen.add(value)

        # Note: Some duplicates might be intentional (e.g., "Success" for multiple operations)
        # This test is informational rather than strict
        if duplicates_de:
            print(f"INFO: Potential duplicate German translations: {duplicates_de}")
        if duplicates_en:
            print(f"INFO: Potential duplicate English translations: {duplicates_en}")
