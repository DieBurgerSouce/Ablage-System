"""
Ablage-System OCR API
Main FastAPI application entry point

Created: 2025-11-22
Status: Proof of Concept
"""

from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from datetime import datetime
from typing import Optional, List
import sys
from pathlib import Path
import logging

# Add app directory to path
sys.path.append(str(Path(__file__).parent))

from gpu_manager import GPUManager
from german_validator import GermanValidator

# Import API routers
try:
    from api.v1 import agents, metrics
    API_ROUTERS_AVAILABLE = True
except ImportError as e:
    API_ROUTERS_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning(f"API routers not available: {e}")

try:
    from core.exceptions import AblageSystemException
    from core.monitoring import get_system_monitor, PerformanceTimer
    from core.gdpr import get_gdpr_manager, DataCategory, ProcessingPurpose
    MONITORING_AVAILABLE = True
    GDPR_AVAILABLE = True
except ImportError:
    MONITORING_AVAILABLE = False
    GDPR_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("Core modules not available")

try:
    from services.ocr_service import get_ocr_service
    OCR_SERVICE_AVAILABLE = True
except ImportError:
    OCR_SERVICE_AVAILABLE = False
    logger.warning("OCR service not available")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Ablage-System OCR",
    description="Enterprise German Document Processing with GPU Acceleration",
    version="0.1.0-poc",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Initialize managers
gpu_manager = GPUManager()
german_validator = GermanValidator()
system_monitor = get_system_monitor() if MONITORING_AVAILABLE else None
gdpr_manager = get_gdpr_manager() if GDPR_AVAILABLE else None
ocr_service = get_ocr_service() if OCR_SERVICE_AVAILABLE else None

# Register API routers
if API_ROUTERS_AVAILABLE:
    app.include_router(agents.router, prefix="/api/v1", tags=["agents"])
    app.include_router(metrics.router, prefix="/api/v1", tags=["metrics"])
    logger.info("Multi-agent API routers registered")


# Exception handlers
if MONITORING_AVAILABLE:
    @app.exception_handler(AblageSystemException)
    async def ablage_exception_handler(request: Request, exc: AblageSystemException):
        """Handle custom Ablage-System exceptions"""
        logger.error(f"AblageSystemException: {exc.error_code} - {exc.message}")
        if system_monitor:
            system_monitor.metrics.record_error(exc.error_code)

        return JSONResponse(
            status_code=400,
            content=exc.to_dict()
        )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors"""
    logger.warning(f"Validation error: {exc}")
    return JSONResponse(
        status_code=422,
        content={
            "error_code": "E011",
            "message": "Validation error",
            "user_message_de": "Ungültige Eingabedaten",
            "details": exc.errors()
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions"""
    logger.exception("Unexpected error")
    if MONITORING_AVAILABLE and system_monitor:
        system_monitor.metrics.record_error("E999")

    return JSONResponse(
        status_code=500,
        content={
            "error_code": "E999",
            "message": "Internal server error",
            "user_message_de": "Interner Serverfehler",
            "details": {"type": type(exc).__name__}
        }
    )

@app.on_event("startup")
async def startup_event():
    """Initialize system on startup"""
    print("[>] Starting Ablage-System OCR...")

    # Check GPU
    gpu_status = gpu_manager.check_availability()
    if gpu_status["available"]:
        print(f"[OK] GPU detected: {gpu_status.get('gpu_name', 'Unknown')}")
        print(f"     Total VRAM: {gpu_status['total_gb']:.1f}GB")
    else:
        print("[!] No GPU detected - running in CPU mode")

    # Initialize skills
    if API_ROUTERS_AVAILABLE:
        try:
            from app.core.skill_loader import initialize_skills
            await initialize_skills()
            print("[OK] Skills loaded")
        except Exception as e:
            print(f"[!] Failed to load skills: {e}")

    print("[OK] System ready!")

@app.get("/")
def root():
    """Root endpoint with system info"""
    return {
        "system": "Ablage-System OCR",
        "status": "operational",
        "philosophy": "Feinpoliert und durchdacht",
        "documentation": "See /docs for API documentation"
    }

@app.get("/health")
def health_check():
    """Health check endpoint"""
    gpu_status = gpu_manager.check_availability()

    response = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "gpu": {
            "available": gpu_status["available"],
            "name": gpu_status.get("gpu_name"),
            "vram_total_gb": gpu_status.get("total_gb"),
            "vram_free_gb": gpu_status.get("free_gb")
        },
        "backends": {
            "deepseek": "not_implemented",
            "got_ocr": "not_implemented",
            "surya": "not_implemented"
        }
    }

    # Add monitoring data if available
    if MONITORING_AVAILABLE and system_monitor:
        response["system_status"] = system_monitor.get_system_status()
        response["metrics"] = system_monitor.metrics.get_summary()

    return response


@app.get("/metrics")
def get_metrics():
    """Get system metrics and statistics"""
    if not MONITORING_AVAILABLE or not system_monitor:
        return {
            "error": "Monitoring not available",
            "message": "Install monitoring modules"
        }

    return {
        "metrics": system_monitor.metrics.get_summary(),
        "system": system_monitor.get_system_status(),
        "health": system_monitor.check_health()
    }

@app.post("/ocr/test")
async def test_ocr(text: str = "Müller GmbH & Co. KG"):
    """Test OCR endpoint with German text validation"""

    # Validate German text
    validation_result = german_validator.validate_umlauts(text)
    date_formats = german_validator.validate_date_format(text)
    currency_formats = german_validator.validate_currency_format(text)

    return {
        "input": text,
        "mock_output": f"Verarbeitet: {text}",
        "validation": {
            "umlauts_valid": validation_result["valid"],
            "umlauts_found": validation_result["umlauts_found"],
            "potential_errors": validation_result["potential_errors"],
            "confidence": validation_result["confidence"]
        },
        "extracted": {
            "dates": date_formats,
            "amounts": currency_formats
        },
        "backend": "mock",
        "processing_time_ms": 42
    }

@app.post("/ocr/process")
async def process_document(
    file: UploadFile = File(...),
    backend: Optional[str] = None,
    language: str = "de",
    detect_layout: bool = True
):
    """
    Process uploaded document with OCR

    Args:
        file: Uploaded image/PDF file
        backend: OCR backend to use ("auto", "deepseek", "got_ocr", "surya")
        language: Target language (default: "de")
        detect_layout: Perform layout detection (default: True)

    Returns:
        OCR result with extracted text and metadata

    TODO: Add proper authentication before production!
    """
    import os

    # File size limit (50 MB default)
    MAX_FILE_SIZE = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50")) * 1024 * 1024

    # Allowed file extensions
    ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"}

    # Validate file extension
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{file_ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Read file with size limit
    content = bytearray()
    bytes_read = 0
    async for chunk in file.stream:
        bytes_read += len(chunk)
        if bytes_read > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size: {MAX_FILE_SIZE // 1024 // 1024}MB"
            )
        content.extend(chunk)
    if not OCR_SERVICE_AVAILABLE or not ocr_service:
        # Fallback to mock processing
        return {
            "success": True,
            "filename": file.filename,
            "text": f"[MOCK] Dokument '{file.filename}' verarbeitet\n\nRechnung Nr. 2024-001\nMüller GmbH\nBetrag: 1.234,56 €",
            "backend": "mock",
            "message": "OCR service running with mock processing - install backends for real OCR",
            "gpu_available": gpu_manager.check_availability()["available"],
            "file_size_bytes": len(content)
        }

    # Save uploaded file temporarily
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
        tmp_file.write(content)
        tmp_path = tmp_file.name

    try:
        # Process with OCR service
        result = await ocr_service.process_document(
            image_path=tmp_path,
            backend=backend or "auto",
            language=language,
            detect_layout=detect_layout
        )

        # Add file info
        result["file_info"] = {
            "filename": file.filename,
            "size_bytes": len(content),
            "content_type": file.content_type
        }

        return result

    finally:
        # Cleanup temp file
        Path(tmp_path).unlink(missing_ok=True)

@app.post("/ocr/batch")
async def batch_process_documents(
    files: List[UploadFile] = File(...),
    backend: Optional[str] = None,
    language: str = "de"
):
    """
    Batch process multiple documents

    Args:
        files: List of uploaded files
        backend: OCR backend to use for all files
        language: Target language

    Returns:
        List of OCR results

    TODO: Add proper authentication before production!
    """
    import os

    # Batch size limit
    MAX_BATCH_SIZE = int(os.getenv("MAX_BATCH_SIZE", "10"))
    if len(files) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Batch too large. Maximum {MAX_BATCH_SIZE} files allowed. Received: {len(files)}"
        )

    # File size limit per file
    MAX_FILE_SIZE = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50")) * 1024 * 1024
    ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"}
    if not OCR_SERVICE_AVAILABLE or not ocr_service:
        return {
            "error": "OCR service not available",
            "message": "Install OCR backends for batch processing",
            "mock_mode": True,
            "files_received": len(files)
        }

    import tempfile
    temp_files = []

    try:
        # Validate and save all files temporarily
        for file in files:
            # Validate file extension
            file_ext = Path(file.filename).suffix.lower()
            if file_ext not in ALLOWED_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid file type in batch: '{file.filename}' ({file_ext})"
                )

            # Read with size limit
            content = bytearray()
            bytes_read = 0
            async for chunk in file.stream:
                bytes_read += len(chunk)
                if bytes_read > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File '{file.filename}' too large. Max: {MAX_FILE_SIZE // 1024 // 1024}MB"
                    )
                content.extend(chunk)

            # Save to temp file
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_ext)
            tmp_file.write(content)
            tmp_file.close()
            temp_files.append(tmp_file.name)

        # Batch process
        results = await ocr_service.batch_process(
            image_paths=temp_files,
            backend=backend or "auto",
            language=language
        )

        # Add filenames to results
        for i, result in enumerate(results):
            if i < len(files):
                result["filename"] = files[i].filename

        return {
            "batch_size": len(files),
            "results": results,
            "stats": ocr_service.get_stats()
        }

    finally:
        # Cleanup all temp files
        for tmp_path in temp_files:
            Path(tmp_path).unlink(missing_ok=True)


@app.get("/ocr/stats")
def get_ocr_stats():
    """Get OCR processing statistics"""
    if not OCR_SERVICE_AVAILABLE or not ocr_service:
        return {
            "error": "OCR service not available"
        }

    return ocr_service.get_stats()


@app.get("/ocr/backends")
def list_ocr_backends():
    """List available OCR backends"""
    backends = {
        "deepseek": {
            "name": "DeepSeek-Janus-Pro 1.0",
            "type": "multimodal_vlm",
            "vram_required_gb": 12.0,
            "performance": "2-3 pages/sec",
            "best_for": "Complex layouts, tables, images",
            "installed": False  # Would check actual installation
        },
        "got_ocr": {
            "name": "GOT-OCR 2.0",
            "type": "transformer_ocr",
            "vram_required_gb": 10.0,
            "performance": "5-7 pages/sec",
            "best_for": "Handwriting, degraded documents",
            "installed": False
        },
        "surya": {
            "name": "Surya + Docling",
            "type": "cpu_pipeline",
            "vram_required_gb": 0,
            "performance": "1-2 pages/sec",
            "best_for": "CPU fallback, layout analysis",
            "installed": False
        }
    }

    return {
        "ocr_service_available": OCR_SERVICE_AVAILABLE,
        "backends": backends,
        "gpu_info": gpu_manager.get_detailed_status(),
        "auto_selection": "Available - automatically selects best backend based on document type and GPU availability"
    }


@app.get("/gpu/status")
def gpu_status():
    """Get detailed GPU status"""
    return gpu_manager.get_detailed_status()

@app.post("/validate/german")
async def validate_german_text(text: str):
    """Validate German text for OCR quality"""
    validation_result = {
        "umlauts": german_validator.validate_umlauts(text),
        "dates": german_validator.validate_date_format(text),
        "currency": german_validator.validate_currency_format(text),
        "business_terms": german_validator.extract_business_terms(text)
    }

    # Add GDPR sensitive data check
    if GDPR_AVAILABLE and gdpr_manager:
        validation_result["gdpr"] = gdpr_manager.check_sensitive_data(text)

    return validation_result


@app.get("/gdpr/compliance")
def get_gdpr_compliance():
    """Get GDPR compliance report"""
    if not GDPR_AVAILABLE or not gdpr_manager:
        return {
            "error": "GDPR module not available",
            "message": "Install GDPR compliance modules"
        }

    return gdpr_manager.get_compliance_report()


@app.post("/gdpr/data-export/{subject_id}")
def request_data_export(subject_id: str):
    """Art. 20 DSGVO - Request data export (Right to Data Portability)

    TODO: CRITICAL SECURITY ISSUE!
          Add authentication + identity verification before production!
          Must verify that requester owns this subject_id.

    SECURITY RISK: Currently NO AUTHENTICATION - anyone can export anyone's data!
    """
    # TODO: Replace with proper auth + identity check
    # if current_user.subject_id != subject_id and not is_admin(current_user):
    #     raise HTTPException(403, "Can only export your own data")

    import os
    if os.getenv("ENVIRONMENT", "development") == "production":
        raise HTTPException(
            status_code=403,
            detail="GDPR endpoints require authentication. Enable auth system first."
        )

    if not GDPR_AVAILABLE or not gdpr_manager:
        return {
            "error": "GDPR module not available"
        }

    export = gdpr_manager.generate_data_export(subject_id)

    return {
        "status": "success",
        "message_de": "Datenexport erfolgreich erstellt",
        "export": export
    }


@app.post("/gdpr/request-deletion/{subject_id}")
def request_data_deletion(subject_id: str):
    """Art. 17 DSGVO - Request data deletion (Right to Erasure)

    TODO: CRITICAL SECURITY ISSUE!
          Add authentication + identity verification before production!
          Must verify that requester owns this subject_id.

    SECURITY RISK: Currently NO AUTHENTICATION - anyone can delete anyone's data!
    """
    # TODO: Replace with proper auth + identity check
    # if current_user.subject_id != subject_id and not is_admin(current_user):
    #     raise HTTPException(403, "Can only delete your own data")

    import os
    if os.getenv("ENVIRONMENT", "development") == "production":
        raise HTTPException(
            status_code=403,
            detail="GDPR endpoints require authentication. Enable auth system first."
        )

    if not GDPR_AVAILABLE or not gdpr_manager:
        return {
            "error": "GDPR module not available"
        }

    # This would typically be more complex with database cleanup
    from core.gdpr import DataSubject

    subject = DataSubject(subject_id)
    deadline = subject.request_deletion()

    return {
        "status": "deletion_requested",
        "message_de": f"Löschung Ihrer Daten wurde beantragt",
        "subject_id": subject_id,
        "deletion_deadline": deadline.isoformat(),
        "deadline_human_readable_de": f"Innerhalb von 30 Tagen (bis {deadline.strftime('%d.%m.%Y')})"
    }

if __name__ == "__main__":
    import uvicorn
    print("[i] Starting development server...")
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
