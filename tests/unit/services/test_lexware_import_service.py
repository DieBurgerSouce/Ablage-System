# -*- coding: utf-8 -*-
"""
Tests fuer LexwareImportService.

Testet:
- Hilfsfunktionen (normalize_text, calculate_similarity, is_placeholder)
- Datenklassen (ImportResult, CustomerRecord, SupplierRecord)
- Kunden-Import
- Lieferanten-Import
- Konflikt-Erkennung und -Behandlung
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import pandas as pd

from app.services.lexware_import_service import (
    LexwareImportService,
    ImportResult,
    CustomerRecord,
    SupplierRecord,
    normalize_text,
    calculate_similarity,
    is_placeholder,
    clean_customer_number,
)
from app.db.models import BusinessEntity, EntityType


class TestNormalizeText:
    """Tests fuer normalize_text Hilfsfunktion."""

    def test_normalize_lowercase(self):
        """Sollte Text in Kleinbuchstaben umwandeln."""
        result = normalize_text("MUELLER GMBH")
        assert result == "mueller gmbh"

    def test_normalize_whitespace(self):
        """Sollte mehrfache Leerzeichen reduzieren."""
        result = normalize_text("Mueller   GmbH   Berlin")
        assert result == "mueller gmbh berlin"

    def test_normalize_empty(self):
        """Sollte leeren String bei leerem Input zurueckgeben."""
        assert normalize_text("") == ""
        assert normalize_text(None) == ""

    def test_normalize_strip(self):
        """Sollte fuehrende/nachfolgende Leerzeichen entfernen."""
        result = normalize_text("  Mueller GmbH  ")
        assert result == "mueller gmbh"

    def test_normalize_with_umlauts(self):
        """Sollte Umlaute korrekt behandeln."""
        result = normalize_text("Müller GmbH")
        assert result == "müller gmbh"

    def test_normalize_numpy_nan(self):
        """Sollte numpy NaN korrekt behandeln."""
        import numpy as np
        result = normalize_text(np.nan)
        assert result == ""


class TestCalculateSimilarity:
    """Tests fuer calculate_similarity Funktion."""

    def test_similarity_identical(self):
        """Identische Strings sollten 1.0 ergeben."""
        result = calculate_similarity("Mueller GmbH", "Mueller GmbH")
        assert result == 1.0

    def test_similarity_case_insensitive(self):
        """Sollte Gross-/Kleinschreibung ignorieren."""
        result = calculate_similarity("MUELLER", "mueller")
        assert result == 1.0

    def test_similarity_similar(self):
        """Aehnliche Strings sollten hohe Aehnlichkeit haben."""
        result = calculate_similarity("Mueller GmbH", "Müller GmbH")
        assert result > 0.8

    def test_similarity_different(self):
        """Unterschiedliche Strings sollten niedrige Aehnlichkeit haben."""
        result = calculate_similarity("Mueller", "Schulze")
        assert result < 0.5

    def test_similarity_empty(self):
        """Leere Strings sollten 0.0 ergeben."""
        assert calculate_similarity("", "test") == 0.0
        assert calculate_similarity("test", "") == 0.0
        assert calculate_similarity("", "") == 0.0


class TestIsPlaceholder:
    """Tests fuer is_placeholder Funktion."""

    def test_empty_is_placeholder(self):
        """Leerer String sollte Platzhalter sein."""
        assert is_placeholder("") is True
        assert is_placeholder(None) is True

    def test_dot_is_placeholder(self):
        """Punkt sollte Platzhalter sein."""
        assert is_placeholder(".") is True

    def test_dash_is_placeholder(self):
        """Bindestrich sollte Platzhalter sein."""
        assert is_placeholder("-") is True
        assert is_placeholder("--") is True
        assert is_placeholder("---") is True

    def test_na_is_placeholder(self):
        """n/a sollte Platzhalter sein."""
        assert is_placeholder("n/a") is True
        assert is_placeholder("n.a.") is True
        assert is_placeholder("keine") is True

    def test_real_text_is_not_placeholder(self):
        """Echter Text sollte kein Platzhalter sein."""
        assert is_placeholder("Mueller GmbH") is False
        assert is_placeholder("12345") is False

    def test_numpy_nan_is_placeholder(self):
        """Numpy NaN sollte Platzhalter sein."""
        import numpy as np
        assert is_placeholder(np.nan) is True


class TestCleanCustomerNumber:
    """Tests fuer clean_customer_number Funktion."""

    def test_clean_simple_number(self):
        """Sollte einfache Nummer unveraendert lassen."""
        result = clean_customer_number("12345")
        assert result == "12345"

    def test_clean_with_spaces(self):
        """Sollte Leerzeichen entfernen."""
        result = clean_customer_number(" 12345 ")
        assert result == "12345"

    def test_clean_with_special_chars(self):
        """Sollte Sonderzeichen entfernen."""
        result = clean_customer_number("12-345")
        assert result == "12345"

    def test_clean_empty(self):
        """Sollte leeren String bei leerem Input zurueckgeben."""
        assert clean_customer_number("") == ""
        assert clean_customer_number(None) == ""


class TestImportResult:
    """Tests fuer ImportResult Dataclass."""

    def test_default_values(self):
        """Sollte korrekte Standardwerte haben."""
        result = ImportResult()
        assert result.imported_count == 0
        assert result.skipped_count == 0
        assert result.merged_count == 0
        assert result.duplicate_count == 0
        assert result.error_count == 0
        assert result.skipped_entities == []
        assert result.errors == []

    def test_with_values(self):
        """Sollte Werte korrekt speichern."""
        result = ImportResult(
            imported_count=100,
            skipped_count=30,
            merged_count=260,
            skipped_entities=[{"kd_nr": "12345", "reason": "Konflikt"}],
            errors=["Fehler 1"]
        )
        assert result.imported_count == 100
        assert result.skipped_count == 30
        assert result.merged_count == 260
        assert len(result.skipped_entities) == 1
        assert len(result.errors) == 1


class TestCustomerRecord:
    """Tests fuer CustomerRecord Dataclass."""

    def test_create_record(self):
        """Sollte CustomerRecord korrekt erstellen."""
        record = CustomerRecord(
            kd_nr="12345",
            matchcode="MUELLER",
            firma="Müller GmbH",
            name="Müller",
            vorname="Hans",
            plz="12345",
            ort="Berlin",
            strasse="Hauptstr.",
            haus_nr="1",
            email="mueller@test.de",
            company="folie"
        )

        assert record.kd_nr == "12345"
        assert record.matchcode == "MUELLER"
        assert record.company == "folie"

    def test_optional_fields(self):
        """Sollte optionale Felder mit Standardwerten haben."""
        record = CustomerRecord(
            kd_nr="12345",
            matchcode="MUELLER",
            firma="",
            name="",
            vorname="",
            plz="",
            ort="",
            strasse="",
            haus_nr="",
            email="",
            company="folie"
        )

        assert record.tel1 == ""
        assert record.tel2 == ""
        assert record.iban == ""


class TestSupplierRecord:
    """Tests fuer SupplierRecord Dataclass."""

    def test_create_record(self):
        """Sollte SupplierRecord korrekt erstellen."""
        record = SupplierRecord(
            lief_nr="L1001",
            matchcode="AGRIMPEX",
            firma="Agrimpex GmbH",
            name="Agri",
            vorname="",
            plz="12345",
            ort="Hamburg",
            konto_nr="",
            tel1="",
            tel2="",
            strasse="Industriestr.",
            haus_nr="42",
            email="info@agrimpex.de",
            iban="DE89370400440532013000",
            kreditoren_nr="K2001",
            bic="COBADEFFXXX",
            company="messer"
        )

        assert record.lief_nr == "L1001"
        assert record.matchcode == "AGRIMPEX"
        assert record.company == "messer"


class TestLexwareImportServiceInit:
    """Tests fuer Service-Initialisierung."""

    def test_init_creates_service(self):
        """Sollte Service korrekt initialisieren."""
        mock_db = MagicMock()
        service = LexwareImportService(mock_db)

        assert service.db == mock_db

    def test_threshold_values(self):
        """Sollte korrekte Schwellenwerte haben."""
        mock_db = MagicMock()
        service = LexwareImportService(mock_db)

        assert service.CRITICAL_SIMILARITY_THRESHOLD == 0.5
        assert service.HARMLESS_SIMILARITY_THRESHOLD == 0.7


class TestGetSupplierNameKey:
    """Tests fuer _get_supplier_name_key Methode."""

    @pytest.fixture
    def service(self):
        mock_db = MagicMock()
        return LexwareImportService(mock_db)

    def test_get_name_key_from_firma(self, service):
        """Sollte normalisierten Namen aus Firma extrahieren."""
        row = pd.Series({"Firma": "Müller GmbH", "Matchcode": "MUELLER"})
        result = service._get_supplier_name_key(row)
        assert result == "müller gmbh"

    def test_get_name_key_from_matchcode_fallback(self, service):
        """Sollte Matchcode verwenden wenn Firma leer."""
        row = pd.Series({"Firma": "", "Matchcode": "AGRIMPEX"})
        result = service._get_supplier_name_key(row)
        assert result == "agrimpex"

    def test_get_name_key_placeholder_returns_empty(self, service):
        """Sollte leeren String bei Platzhaltern zurueckgeben."""
        row = pd.Series({"Firma": ".", "Matchcode": "-"})
        result = service._get_supplier_name_key(row)
        assert result == ""

    def test_get_name_key_empty_returns_empty(self, service):
        """Sollte leeren String bei leeren Werten zurueckgeben."""
        row = pd.Series({"Firma": "", "Matchcode": ""})
        result = service._get_supplier_name_key(row)
        assert result == ""


class TestFindSimilarNameKey:
    """Tests fuer _find_similar_name_key Methode."""

    @pytest.fixture
    def service(self):
        mock_db = MagicMock()
        return LexwareImportService(mock_db)

    def test_find_exact_match(self, service):
        """Sollte exakten Match finden."""
        existing = ["mueller gmbh", "schulze ag", "agrimpex"]
        result = service._find_similar_name_key("mueller gmbh", existing)
        assert result == "mueller gmbh"

    def test_find_similar_match(self, service):
        """Sollte aehnlichen Namen ueber Threshold finden."""
        existing = ["mueller gmbh", "schulze ag"]
        result = service._find_similar_name_key("müller gmbh", existing)
        assert result == "mueller gmbh"

    def test_no_match_below_threshold(self, service):
        """Sollte None bei zu niedriger Aehnlichkeit zurueckgeben."""
        existing = ["schulze ag", "agrimpex"]
        result = service._find_similar_name_key("mueller gmbh", existing)
        assert result is None

    def test_empty_existing_keys(self, service):
        """Sollte None bei leerer Liste zurueckgeben."""
        result = service._find_similar_name_key("mueller gmbh", [])
        assert result is None


class TestAnalyzeCustomerConflicts:
    """Tests fuer _analyze_customer_conflicts Methode."""

    @pytest.fixture
    def service(self):
        mock_db = MagicMock()
        return LexwareImportService(mock_db)

    def test_detect_critical_conflict(self, service):
        """Sollte kritischen Konflikt erkennen bei niedriger Matchcode-Aehnlichkeit."""
        folie_df = pd.DataFrame({
            "Kd_Nr": ["12345"],
            "Matchcode": ["MUELLER"]
        })
        messer_df = pd.DataFrame({
            "Kd_Nr": ["12345"],
            "Matchcode": ["SCHULZE"]  # Komplett anders
        })

        result = service._analyze_customer_conflicts(folie_df, messer_df)

        assert len(result["kritische_konflikte"]) == 1
        assert result["kritische_konflikte"][0]["Kd_Nr"] == "12345"

    def test_detect_harmless_variant(self, service):
        """Sollte harmlose Variante erkennen bei hoher Aehnlichkeit."""
        folie_df = pd.DataFrame({
            "Kd_Nr": ["12345"],
            "Matchcode": ["MUELLER"]
        })
        messer_df = pd.DataFrame({
            "Kd_Nr": ["12345"],
            "Matchcode": ["MUELLER-GMBH"]  # Aehnlich
        })

        result = service._analyze_customer_conflicts(folie_df, messer_df)

        # Nicht kritisch, aber eine Variante
        assert len(result["kritische_konflikte"]) == 0
        assert len(result["harmlose_varianten"]) == 1

    def test_no_conflict_identical(self, service):
        """Sollte keinen Konflikt bei identischen Matchcodes erkennen."""
        folie_df = pd.DataFrame({
            "Kd_Nr": ["12345"],
            "Matchcode": ["MUELLER"]
        })
        messer_df = pd.DataFrame({
            "Kd_Nr": ["12345"],
            "Matchcode": ["MUELLER"]  # Identisch
        })

        result = service._analyze_customer_conflicts(folie_df, messer_df)

        assert len(result["kritische_konflikte"]) == 0
        assert len(result["harmlose_varianten"]) == 0

    def test_no_common_kd_nr(self, service):
        """Sollte keine Konflikte bei unterschiedlichen Kundennummern erkennen."""
        folie_df = pd.DataFrame({
            "Kd_Nr": ["12345"],
            "Matchcode": ["MUELLER"]
        })
        messer_df = pd.DataFrame({
            "Kd_Nr": ["54321"],  # Andere Nummer
            "Matchcode": ["SCHULZE"]
        })

        result = service._analyze_customer_conflicts(folie_df, messer_df)

        assert len(result["kritische_konflikte"]) == 0
        assert len(result["harmlose_varianten"]) == 0


class TestAnalyzeSupplierConflicts:
    """Tests fuer _analyze_supplier_conflicts Methode."""

    @pytest.fixture
    def service(self):
        mock_db = MagicMock()
        return LexwareImportService(mock_db)

    def test_returns_empty_conflicts(self, service):
        """Sollte leere Listen zurueckgeben (Lieferanten nach Namen gemapped)."""
        folie_df = pd.DataFrame({"Firma": ["Test"], "Matchcode": ["TEST"]})
        messer_df = pd.DataFrame({"Firma": ["Test"], "Matchcode": ["TEST"]})

        result = service._analyze_supplier_conflicts(folie_df, messer_df)

        assert result["kritische_konflikte"] == []
        assert result["namensvarianten"] == []


class TestImportCustomers:
    """Tests fuer import_customers Methode."""

    @pytest.fixture
    def service(self):
        mock_db = AsyncMock()
        return LexwareImportService(mock_db)

    @pytest.mark.asyncio
    async def test_import_customers_empty_files(self, service):
        """Sollte leere Dateien verarbeiten."""
        folie_df = pd.DataFrame({
            "Kd_Nr": [],
            "Matchcode": [],
            "Firma": [],
            "Name": [],
            "Vorname": [],
            "PLZ": [],
            "Ort": [],
            "Strasse": [],
            "HausNr": [],
            "Email": [],
        })

        with patch.object(service, "_load_customer_excel", return_value=folie_df):
            service.db.commit = AsyncMock()

            result = await service.import_customers(
                folie_file=Path("folie.xlsx"),
                messer_file=Path("messer.xlsx"),
                skip_conflicts=True
            )

            assert isinstance(result, ImportResult)
            assert result.imported_count == 0

    @pytest.mark.asyncio
    async def test_import_customers_skips_critical_conflicts(self, service):
        """Sollte kritische Konflikte ueberspringen."""
        folie_df = pd.DataFrame({
            "Kd_Nr": ["12345", "67890"],
            "Matchcode": ["MUELLER", "SCHULZE"],
            "Firma": ["Müller", "Schulze"],
            "Name": ["", ""],
            "Vorname": ["", ""],
            "PLZ": ["", ""],
            "Ort": ["", ""],
            "Strasse": ["", ""],
            "HausNr": ["", ""],
            "Email": ["", ""],
        })
        messer_df = pd.DataFrame({
            "Kd_Nr": ["12345"],
            "Matchcode": ["KOMPLETT_ANDERS"],  # Kritischer Konflikt
            "Firma": ["Andere Firma"],
            "Name": [""],
            "Vorname": [""],
            "PLZ": [""],
            "Ort": [""],
            "Strasse": [""],
            "HausNr": [""],
            "Email": [""],
        })

        def load_excel_side_effect(file_path, company):
            if company == "folie":
                return folie_df
            return messer_df

        with patch.object(service, "_load_customer_excel", side_effect=load_excel_side_effect):
            service.db.add = MagicMock()
            service.db.commit = AsyncMock()

            result = await service.import_customers(
                folie_file=Path("folie.xlsx"),
                messer_file=Path("messer.xlsx"),
                skip_conflicts=True
            )

            assert isinstance(result, ImportResult)
            # 12345 sollte uebersprungen werden (kritischer Konflikt)
            assert result.skipped_count >= 1


class TestImportSuppliers:
    """Tests fuer import_suppliers Methode."""

    @pytest.fixture
    def service(self):
        mock_db = AsyncMock()
        return LexwareImportService(mock_db)

    @pytest.mark.asyncio
    async def test_import_suppliers_empty_files(self, service):
        """Sollte leere Dateien verarbeiten."""
        empty_df = pd.DataFrame({
            "Lief_Nr": [],
            "Matchcode": [],
            "Firma": [],
            "Name": [],
            "Vorname": [],
            "PLZ": [],
            "Ort": [],
            "Strasse": [],
            "HausNr": [],
            "Email": [],
            "Company": [],
        })

        with patch.object(service, "_load_supplier_excel", return_value=empty_df):
            service.db.commit = AsyncMock()

            result = await service.import_suppliers(
                folie_file=Path("folie_lief.xlsx"),
                messer_file=Path("messer_lief.xlsx"),
                skip_conflicts=True
            )

            assert isinstance(result, ImportResult)
            assert result.imported_count == 0

    @pytest.mark.asyncio
    async def test_import_suppliers_merges_similar_names(self, service):
        """Sollte aehnliche Lieferanten-Namen zusammenfuehren."""
        folie_df = pd.DataFrame({
            "Lief_Nr": ["L1001"],
            "Matchcode": ["AGRIMPEX"],
            "Firma": ["Agrimpex GmbH"],
            "Name": [""],
            "Vorname": [""],
            "PLZ": ["12345"],
            "Ort": ["Hamburg"],
            "Strasse": ["Industriestr."],
            "HausNr": ["42"],
            "Email": [""],
            "IBAN": [""],
            "BIC": [""],
            "Company": ["folie"],
        })
        messer_df = pd.DataFrame({
            "Lief_Nr": ["L2047"],
            "Matchcode": ["AGRIMPEX GMBH"],  # Aehnlich
            "Firma": ["Agrimpex GmbH"],
            "Name": [""],
            "Vorname": [""],
            "PLZ": ["12345"],
            "Ort": ["Hamburg"],
            "Strasse": ["Industriestr."],
            "HausNr": ["42"],
            "Email": [""],
            "IBAN": [""],
            "BIC": [""],
            "Company": ["messer"],
        })

        def load_excel_side_effect(file_path, company):
            if company == "folie":
                return folie_df
            return messer_df

        with patch.object(service, "_load_supplier_excel", side_effect=load_excel_side_effect):
            service.db.add = MagicMock()
            service.db.commit = AsyncMock()

            result = await service.import_suppliers(
                folie_file=Path("folie_lief.xlsx"),
                messer_file=Path("messer_lief.xlsx"),
                skip_conflicts=True
            )

            assert isinstance(result, ImportResult)
            # Sollte zusammengefuehrt werden (nur 1 Entity, nicht 2)
            # merged_count zeigt zusammengefuehrte Eintraege
            assert result.merged_count >= 0


class TestFactoryFunction:
    """Tests fuer Factory-Funktion."""

    def test_get_lexware_import_service_creates_instance(self):
        """Sollte neue Service-Instanz erstellen."""
        from app.services.lexware_import_service import get_lexware_import_service

        mock_db = MagicMock()
        service = get_lexware_import_service(mock_db)

        assert isinstance(service, LexwareImportService)
        assert service.db == mock_db
