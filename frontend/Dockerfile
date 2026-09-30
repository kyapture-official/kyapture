# C:/Users/LENOVO/Desktop/kyapture/frontend/Dockerfile
# Build stage
FROM node:20-alpine AS builder
WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
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
