"""Surya OCR test using lower-level API to handle language issue."""

from PIL import Image
from pathlib import Path
import torch
from surya.detection import batch_text_detection
from surya.recognition import batch_recognition
from surya.model.detection.segformer import load_model as load_det_model
from surya.model.detection.segformer import load_processor as load_det_processor
from surya.model.recognition.model import load_model as load_rec_model
from surya.model.recognition.processor import load_processor as load_rec_processor
from surya.postprocessing.text import draw_text_on_image
from surya.settings import settings

print("Loading Surya models...")
det_model = load_det_model()
det_processor = load_det_processor()
rec_model = load_rec_model()
rec_processor = load_rec_processor()
print("Models loaded successfully!")

def process_with_surya(image_path):
    """Process image with Surya using low-level API."""
    print(f"\nProcessing: {image_path}")

    # Load image
    image = Image.open(image_path)
    if image.mode != 'RGB':
        image = image.convert('RGB')

    # Step 1: Detect text regions
    print("Detecting text regions...")
    predictions = batch_text_detection([image], det_model, det_processor)

    if not predictions or len(predictions) == 0:
        print("No text regions detected")
        return []

    pred = predictions[0]
    print(f"Found {len(pred.bboxes)} text regions")

    if len(pred.bboxes) == 0:
        print("No bounding boxes found")
        return []

    # Step 2: Extract image slices for each detected region
    slices = []
    for bbox in pred.bboxes:
        # Get the bounding box coordinates
        x1, y1, x2, y2 = int(bbox.bbox[0]), int(bbox.bbox[1]), int(bbox.bbox[2]), int(bbox.bbox[3])

        # Ensure coordinates are valid
        x1, x2 = max(0, x1), min(image.width, x2)
        y1, y2 = max(0, y1), min(image.height, y2)

        # Crop the image to the bounding box
        if x2 > x1 and y2 > y1:
            cropped = image.crop((x1, y1, x2, y2))
            slices.append(cropped)

    if not slices:
        print("No valid image slices extracted")
        return []

    print(f"Extracted {len(slices)} image slices")

    # Step 3: Recognize text in each slice
    # CRITICAL: We need one language per slice!
    # For German documents, we'll use "de" for all slices
    langs = ["de"] * len(slices)

    print(f"Running recognition with {len(langs)} language codes for {len(slices)} slices")
    try:
        rec_predictions, confidence_scores = batch_recognition(slices, langs, rec_model, rec_processor)

        # Extract text from predictions
        extracted_text = []
        for i, (pred_text, conf) in enumerate(zip(rec_predictions, confidence_scores)):
            if pred_text and pred_text.text:
                print(f"  Region {i+1}: {pred_text.text} (conf: {conf:.2f})")
                extracted_text.append(pred_text.text)

        return extracted_text

    except Exception as e:
        print(f"Recognition failed: {e}")
        import traceback
        traceback.print_exc()
        return []

# Test with German documents
print("\n" + "="*60)
print("TEST 1: German Umlauts Document")
print("="*60)

umlaut_path = Path("test_documents/test_umlauts.png")
if umlaut_path.exists():
    umlaut_text = process_with_surya(umlaut_path)

    if umlaut_text:
        full_text = " ".join(umlaut_text)
        print(f"\nFull text: {full_text}")

        # Check for German characters
        german_chars = ['ä', 'ö', 'ü', 'Ä', 'Ö', 'Ü', 'ß']
        found_chars = [char for char in german_chars if char in full_text]

        if found_chars:
            print(f"[OK] German characters found: {', '.join(found_chars)}")
        else:
            print("[WARNING] No German special characters detected")

print("\n" + "="*60)
print("TEST 2: German Invoice")
print("="*60)

invoice_path = Path("test_documents/test_invoice.png")
if invoice_path.exists():
    invoice_text = process_with_surya(invoice_path)

    if invoice_text:
        print("\nFirst 5 lines of invoice:")
        for line in invoice_text[:5]:
            print(f"  - {line}")

print("\n" + "="*60)
print("SUMMARY")
print("="*60)
print("Key finding: Surya needs one language code PER TEXT REGION")
print("Solution: Detect regions first, then provide matching language array")
print("\n[OK] Test completed!")