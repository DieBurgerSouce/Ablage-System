# -*- coding: utf-8 -*-
"""
Quality Assurance Agent for Ablage-System.

Enterprise-grade quality assurance for OCR output:
- Text quality validation
- German language accuracy checking
- Entity validation and plausibility
- Confidence score aggregation
- Automatic correction suggestions
- Semantic plausibility checking
- Cross-entity validation
- Document completeness scoring
- Comprehensive quality metrics

Feinpoliert und durchdacht - Qualitätssicherung für perfekte Ergebnisse.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

import structlog

from app.agents.base import PostprocessingAgent
from app.german_validator import GermanValidator

logger = structlog.get_logger(__name__)


@dataclass
class QualityMetrics:
    """Comprehensive quality metrics for a document."""
    overall_score: float = 0.0
    text_quality_score: float = 0.0
    german_quality_score: float = 0.0
    entity_quality_score: float = 0.0
    completeness_score: float = 0.0
    plausibility_score: float = 0.0
    ocr_confidence: float = 0.0
    issue_count: int = 0
    critical_issue_count: int = 0
    suggestion_count: int = 0

    def to_dict(self) -> Dict[str, object]:
        """Convert to dictionary."""
        return {
            "overall_score": round(self.overall_score, 3),
            "text_quality_score": round(self.text_quality_score, 3),
            "german_quality_score": round(self.german_quality_score, 3),
            "entity_quality_score": round(self.entity_quality_score, 3),
            "completeness_score": round(self.completeness_score, 3),
            "plausibility_score": round(self.plausibility_score, 3),
            "ocr_confidence": round(self.ocr_confidence, 3),
            "issue_count": self.issue_count,
            "critical_issue_count": self.critical_issue_count,
            "suggestion_count": self.suggestion_count,
        }


@dataclass
class SemanticCheck:
    """Result of a semantic plausibility check."""
    check_name: str
    passed: bool
    message: str
    severity: float = 0.5
    details: Dict[str, object] = field(default_factory=dict)


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
    # New semantic/cross-entity issues
    SEMANTIC_INCONSISTENCY = "semantic_inconsistency"
    DATE_SEQUENCE_ERROR = "date_sequence_error"
    AMOUNT_MISMATCH = "amount_mismatch"
    DOCUMENT_INCOMPLETE = "document_incomplete"
    CROSS_ENTITY_CONFLICT = "cross_entity_conflict"


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
        # New issue types
        QAIssueType.SEMANTIC_INCONSISTENCY: 0.75,
        QAIssueType.DATE_SEQUENCE_ERROR: 0.7,
        QAIssueType.AMOUNT_MISMATCH: 0.8,
        QAIssueType.DOCUMENT_INCOMPLETE: 0.6,
        QAIssueType.CROSS_ENTITY_CONFLICT: 0.75,
    }

    # Document completeness requirements by type
    COMPLETENESS_REQUIREMENTS = {
        "invoice": {
            "required": ["DATE", "CURRENCY", "INVOICE_NUMBER"],
            "recommended": ["IBAN", "VAT_ID", "ADDRESS"],
            "min_text_length": 100,
        },
        "contract": {
            "required": ["DATE", "PERSON", "ORGANIZATION"],
            "recommended": ["ADDRESS", "CONTRACT_FIELD"],
            "min_text_length": 500,
        },
        "receipt": {
            "required": ["DATE", "CURRENCY"],
            "recommended": [],
            "min_text_length": 50,
        },
        "letter": {
            "required": ["DATE"],
            "recommended": ["ADDRESS", "PERSON"],
            "min_text_length": 100,
        },
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

    async def process(self, input_data: Dict[str, object]) -> Dict[str, object]:
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
        issues: List[Dict[str, object]] = []
        suggestions: List[Dict[str, object]] = []

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

        # NEW: Semantic plausibility checks
        semantic_check = self._check_semantic_plausibility(text, entities, classification)
        issues.extend(semantic_check["issues"])
        suggestions.extend(semantic_check["suggestions"])

        # NEW: Cross-entity validation
        cross_entity_check = self._check_cross_entity_consistency(entities, classification)
        issues.extend(cross_entity_check["issues"])
        suggestions.extend(cross_entity_check["suggestions"])

        # NEW: Document completeness check
        completeness_check = self._check_document_completeness(
            text, entities, classification
        )
        issues.extend(completeness_check["issues"])
        suggestions.extend(completeness_check["suggestions"])

        # Calculate overall quality score (updated to include new checks)
        quality_score = self._calculate_quality_score(
            text_quality["score"],
            german_quality["score"],
            entity_quality["score"],
            ocr_confidence,
            issues,
            completeness_score=completeness_check["score"],
            semantic_score=semantic_check["score"],
        )

        # Determine quality level
        quality_level = self._determine_quality_level(quality_score)

        # Determine if acceptable
        is_acceptable = quality_level not in [
            QualityLevel.POOR,
            QualityLevel.UNACCEPTABLE,
        ]

        # Build validation details (including new checks)
        validation_details = {
            "text_quality": text_quality,
            "german_quality": german_quality,
            "entity_quality": entity_quality,
            "confidence_check": confidence_check,
            "encoding_check": encoding_check,
            "semantic_check": semantic_check,
            "cross_entity_check": cross_entity_check,
            "completeness_check": completeness_check,
        }

        # Build comprehensive quality metrics
        critical_issues = [i for i in issues if i.get("severity", 0) > 0.8]
        quality_metrics = QualityMetrics(
            overall_score=quality_score,
            text_quality_score=text_quality["score"],
            german_quality_score=german_quality["score"],
            entity_quality_score=entity_quality["score"],
            completeness_score=completeness_check["score"],
            plausibility_score=semantic_check["score"],
            ocr_confidence=ocr_confidence,
            issue_count=len(issues),
            critical_issue_count=len(critical_issues),
            suggestion_count=len(suggestions),
        )

        # Determine if human review is needed
        needs_review, review_reasons = self._determine_human_review(
            quality_level, quality_score, issues, ocr_confidence
        )

        result = {
            "quality_score": round(quality_score, 3),
            "quality_level": quality_level,
            "quality_level_german": self._get_german_quality_level(quality_level),
            "quality_metrics": quality_metrics.to_dict(),
            "issues": issues,
            "issue_count": len(issues),
            "critical_issues": critical_issues,
            "suggestions": suggestions,
            "validation_details": validation_details,
            "is_acceptable": is_acceptable,
            "needs_review": needs_review,
            "review_reasons": review_reasons,
            "recommendation": self._get_recommendation(quality_level, issues),
            "summary": self._generate_quality_summary(
                quality_metrics, quality_level, issues, suggestions
            ),
        }

        self.logger.info(
            "qa_completed",
            quality_score=quality_score,
            quality_level=quality_level,
            issue_count=len(issues),
            is_acceptable=is_acceptable,
        )

        return result

    def _check_text_quality(self, text: str) -> Dict[str, object]:
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

    def _check_german_quality(self, text: str) -> Dict[str, object]:
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
                    'aend', 'aerzt', 'aehn', 'ärger', 'baeck', 'geraet',
                    'höhe', 'können', 'möglich', 'öffn',
                    'für', 'müssen', 'prüf', 'über', 'zurück',
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
        entities: List[Dict[str, object]],
        classification: Dict[str, object],
    ) -> Dict[str, object]:
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
        # Convert dicts to strings for hashability comparison
        hashable_values = [
            str(v) if isinstance(v, dict) else v
            for v in entity_values
        ]
        try:
            duplicates = [v for v in set(hashable_values) if hashable_values.count(v) > 1]
        except TypeError:
            # Fallback if values still not hashable
            duplicates = []
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

    def _validate_entity(self, entity: Dict[str, object]) -> List[Dict[str, object]]:
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
        entities: List[Dict[str, object]],
        document_type: str,
    ) -> List[Dict[str, object]]:
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
        entities: List[Dict[str, object]],
    ) -> Dict[str, object]:
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

    def _check_encoding(self, text: str) -> Dict[str, object]:
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
        issues: List[Dict[str, object]],
        completeness_score: float = 1.0,
        semantic_score: float = 1.0,
    ) -> float:
        """
        Calculate overall quality score.

        Weights:
        - Text quality: 20%
        - German language quality: 25%
        - Entity extraction quality: 15%
        - OCR confidence: 15%
        - Document completeness: 15%
        - Semantic plausibility: 10%
        """
        # Base scores with updated weights
        weighted_score = (
            text_score * 0.20 +
            german_score * 0.25 +
            entity_score * 0.15 +
            ocr_confidence * 0.15 +
            completeness_score * 0.15 +
            semantic_score * 0.10
        )

        # Apply issue penalties
        total_penalty = 0
        for issue in issues:
            severity = issue.get("severity", 0.5)
            weight = self.ISSUE_SEVERITY.get(issue.get("type"), 0.5)
            total_penalty += severity * weight * 0.03

        final_score = max(0, weighted_score - min(0.4, total_penalty))

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
        issues: List[Dict[str, object]],
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
        issues: List[Dict[str, object]],
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

    def get_qa_stats(self) -> Dict[str, object]:
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

    def _check_semantic_plausibility(
        self,
        text: str,
        entities: List[Dict[str, object]],
        classification: Dict[str, object],
    ) -> Dict[str, object]:
        """
        Check semantic plausibility of document content.

        Validates:
        - Date sequences (start before end dates)
        - Amount consistency (subtotals add up)
        - Logical entity relationships
        - Document-type specific rules

        Args:
            text: OCR extracted text
            entities: Extracted entities
            classification: Document classification

        Returns:
            Dictionary with score, issues, suggestions, and semantic checks
        """
        issues: List[Dict[str, object]] = []
        suggestions: List[Dict[str, object]] = []
        semantic_checks: List[SemanticCheck] = []
        score = 1.0

        document_type = classification.get("document_type", "other")

        # Check 1: Date sequence validation
        date_check = self._validate_date_sequences(entities)
        semantic_checks.append(date_check)
        if not date_check.passed:
            issues.append({
                "type": QAIssueType.DATE_SEQUENCE_ERROR,
                "message": date_check.message,
                "severity": date_check.severity,
                "details": date_check.details,
            })
            score -= 0.15
            suggestions.append({
                "type": "date_correction",
                "message": "Datumsreihenfolge überprüfen",
                "details": date_check.details,
            })

        # Check 2: Amount consistency (for invoices)
        if document_type == "invoice":
            amount_check = self._validate_amount_consistency(entities)
            semantic_checks.append(amount_check)
            if not amount_check.passed:
                issues.append({
                    "type": QAIssueType.AMOUNT_MISMATCH,
                    "message": amount_check.message,
                    "severity": amount_check.severity,
                    "details": amount_check.details,
                })
                score -= 0.2
                suggestions.append({
                    "type": "amount_verification",
                    "message": "Beträge manuell überprüfen",
                    "details": amount_check.details,
                })

        # Check 3: Invoice number format
        if document_type == "invoice":
            invoice_check = self._validate_invoice_number(entities, text)
            semantic_checks.append(invoice_check)
            if not invoice_check.passed:
                issues.append({
                    "type": QAIssueType.SEMANTIC_INCONSISTENCY,
                    "message": invoice_check.message,
                    "severity": invoice_check.severity,
                })
                score -= 0.1

        # Check 4: Contract date logic
        if document_type == "contract":
            contract_check = self._validate_contract_dates(entities)
            semantic_checks.append(contract_check)
            if not contract_check.passed:
                issues.append({
                    "type": QAIssueType.DATE_SEQUENCE_ERROR,
                    "message": contract_check.message,
                    "severity": contract_check.severity,
                    "details": contract_check.details,
                })
                score -= 0.15

        # Check 5: Text content matches document type
        content_check = self._validate_content_matches_type(text, document_type)
        semantic_checks.append(content_check)
        if not content_check.passed:
            issues.append({
                "type": QAIssueType.SEMANTIC_INCONSISTENCY,
                "message": content_check.message,
                "severity": content_check.severity,
            })
            score -= 0.1
            suggestions.append({
                "type": "classification_review",
                "message": "Dokumentklassifikation überprüfen",
            })

        return {
            "score": max(0, score),
            "issues": issues,
            "suggestions": suggestions,
            "semantic_checks": [
                {
                    "name": c.check_name,
                    "passed": c.passed,
                    "message": c.message,
                }
                for c in semantic_checks
            ],
            "checks_passed": sum(1 for c in semantic_checks if c.passed),
            "checks_total": len(semantic_checks),
        }

    def _validate_date_sequences(
        self, entities: List[Dict[str, object]]
    ) -> SemanticCheck:
        """Validate that date sequences are logical (start before end)."""
        date_entities = [e for e in entities if e.get("type") == "DATE"]

        # Look for start/end date pairs
        start_dates = []
        end_dates = []

        for entity in date_entities:
            context = entity.get("context", "").lower()
            value = entity.get("value", "")
            parsed = entity.get("parsed_date")

            if any(kw in context for kw in ["beginn", "start", "ab", "von", "anfang"]):
                start_dates.append({"value": value, "parsed": parsed, "entity": entity})
            elif any(kw in context for kw in ["ende", "bis", "ablauf", "endet"]):
                end_dates.append({"value": value, "parsed": parsed, "entity": entity})

        # Check if any end date is before start date
        for start in start_dates:
            for end in end_dates:
                start_parsed = start.get("parsed")
                end_parsed = end.get("parsed")

                if start_parsed and end_parsed:
                    try:
                        if isinstance(start_parsed, str):
                            start_dt = datetime.fromisoformat(start_parsed)
                        else:
                            start_dt = start_parsed

                        if isinstance(end_parsed, str):
                            end_dt = datetime.fromisoformat(end_parsed)
                        else:
                            end_dt = end_parsed

                        if end_dt < start_dt:
                            return SemanticCheck(
                                check_name="date_sequence",
                                passed=False,
                                message=f"Enddatum ({end['value']}) liegt vor Startdatum ({start['value']})",
                                severity=0.8,
                                details={
                                    "start_date": start["value"],
                                    "end_date": end["value"],
                                },
                            )
                    except (ValueError, TypeError) as e:
                        logger.debug(
                            "date_sequence_parse_failed",
                            error_type=type(e).__name__,
                        )

        return SemanticCheck(
            check_name="date_sequence",
            passed=True,
            message="Datumsreihenfolge ist korrekt",
            severity=0.0,
        )

    def _validate_amount_consistency(
        self, entities: List[Dict[str, object]]
    ) -> SemanticCheck:
        """Validate that amounts in invoice are consistent (subtotals add up)."""
        currency_entities = [
            e for e in entities
            if e.get("type") == "CURRENCY" and e.get("numeric_value") is not None
        ]

        if len(currency_entities) < 2:
            return SemanticCheck(
                check_name="amount_consistency",
                passed=True,
                message="Nicht genug Beträge für Konsistenzprüfung",
                severity=0.0,
            )

        # Try to identify total, subtotal, and tax amounts
        total_amount = None
        subtotal = None
        tax_amount = None

        for entity in currency_entities:
            context = entity.get("context", "").lower()
            value = entity.get("numeric_value")

            if any(kw in context for kw in ["gesamt", "total", "summe", "endbetrag"]):
                if total_amount is None or value > total_amount:
                    total_amount = value
            elif any(kw in context for kw in ["netto", "zwischensumme", "subtotal"]):
                subtotal = value
            elif any(kw in context for kw in ["mwst", "ust", "steuer", "vat", "tax"]):
                tax_amount = value

        # Validate: subtotal + tax ≈ total
        if total_amount and subtotal and tax_amount:
            calculated_total = subtotal + tax_amount
            tolerance = total_amount * 0.01  # 1% tolerance

            if abs(calculated_total - total_amount) > tolerance:
                return SemanticCheck(
                    check_name="amount_consistency",
                    passed=False,
                    message=f"Beträge inkonsistent: Netto ({subtotal:.2f}) + MwSt ({tax_amount:.2f}) ≠ Gesamt ({total_amount:.2f})",
                    severity=0.8,
                    details={
                        "subtotal": subtotal,
                        "tax": tax_amount,
                        "calculated_total": calculated_total,
                        "stated_total": total_amount,
                        "difference": abs(calculated_total - total_amount),
                    },
                )

        return SemanticCheck(
            check_name="amount_consistency",
            passed=True,
            message="Beträge sind konsistent",
            severity=0.0,
        )

    def _validate_invoice_number(
        self, entities: List[Dict[str, object]], text: str
    ) -> SemanticCheck:
        """Validate invoice number format and presence."""
        invoice_entities = [
            e for e in entities if e.get("type") == "INVOICE_NUMBER"
        ]

        if not invoice_entities:
            # Check if invoice number might exist in text
            invoice_patterns = [
                r"Rechnungs?-?Nr\.?\s*:?\s*(\S+)",
                r"Invoice\s*No\.?\s*:?\s*(\S+)",
                r"Re\.?-?Nr\.?\s*:?\s*(\S+)",
            ]

            for pattern in invoice_patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    return SemanticCheck(
                        check_name="invoice_number",
                        passed=False,
                        message="Rechnungsnummer im Text gefunden, aber nicht extrahiert",
                        severity=0.6,
                    )

            return SemanticCheck(
                check_name="invoice_number",
                passed=False,
                message="Keine Rechnungsnummer gefunden",
                severity=0.5,
            )

        # Validate format (should have numbers)
        invoice_num = invoice_entities[0].get("value", "")
        if not re.search(r"\d", invoice_num):
            return SemanticCheck(
                check_name="invoice_number",
                passed=False,
                message=f"Rechnungsnummer enthält keine Ziffern: {invoice_num}",
                severity=0.7,
            )

        return SemanticCheck(
            check_name="invoice_number",
            passed=True,
            message="Rechnungsnummer ist valide",
            severity=0.0,
        )

    def _validate_contract_dates(
        self, entities: List[Dict[str, object]]
    ) -> SemanticCheck:
        """Validate contract-specific date logic."""
        date_entities = [e for e in entities if e.get("type") == "DATE"]
        contract_fields = [e for e in entities if e.get("type") == "CONTRACT_FIELD"]

        # Look for contract start and end dates
        contract_start = None
        contract_end = None

        for field in contract_fields:
            field_name = field.get("field_name", "")
            parsed = field.get("parsed_date") or field.get("value")

            if field_name in ["start_date", "contract_date"]:
                contract_start = parsed
            elif field_name in ["end_date", "termination_date"]:
                contract_end = parsed

        if contract_start and contract_end:
            try:
                if isinstance(contract_start, str):
                    start_dt = datetime.fromisoformat(contract_start)
                else:
                    start_dt = contract_start

                if isinstance(contract_end, str):
                    end_dt = datetime.fromisoformat(contract_end)
                else:
                    end_dt = contract_end

                if end_dt < start_dt:
                    return SemanticCheck(
                        check_name="contract_dates",
                        passed=False,
                        message=f"Vertragsende liegt vor Vertragsbeginn",
                        severity=0.8,
                        details={
                            "start": str(contract_start),
                            "end": str(contract_end),
                        },
                    )

                # Check for suspiciously long contracts (> 100 years)
                if (end_dt - start_dt).days > 36500:
                    return SemanticCheck(
                        check_name="contract_dates",
                        passed=False,
                        message="Vertragslaufzeit erscheint unplausibel (> 100 Jahre)",
                        severity=0.7,
                        details={
                            "duration_years": (end_dt - start_dt).days / 365,
                        },
                    )

            except (ValueError, TypeError) as e:
                logger.debug(
                    "contract_dates_parse_failed",
                    error_type=type(e).__name__,
                )

        return SemanticCheck(
            check_name="contract_dates",
            passed=True,
            message="Vertragsdaten sind plausibel",
            severity=0.0,
        )

    def _validate_content_matches_type(
        self, text: str, document_type: str
    ) -> SemanticCheck:
        """Validate that text content matches the classified document type."""
        text_lower = text.lower()

        # Keywords expected for each document type
        type_keywords = {
            "invoice": [
                "rechnung", "invoice", "rechnungsnummer", "betrag", "netto",
                "brutto", "mwst", "zahlbar", "fällig", "konto",
            ],
            "contract": [
                "vertrag", "vereinbarung", "parteien", "§", "paragraph",
                "gültigkeit", "laufzeit", "kündigung", "unterschrift",
            ],
            "receipt": [
                "quittung", "kassenbon", "bar", "bezahlt", "erhalt",
                "empfangen", "summe", "gesamt",
            ],
            "letter": [
                "sehr geehrte", "mit freundlichen grüßen", "betreff",
                "datum", "anschrift", "absender",
            ],
            "form": [
                "formular", "antrag", "eingabe", "feld", "ausfüllen",
                "ankreuzen", "unterschrift",
            ],
        }

        keywords = type_keywords.get(document_type, [])
        if not keywords:
            return SemanticCheck(
                check_name="content_type_match",
                passed=True,
                message="Dokumenttyp ohne spezifische Schlüsselwörter",
                severity=0.0,
            )

        # Count keyword matches
        matches = sum(1 for kw in keywords if kw in text_lower)
        match_ratio = matches / len(keywords) if keywords else 0

        if match_ratio < 0.2:
            return SemanticCheck(
                check_name="content_type_match",
                passed=False,
                message=f"Textinhalt passt nicht zum Dokumenttyp '{document_type}' ({match_ratio:.0%} Übereinstimmung)",
                severity=0.6,
                details={
                    "expected_keywords": keywords[:5],
                    "match_ratio": match_ratio,
                },
            )

        return SemanticCheck(
            check_name="content_type_match",
            passed=True,
            message=f"Textinhalt passt zum Dokumenttyp ({match_ratio:.0%} Übereinstimmung)",
            severity=0.0,
        )

    def _check_cross_entity_consistency(
        self,
        entities: List[Dict[str, object]],
        classification: Dict[str, object],
    ) -> Dict[str, object]:
        """
        Check consistency between related entities.

        Validates:
        - IBAN matches address country
        - VAT ID format matches company country
        - Multiple mentions of same entity are consistent
        - Person names are consistently formatted

        Args:
            entities: Extracted entities
            classification: Document classification

        Returns:
            Dictionary with score, issues, and suggestions
        """
        issues: List[Dict[str, object]] = []
        suggestions: List[Dict[str, object]] = []
        score = 1.0

        # Check 1: IBAN country matches address
        iban_check = self._check_iban_address_consistency(entities)
        if iban_check:
            issues.append(iban_check)
            score -= 0.1

        # Check 2: VAT ID format matches expectations
        vat_check = self._check_vat_consistency(entities)
        if vat_check:
            issues.append(vat_check)
            score -= 0.1

        # Check 3: Duplicate entity consistency
        duplicate_issues = self._check_duplicate_entity_consistency(entities)
        issues.extend(duplicate_issues)
        score -= len(duplicate_issues) * 0.05

        if duplicate_issues:
            suggestions.append({
                "type": "entity_normalization",
                "message": "Entitäten normalisieren für konsistente Darstellung",
                "affected_count": len(duplicate_issues),
            })

        # Check 4: Person name formatting consistency
        name_issues = self._check_name_consistency(entities)
        issues.extend(name_issues)
        score -= len(name_issues) * 0.03

        # Check 5: Date format consistency
        date_format_issues = self._check_date_format_consistency(entities)
        if date_format_issues:
            issues.append(date_format_issues)
            score -= 0.05
            suggestions.append({
                "type": "date_normalization",
                "message": "Datumsformate vereinheitlichen",
            })

        return {
            "score": max(0, score),
            "issues": issues,
            "suggestions": suggestions,
            "checks_performed": [
                "iban_address",
                "vat_format",
                "duplicate_consistency",
                "name_formatting",
                "date_format",
            ],
        }

    def _check_iban_address_consistency(
        self, entities: List[Dict[str, object]]
    ) -> Optional[Dict[str, object]]:
        """Check if IBAN country code matches address country."""
        ibans = [e for e in entities if e.get("type") == "IBAN"]
        addresses = [e for e in entities if e.get("type") == "ADDRESS"]

        if not ibans or not addresses:
            return None

        # Extract IBAN country codes
        iban_countries = []
        for iban in ibans:
            value = iban.get("value", "")
            if len(value) >= 2:
                iban_countries.append(value[:2].upper())

        # Extract address countries
        address_countries = []
        for addr in addresses:
            country = addr.get("country", "").upper()
            if country:
                # Map country names to ISO codes
                country_map = {
                    "DEUTSCHLAND": "DE",
                    "GERMANY": "DE",
                    "ÖSTERREICH": "AT",
                    "AUSTRIA": "AT",
                    "SCHWEIZ": "CH",
                    "SWITZERLAND": "CH",
                }
                address_countries.append(country_map.get(country, country[:2]))

        # Check for mismatches
        if iban_countries and address_countries:
            if iban_countries[0] not in address_countries:
                return {
                    "type": QAIssueType.CROSS_ENTITY_CONFLICT,
                    "message": f"IBAN-Land ({iban_countries[0]}) stimmt nicht mit Adressland überein",
                    "severity": 0.6,
                    "details": {
                        "iban_country": iban_countries[0],
                        "address_countries": address_countries,
                    },
                }

        return None

    def _check_vat_consistency(
        self, entities: List[Dict[str, object]]
    ) -> Optional[Dict[str, object]]:
        """Check VAT ID format consistency."""
        vat_ids = [e for e in entities if e.get("type") == "VAT_ID"]

        if not vat_ids:
            return None

        # VAT ID format patterns by country
        vat_formats = {
            "DE": r"^DE\d{9}$",
            "AT": r"^ATU\d{8}$",
            "CH": r"^CHE-?\d{3}\.?\d{3}\.?\d{3}$",
        }

        for vat in vat_ids:
            value = vat.get("value", "").replace(" ", "")
            country = value[:2].upper() if len(value) >= 2 else ""

            if country in vat_formats:
                if not re.match(vat_formats[country], value, re.IGNORECASE):
                    return {
                        "type": QAIssueType.CROSS_ENTITY_CONFLICT,
                        "message": f"USt-IdNr. Format entspricht nicht dem Standard für {country}",
                        "severity": 0.7,
                        "details": {
                            "value": value,
                            "expected_format": vat_formats[country],
                        },
                    }

        return None

    def _check_duplicate_entity_consistency(
        self, entities: List[Dict[str, object]]
    ) -> List[Dict[str, object]]:
        """Check that duplicate entities have consistent values."""
        issues = []

        # Group entities by type
        by_type: Dict[str, List[Dict[str, object]]] = {}
        for entity in entities:
            entity_type = entity.get("type", "")
            if entity_type not in by_type:
                by_type[entity_type] = []
            by_type[entity_type].append(entity)

        # Check for inconsistent duplicates
        for entity_type, entity_list in by_type.items():
            if len(entity_list) > 1 and entity_type in ["PERSON", "ORGANIZATION"]:
                values = [e.get("value", "") for e in entity_list]
                normalized = [v.lower().strip() for v in values]

                # Find similar but not identical values
                for i, val1 in enumerate(normalized):
                    for j, val2 in enumerate(normalized[i + 1:], i + 1):
                        if val1 != val2:
                            # Check similarity
                            from difflib import SequenceMatcher
                            ratio = SequenceMatcher(None, val1, val2).ratio()
                            if 0.7 < ratio < 1.0:
                                issues.append({
                                    "type": QAIssueType.CROSS_ENTITY_CONFLICT,
                                    "message": f"Ähnliche aber unterschiedliche {entity_type}: '{values[i]}' vs '{values[j]}'",
                                    "severity": 0.5,
                                    "details": {
                                        "value1": values[i],
                                        "value2": values[j],
                                        "similarity": ratio,
                                    },
                                })

        return issues

    def _check_name_consistency(
        self, entities: List[Dict[str, object]]
    ) -> List[Dict[str, object]]:
        """Check person name formatting consistency."""
        issues = []
        persons = [e for e in entities if e.get("type") == "PERSON"]

        if len(persons) < 2:
            return issues

        # Check formatting patterns
        formats_found = set()
        for person in persons:
            value = person.get("value", "")
            if "," in value:
                formats_found.add("last_first")
            elif re.match(r"^[A-ZÄÖÜ][a-zäöüß]+\s+[A-ZÄÖÜ]", value):
                formats_found.add("first_last")
            elif re.match(r"^[A-ZÄÖÜ]\.\s*[A-ZÄÖÜ]", value):
                formats_found.add("initials")

        if len(formats_found) > 1:
            issues.append({
                "type": QAIssueType.CROSS_ENTITY_CONFLICT,
                "message": f"Inkonsistente Namensformate: {', '.join(formats_found)}",
                "severity": 0.3,
                "details": {"formats": list(formats_found)},
            })

        return issues

    def _check_date_format_consistency(
        self, entities: List[Dict[str, object]]
    ) -> Optional[Dict[str, object]]:
        """Check that all dates use consistent formatting."""
        dates = [e for e in entities if e.get("type") == "DATE"]

        if len(dates) < 2:
            return None

        formats_found = set()
        for date in dates:
            value = date.get("value", "")
            if re.match(r"^\d{2}\.\d{2}\.\d{4}$", value):
                formats_found.add("DD.MM.YYYY")
            elif re.match(r"^\d{2}\.\d{2}\.\d{2}$", value):
                formats_found.add("DD.MM.YY")
            elif re.match(r"^\d{1,2}\.\s*\w+\s*\d{4}$", value):
                formats_found.add("D. Month YYYY")
            elif re.match(r"^\d{4}-\d{2}-\d{2}$", value):
                formats_found.add("YYYY-MM-DD")

        if len(formats_found) > 1:
            return {
                "type": QAIssueType.CROSS_ENTITY_CONFLICT,
                "message": f"Inkonsistente Datumsformate: {', '.join(formats_found)}",
                "severity": 0.4,
                "details": {"formats": list(formats_found)},
            }

        return None

    def _check_document_completeness(
        self,
        text: str,
        entities: List[Dict[str, object]],
        classification: Dict[str, object],
    ) -> Dict[str, object]:
        """
        Check document completeness based on type requirements.

        Validates:
        - Required entities are present
        - Recommended entities are present
        - Minimum text length is met
        - Key document sections exist

        Args:
            text: OCR extracted text
            entities: Extracted entities
            classification: Document classification

        Returns:
            Dictionary with score, issues, and suggestions
        """
        issues: List[Dict[str, object]] = []
        suggestions: List[Dict[str, object]] = []
        score = 1.0

        document_type = classification.get("document_type", "other")
        requirements = self.COMPLETENESS_REQUIREMENTS.get(document_type, {})

        if not requirements:
            return {
                "score": 1.0,
                "issues": [],
                "suggestions": [],
                "completeness_details": {
                    "document_type": document_type,
                    "no_requirements": True,
                },
            }

        entity_types = set(e.get("type") for e in entities)

        # Check required entities
        required = requirements.get("required", [])
        missing_required = [r for r in required if r not in entity_types]

        if missing_required:
            issues.append({
                "type": QAIssueType.DOCUMENT_INCOMPLETE,
                "message": f"Erforderliche Entitäten fehlen: {', '.join(missing_required)}",
                "severity": 0.8,
                "details": {"missing": missing_required},
            })
            score -= len(missing_required) * 0.15
            suggestions.append({
                "type": "entity_extraction",
                "message": "Manuelle Extraktion der fehlenden Entitäten",
                "missing_entities": missing_required,
            })

        # Check recommended entities
        recommended = requirements.get("recommended", [])
        missing_recommended = [r for r in recommended if r not in entity_types]

        if missing_recommended:
            issues.append({
                "type": QAIssueType.DOCUMENT_INCOMPLETE,
                "message": f"Empfohlene Entitäten fehlen: {', '.join(missing_recommended)}",
                "severity": 0.4,
                "details": {"missing": missing_recommended},
            })
            score -= len(missing_recommended) * 0.05

        # Check minimum text length
        min_length = requirements.get("min_text_length", 0)
        if len(text) < min_length:
            issues.append({
                "type": QAIssueType.DOCUMENT_INCOMPLETE,
                "message": f"Text zu kurz: {len(text)} Zeichen (Minimum: {min_length})",
                "severity": 0.6,
            })
            score -= 0.2
            suggestions.append({
                "type": "ocr_retry",
                "message": "OCR-Verarbeitung mit anderen Einstellungen wiederholen",
            })

        # Check for key sections based on document type
        section_check = self._check_document_sections(text, document_type)
        if section_check["missing_sections"]:
            issues.append({
                "type": QAIssueType.DOCUMENT_INCOMPLETE,
                "message": f"Fehlende Dokumentabschnitte: {', '.join(section_check['missing_sections'])}",
                "severity": 0.5,
                "details": section_check,
            })
            score -= 0.1

        # Calculate completeness percentage
        required_found = len(required) - len(missing_required)
        required_total = len(required) if required else 1
        completeness_pct = required_found / required_total

        return {
            "score": max(0, score),
            "issues": issues,
            "suggestions": suggestions,
            "completeness_details": {
                "document_type": document_type,
                "required_found": required_found,
                "required_total": len(required),
                "recommended_found": len(recommended) - len(missing_recommended),
                "recommended_total": len(recommended),
                "completeness_percentage": completeness_pct,
                "text_length": len(text),
                "min_text_length": min_length,
            },
        }

    def _check_document_sections(
        self, text: str, document_type: str
    ) -> Dict[str, object]:
        """Check for expected document sections."""
        text_lower = text.lower()

        # Expected sections by document type
        expected_sections = {
            "invoice": {
                "header": ["rechnung", "invoice", "re-nr", "rechnungsnummer"],
                "sender": ["absender", "von", "firma"],
                "recipient": ["empfänger", "an", "kunde"],
                "items": ["position", "beschreibung", "menge", "preis"],
                "total": ["gesamt", "summe", "total", "zu zahlen"],
                "payment": ["zahlung", "bank", "iban", "überweisung"],
            },
            "contract": {
                "header": ["vertrag", "vereinbarung", "agreement"],
                "parties": ["parteien", "zwischen", "vertragspartner"],
                "terms": ["§", "bestimmungen", "bedingungen"],
                "signature": ["unterschrift", "datum", "ort"],
            },
            "letter": {
                "header": ["datum", "betreff", "subject"],
                "salutation": ["sehr geehrte", "liebe", "dear"],
                "closing": ["mit freundlichen grüßen", "hochachtungsvoll"],
            },
        }

        sections = expected_sections.get(document_type, {})
        if not sections:
            return {"missing_sections": [], "found_sections": []}

        found_sections = []
        missing_sections = []

        for section_name, keywords in sections.items():
            if any(kw in text_lower for kw in keywords):
                found_sections.append(section_name)
            else:
                missing_sections.append(section_name)

        return {
            "found_sections": found_sections,
            "missing_sections": missing_sections,
            "section_count": len(found_sections),
            "expected_count": len(sections),
        }

    def _generate_quality_summary(
        self,
        metrics: QualityMetrics,
        quality_level: str,
        issues: List[Dict[str, object]],
        suggestions: List[Dict[str, object]],
    ) -> Dict[str, object]:
        """
        Generate a human-readable quality summary in German.

        Args:
            metrics: Quality metrics dataclass
            quality_level: Quality level category
            issues: List of identified issues
            suggestions: List of suggestions

        Returns:
            Dictionary with summary text and key findings
        """
        german_level = self._get_german_quality_level(quality_level)

        # Build summary text
        summary_parts = []

        # Overall assessment
        summary_parts.append(
            f"Qualitätsbewertung: {german_level} ({metrics.overall_score:.0%})"
        )

        # Key metrics
        if metrics.text_quality_score < 0.8:
            summary_parts.append(
                f"Textqualität eingeschränkt ({metrics.text_quality_score:.0%})"
            )

        if metrics.german_quality_score < 0.8:
            summary_parts.append(
                f"Deutsche Sprachqualität: {metrics.german_quality_score:.0%}"
            )

        if metrics.completeness_score < 0.8:
            summary_parts.append(
                f"Dokumentvollständigkeit: {metrics.completeness_score:.0%}"
            )

        # Issue summary
        if metrics.critical_issue_count > 0:
            summary_parts.append(
                f"{metrics.critical_issue_count} kritische Probleme gefunden"
            )

        if metrics.issue_count > metrics.critical_issue_count:
            other_issues = metrics.issue_count - metrics.critical_issue_count
            summary_parts.append(f"{other_issues} weitere Hinweise")

        # Suggestions summary
        if metrics.suggestion_count > 0:
            summary_parts.append(
                f"{metrics.suggestion_count} Verbesserungsvorschläge"
            )

        # Build key findings
        key_findings = []

        # Group issues by type
        issue_types = {}
        for issue in issues:
            issue_type = issue.get("type", "unknown")
            if issue_type not in issue_types:
                issue_types[issue_type] = 0
            issue_types[issue_type] += 1

        for issue_type, count in sorted(
            issue_types.items(), key=lambda x: -x[1]
        )[:3]:
            key_findings.append({
                "type": issue_type,
                "count": count,
                "description": self._get_issue_type_description(issue_type),
            })

        # Build action items
        action_items = []
        if quality_level in [QualityLevel.POOR, QualityLevel.UNACCEPTABLE]:
            action_items.append("Dokument erneut scannen oder manuell überprüfen")

        if metrics.critical_issue_count > 0:
            action_items.append("Kritische Probleme vor Freigabe beheben")

        for suggestion in suggestions[:2]:
            action_items.append(suggestion.get("message", ""))

        return {
            "summary_text": ". ".join(summary_parts) + ".",
            "quality_level": german_level,
            "quality_score_percent": f"{metrics.overall_score:.0%}",
            "key_findings": key_findings,
            "action_items": action_items[:3],
            "metrics_overview": {
                "text": f"{metrics.text_quality_score:.0%}",
                "german": f"{metrics.german_quality_score:.0%}",
                "entities": f"{metrics.entity_quality_score:.0%}",
                "completeness": f"{metrics.completeness_score:.0%}",
                "ocr_confidence": f"{metrics.ocr_confidence:.0%}",
            },
            "needs_attention": metrics.critical_issue_count > 0
            or quality_level in [QualityLevel.POOR, QualityLevel.UNACCEPTABLE],
        }

    def _get_issue_type_description(self, issue_type: str) -> str:
        """Get German description for issue type."""
        descriptions = {
            QAIssueType.UMLAUT_ERROR: "Umlaut-Fehler",
            QAIssueType.DATE_FORMAT: "Datumsformat-Problem",
            QAIssueType.CURRENCY_FORMAT: "Währungsformat-Problem",
            QAIssueType.IBAN_INVALID: "Ungültige IBAN",
            QAIssueType.VAT_ID_INVALID: "Ungültige USt-IdNr.",
            QAIssueType.LOW_CONFIDENCE: "Niedrige Konfidenz",
            QAIssueType.TEXT_QUALITY: "Textqualitätsproblem",
            QAIssueType.ENTITY_MISSING: "Fehlende Entität",
            QAIssueType.ENTITY_IMPLAUSIBLE: "Unplausible Entität",
            QAIssueType.ENCODING_ERROR: "Encoding-Fehler",
            QAIssueType.SEMANTIC_INCONSISTENCY: "Semantische Inkonsistenz",
            QAIssueType.DATE_SEQUENCE_ERROR: "Datumsreihenfolge-Fehler",
            QAIssueType.AMOUNT_MISMATCH: "Betragsabweichung",
            QAIssueType.DOCUMENT_INCOMPLETE: "Unvollständiges Dokument",
            QAIssueType.CROSS_ENTITY_CONFLICT: "Entitätskonflikt",
        }
        return descriptions.get(issue_type, issue_type)
