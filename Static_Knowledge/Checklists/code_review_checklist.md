# Code Review Checklist - Ablage-System
**Version:** 1.0
**Status:** Active
**Letzte Aktualisierung:** 2025-11-23
**Verwendung:** Für alle Pull Requests

**Tags:** #code_review #checklist #quality #developer #qa #testing #security #high #static_knowledge

---

## Überblick

Diese Checklist wird für **ALLE Pull Requests** verwendet. Reviewers müssen alle zutreffenden Punkte abhaken vor Approval.

### Review-Prozess

```
1. Author erstellt PR
2. CI/CD läuft (Tests, Linting)
3. 2 Reviewers assigned
4. Reviewers nutzen diese Checklist
5. Feedback → Author fixes
6. Re-review
7. Approval (beide Reviewers ✅)
8. Merge (Squash & Merge)
```

---

## 📋 General Code Quality

### Code Style & Standards

- [ ] **Linting:** `ruff check .` passes ohne Fehler
- [ ] **Formatting:** `ruff format .` angewendet
- [ ] **Type Hints:** Alle Funktionen haben Type Annotations
  ```python
  # ✅ Good
  async def process(doc_id: str) -> Dict[str, Any]:

  # ❌ Bad
  async def process(doc_id):
  ```
- [ ] **Type Checking:** `mypy app/` passes (strict mode)
- [ ] **Naming Conventions:**
  - snake_case für Funktionen/Variablen
  - PascalCase für Klassen
  - UPPER_SNAKE_CASE für Konstanten
- [ ] **Line Length:** <100 Zeichen (Ruff-configured)
- [ ] **Imports:** Sortiert und gruppiert (stdlib → third-party → local)
  ```python
  # ✅ Good
  import asyncio
  import os

  from fastapi import FastAPI
  import torch

  from app.services import ocr_service
  ```

### Code Complexity

- [ ] **Function Length:** Funktionen <50 Zeilen (Ausnahmen begründet)
- [ ] **Cyclomatic Complexity:** <10 (keine verschachtelten if/for Schleifen >3 Ebenen)
- [ ] **DRY Principle:** Kein duplizierter Code
- [ ] **Single Responsibility:** Jede Funktion macht genau eine Sache

### Documentation

- [ ] **Docstrings:** Alle öffentlichen Funktionen/Klassen dokumentiert
  ```python
  async def process_document(document_id: str, backend: str = "auto") -> OCRResult:
      """
      Process document with OCR.

      Args:
          document_id: UUID of document to process
          backend: OCR backend to use ('auto', 'deepseek', 'got_ocr', 'surya')

      Returns:
          OCRResult with extracted text and metadata

      Raises:
          DocumentNotFoundError: If document doesn't exist
          OCRProcessingError: If OCR fails
          GPUOutOfMemoryError: If GPU VRAM exhausted
      """
  ```
- [ ] **Comments:** Komplexe Logik erklärt (WARUM, nicht WAS)
- [ ] **CLAUDE.md:** Update falls Architecture/APIs geändert
- [ ] **Changelog:** Wichtige Änderungen dokumentiert

---

## ✅ Testing

### Test Coverage

- [ ] **Coverage:** Neue Code-Zeilen >80% abgedeckt
- [ ] **Unit Tests:** Alle neuen Funktionen haben Unit Tests
- [ ] **Integration Tests:** Neue Features haben Integration Tests
- [ ] **E2E Tests:** Kritische User-Flows getestet (falls anwendbar)

### Test Quality

- [ ] **Test Names:** Beschreibend und klar
  ```python
  # ✅ Good
  async def test_deepseek_processes_german_umlauts_correctly():

  # ❌ Bad
  async def test_ocr():
  ```
- [ ] **Assertions:** Klare, spezifische Assertions
  ```python
  # ✅ Good
  assert result['text'] == "Müller GmbH"
  assert result['umlaut_accuracy'] >= 95.0

  # ❌ Bad
  assert result
  ```
- [ ] **Test Data:** Fixtures verwendet statt hardcoded data
- [ ] **Mocking:** Dependencies gemockt wo sinnvoll
- [ ] **Test Isolation:** Tests beeinflussen sich nicht gegenseitig

### Special Cases

- [ ] **Error Paths:** Fehlerszenarien getestet
- [ ] **Edge Cases:** Grenzfälle berücksichtigt (leere Eingabe, None, etc.)
- [ ] **Performance:** Langsame Tests (<1s) dokumentiert

---

## 🔐 Security

### Authentication & Authorization

- [ ] **Auth Required:** Geschützte Endpoints haben `Depends(get_current_user)`
- [ ] **RBAC:** Berechtigungsprüfung implementiert
  ```python
  if document.user_id != current_user.id and not current_user.is_admin:
      raise HTTPException(403, "Access denied")
  ```
- [ ] **Password Security:** NIEMALS Passwörter in Klartext (bcrypt verwendet)

### Input Validation

- [ ] **Pydantic Models:** Alle Inputs validiert
  ```python
  class DocumentCreate(BaseModel):
      filename: str = Field(..., max_length=255)
      language: str = Field(default="de", regex="^(de|en)$")
  ```
- [ ] **Path Traversal:** Filename-Validierung (keine `..`, `/`, `\`)
- [ ] **SQL Injection:** Keine String-Konkatenation in Queries (ORM verwendet)
- [ ] **XSS Prevention:** User-Input escaped (FastAPI macht das automatisch)

### Sensitive Data

- [ ] **Secrets:** KEINE Secrets im Code (Env-Variables verwendet)
- [ ] **Logging:** KEINE sensitive Daten geloggt (Passwörter, API Keys, PII)
- [ ] **Error Messages:** KEINE Details über interne Struktur preisgegeben

### GDPR Compliance

- [ ] **User Data:** Löschung implementiert (GDPR Artikel 17)
- [ ] **Data Export:** Export-Funktionalität (GDPR Artikel 20)
- [ ] **Audit Logging:** Datenzugriff geloggt

---

## ⚡ Performance

### Database Queries

- [ ] **N+1 Problem:** Keine N+1 Queries (selectinload/joinedload verwendet)
  ```python
  # ✅ Good
  result = await db.execute(
      select(Document).options(selectinload(Document.ocr_results))
  )

  # ❌ Bad (N+1)
  documents = await db.execute(select(Document))
  for doc in documents:
      ocr_results = await db.execute(select(OCRResult).where(OCRResult.document_id == doc.id))
  ```
- [ ] **Indexes:** Queries auf indizierten Spalten
- [ ] **Pagination:** Große Resultsets paginiert
- [ ] **Connection Pool:** AsyncSession korrekt verwendet

### Caching

- [ ] **Cache Strategy:** Sinnvolle TTLs gesetzt
- [ ] **Cache Invalidation:** Cache wird bei Updates invalidiert
- [ ] **Cache Keys:** Eindeutige, beschreibende Keys

### Async/Await

- [ ] **Async Everywhere:** I/O-bound code ist async
- [ ] **No Blocking:** Keine blocking calls in async functions
  ```python
  # ❌ Bad
  async def bad():
      result = requests.get(url)  # BLOCKING!

  # ✅ Good
  async def good():
      async with httpx.AsyncClient() as client:
          result = await client.get(url)
  ```
- [ ] **await:** Alle async calls haben `await`
- [ ] **Concurrent:** `asyncio.gather` für parallele Operationen

---

## 🎮 GPU-Spezifisch (falls zutreffend)

### GPU Resource Management

- [ ] **Memory Guard:** gpu_memory_guard verwendet
  ```python
  with gpu_memory_guard(threshold_gb=13.6):
      result = model.process(image)
  ```
- [ ] **VRAM Check:** Tests validieren <85% VRAM (13.6GB / 16GB)
- [ ] **GPU Lock:** Multi-Process Konflikte verhindert
- [ ] **Cache Clearing:** `torch.cuda.empty_cache()` nach Processing
- [ ] **Error Handling:** OOM-Errors caught und handled

### GPU Optimization

- [ ] **Batch Processing:** Batch size dynamisch angepasst
- [ ] **FP16:** Mixed Precision verwendet (falls möglich)
- [ ] **Model Compilation:** `torch.compile` aktiviert (PyTorch 2.0+)

---

## 🇩🇪 German Language Requirements

### Text Processing

- [ ] **Umlaut Support:** ä, ö, ü, ß korrekt verarbeitet
- [ ] **Validation:** GermanValidator für OCR-Output
- [ ] **Normalization:** Unicode NFC normalization
- [ ] **Spell Check:** Deutsche Rechtschreibprüfung

### User-Facing Content

- [ ] **Error Messages:** Alle auf Deutsch
  ```python
  # ✅ Good
  raise HTTPException(404, "Dokument nicht gefunden")

  # ❌ Bad
  raise HTTPException(404, "Document not found")
  ```
- [ ] **API Responses:** Deutsche Feldnamen (wo sinnvoll)
- [ ] **Logs:** Deutsche Meldungen für User-sichtbare Logs

### Testing

- [ ] **German Test Data:** Tests verwenden deutsche Samples
- [ ] **Umlaut Accuracy:** Tests für Umlaut-Genauigkeit (>95%)

---

## 🔄 Error Handling

### Exception Handling

- [ ] **Specific Exceptions:** Spezifische Exceptions statt `Exception`
  ```python
  # ✅ Good
  except DocumentNotFoundError:

  # ❌ Bad
  except Exception:
  ```
- [ ] **Error Context:** Exceptions mit Context (f-strings)
  ```python
  raise OCRProcessingError(f"Failed to process document {doc_id}: {error}")
  ```
- [ ] **Re-raise:** Exceptions richtig re-raised (`raise ... from e`)
- [ ] **Cleanup:** finally-Block für Resource cleanup

### Logging

- [ ] **Structured Logging:** structlog verwendet
- [ ] **Log Levels:** Korrekte Levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- [ ] **Context:** Log-Meldungen mit Kontext (doc_id, user_id, etc.)
  ```python
  logger.info("document_processed", document_id=doc_id, backend=backend, duration=elapsed)
  ```

---

## 📊 Monitoring & Observability

### Metrics

- [ ] **Prometheus Metrics:** Neue Features exportieren Metriken
- [ ] **Counter/Gauge/Histogram:** Korrekte Metric-Typen
- [ ] **Labels:** Sinnvolle Labels (backend, status, etc.)

### Logging

- [ ] **Important Events:** Wichtige Ereignisse geloggt
- [ ] **Error Logging:** Alle Errors geloggt (exc_info=True)
- [ ] **Performance:** Slow-Query-Logging

---

## 🐳 Infrastructure (falls zutreffend)

### Docker

- [ ] **Dockerfile:** Optimiert (multi-stage build, layer caching)
- [ ] **docker-compose.yml:** Korrekte Service-Dependencies
- [ ] **Environment Variables:** Alle Secrets als ENV vars
- [ ] **Health Checks:** Container health checks definiert

### Deployment

- [ ] **Migrations:** Database migrations getestet
- [ ] **Rollback:** Rollback-Strategie dokumentiert
- [ ] **Zero-Downtime:** Deployment ohne Downtime möglich

---

## 📝 Pull Request Quality

### PR Description

- [ ] **Title:** Klarer, beschreibender Titel
- [ ] **Description:** Was, Warum, Wie erklärt
- [ ] **Related Issues:** GitHub Issues verlinkt
- [ ] **Screenshots:** UI-Änderungen haben Screenshots
- [ ] **Breaking Changes:** Breaking Changes dokumentiert

### Commits

- [ ] **Commit Messages:** Conventional Commits Format
  ```
  feat(ocr): add DeepSeek backend support
  fix(api): prevent race condition in upload
  docs(readme): update deployment instructions
  ```
- [ ] **Atomic Commits:** Jeder Commit ist logisch zusammenhängend
- [ ] **Commit Size:** Nicht zu groß (max ~300 LOC)

---

## 🎯 Domain-Specific Checks

### OCR-Features

- [ ] **Backend Selection:** Logik getestet (DeepSeek vs GOT-OCR vs Surya)
- [ ] **Preprocessing:** Image preprocessing korrekt
- [ ] **Postprocessing:** German validation integriert
- [ ] **Quality Metrics:** Accuracy, Processing Time gemessen

### Agent-Features

- [ ] **Base Agent:** Erbt korrekt von BaseAgent
- [ ] **Lifecycle:** startup/cleanup implementiert
- [ ] **State Management:** Agent-State persistiert
- [ ] **Metrics:** Agent-Metrics exportiert

---

## ✅ Final Review Checklist

Vor Approval müssen folgende Punkte erfüllt sein:

### CI/CD

- [ ] ✅ All GitHub Actions pass
- [ ] ✅ Tests: >80% coverage
- [ ] ✅ Linting: Ruff clean
- [ ] ✅ Type Check: mypy clean
- [ ] ✅ Security Scan: No critical issues

### Code Quality

- [ ] ✅ Alle zutreffenden Checkboxen ✅
- [ ] ✅ Kein TODO/FIXME Code (oder Issue erstellt)
- [ ] ✅ Keine Debug-Statements (print, debugger)
- [ ] ✅ Keine hardcoded Secrets/URLs

### Documentation

- [ ] ✅ Docstrings vorhanden
- [ ] ✅ README updated (falls nötig)
- [ ] ✅ CLAUDE.md updated (falls nötig)

### Testing

- [ ] ✅ Tests lokal laufen
- [ ] ✅ Tests relevant und sinnvoll
- [ ] ✅ Keine flaky tests

### Final Thoughts

- [ ] **Code Readability:** Ist der Code verständlich?
- [ ] **Maintainability:** Kann der Code einfach gewartet werden?
- [ ] **Edge Cases:** Sind alle Edge Cases berücksichtigt?
- [ ] **Future-Proof:** Ist der Code erweiterbar?

---

## 🚫 Automatic Rejection Criteria

PR wird **AUTOMATISCH REJECTED** bei:

1. ❌ CI/CD failures (Tests, Linting, Type Check)
2. ❌ Security vulnerabilities (Critical/High)
3. ❌ Test Coverage <60% (für neue Code-Zeilen)
4. ❌ Secrets im Code
5. ❌ Breaking Changes ohne Migration-Plan
6. ❌ Keine Tests für neue Features
7. ❌ Fehlende Docstrings für öffentliche APIs

---

## 📚 Review Templates

### Approval Template

```markdown
## ✅ LGTM (Looks Good To Me)

**Reviewed:** All items in checklist ✅
**Tests:** Pass with 87% coverage
**Code Quality:** Excellent, well-structured
**Documentation:** Complete

**Comments:**
- Great use of async/await patterns
- Good test coverage for edge cases
- Minor suggestion: Consider caching in line 42 (non-blocking)

**Approval:** ✅ Approved

**Next Steps:** Ready to merge
```

### Request Changes Template

```markdown
## 🔄 Changes Requested

**Reviewed:** Checklist items reviewed

**Blocking Issues:**
1. Security: [ ] Secrets exposed in line 123 (CRITICAL)
2. Tests: [ ] Missing tests for error paths
3. Performance: [ ] N+1 query in line 67

**Non-Blocking Suggestions:**
- Consider refactoring function X for better readability
- Add logging for debugging in production

**Next Steps:**
Please address blocking issues, then request re-review.
```

---

## 🎓 Review Best Practices

### For Reviewers

1. **Be Constructive:** Feedback soll helfen, nicht kritisieren
2. **Explain Why:** Begründe Änderungswünsche
3. **Suggest Solutions:** Biete Lösungsvorschläge an
4. **Prioritize:** Unterscheide blocking vs non-blocking
5. **Timely:** Review binnen 24h (working days)

### For Authors

1. **Self-Review:** Nutze Checklist VOR PR-Erstellung
2. **Small PRs:** <500 LOC ideal, max 1000 LOC
3. **Context:** Gib genug Kontext in PR-Description
4. **Respond:** Beantworte Review-Comments konstruktiv
5. **Test Locally:** Alle Tests lokal vor Push

---

## 📖 Verwandte Dokumentation

- **[async_patterns.md](../Patterns/async_patterns.md)** - Async/Await Best Practices
- **[agent_implementation_patterns.md](../Architecture/agent_implementation_patterns.md)** - Agent Patterns
- **[agent_testing_guide.md](../Architecture/agent_testing_guide.md)** - Testing Strategies

---

## Changelog

| Version | Datum | Änderungen | Autor |
|---------|-------|-----------|-------|
| 1.0 | 2025-11-23 | Initial checklist | Development Team |

---

**Maintainer:** Development Team
**Review:** Quarterly
**Feedback:** PRs welcome für Checklist-Verbesserungen
