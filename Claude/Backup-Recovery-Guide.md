 BACKUP & DISASTER RECOVERY GUIDE - TEIL 1
Comprehensive Guide to Backup Strategies, Automation & Recovery

📋 TABLE OF CONTENTS

Introduction
Database Backup Strategies
Automated Backups
Point-in-Time Recovery
File Storage Backups


🎯 INTRODUCTION
Why Backup & Disaster Recovery Matters
┌─────────────────────────────────────────────────────────┐
│               DISASTER SCENARIOS TO PREPARE FOR          │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  💥 Hardware Failure     → Disk crash, server death     │
│  🔥 Data Corruption      → Database corruption          │
│  🗑️  Accidental Deletion → User/admin mistakes         │
│  🏢 Site Disaster        → Fire, flood, power outage    │
│  🦠 Ransomware Attack    → Data encryption/hostage      │
│  👤 Human Error          → Wrong UPDATE/DELETE          │
│  🔧 Software Bugs        → Application bugs             │
│  ⚡ Power Loss           → Sudden shutdown              │
│                                                         │
└─────────────────────────────────────────────────────────┘
Backup Architecture Overview
┌──────────────────────────────────────────────────────────────┐
│                    BACKUP ARCHITECTURE                        │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────┐      ┌─────────────┐      ┌─────────────┐ │
│  │ Production  │──────▶│   Backup    │──────▶│   Offsite   │ │
│  │   Server    │ Hot  │   Server    │ Cold │   Storage   │ │
│  └─────────────┘      └─────────────┘      └─────────────┘ │
│         │                     │                     │        │
│         │                     │                     │        │
│    PostgreSQL            PostgreSQL              S3/NAS     │
│    + WAL Files          + pg_dump             + Glacier     │
│    + File Storage       + Incremental         + Tape        │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              BACKUP SCHEDULE                          │  │
│  ├──────────────────────────────────────────────────────┤  │
│  │  Continuous    → WAL Archiving (every 1-5 min)       │  │
│  │  Hourly        → Incremental File Backups            │  │
│  │  Daily         → Full Database Dump                  │  │
│  │  Weekly        → Full System Backup                  │  │
│  │  Monthly       → Archive to Cold Storage             │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
└──────────────────────────────────────────────────────────────┘
Key Concepts
python# RTO (Recovery Time Objective)
# Maximum acceptable downtime
RTO = "4 hours"  # System must be back online within 4 hours

# RPO (Recovery Point Objective)
# Maximum acceptable data loss
RPO = "15 minutes"  # Can lose max 15 minutes of data

# Backup Types
FULL_BACKUP = "Complete copy of all data"
INCREMENTAL_BACKUP = "Only changes since last backup"
DIFFERENTIAL_BACKUP = "Changes since last full backup"

# Storage Tiers
HOT_STORAGE = "Fast access, expensive (local SSD)"
WARM_STORAGE = "Medium access, moderate (NAS)"
COLD_STORAGE = "Slow access, cheap (S3 Glacier, Tape)"

💾 DATABASE BACKUP STRATEGIES
1. Backup Strategy Matrix
python# backend/config/backup_strategy.py

from enum import Enum
from typing import Dict, Any


class BackupType(str, Enum):
    """Types of database backups"""
    LOGICAL = "logical"          # SQL dump (pg_dump)
    PHYSICAL = "physical"        # File-level copy
    CONTINUOUS = "continuous"    # WAL archiving
    SNAPSHOT = "snapshot"        # Storage snapshot


class BackupFrequency(str, Enum):
    """Backup frequencies"""
    CONTINUOUS = "continuous"    # WAL archiving
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


# ============================================
# BACKUP STRATEGY RECOMMENDATIONS
# ============================================

BACKUP_STRATEGIES: Dict[str, Dict[str, Any]] = {
    
    # Small Database (< 10 GB)
    "small": {
        "primary": {
            "type": BackupType.LOGICAL,
            "frequency": BackupFrequency.DAILY,
            "tool": "pg_dump",
            "retention": "30 days",
            "compression": True
        },
        "secondary": {
            "type": BackupType.CONTINUOUS,
            "frequency": BackupFrequency.CONTINUOUS,
            "tool": "WAL archiving",
            "retention": "7 days"
        },
        "rto": "1 hour",
        "rpo": "15 minutes"
    },
    
    # Medium Database (10-100 GB)
    "medium": {
        "primary": {
            "type": BackupType.PHYSICAL,
            "frequency": BackupFrequency.DAILY,
            "tool": "pg_basebackup",
            "retention": "14 days",
            "compression": True
        },
        "secondary": {
            "type": BackupType.CONTINUOUS,
            "frequency": BackupFrequency.CONTINUOUS,
            "tool": "WAL archiving",
            "retention": "14 days"
        },
        "tertiary": {
            "type": BackupType.SNAPSHOT,
            "frequency": BackupFrequency.WEEKLY,
            "tool": "LVM/ZFS snapshot",
            "retention": "4 weeks"
        },
        "rto": "30 minutes",
        "rpo": "5 minutes"
    },
    
    # Large Database (> 100 GB)
    "large": {
        "primary": {
            "type": BackupType.PHYSICAL,
            "frequency": BackupFrequency.DAILY,
            "tool": "pg_basebackup",
            "retention": "7 days",
            "compression": True,
            "parallel": True
        },
        "secondary": {
            "type": BackupType.CONTINUOUS,
            "frequency": BackupFrequency.CONTINUOUS,
            "tool": "WAL archiving",
            "retention": "7 days",
            "compression": True
        },
        "tertiary": {
            "type": BackupType.SNAPSHOT,
            "frequency": BackupFrequency.HOURLY,
            "tool": "Storage snapshot",
            "retention": "24 hours"
        },
        "archive": {
            "type": BackupType.LOGICAL,
            "frequency": BackupFrequency.WEEKLY,
            "tool": "pg_dump",
            "retention": "12 weeks",
            "destination": "S3 Glacier"
        },
        "rto": "15 minutes",
        "rpo": "1 minute"
    }
}
2. PostgreSQL Backup Comparison
python# backend/utils/backup_comparison.py

"""
POSTGRESQL BACKUP METHODS COMPARISON
====================================

┌─────────────────┬──────────────┬──────────────┬──────────────┐
│     Method      │   pg_dump    │pg_basebackup │ WAL Archive  │
├─────────────────┼──────────────┼──────────────┼──────────────┤
│ Type            │ Logical      │ Physical     │ Continuous   │
│ Downtime        │ No           │ No           │ No           │
│ PITR Support    │ No           │ Yes          │ Yes          │
│ Size            │ Small        │ Large        │ Medium       │
│ Compression     │ Easy         │ Medium       │ Easy         │
│ Speed (Backup)  │ Slow         │ Fast         │ Continuous   │
│ Speed (Restore) │ Slow         │ Fast         │ Fast         │
│ Selective       │ Yes (tables) │ No (all/none)│ No           │
│ Cross-Version   │ Yes          │ No           │ No           │
│ Single Table    │ Yes          │ No           │ No           │
│ Storage Type    │ Any          │ Any          │ Sequential   │
└─────────────────┴──────────────┴──────────────┴──────────────┘

RECOMMENDATIONS:

1. Small DB (< 10 GB):
   - Daily: pg_dump (compressed)
   - Continuous: WAL archiving
   - Easy to manage, minimal complexity

2. Medium DB (10-100 GB):
   - Daily: pg_basebackup
   - Continuous: WAL archiving
   - Balance of speed and features

3. Large DB (> 100 GB):
   - Daily: pg_basebackup (parallel)
   - Continuous: WAL archiving (compressed)
   - Hourly: Storage snapshots
   - Optimize for speed and RPO

4. Critical Systems:
   - Streaming Replication + WAL archiving
   - Real-time standby server
   - Automatic failover
   - RPO: Near-zero
"""
3. Backup Configuration File
yaml# config/backup_config.yaml

# ============================================
# BACKUP CONFIGURATION
# ============================================

backup:
  # Database type
  database:
    type: postgresql
    version: "15"
    size_category: medium  # small, medium, large
  
  # Backup schedule
  schedule:
    full_backup:
      frequency: daily
      time: "02:00"  # 2 AM
      retention_days: 14
    
    incremental_backup:
      frequency: hourly
      retention_days: 2
    
    wal_archiving:
      enabled: true
      retention_days: 7
      compression: true
    
    snapshot:
      enabled: true
      frequency: weekly
      day: sunday
      time: "03:00"
      retention_weeks: 4
  
  # Storage locations
  storage:
    local:
      path: /var/backups/postgres
      max_size_gb: 500
    
    remote:
      type: s3
      bucket: my-app-backups
      region: eu-central-1
      encryption: true
      storage_class: STANDARD_IA  # Infrequent Access
    
    archive:
      type: s3
      bucket: my-app-archive
      storage_class: GLACIER
      retention_months: 12
  
  # Recovery objectives
  sla:
    rto: "30 minutes"  # Recovery Time Objective
    rpo: "5 minutes"   # Recovery Point Objective
  
  # Notification
  notifications:
    on_success: false
    on_failure: true
    channels:
      - email: ops@example.com
      - slack: "#alerts"
  
  # Testing
  testing:
    frequency: monthly
    restore_test: true
    integrity_check: true

🤖 AUTOMATED BACKUPS
1. pg_dump Automation
bash#!/bin/bash
# scripts/backup_postgres_logical.sh

# ============================================
# POSTGRESQL LOGICAL BACKUP SCRIPT
# ============================================
# 
# Features:
# - Full database dump
# - Compression
# - Encryption (optional)
# - Remote upload (S3)
# - Retention management
# - Notifications
#
# Usage:
#   ./backup_postgres_logical.sh
#
# Cron:
#   0 2 * * * /path/to/backup_postgres_logical.sh
# ============================================

set -euo pipefail

# ============================================
# CONFIGURATION
# ============================================

# Database settings
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-myapp}"
DB_USER="${DB_USER:-postgres}"

# Backup settings
BACKUP_DIR="${BACKUP_DIR:-/var/backups/postgres}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.sql.gz"

# S3 settings (optional)
S3_BUCKET="${S3_BUCKET:-}"
S3_PREFIX="${S3_PREFIX:-backups/postgres}"

# Notification settings
SLACK_WEBHOOK="${SLACK_WEBHOOK:-}"
EMAIL_TO="${EMAIL_TO:-}"

# ============================================
# LOGGING
# ============================================

LOG_FILE="${BACKUP_DIR}/backup.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" | tee -a "$LOG_FILE" >&2
}

# ============================================
# NOTIFICATION FUNCTIONS
# ============================================

send_slack_notification() {
    local message=$1
    local status=$2  # success or error
    
    if [ -n "$SLACK_WEBHOOK" ]; then
        local color="good"
        [ "$status" = "error" ] && color="danger"
        
        curl -X POST "$SLACK_WEBHOOK" \
            -H 'Content-Type: application/json' \
            -d "{
                \"attachments\": [{
                    \"color\": \"$color\",
                    \"title\": \"Database Backup: $status\",
                    \"text\": \"$message\",
                    \"footer\": \"Backup Script\",
                    \"ts\": $(date +%s)
                }]
            }" 2>&1 | tee -a "$LOG_FILE"
    fi
}

send_email_notification() {
    local subject=$1
    local body=$2
    
    if [ -n "$EMAIL_TO" ]; then
        echo "$body" | mail -s "$subject" "$EMAIL_TO"
    fi
}

# ============================================
# BACKUP FUNCTION
# ============================================

perform_backup() {
    log "Starting PostgreSQL backup..."
    log "Database: $DB_NAME"
    log "Target: $BACKUP_FILE"
    
    # Create backup directory if not exists
    mkdir -p "$BACKUP_DIR"
    
    # Perform backup with pg_dump
    log "Running pg_dump..."
    
    # Set password in environment
    export PGPASSWORD="${DB_PASSWORD}"
    
    pg_dump \
        --host="$DB_HOST" \
        --port="$DB_PORT" \
        --username="$DB_USER" \
        --dbname="$DB_NAME" \
        --format=plain \
        --no-owner \
        --no-acl \
        --verbose \
        2>> "$LOG_FILE" \
        | gzip > "$BACKUP_FILE"
    
    # Unset password
    unset PGPASSWORD
    
    # Check if backup was successful
    if [ ! -f "$BACKUP_FILE" ]; then
        log_error "Backup file not created!"
        return 1
    fi
    
    # Get file size
    local file_size=$(du -h "$BACKUP_FILE" | cut -f1)
    log "Backup created successfully: $file_size"
    
    # Verify backup integrity
    log "Verifying backup integrity..."
    if gzip -t "$BACKUP_FILE"; then
        log "Backup integrity verified"
    else
        log_error "Backup file is corrupted!"
        return 1
    fi
    
    return 0
}

# ============================================
# UPLOAD TO S3
# ============================================

upload_to_s3() {
    if [ -n "$S3_BUCKET" ]; then
        log "Uploading to S3..."
        
        aws s3 cp "$BACKUP_FILE" \
            "s3://${S3_BUCKET}/${S3_PREFIX}/$(basename $BACKUP_FILE)" \
            --storage-class STANDARD_IA \
            --server-side-encryption AES256 \
            2>&1 | tee -a "$LOG_FILE"
        
        if [ $? -eq 0 ]; then
            log "Upload to S3 successful"
        else
            log_error "Upload to S3 failed"
            return 1
        fi
    fi
    
    return 0
}

# ============================================
# CLEANUP OLD BACKUPS
# ============================================

cleanup_old_backups() {
    log "Cleaning up backups older than $RETENTION_DAYS days..."
    
    find "$BACKUP_DIR" \
        -name "${DB_NAME}_*.sql.gz" \
        -type f \
        -mtime +$RETENTION_DAYS \
        -delete \
        2>&1 | tee -a "$LOG_FILE"
    
    log "Cleanup completed"
}

# ============================================
# MAIN EXECUTION
# ============================================

main() {
    local start_time=$(date +%s)
    
    log "========================================"
    log "PostgreSQL Backup Started"
    log "========================================"
    
    # Perform backup
    if ! perform_backup; then
        send_slack_notification "Backup failed for $DB_NAME" "error"
        send_email_notification \
            "BACKUP FAILED: $DB_NAME" \
            "PostgreSQL backup failed. Check logs at $LOG_FILE"
        exit 1
    fi
    
    # Upload to S3
    if ! upload_to_s3; then
        send_slack_notification "S3 upload failed for $DB_NAME" "error"
        # Don't exit - local backup still exists
    fi
    
    # Cleanup old backups
    cleanup_old_backups
    
    # Calculate duration
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    log "========================================"
    log "Backup completed successfully in ${duration}s"
    log "========================================"
    
    # Send success notification
    send_slack_notification \
        "Backup completed for $DB_NAME in ${duration}s" \
        "success"
}

# Run main function
main "$@"
2. pg_basebackup Automation
bash#!/bin/bash
# scripts/backup_postgres_physical.sh

# ============================================
# POSTGRESQL PHYSICAL BACKUP SCRIPT
# ============================================
# 
# Features:
# - Physical backup (pg_basebackup)
# - Parallel streaming
# - WAL files included
# - Faster than pg_dump for large DBs
#
# Usage:
#   ./backup_postgres_physical.sh
# ============================================

set -euo pipefail

# Configuration
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-postgres}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/postgres/physical}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_PATH="${BACKUP_DIR}/${TIMESTAMP}"
RETENTION_DAYS=7

# Logging
LOG_FILE="${BACKUP_DIR}/physical_backup.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# Create backup directory
mkdir -p "$BACKUP_PATH"

log "Starting physical backup..."
log "Target: $BACKUP_PATH"

# Set password
export PGPASSWORD="${DB_PASSWORD}"

# Perform basebackup
pg_basebackup \
    --host="$DB_HOST" \
    --port="$DB_PORT" \
    --username="$DB_USER" \
    --pgdata="$BACKUP_PATH" \
    --format=tar \
    --gzip \
    --compress=9 \
    --checkpoint=fast \
    --progress \
    --verbose \
    --wal-method=stream \
    2>&1 | tee -a "$LOG_FILE"

unset PGPASSWORD

if [ $? -eq 0 ]; then
    log "Physical backup completed successfully"
    
    # Get backup size
    backup_size=$(du -sh "$BACKUP_PATH" | cut -f1)
    log "Backup size: $backup_size"
    
    # Cleanup old backups
    find "$BACKUP_DIR" \
        -maxdepth 1 \
        -type d \
        -mtime +$RETENTION_DAYS \
        ! -name "$(basename $BACKUP_DIR)" \
        -exec rm -rf {} \; \
        2>&1 | tee -a "$LOG_FILE"
    
    log "Old backups cleaned up"
else
    log "ERROR: Physical backup failed!"
    exit 1
fi
3. WAL Archiving Configuration
conf# postgresql.conf - WAL Archiving Settings

# ============================================
# WAL ARCHIVING CONFIGURATION
# ============================================

# Enable WAL archiving
wal_level = replica                    # or 'logical' for logical replication
archive_mode = on                      # Enable archiving
archive_command = '/usr/local/bin/archive_wal.sh %p %f'
archive_timeout = 300                  # Force WAL switch every 5 minutes

# WAL settings
max_wal_senders = 10                   # Max concurrent WAL senders
max_wal_size = 4GB                     # Max size before checkpoint
min_wal_size = 1GB                     # Minimum WAL to keep
wal_keep_size = 1GB                    # Amount to keep for standbys

# Checkpoint settings
checkpoint_timeout = 15min             # Time between checkpoints
checkpoint_completion_target = 0.9     # Spread checkpoint I/O

# Logging
log_checkpoints = on                   # Log checkpoint activity
log_replication_commands = on          # Log replication commands
bash#!/bin/bash
# /usr/local/bin/archive_wal.sh

# ============================================
# WAL ARCHIVING SCRIPT
# ============================================
#
# Called by PostgreSQL archive_command
# Args: $1 = WAL file path, $2 = WAL filename
#
# This script:
# - Compresses WAL files
# - Stores locally
# - Uploads to S3
# - Manages retention
# ============================================

set -euo pipefail

WAL_PATH="$1"
WAL_FILE="$2"

# Configuration
ARCHIVE_DIR="/var/lib/postgresql/wal_archive"
S3_BUCKET="${S3_BUCKET:-my-app-wal-archive}"
S3_PREFIX="wal"
RETENTION_DAYS=7

# Logging
LOG_FILE="/var/log/postgresql/wal_archive.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"
}

# Create archive directory
mkdir -p "$ARCHIVE_DIR"

# Compress and copy locally
log "Archiving WAL: $WAL_FILE"

gzip -c "$WAL_PATH" > "${ARCHIVE_DIR}/${WAL_FILE}.gz"

if [ $? -ne 0 ]; then
    log "ERROR: Failed to compress WAL file"
    exit 1
fi

# Upload to S3
if [ -n "$S3_BUCKET" ]; then
    aws s3 cp \
        "${ARCHIVE_DIR}/${WAL_FILE}.gz" \
        "s3://${S3_BUCKET}/${S3_PREFIX}/${WAL_FILE}.gz" \
        --storage-class STANDARD_IA \
        >> "$LOG_FILE" 2>&1
    
    if [ $? -ne 0 ]; then
        log "ERROR: Failed to upload to S3"
        exit 1
    fi
    
    log "Uploaded to S3 successfully"
fi

# Cleanup old WAL files
find "$ARCHIVE_DIR" \
    -name "*.gz" \
    -type f \
    -mtime +$RETENTION_DAYS \
    -delete \
    >> "$LOG_FILE" 2>&1

log "WAL archiving completed: $WAL_FILE"

exit 0
4. Systemd Timers for Backup
ini# /etc/systemd/system/postgres-backup.timer

[Unit]
Description=PostgreSQL Daily Backup Timer
Requires=postgres-backup.service

[Timer]
OnCalendar=daily
OnCalendar=02:00
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
ini# /etc/systemd/system/postgres-backup.service

[Unit]
Description=PostgreSQL Daily Backup
After=postgresql.service
Requires=postgresql.service

[Service]
Type=oneshot
User=postgres
Group=postgres

# Environment
Environment="DB_HOST=localhost"
Environment="DB_NAME=myapp"
Environment="DB_USER=postgres"
EnvironmentFile=/etc/postgres-backup/config

# Execution
ExecStart=/usr/local/bin/backup_postgres_logical.sh

# Security
PrivateTmp=yes
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/backups/postgres

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=postgres-backup

[Install]
WantedBy=multi-user.target
bash# Enable and manage timer
sudo systemctl enable postgres-backup.timer
sudo systemctl start postgres-backup.timer

# Check timer status
sudo systemctl list-timers postgres-backup.timer

# Manual run
sudo systemctl start postgres-backup.service

# View logs
sudo journalctl -u postgres-backup.service -f

⏰ POINT-IN-TIME RECOVERY (PITR)
1. PITR Configuration
conf# postgresql.conf - Additional PITR settings

# Recovery settings (for standby/restore)
restore_command = '/usr/local/bin/restore_wal.sh %f %p'
recovery_target_timeline = 'latest'

# Hot standby (if using streaming replication)
hot_standby = on
hot_standby_feedback = on
bash#!/bin/bash
# /usr/local/bin/restore_wal.sh

# ============================================
# WAL RESTORE SCRIPT FOR PITR
# ============================================
#
# Called by PostgreSQL restore_command
# Args: $1 = WAL filename, $2 = destination path
#
# This script:
# - Checks local archive first
# - Downloads from S3 if not found locally
# - Decompresses WAL file
# ============================================

set -euo pipefail

WAL_FILE="$1"
DEST_PATH="$2"

# Configuration
ARCHIVE_DIR="/var/lib/postgresql/wal_archive"
S3_BUCKET="${S3_BUCKET:-my-app-wal-archive}"
S3_PREFIX="wal"

# Logging
LOG_FILE="/var/log/postgresql/wal_restore.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"
}

log "Restoring WAL: $WAL_FILE"

# Check if file exists locally
if [ -f "${ARCHIVE_DIR}/${WAL_FILE}.gz" ]; then
    log "Found WAL in local archive"
    gzip -dc "${ARCHIVE_DIR}/${WAL_FILE}.gz" > "$DEST_PATH"
    exit $?
fi

# Download from S3
log "Downloading WAL from S3"

aws s3 cp \
    "s3://${S3_BUCKET}/${S3_PREFIX}/${WAL_FILE}.gz" \
    - \
    2>> "$LOG_FILE" \
    | gzip -dc > "$DEST_PATH"

exit_code=$?

if [ $exit_code -eq 0 ]; then
    log "WAL restored successfully: $WAL_FILE"
else
    log "ERROR: Failed to restore WAL: $WAL_FILE"
fi

exit $exit_code
2. PITR Recovery Script
bash#!/bin/bash
# scripts/pitr_recovery.sh

# ============================================
# POINT-IN-TIME RECOVERY SCRIPT
# ============================================
#
# Restore database to a specific point in time
#
# Usage:
#   ./pitr_recovery.sh "2024-01-15 14:30:00"
#   ./pitr_recovery.sh "2024-01-15 14:30:00 UTC"
#   ./pitr_recovery.sh "latest"
# ============================================

set -euo pipefail

# Parse arguments
RECOVERY_TARGET="${1:-latest}"

# Configuration
PGDATA="${PGDATA:-/var/lib/postgresql/data}"
BACKUP_DIR="/var/backups/postgres/physical"
WAL_ARCHIVE_DIR="/var/lib/postgresql/wal_archive"

# Logging
LOG_FILE="/var/log/postgresql/pitr_recovery.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" | tee -a "$LOG_FILE" >&2
}

# ============================================
# PRE-FLIGHT CHECKS
# ============================================

log "========================================"
log "POINT-IN-TIME RECOVERY"
log "Target: $RECOVERY_TARGET"
log "========================================"

# Check if PostgreSQL is running
if pg_isready > /dev/null 2>&1; then
    log_error "PostgreSQL is still running! Stop it first."
    exit 1
fi

# Check if backup exists
LATEST_BACKUP=$(ls -1dt "$BACKUP_DIR"/* 2>/dev/null | head -n1)

if [ -z "$LATEST_BACKUP" ]; then
    log_error "No backup found in $BACKUP_DIR"
    exit 1
fi

log "Using backup: $LATEST_BACKUP"

# ============================================
# BACKUP CURRENT DATA (SAFETY)
# ============================================

log "Creating safety backup of current PGDATA..."

SAFETY_BACKUP="${PGDATA}.before_pitr_$(date +%Y%m%d_%H%M%S)"
mv "$PGDATA" "$SAFETY_BACKUP"

log "Current data backed up to: $SAFETY_BACKUP"

# ============================================
# RESTORE BASE BACKUP
# ============================================

log "Restoring base backup..."

mkdir -p "$PGDATA"
tar -xzf "${LATEST_BACKUP}/base.tar.gz" -C "$PGDATA"

if [ -f "${LATEST_BACKUP}/pg_wal.tar.gz" ]; then
    tar -xzf "${LATEST_BACKUP}/pg_wal.tar.gz" -C "${PGDATA}/pg_wal"
fi

log "Base backup restored"

# ============================================
# CREATE RECOVERY CONFIGURATION
# ============================================

log "Creating recovery configuration..."

cat > "${PGDATA}/recovery.signal" << EOF
# Recovery signal file
# Created by PITR recovery script
EOF

# PostgreSQL 12+ uses postgresql.auto.conf
cat > "${PGDATA}/postgresql.auto.conf" << EOF
# PITR Recovery Configuration
restore_command = '/usr/local/bin/restore_wal.sh %f %p'
recovery_target_timeline = 'latest'
EOF

# Set recovery target
if [ "$RECOVERY_TARGET" != "latest" ]; then
    cat >> "${PGDATA}/postgresql.auto.conf" << EOF
recovery_target_time = '$RECOVERY_TARGET'
recovery_target_action = 'promote'
EOF
    log "Recovery target time: $RECOVERY_TARGET"
else
    log "Recovery target: Latest available"
fi

# ============================================
# SET PERMISSIONS
# ============================================

chown -R postgres:postgres "$PGDATA"
chmod 0700 "$PGDATA"

# ============================================
# START RECOVERY
# ============================================

log "Starting PostgreSQL for recovery..."

systemctl start postgresql

# Wait for recovery to complete
log "Waiting for recovery to complete..."

while [ -f "${PGDATA}/recovery.signal" ]; do
    sleep 5
    log "Recovery in progress..."
done

log "========================================"
log "PITR Recovery completed successfully!"
log "========================================"
log "Safety backup available at: $SAFETY_BACKUP"
log "Remove it after verification: rm -rf $SAFETY_BACKUP"
3. PITR Testing Script
python# scripts/test_pitr.py

"""
PITR Testing Script

This script:
1. Creates test data with timestamps
2. Performs backup
3. Adds more data
4. Simulates disaster
5. Performs PITR to specific point
6. Validates recovery
"""

import psycopg2
from datetime import datetime, timedelta
import subprocess
import time


class PITRTester:
    """Test Point-in-Time Recovery"""
    
    def __init__(self, db_config):
        self.db_config = db_config
        self.conn = None
        self.test_table = "pitr_test"
    
    def connect(self):
        """Connect to database"""
        self.conn = psycopg2.connect(**self.db_config)
        self.conn.autocommit = True
    
    def create_test_table(self):
        """Create test table"""
        with self.conn.cursor() as cur:
            cur.execute(f"""
                DROP TABLE IF EXISTS {self.test_table};
                CREATE TABLE {self.test_table} (
                    id SERIAL PRIMARY KEY,
                    data TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)
        print("✓ Test table created")
    
    def insert_test_data(self, count=1000, label="initial"):
        """Insert test data"""
        with self.conn.cursor() as cur:
            for i in range(count):
                cur.execute(
                    f"INSERT INTO {self.test_table} (data) VALUES (%s)",
                    (f"{label}_data_{i}",)
                )
        print(f"✓ Inserted {count} rows ({label})")
    
    def get_row_count(self):
        """Get total row count"""
        with self.conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {self.test_table}")
            return cur.fetchone()[0]
    
    def get_latest_timestamp(self):
        """Get latest record timestamp"""
        with self.conn.cursor() as cur:
            cur.execute(
                f"SELECT MAX(created_at) FROM {self.test_table}"
            )
            return cur.fetchone()[0]
    
    def perform_backup(self):
        """Trigger backup"""
        print("\n📦 Performing backup...")
        result = subprocess.run(
            ["/usr/local/bin/backup_postgres_logical.sh"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✓ Backup completed")
        else:
            print(f"✗ Backup failed: {result.stderr}")
            raise Exception("Backup failed")
    
    def run_test(self):
        """Run complete PITR test"""
        
        print("=" * 60)
        print("PITR TEST STARTED")
        print("=" * 60)
        
        # Connect
        self.connect()
        
        # Phase 1: Initial data
        print("\n📝 Phase 1: Creating initial data...")
        self.create_test_table()
        self.insert_test_data(1000, "initial")
        initial_count = self.get_row_count()
        print(f"   Total rows: {initial_count}")
        
        # Perform backup
        self.perform_backup()
        
        # Wait for WAL archiving
        print("\n⏰ Waiting for WAL archiving...")
        time.sleep(10)
        
        # Phase 2: More data (before recovery point)
        print("\n📝 Phase 2: Adding more data...")
        self.insert_test_data(500, "before_recovery")
        before_recovery_count = self.get_row_count()
        recovery_point = self.get_latest_timestamp()
        
        print(f"   Total rows: {before_recovery_count}")
        print(f"   Recovery point: {recovery_point}")
        
        # Wait
        time.sleep(5)
        
        # Phase 3: Data to lose (after recovery point)
        print("\n📝 Phase 3: Adding data that should be lost...")
        self.insert_test_data(300, "after_recovery_will_be_lost")
        final_count = self.get_row_count()
        print(f"   Total rows: {final_count}")
        
        # Close connection
        self.conn.close()
        
        # Phase 4: PITR
        print(f"\n🔄 Phase 4: Performing PITR to {recovery_point}...")
        
        # Stop PostgreSQL
        subprocess.run(["systemctl", "stop", "postgresql"])
        
        # Perform PITR
        result = subprocess.run(
            [
                "/path/to/pitr_recovery.sh",
                recovery_point.strftime("%Y-%m-%d %H:%M:%S")
            ],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"✗ PITR failed: {result.stderr}")
            raise Exception("PITR failed")
        
        print("✓ PITR completed")
        
        # Phase 5: Validation
        print("\n✅ Phase 5: Validating recovery...")
        self.connect()
        
        recovered_count = self.get_row_count()
        recovered_timestamp = self.get_latest_timestamp()
        
        print(f"   Expected rows: {before_recovery_count}")
        print(f"   Recovered rows: {recovered_count}")
        print(f"   Recovered timestamp: {recovered_timestamp}")
        
        # Validation
        if recovered_count == before_recovery_count:
            print("\n✓✓✓ PITR TEST PASSED ✓✓✓")
            print(f"   Recovered to exact point: {recovery_point}")
            print(f"   Lost {final_count - recovered_count} rows (as expected)")
        else:
            print("\n✗✗✗ PITR TEST FAILED ✗✗✗")
            print(f"   Expected: {before_recovery_count}")
            print(f"   Got: {recovered_count}")
        
        print("=" * 60)


if __name__ == "__main__":
    # Database configuration
    db_config = {
        "host": "localhost",
        "port": 5432,
        "database": "testdb",
        "user": "postgres",
        "password": "your_password"
    }
    
    tester = PITRTester(db_config)
    tester.run_test()

📁 FILE STORAGE BACKUPS
1. File Backup Strategy
python# backend/config/file_backup_config.py

"""
FILE BACKUP STRATEGY
===================

File Types to Backup:
1. User Uploads
   - Images, documents, videos
   - Location: /var/app/uploads
   - Strategy: Incremental hourly, full daily
   
2. Application Assets
   - Static files, templates
   - Location: /var/app/static
   - Strategy: On deployment only
   
3. Configuration Files
   - .env, configs, certificates
   - Location: /etc/app
   - Strategy: On change + daily
   
4. Logs
   - Application, access, error logs
   - Location: /var/log/app
   - Strategy: Daily, 30-day retention
"""

FILE_BACKUP_CONFIG = {
    "uploads": {
        "source": "/var/app/uploads",
        "destination": "s3://my-app-backups/uploads",
        "schedule": {
            "incremental": "hourly",
            "full": "daily at 03:00"
        },
        "retention": {
            "incremental": "7 days",
            "full": "30 days"
        },
        "exclude": [
            "*.tmp",
            "*.cache",
            ".DS_Store"
        ],
        "compression": True,
        "encryption": True
    },
    
    "config": {
        "source": "/etc/app",
        "destination": "s3://my-app-backups/config",
        "schedule": {
            "full": "on change + daily at 04:00"
        },
        "retention": {
            "full": "90 days"
        },
        "versioning": True,
        "encryption": True
    },
    
    "logs": {
        "source": "/var/log/app",
        "destination": "s3://my-app-backups/logs",
        "schedule": {
            "full": "daily at 05:00"
        },
        "retention": {
            "full": "30 days"
        },
        "compression": True
    }
}
2. rsync Backup Script
bash#!/bin/bash
# scripts/backup_files_rsync.sh

# ============================================
# FILE BACKUP SCRIPT USING RSYNC
# ============================================
#
# Features:
# - Incremental backups
# - Hardlinks for unchanged files
# - Bandwidth limiting
# - Exclude patterns
# - Logging
#
# Usage:
#   ./backup_files_rsync.sh
# ============================================

set -euo pipefail

# Configuration
SOURCE_DIR="/var/app/uploads"
BACKUP_ROOT="/var/backups/files"
RETENTION_DAYS=30
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="${BACKUP_ROOT}/${TIMESTAMP}"
LATEST_LINK="${BACKUP_ROOT}/latest"

# Logging
LOG_FILE="${BACKUP_ROOT}/backup.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# Create backup directory
mkdir -p "$BACKUP_DIR"

log "Starting file backup..."
log "Source: $SOURCE_DIR"
log "Destination: $BACKUP_DIR"

# Perform rsync backup
rsync -av \
    --delete \
    --hard-links \
    --link-dest="$LATEST_LINK" \
    --exclude="*.tmp" \
    --exclude="*.cache" \
    --exclude=".DS_Store" \
    --exclude="Thumbs.db" \
    --stats \
    --human-readable \
    --bwlimit=10000 \
    "$SOURCE_DIR/" \
    "$BACKUP_DIR/" \
    2>&1 | tee -a "$LOG_FILE"

if [ ${PIPESTATUS[0]} -eq 0 ]; then
    log "Backup completed successfully"
    
    # Update latest symlink
    rm -f "$LATEST_LINK"
    ln -s "$BACKUP_DIR" "$LATEST_LINK"
    
    # Get backup size
    backup_size=$(du -sh "$BACKUP_DIR" | cut -f1)
    log "Backup size: $backup_size"
    
    # Cleanup old backups
    find "$BACKUP_ROOT" \
        -maxdepth 1 \
        -type d \
        -mtime +$RETENTION_DAYS \
        ! -name "$(basename $BACKUP_ROOT)" \
        -exec rm -rf {} \; \
        2>&1 | tee -a "$LOG_FILE"
    
    log "Old backups cleaned up"
else
    log "ERROR: Backup failed!"
    exit 1
fi
3. S3 Sync Backup
bash#!/bin/bash
# scripts/backup_files_s3.sh

# ============================================
# FILE BACKUP TO S3 USING AWS CLI
# ============================================
#
# Features:
# - Sync to S3
# - Server-side encryption
# - Lifecycle policies
# - Multipart upload for large files
#
# Usage:
#   ./backup_files_s3.sh
# ============================================

set -euo pipefail

# Configuration
SOURCE_DIR="/var/app/uploads"
S3_BUCKET="my-app-backups"
S3_PREFIX="uploads"
LOG_FILE="/var/log/app/s3_backup.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "Starting S3 sync backup..."

# Sync to S3
aws s3 sync \
    "$SOURCE_DIR" \
    "s3://${S3_BUCKET}/${S3_PREFIX}" \
    --delete \
    --storage-class STANDARD_IA \
    --server-side-encryption AES256 \
    --exclude "*.tmp" \
    --exclude "*.cache" \
    --exclude ".DS_Store" \
    --no-progress \
    2>&1 | tee -a "$LOG_FILE"

if [ ${PIPESTATUS[0]} -eq 0 ]; then
    log "S3 sync completed successfully"
else
    log "ERROR: S3 sync failed!"
    exit 1
fi

# Enable versioning (run once)
# aws s3api put-bucket-versioning \
#     --bucket "$S3_BUCKET" \
#     --versioning-configuration Status=Enabled

# Set lifecycle policy (run once)
# cat > lifecycle.json << 'EOF'
# {
#     "Rules": [
#         {
#             "Id": "Move old versions to Glacier",
#             "Status": "Enabled",
#             "NoncurrentVersionTransitions": [
#                 {
#                     "NoncurrentDays": 30,
#                     "StorageClass": "GLACIER"
#                 }
#             ],
#             "NoncurrentVersionExpiration": {
#                 "NoncurrentDays": 365
#             }
#         }
#     ]
# }
# EOF
# 
# aws s3api put-bucket-lifecycle-configuration \
#     --bucket "$S3_BUCKET" \
#     --lifecycle-configuration file://lifecycle.json
4. Restic Backup (Modern Alternative)
bash#!/bin/bash
# scripts/backup_files_restic.sh

# ============================================
# FILE BACKUP USING RESTIC
# ============================================
#
# Restic features:
# - Deduplication
# - Encryption
# - Compression
# - Multiple backends (S3, local, SFTP)
# - Fast incremental backups
# - Easy restoration
#
# Usage:
#   ./backup_files_restic.sh
# ============================================

set -euo pipefail

# Configuration
SOURCE_DIR="/var/app/uploads"
RESTIC_REPOSITORY="s3:s3.amazonaws.com/my-app-backups/restic"
RESTIC_PASSWORD_FILE="/etc/restic/password"
LOG_FILE="/var/log/app/restic_backup.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# Export repository and password
export RESTIC_REPOSITORY="$RESTIC_REPOSITORY"
export RESTIC_PASSWORD_FILE="$RESTIC_PASSWORD_FILE"

log "Starting Restic backup..."

# Initialize repository (first time only)
# restic init

# Perform backup
restic backup \
    "$SOURCE_DIR" \
    --tag "uploads" \
    --exclude "*.tmp" \
    --exclude "*.cache" \
    --exclude ".DS_Store" \
    --verbose \
    2>&1 | tee -a "$LOG_FILE"

if [ ${PIPESTATUS[0]} -eq 0 ]; then
    log "Backup completed successfully"
    
    # Forget old snapshots (keep policy)
    restic forget \
        --keep-daily 7 \
        --keep-weekly 4 \
        --keep-monthly 12 \
        --keep-yearly 3 \
        --prune \
        2>&1 | tee -a "$LOG_FILE"
    
    log "Cleanup completed"
    
    # Check repository integrity (weekly)
    if [ "$(date +%u)" -eq 7 ]; then
        log "Running integrity check..."
        restic check 2>&1 | tee -a "$LOG_FILE"
    fi
else
    log "ERROR: Backup failed!"
    exit 1
fi

# List snapshots
restic snapshots | tail -n 20 | tee -a "$LOG_FILE"




BACKUP & DISASTER RECOVERY GUIDE - TEIL 2
Testing, Validation & Recovery Procedures

📋 TABLE OF CONTENTS (TEIL 2)

Backup Testing & Validation
Disaster Recovery Plan
RTO/RPO Definitions
Restoration Procedures
Monitoring & Alerting


✅ BACKUP TESTING & VALIDATION
1. Why Test Backups?
┌─────────────────────────────────────────────────────────┐
│         "UNTESTED BACKUPS = NO BACKUPS"                  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Common Backup Failures:                                │
│  ❌ Corrupted backup files                              │
│  ❌ Missing WAL files                                   │
│  ❌ Incomplete backups                                  │
│  ❌ Wrong permissions                                   │
│  ❌ Insufficient storage                                │
│  ❌ Network failures during backup                      │
│  ❌ Backup script errors                                │
│  ❌ Encryption key lost                                 │
│                                                         │
│  Without Testing:                                       │
│  ⚠️  You only find out during disaster                  │
│  ⚠️  Recovery time is unknown                           │
│  ⚠️  Team doesn't know procedures                       │
│  ⚠️  Dependencies might be missing                      │
│                                                         │
└─────────────────────────────────────────────────────────┘
2. Backup Validation Checklist
yaml# config/backup_validation.yaml

validation:
  # Daily automatic checks
  daily:
    - name: "File Existence Check"
      description: "Verify backup files were created"
      critical: true
      
    - name: "File Size Check"
      description: "Ensure backup isn't suspiciously small"
      threshold: "min_size_mb: 100"
      critical: true
      
    - name: "Compression Integrity"
      description: "Verify compressed files aren't corrupted"
      command: "gzip -t"
      critical: true
      
    - name: "Checksum Validation"
      description: "Verify file integrity with checksums"
      algorithm: "SHA256"
      critical: true
  
  # Weekly detailed checks
  weekly:
    - name: "Restore Test (Partial)"
      description: "Restore single table to staging"
      critical: true
      
    - name: "WAL Archive Check"
      description: "Verify WAL continuity"
      critical: true
      
    - name: "S3 Upload Verification"
      description: "Confirm remote backups exist"
      critical: true
  
  # Monthly full checks
  monthly:
    - name: "Full Restore Test"
      description: "Complete restore to staging environment"
      critical: true
      duration_hours: 4
      
    - name: "PITR Test"
      description: "Test point-in-time recovery"
      critical: true
      
    - name: "Disaster Drill"
      description: "Simulate complete disaster scenario"
      critical: true
      team_required: true

  # Quarterly compliance
  quarterly:
    - name: "Compliance Audit"
      description: "Verify backup meets compliance requirements"
      standards: ["GDPR", "ISO27001"]
      
    - name: "Documentation Review"
      description: "Update DR documentation"
      
    - name: "Team Training"
      description: "Train team on recovery procedures"
3. Automated Validation Script
python# scripts/validate_backup.py

"""
BACKUP VALIDATION SCRIPT
========================

Performs comprehensive validation of backups:
1. File existence and size checks
2. Compression integrity
3. Checksum verification
4. Database restore test
5. WAL continuity check
6. Remote storage verification
"""

import os
import sys
import gzip
import hashlib
import subprocess
import json
from datetime import datetime, timedelta
from pathlib import Path
import psycopg2
from typing import Dict, List, Optional


class BackupValidator:
    """Validate database and file backups"""
    
    def __init__(self, config_file: str = "config/backup_config.yaml"):
        self.config = self.load_config(config_file)
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "tests": [],
            "passed": 0,
            "failed": 0,
            "warnings": 0
        }
    
    def load_config(self, config_file: str) -> dict:
        """Load backup configuration"""
        import yaml
        with open(config_file, 'r') as f:
            return yaml.safe_load(f)
    
    def log(self, level: str, message: str, **kwargs):
        """Log test result"""
        result = {
            "level": level,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            **kwargs
        }
        
        self.results["tests"].append(result)
        
        if level == "PASS":
            self.results["passed"] += 1
            print(f"✓ {message}")
        elif level == "FAIL":
            self.results["failed"] += 1
            print(f"✗ {message}")
        elif level == "WARN":
            self.results["warnings"] += 1
            print(f"⚠ {message}")
        else:
            print(f"ℹ {message}")
    
    # ============================================
    # FILE VALIDATION
    # ============================================
    
    def test_file_existence(self, backup_dir: str) -> bool:
        """Check if backup files exist"""
        
        if not os.path.exists(backup_dir):
            self.log("FAIL", "Backup directory does not exist", path=backup_dir)
            return False
        
        # Find latest backup
        backups = sorted(Path(backup_dir).glob("*.sql.gz"), reverse=True)
        
        if not backups:
            self.log("FAIL", "No backup files found", directory=backup_dir)
            return False
        
        latest_backup = backups[0]
        age_hours = (datetime.now() - datetime.fromtimestamp(
            latest_backup.stat().st_mtime
        )).total_seconds() / 3600
        
        if age_hours > 25:  # Should be < 24 hours for daily backups
            self.log(
                "WARN",
                f"Latest backup is {age_hours:.1f} hours old",
                file=str(latest_backup)
            )
        else:
            self.log(
                "PASS",
                f"Latest backup found ({age_hours:.1f} hours old)",
                file=str(latest_backup)
            )
        
        return True
    
    def test_file_size(self, backup_file: str, min_size_mb: int = 100) -> bool:
        """Validate backup file size"""
        
        if not os.path.exists(backup_file):
            self.log("FAIL", "Backup file not found", file=backup_file)
            return False
        
        size_mb = os.path.getsize(backup_file) / (1024 * 1024)
        
        if size_mb < min_size_mb:
            self.log(
                "FAIL",
                f"Backup suspiciously small: {size_mb:.1f} MB",
                file=backup_file,
                threshold=f"{min_size_mb} MB"
            )
            return False
        
        self.log(
            "PASS",
            f"Backup size acceptable: {size_mb:.1f} MB",
            file=backup_file
        )
        return True
    
    def test_compression_integrity(self, backup_file: str) -> bool:
        """Test if compressed backup is valid"""
        
        try:
            with gzip.open(backup_file, 'rb') as f:
                # Try to read first chunk
                f.read(1024)
            
            self.log("PASS", "Compression integrity verified", file=backup_file)
            return True
            
        except Exception as e:
            self.log(
                "FAIL",
                f"Compression integrity check failed: {str(e)}",
                file=backup_file
            )
            return False
    
    def test_checksum(self, backup_file: str, checksum_file: str = None) -> bool:
        """Verify file checksum"""
        
        if checksum_file is None:
            checksum_file = f"{backup_file}.sha256"
        
        # Calculate current checksum
        sha256 = hashlib.sha256()
        with open(backup_file, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        
        current_checksum = sha256.hexdigest()
        
        # Compare with stored checksum if exists
        if os.path.exists(checksum_file):
            with open(checksum_file, 'r') as f:
                stored_checksum = f.read().strip().split()[0]
            
            if current_checksum == stored_checksum:
                self.log("PASS", "Checksum verified", file=backup_file)
                return True
            else:
                self.log(
                    "FAIL",
                    "Checksum mismatch",
                    file=backup_file,
                    expected=stored_checksum,
                    actual=current_checksum
                )
                return False
        else:
            # Store checksum for future validation
            with open(checksum_file, 'w') as f:
                f.write(f"{current_checksum}  {os.path.basename(backup_file)}\n")
            
            self.log("PASS", "Checksum calculated and stored", file=backup_file)
            return True
    
    # ============================================
    # DATABASE VALIDATION
    # ============================================
    
    def test_database_restore(
        self,
        backup_file: str,
        test_db_config: dict
    ) -> bool:
        """Test database restore to staging"""
        
        try:
            # Create test database
            self.log("INFO", "Creating test database for restore validation")
            
            admin_conn = psycopg2.connect(
                host=test_db_config['host'],
                port=test_db_config['port'],
                user=test_db_config['user'],
                password=test_db_config['password'],
                database='postgres'
            )
            admin_conn.autocommit = True
            
            with admin_conn.cursor() as cur:
                # Drop if exists
                cur.execute(f"DROP DATABASE IF EXISTS {test_db_config['database']}")
                # Create fresh
                cur.execute(f"CREATE DATABASE {test_db_config['database']}")
            
            admin_conn.close()
            
            # Restore backup
            self.log("INFO", "Restoring backup to test database")
            
            restore_cmd = [
                'gunzip', '-c', backup_file,
                '|',
                'psql',
                '-h', test_db_config['host'],
                '-p', str(test_db_config['port']),
                '-U', test_db_config['user'],
                '-d', test_db_config['database']
            ]
            
            result = subprocess.run(
                ' '.join(restore_cmd),
                shell=True,
                capture_output=True,
                text=True,
                env={**os.environ, 'PGPASSWORD': test_db_config['password']}
            )
            
            if result.returncode != 0:
                self.log(
                    "FAIL",
                    "Database restore failed",
                    error=result.stderr[:500]
                )
                return False
            
            # Validate restored data
            test_conn = psycopg2.connect(**test_db_config)
            
            with test_conn.cursor() as cur:
                # Count tables
                cur.execute("""
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                """)
                table_count = cur.fetchone()[0]
                
                # Check if we have data
                if table_count == 0:
                    self.log("FAIL", "Restored database has no tables")
                    return False
                
                self.log(
                    "PASS",
                    f"Database restored successfully ({table_count} tables)",
                    database=test_db_config['database']
                )
            
            test_conn.close()
            
            # Cleanup test database
            admin_conn = psycopg2.connect(
                host=test_db_config['host'],
                port=test_db_config['port'],
                user=test_db_config['user'],
                password=test_db_config['password'],
                database='postgres'
            )
            admin_conn.autocommit = True
            
            with admin_conn.cursor() as cur:
                cur.execute(f"DROP DATABASE {test_db_config['database']}")
            
            admin_conn.close()
            
            return True
            
        except Exception as e:
            self.log(
                "FAIL",
                f"Database restore test failed: {str(e)}",
                traceback=str(e)
            )
            return False
    
    def test_wal_continuity(self, wal_archive_dir: str) -> bool:
        """Check WAL file continuity"""
        
        try:
            # Get all WAL files
            wal_files = sorted(Path(wal_archive_dir).glob("*.gz"))
            
            if len(wal_files) < 2:
                self.log("WARN", "Not enough WAL files to check continuity")
                return True
            
            # Check for gaps
            gaps = []
            for i in range(len(wal_files) - 1):
                current_file = wal_files[i].stem  # Remove .gz
                next_file = wal_files[i + 1].stem
                
                # WAL files follow pattern: 000000010000000000000001
                # Extract sequence number (last 8 hex digits)
                current_seq = int(current_file[-8:], 16)
                next_seq = int(next_file[-8:], 16)
                
                if next_seq != current_seq + 1:
                    gaps.append((current_file, next_file))
            
            if gaps:
                self.log(
                    "FAIL",
                    f"Found {len(gaps)} gap(s) in WAL archive",
                    gaps=[(f1, f2) for f1, f2 in gaps[:5]]  # Show first 5
                )
                return False
            
            self.log(
                "PASS",
                f"WAL continuity verified ({len(wal_files)} files)",
                directory=wal_archive_dir
            )
            return True
            
        except Exception as e:
            self.log(
                "FAIL",
                f"WAL continuity check failed: {str(e)}"
            )
            return False
    
    # ============================================
    # REMOTE STORAGE VALIDATION
    # ============================================
    
    def test_s3_backups(self, s3_bucket: str, s3_prefix: str) -> bool:
        """Verify backups exist in S3"""
        
        try:
            import boto3
            
            s3 = boto3.client('s3')
            
            # List recent backups
            response = s3.list_objects_v2(
                Bucket=s3_bucket,
                Prefix=s3_prefix,
                MaxKeys=10
            )
            
            if 'Contents' not in response or len(response['Contents']) == 0:
                self.log(
                    "FAIL",
                    "No backups found in S3",
                    bucket=s3_bucket,
                    prefix=s3_prefix
                )
                return False
            
            # Check latest backup age
            latest_backup = max(
                response['Contents'],
                key=lambda x: x['LastModified']
            )
            
            age_hours = (
                datetime.now(latest_backup['LastModified'].tzinfo) -
                latest_backup['LastModified']
            ).total_seconds() / 3600
            
            if age_hours > 25:
                self.log(
                    "WARN",
                    f"Latest S3 backup is {age_hours:.1f} hours old",
                    bucket=s3_bucket,
                    key=latest_backup['Key']
                )
            else:
                self.log(
                    "PASS",
                    f"S3 backups verified ({len(response['Contents'])} files)",
                    bucket=s3_bucket,
                    latest_age_hours=f"{age_hours:.1f}"
                )
            
            return True
            
        except Exception as e:
            self.log(
                "FAIL",
                f"S3 validation failed: {str(e)}",
                bucket=s3_bucket
            )
            return False
    
    # ============================================
    # MAIN VALIDATION RUNNER
    # ============================================
    
    def run_validation(self, level: str = "daily"):
        """Run validation tests based on level"""
        
        print("=" * 60)
        print(f"BACKUP VALIDATION - {level.upper()}")
        print("=" * 60)
        print()
        
        backup_dir = self.config['backup']['storage']['local']['path']
        
        # Daily checks
        if level in ["daily", "weekly", "monthly"]:
            self.test_file_existence(backup_dir)
            
            # Get latest backup
            latest_backup = max(
                Path(backup_dir).glob("*.sql.gz"),
                key=os.path.getmtime,
                default=None
            )
            
            if latest_backup:
                self.test_file_size(str(latest_backup))
                self.test_compression_integrity(str(latest_backup))
                self.test_checksum(str(latest_backup))
        
        # Weekly checks
        if level in ["weekly", "monthly"]:
            if latest_backup:
                # Restore test to staging
                test_db_config = {
                    'host': 'localhost',
                    'port': 5432,
                    'database': 'backup_test',
                    'user': 'postgres',
                    'password': os.getenv('POSTGRES_PASSWORD')
                }
                self.test_database_restore(str(latest_backup), test_db_config)
            
            # WAL continuity
            wal_dir = "/var/lib/postgresql/wal_archive"
            if os.path.exists(wal_dir):
                self.test_wal_continuity(wal_dir)
            
            # S3 verification
            if 'remote' in self.config['backup']['storage']:
                self.test_s3_backups(
                    self.config['backup']['storage']['remote']['bucket'],
                    "backups/postgres"
                )
        
        # Monthly checks
        if level == "monthly":
            self.log("INFO", "Monthly checks - Full restore test recommended")
            self.log("INFO", "Monthly checks - PITR test recommended")
            self.log("INFO", "Monthly checks - Disaster drill recommended")
        
        # Print summary
        print()
        print("=" * 60)
        print("VALIDATION SUMMARY")
        print("=" * 60)
        print(f"Passed:   {self.results['passed']}")
        print(f"Failed:   {self.results['failed']}")
        print(f"Warnings: {self.results['warnings']}")
        print()
        
        # Save results
        results_file = f"validation_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(results_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        print(f"Results saved to: {results_file}")
        
        # Exit code
        if self.results['failed'] > 0:
            sys.exit(1)
        else:
            sys.exit(0)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Validate backups")
    parser.add_argument(
        '--level',
        choices=['daily', 'weekly', 'monthly'],
        default='daily',
        help='Validation level'
    )
    
    args = parser.parse_args()
    
    validator = BackupValidator()
    validator.run_validation(args.level)
4. Cron Jobs for Validation
bash# /etc/cron.d/backup-validation

# Daily validation at 6 AM
0 6 * * * root /usr/local/bin/validate_backup.py --level daily

# Weekly validation on Sundays at 7 AM
0 7 * * 0 root /usr/local/bin/validate_backup.py --level weekly

# Monthly validation on 1st of month at 8 AM
0 8 1 * * root /usr/local/bin/validate_backup.py --level monthly

🚨 DISASTER RECOVERY PLAN
1. Disaster Recovery Framework
python# config/disaster_recovery_plan.py

"""
DISASTER RECOVERY PLAN
======================

This document outlines the procedures for recovering from
various disaster scenarios.
"""

DISASTER_SCENARIOS = {
    # ============================================
    # SCENARIO 1: DATABASE CORRUPTION
    # ============================================
    "database_corruption": {
        "severity": "HIGH",
        "rto": "2 hours",
        "rpo": "15 minutes",
        "detection": [
            "Database won't start",
            "Checksum errors in logs",
            "Query failures",
            "Data inconsistency"
        ],
        "response_team": [
            "DBA Lead",
            "SysAdmin",
            "DevOps Engineer"
        ],
        "recovery_steps": [
            "1. Stop application servers",
            "2. Assess corruption extent",
            "3. Attempt PostgreSQL recovery (pg_resetwal)",
            "4. If fails: Restore from latest backup",
            "5. Apply WAL files for PITR",
            "6. Verify data integrity",
            "7. Restart application",
            "8. Monitor for issues"
        ],
        "rollback_plan": "Keep corrupted database for forensics",
        "post_mortem": "Required - identify root cause"
    },
    
    # ============================================
    # SCENARIO 2: ACCIDENTAL DATA DELETION
    # ============================================
    "accidental_deletion": {
        "severity": "MEDIUM",
        "rto": "1 hour",
        "rpo": "5 minutes",
        "detection": [
            "User reports missing data",
            "Unexpected row count drop",
            "Application errors"
        ],
        "response_team": [
            "DBA Lead",
            "Application Developer"
        ],
        "recovery_steps": [
            "1. Identify deletion time",
            "2. Stop further writes to affected tables",
            "3. Perform PITR to just before deletion",
            "4. Extract deleted data",
            "5. Re-insert to production",
            "6. Verify data consistency",
            "7. Resume normal operations"
        ],
        "prevention": [
            "Implement soft deletes",
            "Add DELETE confirmation prompts",
            "Row-level audit logging"
        ]
    },
    
    # ============================================
    # SCENARIO 3: HARDWARE FAILURE
    # ============================================
    "hardware_failure": {
        "severity": "CRITICAL",
        "rto": "4 hours",
        "rpo": "15 minutes",
        "detection": [
            "Server unresponsive",
            "Disk I/O errors",
            "Hardware monitoring alerts"
        ],
        "response_team": [
            "SysAdmin",
            "DBA Lead",
            "DevOps Engineer",
            "Hardware Vendor (if under warranty)"
        ],
        "recovery_steps": [
            "1. Provision replacement hardware",
            "2. Install OS and PostgreSQL",
            "3. Restore latest base backup",
            "4. Apply WAL files",
            "5. Update DNS/Load balancer",
            "6. Verify service",
            "7. Monitor performance"
        ],
        "prevention": [
            "RAID configuration",
            "Hardware monitoring",
            "Regular maintenance",
            "Hot standby server"
        ]
    },
    
    # ============================================
    # SCENARIO 4: RANSOMWARE ATTACK
    # ============================================
    "ransomware": {
        "severity": "CRITICAL",
        "rto": "8 hours",
        "rpo": "1 hour",  # Use older backup (pre-infection)
        "detection": [
            "Files encrypted",
            "Ransom note",
            "Unusual file modifications",
            "Suspicious process activity"
        ],
        "response_team": [
            "Security Team",
            "DBA Lead",
            "SysAdmin",
            "Legal/Management"
        ],
        "recovery_steps": [
            "1. ISOLATE INFECTED SYSTEMS",
            "2. DO NOT pay ransom",
            "3. Identify infection point",
            "4. Provision clean hardware",
            "5. Restore from backup BEFORE infection",
            "6. Verify backup integrity",
            "7. Scan for malware",
            "8. Restore service",
            "9. Implement additional security"
        ],
        "prevention": [
            "Immutable backups",
            "Offsite/offline backups",
            "Network segmentation",
            "Security monitoring",
            "Regular security audits"
        ],
        "compliance": "Report to authorities if required"
    },
    
    # ============================================
    # SCENARIO 5: SITE DISASTER (FIRE/FLOOD)
    # ============================================
    "site_disaster": {
        "severity": "CRITICAL",
        "rto": "24 hours",
        "rpo": "1 hour",
        "detection": [
            "Physical site inaccessible",
            "All services down",
            "News reports"
        ],
        "response_team": [
            "All hands on deck",
            "Management",
            "DR Coordinator"
        ],
        "recovery_steps": [
            "1. Activate DR site/cloud failover",
            "2. Provision new infrastructure",
            "3. Restore from offsite backups",
            "4. Update DNS to new location",
            "5. Restore all services",
            "6. Notify stakeholders",
            "7. Assess permanent relocation"
        ],
        "prevention": [
            "Geographic redundancy",
            "Cloud backup strategy",
            "Regular DR drills",
            "Hot standby in different location"
        ]
    }
}


# ============================================
# RECOVERY PROCEDURES BY TYPE
# ============================================

RECOVERY_PROCEDURES = {
    "full_restore": {
        "description": "Complete database restore from backup",
        "when_to_use": "Total data loss, corruption, disaster",
        "steps": "See restoration_procedures.md"
    },
    
    "pitr": {
        "description": "Point-in-time recovery",
        "when_to_use": "Accidental deletion, need specific timestamp",
        "steps": "See pitr_recovery.sh"
    },
    
    "table_restore": {
        "description": "Restore specific table(s)",
        "when_to_use": "Isolated table corruption/deletion",
        "steps": "See table_restore.sh"
    },
    
    "file_restore": {
        "description": "Restore files from backup",
        "when_to_use": "File deletion, corruption",
        "steps": "See file_restore.sh"
    }
}
2. DR Runbook Template
markdown# DISASTER RECOVERY RUNBOOK

## 🚨 EMERGENCY CONTACTS

| Role | Name | Phone | Email | Backup |
|------|------|-------|-------|--------|
| DR Coordinator | John Doe | +49... | john@company.de | Jane Doe |
| DBA Lead | Jane Smith | +49... | jane@company.de | Bob Lee |
| SysAdmin | Bob Lee | +49... | bob@company.de | Alice Kim |
| DevOps | Alice Kim | +49... | alice@company.de | John Doe |
| Management | CEO | +49... | ceo@company.de | CTO |

## 📞 VENDOR CONTACTS

| Vendor | Service | Support Phone | Account # |
|--------|---------|---------------|-----------|
| AWS | Cloud Infrastructure | +1-... | 123456 |
| ISP | Internet | +49... | ISP-789 |
| Hardware Vendor | Servers | +49... | HW-456 |

---

## 🎯 INITIAL RESPONSE (FIRST 15 MINUTES)

### Step 1: Assess Situation
- [ ] What happened? (corruption, deletion, hardware, attack, disaster)
- [ ] When did it happen?
- [ ] What systems are affected?
- [ ] Are users impacted?
- [ ] Is data at risk?

### Step 2: Notify Team
- [ ] Alert DR Coordinator
- [ ] Page on-call engineer
- [ ] Notify management if critical
- [ ] Start incident log

### Step 3: Immediate Actions
- [ ] STOP further damage if possible
- [ ] Isolate affected systems if security incident
- [ ] Enable maintenance mode if needed
- [ ] Begin documenting everything

---

## 🔧 RECOVERY PROCEDURES BY SCENARIO

### DATABASE CORRUPTION

**Detection:**
- Database won't start
- Checksum errors in logs
- Widespread query failures

**Response:**
```bash
# 1. Stop application
systemctl stop myapp

# 2. Attempt automatic recovery
sudo -u postgres /usr/local/bin/attempt_recovery.sh

# 3. If fails, restore from backup
sudo -u postgres /usr/local/bin/full_restore.sh

# 4. Verify
sudo -u postgres psql -c "SELECT COUNT(*) FROM critical_table;"

# 5. Start application
systemctl start myapp
```

**Validation:**
- [ ] Database starts successfully
- [ ] All tables accessible
- [ ] Row counts match expected
- [ ] Application functions normally

---

### ACCIDENTAL DATA DELETION

**Detection:**
- User reports missing data
- Row count drop

**Response:**
```bash
# 1. Determine deletion time
# Check application logs, audit logs

# 2. Perform PITR
sudo -u postgres /usr/local/bin/pitr_recovery.sh "2024-01-15 14:25:00"

# 3. Extract deleted data
sudo -u postgres /usr/local/bin/extract_deleted_data.sh

# 4. Re-insert to production
psql -U postgres -d production < deleted_data.sql
```

**Validation:**
- [ ] Deleted data restored
- [ ] No data duplication
- [ ] Referential integrity intact

---

## 📊 POST-INCIDENT CHECKLIST

### Immediate (Within 24 hours)
- [ ] Document incident timeline
- [ ] Verify all systems operational
- [ ] Notify stakeholders of resolution
- [ ] Schedule team debrief

### Short-term (Within 1 week)
- [ ] Complete incident report
- [ ] Identify root cause
- [ ] Update runbooks if needed
- [ ] Implement prevention measures

### Long-term (Within 1 month)
- [ ] Post-mortem meeting
- [ ] Review DR plan
- [ ] Update training materials
- [ ] Test improved procedures
3. Incident Response Template
python# scripts/incident_report.py

"""
Incident Report Generator

Creates structured incident reports for disaster recovery events.
"""

import json
from datetime import datetime
from typing import List, Dict


class IncidentReport:
    """Generate incident reports"""
    
    def __init__(self):
        self.report = {
            "incident_id": self.generate_incident_id(),
            "timestamp": datetime.now().isoformat(),
            "severity": None,
            "status": "OPEN",
            "detection": {},
            "impact": {},
            "response": {},
            "resolution": {},
            "timeline": [],
            "root_cause": None,
            "prevention": []
        }
    
    def generate_incident_id(self) -> str:
        """Generate unique incident ID"""
        return f"INC-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    
    def set_severity(self, severity: str):
        """Set incident severity: LOW, MEDIUM, HIGH, CRITICAL"""
        self.report["severity"] = severity
    
    def add_timeline_event(self, event: str, timestamp: datetime = None):
        """Add event to timeline"""
        if timestamp is None:
            timestamp = datetime.now()
        
        self.report["timeline"].append({
            "timestamp": timestamp.isoformat(),
            "event": event
        })
    
    def set_detection(self, how_detected: str, detected_by: str, detected_at: datetime):
        """Record detection details"""
        self.report["detection"] = {
            "how": how_detected,
            "by": detected_by,
            "at": detected_at.isoformat()
        }
    
    def set_impact(
        self,
        affected_systems: List[str],
        data_loss: str,
        downtime_minutes: int,
        users_affected: int
    ):
        """Record impact details"""
        self.report["impact"] = {
            "affected_systems": affected_systems,
            "data_loss": data_loss,
            "downtime_minutes": downtime_minutes,
            "users_affected": users_affected
        }
    
    def set_response(
        self,
        team_members: List[str],
        actions_taken: List[str],
        recovery_method: str
    ):
        """Record response details"""
        self.report["response"] = {
            "team": team_members,
            "actions": actions_taken,
            "recovery_method": recovery_method
        }
    
    def set_resolution(
        self,
        resolved_at: datetime,
        verification_steps: List[str],
        data_recovered: bool
    ):
        """Record resolution details"""
        self.report["resolution"] = {
            "resolved_at": resolved_at.isoformat(),
            "verification": verification_steps,
            "data_recovered": data_recovered
        }
        self.report["status"] = "RESOLVED"
    
    def set_root_cause(self, cause: str, contributing_factors: List[str]):
        """Document root cause analysis"""
        self.report["root_cause"] = {
            "primary_cause": cause,
            "contributing_factors": contributing_factors
        }
    
    def add_prevention_measure(self, measure: str):
        """Add prevention measure"""
        self.report["prevention"].append(measure)
    
    def generate_report(self, output_file: str = None):
        """Generate and save report"""
        
        if output_file is None:
            output_file = f"incident_report_{self.report['incident_id']}.json"
        
        with open(output_file, 'w') as f:
            json.dump(self.report, f, indent=2)
        
        print(f"Incident report generated: {output_file}")
        return output_file
    
    def generate_summary(self) -> str:
        """Generate human-readable summary"""
        
        summary = f"""
================================================================================
                        INCIDENT REPORT SUMMARY
================================================================================

Incident ID:     {self.report['incident_id']}
Severity:        {self.report['severity']}
Status:          {self.report['status']}

DETECTION
---------
How:             {self.report['detection'].get('how', 'N/A')}
By:              {self.report['detection'].get('by', 'N/A')}
When:            {self.report['detection'].get('at', 'N/A')}

IMPACT
------
Systems:         {', '.join(self.report['impact'].get('affected_systems', []))}
Data Loss:       {self.report['impact'].get('data_loss', 'N/A')}
Downtime:        {self.report['impact'].get('downtime_minutes', 0)} minutes
Users Affected:  {self.report['impact'].get('users_affected', 0)}

RESPONSE
--------
Team:            {', '.join(self.report['response'].get('team', []))}
Recovery Method: {self.report['response'].get('recovery_method', 'N/A')}

ROOT CAUSE
----------
{self.report.get('root_cause', {}).get('primary_cause', 'Analysis pending')}

PREVENTION MEASURES
-------------------
"""
        for i, measure in enumerate(self.report['prevention'], 1):
            summary += f"{i}. {measure}\n"
        
        summary += "\n" + "=" * 80 + "\n"
        
        return summary


# Example usage
if __name__ == "__main__":
    report = IncidentReport()
    
    # Set details
    report.set_severity("HIGH")
    report.add_timeline_event("Database corruption detected")
    report.set_detection(
        how_detected="Monitoring alert",
        detected_by="Prometheus",
        detected_at=datetime(2024, 1, 15, 14, 30)
    )
    report.set_impact(
        affected_systems=["PostgreSQL", "API"],
        data_loss="None - recovered via PITR",
        downtime_minutes=45,
        users_affected=150
    )
    report.set_response(
        team_members=["DBA Lead", "SysAdmin"],
        actions_taken=[
            "Stopped application servers",
            "Performed PITR to 14:25",
            "Verified data integrity",
            "Restarted services"
        ],
        recovery_method="Point-in-Time Recovery"
    )
    report.set_resolution(
        resolved_at=datetime(2024, 1, 15, 15, 15),
        verification_steps=[
            "Database accessible",
            "Row counts verified",
            "Application functional"
        ],
        data_recovered=True
    )
    report.set_root_cause(
        cause="Hardware fault causing disk errors",
        contributing_factors=[
            "Aging hardware (5 years old)",
            "No RAID configuration",
            "Delayed hardware monitoring alerts"
        ]
    )
    report.add_prevention_measure("Implement RAID 10")
    report.add_prevention_measure("Replace aging hardware")
    report.add_prevention_measure("Improve monitoring sensitivity")
    
    # Generate
    report.generate_report()
    print(report.generate_summary())

⏱️ RTO/RPO DEFINITIONS
1. Understanding RTO and RPO
python# config/rto_rpo.py

"""
RTO (Recovery Time Objective) vs RPO (Recovery Point Objective)
================================================================

RTO: How long can you afford to be down?
RPO: How much data can you afford to lose?

Example:
- RTO = 4 hours: System must be back online within 4 hours
- RPO = 15 minutes: Can lose max 15 minutes of data
"""

# ============================================
# RTO/RPO MATRIX BY SYSTEM CRITICALITY
# ============================================

RTO_RPO_MATRIX = {
    # Mission Critical Systems
    "tier_1_critical": {
        "description": "Core business systems, revenue-generating",
        "examples": ["E-commerce database", "Payment processing"],
        "rto": "15 minutes",
        "rpo": "< 1 minute",
        "backup_strategy": {
            "primary": "Hot standby with streaming replication",
            "secondary": "Continuous WAL archiving",
            "testing": "Weekly failover tests"
        },
        "cost_impact": "HIGH - Requires redundancy"
    },
    
    # Business Critical
    "tier_2_important": {
        "description": "Important business systems",
        "examples": ["CRM", "Inventory system", "Customer portal"],
        "rto": "1 hour",
        "rpo": "5 minutes",
        "backup_strategy": {
            "primary": "WAL archiving every 5 minutes",
            "secondary": "Daily full backup",
            "testing": "Monthly restore tests"
        },
        "cost_impact": "MEDIUM - Balanced approach"
    },
    
    # Important but not critical
    "tier_3_standard": {
        "description": "Standard business systems",
        "examples": ["Internal tools", "Reporting systems"],
        "rto": "4 hours",
        "rpo": "15 minutes",
        "backup_strategy": {
            "primary": "Daily full backup",
            "secondary": "WAL archiving",
            "testing": "Quarterly restore tests"
        },
        "cost_impact": "LOW - Cost-effective"
    },
    
    # Non-critical
    "tier_4_non_critical": {
        "description": "Development, testing, analytics",
        "examples": ["Dev environment", "Analytics DB"],
        "rto": "24 hours",
        "rpo": "24 hours",
        "backup_strategy": {
            "primary": "Daily backup",
            "secondary": "None",
            "testing": "Annual or on-demand"
        },
        "cost_impact": "MINIMAL"
    }
}


# ============================================
# CALCULATING COSTS
# ============================================

def calculate_downtime_cost(
    revenue_per_hour: float,
    rto_hours: float,
    probability_per_year: float = 1.0
) -> dict:
    """
    Calculate cost of downtime
    
    Args:
        revenue_per_hour: Average revenue per hour
        rto_hours: Recovery time in hours
        probability_per_year: Expected disasters per year
    
    Returns:
        Cost breakdown
    """
    
    # Direct revenue loss
    direct_loss = revenue_per_hour * rto_hours * probability_per_year
    
    # Indirect costs (estimated)
    productivity_loss = direct_loss * 0.3  # 30% additional
    reputation_damage = direct_loss * 0.5  # 50% additional
    
    total_cost = direct_loss + productivity_loss + reputation_damage
    
    return {
        "direct_revenue_loss": direct_loss,
        "productivity_loss": productivity_loss,
        "reputation_damage": reputation_damage,
        "total_annual_cost": total_cost,
        "cost_per_incident": total_cost / probability_per_year
    }


def calculate_data_loss_cost(
    rpoh_minutes: float,
    transactions_per_minute: float,
    value_per_transaction: float,
    probability_per_year: float = 1.0
) -> float:
    """
    Calculate cost of data loss
    
    Args:
        rpo_minutes: Recovery point objective in minutes
        transactions_per_minute: Average transactions per minute
        value_per_transaction: Average value per transaction
        probability_per_year: Expected disasters per year
    
    Returns:
        Annual cost of data loss
    """
    
    transactions_lost = rpo_minutes * transactions_per_minute
    cost_per_incident = transactions_lost * value_per_transaction
    annual_cost = cost_per_incident * probability_per_year
    
    return annual_cost


# Example calculation
if __name__ == "__main__":
    # E-commerce site
    revenue_per_hour = 50000  # €50k/hour
    rto_hours = 4
    disasters_per_year = 0.5  # Once every 2 years
    
    downtime_cost = calculate_downtime_cost(
        revenue_per_hour,
        rto_hours,
        disasters_per_year
    )
    
    print("Downtime Cost Analysis")
    print("=" * 50)
    print(f"Direct Loss:      €{downtime_cost['direct_revenue_loss']:,.2f}")
    print(f"Productivity:     €{downtime_cost['productivity_loss']:,.2f}")
    print(f"Reputation:       €{downtime_cost['reputation_damage']:,.2f}")
    print(f"Total Annual:     €{downtime_cost['total_annual_cost']:,.2f}")
    print(f"Per Incident:     €{downtime_cost['cost_per_incident']:,.2f}")
    
    # Data loss
    rpo_minutes = 15
    transactions_per_minute = 10
    value_per_transaction = 100  # €100 average order
    
    data_loss_cost = calculate_data_loss_cost(
        rpo_minutes,
        transactions_per_minute,
        value_per_transaction,
        disasters_per_year
    )
    
    print(f"\nData Loss Cost:   €{data_loss_cost:,.2f}/year")
    
    # Investment justification
    print("\n" + "=" * 50)
    print("Investment Justification")
    print("=" * 50)
    total_risk = downtime_cost['total_annual_cost'] + data_loss_cost
    print(f"Total Annual Risk: €{total_risk:,.2f}")
    print(f"\nJustifiable DR Investment: €{total_risk * 0.1:,.2f} - €{total_risk * 0.3:,.2f}")
    print("(10-30% of total annual risk)")
2. RTO/RPO Monitoring
python# scripts/monitor_rto_rpo.py

"""
RTO/RPO Monitoring Script

Tracks and reports on RTO/RPO compliance.
"""

import psycopg2
from datetime import datetime, timedelta
import os
from pathlib import Path


class RTORPOMonitor:
    """Monitor RTO/RPO compliance"""
    
    def __init__(self, config):
        self.config = config
        self.alerts = []
    
    def check_backup_freshness(self) -> dict:
        """Check if backups meet RPO requirements"""
        
        backup_dir = self.config['backup_dir']
        rpo_minutes = self.config['rpo_minutes']
        
        # Find latest backup
        latest_backup = max(
            Path(backup_dir).glob("*.sql.gz"),
            key=os.path.getmtime,
            default=None
        )
        
        if not latest_backup:
            self.alerts.append({
                "severity": "CRITICAL",
                "message": "No backups found!"
            })
            return {"compliant": False, "age_minutes": None}
        
        # Check age
        backup_time = datetime.fromtimestamp(latest_backup.stat().st_mtime)
        age_minutes = (datetime.now() - backup_time).total_seconds() / 60
        
        compliant = age_minutes <= rpo_minutes * 1.5  # 50% tolerance
        
        if not compliant:
            self.alerts.append({
                "severity": "WARNING",
                "message": f"Backup age ({age_minutes:.0f} min) exceeds RPO ({rpo_minutes} min)"
            })
        
        return {
            "compliant": compliant,
            "age_minutes": age_minutes,
            "rpo_minutes": rpo_minutes,
            "latest_backup": str(latest_backup)
        }
    
    def check_wal_continuity(self) -> dict:
        """Check WAL archiving meets RPO"""
        
        wal_dir = self.config['wal_archive_dir']
        rpo_minutes = self.config['rpo_minutes']
        
        # Find latest WAL
        latest_wal = max(
            Path(wal_dir).glob("*.gz"),
            key=os.path.getmtime,
            default=None
        )
        
        if not latest_wal:
            self.alerts.append({
                "severity": "CRITICAL",
                "message": "No WAL files found!"
            })
            return {"compliant": False}
        
        # Check age
        wal_time = datetime.fromtimestamp(latest_wal.stat().st_mtime)
        age_minutes = (datetime.now() - wal_time).total_seconds() / 60
        
        compliant = age_minutes <= rpo_minutes
        
        if not compliant:
            self.alerts.append({
                "severity": "CRITICAL",
                "message": f"WAL age ({age_minutes:.0f} min) exceeds RPO ({rpo_minutes} min)"
            })
        
        return {
            "compliant": compliant,
            "age_minutes": age_minutes,
            "latest_wal": str(latest_wal)
        }
    
    def estimate_recovery_time(self) -> dict:
        """Estimate current RTO"""
        
        # Factors affecting RTO:
        # 1. Backup size
        # 2. Restore speed (measured)
        # 3. WAL replay time
        
        backup_dir = self.config['backup_dir']
        restore_speed_mbps = self.config.get('restore_speed_mbps', 100)  # MB/s
        
        latest_backup = max(
            Path(backup_dir).glob("*.sql.gz"),
            key=os.path.getmtime,
            default=None
        )
        
        if not latest_backup:
            return {"estimated_rto_minutes": None}
        
        # Get backup size
        backup_size_mb = latest_backup.stat().st_size / (1024 * 1024)
        
        # Estimate restore time
        restore_time_minutes = (backup_size_mb / restore_speed_mbps) / 60
        
        # Add overhead (decompression, indexing, etc.)
        overhead_minutes = restore_time_minutes * 0.3
        
        # Add WAL replay time (estimate)
        wal_replay_minutes = 5
        
        total_rto_minutes = restore_time_minutes + overhead_minutes + wal_replay_minutes
        
        rto_target = self.config['rto_minutes']
        compliant = total_rto_minutes <= rto_target
        
        if not compliant:
            self.alerts.append({
                "severity": "WARNING",
                "message": f"Estimated RTO ({total_rto_minutes:.0f} min) exceeds target ({rto_target} min)"
            })
        
        return {
            "estimated_rto_minutes": total_rto_minutes,
            "rto_target_minutes": rto_target,
            "compliant": compliant,
            "backup_size_mb": backup_size_mb
        }
    
    def generate_report(self):
        """Generate compliance report"""
        
        print("=" * 60)
        print("RTO/RPO COMPLIANCE REPORT")
        print("=" * 60)
        print()
        
        # Check RPO (backup freshness)
        backup_check = self.check_backup_freshness()
        print("BACKUP FRESHNESS (RPO)")
        print("-" * 60)
        print(f"RPO Target:       {self.config['rpo_minutes']} minutes")
        print(f"Latest Backup:    {backup_check['age_minutes']:.0f} minutes ago")
        print(f"Status:           {'✓ COMPLIANT' if backup_check['compliant'] else '✗ NON-COMPLIANT'}")
        print()
        
        # Check WAL archiving
        wal_check = self.check_wal_continuity()
        print("WAL ARCHIVING (RPO)")
        print("-" * 60)
        print(f"Latest WAL:       {wal_check['age_minutes']:.0f} minutes ago")
        print(f"Status:           {'✓ COMPLIANT' if wal_check['compliant'] else '✗ NON-COMPLIANT'}")
        print()
        
        # Estimate RTO
        rto_check = self.estimate_recovery_time()
        print("RECOVERY TIME ESTIMATE (RTO)")
        print("-" * 60)
        print(f"RTO Target:       {self.config['rto_minutes']} minutes")
        print(f"Estimated RTO:    {rto_check['estimated_rto_minutes']:.0f} minutes")
        print(f"Backup Size:      {rto_check['backup_size_mb']:.0f} MB")
        print(f"Status:           {'✓ COMPLIANT' if rto_check['compliant'] else '✗ NON-COMPLIANT'}")
        print()
        
        # Alerts
        if self.alerts:
            print("ALERTS")
            print("-" * 60)
            for alert in self.alerts:
                print(f"[{alert['severity']}] {alert['message']}")
            print()
        
        print("=" * 60)


if __name__ == "__main__":
    config = {
        "backup_dir": "/var/backups/postgres",
        "wal_archive_dir": "/var/lib/postgresql/wal_archive",
        "rpo_minutes": 15,
        "rto_minutes": 240,  # 4 hours
        "restore_speed_mbps": 100
    }
    
    monitor = RTORPOMonitor(config)
    monitor.generate_report()

📦 BACKUP & DISASTER RECOVERY GUIDE - TEIL 3
Restoration Procedures, Monitoring & Best Practices

📋 TABLE OF CONTENTS (TEIL 3)

Restoration Procedures
Monitoring & Alerting
Best Practices Summary
Checklists & Quick Reference


🔄 RESTORATION PROCEDURES
1. Full Database Restore
bash#!/bin/bash
# scripts/full_restore.sh

# ============================================
# FULL DATABASE RESTORE SCRIPT
# ============================================
#
# This script performs a complete database restore
# from a backup file.
#
# Usage:
#   ./full_restore.sh /path/to/backup.sql.gz
#   ./full_restore.sh --latest
#   ./full_restore.sh --date 2024-01-15
#
# WARNING: This will REPLACE the entire database!
# ============================================

set -euo pipefail

# ============================================
# CONFIGURATION
# ============================================

DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-myapp}"
DB_USER="${DB_USER:-postgres}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/postgres}"
LOG_FILE="/var/log/postgres/restore.log"

# ============================================
# LOGGING
# ============================================

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" | tee -a "$LOG_FILE" >&2
}

# ============================================
# PARSE ARGUMENTS
# ============================================

BACKUP_FILE=""

case "${1:-}" in
    --latest)
        log "Finding latest backup..."
        BACKUP_FILE=$(ls -1t "$BACKUP_DIR"/*.sql.gz 2>/dev/null | head -n1)
        if [ -z "$BACKUP_FILE" ]; then
            log_error "No backup files found in $BACKUP_DIR"
            exit 1
        fi
        ;;
    --date)
        if [ -z "${2:-}" ]; then
            log_error "Date required. Usage: --date 2024-01-15"
            exit 1
        fi
        DATE=$2
        BACKUP_FILE=$(ls -1 "$BACKUP_DIR"/*${DATE}*.sql.gz 2>/dev/null | head -n1)
        if [ -z "$BACKUP_FILE" ]; then
            log_error "No backup found for date: $DATE"
            exit 1
        fi
        ;;
    *)
        if [ -z "${1:-}" ]; then
            log_error "Usage: $0 <backup_file> | --latest | --date YYYY-MM-DD"
            exit 1
        fi
        BACKUP_FILE=$1
        if [ ! -f "$BACKUP_FILE" ]; then
            log_error "Backup file not found: $BACKUP_FILE"
            exit 1
        fi
        ;;
esac

log "=========================================="
log "FULL DATABASE RESTORE"
log "=========================================="
log "Backup file: $BACKUP_FILE"
log "Database: $DB_NAME"
log "Host: $DB_HOST"

# ============================================
# SAFETY CHECKS
# ============================================

log "Performing safety checks..."

# Check if PostgreSQL is running
if ! pg_isready -h "$DB_HOST" -p "$DB_PORT" > /dev/null 2>&1; then
    log_error "PostgreSQL is not running on $DB_HOST:$DB_PORT"
    exit 1
fi

# Check backup file integrity
log "Verifying backup integrity..."
if ! gzip -t "$BACKUP_FILE"; then
    log_error "Backup file is corrupted: $BACKUP_FILE"
    exit 1
fi

log "✓ All safety checks passed"

# ============================================
# CONFIRMATION
# ============================================

log ""
log "⚠️  WARNING: This will COMPLETELY REPLACE the database!"
log "   Database: $DB_NAME"
log "   Backup: $(basename $BACKUP_FILE)"
log ""

if [ "${SKIP_CONFIRM:-}" != "yes" ]; then
    read -p "Are you sure you want to continue? (yes/no): " -r
    if [[ ! $REPLY =~ ^yes$ ]]; then
        log "Restore cancelled by user"
        exit 0
    fi
fi

# ============================================
# PRE-RESTORE BACKUP (SAFETY)
# ============================================

log "Creating safety backup of current database..."

SAFETY_BACKUP="${BACKUP_DIR}/pre_restore_safety_$(date +%Y%m%d_%H%M%S).sql.gz"

export PGPASSWORD="${DB_PASSWORD}"

pg_dump \
    --host="$DB_HOST" \
    --port="$DB_PORT" \
    --username="$DB_USER" \
    --dbname="$DB_NAME" \
    --format=plain \
    --no-owner \
    --no-acl \
    2>> "$LOG_FILE" \
    | gzip > "$SAFETY_BACKUP"

if [ $? -eq 0 ]; then
    log "✓ Safety backup created: $SAFETY_BACKUP"
else
    log_error "Failed to create safety backup!"
    exit 1
fi

# ============================================
# STOP APPLICATION
# ============================================

log "Stopping application servers..."

# Stop your application (customize this)
if systemctl is-active --quiet myapp; then
    systemctl stop myapp
    log "✓ Application stopped"
fi

# ============================================
# TERMINATE CONNECTIONS
# ============================================

log "Terminating active connections to database..."

psql \
    --host="$DB_HOST" \
    --port="$DB_PORT" \
    --username="$DB_USER" \
    --dbname="postgres" \
    --command="
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE datname = '$DB_NAME'
          AND pid <> pg_backend_pid();
    " \
    2>> "$LOG_FILE"

log "✓ Connections terminated"

# ============================================
# DROP AND RECREATE DATABASE
# ============================================

log "Dropping existing database..."

psql \
    --host="$DB_HOST" \
    --port="$DB_PORT" \
    --username="$DB_USER" \
    --dbname="postgres" \
    --command="DROP DATABASE IF EXISTS $DB_NAME;" \
    2>> "$LOG_FILE"

log "Creating fresh database..."

psql \
    --host="$DB_HOST" \
    --port="$DB_PORT" \
    --username="$DB_USER" \
    --dbname="postgres" \
    --command="CREATE DATABASE $DB_NAME;" \
    2>> "$LOG_FILE"

log "✓ Database recreated"

# ============================================
# RESTORE BACKUP
# ============================================

log "Starting restore process..."
log "This may take several minutes..."

START_TIME=$(date +%s)

gunzip -c "$BACKUP_FILE" | \
    psql \
        --host="$DB_HOST" \
        --port="$DB_PORT" \
        --username="$DB_USER" \
        --dbname="$DB_NAME" \
        --single-transaction \
        2>> "$LOG_FILE"

RESTORE_EXIT_CODE=$?

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

if [ $RESTORE_EXIT_CODE -ne 0 ]; then
    log_error "Restore failed! Check log: $LOG_FILE"
    log_error "You can restore the safety backup: $SAFETY_BACKUP"
    exit 1
fi

log "✓ Restore completed in ${DURATION}s"

# ============================================
# POST-RESTORE VALIDATION
# ============================================

log "Validating restored database..."

# Check if database exists
DB_EXISTS=$(psql \
    --host="$DB_HOST" \
    --port="$DB_PORT" \
    --username="$DB_USER" \
    --dbname="postgres" \
    --tuples-only \
    --command="SELECT 1 FROM pg_database WHERE datname = '$DB_NAME';" \
    2>> "$LOG_FILE")

if [ -z "$DB_EXISTS" ]; then
    log_error "Database does not exist after restore!"
    exit 1
fi

# Count tables
TABLE_COUNT=$(psql \
    --host="$DB_HOST" \
    --port="$DB_PORT" \
    --username="$DB_USER" \
    --dbname="$DB_NAME" \
    --tuples-only \
    --command="SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" \
    2>> "$LOG_FILE" | xargs)

log "✓ Database contains $TABLE_COUNT tables"

# Test connectivity
if psql \
    --host="$DB_HOST" \
    --port="$DB_PORT" \
    --username="$DB_USER" \
    --dbname="$DB_NAME" \
    --command="SELECT 1;" \
    > /dev/null 2>&1; then
    log "✓ Database connectivity verified"
else
    log_error "Database connectivity test failed!"
    exit 1
fi

# ============================================
# ANALYZE DATABASE
# ============================================

log "Analyzing database for optimal performance..."

psql \
    --host="$DB_HOST" \
    --port="$DB_PORT" \
    --username="$DB_USER" \
    --dbname="$DB_NAME" \
    --command="ANALYZE;" \
    2>> "$LOG_FILE"

log "✓ Database analyzed"

# ============================================
# RESTART APPLICATION
# ============================================

log "Restarting application..."

if [ -f /etc/systemd/system/myapp.service ]; then
    systemctl start myapp
    sleep 5
    
    if systemctl is-active --quiet myapp; then
        log "✓ Application restarted successfully"
    else
        log_error "Application failed to start!"
        log "Check application logs for details"
    fi
fi

# ============================================
# CLEANUP
# ============================================

log "Cleaning up temporary files..."

unset PGPASSWORD

# Optional: Remove safety backup after successful restore
# rm -f "$SAFETY_BACKUP"

# ============================================
# SUMMARY
# ============================================

log "=========================================="
log "RESTORE COMPLETED SUCCESSFULLY"
log "=========================================="
log "Duration: ${DURATION}s"
log "Tables restored: $TABLE_COUNT"
log "Safety backup: $SAFETY_BACKUP"
log ""
log "Next steps:"
log "1. Verify application functionality"
log "2. Check critical data"
log "3. Monitor for issues"
log "4. Remove safety backup: rm $SAFETY_BACKUP"
log "=========================================="
2. Table-Level Restore
bash#!/bin/bash
# scripts/restore_table.sh

# ============================================
# TABLE-LEVEL RESTORE SCRIPT
# ============================================
#
# Restore specific table(s) from backup without
# affecting the rest of the database.
#
# Usage:
#   ./restore_table.sh backup.sql.gz users
#   ./restore_table.sh backup.sql.gz users,orders
# ============================================

set -euo pipefail

# Configuration
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-myapp}"
DB_USER="${DB_USER:-postgres}"
LOG_FILE="/var/log/postgres/table_restore.log"

# Parse arguments
BACKUP_FILE="$1"
TABLES="$2"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "=========================================="
log "TABLE-LEVEL RESTORE"
log "=========================================="
log "Backup: $BACKUP_FILE"
log "Tables: $TABLES"

# Verify backup
if ! gzip -t "$BACKUP_FILE"; then
    log "ERROR: Backup file corrupted"
    exit 1
fi

export PGPASSWORD="${DB_PASSWORD}"

# Create temporary restore database
TEMP_DB="temp_restore_$$"

log "Creating temporary database..."

psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres \
    -c "CREATE DATABASE $TEMP_DB;" 2>> "$LOG_FILE"

# Restore to temporary database
log "Restoring backup to temporary database..."

gunzip -c "$BACKUP_FILE" | \
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$TEMP_DB" \
    2>> "$LOG_FILE"

# For each table
IFS=',' read -ra TABLE_ARRAY <<< "$TABLES"

for TABLE in "${TABLE_ARRAY[@]}"; do
    TABLE=$(echo "$TABLE" | xargs)  # Trim whitespace
    
    log "Restoring table: $TABLE"
    
    # Backup current table (safety)
    log "  Creating safety backup..."
    pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        -t "$TABLE" --format=plain \
        > "/tmp/${TABLE}_backup_$(date +%Y%m%d_%H%M%S).sql" 2>> "$LOG_FILE"
    
    # Drop existing table
    log "  Dropping existing table..."
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        -c "DROP TABLE IF EXISTS $TABLE CASCADE;" 2>> "$LOG_FILE"
    
    # Restore table from temp database
    log "  Restoring from backup..."
    pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$TEMP_DB" \
        -t "$TABLE" --format=plain | \
        psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        2>> "$LOG_FILE"
    
    # Verify
    ROW_COUNT=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        -t -c "SELECT COUNT(*) FROM $TABLE;" | xargs)
    
    log "  ✓ Restored $ROW_COUNT rows"
done

# Cleanup temporary database
log "Cleaning up temporary database..."
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres \
    -c "DROP DATABASE $TEMP_DB;" 2>> "$LOG_FILE"

unset PGPASSWORD

log "=========================================="
log "TABLE RESTORE COMPLETED"
log "=========================================="
3. File Restore from S3
bash#!/bin/bash
# scripts/restore_files_from_s3.sh

# ============================================
# FILE RESTORE FROM S3
# ============================================
#
# Restore files from S3 backup
#
# Usage:
#   ./restore_files_from_s3.sh /path/to/restore
#   ./restore_files_from_s3.sh /path/to/restore --date 2024-01-15
# ============================================

set -euo pipefail

# Configuration
S3_BUCKET="${S3_BUCKET:-my-app-backups}"
S3_PREFIX="${S3_PREFIX:-uploads}"
RESTORE_PATH="${1:-/var/app/uploads}"
LOG_FILE="/var/log/app/file_restore.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "=========================================="
log "FILE RESTORE FROM S3"
log "=========================================="
log "Bucket: s3://$S3_BUCKET/$S3_PREFIX"
log "Destination: $RESTORE_PATH"

# Safety backup of current files
if [ -d "$RESTORE_PATH" ]; then
    SAFETY_BACKUP="${RESTORE_PATH}_backup_$(date +%Y%m%d_%H%M%S)"
    log "Creating safety backup: $SAFETY_BACKUP"
    cp -r "$RESTORE_PATH" "$SAFETY_BACKUP"
fi

# Create restore directory
mkdir -p "$RESTORE_PATH"

# Restore from S3
log "Starting S3 sync..."

aws s3 sync \
    "s3://${S3_BUCKET}/${S3_PREFIX}" \
    "$RESTORE_PATH" \
    --delete \
    2>&1 | tee -a "$LOG_FILE"

if [ ${PIPESTATUS[0]} -eq 0 ]; then
    FILE_COUNT=$(find "$RESTORE_PATH" -type f | wc -l)
    TOTAL_SIZE=$(du -sh "$RESTORE_PATH" | cut -f1)
    
    log "✓ Restore completed"
    log "  Files: $FILE_COUNT"
    log "  Size: $TOTAL_SIZE"
    log "  Safety backup: $SAFETY_BACKUP"
else
    log "ERROR: Restore failed!"
    exit 1
fi

log "=========================================="
4. Restic File Restore
bash#!/bin/bash
# scripts/restore_files_restic.sh

# ============================================
# RESTIC FILE RESTORE
# ============================================
#
# Restore files using Restic
#
# Usage:
#   ./restore_files_restic.sh /path/to/restore
#   ./restore_files_restic.sh /path/to/restore --snapshot latest
#   ./restore_files_restic.sh /path/to/restore --snapshot abc123
#   ./restore_files_restic.sh /path/to/restore --date 2024-01-15
# ============================================

set -euo pipefail

# Configuration
RESTIC_REPOSITORY="${RESTIC_REPOSITORY:-s3:s3.amazonaws.com/my-app-backups/restic}"
RESTIC_PASSWORD_FILE="${RESTIC_PASSWORD_FILE:-/etc/restic/password}"
RESTORE_PATH="${1:-/var/app/uploads}"
LOG_FILE="/var/log/app/restic_restore.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# Export environment
export RESTIC_REPOSITORY
export RESTIC_PASSWORD_FILE

log "=========================================="
log "RESTIC FILE RESTORE"
log "=========================================="

# Determine snapshot
SNAPSHOT="latest"

case "${2:-}" in
    --snapshot)
        SNAPSHOT="${3:-latest}"
        ;;
    --date)
        DATE="${3:-}"
        if [ -z "$DATE" ]; then
            log "ERROR: Date required"
            exit 1
        fi
        # Find snapshot for date
        SNAPSHOT=$(restic snapshots --json | \
            jq -r ".[] | select(.time | startswith(\"$DATE\")) | .short_id" | \
            head -n1)
        if [ -z "$SNAPSHOT" ]; then
            log "ERROR: No snapshot found for date: $DATE"
            exit 1
        fi
        ;;
esac

log "Snapshot: $SNAPSHOT"
log "Destination: $RESTORE_PATH"

# List snapshot contents
log "Snapshot contents:"
restic ls "$SNAPSHOT" --long | head -n 20 | tee -a "$LOG_FILE"

# Confirmation
read -p "Restore this snapshot? (yes/no): " -r
if [[ ! $REPLY =~ ^yes$ ]]; then
    log "Restore cancelled"
    exit 0
fi

# Safety backup
if [ -d "$RESTORE_PATH" ]; then
    SAFETY_BACKUP="${RESTORE_PATH}_backup_$(date +%Y%m%d_%H%M%S)"
    log "Creating safety backup: $SAFETY_BACKUP"
    mv "$RESTORE_PATH" "$SAFETY_BACKUP"
fi

# Restore
log "Starting restore..."

restic restore "$SNAPSHOT" \
    --target "$RESTORE_PATH" \
    --verbose \
    2>&1 | tee -a "$LOG_FILE"

if [ ${PIPESTATUS[0]} -eq 0 ]; then
    FILE_COUNT=$(find "$RESTORE_PATH" -type f | wc -l)
    TOTAL_SIZE=$(du -sh "$RESTORE_PATH" | cut -f1)
    
    log "✓ Restore completed"
    log "  Files: $FILE_COUNT"
    log "  Size: $TOTAL_SIZE"
    log "  Safety backup: $SAFETY_BACKUP"
else
    log "ERROR: Restore failed!"
    
    # Restore safety backup
    if [ -d "$SAFETY_BACKUP" ]; then
        log "Restoring from safety backup..."
        rm -rf "$RESTORE_PATH"
        mv "$SAFETY_BACKUP" "$RESTORE_PATH"
    fi
    
    exit 1
fi

log "=========================================="
5. Emergency Recovery Checklist
markdown# 🚨 EMERGENCY RECOVERY CHECKLIST

## IMMEDIATE ACTIONS (First 5 Minutes)

- [ ] **STOP**: Don't panic, don't make hasty decisions
- [ ] **ASSESS**: What exactly happened? When? What's affected?
- [ ] **ISOLATE**: Prevent further damage
  - [ ] Stop application if data corruption
  - [ ] Disconnect from network if security breach
  - [ ] Disable write access if accidental deletion
- [ ] **NOTIFY**: Alert response team
  - [ ] DBA Lead
  - [ ] SysAdmin
  - [ ] Management (if critical)
- [ ] **LOG**: Start documenting everything
  - [ ] What happened
  - [ ] When it was detected
  - [ ] What actions you're taking
  - [ ] Timeline of events

## ASSESSMENT PHASE (5-15 Minutes)

- [ ] **Verify backup availability**
```bash
  ls -lh /var/backups/postgres/*.sql.gz
  aws s3 ls s3://my-app-backups/postgres/
```

- [ ] **Check backup integrity**
```bash
  gzip -t /var/backups/postgres/latest.sql.gz
```

- [ ] **Identify recovery point**
  - [ ] What time do you need to restore to?
  - [ ] Is that backup available?
  - [ ] How much data will be lost?

- [ ] **Estimate recovery time**
  - [ ] How long will restore take?
  - [ ] Do you have maintenance window?
  - [ ] Need to notify users?

## DECISION PHASE (15-30 Minutes)

- [ ] **Choose recovery method**
  - [ ] Full restore (complete disaster)
  - [ ] PITR (accidental deletion, need specific time)
  - [ ] Table restore (isolated table issue)
  - [ ] File restore (file corruption/deletion)

- [ ] **Get approval** (if required)
  - [ ] Management signoff for downtime
  - [ ] Stakeholder notification

- [ ] **Prepare recovery environment**
  - [ ] Test database available?
  - [ ] Sufficient disk space?
  - [ ] Network connectivity OK?

## EXECUTION PHASE

- [ ] **Create safety backup**
```bash
  # Always backup current state before restore!
  pg_dump myapp | gzip > safety_backup_$(date +%Y%m%d_%H%M%S).sql.gz
```

- [ ] **Put system in maintenance mode**
```bash
  systemctl stop myapp
  # Update load balancer, show maintenance page
```

- [ ] **Execute restore**
```bash
  # Choose appropriate script
  ./scripts/full_restore.sh --latest
  # OR
  ./scripts/pitr_recovery.sh "2024-01-15 14:30:00"
  # OR
  ./scripts/restore_table.sh backup.sql.gz users
```

- [ ] **Monitor progress**
  - [ ] Watch logs: `tail -f /var/log/postgres/restore.log`
  - [ ] Check disk space: `df -h`
  - [ ] Monitor system load: `top`

## VALIDATION PHASE

- [ ] **Verify database**
```bash
  psql -c "SELECT COUNT(*) FROM users;"
  psql -c "SELECT COUNT(*) FROM orders;"
  # Check critical tables
```

- [ ] **Test application**
  - [ ] Can connect to database?
  - [ ] Critical functions work?
  - [ ] Data looks correct?

- [ ] **Run integrity checks**
```bash
  # Check for corruption
  vacuumdb --analyze myapp
```

- [ ] **Compare with expectations**
  - [ ] Row counts correct?
  - [ ] Latest records present?
  - [ ] No duplicates?

## RECOVERY COMPLETION

- [ ] **Restart services**
```bash
  systemctl start myapp
  systemctl status myapp
```

- [ ] **Remove maintenance mode**
  - [ ] Update load balancer
  - [ ] Remove maintenance page

- [ ] **Monitor closely**
  - [ ] Watch error logs
  - [ ] Monitor performance
  - [ ] Check for issues

- [ ] **Notify stakeholders**
  - [ ] Service restored
  - [ ] What happened
  - [ ] What data (if any) was lost
  - [ ] Prevention measures

## POST-RECOVERY

- [ ] **Document incident**
  - [ ] What happened
  - [ ] How it was detected
  - [ ] Recovery steps taken
  - [ ] Time to recover
  - [ ] Data loss (if any)

- [ ] **Schedule post-mortem** (within 48 hours)
  - [ ] Root cause analysis
  - [ ] What went well
  - [ ] What could be improved
  - [ ] Action items

- [ ] **Update procedures** (if needed)
  - [ ] Did scripts work as expected?
  - [ ] Documentation accurate?
  - [ ] New scenarios to prepare for?

- [ ] **Test improvements**
  - [ ] Implement prevention measures
  - [ ] Update monitoring
  - [ ] Schedule DR drill

📊 MONITORING & ALERTING
1. Prometheus Metrics
python# backend/monitoring/backup_metrics.py

"""
Prometheus Metrics for Backup Monitoring
"""

from prometheus_client import Gauge, Counter, Histogram
import os
from pathlib import Path
from datetime import datetime


# ============================================
# METRICS DEFINITIONS
# ============================================

# Backup age in seconds
backup_age_seconds = Gauge(
    'backup_age_seconds',
    'Age of latest backup in seconds',
    ['backup_type']  # full, incremental, wal
)

# Backup size in bytes
backup_size_bytes = Gauge(
    'backup_size_bytes',
    'Size of latest backup in bytes',
    ['backup_type']
)

# Backup success/failure counter
backup_total = Counter(
    'backup_total',
    'Total number of backups',
    ['backup_type', 'status']  # success, failed
)

# Backup duration in seconds
backup_duration_seconds = Histogram(
    'backup_duration_seconds',
    'Backup duration in seconds',
    ['backup_type'],
    buckets=[60, 300, 600, 1800, 3600, 7200]  # 1m, 5m, 10m, 30m, 1h, 2h
)

# RPO compliance (time since last successful backup)
rpo_compliance_seconds = Gauge(
    'rpo_compliance_seconds',
    'Time since last successful backup (RPO indicator)'
)

# RTO estimate (based on backup size and restore speed)
rto_estimate_seconds = Gauge(
    'rto_estimate_seconds',
    'Estimated recovery time in seconds'
)

# Restore test results
restore_test_success = Gauge(
    'restore_test_success',
    'Result of last restore test (1=success, 0=failure)'
)

# WAL archive status
wal_archive_age_seconds = Gauge(
    'wal_archive_age_seconds',
    'Age of latest WAL archive in seconds'
)

# Storage usage
backup_storage_bytes = Gauge(
    'backup_storage_bytes',
    'Total backup storage usage in bytes',
    ['location']  # local, s3, glacier
)

backup_storage_available_bytes = Gauge(
    'backup_storage_available_bytes',
    'Available backup storage in bytes',
    ['location']
)


# ============================================
# METRIC COLLECTION
# ============================================

class BackupMetricsCollector:
    """Collect and update backup metrics"""
    
    def __init__(self, config):
        self.config = config
    
    def update_backup_metrics(self):
        """Update all backup-related metrics"""
        
        # Update backup age
        self._update_backup_age()
        
        # Update backup size
        self._update_backup_size()
        
        # Update storage metrics
        self._update_storage_metrics()
        
        # Update WAL metrics
        self._update_wal_metrics()
        
        # Update compliance metrics
        self._update_compliance_metrics()
    
    def _update_backup_age(self):
        """Update backup age metrics"""
        
        backup_dir = self.config['backup_dir']
        
        # Full backups
        full_backups = sorted(
            Path(backup_dir).glob("*.sql.gz"),
            key=os.path.getmtime,
            reverse=True
        )
        
        if full_backups:
            latest = full_backups[0]
            age = datetime.now().timestamp() - latest.stat().st_mtime
            backup_age_seconds.labels(backup_type='full').set(age)
    
    def _update_backup_size(self):
        """Update backup size metrics"""
        
        backup_dir = self.config['backup_dir']
        
        full_backups = sorted(
            Path(backup_dir).glob("*.sql.gz"),
            key=os.path.getmtime,
            reverse=True
        )
        
        if full_backups:
            latest = full_backups[0]
            size = latest.stat().st_size
            backup_size_bytes.labels(backup_type='full').set(size)
    
    def _update_storage_metrics(self):
        """Update storage usage metrics"""
        
        backup_dir = self.config['backup_dir']
        
        # Total size
        total_size = sum(
            f.stat().st_size
            for f in Path(backup_dir).rglob("*")
            if f.is_file()
        )
        backup_storage_bytes.labels(location='local').set(total_size)
        
        # Available space
        stat = os.statvfs(backup_dir)
        available = stat.f_bavail * stat.f_frsize
        backup_storage_available_bytes.labels(location='local').set(available)
    
    def _update_wal_metrics(self):
        """Update WAL archive metrics"""
        
        wal_dir = self.config.get('wal_archive_dir')
        if not wal_dir or not os.path.exists(wal_dir):
            return
        
        wal_files = sorted(
            Path(wal_dir).glob("*.gz"),
            key=os.path.getmtime,
            reverse=True
        )
        
        if wal_files:
            latest = wal_files[0]
            age = datetime.now().timestamp() - latest.stat().st_mtime
            wal_archive_age_seconds.set(age)
    
    def _update_compliance_metrics(self):
        """Update RTO/RPO compliance metrics"""
        
        # RPO: Time since last backup
        backup_dir = self.config['backup_dir']
        backups = sorted(
            Path(backup_dir).glob("*.sql.gz"),
            key=os.path.getmtime,
            reverse=True
        )
        
        if backups:
            age = datetime.now().timestamp() - backups[0].stat().st_mtime
            rpo_compliance_seconds.set(age)
        
        # RTO: Estimate based on backup size
        if backups:
            size_mb = backups[0].stat().st_size / (1024 * 1024)
            restore_speed_mbps = self.config.get('restore_speed_mbps', 100)
            
            # Estimate: restore time + overhead
            restore_time = (size_mb / restore_speed_mbps) * 60  # seconds
            overhead = restore_time * 0.3
            rto_estimate = restore_time + overhead
            
            rto_estimate_seconds.set(rto_estimate)
    
    def record_backup_completion(
        self,
        backup_type: str,
        duration: float,
        success: bool
    ):
        """Record backup completion"""
        
        status = 'success' if success else 'failed'
        
        backup_total.labels(
            backup_type=backup_type,
            status=status
        ).inc()
        
        if success:
            backup_duration_seconds.labels(
                backup_type=backup_type
            ).observe(duration)
    
    def record_restore_test(self, success: bool):
        """Record restore test result"""
        restore_test_success.set(1 if success else 0)


# ============================================
# PROMETHEUS EXPORTER
# ============================================

from prometheus_client import start_http_server
import time


def start_metrics_server(port=9090):
    """Start Prometheus metrics server"""
    
    start_http_server(port)
    print(f"Metrics server started on port {port}")
    print(f"Metrics available at http://localhost:{port}/metrics")
    
    # Keep running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Metrics server stopped")


if __name__ == "__main__":
    # Example usage
    config = {
        'backup_dir': '/var/backups/postgres',
        'wal_archive_dir': '/var/lib/postgresql/wal_archive',
        'restore_speed_mbps': 100
    }
    
    collector = BackupMetricsCollector(config)
    
    # Start metrics server
    start_metrics_server(9090)
    
    # Update metrics periodically
    import schedule
    
    schedule.every(1).minutes.do(collector.update_backup_metrics)
    
    while True:
        schedule.run_pending()
        time.sleep(1)
2. Prometheus Alert Rules
yaml# prometheus/alerts/backup_alerts.yml

groups:
  - name: backup_alerts
    interval: 1m
    
    rules:
      # ============================================
      # CRITICAL ALERTS
      # ============================================
      
      - alert: BackupMissing
        expr: time() - backup_age_seconds{backup_type="full"} > 86400 * 2
        for: 5m
        labels:
          severity: critical
          team: infrastructure
        annotations:
          summary: "No backup in 48 hours"
          description: "Last backup was {{ $value | humanizeDuration }} ago. RPO severely violated!"
          runbook: "https://docs.company.com/runbooks/backup-missing"
      
      - alert: BackupFailed
        expr: rate(backup_total{status="failed"}[1h]) > 0
        for: 5m
        labels:
          severity: critical
          team: infrastructure
        annotations:
          summary: "Backup failures detected"
          description: "{{ $value }} backup failures in the last hour"
          runbook: "https://docs.company.com/runbooks/backup-failed"
      
      - alert: WALArchiveStalled
        expr: wal_archive_age_seconds > 1800
        for: 10m
        labels:
          severity: critical
          team: infrastructure
        annotations:
          summary: "WAL archiving stalled"
          description: "No WAL archived in {{ $value | humanizeDuration }}. RPO at risk!"
          runbook: "https://docs.company.com/runbooks/wal-stalled"
      
      - alert: BackupStorageFull
        expr: |
          (backup_storage_available_bytes{location="local"} / 
           backup_storage_bytes{location="local"}) < 0.1
        for: 15m
        labels:
          severity: critical
          team: infrastructure
        annotations:
          summary: "Backup storage critically low"
          description: "Less than 10% storage available for backups"
          runbook: "https://docs.company.com/runbooks/backup-storage-full"
      
      # ============================================
      # WARNING ALERTS
      # ============================================
      
      - alert: RPOViolation
        expr: rpo_compliance_seconds > 3600
        for: 15m
        labels:
          severity: warning
          team: infrastructure
        annotations:
          summary: "RPO objective violated"
          description: "Last backup {{ $value | humanizeDuration }} ago, exceeds RPO target"
          runbook: "https://docs.company.com/runbooks/rpo-violation"
      
      - alert: RTOEstimateHigh
        expr: rto_estimate_seconds > 14400
        for: 1h
        labels:
          severity: warning
          team: infrastructure
        annotations:
          summary: "Estimated RTO exceeds target"
          description: "Current backup size would take {{ $value | humanizeDuration }} to restore"
          runbook: "https://docs.company.com/runbooks/rto-high"
      
      - alert: BackupSizeIncreased
        expr: |
          (backup_size_bytes{backup_type="full"} - 
           backup_size_bytes{backup_type="full"} offset 24h) / 
           backup_size_bytes{backup_type="full"} offset 24h > 0.5
        for: 1h
        labels:
          severity: warning
          team: infrastructure
        annotations:
          summary: "Backup size increased significantly"
          description: "Backup size increased by {{ $value | humanizePercentage }} in 24h"
          runbook: "https://docs.company.com/runbooks/backup-size-increase"
      
      - alert: RestoreTestFailed
        expr: restore_test_success == 0
        for: 5m
        labels:
          severity: warning
          team: infrastructure
        annotations:
          summary: "Restore test failed"
          description: "Last restore test did not complete successfully"
          runbook: "https://docs.company.com/runbooks/restore-test-failed"
      
      - alert: BackupStorageLow
        expr: |
          (backup_storage_available_bytes{location="local"} / 
           backup_storage_bytes{location="local"}) < 0.2
        for: 30m
        labels:
          severity: warning
          team: infrastructure
        annotations:
          summary: "Backup storage running low"
          description: "Less than 20% storage available for backups"
          runbook: "https://docs.company.com/runbooks/backup-storage-low"
3. Grafana Dashboard
json{
  "dashboard": {
    "title": "Backup & DR Monitoring",
    "tags": ["backup", "disaster-recovery"],
    "timezone": "browser",
    "panels": [
      {
        "title": "Backup Age",
        "type": "graph",
        "targets": [
          {
            "expr": "backup_age_seconds{backup_type=\"full\"} / 3600",
            "legendFormat": "Full Backup Age (hours)"
          },
          {
            "expr": "wal_archive_age_seconds / 60",
            "legendFormat": "WAL Archive Age (minutes)"
          }
        ],
        "yaxes": [
          {
            "label": "Age",
            "format": "short"
          }
        ],
        "alert": {
          "conditions": [
            {
              "evaluator": {
                "params": [24],
                "type": "gt"
              },
              "query": {
                "params": ["A", "5m", "now"]
              },
              "reducer": {
                "params": [],
                "type": "last"
              },
              "type": "query"
            }
          ],
          "name": "Backup Age Alert"
        }
      },
      {
        "title": "Backup Size Trend",
        "type": "graph",
        "targets": [
          {
            "expr": "backup_size_bytes{backup_type=\"full\"} / 1024 / 1024 / 1024",
            "legendFormat": "Backup Size (GB)"
          }
        ]
      },
      {
        "title": "Backup Success Rate",
        "type": "gauge",
        "targets": [
          {
            "expr": "rate(backup_total{status=\"success\"}[24h]) / rate(backup_total[24h]) * 100",
            "legendFormat": "Success Rate (%)"
          }
        ],
        "thresholds": [
          {
            "value": 95,
            "color": "red"
          },
          {
            "value": 98,
            "color": "yellow"
          },
          {
            "value": 100,
            "color": "green"
          }
        ]
      },
      {
        "title": "RTO/RPO Compliance",
        "type": "stat",
        "targets": [
          {
            "expr": "rpo_compliance_seconds / 60",
            "legendFormat": "RPO (minutes)"
          },
          {
            "expr": "rto_estimate_seconds / 3600",
            "legendFormat": "RTO Estimate (hours)"
          }
        ]
      },
      {
        "title": "Storage Usage",
        "type": "graph",
        "targets": [
          {
            "expr": "backup_storage_bytes{location=\"local\"} / 1024 / 1024 / 1024",
            "legendFormat": "Used (GB)"
          },
          {
            "expr": "backup_storage_available_bytes{location=\"local\"} / 1024 / 1024 / 1024",
            "legendFormat": "Available (GB)"
          }
        ]
      },
      {
        "title": "Recent Backup Events",
        "type": "table",
        "targets": [
          {
            "expr": "backup_total",
            "format": "table"
          }
        ]
      }
    ]
  }
}
```

---

## ✅ BEST PRACTICES SUMMARY

### 1. The 3-2-1 Rule
```
┌─────────────────────────────────────────────────────────┐
│                  3-2-1 BACKUP RULE                       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  3  Keep THREE copies of your data                      │
│     - Production data                                   │
│     - Local backup                                      │
│     - Remote backup                                     │
│                                                         │
│  2  Store backups on TWO different media types          │
│     - Disk (fast restore)                               │
│     - Cloud/Tape (disaster recovery)                    │
│                                                         │
│  1  Keep ONE copy offsite                               │
│     - Different geographic location                     │
│     - Protection against site disasters                 │
│                                                         │
└─────────────────────────────────────────────────────────┘
2. Critical Best Practices
python# config/best_practices.py

BACKUP_BEST_PRACTICES = {
    "automation": {
        "DO": [
            "Automate all backups with cron/systemd",
            "Use configuration management (Ansible, etc.)",
            "Implement automated monitoring",
            "Set up automatic alerting",
            "Script common recovery procedures"
        ],
        "DON'T": [
            "Rely on manual backups",
            "Assume backups work without testing",
            "Ignore backup failures",
            "Skip automation 'because it's complex'"
        ]
    },
    
    "testing": {
        "DO": [
            "Test restores regularly (monthly minimum)",
            "Validate backup integrity automatically",
            "Practice disaster recovery procedures",
            "Document all test results",
            "Time your restore procedures",
            "Test PITR capabilities"
        ],
        "DON'T": [
            "Assume backups work without testing",
            "Test only once per year",
            "Skip validation steps",
            "Test in production environment"
        ]
    },
    
    "security": {
        "DO": [
            "Encrypt backups at rest and in transit",
            "Use strong encryption (AES-256)",
            "Store encryption keys securely",
            "Implement access controls",
            "Audit backup access",
            "Sanitize sensitive data in dev/test restores"
        ],
        "DON'T": [
            "Store unencrypted backups",
            "Use weak encryption",
            "Store keys with backups",
            "Give everyone backup access",
            "Ignore compliance requirements"
        ]
    },
    
    "retention": {
        "DO": [
            "Define clear retention policies",
            "Keep multiple generations",
            "Archive compliance-required backups",
            "Clean up old backups automatically",
            "Document retention decisions"
        ],
        "DON'T": [
            "Keep backups forever (costs)",
            "Delete backups too quickly",
            "Ignore compliance requirements",
            "Manually manage retention"
        ]
    },
    
    "monitoring": {
        "DO": [
            "Monitor backup completion",
            "Track backup size trends",
            "Alert on failures immediately",
            "Monitor storage capacity",
            "Track RTO/RPO compliance",
            "Log all backup activities"
        ],
        "DON'T": [
            "Assume backups work",
            "Check backups manually",
            "Ignore size increases",
            "Wait for disasters to find issues"
        ]
    },
    
    "documentation": {
        "DO": [
            "Document all procedures",
            "Keep runbooks up to date",
            "Document configuration",
            "Maintain disaster recovery plan",
            "Record test results",
            "Update docs after incidents"
        ],
        "DON'T": [
            "Rely on tribal knowledge",
            "Create docs and forget them",
            "Skip documentation 'for later'",
            "Document only what you remember"
        ]
    }
}

📝 CHECKLISTS & QUICK REFERENCE
Daily Checklist
markdown## Daily Backup Checklist

- [ ] Verify last night's backup completed
```bash
  ls -lh /var/backups/postgres/*.sql.gz | tail -n 1
```

- [ ] Check backup age (should be < 24 hours)
```bash
  find /var/backups/postgres -name "*.sql.gz" -mtime -1 | wc -l
```

- [ ] Verify WAL archiving is working
```bash
  ls -lh /var/lib/postgresql/wal_archive/*.gz | tail -n 5
```

- [ ] Check backup logs for errors
```bash
  tail -n 50 /var/log/postgres/backup.log | grep -i error
```

- [ ] Monitor storage space
```bash
  df -h /var/backups
```

- [ ] Review alerts (if any)
```bash
  # Check Prometheus/Grafana
```
Weekly Checklist
markdown## Weekly Backup Checklist

- [ ] Review all backup failures from past week
- [ ] Test restore of single table to staging
```bash
  ./scripts/restore_table.sh latest users
```
- [ ] Verify S3/remote backups exist
```bash
  aws s3 ls s3://my-app-backups/postgres/ | tail -n 10
```
- [ ] Check backup size trends
- [ ] Review and cleanup old backups
- [ ] Update team on backup status
Monthly Checklist
markdown## Monthly Backup Checklist

- [ ] Perform full restore test to staging
```bash
  ./scripts/full_restore.sh --latest
```
- [ ] Test PITR procedure
```bash
  ./scripts/pitr_recovery.sh "$(date --date='1 hour ago' '+%Y-%m-%d %H:%M:%S')"
```
- [ ] Review and update DR documentation
- [ ] Check compliance with retention policies
- [ ] Verify encryption is working
- [ ] Test file restore procedures
- [ ] Review RTO/RPO metrics
- [ ] Schedule DR drill if needed
Quarterly Checklist
markdown## Quarterly Backup Checklist

- [ ] Full disaster recovery drill
- [ ] Review and update DR plan
- [ ] Test recovery on different hardware
- [ ] Audit backup access logs
- [ ] Review backup costs and optimization
- [ ] Update team training materials
- [ ] Test backup procedures with new team members
- [ ] Review and update alert thresholds
- [ ] Compliance audit (if required)
```

---

## 🎯 FINAL SUMMARY
```
┌──────────────────────────────────────────────────────────────┐
│              BACKUP & DR - COMPLETE COVERAGE                  │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ✅ Database Backup Strategies                               │
│     - pg_dump, pg_basebackup, WAL archiving                  │
│     - Strategy matrix by database size                       │
│                                                              │
│  ✅ Automated Backups                                        │
│     - Shell scripts with error handling                      │
│     - Systemd timers                                         │
│     - S3 upload, compression, encryption                     │
│                                                              │
│  ✅ Point-in-Time Recovery                                   │
│     - Complete PITR procedures                               │
│     - Testing scripts                                        │
│     - Validation procedures                                  │
│                                                              │
│  ✅ File Storage Backups                                     │
│     - rsync, S3 sync, Restic                                 │
│     - Incremental and full backups                           │
│                                                              │
│  ✅ Backup Testing & Validation                              │
│     - Automated validation scripts                           │
│     - Daily/weekly/monthly checks                            │
│     - Integrity verification                                 │
│                                                              │
│  ✅ Disaster Recovery Plan                                   │
│     - Complete DR framework                                  │
│     - Scenario-based procedures                              │
│     - Emergency runbooks                                     │
│     - Incident reporting                                     │
│                                                              │
│  ✅ RTO/RPO Definitions                                      │
│     - Tier-based matrix                                      │
│     - Cost calculations                                      │
│     - Compliance monitoring                                  │
│                                                              │
│  ✅ Restoration Procedures                                   │
│     - Full database restore                                  │
│     - Table-level restore                                    │
│     - File restore (S3, Restic)                              │
│     - Emergency checklists                                   │
│                                                              │
│  ✅ Monitoring & Alerting                                    │
│     - Prometheus metrics                                     │
│     - Alert rules                                            │
│     - Grafana dashboards                                     │
│                                                              │
│  ✅ Best Practices                                           │
│     - 3-2-1 rule                                             │
│     - DO's and DON'Ts                                        │
│     - Daily/weekly/monthly checklists                        │
│                                                              │
└──────────────────────────────────────────────────────────────┘