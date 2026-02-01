# -*- coding: utf-8 -*-
"""
E-Invoice Service Package.

Bietet Unterstuetzung fuer:
- ZUGFeRD 2.x (Factur-X) PDF Parsing und Generierung
- XRechnung 3.0.2 (CII/UBL) XML Generierung
- KoSIT Validator Integration
- Mapping zwischen ExtractedInvoiceData und E-Invoice Standards

Komponenten:
- parser_service: ZUGFeRD-PDFs und XRechnung-XMLs parsen
- generator_service: E-Rechnungen generieren
- validator_service: KoSIT Validierung
- mustang_client: Java Microservice Client fuer XRechnung 3.0.2
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .parser_service import EInvoiceParserService
    from .generator_service import EInvoiceGeneratorService
    from .validator_service import EInvoiceValidatorService
    from .mustang_client import MustangClient

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

__all__ = [
    # Services
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
]
