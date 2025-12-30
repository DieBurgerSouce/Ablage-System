"""
Personal-Modul API - Enterprise HR.

Beinhaltet alle HR-bezogenen Endpunkte:
- Mitarbeiter-Verwaltung
- Abteilungen & Positionen
- Arbeitsvertraege
- Urlaubsantraege & Abwesenheiten
- Zeiterfassung
- Weiterbildungen
- Beurteilungen
- Onboarding
- HR-Dokumente

Alle Antworten auf Deutsch.
"""

from fastapi import APIRouter

from .employees import router as employees_router
from .departments import router as departments_router
from .positions import router as positions_router

# Haupt-Router fuer Personal-Modul
router = APIRouter(prefix="/personal", tags=["Personal"])

# Sub-Router einbinden
router.include_router(employees_router)
router.include_router(departments_router)
router.include_router(positions_router)

# Weitere Router werden in spaetereren Phasen hinzugefuegt:
# from .contracts import router as contracts_router
# from .leave import router as leave_router
# from .absences import router as absences_router
# from .time import router as time_router
# from .trainings import router as trainings_router
# from .reviews import router as reviews_router
# from .onboarding import router as onboarding_router
# from .documents import router as hr_documents_router

__all__ = ["router"]
