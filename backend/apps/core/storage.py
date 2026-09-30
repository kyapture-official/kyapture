# backend/apps/core/storage.py
"""
Phase 2 (media delivery): split media into two storage classes with
different security/caching contracts, instead of the single bucket-wide
"default" storage every FileField/ImageField shared before.

WHY THIS EXISTS — confirmed gap in the prior single-storage setup
(config/settings/base.py's old STORAGES["default"]):
  - AWS_QUERYSTRING_AUTH=True (production.py) meant literally every file —
    originals AND already-public derivatives (WebP thumbnails, the WebP
    display image, video posters) — got a presigned URL that expires in
    1 hour and changes every time it's regenerated. A CDN cannot cache a
    URL that changes on every request; browsers can't cache it past the
    signature's expiry either. That defeats "cacheable CDN delivery" for
    exactly the files that most need to be cheaply, aggressively cached.
  - default_acl="private" + file_overwrite=False bucket-wide also meant a
    *retried* derivative-generation task (Celery `self.retry(...)`) would
    get a NEW randomized key each time (django-storages' default
    behavior when file_overwrite=False and the key already exists), never
    overwriting the previous attempt's file — a real orphaned-derivative
    leak on every retry.

Two storage classes now exist:

- PrivateMediaStorage — for `original_file` only. Unchanged behavior:
  private ACL, signed/expiring URLs. Originals must never be guessable or
  cacheable by a shared CDN; they're only ever reached through the app's
  own authorization-gated download endpoints.
- PublicMediaStorage — for every derivative (WebP thumbnail/medium/display,
  video poster, video H.264 playback MP4). Public-read, no query-string
  signing (so the URL is stable forever), `file_overwrite=True` (so a
  retry overwrites the same deterministic key — see get_*_path() in
  photos/models.py, which already derives keys from the asset's UUID, not
  from a random name), and a long `Cache-Control: public, max-age=...,
  immutable` response header baked into every object's metadata at write
  time — exactly what lets a CDN (or a browser) cache a derivative
  indefinitely without a single revalidation request. "Immutable" is
  correct here because retrying/regenerating a derivative reuses the SAME
  key — once processing succeeds, that key's bytes never change again;
  the *only* way a derivative's content changes is a full asset
  delete+re-upload, which mints a brand new key (a new MediaAsset UUID).

Local development (no AWS credentials in the environment) falls back to
plain Django FileSystemStorage for both — there is no query-string
signing or ACL concept on local disk, and `allow_overwrite=True` mirrors
the same idempotent-retry behavior PublicMediaStorage gets in production.
"""
import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage

_S3_CONFIGURED = bool(
    os.getenv("AWS_ACCESS_KEY_ID")
    and os.getenv("AWS_SECRET_ACCESS_KEY")
    and os.getenv("AWS_STORAGE_BUCKET_NAME")
)

# One year — effectively "forever" for a cache header, and the standard
# value for immutable, content-addressed-by-UUID assets. Matches the
# frontend's own Vite build asset caching convention
# (frontend/nginx.conf's `location /assets/` block).
_PUBLIC_MAX_AGE_SECONDS = 60 * 60 * 24 * 365

if _S3_CONFIGURED:
    from storages.backends.s3boto3 import S3Boto3Storage

    class PrivateMediaStorage(S3Boto3Storage):
        bucket_name = os.getenv("AWS_STORAGE_BUCKET_NAME")
        region_name = os.getenv("AWS_S3_REGION_NAME", "us-east-1")
        default_acl = "private"
        querystring_auth = True
        querystring_expire = 3600
        file_overwrite = False

    class PublicMediaStorage(S3Boto3Storage):
        bucket_name = os.getenv("AWS_STORAGE_BUCKET_NAME")
        region_name = os.getenv("AWS_S3_REGION_NAME", "us-east-1")
        default_acl = "public-read"
        querystring_auth = False
        file_overwrite = True
        object_parameters = {
            "CacheControl": f"public, max-age={_PUBLIC_MAX_AGE_SECONDS}, immutable",
        }

else:
    class PrivateMediaStorage(FileSystemStorage):
        """Local dev fallback — disk has no ACL/signing concept."""
        pass

    class PublicMediaStorage(FileSystemStorage):
        """
        Local dev fallback. `allow_overwrite=True` (Django 5.1+) gives the
        same idempotent-retry behavior as production's file_overwrite=True
        — a regenerated derivative overwrites its previous copy on disk
        instead of accumulating `_XmZ9q1.webp`-suffixed orphans.
        """
        def __init__(self, *args, **kwargs):
            kwargs.setdefault("allow_overwrite", True)
            super().__init__(*args, **kwargs)
