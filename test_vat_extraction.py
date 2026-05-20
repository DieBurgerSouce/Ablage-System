# -*- coding: utf-8 -*-
"""
Schnelltest fuer VAT-ID Extraktion.

Testet die neue intelligente USt-IdNr Zuordnung.
"""

import asyncio
import sys
from pathlib import Path

# Projekt-Root zum Path hinzufuegen
sys.path.insert(0, str(Path(__file__).parent))


async def test_vat_extraction(text: str) -> None:
    """Testet die VAT-ID Extraktion aus gegebenem Text."""
    from app.services.structured_extraction_service import StructuredExtractionService

    print("=" * 60)
    print("VAT-ID EXTRAKTION TEST")
    print("=" * 60)

    service = StructuredExtractionService()
    result = await service.extract(text)

    print(f"\nDokumenttyp: {result.classification.document_type}")
    print(f"Konfidenz: {result.classification.confidence:.1%}")

    if result.invoice:
        print("\n--- INVOICE DATA ---")
        print(f"Rechnungsnummer: {result.invoice.invoice_number}")
        print(f"Rechnungsdatum: {result.invoice.invoice_date}")
        print(f"Nettobetrag: {result.invoice.net_amount}")
        print(f"Bruttobetrag: {result.invoice.gross_amount}")

        print("\n--- VAT-ID ZUORDNUNG (NEU!) ---")
        print(f"Sender VAT-ID:    {result.invoice.sender_vat_id}")
        print(f"Recipient VAT-ID: {result.invoice.recipient_vat_id}")

        print("\n--- NEUE FELDER ---")
        print(f"Lieferbedingungen: {result.invoice.delivery_terms}")
        print(f"Reverse Charge:    {result.invoice.is_reverse_charge}")
        print(f"RC Hinweis:        {result.invoice.reverse_charge_note}")
        print(f"VAT Exemption:     {getattr(result.invoice, 'vat_exemption_reason', None)}")
        print(f"Intra-Community:   {getattr(result.invoice, 'intra_community_supply', False)}")

        print("\n--- BANKDATEN (NEU!) ---")
        if result.invoice.sender_bank:
            print(f"IBAN:              {result.invoice.sender_bank.iban}")
            print(f"BIC:               {result.invoice.sender_bank.bic}")
        else:
            print("Keine Bankdaten extrahiert")

        if result.invoice.sender:
            print(f"\nAbsender: {result.invoice.sender.company}, {result.invoice.sender.city}")
        if result.invoice.recipient:
            print(f"Empfaenger: {result.invoice.recipient.company}, {result.invoice.recipient.city}")

    # Alle gefundenen VAT-IDs anzeigen
    if result.vat_ids:
        print(f"\n--- ALLE GEFUNDENEN VAT-IDs ---")
        for vat in result.vat_ids:
            print(f"  - {vat}")

    print("\n" + "=" * 60)


def main() -> None:
    """Hauptfunktion."""
    # ALPAC-Rechnungstext (simuliert OCR-Output) - MIT IBAN UND BIC!
    alpac_text = """
    ALPAC
    kunststof bakken en pallets

    Sales - Invoice
    Alpac - kunststof bakken en pallets BV
    Van der Landeweg 6
    7418 HG Deventer

    Phone No.: +31(0)570-827880
    Fax No.: +31(0)570-624196

    VAT Registration No.: NL820594829B01

    Bank: ING Bank Amsterdam
    IBAN: NL51 INGB 0658010921
    BIC: INGBNL2A

    Bill-to Customer No.: 001808

    Stanzgewerbeverband Firmenich
    Altena-Blaegon-Str. 11
    D-42719 Solingen
    Duitsland

    VAT Registration No.: DE200053646

    Payment Terms: Netto 10 dagen

    6. April 2020

    No.  Description                  Quantity Measure  Unit Price  Amount
    OM-0332.00  DeckPallet 500 x 300 x 200 mm    384 Pieces    3,40    1.305,60
    HDPE, 0.6 A

    Total EUR                                                    1.305,60

    Intra-Community supply - VAT reverse charged

    Van der Landeweg 6, tel. +31 (0)570 - 62 78 80
    7418 HG Deventer, tel. +31 (0)570 - 62 41 84
    """

    print("\nStarte Test mit ALPAC-Rechnungstext...\n")
    asyncio.run(test_vat_extraction(alpac_text))

    print("\n[INFO] Test abgeschlossen!")
    print("[INFO] Starte jetzt das Backend mit: uvicorn app.main:app --reload")


if __name__ == "__main__":
    main()
