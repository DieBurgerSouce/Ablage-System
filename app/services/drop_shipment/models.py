"""
Streckengeschäft (Drop Shipment) & Dreiecksgeschäft Models

Rechtliche Grundlagen:
- §3 Abs. 6a UStG: Reihengeschäft - nur eine bewegte Lieferung in der Kette
- §25b UStG: Innergemeinschaftliches Dreiecksgeschäft - Vereinfachungsregelung
- BMF-Schreiben 25.04.2023: Nachweispflichten für Transportverantwortlichkeit
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# ENUMS
# =============================================================================

class DropShipmentClassificationType(str, Enum):
    """Klassifikationstyp des Geschäfts"""
    DROP_SHIPMENT = "drop_shipment"       # Einfaches Streckengeschäft
    TRIANGULAR = "triangular"             # Innergemeinschaftliches Dreiecksgeschäft §25b
    CHAIN_TRANSACTION = "chain_transaction"  # Reihengeschäft mit >3 Beteiligten
    DOMESTIC = "domestic"                 # Inlandsgeschäft (kein Streckengeschäft)
    UNKNOWN = "unknown"                   # Noch nicht klassifiziert


class ClassificationSource(str, Enum):
    """Quelle der Klassifikation"""
    AUTOMATIC = "automatic"    # Automatische OCR/Regel-basierte Erkennung
    MANUAL = "manual"          # Manuelle Klassifikation durch Benutzer
    ERP_IMPORT = "erp_import"  # Import aus ERP-System
    ZUGFERD = "zugferd"        # Aus ZUGFeRD/XRechnung-Metadaten


class EuTransactionType(str, Enum):
    """EU-Transaktionstyp"""
    INTRA_COMMUNITY = "intra_community"  # Innergemeinschaftlich
    DOMESTIC = "domestic"                 # Inländisch
    EXPORT = "export"                     # Drittland-Export
    IMPORT = "import"                     # Drittland-Import


class TaxTreatment(str, Enum):
    """Steuerliche Behandlung"""
    TAX_FREE_IC = "tax_free_ic"        # Steuerfrei innergemeinschaftlich §4 Nr. 1b
    REVERSE_CHARGE = "reverse_charge"   # Steuerschuldnerschaft Empfänger §13b
    STANDARD_VAT = "standard_vat"       # Normale USt
    TRIANGULAR_25B = "triangular_25b"   # Dreiecksgeschäft §25b


class PartyRole(str, Enum):
    """Rolle einer Partei in der Transaktion"""
    FIRST_SUPPLIER = "first_supplier"      # Erster Lieferer (Ursprung)
    INTERMEDIATE = "intermediate"          # Zwischenhändler
    FINAL_RECIPIENT = "final_recipient"    # Letzter Abnehmer (Endkunde)


class ProofDocumentType(str, Enum):
    """Belegnachweis-Typ"""
    CMR = "cmr"                                # CMR-Frachtbrief
    GELANGENSBESTAETIGUNG = "gelangensbestaetigung"  # §17b UStDV
    SPEDITIONSAUFTRAG = "speditionsauftrag"  # Speditionsauftrag
    SPEDITEURSBESCHEINIGUNG = "spediteursbescheinigung"
    LIEFERSCHEIN = "lieferschein"
    VERSANDBESTAETIGUNG = "versandbestaetigung"


class ProofValidationStatus(str, Enum):
    """Validierungsstatus für Belegnachweise"""
    PENDING = "pending"      # Noch nicht geprüft
    VALID = "valid"          # Vollständig und gültig
    INCOMPLETE = "incomplete"  # Unvollständig
    INVALID = "invalid"      # Ungültig


class VatCategoryCode(str, Enum):
    """ZUGFeRD VAT Category Codes nach UNTDID 5305"""
    K = "K"    # Intra-community supply
    AE = "AE"  # VAT Reverse Charge
    G = "G"    # Free export
    S = "S"    # Standard rate
    Z = "Z"    # Zero rated
    E = "E"    # Exempt
    O = "O"    # Outside scope


class ConfidenceLevel(str, Enum):
    """Konfidenz-Level für automatische Erkennung"""
    DEFINITIVE = "definitive"  # 100%
    HIGH = "high"              # 90-99%
    MEDIUM = "medium"          # 70-89%
    LOW = "low"                # 50-69%
    UNCERTAIN = "uncertain"    # <50%


class DropShipmentIndicator(str, Enum):
    """Erkennungsindikatoren"""
    POSITION_TYPE_TAS = "position_type_tas"
    EXTERNAL_PROCUREMENT = "external_procurement"
    PARAGRAPH_25B_REFERENCE = "paragraph_25b_reference"
    THREE_EU_VAT_IDS = "three_eu_vat_ids"
    EMPTY_WAREHOUSE_FIELD = "empty_warehouse_field"
    ADDRESS_MISMATCH = "address_mismatch"
    CMR_THIRD_PARTY_RECIPIENT = "cmr_third_party_recipient"
    NO_VAT_REVERSE_CHARGE = "no_vat_reverse_charge"
    DROP_SHIP_WAREHOUSE = "drop_ship_warehouse"
    ZUGFERD_SHIP_TO_DIFFERS = "zugferd_ship_to_differs"


# =============================================================================
# BASE MODELS
# =============================================================================

class Address(BaseModel):
    """Adresse"""
    id: Optional[UUID] = None
    street: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    country: str = Field(..., min_length=2, max_length=2)  # ISO 2-letter
    country_name: Optional[str] = None


class DetectionReason(BaseModel):
    """Erkennungsgrund für die Klassifikation"""
    indicator: DropShipmentIndicator
    confidence: float = Field(..., ge=0.0, le=1.0)
    extracted_value: Optional[str] = None
    field_location: Optional[str] = None
    description: str


class TransactionParty(BaseModel):
    """Beteiligte Partei in der Transaktion"""
    id: Optional[UUID] = None
    classification_id: Optional[UUID] = None
    party_role: PartyRole
    company_name: str
    vat_id: Optional[str] = None
    vat_id_country: Optional[str] = Field(None, min_length=2, max_length=2)
    address: Optional[Address] = None
    is_transport_responsible: bool = False
    created_at: Optional[datetime] = None

    @field_validator('vat_id')
    @classmethod
    def validate_vat_id(cls, v: Optional[str]) -> Optional[str]:
        """Validiert USt-IdNr. Format"""
        if v is None:
            return v
        # Entferne Leerzeichen und normalisiere
        v = v.replace(" ", "").upper()
        if len(v) < 4:
            raise ValueError("USt-IdNr. zu kurz")
        return v


class DropShipmentLineItem(BaseModel):
    """Positionsebene für Mischbelege"""
    id: Optional[UUID] = None
    classification_id: Optional[UUID] = None
    line_item_number: int
    description: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    is_drop_shipment: bool
    warehouse_code: Optional[str] = None  # NULL = Streckenposition
    supplier_id: Optional[UUID] = None
    ship_to_address_id: Optional[UUID] = None
    datev_account: Optional[str] = None
    datev_tax_code: Optional[str] = None
    created_at: Optional[datetime] = None


class ProofDocument(BaseModel):
    """Belegnachweis-Dokument"""
    id: Optional[UUID] = None
    classification_id: Optional[UUID] = None
    proof_type: ProofDocumentType
    document_id: Optional[UUID] = None
    document_name: Optional[str] = None
    is_complete: bool = False
    validation_status: ProofValidationStatus = ProofValidationStatus.PENDING
    missing_fields: Optional[list[str]] = None
    validation_notes: Optional[str] = None
    created_at: Optional[datetime] = None


# =============================================================================
# MAIN CLASSIFICATION MODEL
# =============================================================================

class DropShipmentClassification(BaseModel):
    """Hauptklassifikation eines Dokuments"""
    id: Optional[UUID] = None
    document_id: UUID
    classification_type: DropShipmentClassificationType
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    confidence_level: ConfidenceLevel
    classification_source: ClassificationSource
    
    # Bestätigung
    is_confirmed: bool = False
    confirmed_by: Optional[UUID] = None
    confirmed_at: Optional[datetime] = None
    
    # EU-spezifisch
    eu_transaction_type: Optional[EuTransactionType] = None
    moving_delivery_assigned_to: Optional[str] = None
    tax_treatment: Optional[TaxTreatment] = None
    
    # ZM (Zusammenfassende Meldung)
    zm_relevant: bool = False
    zm_reported: bool = False
    zm_report_date: Optional[date] = None
    zm_deadline: Optional[date] = None
    
    # DATEV
    suggested_datev_account: Optional[str] = None
    suggested_datev_tax_code: Optional[str] = None
    
    # Erkennungsgründe
    detection_reasons: list[DetectionReason] = Field(default_factory=list)
    
    # Verknüpfte Daten
    parties: list[TransactionParty] = Field(default_factory=list)
    line_items: list[DropShipmentLineItem] = Field(default_factory=list)
    proof_documents: list[ProofDocument] = Field(default_factory=list)
    
    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def get_confidence_level(self) -> ConfidenceLevel:
        """Bestimmt Konfidenz-Level basierend auf Score"""
        if self.confidence_score >= 1.0:
            return ConfidenceLevel.DEFINITIVE
        elif self.confidence_score >= 0.9:
            return ConfidenceLevel.HIGH
        elif self.confidence_score >= 0.7:
            return ConfidenceLevel.MEDIUM
        elif self.confidence_score >= 0.5:
            return ConfidenceLevel.LOW
        return ConfidenceLevel.UNCERTAIN

    def has_complete_proofs(self) -> bool:
        """Prüft ob alle Belegnachweise vollständig sind"""
        return all(
            proof.validation_status == ProofValidationStatus.VALID
            for proof in self.proof_documents
        )

    def count_eu_countries(self) -> int:
        """Zählt beteiligte EU-Länder"""
        countries = {
            party.vat_id_country
            for party in self.parties
            if party.vat_id_country
        }
        return len(countries)

