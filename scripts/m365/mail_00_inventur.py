#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mail_00_inventur.py — M365-Postfach-Inventur (Phase P0, REIN LESEND / nur GET).

Ermittelt fuer den Tenant „spargelmesserfirmenich":
  1. alle Nutzer (inkl. deaktiviert/unlizenziert) + Postfach-Existenz-Probe
  2. Nutzungsbericht (getMailboxUsageDetail, D7): Items, GB, geloeschte Items, Archiv
  3. je Postfach rekursive Ordner-Zaehlung (Soll-Zahlen fuer die spaetere Verifikation)

Ausgabe: inventur_report.csv + inventur_report.md (+ optional .json) im STAGING_ROOT
(Fallback: aktuelles Verzeichnis mit Warnung) sowie eine Konsolen-Zusammenfassung.

Schreibt NICHTS nach M365. Einrichtung/Zugangsdaten: RUNBOOK_P0_BEN.md.

Aufruf:
    python mail_00_inventur.py [--no-folders] [--limit-users N] [--json] [--period D7]
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

# Sicherstellen, dass das Paket mail_lib gefunden wird (Skript-Verzeichnis).
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Konsole auf UTF-8, damit Umlaute/Sonderzeichen unter Windows nicht zu Fehlern fuehren.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

from mail_lib import config  # noqa: E402
from mail_lib import log as mlog  # noqa: E402
from mail_lib.auth import AuthError, TokenProvider  # noqa: E402
from mail_lib.graph import GraphClient, GraphError  # noqa: E402

USER_SELECT = "id,userPrincipalName,displayName,mail,accountEnabled,userType,assignedLicenses"

_GUID_RE = re.compile(r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$")

# Spaltennamen des Nutzungsberichts (stabil englisch), klein geschrieben.
_REPORT_COLS = {
    "upn": "user principal name",
    "display": "display name",
    "is_deleted": "is deleted",
    "last_activity": "last activity date",
    "items": "item count",
    "storage": "storage used (byte)",
    "deleted_items": "deleted item count",
    "deleted_size": "deleted item size (byte)",
    "has_archive": "has archive",
}

_log = mlog.get_logger("inventur")


# --------------------------------------------------------------------------- #
# Hilfsfunktionen
# --------------------------------------------------------------------------- #
def _pathseg(value: str) -> str:
    """UPN/ID fuer den URL-Pfad kodieren ('#' bei Gast-UPNs muss escaped werden)."""
    return quote(value or "", safe="@")


def _to_int(value: str) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _norm(value: str) -> str:
    return (value or "").strip().lower()


def _yn(value) -> str:
    if value is None:
        return ""
    return "ja" if value else "nein"


def _gb(bytes_value) -> float | None:
    if bytes_value is None:
        return None
    return round(bytes_value / 1e9, 2)


# --------------------------------------------------------------------------- #
# Graph-Abrufe (alle rein lesend)
# --------------------------------------------------------------------------- #
def enumerate_users(client: GraphClient, limit: int | None) -> list[dict]:
    params = {"$select": USER_SELECT, "$top": "999"}
    users: list[dict] = []
    for user in client.get_paged("/v1.0/users", params):
        users.append(user)
        if limit and len(users) >= limit:
            break
    return users


def probe_mailbox(client: GraphClient, user_ref: str) -> tuple[bool, str]:
    """Postfach-Existenz via msgfolderroot. 404 = kein Postfach; 403 = kein Zugriff."""
    try:
        client.get(f"/v1.0/users/{_pathseg(user_ref)}/mailFolders/msgfolderroot",
                   params={"$select": "id"})
        return True, ""
    except GraphError as exc:
        if exc.status == 404:
            return False, "kein Postfach"
        if exc.status == 403:
            return False, "kein Zugriff (evtl. AccessPolicy)"
        return False, f"Probe-Fehler {exc.status}"


def count_folders(client: GraphClient, upn: str) -> tuple[int, int, int]:
    """Rekursive Ordner-Zaehlung. Liefert (Items-Summe, Ordner-Anzahl, Items in Geloescht)."""
    total_items = 0
    folder_count = 0
    deleted_items = 0
    select = "id,displayName,totalItemCount,unreadItemCount,wellKnownName,childFolderCount"

    def walk(list_url: str, depth: int) -> None:
        nonlocal total_items, folder_count, deleted_items
        if depth > 20:  # Schutz vor pathologisch tiefen Baeumen
            return
        params = {"$top": "200", "includeHiddenFolders": "true", "$select": select}
        for folder in client.get_paged(list_url, params):
            folder_count += 1
            count = folder.get("totalItemCount") or 0
            total_items += count
            if (folder.get("wellKnownName") or "") == "deleteditems":
                deleted_items = count
            if (folder.get("childFolderCount") or 0) > 0:
                # /beta noetig: v1.0-$select kennt wellKnownName auf mailFolder nicht (400).
                child_url = f"/beta/users/{_pathseg(upn)}/mailFolders/{folder['id']}/childFolders"
                walk(child_url, depth + 1)

    walk(f"/beta/users/{_pathseg(upn)}/mailFolders", 0)
    return total_items, folder_count, deleted_items


def fetch_usage_report(client: GraphClient, period: str) -> tuple[list[dict], bool]:
    """getMailboxUsageDetail (CSV; Redirect wird OHNE Auth-Header verfolgt)."""
    url = f"/v1.0/reports/getMailboxUsageDetail(period='{period}')"
    text = client.get_report_csv(url)
    rows = parse_usage_csv(text)
    return rows, detect_obfuscation(rows)


def parse_usage_csv(text: str) -> list[dict]:
    text = text.lstrip("﻿")
    reader = csv.reader(io.StringIO(text))
    table = [r for r in reader if r]
    if not table:
        return []
    header = [h.strip().lower() for h in table[0]]

    def idx(col_key: str) -> int:
        name = _REPORT_COLS[col_key]
        return header.index(name) if name in header else -1

    ix = {k: idx(k) for k in _REPORT_COLS}
    out: list[dict] = []
    for row in table[1:]:
        if all(not c.strip() for c in row):
            continue

        def val(col_key: str) -> str:
            i = ix[col_key]
            return row[i].strip() if 0 <= i < len(row) else ""

        out.append({
            "upn": val("upn"),
            "display": val("display"),
            "is_deleted": val("is_deleted"),
            "last_activity": val("last_activity"),
            "items": _to_int(val("items")),
            "storage": _to_int(val("storage")),
            "deleted_items": _to_int(val("deleted_items")),
            "deleted_size": _to_int(val("deleted_size")),
            "has_archive": val("has_archive"),
        })
    return out


def detect_obfuscation(rows: list[dict]) -> bool:
    """Verschleierte Namen: UPNs ohne '@' bzw. reine GUIDs bei >= Haelfte der Zeilen."""
    if not rows:
        return False
    concealed = sum(1 for r in rows if ("@" not in r["upn"]) or _GUID_RE.match(r["upn"] or ""))
    return concealed >= max(1, len(rows) // 2)


# --------------------------------------------------------------------------- #
# Datensatz-Aufbau
# --------------------------------------------------------------------------- #
def new_record(upn: str, display: str = "") -> dict:
    return {
        "upn": upn,
        "display": display,
        "enabled": None,
        "lizenziert": None,
        "usertype": "",
        "mailbox_vorhanden": None,
        "items_report": None,
        "gb_report": None,
        "deleted_items": None,
        "has_archive": "",
        "items_folders_summe": None,
        "ordner_anzahl": None,
        "last_activity": "",
        "hinweis": "",
    }


def add_hint(rec: dict, text: str) -> None:
    rec["hinweis"] = f"{rec['hinweis']}; {text}".strip("; ") if rec["hinweis"] else text


def collect(client: GraphClient, users: list[dict], do_folders: bool) -> dict[str, dict]:
    records: dict[str, dict] = {}
    n = len(users)
    for i, user in enumerate(users, 1):
        upn = user.get("userPrincipalName") or ""
        rec = new_record(upn, user.get("displayName") or "")
        rec["enabled"] = bool(user.get("accountEnabled"))
        rec["lizenziert"] = bool(user.get("assignedLicenses"))
        rec["usertype"] = user.get("userType") or ""

        exists, note = probe_mailbox(client, user.get("id") or upn)
        rec["mailbox_vorhanden"] = exists
        if note:
            add_hint(rec, note)

        if exists and do_folders:
            try:
                items, folders, deleted = count_folders(client, upn)
                rec["items_folders_summe"] = items
                rec["ordner_anzahl"] = folders
                rec["deleted_items"] = deleted
            except GraphError as exc:
                add_hint(rec, f"Ordnerzaehlung fehlgeschlagen ({exc.status})")

        records[_norm(upn)] = rec
        _log.info("[%d/%d] %s — Postfach=%s%s", i, n, upn or "(ohne UPN)",
                  _yn(exists), f", Ordner={rec['ordner_anzahl']}" if rec["ordner_anzahl"] is not None else "")
    return records


def merge_report(records: dict[str, dict], rows: list[dict]) -> None:
    for r in rows:
        key = _norm(r["upn"])
        rec = records.get(key)
        if rec is None:
            rec = new_record(r["upn"], r["display"])
            rec["mailbox_vorhanden"] = True  # taucht im Nutzungsbericht auf
            add_hint(rec, "nur im Nutzungsbericht (evtl. Shared/Funktionspostfach)")
            records[key] = rec
        rec["items_report"] = r["items"]
        rec["gb_report"] = _gb(r["storage"])
        rec["deleted_items"] = r["deleted_items"] if r["deleted_items"] is not None else rec["deleted_items"]
        rec["last_activity"] = r["last_activity"]
        ha = (r["has_archive"] or "").strip().lower()
        rec["has_archive"] = "ja" if ha in ("true", "1", "yes", "ja") else ("nein" if ha in ("false", "0", "no", "nein") else "")
        if (r.get("is_deleted") or "").strip().lower() in ("true", "1", "yes", "ja"):
            add_hint(rec, "im Bericht als geloescht markiert")


# --------------------------------------------------------------------------- #
# Ausgabe
# --------------------------------------------------------------------------- #
CSV_COLUMNS = [
    "upn", "display", "enabled", "lizenziert", "mailbox_vorhanden",
    "items_report", "gb_report", "deleted_items", "has_archive",
    "items_folders_summe", "ordner_anzahl", "last_activity", "hinweis",
]


def _sorted_records(records: dict[str, dict]) -> list[dict]:
    return sorted(records.values(), key=lambda r: (-(r["gb_report"] or 0.0), r["upn"].lower()))


def write_csv(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(CSV_COLUMNS)
        for r in records:
            writer.writerow([
                r["upn"], r["display"], _yn(r["enabled"]), _yn(r["lizenziert"]),
                _yn(r["mailbox_vorhanden"]),
                r["items_report"] if r["items_report"] is not None else "",
                r["gb_report"] if r["gb_report"] is not None else "",
                r["deleted_items"] if r["deleted_items"] is not None else "",
                r["has_archive"],
                r["items_folders_summe"] if r["items_folders_summe"] is not None else "",
                r["ordner_anzahl"] if r["ordner_anzahl"] is not None else "",
                r["last_activity"], r["hinweis"],
            ])


def _md_row(r: dict) -> str:
    return "| {upn} | {mb} | {en} | {lz} | {gb} | {ir} | {fs} | {oc} | {di} | {ar} | {la} |".format(
        upn=r["upn"] or "—",
        mb=_yn(r["mailbox_vorhanden"]),
        en=_yn(r["enabled"]),
        lz=_yn(r["lizenziert"]),
        gb=f'{r["gb_report"]:.2f}' if r["gb_report"] is not None else "—",
        ir=r["items_report"] if r["items_report"] is not None else "—",
        fs=r["items_folders_summe"] if r["items_folders_summe"] is not None else "—",
        oc=r["ordner_anzahl"] if r["ordner_anzahl"] is not None else "—",
        di=r["deleted_items"] if r["deleted_items"] is not None else "—",
        ar=r["has_archive"] or "—",
        la=r["last_activity"] or "—",
    )


def write_md(path: Path, records: list[dict], *, period: str, obfuscated: bool,
             out_fallback: bool) -> dict:
    total_gb = sum((r["gb_report"] or 0.0) for r in records)
    total_items_report = sum((r["items_report"] or 0) for r in records)
    total_items_folders = sum((r["items_folders_summe"] or 0) for r in records)
    mailboxes = [r for r in records if r["mailbox_vorhanden"]]
    archives = [r for r in records if r["has_archive"] == "ja"]
    disabled_with_mb = [r for r in records if r["enabled"] is False and r["mailbox_vorhanden"]]
    report_only = [r for r in records if "nur im Nutzungsbericht" in r["hinweis"]]
    ssd_gb = math.ceil(total_gb * 1.2)

    lines: list[str] = []
    lines.append("# M365-Postfach-Inventur (Phase P0)")
    lines.append("")
    lines.append(f"- **Erstellt:** {datetime.now():%Y-%m-%d %H:%M}")
    lines.append(f"- **Nutzungsbericht-Zeitraum:** {period}")
    lines.append("- **Zugriff:** rein lesend (Microsoft Graph, nur GET) — keine Aenderung an M365")
    lines.append(f"- **Postfaecher gesamt:** {len(mailboxes)} (Datensaetze inkl. ohne Postfach: {len(records)})")
    lines.append("")
    lines.append("## Zusammenfassung")
    lines.append("")
    lines.append(f"- Summe Speicher (Bericht): **{total_gb:.2f} GB**")
    lines.append(f"- Summe Items (Bericht): **{total_items_report:,}**".replace(",", "."))
    if total_items_folders:
        lines.append(f"- Summe Items (Ordner-Zaehlung): **{total_items_folders:,}**".replace(",", "."))
    lines.append(f"- **Grobe SSD-Empfehlung: ~{ssd_gb} GB** (Σ Postfach-GB × 1,2)")
    lines.append("  - Reserve fuer EML-/Anhang-Overhead und Wachstum separat einplanen (Plan S1.1).")
    lines.append("")

    if obfuscated:
        lines.append("> ⚠️ **Verschleierte Namen aktiv.** Der Nutzungsbericht liefert anonymisierte UPNs/Namen.")
        lines.append("> Bitte im Admin-Center deaktivieren (Runbook Abschnitt 4) und die Inventur erneut laufen lassen.")
        lines.append("")

    lines.append("## Postfaecher (nach Speicher absteigend)")
    lines.append("")
    lines.append("| UPN | Postfach | Aktiv | Lizenz | GB | Items(B) | Items(O) | Ordner | Geloescht | Archiv | Letzte Aktivitaet |")
    lines.append("|---|---|---|---|---:|---:|---:|---:|---:|---|---|")
    for r in records:
        lines.append(_md_row(r))
    lines.append("")

    lines.append("## Auffaelligkeiten")
    lines.append("")
    lines.append("### Groesste Postfaecher (Top 5)")
    for r in [x for x in records if x["gb_report"]][:5]:
        lines.append(f"- **{r['upn']}** — {r['gb_report']:.2f} GB, {r['items_report'] or '—'} Items")
    if not any(x["gb_report"] for x in records):
        lines.append("- (keine GB-Daten — Nutzungsbericht leer oder verschleiert)")
    lines.append("")
    lines.append("### Archiv-Postfaecher (Online-Archiv aktiv)")
    if archives:
        for r in archives:
            lines.append(f"- {r['upn']} — Archiv=ja (Graph erreicht Online-Archive nicht zuverlaessig → Purview-PST-Fallback, Plan S1.3)")
    else:
        lines.append("- keine laut Bericht (EXO-Cross-Check bestaetigt ArchiveStatus zuverlaessiger)")
    lines.append("")
    lines.append("### Deaktivierte Accounts mit Postfach")
    if disabled_with_mb:
        for r in disabled_with_mb:
            lines.append(f"- {r['upn']} — deaktiviert, aber Postfach vorhanden (Ex-Mitarbeiter? Extrahieren!)")
    else:
        lines.append("- keine gefunden")
    lines.append("")
    lines.append("### Nur im Nutzungsbericht (Shared/Funktionspostfaecher?)")
    if report_only:
        for r in report_only:
            lines.append(f"- {r['upn']} — {(r['gb_report'] or 0):.2f} GB")
    else:
        lines.append("- keine")
    lines.append("")

    lines.append("## Naechste Schritte / offene Punkte")
    lines.append("")
    lines.append("- ⚠️ **EXO-PowerShell-Cross-Check** (Runbook Abschnitt 5): Shared/Archiv/Hold-Status, "
                 "die Graph nicht liefert — insbesondere **soft-deleted Postfaecher (Matthias!)** im 30-Tage-Fenster.")
    lines.append("- Diese Inventur deckt **aktive Postfaecher** ab; inaktive/Hold-Bestaende nur via Purview-eDiscovery (PST).")
    lines.append("- SSD-Groesse (E-S1) anhand obiger Summe festlegen.")
    if out_fallback:
        lines.append("- ⚠️ Report liegt im **aktuellen Verzeichnis** (STAGING_ROOT nicht gesetzt/vorhanden). "
                     "Nach SSD-Einrichtung STAGING_ROOT setzen und erneut laufen lassen.")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return {
        "postfaecher": len(mailboxes),
        "datensaetze": len(records),
        "total_gb": round(total_gb, 2),
        "total_items_report": total_items_report,
        "ssd_empfehlung_gb": ssd_gb,
        "archive": len(archives),
        "deaktiviert_mit_postfach": len(disabled_with_mb),
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="M365-Postfach-Inventur (rein lesend, nur GET).",
    )
    p.add_argument("--no-folders", action="store_true",
                   help="Ordner-Zaehlung je Postfach ueberspringen (schneller).")
    p.add_argument("--limit-users", type=int, default=None, metavar="N",
                   help="Nur die ersten N Nutzer verarbeiten (Testlauf).")
    p.add_argument("--json", action="store_true",
                   help="Zusaetzlich Rohdaten als inventur_report.json ablegen.")
    p.add_argument("--period", default="D7", choices=["D7", "D30", "D90", "D180"],
                   help="Zeitraum des Nutzungsberichts (Standard: D7).")
    return p


def resolve_out_dir(cfg: config.Config) -> tuple[Path, bool]:
    """Zielverzeichnis fuer die Reports: STAGING_ROOT wenn vorhanden, sonst CWD (Warnung)."""
    staging = cfg.staging_path()
    if staging and staging.is_dir():
        return staging, False
    return Path.cwd(), True


def run(args: argparse.Namespace) -> int:
    cfg = config.load()
    logfile = mlog.setup(staging_root=cfg.staging_root or None)
    _log.info("M365-Inventur startet (REIN LESEND). %s", cfg.summary())
    _log.info("Logdatei: %s", logfile)

    out_dir, fallback = resolve_out_dir(cfg)
    if fallback:
        _log.warning("STAGING_ROOT nicht gesetzt/vorhanden — Reports landen in: %s", out_dir)

    provider = TokenProvider(cfg)
    with GraphClient(provider) as client:
        _log.info("Nutzer werden aufgezaehlt …")
        users = enumerate_users(client, args.limit_users)
        _log.info("%d Nutzer gefunden%s.", len(users),
                  f" (limitiert auf {args.limit_users})" if args.limit_users else "")

        records = collect(client, users, do_folders=not args.no_folders)

        _log.info("Nutzungsbericht wird abgerufen (period=%s) …", args.period)
        try:
            rows, obfuscated = fetch_usage_report(client, args.period)
            _log.info("Nutzungsbericht: %d Zeilen%s.", len(rows),
                      " (VERSCHLEIERT!)" if obfuscated else "")
            merge_report(records, rows)
        except GraphError as exc:
            obfuscated = False
            rows = []
            _log.error("Nutzungsbericht fehlgeschlagen (%s): %s — CSV-Werte bleiben leer.",
                       exc.status, exc.detail)

    ordered = _sorted_records(records)
    csv_path = out_dir / "inventur_report.csv"
    md_path = out_dir / "inventur_report.md"
    write_csv(csv_path, ordered)
    summary = write_md(md_path, ordered, period=args.period, obfuscated=obfuscated,
                       out_fallback=fallback)

    if args.json:
        json_path = out_dir / "inventur_report.json"
        json_path.write_text(json.dumps(
            {"records": ordered, "report_rows": rows, "obfuscated": obfuscated},
            ensure_ascii=False, indent=2), encoding="utf-8")
        _log.info("Rohdaten: %s", json_path)

    _print_summary(summary, csv_path, md_path, obfuscated, fallback, client.request_count)
    return 0


def _print_summary(summary: dict, csv_path: Path, md_path: Path,
                   obfuscated: bool, fallback: bool, requests: int) -> None:
    print("")
    print("==================  M365-INVENTUR (rein lesend)  ==================")
    print(f"  Postfaecher (mit Mailbox) : {summary['postfaecher']}")
    print(f"  Datensaetze gesamt        : {summary['datensaetze']}")
    print(f"  Speicher (Bericht)        : {summary['total_gb']:.2f} GB")
    print(f"  Items (Bericht)           : {summary['total_items_report']:,}".replace(",", "."))
    print(f"  Online-Archive            : {summary['archive']}")
    print(f"  Deaktiviert + Postfach    : {summary['deaktiviert_mit_postfach']}")
    print(f"  >> Grobe SSD-Empfehlung   : ~{summary['ssd_empfehlung_gb']} GB (Summe GB x 1,2)")
    print(f"  Graph-Anfragen            : {requests}")
    print("  ---------------------------------------------------------------")
    print(f"  CSV : {csv_path}")
    print(f"  MD  : {md_path}")
    if obfuscated:
        print("  [!] VERSCHLEIERTE NAMEN aktiv - Runbook Abschnitt 4, dann erneut laufen lassen.")
    if fallback:
        print("  [!] STAGING_ROOT fehlt - Reports im aktuellen Verzeichnis (SSD einrichten!).")
    print("  [!] Naechster Pflichtschritt: EXO-Cross-Check (Runbook 5), v. a. Soft-Delete/Matthias.")
    print("===================================================================")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except config.ConfigError as exc:
        print(f"\n[KONFIG-FEHLER]\n{exc}\n", file=sys.stderr)
        return 2
    except AuthError as exc:
        print(f"\n[AUTH-FEHLER] {exc}\nSiehe RUNBOOK_P0_BEN.md (Abschnitte 2, 3).\n", file=sys.stderr)
        return 3
    except GraphError as exc:
        print(f"\n[GRAPH-FEHLER] {exc}\n", file=sys.stderr)
        return 4
    except RuntimeError as exc:  # z. B. fehlendes msal/httpx
        print(f"\n[FEHLER] {exc}\n", file=sys.stderr)
        return 5
    except KeyboardInterrupt:
        print("\nAbgebrochen.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
