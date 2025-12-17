# -*- coding: utf-8 -*-
"""
Abstrakte Basis fuer Kontenrahmen.

Definiert die Schnittstelle fuer SKR03 und SKR04 Implementierungen.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional


class BaseKontenrahmen(ABC):
    """
    Abstrakte Basis fuer Kontenrahmen.

    Jeder Kontenrahmen definiert Standard-Konten fuer verschiedene
    Buchungstypen (Wareneingang, Erloese, etc.) sowie die Mapping-
    Logik fuer automatische Kontozuordnung.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Name des Kontenrahmens (z.B. 'SKR03')."""
        pass

    @property
    @abstractmethod
    def beschreibung(self) -> str:
        """Kurze Beschreibung des Kontenrahmens."""
        pass

    # =========================================================================
    # AUFWANDSKONTEN (Eingangsrechnungen)
    # =========================================================================

    @abstractmethod
    def get_expense_account(
        self,
        expense_type: str,
        vat_rate: Optional[float] = None
    ) -> str:
        """
        Liefert Standard-Aufwandskonto.

        Args:
            expense_type: Typ des Aufwands (waren, dienstleistung, miete, etc.)
            vat_rate: MwSt-Satz (7 oder 19), optional fuer differenzierte Konten

        Returns:
            Kontonummer als String
        """
        pass

    @property
    @abstractmethod
    def expense_accounts(self) -> Dict[str, str]:
        """
        Alle verfuegbaren Aufwandskonten.

        Returns:
            Dict mit {expense_type: kontonummer}
        """
        pass

    # =========================================================================
    # ERLOESKONTEN (Ausgangsrechnungen)
    # =========================================================================

    @abstractmethod
    def get_revenue_account(
        self,
        revenue_type: str,
        vat_rate: Optional[float] = None
    ) -> str:
        """
        Liefert Standard-Erloeskonto.

        Args:
            revenue_type: Typ des Erloses (waren, dienstleistung, etc.)
            vat_rate: MwSt-Satz (7 oder 19), optional

        Returns:
            Kontonummer als String
        """
        pass

    @property
    @abstractmethod
    def revenue_accounts(self) -> Dict[str, str]:
        """
        Alle verfuegbaren Erloeskonten.

        Returns:
            Dict mit {revenue_type: kontonummer}
        """
        pass

    # =========================================================================
    # PERSONENKONTEN
    # =========================================================================

    @property
    @abstractmethod
    def default_creditor_account(self) -> str:
        """Standard-Kreditorenkonto (Lieferanten)."""
        pass

    @property
    @abstractmethod
    def default_debtor_account(self) -> str:
        """Standard-Debitorenkonto (Kunden)."""
        pass

    @property
    @abstractmethod
    def creditor_range_start(self) -> str:
        """Beginn des Kreditoren-Nummernkreises."""
        pass

    @property
    @abstractmethod
    def creditor_range_end(self) -> str:
        """Ende des Kreditoren-Nummernkreises."""
        pass

    @property
    @abstractmethod
    def debtor_range_start(self) -> str:
        """Beginn des Debitoren-Nummernkreises."""
        pass

    @property
    @abstractmethod
    def debtor_range_end(self) -> str:
        """Ende des Debitoren-Nummernkreises."""
        pass

    # =========================================================================
    # SAMMELKONTEN
    # =========================================================================

    @property
    @abstractmethod
    def sammelkonto_kreditoren(self) -> str:
        """Sammelkonto Kreditoren (Verbindlichkeiten)."""
        pass

    @property
    @abstractmethod
    def sammelkonto_debitoren(self) -> str:
        """Sammelkonto Debitoren (Forderungen)."""
        pass

    # =========================================================================
    # STEUERKONTEN
    # =========================================================================

    @property
    @abstractmethod
    def vorsteuer_19(self) -> str:
        """Vorsteuer 19%."""
        pass

    @property
    @abstractmethod
    def vorsteuer_7(self) -> str:
        """Vorsteuer 7%."""
        pass

    @property
    @abstractmethod
    def umsatzsteuer_19(self) -> str:
        """Umsatzsteuer 19%."""
        pass

    @property
    @abstractmethod
    def umsatzsteuer_7(self) -> str:
        """Umsatzsteuer 7%."""
        pass

    # =========================================================================
    # HILFSMETHODEN
    # =========================================================================

    def get_all_accounts(self) -> Dict[str, Dict[str, str]]:
        """
        Liefert alle Konten als verschachteltes Dict.

        Returns:
            Dict mit Kategorien und zugehoerigen Konten
        """
        return {
            "aufwand": self.expense_accounts,
            "erloes": self.revenue_accounts,
            "personenkonten": {
                "kreditor_default": self.default_creditor_account,
                "debitor_default": self.default_debtor_account,
                "kreditor_start": self.creditor_range_start,
                "kreditor_end": self.creditor_range_end,
                "debitor_start": self.debtor_range_start,
                "debitor_end": self.debtor_range_end,
            },
            "sammelkonten": {
                "kreditoren": self.sammelkonto_kreditoren,
                "debitoren": self.sammelkonto_debitoren,
            },
            "steuer": {
                "vorsteuer_19": self.vorsteuer_19,
                "vorsteuer_7": self.vorsteuer_7,
                "umsatzsteuer_19": self.umsatzsteuer_19,
                "umsatzsteuer_7": self.umsatzsteuer_7,
            },
        }

    def is_creditor_account(self, account: str) -> bool:
        """Prueft ob Kontonummer im Kreditoren-Bereich liegt."""
        try:
            num = int(account)
            start = int(self.creditor_range_start)
            end = int(self.creditor_range_end)
            return start <= num <= end
        except ValueError:
            return False

    def is_debtor_account(self, account: str) -> bool:
        """Prueft ob Kontonummer im Debitoren-Bereich liegt."""
        try:
            num = int(account)
            start = int(self.debtor_range_start)
            end = int(self.debtor_range_end)
            return start <= num <= end
        except ValueError:
            return False
