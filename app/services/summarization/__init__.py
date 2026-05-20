"""Dokumenten-Zusammenfassungs-Modul.

Generiert automatische deutsche Zusammenfassungen, Schluesselwoerter
und Einzeiler fuer verarbeitete Dokumente mittels lokalem LLM.
"""

from app.services.summarization.summary_service import SummaryService

__all__ = ["SummaryService"]
