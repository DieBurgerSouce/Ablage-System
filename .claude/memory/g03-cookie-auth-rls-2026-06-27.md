# G03 httpOnly-Cookie-Auth + RLS-Konsolidierung (2026-06-27)

**Branch:** `feature/g03-cookie-auth-rls` · **Status:** umgesetzt + verifiziert, gepusht. Geht aus der Offene-Punkte-Offensive hervor (Statusdoc: `docs/qa-reports/2026-06-25-offene-punkte-statusplan.html`).

## G03 — JWT vollständig aus JS entfernt (Cookie-Auth + CSRF)
Vorher: Access/Refresh-JWT lag im `sessionStorage` (XSS-Diebstahl möglich), REST sendete `Authorization: Bearer`, WS/SSE passten den Token in URL/Header.

**Backend** (`app/`):
- `dependencies.py`: `set_auth_cookies`/`clear_auth_cookies` + `_get_access_token` (Token aus Bearer-Header ODER httpOnly-`access_token`-Cookie). `get_current_user` nutzt jetzt diesen Extractor.
- `auth.py`: login/verify-2fa/refresh setzen Cookies, logout löscht sie; `/auth/refresh` liest Refresh-Token aus Cookie-Fallback (`request.cookies['refresh_token']`).
- `schemas.py`: `RefreshTokenRequest.refresh_token` → `Optional` (Cookie-basiert kein Body-Token).
- WS-Cookie-Fallback (`token = token or websocket.cookies['access_token']`) in `websocket.py` (+3 Presence-GET-Routes mit `request.cookies`), `exports.py`, `notifications.py`, `rag/chat_ws.py`, `tasks.py`; die 3 Pflicht-`token`-Query-Params → `Optional`.
- CSRF: die bestehende `app/middleware/csrf.py` (Double-Submit, bearer-bypass) schützt Cookie-Auth automatisch.

**Frontend** (`frontend/src/`):
- Neu `lib/auth/csrf.ts` (`getCsrfToken`/`csrfHeaders`/`readCookie`).
- `lib/api/client.ts`: `withCredentials:true`, kein Bearer, `X-CSRF-Token` bei state-changing.
- `lib/api/services/auth.ts`: speichert KEINE Token mehr; `isAuthenticated` via `user`-Objekt; `getAuthToken`→null; refresh ohne Body.
- WS (`lib/websocket.ts` + 3 Hooks): kein `?token=` mehr (Cookie geht same-origin automatisch mit).
- SSE/Direct-Fetch (6 Konsumenten: lib+rag chat-api, bi-api, ki-chat, ablage-api(XHR), personal-api, collaboration presence): kein Bearer, `credentials:'include'` + CSRF.
- 8 „Token-Storage"-Test-Suites auf den Cookie-Vertrag umgeschrieben.

**Verifikation:** `tsc -b` 0 Fehler · 63 vitest-Tests grün · kein `auth_token` mehr im Source. **Backend-E2E 12/12 grün** (TestClient gegen echte App + Postgres@271 + Redis): login→httpOnly+SameSite-Cookies, `/auth/me` nur via Cookie→200, logout ohne CSRF→403 / mit→200, refresh via Cookie→200. (Frühere Test-Fehlschläge = Windows-cp1252-Logging + `localhost`→IPv6 vs. Redis-IPv4, kein G03-Defekt.)

**Offen:** optionaler Browser-Smoke-Test (Frontend+Backend zusammen) erst nach Deploy meines Codes (laufender Stack ist alt).

## RLS-Endausbau — kanonische Session-Var-Konsolidierung
**`pg_policies`-Live-Audit** (isolierter Postgres, alembic from-scratch→Head 271): kanonisch ist `app.current_company_id` (89 Policies); nur **5** `tenant_isolation_*` nutzten `app.current_tenant_id` (Mig 210), jede Tabelle hatte zusätzlich eine company_id-Policy → redundant.

**Migration `271_rls_canonical_session_vars.py`**: schreibt die 5×`tenant_isolation_*` + 5×`superuser_bypass_*` (documents/invoices/approval_requests/document_versions/slack_channels) auf `app.current_company_id`/`app.is_admin` um (idempotent, to_regclass-Guard, PG-only). Re-Audit: `current_tenant_id` = **0 Policies** (vorher 5), kanonisch 94.

**App-seitig** (vorgelagert, additiv, in `company_context.py`/`session.py`/`dependencies.py`): App setzt zusätzlich `app.current_tenant_id`+`app.current_user_is_superuser` mit — nach Mig 271 redundant, aber harmlos.

**Adversariale Tests grün** (SQL gegen echte DB, **Nicht-Superuser-Rolle** via SET ROLE): Kontext A→nur A, Kontext B→nur B, **kein Kontext→0 Zeilen (fail-closed)**. Plus 4 `tests/unit/test_rls_enforce_default.py` grün.

**KRITISCHER Live-Befund:** App-Rolle `ablage_admin` ist **Superuser** → RLS wird auf der Live-DB **komplett gebypassed**. `RLS_ENFORCE_DEFAULT=on` wäre wirkungslos. → Nicht-Superuser-Rolle **`ablage_app`** (NOSUPERUSER/NOBYPASSRLS + Grants) auf Dev-DB angelegt (Passwort vor Prod ersetzen!).

## Deploy-Reihenfolge (WICHTIG)
1. Migration 271 erst auf Live-DB anwenden, **wenn der Container den 271-File hat** (sonst bricht dessen nächster `alembic upgrade` mit „revision 271 not found"). Multi-Head geprüft: **keiner** (nur 271 hängt an 270, kein `alembic merge` nötig).
2. `DATABASE_URL` auf `ablage_app` umstellen + `RLS_ENFORCE_DEFAULT=on` — gemeinsam.
3. G03: Frontend+Backend zusammen deployen (Cookie-Auth ist backward-compatible: Backend akzeptiert Cookie ODER Bearer während Übergang).

## Weitere kleine Fixes in derselben Welle (uncommitted→committed)
W1-022 (`/metrics` fail-closed in Prod, `metrics.py`), G07 (`RateLimitTier.LOGIN` single source, `rate_limiting.py`), jose-Cleanup (`pyproject.toml`→PyJWT), Schemathesis-Resthärtung (`integration_sync.py` betrag-Bool→422).
