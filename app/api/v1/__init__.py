"""
API v1 - Version 1 of the API.

Available routers:
- auth: Authentication endpoints
- tasks: Task management endpoints
- metrics: Prometheus metrics and monitoring
- agents: Agent management and execution (requires Celery)
- ml: Machine Learning endpoints (Drift, SHAP, A/B Testing)
- versions: OCR version management endpoints
"""

# Lazy imports - only import when explicitly needed
# from . import auth, tasks, metrics, agents, ml, versions

__all__ = ["auth", "tasks", "metrics", "agents", "ml", "versions"]
