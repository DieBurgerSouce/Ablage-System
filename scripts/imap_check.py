# -*- coding: utf-8 -*-
"""IMAP-Postfach-Test fuer die zentrale Rechnungsadresse (AP-6, Go-Live-Runbook).

Prueft VOR der UI-Konfiguration (admin.imports.email), ob das Postfach mit
IMAP+Passwort erreichbar ist — genau das (und nur das) kann der E-Mail-Import
(kein OAuth2/XOAUTH2 im Code, Grep 2026-07-11). Erkennt insbesondere die
Microsoft-365-Falle: M365 hat Basic-Auth-IMAP deaktiviert, ein
M365-Postfach scheitert hier IMMER am Login (Runbook E-6: Postfach beim
Bestands-Mailhoster nutzen oder M365-Weiterleitung dorthin).

Aufruf (Host oder Container, nur Stdlib):

    python scripts/imap_check.py --host imap.example.de --user rechnung@firmenich.de
    (Passwort wird interaktiv abgefragt; alternativ --password-env IMAP_PASSWORD)

Exit-Code 0 = Login OK (INBOX zaehlbar), 1 = FAIL (mit deutschem Hinweis).

Feinpoliert und durchdacht.
"""
from __future__ import annotations

import argparse
import getpass
import imaplib
import os
import socket
import ssl
import sys
from typing import Optional, Sequence

# M365-/Exchange-Online-Hosts: Basic-Auth-IMAP ist dort abgeschaltet.
_M365_HOST_MARKERS = ("office365.com", "outlook.com", "office.com")

_NETWORK_ERROR_MARKERS = (
    "timed out",
    "timeout",
    "refused",
    "unreachable",
    "getaddrinfo",
    "name or service not known",
)


def is_m365_host(host: str) -> bool:
    """Erkennt Microsoft-365-/Exchange-Online-IMAP-Hosts."""
    lowered = (host or "").strip().lower()
    return any(lowered.endswith(marker) or marker in lowered for marker in _M365_HOST_MARKERS)


def failure_hint(host: str, error_text: str) -> str:
    """Deutscher Hinweistext fuer einen fehlgeschlagenen IMAP-Test."""
    lowered = (error_text or "").lower()
    if any(marker in lowered for marker in _NETWORK_ERROR_MARKERS):
        return (
            f"Server {host}:993 nicht erreichbar — DNS/Port/Firewall pruefen "
            "(openssl s_client -connect <host>:993 als Gegenprobe)."
        )
    if is_m365_host(host):
        return (
            "Login fehlgeschlagen — das ist die erwartete Microsoft-365-Falle: "
            "M365 erlaubt kein Basic-Auth-IMAP mehr, nur OAuth2, und der "
            "E-Mail-Import der Ablage kann ausschliesslich Passwort-Login. "
            "Runbook E-6: Postfach beim Bestands-Mailhoster anlegen ODER "
            "M365-Weiterleitung auf ein solches Postfach einrichten."
        )
    return (
        "Login fehlgeschlagen — Zugangsdaten pruefen (Benutzer = volle "
        "E-Mail-Adresse? App-Passwort noetig? IMAP im Postfach aktiviert?)."
    )


def run_check(host: str, port: int, user: str, password: str) -> int:
    """Fuehrt den echten IMAP-SSL-Login aus. 0 = OK, 1 = FAIL."""
    print(f"Verbinde {host}:{port} (SSL) ...", flush=True)
    try:
        context = ssl.create_default_context()
        with imaplib.IMAP4_SSL(host, port, ssl_context=context, timeout=20) as client:
            print("TLS-Verbindung steht. Login ...", flush=True)
            client.login(user, password)
            status, data = client.select("INBOX", readonly=True)
            count = data[0].decode() if status == "OK" and data and data[0] else "?"
            print(f"PASS: Login OK, INBOX enthaelt {count} Nachrichten.", flush=True)
            print(
                "Naechster Schritt: Konfiguration in der UI unter "
                "admin/imports/email anlegen (Intervall 5 min, auto_ocr an).",
                flush=True,
            )
            return 0
    except (imaplib.IMAP4.error, ssl.SSLError, OSError, socket.error) as exc:
        print(f"FAIL: {exc}", flush=True)
        print(f"Hinweis: {failure_hint(host, str(exc))}", flush=True)
        return 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="IMAP-Login-Test fuer die zentrale Rechnungsadresse (Runbook AP-6/V7)"
    )
    parser.add_argument("--host", required=True, help="IMAP-Server, z.B. imap.example.de")
    parser.add_argument("--port", type=int, default=993, help="IMAP-SSL-Port (Default 993)")
    parser.add_argument("--user", required=True, help="Login (meist die volle E-Mail-Adresse)")
    parser.add_argument(
        "--password-env",
        default=None,
        metavar="VAR",
        help="Passwort aus dieser Umgebungsvariable lesen (statt interaktiv)",
    )
    args = parser.parse_args(argv)

    if is_m365_host(args.host):
        print(
            "WARNUNG: Das sieht nach Microsoft 365 aus — Basic-Auth-IMAP ist "
            "dort deaktiviert; der Test wird voraussichtlich scheitern (E-6).",
            flush=True,
        )

    password = os.environ.get(args.password_env) if args.password_env else None
    if not password:
        password = getpass.getpass(f"IMAP-Passwort fuer {args.user}: ")

    return run_check(args.host, args.port, args.user, password)


if __name__ == "__main__":
    sys.exit(main())
