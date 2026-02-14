# GPU-enabled Docker image for Ablage-System OCR
# Security-hardened with non-root user
FROM nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV TORCH_CUDA_ARCH_LIST="8.6;8.9"
ENV CUDA_VISIBLE_DEVICES=0

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-dev \
    python3-pip \
    git \
    wget \
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
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Set Python 3.11 as default and ensure pip uses Python 3.11
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# Install uv for fast dependency resolution (10-100x faster than pip)
# Use python3.11 -m pip to ensure packages go to Python 3.11
RUN python3.11 -m pip install --no-cache-dir --upgrade pip setuptools wheel uv

# Create non-root user BEFORE copying files
ARG UID=1000
ARG GID=1000
RUN groupadd -g ${GID} ablage && \
    useradd -m -u ${UID} -g ${GID} -s /bin/bash ablage

# Create app directory with correct ownership
WORKDIR /app
RUN mkdir -p /app/uploads /app/outputs /app/logs /app/cache && \
    chown -R ablage:ablage /app

# Copy requirements first for better caching
COPY --chown=ablage:ablage requirements.txt .
COPY --chown=ablage:ablage requirements-gpu.txt .

# Install Python dependencies as root (for system packages)
# Using uv for 10-100x faster dependency resolution (Rust-based pip replacement)
RUN uv pip install --system -r requirements.txt

# NOTE: PyTorch with CUDA support is now installed via requirements.txt (transformers pulls torch with CUDA bindings)
# The cu121 index install was removed to avoid version conflicts - torch-2.9.1 from pypi includes nvidia-* packages

# Install additional GPU requirements
RUN uv pip install --system -r requirements-gpu.txt

# Install DeepSeek Janus library for Janus-Pro multimodal OCR
# Required for MultiModalityCausalLM and VLChatProcessor classes
# First install dependencies, then the package in editable mode via PYTHONPATH
RUN git clone --depth 1 https://github.com/deepseek-ai/Janus.git /opt/janus && \
    uv pip install --system attrdict einops sentencepiece timm accelerate && \
    echo "/opt/janus" > /usr/local/lib/python3.11/dist-packages/janus.pth && \
    python3.11 -c "from janus.models import MultiModalityCausalLM, VLChatProcessor; print('Janus OK')"

# Copy application code with correct ownership
COPY --chown=ablage:ablage app/ ./app/
COPY --chown=ablage:ablage test_documents/ ./test_documents/
COPY --chown=ablage:ablage *.py ./

# Set permissions (SECURITY FIX: 775 statt 777 für write-Verzeichnisse)
# User ablage und Gruppe ablage haben Schreibrechte, andere nur lesen
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
