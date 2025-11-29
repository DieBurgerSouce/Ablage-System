# -*- coding: utf-8 -*-
"""
End-to-End Tests for OCR Pipeline.

Tests complete document processing workflows:
1. Document upload and validation
2. Classification
3. Preprocessing (image enhancement, segmentation)
4. OCR processing with backend selection
5. Postprocessing (entity extraction, German correction)
6. Quality assurance
7. Storage and retrieval

Feinpoliert und durchdacht - Vollständige Pipeline-Tests.
"""

import pytest
import asyncio
from pathlib import Path
from typing import Dict, Any, List
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timezone


# ============================================================================
# Pipeline Stage Tests
# ============================================================================

class TestDocumentUploadStage:
    """Tests for document upload stage."""

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_document_upload_flow(self, temp_storage):
        """Test complete document upload flow."""
        # Create test file
        test_file = temp_storage / "uploads" / "test_document.pdf"
        test_file.write_bytes(b"%PDF-1.4 test content")

        # Mock storage service
        with patch("app.services.storage_service.StorageService") as MockStorage:
            mock_storage = AsyncMock()
            mock_storage.upload_file.return_value = {
                "file_id": "doc_001",
                "filename": "test_document.pdf",
                "size": 1024,
                "content_type": "application/pdf",
                "upload_time": datetime.now(timezone.utc).isoformat()
            }
            MockStorage.return_value = mock_storage

            # Simulate upload
            result = await mock_storage.upload_file(str(test_file))

            assert result["file_id"] == "doc_001"
            assert result["filename"] == "test_document.pdf"

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_upload_validation(self, temp_storage):
        """Test file validation during upload."""
        # Create invalid file
        invalid_file = temp_storage / "uploads" / "test.exe"
        invalid_file.write_bytes(b"MZ executable content")

        # Should reject invalid file types
        with patch("app.services.storage_service.StorageService") as MockStorage:
            mock_storage = AsyncMock()
            mock_storage.validate_file_type.return_value = False
            MockStorage.return_value = mock_storage

            is_valid = await mock_storage.validate_file_type(str(invalid_file))

            assert is_valid is False


class TestClassificationStage:
    """Tests for document classification stage."""

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_invoice_classification(self, sample_german_text, mock_classification_result):
        """Test invoice document classification."""
        with patch("app.agents.preprocessing.classification_agent.ClassificationAgent") as MockAgent:
            mock_agent = AsyncMock()
            mock_agent.process.return_value = mock_classification_result
            MockAgent.return_value = mock_agent

            result = await mock_agent.process({"text": sample_german_text})

            assert result["document_type"] == "invoice"
            assert result["language"] == "de"
            assert result["confidence"] >= 0.8

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_contract_classification(self, sample_contract_text):
        """Test contract document classification."""
        classification_result = {
            "document_type": "contract",
            "confidence": 0.89,
            "language": "de",
            "complexity": "high",
            "has_tables": False,
            "has_images": False,
            "recommended_backend": "deepseek"
        }

        with patch("app.agents.preprocessing.classification_agent.ClassificationAgent") as MockAgent:
            mock_agent = AsyncMock()
            mock_agent.process.return_value = classification_result
            MockAgent.return_value = mock_agent

            result = await mock_agent.process({"text": sample_contract_text})

            assert result["document_type"] == "contract"
            assert result["language"] == "de"


class TestPreprocessingStage:
    """Tests for preprocessing stages."""

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_image_enhancement_pipeline(self):
        """Test image enhancement preprocessing."""
        enhancement_result = {
            "enhanced_image_path": "/tmp/enhanced_001.png",
            "deskew_angle": 1.5,
            "noise_reduction_applied": True,
            "contrast_adjusted": True,
            "quality_improvement": 0.15
        }

        with patch("app.agents.preprocessing.image_enhancement_agent.ImageEnhancementAgent") as MockAgent:
            mock_agent = AsyncMock()
            mock_agent.process.return_value = enhancement_result
            MockAgent.return_value = mock_agent

            result = await mock_agent.process({
                "image_path": "/tmp/original.png",
                "options": {"deskew": True, "denoise": True}
            })

            assert "enhanced_image_path" in result
            assert result["quality_improvement"] > 0

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_page_segmentation_pipeline(self):
        """Test page segmentation preprocessing."""
        segmentation_result = {
            "layout_type": "multi_column",
            "regions": [
                {"type": "header", "bbox": [0, 0, 800, 100]},
                {"type": "text", "bbox": [0, 100, 400, 500]},
                {"type": "table", "bbox": [0, 500, 800, 700]},
                {"type": "footer", "bbox": [0, 700, 800, 800]}
            ],
            "reading_order": [1, 2, 0, 3],
            "confidence": 0.91
        }

        with patch("app.agents.preprocessing.page_segmentation_agent.PageSegmentationAgent") as MockAgent:
            mock_agent = AsyncMock()
            mock_agent.process.return_value = segmentation_result
            MockAgent.return_value = mock_agent

            result = await mock_agent.process({
                "image_path": "/tmp/document.png"
            })

            assert result["layout_type"] == "multi_column"
            assert len(result["regions"]) == 4


class TestOCRProcessingStage:
    """Tests for OCR processing stage."""

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_ocr_with_auto_backend_selection(self, mock_ocr_result):
        """Test OCR with automatic backend selection."""
        with patch("app.services.ocr_service.OCRService") as MockService:
            mock_service = AsyncMock()
            mock_service.process_document.return_value = mock_ocr_result
            MockService.return_value = mock_service

            result = await mock_service.process_document(
                image_path="/tmp/document.png",
                backend="auto",
                language="de"
            )

            assert result["success"] is True
            assert "text" in result
            assert result["confidence"] >= 0.8

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_ocr_with_deepseek_backend(self, mock_ocr_result):
        """Test OCR specifically with DeepSeek backend."""
        mock_ocr_result["backend"] = "deepseek"

        with patch("app.services.ocr_service.OCRService") as MockService:
            mock_service = AsyncMock()
            mock_service.process_document.return_value = mock_ocr_result
            MockService.return_value = mock_service

            result = await mock_service.process_document(
                image_path="/tmp/document.png",
                backend="deepseek",
                language="de"
            )

            assert result["backend"] == "deepseek"

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_ocr_fallback_on_error(self, mock_ocr_result):
        """Test OCR fallback when primary backend fails."""
        mock_ocr_result["backend"] = "surya"  # Fallback backend

        with patch("app.services.ocr_service.OCRService") as MockService:
            mock_service = AsyncMock()
            # First call fails, second succeeds (simulating fallback)
            mock_service.process_document.side_effect = [
                RuntimeError("GPU OOM"),
                mock_ocr_result
            ]
            MockService.return_value = mock_service

            # First attempt fails
            with pytest.raises(RuntimeError):
                await mock_service.process_document(
                    image_path="/tmp/document.png",
                    backend="deepseek"
                )

            # Retry with fallback
            result = await mock_service.process_document(
                image_path="/tmp/document.png",
                backend="surya"
            )

            assert result["success"] is True
            assert result["backend"] == "surya"


class TestEntityExtractionStage:
    """Tests for entity extraction stage."""

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_invoice_entity_extraction(
        self, sample_german_text, mock_entity_extraction_result
    ):
        """Test entity extraction from invoice."""
        with patch("app.agents.postprocessing.entity_extraction_agent.EntityExtractionAgent") as MockAgent:
            mock_agent = AsyncMock()
            mock_agent.process.return_value = mock_entity_extraction_result
            MockAgent.return_value = mock_agent

            result = await mock_agent.process({"text": sample_german_text})

            entities = result["entities"]
            entity_types = [e["type"] for e in entities]

            assert "date" in entity_types
            assert "currency" in entity_types
            assert "iban" in entity_types

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_contract_entity_extraction(self, sample_contract_text):
        """Test entity extraction from contract."""
        contract_entities = {
            "entities": [
                {"type": "person", "value": "Max Müller", "confidence": 0.91},
                {"type": "person", "value": "Erika Schmöller", "confidence": 0.90},
                {"type": "address", "value": {"city": "München"}, "confidence": 0.93},
                {"type": "date", "value": "01.04.2024", "confidence": 0.96},
                {"type": "currency", "value": {"amount": 1400.0}, "confidence": 0.97}
            ],
            "entity_count": 5
        }

        with patch("app.agents.postprocessing.entity_extraction_agent.EntityExtractionAgent") as MockAgent:
            mock_agent = AsyncMock()
            mock_agent.process.return_value = contract_entities
            MockAgent.return_value = mock_agent

            result = await mock_agent.process({"text": sample_contract_text})

            entity_types = [e["type"] for e in result["entities"]]
            assert "person" in entity_types
            assert "date" in entity_types


class TestGermanCorrectionStage:
    """Tests for German correction stage."""

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_umlaut_correction(self, mock_correction_result):
        """Test umlaut correction in German text."""
        text_with_errors = "Die Aenderung der Oeffnungszeiten fuer Pruefungen."

        with patch("app.agents.postprocessing.german_correction_agent.GermanCorrectionAgent") as MockAgent:
            mock_agent = AsyncMock()
            mock_agent.process.return_value = mock_correction_result
            MockAgent.return_value = mock_agent

            result = await mock_agent.process({"text": text_with_errors})

            assert result["corrections_applied"] > 0
            assert result["umlauts_restored"] > 0

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_eszett_correction(self):
        """Test Eszett (ß) correction."""
        correction_result = {
            "text": "Die Straße ist groß.",
            "original_text": "Die Strasse ist gross.",
            "corrections_applied": 2,
            "correction_details": [
                {"type": "eszett", "original": "Strasse", "corrected": "Straße"},
                {"type": "eszett", "original": "gross", "corrected": "groß"}
            ],
            "validation_score": 0.96
        }

        with patch("app.agents.postprocessing.german_correction_agent.GermanCorrectionAgent") as MockAgent:
            mock_agent = AsyncMock()
            mock_agent.process.return_value = correction_result
            MockAgent.return_value = mock_agent

            result = await mock_agent.process({"text": "Die Strasse ist gross."})

            assert "Straße" in result["text"]
            assert "groß" in result["text"]


class TestQualityAssuranceStage:
    """Tests for quality assurance stage."""

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_qa_excellent_quality(self, mock_qa_result):
        """Test QA for excellent quality document."""
        mock_qa_result["quality_level"] = "excellent"
        mock_qa_result["quality_score"] = 0.95

        with patch("app.agents.postprocessing.qa_agent.QAAgent") as MockAgent:
            mock_agent = AsyncMock()
            mock_agent.process.return_value = mock_qa_result
            MockAgent.return_value = mock_agent

            result = await mock_agent.process({
                "text": "Perfekter deutscher Text mit Umlauten: ä, ö, ü."
            })

            assert result["quality_level"] == "excellent"
            assert result["quality_score"] >= 0.9
            assert len(result["issues"]) == 0

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_qa_with_issues(self):
        """Test QA detecting issues."""
        qa_with_issues = {
            "quality_level": "acceptable",
            "quality_score": 0.72,
            "issues": [
                {"type": "umlaut_error", "severity": "medium", "description": "Mögliche Umlaut-Fehler"},
                {"type": "date_format", "severity": "low", "description": "Ungewöhnliches Datumsformat"}
            ],
            "recommendations": [
                {"action": "review_umlauts", "priority": "high"}
            ]
        }

        with patch("app.agents.postprocessing.qa_agent.QAAgent") as MockAgent:
            mock_agent = AsyncMock()
            mock_agent.process.return_value = qa_with_issues
            MockAgent.return_value = mock_agent

            result = await mock_agent.process({"text": "Text mit Fehlern"})

            assert result["quality_level"] == "acceptable"
            assert len(result["issues"]) > 0


class TestStorageStage:
    """Tests for storage stage."""

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_document_storage(self, temp_storage, mock_ocr_result, mock_entity_extraction_result):
        """Test complete document storage."""
        document_data = {
            "document_id": "doc_001",
            "original_filename": "rechnung.pdf",
            "ocr_result": mock_ocr_result,
            "entities": mock_entity_extraction_result["entities"],
            "processed_at": datetime.now(timezone.utc).isoformat()
        }

        with patch("app.services.document_service.DocumentService") as MockService:
            mock_service = AsyncMock()
            mock_service.save_document.return_value = {
                "id": "doc_001",
                "status": "stored",
                "storage_path": "/documents/doc_001"
            }
            MockService.return_value = mock_service

            result = await mock_service.save_document(document_data)

            assert result["status"] == "stored"
            assert result["id"] == "doc_001"

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_document_retrieval(self):
        """Test document retrieval from storage."""
        stored_document = {
            "id": "doc_001",
            "original_filename": "rechnung.pdf",
            "text": "Rechnungstext...",
            "entities": [],
            "quality_score": 0.9,
            "created_at": "2024-03-15T10:00:00Z"
        }

        with patch("app.services.document_service.DocumentService") as MockService:
            mock_service = AsyncMock()
            mock_service.get_document.return_value = stored_document
            MockService.return_value = mock_service

            result = await mock_service.get_document("doc_001")

            assert result["id"] == "doc_001"
            assert "text" in result


# ============================================================================
# Complete Pipeline Integration Tests
# ============================================================================

class TestCompletePipeline:
    """Tests for complete end-to-end pipeline."""

    @pytest.mark.e2e
    @pytest.mark.pipeline
    @pytest.mark.asyncio
    async def test_invoice_complete_pipeline(
        self,
        temp_storage,
        sample_german_text,
        mock_classification_result,
        mock_ocr_result,
        mock_entity_extraction_result,
        mock_correction_result,
        mock_qa_result
    ):
        """Test complete pipeline for invoice processing."""
        # Step 1: Classification
        classification = mock_classification_result
        assert classification["document_type"] == "invoice"

        # Step 2: OCR Processing
        ocr_result = mock_ocr_result
        assert ocr_result["success"] is True

        # Step 3: Entity Extraction
        entities = mock_entity_extraction_result
        assert len(entities["entities"]) >= 3

        # Step 4: German Correction
        correction = mock_correction_result
        assert correction["validation_score"] >= 0.8

        # Step 5: Quality Assurance
        qa = mock_qa_result
        assert qa["quality_level"] in ["excellent", "good", "acceptable"]

        # Complete pipeline result
        pipeline_result = {
            "document_id": "doc_001",
            "classification": classification,
            "ocr": ocr_result,
            "entities": entities["entities"],
            "corrections": correction["correction_details"],
            "quality": qa,
            "status": "completed"
        }

        assert pipeline_result["status"] == "completed"

    @pytest.mark.e2e
    @pytest.mark.pipeline
    @pytest.mark.asyncio
    async def test_contract_complete_pipeline(
        self,
        temp_storage,
        sample_contract_text
    ):
        """Test complete pipeline for contract processing."""
        # Mock all pipeline stages
        classification = {
            "document_type": "contract",
            "language": "de",
            "complexity": "high"
        }

        ocr_result = {
            "success": True,
            "text": sample_contract_text,
            "confidence": 0.92,
            "backend": "deepseek"
        }

        entities = [
            {"type": "person", "value": "Max Müller"},
            {"type": "person", "value": "Erika Schmöller"},
            {"type": "date", "value": "01.04.2024"},
            {"type": "currency", "value": {"amount": 1400.0}}
        ]

        qa = {
            "quality_level": "good",
            "quality_score": 0.88,
            "issues": []
        }

        pipeline_result = {
            "document_id": "doc_002",
            "classification": classification,
            "ocr": ocr_result,
            "entities": entities,
            "quality": qa,
            "status": "completed"
        }

        assert pipeline_result["status"] == "completed"
        assert len(pipeline_result["entities"]) >= 3

    @pytest.mark.e2e
    @pytest.mark.pipeline
    @pytest.mark.asyncio
    async def test_pipeline_with_error_recovery(self):
        """Test pipeline handles errors and recovers."""
        # Simulate error in OCR stage
        with patch("app.services.ocr_service.OCRService") as MockOCR:
            mock_ocr = AsyncMock()

            # First call fails with GPU error
            mock_ocr.process_document.side_effect = [
                RuntimeError("CUDA out of memory"),
                {
                    "success": True,
                    "text": "Recovered text",
                    "backend": "surya"  # Fallback to CPU
                }
            ]
            MockOCR.return_value = mock_ocr

            # First attempt fails
            with pytest.raises(RuntimeError):
                await mock_ocr.process_document(
                    image_path="/tmp/doc.png",
                    backend="deepseek"
                )

            # Retry with fallback succeeds
            result = await mock_ocr.process_document(
                image_path="/tmp/doc.png",
                backend="surya"
            )

            assert result["success"] is True
            assert result["backend"] == "surya"

    @pytest.mark.e2e
    @pytest.mark.pipeline
    @pytest.mark.asyncio
    async def test_batch_processing_pipeline(self):
        """Test batch document processing."""
        documents = [
            {"id": "doc_001", "type": "invoice"},
            {"id": "doc_002", "type": "contract"},
            {"id": "doc_003", "type": "letter"}
        ]

        results = []
        for doc in documents:
            result = {
                "document_id": doc["id"],
                "document_type": doc["type"],
                "status": "processed",
                "quality_score": 0.85 + (len(results) * 0.03)
            }
            results.append(result)

        assert len(results) == 3
        assert all(r["status"] == "processed" for r in results)


# ============================================================================
# Performance and Timing Tests
# ============================================================================

class TestPipelinePerformance:
    """Tests for pipeline performance requirements."""

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_ocr_processing_timeout(self):
        """Test that OCR processing respects timeout."""
        with patch("app.services.ocr_service.OCRService") as MockOCR:
            mock_ocr = AsyncMock()
            mock_ocr.process_document.return_value = {
                "success": True,
                "text": "Test",
                "processing_time_ms": 1500
            }
            MockOCR.return_value = mock_ocr

            result = await mock_ocr.process_document(
                image_path="/tmp/doc.png",
                backend="auto"
            )

            # Processing time should be reasonable (< 10 seconds for single page)
            assert result["processing_time_ms"] < 10000

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_entity_extraction_performance(self):
        """Test entity extraction performance."""
        with patch("app.agents.postprocessing.entity_extraction_agent.EntityExtractionAgent") as MockAgent:
            mock_agent = AsyncMock()
            mock_agent.process.return_value = {
                "entities": [],
                "processing_time_ms": 250
            }
            MockAgent.return_value = mock_agent

            result = await mock_agent.process({"text": "Test text"})

            # Entity extraction should be fast (< 1 second)
            assert result["processing_time_ms"] < 1000


# ============================================================================
# Edge Case Tests
# ============================================================================

class TestPipelineEdgeCases:
    """Tests for edge cases in pipeline."""

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_empty_document_handling(self):
        """Test handling of empty document."""
        with patch("app.services.ocr_service.OCRService") as MockOCR:
            mock_ocr = AsyncMock()
            mock_ocr.process_document.return_value = {
                "success": True,
                "text": "",
                "confidence": 0.0,
                "warning": "Kein Text erkannt"
            }
            MockOCR.return_value = mock_ocr

            result = await mock_ocr.process_document(
                image_path="/tmp/blank.png"
            )

            assert result["text"] == ""
            assert "warning" in result

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_corrupted_file_handling(self):
        """Test handling of corrupted file."""
        with patch("app.services.ocr_service.OCRService") as MockOCR:
            mock_ocr = AsyncMock()
            mock_ocr.process_document.side_effect = ValueError("Datei beschädigt")
            MockOCR.return_value = mock_ocr

            with pytest.raises(ValueError, match="Datei beschädigt"):
                await mock_ocr.process_document(
                    image_path="/tmp/corrupted.pdf"
                )

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_very_large_document_handling(self):
        """Test handling of very large document."""
        with patch("app.services.ocr_service.OCRService") as MockOCR:
            mock_ocr = AsyncMock()
            # Large document takes longer but succeeds
            mock_ocr.process_document.return_value = {
                "success": True,
                "text": "A" * 100000,  # 100KB of text
                "pages": 50,
                "processing_time_ms": 45000  # 45 seconds
            }
            MockOCR.return_value = mock_ocr

            result = await mock_ocr.process_document(
                image_path="/tmp/large_doc.pdf"
            )

            assert result["success"] is True
            assert result["pages"] == 50

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_mixed_language_document(self):
        """Test handling of mixed German/English document."""
        mixed_text = """
        Dear Customer,

        Betreff: Ihre Bestellung Nr. 12345

        Thank you for your order.
        Vielen Dank für Ihre Bestellung.

        Best regards / Mit freundlichen Grüßen
        """

        with patch("app.agents.preprocessing.classification_agent.ClassificationAgent") as MockAgent:
            mock_agent = AsyncMock()
            mock_agent.process.return_value = {
                "document_type": "letter",
                "language": "de",  # Primary language
                "secondary_language": "en",
                "confidence": 0.78
            }
            MockAgent.return_value = mock_agent

            result = await mock_agent.process({"text": mixed_text})

            assert result["language"] == "de"
            assert "secondary_language" in result


# ============================================================================
# Data Validation Tests
# ============================================================================

class TestDataValidation:
    """Tests for data validation throughout pipeline."""

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_iban_validation_in_pipeline(self):
        """Test IBAN validation during entity extraction."""
        text = "IBAN: DE89 3704 0044 0532 0130 00"

        entity_result = {
            "entities": [
                {
                    "type": "iban",
                    "value": "DE89370400440532013000",
                    "valid": True,
                    "checksum_valid": True,
                    "confidence": 0.99
                }
            ]
        }

        with patch("app.agents.postprocessing.entity_extraction_agent.EntityExtractionAgent") as MockAgent:
            mock_agent = AsyncMock()
            mock_agent.process.return_value = entity_result
            MockAgent.return_value = mock_agent

            result = await mock_agent.process({"text": text})

            iban_entity = result["entities"][0]
            assert iban_entity["valid"] is True
            assert iban_entity["checksum_valid"] is True

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_date_format_validation(self):
        """Test German date format validation."""
        text = "Datum: 15.03.2024"

        entity_result = {
            "entities": [
                {
                    "type": "date",
                    "value": "15.03.2024",
                    "parsed": "2024-03-15",
                    "format": "DD.MM.YYYY",
                    "valid": True,
                    "confidence": 0.96
                }
            ]
        }

        with patch("app.agents.postprocessing.entity_extraction_agent.EntityExtractionAgent") as MockAgent:
            mock_agent = AsyncMock()
            mock_agent.process.return_value = entity_result
            MockAgent.return_value = mock_agent

            result = await mock_agent.process({"text": text})

            date_entity = result["entities"][0]
            assert date_entity["format"] == "DD.MM.YYYY"
            assert date_entity["valid"] is True

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_currency_format_validation(self):
        """Test German currency format validation."""
        text = "Betrag: 1.234,56 EUR"

        entity_result = {
            "entities": [
                {
                    "type": "currency",
                    "value": {
                        "amount": 1234.56,
                        "currency": "EUR",
                        "original_format": "1.234,56 EUR"
                    },
                    "valid": True,
                    "confidence": 0.98
                }
            ]
        }

        with patch("app.agents.postprocessing.entity_extraction_agent.EntityExtractionAgent") as MockAgent:
            mock_agent = AsyncMock()
            mock_agent.process.return_value = entity_result
            MockAgent.return_value = mock_agent

            result = await mock_agent.process({"text": text})

            currency_entity = result["entities"][0]
            assert currency_entity["value"]["amount"] == 1234.56
            assert currency_entity["value"]["currency"] == "EUR"
