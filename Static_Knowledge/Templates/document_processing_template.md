# Document Processing Template

**Purpose:** Standard template for implementing new document processing workflows in Ablage-System
**Last Updated:** 2025-01-20
**Maintained By:** Backend Team

---

## Template Overview

Use this template when adding new document types (e.g., contracts, delivery notes, customs declarations) to the Ablage-System processing pipeline. This ensures consistency with existing workflows and compliance requirements.

**When to Use This Template:**
- ✅ Adding new document type support
- ✅ Implementing custom extraction rules
- ✅ Creating document-specific validation
- ✅ Building specialized workflows

**Prerequisites:**
- [ ] Document type requirements documented
- [ ] Sample documents (minimum 50) collected
- [ ] German business rules identified
- [ ] GDPR implications assessed

---

## Section 1: Document Type Definition

### 1.1 Basic Information

**Replace placeholder values with your document-specific information:**

```yaml
document_type:
  name: "DOCUMENT_TYPE_NAME"  # e.g., "Lieferschein", "Vertrag", "Mahnung"
  display_name_de: "German Display Name"
  display_name_en: "English Display Name (optional)"
  category: "CATEGORY"  # Options: invoice, contract, delivery_note, tax_document, other

  description: |
    Brief description of the document type and its purpose in German business context.
    Include typical use cases and why processing this document type is important.

  common_variations:
    - "Variation 1"  # e.g., "Rechnung", "Invoice", "RG"
    - "Variation 2"
    - "Variation 3"

  regulatory_framework:
    - "§X Law Name"  # e.g., "§14 UStG", "§238 HGB"
    - "GDPR Article X"
    - "Industry Standard Y"
```

**Example (Invoice):**
```yaml
document_type:
  name: "rechnung"
  display_name_de: "Rechnung"
  display_name_en: "Invoice"
  category: "invoice"

  description: |
    Deutsche Handelsrechnung gemäß §14 UStG. Dokumentiert Lieferung oder sonstige
    Leistung mit allen steuerlich erforderlichen Angaben. Aufbewahrungspflicht: 10 Jahre.

  common_variations:
    - "Rechnung"
    - "Invoice"
    - "Faktura"
    - "RG"
    - "RE"

  regulatory_framework:
    - "§14 UStG (Rechnungsanforderungen)"
    - "§147 AO (Aufbewahrungspflicht)"
    - "GDPR Art. 17 (Löschpflicht nach Ablauf)"
```

### 1.2 Document Characteristics

**Define visual and structural characteristics:**

```python
# app/services/document_types/DOCUMENT_TYPE_NAME.py

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

class DocumentTypeCharacteristics(BaseModel):
    """Visual and structural characteristics for document identification."""

    # Layout complexity (affects OCR backend selection)
    has_tables: bool = Field(
        default=False,
        description="Document contains tabular data"
    )

    has_multi_column: bool = Field(
        default=False,
        description="Document has multi-column layout"
    )

    has_handwriting: bool = Field(
        default=False,
        description="Document may contain handwritten annotations"
    )

    has_stamps_signatures: bool = Field(
        default=False,
        description="Document typically includes stamps or signatures"
    )

    # Content characteristics
    typical_page_count: tuple[int, int] = Field(
        default=(1, 3),
        description="Expected page count range (min, max)"
    )

    language: str = Field(
        default="de",
        description="Primary language (de, en, de+en)"
    )

    text_density: str = Field(
        default="medium",
        description="Options: low, medium, high"
    )

    # Quality expectations
    expected_scan_quality: str = Field(
        default="medium",
        description="Options: low (fax), medium (office scan), high (professional)"
    )

    ocr_confidence_threshold: float = Field(
        default=0.85,
        description="Minimum OCR confidence for acceptance (0.0-1.0)"
    )


# Example instance
RECHNUNG_CHARACTERISTICS = DocumentTypeCharacteristics(
    has_tables=True,
    has_multi_column=False,
    has_handwriting=False,
    has_stamps_signatures=True,
    typical_page_count=(1, 2),
    language="de",
    text_density="medium",
    expected_scan_quality="medium",
    ocr_confidence_threshold=0.85
)
```

---

## Section 2: Entity Extraction Rules

### 2.1 Required Entities

**Define all entities that MUST be extracted from this document type:**

```python
from pydantic import BaseModel, validator
from typing import Optional
from datetime import date
from decimal import Decimal

class DocumentTypeEntities(BaseModel):
    """Required and optional entities for DOCUMENT_TYPE_NAME."""

    # Document identification
    document_number: str = Field(
        ...,  # Required field
        description="Unique document identifier",
        min_length=1,
        max_length=50,
        example="RE-2025-00123"
    )

    document_date: date = Field(
        ...,
        description="Document issue date (DD.MM.YYYY format)",
        example="2025-01-20"
    )

    # Parties involved
    issuer_name: str = Field(
        ...,
        description="Name of document issuer (company or person)",
        example="Mustermann GmbH"
    )

    issuer_address: Optional[str] = Field(
        None,
        description="Full address of issuer",
        example="Musterstraße 123, 12345 Musterstadt"
    )

    issuer_ust_id: Optional[str] = Field(
        None,
        description="USt-IdNr of issuer (DExxxxxxxxx)",
        pattern=r"^DE\d{9}$",
        example="DE123456789"
    )

    recipient_name: str = Field(
        ...,
        description="Name of document recipient",
        example="Kunde AG"
    )

    recipient_address: Optional[str] = Field(
        None,
        description="Full address of recipient"
    )

    # Financial information (if applicable)
    total_amount: Optional[Decimal] = Field(
        None,
        description="Total amount in EUR",
        ge=0,  # Greater than or equal to 0
        decimal_places=2,
        example=1234.56
    )

    currency: Optional[str] = Field(
        "EUR",
        description="Currency code (ISO 4217)",
        pattern=r"^[A-Z]{3}$"
    )

    vat_amount: Optional[Decimal] = Field(
        None,
        description="VAT amount in EUR",
        ge=0,
        decimal_places=2
    )

    # Custom validators
    @validator("document_date")
    def validate_document_date(cls, v: date) -> date:
        """Ensure document date is not in the future."""
        from datetime import date as dt_date
        if v > dt_date.today():
            raise ValueError("Dokumentdatum darf nicht in der Zukunft liegen")
        return v

    @validator("issuer_ust_id")
    def validate_ust_id_checksum(cls, v: Optional[str]) -> Optional[str]:
        """Validate USt-IdNr format and checksum (if provided)."""
        if v is None:
            return v

        if not re.match(r"^DE\d{9}$", v):
            raise ValueError("USt-IdNr Format ungültig (erwartet: DExxxxxxxxx)")

        # Optional: Add BZSt API validation for production
        # validate_ust_id_with_bzst(v)

        return v

    @validator("total_amount", "vat_amount")
    def validate_amounts(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        """Ensure amounts are positive and have max 2 decimal places."""
        if v is not None:
            if v < 0:
                raise ValueError("Betrag darf nicht negativ sein")
            if v.as_tuple().exponent < -2:
                raise ValueError("Betrag darf maximal 2 Nachkommastellen haben")
        return v


# Example instance
rechnung_entities = DocumentTypeEntities(
    document_number="RE-2025-00123",
    document_date=date(2025, 1, 20),
    issuer_name="Mustermann GmbH",
    issuer_address="Musterstraße 123, 12345 Musterstadt",
    issuer_ust_id="DE123456789",
    recipient_name="Kunde AG",
    recipient_address="Kundenweg 456, 54321 Kundenstadt",
    total_amount=Decimal("1234.56"),
    currency="EUR",
    vat_amount=Decimal("234.56")
)
```

### 2.2 Extraction Rules (Regex Patterns)

**Define regex patterns for extracting entities:**

```python
# app/services/document_types/DOCUMENT_TYPE_NAME_rules.py

from typing import Dict, List
import re

class DocumentTypeExtractionRules:
    """Regex patterns and extraction rules for DOCUMENT_TYPE_NAME."""

    # Document number patterns (order by specificity)
    DOCUMENT_NUMBER_PATTERNS = [
        # Pattern 1: Explicit label
        r"(?:Rechnungsnummer|Invoice No\.|RE-Nr\.?|RG-Nr\.?):?\s*([A-Z0-9\-/]+)",

        # Pattern 2: Standalone format
        r"\b(RE-\d{4}-\d{5})\b",

        # Pattern 3: Generic fallback
        r"(?:Nummer|Number|Nr\.?):?\s*([A-Z0-9\-/]{5,20})",
    ]

    # Date patterns (German DD.MM.YYYY format)
    DATE_PATTERNS = [
        r"(?:Rechnungsdatum|Datum|Date):?\s*(\d{1,2}\.\d{1,2}\.\d{2,4})",
        r"\b(\d{1,2}\.\d{1,2}\.\d{4})\b",  # Standalone date
    ]

    # USt-IdNr pattern
    UST_ID_PATTERN = r"(?:USt-IdNr\.?|VAT ID):?\s*(DE\d{9})"

    # IBAN pattern
    IBAN_PATTERN = r"\b(DE\d{2}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{2})\b"

    # Amount patterns (German format: 1.234,56)
    AMOUNT_PATTERNS = {
        "total": [
            r"(?:Gesamtbetrag|Summe|Total|Endbetrag):?\s*€?\s*([\d\.]+,\d{2})\s*€?",
            r"(?:Zu zahlen|Zahlbetrag):?\s*€?\s*([\d\.]+,\d{2})\s*€?",
        ],
        "vat": [
            r"(?:MwSt\.?|Mehrwertsteuer|VAT|Umsatzsteuer):?\s*€?\s*([\d\.]+,\d{2})\s*€?",
            r"(?:19\s*%|7\s*%)\s*€?\s*([\d\.]+,\d{2})\s*€?",  # Common VAT rates
        ],
    }

    @staticmethod
    def extract_with_patterns(text: str, patterns: List[str]) -> Optional[str]:
        """Try multiple patterns in order, return first match."""
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    @staticmethod
    def extract_document_number(text: str) -> Optional[str]:
        """Extract document number using patterns."""
        return DocumentTypeExtractionRules.extract_with_patterns(
            text,
            DocumentTypeExtractionRules.DOCUMENT_NUMBER_PATTERNS
        )

    @staticmethod
    def extract_german_date(text: str) -> Optional[date]:
        """Extract and parse German date (DD.MM.YYYY)."""
        date_str = DocumentTypeExtractionRules.extract_with_patterns(
            text,
            DocumentTypeExtractionRules.DATE_PATTERNS
        )

        if not date_str:
            return None

        # Parse German date format
        try:
            day, month, year = date_str.split('.')

            # Handle 2-digit years
            if len(year) == 2:
                year = f"20{year}" if int(year) < 50 else f"19{year}"

            return date(int(year), int(month), int(day))
        except (ValueError, IndexError):
            return None

    @staticmethod
    def extract_german_amount(text: str, amount_type: str = "total") -> Optional[Decimal]:
        """Extract amount in German format (1.234,56) and convert to Decimal."""
        patterns = DocumentTypeExtractionRules.AMOUNT_PATTERNS.get(amount_type, [])
        amount_str = DocumentTypeExtractionRules.extract_with_patterns(text, patterns)

        if not amount_str:
            return None

        # Convert German format to Decimal
        # 1.234,56 → 1234.56
        amount_str = amount_str.replace('.', '').replace(',', '.')

        try:
            return Decimal(amount_str)
        except (ValueError, decimal.InvalidOperation):
            return None
```

---

## Section 3: Validation Rules

### 3.1 Regulatory Compliance

**Define compliance checks specific to this document type:**

```python
# app/services/document_types/DOCUMENT_TYPE_NAME_validator.py

from typing import Tuple, List, Dict, Any
from pydantic import BaseModel

class DocumentTypeValidator:
    """Validation rules for DOCUMENT_TYPE_NAME compliance."""

    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def validate(self, entities: DocumentTypeEntities) -> Tuple[bool, List[str], List[str]]:
        """
        Validate extracted entities against regulatory requirements.

        Returns:
            (is_valid, errors, warnings)
        """
        self.errors = []
        self.warnings = []

        # Run all validation checks
        self._validate_required_fields(entities)
        self._validate_business_rules(entities)
        self._validate_regulatory_compliance(entities)

        is_valid = len(self.errors) == 0
        return (is_valid, self.errors, self.warnings)

    def _validate_required_fields(self, entities: DocumentTypeEntities) -> None:
        """Check that all required fields are present."""

        required_fields = [
            ("document_number", "Dokumentnummer"),
            ("document_date", "Dokumentdatum"),
            ("issuer_name", "Aussteller Name"),
            ("recipient_name", "Empfänger Name"),
        ]

        for field_name, display_name in required_fields:
            if not getattr(entities, field_name, None):
                self.errors.append(f"{display_name} fehlt (Pflichtfeld)")

    def _validate_business_rules(self, entities: DocumentTypeEntities) -> None:
        """Validate business logic rules."""

        # Example: Total amount should be greater than VAT amount
        if entities.total_amount and entities.vat_amount:
            if entities.vat_amount >= entities.total_amount:
                self.errors.append(
                    "MwSt-Betrag darf nicht größer als Gesamtbetrag sein"
                )

        # Example: Document date should not be too old
        if entities.document_date:
            age_days = (date.today() - entities.document_date).days
            if age_days > 365 * 3:  # 3 years
                self.warnings.append(
                    f"Dokument ist {age_days} Tage alt (> 3 Jahre)"
                )

        # Example: USt-IdNr should be present for amounts > 250 EUR
        if entities.total_amount and entities.total_amount > 250:
            if not entities.issuer_ust_id:
                self.warnings.append(
                    "USt-IdNr fehlt (empfohlen für Beträge > 250 EUR)"
                )

    def _validate_regulatory_compliance(self, entities: DocumentTypeEntities) -> None:
        """
        Validate against regulatory requirements (e.g., §14 UStG for invoices).

        CUSTOMIZE THIS METHOD for your document type's specific regulations.
        """

        # Example for invoices (§14 UStG)
        # Remove or modify for other document types

        # §14 Abs. 4 Nr. 1-10 UStG requirements
        required_invoice_fields = [
            ("issuer_name", "§14(4) Nr. 1: Vollständiger Name des Leistenden"),
            ("issuer_address", "§14(4) Nr. 1: Vollständige Anschrift des Leistenden"),
            ("recipient_name", "§14(4) Nr. 2: Vollständiger Name des Empfängers"),
            ("recipient_address", "§14(4) Nr. 2: Vollständige Anschrift des Empfängers"),
            ("issuer_ust_id", "§14(4) Nr. 3: USt-IdNr oder Steuernummer"),
            ("document_date", "§14(4) Nr. 4: Ausstellungsdatum"),
            ("document_number", "§14(4) Nr. 5: Fortlaufende Rechnungsnummer"),
            ("total_amount", "§14(4) Nr. 8: Entgelt (Gesamtbetrag)"),
        ]

        for field_name, compliance_note in required_invoice_fields:
            if not getattr(entities, field_name, None):
                self.errors.append(f"Compliance-Fehler: {compliance_note} fehlt")

        # §14 Abs. 4 Nr. 5: Invoice number must be unique and sequential
        # This would require database check - add warning for manual review
        if entities.document_number:
            self.warnings.append(
                f"Bitte Eindeutigkeit der Rechnungsnummer {entities.document_number} prüfen (§14(4) Nr. 5)"
            )
```

### 3.2 Data Quality Checks

**Define data quality thresholds:**

```python
class DataQualityChecker:
    """Check extracted data quality before acceptance."""

    @staticmethod
    def check_ocr_confidence(ocr_result: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Verify OCR confidence meets threshold."""
        warnings = []

        min_confidence = RECHNUNG_CHARACTERISTICS.ocr_confidence_threshold  # 0.85

        if "confidence" in ocr_result:
            confidence = ocr_result["confidence"]

            if confidence < min_confidence:
                warnings.append(
                    f"OCR Konfidenz zu niedrig: {confidence:.2%} (Minimum: {min_confidence:.2%})"
                )

                # Suggest manual review for low confidence
                if confidence < 0.70:
                    warnings.append("Manuelle Prüfung empfohlen (Konfidenz < 70%)")

        return (len(warnings) == 0, warnings)

    @staticmethod
    def check_entity_completeness(entities: DocumentTypeEntities) -> Tuple[float, List[str]]:
        """
        Calculate completeness score (0.0-1.0) for extracted entities.

        Returns:
            (completeness_score, missing_fields)
        """
        all_fields = entities.__fields__.keys()
        filled_fields = [
            field for field in all_fields
            if getattr(entities, field, None) is not None
        ]

        completeness = len(filled_fields) / len(all_fields)
        missing_fields = [field for field in all_fields if field not in filled_fields]

        return (completeness, missing_fields)
```

---

## Section 4: Processing Workflow

### 4.1 Celery Task Implementation

**Create async processing task:**

```python
# app/workers/document_types/DOCUMENT_TYPE_NAME_tasks.py

from celery import shared_task
from typing import Dict, Any
import structlog

logger = structlog.get_logger(__name__)

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,  # 1 minute
    time_limit=300,  # 5 minutes max
    soft_time_limit=240  # Warning at 4 minutes
)
def process_DOCUMENT_TYPE_NAME(self, document_id: str) -> Dict[str, Any]:
    """
    Process DOCUMENT_TYPE_NAME document through complete pipeline.

    Pipeline Steps:
        1. Load document from MinIO
        2. Select OCR backend based on characteristics
        3. Run OCR extraction
        4. Extract entities using rules + NLP
        5. Validate extracted data
        6. Store results in PostgreSQL
        7. Cache in Redis
        8. Emit completion event

    Args:
        document_id: Unique document identifier

    Returns:
        Processing result with extracted entities and validation status

    Raises:
        Retry on transient failures (network, GPU OOM)
        Fails permanently on invalid document format
    """

    logger.info(
        "document_processing_started",
        document_id=document_id,
        document_type="DOCUMENT_TYPE_NAME",
        task_id=self.request.id
    )

    try:
        # Step 1: Load document
        document = await storage_service.get_document(document_id)
        if not document:
            raise ValueError(f"Dokument {document_id} nicht gefunden")

        # Step 2: Select OCR backend
        backend = ocr_orchestrator.select_backend(
            document=document,
            characteristics=RECHNUNG_CHARACTERISTICS
        )

        logger.info(
            "ocr_backend_selected",
            document_id=document_id,
            backend=backend,
            reason=ocr_orchestrator.selection_reason
        )

        # Step 3: Run OCR
        with gpu_memory_guard():
            ocr_result = await ocr_backends[backend].process(document)

        # Step 4: Extract entities
        extractor = DocumentTypeEntityExtractor()
        entities = extractor.extract(ocr_result["text"])

        # Step 5: Validate
        validator = DocumentTypeValidator()
        is_valid, errors, warnings = validator.validate(entities)

        # Step 6: Store results
        result = {
            "document_id": document_id,
            "document_type": "DOCUMENT_TYPE_NAME",
            "entities": entities.dict(),
            "validation": {
                "is_valid": is_valid,
                "errors": errors,
                "warnings": warnings
            },
            "ocr_metadata": {
                "backend": backend,
                "confidence": ocr_result.get("confidence"),
                "processing_time_ms": ocr_result.get("processing_time_ms")
            },
            "status": "valid" if is_valid else "validation_failed"
        }

        await db_service.update_document(document_id, result)

        # Step 7: Cache results
        await cache_service.set(
            f"doc:{document_id}:entities",
            entities.dict(),
            ttl=3600  # 1 hour
        )

        # Step 8: Emit event
        await event_service.emit("document.processed", result)

        logger.info(
            "document_processing_completed",
            document_id=document_id,
            is_valid=is_valid,
            entity_count=len(entities.dict()),
            validation_errors=len(errors)
        )

        return result

    except (torch.cuda.OutOfMemoryError, redis.ConnectionError) as e:
        # Transient errors - retry
        logger.warning(
            "document_processing_retry",
            document_id=document_id,
            error=str(e),
            retry_count=self.request.retries
        )
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))

    except Exception as e:
        # Permanent failure
        logger.exception(
            "document_processing_failed",
            document_id=document_id,
            error=str(e)
        )

        # Mark document as failed
        await db_service.update_document(document_id, {
            "status": "processing_failed",
            "error": str(e)
        })

        raise
```

### 4.2 API Endpoint

**Create FastAPI endpoint:**

```python
# app/api/v1/documents/DOCUMENT_TYPE_NAME.py

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_db, get_current_user
from app.models import User

router = APIRouter(prefix="/documents/DOCUMENT_TYPE_NAME", tags=["DOCUMENT_TYPE_NAME"])

@router.post("/", status_code=202)
async def upload_DOCUMENT_TYPE_NAME(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Upload and process DOCUMENT_TYPE_NAME document.

    Process:
        1. Validate file type and size
        2. Store in MinIO
        3. Create database record
        4. Queue for async processing

    Returns:
        202 Accepted with document_id and status endpoint
    """

    # Validate file type
    allowed_types = ["application/pdf", "image/png", "image/jpeg", "image/tiff"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_FILE_TYPE",
                "message": f"Dateityp {file.content_type} nicht unterstützt",
                "allowed_types": allowed_types
            }
        )

    # Validate file size (max 50MB)
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "FILE_TOO_LARGE",
                "message": "Datei zu groß (Maximum: 50 MB)"
            }
        )

    # Store in MinIO
    document_id = generate_document_id()
    storage_path = await storage_service.upload(
        content=content,
        filename=file.filename,
        document_id=document_id
    )

    # Create database record
    document = await db_service.create_document(
        db=db,
        document_id=document_id,
        document_type="DOCUMENT_TYPE_NAME",
        filename=file.filename,
        storage_path=storage_path,
        user_id=current_user.id,
        status="queued"
    )

    # Queue for processing
    task = process_DOCUMENT_TYPE_NAME.delay(document_id)

    logger.info(
        "document_upload_queued",
        document_id=document_id,
        document_type="DOCUMENT_TYPE_NAME",
        user_id=current_user.id,
        task_id=task.id
    )

    return {
        "document_id": document_id,
        "status": "queued",
        "task_id": task.id,
        "status_endpoint": f"/api/v1/documents/{document_id}/status"
    }


@router.get("/{document_id}")
async def get_DOCUMENT_TYPE_NAME(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Retrieve processed DOCUMENT_TYPE_NAME with extracted entities."""

    document = await db_service.get_document(db, document_id)

    if not document:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")

    # Check access rights
    if document.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Zugriff verweigert")

    return {
        "document_id": document.id,
        "document_type": document.document_type,
        "filename": document.filename,
        "status": document.status,
        "entities": document.entities,  # Extracted entities
        "validation": document.validation,  # Validation results
        "created_at": document.created_at.isoformat(),
        "processed_at": document.processed_at.isoformat() if document.processed_at else None
    }
```

---

## Section 5: Testing

### 5.1 Unit Tests

**Create test suite:**

```python
# tests/unit/document_types/test_DOCUMENT_TYPE_NAME.py

import pytest
from datetime import date
from decimal import Decimal
from app.services.document_types.DOCUMENT_TYPE_NAME import (
    DocumentTypeEntities,
    DocumentTypeExtractionRules,
    DocumentTypeValidator
)

class TestDocumentTypeEntities:
    """Test entity model validation."""

    def test_valid_entity_creation(self):
        """Valid entities should be accepted."""
        entities = DocumentTypeEntities(
            document_number="RE-2025-00123",
            document_date=date(2025, 1, 20),
            issuer_name="Mustermann GmbH",
            issuer_ust_id="DE123456789",
            recipient_name="Kunde AG",
            total_amount=Decimal("1234.56"),
            currency="EUR"
        )

        assert entities.document_number == "RE-2025-00123"
        assert entities.total_amount == Decimal("1234.56")

    def test_future_date_rejected(self):
        """Future document dates should be rejected."""
        from datetime import datetime, timedelta

        with pytest.raises(ValueError, match="Zukunft"):
            DocumentTypeEntities(
                document_number="RE-2025-00123",
                document_date=datetime.now().date() + timedelta(days=1),
                issuer_name="Test",
                recipient_name="Test"
            )

    def test_invalid_ust_id_rejected(self):
        """Invalid USt-IdNr format should be rejected."""
        with pytest.raises(ValueError, match="USt-IdNr"):
            DocumentTypeEntities(
                document_number="RE-2025-00123",
                document_date=date(2025, 1, 20),
                issuer_name="Test",
                issuer_ust_id="INVALID",  # Wrong format
                recipient_name="Test"
            )


class TestDocumentTypeExtractionRules:
    """Test entity extraction regex patterns."""

    @pytest.fixture
    def sample_text(self):
        return """
        Rechnung

        Rechnungsnummer: RE-2025-00123
        Rechnungsdatum: 20.01.2025

        Mustermann GmbH
        Musterstraße 123
        12345 Musterstadt
        USt-IdNr: DE123456789

        Gesamtbetrag: 1.234,56 EUR
        MwSt. 19%: 197,24 EUR
        """

    def test_extract_document_number(self, sample_text):
        """Should extract document number."""
        number = DocumentTypeExtractionRules.extract_document_number(sample_text)
        assert number == "RE-2025-00123"

    def test_extract_date(self, sample_text):
        """Should extract and parse German date."""
        extracted_date = DocumentTypeExtractionRules.extract_german_date(sample_text)
        assert extracted_date == date(2025, 1, 20)

    def test_extract_total_amount(self, sample_text):
        """Should extract total amount in German format."""
        amount = DocumentTypeExtractionRules.extract_german_amount(sample_text, "total")
        assert amount == Decimal("1234.56")

    def test_extract_vat_amount(self, sample_text):
        """Should extract VAT amount."""
        vat = DocumentTypeExtractionRules.extract_german_amount(sample_text, "vat")
        assert vat == Decimal("197.24")


class TestDocumentTypeValidator:
    """Test validation rules."""

    def test_valid_entities_pass_validation(self):
        """Complete valid entities should pass all checks."""
        entities = DocumentTypeEntities(
            document_number="RE-2025-00123",
            document_date=date(2025, 1, 20),
            issuer_name="Mustermann GmbH",
            issuer_address="Musterstraße 123, 12345 Musterstadt",
            issuer_ust_id="DE123456789",
            recipient_name="Kunde AG",
            recipient_address="Kundenweg 456, 54321 Kundenstadt",
            total_amount=Decimal("1234.56"),
            vat_amount=Decimal("197.24")
        )

        validator = DocumentTypeValidator()
        is_valid, errors, warnings = validator.validate(entities)

        assert is_valid is True
        assert len(errors) == 0

    def test_missing_required_field_fails(self):
        """Missing required fields should fail validation."""
        entities = DocumentTypeEntities(
            document_number="RE-2025-00123",
            document_date=date(2025, 1, 20),
            issuer_name="Test",
            recipient_name="Test"
            # Missing other required fields
        )

        validator = DocumentTypeValidator()
        is_valid, errors, warnings = validator.validate(entities)

        assert is_valid is False
        assert len(errors) > 0

    def test_vat_exceeds_total_fails(self):
        """VAT amount > total amount should fail validation."""
        entities = DocumentTypeEntities(
            document_number="RE-2025-00123",
            document_date=date(2025, 1, 20),
            issuer_name="Test",
            recipient_name="Test",
            total_amount=Decimal("100.00"),
            vat_amount=Decimal("150.00")  # Exceeds total!
        )

        validator = DocumentTypeValidator()
        is_valid, errors, warnings = validator.validate(entities)

        assert is_valid is False
        assert any("MwSt-Betrag" in error for error in errors)
```

### 5.2 Integration Tests

**Create end-to-end test:**

```python
# tests/integration/test_DOCUMENT_TYPE_NAME_workflow.py

import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.integration
@pytest.mark.asyncio
async def test_document_upload_and_processing_workflow():
    """Test complete document processing workflow."""

    async with AsyncClient(app=app, base_url="http://test") as client:
        # Step 1: Upload document
        files = {
            "file": ("sample_rechnung.pdf", open("tests/fixtures/sample_rechnung.pdf", "rb"))
        }

        response = await client.post(
            "/api/v1/documents/DOCUMENT_TYPE_NAME/",
            files=files
        )

        assert response.status_code == 202
        data = response.json()
        document_id = data["document_id"]

        # Step 2: Poll for completion (max 30 seconds)
        import asyncio
        for _ in range(30):
            response = await client.get(f"/api/v1/documents/{document_id}")
            data = response.json()

            if data["status"] in ["valid", "validation_failed"]:
                break

            await asyncio.sleep(1)

        # Step 3: Verify extracted entities
        assert data["status"] == "valid"
        entities = data["entities"]

        assert entities["document_number"] is not None
        assert entities["document_date"] is not None
        assert entities["issuer_name"] is not None
        assert entities["recipient_name"] is not None

        # Step 4: Verify validation passed
        validation = data["validation"]
        assert validation["is_valid"] is True
        assert len(validation["errors"]) == 0
```

---

## Section 6: Documentation

### 6.1 User-Facing Documentation (German)

**Create user guide:**

```markdown
# DOCUMENT_TYPE_NAME Verarbeitung

## Überblick

Die Ablage-System verarbeitet [DOCUMENT_TYPE_NAME] Dokumente automatisch und extrahiert
alle relevanten Informationen gemäß [§X Gesetz].

## Unterstützte Formate

- PDF (empfohlen)
- PNG, JPEG, TIFF (Bilder)
- Maximale Dateigröße: 50 MB
- Maximale Seitenzahl: [X] Seiten

## Extrahierte Informationen

Die folgenden Informationen werden automatisch erkannt:

- ✅ Dokumentnummer (z.B. RE-2025-00123)
- ✅ Dokumentdatum (DD.MM.YYYY)
- ✅ Aussteller Name und Anschrift
- ✅ Empfänger Name und Anschrift
- ✅ USt-IdNr (DExxxxxxxxx)
- ✅ Beträge (Gesamt, MwSt.)
- ✅ [Weitere dokumentspezifische Felder]

## Qualitätsanforderungen

Für optimale Ergebnisse beachten Sie bitte:

- **Auflösung**: Mindestens 300 DPI
- **Lesbarkeit**: Text sollte scharf und kontrastreich sein
- **Vollständigkeit**: Alle Seiten des Dokuments hochladen
- **Format**: PDF bevorzugt (bessere OCR-Qualität)

## Compliance und Aufbewahrung

- **§14 UStG**: Rechnungen werden 10 Jahre aufbewahrt
- **DSGVO Art. 17**: Löschung nach Ablauf der Aufbewahrungsfrist
- **Audit-Log**: Alle Zugriffe werden protokolliert

## Fehlerbehandlung

Bei Problemen wird das Dokument zur manuellen Prüfung markiert:

- ⚠️ **Niedrige OCR-Qualität** (< 85%): Manuelle Prüfung empfohlen
- ❌ **Validation fehlgeschlagen**: Pflichtfelder fehlen
- ❌ **Ungültiges Format**: Datei kann nicht verarbeitet werden

## API Endpunkte

```bash
# Dokument hochladen
POST /api/v1/documents/DOCUMENT_TYPE_NAME/
Content-Type: multipart/form-data

# Status abfragen
GET /api/v1/documents/{document_id}/status

# Ergebnis abrufen
GET /api/v1/documents/{document_id}
```
```

### 6.2 Developer Documentation

**Update main documentation:**

```markdown
# DOCUMENT_TYPE_NAME Implementation

## Architecture

[Include Mermaid diagram of processing flow]

## Key Components

- **Entity Model**: [DocumentTypeEntities.py](../../app/services/document_types/DOCUMENT_TYPE_NAME.py)
- **Extraction Rules**: [DOCUMENT_TYPE_NAME_rules.py](...)
- **Validator**: [DOCUMENT_TYPE_NAME_validator.py](...)
- **Celery Task**: [DOCUMENT_TYPE_NAME_tasks.py](...)
- **API Endpoint**: [DOCUMENT_TYPE_NAME.py](...)

## Adding Custom Rules

To add new entity extraction rules:

1. Add regex pattern to `DOCUMENT_TYPE_NAME_rules.py`
2. Add field to `DocumentTypeEntities` model
3. Add validation rule to `DocumentTypeValidator`
4. Update tests
5. Update API documentation

## Performance Benchmarks

| Metric | Target | Current |
|--------|--------|---------|
| OCR Processing | < 3s per page | 2.8s |
| Entity Extraction | < 500ms | 320ms |
| Validation | < 100ms | 45ms |
| End-to-End | < 5s per document | 3.8s |

## Related Documentation

- [ADR-003: OCR Backend Selection](../../Static_Knowledge/ADRs/ADR_003_ocr_backend_selection.md)
- [ADR-004: German NLP Approach](../../Static_Knowledge/ADRs/ADR_004_german_nlp_approach.md)
- [Entity Extraction Guide](../../Dynamic_Knowledge/Guides/entity_extraction.md)
```

---

## Checklist: Implementation Complete

Use this checklist to verify your implementation is production-ready:

### Code Implementation
- [ ] Entity model created with all required fields
- [ ] Pydantic validators implemented for all business rules
- [ ] Extraction rules defined (regex patterns)
- [ ] Validation rules implemented (regulatory compliance)
- [ ] Celery task created with error handling
- [ ] FastAPI endpoints created (upload, retrieve)
- [ ] German NLP post-processing integrated

### Testing
- [ ] Unit tests written (entities, extraction, validation)
- [ ] Integration tests written (end-to-end workflow)
- [ ] Test coverage > 80%
- [ ] Edge cases tested (missing fields, invalid data)
- [ ] Performance benchmarks run (< 5s per document)

### Documentation
- [ ] User-facing documentation written (German)
- [ ] Developer documentation updated
- [ ] API documentation auto-generated (OpenAPI)
- [ ] ADR created (if architectural decision involved)
- [ ] README updated with new document type

### Compliance & Security
- [ ] GDPR implications assessed (Art. 17, 30)
- [ ] Regulatory requirements verified (§14 UStG, etc.)
- [ ] Audit logging implemented
- [ ] Input validation (XSS, SQLi prevention)
- [ ] Access control verified

### Deployment
- [ ] Database migrations created (if schema changes)
- [ ] Monitoring metrics added (Prometheus)
- [ ] Alerting rules configured (error rates, latency)
- [ ] Rollback plan documented
- [ ] Staging deployment successful
- [ ] Production deployment scheduled

---

## Additional Resources

- **[ADR Template](ADR_template.md)** - For documenting architectural decisions
- **[German NLP Best Practices](../../Dynamic_Knowledge/Guides/german_nlp_best_practices.md)**
- **[OCR Troubleshooting Guide](../../Meta_Layer/Indexes/troubleshooting_index.yaml)**
- **[Celery Task Optimization](../../Dynamic_Knowledge/Learnings/celery_task_optimization.md)**

---

**Template Version:** 1.0
**Last Updated:** 2025-01-20
**Maintained By:** Backend Team

**Questions or Issues?**
- Create issue in repository
- Contact: backend-team@ablage-system.de
- Slack: #ablage-development
