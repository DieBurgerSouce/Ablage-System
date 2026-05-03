# 00k - ML/Data Pilot-Reality-Check

**Datum**: 2026-05-03
**Scope**: Realisierungsgrad PlanRAGAblage.md (109 KB) + PlanVektorPipeline.md gegen Code-Stand
**Branch**: feature/ocr-performance

---

## 1. OCR-Backends (REAL)

In `app/agents/ocr/` existieren **15 Backend-Implementierungen** (`__init__.py` orchestriert mit conditional imports):

| Backend | Datei | Beschreibung |
|---|---|---|
| DeepSeek-Janus-Pro | `deepseek_agent.py` | GPU-VLM, Best Umlaut-Acc, Fraktur |
| GOT-OCR 2.0 | `got_ocr_agent.py` | GPU, schnell, Tabellen/Formeln |
| Surya + Docling | `surya_docling_agent.py` + `_enhanced_agent.py` | CPU, Layout-Analyse |
| Surya GPU | `surya_gpu_agent.py` | GPU-Variante |
| Hybrid | `hybrid_agent.py` | Multi-Engine-Fusion |
| Qwen2.5-VL-7B | `qwen_ocr_agent.py` | GPT-4o-Level, 14 GB VRAM |
| Chandra (Qwen3-VL) | `chandra_agent.py` | SOTA 9B VLM (Datalab) |
| OlmOCR-2 (Qwen2.5-VL) | `olmocr_agent.py` | Allen AI, 270k PDF-Trained |
| Donut | `donut_agent.py` | 100+ Sprachen, Kyrillisch |
| PaddleOCR PP-OCRv5 | `paddle_ocr_agent.py` | CPU, 106 Sprachen |
| docTR (Mindee) | `doctr_agent.py` | CPU, deutsches Modell |
| Docling Layout | `docling_layout_analyzer.py` | reine Layout-Analyse |
| PaddleOCR-VL (exp) | `paddle_ocr_vl_agent_experimental.py` | Experimentell |

Plus 5 Service-Wrapper in `app/services/ocr/` (semantic_validation, cross_backend_consistency, table/formula_extraction, document_dna, supplier/auto-template, industry_vocabulary, document_quality_score).

**Note**: 9/10. Backend-Vielfalt deutlich groesser als geplant.

---

## 2. OCR-Genauigkeit / Umlaute

- **Service**: `app/services/umlaut_validation_service.py`, `contextual_umlaut_restorer.py`, `german_phonetic_matcher.py`, `german_compound_splitter.py`, `german_text_postprocessor.py`, `german_spellchecker.py`. 60 Files referenzieren Umlaute.
- **Tests**: `tests/unit/services/test_umlaut_validation_service.py` (NEU, untracked!) und `test_contextual_umlaut.py`. **4158 Umlaut/UTF-8 Vorkommen** in `tests/`.
- **Loss-Function**: `app/ml/finetuning/umlaut_weighted_loss.py` (für Surya/DeepSeek-Finetuning).

**Note**: 9/10. CRITICAL Rule #2 erfuellt.

---

## 3. Self-Learning Loop

- Service: `app/services/ocr/self_learning_service.py` (existiert).
- Aufruf: `app/workers/tasks/ocr_tasks.py:1802, 1865` (`get_self_learning_service`). **Keine Beat-Schedule fuer `self_learning_task`/`self_learning_pipeline`** gefunden — Loop ist event-getriggert, nicht zeitgesteuert.

**Note**: 6/10. Service existiert, aber autonomer Loop ist NICHT auf Cron — laeuft nur, wenn OCR-Task Self-Learning explizit aufruft.

---

## 4. Confidence-Calibration & Thresholds

- **Service**: `app/services/confidence_calibration.py` (Isotonic, Platt, Temperature, Histogram), plus `app/ml/confidence_calibration.py` und `app/services/ocr/confidence_service.py` (Wort-Level).
- **Thresholds** (`app/core/thresholds.py`): `OCR_CONFIDENCE_AUTO_ACCEPT=0.85`, `OCR_CONFIDENCE_AUTO_REJECT=0.4`, `QA_REVIEW_THRESHOLD=0.7`. ENV-driven, sauber gekapselt.
- **Autonomy-Level** (`app/services/autonomy/autonomy_level.py`): 4 Stufen mit Confidence-Schwellen 0.70/0.85/0.95/1.01.

**Note**: 9/10. Production-grade Konfiguration.

---

## 5. RAG-Status (KRITISCH)

**REAL und tief implementiert:**

- **Migrationen**: `alembic/versions/033_add_rag_tables.py` (rag_document_chunks, rag_customer_cards, rag_chat_sessions, rag_chat_messages), `036_fix_embedding_dimensions.py`, `043_add_vector_ab_testing.py`, `044_nullable_chunk_embedding.py`, `051_add_attached_document_to_chat_messages.py`, `052_add_chat_session_sharing.py`, `212_chat_tool_actions.py`. Insgesamt 229 Migrations.
- **Services** (`app/services/rag/`): `chunking_service`, `llm_service` (Ollama Qwen3-8B/14B), `search_service`, `customer_card_service`, `qdrant_service` (107 qdrant-Refs!), `vector_sync_service`, `ab_testing_router`, `chat_service`, `ai_action_service`, `action_dispatcher`, `excel_generator`, `word_generator`, `prompt_templates`, `tool_registry`, `metrics`.
- **API-Endpoints** (`app/api/v1/rag/`): `chat.py`, `chat_rest.py`, `chat_ws.py` (WebSocket!), `chunks.py`, `customers.py`, `jobs.py`, `router.py`, `search.py`. Plus Top-Level `app/api/v1/rag.py` und `schemas/rag.py`.
- **Vector-Backend**: **Qdrant statt pgvector** ist der aktive Pfad (`vector_sync_service` migriert pgvector → Qdrant; `ab_testing_router` toggelt zwischen `VectorBackend.QDRANT` und `VectorBackend.PGVECTOR`). Beides parallel verfuegbar.

**Note**: 9/10. Plan ist zu ~85% realisiert.

---

## 6. Embeddings

- **Modell**: `intfloat/multilingual-e5-large` (1024-dim, `app/core/config.py:390, 529`, `app/db/models.py:211`). Plus optional Jina-Embedding (`JINA_EMBEDDING_MODEL`, `app/core/config.py:491`).
- **Services**: `app/services/embedding_service.py` (832 LOC), `app/services/vector/embedding_factory.py`.
- **Worker**: `app/workers/tasks/embedding_tasks.py` (GPU-accelerated).

**Note**: 10/10. Plan-konform.

---

## 7. A/B-Testing

- **Files**: 82 Experimente in `data/ab_tests/` (Format `exp_deepseek_vs_got_<timestamp>.json`, von 2025-11-27 bis 2026-01-18). LIVE-Daten!
- **Code**: `app/ml/ab_testing.py` (via `app/services/backend_manager.py:146`), `app/services/rag/ab_testing_router.py`, `app/services/embedding_service.py:832` (`VECTOR_AB_TESTING_ENABLED`), `app/services/ai/smart_dunning_service.py:87` (Prometheus AB_TEST_CONVERSION).

**Note**: 9/10. Aktive Experimente.

---

## 8. Drift-Detection

- **Service**: `app/ml/drift_detector.py` (`DriftDetector`, `DriftReport`, `DriftSeverity` ab Zeile 129).
- **Beat-Schedule**: `app/workers/celery_app.py:722` (`run_drift_detection`, queue=metrics, priority=2).
- **Reports**: `data/drift_reports/` ist **LEER**.

**Note**: 6/10. Code production-ready, aber noch keine erzeugten Reports.

---

## 9. Trainings-Daten

- `Trainings_Data/` enthaelt **10 UP*-Subdirs** (UP000000–UP000024) plus `_validation_system/` (mit `inventory_scanner.py`, `migration_export.csv`, `training_data.db`, `validation_ui.py`).
- `UP000000/` allein hat **1024 Files** (PDFs/TIFs).
- **Annotation-Files (JSON) fehlen** in den UP*-Verzeichnissen (Glob `Trainings_Data/UP*/*.json` → 0 Treffer).
- `data/training/training_samples.json` (121.501 Zeilen) liefert Trainings-Samples.

**Note**: 5/10. Rohdaten massiv vorhanden, strukturierte Annotations fehlen weitgehend.

---

## 10. Qwen3-Integration

- **7 Code-Stellen** referenzieren Qwen3-8B/14B:
  - `app/services/rag/llm_service.py` (Realtime-Telefonsupport)
  - `app/services/llm_ocr_review_service.py` (LLM Post-OCR-Review)
  - `app/services/ai/nlq/sql_generator.py` (`DEFAULT_MODEL = "qwen3:8b"`)
  - `app/workers/tasks/training_tasks.py:2041` (Sample-Verifikation)
- **Qwen2.5-VL-7B** als OCR-Backend bereits aktiv (`qwen_ocr_agent.py`, MODEL_NAME = `Qwen/Qwen2.5-VL-7B-Instruct`). Chandra (Qwen3-VL) und OlmOCR (Qwen2.5-VL) ebenfalls.

**Note**: 8/10. Plan vollstaendig im Code verankert.

---

## 11. Ground-Truth-Pipeline

- **Service**: `app/services/auto_ground_truth_service.py` (`AutoGroundTruthService`, Singleton).
- **Hooks**: `app/workers/tasks/ocr_tasks.py:655–684` (`auto_ground_truth_created/skipped/failed`-Events), Beat-Task `process_auto_ground_truth_batch` (`training_tasks.py:1720`).
- **Verification-Queue**: `verification_queue_service.py:586` ruft GT-Service auf.

**Note**: 8/10. Pipeline ist vollstaendig verdrahtet.

---

## 12. GPU-Resource-Management

- `app/gpu_manager.py` (zentral, Backend-VRAM-Map), `app/core/gpu_recovery.py`, `app/services/gpu_metrics_service.py`.
- 8 Files nutzen `gpu_memory_guard()`/`GPUBatchProcessor`.

**Note**: 9/10. CRITICAL Rule #3 erfuellt.

---

## 13. Translation-Pipeline (PlanVektorPipeline.md)

- `app/services/translation_service.py`: Provider Argos/LibreTranslate/DeepL/Disabled.
- **MarianMT/opus-mt/nllb**: 0 Treffer in `app/`. Plan-Variante NICHT realisiert; ARGOS ist die produktive Loesung.

**Note**: 6/10. Funktional vorhanden, aber andere Architektur als geplant.

---

## 14. Structured-Extraction (PlanVektorPipeline.md)

- `app/services/structured_extraction_service.py`: Klassifizierung + Invoice/Order/Contract-Extraktion.
- Aufruf `app/main.py:2105` (`structured_extraction_completed/failed`-Events), Beat-Task `reprocess_all_documents_structured_extraction` (`celery_app.py:2545`).
- Qwen2.5-VL fuer Extraktion: ueber Chandra/OlmOCR/Qwen-OCR-Agents indirekt.

**Note**: 8/10. End-to-End verdrahtet.

---

## Plan-Feature-Matrix

| Plan-Feature | Status | Beleg |
|---|---|---|
| RAG-Tabellen (chunks/cards/sessions) | DONE | `alembic/versions/033_add_rag_tables.py` |
| Qdrant-Integration | DONE | `app/services/rag/qdrant_service.py` (107 Refs) |
| pgvector-Fallback + AB-Testing | DONE | `app/services/rag/ab_testing_router.py:5`, mig 043 |
| Qwen3-8B/14B (Ollama) | DONE | `app/services/rag/llm_service.py:4,498` |
| Customer Cards | DONE | `app/services/rag/customer_card_service.py:53` |
| Chat-WebSocket | DONE | `app/api/v1/rag/chat_ws.py` |
| Chunking-Service | DONE | `app/services/rag/chunking_service.py` |
| Embeddings (e5-large 1024-dim) | DONE | `app/core/config.py:390`, `models.py:211` |
| Excel/Word-Reportgenerierung | DONE | `excel_generator.py`, `word_generator.py` |
| Tool-Registry / Action-Dispatcher | DONE | `tool_registry.py`, `action_dispatcher.py` |
| Drift-Detection (Reports) | IN_PROGRESS | Code DONE, `data/drift_reports/` LEER |
| Self-Learning Loop (Cron) | IN_PROGRESS | Service DONE, kein Beat-Schedule |
| Auto-Ground-Truth | DONE | `auto_ground_truth_service.py`, mig + tasks |
| Confidence-Calibration | DONE | `app/services/confidence_calibration.py` |
| MarianMT/opus-mt Translation | PLANNED | nicht implementiert (Argos statt) |
| Annotated Training-Datasets | PLANNED | UP*-Dirs ohne JSON-Annotations |
| Multi-Backend OCR (>= 8) | DONE | 13+ Backends in `app/agents/ocr/` |
| Cross-Backend-Consistency | DONE | `app/services/ocr/cross_backend_consistency_service.py` |
| Umlaut-Validation | DONE | Service + Tests + Loss-Function |
| Structured Extraction | DONE | `structured_extraction_service.py` |
| Threshold-System (Auto/Review) | DONE | `app/core/thresholds.py:103,108,323` |
| AB-Test-Daten | DONE | 82 JSON-Files in `data/ab_tests/` |

---

## Top-3 Staerken

1. **OCR-Backend-Pluralitaet**: 13+ Agents mit conditional imports, GPU/CPU-Fallback, VRAM-Map. Weit ueber Plan-Anforderung.
2. **RAG-Stack tief integriert**: 16 RAG-Services + 9 API-Endpoints + 7 Migrations + WebSocket-Chat + Qdrant-Sync. Plan-Versprechen ~85% eingeloest.
3. **Self-Learning + Auto-GT-Pipeline**: Inkl. Confidence-Calibration, Drift-Detector, AB-Test-Routing — Production-grade ML-Ops.

## Top-5 Luecken

1. **Annotierte Trainings-Datasets fehlen**: 10× UP*-Dirs mit ~10k Roh-PDFs, aber 0 strukturierte JSON-Annotations. → `auto_ground_truth_service` muss massiv durchlaufen.
2. **Drift-Reports werden nicht erzeugt**: `data/drift_reports/` LEER, obwohl Beat-Task & DriftDetector existieren. Beat scheint nicht zu laufen oder Schwellen nie erreicht.
3. **Self-Learning-Loop nicht zeitgesteuert**: kein Beat-Schedule fuer `self_learning_pipeline` — nur reactive Aufrufe in `ocr_tasks.py`. Plan-Promise "kontinuierliches Lernen" nur halb wahr.
4. **Translation-Plan veraltet**: PlanVektorPipeline.md fordert MarianMT/opus-mt/nllb. Code hat Argos/LibreTranslate/DeepL. Plan-Doku abgleichen.
5. **Untracked Test-Files**: `test_embedding_service.py`, `test_spotlight_service.py`, `test_umlaut_validation_service.py` etc. existieren als untracked — Coverage-Status unklar bis committed/run.

---

## Pilot-Reality-Check Note

| Bereich | Note |
|---|---|
| OCR-Backends | 9/10 |
| OCR-Genauigkeit | 9/10 |
| Self-Learning | 6/10 |
| Confidence-Cal | 9/10 |
| RAG-Stack | 9/10 |
| Embeddings | 10/10 |
| A/B-Testing | 9/10 |
| Drift-Detection | 6/10 |
| Trainings-Daten | 5/10 |
| Qwen3-Integration | 8/10 |
| Ground-Truth | 8/10 |
| GPU-Mgmt | 9/10 |
| Translation | 6/10 |
| Structured Extraction | 8/10 |

**Gesamtnote ML/Data Pilot-Readiness: 8/10**

## Wie weit sind wir vom RAG-Versprechen?

**Sehr nah — geschaetzt 80–85% Plan-Realisierung.** Code-seitig sind alle Kern-Bausteine vorhanden: Migrations (033, 043, 044, 051, 052, 212), Services (Qdrant + pgvector dual, Chunking, LLM, Search, Customer Cards, Chat, AB-Test, Vector-Sync), Endpoints (REST + WebSocket + Tool-Actions), Embedding-Pipeline (e5-large + GPU-Worker), Reportgeneratoren (Excel/Word), Metrics (Prometheus integriert).

**Was zum 100%-Versprechen fehlt:**
- Annotated Trainings-Daten (Hauptluecke fuer LLM-Finetuning auf domain-specific Daten)
- Aktiver Cron-getriggerter Self-Learning-Loop
- Erzeugte Drift-Reports (Operational-Monitoring-Beleg)
- Konsolidierung Translation-Pipeline gegen Plan
- Untracked Test-Files committen + CI-Run als Coverage-Beleg

Pilot-Tauglichkeit: **JA**, mit Caveat dass Self-Learning + Drift-Reports operational nachgezogen werden muessen.
