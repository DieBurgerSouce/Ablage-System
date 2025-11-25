# SOP-001: Installing OCR Backends
## PyTorch, CUDA, DeepSeek, GOT-OCR, Surya+Docling Setup

**Status**: Active
**Audience**: Developers, DevOps
**Estimated Time**: 45-60 minutes (first time), 15-20 minutes (subsequent)
**Prerequisites**: Ubuntu 22.04 LTS, NVIDIA RTX 4080, sudo access

---

## Overview

This SOP covers the complete installation of all OCR backends for the Ablage-System:
1. **System Dependencies**: CUDA, cuDNN, Python 3.11
2. **GPU Backend (DeepSeek-Janus-Pro)**: ~12GB VRAM required
3. **GPU Backend (GOT-OCR 2.0)**: ~10GB VRAM required
4. **CPU Fallback (Surya + Docling)**: No GPU required

---

## Table of Contents

1. [Prerequisites Check](#step-1-prerequisites-check)
2. [Install NVIDIA Drivers and CUDA](#step-2-install-nvidia-drivers-and-cuda)
3. [Install Python 3.11 and Dependencies](#step-3-install-python-311-and-dependencies)
4. [Install PyTorch with CUDA Support](#step-4-install-pytorch-with-cuda-support)
5. [Install DeepSeek-Janus-Pro](#step-5-install-deepseek-janus-pro)
6. [Install GOT-OCR 2.0](#step-6-install-got-ocr-20)
7. [Install Surya + Docling](#step-7-install-surya--docling)
8. [Verification and Testing](#step-8-verification-and-testing)
9. [Troubleshooting](#troubleshooting)

---

## Step 1: Prerequisites Check

### 1.1 Verify System
```bash
# OS version
lsb_release -a
# Expected: Ubuntu 22.04 LTS

# GPU detection
lspci | grep -i nvidia
# Expected: NVIDIA RTX 4080

# Disk space
df -h /
# Minimum: 100GB free (models are large)
```

### 1.2 Update System
```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y build-essential git wget curl
```

---

## Step 2: Install NVIDIA Drivers and CUDA

### 2.1 Install NVIDIA Driver (v535+)
```bash
# Remove old drivers (if any)
sudo apt remove --purge nvidia-* -y
sudo apt autoremove -y

# Add NVIDIA repository
sudo apt install -y software-properties-common
sudo add-apt-repository ppa:graphics-drivers/ppa -y
sudo apt update

# Install recommended driver
sudo apt install -y nvidia-driver-535

# Reboot required
sudo reboot
```

### 2.2 Verify Driver Installation
```bash
# After reboot
nvidia-smi

# Expected output:
# +-----------------------------------------------------------------------------+
# | NVIDIA-SMI 535.xx       Driver Version: 535.xx       CUDA Version: 12.2    |
# |-------------------------------+----------------------+----------------------+
# | GPU  Name        Persistence-M| Bus-Id        Disp.A | Volatile Uncorr. ECC |
# | Fan  Temp  Perf  Pwr:Usage/Cap|         Memory-Usage | GPU-Util  Compute M. |
# |===============================+======================+======================|
# |   0  NVIDIA GeForce ...  Off  | 00000000:01:00.0 Off |                  N/A |
# | 30%   35C    P8    15W / 320W |      0MiB / 16384MiB |      0%      Default |
# +-------------------------------+----------------------+----------------------+
```

### 2.3 Install CUDA Toolkit 12.1
```bash
# Download CUDA 12.1 installer
wget https://developer.download.nvidia.com/compute/cuda/12.1.0/local_installers/cuda_12.1.0_530.30.02_linux.run

# Install CUDA (do NOT install driver, we already have it)
sudo sh cuda_12.1.0_530.30.02_linux.run --silent --toolkit --no-opengl-libs

# Add to PATH
echo 'export PATH=/usr/local/cuda-12.1/bin:$PATH' >> ~/.bashrc
echo 'export LD_LIBRARY_PATH=/usr/local/cuda-12.1/lib64:$LD_LIBRARY_PATH' >> ~/.bashrc
source ~/.bashrc

# Verify CUDA
nvcc --version
# Expected: CUDA compilation tools, release 12.1
```

### 2.4 Install cuDNN 8.9
```bash
# Download cuDNN (requires NVIDIA account)
# Visit: https://developer.nvidia.com/cudnn
# Download: cuDNN v8.9.x for CUDA 12.x

# Extract and install
tar -xvf cudnn-linux-x86_64-8.9.x.x_cuda12-archive.tar.xz
sudo cp cudnn-*-archive/include/cudnn*.h /usr/local/cuda/include
sudo cp -P cudnn-*-archive/lib/libcudnn* /usr/local/cuda/lib64
sudo chmod a+r /usr/local/cuda/include/cudnn*.h /usr/local/cuda/lib64/libcudnn*
```

---

## Step 3: Install Python 3.11 and Dependencies

### 3.1 Install Python 3.11
```bash
# Add deadsnakes PPA
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update

# Install Python 3.11
sudo apt install -y python3.11 python3.11-venv python3.11-dev

# Verify
python3.11 --version
# Expected: Python 3.11.x
```

### 3.2 Create Virtual Environment
```bash
cd ~/ablage-system  # Or your project directory

# Create venv
python3.11 -m venv venv

# Activate
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip setuptools wheel
```

---

## Step 4: Install PyTorch with CUDA Support

### 4.1 Install PyTorch 2.1+ (CUDA 12.1)
```bash
# Activate venv (if not already)
source venv/bin/activate

# Install PyTorch with CUDA 12.1
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# This will install:
# - torch ~2.5GB
# - torchvision ~1GB
# - torchaudio ~500MB
```

### 4.2 Verify PyTorch + CUDA
```bash
python3 -c "import torch; print(f'PyTorch version: {torch.__version__}'); print(f'CUDA available: {torch.cuda.is_available()}'); print(f'CUDA version: {torch.version.cuda}'); print(f'GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')"

# Expected output:
# PyTorch version: 2.1.x+cu121
# CUDA available: True
# CUDA version: 12.1
# GPU: NVIDIA GeForce RTX 4080
```

---

## Step 5: Install DeepSeek-Janus-Pro

### 5.1 Install Dependencies
```bash
pip install transformers==4.36.0
pip install accelerate==0.25.0
pip install sentencepiece==0.1.99
pip install pillow==10.1.0
```

### 5.2 Download Model (12GB download + 12GB VRAM required)
```bash
# Using Hugging Face Hub
pip install huggingface-hub

# Download model (this will take 15-30 minutes)
python3 << EOF
from transformers import AutoModel, AutoTokenizer

model_name = "deepseek-ai/deepseek-janus-pro-1.0"

print("Downloading DeepSeek-Janus-Pro model...")
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModel.from_pretrained(
    model_name,
    trust_remote_code=True,
    torch_dtype=torch.float16  # Use FP16 to save VRAM
)

print("Model downloaded successfully!")
print(f"Model size: ~12GB")
EOF
```

### 5.3 Test DeepSeek
```bash
python3 << EOF
import torch
from transformers import AutoModel, AutoTokenizer
from PIL import Image

model_name = "deepseek-ai/deepseek-janus-pro-1.0"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModel.from_pretrained(
    model_name,
    trust_remote_code=True,
    torch_dtype=torch.float16
).cuda()

# Test with dummy image
dummy_image = Image.new('RGB', (224, 224), color='white')

print("DeepSeek-Janus-Pro loaded successfully!")
print(f"VRAM usage: {torch.cuda.memory_allocated() / 1024**3:.2f} GB")
EOF
```

---

## Step 6: Install GOT-OCR 2.0

### 6.1 Clone GOT-OCR Repository
```bash
cd ~/
git clone https://github.com/ucaslcl/GOT-OCR2.0.git
cd GOT-OCR2.0
```

### 6.2 Install Dependencies
```bash
pip install -r requirements.txt
# Includes: transformers, timm, tiktoken, verovio
```

### 6.3 Download GOT-OCR Model (10GB)
```bash
# Download from Hugging Face or model source
# (Follow GOT-OCR documentation for latest model)

python3 << EOF
from transformers import AutoModel

model = AutoModel.from_pretrained(
    "stepfun-ai/GOT-OCR2_0",
    trust_remote_code=True,
    torch_dtype=torch.float16
)

print("GOT-OCR 2.0 downloaded successfully!")
EOF
```

### 6.4 Test GOT-OCR
```bash
cd ~/GOT-OCR2.0

python3 << EOF
import torch
from transformers import AutoModel

model = AutoModel.from_pretrained(
    "stepfun-ai/GOT-OCR2_0",
    trust_remote_code=True,
    torch_dtype=torch.float16
).cuda()

print("GOT-OCR 2.0 loaded successfully!")
print(f"VRAM usage: {torch.cuda.memory_allocated() / 1024**3:.2f} GB")
EOF
```

---

## Step 7: Install Surya + Docling

### 7.1 Install Surya (CPU Fallback OCR)
```bash
cd ~/ablage-system
source venv/bin/activate

pip install surya-ocr==1.1.0
```

### 7.2 Install Docling (Layout Analysis)
```bash
pip install docling==1.0.0
```

### 7.3 Test Surya
```bash
python3 << EOF
from surya import OCRModel

# Surya runs on CPU (no CUDA required)
model = OCRModel()

print("Surya OCR loaded successfully (CPU mode)!")
EOF
```

---

## Step 8: Verification and Testing

### 8.1 Verify All Backends
```bash
cd ~/ablage-system
source venv/bin/activate

python3 << EOF
import torch
from app.gpu_manager import GPUManager
from app.services.ocr_service import OCRService

# GPU Manager
gpu = GPUManager()
print("=== GPU Status ===")
print(gpu.get_detailed_status())

# OCR Service
ocr = OCRService()
print("\n=== OCR Backends ===")
print(f"DeepSeek available: {ocr.is_backend_available('deepseek')}")
print(f"GOT-OCR available: {ocr.is_backend_available('got_ocr')}")
print(f"Surya available: {ocr.is_backend_available('surya')}")
EOF
```

### 8.2 Run Integration Tests
```bash
pytest tests/test_basic.py -v

# Expected: 7/7 tests passing
```

### 8.3 Process Test Document
```bash
# Start API server
python app/main.py &

# Wait for startup (5 seconds)
sleep 5

# Test OCR endpoint
curl -X POST "http://localhost:8000/api/v1/ocr/process/test_doc_001?backend=auto"

# Check response for successful processing
```

---

## Troubleshooting

### Issue 1: CUDA not detected by PyTorch
**Symptom**: `torch.cuda.is_available()` returns `False`

**Solutions**:
```bash
# 1. Verify NVIDIA driver
nvidia-smi

# 2. Reinstall PyTorch with correct CUDA version
pip uninstall torch torchvision torchaudio
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# 3. Check CUDA path
echo $LD_LIBRARY_PATH
# Should contain /usr/local/cuda-12.1/lib64
```

### Issue 2: Out of Memory (OOM) during model loading
**Symptom**: `torch.cuda.OutOfMemoryError` when loading models

**Solutions**:
```bash
# 1. Clear VRAM
python3 -c "import torch; torch.cuda.empty_cache()"

# 2. Check VRAM usage
nvidia-smi

# 3. Load only one model at a time (don't preload all)
# Edit app/services/model_manager.py:
# - Lazy loading: Load models on-demand
# - Unload models after use if VRAM < 4GB free
```

### Issue 3: Model download fails
**Symptom**: Connection timeout or slow download

**Solutions**:
```bash
# 1. Use Hugging Face mirror (for China/slow regions)
export HF_ENDPOINT=https://hf-mirror.com

# 2. Download manually and place in cache
# Models are cached in: ~/.cache/huggingface/

# 3. Resume interrupted download
pip install huggingface-hub
huggingface-cli download deepseek-ai/deepseek-janus-pro-1.0 --resume-download
```

### Issue 4: cuDNN version mismatch
**Symptom**: `Could not load library 'libcudnn_ops_infer.so.8'`

**Solutions**:
```bash
# 1. Verify cuDNN installation
ls /usr/local/cuda/lib64/libcudnn*

# 2. Reinstall cuDNN 8.9 for CUDA 12.x (see Step 2.4)

# 3. Set LD_LIBRARY_PATH
export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH
```

---

## Post-Installation Checklist

- [ ] NVIDIA driver 535+ installed (`nvidia-smi` works)
- [ ] CUDA 12.1 installed (`nvcc --version` shows 12.1)
- [ ] cuDNN 8.9 installed (files in `/usr/local/cuda/lib64/`)
- [ ] Python 3.11+ with venv (`python3.11 --version`)
- [ ] PyTorch with CUDA support (`torch.cuda.is_available()` = True)
- [ ] DeepSeek-Janus-Pro model downloaded (~12GB)
- [ ] GOT-OCR 2.0 model downloaded (~10GB)
- [ ] Surya + Docling installed (CPU fallback)
- [ ] Integration tests passing (`pytest tests/test_basic.py`)
- [ ] API server starts successfully (`python app/main.py`)

---

## Maintenance

### Weekly Tasks
- Monitor VRAM usage (`nvidia-smi`)
- Check for PyTorch updates (`pip list --outdated | grep torch`)
- Verify all backends still functional

### Monthly Tasks
- Update NVIDIA drivers (if needed)
- Update OCR model versions (check GitHub releases)
- Review and clean model cache (`~/.cache/huggingface/`)

### Quarterly Tasks
- CUDA/cuDNN updates (if compatible with PyTorch)
- Performance benchmarking (measure pages/sec)

---

## References

- [NVIDIA CUDA Installation Guide](https://docs.nvidia.com/cuda/cuda-installation-guide-linux/)
- [PyTorch Installation](https://pytorch.org/get-started/locally/)
- [DeepSeek-Janus-Pro GitHub](https://github.com/deepseek-ai/DeepSeek-Janus)
- [GOT-OCR 2.0 GitHub](https://github.com/ucaslcl/GOT-OCR2.0)
- [Surya OCR Documentation](https://github.com/VikParuchuri/surya)
- [app/gpu_manager.py](../../app/gpu_manager.py) - GPU management code
- [requirements.txt](../../requirements.txt) - Python dependencies

---

**Last Updated**: 2025-01-22
**Next Review**: 2025-04-22
**SOP Owner**: DevOps Team
