<!--
/goal-Prompt — Strom G0: Vorbereitung (Config & Interface-Kontrakt)
WELLE 0 — vor Welle 1 ausführen (klein, ~S). Eigener Branch: feature/g0-prereq
Den Text ab "===" als /goal in eine Claude-Code-Session einfügen.
-->

=== GOAL G0 ===

Setze die Vorbereitungs-PR fuer die Remediation des Projekts "Ablage-System" um (Repo-Root C:\Users\benfi\Ablage_System, Branch master). Diese kleine PR liegt quer zu den 5 Hauptstroemen (G1-G5) und muss VOR Welle 1 gemergt sein, damit G4/G5 nicht ins Leere laufen.

## Aufgaben
1. **Settings ergaenzen** in `app/core/config.py` (Pydantic Settings):
   - `FINTS_ALLOW_MOCK_SYNC: bool = False` — Guard, ob der FinTS-Mock-Sync echte Reconciliation/Buchung ausloesen darf (G4 liest das).
   - `FINTS_AUTO_SYNC_ENABLED: bool = False` — ob der Auto-Bank-Sync-Beat aktiv ist.
   - Beide mit deutschem Kommentar, in `.env.example` dokumentieren.
2. **Dependency pinnen** in `requirements.txt` (und ggf. requirements-Constraints): `asn1crypto` in passender Version (fuer RFC-3161-TSA in G4, `app/services/compliance/tsa_service.py`). Falls `cryptography` bevorzugt wird und bereits vorhanden, das im Interface-Kontrakt vermerken.
3. **Interface-Kontrakt G1↔G4 schriftlich fixieren** (kurze Notiz unter `.claude/reviews/2026-06-03/INTERFACE_CONTRACT_G1_G4.md`): 
   - Service-Lesemethoden, die G1 (Dashboard-KPIs M1-M4) von G4 erwartet: Name, Parameter (inkl. `company_id: UUID`), Rueckgabetyp. Mindestens: Cash-Flow-Summary, Approval-Counts, OCR-Quality.
   - Fraud-Alert-Persistenz (M5): welches DB-Modell/Service G4 bereitstellt (Felder `company_id`, `status`, `action`), und welche Methoden G1 zum Lesen/Aktualisieren aufruft.
   - Celery-Restart-Hook (M6): Name/Signatur des Hooks, den G4 fuer den ehrlichen Admin-Restart bereitstellt (oder Entscheidung "kein Restart -> 501").

## Nicht jetzt (nach G4-Merge, separate Mini-PR)
- `alembic/env.py` auf `from app.db.all_models import *` umstellen (all_models.py liefert G4).

## Constraints
- mypy strict, kein `Any`. Deutsche Kommentare. Keine Secrets/PII. Keine Funktionsaenderung an bestehendem Code ausser den genannten Settings.

## Definition of Done
- `python -c "from app.core.config import settings; print(settings.FINTS_ALLOW_MOCK_SYNC, settings.FINTS_AUTO_SYNC_ENABLED)"` -> `False False`.
- `pip show asn1crypto` (bzw. cryptography) vorhanden / in requirements gepinnt.
- `INTERFACE_CONTRACT_G1_G4.md` existiert und benennt alle 3 Kopplungspunkte konkret.
