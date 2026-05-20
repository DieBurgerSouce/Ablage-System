# -*- coding: utf-8 -*-
"""
Deutsche Praezision - Korrekte Fachbegriffe durchgaengig.

DATEV-konforme Terminologie. Einheitliche Formulierungen.
Kein Mix aus formell/informell. Alle Fachbegriffe korrekt.

Erweitert um:
- Umfassenderes Woerterbuch (Buchhaltung, Rechnungswesen, Steuer, DATEV, BWA)
- Kategorisierte Begriffe für Frontend-i18n
- Tooltip/Hilfetexte für UI-Elemente
- Terminologie-Validierung mit Wortgrenzen-Erkennung
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


class GermanTerminologyService:
    """Deutsche Praezision - Korrekte Fachbegriffe durchgaengig.

    DATEV-konforme Terminologie. Einheitliche Formulierungen.
    Kein Mix aus formell/informell. Alle Fachbegriffe korrekt.
    """

    # Umfassende deutsche Buchhaltungs- und Finanzbegriffe
    FACHBEGRIFFE: Dict[str, str] = {
        # Buchhaltungs-Begriffe
        "booking_entry": "Buchungssatz",
        "account": "Konto",
        "account_chart": "Kontenrahmen",
        "chart_of_accounts": "Kontenrahmen",
        "general_ledger": "Hauptbuch",
        "subledger": "Nebenbuch",
        "subsidiary_ledger": "Nebenbuch",
        "journal": "Journal",
        "posting": "Buchung",
        "debit": "Soll",
        "credit": "Haben",
        "balance": "Saldo",
        "trial_balance": "Summen- und Saldenliste",
        "balance_sheet": "Bilanz",
        "income_statement": "Gewinn- und Verlustrechnung",
        "profit_loss": "GuV",
        "fiscal_year": "Geschäftsjahr",
        "closing": "Abschluss",
        "month_end_closing": "Monatsabschluss",
        "year_end_closing": "Jahresabschluss",
        "accrual": "Abgrenzung",
        "depreciation": "Abschreibung",
        "amortization": "Tilgung",
        "retained_earnings": "Gewinnvortrag",
        "audit": "Prüfung",
        "compliance": "Ordnungsmaessigkeit",

        # Rechnungswesen
        "invoice": "Rechnung",
        "purchase_invoice": "Eingangsrechnung",
        "incoming_invoice": "Eingangsrechnung",
        "sales_invoice": "Ausgangsrechnung",
        "outgoing_invoice": "Ausgangsrechnung",
        "credit_note": "Gutschrift",
        "dunning": "Mahnung",
        "dunning_level": "Mahnstufe",
        "payment_reminder": "Zahlungserinnerung",
        "cash_discount": "Skonto",
        "payment_terms": "Zahlungsbedingungen",
        "payment_term": "Zahlungsziel",
        "due_date": "Fälligkeitsdatum",
        "partial_payment": "Teilzahlung",
        "outstanding_amount": "Offener Betrag",
        "open_items": "Offene Posten",
        "accounts_receivable": "Forderungen",
        "accounts_payable": "Verbindlichkeiten",
        "net_amount": "Nettobetrag",
        "gross_amount": "Bruttobetrag",

        # Steuer
        "vat": "Umsatzsteuer",
        "input_vat": "Vorsteuer",
        "input_tax": "Vorsteuer",
        "output_vat": "Umsatzsteuer",
        "vat_return": "USt-Voranmeldung",
        "tax_number": "Steuernummer",
        "vat_id": "USt-IdNr.",
        "tax_rate": "Steuersatz",
        "tax_liability": "Zahllast",
        "tax_exempt": "Steuerfrei",
        "intra_community": "Innergemeinschaftlich",

        # DATEV
        "accounting_pattern": "Kontierungsmuster",
        "posting_key": "Buchungsschluessel",
        "account_assignment": "Kontierung",
        "cost_center": "Kostenstelle",
        "cost_type": "Kostenart",
        "document_link": "Beleglink",
        "posting_text": "Buchungstext",
        "posting_date": "Buchungsdatum",
        "document_date": "Belegdatum",
        "document_number": "Belegnummer",
        "tax_advisor": "Steuerberater",
        "tax_office": "Finanzamt",

        # BWA (Betriebswirtschaftliche Auswertung)
        "revenue": "Erloese",
        "material_costs": "Materialaufwand",
        "cost_of_goods": "Materialaufwand",
        "personnel_costs": "Personalaufwand",
        "other_expenses": "Sonstige betriebliche Aufwendungen",
        "operating_result": "Betriebsergebnis",
        "financial_result": "Finanzergebnis",
        "pre_tax_result": "Ergebnis vor Steuern",
        "net_income": "Jahresüberschuss",
        "net_profit": "Jahresüberschuss",

        # Dokumente
        "document": "Dokument",
        "attachment": "Anlage",
        "delivery_note": "Lieferschein",
        "order": "Bestellung",
        "purchase_order": "Bestellauftrag",
        "contract": "Vertrag",
        "receipt": "Quittung",
        "voucher": "Buchungsbeleg",
        "offer": "Angebot",
        "order_confirmation": "Auftragsbestätigung",

        # Bank-Begriffe
        "bank_statement": "Kontoauszug",
        "wire_transfer": "Überweisung",
        "direct_debit": "Lastschrift",
        "standing_order": "Dauerauftrag",
        "account_balance": "Kontostand",
        "reconciliation": "Abstimmung",

        # Entities
        "customer": "Kunde",
        "supplier": "Lieferant",
        "business_partner": "Geschäftspartner",
        "contact": "Ansprechpartner",

        # Status
        "draft": "Entwurf",
        "pending": "Ausstehend",
        "approved": "Genehmigt",
        "rejected": "Abgelehnt",
        "completed": "Abgeschlossen",
        "cancelled": "Storniert",
        "overdue": "Überfällig",
        "in_progress": "In Bearbeitung",
        "verified": "Geprüft",
        "archived": "Archiviert",
    }

    # Deutsche Fehlermeldungen
    FEHLERMELDUNGEN: Dict[str, str] = {
        "not_found": "Nicht gefunden",
        "document_not_found": "Dokument nicht gefunden",
        "invoice_not_found": "Rechnung nicht gefunden",
        "entity_not_found": "Geschäftspartner nicht gefunden",
        "permission_denied": "Zugriff verweigert",
        "validation_failed": "Validierung fehlgeschlagen",
        "duplicate_detected": "Duplikat erkannt",
        "processing_failed": "Verarbeitung fehlgeschlagen",
        "upload_failed": "Hochladen fehlgeschlagen",
        "export_failed": "Export fehlgeschlagen",
        "import_failed": "Import fehlgeschlagen",
        "invalid_format": "Ungültiges Dateiformat",
        "invalid_amount": "Ungültiger Betrag",
        "invalid_date": "Ungültiges Datum",
        "file_too_large": "Datei zu gross",
        "quota_exceeded": "Kontingent überschritten",
        "rate_limited": "Zu viele Anfragen - bitte warten",
        "session_expired": "Sitzung abgelaufen - bitte erneut anmelden",
        "maintenance": "Wartungsarbeiten - bitte später erneut versuchen",
        "skonto_expired": "Skontofrist abgelaufen",
        "approval_required": "Genehmigung erforderlich",
        "approval_timeout": "Genehmigungsfrist überschritten",
        "sla_breach": "SLA-Verletzung festgestellt",
        "invoice_overdue": "Rechnung überfällig",
        "insufficient_funds": "Unzureichende Deckung",
        "connection_failed": "Verbindung fehlgeschlagen",
        "timeout": "Zeitüberschreitung",
        "contract_expired": "Vertrag abgelaufen",
        "deadline_missed": "Frist versaeumt",
        "thread_not_found": "Kommentar-Thread nicht gefunden",
        "reply_not_found": "Antwort nicht gefunden",
        "task_not_found": "Aufgabe nicht gefunden",
        "annotation_not_found": "Annotation nicht gefunden",
        "user_not_found": "Benutzer nicht gefunden",
        "invalid_status": "Ungültiger Status",
        "invalid_coordinates": "Ungültige Koordinaten",
    }

    # Deutsche Statusmeldungen
    STATUSMELDUNGEN: Dict[str, str] = {
        "uploading": "Wird hochgeladen...",
        "processing": "Wird verarbeitet...",
        "ocr_running": "OCR-Erkennung laeuft...",
        "extracting": "Daten werden extrahiert...",
        "validating": "Wird validiert...",
        "complete": "Fertig",
        "error": "Fehler aufgetreten",
        "queued": "In Warteschlange",
        "pending_approval": "Wartet auf Genehmigung",
        "approved": "Genehmigt",
        "rejected": "Abgelehnt",
        "archived": "Archiviert",
        "deleted": "Gelöscht",
    }

    # Deutsche Tooltips für UI-Elemente
    TOOLTIPS: Dict[str, str] = {
        "skonto": (
            "Nachlass bei frühzeitiger Zahlung "
            "innerhalb der Skontofrist"
        ),
        "skonto_hint": (
            "Skonto ist ein Preisnachlass bei Zahlung "
            "innerhalb der vereinbarten Frist"
        ),
        "bwa": (
            "Betriebswirtschaftliche Auswertung - "
            "Überblick über Erträge und Aufwendungen"
        ),
        "bwa_hint": (
            "Die Betriebswirtschaftliche Auswertung zeigt die "
            "wirtschaftliche Lage Ihres Unternehmens"
        ),
        "ust_voranmeldung": (
            "Monatliche/quartalsweise Umsatzsteuer-Voranmeldung "
            "ans Finanzamt"
        ),
        "ust_hint": (
            "Die Umsatzsteuer-Voranmeldung muss monatlich oder "
            "quartalsweise beim Finanzamt eingereicht werden"
        ),
        "offene_posten": (
            "Noch nicht bezahlte Rechnungen "
            "(Forderungen und Verbindlichkeiten)"
        ),
        "zahllast": (
            "Differenz zwischen Umsatzsteuer und Vorsteuer - "
            "an Finanzamt zu zahlen"
        ),
        "mahnstufe": (
            "Eskalationsstufe im Mahnverfahren "
            "(Zahlungserinnerung -> 1. Mahnung -> 2. Mahnung)"
        ),
        "kontenrahmen": (
            "Systematische Ordnung aller Konten eines Unternehmens "
            "(z.B. SKR 03, SKR 04)"
        ),
        "kontierungsmuster": (
            "Vordefinierte Buchungsregeln für "
            "wiederkehrende Geschäftsvorfaelle"
        ),
        "kostenstelle": (
            "Organisatorische Einheit zur Zuordnung von Kosten "
            "(z.B. Abteilung, Projekt)"
        ),
        "beleglink": (
            "Verknüpfung zwischen digitalem Beleg "
            "und Buchungssatz in DATEV"
        ),
        "innergemeinschaftlich": (
            "Lieferungen und Leistungen innerhalb der EU - "
            "besondere steuerliche Behandlung"
        ),
        "abgrenzung": (
            "Periodengerechte Zuordnung von Aufwendungen und Erträgen "
            "zum richtigen Geschäftsjahr"
        ),
        "datev_hint": (
            "DATEV ist das Standard-Format für den Datenaustausch "
            "mit Ihrem Steuerberater"
        ),
        "gdpr_hint": (
            "Alle personenbezogenen Daten werden DSGVO-konform "
            "verarbeitet und gespeichert"
        ),
        "gobd_hint": (
            "GoBD: Grundsätze zur ordnungsmaessigen Führung "
            "und Aufbewahrung von Buechern"
        ),
    }

    def translate(self, key: str) -> str:
        """Fachbegriff übersetzen (English -> Deutsch).

        Args:
            key: Englischer Schluessel

        Returns:
            Deutscher Fachbegriff oder Schluessel wenn nicht gefunden
        """
        return self.FACHBEGRIFFE.get(key, key)

    def get_error_message(self, key: str) -> str:
        """Deutsche Fehlermeldung abrufen.

        Args:
            key: Fehler-Schluessel

        Returns:
            Deutsche Fehlermeldung
        """
        return self.FEHLERMELDUNGEN.get(key, "Ein Fehler ist aufgetreten")

    def get_status_message(self, key: str) -> str:
        """Deutsche Statusmeldung abrufen.

        Args:
            key: Status-Schluessel

        Returns:
            Deutsche Statusmeldung
        """
        return self.STATUSMELDUNGEN.get(key, key)

    def get_tooltip(self, key: str) -> str:
        """Tooltip-Text abrufen.

        Args:
            key: Tooltip-Schluessel

        Returns:
            Tooltip-Text oder leerer String
        """
        return self.TOOLTIPS.get(key, "")

    def validate_terminology(self, text: str) -> List[Dict[str, str]]:
        """Prüfen ob englische Fachbegriffe im Text vorkommen die deutsch sein sollten.

        Verwendet Wortgrenzen-Erkennung um falsche Treffer zu vermeiden.

        Args:
            text: Zu prüfender Text

        Returns:
            Liste von Befunden mit found, should_be und message
        """
        findings: List[Dict[str, str]] = []
        text_lower = text.lower()

        # Häufige englische Begriffe mit Wortgrenzen-Erkennung prüfen
        check_patterns: Dict[str, str] = {
            "invoice": "Rechnung",
            "credit note": "Gutschrift",
            "dunning": "Mahnung",
            "payment terms": "Zahlungsbedingungen",
            "due date": "Fälligkeitsdatum",
            "cash discount": "Skonto",
            "outstanding amount": "Offener Betrag",
            "open items": "Offene Posten",
            "chart of accounts": "Kontenrahmen",
            "general ledger": "Hauptbuch",
            "trial balance": "Summen- und Saldenliste",
            "fiscal year": "Geschäftsjahr",
            "cost center": "Kostenstelle",
            "delivery note": "Lieferschein",
            "purchase order": "Bestellauftrag",
            "accounts receivable": "Forderungen",
            "accounts payable": "Verbindlichkeiten",
            "tax rate": "Steuersatz",
            "tax number": "Steuernummer",
            "partial payment": "Teilzahlung",
        }

        for english, german in check_patterns.items():
            pattern = r"\b" + re.escape(english) + r"\b"
            if re.search(pattern, text_lower):
                findings.append({
                    "found": english,
                    "should_be": german,
                    "message": (
                        f"'{english}' sollte als '{german}' "
                        f"übersetzt werden"
                    ),
                })

        return findings

    def get_all_terms(self) -> Dict[str, str]:
        """Komplettes Terminologie-Woerterbuch zurückgeben.

        Wird vom Frontend für i18n/Lokalisierung verwendet.

        Returns:
            Dictionary mit allen englisch-deutschen Begriffspaaren
        """
        return dict(self.FACHBEGRIFFE)

    def get_all_errors(self) -> Dict[str, str]:
        """Alle deutschen Fehlermeldungen zurückgeben.

        Returns:
            Dictionary mit allen Fehler-Schluessel-Meldungs-Paaren
        """
        return dict(self.FEHLERMELDUNGEN)

    def get_all_tooltips(self) -> Dict[str, str]:
        """Alle Tooltips zurückgeben.

        Returns:
            Dictionary mit allen Tooltip-Schluessel-Text-Paaren
        """
        return dict(self.TOOLTIPS)

    def get_full_dictionary(self) -> Dict[str, Dict[str, str]]:
        """Komplettes Woerterbuch aller Kategorien zurückgeben.

        Returns:
            Dict mit allen Kategorien (fachbegriffe, fehler, status, tooltips)
        """
        return {
            "fachbegriffe": self.FACHBEGRIFFE,
            "fehlermeldungen": self.FEHLERMELDUNGEN,
            "statusmeldungen": self.STATUSMELDUNGEN,
            "tooltips": self.TOOLTIPS,
        }

    def get_category_terms(self, category: str) -> Dict[str, str]:
        """Gibt Begriffe einer bestimmten Kategorie zurück.

        Args:
            category: Kategorie (buchhaltung, rechnungswesen, steuer,
                      datev, bwa, dokumente, bank, entities, status)

        Returns:
            Dictionary mit Begriffen der Kategorie
        """
        categories: Dict[str, List[str]] = {
            "buchhaltung": [
                "booking_entry", "account", "chart_of_accounts",
                "general_ledger", "subledger", "journal", "posting",
                "debit", "credit", "balance", "trial_balance",
                "balance_sheet", "income_statement", "profit_loss",
                "fiscal_year", "closing", "month_end_closing",
                "year_end_closing", "accrual", "depreciation",
                "amortization", "retained_earnings", "audit",
                "compliance",
            ],
            "rechnungswesen": [
                "invoice", "purchase_invoice", "sales_invoice",
                "credit_note", "dunning", "dunning_level",
                "payment_reminder", "cash_discount", "payment_terms",
                "due_date", "partial_payment", "outstanding_amount",
                "open_items", "accounts_receivable", "accounts_payable",
                "net_amount", "gross_amount",
            ],
            "steuer": [
                "vat", "input_vat", "output_vat", "vat_return",
                "tax_number", "vat_id", "tax_rate", "tax_liability",
                "tax_exempt", "intra_community",
            ],
            "datev": [
                "accounting_pattern", "posting_key", "account_assignment",
                "cost_center", "cost_type", "document_link",
                "posting_text", "posting_date", "document_date",
                "document_number", "tax_advisor", "tax_office",
            ],
            "bwa": [
                "revenue", "material_costs", "personnel_costs",
                "other_expenses", "operating_result", "financial_result",
                "pre_tax_result", "net_income",
            ],
            "dokumente": [
                "document", "attachment", "delivery_note", "order",
                "purchase_order", "contract", "receipt", "voucher",
                "offer", "order_confirmation",
            ],
            "bank": [
                "bank_statement", "wire_transfer", "direct_debit",
                "standing_order", "account_balance", "reconciliation",
            ],
            "entities": [
                "customer", "supplier", "business_partner", "contact",
            ],
            "status": [
                "draft", "pending", "approved", "rejected", "completed",
                "cancelled", "overdue", "in_progress", "verified",
                "archived",
            ],
        }

        keys = categories.get(category, [])
        return {k: self.FACHBEGRIFFE[k] for k in keys if k in self.FACHBEGRIFFE}


# Singleton
_terminology_service: Optional[GermanTerminologyService] = None


def get_german_terminology_service() -> GermanTerminologyService:
    """Factory-Funktion für GermanTerminologyService Singleton."""
    global _terminology_service
    if _terminology_service is None:
        _terminology_service = GermanTerminologyService()
    return _terminology_service
