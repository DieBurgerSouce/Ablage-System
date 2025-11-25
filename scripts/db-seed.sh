#!/bin/bash
# Database Seeding Script - Ablage-System OCR
# Populates database with test data for development

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DOCKER_COMPOSE="docker-compose -f docker-compose.yml -f docker-compose.dev.yml"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Function to check if database is accessible
check_database() {
    echo -e "${BLUE}🔍 Checking database connection...${NC}"

    if ! $DOCKER_COMPOSE ps postgres | grep -q "Up"; then
        echo -e "${RED}❌ PostgreSQL container is not running${NC}"
        echo -e "${YELLOW}Starting PostgreSQL...${NC}"
        $DOCKER_COMPOSE up -d postgres
        sleep 5
    fi

    # Test connection
    if $DOCKER_COMPOSE exec -T postgres pg_isready -U postgres > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Database is accessible${NC}"
    else
        echo -e "${RED}❌ Cannot connect to database${NC}"
        exit 1
    fi
}

# Function to run migrations
run_migrations() {
    echo -e "${BLUE}🔄 Running database migrations...${NC}"

    $DOCKER_COMPOSE exec -T backend alembic upgrade head

    echo -e "${GREEN}✅ Migrations complete${NC}"
}

# Function to seed users
seed_users() {
    echo -e "${BLUE}👥 Seeding users...${NC}"

    $DOCKER_COMPOSE exec -T postgres psql -U postgres -d ablage_ocr <<EOF
-- Create test users
INSERT INTO users (id, email, username, hashed_password, is_active, is_superuser, created_at)
VALUES
    ('00000000-0000-0000-0000-000000000001', 'admin@ablage-system.local', 'admin', '\$2b\$12\$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5NU7wPxE.nMii', true, true, NOW()),
    ('00000000-0000-0000-0000-000000000002', 'user1@ablage-system.local', 'user1', '\$2b\$12\$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5NU7wPxE.nMii', true, false, NOW()),
    ('00000000-0000-0000-0000-000000000003', 'user2@ablage-system.local', 'user2', '\$2b\$12\$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5NU7wPxE.nMii', true, false, NOW())
ON CONFLICT (email) DO NOTHING;

-- Default password for all test users: "password123"
EOF

    echo -e "${GREEN}✅ Users seeded (admin@ablage-system.local, user1@ablage-system.local, user2@ablage-system.local)${NC}"
    echo -e "${YELLOW}   Default password: password123${NC}"
}

# Function to seed documents
seed_documents() {
    echo -e "${BLUE}📄 Seeding sample documents...${NC}"

    $DOCKER_COMPOSE exec -T postgres psql -U postgres -d ablage_ocr <<EOF
-- Create sample documents
INSERT INTO documents (id, user_id, filename, original_filename, file_size, mime_type, status, language, created_at)
VALUES
    ('10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000002', 'sample_invoice.pdf', 'Rechnung_2024_001.pdf', 524288, 'application/pdf', 'processed', 'de', NOW() - INTERVAL '2 days'),
    ('10000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000002', 'sample_contract.pdf', 'Vertrag_Müller_GmbH.pdf', 1048576, 'application/pdf', 'processed', 'de', NOW() - INTERVAL '1 day'),
    ('10000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000003', 'sample_letter.pdf', 'Brief_Behörde.pdf', 262144, 'application/pdf', 'processing', 'de', NOW() - INTERVAL '1 hour'),
    ('10000000-0000-0000-0000-000000000004', '00000000-0000-0000-0000-000000000002', 'sample_receipt.jpg', 'Quittung_Supermarkt.jpg', 131072, 'image/jpeg', 'pending', 'de', NOW() - INTERVAL '30 minutes')
ON CONFLICT (id) DO NOTHING;

-- Add extracted text for processed documents
UPDATE documents
SET extracted_text = 'Rechnung Nr. 2024-001\n\nMüller GmbH\nMusterstraße 123\n12345 Berlin\n\nRechnungsdatum: 15.01.2024\nBetrag: 1.234,56 €\n\nMehrwertsteuer (19%): 234,56 €\nGesamtbetrag: 1.469,12 €',
    ocr_confidence = 0.98,
    processing_time_ms = 1500,
    ocr_backend = 'deepseek'
WHERE id = '10000000-0000-0000-0000-000000000001';

UPDATE documents
SET extracted_text = 'Vertrag zwischen Auftraggeber und Auftragnehmer\n\nVertragspartner:\nMüller GmbH\nMusterstraße 123, 12345 Berlin\n\nVertragsgegenstand:\nSoftware-Entwicklung für Dokumentenverwaltung\n\nVertragslaufzeit: 12 Monate\nVertragssumme: 50.000,00 €',
    ocr_confidence = 0.95,
    processing_time_ms = 2100,
    ocr_backend = 'got_ocr'
WHERE id = '10000000-0000-0000-0000-000000000002';
EOF

    echo -e "${GREEN}✅ Sample documents seeded (4 documents)${NC}"
}

# Function to seed tags
seed_tags() {
    echo -e "${BLUE}🏷️  Seeding tags and categories...${NC}"

    $DOCKER_COMPOSE exec -T postgres psql -U postgres -d ablage_ocr <<EOF
-- Create tags
INSERT INTO tags (id, name, color, created_at)
VALUES
    ('20000000-0000-0000-0000-000000000001', 'Rechnung', '#FF5733', NOW()),
    ('20000000-0000-0000-0000-000000000002', 'Vertrag', '#3498DB', NOW()),
    ('20000000-0000-0000-0000-000000000003', 'Brief', '#2ECC71', NOW()),
    ('20000000-0000-0000-0000-000000000004', 'Wichtig', '#E74C3C', NOW()),
    ('20000000-0000-0000-0000-000000000005', 'Archiv', '#95A5A6', NOW())
ON CONFLICT (name) DO NOTHING;

-- Tag documents
INSERT INTO document_tags (document_id, tag_id)
VALUES
    ('10000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000001'),
    ('10000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000004'),
    ('10000000-0000-0000-0000-000000000002', '20000000-0000-0000-0000-000000000002'),
    ('10000000-0000-0000-0000-000000000002', '20000000-0000-0000-0000-000000000004'),
    ('10000000-0000-0000-0000-000000000003', '20000000-0000-0000-0000-000000000003')
ON CONFLICT (document_id, tag_id) DO NOTHING;
EOF

    echo -e "${GREEN}✅ Tags and categories seeded${NC}"
}

# Function to seed OCR statistics
seed_statistics() {
    echo -e "${BLUE}📊 Seeding OCR statistics...${NC}"

    $DOCKER_COMPOSE exec -T postgres psql -U postgres -d ablage_ocr <<EOF
-- Create OCR statistics
INSERT INTO ocr_statistics (id, document_id, backend, processing_time_ms, confidence, gpu_used, vram_used_mb, created_at)
VALUES
    ('30000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', 'deepseek', 1500, 0.98, true, 8192, NOW() - INTERVAL '2 days'),
    ('30000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000002', 'got_ocr', 2100, 0.95, true, 6144, NOW() - INTERVAL '1 day')
ON CONFLICT (id) DO NOTHING;
EOF

    echo -e "${GREEN}✅ OCR statistics seeded${NC}"
}

# Function to display seeded data summary
show_summary() {
    echo ""
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo -e "${BLUE}   Database Seeding Complete! 🎉${NC}"
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo ""
    echo -e "${GREEN}📊 Seeded Data Summary:${NC}"
    echo ""

    # Count records
    USERS=$($DOCKER_COMPOSE exec -T postgres psql -U postgres -d ablage_ocr -t -c "SELECT COUNT(*) FROM users;")
    DOCUMENTS=$($DOCKER_COMPOSE exec -T postgres psql -U postgres -d ablage_ocr -t -c "SELECT COUNT(*) FROM documents;")
    TAGS=$($DOCKER_COMPOSE exec -T postgres psql -U postgres -d ablage_ocr -t -c "SELECT COUNT(*) FROM tags;")

    echo -e "${BLUE}  👥 Users:${NC} $USERS"
    echo -e "${BLUE}  📄 Documents:${NC} $DOCUMENTS"
    echo -e "${BLUE}  🏷️  Tags:${NC} $TAGS"
    echo ""
    echo -e "${YELLOW}🔑 Test Credentials:${NC}"
    echo -e "   Admin:  admin@ablage-system.local / password123"
    echo -e "   User 1: user1@ablage-system.local / password123"
    echo -e "   User 2: user2@ablage-system.local / password123"
    echo ""
    echo -e "${BLUE}🌐 Access the API:${NC}"
    echo -e "   http://localhost:8000/docs"
    echo ""
}

# Main script
main() {
    echo -e "${BLUE}🌱 Database Seeding Script${NC}"
    echo -e "${BLUE}═══════════════════════════${NC}"
    echo ""

    # Check if we're in development environment
    if [ ! -f "docker-compose.dev.yml" ]; then
        echo -e "${RED}❌ This script should only be run in development!${NC}"
        exit 1
    fi

    # Warning
    echo -e "${YELLOW}⚠️  Warning: This will add test data to your database${NC}"
    read -p "Continue? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Aborted${NC}"
        exit 0
    fi

    # Execute seeding steps
    check_database
    run_migrations
    seed_users
    seed_documents
    seed_tags
    seed_statistics
    show_summary

    echo -e "${GREEN}✅ Database seeding complete!${NC}"
}

# Run main function
main
