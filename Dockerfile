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
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Set Python 3.11 as default
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1
RUN update-alternatives --install /usr/bin/pip pip /usr/bin/pip3 1

# Upgrade pip
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

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
RUN pip install --no-cache-dir -r requirements.txt

# Install PyTorch with CUDA support
RUN pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# Install additional GPU requirements
RUN pip install --no-cache-dir -r requirements-gpu.txt

# Copy application code with correct ownership
COPY --chown=ablage:ablage app/ ./app/
COPY --chown=ablage:ablage test_documents/ ./test_documents/
COPY --chown=ablage:ablage *.py ./

# Set permissions
RUN chmod -R 755 /app && \
    chmod -R 777 /app/uploads /app/outputs /app/logs /app/cache

# Switch to non-root user
USER ablage

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
