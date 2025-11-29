"""
OCR Processing Agent - Autonomous Document Processing
Orchestriert den vollstaendigen OCR-Pipeline-Workflow
"""

from typing import Dict, Any, Optional, List
from datetime import datetime

import structlog

logger = structlog.get_logger(__name__)


class OCRProcessingAgent:
    """
    Autonomous agent for end-to-end OCR processing.

    Orchestrates the complete document processing pipeline including:
    - Document retrieval
    - Backend selection
    - OCR processing with fallback
    - German text validation
    - Template field extraction
    - Quality assurance
    - Result storage
    """

    def __init__(self):
        self._storage_agent = None
        self._ocr_agent = None
        self._validation_agent = None
        self._template_agent = None
        self._qa_agent = None

    def _get_storage_agent(self):
        """Lazy load storage agent."""
        if self._storage_agent is None:
            from Execution_Layer.Sub_Agents.storage_sub_agent import StorageSubAgent
            self._storage_agent = StorageSubAgent()
        return self._storage_agent

    async def process_document(
        self,
        document_id: str,
        backend: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Autonomously process document through complete pipeline.

        Steps:
        1. Load document from storage
        2. Select optimal backend (decision tree)
        3. Process with OCR (with retry/fallback)
        4. Validate German text
        5. Extract template fields
        6. Validate compliance
        7. Store results
        8. Log GDPR access

        Args:
            document_id: UUID of the document to process
            backend: Optional OCR backend override (auto-select if None)

        Returns:
            dict with processing results, extracted text, and metadata
        """
        result = {
            "document_id": document_id,
            "status": "processing",
            "steps": [],
            "started_at": datetime.utcnow().isoformat()
        }

        try:
            # Step 1: Load document from storage
            storage_agent = self._get_storage_agent()
            doc_data = await storage_agent.retrieve_document(document_id)

            if doc_data.get("status") != "success":
                raise ValueError(
                    f"Dokument konnte nicht geladen werden: {doc_data.get('error', 'Unbekannter Fehler')}"
                )

            result["steps"].append({
                "step": "load_document",
                "status": "success",
                "source": doc_data.get("source")
            })

            logger.info(
                "ocr_step_load_complete",
                document_id=document_id,
                file_size=doc_data.get("metadata", {}).get("file_size")
            )

            # Step 2: Select optimal backend
            if backend is None:
                backend = await self._select_backend(doc_data)

            result["backend"] = backend
            result["steps"].append({
                "step": "backend_selection",
                "status": "success",
                "selected_backend": backend
            })

            logger.info(
                "ocr_step_backend_selected",
                document_id=document_id,
                backend=backend
            )

            # Step 3: Process with OCR (with retry/fallback)
            ocr_result = await self._process_with_ocr(
                doc_data.get("file"),
                backend,
                document_id
            )

            result["ocr_result"] = ocr_result
            result["text"] = ocr_result.get("text", "")
            result["confidence"] = ocr_result.get("confidence", 0.0)
            result["steps"].append({
                "step": "ocr_processing",
                "status": "success",
                "backend_used": ocr_result.get("backend"),
                "confidence": ocr_result.get("confidence")
            })

            logger.info(
                "ocr_step_processing_complete",
                document_id=document_id,
                text_length=len(result["text"]),
                confidence=result["confidence"]
            )

            # Step 4: Validate German text
            validation_result = await self._validate_german_text(result["text"])
            result["german_validation"] = validation_result
            result["steps"].append({
                "step": "german_validation",
                "status": "success" if validation_result.get("valid", False) else "warning",
                "has_umlauts": validation_result.get("has_umlauts"),
                "issues_count": len(validation_result.get("issues", []))
            })

            logger.info(
                "ocr_step_validation_complete",
                document_id=document_id,
                valid=validation_result.get("valid")
            )

            # Step 5: Extract template fields
            extracted_fields = await self._extract_template_fields(result["text"])
            result["extracted_fields"] = extracted_fields
            result["steps"].append({
                "step": "template_extraction",
                "status": "success",
                "fields_count": len(extracted_fields.get("fields", {}))
            })

            logger.info(
                "ocr_step_extraction_complete",
                document_id=document_id,
                fields=list(extracted_fields.get("fields", {}).keys())
            )

            # Step 6: Validate compliance (QA check)
            qa_result = await self._validate_compliance(result)
            result["qa_validation"] = qa_result
            result["steps"].append({
                "step": "qa_validation",
                "status": "success" if qa_result.get("passed", False) else "warning",
                "checks_passed": sum(1 for c in qa_result.get("checks", []) if c.get("passed"))
            })

            logger.info(
                "ocr_step_qa_complete",
                document_id=document_id,
                passed=qa_result.get("passed")
            )

            # Step 7: Store results
            store_result = await self._store_results(document_id, result)
            result["steps"].append({
                "step": "store_results",
                "status": "success" if store_result else "warning"
            })

            # Step 8: Log GDPR access
            logger.info(
                "gdpr_document_processed",
                document_id=document_id,
                action="ocr_processing",
                article="DSGVO Art. 6 - Rechtmaessigkeit der Verarbeitung",
                processing_purpose="Dokumentendigitalisierung"
            )
            result["steps"].append({
                "step": "gdpr_logging",
                "status": "success"
            })

            result["status"] = "success"
            result["finished_at"] = datetime.utcnow().isoformat()

            logger.info(
                "ocr_processing_complete",
                document_id=document_id,
                total_steps=len(result["steps"]),
                text_length=len(result["text"])
            )

        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            result["finished_at"] = datetime.utcnow().isoformat()

            logger.error(
                "ocr_processing_failed",
                document_id=document_id,
                error=str(e),
                exc_info=True
            )

        return result

    async def _select_backend(self, doc_data: Dict[str, Any]) -> str:
        """
        Select optimal OCR backend based on document analysis.

        Uses UnifiedRouter for intelligent backend selection.
        """
        try:
            from app.agents.orchestration.unified_router import UnifiedRouter

            router = UnifiedRouter()

            # Prepare analysis data
            analysis = {
                "mime_type": doc_data.get("metadata", {}).get("mime_type"),
                "file_size": doc_data.get("metadata", {}).get("file_size"),
                "language": doc_data.get("metadata", {}).get("language", "de")
            }

            # Get routing decision
            routing_result = await router.route(analysis)

            if hasattr(routing_result, 'backend'):
                return routing_result.backend.value
            elif isinstance(routing_result, dict):
                return routing_result.get("backend", "surya")
            else:
                return str(routing_result)

        except Exception as e:
            logger.warning(
                "backend_selection_fallback",
                error=str(e)
            )
            # Default to Surya (CPU-based, always available)
            return "surya"

    async def _process_with_ocr(
        self,
        file_content: bytes,
        backend: str,
        document_id: str
    ) -> Dict[str, Any]:
        """
        Process document with OCR, with retry and fallback logic.
        """
        from Execution_Layer.Sub_Agents.ocr_backend_agent import OCRBackendAgent

        # Fallback chain: requested backend → surya_gpu → surya
        fallback_backends = [backend]
        if backend not in ["surya", "surya_gpu"]:
            fallback_backends.append("surya_gpu")
        if backend != "surya":
            fallback_backends.append("surya")

        last_error = None

        for current_backend in fallback_backends:
            try:
                ocr_agent = OCRBackendAgent(current_backend)
                results = await ocr_agent.process_batch([file_content])

                if results and len(results) > 0:
                    result = results[0]
                    if result.get("text") or result.get("confidence", 0) > 0:
                        logger.info(
                            "ocr_backend_success",
                            document_id=document_id,
                            backend=current_backend
                        )
                        return result

            except Exception as e:
                last_error = e
                logger.warning(
                    "ocr_backend_failed_trying_next",
                    document_id=document_id,
                    backend=current_backend,
                    error=str(e)
                )
                continue

        # All backends failed
        raise RuntimeError(
            f"Alle OCR-Backends fehlgeschlagen: {last_error}"
        )

    async def _validate_german_text(self, text: str) -> Dict[str, Any]:
        """Validate German text for umlaut integrity and common OCR errors."""
        try:
            from Static_Knowledge.Snippets.german_validation_snippets import (
                validate_umlaut_integrity,
                normalize_german_text
            )

            # Normalize text first
            normalized = normalize_german_text(text)

            # Validate umlaut integrity
            validation = validate_umlaut_integrity(normalized)

            return validation

        except ImportError:
            logger.warning("german_validation_snippets_not_available")
            return {
                "valid": True,
                "has_umlauts": False,
                "issues": [],
                "note": "Validierung nicht verfuegbar"
            }
        except Exception as e:
            logger.error("german_validation_failed", error=str(e))
            return {
                "valid": False,
                "error": str(e)
            }

    async def _extract_template_fields(self, text: str) -> Dict[str, Any]:
        """Extract template fields from OCR text."""
        try:
            from Static_Knowledge.Snippets.german_validation_snippets import (
                extract_german_dates,
                extract_tax_ids,
                extract_company_names,
                extract_business_terms
            )

            fields = {
                "dates": extract_german_dates(text),
                "tax_ids": extract_tax_ids(text),
                "companies": extract_company_names(text),
                "business_terms": extract_business_terms(text)
            }

            # Calculate extraction confidence
            total_fields = sum(
                len(v) if isinstance(v, list) else (1 if v else 0)
                for v in fields.values()
            )

            return {
                "fields": fields,
                "total_extracted": total_fields,
                "confidence": min(1.0, total_fields * 0.1) if total_fields > 0 else 0.0
            }

        except ImportError:
            logger.warning("template_extraction_not_available")
            return {"fields": {}, "total_extracted": 0, "confidence": 0.0}
        except Exception as e:
            logger.error("template_extraction_failed", error=str(e))
            return {"fields": {}, "error": str(e)}

    async def _validate_compliance(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Run QA validation checks on processing result."""
        checks = []

        # Check 1: OCR confidence
        confidence = result.get("confidence", 0.0)
        checks.append({
            "name": "ocr_confidence",
            "passed": confidence >= 0.85,
            "value": confidence,
            "threshold": 0.85
        })

        # Check 2: Text extraction success
        text_length = len(result.get("text", ""))
        checks.append({
            "name": "text_extracted",
            "passed": text_length > 0,
            "value": text_length
        })

        # Check 3: German validation
        german_valid = result.get("german_validation", {}).get("valid", False)
        checks.append({
            "name": "german_validation",
            "passed": german_valid,
            "issues": result.get("german_validation", {}).get("issues", [])
        })

        # Check 4: Fields extracted
        fields_count = result.get("extracted_fields", {}).get("total_extracted", 0)
        checks.append({
            "name": "fields_extracted",
            "passed": fields_count > 0,
            "value": fields_count
        })

        # Overall pass/fail
        passed = all(c["passed"] for c in checks)

        return {
            "passed": passed,
            "checks": checks,
            "warnings": [c["name"] for c in checks if not c["passed"]],
            "timestamp": datetime.utcnow().isoformat()
        }

    async def _store_results(
        self,
        document_id: str,
        result: Dict[str, Any]
    ) -> bool:
        """Store OCR results back to storage."""
        try:
            # Update document status in database
            from app.db.database import async_session_maker
            from app.db.models import Document, OCRResult
            from sqlalchemy import select
            import uuid

            async with async_session_maker() as session:
                # Update document status
                query = select(Document).where(
                    Document.id == uuid.UUID(document_id)
                )
                db_result = await session.execute(query)
                doc = db_result.scalar_one_or_none()

                if doc:
                    doc.status = "processed"
                    doc.extracted_text = result.get("text", "")
                    doc.ocr_confidence = result.get("confidence", 0.0)

                    # Store OCR result
                    ocr_record = OCRResult(
                        document_id=uuid.UUID(document_id),
                        backend=result.get("backend", "unknown"),
                        extracted_text=result.get("text", ""),
                        confidence=result.get("confidence", 0.0),
                        metadata={
                            "extracted_fields": result.get("extracted_fields"),
                            "german_validation": result.get("german_validation"),
                            "qa_validation": result.get("qa_validation")
                        }
                    )
                    session.add(ocr_record)
                    await session.commit()

                    logger.info(
                        "ocr_results_stored",
                        document_id=document_id
                    )
                    return True

            return False

        except Exception as e:
            logger.error(
                "store_results_failed",
                document_id=document_id,
                error=str(e)
            )
            return False


# See: Static_Knowledge/Skills/backend_selection_skill.yaml
# See: Relations/Decision_Trees/backend_selection_tree.yaml
