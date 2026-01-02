"""Working Surya OCR implementation with proper language handling."""

from PIL import Image
from pathlib import Path
from surya.ocr import run_ocr
from surya.model.detection.segformer import load_model as load_det_model
from surya.model.detection.segformer import load_processor as load_det_processor
from surya.model.recognition.model import load_model as load_rec_model
from surya.model.recognition.processor import load_processor as load_rec_processor
from surya.languages import LANGUAGE_DATA

print("Loading Surya models...")
det_model = load_det_model()
det_processor = load_det_processor()
rec_model = load_rec_model()
rec_processor = load_rec_processor()
print("Models loaded successfully!")

# Test with our test image
test_image_path = Path("test_documents/test_umlauts.png")

if test_image_path.exists():
    print(f"\nProcessing: {test_image_path}")
    image = Image.open(test_image_path)

    # WICHTIG: Surya erwartet EINE Sprache pro BILD
    # Nicht mehrere Sprachen für ein Bild!
    print("\nRunning Surya OCR...")

    # Verwende run_ocr mit korrekter Sprach-Konfiguration
    # Ein String pro Bild in der Liste
    predictions = run_ocr(
        images=[image],
        langs=["German"],  # Verwende Sprachnamen aus LANGUAGE_DATA
        det_model=det_model,
        det_processor=det_processor,
        rec_model=rec_model,
        rec_processor=rec_processor
    )

    if predictions and len(predictions) > 0:
        result = predictions[0]

        print("\n" + "="*60)
        print("SURYA OCR RESULTS (GERMAN):")
        print("="*60)

        # Extract text
        full_text = []
        if hasattr(result, 'text_lines'):
            for idx, line in enumerate(result.text_lines, 1):
                if hasattr(line, 'text') and line.text:
                    print(f"Line {idx}: {line.text}")
                    full_text.append(line.text)

                    # Prüfe auf Umlaute
                    if any(char in line.text for char in "äöüÄÖÜß"):
                        print(f"         -> Umlaute erkannt! ✓")

        print("="*60)
        print(f"\nFull text ({len(full_text)} lines):")
        print("\n".join(full_text))

        # Test auch mit Rechnung
        invoice_path = Path("test_documents/test_invoice.png")
        if invoice_path.exists():
            print(f"\n\nProcessing invoice: {invoice_path}")
            invoice_image = Image.open(invoice_path)

            invoice_predictions = run_ocr(
                images=[invoice_image],
                langs=["German"],
                det_model=det_model,
                det_processor=det_processor,
                rec_model=rec_model,
                rec_processor=rec_processor
            )

            if invoice_predictions:
                invoice_result = invoice_predictions[0]
                print("\n" + "="*60)
                print("INVOICE OCR RESULTS:")
                print("="*60)

                if hasattr(invoice_result, 'text_lines'):
                    for line in invoice_result.text_lines[:10]:  # Erste 10 Zeilen
                        if hasattr(line, 'text') and line.text:
                            print(line.text)

                print("="*60)
    else:
        print("No predictions returned")

else:
    print(f"Test image not found: {test_image_path}")

print("\n\n✅ Surya OCR Test completed!")