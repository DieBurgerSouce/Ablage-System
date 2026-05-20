# -*- coding: utf-8 -*-
"""
Unit Tests fuer OCR Formula Extraction API (Feature 19).

Testet:
- POST /api/v1/ocr/formulas/extract
- POST /api/v1/ocr/formulas/parse
- POST /api/v1/ocr/formulas/validate
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch
import pytest
from fastapi import status

from app.services.ocr.formula_extraction_service import (
    FormulaResult,
    FormulaType,
    FormulaContext,
    ValidationSeverity,
    ValidationIssue,
    ExtractedValue,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_formula_result():
    """Mock FormulaResult fuer Tests."""
    return FormulaResult(
        original="x = 5",
        formula_type=FormulaType.EQUATION,
        context=FormulaContext.GENERAL,
        is_valid=True,
        validation_issues=[],
        extracted_values=[
            ExtractedValue(value=Decimal("5"), unit=None, position=4)
        ],
        variables=["x"],
        confidence=0.95,
    )


# =============================================================================
# POST /formulas/extract Tests
# =============================================================================


class TestExtractFormulas:
    """Tests fuer POST /ocr/formulas/extract."""

    @pytest.mark.asyncio
    async def test_extracts_formulas_from_text(
        self, client, auth_headers, mock_formula_result
    ):
        """Test: Formeln werden aus Text extrahiert."""
        with patch(
            "app.api.v1.ocr.get_formula_extraction_service"
        ) as mock_service:
            service = MagicMock()
            service.extract_formulas.return_value = [mock_formula_result]
            mock_service.return_value = service

            response = await client.post(
                "/api/v1/ocr/formulas/extract",
                json={"text": "Die Gleichung $x = 5$ ist einfach."},
                headers=auth_headers,
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            # API gibt deutsche Feldnamen zurueck
            assert "formeln" in data
            assert len(data["formeln"]) == 1
            assert data["formeln"][0]["formula_type"] == "equation"

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_formulas(self, client, auth_headers):
        """Test: Leere Liste bei Text ohne Formeln."""
        with patch(
            "app.api.v1.ocr.get_formula_extraction_service"
        ) as mock_service:
            service = MagicMock()
            service.extract_formulas.return_value = []
            mock_service.return_value = service

            response = await client.post(
                "/api/v1/ocr/formulas/extract",
                json={"text": "Normaler Text ohne Mathematik."},
                headers=auth_headers,
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            # API gibt deutsche Feldnamen zurueck
            assert data["formeln"] == []
            assert data["formeln_gefunden"] == 0

    @pytest.mark.asyncio
    async def test_requires_authentication(self, client):
        """Test: Authentifizierung erforderlich."""
        response = await client.post(
            "/api/v1/ocr/formulas/extract",
            json={"text": "Test"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_validates_text_not_empty(self, client, auth_headers):
        """Test: Text darf nicht leer sein."""
        response = await client.post(
            "/api/v1/ocr/formulas/extract",
            json={"text": ""},
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# =============================================================================
# POST /formulas/parse Tests
# =============================================================================


class TestParseFormula:
    """Tests fuer POST /ocr/formulas/parse."""

    @pytest.mark.asyncio
    async def test_parses_valid_formula(
        self, client, auth_headers, mock_formula_result
    ):
        """Test: Valide Formel wird geparst."""
        with patch(
            "app.api.v1.ocr.get_formula_extraction_service"
        ) as mock_service:
            service = MagicMock()
            service.parse_formula.return_value = mock_formula_result
            service.to_mathml.return_value = "<math><mi>x</mi></math>"
            mock_service.return_value = service

            response = await client.post(
                "/api/v1/ocr/formulas/parse",
                json={"formula": "x = 5"},
                headers=auth_headers,
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["formula_type"] == "equation"
            assert data["is_valid"] is True
            assert "mathml" in data

    @pytest.mark.asyncio
    async def test_handles_complex_formula(self, client, auth_headers):
        """Test: Komplexe Formeln werden verarbeitet."""
        complex_result = FormulaResult(
            original=r"\frac{a}{b}",
            formula_type=FormulaType.FRACTION,
            context=FormulaContext.GENERAL,
            is_valid=True,
            validation_issues=[],
            extracted_values=[],
            variables=["a", "b"],
            confidence=0.92,
        )

        with patch(
            "app.api.v1.ocr.get_formula_extraction_service"
        ) as mock_service:
            service = MagicMock()
            service.parse_formula.return_value = complex_result
            service.to_mathml.return_value = "<math><mfrac></mfrac></math>"
            mock_service.return_value = service

            response = await client.post(
                "/api/v1/ocr/formulas/parse",
                json={"formula": r"\frac{a}{b}"},
                headers=auth_headers,
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["formula_type"] == "fraction"


# =============================================================================
# POST /formulas/validate Tests
# =============================================================================


class TestValidateFormula:
    """Tests fuer POST /ocr/formulas/validate."""

    @pytest.mark.asyncio
    async def test_validates_correct_formula(self, client, auth_headers):
        """Test: Korrekte Formel wird als valid markiert."""
        with patch(
            "app.api.v1.ocr.get_formula_extraction_service"
        ) as mock_service:
            service = MagicMock()
            service.validate_formula.return_value = (True, [])
            mock_service.return_value = service

            response = await client.post(
                "/api/v1/ocr/formulas/validate",
                json={"formula": r"\frac{a}{b}"},
                headers=auth_headers,
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["is_valid"] is True
            assert data["issues"] == []

    @pytest.mark.asyncio
    async def test_reports_validation_issues(self, client, auth_headers):
        """Test: Validierungsprobleme werden gemeldet."""
        issues = [
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                message="Unbalanced braces",
                position=5,
            )
        ]

        with patch(
            "app.api.v1.ocr.get_formula_extraction_service"
        ) as mock_service:
            service = MagicMock()
            service.validate_formula.return_value = (False, issues)
            mock_service.return_value = service

            response = await client.post(
                "/api/v1/ocr/formulas/validate",
                json={"formula": "{{{invalid"},
                headers=auth_headers,
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["is_valid"] is False
            assert len(data["issues"]) == 1
            assert data["issues"][0]["severity"] == "error"

    @pytest.mark.asyncio
    async def test_validates_formula_length(self, client, auth_headers):
        """Test: Formel-Laenge wird validiert (max 2000 chars)."""
        long_formula = "x" * 2001

        response = await client.post(
            "/api/v1/ocr/formulas/validate",
            json={"formula": long_formula},
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
