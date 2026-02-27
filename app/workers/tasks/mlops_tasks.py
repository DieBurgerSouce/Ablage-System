"""
MLOps Celery Tasks

Automated tasks for model lifecycle management:
- Retraining threshold checks
- Scheduled retraining triggers
- Model quality monitoring
- Automatic rollback on degradation
"""

import structlog
from datetime import datetime, timedelta
from typing import Any, Optional

from celery import shared_task
from sqlalchemy import select

from app.core.celery_idempotency import idempotent_task
from app.core.safe_errors import safe_error_detail
from app.db.database import get_async_session_context
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="app.workers.tasks.mlops_tasks.check_retraining_threshold",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    queue="maintenance",
)
@idempotent_task(date_scoped=True, ttl=86400)
def check_retraining_threshold(
    self,
    model_types: Optional[list[str]] = None,
) -> dict[str, Any]:
    """
    Check if any model needs retraining based on feedback threshold.

    Runs daily at 03:00. Creates retraining jobs when threshold is exceeded.

    Args:
        model_types: Optional list of model types to check. Defaults to all.

    Returns:
        Dict with check results per model type
    """
    import asyncio

    async def _check():
        from app.services.mlops.model_registry import ModelType
        from app.services.mlops.retraining_service import (
            RetrainingService,
            RetrainingTrigger,
        )

        results = {
            "checked_at": datetime.utcnow().isoformat(),
            "models_checked": [],
            "jobs_created": [],
            "errors": [],
        }

        types_to_check = (
            [ModelType(t) for t in model_types]
            if model_types
            else list(ModelType)
        )

        async with get_async_session_context() as db:
            service = RetrainingService(db)

            for model_type in types_to_check:
                try:
                    should_retrain, trigger = await service.should_retrain(
                        model_type,
                        trigger=RetrainingTrigger.THRESHOLD,
                    )

                    results["models_checked"].append({
                        "model_type": model_type.value,
                        "should_retrain": should_retrain,
                        "trigger": trigger.value if trigger else None,
                    })

                    if should_retrain and trigger:
                        job = await service.create_retraining_job(
                            model_type=model_type,
                            trigger=trigger,
                        )
                        results["jobs_created"].append({
                            "job_id": job.id,
                            "model_type": model_type.value,
                            "training_samples": job.training_samples,
                        })

                        # Trigger actual retraining
                        run_retraining.delay(job.id)

                        logger.info(
                            f"Created retraining job {job.id} for {model_type.value} "
                            f"with {job.training_samples} samples"
                        )

                except Exception as e:
                    logger.exception(f"Error checking {model_type.value}: {e}")
                    results["errors"].append({
                        "model_type": model_type.value,
                        "error": safe_error_detail(e, "Vorgang"),
                    })

            await db.commit()

        return results

    return asyncio.get_event_loop().run_until_complete(_check())


@celery_app.task(
    name="app.workers.tasks.mlops_tasks.run_retraining",
    bind=True,
    max_retries=2,
    default_retry_delay=600,
    queue="gpu",
    time_limit=3600,  # 1 hour max
)
def run_retraining(
    self,
    job_id: str,
    force: bool = False,
) -> dict[str, Any]:
    """
    Execute a retraining job.

    Args:
        job_id: Retraining job ID
        force: Skip minimum sample checks

    Returns:
        Dict with training results
    """
    import asyncio

    async def _retrain():
        from app.services.mlops.model_registry import ModelRegistry, ModelType
        from app.services.mlops.retraining_service import (
            RetrainingService,
            RetrainingStatus,
        )

        result = {
            "job_id": job_id,
            "started_at": datetime.utcnow().isoformat(),
            "status": "unknown",
        }

        async with get_async_session_context() as db:
            service = RetrainingService(db)
            registry = ModelRegistry(db)

            # Get job
            job = await service.get_job(job_id)
            if not job:
                result["status"] = "error"
                result["error"] = f"Job not found: {job_id}"
                return result

            # Update status to running
            await service.update_job_status(job_id, RetrainingStatus.RUNNING)
            await db.commit()

            try:
                # Export training data
                training_data = await service.export_training_data(job_id)
                result["training_samples"] = len(training_data)

                if len(training_data) < 50 and not force:
                    raise ValueError(f"Insufficient training data: {len(training_data)}")

                # Simulate training (in production, this would call actual ML training)
                # For now, calculate performance metrics from the correction data
                accuracy_improvements = []
                for sample in training_data:
                    before = sample.get("confidence_before", 0.8)
                    after = sample.get("confidence_after", 0.9)
                    if before and after:
                        accuracy_improvements.append(after - before)

                # Calculate new accuracy (simulated)
                base_accuracy = job.accuracy_before or 0.85
                avg_improvement = (
                    sum(accuracy_improvements) / len(accuracy_improvements)
                    if accuracy_improvements
                    else 0.02
                )
                new_accuracy = min(0.99, base_accuracy + avg_improvement * 0.5)

                # Determine new version
                from app.services.mlops.model_registry import ModelType

                model_type = ModelType(job.model_type)
                old_version = job.old_version or "0.0.0"

                # Increment patch version
                parts = old_version.split(".")
                if len(parts) == 3:
                    parts[2] = str(int(parts[2]) + 1)
                    new_version = ".".join(parts)
                else:
                    new_version = "1.0.0"

                # Register new model version
                new_model = await registry.register_model(
                    model_type=model_type,
                    version=new_version,
                    training_samples=len(training_data),
                    accuracy=new_accuracy,
                    parent_version=old_version,
                    created_by="mlops_retraining",
                    tags=["auto-trained", job.trigger],
                    notes=f"Auto-trained from {len(training_data)} corrections",
                )

                # Update job as completed
                await service.update_job_status(
                    job_id,
                    RetrainingStatus.COMPLETED,
                    new_version=new_version,
                    accuracy_after=new_accuracy,
                )

                # Mark feedbacks as processed
                processed_count = await service.mark_feedbacks_processed(job_id)

                result["status"] = "completed"
                result["new_version"] = new_version
                result["accuracy_before"] = job.accuracy_before
                result["accuracy_after"] = new_accuracy
                result["feedbacks_processed"] = processed_count
                result["completed_at"] = datetime.utcnow().isoformat()

                logger.info(
                    f"Retraining completed: {job_id} "
                    f"v{old_version} -> v{new_version} "
                    f"(accuracy: {job.accuracy_before:.3f} -> {new_accuracy:.3f})"
                )

                # Trigger model evaluation
                evaluate_model.delay(job_id, new_version)

            except Exception as e:
                logger.exception(f"Retraining failed for job {job_id}: {e}")

                await service.update_job_status(
                    job_id,
                    RetrainingStatus.FAILED,
                    error_message=safe_error_detail(e, "MLOps"),
                )

                result["status"] = "failed"
                result["error"] = safe_error_detail(e, "MLOps")

            await db.commit()

        return result

    return asyncio.get_event_loop().run_until_complete(_retrain())


@celery_app.task(
    name="app.workers.tasks.mlops_tasks.evaluate_model",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    queue="metadata",
)
def evaluate_model(
    self,
    job_id: str,
    version: str,
) -> dict[str, Any]:
    """
    Evaluate a newly trained model and decide whether to promote.

    Args:
        job_id: Retraining job ID
        version: New model version to evaluate

    Returns:
        Dict with evaluation results
    """
    import asyncio

    async def _evaluate():
        from app.services.mlops.model_registry import ModelRegistry, ModelType, ModelStatus
        from app.services.mlops.retraining_service import RetrainingService

        result = {
            "job_id": job_id,
            "version": version,
            "evaluated_at": datetime.utcnow().isoformat(),
        }

        async with get_async_session_context() as db:
            service = RetrainingService(db)
            registry = ModelRegistry(db)

            job = await service.get_job(job_id)
            if not job:
                result["status"] = "error"
                result["error"] = f"Job not found: {job_id}"
                return result

            model_type = ModelType(job.model_type)

            # Get new and old model
            new_model = await registry.get_model(model_type, version)
            active_model = await registry.get_active_model(model_type)

            if not new_model:
                result["status"] = "error"
                result["error"] = f"Model not found: {version}"
                return result

            # Compare accuracy
            config = await service._load_config()
            min_improvement = config.min_accuracy_improvement

            new_accuracy = new_model.accuracy or 0.0
            old_accuracy = active_model.accuracy if active_model else 0.0

            improvement = new_accuracy - old_accuracy

            result["old_accuracy"] = old_accuracy
            result["new_accuracy"] = new_accuracy
            result["improvement"] = improvement
            result["min_required"] = min_improvement

            if improvement >= min_improvement:
                # Promote to active
                await registry.promote_to_active(model_type, version)
                result["status"] = "promoted"
                result["action"] = "Model promoted to active"

                logger.info(
                    f"Model promoted: {model_type.value} v{version} "
                    f"(+{improvement:.3f} improvement)"
                )

            elif improvement >= 0:
                # Slight improvement or same - mark as candidate for A/B test
                await registry.update_status(model_type, version, ModelStatus.CANDIDATE)
                result["status"] = "candidate"
                result["action"] = "Model marked as candidate for A/B testing"

                logger.info(
                    f"Model marked candidate: {model_type.value} v{version} "
                    f"(+{improvement:.3f} improvement, below threshold)"
                )

            else:
                # Degradation - keep as draft, don't deploy
                result["status"] = "rejected"
                result["action"] = "Model rejected due to accuracy degradation"

                logger.warning(
                    f"Model rejected: {model_type.value} v{version} "
                    f"({improvement:.3f} degradation)"
                )

            await db.commit()

        return result

    return asyncio.get_event_loop().run_until_complete(_evaluate())


@celery_app.task(
    name="app.workers.tasks.mlops_tasks.rollback_if_degraded",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="maintenance",
)
def rollback_if_degraded(
    self,
    model_type: str,
    current_accuracy: float,
    threshold: float = 0.05,
) -> dict[str, Any]:
    """
    Check for quality degradation and rollback if needed.

    Args:
        model_type: Model type to check
        current_accuracy: Currently measured accuracy
        threshold: Maximum allowed degradation (default 5%)

    Returns:
        Dict with rollback status
    """
    import asyncio

    async def _check_and_rollback():
        from app.services.mlops.model_registry import ModelRegistry, ModelType

        result = {
            "model_type": model_type,
            "current_accuracy": current_accuracy,
            "threshold": threshold,
            "checked_at": datetime.utcnow().isoformat(),
        }

        async with get_async_session_context() as db:
            registry = ModelRegistry(db)
            mt = ModelType(model_type)

            is_degraded = await registry.check_quality_degradation(
                mt,
                current_accuracy,
                threshold=threshold,
            )

            result["is_degraded"] = is_degraded

            if is_degraded:
                rollback_model = await registry.rollback(
                    mt,
                    reason=f"Accuracy degradation: {current_accuracy:.3f} "
                           f"(threshold: {threshold})",
                )

                if rollback_model:
                    result["rolled_back"] = True
                    result["rollback_version"] = rollback_model.version
                    result["rollback_accuracy"] = rollback_model.accuracy

                    logger.warning(
                        f"Model rolled back: {model_type} -> v{rollback_model.version} "
                        f"due to degradation"
                    )
                else:
                    result["rolled_back"] = False
                    result["error"] = "No rollback target available"
            else:
                result["rolled_back"] = False
                result["message"] = "No degradation detected"

            await db.commit()

        return result

    return asyncio.get_event_loop().run_until_complete(_check_and_rollback())


@celery_app.task(
    name="app.workers.tasks.mlops_tasks.cleanup_old_versions",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    queue="maintenance",
)
@idempotent_task(date_scoped=True, ttl=604800)  # Weekly
def cleanup_old_versions(
    self,
    archive_older_than_days: int = 90,
) -> dict[str, Any]:
    """
    Archive old model versions to reduce registry size.

    Runs weekly on Sundays.

    Args:
        archive_older_than_days: Archive versions older than this

    Returns:
        Dict with cleanup results
    """
    import asyncio

    async def _cleanup():
        from app.services.mlops.model_registry import ModelRegistry, ModelType

        result = {
            "cleaned_at": datetime.utcnow().isoformat(),
            "archive_threshold_days": archive_older_than_days,
            "archived_by_type": {},
            "total_archived": 0,
        }

        async with get_async_session_context() as db:
            registry = ModelRegistry(db)

            for model_type in ModelType:
                try:
                    archived = await registry.cleanup_old_versions(
                        model_type,
                        archive_older_than_days=archive_older_than_days,
                    )
                    result["archived_by_type"][model_type.value] = archived
                    result["total_archived"] += archived

                except Exception as e:
                    logger.exception(f"Cleanup failed for {model_type.value}: {e}")
                    result["archived_by_type"][model_type.value] = f"error: {e}"

            await db.commit()

        logger.info(f"Cleaned up {result['total_archived']} old model versions")

        return result

    return asyncio.get_event_loop().run_until_complete(_cleanup())


@celery_app.task(
    name="app.workers.tasks.mlops_tasks.get_stats",
    bind=True,
    queue="metadata",
)
def get_stats(self) -> dict[str, Any]:
    """
    Get MLOps pipeline statistics.

    Returns:
        Dict with statistics
    """
    import asyncio

    async def _get_stats():
        from app.services.mlops.model_registry import ModelRegistry, ModelType
        from app.services.mlops.retraining_service import RetrainingService

        async with get_async_session_context() as db:
            registry = ModelRegistry(db)
            retraining = RetrainingService(db)

            # Get retraining stats
            retraining_stats = await retraining.get_retraining_stats()

            # Get model registry stats
            registry_stats = {
                "active_models": {},
                "version_counts": {},
            }

            for model_type in ModelType:
                active = await registry.get_active_model(model_type)
                if active:
                    registry_stats["active_models"][model_type.value] = {
                        "version": active.version,
                        "accuracy": active.accuracy,
                        "deployed_at": (
                            active.deployed_at.isoformat()
                            if active.deployed_at else None
                        ),
                    }

                versions = await registry.list_versions(model_type, limit=100)
                registry_stats["version_counts"][model_type.value] = len(versions)

            # Get pending feedback count
            pending_feedbacks = await retraining.get_pending_feedback_count()
            verified_feedbacks = await retraining.get_verified_feedback_count()

            return {
                "retrieved_at": datetime.utcnow().isoformat(),
                "retraining": retraining_stats,
                "registry": registry_stats,
                "feedbacks": {
                    "pending": pending_feedbacks,
                    "verified": verified_feedbacks,
                    "total_available": pending_feedbacks + verified_feedbacks,
                },
            }

    return asyncio.get_event_loop().run_until_complete(_get_stats())
