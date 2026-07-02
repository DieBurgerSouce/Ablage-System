# 03 — Tenancy-Residuen (Spec)

## IST (belegt)
- **40x** bare `Depends(get_current_company_id)` / `Depends(get_company_id)` in API-Routern. Diese lesen den
  X-Company-ID-Header ungeprueft -> (a) None -> Insert/Query mit None, (b) beliebiger Header -> Cross-Tenant (IDOR).
  Belegte Dateien (Auszug): `app/api/v1/audit_chain.py:75,132,269,326`, `analytics_team.py:151,394,655,837`,
  `ai_mentor.py:291`, `ceo_dashboard.py:45`, `knowledge_graph.py:47`, `lineage.py:149`, `zero_touch.py:284` (+26 weitere).
- **1x** `app/api/v1/sso.py:1060` `getattr(user, "company_id", None)` -> liefert immer None (User hat kein
  company_id) -> Token-/Kontext-company_id faellt still auf None.

## ABGRENZUNG (NICHT anfassen)
- `PortalUser` (Modul `app/api/v1/portal/*`, Modell `models_portal`) HAT legitim eine `company_id`-Spalte.
  Die ~30 `.company_id`-Zugriffe in `portal/` sind KORREKT (PortalUser != User). Nicht als Residuum behandeln.
  -> Verifizieren via `grep` ob der Zugriff auf PortalUser-Objekten erfolgt, bevor irgendetwas geaendert wird.

## ZIEL
- bare getter -> `Depends(get_user_company_id_dep)` (Mitgliedschafts-Lookup ueber UserCompany; 403 statt None;
  kein Cross-Tenant). Helper existiert in `app/api/dependencies.py`.
- `getattr(user,'company_id')` -> `await get_user_company_id(db, user)` (mit None-Guard -> 400/403).

### Pseudocode (Router-Endpunkt)
```
# vorher
company_id: UUID = Depends(get_current_company_id)   # ungeprueft, kann None/fremd sein
# nachher
company_id: UUID = Depends(get_user_company_id_dep)  # wirft 403 wenn keine Mitgliedschaft
```
```
# sso.py:1060 vorher
cid = getattr(user, "company_id", None)        # immer None
# nachher
cid = await get_user_company_id(db, user)       # echte aktive Company, sonst None -> bewusst behandeln
```

## TDD-Anker (pro betroffenem Endpunkt-Cluster)
- `test_<endpoint>_without_company_header_returns_403` (kein X-Company-ID -> 403, NICHT 200/500).
- `test_<endpoint>_foreign_company_header_no_cross_tenant` (fremde company_id im Header -> kein Zugriff auf
  fremde Daten; 403 oder leere, eigene Sicht).
- `test_get_user_company_id_dep_resolves_via_user_companies` (UserCompany-Join).

## Verifikation / DoD
- [ ] `grep -rn "Depends(get_current_company_id)\|Depends(get_company_id)" app/api | grep -v portal` -> 0.
- [ ] `grep -n "getattr(user, .company_id" app/api/v1/sso.py` -> 0.
- [ ] PortalUser-Zugriffe unveraendert + funktionsfaehig (Portal-Smoke gruen).
- [ ] Multi-Tenant-Isolationstest (`tests/integration/test_multi_tenant_isolation.py`) gruen gegen echte DB.