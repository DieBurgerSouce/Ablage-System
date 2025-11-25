"""Compliance Validator - §14 UStG"""

class ComplianceValidator:
    """Validate German invoice compliance (§14 UStG)."""

    REQUIRED_FIELDS_USTG_14 = [
        "rechnungsnummer",
        "datum",
        "steuernummer_or_ust_idnr",
        "netto",
        "mwst",
        "brutto"
    ]

    def validate_invoice(self, extracted_fields: dict) -> dict:
        """Validate §14 UStG compliance."""
        errors = []

        for field in self.REQUIRED_FIELDS_USTG_14:
            if field not in extracted_fields:
                errors.append(f"§14 UStG: Missing required field '{field}'")

        # Math check
        if all(f in extracted_fields for f in ["netto", "mwst", "brutto"]):
            netto = extracted_fields["netto"]
            mwst = extracted_fields["mwst"]
            brutto = extracted_fields["brutto"]

            expected = netto + mwst
            if abs(expected - brutto) > 0.02:
                errors.append(f"Math error: {netto} + {mwst} != {brutto}")

        return {"compliant": len(errors) == 0, "errors": errors}
