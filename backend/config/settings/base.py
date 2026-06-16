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
    
    "EXCEPTION_HANDLER": "apps.core.exceptions.custom_exception_handler",
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


# AWS S3 STATIC & MEDIA STORAGE (Self-Healing Hybrid Setup)


# Load S3 credentials dynamically from your backend/.env file
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_STORAGE_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME")
AWS_S3_REGION_NAME = os.getenv("AWS_S3_REGION_NAME", "us-east-1")

if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY and AWS_STORAGE_BUCKET_NAME:
    # 1. AWS Credentials are present: Activate Cloud Storage
    if "storages" not in INSTALLED_APPS:
        INSTALLED_APPS.append("storages")
    
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
            "OPTIONS": {
                "bucket_name": AWS_STORAGE_BUCKET_NAME,
                "region_name": AWS_S3_REGION_NAME,
                "default_acl": "private",     # Enforces that raw downloads require pre-signed URLs
                "querystring_auth": True,     # Enables automatic generation of pre-signed expiry signatures
                "querystring_expire": 3600,    # URLs automatically expire in 1 hour (Security standard)
                "file_overwrite": False,       # Prevents files with duplicate names from overwriting each other
            },
        },
        "staticfiles": {
            # Keep admin static files local in development to avoid AWS overhead
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
else:
    # 2. No AWS Credentials found: Gracefully fall back to local disk storage
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }