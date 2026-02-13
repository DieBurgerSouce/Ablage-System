# -*- coding: utf-8 -*-
"""Tests fuer AutoTemplateService."""
import pytest
from uuid import uuid4
from app.services.ocr.auto_template_service import (
    AutoTemplateService,
    FieldPosition,
    MIN_DOCUMENTS_FOR_TEMPLATE,
)


class TestAutoTemplateService:
    """Tests fuer automatische Template-Generierung."""

    def setup_method(self) -> None:
        self.service = AutoTemplateService()

    def test_calculate_position_variance_identical(self) -> None:
        """Identische Positionen = 0 Varianz."""
        positions = [
            FieldPosition("test", 0.5, 0.3, 0.1, 0.02),
            FieldPosition("test", 0.5, 0.3, 0.1, 0.02),
            FieldPosition("test", 0.5, 0.3, 0.1, 0.02),
        ]
        variance = self.service._calculate_position_variance(positions)
        assert variance == 0.0

    def test_calculate_position_variance_within_tolerance(self) -> None:
        """Geringe Abweichungen unter Toleranzschwelle."""
        positions = [
            FieldPosition("test", 0.50, 0.30, 0.1, 0.02),
            FieldPosition("test", 0.51, 0.31, 0.1, 0.02),
            FieldPosition("test", 0.49, 0.29, 0.1, 0.02),
        ]
        variance = self.service._calculate_position_variance(positions)
        assert variance < 0.05  # Within tolerance

    def test_calculate_position_variance_high(self) -> None:
        """Grosse Abweichungen ueber Toleranzschwelle."""
        positions = [
            FieldPosition("test", 0.1, 0.1, 0.1, 0.02),
            FieldPosition("test", 0.9, 0.9, 0.1, 0.02),
        ]
        variance = self.service._calculate_position_variance(positions)
        assert variance > 0.05

    def test_find_common_fields(self) -> None:
        """Felder die in 2/3 der Dokumente vorkommen."""
        all_positions = {
            uuid4(): {
                "invoice_number": FieldPosition("invoice_number", 0.5, 0.1, 0.1, 0.02),
                "total_amount": FieldPosition("total_amount", 0.5, 0.9, 0.1, 0.02),
                "rare_field": FieldPosition("rare_field", 0.1, 0.1, 0.1, 0.02),
            },
            uuid4(): {
                "invoice_number": FieldPosition("invoice_number", 0.5, 0.1, 0.1, 0.02),
                "total_amount": FieldPosition("total_amount", 0.5, 0.9, 0.1, 0.02),
            },
            uuid4(): {
                "invoice_number": FieldPosition("invoice_number", 0.5, 0.1, 0.1, 0.02),
                "total_amount": FieldPosition("total_amount", 0.5, 0.9, 0.1, 0.02),
            },
        }
        common = self.service._find_common_fields(all_positions)
        assert "invoice_number" in common
        assert "total_amount" in common
        assert "rare_field" not in common

    def test_build_field_definitions(self) -> None:
        """Field-Definitionen werden korrekt generiert."""
        all_positions = {
            uuid4(): {
                "invoice_number": FieldPosition("invoice_number", 0.50, 0.10, 0.15, 0.03),
            },
            uuid4(): {
                "invoice_number": FieldPosition("invoice_number", 0.52, 0.11, 0.14, 0.03),
            },
            uuid4(): {
                "invoice_number": FieldPosition("invoice_number", 0.48, 0.09, 0.16, 0.03),
            },
        }
        defs = self.service._build_field_definitions(all_positions, ["invoice_number"])
        assert len(defs) == 1
        assert defs[0]["name"] == "invoice_number"
        assert defs[0]["label"] == "Rechnungsnummer"
        assert "coordinates" in defs[0]
        assert defs[0]["sample_count"] == 3

    def test_calculate_template_confidence(self) -> None:
        """Template-Confidence wird korrekt berechnet."""
        all_positions = {
            uuid4(): {
                "invoice_number": FieldPosition("invoice_number", 0.50, 0.10, 0.15, 0.03),
            },
            uuid4(): {
                "invoice_number": FieldPosition("invoice_number", 0.50, 0.10, 0.15, 0.03),
            },
        }
        confidence = self.service._calculate_template_confidence(
            all_positions, ["invoice_number"]
        )
        assert confidence == 1.0  # Identical positions = max confidence

    def test_calculate_template_confidence_empty(self) -> None:
        """Leere Felder = 0 Confidence."""
        confidence = self.service._calculate_template_confidence({}, [])
        assert confidence == 0.0

    def test_min_documents_constant(self) -> None:
        """Mindestanzahl Dokumente fuer Template."""
        assert MIN_DOCUMENTS_FOR_TEMPLATE == 3
