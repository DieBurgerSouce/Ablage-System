"""Test EasyOCR with German text."""

import easyocr
from pathlib import Path
import numpy as np
from PIL import Image

print("Initializing EasyOCR with German and English support...")
# Create reader with German and English support
# verbose=False to avoid unicode progress bar issues on Windows
reader = easyocr.Reader(['de', 'en'], gpu=False, verbose=False)  # CPU-only, no verbose output
print("EasyOCR initialized!")

# Test with our test image
test_image_path = Path("test_documents/test_umlauts.png")

if test_image_path.exists():
    print(f"\nProcessing: {test_image_path}")

    # Read text from image
    results = reader.readtext(str(test_image_path))

    print("\nOCR Results:")
    print("-" * 50)

    # Extract and display text
    full_text = []
    for (bbox, text, prob) in results:
        print(f"{text} (confidence: {prob:.2f})")
        full_text.append(text)

    print("-" * 50)
    print("\nFull extracted text:")
    print(" ".join(full_text))

    # Test with invoice image too
    invoice_path = Path("test_documents/test_invoice.png")
    if invoice_path.exists():
        print(f"\n\nProcessing invoice: {invoice_path}")
        invoice_results = reader.readtext(str(invoice_path))

        print("\nInvoice OCR Results:")
        print("-" * 50)
        for (bbox, text, prob) in invoice_results:
            if prob > 0.5:  # Only show confident results
                print(f"{text} (confidence: {prob:.2f})")
        print("-" * 50)

    print("\nEasyOCR test completed successfully!")

else:
    print(f"Test image not found: {test_image_path}")
    print("Run create_test_image.py first to create test images")