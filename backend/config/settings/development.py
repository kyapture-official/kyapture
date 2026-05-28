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