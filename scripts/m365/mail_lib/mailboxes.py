# -*- coding: utf-8 -*-
"""Postfach-Liste (aus exo_sizes.csv) + Adress-/Richtungs-Helfer der Extraktion.

Rein lesend, ohne Fremd-Bibliothek. Wird von mail_01_extract und mail_02_verify
gemeinsam genutzt. Die Firmen-Domains steuern die Richtungs-Heuristik (ein/aus/intern).
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

# Firmen-Domains (Plan S1.3/S2): steuern Richtung und spaeter den Waechter.
FIRMENICH_DOMAINS = {"firmenich.de", "spargelmesserfirmenich.onmicrosoft.com"}

# System-Postfach (Discovery Search) — nie extrahieren.
DISCOVERY_MARKER = "discoverysearchmailbox"


@dataclass
class Mailbox:
    """Eine Zeile aus exo_sizes.csv (nur die fuer die Extraktion relevanten Felder)."""

    upn: str
    display_name: str
    rtype: str
    item_count: int
    size_mb: float

    @property
    def is_discovery(self) -> bool:
        return (DISCOVERY_MARKER in self.upn.lower()) or (self.rtype.lower() == "discoverymailbox")


def _to_int(value: str) -> int:
    try:
        return int(float((value or "").strip()))
    except (TypeError, ValueError):
        return 0


def _to_float(value: str) -> float:
    # exo_sizes.csv nutzt deutsches Dezimalkomma ("25333,4").
    raw = (value or "").strip().replace(".", "").replace(",", ".")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def load_mailboxes(csv_path: Path) -> list[Mailbox]:
    """Liest exo_sizes.csv und liefert die ECHTEN Postfaecher.

    Uebersprungen werden: Discovery-Postfach und Zeilen mit ItemCount <= 0.
    """
    rows: list[Mailbox] = []
    with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            mb = Mailbox(
                upn=(row.get("UPN") or "").strip(),
                display_name=(row.get("DisplayName") or "").strip(),
                rtype=(row.get("Typ") or "").strip(),
                item_count=_to_int(row.get("ItemCount")),
                size_mb=_to_float(row.get("SizeMB")),
            )
            if not mb.upn or mb.is_discovery or mb.item_count <= 0:
                continue
            rows.append(mb)
    return rows


def sort_smallest_first(mailboxes: list[Mailbox]) -> list[Mailbox]:
    """Kleinste zuerst (Mail-Anzahl, dann Groesse) — schnelles Feedback."""
    return sorted(mailboxes, key=lambda m: (m.item_count, m.size_mb, m.upn.lower()))


# --------------------------------------------------------------------------- #
# Adress-Helfer (arbeiten auf den Graph-Metadaten)
# --------------------------------------------------------------------------- #
def _email_address(recipient: dict | None) -> dict:
    """Graph verschachtelt die Adresse unter 'emailAddress'."""
    return (recipient or {}).get("emailAddress") or {}


def _fmt(ea: dict) -> str:
    name = (ea.get("name") or "").strip()
    addr = (ea.get("address") or "").strip()
    if addr and name and name.lower() != addr.lower():
        return f"{name} <{addr}>"
    return addr or name


def format_from(msg_from: dict | None) -> str:
    return _fmt(_email_address(msg_from))


def format_recipients(recipients: list | None) -> str:
    parts = [_fmt(_email_address(r)) for r in (recipients or [])]
    return "; ".join(p for p in parts if p)


_DOMAIN_RE = re.compile(r"@([^@>\s;,]+)")


def addr_domain(value: str) -> str:
    """Domain aus 'Name <a@b.de>' oder 'a@b.de'; leer, wenn nicht gefunden."""
    m = _DOMAIN_RE.search(value or "")
    return m.group(1).strip().lower().rstrip(".") if m else ""


def _recipient_domain(recipient: dict) -> str:
    addr = (_email_address(recipient).get("address") or "")
    return addr.split("@")[-1].strip().lower().rstrip(".") if "@" in addr else ""


def classify_direction(msg: dict) -> str:
    """Einfache Heuristik: ein / aus / intern anhand der Firmen-Domains.

    Absender firmenich + mind. 1 externer Empfaenger  -> 'aus'
    Absender firmenich + nur interne Empfaenger        -> 'intern'
    Absender extern                                    -> 'ein'
    Kein Absender (z. B. Entwurf)                       -> '' (unbekannt)
    """
    from_domain = addr_domain(format_from(msg.get("from")))
    if not from_domain:
        return ""
    from_intern = from_domain in FIRMENICH_DOMAINS
    recipient_domains = [
        d
        for key in ("toRecipients", "ccRecipients", "bccRecipients")
        for r in (msg.get(key) or [])
        if (d := _recipient_domain(r))
    ]
    if from_intern:
        any_external = any(d not in FIRMENICH_DOMAINS for d in recipient_domains)
        return "aus" if any_external else "intern"
    return "ein"
