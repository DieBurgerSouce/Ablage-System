# Sprint 0 / G05 - Backend-Watchdog Sidecar
# Minimalistisches Image (~25 MB) mit docker-cli + bash + curl.
# Container ruft Watchdog-Script in Endlosschleife (--loop) auf.

FROM docker:24-cli

# Sicherheits- und Build-Argumente
ARG TARGETPLATFORM
LABEL maintainer="Ablage-System"
LABEL purpose="backend-watchdog-sidecar"
LABEL sprint="sprint-0-g05"

# bash + curl + tini (Init-System fuer saubere Signal-Behandlung)
RUN apk add --no-cache bash curl tini

WORKDIR /app

# Verzeichnisse fuer State + Logs (werden als Volume gemountet)
RUN mkdir -p /state /state/logs

# Default-ENV (im Compose ueberschreibbar)
ENV CONTAINER=ablage-backend \
    HEALTH_URL=http://backend:8000/health \
    HEALTH_TIMEOUT=15 \
    RESTART_THRESHOLD=3 \
    ESCALATE_THRESHOLD=5 \
    LOOP_INTERVAL=60 \
    STATE_FILE=/state/watchdog.state \
    LOG_DIR=/state/logs \
    SLACK_WEBHOOK_FILE=/app/slack-webhook.url \
    SIDECAR_MODE=true

# Healthcheck: pruefe dass das Script-File existiert und State-File schreibbar ist
HEALTHCHECK --interval=2m --timeout=10s --start-period=10s --retries=3 \
    CMD test -f /app/backend_watchdog.sh && test -w /state || exit 1

# Tini als PID 1 fuer saubere Signal-Behandlung (SIGTERM -> shutdown loop)
ENTRYPOINT ["/sbin/tini", "--"]

# Watchdog-Script in Endlosschleife
CMD ["bash", "/app/backend_watchdog.sh", "loop"]
