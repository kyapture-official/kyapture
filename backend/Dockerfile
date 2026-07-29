# backend/Dockerfile

FROM python:3.12-slim

# Set strict Python environment parameters
# - PYTHONDONTWRITEBYTECODE=1: Prevents Python from writing .pyc caching files inside the container
# - PYTHONUNBUFFERED=1: Forces stdout and stderr streams to write immediately to logs (prevents lost logs on crash)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Pre-compile and collect static assets during the image build phase.
# This compiles, compresses, and generates cache-busting hashes for WhiteNoise static serving.
RUN python manage.py collectstatic --noinput --settings=config.settings.production

# Instruct Docker to expose port 8000 programmatically
EXPOSE 8000

# Execute Gunicorn in production mode with 3 concurrent worker processes
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]