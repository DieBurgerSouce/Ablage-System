# -*- coding: utf-8 -*-
"""
Unit Tests fuer TranslationService.

Testet die Uebersetzungsfunktionalitaet fuer mehrsprachige Dokumentenextraktion:
- Skip von de/en Texten (keine Uebersetzung noetig)
- Uebersetzung von anderen Sprachen nach Deutsch
- Caching-Verhalten
- Provider-Konfidenz
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.translation_service import (
    TranslationService,
    TranslationProvider,
    TranslationResult,
    get_translation_service,
    reset_translation_service,
)


class TestTranslationProvider:
    """Tests fuer TranslationProvider Enum."""

    def test_provider_values(self) -> None:
        """Provider-Werte sollten korrekt sein."""
        assert TranslationProvider.ARGOS.value == "argos"
        assert TranslationProvider.LIBRETRANSLATE.value == "libretranslate"
        assert TranslationProvider.DEEPL.value == "deepl"
        assert TranslationProvider.DISABLED.value == "disabled"

    def test_provider_from_string(self) -> None:
        """Provider sollte aus String erstellt werden koennen."""
        assert TranslationProvider("argos") == TranslationProvider.ARGOS
        assert TranslationProvider("disabled") == TranslationProvider.DISABLED


class TestTranslationResult:
    """Tests fuer TranslationResult Dataclass."""

    def test_translation_result_creation(self) -> None:
        """TranslationResult sollte korrekt erstellt werden."""
        result = TranslationResult(
            original_text="Счёт-фактура",
            translated_text="Rechnung",
            source_language="ru",
            target_language="de",
            provider=TranslationProvider.ARGOS,
            confidence=0.85,
            duration_ms=150,
            was_translated=True,
        )

        assert result.original_text == "Счёт-фактура"
        assert result.translated_text == "Rechnung"
        assert result.source_language == "ru"
        assert result.target_language == "de"
        assert result.provider == TranslationProvider.ARGOS
        assert result.confidence == 0.85
        assert result.duration_ms == 150
        assert result.was_translated is True


class TestTranslationService:
    """Tests fuer TranslationService."""

    @pytest.fixture
    def service(self) -> TranslationService:
        """Erstellt eine frische Service-Instanz mit disabled Provider."""
        return TranslationService(provider=TranslationProvider.DISABLED)

    @pytest.fixture
    def argos_service(self) -> TranslationService:
        """Erstellt eine Service-Instanz mit Argos Provider (fuer Mocking)."""
        return TranslationService(provider=TranslationProvider.ARGOS)

    # =========================================================================
    # is_translation_needed Tests
    # =========================================================================

    def test_translation_not_needed_for_german(self, service: TranslationService) -> None:
        """Deutsche Texte benoetigen keine Uebersetzung."""
        assert service.is_translation_needed("de") is False

    def test_translation_not_needed_for_english(self, service: TranslationService) -> None:
        """Englische Texte benoetigen keine Uebersetzung."""
        assert service.is_translation_needed("en") is False

    def test_translation_needed_for_russian(self, service: TranslationService) -> None:
        """Russische Texte benoetigen Uebersetzung."""
        # Bei disabled Provider ist translation_needed immer False
        disabled_service = TranslationService(provider=TranslationProvider.DISABLED)
        assert disabled_service.is_translation_needed("ru") is False

        # Bei aktivem Provider sollte es True sein
        argos_service = TranslationService(provider=TranslationProvider.ARGOS)
        assert argos_service.is_translation_needed("ru") is True

    def test_translation_needed_for_polish(self) -> None:
        """Polnische Texte benoetigen Uebersetzung."""
        service = TranslationService(provider=TranslationProvider.ARGOS)
        assert service.is_translation_needed("pl") is True

    def test_translation_needed_for_ukrainian(self) -> None:
        """Ukrainische Texte benoetigen Uebersetzung."""
        service = TranslationService(provider=TranslationProvider.ARGOS)
        assert service.is_translation_needed("uk") is True

    def test_translation_not_needed_for_none(self) -> None:
        """None-Sprache benoetigt keine Uebersetzung."""
        service = TranslationService(provider=TranslationProvider.ARGOS)
        assert service.is_translation_needed(None) is False

    def test_translation_not_needed_for_unknown(self) -> None:
        """Unknown-Sprache benoetigt keine Uebersetzung."""
        service = TranslationService(provider=TranslationProvider.ARGOS)
        assert service.is_translation_needed("unknown") is False

    # =========================================================================
    # translate_for_extraction Tests - Skip Cases
    # =========================================================================

    @pytest.mark.asyncio
    async def test_skip_german_text(self, service: TranslationService) -> None:
        """Deutsche Texte werden nicht uebersetzt."""
        result = await service.translate_for_extraction(
            text="Rechnung Nr. RE-2024-001",
            source_language="de",
        )

        assert result.was_translated is False
        assert result.translated_text == result.original_text
        assert result.confidence == 1.0
        assert result.duration_ms == 0

    @pytest.mark.asyncio
    async def test_skip_english_text(self, service: TranslationService) -> None:
        """Englische Texte werden nicht uebersetzt."""
        result = await service.translate_for_extraction(
            text="Invoice No. INV-2024-001",
            source_language="en",
        )

        assert result.was_translated is False
        assert result.translated_text == "Invoice No. INV-2024-001"

    @pytest.mark.asyncio
    async def test_skip_unknown_language(self, service: TranslationService) -> None:
        """Unbekannte Sprache wird uebersprungen."""
        result = await service.translate_for_extraction(
            text="Some unknown text",
            source_language="unknown",
        )

        assert result.was_translated is False

    @pytest.mark.asyncio
    async def test_skip_when_provider_disabled(self) -> None:
        """Bei deaktiviertem Provider wird nicht uebersetzt."""
        service = TranslationService(provider=TranslationProvider.DISABLED)

        result = await service.translate_for_extraction(
            text="Счёт-фактура номер 123",
            source_language="ru",
        )

        assert result.was_translated is False
        assert result.translated_text == result.original_text

    # =========================================================================
    # translate_for_extraction Tests - Translation Cases (Mocked)
    # =========================================================================

    @pytest.mark.asyncio
    async def test_translate_russian_text(self, argos_service: TranslationService) -> None:
        """Russische Texte werden uebersetzt (mit Mock)."""
        # Argos Translate mocken
        with patch.object(argos_service, '_translate_argos') as mock_translate:
            mock_translate.return_value = "Rechnung Nummer 123"

            result = await argos_service.translate_for_extraction(
                text="Счёт-фактура номер 123",
                source_language="ru",
            )

            assert result.was_translated is True
            assert result.translated_text == "Rechnung Nummer 123"
            assert result.source_language == "ru"
            assert result.target_language == "de"
            mock_translate.assert_called_once()

    @pytest.mark.asyncio
    async def test_translate_polish_text(self, argos_service: TranslationService) -> None:
        """Polnische Texte werden uebersetzt (mit Mock)."""
        with patch.object(argos_service, '_translate_argos') as mock_translate:
            mock_translate.return_value = "Rechnung Nr. FA-2024-001"

            result = await argos_service.translate_for_extraction(
                text="Faktura nr FA-2024-001",
                source_language="pl",
            )

            assert result.was_translated is True
            assert "Rechnung" in result.translated_text
            assert result.source_language == "pl"

    @pytest.mark.asyncio
    async def test_translation_sets_confidence(self, argos_service: TranslationService) -> None:
        """Uebersetzung setzt Provider-spezifische Konfidenz."""
        with patch.object(argos_service, '_translate_argos') as mock_translate:
            mock_translate.return_value = "Uebersetzter Text"

            result = await argos_service.translate_for_extraction(
                text="Originaltext",
                source_language="ru",
            )

            # Argos hat Konfidenz 0.80
            assert result.confidence == 0.80

    @pytest.mark.asyncio
    async def test_translation_measures_duration(self, argos_service: TranslationService) -> None:
        """Uebersetzungsdauer wird gemessen."""
        with patch.object(argos_service, '_translate_argos') as mock_translate:
            mock_translate.return_value = "Uebersetzter Text"

            result = await argos_service.translate_for_extraction(
                text="Originaltext",
                source_language="ru",
            )

            assert result.duration_ms >= 0

    # =========================================================================
    # Caching Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_caching_enabled(self, argos_service: TranslationService) -> None:
        """Cache speichert Uebersetzungen."""
        text = "Счёт-фактура"

        with patch.object(argos_service, '_translate_argos') as mock_translate:
            mock_translate.return_value = "Rechnung"

            # Erste Anfrage
            result1 = await argos_service.translate_for_extraction(text, "ru")

            # Zweite Anfrage (sollte gecacht sein)
            result2 = await argos_service.translate_for_extraction(text, "ru")

            # Translate sollte nur einmal aufgerufen werden
            assert mock_translate.call_count == 1

            # Ergebnisse sollten identisch sein
            assert result1.translated_text == result2.translated_text

            # Stats pruefen
            stats = argos_service.get_stats()
            assert stats["cached"] >= 1

    @pytest.mark.asyncio
    async def test_cache_disabled(self) -> None:
        """Bei deaktiviertem Cache wird immer uebersetzt."""
        service = TranslationService(
            provider=TranslationProvider.ARGOS,
            cache_enabled=False
        )

        with patch.object(service, '_translate_argos') as mock_translate:
            mock_translate.return_value = "Rechnung"

            await service.translate_for_extraction("Счёт", "ru")
            await service.translate_for_extraction("Счёт", "ru")

            # Translate sollte zweimal aufgerufen werden
            assert mock_translate.call_count == 2

    def test_clear_cache(self, argos_service: TranslationService) -> None:
        """Cache kann geleert werden."""
        # Cache manuell befuellen ueber die LRUCache set() Methode
        argos_service._cache.set(
            "test:abc123",
            TranslationResult(
                original_text="test",
                translated_text="test",
                source_language="ru",
                target_language="de",
                provider=TranslationProvider.ARGOS,
                confidence=0.8,
                duration_ms=100,
                was_translated=True,
            )
        )

        count = argos_service.clear_cache()

        assert count == 1
        assert len(argos_service._cache) == 0

    # =========================================================================
    # Stats Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_stats_tracking(self, argos_service: TranslationService) -> None:
        """Statistiken werden korrekt getrackt."""
        with patch.object(argos_service, '_translate_argos') as mock_translate:
            mock_translate.return_value = "Uebersetzt"

            # Deutsche (skip)
            await argos_service.translate_for_extraction("Hallo", "de")

            # Russisch (translate)
            await argos_service.translate_for_extraction("Привет", "ru")

            # Nochmal Russisch (cached)
            await argos_service.translate_for_extraction("Привет", "ru")

            stats = argos_service.get_stats()

            assert stats["total"] == 3
            assert stats["skipped"] == 1
            assert stats["translated"] == 1
            assert stats["cached"] == 1

    # =========================================================================
    # Text Length Limit Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_text_truncation(self, argos_service: TranslationService) -> None:
        """Lange Texte werden gekuerzt."""
        argos_service.max_text_length = 100
        long_text = "A" * 200

        with patch.object(argos_service, '_translate_argos') as mock_translate:
            mock_translate.return_value = "Gekuerzter Text"

            await argos_service.translate_for_extraction(long_text, "ru")

            # Check dass nur max_text_length Zeichen uebersetzt wurden
            call_args = mock_translate.call_args[0]
            assert len(call_args[0]) == 100

    # =========================================================================
    # Error Handling Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_translation_error_returns_original(self, argos_service: TranslationService) -> None:
        """Bei Uebersetzungsfehler wird Original zurueckgegeben."""
        with patch.object(argos_service, '_translate_argos') as mock_translate:
            mock_translate.side_effect = Exception("Translation failed")

            result = await argos_service.translate_for_extraction(
                text="Текст",
                source_language="ru",
            )

            # Sollte nicht als uebersetzt markiert sein
            assert result.was_translated is False
            # Original Text sollte zurueckgegeben werden
            assert result.translated_text == "Текст"

            # Fehler sollte gezaehlt werden
            stats = argos_service.get_stats()
            assert stats["errors"] == 1

    # =========================================================================
    # Provider Confidence Tests
    # =========================================================================

    def test_provider_confidence_values(self) -> None:
        """Provider-Konfidenzwerte sind korrekt definiert."""
        assert TranslationService.PROVIDER_CONFIDENCE[TranslationProvider.ARGOS] == 0.80
        assert TranslationService.PROVIDER_CONFIDENCE[TranslationProvider.LIBRETRANSLATE] == 0.82
        assert TranslationService.PROVIDER_CONFIDENCE[TranslationProvider.DEEPL] == 0.95
        assert TranslationService.PROVIDER_CONFIDENCE[TranslationProvider.DISABLED] == 0.0

    # =========================================================================
    # Cache Size Limit Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_cache_size_limit(self) -> None:
        """Cache respektiert Groessenlimit (LRU-Verhalten)."""
        # Service mit kleinem Cache erstellen
        service = TranslationService(
            provider=TranslationProvider.ARGOS,
            cache_size=3
        )

        with patch.object(service, '_translate_argos') as mock_translate:
            mock_translate.return_value = "Uebersetzt"

            # 5 verschiedene Texte uebersetzen
            for i in range(5):
                await service.translate_for_extraction(f"Text {i}", "ru")

            # Cache sollte nur 3 Eintraege haben (maxsize=3)
            assert len(service._cache) == 3

            # Die aeltesten (Text 0, Text 1) sollten rausgeworfen sein
            # Die neuesten (Text 2, 3, 4) sollten noch da sein
            stats = service.get_stats()
            assert stats["translated"] == 5  # Alle wurden uebersetzt

    def test_cache_lru_eviction_order(self) -> None:
        """LRU Cache entfernt aelteste Eintraege zuerst."""
        from app.services.translation_service import LRUCache

        cache: LRUCache = LRUCache(maxsize=2)

        # Zwei Eintraege hinzufuegen
        result1 = TranslationResult(
            original_text="a", translated_text="A",
            source_language="ru", target_language="de",
            provider=TranslationProvider.ARGOS,
            confidence=0.8, duration_ms=100, was_translated=True
        )
        result2 = TranslationResult(
            original_text="b", translated_text="B",
            source_language="ru", target_language="de",
            provider=TranslationProvider.ARGOS,
            confidence=0.8, duration_ms=100, was_translated=True
        )
        result3 = TranslationResult(
            original_text="c", translated_text="C",
            source_language="ru", target_language="de",
            provider=TranslationProvider.ARGOS,
            confidence=0.8, duration_ms=100, was_translated=True
        )

        cache.set("key1", result1)
        cache.set("key2", result2)

        # key1 abfragen (wird zum neuesten)
        cache.get("key1")

        # key3 hinzufuegen - sollte key2 rauswerfen (aeltester)
        cache.set("key3", result3)

        assert cache.get("key1") is not None  # Noch da (wurde abgefragt)
        assert cache.get("key2") is None  # Rausgeworfen
        assert cache.get("key3") is not None  # Neu hinzugefuegt


class TestGetTranslationServiceSingleton:
    """Tests fuer Singleton-Pattern."""

    def test_singleton_returns_same_instance(self) -> None:
        """Singleton sollte immer dieselbe Instanz zurueckgeben."""
        reset_translation_service()

        with patch('app.core.config.settings') as mock_settings:
            mock_settings.TRANSLATION_PROVIDER = "disabled"
            mock_settings.TRANSLATION_TARGET_LANGUAGE = "de"
            mock_settings.TRANSLATION_CACHE_ENABLED = True
            mock_settings.TRANSLATION_CACHE_SIZE = 1000
            mock_settings.LIBRETRANSLATE_URL = None
            mock_settings.DEEPL_API_KEY = None

            service1 = get_translation_service()
            service2 = get_translation_service()

            assert service1 is service2

        reset_translation_service()

    def test_reset_clears_singleton(self) -> None:
        """Reset setzt die Singleton-Instanz zurueck."""
        reset_translation_service()

        with patch('app.core.config.settings') as mock_settings:
            mock_settings.TRANSLATION_PROVIDER = "disabled"
            mock_settings.TRANSLATION_TARGET_LANGUAGE = "de"
            mock_settings.TRANSLATION_CACHE_ENABLED = True
            mock_settings.TRANSLATION_CACHE_SIZE = 1000
            mock_settings.LIBRETRANSLATE_URL = None
            mock_settings.DEEPL_API_KEY = None

            service1 = get_translation_service()
            reset_translation_service()
            service2 = get_translation_service()

            assert service1 is not service2

        reset_translation_service()


class TestLibreTranslateProvider:
    """Tests fuer LibreTranslate Provider."""

    @pytest.mark.asyncio
    async def test_libretranslate_api_call(self) -> None:
        """LibreTranslate API wird korrekt aufgerufen."""
        service = TranslationService(
            provider=TranslationProvider.LIBRETRANSLATE,
            libretranslate_url="http://test-server:5000"
        )

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_response = MagicMock()
            mock_response.json.return_value = {"translatedText": "Uebersetzter Text"}
            mock_client.post.return_value = mock_response

            result = await service.translate_for_extraction("Текст", "ru")

            assert result.was_translated is True
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert "http://test-server:5000/translate" in str(call_args)


class TestDeepLProvider:
    """Tests fuer DeepL Provider."""

    @pytest.mark.asyncio
    async def test_deepl_requires_api_key(self) -> None:
        """DeepL erfordert API-Key."""
        service = TranslationService(
            provider=TranslationProvider.DEEPL,
            deepl_api_key=None
        )

        result = await service.translate_for_extraction("Текст", "ru")

        # Sollte Fehler haben und Original zurueckgeben
        assert result.was_translated is False
        stats = service.get_stats()
        assert stats["errors"] >= 1

    @pytest.mark.asyncio
    async def test_deepl_api_call(self) -> None:
        """DeepL API wird korrekt aufgerufen."""
        service = TranslationService(
            provider=TranslationProvider.DEEPL,
            deepl_api_key="test-api-key"
        )

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "translations": [{"text": "Uebersetzter Text"}]
            }
            mock_client.post.return_value = mock_response

            result = await service.translate_for_extraction("Текст", "ru")

            assert result.was_translated is True
            assert result.confidence == 0.95  # DeepL Konfidenz
            mock_client.post.assert_called_once()
