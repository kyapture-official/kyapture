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
ENV SECRET_KEY=build-time-placeholder-overridden-at-runtime \
    AWS_ACCESS_KEY_ID=build-time-placeholder \
    AWS_SECRET_ACCESS_KEY=build-time-placeholder \
    AWS_STORAGE_BUCKET_NAME=build-time-placeholder \
    DEFAULT_FROM_EMAIL=build-time-placeholder@example.com \
    DB_NAME=build-time-placeholder \
    DB_USER=build-time-placeholder \
    DB_PASSWORD=build-time-placeholder \
    DB_HOST=build-time-placeholder

# Pre-compile and collect static assets during the image build phase.
# This compiles, compresses, and generates cache-busting hashes for WhiteNoise static serving.
RUN python manage.py collectstatic --noinput --settings=config.settings.production

# Instruct Docker to expose port 8000 programmatically
EXPOSE 8000

# Execute Gunicorn in production mode with 3 concurrent worker processes
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
