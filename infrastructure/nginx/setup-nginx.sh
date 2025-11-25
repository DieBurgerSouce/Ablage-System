#!/bin/bash
# Nginx Setup Script - Ablage-System OCR
# Initial setup and configuration validation

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${BLUE}🌐 Nginx Setup Script${NC}"
echo -e "${BLUE}════════════════════${NC}"
echo ""

# Function to check prerequisites
check_prerequisites() {
    echo -e "${BLUE}🔍 Checking prerequisites...${NC}"

    # Check Docker
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}❌ Docker is not installed${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ Docker is installed${NC}"

    # Check docker-compose
    if ! command -v docker-compose &> /dev/null; then
        echo -e "${RED}❌ docker-compose is not installed${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ docker-compose is installed${NC}"
}

# Function to create htpasswd file
create_htpasswd() {
    echo -e "${BLUE}🔐 Creating htpasswd file for Prometheus...${NC}"

    if [ -f "$SCRIPT_DIR/.htpasswd" ]; then
        echo -e "${YELLOW}⚠️  htpasswd file already exists${NC}"
        read -p "Recreate? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            return
        fi
    fi

    # Use Docker to create htpasswd (no local apache2-utils needed)
    read -p "Enter username for Prometheus access: " username
    read -sp "Enter password: " password
    echo

    docker run --rm httpd:alpine htpasswd -nb "$username" "$password" > "$SCRIPT_DIR/.htpasswd"

    echo -e "${GREEN}✅ htpasswd file created${NC}"
}

# Function to generate DH parameters
generate_dhparam() {
    echo -e "${BLUE}🔒 Generating DH parameters (this may take a while)...${NC}"

    if [ -f "$SCRIPT_DIR/dhparam.pem" ]; then
        echo -e "${YELLOW}⚠️  DH parameters already exist${NC}"
        return
    fi

    # Generate 4096-bit DH parameters
    docker run --rm -v "$SCRIPT_DIR:/output" alpine/openssl dhparam -out /output/dhparam.pem 4096

    echo -e "${GREEN}✅ DH parameters generated${NC}"
}

# Function to validate configuration
validate_config() {
    echo -e "${BLUE}🔍 Validating Nginx configuration...${NC}"

    # Build the container if not exists
    if ! docker images | grep -q "ablage-nginx"; then
        echo -e "${YELLOW}Building Nginx image...${NC}"
        docker build -t ablage-nginx "$SCRIPT_DIR"
    fi

    # Test configuration
    docker run --rm -v "$SCRIPT_DIR/nginx.conf:/etc/nginx/nginx.conf:ro" \
        -v "$SCRIPT_DIR/conf.d:/etc/nginx/conf.d:ro" \
        -v "$SCRIPT_DIR/snippets:/etc/nginx/snippets:ro" \
        nginx:alpine nginx -t

    echo -e "${GREEN}✅ Nginx configuration is valid${NC}"
}

# Function to setup hosts file entries
setup_hosts() {
    echo -e "${BLUE}🌐 Setting up hosts file entries...${NC}"

    HOSTS_FILE="/etc/hosts"
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
        HOSTS_FILE="C:\\Windows\\System32\\drivers\\etc\\hosts"
    fi

    echo -e "${YELLOW}Add these entries to $HOSTS_FILE:${NC}"
    echo ""
    echo "127.0.0.1 ablage-system.local"
    echo "127.0.0.1 grafana.ablage-system.local"
    echo "127.0.0.1 prometheus.ablage-system.local"
    echo ""
    echo -e "${BLUE}On Linux/Mac:${NC}"
    echo "sudo sh -c 'echo \"127.0.0.1 ablage-system.local\" >> /etc/hosts'"
    echo "sudo sh -c 'echo \"127.0.0.1 grafana.ablage-system.local\" >> /etc/hosts'"
    echo "sudo sh -c 'echo \"127.0.0.1 prometheus.ablage-system.local\" >> /etc/hosts'"
    echo ""
    echo -e "${BLUE}On Windows (as Administrator):${NC}"
    echo "echo 127.0.0.1 ablage-system.local >> C:\\Windows\\System32\\drivers\\etc\\hosts"
    echo "echo 127.0.0.1 grafana.ablage-system.local >> C:\\Windows\\System32\\drivers\\etc\\hosts"
    echo "echo 127.0.0.1 prometheus.ablage-system.local >> C:\\Windows\\System32\\drivers\\etc\\hosts"
    echo ""
}

# Function to create docker network
create_network() {
    echo -e "${BLUE}🔗 Creating Docker network...${NC}"

    if docker network ls | grep -q "ablage_network"; then
        echo -e "${YELLOW}⚠️  Network already exists${NC}"
    else
        docker network create ablage_network
        echo -e "${GREEN}✅ Network created${NC}"
    fi
}

# Function to start Nginx
start_nginx() {
    echo -e "${BLUE}🚀 Starting Nginx...${NC}"

    cd "$SCRIPT_DIR"
    docker-compose -f docker-compose.nginx.yml up -d

    echo -e "${GREEN}✅ Nginx started${NC}"
    echo ""
    echo -e "${BLUE}Container status:${NC}"
    docker-compose -f docker-compose.nginx.yml ps
}

# Function to show summary
show_summary() {
    echo ""
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo -e "${BLUE}   Nginx Setup Complete! 🎉${NC}"
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo ""
    echo -e "${GREEN}✅ Nginx is running${NC}"
    echo ""
    echo -e "${BLUE}🌐 Access Points:${NC}"
    echo -e "   Main App:    http://ablage-system.local"
    echo -e "   Grafana:     http://grafana.ablage-system.local"
    echo -e "   Prometheus:  http://prometheus.ablage-system.local"
    echo ""
    echo -e "${YELLOW}⚠️  Note: HTTPS is not yet configured${NC}"
    echo -e "   Run the SSL setup script to enable HTTPS:"
    echo -e "   ${GREEN}cd ../../ && ./scripts/ssl-setup.sh${NC}"
    echo ""
    echo -e "${BLUE}📝 Useful Commands:${NC}"
    echo -e "   View logs:       docker logs -f ablage-nginx"
    echo -e "   Reload config:   docker exec ablage-nginx nginx -s reload"
    echo -e "   Test config:     docker exec ablage-nginx nginx -t"
    echo -e "   Stop:            docker-compose -f docker-compose.nginx.yml down"
    echo ""
}

# Main setup flow
main() {
    check_prerequisites
    echo ""

    create_htpasswd
    echo ""

    generate_dhparam
    echo ""

    validate_config
    echo ""

    create_network
    echo ""

    setup_hosts
    echo ""

    read -p "Start Nginx now? (Y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        start_nginx
    fi

    show_summary
}

# Run main function
main
