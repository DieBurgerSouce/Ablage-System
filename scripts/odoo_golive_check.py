# -*- coding: utf-8 -*-
"""Go-Live-Check Ablage<->Odoo (AP-3, Go-Live-Runbook 01.08.2026).

Zwei Modi (kombinierbar), je aktiver Odoo-ERPConnection der Datenbank:

``--phase2`` — Referenzplan-Phase-2-DoD ("1 Rechnung lesen + 1 Draft-Bill"):
  1. XML-RPC-Login mit den Connection-Creds (PASS/FAIL)
  2. ``account.move`` zaehlen (0 ist OK — Prod startet buchungsfrei)
  3. Eine Test-Entwurfs-Lieferantenrechnung anlegen (1,00 EUR, eindeutige
     Referenz ``ABLAGE-GOLIVE-CHECK-…``) und sofort wieder loeschen
     (Entwuerfe sind loeschbar; ``--keep-draft`` laesst sie stehen).

``--diff`` — Spiegel-Abgleich fuer DoD 3 ("Zaehler-Abgleich = 0 Diff"):
  1. Je move_type: Odoo ``search_count`` (state != draft) vs. lokal
     ``count(DISTINCT odoo_id)`` der odoo_mirror-Dokumente.
  2. Bei Diff: fehlende Odoo-Move-IDs benennen (bis 10, solange die
     Odoo-Seite nicht groesser als --max-id-diff ist).
  3. ``--samples N`` Hash-Stichproben: lokale Bytes aus MinIO neu hashen
     und gegen Document.checksum (SHA-256), den beim Spiegeln gespeicherten
     ir.attachment.checksum (SHA-1) UND den LIVE aus Odoo gelesenen
     checksum pruefen (erkennt lokale UND Odoo-seitige Veraenderung).

Aufruf im Backend-Container (scripts/ ist read-only gemountet):

    docker compose exec backend python scripts/odoo_golive_check.py --phase2
    docker compose exec backend python scripts/odoo_golive_check.py --diff --samples 50
    docker compose exec backend python scripts/odoo_golive_check.py --phase2 --diff --connection "Odoo Spargelmesser"

Exit-Code 0 = alle Pruefungen PASS, 1 = mindestens ein FAIL.

Feinpoliert und durchdacht.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# WICHTIG: Auf Modul-Ebene NUR Stdlib importieren. App-Imports (Settings/DB/
# Connector) passieren lazy in den Ausfuehrungspfaden, damit die Unit-Tests
# der reinen Funktionen ohne konfigurierte Umgebung laufen.

# sys.path-Bootstrap: Beim Direktaufruf "python scripts/odoo_golive_check.py"
# ist sys.path[0] das scripts/-Verzeichnis — Projekt-Root ergaenzen, damit
# "app.*" ohne PYTHONPATH importierbar ist (Muster: create_admin.py).
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# =============================================================================
# Reine, testbare Bausteine
# =============================================================================


def build_check_ref() -> str:
    """Eindeutige, sofort erkennbare Referenz fuer den Test-Draft.

    Eindeutigkeit ist Pflicht: create_vendor_bill_draft dedupliziert auf
    (partner, ref, invoice_date) — eine wiederverwendete Referenz wuerde den
    Draft eines frueheren Checks "adoptieren" statt neu anzulegen (F-07/F-19).
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"ABLAGE-GOLIVE-CHECK-{stamp}-{uuid.uuid4().hex[:6].upper()}"


@dataclass
class DiffRow:
    """Zaehler-Abgleich einer Belegart (Odoo vs. lokaler Spiegel)."""

    move_type: str
    odoo_count: int
    local_count: int

    @property
    def delta(self) -> int:
        return self.odoo_count - self.local_count

    @property
    def ok(self) -> bool:
        return self.delta == 0


def compute_move_diff(
    odoo_counts: Dict[str, int], local_counts: Dict[str, int]
) -> List[DiffRow]:
    """Baut den Zaehler-Abgleich ueber die Vereinigung beider Zaehlungen."""
    move_types = list(odoo_counts.keys())
    move_types += [mt for mt in local_counts.keys() if mt not in odoo_counts]
    return [
        DiffRow(
            move_type=mt,
            odoo_count=int(odoo_counts.get(mt, 0)),
            local_count=int(local_counts.get(mt, 0)),
        )
        for mt in move_types
    ]


@dataclass
class SampleResult:
    """Ergebnis einer Hash-Stichprobe (ein gespiegeltes Dokument)."""

    problems: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def verify_sample_content(
    content: bytes,
    *,
    stored_sha256: Optional[str],
    stored_odoo_sha1: Optional[str],
    live_odoo_sha1: Optional[str],
) -> SampleResult:
    """Dreifach-Pruefung der Bytes einer Stichprobe.

    - SHA-256 gegen Document.checksum (lokale Integritaet / MinIO)
    - SHA-1 gegen den beim Spiegeln gespeicherten ir.attachment.checksum
    - SHA-1 gegen den LIVE aus Odoo gelesenen checksum (Odoo-seitige
      Veraenderung nach dem Spiegeln)
    Fehlende Vergleichswerte werden uebersprungen (kein Fehler).
    """
    problems: List[str] = []
    sha256 = hashlib.sha256(content).hexdigest()
    sha1 = hashlib.sha1(content).hexdigest()

    if stored_sha256 and sha256 != stored_sha256.strip().lower():
        problems.append(
            f"sha256-Mismatch: lokal berechnet {sha256}, "
            f"Document.checksum {stored_sha256}"
        )
    if stored_odoo_sha1 and sha1 != stored_odoo_sha1.strip().lower():
        problems.append(
            f"odoo_checksum-Mismatch (gespeichert): sha1 {sha1} "
            f"vs. {stored_odoo_sha1}"
        )
    if live_odoo_sha1 and sha1 != live_odoo_sha1.strip().lower():
        problems.append(
            f"live-Odoo-checksum weicht ab: sha1 {sha1} vs. {live_odoo_sha1} "
            "(Anhang wurde in Odoo veraendert?)"
        )
    return SampleResult(problems=problems)


@dataclass
class Phase2Result:
    """Ergebnis des Phase-2-DoD-Checks (Login, Lesen, Draft-Bill)."""

    ok: bool
    move_count: Optional[int] = None
    draft_move_id: Optional[str] = None
    draft_deleted: bool = False
    problems: List[str] = field(default_factory=list)


async def run_phase2(
    connector: Any,
    *,
    odoo_company_id: Optional[int],
    keep_draft: bool = False,
) -> Phase2Result:
    """Fuehrt den Phase-2-DoD gegen eine verbundene Odoo-Instanz aus.

    Erwartet einen (noch nicht verbundenen) OdooConnector; disconnect
    verantwortet der Aufrufer.
    """
    problems: List[str] = []

    # Gate 0: Ohne Company-Context laufen alle Folge-Calls firmenuebergreifend
    # (Company 1 "ALT-KOPIE"-Risiko, Runbook AP-1/AP-2) -> harter Konfig-FAIL.
    if odoo_company_id is None:
        problems.append(
            "Kein Odoo-Company-Context aufgeloest: ODOO_MIRROR_COMPANY_ID "
            "in .env setzen (Spargelmesser=2) oder sync_state der Connection "
            "pflegen — Abbruch VOR jedem Odoo-Call."
        )
        return Phase2Result(ok=False, problems=problems)

    # Schritt 1: Login
    if not await connector.connect():
        problems.append("XML-RPC-Login fehlgeschlagen (URL/DB/User/API-Key pruefen)")
        return Phase2Result(ok=False, problems=problems)

    # Schritt 2: Lesen — search_count ist der minimale Lese-Beweis;
    # 0 Treffer sind ausdruecklich OK (Prod startet buchungsfrei).
    move_count = int(
        await connector._execute_kw("account.move", "search_count", [[]])
    )

    # Schritt 3: Draft-Bill anlegen (+ aufraeumen)
    partner_ids = await connector._execute_kw(
        "res.partner", "search", [[["supplier_rank", ">", 0]]], {"limit": 1}
    )
    if not partner_ids:
        # Fallback: irgendein Partner (frische DB ohne Lieferanten-Rank)
        partner_ids = await connector._execute_kw(
            "res.partner", "search", [[]], {"limit": 1}
        )
    if not partner_ids:
        problems.append("Kein res.partner gefunden — Draft-Bill-Check nicht moeglich")
        return Phase2Result(ok=False, move_count=move_count, problems=problems)

    # Lazy-Imports: pydantic-Schema + Decimal nur im Ausfuehrungspfad
    from datetime import date
    from decimal import Decimal

    from app.schemas.odoo import OdooVendorBillDraft

    draft = OdooVendorBillDraft(
        partner_id=int(partner_ids[0]),
        invoice_date=date.today(),
        ref=build_check_ref(),
        amount_total_brutto=Decimal("1.00"),
        currency="EUR",
        line_name="Ablage Go-Live-Check — Testeintrag, wird sofort geloescht",
        narration="Automatischer Phase-2-Check (Go-Live-Runbook V5/A3)",
    )
    draft_move_id = await connector.create_vendor_bill_draft(draft)
    if not draft_move_id:
        problems.append("create_vendor_bill_draft lieferte keine move_id")
        return Phase2Result(ok=False, move_count=move_count, problems=problems)

    draft_deleted = False
    if keep_draft:
        problems.append(
            f"--keep-draft: Test-Entwurf {draft_move_id} bleibt in Odoo stehen"
        )
    else:
        try:
            await connector._execute_kw(
                "account.move", "unlink", [[int(draft_move_id)]]
            )
            draft_deleted = True
        except Exception as exc:  # noqa: BLE001 — Aufraeumen darf nie FAIL erzeugen
            problems.append(
                f"Test-Entwurf {draft_move_id} konnte nicht geloescht werden "
                f"({exc}) — bitte manuell in Odoo loeschen (ist ein Entwurf)."
            )

    return Phase2Result(
        ok=True,
        move_count=move_count,
        draft_move_id=str(draft_move_id),
        draft_deleted=draft_deleted,
        problems=problems,
    )


# =============================================================================
# Orchestrierung (lazy App-Imports)
# =============================================================================


def _print(line: str) -> None:
    print(line, flush=True)


async def _local_move_type_counts(db: Any, company_id: Any) -> Dict[str, int]:
    """count(DISTINCT odoo_id) je move_type der gespiegelten Dokumente."""
    from sqlalchemy import func, select

    from app.db.models import Document

    stmt = (
        select(
            Document.document_metadata["odoo_move_type"].as_string().label("mt"),
            func.count(
                func.distinct(Document.document_metadata["odoo_id"].as_string())
            ),
        )
        .where(
            Document.company_id == company_id,
            Document.document_metadata["import_source"].as_string()
            == "odoo_mirror",
        )
        .group_by("mt")
    )
    result = await db.execute(stmt)
    return {str(mt): int(count) for mt, count in result.all() if mt}


async def _local_move_ids(db: Any, company_id: Any, move_type: str) -> set:
    from sqlalchemy import select

    from app.db.models import Document

    stmt = select(
        Document.document_metadata["odoo_id"].as_string()
    ).where(
        Document.company_id == company_id,
        Document.document_metadata["import_source"].as_string() == "odoo_mirror",
        Document.document_metadata["odoo_move_type"].as_string() == move_type,
    )
    result = await db.execute(stmt)
    return {int(v) for (v,) in result.all() if v}


async def _run_diff(
    db: Any, connection: Any, connector: Any, *, samples: int, max_id_diff: int
) -> bool:
    """Zaehler-Abgleich + Hash-Stichproben. True = alles PASS."""
    from sqlalchemy import func, select

    from app.db.models import Document
    from app.services.erp.odoo_mirror_service import MIRROR_MOVE_TYPES
    from app.services.storage_service import StorageService

    ok = True

    # --- Zaehler je move_type -------------------------------------------------
    odoo_counts: Dict[str, int] = {}
    for move_type in MIRROR_MOVE_TYPES:
        odoo_counts[move_type] = int(
            await connector._execute_kw(
                "account.move",
                "search_count",
                [[["move_type", "=", move_type], ["state", "!=", "draft"]]],
            )
        )
    local_counts = await _local_move_type_counts(db, connection.company_id)

    _print("  Zaehler-Abgleich (Odoo state!=draft vs. lokale DISTINCT odoo_id):")
    for row in compute_move_diff(odoo_counts, local_counts):
        marker = "PASS" if row.ok else "DIFF"
        _print(
            f"    [{marker}] {row.move_type:<12} odoo={row.odoo_count:>6} "
            f"lokal={row.local_count:>6} delta={row.delta}"
        )
        if not row.ok:
            ok = False
            if 0 < row.odoo_count <= max_id_diff:
                odoo_ids = set(
                    await connector._execute_kw(
                        "account.move",
                        "search",
                        [[["move_type", "=", row.move_type], ["state", "!=", "draft"]]],
                    )
                )
                local_ids = await _local_move_ids(
                    db, connection.company_id, row.move_type
                )
                missing = sorted(odoo_ids - local_ids)[:10]
                extra = sorted(local_ids - odoo_ids)[:10]
                if missing:
                    _print(f"      fehlt lokal (max 10): {missing}")
                if extra:
                    _print(f"      lokal ohne Odoo-Gegenstueck (max 10): {extra}")

    # --- Hash-Stichproben -------------------------------------------------------
    if samples > 0:
        stmt = (
            select(Document)
            .where(
                Document.company_id == connection.company_id,
                Document.document_metadata["import_source"].as_string()
                == "odoo_mirror",
            )
            .order_by(func.random())
            .limit(samples)
        )
        docs = list((await db.execute(stmt)).scalars().all())
        if not docs:
            _print("  Stichproben: keine gespiegelten Dokumente vorhanden (uebersprungen)")
        else:
            attachment_ids = [
                int(dict(d.document_metadata or {}).get("odoo_attachment_id") or 0)
                for d in docs
            ]
            live_by_id: Dict[int, Optional[str]] = {}
            valid_ids = [a for a in attachment_ids if a]
            if valid_ids:
                rows = await connector._execute_kw(
                    "ir.attachment", "read", [valid_ids, ["checksum"]]
                )
                live_by_id = {
                    int(r["id"]): (r.get("checksum") or None) for r in rows or []
                }

            storage = StorageService()
            passed = 0
            for doc in docs:
                meta = dict(doc.document_metadata or {})
                content = await storage.download_document(str(doc.file_path))
                if content is None:
                    ok = False
                    _print(f"    [FAIL] {doc.id}: Storage-Download fehlgeschlagen")
                    continue
                sample = verify_sample_content(
                    content,
                    stored_sha256=str(doc.checksum) if doc.checksum else None,
                    stored_odoo_sha1=meta.get("odoo_checksum"),
                    live_odoo_sha1=live_by_id.get(
                        int(meta.get("odoo_attachment_id") or 0)
                    ),
                )
                if sample.ok:
                    passed += 1
                else:
                    ok = False
                    for problem in sample.problems:
                        _print(f"    [FAIL] {doc.id}: {problem}")
            _print(f"  Stichproben: {passed}/{len(docs)} hash-identisch")

    return ok


async def _run_for_connection(db: Any, connection: Any, args: argparse.Namespace) -> bool:
    """Fuehrt die gewaehlten Checks fuer EINE Connection aus. True = PASS."""
    from app.workers.tasks.erp_sync_tasks import (
        create_connector,
        get_connection_config,
    )

    _print(f"\n=== Connection: {connection.name} ({connection.url}) ===")
    config = await get_connection_config(db, connection.id)
    if config is None:
        _print("  [FAIL] Konfiguration nicht ladbar")
        return False
    _print(f"  odoo_company_id: {config.odoo_company_id}")

    connector = await create_connector(config)
    ok = True
    try:
        if args.phase2:
            result = await run_phase2(
                connector,
                odoo_company_id=config.odoo_company_id,
                keep_draft=args.keep_draft,
            )
            marker = "PASS" if result.ok else "FAIL"
            _print(
                f"  [{marker}] Phase 2: login+lesen ok, "
                f"account.move count={result.move_count}, "
                f"draft={result.draft_move_id} geloescht={result.draft_deleted}"
            )
            for problem in result.problems:
                _print(f"    Hinweis: {problem}")
            ok = ok and result.ok
            if not result.ok and args.diff:
                _print("  [SKIP] --diff uebersprungen (Phase 2 rot)")
                return False

        if args.diff:
            if not args.phase2:
                # --diff allein braucht auch eine Verbindung
                if config.odoo_company_id is None:
                    _print(
                        "  [FAIL] Kein Company-Context (ODOO_MIRROR_COMPANY_ID) — "
                        "Diff waere firmenuebergreifend und damit wertlos"
                    )
                    return False
                if not await connector.connect():
                    _print("  [FAIL] XML-RPC-Login fehlgeschlagen")
                    return False
            diff_ok = await _run_diff(
                db,
                connection,
                connector,
                samples=args.samples,
                max_id_diff=args.max_id_diff,
            )
            _print(f"  [{'PASS' if diff_ok else 'FAIL'}] Spiegel-Diff")
            ok = ok and diff_ok
    finally:
        try:
            await connector.disconnect()
        except Exception:  # noqa: BLE001 — Aufraeumen ist best-effort
            pass
    return ok


async def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if not args.phase2 and not args.diff:
        _print("Nichts zu tun: --phase2 und/oder --diff angeben.")
        return 2

    from sqlalchemy import select

    import app.db.all_models  # noqa: F401  # registriert den vollstaendigen ORM-Modellgraphen
    from app.db.models import ERPConnection
    from app.db.session import get_async_session_context

    overall_ok = True
    async with get_async_session_context() as db:
        stmt = select(ERPConnection).where(
            ERPConnection.erp_type == "odoo",
            ERPConnection.is_active.is_(True),
        )
        if args.connection:
            stmt = stmt.where(ERPConnection.name == args.connection)
        connections = list((await db.execute(stmt)).scalars().all())

        if not connections:
            _print(
                "Keine aktive Odoo-ERPConnection gefunden"
                + (f" (Name: {args.connection!r})" if args.connection else "")
                + " — zuerst via admin/erp-UI anlegen (Runbook V5/A2)."
            )
            return 1

        for connection in connections:
            overall_ok = await _run_for_connection(db, connection, args) and overall_ok

    _print(f"\nGESAMT: {'PASS' if overall_ok else 'FAIL'}")
    return 0 if overall_ok else 1


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Go-Live-Check Ablage<->Odoo: --phase2 (Login/Lesen/Draft-Bill) "
            "und/oder --diff (Spiegel-Zaehler + Hash-Stichproben)"
        )
    )
    parser.add_argument("--phase2", action="store_true", help="Phase-2-DoD ausfuehren")
    parser.add_argument("--diff", action="store_true", help="Spiegel-Abgleich ausfuehren")
    parser.add_argument(
        "--connection",
        default=None,
        metavar="NAME",
        help="Nur diese Connection pruefen (Default: alle aktiven Odoo-Connections)",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=10,
        metavar="N",
        help="Anzahl Hash-Stichproben im --diff (Default 10; 0 = keine)",
    )
    parser.add_argument(
        "--max-id-diff",
        type=int,
        default=5000,
        metavar="N",
        help="ID-Differenzliste nur wenn Odoo-Count <= N (Default 5000)",
    )
    parser.add_argument(
        "--keep-draft",
        action="store_true",
        help="Test-Entwurf NICHT loeschen (Sichtpruefung in Odoo)",
    )
    return parser


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
