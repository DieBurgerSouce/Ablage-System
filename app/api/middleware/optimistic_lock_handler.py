"""Exception Handler fuer Optimistic Locking Konflikte.

Wandelt SQLAlchemy StaleDataError und OptimisticLockError
in HTTP 409 Conflict um.

Registrierung erfolgt in app/core/exception_handlers.py via
register_exception_handlers().
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm.exc import StaleDataError
import structlog

from app.services.optimistic_lock_service import OptimisticLockError

logger = structlog.get_logger(__name__)


async def stale_data_exception_handler(
    request: Request, exc: StaleDataError
) -> JSONResponse:
    """Behandelt SQLAlchemy StaleDataError (Optimistic Locking via Mixin).

    Wird geworfen wenn version_id_col im Mixin einen Konflikt erkennt.
    Gibt HTTP 409 zurueck damit der Client die aktuelle Version neu laden kann.
    """
    logger.warning(
        "optimistic_lock_conflict",
        path=request.url.path,
        method=request.method,
        source="stale_data_error",
    )

    return JSONResponse(
        status_code=409,
        content={
            "detail": (
                "Konflikt: Dieses Objekt wurde zwischenzeitlich von einem "
                "anderen Nutzer geaendert. Bitte laden Sie die Seite neu "
                "und versuchen Sie es erneut."
            ),
            "error_code": "OPTIMISTIC_LOCK_CONFLICT",
            "hint": "Aktuelle Version laden und Aenderungen erneut anwenden.",
        },
    )


async def optimistic_lock_exception_handler(
    request: Request, exc: OptimisticLockError
) -> JSONResponse:
    """Behandelt OptimisticLockError (expliziter Service-basierter Check).

    Wird geworfen wenn update_with_optimistic_lock() einen
    Versionskonflikt erkennt. Gibt HTTP 409 zurueck.
    """
    logger.warning(
        "optimistic_lock_conflict",
        path=request.url.path,
        method=request.method,
        source="optimistic_lock_service",
        entity_type=exc.entity_type,
        entity_id=str(exc.entity_id),
        expected_version=exc.expected_version,
    )

    return JSONResponse(
        status_code=409,
        content={
            "detail": (
                "Konflikt: Dieses Objekt wurde zwischenzeitlich von einem "
                "anderen Nutzer geaendert. Bitte laden Sie die Seite neu "
                "und versuchen Sie es erneut."
            ),
            "error_code": "OPTIMISTIC_LOCK_CONFLICT",
            "entity_type": exc.entity_type,
            "expected_version": exc.expected_version,
            "hint": "Aktuelle Version laden und Aenderungen erneut anwenden.",
        },
    )
