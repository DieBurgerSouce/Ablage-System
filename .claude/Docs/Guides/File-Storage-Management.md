FILE STORAGE & MANAGEMENT GUIDE - TEIL 1
Complete Guide to File Storage, Upload Handling & Cloud Integration

📋 TABLE OF CONTENTS

Introduction
Local File Storage
S3/MinIO Integration
File Upload Handling


🎯 INTRODUCTION
Why File Storage Management Matters
┌─────────────────────────────────────────────────────────┐
│              FILE STORAGE CHALLENGES                     │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  📈 Scale                                                │
│     - Millions of files                                 │
│     - Petabytes of data                                 │
│     - Global distribution                               │
│                                                         │
│  💰 Cost                                                 │
│     - Storage costs grow                                │
│     - Bandwidth costs                                   │
│     - Processing overhead                               │
│                                                         │
│  🔒 Security                                             │
│     - Malware/virus uploads                             │
│     - Unauthorized access                               │
│     - Data breaches                                     │
│                                                         │
│  ⚡ Performance                                          │
│     - Fast uploads/downloads                            │
│     - Image optimization                                │
│     - CDN distribution                                  │
│                                                         │
│  🧹 Maintenance                                          │
│     - Orphaned files                                    │
│     - Duplicate detection                               │
│     - Storage cleanup                                   │
│                                                         │
└─────────────────────────────────────────────────────────┘
Storage Architecture Overview
┌──────────────────────────────────────────────────────────────┐
│                  STORAGE ARCHITECTURE                         │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────┐                                            │
│  │   Client    │                                            │
│  └──────┬──────┘                                            │
│         │ Upload                                            │
│         ▼                                                   │
│  ┌─────────────┐      ┌──────────────┐                     │
│  │  FastAPI    │─────▶│   Validation │                     │
│  │  Endpoint   │      │   - Size      │                     │
│  └──────┬──────┘      │   - Type      │                     │
│         │             │   - Virus     │                     │
│         │             └──────────────┘                     │
│         ▼                                                   │
│  ┌─────────────┐      ┌──────────────┐                     │
│  │  Processing │─────▶│ Optimization  │                     │
│  │  Pipeline   │      │   - Resize    │                     │
│  └──────┬──────┘      │   - Compress  │                     │
│         │             │   - Convert   │                     │
│         │             └──────────────┘                     │
│         ▼                                                   │
│  ┌──────────────────────────────────────┐                  │
│  │         STORAGE LAYER                 │                  │
│  ├───────────────┬──────────────────────┤                  │
│  │  Local (Hot)  │  S3/MinIO (Warm)     │                  │
│  │  - Temp files │  - Permanent storage │                  │
│  │  - Cache      │  - Versioning        │                  │
│  │  - Fast access│  - Lifecycle rules   │                  │
│  └───────┬───────┴──────────┬───────────┘                  │
│          │                  │                              │
│          ▼                  ▼                              │
│  ┌─────────────┐    ┌─────────────┐                       │
│  │     CDN     │    │   Glacier   │                       │
│  │  (Delivery) │    │  (Archive)  │                       │
│  └─────────────┘    └─────────────┘                       │
│                                                              │
└──────────────────────────────────────────────────────────────┘
File Types & Use Cases
python# config/file_types.py

FILE_CATEGORIES = {
    "images": {
        "extensions": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"],
        "mime_types": [
            "image/jpeg",
            "image/png",
            "image/gif",
            "image/webp",
            "image/svg+xml"
        ],
        "max_size_mb": 10,
        "storage": "s3",
        "optimization": True,
        "cdn": True,
        "use_cases": [
            "User avatars",
            "Product photos",
            "Content images",
            "Thumbnails"
        ]
    },
    
    "documents": {
        "extensions": [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt"],
        "mime_types": [
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "text/plain"
        ],
        "max_size_mb": 50,
        "storage": "s3",
        "optimization": False,
        "cdn": False,
        "virus_scan": True,
        "use_cases": [
            "Invoices",
            "Contracts",
            "Reports",
            "Attachments"
        ]
    },
    
    "videos": {
        "extensions": [".mp4", ".avi", ".mov", ".wmv", ".flv"],
        "mime_types": [
            "video/mp4",
            "video/x-msvideo",
            "video/quicktime",
            "video/x-ms-wmv",
            "video/x-flv"
        ],
        "max_size_mb": 500,
        "storage": "s3",
        "optimization": True,  # Transcoding
        "cdn": True,
        "use_cases": [
            "Product videos",
            "Tutorials",
            "User uploads"
        ]
    },
    
    "archives": {
        "extensions": [".zip", ".tar", ".gz", ".rar"],
        "mime_types": [
            "application/zip",
            "application/x-tar",
            "application/gzip",
            "application/x-rar-compressed"
        ],
        "max_size_mb": 100,
        "storage": "s3",
        "virus_scan": True,
        "use_cases": [
            "Bulk uploads",
            "Backups",
            "Data exports"
        ]
    }
}

💾 LOCAL FILE STORAGE
1. Directory Structure
python# backend/core/storage/local.py

"""
Local File Storage Implementation

Handles local file system storage with:
- Organized directory structure
- Safe file naming
- Metadata tracking
- Cleanup management
"""

from pathlib import Path
from datetime import datetime
import hashlib
import mimetypes
from typing import Optional, BinaryIO
import os


class LocalFileStorage:
    """
    Local file storage handler
    
    Directory structure:
    /var/app/storage/
    ├── uploads/          # User uploads
    │   ├── 2024/
    │   │   ├── 01/       # Month
    │   │   │   ├── 15/   # Day
    │   │   │   │   ├── abc123_original.jpg
    │   │   │   │   └── abc123_thumbnail.jpg
    ├── temp/             # Temporary files
    ├── cache/            # Cached processed files
    └── quarantine/       # Suspicious files
    """
    
    def __init__(self, base_path: str = "/var/app/storage"):
        self.base_path = Path(base_path)
        self.uploads_path = self.base_path / "uploads"
        self.temp_path = self.base_path / "temp"
        self.cache_path = self.base_path / "cache"
        self.quarantine_path = self.base_path / "quarantine"
        
        # Create directories
        self._init_directories()
    
    def _init_directories(self):
        """Initialize directory structure"""
        for path in [
            self.uploads_path,
            self.temp_path,
            self.cache_path,
            self.quarantine_path
        ]:
            path.mkdir(parents=True, exist_ok=True)
    
    def generate_file_path(
        self,
        filename: str,
        category: str = "uploads",
        date: Optional[datetime] = None
    ) -> Path:
        """
        Generate organized file path
        
        Args:
            filename: Original filename
            category: Storage category (uploads, temp, cache)
            date: Date for organization (defaults to now)
        
        Returns:
            Full file path
        """
        if date is None:
            date = datetime.now()
        
        # Create date-based subdirectories
        year = date.strftime("%Y")
        month = date.strftime("%m")
        day = date.strftime("%d")
        
        # Base directory
        if category == "uploads":
            base = self.uploads_path
        elif category == "temp":
            base = self.temp_path
        elif category == "cache":
            base = self.cache_path
        else:
            base = self.quarantine_path
        
        # Create path
        directory = base / year / month / day
        directory.mkdir(parents=True, exist_ok=True)
        
        # Safe filename
        safe_name = self._sanitize_filename(filename)
        
        # Generate unique name if file exists
        file_path = directory / safe_name
        counter = 1
        while file_path.exists():
            name, ext = os.path.splitext(safe_name)
            file_path = directory / f"{name}_{counter}{ext}"
            counter += 1
        
        return file_path
    
    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize filename for safe storage
        
        - Remove dangerous characters
        - Limit length
        - Preserve extension
        """
        # Get extension
        name, ext = os.path.splitext(filename)
        
        # Remove dangerous characters
        safe_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
        safe_name = ''.join(c if c in safe_chars else '_' for c in name)
        
        # Limit length
        max_length = 200
        if len(safe_name) > max_length:
            safe_name = safe_name[:max_length]
        
        # Combine
        return f"{safe_name}{ext.lower()}"
    
    def save_file(
        self,
        file: BinaryIO,
        filename: str,
        category: str = "uploads",
        calculate_hash: bool = True
    ) -> dict:
        """
        Save file to local storage
        
        Args:
            file: File object
            filename: Original filename
            category: Storage category
            calculate_hash: Whether to calculate file hash
        
        Returns:
            File metadata
        """
        # Generate path
        file_path = self.generate_file_path(filename, category)
        
        # Calculate hash while writing
        hash_md5 = hashlib.md5() if calculate_hash else None
        hash_sha256 = hashlib.sha256() if calculate_hash else None
        
        size = 0
        
        # Write file
        with open(file_path, 'wb') as f:
            while chunk := file.read(8192):
                f.write(chunk)
                size += len(chunk)
                
                if calculate_hash:
                    hash_md5.update(chunk)
                    hash_sha256.update(chunk)
        
        # Get mime type
        mime_type, _ = mimetypes.guess_type(str(file_path))
        
        # Build metadata
        metadata = {
            "path": str(file_path),
            "filename": filename,
            "safe_filename": file_path.name,
            "size": size,
            "mime_type": mime_type,
            "created_at": datetime.now().isoformat(),
            "category": category
        }
        
        if calculate_hash:
            metadata["md5"] = hash_md5.hexdigest()
            metadata["sha256"] = hash_sha256.hexdigest()
        
        return metadata
    
    def read_file(self, file_path: str) -> BinaryIO:
        """Read file from storage"""
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        return open(path, 'rb')
    
    def delete_file(self, file_path: str) -> bool:
        """Delete file from storage"""
        path = Path(file_path)
        
        if path.exists():
            path.unlink()
            return True
        
        return False
    
    def move_file(self, source: str, destination: str) -> bool:
        """Move file to new location"""
        src_path = Path(source)
        dst_path = Path(destination)
        
        if not src_path.exists():
            raise FileNotFoundError(f"Source file not found: {source}")
        
        # Create destination directory
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Move file
        src_path.rename(dst_path)
        return True
    
    def get_storage_stats(self) -> dict:
        """Get storage statistics"""
        
        def get_size(path: Path) -> int:
            """Calculate directory size"""
            total = 0
            for item in path.rglob("*"):
                if item.is_file():
                    total += item.stat().st_size
            return total
        
        stats = {
            "uploads": {
                "size": get_size(self.uploads_path),
                "files": sum(1 for _ in self.uploads_path.rglob("*") if _.is_file())
            },
            "temp": {
                "size": get_size(self.temp_path),
                "files": sum(1 for _ in self.temp_path.rglob("*") if _.is_file())
            },
            "cache": {
                "size": get_size(self.cache_path),
                "files": sum(1 for _ in self.cache_path.rglob("*") if _.is_file())
            },
            "quarantine": {
                "size": get_size(self.quarantine_path),
                "files": sum(1 for _ in self.quarantine_path.rglob("*") if _.is_file())
            }
        }
        
        stats["total"] = {
            "size": sum(s["size"] for s in stats.values()),
            "files": sum(s["files"] for s in stats.values())
        }
        
        return stats


# Example usage
if __name__ == "__main__":
    storage = LocalFileStorage()
    
    # Save file
    with open("test.jpg", "rb") as f:
        metadata = storage.save_file(f, "test.jpg")
        print(f"File saved: {metadata}")
    
    # Get stats
    stats = storage.get_storage_stats()
    print(f"Storage stats: {stats}")
2. File Metadata Database
python# backend/models/file.py

"""
File metadata model for database tracking
"""

from sqlalchemy import Column, Integer, String, BigInteger, DateTime, Boolean, JSON
from sqlalchemy.sql import func
from database import Base


class File(Base):
    """File metadata model"""
    
    __tablename__ = "files"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # File identification
    uuid = Column(String(36), unique=True, index=True, nullable=False)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    
    # Storage
    storage_type = Column(String(20), nullable=False)  # local, s3, minio
    storage_path = Column(String(500), nullable=False)
    storage_bucket = Column(String(100))  # For S3/MinIO
    
    # File properties
    size = Column(BigInteger, nullable=False)
    mime_type = Column(String(100))
    extension = Column(String(10))
    
    # Checksums
    md5 = Column(String(32))
    sha256 = Column(String(64), index=True)
    
    # Ownership
    user_id = Column(Integer, index=True)
    category = Column(String(50), index=True)  # avatar, document, image, etc.
    
    # Status
    is_public = Column(Boolean, default=False)
    is_processed = Column(Boolean, default=False)
    is_quarantined = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)
    
    # Metadata
    metadata = Column(JSON)  # Extra metadata (image dimensions, video duration, etc.)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    accessed_at = Column(DateTime(timezone=True))
    deleted_at = Column(DateTime(timezone=True))
    
    # Relationships
    versions = Column(JSON)  # File versions (original, thumbnail, optimized)
    
    def __repr__(self):
        return f"<File {self.filename} ({self.size} bytes)>"
python# backend/repositories/file_repository.py

"""
File repository for database operations
"""

from sqlalchemy.orm import Session
from models.file import File
from typing import Optional, List
from datetime import datetime


class FileRepository:
    """Repository for file operations"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create(self, file_data: dict) -> File:
        """Create new file record"""
        file = File(**file_data)
        self.db.add(file)
        self.db.commit()
        self.db.refresh(file)
        return file
    
    def get_by_uuid(self, uuid: str) -> Optional[File]:
        """Get file by UUID"""
        return self.db.query(File).filter(
            File.uuid == uuid,
            File.is_deleted == False
        ).first()
    
    def get_by_sha256(self, sha256: str) -> Optional[File]:
        """Get file by SHA256 hash (deduplication)"""
        return self.db.query(File).filter(
            File.sha256 == sha256,
            File.is_deleted == False
        ).first()
    
    def get_by_user(
        self,
        user_id: int,
        category: Optional[str] = None,
        limit: int = 100
    ) -> List[File]:
        """Get files by user"""
        query = self.db.query(File).filter(
            File.user_id == user_id,
            File.is_deleted == False
        )
        
        if category:
            query = query.filter(File.category == category)
        
        return query.order_by(File.created_at.desc()).limit(limit).all()
    
    def update_accessed_at(self, file_id: int):
        """Update last access time"""
        self.db.query(File).filter(File.id == file_id).update({
            "accessed_at": datetime.now()
        })
        self.db.commit()
    
    def soft_delete(self, file_id: int):
        """Soft delete file"""
        self.db.query(File).filter(File.id == file_id).update({
            "is_deleted": True,
            "deleted_at": datetime.now()
        })
        self.db.commit()
    
    def get_orphaned_files(self, days: int = 7) -> List[File]:
        """Get files not accessed in X days"""
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=days)
        
        return self.db.query(File).filter(
            File.accessed_at < cutoff,
            File.is_deleted == False
        ).all()
    
    def get_storage_usage(self, user_id: Optional[int] = None) -> dict:
        """Get storage usage statistics"""
        from sqlalchemy import func
        
        query = self.db.query(
            func.sum(File.size).label("total_size"),
            func.count(File.id).label("total_files")
        ).filter(File.is_deleted == False)
        
        if user_id:
            query = query.filter(File.user_id == user_id)
        
        result = query.first()
        
        return {
            "total_size": result.total_size or 0,
            "total_files": result.total_files or 0
        }

☁️ S3/MINIO INTEGRATION
1. S3 Storage Implementation
python# backend/core/storage/s3.py

"""
S3/MinIO Storage Implementation

Supports both AWS S3 and MinIO (S3-compatible)
"""

import boto3
from botocore.exceptions import ClientError
from botocore.config import Config
from typing import Optional, BinaryIO
import io
from datetime import datetime, timedelta
from loguru import logger


class S3Storage:
    """
    S3/MinIO storage handler
    
    Features:
    - Upload/download files
    - Presigned URLs
    - Multipart uploads
    - Lifecycle management
    - Versioning
    """
    
    def __init__(
        self,
        bucket: str,
        aws_access_key_id: str,
        aws_secret_access_key: str,
        endpoint_url: Optional[str] = None,  # For MinIO
        region: str = "eu-central-1"
    ):
        self.bucket = bucket
        
        # Configure client
        config = Config(
            region_name=region,
            signature_version='s3v4',
            retries={
                'max_attempts': 3,
                'mode': 'standard'
            }
        )
        
        # Create client
        self.client = boto3.client(
            's3',
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            endpoint_url=endpoint_url,
            config=config
        )
        
        # Ensure bucket exists
        self._ensure_bucket_exists()
    
    def _ensure_bucket_exists(self):
        """Create bucket if it doesn't exist"""
        try:
            self.client.head_bucket(Bucket=self.bucket)
            logger.info(f"Bucket exists: {self.bucket}")
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                logger.info(f"Creating bucket: {self.bucket}")
                self.client.create_bucket(
                    Bucket=self.bucket,
                    CreateBucketConfiguration={
                        'LocationConstraint': self.client.meta.region_name
                    }
                )
            else:
                raise
    
    def upload_file(
        self,
        file: BinaryIO,
        key: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None,
        acl: str = 'private',
        storage_class: str = 'STANDARD'
    ) -> dict:
        """
        Upload file to S3
        
        Args:
            file: File object
            key: S3 key (path)
            content_type: MIME type
            metadata: Custom metadata
            acl: Access control (private, public-read)
            storage_class: Storage class (STANDARD, STANDARD_IA, GLACIER)
        
        Returns:
            Upload result
        """
        try:
            # Prepare extra args
            extra_args = {
                'ACL': acl,
                'StorageClass': storage_class
            }
            
            if content_type:
                extra_args['ContentType'] = content_type
            
            if metadata:
                extra_args['Metadata'] = metadata
            
            # Upload
            self.client.upload_fileobj(
                file,
                self.bucket,
                key,
                ExtraArgs=extra_args
            )
            
            logger.info(f"Uploaded file: s3://{self.bucket}/{key}")
            
            return {
                "bucket": self.bucket,
                "key": key,
                "url": f"s3://{self.bucket}/{key}",
                "storage_class": storage_class
            }
            
        except ClientError as e:
            logger.error(f"Failed to upload file: {e}")
            raise
    
    def download_file(self, key: str) -> bytes:
        """Download file from S3"""
        try:
            response = self.client.get_object(
                Bucket=self.bucket,
                Key=key
            )
            
            return response['Body'].read()
            
        except ClientError as e:
            logger.error(f"Failed to download file: {e}")
            raise
    
    def get_presigned_url(
        self,
        key: str,
        expiration: int = 3600,
        method: str = 'get_object'
    ) -> str:
        """
        Generate presigned URL for temporary access
        
        Args:
            key: S3 key
            expiration: URL expiration in seconds
            method: Operation (get_object, put_object)
        
        Returns:
            Presigned URL
        """
        try:
            url = self.client.generate_presigned_url(
                method,
                Params={
                    'Bucket': self.bucket,
                    'Key': key
                },
                ExpiresIn=expiration
            )
            
            return url
            
        except ClientError as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            raise
    
    def delete_file(self, key: str) -> bool:
        """Delete file from S3"""
        try:
            self.client.delete_object(
                Bucket=self.bucket,
                Key=key
            )
            
            logger.info(f"Deleted file: s3://{self.bucket}/{key}")
            return True
            
        except ClientError as e:
            logger.error(f"Failed to delete file: {e}")
            return False
    
    def copy_file(self, source_key: str, dest_key: str) -> bool:
        """Copy file within S3"""
        try:
            self.client.copy_object(
                Bucket=self.bucket,
                CopySource={'Bucket': self.bucket, 'Key': source_key},
                Key=dest_key
            )
            
            logger.info(f"Copied: {source_key} -> {dest_key}")
            return True
            
        except ClientError as e:
            logger.error(f"Failed to copy file: {e}")
            return False
    
    def list_files(
        self,
        prefix: str = "",
        max_keys: int = 1000
    ) -> list:
        """List files in bucket"""
        try:
            response = self.client.list_objects_v2(
                Bucket=self.bucket,
                Prefix=prefix,
                MaxKeys=max_keys
            )
            
            if 'Contents' not in response:
                return []
            
            return [
                {
                    'key': obj['Key'],
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'],
                    'storage_class': obj.get('StorageClass', 'STANDARD')
                }
                for obj in response['Contents']
            ]
            
        except ClientError as e:
            logger.error(f"Failed to list files: {e}")
            return []
    
    def get_file_metadata(self, key: str) -> dict:
        """Get file metadata"""
        try:
            response = self.client.head_object(
                Bucket=self.bucket,
                Key=key
            )
            
            return {
                'size': response['ContentLength'],
                'content_type': response.get('ContentType'),
                'last_modified': response['LastModified'],
                'metadata': response.get('Metadata', {}),
                'storage_class': response.get('StorageClass', 'STANDARD'),
                'etag': response['ETag'].strip('"')
            }
            
        except ClientError as e:
            logger.error(f"Failed to get metadata: {e}")
            raise
    
    def set_lifecycle_policy(self):
        """
        Set lifecycle policy for automatic archiving
        
        - Move to STANDARD_IA after 30 days
        - Move to GLACIER after 90 days
        - Delete after 365 days
        """
        try:
            lifecycle_config = {
                'Rules': [
                    {
                        'ID': 'Move to IA',
                        'Status': 'Enabled',
                        'Prefix': '',
                        'Transitions': [
                            {
                                'Days': 30,
                                'StorageClass': 'STANDARD_IA'
                            },
                            {
                                'Days': 90,
                                'StorageClass': 'GLACIER'
                            }
                        ],
                        'Expiration': {
                            'Days': 365
                        }
                    }
                ]
            }
            
            self.client.put_bucket_lifecycle_configuration(
                Bucket=self.bucket,
                LifecycleConfiguration=lifecycle_config
            )
            
            logger.info("Lifecycle policy set successfully")
            
        except ClientError as e:
            logger.error(f"Failed to set lifecycle policy: {e}")
            raise
    
    def enable_versioning(self):
        """Enable versioning on bucket"""
        try:
            self.client.put_bucket_versioning(
                Bucket=self.bucket,
                VersioningConfiguration={'Status': 'Enabled'}
            )
            
            logger.info("Versioning enabled")
            
        except ClientError as e:
            logger.error(f"Failed to enable versioning: {e}")
            raise


# Example usage
if __name__ == "__main__":
    # AWS S3
    s3 = S3Storage(
        bucket="my-app-uploads",
        aws_access_key_id="YOUR_KEY",
        aws_secret_access_key="YOUR_SECRET"
    )
    
    # MinIO (local S3-compatible)
    minio = S3Storage(
        bucket="my-app-uploads",
        aws_access_key_id="minioadmin",
        aws_secret_access_key="minioadmin",
        endpoint_url="http://localhost:9000"
    )
    
    # Upload file
    with open("test.jpg", "rb") as f:
        result = s3.upload_file(
            f,
            "uploads/2024/01/test.jpg",
            content_type="image/jpeg"
        )
        print(result)
    
    # Generate presigned URL
    url = s3.get_presigned_url("uploads/2024/01/test.jpg", expiration=3600)
    print(f"Download URL: {url}")
2. MinIO Docker Setup
yaml# docker-compose.yml - MinIO Service

version: '3.8'

services:
  minio:
    image: minio/minio:latest
    container_name: minio
    ports:
      - "9000:9000"      # API
      - "9001:9001"      # Console
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
      MINIO_DOMAIN: minio.local
    volumes:
      - minio_data:/data
    command: server /data --console-address ":9001"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 30s
      timeout: 20s
      retries: 3
    networks:
      - app_network
  
  # MinIO Client (for setup)
  minio_setup:
    image: minio/mc:latest
    depends_on:
      - minio
    entrypoint: >
      /bin/sh -c "
      sleep 5;
      mc alias set myminio http://minio:9000 minioadmin minioadmin;
      mc mb myminio/uploads --ignore-existing;
      mc mb myminio/backups --ignore-existing;
      mc anonymous set download myminio/uploads;
      echo 'MinIO setup complete';
      "
    networks:
      - app_network

volumes:
  minio_data:
    driver: local

networks:
  app_network:
    driver: bridge
3. Storage Factory Pattern
python# backend/core/storage/factory.py

"""
Storage Factory

Unified interface for different storage backends
"""

from typing import Union
from core.storage.local import LocalFileStorage
from core.storage.s3 import S3Storage
from config import settings


class StorageFactory:
    """Factory for creating storage instances"""
    
    @staticmethod
    def create(storage_type: str = None) -> Union[LocalFileStorage, S3Storage]:
        """
        Create storage instance
        
        Args:
            storage_type: Type of storage (local, s3, minio)
        
        Returns:
            Storage instance
        """
        if storage_type is None:
            storage_type = settings.DEFAULT_STORAGE
        
        if storage_type == "local":
            return LocalFileStorage(
                base_path=settings.LOCAL_STORAGE_PATH
            )
        
        elif storage_type == "s3":
            return S3Storage(
                bucket=settings.S3_BUCKET,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region=settings.AWS_REGION
            )
        
        elif storage_type == "minio":
            return S3Storage(
                bucket=settings.MINIO_BUCKET,
                aws_access_key_id=settings.MINIO_ACCESS_KEY,
                aws_secret_access_key=settings.MINIO_SECRET_KEY,
                endpoint_url=settings.MINIO_ENDPOINT
            )
        
        else:
            raise ValueError(f"Unknown storage type: {storage_type}")


# Usage
storage = StorageFactory.create("s3")

📤 FILE UPLOAD HANDLING
1. FastAPI Upload Endpoint
python# backend/api/endpoints/upload.py

"""
File Upload API Endpoints

Features:
- Single file upload
- Multiple file upload
- Chunked upload (large files)
- Progress tracking
- Validation
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import List, Optional
from sqlalchemy.orm import Session
import uuid
from datetime import datetime

from core.storage.factory import StorageFactory
from repositories.file_repository import FileRepository
from database import get_db
from auth import get_current_user
from utils.validators import validate_file
from loguru import logger


router = APIRouter(prefix="/api/files", tags=["files"])


# ============================================
# SINGLE FILE UPLOAD
# ============================================

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    category: str = "general",
    is_public: bool = False,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Upload single file
    
    - Validates file type and size
    - Scans for viruses (if enabled)
    - Stores locally and/or S3
    - Creates database record
    """
    
    try:
        # Validate file
        validation = validate_file(file, category)
        if not validation['valid']:
            raise HTTPException(
                status_code=400,
                detail=validation['error']
            )
        
        # Generate UUID
        file_uuid = str(uuid.uuid4())
        
        # Read file content
        content = await file.read()
        
        # Save to storage
        storage = StorageFactory.create()
        
        # Generate storage key
        now = datetime.now()
        storage_key = f"uploads/{now.year}/{now.month:02d}/{now.day:02d}/{file_uuid}_{file.filename}"
        
        # Upload
        from io import BytesIO
        result = storage.upload_file(
            BytesIO(content),
            storage_key,
            content_type=file.content_type
        )
        
        # Create database record
        file_repo = FileRepository(db)
        file_record = file_repo.create({
            "uuid": file_uuid,
            "filename": file.filename,
            "original_filename": file.filename,
            "storage_type": "s3",
            "storage_path": storage_key,
            "storage_bucket": result['bucket'],
            "size": len(content),
            "mime_type": file.content_type,
            "user_id": current_user.id,
            "category": category,
            "is_public": is_public
        })
        
        logger.info(
            f"File uploaded: {file.filename}",
            extra={
                "user_id": current_user.id,
                "file_uuid": file_uuid,
                "size": len(content)
            }
        )
        
        return {
            "uuid": file_uuid,
            "filename": file.filename,
            "size": len(content),
            "url": f"/api/files/{file_uuid}",
            "uploaded_at": file_record.created_at
        }
        
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# MULTIPLE FILE UPLOAD
# ============================================

@router.post("/upload/multiple")
async def upload_multiple_files(
    files: List[UploadFile] = File(...),
    category: str = "general",
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Upload multiple files
    
    - Processes files in parallel
    - Returns individual results
    """
    
    results = []
    errors = []
    
    for file in files:
        try:
            # Validate
            validation = validate_file(file, category)
            if not validation['valid']:
                errors.append({
                    "filename": file.filename,
                    "error": validation['error']
                })
                continue
            
            # Upload (reuse single upload logic)
            file_uuid = str(uuid.uuid4())
            content = await file.read()
            
            storage = StorageFactory.create()
            now = datetime.now()
            storage_key = f"uploads/{now.year}/{now.month:02d}/{now.day:02d}/{file_uuid}_{file.filename}"
            
            result = storage.upload_file(
                BytesIO(content),
                storage_key,
                content_type=file.content_type
            )
            
            # Database
            file_repo = FileRepository(db)
            file_record = file_repo.create({
                "uuid": file_uuid,
                "filename": file.filename,
                "original_filename": file.filename,
                "storage_type": "s3",
                "storage_path": storage_key,
                "storage_bucket": result['bucket'],
                "size": len(content),
                "mime_type": file.content_type,
                "user_id": current_user.id,
                "category": category
            })
            
            results.append({
                "uuid": file_uuid,
                "filename": file.filename,
                "size": len(content),
                "status": "success"
            })
            
        except Exception as e:
            errors.append({
                "filename": file.filename,
                "error": str(e)
            })
    
    return {
        "uploaded": len(results),
        "failed": len(errors),
        "results": results,
        "errors": errors
    }


# ============================================
# CHUNKED UPLOAD (LARGE FILES)
# ============================================

@router.post("/upload/chunked/init")
async def init_chunked_upload(
    filename: str,
    total_size: int,
    category: str = "general",
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Initialize chunked upload for large files
    
    Returns upload ID for subsequent chunks
    """
    
    # Validate size
    max_size = 5 * 1024 * 1024 * 1024  # 5 GB
    if total_size > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Max size: {max_size} bytes"
        )
    
    # Generate upload ID
    upload_id = str(uuid.uuid4())
    
    # Store upload metadata in cache/database
    # (Implementation depends on your caching solution)
    
    logger.info(
        f"Chunked upload initialized: {filename}",
        extra={
            "upload_id": upload_id,
            "total_size": total_size,
            "user_id": current_user.id
        }
    )
    
    return {
        "upload_id": upload_id,
        "chunk_size": 5 * 1024 * 1024,  # 5 MB chunks
        "total_chunks": (total_size + 5 * 1024 * 1024 - 1) // (5 * 1024 * 1024)
    }


@router.post("/upload/chunked/{upload_id}/chunk/{chunk_number}")
async def upload_chunk(
    upload_id: str,
    chunk_number: int,
    chunk: UploadFile = File(...),
    current_user = Depends(get_current_user)
):
    """
    Upload single chunk
    
    - Stores chunk temporarily
    - Tracks progress
    """
    
    try:
        # Read chunk
        content = await chunk.read()
        
        # Store chunk temporarily
        # (Save to temp storage)
        
        logger.info(
            f"Chunk uploaded: {upload_id}",
            extra={
                "chunk_number": chunk_number,
                "size": len(content)
            }
        )
        
        return {
            "upload_id": upload_id,
            "chunk_number": chunk_number,
            "status": "received"
        }
        
    except Exception as e:
        logger.error(f"Chunk upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload/chunked/{upload_id}/complete")
async def complete_chunked_upload(
    upload_id: str,
    filename: str,
    category: str = "general",
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None,
    current_user = Depends(get_current_user)
):
    """
    Complete chunked upload
    
    - Combines chunks
    - Creates final file
    - Cleans up temp chunks
    """
    
    try:
        # Combine chunks
        # (Implementation depends on temp storage)
        
        # Save to permanent storage
        storage = StorageFactory.create()
        
        # ... (combine and upload logic)
        
        # Clean up temp chunks in background
        if background_tasks:
            background_tasks.add_task(cleanup_chunks, upload_id)
        
        return {
            "upload_id": upload_id,
            "status": "completed",
            "filename": filename
        }
        
    except Exception as e:
        logger.error(f"Failed to complete upload: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# FILE DOWNLOAD
# ============================================

@router.get("/{file_uuid}")
async def download_file(
    file_uuid: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Download file
    
    - Checks permissions
    - Generates presigned URL for S3
    - Or streams local file
    """
    
    # Get file record
    file_repo = FileRepository(db)
    file_record = file_repo.get_by_uuid(file_uuid)
    
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Check permissions
    if not file_record.is_public and file_record.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update access time
    file_repo.update_accessed_at(file_record.id)
    
    # Generate download URL
    if file_record.storage_type in ["s3", "minio"]:
        storage = StorageFactory.create(file_record.storage_type)
        url = storage.get_presigned_url(
            file_record.storage_path,
            expiration=3600
        )
        
        return {
            "url": url,
            "filename": file_record.filename,
            "size": file_record.size,
            "expires_in": 3600
        }
    
    else:
        # Stream local file
        from fastapi.responses import FileResponse
        return FileResponse(
            file_record.storage_path,
            filename=file_record.filename,
            media_type=file_record.mime_type
        )


# Helper functions

def cleanup_chunks(upload_id: str):
    """Background task to cleanup temp chunks"""
    logger.info(f"Cleaning up chunks: {upload_id}")
    # ... cleanup logic
2. File Validation
python# backend/utils/validators.py

"""
File validation utilities
"""

from typing import Dict
from fastapi import UploadFile
import magic
from config.file_types import FILE_CATEGORIES


def validate_file(file: UploadFile, category: str) -> Dict[str, any]:
    """
    Validate uploaded file
    
    Checks:
    - File type (extension and MIME)
    - File size
    - Content validation
    
    Args:
        file: Uploaded file
        category: File category (images, documents, etc.)
    
    Returns:
        Validation result
    """
    
    # Get category config
    if category not in FILE_CATEGORIES:
        return {
            "valid": False,
            "error": f"Unknown category: {category}"
        }
    
    config = FILE_CATEGORIES[category]
    
    # Check extension
    filename_lower = file.filename.lower()
    extension = None
    for ext in config['extensions']:
        if filename_lower.endswith(ext):
            extension = ext
            break
    
    if not extension:
        return {
            "valid": False,
            "error": f"Invalid file type. Allowed: {', '.join(config['extensions'])}"
        }
    
    # Check MIME type
    if file.content_type not in config['mime_types']:
        return {
            "valid": False,
            "error": f"Invalid MIME type: {file.content_type}"
        }
    
    # Check size
    # Note: FastAPI doesn't provide file size directly
    # You need to read the file to check size
    # For production, implement size check during upload
    
    return {
        "valid": True,
        "extension": extension,
        "mime_type": file.content_type
    }


def validate_file_content(content: bytes, expected_type: str) -> bool:
    """
    Validate file content using magic numbers
    
    Args:
        content: File content
        expected_type: Expected MIME type
    
    Returns:
        True if content matches expected type
    """
    
    # Use python-magic to detect actual file type
    mime = magic.Magic(mime=True)
    actual_type = mime.from_buffer(content)
    
    # Compare
    if actual_type != expected_type:
        return False
    
    return True


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename
    
    - Remove dangerous characters
    - Limit length
    - Preserve extension
    """
    import re
    import os
    
    # Get extension
    name, ext = os.path.splitext(filename)
    
    # Remove dangerous characters
    name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    
    # Limit length
    max_length = 200
    if len(name) > max_length:
        name = name[:max_length]
    
    # Combine
    return f"{name}{ext.lower()}"


FILE STORAGE & MANAGEMENT GUIDE - TEIL 2
Image Optimization, CDN, Security & Cleanup

📋 TABLE OF CONTENTS (TEIL 2)

Image Optimization
CDN Integration
Virus Scanning
Storage Quotas
File Cleanup Strategies


🖼️ IMAGE OPTIMIZATION
1. Image Processing with Pillow
python# backend/services/image_processor.py

"""
Image Processing Service

Features:
- Resize images
- Generate thumbnails
- Convert formats
- Optimize file size
- Add watermarks
- Extract metadata
"""

from PIL import Image, ImageOps, ImageDraw, ImageFont
from PIL.ExifTags import TAGS
import io
from typing import Tuple, Optional, Dict
from pathlib import Path
from loguru import logger


class ImageProcessor:
    """
    Image processing service
    
    Handles all image manipulation tasks
    """
    
    # Supported formats
    SUPPORTED_FORMATS = {
        'JPEG': {'quality': 85, 'optimize': True},
        'PNG': {'optimize': True},
        'WEBP': {'quality': 85, 'method': 6},
        'GIF': {},
    }
    
    # Thumbnail sizes
    THUMBNAIL_SIZES = {
        'small': (150, 150),
        'medium': (300, 300),
        'large': (600, 600),
        'xlarge': (1200, 1200)
    }
    
    def __init__(self, max_dimension: int = 4096):
        """
        Initialize image processor
        
        Args:
            max_dimension: Maximum allowed dimension (width or height)
        """
        self.max_dimension = max_dimension
    
    def open_image(self, image_data: bytes) -> Image.Image:
        """
        Open image from bytes
        
        Args:
            image_data: Image bytes
        
        Returns:
            PIL Image object
        """
        try:
            img = Image.open(io.BytesIO(image_data))
            
            # Handle EXIF orientation
            img = ImageOps.exif_transpose(img)
            
            return img
            
        except Exception as e:
            logger.error(f"Failed to open image: {e}")
            raise ValueError("Invalid image format")
    
    def resize_image(
        self,
        image: Image.Image,
        size: Tuple[int, int],
        maintain_aspect_ratio: bool = True,
        upscale: bool = False
    ) -> Image.Image:
        """
        Resize image
        
        Args:
            image: PIL Image
            size: Target size (width, height)
            maintain_aspect_ratio: Keep aspect ratio
            upscale: Allow upscaling (default: False)
        
        Returns:
            Resized image
        """
        
        # Don't upscale unless explicitly allowed
        if not upscale:
            if image.width <= size[0] and image.height <= size[1]:
                return image
        
        if maintain_aspect_ratio:
            # Calculate aspect ratio
            image.thumbnail(size, Image.Resampling.LANCZOS)
            return image
        else:
            # Force exact size (may distort)
            return image.resize(size, Image.Resampling.LANCZOS)
    
    def generate_thumbnail(
        self,
        image_data: bytes,
        size: str = 'medium',
        custom_size: Optional[Tuple[int, int]] = None
    ) -> bytes:
        """
        Generate thumbnail
        
        Args:
            image_data: Original image bytes
            size: Predefined size (small, medium, large, xlarge)
            custom_size: Custom size (width, height)
        
        Returns:
            Thumbnail image bytes
        """
        
        # Open image
        img = self.open_image(image_data)
        
        # Determine size
        if custom_size:
            target_size = custom_size
        else:
            target_size = self.THUMBNAIL_SIZES.get(size, self.THUMBNAIL_SIZES['medium'])
        
        # Resize
        img = self.resize_image(img, target_size, maintain_aspect_ratio=True)
        
        # Convert to RGB if necessary (for JPEG)
        if img.mode in ('RGBA', 'LA', 'P'):
            # Create white background
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        
        # Save to bytes
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=85, optimize=True)
        return output.getvalue()
    
    def convert_format(
        self,
        image_data: bytes,
        target_format: str = 'WEBP',
        quality: int = 85
    ) -> bytes:
        """
        Convert image to different format
        
        Args:
            image_data: Original image bytes
            target_format: Target format (JPEG, PNG, WEBP)
            quality: Quality (1-100, for lossy formats)
        
        Returns:
            Converted image bytes
        """
        
        # Open image
        img = self.open_image(image_data)
        
        # Validate format
        if target_format.upper() not in self.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported format: {target_format}")
        
        # Get format settings
        format_settings = self.SUPPORTED_FORMATS[target_format.upper()].copy()
        if 'quality' in format_settings:
            format_settings['quality'] = quality
        
        # Convert RGB if needed
        if target_format.upper() == 'JPEG' and img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        
        # Save
        output = io.BytesIO()
        img.save(output, format=target_format.upper(), **format_settings)
        return output.getvalue()
    
    def optimize_image(
        self,
        image_data: bytes,
        max_size_kb: Optional[int] = None,
        target_format: str = 'WEBP'
    ) -> bytes:
        """
        Optimize image for web
        
        - Converts to WebP for best compression
        - Resizes if too large
        - Reduces quality if file size exceeds limit
        
        Args:
            image_data: Original image bytes
            max_size_kb: Maximum file size in KB
            target_format: Target format
        
        Returns:
            Optimized image bytes
        """
        
        # Open image
        img = self.open_image(image_data)
        
        # Resize if too large
        if img.width > self.max_dimension or img.height > self.max_dimension:
            max_size = (self.max_dimension, self.max_dimension)
            img = self.resize_image(img, max_size, maintain_aspect_ratio=True)
        
        # Convert to target format
        quality = 85
        optimized = self.convert_format(
            self._image_to_bytes(img),
            target_format,
            quality
        )
        
        # Reduce quality if size limit specified
        if max_size_kb:
            max_bytes = max_size_kb * 1024
            
            while len(optimized) > max_bytes and quality > 20:
                quality -= 5
                optimized = self.convert_format(
                    self._image_to_bytes(img),
                    target_format,
                    quality
                )
        
        logger.info(
            f"Image optimized",
            extra={
                "original_size": len(image_data),
                "optimized_size": len(optimized),
                "reduction": f"{(1 - len(optimized)/len(image_data)) * 100:.1f}%",
                "format": target_format,
                "quality": quality
            }
        )
        
        return optimized
    
    def add_watermark(
        self,
        image_data: bytes,
        watermark_text: str,
        position: str = 'bottom-right',
        opacity: int = 128
    ) -> bytes:
        """
        Add text watermark to image
        
        Args:
            image_data: Original image bytes
            watermark_text: Text to add
            position: Position (bottom-right, bottom-left, center, etc.)
            opacity: Opacity (0-255)
        
        Returns:
            Watermarked image bytes
        """
        
        # Open image
        img = self.open_image(image_data)
        
        # Convert to RGBA if needed
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        
        # Create watermark layer
        watermark = Image.new('RGBA', img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(watermark)
        
        # Load font
        try:
            # Try to use a nice font
            font_size = max(20, img.width // 40)
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
        except:
            # Fallback to default
            font = ImageFont.load_default()
        
        # Get text size
        bbox = draw.textbbox((0, 0), watermark_text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        # Calculate position
        margin = 10
        if position == 'bottom-right':
            x = img.width - text_width - margin
            y = img.height - text_height - margin
        elif position == 'bottom-left':
            x = margin
            y = img.height - text_height - margin
        elif position == 'top-right':
            x = img.width - text_width - margin
            y = margin
        elif position == 'top-left':
            x = margin
            y = margin
        else:  # center
            x = (img.width - text_width) // 2
            y = (img.height - text_height) // 2
        
        # Draw text
        draw.text((x, y), watermark_text, font=font, fill=(255, 255, 255, opacity))
        
        # Composite
        watermarked = Image.alpha_composite(img, watermark)
        
        # Convert back to RGB
        if watermarked.mode == 'RGBA':
            background = Image.new('RGB', watermarked.size, (255, 255, 255))
            background.paste(watermarked, mask=watermarked.split()[-1])
            watermarked = background
        
        return self._image_to_bytes(watermarked)
    
    def extract_metadata(self, image_data: bytes) -> Dict:
        """
        Extract image metadata
        
        Args:
            image_data: Image bytes
        
        Returns:
            Metadata dictionary
        """
        
        img = self.open_image(image_data)
        
        metadata = {
            'format': img.format,
            'mode': img.mode,
            'width': img.width,
            'height': img.height,
            'aspect_ratio': round(img.width / img.height, 2),
            'size_bytes': len(image_data)
        }
        
        # Extract EXIF data
        exif = img.getexif()
        if exif:
            exif_data = {}
            for tag_id, value in exif.items():
                tag = TAGS.get(tag_id, tag_id)
                exif_data[tag] = str(value)
            
            metadata['exif'] = exif_data
        
        return metadata
    
    def create_image_variants(
        self,
        image_data: bytes
    ) -> Dict[str, bytes]:
        """
        Create multiple image variants
        
        - Original (optimized)
        - Thumbnails (small, medium, large)
        - WebP version
        
        Args:
            image_data: Original image bytes
        
        Returns:
            Dictionary of variants
        """
        
        variants = {}
        
        # Optimized original
        variants['original'] = self.optimize_image(image_data, target_format='WEBP')
        
        # Thumbnails
        for size_name in ['small', 'medium', 'large']:
            variants[f'thumbnail_{size_name}'] = self.generate_thumbnail(
                image_data,
                size=size_name
            )
        
        # WebP version
        variants['webp'] = self.convert_format(image_data, 'WEBP', quality=85)
        
        # JPEG version (for compatibility)
        variants['jpeg'] = self.convert_format(image_data, 'JPEG', quality=85)
        
        return variants
    
    def _image_to_bytes(self, img: Image.Image, format: str = 'JPEG') -> bytes:
        """Convert PIL Image to bytes"""
        output = io.BytesIO()
        
        # Ensure RGB for JPEG
        if format == 'JPEG' and img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        
        img.save(output, format=format, quality=85, optimize=True)
        return output.getvalue()


# Example usage
if __name__ == "__main__":
    processor = ImageProcessor()
    
    # Load image
    with open("test.jpg", "rb") as f:
        image_data = f.read()
    
    # Generate thumbnail
    thumbnail = processor.generate_thumbnail(image_data, size='medium')
    with open("thumbnail.jpg", "wb") as f:
        f.write(thumbnail)
    
    # Optimize
    optimized = processor.optimize_image(image_data, max_size_kb=200)
    with open("optimized.webp", "wb") as f:
        f.write(optimized)
    
    # Extract metadata
    metadata = processor.extract_metadata(image_data)
    print(f"Metadata: {metadata}")
    
    # Create variants
    variants = processor.create_image_variants(image_data)
    print(f"Created {len(variants)} variants")
2. Background Image Processing
python# backend/services/image_processing_worker.py

"""
Background Image Processing Worker

Uses Celery/RQ for async processing
"""

from celery import Celery
from services.image_processor import ImageProcessor
from core.storage.factory import StorageFactory
from repositories.file_repository import FileRepository
from database import SessionLocal
from loguru import logger


# Initialize Celery
celery_app = Celery(
    'image_processing',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/0'
)


@celery_app.task(name='process_uploaded_image')
def process_uploaded_image(file_uuid: str):
    """
    Background task to process uploaded image
    
    - Generates thumbnails
    - Creates optimized versions
    - Updates database
    
    Args:
        file_uuid: File UUID
    """
    
    logger.info(f"Processing image: {file_uuid}")
    
    db = SessionLocal()
    
    try:
        # Get file record
        file_repo = FileRepository(db)
        file_record = file_repo.get_by_uuid(file_uuid)
        
        if not file_record:
            logger.error(f"File not found: {file_uuid}")
            return
        
        # Download original
        storage = StorageFactory.create(file_record.storage_type)
        image_data = storage.download_file(file_record.storage_path)
        
        # Process image
        processor = ImageProcessor()
        variants = processor.create_image_variants(image_data)
        
        # Upload variants
        variant_paths = {}
        
        for variant_name, variant_data in variants.items():
            # Generate storage key
            base_key = file_record.storage_path.rsplit('.', 1)[0]
            variant_key = f"{base_key}_{variant_name}.webp"
            
            # Upload
            from io import BytesIO
            storage.upload_file(
                BytesIO(variant_data),
                variant_key,
                content_type='image/webp'
            )
            
            variant_paths[variant_name] = variant_key
        
        # Extract metadata
        metadata = processor.extract_metadata(image_data)
        
        # Update database
        file_record.metadata = {
            **metadata,
            'variants': variant_paths
        }
        file_record.is_processed = True
        
        db.commit()
        
        logger.info(
            f"Image processed successfully: {file_uuid}",
            extra={
                "variants": len(variants),
                "metadata": metadata
            }
        )
        
    except Exception as e:
        logger.error(f"Image processing failed: {e}")
        db.rollback()
        raise
        
    finally:
        db.close()


@celery_app.task(name='cleanup_temp_images')
def cleanup_temp_images():
    """
    Cleanup temporary image files
    
    Runs periodically to remove old temp files
    """
    
    logger.info("Cleaning up temp images")
    
    # Implementation depends on your temp storage
    # Delete files older than 24 hours
    
    pass
3. Image Upload with Processing
python# backend/api/endpoints/images.py

"""
Image Upload API with Processing
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
import uuid
from datetime import datetime

from services.image_processor import ImageProcessor
from services.image_processing_worker import process_uploaded_image
from core.storage.factory import StorageFactory
from repositories.file_repository import FileRepository
from database import get_db
from auth import get_current_user
from loguru import logger


router = APIRouter(prefix="/api/images", tags=["images"])


@router.post("/upload")
async def upload_image(
    file: UploadFile = File(...),
    generate_thumbnails: bool = True,
    optimize: bool = True,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Upload image with processing
    
    - Validates image
    - Optionally generates thumbnails
    - Optionally optimizes
    - Processes in background
    """
    
    try:
        # Validate image
        if not file.content_type.startswith('image/'):
            raise HTTPException(
                status_code=400,
                detail="File must be an image"
            )
        
        # Read image
        image_data = await file.read()
        
        # Validate with PIL
        processor = ImageProcessor()
        try:
            img = processor.open_image(image_data)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        
        # Generate UUID
        file_uuid = str(uuid.uuid4())
        
        # Optimize if requested (sync for quick preview)
        if optimize:
            image_data = processor.optimize_image(image_data, max_size_kb=500)
        
        # Upload to storage
        storage = StorageFactory.create()
        now = datetime.now()
        storage_key = f"images/{now.year}/{now.month:02d}/{now.day:02d}/{file_uuid}.webp"
        
        from io import BytesIO
        result = storage.upload_file(
            BytesIO(image_data),
            storage_key,
            content_type='image/webp'
        )
        
        # Extract basic metadata
        metadata = processor.extract_metadata(image_data)
        
        # Create database record
        file_repo = FileRepository(db)
        file_record = file_repo.create({
            "uuid": file_uuid,
            "filename": file.filename,
            "original_filename": file.filename,
            "storage_type": "s3",
            "storage_path": storage_key,
            "storage_bucket": result['bucket'],
            "size": len(image_data),
            "mime_type": "image/webp",
            "user_id": current_user.id,
            "category": "image",
            "metadata": metadata,
            "is_processed": not generate_thumbnails  # Not fully processed if thumbnails needed
        })
        
        # Schedule background processing
        if generate_thumbnails and background_tasks:
            background_tasks.add_task(
                process_uploaded_image.delay,
                file_uuid
            )
        
        logger.info(
            f"Image uploaded: {file.filename}",
            extra={
                "user_id": current_user.id,
                "file_uuid": file_uuid,
                "size": len(image_data),
                "dimensions": f"{metadata['width']}x{metadata['height']}"
            }
        )
        
        return {
            "uuid": file_uuid,
            "filename": file.filename,
            "size": len(image_data),
            "width": metadata['width'],
            "height": metadata['height'],
            "url": f"/api/images/{file_uuid}",
            "processing": generate_thumbnails,
            "uploaded_at": file_record.created_at
        }
        
    except Exception as e:
        logger.error(f"Image upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{file_uuid}/variants")
async def get_image_variants(
    file_uuid: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get all variants of an image
    
    Returns URLs for:
    - Original
    - Thumbnails
    - Different formats
    """
    
    # Get file record
    file_repo = FileRepository(db)
    file_record = file_repo.get_by_uuid(file_uuid)
    
    if not file_record:
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Check permissions
    if file_record.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get variants from metadata
    variants = file_record.metadata.get('variants', {})
    
    # Generate presigned URLs
    storage = StorageFactory.create(file_record.storage_type)
    
    variant_urls = {}
    for variant_name, variant_path in variants.items():
        url = storage.get_presigned_url(variant_path, expiration=3600)
        variant_urls[variant_name] = url
    
    return {
        "uuid": file_uuid,
        "original": storage.get_presigned_url(file_record.storage_path, expiration=3600),
        "variants": variant_urls,
        "processed": file_record.is_processed
    }

🌐 CDN INTEGRATION
1. CloudFront Configuration
python# backend/services/cdn.py

"""
CDN Service for Content Delivery

Supports:
- AWS CloudFront
- Cloudflare
- Custom CDN
"""

import boto3
from typing import Optional, Dict
from datetime import datetime, timedelta
from loguru import logger


class CloudFrontCDN:
    """
    AWS CloudFront CDN integration
    
    Features:
    - Presigned URLs with custom policies
    - Cache invalidation
    - Distribution management
    """
    
    def __init__(
        self,
        distribution_id: str,
        domain_name: str,
        key_pair_id: str,
        private_key_path: str
    ):
        """
        Initialize CloudFront CDN
        
        Args:
            distribution_id: CloudFront distribution ID
            domain_name: CDN domain name
            key_pair_id: CloudFront key pair ID
            private_key_path: Path to private key file
        """
        self.distribution_id = distribution_id
        self.domain_name = domain_name
        self.key_pair_id = key_pair_id
        
        # Load private key
        with open(private_key_path, 'rb') as f:
            self.private_key = f.read()
        
        # CloudFront client
        self.client = boto3.client('cloudfront')
    
    def get_signed_url(
        self,
        key: str,
        expiration: int = 3600
    ) -> str:
        """
        Generate signed CloudFront URL
        
        Args:
            key: Object key
            expiration: URL expiration in seconds
        
        Returns:
            Signed URL
        """
        
        from botocore.signers import CloudFrontSigner
        
        def rsa_signer(message):
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import padding
            from cryptography.hazmat.primitives.serialization import load_pem_private_key
            from cryptography.hazmat.backends import default_backend
            
            private_key = load_pem_private_key(
                self.private_key,
                password=None,
                backend=default_backend()
            )
            
            return private_key.sign(message, padding.PKCS1v15(), hashes.SHA1())
        
        cloudfront_signer = CloudFrontSigner(self.key_pair_id, rsa_signer)
        
        # Generate URL
        url = f"https://{self.domain_name}/{key}"
        
        # Calculate expiration
        expire_date = datetime.now() + timedelta(seconds=expiration)
        
        # Sign URL
        signed_url = cloudfront_signer.generate_presigned_url(
            url,
            date_less_than=expire_date
        )
        
        return signed_url
    
    def invalidate_cache(self, paths: list) -> str:
        """
        Invalidate CloudFront cache for specific paths
        
        Args:
            paths: List of paths to invalidate (e.g., ['/images/*', '/videos/abc.mp4'])
        
        Returns:
            Invalidation ID
        """
        
        try:
            response = self.client.create_invalidation(
                DistributionId=self.distribution_id,
                InvalidationBatch={
                    'Paths': {
                        'Quantity': len(paths),
                        'Items': paths
                    },
                    'CallerReference': str(datetime.now().timestamp())
                }
            )
            
            invalidation_id = response['Invalidation']['Id']
            
            logger.info(
                f"Cache invalidation created: {invalidation_id}",
                extra={"paths": paths}
            )
            
            return invalidation_id
            
        except Exception as e:
            logger.error(f"Cache invalidation failed: {e}")
            raise
    
    def get_distribution_config(self) -> Dict:
        """Get CloudFront distribution configuration"""
        
        try:
            response = self.client.get_distribution_config(
                Id=self.distribution_id
            )
            
            return response['DistributionConfig']
            
        except Exception as e:
            logger.error(f"Failed to get distribution config: {e}")
            raise


class CloudflareCDN:
    """
    Cloudflare CDN integration
    
    Features:
    - Cache purging
    - Zone management
    - Custom caching rules
    """
    
    def __init__(
        self,
        api_token: str,
        zone_id: str,
        domain_name: str
    ):
        """
        Initialize Cloudflare CDN
        
        Args:
            api_token: Cloudflare API token
            zone_id: Zone ID
            domain_name: Domain name
        """
        self.api_token = api_token
        self.zone_id = zone_id
        self.domain_name = domain_name
        self.api_url = "https://api.cloudflare.com/client/v4"
    
    def get_url(self, key: str) -> str:
        """
        Get CDN URL for object
        
        Args:
            key: Object key
        
        Returns:
            CDN URL
        """
        return f"https://{self.domain_name}/{key}"
    
    def purge_cache(
        self,
        files: Optional[list] = None,
        purge_everything: bool = False
    ) -> bool:
        """
        Purge Cloudflare cache
        
        Args:
            files: List of file URLs to purge
            purge_everything: Purge entire cache
        
        Returns:
            Success status
        """
        
        import requests
        
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        
        if purge_everything:
            data = {"purge_everything": True}
        else:
            data = {"files": files or []}
        
        try:
            response = requests.post(
                f"{self.api_url}/zones/{self.zone_id}/purge_cache",
                headers=headers,
                json=data
            )
            
            response.raise_for_status()
            
            logger.info(
                f"Cache purged successfully",
                extra={"purge_everything": purge_everything, "files": files}
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Cache purge failed: {e}")
            return False
    
    def create_page_rule(
        self,
        url_pattern: str,
        cache_level: str = "cache_everything",
        edge_cache_ttl: int = 86400
    ) -> Dict:
        """
        Create Cloudflare page rule for custom caching
        
        Args:
            url_pattern: URL pattern (e.g., '*example.com/images/*')
            cache_level: Cache level (cache_everything, no_cache, etc.)
            edge_cache_ttl: Edge cache TTL in seconds
        
        Returns:
            Page rule details
        """
        
        import requests
        
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        
        data = {
            "targets": [
                {
                    "target": "url",
                    "constraint": {
                        "operator": "matches",
                        "value": url_pattern
                    }
                }
            ],
            "actions": [
                {
                    "id": "cache_level",
                    "value": cache_level
                },
                {
                    "id": "edge_cache_ttl",
                    "value": edge_cache_ttl
                }
            ],
            "priority": 1,
            "status": "active"
        }
        
        try:
            response = requests.post(
                f"{self.api_url}/zones/{self.zone_id}/pagerules",
                headers=headers,
                json=data
            )
            
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"Failed to create page rule: {e}")
            raise


# CDN Factory
class CDNFactory:
    """Factory for creating CDN instances"""
    
    @staticmethod
    def create(cdn_type: str, **kwargs):
        """
        Create CDN instance
        
        Args:
            cdn_type: Type of CDN (cloudfront, cloudflare)
            **kwargs: CDN-specific parameters
        
        Returns:
            CDN instance
        """
        
        if cdn_type == "cloudfront":
            return CloudFrontCDN(**kwargs)
        elif cdn_type == "cloudflare":
            return CloudflareCDN(**kwargs)
        else:
            raise ValueError(f"Unknown CDN type: {cdn_type}")


# Example usage
if __name__ == "__main__":
    # CloudFront
    cf_cdn = CloudFrontCDN(
        distribution_id="E1234567890ABC",
        domain_name="cdn.example.com",
        key_pair_id="APKAEXAMPLE",
        private_key_path="/path/to/private_key.pem"
    )
    
    # Generate signed URL
    url = cf_cdn.get_signed_url("images/2024/01/photo.jpg", expiration=3600)
    print(f"Signed URL: {url}")
    
    # Invalidate cache
    cf_cdn.invalidate_cache(["/images/*"])
    
    # Cloudflare
    cf_cdn = CloudflareCDN(
        api_token="your_token",
        zone_id="your_zone_id",
        domain_name="cdn.example.com"
    )
    
    # Purge cache
    cf_cdn.purge_cache(files=[
        "https://cdn.example.com/images/photo.jpg"
    ])
2. CDN Integration in Storage
python# backend/core/storage/cdn_storage.py

"""
Storage with CDN integration
"""

from core.storage.s3 import S3Storage
from services.cdn import CDNFactory
from typing import Optional


class CDNEnabledStorage(S3Storage):
    """
    S3 Storage with CDN integration
    
    Automatically serves files through CDN
    """
    
    def __init__(
        self,
        bucket: str,
        aws_access_key_id: str,
        aws_secret_access_key: str,
        cdn_type: str = "cloudfront",
        cdn_config: dict = None,
        **kwargs
    ):
        """
        Initialize CDN-enabled storage
        
        Args:
            bucket: S3 bucket
            aws_access_key_id: AWS key
            aws_secret_access_key: AWS secret
            cdn_type: CDN type (cloudfront, cloudflare)
            cdn_config: CDN configuration
        """
        super().__init__(
            bucket,
            aws_access_key_id,
            aws_secret_access_key,
            **kwargs
        )
        
        # Initialize CDN
        if cdn_config:
            self.cdn = CDNFactory.create(cdn_type, **cdn_config)
        else:
            self.cdn = None
    
    def get_public_url(self, key: str, use_cdn: bool = True) -> str:
        """
        Get public URL for object
        
        Args:
            key: Object key
            use_cdn: Use CDN URL (default: True)
        
        Returns:
            Public URL
        """
        
        if use_cdn and self.cdn:
            if isinstance(self.cdn, CloudFrontCDN):
                # For CloudFront, generate signed URL
                return self.cdn.get_signed_url(key)
            else:
                # For Cloudflare, just return CDN URL
                return self.cdn.get_url(key)
        else:
            # Return S3 URL
            return f"https://{self.bucket}.s3.amazonaws.com/{key}"
    
    def invalidate_cache(self, keys: list):
        """Invalidate CDN cache for specific keys"""
        
        if self.cdn:
            if isinstance(self.cdn, CloudFrontCDN):
                # CloudFront invalidation
                paths = [f"/{key}" for key in keys]
                self.cdn.invalidate_cache(paths)
            elif isinstance(self.cdn, CloudflareCDN):
                # Cloudflare purge
                urls = [self.cdn.get_url(key) for key in keys]
                self.cdn.purge_cache(files=urls)

🛡️ VIRUS SCANNING
1. ClamAV Setup
dockerfile# docker/clamav/Dockerfile

FROM clamav/clamav:latest

# Install freshclam (virus database updater)
RUN freshclam

# Expose ClamAV daemon port
EXPOSE 3310

# Health check
HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
  CMD clamdcheck || exit 1

CMD ["clamd"]
yaml# docker-compose.yml - ClamAV Service

version: '3.8'

services:
  clamav:
    build: ./docker/clamav
    container_name: clamav
    ports:
      - "3310:3310"
    volumes:
      - clamav_db:/var/lib/clamav
    environment:
      - CLAMD_CONF_MaxFileSize=100M
      - CLAMD_CONF_MaxScanSize=500M
      - CLAMD_CONF_StreamMaxLength=100M
    healthcheck:
      test: ["CMD", "clamdcheck"]
      interval: 60s
      timeout: 10s
      retries: 3
    networks:
      - app_network

volumes:
  clamav_db:
    driver: local

networks:
  app_network:
    driver: bridge
2. Virus Scanner Service
python# backend/services/virus_scanner.py

"""
Virus Scanning Service using ClamAV

Features:
- Scan uploaded files
- Async scanning
- Quarantine infected files
"""

import clamd
from typing import Dict, Optional
from loguru import logger


class VirusScanner:
    """
    ClamAV virus scanner integration
    
    Scans files for viruses and malware
    """
    
    def __init__(self, host: str = 'localhost', port: int = 3310):
        """
        Initialize virus scanner
        
        Args:
            host: ClamAV daemon host
            port: ClamAV daemon port
        """
        self.host = host
        self.port = port
        
        try:
            self.client = clamd.ClamdNetworkSocket(host, port)
            # Test connection
            self.client.ping()
            logger.info(f"Connected to ClamAV at {host}:{port}")
        except Exception as e:
            logger.error(f"Failed to connect to ClamAV: {e}")
            self.client = None
    
    def scan_bytes(self, data: bytes) -> Dict[str, any]:
        """
        Scan bytes for viruses
        
        Args:
            data: File bytes to scan
        
        Returns:
            Scan result
        """
        
        if not self.client:
            logger.warning("ClamAV not available, skipping scan")
            return {
                "clean": True,
                "skipped": True,
                "reason": "Scanner not available"
            }
        
        try:
            # Scan data
            result = self.client.instream(data)
            
            # Parse result
            # Result format: {'stream': ('FOUND', 'Virus.Name')} or {'stream': ('OK', None)}
            status = result['stream']
            
            if status[0] == 'OK':
                logger.info("File scan: CLEAN")
                return {
                    "clean": True,
                    "virus": None
                }
            elif status[0] == 'FOUND':
                virus_name = status[1]
                logger.warning(f"File scan: INFECTED - {virus_name}")
                return {
                    "clean": False,
                    "virus": virus_name
                }
            else:
                logger.error(f"File scan: ERROR - {status}")
                return {
                    "clean": False,
                    "error": status[1]
                }
                
        except Exception as e:
            logger.error(f"Virus scan failed: {e}")
            return {
                "clean": False,
                "error": str(e)
            }
    
    def scan_file(self, file_path: str) -> Dict[str, any]:
        """
        Scan file for viruses
        
        Args:
            file_path: Path to file
        
        Returns:
            Scan result
        """
        
        try:
            with open(file_path, 'rb') as f:
                data = f.read()
            
            return self.scan_bytes(data)
            
        except Exception as e:
            logger.error(f"Failed to scan file: {e}")
            return {
                "clean": False,
                "error": str(e)
            }
    
    def get_version(self) -> Optional[str]:
        """Get ClamAV version"""
        
        if not self.client:
            return None
        
        try:
            return self.client.version()
        except Exception as e:
            logger.error(f"Failed to get version: {e}")
            return None
    
    def reload_database(self) -> bool:
        """Reload virus database"""
        
        if not self.client:
            return False
        
        try:
            self.client.reload()
            logger.info("ClamAV database reloaded")
            return True
        except Exception as e:
            logger.error(f"Failed to reload database: {e}")
            return False


# Example usage
if __name__ == "__main__":
    scanner = VirusScanner()
    
    # Check version
    version = scanner.get_version()
    print(f"ClamAV version: {version}")
    
    # Scan file
    result = scanner.scan_file("test.pdf")
    print(f"Scan result: {result}")
3. Upload with Virus Scanning
python# backend/api/endpoints/upload_with_scan.py

"""
File Upload with Virus Scanning
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session

from services.virus_scanner import VirusScanner
from core.storage.factory import StorageFactory
from repositories.file_repository import FileRepository
from database import get_db
from auth import get_current_user
from loguru import logger


router = APIRouter(prefix="/api/upload", tags=["upload"])


@router.post("/secure")
async def upload_with_virus_scan(
    file: UploadFile = File(...),
    category: str = "general",
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Upload file with virus scanning
    
    - Scans file for viruses
    - Quarantines infected files
    - Stores clean files
    """
    
    try:
        # Read file
        content = await file.read()
        
        # Scan for viruses
        scanner = VirusScanner()
        scan_result = scanner.scan_bytes(content)
        
        if not scan_result['clean']:
            # File is infected
            virus = scan_result.get('virus', 'Unknown')
            
            logger.warning(
                f"Infected file upload blocked: {file.filename}",
                extra={
                    "user_id": current_user.id,
                    "virus": virus
                }
            )
            
            # Quarantine file
            storage = StorageFactory.create()
            quarantine_key = f"quarantine/{file.filename}_{uuid.uuid4()}"
            
            from io import BytesIO
            storage.upload_file(
                BytesIO(content),
                quarantine_key,
                content_type=file.content_type
            )
            
            # Create database record (marked as quarantined)
            file_repo = FileRepository(db)
            file_repo.create({
                "uuid": str(uuid.uuid4()),
                "filename": file.filename,
                "original_filename": file.filename,
                "storage_type": "s3",
                "storage_path": quarantine_key,
                "size": len(content),
                "mime_type": file.content_type,
                "user_id": current_user.id,
                "category": "quarantine",
                "is_quarantined": True,
                "metadata": {
                    "virus": virus,
                    "scan_result": scan_result
                }
            })
            
            raise HTTPException(
                status_code=400,
                detail=f"File infected with virus: {virus}"
            )
        
        # File is clean - proceed with normal upload
        # ... (same as regular upload)
        
        logger.info(
            f"Clean file uploaded: {file.filename}",
            extra={
                "user_id": current_user.id,
                "size": len(content)
            }
        )
        
        return {
            "status": "success",
            "filename": file.filename,
            "scanned": True,
            "clean": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


📁 FILE STORAGE & MANAGEMENT GUIDE - TEIL 3
Storage Quotas, Cleanup & Best Practices

📋 TABLE OF CONTENTS (TEIL 3)

Storage Quotas
File Cleanup Strategies
Best Practices Summary
Quick Reference & Checklists


📊 STORAGE QUOTAS
1. Quota System Implementation
python# backend/services/quota_manager.py

"""
Storage Quota Management

Features:
- User storage limits
- Organization quotas
- Quota enforcement
- Usage tracking
- Alerts
"""

from sqlalchemy.orm import Session
from sqlalchemy import func
from models.file import File
from models.user import User
from typing import Dict, Optional
from loguru import logger
from datetime import datetime


class QuotaManager:
    """
    Manage storage quotas for users and organizations
    
    Quota hierarchy:
    - Free tier: 1 GB
    - Pro tier: 100 GB
    - Enterprise: Unlimited
    """
    
    # Quota limits by tier (in bytes)
    QUOTA_LIMITS = {
        'free': 1 * 1024 * 1024 * 1024,      # 1 GB
        'basic': 10 * 1024 * 1024 * 1024,    # 10 GB
        'pro': 100 * 1024 * 1024 * 1024,     # 100 GB
        'enterprise': None                     # Unlimited
    }
    
    # Warning thresholds
    WARNING_THRESHOLDS = [0.80, 0.90, 0.95]  # 80%, 90%, 95%
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_user_quota(self, user_id: int) -> Dict:
        """
        Get user's quota information
        
        Args:
            user_id: User ID
        
        Returns:
            Quota information
        """
        
        # Get user
        user = self.db.query(User).filter(User.id == user_id).first()
        
        if not user:
            raise ValueError(f"User not found: {user_id}")
        
        # Get quota limit based on tier
        tier = user.subscription_tier or 'free'
        limit = self.QUOTA_LIMITS.get(tier)
        
        # Calculate current usage
        usage = self._calculate_user_usage(user_id)
        
        # Calculate percentage
        if limit:
            percentage = (usage / limit) * 100
            remaining = limit - usage
        else:
            # Unlimited
            percentage = 0
            remaining = None
        
        return {
            'user_id': user_id,
            'tier': tier,
            'limit': limit,
            'limit_formatted': self._format_bytes(limit) if limit else 'Unlimited',
            'used': usage,
            'used_formatted': self._format_bytes(usage),
            'remaining': remaining,
            'remaining_formatted': self._format_bytes(remaining) if remaining else 'Unlimited',
            'percentage': round(percentage, 2),
            'is_exceeded': limit and usage > limit,
            'is_warning': limit and percentage >= 80
        }
    
    def _calculate_user_usage(self, user_id: int) -> int:
        """
        Calculate total storage usage for user
        
        Args:
            user_id: User ID
        
        Returns:
            Total bytes used
        """
        
        result = self.db.query(
            func.sum(File.size)
        ).filter(
            File.user_id == user_id,
            File.is_deleted == False
        ).scalar()
        
        return result or 0
    
    def check_quota(
        self,
        user_id: int,
        additional_size: int = 0
    ) -> Dict:
        """
        Check if user can upload more files
        
        Args:
            user_id: User ID
            additional_size: Size of file to upload (bytes)
        
        Returns:
            Quota check result
        """
        
        quota = self.get_user_quota(user_id)
        
        if quota['limit'] is None:
            # Unlimited
            return {
                'allowed': True,
                'reason': 'unlimited'
            }
        
        projected_usage = quota['used'] + additional_size
        
        if projected_usage > quota['limit']:
            return {
                'allowed': False,
                'reason': 'quota_exceeded',
                'current_usage': quota['used'],
                'limit': quota['limit'],
                'required': projected_usage,
                'shortage': projected_usage - quota['limit']
            }
        
        return {
            'allowed': True,
            'remaining': quota['limit'] - projected_usage
        }
    
    def enforce_quota(
        self,
        user_id: int,
        file_size: int
    ) -> bool:
        """
        Enforce quota before upload
        
        Args:
            user_id: User ID
            file_size: Size of file to upload
        
        Returns:
            True if upload allowed
        
        Raises:
            QuotaExceededException if quota exceeded
        """
        
        check = self.check_quota(user_id, file_size)
        
        if not check['allowed']:
            raise QuotaExceededException(
                f"Storage quota exceeded. "
                f"Used: {self._format_bytes(check['current_usage'])}, "
                f"Limit: {self._format_bytes(check['limit'])}"
            )
        
        # Check if warning threshold reached
        quota = self.get_user_quota(user_id)
        if quota['is_warning']:
            self._send_quota_warning(user_id, quota)
        
        return True
    
    def get_organization_usage(self, org_id: int) -> Dict:
        """
        Get organization-wide storage usage
        
        Args:
            org_id: Organization ID
        
        Returns:
            Organization usage statistics
        """
        
        # Get all users in organization
        users = self.db.query(User).filter(User.organization_id == org_id).all()
        
        total_usage = 0
        user_stats = []
        
        for user in users:
            usage = self._calculate_user_usage(user.id)
            total_usage += usage
            
            user_stats.append({
                'user_id': user.id,
                'email': user.email,
                'usage': usage,
                'usage_formatted': self._format_bytes(usage)
            })
        
        # Sort by usage
        user_stats.sort(key=lambda x: x['usage'], reverse=True)
        
        return {
            'organization_id': org_id,
            'total_users': len(users),
            'total_usage': total_usage,
            'total_usage_formatted': self._format_bytes(total_usage),
            'top_users': user_stats[:10]  # Top 10 users
        }
    
    def _send_quota_warning(self, user_id: int, quota: Dict):
        """
        Send quota warning notification
        
        Args:
            user_id: User ID
            quota: Quota information
        """
        
        percentage = quota['percentage']
        
        # Determine warning level
        if percentage >= 95:
            level = 'critical'
        elif percentage >= 90:
            level = 'high'
        else:
            level = 'medium'
        
        logger.warning(
            f"Storage quota warning: {level}",
            extra={
                'user_id': user_id,
                'percentage': percentage,
                'used': quota['used_formatted'],
                'limit': quota['limit_formatted']
            }
        )
        
        # Send email/notification
        # (Implementation depends on your notification system)
    
    def _format_bytes(self, bytes_size: Optional[int]) -> str:
        """Format bytes as human-readable string"""
        
        if bytes_size is None:
            return 'N/A'
        
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.2f} {unit}"
            bytes_size /= 1024.0
        
        return f"{bytes_size:.2f} PB"


class QuotaExceededException(Exception):
    """Exception raised when storage quota is exceeded"""
    pass


# Example usage
if __name__ == "__main__":
    from database import SessionLocal
    
    db = SessionLocal()
    quota_manager = QuotaManager(db)
    
    # Get user quota
    quota = quota_manager.get_user_quota(user_id=1)
    print(f"User quota: {quota}")
    
    # Check if can upload
    check = quota_manager.check_quota(user_id=1, additional_size=100*1024*1024)  # 100 MB
    print(f"Can upload: {check}")
    
    # Get org usage
    org_usage = quota_manager.get_organization_usage(org_id=1)
    print(f"Org usage: {org_usage}")
2. Quota Enforcement in Upload Endpoint
python# backend/api/endpoints/upload_with_quota.py

"""
File Upload with Quota Enforcement
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session
import uuid

from services.quota_manager import QuotaManager, QuotaExceededException
from core.storage.factory import StorageFactory
from repositories.file_repository import FileRepository
from database import get_db
from auth import get_current_user
from loguru import logger


router = APIRouter(prefix="/api/upload", tags=["upload"])


@router.post("/")
async def upload_with_quota_check(
    file: UploadFile = File(...),
    category: str = "general",
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Upload file with quota enforcement
    
    - Checks user's storage quota
    - Rejects upload if quota exceeded
    - Updates usage after upload
    """
    
    try:
        # Read file
        content = await file.read()
        file_size = len(content)
        
        # Check quota
        quota_manager = QuotaManager(db)
        
        try:
            quota_manager.enforce_quota(current_user.id, file_size)
        except QuotaExceededException as e:
            # Get current quota for detailed message
            quota = quota_manager.get_user_quota(current_user.id)
            
            raise HTTPException(
                status_code=413,  # Payload Too Large
                detail={
                    "error": "quota_exceeded",
                    "message": str(e),
                    "quota": {
                        "used": quota['used_formatted'],
                        "limit": quota['limit_formatted'],
                        "percentage": quota['percentage']
                    },
                    "upgrade_url": "/pricing"
                }
            )
        
        # Quota OK - proceed with upload
        storage = StorageFactory.create()
        file_uuid = str(uuid.uuid4())
        
        from datetime import datetime
        from io import BytesIO
        
        now = datetime.now()
        storage_key = f"uploads/{now.year}/{now.month:02d}/{now.day:02d}/{file_uuid}_{file.filename}"
        
        result = storage.upload_file(
            BytesIO(content),
            storage_key,
            content_type=file.content_type
        )
        
        # Create database record
        file_repo = FileRepository(db)
        file_record = file_repo.create({
            "uuid": file_uuid,
            "filename": file.filename,
            "original_filename": file.filename,
            "storage_type": "s3",
            "storage_path": storage_key,
            "storage_bucket": result['bucket'],
            "size": file_size,
            "mime_type": file.content_type,
            "user_id": current_user.id,
            "category": category
        })
        
        # Get updated quota
        updated_quota = quota_manager.get_user_quota(current_user.id)
        
        logger.info(
            f"File uploaded: {file.filename}",
            extra={
                "user_id": current_user.id,
                "file_uuid": file_uuid,
                "size": file_size,
                "quota_used": updated_quota['percentage']
            }
        )
        
        return {
            "uuid": file_uuid,
            "filename": file.filename,
            "size": file_size,
            "url": f"/api/files/{file_uuid}",
            "quota": {
                "used": updated_quota['used_formatted'],
                "limit": updated_quota['limit_formatted'],
                "percentage": updated_quota['percentage'],
                "remaining": updated_quota['remaining_formatted']
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quota")
async def get_quota(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get current user's quota information"""
    
    quota_manager = QuotaManager(db)
    quota = quota_manager.get_user_quota(current_user.id)
    
    return quota
3. Quota Monitoring Dashboard
python# backend/services/quota_monitor.py

"""
Quota Monitoring Service

Features:
- Track quota usage trends
- Alert on high usage
- Generate reports
"""

from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from models.file import File
from models.user import User
from datetime import datetime, timedelta
from typing import List, Dict
from loguru import logger


class QuotaMonitor:
    """Monitor and report on storage quota usage"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_users_near_limit(self, threshold: float = 0.80) -> List[Dict]:
        """
        Get users approaching their quota limit
        
        Args:
            threshold: Percentage threshold (0.80 = 80%)
        
        Returns:
            List of users near limit
        """
        
        from services.quota_manager import QuotaManager
        
        quota_manager = QuotaManager(self.db)
        
        # Get all active users
        users = self.db.query(User).filter(User.is_active == True).all()
        
        near_limit = []
        
        for user in users:
            quota = quota_manager.get_user_quota(user.id)
            
            if quota['limit'] and quota['percentage'] >= (threshold * 100):
                near_limit.append({
                    'user_id': user.id,
                    'email': user.email,
                    'tier': quota['tier'],
                    'used': quota['used_formatted'],
                    'limit': quota['limit_formatted'],
                    'percentage': quota['percentage']
                })
        
        # Sort by percentage
        near_limit.sort(key=lambda x: x['percentage'], reverse=True)
        
        return near_limit
    
    def get_growth_trend(
        self,
        user_id: int,
        days: int = 30
    ) -> Dict:
        """
        Analyze storage growth trend
        
        Args:
            user_id: User ID
            days: Number of days to analyze
        
        Returns:
            Growth trend analysis
        """
        
        cutoff = datetime.now() - timedelta(days=days)
        
        # Get file uploads over time
        uploads = self.db.query(
            func.date(File.created_at).label('date'),
            func.sum(File.size).label('total_size'),
            func.count(File.id).label('file_count')
        ).filter(
            File.user_id == user_id,
            File.created_at >= cutoff,
            File.is_deleted == False
        ).group_by(
            func.date(File.created_at)
        ).all()
        
        if not uploads:
            return {
                'trend': 'stable',
                'daily_average': 0,
                'projected_monthly': 0
            }
        
        # Calculate daily average
        total_added = sum(upload.total_size for upload in uploads)
        daily_average = total_added / days
        
        # Project monthly growth
        projected_monthly = daily_average * 30
        
        # Determine trend
        if daily_average > 100 * 1024 * 1024:  # > 100 MB/day
            trend = 'high_growth'
        elif daily_average > 10 * 1024 * 1024:  # > 10 MB/day
            trend = 'moderate_growth'
        else:
            trend = 'low_growth'
        
        return {
            'trend': trend,
            'daily_average': daily_average,
            'daily_average_formatted': self._format_bytes(daily_average),
            'projected_monthly': projected_monthly,
            'projected_monthly_formatted': self._format_bytes(projected_monthly),
            'data_points': len(uploads)
        }
    
    def generate_quota_report(self) -> Dict:
        """
        Generate comprehensive quota report
        
        Returns:
            Quota report
        """
        
        # Total storage usage
        total_usage = self.db.query(
            func.sum(File.size)
        ).filter(
            File.is_deleted == False
        ).scalar() or 0
        
        # Total files
        total_files = self.db.query(
            func.count(File.id)
        ).filter(
            File.is_deleted == False
        ).scalar() or 0
        
        # Users by tier
        tier_breakdown = self.db.query(
            User.subscription_tier,
            func.count(User.id).label('user_count')
        ).filter(
            User.is_active == True
        ).group_by(
            User.subscription_tier
        ).all()
        
        # Users near limit
        near_limit = self.get_users_near_limit(threshold=0.80)
        
        # Top storage users
        top_users = self.db.query(
            File.user_id,
            func.sum(File.size).label('total_size')
        ).filter(
            File.is_deleted == False
        ).group_by(
            File.user_id
        ).order_by(
            func.sum(File.size).desc()
        ).limit(10).all()
        
        return {
            'generated_at': datetime.now().isoformat(),
            'summary': {
                'total_usage': self._format_bytes(total_usage),
                'total_files': total_files,
                'average_file_size': self._format_bytes(total_usage / total_files if total_files else 0)
            },
            'tier_breakdown': [
                {
                    'tier': tier or 'free',
                    'users': count
                }
                for tier, count in tier_breakdown
            ],
            'users_near_limit': len(near_limit),
            'top_users': [
                {
                    'user_id': user_id,
                    'usage': self._format_bytes(size)
                }
                for user_id, size in top_users
            ]
        }
    
    def _format_bytes(self, bytes_size: int) -> str:
        """Format bytes as human-readable string"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.2f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.2f} PB"


# Monitoring endpoint
from fastapi import APIRouter, Depends
from database import get_db

router = APIRouter(prefix="/api/admin/quota", tags=["admin"])


@router.get("/report")
async def get_quota_report(
    db: Session = Depends(get_db),
    # current_admin = Depends(get_admin_user)
):
    """Get comprehensive quota report (admin only)"""
    
    monitor = QuotaMonitor(db)
    report = monitor.generate_quota_report()
    
    return report


@router.get("/alerts")
async def get_quota_alerts(
    threshold: float = 0.80,
    db: Session = Depends(get_db),
    # current_admin = Depends(get_admin_user)
):
    """Get users near quota limit (admin only)"""
    
    monitor = QuotaMonitor(db)
    alerts = monitor.get_users_near_limit(threshold)
    
    return {
        'threshold': threshold * 100,
        'count': len(alerts),
        'users': alerts
    }

🧹 FILE CLEANUP STRATEGIES
1. Orphaned File Cleanup
python# backend/services/cleanup_service.py

"""
File Cleanup Service

Features:
- Remove orphaned files
- Clean temporary files
- Remove old deleted files
- Deduplicate files
"""

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from models.file import File
from core.storage.factory import StorageFactory
from datetime import datetime, timedelta
from typing import List, Dict
from loguru import logger


class CleanupService:
    """
    File cleanup and maintenance service
    
    Handles:
    - Orphaned file removal
    - Temporary file cleanup
    - Soft-deleted file purging
    - Storage optimization
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    def find_orphaned_files(
        self,
        not_accessed_days: int = 90
    ) -> List[File]:
        """
        Find files not accessed in X days
        
        Args:
            not_accessed_days: Days threshold
        
        Returns:
            List of orphaned files
        """
        
        cutoff = datetime.now() - timedelta(days=not_accessed_days)
        
        orphaned = self.db.query(File).filter(
            or_(
                File.accessed_at < cutoff,
                File.accessed_at.is_(None)
            ),
            File.is_deleted == False
        ).all()
        
        logger.info(
            f"Found {len(orphaned)} orphaned files",
            extra={'threshold_days': not_accessed_days}
        )
        
        return orphaned
    
    def cleanup_temp_files(self, older_than_hours: int = 24) -> int:
        """
        Remove temporary files older than X hours
        
        Args:
            older_than_hours: Age threshold in hours
        
        Returns:
            Number of files cleaned
        """
        
        cutoff = datetime.now() - timedelta(hours=older_than_hours)
        
        # Find temp files
        temp_files = self.db.query(File).filter(
            File.category == 'temp',
            File.created_at < cutoff
        ).all()
        
        cleaned = 0
        storage = StorageFactory.create()
        
        for file in temp_files:
            try:
                # Delete from storage
                storage.delete_file(file.storage_path)
                
                # Delete from database
                self.db.delete(file)
                
                cleaned += 1
                
            except Exception as e:
                logger.error(f"Failed to cleanup temp file: {e}")
        
        self.db.commit()
        
        logger.info(
            f"Cleaned up {cleaned} temp files",
            extra={'threshold_hours': older_than_hours}
        )
        
        return cleaned
    
    def purge_deleted_files(self, days: int = 30) -> int:
        """
        Permanently remove soft-deleted files after X days
        
        Args:
            days: Days after deletion to purge
        
        Returns:
            Number of files purged
        """
        
        cutoff = datetime.now() - timedelta(days=days)
        
        # Find files to purge
        to_purge = self.db.query(File).filter(
            File.is_deleted == True,
            File.deleted_at < cutoff
        ).all()
        
        purged = 0
        storage = StorageFactory.create()
        
        for file in to_purge:
            try:
                # Delete from storage
                storage.delete_file(file.storage_path)
                
                # Delete variants if they exist
                if file.metadata and 'variants' in file.metadata:
                    for variant_path in file.metadata['variants'].values():
                        try:
                            storage.delete_file(variant_path)
                        except:
                            pass
                
                # Delete from database
                self.db.delete(file)
                
                purged += 1
                
            except Exception as e:
                logger.error(f"Failed to purge file: {e}")
        
        self.db.commit()
        
        logger.info(
            f"Purged {purged} deleted files",
            extra={'threshold_days': days}
        )
        
        return purged
    
    def find_duplicates(self) -> List[Dict]:
        """
        Find duplicate files based on SHA256 hash
        
        Returns:
            List of duplicate file groups
        """
        
        from sqlalchemy import func
        
        # Find hashes that appear more than once
        duplicates = self.db.query(
            File.sha256,
            func.count(File.id).label('count'),
            func.sum(File.size).label('total_size')
        ).filter(
            File.sha256.isnot(None),
            File.is_deleted == False
        ).group_by(
            File.sha256
        ).having(
            func.count(File.id) > 1
        ).all()
        
        duplicate_groups = []
        
        for sha256, count, total_size in duplicates:
            # Get all files with this hash
            files = self.db.query(File).filter(
                File.sha256 == sha256,
                File.is_deleted == False
            ).all()
            
            # Calculate waste (all but one could be removed)
            waste = total_size - files[0].size
            
            duplicate_groups.append({
                'sha256': sha256,
                'count': count,
                'total_size': total_size,
                'waste': waste,
                'waste_formatted': self._format_bytes(waste),
                'files': [
                    {
                        'id': f.id,
                        'uuid': f.uuid,
                        'filename': f.filename,
                        'user_id': f.user_id,
                        'created_at': f.created_at
                    }
                    for f in files
                ]
            })
        
        # Sort by waste (highest first)
        duplicate_groups.sort(key=lambda x: x['waste'], reverse=True)
        
        logger.info(
            f"Found {len(duplicate_groups)} duplicate groups",
            extra={
                'total_waste': sum(g['waste'] for g in duplicate_groups)
            }
        )
        
        return duplicate_groups
    
    def deduplicate_files(
        self,
        dry_run: bool = True
    ) -> Dict:
        """
        Deduplicate files by replacing duplicates with references
        
        Args:
            dry_run: If True, only simulate (don't actually delete)
        
        Returns:
            Deduplication results
        """
        
        duplicates = self.find_duplicates()
        
        total_saved = 0
        files_removed = 0
        
        storage = StorageFactory.create()
        
        for group in duplicates:
            # Keep the oldest file, remove others
            files = sorted(group['files'], key=lambda x: x['created_at'])
            keep_file = files[0]
            remove_files = files[1:]
            
            for remove_file in remove_files:
                # Get full file record
                file_record = self.db.query(File).filter(
                    File.id == remove_file['id']
                ).first()
                
                if not dry_run:
                    # Delete from storage
                    try:
                        storage.delete_file(file_record.storage_path)
                    except:
                        pass
                    
                    # Update database to point to kept file
                    file_record.storage_path = None
                    file_record.metadata = {
                        **file_record.metadata,
                        'deduped': True,
                        'references': keep_file['uuid']
                    }
                
                total_saved += file_record.size
                files_removed += 1
        
        if not dry_run:
            self.db.commit()
        
        logger.info(
            f"Deduplication complete (dry_run={dry_run})",
            extra={
                'files_removed': files_removed,
                'space_saved': self._format_bytes(total_saved)
            }
        )
        
        return {
            'dry_run': dry_run,
            'files_removed': files_removed,
            'space_saved': total_saved,
            'space_saved_formatted': self._format_bytes(total_saved)
        }
    
    def cleanup_quarantine(self, days: int = 7) -> int:
        """
        Remove old quarantined files
        
        Args:
            days: Days to keep in quarantine
        
        Returns:
            Number of files removed
        """
        
        cutoff = datetime.now() - timedelta(days=days)
        
        quarantined = self.db.query(File).filter(
            File.is_quarantined == True,
            File.created_at < cutoff
        ).all()
        
        removed = 0
        storage = StorageFactory.create()
        
        for file in quarantined:
            try:
                storage.delete_file(file.storage_path)
                self.db.delete(file)
                removed += 1
            except Exception as e:
                logger.error(f"Failed to remove quarantined file: {e}")
        
        self.db.commit()
        
        logger.info(
            f"Removed {removed} quarantined files",
            extra={'threshold_days': days}
        )
        
        return removed
    
    def _format_bytes(self, bytes_size: int) -> str:
        """Format bytes as human-readable string"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.2f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.2f} PB"


# Scheduled cleanup task
from celery import Celery
from database import SessionLocal

celery_app = Celery(
    'cleanup',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/0'
)


@celery_app.task(name='daily_cleanup')
def daily_cleanup():
    """
    Daily cleanup task
    
    - Remove temp files
    - Clean quarantine
    """
    
    db = SessionLocal()
    cleanup = CleanupService(db)
    
    try:
        # Cleanup temp files older than 24 hours
        cleanup.cleanup_temp_files(older_than_hours=24)
        
        # Remove old quarantine files
        cleanup.cleanup_quarantine(days=7)
        
        logger.info("Daily cleanup completed")
        
    finally:
        db.close()


@celery_app.task(name='weekly_cleanup')
def weekly_cleanup():
    """
    Weekly cleanup task
    
    - Purge deleted files
    - Find duplicates
    """
    
    db = SessionLocal()
    cleanup = CleanupService(db)
    
    try:
        # Purge files deleted more than 30 days ago
        cleanup.purge_deleted_files(days=30)
        
        # Find duplicates (reporting only)
        duplicates = cleanup.find_duplicates()
        logger.info(f"Found {len(duplicates)} duplicate groups")
        
        logger.info("Weekly cleanup completed")
        
    finally:
        db.close()
2. Storage Lifecycle Management
python# backend/services/lifecycle_manager.py

"""
Storage Lifecycle Management

Features:
- Automatic archiving of old files
- Transition to cheaper storage tiers
- Expiration policies
"""

from sqlalchemy.orm import Session
from models.file import File
from core.storage.s3 import S3Storage
from datetime import datetime, timedelta
from typing import List, Dict
from loguru import logger


class LifecycleManager:
    """
    Manage file storage lifecycle
    
    Storage tiers:
    - Hot (STANDARD): Active files, fast access
    - Warm (STANDARD_IA): Infrequent access
    - Cold (GLACIER): Archive, slow retrieval
    """
    
    LIFECYCLE_RULES = {
        'documents': {
            'to_ia_days': 90,      # Move to IA after 90 days
            'to_glacier_days': 365, # Move to Glacier after 1 year
            'expire_days': None     # Never expire
        },
        'images': {
            'to_ia_days': 30,
            'to_glacier_days': 180,
            'expire_days': 730      # Delete after 2 years
        },
        'temp': {
            'to_ia_days': None,
            'to_glacier_days': None,
            'expire_days': 1        # Delete after 1 day
        },
        'backups': {
            'to_ia_days': 7,
            'to_glacier_days': 30,
            'expire_days': 90
        }
    }
    
    def __init__(self, db: Session, storage: S3Storage):
        self.db = db
        self.storage = storage
    
    def apply_lifecycle_policies(self) -> Dict:
        """
        Apply lifecycle policies to all files
        
        Returns:
            Results summary
        """
        
        results = {
            'moved_to_ia': 0,
            'moved_to_glacier': 0,
            'expired': 0
        }
        
        for category, rules in self.LIFECYCLE_RULES.items():
            # Process files in this category
            files = self.db.query(File).filter(
                File.category == category,
                File.is_deleted == False
            ).all()
            
            for file in files:
                age_days = (datetime.now() - file.created_at).days
                current_class = file.metadata.get('storage_class', 'STANDARD')
                
                # Check expiration
                if rules['expire_days'] and age_days >= rules['expire_days']:
                    self._expire_file(file)
                    results['expired'] += 1
                
                # Check Glacier transition
                elif (rules['to_glacier_days'] and 
                      age_days >= rules['to_glacier_days'] and
                      current_class != 'GLACIER'):
                    self._transition_to_glacier(file)
                    results['moved_to_glacier'] += 1
                
                # Check IA transition
                elif (rules['to_ia_days'] and
                      age_days >= rules['to_ia_days'] and
                      current_class == 'STANDARD'):
                    self._transition_to_ia(file)
                    results['moved_to_ia'] += 1
        
        self.db.commit()
        
        logger.info(
            "Lifecycle policies applied",
            extra=results
        )
        
        return results
    
    def _transition_to_ia(self, file: File):
        """Move file to STANDARD_IA storage class"""
        
        try:
            # Copy to IA
            self.storage.client.copy_object(
                Bucket=file.storage_bucket,
                CopySource={
                    'Bucket': file.storage_bucket,
                    'Key': file.storage_path
                },
                Key=file.storage_path,
                StorageClass='STANDARD_IA'
            )
            
            # Update metadata
            if not file.metadata:
                file.metadata = {}
            file.metadata['storage_class'] = 'STANDARD_IA'
            file.metadata['transitioned_at'] = datetime.now().isoformat()
            
            logger.info(
                f"Transitioned to IA: {file.uuid}",
                extra={'filename': file.filename}
            )
            
        except Exception as e:
            logger.error(f"Failed to transition to IA: {e}")
    
    def _transition_to_glacier(self, file: File):
        """Move file to GLACIER storage class"""
        
        try:
            # Copy to Glacier
            self.storage.client.copy_object(
                Bucket=file.storage_bucket,
                CopySource={
                    'Bucket': file.storage_bucket,
                    'Key': file.storage_path
                },
                Key=file.storage_path,
                StorageClass='GLACIER'
            )
            
            # Update metadata
            if not file.metadata:
                file.metadata = {}
            file.metadata['storage_class'] = 'GLACIER'
            file.metadata['archived_at'] = datetime.now().isoformat()
            
            logger.info(
                f"Archived to Glacier: {file.uuid}",
                extra={'filename': file.filename}
            )
            
        except Exception as e:
            logger.error(f"Failed to archive to Glacier: {e}")
    
    def _expire_file(self, file: File):
        """Permanently delete expired file"""
        
        try:
            # Delete from storage
            self.storage.delete_file(file.storage_path)
            
            # Delete from database
            self.db.delete(file)
            
            logger.info(
                f"Expired file deleted: {file.uuid}",
                extra={'filename': file.filename}
            )
            
        except Exception as e:
            logger.error(f"Failed to expire file: {e}")


# Celery task
@celery_app.task(name='apply_lifecycle_policies')
def apply_lifecycle_policies():
    """Apply storage lifecycle policies"""
    
    db = SessionLocal()
    
    try:
        from config import settings
        
        storage = S3Storage(
            bucket=settings.S3_BUCKET,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
        )
        
        lifecycle = LifecycleManager(db, storage)
        results = lifecycle.apply_lifecycle_policies()
        
        logger.info(f"Lifecycle policies applied: {results}")
        
    finally:
        db.close()
3. Cleanup API Endpoints
python# backend/api/endpoints/cleanup.py

"""
File Cleanup API (Admin Only)
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from services.cleanup_service import CleanupService
from database import get_db
from auth import get_admin_user


router = APIRouter(prefix="/api/admin/cleanup", tags=["admin"])


@router.get("/orphaned")
async def find_orphaned_files(
    days: int = 90,
    db: Session = Depends(get_db),
    current_admin = Depends(get_admin_user)
):
    """Find files not accessed in X days"""
    
    cleanup = CleanupService(db)
    orphaned = cleanup.find_orphaned_files(not_accessed_days=days)
    
    return {
        'count': len(orphaned),
        'threshold_days': days,
        'files': [
            {
                'uuid': f.uuid,
                'filename': f.filename,
                'size': f.size,
                'created_at': f.created_at,
                'accessed_at': f.accessed_at
            }
            for f in orphaned[:100]  # Limit to 100
        ]
    }


@router.post("/temp")
async def cleanup_temp_files(
    hours: int = 24,
    db: Session = Depends(get_db),
    current_admin = Depends(get_admin_user)
):
    """Remove temporary files older than X hours"""
    
    cleanup = CleanupService(db)
    count = cleanup.cleanup_temp_files(older_than_hours=hours)
    
    return {
        'cleaned': count,
        'threshold_hours': hours
    }


@router.post("/deleted")
async def purge_deleted_files(
    days: int = 30,
    db: Session = Depends(get_db),
    current_admin = Depends(get_admin_user)
):
    """Permanently remove soft-deleted files"""
    
    cleanup = CleanupService(db)
    count = cleanup.purge_deleted_files(days=days)
    
    return {
        'purged': count,
        'threshold_days': days
    }


@router.get("/duplicates")
async def find_duplicates(
    db: Session = Depends(get_db),
    current_admin = Depends(get_admin_user)
):
    """Find duplicate files"""
    
    cleanup = CleanupService(db)
    duplicates = cleanup.find_duplicates()
    
    total_waste = sum(d['waste'] for d in duplicates)
    
    return {
        'groups': len(duplicates),
        'total_waste': total_waste,
        'total_waste_formatted': cleanup._format_bytes(total_waste),
        'duplicates': duplicates[:50]  # Limit to 50
    }


@router.post("/deduplicate")
async def deduplicate_files(
    dry_run: bool = True,
    db: Session = Depends(get_db),
    current_admin = Depends(get_admin_user)
):
    """Deduplicate files"""
    
    cleanup = CleanupService(db)
    result = cleanup.deduplicate_files(dry_run=dry_run)
    
    return result

✅ BEST PRACTICES SUMMARY
1. Storage Best Practices
python# docs/storage_best_practices.py

"""
File Storage & Management Best Practices
=========================================

A comprehensive guide to best practices
"""

BEST_PRACTICES = {
    # ============================================
    # FILE ORGANIZATION
    # ============================================
    "organization": {
        "DO": [
            "Use date-based directory structure (YYYY/MM/DD)",
            "Generate unique file identifiers (UUIDs)",
            "Sanitize all user-provided filenames",
            "Store metadata in database, not filename",
            "Separate different file types",
            "Use consistent naming conventions"
        ],
        "DON'T": [
            "Store files in single flat directory",
            "Trust user-provided filenames",
            "Encode metadata in filenames",
            "Mix file types in same directory",
            "Use sequential IDs as filenames"
        ]
    },
    
    # ============================================
    # STORAGE STRATEGY
    # ============================================
    "storage": {
        "DO": [
            "Use cloud storage (S3/MinIO) for production",
            "Implement CDN for public files",
            "Enable versioning for critical files",
            "Set up lifecycle policies",
            "Use appropriate storage classes",
            "Implement backup strategy",
            "Monitor storage costs"
        ],
        "DON'T": [
            "Store everything on local disk",
            "Ignore storage costs",
            "Keep all files in hot storage",
            "Forget about backups",
            "Mix production and test data"
        ]
    },
    
    # ============================================
    # SECURITY
    # ============================================
    "security": {
        "DO": [
            "Scan all uploads for viruses",
            "Validate file types (content, not extension)",
            "Implement upload size limits",
            "Use signed URLs for private files",
            "Encrypt sensitive files",
            "Implement access controls",
            "Audit file access",
            "Quarantine suspicious files"
        ],
        "DON'T": [
            "Trust file extensions",
            "Skip virus scanning",
            "Serve files directly from storage",
            "Store API keys in files",
            "Allow unlimited uploads",
            "Ignore security alerts"
        ]
    },
    
    # ============================================
    # PERFORMANCE
    # ============================================
    "performance": {
        "DO": [
            "Optimize images automatically",
            "Generate multiple sizes/formats",
            "Use CDN for static files",
            "Implement caching headers",
            "Process uploads asynchronously",
            "Use streaming for large files",
            "Monitor performance metrics"
        ],
        "DON'T": [
            "Serve original unoptimized images",
            "Process large files synchronously",
            "Skip CDN integration",
            "Ignore caching",
            "Load entire file into memory"
        ]
    },
    
    # ============================================
    # QUOTA & LIMITS
    # ============================================
    "quotas": {
        "DO": [
            "Implement user storage quotas",
            "Enforce limits before upload",
            "Monitor quota usage",
            "Send warnings at thresholds",
            "Provide upgrade paths",
            "Track usage trends"
        ],
        "DON'T": [
            "Allow unlimited uploads",
            "Check quota after upload",
            "Ignore quota warnings",
            "Provide unclear error messages"
        ]
    },
    
    # ============================================
    # CLEANUP & MAINTENANCE
    # ============================================
    "cleanup": {
        "DO": [
            "Schedule regular cleanup tasks",
            "Remove orphaned files",
            "Purge old temp files",
            "Implement soft deletes",
            "Keep deleted files for grace period",
            "Deduplicate when beneficial",
            "Archive old files to cheaper storage"
        ],
        "DON'T": [
            "Never clean up files",
            "Delete files immediately",
            "Ignore orphaned files",
            "Keep duplicates indefinitely",
            "Store everything in hot storage"
        ]
    },
    
    # ============================================
    # MONITORING
    # ============================================
    "monitoring": {
        "DO": [
            "Track upload/download metrics",
            "Monitor storage usage",
            "Alert on quota thresholds",
            "Log all file operations",
            "Track error rates",
            "Monitor costs"
        ],
        "DON'T": [
            "Operate blindly",
            "Ignore metrics",
            "Skip error logging",
            "Forget about costs"
        ]
    }
}


# Storage size recommendations
STORAGE_LIMITS = {
    "file_types": {
        "images": {
            "max_size": "10 MB",
            "recommended_formats": ["JPEG", "PNG", "WebP"],
            "optimization": "Required"
        },
        "documents": {
            "max_size": "50 MB",
            "recommended_formats": ["PDF", "DOCX", "XLSX"],
            "virus_scan": "Required"
        },
        "videos": {
            "max_size": "500 MB",
            "recommended_formats": ["MP4", "WebM"],
            "processing": "Transcode to web-friendly formats"
        },
        "archives": {
            "max_size": "100 MB",
            "recommended_formats": ["ZIP", "TAR.GZ"],
            "virus_scan": "Required",
            "extract": "Optional"
        }
    },
    
    "user_quotas": {
        "free": "1 GB",
        "basic": "10 GB",
        "pro": "100 GB",
        "enterprise": "Unlimited"
    }
}


# Lifecycle recommendations
LIFECYCLE_POLICIES = {
    "active_files": {
        "storage_class": "STANDARD",
        "description": "Frequently accessed files",
        "retention": "Keep as long as active"
    },
    
    "archived_files": {
        "storage_class": "STANDARD_IA",
        "transition_after": "30-90 days",
        "description": "Infrequently accessed files",
        "cost_savings": "50% vs STANDARD"
    },
    
    "cold_storage": {
        "storage_class": "GLACIER",
        "transition_after": "180-365 days",
        "description": "Rarely accessed archives",
        "cost_savings": "80% vs STANDARD",
        "retrieval_time": "Minutes to hours"
    },
    
    "temp_files": {
        "expiration": "24 hours",
        "description": "Temporary uploads",
        "auto_delete": True
    }
}

📝 QUICK REFERENCE & CHECKLISTS
Daily Operations Checklist
markdown## Daily Storage Operations Checklist

### Morning Checks (5 min)

- [ ] Check storage usage dashboard
```bash
  curl http://localhost:8000/api/admin/storage/stats
```

- [ ] Review upload/download metrics
- [ ] Check for failed uploads
- [ ] Verify backup completion
- [ ] Review virus scan alerts

### Monitoring (Throughout Day)

- [ ] Monitor quota warnings
- [ ] Check error logs
```bash
  tail -f /var/log/app/storage.log | grep ERROR
```

- [ ] Track CDN cache hit rate
- [ ] Monitor storage costs

### End of Day (5 min)

- [ ] Review daily upload volume
- [ ] Check for quota threshold violations
- [ ] Verify cleanup tasks ran successfully
Weekly Maintenance Checklist
markdown## Weekly Storage Maintenance

### File Management

- [ ] Review orphaned files report
```bash
  GET /api/admin/cleanup/orphaned?days=90
```

- [ ] Check duplicate files
```bash
  GET /api/admin/cleanup/duplicates
```

- [ ] Purge old deleted files (30+ days)
```bash
  POST /api/admin/cleanup/deleted?days=30
```

- [ ] Review quarantine folder

### Performance

- [ ] Check image optimization queue
- [ ] Review CDN cache statistics
- [ ] Analyze slow upload/download reports
- [ ] Check storage tier distribution

### Security

- [ ] Review virus scan logs
- [ ] Check failed authentication attempts
- [ ] Audit file access logs
- [ ] Update virus definitions
```bash
  docker exec clamav freshclam
```

### Costs

- [ ] Review storage costs
- [ ] Check bandwidth usage
- [ ] Analyze storage tier distribution
- [ ] Identify cost optimization opportunities
Monthly Tasks Checklist
markdown## Monthly Storage Tasks

### Analysis & Reporting

- [ ] Generate comprehensive storage report
```bash
  GET /api/admin/quota/report
```

- [ ] Analyze growth trends
- [ ] Review user quota distribution
- [ ] Identify top storage users

### Optimization

- [ ] Run deduplication analysis
```bash
  POST /api/admin/cleanup/deduplicate?dry_run=true
```

- [ ] Review lifecycle policy effectiveness
- [ ] Optimize storage tier transitions
- [ ] Clean up old test data

### Capacity Planning

- [ ] Project next month's storage needs
- [ ] Review quota limits
- [ ] Plan infrastructure scaling
- [ ] Budget for next quarter

### Compliance

- [ ] Verify backup retention compliance
- [ ] Audit access controls
- [ ] Review data retention policies
- [ ] Update documentation
Emergency Procedures
markdown## Storage Emergency Procedures

### Quota Exceeded

1. **Immediate Action**
   - Identify user/org exceeding quota
   - Temporarily increase limit if justified
   - Contact user if needed

2. **Investigation**
   - Check for unusual upload patterns
   - Review file types/sizes
   - Look for duplicates

3. **Resolution**
   - Clean up duplicates
   - Remove temp files
   - Upgrade plan or enforce limits

### Storage Full

1. **Immediate Action**
   - Check available space
```bash
   df -h /var/app/storage
```
   - Free up space urgently
   - Disable uploads temporarily if needed

2. **Quick Wins**
   - Clean temp files
   - Purge old deleted files
   - Move to cheaper storage tier

3. **Long-term**
   - Add storage capacity
   - Implement lifecycle policies
   - Review growth projections

### Virus Detection

1. **Immediate Action**
   - Quarantine infected file
   - Block user if needed
   - Alert security team

2. **Investigation**
   - Review user's other uploads
   - Check upload patterns
   - Identify attack vector

3. **Prevention**
   - Update virus definitions
   - Review upload validation
   - Enhance monitoring

### Performance Issues

1. **Diagnosis**
   - Check storage latency
   - Review CDN hit rate
   - Monitor database queries
   - Check image optimization queue

2. **Quick Fixes**
   - Clear CDN cache if needed
   - Restart stuck workers
   - Scale processing capacity

3. **Optimization**
   - Review slow queries
   - Optimize image processing
   - Improve caching strategy
```

---

## 🎯 FINAL SUMMARY
```
┌──────────────────────────────────────────────────────────────┐
│         FILE STORAGE & MANAGEMENT - COMPLETE COVERAGE         │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ✅ Local File Storage                                       │
│     - Organized directory structure                          │
│     - Safe file naming                                       │
│     - Metadata tracking                                      │
│     - Database integration                                   │
│                                                              │
│  ✅ S3/MinIO Integration                                     │
│     - Complete S3 client implementation                      │
│     - MinIO Docker setup                                     │
│     - Presigned URLs                                         │
│     - Lifecycle management                                   │
│     - Storage factory pattern                                │
│                                                              │
│  ✅ File Upload Handling                                     │
│     - Single & multiple uploads                              │
│     - Chunked uploads for large files                        │
│     - Progress tracking                                      │
│     - Validation & sanitization                              │
│                                                              │
│  ✅ Image Optimization                                       │
│     - Pillow integration                                     │
│     - Automatic resizing                                     │
│     - Thumbnail generation                                   │
│     - Format conversion (WebP)                               │
│     - Watermarking                                           │
│     - Background processing                                  │
│                                                              │
│  ✅ CDN Integration                                          │
│     - CloudFront support                                     │
│     - Cloudflare support                                     │
│     - Signed URLs                                            │
│     - Cache invalidation                                     │
│     - Custom caching rules                                   │
│                                                              │
│  ✅ Virus Scanning                                           │
│     - ClamAV Docker setup                                    │
│     - Automatic scanning                                     │
│     - Quarantine system                                      │
│     - Real-time protection                                   │
│                                                              │
│  ✅ Storage Quotas                                           │
│     - User/org quota management                              │
│     - Tier-based limits                                      │
│     - Usage tracking                                         │
│     - Warning system                                         │
│     - Enforcement                                            │
│                                                              │
│  ✅ File Cleanup Strategies                                  │
│     - Orphaned file removal                                  │
│     - Temp file cleanup                                      │
│     - Soft delete purging                                    │
│     - Deduplication                                          │
│     - Lifecycle policies                                     │
│     - Automated maintenance                                  │
│                                                              │
│  ✅ Best Practices                                           │
│     - Organization guidelines                                │
│     - Security recommendations                               │
│     - Performance optimization                               │
│     - Cost management                                        │
│                                                              │
│  ✅ Operations & Maintenance                                 │
│     - Daily/weekly/monthly checklists                        │
│     - Emergency procedures                                   │
│     - Monitoring dashboards                                  │
│     - Reporting tools                                        │
│                                                              │
└──────────────────────────────────────────────────────────────┘