# -*- coding: utf-8 -*-
"""DoS-Haertung der text_similarity-Metrik im GermanCorrectionAgent (2026-06-25).

_calculate_quality_metrics vergleicht den vollen original- vs korrigierten
OCR-Text mit SequenceMatcher (~O(L^2)). Bei pathologisch grossem Text drohte
eine Worker-Memory/CPU-Explosion. Diese Tests verifizieren die Input-Kappung.
"""

from unittest.mock import patch

from app.agents.postprocessing.german_correction_agent import (
    GermanCorrectionAgent,
    MAX_SIMILARITY_TEXT_LEN,
)


def test_max_similarity_text_len_sane():
    """Schranke gross genug fuer reale Mehrseiter, klein genug als O(L^2)-Grenze."""
    assert 10_000 <= MAX_SIMILARITY_TEXT_LEN <= 1_000_000


def test_quality_metrics_caps_oversized_text():
    """Riesen-Texte -> text_similarity wird gekappt berechnet (kein O(L^2)-Spin)."""
    agent = GermanCorrectionAgent()
    with patch(
        "app.agents.postprocessing.german_correction_agent.MAX_SIMILARITY_TEXT_LEN",
        1000,
    ):
        original = "a" * 200_000
        corrected = "a" * 200_000
        metrics = agent._calculate_quality_metrics(original, corrected, [], {})
    sim = metrics["text_similarity"]
    assert 0.0 <= sim <= 1.0
    assert sim == 1.0  # identische Texte -> nach Kappung weiterhin 1.0


def test_quality_metrics_normal_text_unaffected():
    """Reale kurze Texte: leichte Korrektur -> hohe, aber < 1.0 Aehnlichkeit."""
    agent = GermanCorrectionAgent()
    metrics = agent._calculate_quality_metrics(
        "Rechnnug Muster GmbH", "Rechnung Muster GmbH", [], {}
    )
    assert 0.0 < metrics["text_similarity"] < 1.0
