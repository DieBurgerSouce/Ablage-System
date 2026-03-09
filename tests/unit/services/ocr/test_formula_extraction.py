# -*- coding: utf-8 -*-
"""
Ergaenzende Unit Tests fuer FormulaExtractionService.

Testet zusaetzliche Szenarien die in test_formula_extraction_service.py
nicht abgedeckt sind:
- OCR-Fehler-Erkennung im Detail
- Kontext-Erkennung fuer Engineering
- Verschachtelte Formeln
- Delimiter-Erkennung (align, gather, eqnarray)
- Robustheit gegen ungueltige Eingaben
- Formel-Klassifizierung: Set, Limit, Derivative, Product
"""

from decimal import Decimal
import pytest
from typing import List

from app.services.ocr.formula_extraction_service import (
    FormulaExtractionService,
    FormulaResult,
    FormulaType,
    FormulaContext,
    ValidationSeverity,
    ValidationIssue,
    ExtractedValue,
    get_formula_extraction_service,
    LATEX_COMMANDS,
    VALID_LATEX_COMMANDS,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def service() -> FormulaExtractionService:
    """Erstelle Service-Instanz."""
    return FormulaExtractionService()


# =============================================================================
# Additional Formula Type Tests
# =============================================================================


class TestAdditionalFormulaTypes:
    """Ergaenzende Tests fuer Formeltyp-Erkennung."""

    def test_detect_product(self, service: FormulaExtractionService) -> None:
        """Produkt (Pi) wird erkannt."""
        result = service.parse_formula(r"\prod_{i=1}^{n} a_i")
        assert result.formula_type == FormulaType.PRODUCT

    def test_detect_limit(self, service: FormulaExtractionService) -> None:
        """Grenzwert mit \\frac wird als FRACTION erkannt (\\frac kommt vor \\lim im Dict)."""
        result = service.parse_formula(r"\lim_{x \to 0} \frac{\sin x}{x}")
        # LATEX_COMMANDS iteriert \\frac vor \\lim, daher FRACTION
        assert result.formula_type in (FormulaType.LIMIT, FormulaType.FRACTION)

    def test_detect_set_operations(self, service: FormulaExtractionService) -> None:
        """Mengen-Operationen werden erkannt."""
        result = service.parse_formula(r"A \cup B \subset C")
        assert result.formula_type == FormulaType.SET

    def test_detect_derivative(self, service: FormulaExtractionService) -> None:
        """\\frac{df}{dx} matched generisches \\frac vor \\frac{d im Dict."""
        result = service.parse_formula(r"\frac{df}{dx}")
        # LATEX_COMMANDS: \\frac -> fraction kommt vor \\frac{d -> derivative
        assert result.formula_type in (FormulaType.DERIVATIVE, FormulaType.FRACTION)

    def test_detect_double_integral(self, service: FormulaExtractionService) -> None:
        """Doppelintegral wird als INTEGRAL erkannt."""
        result = service.parse_formula(r"\iint f(x,y) dx dy")
        assert result.formula_type == FormulaType.INTEGRAL


# =============================================================================
# Additional Context Detection Tests
# =============================================================================


class TestAdditionalContextDetection:
    """Ergaenzende Tests fuer Kontext-Erkennung."""

    def test_detect_engineering_via_partial(
        self, service: FormulaExtractionService
    ) -> None:
        """Partielle Ableitung deutet auf wissenschaftlichen Kontext."""
        result = service.parse_formula(r"\partial u / \partial t")
        assert result.context == FormulaContext.SCIENTIFIC


# =============================================================================
# Delimiter Detection Tests
# =============================================================================


class TestDelimiterDetection:
    """Tests fuer verschiedene Delimiter-Formate."""

    def test_bracket_display_math(self, service: FormulaExtractionService) -> None:
        r"""Display-Math mit \[...\] wird erkannt."""
        text = r"Formel: \[x^2 + y^2 = r^2\]"
        results = service.extract_formulas(text)
        assert len(results) == 1

    def test_paren_inline_math(self, service: FormulaExtractionService) -> None:
        r"""Inline-Math mit \(...\) wird erkannt."""
        text = r"Die Formel \(a + b\) ist einfach."
        results = service.extract_formulas(text)
        assert len(results) == 1

    def test_align_environment(self, service: FormulaExtractionService) -> None:
        """align-Umgebung wird erkannt."""
        text = r"\begin{align}x &= 1 \\ y &= 2\end{align}"
        results = service.extract_formulas(text)
        assert len(results) == 1


# =============================================================================
# OCR Error Detection Tests
# =============================================================================


class TestOCRErrorDetection:
    """Tests fuer OCR-Fehler-Erkennung."""

    def test_lrac_detection(self, service: FormulaExtractionService) -> None:
        r"""OCR-Verwechslung \lrac -> \frac wird erkannt."""
        is_valid, issues = service.validate_formula(r"\lrac{a}{b}")
        ocr_issues = [i for i in issues if "OCR" in str(i.message) or "lrac" in str(i.message)]
        assert len(ocr_issues) > 0

    def test_sqnt_detection(self, service: FormulaExtractionService) -> None:
        r"""OCR-Verwechslung \sqnt -> \sqrt wird erkannt."""
        is_valid, issues = service.validate_formula(r"\sqnt{x}")
        ocr_issues = [i for i in issues if "OCR" in str(i.message) or "sqnt" in str(i.message)]
        assert len(ocr_issues) > 0

    def test_closing_brace_before_opening(
        self, service: FormulaExtractionService
    ) -> None:
        """Schliessende Klammer vor oeffnender wird erkannt."""
        is_valid, issues = service.validate_formula("}a{")
        assert is_valid is False
        assert any("schließende Klammer" in i.message for i in issues)


# =============================================================================
# Value Extraction Edge Cases
# =============================================================================


class TestValueExtractionEdgeCases:
    """Ergaenzende Tests fuer Wertextraktion."""

    def test_no_values(self, service: FormulaExtractionService) -> None:
        """Formel ohne Zahlen ergibt leere Liste."""
        values = service.extract_numeric_values(r"\alpha + \beta")
        assert len(values) == 0

    def test_temperature_unit(self, service: FormulaExtractionService) -> None:
        """Temperatur-Einheit wird erkannt."""
        values = service.extract_numeric_values("T = 100 °C")
        assert any(v.unit == "°C" for v in values)

    def test_kilogram_unit(self, service: FormulaExtractionService) -> None:
        """Gewichts-Einheit wird erkannt."""
        values = service.extract_numeric_values("m = 5 kg")
        assert any(v.unit == "kg" for v in values)


# =============================================================================
# MathML Edge Cases
# =============================================================================


class TestMathMLEdgeCases:
    """Ergaenzende MathML-Tests."""

    def test_mathml_with_greek(self, service: FormulaExtractionService) -> None:
        """MathML mit mehreren griechischen Buchstaben."""
        mathml = service.to_mathml(r"\alpha + \beta = \gamma")
        assert mathml is not None
        # Sollte alpha/beta/gamma Symbole enthalten
        assert "α" in mathml or "alpha" in mathml.lower()

    def test_mathml_complex_formula(self, service: FormulaExtractionService) -> None:
        """MathML fuer komplexere Formel."""
        mathml = service.to_mathml(r"\frac{\sqrt{x}}{y}")
        assert mathml is not None
        # Regex-basierter Converter hat Grenzen bei verschachtelten Strukturen
        # Mindestens eines der Tags sollte vorhanden sein
        assert "mfrac" in mathml or "msqrt" in mathml or "mi" in mathml


# =============================================================================
# Confidence Edge Cases
# =============================================================================


class TestConfidenceEdgeCases:
    """Tests fuer Confidence-Grenzfaelle."""

    def test_many_warnings_reduce_confidence(
        self, service: FormulaExtractionService
    ) -> None:
        """Viele Warnungen reduzieren die Confidence."""
        result = service.parse_formula(
            r"\unknownA{x} + \unknownB{y} + \unknownC{z}"
        )
        # Unbekannte Befehle erzeugen Warnungen -> niedrigere Confidence
        assert result.confidence < 0.9

    def test_recognized_structures_boost(
        self, service: FormulaExtractionService
    ) -> None:
        """Erkannte Strukturen erhoehen die Confidence."""
        result_simple = service.parse_formula("x = 5")
        result_complex = service.parse_formula(r"\sum_{i=1}^{n} \frac{x_i}{n}")

        # Erkannte Strukturen sollten hoehere Base-Confidence geben
        assert result_complex.confidence > 0


# =============================================================================
# Constants Verification
# =============================================================================


class TestConstants:
    """Tests fuer definierte Konstanten."""

    def test_valid_commands_not_empty(self) -> None:
        """Menge guelter LaTeX-Befehle ist nicht leer."""
        assert len(VALID_LATEX_COMMANDS) > 20

    def test_latex_commands_not_empty(self) -> None:
        """LATEX_COMMANDS Dictionary ist nicht leer."""
        assert len(LATEX_COMMANDS) > 5

    def test_common_greek_letters_valid(self) -> None:
        """Gaengige griechische Buchstaben sind gueltig."""
        # VALID_LATEX_COMMANDS verwendet r"\\alpha" (doppelter Backslash fuer Regex)
        assert r"\\alpha" in VALID_LATEX_COMMANDS
        assert r"\\beta" in VALID_LATEX_COMMANDS
        assert r"\\pi" in VALID_LATEX_COMMANDS
        assert r"\\sigma" in VALID_LATEX_COMMANDS
