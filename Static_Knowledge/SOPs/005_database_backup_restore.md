# SOP-005: Database Backup and Restore

**Status**: Active
**Last Updated**: 2025-11-22
**Owner**: Operations Team
**Priority**: Critical
**Review Frequency**: Quarterly

## Purpose

Standard Operating Procedure for PostgreSQL database backup and restore operations, including point-in-time recovery (PITR) and GDPR-compliant backup retention.

## Scope

- PostgreSQL 16 production database
- Automated daily backups
- Manual backup procedures
- Disaster recovery scenarios
- GDPR compliance (7-year retention for audit logs)

## Prerequisites

- PostgreSQL superuser access
- Sufficient disk space (minimum 3x database size)
- pg_dump/pg_restore installed
- Access to backup storage (NAS/MinIO)

---

## Backup Procedures

### 1. Automated Daily Backups

**Schedule**: 02:00 AM daily (low-traffic period)

**Script Location**: `/opt/ablage/scripts/backup_database.sh`

```bash
#!/bin/bash
# Daily PostgreSQL backup script

set -e

# Configuration
DB_NAME="ablage"
DB_USER="postgres"
BACKUP_DIR="/mnt/nas/ablage-backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=30

# Create backup directory if not exists
mkdir -p "$BACKUP_DIR"

# Full database backup
echo "Starting backup: $TIMESTAMP"
pg_dump \
  -U "$DB_USER" \
  -Fc \
  -f "$BACKUP_DIR/ablage_backup_$TIMESTAMP.dump" \
  "$DB_NAME"

# Verify backup
if [ $? -eq 0 ]; then
    echo "✓ Backup successful: ablage_backup_$TIMESTAMP.dump"

    # Compress backup
    gzip "$BACKUP_DIR/ablage_backup_$TIMESTAMP.dump"

    # Calculate checksum
    sha256sum "$BACKUP_DIR/ablage_backup_$TIMESTAMP.dump.gz" > \
      "$BACKUP_DIR/ablage_backup_$TIMESTAMP.dump.gz.sha256"

    # Upload to remote storage
    mc cp "$BACKUP_DIR/ablage_backup_$TIMESTAMP.dump.gz" \
      "s3/ablage-backups/"
else
    echo "✗ Backup failed!"
    # Send alert
    curl -X POST "http://alertmanager:9093/api/v1/alerts" \
      -d '[{"labels":{"alertname":"BackupFailed","severity":"critical"}}]'
    exit 1
fi

# Cleanup old backups (keep last 30 days)
find "$BACKUP_DIR" -name "ablage_backup_*.dump.gz" -mtime +$RETENTION_DAYS -delete

echo "Backup completed successfully"
```

**Cron Setup**:
```bash
# Edit crontab
crontab -e

# Add backup job
0 2 * * * /opt/ablage/scripts/backup_database.sh >> /var/log/ablage/backup.log 2>&1
```

### 2. Manual Backup Before Maintenance

**When**: Before any database migration, major schema change, or system upgrade

```bash
# Full backup with timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
pg_dump -U postgres -Fc -f "ablage_manual_backup_$TIMESTAMP.dump" ablage

# Verify backup integrity
pg_restore --list "ablage_manual_backup_$TIMESTAMP.dump" | head -n 20
```

### 3. Schema-Only Backup

**Use Case**: Quick schema snapshots for development/testing

```bash
pg_dump -U postgres --schema-only -f ablage_schema.sql ablage
```

### 4. Specific Table Backup

**Use Case**: Backup critical tables (e.g., audit logs)

```bash
# Backup audit_logs table
pg_dump -U postgres -t audit_logs -Fc -f audit_logs_backup.dump ablage
```

---

## Restore Procedures

### 1. Full Database Restore

**⚠️ WARNING**: This will **DROP** the existing database!

```bash
# Step 1: Stop all services
docker-compose down

# Step 2: Drop existing database (if exists)
psql -U postgres -c "DROP DATABASE IF EXISTS ablage;"

# Step 3: Create fresh database
psql -U postgres -c "CREATE DATABASE ablage;"

# Step 4: Restore from backup
pg_restore \
  -U postgres \
  -d ablage \
  -v \
  "ablage_backup_20251122_020000.dump"

# Step 5: Restart services
docker-compose up -d

# Step 6: Verify restoration
psql -U postgres -d ablage -c "\
SELECT COUNT(*) FROM documents; \
SELECT COUNT(*) FROM users; \
SELECT COUNT(*) FROM ocr_results;"
```

### 2. Point-in-Time Recovery (PITR)

**Use Case**: Restore to specific point in time (e.g., before data corruption)

**Prerequisites**: WAL archiving must be enabled

**Configuration** (`postgresql.conf`):
```
wal_level = replica
archive_mode = on
archive_command = 'cp %p /mnt/nas/ablage-wal/%f'
```

**Restore to Specific Time**:
```bash
# Stop PostgreSQL
systemctl stop postgresql

# Remove current data directory
rm -rf /var/lib/postgresql/16/main/*

# Restore base backup
pg_basebackup -U postgres -D /var/lib/postgresql/16/main -Fp -Xs -P

# Create recovery.conf
cat > /var/lib/postgresql/16/main/recovery.conf <<EOF
restore_command = 'cp /mnt/nas/ablage-wal/%f %p'
recovery_target_time = '2025-11-22 14:30:00+01'
recovery_target_action = 'promote'
EOF

# Start PostgreSQL
systemctl start postgresql

# Monitor recovery
tail -f /var/log/postgresql/postgresql-16-main.log
```

### 3. Table-Level Restore

**Use Case**: Restore single table without full database restore

```bash
# Extract specific table from backup
pg_restore \
  -U postgres \
  -d ablage \
  -t documents \
  --clean \
  --if-exists \
  ablage_backup_20251122_020000.dump
```

---

## Disaster Recovery Scenarios

### Scenario 1: Database Corruption

**Symptoms**:
- Query errors: "invalid page header"
- PostgreSQL crashes on startup
- Data inconsistencies

**Recovery Steps**:

1. **Assess Damage**:
   ```bash
   # Check for corruption
   psql -U postgres -d ablage -c "SELECT pg_database_size('ablage');"

   # Vacuum to detect issues
   vacuumdb -U postgres -d ablage --analyze --verbose
   ```

2. **Attempt Repair**:
   ```bash
   # Reindex all tables
   reindexdb -U postgres -d ablage

   # Vacuum full (offline operation)
   vacuumdb -U postgres -d ablage --full
   ```

3. **If Repair Fails, Restore from Backup**:
   ```bash
   # Follow "Full Database Restore" procedure above
   ```

### Scenario 2: Accidental Data Deletion

**Symptoms**:
- User reports missing documents
- Audit log shows DELETE operations

**Recovery Steps**:

1. **Identify Deletion Time**:
   ```sql
   SELECT * FROM audit_logs
   WHERE action = 'DELETE'
   AND entity_type = 'document'
   ORDER BY timestamp DESC
   LIMIT 10;
   ```

2. **PITR to Before Deletion**:
   - Use PITR procedure to restore to time before deletion
   - Alternatively, extract deleted data from backup

3. **Selective Data Restore**:
   ```bash
   # Restore to temporary database
   createdb ablage_temp
   pg_restore -d ablage_temp ablage_backup_20251122_020000.dump

   # Copy deleted records
   psql -U postgres -d ablage <<EOF
   INSERT INTO documents
   SELECT * FROM ablage_temp.documents
   WHERE id IN ('doc_123', 'doc_456');
   EOF

   # Drop temporary database
   dropdb ablage_temp
   ```

### Scenario 3: Hardware Failure

**Symptoms**:
- Database server hardware fails
- Disk failure, server won't boot

**Recovery Steps**:

1. **Provision New Server**

2. **Install PostgreSQL 16**:
   ```bash
   apt-get update
   apt-get install postgresql-16
   ```

3. **Restore from Latest Backup**:
   - Follow "Full Database Restore" procedure
   - Use most recent backup from remote storage

4. **Update Application Configuration**:
   - Update `DATABASE_URL` in `.env`
   - Restart application services

---

## Backup Verification

### Monthly Restore Test

**Schedule**: First Sunday of each month

**Procedure**:
```bash
# 1. Create test database
createdb ablage_restore_test

# 2. Restore latest backup
pg_restore \
  -U postgres \
  -d ablage_restore_test \
  ablage_backup_latest.dump

# 3. Run verification queries
psql -U postgres -d ablage_restore_test -f /opt/ablage/scripts/verify_restore.sql

# 4. Compare with production
diff <(psql -U postgres -d ablage -c "\dt") \
     <(psql -U postgres -d ablage_restore_test -c "\dt")

# 5. Cleanup
dropdb ablage_restore_test
```

**Verification Script** (`verify_restore.sql`):
```sql
-- Check table counts
SELECT 'documents' AS table_name, COUNT(*) FROM documents
UNION ALL
SELECT 'users', COUNT(*) FROM users
UNION ALL
SELECT 'ocr_results', COUNT(*) FROM ocr_results;

-- Check recent data
SELECT MAX(created_at) AS last_document FROM documents;
SELECT MAX(created_at) AS last_user FROM users;

-- Check constraints
SELECT COUNT(*) FROM information_schema.table_constraints
WHERE constraint_type = 'FOREIGN KEY';
```

---

## GDPR Compliance

### Backup Retention Policy

**Standard Data**: 30 days retention
**Audit Logs**: 7 years retention (German legal requirement)

**Implementation**:
```bash
# Separate backup for audit logs
pg_dump -U postgres -t audit_logs -Fc \
  -f "audit_logs_$(date +%Y%m%d).dump" ablage

# Archive to long-term storage
mc cp "audit_logs_$(date +%Y%m%d).dump" \
  s3/ablage-audit-archives/$(date +%Y)/
```

### Data Deletion Compliance

**When user requests data deletion (GDPR Art. 17)**:

1. **Delete from Production**:
   ```sql
   DELETE FROM documents WHERE user_id = 'user_123';
   DELETE FROM users WHERE id = 'user_123';
   ```

2. **Remove from Recent Backups**:
   ```bash
   # Restore backup, remove user data, re-backup
   pg_restore -d ablage_temp backup.dump
   psql -d ablage_temp -c "DELETE FROM documents WHERE user_id = 'user_123';"
   pg_dump -d ablage_temp -Fc -f backup_sanitized.dump
   ```

3. **Update Audit Log**:
   ```sql
   INSERT INTO audit_logs (action, entity_type, entity_id, gdpr_article, timestamp)
   VALUES ('DELETE', 'user', 'user_123', 'Art. 17', NOW());
   ```

---

## Monitoring and Alerts

### Backup Success Monitoring

**Prometheus Metrics**:
```yaml
- alert: BackupFailed
  expr: time() - ablage_last_backup_timestamp_seconds > 90000  # 25 hours
  labels:
    severity: critical
  annotations:
    summary: "Database backup failed or stale"
    description: "Last successful backup: {{ $value | humanizeDuration }} ago"
```

### Backup Size Monitoring

```bash
# Track backup size growth
du -sh /mnt/nas/ablage-backups/*.dump.gz | tail -n 7
```

**Alert if backup size increases > 50% unexpectedly**

---

## Troubleshooting

### Backup Fails with "Permission Denied"

**Solution**:
```bash
# Fix permissions
chown -R postgres:postgres /mnt/nas/ablage-backups/
chmod 700 /mnt/nas/ablage-backups/
```

### Restore Fails with "Role does not exist"

**Solution**:
```bash
# Create missing roles before restore
createuser -U postgres ablage_app
createuser -U postgres ablage_readonly
```

### PITR Fails - WAL Files Missing

**Solution**:
```bash
# Check WAL archive
ls -lh /mnt/nas/ablage-wal/

# If WAL files missing, cannot PITR
# Must use base backup (may lose recent changes)
```

---

## Checklist

### Daily (Automated)
- [ ] Backup script runs successfully
- [ ] Backup uploaded to remote storage
- [ ] No backup failure alerts

### Weekly
- [ ] Review backup logs for errors
- [ ] Check backup storage capacity
- [ ] Verify backup file integrity (checksum)

### Monthly
- [ ] Perform restore test
- [ ] Update backup documentation
- [ ] Review and cleanup old backups

### Quarterly
- [ ] Full disaster recovery drill
- [ ] Review and update SOP
- [ ] Audit GDPR compliance

---

## Related Documents

- [SOP-002: Rollback Procedure](002_rollback_procedure.md)
- [Playbook: Database Performance](../../Relations/Playbooks/database_performance_playbook.yaml)
- [Skills: Database Optimization](../Skills/database_optimization_skill.yaml)

---

**Revision History**:
- 2025-11-22: Initial version
- Next Review: 2026-02-22
