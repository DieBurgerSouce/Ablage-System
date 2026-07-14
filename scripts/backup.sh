#!/usr/bin/env bash
# ============================================================
# DEPRECATED (F-PHX-P2-1, 2026-07-14) — NICHT VERWENDEN.
#
# Dieses Alt-Skript zielte auf eine DB "ablage_ocr" mit User "postgres",
# die es so nie in Produktion gab — ein Lauf haette ein LEERES Backup
# erzeugt und echte Sicherungen vorgetaeuscht (Phoenix-Report F-PHX-P2-1).
#
# Der bewiesene Backup-Weg ist restic (3-2-1):
#   scripts/backup/restic_backup.sh
# Anleitung + Restore-Beweis: docs/runbooks/disaster-recovery.md §1
# ============================================================
echo "FEHLER: scripts/backup.sh ist DEPRECATED (falsche DB 'ablage_ocr')." >&2
echo "Nutze: scripts/backup/restic_backup.sh — siehe docs/runbooks/disaster-recovery.md §1" >&2
exit 1
