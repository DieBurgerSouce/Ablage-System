"""Direct GPU OCR test to debug text extraction issue."""

import asyncio
import sys
import os
from pathlib import Path
import torch

# Add app directory to path
sys.path.append(str(Path(__file__).parent / "app"))

async def test_gpu_ocr_direct():
    """Test GPU OCR directly without API."""
    print("\n" + "="*60)
    print("DIRECT GPU OCR TEST")
    print("="*60)

    # Check GPU
    print("\n1. GPU Status:")
    if torch.cuda.is_available():
        print(f"[OK] CUDA available: {torch.version.cuda}")
        print(f"[OK] GPU: {torch.cuda.get_device_name(0)}")
        print(f"[OK] VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")

        # Check current memory usage
        allocated = torch.cuda.memory_allocated() / 1024**3
        reserved = torch.cuda.memory_reserved() / 1024**3
        print(f"[OK] Current VRAM usage: {allocated:.2f} GB allocated, {reserved:.2f} GB reserved")
    else:
        print("[ERROR] CUDA not available")
        return

    # Import GPU agent
    print("\n2. Loading GPU Agent...")
    from agents.ocr.surya_gpu_agent import SuryaGPUAgent

    # Create agent
    agent = SuryaGPUAgent()
    print(f"[OK] Agent initialized on {agent.device}")
    print(f"[OK] Using dtype: {agent.dtype}")

    # Test image
    test_image = Path("test_documents/test_umlauts.png")
    if not test_image.exists():
        print(f"[ERROR] Test image not found: {test_image}")
        return

    print(f"\n3. Processing test image: {test_image}")

    # Test with string path directly
    print("\nTest A: String path input")
    result = await agent.process(str(test_image), language="de")

    if result.get("success"):
        print(f"[OK] Success: {result.get('success')}")
        print(f"[OK] Confidence: {result.get('confidence', 0):.1%}")
        print(f"[OK] Text length: {len(result.get('text', ''))} chars")
        print(f"[OK] Backend: {result.get('backend', 'unknown')}")

        # Show first 200 chars of text
        text = result.get('text', '')
        if text:
            print(f"\nExtracted text (first 200 chars):")
            print(f"'{text[:200]}'")

            # Check for German characters
            german_chars = ['ä', 'ö', 'ü', 'Ä', 'Ö', 'Ü', 'ß']
            found = [c for c in german_chars if c in text]
            if found:
                print(f"[OK] German characters found: {', '.join(found)}")
            else:
                print("[ERROR] No German characters found")
        else:
            print("[ERROR] No text extracted!")
    else:
        print(f"[ERROR] Processing failed: {result.get('error', 'Unknown error')}")

    # Test with dict input
    print("\nTest B: Dict input")
    result2 = await agent.process(
        {"image_path": str(test_image), "language": "de"},
        language="de"
    )

    if result2.get("success"):
        print(f"[OK] Dict input worked")
        print(f"[OK] Text length: {len(result2.get('text', ''))} chars")
    else:
        print(f"[ERROR] Dict input failed: {result2.get('error', 'Unknown error')}")

    # Check GPU memory after processing
    print("\n4. GPU Memory Status:")
    allocated = torch.cuda.memory_allocated() / 1024**3
    reserved = torch.cuda.memory_reserved() / 1024**3
    max_allocated = torch.cuda.max_memory_allocated() / 1024**3
    print(f"[OK] Current: {allocated:.2f} GB allocated")
    print(f"[OK] Reserved: {reserved:.2f} GB reserved")
    print(f"[OK] Peak: {max_allocated:.2f} GB max allocated")

    # Cleanup
    agent.cleanup()
    torch.cuda.empty_cache()
    print("\n[OK] Cleanup complete")

if __name__ == "__main__":
    asyncio.run(test_gpu_ocr_direct())