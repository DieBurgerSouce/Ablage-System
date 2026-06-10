"""W1: zentrale GPU-OOM-Erkennung (app.core.gpu_errors)."""

import pytest

from app.core.gpu_errors import is_oom_error


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("CUDA out of memory. Tried to allocate 2.00 GiB", True),
        ("cannot allocate memory", True),
        ("OOM when allocating tensor", True),
        ("memory allocation failed on device 0", True),
        ("Ungueltige Eingabe", False),
        ("Connection refused", False),
        ("Datei nicht gefunden", False),
    ],
)
def test_is_oom_error_string_heuristic(message: str, expected: bool) -> None:
    assert is_oom_error(RuntimeError(message)) is expected


def test_is_oom_error_handles_arbitrary_exceptions() -> None:
    assert is_oom_error(ValueError("out of memory")) is True
    assert is_oom_error(Exception("alles gut")) is False
