"""Scanner Integration Service.

Manages scanner devices and scan jobs. Works with:
- Local scanning agent (Windows WIA / Linux SANE)
- WebUSB direct browser scanning (experimental)
- Network scanner HTTP push

The scanner agent polls for scan jobs and pushes scanned images.
"""

import structlog
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict
from uuid import UUID, uuid4
from enum import Enum

logger = structlog.get_logger(__name__)

class ScannerType(str, Enum):
    WIA = "wia"         # Windows Image Acquisition
    SANE = "sane"       # Scanner Access Now Easy (Linux)
    NETWORK = "network" # Network scanner (HTTP push)
    WEBUSB = "webusb"   # Browser WebUSB API

class ScanResolution(str, Enum):
    DRAFT = "150"       # 150 DPI
    STANDARD = "300"    # 300 DPI (default for documents)
    HIGH = "600"        # 600 DPI
    ULTRA = "1200"      # 1200 DPI (photos)

class ScanColorMode(str, Enum):
    COLOR = "color"
    GRAYSCALE = "grayscale"
    BW = "bw"           # Black & white (1-bit)

class ScanJobStatus(str, Enum):
    PENDING = "pending"
    SCANNING = "scanning"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class ScannerDevice:
    """Registriertes Scanner-Gerät."""
    id: str
    name: str
    scanner_type: ScannerType
    model: Optional[str] = None
    location: Optional[str] = None
    has_adf: bool = False  # Automatic Document Feeder
    has_duplex: bool = False
    max_resolution: int = 600
    is_online: bool = False
    last_seen: Optional[datetime] = None

@dataclass
class ScanJob:
    """Scan-Auftrag."""
    id: str
    scanner_id: str
    company_id: str
    user_id: str
    resolution: ScanResolution = ScanResolution.STANDARD
    color_mode: ScanColorMode = ScanColorMode.COLOR
    use_adf: bool = False
    duplex: bool = False
    status: ScanJobStatus = ScanJobStatus.PENDING
    pages_scanned: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    document_ids: List[str] = field(default_factory=list)

# In-memory store (production would use Redis/DB)
_registered_scanners: Dict[str, ScannerDevice] = {}
_scan_jobs: Dict[str, ScanJob] = {}

class ScannerService:
    """Scanner-Verwaltungsdienst."""

    def register_scanner(self, device: ScannerDevice) -> ScannerDevice:
        """Registriert ein Scanner-Gerät."""
        _registered_scanners[device.id] = device
        logger.info("scanner_registered", scanner_id=device.id, name=device.name)
        return device

    def unregister_scanner(self, scanner_id: str) -> bool:
        """Entfernt Scanner-Registrierung."""
        if scanner_id in _registered_scanners:
            del _registered_scanners[scanner_id]
            logger.info("scanner_unregistered", scanner_id=scanner_id)
            return True
        return False

    def list_scanners(self) -> List[ScannerDevice]:
        """Listet alle registrierten Scanner."""
        return list(_registered_scanners.values())

    def heartbeat(self, scanner_id: str) -> bool:
        """Scanner meldet sich als online."""
        if scanner_id in _registered_scanners:
            _registered_scanners[scanner_id].is_online = True
            _registered_scanners[scanner_id].last_seen = datetime.now(timezone.utc)
            return True
        return False

    def create_scan_job(self, scanner_id: str, company_id: UUID, user_id: UUID,
                        resolution: ScanResolution = ScanResolution.STANDARD,
                        color_mode: ScanColorMode = ScanColorMode.COLOR,
                        use_adf: bool = False, duplex: bool = False) -> ScanJob:
        """Erstellt einen neuen Scan-Auftrag."""
        if scanner_id not in _registered_scanners:
            raise ValueError("Scanner nicht gefunden")
        if not _registered_scanners[scanner_id].is_online:
            raise ValueError("Scanner ist offline")

        job = ScanJob(
            id=str(uuid4()),
            scanner_id=scanner_id,
            company_id=str(company_id),
            user_id=str(user_id),
            resolution=resolution,
            color_mode=color_mode,
            use_adf=use_adf,
            duplex=duplex,
        )
        _scan_jobs[job.id] = job
        logger.info("scan_job_created", job_id=job.id, scanner_id=scanner_id)
        return job

    def get_job(self, job_id: str) -> Optional[ScanJob]:
        """Liest Scan-Auftrag."""
        return _scan_jobs.get(job_id)

    def list_jobs(self, company_id: str, limit: int = 20) -> List[ScanJob]:
        """Listet Scan-Aufträge einer Firma."""
        jobs = [j for j in _scan_jobs.values() if j.company_id == company_id]
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs[:limit]

    def update_job_status(self, job_id: str, status: ScanJobStatus,
                          pages_scanned: int = 0, error_message: Optional[str] = None,
                          document_ids: Optional[List[str]] = None) -> Optional[ScanJob]:
        """Aktualisiert Scan-Auftrag Status (vom Scanner-Agent aufgerufen)."""
        job = _scan_jobs.get(job_id)
        if not job:
            return None
        job.status = status
        if pages_scanned:
            job.pages_scanned = pages_scanned
        if error_message:
            job.error_message = error_message
        if document_ids:
            job.document_ids = document_ids
        if status in (ScanJobStatus.COMPLETED, ScanJobStatus.FAILED):
            job.completed_at = datetime.now(timezone.utc)
        logger.info("scan_job_updated", job_id=job_id, status=status.value)
        return job

    def cancel_job(self, job_id: str) -> bool:
        """Bricht einen Scan-Auftrag ab."""
        job = _scan_jobs.get(job_id)
        if not job or job.status not in (ScanJobStatus.PENDING, ScanJobStatus.SCANNING):
            return False
        job.status = ScanJobStatus.CANCELLED
        job.completed_at = datetime.now(timezone.utc)
        return True
