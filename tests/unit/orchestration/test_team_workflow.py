"""Tests fuer team_workflow.py - Team-Klassifikation und Templates.

Testet:
- Klassifikationsmatrix (Complexity x Coupling -> TeamType)
- Security/Review-Overrides
- Confidence-Berechnung
- Template-Invarianten (deepcopy, no_team builder)
- Pfad-Matching (exact, nicht substring)
"""

import pytest
import sys
from pathlib import Path

# Ensure .claude dir is on path
_claude_path = str(Path(__file__).parent.parent.parent.parent / ".claude")
if _claude_path not in sys.path:
    sys.path.insert(0, _claude_path)

from orchestration.team_workflow import (
    ClassificationInput,
    ClassificationOutput,
    Complexity,
    Coupling,
    PhaseMode,
    TeamClassifier,
    TeamTemplate,
    TeamType,
    CLASSIFICATION_MATRIX,
    TEAM_TEMPLATES,
    _build_no_team_template,
)


@pytest.fixture
def classifier() -> TeamClassifier:
    return TeamClassifier()


class TestClassificationMatrix:
    """Prueft die Zuordnung Complexity x Coupling -> TeamType."""

    def test_trivial_isolated_returns_no_team_haiku(
        self, classifier: TeamClassifier
    ) -> None:
        result = classifier.classify(ClassificationInput(
            task_description="Fix typo in readme",
            affected_files=["README.md"],
        ))
        assert result.team_type == TeamType.NO_TEAM_HAIKU

    def test_contained_light_returns_feature_standard(
        self, classifier: TeamClassifier
    ) -> None:
        result = classifier.classify(ClassificationInput(
            task_description="Add user service",
            affected_files=[
                "app/services/user/user_service.py",
                "app/api/v1/user.py",
                "tests/unit/services/user/test_user_service.py",
            ],
        ))
        # 3 files = C2, no shared files = M1 -> FEATURE_SMALL
        assert result.team_type == TeamType.FEATURE_SMALL

    def test_security_keyword_overrides(
        self, classifier: TeamClassifier
    ) -> None:
        result = classifier.classify(ClassificationInput(
            task_description="Run security audit on authentication module",
            affected_files=[],
        ))
        assert result.team_type == TeamType.SECURITY_AUDIT
        assert result.override_reason == "security"

    def test_review_keyword_overrides(
        self, classifier: TeamClassifier
    ) -> None:
        result = classifier.classify(ClassificationInput(
            task_description="Review code for banking module",
            affected_files=[],
        ))
        assert result.team_type == TeamType.REVIEW
        assert result.override_reason == "review"

    def test_classification_matrix_complete(self) -> None:
        """Alle 12 Complexity x Coupling Kombinationen sind abgedeckt."""
        for c in Complexity:
            for m in Coupling:
                assert (c, m) in CLASSIFICATION_MATRIX, (
                    f"Matrix-Eintrag fehlt: ({c.value}, {m.value})"
                )


@pytest.mark.parametrize(
    "file_count,expected",
    [
        (1, Complexity.C1_TRIVIAL),
        (2, Complexity.C1_TRIVIAL),
        (5, Complexity.C2_CONTAINED),
        (8, Complexity.C2_CONTAINED),
        (15, Complexity.C3_CROSS_CUTTING),
        (25, Complexity.C4_ARCHITECTURE),
    ],
)
def test_complexity_determination(
    classifier: TeamClassifier, file_count: int, expected: Complexity
) -> None:
    files = [f"app/services/mod{i}/svc.py" for i in range(file_count)]
    inp = ClassificationInput(task_description="task", affected_files=files)
    assert classifier._determine_complexity(inp) == expected


def test_coupling_with_shared_files(classifier: TeamClassifier) -> None:
    inp = ClassificationInput(
        task_description="update models",
        affected_files=[
            "app/services/foo/bar.py",
            "app/main.py",
            "app/db/models.py",
        ],
    )
    coupling = classifier._determine_coupling(inp)
    assert coupling == Coupling.M2_LIGHT_COUPLED


def test_no_team_template_builder() -> None:
    t_haiku = _build_no_team_template("haiku")
    t_sonnet = _build_no_team_template("sonnet")
    assert t_haiku.team_type == TeamType.NO_TEAM_HAIKU
    assert t_sonnet.team_type == TeamType.NO_TEAM_SONNET
    assert t_haiku.total_agents == 1
    assert len(t_haiku.phases) == 1
    assert t_haiku.phases[0].agents[0].model == "haiku"


def test_feature_full_is_deepcopy() -> None:
    """FEATURE_FULL darf FEATURE_STANDARD nicht mutieren."""
    std = TEAM_TEMPLATES[TeamType.FEATURE_STANDARD]
    full = TEAM_TEMPLATES[TeamType.FEATURE_FULL]
    assert full.team_type == TeamType.FEATURE_FULL
    assert std.team_type == TeamType.FEATURE_STANDARD
    # They must be separate objects
    assert std is not full
    assert std.phases is not full.phases


def test_confidence_uses_complexity_and_coupling(
    classifier: TeamClassifier,
) -> None:
    """C1+M1 soll hoehere Confidence als C4+M3 liefern."""
    simple_inp = ClassificationInput(
        task_description="A short task with files listed for good measure",
        affected_files=["app/a.py"],
    )
    complex_inp = ClassificationInput(
        task_description="A short task with files listed for good measure",
        affected_files=["app/a.py"],
    )
    c_simple = classifier._calculate_confidence(
        Complexity.C1_TRIVIAL, Coupling.M1_ISOLATED, simple_inp
    )
    c_complex = classifier._calculate_confidence(
        Complexity.C4_ARCHITECTURE, Coupling.M3_SHARED_INFRA, complex_inp
    )
    assert c_simple > c_complex


def test_path_match_exact_not_substring(
    classifier: TeamClassifier,
) -> None:
    """'app/main.py' is bottleneck, but 'app/main.py.bak' is not."""
    inp_exact = ClassificationInput(
        task_description="task",
        affected_files=["app/main.py"],
    )
    inp_suffix = ClassificationInput(
        task_description="task",
        affected_files=["app/main.py.bak"],
    )
    assert classifier._determine_coupling(inp_exact) != Coupling.M1_ISOLATED
    assert classifier._determine_coupling(inp_suffix) == Coupling.M1_ISOLATED
