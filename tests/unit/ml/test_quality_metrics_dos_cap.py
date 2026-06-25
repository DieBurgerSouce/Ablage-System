# -*- coding: utf-8 -*-
"""DoS-Haertung der OCR-Pipeline-Distanz/Fuzzy-Stellen (Defense-in-Depth, 2026-06-25).

Sweep-Abschluss der api-Hang/DoS-Klasse ueber die API-Handler hinaus: die
verbleibenden Stellen liegen in OCR-Postprocessing/ML und sind bounded/niedrig
exponiert (Entity-Werte bzw. curated/offline ML-/Benchmark-Daten). Sie werden
trotzdem defensiv gegen die O(L^2)-Explosion gecappt.
"""

from unittest.mock import patch

from app.ml.quality_metrics import OCRQualityCalculator, MAX_LEVENSHTEIN_TEXT_LEN
from app.agents.ocr.hybrid_agent import MAX_ENTITY_VALUE_LEN
from app.agents.postprocessing.qa_agent import MAX_QA_VALUE_LEN


def test_dos_cap_constants_sane():
    """Alle drei Caps gross genug fuer reale Daten, klein genug als O(L^2)-Grenze."""
    assert 1_000 <= MAX_LEVENSHTEIN_TEXT_LEN <= 1_000_000
    assert 100 <= MAX_ENTITY_VALUE_LEN <= 100_000
    assert 100 <= MAX_QA_VALUE_LEN <= 100_000


def test_levenshtein_caps_oversized_inputs():
    """Ueberlange Inputs -> auf MAX gekappt berechnet (kein O(m*n)-Spin)."""
    calc = OCRQualityCalculator()
    with patch("app.ml.quality_metrics.MAX_LEVENSHTEIN_TEXT_LEN", 100):
        # 5000x 'a' vs 5000x 'b' -> nach Kappung 100 'a' vs 100 'b' -> Distanz 100
        result = calc.levenshtein_distance("a" * 5000, "b" * 5000)
    assert result.distance == 100


def test_levenshtein_normal_inputs_unaffected():
    """Reale (kurze) Inputs unveraendert: korrekte Distanz."""
    calc = OCRQualityCalculator()
    assert calc.levenshtein_distance("Mustermann", "Mustermann").distance == 0
    assert calc.levenshtein_distance("Rechnung", "Rechnnug").distance >= 1
