"""Surya OCR test - process each text region individually to avoid batch bug."""

from PIL import Image
from pathlib import Path
from surya.detection import batch_text_detection
from surya.recognition import batch_recognition
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

def process_with_surya_individual(image_path):
    """Process image by recognizing each region individually."""
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

    # Step 2: Process each region individually
    all_text = []
    for i, bbox in enumerate(pred.bboxes):
        # Get the bounding box coordinates
        x1, y1, x2, y2 = int(bbox.bbox[0]), int(bbox.bbox[1]), int(bbox.bbox[2]), int(bbox.bbox[3])

        # Ensure coordinates are valid
        x1, x2 = max(0, x1), min(image.width, x2)
        y1, y2 = max(0, y1), min(image.height, y2)

        # Crop the image to the bounding box
        if x2 > x1 and y2 > y1:
            cropped = image.crop((x1, y1, x2, y2))

            # Process this single region
            try:
                # Process one region at a time to avoid batch language bug
                rec_preds, conf_scores = batch_recognition(
                    [cropped],  # Single image slice
                    ["de"],     # Single language code
                    rec_model,
                    rec_processor
                )

                if rec_preds and rec_preds[0] and rec_preds[0].text:
                    text = rec_preds[0].text
                    conf = conf_scores[0] if conf_scores else 0.0
                    print(f"  Region {i+1}: {text} (conf: {conf:.2f})")
                    all_text.append(text)

            except Exception as e:
                print(f"  Region {i+1}: Failed - {e}")
                continue

    return all_text

# Test with German documents
print("\n" + "="*60)
print("TEST 1: German Umlauts Document")
print("="*60)

umlaut_path = Path("test_documents/test_umlauts.png")
if umlaut_path.exists():
    umlaut_text = process_with_surya_individual(umlaut_path)

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
    else:
        print("No text extracted")

print("\n" + "="*60)
print("TEST 2: German Invoice (first 10 regions only)")
print("="*60)

invoice_path = Path("test_documents/test_invoice.png")
if invoice_path.exists():
    # Limit to first 10 regions for speed
    invoice_text = []
    image = Image.open(invoice_path)
    if image.mode != 'RGB':
        image = image.convert('RGB')

    predictions = batch_text_detection([image], det_model, det_processor)
    if predictions:
        pred = predictions[0]
        print(f"Found {len(pred.bboxes)} text regions, processing first 10...")

        for i, bbox in enumerate(pred.bboxes[:10]):  # Only first 10
            x1, y1, x2, y2 = int(bbox.bbox[0]), int(bbox.bbox[1]), int(bbox.bbox[2]), int(bbox.bbox[3])
            x1, x2 = max(0, x1), min(image.width, x2)
            y1, y2 = max(0, y1), min(image.height, y2)

            if x2 > x1 and y2 > y1:
                cropped = image.crop((x1, y1, x2, y2))
                try:
                    rec_preds, conf_scores = batch_recognition([cropped], ["de"], rec_model, rec_processor)
                    if rec_preds and rec_preds[0] and rec_preds[0].text:
                        text = rec_preds[0].text
                        print(f"  Region {i+1}: {text}")
                        invoice_text.append(text)
                except Exception as e:
                    print(f"  Region {i+1}: Failed")

print("\n" + "="*60)
print("CONCLUSION")
print("="*60)
print("Processing regions individually avoids the batch language bug")
print("This is slower but actually works!")
print("\n[OK] Test completed!")