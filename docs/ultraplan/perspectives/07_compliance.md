# 07 — Compliance-Perspektive

**Rolle:** Compliance Officer mit Fokus GoBD/GDPR/DATEV. Bußgeld-erfahren. Toleranzgrenze: null.
**Datum:** 2026-05-03
**Branch:** feature/ocr-performance
**Quellen:** 00_GROUND_TRUTH, 00i_COMPLIANCE_AUDIT, 00c_DB_SCHEMA_AUDIT, 00h_SECURITY_AUDIT + eigene Recherche.

---

## 1-Sentence-Verdict

Technisch eines der saubersten Compliance-Fundamente, die ich in einem deutschen Mittelstandstool gesehen habe — aber ohne signierte Verfahrensdokumentation, gepflegtes Art.-30-Verzeichnis und KOSIT-Validierung darf das System bei einer Betriebsprüfung oder ersten B2G-XRechnung nicht ans Tageslicht.

---

## 2. Compliance-Status-Tabelle

| # | Anforderung | Status | Evidenz / Datei:Zeile |
|---|---|---|---|
| 1 | GoBD Unveränderbarkeit (DB-Trigger) | COMPLETE | `alembic/versions/059_add_gobd_compliance_enhancements.py:91-175` (UPDATE/DELETE/entry_number-Schutz), `151_gobd_insert_only_triggers.py:32-39`, `229_add_gobd_audit_chain_immutability.py:33`, `017_add_audit_log_immutability.py:96` |
| 2 | GoBD Service-Layer-Schutz | PARTIAL | Trigger fängt es, aber `app/services/cash_service.py` raised keine explizite `GoBDViolation` — Fehler kommt rein aus DB |
| 3 | GoBD Lückenlosigkeit entry_number | COMPLETE | `models_cash_company.py:454` UNIQUE `(cash_register_id, fiscal_year, entry_number)` + `cash_service.py:1036-1040` `with_for_update()` Register-Lock |
| 4 | Lücken-Recovery (Storno-Pattern) | COMPLETE | `models_cash_company.py:343-353` (`is_cancelled`, `cancelled_by_entry_id` Self-FK) — keine echten Lücken, nur Storno-Verkettung |
| 5 | Verfahrensdokumentation als Artefakt | **MISSING** | `find -iname "*verfahren*"` → 0 Treffer. Generator existiert (`procedure_documentation_service.py`), Output nicht im Repo, nicht signiert, nicht versioniert |
| 6 | GDPR Art. 17 Soft-Delete + Hard-Delete-Schedule | COMPLETE | `gdpr_service.py:38-80` + `cleanup_tasks.py:27` (`SOFT_DELETE_RETENTION_DAYS = 30`) + `celery_app.py:669` Beat-Schedule |
| 7 | GDPR Art. 20 Datenportabilität | COMPLETE | `api/v1/gdpr.py:342` `request_data_export` + `data_export_service.py` + `data_subject_rights_service.py:235` |
| 8 | GDPR Art. 30 Verzeichnis (`GDPRProcessingActivity`) | PARTIAL | Modell `models_gdpr_compliance.py:157` da, aber keine Migration mit Initial-Seed, keine Admin-UI, keine API-Endpoints — leer = nicht erfüllt |
| 9 | GDPR Art. 33 Breach 72h | COMPLETE | `breach_notification_service.py:186-200` (`deadline_72h`, `is_deadline_met`) + `gdpr_tasks.py:435` Celery Priority 9 |
| 10 | DATEV-Schnittstellen-Zertifizierung | **MISSING** | Kein Antrag, kein Vertrag, kein Audit-Bericht im Repo — nur Connector-Skelett |
| 11 | DATEV OAuth2-Token-Refresh | PARTIAL | `datev_auth_service.py` + `datev_connector.py:50-72` — Refresh-Flow nicht final auditiert |
| 12 | DATEV Belegbilder-Upload | PARTIAL | `enabled_features=["belege"]` (`datev_connector.py:69`), aber kein `belegbilder_service.py` mit Upload-Endpoint |
| 13 | E-Invoicing ZUGFeRD-Profile | COMPLETE | `einvoice/parser_service.py:352-361` MINIMUM, BASIC_WL, BASIC, EN16931, EXTENDED + `zugferd_validator.py:10` |
| 14 | E-Invoicing XRechnung Generator | COMPLETE | `einvoice/xrechnung_generator.py` + `mapping/xrechnung_ubl_mapper.py` (UBL 2.1) |
| 15 | KOSIT-Validator (B2G-Pflicht) | **MISSING** | 0 Treffer für `kosit`. Eigener `mustang_client.py` nur, kein offizieller Validator |
| 16 | PEPPOL-Sender + Receiver | COMPLETE | `einvoice/peppol_sender_service.py` + `receiver_service.py` |
| 17 | §147 AO 10-Jahre automatisiert | COMPLETE | `retention_service.py` + `retention_enforcement_service.py` + `gobd_retention_policies` Tabelle + `schemas.py:5012` Validation |
| 18 | §147 AO vs Art. 17 DSGVO Konfliktlösung | COMPLETE | `retention_enforcement_service.py:1-46` (RETENTION_WINS / ANONYMIZE / SCHEDULE_POST_RETENTION / EXCEPTION_REQUIRED) |
| 19 | TSE / KassenSichV §146a AO | **MISSING / UNCLEAR** | 0 Files für `tse` oder `kassen*`. CashEntry ist B2B-Buchungslogik, kein POS — Anwendbarkeit muss schriftlich geklärt werden |
| 20 | Domain-Event Hash-Chain (Apr 2026) | COMPLETE | `models_misc.py:814-853` (`event_hash`, `previous_hash`, `chain_hash`, sequence_number, UniqueConstraint) + Migration `254_event_store_hash_chain.py` |
| 21 | Hash-Chain Tamper-Evidence | COMPLETE | `merkle_tree_service.py` + `audit_chain_service.py:215-272` Sequence-Verifikation |
| 22 | Tax Authority Export GDPdU/IDEA | PARTIAL | `tax_authority_export_service.py` + `gdpdu_export_service.py` existieren, Format-Schema 2025 nicht gegen aktuelle BMF-Spezifikation verifiziert |
| 23 | DPIA-Service Art. 35 | COMPLETE | `app/services/compliance/dpia_service.py` |

---

## 3. Top-3 Stärken

**S1 — GoBD-DB-Layer auf Bank-Niveau.** Vier voneinander unabhängige Trigger-Schichten auf fünf Tabellen (`cash_entries`, `domain_events`, `gobd_audit_chain`, `audit_logs`, `finance_document_history`). Selbst direkter SQL-Zugriff durch einen entwendeten DB-Account kann keinen Cash-Entry manipulieren — der Trigger raised `GoBD-Verletzung`. Das hält jeder Außenprüfung stand und ist die seltene Implementierung, bei der "APPEND-ONLY" nicht nur Service-Konvention ist, sondern auf der untersten Schicht erzwungen wird. **Service-Layer raised allerdings keinen sprechenden Fehler — der Trigger-Error landet roh beim User.** Polituraufgabe.

**S2 — Echtes §147-AO-vs-Art-17-DSGVO-Konfliktmodell.** `retention_enforcement_service.py` löst den klassischen Konflikt mit vier diskreten Strategien (RETENTION_WINS, ANONYMIZE_METADATA, SCHEDULE_POST_RETENTION, EXCEPTION_REQUIRED). Die meisten Wettbewerber haben hier entweder gar nichts oder einen verschwommenen Hardcode. Plus echte 72h-Breach-Notification mit `deadline_72h`-Tracking und Celery-Priority-9-Task — überdurchschnittlich.

**S3 — Domain-Event Hash-Chain (Apr 2026) ist GoBD-tauglich.** SHA-256 verkettet, kanonisches JSON (`sort_keys=True`, `separators=(",", ":")`), Genesis-Hash, `UniqueConstraint(aggregate_type, aggregate_id, sequence_number)`. Migration 254 + Event-Store sauber. Das übertrifft die GoBD-Anforderung "nachvollziehbare Aufzeichnung" deutlich und liefert ein Tamper-Evidence-Niveau, das ein IDW-Prüfer als Konformitätsbescheinigung schreiben würde.

---

## 4. Top-5 Lücken (DATEV-blockierend bzw. prüfungs-blockierend)

**L1 — Verfahrensdokumentation existiert als Generator, nicht als Artefakt. HARD BLOCKER.** GoBD-BMF-Schreiben 2019 Rz. 151-155 verlangt eine "aussagekräftige Verfahrensdokumentation". Bei Außenprüfung **erste Anforderung des Prüfers, Tag 1**. Generator-Code allein ist nichts. Das System muss pro Release ein PDF erzeugen, signieren, versionieren, archivieren — und die Doku muss organisatorische Verantwortlichkeiten, Datenflüsse, Kontrollen, Notfallpläne enthalten, die nicht aus Code generierbar sind. Schadenpotential: Schätzungsbescheid + Verzögerungsgeld bis 250.000 €.

**L2 — KEINE TSE/KassenSichV-Anbindung, Anwendbarkeit ungeklärt.** §146a AO + KassenSichV verlangt für jede elektronische Aufzeichnung von Bargeld-Endkundenumsätzen eine zertifizierte TSE. Bens System hat `cash_entries` mit `counterparty -> business_entities` — sieht nach B2B-Kassenbuch aus, nicht POS. **Aber bevor Pilot startet muss schriftlich (Steuerberater + Anwalt) geklärt werden, dass kein Endkunden-Bargeld erfasst wird.** Bußgeld §379 AO bis 25.000 € pro Kasse, plus Hinzuschätzung. Falls relevant: Cloud-TSE-Anbindung (fiskaly, Swissbit, Epson) ist 4-6-Wochen-Projekt.

**L3 — KOSIT-Validator fehlt für B2G-XRechnungen.** Seit 27.11.2020 müssen Rechnungen an Bundesbehörden als XRechnung eingereicht werden, ab Jan 2025 ist B2B-Empfang von strukturierten E-Rechnungen Pflicht (BEG IV, §14 UStG). KOSIT (Koordinierungsstelle für IT-Standards) ist der **offizielle Validator** für Bundes- und viele Landes-Empfänger. Mustang reicht für Selbsttest, aber B2G-Empfänger lehnen ohne KOSIT-Konformitätsstempel ab. Fix: KOSIT-Validator-Jar als Subprocess oder Cloud-Service.

**L4 — Art. 30 DSGVO Verzeichnis ist Modell ohne Daten.** `GDPRProcessingActivity` Klasse existiert, aber keine Initial-Seed-Migration, keine Admin-UI, keine API-Endpoints, kein Pflege-Workflow. Bei DSGVO-Prüfung durch LfDI ist das Verzeichnis **Pflicht** (Art. 30 Abs. 1 DSGVO). Leeres Modell ≠ erfüllt. Bußgeld bis 10 Mio EUR oder 2 % Konzernumsatz. Fix: Seed-Migration mit den ~20 typischen Aktivitäten (Auth, OCR, Backup, Email-Import, DATEV-Export, RAG, Mahnwesen, ...) + UI in Admin-Bereich.

**L5 — DATEV-Belegbilder-Upload nicht produktiv + keine Schnittstellen-Zertifizierung beantragt.** `enabled_features=["belege"]` als Konfig-Flag ist nicht dasselbe wie ein funktionierender Upload-Service mit Beleg-Verknüpfung über `beleglink_prefix`. DATEV-Schnittstellen-Zertifizierung verlangt End-to-End-Test (Buchungsstapel → Beleg-Upload → Beleg-Verknüpfung in DATEV-Mandantenbuchhaltung) und funktioniert nicht ohne Partnerschaftsantrag. Heute weder beantragt noch im Repo dokumentiert.

---

## 5. Note Compliance-Readiness: **6.5 / 10**

Aufschlüsselung:
- +3.0 GoBD-DB-Layer (Trigger, Hash-Chain, Audit, Sequence-Lock) — Best-in-Class
- +2.0 GDPR-Tiefe (Breach-72h, Konflikt-Resolver, Data-Subject-Rights, DPIA)
- +1.0 E-Invoicing breite Format-Abdeckung (ZUGFeRD alle 5 Profile + XRechnung + PEPPOL + PDF/A-3)
- +0.5 DATEV-Connector-Skelett mit SKR03/SKR04 vorhanden
- −2.0 Verfahrensdokumentation als Artefakt fehlt komplett
- −1.0 TSE/KassenSichV-Anwendbarkeit ungeklärt
- −0.5 Art. 30 leer
- −0.5 KOSIT-Validator fehlt

**Pilot mit B2B-only + interner Steuerberater-Anbindung** ist machbar. **Pilot mit Endkunden-Cash, Behörden-XRechnungen oder vor Außenprüfung ohne Verfahrensdoku-Artefakt** ist **nicht ready**.

---

## 6. DATEV-Zertifizierungs-Pfad (Reihenfolge)

DATEV-Schnittstellen-Zertifizierung (offiziell "DATEVconnect online" + "DATEV Belege online"-Konformität) ist ein 6–9-Monats-Prozess auf DATEV-Seite. Reihenfolge:

1. **Woche 1:** DATEV-Partnerschaftsantrag stellen (DATEV Marketplace + Software-Partner-Programm). Parallel: NDA + technisches Briefing anfordern.
2. **Woche 1–2:** IDW-zertifizierten Wirtschaftsprüfer für Q3-Konformitätsbescheinigung beauftragen (IDW PS 880 / IDW RS FAIT 1-5). Vorlauf hier ist real der Engpass.
3. **Woche 2–4:** L1 schließen — Verfahrensdokumentation als signiertes PDF v1.0 erzeugen, organisatorische Kapitel ergänzen, in Repo + Wiki + Steuerberater-Postfach archivieren. CI-Job, der pro Release neue Version generiert + signiert.
4. **Woche 2–4:** L4 schließen — Art. 30 Verzeichnis seeden, UI freischalten, Datenschutzbeauftragter signiert ab.
5. **Woche 4–8:** L5 schließen — Belegbilderservice gegen DATEV-Sandbox final implementieren + End-to-End testen (Buchungsstapel-Festschreibung + Beleg-Upload + Verknüpfung).
6. **Woche 4–8:** OAuth2-Token-Refresh-Härtung + Fehlerbehandlung, GDPdU/IDEA-Export gegen aktuelles BMF-Schema verifizieren.
7. **Woche 8–12:** L3 schließen — KOSIT-Validator integrieren (Cloud-Service oder Jar-Subprocess), Smoketest gegen 5 reale Behörden-XRechnungen.
8. **Woche 12–16:** IDW-Prüfung durchführen. Ergebnis ist GoBD-Konformitätsbescheinigung, Voraussetzung für DATEV-Audit.
9. **Woche 16–24:** DATEV-Konformitätsprüfung (technisch + Schulung), Vertrag.

**Realistisch: Q4 2026 / Q1 2027** für DATEV-Zertifikat. Wenn Antrag erst in 30 Tagen gestellt wird, schiebt sich das auf Q1–Q2 2027. **6-Monats-Plan ist nur dann realistisch, wenn diese Woche der Antrag rausgeht UND der IDW-Prüfer fest gebucht ist.** Sonst Realismus-Korrektur.

---

## 7. Drei sofort-Maßnahmen vor Pilot

**Sofort-1 (Tag 1–7) — TSE-Risiko schriftlich klären.** Steuerberater + Fachanwalt Steuerrecht bestätigen lassen, dass das Pilot-Unternehmen **keine Bargeld-Endkundenumsätze** erfasst und der Pilot deshalb nicht KassenSichV-pflichtig ist. Schriftliches Memo, signiert, in `docs/compliance/`. Ohne dieses Memo darf der Pilot nicht starten — sonst ist Ben persönlich für jedes nicht-TSE-gesicherte Cash-Event haftbar.

**Sofort-2 (Tag 1–14) — Verfahrensdokumentation v1.0 erzeugen, signieren, ablegen.** `procedure_documentation_service.generate()` ausführen, organisatorische Kapitel (Verantwortlichkeiten, Datenflüsse, Notfallplan, Datensicherung, Berechtigungskonzept, Mandantentrennung) manuell ergänzen, PDF/A-3, signiert (PAdES), nach `docs/compliance/Verfahrensdokumentation_v1.0.pdf`. Ohne dieses Artefakt ist der Pilot bei Außenprüfung nicht verteidigungsfähig — egal wie gut die Trigger sind.

**Sofort-3 (Tag 1–21) — Art. 30 Verzeichnis seeden + Datenschutzbeauftragten benennen.** Initial-Seed-Migration mit den ~20 typischen Verarbeitungstätigkeiten erstellen, Datenschutzbeauftragten (intern oder extern) bestellen + im Verzeichnis hinterlegen, AVV mit allen Auftragsverarbeitern (MinIO-Provider, falls extern; OCR-Provider falls extern; Email-Provider) prüfen + ablegen. Ohne aktives Verzeichnis ist der Pilot bei jeder LfDI-Anfrage angreifbar.

---

**Bottom Line.** Das technische Compliance-Fundament ist auf einem Niveau, das die meisten lexoffice/sevDesk-Wettbewerber nicht erreichen. Die Lücken sind nicht im Code, sondern in **Prozess, Dokumentation, organisatorischer Hülle**. Genau das, was Entwickler typisch unterschätzen — und was bei einer Prüfung zuerst auf den Tisch kommt. Mit einem erfahrenen Compliance-Officer 8–12 Wochen Arbeit. Ohne ihn ist DATEV-Zertifizierung in 6 Monaten Wunschdenken.

— Wortzahl: ca. 1.380.
