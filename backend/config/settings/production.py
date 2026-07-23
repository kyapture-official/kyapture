# C:\Users\LENOVO\Desktop\kyapture\backend\config\settings\production.py

from .base import *
import os

# Strict Safety Guard: Guarantee DEBUG is NEVER True in production
DEBUG = False

# ─── 1. HOST & CORS DOMAIN WHITELISTING ──────────────────────────────────────

# Load allowed hosts from env (e.g. ALLOWED_HOSTS=api.kaypture.com,app.kaypture.com)
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "").split(",")
if not ALLOWED_HOSTS or ALLOWED_HOSTS == [""]:
    # Fallback safe wildcard for tenant subdomains (e.g. .kaypture.com matches all subdomains)
    ALLOWED_HOSTS = [".kaypture.com"]

# Load allowed CORS origins from env
CORS_ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
if not CORS_ALLOWED_ORIGINS or CORS_ALLOWED_ORIGINS == [""]:
    CORS_ALLOWED_ORIGINS = [
        "https://app.kaypture.com",
        "https://kaypture.com",
    ]

# ─── 2. WHITENOISE STATIC FILE SERVING ───────────────────────────────────────

# Dynamically inject WhiteNoise middleware directly below Django's SecurityMiddleware
if "whitenoise.middleware.WhiteNoiseMiddleware" not in MIDDLEWARE:
    try:
        security_index = MIDDLEWARE.index("django.middleware.security.SecurityMiddleware")
        MIDDLEWARE.insert(security_index + 1, "whitenoise.middleware.WhiteNoiseMiddleware")
    except ValueError:
        MIDDLEWARE.insert(0, "whitenoise.middleware.WhiteNoiseMiddleware")

# Compress and cache static files forever (cache-busting hashes automatically applied)
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"


# ─── 3. CRYPTOGRAPHIC COOKIE & HTTPS SECURITY ────────────────────────────────

# Force Access and Refresh HttpOnly cookies to ONLY be transmitted over encrypted HTTPS
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Enforce secure cookie flags globally across subdomains
SESSION_COOKIE_DOMAIN = os.getenv("SESSION_COOKIE_DOMAIN", ".kaypture.com")

# Force SSL Redirect: Automatically redirect all unencrypted HTTP requests to HTTPS
SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "True") == "True"

# HTTP Strict Transport Security (HSTS): Instructs browsers to ONLY communicate via HTTPS
SECURE_HSTS_SECONDS = 31536000  # 1 Year duration (security standard)
SECURE_HSTS_PRELOAD = True
SECURE_HSTS_INCLUDE_SUBDOMAINS = True

# Cross-Site Scripting (XSS) and Content-Type sniffing browser protections
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'  # Completely prevents clickjacking click hijacking


# ─── 4. AWS S3 STORAGE SECURE OVERRIDES ──────────────────────────────────────

# Override S3 signature version to use modern, secure AWS Signature Version 4
AWS_S3_SIGNATURE_VERSION = 's3v4'

# Generate S3 pre-signed URLs with dynamic query parameters
AWS_QUERYSTRING_AUTH = True
AWS_QUERYSTRING_EXPIRE = 3600  # Generated image/video links expire in 1 hour

# Enforce S3 secure connection parameters
AWS_S3_SECURE_URLS = True