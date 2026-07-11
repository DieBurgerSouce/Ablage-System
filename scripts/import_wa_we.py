# -*- coding: utf-8 -*-
"""WA/WE-Altbestand-Import (Neuausrichtung Phase 5, Scope-Entscheidung 7).

Importiert die historischen Monats-Sammel-PDFs Warenausgang (WA) und
Wareneingang (WE) 2008-2026 ins Ablage-System. Diese 444 PDFs sind zugleich
die Bild-Quelle der ~293k Odoo-Alt-Belege (x_pdf_attachment_id verweist auf
die Sammel-Attachments) — der Import ist damit der Alt-Backfill der
Belegbilder; ein 293k-Einzel-PDF-Download aus Odoo entfaellt (Plan §4c.6).

Verhalten:
- Dateiname-Regel: ``Spargelmesser_(WA|WE)_(Monat)_(JJJJ).pdf``
  (deutsche Monatsnamen, "März" und ASCII-Variante "Maerz" toleriert).
  WA -> beleg_typ "warenausgang", WE -> "wareneingang";
  periode "JJJJ-MM"; document_date = Monatsletzter.
- Platzhalter-Filter: leere Monats-PDFs sind byte-identisch 172643 Bytes
  gross -> werden uebersprungen und protokolliert.
- Persistenz wie der Upload-/Folder-Import-Pfad: StorageService (MinIO)
  + ``Document`` mit ``document_metadata`` (import_source, beleg_typ,
  periode, quelle_datei) + GoBD-Archivierung (``GoBDArchiveService``,
  Kategorie "receipt" = Belege, 10 Jahre §147 AO) + OCR-Task (Scans ohne
  Textlayer, auto_ocr) als GPU-Nachtlauf mit niedriger Prioritaet (E3).
- Idempotent: SHA256-Dedupe gegen bestehende Documents der Company
  (``Document.checksum``) — ein Zweitlauf importiert 0 Dateien.
- Default ist ``--dry-run`` (nur Protokoll, KEINE Schreibzugriffe, keine
  DB-Verbindung noetig); der echte Lauf erfordert explizit ``--execute``.

Aufruf im Backend-Container (scripts/ ist read-only gemountet):

    docker compose exec backend python scripts/import_wa_we.py --dry-run
    docker compose exec backend python scripts/import_wa_we.py --execute
    docker compose exec backend python scripts/import_wa_we.py --execute --limit 5

Feinpoliert und durchdacht.
"""
from __future__ import annotations

import argparse
import asyncio
import calendar
import hashlib
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence

# WICHTIG: Auf Modul-Ebene NUR Stdlib importieren. App-Imports (Settings/DB/
# MinIO) passieren lazy im --execute-Pfad, damit --dry-run und die Unit-Tests
# ohne konfigurierte Umgebung (SECRET_KEY, DB, Docker) laufen.

# Standard-Quellordner (Bens Archiv-Export, siehe Plan §4c.6)
DEFAULT_SOURCE_DIRS: List[str] = [
    r"C:\Users\benfi\Firmenich-Odoo\WA_Archiv",
    r"C:\Users\benfi\Firmenich-Odoo\WE_Archiv",
]

# Leere Platzhalter-Monate sind byte-identisch exakt so gross (verifiziert
# gegen die realen Verzeichnisse am 2026-07-08).
PLACEHOLDER_SIZE_BYTES = 172643

# GoBD-Retention-Kategorie: WA/WE-Sammel-PDFs sind Handels-/Buchungsbelege.
# "receipt" (Belege) = 10 Jahre §147 AO im RetentionService — bewusst die
# neutrale Beleg-Kategorie, da jede Monats-PDF gemischte Belegarten der
# jeweiligen Richtung enthaelt (keine falsche Einzel-Klassifikation).
GOBD_CATEGORY = "receipt"

# Deutsche Monatsnamen -> Monatszahl; ASCII-Schreibweise "Maerz" wird
# zusaetzlich toleriert (reale Dateien nutzen "März", verifiziert).
MONTH_BY_NAME: Dict[str, int] = {
    "Januar": 1,
    "Februar": 2,
    "März": 3,
    "Maerz": 3,
    "April": 4,
    "Mai": 5,
    "Juni": 6,
    "Juli": 7,
    "August": 8,
    "September": 9,
    "Oktober": 10,
    "November": 11,
    "Dezember": 12,
}

_MONTH_ALTERNATION = "|".join(MONTH_BY_NAME.keys())

FILENAME_RE = re.compile(
    rf"^Spargelmesser_(WA|WE)_({_MONTH_ALTERNATION})_(\d{{4}})\.pdf$"
)

BELEG_TYP_BY_KUERZEL = {
    "WA": "warenausgang",
    "WE": "wareneingang",
}


@dataclass(frozen=True)
class ParsedWaWeName:
    """Ergebnis des Dateinamen-Parsings (reine Logik, testbar ohne App)."""

    beleg_typ: str  # "warenausgang" | "wareneingang"
    year: int
    month: int

    @property
    def periode(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"

    @property
    def document_date(self) -> date:
        return month_end(self.year, self.month)


@dataclass
class ScanEintrag:
    """Eine gefundene Datei inkl. Parsing-/Filter-Ergebnis."""

    path: Path
    size: int
    parsed: Optional[ParsedWaWeName]
    is_placeholder: bool


@dataclass
class ScanErgebnis:
    """Gesamtergebnis eines Verzeichnis-Scans."""

    importierbar: List[ScanEintrag] = field(default_factory=list)
    platzhalter: List[ScanEintrag] = field(default_factory=list)
    ignoriert: List[Path] = field(default_factory=list)  # Name passt nicht


def parse_wa_we_filename(filename: str) -> Optional[ParsedWaWeName]:
    """Parst einen WA/WE-Dateinamen; ``None`` wenn das Muster nicht passt.

    Beispiel: ``Spargelmesser_WA_März_2019.pdf`` ->
    beleg_typ "warenausgang", periode "2019-03", document_date 2019-03-31.
    """
    match = FILENAME_RE.match(filename)
    if not match:
        return None
    kuerzel, monat_name, jahr = match.group(1), match.group(2), match.group(3)
    return ParsedWaWeName(
        beleg_typ=BELEG_TYP_BY_KUERZEL[kuerzel],
        year=int(jahr),
        month=MONTH_BY_NAME[monat_name],
    )


def month_end(year: int, month: int) -> date:
    """Letzter Kalendertag des Monats (inkl. Schaltjahr-Februar)."""
    return date(year, month, calendar.monthrange(year, month)[1])


def is_placeholder_size(size_bytes: int) -> bool:
    """Platzhalter-Monat? Leere Monats-PDFs sind exakt 172643 Bytes gross."""
    return size_bytes == PLACEHOLDER_SIZE_BYTES


def scan_source_dirs(
    source_dirs: Sequence[str], limit: Optional[int] = None
) -> ScanErgebnis:
    """Scannt die Quellordner und kategorisiert alle PDF-Dateien.

    ``limit`` begrenzt die Anzahl IMPORTIERBARER Dateien (Testlauf);
    Platzhalter/ignorierte Dateien zaehlen nicht gegen das Limit.
    """
    ergebnis = ScanErgebnis()
    for source_dir in source_dirs:
        base = Path(source_dir)
        if not base.is_dir():
            print(f"[import_wa_we] WARNUNG: Quellordner fehlt: {base}")
            continue
        for path in sorted(base.iterdir()):
            if not path.is_file() or path.suffix.lower() != ".pdf":
                continue
            parsed = parse_wa_we_filename(path.name)
            if parsed is None:
                ergebnis.ignoriert.append(path)
                continue
            size = path.stat().st_size
            eintrag = ScanEintrag(
                path=path,
                size=size,
                parsed=parsed,
                is_placeholder=is_placeholder_size(size),
            )
            if eintrag.is_placeholder:
                ergebnis.platzhalter.append(eintrag)
            elif limit is None or len(ergebnis.importierbar) < limit:
                ergebnis.importierbar.append(eintrag)
    return ergebnis


def _ascii_dateiname(filename: str) -> str:
    """Umlaut-sichere ASCII-Variante fuer MinIO-Objekt-Metadaten.

    S3/MinIO-User-Metadata sind HTTP-Header (US-ASCII); "März" wuerde dort
    knallen. Der Original-Name (mit Umlaut) bleibt in ``original_filename``
    und ``document_metadata.quelle_datei`` in der DB erhalten.
    """
    mapping = {
        "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
        "Ä": "Ae", "Ö": "Oe", "Ü": "Ue",
    }
    for src, dst in mapping.items():
        filename = filename.replace(src, dst)
    return filename.encode("ascii", "ignore").decode("ascii")


def _protokoll_kopf(source_dirs: Sequence[str], dry_run: bool) -> None:
    modus = "DRY-RUN (nur Protokoll, es wird NICHTS geschrieben)" if dry_run else "EXECUTE"
    print("=" * 70)
    print("[import_wa_we] WA/WE-Altbestand-Import (Neuausrichtung Phase 5)")
    print(f"[import_wa_we] Modus: {modus}")
    for d in source_dirs:
        print(f"[import_wa_we] Quellordner: {d}")
    print("=" * 70)


def _protokoll_scan(scan: ScanErgebnis) -> None:
    wa = sum(1 for e in scan.importierbar if e.parsed and e.parsed.beleg_typ == "warenausgang")
    we = sum(1 for e in scan.importierbar if e.parsed and e.parsed.beleg_typ == "wareneingang")
    print(f"[import_wa_we] Erkannt (importierbar): {len(scan.importierbar)} "
          f"(Warenausgang: {wa}, Wareneingang: {we})")
    print(f"[import_wa_we] Uebersprungen (Platzhalter {PLACEHOLDER_SIZE_BYTES} Bytes): "
          f"{len(scan.platzhalter)}")
    for e in scan.platzhalter:
        print(f"[import_wa_we]   PLATZHALTER: {e.path.name}")
    if scan.ignoriert:
        print(f"[import_wa_we] Ignoriert (Dateiname passt nicht): {len(scan.ignoriert)}")
        for p in scan.ignoriert:
            print(f"[import_wa_we]   IGNORIERT: {p.name}")


async def _resolve_company(session, company_arg: Optional[str]):
    """Company aufloesen: per Name/short_name oder Default (wie create_admin)."""
    from sqlalchemy import select

    from app.db.models_cash_company import Company

    if company_arg:
        company = (
            (
                await session.execute(
                    select(Company).where(
                        Company.is_active.is_(True),
                        (Company.name == company_arg)
                        | (Company.short_name == company_arg),
                    ).limit(1)
                )
            )
            .scalars()
            .first()
        )
        if company is None:
            raise SystemExit(
                f"[import_wa_we] FEHLER: Keine aktive Company '{company_arg}' gefunden."
            )
        return company

    company = (
        (
            await session.execute(
                select(Company)
                .where(Company.is_active.is_(True))
                .order_by(Company.is_default.desc(), Company.created_at.asc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    if company is None:
        raise SystemExit(
            "[import_wa_we] FEHLER: Keine aktive Company vorhanden. "
            "Zuerst scripts/create_admin.py ausfuehren."
        )
    return company


async def _resolve_owner(session):
    """Ersten aktiven Superuser als Dokument-Owner/Archivierer verwenden."""
    from sqlalchemy import select

    from app.db.models import User

    owner = (
        (
            await session.execute(
                select(User)
                .where(User.is_superuser.is_(True), User.is_active.is_(True))
                .order_by(User.created_at.asc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    if owner is None:
        raise SystemExit(
            "[import_wa_we] FEHLER: Kein aktiver Admin-Benutzer vorhanden. "
            "Zuerst scripts/create_admin.py ausfuehren."
        )
    return owner


async def _import_datei(
    session, storage, archive_service, company, owner, eintrag: ScanEintrag
) -> str:
    """Importiert EINE Datei; Rueckgabe: "importiert" | "duplikat".

    Ablauf identisch zum kanonischen Upload-Pfad (api/v1/documents.py):
    SHA256 -> Dedupe -> MinIO-Upload -> Document -> GoBD-Archiv -> OCR-Task.
    """
    from uuid import uuid4

    from sqlalchemy import select

    from app.db.models import Document

    assert eintrag.parsed is not None
    parsed = eintrag.parsed

    content = eintrag.path.read_bytes()
    file_hash = hashlib.sha256(content).hexdigest()

    # SHA256-Dedupe gegen bestehende Documents der Company (wie
    # folder_import_service._check_duplicate_by_hash, hier company-weit,
    # damit der Zweitlauf unabhaengig vom Owner 0 importiert).
    existing = (
        await session.execute(
            select(Document.id)
            .where(
                Document.company_id == company.id,
                Document.checksum == file_hash,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        print(
            f"[import_wa_we]   DUPLIKAT: {eintrag.path.name} "
            f"(bereits als Dokument {existing} vorhanden)"
        )
        return "duplikat"

    # 1) MinIO-Upload (StorageService generiert user_id/hash-basierten Key)
    ascii_name = _ascii_dateiname(eintrag.path.name)
    upload_result = await storage.upload_document(
        file_data=content,
        filename=ascii_name,
        content_type="application/pdf",
        user_id=str(owner.id),
        metadata={
            "import-source": "wa_we_altbestand",
            "beleg-typ": parsed.beleg_typ,
            "periode": parsed.periode,
        },
    )

    # 2) Document-Zeile (derselbe Weg wie Upload-/Folder-Import: Document mit
    #    document_metadata; auto_ocr folgt in Schritt 4)
    doc_id = uuid4()
    document = Document(
        id=doc_id,
        filename=upload_result["storage_path"].split("/")[-1],
        original_filename=eintrag.path.name,
        file_path=upload_result["storage_path"],
        file_size=eintrag.size,
        mime_type="application/pdf",
        checksum=file_hash,
        document_type="receipt",
        status="pending",  # OCR folgt (Scans ohne Textlayer)
        owner_id=owner.id,
        company_id=company.id,
        document_metadata={
            "import_source": "wa_we_altbestand",
            "beleg_typ": parsed.beleg_typ,
            "periode": parsed.periode,
            "quelle_datei": str(eintrag.path),
        },
    )
    session.add(document)
    await session.flush()

    # 3) GoBD-Einbuchung (SHA256, Retention 10 J. §147 AO, Audit-Chain)
    await archive_service.archive_document(
        db=session,
        document_id=doc_id,
        company_id=company.id,
        category=GOBD_CATEGORY,
        document_content=content,
        document_date=parsed.document_date,
        archived_by_id=owner.id,
        metadata={
            "import_source": "wa_we_altbestand",
            "beleg_typ": parsed.beleg_typ,
            "periode": parsed.periode,
            "quelle_datei": str(eintrag.path),
        },
        use_tsa=False,
    )

    # Erst persistieren (Document + Archiv atomar), dann OCR anstossen —
    # der Task laeuft in einem anderen Prozess und braucht die Zeile.
    await session.commit()

    # 4) auto_ocr=True: OCR-Task best-effort einreihen (niedrige Prioritaet,
    #    GPU-Nachtlauf gem. E3). Fehler (z. B. Redis nicht erreichbar) brechen
    #    den Import NICHT ab — Status faellt dann auf "uploaded" zurueck,
    #    OCR kann spaeter nachgeholt werden (Muster aus api/v1/documents.py).
    try:
        from app.workers.tasks.ocr_tasks import process_document_task

        process_document_task.apply_async(
            kwargs={
                "document_id": str(doc_id),
                "backend": "auto",
                "language": "de",
                "priority": "low",
            },
            priority=9,  # 9 = niedrigste Celery-Prioritaet (Nachtlauf)
        )
    except Exception as exc:
        print(
            f"[import_wa_we]   WARNUNG: OCR-Task fuer {eintrag.path.name} "
            f"nicht eingereiht ({type(exc).__name__}) — Status 'uploaded', "
            "OCR spaeter nachholen."
        )
        document.status = "uploaded"
        await session.commit()

    print(
        f"[import_wa_we]   IMPORTIERT: {eintrag.path.name} "
        f"({parsed.beleg_typ}, Periode {parsed.periode}, "
        f"Belegdatum {parsed.document_date.isoformat()})"
    )
    return "importiert"


async def _execute_import(scan: ScanErgebnis, company_arg: Optional[str]) -> Dict[str, int]:
    """Echter Lauf: Session, Company/Owner, Import pro Datei mit Fehler-Isolation."""
    import app.db.all_models  # noqa: F401  # vollstaendigen ORM-Graphen registrieren
    from app.db.session import get_worker_session_context
    from app.services.compliance.archive_service import GoBDArchiveService
    from app.services.storage_service import get_storage_service

    zaehler = {"importiert": 0, "duplikat": 0, "fehler": 0}
    storage = get_storage_service()
    archive_service = GoBDArchiveService()

    # RLS-Bypass SESSION-level (get_worker_session_context, F-16-Muster).
    # WICHTIG: Das fruehere transaktions-lokale set_config(..., true) verdampfte
    # beim Commit-pro-Datei nach Datei 1 -> Dedupe-Reads sahen 0 Zeilen
    # (Zweitlauf haette dupliziert) und ab Migration 274 waeren die INSERTs
    # der Dateien 2..n abgelehnt worden. Systemischer CLI-Import = Bypass ok.
    async with get_worker_session_context() as session:
        company = await _resolve_company(session, company_arg)
        owner = await _resolve_owner(session)
        print(f"[import_wa_we] Ziel-Company: '{company.name}' ({company.id})")
        print(f"[import_wa_we] Dokument-Owner: {owner.email}")

        for eintrag in scan.importierbar:
            try:
                ergebnis = await _import_datei(
                    session, storage, archive_service, company, owner, eintrag
                )
                zaehler[ergebnis] += 1
            except Exception as exc:
                await session.rollback()
                # Bypass ist session-level (get_worker_session_context) und
                # ueberlebt Commit UND Rollback — kein Re-Arm mehr noetig.
                zaehler["fehler"] += 1
                print(
                    f"[import_wa_we]   FEHLER: {eintrag.path.name} — "
                    f"{type(exc).__name__}: {exc}"
                )

    return zaehler


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Importiert die WA/WE-Monats-Sammel-PDFs (Altbestand 2008-2026) "
            "ins Ablage-System (GoBD-Archiv + OCR). Default: --dry-run."
        )
    )
    parser.add_argument(
        "--source-dir",
        action="append",
        dest="source_dirs",
        metavar="PFAD",
        help=(
            "Quellordner (mehrfach angebbar). Default: "
            + " und ".join(DEFAULT_SOURCE_DIRS)
        ),
    )
    parser.add_argument(
        "--company",
        default=None,
        help="Name oder Kurzname der Ziel-Company (Default: aktive Default-Company)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Nur Protokoll, nichts schreiben (DEFAULT)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Echten Import ausfuehren (hebt --dry-run auf)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Maximal N importierbare Dateien verarbeiten (Testlauf)",
    )
    return parser


async def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    dry_run = not args.execute
    source_dirs = args.source_dirs or DEFAULT_SOURCE_DIRS

    _protokoll_kopf(source_dirs, dry_run)
    scan = scan_source_dirs(source_dirs, limit=args.limit)
    _protokoll_scan(scan)

    if dry_run:
        print("-" * 70)
        print("[import_wa_we] DRY-RUN abgeschlossen — es wurde nichts geschrieben.")
        print(
            f"[import_wa_we] Wuerde importieren: {len(scan.importierbar)} | "
            f"Uebersprungen (Platzhalter): {len(scan.platzhalter)} | "
            f"Ignoriert: {len(scan.ignoriert)}"
        )
        print("[import_wa_we] Echten Lauf mit --execute starten "
              "(Duplikat-Pruefung erfolgt dort gegen die Datenbank).")
        return 0

    zaehler = await _execute_import(scan, args.company)

    print("-" * 70)
    print("[import_wa_we] Abschluss-Protokoll:")
    print(f"[import_wa_we]   Importiert:                  {zaehler['importiert']}")
    print(f"[import_wa_we]   Uebersprungen (Platzhalter): {len(scan.platzhalter)}")
    print(f"[import_wa_we]   Uebersprungen (Duplikat):    {zaehler['duplikat']}")
    print(f"[import_wa_we]   Fehler:                      {zaehler['fehler']}")
    if scan.ignoriert:
        print(f"[import_wa_we]   Ignoriert (kein WA/WE-Name): {len(scan.ignoriert)}")
    print("[import_wa_we] Fertig.")
    return 1 if zaehler["fehler"] else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
