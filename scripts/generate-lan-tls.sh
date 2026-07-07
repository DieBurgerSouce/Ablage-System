#!/bin/bash
# -*- coding: utf-8 -*-
#
# LAN-TLS-Zertifikatserzeugung (M-14, Phase 0 Betriebsreife)
#
# Erzeugt eine lokale Mini-CA (10 Jahre) und ein Server-Zertifikat
# (825 Tage, Browser-/Apple-Limit) fuer https://ablage.firmenich.lan.
#
# Usage:
#   ./scripts/generate-lan-tls.sh
#   LAN_IP=192.168.1.50 ./scripts/generate-lan-tls.sh
#   ./scripts/generate-lan-tls.sh --output infrastructure/nginx/ssl --lan-ip 192.168.1.50
#
# Ausgabe (Default: ./infrastructure/nginx/ssl — gitignored, nur .gitkeep im Repo):
#   ca.crt / ca.key          - lokale CA (ca.crt auf ALLEN LAN-Clients installieren!)
#   ablage.crt / ablage.key  - Server-Zertifikat + Key fuer nginx
#                              (/etc/nginx/ssl/ablage.crt|.key im Container)
#
# SANs im Server-Zertifikat:
#   DNS: <domain> (Default ablage.firmenich.lan), localhost
#   IP:  127.0.0.1 [+ optionale LAN-IP aus ENV LAN_IP oder --lan-ip]
#
# Idempotent: existierende Dateien werden NICHT ueberschrieben
# (--force erzwingt Neuerstellung des Server-Zertifikats; die CA bleibt
# bestehen, solange ca.key/ca.crt vorhanden sind).

set -euo pipefail

# Git-Bash/MSYS-Kompatibilitaet (Windows-Host): verhindert, dass openssl-
# Argumente wie -subj "/C=DE/..." als Windows-Pfade umgeschrieben werden.
# Unter Linux/Container wirkungslos.
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

# Farben
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Standardwerte
OUTPUT_DIR="${OUTPUT_DIR:-./infrastructure/nginx/ssl}"
DOMAIN="${DOMAIN:-ablage.firmenich.lan}"
LAN_IP="${LAN_IP:-}"
CA_DAYS=3650          # 10 Jahre
CERT_DAYS=825         # max. akzeptierte Laufzeit moderner Clients
CA_KEY_SIZE=4096
SERVER_KEY_SIZE=2048
ORG_NAME="Firmenich Ablage-System"
COUNTRY="DE"
FORCE=0

# Argument Parsing
while [[ $# -gt 0 ]]; do
    case $1 in
        --output|-o)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --domain|-d)
            DOMAIN="$2"
            shift 2
            ;;
        --lan-ip)
            LAN_IP="$2"
            shift 2
            ;;
        --force|-f)
            FORCE=1
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --output, -o DIR   Output-Verzeichnis (default: ./infrastructure/nginx/ssl)"
            echo "  --domain, -d NAME  Server-Domain (default: ablage.firmenich.lan)"
            echo "  --lan-ip IP        Zusaetzliche IP-SAN (alternativ ENV LAN_IP)"
            echo "  --force, -f        Server-Zertifikat neu erstellen (CA bleibt)"
            echo "  --help, -h         Diese Hilfe"
            exit 0
            ;;
        *)
            echo -e "${RED}Unbekannte Option: $1${NC}"
            exit 1
            ;;
    esac
done

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNUNG]${NC} $1"; }
log_error() { echo -e "${RED}[FEHLER]${NC} $1"; }

echo ""
echo "=============================================="
echo "  LAN-TLS-Zertifikat-Generator (M-14)"
echo "  Domain: ${DOMAIN}"
echo "=============================================="
echo ""

if ! command -v openssl >/dev/null 2>&1; then
    log_error "openssl nicht gefunden — bitte installieren."
    exit 1
fi

mkdir -p "$OUTPUT_DIR"
cd "$OUTPUT_DIR"

log_info "Output-Verzeichnis: $OUTPUT_DIR"

# ============================================================================
# 1) Lokale CA erstellen (wenn nicht vorhanden)
# ============================================================================

if [ ! -f "ca.key" ] || [ ! -f "ca.crt" ]; then
    log_info "Erstelle lokale CA (gueltig ${CA_DAYS} Tage) ..."

    openssl genrsa -out ca.key ${CA_KEY_SIZE} 2>/dev/null
    chmod 600 ca.key

    openssl req -x509 -new -nodes \
        -key ca.key \
        -sha256 \
        -days ${CA_DAYS} \
        -out ca.crt \
        -subj "/C=${COUNTRY}/O=${ORG_NAME}/CN=${ORG_NAME} LAN CA" \
        2>/dev/null

    log_success "Lokale CA erstellt (ca.crt / ca.key)"
else
    log_info "Lokale CA existiert bereits — wird wiederverwendet"
fi

# ============================================================================
# 2) Server-Zertifikat fuer ${DOMAIN} erstellen
# ============================================================================

if [ "$FORCE" = "1" ]; then
    log_warning "--force: bestehendes Server-Zertifikat wird ersetzt"
    rm -f ablage.crt ablage.key
fi

if [ ! -f "ablage.key" ] || [ ! -f "ablage.crt" ]; then
    log_info "Erstelle Server-Zertifikat fuer ${DOMAIN} (gueltig ${CERT_DAYS} Tage) ..."

    openssl genrsa -out ablage.key ${SERVER_KEY_SIZE} 2>/dev/null
    chmod 600 ablage.key

    openssl req -new \
        -key ablage.key \
        -out ablage.csr \
        -subj "/C=${COUNTRY}/O=${ORG_NAME}/CN=${DOMAIN}" \
        2>/dev/null

    # SAN-Extension (DNS + IPs); optionale LAN-IP aus ENV/Flag
    cat > server_ext.cnf << EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = ${DOMAIN}
DNS.2 = localhost
IP.1 = 127.0.0.1
EOF
    if [ -n "$LAN_IP" ]; then
        echo "IP.2 = ${LAN_IP}" >> server_ext.cnf
        log_info "Zusaetzliche IP-SAN: ${LAN_IP}"
    else
        log_info "Keine LAN_IP gesetzt — Zertifikat ohne LAN-IP-SAN (ENV LAN_IP=<ip> fuer Zugriff per IP)"
    fi

    openssl x509 -req \
        -in ablage.csr \
        -CA ca.crt \
        -CAkey ca.key \
        -CAcreateserial \
        -out ablage.crt \
        -days ${CERT_DAYS} \
        -sha256 \
        -extfile server_ext.cnf \
        2>/dev/null

    rm -f ablage.csr server_ext.cnf

    log_success "Server-Zertifikat erstellt (ablage.crt / ablage.key)"
else
    log_info "Server-Zertifikat existiert bereits (--force zum Neuerstellen)"
fi

# ============================================================================
# 3) Verifikation + Zusammenfassung
# ============================================================================

log_info "Verifiziere Zertifikatskette ..."
if openssl verify -CAfile ca.crt ablage.crt >/dev/null 2>&1; then
    log_success "Zertifikatskette gueltig (ablage.crt signiert von lokaler CA)"
else
    log_error "Zertifikatskette UNGUELTIG!"
    exit 1
fi

echo ""
log_info "Server-Zertifikat:"
openssl x509 -in ablage.crt -noout -subject -dates 2>/dev/null | sed 's/^/  /'
openssl x509 -in ablage.crt -noout -ext subjectAltName 2>/dev/null | sed 's/^/  /'

echo ""
log_success "LAN-TLS-Zertifikate erfolgreich erstellt!"
echo ""
echo "Naechste Schritte:"
echo "  1. ca.crt auf allen LAN-Clients als vertrauenswuerdige Stammzertifizierungs-"
echo "     stelle installieren (Windows: certmgr.msc; iOS/Android: Profil/Zertifikat)."
echo "  2. LAN-DNS einrichten: ${DOMAIN} -> Server-IP"
echo "     (Router-DNS oder hosts-Datei der Clients — Plan-Entscheidung E7)."
echo "  3. nginx neu starten, damit /etc/nginx/ssl/ablage.crt geladen wird:"
echo "     docker compose restart frontend   (bzw. den nginx-Service)"
echo ""
log_warning "ca.key sicher verwahren und NIEMALS committen (Verzeichnis ist gitignored)."
echo ""
