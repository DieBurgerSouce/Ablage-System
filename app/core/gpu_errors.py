"""GPU-Fehler-Erkennung (Welle 1 Pipeline-Robustheit).

Zentrale OOM-Erkennung, extrahiert aus ``ocr_tasks._is_oom_error``, damit
``backend_manager`` dieselbe Logik nutzen kann statt eines generischen
``RuntimeError``-Catch-alls.
"""

from __future__ import annotations

OOM_INDICATORS = (
    "out of memory",
    "cuda out of memory",
    "oom",
    "memory allocation",
    "cannot allocate",
)


def is_oom_error(exception: Exception) -> bool:
    """Prüfe, ob eine Exception ein GPU-OOM-Fehler ist.

    torch ist optional (CPU-only-Umgebungen): ohne torch greift nur die
    String-Heuristik.
    """
    try:
        import torch  # noqa: PLC0415 - optionale Abhaengigkeit, lazy

        if torch.cuda.is_available() and isinstance(
            exception, torch.cuda.OutOfMemoryError
        ):
            return True
    except ImportError:
        pass  # torch nicht installiert -> nur die String-Heuristik unten greift

    error_msg = str(exception).lower()
    return any(indicator in error_msg for indicator in OOM_INDICATORS)
