# Deployment Gotchas
## Docker, CUDA, Permissions, and Production Issues

**Last Updated**: 2025-01-22
**Contributors**: DevOps Team
**Status**: Living Document

---

## Executive Summary

This document captures non-obvious deployment issues discovered during Ablage-System setup. These are the "gotchas" that cost hours of debugging and aren't in official documentation.

**Top 3 Issues**:
1. Docker GPU passthrough requires `--gpus all` flag **AND** nvidia-docker2
2. File permissions mismatch between host and container causes "permission denied"
3. CUDA version mismatch between host driver and container PyTorch

---

## Issue #1: Docker GPU Passthrough Not Working

### Symptom
```bash
docker run my-ocr-app
# Inside container:
python3 -c "import torch; print(torch.cuda.is_available())"
# Output: False  ❌
```

### Root Cause (Multiple)

**Cause A: Missing `--gpus` flag**
```bash
# ❌ WRONG: GPU not passed to container
docker run -it my-ocr-app

# ✅ CORRECT: Pass GPU to container
docker run --gpus all -it my-ocr-app
```

**Cause B: nvidia-docker2 not installed**
```bash
# Check if nvidia-docker2 installed
dpkg -l | grep nvidia-docker

# If not found, install:
sudo apt install -y nvidia-docker2
sudo systemctl restart docker
```

**Cause C: Docker daemon not configured for nvidia runtime**
```json
// /etc/docker/daemon.json
{
  "runtimes": {
    "nvidia": {
      "path": "nvidia-container-runtime",
      "runtimeArgs": []
    }
  },
  "default-runtime": "nvidia"  // <-- ADD THIS
}
```

### Solution Checklist
- [ ] nvidia-docker2 installed
- [ ] Docker daemon restarted after installation
- [ ] `/etc/docker/daemon.json` configured with nvidia runtime
- [ ] `--gpus all` flag used in `docker run` command
- [ ] `nvidia-smi` works inside container

### Verification
```bash
# Test GPU access in container
docker run --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi

# Should show:
# +-----------------------------------------------------------------------------+
# | NVIDIA-SMI 535.xx       Driver Version: 535.xx       CUDA Version: 12.2    |
# ...
```

---

## Issue #2: File Permission Denied in Container

### Symptom
```bash
# In Docker container
python app/main.py

# Error:
# PermissionError: [Errno 13] Permission denied: '/app/uploads/document.pdf'
```

### Root Cause
Docker container runs as root (UID=0), but mounted volume files owned by host user (UID=1000)

### Understanding UIDs
```bash
# Host machine
id
# Output: uid=1000(benfi) gid=1000(benfi) groups=1000(benfi)

# Inside Docker container (default)
id
# Output: uid=0(root) gid=0(root)

# File created by container has UID=0
# Host user (UID=1000) cannot access it!
```

### Solution: Match UIDs

**Option 1: Run container as host user**
```bash
# Get host UID
HOST_UID=$(id -u)
HOST_GID=$(id -g)

# Run container with host user
docker run --user $HOST_UID:$HOST_GID \
  --gpus all \
  -v $(pwd)/uploads:/app/uploads \
  my-ocr-app
```

**Option 2: Dockerfile with matching UID**
```dockerfile
FROM python:3.11-slim

# Create user with same UID as host
ARG USER_ID=1000
ARG GROUP_ID=1000

RUN groupadd -g ${GROUP_ID} appuser && \
    useradd -m -u ${USER_ID} -g appuser appuser

# Set ownership
COPY --chown=appuser:appuser . /app

# Switch to non-root user
USER appuser

WORKDIR /app
CMD ["python", "app/main.py"]
```

**Build with host UID**:
```bash
docker build \
  --build-arg USER_ID=$(id -u) \
  --build-arg GROUP_ID=$(id -g) \
  -t my-ocr-app .
```

**Option 3: Fix permissions at runtime (hacky)**
```bash
# In entrypoint.sh
#!/bin/bash
chown -R $(id -u):$(id -g) /app/uploads
exec python app/main.py
```

---

## Issue #3: CUDA Version Mismatch

### Symptom
```python
import torch
torch.cuda.is_available()
# False  ❌

# Or:
# RuntimeError: CUDA driver version is insufficient for CUDA runtime version
```

### Root Cause
PyTorch compiled for CUDA 12.1, but host has CUDA 11.8 driver

### Check Versions
```bash
# Host CUDA version
nvidia-smi
# Look for "CUDA Version: 11.8"

# PyTorch CUDA version
python3 -c "import torch; print(torch.version.cuda)"
# Output: 12.1
```

### Solution: Match Versions

**Option 1: Update host CUDA drivers**
```bash
# Install CUDA 12.1 drivers
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.0-1_all.deb
sudo dpkg -i cuda-keyring_1.0-1_all.deb
sudo apt update
sudo apt install cuda-12-1

# Verify
nvidia-smi  # Should show CUDA Version: 12.1
```

**Option 2: Install matching PyTorch version**
```bash
# If host has CUDA 11.8, install PyTorch for CUDA 11.8
pip uninstall torch torchvision torchaudio
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

**Version Matrix**:
| Host CUDA | PyTorch Index URL |
|-----------|-------------------|
| 11.8 | `https://download.pytorch.org/whl/cu118` |
| 12.1 | `https://download.pytorch.org/whl/cu121` |
| CPU only | `https://download.pytorch.org/whl/cpu` |

---

## Issue #4: Port Already in Use

### Symptom
```bash
uvicorn app.main:app --port 8000
# Error: [Errno 98] Address already in use
```

### Root Cause
Previous process still running or zombie process on port 8000

### Solution
```bash
# Find process using port 8000
lsof -i :8000

# Output:
# COMMAND   PID   USER   FD   TYPE DEVICE SIZE/OFF NODE NAME
# python  12345  user    3u  IPv4 123456      0t0  TCP *:8000 (LISTEN)

# Kill process
kill -9 12345

# Or kill all Python processes (dangerous!)
pkill -f "uvicorn"
```

**Better: Use systemd**
```bash
# /etc/systemd/system/ablage-backend.service
[Unit]
Description=Ablage System Backend
After=network.target

[Service]
Type=simple
User=appuser
WorkingDirectory=/opt/ablage-system
ExecStart=/opt/ablage-system/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

---

## Issue #5: Environment Variables Not Loaded

### Symptom
```python
import os
DATABASE_URL = os.getenv("DATABASE_URL")
print(DATABASE_URL)
# Output: None  ❌
```

### Root Cause
`.env` file not loaded or Docker environment variables not passed

### Solution

**For Docker Compose**:
```yaml
# docker-compose.yml
services:
  backend:
    build: .
    env_file:
      - .env  # Load .env file
    environment:
      - DATABASE_URL=${DATABASE_URL}  # Pass specific vars
```

**For Docker Run**:
```bash
# Pass .env file
docker run --env-file .env my-ocr-app

# Or pass individual vars
docker run \
  -e DATABASE_URL=postgresql://... \
  -e REDIS_URL=redis://... \
  my-ocr-app
```

**For Python (development)**:
```python
# Load .env in code (development only!)
from dotenv import load_dotenv
load_dotenv()  # Loads .env file

DATABASE_URL = os.getenv("DATABASE_URL")
```

---

## Issue #6: Model Files Not Found in Container

### Symptom
```python
from transformers import AutoModel
model = AutoModel.from_pretrained("deepseek-ai/deepseek-janus-pro-1.0")

# Error:
# OSError: Model deepseek-ai/deepseek-janus-pro-1.0 not found
```

### Root Cause
Hugging Face cache not mounted or models not downloaded

### Solution

**Mount Hugging Face cache**:
```bash
# Host cache location
~/.cache/huggingface/

# Mount in Docker
docker run \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  my-ocr-app
```

**Or download models during build**:
```dockerfile
# Dockerfile
FROM python:3.11-slim

# Install dependencies
RUN pip install transformers torch

# Download models at build time
RUN python -c "from transformers import AutoModel; \
               AutoModel.from_pretrained('deepseek-ai/deepseek-janus-pro-1.0')"

# Now model is baked into image (increases image size by ~12GB!)
```

**Trade-offs**:
- **Mounted cache**: Faster builds, shared across containers, but requires host setup
- **Baked into image**: Slower builds, larger image (20GB+), but container is self-contained

---

## Issue #7: Celery Workers Not Processing Tasks

### Symptom
```bash
# Task queued but never processed
celery -A app.celery worker --loglevel=info

# Worker shows: "ready" but no tasks executed
```

### Root Cause (Multiple)

**Cause A: Redis not accessible**
```bash
# Test Redis connection
redis-cli ping
# Should return: PONG
```

**Cause B: Wrong broker URL**
```python
# app/celery.py
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")

# If Redis in Docker: use service name!
# ❌ WRONG: redis://localhost:6379/0
# ✅ CORRECT: redis://redis:6379/0  (if service named "redis")
```

**Cause C: Task not registered**
```python
# Must import tasks for Celery to discover them
from app.workers import celery_app

# Import all task modules
from app.workers import ocr_tasks  # <-- MUST import!
```

**Cause D: Firewall blocking Redis port**
```bash
# Check if port 6379 open
telnet redis-server 6379

# If timeout, check firewall
sudo ufw status
sudo ufw allow 6379/tcp
```

---

## Deployment Checklist

### Pre-Deployment
- [ ] GPU drivers installed (nvidia-driver-535+)
- [ ] Docker + nvidia-docker2 installed
- [ ] CUDA versions match (host driver ≥ PyTorch CUDA)
- [ ] `.env` file configured
- [ ] Ports available (8000, 6379, 5432, 9000)

### Docker Setup
- [ ] `--gpus all` flag used
- [ ] User UID matches host (avoid permission issues)
- [ ] Volumes mounted (`/app/uploads`, HuggingFace cache)
- [ ] Environment variables passed (`--env-file .env`)
- [ ] Health checks configured

### Verification
- [ ] `nvidia-smi` works in container
- [ ] `torch.cuda.is_available()` returns `True`
- [ ] API responds: `curl http://localhost:8000/health`
- [ ] Redis accessible: `redis-cli ping`
- [ ] Database connects: `psql $DATABASE_URL`
- [ ] Celery worker processes tasks

---

## Quick Troubleshooting Commands

```bash
# GPU
nvidia-smi                              # Check GPU status
docker run --gpus all nvidia/cuda:12.1-base nvidia-smi  # Test GPU in Docker

# Permissions
ls -la /path/to/file                    # Check file ownership
id                                       # Check current user UID

# Ports
lsof -i :8000                           # Check what's using port 8000
netstat -tlnp | grep 8000               # Alternative port check

# Docker
docker ps -a                            # List all containers
docker logs <container_id>              # Check container logs
docker exec -it <container_id> bash     # Enter container shell

# Redis
redis-cli ping                          # Test Redis connection
redis-cli monitor                       # Watch Redis commands

# Database
psql $DATABASE_URL -c "SELECT 1"        # Test database connection

# Python environment
python3 -c "import torch; print(torch.cuda.is_available())"  # CUDA check
python3 -c "import sys; print(sys.path)"  # Check Python path
```

---

## References

- [NVIDIA Docker Documentation](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
- [Static_Knowledge/SOPs/001_installing_ocr_backends.md](../../Static_Knowledge/SOPs/001_installing_ocr_backends.md) - Backend installation
- [docker-compose.yml](../../docker-compose.yml) - Multi-service setup

---

**Key Takeaway**: Most deployment issues come from mismatched UIDs, CUDA versions, or missing Docker flags. Always verify GPU access, file permissions, and service connectivity before debugging application code.
