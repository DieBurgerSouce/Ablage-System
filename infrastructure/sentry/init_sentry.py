"""
Sentry Initialization - Ablage-System OCR
Application startup integration
"""

import os
from typing import Optional

from .sentry import (
    init_sentry,
    set_context,
    add_breadcrumb,
)


def initialize_sentry_for_backend(
    app_name: str = "ablage-backend",
    environment: Optional[str] = None,
    release: Optional[str] = None
) -> None:
    """
    Initialize Sentry for FastAPI backend.

    Args:
        app_name: Application name
        environment: Environment (dev, staging, production)
        release: Release version
    """
    # Get configuration from environment
    environment = environment or os.getenv('ENVIRONMENT', 'development')
    release = release or os.getenv('VERSION', 'unknown')

    # Initialize Sentry
    init_sentry(
        environment=environment,
        release=release,
        traces_sample_rate=float(os.getenv('SENTRY_TRACES_SAMPLE_RATE', '0.1')),
        profiles_sample_rate=float(os.getenv('SENTRY_PROFILES_SAMPLE_RATE', '0.1')),
        enable_tracing=os.getenv('SENTRY_ENABLE_TRACING', 'true').lower() == 'true'
    )

    # Set application context
    set_context('application', {
        'name': app_name,
        'environment': environment,
        'release': release,
        'python_version': os.sys.version,
    })

    # Add startup breadcrumb
    add_breadcrumb(
        message=f'{app_name} starting',
        category='application',
        level='info',
        data={
            'environment': environment,
            'release': release,
        }
    )


def initialize_sentry_for_worker(
    worker_name: str = "ablage-worker",
    environment: Optional[str] = None,
    release: Optional[str] = None
) -> None:
    """
    Initialize Sentry for Celery worker.

    Args:
        worker_name: Worker name
        environment: Environment (dev, staging, production)
        release: Release version
    """
    # Get configuration from environment
    environment = environment or os.getenv('ENVIRONMENT', 'development')
    release = release or os.getenv('VERSION', 'unknown')

    # Initialize Sentry with different sampling for workers
    init_sentry(
        environment=environment,
        release=release,
        traces_sample_rate=float(os.getenv('SENTRY_WORKER_TRACES_SAMPLE_RATE', '0.05')),
        profiles_sample_rate=float(os.getenv('SENTRY_WORKER_PROFILES_SAMPLE_RATE', '0.05')),
        enable_tracing=os.getenv('SENTRY_ENABLE_TRACING', 'true').lower() == 'true'
    )

    # Set worker context
    set_context('worker', {
        'name': worker_name,
        'environment': environment,
        'release': release,
        'gpu_available': _check_gpu_available(),
    })

    # Add startup breadcrumb
    add_breadcrumb(
        message=f'{worker_name} starting',
        category='worker',
        level='info',
        data={
            'environment': environment,
            'release': release,
            'gpu': _check_gpu_available(),
        }
    )


def _check_gpu_available() -> bool:
    """Check if GPU is available."""
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False
