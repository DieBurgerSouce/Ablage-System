# -*- coding: utf-8 -*-
"""
Unit Tests fuer FormulaExtractionService.

Testet:
- LaTeX-Formelextraktion aus OCR-Text
- Syntax-Validierung
- Numerische Wertextraktion
- Formeltyp-Erkennung
- MathML-Konvertierung

Feature 19: LaTeX Formula Parsing
"""

from decimal import Decimal
import pytest

from app.services.ocr.formula_extraction_service import (
    FormulaExtractionService,
    FormulaResult,
    FormulaType,
    FormulaContext,
    ValidationSeverity,
    ValidationIssue,
    ExtractedValue,
    get_formula_extraction_service,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def service():
    """Erstelle Service-Instanz."""
    return FormulaExtractionService()


# =============================================================================
# Basic Tests
# =============================================================================


class TestFormulaExtractionService:
    """Grundlegende Tests fuer FormulaExtractionService."""

    def test_init(self, service):
        """Test Service-Initialisierung."""
        assert service._delimiter_patterns is not None
        assert service._number_pattern is not None
        assert service._variable_pattern is not None

    def test_singleton(self):
        """Test Singleton-Pattern."""
        import app.services.ocr.formula_extraction_service as module
        module._service = None

        service1 = get_formula_extraction_service()
        service2 = get_formula_extraction_service()

        assert service1 is service2


# =============================================================================
# Formula Extraction Tests
# =============================================================================


class TestExtractFormulas:
    """Tests fuer Formelextraktion."""

    def test_extract_inline_math(self, service):
        """Test: Inline-Formeln mit $...$ werden erkannt."""
        text = "Die Formel $a^2 + b^2 = c^2$ ist der Satz des Pythagoras."
        results = service.extract_formulas(text)

        assert len(results) == 1
        assert "a^2 + b^2 = c^2" in results[0].original

    def test_extract_display_math(self, service):
        """Test: Display-Formeln mit $$...$$ werden erkannt."""
        text = "Berechnung: $$E = mc^2$$"
        results = service.extract_formulas(text)

        assert len(results) == 1
        assert "E = mc^2" in results[0].original

    def test_extract_equation_environment(self, service):
        """Test: equation-Umgebung wird erkannt."""
        text = r"\begin{equation}x = \frac{-b \pm \sqrt{b^2-4ac}}{2a}\end{equation}"
        results = service.extract_formulas(text)

        assert len(results) == 1
        assert "\\frac" in results[0].original

    def test_extract_multiple_formulas(self, service):
        """Test: Mehrere Formeln werden alle extrahiert."""
        text = "Gleichung 1: $a + b = c$. Gleichung 2: $x = y$."
        results = service.extract_formulas(text)

        assert len(results) == 2

    def test_extract_no_formulas(self, service):
        """Test: Text ohne Formeln gibt leere Liste zurueck."""
        text = "Dies ist normaler Text ohne Mathematik."
        results = service.extract_formulas(text)

        assert len(results) == 0


# =============================================================================
# Formula Type Detection Tests
# =============================================================================


class TestFormulaTypeDetection:
    """Tests fuer Formeltyp-Erkennung."""

    def test_detect_equation(self, service):
        """Test: Gleichung wird erkannt."""
        result = service.parse_formula("x = 5")
        assert result.formula_type == FormulaType.EQUATION

    def test_detect_inequality(self, service):
        """Test: Ungleichung wird erkannt."""
        result = service.parse_formula("x > 5")
        assert result.formula_type == FormulaType.INEQUALITY

        result = service.parse_formula(r"x \leq 10")
        assert result.formula_type == FormulaType.INEQUALITY

    def test_detect_fraction(self, service):
        """Test: Bruch wird erkannt."""
        result = service.parse_formula(r"\frac{a}{b}")
        assert result.formula_type == FormulaType.FRACTION

    def test_detect_sum(self, service):
        """Test: Summe wird erkannt."""
        result = service.parse_formula(r"\sum_{i=1}^{n} x_i")
        assert result.formula_type == FormulaType.SUM

    def test_detect_integral(self, service):
        """Test: Integral wird erkannt."""
        result = service.parse_formula(r"\int_0^1 f(x) dx")
        assert result.formula_type == FormulaType.INTEGRAL

    def test_detect_matrix(self, service):
        """Test: Matrix wird erkannt."""
        result = service.parse_formula(r"\begin{matrix} a & b \\ c & d \end{matrix}")
        assert result.formula_type == FormulaType.MATRIX

    def test_detect_expression(self, service):
        """Test: Ausdruck ohne Operator wird als EXPRESSION klassifiziert."""
        result = service.parse_formula("a + b")
        assert result.formula_type == FormulaType.EXPRESSION


# =============================================================================
# Context Detection Tests
# =============================================================================


class TestContextDetection:
    """Tests fuer Kontext-Erkennung."""

    def test_detect_financial_context(self, service):
        """Test: Finanzieller Kontext wird erkannt."""
        result = service.parse_formula("100 € + 19% = 119 €")
        assert result.context == FormulaContext.FINANCIAL

    def test_detect_accounting_context(self, service):
        """Test: Buchhaltungs-Kontext wird erkannt."""
        result = service.parse_formula(r"\sum Netto + MwSt = Brutto")
        assert result.context == FormulaContext.ACCOUNTING

    def test_detect_statistical_context(self, service):
        """Test: Statistischer Kontext wird erkannt."""
        result = service.parse_formula(r"\mu + 2\sigma")
        assert result.context == FormulaContext.STATISTICAL

    def test_detect_scientific_context(self, service):
        """Test: Wissenschaftlicher Kontext wird erkannt."""
        result = service.parse_formula(r"\int_0^\infty e^{-x} dx")
        assert result.context == FormulaContext.SCIENTIFIC

    def test_detect_general_context(self, service):
        """Test: Allgemeiner Kontext als Default."""
        result = service.parse_formula("a + b = c")
        assert result.context == FormulaContext.GENERAL


# =============================================================================
# Syntax Validation Tests
# =============================================================================


class TestSyntaxValidation:
    """Tests fuer Syntax-Validierung."""

    def test_valid_formula(self, service):
        """Test: Valide Formel wird als valid markiert."""
        is_valid, issues = service.validate_formula(r"\frac{a}{b}")
        assert is_valid is True
        assert not any(i.severity == ValidationSeverity.ERROR for i in issues)

    def test_unbalanced_braces(self, service):
        """Test: Unausgeglichene Klammern werden erkannt."""
        is_valid, issues = service.validate_formula(r"\frac{a}{b")
        assert is_valid is False
        assert any("Klammer" in i.message for i in issues)

    def test_unknown_command(self, service):
        """Test: Unbekannte Befehle werden als Warnung gemeldet."""
        is_valid, issues = service.validate_formula(r"\unknowncommand{x}")
        # Warnung, aber immer noch valid
        assert any(i.severity == ValidationSeverity.WARNING for i in issues)
        assert any("Unbekannter LaTeX-Befehl" in i.message for i in issues)

    def test_valid_known_commands(self, service):
        """Test: Bekannte Befehle werden akzeptiert."""
        is_valid, issues = service.validate_formula(r"\alpha + \beta = \gamma")
        assert is_valid is True

    def test_ocr_error_detection(self, service):
        """Test: Typische OCR-Fehler werden erkannt."""
        is_valid, issues = service.validate_formula(r"\lrac{a}{b}")  # l statt f
        assert any("OCR" in str(i.message) or "lrac" in str(i.message) for i in issues)


# =============================================================================
# Value Extraction Tests
# =============================================================================


class TestValueExtraction:
    """Tests fuer Werteextraktion."""

    def test_extract_integer(self, service):
        """Test: Ganzzahlen werden extrahiert."""
        values = service.extract_numeric_values("x = 42")
        assert len(values) == 1
        assert values[0].value == Decimal("42")

    def test_extract_decimal(self, service):
        """Test: Dezimalzahlen werden extrahiert."""
        values = service.extract_numeric_values("x = 3.14")
        assert len(values) == 1
        assert values[0].value == Decimal("3.14")

    def test_extract_german_decimal(self, service):
        """Test: Deutsche Dezimalschreibweise (Komma) wird unterstuetzt."""
        values = service.extract_numeric_values("Preis: 19,99 €")
        assert len(values) >= 1
        assert any(v.value == Decimal("19.99") for v in values)

    def test_extract_with_unit(self, service):
        """Test: Einheiten werden mit extrahiert."""
        values = service.extract_numeric_values("Laenge = 5.2 m")
        assert len(values) == 1
        assert values[0].value == Decimal("5.2")
        assert values[0].unit == "m"

    def test_extract_currency(self, service):
        """Test: Waehrungseinheiten werden erkannt."""
        values = service.extract_numeric_values("100 €")
        assert len(values) == 1
        assert values[0].value == Decimal("100")
        assert values[0].unit == "€"

    def test_extract_percentage(self, service):
        """Test: Prozentangaben werden erkannt."""
        values = service.extract_numeric_values("19%")
        assert len(values) == 1
        assert values[0].value == Decimal("19")
        assert values[0].unit == "%"

    def test_extract_multiple_values(self, service):
        """Test: Mehrere Werte werden extrahiert."""
        values = service.extract_numeric_values("a = 10 + 20 = 30")
        assert len(values) == 3

    def test_extract_negative(self, service):
        """Test: Negative Zahlen werden extrahiert."""
        values = service.extract_numeric_values("Delta = -5.5")
        assert any(v.value == Decimal("-5.5") for v in values)

    def test_extract_scientific_notation(self, service):
        """Test: Wissenschaftliche Notation wird unterstuetzt."""
        values = service.extract_numeric_values("x = 1.5e-10")
        assert len(values) >= 1


# =============================================================================
# Variable Extraction Tests
# =============================================================================


class TestVariableExtraction:
    """Tests fuer Variablenextraktion."""

    def test_extract_single_variables(self, service):
        """Test: Einzelne Variablen werden extrahiert."""
        result = service.parse_formula("a + b = c")
        assert "a" in result.variables
        assert "b" in result.variables
        assert "c" in result.variables

    def test_extract_subscripted_variables(self, service):
        """Test: Variablen mit Indizes werden extrahiert."""
        result = service.parse_formula("x_1 + x_2 = x_n")
        # Je nach Implementation koennen subscripts unterschiedlich behandelt werden
        assert len(result.variables) > 0

    def test_ignore_latex_commands(self, service):
        """Test: LaTeX-Befehle werden nicht als Variablen erkannt."""
        result = service.parse_formula(r"\alpha + \beta")
        # alpha und beta sind Befehle, nicht Variablen
        assert "alpha" not in result.variables
        assert "beta" not in result.variables


# =============================================================================
# MathML Conversion Tests
# =============================================================================


class TestMathMLConversion:
    """Tests fuer MathML-Konvertierung."""

    def test_to_mathml_basic(self, service):
        """Test: Einfache Konvertierung zu MathML."""
        mathml = service.to_mathml("a + b = c")
        assert mathml is not None
        assert "math" in mathml
        assert "xmlns" in mathml

    def test_to_mathml_fraction(self, service):
        """Test: Brueche werden konvertiert."""
        mathml = service.to_mathml(r"\frac{a}{b}")
        assert mathml is not None
        assert "mfrac" in mathml

    def test_to_mathml_sqrt(self, service):
        """Test: Wurzeln werden konvertiert."""
        mathml = service.to_mathml(r"\sqrt{x}")
        assert mathml is not None
        assert "msqrt" in mathml

    def test_to_mathml_greek(self, service):
        """Test: Griechische Buchstaben werden konvertiert."""
        mathml = service.to_mathml(r"\alpha + \beta")
        assert mathml is not None
        assert "α" in mathml or "alpha" in mathml.lower()

    def test_to_mathml_numbers(self, service):
        """Test: Zahlen werden als mn-Elemente markiert."""
        mathml = service.to_mathml("x = 42")
        assert mathml is not None
        assert "mn" in mathml


# =============================================================================
# Confidence Calculation Tests
# =============================================================================


class TestConfidenceCalculation:
    """Tests fuer Confidence-Berechnung."""

    def test_valid_formula_high_confidence(self, service):
        """Test: Valide Formeln haben hohe Confidence."""
        result = service.parse_formula(r"\frac{a}{b}")
        assert result.confidence >= 0.8

    def test_invalid_formula_low_confidence(self, service):
        """Test: Invalide Formeln haben niedrige Confidence."""
        result = service.parse_formula("{{{a")  # Unbalanced braces
        assert result.confidence < 0.5

    def test_confidence_range(self, service):
        """Test: Confidence ist immer zwischen 0 und 1."""
        test_cases = [
            r"\frac{a}{b}",
            "x = 5",
            "{{{invalid",
            r"\sum_{i=1}^{n} x_i",
        ]
        for formula in test_cases:
            result = service.parse_formula(formula)
            assert 0.0 <= result.confidence <= 1.0


# =============================================================================
# FormulaResult Tests
# =============================================================================


class TestFormulaResult:
    """Tests fuer FormulaResult Dataclass."""

    def test_to_dict(self, service):
        """Test: to_dict() funktioniert korrekt."""
        result = service.parse_formula("x = 5")
        d = result.to_dict()

        assert "original" in d
        assert "formula_type" in d
        assert "context" in d
        assert "is_valid" in d
        assert "extracted_values" in d
        assert "variables" in d
        assert "validation_issues" in d
        assert "confidence" in d

    def test_to_dict_extracted_values_format(self, service):
        """Test: Extrahierte Werte haben korrektes Format."""
        result = service.parse_formula("x = 100 €")
        d = result.to_dict()

        if d["extracted_values"]:
            value = d["extracted_values"][0]
            assert "value" in value
            assert isinstance(value["value"], (int, float))


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests fuer Randfaelle."""

    def test_empty_formula(self, service):
        """Test: Leere Formel."""
        result = service.parse_formula("")
        assert result is not None
        assert result.original == ""

    def test_whitespace_only(self, service):
        """Test: Nur Whitespace."""
        result = service.parse_formula("   ")
        assert result is not None

    def test_unicode_in_formula(self, service):
        """Test: Unicode-Zeichen in Formel."""
        result = service.parse_formula("α + β = γ")  # Direkte Unicode-Zeichen
        assert result is not None

    def test_very_long_formula(self, service):
        """Test: Sehr lange Formel."""
        long_formula = " + ".join([f"x_{i}" for i in range(100)])
        result = service.parse_formula(long_formula)
        assert result is not None

    def test_nested_braces(self, service):
        """Test: Tief verschachtelte Klammern."""
        nested = r"\frac{\frac{\frac{a}{b}}{c}}{d}"
        result = service.parse_formula(nested)
        assert result.is_valid

    def test_mixed_delimiters(self, service):
        """Test: Gemischte Delimiter im Text."""
        text = "Formel 1: $a + b$ und Formel 2: $$c + d$$"
        results = service.extract_formulas(text)
        assert len(results) == 2
