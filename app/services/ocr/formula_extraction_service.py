# -*- coding: utf-8 -*-
"""
LaTeX Formula Extraction Service.

Parst und validiert LaTeX-Formeln aus OCR-Output (GOT-OCR, OlmOCR):
- LaTeX-Syntax-Validierung
- Numerische Wertextraktion aus Formeln
- MathML/SVG Rendering-Vorbereitung
- Formel-Klassifizierung (Gleichung, Ungleichung, etc.)

Feature 19: LaTeX Formula Parsing

Feinpoliert und durchdacht - Mathematische Inhalte präzise verarbeiten.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums
# =============================================================================


class FormulaType(str, Enum):
    """Typ der mathematischen Formel."""
    EQUATION = "equation"          # Gleichung (a = b)
    INEQUALITY = "inequality"      # Ungleichung (a < b, a >= b)
    EXPRESSION = "expression"      # Ausdruck (a + b)
    FRACTION = "fraction"          # Bruch (a/b)
    SUM = "sum"                    # Summe (Σ)
    PRODUCT = "product"            # Produkt (Π)
    INTEGRAL = "integral"          # Integral (∫)
    DERIVATIVE = "derivative"      # Ableitung (d/dx)
    MATRIX = "matrix"              # Matrix
    SET = "set"                    # Mengenschreibweise
    LIMIT = "limit"                # Grenzwert (lim)
    UNKNOWN = "unknown"            # Unbekannt


class FormulaContext(str, Enum):
    """Kontext der Formel im Dokument."""
    FINANCIAL = "financial"        # Finanzberechnung
    SCIENTIFIC = "scientific"      # Wissenschaftlich
    STATISTICAL = "statistical"    # Statistik
    ACCOUNTING = "accounting"      # Buchhaltung (Summen, Prozent)
    ENGINEERING = "engineering"    # Ingenieurwesen
    GENERAL = "general"            # Allgemein


class ValidationSeverity(str, Enum):
    """Schweregrad einer Validierungsmeldung."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class ValidationIssue:
    """Validierungsproblem bei einer Formel."""
    severity: ValidationSeverity
    message: str
    position: Optional[int] = None
    length: Optional[int] = None
    suggestion: Optional[str] = None


@dataclass
class ExtractedValue:
    """Extrahierter numerischer Wert aus einer Formel."""
    value: Decimal
    unit: Optional[str] = None
    label: Optional[str] = None
    position_in_formula: Optional[str] = None


@dataclass
class FormulaResult:
    """Ergebnis der Formelanalyse."""
    original: str
    formula_type: FormulaType
    context: FormulaContext
    is_valid: bool
    normalized: Optional[str] = None
    extracted_values: List[ExtractedValue] = field(default_factory=list)
    variables: List[str] = field(default_factory=list)
    validation_issues: List[ValidationIssue] = field(default_factory=list)
    mathml: Optional[str] = None
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary."""
        return {
            "original": self.original,
            "formula_type": self.formula_type.value,
            "context": self.context.value,
            "is_valid": self.is_valid,
            "normalized": self.normalized,
            "extracted_values": [
                {
                    "value": float(v.value),
                    "unit": v.unit,
                    "label": v.label,
                }
                for v in self.extracted_values
            ],
            "variables": self.variables,
            "validation_issues": [
                {
                    "severity": i.severity.value,
                    "message": i.message,
                    "suggestion": i.suggestion,
                }
                for i in self.validation_issues
            ],
            "mathml": self.mathml,
            "confidence": self.confidence,
        }


# =============================================================================
# LaTeX Patterns
# =============================================================================

# LaTeX-Befehle die einen validen Formelbeginn markieren
LATEX_MATH_DELIMITERS = [
    (r"\$\$(.*?)\$\$", "display"),      # Display math $$...$$
    (r"\$(.*?)\$", "inline"),            # Inline math $...$
    (r"\\begin\{equation\}(.*?)\\end\{equation\}", "equation"),
    (r"\\begin\{align\}(.*?)\\end\{align\}", "align"),
    (r"\\begin\{gather\}(.*?)\\end\{gather\}", "gather"),
    (r"\\begin\{eqnarray\}(.*?)\\end\{eqnarray\}", "eqnarray"),
    (r"\\\[(.*?)\\\]", "display_bracket"),  # \[...\]
    (r"\\\((.*?)\\\)", "inline_paren"),     # \(...\)
]

# LaTeX-Befehle für Struktur-Erkennung
LATEX_COMMANDS = {
    # Brüche
    r"\\frac": "fraction",
    r"\\dfrac": "fraction",
    r"\\tfrac": "fraction",

    # Summen/Produkte
    r"\\sum": "sum",
    r"\\prod": "product",

    # Integrale
    r"\\int": "integral",
    r"\\iint": "integral",
    r"\\iiint": "integral",
    r"\\oint": "integral",

    # Ableitungen
    r"\\frac\{d": "derivative",
    r"\\partial": "derivative",

    # Matrizen
    r"\\begin\{matrix": "matrix",
    r"\\begin\{pmatrix": "matrix",
    r"\\begin\{bmatrix": "matrix",
    r"\\begin\{vmatrix": "matrix",

    # Mengen
    r"\\in": "set",
    r"\\subset": "set",
    r"\\cup": "set",
    r"\\cap": "set",

    # Grenzwerte
    r"\\lim": "limit",
}

# Ungleichheitsoperatoren
INEQUALITY_OPERATORS = {
    r"<", r">", r"\\le", r"\\leq", r"\\ge", r"\\geq",
    r"\\lt", r"\\gt", r"\\neq", r"\\ne",
}

# Gleichheitsoperatoren
EQUALITY_OPERATORS = {
    r"=", r"\\equiv", r"\\approx", r"\\sim", r"\\cong",
}

# Bekannte LaTeX-Befehle für Validierung
VALID_LATEX_COMMANDS = {
    # Griechische Buchstaben
    r"\\alpha", r"\\beta", r"\\gamma", r"\\delta", r"\\epsilon",
    r"\\zeta", r"\\eta", r"\\theta", r"\\iota", r"\\kappa",
    r"\\lambda", r"\\mu", r"\\nu", r"\\xi", r"\\pi",
    r"\\rho", r"\\sigma", r"\\tau", r"\\upsilon", r"\\phi",
    r"\\chi", r"\\psi", r"\\omega",
    r"\\Gamma", r"\\Delta", r"\\Theta", r"\\Lambda", r"\\Xi",
    r"\\Pi", r"\\Sigma", r"\\Upsilon", r"\\Phi", r"\\Psi", r"\\Omega",

    # Mathematische Operatoren
    r"\\sin", r"\\cos", r"\\tan", r"\\cot", r"\\sec", r"\\csc",
    r"\\log", r"\\ln", r"\\exp", r"\\sqrt", r"\\root",
    r"\\max", r"\\min", r"\\sup", r"\\inf", r"\\lim",

    # Pfeile
    r"\\to", r"\\rightarrow", r"\\leftarrow", r"\\Rightarrow",
    r"\\Leftarrow", r"\\leftrightarrow", r"\\Leftrightarrow",

    # Klammern
    r"\\left", r"\\right", r"\\big", r"\\Big", r"\\bigg", r"\\Bigg",

    # Akzente
    r"\\hat", r"\\bar", r"\\dot", r"\\ddot", r"\\tilde", r"\\vec",

    # Sonstiges
    r"\\infty", r"\\pm", r"\\mp", r"\\times", r"\\div", r"\\cdot",
    r"\\ldots", r"\\cdots", r"\\vdots", r"\\ddots",
    r"\\text", r"\\mathrm", r"\\mathbf", r"\\mathit",
}


# =============================================================================
# Service Implementation
# =============================================================================


class FormulaExtractionService:
    """Service für LaTeX-Formelextraktion und -validierung."""

    def __init__(self) -> None:
        """Initialisiere Service."""
        # Kompilierte Regex-Pattern
        self._delimiter_patterns = [
            (re.compile(pattern, re.DOTALL), mode)
            for pattern, mode in LATEX_MATH_DELIMITERS
        ]
        self._number_pattern = re.compile(
            r"(-?\d+(?:[.,]\d+)?(?:[eE][+-]?\d+)?)\s*"
            r"(€|EUR|USD|\$|%|kg|g|m|cm|mm|km|l|ml|s|min|h|°C|°F|K)?"
        )
        self._variable_pattern = re.compile(r"\\?([a-zA-Z](?:_\{?[a-zA-Z0-9]+\}?)?)")

    def extract_formulas(self, text: str) -> List[FormulaResult]:
        """
        Extrahiere alle LaTeX-Formeln aus Text.

        Args:
            text: OCR-Text mit eingebetteten LaTeX-Formeln

        Returns:
            Liste der gefundenen und analysierten Formeln
        """
        results: List[FormulaResult] = []

        for pattern, mode in self._delimiter_patterns:
            for match in pattern.finditer(text):
                formula_content = match.group(1)
                if formula_content.strip():
                    result = self.parse_formula(formula_content)
                    results.append(result)

        return results

    def parse_formula(self, latex: str) -> FormulaResult:
        """
        Parse und analysiere eine einzelne LaTeX-Formel.

        Args:
            latex: LaTeX-Formelinhalt (ohne Delimiter)

        Returns:
            FormulaResult mit Analyse-Ergebnissen
        """
        # Normalisiere Whitespace
        normalized = " ".join(latex.split())

        # Validiere Syntax
        is_valid, issues = self._validate_syntax(normalized)

        # Bestimme Formeltyp
        formula_type = self._detect_formula_type(normalized)

        # Bestimme Kontext
        context = self._detect_context(normalized)

        # Extrahiere numerische Werte
        extracted_values = self._extract_values(normalized)

        # Extrahiere Variablen
        variables = self._extract_variables(normalized)

        # Berechne Confidence
        confidence = self._calculate_confidence(is_valid, len(issues), normalized)

        return FormulaResult(
            original=latex,
            formula_type=formula_type,
            context=context,
            is_valid=is_valid,
            normalized=normalized,
            extracted_values=extracted_values,
            variables=variables,
            validation_issues=issues,
            confidence=confidence,
        )

    def validate_formula(self, latex: str) -> Tuple[bool, List[ValidationIssue]]:
        """
        Validiere LaTeX-Syntax.

        Args:
            latex: LaTeX-Formel

        Returns:
            Tuple (is_valid, issues)
        """
        return self._validate_syntax(latex)

    def extract_numeric_values(self, latex: str) -> List[ExtractedValue]:
        """
        Extrahiere numerische Werte aus Formel.

        Args:
            latex: LaTeX-Formel

        Returns:
            Liste extrahierter Werte
        """
        return self._extract_values(latex)

    def to_mathml(self, latex: str) -> Optional[str]:
        """
        Konvertiere LaTeX zu MathML.

        HINWEIS: Für vollständige MathML-Konvertierung wird eine
        externe Bibliothek wie latex2mathml benötigt.

        Args:
            latex: LaTeX-Formel

        Returns:
            MathML-String oder None
        """
        # Einfache Konvertierung für häufige Fälle
        # Für vollständige Unterstützung: latex2mathml Bibliothek verwenden
        try:
            # Basis-MathML-Wrapper
            mathml = f'<math xmlns="http://www.w3.org/1998/Math/MathML">'

            # Einfache Ersetzungen
            content = latex
            content = re.sub(r"\\frac\{([^}]+)\}\{([^}]+)\}", r"<mfrac><mrow>\1</mrow><mrow>\2</mrow></mfrac>", content)
            content = re.sub(r"\\sqrt\{([^}]+)\}", r"<msqrt>\1</msqrt>", content)
            content = re.sub(r"\^(\{[^}]+\}|.)", r"<msup><mrow></mrow>\1</msup>", content)
            content = re.sub(r"_(\{[^}]+\}|.)", r"<msub><mrow></mrow>\1</msub>", content)

            # Griechische Buchstaben
            greek_map = {
                r"\\alpha": "α", r"\\beta": "β", r"\\gamma": "γ",
                r"\\delta": "δ", r"\\epsilon": "ε", r"\\pi": "π",
                r"\\sigma": "σ", r"\\theta": "θ", r"\\lambda": "λ",
            }
            for tex, symbol in greek_map.items():
                content = content.replace(tex, f"<mi>{symbol}</mi>")

            # Zahlen
            content = re.sub(r"(\d+(?:\.\d+)?)", r"<mn>\1</mn>", content)

            # Variablen (einzelne Buchstaben)
            content = re.sub(r"(?<![a-zA-Z])([a-zA-Z])(?![a-zA-Z{])", r"<mi>\1</mi>", content)

            mathml += content + "</math>"
            return mathml

        except Exception as e:
            logger.warning("MathML-Konvertierung fehlgeschlagen", error=str(e))
            return None

    # =========================================================================
    # Private Methods
    # =========================================================================

    def _validate_syntax(self, latex: str) -> Tuple[bool, List[ValidationIssue]]:
        """Validiere LaTeX-Syntax."""
        issues: List[ValidationIssue] = []

        # Check balanced braces
        brace_count = 0
        for i, char in enumerate(latex):
            if char == "{":
                brace_count += 1
            elif char == "}":
                brace_count -= 1
                if brace_count < 0:
                    issues.append(ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        message="Unausgeglichene schließende Klammer",
                        position=i,
                    ))
                    brace_count = 0

        if brace_count > 0:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                message=f"{brace_count} öffnende Klammer(n) ohne Gegenstück",
            ))

        # Check for unknown commands
        commands = re.findall(r"\\[a-zA-Z]+", latex)
        valid_commands = VALID_LATEX_COMMANDS | set(LATEX_COMMANDS.keys())
        for cmd in commands:
            if cmd not in valid_commands and not cmd.startswith(r"\begin") and not cmd.startswith(r"\end"):
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    message=f"Unbekannter LaTeX-Befehl: {cmd}",
                    suggestion="Prüfen Sie die Schreibweise des Befehls",
                ))

        # Check for common OCR errors
        ocr_issues = self._check_ocr_errors(latex)
        issues.extend(ocr_issues)

        is_valid = not any(i.severity == ValidationSeverity.ERROR for i in issues)
        return is_valid, issues

    def _check_ocr_errors(self, latex: str) -> List[ValidationIssue]:
        """Prüfe auf typische OCR-Fehler in Formeln."""
        issues: List[ValidationIssue] = []

        # Häufige OCR-Verwechslungen
        ocr_confusions = [
            (r"\\lrac", r"\\frac", "OCR könnte 'f' als 'l' erkannt haben"),
            (r"\\sqnt", r"\\sqrt", "OCR könnte 'r' als 'n' erkannt haben"),
            (r"0([a-zA-Z])", r"O\1", "Null könnte mit O verwechselt sein"),
            (r"1([a-zA-Z])", r"l\1", "Eins könnte mit l verwechselt sein"),
        ]

        for pattern, suggestion, message in ocr_confusions:
            if re.search(pattern, latex):
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    message=message,
                    suggestion=f"Mögliche Korrektur: {suggestion}",
                ))

        return issues

    def _detect_formula_type(self, latex: str) -> FormulaType:
        """Bestimme den Typ der Formel."""
        # Prüfe auf spezifische LaTeX-Befehle
        for pattern, formula_type in LATEX_COMMANDS.items():
            if re.search(pattern, latex):
                return FormulaType(formula_type)

        # Prüfe auf Gleichung vs Ungleichung
        has_equality = any(op in latex for op in EQUALITY_OPERATORS)
        has_inequality = any(re.search(op, latex) for op in INEQUALITY_OPERATORS)

        if has_inequality:
            return FormulaType.INEQUALITY
        elif has_equality:
            return FormulaType.EQUATION
        else:
            return FormulaType.EXPRESSION

    def _detect_context(self, latex: str) -> FormulaContext:
        """Bestimme den Kontext der Formel."""
        # Finanzielle Indikatoren
        financial_patterns = [r"€", r"EUR", r"USD", r"\$", r"%", r"Zinsen?", r"Betrag"]
        for pattern in financial_patterns:
            if re.search(pattern, latex, re.IGNORECASE):
                return FormulaContext.FINANCIAL

        # Buchhaltung
        accounting_patterns = [r"\\sum", r"Summe", r"Saldo", r"Brutto", r"Netto", r"MwSt"]
        for pattern in accounting_patterns:
            if re.search(pattern, latex, re.IGNORECASE):
                return FormulaContext.ACCOUNTING

        # Statistik
        statistical_patterns = [r"\\mu", r"\\sigma", r"\\bar", r"Mittelwert", r"Varianz"]
        for pattern in statistical_patterns:
            if re.search(pattern, latex):
                return FormulaContext.STATISTICAL

        # Wissenschaftlich
        scientific_patterns = [r"\\int", r"\\partial", r"\\nabla", r"\\lim"]
        for pattern in scientific_patterns:
            if re.search(pattern, latex):
                return FormulaContext.SCIENTIFIC

        return FormulaContext.GENERAL

    def _extract_values(self, latex: str) -> List[ExtractedValue]:
        """Extrahiere numerische Werte aus Formel."""
        values: List[ExtractedValue] = []

        # Entferne LaTeX-Befehle für saubere Zahlenextraktion
        cleaned = re.sub(r"\\[a-zA-Z]+\{?", " ", latex)
        cleaned = re.sub(r"\}", " ", cleaned)

        for match in self._number_pattern.finditer(cleaned):
            number_str = match.group(1).replace(",", ".")
            unit = match.group(2) if match.group(2) else None

            try:
                value = Decimal(number_str)
                values.append(ExtractedValue(
                    value=value,
                    unit=unit,
                ))
            except InvalidOperation:
                continue

        return values

    def _extract_variables(self, latex: str) -> List[str]:
        """Extrahiere Variablennamen aus Formel."""
        variables: Set[str] = set()

        # Finde Variablen (Buchstaben die nicht Teil von Befehlen sind)
        # Entferne zuerst alle LaTeX-Befehle
        cleaned = re.sub(r"\\[a-zA-Z]+", " ", latex)

        for match in self._variable_pattern.finditer(cleaned):
            var = match.group(1)
            if len(var) == 1 or var.startswith("_"):
                variables.add(var)

        return sorted(list(variables))

    def _calculate_confidence(
        self,
        is_valid: bool,
        issue_count: int,
        latex: str,
    ) -> float:
        """Berechne Confidence-Score."""
        if not is_valid:
            return 0.3

        base_confidence = 0.9

        # Reduziere für Warnungen
        base_confidence -= issue_count * 0.1

        # Erhöhe für erkannte Strukturen
        for pattern in LATEX_COMMANDS.keys():
            if re.search(pattern, latex):
                base_confidence += 0.02

        return max(0.0, min(1.0, base_confidence))


# =============================================================================
# Service Instance
# =============================================================================

_service: Optional[FormulaExtractionService] = None


def get_formula_extraction_service() -> FormulaExtractionService:
    """Hole Singleton-Instanz des Services."""
    global _service
    if _service is None:
        _service = FormulaExtractionService()
    return _service
