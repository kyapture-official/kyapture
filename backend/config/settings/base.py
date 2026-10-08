#C:\Users\LENOVO\Desktop\kyapture\backend\config\settings\base.py
import os
import sys
from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv

# Resolves to the root of your project: C:\Users\LENOVO\Desktop\kyapture
BASE_DIR = Path(__file__).resolve().parents[3]

# Loads environment variables from backend/.env
load_dotenv(BASE_DIR / "backend" / ".env")

# SECRET_KEY is loaded from environment variables in production, with a fallback for local safety
SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-change-this-in-production")

# Key rotation (docs/security/secrets.md, "Rotating SECRET_KEY"): the previous
# key(s), comma-separated. Django still VERIFIES values signed with them
# (download/job/file links, password-reset links) while signing only with the
# new SECRET_KEY, so a rotation does not kill every emailed link at once.
SECRET_KEY_FALLBACKS = [k.strip() for k in os.getenv("SECRET_KEY_FALLBACKS", "").split(",") if k.strip()]

# `manage.py test`: the shared cache uses its own Redis database (see CACHES).
TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"

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
    "apps.core.middleware.JsonGZipMiddleware",  # JSON only; wraps everything below so error bodies compress too
    "apps.core.middleware.ApiExceptionMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# ─── CORS SECURITY CONFIGURATION ─────────────────────────────────────────────
# Load allowed CORS origins from .env (comma-separated list), with safe fallback 
# to local Vite React development ports.
raw_cors_origins = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
CORS_ALLOWED_ORIGINS = [origin.strip() for origin in raw_cors_origins.split(",") if origin.strip()]

# CRITICAL: Enforces Access-Control-Allow-Credentials header to permit browsers 
# to save and transmit our secure HttpOnly access_token/refresh_token cookies.
CORS_ALLOW_CREDENTIALS = True

# The app calls the API cross-origin (frontend :3000 -> API :8000), where a script
# can only read the CORS-safelisted response headers. The download UI honours
# `Retry-After` on a 503 web_size_preparing, so that header must be exposed.
CORS_EXPOSE_HEADERS = ["Retry-After"]

# 7G (7R-2 R3): the prepared-download page sends its job key in this request
# header, never in the query string (a query string lands in access logs).
from corsheaders.defaults import default_headers as _cors_default_headers  # noqa: E402
CORS_ALLOW_HEADERS = (*_cors_default_headers, "x-download-link-key")

# REST Framework Configuration (Versioned globally)
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.core.authentication.CookieJWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    
    "EXCEPTION_HANDLER": "apps.core.exceptions.custom_exception_handler",
    
    # Dynamic Throttling / Rate-Limiting Controls
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    # How many trusted reverse proxies sit in front of Django. DRF reads this
    # ONLY from here (a top-level NUM_PROXIES setting is ignored): with None,
    # every anonymous throttle was keyed on the raw client-sent
    # X-Forwarded-For, so a new header value per request got a fresh bucket
    # (SEC-01, debt row 78). 0 = no proxy (dev compose: the browser reaches
    # :8000 directly) -> REMOTE_ADDR; production.py sets 1 (the proxy that
    # appends/overwrites X-Forwarded-For) -> the address that proxy added.
    "NUM_PROXIES": int(os.getenv("NUM_PROXIES", "0")),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/day",                  # Standard guest threshold — fine for arbitrary/misc anon endpoints
        "user": "1000/hour",                # Standard authenticated photographer threshold
        "password_unlock": "5/minute",      # Tight brute-force security for private galleries
        # 7-C: reset requests per client address (429 past it). Reset EMAILS per
        # typed address are capped separately and silently (the answer never
        # changes): `password_reset_email`. Link checks and new-password
        # submissions per address: `password_reset_confirm`.
        "password_reset": "10/hour",
        "password_reset_email": "3/hour",
        "password_reset_confirm": "30/hour",
        "login": "5/minute",                # Tight brute-force security for photographer login
        "password_change": "10/hour",       # Per-user: guards the current-password check against guessing
        # Phase 4 (F-41 fix): ordinary public gallery browsing/streaming/
        # single-file-download/portfolio traffic previously fell through
        # to the blanket "anon: 100/day" above — fine for a rarely-hit
        # misc endpoint, but a real client viewing one gallery already
        # generates far more than 100 requests/day on its own (the
        # gallery payload, several pagination pages, a handful of
        # lightbox/video/download clicks) BEFORE counting that many
        # visitors can share one IP behind CGNAT or an office network,
        # all sharing the same throttle bucket. 120/minute is generous
        # enough that no ordinary visitor — even several behind the same
        # IP — ever notices it, while still bounding a genuine scraping/
        # abuse burst. Distinct from password_unlock (5/minute), which
        # stays tight on purpose: unlock attempts are a brute-force
        # target this scope is not.
        "public_gallery_browse": "120/minute",
        # Per-user: the upload page asks once per dropped batch whether its
        # videos fit the plan (photos/views.py::VideoPreflightView).
        "video_preflight": "60/minute",
        # Per-user (authenticated user id, never the IP): POST /api/v1/feedback/.
        "feedback": "5/hour",
        # 7-B: sign-ups per address (was the shared anon 100/day).
        "register": "10/hour",
        # 7-B: login attempts per ACCOUNT (the email), on top of `login` per address,
        # so a botnet with many addresses still gets only this many tries on one account.
        "login_account": "20/hour",
        # 7-B (debt row 92): token refresh per USER (from the refresh token), so
        # several people behind one NAT never share one anonymous bucket. One
        # tab refreshes about 4 times an hour (15 min access token).
        "token_refresh": "60/hour",
        # 7.5-A: the staff area, per staff user id. Reads (users list, audit log) and
        # the two account actions (suspend / reactivate) have their own buckets.
        "staff_list": "60/minute",
        "staff_action": "30/hour",
    }
}

# ─── SHARED CACHE (throttles, lockouts, notification de-duplication) ────────
# DRF throttles and the PIN/password lockout (apps/clients/lockout.py) count in
# Django's default cache. Without CACHES this was the per-PROCESS local-memory
# cache, so every gunicorn worker counted separately (debt row 108). Redis is
# already in the stack (the Celery broker); the cache uses its own database.
# `manage.py test` uses CACHE_REDIS_TEST_URL (another database) so a test run's
# cache.clear() never wipes the running app's counters. Without a URL (bare
# local dev with no Redis) it falls back to local memory; production.py refuses
# to boot without one.
CACHE_REDIS_URL = os.getenv("CACHE_REDIS_URL", "")
if TESTING and os.getenv("CACHE_REDIS_TEST_URL"):
    CACHE_REDIS_URL = os.getenv("CACHE_REDIS_TEST_URL")
if CACHE_REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": CACHE_REDIS_URL,
            "KEY_PREFIX": "kyapture",
        }
    }
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# ─── FAILED-ATTEMPT LOCKOUT: gallery password and download PIN (7-B, row 81) ─
# Counted per gallery + client address and per gallery, in the shared cache.
# A client is locked after GATE_CLIENT_MAX_FAILURES wrong values within
# GATE_CLIENT_WINDOW_SECONDS (a success clears its count); the gallery's gate
# is locked for everyone after GATE_GALLERY_MAX_FAILURES within
# GATE_GALLERY_WINDOW_SECONDS, and the photographer gets a bell notification.
# Changing the PIN / password is the reset (it clears both counts).
GATE_CLIENT_MAX_FAILURES = int(os.getenv("GATE_CLIENT_MAX_FAILURES", "5"))
GATE_CLIENT_WINDOW_SECONDS = int(os.getenv("GATE_CLIENT_WINDOW_SECONDS", str(15 * 60)))
GATE_GALLERY_MAX_FAILURES = int(os.getenv("GATE_GALLERY_MAX_FAILURES", "50"))
GATE_GALLERY_WINDOW_SECONDS = int(os.getenv("GATE_GALLERY_WINDOW_SECONDS", str(60 * 60)))
# 7G: a try that would exceed GATE_CLIENT_MAX_FAILURES counting the tries still in
# flight from the same address waits up to this long for them (guests behind one NAT
# typing the right value together), then gets a 429 that sets no lock.
GATE_INFLIGHT_WAIT_SECONDS = float(os.getenv("GATE_INFLIGHT_WAIT_SECONDS", "5"))

# Django admin login (apps/core/admin_login.py): failures per address and per
# account before the form is locked for the rest of the window.
ADMIN_LOGIN_MAX_FAILURES_PER_IP = int(os.getenv("ADMIN_LOGIN_MAX_FAILURES_PER_IP", "5"))
ADMIN_LOGIN_MAX_FAILURES_PER_ACCOUNT = int(os.getenv("ADMIN_LOGIN_MAX_FAILURES_PER_ACCOUNT", "10"))
ADMIN_LOGIN_WINDOW_SECONDS = int(os.getenv("ADMIN_LOGIN_WINDOW_SECONDS", str(15 * 60)))

# Feedback (apps/users/feedback_api.py). APP_VERSION is stamped on each feedback;
# a client-sent app_version is kept only when it is in this allowlist, else "unknown".
APP_VERSION = os.getenv("APP_VERSION", "dev")
FEEDBACK_ACCEPTED_APP_VERSIONS = [
    v.strip() for v in os.getenv("FEEDBACK_ACCEPTED_APP_VERSIONS", "").split(",") if v.strip()
]

# SimpleJWT Configuration for scale-safe session management
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),   # Short-lived for security
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),      # Long-lived for persistence
    "ROTATE_REFRESH_TOKENS": True,                    # Issues new refresh token on every refresh
    "BLACKLIST_AFTER_ROTATION": True,                 # Revokes old refresh token instantly
    # Explicit Defaults (For developer readability)
    "ALGORITHM": "HS256",
    # Own key for JWTs (SEC-13, debt row 88), so SECRET_KEY can be rotated
    # without logging everyone out, and vice versa. Defaults to SECRET_KEY.
    "SIGNING_KEY": os.getenv("JWT_SIGNING_KEY") or SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

# Core Auth and I18N configuration
AUTH_USER_MODEL = "users.User"

# Password policy. This was previously unset (an empty list), which made every
# validate_password() call in registration, password change and password reset
# a silent no-op - any password, including a single character, was accepted.
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ─── SECURE COOKIE FALLBACKS (Development Default) ───────────────────────────
# In development, SESSION_COOKIE_DOMAIN must be None so cookies are permitted 
# to be shared across localhost ports. Secure flags default to False to avoid 
# SSL redirect loops on unencrypted HTTP local connections.
SESSION_COOKIE_DOMAIN = os.getenv("SESSION_COOKIE_DOMAIN", None)
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "False") == "True"
CSRF_COOKIE_SECURE = os.getenv("CSRF_COOKIE_SECURE", "False") == "True"

# Media files (Uploaded assets like photographer avatars and receipts).
# Resolve from the backend package directory rather than BASE_DIR: the
# Windows checkout has an outer repository directory, while the Docker image
# runs the backend directly at /app. This keeps both environments on the
# same mounted /app/media path inside Compose.
MEDIA_URL = "/media/"
BACKEND_DIR = Path(__file__).resolve().parents[2]
MEDIA_ROOT = BACKEND_DIR / "media"

# Static files (Django Admin panel CSS, JavaScript, and Icons)
STATIC_URL = "/static/"
STATIC_ROOT = BACKEND_DIR / "staticfiles"


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
    # 2. No AWS Credentials found: Gracefully fall back to local disk storage.
    # The default storage holds private files (payment receipts), so its URLs
    # are signed and expire like the S3 ones (7-B, debt row 83).
    STORAGES = {
        "default": {
            "BACKEND": "apps.core.storage.SignedFileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
    
# ─────────────────────────────────────────────────────────────
# CELERY BACKGROUND WORKER CONFIGURATION
# ─────────────────────────────────────────────────────────────

# Dynamic Redis broker routing. Falls back to local Redis in development.
# Database index /0 is used for task brokering, and /1 is used for storing results.
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/1")

# Enforce secure JSON payload serialization
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"

# Synchronize background task scheduling with Django's global timezone settings
CELERY_TIMEZONE = TIME_ZONE

# Prevent ghost tasks: Acknowledges task completion only after successful execution
CELERY_TASK_ACKS_LATE = True

# Limits active worker prefetching to prevent RAM spikes on large media transcodes
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

# Web Size derivatives (apps/clients/web_size.py) are encoded by their own
# queue so the CPU they may use is bounded by that worker's --concurrency
# (docker-compose `celery_websize`), never by the web request threads.
WEB_SIZE_QUEUE = "websize"
CELERY_TASK_ROUTES = {
    "apps.clients.tasks.generate_web_size": {"queue": WEB_SIZE_QUEUE},
}
# How long a single-photo request waits for a cold Web Size to be encoded
# before answering 503 "still preparing" (a warm request never waits).
WEB_SIZE_WAIT_SECONDS = int(os.getenv("WEB_SIZE_WAIT_SECONDS", "25"))
# `Retry-After` sent with that 503: when the client should ask again.
WEB_SIZE_RETRY_AFTER_SECONDS = int(os.getenv("WEB_SIZE_RETRY_AFTER_SECONDS", "3"))

# ─────────────────────────────────────────────────────────────
# TRASH / PURGE RETENTION (Phase 4 — storage-leak fix, F-30)
# ─────────────────────────────────────────────────────────────
# How long a soft-deleted gallery (Gallery.is_active=False,
# Gallery.trashed_at set) stays recoverable before the scheduled purge
# task (apps/galleries/tasks.py::purge_trashed_galleries) hard-deletes
# it and its media. Env-overridable so staging can use a short window
# for testing without touching code.
GALLERY_TRASH_RETENTION_DAYS = int(os.getenv("GALLERY_TRASH_RETENTION_DAYS", "30"))

# How long a ClientSession stays valid after creation before the
# scheduled cleanup task purges it (Phase 4 — auth hardening, ClientSession
# lifecycle). A session this old is treated as expired even if never
# explicitly revoked (e.g. by a password change) — see
# apps/clients/views.py's session-validation gate, which checks this
# expiry the same way it already checks token/gallery match.
CLIENT_SESSION_TTL_DAYS = int(os.getenv("CLIENT_SESSION_TTL_DAYS", "30"))

# Lifetime of the signed download access token a client earns by passing the
# download PIN / email step (see apps/clients/download_access.py). Short on
# purpose: it only needs to cover one browsing-and-downloading visit, and it
# is additionally invalidated the moment the gallery's PIN changes.
DOWNLOAD_ACCESS_TTL_SECONDS = int(os.getenv("DOWNLOAD_ACCESS_TTL_SECONDS", str(2 * 60 * 60)))

# Prepared (background) gallery/set ZIPs. A READY job — and the ZIPs stored in
# private storage for it — lives this long (7 days), then the daily purge task
# deletes both. Its file links work, repeatedly, until then.
DOWNLOAD_JOB_TTL_SECONDS = int(os.getenv("DOWNLOAD_JOB_TTL_SECONDS", str(7 * 24 * 60 * 60)))
# 7G (7R-2 R3): the job key is read from the X-Download-Link-Key header only. A
# `?link_token=` query (pages built before 7G) is refused with 400, unless this
# transition flag is set while old pages are still open. Off by default.
DOWNLOAD_LINK_KEY_QUERY_FALLBACK = os.getenv("DOWNLOAD_LINK_KEY_QUERY_FALLBACK", "false").lower() == "true"
# How long one signed file URL (handed out by the job-status endpoint) works.
# It is bound to ONE file of ONE job. 7-B: one hour, not the job's week: the
# ready page asks the status endpoint for a fresh URL on every click (and the
# emailed link, which lives as long as the job, opens that page), so a file URL
# that sits in browser or download-manager history stops working soon after.
DOWNLOAD_FILE_URL_TTL_SECONDS = int(os.getenv("DOWNLOAD_FILE_URL_TTL_SECONDS", str(60 * 60)))
# A prepared download is split into several ZIP parts once the photos in one
# part would pass this many bytes ("...-photo-download-1of3.zip"). A single
# file bigger than the limit still gets a part of its own.
DOWNLOAD_ZIP_PART_MAX_BYTES = int(os.getenv("DOWNLOAD_ZIP_PART_MAX_BYTES", str(2 * 1024 ** 3)))  # 2 GB
# "Your photos are ready" emails: at most this many per hour for one recipient
# address, one requesting IP and one gallery. Over a limit the email is skipped
# silently (the visitor still sees the ready page); nothing tells them why.
DOWNLOAD_READY_EMAIL_WINDOW_SECONDS = int(os.getenv("DOWNLOAD_READY_EMAIL_WINDOW_SECONDS", str(60 * 60)))
DOWNLOAD_READY_EMAIL_LIMIT_PER_EMAIL = int(os.getenv("DOWNLOAD_READY_EMAIL_LIMIT_PER_EMAIL", "5"))
DOWNLOAD_READY_EMAIL_LIMIT_PER_IP = int(os.getenv("DOWNLOAD_READY_EMAIL_LIMIT_PER_IP", "10"))
DOWNLOAD_READY_EMAIL_LIMIT_PER_GALLERY = int(os.getenv("DOWNLOAD_READY_EMAIL_LIMIT_PER_GALLERY", "30"))
# A job still PREPARING after this long is treated as failed (worker lost).
DOWNLOAD_JOB_STALE_SECONDS = int(os.getenv("DOWNLOAD_JOB_STALE_SECONDS", str(30 * 60)))

# DownloadLog retention (Phase 4 — DB cleanup). Purely an operational
# cleanup of old lead-generation rows; not a security control.
DOWNLOAD_LOG_RETENTION_DAYS = int(os.getenv("DOWNLOAD_LOG_RETENTION_DAYS", "365"))

# ─────────────────────────────────────────────────────────────
# SYNCHRONOUS ZIP DOWNLOAD LIMITS (Phase 4 — download hardening)
# ─────────────────────────────────────────────────────────────
# PublicGalleryDownloadView still compiles a gallery's ZIP synchronously
# inside the request/response cycle (streamed to disk in 1MB chunks, not
# held in RAM — see that view's own docstring). That's an acceptable MVP
# tradeoff for a typical gallery, but with no cap at all a single request
# for a pathologically large selection (thousands of assets, or many GB)
# could tie up a gunicorn worker for an unbounded amount of time. These
# are a deliberately generous technical ceiling — not a plan/business
# limit — that reject only the genuinely extreme case with a clear 400,
# rather than the smallest safe fix here being a full async-job rewrite.
SYNC_ZIP_MAX_ASSET_COUNT = int(os.getenv("SYNC_ZIP_MAX_ASSET_COUNT", "500"))
SYNC_ZIP_MAX_TOTAL_BYTES = int(os.getenv("SYNC_ZIP_MAX_TOTAL_BYTES", str(5 * 1024 ** 3)))  # 5 GB

# ─────────────────────────────────────────────────────────────
# SYSTEM LOGGING CONFIGURATION (Audit & Security Compliance)
# ─────────────────────────────────────────────────────────────

# Dynamic Bootstrap: Enforce directory presence to prevent FileHandler initialization crashes
LOGS_DIR = BASE_DIR / "backend" / "logs"
os.makedirs(LOGS_DIR, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
        "file": {
            "level": "WARNING",  # Prevents disk-space inflation by logging only Warnings/Errors
            "class": "logging.FileHandler",
            "filename": os.path.join(LOGS_DIR, "django.log"),
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": True,
        },
        "django.request": {
            "handlers": ["file"],
            "level": "ERROR",  # Captures unhandled 500 server crashes and bad HTTP requests
            "propagate": False,
        },
        
        "apps.users.views": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# ─────────────────────────────────────────────────────────────
# TRANSACTIONAL EMAIL (password reset today; anything else later)
# ─────────────────────────────────────────────────────────────
# EMAIL_BACKEND is deliberately NOT set here — each environment file picks
# its own:
#   development.py -> django.core.mail.backends.console.EmailBackend
#                      (prints to the runserver terminal, same convenience
#                      the old print()-based stub had)
#   production.py  -> django_ses.SESBackend
#                      (real delivery via Amazon SES; hard-fails at boot
#                      if DEFAULT_FROM_EMAIL isn't set — see production.py)
# Leaving it undefined here means a brand-new environment file that forgets
# to set EMAIL_BACKEND fails loudly the first time mail is sent, instead of
# silently no-op'ing the way the previous print()-only implementation did.
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "Kyapture <no-reply@kyapture.com>")
SERVER_EMAIL = os.getenv("SERVER_EMAIL", DEFAULT_FROM_EMAIL)
EMAIL_SUBJECT_PREFIX = "[Kyapture] "
EMAIL_TIMEOUT = 10  # seconds — a stalled mail provider call should never hang a request/worker

# SMTP settings for any environment that sends through an SMTP server (dev
# compose: Mailpit). Read from the environment only; nothing secret is ever
# committed. production.py keeps Amazon SES unless EMAIL_BACKEND says otherwise.
EMAIL_HOST = os.getenv("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "1025"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "false").lower() == "true"
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "false").lower() == "true"

# 7-C: how long an emailed "forgot password" link works (apps/users/password_reset.py).
PASSWORD_RESET_TOKEN_MINUTES = int(os.getenv("PASSWORD_RESET_TOKEN_MINUTES", "30"))

# Public origin of the deployed React SPA. Views build outgoing email links
# (password reset, etc.) from this setting instead of hardcoding a hostname,
# so the exact same view code produces a working link in every environment.
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
