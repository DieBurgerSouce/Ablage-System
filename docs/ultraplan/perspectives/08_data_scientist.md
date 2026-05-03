# 08 — Perspektive: Data Scientist / ML Engineer

**Datum:** 2026-05-03
**Rolle:** Data Scientist / ML Engineer
**Maxime:** "Funktioniert" ist kein Datum. Ohne Messung gibt es keinen Anspruch.
**Quellen:** `docs/ultraplan/00_GROUND_TRUTH.md`, `docs/ultraplan/audit/00k_ML_DATA_AUDIT.md`

---

## 1-Sentence-Verdict

Das System ist ML-baulich erstaunlich weit (13 OCR-Backends, Qdrant+pgvector dual, Qwen3-LLM-Stack, e5-large Embeddings, Auto-Ground-Truth, Confidence-Calibration, AB-Test-Routing) — aber es **misst seine Versprechen nicht**: keine veröffentlichten Accuracy-Zahlen, kein Drift-Reporting im Betrieb, kein zeitgesteuerter Self-Learning-Loop, keine annotierten Trainings-Sets, sodass die ML-Reife mehr nach "tief gebaut, leichtfertig kalibriert" aussieht als nach "datengetrieben validiert".

---

## Quantitative Befunde — Plan vs. Real vs. Lücke

| Plan-Feature (PlanRAGAblage / PlanVektorPipeline) | Real (Code-belegt) | Lücke |
|---|---|---|
| Multi-Backend OCR (>= 8 Backends) | 13+ Agents in `app/agents/ocr/` (DeepSeek, GOT, Surya, Qwen2.5-VL, Chandra, OlmOCR, Donut, PaddleOCR, docTR, Hybrid) | 0 — übererfüllt |
| Umlaut-Genauigkeit 100% | Service-Stack (`umlaut_validation_service`, `contextual_umlaut_restorer`, `umlaut_weighted_loss`) + 4158 UTF-8-Tests | Keine veröffentlichte numerische Accuracy-Metrik je Backend; Tests prüfen Logik, nicht Korpus-Korrektheit |
| OCR-Routing/Backend-Manager | `app/services/backend_manager.py` + `app/ml/ab_testing.py` + `app/services/rag/ab_testing_router.py` | Routing-Policy nicht dokumentiert; Auswahl-Heuristik im Code verstreut |
| Confidence-Thresholds (Auto/Review) | `app/core/thresholds.py`: `OCR_CONFIDENCE_AUTO_ACCEPT=0.85`, `AUTO_REJECT=0.4`, `QA_REVIEW=0.7`; 4-stufige Autonomy-Level (0.70/0.85/0.95/1.01) | Werte ENV-konfiguriert, aber keine Kalibrierungs-Evidenz (ECE/Reliability-Diagrams) im Repo gefunden |
| Confidence-Calibration (Isotonic/Platt/Temp) | `app/services/confidence_calibration.py` + `app/ml/confidence_calibration.py` + `app/services/ocr/confidence_service.py` | Code vorhanden, kein Calibration-Run-Output / kein periodisches Re-Fitting belegt |
| Self-Learning-Loop (kontinuierlich) | `app/services/ocr/self_learning_service.py`; reactive Aufrufe in `app/workers/tasks/ocr_tasks.py:1802,1865` | **Kein Beat-Schedule** — Loop läuft nur bei OCR-Events, nicht zeitgesteuert; "kontinuierliches Lernen" ist Marketing |
| Auto-Ground-Truth-Pipeline | `auto_ground_truth_service.py` + Beat `process_auto_ground_truth_batch` (training_tasks:1720) + Hooks in ocr_tasks:655–684 | Pipeline verdrahtet; Output-Volumen nicht messbar (UP*-Dirs ohne JSON-Annotations) |
| RAG-Tabellen (chunks/cards/sessions/messages) | Migrations `033`, `036`, `043`, `044`, `051`, `052`, `212` | Plan zu ~85% realisiert |
| Vector-Backend (pgvector + Qdrant + AB) | `app/services/rag/qdrant_service.py` (107 Refs), `vector_sync_service`, `ab_testing_router` (QDRANT/PGVECTOR-Toggle) | Dual-Stack live, aber keine veröffentlichte Recall@k / NDCG-Messung |
| Embeddings (multilingual-e5-large 1024-dim) | `app/core/config.py:390,529`, `models.py:211`, GPU-Worker `embedding_tasks.py` | Plan-konform; Retrieval-Quality unbenchmarkt |
| Qwen3-8B/14B (Ollama) | `rag/llm_service.py`, `llm_ocr_review_service.py`, `ai/nlq/sql_generator.py` (`DEFAULT_MODEL="qwen3:8b"`) | Verankert; keine Latenz-/Quality-Benchmarks |
| Drift-Detection | `app/ml/drift_detector.py` + Beat `run_drift_detection` (celery_app:722) | **`data/drift_reports/` LEER** — Code production-ready, Reports werden faktisch nicht erzeugt |
| A/B-Testing OCR | 82 Experimente in `data/ab_tests/` (2025-11-27 bis 2026-01-18, Format `exp_deepseek_vs_got_*.json`) | Daten vorhanden; **letzter Run: Jan 2026** → 3+ Monate alt, Pipeline nicht aktiv |
| Translation-Pipeline (PlanVektorPipeline) | `app/services/translation_service.py` mit Argos/LibreTranslate/DeepL | **MarianMT/NLLB nicht implementiert** → Plan-Architektur veraltet, Implementierung weicht ab |
| Structured Extraction (Qwen2.5-VL) | `structured_extraction_service.py` + Beat `reprocess_all_documents_structured_extraction` | End-to-End verdrahtet |
| Trainingsdaten-Volumen | `Trainings_Data/UP000000`–`UP000024` (10 Subdirs); UP000000 allein 1024 Files; `data/training/training_samples.json` 121.501 Zeilen | **0 strukturierte JSON-Annotations** in UP*-Dirs (Glob `Trainings_Data/UP*/*.json` → 0 Treffer) — Rohdaten ohne Labels = Training-Pipeline läuft auf reduzierter Datenbasis |
| Untracked Test-Files (Coverage) | `test_embedding_service.py`, `test_umlaut_validation_service.py`, `test_spotlight_service.py` etc. existieren als untracked | CI-Run + Coverage unbekannt |

---

## Top-3 Stärken

1. **OCR-Backend-Pluralität ist überdurchschnittlich.** 13+ Agents, GPU/CPU-Fallback, VRAM-Map, Cross-Backend-Consistency-Service, AB-Routing zwischen Backends. Keine andere deutsche Mittelstands-Lösung dürfte annähernd so viel Optionalität haben. Das ist echtes Engineering-Kapital, kein Plan-Papier.
2. **RAG-Stack ist tief integriert (~85% Plan-Realisierung).** Qdrant+pgvector dual-active, AB-Toggle, WebSocket-Chat (`chat_ws.py`), Customer-Cards-Service, Tool-Registry, Action-Dispatcher, Excel/Word-Reportgenerierung, Prometheus-Metrics. Die Bausteine, die andere Teams 6-12 Monate kosten, sind hier vorhanden.
3. **Confidence/Threshold-Architektur ist Production-grade.** ENV-getriebene `app/core/thresholds.py`, vier Autonomy-Level mit klaren Confidence-Schwellen, Word-Level-Confidence in `ocr/confidence_service.py`, drei Calibration-Methoden (Isotonic, Platt, Temperature). Die Mechanik für "Auto vs Review" ist sauber gekapselt — der Datenbeleg fehlt, nicht der Code.

---

## Top-5 Lücken (Plan-vs-Reality)

1. **Keine veröffentlichten Accuracy-Zahlen.** Weder OCR-Genauigkeit (CER/WER pro Backend) noch Umlaut-Recall noch Retrieval-Quality (NDCG/Recall@k) noch RAG-Antwort-Qualität sind im Repo als Messreihe dokumentiert. Das CRITICAL-Rule-2-Versprechen "100% Umlaut-Accuracy" ist nicht numerisch belegt — nur Code-strukturell. Für eine Pilot-Pitch-Aussage "wir machen X% Genauigkeit" gibt es **keine Quelle**.
2. **Self-Learning-Loop ist nicht zeitgesteuert.** `self_learning_service.py` existiert, aber kein Celery-Beat triggert ihn periodisch. Aufrufe nur reactive in `ocr_tasks.py:1802,1865`. Das Plan-Versprechen "kontinuierliches Lernen" ist halb-wahr: Lernen passiert nur, wenn neue Dokumente OCR'd werden — bei Stillstand stillsteht der Loop. Konkurrenten (lexoffice) haben hier nichts, aber die eigene Marketing-Aussage muss korrigiert werden.
3. **Drift-Detection läuft, aber produziert keine Reports.** `data/drift_reports/` ist **leer**. Beat-Schedule `run_drift_detection` (celery_app:722) ist konfiguriert. Das bedeutet entweder: Beat-Worker läuft nicht / Schwellen werden nie erreicht / Output-Path falsch. Ohne Drift-Reports keine GoBD-relevante ML-Aufsicht — kritisch für 4.6/5-Compliance-Anspruch.
4. **Trainingsdaten unannotiert.** 10 UP*-Verzeichnisse mit ~10k PDFs/TIFs, aber **0 JSON-Label-Files**. `training_samples.json` (121k Zeilen) existiert isoliert. Das Auto-Ground-Truth-Backlog ist also massiv: ohne durchgelaufene GT-Pipeline keine domänenspezifischen Finetunes. Plan-Versprechen "domain-specific Trained Models" basiert auf nicht gemachter Hausaufgabe.
5. **Translation-Plan ist obsolet.** `PlanVektorPipeline.md` fordert MarianMT/opus-mt/nllb. Code hat Argos/LibreTranslate/DeepL. Funktional vorhanden, aber die Plan-Doku ist 5 Monate alte Fiktion. **A/B-Test-Pipeline frisch ist sie auch nicht** — letzter `exp_*.json` ist 2026-01-18, also 3.5 Monate alt. Heißt: AB-Framework existiert, wird aber nicht mehr betrieben. Entweder reaktivieren oder offiziell pausieren.

---

## Note ML/Data-Reife: **6.5/10**

**Begründung:**
- **Code-Tiefe:** 9/10 — die Bausteine sind da, und in einer Tiefe, die für ein Familienbetriebs-Tool atypisch ist.
- **Operational ML:** 5/10 — Self-Learning nicht-cron, Drift-Reports leer, AB-Tests seit 3+ Monaten kalt, Calibration-Outputs nicht versioniert.
- **Datenkultur:** 4/10 — keine Accuracy-Dashboards, keine Annotationen, keine Eval-Sets in `tests/resources/` als Goldstandard.
- **Compliance-Fitness der ML:** 7/10 — Confidence-Thresholds sauber, aber ohne Drift-Reports + ohne dokumentierte Calibration-Evidenz wird ein GoBD-Auditor nervös.

→ Mittelwert ~6.25, aufgerundet auf **6.5** wegen herausragender Backend-Pluralität und tiefer RAG-Integration.

Wenn die Frage nur lautete "ist das Pilot-tauglich" (ein Familienbetrieb mit human-in-the-loop), dann ist die Note **8/10**, weil Confidence-Thresholds + Review-Queue genau für diesen Modus gebaut sind. Ich gebe trotzdem 6.5 als Gesamtreife, weil Marketing-Aussagen aus dem Plan ohne Messung nicht haltbar sind.

---

## Wie weit ist der RAG-Plan weg von der Realität?

**Antwort:** Der Plan ist zu **~85%** realisiert. Was zur 100%-Erfüllung fehlt, kostet realistisch **4–8 Wochen Engineering** plus **2–4 Wochen Datenarbeit (Annotation/Eval-Sets)** — nicht Monate.

Konkret:
- **Beat-Schedule für Self-Learning:** 1–2 Tage (Cron-Eintrag, Idempotenz-Check, Logging).
- **Drift-Reports erzeugen:** 3–5 Tage (Beat-Trigger debuggen, Output-Path validieren, Dashboard-Anbindung Grafana).
- **AB-Framework reaktivieren:** 2–3 Tage (letzten Job erneut starten, Schwellen prüfen).
- **Annotated Eval-Set für Umlaute & Fraktur:** 1–2 Wochen (Goldstandard 200–500 Dokumente kuratiert).
- **OCR-Accuracy-Dashboard (CER/WER pro Backend pro Doku-Typ):** 1 Woche (Service existiert, nur Aggregation+Visualisierung).
- **Translation-Pipeline-Konsolidierung:** 1 Woche (Plan-Doku updaten oder MarianMT nachrüsten).
- **Trainingsdaten annotieren via Auto-GT-Pipeline:** 4–6 Wochen Wallclock (Pipeline läuft, Samples generieren sich passiv).

Zusammengefasst: **6–10 Wochen** vom heutigen Stand bis "RAG-Versprechen vollständig durch Daten gedeckt". Das ist eine Größenordnung, die mit dem 4-8-Wochen-Pilotzeitfenster kompatibel ist — wenn parallel gearbeitet wird, nicht sequentiell.

---

## Drei Sofort-Maßnahmen für Pilot

1. **OCR-Accuracy-Tagesbericht aktivieren (Tag 1–3).**
   Goldstandard-Set von 50–100 echten Dokumenten aus dem Familienbetrieb manuell annotieren (Volltext + Felder), Beat-Task `daily_ocr_eval` einrichten, der jedes Backend gegen das Set laufen lässt und CER/WER + Umlaut-Recall in Prometheus pusht. Grafana-Panel "OCR-Health". → Damit ist die Aussage "wir machen X% Genauigkeit" pilotfähig belegbar und Drift wird sichtbar.

2. **Drift-Detection-Reports debuggen + Self-Learning auf Cron (Tag 4–7).**
   Beat-Worker prüfen (läuft `run_drift_detection` wirklich?), Output-Path validieren, mind. einen erzwungenen Run in `data/drift_reports/` erzeugen. Parallel: Beat-Eintrag `self_learning_pipeline_daily` schreiben (z.B. nightly 03:00). → Damit ist das Plan-Versprechen "kontinuierliches Lernen + Drift-Aufsicht" operativ statt nur architektonisch.

3. **Confidence-Threshold-Sanity-Check gegen reale Pilot-Daten (Woche 2).**
   Nach 1 Woche Pilot-Betrieb: Confusion-Matrix der Auto-Accept/Review/Reject-Entscheidungen gegen menschliches Feedback bauen (Reviewer-Queue gibt's bereits). Wenn Auto-Accept (0.85) zu viele Fehler durchlässt → auf 0.90 ziehen. Wenn Review-Queue zu lang → Threshold für `QA_REVIEW=0.7` neu kalibrieren. **Diese Datenrunde ist der eigentliche ML-Wert des Piloten** — nicht das System sehen, sondern es justieren.

---

**Fazit:** Das System verdient die Note 6.5, nicht 9, weil es zwar baut, aber nicht misst. Mit drei fokussierten Maßnahmen in Woche 1–2 des Pilots wird daraus eine 8 — und damit eine Aussage, die ein Data Scientist vor einem ehrlichen Auditor verteidigen kann.
