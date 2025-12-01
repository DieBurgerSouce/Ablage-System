#!/bin/bash
# Vault TLS Certificate Generator
# Generiert selbstsignierte Zertifikate für Vault Development/Staging

set -e

CERT_DIR="$(dirname "$0")"
DAYS_VALID=365
KEY_SIZE=4096

# Farben für Output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== Vault TLS Certificate Generator ===${NC}"
echo ""

# Prüfe ob OpenSSL installiert ist
if ! command -v openssl &> /dev/null; then
    echo -e "${RED}Fehler: OpenSSL ist nicht installiert!${NC}"
    echo "Bitte installiere OpenSSL:"
    echo "  Ubuntu/Debian: sudo apt-get install openssl"
    echo "  macOS: brew install openssl"
    echo "  Windows: choco install openssl"
    exit 1
fi

cd "$CERT_DIR"

# CA Konfiguration
cat > ca.cnf << EOF
[req]
distinguished_name = req_distinguished_name
x509_extensions = v3_ca
prompt = no

[req_distinguished_name]
C = DE
ST = Berlin
L = Berlin
O = Ablage-System
OU = Infrastructure
CN = Ablage-System Root CA

[v3_ca]
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always,issuer
basicConstraints = critical, CA:true
keyUsage = critical, digitalSignature, cRLSign, keyCertSign
EOF

# Vault Server Konfiguration
cat > vault.cnf << EOF
[req]
distinguished_name = req_distinguished_name
req_extensions = v3_req
prompt = no

[req_distinguished_name]
C = DE
ST = Berlin
L = Berlin
O = Ablage-System
OU = Infrastructure
CN = vault

[v3_req]
basicConstraints = CA:FALSE
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth, clientAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = vault
DNS.2 = localhost
DNS.3 = ablage-vault
DNS.4 = *.ablage-system.local
IP.1 = 127.0.0.1
IP.2 = 0.0.0.0
EOF

echo -e "${GREEN}1. Generiere CA Private Key...${NC}"
openssl genrsa -out ca.key $KEY_SIZE 2>/dev/null

echo -e "${GREEN}2. Generiere CA Certificate...${NC}"
openssl req -x509 -new -nodes \
    -key ca.key \
    -sha256 \
    -days $DAYS_VALID \
    -out ca.crt \
    -config ca.cnf

echo -e "${GREEN}3. Generiere Vault Server Private Key...${NC}"
openssl genrsa -out vault.key $KEY_SIZE 2>/dev/null

echo -e "${GREEN}4. Generiere Vault Certificate Signing Request...${NC}"
openssl req -new \
    -key vault.key \
    -out vault.csr \
    -config vault.cnf

echo -e "${GREEN}5. Signiere Vault Certificate mit CA...${NC}"
openssl x509 -req \
    -in vault.csr \
    -CA ca.crt \
    -CAkey ca.key \
    -CAcreateserial \
    -out vault.crt \
    -days $DAYS_VALID \
    -sha256 \
    -extensions v3_req \
    -extfile vault.cnf

# Setze sichere Berechtigungen
chmod 600 ca.key vault.key
chmod 644 ca.crt vault.crt

# Aufräumen
rm -f ca.cnf vault.cnf vault.csr ca.srl 2>/dev/null || true

echo ""
echo -e "${GREEN}=== Zertifikate erfolgreich generiert! ===${NC}"
echo ""
echo "Generierte Dateien:"
echo "  - ca.crt      (CA Zertifikat - vertrauenswürdig markieren)"
echo "  - ca.key      (CA Private Key - SICHER AUFBEWAHREN!)"
echo "  - vault.crt   (Vault Server Zertifikat)"
echo "  - vault.key   (Vault Server Private Key)"
echo ""
echo -e "${YELLOW}WICHTIG für Production:${NC}"
echo "  1. Ersetze diese selbstsignierten Zertifikate durch CA-signierte"
echo "  2. Sichere ca.key an einem sicheren Ort"
echo "  3. Füge ca.crt zum Truststore der Clients hinzu"
echo ""
echo "Vault starten mit:"
echo "  docker-compose up -d vault"
echo ""
echo "Vault Status prüfen:"
echo "  VAULT_ADDR=https://localhost:8200 VAULT_CACERT=./ca.crt vault status"
