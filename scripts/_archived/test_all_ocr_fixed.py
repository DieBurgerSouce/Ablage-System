# -*- coding: utf-8 -*-
"""
Teste ALLE OCR Backends auf einer Testdatei - mit korrekten Parametern.
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

TEST_FILE = "C:/Users/benfi/Ablage_System/Trainings_Data/UP000000/0000000B.TIF"


def test_doctr_direct():
    """Test DocTR direkt ohne Agent."""
    print("\n" + "="*60)
    print("TESTE: DocTR (CPU) - DIREKT")
    print("="*60)
    try:
        from doctr.io import DocumentFile
        from doctr.models import ocr_predictor

        start = time.perf_counter()

        # Lade Modell
        model = ocr_predictor(pretrained=True)

        # Lade Dokument mit Dateipfad (das funktioniert!)
        doc = DocumentFile.from_images([TEST_FILE])

        # OCR
        result = model(doc)

        # Extrahiere Text
        text_lines = []
        total_conf = 0.0
        word_count = 0

        for page in result.pages:
            for block in page.blocks:
                for line in block.lines:
                    line_text = ' '.join([word.value for word in line.words])
                    text_lines.append(line_text)
                    for word in line.words:
                        total_conf += word.confidence
                        word_count += 1

        text = '\n'.join(text_lines)
        confidence = total_conf / word_count if word_count > 0 else 0.0
        elapsed = time.perf_counter() - start

        print(f"OK - {elapsed:.1f}s - {len(text)} Zeichen - {confidence:.1%} Confidence")
        print(f"Text (erste 300 Zeichen):\n{text[:300]}...")
        return {"backend": "DocTR", "success": True, "time": elapsed, "chars": len(text), "confidence": confidence}

    except Exception as e:
        print(f"EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return {"backend": "DocTR", "success": False, "error": str(e)}


def test_paddleocr_direct():
    """Test PaddleOCR direkt ohne Agent."""
    print("\n" + "="*60)
    print("TESTE: PaddleOCR (CPU) - DIREKT")
    print("="*60)
    try:
        # Disable OneDNN which causes issues on Windows
        os.environ["FLAGS_use_mkldnn"] = "0"
        os.environ["MKLDNN_CACHE_CAPACITY"] = "0"

        from paddleocr import PaddleOCR
        from PIL import Image
        import numpy as np

        start = time.perf_counter()

        # Lade Modell (multilingual mit German)
        ocr = PaddleOCR(
            use_angle_cls=True,
            lang='german',
            use_gpu=False,
            show_log=False,
            enable_mkldnn=False,  # Disable MKLDNN
        )

        # Lade Bild
        img = Image.open(TEST_FILE).convert('RGB')
        img_np = np.array(img)

        # OCR
        result = ocr.ocr(img_np, cls=True)

        # Extrahiere Text
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
            print(f"Text (erste 300 Zeichen):\n{text[:300]}...")
            return {"backend": "PaddleOCR", "success": True, "time": elapsed, "chars": len(text), "confidence": confidence}
        else:
            print("FEHLER: Kein Text extrahiert")
            return {"backend": "PaddleOCR", "success": False, "error": "Kein Text"}

    except Exception as e:
        print(f"EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
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
            conf = result.get('confidence', 0)
            print(f"OK - {elapsed:.1f}s - {len(text)} Zeichen - {conf:.1%} Confidence")
            print(f"Text (erste 300 Zeichen):\n{text[:300]}...")
            return {"backend": "Surya", "success": True, "time": elapsed, "chars": len(text), "confidence": conf}
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
        # GOT-OCR erwartet document_id
        result = await agent.process({
            "image_path": TEST_FILE,
            "language": "de",
            "document_id": "test-doc-001"
        })
        elapsed = time.perf_counter() - start

        if result.get("success") and result.get("text"):
            text = result["text"]
            conf = result.get('confidence', 0)
            print(f"OK - {elapsed:.1f}s - {len(text)} Zeichen - {conf:.1%} Confidence")
            print(f"Text (erste 300 Zeichen):\n{text[:300]}...")
            return {"backend": "GOT-OCR", "success": True, "time": elapsed, "chars": len(text), "confidence": conf}
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

        # Die Klasse heisst DeepSeekAgent (ohne OCR im Namen)
        from app.agents.ocr.deepseek_agent import DeepSeekAgent
        agent_class = DeepSeekAgent

        agent = agent_class()
        start = time.perf_counter()
        result = await agent.process({"image_path": TEST_FILE, "language": "de"})
        elapsed = time.perf_counter() - start

        if result.get("success") and result.get("text"):
            text = result["text"]
            conf = result.get('confidence', 0)
            print(f"OK - {elapsed:.1f}s - {len(text)} Zeichen - {conf:.1%} Confidence")
            print(f"Text (erste 300 Zeichen):\n{text[:300]}...")
            return {"backend": "DeepSeek", "success": True, "time": elapsed, "chars": len(text), "confidence": conf}
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
    print("OCR BACKEND VERGLEICHSTEST (FIXED)")
    print(f"Testdatei: {TEST_FILE}")
    print("="*60)

    if not Path(TEST_FILE).exists():
        print(f"FEHLER: Testdatei nicht gefunden!")
        return

    results = []

    # CPU Backends zuerst (schneller)
    results.append(test_doctr_direct())
    results.append(test_paddleocr_direct())
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

    print(f"\n{'='*60}")
    print(f"FUNKTIONIEREND: {len(working)}/{len(results)}")
    print(f"{'='*60}")
    for r in working:
        print(f"  {r['backend']:15} | {r['time']:5.1f}s | {r['chars']:5} chars | {r.get('confidence', 0):.0%}")

    print(f"\n{'='*60}")
    print(f"FEHLGESCHLAGEN: {len(failed)}/{len(results)}")
    print(f"{'='*60}")
    for r in failed:
        err = str(r.get('error', 'Unbekannt'))[:60]
        print(f"  {r['backend']:15} | {err}")


if __name__ == "__main__":
    asyncio.run(main())
