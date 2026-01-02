# -*- coding: utf-8 -*-
"""
Teste ALLE OCR Backends auf einer Testdatei.
"""
import asyncio
import sys
import os
import time

# Windows encoding fix
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
logger = structlog.get_logger(__name__)

TEST_FILE = "C:/Users/benfi/Ablage_System/Trainings_Data/UP000000/0000000B.TIF"


async def test_doctr():
    """Test DocTR."""
    print("\n" + "="*60)
    print("TESTE: DocTR (CPU)")
    print("="*60)
    try:
        from app.agents.ocr.doctr_agent import DocTRAgent
        agent = DocTRAgent()
        start = time.perf_counter()
        result = await agent.process({"image_path": TEST_FILE, "language": "de"})
        elapsed = time.perf_counter() - start

        if result.get("success") and result.get("text"):
            text = result["text"]
            print(f"OK - {elapsed:.1f}s - {len(text)} Zeichen")
            print(f"Confidence: {result.get('confidence', 0):.1%}")
            print(f"Text (erste 300 Zeichen):\n{text[:300]}...")
            return {"backend": "DocTR", "success": True, "time": elapsed, "chars": len(text)}
        else:
            print(f"FEHLER: {result.get('error', 'Kein Text')}")
            return {"backend": "DocTR", "success": False, "error": result.get('error')}
    except Exception as e:
        print(f"EXCEPTION: {e}")
        return {"backend": "DocTR", "success": False, "error": str(e)}


async def test_paddleocr():
    """Test PaddleOCR."""
    print("\n" + "="*60)
    print("TESTE: PaddleOCR (CPU)")
    print("="*60)
    try:
        from app.agents.ocr.paddle_ocr_agent import PaddleOCRAgent
        agent = PaddleOCRAgent()
        start = time.perf_counter()
        result = await agent.process({"image_path": TEST_FILE, "language": "de"})
        elapsed = time.perf_counter() - start

        if result.get("success") and result.get("text"):
            text = result["text"]
            print(f"OK - {elapsed:.1f}s - {len(text)} Zeichen")
            print(f"Confidence: {result.get('confidence', 0):.1%}")
            print(f"Text (erste 300 Zeichen):\n{text[:300]}...")
            return {"backend": "PaddleOCR", "success": True, "time": elapsed, "chars": len(text)}
        else:
            print(f"FEHLER: {result.get('error', 'Kein Text')}")
            return {"backend": "PaddleOCR", "success": False, "error": result.get('error')}
    except Exception as e:
        print(f"EXCEPTION: {e}")
        return {"backend": "PaddleOCR", "success": False, "error": str(e)}


async def test_surya():
    """Test Surya CPU."""
    print("\n" + "="*60)
    print("TESTE: Surya (CPU)")
    print("="*60)
    try:
        from app.agents.ocr.surya_docling_agent import SuryaDoclingAgent
        agent = SuryaDoclingAgent()
        start = time.perf_counter()
        result = await agent.process({"image_path": TEST_FILE, "language": "de"})
        elapsed = time.perf_counter() - start

        if result.get("success") and result.get("text"):
            text = result["text"]
            print(f"OK - {elapsed:.1f}s - {len(text)} Zeichen")
            print(f"Confidence: {result.get('confidence', 0):.1%}")
            print(f"Text (erste 300 Zeichen):\n{text[:300]}...")
            return {"backend": "Surya", "success": True, "time": elapsed, "chars": len(text)}
        else:
            print(f"FEHLER: {result.get('error', 'Kein Text')}")
            return {"backend": "Surya", "success": False, "error": result.get('error')}
    except Exception as e:
        print(f"EXCEPTION: {e}")
        return {"backend": "Surya", "success": False, "error": str(e)}


async def test_got_ocr():
    """Test GOT-OCR 2.0."""
    print("\n" + "="*60)
    print("TESTE: GOT-OCR 2.0 (GPU)")
    print("="*60)
    try:
        import torch
        if not torch.cuda.is_available():
            print("SKIP - Keine GPU verfuegbar")
            return {"backend": "GOT-OCR", "success": False, "error": "No GPU"}

        from app.agents.ocr.got_ocr_agent import GOTOCRAgent
        agent = GOTOCRAgent()
        start = time.perf_counter()
        result = await agent.process({"image_path": TEST_FILE, "language": "de"})
        elapsed = time.perf_counter() - start

        if result.get("success") and result.get("text"):
            text = result["text"]
            print(f"OK - {elapsed:.1f}s - {len(text)} Zeichen")
            print(f"Confidence: {result.get('confidence', 0):.1%}")
            print(f"Text (erste 300 Zeichen):\n{text[:300]}...")
            return {"backend": "GOT-OCR", "success": True, "time": elapsed, "chars": len(text)}
        else:
            print(f"FEHLER: {result.get('error', 'Kein Text')}")
            return {"backend": "GOT-OCR", "success": False, "error": result.get('error')}
    except Exception as e:
        print(f"EXCEPTION: {e}")
        return {"backend": "GOT-OCR", "success": False, "error": str(e)}
    finally:
        try:
            import torch
            torch.cuda.empty_cache()
        except:
            pass


async def test_deepseek():
    """Test DeepSeek-Janus-Pro."""
    print("\n" + "="*60)
    print("TESTE: DeepSeek-Janus-Pro (GPU)")
    print("="*60)
    try:
        import torch
        if not torch.cuda.is_available():
            print("SKIP - Keine GPU verfuegbar")
            return {"backend": "DeepSeek", "success": False, "error": "No GPU"}

        from app.agents.ocr.deepseek_agent import DeepseekOCRAgent
        agent = DeepseekOCRAgent()
        start = time.perf_counter()
        result = await agent.process({"image_path": TEST_FILE, "language": "de"})
        elapsed = time.perf_counter() - start

        if result.get("success") and result.get("text"):
            text = result["text"]
            print(f"OK - {elapsed:.1f}s - {len(text)} Zeichen")
            print(f"Confidence: {result.get('confidence', 0):.1%}")
            print(f"Text (erste 300 Zeichen):\n{text[:300]}...")
            return {"backend": "DeepSeek", "success": True, "time": elapsed, "chars": len(text)}
        else:
            print(f"FEHLER: {result.get('error', 'Kein Text')}")
            return {"backend": "DeepSeek", "success": False, "error": result.get('error')}
    except Exception as e:
        print(f"EXCEPTION: {e}")
        return {"backend": "DeepSeek", "success": False, "error": str(e)}
    finally:
        try:
            import torch
            torch.cuda.empty_cache()
        except:
            pass


async def main():
    print("="*60)
    print("OCR BACKEND VERGLEICHSTEST")
    print(f"Testdatei: {TEST_FILE}")
    print("="*60)

    if not Path(TEST_FILE).exists():
        print(f"FEHLER: Testdatei nicht gefunden!")
        return

    results = []

    # CPU Backends zuerst (schneller)
    results.append(await test_doctr())
    results.append(await test_paddleocr())
    results.append(await test_surya())

    # GPU Backends
    results.append(await test_got_ocr())
    results.append(await test_deepseek())

    # Zusammenfassung
    print("\n" + "="*60)
    print("ZUSAMMENFASSUNG")
    print("="*60)

    working = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]

    print(f"\nFunktionierend: {len(working)}/{len(results)}")
    for r in working:
        print(f"  - {r['backend']}: {r['time']:.1f}s, {r['chars']} Zeichen")

    print(f"\nFehlgeschlagen: {len(failed)}/{len(results)}")
    for r in failed:
        print(f"  - {r['backend']}: {r.get('error', 'Unbekannter Fehler')[:50]}")


if __name__ == "__main__":
    asyncio.run(main())
