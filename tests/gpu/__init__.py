"""GPU Backend Tests for Ablage-System OCR.

This package contains tests for GPU-accelerated OCR backends:
- SuryaGPU: GPU-accelerated Surya OCR
- Donut: Vision encoder-decoder OCR
- GOT-OCR: Transformer-based OCR
- DeepSeek: Multimodal Janus-Pro 7B

Requirements:
- NVIDIA GPU with 16GB+ VRAM (RTX 4080 recommended)
- CUDA 12.x and cuDNN
- BitsAndBytes for 4-bit quantization (Linux/WSL2 recommended)

Run with:
    pytest tests/gpu/ -v --tb=short

Run in Docker/WSL2 for best compatibility:
    docker exec -it ablage-backend pytest tests/gpu/ -v
"""
