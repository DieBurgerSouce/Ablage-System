# IDE Setup Guide

> **Ablage-System - IDE-Konfiguration**
> Version: 1.0 | Stand: Januar 2025

---

## Übersicht

Dieses Dokument beschreibt die optimale IDE-Konfiguration für die Entwicklung am Ablage-System. Wir unterstützen:

- **VS Code** (empfohlen)
- **PyCharm Professional**
- **Neovim**

---

## VS Code (Empfohlen)

### Extensions installieren

#### Erforderlich

```bash
# Python
code --install-extension ms-python.python
code --install-extension ms-python.vscode-pylance
code --install-extension ms-python.debugpy

# TypeScript/React
code --install-extension esbenp.prettier-vscode
code --install-extension dbaeumer.vscode-eslint

# Docker
code --install-extension ms-azuretools.vscode-docker

# Git
code --install-extension eamodio.gitlens
```

#### Empfohlen

```bash
# Produktivität
code --install-extension christian-kohler.path-intellisense
code --install-extension formulahendry.auto-rename-tag
code --install-extension bradlc.vscode-tailwindcss

# Code-Qualität
code --install-extension charliermarsh.ruff
code --install-extension ms-python.mypy-type-checker

# Datenbank
code --install-extension cweijan.vscode-postgresql-client2

# Markdown
code --install-extension yzhang.markdown-all-in-one

# AI-Assistenz
code --install-extension anthropic.claude-code
```

### Workspace Settings

Erstellen Sie `.vscode/settings.json`:

```json
{
    // Python
    "python.defaultInterpreterPath": "${workspaceFolder}/venv/bin/python",
    "python.analysis.typeCheckingMode": "strict",
    "python.analysis.autoImportCompletions": true,
    "python.analysis.inlayHints.functionReturnTypes": true,
    "python.analysis.inlayHints.variableTypes": true,

    // Ruff (Linting + Formatting)
    "[python]": {
        "editor.formatOnSave": true,
        "editor.codeActionsOnSave": {
            "source.fixAll.ruff": "explicit",
            "source.organizeImports.ruff": "explicit"
        },
        "editor.defaultFormatter": "charliermarsh.ruff"
    },
    "ruff.lint.args": ["--config=pyproject.toml"],

    // mypy
    "mypy.runUsingActiveInterpreter": true,
    "mypy.configFile": "pyproject.toml",

    // TypeScript/React
    "[typescript]": {
        "editor.formatOnSave": true,
        "editor.defaultFormatter": "esbenp.prettier-vscode"
    },
    "[typescriptreact]": {
        "editor.formatOnSave": true,
        "editor.defaultFormatter": "esbenp.prettier-vscode"
    },
    "[javascript]": {
        "editor.formatOnSave": true,
        "editor.defaultFormatter": "esbenp.prettier-vscode"
    },

    // ESLint
    "eslint.validate": [
        "javascript",
        "javascriptreact",
        "typescript",
        "typescriptreact"
    ],

    // Tailwind CSS
    "tailwindCSS.experimental.classRegex": [
        ["cva\\(([^)]*)\\)", "[\"'`]([^\"'`]*).*?[\"'`]"]
    ],

    // Editor
    "editor.rulers": [100],
    "editor.tabSize": 4,
    "editor.insertSpaces": true,
    "editor.wordWrap": "on",
    "editor.bracketPairColorization.enabled": true,
    "editor.guides.bracketPairs": true,

    // Files
    "files.trimTrailingWhitespace": true,
    "files.insertFinalNewline": true,
    "files.exclude": {
        "**/__pycache__": true,
        "**/.pytest_cache": true,
        "**/.mypy_cache": true,
        "**/node_modules": true,
        "**/.git": true,
        "**/venv": true
    },

    // Terminal
    "terminal.integrated.defaultProfile.linux": "bash",
    "terminal.integrated.cwd": "${workspaceFolder}",

    // Search
    "search.exclude": {
        "**/node_modules": true,
        "**/venv": true,
        "**/__pycache__": true,
        "**/dist": true
    },

    // Docker
    "docker.environment": {
        "COMPOSE_PROJECT_NAME": "ablage"
    }
}
```

### Debug-Konfiguration

Erstellen Sie `.vscode/launch.json`:

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Python: FastAPI Backend",
            "type": "debugpy",
            "request": "launch",
            "module": "uvicorn",
            "args": [
                "app.main:app",
                "--reload",
                "--host", "0.0.0.0",
                "--port", "8000"
            ],
            "jinja": true,
            "env": {
                "PYTHONPATH": "${workspaceFolder}"
            },
            "cwd": "${workspaceFolder}"
        },
        {
            "name": "Python: Celery Worker",
            "type": "debugpy",
            "request": "launch",
            "module": "celery",
            "args": [
                "-A", "app.workers.celery_app",
                "worker",
                "--loglevel=debug",
                "--pool=solo"
            ],
            "env": {
                "PYTHONPATH": "${workspaceFolder}"
            },
            "cwd": "${workspaceFolder}"
        },
        {
            "name": "Python: Current File",
            "type": "debugpy",
            "request": "launch",
            "program": "${file}",
            "console": "integratedTerminal",
            "env": {
                "PYTHONPATH": "${workspaceFolder}"
            }
        },
        {
            "name": "Python: pytest",
            "type": "debugpy",
            "request": "launch",
            "module": "pytest",
            "args": [
                "-v",
                "-s",
                "${file}"
            ],
            "cwd": "${workspaceFolder}"
        },
        {
            "name": "Docker: Backend Remote Debug",
            "type": "debugpy",
            "request": "attach",
            "connect": {
                "host": "localhost",
                "port": 5678
            },
            "pathMappings": [
                {
                    "localRoot": "${workspaceFolder}",
                    "remoteRoot": "/app"
                }
            ]
        },
        {
            "name": "Chrome: Frontend",
            "type": "chrome",
            "request": "launch",
            "url": "http://localhost:5173",
            "webRoot": "${workspaceFolder}/frontend/src"
        }
    ],
    "compounds": [
        {
            "name": "Full Stack Debug",
            "configurations": [
                "Python: FastAPI Backend",
                "Chrome: Frontend"
            ]
        }
    ]
}
```

### Tasks

Erstellen Sie `.vscode/tasks.json`:

```json
{
    "version": "2.0.0",
    "tasks": [
        {
            "label": "Docker: Start All",
            "type": "shell",
            "command": "docker-compose up -d",
            "group": "build",
            "presentation": {
                "reveal": "always",
                "panel": "new"
            }
        },
        {
            "label": "Docker: Stop All",
            "type": "shell",
            "command": "docker-compose down",
            "group": "build"
        },
        {
            "label": "Docker: Rebuild Backend",
            "type": "shell",
            "command": "docker-compose build backend && docker-compose up -d backend",
            "group": "build"
        },
        {
            "label": "Docker: Rebuild Frontend",
            "type": "shell",
            "command": "docker-compose build frontend && docker-compose up -d frontend",
            "group": "build"
        },
        {
            "label": "Docker: Logs Backend",
            "type": "shell",
            "command": "docker-compose logs -f backend",
            "isBackground": true
        },
        {
            "label": "Docker: Logs Worker",
            "type": "shell",
            "command": "docker-compose logs -f worker",
            "isBackground": true
        },
        {
            "label": "Python: Run Tests",
            "type": "shell",
            "command": "${workspaceFolder}/venv/bin/pytest",
            "args": ["-v", "--tb=short"],
            "group": {
                "kind": "test",
                "isDefault": true
            },
            "problemMatcher": "$pytest"
        },
        {
            "label": "Python: Run Tests with Coverage",
            "type": "shell",
            "command": "${workspaceFolder}/venv/bin/pytest",
            "args": [
                "--cov=app",
                "--cov-report=html",
                "--cov-report=term"
            ],
            "group": "test"
        },
        {
            "label": "Python: Type Check",
            "type": "shell",
            "command": "${workspaceFolder}/venv/bin/mypy",
            "args": ["app/"],
            "group": "build",
            "problemMatcher": "$mypy"
        },
        {
            "label": "Python: Lint",
            "type": "shell",
            "command": "${workspaceFolder}/venv/bin/ruff",
            "args": ["check", "."],
            "group": "build"
        },
        {
            "label": "Alembic: Migrate",
            "type": "shell",
            "command": "docker-compose exec backend alembic upgrade head",
            "group": "build"
        },
        {
            "label": "Alembic: Create Migration",
            "type": "shell",
            "command": "docker-compose exec backend alembic revision --autogenerate -m",
            "args": ["${input:migrationName}"],
            "group": "build"
        },
        {
            "label": "Frontend: Dev Server",
            "type": "shell",
            "command": "npm run dev",
            "options": {
                "cwd": "${workspaceFolder}/frontend"
            },
            "isBackground": true
        },
        {
            "label": "Frontend: Build",
            "type": "shell",
            "command": "npm run build",
            "options": {
                "cwd": "${workspaceFolder}/frontend"
            },
            "group": "build"
        },
        {
            "label": "Frontend: Type Check",
            "type": "shell",
            "command": "npm run type-check",
            "options": {
                "cwd": "${workspaceFolder}/frontend"
            },
            "group": "build"
        }
    ],
    "inputs": [
        {
            "id": "migrationName",
            "type": "promptString",
            "description": "Migration Name (z.B. add_user_table)"
        }
    ]
}
```

### Keyboard Shortcuts

Empfohlene Shortcuts (`.vscode/keybindings.json`):

```json
[
    {
        "key": "ctrl+shift+t",
        "command": "workbench.action.tasks.runTask",
        "args": "Python: Run Tests"
    },
    {
        "key": "ctrl+shift+d",
        "command": "workbench.action.tasks.runTask",
        "args": "Docker: Start All"
    },
    {
        "key": "ctrl+shift+l",
        "command": "workbench.action.tasks.runTask",
        "args": "Docker: Logs Backend"
    }
]
```

---

## PyCharm Professional

### Projekt konfigurieren

1. **Öffnen**: File → Open → Ablage-System Verzeichnis wählen

2. **Python Interpreter**:
   - Settings → Project → Python Interpreter
   - Add Interpreter → Existing → `venv/bin/python`

3. **Docker Integration**:
   - Settings → Build, Execution, Deployment → Docker
   - Docker Desktop / Unix Socket konfigurieren

### Run Configurations

#### FastAPI Backend

```
Name: FastAPI Backend
Script path: <venv>/bin/uvicorn
Parameters: app.main:app --reload --host 0.0.0.0 --port 8000
Working directory: $PROJECT_DIR$
Environment variables: PYTHONPATH=$PROJECT_DIR$
```

#### Celery Worker

```
Name: Celery Worker
Script path: <venv>/bin/celery
Parameters: -A app.workers.celery_app worker --loglevel=debug --pool=solo
Working directory: $PROJECT_DIR$
Environment variables: PYTHONPATH=$PROJECT_DIR$
```

#### pytest

```
Name: All Tests
Script path: <venv>/bin/pytest
Parameters: -v --tb=short
Working directory: $PROJECT_DIR$
```

### Code Style

Settings → Editor → Code Style → Python:

- **Tabs and Indents**: 4 Spaces
- **Line Length**: 100
- **Blank Lines**: PEP 8

Settings → Editor → Inspections:

- Python → Type Checker → mypy (aktivieren)
- Python → Ruff (wenn Plugin installiert)

### Plugins empfohlen

- **Ruff**: Linting und Formatting
- **Docker**: Container-Management
- **.env files support**: Environment-Variablen
- **GitToolBox**: Erweiterte Git-Features
- **Database Navigator**: Datenbank-Zugriff

---

## Neovim

### Voraussetzungen

```bash
# Neovim 0.9+
nvim --version

# Node.js für LSP
node --version

# Python Provider
pip install pynvim
```

### Plugin-Manager (lazy.nvim)

```lua
-- ~/.config/nvim/init.lua
require("config.lazy")
```

```lua
-- ~/.config/nvim/lua/config/lazy.lua
local lazypath = vim.fn.stdpath("data") .. "/lazy/lazy.nvim"
if not vim.loop.fs_stat(lazypath) then
  vim.fn.system({
    "git", "clone", "--filter=blob:none",
    "https://github.com/folke/lazy.nvim.git",
    "--branch=stable", lazypath,
  })
end
vim.opt.rtp:prepend(lazypath)

require("lazy").setup({
  -- LSP
  {
    "neovim/nvim-lspconfig",
    dependencies = {
      "williamboman/mason.nvim",
      "williamboman/mason-lspconfig.nvim",
    },
  },

  -- Completion
  {
    "hrsh7th/nvim-cmp",
    dependencies = {
      "hrsh7th/cmp-nvim-lsp",
      "hrsh7th/cmp-buffer",
      "hrsh7th/cmp-path",
      "L3MON4D3/LuaSnip",
    },
  },

  -- Python
  { "mfussenegger/nvim-dap-python" },

  -- TypeScript
  { "pmizio/typescript-tools.nvim" },

  -- Linting
  { "mfussenegger/nvim-lint" },

  -- Formatting
  { "stevearc/conform.nvim" },

  -- Git
  { "lewis6991/gitsigns.nvim" },
  { "tpope/vim-fugitive" },

  -- File Explorer
  { "nvim-tree/nvim-tree.lua" },

  -- Fuzzy Finder
  {
    "nvim-telescope/telescope.nvim",
    dependencies = { "nvim-lua/plenary.nvim" },
  },

  -- Statusline
  { "nvim-lualine/lualine.nvim" },

  -- Colorscheme
  { "catppuccin/nvim", name = "catppuccin", priority = 1000 },
})
```

### LSP Konfiguration

```lua
-- ~/.config/nvim/lua/config/lsp.lua
local lspconfig = require("lspconfig")

-- Python (Pyright)
lspconfig.pyright.setup({
  settings = {
    python = {
      analysis = {
        typeCheckingMode = "strict",
        autoImportCompletions = true,
      },
    },
  },
})

-- TypeScript
require("typescript-tools").setup({})

-- Ruff (Linting)
lspconfig.ruff_lsp.setup({})
```

### Formatting

```lua
-- ~/.config/nvim/lua/config/conform.lua
require("conform").setup({
  formatters_by_ft = {
    python = { "ruff_format" },
    typescript = { "prettier" },
    typescriptreact = { "prettier" },
    javascript = { "prettier" },
    json = { "prettier" },
    yaml = { "prettier" },
    markdown = { "prettier" },
  },
  format_on_save = {
    timeout_ms = 500,
    lsp_fallback = true,
  },
})
```

### Keymaps

```lua
-- ~/.config/nvim/lua/config/keymaps.lua
local opts = { noremap = true, silent = true }

-- LSP
vim.keymap.set("n", "gd", vim.lsp.buf.definition, opts)
vim.keymap.set("n", "K", vim.lsp.buf.hover, opts)
vim.keymap.set("n", "<leader>rn", vim.lsp.buf.rename, opts)
vim.keymap.set("n", "<leader>ca", vim.lsp.buf.code_action, opts)
vim.keymap.set("n", "<leader>f", function()
  require("conform").format({ async = true })
end, opts)

-- Telescope
vim.keymap.set("n", "<leader>ff", "<cmd>Telescope find_files<cr>", opts)
vim.keymap.set("n", "<leader>fg", "<cmd>Telescope live_grep<cr>", opts)
vim.keymap.set("n", "<leader>fb", "<cmd>Telescope buffers<cr>", opts)

-- Testing (via vim-test oder neotest)
vim.keymap.set("n", "<leader>tt", "<cmd>TestNearest<cr>", opts)
vim.keymap.set("n", "<leader>tf", "<cmd>TestFile<cr>", opts)
```

---

## Remote Development (Docker)

### VS Code Remote Containers

1. Extension installieren: `ms-vscode-remote.remote-containers`

2. `.devcontainer/devcontainer.json` erstellen:

```json
{
    "name": "Ablage-System Dev",
    "dockerComposeFile": ["../docker-compose.yml", "docker-compose.dev.yml"],
    "service": "backend",
    "workspaceFolder": "/app",
    "customizations": {
        "vscode": {
            "extensions": [
                "ms-python.python",
                "ms-python.vscode-pylance",
                "charliermarsh.ruff",
                "esbenp.prettier-vscode"
            ],
            "settings": {
                "python.defaultInterpreterPath": "/usr/local/bin/python"
            }
        }
    },
    "forwardPorts": [8000, 5173, 3002],
    "postCreateCommand": "pip install -e .[dev]"
}
```

3. `.devcontainer/docker-compose.dev.yml`:

```yaml
version: "3.8"
services:
  backend:
    volumes:
      - ..:/app:cached
    environment:
      - DEBUG=true
    ports:
      - "5678:5678"  # Debug Port
```

### Remote Debugging (debugpy)

In Docker Container:

```python
# app/main.py (nur Entwicklung!)
import debugpy
debugpy.listen(("0.0.0.0", 5678))
# debugpy.wait_for_client()  # Optional: Warten auf Debugger
```

Docker Compose:

```yaml
backend:
  ports:
    - "5678:5678"
  command: python -m debugpy --listen 0.0.0.0:5678 -m uvicorn app.main:app --reload
```

---

## Tipps & Tricks

### Python Import Sorting

Ruff erledigt das automatisch bei Save. Manuelle Sortierung:

```bash
ruff check --select I --fix .
```

### Type Stubs installieren

```bash
pip install types-redis types-requests types-Pillow
```

### Datenbankzugriff

**VS Code**: PostgreSQL Explorer Extension
**PyCharm**: Database Tool Window
**CLI**:

```bash
docker-compose exec postgres psql -U ablage_admin -d ablage
```

### GPU-Debugging

```python
import torch
print(f"CUDA available: {torch.cuda.is_available()}")
print(f"GPU: {torch.cuda.get_device_name(0)}")
print(f"Memory: {torch.cuda.memory_allocated() / 1024**3:.2f} GB")
```

### Log-Analyse

```bash
# JSON-Logs formatieren
docker-compose logs backend 2>&1 | jq '.'

# Fehler filtern
docker-compose logs backend 2>&1 | grep '"level":"error"' | jq '.'
```

---

## Troubleshooting

### "Python Interpreter not found"

```bash
# Virtual Environment neu erstellen
rm -rf venv
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

### "Module not found" in IDE

1. Prüfen Sie den Python Interpreter
2. `PYTHONPATH` in Launch-Config setzen
3. IDE Cache löschen und neu indexieren

### LSP langsam

```json
// settings.json
{
    "python.analysis.indexing": true,
    "python.analysis.persistAllIndices": true
}
```

### Docker-Compose Befehle langsam

```bash
# Docker BuildKit aktivieren
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1
```

---

*Letzte Aktualisierung: Januar 2025*
