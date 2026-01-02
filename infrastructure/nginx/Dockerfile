# Nginx Dockerfile for Ablage-System OCR
# Production-ready reverse proxy

FROM nginx:1.25-alpine

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
# WICHTIG: Fuer Produktion muss .htpasswd VOR dem Build erstellt werden!
# Erstellen mit: docker run --rm httpd:alpine htpasswd -nb USERNAME PASSWORD > .htpasswd
COPY .htpasswd* /etc/nginx/
RUN if [ ! -f /etc/nginx/.htpasswd ]; then \
        echo "# Placeholder - ersetzen mit echtem htpasswd!" > /etc/nginx/.htpasswd && \
        echo "WARNUNG: Keine .htpasswd gefunden! Prometheus-Zugang ist UNSICHER!" >&2; \
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
