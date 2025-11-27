"""Fixed Surya OCR test - ONE language per image as required by API."""

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

def test_ocr(image_path, lang_code, description):
    """Test OCR with a single language per image."""
    print(f"\n{'='*60}")
    print(f"Testing: {description}")
    print(f"Language: {lang_code}")
    print('='*60)

    image = Image.open(image_path)

    # IMPORTANT: Surya expects exactly ONE language per image in the list
    # For a single image: [image] and [lang]
    # For multiple images: [img1, img2] and [lang1, lang2]
    try:
        predictions = run_ocr(
            images=[image],      # List with one image
            langs=[lang_code],   # List with one language code
            det_model=det_model,
            det_processor=det_processor,
            rec_model=rec_model,
            rec_processor=rec_processor
        )

        if predictions and len(predictions) > 0:
            result = predictions[0]

            # Extract text
            extracted_lines = []
            if hasattr(result, 'text_lines'):
                for line in result.text_lines:
                    if hasattr(line, 'text') and line.text:
                        extracted_lines.append(line.text)
                        print(f"  {line.text}")

            # Check for German characters
            full_text = " ".join(extracted_lines)
            german_chars = ['ä', 'ö', 'ü', 'Ä', 'Ö', 'Ü', 'ß']
            found_chars = [char for char in german_chars if char in full_text]

            if found_chars:
                print(f"\n[OK] German characters detected: {', '.join(found_chars)}")
            else:
                print("\n[WARNING] No German special characters found in text")

            return extracted_lines
        else:
            print("[ERROR] No predictions returned")
            return []

    except Exception as e:
        print(f"[ERROR] OCR failed: {e}")
        import traceback
        traceback.print_exc()
        return []

# Test 1: Umlauts with German
umlaut_path = Path("test_documents/test_umlauts.png")
if umlaut_path.exists():
    print("\n>>> Test 1: German language setting")
    german_text = test_ocr(umlaut_path, "de", "German Umlauts Test")

    # Also try with English to see the difference
    print("\n>>> Test 2: English language setting (for comparison)")
    english_text = test_ocr(umlaut_path, "en", "Same image with English setting")

# Test 2: Invoice
invoice_path = Path("test_documents/test_invoice.png")
if invoice_path.exists():
    print("\n>>> Test 3: German Invoice")
    invoice_text = test_ocr(invoice_path, "de", "German Invoice Document")

print("\n" + "="*60)
print("SUMMARY:")
print("="*60)
print("Key Learning: Surya requires EXACTLY one language per image")
print("Correct usage: run_ocr([image], ['de'], ...)")
print("Wrong usage:   run_ocr([image], ['de', 'en'], ...)")
print("\n[OK] Test completed!")