# -*- coding: utf-8 -*-
"""
Abstrakte Basis für Kontenrahmen.

Definiert die Schnittstelle für SKR03 und SKR04 Implementierungen.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional


class BaseKontenrahmen(ABC):
    """
    Abstrakte Basis für Kontenrahmen.

    Jeder Kontenrahmen definiert Standard-Konten für verschiedene
    Buchungstypen (Wareneingang, Erloese, etc.) sowie die Mapping-
    Logik für automatische Kontozuordnung.
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

    @property
    @abstractmethod
    def expense_accounts(self) -> Dict[str, str]:
        """
        Alle verfügbaren Aufwandskonten.

        Returns:
            Dict mit {expense_type: kontonummer}
        """
        pass

    # =========================================================================
    # ERLOESKONTEN (Ausgangsrechnungen)
    # =========================================================================

    @property
    @abstractmethod
    def revenue_accounts(self) -> Dict[str, str]:
        """
        Alle verfügbaren Erloeskonten.

        Returns:
            Dict mit {revenue_type: kontonummer}
        """
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
        """Prüft ob Kontonummer im Kreditoren-Bereich liegt."""
        try:
            num = int(account)
            start = int(self.creditor_range_start)
            end = int(self.creditor_range_end)
            return start <= num <= end
        except ValueError:
            return False

    def is_debtor_account(self, account: str) -> bool:
        """Prüft ob Kontonummer im Debitoren-Bereich liegt."""
        try:
            num = int(account)
            start = int(self.debtor_range_start)
            end = int(self.debtor_range_end)
            return start <= num <= end
        except ValueError:
            return False

    # =========================================================================
    # GEMEINSAME IMPLEMENTIERUNGEN (ehemals in SKR03/SKR04 dupliziert)
    # =========================================================================

    def get_expense_account(
        self,
        expense_type: str,
        vat_rate: Optional[float] = None
    ) -> str:
        """
        Liefert Standard-Aufwandskonto.

        Args:
            expense_type: Typ des Aufwands (waren, dienstleistung, miete, etc.)
            vat_rate: MwSt-Satz (7 oder 19), optional für differenzierte Konten

        Returns:
            Kontonummer als String
        """
        expense_type = expense_type.lower().replace(" ", "_")

        # Spezialfall: Waren mit MwSt-Differenzierung
        if expense_type in ("waren", "wareneingang"):
            if vat_rate == 7:
                return self._wareneingang_7
            return self._wareneingang_19

        return self.expense_accounts.get(expense_type, self._wareneingang_19)

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
        revenue_type = revenue_type.lower().replace(" ", "_")

        # Spezialfall: Differenzierung nach MwSt
        if revenue_type in ("waren", "dienstleistung"):
            if vat_rate == 7:
                return self._erloese_7
            return self._erloese_19

        return self.revenue_accounts.get(revenue_type, self._erloese_19)

    # =========================================================================
    # ABSTRAKTE KONTO-PROPERTIES (müssen in Subklassen definiert werden)
    # =========================================================================

    @property
    @abstractmethod
    def _wareneingang_19(self) -> str:
        """Wareneingang 19% - für get_expense_account."""
        pass

    @property
    @abstractmethod
    def _wareneingang_7(self) -> str:
        """Wareneingang 7% - für get_expense_account."""
        pass

    @property
    @abstractmethod
    def _erloese_19(self) -> str:
        """Erloese 19% - für get_revenue_account."""
        pass

    @property
    @abstractmethod
    def _erloese_7(self) -> str:
        """Erloese 7% - für get_revenue_account."""
        pass

    # =========================================================================
    # GEMEINSAME PERSONENKONTEN-DEFAULTS (identisch für SKR03 und SKR04)
    # =========================================================================

    @property
    def default_creditor_account(self) -> str:
        """Standard-Kreditorenkonto (Lieferanten)."""
        return "70000"

    @property
    def default_debtor_account(self) -> str:
        """Standard-Debitorenkonto (Kunden)."""
        return "10000"

    @property
    def creditor_range_start(self) -> str:
        """Beginn des Kreditoren-Nummernkreises."""
        return "70000"

    @property
    def creditor_range_end(self) -> str:
        """Ende des Kreditoren-Nummernkreises."""
        return "99999"

    @property
    def debtor_range_start(self) -> str:
        """Beginn des Debitoren-Nummernkreises."""
        return "10000"

    @property
    def debtor_range_end(self) -> str:
        """Ende des Debitoren-Nummernkreises."""
        return "69999"
