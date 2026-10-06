# C:/Users/LENOVO/Desktop/kyapture/frontend/Dockerfile
# Build stage
FROM node:20-alpine AS builder
WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
# The API base URL is baked into the bundle at build time, so it is an explicit
# build input (passed by docker-compose.yml for local dev, by the deploy
# pipeline for production) rather than whatever .env file is in the context.
# Left unset, the app falls back to the relative '/api/v1'.
ARG VITE_API_BASE_URL
# The one build-time app version, sent with every feedback submit (src/utils/appVersion.js).
# It must equal the backend's APP_VERSION (or be in FEEDBACK_ACCEPTED_APP_VERSIONS), else the
# server stores 'unknown'. Unset = 'dev', which is also the backend default.
ARG VITE_APP_VERSION
RUN npm run build

# Runtime stage
FROM nginx:1.27-alpine
COPY --from=builder /app/dist /usr/share/nginx/html
# Replaces the stock default.conf with our own SPA-fallback config, so a
# refresh on a deep client-side route (e.g. /dashboard/galleries) serves
# index.html instead of 404ing. See nginx.conf's own header comment.
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
