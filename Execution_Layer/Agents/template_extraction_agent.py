"""
Template Extraction Agent - Autonomous Field Extraction
Extrahiert strukturierte Daten aus OCR-Text mittels Templates
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import re

import structlog

logger = structlog.get_logger(__name__)


# Template definitions for common German document types
DOCUMENT_TEMPLATES = {
    "invoice": {
        "name": "Rechnung",
        "required_fields": ["invoice_number", "date", "total_amount", "company"],
        "optional_fields": ["tax_id", "iban", "payment_terms", "line_items"],
        "keywords": ["rechnung", "invoice", "rechnungsnummer", "rechnungsdatum"],
        "patterns": {
            "invoice_number": r"(?:Rechnungs?-?(?:Nr\.?|nummer)|Invoice\s*(?:No\.?|Number)?)[:\s]*([A-Z0-9\-/]+)",
            "date": r"(?:Rechnungsdatum|Datum|Date)[:\s]*(\d{1,2}\.\d{1,2}\.\d{4})",
            "total_amount": r"(?:Gesamtbetrag|Brutto|Total)[:\s]*([0-9.,]+)\s*(?:€|EUR)?",
            "net_amount": r"(?:Netto|Nettobetrag)[:\s]*([0-9.,]+)\s*(?:€|EUR)?",
            "tax_amount": r"(?:MwSt\.?|Mehrwertsteuer|USt\.?)[:\s]*([0-9.,]+)\s*(?:€|EUR)?",
            "tax_rate": r"(\d{1,2})\s*%\s*(?:MwSt\.?|USt\.?)"
        }
    },
    "contract": {
        "name": "Vertrag",
        "required_fields": ["parties", "date", "contract_type"],
        "optional_fields": ["duration", "value", "termination"],
        "keywords": ["vertrag", "vereinbarung", "contract", "agreement"],
        "patterns": {
            "parties": r"zwischen\s+(.+?)\s+und\s+(.+?)(?:\s|,|\.|$)",
            "date": r"(?:Vertragsdatum|Datum)[:\s]*(\d{1,2}\.\d{1,2}\.\d{4})",
            "duration": r"(?:Laufzeit|Dauer)[:\s]*(\d+\s*(?:Monat|Jahr|Tag)e?n?)"
        }
    },
    "delivery_note": {
        "name": "Lieferschein",
        "required_fields": ["delivery_number", "date", "items"],
        "optional_fields": ["recipient", "sender", "weight"],
        "keywords": ["lieferschein", "delivery", "versand", "sendung"],
        "patterns": {
            "delivery_number": r"(?:Lieferschein-?(?:Nr\.?|nummer))[:\s]*([A-Z0-9\-/]+)",
            "date": r"(?:Lieferdatum|Datum)[:\s]*(\d{1,2}\.\d{1,2}\.\d{4})"
        }
    },
    "general": {
        "name": "Allgemeines Dokument",
        "required_fields": [],
        "optional_fields": ["dates", "companies", "amounts"],
        "keywords": [],
        "patterns": {}
    }
}


class TemplateExtractionAgent:
    """
    Extract structured data from OCR text using templates.

    Supports automatic document type detection and extraction
    of structured fields based on predefined templates.
    """

    def __init__(self):
        self.templates = DOCUMENT_TEMPLATES
        self._validation_agent = None

    def _get_validation_agent(self):
        """Lazy load validation agent."""
        if self._validation_agent is None:
            from Execution_Layer.Sub_Agents.validation_sub_agent import ValidationSubAgent
            self._validation_agent = ValidationSubAgent()
        return self._validation_agent

    async def extract(
        self,
        ocr_text: str,
        template_id: str = "auto"
    ) -> Dict[str, Any]:
        """
        Autonomously extract fields using template matching.

        Steps:
        1. Detect document type (if auto)
        2. Load appropriate template
        3. Apply extraction patterns
        4. Validate extracted fields
        5. Calculate confidence scores
        6. Flag for manual review if needed

        Args:
            ocr_text: OCR-extracted text
            template_id: Template ID or "auto" for auto-detection

        Returns:
            Structured extraction result with fields, confidence, and status
        """
        result = {
            "template_id": template_id,
            "template_name": None,
            "document_type": None,
            "fields": {},
            "raw_extractions": {},
            "validation": {},
            "confidence": 0.0,
            "needs_review": False,
            "review_reasons": [],
            "extracted_at": datetime.utcnow().isoformat()
        }

        if not ocr_text or not ocr_text.strip():
            result["needs_review"] = True
            result["review_reasons"].append("Kein OCR-Text vorhanden")
            return result

        try:
            # Step 1: Detect document type (if auto)
            if template_id == "auto":
                template_id = self._detect_document_type(ocr_text)

            result["template_id"] = template_id
            result["document_type"] = template_id

            # Step 2: Load appropriate template
            template = self.templates.get(template_id, self.templates["general"])
            result["template_name"] = template["name"]

            logger.info(
                "template_extraction_start",
                template_id=template_id,
                template_name=template["name"]
            )

            # Step 3: Apply extraction patterns
            raw_extractions = await self._apply_patterns(ocr_text, template)
            result["raw_extractions"] = raw_extractions

            # Also extract using german validation snippets
            generic_extractions = await self._extract_generic_fields(ocr_text)
            result["raw_extractions"].update(generic_extractions)

            # Step 4: Validate extracted fields
            validated_fields, validation_results = await self._validate_fields(
                raw_extractions,
                template
            )
            result["fields"] = validated_fields
            result["validation"] = validation_results

            # Step 5: Calculate confidence scores
            result["confidence"] = self._calculate_confidence(
                validated_fields,
                validation_results,
                template
            )

            # Step 6: Flag for manual review if needed
            if result["confidence"] < 0.85:
                result["needs_review"] = True
                result["review_reasons"].append(
                    f"Konfidenz unter Schwellwert: {result['confidence']:.2%}"
                )

            # Check for missing required fields
            missing_required = self._check_required_fields(
                validated_fields,
                template
            )
            if missing_required:
                result["needs_review"] = True
                result["review_reasons"].append(
                    f"Fehlende Pflichtfelder: {', '.join(missing_required)}"
                )

            logger.info(
                "template_extraction_complete",
                template_id=template_id,
                fields_count=len(validated_fields),
                confidence=result["confidence"],
                needs_review=result["needs_review"]
            )

        except Exception as e:
            logger.error(
                "template_extraction_failed",
                error=str(e),
                exc_info=True
            )
            result["error"] = str(e)
            result["needs_review"] = True
            result["review_reasons"].append(f"Extraktionsfehler: {e}")

        return result

    def _detect_document_type(self, text: str) -> str:
        """
        Detect document type based on keywords in text.

        Returns template_id for the detected type.
        """
        text_lower = text.lower()

        # Score each template based on keyword matches
        scores = {}
        for template_id, template in self.templates.items():
            if template_id == "general":
                continue

            score = sum(
                1 for keyword in template.get("keywords", [])
                if keyword.lower() in text_lower
            )
            if score > 0:
                scores[template_id] = score

        if scores:
            # Return template with highest score
            best_match = max(scores, key=scores.get)
            logger.debug(
                "document_type_detected",
                detected=best_match,
                scores=scores
            )
            return best_match

        return "general"

    async def _apply_patterns(
        self,
        text: str,
        template: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply regex patterns from template to extract fields."""
        extractions = {}

        for field_name, pattern in template.get("patterns", {}).items():
            try:
                matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
                if matches:
                    # Handle tuple results from groups
                    if isinstance(matches[0], tuple):
                        extractions[field_name] = [
                            " ".join(m).strip() for m in matches
                        ]
                    else:
                        extractions[field_name] = [m.strip() for m in matches]

                    logger.debug(
                        "pattern_match",
                        field=field_name,
                        matches=len(matches)
                    )
            except Exception as e:
                logger.warning(
                    "pattern_match_failed",
                    field=field_name,
                    error=str(e)
                )

        return extractions

    async def _extract_generic_fields(self, text: str) -> Dict[str, Any]:
        """Extract common fields using german validation snippets."""
        extractions = {}

        try:
            from Static_Knowledge.Snippets.german_validation_snippets import (
                extract_german_dates,
                extract_tax_ids,
                extract_company_names,
                extract_business_terms
            )

            # Extract dates
            dates = extract_german_dates(text)
            if dates:
                extractions["dates"] = dates

            # Extract tax IDs
            tax_ids = extract_tax_ids(text)
            if tax_ids.get("ust_idnr") or tax_ids.get("steuernummer"):
                extractions["tax_ids"] = tax_ids

            # Extract company names
            companies = extract_company_names(text)
            if companies:
                extractions["companies"] = companies

            # Extract business terms
            terms = extract_business_terms(text)
            if terms:
                extractions["business_terms"] = terms

        except ImportError:
            logger.warning("german_validation_snippets_not_available")
        except Exception as e:
            logger.error("generic_extraction_failed", error=str(e))

        return extractions

    async def _validate_fields(
        self,
        raw_extractions: Dict[str, Any],
        template: Dict[str, Any]
    ) -> tuple:
        """Validate extracted fields and return validated fields + results."""
        validated = {}
        validation_results = {}

        validator = self._get_validation_agent()

        for field_name, values in raw_extractions.items():
            if not values:
                continue

            # Get first value if list
            value = values[0] if isinstance(values, list) else values

            # Validate based on field type
            if "date" in field_name.lower():
                result = validator.validate_german_date(str(value))
                validation_results[field_name] = result
                if result["valid"]:
                    validated[field_name] = {
                        "value": value,
                        "parsed": result.get("parsed"),
                        "valid": True
                    }
                else:
                    validated[field_name] = {
                        "value": value,
                        "valid": False,
                        "errors": result.get("errors", [])
                    }

            elif "amount" in field_name.lower() or field_name in ["total_amount", "net_amount", "tax_amount"]:
                result = validator.validate_german_currency(str(value))
                validation_results[field_name] = result
                if result["valid"]:
                    validated[field_name] = {
                        "value": value,
                        "decimal_value": result.get("value"),
                        "formatted": result.get("formatted"),
                        "valid": True
                    }
                else:
                    validated[field_name] = {
                        "value": value,
                        "valid": False,
                        "errors": result.get("errors", [])
                    }

            elif "tax_id" in field_name.lower() or field_name == "ust_idnr":
                if isinstance(value, dict):
                    # Already structured (from extract_tax_ids)
                    validated[field_name] = value
                else:
                    result = validator.validate_tax_id(str(value))
                    validation_results[field_name] = result
                    validated[field_name] = {
                        "value": value,
                        "type": result.get("type"),
                        "valid": result.get("valid", False)
                    }

            else:
                # Store as-is for other fields
                validated[field_name] = {
                    "value": value,
                    "valid": True
                }

        return validated, validation_results

    def _calculate_confidence(
        self,
        validated_fields: Dict[str, Any],
        validation_results: Dict[str, Any],
        template: Dict[str, Any]
    ) -> float:
        """Calculate overall extraction confidence."""
        if not validated_fields:
            return 0.0

        total_fields = len(validated_fields)
        valid_fields = sum(
            1 for f in validated_fields.values()
            if isinstance(f, dict) and f.get("valid", False)
        )

        # Base confidence from field validity
        base_confidence = valid_fields / total_fields if total_fields > 0 else 0.0

        # Bonus for required fields
        required = template.get("required_fields", [])
        required_found = sum(
            1 for rf in required
            if rf in validated_fields and validated_fields[rf].get("valid", False)
        )
        required_bonus = (required_found / len(required) * 0.2) if required else 0.0

        # Penalty for validation errors
        error_count = sum(
            1 for v in validation_results.values()
            if not v.get("valid", True)
        )
        error_penalty = min(0.3, error_count * 0.1)

        confidence = min(1.0, max(0.0, base_confidence + required_bonus - error_penalty))

        return round(confidence, 3)

    def _check_required_fields(
        self,
        validated_fields: Dict[str, Any],
        template: Dict[str, Any]
    ) -> List[str]:
        """Check which required fields are missing."""
        required = template.get("required_fields", [])
        missing = []

        for field in required:
            if field not in validated_fields:
                missing.append(field)
            elif not validated_fields[field].get("valid", False):
                missing.append(f"{field} (ungueltig)")

        return missing

    def add_template(
        self,
        template_id: str,
        template_config: Dict[str, Any]
    ) -> bool:
        """Add a new template dynamically."""
        if not template_id or not template_config:
            return False

        self.templates[template_id] = template_config
        logger.info(
            "template_added",
            template_id=template_id,
            name=template_config.get("name")
        )
        return True


# See: Static_Knowledge/ADRs/004_template_extraction_strategy.md
# See: Static_Knowledge/SOPs/003_adding_new_document_template.md
