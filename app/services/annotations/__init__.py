"""Annotations Service Package.

Verwaltet PDF/Bild-Annotationen mit Threading, @-Mentions und Approval-Markierungen.
"""
from app.services.annotations.annotation_service import AnnotationService

__all__ = ["AnnotationService"]
