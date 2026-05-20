/goal Squash-Merge PR #8 sprint-0-pilot-hardening -> master + Tag pilot-v0.1.0

Ziel: PR #8 (https://github.com/DieBurgerSouce/Ablage-System/pull/8) sauber via Squash mergen, Tag pilot-v0.1.0 setzen, Branches abraeumen, Memory/CHANGELOG nachziehen. 561 Commits aus Sprint-0 G01-G10 + Phase A K1-K6 + Phase B B1-B7 + Multi-Agent-Review (A-D, F1-F4) + Sprint-1 S1.1-S1.5. KEINE Code-Aenderungen mehr - reines Ship.

Lange Version: `.claude/reviews/2026-05-20/GOAL_SQUASH_MERGE.md`.

**S0 Pre-Check**: `git fetch origin && git status` (working tree clean ausser `.claude-flow/metrics/*.json` Runtime-Artefakte). `git branch --show-current` = sprint-0-pilot-hardening. `git log origin/sprint-0-pilot-hardening..HEAD --oneline` leer. `gh pr view 8 --json mergeable,statusCheckRollup` = MERGEABLE + CI gruen. STOPP bei rotem CI, NICHT mit --admin overriden.

**S1 Squash-Message**: `mkdir -p docs/pr` und `docs/pr/pr-8-squash-message.md` schreiben (nicht committen). Geruest mit 5 Sektionen, Commit-SHAs als Audit-Trail:
- Sprint-0 Pilot-Hardening: 4e01c076, 20c9bb1b, 6de2d89e, 7e012828, 438f2486
- Phase A (K1-K6): 5db272f9, 12f24731, d605d76e, fbef51c5, 8c78a68e (K3 False-Positive)
- Phase B (B1-B7): ee702408, bace67f4, 8b4b37bf, 74ed7b2d, cbfdb217, 33c84712, ee155e21, 409da931
- Multi-Agent (A-D, F1-F2): 74210d8e, 37baeb94, e1e99825, 1b0c76d3, 81ff78c1, 7badff26, 8ad8045b
- Sprint-1 S1.1-S1.5: 59a5702f, cf062e80, dd693f14, d56cd145, e8f6badb, 87e8b4f2

Body-Abschnitt "Bewusst NICHT in diesem PR": G10 Sentry-DSN, P0b Alert-Triage, Phase C/D/E, BACKLOGs. Plus Co-Authored-By claude-flow. Volltext der Message in der langen Version.

**S2 Merge**:
```bash
gh pr merge 8 --squash --delete-branch \
  --subject "feat(pilot): Sprint-0 Pilot-Hardening + Sprint-1 Sec-Reste -> Pilot-Ship v0.1.0 (PR #8)" \
  --body-file docs/pr/pr-8-squash-message.md
```
KEIN --admin, kein --force. `--delete-branch` raeumt remote.

**S3 Master + Tag**:
```bash
git switch master && git pull origin master --ff-only
git tag -a pilot-v0.1.0 -m "Pilot-Ship v0.1.0 ..."
git push origin pilot-v0.1.0
```

**S4 Branch lokal abraeumen**: `git branch -d sprint-0-pilot-hardening` (falls "not fully merged": ERST `gh pr view 8 --json state` = MERGED verifizieren, DANN `-D` forcen). `git remote prune origin`.

**S5 Memory/CHANGELOG**: Auf master:
1. `.claude/memory/RECENT_CHANGES.md` neuer Block "## 2026-05-20 (Pilot-Ship v0.1.0)" mit Squash-SHA aus `git log master -1 --format=%H`.
2. `.claude/memory/PROJECT_STATUS.md` Recent-Deployments-Zeile oben einfuegen.
3. `CHANGELOG.md`: `## [Unreleased]` -> `## [0.1.0] - 2026-05-20 (Pilot-Ship)`, leeres `## [Unreleased]` darueber neu.
Ein Doc-Commit: `git commit -m "docs(release): Pilot-Ship v0.1.0 Squash-Merge dokumentieren" && git push`.

**S6 Verifikation** (Definition of Done):
1. `gh pr view 8 --json state` = MERGED
2. `git tag --list 'pilot-*'` enthaelt pilot-v0.1.0
3. `git log master..pilot-v0.1.0` leer (Tag auf master HEAD)
4. Lokal+remote: kein sprint-0-pilot-hardening mehr
5. Smoke: `python -c "from app.api.v1 import trash, retention_admin, graphql_api, nlq; from app.db.models_entity_business import InvoiceTracking; assert 'entity_id' in [c.name for c in InvoiceTracking.__table__.columns]; print('OK')"`

**Rollback**: Vor S2 = `gh pr ready 8 --undo`. Nach S2 = `git revert -m 1 <squash-sha>` + Push, Branch via reflog restoren. Nach S3 = `git tag -d pilot-v0.1.0 && git push origin :refs/tags/pilot-v0.1.0`.

**Anti-Pattern (nicht machen)**: `--merge`/`--rebase` (statt --squash), `--admin`, `git push --force` auf master, Tag vor Squash setzen, `-D` ohne MERGED-Verifikation.

**Out of Scope**: P0b Alert-Triage, Sentry-DSN, Phase C/D/E, Branch-Protection-Setup.
