# Initial_Prompt.md für Ablage-System

**Ein umfassendes Dokumenten-Management- und OCR-System mit Multi-Backend-Architektur für deutsche Dokumente**

---

## 📋 Projektübersicht

Das **Ablage-System** ist ein intelligentes Dokumentenverarbeitungssystem, das speziell für die Verarbeitung deutschsprachiger Dokumente optimiert ist. Es kombiniert mehrere OCR-Backends (DeepSeek-Janus-Pro, GOT-OCR 2.0, Surya+Docling) mit intelligenter Routing-Logik, um maximale Erkennungsqualität bei optimaler Ressourcennutzung zu erreichen.

### Kernfunktionen
- **Multi-Backend OCR**: GPU-basiert (DeepSeek, GOT-OCR) und CPU-basiert (Surya, Docling)
- **Deutsche Sprachoptimierung**: Umlaut-Erkennung, DIN 5008, XRechnung/ZUGFeRD
- **DSGVO-Compliance**: Anonymisierung, Audit-Logging, Löschkonzepte
- **Claude Code Integration**: Vollständige Konfiguration für KI-gestützte Entwicklung

---

## 🏗️ Projektstruktur und Architektur

```
Ablage-System/
├── .claude/                          # Claude Code Konfiguration
│   ├── settings.json                 # Hauptkonfiguration
│   ├── settings.local.json           # Lokale Overrides (git-ignored)
│   ├── commands/                     # Custom Slash Commands
│   │   ├── ocr-analyze.md            # /project:ocr-analyze
│   │   ├── german-check.md           # /project:german-check
│   │   └── deploy/
│   │       ├── staging.md
│   │       └── production.md
│   ├── agents/                       # Subagent-Definitionen
│   │   ├── security-auditor.md
│   │   └── ocr-specialist.md
│   └── hooks/                        # Custom Hooks
│       └── validate-german.py
│
├── CLAUDE.md                         # Hauptinstruktionen für Claude
├── CLAUDE.local.md                   # Persönliche Notizen (git-ignored)
├── .claudeignore                     # Ausgeschlossene Dateien
├── .mcp.json                         # MCP-Server Konfiguration
│
├── Static_Knowledge/                 # Unveränderliches Domänenwissen
│   ├── german_document_types.yaml
│   ├── din_5008_standards.yaml
│   ├── xrechnung_schema.xsd
│   └── zugferd_profiles.json
│
├── Dynamic_Knowledge/                # Lernfähiges Wissen
│   ├── detected_patterns/
│   ├── correction_rules/
│   └── entity_mappings/
│
├── Relations/                        # Beziehungsdefinitionen
│   ├── document_relations.yaml
│   └── entity_graph.json
│
├── Execution_Layer/                  # Ausführungslogik
│   ├── routers/
│   │   ├── ocr_router.py
│   │   └── backend_selector.py
│   ├── workers/
│   │   ├── gpu_worker.py
│   │   └── cpu_worker.py
│   └── pipelines/
│       ├── invoice_pipeline.py
│       └── contract_pipeline.py
│
├── Meta-Layer/                       # Metadaten und Orchestrierung
│   ├── agent_registry.yaml
│   ├── skill_definitions/
│   └── orchestration_rules.yaml
│
├── app/                              # Haupt-Applikation
│   ├── __init__.py
│   ├── main.py                       # FastAPI Einstiegspunkt
│   ├── config.py                     # Konfigurationsmanagement
│   ├── database.py                   # Datenbankverbindung
│   ├── models/                       # SQLAlchemy Models
│   │   ├── __init__.py
│   │   ├── document.py
│   │   └── ocr_job.py
│   ├── schemas/                      # Pydantic Schemas
│   │   ├── __init__.py
│   │   ├── document.py
│   │   └── ocr_result.py
│   ├── api/                          # API Router
│   │   ├── __init__.py
│   │   ├── v1/
│   │   │   ├── documents.py
│   │   │   ├── ocr.py
│   │   │   └── health.py
│   │   └── deps.py
│   ├── services/                     # Business-Logik
│   │   ├── ocr_service.py
│   │   ├── text_processor.py
│   │   ├── german_normalizer.py
│   │   └── document_classifier.py
│   └── utils/
│       ├── umlaut_handler.py
│       └── gdpr_anonymizer.py
│
├── backends/                         # OCR-Backend-Integrationen
│   ├── deepseek_janus/
│   │   ├── Dockerfile
│   │   ├── config.yaml
│   │   └── client.py
│   ├── got_ocr/
│   │   ├── Dockerfile
│   │   └── client.py
│   ├── surya_docling/
│   │   ├── Dockerfile
│   │   └── client.py
│   └── base.py                       # Abstract Backend Interface
│
├── infrastructure/                   # IaC und Deployment
│   ├── docker/
│   │   ├── docker-compose.yml
│   │   ├── docker-compose.gpu.yml
│   │   ├── docker-compose.monitoring.yml
│   │   └── Dockerfile
│   ├── terraform/
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   └── modules/
│   │       ├── vpc/
│   │       ├── gpu_instance/
│   │       └── ecs/
│   ├── kubernetes/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── ingress.yaml
│   └── ansible/
│       ├── playbook.yml
│       └── roles/
│
├── monitoring/                       # Observability
│   ├── prometheus/
│   │   ├── prometheus.yml
│   │   └── rules/
│   │       └── alerts.yml
│   ├── grafana/
│   │   └── dashboards/
│   │       ├── ocr-metrics.json
│   │       └── system-health.json
│   ├── alertmanager/
│   │   └── alertmanager.yml
│   └── elk/
│       ├── logstash.conf
│       └── filebeat.yml
│
├── tests/                            # Teststruktur
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_text_processor.py
│   │   ├── test_umlaut_handler.py
│   │   └── test_german_normalizer.py
│   ├── integration/
│   │   ├── test_ocr_api.py
│   │   └── test_backend_routing.py
│   └── e2e/
│       └── test_document_workflow.py
│
├── .github/
│   └── workflows/
│       ├── ci.yml
│       ├── cd.yml
│       └── security-scan.yml
│
├── .pre-commit-config.yaml
├── pyproject.toml
├── requirements.txt
├── .env.example
└── README.md
```

---

## 🤖 CLAUDE.md - Hauptkonfiguration

```markdown
# Ablage-System - Claude Code Entwicklungsguide

## Projekt-Identität
Dies ist das **Ablage-System** - ein Multi-Backend OCR-System für deutsche Dokumentenverarbeitung.
Primäre Sprache: Python 3.11+
Framework: FastAPI
OCR-Backends: DeepSeek-Janus-Pro (GPU A), GOT-OCR 2.0 (GPU B), Surya+Docling (CPU C)

## Tech Stack
- **Backend**: FastAPI 0.115+, Pydantic 2.0+, SQLAlchemy 2.0 (async)
- **OCR**: DeepSeek-Janus-Pro 7B, GOT-OCR 2.0, Surya, Docling
- **Database**: PostgreSQL 16, Redis 7
- **Infrastructure**: Docker, Kubernetes, Terraform
- **Monitoring**: Prometheus, Grafana, ELK Stack

## Projektstruktur-Konventionen
- `app/`: Haupt-Applikationscode (FastAPI)
- `backends/`: OCR-Backend-Integrationen
- `Static_Knowledge/`: Unveränderliche Domänendaten
- `Dynamic_Knowledge/`: Lernfähige/anpassbare Daten
- `Execution_Layer/`: Routing und Worker-Logik
- `Meta-Layer/`: Orchestrierung und Agent-Registry

## Build Commands
- `make dev`: Development Server starten (uvicorn --reload)
- `make test`: pytest mit Coverage
- `make lint`: ruff check + format
- `make type`: mypy Type-Checking
- `make docker-build`: Docker Images bauen
- `make docker-up`: Docker Compose starten

## Code Style Guidelines
- Verwende Type Hints für alle Funktionen
- Pydantic V2 Syntax für Schemas
- Async/await für alle I/O-Operationen
- Deutsche Kommentare in docstrings ERLAUBT für domänenspezifische Logik
- IMPORTANT: UTF-8 Encoding für alle Dateien (Umlaute!)

## Deutsche Sprachspezifika
- Umlaut-Handling: Verwende `app/utils/umlaut_handler.py`
- Datumsformat: DD.MM.YYYY (deutsches Format primär)
- Währung: EUR mit deutschem Format (1.234,56 €)
- DIN 5008: Referenz in `Static_Knowledge/din_5008_standards.yaml`

## OCR-Backend-Routing-Regeln
1. **Formeln/Geometrie** → GOT-OCR 2.0
2. **Komplexe multimodale Analyse** → DeepSeek-Janus-Pro (wenn GPU 24GB+ verfügbar)
3. **Strukturierte PDFs (Rechnungen, Verträge)** → Docling
4. **Multi-Language/Layout-kritisch** → Surya
5. **Fallback-Kette**: Janus → GOT → Surya → Docling → Tesseract

## Workflow Rules
- YOU MUST run `make lint` before committing
- ALWAYS write tests for new OCR-processing logic
- NEVER commit .env files or credentials
- Prefer async database operations

## Forbidden Actions
- DO NOT read `.env` or `secrets/` directories
- DO NOT modify `Static_Knowledge/` ohne Review
- DO NOT deploy to production ohne CI-Pipeline
- DO NOT use synchronous HTTP calls in async contexts

## DSGVO-Compliance
- Alle PII müssen über `gdpr_anonymizer.py` verarbeitet werden
- Audit-Logging ist PFLICHT für Dokumentenzugriffe
- Löschfristen gemäß `Static_Knowledge/retention_rules.yaml`

@docs/architecture.md
@docs/ocr-backends.md
@docs/german-processing.md
```

---

## ⚙️ .claude/settings.json

```json
{
  "permissions": {
    "allow": [
      "Bash(make *)",
      "Bash(pytest *)",
      "Bash(docker compose *)",
      "Bash(git add:*)",
      "Bash(git commit:*)",
      "Bash(git push:*)",
      "Bash(ruff *)",
      "Bash(mypy *)",
      "Bash(uvicorn *)",
      "Read",
      "Edit",
      "Write",
      "mcp__filesystem__*",
      "mcp__postgres__query",
      "mcp__redis__*"
    ],
    "deny": [
      "Bash(rm -rf:*)",
      "Bash(curl:*)",
      "Bash(wget:*)",
      "Read(./.env)",
      "Read(./.env.*)",
      "Read(./secrets/**)",
      "Read(./config/credentials.json)",
      "Read(**/*.pem)",
      "Read(**/*.key)",
      "Write(./.env)",
      "Write(./secrets/**)"
    ]
  },
  "env": {
    "CLAUDE_CODE_ENABLE_TELEMETRY": "0",
    "PYTHONPATH": "${workspaceFolder}/app",
    "TORCH_DEVICE": "cuda",
    "OCR_DEFAULT_LANGUAGE": "deu"
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "python scripts/validate_utf8.py"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "ruff format --quiet $(jq -r '.tool_input.file_path' 2>/dev/null || echo '')"
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "git add -A && git diff --cached --quiet || git commit -m 'Auto-checkpoint by Claude'"
          }
        ]
      }
    ]
  },
  "mcpServers": {}
}
```

---

## 🔌 .mcp.json - MCP-Server Konfiguration

```json
{
  "mcpServers": {
    "filesystem": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "./app", "./backends", "./tests"]
    },
    "postgres": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres"],
      "env": {
        "DATABASE_URL": "${DATABASE_URL}"
      }
    },
    "redis": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "mcp-server-redis"],
      "env": {
        "REDIS_URL": "${REDIS_URL}"
      }
    },
    "sequential-thinking": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "mcp-sequentialthinking-tools"]
    },
    "ocr-router": {
      "type": "stdio",
      "command": "python",
      "args": ["./mcp_servers/ocr_router_server.py"],
      "env": {
        "GPU_BACKEND_URL": "http://localhost:8001",
        "CPU_BACKEND_URL": "http://localhost:8002"
      }
    }
  }
}
```

---

## 🚫 .claudeignore

```gitignore
# Secrets und Credentials
.env
.env.*
secrets/
*.pem
*.key
credentials.json
**/auth_tokens/

# Build Artifacts
dist/
build/
*.egg-info/
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/
htmlcov/
*.pyc

# Node
node_modules/

# IDE
.idea/
.vscode/
*.swp
*.swo

# ML Models (zu groß)
models/
*.bin
*.safetensors
*.gguf

# Logs
logs/
*.log

# Temporäre Dateien
tmp/
temp/
*.tmp

# Test-Fixtures (große Dateien)
tests/fixtures/large_*

# Infrastructure Secrets
infrastructure/terraform/*.tfvars
infrastructure/terraform/.terraform/
infrastructure/ansible/vault_password
```

---

## 🪝 Git Hooks

### .github/hooks/pre-commit

```bash
#!/bin/bash
set -e

echo "🔍 Running pre-commit checks..."

# 1. Ruff Linting
echo "→ Linting with Ruff..."
ruff check app/ backends/ --fix

# 2. Ruff Formatting
echo "→ Formatting with Ruff..."
ruff format app/ backends/

# 3. Type Checking
echo "→ Type checking with mypy..."
mypy app/ --strict --ignore-missing-imports

# 4. UTF-8 Validation (für deutsche Umlaute)
echo "→ Validating UTF-8 encoding..."
find app/ backends/ -name "*.py" -exec file {} \; | grep -v "UTF-8\|ASCII" && {
    echo "❌ Non-UTF-8 files detected!"
    exit 1
} || true

# 5. Secrets Detection
echo "→ Checking for secrets..."
detect-secrets scan --baseline .secrets.baseline

# 6. Unit Tests (schnell)
echo "→ Running fast unit tests..."
pytest tests/unit -x -q --tb=short

echo "✅ All pre-commit checks passed!"
```

### .github/hooks/pre-push

```bash
#!/bin/bash
set -e

echo "🚀 Running pre-push checks..."

# Full test suite
pytest tests/ --cov=app --cov-fail-under=80

# Security scan
bandit -r app/ -ll

# Dependency check
safety check -r requirements.txt

echo "✅ All pre-push checks passed!"
```

---

## 🔄 GitHub Actions Workflows

### .github/workflows/ci.yml

```yaml
name: CI Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

env:
  PYTHON_VERSION: '3.11'
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: 'pip'
      - name: Install Ruff
        run: pipx install ruff
      - name: Lint with Ruff
        run: ruff check --output-format=github .
      - name: Format check
        run: ruff format --check --diff .

  type-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: 'pip'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install mypy types-requests
      - name: Type check with mypy
        run: mypy app/ --strict

  test:
    runs-on: ubuntu-latest
    needs: [lint, type-check]
    strategy:
      matrix:
        python-version: ['3.10', '3.11', '3.12']
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: test
          POSTGRES_DB: test_db
        ports:
          - 5432:5432
      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: 'pip'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov pytest-asyncio
      - name: Run tests
        env:
          DATABASE_URL: postgresql://postgres:test@localhost/test_db
          REDIS_URL: redis://localhost:6379
        run: pytest tests/ --cov=app --cov-report=xml --junitxml=junit.xml
      - name: Upload coverage
        uses: codecov/codecov-action@v4

  docker-build:
    runs-on: ubuntu-latest
    needs: test
    if: github.event_name == 'push'
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      - name: Login to GHCR
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

---

## 🖥️ Backend-Architektur

### DeepSeek-Janus-Pro (GPU Backend A)

```yaml
# backends/deepseek_janus/config.yaml
model:
  name: deepseek-ai/Janus-Pro-7B
  type: multimodal_causal_lm

hardware:
  device: cuda
  vram_required: 24GB
  dtype: bfloat16
  flash_attention: true

server:
  host: 0.0.0.0
  port: 8001
  workers: 1

capabilities:
  - image_understanding
  - document_ocr
  - formula_recognition
  - table_extraction
  - image_generation

performance:
  inference_time_per_page: 2-5s
  batch_size: 4
  max_tokens: 4096
```

### backends/deepseek_janus/client.py

```python
import torch
from transformers import AutoModelForCausalLM, BitsAndBytesConfig
from janus.models import MultiModalityCausalLM, VLChatProcessor
from PIL import Image
from io import BytesIO
from typing import Optional
from pydantic import BaseModel

class JanusOCRResult(BaseModel):
    text: str
    confidence: float
    processing_time_ms: int
    backend: str = "deepseek-janus-pro"

class DeepSeekJanusClient:
    """Client für DeepSeek Janus Pro OCR Backend."""

    def __init__(self, model_path: str = "deepseek-ai/Janus-Pro-7B", quantize: bool = False):
        self.model_path = model_path

        if quantize:
            quant_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.bfloat16
            )
            self.model = AutoModelForCausalLM.from_pretrained(
                model_path,
                quantization_config=quant_config,
                trust_remote_code=True
            )
        else:
            self.model = AutoModelForCausalLM.from_pretrained(
                model_path,
                torch_dtype=torch.bfloat16,
                attn_implementation="flash_attention_2",
                trust_remote_code=True
            ).cuda().eval()

        self.processor = VLChatProcessor.from_pretrained(model_path)
        self.tokenizer = self.processor.tokenizer

    async def ocr(
        self,
        image_bytes: bytes,
        prompt: str = "Extract all text from this document.",
        language: str = "de"
    ) -> JanusOCRResult:
        import time
        start = time.perf_counter()

        image = Image.open(BytesIO(image_bytes)).convert("RGB")

        conversation = [
            {
                "role": "User",
                "content": f"<image_placeholder>\n{prompt}",
                "images": [image]
            },
            {"role": "Assistant", "content": ""}
        ]

        inputs = self.processor(
            conversations=conversation,
            images=[image],
            force_batchify=True
        ).to(self.model.device)

        inputs_embeds = self.model.prepare_inputs_embeds(**inputs)

        outputs = self.model.language_model.generate(
            inputs_embeds=inputs_embeds,
            attention_mask=inputs.attention_mask,
            max_new_tokens=4096,
            do_sample=False,
            pad_token_id=self.tokenizer.eos_token_id
        )

        text = self.tokenizer.decode(outputs[0], skip_special_tokens=True)

        elapsed_ms = int((time.perf_counter() - start) * 1000)

        return JanusOCRResult(
            text=text,
            confidence=0.95,  # Janus hat keine native Confidence
            processing_time_ms=elapsed_ms
        )
```

### GOT-OCR 2.0 (GPU Backend B)

```python
# backends/got_ocr/client.py
from transformers import AutoProcessor, AutoModelForImageTextToText
import torch
from PIL import Image
from io import BytesIO
from pydantic import BaseModel

class GOTOCRResult(BaseModel):
    text: str
    confidence: float
    format: str  # "plain" | "markdown" | "latex"
    processing_time_ms: int
    backend: str = "got-ocr-2.0"

class GOTOCRClient:
    """Client für GOT-OCR 2.0 Backend (580M Parameter)."""

    def __init__(self, model_path: str = "stepfun-ai/GOT-OCR-2.0-hf"):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = AutoModelForImageTextToText.from_pretrained(
            model_path,
            torch_dtype=torch.bfloat16 if self.device == "cuda" else torch.float32,
            device_map=self.device
        )
        self.processor = AutoProcessor.from_pretrained(model_path, use_fast=True)

    async def ocr(
        self,
        image_bytes: bytes,
        output_format: str = "markdown",  # plain, markdown, latex
        region: Optional[list] = None  # [x1, y1, x2, y2]
    ) -> GOTOCRResult:
        import time
        start = time.perf_counter()

        image = Image.open(BytesIO(image_bytes)).convert("RGB")

        inputs = self.processor(
            image,
            return_tensors="pt",
            format=(output_format == "markdown"),
        ).to(self.device)

        outputs = self.model.generate(
            **inputs,
            do_sample=False,
            max_new_tokens=4096,
            stop_strings="<|im_end|>",
            tokenizer=self.processor.tokenizer
        )

        text = self.processor.decode(
            outputs[0, inputs["input_ids"].shape[1]:],
            skip_special_tokens=True
        )

        elapsed_ms = int((time.perf_counter() - start) * 1000)

        return GOTOCRResult(
            text=text,
            confidence=0.92,
            format=output_format,
            processing_time_ms=elapsed_ms
        )
```

### Surya + Docling (CPU Backend C)

```python
# backends/surya_docling/client.py
import os
os.environ["TORCH_DEVICE"] = "cpu"
os.environ["RECOGNITION_BATCH_SIZE"] = "4"

from surya.ocr import run_ocr
from surya.model.detection.model import load_model as load_det_model
from surya.model.recognition.model import load_model as load_rec_model
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions
from PIL import Image
from io import BytesIO
from pathlib import Path
from pydantic import BaseModel

class SuryaDoclingResult(BaseModel):
    text: str
    structured_data: Optional[dict]
    confidence: float
    processing_time_ms: int
    backend: str = "surya-docling"

class SuryaDoclingClient:
    """CPU-optimierter Client für Surya OCR + Docling."""

    def __init__(self):
        # Surya Models laden
        self.det_model = load_det_model()
        self.rec_model = load_rec_model()

        # Docling Converter
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = False  # Surya übernimmt OCR
        pipeline_options.do_table_structure = True

        self.docling_converter = DocumentConverter()

    async def ocr_image(
        self,
        image_bytes: bytes,
        languages: list[str] = ["de", "en"]
    ) -> SuryaDoclingResult:
        import time
        start = time.perf_counter()

        image = Image.open(BytesIO(image_bytes)).convert("RGB")

        predictions = run_ocr(
            [image],
            [languages],
            self.det_model,
            None,  # det_processor
            self.rec_model,
            None   # rec_processor
        )

        text_lines = []
        confidences = []

        for pred in predictions:
            for line in pred.text_lines:
                text_lines.append(line.text)
                confidences.append(line.confidence if hasattr(line, 'confidence') else 0.9)

        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        return SuryaDoclingResult(
            text="\n".join(text_lines),
            structured_data=None,
            confidence=avg_confidence,
            processing_time_ms=elapsed_ms
        )

    async def process_pdf(self, pdf_path: Path) -> SuryaDoclingResult:
        import time
        start = time.perf_counter()

        result = self.docling_converter.convert(str(pdf_path))
        markdown = result.document.export_to_markdown()
        json_data = result.document.export_to_json()

        elapsed_ms = int((time.perf_counter() - start) * 1000)

        return SuryaDoclingResult(
            text=markdown,
            structured_data=json_data,
            confidence=0.88,
            processing_time_ms=elapsed_ms
        )
```

---

## 🔀 Backend-Routing-Logik

```python
# Execution_Layer/routers/ocr_router.py
from enum import Enum
from typing import Protocol, Optional
from pydantic import BaseModel
import asyncio

class BackendType(str, Enum):
    JANUS_PRO = "deepseek-janus-pro"
    GOT_OCR = "got-ocr-2.0"
    SURYA_DOCLING = "surya-docling"
    TESSERACT = "tesseract"

class DocumentAnalysis(BaseModel):
    has_formulas: bool = False
    has_tables: bool = False
    has_complex_layout: bool = False
    requires_image_understanding: bool = False
    languages: list[str] = ["de"]
    is_scanned: bool = False
    page_count: int = 1

class OCRBackend(Protocol):
    async def ocr(self, image_bytes: bytes, **kwargs) -> dict: ...

class OCRRouter:
    """Intelligentes Routing zwischen OCR-Backends."""

    def __init__(
        self,
        janus_client: Optional[OCRBackend] = None,
        got_client: Optional[OCRBackend] = None,
        surya_client: Optional[OCRBackend] = None
    ):
        self.backends = {
            BackendType.JANUS_PRO: janus_client,
            BackendType.GOT_OCR: got_client,
            BackendType.SURYA_DOCLING: surya_client,
        }

        self.gpu_available = self._check_gpu()
        self.vram_gb = self._get_vram() if self.gpu_available else 0

    def _check_gpu(self) -> bool:
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False

    def _get_vram(self) -> float:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.get_device_properties(0).total_memory / (1024**3)
        return 0

    def select_backend(self, analysis: DocumentAnalysis) -> BackendType:
        """Wählt das optimale Backend basierend auf Dokumenteigenschaften."""

        # Regel 1: Komplexe Formeln/Geometrie → GOT-OCR
        if analysis.has_formulas:
            return BackendType.GOT_OCR

        # Regel 2: Multimodale Analyse benötigt → Janus (wenn genug VRAM)
        if analysis.requires_image_understanding:
            if self.gpu_available and self.vram_gb >= 16:
                return BackendType.JANUS_PRO
            return BackendType.GOT_OCR

        # Regel 3: Strukturierte Dokumente (Tabellen) → Surya/Docling
        if analysis.has_tables and not analysis.has_formulas:
            return BackendType.SURYA_DOCLING

        # Regel 4: Multi-Language oder komplexes Layout → Surya
        if len(analysis.languages) > 1 or analysis.has_complex_layout:
            return BackendType.SURYA_DOCLING

        # Regel 5: Einfache gescannte Dokumente
        if analysis.is_scanned:
            if self.gpu_available:
                return BackendType.GOT_OCR
            return BackendType.SURYA_DOCLING

        # Default: Surya für CPU-effiziente Verarbeitung
        return BackendType.SURYA_DOCLING

    async def process_with_fallback(
        self,
        image_bytes: bytes,
        analysis: DocumentAnalysis,
        fallback_chain: Optional[list[BackendType]] = None
    ) -> dict:
        """Verarbeitet mit automatischem Fallback."""

        if fallback_chain is None:
            if self.gpu_available:
                fallback_chain = [
                    BackendType.JANUS_PRO,
                    BackendType.GOT_OCR,
                    BackendType.SURYA_DOCLING
                ]
            else:
                fallback_chain = [
                    BackendType.SURYA_DOCLING,
                    BackendType.GOT_OCR
                ]

        primary = self.select_backend(analysis)
        ordered = [primary] + [b for b in fallback_chain if b != primary]

        errors = []
        for backend_type in ordered:
            backend = self.backends.get(backend_type)
            if backend is None:
                continue

            try:
                result = await backend.ocr(image_bytes, languages=analysis.languages)

                if self._validate_result(result):
                    return {
                        "backend_used": backend_type.value,
                        "result": result,
                        "fallbacks_tried": errors
                    }
            except Exception as e:
                errors.append({"backend": backend_type.value, "error": str(e)})
                continue

        raise RuntimeError(f"Alle Backends fehlgeschlagen: {errors}")

    def _validate_result(self, result: dict) -> bool:
        """Validiert OCR-Ergebnis auf Qualität."""
        if not result or not result.get("text"):
            return False
        if result.get("confidence", 0) < 0.5:
            return False
        if len(result.get("text", "")) < 10:
            return False
        return True
```

---

## 🇩🇪 Deutsche Sprachverarbeitung

### app/utils/umlaut_handler.py

```python
"""Handler für deutsche Umlaute und Sonderzeichen."""
import re
import unicodedata
from typing import Callable

class UmlautHandler:
    """Verarbeitung deutscher Umlaute für OCR-Systeme."""

    # OCR-Fehler-Korrekturen
    OCR_CORRECTIONS = {
        r'\bii\b': 'ü',
        r'i:i': 'ö',
        r'(?<=[a-z])B(?=[a-z])': 'ß',
        r'\bfur\b': 'für',
        r'\buber\b': 'über',
        r'\bUbung\b': 'Übung',
        r'\bGroBe\b': 'Größe',
        r'\bStraBe\b': 'Straße',
    }

    @staticmethod
    def normalize_to_ascii(text: str) -> str:
        """Konvertiert Umlaute zu ASCII-Äquivalenten.

        ä → ae, ö → oe, ü → ue, ß → ss
        """
        umlaut_map = {
            ord('ä'): 'ae', ord('ö'): 'oe', ord('ü'): 'ue', ord('ß'): 'ss',
            ord('Ä'): 'Ae', ord('Ö'): 'Oe', ord('Ü'): 'Ue', ord('ẞ'): 'SS'
        }
        return text.translate(umlaut_map)

    @staticmethod
    def correct_ocr_errors(text: str) -> str:
        """Korrigiert häufige OCR-Fehler bei Umlauten."""
        result = text
        for pattern, replacement in UmlautHandler.OCR_CORRECTIONS.items():
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
        return result

    @staticmethod
    def normalize_unicode(text: str) -> str:
        """Normalisiert Unicode zu NFC-Form."""
        return unicodedata.normalize('NFC', text)

    @classmethod
    def full_german_normalization(cls, text: str) -> str:
        """Vollständige Normalisierung für deutsche Texte."""
        text = cls.normalize_unicode(text)
        text = cls.correct_ocr_errors(text)
        return text
```

### app/utils/german_patterns.py

```python
"""Regex-Patterns für deutsche Dokumentenfelder."""
import re
from typing import Optional

GERMAN_PATTERNS = {
    # IBAN (Deutschland: 22 Zeichen)
    'iban_de': r'DE\s?[0-9]{2}\s?(?:[0-9]{4}\s?){4}[0-9]{2}',

    # USt-IdNr. (Umsatzsteuer-Identifikationsnummer)
    'vat_de': r'DE\s?[0-9]{9}',

    # Deutsche Steuernummer (variiert je nach Bundesland)
    'steuernummer': r'\b(?:\d{3}[\s/]?\d{3}[\s/]?\d{5}|\d{2}[\s/]?\d{3}[\s/]?\d{5}|\d{5}[\s/]?\d{5}|\d{10,11})\b',

    # Deutsche Telefonnummer
    'phone_de': r'\+49\s?[1-9][0-9]{1,14}|0[1-9][0-9]{1,14}',

    # Deutsche PLZ (5 Ziffern)
    'plz_de': r'\b[0-9]{5}\b',

    # Datum (deutsches Format)
    'date_de': r'\b(?:0?[1-9]|[12][0-9]|3[01])\.(?:0?[1-9]|1[0-2])\.(?:19|20)\d{2}\b',

    # Währung EUR
    'eur_amount': r'(?:€|EUR)\s?[\d.,]+|\b[\d.,]+\s?(?:€|EUR)\b',

    # Rechnungsnummer
    'invoice_number': r'(?:RE|RG|INV)[\s\-]?(?:\d+[\s\-/]?)+',

    # Handelsregisternummer
    'hrb': r'(?:HRB|HRA)\s?\d+',
}

def extract_german_fields(text: str) -> dict[str, list[str]]:
    """Extrahiert deutsche Dokumentenfelder aus Text."""
    results = {}
    for field_name, pattern in GERMAN_PATTERNS.items():
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            results[field_name] = matches
    return results

def validate_german_iban(iban: str) -> bool:
    """Validiert deutsche IBAN mit Prüfsumme."""
    iban = iban.replace(' ', '').upper()
    if not re.match(r'^DE\d{20}$', iban):
        return False
    # Prüfsummenberechnung
    rearranged = iban[4:] + iban[:4]
    numeric = ''.join(str(int(c, 36)) for c in rearranged)
    return int(numeric) % 97 == 1
```

---

## 📊 Pydantic Schemas

### app/schemas/document.py

```python
from datetime import datetime
from typing import Optional, Annotated
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict, field_validator

class DocumentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class DocumentBase(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    filename: Annotated[str, Field(min_length=1, max_length=255)]
    content_type: str = Field(pattern=r"^[\w]+/[\w\-\+\.]+$")

class DocumentCreate(DocumentBase):
    file_size: Annotated[int, Field(gt=0, le=50_000_000)]  # Max 50MB

class DocumentResponse(DocumentBase):
    id: int
    status: DocumentStatus
    created_at: datetime
    updated_at: Optional[datetime] = None
    text_content: Optional[str] = None
    confidence_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    backend_used: Optional[str] = None
    processing_time_ms: Optional[int] = None

    # Deutsche Dokumentenfelder
    extracted_iban: Optional[str] = None
    extracted_date: Optional[str] = None
    extracted_amount: Optional[str] = None

class OCRResult(BaseModel):
    model_config = ConfigDict(strict=True)

    text: str
    confidence: float = Field(ge=0.0, le=1.0)
    language: str = Field(default="de")
    processing_time_ms: int = Field(ge=0)
    backend: str

    # Strukturierte Daten
    tables: Optional[list[dict]] = None
    bounding_boxes: Optional[list[list[float]]] = None

    @field_validator("text")
    @classmethod
    def normalize_text(cls, v: str) -> str:
        from app.utils.umlaut_handler import UmlautHandler
        return UmlautHandler.full_german_normalization(v)

class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str
    backends: dict[str, bool]
    database: bool
    redis: bool
```

---

## 🗄️ Enterprise Database Architecture

### 📊 ER-Diagramm

```mermaid
erDiagram
    Organization ||--o{ Tenant : has
    Tenant ||--o{ User : contains
    User ||--o{ Document : uploads
    User ||--o{ AuditLog : triggers
    Document ||--o{ DocumentVersion : has
    Document ||--o{ OCRJob : queues
    Document ||--o{ ExtractedEntity : contains
    OCRJob }o--|| OCRBackendRegistry : uses
    OCRJob ||--o{ OCRJobAttempt : has
    Document }o--o{ DocumentTag : tagged
    Tag ||--o{ DocumentTag : links

    Organization {
        int id PK
        string name UK
        string domain UK
        json settings
        datetime created_at
        datetime updated_at
    }

    Tenant {
        int id PK
        int organization_id FK
        string tenant_key UK
        string name
        json config
        int storage_quota_gb
        int monthly_ocr_limit
        datetime created_at
    }

    User {
        int id PK
        int tenant_id FK
        string email UK
        string password_hash
        string role
        json permissions
        datetime last_login
        datetime created_at
    }

    Document {
        int id PK
        int tenant_id FK
        int user_id FK
        string document_key UK
        string filename
        string content_type
        int file_size_bytes
        string storage_path
        string status
        json metadata
        datetime created_at
        datetime updated_at
        datetime deleted_at
    }

    DocumentVersion {
        int id PK
        int document_id FK
        int version_number
        string change_type
        json changes
        int created_by FK
        datetime created_at
    }

    OCRBackendRegistry {
        int id PK
        string backend_key UK
        string backend_name
        string backend_type
        json capabilities
        json config
        int priority
        boolean is_active
        datetime created_at
    }

    OCRJob {
        bigint id PK
        int document_id FK
        int backend_id FK
        string job_key UK
        string status
        int priority
        json parameters
        datetime scheduled_at
        datetime started_at
        datetime completed_at
    }

    OCRJobAttempt {
        bigint id PK
        bigint job_id FK
        int attempt_number
        string status
        json error_details
        int processing_time_ms
        datetime started_at
        datetime finished_at
    }
```

### 🏗️ Complete SQLAlchemy Models

#### app/models/__init__.py

```python
"""
Enterprise Database Models für Ablage-System.

Vollständige SQLAlchemy 2.0 Models mit:
- Multi-Tenant-Architektur
- Audit-Logging
- Document Versioning
- Dynamic Backend Registry
- Job Queue Management
"""

from app.models.base import Base, TenantMixin, TimestampMixin, SoftDeleteMixin
from app.models.organization import Organization, Tenant
from app.models.user import User, UserSession
from app.models.document import (
    Document,
    DocumentVersion,
    DocumentTag,
    Tag,
    ExtractedEntity
)
from app.models.ocr_backend import OCRBackendRegistry, BackendCapability
from app.models.ocr_job import (
    OCRJob,
    OCRJobAttempt,
    OCRResult,
    OCRResultField
)
from app.models.audit import AuditLog, DataProtectionLog

__all__ = [
    'Base',
    'Organization',
    'Tenant',
    'User',
    'UserSession',
    'Document',
    'DocumentVersion',
    'DocumentTag',
    'Tag',
    'ExtractedEntity',
    'OCRBackendRegistry',
    'BackendCapability',
    'OCRJob',
    'OCRJobAttempt',
    'OCRResult',
    'OCRResultField',
    'AuditLog',
    'DataProtectionLog',
]
```

#### app/models/base.py

```python
from datetime import datetime
from typing import Optional, Any
from sqlalchemy import DateTime, Integer, String, func, Index, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, declared_attr
from sqlalchemy.ext.asyncio import AsyncAttrs

class Base(AsyncAttrs, DeclarativeBase):
    """Base class für alle Models mit async support."""

    @declared_attr.directive
    def __tablename__(cls) -> str:
        """Automatische Tabellennamen aus Klassennamen."""
        return cls.__name__.lower() + 's'

class TimestampMixin:
    """Mixin für created_at und updated_at timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )

    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
        index=True
    )

class TenantMixin:
    """Mixin für Multi-Tenant-Unterstützung."""

    @declared_attr
    def tenant_id(cls) -> Mapped[int]:
        return mapped_column(
            Integer,
            nullable=False,
            index=True
        )

class SoftDeleteMixin:
    """Mixin für Soft-Delete-Funktionalität."""

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        self.deleted_at = datetime.utcnow()
```

#### app/models/organization.py

```python
from typing import List, Optional
from sqlalchemy import String, Integer, JSON, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin

class Organization(Base, TimestampMixin):
    """Organisation (oberste Ebene für Multi-Mandanten)."""

    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)

    # Enterprise Settings
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    max_tenants: Mapped[int] = mapped_column(Integer, default=10)
    max_users_per_tenant: Mapped[int] = mapped_column(Integer, default=100)

    # Relationships
    tenants: Mapped[List["Tenant"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint('max_tenants > 0', name='check_max_tenants_positive'),
        CheckConstraint('max_users_per_tenant > 0', name='check_max_users_positive'),
    )

class Tenant(Base, TimestampMixin):
    """Mandant innerhalb einer Organisation."""

    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tenant_key: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Quotas und Limits
    storage_quota_gb: Mapped[int] = mapped_column(Integer, default=100)
    monthly_ocr_limit: Mapped[int] = mapped_column(Integer, default=10000)
    used_storage_bytes: Mapped[int] = mapped_column(Integer, default=0)
    monthly_ocr_count: Mapped[int] = mapped_column(Integer, default=0)

    # Configuration
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    allowed_file_types: Mapped[list] = mapped_column(
        JSON,
        default=lambda: ["pdf", "png", "jpg", "jpeg", "tiff"]
    )

    # Feature Flags
    features: Mapped[dict] = mapped_column(
        JSON,
        default=lambda: {
            "auto_ocr": True,
            "version_control": True,
            "audit_logging": True,
            "data_encryption": True,
            "api_access": False
        }
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(back_populates="tenants")
    users: Mapped[List["User"]] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan"
    )
    documents: Mapped[List["Document"]] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint('organization_id', 'tenant_key', name='uq_org_tenant_key'),
        CheckConstraint('storage_quota_gb > 0', name='check_storage_quota_positive'),
        CheckConstraint('monthly_ocr_limit >= 0', name='check_ocr_limit_positive'),
        Index('idx_tenant_org_id', 'organization_id'),
    )
```

#### app/models/user.py

```python
from typing import List, Optional
from datetime import datetime
from sqlalchemy import String, Integer, JSON, Boolean, DateTime, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, TenantMixin
import enum

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    USER = "user"
    VIEWER = "viewer"
    API = "api"

class User(Base, TimestampMixin, TenantMixin):
    """Benutzer-Model mit RBAC und Session-Tracking."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # Profile
    first_name: Mapped[Optional[str]] = mapped_column(String(100))
    last_name: Mapped[Optional[str]] = mapped_column(String(100))
    department: Mapped[Optional[str]] = mapped_column(String(100))

    # Security & Access
    role: Mapped[UserRole] = mapped_column(SQLEnum(UserRole), default=UserRole.USER)
    permissions: Mapped[dict] = mapped_column(
        JSON,
        default=lambda: {
            "can_upload": True,
            "can_delete_own": True,
            "can_delete_any": False,
            "can_manage_users": False,
            "can_configure_backends": False,
            "can_view_audit_logs": False
        }
    )

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # MFA
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_secret: Mapped[Optional[str]] = mapped_column(String(32))

    # API Access
    api_key: Mapped[Optional[str]] = mapped_column(String(64), unique=True, index=True)
    api_rate_limit: Mapped[int] = mapped_column(Integer, default=1000)  # requests per hour

    # Relationships
    tenant: Mapped["Tenant"] = relationship(back_populates="users")
    documents: Mapped[List["Document"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan"
    )
    sessions: Mapped[List["UserSession"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan"
    )
    audit_logs: Mapped[List["AuditLog"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index('idx_user_tenant_email', 'tenant_id', 'email'),
        Index('idx_user_active', 'is_active'),
    )

class UserSession(Base, TimestampMixin):
    """Session-Tracking für Security und Audit."""

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    session_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    # Session Data
    ip_address: Mapped[str] = mapped_column(String(45))  # IPv6 support
    user_agent: Mapped[str] = mapped_column(String(500))

    # Validity
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    user: Mapped["User"] = relationship(back_populates="sessions")

    @property
    def is_valid(self) -> bool:
        now = datetime.utcnow()
        return self.expires_at > now and self.revoked_at is None
```

#### app/models/document.py

```python
from typing import List, Optional
from datetime import datetime
from sqlalchemy import (
    String, Integer, BigInteger, Text, JSON, Boolean,
    DateTime, ForeignKey, UniqueConstraint, CheckConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, TenantMixin, SoftDeleteMixin
import enum

class DocumentStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"

class Document(Base, TimestampMixin, TenantMixin, SoftDeleteMixin):
    """Hauptdokument-Model mit Versionierung und Metadaten."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # Unique identifier
    document_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    # File Information
    filename: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Storage
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_backend: Mapped[str] = mapped_column(String(50), default="minio")

    # Status & Processing
    status: Mapped[DocumentStatus] = mapped_column(
        SQLEnum(DocumentStatus),
        default=DocumentStatus.UPLOADED,
        index=True
    )

    # German Document Specific
    document_type: Mapped[Optional[str]] = mapped_column(String(50))  # Rechnung, Vertrag, etc.
    document_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    document_language: Mapped[str] = mapped_column(String(10), default="de")

    # Extracted Content
    extracted_text: Mapped[Optional[str]] = mapped_column(Text)
    extracted_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float)

    # Business Fields (German specific)
    invoice_number: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    customer_number: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    amount_eur: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2),
        comment="Betrag in EUR mit deutscher Formatierung"
    )

    # Encryption & Security
    is_encrypted: Mapped[bool] = mapped_column(Boolean, default=False)
    encryption_key_id: Mapped[Optional[str]] = mapped_column(String(64))

    # Retention & Compliance
    retention_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    legal_hold: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship(back_populates="documents")
    user: Mapped["User"] = relationship(back_populates="documents")
    versions: Mapped[List["DocumentVersion"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentVersion.version_number.desc()"
    )
    ocr_jobs: Mapped[List["OCRJob"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan"
    )
    tags: Mapped[List["Tag"]] = relationship(
        secondary="document_tags",
        back_populates="documents"
    )
    extracted_entities: Mapped[List["ExtractedEntity"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint('tenant_id', 'document_key', name='uq_tenant_document_key'),
        CheckConstraint('file_size_bytes > 0', name='check_file_size_positive'),
        Index('idx_document_status_created', 'status', 'created_at'),
        Index('idx_document_tenant_user', 'tenant_id', 'user_id'),
        Index('idx_document_hash', 'file_hash_sha256'),
    )

class DocumentVersion(Base, TimestampMixin):
    """Versionierung für Dokumentenänderungen."""

    __tablename__ = "document_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(Integer, nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Change Tracking
    change_type: Mapped[str] = mapped_column(
        String(50),
        comment="upload, ocr_update, metadata_edit, content_edit"
    )
    changes: Mapped[dict] = mapped_column(JSON, default=dict)
    change_summary: Mapped[Optional[str]] = mapped_column(String(500))

    # Who made the change
    created_by: Mapped[int] = mapped_column(Integer, nullable=False)

    # Previous version reference
    previous_version_id: Mapped[Optional[int]] = mapped_column(Integer)

    # Content snapshot (optional)
    content_snapshot: Mapped[Optional[dict]] = mapped_column(JSON)

    # Relationships
    document: Mapped["Document"] = relationship(back_populates="versions")

    __table_args__ = (
        UniqueConstraint('document_id', 'version_number', name='uq_document_version'),
        Index('idx_version_document_number', 'document_id', 'version_number'),
    )

class Tag(Base, TimestampMixin):
    """Tags für Dokumentenkategorisierung."""

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    color: Mapped[Optional[str]] = mapped_column(String(7))  # Hex color
    description: Mapped[Optional[str]] = mapped_column(String(255))

    # Relationships
    documents: Mapped[List["Document"]] = relationship(
        secondary="document_tags",
        back_populates="tags"
    )

class DocumentTag(Base):
    """Many-to-Many Relationship zwischen Documents und Tags."""

    __tablename__ = "document_tags"

    document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("documents.id"),
        primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tags.id"),
        primary_key=True
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

class ExtractedEntity(Base, TimestampMixin):
    """Extrahierte Entitäten aus Dokumenten (NER)."""

    __tablename__ = "extracted_entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # Entity Information
    entity_type: Mapped[str] = mapped_column(
        String(50),
        index=True,
        comment="PERSON, ORG, IBAN, DATE, AMOUNT, etc."
    )
    entity_value: Mapped[str] = mapped_column(String(500), index=True)
    normalized_value: Mapped[Optional[str]] = mapped_column(String(500))

    # Position in document
    page_number: Mapped[Optional[int]] = mapped_column(Integer)
    bounding_box: Mapped[Optional[dict]] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)

    # Validation
    is_validated: Mapped[bool] = mapped_column(Boolean, default=False)
    validation_source: Mapped[Optional[str]] = mapped_column(String(50))

    # Relationships
    document: Mapped["Document"] = relationship(back_populates="extracted_entities")

    __table_args__ = (
        Index('idx_entity_document_type', 'document_id', 'entity_type'),
        Index('idx_entity_value', 'entity_value'),
    )
```

#### app/models/ocr_backend.py

```python
from typing import List, Optional
from sqlalchemy import String, Integer, JSON, Boolean, Float, CheckConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin

class OCRBackendRegistry(Base, TimestampMixin):
    """
    Dynamische Backend-Registry für OCR-Engines.
    Erlaubt das Hinzufügen neuer Backends ohne Code-Änderungen.
    """

    __tablename__ = "ocr_backend_registry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    backend_key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    backend_name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Backend Type & Version
    backend_type: Mapped[str] = mapped_column(
        String(50),
        comment="deepseek, got-ocr, surya, docling, tesseract, custom"
    )
    version: Mapped[str] = mapped_column(String(50))

    # Capabilities as JSON
    capabilities: Mapped[dict] = mapped_column(
        JSON,
        default=lambda: {
            "languages": ["de", "en"],
            "document_types": ["pdf", "image"],
            "features": {
                "table_extraction": False,
                "formula_recognition": False,
                "handwriting": False,
                "layout_analysis": False,
                "multi_column": False
            }
        }
    )

    # Performance Metrics
    avg_processing_time_ms: Mapped[Optional[int]] = mapped_column(Integer)
    success_rate: Mapped[Optional[float]] = mapped_column(Float)

    # Resource Requirements
    requires_gpu: Mapped[bool] = mapped_column(Boolean, default=False)
    min_vram_gb: Mapped[Optional[int]] = mapped_column(Integer)
    min_ram_gb: Mapped[Optional[int]] = mapped_column(Integer)
    max_file_size_mb: Mapped[int] = mapped_column(Integer, default=50)

    # Configuration
    config: Mapped[dict] = mapped_column(
        JSON,
        default=lambda: {
            "endpoint": None,
            "api_key": None,
            "model_path": None,
            "batch_size": 1,
            "timeout_seconds": 300
        }
    )

    # Routing Priority (lower = higher priority)
    priority: Mapped[int] = mapped_column(Integer, default=100)

    # Cost (for billing/quotas)
    cost_per_page: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 4),
        comment="Cost in EUR per page"
    )

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_healthy: Mapped[bool] = mapped_column(Boolean, default=True)
    last_health_check: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    ocr_jobs: Mapped[List["OCRJob"]] = relationship(
        back_populates="backend",
        cascade="all, delete-orphan"
    )
    capabilities_list: Mapped[List["BackendCapability"]] = relationship(
        back_populates="backend",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint('priority > 0', name='check_priority_positive'),
        CheckConstraint('max_file_size_mb > 0', name='check_max_file_size_positive'),
        Index('idx_backend_active_priority', 'is_active', 'priority'),
    )

class BackendCapability(Base):
    """Detaillierte Capabilities für Backend-Matching."""

    __tablename__ = "backend_capabilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    backend_id: Mapped[int] = mapped_column(Integer, nullable=False)

    capability_type: Mapped[str] = mapped_column(
        String(50),
        index=True,
        comment="language, document_type, feature"
    )
    capability_value: Mapped[str] = mapped_column(String(100))
    score: Mapped[float] = mapped_column(
        Float,
        default=1.0,
        comment="Quality score for this capability (0-1)"
    )

    # Relationships
    backend: Mapped["OCRBackendRegistry"] = relationship(back_populates="capabilities_list")

    __table_args__ = (
        Index('idx_capability_backend_type', 'backend_id', 'capability_type'),
    )
```

#### app/models/ocr_job.py

```python
from typing import List, Optional
from datetime import datetime
from sqlalchemy import (
    String, Integer, BigInteger, JSON, DateTime,
    ForeignKey, CheckConstraint, Index, Text
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin
import enum

class JobStatus(str, enum.Enum):
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"

class JobPriority(int, enum.Enum):
    LOW = 10
    NORMAL = 5
    HIGH = 3
    URGENT = 1

class OCRJob(Base, TimestampMixin):
    """
    Job-Queue für OCR-Verarbeitung mit Celery.
    Unterstützt Prioritäten, Retries und Status-Tracking.
    """

    __tablename__ = "ocr_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    backend_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Job Identification
    job_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True)

    # Status & Priority
    status: Mapped[JobStatus] = mapped_column(
        SQLEnum(JobStatus),
        default=JobStatus.PENDING,
        nullable=False,
        index=True
    )
    priority: Mapped[JobPriority] = mapped_column(
        SQLEnum(JobPriority),
        default=JobPriority.NORMAL,
        nullable=False,
        index=True
    )

    # Parameters
    parameters: Mapped[dict] = mapped_column(
        JSON,
        default=lambda: {
            "language": "de",
            "output_format": "text",
            "enable_preprocessing": True,
            "enable_postprocessing": True,
            "confidence_threshold": 0.7
        }
    )

    # Scheduling
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Retry Management
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    retry_after: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Error Tracking
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    error_count: Mapped[int] = mapped_column(Integer, default=0)

    # Performance Metrics
    processing_time_ms: Mapped[Optional[int]] = mapped_column(Integer)
    queue_time_ms: Mapped[Optional[int]] = mapped_column(Integer)

    # Relationships
    document: Mapped["Document"] = relationship(back_populates="ocr_jobs")
    backend: Mapped["OCRBackendRegistry"] = relationship(back_populates="ocr_jobs")
    attempts: Mapped[List["OCRJobAttempt"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="OCRJobAttempt.attempt_number.desc()"
    )
    result: Mapped[Optional["OCRResult"]] = relationship(
        back_populates="job",
        uselist=False
    )

    __table_args__ = (
        CheckConstraint('retry_count >= 0', name='check_retry_count_positive'),
        CheckConstraint('max_retries >= 0', name='check_max_retries_positive'),
        Index('idx_job_status_priority', 'status', 'priority', 'scheduled_at'),
        Index('idx_job_document_backend', 'document_id', 'backend_id'),
    )

class OCRJobAttempt(Base, TimestampMixin):
    """Einzelne Verarbeitungsversuche eines OCR-Jobs."""

    __tablename__ = "ocr_job_attempts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Status
    status: Mapped[JobStatus] = mapped_column(
        SQLEnum(JobStatus),
        nullable=False
    )

    # Timing
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    processing_time_ms: Mapped[Optional[int]] = mapped_column(Integer)

    # Error Details
    error_type: Mapped[Optional[str]] = mapped_column(String(100))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    error_details: Mapped[Optional[dict]] = mapped_column(JSON)
    stack_trace: Mapped[Optional[str]] = mapped_column(Text)

    # Resource Usage
    cpu_usage_percent: Mapped[Optional[float]] = mapped_column(Float)
    memory_usage_mb: Mapped[Optional[int]] = mapped_column(Integer)
    gpu_usage_percent: Mapped[Optional[float]] = mapped_column(Float)

    # Relationships
    job: Mapped["OCRJob"] = relationship(back_populates="attempts")

    __table_args__ = (
        UniqueConstraint('job_id', 'attempt_number', name='uq_job_attempt'),
        Index('idx_attempt_job_number', 'job_id', 'attempt_number'),
    )

class OCRResult(Base, TimestampMixin):
    """Ergebnisse der OCR-Verarbeitung."""

    __tablename__ = "ocr_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)

    # Extracted Content
    full_text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)

    # Structured Data
    structured_data: Mapped[Optional[dict]] = mapped_column(
        JSON,
        comment="Tables, forms, structured content"
    )

    # Layout Information
    layout_data: Mapped[Optional[dict]] = mapped_column(
        JSON,
        comment="Bounding boxes, paragraphs, columns"
    )

    # Language Detection
    detected_languages: Mapped[list] = mapped_column(JSON, default=list)
    primary_language: Mapped[str] = mapped_column(String(10), default="de")

    # Quality Metrics
    quality_score: Mapped[float] = mapped_column(Float, comment="0-1 quality score")
    warnings: Mapped[Optional[list]] = mapped_column(JSON)

    # Processing Info
    backend_used: Mapped[str] = mapped_column(String(50))
    backend_version: Mapped[str] = mapped_column(String(50))
    processing_time_ms: Mapped[int] = mapped_column(Integer)

    # Relationships
    job: Mapped["OCRJob"] = relationship(back_populates="result")
    fields: Mapped[List["OCRResultField"]] = relationship(
        back_populates="result",
        cascade="all, delete-orphan"
    )

class OCRResultField(Base):
    """Einzelne extrahierte Felder aus OCR-Ergebnissen."""

    __tablename__ = "ocr_result_fields"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    result_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Field Information
    field_name: Mapped[str] = mapped_column(String(100), index=True)
    field_value: Mapped[str] = mapped_column(Text)
    field_type: Mapped[str] = mapped_column(
        String(50),
        comment="text, number, date, iban, amount, etc."
    )

    # Confidence & Validation
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    is_validated: Mapped[bool] = mapped_column(Boolean, default=False)
    validation_method: Mapped[Optional[str]] = mapped_column(String(50))

    # Position
    page_number: Mapped[Optional[int]] = mapped_column(Integer)
    bounding_box: Mapped[Optional[dict]] = mapped_column(JSON)

    # Relationships
    result: Mapped["OCRResult"] = relationship(back_populates="fields")

    __table_args__ = (
        Index('idx_result_field_name', 'result_id', 'field_name'),
    )
```

#### app/models/audit.py

```python
from typing import Optional
from datetime import datetime
from sqlalchemy import String, Integer, JSON, DateTime, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, TenantMixin

class AuditLog(Base, TimestampMixin, TenantMixin):
    """
    DSGVO-konformes Audit-Logging für alle Systemaktivitäten.
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)

    # Action Details
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    resource_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)

    # HTTP Request Info
    method: Mapped[Optional[str]] = mapped_column(String(10))
    endpoint: Mapped[Optional[str]] = mapped_column(String(255))
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(String(500))

    # Change Details (for updates)
    old_values: Mapped[Optional[dict]] = mapped_column(JSON)
    new_values: Mapped[Optional[dict]] = mapped_column(JSON)

    # Result
    status: Mapped[str] = mapped_column(
        String(20),
        comment="success, failure, error"
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Performance
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)

    # DSGVO Fields
    contains_pii: Mapped[bool] = mapped_column(Boolean, default=False)
    data_categories: Mapped[Optional[list]] = mapped_column(
        JSON,
        comment="Categories of personal data involved"
    )
    legal_basis: Mapped[Optional[str]] = mapped_column(
        String(100),
        comment="consent, contract, legal_obligation, etc."
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship(back_populates="audit_logs")

    __table_args__ = (
        Index('idx_audit_created_action', 'created_at', 'action'),
        Index('idx_audit_user_action', 'user_id', 'action'),
        Index('idx_audit_resource', 'resource_type', 'resource_id'),
        Index('idx_audit_tenant_created', 'tenant_id', 'created_at'),
    )

class DataProtectionLog(Base, TimestampMixin):
    """
    DSGVO-spezifische Datenschutz-Aktivitäten.
    Separates Log für Datenschutz-relevante Ereignisse.
    """

    __tablename__ = "data_protection_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Request Type
    request_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="access, portability, deletion, rectification, restriction"
    )

    # Data Subject
    data_subject_id: Mapped[str] = mapped_column(String(100), nullable=False)
    data_subject_type: Mapped[str] = mapped_column(
        String(50),
        comment="user, customer, employee"
    )

    # Request Details
    requested_by: Mapped[str] = mapped_column(String(255))
    request_reason: Mapped[Optional[str]] = mapped_column(Text)

    # Processing
    processed_by: Mapped[Optional[int]] = mapped_column(Integer)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Result
    status: Mapped[str] = mapped_column(
        String(20),
        comment="pending, approved, rejected, completed"
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text)

    # Data Details
    affected_data: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        comment="List of affected data categories and counts"
    )

    # Compliance
    retention_period_days: Mapped[Optional[int]] = mapped_column(Integer)
    deletion_scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deletion_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index('idx_gdpr_type_status', 'request_type', 'status'),
        Index('idx_gdpr_subject', 'data_subject_type', 'data_subject_id'),
    )
```

### 📦 Repository Pattern Implementation

#### app/repositories/base.py

```python
from typing import Generic, TypeVar, Optional, List, Dict, Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)

class BaseRepository(Generic[ModelType]):
    """Base Repository für CRUD-Operationen."""

    def __init__(self, model: type[ModelType], session: AsyncSession):
        self.model = model
        self.session = session

    async def get(self, id: int) -> Optional[ModelType]:
        """Get by primary key."""
        result = await self.session.get(self.model, id)
        return result

    async def get_by(self, **kwargs) -> Optional[ModelType]:
        """Get single record by arbitrary filters."""
        stmt = select(self.model).filter_by(**kwargs)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_many(
        self,
        filters: Dict[str, Any] = None,
        offset: int = 0,
        limit: int = 100,
        order_by: str = None
    ) -> List[ModelType]:
        """Get multiple records with filtering and pagination."""
        stmt = select(self.model)

        if filters:
            stmt = stmt.filter_by(**filters)

        if order_by:
            stmt = stmt.order_by(order_by)

        stmt = stmt.offset(offset).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, filters: Dict[str, Any] = None) -> int:
        """Count records."""
        stmt = select(func.count()).select_from(self.model)

        if filters:
            stmt = stmt.filter_by(**filters)

        result = await self.session.execute(stmt)
        return result.scalar()

    async def create(self, **kwargs) -> ModelType:
        """Create new record."""
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def update(self, id: int, **kwargs) -> Optional[ModelType]:
        """Update existing record."""
        instance = await self.get(id)
        if not instance:
            return None

        for key, value in kwargs.items():
            setattr(instance, key, value)

        await self.session.flush()
        return instance

    async def delete(self, id: int) -> bool:
        """Delete record."""
        instance = await self.get(id)
        if not instance:
            return False

        await self.session.delete(instance)
        await self.session.flush()
        return True

    async def bulk_create(self, items: List[Dict[str, Any]]) -> List[ModelType]:
        """Bulk create records."""
        instances = [self.model(**item) for item in items]
        self.session.add_all(instances)
        await self.session.flush()
        return instances
```

#### app/repositories/document.py

```python
from typing import Optional, List
from datetime import datetime, timedelta
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload
from app.models.document import Document, DocumentStatus
from app.repositories.base import BaseRepository

class DocumentRepository(BaseRepository[Document]):
    """Repository für Document-spezifische Queries."""

    async def get_with_relations(self, document_id: int) -> Optional[Document]:
        """Get document with all relations loaded."""
        stmt = (
            select(Document)
            .options(
                selectinload(Document.versions),
                selectinload(Document.ocr_jobs),
                selectinload(Document.tags),
                selectinload(Document.extracted_entities)
            )
            .where(Document.id == document_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_tenant_and_key(
        self,
        tenant_id: int,
        document_key: str
    ) -> Optional[Document]:
        """Get document by tenant and unique key."""
        return await self.get_by(
            tenant_id=tenant_id,
            document_key=document_key
        )

    async def get_pending_ocr(self, limit: int = 10) -> List[Document]:
        """Get documents pending OCR processing."""
        stmt = (
            select(Document)
            .where(Document.status.in_([
                DocumentStatus.UPLOADED,
                DocumentStatus.QUEUED
            ]))
            .order_by(Document.created_at)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_expiring_documents(
        self,
        days_ahead: int = 30
    ) -> List[Document]:
        """Get documents expiring soon (DSGVO retention)."""
        expiry_date = datetime.utcnow() + timedelta(days=days_ahead)

        stmt = (
            select(Document)
            .where(
                and_(
                    Document.retention_until.isnot(None),
                    Document.retention_until <= expiry_date,
                    Document.legal_hold == False,
                    Document.deleted_at.is_(None)
                )
            )
            .order_by(Document.retention_until)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def search_documents(
        self,
        tenant_id: int,
        query: str = None,
        status: DocumentStatus = None,
        date_from: datetime = None,
        date_to: datetime = None,
        offset: int = 0,
        limit: int = 100
    ) -> tuple[List[Document], int]:
        """Advanced document search with full-text and filters."""
        stmt = select(Document).where(Document.tenant_id == tenant_id)
        count_stmt = (
            select(func.count())
            .select_from(Document)
            .where(Document.tenant_id == tenant_id)
        )

        # Text search
        if query:
            search_condition = or_(
                Document.filename.ilike(f"%{query}%"),
                Document.extracted_text.ilike(f"%{query}%"),
                Document.invoice_number.ilike(f"%{query}%"),
                Document.customer_number.ilike(f"%{query}%")
            )
            stmt = stmt.where(search_condition)
            count_stmt = count_stmt.where(search_condition)

        # Status filter
        if status:
            stmt = stmt.where(Document.status == status)
            count_stmt = count_stmt.where(Document.status == status)

        # Date range
        if date_from:
            stmt = stmt.where(Document.created_at >= date_from)
            count_stmt = count_stmt.where(Document.created_at >= date_from)

        if date_to:
            stmt = stmt.where(Document.created_at <= date_to)
            count_stmt = count_stmt.where(Document.created_at <= date_to)

        # Execute count
        count_result = await self.session.execute(count_stmt)
        total_count = count_result.scalar()

        # Execute paginated query
        stmt = stmt.offset(offset).limit(limit).order_by(Document.created_at.desc())
        result = await self.session.execute(stmt)
        documents = list(result.scalars().all())

        return documents, total_count
```

### 🔄 Alembic Migration Templates

#### alembic/versions/001_initial_schema.py

```python
"""Initial enterprise schema

Revision ID: 001
Revises:
Create Date: 2024-11-21 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Create all tables with proper indices and constraints."""

    # Organizations
    op.create_table('organizations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('domain', sa.String(255), nullable=False),
        sa.Column('settings', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('max_tenants', sa.Integer(), nullable=False, server_default='10'),
        sa.Column('max_users_per_tenant', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
        sa.UniqueConstraint('domain'),
        sa.CheckConstraint('max_tenants > 0', name='check_max_tenants_positive'),
        sa.CheckConstraint('max_users_per_tenant > 0', name='check_max_users_positive')
    )
    op.create_index('ix_organizations_name', 'organizations', ['name'])
    op.create_index('ix_organizations_domain', 'organizations', ['domain'])

    # Tenants
    op.create_table('tenants',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('tenant_key', sa.String(50), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('storage_quota_gb', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('monthly_ocr_limit', sa.Integer(), nullable=False, server_default='10000'),
        sa.Column('used_storage_bytes', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('monthly_ocr_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('config', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('allowed_file_types', sa.JSON(), nullable=False,
                  server_default='["pdf", "png", "jpg", "jpeg", "tiff"]'),
        sa.Column('features', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_key'),
        sa.UniqueConstraint('organization_id', 'tenant_key', name='uq_org_tenant_key'),
        sa.CheckConstraint('storage_quota_gb > 0', name='check_storage_quota_positive'),
        sa.CheckConstraint('monthly_ocr_limit >= 0', name='check_ocr_limit_positive')
    )
    op.create_index('ix_tenants_tenant_key', 'tenants', ['tenant_key'])
    op.create_index('idx_tenant_org_id', 'tenants', ['organization_id'])

    # OCR Backend Registry
    op.create_table('ocr_backend_registry',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('backend_key', sa.String(50), nullable=False),
        sa.Column('backend_name', sa.String(100), nullable=False),
        sa.Column('backend_type', sa.String(50), nullable=False),
        sa.Column('version', sa.String(50)),
        sa.Column('capabilities', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('avg_processing_time_ms', sa.Integer()),
        sa.Column('success_rate', sa.Float()),
        sa.Column('requires_gpu', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('min_vram_gb', sa.Integer()),
        sa.Column('min_ram_gb', sa.Integer()),
        sa.Column('max_file_size_mb', sa.Integer(), nullable=False, server_default='50'),
        sa.Column('config', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('cost_per_page', sa.Numeric(10, 4)),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_healthy', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('last_health_check', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('backend_key'),
        sa.CheckConstraint('priority > 0', name='check_priority_positive'),
        sa.CheckConstraint('max_file_size_mb > 0', name='check_max_file_size_positive')
    )
    op.create_index('ix_ocr_backend_registry_backend_key', 'ocr_backend_registry', ['backend_key'])
    op.create_index('idx_backend_active_priority', 'ocr_backend_registry', ['is_active', 'priority'])

    # Create remaining tables...
    # (Users, Documents, OCRJobs, AuditLogs, etc.)

    # Add initial data
    op.execute("""
        INSERT INTO ocr_backend_registry
        (backend_key, backend_name, backend_type, version, requires_gpu, priority)
        VALUES
        ('deepseek-janus-pro', 'DeepSeek Janus Pro 7B', 'deepseek', '1.0', true, 1),
        ('got-ocr-2', 'GOT-OCR 2.0', 'got-ocr', '2.0', true, 2),
        ('surya-docling', 'Surya + Docling', 'surya', '1.0', false, 3)
    """)

def downgrade() -> None:
    """Drop all tables in reverse order."""
    op.drop_table('audit_logs')
    op.drop_table('ocr_job_attempts')
    op.drop_table('ocr_jobs')
    op.drop_table('document_versions')
    op.drop_table('documents')
    op.drop_table('users')
    op.drop_table('tenants')
    op.drop_table('ocr_backend_registry')
    op.drop_table('organizations')
```

### 📈 Database Performance Optimization

#### app/database/indexes.sql

```sql
-- Performance-kritische Indizes für Ablage-System

-- Composite Indices für häufige Queries
CREATE INDEX CONCURRENTLY idx_documents_tenant_status_created
ON documents(tenant_id, status, created_at DESC);

CREATE INDEX CONCURRENTLY idx_ocr_jobs_status_priority_scheduled
ON ocr_jobs(status, priority ASC, scheduled_at ASC)
WHERE status IN ('pending', 'queued');

-- Full-Text Search für deutsche Dokumente
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX CONCURRENTLY idx_documents_filename_trgm
ON documents USING gin(filename gin_trgm_ops);

CREATE INDEX CONCURRENTLY idx_documents_text_trgm
ON documents USING gin(extracted_text gin_trgm_ops);

-- Partial Indices für aktive Records
CREATE INDEX CONCURRENTLY idx_documents_active
ON documents(tenant_id, created_at DESC)
WHERE deleted_at IS NULL;

CREATE INDEX CONCURRENTLY idx_users_active_tenant
ON users(tenant_id, email)
WHERE is_active = true;

-- BRIN Indices für Zeit-basierte Daten
CREATE INDEX idx_audit_logs_created_brin
ON audit_logs USING brin(created_at);

-- Covering Index für Document Search
CREATE INDEX CONCURRENTLY idx_documents_search_covering
ON documents(tenant_id, status, created_at DESC)
INCLUDE (filename, document_key, file_size_bytes);

-- Index für DSGVO-Compliance
CREATE INDEX CONCURRENTLY idx_documents_retention
ON documents(retention_until)
WHERE retention_until IS NOT NULL
AND legal_hold = false
AND deleted_at IS NULL;

-- Materialized View für Dashboard Statistics
CREATE MATERIALIZED VIEW mv_tenant_statistics AS
SELECT
    t.id as tenant_id,
    t.name as tenant_name,
    COUNT(DISTINCT d.id) as total_documents,
    COUNT(DISTINCT d.id) FILTER (WHERE d.status = 'completed') as processed_documents,
    COUNT(DISTINCT d.id) FILTER (WHERE d.created_at > NOW() - INTERVAL '30 days') as recent_documents,
    SUM(d.file_size_bytes) as total_storage_bytes,
    COUNT(DISTINCT u.id) as total_users,
    COUNT(DISTINCT u.id) FILTER (WHERE u.last_login > NOW() - INTERVAL '7 days') as active_users
FROM tenants t
LEFT JOIN documents d ON t.id = d.tenant_id AND d.deleted_at IS NULL
LEFT JOIN users u ON t.id = u.tenant_id AND u.is_active = true
GROUP BY t.id, t.name;

CREATE UNIQUE INDEX ON mv_tenant_statistics(tenant_id);

-- Refresh Job für Materialized View
CREATE OR REPLACE FUNCTION refresh_tenant_statistics()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_tenant_statistics;
END;
$$ LANGUAGE plpgsql;
```

---

## 🐳 Docker Compose

### infrastructure/docker/docker-compose.yml

```yaml
version: '3.8'

services:
  # FastAPI Gateway
  api:
    build:
      context: ../..
      dockerfile: infrastructure/docker/Dockerfile
    container_name: ablage-api
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:${DB_PASSWORD}@postgres:5432/ablage
      - REDIS_URL=redis://redis:6379/0
      - GPU_BACKEND_URL=http://ocr-gpu:8001
      - CPU_BACKEND_URL=http://ocr-cpu:8002
    volumes:
      - uploads:/app/uploads
      - logs:/app/logs
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - ablage-network
    restart: unless-stopped

  # PostgreSQL
  postgres:
    image: postgres:16-alpine
    container_name: ablage-postgres
    environment:
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=${DB_PASSWORD}
      - POSTGRES_DB=ablage
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - ablage-network

  # Redis
  redis:
    image: redis:7-alpine
    container_name: ablage-redis
    command: redis-server --appendonly yes
    volumes:
      - redis-data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - ablage-network

  # Surya/Docling CPU Backend
  ocr-cpu:
    build:
      context: ../../backends/surya_docling
      dockerfile: Dockerfile
    container_name: ablage-ocr-cpu
    environment:
      - TORCH_DEVICE=cpu
      - RECOGNITION_BATCH_SIZE=4
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8002/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - ablage-network

volumes:
  postgres-data:
  redis-data:
  uploads:
  logs:

networks:
  ablage-network:
    driver: bridge
```

### infrastructure/docker/docker-compose.gpu.yml

```yaml
version: '3.8'

services:
  # DeepSeek Janus Pro GPU Backend
  ocr-janus:
    build:
      context: ../../backends/deepseek_janus
      dockerfile: Dockerfile
    container_name: ablage-janus
    ports:
      - "8001:8000"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ['0']
              capabilities: [gpu]
        limits:
          memory: 32G
    environment:
      - MODEL_NAME=deepseek-ai/Janus-Pro-7B
      - CUDA_VISIBLE_DEVICES=0
    volumes:
      - huggingface-cache:/root/.cache/huggingface
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 60s
      timeout: 30s
      retries: 3
      start_period: 120s
    networks:
      - ablage-network

  # GOT-OCR 2.0 GPU Backend
  ocr-got:
    build:
      context: ../../backends/got_ocr
      dockerfile: Dockerfile
    container_name: ablage-got-ocr
    ports:
      - "8003:8000"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ['1']
              capabilities: [gpu]
        limits:
          memory: 16G
    environment:
      - MODEL_NAME=stepfun-ai/GOT-OCR-2.0-hf
      - CUDA_VISIBLE_DEVICES=0
    volumes:
      - huggingface-cache:/root/.cache/huggingface
    networks:
      - ablage-network

volumes:
  huggingface-cache:
```

---

## 📈 Monitoring

### monitoring/prometheus/prometheus.yml

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

alerting:
  alertmanagers:
    - static_configs:
        - targets: ['alertmanager:9093']

rule_files:
  - '/etc/prometheus/rules/*.yml'

scrape_configs:
  - job_name: 'ablage-api'
    metrics_path: /metrics
    static_configs:
      - targets: ['api:8000']

  - job_name: 'ocr-backends'
    static_configs:
      - targets: ['ocr-cpu:8002', 'ocr-janus:8001', 'ocr-got:8003']

  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres-exporter:9187']

  - job_name: 'redis'
    static_configs:
      - targets: ['redis-exporter:9121']
```

### monitoring/prometheus/rules/alerts.yml

```yaml
groups:
  - name: ablage-alerts
    rules:
      - alert: OCRBackendDown
        expr: up{job=~"ocr-.*"} == 0
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "OCR Backend {{ $labels.instance }} ist offline"

      - alert: HighOCRLatency
        expr: histogram_quantile(0.99, sum(rate(ocr_processing_duration_seconds_bucket[5m])) by (le, backend)) > 10
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Hohe OCR-Latenz bei {{ $labels.backend }}"

      - alert: HighErrorRate
        expr: sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Fehlerrate über 5%"

      - alert: GPUMemoryHigh
        expr: nvidia_gpu_memory_used_bytes / nvidia_gpu_memory_total_bytes > 0.9
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "GPU-Speicher über 90%"
```

---

## 🧪 Testing

### pyproject.toml (Testing-Sektion)

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = [
    "-vvv",
    "--strict-markers",
    "--cov=app",
    "--cov-report=term-missing",
    "--cov-fail-under=80",
]
markers = [
    "unit: Unit tests",
    "integration: Integration tests",
    "e2e: End-to-end tests",
    "slow: Slow tests",
]

[tool.coverage.run]
source = ["app"]
branch = true
omit = ["*/tests/*", "*/__pycache__/*"]

[tool.mypy]
python_version = "3.11"
strict = true
plugins = ["pydantic.mypy"]

[tool.ruff]
target-version = "py311"
line-length = 88
select = ["E", "F", "W", "I", "N", "UP", "B", "C4"]
```

### tests/conftest.py

```python
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.main import app
from app.database import Base, get_db

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(bind=test_engine, class_=AsyncSession)

@pytest.fixture(scope="function")
async def db_session():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture(scope="function")
async def async_client(db_session):
    async def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()

@pytest.fixture
def sample_german_text():
    return "Rechnungsnummer: RE-2024-001\nBetrag: 1.234,56 €\nDatum: 15.11.2024"
```

---

## 🔐 Sicherheit und DSGVO

### app/utils/gdpr_anonymizer.py

```python
"""DSGVO-konforme Anonymisierung für Dokumente."""
from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig
import logging

logger = logging.getLogger(__name__)

class GDPRAnonymizer:
    """Anonymisiert PII in deutschen Dokumenten."""

    def __init__(self):
        self.analyzer = AnalyzerEngine()
        self.anonymizer = AnonymizerEngine()
        self._add_german_recognizers()

    def _add_german_recognizers(self):
        iban_pattern = Pattern(
            name="german_iban",
            regex=r"DE\s?[0-9]{2}\s?(?:[0-9]{4}\s?){4}[0-9]{2}",
            score=0.9
        )
        self.analyzer.registry.add_recognizer(
            PatternRecognizer(
                supported_entity="DE_IBAN",
                patterns=[iban_pattern],
                supported_language="de"
            )
        )

    def anonymize(self, text: str) -> str:
        results = self.analyzer.analyze(
            text=text,
            language="de",
            entities=["PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS", "DE_IBAN"]
        )
        anonymized = self.anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators={
                "PERSON": OperatorConfig("replace", {"new_value": "[NAME]"}),
                "PHONE_NUMBER": OperatorConfig("mask", {"chars_to_mask": 6, "masking_char": "*"}),
                "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "[EMAIL]"}),
                "DE_IBAN": OperatorConfig("mask", {"chars_to_mask": 14, "masking_char": "X"}),
            }
        )
        return anonymized.text
```

---

## 📦 Dependencies

### requirements.txt

```
# Core Framework
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
pydantic>=2.0.0
pydantic-settings>=2.0.0

# Database
sqlalchemy[asyncio]>=2.0.0
asyncpg>=0.29.0
alembic>=1.13.0
redis>=5.0.0

# OCR Backends
transformers>=4.40.0
torch>=2.2.0
Pillow>=10.0.0
surya-ocr>=0.6.0
docling>=2.0.0
pytesseract>=0.3.10

# German NLP
presidio-analyzer>=2.2.0
presidio-anonymizer>=2.2.0
babel>=2.14.0

# Monitoring
prometheus-client>=0.20.0
structlog>=24.0.0

# Testing
pytest>=8.0.0
pytest-asyncio>=0.24.0
pytest-cov>=5.0.0
httpx>=0.27.0

# Development
ruff>=0.4.0
mypy>=1.10.0
pre-commit>=3.7.0
```

---

## 🚀 Quick Start

```bash
# 1. Repository klonen
git clone https://github.com/DieBurgerSouce/Ablage-System.git
cd Ablage-System

# 2. Virtuelle Umgebung erstellen
python -m venv .venv
source .venv/bin/activate

# 3. Dependencies installieren
pip install -r requirements.txt
pip install -e ".[dev]"

# 4. Umgebungsvariablen konfigurieren
cp .env.example .env
# .env editieren und Werte setzen

# 5. Pre-commit Hooks installieren
pre-commit install

# 6. Datenbank migrieren
alembic upgrade head

# 7. Development Server starten
make dev  # oder: uvicorn app.main:app --reload

# 8. Mit GPU-Backends (optional)
docker compose -f infrastructure/docker/docker-compose.yml \
               -f infrastructure/docker/docker-compose.gpu.yml up -d
```

---

## 📝 Zusammenfassung

Dieses Initial_Prompt.md Dokument bietet eine vollständige Blaupause für das Ablage-System mit:

- **Multi-Backend OCR-Architektur** (DeepSeek-Janus-Pro, GOT-OCR 2.0, Surya+Docling)
- **Intelligentes Backend-Routing** basierend auf Dokumenteigenschaften
- **Deutsche Sprachoptimierung** (Umlaute, DIN 5008, XRechnung/ZUGFeRD)
- **DSGVO-Compliance** (Anonymisierung, Audit-Logging)
- **Claude Code Integration** (CLAUDE.md, MCP-Server, Hooks)
- **Vollständige DevOps-Pipeline** (Docker, CI/CD, Monitoring)
- **Umfassende Testing-Strategie** (Unit, Integration, E2E)

Das System ist so konzipiert, dass es nahtlos mit Claude Code zusammenarbeitet und eine produktionsreife Dokumentenverarbeitungsplattform für deutsche Geschäftsdokumente bereitstellt.
