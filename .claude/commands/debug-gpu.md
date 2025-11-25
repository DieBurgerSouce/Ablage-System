# Debug GPU Issues Command

Diagnose and fix GPU-related problems.

**Instructions:**
1. Run diagnostics:
   ```bash
   nvidia-smi
   python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else None}')"
   ```
2. Check GPU memory usage:
   ```bash
   nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits
   ```
3. Analyze error message/symptoms
4. Consult [gpu_troubleshooting_guide.md](../Execution_Layer/Troubleshooting/gpu_troubleshooting_guide.md)
5. Apply relevant fix from troubleshooting guide
6. Verify fix worked
7. Add monitoring if issue was critical

**Common Issues:**
- OOM → Reduce batch size, clear cache
- CUDA not available → Check drivers, CUDA version
- Slow inference → Enable FP16, check utilization
- Multi-process conflicts → Implement GPU lock

**Verification:**
```bash
# After fix
nvidia-smi
python -c "from app.gpu_manager import GPUManager; print(GPUManager().get_detailed_status())"
```
