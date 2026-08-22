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
]

# CSRF trusts these origins for the Origin-header check on unsafe requests.
# Must include the scheme, and must be exact — no automatic localhost/127.0.0.1 equivalence.
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# ─── LOCAL DEVELOPMENT CELERY BYPASS ───────────────────────────────────────
# Forces Celery to run all background tasks synchronously inside the main thread.
# This eliminates the requirement to have a Redis server running in development.
CELERY_TASK_ALWAYS_EAGER = True

# Propagates task exceptions directly to the Django console for easy debugging
CELERY_TASK_EAGER_PROPAGATES = True


# ─── LOCAL EMAIL: console backend (C-10) ───────────────────────────────────
# Prints every outgoing message — including the password-reset link — to
# the `runserver` terminal instead of hitting a real mail provider. This is
# the direct replacement for the old print(reset_url) stub in
# PasswordResetRequestView, except it now goes through Django's real
# django.core.mail API. That matters because it means the *view code*
# never has to know or care which backend is active: swapping console for
# django_ses.SESBackend in production.py is a settings-only change, zero
# lines differ in apps/users/views.py between environments.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"