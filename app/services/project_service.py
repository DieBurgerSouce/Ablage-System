"""
Project Management Service - Vision 2026

Business logic for managing projects including:
- CRUD operations
- Team member management
- Document assignment (manual and auto-assign)
- Budget tracking integration
- KI-basierte Auto-Zuweisung basierend auf Kunden/Entity-Patterns
"""

from dataclasses import dataclass
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, asc, update, delete
from sqlalchemy.orm import selectinload

import structlog

from app.db.models import Document, BusinessEntity, Company
from app.db.models_project import (
    Project,
    ProjectMember,
    DocumentProjectAssignment,
    ProjectStatus,
    ProjectPriority,
    ProjectMemberRole,
    DocumentAssignmentType,
)
from app.db.models_budget import Kostenstelle

logger = structlog.get_logger(__name__)


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class ProjectSummary:
    """Zusammenfassung der Projekt-Statistiken."""
    total_projects: int
    active_projects: int
    completed_projects: int
    on_hold_projects: int
    total_budget: Decimal
    total_spent: Decimal
    overdue_count: int


@dataclass
class ProjectDocumentStats:
    """Dokumenten-Statistiken eines Projekts."""
    total_documents: int
    invoices: int
    contracts: int
    correspondence: int
    other: int
    auto_assigned: int
    manual_assigned: int


@dataclass
class AutoAssignmentResult:
    """Ergebnis einer automatischen Dokument-Zuweisung."""
    document_id: UUID
    project_id: UUID
    confidence: float
    assignment_reason: str
    assignment_type: str
    auto_assigned: bool


# =============================================================================
# Project Service
# =============================================================================


class ProjectService:
    """
    Service für Projekt-Management.

    Features:
    - CRUD Operationen
    - Team-Mitglieder-Verwaltung
    - Dokument-Zuweisungen
    - Budget-Tracking
    - KI-basierte Auto-Zuweisung
    """

    # -------------------------------------------------------------------------
    # CRUD Operations
    # -------------------------------------------------------------------------

    async def create_project(
        self,
        db: AsyncSession,
        company_id: UUID,
        code: str,
        name: str,
        *,
        description: Optional[str] = None,
        client_id: Optional[UUID] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        budget: Optional[Decimal] = None,
        currency: str = "EUR",
        kostenstelle_id: Optional[UUID] = None,
        manager_id: Optional[UUID] = None,
        priority: str = ProjectPriority.MEDIUM.value,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        created_by_id: Optional[UUID] = None,
    ) -> Project:
        """Neues Projekt erstellen."""
        logger.info(
            "Erstelle neues Projekt",
            company_id=str(company_id),
            code=code,
            name=name
        )

        project = Project(
            company_id=company_id,
            code=code,
            name=name,
            description=description,
            client_id=client_id,
            status=ProjectStatus.PLANNING.value,
            start_date=start_date,
            end_date=end_date,
            budget=budget,
            currency=currency,
            kostenstelle_id=kostenstelle_id,
            manager_id=manager_id,
            priority=priority,
            category=category,
            tags=tags or [],
            created_by_id=created_by_id,
        )

        db.add(project)
        await db.flush()
        await db.refresh(project)

        logger.info("Projekt erstellt", project_id=str(project.id), code=code)
        return project

    async def get_project(
        self,
        db: AsyncSession,
        project_id: UUID,
        *,
        include_members: bool = False,
        include_documents: bool = False,
    ) -> Optional[Project]:
        """Projekt anhand ID abrufen."""
        query = select(Project).where(Project.id == project_id)

        if include_members:
            query = query.options(selectinload(Project.members))
        if include_documents:
            query = query.options(selectinload(Project.document_assignments))

        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_project_by_code(
        self,
        db: AsyncSession,
        company_id: UUID,
        code: str,
    ) -> Optional[Project]:
        """Projekt anhand Code abrufen."""
        query = select(Project).where(
            and_(
                Project.company_id == company_id,
                Project.code == code
            )
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def list_projects(
        self,
        db: AsyncSession,
        company_id: UUID,
        *,
        status: Optional[str] = None,
        client_id: Optional[UUID] = None,
        manager_id: Optional[UUID] = None,
        kostenstelle_id: Optional[UUID] = None,
        search: Optional[str] = None,
        include_archived: bool = False,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Project], int]:
        """Projekte auflisten mit Filterung und Paginierung."""
        # Base query
        query = select(Project).where(Project.company_id == company_id)

        # Filters
        if status:
            query = query.where(Project.status == status)
        elif not include_archived:
            query = query.where(Project.status != ProjectStatus.ARCHIVED.value)

        if client_id:
            query = query.where(Project.client_id == client_id)
        if manager_id:
            query = query.where(Project.manager_id == manager_id)
        if kostenstelle_id:
            query = query.where(Project.kostenstelle_id == kostenstelle_id)

        if search:
            search_filter = or_(
                Project.name.ilike(f"%{search}%"),
                Project.code.ilike(f"%{search}%"),
                Project.description.ilike(f"%{search}%"),
            )
            query = query.where(search_filter)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Sorting
        sort_column = getattr(Project, sort_by, Project.created_at)
        if sort_order == "asc":
            query = query.order_by(asc(sort_column))
        else:
            query = query.order_by(desc(sort_column))

        # Pagination
        query = query.offset(offset).limit(limit)

        # Execute
        result = await db.execute(query)
        projects = list(result.scalars().all())

        return projects, total

    async def update_project(
        self,
        db: AsyncSession,
        project_id: UUID,
        **update_data: object,
    ) -> Optional[Project]:
        """Projekt aktualisieren."""
        project = await self.get_project(db, project_id)
        if not project:
            return None

        # Whitelist von aktualisierbaren Feldern
        allowed_fields = {
            "name", "description", "client_id", "status", "start_date",
            "end_date", "actual_start_date", "actual_end_date", "budget",
            "budget_spent", "currency", "kostenstelle_id", "manager_id",
            "priority", "category", "tags", "metadata",
        }

        for key, value in update_data.items():
            if key in allowed_fields and value is not None:
                setattr(project, key, value)

        await db.flush()
        await db.refresh(project)

        logger.info("Projekt aktualisiert", project_id=str(project_id))
        return project

    async def delete_project(
        self,
        db: AsyncSession,
        project_id: UUID,
        *,
        soft_delete: bool = True,
    ) -> bool:
        """Projekt löschen (soft delete = archivieren)."""
        project = await self.get_project(db, project_id)
        if not project:
            return False

        if soft_delete:
            project.status = ProjectStatus.ARCHIVED.value
            await db.flush()
            logger.info("Projekt archiviert", project_id=str(project_id))
        else:
            await db.delete(project)
            await db.flush()
            logger.info("Projekt gelöscht", project_id=str(project_id))

        return True

    # -------------------------------------------------------------------------
    # Status Management
    # -------------------------------------------------------------------------

    async def activate_project(
        self,
        db: AsyncSession,
        project_id: UUID,
    ) -> Optional[Project]:
        """Projekt aktivieren."""
        project = await self.get_project(db, project_id)
        if not project:
            return None

        project.status = ProjectStatus.ACTIVE.value
        if not project.actual_start_date:
            project.actual_start_date = date.today()

        await db.flush()
        logger.info("Projekt aktiviert", project_id=str(project_id))
        return project

    async def complete_project(
        self,
        db: AsyncSession,
        project_id: UUID,
    ) -> Optional[Project]:
        """Projekt abschließen."""
        project = await self.get_project(db, project_id)
        if not project:
            return None

        project.status = ProjectStatus.COMPLETED.value
        project.actual_end_date = date.today()

        await db.flush()
        logger.info("Projekt abgeschlossen", project_id=str(project_id))
        return project

    # -------------------------------------------------------------------------
    # Team Member Management
    # -------------------------------------------------------------------------

    async def add_member(
        self,
        db: AsyncSession,
        project_id: UUID,
        user_id: UUID,
        *,
        role: str = ProjectMemberRole.MEMBER.value,
        permissions: Optional[List[str]] = None,
        valid_from: Optional[date] = None,
        valid_until: Optional[date] = None,
        allocation_percent: Optional[int] = None,
    ) -> ProjectMember:
        """Mitglied zum Projekt hinzufuegen."""
        # Check if already member
        existing = await self._get_member(db, project_id, user_id)
        if existing:
            raise ValueError("Benutzer ist bereits Projektmitglied")

        member = ProjectMember(
            project_id=project_id,
            user_id=user_id,
            role=role,
            permissions=permissions or [],
            valid_from=valid_from,
            valid_until=valid_until,
            allocation_percent=allocation_percent,
        )

        db.add(member)
        await db.flush()
        await db.refresh(member)

        logger.info(
            "Projektmitglied hinzugefuegt",
            project_id=str(project_id),
            user_id=str(user_id),
            role=role
        )
        return member

    async def remove_member(
        self,
        db: AsyncSession,
        project_id: UUID,
        user_id: UUID,
    ) -> bool:
        """Mitglied aus Projekt entfernen."""
        member = await self._get_member(db, project_id, user_id)
        if not member:
            return False

        await db.delete(member)
        await db.flush()

        logger.info(
            "Projektmitglied entfernt",
            project_id=str(project_id),
            user_id=str(user_id)
        )
        return True

    async def update_member_role(
        self,
        db: AsyncSession,
        project_id: UUID,
        user_id: UUID,
        role: str,
    ) -> Optional[ProjectMember]:
        """Mitglieder-Rolle aktualisieren."""
        member = await self._get_member(db, project_id, user_id)
        if not member:
            return None

        member.role = role
        await db.flush()
        await db.refresh(member)

        logger.info(
            "Mitglieder-Rolle aktualisiert",
            project_id=str(project_id),
            user_id=str(user_id),
            role=role
        )
        return member

    async def list_members(
        self,
        db: AsyncSession,
        project_id: UUID,
        *,
        active_only: bool = True,
    ) -> List[ProjectMember]:
        """Projektmitglieder auflisten."""
        query = select(ProjectMember).where(
            ProjectMember.project_id == project_id
        )

        if active_only:
            query = query.where(ProjectMember.is_active == True)

        result = await db.execute(query)
        return list(result.scalars().all())

    async def _get_member(
        self,
        db: AsyncSession,
        project_id: UUID,
        user_id: UUID,
    ) -> Optional[ProjectMember]:
        """Einzelnes Projektmitglied abrufen."""
        query = select(ProjectMember).where(
            and_(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id
            )
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    # -------------------------------------------------------------------------
    # Document Assignment
    # -------------------------------------------------------------------------

    async def assign_document(
        self,
        db: AsyncSession,
        document_id: UUID,
        project_id: UUID,
        company_id: UUID,
        *,
        assignment_type: str = DocumentAssignmentType.GENERAL.value,
        assigned_by_id: Optional[UUID] = None,
        auto_assigned: bool = False,
        confidence: Optional[float] = None,
        assignment_reason: Optional[str] = None,
    ) -> DocumentProjectAssignment:
        """Dokument einem Projekt zuweisen."""
        # Check if already assigned
        existing = await self._get_assignment(db, document_id, project_id)
        if existing:
            raise ValueError("Dokument ist bereits diesem Projekt zugewiesen")

        assignment = DocumentProjectAssignment(
            document_id=document_id,
            project_id=project_id,
            company_id=company_id,
            assignment_type=assignment_type,
            assigned_by_id=assigned_by_id,
            auto_assigned=auto_assigned,
            confidence=confidence,
            assignment_reason=assignment_reason,
        )

        db.add(assignment)
        await db.flush()
        await db.refresh(assignment)

        # Update project document count
        await self._update_project_counts(db, project_id)

        logger.info(
            "Dokument zugewiesen",
            document_id=str(document_id),
            project_id=str(project_id),
            auto_assigned=auto_assigned
        )
        return assignment

    async def unassign_document(
        self,
        db: AsyncSession,
        document_id: UUID,
        project_id: UUID,
    ) -> bool:
        """Dokument-Zuweisung entfernen."""
        assignment = await self._get_assignment(db, document_id, project_id)
        if not assignment:
            return False

        await db.delete(assignment)
        await db.flush()

        # Update project document count
        await self._update_project_counts(db, project_id)

        logger.info(
            "Dokument-Zuweisung entfernt",
            document_id=str(document_id),
            project_id=str(project_id)
        )
        return True

    async def list_project_documents(
        self,
        db: AsyncSession,
        project_id: UUID,
        *,
        assignment_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[DocumentProjectAssignment], int]:
        """Dokumente eines Projekts auflisten."""
        query = select(DocumentProjectAssignment).where(
            DocumentProjectAssignment.project_id == project_id
        )

        if assignment_type:
            query = query.where(
                DocumentProjectAssignment.assignment_type == assignment_type
            )

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Get assignments
        query = query.order_by(desc(DocumentProjectAssignment.assigned_at))
        query = query.offset(offset).limit(limit)

        result = await db.execute(query)
        assignments = list(result.scalars().all())

        return assignments, total

    async def _get_assignment(
        self,
        db: AsyncSession,
        document_id: UUID,
        project_id: UUID,
    ) -> Optional[DocumentProjectAssignment]:
        """Einzelne Zuweisung abrufen."""
        query = select(DocumentProjectAssignment).where(
            and_(
                DocumentProjectAssignment.document_id == document_id,
                DocumentProjectAssignment.project_id == project_id
            )
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def _update_project_counts(
        self,
        db: AsyncSession,
        project_id: UUID,
    ) -> None:
        """Projekt-Zähler aktualisieren."""
        # Count documents
        count_query = select(func.count()).where(
            DocumentProjectAssignment.project_id == project_id
        )
        result = await db.execute(count_query)
        doc_count = result.scalar() or 0

        # Count invoices
        invoice_query = select(func.count()).where(
            and_(
                DocumentProjectAssignment.project_id == project_id,
                DocumentProjectAssignment.assignment_type == DocumentAssignmentType.INVOICE.value
            )
        )
        result = await db.execute(invoice_query)
        invoice_count = result.scalar() or 0

        # Update project
        await db.execute(
            update(Project)
            .where(Project.id == project_id)
            .values(
                document_count=doc_count,
                invoice_count=invoice_count
            )
        )

    # -------------------------------------------------------------------------
    # Auto-Assignment (KI-Feature)
    # -------------------------------------------------------------------------

    async def suggest_project_for_document(
        self,
        db: AsyncSession,
        document_id: UUID,
        company_id: UUID,
    ) -> List[AutoAssignmentResult]:
        """
        KI-basierte Projekt-Vorschläge für ein Dokument.

        Matching-Strategien:
        1. Entity-Match: Dokument-Entity = Projekt-Client (95% Confidence)
        2. Kostenstelle-Match: Gleiche Kostenstelle (85% Confidence)
        3. Tag-Overlap: Gemeinsame Tags (75% Confidence)
        4. Pattern-Match: Betreff/Text-Analyse (70% Confidence)
        """
        suggestions: List[AutoAssignmentResult] = []

        # Get document with entity
        doc_query = select(Document).where(Document.id == document_id)
        doc_result = await db.execute(doc_query)
        document = doc_result.scalar_one_or_none()

        if not document:
            return suggestions

        # Get active projects
        projects_query = select(Project).where(
            and_(
                Project.company_id == company_id,
                Project.status.in_([
                    ProjectStatus.PLANNING.value,
                    ProjectStatus.ACTIVE.value
                ])
            )
        )
        projects_result = await db.execute(projects_query)
        projects = list(projects_result.scalars().all())

        for project in projects:
            confidence = 0.0
            reasons = []

            # Strategy 1: Entity Match (Client)
            if document.business_entity_id and project.client_id:
                if document.business_entity_id == project.client_id:
                    confidence = max(confidence, 0.95)
                    reasons.append("Kunde stimmt überein")

            # Strategy 2: Kostenstelle Match (from document metadata)
            if project.kostenstelle_id:
                doc_kostenstelle = document.document_metadata.get("kostenstelle_id")
                if doc_kostenstelle and str(project.kostenstelle_id) == str(doc_kostenstelle):
                    confidence = max(confidence, 0.85)
                    reasons.append("Kostenstelle stimmt überein")

            # Strategy 3: Tag Overlap
            if project.tags and hasattr(document, 'tags'):
                doc_tags = set([t.name for t in document.tags] if document.tags else [])
                project_tags = set(project.tags)
                overlap = doc_tags & project_tags
                if overlap:
                    tag_confidence = min(0.75, 0.5 + (len(overlap) * 0.1))
                    if tag_confidence > confidence:
                        confidence = tag_confidence
                        reasons.append(f"Tags überlappen: {', '.join(overlap)}")

            # Strategy 4: Project Code in Document
            if document.extracted_text:
                text_lower = document.extracted_text.lower()
                if project.code.lower() in text_lower:
                    confidence = max(confidence, 0.90)
                    reasons.append(f"Projekt-Code '{project.code}' im Dokument gefunden")
                elif project.name.lower() in text_lower:
                    confidence = max(confidence, 0.80)
                    reasons.append(f"Projekt-Name '{project.name}' im Dokument gefunden")

            # Only suggest if confidence >= 70%
            if confidence >= 0.70:
                # Determine assignment type based on document type
                assignment_type = self._determine_assignment_type(document)

                suggestions.append(AutoAssignmentResult(
                    document_id=document_id,
                    project_id=project.id,
                    confidence=confidence,
                    assignment_reason=" | ".join(reasons),
                    assignment_type=assignment_type,
                    auto_assigned=False,
                ))

        # Sort by confidence descending
        suggestions.sort(key=lambda x: x.confidence, reverse=True)

        logger.info(
            "Projekt-Vorschläge generiert",
            document_id=str(document_id),
            suggestion_count=len(suggestions)
        )
        return suggestions

    async def auto_assign_document(
        self,
        db: AsyncSession,
        document_id: UUID,
        company_id: UUID,
        *,
        min_confidence: float = 0.85,
    ) -> Optional[AutoAssignmentResult]:
        """
        Automatische Projekt-Zuweisung wenn Confidence >= Schwellenwert.

        Returns None wenn keine Zuweisung mit ausreichender Confidence.
        """
        suggestions = await self.suggest_project_for_document(
            db, document_id, company_id
        )

        if not suggestions:
            return None

        best_suggestion = suggestions[0]
        if best_suggestion.confidence < min_confidence:
            logger.info(
                "Auto-Zuweisung abgelehnt: Confidence zu niedrig",
                document_id=str(document_id),
                best_confidence=best_suggestion.confidence,
                threshold=min_confidence
            )
            return None

        # Perform assignment
        await self.assign_document(
            db,
            document_id=document_id,
            project_id=best_suggestion.project_id,
            company_id=company_id,
            assignment_type=best_suggestion.assignment_type,
            auto_assigned=True,
            confidence=best_suggestion.confidence,
            assignment_reason=best_suggestion.assignment_reason,
        )

        best_suggestion.auto_assigned = True

        logger.info(
            "Dokument automatisch zugewiesen",
            document_id=str(document_id),
            project_id=str(best_suggestion.project_id),
            confidence=best_suggestion.confidence
        )
        return best_suggestion

    def _determine_assignment_type(self, document: Document) -> str:
        """Bestimmt den Assignment-Typ basierend auf Dokumenttyp."""
        doc_type = document.document_type or ""

        if doc_type in ["invoice", "credit_note", "dunning"]:
            return DocumentAssignmentType.INVOICE.value
        elif doc_type in ["contract"]:
            return DocumentAssignmentType.CONTRACT.value
        elif doc_type in ["letter", "correspondence"]:
            return DocumentAssignmentType.CORRESPONDENCE.value
        elif doc_type in ["report"]:
            return DocumentAssignmentType.REPORT.value
        elif doc_type in ["delivery_note", "order", "offer"]:
            return DocumentAssignmentType.DELIVERABLE.value
        else:
            return DocumentAssignmentType.GENERAL.value

    # -------------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------------

    async def get_project_summary(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> ProjectSummary:
        """Projekt-Zusammenfassung für Company."""
        # Total and status counts
        status_counts = await db.execute(
            select(
                Project.status,
                func.count(Project.id).label("count")
            )
            .where(Project.company_id == company_id)
            .group_by(Project.status)
        )

        counts_by_status = {row.status: row.count for row in status_counts}

        total = sum(counts_by_status.values())
        active = counts_by_status.get(ProjectStatus.ACTIVE.value, 0)
        completed = counts_by_status.get(ProjectStatus.COMPLETED.value, 0)
        on_hold = counts_by_status.get(ProjectStatus.ON_HOLD.value, 0)

        # Budget totals
        budget_result = await db.execute(
            select(
                func.coalesce(func.sum(Project.budget), 0).label("total_budget"),
                func.coalesce(func.sum(Project.budget_spent), 0).label("total_spent")
            )
            .where(
                and_(
                    Project.company_id == company_id,
                    Project.status.in_([
                        ProjectStatus.PLANNING.value,
                        ProjectStatus.ACTIVE.value,
                        ProjectStatus.ON_HOLD.value
                    ])
                )
            )
        )
        budget_row = budget_result.one()

        # Overdue count
        today = date.today()
        overdue_result = await db.execute(
            select(func.count(Project.id))
            .where(
                and_(
                    Project.company_id == company_id,
                    Project.end_date < today,
                    Project.status.in_([
                        ProjectStatus.PLANNING.value,
                        ProjectStatus.ACTIVE.value,
                        ProjectStatus.ON_HOLD.value
                    ])
                )
            )
        )
        overdue_count = overdue_result.scalar() or 0

        return ProjectSummary(
            total_projects=total,
            active_projects=active,
            completed_projects=completed,
            on_hold_projects=on_hold,
            total_budget=Decimal(str(budget_row.total_budget)),
            total_spent=Decimal(str(budget_row.total_spent)),
            overdue_count=overdue_count,
        )

    async def get_project_document_stats(
        self,
        db: AsyncSession,
        project_id: UUID,
    ) -> ProjectDocumentStats:
        """Dokumenten-Statistiken eines Projekts."""
        # Type counts
        type_counts = await db.execute(
            select(
                DocumentProjectAssignment.assignment_type,
                func.count(DocumentProjectAssignment.id).label("count")
            )
            .where(DocumentProjectAssignment.project_id == project_id)
            .group_by(DocumentProjectAssignment.assignment_type)
        )

        counts_by_type = {row.assignment_type: row.count for row in type_counts}

        # Auto vs manual
        auto_count = await db.execute(
            select(func.count(DocumentProjectAssignment.id))
            .where(
                and_(
                    DocumentProjectAssignment.project_id == project_id,
                    DocumentProjectAssignment.auto_assigned == True
                )
            )
        )
        auto_assigned = auto_count.scalar() or 0

        total = sum(counts_by_type.values())
        manual_assigned = total - auto_assigned

        return ProjectDocumentStats(
            total_documents=total,
            invoices=counts_by_type.get(DocumentAssignmentType.INVOICE.value, 0),
            contracts=counts_by_type.get(DocumentAssignmentType.CONTRACT.value, 0),
            correspondence=counts_by_type.get(DocumentAssignmentType.CORRESPONDENCE.value, 0),
            other=counts_by_type.get(DocumentAssignmentType.GENERAL.value, 0),
            auto_assigned=auto_assigned,
            manual_assigned=manual_assigned,
        )


# Singleton instance
project_service = ProjectService()
