#!/usr/bin/env python3
"""Test VAT patterns against OCR text."""
import asyncio
import asyncpg
import re

# Das VAT_ID_NL Pattern aus dem Code
VAT_ID_NL = re.compile(
    r'\b(NL\s?[0-9]{9}\s?B\s?[0-9]{2})\b',
    re.IGNORECASE
)

# DE Pattern
VAT_ID_DE = re.compile(r'\b(DE\s?[0-9]{9})\b', re.IGNORECASE)

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

        print('=== PATTERN TEST ===')

        # NL VAT testen
        nl_matches = VAT_ID_NL.findall(text)
        print(f'VAT_ID_NL Matches: {nl_matches}')

        for m in VAT_ID_NL.finditer(text):
            print(f'  Match: {repr(m.group())} at pos {m.start()}-{m.end()}')
            print(f'  Group 1: {repr(m.group(1))}')
            normalized = re.sub(r'\s', '', m.group(1)).upper()
            print(f'  Normalized: {normalized}, len={len(normalized)}')

        # DE VAT testen
        de_matches = VAT_ID_DE.findall(text)
        print(f'\nVAT_ID_DE Matches: {de_matches}')

        for m in VAT_ID_DE.finditer(text):
            print(f'  Match: {repr(m.group())} at pos {m.start()}-{m.end()}')
            normalized = re.sub(r'\s', '', m.group(1)).upper()
            print(f'  Normalized: {normalized}, len={len(normalized)}')
    else:
        print('No OCR text found!')

    await conn.close()

if __name__ == '__main__':
    asyncio.run(check())
