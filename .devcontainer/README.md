# DevContainer Configuration

This directory contains VS Code DevContainer configuration for the Ablage-System project.

## What is a DevContainer?

A DevContainer allows you to develop inside a Docker container with all dependencies pre-installed and configured. This ensures:

- **Consistency**: Everyone works in the same environment
- **Reproducibility**: No "works on my machine" issues
- **Isolation**: Project dependencies don't interfere with your system
- **Pre-configured**: All tools, extensions, and settings ready to use

## Prerequisites

1. **Docker Desktop** installed and running
2. **VS Code** with the **Dev Containers** extension
3. **NVIDIA Container Toolkit** (for GPU support)
   - Linux: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html
   - Windows: WSL2 + Docker Desktop with GPU support enabled

## Quick Start

### Option 1: Open in Container (Recommended)

1. Open the project folder in VS Code
2. Press `F1` and select **"Dev Containers: Reopen in Container"**
3. Wait for the container to build (first time takes ~10-15 minutes)
4. VS Code will reload inside the container
5. Setup script runs automatically (installs dependencies, sets up database, etc.)

### Option 2: Clone in Container Volume

1. Press `F1` and select **"Dev Containers: Clone Repository in Container Volume..."**
2. Enter the Git repository URL
3. Wait for clone and container build
4. Start developing immediately

## What's Included

### Services

The DevContainer starts multiple services via Docker Compose:

- **app**: Main development container (Python 3.11, CUDA 12.2)
- **postgres**: PostgreSQL 16 database
- **redis**: Redis 7 for caching and queues
- **minio**: MinIO object storage
- **pgadmin**: PostgreSQL web UI (optional)
- **redis-commander**: Redis web UI (optional)
- **flower**: Celery task monitor (optional, profile: monitoring)

### Pre-installed Tools

#### Python Development
- Python 3.11 with CUDA support
- PyTorch 2.1.0 with CUDA 12.1
- All project dependencies from requirements.txt
- Development tools: pytest, mypy, ruff, black, isort, ipdb

#### VS Code Extensions
- Python (Pylance, debugpy, testing)
- Docker
- GitLens
- Database tools (SQLTools)
- YAML/JSON support
- Markdown tools
- German spell checker
- Jupyter notebooks
- REST client

#### System Tools
- Git, GitHub CLI
- Docker CLI
- PostgreSQL client
- Redis CLI
- Zsh with Oh My Zsh
- htop, tmux, jq, tree

### Automatic Setup

The `setup.sh` script runs automatically after container creation and:

1. ✅ Installs Python dependencies
2. ✅ Sets up pre-commit hooks
3. ✅ Configures Git
4. ✅ Creates project directories
5. ✅ Waits for services (PostgreSQL, Redis, MinIO)
6. ✅ Runs database migrations
7. ✅ Checks GPU availability
8. ✅ Creates .env file from template
9. ✅ Sets proper permissions

## Port Forwarding

The following ports are automatically forwarded:

| Port | Service | Auto-Forward |
|------|---------|--------------|
| 8000 | FastAPI API | Notify |
| 5432 | PostgreSQL | Silent |
| 6379 | Redis | Silent |
| 9000 | MinIO API | Silent |
| 9001 | MinIO Console | Open Browser |
| 5050 | pgAdmin | Silent |
| 8081 | Redis Commander | Silent |
| 5555 | Flower (Celery) | Open Browser |

## GPU Support

The DevContainer is configured for GPU acceleration:

- NVIDIA CUDA 12.2 with cuDNN 8
- All GPU devices passed through
- PyTorch with CUDA support pre-installed
- Automatic GPU detection and validation

### Verify GPU

```bash
# Check GPU hardware
nvidia-smi

# Check CUDA in Python
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0)}')"
```

## Working with the DevContainer

### Running the Application

```bash
# Start FastAPI development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Or use the VSCode task: Ctrl+Shift+P → "Tasks: Run Task" → "Start Development Server"
```

### Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=app --cov-report=html

# Specific test file
pytest tests/test_basic.py -v

# GPU tests only
pytest -m gpu -v

# Or use VSCode: Ctrl+Shift+T or the Testing sidebar
```

### Database Operations

```bash
# Run migrations
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "description"

# Connect to PostgreSQL
psql -h postgres -U postgres -d ablage_ocr

# Or use pgAdmin: http://localhost:5050
# Login: dev@ablage.local / devpassword
```

### Redis Operations

```bash
# Connect to Redis CLI
redis-cli -h redis

# Or use Redis Commander: http://localhost:8081
```

### MinIO Operations

```bash
# MinIO Console (web UI): http://localhost:9001
# Login: minioadmin / minioadmin

# List buckets
mc ls local/

# Upload file
mc cp file.pdf local/documents/
```

### Code Quality

```bash
# Lint with Ruff
ruff check .

# Format with Ruff
ruff format .

# Type check with MyPy
mypy app/

# Run pre-commit on all files
pre-commit run --all-files

# Or let pre-commit run automatically on git commit
```

## Debugging

### Debugging Python

1. Set breakpoints in VS Code
2. Press `F5` and select **"Python: FastAPI"** or **"Python: Current File"**
3. Use the debug console and variables panel

### Debugging Tests

1. Set breakpoints in test files
2. Press `F5` and select **"Python: Debug Tests"**
3. Or use the Testing sidebar (beaker icon) → right-click test → "Debug Test"

### Attach to Container

If you need to debug a running process in another container:

1. Press `F5` and select **"Attach to Container: Backend"**
2. Select the container
3. Debug the running process

## Customization

### Modify Extensions

Edit `.devcontainer/devcontainer.json`:

```json
"customizations": {
  "vscode": {
    "extensions": [
      "your.extension-id"
    ]
  }
}
```

### Modify Settings

Edit `.devcontainer/devcontainer.json`:

```json
"customizations": {
  "vscode": {
    "settings": {
      "your.setting": "value"
    }
  }
}
```

### Add Services

Edit `.devcontainer/docker-compose.yml`:

```yaml
services:
  your-service:
    image: your-image:tag
    ports:
      - "8080:8080"
    networks:
      - ablage-dev-network
```

## Troubleshooting

### Container Won't Start

1. Check Docker Desktop is running
2. Check Docker has enough resources (Memory: 8GB+, CPU: 4+)
3. View logs: `F1` → "Dev Containers: Show Container Log"
4. Rebuild: `F1` → "Dev Containers: Rebuild Container"

### GPU Not Detected

```bash
# Check NVIDIA Container Toolkit
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi

# Check Docker GPU support
docker info | grep -i gpu

# Windows: Ensure WSL2 GPU support is enabled in Docker Desktop
```

### Database Connection Issues

```bash
# Check PostgreSQL is running
docker ps | grep postgres

# Check PostgreSQL logs
docker logs ablage-postgres-dev

# Test connection manually
psql -h postgres -U postgres -d ablage_ocr
```

### Services Not Ready

The setup script waits for services, but if they're still not ready:

```bash
# Manually wait for PostgreSQL
until PGPASSWORD=postgres psql -h postgres -U postgres -d ablage_ocr -c '\q'; do sleep 1; done

# Manually wait for Redis
until redis-cli -h redis ping | grep PONG; do sleep 1; done

# Manually wait for MinIO
until curl -sf http://minio:9000/minio/health/live; do sleep 1; done
```

### Slow Performance

1. Allocate more resources in Docker Desktop
2. Use Docker volumes instead of bind mounts for node_modules (if applicable)
3. Disable unnecessary services in docker-compose.yml
4. Use a local Docker registry for faster image pulls

### Pre-commit Hooks Fail

```bash
# Update hooks
pre-commit autoupdate

# Clear cache and reinstall
pre-commit clean
pre-commit install --install-hooks
```

## Best Practices

1. **Commit .devcontainer to Git**: Ensures everyone has the same setup
2. **Keep .env out of Git**: Use .env.example as a template
3. **Document Custom Changes**: Update this README if you modify the DevContainer
4. **Use VSCode Tasks**: Leverage tasks.json for common operations
5. **Leverage Extensions**: Use installed extensions (GitLens, Testing, etc.)
6. **Use GPU Wisely**: Monitor VRAM usage (nvidia-smi)
7. **Regular Updates**: Rebuild container periodically for updates

## Performance Tips

- **Use .dockerignore**: Exclude unnecessary files from build context
- **Layer Caching**: Order Dockerfile commands from least to most frequently changing
- **Multi-stage Builds**: If applicable, use multi-stage builds
- **Volume Mounts**: Use named volumes for better performance than bind mounts
- **Resource Limits**: Set appropriate CPU/memory limits in docker-compose.yml

## Security Considerations

- ⚠️ **Never commit secrets to .env** (use .env.example)
- ⚠️ **Change default passwords** (PostgreSQL, MinIO, pgAdmin) for production
- ⚠️ **Use secrets management** for production deployments
- ⚠️ **Keep images updated** (rebuild regularly)
- ⚠️ **Review extensions** before installing (only use trusted sources)

## Additional Resources

- [VS Code DevContainers Documentation](https://code.visualstudio.com/docs/devcontainers/containers)
- [Docker Documentation](https://docs.docker.com/)
- [NVIDIA Container Toolkit](https://github.com/NVIDIA/nvidia-container-toolkit)
- [Project Documentation](../README.md)
- [Claude Code Essentials](../.claude/quick-reference/claude-code-essentials.md)

## Getting Help

If you encounter issues:

1. Check this README troubleshooting section
2. Review DevContainer logs: `F1` → "Dev Containers: Show Container Log"
3. Check Docker Desktop logs
4. Search project documentation: `.claude/Docs/`
5. Use `/find-doc` slash command in Claude Code
6. Open an issue using the bug report template

---

**Happy Coding! 🚀**

*"Feinpoliert und durchdacht"* - Every detail matters.
