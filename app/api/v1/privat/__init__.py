# -*- coding: utf-8 -*-
"""
Privat-Modul API Router.

Stellt die Endpunkte des Privat-Bereichs bereit (Dashboard, Spaces, Dokumente,
Immobilien, Fahrzeuge, Versicherungen, Finanzen, Fristen, Notfallzugriff).

F-P4-001 (Perception-Audit 2026-07-12): Die eigentlichen Routen lagen bis dato
in einer Schwester-Datei ``privat.py`` NEBEN diesem Package. Da Python bei
Namensgleichheit das Package ``privat/`` dem Modul ``privat.py`` vorzieht,
importierte ``main.py`` (``from app.api.v1.privat import router``) diesen
frueher LEEREN Package-Router — der 3637-Zeilen-Router war nie gemountet und
ALLE ``/api/v1/privat/*``-Endpunkte lieferten 404 (Privat-Dashboard,
Familienmitglied-Flow tot). Das Modul wurde nach ``privat/routes.py``
verschoben und wird hier re-exportiert; der Tax-Sub-Router bleibt separat.
"""

from app.api.v1.privat.routes import router

__all__ = ["router"]
