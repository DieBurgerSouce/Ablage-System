"""
MinIO Storage Service
S3-compatible object storage for documents
Priority: P0 - CRITICAL
Created: 2024-11-22
"""
from typing import Optional, BinaryIO, Dict, Any
from pathlib import Path
import os
import structlog
from datetime import timedelta
import mimetypes
import hashlib

try:
    from minio import Minio
    from minio.error import S3Error
    MINIO_AVAILABLE = True
except ImportError:
    MINIO_AVAILABLE = False
    Minio = None  # type: ignore

    # Fallback S3Error class for when minio is not installed
    class S3Error(Exception):  # type: ignore
        """Fallback S3Error when minio is not installed."""

        def __init__(
            self,
            code: str = "",
            message: str = "",
            resource: str = "",
            **kwargs: object
        ):
            self.code = code
            self.message = message
            self.resource = resource
            super().__init__(message)

logger = structlog.get_logger(__name__)


# ============================================================================
# CONFIGURATION
# ============================================================================

class StorageConfig:
    """MinIO configuration from environment"""

    def __init__(self):
        self.ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
        self.ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
        self.SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
        self.SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

        # Buckets
        self.DOCUMENTS_BUCKET = os.getenv("MINIO_DOCUMENTS_BUCKET", "documents")
        self.THUMBNAILS_BUCKET = os.getenv("MINIO_THUMBNAILS_BUCKET", "thumbnails")
        self.EXPORTS_BUCKET = os.getenv("MINIO_EXPORTS_BUCKET", "exports")

        # Settings
        self.PRESIGNED_URL_EXPIRY_HOURS = int(os.getenv("MINIO_PRESIGNED_EXPIRY", "24"))
        self.MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "50"))


# ============================================================================
# STORAGE SERVICE
# ============================================================================

class StorageService:
    """MinIO object storage manager"""

    def __init__(self):
        self.config = StorageConfig()
        self.client: Optional[Minio] = None
        self.available = MINIO_AVAILABLE

        if self.available:
            try:
                self._initialize_client()
                self._ensure_buckets()
            except Exception as e:
                logger.error("minio_init_failed", error=str(e))
                self.available = False

    def _initialize_client(self):
        """Initialize MinIO client"""
        try:
            self.client = Minio(
                self.config.ENDPOINT,
                access_key=self.config.ACCESS_KEY,
                secret_key=self.config.SECRET_KEY,
                secure=self.config.SECURE
            )

            # Test connection
            self.client.list_buckets()

            logger.info(
                "minio_initialized",
                endpoint=self.config.ENDPOINT,
                secure=self.config.SECURE
            )

        except Exception as e:
            logger.error("minio_initialization_failed", error=str(e), exc_info=True)
            raise

    def _ensure_buckets(self):
        """Ensure required buckets exist"""
        buckets = [
            self.config.DOCUMENTS_BUCKET,
            self.config.THUMBNAILS_BUCKET,
            self.config.EXPORTS_BUCKET
        ]

        for bucket in buckets:
            try:
                if not self.client.bucket_exists(bucket):
                    self.client.make_bucket(bucket)
                    logger.info("bucket_created", bucket=bucket)
            except Exception as e:
                logger.error("bucket_creation_failed", bucket=bucket, error=str(e))

    # ========================================================================
    # UPLOAD OPERATIONS
    # ========================================================================

    async def upload_document(
        self,
        file_data: bytes,
        filename: str,
        content_type: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Upload document to storage

        Args:
            file_data: File binary data
            filename: Original filename
            content_type: MIME type
            user_id: Owner user ID
            metadata: Additional metadata

        Returns:
            Upload result with storage path and metadata
        """
        if not self.available:
            raise RuntimeError("MinIO not available")

        try:
            # Generate unique object key
            file_hash = hashlib.sha256(file_data).hexdigest()
            extension = Path(filename).suffix
            object_key = f"{user_id or 'anonymous'}/{file_hash}{extension}"

            # Detect content type
            if not content_type:
                content_type, _ = mimetypes.guess_type(filename)
                if not content_type:
                    content_type = "application/octet-stream"

            # Prepare metadata
            minio_metadata = {
                "original-filename": filename,
                "sha256": file_hash,
                **(metadata or {})
            }

            # Upload to MinIO
            from io import BytesIO
            self.client.put_object(
                bucket_name=self.config.DOCUMENTS_BUCKET,
                object_name=object_key,
                data=BytesIO(file_data),
                length=len(file_data),
                content_type=content_type,
                metadata=minio_metadata
            )

            logger.info(
                "document_uploaded",
                filename=filename,
                size_bytes=len(file_data),
                object_key=object_key
            )

            return {
                "success": True,
                "storage_path": object_key,
                "bucket": self.config.DOCUMENTS_BUCKET,
                "size_bytes": len(file_data),
                "content_type": content_type,
                "sha256": file_hash
            }

        except S3Error as e:
            logger.error("minio_upload_failed", error=str(e), exc_info=True)
            raise
        except Exception as e:
            logger.error("upload_failed", error=str(e), exc_info=True)
            raise

    async def upload_thumbnail(
        self,
        thumbnail_data: bytes,
        document_id: str,
        format: str = "png"
    ) -> str:
        """Upload document thumbnail"""
        try:
            object_key = f"{document_id}/thumbnail.{format}"

            from io import BytesIO
            self.client.put_object(
                bucket_name=self.config.THUMBNAILS_BUCKET,
                object_name=object_key,
                data=BytesIO(thumbnail_data),
                length=len(thumbnail_data),
                content_type=f"image/{format}"
            )

            logger.info("thumbnail_uploaded", object_key=object_key)
            return object_key

        except Exception as e:
            logger.error("thumbnail_upload_failed", error=str(e), exc_info=True)
            raise

    # ========================================================================
    # DOWNLOAD OPERATIONS
    # ========================================================================

    async def download_document(self, object_key: str) -> bytes:
        """Download document from storage"""
        if not self.available:
            raise RuntimeError("MinIO not available")

        try:
            response = self.client.get_object(
                bucket_name=self.config.DOCUMENTS_BUCKET,
                object_name=object_key
            )

            data = response.read()
            response.close()
            response.release_conn()

            logger.info("document_downloaded", object_key=object_key, size=len(data))
            return data

        except S3Error as e:
            logger.error("minio_download_failed", error=str(e), exc_info=True)
            raise
        except Exception as e:
            logger.error("download_failed", error=str(e), exc_info=True)
            raise

    async def get_presigned_url(
        self,
        object_key: str,
        expiry_hours: Optional[int] = None
    ) -> str:
        """Generate presigned URL for temporary access"""
        if not self.available:
            raise RuntimeError("MinIO not available")

        try:
            expiry = timedelta(hours=expiry_hours or self.config.PRESIGNED_URL_EXPIRY_HOURS)

            url = self.client.presigned_get_object(
                bucket_name=self.config.DOCUMENTS_BUCKET,
                object_name=object_key,
                expires=expiry
            )

            logger.info("presigned_url_generated", object_key=object_key, expiry=str(expiry))
            return url

        except Exception as e:
            logger.error("presigned_url_generation_failed", error=str(e), exc_info=True)
            raise

    # ========================================================================
    # DELETE OPERATIONS
    # ========================================================================

    async def delete_document(self, object_key: str) -> bool:
        """Delete document from storage"""
        if not self.available:
            raise RuntimeError("MinIO not available")

        try:
            self.client.remove_object(
                bucket_name=self.config.DOCUMENTS_BUCKET,
                object_name=object_key
            )

            logger.info("document_deleted", object_key=object_key)
            return True

        except S3Error as e:
            logger.error("minio_delete_failed", error=str(e), exc_info=True)
            return False
        except Exception as e:
            logger.error("delete_failed", error=str(e), exc_info=True)
            return False

    async def delete_user_documents(self, user_id: str) -> int:
        """Delete all documents for a user (GDPR compliance)"""
        if not self.available:
            raise RuntimeError("MinIO not available")

        try:
            deleted_count = 0
            prefix = f"{user_id}/"

            # List all objects with user prefix
            objects = self.client.list_objects(
                bucket_name=self.config.DOCUMENTS_BUCKET,
                prefix=prefix,
                recursive=True
            )

            # Delete each object
            for obj in objects:
                self.client.remove_object(
                    bucket_name=self.config.DOCUMENTS_BUCKET,
                    object_name=obj.object_name
                )
                deleted_count += 1

            logger.info("user_documents_deleted", user_id=user_id, count=deleted_count)
            return deleted_count

        except Exception as e:
            logger.error("batch_delete_failed", error=str(e), exc_info=True)
            raise

    # ========================================================================
    # HEALTH & STATS
    # ========================================================================

    async def health_check(self) -> Dict[str, Any]:
        """Check MinIO connectivity and status"""
        try:
            if not self.available:
                return {
                    "status": "unavailable",
                    "error": "MinIO client not initialized"
                }

            # Try to list buckets
            buckets = self.client.list_buckets()

            return {
                "status": "healthy",
                "endpoint": self.config.ENDPOINT,
                "buckets": len(buckets),
                "available_buckets": [b.name for b in buckets]
            }

        except Exception as e:
            logger.error("minio_health_check_failed", error=str(e), exc_info=True)
            return {
                "status": "unhealthy",
                "error": str(e)
            }

    async def get_storage_stats(self) -> Dict[str, Any]:
        """Get storage usage statistics"""
        try:
            if not self.available:
                return {"error": "MinIO not available"}

            stats = {
                "documents": {"count": 0, "size_bytes": 0},
                "thumbnails": {"count": 0, "size_bytes": 0},
                "exports": {"count": 0, "size_bytes": 0}
            }

            # Get stats for each bucket
            for bucket_name in stats.keys():
                minio_bucket = getattr(self.config, f"{bucket_name.upper()}_BUCKET")

                objects = self.client.list_objects(
                    bucket_name=minio_bucket,
                    recursive=True
                )

                for obj in objects:
                    stats[bucket_name]["count"] += 1
                    stats[bucket_name]["size_bytes"] += obj.size

            # Add totals
            stats["total_size_bytes"] = sum(b["size_bytes"] for b in stats.values() if isinstance(b, dict))
            stats["total_count"] = sum(b["count"] for b in stats.values() if isinstance(b, dict))

            return stats

        except Exception as e:
            logger.error("storage_stats_failed", error=str(e), exc_info=True)
            return {"error": str(e)}


# ============================================================================
# FACTORY
# ============================================================================

_storage_service: Optional[StorageService] = None


def get_storage_service() -> StorageService:
    """Get singleton storage service instance"""
    global _storage_service

    if _storage_service is None:
        _storage_service = StorageService()

    return _storage_service
