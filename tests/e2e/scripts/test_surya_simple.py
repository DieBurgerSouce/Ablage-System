"""Simple Surya OCR test with proper API usage."""

from PIL import Image
from pathlib import Path
from surya.ocr import run_ocr
from surya.model.detection.segformer import load_model as load_det_model
from surya.model.detection.segformer import load_processor as load_det_processor
from surya.model.recognition.model import load_model as load_rec_model
from surya.model.recognition.processor import load_processor as load_rec_processor

print("Loading Surya models...")
det_model = load_det_model()
det_processor = load_det_processor()
rec_model = load_rec_model()
rec_processor = load_rec_processor()
print("Models loaded successfully!")

# Load test image
test_image = Path("test_documents/test_umlauts.png")
if test_image.exists():
    print(f"\nProcessing: {test_image}")
    image = Image.open(test_image)

    # Important: Surya expects a list with single language code per image
    # Not a list of languages for one image!
    try:
        # Process image - one language per image
        predictions = run_ocr([image], ["de"], det_model, det_processor, rec_model, rec_processor)

        if predictions:
            result = predictions[0]
            print("\nOCR Results:")
            print("-" * 50)

            # Extract text from result
            if hasattr(result, 'text_lines'):
                for line in result.text_lines:
                    if hasattr(line, 'text'):
                        print(line.text)
            else:
                print(result)

            print("-" * 50)
            print("OCR completed successfully!")
        else:
            print("No predictions returned")

    except AssertionError as e:
        print(f"AssertionError: {e}")
        print("\nTrying alternative approach...")

        # Alternative: Try with English
        try:
            predictions = run_ocr([image], ["en"], det_model, det_processor, rec_model, rec_processor)
            if predictions:
                result = predictions[0]
                print("\nOCR Results (English):")
                print("-" * 50)
                if hasattr(result, 'text_lines'):
                    for line in result.text_lines:
                        if hasattr(line, 'text'):
                            print(line.text)
                print("-" * 50)
        except Exception as e2:
            print(f"Also failed with English: {e2}")

    except Exception as e:
        print(f"Error during OCR: {e}")
        import traceback
        traceback.print_exc()
else:
    print(f"Test image not found: {test_image}")