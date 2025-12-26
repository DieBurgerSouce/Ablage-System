#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test extraction quality for 20 random documents."""

import asyncio
import re
from typing import Optional
from uuid import UUID

# Test document IDs (20 random)
TEST_DOC_IDS = [
    "836e49e8-e849-4845-b050-0061de62d451",
    "27633102-ecf4-4995-bf17-553154d68992",
    "a32c7546-0af4-4471-b4ed-c528343ef3d5",
    "717f0a71-542c-4d83-b6f4-c052e9bf0400",
    "89e0482d-6fb6-41e3-87fb-9f1a6e65150c",
    "d1cbb033-c09b-4ea8-a5ae-0984d19b1350",
    "70df7b0e-ad8a-42ee-b42e-1251ebdfd4cc",
    "c075bc89-27d6-4d36-9785-e9c3e7ed5e23",
    "b8b81ee7-da66-4550-b2c5-377fec929216",
    "1d593a7e-1be8-41ea-af58-7f600073d019",
    "52afd05a-7c7e-47f1-b95a-d691a1a98110",
    "81f833f0-38d6-44d4-9815-4aac26cbe201",
    "87958959-440a-4e88-bf02-48e2096d7eac",
    "d645ac37-f993-4b27-81cb-6603eca5728e",
    "565b2baa-fe67-44df-a39f-17142cdb3fd4",
    "dcfa997c-7226-40ba-97be-165c919b181c",
    "7d8a6fb6-9300-45c3-84c3-e0bf3ee0300b",
    "ed45c734-f802-4802-a808-45faa98975e2",
    "2b9cb78c-3bfd-4d77-908f-87ea2b9224db",
    "d164e4f8-a415-4166-bc14-dbb31f78a5a1",
]


def validate_vat_id(vat_id: Optional[str]) -> tuple[bool, str]:
    """Validiere USt-IdNr und gib (valid, reason) zurück."""
    if not vat_id:
        return True, "keine VAT-ID"  # Kein Fehler wenn keine VAT-ID

    # Liste von ungültigen Werten (Farben, Wörter, etc.)
    invalid_patterns = [
        r'^[A-ZÄÖÜ]{4,}$',  # Nur Großbuchstaben ohne Zahlen (SILBERGRAU, BLAU, etc.)
        r'^[a-zäöüß]{4,}$',  # Nur Kleinbuchstaben
        r'silber|grau|blau|rot|schwarz|weiß|grün',  # Farbnamen
        r'^\d{2}[.\-/]\d{2}[.\-/]\d{2,4}$',  # Datum-Format
    ]

    for pattern in invalid_patterns:
        if re.search(pattern, vat_id, re.IGNORECASE):
            return False, f"ungültige VAT-ID: '{vat_id}'"

    # Gültiges Format prüfen: DE123456789, ATU12345678, etc.
    valid_formats = [
        r'^DE\d{9}$',  # Deutschland
        r'^AT[UZ]\d{8}$',  # Österreich
        r'^NL\d{9}B\d{2}$',  # Niederlande
        r'^BE[01]\d{9}$',  # Belgien
        r'^FR[A-Z0-9]{2}\d{9}$',  # Frankreich
        r'^[A-Z]{2}[A-Z0-9]{5,15}$',  # Allgemeines EU-Format
    ]

    for fmt in valid_formats:
        if re.match(fmt, vat_id):
            return True, f"gültig: {vat_id}"

    # Wenn es mit Länderkennzeichen beginnt aber nicht matcht
    if re.match(r'^[A-Z]{2}', vat_id):
        return True, f"möglicherweise gültig: {vat_id}"

    return False, f"unbekanntes Format: '{vat_id}'"


def validate_date(date_str: Optional[str]) -> tuple[bool, str]:
    """Validiere Datumsformat."""
    if not date_str:
        return False, "FEHLT"

    # ISO Format: 2024-01-15
    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        return True, date_str

    # Deutsches Format: 15.01.2024
    if re.match(r'^\d{1,2}\.\d{1,2}\.\d{4}$', date_str):
        return True, date_str

    return False, f"ungültig: '{date_str}'"


def check_address_swap(sender: dict, recipient: dict) -> tuple[bool, str]:
    """Prüfe ob Sender und Empfänger vertauscht sein könnten."""
    sender_name = sender.get('name', '') if sender else ''
    recipient_name = recipient.get('name', '') if recipient else ''

    if not sender_name and not recipient_name:
        return False, "beide fehlen"

    if sender_name == recipient_name and sender_name:
        return False, f"IDENTISCH: '{sender_name[:30]}'"

    return True, "unterschiedlich"


async def test_extraction_for_document(doc_id: str) -> dict:
    """Teste Extraktion für ein einzelnes Dokument."""
    from app.db.session import get_async_session_context
    from app.db.models import Document
    from app.services.structured_extraction_service import StructuredExtractionService
    from sqlalchemy import select

    async with get_async_session_context() as session:
        # Dokument laden
        result = await session.execute(
            select(Document).where(Document.id == doc_id)
        )
        doc = result.scalar_one_or_none()

        if not doc:
            return {"error": "Dokument nicht gefunden", "doc_id": doc_id}

        ocr_text = doc.extracted_text
        if not ocr_text:
            return {"error": "Kein OCR-Text", "doc_id": doc_id}

        # Extraktion durchführen
        service = StructuredExtractionService()
        data = service.extract_all(ocr_text)

        # Validierungen
        date_valid, date_msg = validate_date(data.get('invoice_date'))
        sender_vat_valid, sender_vat_msg = validate_vat_id(
            data.get('sender', {}).get('vat_id') if data.get('sender') else None
        )
        recipient_vat_valid, recipient_vat_msg = validate_vat_id(
            data.get('recipient', {}).get('vat_id') if data.get('recipient') else None
        )
        addr_valid, addr_msg = check_address_swap(
            data.get('sender', {}),
            data.get('recipient', {})
        )

        return {
            "doc_id": doc_id[:8],
            "filename": doc.original_filename,
            "invoice_date": date_msg,
            "date_ok": date_valid,
            "sender_vat": sender_vat_msg,
            "sender_vat_ok": sender_vat_valid,
            "recipient_vat": recipient_vat_msg,
            "recipient_vat_ok": recipient_vat_valid,
            "address": addr_msg,
            "address_ok": addr_valid,
            "has_line_items": len(data.get('line_items', [])) > 0,
        }


async def main():
    """Hauptfunktion: Teste alle 20 Dokumente."""
    print("=" * 80)
    print("EXTRAKTIONSQUALITÄTSTEST - 20 DOKUMENTE")
    print("=" * 80)
    print()

    results = []
    errors_date = 0
    errors_vat = 0
    errors_addr = 0

    for i, doc_id in enumerate(TEST_DOC_IDS, 1):
        print(f"[{i:2}/20] Teste {doc_id[:8]}...", end=" ")
        try:
            result = await test_extraction_for_document(doc_id)
            results.append(result)

            # Fehler zählen
            if not result.get('date_ok'):
                errors_date += 1
            if not result.get('sender_vat_ok') or not result.get('recipient_vat_ok'):
                errors_vat += 1
            if not result.get('address_ok'):
                errors_addr += 1

            # Status-Symbol
            status = "✓" if (result.get('date_ok') and result.get('address_ok')) else "✗"
            print(f"{status} {result.get('invoice_date', 'N/A')}")

        except Exception as e:
            print(f"FEHLER: {e}")
            results.append({"doc_id": doc_id[:8], "error": str(e)})

    # Zusammenfassung
    print()
    print("=" * 80)
    print("ZUSAMMENFASSUNG")
    print("=" * 80)
    print(f"Gesamt:          {len(results)} Dokumente")
    print(f"Datum-Fehler:    {errors_date}/20")
    print(f"VAT-ID-Fehler:   {errors_vat}/20")
    print(f"Adress-Fehler:   {errors_addr}/20")
    print()

    # Details für fehlerhafte Dokumente
    print("FEHLERHAFTE DOKUMENTE:")
    print("-" * 80)
    for r in results:
        if r.get('error') or not r.get('date_ok') or not r.get('address_ok'):
            print(f"\n{r.get('doc_id')} ({r.get('filename', 'N/A')}):")
            if r.get('error'):
                print(f"  FEHLER: {r.get('error')}")
            else:
                print(f"  Datum:    {r.get('invoice_date')}")
                print(f"  Sender:   {r.get('sender_vat')}")
                print(f"  Empfäng.: {r.get('recipient_vat')}")
                print(f"  Adressen: {r.get('address')}")


if __name__ == "__main__":
    asyncio.run(main())
