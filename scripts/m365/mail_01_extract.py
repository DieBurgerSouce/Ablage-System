#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mail_01_extract.py — M365-Voll-Extraktion je Postfach (Phase P1, REIN LESEND / nur GET).

Je Postfach: Ordner-Traversal (inkl. „Geloeschte Elemente", OHNE „Wiederherstellbare
Elemente") -> Metadaten paginiert (receivedDateTime asc) -> Voll-MIME je Mail via
/$value streamend als .eml. Dedup global ueber internetMessageId (erste MIME = kanonisch),
weitere Fundstellen nur als locations-Zeile. Index: <STAGING_ROOT>\\index.sqlite (WAL).
Checkpoint/Resume je (Postfach, Ordner); Zweitlauf = 0 neue EML/Zeilen (idempotent).

Ohne --commit laeuft ein DRY-RUN: echte GET-Metadaten-Abfrage, aber es wird NICHTS
geschrieben (keine EML, kein Index) — nur gezaehlt/geplant.

Schreibt NICHTS nach M365. Einrichtung/Zugangsdaten: RUNBOOK_P0_BEN.md.

Aufruf (Beispiele):
    python mail_01_extract.py                                   # Dry-Run, alle Postfaecher
    python mail_01_extract.py --mailbox webmaster@firmenich.de --limit-mails 20
    python mail_01_extract.py --commit --staging E:\\m365_staging    # Voll-Lauf
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

# Paket mail_lib auffindbar machen (Skript-Verzeichnis).
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Konsole auf UTF-8, damit Umlaute unter Windows nicht scheitern.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

from mail_lib import config  # noqa: E402
from mail_lib import log as mlog  # noqa: E402
from mail_lib import mailboxes as mbx  # noqa: E402
from mail_lib import mindex  # noqa: E402
from mail_lib.auth import AuthError, TokenProvider  # noqa: E402
from mail_lib.graph import GraphClient, GraphError  # noqa: E402

_log = mlog.get_logger("extract")

# Metadaten-Auswahl je Nachricht (Plan S1.3).
MESSAGE_SELECT = (
    "id,internetMessageId,conversationId,conversationIndex,subject,from,"
    "toRecipients,ccRecipients,bccRecipients,receivedDateTime,sentDateTime,"
    "hasAttachments,isDraft,parentFolderId"
)
FOLDER_SELECT = "id,displayName,totalItemCount,wellKnownName,childFolderCount,parentFolderId"

# „Wiederherstellbare Elemente"/Dumpster — nie extrahieren (Plan S1.3).
RECOVERABLE_WKN = {
    "recoverableitemsroot", "recoverableitemsdeletions", "recoverableitemspurges",
    "recoverableitemsversions", "recoverableitemsdiscoveryholds",
    "recoverableitemssubstrateholds", "recoverableitemsaudits", "scheduledsends",
}


# --------------------------------------------------------------------------- #
# Kleine Helfer
# --------------------------------------------------------------------------- #
def _userseg(upn: str) -> str:
    return quote(upn or "", safe="@")


def _idseg(value: str) -> str:
    return quote(value or "", safe="")


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _safe_name(value: str) -> str:
    return "".join(c if (c.isalnum() or c in "@._-") else "_" for c in (value or ""))


def _short_subject(msg: dict, n: int = 60) -> str:
    s = (msg.get("subject") or "(ohne Betreff)").replace("\n", " ").strip()
    return s if len(s) <= n else s[:n] + "…"


def _is_recoverable(well_known: str, display: str) -> bool:
    if well_known in RECOVERABLE_WKN:
        return True
    low = (display or "").lower()
    return "wiederherstellbar" in low or "recoverable items" in low


# --------------------------------------------------------------------------- #
# Laufzeit-Kontext + Statistik
# --------------------------------------------------------------------------- #
@dataclass
class RunCtx:
    client: GraphClient
    conn: sqlite3.Connection | None
    staging: Path | None
    commit: bool
    run_id: str
    limit_mails: int | None
    sleep_ms: int
    dry_seen: set = field(default_factory=set)


@dataclass
class Stats:
    seen: int = 0
    written: int = 0   # neue kanonische EML (bzw. „wuerde laden" im Dry-Run)
    dup: int = 0       # weitere Fundstelle bekannter Nachricht
    skipped: int = 0   # Fundort bereits im Index (Resume/Zweitlauf)
    errors: int = 0
    nbytes: int = 0

    def add(self, other: "Stats") -> None:
        self.seen += other.seen
        self.written += other.written
        self.dup += other.dup
        self.skipped += other.skipped
        self.errors += other.errors
        self.nbytes += other.nbytes


# --------------------------------------------------------------------------- #
# Graph-Abrufe (rein lesend)
# --------------------------------------------------------------------------- #
def traverse_folders(client: GraphClient, upn: str) -> list[dict]:
    """Rekursive Ordnerliste (ohne Recoverable Items). Liefert dicts id/path/wkn/total.

    Ordner-Listing ueber /beta: nur dort ist `wellKnownName` per $select waehlbar
    (v1.0 liefert die Eigenschaft nicht — sprachunabhaengige Erkennung von
    Deleted Items/Sent/Drafts fuer die Skip-Regel und die Richtungs-Signale in Saeule 2).
    Nachrichten-Metadaten und die MIME /$value bleiben auf stabilem v1.0.
    """
    out: list[dict] = []

    def walk(list_url: str, prefix: str, depth: int) -> None:
        if depth > 25:
            return
        params = {"$top": "200", "includeHiddenFolders": "true", "$select": FOLDER_SELECT}
        for f in client.get_paged(list_url, params):
            name = f.get("displayName") or "(ohne Name)"
            wkn = (f.get("wellKnownName") or "").lower()
            path = f"{prefix}/{name}" if prefix else name
            if _is_recoverable(wkn, name):
                _log.debug("  Ordner uebersprungen (Recoverable): %s", path)
                continue
            out.append({"id": f["id"], "path": path, "wkn": wkn,
                        "total": f.get("totalItemCount") or 0})
            if (f.get("childFolderCount") or 0) > 0:
                child_url = f"/beta/users/{_userseg(upn)}/mailFolders/{_idseg(f['id'])}/childFolders"
                walk(child_url, path, depth + 1)

    walk(f"/beta/users/{_userseg(upn)}/mailFolders", "", 0)
    return out


def iter_messages(client: GraphClient, upn: str, folder_id: str, resume_after: str | None):
    """Metadaten paginiert, aufsteigend nach receivedDateTime (stabiler Resume-Cursor)."""
    params = {"$select": MESSAGE_SELECT, "$top": "100", "$orderby": "receivedDateTime asc"}
    if resume_after:
        # Bei Wiederaufnahme ab dem letzten Zeitstempel; Ueberlappung faengt der Index ab.
        params["$filter"] = f"receivedDateTime ge {resume_after}"
    url = f"/v1.0/users/{_userseg(upn)}/mailFolders/{_idseg(folder_id)}/messages"
    yield from client.get_paged(url, params)


def download_eml(run: RunCtx, upn: str, msg: dict, received: str) -> tuple[str, int, str]:
    """Streamt die Voll-MIME nach raw\\<upn>\\<jahr>\\<xx>\\<sha>.eml. Liefert (sha, size, relpfad)."""
    year = (received or msg.get("sentDateTime") or "")[:4]
    if not (year and year.isdigit()):
        year = "0000"
    year_dir = run.staging / "raw" / _safe_name(upn) / year
    year_dir.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(dir=str(year_dir), suffix=".part")
    os.close(fd)
    tmp = Path(tmp_name)
    url = f"/v1.0/users/{_userseg(upn)}/messages/{_idseg(msg['id'])}/$value"
    try:
        sha, size = run.client.stream_to_file(url, tmp)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise

    shard = year_dir / sha[:2]
    shard.mkdir(parents=True, exist_ok=True)
    final = shard / f"{sha}.eml"
    if final.exists():
        tmp.unlink(missing_ok=True)  # inhaltsgleiche EML liegt bereits vor
    else:
        os.replace(tmp, final)
    rel = f"raw/{_safe_name(upn)}/{year}/{sha[:2]}/{sha}.eml"
    return sha, size, rel


def build_message_row(msg: dict, msg_key: str, imid: str, size: int, rel: str, sha: str) -> dict:
    return {
        "msg_key": msg_key,
        "internet_message_id": imid or None,
        "conversation_id": msg.get("conversationId"),
        "conversation_index": msg.get("conversationIndex"),
        "from_addr": mbx.format_from(msg.get("from")) or None,
        "to_addrs": mbx.format_recipients(msg.get("toRecipients")) or None,
        "cc_addrs": mbx.format_recipients(msg.get("ccRecipients")) or None,
        "bcc_addrs": mbx.format_recipients(msg.get("bccRecipients")) or None,
        "subject": msg.get("subject"),
        "sent_at": msg.get("sentDateTime"),
        "received_at": msg.get("receivedDateTime"),
        "direction": mbx.classify_direction(msg) or None,
        "size_bytes": size,
        "has_attachments": 1 if msg.get("hasAttachments") else 0,
        "is_draft": 1 if msg.get("isDraft") else 0,
        "is_flagged_private": 0,
        "body_text": None,          # P1: Volltext bleibt leer (spaeter mail_prep)
        "canonical_eml_path": rel,
        "canonical_sha256": sha,
    }


# --------------------------------------------------------------------------- #
# Kernlogik je Nachricht
# --------------------------------------------------------------------------- #
def handle_message(run: RunCtx, stats: Stats, folder: dict, upn: str, msg: dict) -> str:
    """Verarbeitet eine Nachricht (Dry-Run: nur zaehlen). Liefert receivedDateTime (Cursor)."""
    stats.seen += 1
    gid = msg.get("id") or ""
    imid = (msg.get("internetMessageId") or "").strip()
    msg_key = imid or (f"graph:{gid}" if gid else "")
    received = msg.get("receivedDateTime") or ""
    if not msg_key:
        stats.errors += 1
        _log.warning("  Nachricht ohne id/internetMessageId — uebersprungen.")
        return received

    # Dry-Run: nichts schreiben, nur zaehlen (Dedup im Speicher fuer diesen Lauf).
    if not run.commit:
        if msg_key in run.dry_seen:
            stats.dup += 1
        else:
            run.dry_seen.add(msg_key)
            stats.written += 1
        return received

    conn = run.conn
    # Idempotenz: dieser Fundort ist bereits erfasst?
    if mindex.has_location(conn, upn, gid):
        stats.skipped += 1
        return received
    # Nachricht schon kanonisch bekannt -> nur weitere Fundstelle, kein Download.
    if mindex.has_message(conn, msg_key):
        canon = mindex.canonical_eml_path(conn, msg_key)
        mindex.insert_location(conn, msg_key, upn, folder["path"], folder["wkn"], gid, None, canon)
        stats.dup += 1
        return received
    # Neu: Voll-MIME laden -> kanonische EML.
    try:
        sha, size, rel = download_eml(run, upn, msg, received)
    except GraphError as exc:
        stats.errors += 1
        _log.warning("  MIME-Download fehlgeschlagen (%s) fuer '%s' - spaeterer Lauf holt sie nach.",
                     exc.status, _short_subject(msg))
        return received

    row = build_message_row(msg, msg_key, imid, size, rel, sha)
    mindex.insert_message(conn, row)
    mindex.insert_location(conn, msg_key, upn, folder["path"], folder["wkn"], gid, sha, rel)
    stats.written += 1
    stats.nbytes += size
    if run.sleep_ms:
        time.sleep(run.sleep_ms / 1000.0)
    return received


# --------------------------------------------------------------------------- #
# Zustand (Checkpoint/Resume)
# --------------------------------------------------------------------------- #
def _state_path(run: RunCtx, upn: str) -> Path:
    return run.staging / "state" / f"{_safe_name(upn)}.json"


def load_state(run: RunCtx, upn: str) -> dict:
    if not (run.commit and run.staging):
        return {"folders": {}}
    p = _state_path(run, upn)
    if p.is_file():
        try:
            import json
            data = json.loads(p.read_text(encoding="utf-8"))
            data.setdefault("folders", {})
            return data
        except (OSError, ValueError):
            _log.warning("  State-Datei unlesbar, starte Postfach ohne Checkpoint: %s", p)
    return {"folders": {}}


def save_state(run: RunCtx, upn: str, state: dict) -> None:
    import json
    p = _state_path(run, upn)
    p.parent.mkdir(parents=True, exist_ok=True)
    state["updated"] = _now_iso()
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def mark_folder(state: dict, folder: dict, last_received: str | None, done: bool) -> None:
    fs = state.setdefault("folders", {}).setdefault(folder["id"], {})
    fs["path"] = folder["path"]
    if last_received:
        fs["last_received"] = last_received
    fs["done"] = done


# --------------------------------------------------------------------------- #
# Postfach-Verarbeitung
# --------------------------------------------------------------------------- #
def _log_progress(upn: str, stats: Stats, t0: float) -> None:
    el = time.monotonic() - t0
    rate = stats.seen / el if el > 0 else 0.0
    _log.info("  %s: %d gesehen (neu %d / dup %d / skip %d / err %d) — %.1f Mails/s",
              upn, stats.seen, stats.written, stats.dup, stats.skipped, stats.errors, rate)


def process_mailbox(run: RunCtx, mb: mbx.Mailbox) -> Stats:
    upn = mb.upn
    started = _now_iso()
    stats = Stats()
    _log.info("=== Postfach %s (%s) — gemeldet %d Mails / %.0f MB ===",
              upn, mb.rtype, mb.item_count, mb.size_mb)

    if run.commit:
        mindex.upsert_mailbox(run.conn, upn, mb.display_name, mb.rtype, mb.item_count, mb.size_mb)

    try:
        folders = traverse_folders(run.client, upn)
    except GraphError as exc:
        _log.error("  Ordner-Traversal fehlgeschlagen (%s): %s — Postfach uebersprungen.",
                   exc.status, exc.detail)
        stats.errors += 1
        return stats

    soll = sum(f["total"] for f in folders)
    _log.info("  %d Ordner (Recoverable Items ausgeschlossen), Soll-Items gesamt: %d", len(folders), soll)
    if run.commit:
        for f in folders:
            mindex.upsert_folder(run.conn, upn, f["id"], f["path"], f["wkn"], f["total"])
        run.conn.commit()

    state = load_state(run, upn)
    t0 = time.monotonic()
    limit = run.limit_mails
    reached = False

    for f in folders:
        fstate = state.get("folders", {}).get(f["id"]) if run.commit else None
        if fstate and fstate.get("done"):
            _log.info("  Ordner uebersprungen (Checkpoint erledigt): %s (%d Items)", f["path"], f["total"])
            continue
        resume_after = fstate.get("last_received") if fstate else None
        if resume_after:
            _log.info("  Ordner-Wiederaufnahme ab %s: %s", resume_after, f["path"])

        last_received = resume_after
        try:
            for msg in iter_messages(run.client, upn, f["id"], resume_after):
                last_received = handle_message(run, stats, f, upn, msg) or last_received
                if stats.seen % 500 == 0:
                    _log_progress(upn, stats, t0)
                if run.commit and stats.seen % 200 == 0:
                    mark_folder(state, f, last_received, done=False)
                    save_state(run, upn, state)
                    run.conn.commit()
                if limit and stats.seen >= limit:
                    reached = True
                    break
        except GraphError as exc:
            stats.errors += 1
            _log.error("  Ordner-Fehler %s bei %s: %s", exc.status, f["path"], exc.detail)

        if run.commit:
            mark_folder(state, f, last_received, done=not reached)
            save_state(run, upn, state)
            run.conn.commit()
        if reached:
            _log.info("  Testlimit %d erreicht — Postfach-Abbruch (Rest folgt im Voll-Lauf).", limit)
            break

    finished = _now_iso()
    if run.commit:
        mindex.write_run_log(run.conn, run.run_id, upn, "*ALLE*",
                             started, finished, stats.seen, stats.written, stats.errors)
        run.conn.commit()

    elapsed = time.monotonic() - t0
    verb = "geladen" if run.commit else "wuerde laden"
    _log.info("  Fertig %s: %d gesehen, %s %d, dup %d, skip %d, err %d, %.1f MB, %.0f s",
              upn, stats.seen, verb, stats.written, stats.dup, stats.skipped, stats.errors,
              stats.nbytes / 1e6, elapsed)
    return stats


# --------------------------------------------------------------------------- #
# Auswahl + CLI
# --------------------------------------------------------------------------- #
def select_mailboxes(all_mb: list[mbx.Mailbox], args: argparse.Namespace) -> list[mbx.Mailbox]:
    if args.mailbox:
        wanted = {m.strip().lower() for m in args.mailbox}
        chosen = [mb for mb in all_mb if mb.upn.lower() in wanted]
        found = {mb.upn.lower() for mb in chosen}
        for miss in sorted(wanted - found):
            _log.warning("Postfach nicht in CSV gefunden (uebersprungen): %s", miss)
    else:
        chosen = list(all_mb)
    if args.smallest_first:
        chosen = mbx.sort_smallest_first(chosen)
    if args.max_mailboxes:
        chosen = chosen[: args.max_mailboxes]
    return chosen


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M365-Voll-Extraktion je Postfach (rein lesend, nur GET).")
    p.add_argument("--mailbox", action="append", metavar="UPN",
                   help="Nur dieses Postfach extrahieren (wiederholbar).")
    p.add_argument("--from-csv", default=None, metavar="CSV",
                   help="Postfach-Liste (Default: exo_sizes.csv neben dem Skript).")
    p.add_argument("--smallest-first", action=argparse.BooleanOptionalAction, default=True,
                   help="Kleinste Postfaecher zuerst — schnelles Feedback (Default: an).")
    p.add_argument("--limit-mails", type=int, default=None, metavar="N",
                   help="Testlauf-Obergrenze der gesehenen Mails je Postfach.")
    p.add_argument("--max-mailboxes", type=int, default=None, metavar="N",
                   help="Nur die ersten N Postfaecher der Auswahl.")
    p.add_argument("--commit", action="store_true",
                   help="Schreibt EML + Index. OHNE dieses Flag: Dry-Run (schreibt nichts).")
    p.add_argument("--staging", default=None, metavar="PATH",
                   help="STAGING_ROOT ueberschreiben (Tests ohne echte SSD).")
    p.add_argument("--sleep-ms", type=int, default=0, metavar="MS",
                   help="Optionale Pause zwischen MIME-Downloads (Standard: 0).")
    return p


def _print_summary(mode: str, n_mb: int, total: Stats, requests: int,
                   idx_path: Path | None, logfile: Path) -> None:
    verb = "Neue EML geladen  " if "COMMIT" in mode else "Wuerde laden      "
    print("")
    print("==================  MAIL-EXTRAKTION (rein lesend)  ==================")
    print(f"  Modus                     : {mode}")
    print(f"  Postfaecher               : {n_mb}")
    print(f"  Mails gesehen             : {total.seen:,}".replace(",", "."))
    print(f"  {verb}        : {total.written:,}".replace(",", "."))
    print(f"  Duplikate (Fundstellen)   : {total.dup:,}".replace(",", "."))
    print(f"  Uebersprungen (Resume)    : {total.skipped:,}".replace(",", "."))
    print(f"  Fehler                    : {total.errors:,}".replace(",", "."))
    if "COMMIT" in mode:
        print(f"  Datenvolumen (EML)        : {total.nbytes / 1e9:.2f} GB")
    print(f"  Graph-Anfragen            : {requests:,}".replace(",", "."))
    print("  ---------------------------------------------------------------")
    if idx_path:
        print(f"  Index : {idx_path}")
    print(f"  Log   : {logfile}")
    print("===================================================================")


def run(args: argparse.Namespace) -> int:
    if args.staging:
        os.environ["STAGING_ROOT"] = args.staging

    cfg = config.load()
    staging_root = args.staging or cfg.staging_root
    logfile = mlog.setup(staging_root=staging_root or None)
    mode = "COMMIT (schreibt EML + Index)" if args.commit else "DRY-RUN (zaehlt nur, schreibt nichts)"
    _log.info("mail_01_extract startet (REIN LESEND, nur GET). %s", cfg.summary())
    _log.info("Modus: %s | Logdatei: %s", mode, logfile)

    staging = Path(staging_root) if staging_root else None

    if args.commit:
        if not staging:
            print("\n[FEHLER] --commit braucht STAGING_ROOT (oder --staging PATH). "
                  "Ohne Zielpfad koennen keine EML/Index geschrieben werden.\n", file=sys.stderr)
            return 2
        try:
            staging.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print(f"\n[FEHLER] STAGING_ROOT nicht anlegbar ({exc}). Ist die SSD angeschlossen?\n",
                  file=sys.stderr)
            return 2

    default_csv = Path(__file__).resolve().parent / "exo_sizes.csv"
    csv_path = Path(args.from_csv) if args.from_csv else default_csv
    if not csv_path.is_file():
        print(f"\n[FEHLER] Postfach-Liste nicht gefunden: {csv_path}\n", file=sys.stderr)
        return 2
    all_mb = mbx.load_mailboxes(csv_path)
    selected = select_mailboxes(all_mb, args)
    if not selected:
        print("\n[FEHLER] Keine Postfaecher ausgewaehlt (Filter zu eng?).\n", file=sys.stderr)
        return 2
    _log.info("%d Postfaecher ausgewaehlt (von %d in %s).", len(selected), len(all_mb), csv_path.name)

    conn = None
    idx_path = None
    if args.commit:
        idx_path = staging / "index.sqlite"
        conn = mindex.connect(idx_path)
        mindex.init_schema(conn)
        _log.info("Index geoeffnet: %s", idx_path)

    run_id = f"{datetime.now():%Y%m%dT%H%M%S}-{os.getpid()}"
    provider = TokenProvider(cfg)
    total = Stats()

    with GraphClient(provider) as client:
        run_ctx = RunCtx(client=client, conn=conn, staging=staging, commit=args.commit,
                         run_id=run_id, limit_mails=args.limit_mails, sleep_ms=args.sleep_ms)
        for i, mb in enumerate(selected, 1):
            _log.info("---- [Postfach %d/%d] ----", i, len(selected))
            try:
                st = process_mailbox(run_ctx, mb)
            except GraphError as exc:
                _log.error("Postfach %s abgebrochen (%s): %s", mb.upn, exc.status, exc.detail)
                st = Stats()
                st.errors += 1
            total.add(st)
        requests = client.request_count

    if conn is not None:
        conn.commit()
        conn.close()

    _print_summary(mode, len(selected), total, requests, idx_path, logfile)
    if not args.commit:
        print("  [i] DRY-RUN: nichts geschrieben. Fuer den echten Lauf: --commit (mit gesetztem STAGING_ROOT).")
    return 0


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
        print("\nAbgebrochen (Resume beim naechsten Lauf ueber den Checkpoint).", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
