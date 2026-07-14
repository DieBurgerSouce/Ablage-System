# -*- coding: utf-8 -*-
"""SQLite-Index der M365-Extraktion (Staging), Schema nach Plan S1.4.

Tabellen: mailboxes, messages, locations, attachments, run_log — plus die
Hilfstabelle `folders` (Soll-Item-Zahlen je Ordner fuer mail_02_verify, damit
die Verifikation ohne erneute Graph-Abfrage rechnen kann).

In P1 bleiben `attachments` und `messages.body_text` LEER/NULL — das Parsen der
EML (Volltext, Anhaenge, TNEF) uebernimmt spaeter mail_prep (Saeule 3).

Dedup-Logik (Plan S1.4): Identitaet = internetMessageId (Fallback graph-id).
Die ERSTE gesehene MIME ist die kanonische .eml (messages-Zeile mit
canonical_sha256/-path); jede weitere Fundstelle ist nur eine locations-Zeile.
Idempotenz garantiert der UNIQUE-Index auf (mailbox_upn, graph_id).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA: list[str] = [
    """CREATE TABLE IF NOT EXISTS mailboxes(
        upn                 TEXT PRIMARY KEY,
        display_name        TEXT,
        rtype               TEXT,
        item_count_reported INTEGER,
        size_mb_reported    REAL)""",
    """CREATE TABLE IF NOT EXISTS messages(
        msg_key             TEXT PRIMARY KEY,
        internet_message_id TEXT,
        conversation_id     TEXT,
        conversation_index  TEXT,
        from_addr           TEXT,
        to_addrs            TEXT,
        cc_addrs            TEXT,
        bcc_addrs           TEXT,
        subject             TEXT,
        sent_at             TEXT,
        received_at         TEXT,
        direction           TEXT,
        size_bytes          INTEGER,
        has_attachments     INTEGER,
        is_draft            INTEGER,
        is_flagged_private  INTEGER DEFAULT 0,
        body_text           TEXT,
        canonical_eml_path  TEXT,
        canonical_sha256    TEXT)""",
    """CREATE TABLE IF NOT EXISTS locations(
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        msg_key         TEXT,
        mailbox_upn     TEXT,
        folder_path     TEXT,
        well_known_name TEXT,
        graph_id        TEXT,
        copy_sha256     TEXT,
        eml_path        TEXT)""",
    """CREATE TABLE IF NOT EXISTS attachments(
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        msg_key           TEXT,
        filename          TEXT,
        mime              TEXT,
        size_bytes        INTEGER,
        sha256            TEXT,
        is_tnef_extracted INTEGER DEFAULT 0)""",
    """CREATE TABLE IF NOT EXISTS run_log(
        run_id       TEXT,
        mailbox_upn  TEXT,
        folder       TEXT,
        started      TEXT,
        finished     TEXT,
        msgs_seen    INTEGER,
        msgs_written INTEGER,
        errors       INTEGER)""",
    """CREATE TABLE IF NOT EXISTS folders(
        mailbox_upn      TEXT,
        folder_id        TEXT,
        folder_path      TEXT,
        well_known_name  TEXT,
        total_item_count INTEGER,
        PRIMARY KEY(mailbox_upn, folder_id))""",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_loc_mbox_gid ON locations(mailbox_upn, graph_id)",
    "CREATE INDEX IF NOT EXISTS ix_loc_msg ON locations(msg_key)",
    "CREATE INDEX IF NOT EXISTS ix_loc_mbox ON locations(mailbox_upn)",
]

# Spaltenreihenfolge des messages-INSERT (per :name gebunden).
_MESSAGE_COLUMNS = (
    "msg_key", "internet_message_id", "conversation_id", "conversation_index",
    "from_addr", "to_addrs", "cc_addrs", "bcc_addrs", "subject", "sent_at",
    "received_at", "direction", "size_bytes", "has_attachments", "is_draft",
    "is_flagged_private", "body_text", "canonical_eml_path", "canonical_sha256",
)


def connect(path: Path, *, wal: bool = True) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=60.0)
    conn.row_factory = sqlite3.Row
    if wal:
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    for ddl in SCHEMA:
        conn.execute(ddl)
    conn.commit()


# --------------------------------------------------------------------------- #
# Schreiben (mail_01_extract)
# --------------------------------------------------------------------------- #
def upsert_mailbox(conn, upn, display_name, rtype, item_count, size_mb) -> None:
    conn.execute(
        "INSERT INTO mailboxes(upn,display_name,rtype,item_count_reported,size_mb_reported) "
        "VALUES(?,?,?,?,?) ON CONFLICT(upn) DO UPDATE SET "
        "display_name=excluded.display_name, rtype=excluded.rtype, "
        "item_count_reported=excluded.item_count_reported, size_mb_reported=excluded.size_mb_reported",
        (upn, display_name, rtype, item_count, size_mb),
    )


def upsert_folder(conn, upn, folder_id, folder_path, well_known_name, total) -> None:
    conn.execute(
        "INSERT INTO folders(mailbox_upn,folder_id,folder_path,well_known_name,total_item_count) "
        "VALUES(?,?,?,?,?) ON CONFLICT(mailbox_upn,folder_id) DO UPDATE SET "
        "folder_path=excluded.folder_path, well_known_name=excluded.well_known_name, "
        "total_item_count=excluded.total_item_count",
        (upn, folder_id, folder_path, well_known_name, total),
    )


def has_message(conn, msg_key: str) -> bool:
    return conn.execute("SELECT 1 FROM messages WHERE msg_key=?", (msg_key,)).fetchone() is not None


def canonical_eml_path(conn, msg_key: str) -> str | None:
    row = conn.execute("SELECT canonical_eml_path FROM messages WHERE msg_key=?", (msg_key,)).fetchone()
    return row[0] if row else None


def insert_message(conn, row: dict) -> None:
    cols = ",".join(_MESSAGE_COLUMNS)
    placeholders = ",".join(f":{c}" for c in _MESSAGE_COLUMNS)
    conn.execute(f"INSERT OR IGNORE INTO messages({cols}) VALUES({placeholders})", row)


def has_location(conn, mailbox_upn: str, graph_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM locations WHERE mailbox_upn=? AND graph_id=?", (mailbox_upn, graph_id)
    ).fetchone() is not None


def insert_location(conn, msg_key, mailbox_upn, folder_path, well_known_name,
                    graph_id, copy_sha256, eml_path) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO locations"
        "(msg_key,mailbox_upn,folder_path,well_known_name,graph_id,copy_sha256,eml_path) "
        "VALUES(?,?,?,?,?,?,?)",
        (msg_key, mailbox_upn, folder_path, well_known_name, graph_id, copy_sha256, eml_path),
    )


def write_run_log(conn, run_id, upn, folder, started, finished, seen, written, errors) -> None:
    conn.execute(
        "INSERT INTO run_log(run_id,mailbox_upn,folder,started,finished,msgs_seen,msgs_written,errors) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (run_id, upn, folder, started, finished, seen, written, errors),
    )


# --------------------------------------------------------------------------- #
# Lesen (mail_02_verify)
# --------------------------------------------------------------------------- #
def mailbox_rows(conn) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT upn,display_name,rtype,item_count_reported,size_mb_reported FROM mailboxes ORDER BY upn"
    ).fetchall()


def folder_total(conn, upn: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(total_item_count),0) FROM folders WHERE mailbox_upn=?", (upn,)
    ).fetchone()
    return int(row[0] or 0)


def has_folder_data(conn, upn: str) -> bool:
    return conn.execute("SELECT 1 FROM folders WHERE mailbox_upn=? LIMIT 1", (upn,)).fetchone() is not None


def extracted_count(conn, upn: str) -> int:
    row = conn.execute(
        "SELECT COUNT(DISTINCT msg_key) FROM locations WHERE mailbox_upn=?", (upn,)
    ).fetchone()
    return int(row[0] or 0)


def location_count(conn, upn: str) -> int:
    row = conn.execute("SELECT COUNT(*) FROM locations WHERE mailbox_upn=?", (upn,)).fetchone()
    return int(row[0] or 0)


def canonical_samples(conn) -> list[sqlite3.Row]:
    """Kanonische Nachrichten mit einem konkreten Fundort zum Re-Download.

    Nur Zeilen mit gesetztem canonical_sha256 UND einer locations-Zeile, deren
    copy_sha256 gesetzt ist (= die tatsaechlich geladene kanonische Kopie).
    """
    return conn.execute(
        "SELECT m.msg_key AS msg_key, m.canonical_sha256 AS sha, "
        "       l.mailbox_upn AS upn, l.graph_id AS graph_id, m.canonical_eml_path AS eml_path "
        "FROM messages m JOIN locations l ON l.msg_key=m.msg_key "
        "WHERE m.canonical_sha256 IS NOT NULL AND l.copy_sha256 IS NOT NULL "
        "GROUP BY m.msg_key ORDER BY m.msg_key"
    ).fetchall()


def totals(conn) -> dict:
    def scalar(sql: str) -> int:
        return int(conn.execute(sql).fetchone()[0] or 0)

    return {
        "mailboxes": scalar("SELECT COUNT(*) FROM mailboxes"),
        "messages": scalar("SELECT COUNT(*) FROM messages"),
        "locations": scalar("SELECT COUNT(*) FROM locations"),
        "bytes": scalar("SELECT COALESCE(SUM(size_bytes),0) FROM messages"),
    }
