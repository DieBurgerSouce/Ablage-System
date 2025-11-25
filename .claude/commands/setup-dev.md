# Setup Development Environment Command

Complete development environment setup.

**Instructions:**
1. Check prerequisites:
   ```bash
   python --version  # Must be 3.11+
   docker --version
   nvidia-smi  # GPU check
   ```
2. Create virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # venv\Scripts\activate  # Windows
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```
4. Setup pre-commit hooks:
   ```bash
   pre-commit install
   ```
5. Start infrastructure:
   ```bash
   docker-compose up -d postgres redis minio
   ```
6. Run migrations:
   ```bash
   alembic upgrade head
   ```
7. Validate setup:
   ```bash
   pytest tests/test_basic.py -v
   python -c "from app.gpu_manager import GPUManager; print(GPUManager().get_detailed_status())"
   ```
8. Create .env from .env.example
9. Start development server:
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

**Validation Checklist:**
- [ ] Python 3.11+ installed
- [ ] Virtual environment activated
- [ ] All dependencies installed
- [ ] Docker containers running
- [ ] Database migrated
- [ ] GPU detected
- [ ] Tests passing
- [ ] Dev server running on :8000
