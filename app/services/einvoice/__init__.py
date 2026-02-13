# -*- coding: utf-8 -*-
"""
E-Invoice Service Package - E-Rechnung 2025 Compliance.

Bietet Unterstuetzung fuer:
- ZUGFeRD 2.x (Factur-X) PDF Parsing und Generierung
- XRechnung 3.0.2 (CII/UBL) XML Generierung mit vollstaendiger BR-DE Unterstuetzung
- KoSIT Validator Integration
- Peppol Netzwerk Versand (AS4)
- Eingehende E-Rechnungen Empfang und Verarbeitung
- Mapping zwischen ExtractedInvoiceData und E-Invoice Standards

Komponenten:
- parser_service: ZUGFeRD-PDFs und XRechnung-XMLs parsen
- generator_service: E-Rechnungen generieren (ZUGFeRD/XRechnung)
- xrechnung_generator: Vollstaendige XRechnung 3.0 Generierung
- validator_service: KoSIT Validierung
- peppol_sender_service: Versand ueber Peppol Netzwerk
- receiver_service: Empfang und Verarbeitung eingehender E-Rechnungen
- mustang_client: Java Microservice Client fuer XRechnung 3.0.2

E-Rechnung 2025 Features:
- XRechnung 3.0.2 konform (EN 16931)
- Alle BR-DE Geschaeftsregeln
- Peppol BIS 3.0 Versand
- Automatische Validierung
- Entity-Linking fuer eingehende Rechnungen
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .parser_service import EInvoiceParserService
    from .generator_service import EInvoiceGeneratorService
    from .validator_service import EInvoiceValidatorService
    from .mustang_client import MustangClient
    from .peppol_sender_service import PeppolSenderService
    from .receiver_service import EInvoiceReceiverService
    from .xrechnung_generator import XRechnungGenerator

# Lazy imports fuer bessere Startup-Performance
from .mustang_client import (
    MustangClient,
    MustangError,
    MustangConnectionError,
    MustangValidationError,
    get_mustang_client,
    check_mustang_availability,
)

from .validator_service import (
    EInvoiceValidatorService,
    ValidationResult,
    ValidationMessage,
    ValidatorType,
    ValidationSeverity,
    get_validator_service,
)

from .zugferd_embedder import (
    ZUGFeRDEmbedder,
    get_zugferd_embedder,
)

from .zugferd_validator import (
    ZUGFeRDValidator,
    get_zugferd_validator,
    ZUGFeRDProfile,
)

try:
    from .peppol_sender_service import (
        PeppolSenderService,
        PeppolEndpoint,
        TransmissionResult,
        get_peppol_sender,
    )
except ImportError:
    PeppolSenderService = None  # type: ignore[assignment,misc]
    PeppolEndpoint = None  # type: ignore[assignment,misc]
    TransmissionResult = None  # type: ignore[assignment,misc]
    get_peppol_sender = None  # type: ignore[assignment]

from .receiver_service import (
    EInvoiceReceiverService,
    ProcessingResult,
    ExtractedInvoiceInfo,
    IncomingInvoiceStatus,
    get_receiver_service,
)

from .xrechnung_generator import (
    XRechnungGenerator,
    XRechnungData,
    XRechnungParty,
    XRechnungAddress,
    XRechnungLineItem,
    XRechnungTaxBreakdown,
    InvoiceTypeCode,
    VATCategoryCode,
    get_xrechnung_generator,
)

__all__ = [
    # Core Services
    "EInvoiceParserService",
    "EInvoiceGeneratorService",
    "EInvoiceValidatorService",

    # Mustang Client
    "MustangClient",
    "MustangError",
    "MustangConnectionError",
    "MustangValidationError",
    "get_mustang_client",
    "check_mustang_availability",

    # Validator
    "ValidationResult",
    "ValidationMessage",
    "ValidatorType",
    "ValidationSeverity",
    "get_validator_service",

    # ZUGFeRD Embedder
    "ZUGFeRDEmbedder",
    "get_zugferd_embedder",

    # ZUGFeRD Validator
    "ZUGFeRDValidator",
    "get_zugferd_validator",
    "ZUGFeRDProfile",

    # Peppol Sender (E-Rechnung 2025)
    "PeppolSenderService",
    "PeppolEndpoint",
    "TransmissionResult",
    "get_peppol_sender",

    # E-Invoice Receiver (E-Rechnung 2025)
    "EInvoiceReceiverService",
    "ProcessingResult",
    "ExtractedInvoiceInfo",
    "IncomingInvoiceStatus",
    "get_receiver_service",

    # XRechnung Generator (E-Rechnung 2025)
    "XRechnungGenerator",
    "XRechnungData",
    "XRechnungParty",
    "XRechnungAddress",
    "XRechnungLineItem",
    "XRechnungTaxBreakdown",
    "InvoiceTypeCode",
    "VATCategoryCode",
    "get_xrechnung_generator",
]
