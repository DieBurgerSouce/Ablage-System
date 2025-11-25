#!/bin/bash
# Backup Script for Ablage-System
# Creates backups of database and MinIO data

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BACKUP_DIR="backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DOCKER_COMPOSE="docker-compose -f docker-compose.yml -f docker-compose.dev.yml"

# Ensure backup directory exists
mkdir -p "$BACKUP_DIR"

# Function to backup database
backup_database() {
    echo -e "${BLUE}💾 Backing up PostgreSQL database...${NC}"

    DB_BACKUP_FILE="$BACKUP_DIR/db_backup_$TIMESTAMP.sql"

    # Check if postgres container is running
    if ! $DOCKER_COMPOSE ps postgres | grep -q "Up"; then
        echo -e "${RED}❌ PostgreSQL container is not running${NC}"
        return 1
    fi

    # Dump database
    $DOCKER_COMPOSE exec -T postgres pg_dump -U postgres -d ablage_ocr > "$DB_BACKUP_FILE"

    # Compress backup
    gzip "$DB_BACKUP_FILE"
    DB_BACKUP_FILE="${DB_BACKUP_FILE}.gz"

    # Get file size
    SIZE=$(du -h "$DB_BACKUP_FILE" | cut -f1)

    echo -e "${GREEN}✅ Database backup complete: $DB_BACKUP_FILE ($SIZE)${NC}"
    echo "$DB_BACKUP_FILE"
}

# Function to backup MinIO data
backup_minio() {
    echo -e "${BLUE}💾 Backing up MinIO data...${NC}"

    MINIO_BACKUP_FILE="$BACKUP_DIR/minio_backup_$TIMESTAMP.tar.gz"

    # Check if minio container is running
    if ! $DOCKER_COMPOSE ps minio | grep -q "Up"; then
        echo -e "${RED}❌ MinIO container is not running${NC}"
        return 1
    fi

    # Create temporary directory for backup
    TEMP_DIR=$(mktemp -d)

    # Export MinIO data using mc (MinIO client)
    echo -e "${YELLOW}Exporting MinIO buckets...${NC}"

    # List of buckets to backup
    BUCKETS=("documents" "thumbnails" "exports")

    for bucket in "${BUCKETS[@]}"; do
        echo -e "${BLUE}  → Backing up bucket: $bucket${NC}"

        # Check if bucket exists
        if $DOCKER_COMPOSE exec -T minio mc ls local/$bucket > /dev/null 2>&1; then
            # Mirror bucket to temp directory
            $DOCKER_COMPOSE exec -T minio mc mirror --quiet local/$bucket "$TEMP_DIR/$bucket" || true
        else
            echo -e "${YELLOW}    Bucket $bucket does not exist, skipping${NC}"
        fi
    done

    # Create tarball from temp directory
    tar -czf "$MINIO_BACKUP_FILE" -C "$TEMP_DIR" . 2>/dev/null || true

    # Cleanup temp directory
    rm -rf "$TEMP_DIR"

    # Get file size
    if [ -f "$MINIO_BACKUP_FILE" ]; then
        SIZE=$(du -h "$MINIO_BACKUP_FILE" | cut -f1)
        echo -e "${GREEN}✅ MinIO backup complete: $MINIO_BACKUP_FILE ($SIZE)${NC}"
        echo "$MINIO_BACKUP_FILE"
    else
        echo -e "${YELLOW}⚠  MinIO backup created but empty${NC}"
    fi
}

# Function to create combined backup
backup_all() {
    echo -e "${BLUE}💾 Creating complete backup...${NC}"
    echo ""

    # Backup database
    DB_BACKUP=$(backup_database)
    echo ""

    # Backup MinIO
    MINIO_BACKUP=$(backup_minio)
    echo ""

    # Create combined archive
    COMBINED_BACKUP="$BACKUP_DIR/backup_$TIMESTAMP.tar.gz"

    echo -e "${BLUE}📦 Creating combined archive...${NC}"

    # Add metadata file
    METADATA_FILE="$BACKUP_DIR/backup_metadata_$TIMESTAMP.txt"
    cat > "$METADATA_FILE" <<EOF
Ablage-System Backup
====================
Date: $(date)
Timestamp: $TIMESTAMP
Database Backup: $(basename $DB_BACKUP)
MinIO Backup: $(basename $MINIO_BACKUP)
Version: $(cat VERSION 2>/dev/null || echo "unknown")
EOF

    # Create combined archive
    tar -czf "$COMBINED_BACKUP" \
        "$DB_BACKUP" \
        "$MINIO_BACKUP" \
        "$METADATA_FILE" 2>/dev/null || true

    # Cleanup individual backups and metadata
    rm -f "$DB_BACKUP" "$MINIO_BACKUP" "$METADATA_FILE"

    # Get combined file size
    if [ -f "$COMBINED_BACKUP" ]; then
        SIZE=$(du -h "$COMBINED_BACKUP" | cut -f1)
        echo -e "${GREEN}✅ Combined backup complete: $COMBINED_BACKUP ($SIZE)${NC}"
        echo ""
        echo -e "${BLUE}📊 Backup Summary:${NC}"
        echo -e "  File: $COMBINED_BACKUP"
        echo -e "  Size: $SIZE"
        echo -e "  Timestamp: $TIMESTAMP"
    else
        echo -e "${RED}❌ Failed to create combined backup${NC}"
        exit 1
    fi
}

# Function to list backups
list_backups() {
    echo -e "${BLUE}📋 Available Backups:${NC}"
    echo ""

    if [ ! -d "$BACKUP_DIR" ] || [ -z "$(ls -A $BACKUP_DIR 2>/dev/null)" ]; then
        echo -e "${YELLOW}No backups found${NC}"
        exit 0
    fi

    # List backup files with details
    echo -e "${BLUE}Database Backups:${NC}"
    ls -lh "$BACKUP_DIR"/db_backup_*.sql.gz 2>/dev/null | awk '{print "  " $9 " (" $5 ") - " $6 " " $7 " " $8}' || echo -e "${YELLOW}  None${NC}"
    echo ""

    echo -e "${BLUE}MinIO Backups:${NC}"
    ls -lh "$BACKUP_DIR"/minio_backup_*.tar.gz 2>/dev/null | awk '{print "  " $9 " (" $5 ") - " $6 " " $7 " " $8}' || echo -e "${YELLOW}  None${NC}"
    echo ""

    echo -e "${BLUE}Combined Backups:${NC}"
    ls -lh "$BACKUP_DIR"/backup_*.tar.gz 2>/dev/null | awk '{print "  " $9 " (" $5 ") - " $6 " " $7 " " $8}' || echo -e "${YELLOW}  None${NC}"
    echo ""
}

# Function to cleanup old backups
cleanup_old_backups() {
    local DAYS=${1:-30}

    echo -e "${BLUE}🧹 Cleaning up backups older than $DAYS days...${NC}"

    if [ ! -d "$BACKUP_DIR" ]; then
        echo -e "${YELLOW}No backup directory found${NC}"
        return 0
    fi

    # Find and delete old backups
    DELETED=$(find "$BACKUP_DIR" -name "*.gz" -type f -mtime +$DAYS -delete -print | wc -l)

    if [ "$DELETED" -gt 0 ]; then
        echo -e "${GREEN}✅ Deleted $DELETED old backup(s)${NC}"
    else
        echo -e "${YELLOW}No old backups to delete${NC}"
    fi
}

# Main script
show_usage() {
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  all          - Backup everything (database + MinIO)"
    echo "  db           - Backup database only"
    echo "  minio        - Backup MinIO data only"
    echo "  list         - List all available backups"
    echo "  cleanup      - Remove old backups (default: 30 days)"
    echo ""
    echo "Examples:"
    echo "  $0 all"
    echo "  $0 db"
    echo "  $0 cleanup 7  # Delete backups older than 7 days"
}

# Parse command
COMMAND=${1:-all}

case "$COMMAND" in
    all)
        backup_all
        ;;
    db|database)
        backup_database
        ;;
    minio)
        backup_minio
        ;;
    list|ls)
        list_backups
        ;;
    cleanup|clean)
        DAYS=${2:-30}
        cleanup_old_backups "$DAYS"
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
