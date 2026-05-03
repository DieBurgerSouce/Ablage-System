# Compliance Audit - Pilot Reality Check

**Datum:** 2026-05-03
**Branch:** feature/ocr-performance
**Scope:** GoBD, GDPR, DATEV-Zertifizierung, E-Invoicing, §147 AO, TSE/KassenSichV
**Verdict in einem Satz:** Beeindruckende Tiefe auf Modell-/DB-Ebene, aber kritische Lücken bei Verfahrensdoku, TSE und vollständiger DATEV-Schnittstelle blockieren die echte Pilot-Compliance.

---

## 1. Compliance-Status-Tabelle

| # | Anforderung | Status | Evidenz |
|---|-------------|--------|---------|
| **GoBD** | | | |
| 1.1 | CashEntry APPEND-ONLY Modell | COMPLETE | `app/db/models_cash_company.py:342` (Doc + RESTRICT FKs) |
| 1.2 | DB-Trigger UPDATE-Schutz | COMPLETE | `alembic/versions/059_add_gobd_compliance_enhancements.py:91-133` (`gobd_prevent_cash_entry_update`) |
| 1.3 | DB-Trigger DELETE-Schutz | COMPLETE | `alembic/versions/059_...py:136-151` |
| 1.4 | DB-Trigger entry_number-Schutz | COMPLETE | `alembic/versions/059_...py:158-175` |
| 1.5 | Lückenlosigkeit (UNIQUE Constraint) | COMPLETE | `models_cash_company.py:454` (`ix_cash_entries_unique_number` UNIQUE) + `058_add_cash_module.py:311` |
| 1.6 | Sequential-Number-Service (Race-frei) | COMPLETE | `app/services/cash_service.py:1040` (`_get_next_entry_number` + `with_for_update()` Register-Lock @1036) |
| 1.7 | Service-Layer "raise GoBD" | PARTIAL | Trigger fängt es ab, aber kein expliziter `raise.*append.only` im Service - Fehler kommt nur aus DB |
| 1.8 | domain_events APPEND-ONLY | COMPLETE | `alembic/versions/151_gobd_insert_only_triggers.py:32-39` |
| 1.9 | gobd_audit_chain Immutability | COMPLETE | `229_add_gobd_audit_chain_immutability.py:33` + `234_fix_gobd_trigger_conflict.py:82` |
| 1.10 | finance_document_history Immutability | COMPLETE | `056_add_finance_document_history.py:120` |
| 1.11 | audit_logs Immutability | COMPLETE | `017_add_audit_log_immutability.py:96` |
| 1.12 | GoBD-Service zentral | COMPLETE | `app/services/gobd_compliance_service.py` + `app/services/compliance/gobd_service.py` |
| 1.13 | Audit-Chain mit Sequence-Verifikation | COMPLETE | `audit_chain_service.py:215-272` (Lückenerkennung) |
| **Verfahrensdokumentation** | | | |
| 2.1 | `docs/VERFAHRENSDOKUMENTATION.md` | MISSING | Kein File auf Disk (`find -iname "*verfahren*"` -> 0) |
| 2.2 | Auto-Generator-Service | COMPLETE | `app/services/compliance/procedure_documentation_service.py:1` (PDF/HTML/MD) |
| 2.3 | Generierte/persistierte Doku | MISSING | Service existiert, aber kein Output-File im Repo |
| **GDPR** | | | |
| 3.1 | Art. 17 Soft-Delete | COMPLETE | `app/services/document_services/gdpr_service.py:38-80` |
| 3.2 | Hard-Delete nach Retention (30 Tage) | COMPLETE | `cleanup_tasks.py:27` (`SOFT_DELETE_RETENTION_DAYS = 30`) + Beat-Schedule `celery_app.py:669` |
| 3.3 | Art. 20 Datenportabilität | COMPLETE | `app/api/v1/gdpr.py:342` `request_data_export` + `app/services/data_export_service.py` |
| 3.4 | Art. 30 Verzeichnis (`GDPRProcessingActivity`) | PARTIAL | Modell vorhanden `models_gdpr_compliance.py:157`, aber keine sichtbare Pflege-UI/Seed |
| 3.5 | Art. 33 Breach 72h-Notification | COMPLETE | `app/services/compliance/breach_notification_service.py:186-200` (`deadline_72h` + `is_deadline_met`) + `gdpr_tasks.py:435` `send_breach_notification` (Priority 9) |
| 3.6 | DPIA-Service | COMPLETE | `app/services/compliance/dpia_service.py` |
| 3.7 | Consent-Management | COMPLETE | `app/services/privacy/consent_service.py` |
| 3.8 | Data Subject Rights (Art. 15-22) | COMPLETE | `app/services/compliance/data_subject_rights_service.py:235` (Art. 20 Export) |
| 3.9 | GDPR vs §147 AO Konfliktlösung | COMPLETE | `retention_enforcement_service.py:1-46` (RETENTION_WINS, ANONYMIZE, SCHEDULE_POST_RETENTION) |
| **§147 AO 10-Jahre** | | | |
| 4.1 | Retention-Kategorien definiert | COMPLETE | `models_gdpr_compliance.py:220-226` (10 Doc-Types mit Frist) |
| 4.2 | Retention-Service | COMPLETE | `app/services/compliance/retention_service.py` + `retention_enforcement_service.py` |
| 4.3 | Automatisierte Archivierung | COMPLETE | `app/services/archive_service.py` + `gobd_retention_policies` Tabelle (`bpmn_models/gobd.py:201`) |
| 4.4 | Validation auf Buchungsdatum >10y | COMPLETE | `schemas.py:5012` (`Buchungsdatum darf nicht aelter als 10 Jahre sein`) |
| **DATEV** | | | |
| 5.1 | DATEVconnect OAuth2 | PARTIAL | `datev/connect/datev_auth_service.py` + `datev_connector.py:50-72` (Config), aber Token-Refresh-Flow nicht final auditiert |
| 5.2 | Buchungsstapel-Writer | COMPLETE | `app/services/datev/buchungsstapel_writer.py` |
| 5.3 | Belegbilder-Service | PARTIAL | `enabled_features` enthält "belege" (`datev_connector.py:69`), aber kein dedizierter Upload-Service gefunden |
| 5.4 | Kontenrahmen SKR03/SKR04 | COMPLETE | `datev/kontenrahmen/skr03.py` + `skr04.py` |
| 5.5 | Steuerberater-Paket | COMPLETE | `datev/steuerberater_package_service.py` |
| 5.6 | DATEV GoBD Compliance | COMPLETE | `datev/connect/gobd_compliance_service.py` |
| 5.7 | Plausibilitätsprüfung | COMPLETE | `datev/plausibility_service.py` |
| 5.8 | DATEV-Schnittstellen-Zertifizierung | MISSING | Keine offizielle Zertifizierung dokumentiert |
| **E-Invoicing (Jan 2025)** | | | |
| 6.1 | ZUGFeRD MINIMUM/BASIC_WL/EN16931/EXTENDED | COMPLETE | `einvoice/parser_service.py:352-361` + `zugferd_validator.py:10` |
| 6.2 | XRechnung Generator | COMPLETE | `einvoice/xrechnung_generator.py` + `mapping/xrechnung_ubl_mapper.py` |
| 6.3 | KOSIT-Validator (offiziell) | MISSING | `kosit` keyword 0 Treffer - eigener Mustang-Client (`mustang_client.py`), aber kein KOSIT-Validator-Wrapper |
| 6.4 | PEPPOL-Sender | COMPLETE | `einvoice/peppol_sender_service.py` |
| 6.5 | Receiver-Service | COMPLETE | `einvoice/receiver_service.py` |
| 6.6 | PDF/A-3 Embedder | COMPLETE | `einvoice/zugferd_embedder.py` |
| **TSE / KassenSichV** | | | |
| 7.1 | TSE-Modul vorhanden | MISSING | `app/**/tse*` und `**/kassen*` -> 0 Files |
| 7.2 | Kassen-Modul mit Endkunden-Bargeld | UNKNOWN | CashEntry ist B2B-orientiert (`counterparty_id -> business_entities`), kein POS-Endkunden-Workflow erkennbar |
| **Audit-Logging** | | | |
| 8.1 | AuditLog konsequent geschrieben | COMPLETE | 547 Vorkommen in 44 Service-Files (Grep `AuditLog\|audit_log`) |
| 8.2 | Sequence-basierte Audit-Chain | COMPLETE | `app/core/audit_logger.py:354,463` (`sequence_number` + Verifikation @423-470) |
| 8.3 | Merkle-Tree für Tamper-Evidence | COMPLETE | `app/services/compliance/merkle_tree_service.py` |
| 8.4 | Tax Authority Export (GoBD-DSF) | COMPLETE | `app/services/compliance/tax_authority_export_service.py` + `app/services/gdpdu_export_service.py` |

---

## 2. Top-3 Stärken

### S1. GoBD-Implementierung auf DB-Ebene ist exzellent
Vier voneinander unabhängige Trigger-Schichten (`059`, `151`, `229`, `234`) auf vier Tabellen (`cash_entries`, `domain_events`, `gobd_audit_chain`, `audit_logs`, `finance_document_history`) garantieren echte Datenbank-Unveränderbarkeit. Selbst direkte SQL-Injection oder Admin-Zugriff können einen Cash-Entry nicht manipulieren - der Trigger raised `GoBD-Verletzung`. Das ist Enterprise-Level und wird einer Betriebsprüfung standhalten.

### S2. Lückenlose entry_number-Sequenz mit korrekter Concurrency-Kontrolle
`cash_service.py:1040` verwendet `with_for_update()` auf dem `CashRegister` (@1036), bevor `MAX(entry_number) + 1` ermittelt wird. Das vermeidet die klassische Race Condition. UNIQUE-Constraint `(cash_register_id, fiscal_year, entry_number)` als zweite Defense-Linie. `tests/integration/test_cash_concurrent.py` testet das aktiv. GoBD-konform.

### S3. Tiefe GDPR-Implementierung mit echtem Konfliktmodell
`retention_enforcement_service.py` löst explizit den Konflikt §147 AO (10 Jahre Aufbewahrung) vs. Art. 17 DSGVO (Löschung) mit vier diskreten Strategien (RETENTION_WINS, ANONYMIZE_METADATA, SCHEDULE_POST_RETENTION, EXCEPTION_REQUIRED). Breach-Notification mit echtem 72h-Deadline-Tracking (`deadline_72h`, `is_deadline_met`) und Celery-Priority-9-Task ist über dem Branchendurchschnitt.

---

## 3. Top-5 Lücken (kritisch)

### L1. Verfahrensdokumentation existiert nur als Generator, nicht als Artefakt - HARD BLOCKER
`procedure_documentation_service.py` kann eine Verfahrensdoku generieren (PDF/HTML/MD), aber **kein einziges generiertes Dokument liegt im Repo**. Bei einer Betriebsprüfung wird der Prüfer die Verfahrensdoku **am ersten Tag** verlangen. Ohne diese ist GoBD-Compliance formal nicht nachweisbar - egal wie gut die Trigger sind. Die GoBD verlangt explizit eine "aussagekräftige Verfahrensdokumentation" (BMF-Schreiben 2019, Rz. 151-155).

**Fix:** CI-Job, der `procedure_documentation_service.generate()` pro Release ausführt und das Artefakt nach `docs/compliance/Verfahrensdokumentation_v{version}.pdf` ablegt + signiert.

### L2. KEINE TSE / KassenSichV-Anbindung
0 Files für `tse` oder `kassen` (außer `cash_entries` als Buchungslogik). Falls Bens System echte **Bargeldeinnahmen vom Endkunden** verarbeitet (nicht nur B2B-Einnahmen-Buchungen), ist das ein **§146a AO Verstoß**: Bußgeld bis 25.000 EUR pro Kasse. Die `CashEntry`-Struktur sieht eher nach Buchhaltungs-Kassenbuch aus (`counterparty -> business_entities`), nicht nach POS - aber das muss Ben für den Pilot **schriftlich klären**. Falls relevant: TSE-Provider-Anbindung (z.B. Epson, Swissbit, fiskaly cloud-TSE) ist ein 4-6-Wochen-Projekt.

### L3. KOSIT-Validator fehlt für E-Invoicing
Der eigene `mustang_client.py` validiert ZUGFeRD/XRechnung, aber für **B2G-Rechnungen ist KOSIT (Koordinierungsstelle für IT-Standards) der offizielle Validator**. Ohne KOSIT-Validierung können XRechnungen vom Empfänger (Behörde) abgelehnt werden. Das E-Invoicing-Mandat seit Jan 2025 verlangt für B2B-Empfang strukturierte Formate - Schemavalidierung allein reicht für Pilot, aber für Behörden-Rechnungen Pflicht.

**Fix:** KOSIT-Validator-Jar als Subprocess oder Cloud-Service integrieren (`einvoice/validator_service.py` erweitern).

### L4. Art. 30 DSGVO Verzeichnis-Verarbeitungstätigkeiten nicht aktiv gepflegt
`GDPRProcessingActivity` Modell existiert (`models_gdpr_compliance.py:157`, `retention_period_days` etc.), aber:
- Keine sichtbare Migration mit Initial-Seed der typischen Aktivitäten (Auth, OCR, Backup, Email-Import, ...)
- Keine Admin-UI im Frontend gefunden
- Keine API-Endpoints für CRUD auf `gdpr_processing_activities`

Bei DSGVO-Audit ist das Verzeichnis Pflicht (Art. 30) - **leeres Modell = nicht erfüllt**.

### L5. DATEV-Belegbilderservice nur teil-implementiert
`datev_connector.py:69` listet `"belege"` als enabled_feature, aber:
- Kein dedizierter `belegbilder_service.py` gefunden
- `scan_to_booking_orchestrator.py` existiert, aber kein Upload-Endpoint zum DATEV Belegbilder-API
- Belegverknüpfung (`beleglink_prefix`) konfigurierbar, aber Upload-Flow unklar

Für DATEV-Schnittstellen-Zertifizierung ist Belegbilder-Upload **Pflichtbestandteil**.

---

## 4. Compliance-Pilot-Readiness-Note: **6.5 / 10**

**Begründung:**
- **+3 Punkte:** GoBD-DB-Layer (Trigger, Audit-Chain, Merkle, Sequence) auf Bank-Niveau
- **+2 Punkte:** GDPR-Tiefe (Breach-72h, Retention-Konflikt, Data-Subject-Rights)
- **+1 Punkt:** E-Invoicing breite Format-Abdeckung (ZUGFeRD alle Profile + XRechnung + PEPPOL)
- **+0.5 Punkte:** DATEV-Connector-Skelett vorhanden
- **-2 Punkte:** Verfahrensdokumentation als Artefakt **fehlt komplett**
- **-1 Punkt:** TSE-Frage ungeklärt (potentielles §146a-AO-Risiko)
- **-0.5 Punkte:** Art. 30-Verzeichnis nur Modell, keine Daten
- **-0.5 Punkte:** KOSIT-Validator fehlt

Pilot mit **Inhouse-/B2B-only-Buchungen ohne Bargeld-POS** und **interner Steuerberater-Anbindung** ist machbar. Pilot mit echtem Endkunden-Cash oder Behörden-XRechnungen ist **nicht** ready.

---

## 5. DATEV-Zertifizierung in 6 Monaten - was BLOCKIERT?

### Hard Blocker (nicht in 6 Monaten machbar ohne Eskalation)
1. **Offizielle DATEV-Schnittstellenzertifizierung als Prozess fehlt komplett.** DATEV-Zertifizierung erfordert: (a) DATEV-Partnerschaftsantrag, (b) technische Konformitätsprüfung, (c) Schulung, (d) Vertrag. Allein der DATEV-Side-Prozess dauert typisch 4-9 Monate. **Heute starten = Q4-2026-Termin realistisch.**
2. **Verfahrensdokumentation muss als signiertes PDF + verstetigtes Artefakt vorliegen** (siehe L1). Generator existiert, aber Output, Review, Versionierung, Signatur fehlen.
3. **Belegbilderservice produktiv** (siehe L5). DATEV-Zertifizierung verlangt End-to-End-Belege-Upload mit `beleglink` zu Buchung.

### Soft Blocker (in 6 Monaten machbar)
4. **OAuth2-Token-Refresh-Robustheit** (`datev_auth_service.py` final hardenen + Tests).
5. **Buchungsstapel-Writer mit echtem DATEV-Sandbox getestet** (Festschreibung manuell/automatisch korrekt).
6. **GoBD-Konformitätsbescheinigung** (kann mit unserer Trigger-Architektur erbracht werden, braucht aber Audit-Bericht eines IDW-zertifizierten Prüfers).
7. **Tax Authority Export GDPdU/IDEA-Format** existiert (`tax_authority_export_service.py`) - muss gegen aktuelles Format-Schema 2025 verifiziert werden.

### Empfehlung
6-Monats-Plan ist **nur realistisch**, wenn parallel: (a) DATEV-Partnerschaft **diese Woche** beantragt wird, (b) ein IDW-Prüfer für Q3 gebucht wird, (c) L1+L5 in den nächsten 30 Tagen geschlossen werden. Sonst Realismus-Korrektur auf 9-12 Monate.

---

**Bottom Line:** Das System hat ein sehr starkes Compliance-Fundament auf Code-/DB-Ebene, das viele Wettbewerber nicht haben. Die Lücken sind nicht technisch, sondern **prozessual und dokumentarisch**. Ein erfahrener Compliance-Officer kann die Lücken in 8-12 Wochen schließen - ohne ihn ist die DATEV-Zertifizierung in 6 Monaten unrealistisch.
