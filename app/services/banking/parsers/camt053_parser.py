"""CAMT.053 Bank Statement Parser.

Parst CAMT.053 (ISO 20022) Kontoauszuege, das moderne XML-Format
das von vielen deutschen Banken unterstuetzt wird.

Verwendet die pyiso20022 Bibliothek.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Union, Dict, Any
import structlog
import re
from xml.etree import ElementTree as ET

from .base import BaseParser, ParsedTransaction, ParseResult, ParserRegistry
from ..models import ImportFormat, TransactionType

logger = structlog.get_logger(__name__)

# ISO 20022 Namespaces
CAMT_NS = {
    "camt": "urn:iso:std:iso:20022:tech:xsd:camt.053.001.02",
    "camt04": "urn:iso:std:iso:20022:tech:xsd:camt.053.001.04",
    "camt08": "urn:iso:std:iso:20022:tech:xsd:camt.053.001.08",
}


@ParserRegistry.register
class CAMT053Parser(BaseParser):
    """Parser fuer CAMT.053 (ISO 20022) Kontoauszuege."""

    FORMAT = ImportFormat.CAMT053
    FORMAT_VARIANT = None
    SUPPORTED_EXTENSIONS = [".xml", ".camt", ".camt053"]

    @classmethod
    def can_parse(cls, content: Union[str, bytes], filename: Optional[str] = None) -> float:
        """Pruefe ob Inhalt CAMT.053-Format ist."""
        if isinstance(content, bytes):
            try:
                content = content.decode("utf-8", errors="replace")
            except UnicodeDecodeError:
                return 0.0

        content_lower = content[:3000].lower()

        # Starke Indikatoren: CAMT.053 Namespace
        if "camt.053" in content_lower:
            return 0.95

        # ISO 20022 Indikatoren
        if "iso:std:iso:20022" in content_lower and "bktocstmrstmt" in content_lower:
            return 0.9

        # XML mit Bank-Statement-typischen Elementen
        if "<?xml" in content_lower:
            bank_elements = ["<stmt>", "<ntry>", "<acct>", "<bal>", "<txdtls>"]
            matches = sum(1 for elem in bank_elements if elem in content_lower)
            if matches >= 3:
                return 0.7
            elif matches >= 2:
                return 0.5

        # Extension-basierte Erkennung
        if filename:
            ext = "." + filename.split(".")[-1].lower() if "." in filename else ""
            if ext in cls.SUPPORTED_EXTENSIONS and "<?xml" in content_lower:
                return 0.4

        return 0.0

    def parse(self, content: Union[str, bytes]) -> ParseResult:
        """Parse CAMT.053-Kontoauszug."""
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")

        result = ParseResult(
            success=False,
            format=ImportFormat.CAMT053,
        )

        try:
            # Parse XML
            root = ET.fromstring(content)

            # Namespace ermitteln
            ns = self._detect_namespace(root)
            if not ns:
                result.errors.append({
                    "type": "parse_error",
                    "message": "Kein unterstuetzter CAMT.053 Namespace gefunden",
                })
                return result

            # Statements finden
            statements = root.findall(f".//{{{ns}}}Stmt") or root.findall(".//Stmt")

            if not statements:
                # Fallback ohne Namespace
                statements = root.iter()
                statements = [s for s in root.iter() if s.tag.endswith("Stmt")]

            if not statements:
                result.errors.append({
                    "type": "parse_error",
                    "message": "Keine Statements im CAMT.053 gefunden",
                })
                return result

            for stmt in statements:
                # Kontoinfo
                acct = self._find_element(stmt, "Acct", ns)
                if acct:
                    iban_elem = self._find_element(acct, "Id/IBAN", ns)
                    if iban_elem is not None and iban_elem.text:
                        result.account_iban = self.normalize_iban(iban_elem.text)

                    bic_elem = self._find_element(acct, "Svcr/FinInstnId/BIC", ns)
                    if bic_elem is not None and bic_elem.text:
                        result.account_bic = bic_elem.text

                # Salden
                for bal in self._find_all_elements(stmt, "Bal", ns):
                    bal_type = self._get_text(bal, "Tp/CdOrPrtry/Cd", ns)
                    amt_elem = self._find_element(bal, "Amt", ns)

                    if amt_elem is not None and amt_elem.text:
                        amount = Decimal(amt_elem.text)
                        ccy = amt_elem.get("Ccy", "EUR")

                        # Vorzeichen
                        cdt_dbt = self._get_text(bal, "CdtDbtInd", ns)
                        if cdt_dbt == "DBIT":
                            amount = -amount

                        dt_elem = self._find_element(bal, "Dt/Dt", ns)
                        bal_date = None
                        if dt_elem is not None and dt_elem.text:
                            bal_date = datetime.strptime(dt_elem.text, "%Y-%m-%d").date()

                        if bal_type == "OPBD":  # Opening Balance
                            result.opening_balance = amount
                            result.date_from = bal_date
                        elif bal_type in ("CLBD", "CLAV"):  # Closing Balance
                            result.closing_balance = amount
                            result.balance_date = bal_date

                # Transaktionen (Entries)
                for ntry in self._find_all_elements(stmt, "Ntry", ns):
                    parsed = self._parse_entry(ntry, ns)
                    if parsed:
                        result.transactions.append(parsed)

                        # Statistik
                        if parsed.amount > 0:
                            result.total_credits += parsed.amount
                        else:
                            result.total_debits += abs(parsed.amount)

                        # Zeitraum
                        if parsed.booking_date:
                            if not result.date_from or parsed.booking_date < result.date_from:
                                result.date_from = parsed.booking_date
                            if not result.date_to or parsed.booking_date > result.date_to:
                                result.date_to = parsed.booking_date

            result.success = True

        except ET.ParseError as e:
            logger.exception(f"XML Parse-Fehler: {e}")
            result.errors.append({
                "type": "xml_error",
                "message": f"Ungültiges XML: {e}",
            })
        except Exception as e:
            logger.exception(f"Fehler beim Parsen des CAMT.053: {e}")
            result.errors.append({
                "type": "parse_error",
                "message": str(e),
            })

        return result

    def _detect_namespace(self, root: ET.Element) -> Optional[str]:
        """Ermittle den korrekten CAMT.053 Namespace."""
        # Namespace aus Root-Element
        tag = root.tag
        if "{" in tag:
            ns = tag[tag.find("{") + 1:tag.find("}")]
            if "camt.053" in ns or "20022" in ns:
                return ns

        # Pruefe bekannte Namespaces
        for ns in CAMT_NS.values():
            if root.find(f".//{{{ns}}}Stmt") is not None:
                return ns

        # Fallback: kein Namespace
        if root.find(".//Stmt") is not None:
            return ""

        return None

    def _find_element(self, parent: ET.Element, path: str, ns: str) -> Optional[ET.Element]:
        """Finde Element mit oder ohne Namespace."""
        if ns:
            # Mit Namespace
            parts = path.split("/")
            ns_path = "/".join(f"{{{ns}}}{p}" for p in parts)
            elem = parent.find(ns_path)
            if elem is not None:
                return elem

        # Ohne Namespace
        return parent.find(path.replace("/", "/"))

    def _find_all_elements(self, parent: ET.Element, tag: str, ns: str) -> List[ET.Element]:
        """Finde alle Elemente mit oder ohne Namespace."""
        if ns:
            return parent.findall(f".//{{{ns}}}{tag}")
        return parent.findall(f".//{tag}")

    def _get_text(self, parent: ET.Element, path: str, ns: str) -> Optional[str]:
        """Hole Text aus Element."""
        elem = self._find_element(parent, path, ns)
        return elem.text if elem is not None else None

    def _parse_entry(self, ntry: ET.Element, ns: str) -> Optional[ParsedTransaction]:
        """Parse einzelnen Entry (Transaktion)."""
        try:
            # Betrag
            amt_elem = self._find_element(ntry, "Amt", ns)
            if amt_elem is None or not amt_elem.text:
                return None

            amount = Decimal(amt_elem.text)
            currency = amt_elem.get("Ccy", "EUR")

            # Vorzeichen (CRDT = Gutschrift, DBIT = Belastung)
            cdt_dbt = self._get_text(ntry, "CdtDbtInd", ns)
            if cdt_dbt == "DBIT":
                amount = -amount

            # Buchungsdatum
            booking_date = None
            val_date = None

            bkg_dt = self._get_text(ntry, "BookgDt/Dt", ns)
            if bkg_dt:
                booking_date = datetime.strptime(bkg_dt, "%Y-%m-%d").date()

            val_dt = self._get_text(ntry, "ValDt/Dt", ns)
            if val_dt:
                val_date = datetime.strptime(val_dt, "%Y-%m-%d").date()
            else:
                val_date = booking_date

            # Transaction Details (TxDtls)
            tx_dtls = self._find_element(ntry, "NtryDtls/TxDtls", ns)

            counterparty_name = None
            counterparty_iban = None
            counterparty_bic = None
            reference_text = None
            end_to_end_id = None
            mandate_id = None
            creditor_id = None

            if tx_dtls is not None:
                # End-to-End-ID
                end_to_end_id = self._get_text(tx_dtls, "Refs/EndToEndId", ns)
                mandate_id = self._get_text(tx_dtls, "Refs/MndtId", ns)

                # Gegenpartei
                if cdt_dbt == "DBIT":
                    # Bei Belastung: Creditor
                    party = self._find_element(tx_dtls, "RltdPties/Cdtr", ns)
                    acct = self._find_element(tx_dtls, "RltdPties/CdtrAcct/Id/IBAN", ns)
                    agent = self._find_element(tx_dtls, "RltdAgts/CdtrAgt/FinInstnId/BIC", ns)
                else:
                    # Bei Gutschrift: Debtor
                    party = self._find_element(tx_dtls, "RltdPties/Dbtr", ns)
                    acct = self._find_element(tx_dtls, "RltdPties/DbtrAcct/Id/IBAN", ns)
                    agent = self._find_element(tx_dtls, "RltdAgts/DbtrAgt/FinInstnId/BIC", ns)

                if party is not None:
                    name_elem = self._find_element(party, "Nm", ns)
                    if name_elem is not None and name_elem.text:
                        counterparty_name = name_elem.text

                if acct is not None and acct.text:
                    counterparty_iban = self.normalize_iban(acct.text)

                if agent is not None and agent.text:
                    counterparty_bic = agent.text

                # Verwendungszweck
                rmt_inf = self._find_element(tx_dtls, "RmtInf", ns)
                if rmt_inf is not None:
                    # Unstrukturiert
                    ustrd = self._find_element(rmt_inf, "Ustrd", ns)
                    if ustrd is not None and ustrd.text:
                        reference_text = ustrd.text

                    # Strukturiert (z.B. Rechnungsnummer)
                    strd = self._find_element(rmt_inf, "Strd", ns)
                    if strd is not None:
                        ref = self._get_text(strd, "CdtrRefInf/Ref", ns)
                        if ref:
                            if reference_text:
                                reference_text += f" REF: {ref}"
                            else:
                                reference_text = f"REF: {ref}"

                # Creditor-ID (bei Lastschrift)
                creditor_id = self._get_text(tx_dtls, "RltdPties/Cdtr/Id/PrvtId/Othr/Id", ns)
                if not creditor_id:
                    creditor_id = self._get_text(tx_dtls, "RltdPties/Cdtr/Id/OrgId/Othr/Id", ns)

            # Buchungstext
            booking_text = self._get_text(ntry, "AddtlNtryInf", ns)
            if not booking_text:
                booking_text = self._get_text(ntry, "BkTxCd/Prtry/Cd", ns)

            # Transaktionstyp ermitteln
            transaction_type = self.detect_transaction_type(
                booking_text or "",
                amount
            )

            # Bank-Referenz
            acct_svcr_ref = self._get_text(ntry, "AcctSvcrRef", ns)

            # Referenzen parsen
            parsed_refs = self.parse_reference_text(reference_text or "")

            # Transaction-ID
            transaction_id = acct_svcr_ref or end_to_end_id
            if not transaction_id:
                transaction_id = self.generate_transaction_hash(
                    booking_date or date.today(),
                    amount,
                    counterparty_name or "",
                    reference_text or ""
                )

            return ParsedTransaction(
                transaction_id=transaction_id,
                booking_date=booking_date,
                value_date=val_date,
                amount=amount,
                currency=currency,
                counterparty_name=counterparty_name,
                counterparty_iban=counterparty_iban,
                counterparty_bic=counterparty_bic,
                reference_text=reference_text,
                end_to_end_id=end_to_end_id,
                mandate_id=mandate_id,
                creditor_id=creditor_id,
                transaction_type=transaction_type,
                booking_text=booking_text,
                prima_nota=acct_svcr_ref,
                parsed_invoice_numbers=parsed_refs["invoice_numbers"],
                parsed_customer_numbers=parsed_refs["customer_numbers"],
                parsed_references=parsed_refs["order_numbers"],
                raw_data={
                    "camt_acct_svcr_ref": acct_svcr_ref,
                    "camt_cdt_dbt_ind": cdt_dbt,
                },
            )

        except Exception as e:
            logger.warning(f"Fehler beim Parsen des CAMT.053 Entry: {e}")
            return None
