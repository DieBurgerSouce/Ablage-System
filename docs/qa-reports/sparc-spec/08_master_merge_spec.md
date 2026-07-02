# 08 — Master-Merge der P0-Fixes (Spec)

## IST (belegt)
Kritische P0-Fixes existieren NUR auf den Offensive-Branches, NICHT auf `master` -> Produktion weiter verwundbar:
- **2FA-Bypass-Fix** (rbac.py: Bypass haengt an TESTING statt DEBUG): Commit `44db202d2` — fehlt in `git log master`.
- **SCAN-Cursor-Endlosschleife** (RedisStateManager.invalidate_cache cursor='0' str vs int): Commit `3184c82a7` — fehlt in master.
- Daneben die gesamte F-31/Welle-2-Arbeit auf `qa/az-deep-offensive-2026-06-18` (371 Commits) ist ungemergt.

## RANDBEDINGUNG
Eine **Parallel-Session** arbeitet auf `feature/offensive-2026-06-11`. NICHT stoeren / nicht dort committen.
Der DoD jener Linie ("2 Clean-Runs") ist laut Memory ggf. noch offen.

## ZIEL (Merge-Plan, koordiniert)
1. Mit Parallel-Session-Stand abgleichen (welche P0 sind dort schon clean?).
2. Reihenfolge: zuerst die **isolierten P0** (2FA `44db202d2`, SCAN `3184c82a7`) review-gated nach master
   (cherry-pick oder via offensive-Merge), DANN die groesseren Wellen.
3. VOR Merge: re-verifizieren, dass die P0 auf master tatsaechlich greifen (rbac.py nutzt TESTING; SCAN-Loop weg).
4. Kein Force-Push; non-destruktiver Merge in isoliertem Worktree (Muster aus Memory `g2-cicd-remediation`).

## Verifikation / DoD
- [ ] `git log master --oneline | grep -E "44db202d2|3184c82a7"` -> vorhanden (nach Merge).
- [ ] master `app/core/rbac.py`: 2FA-Bypass an `settings.TESTING and not is_production`, nicht `DEBUG`.
- [ ] master SCAN-Cursor-Fix vorhanden (Cache-Invalidierung terminiert; Test/Repro).
- [ ] Keine Stoerung der Parallel-Session (kein Commit auf deren Branch).