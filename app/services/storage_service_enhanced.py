"""
MinIO Storage Service
S3-compatible object storage for documents with versioning, compression, and bulk operations
Priority: P0 - CRITICAL
Created: 2024-11-22
Updated: 2025-11-26 - Enhanced with full feature set
"""
from typing import Optional, BinaryIO, Dict, Any, List, AsyncIterator, Tuple
from pathlib import Path
import os
from datetime import timedelta, datetime
import mimetypes
import hashlib
import asyncio
from io import BytesIO
import gzip
import json
from contextlib import asynccontextmanager

import structlog

try:
    from minio import Minio
    from minio.error import S3Error
    from minio.commonconfig import CopySource
    MINIO_AVAILABLE = True
except ImportError:
    MINIO_AVAILABLE = False

logger = structlog.get_logger(__name__)


# ============================================================================
# GERMAN ERROR MESSAGES
# ============================================================================

GERMAN_ERRORS = {
    "minio_unavailable": "MinIO-Speicher ist nicht verfügbar",
    "document_not_found": "Dokument nicht gefunden",
    "upload_failed": "Upload fehlgeschlagen",
    "download_failed": "Download fehlgeschlagen",
    "delete_failed": "Löschen fehlgeschlagen",
    "connection_failed": "Verbindung zum Speicher fehlgeschlagen",
    "file_too_large": "Datei ist zu groß (Maximum: {max_mb} MB)",
    "invalid_format": "Ungültiges Dateiformat",
    "compression_failed": "Komprimierung fehlgeschlagen",
    "version_not_found": "Version nicht gefunden",
}
