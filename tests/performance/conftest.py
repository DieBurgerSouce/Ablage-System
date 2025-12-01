# -*- coding: utf-8 -*-
"""
Pytest Configuration fuer Performance Tests.
"""

import pytest


def pytest_configure(config):
    """Registriere Custom Marker."""
    config.addinivalue_line(
        "markers",
        "performance: Performance/Benchmark Tests"
    )
    config.addinivalue_line(
        "markers",
        "benchmark: Benchmark Tests mit Zeitmessung"
    )
