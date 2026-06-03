# Interface-Kontrakt G1 ↔ G4

**Datum:** 2026-06-03
**Strom:** G0 (Vorbereitung, Welle 0) — fixiert die Kopplung zwischen
**G1** (Dashboard-KPIs M1–M4 + Fraud-Alert-UI M5 + Admin-Restart M6, *lesende/aufrufende* Seite)
und **G4** (Banking/FinTS-Sync, Fraud-Persistenz, Compliance-TSA, *bereitstellende* Seite).

Zweck: G1 und G4 laufen in getrennten Wellen. Damit G1 nicht ins Leere baut, legt dieses
Dokument **Name, Parameter (inkl. `company_id: UUID`) und Rückgabetyp** der von G4 zu
liefernden Schnittstellen verbindlich fest. Status-Spalte: `EXISTIERT` = im Code vorhanden
und nutzbar; `ANPASSEN` = vorhanden, aber Signatur/Scope muss von G4 nachgezogen werden;
`NEU` = von G4 zu erstellen.

> Konvention: Alle Lesemethoden sind `async` und multi-tenant-scoped über `company_id: UUID`.
> Geldbeträge als `Decimal`/`float` wie in den jeweiligen Services etabliert. Kein `Any` in
> neuen Signaturen außer wo bestehende Services bereits `Dict[str, Any]` zurückgeben.

---

## Kopplungspunkt 1 — Dashboard-KPI-Lesemethoden (M1–M4)

G1 rendert die Dashboard-KPIs über die Helper in `app/api/v1/dashboard.py`
(`_get_cash_flow_kpis`, `_get_approval_kpis`, `_get_ocr_quality_kpis`,
`_get_invoice_kpis`, `_get_alert_kpis`). Diese Helper rufen die folgenden
G4-/Service-Lesemethoden auf. G4 garantiert deren Verfügbarkeit und Signatur-Stabilität.

### M1 — Cash-Flow-Summary

- **Service:** `app/services/banking/cash_flow_service.py` → `CashFlowService`
- **Methode:**
  ```python
  async def get_cash_flow_summary(
      self,
      db: AsyncSession,
      company_id: UUID,
      bank_account_id: Optional[UUID] = None,
  ) -> Dict[str, Any]
  ```
- **Rückgabe (Vertrag):** Dict mit `generated_at: str` (ISO) und je `short_term` (7 Tage),
  `mid_term` (30 Tage), `long_term` (90 Tage) ein Sub-Dict
  `{ "period": str, "inflow": float, "outflow": float, "net": float }`.
- **Status:** `EXISTIERT` (cash_flow_service.py:182).
- **Hinweis für G4:** Werte stammen aus `get_cash_flow_forecast(...)`. Wenn der
  FinTS-Mock-Sync (`settings.FINTS_ALLOW_MOCK_SYNC`) deaktiviert ist, MUSS die Summary
  weiterhin deterministisch (ohne echte Buchungen) berechenbar bleiben — G1 darf keine
  Exception bekommen, nur ggf. leere/0-Werte.

### M2 — Approval-Counts

- **Service:** `app/services/approval/approval_service.py` → `ApprovalService`
- **Methode:**
  ```python
  async def get_approval_summary(
      self,
      company_id: UUID,
      user_id: Optional[UUID] = None,
  ) -> ApprovalSummary
  ```
- **Rückgabe (Vertrag):** `ApprovalSummary`-DTO mit mindestens den Feldern für
  `pending`, `my_pending` (wenn `user_id` gesetzt), `approved`/`rejected`-Counts.
  G1 liest daraus die KPI-Zahlen; Feldnamen des DTOs sind Teil des Vertrags und
  dürfen von G4 nicht ohne Abstimmung umbenannt werden.
- **Status:** `EXISTIERT` (approval_service.py:1202, Alias auf `get_summary`).

### M3 — OCR-Quality

- **Service (Soll):** `app/services/ocr_quality_metrics_service.py` → `OCRQualityMetricsService`
- **Benötigte Methode (Vertrag, von G4 bereitzustellen/anzupassen):**
  ```python
  async def get_ocr_quality_summary(
      self,
      db: AsyncSession,
      company_id: UUID,
      since: datetime,
  ) -> Dict[str, Any]
  ```
  Rückgabe mindestens: `{ "avg_confidence": float, "avg_german_quality": float,
  "document_count": int, "low_quality_count": int }`.
- **Status:** `ANPASSEN`. **Gap:** Der heutige Service ist prozess-lokal/in-memory
  (`record_ocr_result(...)` / `record_ocr_quality(...)` ohne `company_id`) und damit
  **nicht** company-scoped und **nicht** DB-gestützt. G4 MUSS eine company-scoped,
  DB-gestützte Lesemethode liefern (siehe Soll-Signatur), sonst kann
  `_get_ocr_quality_kpis(db, company_id, today_start)` in `dashboard.py:838` keine
  mandantengetrennten Werte liefern. Bis dahin liefert G1 für OCR-Quality Platzhalter/0.

### M4 — (Sammel) Invoice- & Alert-KPIs

- **Invoice-KPIs:** G1 aggregiert direkt über das ORM-Modell `InvoiceTracking`
  (`company_id`-Filter). Kein dedizierter G4-Service nötig — G4 garantiert nur das
  Modell `app/db/models.py::InvoiceTracking` (Felder unverändert).
- **Alert-KPIs:** über `Alert`-Modell (siehe Kopplungspunkt 2), `company_id`-gefiltert.
- **Status:** `EXISTIERT` (ORM-direkt in dashboard.py).

---

## Kopplungspunkt 2 — Fraud-Alert-Persistenz (M5)

G4 stellt die persistente Ablage von Fraud-Alerts bereit; G1 listet, filtert und
aktualisiert sie im Fraud-Alert-UI.

- **Kanonisches DB-Modell:** `app/db/models_alert.py` → `Alert` (Tabelle `alerts`),
  verwendet mit `category = AlertCategory.FRAUD` ("fraud").
- **Verknüpftes Detail-Modell:** `app/db/models_fraud.py` → `FraudScanResult`
  (Tabelle `fraud_scan_results`), `alert_id` FK → `alerts.id`.

### Pflichtfelder (Vertrag)

| Logisches Feld | `Alert`-Spalte | Typ / Wertebereich |
|----------------|----------------|--------------------|
| `company_id`   | `company_id`   | `UUID` (NOT NULL, multi-tenant) |
| `status`       | `status`       | `AlertStatus`: `new`/`acknowledged`/`in_progress`/`resolved`/`dismissed`/`escalated` |
| `action`       | `resolution_action` (String 100) + `available_actions` (JSONB list) | gewählte Aktion + Menge erlaubter Aktionen |

> Hinweis zu `action`: Das `Alert`-Modell trägt die durchgeführte Aktion in
> `resolution_action` und die auswählbaren Aktionen in `available_actions`. Das
> Detail-Modell `FraudScanResult` hat **kein** eigenes `action`-Feld — es trägt
> `status` (`FraudScanStatus`) und Risiko-Daten und verweist via `alert_id` auf den
> Alert. G4 setzt `action` damit **am `Alert`**, nicht am `FraudScanResult`.

### Methoden, die G1 aufruft

G1 nutzt den bestehenden Alert-Service (`app/services/alert_center_service.py`) bzw.
das ORM. Vertraglich zugesichert:

- **Lesen/Filtern:**
  ```python
  async def list_alerts(
      db: AsyncSession,
      company_id: UUID,
      category: Optional[str] = "fraud",
      status: Optional[str] = None,
      limit: int = 50,
      offset: int = 0,
  ) -> list[Alert]
  ```
  Status: `ANPASSEN` — falls noch nicht vorhanden, von G4 als dünne Wrapper-Methode
  über die vorhandenen `alerts`-Queries bereitzustellen (company- und category-scoped).
- **Aktualisieren (Status/Action):**
  ```python
  async def update_alert_status(
      db: AsyncSession,
      company_id: UUID,
      alert_id: UUID,
      new_status: AlertStatus,
      resolution_action: Optional[str] = None,
      acting_user_id: Optional[UUID] = None,
  ) -> Alert
  ```
  Setzt `status`, optional `resolution_action`, plus `acknowledged_*`/`resolved_*`-Felder
  je nach Zielstatus. Status: `ANPASSEN`/`NEU` je nach Bestand in `alert_center_service.py`.
- **Serialisierung:** G1 verlässt sich auf `Alert.to_dict()` (liefert `company_id`,
  `status`, `available_actions`, etc.). `to_dict()`-Keys sind Teil des Vertrags.

---

## Kopplungspunkt 3 — Celery-Restart-Hook (M6)

**Befund:** `app/api/v1/admin/system.py:244` (`restart_service`) ist heute ein
**Placeholder**, der ein erfolgreiches "Neustart angefordert" zurückgibt, **ohne** etwas
zu tun ("In a real implementation, this would trigger a service restart / return a
placeholder response"). Das ist ein unehrlicher 200er.

### Entscheidung

**Ehrlicher Restart bevorzugt, sonst HTTP 501.** Kein gefälschter Erfolg.

G4 stellt einen Worker-Control-Hook bereit; G1s Admin-Endpoint ruft ihn auf und
spiegelt das **ehrliche** Ergebnis:

- **Service (NEU):** `app/services/admin/worker_control_service.py`
- **Hook-Signatur (Vertrag):**
  ```python
  async def request_worker_restart(reason: str) -> WorkerRestartResult
  ```
  wobei `WorkerRestartResult` ein DTO ist mit:
  `{ performed: bool, mechanism: str, detail: str }`.
- **Verhalten:**
  1. Wenn ein echter Mechanismus verdrahtet ist (z. B.
     `celery_app.control.broadcast("pool_restart", arguments={"reload": True})`
     bei aktivem `worker_pool_restarts`), führt der Hook ihn aus und gibt
     `performed=True, mechanism="pool_restart"` zurück. G1 → HTTP 200 mit echtem Detail.
  2. Wenn **kein** Restart-Mechanismus verfügbar ist, gibt der Hook
     `performed=False` zurück; G1 antwortet mit **HTTP 501 Not Implemented**
     (statt des bisherigen Fake-200).
- **G1-Seite:** `restart_service(...)` in `app/api/v1/admin/system.py` wird so
  umgebaut, dass es `request_worker_restart(...)` aufruft und bei `performed=False`
  `HTTPException(status_code=501, ...)` wirft. Der Placeholder-Kommentar entfällt.
- **Status:** `NEU` (Service) + `ANPASSEN` (Endpoint).

---

## Zusammenfassung der G4-Bringschuld

| # | Kopplung | Artefakt | Status |
|---|----------|----------|--------|
| M1 | Cash-Flow-Summary | `CashFlowService.get_cash_flow_summary(db, company_id, bank_account_id=None) -> Dict` | EXISTIERT |
| M2 | Approval-Counts | `ApprovalService.get_approval_summary(company_id, user_id=None) -> ApprovalSummary` | EXISTIERT |
| M3 | OCR-Quality | `OCRQualityMetricsService.get_ocr_quality_summary(db, company_id, since) -> Dict` | ANPASSEN (company-scoped + DB-gestützt) |
| M4 | Invoice/Alert-KPIs | ORM-Modelle `InvoiceTracking`, `Alert` (company_id-Filter) | EXISTIERT |
| M5 | Fraud-Alert-Persistenz | `Alert` (`company_id`, `status`, `resolution_action`/`available_actions`) + `list_alerts`/`update_alert_status` | ANPASSEN/NEU |
| M6 | Celery-Restart-Hook | `worker_control_service.request_worker_restart(reason) -> WorkerRestartResult` (sonst HTTP 501) | NEU |

## Querverweise / abhängige Settings (aus G0)

- `settings.FINTS_ALLOW_MOCK_SYNC` (Default `False`) — Guard für M1/G4-Sync: bei `False`
  kein echter Abgleich/Buchung; Lesemethoden bleiben dennoch aufrufbar.
- `settings.FINTS_AUTO_SYNC_ENABLED` (Default `False`) — Auto-Sync-Beat aus, bis aktiviert.
- `asn1crypto==1.5.1` in `requirements.txt` — ASN.1 für RFC-3161-TSA in
  `app/services/compliance/tsa_service.py` (G4). `cryptography` ist bereits transitiv
  (PyJWT[crypto]) vorhanden und übernimmt die Signatur-/Zertifikatsprüfung.
