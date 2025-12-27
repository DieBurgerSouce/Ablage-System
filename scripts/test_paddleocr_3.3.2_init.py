# -*- coding: utf-8 -*-
"""
Minimal test script to verify PaddleOCR 3.3.2 initialization.
Tests CPU and German language support.
"""
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

def test_paddleocr_3_3_2_init():
    """Test PaddleOCR 3.3.2 initialization with minimal parameters."""
    print("Testing PaddleOCR 3.3.2 initialization...")

    try:
        from paddleocr import PaddleOCR

        # Test 1: Minimal initialization (German)
        print("\n1. Testing minimal initialization with lang='german':")
        ocr = PaddleOCR(lang='german')
        print("   ✅ PaddleOCR initialized successfully")
        print(f"   Type: {type(ocr)}")
        print(f"   Has 'ocr' method: {hasattr(ocr, 'ocr')}")

        # Test 2: Check if old parameters cause errors
        print("\n2. Testing that old parameters are ignored/removed:")
        try:
            # This should work (old params ignored) or fail gracefully
            ocr2 = PaddleOCR(lang='german', use_gpu=False)
            print("   ✅ Old 'use_gpu' parameter ignored (or not present)")
        except TypeError as e:
            if "use_gpu" in str(e) or "Unknown argument" in str(e):
                print(f"   ✅ Old 'use_gpu' parameter correctly rejected: {e}")
            else:
                raise

        try:
            ocr3 = PaddleOCR(lang='german', show_log=False)
            print("   ✅ Old 'show_log' parameter ignored (or not present)")
        except TypeError as e:
            if "show_log" in str(e) or "Unknown argument" in str(e):
                print(f"   ✅ Old 'show_log' parameter correctly rejected: {e}")
            else:
                raise

        try:
            ocr4 = PaddleOCR(lang='german', use_angle_cls=True)
            print("   ✅ Old 'use_angle_cls' parameter ignored (or not present)")
        except TypeError as e:
            if "use_angle_cls" in str(e) or "Unknown argument" in str(e):
                print(f"   ✅ Old 'use_angle_cls' parameter correctly rejected: {e}")
            else:
                raise

        print("\n✅ All initialization tests passed!")
        return True

    except ImportError as e:
        print(f"❌ PaddleOCR not available: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_paddleocr_3_3_2_init()
    sys.exit(0 if success else 1)










