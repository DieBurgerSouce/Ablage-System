# Disaster Recovery Guide

**Comprehensive Disaster Recovery and Business Continuity Plan for Ablage System**

---

## Table of Contents

1. [Overview](#overview)
2. [Recovery Objectives](#recovery-objectives)
3. [Disaster Scenarios](#disaster-scenarios)
4. [Backup Strategy](#backup-strategy)
5. [Recovery Procedures](#recovery-procedures)
6. [Failover & High Availability](#failover--high-availability)
7. [Data Restoration](#data-restoration)
8. [Testing & Validation](#testing--validation)
9. [Incident Response](#incident-response)
10. [Communication Plan](#communication-plan)
11. [Post-Incident Review](#post-incident-review)

---

## Overview

### Purpose

This Disaster Recovery (DR) guide provides comprehensive procedures for recovering the Ablage System from various disaster scenarios, ensuring business continuity and minimizing data loss.

### Scope

This plan covers:
- **Infrastructure**: Servers, databases, storage, network
- **Data**: Documents, metadata, user data, configurations
- **Applications**: Backend services, frontend, worker processes
- **Personnel**: On-call engineers, escalation procedures

### Key Principles

1. **Prevention First**: Proactive measures to prevent disasters
2. **Multiple Backups**: Redundant backup systems (3-2-1 rule)
3. **Regular Testing**: Quarterly DR drills
4. **Clear Documentation**: Step-by-step recovery procedures
5. **Automation**: Automated backup and recovery where possible

---

## Recovery Objectives

### Recovery Time Objective (RTO)

**RTO** = Maximum acceptable downtime before business impact becomes critical

| Service Tier | RTO Target | Description |
|--------------|------------|-------------|
| **Tier 1 - Critical** | 1 hour | Authentication, document upload, core API |
| **Tier 2 - Important** | 4 hours | OCR processing, search, notifications |
| **Tier 3 - Standard** | 24 hours | Analytics, reporting, exports |
| **Tier 4 - Low Priority** | 72 hours | Archived data, historical logs |

### Recovery Point Objective (RPO)

**RPO** = Maximum acceptable data loss measured in time

| Data Type | RPO Target | Backup Frequency |
|-----------|------------|------------------|
| **Database (transactional)** | 5 minutes | Continuous WAL archiving |
| **Documents (S3)** | 15 minutes | Real-time replication |
| **User uploads (pending)** | 1 hour | Hourly snapshots |
| **Configurations** | 24 hours | Daily Git commits |
| **Logs** | 24 hours | Daily aggregation |

### Service Level Objectives (SLO)

```yaml
# slo.yaml
services:
  api:
    availability: 99.9%  # 43.2 minutes downtime/month
    rto: 1h
    rpo: 5m

  ocr_processing:
    availability: 99.5%  # 3.6 hours downtime/month
    rto: 4h
    rpo: 1h

  storage:
    availability: 99.99%  # 4.32 minutes downtime/month
    rto: 15m
    rpo: 15m
```

---

## Disaster Scenarios

### 1. Infrastructure Failures

#### Scenario: Single Server Failure

**Impact**: Partial service degradation

**Affected Services**:
- API endpoint unavailability
- Worker capacity reduction

**Recovery**:
1. Load balancer detects failure (30 seconds)
2. Traffic rerouted to healthy servers (automatic)
3. Alert sent to on-call engineer
4. Failed server investigated and replaced

**RTO**: 5 minutes (automatic failover)
**RPO**: 0 (no data loss)

#### Scenario: Database Server Failure

**Impact**: Complete service outage

**Affected Services**:
- All API endpoints
- Authentication
- Document processing

**Recovery**:
1. Automatic failover to standby replica (Patroni)
2. DNS updated to new primary
3. Application connections reconnect
4. Failed database investigated

**RTO**: 2-5 minutes (automatic)
**RPO**: 0-30 seconds (replication lag)

```python
# scripts/check_database_failover.py
import psycopg2
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_database_health(connection_string: str) -> bool:
    """Check if database is healthy and accepting connections."""
    try:
        conn = psycopg2.connect(connection_string)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return result[0] == 1
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False


def trigger_failover(patroni_api: str):
    """Trigger manual failover via Patroni API."""
    import requests

    response = requests.post(
        f"{patroni_api}/failover",
        json={"leader": None, "candidate": None}
    )

    if response.status_code == 200:
        logger.info("Failover triggered successfully")
    else:
        logger.error(f"Failover failed: {response.text}")


def wait_for_recovery(connection_string: str, timeout: int = 300):
    """Wait for database to become healthy after failover."""
    start_time = time.time()

    while time.time() - start_time < timeout:
        if check_database_health(connection_string):
            elapsed = time.time() - start_time
            logger.info(f"Database recovered in {elapsed:.2f} seconds")
            return True

        logger.info("Waiting for database recovery...")
        time.sleep(5)

    logger.error(f"Database did not recover within {timeout} seconds")
    return False


if __name__ == "__main__":
    PRIMARY_DB = "postgresql://user:pass@db-primary:5432/ablage"
    STANDBY_DB = "postgresql://user:pass@db-standby:5432/ablage"
    PATRONI_API = "http://patroni:8008"

    # Check primary health
    if not check_database_health(PRIMARY_DB):
        logger.warning("Primary database is unhealthy, triggering failover")
        trigger_failover(PATRONI_API)

        # Wait for standby to become new primary
        if wait_for_recovery(STANDBY_DB):
            logger.info("Failover completed successfully")
        else:
            logger.critical("Failover failed - manual intervention required")
```

#### Scenario: Complete Data Center Outage

**Impact**: Total service unavailability

**Affected Services**: All

**Recovery**:
1. Activate DR site (different geographic region)
2. Restore from latest backups
3. Update DNS to point to DR site
4. Verify all services operational

**RTO**: 4 hours
**RPO**: 15 minutes (last backup)

### 2. Data Loss Scenarios

#### Scenario: Accidental Data Deletion

**Impact**: User data loss

**Recovery**:
```bash
# Restore deleted documents from S3 versioning
aws s3api list-object-versions \
  --bucket ablage-documents \
  --prefix "user-123/" \
  --query 'DeleteMarkers[?IsLatest==`true`]'

# Restore specific version
aws s3api delete-object \
  --bucket ablage-documents \
  --key "user-123/document.pdf" \
  --version-id "delete-marker-id"

# Or restore from point-in-time backup
python scripts/restore_user_data.py \
  --user-id "123" \
  --timestamp "2025-01-15T10:30:00Z"
```

**RTO**: 30 minutes
**RPO**: 15 minutes

#### Scenario: Database Corruption

**Impact**: Data integrity issues

**Recovery**:
1. Stop all writes to database
2. Assess corruption extent
3. Restore from latest verified backup
4. Replay WAL logs to minimize data loss
5. Verify data integrity
6. Resume operations

**RTO**: 2-4 hours
**RPO**: 5 minutes (WAL replay)

```bash
# scripts/restore_database_from_backup.sh
#!/bin/bash
set -e

BACKUP_DATE=$1
BACKUP_PATH="/backups/postgres/${BACKUP_DATE}"
PGDATA="/var/lib/postgresql/data"

if [ -z "$BACKUP_DATE" ]; then
    echo "Usage: $0 <backup-date>"
    echo "Example: $0 2025-01-15"
    exit 1
fi

echo "=== Database Restoration from Backup ==="
echo "Backup date: $BACKUP_DATE"
echo "Backup path: $BACKUP_PATH"

# 1. Stop PostgreSQL
echo "Stopping PostgreSQL..."
systemctl stop postgresql

# 2. Backup current data (just in case)
echo "Backing up current data directory..."
mv $PGDATA ${PGDATA}.backup.$(date +%s)

# 3. Restore base backup
echo "Restoring base backup..."
tar -xzf ${BACKUP_PATH}/base.tar.gz -C /var/lib/postgresql/

# 4. Restore WAL files
echo "Restoring WAL files..."
mkdir -p ${PGDATA}/pg_wal
tar -xzf ${BACKUP_PATH}/wal.tar.gz -C ${PGDATA}/pg_wal/

# 5. Create recovery configuration
echo "Creating recovery configuration..."
cat > ${PGDATA}/recovery.signal <<EOF
restore_command = 'cp ${BACKUP_PATH}/wal/%f %p'
recovery_target_time = '$(date -d "${BACKUP_DATE} 23:59:59" +"%Y-%m-%d %H:%M:%S")'
recovery_target_action = 'promote'
EOF

# 6. Fix permissions
echo "Fixing permissions..."
chown -R postgres:postgres $PGDATA
chmod 700 $PGDATA

# 7. Start PostgreSQL in recovery mode
echo "Starting PostgreSQL in recovery mode..."
systemctl start postgresql

# 8. Wait for recovery to complete
echo "Waiting for recovery to complete..."
until pg_isready -h localhost -p 5432; do
    echo "PostgreSQL is recovering..."
    sleep 5
done

# 9. Verify recovery
echo "Verifying recovery..."
psql -U postgres -c "SELECT pg_is_in_recovery();"
psql -U postgres -d ablage_system -c "SELECT COUNT(*) FROM documents;"

echo "=== Database restoration completed ==="
```

### 3. Security Incidents

#### Scenario: Ransomware Attack

**Impact**: Encrypted data, system compromise

**Response**:
1. **Immediate**: Isolate affected systems
2. **Assess**: Determine encryption extent
3. **Restore**: From offline backups
4. **Investigate**: Root cause analysis
5. **Harden**: Security improvements

**RTO**: 24 hours
**RPO**: 24 hours (offline backup)

```python
# scripts/emergency_isolation.py
"""
Emergency system isolation script.
Use when security breach is detected.
"""
import subprocess
import logging
from typing import List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def block_all_traffic(server_ips: List[str]):
    """Block all incoming/outgoing traffic to affected servers."""
    for ip in server_ips:
        logger.warning(f"Blocking traffic to {ip}")

        # Block via iptables
        subprocess.run([
            "ssh", f"root@{ip}",
            "iptables", "-P", "INPUT", "DROP",
            "&&",
            "iptables", "-P", "OUTPUT", "DROP",
            "&&",
            "iptables", "-P", "FORWARD", "DROP"
        ])


def snapshot_for_forensics(server_ips: List[str]):
    """Create snapshots for forensic analysis."""
    for ip in server_ips:
        logger.info(f"Creating forensic snapshot of {ip}")

        # Create disk snapshot (AWS example)
        subprocess.run([
            "aws", "ec2", "create-snapshot",
            "--volume-id", f"vol-{ip}",
            "--description", f"Forensic snapshot - {ip}",
            "--tag-specifications",
            "ResourceType=snapshot,Tags=[{Key=Purpose,Value=Forensics}]"
        ])


def isolate_database():
    """Isolate database from application servers."""
    logger.critical("Isolating database from all connections")

    # Terminate all connections except superuser
    query = """
    SELECT pg_terminate_backend(pid)
    FROM pg_stat_activity
    WHERE datname = 'ablage_system'
      AND pid <> pg_backend_pid()
      AND usename != 'postgres';
    """

    subprocess.run([
        "psql", "-U", "postgres", "-c", query
    ])

    # Disable remote connections
    subprocess.run([
        "sed", "-i",
        "s/host.*all.*all.*0.0.0.0\\/0.*md5/# DISABLED/g",
        "/etc/postgresql/14/main/pg_hba.conf"
    ])

    # Reload PostgreSQL
    subprocess.run(["systemctl", "reload", "postgresql"])


def notify_security_team():
    """Send emergency notification to security team."""
    logger.critical("Sending emergency notification")

    # Use PagerDuty API
    import requests

    requests.post(
        "https://events.pagerduty.com/v2/enqueue",
        json={
            "routing_key": "YOUR_PAGERDUTY_KEY",
            "event_action": "trigger",
            "payload": {
                "summary": "CRITICAL: Security incident - System isolated",
                "severity": "critical",
                "source": "ablage-system-dr",
            }
        }
    )


if __name__ == "__main__":
    AFFECTED_SERVERS = [
        "10.0.1.10",  # API server 1
        "10.0.1.11",  # API server 2
        "10.0.2.10",  # Worker 1
    ]

    logger.critical("=== EMERGENCY ISOLATION INITIATED ===")

    # 1. Block network traffic
    block_all_traffic(AFFECTED_SERVERS)

    # 2. Create forensic snapshots
    snapshot_for_forensics(AFFECTED_SERVERS)

    # 3. Isolate database
    isolate_database()

    # 4. Notify security team
    notify_security_team()

    logger.critical("=== ISOLATION COMPLETE ===")
    logger.critical("Manual investigation required before restoration")
```

### 4. Natural Disasters

#### Scenario: Regional Disaster (Fire, Flood, Earthquake)

**Impact**: Complete data center loss

**Recovery**:
1. Activate geographic DR site
2. Restore from off-site backups
3. Redirect traffic via DNS/CDN
4. Verify service restoration

**RTO**: 8 hours
**RPO**: 1 hour (cross-region replication)

---

## Backup Strategy

### Backup Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    PRODUCTION ENVIRONMENT                │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  PostgreSQL  │  │   MinIO/S3   │  │    Redis     │  │
│  │   (Primary)  │  │  (Documents) │  │   (Cache)    │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
│         │                 │                  │          │
└─────────┼─────────────────┼──────────────────┼──────────┘
          │                 │                  │
          ▼                 ▼                  ▼
┌─────────────────────────────────────────────────────────┐
│                    BACKUP LAYER 1                        │
│                  (Same Data Center)                      │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   Standby    │  │  S3 Bucket   │  │   Redis      │  │
│  │   Replica    │  │  Versioning  │  │   Persist    │  │
│  │ (Streaming)  │  │   Enabled    │  │    (AOF)     │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────────┘  │
│         │                 │                             │
└─────────┼─────────────────┼─────────────────────────────┘
          │                 │
          ▼                 ▼
┌─────────────────────────────────────────────────────────┐
│                    BACKUP LAYER 2                        │
│               (Different Data Center)                    │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐                     │
│  │  Daily Full  │  │Cross-Region  │                     │
│  │   Backups    │  │ Replication  │                     │
│  │  (pg_dump)   │  │ (S3 → S3)    │                     │
│  └──────┬───────┘  └──────┬───────┘                     │
│         │                 │                             │
└─────────┼─────────────────┼─────────────────────────────┘
          │                 │
          ▼                 ▼
┌─────────────────────────────────────────────────────────┐
│                    BACKUP LAYER 3                        │
│                  (Offline/Tape/Glacier)                  │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐                     │
│  │   Monthly    │  │   S3 Deep    │                     │
│  │   Archive    │  │   Archive    │                     │
│  │   (Tape)     │  │  (Glacier)   │                     │
│  └──────────────┘  └──────────────┘                     │
└─────────────────────────────────────────────────────────┘
```

### Backup Schedule

#### PostgreSQL Database

```yaml
# PostgreSQL Backup Configuration
backups:
  continuous:
    type: WAL_archiving
    frequency: continuous
    retention: 7_days
    destination: s3://ablage-backups/wal/

  incremental:
    type: pg_basebackup
    frequency: hourly
    retention: 24_hours
    destination: s3://ablage-backups/incremental/

  full:
    type: pg_dump
    frequency: daily
    time: "02:00_UTC"
    retention: 30_days
    destination: s3://ablage-backups/full/
    compression: gzip

  archive:
    type: pg_dump
    frequency: monthly
    retention: 12_months
    destination: s3://ablage-backups-glacier/monthly/
    storage_class: GLACIER
```

**Implementation:**

```bash
# scripts/backup_database.sh
#!/bin/bash
set -euo pipefail

# Configuration
BACKUP_TYPE="${1:-full}"  # full, incremental, wal
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/var/backups/postgres"
S3_BUCKET="s3://ablage-backups"
DB_NAME="ablage_system"
DB_USER="postgres"

# Create backup directory
mkdir -p ${BACKUP_DIR}

case $BACKUP_TYPE in
    full)
        echo "Creating full database backup..."
        BACKUP_FILE="${BACKUP_DIR}/full_${DB_NAME}_${TIMESTAMP}.sql.gz"

        # Full database dump with compression
        pg_dump -U ${DB_USER} -d ${DB_NAME} \
            --format=custom \
            --compress=9 \
            --verbose \
            --file=${BACKUP_FILE}

        # Calculate checksum
        sha256sum ${BACKUP_FILE} > ${BACKUP_FILE}.sha256

        # Upload to S3
        aws s3 cp ${BACKUP_FILE} ${S3_BUCKET}/full/
        aws s3 cp ${BACKUP_FILE}.sha256 ${S3_BUCKET}/full/

        echo "Full backup completed: ${BACKUP_FILE}"
        ;;

    incremental)
        echo "Creating incremental backup..."
        BACKUP_FILE="${BACKUP_DIR}/incremental_${TIMESTAMP}.tar.gz"

        # Base backup for PITR
        pg_basebackup -U ${DB_USER} \
            --pgdata=- \
            --format=tar \
            --gzip \
            --progress \
            --checkpoint=fast \
            > ${BACKUP_FILE}

        # Upload to S3
        aws s3 cp ${BACKUP_FILE} ${S3_BUCKET}/incremental/

        echo "Incremental backup completed: ${BACKUP_FILE}"
        ;;

    wal)
        echo "Archiving WAL files..."

        # Archive WAL files (called by PostgreSQL)
        WAL_FILE=$2
        WAL_PATH="${BACKUP_DIR}/wal/${WAL_FILE}"

        # Copy WAL file
        cp ${PGDATA}/pg_wal/${WAL_FILE} ${WAL_PATH}

        # Upload to S3
        aws s3 cp ${WAL_PATH} ${S3_BUCKET}/wal/

        echo "WAL archived: ${WAL_FILE}"
        ;;

    *)
        echo "Unknown backup type: $BACKUP_TYPE"
        exit 1
        ;;
esac

# Cleanup old local backups (keep last 7 days)
find ${BACKUP_DIR} -type f -mtime +7 -delete

# Verify backup integrity
if [ "$BACKUP_TYPE" == "full" ]; then
    echo "Verifying backup integrity..."
    sha256sum -c ${BACKUP_FILE}.sha256
fi

echo "Backup process completed successfully"
```

#### S3/MinIO Documents

```python
# scripts/backup_s3_documents.py
"""
S3 document backup with versioning and cross-region replication.
"""
import boto3
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class S3BackupManager:
    def __init__(self):
        self.s3 = boto3.client('s3')
        self.source_bucket = 'ablage-documents'
        self.backup_bucket = 'ablage-documents-backup'
        self.archive_bucket = 'ablage-documents-glacier'

    def enable_versioning(self):
        """Enable versioning on source bucket."""
        logger.info(f"Enabling versioning on {self.source_bucket}")

        self.s3.put_bucket_versioning(
            Bucket=self.source_bucket,
            VersioningConfiguration={'Status': 'Enabled'}
        )

    def setup_lifecycle_policy(self):
        """Configure lifecycle policy for automatic archival."""
        logger.info("Configuring lifecycle policy")

        lifecycle_policy = {
            'Rules': [
                {
                    'Id': 'TransitionOldVersions',
                    'Status': 'Enabled',
                    'NoncurrentVersionTransitions': [
                        {
                            'NoncurrentDays': 30,
                            'StorageClass': 'STANDARD_IA'
                        },
                        {
                            'NoncurrentDays': 90,
                            'StorageClass': 'GLACIER'
                        }
                    ]
                },
                {
                    'Id': 'DeleteOldVersions',
                    'Status': 'Enabled',
                    'NoncurrentVersionExpiration': {
                        'NoncurrentDays': 365
                    }
                }
            ]
        }

        self.s3.put_bucket_lifecycle_configuration(
            Bucket=self.source_bucket,
            LifecycleConfiguration=lifecycle_policy
        )

    def create_snapshot(self):
        """Create point-in-time snapshot to backup bucket."""
        logger.info("Creating S3 snapshot")

        # List all objects
        paginator = self.s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=self.source_bucket)

        total = 0
        for page in pages:
            for obj in page.get('Contents', []):
                key = obj['Key']

                # Copy to backup bucket
                copy_source = {
                    'Bucket': self.source_bucket,
                    'Key': key
                }

                self.s3.copy_object(
                    CopySource=copy_source,
                    Bucket=self.backup_bucket,
                    Key=key
                )

                total += 1
                if total % 1000 == 0:
                    logger.info(f"Copied {total} objects")

        logger.info(f"Snapshot completed: {total} objects copied")

    def restore_from_version(self, key: str, version_id: str):
        """Restore specific version of object."""
        logger.info(f"Restoring {key} version {version_id}")

        # Get versioned object
        obj = self.s3.get_object(
            Bucket=self.source_bucket,
            Key=key,
            VersionId=version_id
        )

        # Restore as current version
        self.s3.put_object(
            Bucket=self.source_bucket,
            Key=key,
            Body=obj['Body'].read()
        )

        logger.info(f"Restored {key}")

    def list_deleted_objects(self, days: int = 7):
        """List objects deleted in last N days."""
        cutoff = datetime.now() - timedelta(days=days)

        deleted = []

        # List object versions
        paginator = self.s3.get_paginator('list_object_versions')
        pages = paginator.paginate(Bucket=self.source_bucket)

        for page in pages:
            for marker in page.get('DeleteMarkers', []):
                if marker['LastModified'] > cutoff:
                    deleted.append({
                        'Key': marker['Key'],
                        'VersionId': marker['VersionId'],
                        'DeletedAt': marker['LastModified']
                    })

        return deleted


if __name__ == "__main__":
    manager = S3BackupManager()

    # Setup
    manager.enable_versioning()
    manager.setup_lifecycle_policy()

    # Create daily snapshot
    manager.create_snapshot()

    # List recently deleted objects
    deleted = manager.list_deleted_objects(days=7)
    logger.info(f"Found {len(deleted)} deleted objects in last 7 days")
```

#### Configuration Backups

```bash
# scripts/backup_configurations.sh
#!/bin/bash
set -e

BACKUP_DIR="/var/backups/configs"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/configs_${TIMESTAMP}.tar.gz"

mkdir -p ${BACKUP_DIR}

echo "Backing up configurations..."

# Create temporary directory
TEMP_DIR=$(mktemp -d)

# Copy configurations
cp -r /etc/nginx ${TEMP_DIR}/
cp -r /etc/postgresql ${TEMP_DIR}/
cp -r /etc/redis ${TEMP_DIR}/
cp /etc/environment ${TEMP_DIR}/
cp ~/.env ${TEMP_DIR}/app.env

# Backup systemd services
mkdir -p ${TEMP_DIR}/systemd
cp /etc/systemd/system/ablage-*.service ${TEMP_DIR}/systemd/

# Backup SSL certificates
mkdir -p ${TEMP_DIR}/ssl
cp -r /etc/letsencrypt ${TEMP_DIR}/ssl/

# Create archive
tar -czf ${BACKUP_FILE} -C ${TEMP_DIR} .

# Upload to Git repository
cd ${TEMP_DIR}
git init
git add .
git commit -m "Config backup ${TIMESTAMP}"
git push origin main

# Upload to S3
aws s3 cp ${BACKUP_FILE} s3://ablage-backups/configs/

# Cleanup
rm -rf ${TEMP_DIR}

echo "Configuration backup completed: ${BACKUP_FILE}"
```

### Backup Verification

```python
# scripts/verify_backups.py
"""
Automated backup verification and integrity checking.
"""
import boto3
import hashlib
import psycopg2
import tempfile
import subprocess
from datetime import datetime, timedelta


class BackupVerifier:
    def __init__(self):
        self.s3 = boto3.client('s3')

    def verify_database_backup(self, backup_file: str) -> bool:
        """Verify database backup can be restored."""
        print(f"Verifying database backup: {backup_file}")

        try:
            # Download backup
            with tempfile.NamedTemporaryFile(suffix='.sql.gz') as tmp:
                self.s3.download_file(
                    'ablage-backups',
                    f'full/{backup_file}',
                    tmp.name
                )

                # Verify checksum
                checksum_file = f'{backup_file}.sha256'
                self.s3.download_file(
                    'ablage-backups',
                    f'full/{checksum_file}',
                    f'{tmp.name}.sha256'
                )

                # Calculate checksum
                sha256 = hashlib.sha256()
                with open(tmp.name, 'rb') as f:
                    for chunk in iter(lambda: f.read(4096), b''):
                        sha256.update(chunk)

                calculated = sha256.hexdigest()

                # Compare with stored checksum
                with open(f'{tmp.name}.sha256', 'r') as f:
                    expected = f.read().split()[0]

                if calculated != expected:
                    print(f"❌ Checksum mismatch: {calculated} != {expected}")
                    return False

                print("✓ Checksum verified")

                # Test restore to temporary database
                result = subprocess.run([
                    'pg_restore',
                    '--dbname=postgres',
                    '--create',
                    '--clean',
                    '--if-exists',
                    tmp.name
                ], capture_output=True)

                if result.returncode != 0:
                    print(f"❌ Restore test failed: {result.stderr}")
                    return False

                print("✓ Restore test successful")
                return True

        except Exception as e:
            print(f"❌ Verification failed: {e}")
            return False

    def verify_s3_replication(self) -> bool:
        """Verify S3 cross-region replication is working."""
        print("Verifying S3 replication...")

        source_bucket = 'ablage-documents'
        replica_bucket = 'ablage-documents-backup'

        # List objects in source
        source_objects = set()
        paginator = self.s3.get_paginator('list_objects_v2')

        for page in paginator.paginate(Bucket=source_bucket):
            for obj in page.get('Contents', []):
                source_objects.add(obj['Key'])

        # List objects in replica
        replica_objects = set()
        for page in paginator.paginate(Bucket=replica_bucket):
            for obj in page.get('Contents', []):
                replica_objects.add(obj['Key'])

        # Compare
        missing = source_objects - replica_objects

        if missing:
            print(f"❌ {len(missing)} objects not replicated")
            for key in list(missing)[:10]:  # Show first 10
                print(f"  - {key}")
            return False

        print(f"✓ All {len(source_objects)} objects replicated")
        return True

    def run_verification_suite(self):
        """Run complete verification suite."""
        print("=== Backup Verification Suite ===\n")

        results = {}

        # Verify last 3 database backups
        print("1. Database Backups")
        # Get recent backups
        response = self.s3.list_objects_v2(
            Bucket='ablage-backups',
            Prefix='full/'
        )

        backups = sorted(
            response.get('Contents', []),
            key=lambda x: x['LastModified'],
            reverse=True
        )[:3]

        for backup in backups:
            filename = backup['Key'].split('/')[-1]
            results[f'db_{filename}'] = self.verify_database_backup(filename)

        # Verify S3 replication
        print("\n2. S3 Replication")
        results['s3_replication'] = self.verify_s3_replication()

        # Summary
        print("\n=== Verification Summary ===")
        passed = sum(1 for v in results.values() if v)
        total = len(results)

        print(f"Passed: {passed}/{total}")

        for test, result in results.items():
            status = "✓ PASS" if result else "❌ FAIL"
            print(f"{status} - {test}")

        return all(results.values())


if __name__ == "__main__":
    verifier = BackupVerifier()
    success = verifier.run_verification_suite()

    exit(0 if success else 1)
```

---

## Recovery Procedures

### Database Recovery

#### Full Database Restore

```bash
# 1. Stop application servers
kubectl scale deployment ablage-api --replicas=0

# 2. Stop database writes
psql -U postgres -c "
  SELECT pg_terminate_backend(pid)
  FROM pg_stat_activity
  WHERE datname = 'ablage_system'
    AND pid <> pg_backend_pid();
"

# 3. Download backup
BACKUP_DATE="2025-01-15"
aws s3 cp \
  s3://ablage-backups/full/full_ablage_system_${BACKUP_DATE}.sql.gz \
  /tmp/backup.sql.gz

# 4. Verify checksum
aws s3 cp \
  s3://ablage-backups/full/full_ablage_system_${BACKUP_DATE}.sql.gz.sha256 \
  /tmp/backup.sql.gz.sha256

sha256sum -c /tmp/backup.sql.gz.sha256

# 5. Drop existing database
dropdb -U postgres ablage_system

# 6. Restore from backup
gunzip -c /tmp/backup.sql.gz | psql -U postgres

# 7. Verify restoration
psql -U postgres -d ablage_system -c "
  SELECT
    (SELECT COUNT(*) FROM users) as users,
    (SELECT COUNT(*) FROM documents) as documents,
    (SELECT COUNT(*) FROM ocr_results) as ocr_results;
"

# 8. Restart application
kubectl scale deployment ablage-api --replicas=3

# 9. Monitor logs
kubectl logs -f deployment/ablage-api
```

#### Point-in-Time Recovery

```bash
# scripts/point_in_time_recovery.sh
#!/bin/bash
set -e

TARGET_TIME=$1  # Format: "2025-01-15 14:30:00"

if [ -z "$TARGET_TIME" ]; then
    echo "Usage: $0 'YYYY-MM-DD HH:MM:SS'"
    exit 1
fi

echo "=== Point-in-Time Recovery ==="
echo "Target time: $TARGET_TIME"

# 1. Find closest base backup before target time
echo "Finding appropriate base backup..."
BACKUP_DATE=$(date -d "$TARGET_TIME" +%Y%m%d)
BACKUP_FILE="full_ablage_system_${BACKUP_DATE}.sql.gz"

# 2. Stop PostgreSQL
echo "Stopping PostgreSQL..."
systemctl stop postgresql

# 3. Restore base backup
echo "Restoring base backup..."
bash scripts/restore_database_from_backup.sh $BACKUP_DATE

# 4. Configure recovery target
echo "Configuring recovery target..."
cat >> /var/lib/postgresql/data/postgresql.conf <<EOF
recovery_target_time = '$TARGET_TIME'
recovery_target_action = 'promote'
EOF

# 5. Start PostgreSQL for recovery
echo "Starting recovery..."
systemctl start postgresql

# 6. Wait for recovery
echo "Waiting for recovery to complete..."
until pg_isready; do
    sleep 5
done

# 7. Verify recovery point
echo "Verifying recovery point..."
psql -U postgres -d ablage_system -c "
  SELECT pg_last_xact_replay_timestamp();
"

echo "=== Recovery completed ==="
```

### Application Recovery

```yaml
# kubernetes/disaster-recovery.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: dr-procedures
data:
  api-recovery.sh: |
    #!/bin/bash
    # API Server Recovery

    echo "Recovering API servers..."

    # 1. Update database connection
    kubectl create secret generic db-connection \
      --from-literal=url="postgresql://user:pass@db-new:5432/ablage_system" \
      --dry-run=client -o yaml | kubectl apply -f -

    # 2. Scale up deployment
    kubectl scale deployment ablage-api --replicas=3

    # 3. Wait for readiness
    kubectl wait --for=condition=ready pod -l app=ablage-api --timeout=300s

    # 4. Verify health
    for i in {1..5}; do
      kubectl exec deploy/ablage-api -- curl -f http://localhost:8000/health
      sleep 10
    done

    echo "API recovery completed"

  worker-recovery.sh: |
    #!/bin/bash
    # Celery Worker Recovery

    echo "Recovering Celery workers..."

    # 1. Clear Redis queue (if needed)
    kubectl exec deploy/redis -- redis-cli FLUSHDB

    # 2. Scale up workers
    kubectl scale deployment ablage-worker --replicas=5

    # 3. Verify workers are consuming
    kubectl logs -f deploy/ablage-worker --tail=50

    echo "Worker recovery completed"
```

### DNS & Traffic Failover

```python
# scripts/failover_dns.py
"""
Automatic DNS failover to DR site.
"""
import boto3
from typing import List


class DNSFailoverManager:
    def __init__(self):
        self.route53 = boto3.client('route53')
        self.hosted_zone_id = 'Z1234567890ABC'

    def update_record(
        self,
        record_name: str,
        record_type: str,
        new_values: List[str],
        ttl: int = 60
    ):
        """Update DNS record to point to new servers."""
        print(f"Updating {record_name} to {new_values}")

        change_batch = {
            'Changes': [{
                'Action': 'UPSERT',
                'ResourceRecordSet': {
                    'Name': record_name,
                    'Type': record_type,
                    'TTL': ttl,
                    'ResourceRecords': [
                        {'Value': value} for value in new_values
                    ]
                }
            }]
        }

        response = self.route53.change_resource_record_sets(
            HostedZoneId=self.hosted_zone_id,
            ChangeBatch=change_batch
        )

        change_id = response['ChangeInfo']['Id']
        print(f"DNS update initiated: {change_id}")

        # Wait for propagation
        waiter = self.route53.get_waiter('resource_record_sets_changed')
        waiter.wait(Id=change_id)

        print("DNS update completed")

    def failover_to_dr_site(self):
        """Failover all services to DR site."""
        print("=== DNS Failover to DR Site ===")

        # API servers
        self.update_record(
            'api.ablage-system.com',
            'A',
            ['10.20.1.10', '10.20.1.11', '10.20.1.12']  # DR IPs
        )

        # Frontend
        self.update_record(
            'app.ablage-system.com',
            'CNAME',
            ['dr-frontend.cloudfront.net']
        )

        # Database (if publicly accessible)
        self.update_record(
            'db.ablage-system.com',
            'A',
            ['10.20.2.10']  # DR database
        )

        print("Failover completed")

    def failback_to_primary(self):
        """Failback to primary site."""
        print("=== DNS Failback to Primary Site ===")

        # API servers
        self.update_record(
            'api.ablage-system.com',
            'A',
            ['10.10.1.10', '10.10.1.11', '10.10.1.12']  # Primary IPs
        )

        # Frontend
        self.update_record(
            'app.ablage-system.com',
            'CNAME',
            ['primary-frontend.cloudfront.net']
        )

        # Database
        self.update_record(
            'db.ablage-system.com',
            'A',
            ['10.10.2.10']  # Primary database
        )

        print("Failback completed")


if __name__ == "__main__":
    import sys

    manager = DNSFailoverManager()

    if len(sys.argv) < 2:
        print("Usage: python failover_dns.py [failover|failback]")
        sys.exit(1)

    action = sys.argv[1]

    if action == 'failover':
        manager.failover_to_dr_site()
    elif action == 'failback':
        manager.failback_to_primary()
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)
```

---

## Failover & High Availability

### Database High Availability

**Architecture**: PostgreSQL with Patroni + etcd

```yaml
# patroni.yml
scope: ablage-cluster
name: postgres-1

restapi:
  listen: 0.0.0.0:8008
  connect_address: 10.0.1.10:8008

etcd:
  hosts:
    - 10.0.3.10:2379
    - 10.0.3.11:2379
    - 10.0.3.12:2379

bootstrap:
  dcs:
    ttl: 30
    loop_wait: 10
    retry_timeout: 10
    maximum_lag_on_failover: 1048576

    postgresql:
      use_pg_rewind: true
      parameters:
        max_connections: 200
        shared_buffers: 4GB
        effective_cache_size: 12GB
        wal_level: replica
        max_wal_senders: 10
        max_replication_slots: 10

  initdb:
    - encoding: UTF8
    - data-checksums

postgresql:
  listen: 0.0.0.0:5432
  connect_address: 10.0.1.10:5432
  data_dir: /var/lib/postgresql/14/main
  bin_dir: /usr/lib/postgresql/14/bin

  authentication:
    replication:
      username: replicator
      password: repl_password
    superuser:
      username: postgres
      password: postgres_password

  parameters:
    unix_socket_directories: '/var/run/postgresql'
```

### Load Balancer Configuration

```nginx
# /etc/nginx/conf.d/ablage-ha.conf
upstream ablage_api {
    least_conn;  # Connection-based load balancing

    server 10.0.1.10:8000 max_fails=3 fail_timeout=30s;
    server 10.0.1.11:8000 max_fails=3 fail_timeout=30s;
    server 10.0.1.12:8000 max_fails=3 fail_timeout=30s;

    # Health check
    check interval=3000 rise=2 fall=3 timeout=1000 type=http;
    check_http_send "GET /health HTTP/1.0\r\n\r\n";
    check_http_expect_alive http_2xx http_3xx;
}

server {
    listen 443 ssl http2;
    server_name api.ablage-system.com;

    # SSL configuration
    ssl_certificate /etc/letsencrypt/live/ablage-system.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ablage-system.com/privkey.pem;

    # Load balancing
    location / {
        proxy_pass http://ablage_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts
        proxy_connect_timeout 10s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;

        # Retry failed requests
        proxy_next_upstream error timeout http_500 http_502 http_503;
        proxy_next_upstream_tries 2;
    }
}
```

---

## Testing & Validation

### DR Drill Schedule

| Quarter | Scenario | Duration | Participants |
|---------|----------|----------|--------------|
| **Q1** | Database Failover | 2 hours | Platform Team |
| **Q2** | Regional Disaster | 4 hours | All Teams |
| **Q3** | Ransomware Response | 3 hours | Security + Platform |
| **Q4** | Complete DR Site Activation | 8 hours | All Teams |

### DR Drill Procedure

```markdown
# DR Drill Checklist

## Pre-Drill (T-1 week)

- [ ] Schedule drill with all teams
- [ ] Notify customers (if production test)
- [ ] Prepare test data
- [ ] Review procedures
- [ ] Assign roles

## Drill Execution

- [ ] T+0:00 - Incident declared
- [ ] T+0:05 - On-call notified
- [ ] T+0:10 - Incident commander assigned
- [ ] T+0:15 - Assessment complete
- [ ] T+0:30 - Recovery initiated
- [ ] T+1:00 - Primary service restored
- [ ] T+2:00 - All services verified

## Post-Drill

- [ ] Document timeline
- [ ] Identify gaps
- [ ] Update procedures
- [ ] Schedule follow-up
```

### Automated Testing

```python
# scripts/test_disaster_recovery.py
"""
Automated DR testing suite.
"""
import time
import requests
from typing import Dict, List


class DRTester:
    def __init__(self, primary_url: str, dr_url: str):
        self.primary_url = primary_url
        self.dr_url = dr_url

    def test_database_failover(self) -> Dict:
        """Test database automatic failover."""
        print("Testing database failover...")

        results = {
            'test': 'database_failover',
            'steps': [],
            'success': False
        }

        # 1. Verify primary is healthy
        response = requests.get(f"{self.primary_url}/health")
        results['steps'].append({
            'step': 'primary_health_check',
            'success': response.status_code == 200
        })

        # 2. Simulate primary failure
        print("Simulating primary database failure...")
        # (In real test, would stop primary database)
        time.sleep(5)

        # 3. Verify automatic failover
        start_time = time.time()
        failover_detected = False

        while time.time() - start_time < 60:  # 1 minute timeout
            try:
                response = requests.get(f"{self.primary_url}/health")
                if response.json().get('database') == 'healthy':
                    failover_detected = True
                    break
            except:
                pass
            time.sleep(1)

        failover_time = time.time() - start_time
        results['steps'].append({
            'step': 'automatic_failover',
            'success': failover_detected,
            'duration_seconds': failover_time
        })

        results['success'] = all(s['success'] for s in results['steps'])
        return results

    def test_dr_site_activation(self) -> Dict:
        """Test complete DR site activation."""
        print("Testing DR site activation...")

        results = {
            'test': 'dr_site_activation',
            'steps': [],
            'success': False
        }

        # 1. Verify DR site is ready
        try:
            response = requests.get(f"{self.dr_url}/health", timeout=5)
            dr_ready = response.status_code == 200
        except:
            dr_ready = False

        results['steps'].append({
            'step': 'dr_site_ready',
            'success': dr_ready
        })

        if not dr_ready:
            results['success'] = False
            return results

        # 2. Test data replication
        # Create test document on primary
        test_doc = {
            'filename': 'dr-test.pdf',
            'content': 'DR Test Document'
        }

        response = requests.post(
            f"{self.primary_url}/documents/upload",
            json=test_doc
        )
        doc_id = response.json()['id']

        # Wait for replication
        time.sleep(30)

        # Verify on DR site
        response = requests.get(f"{self.dr_url}/documents/{doc_id}")
        data_replicated = response.status_code == 200

        results['steps'].append({
            'step': 'data_replication',
            'success': data_replicated
        })

        # 3. Test failover
        # Switch traffic to DR site (DNS update)
        # (In real test, would update DNS)

        # 4. Verify DR site handles load
        responses = []
        for i in range(100):
            try:
                r = requests.get(f"{self.dr_url}/health", timeout=1)
                responses.append(r.status_code == 200)
            except:
                responses.append(False)

        load_handled = sum(responses) / len(responses) > 0.95

        results['steps'].append({
            'step': 'dr_site_load_handling',
            'success': load_handled,
            'success_rate': sum(responses) / len(responses)
        })

        results['success'] = all(s['success'] for s in results['steps'])
        return results

    def run_test_suite(self) -> List[Dict]:
        """Run complete DR test suite."""
        print("=== DR Test Suite ===\n")

        results = []

        # Test 1: Database Failover
        results.append(self.test_database_failover())

        # Test 2: DR Site Activation
        results.append(self.test_dr_site_activation())

        # Summary
        print("\n=== Test Summary ===")
        for result in results:
            status = "✓ PASS" if result['success'] else "❌ FAIL"
            print(f"{status} - {result['test']}")

            for step in result['steps']:
                step_status = "✓" if step['success'] else "❌"
                print(f"  {step_status} {step['step']}")

        return results


if __name__ == "__main__":
    tester = DRTester(
        primary_url="https://api.ablage-system.com",
        dr_url="https://dr-api.ablage-system.com"
    )

    results = tester.run_test_suite()

    # Exit with error if any test failed
    exit(0 if all(r['success'] for r in results) else 1)
```

---

## Incident Response

### Incident Response Team

| Role | Primary | Backup | Responsibilities |
|------|---------|--------|------------------|
| **Incident Commander** | Platform Lead | Senior Engineer | Overall coordination |
| **Technical Lead** | Senior Engineer | DevOps Lead | Technical decisions |
| **Communications Lead** | Product Manager | Support Lead | Customer communication |
| **Database Expert** | DBA | Backend Lead | Database recovery |
| **Infrastructure Expert** | DevOps Engineer | Platform Engineer | Infrastructure |

### Incident Response Workflow

```mermaid
graph TD
    A[Incident Detected] --> B{Severity?}
    B -->|P1 Critical| C[Immediate Response]
    B -->|P2 High| D[Within 30 min]
    B -->|P3 Medium| E[Within 4 hours]

    C --> F[Notify On-Call]
    D --> F
    E --> F

    F --> G[Incident Commander Assigned]
    G --> H[Assemble Team]
    H --> I[Assess Impact]

    I --> J{Can Mitigate?}
    J -->|Yes| K[Implement Mitigation]
    J -->|No| L[Initiate DR]

    K --> M[Monitor]
    L --> N[Execute DR Plan]

    M --> O{Resolved?}
    N --> O

    O -->|Yes| P[Post-Incident Review]
    O -->|No| Q[Escalate]
    Q --> I
```

### Incident Runbook

```yaml
# runbooks/database-failure.yaml
title: "Database Primary Failure"
severity: P1
estimated_time: "5-15 minutes"

triggers:
  - Database health check fails
  - Application cannot connect to database
  - Patroni reports primary down

initial_response:
  - step: 1
    action: "Verify primary database is down"
    command: "pg_isready -h db-primary -p 5432"
    expected: "Connection refused or timeout"

  - step: 2
    action: "Check Patroni cluster status"
    command: "patronictl -c /etc/patroni/patroni.yml list"
    expected: "Primary shows as failed"

  - step: 3
    action: "Verify automatic failover initiated"
    command: "tail -f /var/log/patroni/patroni.log"
    expected: "Failover to standby initiated"

recovery_steps:
  - step: 1
    action: "Wait for automatic failover (typically 30-60 seconds)"
    verification: "patronictl list shows new primary"

  - step: 2
    action: "Verify application connectivity"
    command: "curl http://api.ablage-system.com/health"
    expected: "database: healthy"

  - step: 3
    action: "Monitor replication lag"
    command: "psql -c 'SELECT * FROM pg_stat_replication;'"

  - step: 4
    action: "Investigate failed primary"
    notes: "Check logs, disk space, system resources"

rollback:
  - condition: "If failover fails after 5 minutes"
  - action: "Manual failover procedure"
  - command: "patronictl failover ablage-cluster"

communication:
  - notify: "Platform team via PagerDuty"
  - status_page: "Update if customer-facing impact"
  - escalate_after: "15 minutes if not resolved"
```

---

## Communication Plan

### Stakeholder Matrix

| Stakeholder | P1 (Critical) | P2 (High) | P3 (Medium) |
|-------------|---------------|-----------|-------------|
| **Customers** | Immediate status page | Within 1 hour | Email next day |
| **Executive Team** | Immediate call | Within 30 min | Daily summary |
| **Engineering Team** | Immediate Slack | Immediate Slack | Slack |
| **Support Team** | Immediate call | Within 15 min | Email |

### Communication Templates

#### Status Page Update

```markdown
**[INVESTIGATING] - Service Degradation**

Posted: 2025-01-15 10:30 UTC

We are currently investigating reports of slow API response times.
Our team is actively working to identify the root cause.

**Impact**: API requests may experience delays of 2-5 seconds.
Document uploads and OCR processing are not affected.

Next update in 30 minutes or when more information becomes available.
```

```markdown
**[RESOLVED] - Service Degradation**

Posted: 2025-01-15 11:45 UTC

The issue has been resolved. All services are operating normally.

**Root Cause**: Database connection pool exhaustion due to long-running queries.

**Resolution**: Implemented connection pool limits and query timeouts.

**Timeline**:
- 10:15 UTC - Issue began
- 10:30 UTC - Investigation started
- 11:00 UTC - Root cause identified
- 11:30 UTC - Fix deployed
- 11:45 UTC - Fully resolved

We apologize for any inconvenience caused.
```

---

## Post-Incident Review

### Post-Incident Review Template

```markdown
# Post-Incident Review

**Incident ID**: INC-2025-001
**Date**: 2025-01-15
**Severity**: P1
**Duration**: 1h 15m
**Impact**: 15,000 users affected

## Summary

Brief description of what happened.

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 10:15 | Database primary experienced high load |
| 10:20 | Alerts triggered for slow responses |
| 10:25 | On-call engineer paged |
| 10:30 | Incident declared |
| 10:45 | Root cause identified |
| 11:00 | Mitigation deployed |
| 11:30 | Services fully restored |

## Root Cause

Detailed analysis of what caused the incident.

## Impact

- **Users**: 15,000 users experienced slow response times
- **Revenue**: Estimated $500 in lost revenue
- **Data**: No data loss
- **Reputation**: 20 support tickets filed

## What Went Well

- Alert detected issue within 5 minutes
- Team assembled quickly
- Communication was clear
- No data loss occurred

## What Could Be Improved

1. **Detection**: Earlier alerting needed
2. **Response**: Runbook was outdated
3. **Prevention**: Need better load testing

## Action Items

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Update database connection limits | @dba | 2025-01-20 | In Progress |
| Create load testing suite | @platform | 2025-01-25 | Pending |
| Update runbook | @oncall | 2025-01-18 | Completed |
| Add capacity monitoring | @devops | 2025-01-22 | In Progress |

## Lessons Learned

1. Always test under realistic load
2. Keep runbooks up-to-date
3. Have clear escalation paths

## Supporting Materials

- Incident chat logs: [link]
- Monitoring dashboards: [link]
- Database logs: [link]
```

---

## Appendix

### Contact Information

```yaml
# emergency-contacts.yaml
incident_commander:
  primary:
    name: "John Doe"
    phone: "+49-xxx-xxxx-001"
    email: "john@ablage-system.com"
  backup:
    name: "Jane Smith"
    phone: "+49-xxx-xxxx-002"
    email: "jane@ablage-system.com"

technical_leads:
  database:
    name: "DB Admin"
    phone: "+49-xxx-xxxx-003"
    email: "dba@ablage-system.com"

  infrastructure:
    name: "DevOps Lead"
    phone: "+49-xxx-xxxx-004"
    email: "devops@ablage-system.com"

escalation:
  level_1: "On-call engineer"
  level_2: "Team lead"
  level_3: "Engineering director"
  level_4: "CTO"

external:
  aws_support: "+1-xxx-xxx-xxxx"
  database_vendor: "support@postgresql.org"
```

### Useful Commands

```bash
# Database
psql -U postgres -c "SELECT * FROM pg_stat_activity;"
patronictl list
pg_isready -h localhost

# Kubernetes
kubectl get pods -n ablage-system
kubectl logs -f deployment/ablage-api
kubectl describe pod <pod-name>

# Monitoring
curl http://localhost:8000/health
curl http://localhost:9090/metrics

# AWS
aws s3 ls s3://ablage-backups/
aws ec2 describe-instances --filters "Name=tag:Environment,Values=production"
aws rds describe-db-instances

# Network
ping db.ablage-system.com
dig api.ablage-system.com
traceroute api.ablage-system.com
```

---

**Document Version**: 1.0.0
**Last Updated**: 2025-01-15
**Next Review**: 2025-04-15
**Owner**: Platform Team
