# -*- coding: utf-8 -*-
"""Banking Utilities.

Hilfsfunktionen fuer Banking-Services:
- IBAN-Maskierung fuer sichere Logs
- Formatierungsfunktionen
"""

from typing import Optional


def mask_iban(iban: Optional[str]) -> str:
    """Maskiert IBAN fuer sichere Log-Ausgaben.

    Zeigt nur Laendercode und letzte 4 Ziffern.
    Beispiel: DE89370400440532013000 -> DE89***...***3000

    Args:
        iban: Die zu maskierende IBAN

    Returns:
        Maskierte IBAN oder '***' bei ungueltigem Input
    """
    if not iban or len(iban) < 8:
        return "***"
    return f"{iban[:4]}***...***{iban[-4:]}"


def mask_account_number(account_number: Optional[str]) -> str:
    """Maskiert Kontonummer fuer sichere Log-Ausgaben.

    Zeigt nur letzte 4 Ziffern.
    Beispiel: 0532013000 -> ******3000

    Args:
        account_number: Die zu maskierende Kontonummer

    Returns:
        Maskierte Kontonummer oder '***' bei ungueltigem Input
    """
    if not account_number or len(account_number) < 4:
        return "***"
    return f"{'*' * (len(account_number) - 4)}{account_number[-4:]}"


def mask_bic(bic: Optional[str]) -> str:
    """Maskiert BIC/SWIFT-Code fuer sichere Log-Ausgaben.

    Zeigt nur Bankcode (erste 4 Zeichen).
    Beispiel: COBADEFFXXX -> COBA*******

    Args:
        bic: Der zu maskierende BIC

    Returns:
        Maskierter BIC oder '***' bei ungueltigem Input
    """
    if not bic or len(bic) < 4:
        return "***"
    return f"{bic[:4]}{'*' * (len(bic) - 4)}"
