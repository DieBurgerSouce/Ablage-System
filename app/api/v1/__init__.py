"""
API v1 - Version 1 of the API.

Available routers:
- auth: Authentication endpoints
- tasks: Task management endpoints
- metrics: Prometheus metrics and monitoring
- agents: Agent management and execution (requires Celery)
"""

# Lazy imports - only import when explicitly needed
# from . import auth, tasks, metrics, agents

__all__ = ["auth", "tasks", "metrics", "agents"]
