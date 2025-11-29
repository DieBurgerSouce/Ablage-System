"""
Validation Sub-Agent - Specialized field validation
Implementiert deutsche Feld-Validierung fuer Datum, Waehrung und Steuer-IDs
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from decimal import Decimal

import structlog

logger = structlog.get_logger(__name__)


class ValidationSubAgent:
    """
    Sub-agent for validating specific field types.

    Specializations:
    - German dates (DD.MM.YYYY)
    - German currency (1.234,56 EUR)
    - Tax IDs (Steuernummer, USt-IdNr)
    - Company names with legal forms
    """

    def validate_german_date(self, date_str: str) -> Dict[str, Any]:
        """
        Validate German date format (DD.MM.YYYY).

        Supports formats:
        - DD.MM.YYYY (e.g., 31.12.2024)
        - D.M.YYYY (e.g., 1.5.2024)
        - Month names (e.g., 31. Dezember 2024)

        Args:
            date_str: Date string to validate

        Returns:
            {
                "valid": bool,
                "parsed": datetime or None,
                "format": detected format,
                "errors": list of error messages (German)
            }
        """
        result = {
            "valid": False,
            "parsed": None,
            "format": None,
            "errors": []
        }

        if not date_str or not isinstance(date_str, str):
            result["errors"].append("Kein Datum angegeben")
            return result

        date_str = date_str.strip()

        try:
            from Static_Knowledge.Snippets.german_validation_snippets import (
                validate_german_date,
                parse_german_date_with_month_name
            )

            # Try standard DD.MM.YYYY format first
            is_valid, parsed = validate_german_date(date_str)

            if is_valid and parsed:
                result["valid"] = True
                result["parsed"] = parsed
                result["format"] = "DD.MM.YYYY"

                logger.debug(
                    "german_date_validated",
                    date=date_str,
                    parsed=parsed.isoformat()
                )
                return result

            # Try month name format (e.g., "31. Dezember 2024")
            parsed_month = parse_german_date_with_month_name(date_str)
            if parsed_month:
                result["valid"] = True
                result["parsed"] = parsed_month
                result["format"] = "DD. Monat YYYY"
                return result

            # Validation failed
            result["errors"].append(
                f"Ungueltiges Datumsformat: '{date_str}'. "
                "Erwartet: DD.MM.YYYY oder 'DD. Monat YYYY'"
            )

        except ImportError:
            # Fallback implementation
            import re

            pattern = r'^(\d{1,2})\.(\d{1,2})\.(\d{4})$'
            match = re.match(pattern, date_str)

            if match:
                try:
                    day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
                    parsed = datetime(year, month, day)
                    result["valid"] = True
                    result["parsed"] = parsed
                    result["format"] = "DD.MM.YYYY"
                except ValueError as e:
                    result["errors"].append(f"Ungueltiges Datum: {e}")
            else:
                result["errors"].append(
                    f"Ungueltiges Datumsformat: '{date_str}'"
                )

        except Exception as e:
            logger.error("date_validation_error", error=str(e))
            result["errors"].append(f"Validierungsfehler: {e}")

        return result

    def validate_german_currency(self, amount_str: str) -> Dict[str, Any]:
        """
        Validate German currency format (1.234,56 EUR).

        Supports formats:
        - 1.234,56 EUR
        - 1234,56EUR
        - EUR 1.234,56
        - 1.234,56

        Args:
            amount_str: Currency string to validate

        Returns:
            {
                "valid": bool,
                "value": Decimal or None,
                "formatted": German formatted string,
                "errors": list of error messages (German)
            }
        """
        result = {
            "valid": False,
            "value": None,
            "formatted": None,
            "errors": []
        }

        if not amount_str or not isinstance(amount_str, str):
            result["errors"].append("Kein Betrag angegeben")
            return result

        amount_str = amount_str.strip()

        try:
            from Static_Knowledge.Snippets.german_validation_snippets import (
                validate_german_currency,
                format_german_currency
            )

            is_valid, decimal_value = validate_german_currency(amount_str)

            if is_valid and decimal_value is not None:
                result["valid"] = True
                result["value"] = decimal_value
                result["formatted"] = format_german_currency(float(decimal_value))

                logger.debug(
                    "german_currency_validated",
                    input=amount_str,
                    value=str(decimal_value)
                )
                return result

            # Validation failed
            result["errors"].append(
                f"Ungueltiges Waehrungsformat: '{amount_str}'. "
                "Erwartet: 1.234,56 EUR oder 1234,56"
            )

        except ImportError:
            # Fallback implementation
            import re

            # Remove currency symbol and whitespace
            cleaned = amount_str.replace('€', '').replace('EUR', '').strip()

            # Pattern: 1.234,56 or 1234,56
            pattern = r'^(\d{1,3}(?:\.\d{3})*),(\d{2})$'
            match = re.match(pattern, cleaned)

            if match:
                try:
                    # Convert German format to decimal
                    numeric = cleaned.replace('.', '').replace(',', '.')
                    decimal_value = Decimal(numeric)
                    result["valid"] = True
                    result["value"] = decimal_value
                    result["formatted"] = f"{cleaned} €"
                except Exception as e:
                    result["errors"].append(f"Konvertierungsfehler: {e}")
            else:
                result["errors"].append(
                    f"Ungueltiges Waehrungsformat: '{amount_str}'"
                )

        except Exception as e:
            logger.error("currency_validation_error", error=str(e))
            result["errors"].append(f"Validierungsfehler: {e}")

        return result

    def validate_tax_id(
        self,
        tax_id: str,
        id_type: str = "auto"
    ) -> Dict[str, Any]:
        """
        Validate German tax ID (USt-IdNr or Steuernummer).

        USt-IdNr format: DE + 9 digits (e.g., DE123456789)
        Steuernummer format: XX/XXX/XXXXX (regional variations)

        Args:
            tax_id: Tax ID string to validate
            id_type: "ust_idnr", "steuernummer", or "auto" (detect automatically)

        Returns:
            {
                "valid": bool,
                "type": "ust_idnr" or "steuernummer" or None,
                "normalized": cleaned/normalized ID,
                "errors": list of error messages (German)
            }
        """
        result = {
            "valid": False,
            "type": None,
            "normalized": None,
            "errors": []
        }

        if not tax_id or not isinstance(tax_id, str):
            result["errors"].append("Keine Steuer-ID angegeben")
            return result

        tax_id = tax_id.strip().upper()

        try:
            from Static_Knowledge.Snippets.german_validation_snippets import (
                validate_ust_idnr,
                validate_steuernummer
            )

            # Auto-detect type based on format
            if id_type == "auto":
                if tax_id.startswith("DE"):
                    id_type = "ust_idnr"
                elif "/" in tax_id or len(tax_id.replace("/", "").replace("-", "")) >= 10:
                    id_type = "steuernummer"
                else:
                    # Try both
                    if validate_ust_idnr(tax_id):
                        id_type = "ust_idnr"
                    elif validate_steuernummer(tax_id):
                        id_type = "steuernummer"
                    else:
                        result["errors"].append(
                            "Steuer-ID Format nicht erkannt. "
                            "Gueltig: USt-IdNr (DE + 9 Ziffern) oder Steuernummer (XX/XXX/XXXXX)"
                        )
                        return result

            # Validate based on detected/specified type
            if id_type == "ust_idnr":
                is_valid = validate_ust_idnr(tax_id)
                if is_valid:
                    result["valid"] = True
                    result["type"] = "ust_idnr"
                    result["normalized"] = tax_id
                else:
                    result["errors"].append(
                        f"Ungueltige USt-IdNr: '{tax_id}'. "
                        "Erwartet: DE + 9 Ziffern (z.B. DE123456789)"
                    )

            elif id_type == "steuernummer":
                is_valid = validate_steuernummer(tax_id)
                if is_valid:
                    result["valid"] = True
                    result["type"] = "steuernummer"
                    result["normalized"] = tax_id
                else:
                    result["errors"].append(
                        f"Ungueltige Steuernummer: '{tax_id}'. "
                        "Erwartet: XX/XXX/XXXXX (z.B. 19/815/08155)"
                    )

            if result["valid"]:
                logger.debug(
                    "tax_id_validated",
                    tax_id=tax_id,
                    type=result["type"]
                )

        except ImportError:
            # Fallback implementation
            import re

            if id_type == "auto":
                if tax_id.startswith("DE"):
                    id_type = "ust_idnr"
                else:
                    id_type = "steuernummer"

            if id_type == "ust_idnr":
                pattern = r'^DE\d{9}$'
                if re.match(pattern, tax_id):
                    result["valid"] = True
                    result["type"] = "ust_idnr"
                    result["normalized"] = tax_id
                else:
                    result["errors"].append(f"Ungueltige USt-IdNr: '{tax_id}'")

            elif id_type == "steuernummer":
                pattern = r'^\d{2,3}/\d{3}/\d{5}$'
                if re.match(pattern, tax_id):
                    result["valid"] = True
                    result["type"] = "steuernummer"
                    result["normalized"] = tax_id
                else:
                    result["errors"].append(f"Ungueltige Steuernummer: '{tax_id}'")

        except Exception as e:
            logger.error("tax_id_validation_error", error=str(e))
            result["errors"].append(f"Validierungsfehler: {e}")

        return result

    def validate_iban(self, iban: str) -> Dict[str, Any]:
        """
        Validate German IBAN.

        Format: DE + 2 check digits + 8 bank code + 10 account number (22 chars total)

        Args:
            iban: IBAN string to validate

        Returns:
            {
                "valid": bool,
                "country": "DE" or None,
                "bic_hint": partial BIC from bank code,
                "errors": list of error messages
            }
        """
        result = {
            "valid": False,
            "country": None,
            "bic_hint": None,
            "errors": []
        }

        if not iban or not isinstance(iban, str):
            result["errors"].append("Keine IBAN angegeben")
            return result

        # Remove spaces and convert to uppercase
        iban = iban.replace(" ", "").replace("-", "").upper()

        # Check length for German IBAN
        if not iban.startswith("DE"):
            result["errors"].append("Nur deutsche IBANs (DE) werden unterstuetzt")
            return result

        if len(iban) != 22:
            result["errors"].append(
                f"Ungueltige IBAN-Laenge: {len(iban)} statt 22 Zeichen"
            )
            return result

        # Basic format validation
        import re
        if not re.match(r'^DE\d{20}$', iban):
            result["errors"].append("IBAN muss DE + 20 Ziffern sein")
            return result

        # IBAN checksum validation (ISO 7064 Mod 97-10)
        try:
            # Move first 4 chars to end
            rearranged = iban[4:] + iban[:4]

            # Convert letters to numbers (A=10, B=11, ..., Z=35)
            numeric = ""
            for char in rearranged:
                if char.isdigit():
                    numeric += char
                else:
                    numeric += str(ord(char) - 55)

            # Mod 97 check
            if int(numeric) % 97 == 1:
                result["valid"] = True
                result["country"] = "DE"
                result["bic_hint"] = iban[4:12]  # Bank code (BLZ)

                logger.debug(
                    "iban_validated",
                    iban=f"{iban[:4]}...{iban[-4:]}",  # Partial for logging
                    bank_code=result["bic_hint"]
                )
            else:
                result["errors"].append("IBAN-Pruefsumme ungueltig")

        except Exception as e:
            logger.error("iban_validation_error", error=str(e))
            result["errors"].append(f"Validierungsfehler: {e}")

        return result

    def validate_all(self, data: Dict[str, str]) -> Dict[str, Any]:
        """
        Validate multiple fields at once.

        Args:
            data: Dictionary with field names and values
                  Supported keys: date, currency, tax_id, iban

        Returns:
            {
                "all_valid": bool,
                "results": {field_name: validation_result, ...},
                "error_count": int
            }
        """
        results = {}
        error_count = 0

        for field_name, value in data.items():
            if field_name == "date" or field_name.endswith("_date"):
                results[field_name] = self.validate_german_date(value)
            elif field_name == "currency" or field_name.endswith("_amount"):
                results[field_name] = self.validate_german_currency(value)
            elif field_name == "tax_id" or "steuer" in field_name.lower():
                results[field_name] = self.validate_tax_id(value)
            elif field_name == "iban":
                results[field_name] = self.validate_iban(value)
            else:
                results[field_name] = {
                    "valid": True,
                    "note": "Keine spezifische Validierung"
                }

            if not results[field_name].get("valid", True):
                error_count += 1

        return {
            "all_valid": error_count == 0,
            "results": results,
            "error_count": error_count
        }


# See: Static_Knowledge/Snippets/german_validation_snippets.py
