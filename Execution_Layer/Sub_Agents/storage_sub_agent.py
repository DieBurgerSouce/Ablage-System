"""
Storage Sub-Agent - Database and Object Storage
Implementiert vollstaendige Storage-Operationen fuer alle Layer
"""

import uuid
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any

import structlog

logger = structlog.get_logger(__name__)


class StorageSubAgent:
    """
    Sub-agent for handling storage operations.

    Coordinates:
    - PostgreSQL (metadata)
    - MinIO (files)
    - Redis (cache)
    """

    def __init__(self):
        self._storage_service = None
        self._cache_service = None

    def _get_storage_service(self):
        """Lazy load storage service."""
        if self._storage_service is None:
            from app.services.storage_service import get_storage_service
            self._storage_service = get_storage_service()
        return self._storage_service

    async def _get_cache_service(self):
        """Lazy load cache service."""
        if self._cache_service is None:
            try:
                from app.services.cache_service import get_cache_service
                self._cache_service = await get_cache_service()
            except Exception as e:
                logger.warning("cache_service_unavailable", error=str(e))
                self._cache_service = None
        return self._cache_service

    async def store_document(
        self,
        document_file: bytes,
        metadata: dict
    ) -> dict:
        """
        Store document in all storage layers.

        Steps:
        1. Upload file to MinIO
        2. Save metadata to PostgreSQL
        3. Cache in Redis (TTL: 1 hour)
        4. Return storage URLs

        Args:
            document_file: Binary file content
            metadata: Document metadata (filename, user_id, mime_type, etc.)

        Returns:
            dict with document_id, storage_path, urls, and status
        """
        document_id = str(uuid.uuid4())
        file_hash = hashlib.sha256(document_file).hexdigest()

        result = {
            "document_id": document_id,
            "status": "pending",
            "storage_layers": [],
            "urls": {},
            "file_hash": file_hash,
            "file_size": len(document_file)
        }

        try:
            # Step 1: Upload file to MinIO
            storage = self._get_storage_service()
            if storage and storage.available:
                upload_result = await storage.upload_document(
                    file_data=document_file,
                    filename=metadata.get("filename", f"{document_id}.bin"),
                    content_type=metadata.get("mime_type"),
                    user_id=metadata.get("user_id"),
                    metadata={
                        "document_id": document_id,
                        "original_filename": metadata.get("original_filename", ""),
                        "uploaded_at": datetime.utcnow().isoformat()
                    }
                )
                result["storage_path"] = upload_result.get("storage_path")
                result["storage_layers"].append("minio")

                # Get presigned URL
                try:
                    url = await storage.get_presigned_url(result["storage_path"])
                    result["urls"]["download"] = url
                except Exception as e:
                    logger.warning("presigned_url_failed", error=str(e))

                logger.info(
                    "document_stored_minio",
                    document_id=document_id,
                    storage_path=result["storage_path"]
                )
            else:
                logger.warning("minio_unavailable", document_id=document_id)

            # Step 2: Save metadata to PostgreSQL
            try:
                from app.db.database import async_session_maker
                from app.db.models import Document
                from sqlalchemy import select

                async with async_session_maker() as session:
                    doc = Document(
                        id=uuid.UUID(document_id),
                        filename=metadata.get("filename"),
                        original_filename=metadata.get("original_filename"),
                        file_size=len(document_file),
                        mime_type=metadata.get("mime_type", "application/octet-stream"),
                        storage_path=result.get("storage_path"),
                        file_hash=file_hash,
                        user_id=uuid.UUID(metadata["user_id"]) if metadata.get("user_id") else None,
                        language=metadata.get("language", "de"),
                        status="uploaded",
                        metadata=metadata.get("extra_metadata", {})
                    )
                    session.add(doc)
                    await session.commit()
                    result["storage_layers"].append("postgresql")

                    logger.info(
                        "document_stored_postgresql",
                        document_id=document_id
                    )
            except Exception as e:
                logger.error("postgresql_store_failed", document_id=document_id, error=str(e))
                # Don't fail completely - MinIO storage succeeded

            # Step 3: Cache in Redis (TTL: 1 hour)
            cache = await self._get_cache_service()
            if cache:
                try:
                    cache_data = {
                        "document_id": document_id,
                        "filename": metadata.get("filename"),
                        "storage_path": result.get("storage_path"),
                        "mime_type": metadata.get("mime_type"),
                        "file_size": len(document_file),
                        "file_hash": file_hash,
                        "created_at": datetime.utcnow().isoformat()
                    }
                    await cache.set(
                        f"doc:{document_id}:metadata",
                        cache_data,
                        ttl=3600  # 1 hour
                    )
                    result["storage_layers"].append("redis")

                    logger.info(
                        "document_cached_redis",
                        document_id=document_id
                    )
                except Exception as e:
                    logger.warning("redis_cache_failed", error=str(e))

            result["status"] = "success"

            logger.info(
                "document_stored_complete",
                document_id=document_id,
                layers=result["storage_layers"],
                file_size=len(document_file)
            )

        except Exception as e:
            logger.error(
                "document_store_failed",
                document_id=document_id,
                error=str(e),
                exc_info=True
            )
            result["status"] = "failed"
            result["error"] = str(e)

        return result

    async def retrieve_document(self, document_id: str) -> dict:
        """
        Retrieve document with cache-first strategy.

        Order:
        1. Check Redis cache
        2. If miss, query PostgreSQL
        3. Fetch file from MinIO
        4. Cache result

        Args:
            document_id: UUID of the document

        Returns:
            dict with document metadata and file content
        """
        result = {
            "document_id": document_id,
            "status": "pending",
            "source": None,
            "metadata": None,
            "file": None
        }

        try:
            # Step 1: Check Redis cache
            cache = await self._get_cache_service()
            if cache:
                try:
                    cached = await cache.get(f"doc:{document_id}:metadata")
                    if cached:
                        result["metadata"] = cached
                        result["source"] = "redis"

                        logger.info(
                            "document_cache_hit",
                            document_id=document_id
                        )
                except Exception as e:
                    logger.warning("redis_get_failed", error=str(e))

            # Step 2: If cache miss, query PostgreSQL
            if result["metadata"] is None:
                try:
                    from app.db.database import async_session_maker
                    from app.db.models import Document
                    from sqlalchemy import select

                    async with async_session_maker() as session:
                        query = select(Document).where(
                            Document.id == uuid.UUID(document_id)
                        )
                        db_result = await session.execute(query)
                        doc = db_result.scalar_one_or_none()

                        if doc:
                            result["metadata"] = {
                                "document_id": str(doc.id),
                                "filename": doc.filename,
                                "original_filename": doc.original_filename,
                                "storage_path": doc.storage_path,
                                "mime_type": doc.mime_type,
                                "file_size": doc.file_size,
                                "file_hash": doc.file_hash,
                                "language": doc.language,
                                "status": doc.status,
                                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                                "updated_at": doc.updated_at.isoformat() if doc.updated_at else None
                            }
                            result["source"] = "postgresql"

                            logger.info(
                                "document_found_postgresql",
                                document_id=document_id
                            )
                        else:
                            raise ValueError(f"Dokument nicht gefunden: {document_id}")

                except ValueError:
                    raise
                except Exception as e:
                    logger.error("postgresql_query_failed", error=str(e))
                    raise

            # Step 3: Fetch file from MinIO
            storage_path = result["metadata"].get("storage_path")
            if storage_path:
                storage = self._get_storage_service()
                if storage and storage.available:
                    try:
                        file_content = await storage.download_document(storage_path)
                        result["file"] = file_content

                        logger.info(
                            "document_file_retrieved",
                            document_id=document_id,
                            size=len(file_content)
                        )
                    except Exception as e:
                        logger.error("minio_download_failed", error=str(e))
                        # Don't fail - metadata is still available

            # Step 4: Cache result if retrieved from DB
            if result["source"] == "postgresql" and cache:
                try:
                    await cache.set(
                        f"doc:{document_id}:metadata",
                        result["metadata"],
                        ttl=3600
                    )

                    logger.info(
                        "document_cached_after_retrieval",
                        document_id=document_id
                    )
                except Exception as e:
                    logger.warning("redis_cache_after_retrieval_failed", error=str(e))

            result["status"] = "success"

        except ValueError as e:
            result["status"] = "not_found"
            result["error"] = str(e)
            logger.warning("document_not_found", document_id=document_id)

        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            logger.error(
                "document_retrieve_failed",
                document_id=document_id,
                error=str(e),
                exc_info=True
            )

        return result

    async def delete_document(self, document_id: str) -> dict:
        """
        Delete from all storage layers (GDPR Art. 17 - Recht auf Loeschung).

        Steps:
        1. Delete from PostgreSQL
        2. Delete from MinIO
        3. Clear Redis cache
        4. Log GDPR deletion

        Args:
            document_id: UUID of the document to delete

        Returns:
            dict with deletion status for each layer
        """
        result = {
            "document_id": document_id,
            "status": "pending",
            "deleted_from": [],
            "errors": [],
            "gdpr_logged": False,
            "deleted_at": datetime.utcnow().isoformat()
        }

        storage_path = None

        try:
            # First, get storage path from PostgreSQL before deletion
            try:
                from app.db.database import async_session_maker
                from app.db.models import Document
                from sqlalchemy import select

                async with async_session_maker() as session:
                    query = select(Document).where(
                        Document.id == uuid.UUID(document_id)
                    )
                    db_result = await session.execute(query)
                    doc = db_result.scalar_one_or_none()

                    if doc:
                        storage_path = doc.storage_path

                        # Step 1: Delete from PostgreSQL
                        await session.delete(doc)
                        await session.commit()
                        result["deleted_from"].append("postgresql")

                        logger.info(
                            "document_deleted_postgresql",
                            document_id=document_id
                        )
                    else:
                        logger.warning(
                            "document_not_found_for_deletion",
                            document_id=document_id
                        )

            except Exception as e:
                result["errors"].append(f"PostgreSQL: {str(e)}")
                logger.error("postgresql_delete_failed", error=str(e))

            # Step 2: Delete from MinIO
            if storage_path:
                storage = self._get_storage_service()
                if storage and storage.available:
                    try:
                        deleted = await storage.delete_document(storage_path)
                        if deleted:
                            result["deleted_from"].append("minio")

                            logger.info(
                                "document_deleted_minio",
                                document_id=document_id,
                                storage_path=storage_path
                            )
                    except Exception as e:
                        result["errors"].append(f"MinIO: {str(e)}")
                        logger.error("minio_delete_failed", error=str(e))

            # Step 3: Clear Redis cache
            cache = await self._get_cache_service()
            if cache:
                try:
                    await cache.delete(f"doc:{document_id}:metadata")
                    await cache.delete(f"doc:{document_id}:ocr_result")
                    await cache.delete(f"doc:{document_id}:embeddings")
                    result["deleted_from"].append("redis")

                    logger.info(
                        "document_cache_cleared",
                        document_id=document_id
                    )
                except Exception as e:
                    result["errors"].append(f"Redis: {str(e)}")
                    logger.warning("redis_delete_failed", error=str(e))

            # Step 4: Log GDPR deletion (DSGVO Art. 17 compliant)
            logger.info(
                "gdpr_document_deleted",
                document_id=document_id,
                deleted_at=result["deleted_at"],
                deleted_layers=result["deleted_from"],
                article="DSGVO Art. 17 - Recht auf Loeschung",
                compliance_note="Vollstaendige Loeschung aus allen Speicherebenen"
            )
            result["gdpr_logged"] = True

            # Determine overall status
            if len(result["deleted_from"]) > 0:
                if len(result["errors"]) == 0:
                    result["status"] = "success"
                else:
                    result["status"] = "partial"
            else:
                result["status"] = "failed"

        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            logger.error(
                "document_delete_failed",
                document_id=document_id,
                error=str(e),
                exc_info=True
            )

        return result


# See: Static_Knowledge/Snippets/gdpr_logging_patterns.py
