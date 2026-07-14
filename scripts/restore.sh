#!/usr/bin/env bash
# ============================================================
# DEPRECATED (F-PHX-P2-1, 2026-07-14) — NICHT VERWENDEN.
#
# Dieses Alt-Skript zielte auf eine DB "ablage_ocr" mit User "postgres" —
# ein Restore-Versuch damit waere im Ernstfall GESCHEITERT bzw. haette in
# die falsche Datenbank geschrieben (Phoenix-Report F-PHX-P2-1).
#
# Der BEWIESENE Restore-Weg (RTO 9:33 min, Generalprobe 13.07.2026):
#   docs/runbooks/disaster-recovery.md §2 (12 Schritte, copy-paste-faehig)
# ============================================================
echo "FEHLER: scripts/restore.sh ist DEPRECATED (falsche DB 'ablage_ocr')." >&2
echo "Bewiesener Restore-Weg: docs/runbooks/disaster-recovery.md §2" >&2
exit 1
