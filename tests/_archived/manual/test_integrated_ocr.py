#!/usr/bin/env python3
"""Test OCR integration directly without API layer"""

import asyncio
from pathlib import Path
import sys
import structlog

# Add app directory to path
sys.path.append("app")

# Configure structlog for console output
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer()
    ]
)

async def test_surya_directly():
    """Test Surya OCR agent directly"""

    from agents.ocr.surya_docling_agent import SuryaDoclingAgent

    print("Testing Surya OCR Agent Directly")
    print("=" * 60)

    # Initialize agent
    agent = SuryaDoclingAgent()

    # Test image
    test_image = "test_documents/test_umlauts.png"

    if not Path(test_image).exists():
        print(f"ERROR: Test image not found: {test_image}")
        return

    # Prepare input
    input_data = {
        "image_path": test_image,
        "language": "de"
    }

    print(f"Testing with image: {test_image}")
    print("Processing...")

    try:
        # Process directly
        result = await agent.process(input_data)

        # Display results
        print(f"\nResult:")
        print(f"  Success: {result.get('success', False)}")
        print(f"  Model: {result.get('model', 'unknown')}")
        print(f"  Confidence: {result.get('confidence', 0.0):.2%}")

        if result.get('error'):
            print(f"  Error: {result['error']}")

        text = result.get('text', '')
        if text:
            print(f"\nExtracted Text ({len(text)} chars):")
            print("-" * 40)
            print(text[:500] if len(text) > 500 else text)
            print("-" * 40)
        else:
            print("\n  No text extracted")

        # Check pages data
        pages = result.get('pages', [])
        if pages:
            print(f"\n  Pages processed: {len(pages)}")
            for page in pages:
                page_text = page.get('full_text', '')
                if page_text:
                    print(f"    Page {page['page_number']}: {len(page_text)} chars")

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Cleanup
        await agent.cleanup()
        print("\nCleanup complete")

if __name__ == "__main__":
    asyncio.run(test_surya_directly())