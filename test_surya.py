"""Test Surya OCR installation and basic functionality."""

import sys
from pathlib import Path

# Test basic imports
try:
    print("Testing Surya imports...")
    from surya.ocr import run_ocr
    print("[OK] surya.ocr imported successfully")

    from surya.model.detection.segformer import load_model as load_det_model
    from surya.model.detection.segformer import load_processor as load_det_processor
    print("[OK] Detection model imports successful")

    from surya.model.recognition.model import load_model as load_rec_model
    from surya.model.recognition.processor import load_processor as load_rec_processor
    print("[OK] Recognition model imports successful")

    print("\nAll imports successful!")

    # Test basic functionality
    from PIL import Image

    # Try to load models
    print("\nLoading models (this may take a moment)...")
    det_model = load_det_model()
    det_processor = load_det_processor()
    print("[OK] Detection model loaded")

    rec_model = load_rec_model()
    rec_processor = load_rec_processor()
    print("[OK] Recognition model loaded")

    # Test with our test image
    test_image_path = Path("test_documents/test_umlauts.png")
    if test_image_path.exists():
        print(f"\nTesting OCR on: {test_image_path}")
        image = Image.open(test_image_path)

        # Run OCR - use only one language per image
        results = run_ocr([image], ["de"], det_model, det_processor, rec_model, rec_processor)

        # Extract text
        if results and len(results) > 0:
            result = results[0]
            if hasattr(result, 'text_lines'):
                text_lines = [line.text for line in result.text_lines if hasattr(line, 'text')]
                full_text = "\n".join(text_lines)
            else:
                full_text = str(result)

            print("\nExtracted text:")
            print("-" * 40)
            print(full_text)
            print("-" * 40)
            print(f"\nOCR successful! Extracted {len(full_text)} characters")
        else:
            print("No results returned from OCR")
    else:
        print(f"\nTest image not found: {test_image_path}")
        print("Run create_test_image.py first to create test images")

except ImportError as e:
    print(f"[ERROR] Import error: {e}")
    print("\nPossible fixes:")
    print("1. Make sure Surya is installed: pip install surya-ocr")
    print("2. Make sure PyTorch is installed: pip install torch")

except Exception as e:
    print(f"[ERROR] Error: {e}")
    import traceback
    traceback.print_exc()