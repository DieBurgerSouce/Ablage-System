# Stage 1: Build
# Pin base image digest for reproducible builds
# Update digest via: docker manifest inspect node:22.12-alpine3.21
FROM node:22.12-alpine3.21@sha256:513c40ed37f6a5b7200de0a9a18e963d8c049c0427bbc9e4fc5cd16ef8881114 AS builder

WORKDIR /app

COPY package.json package-lock.json ./
# --legacy-peer-deps: react-split-pane@0.1.92 ist noch nicht mit React 19 kompatibel
# npm install statt npm ci fuer flexibleres Dependency-Management
# Use npm ci for deterministic installs; --legacy-peer-deps needed for react-split-pane
RUN npm ci --legacy-peer-deps

COPY . .
RUN npm run build

# Stage 2: Production
# Pin base image digest for reproducible builds
# Update digest via: docker manifest inspect nginx:1.27-alpine3.20
FROM nginx:1.27-alpine3.20@sha256:814a8e88df978ade80e584cc5b333144b9372a8e3c98872d07137dbf3b44d0e4 AS production

# Copy nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf

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
