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


# ─── ENFORCE A REAL DATABASE CONNECTION (Fail Loudly, Don't Silently Degrade) ─
# base.py never defines DATABASES at all — only development.py does, scoped
# to local Postgres defaults via DB_NAME/DB_USER/DB_PASSWORD/DB_HOST/DB_PORT.
# Without an explicit block here, Django silently falls back to its own
# built-in default (settings.DATABASES == {}). That looks completely fine at
# import time — `manage.py check` even passes — and only blows up the first
# time any code path actually touches the ORM:
#   django.core.exceptions.ImproperlyConfigured: settings.DATABASES is
#   improperly configured. Please supply the ENGINE value.
# That's effectively every authenticated request, every public gallery view,
# and every Celery task (photo/video processing, the subscription-expiry
# sweep) — the entire application, not an edge case.
#
# Reuses the exact same DB_NAME/DB_USER/DB_PASSWORD/DB_HOST/DB_PORT env var
# names development.py already uses, so one .env/deployment-secret naming
# convention covers both environments — only the values differ per target.
_required_db_vars = ("DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST")
_missing_db_vars = [name for name in _required_db_vars if not os.getenv(name)]

if _missing_db_vars:
    raise ImproperlyConfigured(
        "Production requires a real PostgreSQL connection, but the following "
        f"required environment variable(s) are missing or empty: {', '.join(_missing_db_vars)}. "
        "Set these in your production environment (deployment secrets, not "
        "backend/.env) before starting this service."
    )

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME"),
        "USER": os.getenv("DB_USER"),
        "PASSWORD": os.getenv("DB_PASSWORD"),
        "HOST": os.getenv("DB_HOST"),
        "PORT": os.getenv("DB_PORT", "5432"),
        # Reuses a connection across requests within a worker process instead
        # of opening a fresh one every time (Django's own default is 0 — no
        # persistence). This is Django's built-in connection persistence,
        # not a PgBouncer/pooler replacement — tunable via env without a
        # code change once real traffic patterns are known.
        "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "60")),
    }
}


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



# ─── ENFORCE A SHARED CACHE (Fail Loudly) — 7-B, debt row 108 ───────────────
# Throttles and the PIN/password lockout count in the default cache. Without a
# shared one each gunicorn worker keeps its own counts, so every limit is
# silently multiplied by the number of workers. Redis is already required for
# Celery; point CACHE_REDIS_URL at its own database (e.g. redis://host:6379/2).
if not os.getenv("CACHE_REDIS_URL"):
    raise ImproperlyConfigured(
        "Production requires CACHE_REDIS_URL (a Redis database for the shared "
        "cache that throttles and lockouts count in). Without it each worker "
        "process would count on its own and every rate limit would be multiplied."
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
ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h.strip()]
if not ALLOWED_HOSTS:
    # Fallback safe wildcard for tenant subdomains (e.g. .kyapture.com matches all subdomains)
    ALLOWED_HOSTS = [".kyapture.com"]

# Load allowed CORS origins from env
# Spaces after the commas are tolerated (an unstripped " https://..." silently
# never matched any Origin).
CORS_ALLOWED_ORIGINS = [o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()]
if not CORS_ALLOWED_ORIGINS:
    CORS_ALLOWED_ORIGINS = [
        "https://app.kyapture.com",
        "https://kyapture.com",
    ]

# CSRF trusts these origins for the Origin-header check on unsafe requests
# (POST/PUT/PATCH/DELETE) made with the cookie-authenticated JWT flow —
# CookieJWTAuthentication.enforce_csrf() runs Django's real CSRFCheck on
# every unsafe request, and without CSRF_TRUSTED_ORIGINS set here, every one
# of those requests fails CSRF validation in production the moment the SPA
# and the API are reached via different origins (e.g. app.kyapture.com vs
# api.kyapture.com) — which is the deployment shape ALLOWED_HOSTS/
# CORS_ALLOWED_ORIGINS above are already set up for. Reuses the same env var
# convention as development.py so one .env-style list covers both.
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]
if not CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS = [
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

# CSRF cookie needs the same domain as the session cookie — without this it
# defaults to Django's own None (host-only), which is fine for a single-host
# deployment but breaks the moment the SPA (app.kyapture.com) and the API
# (api.kyapture.com) are split, matching the CORS/CSRF_TRUSTED_ORIGINS shape
# already assumed above.
CSRF_COOKIE_DOMAIN = os.getenv("CSRF_COOKIE_DOMAIN", SESSION_COOKIE_DOMAIN)

# Force SSL Redirect: Automatically redirect all unencrypted HTTP requests to HTTPS
SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "True") == "True"

# Tells Django to trust the X-Forwarded-Proto header set by the TLS-terminating
# reverse proxy (nginx / load balancer) in front of gunicorn. Without this,
# Django believes every request — even ones that reached the proxy over
# HTTPS — arrived over plain HTTP, because gunicorn itself only ever sees
# the proxy's internal HTTP connection. Two concrete failures this causes if
# left unset: SECURE_SSL_REDIRECT above can loop (Django "redirects" an
# already-HTTPS request to HTTPS again, proxy strips it back to HTTP, repeat),
# and request.build_absolute_uri() — used for cover/display/thumbnail URLs
# and the password-reset link — emits http:// links, which browsers then
# block or flag as mixed content on an https:// page.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Companion to the header above: makes Django trust X-Forwarded-Host too, so
# request.get_host() (also used by build_absolute_uri) reflects the host the
# browser actually requested rather than gunicorn's internal bind address.
USE_X_FORWARDED_HOST = True

# DRF's throttle IP detection walks the X-Forwarded-For chain; NUM_PROXIES
# tells it how many trusted hops sit in front of the app (nginx = 1) so it
# reads the address the proxy added instead of the proxy's own address (every
# visitor in one bucket) or a client-chosen value. DRF reads it ONLY from
# REST_FRAMEWORK: the top-level NUM_PROXIES that used to be here was ignored,
# leaving every anonymous throttle keyed on the raw client header (SEC-01,
# debt row 78). The proxy must append to (or overwrite) X-Forwarded-For;
# docs/KYAPTURE_UPLOAD_LIMITS.md has the nginx block. Adjust if a CDN/load
# balancer is added in front of nginx.
REST_FRAMEWORK = {**REST_FRAMEWORK, "NUM_PROXIES": int(os.getenv("NUM_PROXIES", "1"))}

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
