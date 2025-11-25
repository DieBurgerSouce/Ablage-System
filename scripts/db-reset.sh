#!/bin/bash
# Database Reset Script - Ablage-System
# WARNING: This will DELETE ALL DATA!
# Usage: ./scripts/db-reset.sh

set -e

# Colors
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${RED}⚠️  WARNING: This will DELETE ALL DATA!${NC}"
echo -e "${YELLOW}Are you sure you want to reset the database? (yes/no)${NC}"
read -r response

if [ "$response" != "yes" ]; then
    echo -e "${YELLOW}Cancelled.${NC}"
    exit 0
fi

echo -e "\n${RED}Resetting database...${NC}\n"

# Stop services
docker-compose down

# Remove volumes
docker volume rm ablage-system_postgres_data 2>/dev/null || true

# Start postgres
docker-compose up -d postgres

# Wait for postgres
echo "Waiting for PostgreSQL to start..."
sleep 5

# Run migrations
alembic upgrade head

echo -e "\n${YELLOW}✅ Database reset complete${NC}"
echo -e "${YELLOW}Run: ./scripts/dev.sh to start development server${NC}"
