# Orchestration MCP Server - Vollautomatisches Multi-Model Routing

**Status**: ✅ Production-Ready
**Version**: 1.0.0
**Zweck**: Vollautomatisches Routing zwischen Claude Haiku, Sonnet, und Opus + 4 spezialisierte Domain-Expert Agenten

---

## 📋 Übersicht

Der Orchestration MCP Server ermöglicht **vollautomatisches** Multi-Model Routing in Claude Code ohne manuelle Intervention. Tasks werden automatisch an den optimalen Agent (Haiku/Sonnet/Opus oder Spezialist) weitergeleitet basierend auf Komplexität und Domäne.

### Kernfunktionen

✅ **Vollautomatisches Routing**: Keine manuelle Modell-Auswahl erforderlich
✅ **4 Spezialisierte Agenten**: Refactoring, OCR, Testing, Database Experten
✅ **Token Savings**: 40-60% Einsparungen vs Opus-only
✅ **Quality Gates**: Automatische Validierung mit Escalation Chain
✅ **Decision Caching**: Opus-Entscheidungen für Sonnet/Haiku wiederverwendbar
✅ **Metrics Tracking**: Performance-Monitoring & Analytics

---

## 🏗️ Architektur

```
User Task in Claude Code
       ↓
MCP Server (automatisch)
       ↓
   ┌─────────────────────────────────────┐
   │  1. Specialized Agent Detection?    │
   │     - Refactoring Expert            │
   │     - OCR Specialist                │
   │     - Testing Expert                │
   │     - Database Expert               │
   └─────────────────────────────────────┘
       ↓ (if no specialty match)
   ┌─────────────────────────────────────┐
   │  2. Tier-Based Classification       │
   │     - Haiku: Simple tasks           │
   │     - Sonnet: Moderate complexity   │
   │     - Opus: Complex/Architectural   │
   └─────────────────────────────────────┘
       ↓
   ┌─────────────────────────────────────┐
   │  3. Prompt Enhancement              │
   │     - Cached Opus decisions         │
   │     - Tier-specific guidance        │
   │     - Specialty context             │
   └─────────────────────────────────────┘
       ↓
   ┌─────────────────────────────────────┐
   │  4. Task() Call to Claude Code      │
   │     - Agent name                    │
   │     - Model override (haiku/sonnet) │
   │     - Enhanced prompt               │
   └─────────────────────────────────────┘
       ↓
   ┌─────────────────────────────────────┐
   │  5. Quality Validation              │
   │     - 6 quality checks              │
   │     - Escalation if needed          │
   │     - Cache Opus decisions          │
   └─────────────────────────────────────┘
```

---

## 🚀 Installation

### Voraussetzungen

- **Python**: 3.11+
- **Claude Code**: Latest version
- **Windows**: PowerShell 5.1+ (für Auto-Start)

### Schritt 1: Automatische Installation (Empfohlen)

```powershell
# Im .claude/mcp-server/ Verzeichnis:
.\install.ps1
```

Dies richtet ein:
- Windows Scheduled Task für Auto-Start beim Boot
- Automatischer Start bei User-Login
- Restart bei Failures (3 Versuche)

### Schritt 2: .clauderc Konfiguration

Füge folgendes zu `C:\Users\benfi\.clauderc` hinzu:

```json
{
  "mcp_servers": {
    "orchestration": {
      "command": "python",
      "args": ["C:\\Users\\benfi\\Ablage_System\\.claude\\mcp-server\\orchestration_server.py"],
      "enabled": true,
      "auto_start": true
    }
  },
  "orchestration": {
    "enabled": true,
    "cache_enabled": true,
    "auto_routing": true,
    "specialized_agents_enabled": true
  }
}
```

### Schritt 3: Claude Code Neustarten

```bash
# Claude Code beenden und neu starten
# MCP Server wird automatisch erkannt
```

### Schritt 4: Verifizierung

```powershell
# Check ob MCP Server läuft
Get-Process | Where-Object {$_.CommandLine -like "*orchestration_server*"}

# Oder manuell testen
.\test.ps1
```

---

## 📝 Manuelle Installation

Falls Auto-Start nicht gewünscht:

```powershell
# Server manuell starten
.\start.ps1

# Server stoppen
.\stop.ps1

# Server testen (CLI-Modus)
.\test.ps1
```

---

## 🎯 Verwendung

### Automatisches Routing (Transparent)

```python
# User schreibt einfach Task in Claude Code:
"Fix typo in README"
# → Automatisch zu Haiku geroutet

"Implement user login endpoint"
# → Automatisch zu Sonnet geroutet

"Design microservices architecture"
# → Automatisch zu Opus geroutet
```

### Spezialisierte Agenten (Automatisch)

```python
# Refactoring Expert (5+ Dateien)
"Refactoriere Authentication zu JWT"
# → Automatisch zu Refactoring Expert (Opus)

# OCR Specialist (GPU/OCR Keywords)
"Optimiere DeepSeek GPU Batch Processing"
# → Automatisch zu OCR Specialist (Opus)

# Testing Expert (Tests/* oder Testing Keywords)
"Erstelle Unit Tests mit 80% Coverage"
# → Automatisch zu Testing Expert (Sonnet)

# Database Expert (DB Keywords oder Models)
"Erstelle SQLAlchemy Models für Documents"
# → Automatisch zu Database Expert (Sonnet)
```

---

## 🔧 Konfiguration

### config.json

```json
{
  "server": {
    "name": "orchestration",
    "version": "1.0.0",
    "host": "localhost",
    "port": 3000
  },
  "orchestration": {
    "cache_enabled": true,
    "quality_gate_enabled": true,
    "auto_escalation": true,
    "specialized_agents_enabled": true
  },
  "specialized_patterns": {
    "refactoring": {
      "keywords": ["refactor", "migrate", "modernize"],
      "min_files": 5,
      "agent": "refactoring-expert",
      "tier": "opus"
    },
    // ... weitere Patterns
  },
  "thresholds": {
    "haiku_quality_min": 0.95,
    "sonnet_quality_min": 0.85,
    "opus_quality_min": 0.80,
    "cache_ttl_days": 7
  }
}
```

### Anpassungen

**Cache TTL ändern:**
```json
"thresholds": {
  "cache_ttl_days": 14  // 14 Tage statt 7
}
```

**Quality Gates deaktivieren:**
```json
"orchestration": {
  "quality_gate_enabled": false  // Nur Routing, kein Validation
}
```

**Spezialisierte Agenten deaktivieren:**
```json
"orchestration": {
  "specialized_agents_enabled": false  // Nur Tier-based Routing
}
```

---

## 📊 Monitoring & Debugging

### Logs

```powershell
# Server logs anzeigen (wenn als Service läuft)
Get-ScheduledTaskInfo -TaskName "OrchestrationMCPServer"

# Oder direkter Output (test mode)
python orchestration_server.py
```

### Metriken

```python
# Via Python API
from orchestration_server import OrchestrationMetrics

metrics = OrchestrationMetrics()
print(metrics.get_summary())

# Output:
# Total Tasks: 150
# Tier Distribution:
#   - Haiku: 45 (30%)
#   - Sonnet: 75 (50%)
#   - Opus: 30 (20%)
# Token Savings: 42.5%
# Average Quality: 0.92
# Escalation Rate: 8.2%
```

### Debugging

```powershell
# Test mode (CLI output)
.\test.ps1

# Manueller Start mit Debug-Output
python orchestration_server.py --debug
```

---

## 🧪 Testing

### E2E Integration Tests

```bash
# Alle Integration Tests
pytest tests/integration/test_mcp_server_e2e.py -v

# Spezifische Test-Kategorien
pytest tests/integration/ -k "test_specialized_agent" -v
```

### Performance Benchmarks

```bash
# Alle Benchmarks
pytest tests/benchmarks/test_performance.py -v

# Nur Routing Latency
pytest tests/benchmarks/ -k "test_routing_latency" -v

# Comprehensive Report
pytest tests/benchmarks/test_performance.py::test_comprehensive_benchmark_report -v
```

### Erwartete Ergebnisse

✅ **Routing Latency**: P95 < 100ms
✅ **Token Savings**: ≥ 40% vs Opus-only
✅ **Routing Accuracy**: ≥ 85%
✅ **Quality Score**: ≥ 0.90 average
✅ **Escalation Rate**: < 10%
✅ **Cache Hit Rate**: > 30%

---

## 🎨 Spezialisierte Agenten

### 1. Refactoring Expert (`refactoring-expert.md`)

**Einsatzgebiet:**
- Multi-file refactoring (5+ Dateien)
- Database migrations (Alembic)
- Architecture transitions (MVC → DDD, Monolith → Microservices)
- Legacy modernization (Python 2→3, sync→async)

**Trigger:**
- Keywords: `refactor`, `migrate`, `modernize`, `umstruktur`, `migration`
- Min. 5 Dateien betroffen

**Model:** Opus (immer)

**Beispiele:**
- "Migrate von sync zu async SQLAlchemy (15 Dateien)"
- "Refactoriere Auth-System von Session zu JWT"
- "Normalisiere Database Schema (1NF → 3NF)"

---

### 2. OCR Specialist (`ocr-specialist.md`)

**Einsatzgebiet:**
- OCR backend integration (DeepSeek, GOT-OCR, Surya)
- GPU memory optimization (VRAM < 85%)
- German text processing (Umlaute, Fraktur)
- Batch processing strategies

**Trigger:**
- Keywords: `ocr`, `deepseek`, `got-ocr`, `surya`, `gpu`, `vram`, `batch`, `fraktur`
- Files: `app/agents/ocr/*`, `app/services/ocr_service.py`

**Model:** Opus (immer)

**Beispiele:**
- "Optimiere DeepSeek GPU Batch Processing, VRAM unter 85%"
- "Implementiere Fraktur-Erkennung für historische Dokumente"
- "Debug GOT-OCR Memory Leak bei großen Batches"

---

### 3. Testing Expert (`testing-expert.md`)

**Einsatzgebiet:**
- Unit tests (pytest, AAA pattern, 80%+ coverage)
- Integration tests (E2E workflows)
- GPU-specific tests (@pytest.mark.gpu)
- Test fixtures (conftest.py, Factory Pattern)

**Trigger:**
- Keywords: `test`, `pytest`, `coverage`, `fixture`, `integration test`, `unit test`
- Files: `tests/*`

**Model:** Sonnet (default)

**Beispiele:**
- "Erstelle Unit Tests für OCR Pipeline (80%+ Coverage)"
- "Add GPU memory leak tests für DeepSeek"
- "Implementiere E2E Tests für Document Upload Workflow"

---

### 4. Database Expert (`database-expert.md`)

**Einsatzgebiet:**
- SQLAlchemy 2.0 models (async, type hints)
- Alembic migrations (bidirectional, rollback-safe)
- Database optimization (indexes, N+1 queries, EXPLAIN ANALYZE)
- pgvector integration (embeddings, similarity search)

**Trigger:**
- Keywords: `database`, `sqlalchemy`, `alembic`, `migration`, `postgres`, `pgvector`, `schema`
- Files: `app/db/models.py`, `alembic/versions/*`

**Model:** Sonnet (default)

**Beispiele:**
- "Erstelle SQLAlchemy Models für Document Management"
- "Optimiere User-Query (N+1 Problem)"
- "Implementiere pgvector für Embedding-Storage"
- "Schreibe Alembic Migration für email_verified column"

---

## 🔄 Escalation Chain

### Automatische Qualitäts-Validierung

Nach jeder Task-Ausführung:

```
1. Quality Gate prüft 6 Checks:
   ✅ Python Syntax gültig
   ✅ Type Hints vorhanden (keine Any types)
   ✅ Deutsche Fehlermeldungen
   ✅ GPU Resource Management (wenn OCR)
   ✅ Keine Secrets im Code
   ✅ Imports korrekt

2. Bei Failures:
   - Haiku → Eskalation zu Sonnet
   - Sonnet → Eskalation zu Opus
   - Opus → Fehler loggen (keine weitere Eskalation)

3. Bei Success (Opus):
   - Decision in Cache speichern (7 Tage TTL)
   - Für zukünftige Sonnet/Haiku Tasks verfügbar
```

---

## 💡 Best Practices

### 1. Cache Warm-Up

Für optimale Token-Einsparungen:

```python
# Opus Tasks zuerst ausführen für Architecture Decisions
"Design authentication system architecture"
# → Opus Decision wird gecached

# Dann Implementation mit Sonnet (nutzt Cache)
"Implement user login endpoint"
# → Sonnet bekommt Opus Decision als Context
```

### 2. File Patterns nutzen

Für zuverlässige Specialized Agent Detection:

```python
# ✅ GOOD: Explicit file patterns
"Add tests for OCR service"
files: ["tests/unit/services/test_ocr_service.py"]
# → Testing Agent detected via file pattern

# ❌ LESS RELIABLE: Nur Keywords
"Add tests for OCR service"
files: []
# → May or may not detect Testing Agent
```

### 3. Quality Gates aktiviert lassen

```json
// ✅ RECOMMENDED
"orchestration": {
  "quality_gate_enabled": true,
  "auto_escalation": true
}

// ❌ NICHT EMPFOHLEN (nur für Debugging)
"orchestration": {
  "quality_gate_enabled": false
}
```

---

## 🐛 Troubleshooting

### Problem: MCP Server startet nicht

```powershell
# 1. Check Python
python --version  # Sollte 3.11+ sein

# 2. Check Dependencies
pip install -r requirements.txt

# 3. Test manuell
python orchestration_server.py
```

### Problem: Claude Code erkennt MCP Server nicht

```powershell
# 1. Check .clauderc Syntax
cat C:\Users\benfi\.clauderc | python -m json.tool

# 2. Check Server läuft
Get-Process | Where-Object {$_.CommandLine -like "*orchestration_server*"}

# 3. Restart Claude Code
# Beenden und neu starten
```

### Problem: Routing funktioniert nicht wie erwartet

```powershell
# Debug-Modus aktivieren
python orchestration_server.py --debug

# Logs anzeigen
# Output zeigt Routing-Entscheidungen mit Reasoning
```

### Problem: Hohe Escalation Rate (>10%)

```json
// Quality Thresholds anpassen
"thresholds": {
  "haiku_quality_min": 0.90,  // Reduziert von 0.95
  "sonnet_quality_min": 0.80   // Reduziert von 0.85
}
```

---

## 📈 Performance Tuning

### Cache Size optimieren

```json
"thresholds": {
  "cache_ttl_days": 14,  // Länger cachen für mehr Reuse
  "cache_max_size": 1000  // Max Einträge
}
```

### Specialized Agent Priorities anpassen

```json
"specialized_patterns": {
  "refactoring": {
    "keywords": ["refactor", "migrate"],
    "min_files": 3  // Reduziert von 5 für frühere Detection
  }
}
```

---

## 🔒 Security Considerations

### Secrets Management

❌ **NEVER** in MCP Server Code:
- API Keys
- Passwords
- Tokens

✅ **IMMER** in Environment Variables:
```powershell
$env:ANTHROPIC_API_KEY = "sk-..."
```

### Input Validation

MCP Server validiert alle Inputs:
- Task prompts sanitized
- File paths validated (no path traversal)
- Config JSON schema-validated

---

## 📚 Referenzen

### Dokumentation

- **MCP Protocol**: https://modelcontextprotocol.io/
- **Claude Code**: https://claude.com/code
- **Orchestration System Plan**: `C:\Users\benfi\.claude\plans\fluttering-jumping-hopcroft.md`

### Code

- **Server Implementation**: `orchestration_server.py` (~600 lines)
- **Config**: `config.json`
- **Agent Definitions**: `.claude/agents/*.md`
- **Tests**: `tests/integration/test_mcp_server_e2e.py`, `tests/benchmarks/test_performance.py`

---

## 🎯 Roadmap

### Version 1.1 (geplant)

- [ ] Web UI für Metrics Dashboard
- [ ] A/B Testing für Routing-Strategien
- [ ] Machine Learning für adaptive Routing
- [ ] Support für Custom Specialized Agents

### Version 2.0 (geplant)

- [ ] Multi-User Support
- [ ] Team-wide Decision Cache Sharing
- [ ] Advanced Analytics & Insights

---

## 📞 Support

**Issues**: Siehe `.claude/plans/fluttering-jumping-hopcroft.md` für Details

**Logs**: `C:\Users\benfi\Ablage_System\.claude\mcp-server\logs\`

**Metrics**: `OrchestrationMetrics().get_summary()`

---

**Version**: 1.0.0
**Last Updated**: 2026-01-04
**Status**: ✅ Production-Ready
