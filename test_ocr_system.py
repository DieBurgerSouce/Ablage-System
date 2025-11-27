#!/usr/bin/env python3
"""
Test script for Ablage-System OCR
Tests all OCR backends and routing logic

Usage:
    python test_ocr_system.py [--image path/to/image.jpg]
"""

import asyncio
import argparse
import sys
from pathlib import Path
from PIL import Image
import json

# Add app to path
sys.path.append(str(Path(__file__).parent))

from app.agents.ocr.deepseek_agent import DeepSeekAgent
from app.agents.ocr.got_ocr_agent import GOTOCRAgent
from app.agents.ocr.surya_docling_agent import SuryaDoclingAgent
from Execution_Layer.routers.ocr_router import OCRRouter, DocumentAnalysis, BackendType


async def test_backend(backend_name: str, agent, image_path: str):
    """Test a single OCR backend."""
    print(f"\n{'='*60}")
    print(f"Testing {backend_name}")
    print('='*60)

    try:
        # Prepare input
        input_data = {
            "document_id": f"test_{backend_name}",
            "image_path": image_path,
            "language": "de",
            "options": {
                "extract_tables": True,
                "extract_entities": True,
                "output_format": "markdown" if backend_name == "GOT-OCR" else None
            }
        }

        # Process
        print(f"Processing image: {image_path}")
        result = await agent.process(input_data)

        # Display results
        print(f"\n✅ Success!")
        print(f"Backend: {result.get('backend', backend_name)}")
        print(f"Confidence: {result.get('confidence', 'N/A')}")
        print(f"Processing time: {result.get('processing_time_ms', 'N/A')}ms")
        print(f"Text length: {len(result.get('text', ''))} characters")

        # Show first 500 chars of extracted text
        text = result.get('text', '')
        if text:
            print(f"\nExtracted text (first 500 chars):")
            print('-'*40)
            print(text[:500])
            if len(text) > 500:
                print("... [truncated]")

        return result

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_routing_logic():
    """Test the intelligent routing logic."""
    print(f"\n{'='*60}")
    print("Testing Routing Logic")
    print('='*60)

    # Initialize router (without actual backends for logic testing)
    router = OCRRouter()

    # Test scenarios
    test_cases = [
        {
            "name": "Formula Document",
            "analysis": DocumentAnalysis(
                has_formulas=True,
                has_tables=False,
                document_type="scientific"
            ),
            "expected": BackendType.GOT_OCR
        },
        {
            "name": "Complex Multimodal",
            "analysis": DocumentAnalysis(
                requires_image_understanding=True,
                has_handwriting=True,
                has_complex_layout=True
            ),
            "expected": BackendType.JANUS_PRO
        },
        {
            "name": "Structured Invoice",
            "analysis": DocumentAnalysis(
                is_structured_pdf=True,
                document_type="invoice",
                has_tables=True
            ),
            "expected": BackendType.SURYA_DOCLING
        },
        {
            "name": "Multi-Language Document",
            "analysis": DocumentAnalysis(
                languages=["de", "en", "fr"],
                has_complex_layout=True
            ),
            "expected": BackendType.SURYA_DOCLING
        },
        {
            "name": "Simple Scanned Document",
            "analysis": DocumentAnalysis(
                is_scanned=True,
                languages=["de"]
            ),
            "expected": BackendType.GOT_OCR  # Prefer GPU for speed
        }
    ]

    for test in test_cases:
        print(f"\nTest: {test['name']}")
        print(f"Document characteristics: {test['analysis'].model_dump_json(indent=2)}")

        selected = router.select_backend(test['analysis'])
        expected = test['expected']

        if selected == expected:
            print(f"✅ Correct! Selected: {selected.value}")
        else:
            print(f"❌ Mismatch! Expected: {expected.value}, Got: {selected.value}")

    # Test fallback chain
    print("\n\nTesting Fallback Chain:")
    primary = BackendType.JANUS_PRO
    chain = router._get_fallback_chain(primary)
    print(f"Primary backend: {primary.value}")
    print(f"Fallback chain: {' → '.join([b.value for b in chain])}")


async def create_test_image(output_path: str):
    """Create a simple test image with German text."""
    from PIL import Image, ImageDraw, ImageFont

    # Create image
    img = Image.new('RGB', (800, 600), color='white')
    draw = ImageDraw.Draw(img)

    # Add German text
    test_text = """
    Testdokument für Ablage-System OCR

    Datum: 26.11.2025
    Betreff: Überprüfung der Texterkennung

    Dies ist ein Testdokument mit deutschen Umlauten:
    - Äpfel und Übungen
    - Größe und Straße
    - Müller GmbH & Co. KG

    Rechnungsnummer: 2025-001234
    Betrag: 1.234,56 €
    USt-IdNr: DE123456789

    Mit freundlichen Grüßen
    Max Mustermann
    """

    # Try to use a font, fallback to default if not available
    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except:
        font = ImageFont.load_default()

    # Draw text
    y_position = 50
    for line in test_text.strip().split('\n'):
        draw.text((50, y_position), line.strip(), fill='black', font=font)
        y_position += 25

    # Save image
    img.save(output_path)
    print(f"Created test image: {output_path}")


async def main():
    """Main test function."""
    parser = argparse.ArgumentParser(description='Test Ablage-System OCR')
    parser.add_argument('--image', type=str, help='Path to test image')
    parser.add_argument('--create-test-image', action='store_true',
                       help='Create a test image')
    parser.add_argument('--test-routing', action='store_true',
                       help='Test routing logic only')
    parser.add_argument('--backend', type=str,
                       choices=['deepseek', 'got', 'surya', 'all'],
                       default='all',
                       help='Which backend to test')

    args = parser.parse_args()

    # Test routing logic
    if args.test_routing:
        await test_routing_logic()
        return

    # Create test image if needed
    test_image_path = args.image or "test_german_document.png"

    if args.create_test_image or not Path(test_image_path).exists():
        await create_test_image(test_image_path)

    if not Path(test_image_path).exists():
        print(f"Error: Image not found: {test_image_path}")
        return

    # Initialize backends
    backends = {}

    if args.backend in ['surya', 'all']:
        print("Initializing Surya backend...")
        backends['surya'] = SuryaDoclingAgent()

    if args.backend in ['got', 'all']:
        print("Initializing GOT-OCR backend...")
        backends['got'] = GOTOCRAgent()

    if args.backend in ['deepseek', 'all']:
        print("Initializing DeepSeek backend...")
        backends['deepseek'] = DeepSeekAgent()

    # Test each backend
    results = {}
    for name, agent in backends.items():
        result = await test_backend(name.upper(), agent, test_image_path)
        if result:
            results[name] = result

    # Summary
    if results:
        print(f"\n{'='*60}")
        print("Summary")
        print('='*60)
        for backend, result in results.items():
            print(f"\n{backend.upper()}:")
            print(f"  - Success: ✅")
            print(f"  - Confidence: {result.get('confidence', 'N/A')}")
            print(f"  - Processing time: {result.get('processing_time_ms', 'N/A')}ms")
            print(f"  - Text extracted: {len(result.get('text', ''))} chars")

    # Test router with actual backends (if all backends tested)
    if args.backend == 'all' and len(backends) == 3:
        print(f"\n{'='*60}")
        print("Testing Complete Router with Backends")
        print('='*60)

        router = OCRRouter(
            surya_client=backends.get('surya'),
            got_client=backends.get('got'),
            janus_client=backends.get('deepseek')
        )

        # Test document analysis and routing
        analysis = DocumentAnalysis(
            has_tables=True,
            languages=["de"],
            is_scanned=True,
            document_type="invoice"
        )

        selected_backend = router.select_backend(analysis)
        print(f"For invoice with tables, selected: {selected_backend.value}")

        # Test processing with fallback
        print("\nTesting processing with fallback...")
        try:
            with open(test_image_path, 'rb') as f:
                image_bytes = f.read()

            result = await router.process_with_fallback(
                image_bytes=image_bytes,
                analysis=analysis,
                options={"language": "de"}
            )

            print(f"✅ Processing successful!")
            print(f"Backend used: {result.get('backend_used')}")
            print(f"Text extracted: {len(result.get('text', ''))} chars")

        except Exception as e:
            print(f"❌ Error in router processing: {e}")

    print("\n✨ Test completed!")


if __name__ == "__main__":
    asyncio.run(main())