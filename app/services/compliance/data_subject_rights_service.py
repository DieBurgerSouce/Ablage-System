# -*- coding: utf-8 -*-
"""GDPR Data Subject Rights Service - Betroffenenrechte nach DSGVO Art. 15-21.

PHASE 7: Compliance & Audit - GDPR Erweiterungen

Implementiert die Betroffenenrechte nach DSGVO:
- Art. 15: Auskunftsrecht (Right of Access)
- Art. 16: Recht auf Berichtigung (Right to Rectification)
- Art. 17: Recht auf Loeschung (Right to Erasure / "Right to be Forgotten")
- Art. 18: Recht auf Einschraenkung der Verarbeitung (Right to Restriction)
- Art. 20: Recht auf Datenuebertragbarkeit (Right to Data Portability)
- Art. 21: Widerspruchsrecht (Right to Object)

WICHTIG: 30-Tage-Frist fuer Bearbeitung von Anfragen!
"""

import hashlib
import json
import os
import uuid
import zipfile
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import tempfile

import structlog
from sqlalchemy import select, func, and_, or_, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums & Constants
# =============================================================================

class DSRType(str, Enum):
    """Typen von Betroffenenrechte-Anfragen (DSGVO Art. 15-21)."""
    ACCESS = "access"                # Art. 15 - Auskunftsrecht
    RECTIFICATION = "rectification"  # Art. 16 - Berichtigung
    ERASURE = "erasure"              # Art. 17 - Loeschung
    RESTRICTION = "restriction"      # Art. 18 - Einschraenkung
    PORTABILITY = "portability"      # Art. 20 - Datenuebertragbarkeit
    OBJECTION = "objection"          # Art. 21 - Widerspruch


class DSRStatus(str, Enum):
    """Status einer Betroffenenrechte-Anfrage."""
    PENDING = "pending"          # Eingegangen, noch nicht bearbeitet
    VERIFICATION = "verification"  # Identitaetspruefung laeuft
    IN_PROGRESS = "in_progress"  # In Bearbeitung
    COMPLETED = "completed"      # Abgeschlossen
    REJECTED = "rejected"        # Abgelehnt (mit Begruendung)
    CANCELLED = "cancelled"      # Vom Antragsteller zurueckgezogen


class DataCategory(str, Enum):
    """Kategorien personenbezogener Daten."""
    PERSONAL = "personal"          # Name, Email, Adresse
    FINANCIAL = "financial"        # Rechnungen, Zahlungen
    DOCUMENTS = "documents"        # Hochgeladene Dokumente
    ACTIVITY = "activity"          # Aktivitaets-Logs
    PREFERENCES = "preferences"    # Einstellungen
    COMMUNICATIONS = "communications"  # Kommentare, Nachrichten
    AUTHENTICATION = "authentication"  # Login-Daten, Sessions


# DSGVO Frist: 30 Tage (erweiterbar auf 60 bei Komplexitaet)
DEFAULT_RESPONSE_DAYS = 30
EXTENDED_RESPONSE_DAYS = 60

# Export-Einstellungen
EXPORT_EXPIRY_DAYS = 7
MAX_EXPORT_SIZE_MB = 500


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class DSRRequest:
    """Repraesentation einer Betroffenenrechte-Anfrage."""
    id: uuid.UUID
    request_type: DSRType
    status: DSRStatus
    requester_email: str
    requester_name: Optional[str]
    user_id: Optional[uuid.UUID]
    company_id: Optional[uuid.UUID]
    description: Optional[str]
    affected_data_categories: List[DataCategory]
    requested_at: datetime
    due_date: datetime
    verified_at: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    assigned_to_id: Optional[uuid.UUID]
    days_remaining: int

    @property
    def is_overdue(self) -> bool:
        """Prueft ob die Frist ueberschritten ist."""
        if self.status in [DSRStatus.COMPLETED, DSRStatus.REJECTED, DSRStatus.CANCELLED]:
            return False
        return datetime.now(timezone.utc) > self.due_date

    @property
    def urgency_level(self) -> str:
        """Bestimmt Dringlichkeitsstufe."""
        if self.is_overdue:
            return "critical"
        elif self.days_remaining <= 5:
            return "high"
        elif self.days_remaining <= 14:
            return "medium"
        return "low"


@dataclass
class DSRCreateResult:
    """Ergebnis der Erstellung einer DSR-Anfrage."""
    success: bool
    request_id: uuid.UUID
    verification_token: str
    due_date: datetime
    message: str
    status: DSRStatus = DSRStatus.PENDING
    verification_required: bool = True


@dataclass
class DSRVerificationResult:
    """Ergebnis der Identitaetsverifizierung."""
    success: bool
    request_id: uuid.UUID
    verified: bool
    message: str
    verified_at: Optional[datetime] = None
    error_message: Optional[str] = None


@dataclass
class PersonalDataExport:
    """Exportierte personenbezogene Daten."""
    user_id: uuid.UUID
    export_id: uuid.UUID
    categories_included: List[DataCategory]
    file_path: str
    file_size_bytes: int
    file_hash: str
    format: str
    expires_at: datetime
    download_url: Optional[str] = None


@dataclass
class PersonalDataSummary:
    """Zusammenfassung personenbezogener Daten fuer Art. 15 Auskunft."""
    user_id: uuid.UUID
    export_date: datetime
    data_categories: List[DataCategory]
    personal_data: Dict[str, Any]
    total_records: int


@dataclass
class DataCategory_Info:
    """Information ueber eine Datenkategorie."""
    category: DataCategory
    record_count: int
    sample_fields: List[str]
    retention_period: Optional[str]
    legal_basis: str


@dataclass
class ErasureResult:
    """Ergebnis einer Loeschanfrage."""
    success: bool
    request_id: uuid.UUID
    records_deleted: Dict[str, int]
    records_anonymized: Dict[str, int]
    retained_categories: List[str]
    retention_reasons: Dict[str, str]
    completed_at: datetime
    message: str


@dataclass
class RectificationResult:
    """Ergebnis einer Berichtigungsanfrage."""
    success: bool
    corrected_fields: List[str]
    skipped_fields: List[str]
    protected_fields: List[str]
    message: str
    request_id: Optional[uuid.UUID] = None
    completed_at: Optional[datetime] = None


# =============================================================================
# Service Implementation
# =============================================================================

class DataSubjectRightsService:
    """Service fuer DSGVO Betroffenenrechte (Art. 15-21).

    Implementiert:
    - Anfrage-Management mit 30-Tage-Frist-Tracking
    - Identitaetsverifizierung
    - Datenexport (Portabilitaet)
    - Datenloeschung mit Aufbewahrungspflichten
    - Datenberichtigung
    - Audit-Trail fuer alle Aktionen
    """

    _instance: Optional["DataSubjectRightsService"] = None

    def __new__(cls) -> "DataSubjectRightsService":
        """Singleton Pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialisiert den Service."""
        if self._initialized:
            return
        self._initialized = True
        self._export_base_path = Path(tempfile.gettempdir()) / "gdpr_exports"
        self._export_base_path.mkdir(exist_ok=True)
        logger.info("data_subject_rights_service_initialized")

    # =========================================================================
    # Request Management
    # =========================================================================

    async def create_request(
        self,
        db: AsyncSession,
        request_type: DSRType,
        requester_email: str,
        requester_name: Optional[str] = None,
        user_id: Optional[uuid.UUID] = None,
        company_id: Optional[uuid.UUID] = None,
        description: Optional[str] = None,
        affected_data_categories: Optional[List[DataCategory]] = None,
        rectification_details: Optional[Dict[str, Any]] = None,
    ) -> DSRCreateResult:
        """Erstellt eine neue Betroffenenrechte-Anfrage.

        Args:
            db: Datenbank-Session
            request_type: Art der Anfrage (Art. 15-21)
            requester_email: Email des Antragstellers
            requester_name: Optional - Name des Antragstellers
            user_id: Optional - User-ID wenn bekannt
            company_id: Optional - Company-ID
            description: Optional - Beschreibung der Anfrage
            affected_data_categories: Optional - Betroffene Datenkategorien
            rectification_details: Optional - Details fuer Berichtigungsanfragen

        Returns:
            DSRCreateResultExtended
        """
        from app.db.models import GDPRDataSubjectRequest

        now = datetime.now(timezone.utc)
        due_date = now + timedelta(days=DEFAULT_RESPONSE_DAYS)
        verification_token = self._generate_verification_token()

        # Standard-Kategorien wenn nicht angegeben
        affected_categories = affected_data_categories
        if affected_categories is None:
            affected_categories = list(DataCategory)

        request = GDPRDataSubjectRequest(
            id=uuid.uuid4(),
            user_id=user_id,
            company_id=company_id,
            request_type=request_type.value,
            status=DSRStatus.PENDING.value,
            requester_email=requester_email,
            requester_name=requester_name,
            verification_token=verification_token,
            description=description,
            affected_data_categories=[c.value for c in affected_categories],
            rectification_details=rectification_details,
            due_date=due_date,
        )

        db.add(request)
        await db.flush()

        # Wenn User bereits eingeloggt ist, braucht er keine Email-Verifikation
        verification_required = user_id is None

        logger.info(
            "dsr_request_created",
            request_id=str(request.id),
            request_type=request_type.value,
            requester_email=requester_email[:3] + "***",  # PII-Schutz
        )

        return DSRCreateResult(
            success=True,
            request_id=request.id,
            verification_token=verification_token,
            due_date=due_date,
            message=f"Anfrage erfolgreich erstellt. Bitte verifizieren Sie Ihre Identitaet. "
                    f"Bearbeitungsfrist: {due_date.strftime('%d.%m.%Y')}",
            status=DSRStatus.PENDING,
            verification_required=verification_required,
        )

    async def verify_identity(
        self,
        db: AsyncSession,
        request_id: uuid.UUID,
        verification_token: str,
    ) -> DSRVerificationResult:
        """Verifiziert die Identitaet des Antragstellers.

        Args:
            db: Datenbank-Session
            request_id: Anfrage-ID
            verification_token: Verifizierungstoken

        Returns:
            DSRVerificationResult
        """
        from app.db.models import GDPRDataSubjectRequest

        result = await db.execute(
            select(GDPRDataSubjectRequest)
            .where(GDPRDataSubjectRequest.id == request_id)
        )
        request = result.scalar_one_or_none()

        if not request:
            return DSRVerificationResult(
                success=False,
                request_id=request_id,
                verified=False,
                message="Anfrage nicht gefunden",
                error_message="Anfrage nicht gefunden",
            )

        if request.verification_token != verification_token:
            return DSRVerificationResult(
                success=False,
                request_id=request_id,
                verified=False,
                message="Ungueltiger Verifizierungstoken",
                error_message="Ungueltiger Verifizierungstoken",
            )

        if request.verified_at:
            return DSRVerificationResult(
                success=True,
                request_id=request_id,
                verified=True,
                message="Identitaet bereits verifiziert",
                verified_at=request.verified_at,
            )

        # Verifizierung erfolgreich
        now = datetime.now(timezone.utc)
        request.verified_at = now
        request.status = DSRStatus.IN_PROGRESS.value
        request.started_at = now
        await db.flush()

        logger.info(
            "dsr_identity_verified",
            request_id=str(request_id),
        )

        return DSRVerificationResult(
            success=True,
            request_id=request_id,
            verified=True,
            message="Identitaet erfolgreich verifiziert. Ihre Anfrage wird bearbeitet.",
            verified_at=now,
        )

    async def get_request(
        self,
        db: AsyncSession,
        request_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
    ) -> Optional[DSRRequest]:
        """Holt eine Betroffenenrechte-Anfrage.

        Args:
            db: Datenbank-Session
            request_id: Anfrage-ID
            user_id: Optional - User-ID fuer Berechtigungspruefung

        Returns:
            DSRRequest oder None
        """
        from app.db.models import GDPRDataSubjectRequest

        query = select(GDPRDataSubjectRequest).where(
            GDPRDataSubjectRequest.id == request_id
        )

        # Filter nach User wenn angegeben (fuer Berechtigungspruefung)
        if user_id:
            query = query.where(GDPRDataSubjectRequest.user_id == user_id)

        result = await db.execute(query)
        request = result.scalar_one_or_none()

        if not request:
            return None

        now = datetime.now(timezone.utc)
        days_remaining = (request.due_date - now).days

        return DSRRequest(
            id=request.id,
            request_type=DSRType(request.request_type),
            status=DSRStatus(request.status),
            requester_email=request.requester_email,
            requester_name=request.requester_name,
            user_id=request.user_id,
            company_id=request.company_id,
            description=request.description,
            affected_data_categories=[DataCategory(c) for c in (request.affected_data_categories or [])],
            requested_at=request.requested_at or request.created_at,
            due_date=request.due_date,
            verified_at=request.verified_at,
            started_at=request.started_at,
            completed_at=request.completed_at,
            assigned_to_id=request.assigned_to_id,
            days_remaining=max(0, days_remaining),
        )

    async def list_requests(
        self,
        db: AsyncSession,
        user_id: Optional[uuid.UUID] = None,
        company_id: Optional[uuid.UUID] = None,
        status: Optional[DSRStatus] = None,
        request_type: Optional[DSRType] = None,
        overdue_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> List[DSRRequest]:
        """Listet Betroffenenrechte-Anfragen.

        Args:
            db: Datenbank-Session
            user_id: Optional - Filter nach User (fuer Benutzer-Sicht)
            company_id: Optional - Filter nach Company
            status: Optional - Filter nach Status
            request_type: Optional - Filter nach Typ
            overdue_only: Nur ueberfaellige Anfragen
            limit: Maximale Anzahl
            offset: Offset fuer Pagination

        Returns:
            Liste von DSRRequest
        """
        from app.db.models import GDPRDataSubjectRequest

        now = datetime.now(timezone.utc)

        # Basis-Query
        query = select(GDPRDataSubjectRequest)

        conditions = []

        if user_id:
            conditions.append(GDPRDataSubjectRequest.user_id == user_id)
        if company_id:
            conditions.append(GDPRDataSubjectRequest.company_id == company_id)
        if status:
            conditions.append(GDPRDataSubjectRequest.status == status.value)
        if request_type:
            conditions.append(GDPRDataSubjectRequest.request_type == request_type.value)
        if overdue_only:
            conditions.append(GDPRDataSubjectRequest.due_date < now)
            conditions.append(
                GDPRDataSubjectRequest.status.in_([
                    DSRStatus.PENDING.value,
                    DSRStatus.VERIFICATION.value,
                    DSRStatus.IN_PROGRESS.value,
                ])
            )

        if conditions:
            query = query.where(and_(*conditions))

        # Sortierung: Ueberfaellige zuerst, dann nach due_date
        query = query.order_by(
            GDPRDataSubjectRequest.due_date.asc()
        ).offset(offset).limit(limit)

        result = await db.execute(query)
        requests_db = result.scalars().all()

        requests = []
        for r in requests_db:
            days_remaining = (r.due_date - now).days
            requests.append(DSRRequest(
                id=r.id,
                request_type=DSRType(r.request_type),
                status=DSRStatus(r.status),
                requester_email=r.requester_email,
                requester_name=r.requester_name,
                user_id=r.user_id,
                company_id=r.company_id,
                description=r.description,
                affected_data_categories=[DataCategory(c) for c in (r.affected_data_categories or [])],
                requested_at=r.requested_at or r.created_at,
                due_date=r.due_date,
                verified_at=r.verified_at,
                started_at=r.started_at,
                completed_at=r.completed_at,
                assigned_to_id=r.assigned_to_id,
                days_remaining=max(0, days_remaining),
            ))

        return requests

    async def assign_request(
        self,
        db: AsyncSession,
        request_id: uuid.UUID,
        assigned_to_id: uuid.UUID,
    ) -> bool:
        """Weist eine Anfrage einem Bearbeiter zu.

        Args:
            db: Datenbank-Session
            request_id: Anfrage-ID
            assigned_to_id: User-ID des Bearbeiters

        Returns:
            True bei Erfolg
        """
        from app.db.models import GDPRDataSubjectRequest

        result = await db.execute(
            update(GDPRDataSubjectRequest)
            .where(GDPRDataSubjectRequest.id == request_id)
            .values(assigned_to_id=assigned_to_id)
        )

        if result.rowcount > 0:
            logger.info(
                "dsr_request_assigned",
                request_id=str(request_id),
                assigned_to=str(assigned_to_id),
            )
            return True
        return False

    # =========================================================================
    # Art. 15 - Auskunftsrecht (Right of Access)
    # =========================================================================

    async def export_personal_data_summary(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        company_id: Optional[uuid.UUID] = None,
        include_documents: bool = True,
        include_activity: bool = True,
    ) -> PersonalDataSummary:
        """Erstellt eine Zusammenfassung aller personenbezogenen Daten.

        Art. 15 DSGVO: Recht auf Auskunft - leichtgewichtige Version
        fuer direkte API-Antwort ohne Datei-Export.

        Args:
            db: Datenbank-Session
            user_id: User-ID
            company_id: Optional - Company-ID fuer zusaetzlichen Filter
            include_documents: Dokumente einschliessen
            include_activity: Aktivitaeten einschliessen

        Returns:
            PersonalDataSummary
        """
        from app.db.models import User, Document, DocumentComment, AuditLog

        now = datetime.now(timezone.utc)
        personal_data: Dict[str, Any] = {}
        total_records = 0
        included_categories: List[DataCategory] = [DataCategory.PERSONAL]

        # Personal Data (immer)
        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if user:
            personal_data["benutzer"] = {
                "email": user.email,
                "name": user.name,
                "erstellt_am": user.created_at.isoformat() if user.created_at else None,
                "letzte_anmeldung": user.last_login.isoformat() if hasattr(user, 'last_login') and user.last_login else None,
            }
            total_records += 1

        # Documents
        if include_documents:
            included_categories.append(DataCategory.DOCUMENTS)
            doc_query = select(Document).where(Document.user_id == user_id)
            if company_id:
                doc_query = doc_query.where(Document.company_id == company_id)
            doc_result = await db.execute(doc_query.limit(100))
            documents = doc_result.scalars().all()

            personal_data["dokumente"] = {
                "anzahl": len(documents),
                "liste": [
                    {
                        "id": str(d.id),
                        "dateiname": d.filename,
                        "typ": d.document_type,
                        "erstellt_am": d.created_at.isoformat() if d.created_at else None,
                    }
                    for d in documents[:50]  # Max 50 in Zusammenfassung
                ],
                "hinweis": "Vollstaendige Liste ueber Datenexport (Art. 20) verfuegbar" if len(documents) > 50 else None,
            }
            total_records += len(documents)

            # Comments
            included_categories.append(DataCategory.COMMUNICATIONS)
            comment_result = await db.execute(
                select(DocumentComment)
                .where(DocumentComment.user_id == user_id)
                .limit(100)
            )
            comments = comment_result.scalars().all()
            personal_data["kommentare"] = {
                "anzahl": len(comments),
                "liste": [
                    {
                        "id": str(c.id),
                        "dokument_id": str(c.document_id),
                        "erstellt_am": c.created_at.isoformat() if c.created_at else None,
                    }
                    for c in comments[:20]
                ],
            }
            total_records += len(comments)

        # Activity Logs
        if include_activity:
            included_categories.append(DataCategory.ACTIVITY)
            activity_result = await db.execute(
                select(AuditLog)
                .where(AuditLog.user_id == user_id)
                .order_by(AuditLog.created_at.desc())
                .limit(50)
            )
            activities = activity_result.scalars().all()
            personal_data["aktivitaeten"] = {
                "anzahl": len(activities),
                "letzte_aktivitaeten": [
                    {
                        "aktion": a.action,
                        "ressource": a.resource_type,
                        "zeitpunkt": a.created_at.isoformat() if a.created_at else None,
                    }
                    for a in activities[:20]
                ],
            }
            total_records += len(activities)

        # Verarbeitungszwecke und Rechtsgrundlagen (Art. 15 Abs. 1)
        personal_data["verarbeitung"] = {
            "zwecke": [
                "Dokumentenverarbeitung und -verwaltung",
                "OCR-basierte Texterkennung",
                "Rechnungsverarbeitung",
                "Compliance und Audit",
            ],
            "rechtsgrundlagen": {
                "personal_data": "Art. 6 Abs. 1 lit. b DSGVO (Vertragserfuellung)",
                "documents": "Art. 6 Abs. 1 lit. c DSGVO (Rechtliche Verpflichtung)",
                "activity_logs": "Art. 6 Abs. 1 lit. f DSGVO (Berechtigtes Interesse)",
            },
            "aufbewahrungsfristen": {
                "dokumente": "10 Jahre (GoBD, §147 AO, §257 HGB)",
                "aktivitaetsprotokolle": "90 Tage",
                "kontodaten": "Bis zur Kontoloeschung",
            },
            "empfaenger": "Keine Weitergabe an Dritte ohne Einwilligung",
        }

        logger.info(
            "personal_data_summary_generated",
            user_id=str(user_id)[:8] + "...",
            total_records=total_records,
        )

        return PersonalDataSummary(
            user_id=user_id,
            export_date=now,
            data_categories=included_categories,
            personal_data=personal_data,
            total_records=total_records,
        )

    async def get_data_inventory(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> List[DataCategory_Info]:
        """Erstellt ein Inventar der gespeicherten Daten eines Users.

        Art. 15 DSGVO: Der Betroffene hat das Recht zu erfahren,
        welche Daten ueber ihn verarbeitet werden.

        Args:
            db: Datenbank-Session
            user_id: User-ID

        Returns:
            Liste von DataCategory_Info
        """
        from app.db.models import User, Document, DocumentComment, AuditLog

        inventory = []

        # Personal Data
        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if user:
            inventory.append(DataCategory_Info(
                category=DataCategory.PERSONAL,
                record_count=1,
                sample_fields=["email", "name", "phone", "address"],
                retention_period="Bis zur Kontoloeschung",
                legal_basis="Art. 6 Abs. 1 lit. b DSGVO (Vertragserfuellung)",
            ))

        # Documents
        doc_count_result = await db.execute(
            select(func.count()).select_from(Document)
            .where(Document.user_id == user_id)
        )
        doc_count = doc_count_result.scalar() or 0
        if doc_count > 0:
            inventory.append(DataCategory_Info(
                category=DataCategory.DOCUMENTS,
                record_count=doc_count,
                sample_fields=["filename", "ocr_text", "extracted_data", "upload_date"],
                retention_period="10 Jahre (GoBD)",
                legal_basis="Art. 6 Abs. 1 lit. c DSGVO (Rechtliche Verpflichtung)",
            ))

        # Activity Logs
        activity_count_result = await db.execute(
            select(func.count()).select_from(AuditLog)
            .where(AuditLog.user_id == user_id)
        )
        activity_count = activity_count_result.scalar() or 0
        if activity_count > 0:
            inventory.append(DataCategory_Info(
                category=DataCategory.ACTIVITY,
                record_count=activity_count,
                sample_fields=["action", "resource", "timestamp", "ip_address"],
                retention_period="90 Tage",
                legal_basis="Art. 6 Abs. 1 lit. f DSGVO (Berechtigtes Interesse)",
            ))

        # Comments
        comment_count_result = await db.execute(
            select(func.count()).select_from(DocumentComment)
            .where(DocumentComment.user_id == user_id)
        )
        comment_count = comment_count_result.scalar() or 0
        if comment_count > 0:
            inventory.append(DataCategory_Info(
                category=DataCategory.COMMUNICATIONS,
                record_count=comment_count,
                sample_fields=["content", "document_id", "created_at"],
                retention_period="Mit zugehoerigem Dokument",
                legal_basis="Art. 6 Abs. 1 lit. b DSGVO (Vertragserfuellung)",
            ))

        return inventory

    # =========================================================================
    # Art. 20 - Datenuebertragbarkeit (Right to Data Portability)
    # =========================================================================

    async def export_personal_data(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        request_id: Optional[uuid.UUID] = None,
        categories: Optional[List[DataCategory]] = None,
        format: str = "json",
    ) -> PersonalDataExport:
        """Exportiert personenbezogene Daten im maschinenlesbaren Format.

        Art. 20 DSGVO: Recht auf Datenuebertragbarkeit.

        Args:
            db: Datenbank-Session
            user_id: User-ID
            request_id: Optional - Zugehoerige DSR-Anfrage
            categories: Optional - Zu exportierende Kategorien
            format: Export-Format (json, csv)

        Returns:
            PersonalDataExport
        """
        from app.db.models import (
            User, Document, DocumentComment, GDPRDataExport,
            GDPRDataSubjectRequest
        )

        now = datetime.now(timezone.utc)
        export_id = uuid.uuid4()
        categories = categories or list(DataCategory)

        # Sammle Daten
        export_data: Dict[str, Any] = {
            "export_metadata": {
                "user_id": str(user_id),
                "export_id": str(export_id),
                "export_date": now.isoformat(),
                "format_version": "1.0",
                "categories_included": [c.value for c in categories],
            }
        }

        # Personal Data
        if DataCategory.PERSONAL in categories:
            user_result = await db.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one_or_none()
            if user:
                export_data["personal_data"] = {
                    "email": user.email,
                    "name": user.name,
                    "created_at": user.created_at.isoformat() if user.created_at else None,
                }

        # Documents (metadata only, not files)
        if DataCategory.DOCUMENTS in categories:
            doc_result = await db.execute(
                select(Document)
                .where(Document.user_id == user_id)
                .limit(1000)  # Sicherheitslimit
            )
            documents = doc_result.scalars().all()
            export_data["documents"] = [
                {
                    "id": str(d.id),
                    "filename": d.filename,
                    "document_type": d.document_type,
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                    "extracted_data": d.extracted_data,
                }
                for d in documents
            ]

        # Comments
        if DataCategory.COMMUNICATIONS in categories:
            comment_result = await db.execute(
                select(DocumentComment)
                .where(DocumentComment.user_id == user_id)
                .limit(1000)
            )
            comments = comment_result.scalars().all()
            export_data["comments"] = [
                {
                    "id": str(c.id),
                    "content": c.content,
                    "document_id": str(c.document_id),
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                }
                for c in comments
            ]

        # Erstelle Export-Datei
        export_path = self._export_base_path / f"export_{export_id}.json"

        if format == "json":
            with open(export_path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
        else:
            # CSV-Export (vereinfacht)
            with open(export_path, "w", encoding="utf-8") as f:
                f.write(json.dumps(export_data, ensure_ascii=False))

        # Berechne Hash und Groesse
        file_size = export_path.stat().st_size
        file_hash = self._calculate_file_hash(export_path)
        expires_at = now + timedelta(days=EXPORT_EXPIRY_DAYS)

        # Speichere Export-Record
        export_record = GDPRDataExport(
            id=export_id,
            user_id=user_id,
            request_id=request_id,
            export_type="full" if len(categories) == len(DataCategory) else "partial",
            data_categories=[c.value for c in categories],
            format=format,
            file_path=str(export_path),
            file_size_bytes=file_size,
            file_hash=file_hash,
            status="completed",
            started_at=now,
            completed_at=now,
            expires_at=expires_at,
        )
        db.add(export_record)

        # Update DSR-Request falls vorhanden
        if request_id:
            await db.execute(
                update(GDPRDataSubjectRequest)
                .where(GDPRDataSubjectRequest.id == request_id)
                .values(
                    export_file_path=str(export_path),
                    export_format=format,
                    status=DSRStatus.COMPLETED.value,
                    completed_at=now,
                )
            )

        await db.flush()

        logger.info(
            "personal_data_exported",
            user_id=str(user_id),
            export_id=str(export_id),
            file_size=file_size,
            categories=len(categories),
        )

        return PersonalDataExport(
            user_id=user_id,
            export_id=export_id,
            categories_included=categories,
            file_path=str(export_path),
            file_size_bytes=file_size,
            file_hash=file_hash,
            format=format,
            expires_at=expires_at,
        )

    # =========================================================================
    # Art. 17 - Recht auf Loeschung (Right to Erasure)
    # =========================================================================

    async def request_erasure(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        request_id: uuid.UUID,
        categories: Optional[List[DataCategory]] = None,
    ) -> ErasureResult:
        """Fuehrt eine Loeschanfrage durch.

        Art. 17 DSGVO: Recht auf Loeschung ("Recht auf Vergessenwerden").

        WICHTIG: Einige Daten muessen aufgrund gesetzlicher Aufbewahrungspflichten
        behalten werden (z.B. Rechnungen fuer 10 Jahre nach GoBD).

        Args:
            db: Datenbank-Session
            user_id: User-ID
            request_id: DSR-Anfrage-ID
            categories: Optional - Zu loeschende Kategorien

        Returns:
            ErasureResult
        """
        from app.db.models import (
            User, Document, DocumentComment, AuditLog,
            GDPRDataSubjectRequest, Notification
        )

        now = datetime.now(timezone.utc)
        categories = categories or list(DataCategory)

        records_deleted: Dict[str, int] = {}
        records_anonymized: Dict[str, int] = {}
        retained_categories: List[str] = []
        retention_reasons: Dict[str, str] = {}

        # Activity Logs - Anonymisieren statt Loeschen (fuer Audit-Trail)
        if DataCategory.ACTIVITY in categories:
            result = await db.execute(
                update(AuditLog)
                .where(AuditLog.user_id == user_id)
                .values(
                    user_id=None,
                    details={"anonymized": True, "anonymized_at": now.isoformat()},
                )
            )
            records_anonymized["activity_logs"] = result.rowcount

        # Comments - Anonymisieren
        if DataCategory.COMMUNICATIONS in categories:
            result = await db.execute(
                update(DocumentComment)
                .where(DocumentComment.user_id == user_id)
                .values(
                    content="[Inhalt geloescht auf Anfrage des Nutzers]",
                    user_id=None,
                )
            )
            records_anonymized["comments"] = result.rowcount

        # Documents - NICHT loeschen wegen GoBD (10 Jahre Aufbewahrungspflicht)
        if DataCategory.DOCUMENTS in categories:
            doc_count_result = await db.execute(
                select(func.count()).select_from(Document)
                .where(Document.user_id == user_id)
            )
            doc_count = doc_count_result.scalar() or 0
            if doc_count > 0:
                retained_categories.append("documents")
                retention_reasons["documents"] = (
                    "Gesetzliche Aufbewahrungspflicht nach §147 AO, §257 HGB (10 Jahre)"
                )
                # Anonymisiere nur personenbezogene Metadaten
                await db.execute(
                    update(Document)
                    .where(Document.user_id == user_id)
                    .values(user_id=None)  # Entferne User-Referenz
                )
                records_anonymized["documents"] = doc_count

        # Notifications - Loeschen
        result = await db.execute(
            delete(Notification)
            .where(Notification.user_id == user_id)
        )
        records_deleted["notifications"] = result.rowcount

        # Personal Data - Anonymisieren (Account behalten fuer Audit)
        if DataCategory.PERSONAL in categories:
            user_result = await db.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one_or_none()
            if user:
                # Anonymisiere User-Daten
                anonymized_email = f"deleted_{uuid.uuid4().hex[:8]}@anonymized.local"
                user.email = anonymized_email
                user.name = "Geloeschter Benutzer"
                user.password_hash = None
                user.is_active = False
                records_anonymized["user_account"] = 1

        # Update DSR-Request
        await db.execute(
            update(GDPRDataSubjectRequest)
            .where(GDPRDataSubjectRequest.id == request_id)
            .values(
                status=DSRStatus.COMPLETED.value,
                completed_at=now,
                response_notes=json.dumps({
                    "deleted": records_deleted,
                    "anonymized": records_anonymized,
                    "retained": retained_categories,
                }, ensure_ascii=False),
            )
        )

        await db.flush()

        logger.info(
            "erasure_completed",
            user_id=str(user_id),
            request_id=str(request_id),
            deleted=sum(records_deleted.values()),
            anonymized=sum(records_anonymized.values()),
            retained=len(retained_categories),
        )

        return ErasureResult(
            success=True,
            request_id=request_id,
            records_deleted=records_deleted,
            records_anonymized=records_anonymized,
            retained_categories=retained_categories,
            retention_reasons=retention_reasons,
            completed_at=now,
            message="Loeschanfrage bearbeitet. Einige Daten wurden aufgrund "
                    "gesetzlicher Aufbewahrungspflichten anonymisiert statt geloescht.",
        )

    # =========================================================================
    # Art. 16 - Recht auf Berichtigung (Right to Rectification)
    # =========================================================================

    async def rectify_data(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        corrections: Dict[str, Any],
        reason: Optional[str] = None,
        request_id: Optional[uuid.UUID] = None,
    ) -> RectificationResult:
        """Fuehrt eine Berichtigungsanfrage durch.

        Art. 16 DSGVO: Recht auf Berichtigung unrichtiger Daten.

        Args:
            db: Datenbank-Session
            user_id: User-ID
            corrections: Dict mit Feldname -> neuer Wert
            reason: Optional - Begruendung fuer Berichtigung
            request_id: Optional - DSR-Anfrage-ID wenn ueber DSR-Prozess

        Returns:
            RectificationResult
        """
        from app.db.models import User, GDPRDataSubjectRequest

        now = datetime.now(timezone.utc)
        corrected_fields: List[str] = []
        skipped_fields: List[str] = []
        protected_fields: List[str] = []

        # Erlaubte Felder fuer Berichtigung
        allowed_fields = {"name", "phone", "address", "display_name"}
        # Geschuetzte Felder die nicht geaendert werden duerfen
        protected_field_names = {"id", "email", "password_hash", "is_superuser", "created_at", "company_id"}

        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        if not user:
            return RectificationResult(
                success=False,
                corrected_fields=[],
                skipped_fields=[],
                protected_fields=[],
                message="Benutzer nicht gefunden",
            )

        for field_name, new_value in corrections.items():
            # Geschuetzte Felder
            if field_name in protected_field_names:
                protected_fields.append(field_name)
                continue

            # Nicht erlaubte Felder
            if field_name not in allowed_fields:
                skipped_fields.append(field_name)
                continue

            # Pruefe ob Feld existiert
            if not hasattr(user, field_name):
                skipped_fields.append(field_name)
                continue

            # Berichtige Feld
            old_value = getattr(user, field_name, None)
            if old_value != new_value:
                setattr(user, field_name, new_value)
                corrected_fields.append(field_name)
            else:
                skipped_fields.append(field_name)  # Wert unveraendert

        # Update DSR-Request falls vorhanden
        if request_id:
            await db.execute(
                update(GDPRDataSubjectRequest)
                .where(GDPRDataSubjectRequest.id == request_id)
                .values(
                    status=DSRStatus.COMPLETED.value,
                    completed_at=now,
                    response_notes=json.dumps({
                        "corrected": corrected_fields,
                        "skipped": skipped_fields,
                        "protected": protected_fields,
                        "reason": reason,
                    }, ensure_ascii=False),
                )
            )

        await db.flush()

        logger.info(
            "rectification_completed",
            user_id=str(user_id)[:8] + "...",
            corrected=len(corrected_fields),
            skipped=len(skipped_fields),
            protected=len(protected_fields),
        )

        return RectificationResult(
            success=len(corrected_fields) > 0,
            corrected_fields=corrected_fields,
            skipped_fields=skipped_fields,
            protected_fields=protected_fields,
            request_id=request_id,
            completed_at=now,
            message=f"{len(corrected_fields)} Feld(er) berichtigt",
        )

    # =========================================================================
    # Request Management
    # =========================================================================

    async def cancel_request(
        self,
        db: AsyncSession,
        request_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Storniert eine DSR-Anfrage.

        Nur moeglich wenn die Anfrage noch nicht abgeschlossen ist.

        Args:
            db: Datenbank-Session
            request_id: Anfrage-ID
            user_id: User-ID (fuer Berechtigungspruefung)

        Raises:
            ValueError: Wenn Anfrage nicht storniert werden kann
        """
        from app.db.models import GDPRDataSubjectRequest

        result = await db.execute(
            select(GDPRDataSubjectRequest)
            .where(
                and_(
                    GDPRDataSubjectRequest.id == request_id,
                    GDPRDataSubjectRequest.user_id == user_id,
                )
            )
        )
        request = result.scalar_one_or_none()

        if not request:
            raise ValueError("Anfrage nicht gefunden oder keine Berechtigung")

        # Prüfe ob Stornierung möglich
        non_cancellable = [DSRStatus.COMPLETED.value, DSRStatus.REJECTED.value, DSRStatus.CANCELLED.value]
        if request.status in non_cancellable:
            raise ValueError(
                f"Anfrage kann nicht storniert werden (Status: {request.status})"
            )

        # Storniere
        now = datetime.now(timezone.utc)
        request.status = DSRStatus.CANCELLED.value
        request.completed_at = now
        request.response_notes = "Vom Benutzer storniert"

        await db.flush()

        logger.info(
            "dsr_request_cancelled",
            request_id=str(request_id),
            user_id=str(user_id),
        )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    @staticmethod
    def _generate_verification_token() -> str:
        """Generiert einen sicheren Verifizierungstoken."""
        return hashlib.sha256(
            f"{uuid.uuid4()}{datetime.now().isoformat()}".encode()
        ).hexdigest()[:64]

    @staticmethod
    def _calculate_file_hash(file_path: Path) -> str:
        """Berechnet SHA-256 Hash einer Datei."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    async def get_overdue_requests_count(
        self,
        db: AsyncSession,
        company_id: Optional[uuid.UUID] = None,
    ) -> int:
        """Zaehlt ueberfaellige DSR-Anfragen.

        Args:
            db: Datenbank-Session
            company_id: Optional - Company-ID

        Returns:
            Anzahl ueberfaelliger Anfragen
        """
        from app.db.models import GDPRDataSubjectRequest

        now = datetime.now(timezone.utc)

        query = select(func.count()).select_from(GDPRDataSubjectRequest).where(
            and_(
                GDPRDataSubjectRequest.due_date < now,
                GDPRDataSubjectRequest.status.in_([
                    DSRStatus.PENDING.value,
                    DSRStatus.VERIFICATION.value,
                    DSRStatus.IN_PROGRESS.value,
                ]),
            )
        )

        if company_id:
            query = query.where(GDPRDataSubjectRequest.company_id == company_id)

        result = await db.execute(query)
        return result.scalar() or 0

    async def get_statistics(
        self,
        db: AsyncSession,
        company_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """Holt Statistiken zu DSR-Anfragen.

        Args:
            db: Datenbank-Session
            company_id: Optional - Company-ID

        Returns:
            Dict mit Statistiken
        """
        from app.db.models import GDPRDataSubjectRequest

        now = datetime.now(timezone.utc)
        thirty_days_ago = now - timedelta(days=30)

        base_condition = []
        if company_id:
            base_condition.append(GDPRDataSubjectRequest.company_id == company_id)

        # Total
        total_result = await db.execute(
            select(func.count()).select_from(GDPRDataSubjectRequest)
            .where(and_(*base_condition) if base_condition else True)
        )
        total = total_result.scalar() or 0

        # By Status
        status_result = await db.execute(
            select(
                GDPRDataSubjectRequest.status,
                func.count().label("count"),
            )
            .where(and_(*base_condition) if base_condition else True)
            .group_by(GDPRDataSubjectRequest.status)
        )
        by_status = {row.status: row.count for row in status_result.all()}

        # By Type
        type_result = await db.execute(
            select(
                GDPRDataSubjectRequest.request_type,
                func.count().label("count"),
            )
            .where(and_(*base_condition) if base_condition else True)
            .group_by(GDPRDataSubjectRequest.request_type)
        )
        by_type = {row.request_type: row.count for row in type_result.all()}

        # Overdue
        overdue = await self.get_overdue_requests_count(db, company_id)

        # Last 30 days
        recent_result = await db.execute(
            select(func.count()).select_from(GDPRDataSubjectRequest)
            .where(
                and_(
                    GDPRDataSubjectRequest.created_at >= thirty_days_ago,
                    *base_condition,
                )
            )
        )
        recent = recent_result.scalar() or 0

        return {
            "total_requests": total,
            "by_status": by_status,
            "by_type": by_type,
            "overdue_count": overdue,
            "last_30_days": recent,
            "compliance_rate": round(
                (1 - (overdue / max(total, 1))) * 100, 1
            ),
        }


# =============================================================================
# Singleton & Factory
# =============================================================================

def get_data_subject_rights_service() -> DataSubjectRightsService:
    """Factory-Funktion fuer DataSubjectRightsService."""
    return DataSubjectRightsService()


# Singleton-Instanz
data_subject_rights_service = DataSubjectRightsService()
