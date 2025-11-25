"""
Sentry Celery Integration - Ablage-System OCR
Enhanced Celery monitoring with Sentry
"""

from typing import Any, Dict
from functools import wraps

import sentry_sdk
from celery import Task
from celery.signals import (
    task_prerun,
    task_postrun,
    task_failure,
    task_retry,
)


class SentryTask(Task):
    """
    Custom Celery task class with Sentry integration.

    Usage:
        @celery_app.task(base=SentryTask, bind=True)
        def my_task(self, arg):
            ...
    """

    def __call__(self, *args, **kwargs):
        """Execute task with Sentry transaction."""
        transaction_name = f'celery.task.{self.name}'

        with sentry_sdk.start_transaction(op='celery.task', name=transaction_name) as transaction:
            # Set task context
            transaction.set_tag('celery.task_name', self.name)
            transaction.set_tag('celery.queue', self.queue or 'default')

            sentry_sdk.set_context('celery', {
                'task_name': self.name,
                'task_id': self.request.id if self.request else None,
                'args': str(args)[:200],  # Truncate long args
                'kwargs': str(kwargs)[:200],
            })

            try:
                return super().__call__(*args, **kwargs)
            except Exception as exc:
                # Exception is already captured by CeleryIntegration,
                # but we add extra context here
                transaction.set_status('internal_error')
                raise

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Called when task is retried."""
        sentry_sdk.add_breadcrumb(
            message=f'Task {self.name} retrying',
            category='celery',
            level='warning',
            data={
                'task_id': task_id,
                'exception': str(exc),
                'retry_count': self.request.retries if self.request else 0,
            }
        )
        return super().on_retry(exc, task_id, args, kwargs, einfo)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Called when task fails."""
        # Capture exception with full context
        with sentry_sdk.push_scope() as scope:
            scope.set_context('celery_failure', {
                'task_name': self.name,
                'task_id': task_id,
                'args': str(args)[:500],
                'kwargs': str(kwargs)[:500],
                'traceback': str(einfo),
            })
            sentry_sdk.capture_exception(exc)

        return super().on_failure(exc, task_id, args, kwargs, einfo)


# Signal handlers for additional tracking
@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, **extra):
    """Track task start."""
    sentry_sdk.add_breadcrumb(
        message=f'Task {task.name} starting',
        category='celery',
        level='info',
        data={
            'task_id': task_id,
            'task_name': task.name,
        }
    )


@task_postrun.connect
def task_postrun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, retval=None, **extra):
    """Track task completion."""
    sentry_sdk.add_breadcrumb(
        message=f'Task {task.name} completed',
        category='celery',
        level='info',
        data={
            'task_id': task_id,
            'task_name': task.name,
        }
    )


@task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None, args=None, kwargs=None, traceback=None, einfo=None, **extra):
    """Track task failures."""
    sentry_sdk.add_breadcrumb(
        message=f'Task {sender.name} failed',
        category='celery',
        level='error',
        data={
            'task_id': task_id,
            'task_name': sender.name,
            'exception': str(exception),
        }
    )


@task_retry.connect
def task_retry_handler(sender=None, task_id=None, reason=None, einfo=None, **extra):
    """Track task retries."""
    sentry_sdk.add_breadcrumb(
        message=f'Task {sender.name} retrying',
        category='celery',
        level='warning',
        data={
            'task_id': task_id,
            'task_name': sender.name,
            'reason': str(reason),
        }
    )


def track_ocr_task(backend: str):
    """
    Decorator to track OCR tasks with specific backend context.

    Args:
        backend: OCR backend name (deepseek, got_ocr, surya)

    Usage:
        @track_ocr_task(backend='deepseek')
        @celery_app.task(base=SentryTask)
        def process_with_deepseek(document_id: str):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with sentry_sdk.start_span(op='ocr.process', description=f'OCR with {backend}') as span:
                span.set_tag('ocr.backend', backend)

                # Add GPU context if available
                try:
                    import torch
                    if torch.cuda.is_available():
                        span.set_tag('gpu.available', 'true')
                        span.set_data('gpu.name', torch.cuda.get_device_name(0))
                        span.set_data('gpu.memory_allocated', torch.cuda.memory_allocated())
                except ImportError:
                    pass

                return func(*args, **kwargs)

        return wrapper
    return decorator


def track_database_operation(operation: str):
    """
    Decorator to track database operations.

    Args:
        operation: Operation name (select, insert, update, delete)

    Usage:
        @track_database_operation('insert')
        async def create_document(db: Session, data: dict):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            with sentry_sdk.start_span(op=f'db.{operation}', description=func.__name__):
                return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            with sentry_sdk.start_span(op=f'db.{operation}', description=func.__name__):
                return func(*args, **kwargs)

        # Return appropriate wrapper
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
