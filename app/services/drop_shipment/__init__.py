"""
Streckengeschäft (Drop Shipment) & Dreiecksgeschäft Module

Automatische Erkennung und Klassifikation von:
- Streckengeschäften (Drop Shipments)
- Innergemeinschaftlichen Dreiecksgeschäften (§25b UStG)
- Reihengeschäften (Chain Transactions)

Rechtliche Grundlagen:
- §3 Abs. 6a UStG: Reihengeschäft - Zuordnung der bewegten Lieferung
- §25b UStG: Innergemeinschaftliches Dreiecksgeschäft - Vereinfachungsregelung
- BMF-Schreiben 25.04.2023: Nachweispflichten

Features:
- Automatische Dokumentenklassifikation auf Kopf- und Positionsebene
- Konfidenz-basierte Erkennung mit Definitiv- und Wahrscheinlichkeits-Indikatoren
- DATEV-Integration mit korrekter Kontenzuordnung (SKR03/SKR04)
- ZUGFeRD/XRechnung-Validierung (VAT Category Codes, Schematron-Regeln)
- ZM-Überwachung (Zusammenfassende Meldung) mit Frist-Tracking
- Belegnachweis-Verwaltung (CMR, Gelangensbestätigung, etc.)
"""

from .models import (
    # Enums
    DropShipmentClassificationType,
    ClassificationSource,
    EuTransactionType,
    TaxTreatment,
    PartyRole,
    ProofDocumentType,
    ProofValidationStatus,
    VatCategoryCode,
    ConfidenceLevel,
    DropShipmentIndicator,
    # Models
    Address,
    DetectionReason,
    TransactionParty,
    DropShipmentLineItem,
    ProofDocument,
    DropShipmentClassification,
)

from .schemas import (
    # Requests
    ClassifyDocumentRequest,
    ConfirmClassificationRequest,
    OverrideClassificationRequest,
    LinkProofDocumentRequest,
    MarkZmReportedRequest,
    DatevExportRequest,
    BulkActionRequest,
    DropShipmentListFilter,
    # Responses
    ClassifyDocumentResponse,
    DropShipmentListResponse,
    ZmPendingResponse,
    DatevExportResponse,
    BulkActionResponse,
    DocumentFlowValidationResponse,
    RelatedDocumentsResponse,
    DropShipmentDashboardStats,
)

from .datev_constants import (
    DATEV_DROP_SHIPMENT_ACCOUNTS,
    DATEV_TAX_CODES,
    USTVA_KENNZAHLEN,
    EU_MEMBER_STATES,
    DatevAccountMapping,
    get_datev_account,
    get_datev_tax_code,
    format_vat_id_for_datev,
    is_eu_vat_id,
    extract_country_from_vat_id,
)

__all__ = [
    # Enums
    "DropShipmentClassificationType",
    "ClassificationSource",
    "EuTransactionType",
    "TaxTreatment",
    "PartyRole",
    "ProofDocumentType",
    "ProofValidationStatus",
    "VatCategoryCode",
    "ConfidenceLevel",
    "DropShipmentIndicator",
    # Core Models
    "Address",
    "DetectionReason",
    "TransactionParty",
    "DropShipmentLineItem",
    "ProofDocument",
    "DropShipmentClassification",
    # Request Schemas
    "ClassifyDocumentRequest",
    "ConfirmClassificationRequest",
    "OverrideClassificationRequest",
    "LinkProofDocumentRequest",
    "MarkZmReportedRequest",
    "DatevExportRequest",
    "BulkActionRequest",
    "DropShipmentListFilter",
    # Response Schemas
    "ClassifyDocumentResponse",
    "DropShipmentListResponse",
    "ZmPendingResponse",
    "DatevExportResponse",
    "BulkActionResponse",
    "DocumentFlowValidationResponse",
    "RelatedDocumentsResponse",
    "DropShipmentDashboardStats",
    # DATEV Constants & Helpers
    "DATEV_DROP_SHIPMENT_ACCOUNTS",
    "DATEV_TAX_CODES",
    "USTVA_KENNZAHLEN",
    "EU_MEMBER_STATES",
    "DatevAccountMapping",
    "get_datev_account",
    "get_datev_tax_code",
    "format_vat_id_for_datev",
    "is_eu_vat_id",
    "extract_country_from_vat_id",
]
