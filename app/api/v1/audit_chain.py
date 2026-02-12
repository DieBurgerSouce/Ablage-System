"""
Audit Chain API Endpoints

REST API fuer kryptografischen Audit-Trail mit Merkle Trees:
- Status-Uebersicht
- Merkle Proof Generierung
- Proof-Verifikation
- Integritaets-Reports
- Chain-Export

Feinpoliert und durchdacht - Enterprise Audit Trail Security.
"""

from typing import Dict
from datetime import datetime, timezone, timedelta
from uuid import UUID

from app.core.types import JSONDict
import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.db.models import User
from app.api.dependencies import get_db, get_current_active_user, get_current_company_id
from app.services.compliance.merkle_tree_service import MerkleTreeService
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.core.security_auth import build_content_disposition

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/audit-chain", tags=["Audit Chain"])


# =============================================================================
# Schemas
# =============================================================================


class VerifyProofRequest(BaseModel):
    """Request-Schema fuer Proof-Verifikation."""

    entry_hash: str = Field(..., min_length=64, max_length=64, description="SHA256 Hash des Eintrags")
    root_hash: str = Field(..., min_length=64, max_length=64, description="Root Hash des Trees")
    proof_path: list[Dict[str, str]] = Field(..., description="Proof-Pfad")


# =============================================================================
# Audit Chain Endpoints
# =============================================================================


@router.get(
    "/status",
    response_model=JSONDict,
    summary="Audit-Chain Status",
    description="Allgemeine Statistiken zur Audit-Chain"
)
async def get_status(
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> JSONDict:
    """
    Holt Audit-Chain Status.

    **Enthaelt:**
    - Anzahl Eintraege
    - Root Hash
    - Letzte Verifikation
    - Integritaets-Score

    **Rollen:** Alle authentifizierten Benutzer
    """
    logger.info(
        "audit_chain.get_status",
        user_id=str(current_user.id),
        company_id=str(company_id),
    )

    service = MerkleTreeService()

    try:
        report = await service.get_integrity_report(company_id, db)

        return {
            "status": "healthy" if report.integrity_score >= 95 else "degraded",
            "total_entries": report.total_entries,
            "root_hash": report.root_hash,
            "integrity_score": report.integrity_score,
            "last_verified": report.last_verified.isoformat(),
            "violations_count": len(report.violations),
        }
    except Exception as e:
        logger.error(
            "audit_chain.status_failed",
            user_id=str(current_user.id),
            company_id=str(company_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Audit-Chain Status"),
        )


@router.get(
    "/merkle-proof/{entry_hash}",
    response_model=JSONDict,
    summary="Merkle Proof",
    description="Generiert Merkle Proof fuer einzelnen Eintrag"
)
async def get_merkle_proof(
    entry_hash: str,
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> JSONDict:
    """
    Generiert Merkle Proof.

    **Verwendung:**
    - Verifiziere dass bestimmter Audit-Log-Eintrag im Tree existiert
    - Beweise Integritaet ohne kompletten Tree zu uebertragen

    **Parameter:**
    - **entry_hash**: SHA256 Hash des Audit-Log-Eintrags

    **Rollen:** Alle authentifizierten Benutzer
    """
    logger.info(
        "audit_chain.get_merkle_proof",
        entry_hash=entry_hash[:16] + "...",
        user_id=str(current_user.id),
        company_id=str(company_id),
    )

    # Validiere Hash-Format
    if len(entry_hash) != 64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültiger Hash-Format (SHA256 erwartet)",
        )

    service = MerkleTreeService()

    try:
        proof = await service.get_proof(entry_hash, company_id, db)

        if not proof:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Eintrag nicht gefunden",
            )

        return proof.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "audit_chain.merkle_proof_failed",
            entry_hash=entry_hash[:16] + "...",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Merkle Proof"),
        )


@router.post(
    "/verify",
    response_model=JSONDict,
    summary="Proof verifizieren",
    description="Verifiziert Merkle Proof"
)
async def verify_proof(
    request: VerifyProofRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> JSONDict:
    """
    Verifiziert Merkle Proof.

    **Verwendung:**
    - Pruefe ob Proof valide ist
    - Verifiziere Integritaet eines Eintrags

    **Request Body:**
    ```json
    {
        "entry_hash": "abc123...",
        "root_hash": "def456...",
        "proof_path": [
            {"hash": "...", "position": "left"},
            {"hash": "...", "position": "right"}
        ]
    }
    ```

    **Rollen:** Alle authentifizierten Benutzer
    """
    logger.info(
        "audit_chain.verify_proof",
        entry_hash=request.entry_hash[:16] + "...",
        user_id=str(current_user.id),
    )

    service = MerkleTreeService()

    try:
        from app.services.compliance.merkle_tree_service import MerkleProof

        proof = MerkleProof(
            entry_hash=request.entry_hash,
            root_hash=request.root_hash,
            proof_path=request.proof_path,
            verified=False,
        )

        verified = service.verify_proof(proof)

        return {
            "verified": verified,
            "entry_hash": request.entry_hash,
            "root_hash": request.root_hash,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(
            "audit_chain.verify_proof_failed",
            entry_hash=request.entry_hash[:16] + "...",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Proof-Verifikation"),
        )


@router.get(
    "/integrity-report",
    response_model=JSONDict,
    summary="Integritaets-Report",
    description="Detaillierter Integritaets-Report der Audit-Chain"
)
async def get_integrity_report(
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> JSONDict:
    """
    Holt Integritaets-Report.

    **Enthaelt:**
    - Anzahl verifizierter Eintraege
    - Integritaets-Score (0-100)
    - Erkannte Verletzungen
    - Root Hash
    - Letztes Verifikations-Datum

    **Rollen:** Alle authentifizierten Benutzer
    """
    logger.info(
        "audit_chain.get_integrity_report",
        user_id=str(current_user.id),
        company_id=str(company_id),
    )

    service = MerkleTreeService()

    try:
        report = await service.get_integrity_report(company_id, db)
        return report.to_dict()
    except Exception as e:
        logger.error(
            "audit_chain.integrity_report_failed",
            user_id=str(current_user.id),
            company_id=str(company_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Integritaets-Report"),
        )


@router.post(
    "/export",
    summary="Chain exportieren",
    description="Exportiert Audit-Chain mit Merkle Tree (JSON)",
    response_class=Response,
)
async def export_chain(
    from_date: datetime = Query(
        default=None,
        description="Start-Datum (ISO 8601)",
    ),
    to_date: datetime = Query(
        default=None,
        description="End-Datum (ISO 8601)",
    ),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Exportiert Audit-Chain.

    **Format:** JSON mit:
    - Audit-Logs im Zeitraum
    - Merkle Tree (Root + alle Nodes)
    - Metadaten (Company, Export-Datum)

    **Parameter:**
    - **from_date**: Start-Datum (default: vor 30 Tagen)
    - **to_date**: End-Datum (default: jetzt)

    **Rollen:** Alle authentifizierten Benutzer
    """
    # Default-Werte
    now = datetime.now(timezone.utc)
    if not to_date:
        to_date = now
    if not from_date:
        from_date = now - timedelta(days=30)

    logger.info(
        "audit_chain.export",
        user_id=str(current_user.id),
        company_id=str(company_id),
        from_date=from_date.isoformat(),
        to_date=to_date.isoformat(),
    )

    service = MerkleTreeService()

    try:
        export_data = await service.export_chain(company_id, from_date, to_date, db)

        return Response(
            content=export_data,
            media_type="application/json",
            headers={
                "Content-Disposition": build_content_disposition(f"audit_chain_{company_id}_{now.strftime('%Y%m%d')}.json", "attachment")
            },
        )
    except Exception as e:
        logger.error(
            "audit_chain.export_failed",
            user_id=str(current_user.id),
            company_id=str(company_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Audit-Chain Export"),
        )
