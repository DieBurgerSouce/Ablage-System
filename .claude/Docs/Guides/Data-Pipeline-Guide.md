# Data Pipeline Guide - Ablage System

## 🎯 Overview

Dieser umfassende Guide beschreibt die komplette Data Processing Pipeline des Ablage-Systems - von der Dokument-Aufnahme bis zur finalen Speicherung der OCR-Ergebnisse. Die Pipeline ist optimiert für hohen Durchsatz, Fehlertoleranz und Skalierbarkeit.

### Pipeline Stages

1. **Document Ingestion** - File Upload, Validation, Initial Storage
2. **Preprocessing** - Image Enhancement, Format Conversion, Thumbnail Generation
3. **Complexity Analysis** - Automatic Document Classification
4. **OCR Processing** - Multi-Backend Text Extraction
5. **Postprocessing** - Data Validation, Field Extraction, Quality Checks
6. **Result Storage** - Multi-Tier Storage (PostgreSQL, S3, Redis)
7. **Notification** - Webhooks, Email, Status Updates

---

## 📊 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      CLIENT (Frontend/API)                      │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    STAGE 1: INGESTION                           │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  • File Upload Handler                                    │  │
│  │  • Format Validation (PDF, PNG, JPG, TIFF)               │  │
│  │  • Size Validation (max 100MB)                           │  │
│  │  • Virus Scanning (ClamAV)                               │  │
│  │  • S3 Upload (original-documents bucket)                 │  │
│  │  • Database Entry Creation                               │  │
│  │  • Job Queue Submission                                  │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   STAGE 2: PREPROCESSING                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  • Format Detection & Conversion                         │  │
│  │  • Multi-Page PDF Split                                  │  │
│  │  • Image Enhancement (Deskew, Denoise, Contrast)        │  │
│  │  • Resolution Normalization (300 DPI)                   │  │
│  │  • Thumbnail Generation (200x200, 400x400)              │  │
│  │  • Metadata Extraction (EXIF, PDF Info)                 │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                STAGE 3: COMPLEXITY ANALYSIS                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  • Image Quality Metrics (Variance, Sharpness)          │  │
│  │  • Layout Complexity Score                               │  │
│  │  • Text Density Analysis                                 │  │
│  │  • Language Detection (German, English, Multi)          │  │
│  │  • Document Type Classification                          │  │
│  │  • Backend Recommendation (DeepSeek/GOT-OCR/Surya)      │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    STAGE 4: OCR PROCESSING                      │
│  ┌──────────────┬──────────────┬──────────────────────────┐    │
│  │  GPU-A       │   GPU-B      │      CPU                 │    │
│  │ DeepSeek     │  GOT-OCR     │   Surya+Docling         │    │
│  │ (Complex)    │  (Simple)    │   (Fallback)            │    │
│  └──────────────┴──────────────┴──────────────────────────┘    │
│  • Automatic Backend Selection                                 │
│  • Batch Processing (when applicable)                          │
│  • Retry Logic (3 attempts with exponential backoff)          │
│  • Timeout Handling (max 10 min per page)                     │
│  • Result Validation (confidence thresholds)                   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   STAGE 5: POSTPROCESSING                       │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  • Spell Checking (German Dictionary)                   │  │
│  │  • Field Extraction (Regex + NLP)                       │  │
│  │  • Data Validation (Format, Range, Consistency)         │  │
│  │  • Confidence Scoring                                    │  │
│  │  • Table Normalization                                   │  │
│  │  • Format Conversion (JSON, XML, CSV)                   │  │
│  │  • Quality Assurance Checks                             │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    STAGE 6: RESULT STORAGE                      │
│  ┌──────────────┬──────────────┬──────────────────────────┐    │
│  │ PostgreSQL   │    Redis     │       S3/MinIO           │    │
│  │ (Metadata)   │   (Cache)    │    (Files)               │    │
│  └──────────────┴──────────────┴──────────────────────────┘    │
│  • Atomic Transaction Handling                                 │
│  • Versioning & History Tracking                               │
│  • Audit Logging                                               │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    STAGE 7: NOTIFICATION                        │
│  • Webhook Delivery                                             │
│  • Email Notifications                                          │
│  • WebSocket Updates                                            │
│  • Status Page Update                                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📥 STAGE 1: Document Ingestion

### 1.1 File Upload Handler

```python
# backend/api/v1/documents.py

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Optional, List
import uuid
import hashlib
import magic
import aiofiles
from datetime import datetime

from backend.core.database import get_db
from backend.models.documents import Document, ProcessingJob
from backend.tasks.process_document import process_document_task
from backend.core.storage import s3_client, ORIGINAL_BUCKET
from backend.core.auth import get_current_user
from backend.schemas.documents import DocumentUploadResponse

router = APIRouter(prefix="/documents", tags=["documents"])

# Allowed file types
ALLOWED_MIME_TYPES = {
    'application/pdf': ['.pdf'],
    'image/png': ['.png'],
    'image/jpeg': ['.jpg', '.jpeg'],
    'image/tiff': ['.tiff', '.tif'],
}

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    document_type: Optional[str] = None,
    tags: Optional[List[str]] = None,
    metadata: Optional[dict] = None,
    priority: int = 5,  # 1-10, higher = more important
    callback_url: Optional[str] = None,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Upload a document for OCR processing.

    **Process**:
    1. Validate file type and size
    2. Scan for viruses (optional)
    3. Generate unique document ID
    4. Upload to S3 (original-documents bucket)
    5. Create database entries
    6. Queue processing job
    7. Return document ID and status

    **Arguments**:
    - file: Document file (PDF, PNG, JPG, TIFF)
    - document_type: Optional type hint (invoice, contract, etc.)
    - tags: Optional tags for categorization
    - metadata: Optional custom metadata
    - priority: Processing priority (1-10, default 5)
    - callback_url: Optional webhook URL for completion notification

    **Returns**:
    - document_id: Unique document identifier
    - status: Initial status (pending)
    - upload_timestamp: Upload time
    - estimated_pages: Estimated page count
    """

    # ===== VALIDATION =====

    # 1. Check file size
    file.file.seek(0, 2)  # Seek to end
    file_size = file.file.tell()
    file.file.seek(0)  # Reset to beginning

    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size: {MAX_FILE_SIZE / 1024 / 1024}MB"
        )

    if file_size == 0:
        raise HTTPException(
            status_code=400,
            detail="Empty file"
        )

    # 2. Validate MIME type
    file_content = await file.read()
    mime_type = magic.from_buffer(file_content, mime=True)

    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {mime_type}. Allowed: {list(ALLOWED_MIME_TYPES.keys())}"
        )

    # Validate file extension
    file_ext = '.' + file.filename.split('.')[-1].lower()
    if file_ext not in ALLOWED_MIME_TYPES[mime_type]:
        raise HTTPException(
            status_code=400,
            detail=f"File extension {file_ext} doesn't match MIME type {mime_type}"
        )

    # 3. Optional: Virus Scanning
    if ENABLE_VIRUS_SCANNING:
        is_safe = await scan_file_for_viruses(file_content)
        if not is_safe:
            raise HTTPException(
                status_code=400,
                detail="File failed virus scan"
            )

    # ===== DOCUMENT CREATION =====

    # Generate unique document ID
    document_id = str(uuid.uuid4())

    # Calculate file hash (for deduplication)
    file_hash = hashlib.sha256(file_content).hexdigest()

    # Check for duplicate
    existing_doc = db.query(Document).filter(
        Document.file_hash == file_hash,
        Document.user_id == current_user.id
    ).first()

    if existing_doc and ENABLE_DEDUPLICATION:
        return DocumentUploadResponse(
            document_id=existing_doc.id,
            status="duplicate",
            message=f"Duplicate of document {existing_doc.id}",
            duplicate_of=existing_doc.id
        )

    # ===== S3 UPLOAD =====

    # Generate S3 key
    s3_key = f"{current_user.id}/{datetime.utcnow().strftime('%Y/%m/%d')}/{document_id}/{file.filename}"

    try:
        # Upload to S3
        await s3_client.put_object(
            Bucket=ORIGINAL_BUCKET,
            Key=s3_key,
            Body=file_content,
            ContentType=mime_type,
            Metadata={
                'document_id': document_id,
                'user_id': str(current_user.id),
                'original_filename': file.filename
            }
        )
    except Exception as e:
        logger.error(f"S3 upload failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to upload document to storage"
        )

    # ===== DATABASE ENTRIES =====

    # Estimate page count
    estimated_pages = await estimate_page_count(file_content, mime_type)

    # Create Document record
    document = Document(
        id=document_id,
        user_id=current_user.id,
        filename=file.filename,
        mime_type=mime_type,
        file_size=file_size,
        file_hash=file_hash,
        s3_bucket=ORIGINAL_BUCKET,
        s3_key=s3_key,
        document_type=document_type,
        status='pending',
        estimated_pages=estimated_pages,
        tags=tags or [],
        metadata=metadata or {},
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )

    db.add(document)

    # Create Processing Job
    job = ProcessingJob(
        id=str(uuid.uuid4()),
        document_id=document_id,
        user_id=current_user.id,
        status='queued',
        priority=priority,
        callback_url=callback_url,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )

    db.add(job)
    db.commit()
    db.refresh(document)
    db.refresh(job)

    # ===== QUEUE PROCESSING =====

    # Submit to Celery task queue
    background_tasks.add_task(
        process_document_task.apply_async,
        args=[document_id],
        kwargs={'job_id': job.id},
        priority=priority,
        expires=3600  # Expire after 1 hour if not processed
    )

    # Log event
    logger.info(
        "document_uploaded",
        document_id=document_id,
        user_id=current_user.id,
        filename=file.filename,
        size_bytes=file_size,
        estimated_pages=estimated_pages
    )

    # Emit metrics
    document_upload_total.labels(
        user_id=current_user.id,
        document_type=document_type or 'unknown'
    ).inc()

    document_upload_bytes.labels(
        user_id=current_user.id
    ).observe(file_size)

    return DocumentUploadResponse(
        document_id=document_id,
        job_id=job.id,
        status='pending',
        filename=file.filename,
        file_size=file_size,
        estimated_pages=estimated_pages,
        upload_timestamp=document.created_at,
        message="Document uploaded successfully and queued for processing"
    )


async def estimate_page_count(file_content: bytes, mime_type: str) -> int:
    """Estimate number of pages in document"""

    if mime_type == 'application/pdf':
        # Use PyPDF2 to count pages
        import io
        from PyPDF2 import PdfReader

        pdf = PdfReader(io.BytesIO(file_content))
        return len(pdf.pages)

    else:
        # Images are single page
        return 1


async def scan_file_for_viruses(file_content: bytes) -> bool:
    """Scan file for viruses using ClamAV"""

    import clamd

    try:
        cd = clamd.ClamdUnixSocket()
        result = cd.scan_stream(file_content)

        if result is None:
            return True  # No virus found

        # Check result
        for key, val in result.items():
            if val[0] == 'FOUND':
                logger.warning(f"Virus detected: {val[1]}")
                return False

        return True

    except Exception as e:
        logger.error(f"Virus scanning failed: {e}")
        # Fail safe: reject file if scanning fails
        return False if STRICT_VIRUS_CHECKING else True
```

### 1.2 Batch Upload

```python
@router.post("/upload/batch", response_model=List[DocumentUploadResponse])
async def upload_documents_batch(
    files: List[UploadFile] = File(...),
    document_type: Optional[str] = None,
    priority: int = 5,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Upload multiple documents in one request.

    Max 50 files per batch.
    """

    if len(files) > 50:
        raise HTTPException(
            status_code=400,
            detail="Maximum 50 files per batch upload"
        )

    results = []

    for file in files:
        try:
            result = await upload_document(
                file=file,
                document_type=document_type,
                priority=priority,
                background_tasks=background_tasks,
                db=db,
                current_user=current_user
            )
            results.append(result)

        except Exception as e:
            # Log error but continue with other files
            logger.error(f"Failed to upload {file.filename}: {e}")
            results.append(DocumentUploadResponse(
                document_id=None,
                status='error',
                filename=file.filename,
                message=str(e)
            ))

    return results
```

---

## 🔧 STAGE 2: Preprocessing

### 2.1 Format Detection & Conversion

```python
# backend/services/preprocessing/format_handler.py

from PIL import Image
import pdf2image
from typing import List, Tuple
import tempfile
import os

class FormatHandler:
    """Handle different document formats and convert to images"""

    def __init__(self, dpi: int = 300):
        self.dpi = dpi

    async def process_document(self, file_path: str, mime_type: str) -> List[str]:
        """
        Process document and return list of image paths (one per page).

        Returns:
            List of temporary file paths containing page images
        """

        if mime_type == 'application/pdf':
            return await self._process_pdf(file_path)

        elif mime_type.startswith('image/'):
            return await self._process_image(file_path)

        else:
            raise ValueError(f"Unsupported MIME type: {mime_type}")

    async def _process_pdf(self, pdf_path: str) -> List[str]:
        """Convert PDF pages to images"""

        # Convert PDF to images (one per page)
        images = pdf2image.convert_from_path(
            pdf_path,
            dpi=self.dpi,
            fmt='PNG',
            thread_count=4  # Parallel conversion
        )

        # Save to temporary files
        temp_files = []

        for i, img in enumerate(images):
            # Create temp file
            temp_file = tempfile.NamedTemporaryFile(
                mode='wb',
                suffix='.png',
                delete=False
            )

            # Save image
            img.save(temp_file.name, 'PNG', optimize=True, compress_level=6)
            temp_files.append(temp_file.name)

        logger.info(f"Converted PDF to {len(temp_files)} images")

        return temp_files

    async def _process_image(self, image_path: str) -> List[str]:
        """Process single image"""

        # Load image
        img = Image.open(image_path)

        # Convert to RGB if needed
        if img.mode != 'RGB':
            img = img.convert('RGB')

        # Normalize DPI
        img_with_dpi = self._normalize_dpi(img)

        # Save to temp file
        temp_file = tempfile.NamedTemporaryFile(
            mode='wb',
            suffix='.png',
            delete=False
        )

        img_with_dpi.save(temp_file.name, 'PNG', dpi=(self.dpi, self.dpi))

        return [temp_file.name]

    def _normalize_dpi(self, img: Image.Image) -> Image.Image:
        """Ensure image is at target DPI"""

        # Get current DPI
        current_dpi = img.info.get('dpi', (72, 72))

        if isinstance(current_dpi, (int, float)):
            current_dpi = (current_dpi, current_dpi)

        # Calculate scale factor
        scale_x = self.dpi / current_dpi[0]
        scale_y = self.dpi / current_dpi[1]

        # Resize if needed
        if scale_x != 1.0 or scale_y != 1.0:
            new_width = int(img.width * scale_x)
            new_height = int(img.height * scale_y)

            img = img.resize(
                (new_width, new_height),
                Image.Resampling.LANCZOS
            )

        return img
```

### 2.2 Image Enhancement

```python
# backend/services/preprocessing/image_enhancer.py

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage
import logging

logger = logging.getLogger(__name__)


class ImageEnhancer:
    """Advanced image preprocessing for OCR optimization"""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.enable_deskew = self.config.get('enable_deskew', True)
        self.enable_denoise = self.config.get('enable_denoise', True)
        self.enable_contrast = self.config.get('enable_contrast', True)
        self.enable_binarization = self.config.get('enable_binarization', False)

    def enhance(self, image_path: str) -> np.ndarray:
        """
        Apply all enhancement techniques.

        Pipeline:
        1. Deskew (correct rotation)
        2. Denoise (remove noise)
        3. Contrast enhancement (improve readability)
        4. Optional: Binarization (convert to black & white)

        Returns:
            Enhanced image as numpy array
        """

        # Load image
        img = cv2.imread(image_path)

        if img is None:
            raise ValueError(f"Failed to load image: {image_path}")

        # Original size (for metrics)
        original_size = img.shape

        # 1. Deskew
        if self.enable_deskew:
            img = self._deskew(img)
            logger.debug("Image deskewed")

        # 2. Denoise
        if self.enable_denoise:
            img = self._denoise(img)
            logger.debug("Image denoised")

        # 3. Contrast Enhancement
        if self.enable_contrast:
            img = self._enhance_contrast(img)
            logger.debug("Contrast enhanced")

        # 4. Binarization (optional, for very poor quality scans)
        if self.enable_binarization:
            img = self._binarize(img)
            logger.debug("Image binarized")

        logger.info(
            "Image enhancement complete",
            original_size=original_size,
            final_size=img.shape
        )

        return img

    def _deskew(self, img: np.ndarray) -> np.ndarray:
        """
        Correct image rotation using Hough Transform.

        Detects dominant lines in image and rotates to align them.
        """

        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Edge detection
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)

        # Detect lines using Hough Transform
        lines = cv2.HoughLines(edges, 1, np.pi / 180, 200)

        if lines is None:
            return img  # No lines detected, return original

        # Calculate angles
        angles = []
        for rho, theta in lines[:, 0]:
            angle = (theta * 180 / np.pi) - 90
            angles.append(angle)

        # Get median angle
        median_angle = np.median(angles)

        # Only rotate if angle is significant (> 0.5 degrees)
        if abs(median_angle) > 0.5:
            # Rotate image
            (h, w) = img.shape[:2]
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
            img = cv2.warpAffine(
                img,
                M,
                (w, h),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_REPLICATE
            )

            logger.debug(f"Rotated image by {median_angle:.2f} degrees")

        return img

    def _denoise(self, img: np.ndarray) -> np.ndarray:
        """
        Remove noise using Non-Local Means Denoising.

        Preserves edges while removing noise.
        """

        # Apply denoising
        denoised = cv2.fastNlMeansDenoisingColored(
            img,
            None,
            h=10,          # Filter strength
            hColor=10,     # Color filter strength
            templateWindowSize=7,
            searchWindowSize=21
        )

        return denoised

    def _enhance_contrast(self, img: np.ndarray) -> np.ndarray:
        """
        Enhance contrast using CLAHE (Contrast Limited Adaptive Histogram Equalization).

        Better than global histogram equalization for documents with varying lighting.
        """

        # Convert to LAB color space
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)

        # Split channels
        l, a, b = cv2.split(lab)

        # Apply CLAHE to L channel
        clahe = cv2.createCLAHE(
            clipLimit=3.0,
            tileGridSize=(8, 8)
        )
        l = clahe.apply(l)

        # Merge channels
        lab = cv2.merge([l, a, b])

        # Convert back to BGR
        enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

        return enhanced

    def _binarize(self, img: np.ndarray) -> np.ndarray:
        """
        Convert to black & white using Otsu's thresholding.

        Useful for very poor quality scans.
        """

        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Apply Gaussian blur
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        # Otsu's thresholding
        _, binary = cv2.threshold(
            blurred,
            0,
            255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        # Convert back to BGR for consistency
        binary_bgr = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)

        return binary_bgr
```

### 2.3 Thumbnail Generation

```python
# backend/services/preprocessing/thumbnail_generator.py

from PIL import Image
from typing import List, Tuple
import os

class ThumbnailGenerator:
    """Generate thumbnails for document preview"""

    SIZES = [
        (200, 200),   # Small thumbnail
        (400, 400),   # Medium thumbnail
        (800, 800),   # Large thumbnail
    ]

    def generate_thumbnails(
        self,
        image_path: str,
        output_dir: str
    ) -> List[Tuple[str, Tuple[int, int]]]:
        """
        Generate thumbnails in multiple sizes.

        Returns:
            List of (file_path, size) tuples
        """

        img = Image.open(image_path)

        thumbnails = []

        for size in self.SIZES:
            # Create thumbnail
            thumb = img.copy()
            thumb.thumbnail(size, Image.Resampling.LANCZOS)

            # Generate filename
            filename = f"thumb_{size[0]}x{size[1]}.jpg"
            output_path = os.path.join(output_dir, filename)

            # Save
            thumb.save(
                output_path,
                'JPEG',
                quality=85,
                optimize=True
            )

            thumbnails.append((output_path, size))

        return thumbnails
```

---

## 🧠 STAGE 3: Complexity Analysis

### 3.1 Document Complexity Analyzer

```python
# backend/services/analysis/complexity_analyzer.py

import cv2
import numpy as np
from PIL import Image
from typing import Dict, Tuple
from enum import Enum
import langdetect

class DocumentComplexity(Enum):
    SIMPLE = "simple"       # Clean scan, standard layout
    MODERATE = "moderate"   # Some noise, decent quality
    COMPLEX = "complex"     # Poor quality, complex layout, handwriting


class ComplexityAnalyzer:
    """Analyze document complexity to select optimal OCR backend"""

    def __init__(self):
        self.weights = {
            'image_quality': 0.3,
            'layout_complexity': 0.25,
            'text_density': 0.2,
            'noise_level': 0.15,
            'resolution': 0.1
        }

    def analyze(self, image_path: str) -> Dict:
        """
        Comprehensive complexity analysis.

        Returns dict with:
        - complexity: simple/moderate/complex
        - score: 0-100 (higher = more complex)
        - metrics: individual metric scores
        - recommendation: suggested OCR backend
        """

        # Load image
        img = cv2.imread(image_path)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Calculate metrics
        metrics = {
            'image_quality': self._measure_image_quality(gray),
            'layout_complexity': self._measure_layout_complexity(gray),
            'text_density': self._measure_text_density(gray),
            'noise_level': self._measure_noise_level(gray),
            'resolution': self._measure_resolution(img)
        }

        # Calculate weighted score
        score = sum(
            metrics[key] * self.weights[key]
            for key in metrics
        )

        # Classify complexity
        if score < 30:
            complexity = DocumentComplexity.SIMPLE
            backend = "got_ocr"
        elif score < 60:
            complexity = DocumentComplexity.MODERATE
            backend = "deepseek"
        else:
            complexity = DocumentComplexity.COMPLEX
            backend = "deepseek"

        return {
            'complexity': complexity.value,
            'score': score,
            'metrics': metrics,
            'recommendation': backend,
            'details': self._generate_details(metrics, complexity)
        }

    def _measure_image_quality(self, gray: np.ndarray) -> float:
        """
        Measure image quality using variance and sharpness.

        Returns: 0-100 (higher = lower quality = more complex)
        """

        # Variance (proxy for contrast)
        variance = np.var(gray)
        variance_score = max(0, 100 - (variance / 1000) * 100)

        # Sharpness using Laplacian
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        sharpness = laplacian.var()
        sharpness_score = max(0, 100 - (sharpness / 100))

        # Combined score
        quality_score = (variance_score + sharpness_score) / 2

        return min(100, quality_score)

    def _measure_layout_complexity(self, gray: np.ndarray) -> float:
        """
        Measure layout complexity using edge detection.

        More edges = more complex layout

        Returns: 0-100
        """

        # Edge detection
        edges = cv2.Canny(gray, 50, 150)

        # Count edges
        edge_pixels = np.count_nonzero(edges)
        total_pixels = edges.size

        # Edge density
        edge_density = (edge_pixels / total_pixels) * 100

        # Map to 0-100 scale
        # >5% edges = complex layout
        complexity_score = min(100, (edge_density / 5) * 100)

        return complexity_score

    def _measure_text_density(self, gray: np.ndarray) -> float:
        """
        Estimate text density.

        Lower density = more complex (lots of white space, images, etc.)

        Returns: 0-100
        """

        # Binarize
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Count dark pixels (text)
        dark_pixels = np.count_nonzero(binary == 0)
        total_pixels = binary.size

        # Text density
        density = (dark_pixels / total_pixels) * 100

        # Optimal density is around 20-30%
        # Score based on deviation from optimal
        if density < 10 or density > 50:
            # Too sparse or too dense = complex
            score = 70
        elif 15 < density < 35:
            # Optimal range = simple
            score = 20
        else:
            # Moderate
            score = 45

        return score

    def _measure_noise_level(self, gray: np.ndarray) -> float:
        """
        Measure noise level using median filter.

        Higher difference = more noise

        Returns: 0-100
        """

        # Apply median filter
        median = cv2.medianBlur(gray, 5)

        # Calculate difference
        diff = cv2.absdiff(gray, median)

        # Mean difference
        noise_level = np.mean(diff)

        # Map to 0-100 scale
        # >10 mean difference = noisy
        noise_score = min(100, (noise_level / 10) * 100)

        return noise_score

    def _measure_resolution(self, img: np.ndarray) -> float:
        """
        Measure effective resolution.

        Low resolution = more complex for OCR

        Returns: 0-100
        """

        height, width = img.shape[:2]
        megapixels = (height * width) / 1_000_000

        # Optimal: 2-5 MP (roughly 300 DPI for letter size)
        if megapixels < 1:
            # Too low resolution
            score = 80
        elif 2 <= megapixels <= 5:
            # Optimal
            score = 20
        elif megapixels > 10:
            # Very high res (may slow down processing)
            score = 40
        else:
            # Moderate
            score = 35

        return score

    def _generate_details(self, metrics: Dict, complexity: DocumentComplexity) -> str:
        """Generate human-readable analysis details"""

        details = []

        if metrics['image_quality'] > 60:
            details.append("Poor image quality detected")

        if metrics['layout_complexity'] > 60:
            details.append("Complex layout with multiple sections")

        if metrics['noise_level'] > 50:
            details.append("High noise level in image")

        if metrics['resolution'] > 60:
            details.append("Non-optimal resolution")

        if not details:
            details.append("Good quality document with standard layout")

        return "; ".join(details)
```

---

## 🔥 STAGE 4: OCR Processing

### 4.1 Celery Task

```python
# backend/tasks/process_document.py

from celery import Task, states
from celery.exceptions import Reject, Retry
from backend.core.celery_app import celery_app
from backend.core.database import get_db
from backend.models.documents import Document, ProcessingJob, OCRResult
from backend.services.orchestrator.router import intelligent_router
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ProcessDocumentTask(Task):
    """Custom Task class with error handling and retries"""

    autoretry_for = (ConnectionError, TimeoutError)
    retry_kwargs = {'max_retries': 3}
    retry_backoff = True  # Exponential backoff
    retry_backoff_max = 600  # Max 10 minutes
    retry_jitter = True  # Add randomness to backoff


@celery_app.task(
    bind=True,
    base=ProcessDocumentTask,
    name='tasks.process_document',
    time_limit=600,  # 10 minutes hard limit
    soft_time_limit=540  # 9 minutes soft limit
)
def process_document_task(self, document_id: str, job_id: str):
    """
    Main OCR processing task.

    Pipeline:
    1. Load document from DB
    2. Download from S3
    3. Preprocess (enhance, normalize)
    4. Analyze complexity
    5. Route to optimal OCR backend
    6. Postprocess results
    7. Store results
    8. Send notifications

    Args:
        document_id: UUID of document
        job_id: UUID of processing job
    """

    db = next(get_db())

    try:
        # ===== STAGE 1: LOAD DOCUMENT =====

        document = db.query(Document).filter(Document.id == document_id).first()
        job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()

        if not document or not job:
            raise ValueError(f"Document or job not found: {document_id}, {job_id}")

        # Update job status
        job.status = 'processing'
        job.started_at = datetime.utcnow()
        job.celery_task_id = self.request.id
        db.commit()

        logger.info(f"Processing document {document_id}")

        # ===== STAGE 2: DOWNLOAD FROM S3 =====

        # Download file from S3
        local_path = download_from_s3(
            bucket=document.s3_bucket,
            key=document.s3_key,
            document_id=document_id
        )

        # ===== STAGE 3: PREPROCESS =====

        from backend.services.preprocessing import PreprocessingPipeline

        preprocessing = PreprocessingPipeline()
        preprocessed_pages = preprocessing.process(
            file_path=local_path,
            mime_type=document.mime_type
        )

        # Update page count
        document.total_pages = len(preprocessed_pages)
        db.commit()

        # ===== STAGE 4: OCR PROCESSING =====

        results = []

        for page_num, page_path in enumerate(preprocessed_pages, start=1):
            # Update progress
            job.progress_percent = int((page_num / len(preprocessed_pages)) * 100)
            job.current_page = page_num
            db.commit()

            # Process page
            result = intelligent_router.route_document(
                image_path=page_path,
                options={
                    'document_type': document.document_type,
                    'page_number': page_num
                }
            )

            results.append(result)

            logger.info(
                f"Page {page_num}/{len(preprocessed_pages)} processed",
                backend=result.backend_used,
                confidence=result.confidence,
                duration=result.processing_time
            )

        # ===== STAGE 5: POSTPROCESSING =====

        from backend.services.postprocessing import PostprocessingPipeline

        postprocessing = PostprocessingPipeline()
        final_results = postprocessing.process(
            ocr_results=results,
            document_type=document.document_type
        )

        # ===== STAGE 6: STORE RESULTS =====

        # Store in database
        for page_num, result in enumerate(final_results, start=1):
            ocr_result = OCRResult(
                id=str(uuid.uuid4()),
                document_id=document_id,
                job_id=job_id,
                page_number=page_num,
                text=result.text,
                confidence=result.confidence,
                backend_used=result.backend_used,
                processing_time=result.processing_time,
                layout_data=result.layout,
                table_data=result.tables,
                field_data=result.extracted_fields,
                created_at=datetime.utcnow()
            )
            db.add(ocr_result)

        # Update document status
        document.status = 'completed'
        document.processed_at = datetime.utcnow()

        # Calculate aggregate metrics
        document.average_confidence = sum(r.confidence for r in final_results) / len(final_results)
        document.total_processing_time = sum(r.processing_time for r in final_results)

        # Update job status
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        job.progress_percent = 100

        db.commit()

        # ===== STAGE 7: NOTIFICATIONS =====

        # Send webhook if configured
        if job.callback_url:
            send_webhook_notification(job.callback_url, {
                'event': 'document.completed',
                'document_id': document_id,
                'job_id': job_id,
                'pages_processed': len(final_results),
                'average_confidence': document.average_confidence
            })

        # Send email notification
        send_email_notification(
            user_id=document.user_id,
            document_id=document_id,
            status='completed'
        )

        logger.info(f"Document {document_id} processing completed successfully")

        return {
            'status': 'success',
            'document_id': document_id,
            'pages_processed': len(final_results),
            'average_confidence': document.average_confidence
        }

    except Exception as e:
        logger.error(f"Error processing document {document_id}: {e}", exc_info=True)

        # Update job status
        job.status = 'failed'
        job.error_message = str(e)
        job.completed_at = datetime.utcnow()

        # Update document status
        document.status = 'failed'

        db.commit()

        # Send error notification
        if job.callback_url:
            send_webhook_notification(job.callback_url, {
                'event': 'document.failed',
                'document_id': document_id,
                'error': str(e)
            })

        # Re-raise for Celery retry mechanism
        raise

    finally:
        # Cleanup temporary files
        cleanup_temp_files(document_id)
        db.close()
```

---

## ✨ STAGE 5: Postprocessing

### 5.1 Field Extraction

```python
# backend/services/postprocessing/field_extractor.py

import re
from typing import Dict, Optional, List
from datetime import datetime
import spacy

class FieldExtractor:
    """Extract structured fields from OCR text"""

    def __init__(self):
        # Load German NLP model
        self.nlp = spacy.load('de_core_news_sm')

        # Compile regex patterns
        self.patterns = {
            'invoice_number': [
                r'Rechnung(?:snummer)?:?\s*([A-Z0-9-]+)',
                r'Invoice\s*(?:No|Number)?:?\s*([A-Z0-9-]+)',
                r'Rg\.?\s*Nr\.?\s*:?\s*([A-Z0-9-]+)',
            ],
            'date': [
                r'Datum:?\s*(\d{1,2}\.\\d{1,2}\.\d{2,4})',
                r'Date:?\s*(\d{1,2}/\d{1,2}/\d{2,4})',
                r'(\d{1,2}\.\d{1,2}\.\d{4})',
            ],
            'total_amount': [
                r'Gesamt(?:betrag)?:?\s*([\d.,]+)\s*€',
                r'Total:?\s*€?\s*([\d.,]+)',
                r'Summe:?\s*([\d.,]+)\s*€',
            ],
            'vat_number': [
                r'USt[\.-]?(?:ID|IdNr)?:?\s*([A-Z]{2}\s*\d+)',
                r'VAT\s*(?:No|Number)?:?\s*([A-Z]{2}\s*\d+)',
            ],
            'iban': [
                r'IBAN:?\s*([A-Z]{2}\d{2}\s?(?:\d{4}\s?){4}\d{2})',
            ],
            'email': [
                r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
            ],
            'phone': [
                r'\+?\d{1,3}[\s.-]?\(?\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4}',
            ]
        }

    def extract(self, text: str, document_type: Optional[str] = None) -> Dict:
        """Extract fields based on document type"""

        if document_type == 'invoice':
            return self._extract_invoice_fields(text)
        elif document_type == 'contract':
            return self._extract_contract_fields(text)
        else:
            return self._extract_generic_fields(text)

    def _extract_invoice_fields(self, text: str) -> Dict:
        """Extract invoice-specific fields"""

        fields = {}

        # Invoice number
        fields['invoice_number'] = self._extract_pattern(text, 'invoice_number')

        # Date
        date_str = self._extract_pattern(text, 'date')
        fields['invoice_date'] = self._parse_date(date_str) if date_str else None

        # Total amount
        amount_str = self._extract_pattern(text, 'total_amount')
        fields['total_amount'] = self._parse_amount(amount_str) if amount_str else None

        # VAT number
        fields['vat_number'] = self._extract_pattern(text, 'vat_number')

        # IBAN
        fields['iban'] = self._extract_pattern(text, 'iban')

        # Extract line items
        fields['line_items'] = self._extract_line_items(text)

        # Supplier information using NER
        fields['supplier'] = self._extract_supplier(text)

        return fields

    def _extract_pattern(self, text: str, pattern_name: str) -> Optional[str]:
        """Extract value using regex patterns"""

        patterns = self.patterns.get(pattern_name, [])

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return None

    def _parse_date(self, date_str: str) -> Optional[str]:
        """Parse date string to ISO format"""

        # Try different date formats
        formats = [
            '%d.%m.%Y',
            '%d.%m.%y',
            '%d/%m/%Y',
            '%Y-%m-%d',
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                continue

        return None

    def _parse_amount(self, amount_str: str) -> Optional[float]:
        """Parse amount string to float"""

        # Remove currency symbols
        amount_str = re.sub(r'[€$]', '', amount_str)

        # Replace comma with dot for decimal
        amount_str = amount_str.replace(',', '.')

        # Remove thousand separators
        amount_str = re.sub(r'\.(?=\d{3})', '', amount_str)

        try:
            return float(amount_str)
        except ValueError:
            return None

    def _extract_line_items(self, text: str) -> List[Dict]:
        """Extract invoice line items"""

        # Pattern for line items (simplified)
        # Format: Description | Quantity | Unit Price | Total
        pattern = r'(.+?)\s+(\d+(?:[.,]\d+)?)\s+(\d+(?:[.,]\d+)?)\s*€?\s+(\d+(?:[.,]\d+)?)\s*€?'

        matches = re.findall(pattern, text)

        line_items = []
        for match in matches:
            line_items.append({
                'description': match[0].strip(),
                'quantity': self._parse_amount(match[1]),
                'unit_price': self._parse_amount(match[2]),
                'total': self._parse_amount(match[3])
            })

        return line_items

    def _extract_supplier(self, text: str) -> Optional[Dict]:
        """Extract supplier information using NER"""

        doc = self.nlp(text[:1000])  # Process first 1000 chars

        # Extract organizations
        orgs = [ent.text for ent in doc.ents if ent.label_ == 'ORG']

        # Extract addresses
        addresses = [ent.text for ent in doc.ents if ent.label_ == 'LOC']

        if orgs:
            return {
                'name': orgs[0],
                'address': addresses[0] if addresses else None
            }

        return None
```

### 5.2 Quality Assurance

```python
# backend/services/postprocessing/quality_checker.py

from typing import Dict, List
import logging

logger = logging.getLogger(__name__)


class QualityChecker:
    """Validate OCR results and extracted data"""

    def __init__(self, min_confidence: float = 0.7):
        self.min_confidence = min_confidence

    def check(self, result: Dict) -> Dict:
        """
        Run quality checks.

        Returns:
        - passed: bool (overall pass/fail)
        - checks: dict of individual check results
        - warnings: list of warning messages
        - errors: list of error messages
        """

        checks = {}
        warnings = []
        errors = []

        # Check 1: Confidence threshold
        if result.get('confidence', 0) < self.min_confidence:
            checks['confidence'] = False
            errors.append(
                f"Confidence {result['confidence']:.2f} below threshold {self.min_confidence}"
            )
        else:
            checks['confidence'] = True

        # Check 2: Text not empty
        text = result.get('text', '').strip()
        if not text:
            checks['text_present'] = False
            errors.append("No text extracted")
        else:
            checks['text_present'] = True

        # Check 3: Reasonable text length
        if len(text) < 10:
            checks['text_length'] = False
            warnings.append("Very short text extracted")
        else:
            checks['text_length'] = True

        # Check 4: Field extraction (if applicable)
        if 'extracted_fields' in result:
            fields = result['extracted_fields']

            # Check if key fields are present
            if result.get('document_type') == 'invoice':
                required_fields = ['invoice_number', 'total_amount']
                missing = [f for f in required_fields if not fields.get(f)]

                if missing:
                    checks['required_fields'] = False
                    warnings.append(f"Missing fields: {', '.join(missing)}")
                else:
                    checks['required_fields'] = True

        # Overall pass/fail
        passed = all(checks.values()) and len(errors) == 0

        return {
            'passed': passed,
            'checks': checks,
            'warnings': warnings,
            'errors': errors
        }
```

---

## 💾 STAGE 6: Result Storage

### 6.1 Multi-Tier Storage Strategy

```python
# backend/services/storage/result_storage.py

from backend.core.database import get_db
from backend.core.storage import s3_client, redis_client
from backend.models.documents import OCRResult
import json
from datetime import datetime, timedelta

class ResultStorage:
    """Store OCR results in multiple tiers"""

    def __init__(self):
        self.db = next(get_db())

    async def store(self, document_id: str, results: List[Dict]):
        """
        Store results in all tiers.

        Tier 1: PostgreSQL (metadata, searchable fields)
        Tier 2: S3 (full JSON results)
        Tier 3: Redis (cache for quick access)
        """

        # ===== TIER 1: PostgreSQL =====

        for result in results:
            ocr_result = OCRResult(
                id=str(uuid.uuid4()),
                document_id=document_id,
                page_number=result['page_number'],
                text=result['text'],
                confidence=result['confidence'],
                backend_used=result['backend_used'],
                processing_time=result['processing_time'],
                created_at=datetime.utcnow()
            )
            self.db.add(ocr_result)

        self.db.commit()

        # ===== TIER 2: S3 =====

        # Store full results as JSON
        s3_key = f"results/{document_id}/ocr_results.json"

        await s3_client.put_object(
            Bucket='processed-documents',
            Key=s3_key,
            Body=json.dumps(results, indent=2),
            ContentType='application/json',
            Metadata={
                'document_id': document_id,
                'timestamp': datetime.utcnow().isoformat()
            }
        )

        # ===== TIER 3: Redis Cache =====

        # Cache for 24 hours
        redis_key = f"results:{document_id}"
        redis_client.setex(
            redis_key,
            86400,  # 24 hours
            json.dumps(results)
        )

        logger.info(f"Results stored for document {document_id}")
```

---

## 📊 Monitoring & Metrics

### Pipeline Metrics

```python
# Prometheus metrics

from prometheus_client import Counter, Histogram, Gauge

# Pipeline stage metrics
pipeline_stage_duration = Histogram(
    'pipeline_stage_duration_seconds',
    'Time spent in each pipeline stage',
    ['stage']
)

# Processing success/failure
document_processing_total = Counter(
    'document_processing_total',
    'Total documents processed',
    ['status', 'document_type']
)

# Queue depth
processing_queue_depth = Gauge(
    'processing_queue_depth',
    'Number of documents in processing queue'
)

# Error tracking
pipeline_errors_total = Counter(
    'pipeline_errors_total',
    'Pipeline errors by stage',
    ['stage', 'error_type']
)
```

---

## 🎯 Best Practices

### 1. Error Handling
- ✅ Use try-except blocks at each stage
- ✅ Implement retry logic with exponential backoff
- ✅ Log errors with full context
- ✅ Fail gracefully (save partial results)

### 2. Performance
- ✅ Batch process when possible
- ✅ Use async I/O for S3/DB operations
- ✅ Cache frequently accessed data (Redis)
- ✅ Monitor queue depth and scale accordingly

### 3. Data Quality
- ✅ Validate input at every stage
- ✅ Run quality checks on OCR results
- ✅ Store confidence scores
- ✅ Allow manual review for low-confidence results

### 4. Scalability
- ✅ Design for horizontal scaling (stateless workers)
- ✅ Use distributed queue (Celery + Redis)
- ✅ Partition data by user/date
- ✅ Implement rate limiting

---

## 📚 Further Reading

- [Celery Best Practices](https://docs.celeryproject.org/en/stable/userguide/tasks.html)
- [Image Processing with OpenCV](https://docs.opencv.org/)
- [S3 Performance Optimization](https://aws.amazon.com/s3/performance/)
- [PostgreSQL Performance Tuning](https://wiki.postgresql.org/wiki/Performance_Optimization)
