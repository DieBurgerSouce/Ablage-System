#!/usr/bin/env python3
"""
LLM Model Benchmark fuer deutsche Dokument-Verarbeitung.

Testet verschiedene Ollama-Modelle auf:
1. Deutsche Umlaut-Korrektur (ae -> ä, oe -> ö, ue -> ü, ss -> ß)
2. OCR-typische Fehler (0/O, l/1 Verwechslung)
3. Semantische Korrektur
4. Geschwindigkeit (Tokens/Sekunde)

Ausfuehrung: python scripts/benchmark_llm_models.py
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class TestCase:
    """Ein einzelner Testfall."""

    name: str
    category: str  # "umlaut", "ocr_error", "semantic"
    input_text: str
    expected_output: str
    weight: float = 1.0  # Gewichtung fuer Score


@dataclass
class ModelResult:
    """Ergebnis eines Modell-Benchmarks."""

    model_name: str
    total_score: float = 0.0
    umlaut_score: float = 0.0
    ocr_error_score: float = 0.0
    semantic_score: float = 0.0
    avg_tokens_per_second: float = 0.0
    avg_latency_ms: float = 0.0
    total_tests: int = 0
    passed_tests: int = 0
    test_results: list[dict[str, Any]] = field(default_factory=list)


# Testfaelle fuer deutsche Dokument-Verarbeitung
TEST_CASES: list[TestCase] = [
    # ============================================================
    # UMLAUT-KORREKTUR
    # ============================================================
    TestCase(
        name="Umlaut: ae -> ä (Muenchen)",
        category="umlaut",
        input_text="Die Firma hat ihren Sitz in Muenchen.",
        expected_output="Die Firma hat ihren Sitz in München.",
        weight=1.5,
    ),
    TestCase(
        name="Umlaut: oe -> ö (Koeln)",
        category="umlaut",
        input_text="Unser Buero befindet sich in Koeln.",
        expected_output="Unser Büro befindet sich in Köln.",
        weight=1.5,
    ),
    TestCase(
        name="Umlaut: ue -> ü (fuer)",
        category="umlaut",
        input_text="Vielen Dank fuer Ihre Bestellung.",
        expected_output="Vielen Dank für Ihre Bestellung.",
        weight=1.5,
    ),
    TestCase(
        name="Umlaut: ss -> ß (Strasse)",
        category="umlaut",
        input_text="Die Rechnung geht an: Hauptstrasse 15",
        expected_output="Die Rechnung geht an: Hauptstraße 15",
        weight=1.0,
    ),
    TestCase(
        name="Umlaut: Komplex (mehrere)",
        category="umlaut",
        input_text="Gemaess Vertrag ist die Zahlung faellig.",
        expected_output="Gemäß Vertrag ist die Zahlung fällig.",
        weight=2.0,
    ),
    TestCase(
        name="Umlaut: Grossbuchstaben",
        category="umlaut",
        input_text="AENDERUNGEN VORBEHALTEN",
        expected_output="ÄNDERUNGEN VORBEHALTEN",
        weight=1.0,
    ),
    # ============================================================
    # OCR-FEHLER-KORREKTUR
    # ============================================================
    TestCase(
        name="OCR: l/1 Verwechslung (Betrag)",
        category="ocr_error",
        input_text="Gesamtbetrag: l.234,56 EUR",
        expected_output="Gesamtbetrag: 1.234,56 EUR",
        weight=2.0,
    ),
    TestCase(
        name="OCR: 0/O Verwechslung (IBAN)",
        category="ocr_error",
        input_text="IBAN: DE89 37O1 OO50 OOOO OO00 00",
        expected_output="IBAN: DE89 3701 0050 0000 0000 00",
        weight=2.0,
    ),
    TestCase(
        name="OCR: rn/m Verwechslung",
        category="ocr_error",
        input_text="Die Firrna dankt fuer Ihr Vertrauen.",
        expected_output="Die Firma dankt für Ihr Vertrauen.",
        weight=1.5,
    ),
    TestCase(
        name="OCR: cl/d Verwechslung",
        category="ocr_error",
        input_text="Das Produkt wurcle am 15.01. geliefert.",
        expected_output="Das Produkt wurde am 15.01. geliefert.",
        weight=1.5,
    ),
    TestCase(
        name="OCR: Fehlende Leerzeichen",
        category="ocr_error",
        input_text="Rechnungsnummer:2024-001Datum:15.12.2024",
        expected_output="Rechnungsnummer: 2024-001 Datum: 15.12.2024",
        weight=1.0,
    ),
    # ============================================================
    # SEMANTISCHE KORREKTUR
    # ============================================================
    TestCase(
        name="Semantik: Datumsformat",
        category="semantic",
        input_text="Zahlungsziel: 0.5. Januar 2024",
        expected_output="Zahlungsziel: 05. Januar 2024",
        weight=1.5,
    ),
    TestCase(
        name="Semantik: Betragsformat",
        category="semantic",
        input_text="Nettobetrag: EUR 1.000,OO",
        expected_output="Nettobetrag: EUR 1.000,00",
        weight=1.5,
    ),
    TestCase(
        name="Semantik: Prozentangabe",
        category="semantic",
        input_text="MwSt. l9%: EUR 190,00",
        expected_output="MwSt. 19%: EUR 190,00",
        weight=1.5,
    ),
    TestCase(
        name="Semantik: Telefonnummer",
        category="semantic",
        input_text="Tel.: +49 (O) 89 / 123 456",
        expected_output="Tel.: +49 (0) 89 / 123 456",
        weight=1.0,
    ),
]

CORRECTION_PROMPT = """Du bist ein Experte fuer die Korrektur von OCR-Fehlern in deutschen Geschaeftsdokumenten.

Korrigiere den folgenden Text:
1. Ersetze ASCII-Umlaute (ae, oe, ue) durch echte Umlaute (ä, ö, ü)
2. Korrigiere OCR-typische Fehler (l/1, O/0, rn/m Verwechslungen)
3. Korrigiere offensichtliche Tippfehler
4. Behalte die urspruengliche Struktur bei

WICHTIG: Antworte NUR mit dem korrigierten Text, ohne Erklaerungen oder Anmerkungen.

Text zur Korrektur:
{text}

Korrigierter Text:"""


async def test_model(
    client: httpx.AsyncClient,
    model_name: str,
    test_cases: list[TestCase],
    ollama_url: str = "http://localhost:11434",
) -> ModelResult:
    """Testet ein einzelnes Modell mit allen Testfaellen."""
    result = ModelResult(model_name=model_name)

    category_scores: dict[str, list[float]] = {
        "umlaut": [],
        "ocr_error": [],
        "semantic": [],
    }
    latencies: list[float] = []
    tokens_per_second: list[float] = []

    print(f"\n{'='*60}")
    print(f"  Testing: {model_name}")
    print(f"{'='*60}")

    for i, test in enumerate(test_cases, 1):
        print(f"\n  [{i}/{len(test_cases)}] {test.name}")

        prompt = CORRECTION_PROMPT.format(text=test.input_text)

        start_time = time.perf_counter()
        try:
            response = await client.post(
                f"{ollama_url}/api/generate",
                json={
                    "model": model_name,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 200,
                    },
                },
                timeout=120.0,
            )
            response.raise_for_status()
            data = response.json()

            end_time = time.perf_counter()
            latency_ms = (end_time - start_time) * 1000

            output = data.get("response", "").strip()

            # Tokens pro Sekunde berechnen
            eval_count = data.get("eval_count", 0)
            eval_duration_ns = data.get("eval_duration", 1)
            if eval_duration_ns > 0:
                tps = eval_count / (eval_duration_ns / 1e9)
            else:
                tps = 0

            # Bewertung: Wie aehnlich ist die Ausgabe zum erwarteten Ergebnis?
            score = calculate_similarity_score(output, test.expected_output)
            weighted_score = score * test.weight

            # Ergebnis speichern
            test_result = {
                "name": test.name,
                "category": test.category,
                "input": test.input_text,
                "expected": test.expected_output,
                "actual": output,
                "score": score,
                "weighted_score": weighted_score,
                "latency_ms": latency_ms,
                "tokens_per_second": tps,
                "passed": score >= 0.8,
            }
            result.test_results.append(test_result)

            category_scores[test.category].append(weighted_score)
            latencies.append(latency_ms)
            if tps > 0:
                tokens_per_second.append(tps)

            if test_result["passed"]:
                result.passed_tests += 1

            # Status ausgeben
            status = "PASS" if test_result["passed"] else "FAIL"
            print(f"    Input:    '{test.input_text}'")
            print(f"    Expected: '{test.expected_output}'")
            print(f"    Got:      '{output}'")
            print(f"    Score: {score:.2f} | Latency: {latency_ms:.0f}ms | TPS: {tps:.1f} | {status}")

        except httpx.TimeoutException:
            print(f"    TIMEOUT nach 120s")
            result.test_results.append({
                "name": test.name,
                "category": test.category,
                "error": "TIMEOUT",
                "score": 0,
                "passed": False,
            })
        except Exception as e:
            print(f"    ERROR: {e}")
            result.test_results.append({
                "name": test.name,
                "category": test.category,
                "error": str(e),
                "score": 0,
                "passed": False,
            })

        result.total_tests += 1

    # Durchschnittswerte berechnen
    result.umlaut_score = sum(category_scores["umlaut"]) / max(len(category_scores["umlaut"]), 1)
    result.ocr_error_score = sum(category_scores["ocr_error"]) / max(len(category_scores["ocr_error"]), 1)
    result.semantic_score = sum(category_scores["semantic"]) / max(len(category_scores["semantic"]), 1)
    result.total_score = (result.umlaut_score + result.ocr_error_score + result.semantic_score) / 3
    result.avg_latency_ms = sum(latencies) / max(len(latencies), 1)
    result.avg_tokens_per_second = sum(tokens_per_second) / max(len(tokens_per_second), 1)

    return result


def calculate_similarity_score(actual: str, expected: str) -> float:
    """
    Berechnet einen Aehnlichkeits-Score zwischen 0 und 1.

    Verwendet mehrere Metriken:
    1. Exakte Übereinstimmung
    2. Normalisierte Levenshtein-Distanz
    3. Schluesselwort-Matching
    """
    # Normalisieren
    actual_clean = actual.strip().lower()
    expected_clean = expected.strip().lower()

    # Exakte Übereinstimmung
    if actual_clean == expected_clean:
        return 1.0

    # Wenn die Ausgabe den erwarteten Text enthaelt
    if expected_clean in actual_clean:
        # Bestrafe zusaetzlichen Text leicht
        ratio = len(expected_clean) / len(actual_clean)
        return min(1.0, ratio + 0.2)

    # Levenshtein-Distanz (vereinfacht)
    len_diff = abs(len(actual_clean) - len(expected_clean))
    max_len = max(len(actual_clean), len(expected_clean), 1)

    # Zeichen-Matching
    matching_chars = sum(1 for a, b in zip(actual_clean, expected_clean) if a == b)
    char_score = matching_chars / max_len

    # Wort-Matching
    actual_words = set(actual_clean.split())
    expected_words = set(expected_clean.split())
    if expected_words:
        word_score = len(actual_words & expected_words) / len(expected_words)
    else:
        word_score = 0

    # Kombinierter Score
    return (char_score * 0.6 + word_score * 0.4)


async def get_installed_models(
    client: httpx.AsyncClient,
    ollama_url: str = "http://localhost:11434",
) -> list[str]:
    """Holt Liste der installierten Modelle."""
    try:
        response = await client.get(f"{ollama_url}/api/tags", timeout=30.0)
        response.raise_for_status()
        data = response.json()
        return [m["name"] for m in data.get("models", [])]
    except Exception as e:
        print(f"Fehler beim Abrufen der Modelle: {e}")
        return []


async def warmup_model(
    client: httpx.AsyncClient,
    model_name: str,
    ollama_url: str = "http://localhost:11434",
) -> bool:
    """Laed das Modell in den Speicher (Warmup)."""
    print(f"  Warmup: {model_name}...")
    try:
        response = await client.post(
            f"{ollama_url}/api/generate",
            json={
                "model": model_name,
                "prompt": "Hallo",
                "stream": False,
                "options": {"num_predict": 10},
            },
            timeout=300.0,  # 5 Minuten fuer erstes Laden
        )
        response.raise_for_status()
        print(f"  Warmup: {model_name} geladen")
        return True
    except Exception as e:
        print(f"  Warmup FEHLER: {e}")
        return False


def print_summary(results: list[ModelResult]) -> None:
    """Gibt eine zusammenfassende Tabelle aus."""
    print("\n")
    print("=" * 100)
    print("  BENCHMARK ZUSAMMENFASSUNG")
    print("=" * 100)

    # Header
    print(f"\n{'Modell':<35} {'Score':>8} {'Umlaut':>8} {'OCR':>8} {'Semantik':>8} {'TPS':>8} {'Latenz':>10}")
    print("-" * 100)

    # Sortiert nach Total Score
    sorted_results = sorted(results, key=lambda r: r.total_score, reverse=True)

    for r in sorted_results:
        print(
            f"{r.model_name:<35} "
            f"{r.total_score:>7.2f}* "
            f"{r.umlaut_score:>7.2f}* "
            f"{r.ocr_error_score:>7.2f}* "
            f"{r.semantic_score:>7.2f}* "
            f"{r.avg_tokens_per_second:>7.1f} "
            f"{r.avg_latency_ms:>8.0f}ms"
        )

    print("-" * 100)
    print("  * Score ist gewichtet (max ~1.5 bei voller Punktzahl)")
    print()

    # Empfehlung
    if sorted_results:
        best = sorted_results[0]
        fastest = max(results, key=lambda r: r.avg_tokens_per_second)

        print("  EMPFEHLUNGEN:")
        print(f"  - Beste Qualitaet:     {best.model_name} (Score: {best.total_score:.2f})")
        print(f"  - Schnellstes Modell:  {fastest.model_name} (TPS: {fastest.avg_tokens_per_second:.1f})")

        # Beste Balance finden
        if len(sorted_results) > 1:
            # Score normalisieren (0-1) und mit TPS kombinieren
            max_score = max(r.total_score for r in results)
            max_tps = max(r.avg_tokens_per_second for r in results) or 1

            balance_scores = []
            for r in results:
                norm_score = r.total_score / max_score if max_score > 0 else 0
                norm_tps = r.avg_tokens_per_second / max_tps if max_tps > 0 else 0
                balance = norm_score * 0.7 + norm_tps * 0.3  # 70% Qualitaet, 30% Speed
                balance_scores.append((r, balance))

            best_balance = max(balance_scores, key=lambda x: x[1])
            print(f"  - Beste Balance:       {best_balance[0].model_name}")

    print()


async def main() -> None:
    """Hauptfunktion des Benchmarks."""
    print("\n" + "=" * 60)
    print("  LLM MODEL BENCHMARK FUER DEUTSCHE DOKUMENTE")
    print("=" * 60)

    ollama_url = "http://localhost:11434"

    # Modelle zum Testen - alle verfuegbaren Text-Modelle
    target_models = [
        "qwen2.5:7b",
        "qwen2.5:14b",
        "llama3.1:8b",
        # Vision-Modelle werden uebersprungen (nicht fuer Text-Korrektur geeignet)
    ]

    async with httpx.AsyncClient() as client:
        # Installierte Modelle pruefen
        print("\n[1] INSTALLIERTE MODELLE PRUEFEN")
        print("-" * 40)

        installed = await get_installed_models(client, ollama_url)
        print(f"  Gefunden: {len(installed)} Modelle")
        for m in installed:
            print(f"    - {m}")

        # Nur installierte Zielmodelle testen
        models_to_test = [m for m in target_models if m in installed]

        # Falls keine Zielmodelle, teste was verfuegbar ist
        if not models_to_test:
            print("\n  WARNUNG: Keine Zielmodelle gefunden!")
            print("  Teste verfuegbare Modelle...")
            # Filtere Vision-Modelle raus (nicht fuer Text geeignet)
            models_to_test = [m for m in installed if "vision" not in m.lower()]

        if not models_to_test:
            print("\n  FEHLER: Keine geeigneten Modelle gefunden!")
            print("  Bitte installieren Sie mindestens ein Text-Modell:")
            print("    ollama pull qwen2.5:7b-instruct-q4_K_M")
            return

        print(f"\n  Zu testende Modelle: {len(models_to_test)}")
        for m in models_to_test:
            print(f"    - {m}")

        # Benchmark durchfuehren
        print("\n[2] BENCHMARK STARTEN")
        print("-" * 40)

        results: list[ModelResult] = []

        for model_name in models_to_test:
            # Warmup
            success = await warmup_model(client, model_name, ollama_url)
            if not success:
                print(f"  Ueberspringe {model_name} (Warmup fehlgeschlagen)")
                continue

            # Testen
            result = await test_model(client, model_name, TEST_CASES, ollama_url)
            results.append(result)

        # Zusammenfassung
        print_summary(results)


if __name__ == "__main__":
    asyncio.run(main())
