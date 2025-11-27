"""Debug test for batch_recognition return type."""

import sys
from pathlib import Path
import torch
from PIL import Image

# Add app directory to path
sys.path.append(str(Path(__file__).parent / "app"))

# Import Surya components
from surya.recognition import batch_recognition
from surya.detection import batch_text_detection
from surya.model.detection.segformer import load_model as load_det_model
from surya.model.detection.segformer import load_processor as load_det_processor
from surya.model.recognition.model import load_model as load_rec_model
from surya.model.recognition.processor import load_processor as load_rec_processor

def test_batch_recognition_return():
    """Test what batch_recognition actually returns."""
    print("\n" + "="*60)
    print("BATCH RECOGNITION RETURN TYPE TEST")
    print("="*60)

    # Load models
    print("\nLoading models...")
    det_model = load_det_model()
    det_processor = load_det_processor()
    rec_model = load_rec_model()
    rec_processor = load_rec_processor()

    # Move to GPU if available
    if torch.cuda.is_available():
        print(f"Using GPU: {torch.cuda.get_device_name(0)}")
        det_model = det_model.cuda().to(torch.float16)
        rec_model = rec_model.cuda().to(torch.float16)
    else:
        print("Using CPU")

    # Load test image
    test_image = Image.open("test_documents/test_umlauts.png").convert("RGB")
    print(f"\nImage loaded: {test_image.size}")

    # First detect text regions
    print("\nDetecting text regions...")
    det_predictions = batch_text_detection([test_image], det_model, det_processor)
    print(f"Found {len(det_predictions[0].bboxes)} text regions")

    if len(det_predictions[0].bboxes) > 0:
        # Process first region for testing
        bbox = det_predictions[0].bboxes[0]
        x1, y1, x2, y2 = bbox.bbox
        cropped = test_image.crop((x1, y1, x2, y2))

        print("\n" + "-"*40)
        print("Testing batch_recognition with single image and language...")

        # Call batch_recognition
        result = batch_recognition(
            [cropped],      # Single image
            ["de"],         # Single language
            rec_model,
            rec_processor
        )

        # Debug the exact return type
        print(f"\n1. Type of result: {type(result)}")
        print(f"2. Result content: {result}")

        if isinstance(result, tuple):
            print(f"\n3. Result is a tuple with {len(result)} elements")
            for i, item in enumerate(result):
                print(f"   Element {i}: Type={type(item)}, Value={item}")

                if isinstance(item, list) and len(item) > 0:
                    first_item = item[0]
                    print(f"      First item type: {type(first_item)}")
                    print(f"      First item value: {first_item}")

                    # Check if it has .text attribute
                    if hasattr(first_item, 'text'):
                        print(f"      Has .text attribute: {first_item.text}")
                    else:
                        print(f"      NO .text attribute - it's a direct string!")

        elif isinstance(result, list):
            print(f"\n3. Result is a list with {len(result)} items")
            if len(result) > 0:
                first_item = result[0]
                print(f"   First item type: {type(first_item)}")
                print(f"   First item value: {first_item}")

                if hasattr(first_item, 'text'):
                    print(f"   Has .text attribute: {first_item.text}")
                else:
                    print(f"   NO .text attribute - it's a direct string!")

    print("\n" + "="*60)
    print("TEST COMPLETE")
    print("="*60)

if __name__ == "__main__":
    test_batch_recognition_return()