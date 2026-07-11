# -*- coding: utf-8 -*-
"""mail_lib — gemeinsame Bausteine der M365-Extraktion (Projekt „Firmen-E-Mail-Gedaechtnis").

Rein lesender Microsoft-Graph-Zugriff (ausschliesslich GET). Kein Schreibzugriff auf M365.
Bausteine:
  - config : laedt .env.m365 (Zertifikat/Secret, Tenant/Client, STAGING_ROOT)
  - auth   : MSAL-Client-Credentials-Flow (Zertifikat bevorzugt), Token-Cache
  - graph  : synchroner httpx-Client mit Token-Refresh, 429/503-Backoff, Paging
  - log    : Datei-Log unter <STAGING_ROOT>\\logs\\ (Fallback scripts\\m365\\logs\\) + Konsole

Einrichtung: siehe RUNBOOK_P0_BEN.md. Abhaengigkeiten: requirements-m365.txt.
"""

__version__ = "0.1.0"

# Einheitlicher User-Agent fuer alle Graph-Anfragen.
USER_AGENT = "ablage-m365/0.1"
