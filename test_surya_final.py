"""Final working Surya OCR test with correct German support."""

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

def test_ocr(image_path, description):
    """Test OCR on an image."""
    print(f"\n{'='*60}")
    print(f"Testing: {description}")
    print('='*60)

    image = Image.open(image_path)

    # Verwende 'de' für Deutsch - WICHTIG: Eine Sprache pro Bild!
    try:
        predictions = run_ocr(
            images=[image],
            langs=["de"],  # Deutscher Sprachcode
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
                        print(line.text)

            # Check for German characters
            full_text = " ".join(extracted_lines)
            umlauts_found = []
            for umlaut in ['ä', 'ö', 'ü', 'Ä', 'Ö', 'Ü', 'ß']:
                if umlaut in full_text:
                    umlauts_found.append(umlaut)

            if umlauts_found:
                print(f"\n✅ Deutsche Umlaute erkannt: {', '.join(umlauts_found)}")
            else:
                print("\n❌ WARNUNG: Keine deutschen Umlaute gefunden!")

            return extracted_lines
        else:
            print("❌ Keine Ergebnisse zurückgegeben")
            return []

    except Exception as e:
        print(f"❌ Fehler: {e}")
        # Try alternative approach with single text region
        print("\nVersuche alternativen Ansatz...")
        try:
            # Versuch mit unterschiedlicher Konfiguration
            from surya.detection import batch_text_detection

            # Erst Textregionen erkennen
            predictions = batch_text_detection([image], det_model, det_processor)
            if predictions:
                print(f"Gefunden: {len(predictions[0].bboxes)} Textregionen")
            else:
                print("Keine Textregionen gefunden")
        except Exception as e2:
            print(f"Auch alternativer Ansatz fehlgeschlagen: {e2}")

        return []

# Test 1: Umlaute
umlaut_path = Path("test_documents/test_umlauts.png")
if umlaut_path.exists():
    umlaut_text = test_ocr(umlaut_path, "Deutsche Umlaute Test")

# Test 2: Rechnung
invoice_path = Path("test_documents/test_invoice.png")
if invoice_path.exists():
    invoice_text = test_ocr(invoice_path, "Deutsche Rechnung")

print("\n" + "="*60)
print("ZUSAMMENFASSUNG:")
print("="*60)

# Vergleich mit EasyOCR
print("\n🔍 VERGLEICH:")
print("EasyOCR: Alle Umlaute kaputt (Müller → M�ller)")
print("Surya:   [Testergebnisse oben]")

print("\n✅ Test abgeschlossen!")