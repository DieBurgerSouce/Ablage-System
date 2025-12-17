# -*- coding: utf-8 -*-
"""
E-Invoice Mapping Module.

Konvertiert zwischen:
- ExtractedInvoiceData <-> ZUGFeRD XML
- ExtractedInvoiceData <-> XRechnung XML (CII/UBL)

Die Mapper garantieren bidirektionale Konvertierung:
- Parsen: XML/PDF -> ExtractedInvoiceData
- Generieren: ExtractedInvoiceData -> XML/PDF

Verfuegbare Mapper:
- ZUGFeRDMapper: ZUGFeRD 2.x (CII-basiert)
- XRechnungUBLMapper: XRechnung 3.0.2 im UBL 2.1 Format
"""

from .zugferd_mapper import ZUGFeRDMapper, get_zugferd_mapper
from .xrechnung_ubl_mapper import XRechnungUBLMapper, get_ubl_mapper

__all__ = [
    "ZUGFeRDMapper",
    "get_zugferd_mapper",
    "XRechnungUBLMapper",
    "get_ubl_mapper",
]
