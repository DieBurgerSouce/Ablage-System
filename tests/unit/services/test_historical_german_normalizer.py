# -*- coding: utf-8 -*-
"""
Unit tests for Historical German Normalizer Service.

Tests Pre-1996 reform, 19th century Th->T,
C->K/Z mappings, ph->f, and Fraktur character normalization.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.services.historical_german_normalizer import (
    HistoricalGermanNormalizer,
    NormalizationResult,
    NormalizationEra,
    normalize_historical,
    normalize_fraktur,
    is_historical_text,
    get_historical_normalizer,
)


@pytest.mark.unit
class TestNormalizationResult:
    """Test NormalizationResult dataclass."""

    def test_result_with_changes(self):
        """Test result with changes."""
        result = NormalizationResult(
            original="daß",
            normalized="dass",
            changes=[("daß", "dass", 0)],
            era_detected=NormalizationEra.PRE_1996,
            confidence=0.9,
        )

        assert result.was_changed
        assert result.change_count == 1
        assert result.era_detected == NormalizationEra.PRE_1996

    def test_result_without_changes(self):
        """Test result without changes."""
        result = NormalizationResult(
            original="modern",
            normalized="modern",
            changes=[],
            era_detected=NormalizationEra.MODERN,
            confidence=1.0,
        )

        assert not result.was_changed
        assert result.change_count == 0


@pytest.mark.unit
class TestPre1996Normalization:
    """Test Pre-1996 reform normalization (ß->ss)."""

    def setup_method(self):
        """Setup before each test."""
        self.normalizer = HistoricalGermanNormalizer()

    def test_dass_normalization(self):
        """Test daß -> dass normalization."""
        result = self.normalizer.normalize("Er sagte, daß er kommt.")

        assert "dass" in result.normalized
        assert "daß" not in result.normalized
        assert result.was_changed

    def test_muss_normalization(self):
        """Test muß -> muss normalization."""
        result = self.normalizer.normalize("Er muß gehen.")

        assert "muss" in result.normalized
        assert "muß" not in result.normalized

    def test_schloss_normalization(self):
        """Test Schloß -> Schloss normalization."""
        result = self.normalizer.normalize("Das Schloß ist alt.")

        assert "Schloss" in result.normalized

    def test_fluss_normalization(self):
        """Test Fluß -> Fluss normalization."""
        result = self.normalizer.normalize("Der Fluß fließt.")

        assert "Fluss" in result.normalized

    def test_wusste_normalization(self):
        """Test wußte -> wusste normalization."""
        result = self.normalizer.normalize("Ich wußte es nicht.")

        assert "wusste" in result.normalized

    def test_preserve_correct_eszett(self):
        """Test that correct ß usage is preserved."""
        # After long vowels, ß remains
        result = self.normalizer.normalize("Die Straße ist lang.")

        # Straße should remain unchanged (not in mapping)
        assert "Straße" in result.normalized or "straße" in result.normalized.lower()

    @pytest.mark.parametrize(
        "old,new",
        [
            ("daß", "dass"),
            ("muß", "muss"),
            ("Schloß", "Schloss"),
            ("Fluß", "Fluss"),
            ("Kuß", "Kuss"),
            ("Nuß", "Nuss"),
            ("Haß", "Hass"),
            ("naß", "nass"),
            ("blaß", "blass"),
            ("Genuß", "Genuss"),
        ],
    )
    def test_pre_1996_mappings(self, old: str, new: str):
        """Test various Pre-1996 mappings."""
        result = self.normalizer.normalize(old)

        assert new in result.normalized


@pytest.mark.unit
class TestThNormalization:
    """Test 19th century Th->T normalization."""

    def setup_method(self):
        """Setup before each test."""
        self.normalizer = HistoricalGermanNormalizer()

    def test_thuer_to_tuer(self):
        """Test Thür -> Tür normalization."""
        result = self.normalizer.normalize("Die Thür ist offen.")

        assert "Tür" in result.normalized

    def test_thor_to_tor(self):
        """Test Thor -> Tor normalization."""
        result = self.normalizer.normalize("Das große Thor.")

        assert "Tor" in result.normalized

    def test_theil_to_teil(self):
        """Test Theil -> Teil normalization."""
        result = self.normalizer.normalize("Ein Theil davon.")

        assert "Teil" in result.normalized

    def test_thier_to_tier(self):
        """Test Thier -> Tier normalization."""
        result = self.normalizer.normalize("Das wilde Thier.")

        assert "Tier" in result.normalized

    def test_preserve_thron(self):
        """Test that Thron is preserved (Greek origin)."""
        result = self.normalizer.normalize("Der Thron des Königs.")

        # Thron should remain (marked as preserved)
        assert "Thron" in result.normalized

    def test_muth_to_mut(self):
        """Test Muth -> Mut normalization."""
        result = self.normalizer.normalize("Er hat Muth.")

        assert "Mut" in result.normalized

    @pytest.mark.parametrize(
        "old,new",
        [
            ("Thür", "Tür"),
            ("Thor", "Tor"),
            ("Theil", "Teil"),
            ("Thier", "Tier"),
            ("Thal", "Tal"),
            ("thun", "tun"),
            ("Muth", "Mut"),
            ("Wuth", "Wut"),
            ("Rath", "Rat"),
            ("Noth", "Not"),
            ("Werth", "Wert"),
        ],
    )
    def test_th_mappings(self, old: str, new: str):
        """Test various Th->T mappings."""
        result = self.normalizer.normalize(old)

        assert new in result.normalized


@pytest.mark.unit
class TestCNormalization:
    """Test C->K/Z normalization."""

    def setup_method(self):
        """Setup before each test."""
        self.normalizer = HistoricalGermanNormalizer()

    def test_curs_to_kurs(self):
        """Test Curs -> Kurs normalization."""
        result = self.normalizer.normalize("Der Curs steigt.")

        assert "Kurs" in result.normalized

    def test_circus_to_zirkus(self):
        """Test Circus -> Zirkus normalization."""
        result = self.normalizer.normalize("Im Circus.")

        assert "Zirkus" in result.normalized

    def test_caffee_to_kaffee(self):
        """Test Caffee -> Kaffee normalization."""
        result = self.normalizer.normalize("Eine Tasse Caffee.")

        assert "Kaffee" in result.normalized

    def test_classe_to_klasse(self):
        """Test Classe -> Klasse normalization."""
        result = self.normalizer.normalize("Die erste Classe.")

        assert "Klasse" in result.normalized

    @pytest.mark.parametrize(
        "old,new",
        [
            ("Curs", "Kurs"),
            ("Circus", "Zirkus"),
            ("Conto", "Konto"),
            ("Credit", "Kredit"),
            ("Caffee", "Kaffee"),
            ("Classe", "Klasse"),
            ("Cultur", "Kultur"),
            ("Concert", "Konzert"),
        ],
    )
    def test_c_mappings(self, old: str, new: str):
        """Test various C->K/Z mappings."""
        result = self.normalizer.normalize(old)

        assert new in result.normalized


@pytest.mark.unit
class TestPhNormalization:
    """Test ph->f normalization."""

    def setup_method(self):
        """Setup before each test."""
        self.normalizer = HistoricalGermanNormalizer()

    def test_telephon_to_telefon(self):
        """Test Telephon -> Telefon normalization."""
        result = self.normalizer.normalize("Das Telephon klingelt.")

        assert "Telefon" in result.normalized

    def test_photograph_to_fotograf(self):
        """Test Photograph -> Fotograf normalization."""
        result = self.normalizer.normalize("Der Photograph arbeitet.")

        assert "Fotograf" in result.normalized

    def test_graphik_to_grafik(self):
        """Test Graphik -> Grafik normalization."""
        result = self.normalizer.normalize("Schöne Graphik.")

        assert "Grafik" in result.normalized

    @pytest.mark.parametrize(
        "old,new",
        [
            ("Telephon", "Telefon"),
            ("Photograph", "Fotograf"),
            ("Photographie", "Fotografie"),
            ("Graphik", "Grafik"),
            ("Delphin", "Delfin"),
            ("Geographie", "Geografie"),
        ],
    )
    def test_ph_mappings(self, old: str, new: str):
        """Test various ph->f mappings."""
        result = self.normalizer.normalize(old)

        assert new in result.normalized


@pytest.mark.unit
class TestFrakturNormalization:
    """Test Fraktur-specific character normalization."""

    def setup_method(self):
        """Setup before each test."""
        self.normalizer = HistoricalGermanNormalizer()

    def test_long_s_normalization(self):
        """Test ſ (long s) -> s normalization."""
        result = self.normalizer.normalize("daſs")  # with long s

        assert "dass" in result.normalized or "daſs" not in result.normalized

    def test_fraktur_only_normalization(self):
        """Test Fraktur-only normalization."""
        text = "Der groſſe Fluſs"  # with long s
        result = self.normalizer.normalize_fraktur_only(text)

        # All long s should be converted
        assert "ſ" not in result

    def test_round_r_normalization(self):
        """Test ꝛ (r rotunda) -> r normalization."""
        result = self.normalizer.normalize("Liebeꝛ")  # with round r

        # Should be converted to normal r
        assert "ꝛ" not in result.normalized


@pytest.mark.unit
class TestEraDetection:
    """Test historical era detection."""

    def setup_method(self):
        """Setup before each test."""
        self.normalizer = HistoricalGermanNormalizer()

    def test_detect_pre_1996(self):
        """Test detection of Pre-1996 text."""
        text = "Er sagte, daß er kommen muß."
        result = self.normalizer.normalize(text)

        assert result.era_detected == NormalizationEra.PRE_1996

    def test_detect_nineteenth_century(self):
        """Test detection of 19th century text."""
        text = "Die Thür des Thales."
        result = self.normalizer.normalize(text)

        assert result.era_detected == NormalizationEra.NINETEENTH

    def test_detect_fraktur(self):
        """Test detection of Fraktur text."""
        text = "Das iſt ein Teſt."  # with long s
        result = self.normalizer.normalize(text)

        assert result.era_detected == NormalizationEra.FRAKTUR

    def test_detect_modern(self):
        """Test detection of modern text."""
        text = "Das ist ein moderner Text."
        result = self.normalizer.normalize(text)

        assert result.era_detected == NormalizationEra.MODERN


@pytest.mark.unit
class TestPreservedWords:
    """Test words that should NOT be normalized."""

    def setup_method(self):
        """Setup before each test."""
        self.normalizer = HistoricalGermanNormalizer()

    def test_preserve_goethe(self):
        """Test that Goethe is preserved."""
        result = self.normalizer.normalize("Johann Wolfgang von Goethe")

        assert "Goethe" in result.normalized

    def test_preserve_theater(self):
        """Test that Theater is preserved (Greek)."""
        result = self.normalizer.normalize("Das Theater ist voll.")

        assert "Theater" in result.normalized

    def test_preserve_thema(self):
        """Test that Thema is preserved (Greek)."""
        result = self.normalizer.normalize("Das Thema ist interessant.")

        assert "Thema" in result.normalized

    def test_preserve_philosophie(self):
        """Test that Philosophie is preserved."""
        result = self.normalizer.normalize("Die Philosophie ist komplex.")

        assert "Philosophie" in result.normalized


@pytest.mark.unit
class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_normalize_historical(self):
        """Test normalize_historical function."""
        result = normalize_historical("Er sagte, daß er kommt.")

        assert isinstance(result, NormalizationResult)
        assert "dass" in result.normalized

    def test_normalize_fraktur(self):
        """Test normalize_fraktur function."""
        result = normalize_fraktur("Teſt")  # with long s

        assert "ſ" not in result

    def test_is_historical_text(self):
        """Test is_historical_text function."""
        # Historical text
        assert is_historical_text("Er muß zur Thür gehen.")

        # Modern text
        assert not is_historical_text("Er muss zur Tür gehen.")

    def test_get_historical_normalizer_singleton(self):
        """Test singleton pattern."""
        normalizer1 = get_historical_normalizer()
        normalizer2 = get_historical_normalizer()

        assert normalizer1 is normalizer2


@pytest.mark.unit
class TestConfigurableNormalization:
    """Test configurable normalization options."""

    def test_disable_pre_1996(self):
        """Test disabling Pre-1996 normalization."""
        normalizer = HistoricalGermanNormalizer(enable_pre_1996=False)

        result = normalizer.normalize("daß")

        # Should NOT be normalized
        assert "daß" in result.normalized

    def test_disable_th_normalization(self):
        """Test disabling Th->T normalization."""
        normalizer = HistoricalGermanNormalizer(enable_th_normalization=False)

        result = normalizer.normalize("Thür")

        # Should NOT be normalized
        assert "Thür" in result.normalized

    def test_disable_c_normalization(self):
        """Test disabling C->K/Z normalization."""
        normalizer = HistoricalGermanNormalizer(enable_c_normalization=False)

        result = normalizer.normalize("Circus")

        # Should NOT be normalized
        assert "Circus" in result.normalized

    def test_disable_ph_normalization(self):
        """Test disabling ph->f normalization."""
        normalizer = HistoricalGermanNormalizer(enable_ph_normalization=False)

        result = normalizer.normalize("Telephon")

        # Should NOT be normalized
        assert "Telephon" in result.normalized

    def test_disable_fraktur(self):
        """Test disabling Fraktur normalization."""
        normalizer = HistoricalGermanNormalizer(enable_fraktur=False)

        result = normalizer.normalize("Teſt")  # with long s

        # Long s should remain
        assert "ſ" in result.normalized


@pytest.mark.unit
class TestCasePreservation:
    """Test case preservation during normalization."""

    def setup_method(self):
        """Setup before each test."""
        self.normalizer = HistoricalGermanNormalizer()

    def test_uppercase_preservation(self):
        """Test that uppercase is preserved."""
        result = self.normalizer.normalize("DASS")

        # Should be normalized but stay uppercase
        # Note: this depends on mapping having DASS or case handling
        assert result.normalized.isupper() or "DASS" in result.normalized or "DASS" == result.normalized

    def test_mixed_case_preservation(self):
        """Test mixed case text."""
        result = self.normalizer.normalize("Das Schloß ist groß.")

        assert "Schloss" in result.normalized  # Capital preserved
