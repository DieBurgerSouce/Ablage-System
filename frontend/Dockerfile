# Stage 1: Build
# Pin base image digest for reproducible builds
# Update digest via: docker manifest inspect node:22.12-alpine3.21
FROM node:22.12-alpine3.21@sha256:513c40ed37f6a5b7200de0a9a18e963d8c049c0427bbc9e4fc5cd16ef8881114 AS builder

WORKDIR /app

COPY package.json package-lock.json ./
# --legacy-peer-deps: react-split-pane@0.1.92 ist noch nicht mit React 19 kompatibel
# npm install statt npm ci fuer flexibleres Dependency-Management
RUN npm install --legacy-peer-deps --no-audit

COPY . .
RUN npm run build

# Stage 2: Production
# Pin base image digest for reproducible builds
# Update digest via: docker manifest inspect nginx:1.27-alpine3.20
FROM nginx:1.27-alpine3.20@sha256:679a5fd058f6ca754a561846fe27927e408074431d63556e8fc588fc38be6901 AS production

# Copy nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf

# Copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html

# Environment variable substitution script
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 80

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
