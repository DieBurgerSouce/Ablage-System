#!/bin/bash
# -*- coding: utf-8 -*-
#
# mTLS Certificate Generation Script
#
# Erstellt CA und Client-Zertifikate fuer Inter-Service mTLS.
#
# Usage:
#   ./scripts/generate-mtls-certs.sh
#   ./scripts/generate-mtls-certs.sh --client worker
#   ./scripts/generate-mtls-certs.sh --output /etc/nginx/certs
#
# Generiert:
#   - CA Zertifikat (ca.crt, ca.key)
#   - Server Zertifikat (server.crt, server.key)
#   - Client Zertifikate (client-<name>.crt, client-<name>.key)

set -e

# Farben
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Standardwerte
OUTPUT_DIR="${OUTPUT_DIR:-./infrastructure/nginx/certs}"
CA_DAYS=3650  # 10 Jahre
CERT_DAYS=365  # 1 Jahr
KEY_SIZE=4096
CLIENT_KEY_SIZE=2048
CLIENT_NAME=""
ORG_NAME="Ablage-System"
COUNTRY="DE"

# Argument Parsing
while [[ $# -gt 0 ]]; do
    case $1 in
        --output|-o)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --client|-c)
            CLIENT_NAME="$2"
            shift 2
            ;;
        --ca-days)
            CA_DAYS="$2"
            shift 2
            ;;
        --cert-days)
            CERT_DAYS="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --output, -o DIR    Output-Verzeichnis (default: ./infrastructure/nginx/certs)"
            echo "  --client, -c NAME   Client-Zertifikat erstellen"
            echo "  --ca-days DAYS      CA Gueltigkeit (default: 3650)"
            echo "  --cert-days DAYS    Zertifikat Gueltigkeit (default: 365)"
            echo "  --help, -h          Diese Hilfe"
            exit 0
            ;;
        *)
            echo -e "${RED}Unbekannte Option: $1${NC}"
            exit 1
            ;;
    esac
done

# Hilfsfunktionen
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNUNG]${NC} $1"; }
log_error() { echo -e "${RED}[FEHLER]${NC} $1"; }

# Header
echo ""
echo "=============================================="
echo "  mTLS Zertifikat-Generator"
echo "=============================================="
echo ""

# Verzeichnis erstellen
mkdir -p "$OUTPUT_DIR"
cd "$OUTPUT_DIR"

log_info "Output-Verzeichnis: $OUTPUT_DIR"

# ============================================================================
# CA Zertifikat erstellen (wenn nicht vorhanden)
# ============================================================================

if [ ! -f "ca.key" ] || [ ! -f "ca.crt" ]; then
    log_info "Erstelle CA Zertifikat..."

    # CA Private Key
    openssl genrsa -out ca.key $KEY_SIZE 2>/dev/null
    chmod 600 ca.key

    # CA Certificate
    openssl req -x509 -new -nodes \
        -key ca.key \
        -sha256 \
        -days $CA_DAYS \
        -out ca.crt \
        -subj "/C=$COUNTRY/O=$ORG_NAME/CN=$ORG_NAME Internal CA" \
        2>/dev/null

    log_success "CA Zertifikat erstellt (gueltig fuer $CA_DAYS Tage)"
else
    log_info "CA Zertifikat existiert bereits"
fi

# ============================================================================
# Server Zertifikat erstellen (wenn nicht vorhanden)
# ============================================================================

if [ ! -f "server.key" ] || [ ! -f "server.crt" ]; then
    log_info "Erstelle Server Zertifikat..."

    # Server Private Key
    openssl genrsa -out server.key $CLIENT_KEY_SIZE 2>/dev/null
    chmod 600 server.key

    # Server CSR
    openssl req -new \
        -key server.key \
        -out server.csr \
        -subj "/C=$COUNTRY/O=$ORG_NAME/CN=ablage-server" \
        2>/dev/null

    # Server Certificate mit SAN (Subject Alternative Names)
    cat > server_ext.cnf << EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
DNS.2 = ablage-server
DNS.3 = ablage-backend
DNS.4 = *.ablage.local
IP.1 = 127.0.0.1
IP.2 = ::1
EOF

    openssl x509 -req \
        -in server.csr \
        -CA ca.crt \
        -CAkey ca.key \
        -CAcreateserial \
        -out server.crt \
        -days $CERT_DAYS \
        -sha256 \
        -extfile server_ext.cnf \
        2>/dev/null

    rm -f server.csr server_ext.cnf

    log_success "Server Zertifikat erstellt (gueltig fuer $CERT_DAYS Tage)"
else
    log_info "Server Zertifikat existiert bereits"
fi

# ============================================================================
# Client Zertifikat erstellen (wenn --client angegeben)
# ============================================================================

if [ -n "$CLIENT_NAME" ]; then
    CLIENT_KEY="client-${CLIENT_NAME}.key"
    CLIENT_CRT="client-${CLIENT_NAME}.crt"

    if [ ! -f "$CLIENT_KEY" ] || [ ! -f "$CLIENT_CRT" ]; then
        log_info "Erstelle Client Zertifikat fuer '$CLIENT_NAME'..."

        # Client Private Key
        openssl genrsa -out "$CLIENT_KEY" $CLIENT_KEY_SIZE 2>/dev/null
        chmod 600 "$CLIENT_KEY"

        # Client CSR
        openssl req -new \
            -key "$CLIENT_KEY" \
            -out "client-${CLIENT_NAME}.csr" \
            -subj "/C=$COUNTRY/O=$ORG_NAME/CN=ablage-$CLIENT_NAME" \
            2>/dev/null

        # Client Certificate
        cat > client_ext.cnf << EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage = digitalSignature
extendedKeyUsage = clientAuth
EOF

        openssl x509 -req \
            -in "client-${CLIENT_NAME}.csr" \
            -CA ca.crt \
            -CAkey ca.key \
            -CAcreateserial \
            -out "$CLIENT_CRT" \
            -days $CERT_DAYS \
            -sha256 \
            -extfile client_ext.cnf \
            2>/dev/null

        rm -f "client-${CLIENT_NAME}.csr" client_ext.cnf

        log_success "Client Zertifikat '$CLIENT_NAME' erstellt"

        # Verifizierung
        log_info "Verifiziere Client Zertifikat..."
        openssl verify -CAfile ca.crt "$CLIENT_CRT" 2>/dev/null && \
            log_success "Zertifikat gueltig" || \
            log_error "Zertifikat ungueltig!"
    else
        log_info "Client Zertifikat '$CLIENT_NAME' existiert bereits"
    fi
fi

# ============================================================================
# Standard-Clients erstellen (wenn keine spezifischen angegeben)
# ============================================================================

if [ -z "$CLIENT_NAME" ]; then
    log_info "Erstelle Standard-Client-Zertifikate..."

    STANDARD_CLIENTS="worker backend frontend admin"

    for client in $STANDARD_CLIENTS; do
        CLIENT_KEY="client-${client}.key"
        CLIENT_CRT="client-${client}.crt"

        if [ ! -f "$CLIENT_KEY" ] || [ ! -f "$CLIENT_CRT" ]; then
            log_info "  Erstelle Client '$client'..."

            openssl genrsa -out "$CLIENT_KEY" $CLIENT_KEY_SIZE 2>/dev/null
            chmod 600 "$CLIENT_KEY"

            openssl req -new \
                -key "$CLIENT_KEY" \
                -out "client-${client}.csr" \
                -subj "/C=$COUNTRY/O=$ORG_NAME/CN=ablage-$client" \
                2>/dev/null

            cat > client_ext.cnf << EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage = digitalSignature
extendedKeyUsage = clientAuth
EOF

            openssl x509 -req \
                -in "client-${client}.csr" \
                -CA ca.crt \
                -CAkey ca.key \
                -CAcreateserial \
                -out "$CLIENT_CRT" \
                -days $CERT_DAYS \
                -sha256 \
                -extfile client_ext.cnf \
                2>/dev/null

            rm -f "client-${client}.csr" client_ext.cnf

            log_success "  Client '$client' erstellt"
        fi
    done
fi

# ============================================================================
# DH Parameters erstellen (wenn nicht vorhanden)
# ============================================================================

if [ ! -f "dhparam.pem" ]; then
    log_info "Erstelle DH Parameters (kann einige Minuten dauern)..."
    openssl dhparam -out dhparam.pem 2048 2>/dev/null
    log_success "DH Parameters erstellt"
else
    log_info "DH Parameters existieren bereits"
fi

# ============================================================================
# Zusammenfassung
# ============================================================================

echo ""
echo "=============================================="
echo "  Zusammenfassung"
echo "=============================================="
echo ""

log_info "Erstellte Dateien:"
ls -la *.crt *.key *.pem 2>/dev/null | while read line; do
    echo "  $line"
done

echo ""
log_info "CA-Informationen:"
openssl x509 -in ca.crt -noout -subject -dates 2>/dev/null | sed 's/^/  /'

echo ""
log_info "Server-Zertifikat:"
openssl x509 -in server.crt -noout -subject -dates 2>/dev/null | sed 's/^/  /'

echo ""
log_success "Zertifikate erfolgreich erstellt!"
echo ""
echo "Naechste Schritte:"
echo "  1. CA-Zertifikat an Clients verteilen:"
echo "     cp $OUTPUT_DIR/ca.crt /path/to/client/"
echo ""
echo "  2. Nginx konfigurieren:"
echo "     include /etc/nginx/snippets/mtls.conf;"
echo ""
echo "  3. Client-Zertifikate fuer Services konfigurieren"
echo ""
