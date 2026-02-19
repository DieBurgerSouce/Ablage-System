# -*- coding: utf-8 -*-
"""
Kontierung Package.

Automatische Zuordnung von Dokumentdaten (OCR) zu DATEV SKR03/SKR04-Konten.
Erstellt GoBD-konforme JournalEntry + JournalEntryLine Datensaetze.

Oeffentliche API:
    AutoKontierungService  - Hauptservice fuer automatische Kontierung
    KontierungResult       - Ergebnis einer Kontierungsoperation
    KontierungSuggestion   - Kontierungsvorschlag ohne Datenbankschreibung
    get_auto_kontierung_service - FastAPI Dependency Injection Helper
"""

from app.services.kontierung.auto_kontierung_service import (
    AutoKontierungService,
    KontierungResult,
    KontierungSuggestion,
    get_auto_kontierung_service,
)

__all__ = [
    "AutoKontierungService",
    "KontierungResult",
    "KontierungSuggestion",
    "get_auto_kontierung_service",
]
