# C:/Users/LENOVO/Desktop/kyapture/backend/config/settings/development.py
import os
from .base import *  # Import all shared base settings
# Explicitly override base configurations for local development safety
DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "photodelivery"),
        "USER": os.getenv("DB_USER", "photodelivery"),
        "PASSWORD": os.getenv("DB_PASSWORD", "photodelivery"),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
    }
}

# In local development, allow CORS requests from your React/Vite server
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",  # Standard Vite development port
    "http://127.0.0.1:5173",
    "http://localhost:3000",  # Compose nginx frontend
    "http://127.0.0.1:3000",
]

# CSRF trusts these origins for the Origin-header check on unsafe requests.
# Must include the scheme, and must be exact — no automatic localhost/127.0.0.1 equivalence.
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# ─── LOCAL DEVELOPMENT CELERY BYPASS ───────────────────────────────────────
# Forces Celery to run all background tasks synchronously inside the main thread
# by default, preserving the lightweight Windows workflow. Compose overrides
# these two settings to use the real Redis-backed worker for parity validation.
CELERY_TASK_ALWAYS_EAGER = os.getenv("CELERY_TASK_ALWAYS_EAGER", "true").lower() == "true"

# Propagates task exceptions directly to the Django console for easy debugging.
CELERY_TASK_EAGER_PROPAGATES = os.getenv("CELERY_TASK_EAGER_PROPAGATES", "true").lower() == "true"


# ─── LOCAL EMAIL: console backend (C-10) ───────────────────────────────────
# Prints every outgoing message — including the password-reset link — to
# the `runserver` terminal instead of hitting a real mail provider. This is
# the direct replacement for the old print(reset_url) stub in
# PasswordResetRequestView, except it now goes through Django's real
# django.core.mail API. That matters because it means the *view code*
# never has to know or care which backend is active: swapping console for
# django_ses.SESBackend in production.py is a settings-only change, zero
# lines differ in apps/users/views.py between environments.
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")

# docker-compose points the web/worker containers at its dev-only Mailpit
# catcher (SMTP :1025, inbox UI http://localhost:8025) so emails can be read.
# Nothing is delivered anywhere; production.py never reads these.
EMAIL_HOST = os.getenv("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "1025"))

# Download-ready email abuse limits (apps/clients/ready_email.py): loosened here
# so repeated local/QA downloads still produce an email. Production keeps the
# base.py defaults (5 / 10 / 30 per hour); env vars still win.
DOWNLOAD_READY_EMAIL_LIMIT_PER_EMAIL = int(os.getenv("DOWNLOAD_READY_EMAIL_LIMIT_PER_EMAIL", "50"))
DOWNLOAD_READY_EMAIL_LIMIT_PER_IP = int(os.getenv("DOWNLOAD_READY_EMAIL_LIMIT_PER_IP", "100"))
DOWNLOAD_READY_EMAIL_LIMIT_PER_GALLERY = int(os.getenv("DOWNLOAD_READY_EMAIL_LIMIT_PER_GALLERY", "300"))
