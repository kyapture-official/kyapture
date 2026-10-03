# C:/Users/LENOVO/Desktop/kyapture/backend/Dockerfile
# backend/Dockerfile

FROM python:3.12-slim

# Set strict Python environment parameters
# - PYTHONDONTWRITEBYTECODE=1: Prevents Python from writing .pyc caching files inside the container
# - PYTHONUNBUFFERED=1: Forces stdout and stderr streams to write immediately to logs (prevents lost logs on crash)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies (FFmpeg is required for video processing pipeline)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# ─── BUILD-TIME-ONLY PLACEHOLDER ENV (collectstatic, nothing else) ─────────
# config/settings/production.py fails loudly (by design — see its own
# comments) if SECRET_KEY, the AWS_* trio, DEFAULT_FROM_EMAIL, or the DB_*
# vars are missing, because a real deployment must never silently boot
# without them. But `collectstatic` below only needs Django's settings
# module to import successfully — it never touches the database, S3, or
# SES — so it doesn't need real values, just non-empty ones to satisfy
# those guards during the image build.
#
# These ENV defaults are baked into the image, but Docker ENV values are
# only *defaults*: any real deployment already supplies its own
# SECRET_KEY/DB_*/AWS_*/DEFAULT_FROM_EMAIL at container start (compose
# `env_file`, `docker run -e`, or the orchestrator's secret injection) and
# those runtime values override what's set here. Nothing below this line
# is a credential — don't remove the guards in production.py to avoid
# needing this; that would defeat the point of the fail-loud checks.
ARG BUILD_SECRET_KEY=build-time-placeholder
ARG BUILD_AWS_ACCESS_KEY_ID=build-time-placeholder
ARG BUILD_AWS_SECRET_ACCESS_KEY=build-time-placeholder
ARG BUILD_AWS_STORAGE_BUCKET_NAME=build-time-placeholder
ARG BUILD_DEFAULT_FROM_EMAIL=build-time-placeholder@example.com
ARG BUILD_DB_NAME=build-time-placeholder
ARG BUILD_DB_USER=build-time-placeholder
ARG BUILD_DB_PASSWORD=build-time-placeholder
ARG BUILD_DB_HOST=build-time-placeholder

# Pre-compile and collect static assets during the image build phase.
# This compiles, compresses, and generates cache-busting hashes for WhiteNoise static serving.
RUN SECRET_KEY="$BUILD_SECRET_KEY" \
    AWS_ACCESS_KEY_ID="$BUILD_AWS_ACCESS_KEY_ID" \
    AWS_SECRET_ACCESS_KEY="$BUILD_AWS_SECRET_ACCESS_KEY" \
    AWS_STORAGE_BUCKET_NAME="$BUILD_AWS_STORAGE_BUCKET_NAME" \
    DEFAULT_FROM_EMAIL="$BUILD_DEFAULT_FROM_EMAIL" \
    DB_NAME="$BUILD_DB_NAME" \
    DB_USER="$BUILD_DB_USER" \
    DB_PASSWORD="$BUILD_DB_PASSWORD" \
    DB_HOST="$BUILD_DB_HOST" \
    python manage.py collectstatic --noinput --settings=config.settings.production

RUN chmod +x docker-entrypoint.py

# Instruct Docker to expose port 8000 programmatically
EXPOSE 8000

# Shared by every process this image runs (gunicorn here, and the Celery
# worker/beat services in docker-compose.yml, which build this same image
# and only override CMD below, never ENTRYPOINT) — guarantees
# "database available -> migrations applied -> CMD starts" for all of
# them. See docker-entrypoint.py's own docstring for the full rationale
# (this is the fix for the Phase 3 migration-drift production incident).
ENTRYPOINT ["python", "docker-entrypoint.py"]

# Execute Gunicorn in production mode with 3 concurrent worker processes
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
