"""
Document Classifier Agent

Autonomous agent that analyzes uploaded documents and classifies them into
categories (invoice, contract, letter, etc.) using ML and pattern matching.

Classification accuracy target: > 90%
Processing time target: < 500ms per document
"""

import asyncio
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

import structlog
from PIL import Image
import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer

from app.db.models import Document
from app.services.ocr import quick_ocr_preview
from app.utils.german_text import normalize_german_text


logger = structlog.get_logger(__name__)


class DocumentClassifierAgent:
    """
    Autonomous agent for document classification.

    Supports classification into categories:
    - Rechnung (Invoice)
    - Vertrag (Contract)
    - Brief (Letter)
    - Kontoauszug (Bank Statement)
    - Lieferschein (Delivery Note)
    - Angebot (Quote)
    - Sonstiges (Other)

    Uses multi-modal classification:
    1. Text pattern matching (keywords, structure)
    2. Visual layout analysis (logos, tables, signatures)
    3. ML-based classification (transformer model)
    """

    CATEGORIES = [
        "rechnung",
        "vertrag",
        "brief",
        "kontoauszug",
        "lieferschein",
        "angebot",
        "sonstiges"
    ]

    # German keywords for pattern matching
    KEYWORDS = {
        "rechnung": [
            r"rechnung\b",
            r"invoice\b",
            r"faktura\b",
            r"rechnungsnummer",
            r"ust-idnr",
            r"steuernummer",
            r"fälligkeitsdatum",
            r"zahlungsziel",
            r"betrag.*€",
            r"netto.*€",
            r"brutto.*€",
            r"mehrwertsteuer",
            r"umsatzsteuer",
        ],
        "vertrag": [
            r"vertrag\b",
            r"contract\b",
            r"vereinbarung",
            r"§\s*\d+",  # Paragraph references
            r"vertragspartner",
            r"vertragsgegenstand",
            r"laufzeit",
            r"kündigung",
            r"unterschrift",
        ],
        "brief": [
            r"sehr\s+geehrte",
            r"dear\b",
            r"mit\s+freundlichen\s+grüßen",
            r"best\s+regards",
            r"hochachtungsvoll",
            r"betreff:",
        ],
        "kontoauszug": [
            r"kontoauszug",
            r"bank\s+statement",
            r"iban",
            r"bic",
            r"saldo",
            r"buchung",
            r"betrag.*€",
            r"valuta",
        ],
        "lieferschein": [
            r"lieferschein",
            r"delivery\s+note",
            r"lieferung",
            r"lieferadresse",
            r"paketanzahl",
            r"versandart",
        ],
        "angebot": [
            r"angebot\b",
            r"quote\b",
            r"kostenvoranschlag",
            r"gültig\s+bis",
            r"angebotsnummer",
            r"preisangabe",
        ],
    }

    def __init__(self):
        self.model = None
        self.tokenizer = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        logger.info(
            "document_classifier_initialized",
            device=self.device,
            categories=self.CATEGORIES
        )

    async def classify(
        self,
        document_path: str,
        use_ml: bool = True,
        confidence_threshold: float = 0.7
    ) -> Dict[str, Any]:
        """
        Classify a document into one of the predefined categories.

        Args:
            document_path: Path to the document file
            use_ml: Whether to use ML model (slower but more accurate)
            confidence_threshold: Minimum confidence for classification

        Returns:
            Dictionary with classification results:
            {
                "category": "rechnung",
                "confidence": 0.95,
                "method": "pattern_matching",
                "alternative_categories": [{"category": "angebot", "confidence": 0.32}],
                "processing_time_ms": 234
            }
        """
        start_time = datetime.utcnow()

        try:
            # Extract text preview (first page only for speed)
            text_preview = await self._extract_text_preview(document_path)

            # Normalize German text
            text_preview = normalize_german_text(text_preview)

            # Pattern-based classification (fast)
            pattern_result = self._classify_by_patterns(text_preview)

            logger.info(
                "pattern_classification",
                document=document_path,
                category=pattern_result["category"],
                confidence=pattern_result["confidence"]
            )

            # If pattern matching is confident enough, return
            if pattern_result["confidence"] >= confidence_threshold:
                processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
                return {
                    **pattern_result,
                    "method": "pattern_matching",
                    "processing_time_ms": processing_time
                }

            # Use ML model for uncertain cases
            if use_ml:
                ml_result = await self._classify_by_ml(text_preview, document_path)

                logger.info(
                    "ml_classification",
                    document=document_path,
                    category=ml_result["category"],
                    confidence=ml_result["confidence"]
                )

                # Combine pattern and ML results
                final_result = self._combine_classifications(
                    pattern_result,
                    ml_result,
                    weights={"pattern": 0.3, "ml": 0.7}
                )

                processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
                return {
                    **final_result,
                    "method": "ml_combined",
                    "processing_time_ms": processing_time
                }

            # Fallback to pattern result
            processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            return {
                **pattern_result,
                "method": "pattern_matching_fallback",
                "processing_time_ms": processing_time
            }

        except Exception as e:
            logger.exception(
                "classification_failed",
                document=document_path,
                error=str(e)
            )

            # Return "sonstiges" (other) on error
            return {
                "category": "sonstiges",
                "confidence": 0.1,
                "method": "error_fallback",
                "error": str(e),
                "processing_time_ms": (datetime.utcnow() - start_time).total_seconds() * 1000
            }

    async def _extract_text_preview(self, document_path: str) -> str:
        """Extract text from first page for classification."""
        # Quick OCR for preview (not full processing)
        text = await quick_ocr_preview(document_path, max_pages=1)
        return text

    def _classify_by_patterns(self, text: str) -> Dict[str, Any]:
        """
        Classify document based on keyword pattern matching.

        Returns:
            {
                "category": "rechnung",
                "confidence": 0.85,
                "matched_patterns": ["rechnung", "rechnungsnummer", "ust-idnr"]
            }
        """
        text_lower = text.lower()

        # Score each category
        scores = {}
        matched_patterns = {}

        for category, patterns in self.KEYWORDS.items():
            matches = []
            score = 0.0

            for pattern in patterns:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    matches.append(pattern)
                    # Weight by pattern specificity (longer = more specific)
                    score += len(pattern) / 10.0

            if matches:
                scores[category] = score
                matched_patterns[category] = matches

        if not scores:
            # No matches - default to "sonstiges"
            return {
                "category": "sonstiges",
                "confidence": 0.1,
                "matched_patterns": []
            }

        # Get top category
        top_category = max(scores, key=scores.get)
        max_score = scores[top_category]

        # Normalize score to confidence (0-1)
        total_score = sum(scores.values())
        confidence = max_score / total_score if total_score > 0 else 0.1

        # Get alternative categories
        alternatives = [
            {"category": cat, "confidence": score / total_score}
            for cat, score in sorted(scores.items(), key=lambda x: x[1], reverse=True)
            if cat != top_category
        ][:3]  # Top 3 alternatives

        return {
            "category": top_category,
            "confidence": min(confidence, 0.95),  # Cap at 0.95 for pattern matching
            "matched_patterns": matched_patterns.get(top_category, []),
            "alternative_categories": alternatives
        }

    async def _classify_by_ml(
        self,
        text: str,
        document_path: str
    ) -> Dict[str, Any]:
        """
        Classify document using transformer-based ML model.

        Uses a fine-tuned German document classification model.
        """
        # Load model lazily
        if self.model is None:
            await self._load_model()

        # Tokenize text
        inputs = self.tokenizer(
            text,
            max_length=512,
            truncation=True,
            padding=True,
            return_tensors="pt"
        ).to(self.device)

        # Inference
        with torch.no_grad():
            outputs = self.model(**inputs)
            logits = outputs.logits
            probabilities = torch.softmax(logits, dim=-1)

        # Get predictions
        probs = probabilities[0].cpu().numpy()
        predicted_idx = np.argmax(probs)
        confidence = float(probs[predicted_idx])
        category = self.CATEGORIES[predicted_idx]

        # Get alternative predictions
        alternatives = [
            {
                "category": self.CATEGORIES[i],
                "confidence": float(probs[i])
            }
            for i in np.argsort(probs)[::-1][1:4]  # Top 3 alternatives
        ]

        return {
            "category": category,
            "confidence": confidence,
            "alternative_categories": alternatives
        }

    async def _load_model(self):
        """Load ML classification model."""
        try:
            # Load fine-tuned German document classification model
            model_name = "bert-base-german-cased"  # Replace with actual fine-tuned model

            logger.info("loading_classification_model", model=model_name)

            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModel.from_pretrained(model_name)
            self.model.to(self.device)
            self.model.eval()

            logger.info("classification_model_loaded", device=self.device)

        except Exception as e:
            logger.error("model_loading_failed", error=str(e))
            raise

    def _combine_classifications(
        self,
        pattern_result: Dict,
        ml_result: Dict,
        weights: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Combine pattern and ML classification results using weighted voting.

        Args:
            pattern_result: Result from pattern matching
            ml_result: Result from ML model
            weights: Weights for each method (must sum to 1.0)

        Returns:
            Combined classification result
        """
        # Collect all unique categories
        all_categories = set([pattern_result["category"], ml_result["category"]])

        # Add alternatives
        for alt in pattern_result.get("alternative_categories", []):
            all_categories.add(alt["category"])
        for alt in ml_result.get("alternative_categories", []):
            all_categories.add(alt["category"])

        # Compute weighted scores
        scores = {}
        for category in all_categories:
            pattern_score = (
                pattern_result["confidence"]
                if pattern_result["category"] == category
                else next(
                    (alt["confidence"] for alt in pattern_result.get("alternative_categories", [])
                     if alt["category"] == category),
                    0.0
                )
            )

            ml_score = (
                ml_result["confidence"]
                if ml_result["category"] == category
                else next(
                    (alt["confidence"] for alt in ml_result.get("alternative_categories", [])
                     if alt["category"] == category),
                    0.0
                )
            )

            # Weighted combination
            scores[category] = (
                weights["pattern"] * pattern_score +
                weights["ml"] * ml_score
            )

        # Get top category
        top_category = max(scores, key=scores.get)
        confidence = scores[top_category]

        # Get alternatives
        alternatives = [
            {"category": cat, "confidence": score}
            for cat, score in sorted(scores.items(), key=lambda x: x[1], reverse=True)
            if cat != top_category
        ][:3]

        return {
            "category": top_category,
            "confidence": confidence,
            "alternative_categories": alternatives,
            "pattern_confidence": pattern_result["confidence"],
            "ml_confidence": ml_result["confidence"]
        }

    async def classify_batch(
        self,
        document_paths: List[str],
        max_concurrent: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Classify multiple documents concurrently.

        Args:
            document_paths: List of document file paths
            max_concurrent: Maximum concurrent classifications

        Returns:
            List of classification results
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def classify_with_semaphore(path: str):
            async with semaphore:
                return await self.classify(path)

        results = await asyncio.gather(
            *[classify_with_semaphore(path) for path in document_paths],
            return_exceptions=True
        )

        # Filter out exceptions
        successful_results = [
            r if not isinstance(r, Exception) else {
                "category": "sonstiges",
                "confidence": 0.0,
                "error": str(r)
            }
            for r in results
        ]

        logger.info(
            "batch_classification_complete",
            total=len(document_paths),
            successful=len([r for r in successful_results if "error" not in r])
        )

        return successful_results


# ============================================================================
# CLI for Testing
# ============================================================================

async def main():
    """CLI for testing document classification."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python document_classifier_agent.py <document_path>")
        sys.exit(1)

    document_path = sys.argv[1]

    # Initialize agent
    agent = DocumentClassifierAgent()

    # Classify
    result = await agent.classify(document_path, use_ml=True)

    # Print results
    print(f"\n=== Classification Result ===")
    print(f"Category: {result['category']}")
    print(f"Confidence: {result['confidence']:.2%}")
    print(f"Method: {result['method']}")
    print(f"Processing Time: {result['processing_time_ms']:.2f}ms")

    if result.get("alternative_categories"):
        print(f"\nAlternatives:")
        for alt in result["alternative_categories"]:
            print(f"  - {alt['category']}: {alt['confidence']:.2%}")


if __name__ == "__main__":
    asyncio.run(main())
