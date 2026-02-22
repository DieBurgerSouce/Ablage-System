# GPU-enabled Docker image for Ablage-System OCR
# Multi-stage build: builder installs/compiles, production keeps only runtime artifacts
# Security-hardened with non-root user

# ============================================================
# Stage 1: builder
# All build tools, compilers, and pip/uv live here only.
# ============================================================
FROM nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive
ENV TORCH_CUDA_ARCH_LIST="8.6;8.9"

# Install build + runtime-needed system packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-dev \
    python3-pip \
    build-essential \
    libhunspell-dev \
    git \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Set Python 3.11 as default
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# Install uv for fast dependency resolution (10-100x faster than pip)
RUN python3.11 -m pip install --no-cache-dir --upgrade pip setuptools wheel uv

# Copy requirements and install Python dependencies
COPY requirements.txt requirements-gpu.txt ./
RUN uv pip install --system -r requirements.txt
RUN uv pip install --system -r requirements-gpu.txt

# Clone and register DeepSeek Janus
RUN git clone --depth 1 https://github.com/deepseek-ai/Janus.git /opt/janus && \
    uv pip install --system attrdict einops sentencepiece timm accelerate && \
    echo "/opt/janus" > /usr/local/lib/python3.11/dist-packages/janus.pth && \
    python3.11 -c "from janus.models import MultiModalityCausalLM, VLChatProcessor; print('Janus OK')"

# ============================================================
# Stage 2: production
# Only runtime packages; no build tools, no git, no uv/pip.
# curl is kept for the HEALTHCHECK.
# ============================================================
FROM nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV TORCH_CUDA_ARCH_LIST="8.6;8.9"
ENV CUDA_VISIBLE_DEVICES=0

# Install ONLY runtime system dependencies (+ curl for HEALTHCHECK)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    curl \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libpoppler-cpp-dev \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-deu \
    fonts-dejavu-core \
    libhunspell-dev \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Set Python 3.11 as default
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# Copy installed Python packages from builder
COPY --from=builder /usr/local/lib/python3.11/dist-packages/ /usr/local/lib/python3.11/dist-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copy Janus source tree and its .pth registration file
COPY --from=builder /opt/janus /opt/janus
# The .pth file is already inside dist-packages (copied above), but copy explicitly to be safe
COPY --from=builder /usr/local/lib/python3.11/dist-packages/janus.pth /usr/local/lib/python3.11/dist-packages/janus.pth

# Create non-root user BEFORE copying files
ARG UID=1000
ARG GID=1000
RUN groupadd -g ${GID} ablage && \
    useradd -m -u ${UID} -g ${GID} -s /bin/bash ablage

# Create app directory with correct ownership
WORKDIR /app
RUN mkdir -p /app/uploads /app/outputs /app/logs /app/cache && \
    chown -R ablage:ablage /app

# Copy application code with correct ownership
COPY --chown=ablage:ablage app/ ./app/
COPY --chown=ablage:ablage test_documents/ ./test_documents/
COPY --chown=ablage:ablage *.py ./

# Set permissions (SECURITY FIX: 775 statt 777 für write-Verzeichnisse)
RUN chmod -R 755 /app && \
    chmod -R 775 /app/uploads /app/outputs /app/logs /app/cache

# Switch to non-root user
USER ablage

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
