# -*- coding: utf-8 -*-
"""
Evaluation Services für Ablage-System OCR.

Dieses Modul enthält Services für die systematische Evaluierung
von OCR-Backends, insbesondere PaddleOCR-VL 0.9B.

Feinpoliert und durchdacht - Enterprise-grade OCR Evaluation.
"""

from app.services.evaluation.availability_checker import (
    AvailabilityChecker,
    AvailabilityResult,
    DependencyReport,
    get_availability_checker,
)

__all__ = [
    "AvailabilityChecker",
    "AvailabilityResult",
    "DependencyReport",
    "get_availability_checker",
]
