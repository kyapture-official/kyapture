# C:\Users\LENOVO\Desktop\kyapture\backend\config\settings\production.py

from .base import *
import os
from django.core.exceptions import ImproperlyConfigured

# Strict Safety Guard: Guarantee DEBUG is NEVER True in production
DEBUG = False


# ─── ENFORCE A REAL SECRET_KEY (Fail Loudly, Don't Silently Degrade) ────────
# base.py falls back to "django-insecure-change-this-in-production" whenever
# SECRET_KEY isn't set. That's convenient for local dev, but the exact same
# string is printed by every `django-admin startproject` scaffold and copied
# into countless public tutorials/repos — it provides zero real secrecy.
# Anyone who recognizes it can forge session data, password-reset tokens,
# and any other value Django signs with SECRET_KEY.
#
# Checked against the raw env var (not settings.SECRET_KEY) so this also
# catches someone accidentally pasting the insecure placeholder itself into
# their prod env — os.getenv's default only covers "var is absent," but the
# string is public either way, so an exact match is rejected too.
_secret_key = os.getenv("SECRET_KEY")
_insecure_default = "django-insecure-change-this-in-production"

if not _secret_key or _secret_key == _insecure_default:
    raise ImproperlyConfigured(
        "Production requires a real SECRET_KEY, but the environment variable "
        "is missing, empty, or still set to base.py's insecure placeholder "
        "default. Generate a unique secret — e.g. "
        "`python -c \"import secrets; print(secrets.token_urlsafe(64))\"` — "
        "and set it as SECRET_KEY in your production environment (deployment "
        "secrets, not backend/.env) before starting this service."
    )


# ─── ENFORCE S3 MEDIA STORAGE (Fail Loudly, Don't Silently Degrade) ─────────
# base.py's STORAGES block falls back to FileSystemStorage whenever any of
# the three AWS_* vars below is missing — that's the right behavior in dev,
# but catastrophic in prod: on an ephemeral/containerized host, local-disk
# uploads vanish on the next redeploy or restart, silently destroying every
# client's photos with no error anywhere in the logs.
#
# We check the raw env vars directly (not the STORAGES dict base.py already
# built) so this fails at import time, before Django even finishes loading
# settings — the app should refuse to boot rather than come up "successfully"
# and start accepting uploads onto a disk that won't survive a restart.
_required_s3_vars = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_STORAGE_BUCKET_NAME")
_missing_s3_vars = [name for name in _required_s3_vars if not os.getenv(name)]

if _missing_s3_vars:
    raise ImproperlyConfigured(
        "Production requires S3 media storage, but the following required "
        f"environment variable(s) are missing or empty: {', '.join(_missing_s3_vars)}. "
        "Refusing to start rather than silently falling back to local disk "
        "storage (uploaded client photos would be lost on the next deploy/restart). "
        "Set these in your production environment (e.g. deployment secrets, "
        "not just backend/.env) before starting this service."
    )



# ─── ENFORCE REAL TRANSACTIONAL EMAIL DELIVERY (Fail Loudly) — C-10 fix ─────
# Same failure mode as the S3 guard above, same fix. Without a verified
# sender identity, PasswordResetRequestView would keep "succeeding" (still
# return its generic 200) while every reset link silently went nowhere —
# every user who forgets their password would be permanently locked out
# with no error surfacing anywhere. Refuse to boot instead of shipping that.
_required_email_vars = ("DEFAULT_FROM_EMAIL",)
_missing_email_vars = [name for name in _required_email_vars if not os.getenv(name)]

if _missing_email_vars:
    raise ImproperlyConfigured(
        "Production requires a verified outgoing sender identity, but the "
        f"following required environment variable(s) are missing or empty: {', '.join(_missing_email_vars)}. "
        "Set DEFAULT_FROM_EMAIL to an address or domain you have verified "
        "in AWS SES (and requested production access for — new SES accounts "
        "start in sandbox mode and can only mail verified addresses) before "
        "starting this service."
    )

if "django_ses" not in INSTALLED_APPS:
    INSTALLED_APPS.append("django_ses")

# Routes django.core.mail.send_mail() — used today by PasswordResetRequestView,
# and by anything transactional you add later — through Amazon SES instead of
# development.py's console backend. Reuses the AWS_ACCESS_KEY_ID /
# AWS_SECRET_ACCESS_KEY already loaded above for S3; django-ses (like
# django-storages) reads those same Django settings, so there's no second
# credential pair to manage.
EMAIL_BACKEND = "django_ses.SESBackend"

# SES isn't available in every AWS region and has no requirement to share a
# region with the S3 media bucket. Defaults to the bucket's region if you
# haven't pointed it somewhere else explicitly.
AWS_SES_REGION_NAME = os.getenv("AWS_SES_REGION_NAME", AWS_S3_REGION_NAME)
AWS_SES_REGION_ENDPOINT = os.getenv(
    "AWS_SES_REGION_ENDPOINT", f"email.{AWS_SES_REGION_NAME}.amazonaws.com"
)

# Overrides base.py's http://localhost:5173 default. This is what actually
# gets stitched into the link mailed out by PasswordResetRequestView — get
# it wrong and SES will happily, successfully deliver an email containing a
# dead link, with no error anywhere to tell you that happened.
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://app.kyapture.com").rstrip("/")



# ─── 1. HOST & CORS DOMAIN WHITELISTING ──────────────────────────────────────

# Load allowed hosts from env (e.g. ALLOWED_HOSTS=api.kyapture.com,app.kyapture.com)
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "").split(",")
if not ALLOWED_HOSTS or ALLOWED_HOSTS == [""]:
    # Fallback safe wildcard for tenant subdomains (e.g. .kyapture.com matches all subdomains)
    ALLOWED_HOSTS = [".kyapture.com"]

# Load allowed CORS origins from env
CORS_ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
if not CORS_ALLOWED_ORIGINS or CORS_ALLOWED_ORIGINS == [""]:
    CORS_ALLOWED_ORIGINS = [
        "https://app.kyapture.com",
        "https://kyapture.com",
    ]

# ─── 2. WHITENOISE STATIC FILE SERVING ───────────────────────────────────────

# Dynamically inject WhiteNoise middleware directly below Django's SecurityMiddleware
if "whitenoise.middleware.WhiteNoiseMiddleware" not in MIDDLEWARE:
    try:
        security_index = MIDDLEWARE.index("django.middleware.security.SecurityMiddleware")
        MIDDLEWARE.insert(security_index + 1, "whitenoise.middleware.WhiteNoiseMiddleware")
    except ValueError:
        MIDDLEWARE.insert(0, "whitenoise.middleware.WhiteNoiseMiddleware")

STORAGES["staticfiles"] = {
    "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
}

# ─── 3. CRYPTOGRAPHIC COOKIE & HTTPS SECURITY ────────────────────────────────

# Force Access and Refresh HttpOnly cookies to ONLY be transmitted over encrypted HTTPS
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Enforce secure cookie flags globally across subdomains
SESSION_COOKIE_DOMAIN = os.getenv("SESSION_COOKIE_DOMAIN", ".kyapture.com")

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