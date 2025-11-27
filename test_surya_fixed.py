"""Fixed Surya OCR test with proper language handling."""

from PIL import Image
from pathlib import Path
from surya.detection import batch_text_detection
from surya.recognition import batch_recognition
from surya.model.detection.segformer import load_model as load_det_model
from surya.model.detection.segformer import load_processor as load_det_processor
from surya.model.recognition.model import load_model as load_rec_model
from surya.model.recognition.processor import load_processor as load_rec_processor
from surya.postprocessing.text import draw_text_on_image
from surya.ocr import run_ocr

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

    print("\nStep 1: Detecting text regions...")
    # First detect text regions
    predictions = batch_text_detection([image], det_model, det_processor)

    if predictions and len(predictions) > 0:
        pred = predictions[0]
        print(f"Found {len(pred.bboxes)} text regions")

        # Now run full OCR with proper language setup
        # The key is that we need one language per image, not per text region
        print("\nStep 2: Running OCR with language detection fix...")

        try:
            # Use the high-level API but with single language
            results = run_ocr([image], ["_math"], det_model, det_processor, rec_model, rec_processor)

            if results and len(results) > 0:
                result = results[0]
                print("\nOCR Results:")
                print("-" * 50)

                # Extract text
                full_text = []
                if hasattr(result, 'text_lines'):
                    for line in result.text_lines:
                        if hasattr(line, 'text') and line.text:
                            print(line.text)
                            full_text.append(line.text)

                if not full_text:
                    print("No text extracted, checking alternative structure...")
                    print(f"Result type: {type(result)}")
                    print(f"Result dir: {dir(result)}")

                print("-" * 50)
                print(f"Total lines extracted: {len(full_text)}")

                # Save result image
                if hasattr(result, 'text_lines') and result.text_lines:
                    output_image = draw_text_on_image(pred.bboxes, full_text, image.size)
                    output_path = "test_documents/test_ocr_output.png"
                    output_image.save(output_path)
                    print(f"Output saved to: {output_path}")
            else:
                print("No OCR results returned")

        except Exception as e:
            print(f"OCR failed: {e}")

            # Fallback: Try manual recognition
            print("\nTrying manual recognition approach...")

            from surya.input.processing import slice_bboxes_from_image

            # Get image slices for each detected region
            slices = slice_bboxes_from_image(image, pred.bboxes)

            if slices:
                print(f"Processing {len(slices)} text regions...")

                # Create language list - one per slice
                langs = ["_math"] * len(slices)  # Use math as language-agnostic

                try:
                    # Run recognition on slices
                    rec_predictions, confidence_scores = batch_recognition(slices, langs, rec_model, rec_processor)

                    print("\nManual OCR Results:")
                    print("-" * 50)
                    for i, text in enumerate(rec_predictions):
                        if text:
                            print(f"Region {i+1}: {text}")
                    print("-" * 50)

                except Exception as e2:
                    print(f"Manual recognition also failed: {e2}")
    else:
        print("No text regions detected in image")
else:
    print(f"Test image not found: {test_image}")