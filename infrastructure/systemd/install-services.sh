#!/bin/bash
# Systemd Services Installation Script - Ablage-System OCR
# Installs and configures systemd services for production deployment

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/ablage-system"
SYSTEMD_DIR="/etc/systemd/system"

echo -e "${BLUE}🔧 Systemd Services Installation${NC}"
echo -e "${BLUE}════════════════════════════════${NC}"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}❌ This script must be run as root${NC}"
    echo -e "${YELLOW}   Run with: sudo $0${NC}"
    exit 1
fi

# Function to check prerequisites
check_prerequisites() {
    echo -e "${BLUE}🔍 Checking prerequisites...${NC}"

    # Check systemd
    if ! command -v systemctl &> /dev/null; then
        echo -e "${RED}❌ systemd is not installed${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ systemd is installed${NC}"

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

# Function to create ablage user
create_user() {
    echo -e "${BLUE}👤 Creating ablage user...${NC}"

    if id "ablage" &>/dev/null; then
        echo -e "${YELLOW}⚠️  User 'ablage' already exists${NC}"
    else
        useradd -r -s /bin/false -d "$INSTALL_DIR" ablage
        echo -e "${GREEN}✅ User 'ablage' created${NC}"
    fi

    # Add ablage user to docker group
    if ! groups ablage | grep -q docker; then
        usermod -aG docker ablage
        echo -e "${GREEN}✅ User 'ablage' added to docker group${NC}"
    fi
}

# Function to setup installation directory
setup_install_dir() {
    echo -e "${BLUE}📁 Setting up installation directory...${NC}"

    # Create directory if it doesn't exist
    if [ ! -d "$INSTALL_DIR" ]; then
        mkdir -p "$INSTALL_DIR"
        echo -e "${GREEN}✅ Created $INSTALL_DIR${NC}"
    fi

    # Copy application files (if running from source)
    if [ "$(pwd)" != "$INSTALL_DIR" ]; then
        echo -e "${YELLOW}Copying application files to $INSTALL_DIR...${NC}"

        # Create subdirectories
        mkdir -p "$INSTALL_DIR/logs"
        mkdir -p "$INSTALL_DIR/data"
        mkdir -p "$INSTALL_DIR/backups"

        # Copy files
        rsync -av --exclude '.git' --exclude 'node_modules' --exclude '__pycache__' \
            "$(dirname "$SCRIPT_DIR")/" "$INSTALL_DIR/" 2>/dev/null || \
            cp -r "$(dirname "$SCRIPT_DIR")/"* "$INSTALL_DIR/" 2>/dev/null || true

        echo -e "${GREEN}✅ Files copied${NC}"
    fi

    # Set ownership
    chown -R ablage:ablage "$INSTALL_DIR"
    echo -e "${GREEN}✅ Ownership set to ablage:ablage${NC}"

    # Set permissions
    chmod 750 "$INSTALL_DIR"
    chmod 640 "$INSTALL_DIR/.env" 2>/dev/null || true
    echo -e "${GREEN}✅ Permissions set${NC}"
}

# Function to install systemd service files
install_services() {
    echo -e "${BLUE}📦 Installing systemd service files...${NC}"

    # Copy service files
    for service in "$SCRIPT_DIR"/*.service "$SCRIPT_DIR"/*.target; do
        if [ -f "$service" ]; then
            filename=$(basename "$service")
            cp "$service" "$SYSTEMD_DIR/$filename"
            echo -e "${GREEN}✅ Installed $filename${NC}"
        fi
    done

    # Reload systemd
    systemctl daemon-reload
    echo -e "${GREEN}✅ Systemd daemon reloaded${NC}"
}

# Function to enable services
enable_services() {
    echo -e "${BLUE}⚙️  Enabling services...${NC}"

    # Enable main service
    systemctl enable ablage-system.service
    echo -e "${GREEN}✅ Enabled ablage-system.service${NC}"

    # Enable target
    systemctl enable ablage-system.target
    echo -e "${GREEN}✅ Enabled ablage-system.target${NC}"

    # Enable component services (optional)
    read -p "Enable individual component services? (Y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        for service in "$SYSTEMD_DIR"/ablage-*.service; do
            if [ -f "$service" ] && [ "$(basename "$service")" != "ablage-system.service" ]; then
                systemctl enable "$(basename "$service")"
                echo -e "${GREEN}✅ Enabled $(basename "$service")${NC}"
            fi
        done
    fi
}

# Function to create environment file
create_env_file() {
    echo -e "${BLUE}🔧 Creating environment file...${NC}"

    if [ -f "$INSTALL_DIR/.env" ]; then
        echo -e "${YELLOW}⚠️  .env file already exists${NC}"
        read -p "Overwrite? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            return
        fi
    fi

    # Copy from example
    if [ -f "$INSTALL_DIR/.env.example" ]; then
        cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
        echo -e "${GREEN}✅ Created .env from example${NC}"
        echo -e "${YELLOW}⚠️  Edit $INSTALL_DIR/.env and configure secrets${NC}"
    else
        echo -e "${YELLOW}⚠️  .env.example not found, skipping${NC}"
    fi
}

# Function to setup logging
setup_logging() {
    echo -e "${BLUE}📝 Setting up logging...${NC}"

    # Create journald drop-in for ablage services
    JOURNALD_CONF_DIR="/etc/systemd/journald.conf.d"
    mkdir -p "$JOURNALD_CONF_DIR"

    cat > "$JOURNALD_CONF_DIR/ablage-system.conf" <<EOF
[Journal]
# Ablage-System specific logging configuration
MaxLevelStore=info
MaxLevelSyslog=warning
MaxLevelConsole=warning
EOF

    echo -e "${GREEN}✅ Journald configuration created${NC}"

    # Restart journald
    systemctl restart systemd-journald
    echo -e "${GREEN}✅ Journald restarted${NC}"
}

# Function to setup logrotate
setup_logrotate() {
    echo -e "${BLUE}📝 Setting up log rotation...${NC}"

    cat > "/etc/logrotate.d/ablage-system" <<EOF
$INSTALL_DIR/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0640 ablage ablage
    sharedscripts
    postrotate
        systemctl reload ablage-system.service > /dev/null 2>&1 || true
    endscript
}
EOF

    echo -e "${GREEN}✅ Logrotate configuration created${NC}"
}

# Function to create firewall rules
setup_firewall() {
    echo -e "${BLUE}🔥 Setting up firewall rules...${NC}"

    if command -v ufw &> /dev/null; then
        echo -e "${BLUE}Using UFW...${NC}"

        # Allow HTTP and HTTPS
        ufw allow 80/tcp comment 'Ablage-System HTTP'
        ufw allow 443/tcp comment 'Ablage-System HTTPS'

        # Allow SSH (if not already allowed)
        ufw allow 22/tcp comment 'SSH'

        echo -e "${GREEN}✅ UFW rules added${NC}"

    elif command -v firewall-cmd &> /dev/null; then
        echo -e "${BLUE}Using firewalld...${NC}"

        # Allow HTTP and HTTPS
        firewall-cmd --permanent --add-service=http
        firewall-cmd --permanent --add-service=https
        firewall-cmd --reload

        echo -e "${GREEN}✅ Firewalld rules added${NC}"

    else
        echo -e "${YELLOW}⚠️  No firewall detected, skipping${NC}"
    fi
}

# Function to start services
start_services() {
    echo -e "${BLUE}🚀 Starting services...${NC}"

    read -p "Start services now? (Y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        systemctl start ablage-system.target
        echo -e "${GREEN}✅ Services started${NC}"

        # Wait a moment and check status
        sleep 5
        systemctl status ablage-system.service --no-pager || true
    fi
}

# Function to show service status
show_status() {
    echo ""
    echo -e "${BLUE}📊 Service Status:${NC}"
    echo ""

    # List all ablage services
    systemctl list-units --type=service --state=running ablage-* --no-pager
}

# Function to show summary
show_summary() {
    echo ""
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo -e "${BLUE}   Systemd Services Installed! 🎉${NC}"
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo ""
    echo -e "${GREEN}✅ Installation complete${NC}"
    echo ""
    echo -e "${BLUE}📋 Installed Services:${NC}"
    echo -e "   ablage-system.target     - Main target (all services)"
    echo -e "   ablage-system.service    - Docker Compose stack"
    echo -e "   ablage-backend.service   - Backend API"
    echo -e "   ablage-worker.service    - Celery Worker"
    echo ""
    echo -e "${BLUE}📝 Useful Commands:${NC}"
    echo -e "   Start all:       ${GREEN}sudo systemctl start ablage-system.target${NC}"
    echo -e "   Stop all:        ${GREEN}sudo systemctl stop ablage-system.target${NC}"
    echo -e "   Restart all:     ${GREEN}sudo systemctl restart ablage-system.target${NC}"
    echo -e "   Status:          ${GREEN}sudo systemctl status ablage-system.service${NC}"
    echo -e "   Logs:            ${GREEN}sudo journalctl -u ablage-system.service -f${NC}"
    echo -e "   Logs (backend):  ${GREEN}sudo journalctl -u ablage-backend.service -f${NC}"
    echo ""
    echo -e "${BLUE}🔧 Configuration:${NC}"
    echo -e "   Install dir:  $INSTALL_DIR"
    echo -e "   Env file:     $INSTALL_DIR/.env"
    echo -e "   Logs:         $INSTALL_DIR/logs/"
    echo -e "   Services:     $SYSTEMD_DIR/ablage-*.service"
    echo ""
    echo -e "${YELLOW}⚠️  Next Steps:${NC}"
    echo -e "   1. Edit environment file: sudo nano $INSTALL_DIR/.env"
    echo -e "   2. Configure secrets (database passwords, API keys, etc.)"
    echo -e "   3. Start services: sudo systemctl start ablage-system.target"
    echo -e "   4. Check status: sudo systemctl status ablage-system.service"
    echo -e "   5. View logs: sudo journalctl -u ablage-system.service -f"
    echo ""
}

# Main installation flow
main() {
    check_prerequisites
    echo ""

    create_user
    echo ""

    setup_install_dir
    echo ""

    create_env_file
    echo ""

    install_services
    echo ""

    enable_services
    echo ""

    setup_logging
    echo ""

    setup_logrotate
    echo ""

    setup_firewall
    echo ""

    start_services

    show_status
    show_summary
}

# Run main function
main
