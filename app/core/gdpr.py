"""
GDPR Compliance Framework for Ablage-System OCR
Data Privacy and Protection for German Document Processing
Created: 2024-11-22
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from enum import Enum
import hashlib
import logging
import json

logger = logging.getLogger(__name__)


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
        logger.info(f"Deletion requested for subject {self.subject_id}")
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
    """GDPR Compliance Management System"""

    def __init__(self):
        self.data_subjects: Dict[str, DataSubject] = {}
        self.processing_activities: List[Dict] = []
        self.data_breaches: List[Dict] = []

    def register_processing_activity(
        self,
        document_id: str,
        data_categories: List[DataCategory],
        purpose: ProcessingPurpose,
        subject_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Art. 30 DSGVO - Record of Processing Activities"""

        activity = {
            "id": hashlib.sha256(f"{document_id}{datetime.now().isoformat()}".encode()).hexdigest()[:16],
            "document_id": document_id,
            "timestamp": datetime.now().isoformat(),
            "data_categories": [cat.value for cat in data_categories],
            "purpose": purpose.value,
            "subject_id": subject_id,
            "legal_basis": self._determine_legal_basis(purpose),
            "retention_period_days": self._get_retention_period(data_categories)
        }

        self.processing_activities.append(activity)
        logger.info(f"Registered processing activity: {activity['id']}")

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

        # Phone numbers
        if re.search(r'(\+49|0049|0)\s?\d{3,4}\s?\d{6,}', text):
            findings["has_sensitive_data"] = True
            findings["data_types"].append("phone")

        return findings

    def anonymize_text(self, text: str) -> str:
        """Anonymize sensitive data in text"""
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

        # Anonymize Phone
        anonymized = re.sub(
            r'(\+49|0049|0)\s?\d{3,4}\s?\d{6,}',
            '[PHONE_ANONYMIZED]',
            anonymized
        )

        return anonymized

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
        logger.critical(
            f"Data breach detected: {breach_type} affecting {affected_records} records"
        )

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

        logger.info(f"Generated data export for subject {subject_id}")

        return export

    def check_retention_compliance(self) -> Dict[str, Any]:
        """Check which data should be deleted based on retention periods"""

        now = datetime.now()
        expired_activities = []

        for activity in self.processing_activities:
            retention_days = activity["retention_period_days"]
            activity_date = datetime.fromisoformat(activity["timestamp"])
            expiry_date = activity_date + timedelta(days=retention_days)

            if now > expiry_date:
                expired_activities.append({
                    "activity_id": activity["id"],
                    "document_id": activity["document_id"],
                    "expired_since": (now - expiry_date).days
                })

        return {
            "total_activities": len(self.processing_activities),
            "expired_activities": len(expired_activities),
            "to_be_deleted": expired_activities
        }

    def get_compliance_report(self) -> Dict[str, Any]:
        """Generate GDPR compliance report"""

        retention_check = self.check_retention_compliance()

        return {
            "timestamp": datetime.now().isoformat(),
            "total_processing_activities": len(self.processing_activities),
            "total_data_subjects": len(self.data_subjects),
            "total_data_breaches": len(self.data_breaches),
            "retention_compliance": retention_check,
            "pending_deletions": [
                sub_id for sub_id, subject in self.data_subjects.items()
                if subject.deletion_requested
            ]
        }


# Global singleton instance
_gdpr_manager = None


def get_gdpr_manager() -> GDPRComplianceManager:
    """Get global GDPR Manager instance"""
    global _gdpr_manager
    if _gdpr_manager is None:
        _gdpr_manager = GDPRComplianceManager()
    return _gdpr_manager
