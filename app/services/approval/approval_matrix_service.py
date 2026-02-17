"""Approval Matrix Service - Betrags-/Abteilungsbasierte Genehmigungsmatrix.

Enterprise Feature: Verwaltet automatisches Routing von Genehmigungen basierend auf:
- Betragsgrenzen
- Abteilungen
- Dokumenttypen
- Vier-Augen-Prinzip
"""

from __future__ import annotations

import structlog
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional, List, Dict
from uuid import UUID

from sqlalchemy import and_, select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models_approval_matrix import (
    ApprovalMatrix,
    ApprovalChainTemplate,
    ApprovalGroup,
    ApprovalGroupMember,
)

logger = structlog.get_logger(__name__)


@dataclass
class MatrixMatch:
    """Ergebnis eines Matrix-Lookups."""
    matrix_id: UUID
    chain_template_id: Optional[UUID]
    four_eyes_required: bool
    min_approvers: int
    priority: int
    steps_config: List[Dict[str, Any]]


class ApprovalMatrixService:
    """Service fuer Genehmigungsmatrix-Verwaltung.

    Verwaltet:
    - Matrix-Eintraege (CRUD)
    - Chain-Templates
    - Matrix-Lookup fuer Routing
    - Vier-Augen-Prinzip Pruefung
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den ApprovalMatrixService.

        Args:
            db: Async Database Session
        """
        self.db = db

    async def find_matching_matrix(
        self,
        company_id: UUID,
        department: str,
        amount: Decimal,
        document_type: Optional[str] = None,
    ) -> Optional[MatrixMatch]:
        """Findet den passenden Matrix-Eintrag fuer eine Genehmigung.

        Matching-Logik:
        1. Exakter Match: department + document_type + amount
        2. Fallback: department + NULL document_type + amount
        3. Bei mehreren Matches: Hoechste Prioritaet

        Args:
            company_id: Firmen-ID
            department: Abteilung (z.B. "Einkauf", "Finanzen")
            amount: Betrag
            document_type: Optionaler Dokumenttyp (z.B. "invoice")

        Returns:
            MatrixMatch oder None wenn kein Match
        """
        logger.info(
            "matrix_lookup_start",
            company_id=str(company_id),
            department=department,
            amount=str(amount),
            document_type=document_type,
        )

        # Query: Active matrices fuer company + department
        base_conditions = [
            ApprovalMatrix.company_id == company_id,
            ApprovalMatrix.department == department,
            ApprovalMatrix.is_active.is_(True),
        ]

        # Amount Range Filter
        amount_conditions = and_(
            ApprovalMatrix.amount_min <= amount,
            or_(
                ApprovalMatrix.amount_max.is_(None),  # Unbegrenzt
                ApprovalMatrix.amount_max >= amount,
            ),
        )

        # Try exact match first (with document_type)
        if document_type:
            query_exact = (
                select(ApprovalMatrix)
                .options(selectinload(ApprovalMatrix.chain_template))
                .where(
                    and_(
                        *base_conditions,
                        ApprovalMatrix.document_type == document_type,
                        amount_conditions,
                    )
                )
                .order_by(ApprovalMatrix.priority.desc())
            )
            result = await self.db.execute(query_exact)
            matrix = result.scalars().first()

            if matrix:
                return await self._build_matrix_match(matrix)

        # Fallback: NULL document_type (general rule)
        query_fallback = (
            select(ApprovalMatrix)
            .options(selectinload(ApprovalMatrix.chain_template))
            .where(
                and_(
                    *base_conditions,
                    ApprovalMatrix.document_type.is_(None),
                    amount_conditions,
                )
            )
            .order_by(ApprovalMatrix.priority.desc())
        )
        result = await self.db.execute(query_fallback)
        matrix = result.scalars().first()

        if matrix:
            return await self._build_matrix_match(matrix)

        logger.warning(
            "no_matrix_match",
            company_id=str(company_id),
            department=department,
            amount=str(amount),
        )
        return None

    async def _build_matrix_match(self, matrix: ApprovalMatrix) -> MatrixMatch:
        """Baut MatrixMatch aus ApprovalMatrix."""
        steps_config = []
        if matrix.chain_template:
            steps_config = matrix.chain_template.steps_config or []

        return MatrixMatch(
            matrix_id=matrix.id,
            chain_template_id=matrix.chain_template_id,
            four_eyes_required=matrix.four_eyes_required,
            min_approvers=matrix.min_approvers,
            priority=matrix.priority,
            steps_config=steps_config,
        )

    async def build_approval_chain(
        self,
        matrix_match: MatrixMatch,
    ) -> List[Dict[str, Any]]:
        """Baut die Approval Chain aus einem Matrix Match.

        Args:
            matrix_match: Ergebnis von find_matching_matrix

        Returns:
            Liste von Approval Steps
        """
        chain = []
        for step_config in matrix_match.steps_config:
            chain.append({
                "step": step_config.get("step", len(chain) + 1),
                "type": step_config.get("approver_type", "user"),
                "value": step_config.get("approver_id", ""),
                "required": step_config.get("required", True),
                "timeout_hours": step_config.get("timeout_hours", 48),
            })
        return chain

    async def check_four_eyes_principle(
        self,
        request_id: UUID,
        approver_id: UUID,
        matrix_match: MatrixMatch,
    ) -> bool:
        """Prueft ob Vier-Augen-Prinzip erfuellt ist.

        Das Vier-Augen-Prinzip verlangt, dass mindestens min_approvers
        verschiedene Personen genehmigen.

        Args:
            request_id: ID der Approval Request
            approver_id: ID des aktuellen Genehmigers
            matrix_match: Matrix Match mit four_eyes_required Flag

        Returns:
            True wenn Vier-Augen-Prinzip erfuellt, False sonst
        """
        if not matrix_match.four_eyes_required:
            return True

        # Query: Count distinct approvers who already approved this request
        from app.db.models import ApprovalStep, ApprovalStatus

        query = (
            select(ApprovalStep)
            .where(
                and_(
                    ApprovalStep.approval_request_id == request_id,
                    ApprovalStep.status == ApprovalStatus.APPROVED,
                )
            )
        )
        result = await self.db.execute(query)
        approved_steps = result.scalars().all()

        # Get unique approver IDs
        unique_approvers = set()
        for step in approved_steps:
            if step.decision_by_id:
                unique_approvers.add(step.decision_by_id)

        # Add current approver
        unique_approvers.add(approver_id)

        logger.info(
            "four_eyes_check",
            request_id=str(request_id),
            unique_approvers=len(unique_approvers),
            min_required=matrix_match.min_approvers,
        )

        return len(unique_approvers) >= matrix_match.min_approvers

    # =========================================================================
    # Matrix CRUD
    # =========================================================================

    async def create_matrix_entry(
        self,
        company_id: UUID,
        department: str,
        amount_min: Decimal,
        amount_max: Optional[Decimal],
        chain_template_id: Optional[UUID],
        created_by_id: Optional[UUID] = None,
        document_type: Optional[str] = None,
        four_eyes_required: bool = False,
        min_approvers: int = 1,
        priority: int = 0,
    ) -> ApprovalMatrix:
        """Erstellt einen neuen Matrix-Eintrag.

        Args:
            company_id: Firmen-ID
            department: Abteilung
            amount_min: Mindestbetrag
            amount_max: Hoechstbetrag (NULL = unbegrenzt)
            chain_template_id: Chain Template ID
            created_by_id: Ersteller User ID
            document_type: Optionaler Dokumenttyp
            four_eyes_required: Vier-Augen-Prinzip
            min_approvers: Mindestanzahl Genehmiger
            priority: Prioritaet bei Ueberlappung

        Returns:
            Erstellte ApprovalMatrix
        """
        matrix = ApprovalMatrix(
            company_id=company_id,
            department=department,
            amount_min=amount_min,
            amount_max=amount_max,
            chain_template_id=chain_template_id,
            document_type=document_type,
            four_eyes_required=four_eyes_required,
            min_approvers=min_approvers,
            priority=priority,
            created_by_id=created_by_id,
        )
        self.db.add(matrix)
        await self.db.commit()
        await self.db.refresh(matrix)

        logger.info("matrix_entry_created", matrix_id=str(matrix.id))
        return matrix

    async def update_matrix_entry(
        self,
        matrix_id: UUID,
        **updates: Any,
    ) -> Optional[ApprovalMatrix]:
        """Aktualisiert einen Matrix-Eintrag.

        Args:
            matrix_id: Matrix ID
            **updates: Update-Felder

        Returns:
            Aktualisierte ApprovalMatrix oder None
        """
        query = select(ApprovalMatrix).where(ApprovalMatrix.id == matrix_id)
        result = await self.db.execute(query)
        matrix = result.scalar_one_or_none()

        if not matrix:
            return None

        for key, value in updates.items():
            if hasattr(matrix, key):
                setattr(matrix, key, value)

        await self.db.commit()
        await self.db.refresh(matrix)

        logger.info("matrix_entry_updated", matrix_id=str(matrix_id))
        return matrix

    async def delete_matrix_entry(
        self,
        matrix_id: UUID,
    ) -> bool:
        """Deaktiviert einen Matrix-Eintrag (Soft Delete).

        Args:
            matrix_id: Matrix ID

        Returns:
            True wenn erfolgreich
        """
        return await self.update_matrix_entry(matrix_id, is_active=False) is not None

    async def list_matrix_entries(
        self,
        company_id: UUID,
        department: Optional[str] = None,
        active_only: bool = True,
    ) -> List[ApprovalMatrix]:
        """Listet Matrix-Eintraege auf.

        Args:
            company_id: Firmen-ID
            department: Optionaler Abteilungsfilter
            active_only: Nur aktive Eintraege

        Returns:
            Liste von ApprovalMatrix
        """
        conditions = [ApprovalMatrix.company_id == company_id]

        if department:
            conditions.append(ApprovalMatrix.department == department)

        if active_only:
            conditions.append(ApprovalMatrix.is_active.is_(True))

        query = (
            select(ApprovalMatrix)
            .options(selectinload(ApprovalMatrix.chain_template))
            .where(and_(*conditions))
            .order_by(ApprovalMatrix.priority.desc(), ApprovalMatrix.amount_min)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    # =========================================================================
    # Chain Template CRUD
    # =========================================================================

    async def create_chain_template(
        self,
        company_id: UUID,
        name: str,
        steps_config: List[Dict[str, Any]],
        created_by_id: Optional[UUID] = None,
        description: Optional[str] = None,
        is_default: bool = False,
    ) -> ApprovalChainTemplate:
        """Erstellt eine neue Chain Template.

        Args:
            company_id: Firmen-ID
            name: Template-Name
            steps_config: Schritte-Konfiguration
            created_by_id: Ersteller User ID
            description: Beschreibung
            is_default: Standard-Template

        Returns:
            Erstellte ApprovalChainTemplate
        """
        template = ApprovalChainTemplate(
            company_id=company_id,
            name=name,
            steps_config=steps_config,
            description=description,
            is_default=is_default,
            created_by_id=created_by_id,
        )
        self.db.add(template)
        await self.db.commit()
        await self.db.refresh(template)

        logger.info("chain_template_created", template_id=str(template.id))
        return template

    async def list_chain_templates(
        self,
        company_id: UUID,
        active_only: bool = True,
    ) -> List[ApprovalChainTemplate]:
        """Listet Chain Templates auf.

        Args:
            company_id: Firmen-ID
            active_only: Nur aktive Templates

        Returns:
            Liste von ApprovalChainTemplate
        """
        conditions = [ApprovalChainTemplate.company_id == company_id]

        if active_only:
            conditions.append(ApprovalChainTemplate.is_active.is_(True))

        query = (
            select(ApprovalChainTemplate)
            .where(and_(*conditions))
            .order_by(ApprovalChainTemplate.is_default.desc(), ApprovalChainTemplate.name)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())
