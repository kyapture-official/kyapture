# backend/apps/core/media.py
"""
The DEBUG-only /media/ route (config/urls.py). 7-B (SEC-06 / debt row 83).

It used to be Django's `static()` helper over all of MEDIA_ROOT: anyone who
reached the dev server could fetch any original, Download Master, cached Web
Size, prepared ZIP or payment receipt by its path. Now:

  - a PUBLIC file (the names PublicMediaStorage writes: WebP tiers, video poster
    and playback MP4, avatars and logos) is served as before;
  - anything else is served only with a valid, unexpired signature from
    SignedFileSystemStorage.url() (apps/core/storage.py), i.e. exactly the URLs
    the app hands out (an owner's original_url, a staff receipt link), which
    expire after an hour like S3's presigned URLs;
  - everything else is a plain 404 (no hint that the file exists).

Production never uses this route (DEBUG is off and media lives on S3).
"""
import re

from django.conf import settings
from django.core import signing
from django.http import Http404
from django.views.static import serve

from .storage import LOCAL_SIGNED_URL_SALT, LOCAL_SIGNED_URL_SECONDS

_GALLERY = r'photographers/[^/]+/galleries/[^/]+/(?:[0-9a-f]{32}/)?'
PUBLIC_PATHS = (
    re.compile(_GALLERY + r'photos/[^/]+_(?:display|medium)\.webp'),
    re.compile(_GALLERY + r'thumbnails/[^/]+_thumb\.webp'),
    re.compile(_GALLERY + r'videos/[^/]+_(?:poster\.jpg|playback\.mp4|preview\.webm)'),
    re.compile(r'photographers/[^/]+/profile/avatar_[0-9a-f]+\.[a-z0-9]+'),
    re.compile(r'photographers/[^/]+/branding/logo_[0-9a-f]+\.[a-z0-9]+'),
)


def is_public_path(path):
    return any(pattern.fullmatch(path) for pattern in PUBLIC_PATHS)


def signature_is_valid(path, signature):
    if not signature:
        return False
    try:
        signing.TimestampSigner(salt=LOCAL_SIGNED_URL_SALT).unsign(
            f'{path}:{signature}', max_age=LOCAL_SIGNED_URL_SECONDS,
        )
    except signing.BadSignature:      # includes SignatureExpired
        return False
    return True


def serve_media(request, path):
    if '..' in path.split('/'):
        raise Http404
    if not (is_public_path(path) or signature_is_valid(path, request.GET.get('sig', ''))):
        raise Http404
    return serve(request, path, document_root=settings.MEDIA_ROOT)
