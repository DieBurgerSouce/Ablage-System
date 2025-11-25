"""OCR Quality Validator"""

class OCRQualityValidator:
    """Validate OCR output quality."""

    THRESHOLDS = {
        "min_confidence": 0.85,
        "min_text_length": 10,
        "max_unknown_chars_percent": 5
    }

    def validate(self, ocr_result: dict) -> dict:
        """Returns {valid: bool, issues: list}"""
        issues = []

        if ocr_result.get("confidence", 0) < self.THRESHOLDS["min_confidence"]:
            issues.append("Low OCR confidence")

        if len(ocr_result.get("text", "")) < self.THRESHOLDS["min_text_length"]:
            issues.append("Text too short")

        return {"valid": len(issues) == 0, "issues": issues}
