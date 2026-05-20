# -*- coding: utf-8 -*-
"""
Unit Tests fuer Cache Stampede Prevention (XFetch).

Tests fuer:
- _should_early_recompute() Probabilistic Early Recomputation
- Randfaelle (TTL=0, negative Werte, total_ttl=0)
- Probabilistisches Verhalten im letzten 20%-Fenster
"""

import pytest
from unittest.mock import patch

from app.core.cache import _should_early_recompute


class TestShouldEarlyRecompute:
    """Tests fuer _should_early_recompute (XFetch Algorithmus)."""

    def test_returns_true_when_ttl_is_zero(self) -> None:
        """Wenn TTL abgelaufen ist (0), muss recomputed werden."""
        result = _should_early_recompute(ttl_remaining=0.0, total_ttl=300.0)
        assert result is True

    def test_returns_true_when_ttl_is_negative(self) -> None:
        """Wenn TTL negativ ist, muss recomputed werden."""
        result = _should_early_recompute(ttl_remaining=-5.0, total_ttl=300.0)
        assert result is True

    def test_returns_false_when_total_ttl_is_zero(self) -> None:
        """Wenn total_ttl 0 ist, soll nicht recomputed werden."""
        result = _should_early_recompute(ttl_remaining=10.0, total_ttl=0.0)
        assert result is False

    def test_returns_false_when_total_ttl_is_negative(self) -> None:
        """Wenn total_ttl negativ ist, soll nicht recomputed werden."""
        result = _should_early_recompute(ttl_remaining=10.0, total_ttl=-100.0)
        assert result is False

    def test_returns_false_when_ttl_above_threshold(self) -> None:
        """Wenn TTL > 20% des total_ttl, soll nicht recomputed werden."""
        # 200s remaining of 300s total = 66.7% remaining -> no early recompute
        result = _should_early_recompute(ttl_remaining=200.0, total_ttl=300.0)
        assert result is False

    def test_returns_false_at_exactly_threshold(self) -> None:
        """Wenn TTL genau bei 20% liegt (Grenzwert), kein Recompute."""
        # 60s remaining of 300s total = exactly 20% -> ttl_remaining is NOT > threshold
        # 60 > 300 * 0.2 = 60 -> False (not strictly greater)
        # Actually 60 > 60 is False, so it falls through to XFetch math
        # With mock random returning high value, should not trigger
        with patch("random.random", return_value=0.99):
            result = _should_early_recompute(ttl_remaining=60.0, total_ttl=300.0)
            # With high random value, -delta * beta * log(0.99) is very small
            # so it should NOT trigger recompute
            assert result is False

    def test_returns_false_well_above_threshold(self) -> None:
        """Wenn TTL weit ueber 20% liegt, definitiv kein Recompute."""
        # 250s of 300s = 83% remaining
        result = _should_early_recompute(ttl_remaining=250.0, total_ttl=300.0)
        assert result is False

    def test_probabilistic_in_last_20_percent(self) -> None:
        """Im letzten 20%-Fenster soll probabilistisch recomputed werden."""
        # 10s remaining of 300s total = 3.3% remaining -> in the 20% window
        # Run many times and check that at least some return True
        true_count = 0
        false_count = 0
        for _ in range(200):
            if _should_early_recompute(ttl_remaining=10.0, total_ttl=300.0):
                true_count += 1
            else:
                false_count += 1

        # Should have BOTH True and False results (probabilistic)
        assert true_count > 0, "Sollte mindestens einmal True zurueckgeben"
        assert false_count > 0, "Sollte mindestens einmal False zurueckgeben"

    def test_higher_probability_near_zero_ttl(self) -> None:
        """Je naeher TTL an 0, desto hoeher die Wahrscheinlichkeit."""
        # Compare: 1s remaining vs 50s remaining (both in 20% window of 300s)
        near_zero_true = sum(
            1 for _ in range(500)
            if _should_early_recompute(ttl_remaining=1.0, total_ttl=300.0)
        )
        far_from_zero_true = sum(
            1 for _ in range(500)
            if _should_early_recompute(ttl_remaining=50.0, total_ttl=300.0)
        )

        # Near-zero should trigger more often
        assert near_zero_true > far_from_zero_true, (
            f"Bei TTL=1s ({near_zero_true}/500) sollte oefter triggern als "
            f"bei TTL=50s ({far_from_zero_true}/500)"
        )

    def test_beta_increases_probability(self) -> None:
        """Hoeherer Beta-Wert soll die Wahrscheinlichkeit erhoehen."""
        low_beta_true = sum(
            1 for _ in range(500)
            if _should_early_recompute(ttl_remaining=30.0, total_ttl=300.0, beta=0.5)
        )
        high_beta_true = sum(
            1 for _ in range(500)
            if _should_early_recompute(ttl_remaining=30.0, total_ttl=300.0, beta=3.0)
        )

        assert high_beta_true > low_beta_true, (
            f"Beta=3.0 ({high_beta_true}/500) sollte oefter triggern als "
            f"Beta=0.5 ({low_beta_true}/500)"
        )

    def test_returns_true_when_random_is_zero(self) -> None:
        """Wenn random() exakt 0 zurueckgibt, soll True zurueckgegeben werden."""
        with patch("random.random", return_value=0):
            result = _should_early_recompute(ttl_remaining=30.0, total_ttl=300.0)
            assert result is True

    def test_handles_very_large_ttl(self) -> None:
        """Soll auch mit sehr grossen TTL-Werten umgehen koennen."""
        # 1 day TTL, 90% remaining -> no recompute
        result = _should_early_recompute(
            ttl_remaining=80000.0,
            total_ttl=86400.0,
        )
        assert result is False

    def test_handles_very_small_ttl(self) -> None:
        """Soll auch mit sehr kleinen TTL-Werten umgehen koennen."""
        # 0.1s remaining of 1s total = 10% -> in window
        true_count = sum(
            1 for _ in range(100)
            if _should_early_recompute(ttl_remaining=0.1, total_ttl=1.0)
        )
        # Should trigger at least some of the time
        assert true_count > 0, "Sollte bei kleinem TTL mindestens einmal triggern"

    def test_default_beta_is_one(self) -> None:
        """Standard-Beta soll 1.0 sein (Signatur-Check)."""
        import inspect
        sig = inspect.signature(_should_early_recompute)
        beta_param = sig.parameters["beta"]
        assert beta_param.default == 1.0
