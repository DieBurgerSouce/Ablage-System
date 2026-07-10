# Stage 1: Build
# Pin base image digest for reproducible builds
# Update digest via: docker manifest inspect node:22.12-alpine3.21
FROM node:25.2-alpine3.21@sha256:32509199057d74a987fdd88cde00fdfd48ef52469adbd6bd11969fc701477761 AS builder

WORKDIR /app

COPY package.json package-lock.json ./
# --legacy-peer-deps: react-split-pane@0.1.92 ist noch nicht mit React 19 kompatibel
# npm install statt npm ci fuer flexibleres Dependency-Management
# Use npm ci for deterministic installs; --legacy-peer-deps needed for react-split-pane
RUN npm ci --legacy-peer-deps

COPY . .
# build:strict erzwingt `tsc -b` vor dem Vite-Build (F-14): das Image baut nicht
# mehr mit TypeScript-Fehlern. Vorher lief hier `npm run build` (non-strict).
RUN npm run build:strict

# Stage 2: Production
# Pin base image digest for reproducible builds
# Update digest via: docker manifest inspect nginx:1.27-alpine3.20
FROM nginx:1.27-alpine3.20@sha256:679a5fd058f6ca754a561846fe27927e408074431d63556e8fc588fc38be6901 AS production

# Copy nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf

# Security-Header-Snippet: wird von nginx.conf per `include` im server-Block UND in jedem
# location-Block mit eigenem add_header eingebunden (sonst unterdrueckt nginx die CSP dort).
COPY nginx-security-headers.conf /etc/nginx/snippets/security-headers.conf

# Gemeinsamer Server-Body (:80 und :443) — die 443-Site aus /etc/nginx/ssl/*.conf
# (erzeugt von scripts/generate-lan-tls.sh) bindet dasselbe Snippet ein.
COPY nginx-server-common.conf /etc/nginx/snippets/server-common.conf

# Copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html

# Environment variable substitution script
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost/health || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
