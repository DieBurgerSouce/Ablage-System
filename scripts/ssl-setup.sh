#!/bin/bash
# SSL/TLS Setup Script - Ablage-System OCR
# Automated Let's Encrypt certificate provisioning with Certbot

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DOMAIN="${DOMAIN:-ablage-system.local}"
EMAIL="${LETSENCRYPT_EMAIL:-admin@${DOMAIN}}"
STAGING="${STAGING:-false}"
CERTBOT_CONTAINER="ablage-certbot"
NGINX_CONTAINER="ablage-nginx"

echo -e "${BLUE}🔒 SSL/TLS Setup Script${NC}"
echo -e "${BLUE}══════════════════════${NC}"
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

    # Check if nginx is running
    if ! docker ps | grep -q "$NGINX_CONTAINER"; then
        echo -e "${YELLOW}⚠️  Nginx container is not running${NC}"
        read -p "Start Nginx now? (Y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            cd infrastructure/nginx
            docker-compose -f docker-compose.nginx.yml up -d
            sleep 5
            cd -
        else
            echo -e "${RED}❌ Nginx must be running for SSL setup${NC}"
            exit 1
        fi
    fi
    echo -e "${GREEN}✅ Nginx is running${NC}"

    # Check if domain is reachable
    if [ "$DOMAIN" != "*.local" ]; then
        echo -e "${BLUE}🌐 Checking domain accessibility...${NC}"
        if curl -s --connect-timeout 5 "http://$DOMAIN/.well-known/acme-challenge/test" > /dev/null 2>&1; then
            echo -e "${GREEN}✅ Domain is accessible${NC}"
        else
            echo -e "${YELLOW}⚠️  Cannot reach http://$DOMAIN${NC}"
            echo -e "${YELLOW}   Make sure your domain DNS is properly configured${NC}"
        fi
    fi
}

# Function to validate domain
validate_domain() {
    echo -e "${BLUE}🔍 Validating domain: $DOMAIN${NC}"

    # Check if domain contains localhost or .local
    if [[ "$DOMAIN" == *"localhost"* ]] || [[ "$DOMAIN" == *".local"* ]]; then
        echo -e "${YELLOW}⚠️  Local domain detected: $DOMAIN${NC}"
        echo -e "${YELLOW}   Let's Encrypt cannot issue certificates for local domains${NC}"
        echo -e "${BLUE}   For local development, use self-signed certificates${NC}"
        read -p "Generate self-signed certificate? (Y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            generate_selfsigned
            exit 0
        else
            exit 1
        fi
    fi

    echo -e "${GREEN}✅ Domain is valid for Let's Encrypt${NC}"
}

# Function to generate self-signed certificate
generate_selfsigned() {
    echo -e "${BLUE}🔐 Generating self-signed certificate...${NC}"

    CERT_DIR="infrastructure/nginx/certs"
    mkdir -p "$CERT_DIR"

    # Generate private key
    openssl genrsa -out "$CERT_DIR/$DOMAIN.key" 4096

    # Generate certificate signing request
    openssl req -new -key "$CERT_DIR/$DOMAIN.key" -out "$CERT_DIR/$DOMAIN.csr" \
        -subj "/C=DE/ST=Germany/L=Berlin/O=Ablage-System/CN=$DOMAIN"

    # Generate self-signed certificate (valid for 365 days)
    openssl x509 -req -days 365 -in "$CERT_DIR/$DOMAIN.csr" -signkey "$CERT_DIR/$DOMAIN.key" \
        -out "$CERT_DIR/$DOMAIN.crt" \
        -extensions v3_req -extfile <(cat <<EOF
[v3_req]
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = $DOMAIN
DNS.2 = *.$DOMAIN
DNS.3 = grafana.$DOMAIN
DNS.4 = prometheus.$DOMAIN
EOF
)

    # Create fullchain (self-signed doesn't have chain)
    cp "$CERT_DIR/$DOMAIN.crt" "$CERT_DIR/$DOMAIN-fullchain.crt"

    echo -e "${GREEN}✅ Self-signed certificate generated${NC}"
    echo -e "${BLUE}📁 Certificate files:${NC}"
    echo -e "   Key:       $CERT_DIR/$DOMAIN.key"
    echo -e "   Cert:      $CERT_DIR/$DOMAIN.crt"
    echo -e "   Fullchain: $CERT_DIR/$DOMAIN-fullchain.crt"
    echo ""
    echo -e "${YELLOW}⚠️  Note: Self-signed certificates will show warnings in browsers${NC}"
    echo -e "${BLUE}   To trust the certificate:${NC}"
    echo -e "   • Firefox: Add exception in browser"
    echo -e "   • Chrome: Import to system trust store"
    echo -e "   • curl: Use --insecure or -k flag"
}

# Function to request Let's Encrypt certificate
request_certificate() {
    echo -e "${BLUE}📜 Requesting Let's Encrypt certificate...${NC}"

    # Staging or production
    if [ "$STAGING" = "true" ]; then
        echo -e "${YELLOW}Using Let's Encrypt staging server (for testing)${NC}"
        STAGING_FLAG="--staging"
    else
        STAGING_FLAG=""
    fi

    # Domains to include in certificate
    DOMAINS="-d $DOMAIN"

    # Add subdomains if main domain
    if [[ ! "$DOMAIN" == www.* ]]; then
        DOMAINS="$DOMAINS -d www.$DOMAIN -d grafana.$DOMAIN -d prometheus.$DOMAIN"
    fi

    echo -e "${BLUE}Domains: $DOMAINS${NC}"
    echo -e "${BLUE}Email: $EMAIL${NC}"
    echo ""

    # Run certbot
    docker run --rm \
        -v certbot_conf:/etc/letsencrypt \
        -v certbot_www:/var/www/certbot \
        certbot/certbot certonly \
        --webroot \
        --webroot-path=/var/www/certbot \
        --email "$EMAIL" \
        --agree-tos \
        --no-eff-email \
        $STAGING_FLAG \
        $DOMAINS

    echo -e "${GREEN}✅ Certificate obtained successfully${NC}"
}

# Function to request wildcard certificate (DNS challenge)
request_wildcard() {
    echo -e "${BLUE}📜 Requesting wildcard certificate...${NC}"
    echo -e "${YELLOW}⚠️  Wildcard certificates require DNS validation${NC}"
    echo ""

    # Get DNS plugin
    echo -e "${BLUE}Available DNS plugins:${NC}"
    echo "  1. cloudflare"
    echo "  2. route53 (AWS)"
    echo "  3. digitalocean"
    echo "  4. manual (requires manual DNS record creation)"
    echo ""
    read -p "Select DNS provider (1-4): " dns_choice

    case $dns_choice in
        1)
            DNS_PLUGIN="--dns-cloudflare"
            echo -e "${YELLOW}Set CLOUDFLARE_API_TOKEN in environment${NC}"
            ;;
        2)
            DNS_PLUGIN="--dns-route53"
            echo -e "${YELLOW}Ensure AWS credentials are configured${NC}"
            ;;
        3)
            DNS_PLUGIN="--dns-digitalocean"
            echo -e "${YELLOW}Set DIGITALOCEAN_TOKEN in environment${NC}"
            ;;
        4)
            DNS_PLUGIN="--manual --preferred-challenges dns"
            ;;
        *)
            echo -e "${RED}Invalid choice${NC}"
            exit 1
            ;;
    esac

    docker run --rm -it \
        -v certbot_conf:/etc/letsencrypt \
        -v certbot_www:/var/www/certbot \
        certbot/certbot certonly \
        $DNS_PLUGIN \
        --email "$EMAIL" \
        --agree-tos \
        --no-eff-email \
        -d "$DOMAIN" \
        -d "*.$DOMAIN"

    echo -e "${GREEN}✅ Wildcard certificate obtained${NC}"
}

# Function to test certificate renewal
test_renewal() {
    echo -e "${BLUE}🔄 Testing certificate renewal (dry-run)...${NC}"

    docker run --rm \
        -v certbot_conf:/etc/letsencrypt \
        -v certbot_www:/var/www/certbot \
        certbot/certbot renew --dry-run

    echo -e "${GREEN}✅ Renewal test successful${NC}"
}

# Function to setup auto-renewal
setup_autorenewal() {
    echo -e "${BLUE}🔄 Setting up automatic renewal...${NC}"

    # Certbot container already runs renewal check every 12 hours
    # This is configured in docker-compose.nginx.yml

    # Add cron job for additional safety (optional)
    CRON_JOB="0 0,12 * * * docker run --rm -v certbot_conf:/etc/letsencrypt -v certbot_www:/var/www/certbot certbot/certbot renew --quiet && docker exec ablage-nginx nginx -s reload"

    echo -e "${BLUE}Automatic renewal is configured via Docker container${NC}"
    echo -e "${YELLOW}Optional: Add cron job for redundancy:${NC}"
    echo -e "   $CRON_JOB"
    echo ""
    echo -e "${BLUE}To add to crontab:${NC}"
    echo -e "   crontab -e"
    echo -e "   # Add the line above"
}

# Function to reload Nginx
reload_nginx() {
    echo -e "${BLUE}🔄 Reloading Nginx...${NC}"

    if docker exec "$NGINX_CONTAINER" nginx -t > /dev/null 2>&1; then
        docker exec "$NGINX_CONTAINER" nginx -s reload
        echo -e "${GREEN}✅ Nginx reloaded successfully${NC}"
    else
        echo -e "${RED}❌ Nginx configuration test failed${NC}"
        docker exec "$NGINX_CONTAINER" nginx -t
        exit 1
    fi
}

# Function to verify SSL
verify_ssl() {
    echo -e "${BLUE}🔍 Verifying SSL configuration...${NC}"

    # Check if certificates exist
    if docker exec "$NGINX_CONTAINER" test -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem"; then
        echo -e "${GREEN}✅ Certificate files exist${NC}"

        # Check certificate validity
        docker exec "$NGINX_CONTAINER" openssl x509 \
            -in "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" \
            -noout -dates

        # Test HTTPS connection
        if curl -sI --connect-timeout 5 "https://$DOMAIN" > /dev/null 2>&1; then
            echo -e "${GREEN}✅ HTTPS is working${NC}"
        else
            echo -e "${YELLOW}⚠️  Cannot connect via HTTPS yet${NC}"
            echo -e "${BLUE}   This may take a moment for DNS propagation${NC}"
        fi
    else
        echo -e "${YELLOW}⚠️  Certificate files not found${NC}"
    fi
}

# Function to show certificate info
show_certificate_info() {
    echo -e "${BLUE}📋 Certificate Information:${NC}"
    echo ""

    docker exec "$NGINX_CONTAINER" openssl x509 \
        -in "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" \
        -noout \
        -subject \
        -issuer \
        -dates \
        -ext subjectAltName 2>/dev/null || echo -e "${YELLOW}Certificate not found${NC}"
}

# Function to show summary
show_summary() {
    echo ""
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo -e "${BLUE}   SSL/TLS Setup Complete! 🔒${NC}"
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo ""
    echo -e "${GREEN}✅ SSL certificate configured${NC}"
    echo ""
    echo -e "${BLUE}🌐 Your sites are now accessible via HTTPS:${NC}"
    echo -e "   https://$DOMAIN"
    echo -e "   https://www.$DOMAIN"
    echo -e "   https://grafana.$DOMAIN"
    echo -e "   https://prometheus.$DOMAIN"
    echo ""
    echo -e "${BLUE}🔄 Certificate Renewal:${NC}"
    echo -e "   Automatic renewal is configured"
    echo -e "   Certificates will auto-renew 30 days before expiry"
    echo ""
    echo -e "${BLUE}📝 Useful Commands:${NC}"
    echo -e "   Check cert expiry:   ./scripts/ssl-setup.sh info"
    echo -e "   Force renewal:       ./scripts/ssl-setup.sh renew"
    echo -e "   Test renewal:        ./scripts/ssl-setup.sh test"
    echo -e "   Revoke cert:         ./scripts/ssl-setup.sh revoke"
    echo ""
    echo -e "${BLUE}🔍 SSL Test:${NC}"
    echo -e "   https://www.ssllabs.com/ssltest/analyze.html?d=$DOMAIN"
    echo ""
}

# Main setup flow
main() {
    COMMAND=${1:-init}

    case "$COMMAND" in
        init)
            check_prerequisites
            echo ""
            validate_domain
            echo ""
            request_certificate
            echo ""
            setup_autorenewal
            echo ""
            reload_nginx
            echo ""
            verify_ssl
            show_summary
            ;;

        wildcard)
            check_prerequisites
            echo ""
            request_wildcard
            echo ""
            reload_nginx
            echo ""
            show_summary
            ;;

        renew)
            echo -e "${BLUE}🔄 Forcing certificate renewal...${NC}"
            docker run --rm \
                -v certbot_conf:/etc/letsencrypt \
                -v certbot_www:/var/www/certbot \
                certbot/certbot renew --force-renewal
            reload_nginx
            echo -e "${GREEN}✅ Certificate renewed${NC}"
            ;;

        test)
            test_renewal
            ;;

        info)
            show_certificate_info
            ;;

        revoke)
            echo -e "${RED}⚠️  Revoking certificate for $DOMAIN${NC}"
            read -p "Are you sure? (yes/no): " confirm
            if [ "$confirm" = "yes" ]; then
                docker run --rm \
                    -v certbot_conf:/etc/letsencrypt \
                    -v certbot_www:/var/www/certbot \
                    certbot/certbot revoke \
                    --cert-path "/etc/letsencrypt/live/$DOMAIN/fullchain.pem"
                echo -e "${GREEN}✅ Certificate revoked${NC}"
            fi
            ;;

        help|-h|--help)
            echo "Usage: $0 [command]"
            echo ""
            echo "Commands:"
            echo "  init       - Initial SSL setup (default)"
            echo "  wildcard   - Request wildcard certificate (*.$DOMAIN)"
            echo "  renew      - Force certificate renewal"
            echo "  test       - Test certificate renewal (dry-run)"
            echo "  info       - Show certificate information"
            echo "  revoke     - Revoke certificate"
            echo "  help       - Show this help"
            echo ""
            echo "Environment Variables:"
            echo "  DOMAIN               - Domain name (default: ablage-system.local)"
            echo "  LETSENCRYPT_EMAIL    - Email for Let's Encrypt"
            echo "  STAGING              - Use staging server (true/false)"
            ;;

        *)
            echo -e "${RED}❌ Unknown command: $COMMAND${NC}"
            echo "Run '$0 help' for usage"
            exit 1
            ;;
    esac
}

# Run main function
main "$@"
