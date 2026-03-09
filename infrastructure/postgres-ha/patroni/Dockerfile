# Patroni PostgreSQL 16 HA Node
# Ablage-System - Enterprise-grade Database Clustering
#
# Basiert auf PostgreSQL 16 mit Patroni 3.x fuer automatisches Failover

# Pin base image digest for reproducible builds
# Update digest via: docker manifest inspect postgres:16-bookworm
FROM postgres:16-bookworm

LABEL maintainer="Ablage-System Team"
LABEL description="PostgreSQL 16 with Patroni for High Availability"
LABEL version="1.0"

# Umgebungsvariablen
ENV PATRONI_VERSION=3.2.2
ENV DEBIAN_FRONTEND=noninteractive

# System-Pakete installieren
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-psycopg2 \
    python3-yaml \
    python3-requests \
    python3-urllib3 \
    python3-certifi \
    python3-dateutil \
    python3-tz \
    curl \
    jq \
    netcat-openbsd \
    locales \
    && rm -rf /var/lib/apt/lists/*

# Deutsche Locale konfigurieren
RUN sed -i '/de_DE.UTF-8/s/^# //g' /etc/locale.gen && \
    locale-gen de_DE.UTF-8
ENV LANG=de_DE.UTF-8
ENV LC_ALL=de_DE.UTF-8

# Patroni installieren
RUN pip3 install --no-cache-dir --break-system-packages \
    patroni[etcd3]==${PATRONI_VERSION} \
    psycopg2-binary \
    python-etcd

# Patroni-Konfiguration kopieren
COPY patroni.yml /etc/patroni/patroni.yml

# Patroni-Verzeichnisse erstellen
RUN mkdir -p /var/lib/postgresql/data /var/run/postgresql /etc/patroni && \
    chown -R postgres:postgres /var/lib/postgresql /var/run/postgresql /etc/patroni && \
    chmod 700 /var/lib/postgresql/data

# Entrypoint-Script
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# PostgreSQL-Datenverzeichnis
VOLUME /var/lib/postgresql/data

# Ports: PostgreSQL (5432), Patroni REST API (8008)
EXPOSE 5432 8008

# Als postgres-User ausfuehren
USER postgres

# Health Check
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -sf http://localhost:8008/health || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["patroni", "/etc/patroni/patroni.yml"]
