# -*- coding: utf-8 -*-
"""
DATEV Export Module.

Stellt DATEV Buchungsstapel-Export für das Ablage-System bereit.

Features:
- DATEV Buchungsstapel CSV Export (Version 700)
- Unterstützung für SKR03 und SKR04 Kontenrahmen
- Automatische Steuerschluessel-Ermittlung
- Vendor-spezifische Kontozuordnung
- Export-Historie und Audit-Trail

Verwendung:
    from app.services.datev import get_datev_export_service

    service = get_datev_export_service()
    csv_bytes, export = await service.export_buchungsstapel(
        db=session,
        user_id=user_uuid,
        document_ids=[uuid1, uuid2]
    )
"""

from .buchungsstapel_writer import BuchungsstapelWriter, create_buchungsstapel_writer
from .export_service import DATEVExportService, get_datev_export_service
from .kontenrahmen import SKR03, SKR04, BaseKontenrahmen
from .mapping import DATEVInvoiceMapper, TaxCodeMapper

__all__ = [
    # Export Service
    "DATEVExportService",
    "get_datev_export_service",
    # Writer
    "BuchungsstapelWriter",
    "create_buchungsstapel_writer",
    # Kontenrahmen
    "BaseKontenrahmen",
    "SKR03",
    "SKR04",
    # Mapper
    "DATEVInvoiceMapper",
    "TaxCodeMapper",
]
