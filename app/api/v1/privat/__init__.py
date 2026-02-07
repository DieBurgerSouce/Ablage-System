# -*- coding: utf-8 -*-
"""
Privat-Modul API Router.

Stellt spezialisierte Endpunkte fuer das Privat-Modul bereit.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/privat", tags=["privat"])

# Sub-Router werden hier registriert
# from . import tax
# router.include_router(tax.router)
