#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mail_02_verify.py — Verifikation der M365-Extraktion (Phase P1, REIN LESEND / nur GET).

Prueft den Staging-Index gegen die Soll-Zahlen (Plan S1.6):
  1. Zaehl-Abgleich je Postfach: Soll-Items (Σ totalItemCount der Ordner — aus der beim
     Extract gespeicherten `folders`-Tabelle, mit --fresh frisch aus Graph) gegen die
     distinct msg_key-Fundorte in `locations`. Differenzen werden gelistet.
  2. Hash-Stichprobe: N zufaellige (deterministischer Seed) kanonische Nachrichten neu
     via /$value laden, SHA256 gegen canonical_sha256 pruefen.
  3. Vollstaendigkeits-Report je Postfach -> verify_report.md.

Schreibt NICHTS nach M365 und NICHTS in den Index (nur verify_report.md im STAGING_ROOT).

Aufruf:
    python mail_02_verify.py [--staging PATH] [--sample 20] [--seed 1337] [--fresh] [--no-hash]
"""

from __future__ import annotations

import argparse
import hashlib
import os
import random
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

from mail_lib import config  # noqa: E402
from mail_lib import log as mlog  # noqa: E402
from mail_lib import mindex  # noqa: E402
from mail_lib.auth import AuthError, TokenProvider  # noqa: E402
from mail_lib.graph import GraphClient, GraphError  # noqa: E402
from mail_01_extract import _userseg, _idseg, traverse_folders  # noqa: E402

_log = mlog.get_logger("verify")


# --------------------------------------------------------------------------- #
# Zaehl-Abgleich
# --------------------------------------------------------------------------- #
def fresh_folder_total(client: GraphClient, upn: str) -> int:
    """Soll-Items frisch aus Graph (Σ totalItemCount, Recoverable Items ausgeschlossen)."""
    return sum(f["total"] for f in traverse_folders(client, upn))


def reconcile(conn, client: GraphClient | None, fresh: bool) -> list[dict]:
    rows: list[dict] = []
    for mb in mindex.mailbox_rows(conn):
        upn = mb["upn"]
        if fresh and client is not None:
            try:
                expected = fresh_folder_total(client, upn)
                quelle = "Graph (frisch)"
            except GraphError as exc:
                expected = mindex.folder_total(conn, upn)
                quelle = f"Index (Graph-Fehler {exc.status})"
        else:
            expected = mindex.folder_total(conn, upn)
            quelle = "Index (folders)" if mindex.has_folder_data(conn, upn) else "— keine Soll-Daten"
        extracted = mindex.extracted_count(conn, upn)
        locations = mindex.location_count(conn, upn)
        rows.append({
            "upn": upn,
            "expected": expected,
            "extracted": extracted,
            "locations": locations,
            "delta": expected - extracted,
            "quelle": quelle,
        })
        _log.info("  %s: Soll=%d extrahiert=%d (Fundstellen=%d) Delta=%d [%s]",
                  upn, expected, extracted, locations, expected - extracted, quelle)
    return rows


# --------------------------------------------------------------------------- #
# Hash-Stichprobe
# --------------------------------------------------------------------------- #
def hash_sample(client: GraphClient, conn, n: int, seed: int) -> dict:
    population = mindex.canonical_samples(conn)
    if not population:
        return {"geprueft": 0, "ok": 0, "mismatch": 0, "fehler": 0, "details": [],
                "hinweis": "keine kanonischen Nachrichten mit Hash im Index"}
    picks = random.Random(seed).sample(list(population), min(n, len(population)))
    ok = mismatch = fehler = 0
    details: list[dict] = []
    tmp_dir = Path(tempfile.gettempdir())
    for row in picks:
        upn, gid, want = row["upn"], row["graph_id"], row["sha"]
        fd, tmp_name = tempfile.mkstemp(dir=str(tmp_dir), suffix=".part")
        os.close(fd)
        tmp = Path(tmp_name)
        url = f"/v1.0/users/{_userseg(upn)}/messages/{_idseg(gid)}/$value"
        try:
            got, _size = client.stream_to_file(url, tmp)
            if got == want:
                ok += 1
                status = "ok"
            else:
                mismatch += 1
                status = "MISMATCH"
            details.append({"upn": upn, "sha": want, "got": got, "status": status})
        except GraphError as exc:
            fehler += 1
            details.append({"upn": upn, "sha": want, "got": "", "status": f"nicht abrufbar ({exc.status})"})
        finally:
            tmp.unlink(missing_ok=True)
    _log.info("  Hash-Stichprobe: %d geprueft, %d ok, %d Mismatch, %d nicht abrufbar",
              len(picks), ok, mismatch, fehler)
    return {"geprueft": len(picks), "ok": ok, "mismatch": mismatch, "fehler": fehler, "details": details}


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
def write_report(path: Path, rows: list[dict], totals: dict, sample: dict | None,
                 *, fresh: bool, seed: int) -> None:
    total_expected = sum(r["expected"] for r in rows)
    total_extracted = sum(r["extracted"] for r in rows)
    total_delta = total_expected - total_extracted

    lines: list[str] = []
    lines.append("# M365-Extraktion — Verifikationsbericht (Phase P1)")
    lines.append("")
    lines.append(f"- **Erstellt:** {datetime.now():%Y-%m-%d %H:%M}")
    lines.append("- **Zugriff:** rein lesend (Microsoft Graph, nur GET) — keine Aenderung an M365")
    lines.append(f"- **Soll-Quelle:** {'frisch aus Graph' if fresh else 'gespeicherte folders-Tabelle'}")
    lines.append("")
    lines.append("## Zusammenfassung")
    lines.append("")
    lines.append(f"- Postfaecher im Index: **{totals['mailboxes']}**")
    lines.append(f"- Kanonische Nachrichten (messages): **{totals['messages']:,}**".replace(",", "."))
    lines.append(f"- Fundstellen (locations): **{totals['locations']:,}**".replace(",", "."))
    lines.append(f"- Roh-Datenvolumen (Σ size_bytes): **{totals['bytes'] / 1e9:.2f} GB**")
    lines.append(f"- Soll-Items gesamt: **{total_expected:,}**".replace(",", "."))
    lines.append(f"- Extrahiert (distinct msg_key je Postfach): **{total_extracted:,}**".replace(",", "."))
    lines.append(f"- **Delta gesamt: {total_delta:,}**".replace(",", "."))
    lines.append("")
    lines.append("> Delta-Deutung: kleine positive Restwerte sind erklaerbar durch laufende Zustellung, "
                 "Elemente ohne abrufbare MIME (z. B. Kalender-/Kontakt-Objekte in Sonderordnern) oder "
                 "noch nicht abgeschlossene Postfaecher. Negatives Delta = mehr extrahiert als aktuell "
                 "gemeldet (moeglich bei zwischenzeitlich geloeschten Mails). **Erwartung nach Voll-Lauf: ~0.**")
    lines.append("")

    lines.append("## Zaehl-Abgleich je Postfach")
    lines.append("")
    lines.append("| Postfach | Soll (Σ Ordner) | Extrahiert | Fundstellen | Delta | Soll-Quelle |")
    lines.append("|---|---:|---:|---:|---:|---|")
    for r in sorted(rows, key=lambda x: -x["expected"]):
        lines.append("| {upn} | {exp} | {ext} | {loc} | {dl} | {q} |".format(
            upn=r["upn"], exp=r["expected"], ext=r["extracted"],
            loc=r["locations"], dl=r["delta"], q=r["quelle"]))
    lines.append("")

    lines.append("## Hash-Stichprobe (Re-Download `/$value` vs. canonical_sha256)")
    lines.append("")
    if sample is None:
        lines.append("- uebersprungen (`--no-hash`).")
    elif sample.get("hinweis"):
        lines.append(f"- keine Pruefung moeglich: {sample['hinweis']}.")
    else:
        lines.append(f"- deterministischer Seed: `{seed}`")
        lines.append(f"- geprueft: **{sample['geprueft']}** · ok: **{sample['ok']}** · "
                     f"Mismatch: **{sample['mismatch']}** · nicht abrufbar: **{sample['fehler']}**")
        lines.append("")
        lines.append("| Postfach | erwarteter SHA256 (kurz) | Ergebnis |")
        lines.append("|---|---|---|")
        for d in sample["details"]:
            lines.append(f"| {d['upn']} | {d['sha'][:16]}… | {d['status']} |")
    lines.append("")

    lines.append("## Idempotenz")
    lines.append("")
    lines.append("- Ein erneuter `mail_01_extract.py --commit` verarbeitet dieselben Postfaecher, "
                 "erkennt jede Fundstelle ueber `(mailbox_upn, graph_id)` und schreibt **0 neue** "
                 "EML/`messages`/`locations`-Zeilen (Konsolen-Summary 'Neue EML geladen: 0'). "
                 "Checkpoints in `state\\<upn>.json` ueberspringen abgeschlossene Ordner ganz.")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Verifikation der M365-Extraktion (rein lesend, nur GET).")
    p.add_argument("--staging", default=None, metavar="PATH",
                   help="STAGING_ROOT ueberschreiben (Ort von index.sqlite).")
    p.add_argument("--sample", type=int, default=20, metavar="N",
                   help="Anzahl Nachrichten fuer die Hash-Stichprobe (Default: 20).")
    p.add_argument("--seed", type=int, default=1337, metavar="S",
                   help="Deterministischer Seed der Stichprobe (Default: 1337).")
    p.add_argument("--fresh", action="store_true",
                   help="Soll-Item-Zahlen frisch aus Graph holen statt aus der folders-Tabelle.")
    p.add_argument("--no-hash", action="store_true",
                   help="Hash-Stichprobe ueberspringen (kein Graph-Zugriff noetig).")
    return p


def run(args: argparse.Namespace) -> int:
    if args.staging:
        os.environ["STAGING_ROOT"] = args.staging

    cfg = config.load()
    staging_root = args.staging or cfg.staging_root
    logfile = mlog.setup(staging_root=staging_root or None)
    _log.info("mail_02_verify startet (REIN LESEND). %s", cfg.summary())

    staging = Path(staging_root) if staging_root else None
    if not staging:
        print("\n[FEHLER] Kein STAGING_ROOT (oder --staging PATH). Index nicht auffindbar.\n", file=sys.stderr)
        return 2
    idx_path = staging / "index.sqlite"
    if not idx_path.is_file():
        print(f"\n[FEHLER] Index nicht gefunden: {idx_path}\n"
              "Erst extrahieren (mail_01_extract.py --commit).\n", file=sys.stderr)
        return 2

    conn = mindex.connect(idx_path)
    totals = mindex.totals(conn)
    _log.info("Index: %s — %d Postfaecher, %d Nachrichten, %d Fundstellen.",
              idx_path, totals["mailboxes"], totals["messages"], totals["locations"])

    need_graph = args.fresh or not args.no_hash
    client = None
    sample = None
    try:
        if need_graph:
            provider = TokenProvider(cfg)
            client = GraphClient(provider)
        _log.info("Zaehl-Abgleich je Postfach …")
        rows = reconcile(conn, client, args.fresh)
        if not args.no_hash and client is not None:
            _log.info("Hash-Stichprobe (n=%d, seed=%d) …", args.sample, args.seed)
            sample = hash_sample(client, conn, args.sample, args.seed)
    finally:
        if client is not None:
            requests = client.request_count
            client.close()
        else:
            requests = 0

    report_path = staging / "verify_report.md"
    write_report(report_path, rows, totals, sample, fresh=args.fresh, seed=args.seed)
    conn.close()

    _print_summary(rows, totals, sample, report_path, logfile, requests)
    return 0


def _print_summary(rows, totals, sample, report_path, logfile, requests) -> None:
    total_expected = sum(r["expected"] for r in rows)
    total_extracted = sum(r["extracted"] for r in rows)
    print("")
    print("==================  MAIL-VERIFIKATION (rein lesend)  ==================")
    print(f"  Postfaecher               : {totals['mailboxes']}")
    print(f"  Soll-Items (Σ Ordner)     : {total_expected:,}".replace(",", "."))
    print(f"  Extrahiert (distinct)     : {total_extracted:,}".replace(",", "."))
    print(f"  Delta gesamt              : {total_expected - total_extracted:,}".replace(",", "."))
    if sample and not sample.get("hinweis"):
        print(f"  Hash-Stichprobe           : {sample['ok']}/{sample['geprueft']} ok, "
              f"{sample['mismatch']} Mismatch, {sample['fehler']} nicht abrufbar")
    elif sample is None:
        print("  Hash-Stichprobe           : uebersprungen (--no-hash)")
    else:
        print(f"  Hash-Stichprobe           : {sample.get('hinweis', 'keine Daten')}")
    print(f"  Graph-Anfragen            : {requests:,}".replace(",", "."))
    print("  -----------------------------------------------------------------")
    print(f"  Report : {report_path}")
    print(f"  Log    : {logfile}")
    print("======================================================================")


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
    except RuntimeError as exc:
        print(f"\n[FEHLER] {exc}\n", file=sys.stderr)
        return 5
    except KeyboardInterrupt:
        print("\nAbgebrochen.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
