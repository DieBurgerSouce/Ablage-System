# -*- coding: utf-8 -*-
"""
Pytest configuration for E2E tests.

Provides shared fixtures for:
- Test client setup
- Sample document generation
- Mock services
- Cleanup utilities

Feinpoliert und durchdacht - End-to-End Test Infrastruktur.
"""

import pytest
import tempfile
import asyncio
from pathlib import Path
from typing import Generator, Dict, Any
from unittest.mock import Mock, AsyncMock, patch
import sys

# Ensure app is in path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_storage() -> Generator[Path, None, None]:
    """Provide temporary storage directory for E2E tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir)
        # Create standard subdirectories
        (storage / "uploads").mkdir()
        (storage / "processed").mkdir()
        (storage / "cache").mkdir()
        (storage / "exports").mkdir()
        yield storage


@pytest.fixture
def sample_german_text() -> str:
    """Provide sample German text with umlauts."""
    return """
    RECHNUNG Nr. 2024-0001

    Datum: 15.03.2024
    Fälligkeitsdatum: 14.04.2024

    Muster GmbH
    Hauptstraße 123
    12345 Berlin

    Steuernummer: 12/345/67890
    USt-IdNr.: DE123456789

    Sehr geehrte Damen und Herren,

    für die erbrachten Leistungen berechnen wir Ihnen:

    Position 1: Beratungsleistung          500,00 EUR
    Position 2: Softwarelizenz             300,00 EUR
    Position 3: Schulung                   200,00 EUR

    Nettobetrag:                         1.000,00 EUR
    MwSt. 19%:                             190,00 EUR
    Gesamtbetrag:                        1.190,00 EUR

    Zahlbar innerhalb von 30 Tagen auf:
    IBAN: DE89 3704 0044 0532 0130 00
    BIC: COBADEFFXXX

    Mit freundlichen Grüßen
    Max Mustermann
    Geschäftsführer
    """


@pytest.fixture
def sample_contract_text() -> str:
    """Provide sample German contract text."""
    return """
    MIETVERTRAG

    zwischen

    Vermieter:
    Max Müller
    Schloßstraße 45
    80333 München

    und

    Mieter:
    Erika Schmöller
    Gärtnerstraße 12
    80339 München

    §1 Mietobjekt

    Vermietet wird die Wohnung in der Hauptstraße 78, 80331 München,
    bestehend aus 3 Zimmern, Küche, Bad und Flur.

    §2 Mietdauer

    Der Mietvertrag beginnt am 01.04.2024.
    Die Mindestmietdauer beträgt 12 Monate.
    Die Kündigungsfrist beträgt 3 Monate zum Monatsende.

    §3 Miete

    Die monatliche Kaltmiete beträgt: 1.200,00 EUR
    Nebenkostenvorauszahlung:          200,00 EUR
    Gesamtmiete:                      1.400,00 EUR

    Die Kaution beträgt 3.600,00 EUR (drei Monatsmieten).

    §4 Übergabe

    Die Übergabe der Wohnung erfolgt am Mietbeginn.
    Ein Übergabeprotokoll wird erstellt.

    München, den 15.03.2024

    _________________________    _________________________
    Vermieter                    Mieter
    """


@pytest.fixture
def mock_ocr_result() -> Dict[str, Any]:
    """Provide mock OCR processing result."""
    return {
        "success": True,
        "text": "Dies ist ein Beispieltext mit deutschen Umlauten: ä, ö, ü, ß",
        "confidence": 0.95,
        "processing_time_ms": 1250.0,
        "backend": "deepseek",
        "language": "de",
        "word_count": 11,
        "pages": 1,
        "metadata": {
            "backend_used": "deepseek",
            "processing_time_seconds": 1.25,
            "language": "de"
        }
    }


@pytest.fixture
def mock_entity_extraction_result() -> Dict[str, Any]:
    """Provide mock entity extraction result."""
    return {
        "entities": [
            {"type": "date", "value": "15.03.2024", "confidence": 0.95},
            {"type": "date", "value": "14.04.2024", "confidence": 0.94},
            {"type": "currency", "value": {"amount": 1190.0, "currency": "EUR"}, "confidence": 0.98},
            {"type": "iban", "value": "DE89370400440532013000", "valid": True, "confidence": 0.99},
            {"type": "vat_id", "value": "DE123456789", "confidence": 0.97},
            {"type": "address", "value": {"street": "Hauptstraße 123", "zip": "12345", "city": "Berlin"}, "confidence": 0.92},
        ],
        "entity_count": 6,
        "processing_time_ms": 350.0
    }


@pytest.fixture
def mock_classification_result() -> Dict[str, Any]:
    """Provide mock classification result."""
    return {
        "document_type": "invoice",
        "confidence": 0.92,
        "language": "de",
        "complexity": "medium",
        "has_tables": True,
        "has_images": False,
        "page_count": 1,
        "recommended_backend": "deepseek"
    }


@pytest.fixture
def mock_qa_result() -> Dict[str, Any]:
    """Provide mock QA result."""
    return {
        "quality_level": "good",
        "quality_score": 0.88,
        "issues": [],
        "metrics": {
            "umlaut_accuracy": 1.0,
            "date_format_correct": True,
            "currency_format_correct": True
        },
        "recommendations": []
    }


@pytest.fixture
def mock_correction_result() -> Dict[str, Any]:
    """Provide mock German correction result."""
    return {
        "text": "Der korrigierte deutsche Text mit Umlauten: Änderung, Öffnung, Übung.",
        "original_text": "Der korrigierte deutsche Text mit Umlauten: Aenderung, Oeffnung, Uebung.",
        "corrections_applied": 3,
        "correction_details": [
            {"type": "umlaut", "original": "Aenderung", "corrected": "Änderung", "confidence": 0.95},
            {"type": "umlaut", "original": "Oeffnung", "corrected": "Öffnung", "confidence": 0.94},
            {"type": "umlaut", "original": "Uebung", "corrected": "Übung", "confidence": 0.93}
        ],
        "validation_score": 0.95,
        "umlauts_restored": 3
    }


# Markers for test categorization
def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line(
        "markers", "e2e: mark test as end-to-end test"
    )
    config.addinivalue_line(
        "markers", "pipeline: mark test as pipeline test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
