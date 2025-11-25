# Ablage-System Development Container
# Based on Python 3.11 with CUDA support

FROM nvidia/cuda:12.2.0-cudnn8-devel-ubuntu22.04

# Avoid warnings by switching to noninteractive
ENV DEBIAN_FRONTEND=noninteractive

# Configure apt and install base packages
RUN apt-get update \
    && apt-get -y install --no-install-recommends \
    # Development tools
    git \
    curl \
    wget \
    vim \
    nano \
    sudo \
    build-essential \
    ca-certificates \
    gnupg \
    lsb-release \
    # Python build dependencies
    python3.11 \
    python3.11-dev \
    python3.11-venv \
    python3-pip \
    # Image processing libraries
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    # Tesseract OCR
    tesseract-ocr \
    tesseract-ocr-deu \
    libtesseract-dev \
    # Poppler for PDF processing
    poppler-utils \
    libpoppler-cpp-dev \
    # Database clients
    postgresql-client \
    # Utilities
    jq \
    tree \
    htop \
    tmux \
    zsh \
    # Cleanup
    && apt-get autoremove -y \
    && apt-get clean -y \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user 'vscode'
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID

RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME \
    && echo "$USERNAME ALL=(root) NOPASSWD:ALL" > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME

# Set up Python
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/pip pip /usr/bin/pip3 1

# Upgrade pip and install common tools
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Install Python development tools
RUN pip install --no-cache-dir \
    # Linting & Formatting
    ruff \
    black \
    isort \
    mypy \
    pylint \
    # Testing
    pytest \
    pytest-asyncio \
    pytest-cov \
    pytest-mock \
    pytest-xdist \
    # Pre-commit
    pre-commit \
    # Database
    ipython-sql \
    # Debugging
    ipdb \
    debugpy \
    # Documentation
    sphinx \
    sphinx-rtd-theme \
    # Jupyter
    jupyter \
    jupyterlab \
    ipykernel \
    # Git tools
    gitpython \
    # Performance profiling
    py-spy \
    scalene \
    memory-profiler

# Install PyTorch with CUDA support
RUN pip install --no-cache-dir \
    torch==2.1.0 \
    torchvision==0.16.0 \
    torchaudio==2.1.0 \
    --index-url https://download.pytorch.org/whl/cu121

# Install additional ML/OCR dependencies
RUN pip install --no-cache-dir \
    transformers \
    accelerate \
    optimum \
    sentencepiece \
    protobuf \
    opencv-python-headless \
    pillow \
    pytesseract \
    pdf2image \
    pypdfium2

# Install Docker CLI (for docker-in-docker scenarios)
RUN curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu \
    $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update \
    && apt-get install -y docker-ce-cli docker-compose-plugin \
    && apt-get clean -y \
    && rm -rf /var/lib/apt/lists/*

# Install Oh My Zsh for better terminal experience
USER $USERNAME
RUN sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended \
    && echo 'export PATH=$PATH:/home/vscode/.local/bin' >> ~/.zshrc \
    && echo 'alias python=python3' >> ~/.zshrc \
    && echo 'alias pip=pip3' >> ~/.zshrc

# Set up workspace
USER root
WORKDIR /workspace

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    CUDA_HOME=/usr/local/cuda \
    PATH=/usr/local/cuda/bin:$PATH \
    LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH

# Create directories for common mounts
RUN mkdir -p /workspace/.vscode /workspace/.git \
    && chown -R $USERNAME:$USERNAME /workspace

# Switch back to dialog for any ad-hoc use of apt-get
ENV DEBIAN_FRONTEND=dialog

# Set the default user
USER $USERNAME

# Default command
CMD ["/bin/zsh"]
