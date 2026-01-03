"""Test OCR API with file upload."""

import requests
from pathlib import Path

# API base URL
API_URL = "http://localhost:8000"

# Test file
test_file = Path("test_documents/test_umlauts.png")

if test_file.exists():
    print(f"Testing OCR API with: {test_file}")
    print("-" * 60)

    # Prepare the file upload
    with open(test_file, "rb") as f:
        files = {"file": (test_file.name, f, "image/png")}
        data = {
            "backend": "surya",
            "language": "de",
            "detect_layout": "true"
        }

        # Send OCR request
        print("Sending OCR request...")
        response = requests.post(f"{API_URL}/ocr/process", files=files, data=data)

    # Check response
    if response.status_code == 200:
        result = response.json()
        print(f"Status: SUCCESS")
        print(f"Backend used: {result.get('backend', 'unknown')}")
        print(f"Success: {result.get('success', False)}")
        print(f"Confidence: {result.get('confidence', 0):.1%}")

        # Show extracted text (first 200 chars)
        text = result.get('text', '')
        print(f"\nExtracted text ({len(text)} chars):")
        print("-" * 40)
        print(text[:200] if len(text) > 200 else text)
        print("-" * 40)

        # German validation if present
        if 'german_validation' in result:
            validation = result['german_validation']
            print(f"\nGerman validation:")
            print(f"  Has umlauts: {validation.get('has_umlauts', False)}")
            print(f"  Quality score: {validation.get('quality_score', 0):.1%}")
            if validation.get('dates_found'):
                print(f"  Dates found: {validation.get('dates_found')}")
            if validation.get('amounts_found'):
                print(f"  Amounts found: {validation.get('amounts_found')}")
    else:
        print(f"Status: ERROR ({response.status_code})")
        print(f"Error: {response.text}")

else:
    print(f"Test file not found: {test_file}")