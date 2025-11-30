#!/bin/bash
# Patroni Docker Entrypoint
# Ersetzt Umgebungsvariablen in der Konfiguration und startet Patroni

set -e

# Konfigurationsdatei mit Umgebungsvariablen erstellen
PATRONI_CONFIG="/etc/patroni/patroni.yml"
PATRONI_CONFIG_RUNTIME="/tmp/patroni.yml"

echo "=== Ablage-System PostgreSQL HA Node ==="
echo "Node: ${PATRONI_NAME:-pg-node1}"
echo "Cluster: ablage-cluster"
echo ""

# Warte auf etcd Cluster
echo "Warte auf etcd Cluster..."
ETCD_HOSTS="etcd1:2379 etcd2:2379 etcd3:2379"
ETCD_READY=false

for i in {1..60}; do
    for host in $ETCD_HOSTS; do
        if curl -sf "http://${host}/health" > /dev/null 2>&1; then
            echo "etcd erreichbar: ${host}"
            ETCD_READY=true
            break 2
        fi
    done
    echo "Warte auf etcd... (${i}/60)"
    sleep 2
done

if [ "$ETCD_READY" != "true" ]; then
    echo "FEHLER: etcd Cluster nicht erreichbar!"
    exit 1
fi

# Umgebungsvariablen in Konfiguration ersetzen
echo "Erstelle Patroni-Konfiguration..."
envsubst < "$PATRONI_CONFIG" > "$PATRONI_CONFIG_RUNTIME"

# Konfiguration validieren
echo "Validiere Konfiguration..."
if ! python3 -c "import yaml; yaml.safe_load(open('$PATRONI_CONFIG_RUNTIME'))"; then
    echo "FEHLER: Ungueltige YAML-Konfiguration!"
    exit 1
fi

echo "Konfiguration erstellt: $PATRONI_CONFIG_RUNTIME"
echo ""
echo "Starte Patroni..."
echo "=========================================="

# Patroni starten
exec "$@"
