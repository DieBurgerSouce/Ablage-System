# Nginx Dockerfile for Ablage-System OCR
# Production-ready reverse proxy

# Pin base image digest for reproducible builds
# Update digest via: docker manifest inspect nginx:1.25-alpine
FROM nginx:1.25-alpine@sha256:721fa00bc549df26b3e67cc558ff176112d4ba69847537766f3c28e171d180e7

# Install dependencies
RUN apk add --no-cache \
    apache2-utils \
    openssl \
    curl

# Copy configuration
COPY nginx.conf /etc/nginx/nginx.conf
COPY conf.d/ /etc/nginx/conf.d/
COPY snippets/ /etc/nginx/snippets/

# Copy htpasswd if it exists, otherwise create a placeholder
# KRITISCH: Fuer Produktion muss .htpasswd VOR dem Build erstellt werden!
# Erstellen mit: docker run --rm httpd:alpine htpasswd -nb prometheus_admin PASSWORT > .htpasswd
#
# SECURITY FIX: Strikte Validierung - Placeholder wird erkannt und gewarnt
COPY .htpasswd* /etc/nginx/
RUN if [ ! -f /etc/nginx/.htpasswd ]; then \
        echo "# WARNUNG: Placeholder - Prometheus ohne Auth!" > /etc/nginx/.htpasswd && \
        echo "" >&2 && \
        echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" >&2 && \
        echo "! SICHERHEITSWARNUNG: Keine .htpasswd Datei gefunden! !" >&2 && \
        echo "! Prometheus ist OHNE AUTHENTIFIZIERUNG zugaenglich!  !" >&2 && \
        echo "!                                                     !" >&2 && \
        echo "! Erstellen Sie eine .htpasswd:                       !" >&2 && \
        echo "! docker run --rm httpd:alpine htpasswd -nb \\         !" >&2 && \
        echo "!   prometheus_admin SICHERES_PASSWORT > .htpasswd    !" >&2 && \
        echo "!                                                     !" >&2 && \
        echo "! Siehe: infrastructure/nginx/.htpasswd.example       !" >&2 && \
        echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" >&2 && \
        echo "" >&2; \
    elif grep -q "Placeholder\|WARNUNG\|example" /etc/nginx/.htpasswd 2>/dev/null; then \
        echo "" >&2 && \
        echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" >&2 && \
        echo "! SICHERHEITSWARNUNG: .htpasswd ist nur ein Placeholder!!" >&2 && \
        echo "! Ersetzen Sie es durch eine echte htpasswd-Datei!    !" >&2 && \
        echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" >&2 && \
        echo "" >&2; \
    else \
        echo "OK: .htpasswd gefunden und scheint valide zu sein." >&2; \
    fi

# Generate DH parameters (2048 bit for faster build, use 4096 for production)
# HINWEIS: 4096-bit DH-Parameter sind sicherer, benoetigen aber ~5min zum Generieren.
# Fuer Produktion: openssl dhparam -out dhparam.pem 4096 (lokal) und COPY verwenden.
ARG DH_PARAM_BITS=2048
RUN openssl dhparam -out /etc/nginx/dhparam.pem ${DH_PARAM_BITS}

# Create directories
RUN mkdir -p /var/www/certbot \
    && mkdir -p /var/www/ablage-system \
    && mkdir -p /var/log/nginx

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost/health || exit 1

# Expose ports
EXPOSE 80 443

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
