#!/usr/bin/env python3
"""Check OCR text for VAT IDs and IBANs."""
import asyncio
import asyncpg
import re

async def check():
    conn = await asyncpg.connect(
        host='postgres',
        port=5432,
        user='ablage_admin',
        password='ablage123!secure',
        database='ablage_system'
    )

    row = await conn.fetchrow(
        "SELECT extracted_text FROM documents WHERE id = $1",
        'bf325979-b96f-489f-93c6-fd15083ac97d'
    )

    if row and row['extracted_text']:
        text = row['extracted_text']
        print('=== OCR TEXT (erste 2000 Zeichen) ===')
        print(text[:2000])
        print('\n\n=== SUCHE NACH VAT-IDs ===')

        # NL VAT suchen
        nl_vat = re.findall(r'NL\s?[0-9]{9}\s?B\s?[0-9]{2}', text, re.IGNORECASE)
        print(f'NL VAT-IDs gefunden: {nl_vat}')

        # DE VAT suchen
        de_vat = re.findall(r'DE\s?[0-9]{9}', text, re.IGNORECASE)
        print(f'DE VAT-IDs gefunden: {de_vat}')

        # IBAN suchen
        ibans = re.findall(r'[A-Z]{2}\s?[0-9]{2}\s?(?:[A-Z0-9]{4}\s?){2,7}[A-Z0-9]{0,2}', text)
        print(f'IBANs gefunden: {ibans}')

        # BIC suchen
        bics = re.findall(r'[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?', text)
        print(f'BICs gefunden (erste 5): {bics[:5]}')

        # Prüfen ob "NL" überhaupt im Text vorkommt
        if 'NL' in text.upper():
            print('\n"NL" kommt im Text vor!')
            # Kontext um NL zeigen
            for m in re.finditer(r'.{0,30}NL.{0,30}', text, re.IGNORECASE):
                print(f'  Kontext: {repr(m.group())}')
        else:
            print('\n"NL" kommt NICHT im Text vor!')
    else:
        print('Kein OCR-Text gefunden!')

    await conn.close()

if __name__ == '__main__':
    asyncio.run(check())
