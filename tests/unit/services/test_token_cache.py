# -*- coding: utf-8 -*-
"""
Unit Tests fuer Token-Level Caching mit LRU.

Testet das Token-Caching System:
- LRU Eviction
- Fingerprint-Berechnung
- TTL-basierte Expiration
- Word Frequency Cache
"""

import pytest
import time
from app.services.token_cache import (
    CacheEntry,
    CacheStats,
    LRUTokenCache,
    WordFrequencyCache,
    get_token_cache,
    get_word_cache,
)


class TestCacheEntry:
    """Tests fuer CacheEntry Dataclass."""

    def test_create_entry(self):
        """CacheEntry wird korrekt erstellt."""
        entry = CacheEntry(
            value="test",
            confidence=0.95,
            backend="deepseek"
        )
        assert entry.value == "test"
        assert entry.confidence == 0.95
        assert entry.backend == "deepseek"
        assert entry.access_count == 0
        assert entry.created_at > 0

    def test_entry_timestamps(self):
        """Timestamps werden automatisch gesetzt."""
        entry = CacheEntry(value="test", confidence=0.9, backend="got_ocr")
        assert entry.created_at <= time.time()
        assert entry.last_accessed <= time.time()


class TestCacheStats:
    """Tests fuer CacheStats."""

    def test_initial_stats(self):
        """Initiale Statistiken sind 0."""
        stats = CacheStats()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.evictions == 0
        assert stats.entries == 0

    def test_hit_rate_calculation(self):
        """Hit-Rate wird korrekt berechnet."""
        stats = CacheStats(hits=80, misses=20)
        assert stats.hit_rate == 0.8

    def test_hit_rate_zero_total(self):
        """Hit-Rate ist 0 bei leeren Stats."""
        stats = CacheStats()
        assert stats.hit_rate == 0.0


class TestLRUTokenCache:
    """Tests fuer LRUTokenCache."""

    @pytest.fixture
    def cache(self):
        """Erstelle frischen Cache fuer jeden Test."""
        return LRUTokenCache(max_entries=10, max_memory_mb=1, ttl_seconds=60)

    def test_init(self, cache):
        """Cache initialisiert korrekt."""
        assert cache._max_entries == 10
        assert cache._ttl_seconds == 60
        assert len(cache._cache) == 0

    def test_put_and_get(self, cache):
        """Einfaches Put und Get funktioniert."""
        image_data = b"test_image_data_1234567890"

        # Put
        result = cache.put(
            image_data=image_data,
            text="Hallo Welt",
            confidence=0.95,
            backend="deepseek"
        )
        assert result is True

        # Get
        cached = cache.get(image_data)
        assert cached is not None
        text, confidence, backend = cached
        assert text == "Hallo Welt"
        assert confidence == 0.95
        assert backend == "deepseek"

    def test_cache_miss(self, cache):
        """Cache Miss gibt None zurueck."""
        result = cache.get(b"nonexistent_image")
        assert result is None

    def test_low_confidence_rejected(self, cache):
        """Niedrige Confidence wird nicht gecacht."""
        result = cache.put(
            image_data=b"test_image",
            text="low confidence text",
            confidence=0.3,
            backend="test"
        )
        assert result is False

        cached = cache.get(b"test_image")
        assert cached is None

    def test_empty_text_rejected(self, cache):
        """Leerer Text wird nicht gecacht."""
        result = cache.put(
            image_data=b"test_image",
            text="",
            confidence=0.95,
            backend="test"
        )
        assert result is False

    def test_whitespace_only_rejected(self, cache):
        """Nur Whitespace wird nicht gecacht."""
        result = cache.put(
            image_data=b"test_image",
            text="   ",
            confidence=0.95,
            backend="test"
        )
        assert result is False

    def test_lru_eviction(self, cache):
        """LRU Eviction funktioniert bei vollem Cache."""
        # Fuelle Cache
        for i in range(10):
            cache.put(
                image_data=f"image_{i}".encode(),
                text=f"text_{i}",
                confidence=0.9,
                backend="test"
            )

        # Fuege weiteres Element hinzu (sollte aeltestes entfernen)
        cache.put(
            image_data=b"image_new",
            text="new_text",
            confidence=0.9,
            backend="test"
        )

        # Erstes Element sollte entfernt worden sein (LRU)
        assert cache.get(b"image_0") is None

        # Neues Element sollte da sein
        assert cache.get(b"image_new") is not None

    def test_lru_access_updates_order(self, cache):
        """Zugriff aktualisiert LRU-Reihenfolge."""
        # Fuege 3 Elemente hinzu
        for i in range(3):
            cache.put(
                image_data=f"image_{i}".encode(),
                text=f"text_{i}",
                confidence=0.9,
                backend="test"
            )

        # Greife auf erstes Element zu (macht es "neu")
        cache.get(b"image_0")

        # Fuelle Cache auf
        for i in range(10, 18):
            cache.put(
                image_data=f"image_{i}".encode(),
                text=f"text_{i}",
                confidence=0.9,
                backend="test"
            )

        # Element 0 sollte noch da sein (wegen Zugriff)
        assert cache.get(b"image_0") is not None

        # Element 1 sollte entfernt worden sein (kein Zugriff)
        assert cache.get(b"image_1") is None

    def test_region_specific_caching(self, cache):
        """Verschiedene Regionen werden separat gecacht."""
        image_data = b"same_image_data"

        # Zwei verschiedene Regionen
        cache.put(
            image_data=image_data,
            text="Region 1",
            confidence=0.9,
            backend="test",
            region=(0, 0, 100, 100)
        )

        cache.put(
            image_data=image_data,
            text="Region 2",
            confidence=0.9,
            backend="test",
            region=(100, 0, 100, 100)
        )

        # Beide sollten getrennt abrufbar sein
        result1 = cache.get(image_data, region=(0, 0, 100, 100))
        result2 = cache.get(image_data, region=(100, 0, 100, 100))

        assert result1 is not None
        assert result2 is not None
        assert result1[0] == "Region 1"
        assert result2[0] == "Region 2"

    def test_get_stats(self, cache):
        """Statistiken werden korrekt erfasst."""
        # Einige Operationen
        cache.put(b"img1", "text1", 0.9, "test")
        cache.put(b"img2", "text2", 0.9, "test")
        cache.get(b"img1")  # Hit
        cache.get(b"img3")  # Miss

        stats = cache.get_stats()

        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 50.0
        assert stats["entries"] == 2

    def test_clear(self, cache):
        """Clear entfernt alle Eintraege."""
        cache.put(b"img1", "text1", 0.9, "test")
        cache.put(b"img2", "text2", 0.9, "test")

        count = cache.clear()

        assert count == 2
        assert cache.get(b"img1") is None
        assert cache.get(b"img2") is None
        assert cache.get_stats()["entries"] == 0

    def test_ttl_expiration(self):
        """TTL-abgelaufene Eintraege werden entfernt."""
        cache = LRUTokenCache(max_entries=10, ttl_seconds=1)

        cache.put(b"img", "text", 0.9, "test")
        assert cache.get(b"img") is not None

        # Warte auf Ablauf
        time.sleep(1.5)

        # Sollte abgelaufen sein
        assert cache.get(b"img") is None

    def test_warm_up(self, cache):
        """Warm-up fuegt mehrere Eintraege hinzu."""
        entries = [
            {"image_data": b"img1", "text": "text1", "confidence": 0.9, "backend": "test"},
            {"image_data": b"img2", "text": "text2", "confidence": 0.9, "backend": "test"},
            {"image_data": b"img3", "text": "text3", "confidence": 0.5, "backend": "test"},  # Low conf
        ]

        added = cache.warm_up(entries)

        assert added == 2  # Nur 2 mit ausreichend Confidence
        assert cache.get(b"img1") is not None
        assert cache.get(b"img2") is not None


class TestWordFrequencyCache:
    """Tests fuer WordFrequencyCache."""

    @pytest.fixture
    def word_cache(self):
        """Erstelle frischen Word Cache."""
        return WordFrequencyCache()

    def test_init_with_common_words(self, word_cache):
        """Cache ist mit haeufigen Woertern initialisiert."""
        assert word_cache.is_common_word("der")
        assert word_cache.is_common_word("die")
        assert word_cache.is_common_word("und")

    def test_common_word_case_insensitive(self, word_cache):
        """Wortsuche ist case-insensitive."""
        assert word_cache.is_common_word("Der")
        assert word_cache.is_common_word("DER")
        assert word_cache.is_common_word("der")

    def test_record_word(self, word_cache):
        """Wort-Vorkommen werden erfasst."""
        word_cache.record_word("neueswort")
        word_cache.record_word("neueswort")
        word_cache.record_word("neueswort")

        assert word_cache.get_frequency("neueswort") == 3

    def test_record_text(self, word_cache):
        """Text-Verarbeitung erfasst alle Woerter."""
        text = "Dies ist ein Test mit mehreren Woertern"
        count = word_cache.record_text(text)

        assert count > 0
        assert word_cache.get_frequency("test") > 0

    def test_short_words_ignored(self, word_cache):
        """Kurze Woerter werden ignoriert."""
        word_cache.record_word("a")
        assert word_cache.get_frequency("a") == 0

    def test_get_top_words(self, word_cache):
        """Top-Woerter werden korrekt sortiert."""
        # Erfasse einige Woerter mit verschiedenen Haeufigkeiten
        for _ in range(50):
            word_cache.record_word("haeufig")
        for _ in range(20):
            word_cache.record_word("mittel")
        for _ in range(5):
            word_cache.record_word("selten")

        top = word_cache.get_top_words(n=5)

        # Haeufigste zuerst
        assert len(top) >= 3
        # Common words haben initial 100, so "haeufig" mit 50 ist nicht ganz oben
        words = [w for w, _ in top]
        # Die Top-Woerter sollten haeufige deutsche Woerter sein
        assert any(w in WordFrequencyCache.COMMON_GERMAN_WORDS for w in words[:3])

    def test_suggest_correction(self, word_cache):
        """Korrekturvorschlaege fuer aehnliche Woerter."""
        # "dre" sollte zu einem haeufigen Wort korrigiert werden (der oder die)
        correction = word_cache.suggest_correction("dre")
        # Beide sind valid, da beide Edit-Distanz 1 haben
        assert correction in ("der", "die")

    def test_no_correction_needed(self, word_cache):
        """Keine Korrektur fuer bekannte Woerter."""
        correction = word_cache.suggest_correction("der")
        assert correction is None

    def test_suggest_correction_max_distance(self, word_cache):
        """Korrektur respektiert maximale Distanz."""
        # "abcdefg" ist zu weit entfernt von allen Woertern
        correction = word_cache.suggest_correction("abcdefghij", max_distance=1)
        assert correction is None


class TestSingletons:
    """Tests fuer Singleton-Funktionen."""

    def test_get_token_cache_singleton(self):
        """Token Cache ist Singleton."""
        cache1 = get_token_cache()
        cache2 = get_token_cache()
        assert cache1 is cache2

    def test_get_word_cache_singleton(self):
        """Word Cache ist Singleton."""
        cache1 = get_word_cache()
        cache2 = get_word_cache()
        assert cache1 is cache2


class TestFingerprinting:
    """Tests fuer Fingerprint-Berechnung."""

    def test_same_image_same_fingerprint(self):
        """Gleiche Bilder erzeugen gleichen Fingerprint."""
        cache = LRUTokenCache()
        image = b"same_image_content" * 100

        fp1 = cache._compute_fingerprint(image)
        fp2 = cache._compute_fingerprint(image)

        assert fp1 == fp2

    def test_different_images_different_fingerprints(self):
        """Verschiedene Bilder erzeugen verschiedene Fingerprints."""
        cache = LRUTokenCache()

        fp1 = cache._compute_fingerprint(b"image_a" * 100)
        fp2 = cache._compute_fingerprint(b"image_b" * 100)

        assert fp1 != fp2

    def test_same_image_different_regions(self):
        """Gleiche Bilder mit verschiedenen Regionen erzeugen verschiedene Fingerprints."""
        cache = LRUTokenCache()
        image = b"image_content" * 100

        fp1 = cache._compute_fingerprint(image, region=(0, 0, 100, 100))
        fp2 = cache._compute_fingerprint(image, region=(100, 100, 100, 100))

        assert fp1 != fp2


class TestIntegration:
    """Integration-Tests fuer Token Caching."""

    def test_batch_processing_simulation(self):
        """Simuliere Batch-Processing mit Cache."""
        cache = LRUTokenCache(max_entries=1000)

        # Simuliere 100 Dokumente, viele mit aehnlichem Inhalt
        images = [f"document_{i % 20}".encode() * 50 for i in range(100)]
        texts = [f"Text fuer Dokument {i % 20}" for i in range(100)]

        # Erste Runde: Alle cachen
        for img, text in zip(images, texts):
            cache.put(img, text, 0.9, "deepseek")

        # Zweite Runde: Viele sollten Hits sein
        hits = 0
        for img in images:
            if cache.get(img):
                hits += 1

        # Da wir nur 20 unique Images haben, sollten alle Hits sein
        assert hits == 100

        stats = cache.get_stats()
        assert stats["hit_rate"] > 90.0

    def test_word_cache_ocr_workflow(self):
        """Simuliere OCR-Workflow mit Word Cache."""
        word_cache = WordFrequencyCache()

        # OCR-Ergebnisse verarbeiten
        ocr_texts = [
            "Die Rechnung wurde am Freitag erstellt",
            "Der Betrag ist bis zum Freitag faellig",
            "Sehr geehrte Damen und Herren",
        ]

        for text in ocr_texts:
            word_cache.record_text(text)

        # "Freitag" sollte haeufiger sein
        assert word_cache.get_frequency("freitag") >= 2

        # Korrektur sollte funktionieren
        correction = word_cache.suggest_correction("Freiatg")  # Typo
        # Might be "freitag" if close enough
        assert correction is None or correction == "freitag"
