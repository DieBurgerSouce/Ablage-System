"""
Preprocessing Agents Package.

Contains agents responsible for document preprocessing before OCR:
- Document Classification
- Image Enhancement
- Page Segmentation
- Fraktur Detection
- Handwriting Detection
"""

from app.agents.preprocessing.classification_agent import DocumentClassificationAgent
from app.agents.preprocessing.fraktur_detector import (
    FrakturAnalysis,
    FrakturConfidence,
    FrakturDetectorAgent,
    FrakturFeature,
    detect_fraktur,
    get_fraktur_detector,
    get_recommended_backend,
    is_fraktur,
)
from app.agents.preprocessing.handwriting_detector import (
    HandwritingAnalysis,
    HandwritingConfidence,
    HandwritingDetectorAgent,
    HandwritingFeature,
    HandwritingRegion,
    HandwritingType,
    detect_handwriting,
    get_confidence_penalty,
    get_handwriting_detector,
    get_handwriting_regions,
    has_handwriting,
    route_to_backend_for_handwriting,
)
from app.agents.preprocessing.image_enhancement_agent import ImageEnhancementAgent
from app.agents.preprocessing.qr_barcode_detector import (
    CodeCategory,
    CodeDetectionResult,
    CodeType,
    DetectedCode,
    QRBarcodeDetectorAgent,
    SEPAPaymentData,
    detect_codes,
    extract_ean_codes,
    extract_sepa_payment,
    get_qr_barcode_detector,
    has_payment_codes,
)
from app.agents.preprocessing.page_segmentation_agent import (
    LayoutType,
    PageInfo,
    PageSegmentationAgent,
    Region,
    RegionType,
)

__all__ = [
    # Classification
    "DocumentClassificationAgent",
    # Image Enhancement
    "ImageEnhancementAgent",
    # Page Segmentation
    "LayoutType",
    "PageInfo",
    "PageSegmentationAgent",
    "Region",
    "RegionType",
    # Fraktur Detection
    "FrakturAnalysis",
    "FrakturConfidence",
    "FrakturDetectorAgent",
    "FrakturFeature",
    "detect_fraktur",
    "get_fraktur_detector",
    "get_recommended_backend",
    "is_fraktur",
    # Handwriting Detection
    "HandwritingAnalysis",
    "HandwritingConfidence",
    "HandwritingDetectorAgent",
    "HandwritingFeature",
    "HandwritingRegion",
    "HandwritingType",
    "detect_handwriting",
    "get_confidence_penalty",
    "get_handwriting_detector",
    "get_handwriting_regions",
    "has_handwriting",
    "route_to_backend_for_handwriting",
    # QR & Barcode Detection
    "CodeCategory",
    "CodeDetectionResult",
    "CodeType",
    "DetectedCode",
    "QRBarcodeDetectorAgent",
    "SEPAPaymentData",
    "detect_codes",
    "extract_ean_codes",
    "extract_sepa_payment",
    "get_qr_barcode_detector",
    "has_payment_codes",
]
