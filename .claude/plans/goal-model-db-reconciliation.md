# /goal — Modell↔DB-Versöhnung & ehrlich-grüne DB-Integrationstests

> ✅ **ABGESCHLOSSEN (2026-07-14, Drift-Reconcile E4):** Das Kernziel dieses Plans
> ist erreicht und übertroffen — Live-DB ↔ Migrationskette sind in **allen 9
> Katalog-Dimensionen exakt deckungsgleich** (Migrationen 276–279, auf Live
> angewandt, Live-Head 279; Klon-Generalprobe + From-scratch + Doppellauf bewiesen).
> Beweise: `docs/qa-reports/reconcile-2026-07/REPORT.md` · Risiko R9 im Vault
> geschlossen · master = origin (Merge `4d4e6a98e`). Diese Datei bleibt als
> Historie/Kontext erhalten.

> **Zweck:** Diese Datei enthält einen kopierfertigen `/goal`-Prompt. Den Block
> unter „PROMPT" in `/goal` einfügen. Der Rest ist Kontext/Evidenz, damit die
> nächste Instanz ohne Archäologie startet.
>
> **Ethos dieses Projekts** (`.claude/CLAUDE.md`, „Feinpoliert und durchdacht" +
> Wahrheits-Offensive): **Nie False-Green.** Verify-before-claiming. Ein Feature
> gilt erst als „funktioniert", wenn es gegen das **echte** Schema bewiesen ist —
> nicht wenn Unit-Tests mit gemockter DB grün sind. PII-sicher (Regel #1/#8),
> Deutsch für User-Text (#2), Type-Safety/kein `Any` (#4), On-Premises (#6),
> Tests müssen vor Commit grün sein (#5). Reviewbare Diffs, ehrliche Doku.

---

## PROMPT (in `/goal` einfügen)

```
Mach die behaupteten Fixes ECHT: versöhne die ORM-Modelle mit ihren DB-Tabellen
und beweise es gegen reales Postgres — nachhaltig, ohne False-Green.

Leitprinzip (Projekt-Ethos): Ein Feature/Fix gilt NUR als erledigt, wenn ein
Integrationstest gegen das ECHTE Schema (nicht gemockt, nicht gepatcht-zum-Passen)
grün ist. Patche das Test-Schema NIEMALS so, dass ein Mismatch verschwindet —
ein Patch, der eine fehlende/umbenannte Spalte hinzufügt, um den Test grün zu
machen, ist genau die Lüge, die wir bekämpfen. Decke Mismatches auf, behebe die
URSACHE (Modell ODER Migration), und lass den Test es beweisen.

Arbeite in dieser Reihenfolge, jede Stufe mit reviewbarem Diff:

1) DATEV-Kontierung Modell↔Tabelle-Schisma auflösen (höchste Prio, Feature ist
   non-funktional). `DATEVBuchung`/`DATEVKontierungPattern` deklarieren
   konto_soll/konto_haben/betrag_soll/steuerschluessel; die echten Tabellen
   `datev_buchungen`/`datev_kontierung_patterns` haben konto/gegenkonto/umsatz/
   soll_haben/bu_schluessel — und es gibt KEINE Migration für die Modell-Spalten.
   Entscheide die kanonische Richtung BEWUSST (DATEV-Doppik konto_soll/haben ist
   semantisch korrekter — wahrscheinlich Modell behalten + Migration schreiben):
   - Variante A (Modell kanonisch): Alembic-Migration konto→konto_soll,
     gegenkonto→konto_haben, umsatz→betrag_soll (+ soll_haben/bu_schluessel
     abbilden), mit DATEN-Backfill und Down-Migration. Buchhaltungssensibel:
     keine Datenverluste, soll/haben-Semantik korrekt erhalten.
   - Variante B (DB kanonisch): Modell auf konto/gegenkonto/umsatz zurückführen
     und meinen #3-Service-Fix entsprechend revidieren.
   Dann den (jetzt korrekten) Service durch einen Integrationstest gegen reales
   Postgres beweisen: suggest_kontierung liefert aus echten DATEVBuchung-Zeilen
   einen History-Vorschlag; _suggest_from_patterns aus echtem Pattern;
   learn_from_correction persistiert auf den ECHTEN Spalten. Wenn der reale Fix
   Variante A ist, müssen die 5 ehemaligen xfail-Tests OHNE Schema-Patch grün
   werden. Mein #3-Fix von Commit (KNOWN_ISSUES) ist KEIN funktionaler Fix —
   korrigiere ihn als Teil davon.

2) Migrations-Infrastruktur reparieren, damit ein sauberes Test-Schema OHNE
   Klon-Krücke baubar ist (das ist die nachhaltige Basis):
   - Inkonsistenter Alembic-Stand: Dev-DB ist auf 261 gestempelt, aber
     Migrations-231-Spalten (documents.custom_field_values u.a.) fehlen. Ursache
     finden (stamp statt upgrade?) und Migrationskette + Modelle so angleichen,
     dass `alembic upgrade head` von leer DURCHLÄUFT.
   - `alembic upgrade head` von Null bricht: fehlende `german_text`-TS-Config
     (in eine frühe Migration aufnehmen statt out-of-band) und mind. eine buggy
     Migration (TextClause statt Column in create_foreign_key) reparieren.
   - `Base.metadata.create_all` ist kaputt (dangling FK peppol_participants→
     entities): das fehlende Modell/Tabelle ergänzen oder die FK korrigieren.
   - status/priority: Modell deklariert native Enum (approvalstatus), DB ist
     varchar. Eine Richtung wählen (Migration auf native Enum ODER Modell auf
     `String`/`native_enum=False`) und konsistent machen.
   - Die 9 dokumentierten Duplikat-Klassen (AdHocReport etc.) so auflösen, dass
     `configure_mappers()` global OHNE `import app.main`-Krücke gelingt.

3) DB-Integrationstests im CI ehrlich grün schalten:
   - Sobald (2) steht: tests/integration/test_workflow_insights_real_db.py +
     ein neuer test_datev_kontierung_real_db.py laufen gegen eine per `alembic
     upgrade head` gebaute Test-DB (kein Klon+Patch mehr nötig) → das
     scripts/dbtest/setup_real_test_db.sh durch den sauberen Migrations-Weg
     ersetzen/ergänzen.
   - CI-Job mit Postgres-Service (+ Redis, falls für andere DB-Tests nötig);
     die `@pytest.mark.integration`/`real_db`-Tests laufen dort und SKIPPEN
     nicht mehr still. B4 („DB-Tests brauchen laufende Test-DB im CI") schließen.

Verifikation pro Stufe gegen ECHTES Postgres (localhost:5434/ablage_admin,
Container ablage-postgres/ablage-backend; tests/ ist NICHT in den Container
gemountet — Setup siehe scripts/dbtest/). KNOWN_ISSUES nach jeder Stufe
wahrheitsgemäß updaten. Nichts als „behoben" markieren, was nicht ein
Integrationstest gegen das reale Schema beweist.
```

---

## Kontext & Evidenz (für die ausführende Instanz)

### Die zwei Funde (2026-06-05, via reale-Postgres-Integrationstests)

**A) DATEV Modell↔Tabelle-Schisma (Feature non-funktional):**
- Tabelle `datev_buchungen`: `konto, gegenkonto, umsatz, soll_haben, bu_schluessel, user_korrektur, buchungs_guid, ist_festgeschrieben, …`
- Modell `DATEVBuchung`: `konto_soll, konto_haben, betrag_soll, betrag_haben, steuerschluessel, gobd_festgeschrieben, gobd_hash, …`
- `grep -rE "konto_soll|betrag_soll" alembic/versions` → **0 Treffer** (keine Migration).
- Mein #3-Fix (master) richtete den Service auf die Modell-Spalten → `UndefinedColumn` gegen die echte DB. Der Original-Code nutzte `DATEVBuchung.konto` → `AttributeError` (Modell hat kein `konto`). **Beide kaputt.**
- Gleiches Schisma: `datev_kontierung_patterns` (Modell konto_soll/konto_haben/steuerschluessel/confidence fehlen in der DB).

**B) Pervasives Modell↔DB-Drift / kaputte Migrations-Infra:**
- Dev-DB `ablage_system` @ Alembic `261`, aber Migration-231-Spalten fehlen → inkonsistent gestempelt.
- `Base.metadata.create_all` → `NoReferencedTableError: peppol_participants.entity_id → entities` (dangling FK).
- `alembic upgrade head` von leer: `german_text`-TS-Config fehlt; spätere Migration `ArgumentError: 'SchemaItem' … got TextClause` (create_foreign_key falsch).
- `approval_requests.status` ist `varchar`, Modell deklariert native Enum `approvalstatus` (Typ existiert nicht in DB).
- Mehrere Tabellen (`documents`, `users`, `datev_*`) haben Modell-Spalten ohne DB-Pendant (additives Drift — bei `documents` migrationsgedeckt=stale-DB, bei `datev_*` Modell-Drift).
- `configure_mappers()` global scheitert an Duplikat-`AdHocReport` (umgangen via `import app.main`).

Vollständig in `.claude/memory/KNOWN_ISSUES.md` (Abschnitte „Integrationstest-Funde", „Pervasives Modell↔DB-Drift").

### Was schon existiert (nicht neu bauen)
- `tests/integration/test_workflow_insights_real_db.py` — 5 grüne #4-Tests (Muster für #3 übernehmen). Skippt sauber ohne DB.
- `scripts/dbtest/setup_real_test_db.sh` + `patch_schema.py` — aktueller Klon+Patch-Weg. **Ziel von Stufe 2/3: diesen durch den sauberen `alembic upgrade head`-Weg ablösen** (Patch-zum-Passen widerspricht dem Ethos und ist nur Übergangskrücke).
- Bereits verifiziert & korrekt: #4 workflow_insights (SQL + Status-Enum-Fix, master `49fd657a`).

### Verifikations-Cheatsheet
```
# Reale DB: Container ablage-postgres (host localhost:5434), User ablage_admin, DB ablage_system
docker exec ablage-postgres psql -U ablage_admin -d ablage_system -c "\d datev_buchungen"
# Test-DB-Setup (Übergang): bash scripts/dbtest/setup_real_test_db.sh
# Integrationstest im Container (tests/ nicht gemountet -> nach app/ kopieren, via PowerShell gegen Pfad-Mangling):
#   cp tests/integration/<file>.py app/_t.py
#   docker exec -e PYTHONPATH=/app -w /app ablage-backend python -m pytest /app/app/_t.py -q ; (danach app/_t.py löschen)
# Migration testweise gegen frische DB:
#   docker exec -e DATABASE_URL=postgresql+asyncpg://ablage_admin:<pw>@postgres:5432/ablage_test -w /app ablage-backend alembic upgrade head
```

### Definition of Done (ehrlich)
- [ ] DATEV-Kontierung: Modell↔DB versöhnt (eine kanonische Richtung, dokumentiert); `suggest_kontierung`/`_suggest_from_patterns`/`learn_from_correction` durch Integrationstest gegen **reales, per Migration gebautes** Schema bewiesen — **kein Schema-Patch zum Passen**.
- [ ] `alembic upgrade head` läuft von einer leeren DB sauber durch; `create_all` ebenfalls (oder bewusst deprecated mit Begründung).
- [ ] status/priority Enum-vs-varchar konsistent; `configure_mappers()` global ohne Krücke grün.
- [ ] `tests/integration/test_*_real_db.py` laufen im CI gegen Postgres-Service grün (skippen nicht still); B4 geschlossen.
- [ ] KNOWN_ISSUES & RECENT_CHANGES wahrheitsgemäß aktualisiert; nichts als behoben markiert ohne reale-DB-Beweis.
