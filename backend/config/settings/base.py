import os
from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv

# Resolves to the root of your project: C:\Users\LENOVO\Desktop\kyapture
BASE_DIR = Path(__file__).resolve().parents[3]

# Loads environment variables from backend/.env
load_dotenv(BASE_DIR / "backend" / ".env")

# SECRET_KEY is loaded from environment variables in production, with a fallback for local safety
SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-change-this-in-production")

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    
    # Third-Party Packages
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist", 
    "corsheaders",

    "apps.core",          # Core holds abstract models, custom permissions, and global exceptions
    "apps.users",         # Photographer Custom User & Authentication logic
    "apps.clients",       # Public gallery views and download logging
    "apps.galleries",     # Gallery metadata management
    "apps.photos",        # Photo storage and processing
    "apps.subscriptions", # Billing, plans, and payments
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",  # Must be placed at the top of middleware stack
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# REST Framework Configuration (Versioned globally)
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}

# SimpleJWT Configuration for scale-safe session management
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),   # Short-lived for security
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),      # Long-lived for persistence
    "ROTATE_REFRESH_TOKENS": True,                    # Issues new refresh token on every refresh
    "BLACKLIST_AFTER_ROTATION": True,                 # Revokes old refresh token instantly
    # Explicit Defaults (For developer readability)
    "ALGORITHM": "HS256",
    "AUTH_HEADER_TYPES": ("Bearer",),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

# Core Auth and I18N configuration
AUTH_USER_MODEL = "users.User"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Media files (Uploaded assets like photographer avatars and receipts)
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "backend" / "media"

# Static files (Django Admin panel CSS, JavaScript, and Icons)
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "backend" / "staticfiles"