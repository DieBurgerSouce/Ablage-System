# -*- coding: utf-8 -*-
"""
Translation Service fuer mehrsprachige Dokumentenextraktion.

Uebersetzt nicht-deutsche Texte ins Deutsche VOR der strukturierten Extraktion.
Ermoeglicht einheitliche Suche nach deutschen Keywords.

Provider-Optionen:
1. Argos Translate (EMPFOHLEN - 100% offline, kein API-Key)
2. LibreTranslate (self-hosted, REST API)
3. DeepL API (kostenpflichtig, beste Qualitaet)

Usage:
    service = TranslationService(provider=TranslationProvider.ARGOS)
    result = await service.translate_for_extraction(text, source_language="ru")
    print(result.translated_text)  # Deutsche Uebersetzung
"""

import asyncio
import hashlib
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional

import structlog

logger = structlog.get_logger(__name__)


class TranslationProvider(str, Enum):
    """Verfuegbare Uebersetzungs-Provider."""

    ARGOS = "argos"  # Offline, lokal - EMPFOHLEN
    LIBRETRANSLATE = "libretranslate"  # Self-hosted REST API
    DEEPL = "deepl"  # Cloud API (kostenpflichtig)
    DISABLED = "disabled"  # Uebersetzung deaktiviert


@dataclass
class TranslationResult:
    """Ergebnis einer Uebersetzung."""

    original_text: str
    translated_text: str
    source_language: str
    target_language: str
    provider: TranslationProvider
    confidence: float  # 0.0-1.0
    duration_ms: int
    was_translated: bool  # False wenn original == target language oder skip


class LRUCache:
    """Thread-safe LRU Cache mit Groessenbegrenzung."""

    def __init__(self, maxsize: int = 1000) -> None:
        self._cache: OrderedDict[str, TranslationResult] = OrderedDict()
        self._maxsize = maxsize
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[TranslationResult]:
        """Holt Wert aus Cache (thread-safe)."""
        with self._lock:
            if key in self._cache:
                # Move to end (most recently used)
                self._cache.move_to_end(key)
                return self._cache[key]
            return None

    def set(self, key: str, value: TranslationResult) -> None:
        """Setzt Wert in Cache (thread-safe)."""
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            else:
                if len(self._cache) >= self._maxsize:
                    # Remove oldest (first) item
                    self._cache.popitem(last=False)
            self._cache[key] = value

    def clear(self) -> int:
        """Leert Cache, gibt Anzahl entfernter Eintraege zurueck."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)


class TranslationService:
    """
    Uebersetzt Texte fuer die strukturierte Extraktion.

    Strategie:
    - Deutsche/Englische Texte: Direkt durchreichen (keine Uebersetzung)
    - Andere Sprachen: Uebersetzen nach Deutsch
    - Caching: Uebersetzungen werden gecacht (LRU mit Groessenlimit)

    Performance:
    - Argos: ~200-500ms pro Dokument
    - LibreTranslate: ~100-300ms (Netzwerk-abhaengig)
    - DeepL: ~50-200ms (Cloud-API)

    Thread-Safety:
    - Alle internen State-Zugriffe sind thread-safe
    - Geeignet fuer Celery Multi-Worker Umgebungen
    """

    # Sprachen die NICHT uebersetzt werden (bereits unterstuetzt)
    SUPPORTED_LANGUAGES = {"de", "en"}

    # Konfidenz-Werte pro Provider
    PROVIDER_CONFIDENCE = {
        TranslationProvider.ARGOS: 0.80,
        TranslationProvider.LIBRETRANSLATE: 0.82,
        TranslationProvider.DEEPL: 0.95,
        TranslationProvider.DISABLED: 0.0,
    }

    # Cache-Konfiguration
    DEFAULT_CACHE_SIZE = 1000

    def __init__(
        self,
        provider: TranslationProvider = TranslationProvider.ARGOS,
        target_language: str = "de",
        cache_enabled: bool = True,
        cache_size: int = DEFAULT_CACHE_SIZE,
        max_text_length: int = 50000,
        libretranslate_url: Optional[str] = None,
        deepl_api_key: Optional[str] = None,
    ) -> None:
        """
        Initialisiert den TranslationService.

        Args:
            provider: Uebersetzungs-Provider (argos, libretranslate, deepl)
            target_language: Zielsprache (default: de)
            cache_enabled: Uebersetzungen cachen
            cache_size: Maximale Anzahl Cache-Eintraege (default: 1000)
            max_text_length: Maximale Textlaenge (wird gekuerzt)
            libretranslate_url: URL fuer LibreTranslate (falls verwendet)
            deepl_api_key: API-Key fuer DeepL (falls verwendet)
        """
        self.provider = provider
        self.target_language = target_language
        self.cache_enabled = cache_enabled
        self.max_text_length = max_text_length
        self.libretranslate_url = libretranslate_url or "http://localhost:5000"
        self.deepl_api_key = deepl_api_key

        # Thread-safe LRU Cache mit Groessenlimit
        self._cache = LRUCache(maxsize=cache_size)

        # Thread-safe stats
        self._stats_lock = threading.Lock()
        self._stats = {
            "total": 0,
            "cached": 0,
            "translated": 0,
            "skipped": 0,
            "errors": 0,
        }

        # Argos lazy loading mit Lock gegen Race Conditions
        self._argos_initialized = False
        self._argos_init_lock = threading.Lock()

        logger.info(
            "translation_service_initialized",
            provider=provider.value,
            target_language=target_language,
            cache_enabled=cache_enabled,
            cache_size=cache_size,
        )

    def _increment_stat(self, key: str) -> None:
        """Thread-safe Stats-Inkrementierung."""
        with self._stats_lock:
            self._stats[key] += 1

    def _make_cache_key(self, source_language: str, text: str) -> str:
        """Erstellt deterministischen Cache-Key mit hashlib."""
        text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
        return f"{source_language}:{text_hash}"

    async def translate_for_extraction(
        self,
        text: str,
        source_language: str,
    ) -> TranslationResult:
        """
        Uebersetzt Text fuer die strukturierte Extraktion.

        Args:
            text: Zu uebersetzender Text
            source_language: ISO 639-1 Sprachcode (z.B. "ru", "pl")

        Returns:
            TranslationResult mit Original und Uebersetzung
        """
        self._increment_stat("total")

        # Provider deaktiviert?
        if self.provider == TranslationProvider.DISABLED:
            self._increment_stat("skipped")
            return self._create_skip_result(text, source_language, "provider_disabled")

        # Keine Uebersetzung noetig? (Deutsch/Englisch)
        if source_language.lower() in self.SUPPORTED_LANGUAGES:
            self._increment_stat("skipped")
            return self._create_skip_result(text, source_language, "already_supported")

        # Unknown language? Skip
        if source_language.lower() == "unknown":
            self._increment_stat("skipped")
            return self._create_skip_result(text, source_language, "unknown_language")

        # Cache-Check mit deterministischem Hash
        cache_key = self._make_cache_key(source_language, text)
        if self.cache_enabled:
            cached_result = self._cache.get(cache_key)
            if cached_result is not None:
                self._increment_stat("cached")
                logger.debug("translation_cache_hit", source_language=source_language)
                return cached_result

        # Text kuerzen falls zu lang
        text_to_translate = text[: self.max_text_length]

        # Uebersetzung durchfuehren
        start = time.monotonic()

        try:
            if self.provider == TranslationProvider.ARGOS:
                translated = await self._translate_argos(
                    text_to_translate, source_language
                )
            elif self.provider == TranslationProvider.LIBRETRANSLATE:
                translated = await self._translate_libretranslate(
                    text_to_translate, source_language
                )
            elif self.provider == TranslationProvider.DEEPL:
                translated = await self._translate_deepl(
                    text_to_translate, source_language
                )
            else:
                raise ValueError(f"Unbekannter Provider: {self.provider}")

        except Exception as e:
            self._increment_stat("errors")
            logger.error(
                "translation_failed",
                provider=self.provider.value,
                source_language=source_language,
                error=str(e),
            )
            # Fallback: Original zurueckgeben
            return self._create_skip_result(text, source_language, f"error:{str(e)}")

        duration_ms = int((time.monotonic() - start) * 1000)

        result = TranslationResult(
            original_text=text,
            translated_text=translated,
            source_language=source_language,
            target_language=self.target_language,
            provider=self.provider,
            confidence=self.PROVIDER_CONFIDENCE.get(self.provider, 0.8),
            duration_ms=duration_ms,
            was_translated=True,
        )

        # Cachen (thread-safe)
        if self.cache_enabled:
            self._cache.set(cache_key, result)

        self._increment_stat("translated")

        logger.info(
            "text_translated",
            source_language=source_language,
            target_language=self.target_language,
            provider=self.provider.value,
            text_length=len(text),
            translated_length=len(translated),
            duration_ms=duration_ms,
        )

        return result

    def _create_skip_result(
        self, text: str, source_language: str, reason: str
    ) -> TranslationResult:
        """Erstellt ein Skip-Ergebnis (keine Uebersetzung)."""
        return TranslationResult(
            original_text=text,
            translated_text=text,
            source_language=source_language,
            target_language=source_language,
            provider=self.provider,
            confidence=1.0 if source_language in self.SUPPORTED_LANGUAGES else 0.0,
            duration_ms=0,
            was_translated=False,
        )

    async def _translate_argos(self, text: str, source_lang: str) -> str:
        """
        Uebersetzung mit Argos Translate (offline).

        Argos Translate ist synchron, wird daher in einem Thread ausgefuehrt.
        """
        # Lazy initialization mit Lock gegen Race Conditions
        if not self._argos_initialized:
            await self._init_argos()

        import argostranslate.translate

        # Argos ist synchron, in Thread ausfuehren
        # WICHTIG: get_running_loop() statt get_event_loop() (Python 3.10+ kompatibel)
        loop = asyncio.get_running_loop()
        translated = await loop.run_in_executor(
            None,
            lambda: argostranslate.translate.translate(
                text, source_lang, self.target_language
            ),
        )
        return str(translated)

    async def _init_argos(self) -> None:
        """
        Initialisiert Argos Translate (Sprachpakete laden).

        Thread-safe durch Lock - verhindert Race Conditions bei
        gleichzeitigen Initialisierungsversuchen.
        """
        # Double-checked locking pattern
        if self._argos_initialized:
            return

        with self._argos_init_lock:
            # Nochmal pruefen nach Lock-Erwerb
            if self._argos_initialized:
                return

            try:
                import argostranslate.package
                import argostranslate.translate

                # Package-Index NICHT automatisch aktualisieren beim Start
                # Das blockiert ~30 Sekunden und ist fuer Production nicht akzeptabel
                # Stattdessen: Einmalig manuell oder via Script installieren
                #
                # Die Sprachpakete werden via Docker Volume persistent gespeichert
                # und muessen nicht bei jedem Start neu geladen werden.
                #
                # Falls keine Pakete installiert sind, wird ein Fehler geloggt
                # aber die Uebersetzung faellt graceful auf Original zurueck.

                # Pruefen ob Pakete verfuegbar sind
                installed = argostranslate.package.get_installed_packages()
                if not installed:
                    logger.warning(
                        "argos_no_packages_installed",
                        hint="Installiere Sprachpakete mit: python -m scripts.install_argos_packages"
                    )

                self._argos_initialized = True
                logger.info(
                    "argos_translate_initialized",
                    installed_packages=len(installed),
                )

            except ImportError:
                raise ImportError(
                    "argostranslate nicht installiert. "
                    "Installiere mit: pip install argostranslate"
                )
            except Exception as e:
                logger.error("argos_initialization_failed", error=str(e))
                raise

    async def _translate_libretranslate(self, text: str, source_lang: str) -> str:
        """Uebersetzung mit LibreTranslate API."""
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.libretranslate_url}/translate",
                json={
                    "q": text,
                    "source": source_lang,
                    "target": self.target_language,
                    "format": "text",
                },
                timeout=60,
            )
            response.raise_for_status()
            return str(response.json()["translatedText"])

    async def _translate_deepl(self, text: str, source_lang: str) -> str:
        """Uebersetzung mit DeepL API."""
        if not self.deepl_api_key:
            raise ValueError("DEEPL_API_KEY nicht konfiguriert")

        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api-free.deepl.com/v2/translate",
                headers={"Authorization": f"DeepL-Auth-Key {self.deepl_api_key}"},
                data={
                    "text": text,
                    "source_lang": source_lang.upper(),
                    "target_lang": self.target_language.upper(),
                },
                timeout=60,
            )
            response.raise_for_status()
            return str(response.json()["translations"][0]["text"])

    def get_stats(self) -> Dict[str, int]:
        """Gibt Uebersetzungsstatistiken zurueck (thread-safe)."""
        with self._stats_lock:
            return self._stats.copy()

    def clear_cache(self) -> int:
        """Leert den Uebersetzungs-Cache. Gibt Anzahl geloeschter Eintraege zurueck."""
        count = self._cache.clear()
        logger.info("translation_cache_cleared", entries_removed=count)
        return count

    def is_translation_needed(self, source_language: Optional[str]) -> bool:
        """
        Prueft ob eine Uebersetzung fuer die Sprache noetig ist.

        Args:
            source_language: ISO 639-1 Sprachcode oder None

        Returns:
            True wenn Uebersetzung noetig, False wenn nicht
        """
        if self.provider == TranslationProvider.DISABLED:
            return False
        if source_language is None:
            return False
        if source_language.lower() == "unknown":
            return False
        return source_language.lower() not in self.SUPPORTED_LANGUAGES


# =============================================================================
# SINGLETON INSTANCE (Thread-Safe)
# =============================================================================

_translation_service: Optional[TranslationService] = None
_singleton_lock = threading.Lock()


def get_translation_service() -> TranslationService:
    """
    Gibt die Singleton-Instanz des TranslationService zurueck.

    Thread-safe durch Double-Checked Locking.
    Konfiguration wird aus app.core.config geladen.
    """
    global _translation_service

    # Fast path: Singleton bereits initialisiert
    if _translation_service is not None:
        return _translation_service

    # Slow path: Mit Lock initialisieren
    with _singleton_lock:
        # Nochmal pruefen nach Lock-Erwerb
        if _translation_service is not None:
            return _translation_service

        from app.core.config import settings

        # Provider aus Config laden (default: argos)
        provider_str = getattr(settings, "TRANSLATION_PROVIDER", "argos")
        try:
            provider = TranslationProvider(provider_str.lower())
        except ValueError:
            logger.warning(
                "invalid_translation_provider",
                provider=provider_str,
                fallback="argos",
            )
            provider = TranslationProvider.ARGOS

        # Optionale Konfiguration
        libretranslate_url = getattr(settings, "LIBRETRANSLATE_URL", None)
        deepl_api_key = None

        # SecretStr handling
        if hasattr(settings, "DEEPL_API_KEY") and settings.DEEPL_API_KEY:
            deepl_api_key = settings.DEEPL_API_KEY.get_secret_value()

        # Cache-Groesse aus Config
        cache_size = getattr(
            settings,
            "TRANSLATION_CACHE_SIZE",
            TranslationService.DEFAULT_CACHE_SIZE
        )

        _translation_service = TranslationService(
            provider=provider,
            target_language=getattr(settings, "TRANSLATION_TARGET_LANGUAGE", "de"),
            cache_enabled=getattr(settings, "TRANSLATION_CACHE_ENABLED", True),
            cache_size=cache_size,
            libretranslate_url=libretranslate_url,
            deepl_api_key=deepl_api_key,
        )

    return _translation_service


def reset_translation_service() -> None:
    """Setzt die Singleton-Instanz zurueck (fuer Tests)."""
    global _translation_service
    with _singleton_lock:
        _translation_service = None
