# -*- coding: utf-8 -*-
"""
Quality Assurance Agent for Ablage-System.

Enterprise-grade quality assurance for OCR output:
- Text quality validation
- German language accuracy checking
- Entity validation and plausibility
- Confidence score aggregation
- Automatic correction suggestions

Feinpoliert und durchdacht - Qualitätssicherung für perfekte Ergebnisse.
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import structlog

from app.agents.base import PostprocessingAgent
from app.german_validator import GermanValidator

logger = structlog.get_logger(__name__)


class QualityLevel:
    """Quality level constants."""
    EXCELLENT = "excellent"
    GOOD = "good"
    ACCEPTABLE = "acceptable"
    POOR = "poor"
    UNACCEPTABLE = "unacceptable"


class QAIssueType:
    """QA issue type constants."""
    UMLAUT_ERROR = "umlaut_error"
    DATE_FORMAT = "date_format"
    CURRENCY_FORMAT = "currency_format"
    IBAN_INVALID = "iban_invalid"
    VAT_ID_INVALID = "vat_id_invalid"
    LOW_CONFIDENCE = "low_confidence"
    TEXT_QUALITY = "text_quality"
    ENTITY_MISSING = "entity_missing"
    ENTITY_IMPLAUSIBLE = "entity_implausible"
    ENCODING_ERROR = "encoding_error"


class QAAgent(PostprocessingAgent):
    """
    Quality Assurance Agent for OCR output validation.

    Validates and scores OCR output for:
    - Overall text quality (readability, completeness)
    - German language accuracy (umlauts, special characters)
    - Entity extraction accuracy (dates, amounts, IBANs)
    - Document completeness
    - Plausibility checks
    """

    # Quality thresholds
    CONFIDENCE_THRESHOLD_HIGH = 0.9
    CONFIDENCE_THRESHOLD_MEDIUM = 0.75
    CONFIDENCE_THRESHOLD_LOW = 0.6

    # Issue severity weights
    ISSUE_SEVERITY = {
        QAIssueType.UMLAUT_ERROR: 0.8,
        QAIssueType.DATE_FORMAT: 0.6,
        QAIssueType.CURRENCY_FORMAT: 0.7,
        QAIssueType.IBAN_INVALID: 0.9,
        QAIssueType.VAT_ID_INVALID: 0.9,
        QAIssueType.LOW_CONFIDENCE: 0.5,
        QAIssueType.TEXT_QUALITY: 0.7,
        QAIssueType.ENTITY_MISSING: 0.6,
        QAIssueType.ENTITY_IMPLAUSIBLE: 0.8,
        QAIssueType.ENCODING_ERROR: 0.9,
    }

    # German month names for date validation
    GERMAN_MONTHS = [
        "januar", "februar", "märz", "april", "mai", "juni",
        "juli", "august", "september", "oktober", "november", "dezember",
    ]

    def __init__(self) -> None:
        """Initialize QA Agent."""
        super().__init__(name="qa_agent")
        self.validator = GermanValidator()

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform quality assurance on OCR output.

        Args:
            input_data: Dictionary containing:
                - text: OCR extracted text
                - entities: Extracted entities (optional)
                - ocr_confidence: OCR backend confidence (optional)
                - classification: Document classification (optional)
                - correction_result: German correction result (optional)

        Returns:
            QA result containing:
                - quality_score: Overall quality score (0-1)
                - quality_level: Quality level category
                - issues: List of identified issues
                - suggestions: List of correction suggestions
                - validation_details: Detailed validation results
                - is_acceptable: Boolean indicating if quality is acceptable
        """
        self.validate_input(input_data, ["text"])

        text = input_data["text"]
        entities = input_data.get("entities", [])
        ocr_confidence = input_data.get("ocr_confidence", 0.8)
        classification = input_data.get("classification", {})
        correction_result = input_data.get("correction_result", {})

        self.logger.info(
            "qa_started",
            text_length=len(text),
            entity_count=len(entities),
            ocr_confidence=ocr_confidence,
        )

        # Collect all issues
        issues: List[Dict[str, Any]] = []
        suggestions: List[Dict[str, Any]] = []

        # Run all quality checks
        text_quality = self._check_text_quality(text)
        issues.extend(text_quality["issues"])
        suggestions.extend(text_quality["suggestions"])

        german_quality = self._check_german_quality(text)
        issues.extend(german_quality["issues"])
        suggestions.extend(german_quality["suggestions"])

        entity_quality = self._check_entity_quality(entities, classification)
        issues.extend(entity_quality["issues"])
        suggestions.extend(entity_quality["suggestions"])

        confidence_check = self._check_confidence(ocr_confidence, entities)
        issues.extend(confidence_check["issues"])

        encoding_check = self._check_encoding(text)
        issues.extend(encoding_check["issues"])
        suggestions.extend(encoding_check["suggestions"])

        # Calculate overall quality score
        quality_score = self._calculate_quality_score(
            text_quality["score"],
            german_quality["score"],
            entity_quality["score"],
            ocr_confidence,
            issues,
        )

        # Determine quality level
        quality_level = self._determine_quality_level(quality_score)

        # Determine if acceptable
        is_acceptable = quality_level not in [
            QualityLevel.POOR,
            QualityLevel.UNACCEPTABLE,
        ]

        # Build validation details
        validation_details = {
            "text_quality": text_quality,
            "german_quality": german_quality,
            "entity_quality": entity_quality,
            "confidence_check": confidence_check,
            "encoding_check": encoding_check,
        }

        # Determine if human review is needed
        needs_review, review_reasons = self._determine_human_review(
            quality_level, quality_score, issues, ocr_confidence
        )

        result = {
            "quality_score": round(quality_score, 3),
            "quality_level": quality_level,
            "quality_level_german": self._get_german_quality_level(quality_level),
            "issues": issues,
            "issue_count": len(issues),
            "critical_issues": [i for i in issues if i.get("severity", 0) > 0.8],
            "suggestions": suggestions,
            "validation_details": validation_details,
            "is_acceptable": is_acceptable,
            "needs_review": needs_review,
            "review_reasons": review_reasons,
            "recommendation": self._get_recommendation(quality_level, issues),
        }

        self.logger.info(
            "qa_completed",
            quality_score=quality_score,
            quality_level=quality_level,
            issue_count=len(issues),
            is_acceptable=is_acceptable,
        )

        return result

    def _check_text_quality(self, text: str) -> Dict[str, Any]:
        """
        Check overall text quality.

        Validates:
        - Text length and completeness
        - Gibberish detection
        - Paragraph structure
        - Character distribution
        """
        issues = []
        suggestions = []
        score = 1.0

        # Check for empty or very short text
        if len(text.strip()) < 10:
            issues.append({
                "type": QAIssueType.TEXT_QUALITY,
                "message": "Text ist leer oder sehr kurz",
                "severity": 0.9,
            })
            score -= 0.4

        # Check for gibberish (high ratio of special characters)
        if text:
            special_ratio = len(re.findall(r'[^\w\s,.;:!?()äöüÄÖÜß€-]', text)) / len(text)
            if special_ratio > 0.2:
                issues.append({
                    "type": QAIssueType.TEXT_QUALITY,
                    "message": f"Hoher Anteil an Sonderzeichen ({special_ratio:.1%})",
                    "severity": 0.7,
                })
                score -= 0.2
                suggestions.append({
                    "type": "text_cleanup",
                    "message": "Manuelle Überprüfung des OCR-Ergebnisses empfohlen",
                })

        # Check for repeated characters (OCR error indicator)
        if text:
            repeated_pattern = re.findall(r'(.)\1{5,}', text)
            if repeated_pattern:
                issues.append({
                    "type": QAIssueType.TEXT_QUALITY,
                    "message": f"Wiederholte Zeichen gefunden: {repeated_pattern[:3]}",
                    "severity": 0.6,
                })
                score -= 0.15

        # Check for word density (words per character)
        if text:
            words = text.split()
            if len(text) > 100:
                word_density = len(words) / len(text)
                if word_density < 0.1:
                    issues.append({
                        "type": QAIssueType.TEXT_QUALITY,
                        "message": "Niedrige Wortdichte - möglicherweise fehlerhafte Erkennung",
                        "severity": 0.5,
                    })
                    score -= 0.1

        return {
            "score": max(0, score),
            "issues": issues,
            "suggestions": suggestions,
            "metrics": {
                "text_length": len(text),
                "word_count": len(text.split()) if text else 0,
            },
        }

    def _check_german_quality(self, text: str) -> Dict[str, Any]:
        """
        Check German language quality.

        Validates:
        - Umlaut presence and correctness
        - German word patterns
        - Common OCR errors in German text
        """
        issues = []
        suggestions = []
        score = 1.0

        # Use GermanValidator for umlaut check
        umlaut_result = self.validator.validate_umlauts(text)

        # Check for potential umlaut errors
        potential_errors = umlaut_result.get("potential_errors", [])
        if potential_errors:
            for error in potential_errors[:5]:  # Limit to 5 errors
                issues.append({
                    "type": QAIssueType.UMLAUT_ERROR,
                    "message": f"Möglicher Umlaut-Fehler: '{error}'",
                    "severity": 0.7,
                    "location": error,
                })
            score -= min(0.3, len(potential_errors) * 0.05)
            suggestions.append({
                "type": "umlaut_correction",
                "message": "Deutsche Umlaut-Korrektur anwenden",
                "affected_words": potential_errors[:5],
            })

        # Check for ae/oe/ue patterns that should be umlauts
        ae_patterns = re.findall(r'\b\w*ae\w*\b|\b\w*oe\w*\b|\b\w*ue\w*\b', text, re.IGNORECASE)
        if ae_patterns:
            # Filter out false positives
            likely_errors = [
                p for p in ae_patterns
                if any(pattern in p.lower() for pattern in [
                    'aend', 'aerzt', 'aehn', 'aerger', 'baeck', 'geraet',
                    'hoehe', 'koennen', 'moeglich', 'oeffn',
                    'fuer', 'muessen', 'pruef', 'ueber', 'zurueck',
                ])
            ]
            if likely_errors:
                issues.append({
                    "type": QAIssueType.UMLAUT_ERROR,
                    "message": f"ASCII-Umschreibungen gefunden: {likely_errors[:3]}",
                    "severity": 0.8,
                })
                score -= 0.2

        # Check for German-specific patterns
        german_confidence = umlaut_result.get("confidence", 0.8)
        if german_confidence < 0.7:
            issues.append({
                "type": QAIssueType.TEXT_QUALITY,
                "message": f"Niedrige deutsche Textqualität ({german_confidence:.0%})",
                "severity": 0.6,
            })
            score -= 0.15

        return {
            "score": max(0, score),
            "issues": issues,
            "suggestions": suggestions,
            "metrics": {
                "umlauts_found": umlaut_result.get("umlauts_found", []),
                "german_confidence": german_confidence,
                "potential_errors_count": len(potential_errors),
            },
        }

    def _check_entity_quality(
        self,
        entities: List[Dict[str, Any]],
        classification: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Check entity extraction quality.

        Validates:
        - Entity completeness based on document type
        - Entity format validity
        - Entity plausibility
        """
        issues = []
        suggestions = []
        score = 1.0

        document_type = classification.get("document_type", "other")

        # Check for expected entities based on document type
        expected_entities = self._get_expected_entities(document_type)

        entity_types = [e.get("type") for e in entities]

        for expected in expected_entities:
            if expected not in entity_types:
                issues.append({
                    "type": QAIssueType.ENTITY_MISSING,
                    "message": f"Erwartete Entität fehlt: {expected}",
                    "severity": 0.6,
                    "expected_type": expected,
                })
                score -= 0.1

        # Validate individual entities
        for entity in entities:
            entity_issues = self._validate_entity(entity)
            issues.extend(entity_issues)
            score -= len(entity_issues) * 0.05

        # Check for duplicate entities
        entity_values = [e.get("value") for e in entities if e.get("value")]
        duplicates = [v for v in set(entity_values) if entity_values.count(v) > 1]
        if duplicates:
            issues.append({
                "type": QAIssueType.TEXT_QUALITY,
                "message": f"Doppelte Entitäten gefunden: {duplicates[:3]}",
                "severity": 0.4,
            })

        # Plausibility checks
        plausibility_issues = self._check_entity_plausibility(entities, document_type)
        issues.extend(plausibility_issues)
        score -= len(plausibility_issues) * 0.1

        return {
            "score": max(0, score),
            "issues": issues,
            "suggestions": suggestions,
            "metrics": {
                "entity_count": len(entities),
                "expected_entities": expected_entities,
                "found_types": list(set(entity_types)),
            },
        }

    def _get_expected_entities(self, document_type: str) -> List[str]:
        """Get expected entities for document type."""
        expected = {
            "invoice": ["DATE", "CURRENCY", "INVOICE_NUMBER"],
            "contract": ["DATE", "COMPANY_NAME"],
            "receipt": ["DATE", "CURRENCY"],
            "form": ["DATE"],
            "letter": ["DATE"],
            "report": [],
            "other": [],
        }
        return expected.get(document_type, [])

    def _validate_entity(self, entity: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Validate individual entity."""
        issues = []
        entity_type = entity.get("type", "")
        value = entity.get("value", "")

        # IBAN validation
        if entity_type == "IBAN":
            if not entity.get("validated", True):
                issues.append({
                    "type": QAIssueType.IBAN_INVALID,
                    "message": f"IBAN-Prüfsumme ungültig: {value}",
                    "severity": 0.9,
                    "entity": entity,
                })

        # VAT ID validation
        if entity_type == "VAT_ID":
            if not entity.get("validated", True):
                issues.append({
                    "type": QAIssueType.VAT_ID_INVALID,
                    "message": f"USt-IdNr. ungültig: {value}",
                    "severity": 0.9,
                    "entity": entity,
                })

        # Date format validation
        if entity_type == "DATE":
            if not self._is_valid_german_date(value):
                issues.append({
                    "type": QAIssueType.DATE_FORMAT,
                    "message": f"Ungültiges Datumsformat: {value}",
                    "severity": 0.6,
                    "entity": entity,
                })

        # Currency validation
        if entity_type == "CURRENCY":
            numeric_value = entity.get("numeric_value")
            if numeric_value is None:
                issues.append({
                    "type": QAIssueType.CURRENCY_FORMAT,
                    "message": f"Währungsbetrag nicht parsebar: {value}",
                    "severity": 0.7,
                    "entity": entity,
                })

        return issues

    def _is_valid_german_date(self, date_str: str) -> bool:
        """Check if date string is valid German format."""
        # Try common German date patterns
        patterns = [
            r'^\d{1,2}\.\d{1,2}\.\d{2,4}$',  # DD.MM.YYYY or DD.MM.YY
            r'^\d{1,2}\.\s*\w+\s*\d{4}$',  # DD. Month YYYY
        ]

        for pattern in patterns:
            if re.match(pattern, date_str.strip()):
                return True

        # Check for German month names
        for month in self.GERMAN_MONTHS:
            if month in date_str.lower():
                return True

        return False

    def _check_entity_plausibility(
        self,
        entities: List[Dict[str, Any]],
        document_type: str,
    ) -> List[Dict[str, Any]]:
        """Check entity plausibility."""
        issues = []

        # Check date plausibility
        date_entities = [e for e in entities if e.get("type") == "DATE"]
        for date_entity in date_entities:
            value = date_entity.get("value", "")
            # Check for obviously wrong dates (e.g., year 3000)
            year_match = re.search(r'(\d{4})', value)
            if year_match:
                year = int(year_match.group(1))
                current_year = datetime.now().year
                if year < 1900 or year > current_year + 10:
                    issues.append({
                        "type": QAIssueType.ENTITY_IMPLAUSIBLE,
                        "message": f"Unplausibles Datum: {value}",
                        "severity": 0.8,
                        "entity": date_entity,
                    })

        # Check currency plausibility
        currency_entities = [e for e in entities if e.get("type") == "CURRENCY"]
        for currency_entity in currency_entities:
            numeric_value = currency_entity.get("numeric_value")
            if numeric_value is not None:
                # Flag extremely high or negative amounts
                if numeric_value < 0:
                    issues.append({
                        "type": QAIssueType.ENTITY_IMPLAUSIBLE,
                        "message": f"Negativer Betrag: {currency_entity.get('value')}",
                        "severity": 0.7,
                        "entity": currency_entity,
                    })
                elif numeric_value > 1_000_000_000:  # 1 billion
                    issues.append({
                        "type": QAIssueType.ENTITY_IMPLAUSIBLE,
                        "message": f"Sehr hoher Betrag: {currency_entity.get('value')}",
                        "severity": 0.6,
                        "entity": currency_entity,
                    })

        return issues

    def _check_confidence(
        self,
        ocr_confidence: float,
        entities: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Check confidence scores."""
        issues = []

        # Check overall OCR confidence
        if ocr_confidence < self.CONFIDENCE_THRESHOLD_LOW:
            issues.append({
                "type": QAIssueType.LOW_CONFIDENCE,
                "message": f"Sehr niedrige OCR-Konfidenz: {ocr_confidence:.0%}",
                "severity": 0.8,
            })
        elif ocr_confidence < self.CONFIDENCE_THRESHOLD_MEDIUM:
            issues.append({
                "type": QAIssueType.LOW_CONFIDENCE,
                "message": f"Niedrige OCR-Konfidenz: {ocr_confidence:.0%}",
                "severity": 0.5,
            })

        # Check entity confidences
        low_confidence_entities = [
            e for e in entities
            if e.get("confidence", 1.0) < self.CONFIDENCE_THRESHOLD_MEDIUM
        ]

        if low_confidence_entities:
            issues.append({
                "type": QAIssueType.LOW_CONFIDENCE,
                "message": f"{len(low_confidence_entities)} Entitäten mit niedriger Konfidenz",
                "severity": 0.5,
                "entities": [e.get("type") for e in low_confidence_entities],
            })

        return {
            "issues": issues,
            "metrics": {
                "ocr_confidence": ocr_confidence,
                "low_confidence_entity_count": len(low_confidence_entities),
            },
        }

    def _check_encoding(self, text: str) -> Dict[str, Any]:
        """Check for encoding issues."""
        issues = []
        suggestions = []

        # Check for common encoding problems (UTF-8 interpreted as Latin-1)
        encoding_errors = [
            ("\xc3\xa4", "ae-as-umlaut"),  # ä encoded wrong
            ("\xc3\xb6", "oe-as-umlaut"),  # ö encoded wrong
            ("\xc3\xbc", "ue-as-umlaut"),  # ü encoded wrong
            ("\xc3\x9f", "ss-as-eszett"),  # ß encoded wrong
            ("\xc3\x84", "Ae-as-umlaut"),  # Ä encoded wrong
            ("\xc3\x96", "Oe-as-umlaut"),  # Ö encoded wrong
            ("\xc3\x9c", "Ue-as-umlaut"),  # Ü encoded wrong
            ("\xe2\x80\x93", "en-dash"),   # – encoded wrong
            ("\xe2\x80\x99", "apostrophe"), # ' encoded wrong
            ("\xe2\x80\x9c", "quote-left"),  # " encoded wrong
            ("\xe2\x80\x9d", "quote-right"), # " encoded wrong
            ("\xc2\x80", "euro-sign"),     # € encoded wrong
        ]

        found_errors = []
        for bad, good in encoding_errors:
            if bad in text:
                found_errors.append((bad, good))

        if found_errors:
            issues.append({
                "type": QAIssueType.ENCODING_ERROR,
                "message": f"Encoding-Fehler gefunden: {[e[0] for e in found_errors[:3]]}",
                "severity": 0.9,
            })
            suggestions.append({
                "type": "encoding_fix",
                "message": "Encoding-Korrektur durchführen",
                "corrections": found_errors[:5],
            })

        # Check for replacement characters
        if "\ufffd" in text or "�" in text:
            issues.append({
                "type": QAIssueType.ENCODING_ERROR,
                "message": "Ersetzungszeichen (�) im Text gefunden",
                "severity": 0.8,
            })

        return {
            "issues": issues,
            "suggestions": suggestions,
            "metrics": {
                "encoding_errors_found": len(found_errors),
            },
        }

    def _calculate_quality_score(
        self,
        text_score: float,
        german_score: float,
        entity_score: float,
        ocr_confidence: float,
        issues: List[Dict[str, Any]],
    ) -> float:
        """Calculate overall quality score."""
        # Base scores with weights
        weighted_score = (
            text_score * 0.25 +
            german_score * 0.30 +
            entity_score * 0.20 +
            ocr_confidence * 0.25
        )

        # Apply issue penalties
        total_penalty = 0
        for issue in issues:
            severity = issue.get("severity", 0.5)
            weight = self.ISSUE_SEVERITY.get(issue.get("type"), 0.5)
            total_penalty += severity * weight * 0.05

        final_score = max(0, weighted_score - min(0.5, total_penalty))

        return final_score

    def _determine_quality_level(self, score: float) -> str:
        """Determine quality level from score."""
        if score >= 0.9:
            return QualityLevel.EXCELLENT
        elif score >= 0.75:
            return QualityLevel.GOOD
        elif score >= 0.6:
            return QualityLevel.ACCEPTABLE
        elif score >= 0.4:
            return QualityLevel.POOR
        else:
            return QualityLevel.UNACCEPTABLE

    def _get_german_quality_level(self, level: str) -> str:
        """Get German translation of quality level."""
        translations = {
            QualityLevel.EXCELLENT: "Ausgezeichnet",
            QualityLevel.GOOD: "Gut",
            QualityLevel.ACCEPTABLE: "Akzeptabel",
            QualityLevel.POOR: "Mangelhaft",
            QualityLevel.UNACCEPTABLE: "Unzureichend",
        }
        return translations.get(level, level)

    def _get_recommendation(
        self,
        quality_level: str,
        issues: List[Dict[str, Any]],
    ) -> str:
        """Get recommendation based on quality assessment."""
        critical_issues = [i for i in issues if i.get("severity", 0) > 0.8]

        if quality_level == QualityLevel.EXCELLENT:
            return "Das Dokument wurde erfolgreich verarbeitet. Keine weitere Aktion erforderlich."

        if quality_level == QualityLevel.GOOD:
            return "Die Qualität ist gut. Optional: Überprüfen Sie gekennzeichnete Entitäten."

        if quality_level == QualityLevel.ACCEPTABLE:
            if critical_issues:
                return f"Manuelle Überprüfung empfohlen. {len(critical_issues)} kritische Probleme gefunden."
            return "Die Qualität ist akzeptabel. Manuelle Stichprobe empfohlen."

        if quality_level == QualityLevel.POOR:
            return "Manuelle Korrektur erforderlich. Das OCR-Ergebnis weist mehrere Probleme auf."

        return "Das Dokument sollte erneut gescannt und verarbeitet werden. Die Qualität ist unzureichend."

    def _determine_human_review(
        self,
        quality_level: str,
        quality_score: float,
        issues: List[Dict[str, Any]],
        ocr_confidence: float,
    ) -> Tuple[bool, List[str]]:
        """
        Determine if human review is needed and why.

        Review is triggered for:
        - Poor or unacceptable quality levels
        - Multiple critical issues
        - Very low confidence scores
        - Invalid critical entities (IBANs, VAT IDs)
        - Severe encoding problems

        Args:
            quality_level: Quality level category
            quality_score: Overall quality score (0-1)
            issues: List of identified issues
            ocr_confidence: Original OCR confidence

        Returns:
            Tuple of (needs_review: bool, review_reasons: List[str])
        """
        needs_review = False
        review_reasons = []

        # Rule 1: Quality level is poor or unacceptable
        if quality_level in [QualityLevel.POOR, QualityLevel.UNACCEPTABLE]:
            needs_review = True
            review_reasons.append(
                f"Qualitätsstufe '{self._get_german_quality_level(quality_level)}' "
                f"(Score: {quality_score:.0%})"
            )

        # Rule 2: Critical issues (severity > 0.8)
        critical_issues = [i for i in issues if i.get("severity", 0) > 0.8]
        if len(critical_issues) >= 2:
            needs_review = True
            issue_types = list(set(i.get("type", "unbekannt") for i in critical_issues))
            review_reasons.append(
                f"{len(critical_issues)} kritische Probleme: {', '.join(issue_types[:3])}"
            )

        # Rule 3: Very low OCR confidence
        if ocr_confidence < self.CONFIDENCE_THRESHOLD_LOW:
            needs_review = True
            review_reasons.append(
                f"Sehr niedrige OCR-Konfidenz: {ocr_confidence:.0%}"
            )

        # Rule 4: Invalid critical entities (IBAN, VAT ID)
        critical_entity_issues = [
            i for i in issues
            if i.get("type") in [QAIssueType.IBAN_INVALID, QAIssueType.VAT_ID_INVALID]
        ]
        if critical_entity_issues:
            needs_review = True
            for issue in critical_entity_issues[:2]:
                review_reasons.append(issue.get("message", "Ungültige kritische Entität"))

        # Rule 5: Severe encoding problems
        encoding_issues = [
            i for i in issues
            if i.get("type") == QAIssueType.ENCODING_ERROR and i.get("severity", 0) > 0.8
        ]
        if encoding_issues:
            needs_review = True
            review_reasons.append("Schwerwiegende Encoding-Fehler gefunden")

        # Rule 6: Quality score below threshold (configurable)
        from app.core.config import settings
        review_threshold = getattr(settings, "QA_REVIEW_THRESHOLD", 0.7)
        if quality_score < review_threshold and not needs_review:
            needs_review = True
            review_reasons.append(
                f"Qualitätsscore ({quality_score:.0%}) unter Schwellwert ({review_threshold:.0%})"
            )

        # Log if review needed
        if needs_review:
            logger.info(
                "human_review_triggered",
                quality_score=quality_score,
                reason_count=len(review_reasons),
                reasons=review_reasons[:3],
            )

        return needs_review, review_reasons

    def get_qa_stats(self) -> Dict[str, Any]:
        """Get QA agent statistics."""
        return {
            "issue_types": list(QAIssueType.__dict__.keys()),
            "quality_levels": [
                QualityLevel.EXCELLENT,
                QualityLevel.GOOD,
                QualityLevel.ACCEPTABLE,
                QualityLevel.POOR,
                QualityLevel.UNACCEPTABLE,
            ],
            "confidence_thresholds": {
                "high": self.CONFIDENCE_THRESHOLD_HIGH,
                "medium": self.CONFIDENCE_THRESHOLD_MEDIUM,
                "low": self.CONFIDENCE_THRESHOLD_LOW,
            },
        }
