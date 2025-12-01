"""
GDPR Compliance Framework for Ablage-System OCR
Data Privacy and Protection for German Document Processing
Created: 2024-11-22
Updated: 2024-12-01 - Processing Activities now persisted to PostgreSQL

SECURITY FIX: In-Memory-Speicherung wurde durch PostgreSQL ersetzt,
damit Verarbeitungsaktivitäten nicht bei Restart verloren gehen.
"""

from typing import Dict, List, Optional, Any, TYPE_CHECKING
from datetime import datetime, timedelta, timezone
from enum import Enum
from uuid import UUID
import hashlib
import structlog
import json

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


class DataCategory(Enum):
    """GDPR Data Categories"""
    PERSONAL_IDENTIFIABLE = "personal_identifiable"  # Name, Adresse, etc.
    SPECIAL_CATEGORY = "special_category"  # Gesundheit, Religion, etc.
    FINANCIAL = "financial"  # Bankdaten, Rechnungen
    CONTACT = "contact"  # Email, Telefon
    DOCUMENT_CONTENT = "document_content"  # Gescannte Dokumente
    METADATA = "metadata"  # Verarbeitungsinfo
    ANONYMOUS = "anonymous"  # Anonymisierte Daten


class ProcessingPurpose(Enum):
    """GDPR Processing Purposes - Art. 6 DSGVO"""
    DOCUMENT_DIGITIZATION = "document_digitization"
    OCR_PROCESSING = "ocr_processing"
    QUALITY_IMPROVEMENT = "quality_improvement"
    LEGAL_COMPLIANCE = "legal_compliance"
    BUSINESS_OPERATION = "business_operation"


class DataSubject:
    """GDPR Data Subject Information"""

    def __init__(
        self,
        subject_id: str,
        consent_given: bool = False,
        consent_timestamp: Optional[datetime] = None
    ):
        self.subject_id = subject_id
        self.consent_given = consent_given
        self.consent_timestamp = consent_timestamp
        self.data_categories: List[DataCategory] = []
        self.processing_purposes: List[ProcessingPurpose] = []
        self.deletion_requested = False
        self.deletion_deadline: Optional[datetime] = None

    def request_deletion(self) -> datetime:
        """Art. 17 DSGVO - Right to Erasure"""
        self.deletion_requested = True
        # 30 days to process deletion request
        self.deletion_deadline = datetime.now() + timedelta(days=30)
        logger.info("deletion_requested", subject_id=self.subject_id)
        return self.deletion_deadline

    def has_valid_consent(self) -> bool:
        """Check if consent is valid"""
        if not self.consent_given:
            return False

        # Consent must be renewed annually (conservative approach)
        if self.consent_timestamp:
            one_year_ago = datetime.now() - timedelta(days=365)
            return self.consent_timestamp > one_year_ago

        return False


class GDPRComplianceManager:
    """
    GDPR Compliance Management System.

    SECURITY UPDATE: Processing activities werden jetzt in PostgreSQL gespeichert,
    nicht mehr in-memory. Dies gewährleistet:
    - Persistenz über Restarts
    - Konsistenz zwischen Worker-Instanzen
    - Compliance-Audit-Fähigkeit
    """

    def __init__(self):
        self.data_subjects: Dict[str, DataSubject] = {}
        # DEPRECATED: In-memory storage nur noch als Fallback
        self._processing_activities_cache: List[Dict] = []
        self.data_breaches: List[Dict] = []

    async def register_processing_activity_async(
        self,
        db: "AsyncSession",
        document_id: str,
        data_categories: List[DataCategory],
        purpose: ProcessingPurpose,
        subject_id: Optional[str] = None,
        processing_backend: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Art. 30 DSGVO - Record of Processing Activities (Async/DB).

        SECURITY: Diese Methode speichert in PostgreSQL für Persistenz.

        Args:
            db: AsyncSession für Datenbankzugriff
            document_id: UUID des verarbeiteten Dokuments
            data_categories: Liste der Datenkategorien
            purpose: Verarbeitungszweck
            subject_id: Optional - User-ID (wird gehasht)
            processing_backend: Optional - Verwendetes OCR-Backend

        Returns:
            Dict mit Activity-Details
        """
        from app.db.models import GDPRProcessingActivity

        now = datetime.now(timezone.utc)
        activity_id = hashlib.sha256(
            f"{document_id}{now.isoformat()}".encode()
        ).hexdigest()[:16]

        retention_days = self._get_retention_period(data_categories)
        retention_expires = now + timedelta(days=retention_days)

        # Hash subject_id for privacy
        hashed_subject = None
        if subject_id:
            hashed_subject = self.pseudonymize_identifier(subject_id)

        # Parse document_id
        try:
            doc_uuid = UUID(document_id) if document_id else None
        except (ValueError, TypeError):
            doc_uuid = None

        # Create database record
        activity = GDPRProcessingActivity(
            activity_id=activity_id,
            document_id=doc_uuid,
            subject_id=hashed_subject,
            data_categories=[cat.value for cat in data_categories],
            processing_purpose=purpose.value,
            legal_basis=self._determine_legal_basis(purpose),
            retention_period_days=retention_days,
            retention_expires_at=retention_expires,
            processing_backend=processing_backend,
            processed_by_system="ablage-system-ocr"
        )

        db.add(activity)
        await db.commit()
        await db.refresh(activity)

        logger.info(
            "processing_activity_registered_db",
            activity_id=activity_id,
            document_id=str(doc_uuid)[:8] + "..." if doc_uuid else None,
            purpose=purpose.value
        )

        return {
            "id": activity_id,
            "document_id": document_id,
            "timestamp": now.isoformat(),
            "data_categories": [cat.value for cat in data_categories],
            "purpose": purpose.value,
            "subject_id": hashed_subject,
            "legal_basis": self._determine_legal_basis(purpose),
            "retention_period_days": retention_days,
            "retention_expires_at": retention_expires.isoformat()
        }

    def register_processing_activity(
        self,
        document_id: str,
        data_categories: List[DataCategory],
        purpose: ProcessingPurpose,
        subject_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Art. 30 DSGVO - Record of Processing Activities (Sync/In-Memory Fallback).

        DEPRECATED: Verwende register_processing_activity_async für Persistenz.
        Diese Methode existiert für Rückwärtskompatibilität.
        """
        now = datetime.now(timezone.utc)
        activity = {
            "id": hashlib.sha256(f"{document_id}{now.isoformat()}".encode()).hexdigest()[:16],
            "document_id": document_id,
            "timestamp": now.isoformat(),
            "data_categories": [cat.value for cat in data_categories],
            "purpose": purpose.value,
            "subject_id": subject_id,
            "legal_basis": self._determine_legal_basis(purpose),
            "retention_period_days": self._get_retention_period(data_categories)
        }

        self._processing_activities_cache.append(activity)
        logger.warning(
            "processing_activity_registered_memory",
            activity_id=activity['id'],
            warning="In-Memory-Speicherung ist deprecated. Verwende register_processing_activity_async."
        )

        return activity

    def _determine_legal_basis(self, purpose: ProcessingPurpose) -> str:
        """Determine legal basis for processing - Art. 6 DSGVO"""
        legal_bases = {
            ProcessingPurpose.DOCUMENT_DIGITIZATION: "Art. 6(1)(b) - Contract performance",
            ProcessingPurpose.OCR_PROCESSING: "Art. 6(1)(b) - Contract performance",
            ProcessingPurpose.QUALITY_IMPROVEMENT: "Art. 6(1)(f) - Legitimate interest",
            ProcessingPurpose.LEGAL_COMPLIANCE: "Art. 6(1)(c) - Legal obligation",
            ProcessingPurpose.BUSINESS_OPERATION: "Art. 6(1)(f) - Legitimate interest"
        }

        return legal_bases.get(purpose, "Art. 6(1)(a) - Consent")

    def _get_retention_period(self, data_categories: List[DataCategory]) -> int:
        """Get data retention period in days"""
        # Conservative retention periods
        retention_periods = {
            DataCategory.PERSONAL_IDENTIFIABLE: 365,  # 1 year
            DataCategory.SPECIAL_CATEGORY: 180,       # 6 months
            DataCategory.FINANCIAL: 3650,             # 10 years (German tax law)
            DataCategory.CONTACT: 365,
            DataCategory.DOCUMENT_CONTENT: 2555,      # 7 years (German commercial law)
            DataCategory.METADATA: 90,
            DataCategory.ANONYMOUS: 999999            # Indefinite
        }

        # Return maximum retention period for any category
        max_period = max(
            retention_periods.get(cat, 365)
            for cat in data_categories
        )

        return max_period

    def check_sensitive_data(self, text: str) -> Dict[str, Any]:
        """Detect potentially sensitive data in text"""
        import re

        findings = {
            "has_sensitive_data": False,
            "data_types": [],
            "recommendations": []
        }

        # German SSN (Sozialversicherungsnummer)
        if re.search(r'\d{2}\s?\d{6}\s?[A-Z]\s?\d{3}', text):
            findings["has_sensitive_data"] = True
            findings["data_types"].append("sozialversicherungsnummer")
            findings["recommendations"].append("Anonymize SSN before storage")

        # Tax ID (Steuer-ID)
        if re.search(r'\d{11}', text):
            findings["has_sensitive_data"] = True
            findings["data_types"].append("steuer_id")
            findings["recommendations"].append("Anonymize Tax ID")

        # IBAN
        if re.search(r'DE\d{20}', text):
            findings["has_sensitive_data"] = True
            findings["data_types"].append("iban")
            findings["recommendations"].append("Redact IBAN")

        # Email
        if re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text):
            findings["has_sensitive_data"] = True
            findings["data_types"].append("email")

        # Phone numbers (Deutsche Formate mit 2-4 stelligen Vorwahlen)
        if re.search(r'(\+49|0049|0)\s?\d{2,4}\s?\d{5,}', text):
            findings["has_sensitive_data"] = True
            findings["data_types"].append("phone")

        return findings

    def anonymize_text(self, text: str, use_pseudonymization: bool = False) -> str:
        """
        Anonymize sensitive data in text.

        Args:
            text: Text containing potential PII
            use_pseudonymization: If True, use SHA-256 hashed pseudonyms
                                  (allows linking, but not reversing)
                                  If False, use generic placeholders

        Returns:
            Anonymized/pseudonymized text
        """
        import re

        anonymized = text

        if use_pseudonymization:
            # SHA-256 based pseudonymization (linkable within system)
            anonymized = self._pseudonymize_with_sha256(anonymized)
        else:
            # Simple anonymization with generic placeholders
            anonymized = self._anonymize_with_placeholders(anonymized)

        return anonymized

    def _pseudonymize_with_sha256(self, text: str) -> str:
        """
        Pseudonymize PII with SHA-256 hashes.

        Creates consistent pseudonyms - same PII produces same hash.
        This allows for data analysis while protecting identity.
        """
        import re

        def hash_match(match: re.Match, prefix: str = "") -> str:
            """Hash a regex match with SHA-256."""
            value = match.group(0)
            hashed = hashlib.sha256(value.encode()).hexdigest()[:16]
            return f"[{prefix}:{hashed}]"

        anonymized = text

        # Pseudonymize German SSN with hash
        anonymized = re.sub(
            r'\d{2}\s?\d{6}\s?[A-Z]\s?\d{3}',
            lambda m: hash_match(m, "SSN"),
            anonymized
        )

        # Pseudonymize Tax ID with hash
        anonymized = re.sub(
            r'(?<!\d)\d{11}(?!\d)',
            lambda m: hash_match(m, "TAX"),
            anonymized
        )

        # Pseudonymize IBAN with hash (keep DE prefix for format)
        anonymized = re.sub(
            r'(DE)\d{20}',
            lambda m: f"DE{hashlib.sha256(m.group(0).encode()).hexdigest()[:20]}",
            anonymized
        )

        # Pseudonymize Email with hash (keep domain visible)
        def hash_email(m: re.Match) -> str:
            email = m.group(0)
            parts = email.split('@')
            hashed_local = hashlib.sha256(parts[0].encode()).hexdigest()[:8]
            return f"[EMAIL:{hashed_local}@{parts[1]}]"

        anonymized = re.sub(
            r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
            hash_email,
            anonymized
        )

        # Pseudonymize Phone with hash (Deutsche Formate mit 2-4 stelligen Vorwahlen)
        anonymized = re.sub(
            r'(\+49|0049|0)\s?\d{2,4}\s?\d{5,}',
            lambda m: hash_match(m, "PHONE"),
            anonymized
        )

        # Pseudonymize Names (German pattern: Herr/Frau + Name)
        anonymized = re.sub(
            r'(Herr|Frau|Hr\.|Fr\.)\s+([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)?)',
            lambda m: f"{m.group(1)} [NAME:{hashlib.sha256(m.group(2).encode()).hexdigest()[:12]}]",
            anonymized
        )

        return anonymized

    def _anonymize_with_placeholders(self, text: str) -> str:
        """Anonymize with generic placeholders (non-linkable)."""
        import re

        anonymized = text

        # Anonymize German SSN
        anonymized = re.sub(
            r'\d{2}\s?\d{6}\s?[A-Z]\s?\d{3}',
            '[SSN_ANONYMIZED]',
            anonymized
        )

        # Anonymize Tax ID
        anonymized = re.sub(
            r'(?<!\d)\d{11}(?!\d)',
            '[TAX_ID_ANONYMIZED]',
            anonymized
        )

        # Anonymize IBAN
        anonymized = re.sub(
            r'DE\d{20}',
            'DE********************',
            anonymized
        )

        # Anonymize Email
        anonymized = re.sub(
            r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
            '[EMAIL_ANONYMIZED]',
            anonymized
        )

        # Anonymize Phone (Deutsche Formate mit 2-4 stelligen Vorwahlen)
        anonymized = re.sub(
            r'(\+49|0049|0)\s?\d{2,4}\s?\d{5,}',
            '[PHONE_ANONYMIZED]',
            anonymized
        )

        return anonymized

    def pseudonymize_identifier(self, identifier: str, salt: Optional[str] = None) -> str:
        """
        Pseudonymize a single identifier with SHA-256.

        Art. 4(5) DSGVO - Pseudonymisierung: Verarbeitung personenbezogener Daten
        in einer Weise, dass die Daten ohne Hinzuziehung zusätzlicher Informationen
        nicht mehr einer spezifischen betroffenen Person zugeordnet werden können.

        Args:
            identifier: The identifier to pseudonymize (email, user_id, etc.)
            salt: Optional salt for additional security (stored separately)

        Returns:
            SHA-256 hash of the identifier
        """
        if salt:
            combined = f"{salt}:{identifier}"
        else:
            combined = identifier

        return hashlib.sha256(combined.encode('utf-8')).hexdigest()

    def anonymize_ip_address(self, ip: str) -> str:
        """
        Anonymize IP address for logging (GDPR-compliant).

        IPv4: Last octet zeroed (e.g., 192.168.1.100 -> 192.168.1.0)
        IPv6: Last 80 bits zeroed
        """
        if not ip:
            return "[NO_IP]"

        if ':' in ip:
            # IPv6: Keep first 48 bits (3 groups)
            parts = ip.split(':')
            anonymized_parts = parts[:3] + ['0'] * (len(parts) - 3)
            return ':'.join(anonymized_parts)
        else:
            # IPv4: Zero last octet
            parts = ip.split('.')
            if len(parts) == 4:
                return f"{parts[0]}.{parts[1]}.{parts[2]}.0"
            return "[INVALID_IP]"

    def hash_for_audit(self, data: str) -> str:
        """
        Create a one-way hash for audit logging.

        Used to track actions on specific data without storing the actual data.
        """
        return hashlib.sha256(data.encode('utf-8')).hexdigest()[:32]

    def handle_data_breach(
        self,
        breach_type: str,
        affected_records: int,
        description: str
    ) -> Dict[str, Any]:
        """Art. 33 DSGVO - Data Breach Notification"""

        breach = {
            "id": hashlib.sha256(f"{datetime.now().isoformat()}".encode()).hexdigest()[:16],
            "timestamp": datetime.now().isoformat(),
            "breach_type": breach_type,
            "affected_records": affected_records,
            "description": description,
            "notification_required": affected_records > 0,
            "notification_deadline": (datetime.now() + timedelta(hours=72)).isoformat()
        }

        self.data_breaches.append(breach)

        # Log critical breach
        logger.critical("data_breach_detected", breach_type=breach_type, affected_records=affected_records)

        return breach

    def generate_data_export(self, subject_id: str) -> Dict[str, Any]:
        """Art. 20 DSGVO - Right to Data Portability"""

        # Get all processing activities for this subject
        subject_activities = [
            activity for activity in self.processing_activities
            if activity.get("subject_id") == subject_id
        ]

        export = {
            "subject_id": subject_id,
            "export_timestamp": datetime.now().isoformat(),
            "processing_activities": subject_activities,
            "format": "JSON",
            "notice": "This export contains all personal data we have processed for you"
        }

        logger.info("data_export_generated", subject_id=subject_id)

        return export

    async def check_retention_compliance_async(
        self,
        db: "AsyncSession"
    ) -> Dict[str, Any]:
        """
        Check which data should be deleted based on retention periods (DB).

        Art. 5(1)(e) DSGVO - Speicherbegrenzung.

        Args:
            db: AsyncSession für Datenbankzugriff

        Returns:
            Dict mit Compliance-Status und ablaufenden Aktivitäten
        """
        from sqlalchemy import select, func
        from app.db.models import GDPRProcessingActivity

        now = datetime.now(timezone.utc)

        # Count total activities
        total_result = await db.execute(
            select(func.count()).select_from(GDPRProcessingActivity)
        )
        total_count = total_result.scalar() or 0

        # Find expired activities
        expired_result = await db.execute(
            select(GDPRProcessingActivity).where(
                GDPRProcessingActivity.retention_expires_at < now
            ).limit(100)  # Limit for performance
        )
        expired_activities = expired_result.scalars().all()

        expired_list = []
        for activity in expired_activities:
            days_expired = (now - activity.retention_expires_at).days if activity.retention_expires_at else 0
            expired_list.append({
                "activity_id": activity.activity_id,
                "document_id": str(activity.document_id) if activity.document_id else None,
                "expired_since_days": days_expired,
                "purpose": activity.processing_purpose
            })

        logger.info(
            "retention_compliance_checked",
            total=total_count,
            expired=len(expired_list)
        )

        return {
            "total_activities": total_count,
            "expired_activities": len(expired_list),
            "to_be_deleted": expired_list,
            "check_timestamp": now.isoformat()
        }

    def check_retention_compliance(self) -> Dict[str, Any]:
        """
        Check which data should be deleted (In-Memory Fallback).

        DEPRECATED: Verwende check_retention_compliance_async für DB-Zugriff.
        """
        now = datetime.now(timezone.utc)
        expired_activities = []

        for activity in self._processing_activities_cache:
            retention_days = activity["retention_period_days"]
            activity_date = datetime.fromisoformat(activity["timestamp"])
            if activity_date.tzinfo is None:
                activity_date = activity_date.replace(tzinfo=timezone.utc)
            expiry_date = activity_date + timedelta(days=retention_days)

            if now > expiry_date:
                expired_activities.append({
                    "activity_id": activity["id"],
                    "document_id": activity["document_id"],
                    "expired_since": (now - expiry_date).days
                })

        return {
            "total_activities": len(self._processing_activities_cache),
            "expired_activities": len(expired_activities),
            "to_be_deleted": expired_activities
        }

    async def get_compliance_report_async(
        self,
        db: "AsyncSession"
    ) -> Dict[str, Any]:
        """
        Generate GDPR compliance report (DB).

        Erstellt umfassenden Compliance-Bericht für Audits.

        Args:
            db: AsyncSession für Datenbankzugriff

        Returns:
            Dict mit vollständigem Compliance-Report
        """
        from sqlalchemy import select, func
        from app.db.models import (
            GDPRProcessingActivity,
            GDPRDeletionRequest,
            GDPRBreachLog,
            GDPRConsentLog,
            User
        )

        now = datetime.now(timezone.utc)

        # Processing activities count
        activities_result = await db.execute(
            select(func.count()).select_from(GDPRProcessingActivity)
        )
        total_activities = activities_result.scalar() or 0

        # Pending deletion requests
        pending_deletions_result = await db.execute(
            select(func.count()).select_from(GDPRDeletionRequest).where(
                GDPRDeletionRequest.status == "pending"
            )
        )
        pending_deletions = pending_deletions_result.scalar() or 0

        # Data breaches
        breaches_result = await db.execute(
            select(func.count()).select_from(GDPRBreachLog)
        )
        total_breaches = breaches_result.scalar() or 0

        # Active consents
        consents_result = await db.execute(
            select(func.count()).select_from(GDPRConsentLog).where(
                GDPRConsentLog.consent_given == True,
                GDPRConsentLog.withdrawal_date == None
            )
        )
        active_consents = consents_result.scalar() or 0

        # Retention compliance check
        retention_check = await self.check_retention_compliance_async(db)

        # Users with deletion scheduled
        scheduled_deletions_result = await db.execute(
            select(func.count()).select_from(User).where(
                User.deletion_scheduled_for != None,
                User.deletion_confirmed == True
            )
        )
        scheduled_deletions = scheduled_deletions_result.scalar() or 0

        logger.info(
            "compliance_report_generated",
            activities=total_activities,
            pending_deletions=pending_deletions,
            breaches=total_breaches
        )

        return {
            "timestamp": now.isoformat(),
            "total_processing_activities": total_activities,
            "total_data_subjects": active_consents,
            "total_data_breaches": total_breaches,
            "pending_deletion_requests": pending_deletions,
            "scheduled_user_deletions": scheduled_deletions,
            "retention_compliance": retention_check,
            "report_type": "full_compliance",
            "gdpr_articles_covered": [
                "Art. 5 - Grundsätze",
                "Art. 7 - Einwilligung",
                "Art. 17 - Recht auf Löschung",
                "Art. 30 - Verarbeitungsverzeichnis",
                "Art. 33 - Datenschutzvorfälle"
            ]
        }

    def get_compliance_report(self) -> Dict[str, Any]:
        """
        Generate GDPR compliance report (In-Memory Fallback).

        DEPRECATED: Verwende get_compliance_report_async für DB-Zugriff.
        """
        retention_check = self.check_retention_compliance()

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_processing_activities": len(self._processing_activities_cache),
            "total_data_subjects": len(self.data_subjects),
            "total_data_breaches": len(self.data_breaches),
            "retention_compliance": retention_check,
            "pending_deletions": [
                sub_id for sub_id, subject in self.data_subjects.items()
                if subject.deletion_requested
            ],
            "warning": "In-Memory-Report - verwende get_compliance_report_async für vollständigen Report"
        }

    async def get_processing_activities_async(
        self,
        db: "AsyncSession",
        document_id: Optional[str] = None,
        subject_id: Optional[str] = None,
        purpose: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Retrieve processing activities from database.

        Args:
            db: AsyncSession für Datenbankzugriff
            document_id: Optional - Filter nach Dokument
            subject_id: Optional - Filter nach Subject (wird gehasht)
            purpose: Optional - Filter nach Zweck
            limit: Max. Anzahl Ergebnisse
            offset: Offset für Pagination

        Returns:
            Liste der Processing Activities
        """
        from sqlalchemy import select
        from app.db.models import GDPRProcessingActivity

        query = select(GDPRProcessingActivity)

        if document_id:
            try:
                doc_uuid = UUID(document_id)
                query = query.where(GDPRProcessingActivity.document_id == doc_uuid)
            except (ValueError, TypeError):
                pass

        if subject_id:
            hashed_subject = self.pseudonymize_identifier(subject_id)
            query = query.where(GDPRProcessingActivity.subject_id == hashed_subject)

        if purpose:
            query = query.where(GDPRProcessingActivity.processing_purpose == purpose)

        query = query.order_by(GDPRProcessingActivity.created_at.desc())
        query = query.limit(limit).offset(offset)

        result = await db.execute(query)
        activities = result.scalars().all()

        return [
            {
                "id": a.activity_id,
                "document_id": str(a.document_id) if a.document_id else None,
                "subject_id": a.subject_id,
                "data_categories": a.data_categories,
                "purpose": a.processing_purpose,
                "legal_basis": a.legal_basis,
                "retention_period_days": a.retention_period_days,
                "retention_expires_at": a.retention_expires_at.isoformat() if a.retention_expires_at else None,
                "processing_backend": a.processing_backend,
                "created_at": a.created_at.isoformat() if a.created_at else None
            }
            for a in activities
        ]

    @property
    def processing_activities(self) -> List[Dict]:
        """
        Property für Rückwärtskompatibilität.

        DEPRECATED: Gibt nur in-memory Cache zurück.
        Verwende get_processing_activities_async für DB-Zugriff.
        """
        logger.warning(
            "deprecated_property_access",
            property="processing_activities",
            warning="Verwende get_processing_activities_async für DB-Zugriff"
        )
        return self._processing_activities_cache


# Global singleton instance
_gdpr_manager = None


def get_gdpr_manager() -> GDPRComplianceManager:
    """Get global GDPR Manager instance"""
    global _gdpr_manager
    if _gdpr_manager is None:
        _gdpr_manager = GDPRComplianceManager()
    return _gdpr_manager
