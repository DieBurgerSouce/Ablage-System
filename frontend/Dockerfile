# Stage 1: Build
FROM node:22.11-alpine3.20 AS builder

WORKDIR /app

COPY package.json package-lock.json ./
# SECURITY FIX: npm ci statt npm install --force für konsistente Builds
RUN npm ci --prefer-offline --no-audit

COPY . .
RUN npm run build

# Stage 2: Production
FROM nginx:1.27-alpine3.20 AS production

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
