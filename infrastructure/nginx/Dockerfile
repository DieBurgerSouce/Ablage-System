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

# Generate DH parameters (4096 bit)
RUN openssl dhparam -out /etc/nginx/dhparam.pem 4096

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
