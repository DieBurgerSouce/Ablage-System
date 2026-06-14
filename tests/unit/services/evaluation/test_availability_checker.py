# -*- coding: utf-8 -*-
"""
Property-Based Tests für AvailabilityChecker.

Feature: paddleocr-vl-evaluation
Property 1: Version Comparison Correctness
Validates: Requirements 1.3

Tests verwenden Hypothesis für Property-Based Testing mit mindestens 100 Iterationen.
"""

import pytest

try:
    from hypothesis import given, strategies as st, settings, assume, Phase

    HAS_HYPOTHESIS = True
except ImportError:  # hypothesis ist Dev-Only (requirements-dev.txt) und im
    # Runtime-Container nicht installiert -> Property-Tests sauber skippen,
    # Edge-Case-Unit-Tests bleiben aber lauffaehig.
    HAS_HYPOTHESIS = False

    class _StStub:
        """Platzhalter, damit die @given/@st-Dekorationen importierbar bleiben.

        ``composite`` wirkt als Identitaets-Dekorator, damit die als
        ``@st.composite`` definierten Strategie-Funktionen aufrufbar bleiben
        und nicht ``None`` werden (sonst TypeError bei Klassendefinition).
        """

        @staticmethod
        def composite(func):  # noqa: ANN001
            # Strategie-Aufrufe (z.B. simple_version_string()) liefern einen
            # harmlosen Platzhalter; die eigentlichen Property-Tests werden
            # ohnehin per skipif uebersprungen.
            return lambda *a, **k: "0.0.0"

        def __getattr__(self, _name):  # noqa: ANN001
            return lambda *a, **k: None

    st = _StStub()  # type: ignore[assignment]

    def given(*args, **kwargs):  # type: ignore[no-redef]
        def _decorator(func):
            return func

        return _decorator

    def settings(*args, **kwargs):  # type: ignore[no-redef]
        def _decorator(func):
            return func

        return _decorator

    def assume(*args, **kwargs):  # type: ignore[no-redef]
        return None

    Phase = None  # type: ignore[assignment]

from app.services.evaluation.availability_checker import (
    SemanticVersion,
    compare_versions,
    version_meets_requirement,
)


# =============================================================================
# Strategies für Version-Generierung
# =============================================================================

# Strategie für gültige Versionsnummern (0-999)
version_number = st.integers(min_value=0, max_value=999)

# Strategie für Pre-release Identifier
prerelease_identifier = st.from_regex(r'[a-zA-Z0-9]+', fullmatch=True)

# Strategie für vollständige semantische Versionen
@st.composite
def semantic_version_string(draw):
    """Generiert gültige semantische Versionsstrings."""
    major = draw(version_number)
    minor = draw(version_number)
    patch = draw(version_number)

    # Optional: Pre-release
    has_prerelease = draw(st.booleans())
    prerelease = ""
    if has_prerelease:
        prerelease_parts = draw(st.lists(
            st.one_of(
                st.integers(min_value=0, max_value=99).map(str),
                st.from_regex(r'[a-zA-Z][a-zA-Z0-9]*', fullmatch=True)
            ),
            min_size=1,
            max_size=3
        ))
        prerelease = "-" + ".".join(prerelease_parts)

    return f"{major}.{minor}.{patch}{prerelease}"


# Strategie für einfache Versionen (major.minor.patch)
@st.composite
def simple_version_string(draw):
    """Generiert einfache Versionsstrings ohne Pre-release."""
    major = draw(version_number)
    minor = draw(version_number)
    patch = draw(version_number)
    return f"{major}.{minor}.{patch}"


# =============================================================================
# Property Tests
# =============================================================================

@pytest.mark.skipif(
    not HAS_HYPOTHESIS,
    reason="hypothesis (requirements-dev.txt) im Runtime-Container nicht installiert",
)
class TestVersionComparisonCorrectness:
    """
    Property 1: Version Comparison Correctness

    For any two version strings in semantic versioning format,
    the version comparison function SHALL correctly determine
    if the first version meets or exceeds the second version.

    **Validates: Requirements 1.3**
    """

    @settings(max_examples=100, deadline=None)
    @given(simple_version_string())
    def test_version_equals_itself(self, version: str):
        """
        Feature: paddleocr-vl-evaluation, Property 1: Version Comparison Correctness

        Eine Version ist immer gleich sich selbst.
        """
        assert compare_versions(version, version) == 0
        assert version_meets_requirement(version, version) is True

    @settings(max_examples=100, deadline=None)
    @given(simple_version_string(), simple_version_string())
    def test_version_comparison_antisymmetric(self, v1: str, v2: str):
        """
        Feature: paddleocr-vl-evaluation, Property 1: Version Comparison Correctness

        Versionsvergleich ist antisymmetrisch: wenn a < b, dann b > a.
        """
        cmp_ab = compare_versions(v1, v2)
        cmp_ba = compare_versions(v2, v1)

        # Antisymmetrie: sign(cmp(a,b)) == -sign(cmp(b,a))
        assert cmp_ab == -cmp_ba

    @settings(max_examples=100, deadline=None)
    @given(simple_version_string(), simple_version_string(), simple_version_string())
    def test_version_comparison_transitive(self, v1: str, v2: str, v3: str):
        """
        Feature: paddleocr-vl-evaluation, Property 1: Version Comparison Correctness

        Versionsvergleich ist transitiv: wenn a <= b und b <= c, dann a <= c.
        """
        cmp_12 = compare_versions(v1, v2)
        cmp_23 = compare_versions(v2, v3)
        cmp_13 = compare_versions(v1, v3)

        # Transitivität für <=
        if cmp_12 <= 0 and cmp_23 <= 0:
            assert cmp_13 <= 0

    @settings(max_examples=100, deadline=None)
    @given(
        st.integers(min_value=0, max_value=100),
        st.integers(min_value=0, max_value=100),
        st.integers(min_value=0, max_value=100)
    )
    def test_major_version_dominates(self, major1: int, major2: int, minor_patch: int):
        """
        Feature: paddleocr-vl-evaluation, Property 1: Version Comparison Correctness

        Major-Version hat höchste Priorität im Vergleich.
        """
        v1 = f"{major1}.{minor_patch}.{minor_patch}"
        v2 = f"{major2}.{minor_patch}.{minor_patch}"

        result = compare_versions(v1, v2)

        if major1 < major2:
            assert result == -1
        elif major1 > major2:
            assert result == 1
        else:
            assert result == 0

    @settings(max_examples=100, deadline=None)
    @given(
        st.integers(min_value=0, max_value=100),
        st.integers(min_value=0, max_value=100),
        st.integers(min_value=0, max_value=100),
        st.integers(min_value=0, max_value=100)
    )
    def test_minor_version_secondary(self, major: int, minor1: int, minor2: int, patch: int):
        """
        Feature: paddleocr-vl-evaluation, Property 1: Version Comparison Correctness

        Bei gleichem Major hat Minor-Version zweithöchste Priorität.
        """
        v1 = f"{major}.{minor1}.{patch}"
        v2 = f"{major}.{minor2}.{patch}"

        result = compare_versions(v1, v2)

        if minor1 < minor2:
            assert result == -1
        elif minor1 > minor2:
            assert result == 1
        else:
            assert result == 0

    @settings(max_examples=100, deadline=None)
    @given(
        st.integers(min_value=0, max_value=100),
        st.integers(min_value=0, max_value=100),
        st.integers(min_value=0, max_value=100),
        st.integers(min_value=0, max_value=100)
    )
    def test_patch_version_tertiary(self, major: int, minor: int, patch1: int, patch2: int):
        """
        Feature: paddleocr-vl-evaluation, Property 1: Version Comparison Correctness

        Bei gleichem Major und Minor hat Patch-Version dritthöchste Priorität.
        """
        v1 = f"{major}.{minor}.{patch1}"
        v2 = f"{major}.{minor}.{patch2}"

        result = compare_versions(v1, v2)

        if patch1 < patch2:
            assert result == -1
        elif patch1 > patch2:
            assert result == 1
        else:
            assert result == 0

    @settings(max_examples=100, deadline=None)
    @given(simple_version_string(), simple_version_string())
    def test_version_meets_requirement_consistency(self, installed: str, minimum: str):
        """
        Feature: paddleocr-vl-evaluation, Property 1: Version Comparison Correctness

        version_meets_requirement ist konsistent mit compare_versions.
        """
        cmp_result = compare_versions(installed, minimum)
        meets = version_meets_requirement(installed, minimum)

        # meets == True genau dann wenn installed >= minimum (cmp >= 0)
        assert meets == (cmp_result >= 0)

    @settings(max_examples=100, deadline=None)
    @given(simple_version_string())
    def test_prerelease_less_than_release(self, base_version: str):
        """
        Feature: paddleocr-vl-evaluation, Property 1: Version Comparison Correctness

        Pre-release Versionen sind kleiner als Release-Versionen.
        """
        release = base_version
        prerelease = f"{base_version}-alpha"

        # Pre-release < Release
        assert compare_versions(prerelease, release) == -1
        assert compare_versions(release, prerelease) == 1


# =============================================================================
# Unit Tests für Edge Cases
# =============================================================================

class TestVersionComparisonEdgeCases:
    """Unit Tests für spezifische Edge Cases."""

    def test_known_versions_paddleocr(self):
        """Testet bekannte PaddleOCR Versionen."""
        # 3.3.2 > 2.6.0
        assert compare_versions("3.3.2", "2.6.0") == 1
        assert version_meets_requirement("3.3.2", "2.6.0") is True

        # 2.6.0 < 3.3.2
        assert compare_versions("2.6.0", "3.3.2") == -1
        assert version_meets_requirement("2.6.0", "3.3.2") is False

    def test_version_with_leading_v(self):
        """Testet Versionen mit führendem 'v'."""
        v1 = SemanticVersion("v1.2.3")
        v2 = SemanticVersion("1.2.3")

        assert v1 == v2

    def test_prerelease_ordering(self):
        """Testet Pre-release Reihenfolge."""
        # alpha < beta < rc < release
        assert compare_versions("1.0.0-alpha", "1.0.0-beta") == -1
        assert compare_versions("1.0.0-beta", "1.0.0-rc.1") == -1
        assert compare_versions("1.0.0-rc.1", "1.0.0") == -1

    def test_numeric_prerelease_ordering(self):
        """Testet numerische Pre-release Identifier."""
        # 1.0.0-1 < 1.0.0-2 < 1.0.0-10
        assert compare_versions("1.0.0-1", "1.0.0-2") == -1
        assert compare_versions("1.0.0-2", "1.0.0-10") == -1

    def test_zero_versions(self):
        """Testet Versionen mit Nullen."""
        assert compare_versions("0.0.0", "0.0.1") == -1
        assert compare_versions("0.0.1", "0.1.0") == -1
        assert compare_versions("0.1.0", "1.0.0") == -1

    def test_invalid_version_raises(self):
        """Testet dass ungültige Versionen ValueError auslösen."""
        with pytest.raises(ValueError):
            SemanticVersion("not-a-version")

        with pytest.raises(ValueError):
            SemanticVersion("1.2")  # Fehlendes Patch

        with pytest.raises(ValueError):
            SemanticVersion("1")  # Nur Major
