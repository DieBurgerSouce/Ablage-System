# -*- coding: utf-8 -*-
"""Shared priority conversion utilities for Celery task dispatch."""


def int_to_priority_str(p: int) -> str:
    """Konvertiert numerische Prioritaet (1-10) in Task-String (high/normal/low).

    Mapping:
        8-10 -> "high"
        4-7  -> "normal"
        1-3  -> "low"

    Consistent with task_service.py._get_priority_value() inverse mapping:
        "high" -> 9, "normal" -> 5, "low" -> 1
    """
    if p >= 8:
        return "high"
    if p >= 4:
        return "normal"
    return "low"
