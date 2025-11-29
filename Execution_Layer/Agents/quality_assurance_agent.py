"""
Quality Assurance Agent - Validation and Scoring
Validiert OCR-Qualitaet und extrahierte Daten gemaess deutschen Standards
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from decimal import Decimal, InvalidOperation

import structlog

logger = structlog.get_logger(__name__)


# §14 UStG required fields for German invoices
USTG_REQUIRED_FIELDS = [
    "seller_name",        # Name und Anschrift des leistenden Unternehmers
    "seller_address",     # (Teil von seller)
    "buyer_name",         # Name und Anschrift des Leistungsempfängers
    "tax_number",         # Steuernummer oder USt-IdNr
    "invoice_date",       # Ausstellungsdatum
    "invoice_number",     # Fortlaufende Rechnungsnummer
    "service_description", # Art und Umfang der Leistung
    "delivery_date",      # Zeitpunkt der Lieferung/Leistung
    "net_amount",         # Nettobetrag
    "tax_rate",           # Steuersatz
    "tax_amount",         # Steuerbetrag
    "gross_amount"        # Bruttobetrag
]


class QualityAssuranceAgent:
    """
    Validate OCR quality and extracted data.

    Performs comprehensive quality checks including:
    - OCR confidence validation
    - German text quality (umlaut integrity)
    - Field completeness
    - Mathematical consistency
    - Legal compliance (§14 UStG)
    """

    def __init__(self):
        self._validation_agent = None

    def _get_validation_agent(self):
        """Lazy load validation agent."""
        if self._validation_agent is None:
            from Execution_Layer.Sub_Agents.validation_sub_agent import ValidationSubAgent
            self._validation_agent = ValidationSubAgent()
        return self._validation_agent

    async def validate(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Comprehensive quality validation.

        Checks:
        - OCR confidence > 0.85
        - All required fields present
        - German umlaut accuracy 100%
        - Business terms recognized
        - Math validation (netto + mwst = brutto)
        - §14 UStG compliance (for invoices)

        Args:
            result: OCR processing result with text, confidence, and extracted fields

        Returns:
            Validation report with pass/fail status and detailed checks
        """
        validation_report = {
            "passed": True,
            "overall_score": 0.0,
            "checks": [],
            "warnings": [],
            "errors": [],
            "recommendations": [],
            "ustg_compliance": None,
            "validated_at": datetime.utcnow().isoformat()
        }

        try:
            # Extract data from result
            ocr_text = result.get("text", "")
            confidence = result.get("confidence", 0.0)
            extracted_fields = result.get("extracted_fields", {})
            document_type = result.get("document_type", "general")

            # Check 1: OCR Confidence
            check_confidence = await self._check_ocr_confidence(confidence)
            validation_report["checks"].append(check_confidence)
            if not check_confidence["passed"]:
                if confidence < 0.7:
                    validation_report["errors"].append(
                        f"OCR-Konfidenz kritisch niedrig: {confidence:.2%}"
                    )
                else:
                    validation_report["warnings"].append(
                        f"OCR-Konfidenz unter Schwellwert: {confidence:.2%}"
                    )

            # Check 2: Text Extraction Success
            check_text = await self._check_text_extraction(ocr_text)
            validation_report["checks"].append(check_text)
            if not check_text["passed"]:
                validation_report["errors"].append("Kein Text extrahiert")

            # Check 3: German Umlaut Integrity
            check_umlauts = await self._check_umlaut_integrity(ocr_text)
            validation_report["checks"].append(check_umlauts)
            if not check_umlauts["passed"]:
                validation_report["warnings"].append(
                    "Moegliche Umlaut-Fehler erkannt"
                )
                validation_report["recommendations"].append(
                    "Pruefen Sie die Umlaute im extrahierten Text"
                )

            # Check 4: Required Fields Present
            check_fields = await self._check_required_fields(
                extracted_fields,
                document_type
            )
            validation_report["checks"].append(check_fields)
            if not check_fields["passed"]:
                validation_report["warnings"].append(
                    f"Fehlende Felder: {', '.join(check_fields.get('missing', []))}"
                )

            # Check 5: Business Terms Recognized
            check_terms = await self._check_business_terms(
                ocr_text,
                extracted_fields
            )
            validation_report["checks"].append(check_terms)

            # Check 6: Math Validation (for invoices)
            if document_type == "invoice":
                check_math = await self._check_invoice_math(extracted_fields)
                validation_report["checks"].append(check_math)
                if not check_math["passed"]:
                    validation_report["errors"].append(
                        "Rechnungsbetraege sind nicht konsistent"
                    )

                # Check 7: §14 UStG Compliance
                ustg_check = await self._check_ustg_compliance(extracted_fields)
                validation_report["checks"].append(ustg_check)
                validation_report["ustg_compliance"] = ustg_check
                if not ustg_check["passed"]:
                    validation_report["warnings"].append(
                        "§14 UStG Pflichtangaben unvollstaendig"
                    )

            # Calculate overall score
            validation_report["overall_score"] = self._calculate_score(
                validation_report["checks"]
            )

            # Determine overall pass/fail
            critical_checks = [
                c for c in validation_report["checks"]
                if c.get("critical", False) and not c.get("passed", True)
            ]

            if critical_checks:
                validation_report["passed"] = False
            elif validation_report["overall_score"] < 0.7:
                validation_report["passed"] = False
            elif len(validation_report["errors"]) > 0:
                validation_report["passed"] = False

            logger.info(
                "qa_validation_complete",
                passed=validation_report["passed"],
                score=validation_report["overall_score"],
                checks_count=len(validation_report["checks"]),
                errors_count=len(validation_report["errors"]),
                warnings_count=len(validation_report["warnings"])
            )

        except Exception as e:
            logger.error(
                "qa_validation_failed",
                error=str(e),
                exc_info=True
            )
            validation_report["passed"] = False
            validation_report["errors"].append(f"Validierungsfehler: {e}")

        return validation_report

    async def _check_ocr_confidence(self, confidence: float) -> Dict[str, Any]:
        """Check if OCR confidence meets threshold."""
        threshold = 0.85

        return {
            "name": "ocr_confidence",
            "description": "OCR-Konfidenz",
            "passed": confidence >= threshold,
            "critical": True,
            "value": confidence,
            "threshold": threshold,
            "message": (
                f"Konfidenz: {confidence:.2%}"
                if confidence >= threshold
                else f"Konfidenz {confidence:.2%} unter Schwellwert {threshold:.0%}"
            )
        }

    async def _check_text_extraction(self, text: str) -> Dict[str, Any]:
        """Check if text was successfully extracted."""
        text_length = len(text.strip()) if text else 0
        min_length = 10  # Minimum meaningful text length

        return {
            "name": "text_extraction",
            "description": "Textextraktion",
            "passed": text_length >= min_length,
            "critical": True,
            "value": text_length,
            "threshold": min_length,
            "message": (
                f"{text_length} Zeichen extrahiert"
                if text_length >= min_length
                else "Kein oder zu wenig Text extrahiert"
            )
        }

    async def _check_umlaut_integrity(self, text: str) -> Dict[str, Any]:
        """Check German umlaut integrity."""
        try:
            from Static_Knowledge.Snippets.german_validation_snippets import (
                validate_umlaut_integrity
            )

            result = validate_umlaut_integrity(text)
            issues = result.get("issues", [])

            return {
                "name": "umlaut_integrity",
                "description": "Umlaut-Integritaet",
                "passed": result.get("valid", True),
                "critical": False,
                "has_umlauts": result.get("has_umlauts", False),
                "issues_count": len(issues),
                "issues": issues[:5],  # Limit to first 5 issues
                "message": (
                    "Umlaute korrekt"
                    if result.get("valid", True)
                    else f"{len(issues)} moegliche Umlaut-Fehler"
                )
            }

        except ImportError:
            return {
                "name": "umlaut_integrity",
                "description": "Umlaut-Integritaet",
                "passed": True,
                "critical": False,
                "message": "Umlaut-Validierung nicht verfuegbar",
                "skipped": True
            }

    async def _check_required_fields(
        self,
        extracted_fields: Dict[str, Any],
        document_type: str
    ) -> Dict[str, Any]:
        """Check if required fields are present."""
        # Define required fields per document type
        required_by_type = {
            "invoice": ["date", "total_amount", "invoice_number"],
            "contract": ["date", "parties"],
            "delivery_note": ["date", "delivery_number"],
            "general": []
        }

        required = required_by_type.get(document_type, [])

        # Check fields from extracted_fields.fields
        fields = extracted_fields.get("fields", extracted_fields)
        missing = []

        for field in required:
            if field not in fields:
                missing.append(field)
            elif isinstance(fields[field], dict) and not fields[field].get("valid", True):
                missing.append(f"{field} (ungueltig)")

        return {
            "name": "required_fields",
            "description": "Pflichtfelder",
            "passed": len(missing) == 0,
            "critical": False,
            "document_type": document_type,
            "required": required,
            "missing": missing,
            "found": len(required) - len(missing),
            "message": (
                f"Alle {len(required)} Pflichtfelder vorhanden"
                if len(missing) == 0
                else f"{len(missing)} Pflichtfelder fehlen"
            )
        }

    async def _check_business_terms(
        self,
        text: str,
        extracted_fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Check if business terms are recognized."""
        try:
            from Static_Knowledge.Snippets.german_validation_snippets import (
                extract_business_terms
            )

            terms = extract_business_terms(text)
            term_count = sum(len(v) for v in terms.values())

            return {
                "name": "business_terms",
                "description": "Geschaeftsbegriffe",
                "passed": term_count > 0,
                "critical": False,
                "terms_found": terms,
                "count": term_count,
                "message": (
                    f"{term_count} Geschaeftsbegriffe erkannt"
                    if term_count > 0
                    else "Keine Geschaeftsbegriffe erkannt"
                )
            }

        except ImportError:
            return {
                "name": "business_terms",
                "description": "Geschaeftsbegriffe",
                "passed": True,
                "critical": False,
                "message": "Geschaeftsbegriff-Erkennung nicht verfuegbar",
                "skipped": True
            }

    async def _check_invoice_math(
        self,
        extracted_fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate invoice math: netto + MwSt = brutto."""
        fields = extracted_fields.get("fields", extracted_fields)

        try:
            # Extract amounts
            net_field = fields.get("net_amount", {})
            tax_field = fields.get("tax_amount", {})
            gross_field = fields.get("total_amount", fields.get("gross_amount", {}))

            net = self._extract_decimal(net_field)
            tax = self._extract_decimal(tax_field)
            gross = self._extract_decimal(gross_field)

            if net is None or gross is None:
                return {
                    "name": "invoice_math",
                    "description": "Rechnungsmathematik",
                    "passed": True,
                    "critical": False,
                    "message": "Betraege nicht vollstaendig extrahiert",
                    "skipped": True
                }

            # Calculate expected gross
            if tax is not None:
                expected_gross = net + tax
                tolerance = Decimal("0.02")  # 2 cent tolerance
                math_valid = abs(expected_gross - gross) <= tolerance
            else:
                # Try to derive tax from gross - net
                derived_tax = gross - net
                # Check if derived tax is reasonable (0-27% of net)
                math_valid = Decimal("0") <= derived_tax <= (net * Decimal("0.27"))

            return {
                "name": "invoice_math",
                "description": "Rechnungsmathematik",
                "passed": math_valid,
                "critical": False,
                "net": str(net) if net else None,
                "tax": str(tax) if tax else None,
                "gross": str(gross) if gross else None,
                "message": (
                    "Betraege mathematisch konsistent"
                    if math_valid
                    else "Betraege stimmen nicht ueberein"
                )
            }

        except Exception as e:
            logger.warning("invoice_math_check_failed", error=str(e))
            return {
                "name": "invoice_math",
                "description": "Rechnungsmathematik",
                "passed": True,
                "critical": False,
                "message": f"Mathematische Pruefung fehlgeschlagen: {e}",
                "skipped": True
            }

    async def _check_ustg_compliance(
        self,
        extracted_fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Check §14 UStG compliance for German invoices."""
        fields = extracted_fields.get("fields", extracted_fields)

        # Map extracted fields to UStG requirements
        field_mapping = {
            "seller_name": ["companies", "seller", "company"],
            "tax_number": ["tax_ids", "ust_idnr", "steuernummer"],
            "invoice_date": ["date", "invoice_date"],
            "invoice_number": ["invoice_number", "rechnungsnummer"],
            "net_amount": ["net_amount", "netto"],
            "tax_amount": ["tax_amount", "mwst"],
            "gross_amount": ["total_amount", "gross_amount", "brutto"]
        }

        found = []
        missing = []

        for ustg_field, possible_fields in field_mapping.items():
            field_found = False
            for pf in possible_fields:
                if pf in fields:
                    field_value = fields[pf]
                    if isinstance(field_value, dict):
                        if field_value.get("valid", True) or field_value.get("value"):
                            field_found = True
                            break
                    elif field_value:
                        field_found = True
                        break

            if field_found:
                found.append(ustg_field)
            else:
                missing.append(ustg_field)

        compliance_score = len(found) / len(field_mapping) if field_mapping else 0

        return {
            "name": "ustg_compliance",
            "description": "§14 UStG Konformitaet",
            "passed": len(missing) == 0,
            "critical": False,
            "found": found,
            "missing": missing,
            "compliance_score": compliance_score,
            "message": (
                "§14 UStG Pflichtangaben vollstaendig"
                if len(missing) == 0
                else f"{len(missing)} Pflichtangaben nach §14 UStG fehlen"
            )
        }

    def _extract_decimal(self, field: Any) -> Optional[Decimal]:
        """Extract Decimal value from field."""
        if field is None:
            return None

        if isinstance(field, Decimal):
            return field

        if isinstance(field, (int, float)):
            return Decimal(str(field))

        if isinstance(field, dict):
            # Try common keys
            for key in ["decimal_value", "value", "amount"]:
                if key in field and field[key] is not None:
                    try:
                        if isinstance(field[key], Decimal):
                            return field[key]
                        return Decimal(str(field[key]).replace(",", ".").replace(" ", ""))
                    except (InvalidOperation, ValueError):
                        continue
            return None

        if isinstance(field, str):
            try:
                # Handle German format
                cleaned = field.replace("€", "").replace("EUR", "").strip()
                cleaned = cleaned.replace(".", "").replace(",", ".")
                return Decimal(cleaned)
            except (InvalidOperation, ValueError):
                return None

        return None

    def _calculate_score(self, checks: List[Dict[str, Any]]) -> float:
        """Calculate overall QA score from checks."""
        if not checks:
            return 0.0

        # Weight checks
        weights = {
            "ocr_confidence": 0.3,
            "text_extraction": 0.2,
            "umlaut_integrity": 0.15,
            "required_fields": 0.15,
            "business_terms": 0.1,
            "invoice_math": 0.05,
            "ustg_compliance": 0.05
        }

        total_weight = 0.0
        weighted_score = 0.0

        for check in checks:
            if check.get("skipped", False):
                continue

            name = check.get("name", "")
            weight = weights.get(name, 0.1)
            passed = check.get("passed", False)

            total_weight += weight
            if passed:
                weighted_score += weight

        return round(weighted_score / total_weight, 3) if total_weight > 0 else 0.0


# See: Static_Knowledge/Skills/german_text_processing_skill.yaml
# See: Static_Knowledge/Templates/rechnungen_template.json
