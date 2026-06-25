# -*- coding: utf-8 -*-
"""DoS-Haertung von calculate_similarity / find_by_matchcode (2026-06-25).

api-Hang-Defense-in-Depth (Restkandidat aus dem api-Hang/DoS-Audit):
SequenceMatcher.ratio() ist ~O(len1*len2). Ueber angreifer-kontrollierten
Riesen-Such-Input (POST-Suche) x volle Entity-Tabelle koennte EIN Request
CPU-spinnen. Diese Tests verifizieren (a) die Input-Laengen-Kappung im geteilten
Chokepoint und (b) den SQL-Kandidaten-Cap in find_by_matchcode.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.entity_search_service import (
    calculate_similarity,
    MAX_SIMILARITY_INPUT_LEN,
    MAX_FUZZY_CANDIDATES,
    EntitySearchService,
)


def test_calculate_similarity_caps_input_length_equivalent():
    """Riesen-Inputs -> Ergebnis identisch zum direkt-gekappten Vergleich (= 1.0)."""
    huge = "a" * 1_000_000
    capped = "a" * MAX_SIMILARITY_INPUT_LEN
    assert calculate_similarity(huge, huge) == 1.0
    assert calculate_similarity(huge, huge) == calculate_similarity(capped, capped)


def test_calculate_similarity_huge_distinct_inputs_return_bounded():
    """Zwei verschiedene Riesen-Strings: kehrt sofort zurueck (gekappt), float in [0,1]."""
    r = calculate_similarity("x" * 500_000, "y" * 500_000)
    assert 0.0 <= r <= 1.0
    assert r == 0.0  # keine gemeinsamen Zeichen nach Kappung


def test_calculate_similarity_normal_inputs_unaffected():
    """Reale (kurze) Inputs unveraendert: exakte Gleichheit -> 1.0, Teilmatch < 1.0."""
    assert calculate_similarity("Mustermann GmbH", "Mustermann GmbH") == 1.0
    partial = calculate_similarity("Mustermann GmbH", "Mustermann AG")
    assert 0.0 < partial < 1.0


def test_max_similarity_input_len_sane():
    """Cap gross genug fuer reale Namen, klein genug gegen O(L^2)-Spin."""
    assert 64 <= MAX_SIMILARITY_INPUT_LEN <= 1024


class _FakeEntity:
    """Minimal-Entity fuer die find_by_matchcode-Schleife (nur name gesetzt)."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.short_name = None
        self.display_name = None
        self.name_aliases = None
        self.lexware_ids = None


@pytest.mark.asyncio
async def test_find_by_matchcode_caps_candidate_set():
    """DB liefert > Cap Kandidaten -> nur MAX_FUZZY_CANDIDATES werden gescannt."""
    fake = [_FakeEntity(f"e{i}") for i in range(MAX_FUZZY_CANDIDATES + 5)]
    result = MagicMock()
    result.scalars.return_value.all.return_value = fake
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)

    svc = EntitySearchService(db)
    # calculate_similarity patchen: 0.0 -> kein Match (schnell) + Aufrufzaehler
    with patch(
        "app.services.entity_search_service.calculate_similarity",
        return_value=0.0,
    ) as mock_sim:
        out = await svc.find_by_matchcode("e0")

    # Jede Fake-Entity hat nur `name` -> genau 1 Vergleich pro gescannter Entity.
    # Der Cap muss auf MAX_FUZZY_CANDIDATES begrenzen (nicht MAX+5).
    assert mock_sim.call_count == MAX_FUZZY_CANDIDATES
    assert out == []  # threshold 0.7 > 0.0
