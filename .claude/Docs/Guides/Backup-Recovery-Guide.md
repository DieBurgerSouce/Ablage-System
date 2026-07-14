# Backup & Recovery — siehe DR-Runbook

> **DEPRECATED (F-PHX-P2-1, 2026-07-14):** Der frühere Inhalt dieser Datei war ein
> generisches AWS-Tutorial ohne Bezug zum realen Stack (Phönix-Report F-PHX-P2-1).
>
> **Der bewiesene Weg** (DR-Generalprobe 13.07.2026, RTO 9:33 min):
>
> - **Backup erstellen/prüfen:** `docs/runbooks/disaster-recovery.md` §1
>   (restic, `scripts/backup/restic_backup.sh`)
> - **Restore (12 Schritte, copy-paste-fähig):** `docs/runbooks/disaster-recovery.md` §2–3
> - **Einzelszenarien** (nur PG, nur MinIO, Beat hängt): `scripts/backup/DR_RUNBOOK.md`
> - **Beweise:** `docs/qa-reports/phoenix-2026-07/REPORT.md`
