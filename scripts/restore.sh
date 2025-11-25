#!/bin/bash
# Restore Script for Ablage-System
# Restores database and MinIO data from backups

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DOCKER_COMPOSE="docker-compose -f docker-compose.yml -f docker-compose.dev.yml"
TEMP_DIR=$(mktemp -d)

# Cleanup on exit
cleanup() {
    rm -rf "$TEMP_DIR"
}
trap cleanup EXIT

# Function to restore database
restore_database() {
    local DB_BACKUP=$1

    echo -e "${BLUE}📥 Restoring PostgreSQL database...${NC}"

    # Check if file exists
    if [ ! -f "$DB_BACKUP" ]; then
        echo -e "${RED}❌ Database backup file not found: $DB_BACKUP${NC}"
        return 1
    fi

    # Check if postgres container is running
    if ! $DOCKER_COMPOSE ps postgres | grep -q "Up"; then
        echo -e "${YELLOW}⚠  PostgreSQL container not running, starting...${NC}"
        $DOCKER_COMPOSE up -d postgres
        sleep 5
    fi

    # Decompress if needed
    if [[ "$DB_BACKUP" == *.gz ]]; then
        echo -e "${YELLOW}Decompressing backup...${NC}"
        gunzip -c "$DB_BACKUP" > "$TEMP_DIR/db_backup.sql"
        DB_BACKUP="$TEMP_DIR/db_backup.sql"
    fi

    # Warning before restore
    echo -e "${RED}⚠️  WARNING: This will REPLACE the current database!${NC}"
    read -p "Are you sure? Type 'yes' to continue: " confirm

    if [ "$confirm" != "yes" ]; then
        echo -e "${YELLOW}Restore cancelled${NC}"
        return 1
    fi

    # Drop existing connections
    echo -e "${YELLOW}Closing existing database connections...${NC}"
    $DOCKER_COMPOSE exec -T postgres psql -U postgres -d postgres -c \
        "SELECT pg_terminate_backend(pg_stat_activity.pid) FROM pg_stat_activity WHERE pg_stat_activity.datname = 'ablage_ocr' AND pid <> pg_backend_pid();" \
        > /dev/null 2>&1 || true

    # Drop and recreate database
    echo -e "${YELLOW}Recreating database...${NC}"
    $DOCKER_COMPOSE exec -T postgres psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS ablage_ocr;" > /dev/null
    $DOCKER_COMPOSE exec -T postgres psql -U postgres -d postgres -c "CREATE DATABASE ablage_ocr;" > /dev/null

    # Restore database
    echo -e "${BLUE}Restoring data...${NC}"
    cat "$DB_BACKUP" | $DOCKER_COMPOSE exec -T postgres psql -U postgres -d ablage_ocr > /dev/null

    echo -e "${GREEN}✅ Database restored successfully${NC}"
}

# Function to restore MinIO data
restore_minio() {
    local MINIO_BACKUP=$1

    echo -e "${BLUE}📥 Restoring MinIO data...${NC}"

    # Check if file exists
    if [ ! -f "$MINIO_BACKUP" ]; then
        echo -e "${RED}❌ MinIO backup file not found: $MINIO_BACKUP${NC}"
        return 1
    fi

    # Check if minio container is running
    if ! $DOCKER_COMPOSE ps minio | grep -q "Up"; then
        echo -e "${YELLOW}⚠  MinIO container not running, starting...${NC}"
        $DOCKER_COMPOSE up -d minio
        sleep 5
    fi

    # Warning before restore
    echo -e "${RED}⚠️  WARNING: This will REPLACE current MinIO data!${NC}"
    read -p "Are you sure? Type 'yes' to continue: " confirm

    if [ "$confirm" != "yes" ]; then
        echo -e "${YELLOW}Restore cancelled${NC}"
        return 1
    fi

    # Extract backup
    echo -e "${YELLOW}Extracting backup...${NC}"
    tar -xzf "$MINIO_BACKUP" -C "$TEMP_DIR"

    # List of buckets to restore
    BUCKETS=("documents" "thumbnails" "exports")

    for bucket in "${BUCKETS[@]}"; do
        if [ -d "$TEMP_DIR/$bucket" ]; then
            echo -e "${BLUE}  → Restoring bucket: $bucket${NC}"

            # Remove existing bucket (if exists)
            $DOCKER_COMPOSE exec -T minio mc rb --force local/$bucket > /dev/null 2>&1 || true

            # Create bucket
            $DOCKER_COMPOSE exec -T minio mc mb local/$bucket > /dev/null 2>&1

            # Mirror data from temp directory to bucket
            $DOCKER_COMPOSE exec -T minio mc mirror --quiet --overwrite "$TEMP_DIR/$bucket" local/$bucket || true
        else
            echo -e "${YELLOW}  → Bucket $bucket not found in backup, skipping${NC}"
        fi
    done

    echo -e "${GREEN}✅ MinIO data restored successfully${NC}"
}

# Function to restore from combined backup
restore_all() {
    local BACKUP_FILE=$1

    echo -e "${BLUE}📥 Restoring from combined backup...${NC}"
    echo ""

    # Check if file exists
    if [ ! -f "$BACKUP_FILE" ]; then
        echo -e "${RED}❌ Backup file not found: $BACKUP_FILE${NC}"
        exit 1
    fi

    # Extract combined backup
    echo -e "${YELLOW}Extracting combined backup...${NC}"
    tar -xzf "$BACKUP_FILE" -C "$TEMP_DIR"

    # Find database backup
    DB_BACKUP=$(find "$TEMP_DIR" -name "db_backup_*.sql.gz" -o -name "db_backup_*.sql" | head -n 1)

    if [ -n "$DB_BACKUP" ]; then
        echo -e "${BLUE}Found database backup: $(basename $DB_BACKUP)${NC}"
        restore_database "$DB_BACKUP"
        echo ""
    else
        echo -e "${YELLOW}⚠  No database backup found in archive${NC}"
    fi

    # Find MinIO backup
    MINIO_BACKUP=$(find "$TEMP_DIR" -name "minio_backup_*.tar.gz" | head -n 1)

    if [ -n "$MINIO_BACKUP" ]; then
        echo -e "${BLUE}Found MinIO backup: $(basename $MINIO_BACKUP)${NC}"
        restore_minio "$MINIO_BACKUP"
        echo ""
    else
        echo -e "${YELLOW}⚠  No MinIO backup found in archive${NC}"
    fi

    # Show metadata if available
    METADATA=$(find "$TEMP_DIR" -name "backup_metadata_*.txt" | head -n 1)
    if [ -n "$METADATA" ]; then
        echo -e "${BLUE}📋 Backup Information:${NC}"
        cat "$METADATA" | sed 's/^/  /'
        echo ""
    fi

    echo -e "${GREEN}✅ Restore complete${NC}"
}

# Function to list available backups
list_backups() {
    BACKUP_DIR="backups"

    echo -e "${BLUE}📋 Available Backups:${NC}"
    echo ""

    if [ ! -d "$BACKUP_DIR" ] || [ -z "$(ls -A $BACKUP_DIR 2>/dev/null)" ]; then
        echo -e "${YELLOW}No backups found in $BACKUP_DIR${NC}"
        exit 0
    fi

    # List combined backups
    echo -e "${BLUE}Combined Backups (use with 'restore all'):${NC}"
    ls -lh "$BACKUP_DIR"/backup_*.tar.gz 2>/dev/null | awk '{print "  " $9 " (" $5 ") - " $6 " " $7 " " $8}' || echo -e "${YELLOW}  None${NC}"
    echo ""

    # List database backups
    echo -e "${BLUE}Database-only Backups (use with 'restore db'):${NC}"
    ls -lh "$BACKUP_DIR"/db_backup_*.sql.gz 2>/dev/null | awk '{print "  " $9 " (" $5 ") - " $6 " " $7 " " $8}' || echo -e "${YELLOW}  None${NC}"
    echo ""

    # List MinIO backups
    echo -e "${BLUE}MinIO-only Backups (use with 'restore minio'):${NC}"
    ls -lh "$BACKUP_DIR"/minio_backup_*.tar.gz 2>/dev/null | awk '{print "  " $9 " (" $5 ") - " $6 " " $7 " " $8}' || echo -e "${YELLOW}  None${NC}"
    echo ""
}

# Main script
show_usage() {
    echo "Usage: $0 <command> <backup_file>"
    echo ""
    echo "Commands:"
    echo "  all <file>      - Restore everything from combined backup"
    echo "  db <file>       - Restore database only"
    echo "  minio <file>    - Restore MinIO data only"
    echo "  list            - List available backups"
    echo ""
    echo "Examples:"
    echo "  $0 all backups/backup_20250124_120000.tar.gz"
    echo "  $0 db backups/db_backup_20250124_120000.sql.gz"
    echo "  $0 list"
}

# Parse command
COMMAND=${1:-help}
BACKUP_FILE=${2}

case "$COMMAND" in
    all)
        if [ -z "$BACKUP_FILE" ]; then
            echo -e "${RED}❌ Backup file required${NC}"
            echo ""
            show_usage
            exit 1
        fi
        restore_all "$BACKUP_FILE"
        ;;
    db|database)
        if [ -z "$BACKUP_FILE" ]; then
            echo -e "${RED}❌ Backup file required${NC}"
            echo ""
            show_usage
            exit 1
        fi
        restore_database "$BACKUP_FILE"
        ;;
    minio)
        if [ -z "$BACKUP_FILE" ]; then
            echo -e "${RED}❌ Backup file required${NC}"
            echo ""
            show_usage
            exit 1
        fi
        restore_minio "$BACKUP_FILE"
        ;;
    list|ls)
        list_backups
        ;;
    help|-h|--help)
        show_usage
        ;;
    *)
        echo -e "${RED}❌ Unknown command: $COMMAND${NC}"
        echo ""
        show_usage
        exit 1
        ;;
esac

# Success
exit 0
