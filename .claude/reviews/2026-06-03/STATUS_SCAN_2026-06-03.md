# Status-Scan 2026-06-03 — Ablage-System (A–Z Komplett-Scan)

**Methode**: Fan-Out mit 12 Subagents (Doku/Obsidian zuerst, dann Code/Tests/Infra/Security) + Synthese + Stichproben-Verifikation gegen den Code.
**Gesamturteil**: 🟡 **GELB** — echte, breite Enterprise-Software mit solidem Security-Fundament, aber „Production-Ready" ist überzeichnet; A–Z funktioniert NICHT (4 produktionskritische Blocker).
**Zugehörig**: [`MOCK_DATA_REGISTER.md`](./MOCK_DATA_REGISTER.md) (Detail-Inventur der Mock-/Fake-Stellen).

---

## Ampel pro Bereich

| Bereich | Ampel | Kernaussage |
|---------|-------|-------------|
| Security / Secrets / Dependencies | 🟢 | Keine der 10 CRITICAL RULES verletzt; PyJWT (CVE-2024-33664-Migration), bcrypt-12, JSONB-Whitelists (CWE-89), CRLF-Sanitizer (CWE-113), `.env` gitignored, SecretStr. Offene Punkte nur operativ. |
| Backend API-Layer | 🟡 | 298 Module / ~3006 Endpoints, solide Auth — aber systemischer `company_id`-Laufzeitbug (95 Module) + Dashboard-KPI-Platzhalter. |
| Backend Services | 🟡 | 797 Dateien, Kern echt — aber Auto-Bankimport Mock/leer, 3 Fraud-Methoden Stubs, RFC-3161-TSA nicht konform. |
| DB / Migrationen / Celery | 🟡 | 228 Migrationen, **genau 1 Alembic-Head** (sauber!), ~591 Tasks — aber 6 Beat-Jobs → nicht registrierte Tasks, 5 Task-Module dem Worker unsichtbar. |
| Frontend (React/TS) | 🟡 | ~2464 Dateien, 299 Routen, robuster API-Client — aber Knowledge-Graph (3/4 Tabs) + Streckengeschäft zeigen `Math.random`-Mock. |
| Tests & Coverage | 🟡 | 799 Testdateien Breite — aber Security-/Multi-Tenant-Tests als „stub" deaktiviert, ~475 Tests durch Drift tot, reale Coverage ~51 % vs. `fail_under=90`. |
| Deployment / Docker / CI-CD | 🟡 | Compose (~30 Services) lokal deploybar — aber CI baut aus nicht existierenden Dockerfiles; real laufendes Image ungetestet. |

---

## Die 4 Produktions-Blocker (verifiziert)

### B1 — Systemischer `current_user.company_id`-Laufzeitbug (CRITICAL)
- `User`-Modell (`app/db/models.py:379-485`) hat **keine** `company_id`-Spalte (nur `Document` ab Z.139 und `AuditLog` ab Z.842 haben sie — verifiziert per Klassengrenzen-Grep).
- `get_current_user` liefert das rohe `User`-ORM-Objekt; **kein** `hybrid_property`/`synonym`/`column_property` setzt `company_id` dynamisch.
- Dennoch **821 Zugriffe auf `current_user.company_id` in 95 Dateien** (`grep -c` verifiziert), u. a. die zentrale `validate_company_access` (`app/api/dependencies.py:307, 318, 322`) → `AttributeError`/HTTP 500 beim Aufruf.
- `invoices.py` nennt das Muster im Code selbst „latent broken" und wurde bereits korrekt auf `get_user_company_id_dep`/`UserCompany` umgestellt — die übrigen 94 Module nicht.
- **Kontext**: Fortsetzung der laufenden `owner_id → company_id`-Migration (F-Serie, siehe `KNOWN_ISSUES.md` Resolved-Log). Bekannt, aber unvollständig ausgerollt.

### B2 — Auto-Bankimport liefert keine echten Daten (CRITICAL)
- `_fetch_fints_transactions` gibt `[]` zurück (`auto_transaction_import_service.py:480` „Mock: Return empty for now"); PSD2 nutzt `access_token="placeholder"` (Z.434/590).
- `enhanced_fints_service.py:667-669` synct `_generate_mock_transactions()` (Z.1187), die echte Reconciliation/Buchungen auslösen können.
- **Nuance**: PSD2/FinTS-Auto-Sync ist in `breezy-napping-hare.md` als „bewusst OUTSCOPED (BaFin-Compliance)" markiert → teils gewollte Vertagung. Das *Mock-Sync-in-echte-Buchung* (M9) ist trotzdem ein Risiko. Details: Mock-Register M7–M9.

### B3 — CI/CD-Build/Publish-Kette kaputt (HIGH)
- `ci.yml`, `docker.yml`, `docker-build.yml` bauen aus `docker/Dockerfile.backend` und `docker/Dockerfile.frontend` — **diese Dateien existieren nicht** (in `docker/` nur `Dockerfile.worker`, `Dockerfile.mustang`, `Dockerfile.paddleocr-*`).
- Echter Backend-Build = Root-`Dockerfile` (von Compose genutzt), echter Frontend-Build = `frontend/Dockerfile` — von **keinem** CI-Workflow referenziert.
- Folge: keine Images werden gepublished; das real laufende Image wird nie im CI getestet.
- Zusätzlich: `docker-compose.dev.yml` referenziert nicht existierende Build-Stage `development`; 3 divergierende Backend-Dockerfiles (root / `infrastructure/docker/` / `docker/`); `deploy.yml` prüft `migrations/versions` statt `alembic/versions`; `canary-deploy.yml` nutzt nicht existierenden `nginx`-Service.

### B4 — Sicherheit nicht durch laufende Tests bewiesen (CRITICAL)
- `tests/security/test_broken_auth.py`, `test_crlf_injection.py`, `test_pii_leakage.py` und `tests/integration/test_multi_tenant_isolation.py` sind als `@pytest.mark.skip(reason="stub - nicht implementiert")` deaktiviert.
- Genau die Tests, die für ein On-Premises-PII/Lexware-System Sicherheit + Mandanten-Isolation beweisen sollen, laufen nicht — und würden B1 aufdecken.

---

## Doku-vs-Realität-Widersprüche (AP4)

| Behauptung (Doku) | Realität (Code) |
|-------------------|-----------------|
| `PROJECT_STATUS.md`: „100 % Enterprise-Level – Full Production-Ready", alle Services ✅ | B1–B4; reale Coverage ~51 % |
| „Multi-Tenancy-Security: Production-Ready" | Cross-Tenant-/RLS-Negativtests durchgängig gestubbt (B4) |
| Banking/Shipment „Production-Ready" | Auto-Bankimport Mock/leer (B2) |
| CEO-Dashboard / Alert Center fertig | KPIs hardcoded/0, Fraud-Alerts = 501-Stubs (Mock-Register M1–M5) |
| Compliance/DATEV/Aufbewahrung „Production-Ready" | RFC-3161-TSA „nicht konform", GoBD-Checks „simplified" (M14/M15) |
| 3 CI-Workflows „bauen & publishen Images" | referenzierte Dockerfiles existieren nicht (B3) |
| Postgres-Port `:5433` (CLAUDE.md-Diagramm) | `docker-compose.yml:49` bindet `:5434` (5433 Hyper-V-reserviert) |
| Version | `VERSION` = `0.1.0-dev` vs. Compose-Default `0.1.0` vs. Tag `pilot-v0.1.0` |
| **Positiv-Abgleich (Doku stimmt)** | 262-Migration konsolidiert real auf 1 Alembic-Head; `invoices.py` Multi-Tenant korrekt; Security-Fundament (PyJWT/bcrypt/JSONB-Whitelists/.env) real |

---

## Weitere offene Punkte (Medium/Low, nicht Blocker)
- **Celery**: 6 Beat-Schedules → nicht registrierte Task-Namen (NotRegistered); 5 Task-Module (`active_learning_tasks`, `anomaly_tasks`, `clustering_tasks`, `encryption_tasks`, `summary_tasks`) fehlen in `include=[]`/`tasks/__init__.py` → Worker führt sie nie aus.
- **Tests**: ~475 deaktivierte Tests (164 „stub" + Drift „API geändert"/„Mock-Setup unvollständig"); CI triggert nur `main/develop`, Default-Branch ist `master` (kein `main` remote) → Gating greift evtl. nicht.
- **DB**: verwaiste ORM-Modelle `models_categorization_feedback` (keine Migration) und `models_knowledge_graph` (nicht an `Base.metadata` angebunden); Autogenerate-Sichtbarkeit hängt an handgepflegter Liste in `alembic/env.py`.
- **Backend**: Endpoint-Dubletten (`document_chains` vs. `_v2`; `annotations*`/`approval*`/`cashflow*`-Varianten).
- **Security (operativ)**: `.secrets.baseline` leer (`{}`); `safety`-Scan im CI nicht-blockierend (`|| true`); gepinnte Deps teils alternd; JWT als Bearer/sessionStorage statt httpOnly-Cookie (weicht von CLAUDE.md-Guideline ab).

---

## Methoden-Hinweis
4 der ursprünglich 11 Scan-Agents (Doku/Obsidian) lieferten kein strukturiertes Ergebnis; die Doku-Dimension wurde anschließend direkt (Read/Grep) nachgeholt. Die Code-/Test-/Infra-/Security-Findings stammen aus den 7 erfolgreichen strukturierten Reports und wurden für die Blocker B1–B4 + Mock-Register stichprobenartig gegen den Code verifiziert.
