# -*- coding: utf-8 -*-
"""
E-Invoice Mapping Module.

Konvertiert zwischen:
- ExtractedInvoiceData <-> ZUGFeRD XML
- ExtractedInvoiceData <-> XRechnung XML (CII/UBL)

Die Mapper garantieren bidirektionale Konvertierung:
- Parsen: XML/PDF -> ExtractedInvoiceData
- Generieren: ExtractedInvoiceData -> XML/PDF
"""

__all__ = [
    "ZUGFeRDMapper",
    "XRechnungMapper",
]
