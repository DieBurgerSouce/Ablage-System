# -*- coding: utf-8 -*-
"""
Test PaddleOCR in Docker - bypasses Windows OneDNN bug.
"""
import asyncio
import time
import os
import sys

# Set encoding for Windows compatibility
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

TEST_FILE = "/app/test_images/0000000B.TIF"


def test_paddleocr():
    """Test PaddleOCR direkt."""
    print("\n" + "="*60)
    print("TESTE: PaddleOCR (CPU) - Linux/Docker")
    print("="*60)
    try:
        from paddleocr import PaddleOCR
        from PIL import Image
        import numpy as np

        start = time.perf_counter()

        # Load model (multilingual with German)
        ocr = PaddleOCR(
            use_angle_cls=True,
            lang='german',
            use_gpu=False,
            show_log=False,
        )

        # Load image
        img = Image.open(TEST_FILE).convert('RGB')
        img_np = np.array(img)

        # OCR
        result = ocr.ocr(img_np, cls=True)

        # Extract text
        text_lines = []
        total_conf = 0.0
        word_count = 0

        if result and result[0]:
            for line in result[0]:
                text_lines.append(line[1][0])
                total_conf += line[1][1]
                word_count += 1

        text = '\n'.join(text_lines)
        confidence = total_conf / word_count if word_count > 0 else 0.0
        elapsed = time.perf_counter() - start

        if text:
            print(f"OK - {elapsed:.1f}s - {len(text)} Zeichen - {confidence:.1%} Confidence")
            print(f"\nText (erste 500 Zeichen):\n{text[:500]}...")

            # Save result for comparison
            with open("/app/results/paddleocr_result.txt", "w", encoding="utf-8") as f:
                f.write(f"Backend: PaddleOCR\n")
                f.write(f"Time: {elapsed:.1f}s\n")
                f.write(f"Characters: {len(text)}\n")
                f.write(f"Confidence: {confidence:.1%}\n")
                f.write(f"Word Count: {word_count}\n")
                f.write(f"\n{'='*60}\n")
                f.write(f"FULL TEXT:\n")
                f.write(f"{'='*60}\n")
                f.write(text)

            return {"backend": "PaddleOCR", "success": True, "time": elapsed, "chars": len(text), "confidence": confidence}
        else:
            print("FEHLER: Kein Text extrahiert")
            return {"backend": "PaddleOCR", "success": False, "error": "Kein Text"}

    except Exception as e:
        print(f"EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return {"backend": "PaddleOCR", "success": False, "error": str(e)}


if __name__ == "__main__":
    print("="*60)
    print("PADDLEOCR DOCKER TEST")
    print(f"Testdatei: {TEST_FILE}")
    print("="*60)

    result = test_paddleocr()

    print("\n" + "="*60)
    print("ERGEBNIS")
    print("="*60)
    print(result)
