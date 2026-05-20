"""
MinIO Storage Service
S3-compatible object storage for documents
Priority: P0 - CRITICAL
Created: 2024-11-22
"""
import asyncio
from contextlib import contextmanager
from io import BytesIO
from typing import Optional, BinaryIO, Dict, Any, Iterator
from pathlib import Path
import os
import structlog
from datetime import timedelta
import mimetypes
import hashlib

from app.core.config import settings
from app.core.safe_errors import safe_error_log

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
    """MinIO configuration from central settings"""

    def __init__(self):
        # Verwende zentrale settings statt hardcoded Defaults
        self.ENDPOINT = settings.MINIO_ENDPOINT
        self.ACCESS_KEY = settings.MINIO_ACCESS_KEY
        self.SECRET_KEY = settings.MINIO_SECRET_KEY.get_secret_value() if settings.MINIO_SECRET_KEY else ""
        self.SECURE = settings.MINIO_SECURE

        # Buckets - aus zentraler settings (validiert durch Pydantic)
        self.DOCUMENTS_BUCKET = settings.MINIO_BUCKET_DOCUMENTS
        self.THUMBNAILS_BUCKET = settings.MINIO_BUCKET_THUMBNAILS
        # Fallback auf settings wenn vorhanden, sonst Default
        self.EXPORTS_BUCKET = getattr(settings, "MINIO_BUCKET_EXPORTS", None) or os.getenv("MINIO_EXPORTS_BUCKET", "exports")

        # Settings - zentralisiert für bessere Validierung
        self.PRESIGNED_URL_EXPIRY_HOURS = getattr(settings, "MINIO_PRESIGNED_EXPIRY_HOURS", None) or int(os.getenv("MINIO_PRESIGNED_EXPIRY", "24"))
        self.MAX_FILE_SIZE_MB = settings.MAX_UPLOAD_SIZE_MB


# ============================================================================
# STORAGE SERVICE
# ============================================================================

@contextmanager
def _create_bytes_buffer(data: bytes) -> Iterator[BytesIO]:
    """Create BytesIO with proper cleanup."""
    buffer = BytesIO(data)
    try:
        yield buffer
    finally:
        buffer.close()


class StorageService:
    """MinIO object storage manager with async support"""

    def __init__(self):
        self.config = StorageConfig()
        self.client: Optional[Minio] = None
        self.available = MINIO_AVAILABLE

        if self.available:
            try:
                self._initialize_client()
                self._ensure_buckets()
            except Exception as e:
                logger.error("minio_init_failed", **safe_error_log(e))
                self.available = False

    async def close(self) -> None:
        """Cleanup MinIO client resources."""
        if self.client:
            try:
                # MinIO Python client uses urllib3 internally
                # Close the connection pool if accessible
                if hasattr(self.client, '_http'):
                    self.client._http.clear()
                logger.info("minio_client_closed")
            except Exception as e:
                logger.warning("minio_close_error", **safe_error_log(e))
            finally:
                self.client = None
                self.available = False

    async def __aenter__(self) -> "StorageService":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit - cleanup resources."""
        await self.close()

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
            logger.error("minio_initialization_failed", **safe_error_log(e), exc_info=True)
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
                logger.error("bucket_creation_failed", bucket=bucket, **safe_error_log(e))

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

            # Upload to MinIO (async via thread to avoid blocking event loop)
            with _create_bytes_buffer(file_data) as buffer:
                await asyncio.to_thread(
                    self.client.put_object,
                    bucket_name=self.config.DOCUMENTS_BUCKET,
                    object_name=object_key,
                    data=buffer,
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
            logger.error("minio_upload_failed", **safe_error_log(e), exc_info=True)
            raise
        except Exception as e:
            logger.error("upload_failed", **safe_error_log(e), exc_info=True)
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

            # Upload to MinIO (async via thread to avoid blocking event loop)
            with _create_bytes_buffer(thumbnail_data) as buffer:
                await asyncio.to_thread(
                    self.client.put_object,
                    bucket_name=self.config.THUMBNAILS_BUCKET,
                    object_name=object_key,
                    data=buffer,
                    length=len(thumbnail_data),
                    content_type=f"image/{format}"
                )

            logger.info("thumbnail_uploaded", object_key=object_key)
            return object_key

        except Exception as e:
            logger.error("thumbnail_upload_failed", **safe_error_log(e), exc_info=True)
            raise

    # ========================================================================
    # DOWNLOAD OPERATIONS
    # ========================================================================

    async def download_document(self, object_key: str) -> bytes:
        """Download document from storage"""
        if not self.available:
            raise RuntimeError("MinIO not available")

        def _download():
            """Synchronous download helper for thread execution."""
            response = self.client.get_object(
                bucket_name=self.config.DOCUMENTS_BUCKET,
                object_name=object_key
            )
            try:
                data = response.read()
                return data
            finally:
                response.close()
                response.release_conn()

        try:
            # Download from MinIO (async via thread to avoid blocking event loop)
            data = await asyncio.to_thread(_download)

            logger.info("document_downloaded", object_key=object_key, size=len(data))
            return data

        except S3Error as e:
            logger.error("minio_download_failed", **safe_error_log(e), exc_info=True)
            raise
        except Exception as e:
            logger.error("download_failed", **safe_error_log(e), exc_info=True)
            raise

    async def stream_document(
        self,
        object_key: str,
        chunk_size: int = 1024 * 1024  # 1 MB default
    ):
        """
        Stream document from storage in chunks.

        Speichereffizient für große Dateien. Yields Chunks statt
        die gesamte Datei in den Speicher zu laden.

        Args:
            object_key: Pfad zum Objekt im Bucket
            chunk_size: Größe der Chunks in Bytes (default: 1 MB)

        Yields:
            bytes: Chunks der Datei

        Example:
            async for chunk in storage.stream_document("docs/file.pdf"):
                yield chunk
        """
        if not self.available:
            raise RuntimeError("MinIO not available")

        import queue
        import threading

        # Queue für Thread-Kommunikation
        chunk_queue: queue.Queue = queue.Queue(maxsize=5)
        error_container: list = []
        finished = threading.Event()

        def _stream_worker():
            """Worker-Thread für synchrones MinIO-Streaming."""
            response = None
            try:
                response = self.client.get_object(
                    bucket_name=self.config.DOCUMENTS_BUCKET,
                    object_name=object_key
                )

                # Chunks lesen und in Queue einfügen
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    chunk_queue.put(chunk)

            except Exception as e:
                error_container.append(e)
            finally:
                if response:
                    response.close()
                    response.release_conn()
                finished.set()
                # Sentinel für Ende
                chunk_queue.put(None)

        # Worker-Thread starten
        worker = threading.Thread(target=_stream_worker, daemon=True)
        worker.start()

        total_bytes = 0
        try:
            while True:
                # Chunk aus Queue holen (mit Timeout)
                try:
                    chunk = chunk_queue.get(timeout=30)
                except queue.Empty:
                    if finished.is_set():
                        break
                    continue

                if chunk is None:
                    break

                total_bytes += len(chunk)
                yield chunk

            # Prüfe auf Fehler im Worker-Thread
            if error_container:
                raise error_container[0]

            logger.info(
                "document_streamed",
                object_key=object_key,
                total_bytes=total_bytes
            )

        finally:
            # Sicherstellen dass Worker-Thread beendet wird
            finished.wait(timeout=5)

    async def get_document_info(self, object_key: str) -> Dict[str, Any]:
        """
        Holt Metadaten eines Dokuments ohne es herunterzuladen.

        Args:
            object_key: Pfad zum Objekt im Bucket

        Returns:
            Dict mit size, content_type, last_modified, etag
        """
        if not self.available:
            raise RuntimeError("MinIO not available")

        try:
            stat = await asyncio.to_thread(
                self.client.stat_object,
                bucket_name=self.config.DOCUMENTS_BUCKET,
                object_name=object_key
            )

            return {
                "size": stat.size,
                "content_type": stat.content_type,
                "last_modified": stat.last_modified,
                "etag": stat.etag,
            }
        except S3Error as e:
            logger.error("stat_object_failed", **safe_error_log(e), object_key=object_key)
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

            # Generate URL (async via thread to avoid blocking event loop)
            url = await asyncio.to_thread(
                self.client.presigned_get_object,
                bucket_name=self.config.DOCUMENTS_BUCKET,
                object_name=object_key,
                expires=expiry
            )

            logger.info("presigned_url_generated", object_key=object_key, expiry=str(expiry))
            return url

        except Exception as e:
            logger.error("presigned_url_generation_failed", **safe_error_log(e), exc_info=True)
            raise

    # ========================================================================
    # DELETE OPERATIONS
    # ========================================================================

    async def delete_document(self, object_key: str) -> bool:
        """Delete document from storage"""
        if not self.available:
            raise RuntimeError("MinIO not available")

        try:
            # Delete from MinIO (async via thread to avoid blocking event loop)
            await asyncio.to_thread(
                self.client.remove_object,
                bucket_name=self.config.DOCUMENTS_BUCKET,
                object_name=object_key
            )

            logger.info("document_deleted", object_key=object_key)
            return True

        except S3Error as e:
            logger.error("minio_delete_failed", **safe_error_log(e), exc_info=True)
            return False
        except Exception as e:
            logger.error("delete_failed", **safe_error_log(e), exc_info=True)
            return False

    async def delete_user_documents(self, user_id: str) -> int:
        """Delete all documents for a user (GDPR compliance)"""
        if not self.available:
            raise RuntimeError("MinIO not available")

        def _delete_all():
            """Synchronous batch delete helper for thread execution."""
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

            return deleted_count

        try:
            # Batch delete (async via thread to avoid blocking event loop)
            deleted_count = await asyncio.to_thread(_delete_all)

            logger.info("user_documents_deleted", user_id=user_id, count=deleted_count)
            return deleted_count

        except Exception as e:
            logger.error("batch_delete_failed", **safe_error_log(e), exc_info=True)
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

            # Try to list buckets (async via thread to avoid blocking event loop)
            buckets = await asyncio.to_thread(self.client.list_buckets)

            return {
                "status": "healthy",
                "endpoint": self.config.ENDPOINT,
                "buckets": len(buckets),
                "available_buckets": [b.name for b in buckets]
            }

        except Exception as e:
            logger.error("minio_health_check_failed", **safe_error_log(e), exc_info=True)
            return {
                "status": "unhealthy", **safe_error_log(e)}

    async def get_storage_stats(self) -> Dict[str, Any]:
        """Get storage usage statistics"""
        def _collect_stats():
            """Synchronous stats collection helper for thread execution."""
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
            stats["total_size_bytes"] = sum(
                b["size_bytes"] for b in stats.values() if isinstance(b, dict)
            )
            stats["total_count"] = sum(
                b["count"] for b in stats.values() if isinstance(b, dict)
            )

            return stats

        try:
            if not self.available:
                return {"error": "MinIO not available"}

            # Collect stats (async via thread to avoid blocking event loop)
            stats = await asyncio.to_thread(_collect_stats)

            return stats

        except Exception as e:
            logger.error("storage_stats_failed", **safe_error_log(e), exc_info=True)
            return {"error": safe_error_detail(e, "Vorgang")}

    # ========================================================================
    # OBJECT VERSIONING
    # ========================================================================

    async def enable_bucket_versioning(self, bucket_name: str = None) -> bool:
        """
        Aktiviert Versionierung für einen Bucket.

        MinIO speichert dann alle Versionen von Objekten statt sie zu überschreiben.

        Args:
            bucket_name: Bucket-Name (default: Documents-Bucket)

        Returns:
            True wenn erfolgreich

        Note:
            Versionierung kann aktiviert, aber nicht deaktiviert werden.
        """
        if not self.available:
            raise RuntimeError("MinIO not available")

        try:
            from minio.versioningconfig import VersioningConfig, ENABLED

            bucket = bucket_name or self.config.DOCUMENTS_BUCKET

            config = VersioningConfig(ENABLED)
            await asyncio.to_thread(
                self.client.set_bucket_versioning,
                bucket,
                config
            )

            logger.info(
                "bucket_versioning_enabled",
                bucket=bucket
            )
            return True

        except Exception as e:
            logger.error(
                "enable_versioning_failed",
                bucket=bucket_name,
                **safe_error_log(e)
            )
            raise

    async def get_bucket_versioning_status(self, bucket_name: str = None) -> Dict[str, Any]:
        """
        Prüft den Versionierungsstatus eines Buckets.

        Args:
            bucket_name: Bucket-Name (default: Documents-Bucket)

        Returns:
            Dict mit Versionierungsstatus
        """
        if not self.available:
            return {"enabled": False, "error": "MinIO not available"}

        try:
            bucket = bucket_name or self.config.DOCUMENTS_BUCKET

            config = await asyncio.to_thread(
                self.client.get_bucket_versioning,
                bucket
            )

            return {
                "bucket": bucket,
                "enabled": config.status == "Enabled" if config else False,
                "status": config.status if config else "Disabled"
            }

        except Exception as e:
            logger.error(
                "get_versioning_status_failed",
                bucket=bucket_name,
                **safe_error_log(e)
            )
            return {"enabled": False, **safe_error_log(e)}

    async def list_object_versions(
        self,
        object_key: str,
        bucket_name: str = None,
        max_versions: int = 50
    ) -> list:
        """
        Listet alle Versionen eines Objekts auf.

        Args:
            object_key: Objektpfad
            bucket_name: Bucket-Name (default: Documents-Bucket)
            max_versions: Maximale Anzahl (default: 50)

        Returns:
            Liste von Versionen mit Metadaten
        """
        if not self.available:
            raise RuntimeError("MinIO not available")

        def _list_versions():
            """Synchronous version listing helper."""
            bucket = bucket_name or self.config.DOCUMENTS_BUCKET
            versions = []

            # list_objects mit include_version=True gibt Versionen zurück
            objects = self.client.list_objects(
                bucket_name=bucket,
                prefix=object_key,
                include_version=True
            )

            for obj in objects:
                # Nur exakte Matches
                if obj.object_name == object_key:
                    versions.append({
                        "version_id": obj.version_id,
                        "object_key": obj.object_name,
                        "size_bytes": obj.size,
                        "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
                        "etag": obj.etag,
                        "is_latest": obj.is_latest if hasattr(obj, 'is_latest') else False,
                        "is_delete_marker": obj.is_delete_marker if hasattr(obj, 'is_delete_marker') else False
                    })

                    if len(versions) >= max_versions:
                        break

            return versions

        try:
            versions = await asyncio.to_thread(_list_versions)

            logger.debug(
                "object_versions_listed",
                object_key=object_key,
                version_count=len(versions)
            )

            return versions

        except Exception as e:
            logger.error(
                "list_versions_failed",
                object_key=object_key,
                **safe_error_log(e)
            )
            raise

    async def get_object_version(
        self,
        object_key: str,
        version_id: str,
        bucket_name: str = None
    ) -> bytes:
        """
        Lädt eine spezifische Version eines Objekts.

        Args:
            object_key: Objektpfad
            version_id: Version-ID
            bucket_name: Bucket-Name (default: Documents-Bucket)

        Returns:
            Dateiinhalt als bytes
        """
        if not self.available:
            raise RuntimeError("MinIO not available")

        def _download_version():
            """Synchronous versioned download helper."""
            bucket = bucket_name or self.config.DOCUMENTS_BUCKET

            response = self.client.get_object(
                bucket_name=bucket,
                object_name=object_key,
                version_id=version_id
            )

            try:
                data = response.read()
                return data
            finally:
                response.close()
                response.release_conn()

        try:
            data = await asyncio.to_thread(_download_version)

            logger.info(
                "object_version_downloaded",
                object_key=object_key,
                version_id=version_id,
                size=len(data)
            )

            return data

        except S3Error as e:
            logger.error(
                "download_version_failed",
                object_key=object_key,
                version_id=version_id,
                **safe_error_log(e)
            )
            raise

    async def delete_object_version(
        self,
        object_key: str,
        version_id: str,
        bucket_name: str = None
    ) -> bool:
        """
        Löscht eine spezifische Version eines Objekts.

        Args:
            object_key: Objektpfad
            version_id: Version-ID
            bucket_name: Bucket-Name (default: Documents-Bucket)

        Returns:
            True wenn erfolgreich
        """
        if not self.available:
            raise RuntimeError("MinIO not available")

        try:
            bucket = bucket_name or self.config.DOCUMENTS_BUCKET

            await asyncio.to_thread(
                self.client.remove_object,
                bucket,
                object_key,
                version_id=version_id
            )

            logger.info(
                "object_version_deleted",
                object_key=object_key,
                version_id=version_id
            )

            return True

        except S3Error as e:
            logger.error(
                "delete_version_failed",
                object_key=object_key,
                version_id=version_id,
                **safe_error_log(e)
            )
            raise

    async def restore_object_version(
        self,
        object_key: str,
        version_id: str,
        bucket_name: str = None
    ) -> Dict[str, Any]:
        """
        Stellt eine alte Version als aktuelle Version wieder her.

        Kopiert die angegebene Version als neue aktuelle Version.

        Args:
            object_key: Objektpfad
            version_id: Version-ID der wiederherzustellenden Version
            bucket_name: Bucket-Name (default: Documents-Bucket)

        Returns:
            Dict mit neuer Version-Info
        """
        if not self.available:
            raise RuntimeError("MinIO not available")

        def _restore_version():
            """Synchronous version restore helper."""
            from minio.commonconfig import CopySource

            bucket = bucket_name or self.config.DOCUMENTS_BUCKET

            # Kopiere die alte Version als neue aktuelle Version
            source = CopySource(
                bucket,
                object_key,
                version_id=version_id
            )

            result = self.client.copy_object(
                bucket,
                object_key,
                source
            )

            return {
                "new_version_id": result.version_id,
                "new_etag": result.etag,
                "restored_from_version": version_id
            }

        try:
            result = await asyncio.to_thread(_restore_version)

            logger.info(
                "object_version_restored",
                object_key=object_key,
                restored_from=version_id,
                new_version_id=result.get("new_version_id")
            )

            return result

        except S3Error as e:
            logger.error(
                "restore_version_failed",
                object_key=object_key,
                version_id=version_id,
                **safe_error_log(e)
            )
            raise


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


async def cleanup_storage_service() -> None:
    """Cleanup storage service on application shutdown."""
    global _storage_service
    if _storage_service:
        await _storage_service.close()
        _storage_service = None
        logger.info("storage_service_cleanup_complete")
